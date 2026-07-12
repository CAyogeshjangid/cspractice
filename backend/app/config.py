"""Settings — the ONLY reader of os.environ (charter C8).

Fails fast at import of get_settings() with a clear list of missing vars.
No defaults for secrets, no wildcard CORS (C1), no generated fallbacks (C3).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required — no defaults. Missing → pydantic ValidationError at startup.
    database_url: str
    redis_url: str
    jwt_secret: str
    csrf_secret: str
    cors_origins: str  # comma-separated explicit origins (C1)

    # Optional with safe defaults (all listed in .env.example — C6).
    env: str = "dev"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    storage_dir: str = "./data"  # generated documents root

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard(cls, v: str) -> str:
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must list at least one explicit origin")
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must not contain '*' (charter C1)")
        return v

    @field_validator("jwt_secret", "csrf_secret")
    @classmethod
    def _secret_strength(cls, v: str) -> str:
        if len(v) < 32 or v.startswith("CHANGE_ME"):
            raise ValueError("secret must be ≥32 chars and not a placeholder (charter C8)")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def version(self) -> str:
        return _VERSION_FILE.read_text().strip()  # single source (C7)

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # required kwargs come from env (C8)
    except Exception as exc:  # re-raise with an operator-friendly message
        raise RuntimeError(
            "Praxis refuses to start: missing/invalid configuration.\n"
            f"{exc}\n"
            "Copy .env.example to .env and fill every required variable."
        ) from exc
