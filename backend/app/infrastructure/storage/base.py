"""임시 저장소 인터페이스.

기준 명세 6장.

배포 전제가 "요청이 없으면 인스턴스가 0으로 내려가는 컨테이너"이므로,
인스턴스가 여러 개 뜨거나 요청 사이에 사라질 수 있다. 그래서 작업 상태를
프로세스 메모리에 두는 구현은 **단일 인스턴스 전용**이며, 확장 시에는
같은 인터페이스의 외부 저장소 구현으로 갈아 끼워야 한다.

여기 정의된 저장소는 모두 TTL 기반 임시 저장소이며 영구 DB가 아니다.
"""

from typing import Protocol, runtime_checkable

from app.domain.model.job import AnalysisJob


@runtime_checkable
class JobStore(Protocol):
    """분석 작업의 상태와 결과를 TTL 동안만 보관한다."""

    def create(self) -> AnalysisJob:
        """새 작업을 만들고 TTL을 건다."""

    def get(self, job_id: str) -> AnalysisJob:
        """작업을 가져온다. 없으면 `JOB_NOT_FOUND`, 만료면 `JOB_EXPIRED`."""

    def save(self, job: AnalysisJob) -> None:
        """변경된 상태를 반영한다."""

    def delete(self, job_id: str) -> None:
        """즉시 삭제한다. 없어도 조용히 성공한다(멱등)."""

    def sweep(self) -> int:
        """만료된 작업을 모두 지우고 지운 개수를 돌려준다."""


@runtime_checkable
class BlobStore(Protocol):
    """업로드 이미지를 TTL 동안만 보관한다.

    파일명은 추측 불가능해야 하고, 공개 경로를 갖지 않아야 한다.
    기준 명세 5장.
    """

    def put(self, job_id: str, index: int, data: bytes) -> str:
        """저장하고 내부 키를 돌려준다."""

    def get(self, key: str) -> bytes:
        ...

    def list_keys(self, job_id: str) -> list[str]:
        ...

    def delete_all(self, job_id: str) -> None:
        """해당 작업의 모든 이미지를 지운다. 멱등."""
