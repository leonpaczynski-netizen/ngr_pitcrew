"""Per-corner authoring tests (strategy/corner_profile).

Prove the setup engine reads the track's reviewed per-corner segments and shapes the
car to the ACTUAL corner character (tight/open mix, traction-limited exits, kerb load)
— honestly, as a geometric proxy, degrading to the corner-density behaviour when no
per-corner data exists.
"""
from __future__ import annotations

from strategy.corner_profile import (
    build_corner_profile, corner_profile_intents, CornerProfile,
)


def _corner(turn, start, apex, end, direction="left", stype="apex_zone"):
    return {"segment_type": stype, "turn_number": turn, "lap_progress_start": start,
            "lap_progress_mid": apex, "lap_progress_end": end, "direction": direction}


def _corner_set(widths):
    """Build entry+apex+exit segments for corners of the given (width) sizes."""
    segs = []
    p = 0.05
    for i, w in enumerate(widths):
        entry_w = w * 0.4
        exit_w = w * 0.6
        e0, apex, x1 = p, p + entry_w, p + w
        segs.append(_corner(i + 1, e0, apex, x1, stype="corner_entry"))
        segs.append(_corner(i + 1, e0, apex, x1, stype="apex_zone"))
        segs.append(_corner(i + 1, e0, apex, x1, stype="corner_exit"))
        p = x1 + 0.03
    return segs


# ------------------------------------------------------------------ character

def test_structure_parsed_but_tight_open_not_authored():
    # Corner structure is parsed (count, windows) but the weak tight/open window-width
    # proxy is NOT used to author suspension stiffness (honest: no speed data).
    segs = _corner_set([0.02, 0.02, 0.02, 0.02, 0.08])
    prof = build_corner_profile(segs, detection_confidence="high")
    assert prof.available and prof.corner_count == 5
    fields = {i["evidence"] for i in corner_profile_intents(prof, "race")}
    assert not any("tight_dominant" in e or "open_dominant" in e for e in fields)


def test_traction_limited_exits_add_rear_aero():
    # Corners with a much longer exit than entry window.
    segs = []
    p = 0.05
    for i in range(5):
        e0, apex, x1 = p, p + 0.01, p + 0.06   # entry 0.01, exit 0.05 (>1.25x)
        segs += [_corner(i + 1, e0, apex, x1, stype="corner_entry"),
                 _corner(i + 1, e0, apex, x1, stype="apex_zone"),
                 _corner(i + 1, e0, apex, x1, stype="corner_exit")]
        p = x1 + 0.03
    prof = build_corner_profile(segs, detection_confidence="high")
    assert prof.long_exit_fraction >= 0.6
    fields = {i["field"] for i in corner_profile_intents(prof, "race")}
    assert "aero_rear" in fields


# ------------------------------------------------------------------ kerb demand

def test_kerb_heavy_adds_ride_height_margin():
    kerbs = [{"segment_type": "kerb_or_bump_candidate", "lap_progress_start": 0.01 * i,
              "lap_progress_end": 0.01 * i + 0.02, "lap_progress_mid": 0.01 * i + 0.01}
             for i in range(12)]
    prof = build_corner_profile(kerbs, detection_confidence="high")
    # No corner structure, but kerb demand makes the profile usable.
    assert prof.available and prof.kerb_count == 12 and prof.kerb_heavy
    fields = {i["field"]: i for i in corner_profile_intents(prof, "race")}
    assert fields["ride_height_front"]["direction"] > 0     # margin over kerbs
    assert fields["springs_front"]["direction"] < 0         # compliance


# ------------------------------------------------------------------ honesty / degradation

def test_empty_segments_not_available():
    prof = build_corner_profile([], detection_confidence="high")
    assert prof.available is False
    assert corner_profile_intents(prof, "race") == []


def test_confidence_capped_and_labelled_proxy():
    prof = build_corner_profile(_corner_set([0.02, 0.08, 0.02, 0.08]),
                                detection_confidence="high")
    assert prof.confidence == "medium"                      # never "high" (it's a proxy)
    assert any("proxy" in n for n in prof.notes)
    # Low detection confidence → weaker moves.
    low = build_corner_profile(_corner_set([0.02, 0.02, 0.02, 0.08]),
                               detection_confidence="low")
    hi = build_corner_profile(_corner_set([0.02, 0.02, 0.02, 0.08]),
                              detection_confidence="high")
    lo_str = corner_profile_intents(low, "race")[0]["strength"]
    hi_str = corner_profile_intents(hi, "race")[0]["strength"]
    assert lo_str < hi_str


def test_direction_balance_counted():
    segs = (_corner_set([0.03, 0.03]) )
    # first two corners are "left" by default; flip second to right
    for s in segs:
        if s.get("turn_number") == 2:
            s["direction"] = "right"
    prof = build_corner_profile(segs, detection_confidence="high")
    assert prof.left_count == 1 and prof.right_count == 1


# ------------------------------------------------------------------ integration

def test_engineering_layer_uses_corner_profile():
    from strategy.setup_engineering import (
        build_vehicle_model, derive_engineering_intents,
    )
    from types import SimpleNamespace
    vm = build_vehicle_model("Porsche 911 RSR (991) '17", "rr", 6,
                             {"power_hp": 509, "weight_kg": 1243, "category": "Gr.3"})
    track = SimpleNamespace(trustworthy=True, straight_fraction=0.15,
                            corner_density_per_km=4.0, elevation_change_m=8)
    kerbs = [{"segment_type": "kerb_or_bump_candidate", "lap_progress_start": 0.01 * i,
              "lap_progress_end": 0.01 * i + 0.02, "lap_progress_mid": 0.01 * i + 0.01}
             for i in range(12)]
    cp = build_corner_profile(kerbs, detection_confidence="high")
    without = derive_engineering_intents(vm, track, "race", None)
    with_cp = derive_engineering_intents(vm, track, "race", None, corner_profile=cp)
    # The corner profile adds a kerb-driven ride-height intent the plain track lacks.
    assert with_cp.bias().get("ride_height_front", 0) > without.bias().get("ride_height_front", 0)
    assert any("Per-corner" in n for n in with_cp.notes)


def test_real_fuji_reviewed_segments_if_present():
    # Uses the loader against real (runtime) reviewed-segments files if they exist;
    # otherwise degrades honestly. Never fails on absence.
    from strategy.corner_profile import load_reviewed_segments
    segs = load_reviewed_segments("fuji_international_speedway",
                                  "fuji_international_speedway__full_course")
    prof = build_corner_profile(segs, detection_confidence="high")
    if segs:
        # If the model files are present, Fuji resolves real corners and/or kerbs.
        assert prof.available
    else:
        assert prof.available is False
