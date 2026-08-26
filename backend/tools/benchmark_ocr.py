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


def build_engine(name: str, key: str | None, lang="korean", version="PP-OCRv4"):
    if name == "rapid":
        from app.infrastructure.ocr.rapid import RapidOcrEngine

        return RapidOcrEngine(lang=lang, ocr_version=version)
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


def _infix_distance(target: str, blob: str) -> int:
    """`target` 이 `blob` 어딘가에 얼마나 비슷하게 나타나는지.

    보통의 편집 거리를 쓰면 안 된다. OCR 결과에는 시각 라벨·날짜·다른
    메시지가 함께 들어 있어서, 문장 하나를 전체와 비교하면 나머지가 전부
    오류로 잡힌다. 블록 하나씩 비교하는 것도 틀렸다. **OCR 은 말풍선을 여러
    줄로 쪼개므로** 한 블록 안에 문장이 다 들어 있지 않다.

    그래서 시작과 끝을 자유롭게 둔다. 첫 행을 0으로 채워 앞을 건너뛸 수 있게
    하고, 마지막 행의 최솟값을 취해 뒤를 건너뛴다. 결과는 "이 문장과 가장
    비슷한 구간까지의 편집 거리"다.
    """
    if not target:
        return 0
    if not blob:
        return len(target)

    previous = [0] * (len(blob) + 1)  # 앞부분은 공짜로 건너뛴다
    for i, ct in enumerate(target, start=1):
        current = [i]
        for j, cb in enumerate(blob, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ct != cb))
            )
        previous = current
    return min(previous)  # 뒷부분도 공짜로 건너뛴다


def score_text(pages, truth) -> dict:
    """정답 문장이 얼마나 정확히 읽혔는지.

    완전 일치율만 보면 한 글자 틀린 것과 통째로 못 읽은 것이 같아진다.
    실제로 `korean_mobile_v2.0` 이 "다음 주에 시간 어때"를 "다음 축에 시가
    어때"로 읽었는데, 일치율로는 0%라 못 읽은 것과 구분되지 않았다.
    그래서 **문자 단위 오류율(CER)** 을 함께 낸다.
    """
    found = 0
    expected = 0
    errors = 0
    characters = 0
    for page, page_truth in zip(pages, truth):
        blob = "".join(normalize(block.text) for block in page.blocks)
        for message in page_truth["messages"]:
            target = normalize(message["text"])
            expected += 1
            characters += len(target)
            if target in blob:
                found += 1
            else:
                errors += min(_infix_distance(target, blob), len(target))
    return {
        "found": found,
        "expected": expected,
        "rate": found / expected if expected else 0.0,
        "cer": errors / characters if characters else 1.0,
    }


def report(name, pages, truth, elapsed, convo, parse_error) -> None:
    line = "=" * 62
    print(f"\n{line}\n {name}\n{line}")

    blocks = sum(len(page.blocks) for page in pages)
    print(f"  이미지            {len(pages)}장")
    print(f"  인식 블록          {blocks}개")
    print(f"  장당 처리 시간      {elapsed / max(1, len(pages)):.2f}초")

    speakers = score_speakers(pages, truth)
    text = score_text(pages, truth)

    print(f"\n  문장 완전 일치      {text['rate']:.1%}  ({text['found']}/{text['expected']} 문장)")
    print(f"  문자 오류율(CER)    {text['cer']:.1%}  (낮을수록 좋다)")
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
    parser.add_argument("--lang", default="korean", help="인식 언어")
    parser.add_argument("--ocr-version", default="PP-OCRv4", help="모델 세대")
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

    engine = build_engine(args.engine, args.key, args.lang, args.ocr_version)
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
