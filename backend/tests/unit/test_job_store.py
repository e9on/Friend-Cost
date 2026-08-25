"""작업 저장소의 TTL 동작.

기준 명세 5~6장. TTL은 생성 시점 기준 고정형이며 조회로 연장되지 않는다.
"""

import pytest

from app.common.errors import AppError, ErrorCode
from app.domain.value_object.enums import JobStatus
from app.infrastructure.storage.memory import InMemoryJobStore


class FakeClock:
    def __init__(self, now: int = 1_000_000) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    return InMemoryJobStore(ttl_seconds=1_200, clock=clock)


class TestCreateAndGet:
    def test_creates_a_pending_job_with_an_expiry(self, store, clock):
        job = store.create()

        assert job.status is JobStatus.PENDING
        assert job.expires_at == clock.now + 1_200

    def test_job_ids_are_unguessable_uuids(self, store):
        first, second = store.create(), store.create()

        assert first.job_id != second.job_id
        assert len(first.job_id) == 36

    def test_unknown_id_raises_not_found(self, store):
        with pytest.raises(AppError) as caught:
            store.get("존재하지-않는-아이디")

        assert caught.value.code is ErrorCode.JOB_NOT_FOUND


class TestExpiry:
    def test_job_is_gone_after_the_ttl(self, store, clock):
        job = store.create()

        clock.advance(1_201)

        with pytest.raises(AppError) as caught:
            store.get(job.job_id)
        assert caught.value.code is ErrorCode.JOB_EXPIRED

    def test_job_survives_right_up_to_the_ttl(self, store, clock):
        job = store.create()

        clock.advance(1_199)

        assert store.get(job.job_id).job_id == job.job_id

    def test_reading_does_not_extend_the_ttl(self, store, clock):
        job = store.create()
        deadline = job.expires_at

        clock.advance(600)
        store.get(job.job_id)

        assert store.get(job.job_id).expires_at == deadline

    def test_expired_job_is_purged_from_memory(self, store, clock):
        job = store.create()
        clock.advance(1_201)

        with pytest.raises(AppError):
            store.get(job.job_id)

        # 만료를 한 번 확인한 뒤에는 존재 자체가 사라진다
        with pytest.raises(AppError) as caught:
            store.get(job.job_id)
        assert caught.value.code is ErrorCode.JOB_NOT_FOUND


class TestDelete:
    def test_delete_is_idempotent(self, store):
        job = store.create()

        store.delete(job.job_id)
        store.delete(job.job_id)  # 두 번째 호출도 조용히 성공해야 한다

        with pytest.raises(AppError) as caught:
            store.get(job.job_id)
        assert caught.value.code is ErrorCode.JOB_NOT_FOUND

    def test_deleting_an_unknown_id_does_not_raise(self, store):
        store.delete("아무-아이디")


class TestSweep:
    def test_sweep_removes_only_expired_jobs(self, store, clock):
        old = store.create()
        clock.advance(1_100)
        fresh = store.create()
        clock.advance(200)  # old는 만료, fresh는 생존

        removed = store.sweep()

        assert removed == 1
        assert store.get(fresh.job_id).job_id == fresh.job_id
        with pytest.raises(AppError):
            store.get(old.job_id)
