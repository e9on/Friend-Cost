"""친구비가 좁은 구간에 뭉치지 않는가.

산식의 원시 비율은 세 항의 곱이라 값이 가운데로 몰린다. 시뮬레이션에서
중간 50%가 33,000~46,000원에 들어왔다. 내 친구 셋을 재서 38,000·41,000·
44,000이 나오면 서비스는 아무것도 알려주지 못한 것이다.

그래서 원시 비율을 **분위수로 바꿔서** 보여준다. 친구비 80,000원은
"우리가 본 관계 분포에서 상위 20% 언저리"라는 뜻이 된다.
"""

import random
import statistics

import pytest

from app.algorithm.calculator import calculate_scores
from app.algorithm.calculator.relationship import friend_fee, quality_ratio
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


def clamp(value: int) -> int:
    return max(0, min(100, value))


def random_scores(count: int, seed: int = 42):
    """있을 법한 범위에서 관계를 무작위로 만들어 점수를 낸다."""
    rng = random.Random(seed)
    results = []
    for _ in range(count):
        pattern = Pattern(
            sessions=rng.randint(5, 25),
            turns_per_session=rng.randint(3, 8),
            me_starts_ratio=rng.uniform(0.2, 0.9),
            me_burst=rng.randint(1, 3),
            peer_burst=rng.randint(1, 3),
            my_reply_seconds=rng.randint(2 * MINUTE, 3 * HOUR),
            peer_reply_seconds=rng.randint(2 * MINUTE, 5 * HOUR),
            session_gap_seconds=rng.randint(1, 20) * DAY,
        )
        tone = rng.randint(30, 95)
        affection = rng.randint(15, 90)
        effort = rng.randint(25, 95)
        proposed = rng.randint(0, 8)
        declined = rng.randint(0, proposed)
        data = analysis(
            tone=(tone, clamp(tone + rng.randint(-20, 10))),
            affection=(affection, clamp(affection + rng.randint(-25, 10))),
            effort=(effort, clamp(effort + rng.randint(-30, 10))),
            conflict=rng.randint(0, 80),
            depth=rng.randint(20, 90),
            promises=(proposed, proposed - declined, declined),
            money=(rng.randint(0, 2), 0, 0),
        )
        results.append(calculate_scores(build_conversation(pattern), data))
    return results


@pytest.fixture(scope="module")
def sample():
    return random_scores(400)


class TestSpread:
    def test_the_middle_half_is_not_squeezed(self, sample):
        """전형적인 관계들이 서로 구분되어야 한다.

        여기가 좁으면 대부분의 사용자가 비슷한 숫자를 받는다.
        """
        fees = sorted(s.friend_fee for s in sample)
        low = fees[len(fees) // 4]
        high = fees[len(fees) * 3 // 4]

        assert high - low >= 30_000, f"중간 50%가 {low:,}~{high:,} 로 뭉쳐 있다"

    def test_uses_most_of_the_available_range(self, sample):
        fees = [s.friend_fee for s in sample]

        span = max(fees) - min(fees)
        assert span >= (FEE_MAX - FEE_MIN) * 0.7, f"실제 폭이 {span:,} 뿐이다"

    def test_results_are_not_piled_on_one_value(self, sample):
        fees = [s.friend_fee for s in sample]
        most_common = max(fees.count(value) for value in set(fees))

        assert most_common / len(fees) < 0.1, "한 값에 10% 넘게 몰려 있다"


class TestCalibrationCurve:
    def test_median_quality_lands_near_the_middle(self):
        """분포의 한가운데인 관계는 친구비도 한가운데여야 한다."""
        from app.algorithm.rule.constants import FEE_CALIBRATION_MEAN

        fee = friend_fee_for_ratio(FEE_CALIBRATION_MEAN)

        assert 45_000 <= fee <= 55_000

    def test_is_monotone(self):
        """더 나은 관계가 더 낮은 친구비를 받으면 안 된다."""
        fees = [friend_fee_for_ratio(r / 100) for r in range(1, 100)]

        assert fees == sorted(fees)

    def test_respects_the_bounds(self):
        assert friend_fee_for_ratio(0.0) == FEE_MIN
        assert friend_fee_for_ratio(1.0) == FEE_MAX

    def test_rounds_to_thousand_won(self):
        for ratio in (0.2, 0.35, 0.5, 0.65, 0.8):
            assert friend_fee_for_ratio(ratio) % 1_000 == 0


def friend_fee_for_ratio(ratio: float) -> int:
    """원시 비율을 그대로 넣어 친구비를 본다.

    세 항의 곱이 `ratio` 가 되도록 균형도와 위험도를 최댓값으로 고정한다.
    """
    return friend_fee(round(ratio * 100), 100, 0)


class TestQualityRatio:
    def test_combines_the_three_terms(self):
        assert quality_ratio(64, 74, 38) == pytest.approx(0.64 * 0.87 * 0.81)

    def test_perfect_relationship_is_one(self):
        assert quality_ratio(100, 100, 0) == pytest.approx(1.0)

    def test_worst_relationship_is_zero(self):
        assert quality_ratio(0, 0, 100) == pytest.approx(0.0)


class TestOrderingSurvives:
    """분위수로 바꿔도 관계의 순서는 그대로여야 한다."""

    def test_relationship_types_keep_their_order(self):
        fees = {
            case.key: calculate_scores(case.conversation(), case.analysis).friend_fee
            for case in ALL_CASES
        }

        assert (
            fees["close"]
            > fees["balanced"]
            > fees["fading"]
            > fees["one_sided"]
            > fees["conflict"]
        )

    def test_still_deterministic(self):
        first = random_scores(20, seed=7)
        second = random_scores(20, seed=7)

        assert [s.friend_fee for s in first] == [s.friend_fee for s in second]


class TestOtherMetricsUnchanged:
    """친밀도와 위험도는 0~100 점수라 그대로 둔다.

    친구비만 분위수로 바꾸는 이유는, 그것만 '금액'이라는 형태 때문에
    폭이 넓어야 의미가 살기 때문이다. 점수는 100점 만점의 뜻이 이미 있다.
    """

    def test_intimacy_is_untouched(self):
        # 관계 점수 계산 규칙 13장의 예제. 친구비만 바꿨으므로 그대로여야 한다
        from app.algorithm.calculator.relationship import intimacy
        from tests.builders import analysis as spec_analysis

        assert intimacy(spec_analysis(), 74) == 64
