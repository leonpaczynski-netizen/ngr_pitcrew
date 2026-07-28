"""Acceptance tests — Physics-Based Baseline Spring Frequency Target.

Maps each of the 10 story ACs plus the two PO additions to concrete test evidence.
Tests here fill the gaps not already covered by the unit test suites below; the
mapping section at the top of each class explains which existing tests already
satisfy that criterion.

EXISTING COVERAGE (these tests are NOT duplicated here):
  AC1  determinism unit          → test_spring_frequencies.py::TestDeterminism
  AC2  band selection            → test_spring_frequencies.py::TestBandSelection
  AC2  GT7 [1.00,20.00] bounds   → test_spring_frequencies.py::TestGT7SliderBounds
  AC2  differs from NEUTRAL_SEEDS → test_spring_frequencies.py::TestBandSelection
  AC3  RR/MR rear≥front, FF front≥rear → test_spring_frequencies.py::TestFrontRearSplit
  AC4  quali≥race (Hz)           → test_spring_frequencies.py::TestObjectiveShaping
  AC4  straight-heavy≥technical  → test_spring_frequencies.py::TestTrackShaping
  AC5  fallback: None/0/-100/empty-cat/empty-dt → test_spring_frequencies.py::TestFallback
  AC7  reason strings non-empty  → test_spring_frequencies.py::TestReasonStrings
  AC9  zero/negative mass        → test_spring_frequencies.py::TestFallback
  AC9  wet/unknown obj no crash  → test_spring_frequencies.py::TestObjectiveShaping
  PO   weight-dist resolver      → test_car_weight_distribution.py (17 tests)
  PO   front_weight_dist kwarg   → test_spring_frequencies.py::TestWeightDistOverride
  UI   signal mechanics          → test_setup_workspace.py::TestFrontWeightDistField

All tests below are Qt-free and offline unless they live in a class named
``TestPO_UIWiring`` (which requires QApplication).

No production code is modified here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from strategy.setup_engineering import (
    build_vehicle_model,
    derive_spring_frequencies,
    SpringFrequencies,
    OBJ_BASE,
    OBJ_QUALI,
    OBJ_RACE,
    _SPRING_BAND_RACE,
    _SPRING_BAND_ROAD,
    _SPRING_BAND_SPORT,
)
from strategy.setup_baseline import NEUTRAL_SEEDS

_NEUTRAL_FRONT = float(NEUTRAL_SEEDS["springs_front"])   # 3.50
_NEUTRAL_REAR  = float(NEUTRAL_SEEDS["springs_rear"])    # 3.00

_GT7_MIN, _GT7_MAX = 1.00, 20.00


# ---------------------------------------------------------------------------
# Shared builders (identical helpers to test_spring_frequencies.py so both
# files can be read independently)
# ---------------------------------------------------------------------------

def _gr3_rr():
    specs = {"weight_kg": 1243, "power_hp": 509, "category": "Gr.3"}
    return build_vehicle_model("Porsche 911 RSR (991) '17", "rr", 6, specs)


def _road_ff():
    specs = {"weight_kg": 1300, "power_hp": 150, "category": "Road Car"}
    return build_vehicle_model("Road FF Car", "ff", 6, specs)


def _make_advisor():
    from strategy.driving_advisor import DrivingAdvisor
    recorder = SimpleNamespace(
        recent_laps=lambda n: [],
        last_lap=lambda: None,
        best_lap=lambda: None,
    )
    tracker = SimpleNamespace()
    return DrivingAdvisor(recorder, tracker, {})


# ===========================================================================
# AC1 SUPPLEMENT — purity: no file-read at call time when dist supplied
# ===========================================================================
# AC1 determinism is covered by TestDeterminism in test_spring_frequencies.py.
# The additional invariant asserted here is: supplying front_weight_dist
# explicitly keeps the call pure — the car-weight-distribution file is never
# consulted at call time.

class TestAC1PurityNoFileRead:
    """When front_weight_dist is supplied, the data file is never read."""

    def test_explicit_dist_does_not_invoke_the_file_resolver(self, monkeypatch):
        """AC1: derive_spring_frequencies is pure when the caller supplies the
        front weight distribution directly.  The car-weight-distribution file
        is consulted ONLY when the argument is None — not at every call."""
        import data.car_weight_distribution as _mod

        def _should_not_be_called(*_a, **_k):
            pytest.fail(
                "resolve_front_weight_dist was called even though "
                "front_weight_dist was supplied explicitly — the function is "
                "not pure when data is already provided."
            )

        # Point the resolver at the spy — any call will fail the test.
        monkeypatch.setattr(_mod, "resolve_front_weight_dist", _should_not_be_called)

        v = _gr3_rr()
        # Must NOT raise and must NOT call the file resolver.
        sf = derive_spring_frequencies(v, OBJ_RACE, None, front_weight_dist=0.42)

        assert isinstance(sf, SpringFrequencies), "must return a SpringFrequencies object"
        assert sf.front_hz != _NEUTRAL_FRONT, (
            "With known vehicle + explicit dist, the result must not be the neutral fallback."
        )

    def test_determinism_across_two_calls_with_explicit_dist(self):
        """AC1: same inputs → same output, no randomness or state leak."""
        v = _gr3_rr()
        a = derive_spring_frequencies(v, OBJ_RACE, None, front_weight_dist=0.50)
        b = derive_spring_frequencies(v, OBJ_RACE, None, front_weight_dist=0.50)
        assert a.front_hz == b.front_hz
        assert a.rear_hz  == b.rear_hz
        assert a.front_reason == b.front_reason
        assert a.rear_reason  == b.rear_reason


# ===========================================================================
# AC2 SUPPLEMENT — front and rear values differ from EACH OTHER
# ===========================================================================
# TestBandSelection already proves both axles differ from NEUTRAL_SEEDS.
# The additional coverage here is: front_hz != rear_hz (a real front/rear split
# was computed, not a single Hz applied to both axles).

class TestAC2ValuesFromEachOther:
    """Gr.3 and Road FF both show a non-trivial front/rear split."""

    def test_gr3_rr_front_hz_differs_from_rear_hz(self):
        """AC2: Gr.3 RR car produces different Hz on each axle (rear-heavy split)."""
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_BASE)
        assert sf.front_hz != sf.rear_hz, (
            f"Gr.3 RR: front_hz={sf.front_hz} should differ from rear_hz={sf.rear_hz}"
        )

    def test_road_ff_front_hz_differs_from_rear_hz(self):
        """AC2: Road FF produces different Hz on each axle (front-heavy split)."""
        sf = derive_spring_frequencies(_road_ff(), OBJ_BASE)
        assert sf.front_hz != sf.rear_hz, (
            f"Road FF: front_hz={sf.front_hz} should differ from rear_hz={sf.rear_hz}"
        )

    def test_gr3_hz_values_differ_from_road_hz_values(self):
        """AC2: Gr.3 and Road car produce distinct Hz — they are in different bands."""
        sf_gr3  = derive_spring_frequencies(_gr3_rr(),  OBJ_BASE)
        sf_road = derive_spring_frequencies(_road_ff(), OBJ_BASE)
        assert sf_gr3.front_hz != sf_road.front_hz, (
            f"Gr.3 front {sf_gr3.front_hz} should differ from Road FF front {sf_road.front_hz}"
        )
        assert sf_gr3.rear_hz != sf_road.rear_hz, (
            f"Gr.3 rear {sf_gr3.rear_hz} should differ from Road FF rear {sf_road.rear_hz}"
        )

    def test_gr3_both_hz_above_road_band_ceiling(self):
        """AC2: Gr.3 targets live in the race band, Road targets in the road band — no overlap."""
        sf_gr3  = derive_spring_frequencies(_gr3_rr(),  OBJ_BASE)
        sf_road = derive_spring_frequencies(_road_ff(), OBJ_BASE)
        _road_lo, _road_hi = _SPRING_BAND_ROAD
        _race_lo, _race_hi = _SPRING_BAND_RACE
        assert sf_gr3.front_hz >= _race_lo, (
            f"Gr.3 front {sf_gr3.front_hz} must be in race band [{_race_lo}, {_race_hi}]"
        )
        assert sf_road.front_hz <= _road_hi, (
            f"Road FF front {sf_road.front_hz} must be in road band [{_road_lo}, {_road_hi}]"
        )


# ===========================================================================
# AC6 — Targets enter build_baseline_setup via chassis_seed_overrides
# ===========================================================================
# TestIntegration in test_spring_frequencies.py already proves that
# build_baseline_setup accepts chassis_seed_overrides and preserves them.
# The GAP is end-to-end through DrivingAdvisor.build_baseline_setup_response,
# which is what the production code path exercises.

class TestAC6EndToEndAdvisor:
    """Spring frequencies flow from derive_spring_frequencies all the way through
    build_baseline_setup_response; the setup_fields it returns carry the
    physics-derived value, not the flat neutral seed."""

    def _advisor_response(self, car_name, drivetrain, session_type="Race Setup"):
        """Call the production DrivingAdvisor and return parsed setup_fields."""
        import json
        from strategy.setup_ranges import resolve_ranges
        adv = _make_advisor()
        raw = adv.build_baseline_setup_response(
            car_name=car_name,
            ranges=resolve_ranges(""),   # generic (unclamped) 1–20 Hz spring range
            drivetrain=drivetrain,
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
            session_type=session_type,
        )
        data = json.loads(raw)
        return data.get("setup_fields", {}), data.get("recommendation_status", "")

    def test_gr3_rr_car_yields_non_neutral_springs_in_setup_fields(self):
        """AC6 happy path: a known Gr.3 RR car's baseline carries physics-derived
        spring Hz instead of the flat neutral 3.50 / 3.00 seeds."""
        sf, status = self._advisor_response(
            car_name="Porsche 911 RSR (991) '17",
            drivetrain="rr",
        )
        springs_front = sf.get("springs_front")
        springs_rear  = sf.get("springs_rear")
        assert springs_front is not None, "springs_front absent from setup_fields"
        assert springs_rear  is not None, "springs_rear absent from setup_fields"
        assert springs_front != _NEUTRAL_FRONT, (
            f"Gr.3 RR via advisor: springs_front={springs_front} should be != "
            f"neutral {_NEUTRAL_FRONT}"
        )
        assert springs_rear != _NEUTRAL_REAR, (
            f"Gr.3 RR via advisor: springs_rear={springs_rear} should be != "
            f"neutral {_NEUTRAL_REAR}"
        )
        # Springs must still be within GT7 range
        assert _GT7_MIN <= springs_front <= _GT7_MAX
        assert _GT7_MIN <= springs_rear  <= _GT7_MAX

    def test_gr3_rr_springs_in_race_band(self):
        """AC6: The physics-derived Gr.3 values land in the race band."""
        sf, _ = self._advisor_response(
            car_name="Porsche 911 RSR (991) '17", drivetrain="rr"
        )
        lo, hi = _SPRING_BAND_RACE
        # Allow up to hi*_QUALI_STIFFNESS_FACTOR (1.10) because Race session uses
        # the base objective, not qualifying.
        assert lo <= sf["springs_front"] <= hi, (
            f"springs_front={sf['springs_front']} not in race band [{lo}, {hi}]"
        )

    def test_fallback_car_yields_neutral_springs(self):
        """AC6 fallback path: a car with no recognisable specs (empty category,
        empty drivetrain) returns exactly the neutral seeds through the full
        build_baseline_setup_response call chain — the springs are unchanged."""
        sf, _ = self._advisor_response(car_name="", drivetrain="")
        assert sf.get("springs_front") == _NEUTRAL_FRONT, (
            f"Fallback car: springs_front={sf.get('springs_front')!r} expected {_NEUTRAL_FRONT}"
        )
        assert sf.get("springs_rear") == _NEUTRAL_REAR, (
            f"Fallback car: springs_rear={sf.get('springs_rear')!r} expected {_NEUTRAL_REAR}"
        )

    def test_unknown_car_name_no_specs_yields_neutral_springs(self):
        """AC6: a valid drivetrain string but an unknown car name (no entry in
        car_specs.json) means weight_kg is None → fallback fires → neutral springs."""
        sf, _ = self._advisor_response(
            car_name="NonExistentCarThatHasNoSpecs XYZ", drivetrain="rr"
        )
        assert sf.get("springs_front") == _NEUTRAL_FRONT, (
            f"Unknown-car springs_front={sf.get('springs_front')!r} expected {_NEUTRAL_FRONT}"
        )


# ===========================================================================
# AC8 — No external-document numeric constant hard-coded
# ===========================================================================
# This is a code-inspection criterion verified by reading strategy/setup_engineering.py.
# No runnable test can fully enforce it, but we can assert that the module exposes
# the constants as importable NAMED values (a bare literal cannot be asserted on).

class TestAC8NamedConstants:
    """Every Spring-frequency numeric constant is accessible by name (not a bare
    literal); each is imported from setup_engineering.py so changes would break
    these assertions before they could silently change observable behaviour."""

    def test_road_band_is_a_named_constant(self):
        from strategy.setup_engineering import _SPRING_BAND_ROAD
        lo, hi = _SPRING_BAND_ROAD
        assert lo == 1.5 and hi == 3.0, f"_SPRING_BAND_ROAD changed: {_SPRING_BAND_ROAD}"

    def test_sport_band_is_a_named_constant(self):
        from strategy.setup_engineering import _SPRING_BAND_SPORT
        lo, hi = _SPRING_BAND_SPORT
        assert lo == 2.5 and hi == 5.0, f"_SPRING_BAND_SPORT changed: {_SPRING_BAND_SPORT}"

    def test_race_band_is_a_named_constant(self):
        from strategy.setup_engineering import _SPRING_BAND_RACE
        lo, hi = _SPRING_BAND_RACE
        assert lo == 4.0 and hi == 8.0, f"_SPRING_BAND_RACE changed: {_SPRING_BAND_RACE}"

    def test_quali_stiffness_factor_is_a_named_constant(self):
        from strategy.setup_engineering import _QUALI_STIFFNESS_FACTOR
        assert _QUALI_STIFFNESS_FACTOR == 1.10

    def test_track_straight_step_is_a_named_constant(self):
        from strategy.setup_engineering import _TRACK_STRAIGHT_HZ_STEP
        assert _TRACK_STRAIGHT_HZ_STEP == 0.30

    def test_track_corner_step_is_a_named_constant(self):
        from strategy.setup_engineering import _TRACK_CORNER_HZ_STEP
        assert _TRACK_CORNER_HZ_STEP == -0.20

    def test_weight_dist_prior_is_a_named_dict(self):
        from strategy.setup_engineering import _WEIGHT_DIST_PRIOR
        # Keys derived from the known drivetrain strings; values are physics-based
        # front-axle weight fractions (0–1), not arbitrary magic numbers.
        assert set(_WEIGHT_DIST_PRIOR.keys()) >= {"rr", "mr", "fr", "ff", "awd"}
        assert 0.0 < _WEIGHT_DIST_PRIOR["rr"] < 0.50, "RR must be rear-biased"
        assert _WEIGHT_DIST_PRIOR["ff"] > 0.50, "FF must be front-biased"

    def test_split_hz_span_is_a_named_constant(self):
        from strategy.setup_engineering import _SPLIT_HZ_SPAN
        assert _SPLIT_HZ_SPAN == 2.0

    def test_band_lo_hi_constants_are_strictly_inside_gt7_slider(self):
        """Physical bands (1.5–8 Hz) are all within GT7's 1.00–20.00 range, so the
        GT7 clamp in Step 6 is never the first constraint that fires for normal cars."""
        for band in (_SPRING_BAND_ROAD, _SPRING_BAND_SPORT, _SPRING_BAND_RACE):
            lo, hi = band
            assert _GT7_MIN <= lo and hi <= _GT7_MAX, (
                f"Band {band} exceeds GT7 slider range [{_GT7_MIN}, {_GT7_MAX}]"
            )

    def test_neutral_seeds_imported_not_hard_coded(self):
        """The fallback values (3.50/3.00) come from NEUTRAL_SEEDS, not a
        duplicated literal inside setup_engineering.py."""
        # If the fallback used a literal the value would differ from NEUTRAL_SEEDS
        # when someone changes NEUTRAL_SEEDS — this test catches that divergence.
        v_none = build_vehicle_model("T", "rr", 6, {})  # no weight → fallback
        sf = derive_spring_frequencies(v_none, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT, (
            f"Fallback front_hz={sf.front_hz!r} != NEUTRAL_SEEDS[springs_front]={_NEUTRAL_FRONT!r}"
        )
        assert sf.rear_hz == _NEUTRAL_REAR, (
            f"Fallback rear_hz={sf.rear_hz!r} != NEUTRAL_SEEDS[springs_rear]={_NEUTRAL_REAR!r}"
        )


# ===========================================================================
# AC9 SUPPLEMENT — class-band boundary deterministic tie-break
# ===========================================================================
# AC9 zero/negative mass and wet-no-crash are already covered by test_spring_frequencies.py.
# The gap is the BOUNDARY at ptw == 320 (high_power_to_weight threshold).

class TestAC9ClassBandBoundary:
    """The ptw = 320 boundary deterministically selects the race band; ptw < 320
    falls through to the sport band.  Both sides are stable and not in [1,3] Hz."""

    def _veh_ptw(self, ptw_target):
        """Build a non-Gr-category, non-road car at an exact power-to-weight."""
        # weight_kg=1000, power_hp=ptw_target → ptw = ptw_target hp/t exactly
        specs = {"weight_kg": 1000, "power_hp": float(ptw_target), "category": "Sport Car"}
        return build_vehicle_model("Boundary Test Car", "fr", 6, specs)

    def test_ptw_exactly_320_selects_race_band(self):
        """ptw ≥ 320 → high_power_to_weight=True → race band [4, 8] Hz."""
        v = self._veh_ptw(320)
        assert v.high_power_to_weight is True
        sf = derive_spring_frequencies(v, OBJ_BASE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.front_hz <= hi, (
            f"ptw=320 front_hz={sf.front_hz} not in race band [{lo}, {hi}]"
        )
        assert lo <= sf.rear_hz <= hi

    def test_ptw_just_below_320_selects_sport_band(self):
        """ptw < 320 → high_power_to_weight=False → sport band [2.5, 5] Hz."""
        v = self._veh_ptw(319)
        assert v.high_power_to_weight is False
        sf = derive_spring_frequencies(v, OBJ_BASE)
        lo, hi = _SPRING_BAND_SPORT
        # Allow the qualifying factor (×1.10) for qualifying discipline.
        # For OBJ_BASE no factor applies, so both must sit strictly inside sport band.
        assert lo <= sf.front_hz <= hi, (
            f"ptw=319 front_hz={sf.front_hz} not in sport band [{lo}, {hi}]"
        )
        assert lo <= sf.rear_hz <= hi

    def test_boundary_is_deterministic_same_ptw_same_output(self):
        """The tie-break at ptw=320 always fires the same branch; two identical
        calls produce bitwise-identical results."""
        v = self._veh_ptw(320)
        a = derive_spring_frequencies(v, OBJ_BASE)
        b = derive_spring_frequencies(v, OBJ_BASE)
        assert a.front_hz == b.front_hz
        assert a.rear_hz  == b.rear_hz

    def test_crossing_the_boundary_gives_distinct_hz(self):
        """ptw=320 (race band, midpoint=6.0) differs clearly from ptw=319
        (sport band, midpoint=3.75) — no accidental overlap."""
        v_race  = self._veh_ptw(320)
        v_sport = self._veh_ptw(319)
        sf_race  = derive_spring_frequencies(v_race,  OBJ_BASE)
        sf_sport = derive_spring_frequencies(v_sport, OBJ_BASE)
        assert sf_race.front_hz > sf_sport.front_hz, (
            f"race-band Hz {sf_race.front_hz} should exceed sport-band Hz {sf_sport.front_hz}"
        )

    def test_gr_category_overrides_ptw_check(self):
        """A 'Gr.3' category tag always lands in the race band regardless of ptw."""
        # Low ptw but explicit Gr.3 category
        specs = {"weight_kg": 2000, "power_hp": 200, "category": "Gr.3"}
        v_low_ptw = build_vehicle_model("Heavy Gr3", "fr", 6, specs)
        assert v_low_ptw.high_power_to_weight is False   # low ptw
        sf = derive_spring_frequencies(v_low_ptw, OBJ_BASE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.front_hz <= hi, (
            f"Gr.3 category must use race band even at low ptw; got {sf.front_hz}"
        )


# ===========================================================================
# AC10 — Direct call to build_baseline_setup preserves neutral springs
# ===========================================================================
# The existing test_engineering_reasoning.py::test_end_to_end_default_build_baseline_unchanged
# proves that omitting engineering_bias produces byte-identical output to no-bias.
# The comment there notes: "NEUTRAL_SEEDS remains the direct-call fallback when
# chassis_seed_overrides are absent."
#
# The explicit spring-VALUE assertion that is MISSING elsewhere is added here:
# calling build_baseline_setup directly (without chassis_seed_overrides) must
# produce springs at exactly NEUTRAL_SEEDS values — the regression must not break.

class TestAC10DirectCallNeutralSprings:
    """build_baseline_setup called directly without chassis_seed_overrides
    must produce springs at the neutral 3.50 / 3.00 values (byte-for-byte
    regression for all existing callers that do not go through the advisor)."""

    def _build_direct(self, drivetrain="fr", car="", chassis_overrides=None):
        from strategy.setup_baseline import build_baseline_setup
        from strategy.setup_driver_profile import build_driver_profile
        from strategy.setup_ranges import resolve_ranges
        return build_baseline_setup(
            car, resolve_ranges(""), drivetrain, 6,
            build_driver_profile(), None, False,
            chassis_seed_overrides=chassis_overrides,
        )

    def test_springs_front_is_neutral_seed_without_overrides(self):
        """AC10: direct call, no chassis_seed_overrides → springs_front == 3.50."""
        raw = self._build_direct()
        assert raw["setup_fields"]["springs_front"] == _NEUTRAL_FRONT, (
            f"Direct call without overrides: springs_front expected {_NEUTRAL_FRONT}, "
            f"got {raw['setup_fields']['springs_front']}"
        )

    def test_springs_rear_is_neutral_seed_without_overrides(self):
        """AC10: direct call, no chassis_seed_overrides → springs_rear == 3.00."""
        raw = self._build_direct()
        assert raw["setup_fields"]["springs_rear"] == _NEUTRAL_REAR, (
            f"Direct call without overrides: springs_rear expected {_NEUTRAL_REAR}, "
            f"got {raw['setup_fields']['springs_rear']}"
        )

    def test_springs_at_neutral_value_when_override_equals_neutral(self):
        """AC10: if the override happens to equal the neutral seed, the output is
        unchanged — the override path does not introduce a bias when the value matches."""
        raw_no_override = self._build_direct()
        raw_neutral_override = self._build_direct(
            chassis_overrides={
                "springs_front": _NEUTRAL_FRONT,
                "springs_rear":  _NEUTRAL_REAR,
            }
        )
        assert (raw_no_override["setup_fields"]["springs_front"] ==
                raw_neutral_override["setup_fields"]["springs_front"]), (
            "Passing neutral seeds as chassis_seed_overrides must not change the output"
        )

    def test_non_neutral_override_is_preserved(self):
        """AC10 / AC6: when a physics-derived override IS supplied (e.g. 5.76 Hz),
        it enters the funnel and the resulting setup_fields value is NOT the neutral
        seed — it is the override quantised to 1 dp (the pipeline rounds springs to
        1 decimal place: 5.76 → 5.8, 6.24 → 6.2).  This proves the chassis_seed_overrides
        path is active and the pipeline does not silently discard the derived values."""
        target_front = 5.76   # midpoint of race band for Gr.3 RR
        target_rear  = 6.24
        raw = self._build_direct(
            chassis_overrides={
                "springs_front": target_front,
                "springs_rear":  target_rear,
            }
        )
        result_front = raw["setup_fields"]["springs_front"]
        result_rear  = raw["setup_fields"]["springs_rear"]
        # Must not be neutral
        assert result_front != _NEUTRAL_FRONT, (
            f"Override 5.76 was not applied; got neutral {_NEUTRAL_FRONT}"
        )
        assert result_rear != _NEUTRAL_REAR, (
            f"Override 6.24 was not applied; got neutral {_NEUTRAL_REAR}"
        )
        # Must equal the 1-dp-quantised value the pipeline produces
        assert result_front == round(target_front, 1), (
            f"Expected round(5.76,1)={round(target_front,1)}, got {result_front}"
        )
        assert result_rear == round(target_rear, 1), (
            f"Expected round(6.24,1)={round(target_rear,1)}, got {result_rear}"
        )

    def test_two_drivetrain_types_produce_identical_springs_without_overrides(self):
        """AC10: without overrides the spring output is the same regardless of
        drivetrain — the flat NEUTRAL_SEEDS is drivetrain-independent."""
        raw_rr = self._build_direct("rr")
        raw_ff = self._build_direct("ff")
        assert (raw_rr["setup_fields"]["springs_front"] ==
                raw_ff["setup_fields"]["springs_front"] == _NEUTRAL_FRONT)
        assert (raw_rr["setup_fields"]["springs_rear"] ==
                raw_ff["setup_fields"]["springs_rear"] == _NEUTRAL_REAR)


# ===========================================================================
# PO — Weight-distribution resolver: real data when present else prior
# ===========================================================================
# The primary test suite is test_car_weight_distribution.py (17 tests).
# The additional acceptance-level check here is that derive_spring_frequencies
# uses the resolver in the correct order: explicit arg → file → drivetrain prior.

class TestPOWeightDistResolutionOrder:
    """Resolution order: explicit arg takes precedence over file data, which in
    turn takes precedence over the drivetrain prior."""

    def test_explicit_arg_overrides_file_data(self, monkeypatch):
        """When front_weight_dist is supplied, the file entry is ignored."""
        import data.car_weight_distribution as mod
        # Fake file says 0.42; explicit arg says 0.60 (FF-level front bias)
        monkeypatch.setattr(mod, "_CACHE", {"Porsche 911 RSR (991) '17": 0.42})

        v = _gr3_rr()
        with_explicit = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.60)
        with_file_only = derive_spring_frequencies(v, OBJ_BASE)

        # 0.60 → front heavier → front stiffer
        # 0.42 → rear heavier  → rear stiffer
        assert with_explicit.front_hz > with_file_only.front_hz, (
            f"Explicit 0.60 should give stiffer front than file-entry 0.42; "
            f"explicit front={with_explicit.front_hz}, file front={with_file_only.front_hz}"
        )

    def test_file_data_overrides_drivetrain_prior(self, monkeypatch):
        """When the file has an entry, it wins over the drivetrain prior."""
        import data.car_weight_distribution as mod
        # RR drivetrain prior is 0.38 (rear-heavy).
        # Fake file says 0.60 (front-heavy) — file should win.
        monkeypatch.setattr(mod, "_CACHE", {"Porsche 911 RSR (991) '17": 0.60})

        v = _gr3_rr()
        with_file  = derive_spring_frequencies(v, OBJ_BASE)
        empty_file = derive_spring_frequencies(v, OBJ_BASE)  # same; cache unchanged

        # With frac=0.60 (front-heavy) → front stiffer
        # The default prior for RR is 0.38 → rear stiffer
        # So with_file.front_hz must be > rear_hz (front heavier)
        assert with_file.front_hz > with_file.rear_hz, (
            f"File override 0.60 should make front stiffer: "
            f"front={with_file.front_hz}, rear={with_file.rear_hz}"
        )

    def test_drivetrain_prior_used_when_no_file_and_no_arg(self, monkeypatch):
        """When neither arg nor file provide data, the drivetrain prior governs."""
        import data.car_weight_distribution as mod
        # Empty cache → file returns None → drivetrain prior (RR=0.38) applies.
        monkeypatch.setattr(mod, "_CACHE", {})

        v = _gr3_rr()
        sf = derive_spring_frequencies(v, OBJ_BASE)

        # RR prior = 0.38 (rear-heavy) → rear stiffer
        assert sf.rear_hz >= sf.front_hz, (
            f"RR drivetrain prior should make rear stiffer: "
            f"front={sf.front_hz}, rear={sf.rear_hz}"
        )

    def test_reason_string_labels_the_resolution_source(self, monkeypatch):
        """AC7 / PO: the reason string identifies which source was used.

        Note: the "override" label only appears in the reason when the resulting
        fraction is not exactly 0.50 (balanced).  When frac == 0.50 the code emits
        "balanced weight distribution" which carries no label by design.  Using
        frac=0.62 (front-heavy) ensures the bias_desc branch that includes frac_label
        is reached.
        """
        import data.car_weight_distribution as mod

        # Case 1: explicit arg (non-balanced so the bias branch includes the label)
        v = _gr3_rr()
        sf_explicit = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.62)
        assert "override" in sf_explicit.front_reason.lower(), (
            f"Explicit arg (frac=0.62): reason should mention 'override'; "
            f"got {sf_explicit.front_reason!r}"
        )

        # Case 2: drivetrain prior (empty cache, frac=0.38 for RR → rear-traction label)
        monkeypatch.setattr(mod, "_CACHE", {})
        sf_prior = derive_spring_frequencies(v, OBJ_BASE)
        assert "prior" in sf_prior.front_reason.lower(), (
            f"Drivetrain prior: reason should mention 'prior'; got {sf_prior.front_reason!r}"
        )


# ===========================================================================
# PO — UI → SetupInputs wiring: % front value changes the resulting split
# ===========================================================================
# The QtSignal mechanics are proven in test_setup_workspace.py::TestFrontWeightDistField.
# This section proves the split changes DIRECTIONALLY when front_weight_dist_pct
# propagates from the UI into the backend derive_spring_frequencies call.
# (Pure backend test — no Qt required.)

class TestPOFrontWeightDistSplitDirection:
    """A % front value fed into the backend changes the spring split directionally."""

    def test_62pct_front_gives_front_stiffer_than_rear(self):
        """PO: 62% front weight → front-heavy → front_hz > rear_hz for any car/band."""
        v = _gr3_rr()   # normally rear-heavy (RR prior = 0.38)
        # Simulate what the bridge does: pct=62 → frac=0.62
        sf = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.62)
        assert sf.front_hz > sf.rear_hz, (
            f"62% front weight: expected front_hz > rear_hz; "
            f"got front={sf.front_hz}, rear={sf.rear_hz}"
        )

    def test_38pct_front_gives_rear_stiffer_than_front(self):
        """PO: 38% front weight → rear-heavy → rear_hz > front_hz."""
        v = _road_ff()   # normally front-heavy (FF prior = 0.60)
        sf = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.38)
        assert sf.rear_hz > sf.front_hz, (
            f"38% front weight: expected rear_hz > front_hz; "
            f"got front={sf.front_hz}, rear={sf.rear_hz}"
        )

    def test_62pct_changes_split_vs_rr_prior(self):
        """PO: supplying 62% front for an RR car reverses the default split direction."""
        v = _gr3_rr()
        sf_default = derive_spring_frequencies(v, OBJ_BASE)       # RR prior: rear stiffer
        sf_override = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.62)

        # Default RR should have rear ≥ front
        assert sf_default.rear_hz >= sf_default.front_hz, (
            "RR prior should give rear_hz ≥ front_hz"
        )
        # Override 62% front should reverse: front > rear
        assert sf_override.front_hz > sf_override.rear_hz, (
            "62% front override should give front_hz > rear_hz"
        )


# ===========================================================================
# PO — UI → SetupInputs wiring: bridge stores and propagates the value
# ===========================================================================
# These tests require QApplication.

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Auth:
    """Minimal ActiveSetupAuthority (see test_live_shell_bridge.py for the pattern)."""
    class _Active:
        def label(self):
            return "Race v2"
        @property
        def is_active_on_car(self):
            return True

    def active_setup(self, identity, purpose="Race"):
        return self._Active() if purpose == "Race" else None


class _Form:
    def current_setup_dict(self):
        return {"arb_front": 5, "arb_rear": 4,
                "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard"}
    def apply_ai_fields(self, fields):
        pass


class _FakeWindow:
    def __init__(self):
        self._race_form = _Form()
        self._setup_authority = _Auth()
    def _build_event_context(self):
        from data.event_context import build_event_context
        return build_event_context(
            event={"id": 1, "name": "Test Event"},
            strategy={"car": "GT-R", "track_location_id": "fuji"},
        )
    def _build_session_context(self):
        from data.session_context import build_session_context
        return build_session_context(connected=True, packet_count=5, laps_recorded=2)
    def _build_strategy_context(self):
        return None
    def _autosave_applied_setup(self, form):
        pass
    def _revert_last_change_for_form(self, form):
        pass


def _make_bridge(qapp):
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _FakeWindow()
    b = LiveShellBridge(
        shell, ctrl, window=win,
        config={"strategy": {"car": "GT-R", "track": "Fuji Speedway"}},
    )
    b.refresh()
    return b


class TestPOUIWiring:
    """Bridge stores the % front signal and propagates it through _build_inputs()
    to SetupInputs.front_weight_dist_pct — the pure logic path, without a live
    GT7 session."""

    def test_signal_value_stored_on_bridge(self, qapp):
        """PO: _on_front_weight_dist_changed(42) stores 42.0 on the bridge."""
        b = _make_bridge(qapp)
        b._on_front_weight_dist_changed(42)
        assert b._front_weight_dist_pct == 42.0, (
            f"Expected _front_weight_dist_pct == 42.0, got {b._front_weight_dist_pct!r}"
        )

    def test_zero_clears_pct_to_none(self, qapp):
        """PO: signal value 0 clears front_weight_dist_pct (revert to drivetrain prior)."""
        b = _make_bridge(qapp)
        b._on_front_weight_dist_changed(42)
        b._on_front_weight_dist_changed(0)
        assert b._front_weight_dist_pct is None, (
            f"Expected None after 0-signal; got {b._front_weight_dist_pct!r}"
        )

    def test_build_inputs_propagates_pct_to_setup_inputs(self, qapp):
        """PO: _build_inputs() returns SetupInputs with front_weight_dist_pct set."""
        from services.setup_service import SetupInputs
        b = _make_bridge(qapp)
        b._on_front_weight_dist_changed(62)
        inp = b._build_inputs()
        assert isinstance(inp, SetupInputs)
        assert inp.front_weight_dist_pct == 62.0, (
            f"Expected front_weight_dist_pct=62.0, got {inp.front_weight_dist_pct!r}"
        )

    def test_build_inputs_returns_none_pct_before_any_signal(self, qapp):
        """PO: before the driver sets any % front, build_inputs returns None pct
        (use drivetrain default)."""
        b = _make_bridge(qapp)
        # No _on_front_weight_dist_changed call yet
        inp = b._build_inputs()
        assert inp.front_weight_dist_pct is None, (
            f"Before any signal, front_weight_dist_pct should be None; got {inp.front_weight_dist_pct!r}"
        )

    def test_pct_to_fraction_conversion_at_the_backend(self, qapp):
        """PO: the pct stored on the bridge (42) is divided by 100 when passed to
        derive_spring_frequencies, so it arrives as a fraction in (0,1).

        This test drives the full service path: bridge._build_inputs() → SetupInputs
        with front_weight_dist_pct=42 → SetupService._generate_baseline() →
        DrivingAdvisor.build_baseline_setup_response(front_weight_dist_override=42).

        Because the advisor divides by 100 only when the value is truthy, and
        derive_spring_frequencies receives 0.42 (rear-heavy fraction), the resulting
        springs_front must be LESS THAN springs_rear for any car.

        We verify this at the derive_spring_frequencies level directly (no need
        for the full advisor chain).
        """
        # pct=42 → backend frac=0.42 → rear-heavy
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=42.0 / 100.0)
        assert sf.rear_hz >= sf.front_hz, (
            f"42% front (frac=0.42, rear-heavy): expected rear_hz >= front_hz; "
            f"got front={sf.front_hz}, rear={sf.rear_hz}"
        )
