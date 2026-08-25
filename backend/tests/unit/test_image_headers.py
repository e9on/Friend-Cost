"""이미지 헤더에서 형식과 크기를 직접 읽는다.

API 명세 4장. 이미지 라이브러리를 쓰지 않는 이유는 콜드 스타트가 중요한
배포 형태이기 때문이다. 대신 형식별 헤더 구조를 정확히 다뤄야 한다.
"""

import struct

import pytest

from app.application.service.upload_validator import detect_format, read_dimensions

RIFF = b"RIFF"


def jpeg_with_segments(*segments: bytes, width: int = 1080, height: int = 2340) -> bytes:
    """SOF 앞에 임의의 세그먼트를 끼워 넣은 JPEG."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x00" * 9
    return b"\xff\xd8" + b"".join(segments) + sof


def segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def webp(chunk: bytes) -> bytes:
    body = b"WEBP" + chunk
    return RIFF + struct.pack("<I", len(body)) + body


def webp_vp8(width: int, height: int) -> bytes:
    frame = b"\x00\x00\x00" + b"\x9d\x01\x2a"
    frame += struct.pack("<HH", width, height)
    return webp(b"VP8 " + struct.pack("<I", len(frame)) + frame)


def webp_vp8l(width: int, height: int) -> bytes:
    bits = (width - 1) | ((height - 1) << 14)
    payload = b"\x2f" + struct.pack("<I", bits)
    return webp(b"VP8L" + struct.pack("<I", len(payload)) + payload)


class TestJpegVariants:
    def test_skips_application_segments_before_sof(self):
        data = jpeg_with_segments(segment(0xE0, b"JFIF\x00" + b"\x00" * 10))

        assert read_dimensions(data) == (1080, 2340)

    def test_huffman_table_is_not_mistaken_for_sof(self):
        """DHT 마커(0xC4)는 SOF 범위 안에 있지만 크기 정보가 아니다."""
        data = jpeg_with_segments(segment(0xC4, b"\x00" * 30))

        assert read_dimensions(data) == (1080, 2340)

    def test_skips_arithmetic_coding_and_jpg_extension_markers(self):
        data = jpeg_with_segments(segment(0xC8, b"\x00" * 8), segment(0xCC, b"\x00" * 8))

        assert read_dimensions(data) == (1080, 2340)

    def test_tolerates_fill_bytes_before_a_marker(self):
        """마커 앞에 0xFF 패딩이 붙는 인코더가 있다."""
        data = jpeg_with_segments(b"\xff\xff\xff" + segment(0xE1, b"Exif\x00\x00"))

        assert read_dimensions(data) == (1080, 2340)

    def test_progressive_jpeg_is_readable(self):
        sof2 = b"\xff\xc2" + struct.pack(">HBHHB", 17, 8, 1600, 900, 3) + b"\x00" * 9
        data = b"\xff\xd8" + segment(0xE0, b"JFIF\x00") + sof2

        assert read_dimensions(data) == (900, 1600)

    def test_truncated_jpeg_returns_none(self):
        assert read_dimensions(b"\xff\xd8\xff\xe0\x00") is None

    def test_jpeg_without_sof_returns_none(self):
        data = b"\xff\xd8" + segment(0xE0, b"JFIF\x00" + b"\x00" * 40)

        assert read_dimensions(data) is None

    def test_zero_dimension_is_rejected(self):
        data = jpeg_with_segments(width=0, height=100)

        assert read_dimensions(data) is None


class TestWebpVariants:
    def test_reads_lossy_vp8(self):
        assert read_dimensions(webp_vp8(1080, 2340)) == (1080, 2340)

    def test_reads_lossless_vp8l(self):
        assert read_dimensions(webp_vp8l(800, 1600)) == (800, 1600)

    def test_unknown_chunk_returns_none(self):
        assert read_dimensions(webp(b"ANIM" + b"\x00" * 20)) is None

    def test_truncated_webp_returns_none(self):
        assert read_dimensions(webp(b"VP8 " + b"\x00" * 4)) is None

    def test_riff_without_webp_tag_is_not_an_image(self):
        assert detect_format(RIFF + struct.pack("<I", 4) + b"WAVE") is None


class TestPngEdges:
    def test_truncated_png_returns_none(self):
        assert read_dimensions(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) is None

    def test_png_without_ihdr_returns_none(self):
        data = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"XXXX" + b"\x00" * 20

        assert read_dimensions(data) is None

    def test_zero_dimension_is_rejected(self):
        data = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
        data += struct.pack(">II", 0, 100) + b"\x00" * 10

        assert read_dimensions(data) is None


class TestUnknownFormats:
    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"GIF89a",
            b"BM" + b"\x00" * 50,
            b"%PDF-1.4",
            b"MZ\x90\x00",
            b"\x00" * 32,
        ],
    )
    def test_returns_none_for_unsupported_payloads(self, data):
        assert detect_format(data) is None
        assert read_dimensions(data) is None
