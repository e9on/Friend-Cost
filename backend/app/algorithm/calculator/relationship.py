"""친밀도·손절 위험도·친구비·신뢰도.

관계 점수 계산 규칙 8~11장.

여기 있는 함수는 모두 순수 함수다. 같은 입력에 항상 같은 결과가 나와야 하므로
난수, 현재 시각, 외부 호출을 쓰지 않는다.
"""

import math

from app.algorithm.rule.constants import (
    FEE_BASE,
    FEE_CALIBRATION_MEAN,
    FEE_CALIBRATION_STDDEV,
    FEE_CURVE_STRENGTH,
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
) -> int:
    """손절 위험도."""
    return clamp_score(
        W_RISK_CONFLICT * analysis.conflict_level
        + W_RISK_IMBALANCE * contact_imbalance_score(contact_balance, first_contact_ratio)
        + W_RISK_PEER_EFFORT * (100 - analysis.effort_level.peer)
        + W_RISK_REPLY_DELAY * reply_delay_score(peer_reply_seconds)
        + W_RISK_PROMISE * promise_break_score(analysis.promise_signals)
        + W_RISK_MONEY * money_risk_score(analysis.money_signals)
    )


def quality_ratio(
    intimacy_score: int, contact_balance: int, breakup_risk_score: int
) -> float:
    """관계의 원시 품질 비율. 0.0 ~ 1.0.

    | 항 | 역할 | 범위 |
    | --- | --- | --- |
    | 친밀도 | 관계의 기본 가치 | 0.00 ~ 1.00 |
    | 균형 보정 | 한쪽만 노력해도 절반은 인정 | 0.50 ~ 1.00 |
    | 위험 할인 | 최대 50%까지만 깎는다 | 0.50 ~ 1.00 |

    위험도 할인을 절반까지만 적용하는 이유는, 관계가 아무리 나빠도 친구비가
    0원이 되면 결과가 모욕적으로 읽히기 때문이다.
    """
    return (
        (intimacy_score / 100)
        * (0.5 + 0.5 * contact_balance / 100)
        * (1 - breakup_risk_score / 200)
    )


def _normal_cdf(value: float, mean: float, stddev: float) -> float:
    """정규분포의 누적분포함수. 0.0 ~ 1.0."""
    return 0.5 * (1 + math.erf((value - mean) / (stddev * math.sqrt(2))))


def friend_fee(intimacy_score: int, contact_balance: int, breakup_risk_score: int) -> int:
    """친구비. 다른 지표가 확정된 뒤에 계산되는 파생 지표다.

    원시 품질 비율을 그대로 금액으로 바꾸지 않고 **분위수로 옮긴다.**

    세 항의 곱은 값이 가운데로 몰린다. 그대로 쓰면 중간 50%가
    33,000~46,000원에 들어와서, 서로 다른 친구를 재도 비슷한 숫자만 나온다.
    친구 셋을 재서 38,000·41,000·44,000이 나오면 아무것도 알려주지 못한 것이다.

    분위수로 옮기면 친구비가 "우리가 본 관계 분포에서 상위 몇 %"라는 뜻을
    갖는다. 순서는 그대로 보존된다(누적분포함수는 단조 증가한다).
    """
    ratio = quality_ratio(intimacy_score, contact_balance, breakup_risk_score)
    percentile = _normal_cdf(ratio, FEE_CALIBRATION_MEAN, FEE_CALIBRATION_STDDEV)
    # 순수 분위수만 쓰면 양 끝이 뭉개진다. 원래 비율을 섞어 순서를 지킨다
    position = FEE_CURVE_STRENGTH * percentile + (1 - FEE_CURVE_STRENGTH) * ratio
    raw = FEE_MIN + position * (FEE_MAX - FEE_MIN)
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
