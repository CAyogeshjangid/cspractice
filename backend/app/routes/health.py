from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": get_settings().version}
