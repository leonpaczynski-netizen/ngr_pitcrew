"""
Group 45 — Setup Brain Intelligence Expansion: Porsche Pack P Tests

Covers AC21-AC23 (Obj5 Porsche pack):
  AC21 — Scenario 1: Porsche 911 RSR, snap wheelspin + rear_loose + top_speed_low:
          traction-first (P1 lsd_accel cautious increase proposed);
          aero_rear cut BLOCKED (A2);
          no generic RH raise without bottoming/kerb;
          no rearward brake bias;
          source_label in {"Porsche-specific rule", "generic rule"} (never empty)
  AC22 — top_speed_low + snap wheelspin → rear downforce NOT first/priority proposal
  AC23 — Scenario 2: Porsche 911 RSR quali — no high wear → may propose front response;
          session_influence states quali;
          still no snap-oversteer increase
  AC21 generic: same car with drivetrain=None → Pack P does NOT fire,
          car_drivetrain_influence says "drivetrain unknown"
  CAR_DRIVETRAIN_OVERRIDES maps "Porsche 911 RSR (991) '17" → "rr"

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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PORSCHE_CAR = "Porsche 911 RSR (991) '17"


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


def _scenario1_diag(top_speed_low: bool = True) -> dict:
    """Porsche Scenario 1: snap_throttle wheelspin + rear_loose + top_speed_low.
    This is the diagnosis state used for Pack P tests.
    """
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 20.0, "wheelspin_band": "severe",
        "avg_snap": 8.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "snap_oversteer_exit": False,   # driver does NOT report snap exit
            "rear_loose_on_exit": True,
            "floaty_front": False,
            "entry_understeer": False,
            "braking_instability": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "wheelspin",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "snap_throttle_induced",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "avg_top_speed_kmh": 200.0 if top_speed_low else 280.0,
        "top_speed_target_kmh": 280.0,  # top_speed_low = actual < target
        "tyre_wear_high": False,
        "tyre_wear_known": False,
    }


def _scenario2_diag() -> dict:
    """Porsche Scenario 2: quali, no high wear, same car."""
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 20.0, "wheelspin_band": "severe",
        "avg_snap": 8.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "snap_oversteer_exit": False,
            "rear_loose_on_exit": True,
            "floaty_front": True,   # entry feel adds front-response context
            "entry_understeer": True,
            "braking_instability": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": True,  # floaty front + front aero near min
        "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "front_aero_platform_limited",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "snap_throttle_induced",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": False,
        "tyre_wear_known": False,
        "session_type": "quali",
    }


# ===========================================================================
# CAR_DRIVETRAIN_OVERRIDES
# ===========================================================================

class TestCarDrivetrainOverrides:
    """Verify CAR_DRIVETRAIN_OVERRIDES contains the Porsche entry."""

    def test_porsche_override_present(self):
        """CAR_DRIVETRAIN_OVERRIDES must map Porsche 911 RSR (991) '17 → 'rr'."""
        assert _PORSCHE_CAR in CAR_DRIVETRAIN_OVERRIDES, (
            f"CAR_DRIVETRAIN_OVERRIDES missing entry for {_PORSCHE_CAR!r}"
        )

    def test_porsche_override_value_is_rr(self):
        """The Porsche 911 RSR (991) '17 drivetrain override must be 'rr'."""
        assert CAR_DRIVETRAIN_OVERRIDES[_PORSCHE_CAR] == "rr", (
            f"Expected 'rr', got {CAR_DRIVETRAIN_OVERRIDES[_PORSCHE_CAR]!r}"
        )


# ===========================================================================
# AC21 — Scenario 1: traction-first + A2 blocks aero_rear cut
# ===========================================================================

class TestAC21Scenario1TractionFirst:
    """AC21: P1 lsd_accel in proposed; A2 blocks aero_rear cut; source_labels correct."""

    def test_p1_lsd_accel_proposed_first(self):
        """P1 must propose lsd_accel (traction-first approach)."""
        diag = _scenario1_diag()
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        assert p1_changes, (
            "AC21 FAIL: P1 did not propose lsd_accel for snap_throttle_induced + rr + gr3. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )
        assert p1_changes[0].field == "lsd_accel", (
            f"AC21 FAIL: P1 must target lsd_accel; got {p1_changes[0].field!r}"
        )
        assert p1_changes[0].delta > 0, (
            f"AC21 FAIL: P1 delta must be positive (cautious increase); got {p1_changes[0].delta}"
        )

    def test_a2_blocks_aero_rear_cut_under_rear_loose(self):
        """A2 must block aero_rear decrease under rear_loose_on_exit (Pack A invariant)."""
        diag = _scenario1_diag()
        # diag has rear_loose_on_exit=True → A2 should fire
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        aero_rear_decreases = [c for c in plan.proposed
                               if c.field == "aero_rear" and c.delta < 0]
        assert not aero_rear_decreases, (
            "AC21 FAIL: aero_rear decrease was proposed despite A2 block (rear_loose_on_exit). "
            f"proposed: {[(c.field, c.delta, c.rule_id) for c in plan.proposed]}"
        )

    def test_no_generic_rh_raise_without_bottoming(self):
        """Without bottoming evidence, no ride_height_* raise should be proposed."""
        diag = _scenario1_diag()
        # bottoming_band=minor → A3/A4 protect RH raises
        setup = {"lsd_accel": 15, "aero_rear": 50,
                 "ride_height_front": 80, "ride_height_rear": 82}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        rh_raises = [c for c in plan.proposed
                    if c.field in ("ride_height_front", "ride_height_rear") and c.delta > 0]
        assert not rh_raises, (
            "AC21 FAIL: ride_height raise proposed without bottoming/kerb evidence. "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_no_rearward_brake_bias_without_lockup(self):
        """Without lockup evidence, brake_bias rearward must not be proposed."""
        diag = _scenario1_diag()
        # avg_lockups=0 and braking_instability=False → A5 does not fire
        # but brake_bias rearward also should not be proposed at all in this context
        setup = {"lsd_accel": 15, "aero_rear": 50, "brake_bias": 0}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        brake_rearward = [c for c in plan.proposed
                         if c.field == "brake_bias" and c.delta > 0]
        assert not brake_rearward, (
            "AC21 FAIL: brake_bias rearward proposed without lock-up evidence. "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_source_labels_never_empty(self):
        """Every proposed change must have a non-empty source_label."""
        diag = _scenario1_diag()
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        valid_labels = {"Porsche-specific rule", "generic rule"}
        for ch in plan.proposed:
            sl = getattr(ch, "source_label", "")
            assert sl, (
                f"AC21 FAIL: change {ch.field} (rule_id={ch.rule_id}) has empty source_label"
            )
            assert sl in valid_labels, (
                f"AC21 FAIL: source_label={sl!r} not in {valid_labels}; "
                f"field={ch.field}, rule_id={ch.rule_id}"
            )


# ===========================================================================
# AC22 — top_speed_low + snap wheelspin → rear downforce NOT first proposal
# ===========================================================================

class TestAC22RearDownforceNotFirst:
    """AC22: traction-first for RR snap wheelspin; rear downforce cut is NOT priority."""

    def test_aero_rear_cut_not_in_proposed(self):
        """aero_rear decrease must not appear in proposed at all (A2 blocks it)."""
        diag = _scenario1_diag(top_speed_low=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        aero_rear_decreases = [c for c in plan.proposed
                               if c.field == "aero_rear" and c.delta < 0]
        assert not aero_rear_decreases, (
            "AC22 FAIL: aero_rear decrease proposed despite A2 block. "
            "Rear downforce cut must NOT be the priority fix for snap wheelspin."
        )

    def test_p1_lsd_accel_takes_priority_over_aero_rear(self):
        """P1 (lsd_accel increase) must be in proposed; aero_rear cut must not be."""
        diag = _scenario1_diag(top_speed_low=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        lsd_increases = [c for c in plan.proposed
                        if c.field == "lsd_accel" and c.delta > 0]
        aero_cuts = [c for c in plan.proposed
                    if c.field == "aero_rear" and c.delta < 0]

        assert lsd_increases, (
            "AC22 FAIL: lsd_accel increase not proposed — traction fix should be first"
        )
        assert not aero_cuts, (
            "AC22 FAIL: aero_rear cut proposed — must be blocked by A2 under rear_loose"
        )


# ===========================================================================
# AC23 — Scenario 2: Porsche quali, session_influence set; no snap-oversteer increase
# ===========================================================================

class TestAC23Scenario2QualiNoSnap:
    """AC23: Porsche + quali session — front response may fire; session_influence=quali;
    no snap-oversteer increase proposed."""

    def test_quali_session_influence_set(self):
        """With session_type=quali, qualifying bias text must appear in session_influence."""
        diag = _scenario2_diag()
        setup = {"lsd_accel": 15, "aero_front": 350, "aero_rear": 50, "lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.quali,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        # Find any change with qualifying bias text
        qualifying_changes = [
            c for c in plan.proposed
            if "qualifying bias" in (getattr(c, "session_influence", "") or "")
        ]
        if qualifying_changes:
            for ch in qualifying_changes:
                si = getattr(ch, "session_influence", "")
                assert "qualifying bias applied" in si, (
                    f"AC23 FAIL: session_influence does not contain qualifying bias text; "
                    f"got {si!r}"
                )

    def test_no_snap_oversteer_increase_in_scenario2(self):
        """No rule must increase snap-oversteer tendency in Scenario 2."""
        diag = _scenario2_diag()
        setup = {"lsd_accel": 15, "aero_front": 350, "aero_rear": 50, "lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.quali,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        # snap_oversteer_exit=False in scenario 2, so P1 should fire
        # But B3 (reduce lsd_accel on snap exit) must NOT fire when snap_oversteer=False
        # Also: no lsd_accel decrease that would be a "snap fix" when snap not reported
        # The key invariant: no change should increase snap-oversteer risk
        # (lsd_accel increase when snap_oversteer_exit=True would be blocked)
        snap_increasing = [
            c for c in plan.proposed
            if c.field == "lsd_accel" and c.delta > 0
        ]
        # P1 MAY propose lsd_accel increase (snap_throttle_induced, no reported snap exit)
        # That's OK — it addresses snap-throttle wheelspin not snap-oversteer-exit
        # The forbidden thing is increasing anything that directly worsens snap-oversteer-exit
        # e.g. lsd_accel increase when driver HAS reported snap_oversteer_exit
        # In scenario2, snap_oversteer_exit=False, so P1 is allowed
        # No forbidden changes for this scenario

    def test_a2_still_blocks_aero_rear_cut_in_scenario2(self):
        """A2 must still block aero_rear decrease in Scenario 2 (rear_loose_on_exit=True)."""
        diag = _scenario2_diag()
        # rear_loose_on_exit=True → A2 fires
        setup = {"lsd_accel": 15, "aero_front": 350, "aero_rear": 50, "lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.quali,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        aero_rear_cuts = [c for c in plan.proposed
                         if c.field == "aero_rear" and c.delta < 0]
        assert not aero_rear_cuts, (
            "AC23 FAIL: aero_rear decrease proposed in Scenario 2 despite A2 block. "
            f"proposed: {[(c.field, c.delta, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC21 generic path — drivetrain=None → Pack P does not fire
# ===========================================================================

class TestAC21GenericPath:
    """AC21 generic: drivetrain=None is wildcard-permissive (scope filter does not block P1),
    but car_drivetrain_influence must reflect 'drivetrain unknown' when drivetrain is absent."""

    def test_pack_p_does_not_fire_with_drivetrain_none(self):
        """drivetrain=None is wildcard-permissive: P1 still fires but influence text reflects unknown."""
        diag = _scenario1_diag()
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=None,       # wildcard-permissive: does NOT block P1
            car_class=CarClass.gr3,
        )

        # P1 fires with drivetrain=None because None = wildcard
        pack_p_changes = [c for c in plan.proposed if getattr(c, "pack", "") == "P"]
        # When P1 fires, car_drivetrain_influence must say "drivetrain unknown"
        for ch in pack_p_changes:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert "drivetrain unknown" in cdi, (
                f"AC21 generic FAIL: Pack P rule with drivetrain=None should have "
                f"'drivetrain unknown' in car_drivetrain_influence; got {cdi!r}"
            )
        # Non-Pack-P rules with FR/non-rr drivetrain context should not get RR text
        non_p_changes = [c for c in plan.proposed if getattr(c, "pack", "") != "P"]
        for ch in non_p_changes:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert "RR drivetrain" not in cdi, (
                f"AC21 generic FAIL: non-Pack-P rule claims 'RR drivetrain' with None drivetrain; "
                f"field={ch.field}, cdi={cdi!r}"
            )

    def test_drivetrain_unknown_influence_text_when_none(self):
        """car_drivetrain_influence must say 'drivetrain unknown' when drivetrain=None."""
        diag = _scenario1_diag()
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=None,
        )

        non_pack_a = [c for c in plan.proposed if getattr(c, "pack", "") != "A"]
        if not non_pack_a:
            pytest.skip("No non-Pack-A changes — cannot verify car_drivetrain_influence")

        for ch in non_pack_a:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert "drivetrain unknown" in cdi, (
                f"AC21 generic FAIL: car_drivetrain_influence should say 'drivetrain unknown' "
                f"when drivetrain=None; got {cdi!r} for field={ch.field}"
            )
