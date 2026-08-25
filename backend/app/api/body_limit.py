"""과도한 요청 본문을 읽기 전에 막는다.

`Content-Length` 만 보고 판단하므로 본문을 한 바이트도 받지 않는다.
대역폭과 디스크를 아낀다.

**헤더는 위조할 수 있다.** 그래서 이것은 뒤쪽 검증을 대신하지 않는다.
정직하게 큰 요청을 보내는 대부분의 경우를 싸게 걸러내는 앞단일 뿐이고,
실제 용량 검사는 `upload_validator` 가 다시 한다.
"""

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.common.errors import AppError, ErrorCode

# multipart 경계 문자열과 파트 헤더가 붙으므로 여유를 둔다.
# 이미지 10장이면 파트당 200바이트 남짓이라 넉넉한 값이다.
MULTIPART_OVERHEAD: Final = 64 * 1024


class BodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self._limit = max_bytes + MULTIPART_OVERHEAD

    async def dispatch(self, request: Request, call_next) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                size = 0
            if size > self._limit:
                error = AppError(ErrorCode.IMAGE_TOO_LARGE)
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": error.code.value,
                            "message": error.message,
                            "retryable": error.retryable,
                        }
                    },
                )
        return await call_next(request)
