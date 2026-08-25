"""FastAPI 애플리케이션.

기준 명세 10장의 구조를 따르며, 의존성 조립은 여기서만 한다.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.rate_limit import RateLimiter
from app.api.routes import router
from app.api.schemas import ErrorBody, ErrorResponse
from app.application.service.analysis_service import AnalysisService
from app.application.service.pipeline import AnalysisPipeline
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings, get_settings
from app.infrastructure.storage.memory import InMemoryBlobStore, InMemoryJobStore

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60


def _error_response(error: AppError, headers: dict[str, str] | None = None) -> JSONResponse:
    """오류 응답 봉투. 메시지에 대화 원문이나 식별자를 넣지 않는다."""
    body = ErrorResponse(error=ErrorBody.of(error))
    return JSONResponse(
        status_code=error.http_status,
        content=body.model_dump(by_alias=True),
        headers=headers,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    sweeper = asyncio.create_task(_sweep_loop(app))
    try:
        yield
    finally:
        sweeper.cancel()
        await asyncio.gather(sweeper, return_exceptions=True)
        await app.state.service.shutdown()


async def _sweep_loop(app: FastAPI) -> None:
    """TTL이 지난 작업을 주기적으로 지운다.

    조회 시점에도 만료를 확인하지만, 아무도 조회하지 않는 작업은 그대로 남는다.
    영구 저장 금지 원칙을 지키려면 아무도 찾지 않아도 사라져야 한다.
    """
    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            removed = app.state.service.sweep()
            if removed:
                logger.info("만료된 작업 %d건 정리", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("만료 정리 중 오류")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="친구비 측정기 API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.state.settings = settings
    app.state.service = AnalysisService(
        job_store=InMemoryJobStore(ttl_seconds=settings.ttl_seconds),
        blob_store=InMemoryBlobStore(),
        pipeline=AnalysisPipeline.from_settings(settings),
        settings=settings,
    )
    app.state.limiter = RateLimiter(
        per_minute=settings.rate_limit_per_minute,
        per_day=settings.daily_analysis_limit,
        concurrent=settings.concurrent_analysis_limit,
        poll_per_minute=settings.poll_rate_limit_per_minute,
    )
    # 분석이 끝나면 동시 실행 슬롯을 돌려주기 위한 job_id -> ip 대응표
    app.state.pending_release = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],  # 배포 시 서비스 도메인만 넣는다. 와일드카드 금지
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = None
        if exc.code in (
            ErrorCode.RATE_LIMITED,
            ErrorCode.DAILY_LIMIT_EXCEEDED,
            ErrorCode.CONCURRENCY_LIMIT,
        ):
            ip = request.headers.get("x-forwarded-for", "")
            ip = ip.split(",")[0].strip() or (request.client.host if request.client else "unknown")
            headers = {
                "Retry-After": str(request.app.state.limiter.retry_after_for(exc.code, ip)),
                "X-RateLimit-Remaining": "0",
            }
        return _error_response(exc, headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 업로드 형식이 어긋난 경우다. 상세 내용은 노출하지 않는다
        return _error_response(AppError(ErrorCode.IMAGE_FORMAT_UNSUPPORTED))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 오류")
        return _error_response(AppError(ErrorCode.INTERNAL_ERROR))

    app.include_router(router)
    return app


app = create_app()
