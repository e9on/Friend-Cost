"""업로드 이미지 검증.

API 명세 4장, 기준 명세 9장.

확장자가 아니라 매직 넘버로 형식을 판별한다. 확장자만 바꾼 실행 파일을
걸러내기 위해서다.

이미지 크기는 헤더에서 직접 읽는다. 이미지 라이브러리를 쓰지 않는 이유는
콜드 스타트가 중요한 배포 형태이기 때문이다. 헤더 몇 바이트만 보면 되는 일에
무거운 의존성을 들이지 않는다.
"""

import struct
from dataclasses import dataclass
from typing import Sequence

from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass(frozen=True)
class UploadedImage:
    """검증 전 원본. 파일명은 검증에만 쓰고 저장하지 않는다."""

    filename: str
    data: bytes


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    width: int
    height: int

    @property
    def size(self) -> int:
        return len(self.data)


def detect_format(data: bytes) -> str | None:
    """매직 넘버로 형식을 판별한다. 모르면 `None`."""
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return (width, height) if width and height else None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """SOF 마커를 찾아 크기를 읽는다."""
    offset = 2
    length = len(data)
    while offset + 9 < length:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        segment_length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        # SOF0~SOF15 중 DHT(C4), JPG(C8), DAC(CC)는 크기 정보가 아니다
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
            return (width, height) if width and height else None
        offset += 2 + segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    try:
        if chunk == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return width, height
        if chunk == b"VP8 " and len(data) >= 30:
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return width, height
        if chunk == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    except (struct.error, IndexError):
        return None
    return None


def read_dimensions(data: bytes) -> tuple[int, int] | None:
    """이미지 헤더에서 (너비, 높이)를 읽는다. 못 읽으면 `None`."""
    fmt = detect_format(data)
    if fmt == "image/png":
        return _png_dimensions(data)
    if fmt == "image/jpeg":
        return _jpeg_dimensions(data)
    if fmt == "image/webp":
        return _webp_dimensions(data)
    return None


def validate_uploads(
    images: Sequence[UploadedImage], settings: Settings
) -> list[ValidatedImage]:
    """업로드 묶음 전체를 검증한다. 순서는 그대로 유지한다.

    순서를 유지하는 이유는 업로드 순서가 곧 대화의 시간 순서이기 때문이다.
    """
    if not settings.min_images <= len(images) <= settings.max_images:
        raise AppError(ErrorCode.IMAGE_TOO_MANY)

    total = 0
    validated: list[ValidatedImage] = []

    for image in images:
        if len(image.data) > settings.max_image_bytes:
            raise AppError(ErrorCode.IMAGE_TOO_LARGE)
        total += len(image.data)
        if total > settings.max_total_bytes:
            raise AppError(ErrorCode.IMAGE_TOO_LARGE)

        mime_type = detect_format(image.data)
        if mime_type is None or mime_type not in settings.allowed_mime_types:
            raise AppError(ErrorCode.IMAGE_FORMAT_UNSUPPORTED)

        size = read_dimensions(image.data)
        if size is None:
            raise AppError(ErrorCode.IMAGE_FORMAT_UNSUPPORTED)

        width, height = size
        if min(width, height) < settings.min_image_side:
            # 글자를 읽을 수 없을 만큼 작으면 OCR을 돌려봐야 시간과 비용만 든다
            raise AppError(ErrorCode.IMAGE_FORMAT_UNSUPPORTED)

        validated.append(
            ValidatedImage(data=image.data, mime_type=mime_type, width=width, height=height)
        )

    return validated
