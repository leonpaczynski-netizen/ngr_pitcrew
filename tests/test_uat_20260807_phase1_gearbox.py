"""Phase 1 chunk 6: a gearbox from evidence, or none at all — A4.

The old ``_build_gearbox_changes`` emitted the SAME geometric spread for every car in
the game — 3.800/2.558/1.722/1.159/0.780/0.525 with a final drive of 4.25 — from two
global constants, with no reference to the engine, the redline or the track. A gearbox
is the one part of a setup a driver cannot judge by feel from the sheet, so a
plausible-looking wrong answer there is worse than no answer at all.

Phase 0 stopped the orphan case (a final drive with no ratios attached). This is the
positive case, and its defining property is that it authors NOTHING far more often
than the old code did — no car in the repository has a redline or stock ratios until a
GT7 capture supplies them.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from data.car_parameter_model import (
    invalidate_cache, resolve_parameter_model, save_car_capture,
)
from strategy.setup_gearbox import (
    KEEP_STOCK_ADVICE, REQUIREMENTS, derive_gearbox,
)

GR3_CAR = "AMG Mercedes-AMG GT3 '20"
PROVEN_CAR = "Porsche 911 RSR '17"
MONZA = "Autodromo Nazionale Monza"

PROVEN_BOX = {"final_drive": 4.0, "gear_1": 2.98, "gear_2": 2.14, "gear_3": 1.66,
              "gear_4": 1.33, "gear_5": 1.09, "gear_6": 0.905}


def _measured_track(straight_m=1100.0):
    return SimpleNamespace(trustworthy=True, measured=True, straight_fraction=0.30,
                           corner_density_per_km=4.0, longest_straight_m=straight_m,
                           track_location_id="", layout_id="", summary=lambda: {})


@pytest.fixture
def capture_store(tmp_path, monkeypatch):
    import data.car_parameter_model as cpm
    path = tmp_path / "car_gt7_ranges.json"
    path.write_text(json.dumps({"schema": 1, "cars": {}}), encoding="utf-8")
    monkeypatch.setattr(cpm, "_CAPTURE_PATH", path)
    invalidate_cache()
    yield path
    invalidate_cache()


# ---------------------------------------------------------------------------
# The refusal — the normal case today
# ---------------------------------------------------------------------------
def test_no_evidence_authors_no_gearbox():
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track())
    assert plan.authored is False
    assert plan.ratios == {}
    assert plan.final_drive is None


def test_the_refusal_names_exactly_what_is_missing():
    """Authoring nothing is only acceptable if it is actionable."""
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track())
    assert set(plan.missing) == {"redline_rpm", "stock_ratios"}
    assert all(m in REQUIREMENTS for m in plan.missing)
    assert KEEP_STOCK_ADVICE.split(".")[0] in plan.advice
    assert "Capture" in plan.advice


def test_an_unmeasured_track_also_blocks_authoring():
    """A seeded lap length is not an observed straight."""
    seeded = SimpleNamespace(trustworthy=True, measured=False,
                             longest_straight_m=1100.0)
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=seeded)
    assert "longest_straight_m" in plan.missing


def test_a_direction_is_reported_but_never_converted_into_a_ratio():
    """The one thing knowable without a capture is which way the track leans. A
    direction is not a ratio and must not be dressed up as one."""
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track(), final_drive_lean=-0.8)
    assert plan.authored is False
    assert any("longer gearing" in r for r in plan.reasons)
    assert plan.ratios == {}


def test_no_global_constant_spread_survives_anywhere():
    """The specific numbers the register caught. If any of these reappear in an
    authored setup, the geometric spread is back."""
    from strategy.setup_baseline import build_baseline_setup
    from strategy.setup_ranges import resolve_ranges
    from tests.test_group44_baseline_generator import _neutral_profile
    raw = build_baseline_setup(GR3_CAR, resolve_ranges(GR3_CAR), "FR", 6,
                               _neutral_profile(), None, False)
    values = set(raw["setup_fields"].values())
    for banned in (3.8, 2.558, 1.722, 1.159, 0.78, 0.525, 4.25):
        assert banned not in values, f"the geometric spread value {banned} is back"


# ---------------------------------------------------------------------------
# The proven case — the strongest evidence there is
# ---------------------------------------------------------------------------
def test_a_proven_gear_set_is_used_verbatim():
    plan = derive_gearbox(car_model=resolve_parameter_model(PROVEN_CAR),
                          track_profile=_measured_track(),
                          proven_gearbox=PROVEN_BOX)
    assert plan.authored is True
    assert plan.final_drive == 4.0
    assert plan.ratios == {k: v for k, v in PROVEN_BOX.items() if k != "final_drive"}
    assert plan.gear_count == 6


def test_a_proven_final_drive_alone_does_not_become_a_gearbox():
    """Phase 0's finding: authoring a final drive with no ratios silently mismatches
    the car's stock gearing in the one direction the driver cannot diagnose."""
    plan = derive_gearbox(car_model=resolve_parameter_model(PROVEN_CAR),
                          track_profile=_measured_track(),
                          proven_gearbox={"final_drive": 3.9})
    assert plan.authored is True
    assert plan.final_drive == 3.9
    assert plan.ratios == {}
    assert "stock" in plan.advice.lower()


def test_proven_beats_everything_including_a_full_capture(capture_store):
    save_car_capture(PROVEN_CAR, {
        "redline_rpm": 8500,
        "stock": {f"gear_{i}": 3.0 - i * 0.3 for i in range(1, 7)}})
    plan = derive_gearbox(car_model=resolve_parameter_model(PROVEN_CAR),
                          track_profile=_measured_track(),
                          proven_gearbox=PROVEN_BOX)
    assert plan.source == "proven-setup library"
    assert plan.ratios["gear_1"] == 2.98


# ---------------------------------------------------------------------------
# The captured case — what a real capture unlocks
# ---------------------------------------------------------------------------
def test_a_full_capture_unlocks_authoring(capture_store):
    save_car_capture(GR3_CAR, {
        "redline_rpm": 8500,
        "stock": {"gear_1": 2.90, "gear_2": 2.10, "gear_3": 1.64,
                  "gear_4": 1.31, "gear_5": 1.07, "gear_6": 0.89},
        "ranges": {}})
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track())
    assert plan.authored is True
    assert plan.missing == ()
    assert plan.gear_count == 6


def test_a_capture_adjusts_the_stock_ratios_rather_than_replacing_them(capture_store):
    """A manufacturer's gearbox shape encodes more about the engine than anything
    derivable here, so it is scaled, never invented."""
    stock = {"gear_1": 2.90, "gear_2": 2.10, "gear_3": 1.64,
             "gear_4": 1.31, "gear_5": 1.07, "gear_6": 0.89}
    save_car_capture(GR3_CAR, {"redline_rpm": 8500, "stock": dict(stock)})
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track())
    assert plan.ratios == stock
    assert "stock ratios" in plan.source


def test_the_final_drive_scale_is_bounded(capture_store):
    """A track-shaping signal must never restructure a gearbox."""
    from strategy.setup_gearbox import _final_drive_scale
    for lean in (-100, -1, 0, 1, 100):
        assert 0.94 <= _final_drive_scale(lean) <= 1.06
    assert _final_drive_scale("junk") == 1.0
    assert _final_drive_scale(None) == 1.0


def test_the_top_speed_target_grows_with_the_straight():
    from strategy.setup_gearbox import _target_top_speed
    assert (_target_top_speed(300) < _target_top_speed(700)
            < _target_top_speed(1000) < _target_top_speed(1500))


def test_the_reasons_state_the_basis(capture_store):
    save_car_capture(GR3_CAR, {
        "redline_rpm": 8500,
        "stock": {f"gear_{i}": 3.0 - i * 0.3 for i in range(1, 7)}})
    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=_measured_track(1250))
    joined = " ".join(plan.reasons)
    assert "1250 m straight" in joined
    assert "8500 rpm" in joined


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------
def test_the_response_carries_the_gearbox_decision():
    from strategy.driving_advisor import DrivingAdvisor
    from strategy.setup_ranges import resolve_ranges
    advisor = DrivingAdvisor.__new__(DrivingAdvisor)
    advisor._db = None
    resp = json.loads(advisor.build_baseline_setup_response(
        GR3_CAR, resolve_ranges(GR3_CAR), "", 0, None, False, session_type="Race",
        car_class="Gr.3", track_profile=_measured_track(), track_name=MONZA))
    plan = resp["gearbox_plan"]
    assert plan["authored"] is False
    assert plan["missing"]
    assert "stock gearing" in plan["advice"]
    layers = {d["layer"] for d in resp["degradations"]["absent"]}
    assert "gearbox" in layers


def test_the_proven_car_still_gets_its_full_gearbox_end_to_end():
    from strategy.driving_advisor import DrivingAdvisor
    from strategy.setup_ranges import resolve_ranges
    advisor = DrivingAdvisor.__new__(DrivingAdvisor)
    advisor._db = None
    resp = json.loads(advisor.build_baseline_setup_response(
        PROVEN_CAR, resolve_ranges(PROVEN_CAR), "", 0, None, False,
        session_type="Race", car_class="Gr.3", track_profile=_measured_track(),
        track_name=MONZA))
    sf = resp["setup_fields"]
    for field, value in PROVEN_BOX.items():
        assert sf[field] == pytest.approx(value), field


def test_derive_gearbox_never_raises_on_junk():
    for kwargs in ({}, {"car_model": object()}, {"track_profile": object()},
                   {"proven_gearbox": {"gear_1": "x", "final_drive": None}},
                   {"final_drive_lean": "nonsense"}):
        assert derive_gearbox(**kwargs) is not None
