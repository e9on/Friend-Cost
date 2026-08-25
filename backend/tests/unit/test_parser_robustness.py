"""실제 OCR이 줄 법한 지저분한 입력.

지금까지의 Parser 테스트는 우리가 만든 깔끔한 픽스처만 봤다. 실제 엔진은
블록 순서가 뒤섞이고, 말풍선을 여러 조각으로 쪼개고, 잡음을 섞어 보낸다.

여기서 막지 못하면 실제 키를 붙이는 날 처음 알게 된다.
"""

import pytest

from app.ai.parser import parse
from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage
from app.domain.value_object.enums import Speaker

WIDTH = 1080


def block(text: str, x: int, y: int, w: int = 300, h: int = 48, conf: float = 0.95):
    return OcrBlock(
        text=text, box=BoundingBox(x=x, y=y, w=w, h=h), confidence=conf
    )


def page(blocks, index: int = 0, width: int = WIDTH, height: int = 2340) -> OcrPage:
    return OcrPage(image_index=index, width=width, height=height, blocks=tuple(blocks))


def mine(text: str, y: int, w: int = 300):
    """오른쪽 끝에 붙는 내 말풍선."""
    return block(text, WIDTH - 40 - w, y, w)


def theirs(text: str, y: int, w: int = 300):
    """왼쪽에 붙는 상대 말풍선."""
    return block(text, 150, y, w)


class TestBlockOrder:
    def test_blocks_arriving_out_of_order_are_sorted(self):
        """OCR이 블록을 화면 순서대로 준다는 보장이 없다."""
        blocks = [
            theirs("셋째", 300),
            mine("첫째", 100),
            theirs("둘째", 200),
            mine("넷째", 400),
        ]

        convo = parse([page(blocks)], min_messages=1)

        assert [m.text for m in convo.messages] == ["첫째", "둘째", "셋째", "넷째"]

    def test_time_labels_arriving_first_still_attach(self):
        blocks = [
            block("오전 9:00", 600, 110, 96, 28),
            block("오전 9:05", 470, 210, 96, 28),
            mine("안녕", 100),
            theirs("어", 200),
        ]

        convo = parse([page(blocks)], min_messages=1)

        assert all(m.sent_at is not None for m in convo.messages)
        assert convo.messages[1].sent_at - convo.messages[0].sent_at == 300


class TestSplitBubbles:
    def test_a_multi_line_bubble_is_merged(self):
        """긴 메시지는 여러 줄 블록으로 쪼개져 온다."""
        blocks = [
            mine("오늘 진짜 힘들었는데", 100, 400),
            mine("그래도 네 덕분에 버텼어", 152, 400),
            theirs("고생했어", 260),
        ]

        convo = parse([page(blocks)], min_messages=1)

        assert len(convo.messages) == 2
        assert convo.messages[0].text == "오늘 진짜 힘들었는데 그래도 네 덕분에 버텼어"

    def test_bubbles_far_apart_are_not_merged(self):
        blocks = [
            mine("첫 메시지", 100),
            mine("한참 뒤 메시지", 400),
            theirs("응", 500),
        ]

        convo = parse([page(blocks)], min_messages=1)

        assert len(convo.messages) == 3

    def test_misaligned_lines_are_not_merged(self):
        """같은 화자라도 정렬이 다르면 다른 말풍선이다."""
        blocks = [
            mine("짧은 말", 100, 200),
            mine("훨씬 더 긴 말이라 왼쪽 끝이 다르다", 152, 600),
            theirs("응", 260),
        ]

        convo = parse([page(blocks)], min_messages=1)

        # 오른쪽 끝은 같지만 폭이 달라도 me 정렬 기준(오른쪽)은 일치한다
        assert len(convo.messages) >= 2


class TestNoisyInput:
    def test_low_confidence_blocks_are_dropped(self):
        blocks = [
            mine("또렷한 말", 100),
            theirs("흐릿한 말", 200, 300),
            theirs("또렷한 답", 300),
            mine("또 또렷", 400),
        ]
        blocks[1] = blocks[1].model_copy(update={"confidence": 0.3})

        convo = parse([page(blocks)], min_messages=1)

        assert "흐릿한 말" not in [m.text for m in convo.messages]

    def test_empty_text_blocks_are_ignored(self):
        blocks = [
            mine("안녕", 100),
            mine("   ", 200),
            theirs("어", 300),
        ]

        convo = parse([page(blocks)], min_messages=1)

        assert len(convo.messages) == 2

    def test_ui_chrome_near_the_edges_is_handled(self):
        """상단 헤더나 하단 입력창이 함께 잡힐 수 있다."""
        blocks = [
            block("김철수", 480, 20, 120, 30),  # 상단 가운데 = 대화 상대 이름
            mine("안녕", 200),
            theirs("어", 300),
            block("메시지 입력", 480, 2280, 120, 30),  # 하단 입력창
        ]

        convo = parse([page(blocks)], min_messages=1)

        # 가운데 정렬이라 메시지로 세지 않는다
        assert [m.text for m in convo.messages] == ["안녕", "어"]

    def test_very_long_text_survives_intact(self):
        # 반복 문자는 정규화가 접으므로(단어111 -> 단어11) 그런 조각이 없는
        # 문장을 쓴다
        words = ["오늘", "진짜", "힘들었는데", "그래도", "버텼어", "고마워"]
        long_text = " ".join(words[index % len(words)] for index in range(80))
        blocks = [mine(long_text, 100, 700), theirs("응", 300)]

        convo = parse([page(blocks)], min_messages=1)

        assert convo.messages[0].text == long_text


class TestResolutionVariance:
    @pytest.mark.parametrize("width", [720, 1080, 1284, 1440])
    def test_speaker_detection_works_at_any_resolution(self, width):
        edge = int(width * 0.04)
        bubble = int(width * 0.35)
        blocks = [
            block("내 말", width - edge - bubble, 100, bubble),
            block("상대 말", edge + int(width * 0.1), 200, bubble),
        ]

        convo = parse(
            [page(blocks, width=width)], min_messages=1
        )

        assert [m.speaker for m in convo.messages] == [Speaker.ME, Speaker.PEER]

    def test_pages_of_different_sizes_in_one_upload(self):
        """다른 기기에서 찍은 캡처가 섞일 수 있다."""
        narrow = page(
            [block("내 말", 720 - 40 - 250, 100, 250), block("상대", 110, 200, 250)],
            index=0,
            width=720,
        )
        wide = page(
            [block("내 말2", 1440 - 40 - 400, 100, 400), block("상대2", 190, 200, 400)],
            index=1,
            width=1440,
        )

        convo = parse([narrow, wide], min_messages=1)

        assert [m.speaker for m in convo.messages] == [
            Speaker.ME,
            Speaker.PEER,
            Speaker.ME,
            Speaker.PEER,
        ]


class TestFailureModes:
    def test_all_blocks_centered_is_reported(self):
        """말풍선이 잘려 좌우 정렬이 사라진 캡처."""
        blocks = [block(f"메시지 {i}", 400, 100 + i * 60, 280) for i in range(20)]

        with pytest.raises(AppError) as caught:
            parse([page(blocks)])

        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND

    def test_every_block_below_confidence_threshold(self):
        blocks = [
            mine("안녕", 100).model_copy(update={"confidence": 0.1}),
            theirs("어", 200).model_copy(update={"confidence": 0.1}),
        ]

        with pytest.raises(AppError) as caught:
            parse([page(blocks)], min_messages=1)

        assert caught.value.code is ErrorCode.NO_CONVERSATION_FOUND

    def test_empty_page_among_good_ones(self):
        """스크롤 끝의 빈 화면을 함께 올릴 수 있다."""
        good = page([mine("안녕", 100), theirs("어", 200)], index=0)
        empty = page([], index=1)

        convo = parse([good, empty], min_messages=1)

        assert len(convo.messages) == 2
        assert convo.meta.image_count == 2


class TestScale:
    def test_handles_a_large_upload_quickly(self):
        """10장 × 200블록이면 실제 상한에 가깝다."""
        pages = []
        for image_index in range(10):
            blocks = []
            for turn in range(100):
                y = 100 + turn * 60
                stamp_y = y + 16
                if turn % 2 == 0:
                    blocks.append(mine(f"메시지 {image_index}-{turn}", y))
                    blocks.append(block("오전 9:00", 600, stamp_y, 96, 28))
                else:
                    blocks.append(theirs(f"답장 {image_index}-{turn}", y))
                    blocks.append(block("오전 9:01", 470, stamp_y, 96, 28))
            pages.append(page(blocks, index=image_index, height=100 + 100 * 60 + 200))

        convo = parse(pages, min_messages=1, max_messages=120)

        assert convo.meta.sampled is True
        assert convo.meta.message_count == 120
        assert len({m.index for m in convo.messages}) == 120
