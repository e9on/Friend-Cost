"""콘솔 출력 인코딩 고정.

Windows 기본 콘솔은 cp949라 한글 외 문자(엠 대시 등)에서 터진다.
도구가 인코딩 오류로 죽는 것만큼 허무한 일이 없으므로 UTF-8로 맞춘다.
"""

import sys


def force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
