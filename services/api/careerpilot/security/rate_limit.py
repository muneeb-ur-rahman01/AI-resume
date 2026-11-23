"""Fixed-window rate limiting backed by Redis, with an in-process fallback.

The in-memory fallback is per-process and is meant for development/tests or as a degraded mode when
Redis is unavailable; production deployments should configure REDIS_URL.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from careerpilot.config import get_settings
from careerpilot.errors import RateLimited

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    name: str
    max_requests: int
    window_seconds: int


# Named limits used across the API.
LOGIN_IP = Limit("login_ip", 30, 300)
LOGIN_ACCOUNT = Limit("login_account", 10, 900)
REGISTER_IP = Limit("register_ip", 10, 3600)
PASSWORD_RESET = Limit("password_reset", 5, 3600)
VERIFY_EMAIL = Limit("verify_email", 20, 3600)
RESEND_VERIFICATION = Limit("resend_verification", 5, 3600)
UPLOAD = Limit("upload", 20, 3600)
AI_GENERATION = Limit("ai_generation", 30, 3600)
SENSITIVE = Limit("sensitive", 10, 3600)


class _MemoryBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, float]] = {}

    def incr(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            count, expires = self._counts.get(key, (0, now + window))
            if now >= expires:
                count, expires = 0, now + window
            count += 1
            self._counts[key] = (count, expires)
            return count

    def get(self, key: str) -> int:
        with self._lock:
            count, expires = self._counts.get(key, (0, 0.0))
            return count if time.time() < expires else 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._counts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._counts.clear()


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryBackend()
        self._redis = None
        url = get_settings().redis_url
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
            except Exception:  # pragma: no cover - import/config failure
                logger.warning("rate_limiter_redis_unavailable_using_memory")

    def _incr(self, key: str, window: int) -> int:
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, window, nx=True)
                count, _ = pipe.execute()
                return int(count)
            except Exception:
                logger.warning("rate_limiter_redis_error_falling_back")
        return self._memory.incr(key, window)

    def hit(self, limit: Limit, subject: str) -> None:
        key = f"rl:{limit.name}:{subject}"
        if self._incr(key, limit.window_seconds) > limit.max_requests:
            raise RateLimited(
                "Too many requests. Please try again later.", details={"retry_after": limit.window_seconds}
            )

    def increment(self, limit: Limit, subject: str) -> int:
        """Count an event without enforcing the limit (e.g. failed logins checked separately)."""
        return self._incr(f"rl:{limit.name}:{subject}", limit.window_seconds)

    def count(self, limit: Limit, subject: str) -> int:
        key = f"rl:{limit.name}:{subject}"
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                return int(value) if value else 0
            except Exception:
                logger.warning("rate_limiter_redis_error_falling_back")
        return self._memory.get(key)

    def reset(self, limit: Limit, subject: str) -> None:
        key = f"rl:{limit.name}:{subject}"
        if self._redis is not None:
            try:
                self._redis.delete(key)
                return
            except Exception:
                logger.warning("rate_limiter_redis_error_falling_back")
        self._memory.reset(key)

    def clear_memory(self) -> None:
        self._memory.clear()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
