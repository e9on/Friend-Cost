"""합성 캡처로 OCR 엔진을 채점한다.

`render_kakao.py` 가 만든 캡처에는 정답이 딸려 있다. 어느 위치의 어떤
메시지가 누구 것인지 우리가 안다. 그래서 **화자 판별 정확도를 사람 눈이
아니라 숫자로** 잴 수 있다.

    python tools/render_kakao.py --out synth --count 6
    python tools/benchmark_ocr.py --images synth --engine rapid

합성 캡처의 한계는 분명하다. 실제 캡처에는 압축 노이즈, 프로필 사진, 읽음
표시, 다양한 폰트가 섞인다. **여기서 나온 점수는 하한선이 아니라 상한선에
가깝다.** 여기서도 못 하면 실제에서는 확실히 못 한다.
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

from app.ai.parser import parse  # noqa: E402
from app.ai.parser.speaker import BlockRole, classify_block  # noqa: E402
from app.common.errors import AppError  # noqa: E402
from app.domain.model.conversation import OcrPage  # noqa: E402
from app.domain.value_object.enums import Speaker, TimeSource  # noqa: E402


def build_engine(name: str, key: str | None):
    if name == "rapid":
        from app.infrastructure.ocr.rapid import RapidOcrEngine

        return RapidOcrEngine()
    if name == "stub":
        from app.infrastructure.ocr.stub import StubOcrEngine

        return StubOcrEngine()
    if name == "google_vision":
        from app.infrastructure.ocr.google_vision import GoogleVisionOcrEngine

        if not key:
            raise SystemExit("google_vision 을 쓰려면 --key 가 필요합니다")
        return GoogleVisionOcrEngine(api_key=key)
    raise SystemExit(f"알 수 없는 엔진: {name}")


def normalize(text: str) -> str:
    """비교용. 공백과 흔한 오인식을 지운다."""
    return "".join(text.split())


def score_speakers(pages, truth) -> dict:
    """정답 말풍선의 중심이 어느 블록에 들어가는지로 대조한다.

    OCR이 말풍선을 여러 줄로 쪼갤 수 있으므로 블록 단위로 채점한다.
    블록의 중심이 어떤 정답 말풍선 안에 있으면, 그 블록의 좌우 판별이
    정답 화자와 같은지 본다.
    """
    correct = 0
    wrong = 0
    unmatched = 0
    center_blocks = 0

    for page, page_truth in zip(pages, truth):
        boxes = page_truth["messages"]
        for block in page.blocks:
            role = classify_block(block, page.width)
            cx = block.box.x + block.box.w / 2
            cy = block.box.y + block.box.h / 2

            owner = None
            for message in boxes:
                if (
                    message["x"] <= cx <= message["x"] + message["w"]
                    and message["y"] <= cy <= message["y"] + message["h"]
                ):
                    owner = message
                    break

            if owner is None:
                # 시각 라벨, 날짜 구분선, 프로필 등
                unmatched += 1
                continue
            if role is BlockRole.CENTER:
                center_blocks += 1
                continue
            if role.value == owner["speaker"]:
                correct += 1
            else:
                wrong += 1

    total = correct + wrong + center_blocks
    return {
        "correct": correct,
        "wrong": wrong,
        "center": center_blocks,
        "unmatched": unmatched,
        "accuracy": correct / total if total else 0.0,
    }


def score_text(pages, truth) -> dict:
    """정답 문장이 OCR 결과 어딘가에 그대로 나타나는지."""
    found = 0
    expected = 0
    for page, page_truth in zip(pages, truth):
        blob = normalize(" ".join(block.text for block in page.blocks))
        for message in page_truth["messages"]:
            expected += 1
            if normalize(message["text"]) in blob:
                found += 1
    return {"found": found, "expected": expected, "rate": found / expected if expected else 0.0}


def report(name, pages, truth, elapsed, convo, parse_error) -> None:
    line = "=" * 62
    print(f"\n{line}\n {name}\n{line}")

    blocks = sum(len(page.blocks) for page in pages)
    print(f"  이미지            {len(pages)}장")
    print(f"  인식 블록          {blocks}개")
    print(f"  장당 처리 시간      {elapsed / max(1, len(pages)):.2f}초")

    speakers = score_speakers(pages, truth)
    text = score_text(pages, truth)

    print(f"\n  텍스트 인식률       {text['rate']:.1%}  ({text['found']}/{text['expected']} 문장)")
    print(f"  화자 판별 정확도    {speakers['accuracy']:.1%}", end="")
    print(f"  (맞음 {speakers['correct']}, 틀림 {speakers['wrong']}, 중앙 {speakers['center']})")
    print(f"  대조 안 된 블록      {speakers['unmatched']}개 (시각 라벨·날짜 구분선 등)")

    if parse_error:
        print(f"\n  Parser 실패: {parse_error}")
        return

    meta = convo.meta
    sources = Counter(message.time_source for message in convo.messages)
    counts = Counter(message.speaker for message in convo.messages)
    expected_total = sum(len(item["messages"]) for item in truth)

    print(f"\n  -- Parser 결과 --")
    print(f"  메시지            {meta.message_count}개  (정답 {expected_total}개)")
    print(f"  제거              {meta.dropped_count}개")
    print(f"  시각 복원률        {meta.time_coverage:.0%}"
          f"  (explicit {sources.get(TimeSource.EXPLICIT, 0)},"
          f" inferred {sources.get(TimeSource.INFERRED, 0)},"
          f" unknown {sources.get(TimeSource.UNKNOWN, 0)})")
    print(f"  화자 분포          me {counts.get(Speaker.ME, 0)} / peer {counts.get(Speaker.PEER, 0)}")

    if meta.span_seconds is not None:
        print(f"  대화 기간          {meta.span_seconds / 3600:.1f}시간")

    accuracy = speakers["accuracy"]
    print()
    if accuracy >= 0.99:
        print("  판정: 합성 캡처에서는 완벽하다. 실제 캡처로 다시 재야 한다.")
    elif accuracy >= 0.95:
        print("  판정: 합성 캡처에서 양호. 실제 캡처에서는 더 떨어질 것이다.")
    else:
        print("  판정: 합성 캡처에서도 부족하다. 실제 캡처에서는 쓸 수 없다.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="합성 캡처로 OCR 채점")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--engine", default="rapid")
    parser.add_argument("--key", default=None)
    parser.add_argument("--out", type=Path, default=None, help="OcrPage JSON 저장")
    args = parser.parse_args()

    truth_path = args.images / "truth.json"
    if not truth_path.exists():
        raise SystemExit(f"정답 파일이 없습니다: {truth_path}\nrender_kakao.py 로 먼저 만드세요.")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    paths = sorted(p for p in args.images.glob("*.png"))
    if not paths:
        raise SystemExit("캡처를 찾지 못했습니다.")
    print(f"엔진: {args.engine}, 캡처 {len(paths)}장")

    engine = build_engine(args.engine, args.key)
    payload = [path.read_bytes() for path in paths]

    started = time.perf_counter()
    pages = await engine.read(payload)
    elapsed = time.perf_counter() - started

    convo = None
    parse_error = None
    try:
        convo = parse(pages, min_messages=1)
    except AppError as exc:
        parse_error = exc.code.value

    report(args.engine, pages, truth, elapsed, convo, parse_error)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps([page.model_dump(by_alias=True) for page in pages],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n픽스처 저장: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
