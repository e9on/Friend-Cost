"""점수가 서로 다른 관계를 실제로 구분하는가.

산식이 맞게 계산되는지는 다른 테스트가 본다. 여기서 보는 것은 그 산식이
**의미 있는 차이를 만들어내는가**다.

어떤 대화를 넣어도 친밀도가 60~70만 나온다면 가중치가 잘못된 것이다.
그런데 결과는 그럴듯하게 나오므로 실제 캡처를 넣어봐도 알아채기 어렵다.
LLM 후보를 고를 때 "결과 분산"을 핵심 지표로 삼기로 했으면, 코드 쪽
절반도 같은 기준으로 재야 한다.
"""

import pytest

from app.algorithm.calculator import calculate_scores
from app.algorithm.calculator.relationship import contact_imbalance_score
from tests.fixtures.relationships import (
    ALL_CASES,
    BALANCED,
    BY_KEY,
    DAY,
    MINUTE,
    Pattern,
    build_conversation,
)


@pytest.fixture(scope="module")
def scores():
    return {case.key: calculate_scores(case.conversation(), case.analysis) for case in ALL_CASES}


class TestSpread:
    """지표가 좁은 구간에 몰려 있으면 사용자는 차이를 못 느낀다."""

    def test_friend_fee_covers_a_wide_range(self, scores):
        fees = [s.friend_fee for s in scores.values()]

        assert max(fees) - min(fees) >= 40_000, f"친구비가 {fees} 로 몰려 있다"

    def test_intimacy_covers_a_wide_range(self, scores):
        values = [s.intimacy for s in scores.values()]

        assert max(values) - min(values) >= 30, f"친밀도가 {values} 로 몰려 있다"

    def test_breakup_risk_covers_a_wide_range(self, scores):
        values = [s.breakup_risk for s in scores.values()]

        assert max(values) - min(values) >= 40, f"손절 위험도가 {values} 로 몰려 있다"

    def test_no_two_relationships_get_the_same_fee(self, scores):
        fees = [s.friend_fee for s in scores.values()]

        assert len(set(fees)) == len(fees), f"같은 친구비가 겹친다: {fees}"


class TestOrdering:
    """사람이 읽어서 납득할 순서로 나와야 한다."""

    def test_closer_relationships_are_worth_more(self, scores):
        assert (
            scores["close"].friend_fee
            > scores["balanced"].friend_fee
            > scores["fading"].friend_fee
            > scores["one_sided"].friend_fee
            > scores["conflict"].friend_fee
        )

    def test_intimacy_follows_the_same_order(self, scores):
        assert scores["close"].intimacy > scores["balanced"].intimacy
        assert scores["balanced"].intimacy > scores["fading"].intimacy
        assert scores["fading"].intimacy > scores["conflict"].intimacy

    def test_conflict_carries_the_highest_risk(self, scores):
        risks = {key: value.breakup_risk for key, value in scores.items()}

        assert risks["conflict"] == max(risks.values())
        assert risks["close"] == min(risks.values())

    def test_a_close_friend_is_not_flagged_as_risky(self, scores):
        assert scores["close"].breakup_risk < 20

    def test_a_broken_relationship_is_clearly_flagged(self, scores):
        assert scores["conflict"].breakup_risk > 60


class TestFirstContactMatters:
    """먼저 연락 비율이 점수에 반영되어야 한다.

    서비스가 대표 지표로 내세우는 값이 화면에 표시만 되고 계산에는 쓰이지
    않으면, "나만 먼저 연락하는 관계"와 "서로 번갈아 연락하는 관계"가
    같은 점수를 받는다. 사용자가 가장 알고 싶어 하는 차이가 사라진다.
    """

    def balanced_message_counts(self, me_starts_ratio: float):
        """턴 수를 짝수로 두면 누가 시작하든 메시지 수가 정확히 같다.

        메시지 수가 같아야 먼저 연락 비율의 효과만 따로 볼 수 있다.
        """
        return Pattern(
            sessions=12,
            turns_per_session=6,
            me_starts_ratio=me_starts_ratio,
            me_burst=1,
            peer_burst=1,
            my_reply_seconds=20 * MINUTE,
            peer_reply_seconds=25 * MINUTE,
            session_gap_seconds=5 * DAY,
        )

    def score_for(self, me_starts_ratio: float):
        convo = build_conversation(self.balanced_message_counts(me_starts_ratio))
        return calculate_scores(convo, BALANCED.analysis)

    def test_message_counts_really_are_equal(self):
        """이 테스트의 전제. 깨지면 아래 결과를 믿을 수 없다."""
        for ratio in (0.0, 0.5, 1.0):
            assert self.score_for(ratio).contact_balance == 100

    def test_always_initiating_raises_the_risk(self):
        mutual = self.score_for(0.5)
        only_me = self.score_for(1.0)

        assert only_me.breakup_risk > mutual.breakup_risk

    def test_always_initiating_lowers_the_fee(self):
        assert self.score_for(1.0).friend_fee < self.score_for(0.5).friend_fee

    def test_the_other_side_always_initiating_is_also_imbalance(self):
        """한쪽만 노력하는 관계는 방향과 무관하게 위태롭다."""
        only_peer = self.score_for(0.0)
        mutual = self.score_for(0.5)

        assert only_peer.breakup_risk > mutual.breakup_risk

    def test_mutual_initiation_is_the_healthiest(self):
        risks = [self.score_for(ratio).breakup_risk for ratio in (0.0, 0.25, 0.5, 0.75, 1.0)]

        assert risks[2] == min(risks), f"번갈아 연락이 가장 낮아야 한다: {risks}"


class TestContactImbalance:
    """연락 불균형은 메시지 수와 먼저 연락, 두 측면을 함께 본다."""

    @pytest.mark.parametrize(
        "balance, ratio, expected",
        [
            (100, 0.5, 0),  # 완전히 균형
            (0, 1.0, 100),  # 완전히 한쪽으로
            (100, 1.0, 50),  # 메시지 수는 같은데 항상 내가 먼저
            (0, 0.5, 50),  # 먼저 연락은 반반인데 메시지 수가 쏠림
            (74, 0.63, 26),  # 관계 점수 계산 규칙 13장의 예제
        ],
    )
    def test_combines_both_signals(self, balance, ratio, expected):
        assert contact_imbalance_score(balance, ratio) == expected

    def test_direction_does_not_matter(self):
        assert contact_imbalance_score(100, 0.9) == contact_imbalance_score(100, 0.1)


class TestSensitivity:
    """어떤 입력이 점수를 전혀 움직이지 않으면 그 항은 죽은 가중치다."""

    def base(self):
        return BY_KEY["balanced"]

    def shifted(self, **overrides):
        from tests.fixtures.relationships import analysis as make_analysis

        defaults = dict(
            tone=(70, 70),
            affection=(58, 58),
            effort=(65, 65),
            conflict=12,
            depth=60,
            promises=(5, 4, 1),
        )
        defaults.update(overrides)
        convo = self.base().conversation()
        return calculate_scores(convo, make_analysis(**defaults))

    def test_emotional_tone_moves_intimacy(self):
        low = self.shifted(tone=(20, 20)).intimacy
        high = self.shifted(tone=(95, 95)).intimacy

        assert high - low >= 20

    def test_affection_moves_intimacy(self):
        low = self.shifted(affection=(10, 10)).intimacy
        high = self.shifted(affection=(95, 95)).intimacy

        assert high - low >= 15

    def test_topic_depth_moves_intimacy(self):
        low = self.shifted(depth=10).intimacy
        high = self.shifted(depth=95).intimacy

        assert high - low >= 10

    def test_conflict_moves_risk(self):
        low = self.shifted(conflict=0).breakup_risk
        high = self.shifted(conflict=100).breakup_risk

        assert high - low >= 25

    def test_peer_effort_moves_risk(self):
        lazy = self.shifted(effort=(65, 5)).breakup_risk
        eager = self.shifted(effort=(65, 95)).breakup_risk

        assert lazy - eager >= 5

    def test_broken_promises_move_risk(self):
        kept = self.shifted(promises=(6, 6, 0)).breakup_risk
        broken = self.shifted(promises=(6, 0, 6)).breakup_risk

        assert broken - kept >= 10

    def test_unresolved_money_moves_risk(self):
        clean = self.shifted(money=(0, 0, 0)).breakup_risk
        owed = self.shifted(money=(3, 0, 0)).breakup_risk

        assert owed - clean >= 8
