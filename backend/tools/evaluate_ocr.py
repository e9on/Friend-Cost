"""OCR 후보 실측 도구.

`AI-모델-선정-보고서.md` 8.2의 평가 항목을 잰다.

    python tools/evaluate_ocr.py --images ./caps/대화01 --engine stub
    python tools/evaluate_ocr.py --images ./caps/대화01 --engine google_vision --key $KEY

두 가지를 한 번에 한다.

1. **평가** — 화자 판별, 시각 인식률, 처리 시간을 잰다
2. **픽스처 저장** — `OcrPage` JSON을 남긴다. 이 파일이 그대로
   `evaluate_llm.py --fixtures` 의 입력이 되므로, OCR을 한 번만 돌리고
   LLM 후보를 여러 번 비교할 수 있다

**화자 판별 정확도는 자동으로 잴 수 없다.** 정답이 없기 때문이다.
그래서 사람이 훑어볼 수 있는 검토 파일을 함께 내놓는다. 대화 흐름이
"나 -> 상대 -> 나" 로 자연스럽게 이어지는지 눈으로 보면 금방 드러난다.

검토 파일에는 대화 원문이 들어간다. 평가가 끝나면 지운다.
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

from app.ai.parser import parse  # noqa: E402
from app.ai.parser.speaker import BlockRole, classify_block  # noqa: E402
from app.common.errors import AppError  # noqa: E402
from app.domain.model.conversation import ConversationData, OcrPage  # noqa: E402
from app.domain.value_object.enums import Speaker, TimeSource  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def load_images(directory: Path) -> list[tuple[str, bytes]]:
    """파일명 순서를 시간 순서로 본다. 01, 02 처럼 번호를 붙여두면 좋다."""
    paths = sorted(
        path for path in directory.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES
    )
    return [(path.name, path.read_bytes()) for path in paths]


def build_engine(name: str, key: str | None):
    if name == "stub":
        from app.infrastructure.ocr.stub import StubOcrEngine

        return StubOcrEngine()
    if name == "google_vision":
        from app.infrastructure.ocr.google_vision import GoogleVisionOcrEngine

        if not key:
            raise SystemExit("google_vision 을 쓰려면 --key 가 필요합니다")
        return GoogleVisionOcrEngine(api_key=key)
    raise SystemExit(f"알 수 없는 엔진: {name}")


def block_roles(pages: Sequence[OcrPage]) -> Counter:
    counts: Counter = Counter()
    for page in pages:
        for block in page.blocks:
            counts[classify_block(block, page.width).value] += 1
    return counts


def report_pages(pages: Sequence[OcrPage], seconds: float) -> None:
    total_blocks = sum(len(page.blocks) for page in pages)
    roles = block_roles(pages)
    confidences = [
        block.confidence for page in pages for block in page.blocks
    ]

    print("\n-- OCR 단계 --")
    print(f"  이미지            {len(pages)}장")
    print(f"  블록              {total_blocks}개")
    print(f"  장당 처리 시간     {seconds / max(1, len(pages)):.2f}초")
    if confidences:
        low = sum(1 for value in confidences if value < 0.5)
        print(f"  평균 신뢰도        {sum(confidences) / len(confidences):.3f}")
        print(f"  저신뢰(0.5 미만)   {low}개")

    print("\n  블록 좌우 판별")
    for role in (BlockRole.ME, BlockRole.PEER, BlockRole.CENTER):
        count = roles.get(role.value, 0)
        share = count / total_blocks if total_blocks else 0
        print(f"    {role.value:<8} {count:5d}  ({share:.0%})")

    if roles.get(BlockRole.ME.value, 0) == 0 or roles.get(BlockRole.PEER.value, 0) == 0:
        print("\n  경고: 한쪽 화자만 판별되었습니다.")
        print("        말풍선이 좌우로 나뉜 원본 캡처인지 확인하세요.")


def report_conversation(convo: ConversationData) -> None:
    meta = convo.meta
    speakers = Counter(message.speaker for message in convo.messages)
    sources = Counter(message.time_source for message in convo.messages)

    print("\n-- Parser 단계 --")
    print(f"  메시지            {meta.message_count}개")
    print(f"  제거              {meta.dropped_count}개 (시스템·중복·저신뢰)")
    print(f"  샘플링            {'예' if meta.sampled else '아니오'}")
    print(f"  시각 복원률        {meta.time_coverage:.0%}")
    if meta.span_seconds:
        print(f"  대화 기간          {meta.span_seconds / 86400:.1f}일")

    print("\n  화자 분포")
    for speaker in (Speaker.ME, Speaker.PEER):
        count = speakers.get(speaker, 0)
        share = count / meta.message_count if meta.message_count else 0
        print(f"    {speaker.value:<6} {count:5d}  ({share:.0%})")

    print("\n  시각 출처")
    for source in TimeSource:
        print(f"    {source.value:<10} {sources.get(source, 0):5d}")

    if meta.time_coverage < 0.6:
        print("\n  경고: 시각 복원률이 낮습니다.")
        print("        답장 속도와 세션 분할이 부정확해집니다.")

    if meta.span_seconds and meta.span_seconds > 365 * 86400:
        print("\n  경고: 대화 기간이 비정상적으로 깁니다.")
        print("        날짜 앵커 복원이 틀어졌을 수 있습니다.")


def write_fixture(pages: Sequence[OcrPage], path: Path) -> None:
    payload = [page.model_dump(by_alias=True) for page in pages]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n픽스처 저장: {path}")
    print("  evaluate_llm.py --fixtures 로 그대로 쓸 수 있습니다.")


def write_review(convo: ConversationData, path: Path) -> None:
    """사람이 화자 판별을 눈으로 확인할 파일.

    자동으로 잴 수 없는 지표라 이 방법뿐이다. 대화가 자연스럽게
    이어지지 않으면 판별이 틀린 것이다.
    """
    lines = [
        "# 화자 판별 검토",
        "",
        "대화가 자연스럽게 이어지는지 훑어보세요.",
        "한 사람이 혼자 묻고 답하는 것처럼 보이면 판별이 틀린 것입니다.",
        "",
        "**확인이 끝나면 이 파일을 지우세요. 대화 원문이 들어 있습니다.**",
        "",
    ]
    for message in convo.messages:
        who = "나  " if message.speaker is Speaker.ME else "상대"
        mark = "" if message.sent_at else "  [시각없음]"
        lines.append(f"{message.index:4d} | {who} | {message.text}{mark}")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"검토 파일: {path}")
    print("  화자 판별 정확도는 자동으로 잴 수 없습니다. 눈으로 확인하세요.")
    print("  확인 후 삭제하세요. 대화 원문이 들어 있습니다.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="OCR 후보 실측")
    parser.add_argument("--images", type=Path, required=True, help="캡처가 든 디렉터리")
    parser.add_argument("--engine", default="stub")
    parser.add_argument("--key", default=None)
    parser.add_argument("--out", type=Path, default=None, help="픽스처 저장 경로")
    parser.add_argument("--review", type=Path, default=None, help="검토 파일 경로")
    args = parser.parse_args()

    if not args.images.is_dir():
        raise SystemExit(f"디렉터리가 아닙니다: {args.images}")

    images = load_images(args.images)
    if not images:
        raise SystemExit("이미지를 찾지 못했습니다.")

    print(f"엔진: {args.engine}")
    print(f"이미지 {len(images)}장 — {', '.join(name for name, _ in images)}")

    engine = build_engine(args.engine, args.key)

    started = time.perf_counter()
    try:
        pages = await engine.read([data for _, data in images])
    except AppError as exc:
        raise SystemExit(f"OCR 실패: {exc.code.value}")
    elapsed = time.perf_counter() - started

    report_pages(pages, elapsed)

    try:
        convo = parse(pages)
    except AppError as exc:
        print(f"\n-- Parser 단계 --\n  실패: {exc.code.value}")
        print(f"  {exc.message}")
        if args.out:
            write_fixture(pages, args.out)
        return

    report_conversation(convo)

    if args.out:
        write_fixture(pages, args.out)
    if args.review:
        write_review(convo, args.review)


if __name__ == "__main__":
    asyncio.run(main())
