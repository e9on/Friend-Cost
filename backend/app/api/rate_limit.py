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
from typing import Callable, Deque

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


class RateLimiter:
    """생성·폴링·동시성 제한을 한데 묶는다."""

    def __init__(
        self,
        per_minute: int,
        per_day: int,
        concurrent: int,
        poll_per_minute: int,
        clock: Clock = time.time,
    ) -> None:
        self.create_minute = SlidingWindowLimiter(per_minute, MINUTE, clock)
        self.create_day = SlidingWindowLimiter(per_day, DAY, clock)
        self.poll_minute = SlidingWindowLimiter(poll_per_minute, MINUTE, clock)
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
        if not self.concurrency.acquire(ip):
            raise AppError(ErrorCode.CONCURRENCY_LIMIT)

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
