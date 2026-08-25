"""텍스트 정규화.

OCR·Parser 명세 8장. 목적은 두 가지다.
LLM 입력 토큰을 줄이는 것, 의미 없는 변형을 없애 분석 품질을 높이는 것.
"""

import pytest

from app.ai.parser.normalize import is_system_message, normalize_text


class TestRepeatedCharacters:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("ㅋㅋㅋㅋㅋㅋㅋ", "ㅋㅋ"),
            ("ㅎㅎㅎㅎ", "ㅎㅎ"),
            ("!!!!!!", "!!"),
            ("......", ".."),
            ("ㅠㅠㅠㅠㅠㅠㅠㅠ", "ㅠㅠ"),
        ],
    )
    def test_shrinks_long_runs_to_two(self, raw, expected):
        assert normalize_text(raw) == expected

    def test_keeps_two_repeats_as_is(self):
        # 반복 여부 자체가 감정 강도 정보라 두 번까지는 남긴다
        assert normalize_text("ㅋㅋ") == "ㅋㅋ"

    def test_does_not_touch_normal_words(self):
        assert normalize_text("내일 시간 돼?") == "내일 시간 돼?"


class TestPlaceholders:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("https://example.com/a/b?c=1", "[링크]"),
            ("http://naver.com", "[링크]"),
            ("사진", "[사진]"),
            ("사진 3장", "[사진]"),
            ("이모티콘", "[이모티콘]"),
            ("동영상", "[동영상]"),
        ],
    )
    def test_replaces_media_and_links(self, raw, expected):
        assert normalize_text(raw) == expected

    def test_replaces_link_inside_a_sentence(self):
        assert normalize_text("이거 봐 https://example.com 재밌음") == "이거 봐 [링크] 재밌음"


class TestWhitespace:
    def test_collapses_runs_of_spaces(self):
        assert normalize_text("안녕    하세요") == "안녕 하세요"

    def test_strips_surrounding_whitespace(self):
        assert normalize_text("  안녕  ") == "안녕"

    def test_empty_input_stays_empty(self):
        assert normalize_text("   ") == ""


class TestSystemMessages:
    @pytest.mark.parametrize(
        "raw",
        [
            "삭제된 메시지입니다.",
            "김철수님이 들어왔습니다.",
            "김철수님이 나갔습니다.",
            "읽지 않음",
        ],
    )
    def test_detects_system_messages(self, raw):
        assert is_system_message(raw) is True

    @pytest.mark.parametrize("raw", ["내일 시간 돼?", "[사진]", "ㅋㅋ"])
    def test_ordinary_messages_are_not_system(self, raw):
        assert is_system_message(raw) is False
