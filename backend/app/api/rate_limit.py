"""IP 기준 요청 제한.

API 명세 9장, 기준 명세 9장.

IP는 제한 목적으로만 쓰고 제한 창이 지나면 폐기한다. 분석 데이터와 연결해
저장하지 않는다. 그래서 여기에는 IP와 타임스탬프 목록만 남고, 어떤 분석을
했는지는 기록하지 않는다.

메모리 기반이라 단일 인스턴스 전용이다. 저장소와 같은 제약을 갖는다.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Final, Callable, Deque

from app.common.errors import AppError, ErrorCode

Clock = Callable[[], float]

MINUTE = 60
DAY = 24 * 60 * 60


class SlidingWindowLimiter:
    """창 안의 요청 수를 센다."""

    def __init__(self, limit: int, window_seconds: int, clock: Clock = time.time) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> int:
        """소비하지 않고 남은 횟수만 본다."""
        with self._lock:
            return max(0, self._limit - len(self._prune(key, self._clock())))

    def consume(self, key: str) -> bool:
        """한 번 쓴다. 한도를 넘었으면 `False`."""
        now = self._clock()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 1
            return max(1, int(hits[0] + self._window - self._clock()) + 1)

    def prune(self) -> int:
        """창이 지난 키를 통째로 지운다.

        `_prune` 는 창 밖의 기록만 버리고 키는 남긴다. 서로 다른 IP가 계속
        들어오면 빈 항목이 무한히 쌓이므로 주기적으로 걷어내야 한다.
        기준 명세 9장의 "제한 창이 지나면 폐기한다"가 이 뜻이다.
        """
        now = self._clock()
        with self._lock:
            stale = [key for key in self._hits if not self._prune(key, now)]
            for key in stale:
                del self._hits[key]
        return len(stale)

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)


class ConcurrencyGuard:
    """동시에 진행 중인 분석 수를 센다."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def acquire(self, key: str) -> bool:
        with self._lock:
            if self._active[key] >= self._limit:
                return False
            self._active[key] += 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            if self._active[key] > 0:
                self._active[key] -= 1
            if self._active[key] == 0:
                self._active.pop(key, None)


# 전역 창이 쓰는 고정 키. IP 별로 나누지 않겠다는 뜻을 이름으로 남긴다
_SERVICE: Final = "__service__"


class RateLimiter:
    """생성·폴링·동시성 제한을 한데 묶는다."""

    def __init__(
        self,
        per_minute: int,
        per_day: int,
        concurrent: int,
        poll_per_minute: int,
        service_per_day: int = 400,
        clock: Clock = time.time,
    ) -> None:
        self.create_minute = SlidingWindowLimiter(per_minute, MINUTE, clock)
        self.create_day = SlidingWindowLimiter(per_day, DAY, clock)
        self.poll_minute = SlidingWindowLimiter(poll_per_minute, MINUTE, clock)
        # IP 를 키로 쓰지 않는다. 하나의 창에 전부 담아 총량을 센다
        self.service_day = SlidingWindowLimiter(service_per_day, DAY, clock)
        self.concurrency = ConcurrencyGuard(concurrent)

    def check_create(self, ip: str) -> None:
        """생성 요청을 허용할지 판단한다. 막히면 해당 오류를 던진다.

        분당 제한을 먼저 보는 이유는, 일일 한도를 소진시키는 폭주를 그 앞에서
        막는 편이 사용자에게 덜 억울하기 때문이다.
        """
        if not self.create_minute.consume(ip):
            raise AppError(ErrorCode.RATE_LIMITED)
        if not self.create_day.consume(ip):
            raise AppError(ErrorCode.DAILY_LIMIT_EXCEEDED)
        # 개인 한도를 통과한 요청만 총량을 축낸다. 막힌 요청은 LLM 을
        # 부르지 않으므로 전체 몫에서 빼면 안 된다
        if not self.service_day.consume(_SERVICE):
            raise AppError(ErrorCode.SERVICE_DAILY_LIMIT)
        if not self.concurrency.acquire(ip):
            raise AppError(ErrorCode.CONCURRENCY_LIMIT)

    def service_remaining(self) -> int:
        """오늘 남은 전체 분량. 전역 키를 밖으로 드러내지 않으려고 감싼다."""
        return self.service_day.check(_SERVICE)

    def release(self, ip: str) -> None:
        self.concurrency.release(ip)

    def check_poll(self, ip: str) -> None:
        if not self.poll_minute.consume(ip):
            raise AppError(ErrorCode.RATE_LIMITED)

    def retry_after_for(self, code: ErrorCode, ip: str) -> int:
        if code is ErrorCode.DAILY_LIMIT_EXCEEDED:
            return self.create_day.retry_after(ip)
        if code is ErrorCode.CONCURRENCY_LIMIT:
            return 5
        return self.create_minute.retry_after(ip)

    def prune(self) -> int:
        """만료된 IP 기록을 모두 걷어낸다."""
        return (
            self.create_minute.prune()
            + self.create_day.prune()
            + self.poll_minute.prune()
            + self.service_day.prune()
        )

    def tracked_keys(self) -> int:
        return (
            self.create_minute.tracked_keys()
            + self.create_day.tracked_keys()
            + self.poll_minute.tracked_keys()
            + self.service_day.tracked_keys()
        )
