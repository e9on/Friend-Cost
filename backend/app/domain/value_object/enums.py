"""데이터 계약 명세서가 정의한 열거값.

Python 3.10을 대상으로 하므로 3.11에서 추가된 ``enum.StrEnum`` 대신
``str`` 을 함께 상속한다. JSON 직렬화 결과는 동일하다.
"""

from enum import Enum


class Speaker(str, Enum):
    """메시지 화자. 데이터 계약 5장."""

    ME = "me"
    PEER = "peer"


class TimeSource(str, Enum):
    """`sentAt` 을 어떻게 얻었는지. 데이터 계약 5장."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    """결과 신뢰도. 데이터 계약 8장."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def downgrade(self) -> "Confidence":
        """한 단계 강등한다. ``LOW`` 에서는 더 내려가지 않는다.

        관계 점수 계산 규칙 11장의 강등 규칙.
        """
        if self is Confidence.HIGH:
            return Confidence.MEDIUM
        if self is Confidence.MEDIUM:
            return Confidence.LOW
        return Confidence.LOW


class JobStatus(str, Enum):
    """작업 상태. 데이터 계약 10장."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.FAILED, JobStatus.EXPIRED)


class JobStage(str, Enum):
    """`status` 가 ``processing`` 일 때의 세부 단계. 데이터 계약 10장."""

    OCR = "ocr"
    PARSING = "parsing"
    ANALYZING = "analyzing"
    SCORING = "scoring"
    REPORTING = "reporting"
