"""애플리케이션 수명주기와 오류 처리기.

기준 명세 5장(만료 정리), API 명세 2장(오류 봉투).
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.domain.value_object.enums import JobStatus
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


def files(seed: int = 0):
    return [("images", (f"shot{seed}.png", png_bytes() + bytes([seed]) * 64, "image/png"))]


class TestSweepLoop:
    async def test_expired_jobs_disappear_without_being_polled(self):
        """아무도 조회하지 않는 작업도 사라져야 한다.

        조회 시점에만 만료를 확인하면, 결과를 보지 않고 떠난 사용자의 대화가
        프로세스에 남는다. 영구 저장 금지 원칙이 이 지점에서 깨진다.
        """
        settings = Settings(ttl_seconds=0, sweep_interval_seconds=0)
        app = create_app(settings)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.post("/v1/analyses", files=files(1))
                job_id = response.json()["jobId"]
                await app.state.service.wait_for(job_id)

                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if app.state.service.job_store.sweep() == 0:
                        break

                status = await client.get(f"/v1/analyses/{job_id}")
                assert status.status_code in (404, 410)

    async def test_sweep_failures_do_not_kill_the_loop(self):
        settings = Settings(sweep_interval_seconds=0)
        app = create_app(settings)

        calls = {"count": 0}
        original = app.state.service.sweep

        def flaky() -> int:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("정리 중 오류")
            return original()

        app.state.service.sweep = flaky

        async with app.router.lifespan_context(app):
            for _ in range(50):
                await asyncio.sleep(0.01)
                if calls["count"] >= 3:
                    break

        assert calls["count"] >= 3, "한 번 실패했다고 정리가 멈추면 안 된다"


class TestShutdown:
    async def test_running_analyses_are_cancelled_on_shutdown(self):
        settings = Settings(rate_limit_per_minute=100, daily_analysis_limit=100)
        app = create_app(settings)

        class SlowOcr:
            name = "slow"

            async def read(self, images):
                await asyncio.sleep(30)
                return ()

        app.state.service.pipeline.ocr = SlowOcr()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.post("/v1/analyses", files=files(1))
                job_id = response.json()["jobId"]
                await asyncio.sleep(0.02)

        # lifespan을 빠져나오면 진행 중이던 작업은 정리되어 있어야 한다
        assert app.state.service.status(job_id).status is JobStatus.FAILED


class TestErrorHandlers:
    async def test_malformed_upload_returns_the_documented_envelope(self):
        app = create_app(Settings())
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.post(
                    "/v1/analyses",
                    content=b"not a multipart body",
                    headers={"content-type": "multipart/form-data; boundary=x"},
                )

        assert response.status_code == 400
        assert set(response.json()["error"]) == {"code", "message", "retryable"}

    async def test_unexpected_errors_become_internal_error(self):
        app = create_app(Settings())

        def explode(job_id):
            raise RuntimeError("조회 중 폭발")

        app.state.service.status = explode
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.get("/v1/analyses/some-id")

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"

    async def test_internal_error_message_does_not_leak_details(self):
        app = create_app(Settings())

        def explode(job_id):
            raise RuntimeError("데이터베이스 비밀번호는 hunter2")

        app.state.service.status = explode
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.get("/v1/analyses/some-id")

        assert "hunter2" not in response.text


class TestForwardedIp:
    async def test_uses_the_first_forwarded_address(self):
        """프록시 뒤에서는 X-Forwarded-For의 첫 주소가 실제 요청자다."""
        settings = Settings(rate_limit_per_minute=1, daily_analysis_limit=100)
        app = create_app(settings)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                headers_a = {"x-forwarded-for": "203.0.113.1, 70.41.3.18"}
                headers_b = {"x-forwarded-for": "203.0.113.2"}

                first = await client.post("/v1/analyses", files=files(1), headers=headers_a)
                blocked = await client.post("/v1/analyses", files=files(2), headers=headers_a)
                other = await client.post("/v1/analyses", files=files(3), headers=headers_b)

                assert first.status_code == 202
                assert blocked.status_code == 429  # 같은 요청자
                assert other.status_code == 202  # 다른 요청자
