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

from app.ai.parser import parse
from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import OcrPage

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
