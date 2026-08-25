"""감사 로그.

`운영-보안-법적고지-명세.md` 6.2. 원문 없이 요청 패턴만 남긴다.

무엇을 남기지 않는가:

- **대화 원문.** 기준 명세 5장.
- **업로드 파일명.** 사용자가 파일 이름에 상대방 이름을 넣는 경우가 많다.
- **`jobId`.** API 명세 2장. 별도 인증이 없어 `jobId` 자체가 접근 토큰이다.
  로그를 읽을 수 있는 사람이 남의 결과를 조회할 수 있게 된다.
- **IP 주소.** 요청 제한 목적으로만 쓰고 창이 지나면 폐기한다.

무엇을 남기는가:

- 어느 단계에서 실패했는가
- 얼마나 걸렸는가
- 이미지·메시지 수, 토큰 수 같은 집계값
- 오류 코드, 신뢰도 등급

이 정도면 "어느 단계가 자주 실패하는가", "비용이 어디서 나가는가"를 알 수 있다.
개별 사용자를 추적할 수는 없는데, 그것이 의도다.
"""

import logging
import re
from typing import Any, Final

logger = logging.getLogger("audit")

# 감사 로그에 들어갈 수 있는 문자열의 모양.
#
# 여기 담길 것은 오류 코드(`OCR_FAILED`), 단계 이름(`ocr`), 등급(`high`)처럼
# 정해진 식별자뿐이다. 그래서 ASCII 식별자만 허용한다.
#
# **길이로 막지 않는 이유**가 있다. 한글은 짧다. "오늘 진짜 힘들었는데"는
# 12자다. 길이 제한을 아무리 조여도 짧은 대화는 빠져나간다. 반면 대화에는
# 한글·공백·문장부호가 반드시 섞이므로, 허용 문자로 막으면 확실하다.
SAFE_VALUE: Final = re.compile(r"^[A-Za-z0-9_.:\-]{1,48}$")


class AuditEvent:
    """`이름 키=값 키=값` 한 줄.

    긴 문자열을 거부하는 이유는, 감사 로그가 원문이 새는 가장 흔한 경로이기
    때문이다. 규칙을 문서에만 적어두면 언젠가 누군가 어긴다.
    """

    def __init__(self, name: str, **fields: Any) -> None:
        self.name = name
        self.fields: dict[str, Any] = {}

        for key, value in fields.items():
            if value is None or value == "":
                continue
            if isinstance(value, str) and not SAFE_VALUE.match(value):
                raise ValueError(
                    f"감사 로그에는 정해진 식별자만 넣을 수 있다 ({key}={value!r}). "
                    "대화 원문이 섞여 들어갔을 수 있다."
                )
            self.fields[key] = value

    def __str__(self) -> str:
        pairs = " ".join(f"{key}={value}" for key, value in self.fields.items())
        return f"{self.name} {pairs}".strip()


def audit(name: str, **fields: Any) -> None:
    """감사 이벤트 한 줄을 남긴다."""
    logger.info("%s", AuditEvent(name, **fields))
