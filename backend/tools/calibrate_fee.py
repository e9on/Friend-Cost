"""친구비 보정값을 다시 구한다.

`관계-점수-계산-규칙.md` 10.3.

현재 `FEE_CALIBRATION_MEAN` 과 `FEE_CALIBRATION_STDDEV` 는 **합성 데이터**에서
얻은 값이다. 실제 모델의 Analysis Agent 출력 분포가 다르면 보정이 어긋난다.
모델이 감정 온도를 늘 60~80으로만 답한다면 원시 비율의 분포도 달라진다.

    # 실측한 픽스처로 다시 구하기 (권장)
    python tools/calibrate_fee.py --fixtures fixtures/ --provider groq --key $KEY

    # 합성 데이터로 (지금 값이 어떻게 나왔는지 재현)
    python tools/calibrate_fee.py --synthetic 3000

출력한 값을 `app/algorithm/rule/constants.py` 에 반영하고,
`관계-점수-계산-규칙.md` 10.2의 계산 예시 표도 함께 갱신한다.
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

from app.ai.parser import parse  # noqa: E402
from app.algorithm.calculator.behavior import contact_balance, first_contact_ratio, reply_seconds  # noqa: E402
from app.algorithm.calculator.relationship import (  # noqa: E402
    breakup_risk,
    friend_fee,
    intimacy,
    quality_ratio,
)
from app.algorithm.rule.constants import (  # noqa: E402
    FEE_CALIBRATION_MEAN,
    FEE_CALIBRATION_STDDEV,
    FEE_CURVE_STRENGTH,
)
from app.common.errors import AppError  # noqa: E402
from app.domain.model.conversation import OcrPage  # noqa: E402


def ratio_of(convo, analysis) -> float:
    balance = contact_balance(convo)
    replies = reply_seconds(convo)
    initiation = first_contact_ratio(convo)
    intimacy_score = intimacy(analysis, balance)
    risk = breakup_risk(analysis, balance, replies.peer, initiation)
    return quality_ratio(intimacy_score, balance, risk)


def synthetic_ratios(count: int, seed: int = 42) -> list[float]:
    """있을 법한 관계를 무작위로 만들어 원시 비율을 모은다.

    실제 데이터가 없을 때의 대용이다. 이것으로 구한 값은 어디까지나 임시다.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.relationships import (
        DAY,
        HOUR,
        MINUTE,
        Pattern,
        analysis,
        build_conversation,
    )

    def clamp(value: int) -> int:
        return max(0, min(100, value))

    rng = random.Random(seed)
    ratios: list[float] = []
    for _ in range(count):
        pattern = Pattern(
            sessions=rng.randint(5, 25),
            turns_per_session=rng.randint(3, 8),
            me_starts_ratio=rng.uniform(0.2, 0.9),
            me_burst=rng.randint(1, 3),
            peer_burst=rng.randint(1, 3),
            my_reply_seconds=rng.randint(2 * MINUTE, 3 * HOUR),
            peer_reply_seconds=rng.randint(2 * MINUTE, 5 * HOUR),
            session_gap_seconds=rng.randint(1, 20) * DAY,
        )
        tone = rng.randint(30, 95)
        affection = rng.randint(15, 90)
        effort = rng.randint(25, 95)
        proposed = rng.randint(0, 8)
        declined = rng.randint(0, proposed)
        data = analysis(
            tone=(tone, clamp(tone + rng.randint(-20, 10))),
            affection=(affection, clamp(affection + rng.randint(-25, 10))),
            effort=(effort, clamp(effort + rng.randint(-30, 10))),
            conflict=rng.randint(0, 80),
            depth=rng.randint(20, 90),
            promises=(proposed, proposed - declined, declined),
            money=(rng.randint(0, 2), 0, 0),
        )
        ratios.append(ratio_of(build_conversation(pattern), data))
    return ratios


async def measured_ratios(directory: Path, provider_name: str, model: str, key: str | None) -> list[float]:
    """실측 픽스처를 실제 모델에 통과시켜 원시 비율을 모은다."""
    from app.ai.agent.analysis import AnalysisAgent

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evaluate_llm import build_provider

    provider = build_provider(provider_name, model, key, None)
    agent = AnalysisAgent(provider)

    ratios: list[float] = []
    paths = sorted(directory.glob("*.json"))
    for index, path in enumerate(paths, start=1):
        print(f"  [{index}/{len(paths)}] {path.stem} …", end="", flush=True)
        raw = json.loads(path.read_text(encoding="utf-8"))
        pages = tuple(OcrPage.model_validate(item) for item in raw)
        try:
            convo = parse(pages)
            analysis = await agent.run(convo)
        except AppError as exc:
            print(f" 건너뜀({exc.code.value})")
            continue
        ratios.append(ratio_of(convo, analysis))
        print(" 완료")
    return ratios


def report(ratios: list[float], source: str) -> None:
    if len(ratios) < 20:
        raise SystemExit(f"표본이 {len(ratios)}건뿐이라 보정값을 낼 수 없습니다. 20건 이상 필요합니다.")

    mean = statistics.mean(ratios)
    stddev = statistics.pstdev(ratios)
    ordered = sorted(ratios)

    def at(fraction: float) -> float:
        return ordered[int(len(ordered) * fraction)]

    print(f"\n{'=' * 56}")
    print(f" 표본 {len(ratios)}건 ({source})")
    print("=" * 56)
    print(f"  평균     {mean:.4f}   (현재 설정 {FEE_CALIBRATION_MEAN})")
    print(f"  표준편차  {stddev:.4f}   (현재 설정 {FEE_CALIBRATION_STDDEV})")

    print("\n  분위수와 정규분포의 차이 (작을수록 정규분포에 가깝다)")
    worst = 0.0
    distribution = statistics.NormalDist(mean, stddev)
    for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
        actual = at(fraction)
        predicted = distribution.inv_cdf(fraction)
        gap = abs(actual - predicted)
        worst = max(worst, gap)
        print(f"    {int(fraction * 100):>3}%   실제 {actual:.4f}   정규 {predicted:.4f}   차이 {gap:.4f}")

    if worst > 0.05:
        print("\n  경고: 정규분포에서 많이 벗어났습니다.")
        print("        보정 곡선이 이 분포에 맞지 않을 수 있습니다.")

    print("\n  이 값을 쓰면 친구비가 이렇게 나옵니다")
    for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
        ratio = at(fraction)
        percentile = distribution.cdf(ratio)
        position = FEE_CURVE_STRENGTH * percentile + (1 - FEE_CURVE_STRENGTH) * ratio
        fee = round((1000 + position * 99000) / 1000) * 1000
        print(f"    {int(fraction * 100):>3}%   비율 {ratio:.3f}  ->  {fee:>7,}원")

    print(f"\n  app/algorithm/rule/constants.py 에 반영할 값:")
    print(f"    FEE_CALIBRATION_MEAN: Final = {mean:.3f}")
    print(f"    FEE_CALIBRATION_STDDEV: Final = {stddev:.3f}")
    print("\n  관계-점수-계산-규칙.md 10.2의 계산 예시 표도 함께 갱신하세요.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="친구비 보정값 재산출")
    parser.add_argument("--fixtures", type=Path, default=None, help="OcrPage JSON 디렉터리")
    parser.add_argument("--provider", default="stub")
    parser.add_argument("--model", default="stub")
    parser.add_argument("--key", default=None)
    parser.add_argument("--synthetic", type=int, default=0, help="합성 표본 수")
    args = parser.parse_args()

    if args.fixtures:
        print(f"실측 픽스처로 보정값을 구합니다: {args.fixtures}")
        ratios = await measured_ratios(args.fixtures, args.provider, args.model, args.key)
        source = f"실측, {args.provider}/{args.model}"
    else:
        count = args.synthetic or 3000
        print(f"합성 표본 {count}건으로 보정값을 구합니다.")
        print("실제 모델을 붙인 뒤에는 --fixtures 로 다시 구하세요.")
        ratios = synthetic_ratios(count)
        source = "합성"

    report(ratios, source)


if __name__ == "__main__":
    asyncio.run(main())
