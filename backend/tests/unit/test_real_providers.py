"""실제 Provider의 응답 변환.

네트워크를 타지 않고, 각 서비스가 돌려주는 모양을 우리 도메인 모델로
옮기는 부분만 검증한다. 여기가 틀리면 실제 키를 넣는 순간 조용히 잘못된
결과가 나온다.
"""

import pytest

from app.ai.provider.openai_compatible import (
    KNOWN_BASE_URLS,
    OpenAiCompatibleProvider,
    _to_response,
)
from app.application.service.pipeline import _build_llm_provider, _build_ocr_engine
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings
from app.infrastructure.ocr.google_vision import _to_box, _to_page


class TestOpenAiCompatibleResponse:
    def test_extracts_text_and_usage(self):
        body = {
            "choices": [{"message": {"role": "assistant", "content": '  {"a": 1}  '}}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 340},
        }

        result = _to_response(body)

        assert result.text == '{"a": 1}'
        assert result.input_tokens == 1200
        assert result.output_tokens == 340

    def test_missing_usage_defaults_to_zero(self):
        body = {"choices": [{"message": {"content": "{}"}}]}

        result = _to_response(body)

        assert result.input_tokens == 0 and result.output_tokens == 0

    def test_empty_choices_is_a_failure(self):
        with pytest.raises(AppError) as caught:
            _to_response({"choices": []})

        assert caught.value.code is ErrorCode.LLM_FAILED


class TestOpenAiCompatibleConstruction:
    @pytest.mark.parametrize("name", sorted(KNOWN_BASE_URLS))
    def test_known_providers_get_a_base_url(self, name):
        provider = OpenAiCompatibleProvider(name=name, model="m", api_key="k")

        assert provider.name == name

    def test_unknown_provider_needs_an_explicit_url(self):
        with pytest.raises(ValueError):
            OpenAiCompatibleProvider(name="처음보는곳", model="m", api_key="k")

    def test_explicit_url_wins(self):
        provider = OpenAiCompatibleProvider(
            name="처음보는곳", model="m", api_key="k", base_url="https://x.test/v1/"
        )

        assert provider._base_url == "https://x.test/v1"


class TestGoogleVisionBoundingBox:
    def test_converts_vertices_to_an_axis_aligned_box(self):
        bounding = {
            "vertices": [
                {"x": 612, "y": 830},
                {"x": 1008, "y": 830},
                {"x": 1008, "y": 874},
                {"x": 612, "y": 874},
            ]
        }

        box = _to_box(bounding)

        assert (box.x, box.y, box.w, box.h) == (612, 830, 396, 44)

    def test_rotated_text_becomes_its_outer_rectangle(self):
        """회전된 텍스트도 외접 사각형으로 받는다. 좌우 여백만 보면 되기 때문이다."""
        bounding = {
            "vertices": [
                {"x": 100, "y": 200},
                {"x": 300, "y": 180},
                {"x": 310, "y": 260},
                {"x": 110, "y": 280},
            ]
        }

        box = _to_box(bounding)

        assert (box.x, box.y) == (100, 180)
        assert (box.w, box.h) == (210, 100)

    def test_missing_vertices_is_skipped(self):
        assert _to_box(None) is None
        assert _to_box({"vertices": []}) is None

    def test_zero_area_box_is_skipped(self):
        bounding = {"vertices": [{"x": 5, "y": 5}, {"x": 5, "y": 5}]}

        assert _to_box(bounding) is None


class TestGoogleVisionPage:
    def response(self, *, width=1080, height=2340, paragraphs=None):
        return {
            "responses": [
                {
                    "fullTextAnnotation": {
                        "pages": [
                            {
                                "width": width,
                                "height": height,
                                "blocks": [{"paragraphs": paragraphs or []}],
                            }
                        ]
                    }
                }
            ]
        }

    def paragraph(self, text: str, x: int, w: int, y: int = 100):
        symbols = []
        for index, char in enumerate(text):
            symbol = {"text": char}
            if index == len(text) - 1:
                symbol["property"] = {"detectedBreak": {"type": "LINE_BREAK"}}
            symbols.append(symbol)
        return {
            "confidence": 0.97,
            "boundingBox": {
                "vertices": [
                    {"x": x, "y": y},
                    {"x": x + w, "y": y},
                    {"x": x + w, "y": y + 44},
                    {"x": x, "y": y + 44},
                ]
            },
            "words": [{"symbols": [symbol]} for symbol in symbols],
        }

    def test_reads_size_and_blocks(self):
        body = self.response(paragraphs=[self.paragraph("안녕", 612, 396)])

        page = _to_page(0, body)

        assert (page.width, page.height) == (1080, 2340)
        assert len(page.blocks) == 1
        assert page.blocks[0].text == "안녕"
        assert page.blocks[0].box.x == 612

    def test_page_without_size_is_a_failure(self):
        """크기를 모르면 좌우 여백을 비교할 수 없다. 화자 판별의 전제가 깨진다."""
        body = self.response(width=0, paragraphs=[self.paragraph("안녕", 10, 50)])

        with pytest.raises(AppError) as caught:
            _to_page(0, body)

        assert caught.value.code is ErrorCode.OCR_FAILED

    def test_no_text_found_yields_an_empty_page(self):
        page = _to_page(0, {"responses": [{}]})

        assert page.blocks == ()

    def test_api_error_is_reported(self):
        with pytest.raises(AppError) as caught:
            _to_page(0, {"responses": [{"error": {"message": "quota"}}]})

        assert caught.value.code is ErrorCode.OCR_FAILED

    def test_empty_response_is_reported(self):
        with pytest.raises(AppError) as caught:
            _to_page(0, {"responses": []})

        assert caught.value.code is ErrorCode.OCR_FAILED

    def test_word_breaks_become_spaces(self):
        paragraph = {
            "confidence": 0.9,
            "boundingBox": {
                "vertices": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 40},
                    {"x": 0, "y": 40},
                ]
            },
            "words": [
                {
                    "symbols": [
                        {"text": "안", "property": {"detectedBreak": {"type": "SPACE"}}}
                    ]
                },
                {"symbols": [{"text": "녕"}]},
            ],
        }
        body = self.response(paragraphs=[paragraph])

        page = _to_page(0, body)

        assert page.blocks[0].text == "안 녕"


class TestProviderSelection:
    def test_stub_is_the_default(self):
        provider = _build_llm_provider(Settings())

        assert provider.name == "stub"

    def test_openai_compatible_provider_needs_a_key(self):
        with pytest.raises(ValueError):
            _build_llm_provider(Settings(llm_provider="groq", llm_api_key=None))

    def test_groq_is_built_from_settings(self):
        provider = _build_llm_provider(
            Settings(llm_provider="groq", llm_api_key="key", llm_model="llama-3.3-70b-versatile")
        )

        assert provider.name == "groq"
        assert provider.model == "llama-3.3-70b-versatile"

    def test_google_vision_needs_a_key(self):
        with pytest.raises(ValueError):
            _build_ocr_engine(Settings(ocr_engine="google_vision", ocr_api_key=None))

    def test_google_vision_is_built_from_settings(self):
        engine = _build_ocr_engine(
            Settings(ocr_engine="google_vision", ocr_api_key="key")
        )

        assert engine.name == "google_vision"
