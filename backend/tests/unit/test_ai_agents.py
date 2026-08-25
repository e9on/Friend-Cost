"""Analysis Agent와 Report Agent.

기준 명세 7장. 실제 모델은 성능 평가 이후에 붙이므로, 여기서는
Provider 인터페이스와 검증·재시도 규약만 확인한다.
"""

import json

import pytest

from app.ai.agent.analysis import AnalysisAgent
from app.ai.agent.report import ReportAgent
from app.ai.provider.base import LlmProvider, LlmRequest, LlmResponse
from app.ai.provider.stub import StubLlmProvider
from app.common.errors import AppError, ErrorCode
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.report import DISCLAIMER, ReportData
from tests.builders import alternating, analysis, conversation


class ScriptedProvider(LlmProvider):
    """미리 정해둔 응답을 순서대로 돌려주는 가짜 Provider."""

    name = "scripted"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("예정된 응답보다 많이 호출되었다")
        return LlmResponse(text=self._responses.pop(0), input_tokens=10, output_tokens=5)


class ExplodingProvider(LlmProvider):
    name = "exploding"

    async def complete(self, request: LlmRequest) -> LlmResponse:
        raise TimeoutError("연결 실패")


def valid_analysis_json() -> str:
    return analysis().model_dump_json(by_alias=True)


def valid_report_json() -> str:
    return json.dumps(
        {
            "headline": "서로 챙기지만 균형이 조금 기운 사이",
            "summary": "연락은 이어지지만 시작하는 쪽이 한쪽으로 쏠려 있다.",
            "sections": [
                {"title": "연락의 흐름", "body": "먼저 말을 거는 쪽이 대체로 정해져 있다."},
                {"title": "지켜볼 지점", "body": "약속이 미뤄지는 일이 반복되고 있다."},
            ],
            "advice": "다음 약속은 날짜부터 먼저 정해 보자.",
        },
        ensure_ascii=False,
    )


class TestAnalysisAgent:
    async def test_returns_structured_analysis(self):
        provider = ScriptedProvider(valid_analysis_json())

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)
        assert 0 <= result.conflict_level <= 100

    async def test_retries_once_when_the_schema_does_not_match(self):
        provider = ScriptedProvider("이건 JSON이 아니다", valid_analysis_json())

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)
        assert len(provider.requests) == 2

    async def test_gives_up_after_the_single_retry(self):
        provider = ScriptedProvider("망가진 응답", "여전히 망가진 응답")

        with pytest.raises(AppError) as caught:
            await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert caught.value.code is ErrorCode.LLM_SCHEMA_INVALID
        assert len(provider.requests) == 2

    async def test_transport_failure_maps_to_llm_failed(self):
        with pytest.raises(AppError) as caught:
            await AnalysisAgent(ExplodingProvider()).run(conversation(alternating(20)))

        assert caught.value.code is ErrorCode.LLM_FAILED

    async def test_clamps_out_of_range_values_instead_of_failing(self):
        payload = json.loads(valid_analysis_json())
        payload["conflictLevel"] = 480
        provider = ScriptedProvider(json.dumps(payload))

        result = await AnalysisAgent(provider).run(conversation(alternating(20)))

        assert result.conflict_level == 100

    async def test_prompt_marks_the_conversation_as_untrusted_data(self):
        provider = ScriptedProvider(valid_analysis_json())

        await AnalysisAgent(provider).run(conversation(alternating(20)))

        prompt = provider.requests[0].user
        assert "<conversation>" in prompt and "</conversation>" in prompt
        system = provider.requests[0].system
        assert "지시" in system  # 대화 안의 지시를 따르지 말라는 방어 문구


class TestReportAgent:
    async def test_returns_a_report(self):
        provider = ScriptedProvider(valid_report_json())
        scores = _scores()

        result = await ReportAgent(provider).run(analysis(), scores)

        assert isinstance(result, ReportData)
        assert result.disclaimer == DISCLAIMER

    async def test_disclaimer_is_injected_by_the_server(self):
        payload = json.loads(valid_report_json())
        payload["disclaimer"] = "모델이 멋대로 쓴 문구"
        provider = ScriptedProvider(json.dumps(payload, ensure_ascii=False))

        result = await ReportAgent(provider).run(analysis(), _scores())

        assert result.disclaimer == DISCLAIMER

    async def test_does_not_receive_the_conversation_text(self):
        provider = ScriptedProvider(valid_report_json())

        await ReportAgent(provider).run(analysis(), _scores())

        prompt = provider.requests[0].user
        assert "<conversation>" not in prompt

    async def test_rejects_a_report_that_exceeds_length_limits(self):
        payload = json.loads(valid_report_json())
        payload["summary"] = "가" * 500
        provider = ScriptedProvider(
            json.dumps(payload, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)
        )

        with pytest.raises(AppError) as caught:
            await ReportAgent(provider).run(analysis(), _scores())

        assert caught.value.code is ErrorCode.LLM_SCHEMA_INVALID


class TestStubProvider:
    async def test_produces_valid_analysis_payloads(self):
        result = await AnalysisAgent(StubLlmProvider()).run(conversation(alternating(20)))

        assert isinstance(result, RelationshipAnalysisData)

    async def test_produces_valid_report_payloads(self):
        result = await ReportAgent(StubLlmProvider()).run(analysis(), _scores())

        assert isinstance(result, ReportData)

    async def test_is_deterministic_for_the_same_input(self):
        convo = conversation(alternating(20))

        first = await AnalysisAgent(StubLlmProvider()).run(convo)
        second = await AnalysisAgent(StubLlmProvider()).run(convo)

        assert first == second

    async def test_varies_with_the_conversation(self):
        talkative = conversation(alternating(60))
        quiet = conversation(alternating(20))

        a = await AnalysisAgent(StubLlmProvider()).run(talkative)
        b = await AnalysisAgent(StubLlmProvider()).run(quiet)

        assert a != b


def _scores():
    from app.algorithm.calculator import calculate_scores

    return calculate_scores(conversation(alternating(20)), analysis())
