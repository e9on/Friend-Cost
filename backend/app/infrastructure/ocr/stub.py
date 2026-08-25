"""실제 엔진을 붙이기 전까지 쓰는 OCR 스텁.

기준 명세 13장: OCR 엔진은 평가 후에 정한다.

이 스텁은 이미지 내용을 **읽지 않는다.** 바이트를 해시해 씨앗을 만들고,
카카오톡 화면과 같은 성질의 좌표 배치를 지어낸다.

- 내 말풍선은 오른쪽 끝에 붙는다
- 상대 말풍선은 프로필 자리를 비우고 왼쪽에 붙는다
- 시각 라벨은 말풍선 안쪽에 붙는다
- 날짜 구분선은 가운데 정렬된다

덕분에 실제 엔진 없이도 Parser부터 API까지 전 구간을 돌릴 수 있다.
결과의 내용에는 아무 의미가 없으므로 품질 평가에 쓰면 안 된다.
"""

import hashlib
from typing import Final, Sequence

from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage

WIDTH: Final = 1080
HEIGHT: Final = 2340
EDGE: Final = 40
PROFILE_WIDTH: Final = 110
LINE_HEIGHT: Final = 52
GAP: Final = 24
TIME_WIDTH: Final = 96
TIME_HEIGHT: Final = 28
CHAR_WIDTH: Final = 26
MAX_BUBBLE: Final = 700

_ME_LINES: Final = (
    "내일 시간 돼?",
    "ㅋㅋㅋㅋㅋ 그래",
    "밥은 먹었어",
    "그럼 그때 보자",
    "고마워 진짜",
    "나도 그렇게 생각해",
)
_PEER_LINES: Final = (
    "어 괜찮아",
    "미안 좀 늦을 듯",
    "다음에 보자",
    "웬일이야",
    "알겠어 그때 연락할게",
    "ㅇㅇ",
)


def _bubble_width(text: str) -> int:
    return max(60, min(MAX_BUBBLE, len(text) * CHAR_WIDTH + 40))


def _stamp(hour: int, minute: int) -> str:
    if hour < 12:
        return f"오전 {hour or 12}:{minute:02d}"
    return f"오후 {hour - 12 or 12}:{minute:02d}"


class StubOcrEngine:
    """이미지당 합성 대화 한 화면을 만들어 낸다."""

    name = "stub"

    def __init__(self, turns_per_image: int = 18) -> None:
        self._turns = turns_per_image

    async def read(self, images: Sequence[bytes]) -> tuple[OcrPage, ...]:
        return tuple(
            self._page(index, data) for index, data in enumerate(images)
        )

    def _page(self, image_index: int, data: bytes) -> OcrPage:
        seed = int.from_bytes(hashlib.sha256(data).digest()[:8], "big")
        blocks: list[OcrBlock] = []
        y = 120

        def add(text: str, x: int, w: int, h: int, at_y: int) -> None:
            blocks.append(
                OcrBlock(
                    text=text,
                    box=BoundingBox(x=x, y=at_y, w=w, h=h),
                    confidence=0.90 + (seed % 9) / 100,
                )
            )

        if image_index == 0:
            label = "2026년 8월 25일 화요일"
            w = len(label) * CHAR_WIDTH
            add(label, (WIDTH - w) // 2, w, 40, y)
            y += 40 + GAP

        hour = 9 + image_index
        minute = (seed >> 3) % 10

        for turn in range(self._turns):
            mine = (seed >> turn) % 2 == 0
            pool = _ME_LINES if mine else _PEER_LINES
            text = pool[(seed >> (turn + 4)) % len(pool)]
            width = _bubble_width(text)
            stamp = _stamp(hour % 24, minute)

            if mine:
                x = WIDTH - EDGE - width
                add(text, x, width, LINE_HEIGHT, y)
                add(stamp, x - TIME_WIDTH - 10, TIME_WIDTH, TIME_HEIGHT, y + 16)
            else:
                x = EDGE + PROFILE_WIDTH
                add(text, x, width, LINE_HEIGHT, y)
                add(stamp, x + width + 10, TIME_WIDTH, TIME_HEIGHT, y + 16)

            y += LINE_HEIGHT + GAP
            minute += 3 + (seed >> (turn + 8)) % 5
            if minute >= 60:
                minute -= 60
                hour += 1

        return OcrPage(
            image_index=image_index,
            width=WIDTH,
            height=max(HEIGHT, y + 100),
            blocks=tuple(blocks),
        )
