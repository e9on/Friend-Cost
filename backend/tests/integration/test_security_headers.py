"""보안 헤더.

`운영-보안-법적고지-명세.md` 6.2의 배포 전 항목이다.

API 서버라 브라우저가 직접 렌더링할 일은 없지만, 응답이 어딘가에 끼워지거나
잘못 해석되는 경로를 막아둔다. 비용이 거의 들지 않는 방어다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


@pytest.fixture
async def client():
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


class TestSecurityHeaders:
    async def test_content_type_is_not_sniffed(self, client):
        """브라우저가 JSON을 다른 형식으로 추측 해석하지 못하게 한다."""
        response = await client.get("/health")

        assert response.headers["x-content-type-options"] == "nosniff"

    async def test_page_cannot_be_framed(self, client):
        response = await client.get("/health")

        assert response.headers["x-frame-options"] == "DENY"

    async def test_referrer_is_not_leaked(self, client):
        """jobId가 URL에 있으므로 다른 사이트로 새어 나가면 안 된다."""
        response = await client.get("/health")

        assert response.headers["referrer-policy"] == "no-referrer"

    async def test_content_security_policy_blocks_everything(self, client):
        # API 응답이 무언가를 불러올 이유가 없다
        response = await client.get("/health")

        assert response.headers["content-security-policy"] == "default-src 'none'"

    async def test_powerful_features_are_disabled(self, client):
        response = await client.get("/health")

        policy = response.headers["permissions-policy"]
        for feature in ("camera", "microphone", "geolocation"):
            assert f"{feature}=()" in policy

    async def test_analysis_results_are_never_cached(self, client):
        """결과에는 사적인 대화 분석이 담긴다. 중간 캐시에 남으면 안 된다."""
        response = await client.post(
            "/v1/analyses",
            files=[("images", ("a.png", png_bytes(), "image/png"))],
        )

        assert "no-store" in response.headers["cache-control"]

    async def test_headers_are_present_on_errors_too(self, client):
        response = await client.get("/v1/analyses/00000000-0000-4000-8000-000000000000")

        assert response.status_code == 404
        assert response.headers["x-content-type-options"] == "nosniff"


class TestHsts:
    async def test_hsts_is_absent_over_plain_http(self, client):
        """HTTP로 보낸 HSTS 헤더는 브라우저가 무시한다. 붙일 이유가 없다."""
        response = await client.get("/health")

        assert "strict-transport-security" not in response.headers

    async def test_hsts_is_sent_when_the_proxy_reports_https(self):
        app = create_app(Settings())
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.get(
                    "/health", headers={"x-forwarded-proto": "https"}
                )

        assert "max-age=" in response.headers["strict-transport-security"]
