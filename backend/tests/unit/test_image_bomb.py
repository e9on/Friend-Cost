"""비정상적으로 큰 이미지 방어.

`운영-보안-법적고지-명세.md` 6.2에 남은 조치로 적어두었던 항목이다.

파일 크기와 해상도는 별개다. 균일한 색으로 채운 PNG는 33바이트로도
30000×30000을 선언할 수 있다. 용량 검사만 통과시키면 그대로 OCR로 넘어가
처리 시간과 과금이 그대로 나간다.

우리가 직접 디코드하지 않기 때문에 서버가 죽지는 않는다. 대신 **비용이 샌다.**
"""

import struct
import zlib

import pytest

from app.application.service.upload_validator import (
    UploadedImage,
    read_dimensions,
    validate_uploads,
)
from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings


def png(width: int, height: int, padding: int = 0) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    body = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(body) - 4) + body + struct.pack(">I", zlib.crc32(body))
    return header + chunk + b"\x00" * padding


@pytest.fixture
def settings():
    return Settings()


def check(data: bytes, settings: Settings):
    return validate_uploads([UploadedImage(filename="shot.png", data=data)], settings)


class TestPixelLimit:
    def test_a_tiny_file_declaring_a_huge_canvas_is_rejected(self, settings):
        """33바이트로 9억 픽셀을 선언할 수 있다."""
        bomb = png(30_000, 30_000)

        assert len(bomb) < 100
        with pytest.raises(AppError) as caught:
            check(bomb, settings)

        assert caught.value.code is ErrorCode.IMAGE_FORMAT_UNSUPPORTED

    def test_an_extremely_tall_strip_is_rejected(self, settings):
        """긴 스크롤 캡처를 한 장으로 이어 붙인 경우."""
        with pytest.raises(AppError):
            check(png(1080, 200_000), settings)

    def test_an_extremely_wide_strip_is_rejected(self, settings):
        with pytest.raises(AppError):
            check(png(200_000, 1080), settings)

    def test_a_normal_phone_screenshot_passes(self, settings):
        for width, height in ((1080, 2340), (1284, 2778), (1440, 3200), (720, 1600)):
            assert check(png(width, height), settings)

    def test_a_long_but_plausible_scroll_capture_passes(self, settings):
        """스크롤 캡처는 세로로 길다. 정상 범위는 막지 않는다."""
        assert check(png(1080, 12_000), settings)

    def test_the_limit_is_on_total_pixels_not_one_side(self, settings):
        """한 변만 보면 8000×8000(6400만 화소)을 놓친다."""
        with pytest.raises(AppError):
            check(png(8_000, 8_000), settings)


class TestExistingChecksStillWork:
    def test_too_small_is_still_rejected(self, settings):
        with pytest.raises(AppError):
            check(png(100, 100), settings)

    def test_unreadable_header_is_still_rejected(self, settings):
        with pytest.raises(AppError):
            check(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, settings)

    def test_dimension_reading_is_untouched(self):
        assert read_dimensions(png(1080, 2340)) == (1080, 2340)


class TestConfigurable:
    def test_the_limit_can_be_raised(self):
        loose = Settings(max_image_pixels=1_000_000_000)

        assert check(png(30_000, 30_000), loose)

    def test_the_limit_can_be_lowered(self):
        tight = Settings(max_image_pixels=1_000_000)

        with pytest.raises(AppError):
            check(png(1080, 2340), tight)
