"""좌우 여백으로 화자를 판별한다.

OCR·Parser 명세 4장. 이 판별이 틀리면 서비스 지표의 절반이 함께 틀린다.
"""

import pytest

from app.ai.parser.speaker import BlockRole, classify_block
from app.domain.model.conversation import BoundingBox, OcrBlock

WIDTH = 1080


def block(x: int, w: int, y: int = 100, h: int = 44, text: str = "안녕") -> OcrBlock:
    return OcrBlock(text=text, box=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)


class TestClassifyBlock:
    def test_block_hugging_the_left_edge_is_the_peer(self):
        assert classify_block(block(x=40, w=300), WIDTH) is BlockRole.PEER

    def test_block_hugging_the_right_edge_is_me(self):
        # 오른쪽 여백 72px, 왼쪽 여백 612px
        assert classify_block(block(x=612, w=396), WIDTH) is BlockRole.ME

    def test_centered_block_is_neither(self):
        assert classify_block(block(x=400, w=280), WIDTH) is BlockRole.CENTER

    def test_nearly_centered_block_is_still_center(self):
        # 여백 차 20px < 1080 * 0.05
        assert classify_block(block(x=380, w=300), WIDTH) is BlockRole.CENTER

    def test_long_message_is_classified_by_margin_not_midpoint(self):
        """긴 메시지는 중심점이 화면 중앙으로 몰린다.

        폭의 78%를 차지하는 내 메시지: 중심점은 x=580으로 거의 한가운데지만
        오른쪽 여백이 40px밖에 안 되므로 내 메시지다.
        """
        long_block = block(x=200, w=840)

        midpoint = long_block.box.x + long_block.box.w / 2
        assert abs(midpoint - WIDTH / 2) < WIDTH * 0.1  # 중심점만 보면 애매하다

        assert classify_block(long_block, WIDTH) is BlockRole.ME

    @pytest.mark.parametrize("width", [720, 1080, 1440])
    def test_threshold_scales_with_image_width(self, width):
        # 여백 차가 폭의 4%면 어떤 해상도에서도 중앙으로 본다
        gap = int(width * 0.04)
        x = (width - 200 - gap) // 2
        assert classify_block(block(x=x, w=200), width) is BlockRole.CENTER
