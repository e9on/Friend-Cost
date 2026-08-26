"""관계 스펙트럼을 가로지르는 평가용 대화를 만든다.

**왜 필요한가.** `StubOcrEngine` 이 만드는 합성 대화는 문장 풀이 12줄
고정이라 어떤 씨앗을 넣어도 톤이 같다. 그런 입력으로 "친밀도 분산이 작다"는
결과가 나오면 모델이 관계를 못 읽은 것인지 입력이 다 똑같았던 것인지
구분할 수 없다. 그래서 **서로 다른 관계**를 의도적으로 만든다.

핵심은 정답 순서를 우리가 안다는 점이다. 절친이 일방적 관계보다 친밀도가
높게 나와야 한다. 그 순서를 못 맞히는 모델은 쓸 수 없다. 표준편차만으로는
이걸 못 잰다. 값이 널뛰기만 해도 편차는 커지기 때문이다.

프로필의 문장은 실제 대화가 아니라 지어낸 것이다. 실제 캡처가 생기면
`--fixtures` 로 대체한다.
"""

from dataclasses import dataclass
from random import Random
from typing import Final, Sequence

from app.domain.model.conversation import (
    ConversationData,
    ConversationMeta,
    Message,
)
from app.domain.value_object.enums import Speaker, TimeSource

MESSAGES_PER_IMAGE: Final = 14
BASE_EPOCH: Final = 1_756_000_000  # 고정값이라 실행할 때마다 같은 대화가 나온다


@dataclass(frozen=True)
class Profile:
    """관계 한 종류의 생성 규칙.

    `rank` 는 기대 친밀도 순위다(1이 가장 친함). 절대값이 아니라 **순서**를
    기대치로 둔다. 모델마다 눈금이 다르므로 절대값은 비교 기준이 못 된다.
    """

    key: str
    label: str
    rank: int
    note: str
    sessions: int
    turns_per_session: tuple[int, int]
    session_gap_hours: tuple[int, int]
    reply_gap_seconds: tuple[int, int]
    me_initiates: float
    me_lines: tuple[str, ...]
    peer_lines: tuple[str, ...]
    peer_silence: float = 0.0  # 상대가 답하지 않고 대화가 끊길 확률


PROFILES: Final[tuple[Profile, ...]] = (
    Profile(
        key="bestie",
        label="절친",
        rank=1,
        note="자주, 균형 있게, 서로 챙긴다",
        sessions=8,
        turns_per_session=(6, 12),
        session_gap_hours=(4, 20),
        reply_gap_seconds=(30, 400),
        me_initiates=0.5,
        me_lines=(
            "야 나 오늘 진짜 미치는 줄 ㅋㅋㅋㅋ",
            "그거 봤어? 너 생각나서 바로 캡쳐함",
            "주말에 뭐해 얼굴 좀 보자",
            "너 저번에 말한 그거 어떻게 됐어?",
            "고생했다 진짜 ㅠㅠ 내가 밥 살게",
            "ㅋㅋㅋㅋㅋㅋ 아 웃겨 죽겠네",
            "아 맞다 그때 빌려준 거 천천히 줘도 돼",
            "너 아니었으면 나 진짜 못 버텼을 듯",
        ),
        peer_lines=(
            "ㅋㅋㅋㅋ 뭔데 뭔데 빨리 말해봐",
            "헐 대박 나도 그거 보고 너 생각했는데",
            "좋지 토요일 어때? 내가 그쪽으로 갈게",
            "그거 잘 됐어! 너 덕분이야 진짜",
            "아니야 저번에도 네가 샀잖아 이번엔 내가",
            "야 근데 너 요즘 괜찮아? 좀 걱정돼서",
            "알겠어 그건 신경 쓰지 마",
            "무슨 소리야 당연한 거지",
        ),
    ),
    Profile(
        key="close",
        label="친한 사이",
        rank=2,
        note="반가워하지만 자주는 아니다",
        sessions=6,
        turns_per_session=(4, 8),
        session_gap_hours=(20, 72),
        reply_gap_seconds=(300, 3600),
        me_initiates=0.5,
        me_lines=(
            "잘 지내? 오랜만이다 ㅋㅋ",
            "그거 어떻게 됐어? 궁금했는데",
            "다음에 밥 한번 먹자 진짜로",
            "축하해!! 진짜 잘됐다",
            "요즘 바쁜가보네 ㅎㅎ",
            "사진 봤어 너무 좋아 보이더라",
        ),
        peer_lines=(
            "어 잘 지내지 너는 어때?",
            "ㅋㅋ 진짜 오랜만이네",
            "잘 마무리됐어 물어봐줘서 고마워",
            "좋아 시간 맞춰보자",
            "고마워 ㅎㅎ 너도 잘 지내지?",
            "응 요즘 좀 정신없었어",
        ),
    ),
    Profile(
        key="casual",
        label="용건 위주",
        rank=3,
        note="필요할 때 연락하고 끝난다",
        sessions=6,
        turns_per_session=(3, 6),
        session_gap_hours=(30, 96),
        reply_gap_seconds=(600, 7200),
        me_initiates=0.55,
        me_lines=(
            "혹시 내일 시간 돼?",
            "그 파일 좀 보내줄 수 있어?",
            "몇 시에 만날까",
            "알겠어 그때 봐",
            "ㅇㅇ 확인했어",
            "장소는 저번에 거기로 할까",
        ),
        peer_lines=(
            "어 될 것 같아",
            "응 방금 보냈어",
            "7시쯤 어때",
            "ㅇㅋ",
            "그래 그때 보자",
            "거기 좋지",
        ),
    ),
    Profile(
        key="fading",
        label="소원해지는 중",
        rank=4,
        note="답은 오지만 짧고 느리다",
        sessions=11,
        turns_per_session=(2, 4),
        session_gap_hours=(120, 400),
        reply_gap_seconds=(7200, 43200),
        me_initiates=0.7,
        me_lines=(
            "잘 지내지?",
            "오랜만이네 ㅎㅎ",
            "언제 한번 보자",
            "요즘 어떻게 지내",
            "생일 축하해",
        ),
        peer_lines=(
            "어 잘 지내",
            "ㅇㅇ",
            "그러게 언제 한번",
            "그냥 그래",
            "고마워",
        ),
        peer_silence=0.15,
    ),
    Profile(
        key="oneway",
        label="일방적",
        rank=5,
        note="나만 먼저 연락하고 답은 단답이다",
        sessions=14,
        turns_per_session=(2, 4),
        session_gap_hours=(150, 500),
        reply_gap_seconds=(14400, 86400),
        me_initiates=0.95,
        me_lines=(
            "잘 지내?",
            "요즘 연락이 없네",
            "이번 주말에 시간 돼?",
            "혹시 바빠?",
            "그럼 다음에 연락할게",
            "생일 축하해!! 잘 지내지?",
        ),
        peer_lines=(
            "ㅇㅇ",
            "어 좀 바빠",
            "미안 나중에",
            "ㅇㅇ 고마워",
        ),
        peer_silence=0.35,
    ),
    Profile(
        key="formal",
        label="사무적",
        rank=6,
        note="답장은 빠르지만 애정 신호가 없다",
        sessions=6,
        turns_per_session=(3, 6),
        session_gap_hours=(18, 48),
        reply_gap_seconds=(60, 900),
        me_initiates=0.5,
        me_lines=(
            "안녕하세요, 내일 회의 시간 확인 부탁드립니다",
            "자료 공유드렸습니다 확인 부탁드려요",
            "네 알겠습니다",
            "감사합니다 그럼 그렇게 진행하겠습니다",
            "일정 변경 가능할까요?",
        ),
        peer_lines=(
            "안녕하세요 2시로 예정되어 있습니다",
            "확인했습니다 감사합니다",
            "네 그럼 내일 뵙겠습니다",
            "수고하셨습니다",
            "네 가능합니다 조정해두겠습니다",
        ),
    ),
)

PROFILE_BY_KEY: Final = {profile.key: profile for profile in PROFILES}


def build(profile: Profile, seed: int = 0) -> ConversationData:
    """프로필 하나로 대화 한 건을 만든다. 같은 씨앗이면 같은 대화가 나온다."""
    rng = Random(f"{profile.key}:{seed}")
    messages: list[Message] = []
    now = BASE_EPOCH

    for _ in range(profile.sessions):
        turns = rng.randint(*profile.turns_per_session)
        speaker = Speaker.ME if rng.random() < profile.me_initiates else Speaker.PEER

        for turn in range(turns):
            if speaker is Speaker.PEER and rng.random() < profile.peer_silence:
                # 상대가 답하지 않고 대화가 끝난다. 일방적 관계의 핵심 신호다
                break
            pool = profile.me_lines if speaker is Speaker.ME else profile.peer_lines
            messages.append(
                Message(
                    index=len(messages),
                    speaker=speaker,
                    text=pool[rng.randrange(len(pool))],
                    sent_at=now,
                    time_source=TimeSource.EXPLICIT,
                    image_index=len(messages) // MESSAGES_PER_IMAGE,
                )
            )
            if turn + 1 < turns:
                now += rng.randint(*profile.reply_gap_seconds)
            speaker = Speaker.PEER if speaker is Speaker.ME else Speaker.ME

        now += rng.randint(*profile.session_gap_hours) * 3600

    if not messages:  # 방어. 프로필 상수가 잘못 바뀌면 여기서 걸린다
        raise ValueError(f"{profile.key} 가 메시지를 만들지 못했다")

    span = messages[-1].sent_at - messages[0].sent_at
    return ConversationData(
        messages=tuple(messages),
        meta=ConversationMeta(
            image_count=messages[-1].image_index + 1,
            message_count=len(messages),
            dropped_count=0,
            sampled=False,
            time_coverage=1.0,
            span_seconds=span,
        ),
    )


def build_all(seeds: int = 1) -> list[tuple[Profile, ConversationData]]:
    """모든 프로필을 씨앗 수만큼 만든다."""
    return [
        (profile, build(profile, seed))
        for profile in PROFILES
        for seed in range(seeds)
    ]


def concordance(ranked: Sequence[tuple[int, float]]) -> tuple[int, int]:
    """기대 순위와 실제 값이 같은 방향인 쌍의 수를 센다.

    표준편차는 값이 널뛰기만 해도 커진다. 관계를 **구분**하는지 보려면
    순서가 맞는지를 봐야 한다. `(rank, value)` 쌍을 받아 `(일치, 전체)` 를
    낸다. rank 가 작을수록 더 친하다고 기대한다.
    """
    agree = 0
    total = 0
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            rank_i, value_i = ranked[i]
            rank_j, value_j = ranked[j]
            if rank_i == rank_j or value_i == value_j:
                continue
            total += 1
            if (rank_i < rank_j) == (value_i > value_j):
                agree += 1
    return agree, total
