"""작업 상태 전이.

데이터 계약 10장의 상태표를 코드가 실제로 강제하는지 확인한다.
정의되지 않은 전이는 조용히 넘어가지 않고 터져야 한다. 그래야 상태가
뒤엉킨 채로 사용자에게 결과가 나가는 일을 막을 수 있다.
"""

import pytest

from app.common.errors import AppError, ErrorCode
from app.domain.model.job import AnalysisJob, IllegalTransition
from app.domain.model.report import DISCLAIMER, ReportData, ReportSection
from app.domain.model.result import AnalysisResult, ResultMeta
from app.domain.model.score import RelationshipScoreData, ReplySeconds
from app.domain.value_object.enums import JobStage, JobStatus


def job() -> AnalysisJob:
    return AnalysisJob(job_id="test-job", created_at=1_000, expires_at=2_200)


def result() -> AnalysisResult:
    return AnalysisResult(
        job_id="test-job",
        scores=RelationshipScoreData(
            friend_fee=45_000,
            intimacy=64,
            breakup_risk=38,
            first_contact_ratio=0.63,
            avg_reply_seconds=ReplySeconds(me=420, peer=1860),
            contact_balance=74,
        ),
        report=ReportData(
            headline="한 줄 요약",
            summary="요약",
            sections=(
                ReportSection(title="제목1", body="본문1"),
                ReportSection(title="제목2", body="본문2"),
            ),
            advice="제안",
            disclaimer=DISCLAIMER,
        ),
        meta=ResultMeta(message_count=184, image_count=5, sampled=False, span_seconds=1000),
        expires_at=2_200,
    )


class TestHappyPath:
    def test_pending_to_processing_on_first_advance(self):
        target = job()

        target.advance(JobStage.OCR)

        assert target.status is JobStatus.PROCESSING
        assert target.stage is JobStage.OCR

    def test_walks_through_every_stage(self):
        target = job()

        for stage in JobStage:
            target.advance(stage)

        assert target.stage is JobStage.REPORTING
        assert target.status is JobStatus.PROCESSING

    def test_success_clears_the_stage(self):
        target = job()
        target.advance(JobStage.OCR)

        target.succeed(result())

        assert target.status is JobStatus.DONE
        assert target.stage is None
        assert target.result is not None


class TestFailure:
    def test_failure_records_the_error(self):
        target = job()
        target.advance(JobStage.OCR)

        target.fail(AppError(ErrorCode.OCR_FAILED))

        assert target.status is JobStatus.FAILED
        assert target.stage is None
        assert target.error.code is ErrorCode.OCR_FAILED

    def test_can_fail_straight_from_pending(self):
        target = job()

        target.fail(AppError(ErrorCode.IMAGE_TOO_LARGE))

        assert target.status is JobStatus.FAILED


class TestIllegalTransitions:
    def test_cannot_succeed_twice(self):
        target = job()
        target.advance(JobStage.OCR)
        target.succeed(result())

        with pytest.raises(IllegalTransition):
            target.succeed(result())

    def test_cannot_advance_after_completion(self):
        target = job()
        target.advance(JobStage.OCR)
        target.succeed(result())

        with pytest.raises(IllegalTransition):
            target.advance(JobStage.REPORTING)

    def test_cannot_advance_after_failure(self):
        target = job()
        target.fail(AppError(ErrorCode.OCR_FAILED))

        with pytest.raises(IllegalTransition):
            target.advance(JobStage.PARSING)

    def test_cannot_succeed_after_failing(self):
        target = job()
        target.fail(AppError(ErrorCode.OCR_FAILED))

        with pytest.raises(IllegalTransition):
            target.succeed(result())

    def test_expired_is_a_dead_end(self):
        target = job()
        target.expire()

        with pytest.raises(IllegalTransition):
            target.expire()
        with pytest.raises(IllegalTransition):
            target.advance(JobStage.OCR)


class TestExpiry:
    def test_expiring_discards_the_payload(self):
        target = job()
        target.advance(JobStage.OCR)
        target.succeed(result())

        target.expire()

        assert target.result is None
        assert target.error is None

    def test_is_expired_at_compares_against_the_deadline(self):
        target = job()

        assert target.is_expired_at(2_199) is False
        assert target.is_expired_at(2_200) is True


class TestRaiseIfUnavailable:
    def test_done_job_passes(self):
        target = job()
        target.advance(JobStage.OCR)
        target.succeed(result())

        target.raise_if_unavailable()

    def test_pending_job_is_not_ready(self):
        with pytest.raises(AppError) as caught:
            job().raise_if_unavailable()
        assert caught.value.code is ErrorCode.JOB_NOT_READY

    def test_failed_job_reraises_the_original_error(self):
        target = job()
        target.fail(AppError(ErrorCode.GROUP_CHAT_DETECTED))

        with pytest.raises(AppError) as caught:
            target.raise_if_unavailable()
        assert caught.value.code is ErrorCode.GROUP_CHAT_DETECTED

    def test_failed_job_without_an_error_falls_back_to_internal(self):
        target = job()
        target.fail(AppError(ErrorCode.OCR_FAILED))
        target.error = None  # 있어서는 안 될 상태지만 방어한다

        with pytest.raises(AppError) as caught:
            target.raise_if_unavailable()
        assert caught.value.code is ErrorCode.INTERNAL_ERROR

    def test_expired_job_reports_expiry(self):
        target = job()
        target.expire()

        with pytest.raises(AppError) as caught:
            target.raise_if_unavailable()
        assert caught.value.code is ErrorCode.JOB_EXPIRED


class TestStatusHelpers:
    @pytest.mark.parametrize(
        "status, terminal",
        [
            (JobStatus.PENDING, False),
            (JobStatus.PROCESSING, False),
            (JobStatus.DONE, True),
            (JobStatus.FAILED, True),
            (JobStatus.EXPIRED, True),
        ],
    )
    def test_terminal_flag(self, status, terminal):
        assert status.is_terminal is terminal
