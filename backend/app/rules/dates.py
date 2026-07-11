"""FY math, anchor resolution (ordered fallback), and offset application.

FY convention (charter §9): an FY is its ENDING year — FY 2025-26 == 2026.
Indian FY only in v1: 1 Apr (fy-1) .. 31 Mar (fy).
"""
from __future__ import annotations

import calendar as _cal
from datetime import date
from typing import Any


def fy_start(fy: int) -> date:
    return date(fy - 1, 4, 1)


def fy_end(fy: int) -> date:
    return date(fy, 3, 31)


def add_months(d: date, months: int) -> date:
    """Month arithmetic with end-of-month clamping (31 Mar + 6m → 30 Sep)."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, _cal.monthrange(year, month)[1])
    return date(year, month, day)


def resolve_anchor(anchor_spec: Any, company: dict[str, Any], fy: int) -> date | None:
    """Resolve an anchor spec to a date, or None if unresolvable.

    anchor_spec is a name or an ordered fallback list (Amendment A1 / G3):
        "fy_end" | "agm_date" | {"fy_end": {"plus_months": 6}} | [spec, spec, ...]
    First resolvable entry wins; none resolvable → None → needs_review
    (reason missing_anchor). Never guess.
    """
    if isinstance(anchor_spec, list):
        for entry in anchor_spec:
            resolved = resolve_anchor(entry, company, fy)
            if resolved is not None:
                return resolved
        return None

    if anchor_spec == "fy_end":
        return fy_end(fy)
    if anchor_spec == "agm_date":
        agm = company.get("agm_date")
        # only an AGM date that belongs to this FY's cycle counts
        if isinstance(agm, date) and fy_end(fy) < agm <= add_months(fy_end(fy), 12):
            return agm
        return None
    if anchor_spec == "fixed_date":
        return fy_end(fy)  # fixed offsets carry their own month/day; anchor is nominal
    if isinstance(anchor_spec, dict):
        if "fy_end" in anchor_spec:
            mods = anchor_spec["fy_end"] or {}
            return add_months(fy_end(fy), int(mods.get("plus_months", 0)))
        raise ValueError(f"unsupported anchor spec: {anchor_spec!r}")
    raise ValueError(f"unsupported anchor spec: {anchor_spec!r}")


def apply_offset(offset_spec: dict[str, Any], anchor: date | None, fy: int) -> date | None:
    """offset_spec:
    {"type": "offset", "unit": "days"|"months", "amount": N}   — from anchor
    {"type": "fixed", "month": M, "day": D,
     "year_ref": "fy_start_year"|"fy_end_year"|"fy_end_year_plus_1"}
    """
    kind = offset_spec.get("type")
    if kind == "offset":
        if anchor is None:
            return None
        amount = int(offset_spec["amount"])
        if offset_spec["unit"] == "days":
            from datetime import timedelta

            return anchor + timedelta(days=amount)
        if offset_spec["unit"] == "months":
            return add_months(anchor, amount)
        raise ValueError(f"unsupported offset unit: {offset_spec['unit']!r}")

    if kind == "fixed":
        year_ref = offset_spec.get("year_ref", "fy_end_year")
        year = {
            "fy_start_year": fy - 1,
            "fy_end_year": fy,
            "fy_end_year_plus_1": fy + 1,
        }[year_ref]
        return date(year, int(offset_spec["month"]), int(offset_spec["day"]))

    raise ValueError(f"unsupported offset type: {kind!r}")
