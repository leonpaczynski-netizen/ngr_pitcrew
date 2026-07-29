"""Tests for the proven-setup seed library and its baseline wiring.

The library lets the from-scratch baseline start from a vetted complete setup for an
exact car+track instead of generic class defaults (the deterministic equivalent of
recalling a known-good setup). Matching is by car (name/alias) + track (name/alias) +
discipline; a matched entry outranks the generic seeds and the personal-history lift.
"""
from __future__ import annotations

import pytest

from strategy.proven_setup_library import (
    find_proven_setup, split_seed_and_gearbox, load_proven_library,
)
from strategy.setup_baseline import build_baseline_setup, _LABEL_PROVEN, _LABEL_HISTORY
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import DriverProfile


def _neutral_profile() -> DriverProfile:
    return DriverProfile(
        profile_version="v1.0-test", style_tags=[], hard_constraints=[],
        prefers_rear_stability=False, dislikes_snap_exit=False, trail_braker=False,
        rotation_without_snap=False, prefers_front_bite=False, dislikes_floaty_front=False,
        protects_downforce=False, race_values_consistency=False,
    )


def _change(result: dict, field: str) -> dict:
    for c in result.get("changes", []):
        if c.get("field") == field:
            return c
    return {}


# ---------------------------------------------------------------------------
# Library lookup
# ---------------------------------------------------------------------------

def test_library_loads_the_seeded_entries():
    assert len(load_proven_library()) >= 6   # Monza/Watkins/Spa × quali+race


def test_find_matches_car_alias_and_discipline():
    f = find_proven_setup("Porsche 911 RSR (991) '17", "Autodromo Nazionale Monza", "Race")
    assert f and f["lsd_initial"] == 22 and f["aero_front"] == 390


def test_track_alias_and_endash_are_matched():
    # The event name uses an en-dash; the library entry uses a hyphen alias.
    f = find_proven_setup("Porsche 911 RSR '17",
                          "Watkins Glen International – Grand Prix", "Qualifying")
    assert f and f["aero_front"] == 430 and f["lsd_decel"] == 31
    # Short alias also resolves.
    assert find_proven_setup("Porsche 911 RSR '17", "Spa", "Race") is not None


def test_no_match_returns_none():
    assert find_proven_setup("Porsche 911 RSR '17", "Nurburgring", "Race") is None
    # Practice has no discipline-specific proven setup.
    assert find_proven_setup("Porsche 911 RSR '17", "Autodromo Nazionale Monza", "Practice") is None
    assert find_proven_setup("Mazda MX-5", "Autodromo Nazionale Monza", "Race") is None


def test_split_seed_and_gearbox():
    f = find_proven_setup("Porsche 911 RSR '17", "Autodromo Nazionale Monza", "Race")
    seed, gearbox = split_seed_and_gearbox(f)
    assert "springs_front" in seed and "gear_1" not in seed
    assert gearbox["final_drive"] == 4.0 and gearbox["gear_1"] == 2.98
    # Watkins has no gearbox in the library → empty gearbox half.
    _s, gb = split_seed_and_gearbox(
        find_proven_setup("Porsche 911 RSR '17", "Watkins Glen", "Race"))
    assert gb == {}


# ---------------------------------------------------------------------------
# Baseline wiring
# ---------------------------------------------------------------------------

def test_baseline_uses_proven_seed_and_labels_it():
    ranges = resolve_ranges("")
    fields = find_proven_setup("Porsche 911 RSR '17", "Autodromo Nazionale Monza", "Race")
    seed, gearbox = split_seed_and_gearbox(fields)
    result = build_baseline_setup(
        "", ranges, "MR", 6, _neutral_profile(), None, False,
        session_type="Race", proven_seed_overrides=seed, proven_gearbox=gearbox)

    sf = result["setup_fields"]
    assert sf["springs_front"] == 3.4          # from the library, not the 3.5 neutral seed
    assert sf["aero_front"] == 390
    assert _change(result, "springs_front")["why"] == _LABEL_PROVEN
    # Gearbox came from the library too.
    assert _change(result, "final_drive")["to_clamped"] == 4.0
    assert _change(result, "final_drive")["why"] == _LABEL_PROVEN
    assert _change(result, "gear_1")["to_clamped"] == 2.98


def test_proven_library_outranks_personal_history():
    ranges = resolve_ranges("")
    result = build_baseline_setup(
        "", ranges, "MR", 6, _neutral_profile(), None, False, session_type="Race",
        proven_seed_overrides={"camber_front": 2.4},
        historical_seed_overrides={"camber_front": {"value": 4.1}})
    # The vetted library value wins over the personal-history lift.
    assert result["setup_fields"]["camber_front"] == 2.4
    assert _change(result, "camber_front")["why"] == _LABEL_PROVEN
