"""Agent 공통 규약.

기준 명세 7장.

Agent는 프롬프트를 소유하고, Provider는 전송만 한다. 응답 검증에 실패하면
**1회에 한해** 재시도한다. 이는 "LLM 호출 1회" 원칙의 명시적 예외다.
"""

import logging
from typing import TypeVar

from pydantic import BaseModel

from app.ai.provider.base import LlmProvider, LlmRequest
from app.ai.validator.schema import SchemaMismatch, parse_json_response
from app.common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 최초 1회 + 스키마 실패 시 재시도 1회

T = TypeVar("T", bound=BaseModel)


async def call_and_validate(
    provider: LlmProvider,
    request: LlmRequest,
    model: type[T],
) -> T:
    """모델을 호출하고 응답을 검증한다.

    로그에는 대화 원문이 남지 않도록 목적과 시도 횟수만 기록한다.
    """
    last_error: SchemaMismatch | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await provider.complete(request)
        except AppError:
            raise
        except Exception as exc:  # 전송 계층 실패는 모두 LLM_FAILED로 접는다
            logger.warning("llm 호출 실패 purpose=%s attempt=%d", request.purpose, attempt)
            raise AppError(ErrorCode.LLM_FAILED) from exc

        try:
            return parse_json_response(response.text, model)
        except SchemaMismatch as exc:
            last_error = exc
            logger.warning(
                "llm 응답 스키마 불일치 purpose=%s attempt=%d/%d",
                request.purpose,
                attempt,
                MAX_ATTEMPTS,
            )

    raise AppError(ErrorCode.LLM_SCHEMA_INVALID) from last_error
