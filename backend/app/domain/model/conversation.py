"""OCR 산출물과 정규화된 대화 데이터.

데이터 계약 명세서 4~6장.

필드는 파이썬 관례에 따라 snake_case로 두고, 직렬화할 때만 camelCase로 바꾼다.
문서에 적힌 이름이 곧 JSON 이름이 되도록 별칭 생성기를 쓴다.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.domain.value_object.enums import Speaker, TimeSource


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class BoundingBox(_Base):
    """이미지 좌상단(0,0) 기준 픽셀 좌표."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2


class OcrBlock(_Base):
    """OCR이 인식한 텍스트 한 덩어리.

    `imageIndex`를 두지 않는다. 소속 이미지는 ``OcrPage`` 가 안다.
    """

    text: str
    box: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)


class OcrPage(_Base):
    """이미지 한 장의 OCR 결과.

    ``width`` 는 화자 판별의 기준값이므로 필수다.
    """

    image_index: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    blocks: tuple[OcrBlock, ...] = ()


class Message(_Base):
    """정규화된 개별 메시지."""

    index: int = Field(ge=0)
    speaker: Speaker
    text: str
    sent_at: int | None = None
    time_source: TimeSource = TimeSource.UNKNOWN
    image_index: int = Field(ge=0)


class ConversationMeta(_Base):
    image_count: int = Field(ge=0)
    message_count: int = Field(ge=0)
    dropped_count: int = Field(ge=0)
    sampled: bool = False
    time_coverage: float = Field(ge=0.0, le=1.0)
    span_seconds: int | None = None


class ConversationData(_Base):
    """Parser의 최종 산출물이자 Analysis Agent의 유일한 입력."""

    messages: tuple[Message, ...]
    meta: ConversationMeta

    def by_speaker(self, speaker: Speaker) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.speaker is speaker)

    def timed_messages(self) -> tuple[Message, ...]:
        """`sent_at` 이 복원된 메시지만 시간순으로 돌려준다.

        세션 분할과 답장 간격 수집은 시각이 있는 메시지만 사용한다.
        """
        return tuple(m for m in self.messages if m.sent_at is not None)
