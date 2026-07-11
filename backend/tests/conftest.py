from __future__ import annotations

import os

import pytest

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://praxis:test@localhost:5432/praxis_test",
    "REDIS_URL": "redis://localhost:6399/0",  # deliberately unreachable in unit runs
    "JWT_SECRET": "unit-test-jwt-secret-0123456789abcdefghijklmn",
    "CSRF_SECRET": "unit-test-csrf-secret-0123456789abcdefghijklm",
    "CORS_ORIGINS": "http://localhost:5173",
}


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
    monkeypatch.setattr("pydantic_settings.sources.DotEnvSettingsSource._read_env_files",
                        lambda self: {}, raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def unset_env_app(clean_env):
    return None
