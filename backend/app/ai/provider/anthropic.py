"""Anthropic Claude Provider.

기준 명세 8장: Provider와 모델명은 설정으로 분리하여 교체 가능하게 만든다.

이 파일은 **전송만** 담당한다. 프롬프트는 `app/ai/prompt/`, 응답 검증은
`app/ai/validator/` 소관이므로 모델을 바꿔도 그쪽은 손댈 필요가 없다.

`anthropic` 패키지는 선택 의존성이다. 스텁만 쓰는 배포에서는 설치하지 않아도
되도록 임포트를 함수 안으로 미룬다. 콜드 스타트를 줄이려는 의도이기도 하다.

    pip install -e ".[anthropic]"
"""

import logging
from typing import Any

from app.ai.provider.base import LlmRequest, LlmResponse
from app.common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Claude Messages API를 호출한다."""

    name = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        effort: str = "low",
        timeout_seconds: float = 45.0,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self._timeout = timeout_seconds
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - 설치 여부에 달린 경로
            raise AppError(ErrorCode.LLM_FAILED) from exc

        kwargs: dict[str, Any] = {"timeout": self._timeout, "max_retries": 2}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def complete(self, request: LlmRequest) -> LlmResponse:
        client = self._get_client()

        try:
            message = await client.messages.create(
                model=self.model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_config={"effort": self.effort},
            )
        except AppError:
            raise
        except Exception as exc:
            # 대화 원문이 로그에 실리지 않도록 목적과 예외 종류만 남긴다
            logger.warning(
                "anthropic 호출 실패 purpose=%s model=%s error=%s",
                request.purpose,
                self.model,
                type(exc).__name__,
            )
            raise AppError(ErrorCode.LLM_FAILED) from exc

        if getattr(message, "stop_reason", None) == "refusal":
            # 안전 분류기가 거절한 경우다. 재시도해도 같은 결과가 나온다
            logger.warning("anthropic 거절 purpose=%s", request.purpose)
            raise AppError(ErrorCode.LLM_FAILED)

        text = _extract_text(message)
        usage = getattr(message, "usage", None)
        return LlmResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )


def _extract_text(message: Any) -> str:
    """응답에서 텍스트 블록만 이어 붙인다.

    thinking 블록이 함께 올 수 있으므로 타입을 확인하고 골라내야 한다.
    """
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()
