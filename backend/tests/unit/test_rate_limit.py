"""요청 제한.

API 명세 9장. IP는 제한 목적으로만 쓰고 창이 지나면 폐기한다.
"""

import pytest

from app.api.rate_limit import ConcurrencyGuard, RateLimiter, SlidingWindowLimiter
from app.common.errors import AppError, ErrorCode


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


class TestSlidingWindow:
    def test_allows_up_to_the_limit(self, clock):
        limiter = SlidingWindowLimiter(3, 60, clock)

        assert [limiter.consume("ip") for _ in range(4)] == [True, True, True, False]

    def test_window_slides_forward(self, clock):
        limiter = SlidingWindowLimiter(2, 60, clock)
        limiter.consume("ip")
        limiter.consume("ip")

        clock.advance(61)

        assert limiter.consume("ip") is True

    def test_partial_expiry_frees_one_slot(self, clock):
        limiter = SlidingWindowLimiter(2, 60, clock)
        limiter.consume("ip")
        clock.advance(30)
        limiter.consume("ip")

        clock.advance(31)  # 첫 번째만 창을 벗어난다

        assert limiter.consume("ip") is True
        assert limiter.consume("ip") is False

    def test_keys_are_independent(self, clock):
        limiter = SlidingWindowLimiter(1, 60, clock)

        assert limiter.consume("a") is True
        assert limiter.consume("b") is True
        assert limiter.consume("a") is False

    def test_check_does_not_consume(self, clock):
        limiter = SlidingWindowLimiter(2, 60, clock)

        assert limiter.check("ip") == 2
        assert limiter.check("ip") == 2

        limiter.consume("ip")
        assert limiter.check("ip") == 1

    def test_retry_after_counts_down_to_the_oldest_hit(self, clock):
        limiter = SlidingWindowLimiter(1, 60, clock)
        limiter.consume("ip")

        clock.advance(20)

        assert 39 <= limiter.retry_after("ip") <= 42

    def test_retry_after_without_history_is_one_second(self, clock):
        assert SlidingWindowLimiter(1, 60, clock).retry_after("처음 보는 ip") == 1


class TestConcurrencyGuard:
    def test_allows_up_to_the_limit(self):
        guard = ConcurrencyGuard(2)

        assert [guard.acquire("ip") for _ in range(3)] == [True, True, False]

    def test_release_frees_a_slot(self):
        guard = ConcurrencyGuard(1)
        guard.acquire("ip")

        guard.release("ip")

        assert guard.acquire("ip") is True

    def test_release_without_acquire_is_harmless(self):
        guard = ConcurrencyGuard(1)

        guard.release("ip")

        assert guard.acquire("ip") is True

    def test_keys_are_independent(self):
        guard = ConcurrencyGuard(1)

        assert guard.acquire("a") is True
        assert guard.acquire("b") is True


class TestRateLimiter:
    def test_minute_limit_is_checked_before_the_daily_one(self, clock):
        """일일 한도를 소진시키는 폭주를 그 앞에서 막는 편이 덜 억울하다."""
        limiter = RateLimiter(
            per_minute=1, per_day=100, concurrent=10, poll_per_minute=100, clock=clock
        )
        limiter.check_create("ip")

        with pytest.raises(AppError) as caught:
            limiter.check_create("ip")

        assert caught.value.code is ErrorCode.RATE_LIMITED

    def test_daily_limit_reports_its_own_code(self, clock):
        limiter = RateLimiter(
            per_minute=100, per_day=1, concurrent=10, poll_per_minute=100, clock=clock
        )
        limiter.check_create("ip")

        with pytest.raises(AppError) as caught:
            limiter.check_create("ip")

        assert caught.value.code is ErrorCode.DAILY_LIMIT_EXCEEDED

    def test_concurrency_limit_reports_its_own_code(self, clock):
        limiter = RateLimiter(
            per_minute=100, per_day=100, concurrent=1, poll_per_minute=100, clock=clock
        )
        limiter.check_create("ip")

        with pytest.raises(AppError) as caught:
            limiter.check_create("ip")

        assert caught.value.code is ErrorCode.CONCURRENCY_LIMIT

    def test_releasing_lets_the_next_analysis_through(self, clock):
        limiter = RateLimiter(
            per_minute=100, per_day=100, concurrent=1, poll_per_minute=100, clock=clock
        )
        limiter.check_create("ip")

        limiter.release("ip")

        limiter.check_create("ip")

    def test_polling_has_a_separate_budget(self, clock):
        limiter = RateLimiter(
            per_minute=1, per_day=1, concurrent=1, poll_per_minute=5, clock=clock
        )
        limiter.check_create("ip")

        for _ in range(5):
            limiter.check_poll("ip")

        with pytest.raises(AppError) as caught:
            limiter.check_poll("ip")
        assert caught.value.code is ErrorCode.RATE_LIMITED

    @pytest.mark.parametrize(
        "code, expected",
        [
            (ErrorCode.CONCURRENCY_LIMIT, 5),
            (ErrorCode.RATE_LIMITED, 1),
        ],
    )
    def test_retry_after_by_code(self, clock, code, expected):
        limiter = RateLimiter(
            per_minute=5, per_day=5, concurrent=5, poll_per_minute=5, clock=clock
        )

        assert limiter.retry_after_for(code, "ip") == expected

    def test_daily_retry_after_is_measured_in_the_day_window(self, clock):
        limiter = RateLimiter(
            per_minute=5, per_day=1, concurrent=5, poll_per_minute=5, clock=clock
        )
        limiter.check_create("ip")

        wait = limiter.retry_after_for(ErrorCode.DAILY_LIMIT_EXCEEDED, "ip")

        assert wait > 60 * 60  # 분 단위가 아니라 시간 단위여야 한다


class TestServiceDailyLimit:
    """IP 와 무관한 하루 총량.

    다른 제한은 전부 IP 기준이다. IP 하나가 하루 10건을 넘지 못하게 막지만,
    서로 다른 IP 1,000개가 오면 하루 10,000건이 나간다. 전체를 막는 것이
    없었다.

    지금은 LLM 무료 티어라 넘으면 호출이 실패할 뿐이지만, 유료로 전환하는
    순간 이 구멍이 그대로 청구서가 된다.

    `운영-보안-법적고지-명세.md` 6.2.1
    """

    def limiter(self, clock, service_per_day=2):
        return RateLimiter(
            per_minute=100,
            per_day=100,
            concurrent=100,
            poll_per_minute=100,
            service_per_day=service_per_day,
            clock=clock,
        )

    def test_서로_다른_IP_여도_전체_한도에_걸린다(self, clock):
        limiter = self.limiter(clock)

        limiter.check_create("1.1.1.1")
        limiter.check_create("2.2.2.2")

        with pytest.raises(AppError) as caught:
            limiter.check_create("3.3.3.3")

        assert caught.value.code is ErrorCode.SERVICE_DAILY_LIMIT

    def test_개인_할당량과_다른_코드를_쓴다(self, clock):
        """전역 상한에 걸린 사용자는 자기 몫을 쓴 적이 없다.

        같은 코드를 쓰면 "네가 다 썼다"고 사실과 다른 말을 하게 된다.
        """
        limiter = self.limiter(clock)
        limiter.check_create("1.1.1.1")
        limiter.check_create("2.2.2.2")

        with pytest.raises(AppError) as caught:
            limiter.check_create("3.3.3.3")

        assert caught.value.code is not ErrorCode.DAILY_LIMIT_EXCEEDED

    def test_하루가_지나면_풀린다(self, clock):
        limiter = self.limiter(clock)
        limiter.check_create("1.1.1.1")
        limiter.check_create("2.2.2.2")

        clock.advance(86_401)

        limiter.check_create("3.3.3.3")

    def test_개인_한도가_먼저_걸리면_전체_몫을_쓰지_않는다(self, clock):
        """막힌 요청은 LLM 을 부르지 않는다. 총량을 축내서는 안 된다."""
        limiter = RateLimiter(
            per_minute=1,
            per_day=100,
            concurrent=100,
            poll_per_minute=100,
            service_per_day=10,
            clock=clock,
        )
        limiter.check_create("1.1.1.1")

        with pytest.raises(AppError):
            limiter.check_create("1.1.1.1")  # 분당 제한에 걸린다

        assert limiter.service_remaining() == 9
