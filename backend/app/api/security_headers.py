"""응답에 보안 헤더를 붙인다.

`운영-보안-법적고지-명세.md` 6.2.

API 서버라 브라우저가 이 응답을 직접 렌더링할 일은 거의 없다. 그래도
붙이는 이유는, 응답이 어딘가에 끼워지거나 잘못 해석되는 경로를 막는 비용이
거의 0이기 때문이다.

두 가지는 이 서비스의 성격 때문에 특히 중요하다.

- `Referrer-Policy: no-referrer` — `jobId` 가 URL에 들어간다. 결과 페이지에서
  외부 링크를 타면 그 값이 다른 사이트로 새어 나갈 수 있다.
- `Cache-Control: no-store` — 결과에는 사적인 대화 분석이 담긴다. 중간 캐시나
  브라우저 디스크에 남으면 TTL 5분이 무의미해진다.
"""

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 1년. 배포 도메인이 HTTPS로 안정된 뒤에 preload를 검토한다
HSTS_MAX_AGE: Final = 31_536_000

STATIC_HEADERS: Final = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # API 응답이 무언가를 불러올 이유가 없다
    "Content-Security-Policy": "default-src 'none'",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    ),
    "Cross-Origin-Resource-Policy": "same-origin",
    # 분석 결과는 사적인 내용이다. 어디에도 남기지 않는다
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


def _is_https(request: Request) -> bool:
    """프록시 뒤에서는 원래 스킴이 헤더로 온다."""
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip() == "https"
    return request.url.scheme == "https"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        for name, value in STATIC_HEADERS.items():
            response.headers.setdefault(name, value)

        # HTTP로 보낸 HSTS는 브라우저가 무시한다. 붙일 이유가 없다
        if _is_https(request):
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={HSTS_MAX_AGE}; includeSubDomains",
            )

        return response
