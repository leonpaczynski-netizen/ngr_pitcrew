"""Engineering Brain Phase 10 — change-consequences tests."""
import inspect

import pytest

from strategy import change_consequences as CC
from strategy.change_consequences import (
    ConsequenceKind, consequences_fingerprint, coupled_fields, derive_consequences,
)

CAND = {
    "field": "lsd_accel", "direction": "increase", "current_value": 20.0,
    "proposed_value": 25.0, "expected_positive_effect": "increases exit traction",
    "expected_negative_effects": ["may reduce power-oversteer resistance"],
    "window_relationship": "inside_window", "evidence_grade": "medium",
}
CONTEXT = {
    "transfers": [
        {"kind": "successful_experiment", "strength": "strong_match", "field": "lsd_accel",
         "direction": "increase", "detail": "resolved exit wheelspin",
         "supporting_sessions": ["300", "301"], "confirmed": True},
    ],
}


def test_coupled_fields_from_interaction_graph():
    coupled = coupled_fields("lsd_accel")
    others = {c[0] for c in coupled}
    # lsd_accel shares exit_traction / power_oversteer_resistance with rear fields
    assert "arb_rear" in others or "aero_rear" in others


def test_coupled_fields_empty_for_unknown_field():
    assert coupled_fields("nonexistent_field") == ()


def test_primary_side_historical_window_interaction():
    cons = derive_consequences(CAND, context=CONTEXT)
    kinds = {c.kind for c in cons}
    assert ConsequenceKind.PRIMARY_EFFECT.value in kinds
    assert ConsequenceKind.SIDE_EFFECT.value in kinds
    assert ConsequenceKind.HISTORICAL.value in kinds
    assert ConsequenceKind.WORKING_WINDOW.value in kinds
    assert ConsequenceKind.INTERACTION.value in kinds


def test_historical_references_evidence():
    cons = derive_consequences(CAND, context=CONTEXT)
    hist = [c for c in cons if c.kind == ConsequenceKind.HISTORICAL.value]
    assert hist and hist[0].supporting_sessions == ("300", "301")


def test_no_history_still_produces_primary():
    cons = derive_consequences(CAND, context={})
    assert any(c.kind == ConsequenceKind.PRIMARY_EFFECT.value for c in cons)
    assert not any(c.kind == ConsequenceKind.HISTORICAL.value for c in cons)


def test_deterministic():
    a = derive_consequences(CAND, context=CONTEXT)
    b = derive_consequences(CAND, context=CONTEXT)
    assert consequences_fingerprint(a) == consequences_fingerprint(b)


def test_module_is_pure():
    src = inspect.getsource(CC)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
