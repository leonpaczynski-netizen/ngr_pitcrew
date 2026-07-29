"""Physics-based spring natural frequency target — derive_spring_frequencies.

Tests cover:
  - Band selection: Gr.3 → race band (4–8 Hz); Road FF → road band (1.5–3 Hz)
  - Both values differ from the NEUTRAL_SEEDS flat default (3.50 / 3.00)
  - Front/rear split invariants: RR/MR → rear_hz >= front_hz; FF → front_hz >= rear_hz
  - Objective shaping: qualifying >= race on the same car + track
  - Track shaping: straight-heavy >= technical
  - Fallback: weight_kg None/0/-100, category="" or drivetrain="" → exact neutral seeds
  - Wet/unknown objective → no crash
  - Determinism: same inputs twice → identical output
  - All outputs within GT7 slider bounds [1.00, 20.00]
  - Both reason strings non-empty
  - front_weight_dist override changes the split directionally
  - Integration: seeds flow through build_baseline_setup → springs_front != 3.50

All tests are Qt-free and offline (no network, no QApplication).
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
    _BALLAST_POS_FULL,
    _BALLAST_AUTHORITY,
    _BALLAST_FRAC_LO,
    _BALLAST_FRAC_HI,
)
from strategy.setup_baseline import NEUTRAL_SEEDS

_GT7_MIN, _GT7_MAX = 1.00, 20.00
_NEUTRAL_FRONT = float(NEUTRAL_SEEDS["springs_front"])  # 3.50
_NEUTRAL_REAR  = float(NEUTRAL_SEEDS["springs_rear"])   # 3.00


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _veh(drivetrain, weight, power=300.0, category="Sport Car"):
    specs = {"weight_kg": weight, "power_hp": power, "category": category}
    return build_vehicle_model("Test Car", drivetrain, 6, specs)


def _gr3_rr():
    specs = {"weight_kg": 1243, "power_hp": 509, "category": "Gr.3"}
    return build_vehicle_model("Porsche 911 RSR (991) '17", "rr", 6, specs)


def _fuji():
    """Straight-heavy track (straight_fraction=0.32 >= 0.22 threshold)."""
    return SimpleNamespace(
        trustworthy=True,
        straight_fraction=0.32,
        corner_density_per_km=3.5,
        elevation_change_m=40,
        aero_bias="trim",
    )


def _twisty():
    """Corner-dense track (corner_density_per_km=8.0 >= 6.0 threshold)."""
    return SimpleNamespace(
        trustworthy=True,
        straight_fraction=0.10,
        corner_density_per_km=8.0,
        elevation_change_m=8,
        aero_bias="add",
    )


# ---------------------------------------------------------------------------
# Band selection
# ---------------------------------------------------------------------------

class TestBandSelection:
    def test_gr3_car_front_in_race_band(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_RACE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.front_hz <= hi

    def test_gr3_car_rear_in_race_band(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_RACE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.rear_hz <= hi

    def test_gr3_car_base_both_in_race_band(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_BASE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.front_hz <= hi
        assert lo <= sf.rear_hz <= hi

    def test_road_ff_base_both_in_road_band(self):
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE)
        lo, hi = _SPRING_BAND_ROAD
        assert lo <= sf.front_hz <= hi
        assert lo <= sf.rear_hz <= hi

    def test_gr3_car_differs_from_neutral_front(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_BASE)
        assert sf.front_hz != _NEUTRAL_FRONT, (
            f"Gr.3 front_hz={sf.front_hz} should not equal neutral {_NEUTRAL_FRONT}"
        )

    def test_gr3_car_differs_from_neutral_rear(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_BASE)
        assert sf.rear_hz != _NEUTRAL_REAR, (
            f"Gr.3 rear_hz={sf.rear_hz} should not equal neutral {_NEUTRAL_REAR}"
        )

    def test_road_ff_differs_from_neutral_front(self):
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz != _NEUTRAL_FRONT

    def test_road_ff_differs_from_neutral_rear(self):
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.rear_hz != _NEUTRAL_REAR

    def test_high_ptw_non_gr_gets_race_band(self):
        # >320 hp/t → race band even without "Gr." prefix
        v = build_vehicle_model("Fast Road Car", "mr", 6,
                                {"weight_kg": 900, "power_hp": 400, "category": "Sport Car"})
        assert v.high_power_to_weight  # confirm fixture
        sf = derive_spring_frequencies(v, OBJ_BASE)
        lo, hi = _SPRING_BAND_RACE
        assert lo <= sf.front_hz <= hi
        assert lo <= sf.rear_hz <= hi


# ---------------------------------------------------------------------------
# Front/rear split invariants
# ---------------------------------------------------------------------------

class TestFrontRearSplit:
    def test_rr_rear_hz_gte_front_hz(self):
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.rear_hz >= sf.front_hz, (
            f"RR: expected rear_hz({sf.rear_hz}) >= front_hz({sf.front_hz})"
        )

    def test_mr_rear_hz_gte_front_hz(self):
        v = build_vehicle_model("MR Car", "mr", 6,
                                {"weight_kg": 1100, "power_hp": 300, "category": "Sport Car"})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.rear_hz >= sf.front_hz, (
            f"MR: expected rear_hz({sf.rear_hz}) >= front_hz({sf.front_hz})"
        )

    def test_ff_front_hz_gte_rear_hz(self):
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz >= sf.rear_hz, (
            f"FF: expected front_hz({sf.front_hz}) >= rear_hz({sf.rear_hz})"
        )


# ---------------------------------------------------------------------------
# Objective shaping
# ---------------------------------------------------------------------------

class TestObjectiveShaping:
    def test_quali_front_hz_gte_race_same_car(self):
        v = _gr3_rr()
        race  = derive_spring_frequencies(v, OBJ_RACE)
        quali = derive_spring_frequencies(v, OBJ_QUALI)
        assert quali.front_hz >= race.front_hz, (
            f"quali.front_hz={quali.front_hz} should be >= race.front_hz={race.front_hz}"
        )

    def test_quali_rear_hz_gte_race_same_car(self):
        v = _gr3_rr()
        race  = derive_spring_frequencies(v, OBJ_RACE)
        quali = derive_spring_frequencies(v, OBJ_QUALI)
        assert quali.rear_hz >= race.rear_hz

    def test_quali_front_hz_gte_race_same_car_and_track(self):
        v = _gr3_rr()
        race  = derive_spring_frequencies(v, OBJ_RACE, _fuji())
        quali = derive_spring_frequencies(v, OBJ_QUALI, _fuji())
        assert quali.front_hz >= race.front_hz

    def test_wet_objective_no_crash(self):
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, "wet")
        assert isinstance(sf, SpringFrequencies)

    def test_unknown_objective_no_crash(self):
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, "")
        assert isinstance(sf, SpringFrequencies)

    def test_none_objective_no_crash(self):
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, None)  # type: ignore[arg-type]
        assert isinstance(sf, SpringFrequencies)


# ---------------------------------------------------------------------------
# Track shaping
# ---------------------------------------------------------------------------

class TestTrackShaping:
    def test_straight_heavy_front_gte_technical(self):
        v = _gr3_rr()
        straight  = derive_spring_frequencies(v, OBJ_BASE, _fuji())
        technical = derive_spring_frequencies(v, OBJ_BASE, _twisty())
        # straight adds +0.30, technical adds -0.20 → straight > technical
        assert straight.front_hz > technical.front_hz

    def test_straight_heavy_rear_gte_technical(self):
        v = _gr3_rr()
        straight  = derive_spring_frequencies(v, OBJ_BASE, _fuji())
        technical = derive_spring_frequencies(v, OBJ_BASE, _twisty())
        assert straight.rear_hz > technical.rear_hz

    def test_no_track_no_crash(self):
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, OBJ_BASE, None)
        assert isinstance(sf, SpringFrequencies)

    def test_untrusted_track_ignored(self):
        v = _gr3_rr()
        untrusted = SimpleNamespace(trustworthy=False, straight_fraction=0.99)
        no_track  = derive_spring_frequencies(v, OBJ_BASE, None)
        with_bad  = derive_spring_frequencies(v, OBJ_BASE, untrusted)
        assert with_bad.front_hz == no_track.front_hz
        assert with_bad.rear_hz  == no_track.rear_hz


# ---------------------------------------------------------------------------
# Fallback: insufficient data → exact NEUTRAL_SEEDS
# ---------------------------------------------------------------------------

class TestFallback:
    def test_weight_kg_none_returns_neutral_seeds_no_exception(self):
        # No specs → weight_kg is None
        v = build_vehicle_model("T", "rr", 6, {"category": "Gr.3", "power_hp": 400})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_weight_kg_zero_returns_neutral_seeds_no_exception(self):
        v = build_vehicle_model("T", "rr", 6,
                                {"category": "Gr.3", "power_hp": 400, "weight_kg": 0})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_weight_kg_negative_returns_neutral_seeds_no_exception(self):
        v = build_vehicle_model("T", "rr", 6,
                                {"category": "Gr.3", "power_hp": 400, "weight_kg": -100})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_category_empty_returns_neutral_seeds(self):
        v = build_vehicle_model("T", "rr", 6,
                                {"weight_kg": 1200, "power_hp": 400, "category": ""})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_drivetrain_empty_returns_neutral_seeds(self):
        # build_vehicle_model with empty drivetrain → vehicle.drivetrain == ""
        v = build_vehicle_model("T", "", 6,
                                {"weight_kg": 1200, "power_hp": 400, "category": "Gr.3"})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_no_specs_at_all_returns_neutral_seeds_no_exception(self):
        v = build_vehicle_model("T", "fr", 6, {})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT
        assert sf.rear_hz  == _NEUTRAL_REAR

    def test_unrecognised_nonempty_drivetrain_no_data_returns_neutral(self, monkeypatch):
        """AC5 regression: a non-empty but unrecognised drivetrain (e.g. 'hev')
        with no explicit override and no car-data entry must return the NEUTRAL_SEEDS
        fallback — NOT a 50:50 sport-band Hz (the pre-fix silent 0.50 default)."""
        import data.car_weight_distribution as _wd
        # Empty cache so the file resolver also returns None.
        monkeypatch.setattr(_wd, "_CACHE", {})
        # "hev" is not in _WEIGHT_DIST_PRIOR; weight/category are valid so Step 1 passes.
        v = build_vehicle_model("Hybrid Test Car", "hev", 6,
                                {"weight_kg": 1400, "power_hp": 300, "category": "Sport Car"})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_hz == _NEUTRAL_FRONT, (
            f"Unrecognised drivetrain 'hev': expected neutral front {_NEUTRAL_FRONT}; "
            f"got {sf.front_hz}"
        )
        assert sf.rear_hz == _NEUTRAL_REAR, (
            f"Unrecognised drivetrain 'hev': expected neutral rear {_NEUTRAL_REAR}; "
            f"got {sf.rear_hz}"
        )
        assert "fallback" in sf.front_reason.lower() or "neutral" in sf.front_reason.lower(), (
            f"Reason should mention 'fallback' or 'neutral'; got {sf.front_reason!r}"
        )


# ---------------------------------------------------------------------------
# Safety bounds [1.00, 20.00]
# ---------------------------------------------------------------------------

class TestGT7SliderBounds:
    def test_all_outputs_within_gt7_slider(self):
        fixtures = [
            ("rr", "Gr.3",       1243, 509),
            ("ff", "Road Car",   1300, 150),
            ("mr", "Gr.1",        900, 800),
            ("fr", "Sport Car",  1500, 300),
            ("awd", "Gr.4",      1400, 400),
        ]
        tracks = [None, _fuji(), _twisty()]
        for dt, cat, w, p in fixtures:
            v = build_vehicle_model("T", dt, 6,
                                    {"weight_kg": w, "power_hp": p, "category": cat})
            for obj in [OBJ_BASE, OBJ_QUALI, OBJ_RACE]:
                for trk in tracks:
                    sf = derive_spring_frequencies(v, obj, trk)
                    assert _GT7_MIN <= sf.front_hz <= _GT7_MAX, (
                        f"{dt}/{cat}/{obj}/track={trk}: front_hz={sf.front_hz} out of GT7 range"
                    )
                    assert _GT7_MIN <= sf.rear_hz <= _GT7_MAX, (
                        f"{dt}/{cat}/{obj}/track={trk}: rear_hz={sf.rear_hz} out of GT7 range"
                    )


# ---------------------------------------------------------------------------
# Reason strings
# ---------------------------------------------------------------------------

class TestReasonStrings:
    def test_both_reason_strings_non_empty_gr3(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_RACE)
        assert sf.front_reason, "front_reason must not be empty"
        assert sf.rear_reason,  "rear_reason must not be empty"

    def test_both_reason_strings_non_empty_road_ff(self):
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert sf.front_reason, "front_reason must not be empty"
        assert sf.rear_reason,  "rear_reason must not be empty"

    def test_reason_contains_band_name(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_RACE)
        assert "gr." in sf.front_reason.lower() or "race" in sf.front_reason.lower()

    def test_reason_contains_drivetrain(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_BASE)
        assert "rr" in sf.front_reason.lower()

    def test_quali_reason_mentions_stiffened(self):
        sf = derive_spring_frequencies(_gr3_rr(), OBJ_QUALI)
        assert "qualifying" in sf.front_reason.lower() or "stiffened" in sf.front_reason.lower()

    def test_fallback_reason_mentions_fallback(self):
        v = build_vehicle_model("T", "fr", 6, {})
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert "fallback" in sf.front_reason.lower() or "neutral" in sf.front_reason.lower()


# ---------------------------------------------------------------------------
# Reason-string source attribution (FIX 1 regression guard)
# ---------------------------------------------------------------------------

class TestReasonStringSourceLabel:
    """The reason string must identify the correct source of the weight distribution:
    'override' when the caller supplies an explicit fraction; 'car data' when it
    came from the per-car data file; 'prior' when it fell through to the drivetrain
    prior.  A pre-fix bug labelled car-data values as 'override' because
    driving_advisor pre-resolved the file and passed the result as the arg."""

    def test_explicit_arg_reason_says_override(self):
        """When front_weight_dist is supplied directly, reason mentions 'override'."""
        v = _gr3_rr()
        # 0.62 is non-balanced so the bias_desc branch includes frac_label.
        sf = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.62)
        assert "override" in sf.front_reason.lower(), (
            f"Explicit arg: reason should contain 'override'; got {sf.front_reason!r}"
        )

    def test_car_data_file_reason_says_car_data_not_override(self, monkeypatch):
        """When the weight fraction comes from the car-data file (not an explicit arg),
        the reason must say 'car data' — NOT 'override'."""
        import data.car_weight_distribution as _wd
        # Inject a file entry (0.38 → non-balanced, so the bias label is included).
        monkeypatch.setattr(_wd, "_CACHE", {"Porsche 911 RSR (991) '17": 0.38})
        v = _gr3_rr()
        # No explicit front_weight_dist arg → file is consulted.
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert "override" not in sf.front_reason.lower(), (
            f"Car-data source must NOT be labelled 'override'; got {sf.front_reason!r}"
        )
        assert "car data" in sf.front_reason.lower(), (
            f"Car-data source must be labelled 'car data'; got {sf.front_reason!r}"
        )

    def test_drivetrain_prior_reason_says_prior(self, monkeypatch):
        """When neither arg nor file provides a fraction, the drivetrain prior is used
        and the reason mentions 'prior'."""
        import data.car_weight_distribution as _wd
        monkeypatch.setattr(_wd, "_CACHE", {})   # empty → file returns None
        v = _gr3_rr()   # RR prior = 0.38 → rear-traction bias
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert "prior" in sf.front_reason.lower(), (
            f"Drivetrain prior: reason should mention 'prior'; got {sf.front_reason!r}"
        )

    def test_drivetrain_prior_reason_does_not_double_the_code(self, monkeypatch):
        """Regression: the drivetrain code must appear once, not twice
        (was 'RR RR drivetrain prior ...')."""
        import data.car_weight_distribution as _wd
        monkeypatch.setattr(_wd, "_CACHE", {})   # empty → file returns None
        v = _gr3_rr()   # drivetrain 'rr'
        sf = derive_spring_frequencies(v, OBJ_BASE)
        assert "RR RR" not in sf.front_reason, (
            f"Drivetrain code doubled in reason: {sf.front_reason!r}"
        )
        assert sf.front_reason.count("RR") == 1, (
            f"Expected the drivetrain code exactly once; got {sf.front_reason!r}"
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_twice_identical_no_track(self):
        v = _gr3_rr()
        a = derive_spring_frequencies(v, OBJ_RACE)
        b = derive_spring_frequencies(v, OBJ_RACE)
        assert a.front_hz    == b.front_hz
        assert a.rear_hz     == b.rear_hz
        assert a.front_reason == b.front_reason
        assert a.rear_reason  == b.rear_reason

    def test_same_inputs_twice_identical_with_track(self):
        v = _gr3_rr()
        a = derive_spring_frequencies(v, OBJ_RACE, _fuji())
        b = derive_spring_frequencies(v, OBJ_RACE, _fuji())
        assert a.front_hz == b.front_hz
        assert a.rear_hz  == b.rear_hz


# ---------------------------------------------------------------------------
# Weight distribution override changes split directionally
# ---------------------------------------------------------------------------

class TestWeightDistOverride:
    def test_heavy_front_override_raises_front_hz_vs_rr_prior(self):
        v = _gr3_rr()
        # Default RR prior: frac=0.38 → rear stiffer
        default_rr = derive_spring_frequencies(v, OBJ_BASE)
        # Override with heavy-front distribution → front becomes stiffer
        heavy_front = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.65)
        assert heavy_front.front_hz > default_rr.front_hz, (
            f"Heavy-front override should raise front_hz: "
            f"got {heavy_front.front_hz} vs default {default_rr.front_hz}"
        )

    def test_heavy_front_override_lowers_rear_hz_vs_rr_prior(self):
        v = _gr3_rr()
        default_rr  = derive_spring_frequencies(v, OBJ_BASE)
        heavy_front = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.65)
        assert heavy_front.rear_hz < default_rr.rear_hz, (
            f"Heavy-front override should lower rear_hz: "
            f"got {heavy_front.rear_hz} vs default {default_rr.rear_hz}"
        )

    def test_rear_heavy_override_lowers_front_hz_vs_ff_prior(self):
        v = _veh("ff", 1300, 150, "Road Car")
        # Default FF prior: frac=0.60 → front stiffer
        default_ff = derive_spring_frequencies(v, OBJ_BASE)
        # Override with rear-heavy distribution → front loosens
        rear_heavy = derive_spring_frequencies(v, OBJ_BASE, front_weight_dist=0.35)
        assert rear_heavy.front_hz < default_ff.front_hz


# ---------------------------------------------------------------------------
# Integration: seeds flow through build_baseline_setup
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_gr3_springs_via_chassis_seeds_differ_from_neutral(self):
        """End-to-end: derive_spring_frequencies result → chassis_seed_overrides
        → build_baseline_setup → springs_front in setup_fields != NEUTRAL_SEEDS value.

        Uses generic (unconstrained) spring ranges via resolve_ranges("") so the
        class-band-derived seed (e.g. 5.76 Hz for a Gr.3 RR car) is kept interior
        to the range and is not re-mapped back toward the neutral 3.50 value.
        Per-car ranges narrow the band for known cars, but the seed derivation
        and range clamping are separate concerns tested here independently.
        """
        from strategy.setup_baseline import build_baseline_setup, NEUTRAL_SEEDS
        from strategy.setup_driver_profile import build_driver_profile
        from strategy.setup_ranges import resolve_ranges

        # Use a Gr.3 car model but with generic ranges (resolve_ranges(""))
        # so the class-band Hz value is not re-mapped by the narrow per-car range.
        specs = {"weight_kg": 1243, "power_hp": 509, "category": "Gr.3"}
        v = build_vehicle_model("Gr3 Test Car", "rr", 6, specs)
        sf = derive_spring_frequencies(v, OBJ_RACE)

        # Confirm the derived spring is NOT at the flat neutral seed
        assert sf.front_hz != NEUTRAL_SEEDS["springs_front"], (
            f"Expected spring target to differ from neutral 3.50; got {sf.front_hz}"
        )

        # Flow through build_baseline_setup via chassis_seed_overrides.
        # Generic ranges ensure the seed stays interior and is preserved as-is.
        generic_ranges = resolve_ranges("")
        raw = build_baseline_setup(
            "Gr3 Test Car", generic_ranges, "rr", 6,
            build_driver_profile(), None, False,
            session_type="Race",
            chassis_seed_overrides={
                "springs_front": sf.front_hz,
                "springs_rear":  sf.rear_hz,
            },
        )
        springs_front_built = raw["setup_fields"].get("springs_front")
        assert springs_front_built is not None
        assert springs_front_built != NEUTRAL_SEEDS["springs_front"], (
            f"Built springs_front={springs_front_built} should not equal neutral "
            f"{NEUTRAL_SEEDS['springs_front']} for a Gr.3 car"
        )


# ---------------------------------------------------------------------------
# Ballast-aware effective weight distribution
# ---------------------------------------------------------------------------

class TestBallastAdjustment:
    """Ballast-aware effective weight distribution: derive_spring_frequencies
    accepts ballast_kg + ballast_position and adjusts the front-fraction
    mass-weighted before computing the front/rear split."""

    # ── Zero ballast is an EXACT no-op ──────────────────────────────────────

    def test_zero_ballast_exact_noop_fr(self):
        """ballast_kg=0 → result bit-identical to no-ballast call (FR car)."""
        v = _veh("fr", 1500, 300, "Sport Car")
        no_b = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=0.0, ballast_position=30.0)
        assert with_b.front_hz    == no_b.front_hz
        assert with_b.rear_hz     == no_b.rear_hz
        assert with_b.front_reason == no_b.front_reason
        assert with_b.rear_reason  == no_b.rear_reason

    def test_position_alone_without_kg_is_noop(self):
        """ballast_position alone (kg=0) changes nothing — position alone does nothing."""
        v = _gr3_rr()
        no_b    = derive_spring_frequencies(v, OBJ_BASE)
        with_pos = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=0.0, ballast_position=50.0)
        assert with_pos.front_hz    == no_b.front_hz
        assert with_pos.rear_hz     == no_b.rear_hz
        assert with_pos.front_reason == no_b.front_reason
        assert with_pos.rear_reason  == no_b.rear_reason

    # ── Rear / front ballast changes the split directionally ────────────────

    def test_rear_ballast_fr_raises_rear_hz(self):
        """FR car, kg=50, pos=+30 (rear) → rear_hz strictly > no-ballast rear_hz."""
        v = _veh("fr", 1500, 300, "Sport Car")
        no_b   = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=50.0, ballast_position=30.0)
        assert with_b.rear_hz > no_b.rear_hz, (
            f"FR rear ballast: expected rear_hz ({with_b.rear_hz}) > no-ballast ({no_b.rear_hz})"
        )

    def test_front_ballast_rr_raises_front_hz(self):
        """RR car, kg=50, pos=-30 (front) → front_hz strictly > no-ballast front_hz."""
        v = _gr3_rr()   # weight_kg=1243
        no_b   = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=50.0, ballast_position=-30.0)
        assert with_b.front_hz > no_b.front_hz, (
            f"RR front ballast: expected front_hz ({with_b.front_hz}) > no-ballast ({no_b.front_hz})"
        )

    # ── Missing / zero car mass with kg=50 → equals zero-ballast, no crash ──

    def test_zero_car_mass_with_ballast_same_as_no_ballast(self):
        """weight_kg=None + ballast_kg=50 → fallback fires; result = no-ballast result."""
        v_none = build_vehicle_model("T", "fr", 6, {"category": "Gr.3", "power_hp": 400})
        sf_no  = derive_spring_frequencies(v_none, OBJ_BASE)
        sf_bal = derive_spring_frequencies(v_none, OBJ_BASE, ballast_kg=50.0, ballast_position=25.0)
        assert sf_bal.front_hz == sf_no.front_hz
        assert sf_bal.rear_hz  == sf_no.rear_hz

    def test_zero_weight_kg_with_ballast_same_as_no_ballast(self):
        """weight_kg=0 + ballast_kg=50 → result = no-ballast result."""
        v_zero = build_vehicle_model(
            "T", "fr", 6, {"category": "Gr.3", "power_hp": 400, "weight_kg": 0}
        )
        sf_no  = derive_spring_frequencies(v_zero, OBJ_BASE)
        sf_bal = derive_spring_frequencies(v_zero, OBJ_BASE, ballast_kg=50.0, ballast_position=25.0)
        assert sf_bal.front_hz == sf_no.front_hz
        assert sf_bal.rear_hz  == sf_no.rear_hz

    # ── Clamp: heavy ballast at max position stays within band AND [1.00, 20.00] ──

    def test_heavy_ballast_max_pos_stays_in_race_band_and_gt7(self):
        """Gr.3 car, 200 kg at ±50 → both Hz within race band and [1.00, 20.00]."""
        v = _gr3_rr()
        lo, hi = _SPRING_BAND_RACE
        for pos in (50.0, -50.0):
            sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=200.0, ballast_position=pos)
            assert lo <= sf.front_hz <= hi, (
                f"pos={pos}: front_hz={sf.front_hz} outside race band [{lo},{hi}]"
            )
            assert lo <= sf.rear_hz <= hi, (
                f"pos={pos}: rear_hz={sf.rear_hz} outside race band [{lo},{hi}]"
            )
            assert 1.00 <= sf.front_hz <= 20.00
            assert 1.00 <= sf.rear_hz  <= 20.00

    # ── Reason string contains "effective front" and direction ───────────────

    def test_reason_contains_effective_front_when_shift_gte_0005(self):
        """Large rear ballast → reason contains 'effective front' and direction word."""
        v = _veh("fr", 1500, 300, "Sport Car")
        sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=50.0, ballast_position=30.0)
        assert "effective front" in sf.front_reason, (
            f"Expected 'effective front' in reason; got {sf.front_reason!r}"
        )
        # The direction word "rear" appears when eff < base frac
        assert "rear" in sf.front_reason or "front" in sf.front_reason

    def test_reason_unchanged_when_kg_tiny_shift_below_threshold(self):
        """Tiny ballast (0.1 kg on 1500 kg car) → shift < 0.005, no ballast phrase."""
        v = _veh("fr", 1500, 300, "Sport Car")
        sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=0.1, ballast_position=30.0)
        assert "effective front" not in sf.front_reason, (
            f"Tiny ballast should not appear in reason; got {sf.front_reason!r}"
        )

    def test_reason_unchanged_when_kg_zero(self):
        """Zero ballast → no ballast phrase in reason."""
        v = _veh("fr", 1500, 300, "Sport Car")
        sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=0.0, ballast_position=30.0)
        assert "effective front" not in sf.front_reason

    # ── Determinism ──────────────────────────────────────────────────────────

    def test_determinism_same_ballast_inputs_identical(self):
        """Ballast path is deterministic: same inputs → bit-identical output."""
        v = _veh("fr", 1500, 300, "Sport Car")
        a = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=50.0, ballast_position=25.0)
        b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=50.0, ballast_position=25.0)
        assert a.front_hz     == b.front_hz
        assert a.rear_hz      == b.rear_hz
        assert a.front_reason == b.front_reason
        assert a.rear_reason  == b.rear_reason

    # ── Drivetrain invariants survive modest ballast ─────────────────────────

    def test_rr_rear_hz_gte_front_hz_with_modest_rear_ballast(self):
        """RR car + modest rear ballast (kg=30, pos=+10) → rear_hz >= front_hz."""
        v = _gr3_rr()
        sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=30.0, ballast_position=10.0)
        assert sf.rear_hz >= sf.front_hz, (
            f"RR + rear ballast: rear_hz ({sf.rear_hz}) should be >= front_hz ({sf.front_hz})"
        )

    def test_ff_front_hz_gte_rear_hz_with_modest_front_ballast(self):
        """FF car + modest front ballast (kg=30, pos=-10) → front_hz >= rear_hz."""
        v = _veh("ff", 1300, 150, "Road Car")
        sf = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=30.0, ballast_position=-10.0)
        assert sf.front_hz >= sf.rear_hz, (
            f"FF + front ballast: front_hz ({sf.front_hz}) should be >= rear_hz ({sf.rear_hz})"
        )

    # ── Formula-isolation micro-tests for _bpos_frac ─────────────────────────
    # Verified via observable effect (pos=0 → neutral, +50 → full rear, -50 → full front).

    def test_ballast_front_frac_pos_zero_is_neutral_awd(self):
        """At pos=0, ballast contributes 50/50 — for a neutral (AWD 0.50) car,
        any ballast at pos=0 leaves frac unchanged → output identical to no-ballast."""
        v = build_vehicle_model("AWD Test", "awd", 6,
                                {"weight_kg": 1000, "power_hp": 250, "category": "Sport Car"})
        no_b   = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=200.0, ballast_position=0.0)
        # AWD prior = 0.50; ballast at pos=0 → _bpos_frac=0.5 → _eff stays 0.50
        assert with_b.front_hz == no_b.front_hz, (
            f"pos=0 ballast on AWD: front_hz should be unchanged; "
            f"got {no_b.front_hz} → {with_b.front_hz}"
        )
        assert with_b.rear_hz == no_b.rear_hz

    def test_ballast_front_frac_pos_plus50_is_full_rear_observable(self):
        """At pos=+50 (full rear), _bpos_frac=0.0 (all ballast at rear).
        For a front-heavy car (FF), heavy rear ballast must lower front_hz."""
        v = _veh("ff", 1000, 200, "Sport Car")
        no_b   = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=200.0, ballast_position=50.0)
        # pos=+50 → _bpos_frac=0.0 → 100% rear ballast → pulls eff frac below 0.60 (FF prior)
        assert with_b.front_hz < no_b.front_hz, (
            f"pos=+50 (full rear): front_hz should decrease for FF; "
            f"got {with_b.front_hz} vs no-ballast {no_b.front_hz}"
        )

    def test_ballast_front_frac_pos_minus50_is_full_front_observable(self):
        """At pos=-50 (full front), _bpos_frac=1.0 (all ballast at front).
        For a rear-heavy car (RR), heavy front ballast must raise front_hz."""
        v = _gr3_rr()
        no_b   = derive_spring_frequencies(v, OBJ_BASE)
        with_b = derive_spring_frequencies(v, OBJ_BASE, ballast_kg=200.0, ballast_position=-50.0)
        # pos=-50 → _bpos_frac=1.0 → 100% front ballast → raises eff frac above 0.38 (RR prior)
        assert with_b.front_hz > no_b.front_hz, (
            f"pos=-50 (full front): front_hz should increase for RR; "
            f"got {with_b.front_hz} vs no-ballast {no_b.front_hz}"
        )
