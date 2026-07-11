"""Charter C1/C8: fail-fast config, no wildcard CORS, no weak secrets."""
from __future__ import annotations

import pytest


def test_missing_env_refuses_to_start(clean_env) -> None:
    from app.config import get_settings

    with pytest.raises(RuntimeError, match="refuses to start"):
        get_settings()


def test_wildcard_cors_rejected(app_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", "*")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="refuses to start"):
        get_settings()


def test_placeholder_secret_rejected(app_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("CSRF_SECRET", "CHANGE_ME_this_is_long_enough_but_placeholder")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="refuses to start"):
        get_settings()


def test_valid_env_loads_and_reads_version(app_env) -> None:
    from app.config import get_settings

    s = get_settings()
    assert s.cors_origin_list == ["http://localhost:5173"]
    assert s.version  # single-sourced from /VERSION (C7)
