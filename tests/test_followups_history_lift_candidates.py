"""Follow-ups to the Race-Engineer remediation:

  A. Baseline history lift (Phase 9 extension) — the from-scratch base seeds
     personal-fit geometry (camber/toe) from the driver's STRONG proven setup
     instead of a neutral guess; safety diffs/aero/brakes/gearing are untouched.
  B. Candidate columns from the UI — the comparison table accepts caller-supplied
     base/race/quali columns alongside current/recommended/historical.
"""
from __future__ import annotations

import json

from strategy.setup_baseline import build_baseline_setup, _LABEL_HISTORY
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_history_intelligence import (
    build_baseline_seed_overrides, TIER_SAME_CAR_TRACK_LAYOUT, TIER_NEUTRAL,
)

_CAR = "Porsche 911 RSR (991) '17"


def _r():
    return resolve_ranges(_CAR)


# ============================================ A. seed-override selection

def test_strong_camber_prior_selected():
    prior = {"camber_front": {"value": 2.5, "tier": 1, "source": "Watkins"},
             "camber_rear": {"value": 2.1, "tier": 2, "source": "sim"}}
    ov = build_baseline_seed_overrides(prior)
    assert set(ov) == {"camber_front", "camber_rear"}
    assert ov["camber_front"]["value"] == 2.5


def test_weak_prior_excluded():
    prior = {"camber_front": {"value": 2.5, "tier": TIER_NEUTRAL, "source": "x"}}
    assert build_baseline_seed_overrides(prior) == {}


def test_non_lift_fields_excluded():
    # aero / brake / gearing / ride height must NEVER be lifted from history into
    # the base — they are track/strategy driven, not driver-fit.
    prior = {"aero_front": {"value": 999, "tier": 1, "source": "x"},
             "brake_bias": {"value": 5, "tier": 1, "source": "x"},
             "final_drive": {"value": 4.1, "tier": 1, "source": "x"},
             "ride_height_front": {"value": 60, "tier": 1, "source": "x"}}
    assert build_baseline_seed_overrides(prior) == {}


def test_proven_lsd_is_lifted():
    # Group 64: a STRONG proven same-car LSD triplet IS a valid starting window for
    # the base setup (the diff is a personal-fit lever); aero/brake alongside are not.
    prior = {"lsd_initial": {"value": 22, "tier": 1, "source": "Watkins"},
             "lsd_accel": {"value": 8, "tier": 2, "source": "sim"},
             "lsd_decel": {"value": 33, "tier": 1, "source": "Watkins"},
             "aero_front": {"value": 999, "tier": 1, "source": "x"}}
    ov = build_baseline_seed_overrides(prior)
    assert set(ov) == {"lsd_initial", "lsd_accel", "lsd_decel"}
    assert ov["lsd_initial"]["value"] == 22
    assert ov["lsd_decel"]["value"] == 33


def test_non_numeric_prior_ignored():
    prior = {"camber_front": {"value": "n/a", "tier": 1, "source": "x"}}
    assert build_baseline_seed_overrides(prior) == {}


# ============================================ A. lift applied in the base

def test_baseline_camber_lifted_to_proven():
    p, r = build_driver_profile(), _r()
    ov = {"camber_front": {"value": 2.5}, "camber_rear": {"value": 2.1}}
    base = build_baseline_setup(_CAR, r, "MR", 6, p, None, False)
    lift = build_baseline_setup(_CAR, r, "MR", 6, p, None, False,
                                historical_seed_overrides=ov)
    assert base["setup_fields"]["camber_front"] == 1.0     # neutral base
    assert lift["setup_fields"]["camber_front"] == 2.5     # lifted
    assert lift["setup_fields"]["camber_rear"] == 2.1


def test_lift_does_not_touch_aero():
    p, r = build_driver_profile(), _r()
    ov = {"camber_front": {"value": 2.5}}
    base = build_baseline_setup(_CAR, r, "MR", 6, p, None, False)
    lift = build_baseline_setup(_CAR, r, "MR", 6, p, None, False,
                                historical_seed_overrides=ov)
    assert base["setup_fields"]["aero_front"] == lift["setup_fields"]["aero_front"]


def test_lift_discloses_and_labels():
    p, r = build_driver_profile(), _r()
    ov = {"camber_front": {"value": 2.5}}
    lift = build_baseline_setup(_CAR, r, "MR", 6, p, None, False,
                                historical_seed_overrides=ov)
    assert "proven setup" in lift["analysis"]
    assert any(x["field"] == "camber_front" for x in lift["historical_lift"])
    _cf_change = next(c for c in lift["changes"] if c.get("field") == "camber_front")
    assert _cf_change.get("source_label") == _LABEL_HISTORY


def test_quali_bias_stacks_on_lifted_base():
    p, r = build_driver_profile(), _r()
    ov = {"camber_front": {"value": 2.5}}
    lift_q = build_baseline_setup(_CAR, r, "MR", 6, p, None, False,
                                  session_type="Qualifying",
                                  historical_seed_overrides=ov)
    # quali adds +0.5 camber_front on top of the proven 2.5 (clamped to range)
    lo, hi = r["camber_front"]
    assert lift_q["setup_fields"]["camber_front"] == min(3.0, hi)


def test_lift_clamped_to_range():
    p, r = build_driver_profile(), _r()
    lo, hi = r["camber_front"]
    ov = {"camber_front": {"value": hi + 10}}   # absurd proven value
    lift = build_baseline_setup(_CAR, r, "MR", 6, p, None, False,
                                historical_seed_overrides=ov)
    assert lift["setup_fields"]["camber_front"] <= hi


def test_no_overrides_is_a_plain_baseline():
    p, r = build_driver_profile(), _r()
    plain = build_baseline_setup(_CAR, r, "MR", 6, p, None, False)
    assert plain.get("historical_lift") == []
    assert "proven setup" not in plain["analysis"]


# ============================================ A. response path (liked history)

def _liked_setup(**vals):
    return {"name": _CAR, "track": "Watkins Glen", "layout_id": "full",
            "rating": "liked", "setup_label": "Watkins winner", **vals}


def _advisor():
    import tests.test_group41_validation_gate as G
    return G._make_full_advisor({}, [G._make_lap()])


def test_baseline_response_lifts_from_liked_history():
    adv = _advisor()
    hist = [_liked_setup(camber_front=2.5, camber_rear=2.1)]
    res = json.loads(adv.build_baseline_setup_response(
        _CAR, _r(), "MR", 6, None, False, session_type="Race",
        track_name="Watkins Glen", historical_setups=hist))
    assert res["setup_fields"]["camber_front"] == 2.5
    assert "proven setup" in res["analysis"]


def test_baseline_response_no_history_no_lift():
    adv = _advisor()
    res = json.loads(adv.build_baseline_setup_response(
        _CAR, _r(), "MR", 6, None, False, session_type="Race",
        track_name="Watkins Glen", historical_setups=[]))
    assert res["setup_fields"]["camber_front"] == 1.0
    assert res.get("historical_lift") == []


# ============================================ B. extra candidate columns

def test_extra_candidates_added_as_columns(monkeypatch):
    import strategy.driving_advisor as da
    adv = _advisor()
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"arb_front": 6, "arb_rear": 5, "aero_front": 400},
        car_name=_CAR, feeling="pushes wide in the middle of the corner",
        extra_candidates=[
            {"name": "race", "label": "Race setup", "source": "r", "values": {"arb_front": 6}},
            {"name": "quali", "label": "Quali setup", "source": "q", "values": {"arb_front": 5}},
            {"name": "base", "label": "Base", "source": "b", "values": {"arb_front": 7}},
        ]))
    names = [c["name"] for c in res["candidate_comparison"]["columns"]]
    assert "race" in names and "quali" in names and "base" in names


def test_malformed_extra_candidate_guarded(monkeypatch):
    import strategy.driving_advisor as da
    adv = _advisor()
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    # values missing / None -> must not crash, just no column
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"arb_front": 6, "aero_front": 400}, car_name=_CAR,
        feeling="pushes wide in the middle of the corner",
        extra_candidates=[{"name": "bad"}, {"name": "worse", "values": None}]))
    assert "candidate_comparison" in res
