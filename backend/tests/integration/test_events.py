"""사용 이벤트.

서버는 분석 요청이 들어와야만 안다. 그 전에 떠난 사람은 흔적이 없다.
이탈 지점이 정확히 거기이므로 화면이 알려줘야 한다.

식별자를 두지 않는다. 그래서 "방문 100, 동의 60" 은 알아도 "그 60명이
누구인가"는 모른다. `데이터-계약-명세.md` 12-1
"""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(Settings(poll_rate_limit_per_minute=1000))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


class TestEvents:
    async def test_정해진_이름을_받는다(self, client):
        response = await client.post("/v1/events", json={"name": "consent.agreed"})

        assert response.status_code == 204

    async def test_모르는_이름은_거절한다(self, client):
        """아무 문자열이나 받으면 로그가 오염되고, 그 자체가 대화 원문이
        새는 통로가 된다."""
        response = await client.post("/v1/events", json={"name": "made.up"})

        assert response.status_code == 400

    async def test_대화_원문이_섞여도_거절한다(self, client):
        response = await client.post("/v1/events", json={"name": "오늘 진짜 힘들었는데"})

        assert response.status_code == 400

    async def test_이름이_없으면_거절한다(self, client):
        response = await client.post("/v1/events", json={})

        assert response.status_code in (400, 422)

    async def test_감사_로그에_남는다(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="audit"):
            await client.post("/v1/events", json={"name": "page.view"})

        assert any("page.view" in record.getMessage() for record in caplog.records)

    async def test_식별자를_남기지_않는다(self, client, caplog):
        """IP 도 세션도 남기지 않는다. 개인을 이어붙이지 않는 것이 의도다."""
        with caplog.at_level(logging.INFO, logger="audit"):
            await client.post(
                "/v1/events",
                json={"name": "page.view"},
                headers={"x-forwarded-for": "203.0.113.9"},
            )

        rendered = " ".join(record.getMessage() for record in caplog.records)
        assert "203.0.113.9" not in rendered

    async def test_요청_제한이_걸린다(self):
        """제한이 없으면 로그 폭탄의 통로가 된다."""
        app = create_app(Settings(poll_rate_limit_per_minute=2))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            async with app.router.lifespan_context(app):
                await http.post("/v1/events", json={"name": "page.view"})
                await http.post("/v1/events", json={"name": "page.view"})
                third = await http.post("/v1/events", json={"name": "page.view"})

                assert third.status_code == 429
