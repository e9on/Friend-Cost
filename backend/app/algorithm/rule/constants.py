"""관계 점수 계산 규칙 3장의 상수.

가중치와 임계값을 코드 곳곳에 흩어놓지 않고 여기 한 곳에 모은다.
값을 바꾸면 `관계-점수-계산-규칙.md` 의 표와 계산 예시도 함께 고쳐야 한다.
"""

from typing import Final

# --- 시간 ---
SESSION_GAP_SECONDS: Final = 21_600  # 6시간. 이보다 벌어지면 새 대화 세션
REPLY_MAX_SECONDS: Final = 21_600  # 6시간. 이보다 늦으면 답장이 아니라 새 세션
REPLY_FLOOR_SECONDS: Final = 300  # 5분. 이하는 지연 점수 0
REPLY_CEIL_SECONDS: Final = 21_600  # 6시간. 이상은 지연 점수 100
TRIM_RATIO: Final = 0.10  # 절사평균에서 잘라낼 상위 비율

# --- 친구비 ---
FEE_BASE: Final = 100_000
FEE_MIN: Final = 1_000
FEE_MAX: Final = 100_000
FEE_UNIT: Final = 1_000  # 반올림 단위

# --- 표본 요건 ---
MIN_MESSAGES: Final = 15  # 미만이면 분석 거절
RELIABLE_MESSAGES: Final = 40  # 이상이어야 신뢰도 high 후보
MIN_REPLY_SAMPLES: Final = 3  # 미만이면 평균 답장 속도를 내지 않는다
MIN_SESSIONS: Final = 3  # 미만이면 먼저 연락 비율이 무의미
RELIABLE_TIME_COVERAGE: Final = 0.6

# --- 친밀도 가중치 (합 1.00) ---
W_INTIMACY_TONE: Final = 0.35
W_INTIMACY_AFFECTION: Final = 0.25
W_INTIMACY_BALANCE: Final = 0.20
W_INTIMACY_DEPTH: Final = 0.20

# --- 손절 위험도 가중치 (합 1.00) ---
W_RISK_CONFLICT: Final = 0.30
W_RISK_IMBALANCE: Final = 0.15
W_RISK_PEER_EFFORT: Final = 0.10
W_RISK_REPLY_DELAY: Final = 0.20
W_RISK_PROMISE: Final = 0.15
W_RISK_MONEY: Final = 0.10


def _assert_weights_sum_to_one() -> None:
    """가중치 합이 1.00이 아니면 점수 범위가 깨진다. 임포트 시점에 잡는다."""
    intimacy = (
        W_INTIMACY_TONE + W_INTIMACY_AFFECTION + W_INTIMACY_BALANCE + W_INTIMACY_DEPTH
    )
    risk = (
        W_RISK_CONFLICT
        + W_RISK_IMBALANCE
        + W_RISK_PEER_EFFORT
        + W_RISK_REPLY_DELAY
        + W_RISK_PROMISE
        + W_RISK_MONEY
    )
    for name, total in (("친밀도", intimacy), ("손절 위험도", risk)):
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{name} 가중치 합이 1.00이 아니다: {total}")


_assert_weights_sum_to_one()
