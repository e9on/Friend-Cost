"""Report Agent(LLM 1회)의 출력.

데이터 계약 명세서 9장.

글자 수 상한은 출력 토큰 비용을 통제하기 위한 규격이며 권고가 아니라 제약이다.
따라서 검증에서 실제로 강제한다.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

DISCLAIMER = "이 결과는 재미를 위한 추정이며 실제 관계를 판단하는 근거가 아닙니다."


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class ReportSection(_Base):
    title: str = Field(min_length=1, max_length=20)
    body: str = Field(min_length=1, max_length=300)


class ReportData(_Base):
    headline: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=200)
    sections: tuple[ReportSection, ...] = Field(min_length=2, max_length=3)
    advice: str = Field(min_length=1, max_length=150)
    disclaimer: str = DISCLAIMER
