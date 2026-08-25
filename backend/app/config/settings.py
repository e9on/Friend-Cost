"""런타임 설정.

기준 명세 8장: Provider와 모델명은 설정으로 분리하여 교체 가능하게 만든다.
9장의 제한값도 여기 모은다. 값을 바꿀 때 코드를 뒤지지 않아도 되게 하기 위해서다.

환경변수 접두사는 `FC_` 다. 예) `FC_TTL_SECONDS=1200`
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FC_", env_file=".env", extra="ignore")

    # --- 수명 ---
    ttl_seconds: int = 1_200  # 20분. 생성 시점 기준 고정형이며 조회로 연장되지 않는다

    # --- 업로드 제한 (API 명세 4장) ---
    max_images: int = 10
    min_images: int = 1
    max_image_bytes: int = 5 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024
    min_image_side: int = 320  # 이보다 작으면 글자를 읽을 수 없다

    # 총 화소 수 상한. 파일 크기와는 별개다.
    #
    # 균일한 색으로 채운 PNG는 33바이트로도 30000x30000을 선언할 수 있다.
    # 용량만 검사하면 그대로 OCR로 넘어가 처리 시간과 과금이 그대로 나간다.
    # 우리가 직접 디코드하지 않아 서버가 죽지는 않지만 비용이 샌다.
    #
    # 한 변이 아니라 총 화소를 보는 이유는, 변마다 상한을 두면
    # 8000x8000(6400만 화소) 같은 조합을 놓치기 때문이다.
    # 스크롤 캡처는 세로로 길어서 1080x12000(1300만 화소) 정도는 정상이다.
    max_image_pixels: int = 40_000_000
    allowed_mime_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp")

    # --- 요청 제한 (API 명세 9장) ---
    rate_limit_per_minute: int = 5
    daily_analysis_limit: int = 10
    concurrent_analysis_limit: int = 3
    poll_rate_limit_per_minute: int = 60
    poll_after_seconds: int = 2

    # --- 실행 시간 제한 (기준 명세 9장) ---
    total_timeout_seconds: int = 180
    ocr_timeout_seconds: int = 60
    llm_timeout_seconds: int = 45

    # --- 파이프라인 ---
    max_messages: int = 120  # 초과하면 샘플링한다

    # 만료 정리 주기. 조회되지 않은 작업도 사라지게 하는 장치다
    sweep_interval_seconds: int = 60

    # --- 교체 지점 ---
    # 후보와 선정 근거는 `AI-모델-선정-보고서.md` 참조.
    # 무료 티어라도 입력을 학습에 쓰는 곳은 쓸 수 없다. 우리는 사용자 본인이
    # 아니라 대화 상대방의 사적 메시지를 다루기 때문이다.
    llm_provider: Literal[
        "stub", "anthropic", "groq", "deepseek", "together", "openrouter"
    ] = "stub"
    ocr_engine: Literal["stub", "google_vision"] = "stub"

    # 어떤 모델을 쓸지는 실측으로 정한다. tools/evaluate_llm.py 참조.
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_key: str | None = None
    # OpenAI 호환 후보의 주소를 직접 지정할 때만 쓴다. 알려진 곳은 자동으로 채운다
    llm_base_url: str | None = None

    # anthropic Provider 전용.
    # 구조화된 추출 작업이라 낮은 추론 강도로 충분하다. 비용 목표와도 맞는다.
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"

    ocr_api_key: str | None = None

    # 배포 시 프론트 도메인을 넣는다. 기본값이 비어 있어 브라우저에서 호출되지
    # 않는다. 실수로 열린 채 배포되는 것보다, 설정을 잊어 안 되는 편이 낫다.
    # 후자는 즉시 드러난다.
    cors_origins: tuple[str, ...] = ()

    log_level: str = "INFO"

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(origin.strip() == "*" for origin in value):
            raise ValueError("CORS에 와일드카드를 쓰지 않는다")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
