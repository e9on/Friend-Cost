"""Report Agent.

기준 명세 7장. 계산된 점수를 사람이 읽을 글로 옮긴다. LLM 호출 1회.

대화 원문을 입력으로 받지 않는다. 입력 토큰을 줄이기 위한 의도적 제약이며,
동시에 원문이 한 번 더 외부로 나가는 경로를 없애는 효과도 있다.
"""

import json

from app.common.numeric import round_half_up

from app.ai.agent.base import call_and_validate
from app.ai.prompt.templates import REPORT_SYSTEM, report_user_prompt
from app.ai.provider.base import LlmProvider, LlmRequest
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.report import DISCLAIMER, ReportData
from app.domain.model.score import RelationshipScoreData

MAX_OUTPUT_TOKENS = 700


def _minutes(seconds: int | None) -> str:
    """답장 속도를 사람이 쓰는 단위로 적는다.

    **숫자가 아니라 완성된 문자열을 넘긴다.** 날숫자에 `초` 라는 이름만
    붙여 보냈더니 모델이 그대로 옮겨 적었다.

        평균 답장 속도는 내가 1305초, 상대가 1834초로 내가 더 빠르게…

    1305초로 생각하는 사람은 없다. 문자열로 넘기면 모델이 단위를 지어낼
    여지가 없다.

    표본이 없을 때(``None``)를 "0분"이 아니라 "알 수 없음"으로 적는 이유는,
    빠른 답장과 표본 없음이 다른 뜻이기 때문이다.
    """
    if seconds is None:
        return "알 수 없음"
    if seconds < 60:
        return "1분 이내"

    # 절사가 아니라 반올림이다. 화면(`frontend/src/lib/format.ts`)이
    # `Math.round` 를 쓰므로 여기서 절사하면 같은 값을 두 곳이 달리 말한다.
    # 화면에 "22분"이라 적혀 있는데 글에는 "21분"이라고 쓰이는 식이다
    minutes = round_half_up(seconds / 60)
    if minutes < 60:
        return f"{minutes}분"
    hours, rest = divmod(minutes, 60)
    return f"{hours}시간 {rest}분" if rest else f"{hours}시간"


def _fee(friend_fee: int) -> dict[str, object]:
    """친구비를 방향과 절댓값으로 나눈다. 부호는 넘기지 않는다.

    문구를 화면(`frontend/src/lib/format.ts`)과 같은 말로 맞춘다. 화면은
    "친구에게 친구비를 주세요"라고 쓰는데 글이 "내가 낼 몫"이라고 쓰면 같은
    것을 두 이름으로 부르는 셈이다. 답장 속도를 초가 아니라 분으로 넘긴 것과
    같은 이유다.
    """
    if friend_fee > 0:
        direction = "친구가 나에게 친구비를 주어야 함"
    elif friend_fee < 0:
        direction = "내가 친구에게 친구비를 주어야 함"
    else:
        direction = "서로 비긴 사이"
    return {"방향": direction, "금액(원)": abs(friend_fee)}


def _render_scores(scores: RelationshipScoreData) -> str:
    reply = scores.avg_reply_seconds
    return json.dumps(
        {
            # 부호를 보내면 모델이 부호를 설명한다. 실측 리포트에
            # "친구비가 음수로 나타났지만"이 실렸다. `음수` 는 내부 용어이고
            # 사용자는 화면에서 부호를 본 적이 없다. 절댓값과 방향 문구만
            # 본다. 말로 부탁하는 것보다 **입력에서 없애는 쪽이 확실하다.**
            # `평균답장속도` 를 초에서 분으로 바꾼 것과 같다.
            # AI-프롬프트-명세 5.3.3
            "친구비": _fee(scores.friend_fee),
            "친밀도": scores.intimacy,
            "손절위험도": scores.breakup_risk,
            "먼저연락비율": scores.first_contact_ratio,
            "평균답장속도": {"나": _minutes(reply.me), "상대": _minutes(reply.peer)},
            "연락균형도": scores.contact_balance,
        },
        ensure_ascii=False,
    )


class ReportAgent:
    def __init__(self, provider: LlmProvider) -> None:
        self._provider = provider

    async def run(
        self, analysis: RelationshipAnalysisData, scores: RelationshipScoreData
    ) -> ReportData:
        request = LlmRequest(
            system=REPORT_SYSTEM,
            user=report_user_prompt(
                analysis.model_dump_json(by_alias=True), _render_scores(scores)
            ),
            max_output_tokens=MAX_OUTPUT_TOKENS,
            purpose="report",
        )
        report = await call_and_validate(self._provider, request, ReportData)

        # 고지 문구는 서버가 정한다. 모델이 무엇을 보냈든 덮어쓴다.
        return report.model_copy(update={"disclaimer": DISCLAIMER})
