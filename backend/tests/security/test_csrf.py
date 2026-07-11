"""Charter C3 acceptance: a mutating request without a CSRF token returns 403.

Runs without Postgres/Redis: the CSRF middleware rejects before any route or
DB dependency executes, and the rate limiter fails open for non-auth paths.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def client(app_env):
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_mutating_request_without_csrf_is_403(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/companies", json={"cin": "X" * 21, "name": "T"})
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["title"]


async def test_header_without_cookie_is_403(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/companies",
        json={"cin": "X" * 21, "name": "T"},
        headers={"X-CSRF-Token": "forged-token.deadbeef"},
    )
    assert resp.status_code == 403


async def test_mismatched_cookie_and_header_is_403(client: AsyncClient) -> None:
    from app.config import get_settings
    from app.security.csrf import issue_token

    real = issue_token(get_settings().csrf_secret)
    client.cookies.set("praxis_csrf", real)
    resp = await client.post(
        "/api/v1/companies",
        json={"cin": "X" * 21, "name": "T"},
        headers={"X-CSRF-Token": "different-value.sig"},
    )
    assert resp.status_code == 403


async def test_valid_csrf_passes_middleware(client: AsyncClient) -> None:
    """With a valid token the request reaches auth (401), proving CSRF passed."""
    from app.config import get_settings
    from app.security.csrf import issue_token

    token = issue_token(get_settings().csrf_secret)
    client.cookies.set("praxis_csrf", token)
    resp = await client.post(
        "/api/v1/companies",
        json={"cin": "X" * 21, "name": "T"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 401  # not 403: CSRF ok, authentication required


async def test_get_needs_no_csrf_and_carries_security_headers(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    # C9: headers on ALL routes including /api/*
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "unsafe-eval" not in resp.headers["Content-Security-Policy"]
