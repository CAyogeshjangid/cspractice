"""App factory — middleware registration and fail-fast settings (charter M1).

Middleware order (outermost first): headers → CORS → rate limit → CSRF.
CSRF is registered unconditionally; there is no path that skips it (C3).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.config import get_settings
from app.routes import (
    activity,
    auth,
    calendar,
    companies,
    directors,
    documents,
    firm,
    health,
    imports,
    meetings,
    registers,
    reminders,
    shareholders,
    taxonomies,
    team,
)
from app.security.csrf import CSRFMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.ratelimit import RateLimitMiddleware


def create_app() -> FastAPI:
    settings = get_settings()  # raises with a clear message if config is missing (C8)

    app = FastAPI(title="Praxis", version=settings.version, docs_url=None, redoc_url=None)

    # Starlette applies middleware in reverse registration order → register inner first.
    app.add_middleware(CSRFMiddleware, secret=settings.csrf_secret)
    app.add_middleware(
        RateLimitMiddleware,
        redis=Redis.from_url(settings.redis_url),
        per_minute=settings.rate_limit_per_minute,
        auth_per_minute=settings.auth_rate_limit_per_minute,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,  # explicit, never '*' (C1)
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(imports.router)  # literal /companies/import|export before /{company_id}
    app.include_router(companies.router)
    app.include_router(directors.router)
    app.include_router(shareholders.router)
    app.include_router(taxonomies.router)
    app.include_router(calendar.router)
    app.include_router(reminders.router)
    app.include_router(firm.router)
    app.include_router(documents.router)
    app.include_router(activity.router)
    app.include_router(registers.router)
    app.include_router(meetings.router)
    app.include_router(team.router)
    return app


def run() -> None:  # uvicorn entrypoint: `uvicorn app.main:app` via factory
    import uvicorn

    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000)


app = create_app  # factory reference for uvicorn --factory
