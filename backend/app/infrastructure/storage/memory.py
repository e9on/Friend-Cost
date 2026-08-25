"""프로세스 메모리를 쓰는 임시 저장소.

**단일 인스턴스 전용이다.** 기준 명세 6장이 못 박은 대로, 인스턴스를 둘 이상으로
늘리는 순간 이 구현은 깨진다. 확장할 때는 같은 인터페이스의 외부 저장소 구현으로
갈아 끼운다.

로컬 개발과 테스트에서는 이 구현이 가장 단순하고 빠르다.
"""

import threading
import time
import uuid
from typing import Callable

from app.common.errors import AppError, ErrorCode
from app.domain.model.job import AnalysisJob

Clock = Callable[[], int]


def _system_clock() -> int:
    return int(time.time())


class InMemoryJobStore:
    def __init__(self, ttl_seconds: int, clock: Clock = _system_clock) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = threading.Lock()

    def create(self) -> AnalysisJob:
        now = self._clock()
        job = AnalysisJob(
            job_id=str(uuid.uuid4()),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> AnalysisJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError(ErrorCode.JOB_NOT_FOUND)
            if job.is_expired_at(self._clock()):
                # 만료를 확인한 김에 실제로 지운다. TTL은 삭제 보장 장치다
                del self._jobs[job_id]
                raise AppError(ErrorCode.JOB_EXPIRED)
            return job

    def save(self, job: AnalysisJob) -> None:
        with self._lock:
            if job.job_id in self._jobs:
                self._jobs[job.job_id] = job

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def sweep(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [key for key, job in self._jobs.items() if job.is_expired_at(now)]
            for key in expired:
                del self._jobs[key]
        return len(expired)


class InMemoryBlobStore:
    """업로드 이미지를 메모리에 둔다.

    키에 파일명이나 순번 이외의 정보를 넣지 않는다. 원본 파일명은 저장하지 않는다.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._by_job: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def put(self, job_id: str, index: int, data: bytes) -> str:
        key = f"{job_id}/{index}/{uuid.uuid4().hex}"
        with self._lock:
            self._blobs[key] = data
            self._by_job.setdefault(job_id, []).append(key)
        return key

    def get(self, key: str) -> bytes:
        with self._lock:
            blob = self._blobs.get(key)
        if blob is None:
            raise AppError(ErrorCode.JOB_EXPIRED)
        return blob

    def list_keys(self, job_id: str) -> list[str]:
        with self._lock:
            return list(self._by_job.get(job_id, ()))

    def delete_all(self, job_id: str) -> None:
        with self._lock:
            for key in self._by_job.pop(job_id, ()):
                self._blobs.pop(key, None)
