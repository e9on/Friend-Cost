"""규모별 운영 비용을 계산한다.

`AI-모델-선정-보고서.md` 6장.

100건/월만 보고 "비용은 문제가 아니다"라고 결론 내렸는데, 규모가 커지면
무엇이 비용을 지배하는지 달라진다. 그 전환점을 계산한다.

    python tools/cost_model.py
    python tools/cost_model.py --images 5 --llm haiku
    python tools/cost_model.py --volumes 100 1000 5000 20000

단가는 2026년 8월 기준 공개 가격이다. 바뀌면 아래 상수를 고친다.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _console import force_utf8  # noqa: E402

force_utf8()

USD_TO_KRW = 1_400

# --- OCR ---
# Google Cloud Vision: 월 1,000 units 무료, 이후 1,000당 $1.50
VISION_FREE_UNITS = 1_000
VISION_PER_1K_USD = 1.50

# Naver CLOVA OCR: 월 1,000건 무료, 이후 건당 약 10원
CLOVA_FREE_UNITS = 1_000
CLOVA_PER_UNIT_KRW = 10.0

# 자체 호스팅 OCR: 상시 실행 인스턴스가 필요하다.
# 소형 인스턴스 월 $7 안팎. 스케일-투-제로를 포기하는 대가다.
SELF_HOSTED_MONTHLY_USD = 7.0

# --- Cloud Run ---
# 무료: vCPU 180,000초, 메모리 360,000 GiB-초, 요청 200만
RUN_FREE_VCPU_SECONDS = 180_000
RUN_FREE_GIB_SECONDS = 360_000
RUN_VCPU_SECOND_USD = 0.000024
RUN_GIB_SECOND_USD = 0.0000025
# 분석 1건이 붙잡는 시간과 메모리
RUN_SECONDS_PER_ANALYSIS = 60
RUN_MEMORY_GIB = 0.5

# --- LLM (100만 토큰당 입력/출력 달러) ---
# 워크로드: 분석 호출 입력 4,500 + 출력 1,000, 리포트 호출 입력 2,000 + 출력 600
LLM_INPUT_TOKENS = 6_500
LLM_OUTPUT_TOKENS = 1_600

LLM_PRICES: dict[str, tuple[float, float]] = {
    "groq": (0.0, 0.0),  # 무료 티어. 하루 1,000요청 = 500건
    "qwen-flash": (0.03, 0.13),
    "gemini-flash-lite": (0.10, 0.40),
    "deepseek": (0.14, 0.28),
    "haiku": (1.00, 5.00),
    "sonnet": (2.00, 10.00),
}
# Groq 무료 티어 한도. 분석 1건에 LLM 2회를 쓴다
GROQ_DAILY_REQUESTS = 1_000
GROQ_MONTHLY_ANALYSES = GROQ_DAILY_REQUESTS // 2 * 30


@dataclass
class Breakdown:
    ocr: float
    llm: float
    server: float

    @property
    def total(self) -> float:
        return self.ocr + self.llm + self.server


def vision_cost(images: int) -> float:
    billable = max(0, images - VISION_FREE_UNITS)
    return billable / 1_000 * VISION_PER_1K_USD * USD_TO_KRW


def clova_cost(images: int) -> float:
    return max(0, images - CLOVA_FREE_UNITS) * CLOVA_PER_UNIT_KRW


def self_hosted_cost(_images: int) -> float:
    """상시 실행이라 건수와 무관하게 고정이다."""
    return SELF_HOSTED_MONTHLY_USD * USD_TO_KRW


OCR_OPTIONS = {
    "vision": ("Google Vision", vision_cost),
    "clova": ("Naver CLOVA", clova_cost),
    "self": ("자체 호스팅", self_hosted_cost),
}


def llm_cost(analyses: int, model: str) -> float:
    if model == "groq" and analyses > GROQ_MONTHLY_ANALYSES:
        # 무료 한도를 넘으면 유료 후보로 넘어가야 한다
        return float("nan")
    inp, out = LLM_PRICES[model]
    per_analysis = (
        LLM_INPUT_TOKENS / 1_000_000 * inp + LLM_OUTPUT_TOKENS / 1_000_000 * out
    )
    return per_analysis * analyses * USD_TO_KRW


def server_cost(analyses: int) -> float:
    vcpu = analyses * RUN_SECONDS_PER_ANALYSIS
    gib = vcpu * RUN_MEMORY_GIB
    billable_vcpu = max(0, vcpu - RUN_FREE_VCPU_SECONDS)
    billable_gib = max(0, gib - RUN_FREE_GIB_SECONDS)
    usd = billable_vcpu * RUN_VCPU_SECOND_USD + billable_gib * RUN_GIB_SECOND_USD
    return usd * USD_TO_KRW


def breakdown(analyses: int, images_each: int, ocr: str, model: str) -> Breakdown:
    images = analyses * images_each
    return Breakdown(
        ocr=OCR_OPTIONS[ocr][1](images),
        llm=llm_cost(analyses, model),
        server=server_cost(analyses),
    )


def won(value: float) -> str:
    if value != value:  # NaN
        return "한도초과"
    return f"{round(value):,}원"


def crossover(images_each: int) -> int:
    """자체 호스팅이 Vision API보다 싸지는 월 분석 건수."""
    fixed = self_hosted_cost(0)
    analyses = 1
    while analyses < 1_000_000:
        if vision_cost(analyses * images_each) >= fixed:
            return analyses
        analyses += 10
    return -1


def main() -> None:
    parser = argparse.ArgumentParser(description="규모별 운영 비용")
    parser.add_argument("--images", type=int, default=5, help="분석당 이미지 수")
    parser.add_argument(
        "--volumes",
        type=int,
        nargs="+",
        default=[100, 500, 1_000, 5_000, 20_000],
        help="월 분석 건수",
    )
    args = parser.parse_args()

    print(f"분석당 이미지 {args.images}장 기준, 환율 {USD_TO_KRW:,}원\n")

    for ocr_key, (ocr_label, _) in OCR_OPTIONS.items():
        print(f"{'=' * 74}")
        print(f" OCR: {ocr_label}")
        print("=" * 74)
        header = f"{'월 건수':>8} │ {'OCR':>10} {'서버':>9} │"
        for model in ("groq", "qwen-flash", "haiku"):
            header += f" {model:>11}"
        print(header)
        print("-" * 74)

        for volume in args.volumes:
            base = breakdown(volume, args.images, ocr_key, "groq")
            row = f"{volume:>8,} │ {won(base.ocr):>10} {won(base.server):>9} │"
            for model in ("groq", "qwen-flash", "haiku"):
                data = breakdown(volume, args.images, ocr_key, model)
                row += f" {won(data.total):>11}"
            print(row)
        print()

    point = crossover(args.images)
    print("=" * 74)
    print(" 전환점")
    print("=" * 74)
    print(f"  자체 호스팅 OCR이 Vision API보다 싸지는 지점: 월 약 {point:,}건")
    print(f"  Groq 무료 티어 한도: 월 {GROQ_MONTHLY_ANALYSES:,}건 (하루 500건)")
    print()
    print("  주의: 자체 호스팅은 상시 실행이라 스케일-투-제로를 포기한다.")
    print("        서버 비용이 함께 오르므로 위 표의 '서버' 열도 달라진다.")


if __name__ == "__main__":
    main()
