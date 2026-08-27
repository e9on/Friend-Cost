"""관계 점수 계산 진입점.

관계 점수 계산 규칙 2장의 순서를 그대로 따른다. 순서가 중요한 이유는
친구비가 친밀도·연락 균형도·손절 위험도의 파생 지표이기 때문이다.
"""

from app.algorithm.calculator.behavior import (
    contact_balance,
    first_contact_ratio,
    peer_reply_chances,
    reply_seconds,
    split_sessions,
)
from app.algorithm.calculator.relationship import (
    contribution_gap,
    breakup_risk,
    friend_fee,
    intimacy,
)
from app.algorithm.rule.constants import MIN_MESSAGES
from app.common.errors import AppError, ErrorCode
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.conversation import ConversationData
from app.domain.model.score import RelationshipScoreData
from app.domain.value_object.enums import Speaker

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
    # 표본이 없을 때 "모른다"와 "6시간 안에 답한 적이 없다"를 가르려면
    # 기회 횟수가 필요하다. 관계-점수-계산-규칙 8장
    chances = peer_reply_chances(convo)
    initiation = first_contact_ratio(convo)

    intimacy_score = intimacy(analysis, balance)
    risk_score = breakup_risk(analysis, balance, replies.peer, initiation, chances)

    # 친구비는 품질이 아니라 **기여 격차**를 잰다. 친밀도와 같은 정보를
    # 두 번 보여주지 않기 위해서다. 관계-점수-계산-규칙 10장
    gap = contribution_gap(
        analysis=analysis,
        my_count=len(convo.by_speaker(Speaker.ME)),
        peer_count=len(convo.by_speaker(Speaker.PEER)),
        first_contact_ratio=initiation,
        replies=replies,
    )

    return RelationshipScoreData(
        friend_fee=friend_fee(gap),
        intimacy=intimacy_score,
        breakup_risk=risk_score,
        first_contact_ratio=initiation,
        avg_reply_seconds=replies,
        contact_balance=balance,
    )
