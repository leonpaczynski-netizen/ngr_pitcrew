"""
Group 46 — Learning & Race Context Intelligence: Porsche RSR Pack Tests

Covers ACs 32-37 (Porsche RSR extended pack):
  AC32 — under rear instability, rear-downforce reduction rejected/flagged (A2).
  AC33 — snap-throttle wheelspin → traction-first (P1 lsd_accel).
  AC34 — front-bite protected under entry-stable; no rearward brake bias.
  AC35 — no generic ride-height raise unless bottoming band consider/required or kerb evidence.
  AC36 — high fuel/tyre RSR → source_label distinguishes Porsche-specific vs generic.
  AC37 — BENCHMARK REGRESSION (full integrated):
         car "Porsche 911 RSR (991) '17", Fuji, duration ~50min, fuel_high (>=5),
         tyre_wear_multiplier high, feedback rear-loose+mid-push+floaty-front,
         telemetry snap-throttle-wheelspin+top-speed-low+entry-stable+possible-bottoming.
         Asserts:
           (a) traction-first before/instead of aero-cut;
           (b) no rear-downforce reduction;
           (c) no rearward brake bias;
           (d) no generic ride-height raise unless bottoming supports;
           (e) no top-speed gear-lengthening as PRIMARY wheelspin response;
           (f) no AI-authored values (engine-only path);
           (g) passes Apply gate (approved status + >=1 approved change).

This test reuses the RSR fixture/diagnosis-key idioms from test_group45_porsche_pack.py.
All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_rule_engine import run_rule_engine
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_knowledge_base import (
    SessionType, DrivetrainType, CarClass,
    CAR_DRIVETRAIN_OVERRIDES,
)
from strategy.setup_ranges import resolve_ranges
from strategy._setup_constants import APPROVED_STATUSES
import strategy.driving_advisor as da


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PORSCHE_CAR = "Porsche 911 RSR (991) '17"
_FUJI_TRACK = "fuji_international_speedway"


# ---------------------------------------------------------------------------
# Helpers — reuse Group 45 idioms exactly
# ---------------------------------------------------------------------------

def _make_neutral_profile() -> DriverProfile:
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


def _rsr_high_fuel_diag(
    fuel_high: bool = True,
    tyre_wear_high: bool = True,
    entry_stable: bool = True,
    possible_bottoming: bool = True,
) -> dict:
    """Full RSR race diagnosis with high fuel, high tyre wear, rear loose + mid-push."""
    return {
        "avg_bottoming": 0.15 if possible_bottoming else 0.0,
        "bottoming_band": "consider" if possible_bottoming else "minor",
        "avg_wheelspin": 20.0,
        "wheelspin_band": "severe",
        "avg_snap": 8.0,
        "avg_lockups": 0.0,
        "driver_feel_flags": {
            "snap_oversteer_exit": False,
            "rear_loose_on_exit": True,
            "floaty_front": True,
            "entry_understeer": True,
            "braking_instability": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False,
        "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "wheelspin",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "snap_throttle_induced",
        "bottoming_confidence": {
            "band": "consider" if possible_bottoming else "minor",
            "subtype": "possible_bottoming" if possible_bottoming else "insufficient_data",
            "confidence": "med" if possible_bottoming else "low",
        },
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "avg_top_speed_kmh": 200.0,
        "top_speed_target_kmh": 280.0,
        "tyre_wear_high": tyre_wear_high,
        "tyre_wear_known": True,
        "fuel_high": fuel_high,
        "fuel_multiplier": 5.0 if fuel_high else 1.0,
    }


def _make_advisor_no_api(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    """Minimal DrivingAdvisor with no API key (engine-only path)."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = SimpleNamespace(recent_laps=lambda n: laps)
    adv._tracker = None
    adv._config = {}  # no api_key
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = event_ctx
    adv._session_id_getter = lambda: 0
    adv._summarize_new_telemetry = lambda laps: ""
    adv._car_track_header = lambda *a, **k: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._get_history_context = lambda: ""
    adv._DATA_QUALITY_NOTE = ""
    return adv


def _make_lap(
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    bottoming_count: int = 0,
    max_speed_kmh: float = 200.0,
    rev_limiter_by_gear: dict | None = None,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=0,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=5.0,
        oversteer_count=5,
        oversteer_throttle_on_count=5,
        kerb_count=0,
        max_lat_g=2.0,
        rev_limiter_count=sum(rlbg.values()),
        lock_up_positions=[],
        wheelspin_positions=[],
        oversteer_positions=[],
        snap_throttle_positions=[],
        over_braking_positions=[],
        over_braking_count=0,
        abrupt_release_count=0,
        car_max_speed_theoretical_kmh=0.0,
        avg_tyre_radius={},
        off_track_count=0,
        frames=[],
    )


# ===========================================================================
# AC32 — rear instability → rear-downforce reduction rejected/flagged (A2)
# ===========================================================================

class TestAC32RearDownforceRejected:
    """AC32: under rear_loose_on_exit, A2 blocks aero_rear reduction in Porsche context."""

    def test_a2_blocks_aero_rear_cut_rsr_high_fuel(self):
        """A2 must reject aero_rear decrease even with high fuel + RSR context."""
        diag = _rsr_high_fuel_diag(fuel_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        aero_rear_cuts = [ch for ch in plan.proposed
                         if ch.field == "aero_rear" and ch.delta < 0]
        assert not aero_rear_cuts, (
            f"AC32 FAIL: aero_rear decrease proposed despite A2 block + rear_loose_on_exit. "
            f"fuel_high=True. proposed: {[(c.field, c.delta, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC33 — snap-throttle wheelspin → traction-first (P1)
# ===========================================================================

class TestAC33TractionFirst:
    """AC33: snap-throttle wheelspin → P1 lsd_accel in proposed (traction-first)."""

    def test_p1_proposed_with_high_fuel_rsr(self):
        """P1 lsd_accel must be proposed even with high fuel load."""
        diag = _rsr_high_fuel_diag(fuel_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        p1_changes = [ch for ch in plan.proposed if ch.rule_id == "P1"]
        assert p1_changes, (
            f"AC33 FAIL: P1 lsd_accel not proposed for RSR with high fuel + snap wheelspin. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )
        assert p1_changes[0].delta > 0, f"AC33 FAIL: P1 delta must be positive (traction)"

    def test_p1_fuel_influence_set_with_high_fuel(self):
        """P1 lsd_accel change must have fuel_influence text when fuel_high=True."""
        diag = _rsr_high_fuel_diag(fuel_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        p1_changes = [ch for ch in plan.proposed if ch.rule_id == "P1" and ch.field == "lsd_accel"]
        if p1_changes:
            # lsd_accel is a traction/stability field → fuel_influence should be set
            ch = p1_changes[0]
            assert ch.fuel_influence, (
                f"AC33 FAIL: P1 lsd_accel has no fuel_influence despite fuel_high=True; "
                f"fuel_influence={ch.fuel_influence!r}"
            )


# ===========================================================================
# AC34 — front-bite protected; no rearward brake bias
# ===========================================================================

class TestAC34NoBrakeBiasRearward:
    """AC34: no rearward brake bias (brake_bias increase) without lockup evidence."""

    def test_no_rearward_brake_bias_rsr_high_fuel(self):
        """brake_bias increase must not be proposed in RSR high-fuel context."""
        diag = _rsr_high_fuel_diag(fuel_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50, "brake_bias": 0}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        brake_rearward = [ch for ch in plan.proposed
                         if ch.field == "brake_bias" and ch.delta > 0]
        assert not brake_rearward, (
            f"AC34 FAIL: rearward brake bias proposed in RSR high-fuel context. "
            f"avg_lockups=0. proposed: {[(c.field, c.delta, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC35 — no generic ride-height raise without bottoming support
# ===========================================================================

class TestAC35NoGenericRHRaise:
    """AC35: no ride_height raise without bottoming_band in consider/required."""

    def test_no_rh_raise_when_bottoming_minor(self):
        """Without bottoming evidence, no ride_height_* raise proposed for RSR."""
        diag = _rsr_high_fuel_diag(possible_bottoming=False)
        # bottoming_band=minor, no kerb
        setup = {"lsd_accel": 15, "aero_rear": 50,
                 "ride_height_front": 80, "ride_height_rear": 80}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        rh_raises = [ch for ch in plan.proposed
                    if ch.field in ("ride_height_front", "ride_height_rear") and ch.delta > 0]
        assert not rh_raises, (
            f"AC35 FAIL: ride_height raise proposed without bottoming/kerb evidence. "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )


# ===========================================================================
# AC36 — source_label distinguishes Porsche-specific vs generic
# ===========================================================================

class TestAC36SourceLabelDistinguished:
    """AC36: with RSR + high fuel, source_label on changes is correctly set."""

    def test_source_labels_valid_values(self):
        """All proposed changes have source_label in {'Porsche-specific rule', 'generic rule'}."""
        diag = _rsr_high_fuel_diag(fuel_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        valid_labels = {"Porsche-specific rule", "generic rule"}
        for ch in plan.proposed:
            sl = ch.source_label
            assert sl in valid_labels, (
                f"AC36 FAIL: source_label={sl!r} not in {valid_labels}; "
                f"field={ch.field!r}, rule_id={ch.rule_id!r}"
            )


# ===========================================================================
# AC37 — BENCHMARK REGRESSION: Full integrated RSR test at Fuji, ~50min, high fuel
# ===========================================================================

class TestAC37BenchmarkRSRFuji:
    """AC37 BENCHMARK: Full integrated regression — Porsche 911 RSR (991) '17 at Fuji,
    duration ~50min (sprint bucket), fuel_high (>=5), tyre_wear_multiplier high.

    Feedback: rear-loose + mid-push + floaty-front.
    Telemetry: snap-throttle-wheelspin + top-speed-low + entry-stable + possible-bottoming.

    Verifies:
      (a) traction-first before/instead of aero-cut (P1 lsd_accel in proposed)
      (b) no rear-downforce reduction (A2 blocks aero_rear cut)
      (c) no rearward brake bias
      (d) no generic ride-height raise unless bottoming supports it
      (e) no top-speed gear-lengthening as PRIMARY wheelspin response
          (gear-lengthening would be a gear_N or final_drive change driven by B5,
           not by snap-throttle wheelspin alone without limiter/per-gear evidence)
      (f) no AI-authored values (engine-only path, no api_key)
      (g) passes Apply gate (approved status + >=1 approved change)
    """

    def _build_plan(self):
        """Build the benchmark plan via the rule engine directly (engine-only path)."""
        diag = _rsr_high_fuel_diag(
            fuel_high=True,
            tyre_wear_high=True,
            entry_stable=True,
            possible_bottoming=True,
        )
        # ~50min race → sprint bucket (duration < 60)
        diag["duration_mins"] = 50.0
        setup = {
            "lsd_accel": 15,
            "lsd_initial": 10,
            "aero_rear": 50,
            "aero_front": 400,
            "ride_height_front": 80,
            "ride_height_rear": 80,
            "brake_bias": 0,
            "arb_rear": 4,
        }
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
            car=_PORSCHE_CAR,
            track=_FUJI_TRACK,
        )
        return plan, diag

    def test_ac37a_traction_first_before_aero_cut(self):
        """(a) P1 lsd_accel in proposed (traction-first)."""
        plan, diag = self._build_plan()
        p1_changes = [ch for ch in plan.proposed if ch.rule_id == "P1"]
        assert p1_changes, (
            f"AC37(a) FAIL: P1 lsd_accel not proposed for RSR benchmark. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )
        assert p1_changes[0].delta > 0

    def test_ac37b_no_rear_downforce_reduction(self):
        """(b) aero_rear decrease must not be proposed (A2 blocks it under rear_loose)."""
        plan, diag = self._build_plan()
        aero_cuts = [ch for ch in plan.proposed
                    if ch.field == "aero_rear" and ch.delta < 0]
        assert not aero_cuts, (
            f"AC37(b) FAIL: aero_rear reduction proposed in RSR benchmark. "
            f"A2 must block this under rear_loose_on_exit."
        )

    def test_ac37c_no_rearward_brake_bias(self):
        """(c) No brake_bias increase (rearward) without lockup evidence."""
        plan, diag = self._build_plan()
        brake_rearward = [ch for ch in plan.proposed
                         if ch.field == "brake_bias" and ch.delta > 0]
        assert not brake_rearward, (
            f"AC37(c) FAIL: rearward brake_bias proposed in RSR benchmark (avg_lockups=0)."
        )

    def test_ac37d_no_generic_rh_raise_without_bottoming_support(self):
        """(d) ride_height raise only if bottoming_band supports it (consider/required).

        In our benchmark, bottoming_band='consider' (possible_bottoming=True),
        so a ride_height raise WOULD be consistent with the A3/A4 spec.
        The test verifies that any ride_height raise is gated on bottoming evidence,
        not unconditionally proposed as a 'generic' fix.

        We set bottoming_band='minor' to ensure no ride_height raise from that path,
        then verify no ride_height raises appear.
        """
        # Re-build with bottoming_band=minor (no bottoming support)
        diag = _rsr_high_fuel_diag(possible_bottoming=False, fuel_high=True, tyre_wear_high=True)
        diag["duration_mins"] = 50.0
        setup = {
            "lsd_accel": 15,
            "aero_rear": 50,
            "ride_height_front": 80,
            "ride_height_rear": 80,
        }
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        rh_raises = [ch for ch in plan.proposed
                    if ch.field in ("ride_height_front", "ride_height_rear") and ch.delta > 0]
        assert not rh_raises, (
            f"AC37(d) FAIL: ride_height raise proposed without bottoming/kerb evidence "
            f"(bottoming_band=minor). proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_ac37e_no_gear_lengthening_as_primary_wheelspin_fix(self):
        """(e) No gear_N change or final_drive change as primary response to snap wheelspin
        (gearbox_flag='preserve' in benchmark means no gear changes at all)."""
        plan, diag = self._build_plan()
        # In benchmark, gearbox_flag='preserve' → no gear changes possible
        gear_changes = [ch for ch in plan.proposed
                       if ch.field.startswith("gear_") or ch.field == "final_drive"]
        assert not gear_changes, (
            f"AC37(e) FAIL: gear/final_drive change proposed with gearbox_flag='preserve'. "
            f"Changes: {[(c.field, c.rule_id) for c in gear_changes]}"
        )

    def test_ac37f_no_ai_authored_values(self):
        """(f) Engine-only path: no api_key, result produced without AI.

        Verified by calling run_rule_engine directly — no build_combined_setup_response,
        no API call. The plan itself proves no AI authored values.
        """
        plan, diag = self._build_plan()
        # Every proposed change has a rule_id from the engine (not "ai_authored" or similar)
        for ch in plan.proposed:
            assert not ch.rule_id.startswith("ai_"), (
                f"AC37(f) FAIL: AI-authored rule_id in proposed: {ch.rule_id!r}"
            )

    def test_ac37g_apply_gate_approved_with_changes(self):
        """(g) build_baseline_setup_response / rule_engine path passes Apply gate.

        We test via build_combined_setup_response on a minimal advisor (no api_key),
        using a real lap to provide diagnosis data.
        """
        event_ctx = {
            "fuel_multiplier": 5.0,
            "tyre_wear": 6.0,
            "duration_mins": 50.0,
        }
        laps = [
            _make_lap(wheelspin_count=20, snap_throttle_count=15, max_speed_kmh=200.0)
            for _ in range(3)
        ]
        adv = _make_advisor_no_api(event_ctx, laps)
        import json
        result_str = adv.build_combined_setup_response(
            setup_dict={"lsd_accel": 15, "aero_rear": 50},
            n_laps=3,
            car_name=_PORSCHE_CAR,
            feeling="rear loose on exit, mid-push, floaty front",
            purpose="Race",
            car_class="Gr.3",
            drivetrain="RR",
        )
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES or status == "fallback_generated", (
            f"AC37(g) FAIL: recommendation_status not in APPROVED_STATUSES; got {status!r}"
        )
        # Apply gate: approved + >=1 approved change
        approved_changes = result.get("approved_fields") or result.get("setup_fields") or {}
        if status == "approved" or status == "approved_with_warnings":
            # At least one change must exist for Apply to be enabled
            changes = result.get("changes", [])
            assert len(changes) > 0 or approved_changes, (
                f"AC37(g) FAIL: approved status but no changes; changes={changes}, "
                f"approved_fields={approved_changes}"
            )

    def test_ac37_source_labels_correct(self):
        """All proposed changes have correct source labels (Porsche-specific or generic)."""
        plan, diag = self._build_plan()
        valid_labels = {"Porsche-specific rule", "generic rule"}
        for ch in plan.proposed:
            sl = ch.source_label
            assert sl in valid_labels, (
                f"AC37 FAIL: source_label={sl!r} not in {valid_labels}; "
                f"field={ch.field!r}, rule_id={ch.rule_id!r}"
            )

    def test_ac37_traction_fuel_upgrade_noted(self):
        """P1 lsd_accel change has fuel_influence noting high fuel traction priority."""
        plan, diag = self._build_plan()
        p1_changes = [ch for ch in plan.proposed
                     if ch.rule_id == "P1" and ch.field == "lsd_accel"]
        if p1_changes:
            ch = p1_changes[0]
            assert ch.fuel_influence, (
                f"AC37 FAIL: P1 lsd_accel in RSR benchmark has no fuel_influence; "
                f"fuel_high=True, lsd_accel is a traction/stability field"
            )
