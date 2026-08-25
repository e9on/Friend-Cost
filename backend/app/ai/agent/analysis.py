"""Analysis Agent.

기준 명세 7장. 관계 의미를 구조화된 데이터로 뽑는다. LLM 호출 1회.

연락 패턴과 답장 패턴은 여기서 다루지 않는다. 코드로 계산 가능하므로
`app.algorithm` 이 맡는다.
"""

from app.ai.agent.base import call_and_validate
from app.ai.prompt.templates import ANALYSIS_SYSTEM, analysis_user_prompt
from app.ai.provider.base import LlmProvider, LlmRequest
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.conversation import ConversationData
from app.domain.value_object.enums import Speaker

MAX_OUTPUT_TOKENS = 800


def render_conversation(convo: ConversationData) -> str:
    """대화를 프롬프트에 넣을 형태로 압축한다.

    절대 시각 대신 직전 메시지로부터의 경과 초를 쓴다. 절대 날짜는 분석에
    쓸모가 없고 토큰만 먹는다.
    """
    lines: list[str] = []
    previous: int | None = None

    for message in convo.messages:
        who = "나" if message.speaker is Speaker.ME else "상대"
        if message.sent_at is None:
            gap = "?"
        elif previous is None:
            gap = "0"
        else:
            gap = str(message.sent_at - previous)
        if message.sent_at is not None:
            previous = message.sent_at
        lines.append(f"{who}|+{gap}s|{message.text}")

    return "\n".join(lines)


class AnalysisAgent:
    def __init__(self, provider: LlmProvider) -> None:
        self._provider = provider

    async def run(self, convo: ConversationData) -> RelationshipAnalysisData:
        request = LlmRequest(
            system=ANALYSIS_SYSTEM,
            user=analysis_user_prompt(render_conversation(convo)),
            max_output_tokens=MAX_OUTPUT_TOKENS,
            purpose="analysis",
        )
        return await call_and_validate(self._provider, request, RelationshipAnalysisData)
