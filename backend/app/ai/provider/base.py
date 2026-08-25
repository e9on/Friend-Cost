"""LLM Provider 인터페이스.

기준 명세 8장: Provider와 모델명은 설정으로 분리하여 교체 가능하게 만든다.

Provider는 **순수 전송 담당**이다. 프롬프트를 만들지도, 응답을 해석하지도 않는다.
그 일은 `app.ai.agent` 와 `app.ai.validator` 가 한다. 이렇게 나눠두면 실제 모델을
붙일 때 이 파일 아래에 구현 하나를 추가하는 것으로 끝난다.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    max_output_tokens: int
    purpose: str  # 로그와 지표 분류용. 대화 내용은 담지 않는다


@dataclass(frozen=True)
class LlmResponse:
    text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class LlmProvider(Protocol):
    """모델 호출 한 번을 담당한다."""

    name: str

    async def complete(self, request: LlmRequest) -> LlmResponse:
        ...
