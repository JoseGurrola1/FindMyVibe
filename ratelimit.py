"""
In-memory rate limiting for the API.

Every game turn spends SerpApi and Gemini quota, and the site is public,
so we cap how often each visitor (by IP) can call the API, plus an overall
cap across all visitors.

The per-visitor limits are generous on purpose: people on shared Wi-Fi
(e.g. judges at a venue) all appear as one IP. The overall cap is what
protects the quota.

Limits can be changed without code edits via environment variables
(e.g. in .env):
    RATE_LIMIT_PER_MINUTE         default 100  (per visitor)
    RATE_LIMIT_PER_HOUR           default 1000 (per visitor)
    RATE_LIMIT_GLOBAL_PER_HOUR    default 1000 (all visitors combined)
    RATE_LIMIT_ENABLED            default true (set to false to turn off)

State lives in this process's memory, which is fine for our single
uvicorn process; it resets when the API restarts.
"""

import math
import os
import threading
import time
from collections import deque


class RateLimiter:
    """
    Sliding-window limiter. `rules` is a list of (max_requests, window_seconds);
    a key is allowed only if it is under every rule.
    """

    def __init__(self, rules, clock=time.monotonic):
        self.rules = [(int(limit), float(window)) for limit, window in rules]
        self.longest = max(window for _, window in self.rules)
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()
        self._last_cleanup = clock()

    def hit(self, key):
        """
        Record a request for `key` if it's allowed.
        Returns None when allowed, or the number of seconds to wait.
        """
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            hits = self._hits.setdefault(key, deque())

            # Forget requests older than the longest window.
            while hits and hits[0] <= now - self.longest:
                hits.popleft()

            wait = 0.0
            for limit, window in self.rules:
                in_window = [t for t in hits if t > now - window]
                if len(in_window) >= limit:
                    # Free again once the oldest counted request ages out.
                    oldest = in_window[len(in_window) - limit]
                    wait = max(wait, oldest + window - now)

            if wait > 0:
                return max(1, math.ceil(wait))

            hits.append(now)
            return None

    def reset(self):
        with self._lock:
            self._hits.clear()

    def _cleanup(self, now):
        # Drop visitors with no recent requests so memory doesn't grow forever.
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.longest]
        for key in stale:
            del self._hits[key]


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def limiters_from_env():
    """Build the per-visitor and global limiters from env settings."""
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
    per_visitor = RateLimiter([
        (_env_int("RATE_LIMIT_PER_MINUTE", 100), 60),
        (_env_int("RATE_LIMIT_PER_HOUR", 1000), 3600),
    ])
    overall = RateLimiter([
        (_env_int("RATE_LIMIT_GLOBAL_PER_HOUR", 1000), 3600),
    ])
    return enabled, per_visitor, overall
