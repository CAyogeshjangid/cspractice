from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

# Real service URLs come from the environment (CI services / local dev);
# the fallbacks match the local scratch Postgres+Redis. Rate limits are high
# so auth-heavy tests never trip the limiter (it has its own dedicated test).
REQUIRED_ENV = {
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://praxis:migtest@127.0.0.1:5433/praxis_test"
    ),
    "REDIS_URL": os.environ.get("REDIS_URL", "redis://127.0.0.1:6399/1"),
    "JWT_SECRET": "unit-test-jwt-secret-0123456789abcdefghijklmn",
    "CSRF_SECRET": "unit-test-csrf-secret-0123456789abcdefghijklm",
    "CORS_ORIGINS": "http://localhost:5173",
    "RATE_LIMIT_PER_MINUTE": "100000",
    "AUTH_RATE_LIMIT_PER_MINUTE": "100000",
    "STORAGE_DIR": os.environ.get(
        "STORAGE_DIR", os.path.join(tempfile.gettempdir(), "praxis-test-docs")
    ),
}

STRONG_PW = "a-strong-password-123"  # test fixture value, not a credential


@pytest.fixture()
def app_env(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "pydantic_settings.sources.DotEnvSettingsSource._read_env_files",
        lambda self: {},
        raising=False,
    )
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
async def db(app_env):
    """Fresh schema per test against REAL Postgres — no mocked DB (charter §8)."""
    import app.db as dbmod
    import app.security.auth as authmod
    from app.models import Base

    # engines/clients are loop-bound; reset so each test's loop gets its own
    dbmod._engine = None
    dbmod._sessionmaker = None
    authmod._redis_client = None

    engine = dbmod.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if authmod._redis_client is not None:
        await authmod._redis_client.aclose()
    dbmod._engine = None
    dbmod._sessionmaker = None
    authmod._redis_client = None


@pytest.fixture()
async def make_client(db):
    from app.main import create_app

    app = create_app()
    clients: list[AsyncClient] = []

    def _make() -> AsyncClient:
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()


async def csrf(client: AsyncClient) -> str:
    """Fetch (once) and cache the CSRF token for a client's cookie jar."""
    token = getattr(client, "_csrf", None)
    if token is None:
        res = await client.get("/api/v1/auth/csrf")
        token = res.json()["csrf_token"]
        client._csrf = token  # type: ignore[attr-defined]
    return token


async def post(client: AsyncClient, path: str, json: dict, method: str = "POST"):
    return await client.request(
        method, f"/api/v1{path}", json=json, headers={"X-CSRF-Token": await csrf(client)}
    )


async def register_firm(client: AsyncClient, email: str, firm_name: str = "Test Firm"):
    res = await post(
        client, "/auth/register",
        {"firm_name": firm_name, "email": email, "password": STRONG_PW},
    )
    assert res.status_code == 201, res.text
    return res


@pytest.fixture()
async def firm(make_client):
    """A firm with all four personas, provisioned via the real invitation flow."""
    partner = make_client()
    await register_firm(partner, "partner@example.com")

    async def add(role: str) -> AsyncClient:
        res = await post(partner, "/team/invitations", {"email": f"{role}@example.com", "role": role})
        assert res.status_code == 201, res.text
        token = res.json()["token"]
        c = make_client()
        accept = await post(c, "/team/invitations/accept", {"token": token, "password": STRONG_PW})
        assert accept.status_code == 201, accept.text
        return c

    return SimpleNamespace(
        partner=partner,
        manager=await add("manager"),
        executive=await add("executive"),
        viewer=await add("viewer"),
        make_client=make_client,
    )
