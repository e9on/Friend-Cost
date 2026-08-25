"""테스트용 도메인 객체 빌더.

실제 캡처 이미지 없이도 Parser 이후 단계를 검증할 수 있도록,
`ConversationData` 를 손으로 조립하는 도구를 모아둔다.
"""

from app.domain.model.analysis import (
    MoneySignals,
    PromiseSignals,
    RelationshipAnalysisData,
    SpeakerScores,
)
from app.domain.model.conversation import ConversationData, ConversationMeta, Message
from app.domain.value_object.enums import Speaker, TimeSource

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

BASE_TS = 1_755_000_000


def msg(
    index: int,
    speaker: Speaker,
    sent_at: int | None = None,
    text: str = "메시지",
    image_index: int = 0,
) -> Message:
    return Message(
        index=index,
        speaker=speaker,
        text=text,
        sent_at=sent_at,
        time_source=TimeSource.UNKNOWN if sent_at is None else TimeSource.EXPLICIT,
        image_index=image_index,
    )


def conversation(
    messages: list[Message],
    *,
    image_count: int = 1,
    dropped_count: int = 0,
    sampled: bool = False,
    time_coverage: float | None = None,
) -> ConversationData:
    """메시지 목록으로부터 `ConversationData` 를 만든다.

    `time_coverage` 와 `span_seconds` 는 지정하지 않으면 메시지에서 계산한다.
    """
    timed = [m for m in messages if m.sent_at is not None]
    if time_coverage is None:
        time_coverage = len(timed) / len(messages) if messages else 0.0
    span = (timed[-1].sent_at - timed[0].sent_at) if len(timed) >= 2 else None
    return ConversationData(
        messages=tuple(messages),
        meta=ConversationMeta(
            image_count=image_count,
            message_count=len(messages),
            dropped_count=dropped_count,
            sampled=sampled,
            time_coverage=time_coverage,
            span_seconds=span,
        ),
    )


def alternating(count: int, *, start: int = BASE_TS, gap: int = 5 * MINUTE) -> list[Message]:
    """me/peer가 번갈아 말하는 대화를 만든다."""
    return [
        msg(i, Speaker.ME if i % 2 == 0 else Speaker.PEER, start + i * gap)
        for i in range(count)
    ]


def analysis(
    *,
    tone: tuple[int, int] = (72, 65),
    affection: tuple[int, int] = (58, 41),
    effort: tuple[int, int] = (70, 45),
    conflict: int = 18,
    depth: int = 62,
    promises: tuple[int, int, int] = (6, 4, 2),
    money: tuple[int, int, int] = (1, 0, 0),
    moments: tuple[str, ...] = (),
) -> RelationshipAnalysisData:
    """관계 점수 계산 규칙 13장의 예제 값을 기본값으로 쓴다."""
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
        notable_moments=moments,
    )
