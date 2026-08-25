"""업로드 이미지 검증.

API 명세 4장. 확장자가 아니라 매직 넘버로 형식을 판별한다.
확장자만 바꾼 실행 파일을 걸러내기 위해서다.
"""

import struct
import zlib

import pytest

from app.application.service.upload_validator import (
    UploadedImage,
    detect_format,
    read_dimensions,
    validate_uploads,
)
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings


def png_bytes(width: int = 1080, height: int = 2340) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr_body = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_body) - 4) + ihdr_body
    ihdr += struct.pack(">I", zlib.crc32(ihdr_body))
    return header + ihdr


def jpeg_bytes(width: int = 1080, height: int = 2340) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x00" * 9
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + sof


def webp_bytes(width: int = 1080, height: int = 2340) -> bytes:
    vp8x = b"VP8X" + struct.pack("<I", 10) + b"\x00" * 4
    vp8x += struct.pack("<I", width - 1)[:3] + struct.pack("<I", height - 1)[:3]
    body = b"WEBP" + vp8x
    return b"RIFF" + struct.pack("<I", len(body)) + body


@pytest.fixture
def settings():
    return Settings()


def image(data: bytes, name: str = "shot.png") -> UploadedImage:
    return UploadedImage(filename=name, data=data)


class TestDetectFormat:
    @pytest.mark.parametrize(
        "data, expected",
        [
            (png_bytes(), "image/png"),
            (jpeg_bytes(), "image/jpeg"),
            (webp_bytes(), "image/webp"),
        ],
    )
    def test_reads_the_magic_number(self, data, expected):
        assert detect_format(data) == expected

    def test_executable_disguised_as_png_is_rejected(self):
        assert detect_format(b"MZ\x90\x00" + b"\x00" * 100) is None

    def test_empty_payload_is_rejected(self):
        assert detect_format(b"") is None


class TestReadDimensions:
    @pytest.mark.parametrize("factory", [png_bytes, jpeg_bytes, webp_bytes])
    def test_reads_width_and_height(self, factory):
        assert read_dimensions(factory(800, 1600)) == (800, 1600)

    def test_returns_none_for_unreadable_headers(self):
        assert read_dimensions(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4) is None


class TestValidateUploads:
    def test_accepts_a_normal_batch(self, settings):
        images = [image(png_bytes()) for _ in range(3)]

        assert len(validate_uploads(images, settings)) == 3

    def test_rejects_an_empty_batch(self, settings):
        with pytest.raises(AppError) as caught:
            validate_uploads([], settings)
        assert caught.value.code is ErrorCode.IMAGE_TOO_MANY

    def test_rejects_too_many_images(self, settings):
        images = [image(png_bytes()) for _ in range(settings.max_images + 1)]

        with pytest.raises(AppError) as caught:
            validate_uploads(images, settings)
        assert caught.value.code is ErrorCode.IMAGE_TOO_MANY

    def test_rejects_an_oversized_image(self, settings):
        big = image(png_bytes() + b"\x00" * (settings.max_image_bytes + 1))

        with pytest.raises(AppError) as caught:
            validate_uploads([big], settings)
        assert caught.value.code is ErrorCode.IMAGE_TOO_LARGE

    def test_rejects_when_the_batch_total_is_too_large(self, settings):
        chunk = settings.max_image_bytes - 1000
        images = [image(png_bytes() + b"\x00" * chunk) for _ in range(6)]

        with pytest.raises(AppError) as caught:
            validate_uploads(images, settings)
        assert caught.value.code is ErrorCode.IMAGE_TOO_LARGE

    def test_rejects_an_unsupported_format(self, settings):
        with pytest.raises(AppError) as caught:
            validate_uploads([image(b"GIF89a" + b"\x00" * 50, "shot.gif")], settings)
        assert caught.value.code is ErrorCode.IMAGE_FORMAT_UNSUPPORTED

    def test_rejects_a_file_renamed_to_png(self, settings):
        disguised = image(b"MZ\x90\x00" + b"\x00" * 500, "innocent.png")

        with pytest.raises(AppError) as caught:
            validate_uploads([disguised], settings)
        assert caught.value.code is ErrorCode.IMAGE_FORMAT_UNSUPPORTED

    def test_rejects_an_image_too_small_to_read(self, settings):
        tiny = image(png_bytes(100, 100))

        with pytest.raises(AppError) as caught:
            validate_uploads([tiny], settings)
        assert caught.value.code is ErrorCode.IMAGE_FORMAT_UNSUPPORTED

    def test_keeps_the_upload_order(self, settings):
        images = [image(png_bytes(800 + i, 1600)) for i in range(3)]

        validated = validate_uploads(images, settings)

        assert [v.width for v in validated] == [800, 801, 802]
