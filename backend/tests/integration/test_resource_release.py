"""분석이 끝나면 자원이 실제로 반납되는가.

폴링은 클라이언트의 선택이다. 사용자가 결과를 보지 않고 창을 닫아도
서버 쪽 자원은 제자리로 돌아와야 한다.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.rate_limit import RateLimiter
from app.config.settings import Settings
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


def files(seed: int = 0):
    return [("images", (f"shot{seed}.png", png_bytes() + bytes([seed]) * 64, "image/png"))]


class TestConcurrencySlotRelease:
    async def test_slot_returns_without_anyone_polling(self):
        """동시 한도만큼 요청하고 결과를 아무도 보지 않아도 다음 요청이 통과해야 한다.

        슬롯 반납이 폴링에 달려 있으면, 창을 닫고 떠난 사용자는 그 IP를
        프로세스가 재시작될 때까지 막아버린다.
        """
        settings = Settings(
            rate_limit_per_minute=100, daily_analysis_limit=100, concurrent_analysis_limit=2
        )
        app = create_app(settings)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                first = await client.post("/v1/analyses", files=files(1))
                second = await client.post("/v1/analyses", files=files(2))
                assert first.status_code == 202
                assert second.status_code == 202

                # 상태를 한 번도 조회하지 않고 분석이 끝나기만 기다린다
                await app.state.service.wait_for(first.json()["jobId"])
                await app.state.service.wait_for(second.json()["jobId"])

                third = await client.post("/v1/analyses", files=files(3))

                assert third.status_code == 202, third.text

    async def test_slot_returns_even_when_analysis_fails(self):
        settings = Settings(
            rate_limit_per_minute=100, daily_analysis_limit=100, concurrent_analysis_limit=1
        )
        app = create_app(settings)

        class BrokenOcr:
            name = "broken"

            async def read(self, images):
                raise RuntimeError("실패")

        app.state.service.pipeline.ocr = BrokenOcr()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                first = await client.post("/v1/analyses", files=files(1))
                await app.state.service.wait_for(first.json()["jobId"])

                second = await client.post("/v1/analyses", files=files(2))

                assert second.status_code == 202


class TestRateLimiterMemory:
    def test_pruning_drops_keys_whose_window_has_passed(self):
        """IP 기록이 무한히 쌓이면 안 된다.

        제한 창이 지난 IP는 흔적을 남기지 않아야 한다. 기준 명세 9장이
        "제한 창이 지나면 폐기한다"고 정한 것이 이 뜻이다.
        """
        now = [1_000.0]
        limiter = RateLimiter(
            per_minute=5,
            per_day=10,
            concurrent=3,
            poll_per_minute=60,
            clock=lambda: now[0],
        )

        for index in range(500):
            limiter.check_create(f"10.0.0.{index}")
            limiter.release(f"10.0.0.{index}")

        assert limiter.tracked_keys() >= 500

        now[0] += 25 * 60 * 60  # 하루가 지났다
        removed = limiter.prune()

        assert removed >= 500
        assert limiter.tracked_keys() == 0

    def test_pruning_keeps_active_keys(self):
        now = [1_000.0]
        limiter = RateLimiter(
            per_minute=5,
            per_day=10,
            concurrent=3,
            poll_per_minute=60,
            clock=lambda: now[0],
        )
        limiter.check_create("살아있는-ip")

        limiter.prune()

        assert limiter.tracked_keys() > 0
