"""Envelope encryption for secrets stored in firm.settings JSONB (charter §5).

Key is derived from JWT_SECRET — no plaintext SMTP passwords / API keys at
rest, and no secret ever surfaces in logs or API responses (C8): GET routes
return presence flags, never values.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
