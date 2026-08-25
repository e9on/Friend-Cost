"""로그가 무엇을 남기고 무엇을 남기지 않는가.

두 가지를 본다.

- **남기면 안 되는 것이 안 남는가.** 대화 원문, 파일명, `jobId`.
  `jobId` 는 사실상의 접근 토큰이라(API 명세 2장) 로그를 읽을 수 있으면
  남의 결과를 조회할 수 있다.
- **필요한 것이 남는가.** 어느 단계가 실패하는지, 얼마나 걸리는지,
  비용이 얼마나 나가는지. 원문 없이도 이건 알아야 운영이 된다.
"""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.common.audit import AuditEvent, audit
from app.config.settings import Settings
from app.main import create_app
from tests.unit.test_upload_validation import png_bytes


OUR_LOGGERS = ("audit", "app")


@pytest.fixture
def captured(caplog):
    """우리 코드가 남긴 로그만 본다.

    httpx 같은 라이브러리는 요청 URL을 그대로 찍는다. 그건 우리가 고칠
    수 있는 것이 아니다. 다만 `jobId` 가 URL에 있는 한 배포 플랫폼의
    접근 로그에는 남는다는 사실은 문서에 적어두었다.
    """
    caplog.set_level(logging.INFO)

    class OursOnly:
        @property
        def text(self) -> str:
            ours = [
                record.getMessage()
                for record in caplog.records
                if record.name.split(".")[0] in OUR_LOGGERS
            ]
            return chr(10).join(ours)

    return OursOnly()


def files(count: int = 2):
    return [
        ("images", (f"내-비밀-대화-{i}.png", png_bytes() + bytes([i]) * 64, "image/png"))
        for i in range(count)
    ]


async def run_analysis(client: AsyncClient) -> str:
    response = await client.post("/v1/analyses", files=files())
    job_id = response.json()["jobId"]
    for _ in range(200):
        status = await client.get(f"/v1/analyses/{job_id}")
        if status.json()["status"] in ("done", "failed"):
            break
    return job_id


@pytest.fixture
async def client():
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


class TestNothingSensitiveLeaks:
    async def test_job_id_never_appears_in_our_logs(self, client, captured):
        """jobId 는 사실상의 접근 토큰이다. 우리가 직접 찍어서는 안 된다."""
        job_id = await run_analysis(client)

        assert job_id not in captured.text, "jobId 가 로그에 남았다"

    async def test_uploaded_filenames_never_appear(self, client, captured):
        await run_analysis(client)

        assert "내-비밀-대화" not in captured.text

    async def test_conversation_text_never_appears(self, client, captured):
        """스텁 OCR이 만드는 문구가 로그에 새면 실제 대화도 샌다."""
        await run_analysis(client)

        for phrase in ("내일 시간 돼?", "미안 좀 늦을 듯", "웬일이야"):
            assert phrase not in captured.text


class TestUsefulThingsAreLogged:
    async def test_completion_is_recorded_with_counts(self, client, captured):
        await run_analysis(client)

        assert "analysis.completed" in captured.text
        assert "images=" in captured.text
        assert "messages=" in captured.text

    async def test_duration_is_recorded(self, client, captured):
        await run_analysis(client)

        assert "ms=" in captured.text

    async def test_failures_record_the_stage_and_code(self, captured):
        app = create_app(Settings())

        class BrokenOcr:
            name = "broken"

            async def read(self, images):
                from app.common.errors import AppError, ErrorCode

                raise AppError(ErrorCode.OCR_FAILED)

        app.state.service.pipeline.ocr = BrokenOcr()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with app.router.lifespan_context(app):
                response = await client.post("/v1/analyses", files=files(1))
                await app.state.service.wait_for(response.json()["jobId"])

        assert "analysis.failed" in captured.text
        assert "OCR_FAILED" in captured.text
        assert "stage=ocr" in captured.text


class TestAuditEvent:
    def test_renders_as_key_value_pairs(self):
        event = AuditEvent(
            "analysis.completed", images=5, messages=184, ms=1200, confidence="high"
        )

        rendered = str(event)

        assert rendered.startswith("analysis.completed ")
        assert "images=5" in rendered
        assert "confidence=high" in rendered

    def test_drops_empty_values(self):
        event = AuditEvent("analysis.failed", code="OCR_FAILED", stage=None)

        assert "stage=" not in str(event)

    @pytest.mark.parametrize(
        "value",
        [
            "오늘 진짜 힘들었는데",
            "ㅋㅋ",
            "내일 시간 돼?",
            "hello world",  # 공백만 있어도 식별자가 아니다
        ],
    )
    def test_refuses_anything_that_is_not_an_identifier(self, value):
        """실수로 원문을 넘기는 것을 막는다.

        길이로 막지 않는 이유는 한글이 짧기 때문이다. "오늘 진짜 힘들었는데"는
        12자라 어지간한 길이 제한을 다 빠져나간다.
        """
        with pytest.raises(ValueError, match="감사 로그"):
            AuditEvent("analysis.completed", note=value)

    def test_allows_short_known_values(self):
        assert "code=TOO_FEW_MESSAGES" in str(
            AuditEvent("analysis.failed", code="TOO_FEW_MESSAGES")
        )


class TestAuditHelper:
    def test_writes_to_the_audit_logger(self, caplog):
        caplog.set_level(logging.INFO, logger="audit")

        audit("analysis.completed", images=3, ms=900)

        assert "analysis.completed" in caplog.text
        assert "images=3" in caplog.text
