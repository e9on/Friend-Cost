"""관계 유형별 합성 대화.

점수 알고리즘이 **서로 다른 관계를 실제로 구분하는지** 확인하기 위한 것이다.

산식이 맞게 계산되는지는 이미 검증했다. 확인하지 않은 것은 그 산식이
의미 있는 차이를 만들어내는가다. 어떤 대화를 넣어도 친밀도가 60~70만
나온다면 가중치가 잘못된 것인데, 결과는 그럴듯하게 나오므로 실제 캡처를
넣어봐도 알아채기 어렵다.

여기서 만드는 것은 대화의 **행동 패턴**(메시지 수, 답장 속도, 세션)과
Analysis Agent가 그런 대화에서 뽑아낼 법한 **의미 판단**이다.
"""

from dataclasses import dataclass

from app.domain.model.analysis import (
    MoneySignals,
    PromiseSignals,
    RelationshipAnalysisData,
    SpeakerScores,
)
from app.domain.model.conversation import (
    ConversationData,
    ConversationMeta,
    Message,
)
from app.domain.value_object.enums import Speaker, TimeSource

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

BASE_TS = 1_755_000_000


@dataclass(frozen=True)
class Pattern:
    """대화의 행동 패턴."""

    sessions: int
    turns_per_session: int
    me_starts_ratio: float  # me가 시작하는 세션 비율
    me_burst: int  # me가 한 번에 연달아 보내는 메시지 수
    peer_burst: int
    my_reply_seconds: int
    peer_reply_seconds: int
    session_gap_seconds: int = 2 * DAY


def build_conversation(pattern: Pattern) -> ConversationData:
    """행동 패턴대로 대화를 조립한다."""
    messages: list[Message] = []
    now = BASE_TS
    index = 0

    for session in range(pattern.sessions):
        # 세션을 누가 여는지
        me_opens = session < round(pattern.sessions * pattern.me_starts_ratio)
        speaker = Speaker.ME if me_opens else Speaker.PEER

        for turn in range(pattern.turns_per_session):
            burst = pattern.me_burst if speaker is Speaker.ME else pattern.peer_burst
            for step in range(burst):
                messages.append(
                    Message(
                        index=index,
                        speaker=speaker,
                        text=f"세션{session} 턴{turn} {step}",
                        sent_at=now,
                        time_source=TimeSource.EXPLICIT,
                        image_index=0,
                    )
                )
                index += 1
                now += 30  # 연달아 보내는 간격

            # 상대가 답할 차례. 답장 속도만큼 지난다
            speaker = Speaker.PEER if speaker is Speaker.ME else Speaker.ME
            now += (
                pattern.peer_reply_seconds
                if speaker is Speaker.PEER
                else pattern.my_reply_seconds
            )

        now += pattern.session_gap_seconds

    stamps = [m.sent_at for m in messages]
    return ConversationData(
        messages=tuple(messages),
        meta=ConversationMeta(
            image_count=5,
            message_count=len(messages),
            dropped_count=0,
            sampled=False,
            time_coverage=1.0,
            span_seconds=max(stamps) - min(stamps) if len(stamps) >= 2 else None,
        ),
    )


def analysis(
    *,
    tone: tuple[int, int],
    affection: tuple[int, int],
    effort: tuple[int, int],
    conflict: int,
    depth: int,
    promises: tuple[int, int, int] = (0, 0, 0),
    money: tuple[int, int, int] = (0, 0, 0),
) -> RelationshipAnalysisData:
    return RelationshipAnalysisData(
        emotional_tone=SpeakerScores(me=tone[0], peer=tone[1]),
        affection_signals=SpeakerScores(me=affection[0], peer=affection[1]),
        effort_level=SpeakerScores(me=effort[0], peer=effort[1]),
        conflict_level=conflict,
        topic_depth=depth,
        promise_signals=PromiseSignals(
            proposed=promises[0], fulfilled=promises[1], declined=promises[2]
        ),
        money_signals=MoneySignals(lent=money[0], borrowed=money[1], resolved=money[2]),
        notable_moments=(),
    )


@dataclass(frozen=True)
class Case:
    """관계 유형 하나."""

    key: str
    label: str
    pattern: Pattern
    analysis: RelationshipAnalysisData

    def conversation(self) -> ConversationData:
        return build_conversation(self.pattern)


# --- 관계 유형들 ---
#
# 사람이 읽어서 "그렇겠네" 싶은 조합이어야 한다. 억지로 극단을 만들면
# 알고리즘이 구분하는 게 당연해져서 검증의 의미가 없다.

CLOSE = Case(
    key="close",
    label="자주 연락하는 가까운 친구",
    pattern=Pattern(
        sessions=20,
        turns_per_session=6,
        me_starts_ratio=0.5,
        me_burst=1,
        peer_burst=1,
        my_reply_seconds=4 * MINUTE,
        peer_reply_seconds=5 * MINUTE,
        session_gap_seconds=1 * DAY,
    ),
    analysis=analysis(
        tone=(85, 88),
        affection=(80, 82),
        effort=(85, 88),
        conflict=5,
        depth=80,
        promises=(8, 7, 1),
    ),
)

BALANCED = Case(
    key="balanced",
    label="가끔 보지만 편한 친구",
    pattern=Pattern(
        sessions=10,
        turns_per_session=5,
        me_starts_ratio=0.5,
        me_burst=1,
        peer_burst=1,
        my_reply_seconds=25 * MINUTE,
        peer_reply_seconds=30 * MINUTE,
        session_gap_seconds=5 * DAY,
    ),
    analysis=analysis(
        tone=(70, 70),
        affection=(58, 58),
        effort=(65, 65),
        conflict=12,
        depth=60,
        promises=(5, 4, 1),
    ),
)

FADING = Case(
    key="fading",
    label="요즘 뜸해진 친구",
    pattern=Pattern(
        sessions=6,
        turns_per_session=3,
        me_starts_ratio=0.5,
        me_burst=1,
        peer_burst=1,
        my_reply_seconds=90 * MINUTE,
        peer_reply_seconds=3 * HOUR,
        session_gap_seconds=20 * DAY,
    ),
    analysis=analysis(
        tone=(55, 50),
        affection=(35, 30),
        effort=(45, 35),
        conflict=20,
        depth=35,
        promises=(4, 1, 3),
    ),
)

ONE_SIDED = Case(
    key="one_sided",
    label="나만 노력하는 관계",
    pattern=Pattern(
        sessions=12,
        turns_per_session=4,
        me_starts_ratio=0.92,
        me_burst=3,  # 내가 연달아 여러 개 보낸다
        peer_burst=1,
        my_reply_seconds=3 * MINUTE,
        peer_reply_seconds=4 * HOUR,
        session_gap_seconds=4 * DAY,
    ),
    analysis=analysis(
        tone=(72, 45),
        affection=(75, 25),
        effort=(85, 25),
        conflict=25,
        depth=40,
        promises=(7, 2, 5),
    ),
)

CONFLICT = Case(
    key="conflict",
    label="사이가 틀어진 관계",
    pattern=Pattern(
        sessions=8,
        turns_per_session=4,
        me_starts_ratio=0.75,
        me_burst=2,
        peer_burst=1,
        my_reply_seconds=10 * MINUTE,
        peer_reply_seconds=5 * HOUR,
        session_gap_seconds=10 * DAY,
    ),
    analysis=analysis(
        tone=(35, 25),
        affection=(20, 12),
        effort=(40, 18),
        conflict=85,
        depth=45,
        promises=(6, 1, 5),
        money=(2, 0, 0),
    ),
)

ALL_CASES = (CLOSE, BALANCED, FADING, ONE_SIDED, CONFLICT)
BY_KEY = {case.key: case for case in ALL_CASES}
