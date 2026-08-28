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
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.body_limit import BodyLimitMiddleware
from app.api.rate_limit import RateLimiter
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.routes import router
from app.api.schemas import ErrorBody, ErrorResponse
from app.application.service.analysis_service import AnalysisService
from app.application.service.pipeline import AnalysisPipeline
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings, get_settings
from app.infrastructure.storage.memory import InMemoryBlobStore, InMemoryJobStore

logger = logging.getLogger(__name__)

# 프레임워크가 만든 상태 코드를 우리 오류 코드로 옮긴다
_HTTP_STATUS_TO_CODE = {
    400: ErrorCode.IMAGE_FORMAT_UNSUPPORTED,
    404: ErrorCode.JOB_NOT_FOUND,
    405: ErrorCode.JOB_NOT_FOUND,
    409: ErrorCode.JOB_NOT_READY,
    410: ErrorCode.JOB_EXPIRED,
    413: ErrorCode.IMAGE_TOO_LARGE,
    422: ErrorCode.IMAGE_FORMAT_UNSUPPORTED,
    429: ErrorCode.RATE_LIMITED,
}


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
            await asyncio.sleep(app.state.settings.sweep_interval_seconds)
            removed = app.state.service.sweep()
            stale_keys = app.state.limiter.prune()
            if removed or stale_keys:
                logger.info("만료 작업 %d건, IP 기록 %d건 정리", removed, stale_keys)
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
    app.state.limiter = RateLimiter(
        per_minute=settings.rate_limit_per_minute,
        per_day=settings.daily_analysis_limit,
        concurrent=settings.concurrent_analysis_limit,
        poll_per_minute=settings.poll_rate_limit_per_minute,
        service_per_day=settings.service_daily_limit,
    )
    # 분석이 끝나면 동시 실행 슬롯을 돌려주기 위한 job_id -> ip 대응표
    app.state.pending_release = {}

    def release_slot(job_id: str) -> None:
        """분석이 끝나는 즉시 동시 실행 슬롯을 돌려준다.

        폴링 시점에 반납하면, 결과를 보지 않고 떠난 사용자가 그 IP의 슬롯을
        영영 붙들고 있게 된다.
        """
        ip = app.state.pending_release.pop(job_id, None)
        if ip:
            app.state.limiter.release(ip)

    app.state.service = AnalysisService(
        job_store=InMemoryJobStore(ttl_seconds=settings.ttl_seconds),
        blob_store=InMemoryBlobStore(),
        pipeline=AnalysisPipeline.from_settings(settings),
        settings=settings,
        on_finish=release_slot,
    )

    # 미들웨어는 나중에 등록한 것이 바깥에서 돈다.
    # 보안 헤더를 먼저 등록해 CORS 프리플라이트 응답에도 붙게 한다
    app.add_middleware(SecurityHeadersMiddleware)

    # 본문 크기 검사는 가장 바깥에 둔다. 읽기 전에 거절해야 의미가 있다
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_total_bytes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),  # FC_CORS_ORIGINS 로 설정
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

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """프레임워크가 직접 만드는 오류도 같은 봉투에 담는다.

        multipart 파싱 실패나 존재하지 않는 경로는 우리 코드에 닿기 전에
        Starlette이 처리한다. 그대로 두면 `{"detail": ...}` 형태가 새어 나가
        API 명세 2장의 오류 규격이 깨진다.
        """
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _error_response(AppError(code))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 오류")
        return _error_response(AppError(ErrorCode.INTERNAL_ERROR))

    app.include_router(router)
    return app


app = create_app()
