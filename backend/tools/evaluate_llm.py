"""LLM 후보 실측 도구.

`AI-모델-선정-보고서.md` 8.3의 평가 항목을 실제로 잰다.

    python tools/evaluate_llm.py --provider stub
    python tools/evaluate_llm.py --provider groq --model openai/gpt-oss-120b --key $GROQ_KEY
    python tools/evaluate_llm.py --provider anthropic --model claude-haiku-4-5 --key $ANTHROPIC_KEY

가장 중요한 지표는 정확도가 아니라 **결과 분산**이다.
스키마를 지키고 문장이 매끄러워도, 어떤 대화를 넣든 친밀도가 60~70으로만
나온다면 그 모델은 관계를 읽지 못하는 것이다. 그런 결과는 오류로 드러나지
않고, 사용자는 그것이 자기 관계를 반영한다고 믿는다.

실제 카카오톡 캡처가 있으면 --fixtures 로 OcrPage JSON 디렉터리를 넘긴다.
없으면 합성 대화로 돌린다. 합성 대화는 파이프라인 점검용이며 품질 평가에
쓰면 안 된다.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

from app.ai.agent.analysis import AnalysisAgent  # noqa: E402
from app.ai.agent.report import ReportAgent  # noqa: E402
from app.ai.parser import parse  # noqa: E402
from app.algorithm.calculator import calculate_scores  # noqa: E402
from app.common.errors import AppError  # noqa: E402
from app.domain.model.conversation import ConversationData, OcrPage  # noqa: E402
from app.infrastructure.ocr.stub import StubOcrEngine  # noqa: E402

# 100만 토큰당 달러. AI-모델-선정-보고서 5.1의 표와 같아야 한다
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Groq 무료 티어. 모델 목록은 자주 바뀌므로 console.groq.com/docs/models 확인
    "openai/gpt-oss-120b": (0.0, 0.0),
    "openai/gpt-oss-20b": (0.0, 0.0),
    "llama-3.3-70b-versatile": (0.0, 0.0),  # 2026-06 지원 종료
    "deepseek-chat": (0.14, 0.28),
}
USD_TO_KRW = 1400


@dataclass
class Sample:
    label: str
    conversation: ConversationData
    rank: int | None = None  # 기대 친밀도 순위. 프로필 대화에만 있다
    note: str = ""


@dataclass
class Outcome:
    label: str
    ok: bool
    rank: int | None = None
    first_try: bool = False
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    intimacy: int | None = None
    breakup_risk: int | None = None
    friend_fee: int | None = None
    headline: str | None = None
    error: str | None = None


@dataclass
class Report:
    provider: str
    model: str
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def succeeded(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.ok]

    def rate(self, predicate) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for o in self.outcomes if predicate(o)) / len(self.outcomes)

    def spread(self, attribute: str) -> float:
        """서로 다른 대화에 서로 다른 값이 나오는가. 표준편차로 본다."""
        values = [
            getattr(o, attribute)
            for o in self.succeeded
            if getattr(o, attribute) is not None
        ]
        return statistics.pstdev(values) if len(values) >= 2 else 0.0

    def cost_krw(self) -> float:
        price = PRICES.get(self.model)
        if price is None:
            return -1.0
        inp, out = price
        total = sum(
            o.input_tokens / 1_000_000 * inp + o.output_tokens / 1_000_000 * out
            for o in self.succeeded
        )
        return total * USD_TO_KRW / max(1, len(self.succeeded))


def load_fixtures(directory: Path) -> list[Sample]:
    """OcrPage JSON 묶음을 읽는다.

    파일 하나가 대화 한 건이며, 최상위는 OcrPage 배열이다.
    """
    samples: list[Sample] = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        pages = tuple(OcrPage.model_validate(item) for item in raw)
        try:
            samples.append(Sample(label=path.stem, conversation=parse(pages)))
        except AppError as exc:
            print(f"  건너뜀 {path.name}: {exc.code.value}")
    return samples


def load_profiles(seeds: int) -> list[Sample]:
    """관계 스펙트럼 대화를 만든다. 기대 순위가 함께 붙는다."""
    from samples import build_all

    return [
        Sample(
            label=f"{profile.label}" + (f"#{index % seeds}" if seeds > 1 else ""),
            conversation=convo,
            rank=profile.rank,
            note=profile.note,
        )
        for index, (profile, convo) in enumerate(build_all(seeds))
    ]


async def synthesize(count: int) -> list[Sample]:
    """합성 대화를 만든다. 파이프라인 점검용이며 품질 평가용이 아니다."""
    engine = StubOcrEngine()
    samples: list[Sample] = []
    for index in range(count):
        images = [bytes([index, page]) * 512 for page in range(3)]
        pages = await engine.read(images)
        try:
            samples.append(Sample(label=f"합성-{index:02d}", conversation=parse(pages)))
        except AppError:
            continue
    return samples


def build_provider(
    name: str,
    model: str,
    key: str | None,
    base_url: str | None,
    reasoning_effort: str | None = None,
):
    if name == "stub":
        from app.ai.provider.stub import StubLlmProvider

        return StubLlmProvider()
    if name == "anthropic":
        from app.ai.provider.anthropic import AnthropicProvider

        return AnthropicProvider(model=model, api_key=key)

    from app.ai.provider.openai_compatible import OpenAiCompatibleProvider

    if not key:
        raise SystemExit(f"{name} 를 쓰려면 --key 가 필요합니다")
    return OpenAiCompatibleProvider(
        name=name,
        model=model,
        api_key=key,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
    )


async def run_one(provider, sample: Sample) -> Outcome:
    analysis_agent = AnalysisAgent(provider)
    report_agent = ReportAgent(provider)

    started = time.perf_counter()
    try:
        analysis = await analysis_agent.run(sample.conversation)
        scores = calculate_scores(sample.conversation, analysis)
        report = await report_agent.run(analysis, scores)
    except AppError as exc:
        return Outcome(
            label=sample.label,
            rank=sample.rank,
            ok=False,
            seconds=time.perf_counter() - started,
            error=exc.code.value,
        )

    return Outcome(
        label=sample.label,
        rank=sample.rank,
        ok=True,
        first_try=True,
        seconds=time.perf_counter() - started,
        intimacy=scores.intimacy,
        breakup_risk=scores.breakup_risk,
        friend_fee=scores.friend_fee,
        headline=report.headline,
    )


async def evaluate(
    provider, model: str, samples: Sequence[Sample], delay: float = 0.0
) -> Report:
    """대화를 하나씩 넣는다.

    `delay` 는 분당 토큰 한도를 넘지 않기 위한 간격이다. 0으로 두면 한도에
    걸려 429 가 쏟아지고, 그러면 성공률이 모델 품질이 아니라 우리 요청 속도를
    재게 된다.
    """
    report = Report(provider=provider.name, model=model)
    for index, sample in enumerate(samples, start=1):
        if index > 1 and delay:
            await asyncio.sleep(delay)
        print(f"  [{index}/{len(samples)}] {sample.label} …", end="", flush=True)
        outcome = await run_one(provider, sample)
        report.outcomes.append(outcome)
        print(" 성공" if outcome.ok else f" 실패({outcome.error})")
    return report


def print_discrimination(report: Report) -> None:
    """기대 순위를 맞혔는지 본다. 분산보다 이쪽이 중요하다.

    분산은 값이 널뛰기만 해도 커진다. 절친과 일방적 관계를 실제로 **구분**
    하는지 보려면 순서가 맞는지를 봐야 한다.
    """
    from samples import concordance

    graded = [o for o in report.succeeded if o.rank is not None]
    if not graded:
        return

    # 같은 프로필을 여러 씨앗으로 돌렸으면 평균을 낸다
    by_rank: dict[int, list[Outcome]] = {}
    for outcome in graded:
        by_rank.setdefault(outcome.rank, []).append(outcome)

    print("\n  -- 프로필별 결과 (위가 더 친하다고 기대한 관계) --")
    print(f"  {'관계':<14} {'친밀도':>7} {'손절위험':>9} {'친구비':>10}")
    ranked: list[tuple[int, float]] = []
    for rank in sorted(by_rank):
        group = by_rank[rank]
        label = group[0].label.split("#")[0]
        intimacy = statistics.mean(o.intimacy for o in group if o.intimacy is not None)
        risk = statistics.mean(o.breakup_risk for o in group if o.breakup_risk is not None)
        fee = statistics.mean(o.friend_fee for o in group if o.friend_fee is not None)
        print(f"  {label:<14} {intimacy:>7.0f} {risk:>9.0f} {fee:>10,.0f}")
        ranked.append((rank, intimacy))

    agree, total = concordance(ranked)
    if total == 0:
        print("\n  순위 일치도     잴 수 없음 (모든 관계에 같은 값을 냈습니다)")
        print("                  이 모델은 관계를 판단하지 않고 있습니다.")
        return

    rate = agree / total
    print(f"\n  순위 일치도     {agree}/{total} 쌍 ({rate:.0%})")
    if rate >= 0.85:
        print("                  기대한 순서를 지킵니다. 채택 후보입니다.")
    elif rate >= 0.65:
        print("                  대체로 맞지만 뒤집히는 쌍이 있습니다. 다른 후보와 비교하세요.")
    else:
        print("                  순서를 못 맞힙니다. 이 모델은 쓸 수 없습니다.")


def print_report(report: Report, repeats: list[list[int]] | None) -> None:
    line = "=" * 58
    print(f"\n{line}")
    print(f" {report.provider} / {report.model}")
    print(line)

    success = report.rate(lambda o: o.ok)
    print(f"  성공률          {success:.0%}  ({len(report.succeeded)}/{report.total})")

    if not report.succeeded:
        print("  성공한 건이 없어 나머지 지표를 낼 수 없습니다.")
        return

    latencies = [o.seconds for o in report.succeeded]
    print(f"  평균 소요       {statistics.mean(latencies):.2f}초")
    print(f"  최대 소요       {max(latencies):.2f}초")

    cost = report.cost_krw()
    print(f"  건당 비용       {'무료 또는 미상' if cost < 0 else f'{cost:.2f}원'}")

    print("\n  -- 결과 분산 (클수록 관계를 구분하고 있다는 뜻) --")
    for attribute, label in (
        ("intimacy", "친밀도"),
        ("breakup_risk", "손절 위험도"),
        ("friend_fee", "친구비"),
    ):
        spread = report.spread(attribute)
        values = [
            getattr(o, attribute) for o in report.succeeded if getattr(o, attribute)
        ]
        low, high = (min(values), max(values)) if values else (0, 0)
        print(f"  {label:<12} 표준편차 {spread:7.1f}   범위 {low} ~ {high}")

    if report.spread("intimacy") < 5:
        print("\n  경고: 친밀도가 거의 변하지 않습니다.")
        print("        어떤 대화를 넣어도 비슷한 값이 나온다면 관계를 읽지 못하는 것입니다.")

    print_discrimination(report)

    if repeats:
        deviations = [statistics.pstdev(run) for run in repeats if len(run) >= 2]
        if deviations:
            print(f"\n  재현성          같은 입력 반복 시 친밀도 편차 {statistics.mean(deviations):.1f}")

    headlines = {o.headline for o in report.succeeded if o.headline}
    print(f"\n  리포트 다양성   서로 다른 헤드라인 {len(headlines)}종 / {len(report.succeeded)}건")
    for headline in list(headlines)[:3]:
        print(f"    · {headline}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 후보 실측")
    parser.add_argument("--provider", default="stub")
    parser.add_argument("--model", default="stub")
    parser.add_argument("--key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        help="추론 모델의 사고 분량. gpt-oss 는 low, qwen 은 none",
    )
    parser.add_argument("--fixtures", type=Path, default=None, help="OcrPage JSON 디렉터리")
    parser.add_argument("--count", type=int, default=8, help="합성 대화 수")
    parser.add_argument(
        "--profiles",
        action="store_true",
        help="관계 스펙트럼 대화로 평가한다. 모델 선정은 이걸로 한다",
    )
    parser.add_argument("--seeds", type=int, default=1, help="프로필당 대화 수")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="대화 사이 간격(초). 분당 토큰 한도가 있는 곳에서는 채운다",
    )
    parser.add_argument("--repeat", type=int, default=0, help="재현성 확인 반복 횟수")
    args = parser.parse_args()

    if args.fixtures:
        print(f"픽스처를 읽는 중: {args.fixtures}")
        samples = load_fixtures(args.fixtures)
    elif args.profiles:
        print("관계 스펙트럼 대화를 만드는 중")
        samples = load_profiles(args.seeds)
        for sample in samples[: len(samples) // max(1, args.seeds)]:
            print(f"  {sample.rank}. {sample.label} — {sample.note}")
    else:
        print("합성 대화를 만드는 중 (파이프라인 점검용입니다)")
        print("  모델을 고르려면 --profiles 를 쓰세요. 이 대화들은 톤이 다 같습니다.")
        samples = await synthesize(args.count)

    if not samples:
        raise SystemExit("평가할 대화가 없습니다.")
    print(f"대화 {len(samples)}건 준비 완료\n")

    provider = build_provider(
        args.provider, args.model, args.key, args.base_url, args.reasoning_effort
    )
    report = await evaluate(provider, args.model, samples, delay=args.delay)

    repeats: list[list[int]] | None = None
    if args.repeat >= 2 and samples:
        print(f"\n재현성 확인: 같은 대화를 {args.repeat}회 반복")
        run: list[int] = []
        for _ in range(args.repeat):
            outcome = await run_one(provider, samples[0])
            if outcome.intimacy is not None:
                run.append(outcome.intimacy)
        repeats = [run]

    print_report(report, repeats)


if __name__ == "__main__":
    asyncio.run(main())
