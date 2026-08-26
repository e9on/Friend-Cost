"""친구비가 기여 격차를 재는지.

**부호가 뜻을 갖는다.** 양수면 상대가 나에게, 음수면 내가 상대에게 내야
한다. 관계가 나쁘다는 뜻이 아니라 **누가 더 기여했는가**를 나타낸다.

옛 규칙에서 친구비는 `intimacy`·`contactBalance`·`breakupRisk` 의 함수라
친밀도와 거의 같은 정보를 보여줬다. 실측에서 친밀도 87·69·41·40·38·34 에
대해 친구비가 93,000·88,000·29,000·34,000·17,000·22,000 으로 거의 단조였다.
지표 하나를 두 번 보여준 셈이다.

`관계-점수-계산-규칙.md` 10장.
"""

import pytest

from app.algorithm.calculator.relationship import contribution_gap, friend_fee
from app.domain.model.analysis import (
    MoneySignals,
    PromiseSignals,
    RelationshipAnalysisData,
    SpeakerScores,
)
from app.domain.model.score import FEE_MAX, FEE_MIN, ReplySeconds


def analysis(*, effort=(50, 50), affection=(50, 50)) -> RelationshipAnalysisData:
    return RelationshipAnalysisData(
        emotional_tone=SpeakerScores(me=50, peer=50),
        affection_signals=SpeakerScores(me=affection[0], peer=affection[1]),
        effort_level=SpeakerScores(me=effort[0], peer=effort[1]),
        conflict_level=10,
        topic_depth=50,
        promise_signals=PromiseSignals(proposed=0, fulfilled=0, declined=0),
        money_signals=MoneySignals(lent=0, borrowed=0, resolved=0),
    )


def gap(**kwargs) -> float:
    base = dict(
        analysis=analysis(),
        my_count=10,
        peer_count=10,
        first_contact_ratio=0.5,
        replies=ReplySeconds(me=600, peer=600),
    )
    base.update(kwargs)
    return contribution_gap(**base)


class TestDirection:
    def test_완전히_대칭이면_0이다(self):
        assert gap() == pytest.approx(0.0, abs=1e-9)

    def test_내가_더_노력하면_양수다(self):
        assert gap(analysis=analysis(effort=(80, 20))) > 0

    def test_상대가_더_노력하면_음수다(self):
        assert gap(analysis=analysis(effort=(20, 80))) < 0

    def test_내가_더_많이_말하면_양수다(self):
        assert gap(my_count=30, peer_count=10) > 0

    def test_내가_더_먼저_걸면_양수다(self):
        assert gap(first_contact_ratio=0.9) > 0

    def test_내가_더_빨리_답하면_양수다(self):
        assert gap(replies=ReplySeconds(me=60, peer=3600)) > 0

    def test_모든_신호가_한쪽이면_격차가_크다(self):
        both = gap(
            analysis=analysis(effort=(95, 5), affection=(95, 5)),
            my_count=40,
            peer_count=2,
            first_contact_ratio=1.0,
            replies=ReplySeconds(me=30, peer=86_400),
        )
        assert both > 0.7, f"극단인데 {both:.2f}"


class TestUnknownIsNotAGap:
    """모르는 것을 격차로 치지 않는다."""

    @pytest.mark.parametrize(
        "replies",
        [
            ReplySeconds(me=None, peer=600),
            ReplySeconds(me=600, peer=None),
            ReplySeconds(me=None, peer=None),
        ],
    )
    def test_답장_표본이_한쪽이라도_없으면_그_항은_0이다(self, replies):
        # 격차는 양쪽을 견줘야 나온다. 한쪽이 비면 견줄 수가 없다
        assert gap(replies=replies) == pytest.approx(0.0, abs=1e-9)

    def test_메시지가_없으면_그_항은_0이다(self):
        assert gap(my_count=0, peer_count=0) == pytest.approx(0.0, abs=1e-9)


class TestFriendFee:
    def test_대칭이면_0원이다(self):
        assert friend_fee(0.0) == 0

    def test_부호가_보존된다(self):
        assert friend_fee(0.3) > 0
        assert friend_fee(-0.3) < 0

    def test_크기가_같으면_금액도_대칭이다(self):
        assert friend_fee(0.4) == -friend_fee(-0.4)

    def test_상한과_하한에_도달한다(self):
        # 옛 규칙에서 도달 불가능한 상한을 만든 적이 있다. 같은 실수를 막는다
        assert friend_fee(1.0) == FEE_MAX
        assert friend_fee(-1.0) == FEE_MIN

    def test_범위를_벗어나지_않는다(self):
        for raw in (-5.0, -1.0, -0.01, 0.0, 0.01, 1.0, 5.0):
            assert FEE_MIN <= friend_fee(raw) <= FEE_MAX

    def test_천원_단위다(self):
        for raw in (0.13, 0.27, -0.41, 0.66):
            assert friend_fee(raw) % 1_000 == 0

    def test_격차가_클수록_금액도_크다(self):
        fees = [friend_fee(g) for g in (0.05, 0.15, 0.30, 0.50, 0.80)]
        assert fees == sorted(fees), fees

    def test_아주_작은_격차는_작은_금액이다(self):
        """보정이 지나치면 거의 대칭인 관계도 큰 금액이 된다.

        경계값은 추측하지 않는다. 처음에 "격차 0.15면 상한의 절반 미만"
        이라고 적었다가 깨졌다. 측정된 표준편차가 0.125 이므로 0.15 는
        오히려 평균보다 큰 격차였다. 지금은 표준편차의 4분의 1 지점만
        본다. 그 정도는 누가 봐도 작은 기울기다.
        """
        from app.algorithm.rule.constants import FEE_GAP_STDDEV

        assert abs(friend_fee(FEE_GAP_STDDEV / 4)) < FEE_MAX * 0.3
