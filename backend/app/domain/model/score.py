"""Relationship Algorithm(코드)의 출력.

데이터 계약 명세서 8장. 산식은 ``app/algorithm`` 이 담당하며, 여기서는 구조와 단위만 정의한다.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.value_object.enums import Confidence

FEE_MIN = -100_000
FEE_MAX = 100_000


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class ReplySeconds(_Base):
    """화자별 평균 답장 속도(초).

    표본이 3개 미만이면 ``None`` 이다. 0이 아니라 ``None`` 인 이유는
    "즉시 답장"과 "알 수 없음"을 구분해야 하기 때문이다.
    """

    me: int | None = Field(default=None, ge=0)
    peer: int | None = Field(default=None, ge=0)


class RelationshipScoreData(_Base):
    friend_fee: int = Field(ge=FEE_MIN, le=FEE_MAX)
    intimacy: int = Field(ge=0, le=100)
    breakup_risk: int = Field(ge=0, le=100)
    first_contact_ratio: float = Field(ge=0.0, le=1.0)
    avg_reply_seconds: ReplySeconds
    contact_balance: int = Field(ge=0, le=100)
    confidence: Confidence
