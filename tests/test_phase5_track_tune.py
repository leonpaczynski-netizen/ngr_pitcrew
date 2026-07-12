"""Phase 5 — track-specific base tune (track_tune_profile + baseline shaping).

Same car on two meaningfully different circuits produces different base tunes; a
long-straight track is NOT given max front aero; a missing track model discloses
and falls back conservatively; no track characteristics are invented.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.track_tune_profile import build_track_tune_profile
from strategy.setup_baseline import build_baseline_setup
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile

RSR = "Porsche 911 RSR (991) '17"


def _seed(length_m, corners, straight, elev=20):
    return SimpleNamespace(length_m=length_m, corners_expected=corners,
                           longest_straight_m=straight, elevation_change_m=elev)


# --------------------------------------------------- profile derivation

def test_straight_heavy_track_trims_aero():
    p = build_track_tune_profile("fuji", "full", seed_layout=_seed(4563, 16, 1475))
    assert p.trustworthy is True
    assert p.aero_bias == "trim"
    assert p.straight_fraction == round(1475 / 4563, 3)
    assert p.corner_density_per_km == round(16 / 4.563, 2)


def test_twisty_track_adds_aero():
    # Short, corner-dense, no long straight -> aero "add".
    p = build_track_tune_profile("tw", "l", seed_layout=_seed(2000, 16, 200))
    assert p.aero_bias == "add"


def test_balanced_track_neutral_aero():
    p = build_track_tune_profile("bal", "l", seed_layout=_seed(4000, 12, 600))
    assert p.aero_bias == "neutral"


def test_missing_model_not_trustworthy_and_neutral():
    p = build_track_tune_profile("x", "y", seed_layout=None, accepted_model=None)
    assert p.trustworthy is False
    assert p.aero_bias == "neutral"
    assert any("conservative" in n.lower() for n in p.notes)
    # No characteristics invented — all missing/unavailable.
    assert all((not c.available) for c in p.characteristics)


def test_accepted_model_overrides_seed_for_length_and_corners():
    seed = _seed(4600, 15, 1400)
    accepted = SimpleNamespace(lap_length_m_model=4563.0, model_corners_found=16)
    p = build_track_tune_profile("f", "l", seed_layout=seed, accepted_model=accepted)
    assert p.lap_length_m == 4563.0 and p.corner_count == 16
    src = {c.name: c.source for c in p.characteristics}
    assert src["lap_length_m"] == "accepted_model"
    assert src["corner_count"] == "accepted_model"


# --------------------------------------------------- baseline shaping

def _aero(track_profile=None, session="Race Setup"):
    r = resolve_ranges(RSR)
    sf = build_baseline_setup(RSR, r, "MR", 6, build_driver_profile(), None, False,
                              session_type=session, duration_mins=30,
                              track_profile=track_profile)["setup_fields"]
    return sf["aero_front"], sf["aero_rear"]


def test_baseline_never_pins_front_aero_to_max():
    # dislikes_floaty_front profile bias (+50) previously pinned aero_front to 450.
    af, _ = _aero(track_profile=None)
    lo, hi = resolve_ranges(RSR)["aero_front"]   # (350, 450)
    assert af < hi, "front aero must not be pinned to its ceiling by the profile nudge alone"


def test_straight_track_trims_below_neutral():
    fuji = build_track_tune_profile("fuji", "full", seed_layout=_seed(4563, 16, 1475))
    af_fuji, ar_fuji = _aero(track_profile=fuji)
    af_none, ar_none = _aero(track_profile=None)
    assert af_fuji < af_none and ar_fuji < ar_none, "straight-heavy track must trim aero"


def test_two_different_tracks_give_different_tunes():
    fuji = build_track_tune_profile("fuji", "full", seed_layout=_seed(4563, 16, 1475))   # trim
    twisty = build_track_tune_profile("tw", "l", seed_layout=_seed(2000, 16, 200))        # add
    assert _aero(track_profile=fuji) != _aero(track_profile=twisty)


def test_analysis_discloses_track_shaping():
    fuji = build_track_tune_profile("fuji", "full", seed_layout=_seed(4563, 16, 1475))
    r = resolve_ranges(RSR)
    res = build_baseline_setup(RSR, r, "MR", 6, build_driver_profile(), None, False,
                               session_type="Race Setup", duration_mins=30, track_profile=fuji)
    assert "Track-shaped" in res["analysis"]
