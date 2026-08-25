"""`ConversationData` + `RelationshipAnalysisData` -> `RelationshipScoreData`.

관계 점수 계산 규칙 2장의 계산 순서를 실제로 밟는지 확인한다.
"""

import pytest

from app.algorithm.calculator import calculate_scores
from app.algorithm.calculator.behavior import (
    contact_balance,
    first_contact_ratio,
    reply_seconds,
    split_sessions,
)
from app.algorithm.calculator.relationship import breakup_risk, friend_fee, intimacy
from app.common.errors import AppError, ErrorCode
from app.domain.value_object.enums import Confidence, Speaker
from tests.builders import BASE_TS, DAY, MINUTE, alternating, analysis, conversation, msg


def spec_like_conversation():
    """세션이 여러 개이고 양쪽이 모두 말하는 충분한 길이의 대화."""
    messages = []
    index = 0
    for day in range(8):
        start = BASE_TS + day * DAY
        for turn in range(8):
            speaker = Speaker.ME if turn % 2 == 0 else Speaker.PEER
            messages.append(msg(index, speaker, start + turn * 7 * MINUTE))
            index += 1
    return conversation(messages, image_count=5)


class TestCalculateScores:
    def test_composes_the_individual_metrics(self):
        convo = spec_like_conversation()
        data = analysis()

        scores = calculate_scores(convo, data)

        balance = contact_balance(convo)
        replies = reply_seconds(convo)
        expected_intimacy = intimacy(data, balance)
        expected_risk = breakup_risk(data, balance, replies.peer)

        assert scores.contact_balance == balance
        assert scores.avg_reply_seconds == replies
        assert scores.first_contact_ratio == first_contact_ratio(convo)
        assert scores.intimacy == expected_intimacy
        assert scores.breakup_risk == expected_risk
        assert scores.friend_fee == friend_fee(expected_intimacy, balance, expected_risk)

    def test_high_confidence_for_a_long_well_timed_conversation(self):
        scores = calculate_scores(spec_like_conversation(), analysis())

        assert scores.confidence is Confidence.HIGH

    def test_rejects_conversations_below_the_minimum(self):
        convo = conversation(alternating(14))

        with pytest.raises(AppError) as caught:
            calculate_scores(convo, analysis())

        assert caught.value.code is ErrorCode.TOO_FEW_MESSAGES

    def test_accepts_exactly_the_minimum(self):
        scores = calculate_scores(conversation(alternating(15)), analysis())

        assert scores.friend_fee >= 1_000

    def test_single_session_conversation_gets_low_confidence(self):
        # 15개가 5분 간격이면 세션은 하나뿐이다
        scores = calculate_scores(conversation(alternating(15)), analysis())

        assert len(split_sessions(conversation(alternating(15)))) == 1
        assert scores.confidence is Confidence.LOW

    def test_result_stays_within_contract_ranges(self):
        scores = calculate_scores(spec_like_conversation(), analysis())

        assert 1_000 <= scores.friend_fee <= 100_000
        assert 0 <= scores.intimacy <= 100
        assert 0 <= scores.breakup_risk <= 100
        assert 0.0 <= scores.first_contact_ratio <= 1.0
        assert 0 <= scores.contact_balance <= 100

    def test_is_deterministic(self):
        convo = spec_like_conversation()
        data = analysis()

        assert calculate_scores(convo, data) == calculate_scores(convo, data)
