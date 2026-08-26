"""OCR 결과를 `ConversationData` 로 바꾸는 Parser 전체.

OCR·Parser 명세 4~11장.
"""

import pytest

from app.ai.parser import NAME_LABEL_MIN_REPEATS, parse
from app.common.errors import AppError, ErrorCode
from app.domain.value_object.enums import Speaker, TimeSource
from tests.fixtures.kakao import ScreenBuilder, message_text, simple_chat


class TestSpeakerAssignment:
    def test_assigns_speakers_from_bubble_position(self):
        page = (
            ScreenBuilder()
            .center("2026년 8월 25일 화요일")
            .me("내가 보낸 말", at="오후 3:07")
            .peer("상대가 보낸 말", at="오후 3:10")
            .build()
        )

        convo = parse([page], min_messages=1)

        assert [m.speaker for m in convo.messages] == [Speaker.ME, Speaker.PEER]
        assert [m.text for m in convo.messages] == ["내가 보낸 말", "상대가 보낸 말"]

    def test_time_label_is_not_mistaken_for_a_message(self):
        page = (
            ScreenBuilder().me("안녕", at="오후 3:07").peer("어 왔어", at="오후 3:08").build()
        )

        convo = parse([page], min_messages=1)

        assert [m.text for m in convo.messages] == ["안녕", "어 왔어"]

    def test_long_bubble_is_still_attributed_correctly(self):
        long_text = "이건 아주 긴 메시지라서 화면 폭을 거의 다 차지한다 그래도 내 것이다"
        page = (
            ScreenBuilder().me(long_text, at="오후 3:07").peer("그렇구나", at="오후 3:08").build()
        )

        convo = parse([page], min_messages=1)

        assert convo.messages[0].speaker is Speaker.ME
        assert convo.messages[0].text == long_text


class TestTimeRestoration:
    def test_uses_the_date_separator_as_anchor(self):
        page = (
            ScreenBuilder()
            .center("2026년 8월 25일 화요일")
            .me("첫 메시지", at="오전 9:00")
            .peer("두번째", at="오전 9:05")
            .build()
        )

        convo = parse([page], min_messages=1)

        first, second = convo.messages
        assert first.time_source is TimeSource.EXPLICIT
        assert second.sent_at - first.sent_at == 300

    def test_rolls_over_to_next_day_when_clock_goes_backwards(self):
        page = (
            ScreenBuilder()
            .center("2026년 8월 25일")
            .me("자기 전에", at="오후 11:50")
            .peer("자정 넘어서", at="오전 12:15")
            .build()
        )

        convo = parse([page], min_messages=1)

        late, past_midnight = convo.messages
        assert past_midnight.sent_at - late.sent_at == 25 * 60
        assert past_midnight.time_source is TimeSource.INFERRED

    def test_builds_a_virtual_timeline_without_a_date_separator(self):
        page = (
            ScreenBuilder()
            .me("날짜 없음", at="오전 9:00")
            .peer("그래도 간격은 안다", at="오전 9:30")
            .build()
        )

        convo = parse([page], min_messages=1)

        first, second = convo.messages
        assert second.sent_at - first.sent_at == 1800
        assert all(m.time_source is TimeSource.INFERRED for m in convo.messages)

    def test_message_without_a_time_label_has_no_timestamp(self):
        page = (
            ScreenBuilder()
            .center("2026년 8월 25일")
            .me("시각 있음", at="오전 9:00")
            .peer("시각 없음")
            .build()
        )

        convo = parse([page], min_messages=1)

        assert convo.messages[1].sent_at is None
        assert convo.messages[1].time_source is TimeSource.UNKNOWN
        assert convo.meta.time_coverage == pytest.approx(0.5)


class TestNormalizationAndDropping:
    def test_drops_system_messages(self):
        page = (
            ScreenBuilder()
            .me("안녕", at="오전 9:00")
            .center("김철수님이 나갔습니다.")
            .peer("그래", at="오전 9:01")
            .build()
        )

        convo = parse([page], min_messages=1)

        assert [m.text for m in convo.messages] == ["안녕", "그래"]
        assert convo.meta.dropped_count >= 1

    def test_normalizes_message_text(self):
        page = (
            ScreenBuilder().me("ㅋㅋㅋㅋㅋㅋ", at="오전 9:00").peer("왜", at="오전 9:01").build()
        )

        convo = parse([page], min_messages=1)

        assert convo.messages[0].text == "ㅋㅋ"

    def test_drops_low_confidence_blocks(self):
        page = (
            ScreenBuilder()
            .me("흐릿하게 찍힌 말", at="오전 9:00")
            .peer("또렷한 말", at="오전 9:01")
            .me("이것도 또렷", at="오전 9:02")
            .build()
        )
        blocks = list(page.blocks)
        noisy = blocks[0].model_copy(update={"confidence": 0.2})
        page = page.model_copy(update={"blocks": (noisy, *blocks[1:])})

        convo = parse([page], min_messages=1)

        assert "흐릿하게 찍힌 말" not in [m.text for m in convo.messages]
        assert len(convo.messages) == 2


class TestGroupChatDetection:
    """이름은 **반복될 때** 이름으로 본다.

    한 번 나타난 것을 이름으로 치면 "나 지금 회사야" 같은 평범한 메시지가
    걸려 정상 1:1 대화가 거부된다. 실측에서 실제로 그랬다.
    `OCR-Parser-명세.md` 7장.
    """

    def test_rejects_a_chat_with_repeated_name_labels(self):
        screen = ScreenBuilder().center("2026년 8월 25일")
        for turn in range(NAME_LABEL_MIN_REPEATS):
            screen.peer_name("김철수")
            screen.peer(f"안녕 {turn}", at=f"오전 9:0{turn}")
            screen.peer_name("이영희")
            screen.peer(f"나도 안녕 {turn}", at=f"오전 9:1{turn}")

        with pytest.raises(AppError) as caught:
            parse([screen.build()], min_messages=1)

        assert caught.value.code is ErrorCode.GROUP_CHAT_DETECTED

    def test_알려진_한계_각자_한_번씩만_말한_단체방은_놓친다(self):
        """오탐과 미탐 중 오탐을 더 나쁘게 본 결과다.

        짧은 답장은 실제 대화에서 매우 흔하므로, 한 번 나타난 짧은 텍스트를
        이름으로 치면 정상 이용자가 서비스를 거부당한다. 이 테스트는 그
        대가를 **눈에 보이게** 남겨둔다. 나중에 더 나은 단서를 찾으면
        이 테스트가 먼저 깨진다.
        """
        screen = ScreenBuilder().center("2026년 8월 25일")
        screen.peer_name("김철수")
        screen.peer("안녕", at="오전 9:00")
        screen.peer_name("이영희")
        screen.peer("나도 안녕", at="오전 9:01")
        screen.me("둘 다 안녕", at="오전 9:02")

        convo = parse([screen.build()], min_messages=1)

        assert convo.meta.message_count > 0, "지금은 단체방으로 보지 않는다"

    def test_single_name_label_is_not_a_group_chat(self):
        screen = ScreenBuilder().center("2026년 8월 25일")
        screen.peer_name("김철수")
        screen.peer("안녕", at="오전 9:00")
        screen.me("어", at="오전 9:01")

        convo = parse([screen.build()], min_messages=1)

        assert len(convo.messages) >= 2


class TestCrossImageDedupe:
    def test_removes_the_overlapping_tail_of_the_previous_image(self):
        first = simple_chat(turns=10, image_index=0, start_hour=9)

        overlap = ScreenBuilder(image_index=1).center("2026년 8월 25일 화요일")
        # 앞 이미지의 마지막 네 개를 그대로 반복한 뒤 새 내용을 잇는다
        for turn in (6, 7, 8, 9):
            stamp = f"오전 9:{turn * 5:02d}"
            repeated = message_text(0, turn)
            if turn % 2 == 0:
                overlap.me(repeated, at=stamp)
            else:
                overlap.peer(repeated, at=stamp)
        overlap.me("새로운 내용", at="오전 10:00")

        convo = parse([first, overlap.build()], min_messages=1)

        texts = [m.text for m in convo.messages]
        assert texts.count(message_text(0, 9)) == 1
        assert texts[-1] == "새로운 내용"

    def test_keeps_short_coincidental_repeats(self):
        first = (
            ScreenBuilder(image_index=0)
            .peer("밥 먹었어?", at="오전 9:00")
            .me("ㅇㅇ", at="오전 9:01")
            .build()
        )
        second = (
            ScreenBuilder(image_index=1)
            .peer("잘 들어갔어?", at="오전 9:30")
            .me("ㅇㅇ", at="오전 9:31")
            .build()
        )

        convo = parse([first, second], min_messages=1)

        # 연속 3개 이상 일치해야 중복으로 본다. 'ㅇㅇ' 하나로는 지우지 않는다
        assert [m.text for m in convo.messages].count("ㅇㅇ") == 2


class TestAnchorCarriesAcrossImages:
    def test_date_anchor_from_the_first_image_applies_to_later_ones(self):
        """스크롤 캡처는 하나의 대화다.

        날짜 구분선은 보통 첫 화면에만 찍힌다. 이미지가 바뀔 때 앵커를
        초기화하면 뒤 이미지가 가상 기준일로 되돌아가 시간이 거꾸로 흐른다.
        """
        first = (
            ScreenBuilder(image_index=0)
            .center("2026년 8월 25일 화요일")
            .me("첫 화면", at="오전 9:00")
            .peer("응", at="오전 9:05")
            .build()
        )
        second = (
            ScreenBuilder(image_index=1)
            .me("두번째 화면", at="오전 9:10")
            .peer("그래", at="오전 9:15")
            .build()
        )

        convo = parse([first, second], min_messages=1)

        stamps = [m.sent_at for m in convo.messages]
        assert all(a <= b for a, b in zip(stamps, stamps[1:])), "시간이 거꾸로 흘렀다"
        assert convo.meta.span_seconds == 15 * 60

    def test_span_stays_sane_across_many_images(self):
        pages = [simple_chat(turns=10, image_index=i, start_hour=9 + i) for i in range(4)]

        convo = parse(pages, min_messages=1)

        # 네 화면이 몇 시간짜리 대화여야지 몇 년짜리가 되면 안 된다
        assert convo.meta.span_seconds is not None
        assert convo.meta.span_seconds < 2 * 24 * 3600

    def test_rollover_carries_across_an_image_boundary(self):
        first = (
            ScreenBuilder(image_index=0)
            .center("2026년 8월 25일")
            .me("자기 전", at="오후 11:50")
            .build()
        )
        second = ScreenBuilder(image_index=1).peer("자정 지나서", at="오전 12:10").build()

        convo = parse([first, second], min_messages=1)

        assert convo.messages[1].sent_at - convo.messages[0].sent_at == 20 * 60


class TestSampling:
    def test_keeps_everything_below_the_limit(self):
        convo = parse([simple_chat(turns=20)], min_messages=1, max_messages=120)

        assert convo.meta.sampled is False
        assert convo.meta.message_count == 20

    def test_samples_head_middle_and_tail_when_too_long(self):
        pages = [simple_chat(turns=60, image_index=i, start_hour=6 + i * 3) for i in range(3)]

        convo = parse(pages, min_messages=1, max_messages=120)

        assert convo.meta.sampled is True
        assert convo.meta.message_count == 120
        assert [m.index for m in convo.messages] == list(range(120))


class TestMinimumRequirements:
    def test_rejects_a_conversation_that_is_too_short(self):
        page = simple_chat(turns=4)

        with pytest.raises(AppError) as caught:
            parse([page])

        assert caught.value.code is ErrorCode.TOO_FEW_MESSAGES

    def test_rejects_when_only_one_side_speaks(self):
        screen = ScreenBuilder().center("2026년 8월 25일")
        for turn in range(20):
            screen.me(f"혼잣말 {turn}", at=f"오전 9:{turn:02d}")

        with pytest.raises(AppError) as caught:
            parse([screen.build()])

        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND

    def test_rejects_when_nothing_was_recognised(self):
        page = ScreenBuilder().build()

        with pytest.raises(AppError) as caught:
            parse([page])

        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND


class TestMeta:
    def test_reports_counts_and_span(self):
        convo = parse([simple_chat(turns=20)], min_messages=1)

        assert convo.meta.image_count == 1
        assert convo.meta.message_count == 20
        assert convo.meta.time_coverage == pytest.approx(1.0)
        assert convo.meta.span_seconds == 19 * 5 * 60

    def test_indexes_are_sequential_after_filtering(self):
        page = (
            ScreenBuilder()
            .me("하나", at="오전 9:00")
            .center("삭제된 메시지입니다.")
            .peer("둘", at="오전 9:01")
            .build()
        )

        convo = parse([page], min_messages=1)

        assert [m.index for m in convo.messages] == [0, 1]
