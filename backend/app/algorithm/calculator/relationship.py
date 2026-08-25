"""친밀도·손절 위험도·친구비·신뢰도.

관계 점수 계산 규칙 8~11장.

여기 있는 함수는 모두 순수 함수다. 같은 입력에 항상 같은 결과가 나와야 하므로
난수, 현재 시각, 외부 호출을 쓰지 않는다.
"""

import math

from app.algorithm.rule.constants import (
    FEE_BASE,
    FEE_MAX,
    FEE_MIN,
    FEE_UNIT,
    MIN_SESSIONS,
    RELIABLE_MESSAGES,
    RELIABLE_TIME_COVERAGE,
    REPLY_CEIL_SECONDS,
    REPLY_FLOOR_SECONDS,
    W_INTIMACY_AFFECTION,
    W_INTIMACY_BALANCE,
    W_INTIMACY_DEPTH,
    W_INTIMACY_TONE,
    W_RISK_CONFLICT,
    W_RISK_IMBALANCE,
    W_RISK_MONEY,
    W_RISK_PEER_EFFORT,
    W_RISK_PROMISE,
    W_RISK_REPLY_DELAY,
)
from app.common.numeric import clamp, clamp_score, round_to_unit
from app.domain.model.analysis import (
    MoneySignals,
    PromiseSignals,
    RelationshipAnalysisData,
)
from app.domain.model.conversation import ConversationMeta
from app.domain.value_object.enums import Confidence

_LOG_SPAN = math.log(REPLY_CEIL_SECONDS / REPLY_FLOOR_SECONDS)


def intimacy(analysis: RelationshipAnalysisData, contact_balance: int) -> int:
    """친밀도.

    감정 온도에 가장 큰 비중을 두되, 말로만 친한 관계와 실제로 주고받는 관계를
    구분하기 위해 연락 균형도를 함께 넣는다.
    """
    return clamp_score(
        W_INTIMACY_TONE * analysis.emotional_tone.average
        + W_INTIMACY_AFFECTION * analysis.affection_signals.average
        + W_INTIMACY_BALANCE * contact_balance
        + W_INTIMACY_DEPTH * analysis.topic_depth
    )


def reply_delay_score(peer_reply_seconds: int | None) -> int:
    """상대의 답장이 느릴수록 높아지는 보조 점수.

    로그 스케일을 쓰는 이유는 5분과 30분의 차이가 3시간과 4시간의 차이보다
    관계적으로 크기 때문이다.

    표본이 없으면(``None``) 0으로 둔다. 모르는 것을 위험으로 치지 않는다.
    """
    if peer_reply_seconds is None or peer_reply_seconds <= REPLY_FLOOR_SECONDS:
        return 0
    if peer_reply_seconds >= REPLY_CEIL_SECONDS:
        return 100

    ratio = math.log(peer_reply_seconds / REPLY_FLOOR_SECONDS) / _LOG_SPAN
    return clamp_score(100 * ratio)


def promise_break_score(promises: PromiseSignals) -> int:
    if promises.proposed == 0:
        return 0
    return clamp_score(100 * promises.declined / promises.proposed)


def money_risk_score(money: MoneySignals) -> int:
    """빌려준 돈이 정산되지 않은 정도. 빌린 적이 없으면 0이다."""
    if money.lent == 0:
        return 0
    unresolved = max(0, money.lent - money.resolved)
    return clamp_score(100 * unresolved / money.lent)


def breakup_risk(
    analysis: RelationshipAnalysisData,
    contact_balance: int,
    peer_reply_seconds: int | None,
) -> int:
    """손절 위험도."""
    return clamp_score(
        W_RISK_CONFLICT * analysis.conflict_level
        + W_RISK_IMBALANCE * (100 - contact_balance)
        + W_RISK_PEER_EFFORT * (100 - analysis.effort_level.peer)
        + W_RISK_REPLY_DELAY * reply_delay_score(peer_reply_seconds)
        + W_RISK_PROMISE * promise_break_score(analysis.promise_signals)
        + W_RISK_MONEY * money_risk_score(analysis.money_signals)
    )


def friend_fee(intimacy_score: int, contact_balance: int, breakup_risk_score: int) -> int:
    """친구비. 다른 지표가 확정된 뒤에 계산되는 파생 지표다.

    위험도 할인을 절반까지만 적용하는 이유는, 관계가 아무리 나빠도 친구비가
    0원이 되면 결과가 모욕적으로 읽히기 때문이다.
    """
    raw = (
        FEE_BASE
        * (intimacy_score / 100)
        * (0.5 + 0.5 * contact_balance / 100)
        * (1 - breakup_risk_score / 200)
    )
    return int(clamp(round_to_unit(raw, FEE_UNIT), FEE_MIN, FEE_MAX))


def confidence_of(meta: ConversationMeta, session_count: int) -> Confidence:
    """결과 신뢰도.

    표본이 부족한 결과를 그럴듯하게 보여주지 않기 위한 장치다.
    """
    if session_count < MIN_SESSIONS:
        return Confidence.LOW

    enough_messages = meta.message_count >= RELIABLE_MESSAGES
    enough_coverage = meta.time_coverage >= RELIABLE_TIME_COVERAGE

    if enough_messages and enough_coverage:
        level = Confidence.HIGH
    elif enough_messages or enough_coverage:
        level = Confidence.MEDIUM
    else:
        level = Confidence.LOW

    return level.downgrade() if meta.sampled else level
