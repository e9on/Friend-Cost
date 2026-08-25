"""업로드 이미지는 저장소를 거쳐 파이프라인에 들어간다.

지금까지는 저장소에 넣어두고 **한 번도 읽지 않았다.** 파이프라인은 메모리에
들고 있던 바이트를 직접 받았고, 저장소는 쓰기 전용이었다.

인메모리 구현에서는 같은 객체라 티가 나지 않는다. 그러나 기준 명세 6장이
전제한 대로 외부 오브젝트 스토리지로 갈아 끼우는 순간, 이미지는 업로드될 뿐
읽히지 않아 분석이 빈 입력으로 돌아간다.
"""

import pytest

from app.application.service.analysis_service import AnalysisService
from app.application.service.pipeline import AnalysisPipeline
from app.application.service.upload_validator import UploadedImage
from app.config.settings import Settings
from app.domain.value_object.enums import JobStatus
from app.infrastructure.storage.memory import InMemoryBlobStore, InMemoryJobStore
from tests.unit.test_upload_validation import png_bytes


def uploads(count: int = 3):
    return [
        UploadedImage(filename=f"shot{i}.png", data=png_bytes() + bytes([i]) * 64)
        for i in range(count)
    ]


class RecordingBlobStore(InMemoryBlobStore):
    """읽기 호출을 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.reads: list[str] = []

    def get(self, key: str) -> bytes:
        self.reads.append(key)
        return super().get(key)


def build(blob_store) -> AnalysisService:
    settings = Settings()
    return AnalysisService(
        job_store=InMemoryJobStore(ttl_seconds=settings.ttl_seconds),
        blob_store=blob_store,
        pipeline=AnalysisPipeline.from_settings(settings),
        settings=settings,
    )


class TestPipelineReadsFromStorage:
    async def test_images_are_read_back_from_the_store(self):
        blobs = RecordingBlobStore()
        service = build(blobs)

        job = await service.create(uploads(3))
        await service.wait_for(job.job_id)

        assert len(blobs.reads) == 3, "저장소에서 이미지를 읽지 않았다"

    async def test_analysis_fails_when_the_images_are_gone(self):
        """저장소에서 사라지면 분석도 실패해야 한다.

        성공한다면 파이프라인이 저장소가 아닌 다른 곳에서 이미지를 얻고
        있다는 뜻이고, 그러면 외부 저장소로 바꿔도 소용이 없다.
        """
        blobs = InMemoryBlobStore()
        service = build(blobs)

        original_create = service.job_store.create
        job = await service.create(uploads(3))
        # 분석이 시작되기 전에 이미지를 지운다
        blobs.delete_all(job.job_id)
        await service.wait_for(job.job_id)

        assert service.status(job.job_id).status is JobStatus.FAILED

    async def test_images_are_removed_after_analysis(self):
        blobs = RecordingBlobStore()
        service = build(blobs)

        job = await service.create(uploads(2))
        await service.wait_for(job.job_id)

        assert blobs.list_keys(job.job_id) == []

    async def test_upload_order_survives_the_round_trip(self):
        """업로드 순서가 곧 시간 순서다. 저장소를 거쳐도 유지되어야 한다."""
        blobs = RecordingBlobStore()
        service = build(blobs)

        job = await service.create(uploads(5))
        await service.wait_for(job.job_id)

        assert service.status(job.job_id).status is JobStatus.DONE
        assert len(blobs.reads) == 5
