"""HTTP 응답 본문.

API 명세 4~7장. 도메인 모델과 같은 camelCase 규약을 쓴다.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.common.errors import AppError
from app.domain.model.job import AnalysisJob
from app.domain.value_object.enums import JobStage, JobStatus


class _Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorBody(_Base):
    code: str
    message: str
    retryable: bool

    @classmethod
    def of(cls, error: AppError) -> "ErrorBody":
        return cls(code=error.code.value, message=error.message, retryable=error.retryable)


class ErrorResponse(_Base):
    error: ErrorBody


class CreateResponse(_Base):
    job_id: str
    status: JobStatus
    expires_at: int
    poll_after_seconds: int


class StatusResponse(_Base):
    job_id: str
    status: JobStatus
    stage: JobStage | None = None
    expires_at: int
    poll_after_seconds: int | None = None
    error: ErrorBody | None = None

    @classmethod
    def of(cls, job: AnalysisJob, poll_after_seconds: int) -> "StatusResponse":
        return cls(
            job_id=job.job_id,
            status=job.status,
            stage=job.stage,
            expires_at=job.expires_at,
            poll_after_seconds=(
                poll_after_seconds if not job.status.is_terminal else None
            ),
            error=ErrorBody.of(job.error) if job.error else None,
        )


class HealthResponse(_Base):
    status: str
    llm_provider: str
    ocr_engine: str
    ttl_seconds: int
