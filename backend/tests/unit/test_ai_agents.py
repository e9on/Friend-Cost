"""Analysis Agent와 Report Agent.

기준 명세 7장. 실제 모델은 성능 평가 이후에 붙이므로, 여기서는
Provider 인터페이스와 검증·재시도 규약만 확인한다.
"""

import json

import pytest

from app.ai.agent.analysis import AnalysisAgent
from app.ai.agent.report import ReportAgent
from app.ai.provider.base import LlmProvider, LlmRequest, LlmResponse
from app.ai.provider.stub import StubLlmProvider
from app.common.errors import AppError, ErrorCode
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.report import DISCLAIMER, ReportData
from tests.builders import alternating, analysis, conversation


class ScriptedProvider(LlmProvider):
    """미리 정해둔 응답을 순서대로 돌려주는 가짜 Provider."""

    name = "scripted"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("예정된 응답보다 많이 호출되었다")
        return LlmResponse(text=self._responses.pop(0), input_tokens=10, output_tokens=5)


class ExplodingProvider(LlmProvider):
    name = "exploding"

    async def complete(self, request: LlmRequest) -> LlmResponse:
        raise TimeoutError("연결 실패")


def valid_analysis_json() -> str:
    return analysis().model_dump_json(by_alias=True)


def valid_report_json() -> str:
    return json.dumps(
        {
            "headline": "서로 챙기지만 균형이 조금 기운 사이",
            "summary": "연락은 이어지지만 시작하는 쪽이 한쪽으로 쏠려 있다.",
            "sections": [
                {"title": "연락의 흐름", "body": "먼저 말을 거는 쪽이 대체로 정해져 있다."},
                {"title": "지켜볼 지점", "body": "약속이 미뤄지는 일이 반복되고 있다."},
            ],
            "advice": "다음 약속은 날짜부터 먼저 정해 보자.",
        },
        ensure_ascii=False,
    )


class TestAnalysisAgent:
    async def test_returns_structured_analysis(self):
        provider = ScriptedProvider(valid_analysis_json())

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)
        assert 0 <= result.conflict_level <= 100

    async def test_retries_once_when_the_schema_does_not_match(self):
        provider = ScriptedProvider("이건 JSON이 아니다", valid_analysis_json())

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)
        assert len(provider.requests) == 2

    async def test_gives_up_after_the_single_retry(self):
        provider = ScriptedProvider("망가진 응답", "여전히 망가진 응답")

        with pytest.raises(AppError) as caught:
            await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert caught.value.code is ErrorCode.LLM_SCHEMA_INVALID
        assert len(provider.requests) == 2

    async def test_transport_failure_maps_to_llm_failed(self):
        with pytest.raises(AppError) as caught:
            await AnalysisAgent(ExplodingProvider()).run(conversation(alternating(20)))

        assert caught.value.code is ErrorCode.LLM_FAILED

    async def test_clamps_out_of_range_values_instead_of_failing(self):
        payload = json.loads(valid_analysis_json())
        payload["conflictLevel"] = 480
        provider = ScriptedProvider(json.dumps(payload))

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert result.conflict_level == 100

    async def test_prompt_marks_the_conversation_as_untrusted_data(self):
        provider = ScriptedProvider(valid_analysis_json())

        await AnalysisAgent(provider).run(conversation(alternating(20)))

        prompt = provider.requests[0].user
        assert "<conversation>" in prompt and "</conversation>" in prompt
        system = provider.requests[0].system
        assert "지시" in system  # 대화 안의 지시를 따르지 말라는 방어 문구


class TestReportAgent:
    async def test_returns_a_report(self):
        provider = ScriptedProvider(valid_report_json())
        scores = _scores()

        result = await ReportAgent(provider).run(analysis(), scores)

        assert isinstance(result, ReportData)
        assert result.disclaimer == DISCLAIMER

    async def test_disclaimer_is_injected_by_the_server(self):
        payload = json.loads(valid_report_json())
        payload["disclaimer"] = "모델이 멋대로 쓴 문구"
        provider = ScriptedProvider(json.dumps(payload, ensure_ascii=False))

        result = await ReportAgent(provider).run(analysis(), _scores())

        assert result.disclaimer == DISCLAIMER

    async def test_does_not_receive_the_conversation_text(self):
        provider = ScriptedProvider(valid_report_json())

        await ReportAgent(provider).run(analysis(), _scores())

        prompt = provider.requests[0].user
        assert "<conversation>" not in prompt

    async def test_rejects_a_report_that_exceeds_length_limits(self):
        payload = json.loads(valid_report_json())
        payload["summary"] = "가" * 500
        provider = ScriptedProvider(
            json.dumps(payload, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)
        )

        with pytest.raises(AppError) as caught:
            await ReportAgent(provider).run(analysis(), _scores())

        assert caught.value.code is ErrorCode.LLM_SCHEMA_INVALID


class TestStubProvider:
    async def test_produces_valid_analysis_payloads(self):
        result = await AnalysisAgent(StubLlmProvider()).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)

    async def test_produces_valid_report_payloads(self):
        result = await ReportAgent(StubLlmProvider()).run(analysis(), _scores())

        assert isinstance(result, ReportData)

    async def test_is_deterministic_for_the_same_input(self):
        convo = conversation(alternating(20))

        first = await AnalysisAgent(StubLlmProvider()).run(convo)
        second = await AnalysisAgent(StubLlmProvider()).run(convo)

        assert first == second

    async def test_varies_with_the_conversation(self):
        talkative = conversation(alternating(60))
        quiet = conversation(alternating(20))

        a = await AnalysisAgent(StubLlmProvider()).run(talkative)
        b = await AnalysisAgent(StubLlmProvider()).run(quiet)

        assert a != b


def _scores():
    from app.algorithm.calculator import calculate_scores

    return calculate_scores(conversation(alternating(20)), analysis())


class TestReplySpeedUnit:
    """리포트에 초 단위를 넘기지 않는다.

    실측 리포트에 이런 문장이 실렸다.

        평균 답장 속도는 내가 1305초, 상대가 1834초로 내가 더 빠르게…

    **1305초로 생각하는 사람은 없다.** 점수 블록이 `평균답장속도초` 라는
    이름으로 날숫자를 넘기니 모델이 그대로 옮겨 적는다.

    숫자가 아니라 완성된 문자열("22분")을 넘긴다. 그러면 모델이 단위를
    지어낼 여지가 없다.
    """

    def _block(self, me, peer):
        from app.ai.agent.report import _render_scores
        from app.domain.model.score import (
            RelationshipScoreData,
            ReplySeconds,
        )

        return _render_scores(
            RelationshipScoreData(
                friend_fee=12_000,
                intimacy=60,
                breakup_risk=20,
                first_contact_ratio=0.5,
                avg_reply_seconds=ReplySeconds(me=me, peer=peer),
                contact_balance=90,
            )
        )

    def test_초_단위_날숫자를_넘기지_않는다(self):
        block = self._block(1305, 1834)

        assert "1305" not in block
        assert "1834" not in block

    def test_분으로_적어_넘긴다(self):
        block = self._block(1305, 1834)

        assert "22분" in block
        assert "31분" in block

    def test_한_시간이_넘으면_시간과_분으로(self):
        block = self._block(5400, 7200)

        assert "1시간 30분" in block
        assert "2시간" in block

    def test_일_분_미만은_일_분_이내로(self):
        block = self._block(45, 30)

        assert "1분 이내" in block

    def test_표본이_없으면_모른다고_적는다(self):
        # 0분과 구별되어야 한다. 빠른 답장과 표본 없음은 다른 뜻이다
        block = self._block(None, 600)

        assert "알 수 없음" in block

    def test_화면과_같은_방식으로_반올림한다(self):
        """프론트의 `formatDuration` 과 눈금이 같아야 한다.

        절사하면 화면에 "22분"이라 적힌 값이 글에는 "21분"으로 쓰인다.
        같은 숫자를 두 곳이 달리 말하는 셈이다.
        """
        from app.ai.agent.report import _minutes

        # 1305초 = 21.75분. 절사하면 21, 반올림하면 22
        assert _minutes(1305) == "22분"
        assert _minutes(1834) == "31분"
        assert _minutes(90) == "2분"


class TestFeeSignIsNotSentToTheModel:
    """부호를 넘기지 않는다. 넘기면 모델이 부호를 설명한다.

    실측 리포트에 이런 문장이 실렸다.

        상대가 더 많은 노력을 기울이고 있어 **친구비가 음수로 나타났지만**,
        이는 관계의 질을 떨어뜨리지 않습니다.

    `음수` 는 내부 용어다. 사용자는 화면에서 부호를 본 적이 없다. 절댓값과
    방향 문구만 본다. 글에만 나오면 화면에 없는 개념을 설명하는 셈이다.

    `평균답장속도` 를 초에서 분으로 바꾼 것과 같은 방법이다. 말로 부탁하지
    않고 **입력에서 없앤다.** `AI-프롬프트-명세.md` 5.3.3.
    """

    def _block(self, friend_fee):
        from app.ai.agent.report import _render_scores
        from app.domain.model.score import RelationshipScoreData, ReplySeconds

        return _render_scores(
            RelationshipScoreData(
                friend_fee=friend_fee,
                intimacy=60,
                breakup_risk=20,
                first_contact_ratio=0.5,
                avg_reply_seconds=ReplySeconds(me=120, peer=180),
                contact_balance=90,
            )
        )

    def test_마이너스_부호를_넘기지_않는다(self):
        block = self._block(-79_000)

        assert "-79000" not in block
        assert "-79,000" not in block

    def test_금액은_절댓값으로_넘긴다(self):
        assert "79000" in self._block(-79_000)

    def test_방향을_말로_넘긴다(self):
        assert "내가" in self._block(-79_000)
        assert "친구가" in self._block(79_000)

    def test_화면과_같은_말을_쓴다(self):
        """화면은 "친구에게 친구비를 주세요"라고 쓴다.

        글이 "내가 낼 몫"이라고 쓰면 같은 것을 두 이름으로 부르는 셈이다.
        답장 속도를 초에서 분으로 맞춘 것과 같은 이유다.
        """
        assert "친구비를 주어야" in self._block(-79_000)

    def test_두_방향의_문구가_다르다(self):
        import json

        pay = json.loads(self._block(-79_000))["친구비"]["방향"]
        receive = json.loads(self._block(79_000))["친구비"]["방향"]

        assert pay != receive

    def test_비긴_경우도_말이_된다(self):
        import json

        assert json.loads(self._block(0))["친구비"]["금액(원)"] == 0


class TestPromptForbidsSignWords:
    """금지어는 보강이다. 근본은 입력에서 부호를 없애는 것이다."""

    def test_음수_양수를_쓰지_말라고_적혀_있다(self):
        from app.ai.prompt.templates import REPORT_SYSTEM

        assert "음수" in REPORT_SYSTEM and "쓰지 않는다" in REPORT_SYSTEM

    def test_프롬프트가_친구비를_부호로_설명하지_않는다(self):
        """프롬프트 본문이 '음수면 …' 하고 가르치면 모델이 그 말을 옮긴다."""
        from app.ai.prompt.templates import REPORT_SYSTEM

        assert "음수면" not in REPORT_SYSTEM
