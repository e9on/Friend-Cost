"""분석 작업의 상태.

데이터 계약 명세서 10장.

작업은 상태가 바뀌므로 다른 도메인 모델과 달리 불변이 아니다.
상태 전이는 ``advance`` / ``succeed`` / ``fail`` 만 통과하도록 해서
임의의 전이가 생기지 않게 한다.
"""

from dataclasses import dataclass, field

from app.common.errors import AppError, ErrorCode
from app.domain.model.result import AnalysisResult
from app.domain.value_object.enums import JobStage, JobStatus

_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.PROCESSING, JobStatus.FAILED, JobStatus.EXPIRED}),
    JobStatus.PROCESSING: frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.EXPIRED}),
    JobStatus.DONE: frozenset({JobStatus.EXPIRED}),
    JobStatus.FAILED: frozenset({JobStatus.EXPIRED}),
    JobStatus.EXPIRED: frozenset(),
}


class IllegalTransition(RuntimeError):
    """정의되지 않은 상태 전이. 사용자에게 노출되는 오류가 아니라 구현 결함이다."""


@dataclass
class AnalysisJob:
    job_id: str
    created_at: int
    expires_at: int
    status: JobStatus = JobStatus.PENDING
    stage: JobStage | None = None
    error: AppError | None = field(default=None, repr=False)
    result: AnalysisResult | None = field(default=None, repr=False)

    def _transition(self, to: JobStatus) -> None:
        if to not in _ALLOWED[self.status]:
            raise IllegalTransition(f"{self.status.value} -> {to.value}")
        self.status = to

    def advance(self, stage: JobStage) -> None:
        """처리 단계를 진행한다. 아직 ``pending`` 이면 ``processing`` 으로 올린다."""
        if self.status is JobStatus.PENDING:
            self._transition(JobStatus.PROCESSING)
        elif self.status is not JobStatus.PROCESSING:
            raise IllegalTransition(f"{self.status.value} 상태에서는 단계를 진행할 수 없다")
        self.stage = stage

    def succeed(self, result: AnalysisResult) -> None:
        self._transition(JobStatus.DONE)
        self.stage = None
        self.result = result

    def fail(self, error: AppError) -> None:
        self._transition(JobStatus.FAILED)
        self.stage = None
        self.error = error

    def expire(self) -> None:
        self._transition(JobStatus.EXPIRED)
        self.stage = None
        self.result = None
        self.error = None

    def is_expired_at(self, now: int) -> bool:
        return now >= self.expires_at

    def raise_if_unavailable(self) -> None:
        """결과 조회가 불가능한 상태면 해당 오류를 던진다."""
        if self.status is JobStatus.EXPIRED:
            raise AppError(ErrorCode.JOB_EXPIRED)
        if self.status is JobStatus.FAILED:
            raise self.error or AppError(ErrorCode.INTERNAL_ERROR)
        if self.status is not JobStatus.DONE:
            raise AppError(ErrorCode.JOB_NOT_READY)
