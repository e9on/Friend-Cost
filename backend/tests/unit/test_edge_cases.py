"""자주 지나치는 경계 조건.

정상 흐름에서는 닿지 않지만, 실제 데이터는 언제나 예상 밖이다.
"""

import pytest

from app.ai.parser import parse
from app.ai.parser.normalize import normalize_text
from app.ai.parser.speaker import BlockRole
from app.ai.parser.timeline import parse_date_line, parse_time_of_day
from app.algorithm.calculator.behavior import reply_seconds, split_sessions
from app.algorithm.rule import constants
from app.common.errors import AppError, ErrorCode
from app.domain.value_object.enums import Speaker
from app.infrastructure.storage.memory import InMemoryBlobStore
from tests.builders import BASE_TS, conversation, msg
from tests.fixtures.kakao import ScreenBuilder


class TestSpeakerRole:
    def test_center_maps_to_no_speaker(self):
        # 날짜 구분선과 시스템 안내는 화자가 없다
        assert BlockRole.CENTER.to_speaker() is None

    def test_sides_map_to_speakers(self):
        assert BlockRole.ME.to_speaker() is Speaker.ME
        assert BlockRole.PEER.to_speaker() is Speaker.PEER


class TestTimeParsingEdges:
    def test_impossible_minute_is_rejected(self):
        assert parse_time_of_day("9:75") is None

    def test_impossible_hour_in_twelve_hour_format_is_rejected(self):
        assert parse_time_of_day("오후 13:30") is None
        assert parse_time_of_day("오전 0:30") is None

    def test_impossible_date_is_rejected(self):
        # 2월 30일 같은 날짜가 OCR 오인식으로 나올 수 있다
        assert parse_date_line("2026년 2월 30일") is None
        assert parse_date_line("2026년 13월 1일") is None

    def test_boundary_times_are_accepted(self):
        assert parse_time_of_day("23:59") == (23, 59)
        assert parse_time_of_day("0:00") == (0, 0)


class TestNormalizeEdges:
    def test_file_attachment_becomes_a_placeholder(self):
        assert normalize_text("파일: 계약서.pdf") == "[파일]"
        assert normalize_text("파일：사진첩.zip") == "[파일]"

    def test_photo_count_variants(self):
        assert normalize_text("사진 12장") == "[사진]"
        assert normalize_text("사진") == "[사진]"

    def test_a_word_containing_photo_is_not_replaced(self):
        # "사진관 앞에서 보자" 를 [사진] 으로 바꾸면 대화가 망가진다
        assert normalize_text("사진관 앞에서 보자") == "사진관 앞에서 보자"


class TestBehaviorEdges:
    def test_sessions_of_an_empty_conversation(self):
        assert split_sessions(conversation([])) == ()

    def test_reply_gaps_are_ignored_when_time_goes_backwards(self):
        """이미지 순서를 뒤섞어 올리면 시각이 역행할 수 있다."""
        convo = conversation(
            [
                msg(0, Speaker.ME, BASE_TS + 600),
                msg(1, Speaker.PEER, BASE_TS),
                msg(2, Speaker.ME, BASE_TS + 60),
                msg(3, Speaker.PEER, BASE_TS + 120),
                msg(4, Speaker.ME, BASE_TS + 180),
                msg(5, Speaker.PEER, BASE_TS + 240),
            ]
        )

        result = reply_seconds(convo)

        # 음수 간격은 표본에 넣지 않는다
        assert result.peer is None or result.peer >= 0
        assert result.me is None or result.me >= 0

    def test_single_speaker_has_no_reply_samples(self):
        convo = conversation([msg(i, Speaker.ME, BASE_TS + i * 60) for i in range(10)])

        result = reply_seconds(convo)

        assert result.me is None and result.peer is None


class TestWeightGuard:
    def test_weight_sum_check_rejects_broken_values(self):
        """가중치 합이 1.00이 아니면 점수 범위가 깨진다."""
        original = constants.W_INTIMACY_TONE
        try:
            constants.W_INTIMACY_TONE = 0.9
            with pytest.raises(ValueError, match="가중치 합"):
                constants._assert_weights_sum_to_one()
        finally:
            constants.W_INTIMACY_TONE = original

        constants._assert_weights_sum_to_one()


class TestBlobStoreEdges:
    def test_reading_a_missing_blob_reports_expiry(self):
        store = InMemoryBlobStore()

        with pytest.raises(AppError) as caught:
            store.get("없는-키")

        assert caught.value.code is ErrorCode.JOB_EXPIRED

    def test_keys_do_not_contain_the_original_filename(self):
        # 원본 파일명은 저장하지 않는다. 기준 명세 5장
        store = InMemoryBlobStore()

        key = store.put("job-1", 0, b"data")

        assert "job-1" in key
        assert len(key.split("/")[-1]) == 32  # uuid hex

    def test_delete_all_is_idempotent(self):
        store = InMemoryBlobStore()
        store.put("job-1", 0, b"data")

        store.delete_all("job-1")
        store.delete_all("job-1")

        assert store.list_keys("job-1") == []


class TestParserEdges:
    def test_pages_out_of_order_are_sorted_by_index(self):
        """업로드 순서가 곧 시간 순서다. 인덱스로 정렬한다."""
        second = (
            ScreenBuilder(image_index=1)
            .me("나중 화면", at="오전 10:00")
            .peer("응", at="오전 10:01")
            .build()
        )
        first = (
            ScreenBuilder(image_index=0)
            .center("2026년 8월 25일")
            .me("먼저 화면", at="오전 9:00")
            .peer("어", at="오전 9:01")
            .build()
        )

        convo = parse([second, first], min_messages=1)

        assert convo.messages[0].text == "먼저 화면"
        assert convo.messages[0].image_index == 0

    def test_page_with_only_a_date_line_yields_nothing(self):
        page = ScreenBuilder().center("2026년 8월 25일").build()

        with pytest.raises(AppError) as caught:
            parse([page], min_messages=1)

        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND

    def test_sampling_falls_back_when_the_limit_is_tiny(self):
        """상한이 앞뒤 몫보다 작아도 터지지 않아야 한다."""
        screen = ScreenBuilder().center("2026년 8월 25일")
        for turn in range(40):
            stamp = f"오전 9:{turn:02d}"
            if turn % 2 == 0:
                screen.me(f"메시지 {turn}", at=stamp)
            else:
                screen.peer(f"메시지 {turn}", at=stamp)

        convo = parse([screen.build()], min_messages=1, max_messages=10)

        assert convo.meta.sampled is True
        assert convo.meta.message_count == 10
