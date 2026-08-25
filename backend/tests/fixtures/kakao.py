"""카카오톡 1:1 화면을 흉내 낸 합성 OCR 픽스처.

실제 캡처 이미지 없이 Parser 전체를 검증하기 위한 도구다.
좌표 배치가 실제 화면과 같은 성질을 갖도록 만든다.

- 내 말풍선은 오른쪽 끝에 붙는다
- 상대 말풍선은 프로필 사진 자리를 비우고 왼쪽에 붙는다
- 시각 라벨은 말풍선 안쪽(내 것은 왼쪽, 상대 것은 오른쪽)에 붙는다
- 날짜 구분선과 시스템 안내는 가운데 정렬된다

실제 OCR 엔진을 붙일 때 이 픽스처가 그대로 비교 기준이 된다.
"""

from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage

WIDTH = 1080
HEIGHT = 2340

EDGE = 40
PROFILE_WIDTH = 110
LINE_HEIGHT = 52
GAP = 24
TIME_WIDTH = 96
TIME_HEIGHT = 28
CHAR_WIDTH = 26
MAX_BUBBLE = 700


def _bubble_width(text: str) -> int:
    return max(60, min(MAX_BUBBLE, len(text) * CHAR_WIDTH + 40))


class ScreenBuilder:
    """세로로 흘러가는 대화 화면을 조립한다."""

    def __init__(self, image_index: int = 0, width: int = WIDTH) -> None:
        self.image_index = image_index
        self.width = width
        self.blocks: list[OcrBlock] = []
        self._y = 120

    def _add(self, text: str, x: int, w: int, h: int, y: int | None = None) -> None:
        self.blocks.append(
            OcrBlock(
                text=text,
                box=BoundingBox(x=x, y=self._y if y is None else y, w=w, h=h),
                confidence=0.96,
            )
        )

    def me(self, text: str, at: str | None = None) -> "ScreenBuilder":
        """내 메시지. 오른쪽 끝에 붙는다."""
        w = _bubble_width(text)
        x = self.width - EDGE - w
        self._add(text, x, w, LINE_HEIGHT)
        if at:
            self._add(at, x - TIME_WIDTH - 10, TIME_WIDTH, TIME_HEIGHT, self._y + 16)
        self._y += LINE_HEIGHT + GAP
        return self

    def peer(self, text: str, at: str | None = None) -> "ScreenBuilder":
        """상대 메시지. 프로필 자리를 비우고 왼쪽에 붙는다."""
        w = _bubble_width(text)
        x = EDGE + PROFILE_WIDTH
        self._add(text, x, w, LINE_HEIGHT)
        if at:
            self._add(at, x + w + 10, TIME_WIDTH, TIME_HEIGHT, self._y + 16)
        self._y += LINE_HEIGHT + GAP
        return self

    def center(self, text: str) -> "ScreenBuilder":
        """날짜 구분선이나 시스템 안내. 가운데 정렬."""
        w = max(60, len(text) * CHAR_WIDTH)
        self._add(text, (self.width - w) // 2, w, 40)
        self._y += 40 + GAP
        return self

    def peer_name(self, name: str) -> "ScreenBuilder":
        """단체방에서 말풍선 위에 붙는 발신자 이름."""
        w = len(name) * 20
        self._add(name, EDGE + PROFILE_WIDTH, w, 26)
        self._y += 26 + 6
        return self

    def build(self) -> OcrPage:
        return OcrPage(
            image_index=self.image_index,
            width=self.width,
            height=max(HEIGHT, self._y + 100),
            blocks=tuple(self.blocks),
        )


def simple_chat(turns: int = 20, image_index: int = 0, start_hour: int = 9) -> OcrPage:
    """me/peer가 번갈아 말하는 평범한 대화 한 화면."""
    screen = ScreenBuilder(image_index=image_index)
    screen.center("2026년 8월 25일 화요일")
    minute = 0
    hour = start_hour
    for turn in range(turns):
        stamp = f"오전 {hour}:{minute:02d}" if hour < 12 else f"오후 {hour - 12 or 12}:{minute:02d}"
        text = f"메시지 {turn}"
        if turn % 2 == 0:
            screen.me(text, at=stamp)
        else:
            screen.peer(text, at=stamp)
        minute += 5
        if minute >= 60:
            minute -= 60
            hour += 1
    return screen.build()
