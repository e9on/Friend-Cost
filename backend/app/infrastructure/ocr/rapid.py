"""RapidOCR 엔진. 컨테이너 내장 OCR 후보.

PaddleOCR 모델을 ONNX로 변환한 것이라 torch를 끌고 오지 않는다. 설치 용량이
수백 MB 수준이고 CPU에서 돌아간다.

`AI-모델-선정-보고서.md` 4장에서 컨테이너 내장 OCR은 "볼륨이 커진 뒤"로 미뤄뒀는데,
비용 모델을 다시 계산해보니 전환점이 예상보다 낮았다(월 약 1,100건). 그래서
후보로 올린다.

**API 키가 필요 없다.** 그 덕에 실제 계약 없이 지금 평가할 수 있다.

    pip install rapidocr-onnxruntime

무거운 의존성이라 선택 설치로 둔다. 임포트를 함수 안으로 미뤄서, 쓰지 않는
배포에서는 설치하지 않아도 되게 한다.
"""

import asyncio
import logging
from typing import Any, Sequence

from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.3


class RapidOcrEngine:
    """컨테이너 안에서 도는 OCR. 상시 실행 인스턴스를 전제한다."""

    name = "rapid"

    def __init__(self, *, use_gpu: bool = False) -> None:
        self._use_gpu = use_gpu
        self._reader: Any = None

    def _get_reader(self) -> Any:
        if self._reader is not None:
            return self._reader
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - 설치 여부에 달린 경로
            raise AppError(ErrorCode.OCR_FAILED) from exc
        self._reader = RapidOCR()
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
            result, _ = reader(_to_array(image))
        except Exception as exc:
            logger.warning("rapid ocr 실패 image=%d error=%s", index, type(exc).__name__)
            raise AppError(ErrorCode.OCR_FAILED) from exc

        return OcrPage(
            image_index=index,
            width=width,
            height=height,
            blocks=tuple(_to_blocks(result or [])),
        )


def _to_array(image: Any) -> Any:
    import numpy as np

    return np.array(image)


def _to_blocks(result: Sequence[Any]):
    """RapidOCR 결과를 `OcrBlock` 으로 옮긴다.

    결과 한 줄은 `[꼭짓점 4개, 텍스트, 신뢰도]` 형태다. 꼭짓점은 회전을
    표현하려는 것이므로 외접 사각형으로 접는다. 우리는 좌우 여백만 본다.
    """
    for item in result:
        try:
            points, text, score = item[0], item[1], float(item[2])
        except (IndexError, TypeError, ValueError):
            continue
        if not text or not text.strip() or score < MIN_CONFIDENCE:
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
            confidence=min(1.0, max(0.0, score)),
        )
