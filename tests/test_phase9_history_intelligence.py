"""Phase 9 — historical successful-setup intelligence.

Retrieves the driver's proven setup VALUES, scopes them by a hierarchy, builds a
transparent prior, and flags a recommendation that moves materially away from a
strong proven value. Encodes the known Watkins Porsche setup.
"""
from __future__ import annotations

from strategy.setup_history_intelligence import (
    find_historical_setups, build_historical_prior, compare_to_history,
    TIER_SAME_CAR_TRACK_LAYOUT, TIER_SAME_CAR_DISCIPLINE, TIER_SAME_CATEGORY_TRACK,
)

RSR = "Porsche 911 RSR (991) '17"

WATKINS = {
    "setup_label": "R Watkins winner", "name": RSR, "track": "Watkins Glen",
    "layout_id": "watkins__long", "setup_type": "Race", "rating": "liked",
    "lsd_initial": 22, "lsd_accel": 8, "lsd_decel": 33,
    "aero_front": 400, "aero_rear": 600, "arb_front": 7, "arb_rear": 7,
    "camber_front": 2.5, "camber_rear": 2.1,
}


def _setup(**over):
    base = dict(WATKINS)
    base.update(over)
    return base


# --------------------------------------------------- successful filter

def test_only_liked_setups_are_successful():
    liked = _setup(rating="liked")
    hated = _setup(setup_label="bad", rating="hated")
    neutral = _setup(setup_label="meh", rating="neutral")
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race",
                                 [liked, hated, neutral])
    assert len(res) == 1 and res[0].label == "R Watkins winner"


def test_result_quality_counts_as_successful():
    winner = _setup(rating="", result_quality="win")
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race", [winner])
    assert len(res) == 1


# --------------------------------------------------- scope hierarchy

def test_same_car_track_layout_is_tier_1():
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race", [WATKINS])
    assert res[0].scope_tier == TIER_SAME_CAR_TRACK_LAYOUT


def test_same_car_different_track_is_lower_tier():
    res = find_historical_setups(RSR, "Fuji", "fuji__full", "Race", [WATKINS])
    assert res and res[0].scope_tier == TIER_SAME_CAR_DISCIPLINE


def test_same_category_different_car_is_tier_4():
    other = _setup(name="Some Other Gr.3 Car", car_category="Gr.3")
    res = find_historical_setups("Different Gr.3 Car", "Watkins Glen", "watkins__long",
                                 "Race", [other], car_category="Gr.3")
    assert res and res[0].scope_tier == TIER_SAME_CATEGORY_TRACK


def test_unrelated_car_and_track_excluded():
    res = find_historical_setups("Mazda MX-5", "Suzuka", "suzuka__gp", "Race", [WATKINS])
    assert res == []


def test_stronger_scope_ranks_first():
    exact = _setup(setup_label="exact")
    other_track = _setup(setup_label="other", track="Spa", layout_id="spa__gp")
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race",
                                 [other_track, exact])
    assert res[0].label == "exact"   # tier 1 beats tier 3 despite later index


# --------------------------------------------------- prior + comparison

def test_prior_recovers_watkins_values():
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race", [WATKINS])
    prior = build_historical_prior(res)
    assert prior["lsd_accel"]["value"] == 8
    assert prior["lsd_initial"]["value"] == 22
    assert prior["lsd_decel"]["value"] == 33
    assert prior["camber_front"]["value"] == 2.5
    assert prior["aero_front"]["value"] == 400


def test_deviation_from_proven_lsd_is_flagged():
    # The UAT: recommending LSD accel 17 against the proven Watkins 8.
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race", [WATKINS])
    prior = build_historical_prior(res)
    rows = compare_to_history({"lsd_accel": 15}, {"lsd_accel": 17}, prior)
    lsd = next(r for r in rows if r.field == "lsd_accel")
    assert lsd.historical == 8 and lsd.recommended == 17
    assert lsd.deviation_flagged is True
    assert "proven" in lsd.note.lower()


def test_small_move_from_proven_not_flagged():
    res = find_historical_setups(RSR, "Watkins Glen", "watkins__long", "Race", [WATKINS])
    prior = build_historical_prior(res)
    rows = compare_to_history({"lsd_accel": 8}, {"lsd_accel": 9}, prior)  # +1 click
    lsd = next(r for r in rows if r.field == "lsd_accel")
    assert lsd.deviation_flagged is False


def test_history_never_forces_empty_prior():
    # No successful history -> empty prior -> no comparisons, nothing invented.
    prior = build_historical_prior([])
    assert prior == {}
    assert compare_to_history({"lsd_accel": 15}, {"lsd_accel": 17}, prior) == []


def test_response_attaches_historical_comparison(monkeypatch):
    # End-to-end: the setup response carries a current/historical comparison built
    # from the proven Watkins setup.
    import json
    import tests.test_group41_validation_gate as G
    import strategy.driving_advisor as da
    laps = [G._make_lap(wheelspin_count=12)]
    adv = G._make_full_advisor({}, laps)
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    setup = {"lsd_accel": 15, "aero_front": 400, "aero_rear": 600, "camber_front": 1.0}
    res = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name=RSR, track_name="Watkins Glen", purpose="Race",
        historical_setups=[WATKINS], feeling="Mid-Corner: Pushes wide"))
    hc = res.get("historical_comparison", [])
    lsd = next((r for r in hc if r["field"] == "lsd_accel"), None)
    assert lsd is not None and lsd["historical"] == 8 and lsd["current"] == 15
