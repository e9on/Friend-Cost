"""Analysis Agent(LLM 1회)의 출력.

데이터 계약 명세서 7장.

여기 담기는 값은 모두 "의미 판단"이다. 점수·비율·평균은 들어오지 않는다.
그런 값은 다음 단계에서 코드가 계산한다.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SCORE = Field(ge=0, le=100)
COUNT = Field(ge=0)


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class SpeakerScores(_Base):
    """화자별 0~100 판단값."""

    me: int = SCORE
    peer: int = SCORE

    @property
    def average(self) -> float:
        return (self.me + self.peer) / 2


class PromiseSignals(_Base):
    proposed: int = COUNT
    fulfilled: int = COUNT
    declined: int = COUNT


class MoneySignals(_Base):
    lent: int = COUNT
    borrowed: int = COUNT
    resolved: int = COUNT


class RelationshipAnalysisData(_Base):
    emotional_tone: SpeakerScores
    affection_signals: SpeakerScores
    effort_level: SpeakerScores
    conflict_level: int = SCORE
    topic_depth: int = SCORE
    promise_signals: PromiseSignals
    money_signals: MoneySignals
    notable_moments: tuple[str, ...] = Field(default=(), max_length=5)
