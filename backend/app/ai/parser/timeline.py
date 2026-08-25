"""캡처에 적힌 시각과 날짜를 읽고 절대 시각을 복원한다.

OCR·Parser 명세 5장.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Final

_TIME = re.compile(r"(?:(오전|오후)\s*)?(\d{1,2}):(\d{2})")
_DATE_KO = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_DATE_DOT = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?")

# 캡처에 날짜 구분선이 없을 때 쓰는 가상 기준일.
# 절대 날짜는 의미가 없고 간격만 유효하다. 결과 응답에 절대 시각은 노출되지 않는다.
VIRTUAL_EPOCH_DATE: Final = date(2000, 1, 1)

KST: Final = timezone(timedelta(hours=9))


def parse_time_of_day(text: str) -> tuple[int, int] | None:
    """`오전 9:15` / `21:15` 같은 표기에서 (시, 분)을 뽑는다.

    12시간제의 정오와 자정을 뒤집지 않도록 주의한다.
    오후 12시는 12시이고, 오전 12시는 0시다.
    """
    match = _TIME.search(text)
    if not match:
        return None

    meridiem, raw_hour, raw_minute = match.groups()
    hour, minute = int(raw_hour), int(raw_minute)

    if minute > 59:
        return None

    if meridiem is None:
        return (hour, minute) if hour <= 23 else None

    if hour < 1 or hour > 12:
        return None
    if meridiem == "오전":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return hour, minute


def parse_date_line(text: str) -> date | None:
    """날짜 구분선에서 날짜를 뽑는다. 연도가 없으면 날짜로 보지 않는다."""
    stripped = text.strip()
    for pattern in (_DATE_KO, _DATE_DOT):
        match = pattern.search(stripped)
        if match:
            year, month, day = (int(group) for group in match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def to_epoch(day: date, hour: int, minute: int) -> int:
    """한국 시간대 기준으로 Unix epoch 초를 만든다."""
    return int(datetime.combine(day, time(hour, minute), tzinfo=KST).timestamp())
