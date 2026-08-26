"""분석 파이프라인과 이를 감싸는 서비스.

기준 명세 4장(비동기 흐름), 7장(파이프라인), 5장(데이터 최소화).
"""

import asyncio

import pytest

from app.application.service.analysis_service import AnalysisService
from app.application.service.pipeline import AnalysisPipeline
from app.application.service.upload_validator import UploadedImage
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings
from app.domain.model.result import AnalysisResult
from app.domain.value_object.enums import JobStatus
from app.infrastructure.ocr.stub import StubOcrEngine
from app.infrastructure.storage.memory import InMemoryBlobStore, InMemoryJobStore
from tests.unit.test_upload_validation import png_bytes


def build_service(**overrides) -> AnalysisService:
    settings = Settings(**overrides)
    return AnalysisService(
        job_store=InMemoryJobStore(ttl_seconds=settings.ttl_seconds),
        blob_store=InMemoryBlobStore(),
        pipeline=AnalysisPipeline.from_settings(settings),
        settings=settings,
    )


def uploads(count: int = 3) -> list[UploadedImage]:
    # 이미지마다 다른 바이트를 줘야 스텁 OCR이 다른 대화를 만든다
    return [
        UploadedImage(filename=f"shot{i}.png", data=png_bytes() + bytes([i]) * 64)
        for i in range(count)
    ]


async def run_to_completion(service: AnalysisService, images) -> str:
    job = await service.create(images)
    await service.wait_for(job.job_id)
    return job.job_id


class TestPipelineEndToEnd:
    async def test_produces_a_full_result(self):
        service = build_service()

        job_id = await run_to_completion(service, uploads())
        result = service.result(job_id)

        assert isinstance(result, AnalysisResult)
        # 친구비는 정산액이라 음수가 정상이다. 관계-점수-계산-규칙 10장
        assert -100_000 <= result.scores.friend_fee <= 100_000
        assert len(result.report.sections) >= 2
        assert result.meta.image_count == 3

    async def test_job_reaches_done(self):
        service = build_service()

        job_id = await run_to_completion(service, uploads())

        assert service.status(job_id).status is JobStatus.DONE
        assert service.status(job_id).stage is None

    async def test_result_does_not_contain_conversation_text(self):
        service = build_service()

        job_id = await run_to_completion(service, uploads())
        payload = service.result(job_id).model_dump_json(by_alias=True)

        # 대화 원문은 결과에 실리지 않는다
        assert "messages" not in payload
        assert "emotionalTone" not in payload

    async def test_uploaded_images_are_discarded_once_analysis_ends(self):
        service = build_service()

        job_id = await run_to_completion(service, uploads())

        assert service.blob_store.list_keys(job_id) == []


class TestFailureHandling:
    async def test_a_failing_stage_marks_the_job_failed(self):
        service = build_service()

        class BrokenOcr:
            name = "broken"

            async def read(self, images):
                raise AppError(ErrorCode.OCR_FAILED)

        service.pipeline.ocr = BrokenOcr()

        job = await service.create(uploads())
        await service.wait_for(job.job_id)

        stored = service.status(job.job_id)
        assert stored.status is JobStatus.FAILED
        assert stored.error is not None
        assert stored.error.code is ErrorCode.OCR_FAILED

    async def test_result_of_a_failed_job_raises_the_original_error(self):
        service = build_service()

        class BrokenOcr:
            name = "broken"

            async def read(self, images):
                raise AppError(ErrorCode.NO_CONVERSATION_FOUND)

        service.pipeline.ocr = BrokenOcr()
        job = await service.create(uploads())
        await service.wait_for(job.job_id)

        with pytest.raises(AppError) as caught:
            service.result(job.job_id)
        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND

    async def test_unexpected_error_becomes_internal_error(self):
        service = build_service()

        class ExplodingOcr:
            name = "exploding"

            async def read(self, images):
                raise RuntimeError("예상 못한 실패")

        service.pipeline.ocr = ExplodingOcr()
        job = await service.create(uploads())
        await service.wait_for(job.job_id)

        assert service.status(job.job_id).error.code is ErrorCode.INTERNAL_ERROR

    async def test_timeout_marks_the_job_as_timed_out(self):
        service = build_service(total_timeout_seconds=0)

        class SlowOcr:
            name = "slow"

            async def read(self, images):
                await asyncio.sleep(5)
                return ()

        service.pipeline.ocr = SlowOcr()
        job = await service.create(uploads())
        await service.wait_for(job.job_id)

        assert service.status(job.job_id).error.code is ErrorCode.ANALYSIS_TIMEOUT

    async def test_images_are_discarded_even_when_analysis_fails(self):
        service = build_service()

        class BrokenOcr:
            name = "broken"

            async def read(self, images):
                raise AppError(ErrorCode.OCR_FAILED)

        service.pipeline.ocr = BrokenOcr()
        job = await service.create(uploads())
        await service.wait_for(job.job_id)

        assert service.blob_store.list_keys(job.job_id) == []


class TestLifecycle:
    async def test_result_before_completion_is_not_ready(self):
        service = build_service()
        job = await service.create(uploads())

        try:
            with pytest.raises(AppError) as caught:
                service.result(job.job_id)
            assert caught.value.code is ErrorCode.JOB_NOT_READY
        finally:
            await service.wait_for(job.job_id)

    async def test_delete_removes_the_job_and_the_images(self):
        service = build_service()
        job_id = await run_to_completion(service, uploads())

        service.delete(job_id)

        with pytest.raises(AppError) as caught:
            service.status(job_id)
        assert caught.value.code is ErrorCode.JOB_NOT_FOUND

    async def test_delete_is_idempotent(self):
        service = build_service()
        job_id = await run_to_completion(service, uploads())

        service.delete(job_id)
        service.delete(job_id)

    async def test_rejects_invalid_uploads_before_creating_a_job(self):
        service = build_service()

        with pytest.raises(AppError) as caught:
            await service.create([])

        assert caught.value.code is ErrorCode.IMAGE_TOO_MANY
