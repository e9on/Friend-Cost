"""분석 작업의 수명주기를 관리한다.

기준 명세 4장: 분석 요청은 즉시 `jobId` 를 반환하고, 클라이언트는 상태를 폴링한다.

분석은 백그라운드 태스크로 돌린다. 큐를 두지 않는 이유는 기준 명세 4장이
"초기에는 단일 프로세스 내 백그라운드 작업으로 시작한다"고 정했기 때문이다.
"""

import asyncio
import logging
from typing import Callable, Sequence

from app.application.service.pipeline import AnalysisPipeline, to_app_error
from app.application.service.upload_validator import UploadedImage, validate_uploads
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings
from app.domain.model.job import AnalysisJob
from app.domain.model.result import AnalysisResult
from app.infrastructure.storage.base import BlobStore, JobStore

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(
        self,
        job_store: JobStore,
        blob_store: BlobStore,
        pipeline: AnalysisPipeline,
        settings: Settings,
        on_finish: Callable[[str], None] | None = None,
    ) -> None:
        self.job_store = job_store
        self.blob_store = blob_store
        self.pipeline = pipeline
        self.settings = settings
        # 분석이 끝났을 때 호출된다. 자원 반납을 폴링에 의존하지 않기 위한 통로다
        self.on_finish = on_finish
        self._tasks: dict[str, asyncio.Task] = {}

    async def create(self, images: Sequence[UploadedImage]) -> AnalysisJob:
        """업로드를 받아 작업을 만들고 분석을 시작한다.

        검증은 작업을 만들기 **전에** 한다. 잘못된 업로드로 저장소에
        쓰레기를 남기지 않기 위해서다.
        """
        validated = validate_uploads(images, self.settings)

        job = self.job_store.create()
        keys = [
            self.blob_store.put(job.job_id, index, image.data)
            for index, image in enumerate(validated)
        ]

        # 바이트를 그대로 넘기지 않고 **저장소 키만** 넘긴다.
        #
        # 인메모리 구현에서는 차이가 없어 보인다. 그러나 외부 오브젝트
        # 스토리지로 갈아 끼우면(기준 명세 6장) 이미지를 계속 들고 있을
        # 필요가 없어지고, 동시 요청이 많을 때 메모리가 줄어든다.
        self._tasks[job.job_id] = asyncio.create_task(self._execute(job, keys))
        return job

    async def _execute(self, job: AnalysisJob, keys: list[str]) -> None:
        try:
            images = [self.blob_store.get(key) for key in keys]
            result = await asyncio.wait_for(
                self.pipeline.run(job, images),
                timeout=self.settings.total_timeout_seconds,
            )
            job.succeed(result)
        except BaseException as exc:  # 취소를 포함해 어떤 경우에도 상태를 남긴다
            job.fail(to_app_error(exc))
        finally:
            # 분석이 끝나면 원본 이미지는 더 필요 없다. TTL을 기다리지 않고 지운다
            self.blob_store.delete_all(job.job_id)
            self.job_store.save(job)
            self._tasks.pop(job.job_id, None)
            self._notify_finished(job.job_id)

    def _notify_finished(self, job_id: str) -> None:
        """자원 반납 통지. 여기서 난 오류가 분석 결과를 덮지 않게 한다."""
        if self.on_finish is None:
            return
        try:
            self.on_finish(job_id)
        except Exception:
            logger.exception("종료 통지 처리 중 오류 job=%s", job_id)

    async def wait_for(self, job_id: str) -> None:
        """해당 작업이 끝날 때까지 기다린다. 테스트와 종료 처리에 쓴다."""
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        """진행 중인 작업을 정리한다."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def status(self, job_id: str) -> AnalysisJob:
        return self.job_store.get(job_id)

    def result(self, job_id: str) -> AnalysisResult:
        job = self.job_store.get(job_id)
        job.raise_if_unavailable()
        if job.result is None:  # 상태는 done인데 결과가 없다면 구현 결함이다
            raise AppError(ErrorCode.INTERNAL_ERROR)
        return job.result

    def delete(self, job_id: str) -> None:
        """즉시 삭제한다. 존재 여부를 알려주지 않는다.

        없는 작업에도 조용히 성공하는 이유는, 존재 여부를 응답으로 구분해 주면
        `jobId` 유효성을 탐지하는 통로가 되기 때문이다.
        """
        self.blob_store.delete_all(job_id)
        self.job_store.delete(job_id)

    def sweep(self) -> int:
        return self.job_store.sweep()
