"""
Simple in-memory sliding-window rate limiter middleware.

Keyed on the x-api-key header value.  Falls back to client IP when no key
is present (covers unauthenticated requests that will be rejected by auth
anyway, but we still want to prevent flood-before-auth patterns).

No external dependencies — works out of the box alongside the existing
in-memory cache.  For multi-process deployments, swap the _windows dict
for a Redis-backed counter.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings

logger = logging.getLogger(__name__)

# { identifier: deque of request timestamps (monotonic) }
_windows: dict[str, deque[float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter: RATE_LIMIT_PER_MINUTE requests / 60 s.

    Returns HTTP 429 with Retry-After header on breach.
    Health-check endpoint is exempt.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self._limit = settings.rate_limit_per_minute
        self._window = 60.0  # seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        identifier = (
            request.headers.get("x-api-key")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )

        now = time.monotonic()
        window = _windows.setdefault(identifier, deque())

        # Evict timestamps outside the rolling window
        while window and window[0] <= now - self._window:
            window.popleft()

        if len(window) >= self._limit:
            retry_after = int(self._window - (now - window[0])) + 1
            logger.warning("Rate limit exceeded for %s", identifier[:16])
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self._limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        window.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._limit)
        response.headers["X-RateLimit-Remaining"] = str(self._limit - len(window))
        return response
