"""OCR 결과를 정규화된 대화 데이터로 바꾼다.

OCR·Parser 명세 4~11장.

처리 순서:
    시각 라벨 분리 -> 화자 판별 -> 이름 라벨로 단톡 감지 -> 블록 병합
    -> 절대 시각 복원 -> 정규화와 폐기 -> 이미지 간 중복 제거 -> 샘플링
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
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
MERGE_LINE_FACTOR: Final = 1.5  # 블록 병합 시 허용하는 세로 간격 (앞 블록 높이 대비)
MERGE_ALIGN_RATIO: Final = 0.03  # 같은 말풍선으로 볼 정렬 오차 (이미지 폭 대비)
NAME_LABEL_MAX_LEN: Final = 12
NAME_LABEL_GAP_FACTOR: Final = 1.2
DEDUPE_WINDOW: Final = 10
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


def _is_time_label(text: str) -> bool:
    """텍스트 전체가 시각 표기일 때만 라벨로 본다.

    부분 일치를 쓰면 "3:30에 보자" 같은 본문이 라벨로 오인된다.
    """
    return bool(_TIME_LABEL.match(text.strip()))


def _detect_group_chat(blocks: Sequence[OcrBlock], page_width: int) -> None:
    """왼쪽 말풍선 위에 붙은 발신자 이름이 둘 이상이면 단체방이다."""
    left_blocks = [b for b in blocks if classify_block(b, page_width) is BlockRole.PEER]
    names: set[str] = set()

    for candidate in left_blocks:
        if len(candidate.text.strip()) > NAME_LABEL_MAX_LEN or _is_time_label(candidate.text):
            continue
        below = [
            other
            for other in left_blocks
            if other is not candidate
            and 0 < other.box.y - candidate.box.bottom < candidate.box.h * NAME_LABEL_GAP_FACTOR
            and other.box.h > candidate.box.h
        ]
        if below:
            names.add(candidate.text.strip())

    if len(names) >= 2:
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


def _collect_raw(page: OcrPage) -> tuple[list[_Raw], int, list[date]]:
    """한 이미지에서 메시지 후보와 날짜 앵커를 뽑는다."""
    usable = [b for b in page.blocks if b.confidence >= MIN_BLOCK_CONFIDENCE]
    dropped = len(page.blocks) - len(usable)

    time_labels = [b for b in usable if _is_time_label(b.text)]
    others = [b for b in usable if not _is_time_label(b.text)]

    _detect_group_chat(others, page.width)

    anchors: list[date] = []
    body_blocks: dict[BlockRole, list[OcrBlock]] = {BlockRole.ME: [], BlockRole.PEER: []}

    for block in others:
        role = classify_block(block, page.width)
        if role is BlockRole.CENTER:
            found = parse_date_line(block.text)
            if found:
                anchors.append(found)
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

    raws.sort(key=lambda r: r.y)
    _attach_time_labels(raws, time_labels)
    return raws, dropped, anchors


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


def _restore_timestamps(raws: list[_Raw], anchors: list[date]) -> None:
    """시계 표기에 날짜를 붙여 절대 시각으로 만든다.

    날짜 구분선이 하나도 없으면 가상 기준일 위에 배치한다. 절대 날짜는 의미가
    없고 간격만 유효하며, 그 값은 API 응답에 노출되지 않는다.
    """
    has_anchor = bool(anchors)
    current = anchors[0] if has_anchor else VIRTUAL_EPOCH_DATE
    previous_minutes: int | None = None

    for raw in raws:
        if raw.clock is None:
            continue
        hour, minute = raw.clock
        minutes = hour * 60 + minute
        if previous_minutes is not None and minutes < previous_minutes:
            current = current + timedelta(days=1)
            raw.rolled_over = True
        previous_minutes = minutes
        raw.epoch = to_epoch(current, hour, minute)
        raw.anchored = has_anchor


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

    for page in sorted(pages, key=lambda p: p.image_index):
        raws, page_dropped, anchors = _collect_raw(page)
        dropped += page_dropped
        _restore_timestamps(raws, anchors)
        pages_raws.append(raws)

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
