"""답장 지연 점수에서 "모른다"와 "답하지 않았다"를 가른다.

세 상수가 모두 6시간이다. `SESSION_GAP_SECONDS` 가 세션 경계를 정하고,
그 경계가 곧 답장으로 인정하는 상한이며, 점수 100 지점도 같다. 그래서
6시간을 **넘긴** 간격은 표본에서 통째로 사라진다.

사라진 표본을 `None` 으로 받아 0점을 주면, **답장이 느릴수록 위험이
낮아진다.** 2026-08-26 실측에서 소원해지는 중(2~12시간)과 일방적
(4~24시간)이 지연 점수 0을 받았다. 같은 표에서 용건 위주(1.1시간)는
61이었다. 반나절씩 답하지 않는 상대가 "위험 없음"으로 나온 것이다.

`관계-점수-계산-규칙.md` 8장.
"""

import pytest

from app.algorithm.calculator.behavior import peer_reply_chances, reply_seconds
from app.algorithm.calculator.relationship import reply_delay_score
from app.algorithm.rule.constants import MIN_REPLY_SAMPLES, REPLY_MAX_SECONDS
from app.domain.model.conversation import (
    ConversationData,
    ConversationMeta,
    Message,
)
from app.domain.value_object.enums import Speaker, TimeSource

BASE = 1_756_000_000


def conversation(gaps_hours: list[float]) -> ConversationData:
    """나와 상대가 번갈아 말하는 대화. 간격을 시간 단위로 준다."""
    messages: list[Message] = []
    now = BASE
    speaker = Speaker.ME
    for index, gap in enumerate([0.0, *gaps_hours]):
        now += int(gap * 3600)
        messages.append(
            Message(
                index=index,
                speaker=speaker,
                text="ㅇㅇ",
                sent_at=now,
                time_source=TimeSource.EXPLICIT,
                image_index=0,
            )
        )
        speaker = Speaker.PEER if speaker is Speaker.ME else Speaker.ME

    return ConversationData(
        messages=tuple(messages),
        meta=ConversationMeta(
            image_count=1,
            message_count=len(messages),
            dropped_count=0,
            time_coverage=1.0,
            span_seconds=messages[-1].sent_at - messages[0].sent_at,
        ),
    )


class TestPeerReplyChances:
    def test_상대가_답할_차례였던_횟수를_센다(self):
        # 나 → 상대 → 나 → 상대: 상대가 답할 차례는 두 번
        convo = conversation([0.5, 0.5, 0.5])

        assert peer_reply_chances(convo) == 2

    def test_간격이_길어도_차례는_차례다(self):
        # 표본에서는 버려지지만 기회가 있었다는 사실은 남는다
        convo = conversation([20.0, 20.0, 20.0])

        assert peer_reply_chances(convo) == 2

    def test_시각이_없으면_세지_않는다(self):
        convo = conversation([0.5, 0.5])
        stripped = convo.model_copy(
            update={
                "messages": tuple(
                    message.model_copy(
                        update={"sent_at": None, "time_source": TimeSource.UNKNOWN}
                    )
                    for message in convo.messages
                )
            }
        )

        assert peer_reply_chances(stripped) == 0


class TestReplyDelayScore:
    def test_기회가_충분한데_표본이_없으면_최대_위험이다(self):
        chances = MIN_REPLY_SAMPLES

        assert reply_delay_score(None, chances=chances) == 100

    def test_기회가_모자라면_모르는_것으로_둔다(self):
        # 한두 번의 공백으로 단정하지 않는다
        assert reply_delay_score(None, chances=MIN_REPLY_SAMPLES - 1) == 0

    def test_기회를_주지_않으면_예전처럼_0이다(self):
        # 기존 호출부를 깨지 않는다
        assert reply_delay_score(None) == 0

    @pytest.mark.parametrize("seconds,expected", [(300, 0), (REPLY_MAX_SECONDS, 100)])
    def test_표본이_있으면_기회는_영향을_주지_않는다(self, seconds, expected):
        assert reply_delay_score(seconds, chances=99) == expected


class TestNoInversion:
    """느릴수록 위험이 높아야 한다. 이 성질이 깨진 적이 있다."""

    def test_느린_상대가_빠른_상대보다_위험하다(self):
        fast = conversation([0.1] * 8)
        slow = conversation([12.0] * 8)

        fast_score = reply_delay_score(
            reply_seconds(fast).peer, chances=peer_reply_chances(fast)
        )
        slow_score = reply_delay_score(
            reply_seconds(slow).peer, chances=peer_reply_chances(slow)
        )

        assert slow_score > fast_score, (
            f"12시간 걸리는 상대({slow_score})가 6분 걸리는 상대({fast_score})보다 "
            "위험하지 않게 나왔다"
        )
