"""Directors / shareholders / disclosures / taxonomies — every fn takes firm_id (C10)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Director,
    DirectorDisclosure,
    Industry,
    ProfessionalGroup,
    Shareholder,
)
from app.rules.dates import fy_end, fy_start


async def list_directors(
    session: AsyncSession,
    firm_id: uuid.UUID,
    company_id: uuid.UUID,
    fy: int | None = None,
) -> list[Director]:
    q = select(Director).where(
        Director.firm_id == firm_id, Director.company_id == company_id
    )
    if fy is not None:
        # in office at any point during the FY: appointed on/before FY end,
        # and not ceased before FY start
        q = q.where(
            (Director.appointment_date.is_(None)) | (Director.appointment_date <= fy_end(fy))
        ).where(
            (Director.cessation_date.is_(None)) | (Director.cessation_date >= fy_start(fy))
        )
    return list((await session.execute(q.order_by(Director.name))).scalars().all())


async def get_director(
    session: AsyncSession, firm_id: uuid.UUID, director_id: uuid.UUID
) -> Director | None:
    return (
        await session.execute(
            select(Director).where(Director.firm_id == firm_id, Director.id == director_id)
        )
    ).scalar_one_or_none()


async def create_director(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID, data: dict[str, Any]
) -> Director:
    director = Director(firm_id=firm_id, company_id=company_id, **data)
    session.add(director)
    await session.flush()
    return director


async def upsert_disclosure(
    session: AsyncSession,
    firm_id: uuid.UUID,
    director_id: uuid.UUID,
    fy: int,
    data: dict[str, Any],
) -> tuple[DirectorDisclosure, dict[str, Any] | None]:
    """Returns (row, before-dict or None if created)."""
    existing = (
        await session.execute(
            select(DirectorDisclosure).where(
                DirectorDisclosure.firm_id == firm_id,
                DirectorDisclosure.director_id == director_id,
                DirectorDisclosure.fy == fy,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        row = DirectorDisclosure(firm_id=firm_id, director_id=director_id, fy=fy, **data)
        session.add(row)
        await session.flush()
        return row, None
    before = {k: str(getattr(existing, k)) for k in data}
    for k, v in data.items():
        setattr(existing, k, v)
    await session.flush()
    return existing, before


async def list_disclosures(
    session: AsyncSession, firm_id: uuid.UUID, director_id: uuid.UUID
) -> list[DirectorDisclosure]:
    return list(
        (
            await session.execute(
                select(DirectorDisclosure)
                .where(
                    DirectorDisclosure.firm_id == firm_id,
                    DirectorDisclosure.director_id == director_id,
                )
                .order_by(DirectorDisclosure.fy)
            )
        )
        .scalars()
        .all()
    )


async def list_shareholders(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID
) -> list[Shareholder]:
    return list(
        (
            await session.execute(
                select(Shareholder)
                .where(Shareholder.firm_id == firm_id, Shareholder.company_id == company_id)
                .order_by(Shareholder.name)
            )
        )
        .scalars()
        .all()
    )


async def get_shareholder(
    session: AsyncSession, firm_id: uuid.UUID, shareholder_id: uuid.UUID
) -> Shareholder | None:
    return (
        await session.execute(
            select(Shareholder).where(
                Shareholder.firm_id == firm_id, Shareholder.id == shareholder_id
            )
        )
    ).scalar_one_or_none()


async def create_shareholder(
    session: AsyncSession, firm_id: uuid.UUID, company_id: uuid.UUID, data: dict[str, Any]
) -> Shareholder:
    row = Shareholder(firm_id=firm_id, company_id=company_id, **data)
    session.add(row)
    await session.flush()
    return row


TAXONOMY_MODELS = {"professional-groups": ProfessionalGroup, "industries": Industry}


async def list_taxonomy(
    session: AsyncSession, firm_id: uuid.UUID, kind: str
) -> list[ProfessionalGroup | Industry]:
    model = TAXONOMY_MODELS[kind]
    return list(
        (
            await session.execute(
                select(model).where(model.firm_id == firm_id).order_by(model.name)
            )
        )
        .scalars()
        .all()
    )


async def create_taxonomy(
    session: AsyncSession, firm_id: uuid.UUID, kind: str, name: str
) -> ProfessionalGroup | Industry:
    model = TAXONOMY_MODELS[kind]
    row = model(firm_id=firm_id, name=name)
    session.add(row)
    await session.flush()
    return row
