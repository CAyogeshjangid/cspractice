"""Tri-state (Kleene) predicate evaluation — Amendment A1 / spike G1.

A predicate over company attributes resolves TRUE, FALSE, or UNKNOWN.
UNKNOWN propagates: the calendar emits the row flagged needs_review
(reason applicability_unknown) instead of silently dropping an obligation —
a missed *emission* is the invisible failure mode this design forbids.

Grammar (JSON/YAML):
    {"all": [<pred>, ...]}
    {"any": [<pred>, ...]}
    {"not": <pred>}
    {"attr": <name>, "op": eq|ne|gt|gte|lt|lte|in, "value": <v>, "at": "fy"|"fy-1"}

Attributes come from an AttributeBag: {fy: {attr_name: value}}; a missing or
None attribute resolves UNKNOWN (never False).
"""
from __future__ import annotations

import enum
from typing import Any


class Tri(enum.Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


AttributeBag = dict[int, dict[str, Any]]  # fy -> {attr: value}

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
}


def evaluate(pred: dict[str, Any] | None, attrs: AttributeBag, fy: int) -> Tri:
    """Evaluate a predicate for a given FY (ending-year convention, §9)."""
    if pred is None or pred == {}:
        return Tri.TRUE  # no predicate = universally applicable

    if "all" in pred:
        results = [evaluate(p, attrs, fy) for p in pred["all"]]
        if Tri.FALSE in results:
            return Tri.FALSE
        return Tri.UNKNOWN if Tri.UNKNOWN in results else Tri.TRUE

    if "any" in pred:
        results = [evaluate(p, attrs, fy) for p in pred["any"]]
        if Tri.TRUE in results:
            return Tri.TRUE
        return Tri.UNKNOWN if Tri.UNKNOWN in results else Tri.FALSE

    if "not" in pred:
        inner = evaluate(pred["not"], attrs, fy)
        if inner is Tri.UNKNOWN:
            return Tri.UNKNOWN
        return Tri.FALSE if inner is Tri.TRUE else Tri.TRUE

    if "attr" in pred:
        return _leaf(pred, attrs, fy)

    raise ValueError(f"malformed predicate node: {pred!r}")


def _leaf(pred: dict[str, Any], attrs: AttributeBag, fy: int) -> Tri:
    at = pred.get("at", "fy")
    if at == "fy":
        target_fy = fy
    elif at == "fy-1":  # e.g. CSR tests the PRECEDING FY's financials (G8)
        target_fy = fy - 1
    else:
        raise ValueError(f"unsupported 'at' addressing: {at!r}")

    op = pred.get("op")
    if op not in _OPS:
        raise ValueError(f"unsupported op: {op!r}")

    value = attrs.get(target_fy, {}).get(pred["attr"])
    if value is None:
        return Tri.UNKNOWN

    try:
        return Tri.TRUE if _OPS[op](value, pred["value"]) else Tri.FALSE
    except TypeError:
        # incomparable types = a data problem, surfaced not swallowed
        return Tri.UNKNOWN
