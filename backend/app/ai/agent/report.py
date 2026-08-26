"""Report Agent.

기준 명세 7장. 계산된 점수를 사람이 읽을 글로 옮긴다. LLM 호출 1회.

대화 원문을 입력으로 받지 않는다. 입력 토큰을 줄이기 위한 의도적 제약이며,
동시에 원문이 한 번 더 외부로 나가는 경로를 없애는 효과도 있다.
"""

import json

from app.ai.agent.base import call_and_validate
from app.ai.prompt.templates import REPORT_SYSTEM, report_user_prompt
from app.ai.provider.base import LlmProvider, LlmRequest
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.report import DISCLAIMER, ReportData
from app.domain.model.score import RelationshipScoreData

MAX_OUTPUT_TOKENS = 700


def _render_scores(scores: RelationshipScoreData) -> str:
    reply = scores.avg_reply_seconds
    return json.dumps(
        {
            "친구비(원)": scores.friend_fee,
            "친밀도": scores.intimacy,
            "손절위험도": scores.breakup_risk,
            "먼저연락비율": scores.first_contact_ratio,
            "평균답장속도초": {"나": reply.me, "상대": reply.peer},
            "연락균형도": scores.contact_balance,
            # 관계의 신뢰도가 아니라 **이 분석을 얼마나 믿을 수 있는지**다.
            # "신뢰도"로 적어 보냈더니 모델이 관계의 신뢰로 읽고
            # "신뢰도는 high로 평가됩니다"라고 썼다. 사용자는 그것을
            # "이 관계는 믿을 만하다"로 읽는다. AI-프롬프트-명세 5.2
            "분석신뢰도": scores.confidence.value,
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
