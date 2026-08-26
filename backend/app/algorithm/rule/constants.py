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

# 친구비 보정 곡선.
#
# 원시 품질 비율은 세 항의 곱이라 값이 가운데로 몰린다. 그대로 금액으로
# 바꾸면 중간 50%가 33,000~46,000원에 들어와서, 서로 다른 친구를 재도
# 비슷한 숫자만 나온다.
#
# 아래 두 값은 있을 법한 관계 3,000건을 시뮬레이션해 얻은 원시 비율의
# 평균과 표준편차다. 분포가 정규분포에 매우 가까워(최대 오차 0.013)
# 정규 CDF를 통과시키면 균등 분포가 되고, 친구비가 "상위 몇 %"라는
# 뜻을 갖게 된다.
#
# **이 값은 합성 데이터에서 얻은 것이다.** 실제 모델을 붙인 뒤 출력
# 분포가 다르면 다시 구해야 한다. tools/calibrate_fee.py 로 재산출한다.
FEE_CALIBRATION_MEAN: Final = 0.400
FEE_CALIBRATION_STDDEV: Final = 0.099

# 보정 곡선의 세기. 1.0이면 순수 분위수, 0.0이면 보정하지 않음.
#
# 순수 분위수를 쓰면 양 끝이 뭉개진다. 평균에서 2.5표준편차만 벗어나도
# 누적분포함수가 0이나 1에 붙어버려서, 서로 다른 좋은 관계가 전부 99,000원,
# 서로 다른 나쁜 관계가 전부 1,000원이 된다. 가운데를 벌리려다 양 끝을
# 잃는 셈이다.
#
# 그래서 원래 비율을 일부 섞는다. 가운데는 여전히 넓어지고, 양 끝에서는
# 원래 비율이 순서를 지켜준다.
FEE_CURVE_STRENGTH: Final = 0.7
FEE_MIN: Final = -100_000
FEE_MAX: Final = 100_000
FEE_UNIT: Final = 1_000  # 반올림 단위

# --- 기여 격차 (관계-점수-계산-규칙 10장) ---
#
# 친구비는 관계의 품질이 아니라 **누가 더 기여했는가**를 잰다. 양수면 상대가
# 나에게, 음수면 내가 상대에게 내야 한다.
#
# 품질을 재던 시절에는 친구비가 친밀도와 거의 같은 정보를 보여줬다. 실측에서
# 친밀도 87·69·41·40·38·34 에 친구비 93,000·88,000·29,000·34,000·17,000·22,000
# 이 대응했다. 지표 하나를 두 번 보여준 셈이다.
W_GAP_EFFORT: Final = 0.30
W_GAP_AFFECTION: Final = 0.20
W_GAP_MESSAGES: Final = 0.20
W_GAP_INITIATION: Final = 0.20
W_GAP_REPLY: Final = 0.10

# 답장 속도 격차의 로그 밑. 8배 차이가 나면 1.0에 닿는다
REPLY_GAP_BASE: Final = 8.0

# |rawGap| 의 표준편차. tools/calibrate_fee.py 로 측정해서 정한다.
# 손으로 정하면 실측 분포와 어긋나 상한에 닿지 못하거나 작은 격차가
# 금액을 다 먹는다.
# 2026-08-26 측정값. 있을 법한 관계 3,000건의 |rawGap| 표준편차다
FEE_GAP_STDDEV: Final = 0.125

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
    gap = (
        W_GAP_EFFORT
        + W_GAP_AFFECTION
        + W_GAP_MESSAGES
        + W_GAP_INITIATION
        + W_GAP_REPLY
    )
    for name, total in (("친밀도", intimacy), ("손절 위험도", risk), ("기여 격차", gap)):
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{name} 가중치 합이 1.00이 아니다: {total}")


_assert_weights_sum_to_one()
