"""Document generation via docxtpl (charter M6).

Hard rules:
- Templates without a CURRENT validation stamp (validated_at set, is_active)
  are refused with a clear 422 — enforced, not advisory (PRD §4.7).
- Rendering uses StrictUndefined: a merge field with no value fails loudly
  and reports the missing variables instead of silently printing blanks —
  a blank in a statutory document is a liability, not a default.
- Every generated document is stored with a full data snapshot (§4.7).

Template registry sync: `python -m app.services.documents` upserts
doc_template rows from templates/docx/manifest.json (idempotent; never
touches stamps).
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
from jinja2 import StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Company, DocTemplate, Firm, Letterhead
from app.repositories import masters as masters_repo

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "docx"


class TemplateNotUsable(Exception):
    """Template missing, inactive, or unstamped."""


class MissingContext(Exception):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"missing merge fields: {missing}")


async def sync_templates(session: AsyncSession) -> dict[str, int]:
    manifest = json.loads((TEMPLATES_DIR / "manifest.json").read_text())
    created = updated = 0
    for entry in manifest:
        row = (
            await session.execute(select(DocTemplate).where(DocTemplate.code == entry["code"]))
        ).scalar_one_or_none()
        if row is None:
            session.add(
                DocTemplate(
                    code=entry["code"],
                    name=entry["name"],
                    governing_reference=entry["governing_reference"],
                    file_path=entry["file"],
                    version=entry["version"],
                )
            )
            created += 1
        elif (row.name, row.governing_reference, row.file_path, row.version) != (
            entry["name"], entry["governing_reference"], entry["file"], entry["version"],
        ):
            row.name = entry["name"]
            row.governing_reference = entry["governing_reference"]
            row.file_path = entry["file"]
            if row.version != entry["version"]:
                row.version = entry["version"]
                # a NEW template version invalidates the old stamp (PRD §4.7:
                # stamps are per-version — revalidation required)
                row.validated_at = None
                row.validated_by = None
                row.validated_membership_no = None
            updated += 1
    await session.commit()
    return {"created": created, "updated": updated}


async def build_context(
    session: AsyncSession,
    firm: Firm,
    company: Company,
    letterhead: Letterhead,
    params: dict[str, Any],
) -> dict[str, Any]:
    directors = await masters_repo.list_directors(session, firm.id, company.id)
    shareholders = await masters_repo.list_shareholders(session, firm.id, company.id)

    if letterhead == Letterhead.company:
        head_name, head_addr = company.name, company.registered_address or ""
    elif letterhead == Letterhead.pcs:
        head_name = firm.name
        head_addr = (firm.settings or {}).get("letterhead_address", "")
    else:
        head_name = head_addr = ""

    computed = {
        "letterhead_name": head_name,
        "letterhead_address": head_addr,
        "company_name": company.name,
        "cin": company.cin,
        "registered_address": company.registered_address or "",
        "agm_date": str(company.agm_date) if company.agm_date else "",
        "fy_end_date": f"{company.fy_end_day:02d}-{company.fy_end_month:02d}",
        "document_date": str(date.today()),
        "directors": [
            {
                "name": d.name,
                "din": d.din or "—",
                "designation": d.designation or "Director",
                "appointment_date": str(d.appointment_date) if d.appointment_date else "—",
            }
            for d in directors
            if d.is_active
        ],
        "shareholders": [
            {
                "name": s.name,
                "folio": s.folio or "—",
                "shares": str(s.shares or 0),
                "percentage": str(s.percentage or 0),
                "category": s.category or "—",
            }
            for s in shareholders
        ],
        "total_shares": str(sum(int(s.shares or 0) for s in shareholders)),
    }
    # caller params fill the rest (venue, times, business items, financials);
    # computed values always win so master data cannot be spoofed per-request
    return {**params, **computed}


def render(template_file: str, context: dict[str, Any]) -> bytes:
    path = TEMPLATES_DIR / template_file
    if not path.exists():
        raise TemplateNotUsable(f"template file missing: {template_file}")
    doc = DocxTemplate(str(path))

    env_vars = doc.get_undeclared_template_variables()
    missing = sorted(v for v in env_vars if v not in context)
    if missing:
        raise MissingContext(missing)

    from jinja2 import Environment

    doc.render(context, jinja_env=Environment(undefined=StrictUndefined, autoescape=False))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def generate(
    session: AsyncSession,
    firm: Firm,
    company: Company,
    template_code: str,
    letterhead: Letterhead,
    params: dict[str, Any],
    actor_user_id: uuid.UUID,
    context_overrides: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, str]:
    """→ (generated_document id, absolute file path). Raises TemplateNotUsable /
    MissingContext for the route to map to 422."""
    template = (
        await session.execute(select(DocTemplate).where(DocTemplate.code == template_code))
    ).scalar_one_or_none()
    if template is None:
        raise TemplateNotUsable(f"unknown template code: {template_code}")
    if not template.is_active or template.validated_at is None:
        raise TemplateNotUsable(
            f"template {template_code} has no current validation stamp — a reviewing "
            "professional must validate it before production use (PRD §4.7)"
        )

    context = await build_context(session, firm, company, letterhead, params)
    if context_overrides:
        # SERVER-ONLY: never exposed on the generic route. Used by trusted
        # services (meeting packs) that derive values from master data
        # themselves — e.g. an attendance list limited to the meeting's
        # participants, still sourced from the directors register.
        context.update(context_overrides)
    rendered = render(template.file_path, context)

    storage = Path(get_settings().storage_dir) / str(firm.id) / str(company.id)
    storage.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = storage / f"{template_code}-{stamp}-{uuid.uuid4().hex[:8]}.docx"
    out_path.write_bytes(rendered)

    from app.models import GeneratedDocument

    row = GeneratedDocument(
        firm_id=firm.id,
        company_id=company.id,
        template_id=template.id,
        template_version=template.version,
        letterhead=letterhead,
        data_snapshot={"context": _jsonable(context), "params": _jsonable(params)},
        file_path=str(out_path),
        generated_by=actor_user_id,
    )
    session.add(row)
    await session.flush()
    return row.id, str(out_path)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


async def main() -> None:
    """CLI: sync the template registry from manifest.json."""
    from app.db import get_engine, get_session

    get_engine()
    async for session in get_session():
        print(await sync_templates(session))  # noqa: T201 — CLI output


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
