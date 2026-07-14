"""Canonical SetupEngineeringContext tests (Engineering-Brain Phase 2).

Proves the ONE context bundles driver+car+track+event+evidence, derives a WORKING
WINDOW (range + provenance, not a forced value) per field via evidence precedence,
reports track confidence per capability, and separates current from historical feedback.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from strategy.setup_engineering_context import (
    build_working_window, build_working_windows, track_confidence_by_capability,
    feedback_state, build_setup_engineering_context, WorkingWindow, EVIDENCE_PRECEDENCE,
)
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile

_CAR = "Porsche 911 RSR (991) '17"


def _ranges():
    return resolve_ranges(_CAR)


# ------------------------------------------------------------------ working windows

def test_proven_value_narrows_window_with_provenance():
    prior = {"lsd_initial": {"value": 22, "tier": 1, "source": "Watkins"}}
    w = build_working_window("lsd_initial", _ranges(), prior)
    assert isinstance(w, WorkingWindow)
    assert w.preferred == 22
    lo, hi = _ranges()["lsd_initial"]
    assert lo <= w.low < 22 < w.high <= hi        # a band AROUND the proven value
    assert w.confidence == "high"                 # tier 1 = strong
    assert any("proven" in s for s in w.sources)


def test_similar_track_proven_is_medium():
    prior = {"lsd_accel": {"value": 8, "tier": 2, "source": "sim"}}
    assert build_working_window("lsd_accel", _ranges(), prior).confidence == "high"  # tier<=2 strong
    prior3 = {"lsd_accel": {"value": 8, "tier": 3, "source": "other track"}}
    assert build_working_window("lsd_accel", _ranges(), prior3).confidence == "medium"


def test_no_proven_value_is_full_range_low_confidence():
    w = build_working_window("arb_front", _ranges(), {})
    lo, hi = _ranges()["arb_front"]
    assert w.low == lo and w.high == hi and w.preferred is None
    assert w.confidence == "low"


def test_weak_prior_does_not_narrow():
    # A tier beyond same-car (>3) is not strong enough to move the window.
    prior = {"arb_front": {"value": 3, "tier": 6, "source": "neutral"}}
    w = build_working_window("arb_front", _ranges(), prior)
    assert w.preferred is None and w.confidence == "low"


def test_locked_field_collapses_window():
    w = build_working_window("aero_front", _ranges(), {}, locked=True, current_value=420)
    assert w.locked and w.low == w.high == 420 and w.confidence == "n/a"


def test_build_working_windows_covers_all_range_fields():
    ws = build_working_windows(_ranges(), {})
    assert len(ws) == len(_ranges())
    assert all(isinstance(w, WorkingWindow) for w in ws.values())


# ------------------------------------------------------------------ capability confidence

def test_track_confidence_by_capability():
    none = track_confidence_by_capability(None, None)
    assert none["setup_shaping"] == "none" and none["geometry"] == "none"
    tp = SimpleNamespace(trustworthy=True)
    cp = SimpleNamespace(available=True, confidence="medium")
    full = track_confidence_by_capability(tp, cp)
    assert full["setup_shaping"] == "medium" and full["geometry"] == "high"
    assert full["corner_detail"] == "medium"


# ------------------------------------------------------------------ feedback state

def test_feedback_state_separates_current_and_historical():
    diag = {"driver_feel_flags": {"mid_corner_understeer": True, "entry_balance_good": True}}
    prior = {"lsd_initial": {"value": 22, "tier": 1}}
    fb = feedback_state(diag, prior)
    assert fb["has_current_feedback"] and "mid_corner_understeer" in fb["current_problems"]
    assert "entry_balance_good" not in fb["current_problems"]   # "leave it", not a problem
    assert fb["has_proven_history"] and fb["proven_fields"] == ["lsd_initial"]


# ------------------------------------------------------------------ full context

def test_build_context_bundles_everything():
    prior = {"lsd_initial": {"value": 22, "tier": 1, "source": "Watkins"}}
    tp = SimpleNamespace(trustworthy=True, summary=lambda: "Fuji")
    cp = SimpleNamespace(available=True, confidence="medium", summary=lambda: "8 corners")
    ctx = build_setup_engineering_context(
        car=_CAR, objective="race", ranges=_ranges(), drivetrain="RR",
        profile=build_driver_profile(), track_profile=tp, corner_profile=cp,
        history_prior=prior,
        diagnosis={"driver_feel_flags": {"rear_loose_on_exit": True}})
    assert ctx.vehicle is not None and "rear-engined" in ctx.as_json()["vehicle"]
    assert ctx.window("lsd_initial").preferred == 22
    assert ctx.track_confidence["geometry"] == "high"
    assert ctx.feedback["current_problems"] == ["rear_loose_on_exit"]
    j = ctx.as_json()
    assert j["working_windows"] and j["evidence_precedence"] == list(EVIDENCE_PRECEDENCE)


def test_context_missing_evidence_is_honest():
    ctx = build_setup_engineering_context(
        car=_CAR, objective="base", ranges=_ranges(), drivetrain="RR",
        profile=build_driver_profile())   # no track, corner, history, specs-less
    miss = " ".join(ctx.missing_evidence)
    assert "track model" in miss and "per-corner" in miss and "history" in miss


# ------------------------------------------------------------------ integration

def test_engineering_context_surfaced_in_baseline_response():
    from strategy.driving_advisor import DrivingAdvisor
    adv = DrivingAdvisor(SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                                         best_lap=lambda: None), SimpleNamespace(), {})
    hist = [{"name": _CAR, "track": "Watkins Glen", "layout_id": "full", "rating": "liked",
             "setup_type": "Race", "lsd_initial": 22, "lsd_decel": 33}]
    r = json.loads(adv.build_baseline_setup_response(
        _CAR, _ranges(), "RR", 6, None, False, session_type="Race", duration_mins=45.0,
        track_name="Fuji", layout_id="full", historical_setups=hist))
    ec = r.get("engineering_context") or {}
    assert ec and "rear-engined" in ec.get("vehicle", "")
    assert ec.get("working_windows")
    assert ec["working_windows"]["lsd_initial"]["preferred"] == 22
