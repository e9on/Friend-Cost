"""모델이 담아 보낸 대화 원문을 걷어낸다.

프롬프트에 "원문을 그대로 옮기지 마라"고 적어두었지만 **지시만으로는 막지
못한다.** 2026-08-26 실측에서 리포트 본문에 이런 문장이 실렸다.

    상대가 '그때 연락할게'라고 주도권을 넘기는 경향이 있어…

작은따옴표 안이 대화 원문이다. Analysis Agent 가 `notableMoments` 에 원문을
담았고 Report Agent 가 그것을 인용했다. Report Agent 는 대화 원문을 입력으로
받지 않는데도 이 경로로 우회됐다.

"대화 원문을 로그·응답에 남기지 않는다"는 절대 규칙이므로 코드가 확인한다.
확인하지 못한 문장은 사용자에게 가지 않는다.

`AI-프롬프트-명세.md` 3.5.
"""

import re
from typing import Final

from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.conversation import ConversationData

# 대조하는 조각의 길이.
#
# 모델은 메시지를 통째로 옮기지 않고 **일부만** 따온다. 실측에서 새어 나온
# 것도 "알겠어 그때 연락할게" 중 "그때 연락할게" 뿐이었다. 그래서 메시지
# 전체를 비교하지 않고 이 길이의 창을 밀어가며 본다.
#
# 6으로 잡은 이유는 양쪽 실패를 피하기 위해서다. 더 짧으면 "그래", "알겠어"
# 같은 흔한 말이 걸려 정상 요약까지 버려진다. 더 길면 짧게 따온 인용을
# 놓친다. 한국어 여섯 글자면 우연히 겹치기 어렵다.
MIN_QUOTE_LENGTH: Final = 6

_NOISE = re.compile(r"[\s.,!?~…'\"“”‘’()\[\]<>·:;/\-—]+")


def _normalize(text: str) -> str:
    """공백과 문장부호를 지운다.

    모델은 원문을 그대로 옮기지 않고 조사를 붙이거나 따옴표로 감싼다.
    표면 그대로 비교하면 그런 변형을 놓친다.
    """
    return _NOISE.sub("", text)


def _windows(text: str) -> set[str]:
    """정규화한 문자열에서 길이 `MIN_QUOTE_LENGTH` 조각을 모두 뽑는다.

    집합으로 다루면 원문 조각과 서술 조각의 교집합 한 번으로 끝난다.
    """
    normalized = _normalize(text)
    if len(normalized) < MIN_QUOTE_LENGTH:
        return set()
    return {
        normalized[index : index + MIN_QUOTE_LENGTH]
        for index in range(len(normalized) - MIN_QUOTE_LENGTH + 1)
    }


def strip_verbatim(
    analysis: RelationshipAnalysisData, convo: ConversationData
) -> RelationshipAnalysisData:
    """대화 원문 조각을 담은 `notableMoments` 항목을 버린다.

    버리는 쪽을 택한 이유는, 원문을 가린 서술이 무슨 뜻인지 알 수 없게 되기
    때문이다. 지운 자리를 남기느니 그 항목을 없애는 편이 낫다.
    """
    if not analysis.notable_moments:
        return analysis

    quotes: set[str] = set()
    for message in convo.messages:
        quotes |= _windows(message.text)
    if not quotes:
        return analysis

    kept = tuple(
        moment
        for moment in analysis.notable_moments
        if not (_windows(moment) & quotes)
    )
    if len(kept) == len(analysis.notable_moments):
        return analysis
    return analysis.model_copy(update={"notable_moments": kept})
