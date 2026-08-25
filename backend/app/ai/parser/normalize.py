"""텍스트 정규화.

OCR·Parser 명세 8장.

반복 문자를 줄이면 감정 강도 정보를 일부 잃는다. 그래도 그렇게 하는 이유는
'ㅋ'가 서른 번 반복되는 메시지 하나가 토큰 수십 개를 먹는 비용이 더 크기 때문이다.
강도는 반복 여부(두 번으로 줄었는지)로 남는다.
"""

import re
from typing import Final

MAX_REPEAT: Final = 2

_URL = re.compile(r"https?://\S+")
_PHOTO = re.compile(r"^사진(\s*\d+\s*장)?$")
_EMOTICON = re.compile(r"^이모티콘$")
_VIDEO = re.compile(r"^동영상$")
_FILE = re.compile(r"^파일\s*[:：]")
_REPEAT = re.compile(r"(.)\1{" + str(MAX_REPEAT) + r",}")
_SPACES = re.compile(r"\s+")

_SYSTEM_PATTERNS: Final = (
    re.compile(r"삭제된 메시지입니다"),
    re.compile(r"님이 (들어왔|나갔)습니다"),
    re.compile(r"님을 초대했습니다"),
    re.compile(r"^읽지 않음$"),
    re.compile(r"^여기까지 읽었습니다$"),
    re.compile(r"^차단된 메시지입니다"),
)


def is_system_message(text: str) -> bool:
    """대화가 아니라 앱이 끼워 넣은 안내인지."""
    stripped = text.strip()
    return any(pattern.search(stripped) for pattern in _SYSTEM_PATTERNS)


def normalize_text(text: str) -> str:
    """메시지 본문을 정규화한다.

    빈 문자열이 반환되면 호출한 쪽에서 그 메시지를 버린다.
    """
    stripped = text.strip()
    if not stripped:
        return ""

    if _PHOTO.match(stripped):
        return "[사진]"
    if _EMOTICON.match(stripped):
        return "[이모티콘]"
    if _VIDEO.match(stripped):
        return "[동영상]"
    if _FILE.match(stripped):
        return "[파일]"

    result = _URL.sub("[링크]", stripped)
    result = _REPEAT.sub(lambda m: m.group(1) * MAX_REPEAT, result)
    result = _SPACES.sub(" ", result)
    return result.strip()
