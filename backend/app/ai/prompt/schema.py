"""응답 스키마를 프롬프트에 넣을 형태로 그린다.

**손으로 적지 않는 이유.** 프롬프트에 필드 이름을 직접 써두면 모델을 고칠 때
한쪽만 바뀐다. 그러면 모델은 규격에 맞는 JSON을 내놓는데 우리가 요구한 것과
달라서, 매번 재시도하고 결국 실패한다. 원인이 프롬프트에 있으므로 코드를
읽어서는 찾기 어렵다. 그래서 `model_fields` 에서 직접 만든다.

JSON Schema 를 그대로 붙이지 않는 이유는 토큰이다. 정식 스키마는 같은 내용을
서너 배 길이로 적는다. 여기서는 모델이 형태를 흉내 낼 수 있을 만큼만 그린다.
"""

from types import UnionType
from typing import Any, Union, get_args, get_origin

from annotated_types import Ge, Le, MaxLen
from pydantic import BaseModel
from pydantic.fields import FieldInfo

INDENT = "  "


def _bounds(field: FieldInfo) -> tuple[int | None, int | None, int | None]:
    """Field(ge=, le=, max_length=) 로 붙은 제약을 꺼낸다."""
    low = high = length = None
    for item in field.metadata:
        if isinstance(item, Ge):
            low = item.ge
        elif isinstance(item, Le):
            high = item.le
        elif isinstance(item, MaxLen):
            length = item.max_length
    return low, high, length


def _unwrap(annotation: Any) -> Any:
    """Optional[X] 같은 합집합에서 실제 타입을 꺼낸다."""
    if get_origin(annotation) in (Union, UnionType):
        for arg in get_args(annotation):
            if arg is not type(None):
                return arg
    return annotation


def _describe(annotation: Any, field: FieldInfo, depth: int) -> str:
    annotation = _unwrap(annotation)
    low, high, length = _bounds(field)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _render(annotation, depth)

    origin = get_origin(annotation)
    if origin in (tuple, list):
        args = [a for a in get_args(annotation) if a is not Ellipsis]
        inner = args[0] if args else str
        limit = f" (최대 {length}개)" if length else ""
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return f"[{_render(inner, depth + 1)}]{limit}"
        return f'["문자열"]{limit}'

    if annotation is int:
        if low is not None and high is not None:
            return f"{low}에서 {high} 사이 정수"
        if low is not None:
            return f"{low} 이상 정수"
        return "정수"

    if annotation is str:
        return f'"문자열 (최대 {length}자)"' if length else '"문자열"'

    return '"값"'


def _render(model: type[BaseModel], depth: int, skip: frozenset[str] = frozenset()) -> str:
    pad = INDENT * (depth + 1)
    close = INDENT * depth
    lines = []
    for name, field in model.model_fields.items():
        key = field.alias or name
        if key in skip or name in skip:
            continue
        lines.append(f'{pad}"{key}": {_describe(field.annotation, field, depth + 1)}')
    return "{\n" + ",\n".join(lines) + f"\n{close}}}"


def render_schema(model: type[BaseModel], *, skip: frozenset[str] = frozenset()) -> str:
    """모델을 프롬프트에 넣을 스키마 문안으로 만든다.

    `skip` 에 넣은 필드는 그리지 않는다. 서버가 채우는 값을 모델에게 요구하면
    모델이 제 문구를 써넣는다.
    """
    return _render(model, depth=0, skip=skip)
