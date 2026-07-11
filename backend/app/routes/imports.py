"""Company Excel import/export routes. Included BEFORE the companies router
so the literal paths win over /companies/{company_id}."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Role, User
from app.repositories import companies as repo
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
) -> dict:
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
