"""setup_synthesis as the PRIMARY authoring path (Engineering-Brain, confidence-gated).

Where the complete-setup synthesis has strong track-shaping evidence, its coupled
best-candidate value authors a NON-proven handling field — proven personal values are
never overridden, gearing/tyres/ECU stay with the baseline generator, and the merged
values pass the SAME validation + Apply gate. These tests cover the pure reconciler,
the change-merge helper, and the end-to-end firing through the real baseline path.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from strategy.setup_synthesis import (
    reconcile_synthesis_primary, SYNTHESIS_PRIMARY_FIELDS, _PRIMARY_MODERATION,
)
from strategy.driving_advisor import _apply_synthesis_primary


# ------------------------------------------------------------- fakes

def _win(low, high, preferred=None, locked=False):
    return SimpleNamespace(low=low, high=high, preferred=preferred, locked=locked)


def _ctx(windows, shaping="medium"):
    return SimpleNamespace(working_windows=windows,
                           track_confidence={"setup_shaping": shaping})


def _synth(values, provenance=None):
    best = SimpleNamespace(values=values, provenance=provenance or {})
    return SimpleNamespace(best=best)


# ------------------------------------------------------------- gating

def test_gate_closed_when_track_shaping_weak():
    windows = {"arb_front": _win(1, 10)}
    out = reconcile_synthesis_primary({"arb_front": 6}, _synth({"arb_front": 2}),
                                      _ctx(windows, shaping="none"))
    assert out["overrides"] == {}
    assert "too low" in out["reason"]


def test_no_candidate_returns_empty():
    out = reconcile_synthesis_primary({"arb_front": 6},
                                      SimpleNamespace(best=None), _ctx({}))
    assert out["overrides"] == {} and "no synthesis candidate" in out["reason"]


def test_proven_field_is_kept_never_overridden():
    windows = {"lsd_accel": _win(5, 60, preferred=20)}   # proven personal value
    out = reconcile_synthesis_primary({"lsd_accel": 20}, _synth({"lsd_accel": 55}),
                                      _ctx(windows))
    assert "lsd_accel" in out["kept_proven"]
    assert out["overrides"] == {}


def test_locked_field_skipped():
    windows = {"aero_front": _win(350, 450, locked=True)}
    out = reconcile_synthesis_primary({"aero_front": 400}, _synth({"aero_front": 450}),
                                      _ctx(windows))
    assert "aero_front" in out["skipped"] and out["overrides"] == {}


def test_no_directional_view_at_centre_skipped():
    windows = {"camber_front": _win(0.0, 6.0)}            # centre 3.0
    out = reconcile_synthesis_primary({"camber_front": 3.0}, _synth({"camber_front": 3.0}),
                                      _ctx(windows))
    assert "camber_front" in out["skipped"] and out["overrides"] == {}


def test_non_handling_field_never_authored():
    # final_drive is not in the handling domain — synthesis must not touch it.
    assert "final_drive" not in SYNTHESIS_PRIMARY_FIELDS
    windows = {"final_drive": _win(3.0, 5.0)}
    out = reconcile_synthesis_primary({"final_drive": 4.0}, _synth({"final_drive": 5.0}),
                                      _ctx(windows))
    assert out["overrides"] == {}


# ------------------------------------------------------------- override + moderation

def test_override_fires_and_is_moderated():
    # Full-range window, strong shaping, synthesis wants the max (10). The applied value
    # must be tempered toward centre, not the extreme.
    windows = {"arb_front": _win(1, 10)}                  # centre 5.5
    out = reconcile_synthesis_primary({"arb_front": 6}, _synth({"arb_front": 10},
                                      {"arb_front": "raised for stability"}),
                                      _ctx(windows))
    assert out["applied"] == ["arb_front"]
    v = out["overrides"]["arb_front"]
    # Moderated: centre + (10-5.5)*0.6 = 8.2 -> rounds to 8; strictly inside (6, 10).
    assert 6 < v < 10
    expected = round(5.5 + (10 - 5.5) * _PRIMARY_MODERATION)
    assert v == expected
    assert out["provenance"]["arb_front"] == "raised for stability"


def test_override_skipped_when_moderated_equals_baseline():
    # centre 5.5; synthesis 6 -> moderated 5.5+0.3=5.8 -> rounds to 6 == baseline -> skip.
    windows = {"arb_front": _win(1, 10)}
    out = reconcile_synthesis_primary({"arb_front": 6}, _synth({"arb_front": 6}),
                                      _ctx(windows))
    assert out["overrides"] == {}


# ------------------------------------------------------------- change-merge helper

def test_apply_synthesis_primary_reconciles_existing_change_row():
    raw = {"setup_fields": {"arb_front": 6, "final_drive": 4.0},
           "changes": [{"field": "arb_front", "from": "6", "to": "6", "to_clamped": 6,
                        "why": "baseline neutral"}]}
    _apply_synthesis_primary(raw, {"arb_front": 3}, {"arb_front": "softened for grip"})
    assert raw["setup_fields"]["arb_front"] == 3
    c = next(c for c in raw["changes"] if c["field"] == "arb_front")
    assert c["to"] == "3" and c["to_clamped"] == 3
    assert c["source_label"] == "complete-setup synthesis (primary)"
    assert "Synthesis-primary: softened for grip" in c["why"]
    assert raw["setup_fields"]["final_drive"] == 4.0   # untouched


def test_apply_synthesis_primary_appends_change_when_absent():
    raw = {"setup_fields": {"toe_rear": 0.1}, "changes": []}
    _apply_synthesis_primary(raw, {"toe_rear": 0.4}, {"toe_rear": "rear stability"})
    assert raw["setup_fields"]["toe_rear"] == 0.4
    c = raw["changes"][0]
    assert c["field"] == "toe_rear" and c["to_clamped"] == 0.4
    assert c["source_label"] == "complete-setup synthesis (primary)"


# ------------------------------------------------------------- end-to-end baseline path

def _advisor():
    from strategy.driving_advisor import DrivingAdvisor
    rec = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                          best_lap=lambda: None)
    return DrivingAdvisor(rec, SimpleNamespace(), {})


def _baseline(track_profile):
    from strategy.setup_ranges import resolve_ranges
    from tests.test_group63_setup_brain_uat2 import _CAR
    raw = _advisor().build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0, track_name="Fuji", layout_id="full",
        track_profile=track_profile, historical_setups=None)
    return json.loads(raw)


def test_thin_track_leaves_baseline_unchanged():
    # No track model (or untrustworthy) → gate closed → no synthesis override.
    d = _baseline(None)
    sp = d.get("synthesis_primary") or {}
    assert not sp.get("applied")


def test_trustworthy_track_makes_synthesis_primary_and_passes_gate():
    from strategy._setup_constants import APPROVED_STATUSES
    from strategy.setup_ranges import resolve_ranges
    from tests.test_group63_setup_brain_uat2 import _CAR
    tp = SimpleNamespace(trustworthy=True, straight_fraction=0.25,
                         corner_density_per_km=5.0)
    d = _baseline(tp)
    sp = d.get("synthesis_primary") or {}
    assert sp.get("applied")                                    # synthesis authored fields
    assert d.get("recommendation_status") in APPROVED_STATUSES  # survived the Apply gate
    # Every authored value lands inside the car's legal range (never an illegal extreme).
    rng = resolve_ranges(_CAR)
    sf = d.get("setup_fields") or {}
    for f in sp["applied"]:
        lo, hi = rng[f]
        assert lo <= float(sf[f]) <= hi
        assert f in SYNTHESIS_PRIMARY_FIELDS                    # handling domain only
