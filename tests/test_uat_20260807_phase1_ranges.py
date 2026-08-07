"""Phase 1 chunk 5: real (min, max, step) per parameter — A7.

Three separate problems in one defect:

  * range data was thin and internally contradictory — the generic ARB ceiling was 7
    while all four curated cars use 10, and the form capped ballast at 150 while the
    range table said 200;
  * no step/increment model existed anywhere. ``_round_for_field`` applied a fixed
    decimal precision globally and the form hard-coded every ``setSingleStep``, so the
    app could author a value the GT7 slider cannot land on;
  * legal range and preference window were the same object, which is what let a
    "walk half the window" move travel half of a generic slider.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from data.car_parameter_model import resolve_parameter_model, save_car_capture, invalidate_cache
from strategy.setup_ranges import GENERIC_DEFAULTS, resolve_ranges

GR3_CAR = "AMG Mercedes-AMG GT3 '20"


def _track():
    return SimpleNamespace(trustworthy=True, measured=True, straight_fraction=0.30,
                           corner_density_per_km=4.0, track_location_id="",
                           layout_id="", summary=lambda: {})


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
# Legal range vs preference window — different objects
# ---------------------------------------------------------------------------
def test_legal_and_window_are_separate_objects():
    m = resolve_parameter_model(GR3_CAR)
    for field in ("springs_front", "aero_rear", "ride_height_front", "camber_front"):
        s = m.spec(field)
        assert (s.legal_low, s.legal_high) != (s.window_low, s.window_high), field


def test_window_is_what_a_move_walks_not_the_legal_span():
    """A full-strength move travels half the preference band. Half of a generic
    1-20Hz spring range is 9.5Hz — that is what put 13.4Hz springs on a Gr.3."""
    s = resolve_parameter_model(GR3_CAR).spec("springs_front")
    assert s.window_span / 2 < 1.5
    assert s.legal_span / 2 > 8.0


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def test_every_field_has_a_step():
    for field, spec in resolve_parameter_model(GR3_CAR).parameters.items():
        assert spec.step > 0, field


def test_assumed_steps_match_the_apps_own_precision():
    """Until a car is captured the step IS the display precision, so snapping is a
    deliberate no-op: do nothing until we actually know the increment."""
    from strategy.setup_baseline import _round_for_field, _snap_to_step
    m = resolve_parameter_model(GR3_CAR)
    steps = m.steps()
    ranges = m.legal_ranges()
    for field, value in (("springs_front", 3.47), ("camber_front", 2.53),
                         ("toe_rear", 0.117), ("arb_front", 5.4),
                         ("aero_rear", 612.6)):
        assert _snap_to_step(field, value, ranges, steps) == _round_for_field(field, value)


def test_a_captured_step_actually_snaps(capture_store):
    """The step model earns its keep only once a real increment is known."""
    from strategy.setup_baseline import _snap_to_step
    save_car_capture(GR3_CAR, {
        "ranges": {"ride_height_front": {"min": 50, "max": 100, "step": 5}}})
    m = resolve_parameter_model(GR3_CAR)
    ranges, steps = m.legal_ranges(), m.steps()
    assert _snap_to_step("ride_height_front", 52, ranges, steps) == 50
    assert _snap_to_step("ride_height_front", 53, ranges, steps) == 55
    assert _snap_to_step("ride_height_front", 67, ranges, steps) == 65


def test_a_captured_step_reaches_the_authored_setup(capture_store):
    """End-to-end: the generator must not hand the driver a value the slider cannot
    reach."""
    from strategy.setup_authoring_pipeline import BaselineInputs, build_enriched_baseline
    save_car_capture(GR3_CAR, {
        "ranges": {"ride_height_front": {"min": 50, "max": 100, "step": 5},
                   "ride_height_rear": {"min": 50, "max": 100, "step": 5}}})
    fields = build_enriched_baseline(BaselineInputs(
        car=GR3_CAR, ranges=resolve_ranges(GR3_CAR), session_type="Race",
        track_profile=_track(), track_name="Monza")).setup_fields
    for field in ("ride_height_front", "ride_height_rear"):
        assert float(fields[field]) % 5 == 0, f"{field}={fields[field]} is off the 5mm grid"


def test_snap_never_escapes_the_legal_range(capture_store):
    from strategy.setup_baseline import _snap_to_step
    save_car_capture(GR3_CAR, {
        "ranges": {"ride_height_front": {"min": 52, "max": 97, "step": 5}}})
    m = resolve_parameter_model(GR3_CAR)
    ranges, steps = m.legal_ranges(), m.steps()
    for probe in (-500, 0, 51, 98, 5000):
        out = _snap_to_step("ride_height_front", probe, ranges, steps)
        assert 52 <= out <= 97, f"{probe} -> {out}"


def test_snap_falls_back_cleanly_with_no_step():
    from strategy.setup_baseline import _round_for_field, _snap_to_step
    assert _snap_to_step("springs_front", 3.47, {}, None) == _round_for_field("springs_front", 3.47)
    assert _snap_to_step("springs_front", 3.47, {}, {"springs_front": 0}) == 3.5
    assert _snap_to_step("springs_front", 3.47, {}, {"springs_front": "junk"}) == 3.5


# ---------------------------------------------------------------------------
# The internal contradictions
# ---------------------------------------------------------------------------
def test_generic_arb_agrees_with_every_curated_car():
    """The register's example: generic ARB 1-7 against 1-10 in all four curated cars."""
    curated = json.loads(
        (__import__("pathlib").Path("data/car_setup_ranges.json")).read_text(encoding="utf-8"))
    for car, params in curated.items():
        for field in ("arb_front", "arb_rear"):
            bounds = params.get(field)
            if not bounds:
                continue
            assert GENERIC_DEFAULTS[field][0] <= bounds["min"], (car, field)
            assert bounds["max"] <= GENERIC_DEFAULTS[field][1], (car, field)


def test_no_generic_bound_is_contradicted_by_every_curated_car():
    """A single car exceeding the generic default is fine — that is what a per-car
    override is FOR (the Porsche 963's rear wing genuinely reaches 1200 against a
    generic ceiling of 1000). A bound that EVERY curated car contradicts is different:
    it means the default itself is wrong, which is what the register found for ARB
    (generic 1-7 against 1-10 in all four) and ride height (floor 60 against a vetted
    55). Those are fixed; this guards against the next one."""
    curated = json.loads(
        (__import__("pathlib").Path("data/car_setup_ranges.json")).read_text(encoding="utf-8"))
    by_field: dict = {}
    for params in curated.values():
        for field, bounds in params.items():
            if isinstance(bounds, dict) and field in GENERIC_DEFAULTS:
                by_field.setdefault(field, []).append(bounds)

    wrong = []
    for field, entries in by_field.items():
        g_lo, g_hi = GENERIC_DEFAULTS[field]
        if all(b["min"] < g_lo for b in entries):
            wrong.append((field, "floor too high", g_lo, [b["min"] for b in entries]))
        if all(b["max"] > g_hi for b in entries):
            wrong.append((field, "ceiling too low", g_hi, [b["max"] for b in entries]))
    assert not wrong, f"generic bounds every curated car disagrees with: {wrong}"


def test_a_curated_override_wider_than_generic_still_resolves_coherently():
    """The 963's 800-1200 rear wing: the per-car entry is the legal range for that car,
    and the class window is clipped into it rather than fighting it."""
    s = resolve_parameter_model("Porsche 963 '24").spec("aero_rear")
    assert (s.legal_low, s.legal_high) == (800, 1200)
    assert s.legal_low <= s.window_low <= s.window_high <= s.legal_high
    assert s.legal_low <= s.anchor <= s.legal_high


# ---------------------------------------------------------------------------
# The form binds to the model rather than hard-coding a second copy
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def form():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.setup_form_widget import SetupFormWidget
    w = SetupFormWidget("Race", SimpleNamespace())
    yield w


@pytest.mark.parametrize("attr,field", [
    ("_setup_ballast_kg", "ballast_kg"),
    ("_setup_arb_f", "arb_front"),
    ("_setup_arb_r", "arb_rear"),
    ("_setup_rh_f", "ride_height_front"),
    ("_setup_rh_r", "ride_height_rear"),
    ("_setup_cam_f", "camber_front"),
    ("_setup_toe_f", "toe_front"),
])
def test_form_bounds_match_the_range_table(form, attr, field):
    """The form was a second hard-coded copy of the bounds, and it disagreed: ballast
    capped at 150 against 200 in the table, ARB at 7 against 10."""
    widget = getattr(form, attr)
    lo, hi = GENERIC_DEFAULTS[field]
    assert widget.minimum() == pytest.approx(lo)
    assert widget.maximum() == pytest.approx(hi)


def test_form_ballast_ceiling_is_no_longer_150(form):
    assert form._setup_ballast_kg.maximum() == 200.0


def test_form_step_comes_from_the_step_model(form):
    from data.car_parameter_model import _archetypes
    steps = _archetypes().get("steps") or {}
    assert form._setup_spr_f.singleStep() == pytest.approx(steps["springs_front"])
    assert form._setup_toe_f.singleStep() == pytest.approx(steps["toe_front"])
    assert form._setup_cam_f.singleStep() == pytest.approx(steps["camber_front"])


# ---------------------------------------------------------------------------
# The model reaches the response so the UI can bind to it
# ---------------------------------------------------------------------------
def test_response_carries_the_parameter_model():
    from strategy.driving_advisor import DrivingAdvisor
    advisor = DrivingAdvisor.__new__(DrivingAdvisor)
    advisor._db = None
    resp = json.loads(advisor.build_baseline_setup_response(
        GR3_CAR, resolve_ranges(GR3_CAR), "", 0, None, False, session_type="Race",
        car_class="Gr.3", track_profile=_track(), track_name="Monza"))
    pm = resp["parameter_model"]
    spec = pm["parameters"]["springs_front"]
    assert spec["legal"] != spec["window"]
    assert spec["step"] > 0
    assert pm["archetype"] == "gr3"
