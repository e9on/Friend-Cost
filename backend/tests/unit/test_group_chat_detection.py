"""단체방 감지.

픽스처는 **실제 OCR 출력**이다. 합성 카카오톡 캡처를 `render_kakao.py` 로
그린 뒤 RapidOCR(한국어 PP-OCRv4)에 넣어 나온 `OcrPage` 를 그대로 저장했다.
오인식과 잡음이 함께 들어 있어서, 손으로 지어낸 블록으로는 드러나지 않는
문제가 여기서는 드러난다.

- `direct_1to1.json` — 1:1 대화. 발신자 이름이 **없다.** 잡히면 오탐이다.
- `group_chat.json` — 단체방. 김민지·박준서 등이 붙어 있다. 놓치면 미탐이다.

처음 구현은 폰트 높이로 갈랐는데 실측에서 무너졌다. "나 지금 회사야" 같은
평범한 메시지가 발신자 이름으로 오인돼 정상 대화가 거부됐다.
`OCR-Parser-명세.md` 7장.
"""

import json
from pathlib import Path

import pytest

from app.ai.parser import NAME_LABEL_MIN_REPEATS, parse
from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage
from tests.fixtures.kakao import ScreenBuilder

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ocr"


def load(name: str) -> tuple[OcrPage, ...]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return tuple(OcrPage.model_validate(item) for item in raw)


class TestOneToOneIsNotRejected:
    """정상 대화를 거부하지 않는다. 거부는 사용자에게 서비스 실패로 보인다."""

    def test_짧은_메시지가_있어도_단체방으로_보지_않는다(self):
        pages = load("direct_1to1.json")

        convo = parse(pages, min_messages=1)

        assert convo.meta.message_count > 0

    def test_실제로_짧은_메시지가_들어_있다(self):
        # 이 픽스처가 문제를 재현하지 못하면 위 테스트는 아무것도 지키지 않는다.
        # "나지금회사야"(6자)처럼 이름 길이 안에 드는 본문이 있어야 한다
        from app.ai.parser import NAME_LABEL_MAX_LEN

        texts = [
            block.text.strip()
            for page in load("direct_1to1.json")
            for block in page.blocks
        ]
        short = [t for t in texts if 2 <= len(t) <= NAME_LABEL_MAX_LEN]

        assert len(short) >= 5, f"짧은 블록이 {len(short)}개뿐이라 재현되지 않는다"


class TestGroupChatIsRejected:
    def test_발신자_이름이_반복되면_거부한다(self):
        pages = load("group_chat.json")

        with pytest.raises(AppError) as caught:
            parse(pages, min_messages=1)

        assert caught.value.code is ErrorCode.GROUP_CHAT_DETECTED

    def test_이름이_여러_이미지에_흩어져_있다(self):
        # 이미지 한 장 안에서만 세면 3회를 채우지 못해 놓친다.
        # 이 픽스처가 그 조건을 만족하는지 확인한다
        pages = load("group_chat.json")
        appearances: dict[str, set[int]] = {}
        for page in pages:
            for block in page.blocks:
                text = block.text.strip()
                appearances.setdefault(text, set()).add(page.image_index)

        spread = [t for t, imgs in appearances.items() if len(imgs) >= 2]
        assert spread, "여러 장에 걸쳐 반복되는 텍스트가 없다"


class TestOcrMisreadsOfOneNameAreNotTwoPeople:
    """한 사람의 이름 라벨을 OCR 이 다르게 읽어도 단체방이 아니다.

    2026-08-27 실제 캡처에서 정상 1:1 대화가 거부됐다. 상대 닉네임
    `하트를 든 라이언` 이 어두운 배경 + JPEG 압축 때문에 매번 다르게
    읽혔고, 두 변형이 각각 3회를 넘겨 서로 다른 이름 2개가 됐다.

    아래 텍스트는 그 캡처에서 실제로 나온 것이다. 대화 본문이 아니라
    닉네임 라벨의 오인식이므로 픽스처로 남겨도 사생활이 남지 않는다.
    `OCR-Parser-명세.md` 7.3.
    """

    # 같은 라벨 하나가 이렇게 갈라졌다. 유사도 0.923
    VARIANTS = ("공어고글를렁을", "어고글를렁을")

    def _screens(self):
        screens = []
        for image_index in range(2):
            screen = ScreenBuilder(image_index=image_index)
            for turn in range(NAME_LABEL_MIN_REPEATS):
                for variant in self.VARIANTS:
                    screen.peer_name(variant)
                    screen.peer(f"상대 메시지 {image_index}{turn}", at="오전 9:00")
                    screen.me(f"내 메시지 {image_index}{turn}", at="오전 9:01")
            screens.append(screen.build())
        return screens

    def test_같은_이름의_오인식_변형은_한_사람으로_본다(self):
        convo = parse(self._screens(), min_messages=1)

        assert convo.meta.message_count > 0

    def test_변형들이_실제로_반복_기준을_넘는다(self):
        # 이 조건이 깨지면 위 테스트는 아무것도 지키지 않는다
        from collections import Counter

        from app.ai.parser import _name_candidates, MIN_BLOCK_CONFIDENCE

        counts: Counter = Counter()
        for page in self._screens():
            blocks = [b for b in page.blocks if b.confidence >= MIN_BLOCK_CONFIDENCE]
            counts.update(b.text.strip() for b in _name_candidates(blocks, page.width))

        for variant in self.VARIANTS:
            assert counts[variant] >= NAME_LABEL_MIN_REPEATS, (
                f"{variant!r} 가 {counts[variant]}회뿐이라 재현되지 않는다"
            )

    def test_정말로_다른_이름이면_여전히_거부한다(self):
        """합치기가 단체방 감지를 무력화하지 않는지 확인한다."""
        screen = ScreenBuilder()
        for turn in range(NAME_LABEL_MIN_REPEATS):
            screen.peer_name("김민지")
            screen.peer(f"안녕 {turn}", at="오전 9:00")
            screen.peer_name("박준서")
            screen.peer(f"나도 {turn}", at="오전 9:01")

        with pytest.raises(AppError) as caught:
            parse([screen.build()], min_messages=1)

        assert caught.value.code is ErrorCode.GROUP_CHAT_DETECTED


class TestIndentIsAQualifyingCondition:
    """이름 라벨은 자기가 붙은 말풍선보다 왼쪽으로 튀어나온다.

    본문끼리는 같은 말풍선 기준선을 쓰므로 x 가 같다. 짧은 메시지 다음에 긴
    메시지가 와도 마찬가지다. 그래서 들여쓰기를 **자격 요건**으로 두면
    "나 지금 회사야" 류 오탐이 세기 전에 잘린다.

    좌표는 2026-08-27 실제 캡처(폭 720)에서 잰 값이다. 이름 라벨 x=99,
    말풍선 본문 x=118. `OCR-Parser-명세.md` 7.4.
    """

    WIDTH = 720
    LABEL_X = 99      # 말풍선 바깥 기준선
    TEXT_X = 118      # 말풍선 안쪽

    def _page(self, rows):
        """(x, y, w, h, text) 목록을 한 화면으로 만든다."""
        return OcrPage(
            image_index=0,
            width=self.WIDTH,
            height=3000,
            blocks=tuple(
                OcrBlock(
                    text=text,
                    box=BoundingBox(x=x, y=y, w=w, h=h),
                    confidence=0.7,
                )
                for x, y, w, h, text in rows
            ),
        )

    def test_본문끼리는_x가_같으므로_이름_후보가_아니다(self):
        """짧은 본문 아래에 더 큰 본문이 와도 이름이 아니다."""
        from app.ai.parser import _name_candidates

        rows = []
        y = 100
        for turn in range(NAME_LABEL_MIN_REPEATS + 1):
            rows.append((self.TEXT_X, y, 120, 31, "웬일이야"))
            rows.append((self.TEXT_X, y + 36, 400, 47, f"먼저 연락을 다 하고 {turn}"))
            y += 200
        page = self._page(rows)

        assert _name_candidates(page.blocks, page.width) == []

    def test_말풍선보다_왼쪽인_라벨은_후보가_된다(self):
        from app.ai.parser import _name_candidates

        page = self._page(
            [
                (self.LABEL_X, 100, 165, 31, "김민지"),
                (self.TEXT_X, 136, 400, 47, "안녕 오늘 저녁에 볼까"),
            ]
        )

        found = _name_candidates(page.blocks, page.width)

        assert [b.text for b in found] == ["김민지"]

    def test_튀어나오지_않으면_아무리_반복해도_이름이_아니다(self):
        """자격 요건은 순위가 아니다. 반복으로 뒤집히지 않는다."""
        rows = []
        y = 100
        for turn in range(NAME_LABEL_MIN_REPEATS * 2):
            rows.append((self.TEXT_X, y, 120, 31, "웬일이야"))
            rows.append((self.TEXT_X, y + 36, 400, 47, f"먼저 연락을 다 하고 {turn}"))
            rows.append((self.TEXT_X, y + 100, 120, 31, "그래 알겠어"))
            rows.append((self.TEXT_X, y + 136, 400, 47, f"그럼 그때 보자 {turn}"))
            # 화자가 둘이어야 대화로 인정된다
            rows.append((520, y + 200, 160, 47, f"응 좋아 {turn}"))
            y += 300

        convo = parse([self._page(rows)], min_messages=1)

        assert convo.meta.message_count > 0


class TestNameLabelsAreDropped:
    """이름 라벨은 메시지가 아니다. 감지에 쓴 뒤 버린다.

    2026-08-27 실측에서 캡처 5장의 메시지 120개 중 21개가 이름 라벨이었다.
    전체의 17.5%가 상대방이 보낸 적 없는 메시지로 세어졌고, 연락 균형도와
    기여 격차가 그만큼 상대방 쪽으로 기울었다.

    지표만의 문제가 아니다. 라벨이 메시지에 섞여 LLM 으로 전송된다. 닉네임은
    상대방을 특정할 수 있는 정보이고, 처리방침의 처리 항목에 없다. 고지하지
    않은 항목을 국외로 보내는 셈이다.

    `OCR-Parser-명세.md` 7.1.
    """

    WIDTH = 720
    LABEL_X = 99
    TEXT_X = 118

    def _page(self, rows, image_index=0):
        return OcrPage(
            image_index=image_index,
            width=self.WIDTH,
            height=4000,
            blocks=tuple(
                OcrBlock(
                    text=text,
                    box=BoundingBox(x=x, y=y, w=w, h=h),
                    confidence=0.7,
                )
                for x, y, w, h, text in rows
            ),
        )

    def _one_to_one_with_label(self):
        """이름 라벨이 붙은 1:1 화면. 라벨 6개, 진짜 메시지 12개."""
        rows = []
        y = 100
        for turn in range(6):
            rows.append((self.LABEL_X, y, 165, 31, "하트를든라이언"))
            rows.append((self.TEXT_X, y + 36, 400, 47, f"상대 메시지 {turn}"))
            rows.append((520, y + 120, 160, 47, f"내 메시지 {turn}"))
            y += 220
        return self._page(rows)

    def test_이름_라벨이_메시지로_세어지지_않는다(self):
        convo = parse([self._one_to_one_with_label()], min_messages=1)

        texts = [m.text for m in convo.messages]
        assert not any("라이언" in t for t in texts), f"라벨이 메시지에 남았다: {texts}"

    def test_진짜_메시지는_그대로_남는다(self):
        convo = parse([self._one_to_one_with_label()], min_messages=1)

        assert convo.meta.message_count == 12

    def test_버린_라벨은_droppedCount_에_잡힌다(self):
        convo = parse([self._one_to_one_with_label()], min_messages=1)

        assert convo.meta.dropped_count >= 6

    def test_아래_말풍선이_없는_라벨도_버린다(self):
        """화면 끝에 걸린 라벨은 후보 조건을 못 채운다.

        실측에서 라벨 32개 중 후보로 잡힌 것은 21개뿐이었다. 나머지를 두면
        지표 왜곡이 절반만 고쳐진다.
        """
        rows = []
        y = 100
        for turn in range(6):
            rows.append((self.LABEL_X, y, 165, 31, "하트를든라이언"))
            rows.append((self.TEXT_X, y + 36, 400, 47, f"상대 메시지 {turn}"))
            rows.append((520, y + 120, 160, 47, f"내 메시지 {turn}"))
            y += 220
        # 아래에 말풍선이 없는 라벨 하나를 화면 끝에 둔다
        rows.append((self.LABEL_X, y, 165, 31, "하트를든라이언"))

        convo = parse([self._page(rows)], min_messages=1)

        assert not any("라이언" in m.text for m in convo.messages)
