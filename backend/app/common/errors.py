"""오류 코드와 애플리케이션 예외.

코드, HTTP 상태, 재시도 가능 여부는 데이터 계약 명세서 11장 표를 그대로 옮긴 것이다.
표를 고칠 때는 문서와 이 파일을 함께 고친다.
"""

from enum import Enum
from typing import NamedTuple


class _Spec(NamedTuple):
    http_status: int
    retryable: bool
    message: str


class ErrorCode(str, Enum):
    IMAGE_TOO_MANY = "IMAGE_TOO_MANY"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    IMAGE_FORMAT_UNSUPPORTED = "IMAGE_FORMAT_UNSUPPORTED"
    OCR_FAILED = "OCR_FAILED"
    NO_CONVERSATION_FOUND = "NO_CONVERSATION_FOUND"
    TOO_FEW_MESSAGES = "TOO_FEW_MESSAGES"
    GROUP_CHAT_DETECTED = "GROUP_CHAT_DETECTED"
    SPEAKER_DETECTION_FAILED = "SPEAKER_DETECTION_FAILED"
    LLM_FAILED = "LLM_FAILED"
    LLM_SCHEMA_INVALID = "LLM_SCHEMA_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_EXPIRED = "JOB_EXPIRED"
    JOB_NOT_READY = "JOB_NOT_READY"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ANALYSIS_TIMEOUT = "ANALYSIS_TIMEOUT"


_SPECS: dict[ErrorCode, _Spec] = {
    ErrorCode.IMAGE_TOO_MANY: _Spec(400, False, "이미지 개수가 허용 범위를 벗어났습니다."),
    ErrorCode.IMAGE_TOO_LARGE: _Spec(400, False, "이미지 용량이 너무 큽니다."),
    ErrorCode.IMAGE_FORMAT_UNSUPPORTED: _Spec(400, False, "지원하지 않는 이미지 형식입니다."),
    ErrorCode.OCR_FAILED: _Spec(422, True, "이미지에서 글자를 읽지 못했습니다."),
    ErrorCode.NO_CONVERSATION_FOUND: _Spec(422, False, "대화로 인식되는 내용이 없습니다."),
    ErrorCode.TOO_FEW_MESSAGES: _Spec(422, False, "분석하기에 대화가 너무 짧습니다."),
    ErrorCode.GROUP_CHAT_DETECTED: _Spec(422, False, "단체 대화방은 분석할 수 없습니다."),
    ErrorCode.SPEAKER_DETECTION_FAILED: _Spec(422, False, "누가 보낸 메시지인지 구분하지 못했습니다."),
    ErrorCode.LLM_FAILED: _Spec(502, True, "분석 엔진 호출에 실패했습니다."),
    ErrorCode.LLM_SCHEMA_INVALID: _Spec(502, True, "분석 결과 형식이 올바르지 않습니다."),
    ErrorCode.RATE_LIMITED: _Spec(429, True, "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."),
    ErrorCode.DAILY_LIMIT_EXCEEDED: _Spec(429, False, "오늘 분석 가능한 횟수를 모두 사용했습니다."),
    ErrorCode.CONCURRENCY_LIMIT: _Spec(429, True, "동시에 처리할 수 있는 분석 수를 넘었습니다."),
    ErrorCode.JOB_NOT_FOUND: _Spec(404, False, "존재하지 않는 분석입니다."),
    ErrorCode.JOB_EXPIRED: _Spec(410, False, "분석 결과가 만료되었습니다. 다시 분석해 주세요."),
    ErrorCode.JOB_NOT_READY: _Spec(409, True, "아직 분석이 끝나지 않았습니다."),
    ErrorCode.INTERNAL_ERROR: _Spec(500, True, "일시적인 오류가 발생했습니다."),
    ErrorCode.ANALYSIS_TIMEOUT: _Spec(504, True, "분석 시간이 초과되었습니다."),
}


def http_status_of(code: ErrorCode) -> int:
    return _SPECS[code].http_status


def is_retryable(code: ErrorCode) -> bool:
    return _SPECS[code].retryable


def default_message_of(code: ErrorCode) -> str:
    return _SPECS[code].message


class AppError(Exception):
    """서비스가 사용자에게 노출하는 오류.

    메시지에 대화 원문, 파일명, 좌표를 넣지 않는다.
    기준 명세 5장의 원문 보호 원칙에 따른 제약이므로, 상세 정보를 붙이고 싶을 때는
    ``detail`` 대신 집계값만 쓴다.
    """

    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        self.code = code
        self.message = message or default_message_of(code)
        super().__init__(f"{code.value}: {self.message}")

    @property
    def http_status(self) -> int:
        return http_status_of(self.code)

    @property
    def retryable(self) -> bool:
        return is_retryable(self.code)
