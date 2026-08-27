"""HTTP 인터페이스 전체.

API 명세 3~11장. 실제 모델 없이 스텁으로 전 구간을 돈다.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


@pytest.fixture
def settings():
    return Settings(rate_limit_per_minute=1000, daily_analysis_limit=1000)


@pytest.fixture
async def client(settings):
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


def files(count: int = 3):
    return [
        ("images", (f"shot{i}.png", png_bytes() + bytes([i]) * 64, "image/png"))
        for i in range(count)
    ]


async def create_and_wait(client: AsyncClient, count: int = 3) -> str:
    response = await client.post("/v1/analyses", files=files(count))
    assert response.status_code == 202, response.text
    job_id = response.json()["jobId"]

    for _ in range(100):
        status = await client.get(f"/v1/analyses/{job_id}")
        if status.json()["status"] in ("done", "failed"):
            return job_id
        await asyncio.sleep(0.01)
    raise AssertionError("분석이 끝나지 않았다")


class TestCreate:
    async def test_returns_202_with_a_job_id(self, client):
        response = await client.post("/v1/analyses", files=files())

        assert response.status_code == 202
        body = response.json()
        assert len(body["jobId"]) == 36
        assert body["status"] == "pending"
        assert body["expiresAt"] > 0
        assert body["pollAfterSeconds"] >= 1

    async def test_rejects_an_empty_upload(self, client):
        response = await client.post("/v1/analyses", files=[])

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "IMAGE_TOO_MANY"

    async def test_rejects_too_many_images(self, client):
        response = await client.post("/v1/analyses", files=files(11))

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "IMAGE_TOO_MANY"

    async def test_rejects_a_disguised_executable(self, client):
        payload = [("images", ("innocent.png", b"MZ\x90\x00" + b"\x00" * 500, "image/png"))]

        response = await client.post("/v1/analyses", files=payload)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "IMAGE_FORMAT_UNSUPPORTED"


class TestStatus:
    async def test_reports_progress_then_completion(self, client):
        job_id = await create_and_wait(client)

        body = (await client.get(f"/v1/analyses/{job_id}")).json()

        assert body["status"] == "done"
        assert body["stage"] is None

    async def test_unknown_job_is_404(self, client):
        response = await client.get("/v1/analyses/00000000-0000-4000-8000-000000000000")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "JOB_NOT_FOUND"

    async def test_failed_job_still_returns_200(self, client):
        """작업 조회 자체는 성공했으므로 HTTP는 200이다."""
        response = await client.post("/v1/analyses", files=files(1))
        job_id = response.json()["jobId"]

        for _ in range(100):
            body = (await client.get(f"/v1/analyses/{job_id}")).json()
            if body["status"] in ("done", "failed"):
                break
            await asyncio.sleep(0.01)

        assert (await client.get(f"/v1/analyses/{job_id}")).status_code == 200


class TestResult:
    async def test_returns_scores_and_report(self, client):
        job_id = await create_and_wait(client)

        response = await client.get(f"/v1/analyses/{job_id}/result")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"jobId", "scores", "report", "meta", "expiresAt"}
        assert set(body["scores"]) == {
            "friendFee",
            "intimacy",
            "breakupRisk",
            "firstContactRatio",
            "avgReplySeconds",
            "contactBalance",
        }
        assert body["report"]["disclaimer"]

    async def test_can_be_read_more_than_once(self, client):
        job_id = await create_and_wait(client)

        first = await client.get(f"/v1/analyses/{job_id}/result")
        second = await client.get(f"/v1/analyses/{job_id}/result")

        assert first.json() == second.json()

    async def test_reading_does_not_extend_the_ttl(self, client):
        job_id = await create_and_wait(client)

        first = (await client.get(f"/v1/analyses/{job_id}/result")).json()["expiresAt"]
        second = (await client.get(f"/v1/analyses/{job_id}/result")).json()["expiresAt"]

        assert first == second

    async def test_result_before_completion_is_409(self, client):
        response = await client.post("/v1/analyses", files=files())
        job_id = response.json()["jobId"]

        early = await client.get(f"/v1/analyses/{job_id}/result")

        try:
            assert early.status_code in (409, 200)
            if early.status_code == 409:
                assert early.json()["error"]["code"] == "JOB_NOT_READY"
        finally:
            await create_and_wait(client, 1)

    async def test_never_contains_conversation_text(self, client):
        job_id = await create_and_wait(client)

        raw = (await client.get(f"/v1/analyses/{job_id}/result")).text

        assert "messages" not in raw
        assert "emotionalTone" not in raw


class TestDelete:
    async def test_delete_returns_204(self, client):
        job_id = await create_and_wait(client)

        response = await client.delete(f"/v1/analyses/{job_id}")

        assert response.status_code == 204
        assert (await client.get(f"/v1/analyses/{job_id}")).status_code == 404

    async def test_delete_is_idempotent(self, client):
        job_id = await create_and_wait(client)

        await client.delete(f"/v1/analyses/{job_id}")
        second = await client.delete(f"/v1/analyses/{job_id}")

        assert second.status_code == 204

    async def test_deleting_an_unknown_job_is_still_204(self, client):
        """존재 여부를 응답으로 알려주면 jobId 탐지 통로가 된다."""
        response = await client.delete("/v1/analyses/00000000-0000-4000-8000-000000000000")

        assert response.status_code == 204

    async def test_beacon_path_works_the_same(self, client):
        job_id = await create_and_wait(client)

        response = await client.post(f"/v1/analyses/{job_id}/deletion")

        assert response.status_code == 204
        assert (await client.get(f"/v1/analyses/{job_id}")).status_code == 404


class TestRateLimit:
    async def test_blocks_creation_beyond_the_per_minute_limit(self):
        app = create_app(Settings(rate_limit_per_minute=2, daily_analysis_limit=100))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                first = await client.post("/v1/analyses", files=files(1))
                second = await client.post("/v1/analyses", files=files(1))
                third = await client.post("/v1/analyses", files=files(1))

                assert first.status_code == 202
                assert second.status_code == 202
                assert third.status_code == 429
                assert third.json()["error"]["code"] == "RATE_LIMITED"
                assert third.headers["retry-after"]

    async def test_daily_limit_is_separate_from_the_minute_limit(self):
        app = create_app(Settings(rate_limit_per_minute=100, daily_analysis_limit=1))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                await client.post("/v1/analyses", files=files(1))
                blocked = await client.post("/v1/analyses", files=files(1))

                assert blocked.status_code == 429
                assert blocked.json()["error"]["code"] == "DAILY_LIMIT_EXCEEDED"

    async def test_polling_is_not_blocked_by_the_creation_limit(self, client):
        job_id = await create_and_wait(client)

        for _ in range(20):
            assert (await client.get(f"/v1/analyses/{job_id}")).status_code == 200


class TestErrorShape:
    async def test_errors_follow_the_documented_envelope(self, client):
        response = await client.get("/v1/analyses/00000000-0000-4000-8000-000000000000")

        error = response.json()["error"]
        assert set(error) == {"code", "message", "retryable"}
        assert isinstance(error["retryable"], bool)

    async def test_error_messages_do_not_leak_identifiers(self, client):
        job_id = "00000000-0000-4000-8000-000000000000"

        response = await client.get(f"/v1/analyses/{job_id}")

        assert job_id not in response.json()["error"]["message"]


class TestHealth:
    async def test_health_endpoint_reports_the_active_providers(self, client):
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["llmProvider"] == "stub"
        assert body["ocrEngine"] == "stub"


class TestNoDownloadEndpoint:
    async def test_download_endpoint_does_not_exist(self, client):
        """결과 이미지는 클라이언트가 렌더링한다. 기준 명세 11장."""
        job_id = await create_and_wait(client)

        response = await client.get(f"/v1/analyses/{job_id}/download")

        assert response.status_code == 404
