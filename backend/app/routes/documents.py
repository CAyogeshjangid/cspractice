"""Template registry + document generation + library (charter M6, PRD §4.7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models import (
    DocTemplate,
    Firm,
    GeneratedDocument,
    Letterhead,
    Role,
    User,
)
from app.repositories import companies as companies_repo
from app.security.auth import require_role
from app.services import documents as svc

router = APIRouter(prefix="/api/v1", tags=["documents"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ValidateIn(BaseModel):
    validated_by: str = Field(min_length=3, max_length=200)
    membership_no: str = Field(min_length=1, max_length=50)


class GenerateIn(BaseModel):
    template_code: str = Field(min_length=1, max_length=50)
    letterhead: Letterhead = Letterhead.none
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/templates")
async def list_templates(
    user: User = Depends(require_role(Role.executive)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        (await session.execute(select(DocTemplate).order_by(DocTemplate.code))).scalars().all()
    )
    return [
        {
            "code": t.code,
            "name": t.name,
            "governing_reference": t.governing_reference,
            "version": t.version,
            "is_active": t.is_active,
            "validated": t.validated_at is not None,
            "validated_by": t.validated_by,
            "validated_at": t.validated_at.isoformat() if t.validated_at else None,
        }
        for t in rows
    ]


@router.put("/templates/{code}/validate")
async def validate_template(
    code: str,
    body: ValidateIn,
    request: Request,
    user: User = Depends(require_role(Role.manager)),  # template management: P/M (PRD §9)
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    template = (
        await session.execute(select(DocTemplate).where(DocTemplate.code == code))
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    template.validated_by = body.validated_by
    template.validated_membership_no = body.membership_no
    template.validated_at = datetime.now(timezone.utc)
    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="doc_template",
        entity_id=template.id, action="validate",
        after={"validated_by": body.validated_by, "membership_no": body.membership_no,
               "version": template.version},
        request=request,
    )
    await session.commit()
    return {"code": code, "validated": True, "version": template.version}


@router.post("/companies/{company_id}/documents", status_code=201)
async def generate_document(
    company_id: uuid.UUID,
    body: GenerateIn,
    request: Request,
    user: User = Depends(require_role(Role.executive)),  # generate docs: P/M/E (PRD §9)
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    company = await companies_repo.get_company(session, user.firm_id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    firm = (await session.execute(select(Firm).where(Firm.id == user.firm_id))).scalar_one()

    try:
        doc_id, _path = await svc.generate(
            session, firm, company, body.template_code, body.letterhead, body.params, user.id
        )
    except svc.TemplateNotUsable as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except svc.MissingContext as exc:
        raise HTTPException(
            status_code=422,
            detail={"title": "missing merge fields", "missing": exc.missing,
                    "hint": "supply these in params"},
        )

    await audit.record(
        session, firm_id=user.firm_id, actor_user_id=user.id, entity_type="generated_document",
        entity_id=doc_id, action="generate",
        after={"template_code": body.template_code, "letterhead": body.letterhead.value},
        request=request,
    )
    await session.commit()
    return {"id": str(doc_id), "download": f"/api/v1/documents/{doc_id}/download"}


@router.get("/companies/{company_id}/documents")
async def document_library(
    company_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    if await companies_repo.get_company(session, user.firm_id, company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")
    rows = (
        (
            await session.execute(
                select(GeneratedDocument, DocTemplate.code, DocTemplate.name)
                .join(DocTemplate, GeneratedDocument.template_id == DocTemplate.id)
                .where(
                    GeneratedDocument.firm_id == user.firm_id,
                    GeneratedDocument.company_id == company_id,
                )
                .order_by(GeneratedDocument.created_at.desc())
            )
        ).all()
    )
    return [
        {
            "id": str(doc.id),
            "template_code": code,
            "template_name": name,
            "template_version": doc.template_version,
            "letterhead": doc.letterhead.value,
            "generated_at": doc.created_at.isoformat(),
            "download": f"/api/v1/documents/{doc.id}/download",
        }
        for doc, code, name in rows
    ]


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    doc = (
        await session.execute(
            select(GeneratedDocument).where(
                GeneratedDocument.firm_id == user.firm_id,
                GeneratedDocument.id == document_id,
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="document file no longer on storage")
    return Response(
        content=path.read_bytes(),
        media_type=DOCX,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@router.get("/documents/{document_id}/snapshot")
async def document_snapshot(
    document_id: uuid.UUID,
    user: User = Depends(require_role(Role.viewer)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    doc = (
        await session.execute(
            select(GeneratedDocument).where(
                GeneratedDocument.firm_id == user.firm_id,
                GeneratedDocument.id == document_id,
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc.data_snapshot
