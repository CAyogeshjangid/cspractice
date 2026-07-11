"""CSRF — double-submit cookie with HMAC binding (charter C3).

Registered unconditionally at app construction. There is no flag, env var,
or code path that disables it. Login/registration are NOT exempt: clients
first GET /api/v1/auth/csrf to receive the cookie, then send the
X-CSRF-Token header on every mutating request.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
COOKIE_NAME = "praxis_csrf"
HEADER_NAME = "X-CSRF-Token"


def _sign(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def issue_token(secret: str) -> str:
    """Returns 'token.signature' — cookie value and expected header value."""
    token = secrets.token_urlsafe(32)
    return f"{token}.{_sign(token, secret)}"


def _valid(value: str, secret: str) -> bool:
    token, _, sig = value.rpartition(".")
    return bool(token) and hmac.compare_digest(_sign(token, secret), sig)


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str) -> None:
        super().__init__(app)
        self._secret = secret

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in SAFE_METHODS:
            cookie = request.cookies.get(COOKIE_NAME, "")
            header = request.headers.get(HEADER_NAME, "")
            if (
                not cookie
                or not header
                or not hmac.compare_digest(cookie, header)
                or not _valid(cookie, self._secret)
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "type": "about:blank",
                        "title": "CSRF token missing or invalid",
                        "detail": f"send the {HEADER_NAME} header matching the CSRF cookie",
                    },
                )
        return await call_next(request)
