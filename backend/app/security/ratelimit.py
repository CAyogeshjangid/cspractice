"""Redis-backed fixed-window rate limiting (charter C4).

No in-memory state — works identically across N api replicas. Auth endpoints
get a stricter limit. Fails CLOSED on Redis outage for auth endpoints
(credential-stuffing protection beats availability there) and OPEN elsewhere.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import time

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp
from starlette.responses import JSONResponse, Response

AUTH_PREFIX = "/api/v1/auth"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, redis: Redis, per_minute: int, auth_per_minute: int
    ) -> None:
        super().__init__(app)
        self._redis = redis
        self._per_minute = per_minute
        self._auth_per_minute = auth_per_minute

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        is_auth = request.url.path.startswith(AUTH_PREFIX)
        limit = self._auth_per_minute if is_auth else self._per_minute
        client = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"rl:{'auth' if is_auth else 'api'}:{client}:{window}"

        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 90)
        except Exception:
            if is_auth:
                return _limited("rate limiter unavailable; auth temporarily refused")
            return await call_next(request)  # fail open for non-auth

        if count > limit:
            return _limited(f"limit {limit}/minute exceeded")
        return await call_next(request)


def _limited(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"type": "about:blank", "title": "Too many requests", "detail": detail},
        headers={"Retry-After": "60"},
    )
