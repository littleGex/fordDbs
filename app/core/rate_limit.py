"""
Small in-memory attempt limiter for the open routes (login and
registration). State lives in this process: it is lost on restart, and
it assumes the API runs as a single process, which it does (see the
Dockerfile). Move it to the database if that ever changes.
"""
import math
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request


class AttemptLimiter:
    """Allows `limit` recorded attempts per key within a sliding window."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._attempts = defaultdict(list)
        self._lock = Lock()

    def _recent(self, key, now):
        recent = [t for t in self._attempts[key] if now - t < self.window]
        if recent:
            self._attempts[key] = recent
        else:
            self._attempts.pop(key, None)
        return recent

    def retry_after(self, key) -> int:
        """Seconds until this key may try again; 0 if it isn't blocked."""
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) < self.limit:
                return 0
            return math.ceil(recent[-self.limit] + self.window - now)

    def record(self, key):
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def clear(self, match=None):
        """Forgets every key, or only those `match(key)` is true for."""
        with self._lock:
            if match is None:
                self._attempts.clear()
            else:
                for key in [k for k in self._attempts if match(k)]:
                    del self._attempts[key]


FIFTEEN_MINUTES = 15 * 60

# Wrong passwords for one account from one device
login_failures_per_client = AttemptLimiter(5, FIFTEEN_MINUTES)
# Wrong passwords for one account from anywhere, so spreading guesses
# over many addresses doesn't help. Higher, because anyone can run this
# up for someone else's account.
login_failures_per_account = AttemptLimiter(25, FIFTEEN_MINUTES)
# Account requests from one device
registrations_per_client = AttemptLimiter(5, 60 * 60)

ALL_LIMITERS = (login_failures_per_client, login_failures_per_account,
                registrations_per_client)


def client_address(request: Request) -> str:
    """The caller's address. Requests arrive through Cloudflare and the
    reverse proxy, so the socket address is the proxy's."""
    forwarded = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip())
    return forwarded or (
        request.client.host if request.client else "unknown")


def refuse_if_blocked(limiter: AttemptLimiter, key, what: str):
    wait = limiter.retry_after(key)
    if wait:
        minutes = math.ceil(wait / 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many {what}. Try again in {minutes} "
                   f"minute{'' if minutes == 1 else 's'}.",
            headers={"Retry-After": str(wait)})


def forget_login_failures(user_id: int):
    """Unlocks an account, e.g. after the admin resets its password."""
    login_failures_per_client.clear(lambda key: key[1] == user_id)
    login_failures_per_account.clear(lambda key: key == user_id)
