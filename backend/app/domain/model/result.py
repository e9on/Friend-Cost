"""결과 조회 응답 본문.

데이터 계약 명세서 12장.

`RelationshipAnalysisData` 와 `ConversationData.messages` 는 여기에 담기지 않는다.
대화 원문이 클라이언트로 되돌아가지 않게 하기 위한 제약이다.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.model.conversation import ConversationMeta
from app.domain.model.report import ReportData
from app.domain.model.score import RelationshipScoreData


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class ResultMeta(_Base):
    """`ConversationMeta` 의 부분집합.

    `droppedCount` 와 `timeCoverage` 는 내부 지표라 노출하지 않는다.
    """

    message_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    sampled: bool = False
    span_seconds: int | None = None

    @classmethod
    def of(cls, meta: ConversationMeta) -> "ResultMeta":
        return cls(
            message_count=meta.message_count,
            image_count=meta.image_count,
            sampled=meta.sampled,
            span_seconds=meta.span_seconds,
        )


class AnalysisResult(_Base):
    job_id: str
    scores: RelationshipScoreData
    report: ReportData
    meta: ResultMeta
    expires_at: int
