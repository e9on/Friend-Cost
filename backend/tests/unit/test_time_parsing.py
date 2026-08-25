"""캡처에 적힌 시각과 날짜 구분선을 읽는다.

OCR·Parser 명세 5장.
"""

from datetime import date

import pytest

from app.ai.parser.timeline import parse_date_line, parse_time_of_day


class TestParseTimeOfDay:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("오전 9:15", (9, 15)),
            ("오후 3:07", (15, 7)),
            ("오후 11:50", (23, 50)),
            ("21:15", (21, 15)),
            ("00:05", (0, 5)),
        ],
    )
    def test_reads_common_formats(self, raw, expected):
        assert parse_time_of_day(raw) == expected

    def test_noon_is_twelve_not_zero(self):
        assert parse_time_of_day("오후 12:30") == (12, 30)

    def test_midnight_is_zero_not_twelve(self):
        assert parse_time_of_day("오전 12:05") == (0, 5)

    @pytest.mark.parametrize("raw", ["안녕하세요", "", "3장", "25:99"])
    def test_returns_none_for_non_time_text(self, raw):
        assert parse_time_of_day(raw) is None


class TestParseDateLine:
    @pytest.mark.parametrize(
        "raw",
        [
            "2026년 8월 25일",
            "2026년 8월 25일 화요일",
            "2026. 8. 25.",
            "2026.08.25",
        ],
    )
    def test_reads_date_separator_formats(self, raw):
        assert parse_date_line(raw) == date(2026, 8, 25)

    @pytest.mark.parametrize("raw", ["오전 9:15", "안녕하세요", "8월 25일"])
    def test_returns_none_without_a_full_date(self, raw):
        assert parse_date_line(raw) is None
