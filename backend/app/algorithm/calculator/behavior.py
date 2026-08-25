"""LLM 없이 대화 데이터만으로 계산되는 행동 지표.

관계 점수 계산 규칙 4~7장.

기준 명세 8장의 "코드로 계산 가능한 작업은 LLM에 맡기지 않는다" 원칙이
실제로 적용되는 곳이다.
"""

from app.algorithm.rule.constants import (
    MIN_REPLY_SAMPLES,
    MIN_SESSIONS,
    REPLY_MAX_SECONDS,
    SESSION_GAP_SECONDS,
    TRIM_RATIO,
)
from app.common.numeric import round_half_up, round_ratio
from app.domain.model.conversation import ConversationData, Message
from app.domain.model.score import ReplySeconds
from app.domain.value_object.enums import Speaker

Session = tuple[Message, ...]


def split_sessions(convo: ConversationData) -> tuple[Session, ...]:
    """시각이 복원된 메시지를 대화 세션으로 나눈다.

    6시간을 기준으로 삼는 이유는 수면 시간을 대화 공백이 아니라 세션 종료로 보기
    위해서다. 이 처리를 하지 않으면 자정 전후 메시지 하나가 평균 답장 속도를
    통째로 왜곡한다.
    """
    timed = convo.timed_messages()
    if not timed:
        return ()

    sessions: list[list[Message]] = [[timed[0]]]
    for previous, current in zip(timed, timed[1:]):
        if current.sent_at - previous.sent_at > SESSION_GAP_SECONDS:
            sessions.append([current])
        else:
            sessions[-1].append(current)
    return tuple(tuple(session) for session in sessions)


def first_contact_ratio(convo: ConversationData) -> float:
    """내가 먼저 연락한 대화 세션의 비율.

    세션이 3개 미만이면 통계적 의미가 없으므로 0.5로 고정한다.
    이 경우 신뢰도도 함께 강등된다.
    """
    sessions = split_sessions(convo)
    if len(sessions) < MIN_SESSIONS:
        return 0.5

    started_by_me = sum(1 for session in sessions if session[0].speaker is Speaker.ME)
    return round_ratio(started_by_me / len(sessions))


def _runs(messages: tuple[Message, ...]) -> list[list[Message]]:
    """같은 화자가 연속으로 보낸 메시지를 한 덩어리로 묶는다."""
    runs: list[list[Message]] = []
    for message in messages:
        if runs and runs[-1][0].speaker is message.speaker:
            runs[-1].append(message)
        else:
            runs.append([message])
    return runs


def _trimmed_mean(samples: list[int]) -> int | None:
    """가장 느린 상위 10%를 잘라낸 평균.

    답장 간격 분포는 한쪽으로 심하게 치우쳐 있어서, 단순 평균은 소수의 늦은
    답장에 끌려간다.
    """
    if len(samples) < MIN_REPLY_SAMPLES:
        return None

    ordered = sorted(samples)
    trim = int(len(ordered) * TRIM_RATIO)
    kept = ordered[: len(ordered) - trim] if trim else ordered
    return round_half_up(sum(kept) / len(kept))


def reply_seconds(convo: ConversationData) -> ReplySeconds:
    """화자별 평균 답장 속도.

    상대의 마지막 메시지에서 내 첫 메시지까지를 한 번의 답장으로 센다.
    6시간을 넘는 간격은 답장이 아니라 새 세션의 시작이므로 버린다.
    """
    runs = _runs(convo.timed_messages())
    samples: dict[Speaker, list[int]] = {Speaker.ME: [], Speaker.PEER: []}

    for previous, current in zip(runs, runs[1:]):
        gap = current[0].sent_at - previous[-1].sent_at
        if 0 <= gap <= REPLY_MAX_SECONDS:
            samples[current[0].speaker].append(gap)

    return ReplySeconds(
        me=_trimmed_mean(samples[Speaker.ME]),
        peer=_trimmed_mean(samples[Speaker.PEER]),
    )


def contact_balance(convo: ConversationData) -> int:
    """연락 균형도. 100이 완전 균형이다.

    시각이 없는 메시지도 포함해 센다. 누가 얼마나 말했는지는 시각과 무관하다.
    """
    count_me = len(convo.by_speaker(Speaker.ME))
    count_peer = len(convo.by_speaker(Speaker.PEER))
    total = count_me + count_peer
    if total == 0:
        return 0

    return round_half_up(100 * (1 - abs(count_me - count_peer) / total))
