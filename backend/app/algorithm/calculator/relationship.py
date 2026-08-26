"""친밀도·손절 위험도·친구비·신뢰도.

관계 점수 계산 규칙 8~11장.

여기 있는 함수는 모두 순수 함수다. 같은 입력에 항상 같은 결과가 나와야 하므로
난수, 현재 시각, 외부 호출을 쓰지 않는다.
"""

import math

from app.algorithm.rule.constants import (
    REPLY_GAP_BASE,
    FEE_GAP_STDDEV,
    W_GAP_AFFECTION,
    W_GAP_EFFORT,
    W_GAP_INITIATION,
    W_GAP_MESSAGES,
    W_GAP_REPLY,
    FEE_BASE,
    FEE_CALIBRATION_MEAN,
    FEE_CALIBRATION_STDDEV,
    FEE_CURVE_STRENGTH,
    FEE_MAX,
    FEE_MIN,
    FEE_UNIT,
    MIN_REPLY_SAMPLES,
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


def reply_delay_score(peer_reply_seconds: int | None, chances: int = 0) -> int:
    """상대의 답장이 느릴수록 높아지는 보조 점수.

    로그 스케일을 쓰는 이유는 5분과 30분의 차이가 3시간과 4시간의 차이보다
    관계적으로 크기 때문이다.

    표본이 없을 때(``None``)는 두 경우를 가른다. `chances` 는 상대가 답할
    차례였던 횟수다.

    - 차례 자체가 드물었다면 **모르는 것**이므로 0이다.
    - 차례는 여러 번 있었는데 6시간 안에 답한 적이 없다면 **측정된 사실**
      이므로 100이다. 이걸 0으로 두면 답장이 느릴수록 위험이 낮아진다.

    `관계-점수-계산-규칙.md` 8장.
    """
    if peer_reply_seconds is None:
        return 100 if chances >= MIN_REPLY_SAMPLES else 0
    if peer_reply_seconds <= REPLY_FLOOR_SECONDS:
        return 0
    if peer_reply_seconds >= REPLY_CEIL_SECONDS:
        return 100

    ratio = math.log(peer_reply_seconds / REPLY_FLOOR_SECONDS) / _LOG_SPAN
    return clamp_score(100 * ratio)


def contact_imbalance_score(contact_balance: int, first_contact_ratio: float) -> int:
    """연락이 한쪽으로 기운 정도.

    두 가지를 함께 본다. 서로 다른 것을 재기 때문이다.

    - **연락 균형도**: 누가 더 많이 말하는가
    - **먼저 연락 비율**: 누가 대화를 여는가

    메시지 수는 반반인데 항상 한쪽이 먼저 말을 거는 관계가 있다. 균형도만
    보면 완벽해 보이지만, 한쪽이 멈추면 대화도 멈추는 관계다. 사용자가
    가장 알고 싶어 하는 것이 바로 이 차이다.

    방향은 따지지 않는다. 내가 늘 먼저 걸든 상대가 늘 먼저 걸든, 한쪽만
    끌고 가는 관계는 마찬가지로 위태롭다.
    """
    count_imbalance = 100 - contact_balance
    initiation_imbalance = 200 * abs(first_contact_ratio - 0.5)
    return clamp_score(0.5 * count_imbalance + 0.5 * initiation_imbalance)


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
    first_contact_ratio: float = 0.5,
    peer_reply_chances: int = 0,
) -> int:
    """손절 위험도.

    `peer_reply_chances` 는 상대가 답할 차례였던 횟수다. 표본이 없을 때
    "모른다"와 "6시간 안에 답한 적이 없다"를 가르는 데 쓴다.
    """
    return clamp_score(
        W_RISK_CONFLICT * analysis.conflict_level
        + W_RISK_IMBALANCE * contact_imbalance_score(contact_balance, first_contact_ratio)
        + W_RISK_PEER_EFFORT * (100 - analysis.effort_level.peer)
        + W_RISK_REPLY_DELAY * reply_delay_score(peer_reply_seconds, peer_reply_chances)
        + W_RISK_PROMISE * promise_break_score(analysis.promise_signals)
        + W_RISK_MONEY * money_risk_score(analysis.money_signals)
    )


def _normal_cdf(value: float, mean: float, stddev: float) -> float:
    """정규분포의 누적분포함수.

    `math.erf` 로 구한다. scipy 를 끌어오지 않으려는 것이다.
    """
    if stddev <= 0:
        return 0.0 if value < mean else 1.0
    return 0.5 * (1 + math.erf((value - mean) / (stddev * math.sqrt(2))))


def _reply_speed_gap(replies) -> float:
    """내가 더 빨리 답할수록 크다. -1.0 ~ +1.0.

    한쪽이라도 표본이 없으면 0이다. **모르는 것을 격차로 치지 않는다.**
    8장의 `reply_delay_score` 와 달리 "답한 적 없음"도 0으로 둔다. 격차는
    양쪽을 견줘야 나오는 값이고, 한쪽이 비면 견줄 수가 없다.

    로그를 쓰는 이유는 6장과 같다. 5분과 30분의 차이가 3시간과 4시간의
    차이보다 관계적으로 크다.
    """
    if replies.me is None or replies.peer is None:
        return 0.0
    ratio = math.log(max(replies.peer, 1) / max(replies.me, 1)) / math.log(
        REPLY_GAP_BASE
    )
    return clamp(ratio, -1.0, 1.0)


def contribution_gap(
    analysis: RelationshipAnalysisData,
    my_count: int,
    peer_count: int,
    first_contact_ratio: float,
    replies,
) -> float:
    """누가 더 기여했는가. -1.0 ~ +1.0. 양수면 내가 더 기여했다.

    `관계-점수-계산-규칙.md` 10.2.
    """
    total = my_count + peer_count
    message_gap = (my_count - peer_count) / total if total else 0.0

    return clamp(
        W_GAP_EFFORT
        * (analysis.effort_level.me - analysis.effort_level.peer)
        / 100
        + W_GAP_AFFECTION
        * (analysis.affection_signals.me - analysis.affection_signals.peer)
        / 100
        + W_GAP_MESSAGES * message_gap
        + W_GAP_INITIATION * (first_contact_ratio - 0.5) * 2
        + W_GAP_REPLY * _reply_speed_gap(replies),
        -1.0,
        1.0,
    )


def friend_fee(raw_gap: float) -> int:
    """기여 격차를 정산액으로 옮긴다.

    양수면 상대가 나에게, 음수면 내가 상대에게 내야 한다. **관계가 나쁘다는
    뜻이 아니다.** 음수는 "내가 더 받았다"는 뜻이다.

    부호와 크기를 나눠 다룬다. 크기만 보정하고 부호를 그대로 붙이므로,
    보정이 방향을 뒤집는 일은 구조적으로 불가능하다.

    `관계-점수-계산-규칙.md` 10.3.
    """
    magnitude = min(abs(raw_gap), 1.0)

    # 반정규분포의 CDF. 원시 격차가 실측에서 ±0.2 에 그쳐 그대로 쓰면
    # 상한에 영원히 닿지 못한다. 8장에서 한 번 겪은 결함이다
    percentile = 2 * _normal_cdf(magnitude, 0.0, FEE_GAP_STDDEV) - 1
    position = (
        FEE_CURVE_STRENGTH * percentile + (1 - FEE_CURVE_STRENGTH) * magnitude
    )

    amount = clamp(round_to_unit(FEE_MAX * position, FEE_UNIT), 0, FEE_MAX)
    return int(-amount if raw_gap < 0 else amount)



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
