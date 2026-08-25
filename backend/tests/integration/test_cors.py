"""CORS 설정.

기본값이 비어 있어야 한다. 실수로 열린 채 배포되는 것보다,
설정을 잊어 브라우저에서 안 되는 편이 낫다. 후자는 즉시 드러난다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import create_app


async def preflight(settings: Settings, origin: str):
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            return await client.options(
                "/v1/analyses",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )


class TestCors:
    async def test_closed_by_default(self):
        response = await preflight(Settings(), "https://evil.example")

        assert "access-control-allow-origin" not in response.headers

    async def test_configured_origin_is_allowed(self):
        settings = Settings(cors_origins=("https://friend-cost.example",))

        response = await preflight(settings, "https://friend-cost.example")

        assert (
            response.headers["access-control-allow-origin"]
            == "https://friend-cost.example"
        )

    async def test_other_origins_stay_blocked(self):
        settings = Settings(cors_origins=("https://friend-cost.example",))

        response = await preflight(settings, "https://evil.example")

        assert "access-control-allow-origin" not in response.headers

    async def test_wildcard_is_rejected(self):
        """와일드카드는 쓰지 않는다. 설정으로도 못 넣게 막는다."""
        with pytest.raises(ValueError, match="와일드카드"):
            Settings(cors_origins=("*",))

    async def test_credentials_are_never_allowed(self):
        settings = Settings(cors_origins=("https://friend-cost.example",))

        response = await preflight(settings, "https://friend-cost.example")

        # 인증이 없는 서비스다. 자격 증명을 주고받을 이유가 없다
        assert "access-control-allow-credentials" not in response.headers
