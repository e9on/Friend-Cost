"""LLM 응답을 도메인 모델로 검증한다.

기준 명세 7장의 Validator 단계.

범위를 벗어난 값은 clamp 후 통과시키고, 구조 자체가 어긋나면 실패로 본다.
0~100 점수가 480으로 왔다면 의도는 명확하니 잘라 쓰는 편이 낫지만,
필드가 통째로 없다면 다시 물어보는 편이 낫기 때문이다.
"""

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

T = TypeVar("T", bound=BaseModel)


class SchemaMismatch(ValueError):
    """응답이 스키마에 맞지 않는다. 호출한 쪽에서 재시도를 결정한다."""


def _strip_fence(text: str) -> str:
    """모델이 코드펜스를 붙여 보내는 경우를 걷어낸다."""
    return _FENCE.sub("", text).strip()


def _clamp_numbers(value: Any, low: int = 0, high: int = 100) -> Any:
    """0~100으로 정의된 자리에 들어온 숫자를 범위 안으로 밀어 넣는다.

    개수 필드는 상한이 없으므로 음수만 올린다.
    """
    if isinstance(value, dict):
        return {key: _clamp_numbers(item, low, high) for key, item in value.items()}
    if isinstance(value, list):
        return [_clamp_numbers(item, low, high) for item in value]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return max(low, min(high, value))


_UNBOUNDED_KEYS = frozenset({"promiseSignals", "moneySignals", "promise_signals", "money_signals"})


def parse_json_response(text: str, model: type[T], *, clamp: bool = True) -> T:
    """응답 문자열을 모델로 만든다. 실패하면 `SchemaMismatch` 를 던진다."""
    try:
        payload = json.loads(_strip_fence(text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise SchemaMismatch("JSON으로 읽을 수 없다") from exc

    if not isinstance(payload, dict):
        raise SchemaMismatch("최상위가 객체가 아니다")

    if clamp:
        payload = {
            key: value
            if key in _UNBOUNDED_KEYS
            else _clamp_numbers(value)
            for key, value in payload.items()
        }
        for key in _UNBOUNDED_KEYS & payload.keys():
            payload[key] = _clamp_numbers(payload[key], 0, 10**6)

    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise SchemaMismatch("스키마에 맞지 않는다") from exc
