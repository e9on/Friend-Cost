"""운영 종료일.

이 서비스는 기간을 정해두고 연다. 가장 위험한 것은 켜두고 잊는 것이다.
관심이 식었는데 서버는 계속 도는 상태가 되면, 남의 대화를 계속 받으면서
아무도 보지 않는다. 처리방침이 약속한 신고 응답과 72시간 통지가 그 사이
지켜지지 않는다.

날짜를 잊어도 서버가 먼저 멈추게 한다. 사람의 기억에 기대지 않는다.

`운영-보안-법적고지-명세.md` 6.2.2
"""

from datetime import date

import pytest

from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings
from app.application.service.service_window import ensure_open


class TestServiceWindow:
    def test_종료일이_비어_있으면_언제나_연다(self):
        ensure_open(Settings(service_end_date=None), today=date(2099, 1, 1))

    def test_종료일_당일은_아직_연다(self):
        """마지막 날 저녁에 들어온 사용자를 돌려보내지 않는다."""
        ensure_open(Settings(service_end_date=date(2026, 11, 30)), today=date(2026, 11, 30))

    def test_종료일_다음날부터_닫는다(self):
        with pytest.raises(AppError) as caught:
            ensure_open(Settings(service_end_date=date(2026, 11, 30)), today=date(2026, 12, 1))

        assert caught.value.code is ErrorCode.SERVICE_ENDED

    def test_종료_안내는_다시_시도하라고_하지_않는다(self):
        """끝난 서비스에 재시도를 권하면 사용자를 헛되이 붙잡는다."""
        from app.common.errors import http_status_of, is_retryable

        assert is_retryable(ErrorCode.SERVICE_ENDED) is False
        assert http_status_of(ErrorCode.SERVICE_ENDED) == 410
