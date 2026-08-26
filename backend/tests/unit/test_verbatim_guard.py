"""대화 원문이 결과로 새어 나가지 않는지.

**지시만으로는 막지 못한다.** 2026-08-26 실측에서 실제로 새어 나왔다.
Analysis Agent 가 `notableMoments` 에 원문을 담았고, Report Agent 가 그것을
인용해 사용자 화면에 실렸다. Report Agent 는 대화 원문을 입력으로 받지
않는데도 이 경로로 우회됐다.

절대 규칙이므로 모델의 준수에 기대지 않는다. `AI-프롬프트-명세.md` 3.5.
"""

import pytest

from app.ai.guard.verbatim import MIN_QUOTE_LENGTH, strip_verbatim
from app.domain.model.analysis import (
    MoneySignals,
    PromiseSignals,
    RelationshipAnalysisData,
    SpeakerScores,
)
from app.domain.model.conversation import (
    ConversationData,
    ConversationMeta,
    Message,
)
from app.domain.value_object.enums import Speaker, TimeSource


def conversation(*texts: str) -> ConversationData:
    messages = tuple(
        Message(
            index=index,
            speaker=Speaker.ME if index % 2 == 0 else Speaker.PEER,
            text=text,
            sent_at=1_756_000_000 + index * 600,
            time_source=TimeSource.EXPLICIT,
            image_index=0,
        )
        for index, text in enumerate(texts)
    )
    return ConversationData(
        messages=messages,
        meta=ConversationMeta(
            image_count=1,
            message_count=len(messages),
            dropped_count=0,
            time_coverage=1.0,
            span_seconds=len(messages) * 600,
        ),
    )


def analysis(*moments: str) -> RelationshipAnalysisData:
    return RelationshipAnalysisData(
        emotional_tone=SpeakerScores(me=50, peer=50),
        affection_signals=SpeakerScores(me=50, peer=50),
        effort_level=SpeakerScores(me=50, peer=50),
        conflict_level=10,
        topic_depth=50,
        promise_signals=PromiseSignals(proposed=0, fulfilled=0, declined=0),
        money_signals=MoneySignals(lent=0, borrowed=0, resolved=0),
        notable_moments=moments,
    )


class TestStripVerbatim:
    def test_원문을_그대로_담은_항목을_버린다(self):
        convo = conversation("알겠어 그때 연락할게", "응 기다릴게")
        result = strip_verbatim(analysis("상대가 '그때 연락할게'라고 미뤘다"), convo)

        assert result.notable_moments == ()

    def test_따옴표가_없어도_잡는다(self):
        convo = conversation("알겠어 그때 연락할게", "응 기다릴게")
        result = strip_verbatim(analysis("상대가 그때 연락할게 라고 했다"), convo)

        assert result.notable_moments == ()

    def test_요약된_서술은_남긴다(self):
        convo = conversation("알겠어 그때 연락할게", "응 기다릴게")
        summary = "상대가 약속을 구체화하지 않고 미루는 편이다"
        result = strip_verbatim(analysis(summary), convo)

        assert result.notable_moments == (summary,)

    def test_짧은_조각은_버리지_않는다(self):
        # "ㅇㅇ", "그래" 까지 잡으면 정상 서술이 함께 사라진다
        convo = conversation("ㅇㅇ", "그래", "알겠어 그때 연락할게")
        summary = "상대가 그래도 답은 한다"
        result = strip_verbatim(analysis(summary), convo)

        assert result.notable_moments == (summary,)

    def test_공백과_문장부호가_달라도_잡는다(self):
        convo = conversation("내일 시간 돼? 얼굴 좀 보자", "어 좋아")
        result = strip_verbatim(analysis("나는 내일시간돼얼굴좀보자 라고 물었다"), convo)

        assert result.notable_moments == ()

    def test_섞여_있으면_원문만_버린다(self):
        convo = conversation("알겠어 그때 연락할게", "응 기다릴게")
        result = strip_verbatim(
            analysis("상대가 '그때 연락할게'라고 미뤘다", "전반적으로 답이 짧다"), convo
        )

        assert result.notable_moments == ("전반적으로 답이 짧다",)

    def test_다른_값은_건드리지_않는다(self):
        convo = conversation("알겠어 그때 연락할게", "응 기다릴게")
        source = analysis("상대가 '그때 연락할게'라고 미뤘다")
        result = strip_verbatim(source, convo)

        assert result.emotional_tone == source.emotional_tone
        assert result.conflict_level == source.conflict_level

    @pytest.mark.parametrize("length", [MIN_QUOTE_LENGTH - 1, MIN_QUOTE_LENGTH])
    def test_하한_경계(self, length):
        quote = "가" * length
        convo = conversation(quote, "응 기다릴게")
        result = strip_verbatim(analysis(f"상대가 {quote} 라고 했다"), convo)

        expected = () if length >= MIN_QUOTE_LENGTH else (f"상대가 {quote} 라고 했다",)
        assert result.notable_moments == expected


class TestPipelineAppliesGuard:
    """파이프라인이 가드를 실제로 부르는지.

    `strip_verbatim` 이 잘 동작해도 호출하지 않으면 소용없다. 그 한 줄이
    사라지면 원문이 다시 사용자 화면까지 간다.

    **리포트 본문으로 확인하면 안 된다.** StubLlmProvider 는 프롬프트를 무시하고
    정해진 글을 돌려주므로, 가드를 빼도 리포트에는 원문이 나타나지 않는다.
    그래서 Report Agent 가 **무엇을 받았는지**를 본다. 그 자리가 원문이 밖으로
    나가는 마지막 관문이다.
    """

    @pytest.mark.asyncio
    async def test_리포트_작성기에_원문이_전달되지_않는다(self):
        from app.application.service.pipeline import AnalysisPipeline
        from app.config.settings import Settings
        from tests.unit.test_analysis_service import uploads

        pipeline = AnalysisPipeline.from_settings(Settings())
        seen: dict = {}

        run_analysis = pipeline.analysis_agent.run

        async def leaky(convo):
            # 모델이 대화 원문을 notableMoments 에 담아 보낸 상황을 만든다
            result = await run_analysis(convo)
            seen["quote"] = max((m.text for m in convo.messages), key=len)
            return result.model_copy(
                update={"notable_moments": (f"상대가 '{seen['quote']}'라고 말했다",)}
            )

        run_report = pipeline.report_agent.run

        async def capture(analysis, scores):
            seen["received"] = analysis.notable_moments
            return await run_report(analysis, scores)

        pipeline.analysis_agent.run = leaky
        pipeline.report_agent.run = capture

        await pipeline.run(_NullJob(), [image.data for image in uploads(3)])

        assert seen["received"] == (), (
            f"원문을 담은 항목이 Report Agent 로 넘어갔다: {seen['received']}"
        )


class _NullJob:
    """단계 전환만 받아 넘기는 자리표시자."""

    job_id = "test-job"
    expires_at = 1_787_733_000

    def advance(self, stage) -> None:
        pass
