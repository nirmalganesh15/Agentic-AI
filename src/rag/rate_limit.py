"""In-memory rate limiting for a single-instance deployment.

Two limits protect the LLM budget of a public demo:
- per client IP: a sliding one-minute window
- global: a daily cap across all clients

For several instances, move this state to Redis (same logic, shared store).
"""
import os
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import HTTPException, Request, status

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day = date.today()
        self._day_count = 0

    def check(self, client: str) -> None:
        now = time.monotonic()
        today = date.today()
        if today != self._day:
            self._day, self._day_count = today, 0
            self._hits.clear()

        if self._day_count >= self.per_day:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily demo limit reached. Please try again tomorrow.")

        hits = self._hits[client]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.per_minute:
            retry_after = int(WINDOW_SECONDS - (now - hits[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please wait a moment.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        self._day_count += 1


agent_limiter = RateLimiter(
    per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "8")),
    per_day=int(os.getenv("RATE_LIMIT_PER_DAY", "500")),
)


def limit_agent_requests(request: Request) -> None:
    # Behind Render's proxy, uvicorn's proxy-headers support puts the real client IP here.
    agent_limiter.check(request.client.host if request.client else "unknown")
