"""OCR 결과를 정규화된 대화 데이터로 바꾼다.

OCR·Parser 명세 4~11장.

처리 순서:
    시각 라벨 분리 -> 화자 판별 -> 이름 라벨로 단톡 감지 -> 블록 병합
    -> 절대 시각 복원 -> 정규화와 폐기 -> 이미지 간 중복 제거 -> 샘플링
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from collections import Counter
from difflib import SequenceMatcher
from typing import Final, Sequence

from app.ai.parser.normalize import is_system_message, normalize_text
from app.ai.parser.speaker import BlockRole, classify_block
from app.ai.parser.timeline import (
    VIRTUAL_EPOCH_DATE,
    parse_date_line,
    parse_time_of_day,
    to_epoch,
)
from app.algorithm.rule.constants import MIN_MESSAGES
from app.common.errors import AppError, ErrorCode
from app.domain.model.conversation import (
    ConversationData,
    ConversationMeta,
    Message,
    OcrBlock,
    OcrPage,
)
from app.domain.value_object.enums import Speaker, TimeSource

__all__ = ["parse"]

MIN_BLOCK_CONFIDENCE: Final = 0.5
# 블록 병합 시 허용하는 세로 간격 (앞 블록 높이 대비).
#
# 말풍선 안에서 줄이 바뀔 때의 간격은 거의 0에 가깝다. 반면 별개 메시지
# 사이에는 여백이 들어간다. 이 차이가 유일한 단서이므로 허용치를 좁게 잡는다.
# 넓게 잡으면 서로 다른 메시지가 한 덩어리로 합쳐져 메시지 수가 줄고,
# 그러면 연락 균형도와 답장 속도가 통째로 틀어진다.
MERGE_LINE_FACTOR: Final = 0.4
MERGE_ALIGN_RATIO: Final = 0.03  # 같은 말풍선으로 볼 정렬 오차 (이미지 폭 대비)
NAME_LABEL_MAX_LEN: Final = 12
NAME_LABEL_GAP_FACTOR: Final = 1.2
# 이름 라벨이 자기 말풍선보다 왼쪽으로 튀어나온 정도 (이미지 폭 대비).
#
# 이름은 프로필 사진 옆 여백선에 맞고 말풍선은 그보다 안쪽에서 시작한다.
# 본문은 말풍선 안이므로 더 밀린다. 그래서 이름은 왼쪽으로 튀어나오고,
# **본문끼리는 x 가 같다.** 짧은 메시지 다음에 긴 메시지가 와도 마찬가지다.
#
# 실측(폭 720 실제 캡처 / 폭 1080 합성 3벌): 진짜 이름은 폭의 1.9~2.9%,
# 이름이 아닌 후보는 0.09% 이하. 0.01 은 그 사이다.
#
# 픽셀이 아니라 비율인 이유는 캡처 해상도를 우리가 정할 수 없기 때문이다.
#
# **순위가 아니라 자격 요건이다.** 튀어나오지 않은 블록은 아무리 반복돼도
# 이름이 아니다. `OCR-Parser-명세.md` 7.4.
NAME_LABEL_INDENT_RATIO: Final = 0.01
# 같은 텍스트가 이만큼 반복되어야 발신자 이름으로 본다.
#
# **높이로는 가를 수 없다.** 실측에서 1:1 오탐의 높이비(0.61~0.98)와 진짜
# 이름의 높이비(0.82~0.97)가 완전히 겹쳤다. OCR 상자 높이는 글꼴 크기가
# 아니라 받침과 윗선이 있는지를 따라간다.
#
# 발신자 이름은 그 사람이 말할 때마다 다시 붙으므로 반복된다. 실측에서
# 1:1 의 최다 반복은 2회, 단체방은 4~5회였다. 3이 그 사이다.
NAME_LABEL_MIN_REPEATS: Final = 3
# 이만큼 닮은 이름 라벨은 같은 사람으로 본다.
#
# OCR 은 같은 라벨을 매번 같게 읽지 않는다. 실측에서 닉네임 하나가
# `공어고글를렁을` `어고글를렁을` `궁오고글를바을` 처럼 갈라졌고, 그중 둘이
# 반복 기준을 넘겨 **한 사람이 두 사람이 됐다.** 정상 1:1 대화가 거부됐다.
#
# 신뢰도로는 걸러지지 않는다. 저 블록들의 신뢰도는 0.52~0.74 로 전부
# MIN_BLOCK_CONFIDENCE 를 통과했다. 글자를 틀리게 읽어도 OCR 은 확신한다.
#
# 실측: 합쳐야 하는 쌍 0.923, 합치면 안 되는 쌍의 최댓값 0.750
# (`김민지영`/`김민지수`). 그 사이에서 낮은 쪽으로 잡은 것은 거부가 미탐보다
# 나쁘기 때문이다. `OCR-Parser-명세.md` 7.3.
NAME_LABEL_SIMILARITY: Final = 0.8
# 겹침을 찾을 때 살펴보는 메시지 수.
#
# 사용자가 화면을 얼마나 겹쳐 찍을지는 우리가 정할 수 없다. 창보다 많이
# 겹치면 겹침을 **아예 찾지 못한다.** 일부만 지우는 것이 아니라 하나도
# 못 지운다. 그러면 메시지 수가 부풀려져 연락 균형도와 답장 속도가 함께
# 틀어지는데, 결과는 그럴듯하게 나오므로 알아채기 어렵다.
#
# 비교 비용은 창 크기의 제곱이지만 이 규모에서는 무시할 수 있다.
DEDUPE_WINDOW: Final = 60
DEDUPE_MIN_RUN: Final = 3
DEFAULT_MAX_MESSAGES: Final = 120
SAMPLE_HEAD: Final = 30
SAMPLE_TAIL: Final = 50

_TIME_LABEL = re.compile(r"^(?:오전|오후)?\s*\d{1,2}:\d{2}$")


@dataclass
class _Raw:
    """병합까지 끝난 메시지 후보. 시각 복원 단계에서 `epoch` 가 채워진다."""

    speaker: Speaker
    text: str
    y: float
    image_index: int
    clock: tuple[int, int] | None = None
    epoch: int | None = None
    rolled_over: bool = False
    anchored: bool = False
    # 날짜 구분선 자리를 표시하는 표식. 메시지가 아니며 시각 복원 뒤 버려진다
    date_anchor: date | None = None

    @property
    def is_anchor(self) -> bool:
        return self.date_anchor is not None


def _is_time_label(text: str) -> bool:
    """텍스트 전체가 시각 표기일 때만 라벨로 본다.

    부분 일치를 쓰면 "3:30에 보자" 같은 본문이 라벨로 오인된다.
    """
    return bool(_TIME_LABEL.match(text.strip()))


def _name_candidates(blocks: Sequence[OcrBlock], page_width: int) -> list[str]:
    """왼쪽 말풍선 위에 붙은 발신자 이름 후보를 모은다.

    **판정은 여기서 하지 않는다.** 이름은 여러 이미지에 흩어져 나타나므로
    한 장 안에서 세면 반복 횟수를 채우지 못한다. 모으기만 하고 `parse` 가
    전체를 합쳐 판정한다.
    """
    left_blocks = [b for b in blocks if classify_block(b, page_width) is BlockRole.PEER]
    indent = page_width * NAME_LABEL_INDENT_RATIO
    found: list[str] = []

    for candidate in left_blocks:
        text = candidate.text.strip()
        if len(text) > NAME_LABEL_MAX_LEN or _is_time_label(candidate.text):
            continue
        # 이름표를 붙인 말풍선. 바로 아래에 있고 후보보다 크다
        labelled = [
            other
            for other in left_blocks
            if other is not candidate
            and 0 < other.box.y - candidate.box.bottom < candidate.box.h * NAME_LABEL_GAP_FACTOR
            and other.box.h > candidate.box.h
        ]
        if not labelled:
            continue
        # 그 말풍선보다 왼쪽으로 튀어나와야 이름이다. 본문끼리는 x 가 같다
        if all(other.box.x - candidate.box.x >= indent for other in labelled):
            found.append(text)

    return found


def _distinct_names(names: Sequence[str]) -> int:
    """오인식으로 갈라진 같은 이름을 묶고, 남은 이름 수를 센다.

    단일 연결이다. 한 쌍이라도 임계값을 넘으면 같은 이름으로 본다. 한 라벨의
    변형들은 서로 조금씩 다르게 갈라지므로, 모든 변형이 서로 닮기를 요구하면
    묶이지 않는다.

    후보 순서에 결과가 달라지면 같은 대화가 어떤 날은 거부되고 어떤 날은
    통과한다. 그래서 순서와 무관한 합집합-찾기로 묶는다.
    """
    parent = list(range(len(names)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if SequenceMatcher(None, names[i], names[j]).ratio() >= NAME_LABEL_SIMILARITY:
                parent[find(i)] = find(j)

    return len({find(i) for i in range(len(names))})


def _detect_group_chat(candidates: Sequence[str]) -> None:
    """서로 다른 이름 라벨이 둘 이상이면 단체방이다.

    **1:1 에도 이름 라벨은 붙는다.** 그래서 라벨이 있느냐가 아니라 몇 종류냐로
    가른다.

    한 번 나타난 것을 이름으로 치면 **평범한 짧은 메시지가 걸린다.**
    실측에서 "나 지금 회사야"가 발신자 이름으로 오인돼 정상 1:1 대화가
    거부됐다. 사용자에게는 서비스 실패로 보인다.

    반복 횟수만으로도 부족하다. OCR 이 같은 닉네임을 매번 다르게 읽으면 한
    사람이 여러 사람이 된다. 그래서 세기 전에 닮은 것끼리 묶는다.

    `OCR-Parser-명세.md` 7장.
    """
    counts = Counter(candidates)
    # 정렬은 결과를 순서에 의존하지 않게 하려는 것이다
    names = sorted(text for text, count in counts.items() if count >= NAME_LABEL_MIN_REPEATS)
    if _distinct_names(names) >= 2:
        raise AppError(ErrorCode.GROUP_CHAT_DETECTED)


def _merge_blocks(blocks: list[OcrBlock], role: BlockRole, page_width: int) -> list[list[OcrBlock]]:
    """한 말풍선이 여러 줄로 쪼개진 경우를 다시 붙인다."""
    groups: list[list[OcrBlock]] = []
    tolerance = page_width * MERGE_ALIGN_RATIO

    for block in sorted(blocks, key=lambda b: b.box.y):
        if groups:
            previous = groups[-1][-1]
            close_enough = 0 <= block.box.y - previous.box.bottom <= previous.box.h * MERGE_LINE_FACTOR
            if role is BlockRole.ME:
                aligned = abs(block.box.right - previous.box.right) <= tolerance
            else:
                aligned = abs(block.box.x - previous.box.x) <= tolerance
            if close_enough and aligned:
                groups[-1].append(block)
                continue
        groups.append([block])

    return groups


def _collect_raw(page: OcrPage) -> tuple[list[_Raw], int, list[str]]:
    """한 이미지에서 메시지 후보를 뽑는다.

    날짜 구분선은 버리지 않고 위치를 지키는 표식으로 남긴다. 앵커가 화면
    중간에서 바뀔 수 있고, 그 순서를 잃으면 이후 메시지의 날짜가 틀어진다.
    """
    usable = [b for b in page.blocks if b.confidence >= MIN_BLOCK_CONFIDENCE]
    dropped = len(page.blocks) - len(usable)

    time_labels = [b for b in usable if _is_time_label(b.text)]
    others = [b for b in usable if not _is_time_label(b.text)]
    name_candidates = _name_candidates(others, page.width)

    markers: list[_Raw] = []
    body_blocks: dict[BlockRole, list[OcrBlock]] = {BlockRole.ME: [], BlockRole.PEER: []}

    for block in others:
        role = classify_block(block, page.width)
        if role is BlockRole.CENTER:
            found = parse_date_line(block.text)
            if found:
                markers.append(
                    _Raw(
                        speaker=Speaker.ME,  # 표식이라 화자는 의미가 없다
                        text="",
                        y=block.box.center_y,
                        image_index=page.image_index,
                        date_anchor=found,
                    )
                )
            dropped += 1
            continue
        body_blocks[role].append(block)

    raws: list[_Raw] = []
    for role, blocks in body_blocks.items():
        speaker = role.to_speaker()
        assert speaker is not None
        for group in _merge_blocks(blocks, role, page.width):
            text = " ".join(b.text.strip() for b in group)
            raws.append(
                _Raw(
                    speaker=speaker,
                    text=text,
                    y=group[0].box.center_y,
                    image_index=page.image_index,
                )
            )

    _attach_time_labels(sorted(raws, key=lambda r: r.y), time_labels)

    combined = sorted(raws + markers, key=lambda r: r.y)
    return combined, dropped, name_candidates


def _attach_time_labels(raws: list[_Raw], labels: Sequence[OcrBlock]) -> None:
    """시각 라벨을 세로로 가장 가까운 메시지에 붙인다.

    좌우 위치로 붙이지 않는 이유는, 말풍선이 넓어지면 라벨이 반대편 절반으로
    넘어가 화자 판별과 어긋나기 때문이다.
    """
    if not raws:
        return
    for label in labels:
        clock = parse_time_of_day(label.text)
        if clock is None:
            continue
        nearest = min(raws, key=lambda r: abs(r.y - label.box.center_y))
        if nearest.clock is None:
            nearest.clock = clock


def _restore_timestamps(raws: list[_Raw]) -> None:
    """시계 표기에 날짜를 붙여 절대 시각으로 만든다.

    **모든 이미지를 하나의 연속된 흐름으로 본다.** 스크롤 캡처는 한 대화를
    잘라놓은 것이고, 날짜 구분선은 보통 첫 화면에만 찍힌다. 이미지마다 앵커를
    초기화하면 뒤 이미지가 가상 기준일로 되돌아가 시간이 거꾸로 흐른다.

    날짜 구분선이 한 번도 나오지 않으면 가상 기준일 위에 배치한다. 절대 날짜는
    의미가 없고 간격만 유효하며, 그 값은 API 응답에 노출되지 않는다.
    """
    current = VIRTUAL_EPOCH_DATE
    seen_anchor = False
    previous_minutes: int | None = None

    for raw in raws:
        if raw.is_anchor:
            current = raw.date_anchor
            seen_anchor = True
            previous_minutes = None  # 날짜가 바뀌었으니 시각 역행 판단을 새로 시작한다
            continue

        if raw.clock is None:
            continue

        hour, minute = raw.clock
        minutes = hour * 60 + minute
        if previous_minutes is not None and minutes < previous_minutes:
            current = current + timedelta(days=1)
            raw.rolled_over = True
        previous_minutes = minutes
        raw.epoch = to_epoch(current, hour, minute)
        raw.anchored = seen_anchor


def _dedupe(pages_raws: list[list[_Raw]]) -> tuple[list[_Raw], int]:
    """스크롤 캡처가 겹친 구간을 뒤 이미지에서 제거한다.

    3개 연속 일치를 기준으로 삼는 이유는, 'ㅇㅇ' 같은 짧은 메시지가 우연히
    일치할 수 있어 1~2개로는 오탐이 나기 때문이다.
    """
    merged: list[_Raw] = []
    dropped = 0

    for raws in pages_raws:
        if not merged:
            merged.extend(raws)
            continue

        tail = merged[-DEDUPE_WINDOW:]
        head = raws[:DEDUPE_WINDOW]
        overlap = 0
        for length in range(min(len(tail), len(head)), DEDUPE_MIN_RUN - 1, -1):
            if all(
                tail[-length + i].speaker is head[i].speaker
                and tail[-length + i].text == head[i].text
                for i in range(length)
            ):
                overlap = length
                break

        dropped += overlap
        merged.extend(raws[overlap:])

    return merged, dropped


def _sample(raws: list[_Raw], limit: int) -> tuple[list[_Raw], bool]:
    """상한을 넘으면 앞 30 + 중간 + 뒤 50으로 추린다.

    뒷부분을 더 많이 남기는 이유는 관계의 현재 상태가 판단에 더 중요하기 때문이다.
    손절 위험도와 답장 속도는 최근 데이터가 결정한다.
    """
    if len(raws) <= limit:
        return raws, False

    middle_quota = limit - SAMPLE_HEAD - SAMPLE_TAIL
    head = raws[:SAMPLE_HEAD]
    tail = raws[-SAMPLE_TAIL:]
    middle_pool = raws[SAMPLE_HEAD : len(raws) - SAMPLE_TAIL]

    if middle_quota <= 0 or not middle_pool:
        return (head + tail)[:limit], True

    step = len(middle_pool) / middle_quota
    middle = [middle_pool[int(i * step)] for i in range(middle_quota)]
    return head + middle + tail, True


def parse(
    pages: Sequence[OcrPage],
    *,
    min_messages: int = MIN_MESSAGES,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> ConversationData:
    """OCR 페이지들을 `ConversationData` 로 바꾼다."""
    pages_raws: list[list[_Raw]] = []
    dropped = 0
    name_candidates: list[str] = []

    for page in sorted(pages, key=lambda p: p.image_index):
        raws, page_dropped, page_names = _collect_raw(page)
        dropped += page_dropped
        pages_raws.append(raws)
        name_candidates.extend(page_names)

    # 이름은 여러 이미지에 흩어져 나타난다. 장마다 세면 놓친다
    _detect_group_chat(name_candidates)

    # 시각 복원은 이미지 경계를 넘어 한 번에 한다. 앵커가 이어져야 하기 때문이다
    _restore_timestamps([raw for raws in pages_raws for raw in raws])

    pages_raws = [[raw for raw in raws if not raw.is_anchor] for raws in pages_raws]
    merged, overlap_dropped = _dedupe(pages_raws)
    dropped += overlap_dropped

    kept: list[_Raw] = []
    for raw in merged:
        if is_system_message(raw.text):
            dropped += 1
            continue
        normalized = normalize_text(raw.text)
        if not normalized:
            dropped += 1
            continue
        raw.text = normalized
        kept.append(raw)

    sampled_raws, sampled = _sample(kept, max_messages)

    messages = tuple(
        Message(
            index=index,
            speaker=raw.speaker,
            text=raw.text,
            sent_at=raw.epoch,
            time_source=_time_source_of(raw),
            image_index=raw.image_index,
        )
        for index, raw in enumerate(sampled_raws)
    )

    _validate(messages, min_messages)

    timed = [m.sent_at for m in messages if m.sent_at is not None]
    return ConversationData(
        messages=messages,
        meta=ConversationMeta(
            image_count=len(pages),
            message_count=len(messages),
            dropped_count=dropped,
            sampled=sampled,
            time_coverage=(len(timed) / len(messages)) if messages else 0.0,
            span_seconds=(max(timed) - min(timed)) if len(timed) >= 2 else None,
        ),
    )


def _time_source_of(raw: _Raw) -> TimeSource:
    if raw.epoch is None:
        return TimeSource.UNKNOWN
    if raw.rolled_over or not raw.anchored:
        return TimeSource.INFERRED
    return TimeSource.EXPLICIT


def _validate(messages: Sequence[Message], min_messages: int) -> None:
    if not messages:
        raise AppError(ErrorCode.NO_CONVERSATION_FOUND)

    speakers = {m.speaker for m in messages}
    if len(speakers) < 2:
        raise AppError(ErrorCode.NO_CONVERSATION_FOUND)

    if len(messages) < min_messages:
        raise AppError(ErrorCode.TOO_FEW_MESSAGES)
