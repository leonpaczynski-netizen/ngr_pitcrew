"""Car parameter model + class archetypes — UAT 2026-08-07 defects A5, A7.

Chunk 1 of the Phase 1 base-setup rebuild. These tests pin the data layer that
replaces "579 cars engineered as if they were the same car": per-field legal range,
preference window, anchor and step, each carrying the tier it came from.

The Gr.3 assertions are calibrated against evidence already in the repository —
the six vetted Porsche 911 RSR '17 setups in data/proven_setups.json and the four
curated windows in data/car_setup_ranges.json — not against invented numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.car_parameter_model import (
    TIER_ARCHETYPE, TIER_CAPTURED, TIER_GENERIC,
    CarParameterModel, resolve_archetype, resolve_parameter_model,
    save_car_capture, invalidate_cache, typical_gears_for_car,
)

_DATA = Path(__file__).resolve().parent.parent / "data"

GR3_CAR = "AMG Mercedes-AMG GT3 '20"
GR1_CAR = "Porsche 963 '24"
GR4_CAR = "Porsche Cayman GT4 Clubsport '16"
ROAD_CAR = "Toyota AE86 Levin D-Tuned"
GRB_CAR = "Ford Focus Gr.B Rally Car"


# ---------------------------------------------------------------------------
# Archetype resolution
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("car,expected", [
    (GR3_CAR, "gr3"),
    (GR1_CAR, "gr1"),
    (GR4_CAR, "gr4"),
    (ROAD_CAR, "road"),
    ("Porsche 911 RSR (991) '17", "gr3"),
])
def test_archetype_resolves_from_category(car, expected):
    assert resolve_archetype(car) == expected


def test_grb_detected_by_name_not_category():
    """GT7 files Gr.B rally cars under the Gr.4 category, so the name is the only
    signal. If this regresses, every rally car inherits GT4 ride height and springs."""
    specs = json.loads((_DATA / "car_specs.json").read_text(encoding="utf-8"))
    assert specs.get(GRB_CAR, {}).get("category") == "Gr.4", (
        "premise changed: car_specs no longer files this Gr.B car under Gr.4")
    assert resolve_archetype(GRB_CAR) == "grb"


def test_unknown_car_falls_back_to_road_and_never_raises():
    m = resolve_parameter_model("A Car That Does Not Exist")
    assert isinstance(m, CarParameterModel)
    assert m.archetype == "road"
    assert m.is_archetype_only is True


# ---------------------------------------------------------------------------
# The archetype file itself
# ---------------------------------------------------------------------------
def test_every_archetype_covers_every_generic_field():
    """An archetype that omits a field silently drops that field back to generic —
    the exact failure mode this layer exists to remove."""
    from strategy.setup_ranges import GENERIC_DEFAULTS
    data = json.loads((_DATA / "car_archetypes.json").read_text(encoding="utf-8"))
    for key, arch in data["archetypes"].items():
        missing = set(GENERIC_DEFAULTS) - set(arch["parameters"])
        assert not missing, f"archetype {key} is missing {sorted(missing)}"


def test_every_archetype_anchor_sits_inside_its_own_window():
    data = json.loads((_DATA / "car_archetypes.json").read_text(encoding="utf-8"))
    for key, arch in data["archetypes"].items():
        for field, spec in arch["parameters"].items():
            lo, hi = spec["window"]
            assert lo <= spec["anchor"] <= hi, (
                f"{key}.{field}: anchor {spec['anchor']} outside window {lo}..{hi}")


def test_every_archetype_declares_its_confidence_and_source():
    """An archetype interpolated from nothing (Gr.2, Gr.B) must not look as
    authoritative as one calibrated from six vetted setups (Gr.3)."""
    data = json.loads((_DATA / "car_archetypes.json").read_text(encoding="utf-8"))
    for key, arch in data["archetypes"].items():
        assert arch.get("confidence") in {"high", "medium", "low"}, key
        assert len(str(arch.get("source", ""))) > 40, f"{key} has no real source note"


def test_race_archetypes_run_more_front_camber_than_rear():
    """Front camber >= rear is the correct direction for every car that turns; the old
    NEUTRAL_SEEDS had it backwards (1.0 front / 1.5 rear)."""
    data = json.loads((_DATA / "car_archetypes.json").read_text(encoding="utf-8"))
    for key, arch in data["archetypes"].items():
        f = arch["parameters"]["camber_front"]["anchor"]
        r = arch["parameters"]["camber_rear"]["anchor"]
        assert f >= r, f"{key}: front camber {f} below rear {r}"


# ---------------------------------------------------------------------------
# Gr.3 anchors vs the proven library — the calibration that matters
# ---------------------------------------------------------------------------
def _proven_rsr_race() -> dict:
    setups = json.loads((_DATA / "proven_setups.json").read_text(encoding="utf-8"))["setups"]
    for s in setups:
        if s["discipline"] == "race" and "Monza" in s["track"]:
            return s["fields"]
    raise AssertionError("the vetted RSR Monza race setup is no longer in proven_setups.json")


@pytest.mark.parametrize("field,tolerance", [
    ("ride_height_front", 3),
    ("ride_height_rear", 4),
    ("springs_front", 0.3),
    ("springs_rear", 0.3),
    ("camber_front", 0.4),
    ("camber_rear", 0.4),
    ("aero_front", 40),
    ("aero_rear", 40),
])
def test_gr3_anchor_is_close_to_the_vetted_gr3_setup(field, tolerance):
    """The Gr.3 anchor must start near a setup Leon has actually validated on track.
    This is the whole point of the archetype: a from-scratch Gr.3 should begin roughly
    where a good Gr.3 ends up, not at the midpoint of a generic slider."""
    proven = _proven_rsr_race()
    anchor = resolve_parameter_model(GR3_CAR).spec(field).anchor
    assert abs(anchor - proven[field]) <= tolerance, (
        f"{field}: archetype anchor {anchor} vs vetted {proven[field]} "
        f"(tolerance {tolerance})")


def test_gr3_ride_height_lands_in_the_physically_sane_band():
    """UAT verification criterion. The old path produced 80mm from NEUTRAL_SEEDS and
    108mm from the synthesis midpoint walk; a Gr.3 runs 50-80."""
    m = resolve_parameter_model(GR3_CAR)
    for field in ("ride_height_front", "ride_height_rear"):
        assert 50 <= m.spec(field).anchor <= 80, field


def test_gr3_springs_land_in_the_class_band():
    """GT7's spring slider is not real-world natural frequency: a Gr.3 sits near
    3.0-5.0 here. The synthesis midpoint walk produced 13.4/14.9."""
    m = resolve_parameter_model(GR3_CAR)
    for field in ("springs_front", "springs_rear"):
        assert 3.0 <= m.spec(field).anchor <= 5.0, field


def test_no_archetype_anchor_is_pinned_to_a_legal_extreme():
    """A value sitting on its own legal boundary is a clamp artefact, not an
    engineering position (the old path pinned aero_rear to 800/800).

    Fields whose bounds come from car-specific data are exempt: the vetted Porsche
    RSR runs 55mm front, and its curated range floors at exactly 55, so the anchor
    landing on that floor is the right answer rather than a clamp artefact.
    """
    for car in (GR1_CAR, GR3_CAR, GR4_CAR, ROAD_CAR):
        m = resolve_parameter_model(car)
        for field in ("aero_front", "aero_rear", "springs_front", "springs_rear",
                      "ride_height_front", "ride_height_rear"):
            s = m.spec(field)
            if s.legal_tier in ("curated", TIER_CAPTURED):
                assert s.legal_low <= s.anchor <= s.legal_high, f"{car}.{field}"
                continue
            assert s.legal_low < s.anchor < s.legal_high, (
                f"{car}.{field}: anchor {s.anchor} pinned to legal "
                f"{s.legal_low}..{s.legal_high}")


def test_curated_per_car_range_is_not_widened_by_the_class_archetype():
    """A per-car entry is more specific than a class default even when it is only a
    preference window. The Gr.3 band floors at 50mm, but the RSR's own curated entry
    says 55 — and every vetted RSR setup runs 55, so the class must not override it."""
    s = resolve_parameter_model("Porsche 911 RSR (991) '17").spec("ride_height_front")
    assert (s.legal_low, s.legal_high) == (55, 80)
    assert s.legal_tier == "curated"
    assert s.window_low >= 55


# ---------------------------------------------------------------------------
# Legal range vs preference window — the separation defect A7 is about
# ---------------------------------------------------------------------------
def test_window_is_strictly_narrower_than_legal_for_shaped_fields():
    """If the window equals the legal range, walking half of it lands at 13 Hz springs.
    The two must be different objects with different widths."""
    m = resolve_parameter_model(GR3_CAR)
    for field in ("springs_front", "aero_rear", "camber_front", "toe_rear"):
        s = m.spec(field)
        assert s.window_span < s.legal_span, field


def test_generic_bounds_admit_values_already_run_in_gt7():
    """UAT 2026-08-07 defect A7. The generic table used to floor ride height at 60mm
    while every vetted Porsche RSR setup runs 55, and cap ARB at 7 while all four
    curated cars use 10 — bounds that vetoed the correct answer instead of bounding a
    wrong one. Both were corrected from that evidence."""
    from strategy.setup_ranges import GENERIC_DEFAULTS
    assert GENERIC_DEFAULTS["ride_height_front"][0] <= 45
    assert GENERIC_DEFAULTS["ride_height_rear"][0] <= 45
    assert GENERIC_DEFAULTS["arb_front"][1] >= 10
    assert GENERIC_DEFAULTS["arb_rear"][1] >= 10


def test_aero_generic_tuple_is_left_alone():
    """setup_diagnosis keys its _aero_range_is_generic guard off the exact (0, 1000)
    tuple. Widening it would change analyse-path behaviour Phase 1 is not fixing."""
    from strategy.setup_ranges import GENERIC_DEFAULTS
    assert GENERIC_DEFAULTS["aero_front"] == (0, 1000)
    assert GENERIC_DEFAULTS["aero_rear"] == (0, 1000)


def test_there_is_only_one_range_model():
    """Every archetype band must sit inside the generic clamp, so the parameter model
    never has to widen what a caller resolved. Two disagreeing range models is what
    made the validator reject the generator's own 52mm ride height as out of range."""
    from strategy.setup_ranges import GENERIC_DEFAULTS
    data = json.loads((_DATA / "car_archetypes.json").read_text(encoding="utf-8"))
    for key, arch in data["archetypes"].items():
        for field, spec in arch["parameters"].items():
            g_lo, g_hi = GENERIC_DEFAULTS[field]
            w_lo, w_hi = spec["window"]
            assert g_lo <= w_lo and w_hi <= g_hi, (
                f"{key}.{field}: window {w_lo}..{w_hi} escapes generic {g_lo}..{g_hi}")


def test_resolved_legal_range_matches_resolve_ranges_for_an_unmapped_car():
    """The model must not disagree with the table the validator reads."""
    from strategy.setup_ranges import resolve_ranges
    m = resolve_parameter_model(GR3_CAR)
    for field, (lo, hi) in resolve_ranges(GR3_CAR).items():
        s = m.spec(field)
        assert (s.legal_low, s.legal_high) == (lo, hi), field


def test_legal_ranges_shape_matches_resolve_ranges():
    """Callers pass model.legal_ranges() wherever they used to pass resolve_ranges()."""
    m = resolve_parameter_model(GR3_CAR)
    ranges = m.legal_ranges()
    assert set(ranges) == set(m.parameters)
    for lo, hi in ranges.values():
        assert lo <= hi


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def test_every_field_has_a_positive_step():
    m = resolve_parameter_model(GR3_CAR)
    for field, s in m.parameters.items():
        assert s.step > 0, field


@pytest.mark.parametrize("field,raw,expected", [
    ("springs_front", 3.47, 3.5),
    ("springs_front", 3.42, 3.4),
    ("camber_front", 2.53, 2.5),
    ("toe_rear", 0.117, 0.12),
    ("ride_height_front", 55.6, 56),
    ("arb_front", 5.4, 5),
])
def test_snap_rounds_to_the_step_grid(field, raw, expected):
    assert resolve_parameter_model(GR3_CAR).spec(field).snap(raw) == expected


def test_snap_never_escapes_the_legal_range():
    m = resolve_parameter_model(GR3_CAR)
    for field, s in m.parameters.items():
        for probe in (s.legal_low - 999, s.legal_high + 999, s.legal_high - 1e-9):
            assert s.legal_low <= s.snap(probe) <= s.legal_high, field


def test_steps_are_marked_assumed_not_gt7_truth():
    """Steps come from the app's own field precision, not observed GT7 increments.
    Presenting them as captured truth would be a new provenance lie."""
    m = resolve_parameter_model(GR3_CAR)
    assert all(s.step_tier == "assumed" for s in m.parameters.values())


# ---------------------------------------------------------------------------
# Drivetrain — defect A5
# ---------------------------------------------------------------------------
def test_drivetrain_is_resolved_for_every_path():
    """car_specs carries drivetrain for no car; the 527-entry curated file must be
    consulted here, not only on the two paths that already did."""
    assert resolve_parameter_model(GR3_CAR).drivetrain == "FR"
    assert resolve_parameter_model(GRB_CAR).drivetrain == "4WD"


def test_explicit_drivetrain_argument_wins():
    assert resolve_parameter_model(GR3_CAR, drivetrain="rr").drivetrain == "RR"


def test_unknown_drivetrain_stays_empty_and_is_not_invented():
    assert resolve_parameter_model("A Car That Does Not Exist").drivetrain == ""


# ---------------------------------------------------------------------------
# Gear count — defect A4's data half
# ---------------------------------------------------------------------------
def test_num_gears_is_zero_until_captured():
    """The class-typical gear count must never leak into num_gears: authoring a
    gearbox from a class assumption is defect A4 wearing a different hat."""
    m = resolve_parameter_model(GR3_CAR)
    assert m.num_gears == 0
    assert typical_gears_for_car(GR3_CAR) == 6      # available, but only for pre-fill


def test_redline_is_none_until_captured():
    assert resolve_parameter_model(GR3_CAR).redline_rpm is None


# ---------------------------------------------------------------------------
# Capture overrides — per field, partial entries usable
# ---------------------------------------------------------------------------
@pytest.fixture
def capture_store(tmp_path, monkeypatch):
    """Redirect the capture store to a temp file so tests never write user data."""
    import data.car_parameter_model as cpm
    path = tmp_path / "car_gt7_ranges.json"
    path.write_text(json.dumps({"schema": 1, "cars": {}}), encoding="utf-8")
    monkeypatch.setattr(cpm, "_CAPTURE_PATH", path)
    invalidate_cache()
    yield path
    invalidate_cache()


def test_captured_range_overrides_the_archetype(capture_store):
    assert save_car_capture(GR3_CAR, {
        "ranges": {"ride_height_front": {"min": 45, "max": 90, "step": 5}}})
    s = resolve_parameter_model(GR3_CAR).spec("ride_height_front")
    assert (s.legal_low, s.legal_high, s.step) == (45, 90, 5)
    assert s.legal_tier == TIER_CAPTURED
    assert s.step_tier == TIER_CAPTURED


def test_captured_stock_value_becomes_the_anchor(capture_store):
    save_car_capture(GR3_CAR, {"stock": {"springs_front": 4.2}})
    s = resolve_parameter_model(GR3_CAR).spec("springs_front")
    assert s.anchor == 4.2
    assert s.anchor_tier == TIER_CAPTURED


def test_a_partially_captured_car_still_uses_archetype_elsewhere(capture_store):
    """A car is not all-or-nothing: one captured field must not strand the rest."""
    save_car_capture(GR3_CAR, {"stock": {"springs_front": 4.2}})
    m = resolve_parameter_model(GR3_CAR)
    assert m.spec("springs_front").anchor_tier == TIER_CAPTURED
    assert m.spec("camber_front").anchor_tier == TIER_ARCHETYPE
    assert m.spec("camber_front").anchor == 2.5


def test_capture_flips_the_archetype_only_marker(capture_store):
    assert resolve_parameter_model(GR3_CAR).is_archetype_only is True
    save_car_capture(GR3_CAR, {"num_gears": 6})
    m = resolve_parameter_model(GR3_CAR)
    assert m.num_gears == 6
    assert m.is_archetype_only is False


def test_capture_merges_rather_than_replaces(capture_store):
    save_car_capture(GR3_CAR, {"stock": {"springs_front": 4.2}})
    save_car_capture(GR3_CAR, {"stock": {"camber_front": 3.0}, "num_gears": 6})
    m = resolve_parameter_model(GR3_CAR)
    assert m.spec("springs_front").anchor == 4.2
    assert m.spec("camber_front").anchor == 3.0
    assert m.num_gears == 6


def test_capture_matches_tolerantly_on_chassis_code(capture_store):
    save_car_capture("Porsche 911 RSR (991) '17", {"stock": {"springs_front": 3.9}})
    assert resolve_parameter_model("Porsche 911 RSR '17").spec("springs_front").anchor == 3.9


def test_save_rejects_junk_without_raising(capture_store):
    assert save_car_capture("", {"stock": {}}) is False
    assert save_car_capture(GR3_CAR, None) is False


def test_captured_window_is_clipped_into_a_captured_legal_range(capture_store):
    """When real data says the slider stops at 65, the archetype's 75 must not survive."""
    save_car_capture(GR3_CAR, {"ranges": {"ride_height_front": {"min": 50, "max": 65}}})
    s = resolve_parameter_model(GR3_CAR).spec("ride_height_front")
    assert s.legal_high == 65
    assert s.window_high <= 65


# ---------------------------------------------------------------------------
# Purity / serialisation
# ---------------------------------------------------------------------------
def test_model_is_json_serialisable():
    json.dumps(resolve_parameter_model(GR3_CAR).as_json())


def test_resolution_is_deterministic():
    a = resolve_parameter_model(GR3_CAR).as_json()
    b = resolve_parameter_model(GR3_CAR).as_json()
    assert a == b


def test_module_is_qt_free():
    """Checked against the source, not sys.modules — another test in the same session
    may already have imported PyQt6, which would make a sys.modules check pass for
    the wrong reason."""
    src = (Path(__file__).resolve().parent.parent
           / "data" / "car_parameter_model.py").read_text(encoding="utf-8")
    assert "PyQt" not in src and "QtCore" not in src
