"""테스트를 개발자의 로컬 설정에서 떼어낸다.

`Settings` 는 `.env` 를 읽는다. 그래서 로컬에 `.env` 를 두는 순간 테스트가
그 값을 집어 든다. 실제로 `FC_LLM_PROVIDER=groq` 를 적어둔 `.env` 를 만들자
테스트 12개가 깨졌다. 코드는 그대로였다.

이 상태를 방치하면 두 방향으로 나쁘다. 실제 키를 넣어둔 사람은 테스트가
외부 호출을 하게 되고, 값이 조금 다른 사람은 자기 잘못이 아닌 실패를 본다.
CI 는 통과하는데 로컬만 깨지는 것도 여기서 온다.

테스트는 **기본값을 검증하는 것**이므로 `.env` 도 `FC_` 환경변수도 보지
않는다. 특정 값을 쓰려면 `Settings(...)` 에 명시한다.

**세션 스코프여야 한다.** pytest 는 넓은 스코프의 픽스처를 먼저 만든다.
함수 스코프로 두면 모듈 스코프 `settings` 픽스처가 정리 전에 만들어져
환경변수가 그대로 새어 들어간다. 실제로 그렇게 짰다가 두 개가 남았다.
"""

import os
from typing import Iterator

import pytest

from app.config.settings import Settings


@pytest.fixture(autouse=True, scope="session")
def _isolate_settings() -> Iterator[None]:
    saved = {name: os.environ[name] for name in os.environ if name.startswith("FC_")}
    for name in saved:
        del os.environ[name]

    original = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None
    try:
        yield
    finally:
        Settings.model_config["env_file"] = original
        os.environ.update(saved)
