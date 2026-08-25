"""분석 파이프라인.

기준 명세 7장의 흐름을 그대로 밟는다.

    OCR -> Parser -> Analysis Agent -> Validator -> Algorithm -> Report Agent -> Validator

각 단계에서 작업 상태를 갱신해 사용자가 진행 상황을 볼 수 있게 한다.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Sequence

from app.ai.agent.analysis import AnalysisAgent
from app.ai.agent.report import ReportAgent
from app.ai.parser import parse
from app.ai.provider.stub import StubLlmProvider
from app.algorithm.calculator import calculate_scores
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings
from app.domain.model.job import AnalysisJob
from app.domain.model.result import AnalysisResult, ResultMeta
from app.domain.value_object.enums import JobStage
from app.infrastructure.ocr.base import OcrEngine
from app.infrastructure.ocr.stub import StubOcrEngine

logger = logging.getLogger(__name__)


def _build_llm_provider(settings: Settings):
    """설정에 적힌 Provider를 만든다.

    실제 모델은 성능 평가 이후에 붙인다. 그때 이 함수에 분기 하나를 더하고
    설정값을 바꾸는 것으로 교체가 끝나야 한다.
    """
    if settings.llm_provider == "stub":
        return StubLlmProvider()
    raise ValueError(f"알 수 없는 llm provider: {settings.llm_provider}")


def _build_ocr_engine(settings: Settings) -> OcrEngine:
    if settings.ocr_engine == "stub":
        return StubOcrEngine()
    raise ValueError(f"알 수 없는 ocr engine: {settings.ocr_engine}")


@dataclass
class AnalysisPipeline:
    ocr: OcrEngine
    analysis_agent: AnalysisAgent
    report_agent: ReportAgent
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "AnalysisPipeline":
        provider = _build_llm_provider(settings)
        return cls(
            ocr=_build_ocr_engine(settings),
            analysis_agent=AnalysisAgent(provider),
            report_agent=ReportAgent(provider),
            settings=settings,
        )

    async def run(self, job: AnalysisJob, images: Sequence[bytes]) -> AnalysisResult:
        settings = self.settings

        job.advance(JobStage.OCR)
        pages = await asyncio.wait_for(
            self.ocr.read(images), timeout=settings.ocr_timeout_seconds
        )

        job.advance(JobStage.PARSING)
        convo = parse(pages, max_messages=settings.max_messages)

        job.advance(JobStage.ANALYZING)
        analysis = await asyncio.wait_for(
            self.analysis_agent.run(convo), timeout=settings.llm_timeout_seconds
        )

        job.advance(JobStage.SCORING)
        scores = calculate_scores(convo, analysis)

        job.advance(JobStage.REPORTING)
        report = await asyncio.wait_for(
            self.report_agent.run(analysis, scores), timeout=settings.llm_timeout_seconds
        )

        logger.info(
            "분석 완료 job=%s 이미지=%d 메시지=%d 샘플링=%s 신뢰도=%s",
            job.job_id,
            convo.meta.image_count,
            convo.meta.message_count,
            convo.meta.sampled,
            scores.confidence.value,
        )

        return AnalysisResult(
            job_id=job.job_id,
            scores=scores,
            report=report,
            meta=ResultMeta.of(convo.meta),
            expires_at=job.expires_at,
        )


def to_app_error(exc: BaseException) -> AppError:
    """파이프라인에서 나온 예외를 사용자에게 보일 오류로 접는다."""
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, asyncio.TimeoutError):
        return AppError(ErrorCode.ANALYSIS_TIMEOUT)
    logger.exception("파이프라인에서 예상하지 못한 오류")
    return AppError(ErrorCode.INTERNAL_ERROR)
