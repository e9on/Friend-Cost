"""좌우 여백으로 화자를 판별한다.

OCR·Parser 명세 4장.

카카오톡 1:1 화면에서 내 메시지는 오른쪽 끝에, 상대 메시지는 왼쪽 끝에 붙는다.
OCR은 색을 알려주지 않으므로 이 정렬만이 유일한 단서다.
"""

from enum import Enum
from typing import Final

from app.domain.model.conversation import OcrBlock
from app.domain.value_object.enums import Speaker

# 여백 차이가 이미지 폭의 이 비율보다 작으면 중앙 정렬로 본다
CENTER_TOLERANCE_RATIO: Final = 0.05


class BlockRole(str, Enum):
    ME = "me"
    PEER = "peer"
    CENTER = "center"

    def to_speaker(self) -> Speaker | None:
        if self is BlockRole.ME:
            return Speaker.ME
        if self is BlockRole.PEER:
            return Speaker.PEER
        return None


def margins(block: OcrBlock, page_width: int) -> tuple[int, int]:
    """(왼쪽 여백, 오른쪽 여백)."""
    return block.box.x, page_width - block.box.right


def classify_block(block: OcrBlock, page_width: int) -> BlockRole:
    """블록의 좌우 여백을 비교해 역할을 정한다.

    블록의 중심점이 아니라 여백을 비교하는 이유는, 긴 메시지가 화면 폭의 70%
    이상을 차지해서 중심점이 화면 중앙 근처로 몰리기 때문이다. 여백 비교는
    메시지 길이와 무관하게 동작한다.
    """
    left, right = margins(block, page_width)
    if abs(left - right) < page_width * CENTER_TOLERANCE_RATIO:
        return BlockRole.CENTER
    return BlockRole.PEER if left < right else BlockRole.ME
