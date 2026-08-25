"""Google Cloud Vision OCR 엔진.

`AI-모델-선정-보고서.md` 4장의 1순위 후보다. 좌표를 확실히 제공하고,
무료 한도가 초기 규모를 덮으며, 초과 비용도 낮다.

REST API를 직접 호출한다. 공식 클라이언트 라이브러리는 gRPC와 인증 스택을
함께 끌고 와서 이미지가 무거워지는데, 우리는 콜드 스타트가 중요한 배포를
전제하고 있다(기준 명세 6장). 필요한 것은 엔드포인트 하나다.

인증은 API 키를 쓴다. 서비스 계정 JSON은 배포 환경에 파일을 두어야 해서
스케일-투-제로 컨테이너에 잘 맞지 않는다.
"""

import asyncio
import base64
import logging
from typing import Any, Sequence

import httpx

from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import BoundingBox, OcrBlock, OcrPage

logger = logging.getLogger(__name__)

ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"

# 한국어 힌트를 준다. 카카오톡 캡처는 한국어가 대부분이다
LANGUAGE_HINTS = ["ko", "en"]


class GoogleVisionOcrEngine:
    """`DOCUMENT_TEXT_DETECTION` 으로 블록과 좌표를 얻는다."""

    name = "google_vision"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 60.0,
        max_concurrency: int = 4,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        # 이미지를 동시에 보내되 상대 API를 몰아치지 않는다
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def read(self, images: Sequence[bytes]) -> tuple[OcrPage, ...]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            tasks = [
                self._read_one(client, index, data) for index, data in enumerate(images)
            ]
            pages = await asyncio.gather(*tasks)
        return tuple(pages)

    async def _read_one(
        self, client: httpx.AsyncClient, index: int, data: bytes
    ) -> OcrPage:
        payload = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(data).decode("ascii")},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    "imageContext": {"languageHints": LANGUAGE_HINTS},
                }
            ]
        }

        async with self._semaphore:
            try:
                response = await client.post(
                    ENDPOINT, params={"key": self._api_key}, json=payload
                )
            except Exception as exc:
                logger.warning("vision 호출 실패 image=%d error=%s", index, type(exc).__name__)
                raise AppError(ErrorCode.OCR_FAILED) from exc

        if response.status_code >= 400:
            logger.warning("vision 오류 응답 image=%d status=%d", index, response.status_code)
            raise AppError(ErrorCode.OCR_FAILED)

        return _to_page(index, response.json())


def _to_page(index: int, body: dict[str, Any]) -> OcrPage:
    responses = body.get("responses") or []
    if not responses:
        raise AppError(ErrorCode.OCR_FAILED)

    first = responses[0]
    if "error" in first:
        raise AppError(ErrorCode.OCR_FAILED)

    annotation = first.get("fullTextAnnotation")
    if not annotation:
        # 글자를 하나도 찾지 못한 경우다. 빈 페이지로 넘기고 Parser가 판단한다
        return OcrPage(image_index=index, width=1, height=1, blocks=())

    pages = annotation.get("pages") or []
    if not pages:
        raise AppError(ErrorCode.OCR_FAILED)

    page = pages[0]
    width = int(page.get("width") or 0)
    height = int(page.get("height") or 0)
    if width <= 0 or height <= 0:
        # 크기를 모르면 좌우 여백을 비교할 수 없다. 화자 판별의 전제가 깨진다
        raise AppError(ErrorCode.OCR_FAILED)

    blocks = tuple(_iter_blocks(page))
    return OcrPage(image_index=index, width=width, height=height, blocks=blocks)


def _iter_blocks(page: dict[str, Any]):
    """문단(paragraph) 단위로 블록을 만든다.

    블록(block)은 너무 크고 단어(word)는 너무 잘게 쪼개진다. 문단이 말풍선 한 개에
    가장 가깝다. 더 쪼개져 나오더라도 Parser가 좌우 정렬과 세로 간격을 보고
    다시 붙인다.
    """
    for block in page.get("blocks") or []:
        for paragraph in block.get("paragraphs") or []:
            text = _paragraph_text(paragraph)
            if not text:
                continue
            box = _to_box(paragraph.get("boundingBox"))
            if box is None:
                continue
            yield OcrBlock(
                text=text,
                box=box,
                confidence=float(paragraph.get("confidence") or 0.9),
            )


def _paragraph_text(paragraph: dict[str, Any]) -> str:
    """단어와 기호를 이어 붙인다. Vision은 공백을 별도 속성으로 준다."""
    parts: list[str] = []
    for word in paragraph.get("words") or []:
        for symbol in word.get("symbols") or []:
            parts.append(symbol.get("text") or "")
            break_type = ((symbol.get("property") or {}).get("detectedBreak") or {}).get(
                "type"
            )
            if break_type in ("SPACE", "SURE_SPACE"):
                parts.append(" ")
            elif break_type in ("LINE_BREAK", "EOL_SURE_SPACE"):
                parts.append(" ")
    return "".join(parts).strip()


def _to_box(bounding: dict[str, Any] | None) -> BoundingBox | None:
    """꼭짓점 목록을 축에 정렬된 사각형으로 바꾼다.

    Vision은 회전된 텍스트도 다루려고 꼭짓점 4개를 준다. 우리는 좌우 여백만
    비교하므로 외접 사각형이면 충분하다.
    """
    if not bounding:
        return None

    vertices = bounding.get("vertices") or bounding.get("normalizedVertices") or []
    xs = [int(vertex.get("x") or 0) for vertex in vertices]
    ys = [int(vertex.get("y") or 0) for vertex in vertices]
    if not xs or not ys:
        return None

    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    if right <= left or bottom <= top:
        return None

    return BoundingBox(x=left, y=top, w=right - left, h=bottom - top)
