"""Provider의 HTTP 계층.

네트워크를 타지 않고 가짜 응답을 주입해서, 상대 서비스가 이런저런 응답을
돌려줄 때 우리가 제대로 접는지 본다.

실제 키를 넣는 순간에야 드러나는 문제를 미리 잡는 것이 목적이다.
"""

import httpx
import pytest

from app.ai.provider.anthropic import AnthropicProvider, _extract_text
from app.ai.provider.base import LlmRequest
from app.ai.provider.openai_compatible import OpenAiCompatibleProvider
from app.common.errors import AppError, ErrorCode
from app.infrastructure.ocr.google_vision import GoogleVisionOcrEngine
from tests.unit.test_upload_validation import png_bytes


def request(purpose: str = "analysis") -> LlmRequest:
    return LlmRequest(
        system="시스템 문안",
        user="사용자 문안",
        max_output_tokens=800,
        purpose=purpose,
    )


def mock_httpx(monkeypatch, handler) -> list[httpx.Request]:
    """`httpx.AsyncClient` 를 가짜 전송으로 바꾼다."""
    seen: list[httpx.Request] = []

    def record(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(record)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return seen


class TestOpenAiCompatibleTransport:
    async def test_sends_system_and_user_messages(self, monkeypatch):
        seen = mock_httpx(
            monkeypatch,
            lambda req: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3},
                },
            ),
        )
        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="secret")

        result = await provider.complete(request())

        assert result.text == "{}"
        body = seen[0].content.decode()
        assert "시스템 문안" in body and "사용자 문안" in body
        assert seen[0].headers["authorization"] == "Bearer secret"

    async def test_asks_for_json_and_pins_temperature(self, monkeypatch):
        """점수의 재현성을 위해 temperature를 0으로 둔다."""
        seen = mock_httpx(
            monkeypatch,
            lambda req: httpx.Response(
                200, json={"choices": [{"message": {"content": "{}"}}]}
            ),
        )

        await OpenAiCompatibleProvider(name="groq", model="m", api_key="k").complete(
            request()
        )

        body = seen[0].content.decode()
        assert '"temperature":0' in body.replace(" ", "")
        assert "json_object" in body

    @pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
    async def test_error_statuses_become_llm_failed(self, monkeypatch, status):
        mock_httpx(monkeypatch, lambda req: httpx.Response(status, json={}))
        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="k")

        with pytest.raises(AppError) as caught:
            await provider.complete(request())

        assert caught.value.code is ErrorCode.LLM_FAILED

    async def test_connection_failure_becomes_llm_failed(self, monkeypatch):
        def explode(req):
            raise httpx.ConnectError("연결 실패")

        mock_httpx(monkeypatch, explode)
        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="k")

        with pytest.raises(AppError) as caught:
            await provider.complete(request())

        assert caught.value.code is ErrorCode.LLM_FAILED

    async def test_url_is_built_from_the_known_base(self, monkeypatch):
        seen = mock_httpx(
            monkeypatch,
            lambda req: httpx.Response(
                200, json={"choices": [{"message": {"content": "{}"}}]}
            ),
        )

        await OpenAiCompatibleProvider(name="groq", model="m", api_key="k").complete(
            request()
        )

        assert str(seen[0].url).endswith("/chat/completions")
        assert "groq.com" in str(seen[0].url)


class TestAnthropicTransport:
    class FakeMessage:
        def __init__(self, blocks, stop_reason=None, usage=None):
            self.content = blocks
            self.stop_reason = stop_reason
            self.usage = usage

    class Block:
        def __init__(self, type_: str, text: str = ""):
            self.type = type_
            self.text = text

    class Usage:
        def __init__(self, input_tokens: int, output_tokens: int):
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens

    def provider_with(self, message):
        provider = AnthropicProvider(model="claude-haiku-4-5", api_key="k")

        class FakeMessages:
            async def create(self, **kwargs):
                self.kwargs = kwargs
                return message

        class FakeClient:
            def __init__(self):
                self.messages = FakeMessages()

        provider._client = FakeClient()
        return provider

    async def test_extracts_text_blocks_only(self):
        message = self.FakeMessage(
            [self.Block("thinking", "속으로 생각"), self.Block("text", ' {"a":1} ')],
            usage=self.Usage(120, 40),
        )

        result = await self.provider_with(message).complete(request())

        assert result.text == '{"a":1}'
        assert result.input_tokens == 120
        assert result.output_tokens == 40

    async def test_refusal_becomes_llm_failed(self):
        """안전 분류기가 거절하면 재시도해도 같은 결과다."""
        message = self.FakeMessage([self.Block("text", "")], stop_reason="refusal")

        with pytest.raises(AppError) as caught:
            await self.provider_with(message).complete(request())

        assert caught.value.code is ErrorCode.LLM_FAILED

    async def test_missing_usage_defaults_to_zero(self):
        message = self.FakeMessage([self.Block("text", "{}")])

        result = await self.provider_with(message).complete(request())

        assert result.input_tokens == 0 and result.output_tokens == 0

    async def test_transport_failure_becomes_llm_failed(self):
        provider = AnthropicProvider(model="m", api_key="k")

        class Exploding:
            class messages:
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("연결 실패")

        provider._client = Exploding()

        with pytest.raises(AppError) as caught:
            await provider.complete(request())

        assert caught.value.code is ErrorCode.LLM_FAILED

    def test_extract_text_handles_empty_content(self):
        assert _extract_text(self.FakeMessage([])) == ""
        assert _extract_text(self.FakeMessage(None)) == ""


class TestGoogleVisionTransport:
    def vision_response(self, width=1080, height=2340):
        return {
            "responses": [
                {
                    "fullTextAnnotation": {
                        "pages": [
                            {
                                "width": width,
                                "height": height,
                                "blocks": [
                                    {
                                        "paragraphs": [
                                            {
                                                "confidence": 0.97,
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 612, "y": 830},
                                                        {"x": 1008, "y": 830},
                                                        {"x": 1008, "y": 874},
                                                        {"x": 612, "y": 874},
                                                    ]
                                                },
                                                "words": [
                                                    {"symbols": [{"text": "안"}]},
                                                    {"symbols": [{"text": "녕"}]},
                                                ],
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                }
            ]
        }

    async def test_reads_multiple_images_in_order(self, monkeypatch):
        seen = mock_httpx(
            monkeypatch, lambda req: httpx.Response(200, json=self.vision_response())
        )
        engine = GoogleVisionOcrEngine(api_key="key")

        pages = await engine.read([png_bytes(), png_bytes(), png_bytes()])

        assert [page.image_index for page in pages] == [0, 1, 2]
        assert len(seen) == 3
        assert all(page.width == 1080 for page in pages)

    async def test_sends_the_api_key_and_korean_hint(self, monkeypatch):
        seen = mock_httpx(
            monkeypatch, lambda req: httpx.Response(200, json=self.vision_response())
        )

        await GoogleVisionOcrEngine(api_key="secret").read([png_bytes()])

        assert "key=secret" in str(seen[0].url)
        body = seen[0].content.decode()
        assert "DOCUMENT_TEXT_DETECTION" in body
        assert '"ko"' in body

    @pytest.mark.parametrize("status", [400, 403, 429, 500])
    async def test_error_statuses_become_ocr_failed(self, monkeypatch, status):
        mock_httpx(monkeypatch, lambda req: httpx.Response(status, json={}))

        with pytest.raises(AppError) as caught:
            await GoogleVisionOcrEngine(api_key="k").read([png_bytes()])

        assert caught.value.code is ErrorCode.OCR_FAILED

    async def test_connection_failure_becomes_ocr_failed(self, monkeypatch):
        def explode(req):
            raise httpx.ConnectTimeout("느림")

        mock_httpx(monkeypatch, explode)

        with pytest.raises(AppError) as caught:
            await GoogleVisionOcrEngine(api_key="k").read([png_bytes()])

        assert caught.value.code is ErrorCode.OCR_FAILED

    async def test_missing_page_size_is_a_failure(self, monkeypatch):
        """크기를 모르면 좌우 여백을 비교할 수 없다."""
        mock_httpx(
            monkeypatch,
            lambda req: httpx.Response(200, json=self.vision_response(width=0)),
        )

        with pytest.raises(AppError) as caught:
            await GoogleVisionOcrEngine(api_key="k").read([png_bytes()])

        assert caught.value.code is ErrorCode.OCR_FAILED

    async def test_concurrency_is_bounded(self, monkeypatch):
        """이미지를 동시에 보내되 상대 API를 몰아치지 않는다."""
        active = 0
        peak = 0

        def handler(req):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            active -= 1
            return httpx.Response(200, json=self.vision_response())

        mock_httpx(monkeypatch, handler)
        engine = GoogleVisionOcrEngine(api_key="k", max_concurrency=2)

        await engine.read([png_bytes()] * 6)

        assert peak <= 2
