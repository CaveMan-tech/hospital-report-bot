"""Abuse controls that keep the 'no identity collected' promise.

The IP is used in memory for rate limiting and to derive a dedupe key with a salt
that rotates daily and is never persisted. After rotation the key cannot be linked
back to anyone.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, date, datetime


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


class DailyDedupe:
    def __init__(self) -> None:
        self._day: date | None = None
        self._salt = b""

    def key(self, ip: str) -> str:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._salt = today, secrets.token_bytes(32)
        return hmac.new(self._salt, ip.encode(), hashlib.sha256).hexdigest()[:32]
