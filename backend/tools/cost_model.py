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

# 자체 호스팅 OCR: 상시 실행 인스턴스가 필요하다. 어디에 띄우느냐로 갈린다.
#
# **"로컬 PC에서 돌린다"는 뜻이 아니다.** 클라우드 컨테이너 안에 OCR 모델을
# 넣어 Vision API 호출을 대신한다는 뜻이다. 배포처는 여전히 클라우드다.
#
# Cloud Run: 최소 인스턴스를 1로 두면 유휴 요금이 붙는다. 1 vCPU + 2GiB
# 기준 시간당 약 $0.027. 스케일-투-제로를 포기하는 대가가 여기서 나온다.
# 무료 한도(vCPU 180,000초)는 상시 실행 한 달치의 7%밖에 덮지 못한다.
SELF_HOSTED_CLOUDRUN_HOURLY_USD = 0.027

# 저가 VPS: 월 고정 요금. 훨씬 싸지만 관리 부담을 직접 진다.
# OS 패치, HTTPS 인증서, 모니터링, 장애 대응이 모두 우리 몫이 된다.
SELF_HOSTED_VPS_MONTHLY_USD = 7.0

HOURS_PER_MONTH = 730

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


def self_hosted_cloudrun_cost(_images: int) -> float:
    """Cloud Run 최소 인스턴스 1. 상시 실행이라 건수와 무관하게 고정이다."""
    return SELF_HOSTED_CLOUDRUN_HOURLY_USD * HOURS_PER_MONTH * USD_TO_KRW


def self_hosted_vps_cost(_images: int) -> float:
    """저가 VPS. 싸지만 서버 관리를 직접 한다."""
    return SELF_HOSTED_VPS_MONTHLY_USD * USD_TO_KRW


OCR_OPTIONS = {
    "vision": ("Google Vision (API)", vision_cost),
    "clova": ("Naver CLOVA (API)", clova_cost),
    "self_run": ("자체 호스팅 — Cloud Run 상시", self_hosted_cloudrun_cost),
    "self_vps": ("자체 호스팅 — 저가 VPS", self_hosted_vps_cost),
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


def crossover(images_each: int, fixed_cost: float) -> int:
    """고정 비용이 Vision API 비용을 넘어서는 월 분석 건수."""
    analyses = 1
    while analyses < 1_000_000:
        if vision_cost(analyses * images_each) >= fixed_cost:
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

    print("=" * 74)
    print(" 전환점 — 자체 호스팅이 Vision API보다 싸지는 지점")
    print("=" * 74)
    for key in ("self_run", "self_vps"):
        label, fn = OCR_OPTIONS[key]
        fixed = fn(0)
        point = crossover(args.images, fixed)
        print(f"  {label:<28} 고정 {won(fixed):>10}  →  월 약 {point:,}건")
    print()
    print(f"  Groq 무료 티어 한도: 월 {GROQ_MONTHLY_ANALYSES:,}건 (하루 500건)")
    print()
    print("  자체 호스팅은 '로컬 PC에서 돌린다'는 뜻이 아니다.")
    print("  클라우드 컨테이너 안에 OCR 모델을 넣어 API 호출을 대신한다는 뜻이다.")
    print()
    print("  Cloud Run 상시 실행은 스케일-투-제로를 포기하는 것이고,")
    print("  VPS는 싸지만 OS 패치·인증서·모니터링을 직접 진다.")


if __name__ == "__main__":
    main()
