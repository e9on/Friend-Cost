"""운영 기간 판단.

이 서비스는 기간을 정해두고 연다. `운영-보안-법적고지-명세.md` 6.2.2
"""

from datetime import date, datetime, timedelta, timezone

from app.common.errors import AppError, ErrorCode
from app.config.settings import Settings

# 기준 시각은 한국 시간이다. UTC 로 두면 한국의 종료일 저녁이 이미 지난
# 날로 계산되어, 마지막 날 사용자가 하루 일찍 돌려보내진다
KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    return datetime.now(KST).date()


def ensure_open(settings: Settings, today: date | None = None) -> None:
    """종료일이 지났으면 막는다.

    **막는 것은 새 분석뿐이다.** 이미 진행 중인 작업의 상태 조회와 삭제는
    계속 동작한다. 종료일에 걸린 사용자가 자기 결과를 잃지 않게 한다.
    """
    end = settings.service_end_date
    if end is None:
        return
    # 종료일 당일은 아직 연다. 마지막 날 저녁 사용자를 돌려보내지 않는다
    if (today or today_kst()) > end:
        raise AppError(ErrorCode.SERVICE_ENDED)
