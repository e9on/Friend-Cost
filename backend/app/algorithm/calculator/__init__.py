"""관계 점수 계산 진입점.

관계 점수 계산 규칙 2장의 순서를 그대로 따른다. 순서가 중요한 이유는
친구비가 친밀도·연락 균형도·손절 위험도의 파생 지표이기 때문이다.
"""

from app.algorithm.calculator.behavior import (
    contact_balance,
    first_contact_ratio,
    reply_seconds,
    split_sessions,
)
from app.algorithm.calculator.relationship import (
    breakup_risk,
    confidence_of,
    friend_fee,
    intimacy,
)
from app.algorithm.rule.constants import MIN_MESSAGES
from app.common.errors import AppError, ErrorCode
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.conversation import ConversationData
from app.domain.model.score import RelationshipScoreData

__all__ = ["calculate_scores"]


def calculate_scores(
    convo: ConversationData, analysis: RelationshipAnalysisData
) -> RelationshipScoreData:
    """대화와 분석 결과로부터 최종 점수를 만든다.

    LLM을 호출하지 않는다. 같은 입력에는 항상 같은 결과가 나온다.
    """
    if convo.meta.message_count < MIN_MESSAGES:
        # 신뢰도를 낮춰 보여주는 것보다 분석을 거절하는 편이 낫다
        raise AppError(ErrorCode.TOO_FEW_MESSAGES)

    sessions = split_sessions(convo)
    balance = contact_balance(convo)
    replies = reply_seconds(convo)

    intimacy_score = intimacy(analysis, balance)
    risk_score = breakup_risk(analysis, balance, replies.peer)

    return RelationshipScoreData(
        friend_fee=friend_fee(intimacy_score, balance, risk_score),
        intimacy=intimacy_score,
        breakup_risk=risk_score,
        first_contact_ratio=first_contact_ratio(convo),
        avg_reply_seconds=replies,
        contact_balance=balance,
        confidence=confidence_of(convo.meta, session_count=len(sessions)),
    )
