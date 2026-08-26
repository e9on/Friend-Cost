"""RapidOCR 엔진. 컨테이너 내장 OCR 후보.

PaddleOCR 모델을 ONNX로 변환한 것이라 torch를 끌고 오지 않는다. CPU에서
돌고, 실측에서 이미지 한 장에 1초 안쪽이었다.

`AI-모델-선정-보고서.md` 4장에서 컨테이너 내장 OCR은 "볼륨이 커진 뒤"로 미뤄뒀는데,
비용 모델을 다시 계산해보니 전환점이 예상보다 낮았다(월 약 1,100건). 그래서
후보로 올린다.

**API 키가 필요 없다.** 그 덕에 실제 계약 없이 지금 평가할 수 있다.

    pip install "rapidocr>=3.0"

**한국어 모델을 지정해야 한다.** 기본값은 중국어·영어라 한글을 한 글자도
읽지 못한다. 실측에서 인식률 0%였다. 좌표는 잘 잡으므로 화자 판별은 100%가
나오는데 정작 글자가 비어 있다. **오류가 아니라 빈 결과로 나오므로 눈에 띄지
않는다.**

무거운 의존성이라 선택 설치로 둔다. 임포트를 함수 안으로 미뤄서, 쓰지 않는
배포에서는 설치하지 않아도 되게 한다.
"""

import asyncio
import logging
from typing import Any, Final, Sequence

from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.3

# 한국어 인식 모델. 처음 쓸 때 약 23MB를 내려받아 패키지 안에 둔다.
#
# PP-OCRv4 를 쓰는 이유는 **PP-OCRv5 에 한국어 모델이 없기 때문이다.**
# v5 는 중국어·영어·일본어 혼합을 다루고, 한국어 전용은 v4 가 마지막이다.
#
# 구버전 `rapidocr_onnxruntime` 의 `korean_mobile_v2.0`(2021)도 재봤지만
# 문자 오류율이 54%였다. "사진 보냈어 확인해봐"가 "c11등i&s써이&"로 나왔다.
DEFAULT_LANG: Final = "korean"
DEFAULT_OCR_VERSION: Final = "PP-OCRv4"


class RapidOcrEngine:
    """컨테이너 안에서 도는 OCR. 상시 실행 인스턴스를 전제한다."""

    name = "rapid"

    def __init__(
        self,
        *,
        lang: str = DEFAULT_LANG,
        ocr_version: str = DEFAULT_OCR_VERSION,
    ) -> None:
        self._lang = lang
        self._ocr_version = ocr_version
        self._reader: Any = None

    def _get_reader(self) -> Any:
        if self._reader is not None:
            return self._reader
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError as exc:  # pragma: no cover - 설치 여부에 달린 경로
            raise AppError(ErrorCode.OCR_FAILED) from exc

        self._reader = RapidOCR(
            params={
                "Rec.lang_type": LangRec(self._lang),
                "Rec.model_type": ModelType.MOBILE,
                "Rec.ocr_version": OCRVersion(self._ocr_version),
            }
        )
        return self._reader

    async def read(self, images: Sequence[bytes]) -> tuple[OcrPage, ...]:
        reader = self._get_reader()
        # 모델 추론은 동기 CPU 작업이다. 이벤트 루프를 막지 않도록 옮긴다
        pages = await asyncio.gather(
            *(
                asyncio.to_thread(self._read_one, reader, index, data)
                for index, data in enumerate(images)
            )
        )
        return tuple(pages)

    def _read_one(self, reader: Any, index: int, data: bytes) -> OcrPage:
        import io

        from PIL import Image

        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            width, height = image.size
            result = reader(_to_array(image))
        except Exception as exc:
            logger.warning("rapid ocr 실패 image=%d error=%s", index, type(exc).__name__)
            raise AppError(ErrorCode.OCR_FAILED) from exc

        return OcrPage(
            image_index=index,
            width=width,
            height=height,
            blocks=tuple(_to_blocks(result)),
        )


def _to_array(image: Any) -> Any:
    import numpy as np

    return np.array(image)


def _to_blocks(result: Any):
    """`RapidOCROutput` 을 `OcrBlock` 으로 옮긴다.

    `boxes` 는 꼭짓점 네 개다. 회전을 표현하려는 것이므로 외접 사각형으로
    접는다. 우리는 좌우 여백만 본다.

    글자를 하나도 찾지 못하면 세 배열이 모두 `None` 으로 온다. 빈 목록이
    아니라 `None` 이라서, 그대로 순회하면 터진다.
    """
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or texts is None or scores is None:
        return

    for points, text, score in zip(boxes, texts, scores):
        if not text or not text.strip() or float(score) < MIN_CONFIDENCE:
            continue

        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        if right <= left or bottom <= top:
            continue

        yield OcrBlock(
            text=text.strip(),
            box=BoundingBox(x=left, y=top, w=right - left, h=bottom - top),
            confidence=min(1.0, max(0.0, float(score))),
        )
