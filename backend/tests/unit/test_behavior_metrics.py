"""LLM 없이 코드만으로 계산되는 행동 지표.

관계 점수 계산 규칙 4~7장.
"""

import pytest

from app.algorithm.calculator.behavior import (
    contact_balance,
    first_contact_ratio,
    reply_seconds,
    split_sessions,
)
from app.domain.value_object.enums import Speaker
from tests.builders import BASE_TS, DAY, HOUR, MINUTE, alternating, conversation, msg


class TestSplitSessions:
    def test_gap_over_six_hours_starts_new_session(self):
        convo = conversation(
            [
                msg(0, Speaker.ME, BASE_TS),
                msg(1, Speaker.PEER, BASE_TS + 10 * MINUTE),
                msg(2, Speaker.ME, BASE_TS + 10 * MINUTE + 7 * HOUR),
            ]
        )

        sessions = split_sessions(convo)

        assert len(sessions) == 2
        assert [m.index for m in sessions[0]] == [0, 1]
        assert [m.index for m in sessions[1]] == [2]

    def test_gap_of_exactly_six_hours_stays_in_same_session(self):
        convo = conversation(
            [msg(0, Speaker.ME, BASE_TS), msg(1, Speaker.PEER, BASE_TS + 6 * HOUR)]
        )

        assert len(split_sessions(convo)) == 1

    def test_messages_without_timestamp_are_excluded(self):
        convo = conversation(
            [msg(0, Speaker.ME, BASE_TS), msg(1, Speaker.PEER, None), msg(2, Speaker.ME, BASE_TS + MINUTE)]
        )

        sessions = split_sessions(convo)

        assert [m.index for session in sessions for m in session] == [0, 2]


class TestFirstContactRatio:
    def test_counts_sessions_started_by_me(self):
        convo = conversation(
            [
                msg(0, Speaker.ME, BASE_TS),
                msg(1, Speaker.PEER, BASE_TS + MINUTE),
                msg(2, Speaker.PEER, BASE_TS + DAY),
                msg(3, Speaker.ME, BASE_TS + DAY + MINUTE),
                msg(4, Speaker.ME, BASE_TS + 2 * DAY),
                msg(5, Speaker.ME, BASE_TS + 3 * DAY),
            ]
        )

        # 세션 4개 중 me가 시작한 것은 3개
        assert first_contact_ratio(convo) == pytest.approx(0.75)

    def test_returns_half_when_fewer_than_three_sessions(self):
        convo = conversation(
            [msg(0, Speaker.ME, BASE_TS), msg(1, Speaker.PEER, BASE_TS + MINUTE)]
        )

        assert first_contact_ratio(convo) == pytest.approx(0.5)


class TestReplySeconds:
    def test_measures_gap_from_last_message_of_previous_speaker(self):
        convo = conversation(
            [
                msg(0, Speaker.ME, BASE_TS),
                msg(1, Speaker.ME, BASE_TS + 60),
                msg(2, Speaker.PEER, BASE_TS + 360),
                msg(3, Speaker.ME, BASE_TS + 460),
                msg(4, Speaker.PEER, BASE_TS + 760),
                msg(5, Speaker.ME, BASE_TS + 860),
                msg(6, Speaker.PEER, BASE_TS + 1160),
            ]
        )

        result = reply_seconds(convo)

        # peer는 300초씩 세 번 답장했다
        assert result.peer == 300
        # me는 100초씩 두 번 — 표본 3개 미만이라 None
        assert result.me is None

    def test_gaps_longer_than_six_hours_are_discarded(self):
        convo = conversation(
            [
                msg(0, Speaker.ME, BASE_TS),
                msg(1, Speaker.PEER, BASE_TS + 7 * HOUR),
                msg(2, Speaker.ME, BASE_TS + 7 * HOUR + 60),
                msg(3, Speaker.PEER, BASE_TS + 7 * HOUR + 360),
                msg(4, Speaker.ME, BASE_TS + 7 * HOUR + 460),
                msg(5, Speaker.PEER, BASE_TS + 7 * HOUR + 760),
                msg(6, Speaker.ME, BASE_TS + 7 * HOUR + 860),
                msg(7, Speaker.PEER, BASE_TS + 7 * HOUR + 1160),
            ]
        )

        result = reply_seconds(convo)

        # 7시간 간격은 버려지고 300초 세 번만 남는다
        assert result.peer == 300

    def test_trims_slowest_ten_percent(self):
        # peer 답장 10개: 100초 아홉 번 + 6000초 한 번
        messages = []
        ts = BASE_TS
        idx = 0
        for gap in [100] * 9 + [6000]:
            messages.append(msg(idx, Speaker.ME, ts))
            idx += 1
            ts += gap
            messages.append(msg(idx, Speaker.PEER, ts))
            idx += 1
            ts += 30

        result = reply_seconds(conversation(messages))

        # 상위 10%(6000초 한 개)가 잘려서 100초만 남는다
        assert result.peer == 100

    def test_returns_none_without_timestamps(self):
        convo = conversation([msg(i, Speaker.ME if i % 2 == 0 else Speaker.PEER) for i in range(8)])

        result = reply_seconds(convo)

        assert result.me is None and result.peer is None


class TestContactBalance:
    @pytest.mark.parametrize(
        "count_me, count_peer, expected",
        [(50, 50, 100), (60, 40, 80), (70, 30, 60), (90, 10, 20), (100, 0, 0)],
    )
    def test_balance_reflects_message_share(self, count_me, count_peer, expected):
        messages = [msg(i, Speaker.ME, BASE_TS + i) for i in range(count_me)]
        messages += [
            msg(count_me + i, Speaker.PEER, BASE_TS + count_me + i) for i in range(count_peer)
        ]

        assert contact_balance(conversation(messages)) == expected

    def test_worked_example_from_spec(self):
        # 관계 점수 계산 규칙 13장: me 116 : peer 68 -> 74
        messages = [msg(i, Speaker.ME, BASE_TS + i) for i in range(116)]
        messages += [msg(116 + i, Speaker.PEER, BASE_TS + 116 + i) for i in range(68)]

        assert contact_balance(conversation(messages)) == 74

    def test_empty_conversation_is_balanced(self):
        assert contact_balance(conversation([])) == 0
