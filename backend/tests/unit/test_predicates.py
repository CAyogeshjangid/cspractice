"""Tri-state predicate logic (Amendment A1 / spike G1, G8)."""
from __future__ import annotations

import pytest

from app.rules.predicates import Tri, evaluate

FY = 2026


def bag(**attrs):
    return {FY: attrs}


def test_empty_predicate_is_true() -> None:
    assert evaluate(None, bag(), FY) is Tri.TRUE
    assert evaluate({}, bag(), FY) is Tri.TRUE


def test_leaf_ops() -> None:
    p = {"attr": "paidup_capital", "op": "gte", "value": 50_000_000}
    assert evaluate(p, bag(paidup_capital=60_000_000), FY) is Tri.TRUE
    assert evaluate(p, bag(paidup_capital=1_000_000), FY) is Tri.FALSE


def test_missing_attribute_is_unknown_never_false() -> None:
    p = {"attr": "turnover", "op": "gte", "value": 1}
    assert evaluate(p, bag(), FY) is Tri.UNKNOWN
    assert evaluate(p, bag(turnover=None), FY) is Tri.UNKNOWN


def test_kleene_all() -> None:
    true = {"attr": "a", "op": "eq", "value": 1}
    unknown = {"attr": "missing", "op": "eq", "value": 1}
    false = {"attr": "a", "op": "eq", "value": 2}
    attrs = bag(a=1)
    assert evaluate({"all": [true, unknown]}, attrs, FY) is Tri.UNKNOWN
    assert evaluate({"all": [true, false, unknown]}, attrs, FY) is Tri.FALSE  # FALSE dominates
    assert evaluate({"all": [true, true]}, attrs, FY) is Tri.TRUE


def test_kleene_any() -> None:
    true = {"attr": "a", "op": "eq", "value": 1}
    unknown = {"attr": "missing", "op": "eq", "value": 1}
    false = {"attr": "a", "op": "eq", "value": 2}
    attrs = bag(a=1)
    assert evaluate({"any": [false, unknown]}, attrs, FY) is Tri.UNKNOWN
    assert evaluate({"any": [false, unknown, true]}, attrs, FY) is Tri.TRUE  # TRUE dominates
    assert evaluate({"any": [false, false]}, attrs, FY) is Tri.FALSE


def test_not_propagates_unknown() -> None:
    unknown = {"attr": "missing", "op": "eq", "value": 1}
    assert evaluate({"not": unknown}, bag(), FY) is Tri.UNKNOWN


def test_prior_fy_addressing() -> None:
    """CSR-style: applicability tests the PRECEDING FY's net worth (G8)."""
    p = {"attr": "net_worth", "op": "gte", "value": 5_000_000_000, "at": "fy-1"}
    attrs = {FY - 1: {"net_worth": 6_000_000_000}, FY: {"net_worth": 1}}
    assert evaluate(p, attrs, FY) is Tri.TRUE
    assert evaluate(p, {FY: {"net_worth": 6_000_000_000}}, FY) is Tri.UNKNOWN


def test_incomparable_types_are_unknown_not_crash() -> None:
    p = {"attr": "turnover", "op": "gte", "value": 100}
    assert evaluate(p, bag(turnover="not-a-number"), FY) is Tri.UNKNOWN


def test_malformed_predicate_raises() -> None:
    with pytest.raises(ValueError):
        evaluate({"bogus": []}, bag(), FY)
