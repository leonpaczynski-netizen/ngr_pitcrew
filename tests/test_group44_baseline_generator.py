"""
Group 44 — From-Scratch Baseline Setup Generator: Acceptance Tests

Covers:
  - NEUTRAL_SEEDS values match form widget seeds
  - build_baseline_setup: all 33 actionable canonical fields present (neutral profile,
    no locking, AWD, 6 gears)
  - build_baseline_setup: gears strictly decreasing
  - build_baseline_setup: transmission_max_speed_kmh absent from setup_fields
  - build_baseline_setup: driver-profile bias adjusts correct fields
  - build_baseline_setup: locked fields excluded from changes and setup_fields
  - build_baseline_setup: tuning_locked returns empty changes/setup_fields
  - build_baseline_setup: non-AWD cars omit front-differential fields
  - build_baseline_setup: num_gears edge cases (0, 1, 6, >6)
  - build_baseline_setup: gearbox seed with no gears
  - build_baseline_setup: conservative-label fields labelled correctly
  - build_baseline_setup_response: returns JSON, status in APPROVED_STATUSES
  - build_baseline_setup_response: transmission_max_speed_kmh absent from output
  - build_baseline_setup_response: biased profile changes driver-biased fields
  - No regression: all canonical field values clamped within ranges

All tests are pure/offline — no network, no Qt event loop, no QApplication.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_baseline import (
    NEUTRAL_SEEDS,
    build_baseline_setup,
    _CONSERVATIVE_FIELDS,
    _LABEL_BIASED,
    _LABEL_CONSERV,
    _LABEL_NEUTRAL,
    _GEAR_RATIO_RANGE,
    _FINAL_DRIVE_RANGE,
)
from strategy.setup_driver_profile import build_driver_profile, DriverProfile
from strategy.setup_ranges import resolve_ranges
from strategy._setup_constants import APPROVED_STATUSES
from strategy.setup_diagnosis import ValidationFailure


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _neutral_profile() -> DriverProfile:
    """Return a fully-False DriverProfile (no biases)."""
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )


def _full_biased_profile() -> DriverProfile:
    """Return a DriverProfile with all bias flags True."""
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=True,
        dislikes_snap_exit=True,
        trail_braker=True,
        rotation_without_snap=True,
        prefers_front_bite=True,
        dislikes_floaty_front=True,
        protects_downforce=True,
        race_values_consistency=True,
    )


def _make_advisor():
    """Return a minimal DrivingAdvisor instance suitable for testing."""
    from strategy.driving_advisor import DrivingAdvisor
    recorder = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None, best_lap=lambda: None)
    tracker  = SimpleNamespace()
    config   = {}
    return DrivingAdvisor(recorder, tracker, config)


# ---------------------------------------------------------------------------
# NEUTRAL_SEEDS verification
# ---------------------------------------------------------------------------

class TestNeutralSeeds:
    """Verify NEUTRAL_SEEDS matches the form-widget defaults (source of truth)."""

    def test_ride_height_front(self):
        assert NEUTRAL_SEEDS["ride_height_front"] == 80

    def test_ride_height_rear(self):
        assert NEUTRAL_SEEDS["ride_height_rear"] == 80

    def test_springs_front(self):
        assert NEUTRAL_SEEDS["springs_front"] == 3.50

    def test_springs_rear(self):
        assert NEUTRAL_SEEDS["springs_rear"] == 3.00

    def test_dampers_front_comp(self):
        assert NEUTRAL_SEEDS["dampers_front_comp"] == 30

    def test_dampers_front_ext(self):
        assert NEUTRAL_SEEDS["dampers_front_ext"] == 40

    def test_dampers_rear_comp(self):
        assert NEUTRAL_SEEDS["dampers_rear_comp"] == 25

    def test_dampers_rear_ext(self):
        assert NEUTRAL_SEEDS["dampers_rear_ext"] == 35

    def test_arb_front(self):
        assert NEUTRAL_SEEDS["arb_front"] == 5

    def test_arb_rear(self):
        assert NEUTRAL_SEEDS["arb_rear"] == 4

    def test_camber_front(self):
        assert NEUTRAL_SEEDS["camber_front"] == 1.0

    def test_camber_rear(self):
        assert NEUTRAL_SEEDS["camber_rear"] == 1.5

    def test_toe_front(self):
        assert NEUTRAL_SEEDS["toe_front"] == 0.00

    def test_toe_rear(self):
        assert NEUTRAL_SEEDS["toe_rear"] == 0.05

    def test_aero_front(self):
        assert NEUTRAL_SEEDS["aero_front"] == 400

    def test_aero_rear(self):
        assert NEUTRAL_SEEDS["aero_rear"] == 600

    def test_lsd_initial(self):
        assert NEUTRAL_SEEDS["lsd_initial"] == 10

    def test_lsd_accel(self):
        assert NEUTRAL_SEEDS["lsd_accel"] == 15

    def test_lsd_decel(self):
        assert NEUTRAL_SEEDS["lsd_decel"] == 5

    def test_lsd_front_initial_form_seed(self):
        # Form seed is 10; ai_planner fallback is 0 (discrepancy — form seed wins)
        assert NEUTRAL_SEEDS["lsd_front_initial"] == 10

    def test_lsd_front_accel_form_seed(self):
        # Form seed is 15; ai_planner fallback is 0 (discrepancy — form seed wins)
        assert NEUTRAL_SEEDS["lsd_front_accel"] == 15

    def test_lsd_front_decel_form_seed(self):
        # Form seed is 5; ai_planner fallback is 0 (discrepancy — form seed wins)
        assert NEUTRAL_SEEDS["lsd_front_decel"] == 5

    def test_brake_bias(self):
        assert NEUTRAL_SEEDS["brake_bias"] == 0

    def test_ballast_kg(self):
        assert NEUTRAL_SEEDS["ballast_kg"] == 0.0

    def test_ballast_position(self):
        assert NEUTRAL_SEEDS["ballast_position"] == 0

    def test_power_restrictor(self):
        assert NEUTRAL_SEEDS["power_restrictor"] == 100.0


# ---------------------------------------------------------------------------
# build_baseline_setup — field coverage
# ---------------------------------------------------------------------------

class TestFieldCoverage:
    """All 33 actionable canonical fields must be present for AWD + 6 gears."""

    # The 33 actionable canonical fields (excluding transmission_max_speed_kmh):
    EXPECTED_FIELDS = {
        "ride_height_front", "ride_height_rear",
        "springs_front", "springs_rear",
        "dampers_front_comp", "dampers_front_ext",
        "dampers_rear_comp", "dampers_rear_ext",
        "arb_front", "arb_rear",
        "camber_front", "camber_rear",
        "toe_front", "toe_rear",
        "aero_front", "aero_rear",
        "lsd_initial", "lsd_accel", "lsd_decel",
        "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
        "brake_bias",
        "ballast_kg", "ballast_position",
        "power_restrictor",
        "final_drive",
        "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
    }

    #: UAT 2026-08-07 defect A4 — a gearbox is now authored only from evidence, so
    #: full-field coverage has to SUPPLY that evidence. Without it the seven gearbox
    #: fields are correctly absent, which is asserted separately below.
    PROVEN_GEARBOX = {"final_drive": 4.0, "gear_1": 2.98, "gear_2": 2.14,
                      "gear_3": 1.66, "gear_4": 1.33, "gear_5": 1.09, "gear_6": 0.905}

    def _result(self, proven_gearbox="default"):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        return build_baseline_setup(
            car="",
            ranges=ranges,
            drivetrain="AWD",
            num_gears=6,
            profile=profile,
            allowed_tuning=None,
            tuning_locked=False,
            proven_gearbox=(self.PROVEN_GEARBOX if proven_gearbox == "default"
                            else proven_gearbox),
        )

    def test_gearbox_fields_absent_without_evidence(self):
        """The other half of the contract: no evidence, no gearbox, no silent midpoint."""
        sf = self._result(proven_gearbox=None)["setup_fields"]
        assert not ({"final_drive"} | {f"gear_{i}" for i in range(1, 7)}) & set(sf)

    def test_all_33_fields_in_setup_fields(self):
        result = self._result()
        sf = result["setup_fields"]
        missing = self.EXPECTED_FIELDS - set(sf.keys())
        assert not missing, f"Missing from setup_fields: {missing}"

    def test_all_33_fields_in_changes(self):
        result = self._result()
        change_fields = {ch["field"] for ch in result["changes"]}
        missing = self.EXPECTED_FIELDS - change_fields
        assert not missing, f"Missing from changes: {missing}"

    def test_transmission_max_speed_absent_from_setup_fields(self):
        result = self._result()
        assert "transmission_max_speed_kmh" not in result["setup_fields"]

    def test_transmission_max_speed_absent_from_changes(self):
        result = self._result()
        fields = {ch["field"] for ch in result["changes"]}
        assert "transmission_max_speed_kmh" not in fields

    def test_required_raw_data_keys_present(self):
        result = self._result()
        for key in ("analysis", "primary_issue", "changes", "setup_fields",
                    "diagnosis", "validation_targets", "confidence"):
            assert key in result, f"Missing key: {key}"

    def test_count_33(self):
        result = self._result()
        assert len(self.EXPECTED_FIELDS) == 33


# ---------------------------------------------------------------------------
# Gearbox algorithm
# ---------------------------------------------------------------------------

class TestGearboxAlgorithm:
    """Gears must be strictly decreasing and within range."""

    def _gears(self, n: int, drivetrain: str = "FR") -> dict:
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, drivetrain, n, profile, None, False)
        return result["setup_fields"]

    # UAT 2026-08-07 defect A4, Phase 1 chunk 6 — this class used to assert the
    # GEOMETRIC SPREAD: a strictly-decreasing sequence from two global constants,
    # identical for every car in the game, plus a final drive at the midpoint of a
    # global range. Knowing a car has six gears says nothing about what those six
    # ratios should be, and a gearbox is the one part of a setup a driver cannot judge
    # by feel from the sheet — so a plausible-looking wrong answer there is worse than
    # no answer. The spread is gone; these now assert the contract that replaced it.

    def test_no_gearbox_is_authored_without_evidence(self):
        """No car in the repository has a redline or stock ratios until a GT7 capture
        supplies them, so this is the normal outcome today, by design."""
        for n in (1, 3, 6, 10):
            sf = self._gears(n)
            for i in range(1, 8):
                assert f"gear_{i}" not in sf, f"{n} gears: gear_{i} authored with no evidence"
            assert "final_drive" not in sf, f"{n} gears: final drive authored with no evidence"

    def test_0_gears_no_gear_keys(self):
        sf = self._gears(0)
        for i in range(1, 7):
            assert f"gear_{i}" not in sf

    def test_the_plan_says_what_is_missing_and_what_to_do(self):
        """Authoring nothing is only acceptable if it is actionable."""
        ranges = resolve_ranges("")
        raw = build_baseline_setup("", ranges, "FR", 6, _neutral_profile(), None, False)
        plan = raw["gearbox_plan"]
        assert plan["authored"] is False
        assert set(plan["missing"]) == {"redline_rpm", "stock_ratios", "longest_straight_m"}
        assert "stock gearing" in plan["advice"]
        assert "Capture" in plan["advice"]

    def test_a_proven_gear_set_is_authored_verbatim(self):
        """The one case with real evidence: a vetted gear set for this car at this
        track is the strongest thing there is, and it is used exactly."""
        proven = {"final_drive": 4.0, "gear_1": 2.98, "gear_2": 2.14, "gear_3": 1.66,
                  "gear_4": 1.33, "gear_5": 1.09, "gear_6": 0.905}
        raw = build_baseline_setup("", resolve_ranges(""), "FR", 0, _neutral_profile(),
                                   None, False, proven_gearbox=proven)
        sf = raw["setup_fields"]
        for field, value in proven.items():
            assert sf[field] == pytest.approx(value), field
        assert raw["gearbox_plan"]["authored"] is True

    def test_a_proven_gear_set_stays_strictly_decreasing(self):
        raw = build_baseline_setup(
            "", resolve_ranges(""), "FR", 0, _neutral_profile(), None, False,
            proven_gearbox={f"gear_{i}": r for i, r in enumerate(
                [2.98, 2.14, 1.66, 1.33, 1.09, 0.905], start=1)})
        sf = raw["setup_fields"]
        ratios = [sf[f"gear_{i}"] for i in range(1, 7)]
        for i in range(len(ratios) - 1):
            assert ratios[i] > ratios[i + 1]

    def test_a_proven_gear_set_stays_within_the_legal_ratio_range(self):
        lo, hi = _GEAR_RATIO_RANGE
        raw = build_baseline_setup(
            "", resolve_ranges(""), "FR", 0, _neutral_profile(), None, False,
            proven_gearbox={"gear_1": 99.0, "gear_2": 0.001})
        sf = raw["setup_fields"]
        assert lo <= sf["gear_1"] <= hi
        assert lo <= sf["gear_2"] <= hi

    def test_a_proven_final_drive_stays_within_range(self):
        lo, hi = _FINAL_DRIVE_RANGE
        raw = build_baseline_setup(
            "", resolve_ranges(""), "FR", 0, _neutral_profile(), None, False,
            proven_gearbox={"final_drive": 99.0})
        assert lo <= raw["setup_fields"]["final_drive"] <= hi


# ---------------------------------------------------------------------------
# Driver-profile bias
# ---------------------------------------------------------------------------

class TestDriverProfileBias:
    """Biased fields should differ from neutral seeds, label should be 'driver-profile biased'."""

    def _biased_changes(self) -> dict:
        ranges = resolve_ranges("")
        profile = _full_biased_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        return {ch["field"]: ch for ch in result["changes"]}

    def _neutral_changes(self) -> dict:
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        return {ch["field"]: ch for ch in result["changes"]}

    def test_arb_rear_biased_label(self):
        ch = self._biased_changes()
        assert ch["arb_rear"]["rationale"] == "driver-profile biased"

    def test_arb_front_biased_label(self):
        ch = self._biased_changes()
        assert ch["arb_front"]["rationale"] == "driver-profile biased"

    def test_toe_rear_biased_label(self):
        ch = self._biased_changes()
        # toe_rear is in _CONSERVATIVE_FIELDS but bias overrides label
        assert ch["toe_rear"]["rationale"] == "driver-profile biased"

    def test_lsd_accel_biased_lower(self):
        biased = self._biased_changes()
        neutral = self._neutral_changes()
        # dislikes_snap_exit → lsd_accel -2
        biased_val = biased["lsd_accel"]["to_clamped"]
        neutral_val = neutral["lsd_accel"]["to_clamped"]
        assert biased_val < neutral_val

    def test_aero_front_biased_higher(self):
        biased = self._biased_changes()
        neutral = self._neutral_changes()
        assert biased["aero_front"]["to_clamped"] > neutral["aero_front"]["to_clamped"]

    def test_aero_rear_biased_higher(self):
        biased = self._biased_changes()
        neutral = self._neutral_changes()
        assert biased["aero_rear"]["to_clamped"] > neutral["aero_rear"]["to_clamped"]

    def test_lsd_decel_biased_higher(self):
        # Group 45 note: _PROFILE_BIAS_TABLE now has BOTH race_values_consistency (+2)
        # and rotation_without_snap (-2) affecting lsd_decel.  When the full-biased profile
        # has both flags True the deltas cancel (net=0), so biased==neutral for this field.
        # The assertion is updated to >= to reflect the correct net-zero outcome.
        # To test each flag in isolation, use a partial profile; the full-biased profile
        # is no longer a useful isolation test for this specific field.
        biased = self._biased_changes()
        neutral = self._neutral_changes()
        assert biased["lsd_decel"]["to_clamped"] >= neutral["lsd_decel"]["to_clamped"]

    def test_biased_alignment_is_aligned(self):
        ch = self._biased_changes()
        assert ch["arb_rear"]["driver_style_alignment"] == "aligned"

    def test_unbiased_alignment_is_neutral(self):
        ch = self._neutral_changes()
        assert ch["brake_bias"]["driver_style_alignment"] == "neutral"


# ---------------------------------------------------------------------------
# Conservative-label fields
# ---------------------------------------------------------------------------

class TestConservativeLabels:
    """Fields in _CONSERVATIVE_FIELDS without bias must use 'conservative default, not diagnosed'."""

    def _neutral_changes(self) -> dict:
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        return {ch["field"]: ch for ch in result["changes"]}

    @pytest.mark.parametrize("field", [
        "camber_front", "camber_rear",
        "dampers_front_comp", "dampers_front_ext",
        "dampers_rear_comp", "dampers_rear_ext",
        "springs_front", "springs_rear",
        "lsd_initial",
    ])
    def test_conservative_label(self, field: str):
        ch = self._neutral_changes()
        assert ch[field]["rationale"] == "conservative default, not diagnosed", (
            f"{field} expected 'conservative default, not diagnosed', got {ch[field]['rationale']!r}"
        )


# ---------------------------------------------------------------------------
# Locked fields
# ---------------------------------------------------------------------------

class TestLockedFields:
    """Locked fields must not appear in changes or setup_fields."""

    def test_suspension_locked(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup(
            "", ranges, "FR", 6, profile,
            allowed_tuning=["aero", "differential", "brake_balance",
                            "transmission", "power", "ballast"],
            tuning_locked=False,
        )
        suspension_fields = {
            "ride_height_front", "ride_height_rear",
            "springs_front", "springs_rear",
            "arb_front", "arb_rear",
            "dampers_front_comp", "dampers_front_ext",
            "dampers_rear_comp", "dampers_rear_ext",
            "camber_front", "camber_rear",
            "toe_front", "toe_rear",
        }
        change_fields = {ch["field"] for ch in result["changes"]}
        for f in suspension_fields:
            assert f not in result["setup_fields"], f"{f} in setup_fields (should be locked)"
            assert f not in change_fields, f"{f} in changes (should be locked)"

    def test_aero_locked(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup(
            "", ranges, "FR", 6, profile,
            allowed_tuning=["suspension", "differential", "brake_balance",
                            "transmission", "power", "ballast"],
            tuning_locked=False,
        )
        change_fields = {ch["field"] for ch in result["changes"]}
        assert "aero_front" not in result["setup_fields"]
        assert "aero_rear" not in result["setup_fields"]
        assert "aero_front" not in change_fields
        assert "aero_rear" not in change_fields

    def test_tuning_locked_returns_empty(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, tuning_locked=True)
        assert result["changes"] == []
        assert result["setup_fields"] == {}


# ---------------------------------------------------------------------------
# Non-AWD drivetrain
# ---------------------------------------------------------------------------

class TestDrivetrain:
    """Front-differential fields must be absent for non-AWD cars."""

    _FRONT_DIFF = {"lsd_front_initial", "lsd_front_accel", "lsd_front_decel"}

    def _result_fr(self) -> dict:
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        return build_baseline_setup("", ranges, "FR", 6, profile, None, False)

    def _result_awd(self) -> dict:
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        return build_baseline_setup("", ranges, "AWD", 6, profile, None, False)

    def test_fr_no_front_diff_in_setup_fields(self):
        sf = self._result_fr()["setup_fields"]
        for f in self._FRONT_DIFF:
            assert f not in sf, f"{f} should not be in setup_fields for FR"

    def test_fr_no_front_diff_in_changes(self):
        change_fields = {ch["field"] for ch in self._result_fr()["changes"]}
        for f in self._FRONT_DIFF:
            assert f not in change_fields, f"{f} should not be in changes for FR"

    def test_awd_has_front_diff_in_setup_fields(self):
        sf = self._result_awd()["setup_fields"]
        for f in self._FRONT_DIFF:
            assert f in sf, f"{f} missing from setup_fields for AWD"


# ---------------------------------------------------------------------------
# Range clamping
# ---------------------------------------------------------------------------

class TestRangeClamping:
    """All setup_fields values must be within the generic ranges."""

    def test_all_values_within_generic_ranges(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "AWD", 6, profile, None, False)
        sf = result["setup_fields"]
        for field, value in sf.items():
            if field in ranges:
                lo, hi = ranges[field]
                assert lo <= value <= hi, (
                    f"{field}={value} outside [{lo}, {hi}]"
                )


# ---------------------------------------------------------------------------
# build_baseline_setup_response
# ---------------------------------------------------------------------------

class TestBuildBaselineSetupResponse:
    """DrivingAdvisor.build_baseline_setup_response returns valid JSON in APPROVED_STATUSES."""

    def test_returns_json_string(self):
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        assert isinstance(result, str)
        data = json.loads(result)  # must not raise
        assert isinstance(data, dict)

    def test_status_in_approved_statuses(self):
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        assert data["recommendation_status"] in APPROVED_STATUSES, (
            f"status={data['recommendation_status']!r} not in APPROVED_STATUSES"
        )

    def test_transmission_max_speed_absent(self):
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="AWD",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        assert "transmission_max_speed_kmh" not in data.get("setup_fields", {})
        change_fields = {ch.get("field") for ch in data.get("changes", [])}
        assert "transmission_max_speed_kmh" not in change_fields

    def test_no_api_call_made(self):
        """Response must not depend on any API key (no network calls)."""
        advisor = _make_advisor()
        # Ensure config has no API key
        advisor._config = {}
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        assert data["recommendation_status"] in APPROVED_STATUSES

    def test_tuning_locked_returns_valid_json(self):
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=True,
        )
        data = json.loads(result)
        assert isinstance(data, dict)
        assert data.get("changes") == [] or data.get("setup_fields") == {}

    def test_response_has_standard_keys(self):
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        required_keys = {
            "recommendation_status", "changes", "setup_fields",
            "engineering_validation_failed", "engineering_validation_errors",
            "validation_warnings", "fallback_used", "rejected_changes",
            "deterministic_plan", "protected_fields", "rule_engine_version",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"Missing response keys: {missing}"

    def test_biased_profile_changes_arb_rear(self):
        """With full-bias profile, arb_rear should differ from NEUTRAL_SEEDS."""
        # Build directly (not via advisor, which uses build_driver_profile())
        from strategy.setup_baseline import build_baseline_setup
        ranges = resolve_ranges("")
        profile = _full_biased_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        # arb_rear has prefers_rear_stability bias of -1 → should be 4 - 1 = 3
        ch_map = {ch["field"]: ch for ch in result["changes"]}
        assert ch_map["arb_rear"]["to_clamped"] == NEUTRAL_SEEDS["arb_rear"] - 1

    def test_awd_6gear_response_has_all_33_fields(self):
        # UAT 2026-08-07 defect A4 — the gearbox is authored only from evidence, so
        # this uses the car+track that HAS a vetted gear set in the proven library.
        # An unmapped car correctly omits those seven fields (covered in
        # TestFieldCoverage.test_gearbox_fields_absent_without_evidence).
        advisor = _make_advisor()
        car = "Porsche 911 RSR '17"
        ranges = resolve_ranges(car)
        result = advisor.build_baseline_setup_response(
            car_name=car, ranges=ranges, drivetrain="AWD",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
            session_type="Race", track_name="Autodromo Nazionale Monza",
        )
        data = json.loads(result)
        expected = {
            "ride_height_front", "ride_height_rear",
            "springs_front", "springs_rear",
            "dampers_front_comp", "dampers_front_ext",
            "dampers_rear_comp", "dampers_rear_ext",
            "arb_front", "arb_rear",
            "camber_front", "camber_rear",
            "toe_front", "toe_rear",
            "aero_front", "aero_rear",
            "lsd_initial", "lsd_accel", "lsd_decel",
            "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
            "brake_bias", "ballast_kg", "ballast_position", "power_restrictor",
            "final_drive",
            "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
        }
        sf_keys = set(data["setup_fields"].keys())
        missing = expected - sf_keys
        assert not missing, f"Missing from response setup_fields: {missing}"


# ---------------------------------------------------------------------------
# Explainability keys in change dicts
# ---------------------------------------------------------------------------

class TestExplainabilityKeys:
    """Each change dict must carry the full explainability key set."""

    REQUIRED_KEYS = {
        "setting", "field", "from", "to", "to_clamped",
        "symptom", "evidence", "rule_id", "rationale",
        "rejected_alternatives", "risk_level", "confidence_level",
        "driver_style_alignment",
    }

    def test_all_explainability_keys_present(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        for ch in result["changes"]:
            missing = self.REQUIRED_KEYS - set(ch.keys())
            assert not missing, f"Change {ch.get('field')} missing keys: {missing}"

    def test_symptom_is_no_telemetry_baseline(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        for ch in result["changes"]:
            assert ch["symptom"] == "no telemetry baseline", (
                f"{ch['field']}: symptom={ch['symptom']!r}"
            )

    def test_risk_level_is_low(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        for ch in result["changes"]:
            assert ch["risk_level"] == "low"

    def test_confidence_level_is_low(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)
        for ch in result["changes"]:
            assert ch["confidence_level"] == "low"


# ---------------------------------------------------------------------------
# CRITICAL-1 regression: warning-filter for artifact warnings
# ---------------------------------------------------------------------------

class TestBaselineWarningFilter:
    """A clean baseline must be APPLYABLE, and must disclose its own confidence.

    Original contract: the two structural warnings a full-field from-scratch baseline
    always raises ("is a no-op", "too many changes") are artifacts and must not block
    it. That still holds — every assertion below requires an APPROVED_STATUSES value.

    Amended by UAT 2026-08-07 defect A8: filtering those artifacts left the response
    with zero warnings AND status "approved", which renders no banner at all, so a
    30-field, never-validated, ``confidence.overall == "low"`` baseline presented
    exactly like a telemetry-backed, validated recommendation. The baseline is still
    approved; it now says out loud that it is a starting point.

    Also verifies that blocking failures are never filtered out.
    """

    def test_neutral_baseline_is_approved_but_discloses_low_confidence(self):
        """A clean neutral-profile baseline (FR, 6 gears, no locking) is applyable,
        and carries the low-confidence disclosure rather than a silent all-clear."""
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        assert data["recommendation_status"] in APPROVED_STATUSES, (
            f"Baseline must stay applyable, got {data['recommendation_status']!r}. "
            f"validation_warnings={data.get('validation_warnings')}"
        )
        assert data["recommendation_status"] == "approved_with_warnings"
        assert any("low-confidence baseline" in w.lower()
                   for w in data["validation_warnings"])

    def test_neutral_baseline_raises_no_structural_artifact_warnings(self):
        """The artifact filter still does its job: the ONLY warning is the
        confidence disclosure — no "is a no-op" / "too many changes" noise."""
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        residue = [w for w in data["validation_warnings"]
                   if "low-confidence baseline" not in w.lower()]
        assert residue == [], f"Expected no artifact warnings, got: {residue}"

    def test_awd_neutral_baseline_is_approved(self):
        """AWD car (even more fields) must also stay applyable."""
        advisor = _make_advisor()
        ranges = resolve_ranges("")
        result = advisor.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="AWD",
            num_gears=6, allowed_tuning=None, tuning_locked=False,
        )
        data = json.loads(result)
        assert data["recommendation_status"] in APPROVED_STATUSES
        residue = [w for w in data["validation_warnings"]
                   if "low-confidence baseline" not in w.lower()]
        assert residue == []

    def test_filter_only_removes_warning_severity_not_blocking(self):
        """_filter_baseline_artifact_warnings must NEVER remove a blocking failure."""
        from strategy.driving_advisor import _filter_baseline_artifact_warnings
        from strategy.setup_diagnosis import ValidationFailure

        blocking = ValidationFailure(
            code="gearbox_ratio_inversion",
            message="gearbox_ratio_inversion: gear_1 <= gear_2",
            severity="blocking",
        )
        noop_warning = ValidationFailure(
            code="change field 'gear_1' is a no-op (from == to_clamped == 3.8)",
            message="change field 'gear_1' is a no-op (from == to_clamped == 3.8)",
            severity="warning",
        )
        too_many_warning = ValidationFailure(
            code="too many changes (>4)",
            message="too many changes (>4): 31 changes recommended — prefer 2–4 targeted changes",
            severity="warning",
        )
        real_warning = ValidationFailure(
            code="gearbox_out_of_range",
            message="gearbox_out_of_range: gear_1=5.0 is outside the expected range 0.5–4.0.",
            severity="warning",
        )

        mixed = [blocking, noop_warning, too_many_warning, real_warning]
        filtered = _filter_baseline_artifact_warnings(mixed)

        # Blocking failure must survive
        assert blocking in filtered, "Blocking failure was incorrectly removed"
        # The two artifact warnings must be dropped
        assert noop_warning not in filtered, "No-op warning should have been removed"
        assert too_many_warning not in filtered, "Too-many-changes warning should have been removed"
        # A genuine warning (gearbox_out_of_range) must survive
        assert real_warning in filtered, "Genuine warning was incorrectly removed"
        assert len(filtered) == 2  # blocking + real_warning

    def test_filter_with_only_blocking_failures_unchanged(self):
        """If there are no artifact warnings, the list comes back unchanged."""
        from strategy.driving_advisor import _filter_baseline_artifact_warnings
        from strategy.setup_diagnosis import ValidationFailure

        failures = [
            ValidationFailure(
                code="rh_for_minor_bottoming",
                message="rh_for_minor_bottoming: ride height raised for minor bottoming",
                severity="blocking",
            ),
        ]
        filtered = _filter_baseline_artifact_warnings(failures)
        assert filtered == failures

    def test_filter_with_empty_list(self):
        """Empty input returns empty output — no errors."""
        from strategy.driving_advisor import _filter_baseline_artifact_warnings
        assert _filter_baseline_artifact_warnings([]) == []


# ---------------------------------------------------------------------------
# IMPORTANT-3: gearbox range constants match setup_diagnosis source of truth
# ---------------------------------------------------------------------------

class TestGearboxRangeConstants:
    """Module-level fallback constants in setup_baseline must equal setup_diagnosis values."""

    def test_gear_ratio_range_matches_setup_diagnosis(self):
        from strategy.setup_diagnosis import _GEAR_RATIO_RANGE as _diag_grr
        assert _GEAR_RATIO_RANGE == _diag_grr, (
            f"setup_baseline._GEAR_RATIO_RANGE={_GEAR_RATIO_RANGE} differs from "
            f"setup_diagnosis._GEAR_RATIO_RANGE={_diag_grr}"
        )

    def test_final_drive_range_matches_setup_diagnosis(self):
        from strategy.setup_diagnosis import _FINAL_DRIVE_RANGE as _diag_fdr
        assert _FINAL_DRIVE_RANGE == _diag_fdr, (
            f"setup_baseline._FINAL_DRIVE_RANGE={_FINAL_DRIVE_RANGE} differs from "
            f"setup_diagnosis._FINAL_DRIVE_RANGE={_diag_fdr}"
        )


# ---------------------------------------------------------------------------
# MINOR-2: locked analysis text uses category names not raw field keys
# ---------------------------------------------------------------------------

class TestLockedAnalysisText:
    """When allowed_tuning restricts categories, analysis text must name them."""

    def test_locked_categories_use_human_names(self):
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        result = build_baseline_setup(
            "", ranges, "FR", 6, profile,
            allowed_tuning=["aero", "differential"],
            tuning_locked=False,
        )
        analysis = result["analysis"]
        # Category names that SHOULD appear (locked = all cats minus aero/differential)
        # Should mention "Suspension" (not "ride_height_front" etc.)
        assert "Suspension" in analysis or "suspension" in analysis.lower(), (
            f"Expected 'Suspension' in analysis but got: {analysis!r}"
        )
        # Raw field keys should NOT appear in the locked-categories sentence
        assert "ride_height_front" not in analysis
        assert "arb_front" not in analysis
        assert "camber_front" not in analysis
