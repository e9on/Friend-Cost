"""후보 모델을 같은 대화로 나란히 재고 표 하나로 낸다.

`evaluate_llm.py` 는 모델 하나를 자세히 본다. 이건 여러 모델을 **같은 입력**
으로 돌려 고르기 위한 것이다. 모델마다 따로 돌리면 결과를 네 번 읽고 머릿속
에서 비교해야 하는데, 그러다 보면 성공률처럼 눈에 띄는 지표만 보고 정하게
된다.

    python tools/compare_llm.py --key gsk_...
    python tools/compare_llm.py --key gsk_... --models openai/gpt-oss-120b openai/gpt-oss-20b

**고르는 기준은 순위 일치도다.** 성공률이 100%여도 절친과 일방적 관계를
구분하지 못하면 쓸 수 없다. 그런 모델은 오류를 내지 않으므로 눈에 띄지 않고,
사용자는 그 결과가 자기 관계를 반영한다고 믿는다.
"""

import argparse
import asyncio
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

from evaluate_llm import (  # noqa: E402
    Report,
    build_provider,
    evaluate,
    load_profiles,
)
from samples import concordance  # noqa: E402

# Groq 무료 티어에서 지금 쓸 수 있는 텍스트 모델. 목록은 자주 바뀌므로
# console.groq.com/docs/models 에서 확인하고 고친다
# 문서 페이지와 계정에서 실제로 보이는 목록이 다르다. llama-3.3-70b-versatile
# 은 문서에 production 으로 남아 있지만 /v1/models 에 없었다. 돌리기 전에
# GET /openai/v1/models 로 확인한다
DEFAULT_MODELS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
)

# 무료 티어의 실제 병목은 요청 수가 아니라 **분당 토큰(TPM)** 이다.
# 실측(x-ratelimit-limit-tokens): 8,000 TPM, 요청은 하루 1,000건.
# 대화 한 건이 분석 1,500 + 리포트 1,100 토큰쯤 쓰므로 분당 세 건이 상한이다.
#
# 이걸 무시하고 던지면 429 가 쏟아지고, 그러면 성공률이 모델 품질이 아니라
# 우리 요청 속도를 재게 된다. 그 숫자로 모델을 고르면 안 된다
TOKENS_PER_MINUTE = 8_000
TOKENS_PER_CONVERSATION = 2_600
DELAY_SECONDS = 60 * TOKENS_PER_CONVERSATION / TOKENS_PER_MINUTE

# 모델을 갈아탈 때는 한도가 따로 잡히므로 짧게만 쉰다
COOLDOWN_SECONDS = 5

# 추론 모델은 사고 분량을 묶지 않으면 출력 예산을 다 먹고 본문을 못 내놓는다.
# 실측에서 gpt-oss 는 medium, qwen3.6 은 default 로 두면 400 이 났다.
# **허용값이 계열마다 다르다.** gpt-oss: low/medium/high, qwen: none/default
REASONING_EFFORT: dict[str, str] = {
    "openai/gpt-oss": "low",
    "qwen/": "none",
}


def effort_for(model: str) -> str | None:
    for prefix, value in REASONING_EFFORT.items():
        if model.startswith(prefix):
            return value
    return None


@dataclass
class Row:
    model: str
    success: float
    agree: int
    total: int
    intimacy_spread: float
    seconds: float
    headlines: int
    error: str | None = None

    @property
    def rate(self) -> float:
        return self.agree / self.total if self.total else 0.0


def summarize(model: str, report: Report) -> Row:
    if not report.succeeded:
        return Row(model, 0.0, 0, 0, 0.0, 0.0, 0, error="성공한 건이 없음")

    by_rank: dict[int, list[float]] = {}
    for outcome in report.succeeded:
        if outcome.rank is not None and outcome.intimacy is not None:
            by_rank.setdefault(outcome.rank, []).append(outcome.intimacy)
    ranked = [(rank, statistics.mean(values)) for rank, values in sorted(by_rank.items())]
    agree, total = concordance(ranked)

    return Row(
        model=model,
        success=report.rate(lambda o: o.ok),
        agree=agree,
        total=total,
        intimacy_spread=report.spread("intimacy"),
        seconds=statistics.mean(o.seconds for o in report.succeeded),
        headlines=len({o.headline for o in report.succeeded if o.headline}),
    )


# 이 밑이면 관계를 구분하지 못한다고 본다. evaluate_llm 의 판정과 같은 값이라
# 두 도구가 서로 다른 결론을 내놓지 않는다
MIN_AGREEMENT = 0.65


def print_table(rows: list[Row], provider: str) -> None:
    line = "=" * 76
    print(f"\n{line}")
    print(" 후보 비교 — 같은 대화 6건을 모든 모델에 넣었다")
    print(line)
    print(f" {'모델':<26}{'성공률':>7}{'순위일치':>10}{'친밀도편차':>11}{'평균소요':>9}{'헤드라인':>9}")
    print("-" * 76)

    for row in rows:
        if row.error:
            print(f" {row.model:<26}{row.error:>43}")
            continue
        agreement = "잴 수 없음" if row.total == 0 else f"{row.rate:.0%}"
        print(
            f" {row.model:<26}{row.success:>6.0%}{agreement:>10}"
            f"{row.intimacy_spread:>11.1f}{row.seconds:>8.1f}초{row.headlines:>8}종"
        )

    print(line)
    usable = [
        r
        for r in rows
        if not r.error and r.total > 0 and r.success >= 0.9 and r.rate >= MIN_AGREEMENT
    ]
    if not usable:
        print(" 채택할 만한 후보가 없습니다.")
        print(" 성공률이 낮으면 스키마 준수 문제이고, 순위를 못 맞히면 관계를 못 읽는 것입니다.")
        print(f" 순위 일치도가 {MIN_AGREEMENT:.0%} 미만인 모델은 권장하지 않습니다.")
        return

    # 순위 일치도가 같으면 분산이 큰 쪽을 고른다. 같은 순서를 지키면서 값을
    # 더 벌리는 모델이 사용자에게 더 또렷한 결과를 준다
    best = max(usable, key=lambda r: (r.rate, r.intimacy_spread))
    print(f" 권장: {best.model}")
    print(f"       순위 일치 {best.agree}/{best.total} ({best.rate:.0%}), 친밀도 편차 {best.intimacy_spread:.1f}")
    if best.rate < 0.85:
        print("       다만 일치도가 넉넉하지 않습니다. 프롬프트를 손보고 다시 재는 편이 낫습니다.")
    print()
    print(" 채택하려면 설정만 바꿉니다. 코드는 고치지 않습니다:")
    print(f"   FC_LLM_PROVIDER={provider}  FC_LLM_MODEL={best.model}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="후보 모델 나란히 비교")
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--key", required=True)
    parser.add_argument("--base-url", default=None)
    parser.add_argument(
        "--reasoning-effort", default=None, help="비우면 모델별 기본값을 쓴다"
    )
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--seeds", type=int, default=1, help="프로필당 대화 수")
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_SECONDS,
        help="대화 사이 간격(초). 분당 토큰 한도에 맞춘 값이 기본이다",
    )
    args = parser.parse_args()

    samples = load_profiles(args.seeds)
    print(f"대화 {len(samples)}건 × 모델 {len(args.models)}개")
    print(f"LLM 호출 약 {len(samples) * len(args.models) * 2}회\n")

    rows: list[Row] = []
    for index, model in enumerate(args.models):
        print(f"[{index + 1}/{len(args.models)}] {model}")
        try:
            effort = args.reasoning_effort or effort_for(model)
            print(f"  reasoning_effort={effort or '보내지 않음'}")
            provider = build_provider(
                args.provider, model, args.key, args.base_url, effort
            )
            report = await evaluate(provider, model, samples, delay=args.delay)
            rows.append(summarize(model, report))
        except Exception as exc:  # 한 모델이 죽어도 나머지는 재야 한다
            print(f"  건너뜀: {type(exc).__name__} {exc}")
            rows.append(Row(model, 0.0, 0, 0, 0.0, 0.0, 0, error=type(exc).__name__))
        if index + 1 < len(args.models):
            await asyncio.sleep(COOLDOWN_SECONDS)
        print()

    print_table(rows, args.provider)


if __name__ == "__main__":
    asyncio.run(main())
