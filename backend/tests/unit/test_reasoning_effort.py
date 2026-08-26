"""추론 모델의 출력 예산 문제.

Groq 의 gpt-oss·qwen 은 추론 모델이라 `reasoning` 에 토큰을 먼저 쓴다.
`max_tokens` 를 800으로 두면 추론이 예산을 다 먹고 본문을 한 글자도 내놓지
못한다. 그러면 Groq 이 빈 문자열을 JSON 으로 검증하다 400
(`json_validate_failed`)을 낸다. 실측에서 네 모델 모두 이 이유로 전멸했다.

추론량을 낮추면 넷 다 통과한다. 다만 **허용값이 계열마다 다르다.**
gpt-oss 는 low/medium/high 를, qwen 은 none/default 를 받는다. 그래서
설정으로 두고 코드에 박지 않는다.
"""

import httpx
import pytest

from app.ai.provider.base import LlmRequest
from app.ai.provider.openai_compatible import OpenAiCompatibleProvider


def capture(monkeypatch) -> dict:
    """실제로 나가는 요청 본문을 붙잡는다."""
    seen: dict = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, headers, json):
            seen["url"] = url
            seen["payload"] = json
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    return seen


@pytest.fixture
def request_():
    return LlmRequest(system="s", user="u", max_output_tokens=1500, purpose="analysis")


class TestReasoningEffort:
    @pytest.mark.asyncio
    async def test_설정하면_요청에_실린다(self, monkeypatch, request_):
        seen = capture(monkeypatch)
        provider = OpenAiCompatibleProvider(
            name="groq", model="openai/gpt-oss-120b", api_key="k",
            reasoning_effort="low",
        )

        await provider.complete(request_)

        assert seen["payload"]["reasoning_effort"] == "low"

    @pytest.mark.asyncio
    async def test_설정하지_않으면_보내지_않는다(self, monkeypatch, request_):
        # 추론 모델이 아닌 곳에 이 필드를 보내면 400 이 난다
        seen = capture(monkeypatch)
        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="k")

        await provider.complete(request_)

        assert "reasoning_effort" not in seen["payload"]

    @pytest.mark.asyncio
    async def test_qwen이_받는_값도_그대로_보낸다(self, monkeypatch, request_):
        # 계열마다 허용값이 다르므로 우리가 검증하지 않는다. 걸러내면
        # 새 모델이 나올 때마다 코드를 고쳐야 한다
        seen = capture(monkeypatch)
        provider = OpenAiCompatibleProvider(
            name="groq", model="qwen/qwen3.6-27b", api_key="k",
            reasoning_effort="none",
        )

        await provider.complete(request_)

        assert seen["payload"]["reasoning_effort"] == "none"


class TestOutputBudget:
    def test_분석_예산이_추론_모델을_감당한다(self):
        # 실측: gpt-oss-120b 가 reasoning_effort=low 로 486 토큰을 썼다.
        # 800 이면 추론만으로 소진되어 400 이 났다
        from app.ai.agent.analysis import MAX_OUTPUT_TOKENS

        assert MAX_OUTPUT_TOKENS >= 1500


class TestRateLimitRetry:
    """429 는 한 번 기다렸다 다시 던진다.

    무료 티어는 분당 요청 수가 빡빡하다. 한 번에 실패로 접으면 사용자는
    자기 잘못이 아닌 이유로 분석에 실패한다. 무한정 기다릴 수는 없으므로
    재시도는 한 번으로 묶는다.
    """

    @pytest.mark.asyncio
    async def test_한_번_기다렸다_다시_보낸다(self, monkeypatch, request_):
        calls = {"count": 0}
        slept: list[float] = []

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, *, headers, json):
                calls["count"] += 1
                if calls["count"] == 1:
                    return httpx.Response(429, headers={"retry-after": "2"}, json={})
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "{}"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    },
                )

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        import app.ai.provider.openai_compatible as module

        monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="k")
        result = await provider.complete(request_)

        assert calls["count"] == 2
        assert slept == [2.0], "Retry-After 를 따라야 한다"
        assert result.text == "{}"

    @pytest.mark.asyncio
    async def test_두_번째도_막히면_포기한다(self, monkeypatch, request_):
        from app.common.errors import AppError, ErrorCode

        calls = {"count": 0}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, *, headers, json):
                calls["count"] += 1
                return httpx.Response(429, json={})

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        import app.ai.provider.openai_compatible as module

        async def no_wait(seconds):
            return None

        monkeypatch.setattr(module.asyncio, "sleep", no_wait)

        provider = OpenAiCompatibleProvider(name="groq", model="m", api_key="k")
        with pytest.raises(AppError) as caught:
            await provider.complete(request_)

        assert caught.value.code is ErrorCode.LLM_FAILED
        assert calls["count"] == 2, "재시도는 한 번뿐이어야 한다"
