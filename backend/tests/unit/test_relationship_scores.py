"""친밀도·손절 위험도·친구비·신뢰도 산식.

관계 점수 계산 규칙 8~11장. 기대값은 문서 13장의 계산 예제를 그대로 옮긴 것이다.
문서와 이 파일이 어긋나면 둘 중 하나가 틀린 것이다.
"""

import pytest

from app.algorithm.calculator.relationship import (
    breakup_risk,
    confidence_of,
    friend_fee,
    intimacy,
    money_risk_score,
    promise_break_score,
    reply_delay_score,
)
from app.domain.model.conversation import ConversationMeta
from app.domain.value_object.enums import Confidence
from tests.builders import analysis

SPEC_BALANCE = 74
SPEC_PEER_REPLY = 1860
SPEC_FIRST_CONTACT = 0.63


def meta(message_count: int, time_coverage: float, sampled: bool = False) -> ConversationMeta:
    return ConversationMeta(
        image_count=5,
        message_count=message_count,
        dropped_count=0,
        sampled=sampled,
        time_coverage=time_coverage,
        span_seconds=1_209_600,
    )


class TestIntimacy:
    def test_worked_example_from_spec(self):
        assert intimacy(analysis(), SPEC_BALANCE) == 64

    def test_all_maximum_gives_hundred(self):
        perfect = analysis(tone=(100, 100), affection=(100, 100), depth=100)
        assert intimacy(perfect, 100) == 100

    def test_all_minimum_gives_zero(self):
        empty = analysis(tone=(0, 0), affection=(0, 0), depth=0)
        assert intimacy(empty, 0) == 0


class TestReplyDelayScore:
    @pytest.mark.parametrize(
        "seconds, expected",
        [
            (None, 0),
            (60, 0),
            (300, 0),
            (900, 26),
            (1800, 42),
            (SPEC_PEER_REPLY, 43),
            (3600, 58),
            (7200, 74),
            (21600, 100),
        ],
    )
    def test_log_scale_matches_spec_table(self, seconds, expected):
        assert reply_delay_score(seconds) == expected

    def test_beyond_ceiling_stays_at_hundred(self):
        assert reply_delay_score(86_400) == 100


class TestPromiseBreakScore:
    def test_worked_example_from_spec(self):
        # 6번 제안, 2번 무산
        assert promise_break_score(analysis().promise_signals) == 33

    def test_no_proposals_is_zero(self):
        assert promise_break_score(analysis(promises=(0, 0, 0)).promise_signals) == 0

    def test_all_declined_is_hundred(self):
        assert promise_break_score(analysis(promises=(4, 0, 4)).promise_signals) == 100


class TestMoneyRiskScore:
    def test_unresolved_loan_is_hundred(self):
        assert money_risk_score(analysis(money=(1, 0, 0)).money_signals) == 100

    def test_no_loan_is_zero(self):
        assert money_risk_score(analysis(money=(0, 0, 0)).money_signals) == 0

    def test_half_resolved_is_half(self):
        assert money_risk_score(analysis(money=(2, 0, 1)).money_signals) == 50

    def test_over_resolved_does_not_go_negative(self):
        assert money_risk_score(analysis(money=(1, 0, 3)).money_signals) == 0


class TestBreakupRisk:
    def test_worked_example_from_spec(self):
        assert (
            breakup_risk(analysis(), SPEC_BALANCE, SPEC_PEER_REPLY, SPEC_FIRST_CONTACT)
            == 38
        )

    def test_ideal_relationship_is_zero(self):
        ideal = analysis(effort=(100, 100), conflict=0, promises=(5, 5, 0), money=(0, 0, 0))
        assert breakup_risk(ideal, 100, 60, 0.5) == 0

    def test_worst_relationship_is_hundred(self):
        worst = analysis(effort=(0, 0), conflict=100, promises=(5, 0, 5), money=(3, 0, 0))
        # 먼저 연락까지 완전히 한쪽으로 기운 경우
        assert breakup_risk(worst, 0, 21_600, 1.0) == 100


class TestFriendFee:
    """친구비는 **정산액이다.** 품질이 아니라 기여 격차를 잰다.

    v1.5 이전에는 `intimacy`·`contactBalance`·`breakupRisk` 의 함수라
    친밀도와 거의 같은 정보를 보여줬다. 지표 하나를 두 번 보여준 셈이다.
    `관계-점수-계산-규칙.md` 10.1.
    """

    def test_기여가_같으면_0원이다(self):
        # 서로 빚진 것이 없다
        assert friend_fee(0.0) == 0

    def test_내가_더_기여하면_상대가_낸다(self):
        assert friend_fee(0.4) > 0

    def test_상대가_더_기여하면_내가_낸다(self):
        assert friend_fee(-0.4) < 0

    def test_양_끝에_도달한다(self):
        # 닿지 못하는 상한을 만든 적이 있다. 같은 실수를 막는다
        assert friend_fee(1.0) == 100_000
        assert friend_fee(-1.0) == -100_000

    def test_rounds_to_thousand_won(self):
        assert friend_fee(0.37) % 1_000 == 0


class TestConfidence:
    def test_worked_example_from_spec(self):
        assert confidence_of(meta(184, 0.91), session_count=19) is Confidence.HIGH

    def test_enough_messages_but_poor_time_coverage_is_medium(self):
        assert confidence_of(meta(184, 0.3), session_count=19) is Confidence.MEDIUM

    def test_few_messages_but_good_time_coverage_is_medium(self):
        assert confidence_of(meta(20, 0.91), session_count=19) is Confidence.MEDIUM

    def test_neither_is_low(self):
        assert confidence_of(meta(20, 0.3), session_count=19) is Confidence.LOW

    def test_sampling_downgrades_one_step(self):
        assert confidence_of(meta(184, 0.91, sampled=True), session_count=19) is Confidence.MEDIUM

    def test_too_few_sessions_forces_low(self):
        assert confidence_of(meta(184, 0.91), session_count=2) is Confidence.LOW
