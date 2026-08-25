"""과도한 요청 본문을 받기 전에 막는다.

지금까지는 30MB를 보내도 전부 읽은 뒤에야 거절했다. 상한이 20MB인데
그것을 넘는 요청도 일단 다 받았다는 뜻이다.

본문을 읽기 전에 `Content-Length` 로 판단하면 대역폭과 디스크를 아낀다.
헤더는 위조할 수 있지만, 정직하게 큰 요청을 보내는 대부분의 경우를
싸게 걸러낸다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


@pytest.fixture
async def client():
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


def multipart(size: int) -> tuple[bytes, dict]:
    return b"x" * size, {"content-type": "multipart/form-data; boundary=x"}


class TestOversizedBody:
    async def test_a_body_beyond_the_limit_is_refused(self, client):
        body, headers = multipart(30 * 1024 * 1024)

        response = await client.post("/v1/analyses", content=body, headers=headers)

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"

    async def test_the_refusal_uses_the_documented_envelope(self, client):
        body, headers = multipart(30 * 1024 * 1024)

        response = await client.post("/v1/analyses", content=body, headers=headers)

        assert set(response.json()["error"]) == {"code", "message", "retryable"}

    async def test_a_body_within_the_limit_is_read(self, client):
        """상한 안쪽 요청은 평소대로 처리되어야 한다."""
        response = await client.post(
            "/v1/analyses",
            files=[("images", ("a.png", png_bytes(), "image/png"))],
        )

        assert response.status_code == 202

    async def test_requests_without_a_body_are_untouched(self, client):
        assert (await client.get("/health")).status_code == 200

    async def test_a_missing_content_length_still_reaches_validation(self, client):
        """헤더가 없으면 판단할 수 없다. 평소 검증으로 넘긴다."""
        response = await client.post(
            "/v1/analyses",
            content=b"not multipart",
            headers={"content-type": "multipart/form-data; boundary=x"},
        )

        # 통과시키되, 뒤쪽 검증이 잡는다
        assert response.status_code in (400, 413)

    async def test_a_lying_content_length_is_still_caught_later(self, client):
        """헤더는 위조할 수 있다. 앞선 검사는 싼 방어일 뿐이다."""
        response = await client.post(
            "/v1/analyses",
            content=b"x" * (30 * 1024 * 1024),
            headers={
                "content-type": "multipart/form-data; boundary=x",
                "content-length": "100",
            },
        )

        assert response.status_code >= 400
