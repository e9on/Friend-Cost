"""평가용 대화 생성기 검증.

이 도구가 틀리면 **모델 선정이 틀린다.** 순위 일치도가 모델을 떨어뜨리거나
붙이는 근거이므로, 그 계산이 맞는지부터 잠근다.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from samples import PROFILES, build, concordance  # noqa: E402

from app.domain.value_object.enums import Speaker, TimeSource


class TestConcordance:
    def test_기대_순서와_같으면_전부_일치한다(self):
        assert concordance([(1, 90), (2, 80), (3, 70)]) == (3, 3)

    def test_기대_순서와_반대면_하나도_일치하지_않는다(self):
        assert concordance([(1, 70), (2, 80), (3, 90)]) == (0, 3)

    def test_값이_같은_쌍은_세지_않는다(self):
        # 모든 대화에 같은 값을 내놓는 모델은 '틀리지 않았다'가 아니라
        # '판단하지 않았다'다. 분모에서 빼야 일치율이 부풀지 않는다
        assert concordance([(1, 80), (2, 80), (3, 80)]) == (0, 0)

    def test_한_쌍만_뒤집히면_그_쌍만_빠진다(self):
        assert concordance([(1, 90), (2, 70), (3, 80)]) == (2, 3)


class TestProfiles:
    def test_기대_순위가_중복되지_않는다(self):
        ranks = [profile.rank for profile in PROFILES]
        assert sorted(ranks) == list(range(1, len(PROFILES) + 1))

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_같은_씨앗은_같은_대화를_만든다(self, profile):
        assert build(profile, seed=3) == build(profile, seed=3)

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_시각이_거꾸로_흐르지_않는다(self, profile):
        stamps = [message.sent_at for message in build(profile).messages]
        assert stamps == sorted(stamps)

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_양쪽_화자가_모두_등장한다(self, profile):
        speakers = {message.speaker for message in build(profile).messages}
        assert speakers == {Speaker.ME, Speaker.PEER}

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_메타가_메시지와_맞는다(self, profile):
        convo = build(profile)
        assert convo.meta.message_count == len(convo.messages)
        assert convo.meta.image_count == convo.messages[-1].image_index + 1
        assert all(m.time_source is TimeSource.EXPLICIT for m in convo.messages)

    def test_절친이_일방적보다_자주_주고받는다(self):
        # 프로필 상수를 잘못 만지면 스펙트럼이 뒤집힌다. 그 상태로 평가를
        # 돌리면 멀쩡한 모델이 떨어진다.
        #
        # 총량이 아니라 **밀도**로 비교하는 이유는, 뜸한 관계도 오래 스크롤해
        # 캡처하면 메시지 수는 늘기 때문이다. "자주"는 기간당 횟수다
        def per_day(convo):
            return convo.meta.message_count / max(1, convo.meta.span_seconds / 86400)

        assert per_day(build(PROFILES[0])) > per_day(build(PROFILES[-2])) * 10


class TestProfilesPassAnalysis:
    """프로필이 실제 파이프라인을 통과하는지.

    분량이 모자라면 `TOO_FEW_MESSAGES` 로 떨어진다. 하필 소원·일방적처럼
    스펙트럼 아래쪽이 먼저 걸리는데, 그게 빠지면 변별력을 잴 수 없다.
    """

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_최소_메시지_수를_넉넉히_넘는다(self, profile):
        from app.algorithm.rule.constants import MIN_MESSAGES

        count = build(profile).meta.message_count
        assert count >= MIN_MESSAGES + 5, f"{profile.key}: {count}개"

    @pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.key)
    def test_점수_계산까지_통과한다(self, profile):
        from app.algorithm.calculator import calculate_scores
        from app.domain.model.analysis import (
            MoneySignals,
            PromiseSignals,
            RelationshipAnalysisData,
            SpeakerScores,
        )

        neutral = RelationshipAnalysisData(
            emotional_tone=SpeakerScores(me=50, peer=50),
            affection_signals=SpeakerScores(me=50, peer=50),
            effort_level=SpeakerScores(me=50, peer=50),
            conflict_level=20,
            topic_depth=50,
            promise_signals=PromiseSignals(proposed=0, fulfilled=0, declined=0),
            money_signals=MoneySignals(lent=0, borrowed=0, resolved=0),
        )
        scores = calculate_scores(build(profile), neutral)
        assert 0 <= scores.intimacy <= 100
