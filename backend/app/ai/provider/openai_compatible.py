"""OpenAI 호환 API를 쓰는 Provider.

Groq, DeepSeek, Together, OpenRouter, 로컬 vLLM 등이 모두 같은 스펙을 따르므로
구현 하나로 여러 후보를 덮는다. 후보를 바꿀 때 코드가 아니라 설정만 바뀐다.

`AI-모델-선정-보고서.md` 5장의 후보 중 Groq이 1순위다. 무료 티어에서도 입력을
학습에 쓰지 않는다고 명시하는 사실상 유일한 곳이기 때문이다.

의존성을 추가하지 않으려고 `httpx` 로 직접 호출한다. httpx는 테스트에 이미
쓰고 있어 새로 들여오는 것이 없다.
"""

import logging
from typing import Any

import httpx

from app.ai.provider.base import LlmRequest, LlmResponse
from app.common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# 후보별 기본 주소. 설정으로 덮어쓸 수 있다
KNOWN_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class OpenAiCompatibleProvider:
    """`/chat/completions` 를 호출한다."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 45.0,
        temperature: float = 0.0,
    ) -> None:
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = (base_url or KNOWN_BASE_URLS.get(name, "")).rstrip("/")
        if not self._base_url:
            raise ValueError(f"{name} 의 base_url을 알 수 없다. 설정으로 지정해야 한다")
        self._timeout = timeout_seconds
        # 점수 산식의 재현성을 위해 기본값을 0으로 둔다
        self._temperature = temperature

    async def complete(self, request: LlmRequest) -> LlmResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            # 프롬프트로도 JSON을 요구하지만, 지원하는 곳에서는 한 겹 더 강제한다
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except Exception as exc:
            # 대화 원문이 로그에 실리지 않도록 목적과 예외 종류만 남긴다
            logger.warning(
                "%s 호출 실패 purpose=%s error=%s",
                self.name,
                request.purpose,
                type(exc).__name__,
            )
            raise AppError(ErrorCode.LLM_FAILED) from exc

        if response.status_code == 429:
            logger.warning("%s 요청 한도 초과 purpose=%s", self.name, request.purpose)
            raise AppError(ErrorCode.LLM_FAILED)
        if response.status_code >= 400:
            logger.warning(
                "%s 오류 응답 purpose=%s status=%d",
                self.name,
                request.purpose,
                response.status_code,
            )
            raise AppError(ErrorCode.LLM_FAILED)

        return _to_response(response.json())


def _to_response(body: dict[str, Any]) -> LlmResponse:
    choices = body.get("choices") or []
    if not choices:
        raise AppError(ErrorCode.LLM_FAILED)

    text = (choices[0].get("message") or {}).get("content") or ""
    usage = body.get("usage") or {}
    return LlmResponse(
        text=text.strip(),
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )
