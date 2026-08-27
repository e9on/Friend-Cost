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
from app.ai.guard.verbatim import strip_verbatim
from app.ai.agent.report import ReportAgent
from app.ai.parser import parse
from app.ai.provider.stub import StubLlmProvider
from app.algorithm.calculator import calculate_scores
from app.common.audit import audit
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
    if settings.llm_provider == "anthropic":
        from app.ai.provider.anthropic import AnthropicProvider

        return AnthropicProvider(
            model=settings.llm_model,
            effort=settings.llm_effort,
            timeout_seconds=settings.llm_timeout_seconds,
            api_key=settings.llm_api_key,
        )

    # 아래는 모두 OpenAI 호환 스펙을 따르므로 구현 하나로 덮는다
    from app.ai.provider.openai_compatible import OpenAiCompatibleProvider

    if not settings.llm_api_key:
        raise ValueError(f"{settings.llm_provider} 를 쓰려면 FC_LLM_API_KEY 가 필요하다")

    return OpenAiCompatibleProvider(
        name=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=settings.llm_reasoning_effort,
    )


def _build_ocr_engine(settings: Settings) -> OcrEngine:
    if settings.ocr_engine == "stub":
        return StubOcrEngine()
    if settings.ocr_engine == "google_vision":
        from app.infrastructure.ocr.google_vision import GoogleVisionOcrEngine

        if not settings.ocr_api_key:
            raise ValueError("google_vision 을 쓰려면 FC_OCR_API_KEY 가 필요하다")
        return GoogleVisionOcrEngine(
            api_key=settings.ocr_api_key,
            timeout_seconds=settings.ocr_timeout_seconds,
        )
    if settings.ocr_engine == "rapid":
        # 컨테이너 내장 OCR. API 키가 필요 없는 대신 상시 실행을 전제한다.
        # 모델을 처음 쓸 때 약 23MB를 내려받으므로 배포 이미지에 미리 넣는다
        from app.infrastructure.ocr.rapid import RapidOcrEngine

        return RapidOcrEngine()
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
        # 모델이 notableMoments 에 대화 원문을 담아 보내는 일이 실제로 있었다.
        # 프롬프트로 금지해두었지만 지시는 강제가 아니다. AI-프롬프트-명세 3.5
        analysis = strip_verbatim(analysis, convo)

        job.advance(JobStage.SCORING)
        scores = calculate_scores(convo, analysis)

        job.advance(JobStage.REPORTING)
        report = await asyncio.wait_for(
            self.report_agent.run(analysis, scores), timeout=settings.llm_timeout_seconds
        )

        # jobId 는 남기지 않는다. 별도 인증이 없어 그것이 곧 접근 토큰이다
        audit(
            "analysis.completed",
            images=convo.meta.image_count,
            messages=convo.meta.message_count,
            dropped=convo.meta.dropped_count,
            sampled=convo.meta.sampled,
            coverage=round(convo.meta.time_coverage, 2),
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
