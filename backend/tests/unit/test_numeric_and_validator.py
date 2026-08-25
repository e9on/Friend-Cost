"""반올림 규칙과 LLM 응답 검증.

점수 산식은 사람이 손으로 검산하는 문서를 따라야 하므로 항상 사사오입한다.
파이썬 내장 `round` 는 은행가 반올림이라 `round(0.5) == 0` 이 되어 문서와 어긋난다.
"""

import json

import pytest

from app.ai.validator.schema import SchemaMismatch, parse_json_response
from app.common.numeric import (
    clamp,
    clamp_score,
    round_half_up,
    round_ratio,
    round_to_unit,
)
from app.domain.model.analysis import RelationshipAnalysisData
from app.domain.model.report import ReportData
from tests.builders import analysis


class TestRoundHalfUp:
    @pytest.mark.parametrize(
        "value, expected",
        [(0.5, 1), (1.5, 2), (2.5, 3), (0.4, 0), (0.6, 1), (73.913, 74), (38.35, 38)],
    )
    def test_always_rounds_half_upwards(self, value, expected):
        assert round_half_up(value) == expected

    def test_differs_from_the_builtin_on_ties(self):
        # 내장 round는 0.5를 0으로 내린다. 문서의 손계산과 어긋나는 지점이다
        assert round(0.5) == 0
        assert round_half_up(0.5) == 1

    def test_handles_negatives(self):
        assert round_half_up(-0.4) == 0
        assert round_half_up(-1.5) == -2


class TestRoundToUnit:
    @pytest.mark.parametrize(
        "value, expected",
        [(45_100.8, 45_000), (45_500, 46_000), (45_499, 45_000), (999, 1_000), (400, 0)],
    )
    def test_rounds_to_the_nearest_thousand(self, value, expected):
        assert round_to_unit(value, 1_000) == expected


class TestClamp:
    def test_clamps_into_range(self):
        assert clamp(150, 0, 100) == 100
        assert clamp(-20, 0, 100) == 0
        assert clamp(50, 0, 100) == 50

    def test_clamp_score_rounds_and_clamps(self):
        assert clamp_score(63.55) == 64
        assert clamp_score(480) == 100
        assert clamp_score(-30) == 0


class TestRoundRatio:
    def test_keeps_three_decimals(self):
        assert round_ratio(0.63157) == 0.632
        assert round_ratio(0.6315) == 0.632
        assert round_ratio(1.0) == 1.0


class TestParseJsonResponse:
    def test_reads_a_plain_json_object(self):
        payload = analysis().model_dump_json(by_alias=True)

        assert isinstance(
            parse_json_response(payload, RelationshipAnalysisData), RelationshipAnalysisData
        )

    def test_strips_a_code_fence(self):
        payload = "```json\n" + analysis().model_dump_json(by_alias=True) + "\n```"

        assert isinstance(
            parse_json_response(payload, RelationshipAnalysisData), RelationshipAnalysisData
        )

    def test_strips_a_bare_fence(self):
        payload = "```\n" + analysis().model_dump_json(by_alias=True) + "\n```"

        assert isinstance(
            parse_json_response(payload, RelationshipAnalysisData), RelationshipAnalysisData
        )

    @pytest.mark.parametrize("payload", ["설명을 곁들인 답", "", "null", "[1, 2, 3]", '"문자열"'])
    def test_rejects_anything_that_is_not_an_object(self, payload):
        with pytest.raises(SchemaMismatch):
            parse_json_response(payload, RelationshipAnalysisData)

    def test_rejects_a_missing_field(self):
        payload = json.loads(analysis().model_dump_json(by_alias=True))
        del payload["conflictLevel"]

        with pytest.raises(SchemaMismatch):
            parse_json_response(json.dumps(payload), RelationshipAnalysisData)


class TestClampingBehaviour:
    """범위를 벗어난 값은 잘라 쓰고, 구조가 어긋나면 다시 물어본다.

    0~100 자리에 480이 왔다면 의도는 명확하니 잘라 쓰는 편이 낫지만,
    필드가 통째로 없다면 무엇을 채워야 할지 알 수 없다.
    """

    def test_scores_above_one_hundred_are_clamped(self):
        payload = json.loads(analysis().model_dump_json(by_alias=True))
        payload["conflictLevel"] = 480
        payload["emotionalTone"]["me"] = 900

        result = parse_json_response(json.dumps(payload), RelationshipAnalysisData)

        assert result.conflict_level == 100
        assert result.emotional_tone.me == 100

    def test_negative_scores_are_clamped_to_zero(self):
        payload = json.loads(analysis().model_dump_json(by_alias=True))
        payload["topicDepth"] = -50

        result = parse_json_response(json.dumps(payload), RelationshipAnalysisData)

        assert result.topic_depth == 0

    def test_count_fields_are_not_capped_at_one_hundred(self):
        """약속 건수와 금전 건수에는 상한이 없다."""
        payload = json.loads(analysis().model_dump_json(by_alias=True))
        payload["promiseSignals"]["proposed"] = 500

        result = parse_json_response(json.dumps(payload), RelationshipAnalysisData)

        assert result.promise_signals.proposed == 500

    def test_negative_counts_are_still_clamped(self):
        payload = json.loads(analysis().model_dump_json(by_alias=True))
        payload["moneySignals"]["lent"] = -3

        result = parse_json_response(json.dumps(payload), RelationshipAnalysisData)

        assert result.money_signals.lent == 0


class TestReportLengthLimits:
    """글자 수 상한은 출력 토큰 비용을 통제하기 위한 규격이며 권고가 아니다."""

    def base_report(self) -> dict:
        return {
            "headline": "한 줄 요약",
            "summary": "요약",
            "sections": [
                {"title": "제목1", "body": "본문1"},
                {"title": "제목2", "body": "본문2"},
            ],
            "advice": "제안",
        }

    @pytest.mark.parametrize(
        "field, length",
        [("headline", 41), ("summary", 201), ("advice", 151)],
    )
    def test_rejects_overlong_fields(self, field, length):
        payload = self.base_report()
        payload[field] = "가" * length

        with pytest.raises(SchemaMismatch):
            parse_json_response(json.dumps(payload, ensure_ascii=False), ReportData)

    def test_rejects_a_single_section(self):
        payload = self.base_report()
        payload["sections"] = payload["sections"][:1]

        with pytest.raises(SchemaMismatch):
            parse_json_response(json.dumps(payload, ensure_ascii=False), ReportData)

    def test_rejects_four_sections(self):
        payload = self.base_report()
        payload["sections"] = payload["sections"] * 2

        with pytest.raises(SchemaMismatch):
            parse_json_response(json.dumps(payload, ensure_ascii=False), ReportData)

    def test_accepts_three_sections(self):
        payload = self.base_report()
        payload["sections"].append({"title": "제목3", "body": "본문3"})

        result = parse_json_response(json.dumps(payload, ensure_ascii=False), ReportData)

        assert len(result.sections) == 3
