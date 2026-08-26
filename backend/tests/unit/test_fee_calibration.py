"""친구비가 좁은 구간에 뭉치지 않는가.

**기여 격차는 그대로 두면 0 근처에 몰린다.** 실측에서 원시 격차가
-0.16 ~ +0.20 에 그쳤다. 그대로 금액으로 바꾸면 ±2만 원 안에 갇히고,
±100,000원이라는 상한에 영원히 닿지 못한다.

같은 결함을 답장 지연 점수에서 한 번 겪었다. 상한이 24시간이던 시절
6시간을 넘는 표본이 버려져 100점이 나올 수 없었다.

그래서 크기를 분위수로 바꿔 벌린다. `관계-점수-계산-규칙.md` 10.3.
"""

import random
import statistics

import pytest

from app.algorithm.calculator import calculate_scores
from app.algorithm.calculator.relationship import contribution_gap, friend_fee
from app.algorithm.rule.constants import FEE_MAX, FEE_MIN
from tests.fixtures.relationships import (
    ALL_CASES,
    DAY,
    HOUR,
    MINUTE,
    Pattern,
    analysis,
    build_conversation,
)


def simulate(count: int = 3_000) -> list[int]:
    """있을 법한 관계를 지어내 친구비 분포를 본다.

    양쪽 점수를 독립적으로 흔든다. 한쪽만 흔들면 격차가 늘 한 방향이라
    분포가 치우친다.
    """
    rng = random.Random(20260826)
    fees: list[int] = []
    for _ in range(count):
        gap = contribution_gap(
            analysis=_random_analysis(rng),
            my_count=rng.randint(1, 60),
            peer_count=rng.randint(1, 60),
            first_contact_ratio=rng.random(),
            replies=_replies(rng),
        )
        fees.append(friend_fee(gap))
    return sorted(fees)


def _random_analysis(rng: random.Random):
    """양쪽을 독립적으로 흔든다. 한쪽만 흔들면 격차가 늘 한 방향이다."""
    pair = lambda: (rng.randint(0, 100), rng.randint(0, 100))
    return analysis(
        tone=pair(),
        affection=pair(),
        effort=pair(),
        conflict=rng.randint(0, 100),
        depth=rng.randint(0, 100),
    )


def _replies(rng: random.Random):
    from app.domain.model.score import ReplySeconds

    def one():
        # 표본이 없는 경우도 섞는다. 실제로 흔하다
        return None if rng.random() < 0.15 else rng.randint(30, 12 * HOUR)

    return ReplySeconds(me=one(), peer=one())


class TestSpread:
    def test_금액이_한곳에_뭉치지_않는다(self):
        fees = simulate()
        low, high = fees[len(fees) // 4], fees[3 * len(fees) // 4]

        assert high - low >= 30_000, f"중간 50%가 {low:,}~{high:,}원에 갇혔다"

    def test_양쪽_끝이_모두_쓰인다(self):
        fees = simulate()

        assert min(fees) <= -60_000, f"가장 낮은 값이 {min(fees):,}원뿐이다"
        assert max(fees) >= 60_000, f"가장 높은 값이 {max(fees):,}원뿐이다"

    def test_0원_근처가_지나치게_두껍지_않다(self):
        # 대부분이 0원이면 부호가 정보를 주지 못한다
        fees = simulate()
        near_zero = sum(1 for f in fees if abs(f) < 5_000)

        assert near_zero / len(fees) < 0.30, f"{near_zero / len(fees):.0%}가 ±5천원 안"

    def test_부호가_한쪽으로_치우치지_않는다(self):
        fees = simulate()
        positive = sum(1 for f in fees if f > 0)

        assert 0.40 < positive / len(fees) < 0.60, f"양수 비율 {positive / len(fees):.0%}"

    def test_범위를_벗어나지_않는다(self):
        fees = simulate()

        assert FEE_MIN <= min(fees) and max(fees) <= FEE_MAX


class TestCalibrationConstant:
    def test_문서가_말한_표준편차와_실측이_맞는다(self):
        """`FEE_GAP_STDDEV` 는 측정해서 정한 값이다.

        모델을 바꾸면 `effortLevel`·`affectionSignals` 분포가 달라져 이
        값이 어긋난다. 그때 이 테스트가 먼저 깨진다.
        """
        from app.algorithm.rule.constants import FEE_GAP_STDDEV

        rng = random.Random(20260826)
        gaps = []
        for _ in range(3_000):
            gaps.append(
                abs(
                    contribution_gap(
                        analysis=_random_analysis(rng),
                        my_count=rng.randint(1, 60),
                        peer_count=rng.randint(1, 60),
                        first_contact_ratio=rng.random(),
                        replies=_replies(rng),
                    )
                )
            )
        measured = statistics.pstdev(gaps)

        assert measured == pytest.approx(FEE_GAP_STDDEV, abs=0.08), (
            f"실측 {measured:.3f} vs 상수 {FEE_GAP_STDDEV}"
        )


class TestRealPatterns:
    @pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.key)
    def test_실제_같은_패턴도_범위_안이다(self, case):
        scores = calculate_scores(build_conversation(case.pattern), case.analysis)

        assert FEE_MIN <= scores.friend_fee <= FEE_MAX
