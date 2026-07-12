"""Company Excel import/export routes. Included BEFORE the companies router
so the literal paths win over /companies/{company_id}."""
from __future__ import annotations

from typing import Any

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Role, User
from app import audit
from app.models import Company, Director, Shareholder
from app.repositories import companies as companies_repo
from app.repositories import companies as repo
from app.repositories import masters as masters_repo
from app.security.auth import require_role
from app.services import imports as svc

router = APIRouter(prefix="/api/v1/companies", tags=["import-export"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # a 300-entity portfolio is well under 1 MB


@router.get("/import/template")
async def download_template(user: User = Depends(require_role(Role.executive))) -> Response:
    return Response(
        content=svc.build_template(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="praxis_companies_template.xlsx"'},
    )


@router.post("/import")
async def import_companies(
    file: UploadFile,
    request: Request,
    dry_run: bool = False,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (5 MB limit)")

    parsed = svc.parse_and_validate(data)
    report = {
        "rows_ok": len(parsed.rows),
        "errors": [e.as_dict() for e in parsed.errors],
    }
    if parsed.errors:
        # all-or-nothing: nothing was imported; report exactly the bad rows
        raise HTTPException(status_code=422, detail={"title": "import validation failed", **report})
    if dry_run:
        return {**report, "dry_run": True, "imported": False}

    summary = await svc.commit_rows(session, user.firm_id, user.id, parsed.rows, request)
    return {**report, "imported": True, **summary}


@router.get("/export")
async def export_companies(
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows, _total = await repo.list_companies(session, user.firm_id, limit=10_000, offset=0)
    return Response(
        content=svc.build_export(rows),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="praxis_companies.xlsx"'},
    )


# ---------------------------------------------------------------------------
# Per-master import/export (M15 — PRD §4.3/4.4). Same all-or-nothing contract.

MASTER_MODELS: dict[str, type[Director] | type[Shareholder]] = {
    "directors": Director,
    "shareholders": Shareholder,
}


async def _owned_company(session: AsyncSession, user: User, company_id: uuid.UUID) -> Company:
    company = await companies_repo.get_company(session, user.firm_id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return company


def _master_or_404(master: str) -> None:
    if master not in svc.MASTER_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown master: {master}")


async def _master_template(
    company_id: uuid.UUID,
    master: str,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _master_or_404(master)
    await _owned_company(session, user, company_id)
    return Response(
        content=svc.build_master_template(master),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="praxis_{master}_template.xlsx"'},
    )


async def _master_import(
    company_id: uuid.UUID,
    master: str,
    file: UploadFile,
    request: Request,
    dry_run: bool = False,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _master_or_404(master)
    await _owned_company(session, user, company_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (5 MB limit)")

    parsed = svc.parse_master(master, data)
    report = {"rows_ok": len(parsed.rows), "errors": [e.as_dict() for e in parsed.errors]}
    if parsed.errors:
        raise HTTPException(status_code=422, detail={"title": "import validation failed", **report})
    if dry_run:
        return {**report, "dry_run": True, "imported": False}

    identity = svc.MASTER_SPECS[master]["identity"]
    existing_rows: list[Director] | list[Shareholder]
    if master == "directors":
        existing_rows = await masters_repo.list_directors(session, user.firm_id, company_id)
    else:
        existing_rows = await masters_repo.list_shareholders(session, user.firm_id, company_id)
    existing = {
        identity({"din": getattr(r, "din", None),
                  "folio": getattr(r, "folio", None),
                  "name": r.name})
        for r in existing_rows
    }

    model = MASTER_MODELS[master]
    created = skipped = 0
    for record in parsed.rows:
        payload = {k: v for k, v in record.items() if k != "_row"}
        if identity(payload) in existing:
            skipped += 1  # idempotent re-import: exact identity already present
            continue
        row = model(firm_id=user.firm_id, company_id=company_id, **payload)
        session.add(row)
        await session.flush()
        await audit.record(
            session, firm_id=user.firm_id, actor_user_id=user.id,
            entity_type=master[:-1], entity_id=row.id, action="import_create",
            after={k: str(v) for k, v in payload.items()}, request=request,
        )
        created += 1
    await session.commit()
    return {**report, "imported": True, "created": created, "skipped": skipped}


async def _master_export(
    company_id: uuid.UUID,
    master: str,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _master_or_404(master)
    await _owned_company(session, user, company_id)
    rows: list[Director] | list[Shareholder]
    if master == "directors":
        rows = await masters_repo.list_directors(session, user.firm_id, company_id)
    else:
        rows = await masters_repo.list_shareholders(session, user.firm_id, company_id)

    headers = svc.MASTER_SPECS[master]["headers"]
    wb = Workbook()
    ws = wb.active
    ws.title = master
    ws.append(headers)
    for r in rows:
        ws.append([str(getattr(r, h)) if getattr(r, h, None) is not None else None
                   for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{master}.xlsx"'},
    )


# Literal routes per master — a generic /{master} segment would shadow the
# sibling routers' literal paths (e.g. /companies/{id}/calendar/export).
@router.get("/{company_id}/directors/import/template")
async def directors_template(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    return await _master_template(company_id, "directors", user, session)


@router.get("/{company_id}/shareholders/import/template")
async def shareholders_template(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    return await _master_template(company_id, "shareholders", user, session)


@router.post("/{company_id}/directors/import")
async def directors_import(
    company_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    dry_run: bool = False,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await _master_import(company_id, "directors", file, request, dry_run, user, session)


@router.post("/{company_id}/shareholders/import")
async def shareholders_import(
    company_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    dry_run: bool = False,
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await _master_import(company_id, "shareholders", file, request, dry_run, user, session)


@router.get("/{company_id}/directors/export")
async def directors_export(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    return await _master_export(company_id, "directors", user, session)


@router.get("/{company_id}/shareholders/export")
async def shareholders_export(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    return await _master_export(company_id, "shareholders", user, session)
