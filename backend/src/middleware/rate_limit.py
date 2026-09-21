"""Sliding-window rate limit, keyed by client IP.

A FastAPI *dependency* rather than ASGI middleware, so it only guards the
endpoint that costs money. Listing sessions doesn't need it.

State lives in process memory: it resets on restart and isn't shared between
workers. Right trade for a single-instance demo. The production version is
the same algorithm with the timestamps in Redis.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from .. import config

# ip -> timestamps of requests inside the current window
_requests: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request) -> None:
    # Behind a reverse proxy you'd read X-Forwarded-For instead.
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - config.RATE_LIMIT_WINDOW_SECONDS

    recent = [t for t in _requests[client_ip] if t > window_start]  # drop aged-out
    _requests[client_ip] = recent

    if len(recent) >= config.RATE_LIMIT_REQUESTS:
        retry_after = int(recent[0] + config.RATE_LIMIT_WINDOW_SECONDS - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    recent.append(now)


def reset() -> None:
    """Clear all state. The test suite calls this between tests."""
    _requests.clear()