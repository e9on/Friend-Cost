"""화면이 보내는 사용 이벤트 이름.

`데이터-계약-명세.md` 12-1 이 정의처다.

**서버가 정한 목록만 받는다.** 아무 문자열이나 받으면 로그가 오염되고,
그 자체가 대화 원문이 새는 통로가 된다.

분석 시작·성공·실패는 여기 없다. 서버가 이미 안다. 같은 것을 두 곳에서
세면 숫자가 어긋난다.
"""

from enum import Enum


class UsageEvent(str, Enum):
    PAGE_VIEW = "page.view"
    CONSENT_AGREED = "consent.agreed"
    UPLOAD_SELECTED = "upload.selected"
    RESULT_VIEWED = "result.viewed"
    RESULT_SHARED = "result.shared"
    RESULT_SAVED = "result.saved"
