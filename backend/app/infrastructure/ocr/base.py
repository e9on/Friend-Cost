"""OCR 엔진 인터페이스.

OCR·Parser 명세 2장.

**엔진 선정의 1순위 기준은 정확도가 아니라 좌표 제공 여부다.**
화자 판별이 좌우 여백 비교에 의존하므로, 좌표나 이미지 크기를 주지 않는 엔진은
비용이 낮아도 채택할 수 없다. 이 인터페이스가 그 요구를 타입으로 못 박는다.
"""

from typing import Protocol, Sequence, runtime_checkable

from app.domain.model.conversation import OcrPage


@runtime_checkable
class OcrEngine(Protocol):
    name: str

    async def read(self, images: Sequence[bytes]) -> tuple[OcrPage, ...]:
        """이미지들을 읽어 페이지별 블록과 좌표를 돌려준다.

        입력 순서가 곧 `image_index` 이며 시간 순서로 간주된다.
        """
