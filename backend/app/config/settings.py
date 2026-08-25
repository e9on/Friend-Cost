"""런타임 설정.

기준 명세 8장: Provider와 모델명은 설정으로 분리하여 교체 가능하게 만든다.
9장의 제한값도 여기 모은다. 값을 바꿀 때 코드를 뒤지지 않아도 되게 하기 위해서다.

환경변수 접두사는 `FC_` 다. 예) `FC_TTL_SECONDS=1200`
"""

from functools import lru_cache
from typing import Literal

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
    # 실제 모델은 성능 평가 이후에 붙인다. 그때 이 값만 바꾸면 된다.
    llm_provider: Literal["stub", "anthropic"] = "stub"
    ocr_engine: Literal["stub"] = "stub"

    # anthropic Provider를 쓸 때만 의미가 있다.
    # 어떤 모델을 쓸지는 tools/evaluate_llm.py 의 평가 결과로 정한다.
    llm_model: str = "claude-haiku-4-5"
    # 구조화된 추출 작업이라 낮은 추론 강도로 충분하다. 비용 목표와도 맞는다.
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    anthropic_api_key: str | None = None

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
