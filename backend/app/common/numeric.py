"""반올림과 범위 제한.

파이썬 내장 ``round`` 는 은행가 반올림이라 ``round(0.5) == 0`` 이다.
점수 산식은 사람이 손으로 검산하는 문서를 따라야 하므로 항상 사사오입한다.
"""

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: float) -> int:
    """0.5는 항상 올린다."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_to_unit(value: float, unit: int) -> int:
    """`unit` 단위로 사사오입한다. 친구비의 1,000원 단위 반올림에 쓴다."""
    return round_half_up(value / unit) * unit


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_score(value: float) -> int:
    """0~100 정수 점수로 만든다."""
    return int(clamp(round_half_up(value), 0, 100))


def round_ratio(value: float) -> float:
    """비율은 소수 셋째 자리까지. 데이터 계약 2장."""
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
