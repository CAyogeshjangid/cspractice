"""Email provider abstraction: SMTP + Resend, selected per firm (charter §3).

Config lives encrypted in firm.settings["email"]; a missing/incomplete config
raises ProviderNotConfigured so dispatches land in the dead-letter view
instead of failing silently (PRD §4.6: silent failure is a defect).
"""
from __future__ import annotations

from typing import Any

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

import httpx

from app.security.crypto import decrypt_secret

RESEND_API_URL = "https://api.resend.com/emails"


class ProviderNotConfigured(Exception):
    pass


@dataclass
class EmailPayload:
    to: list[str]
    subject: str
    body: str


async def send_email(firm_settings: dict[str, Any], payload: EmailPayload) -> str:
    """Send via the firm's configured provider. Returns the provider name."""
    config = (firm_settings or {}).get("email") or {}
    provider = config.get("provider")
    if provider == "smtp":
        await _send_smtp(config, payload)
        return "smtp"
    if provider == "resend":
        await _send_resend(config, payload)
        return "resend"
    raise ProviderNotConfigured("no email provider configured for this firm")


async def _send_smtp(config: dict[str, Any], payload: EmailPayload) -> None:
    required = {"host", "port", "from_addr"}
    if missing := required - config.keys():
        raise ProviderNotConfigured(f"smtp config missing: {sorted(missing)}")

    def _send() -> None:
        msg = MimeMessage()
        msg["From"] = config["from_addr"]
        msg["To"] = ", ".join(payload.to)
        msg["Subject"] = payload.subject
        msg.set_content(payload.body)
        with smtplib.SMTP(config["host"], int(config["port"]), timeout=30) as smtp:
            if config.get("use_tls", True):
                smtp.starttls()
            if config.get("username"):
                smtp.login(config["username"], decrypt_secret(config["password_enc"]))
            smtp.send_message(msg)

    await asyncio.to_thread(_send)  # smtplib is blocking; keep the loop free


async def _send_resend(config: dict[str, Any], payload: EmailPayload) -> None:
    if "api_key_enc" not in config or "from_addr" not in config:
        raise ProviderNotConfigured("resend config missing api key or from address")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {decrypt_secret(config['api_key_enc'])}"},
            json={
                "from": config["from_addr"],
                "to": payload.to,
                "subject": payload.subject,
                "text": payload.body,
            },
        )
        response.raise_for_status()
