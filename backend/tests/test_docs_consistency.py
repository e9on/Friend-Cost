"""문서와 코드가 어긋나지 않는지 검사한다.

기준 명세 12장은 "데이터 구조나 명칭을 바꿀 때는 데이터 계약 명세를 먼저
고치고 나머지를 따라 고친다"고 정했다. 그런데 사람이 지키는 규칙은 언젠가
깨진다. 코드를 고치고 문서를 잊는 쪽이 훨씬 흔하다.

그래서 **문서의 숫자와 코드의 상수를 직접 비교한다.** 어느 한쪽만 바뀌면
여기서 걸린다.

이 테스트가 깨지면 둘 중 하나가 틀린 것이다. 어느 쪽인지는 사람이 판단한다.
"""

import re
from pathlib import Path

import pytest

from app.algorithm.rule import constants
from app.common.errors import ErrorCode, http_status_of, is_retryable
from app.config.settings import Settings
from app.domain.model.report import ReportData
from app.domain.model.score import FEE_MAX, FEE_MIN
from app.domain.value_object.enums import Confidence, JobStage, JobStatus

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "mdfiles"
ROOT_README = ROOT / "README.md"

CONTRACT = DOCS / "데이터-계약-명세.md"
SCORING = DOCS / "관계-점수-계산-규칙.md"
API = DOCS / "API-명세.md"
BASE = DOCS / "친구비-측정기-서비스-기준-명세.md"
OCR = DOCS / "OCR-Parser-명세.md"
PROMPT = DOCS / "AI-프롬프트-명세.md"


def read(path: Path) -> str:
    assert path.exists(), f"문서가 없다: {path.name}"
    return path.read_text(encoding="utf-8")


class TestDocsExist:
    """기준 명세가 예고한 하위 문서가 실제로 있는지."""

    def test_every_referenced_doc_exists(self):
        text = read(BASE)
        referenced = set(re.findall(r"`([^`]+\.md)`", text))

        missing = [name for name in referenced if not (DOCS / name).exists()]

        assert not missing, f"기준 명세가 가리키는 문서가 없다: {missing}"

    def test_sub_docs_point_back_to_the_base_spec(self):
        for path in DOCS.glob("*.md"):
            if path.name.startswith("친구비-측정기"):
                continue
            assert "친구비-측정기-서비스-기준-명세.md" in read(path), (
                f"{path.name} 이 상위 문서를 가리키지 않는다"
            )

    def test_every_doc_has_a_revision_history(self):
        for path in DOCS.glob("*.md"):
            assert "개정 이력" in read(path), f"{path.name} 에 개정 이력이 없다"


@pytest.fixture(scope="module")
def error_rows() -> dict[str, tuple[int, bool]]:
    """데이터 계약 11장의 오류 코드 표를 읽는다."""
    parsed: dict[str, tuple[int, bool]] = {}
    for line in read(CONTRACT).splitlines():
        match = re.match(
            r"\|\s*`([A-Z_]+)`\s*\|\s*(\d{3})\s*\|\s*(가능|불가)\s*\|", line
        )
        if match:
            code, status, retry = match.groups()
            parsed[code] = (int(status), retry == "가능")
    return parsed


@pytest.fixture(scope="module")
def scoring_rows() -> dict[str, float]:
    """관계 점수 계산 규칙 3장의 상수 표를 읽는다."""
    parsed: dict[str, float] = {}
    for line in read(SCORING).splitlines():
        match = re.match(r"\|\s*`([A-Z_]+)`\s*\|\s*([\d.]+)", line)
        if match:
            name, value = match.groups()
            parsed[name] = float(value)
    return parsed


@pytest.fixture(scope="module")
def api_text() -> str:
    return read(API)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def report_limits() -> dict[str, int]:
    """리포트 글자 수 상한을 검증 규칙에서 읽는다."""
    fields = ReportData.model_fields
    found: dict[str, int] = {}
    for name in ("headline", "summary", "advice"):
        for meta in fields[name].metadata:
            if hasattr(meta, "max_length"):
                found[name] = meta.max_length
    return found


class TestErrorCodes:
    """데이터 계약 11장의 오류 코드 표와 코드가 일치하는지."""

    def test_document_lists_every_code(self, error_rows):
        in_code = {member.value for member in ErrorCode}

        assert in_code == set(error_rows), (
            f"문서에만: {set(error_rows) - in_code} / 코드에만: {in_code - set(error_rows)}"
        )

    def test_http_status_matches(self, error_rows):
        mismatched = {
            code: (documented, http_status_of(ErrorCode(code)))
            for code, (documented, _) in error_rows.items()
            if documented != http_status_of(ErrorCode(code))
        }

        assert not mismatched, f"HTTP 상태가 다르다 (문서, 코드): {mismatched}"

    def test_retryable_matches(self, error_rows):
        mismatched = {
            code: (documented, is_retryable(ErrorCode(code)))
            for code, (_, documented) in error_rows.items()
            if documented != is_retryable(ErrorCode(code))
        }

        assert not mismatched, f"재시도 가능 여부가 다르다 (문서, 코드): {mismatched}"


class TestScoringConstants:
    """관계 점수 계산 규칙 3장의 상수 표와 코드가 일치하는지."""

    def test_documented_constants_match_the_code(self, scoring_rows):
        assert scoring_rows, "상수 표를 읽지 못했다"

        mismatched = {}
        for name, documented in scoring_rows.items():
            actual = getattr(constants, name, None)
            if actual is None:
                mismatched[name] = ("코드에 없음", documented)
            elif float(actual) != documented:
                mismatched[name] = (documented, actual)

        assert not mismatched, f"상수가 다르다 (문서, 코드): {mismatched}"

    def test_fee_bounds_agree_across_modules(self):
        # 친구비 범위가 도메인 모델과 알고리즘 상수 두 곳에 있다
        assert FEE_MIN == constants.FEE_MIN
        assert FEE_MAX == constants.FEE_MAX

    def test_reply_ceiling_is_reachable(self):
        """6시간 넘는 간격은 버려지므로 상한이 그보다 크면 100점이 안 나온다."""
        assert constants.REPLY_CEIL_SECONDS <= constants.REPLY_MAX_SECONDS


class TestApiLimits:
    """API 명세 4장·9장의 제한값과 설정 기본값이 일치하는지."""

    def test_image_count(self, api_text, settings):
        assert f"1 ~ {settings.max_images}개" in api_text

    def test_image_size(self, api_text, settings):
        assert f"{settings.max_image_bytes // (1024 * 1024)} MB" in api_text
        assert f"{settings.max_total_bytes // (1024 * 1024)} MB" in api_text

    def test_minimum_resolution(self, api_text, settings):
        assert f"{settings.min_image_side}px" in api_text

    def test_rate_limits(self, api_text, settings):
        assert f"분당 {settings.rate_limit_per_minute}회" in api_text
        assert f"하루 {settings.daily_analysis_limit}회" in api_text
        assert f"{settings.concurrent_analysis_limit}건" in api_text
        assert f"분당 {settings.poll_rate_limit_per_minute}회" in api_text

    def test_timeouts(self, api_text, settings):
        assert f"{settings.total_timeout_seconds}초" in api_text
        assert f"{settings.ocr_timeout_seconds}초" in api_text
        assert f"{settings.llm_timeout_seconds}초" in api_text

    def test_ttl(self, api_text, settings):
        minutes = settings.ttl_seconds // 60
        assert f"**{minutes}분**" in api_text
        assert f"{minutes}분" in read(BASE)


class TestEnumValues:
    """상태값과 단계가 문서와 일치하는지."""

    def test_job_statuses_are_documented(self):
        text = read(CONTRACT)

        for status in JobStatus:
            assert f"`{status.value}`" in text, f"{status.value} 가 문서에 없다"

    def test_job_stages_are_documented_in_order(self):
        text = read(CONTRACT)
        expected = " → ".join(f"`{stage.value}`" for stage in JobStage)

        assert expected in text, "단계 순서가 문서와 다르다"

    def test_confidence_levels_are_documented(self):
        text = read(CONTRACT)

        for level in Confidence:
            assert f"`{level.value}`" in text


class TestReportLimits:
    """리포트 글자 수 상한이 문서와 검증에서 같은지."""

    def test_documented_limits_match_validation(self, report_limits):
        text = read(CONTRACT)

        assert len(report_limits) == 3, f"상한을 읽지 못했다: {report_limits}"
        for name, value in report_limits.items():
            assert f"{value}자" in text, f"{name} 상한 {value}자가 문서에 없다"

    def test_section_count_is_documented(self):
        assert "2~3개" in read(CONTRACT)


class TestOcrRequirements:
    """OCR 명세가 좌표 필수를 못 박고 있는지."""

    def test_coordinates_are_stated_as_mandatory(self):
        text = read(OCR)

        assert "필수" in text
        assert "bounding box" in text or "좌표" in text

    def test_base_spec_repeats_the_requirement(self):
        # 이 요구가 사라지면 서비스 지표 절반이 계산 불가능해진다
        assert "bounding box 좌표를 반환해야 한다" in read(BASE)


class TestRootReadme:
    """저장소 진입점이 실제 상태를 가리키는지."""

    def test_links_every_spec_document(self):
        text = read(ROOT_README)

        missing = [
            path.name for path in DOCS.glob("*.md") if path.name not in text
        ]

        assert not missing, f"루트 README가 가리키지 않는 문서: {missing}"

    def test_linked_paths_resolve(self):
        text = read(ROOT_README)
        links = re.findall(r"\]\((mdfiles/[^)#]+)\)", text)

        assert links, "명세 문서 링크를 찾지 못했다"
        broken = [link for link in links if not (ROOT / link).exists()]

        assert not broken, f"깨진 링크: {broken}"

    def test_replacement_settings_are_named_correctly(self):
        """README가 알려주는 환경변수가 실제로 존재해야 한다."""
        text = read(ROOT_README)
        prefix = Settings.model_config["env_prefix"]
        mentioned = set(re.findall(rf"{prefix}([A-Z_]+)", text))

        known = {name.upper() for name in Settings.model_fields}
        unknown = mentioned - known

        assert not unknown, f"존재하지 않는 설정을 안내하고 있다: {unknown}"


class TestPrivacyPrinciples:
    """개인정보 원칙이 문서에서 사라지지 않았는지."""

    def test_no_permanent_storage(self):
        assert "영구 저장 금지" in read(BASE)

    def test_conversation_text_is_not_returned(self):
        assert "대화 원문은 클라이언트로 되돌려 보내지 않는다" in read(BASE)

    def test_result_excludes_raw_conversation(self):
        assert "응답에 포함하지 않는다" in read(CONTRACT)

    def test_free_tier_warning_survives(self):
        report = DOCS / "AI-모델-선정-보고서.md"
        text = read(report)

        # 무료 티어를 쓰면 안 되는 이유가 사라지면 나중에 누군가 다시 붙인다
        assert "학습" in text and "탈락" in text


FRONTEND = ROOT / "frontend" / "src"


class TestFrontendAgreesWithBackend:
    """프론트가 들고 있는 값이 백엔드와 어긋나지 않는지.

    프론트는 헛된 왕복을 줄이려고 업로드 제한을 미리 검사한다. 그런데 그 값이
    백엔드와 달라지면 두 가지 중 하나가 일어난다.

    - 프론트가 더 느슨하면: 사용자가 서버에 가서야 거절당한다
    - 프론트가 더 빡세면: 서버가 받아줄 파일을 프론트가 막는다

    둘 다 조용히 일어나므로 여기서 잡는다.
    """

    def test_upload_limits_match(self):
        text = (FRONTEND / "components" / "Uploader.tsx").read_text(encoding="utf-8")
        settings = Settings()

        assert f"MAX_IMAGES = {settings.max_images}" in text
        assert (
            f"MAX_IMAGE_BYTES = {settings.max_image_bytes // (1024 * 1024)} * 1024 * 1024"
            in text
        )
        assert (
            f"MAX_TOTAL_BYTES = {settings.max_total_bytes // (1024 * 1024)} * 1024 * 1024"
            in text
        )

    def test_allowed_mime_types_match(self):
        text = (FRONTEND / "components" / "Uploader.tsx").read_text(encoding="utf-8")

        for mime in Settings().allowed_mime_types:
            assert f"'{mime}'" in text, f"{mime} 이 프론트 허용 목록에 없다"

    def test_job_statuses_match(self):
        text = (FRONTEND / "api" / "types.ts").read_text(encoding="utf-8")

        for status in JobStatus:
            assert f"'{status.value}'" in text, f"{status.value} 가 프론트 타입에 없다"

    def test_job_stages_match(self):
        text = (FRONTEND / "api" / "types.ts").read_text(encoding="utf-8")

        for stage in JobStage:
            assert f"'{stage.value}'" in text, f"{stage.value} 가 프론트 타입에 없다"
            # 각 단계마다 사용자에게 보여줄 문구가 있어야 한다
            assert f"{stage.value}:" in text, f"{stage.value} 안내 문구가 없다"

    def test_confidence_levels_match(self):
        text = (FRONTEND / "api" / "types.ts").read_text(encoding="utf-8")

        for level in Confidence:
            assert f"'{level.value}'" in text

    def test_failure_screen_covers_user_facing_errors(self):
        """사용자가 실제로 마주칠 오류에는 안내가 있어야 한다.

        모르는 코드에도 기본 안내가 나가지만, 흔한 실패에 "알 수 없는 오류"를
        보여주면 사용자는 무엇을 고쳐야 할지 알 수 없다.
        """
        text = (FRONTEND / "components" / "Failure.tsx").read_text(encoding="utf-8")

        # 사용자의 행동으로 이어질 수 있는 오류들
        actionable = {
            ErrorCode.TOO_FEW_MESSAGES,
            ErrorCode.NO_CONVERSATION_FOUND,
            ErrorCode.GROUP_CHAT_DETECTED,
            ErrorCode.SPEAKER_DETECTION_FAILED,
            ErrorCode.IMAGE_TOO_MANY,
            ErrorCode.IMAGE_TOO_LARGE,
            ErrorCode.IMAGE_FORMAT_UNSUPPORTED,
            ErrorCode.RATE_LIMITED,
            ErrorCode.DAILY_LIMIT_EXCEEDED,
            ErrorCode.CONCURRENCY_LIMIT,
            ErrorCode.JOB_EXPIRED,
            ErrorCode.ANALYSIS_TIMEOUT,
        }

        missing = [code.value for code in actionable if code.value not in text]

        assert not missing, f"실패 화면에 안내가 없는 오류: {missing}"

    def test_api_base_path_matches(self):
        text = (FRONTEND / "api" / "client.ts").read_text(encoding="utf-8")

        assert "'/v1'" in text, "프론트가 다른 Base URL을 쓰고 있다"

    def test_beacon_deletion_path_exists_on_both_sides(self):
        """sendBeacon은 POST만 보낼 수 있어 서버가 별도 경로를 연다."""
        front = (FRONTEND / "api" / "client.ts").read_text(encoding="utf-8")
        back = (ROOT / "backend" / "app" / "api" / "routes.py").read_text(encoding="utf-8")

        assert "/deletion" in front
        assert "/deletion" in back


class TestPromptSpec:
    """프롬프트 명세와 코드.

    출력 토큰 상한을 800에서 1500으로 올린 일이 있었다. 추론 모델이 reasoning
    에 예산을 다 쓰고 본문을 못 내놓아 400이 났기 때문이다. 그때 문서와 코드를
    손으로 함께 고쳤는데, 다음에 한쪽만 바뀌면 걸리는 곳이 없었다.
    """

    def test_분석_출력_토큰_상한이_문서와_같다(self):
        from app.ai.agent.analysis import MAX_OUTPUT_TOKENS

        text = read(PROMPT)
        section = text.split("### 4.5")[1].split("###")[0]
        numbers = {int(n) for n in re.findall(r"\*\*(\d{3,5})\.?\*\*", section)}

        assert MAX_OUTPUT_TOKENS in numbers, (
            f"코드는 {MAX_OUTPUT_TOKENS}인데 문서 4.5에는 {numbers or '숫자가 없다'}"
        )

    def test_리포트_출력_토큰_상한이_문서와_같다(self):
        from app.ai.agent.report import MAX_OUTPUT_TOKENS

        section = read(PROMPT).split("### 5.7")[1].split("##")[0]

        assert str(MAX_OUTPUT_TOKENS) in section, (
            f"코드는 {MAX_OUTPUT_TOKENS}인데 문서 5.7에 그 값이 없다"
        )

    def test_추론_설정_이름이_문서에_적혀_있다(self):
        # 설정으로 교체한다는 원칙이 지켜지려면 이름이 문서에 있어야 한다
        assert "llm_reasoning_effort" in Settings.model_fields
        assert "FC_LLM_REASONING_EFFORT" in read(PROMPT)

    def test_리포트_글자수_상한이_모델과_같다(self):
        section = read(PROMPT).split("### 5.4")[1].split("###")[0]

        for name, field in ReportData.model_fields.items():
            limit = next(
                (m.max_length for m in field.metadata if hasattr(m, "max_length")), None
            )
            if limit is None or name == "sections":
                continue
            assert f"{limit}자" in section, (
                f"{name} 상한 {limit}자가 문서 5.4에 없다"
            )


class TestEnvExample:
    """`.env.example` 이 설정을 모두 담고 있는지.

    설정을 추가하고 예시 파일을 잊는 일이 실제로 있었다.
    `FC_LLM_REASONING_EFFORT` 를 넣을 때 그랬다. 그 값이 비면 추론 모델에서
    400이 나는데, 예시에 없으면 배포하는 사람이 알 길이 없다.
    """

    def test_모든_설정이_예시에_있다(self):
        example = read(ROOT / "backend" / ".env.example")

        missing = [
            f"FC_{name.upper()}"
            for name in Settings.model_fields
            if f"FC_{name.upper()}=" not in example
        ]

        assert not missing, f".env.example 에 없는 설정: {missing}"

    def test_예시에_실제_키가_들어_있지_않다(self):
        # 예시 파일은 커밋된다. 실수로 키를 적으면 그대로 공개된다.
        # 주석에는 "gsk_ 로 시작한다" 같은 설명이 있으므로 값만 본다
        example = read(ROOT / "backend" / ".env.example")

        for line in example.splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            value = line.split("=", 1)[1].strip()
            for prefix in ("gsk_", "sk-", "AIza"):
                assert not value.startswith(prefix), (
                    f"예시에 실제 키로 보이는 값이 있다: {line.split('=')[0]}"
                )

    def test_채택한_모델이_예시와_문서에_같이_적혀_있다(self):
        example = read(ROOT / "backend" / ".env.example")
        report = read(DOCS / "AI-모델-선정-보고서.md")

        model = next(
            line.split("=", 1)[1].strip()
            for line in example.splitlines()
            if line.startswith("FC_LLM_MODEL=")
        )

        assert model in report, f"예시의 모델 {model} 이 선정 보고서에 없다"
