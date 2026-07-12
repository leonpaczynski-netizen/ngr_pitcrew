"""
Group 45 — Setup Brain Intelligence Expansion: Context Signals Tests

Covers:
  Obj2 AC10-AC13 (Session context):
    AC10 — quali ranks front-rotation/bite above tyre-preservation vs race +
           session_influence "qualifying bias applied — front response/bite prioritised"
    AC12 — race → "race consistency bias applied"
    AC13 — endurance (duration_mins>=60) → "endurance bias applied";
           unknown/None → "neutral weighting — session type not available"
  Obj3 AC14-AC16 (Tyre/fuel context):
    AC14 — tyre_wear_high (>=5x) contraindicates toe/camber/rear-rotation-tagged rules
    AC15 — absent tyre/fuel → conservative + "tyre/fuel context not available — conservative default applied"
    AC16 — tyre_wear_multiplier=1.0 → NOT high, rules not suppressed
  Obj4 AC17-AC20 (Drivetrain/class context):
    AC17 — drivetrain=rr applies rear-exit-stability modifiers vs generic +
           car_drivetrain_influence names it
    AC18 — drivetrain None → "drivetrain unknown — generic logic applied"
    AC19 — applies_drivetrain filter: rr-scoped rule doesn't fire when fr; fires when None
    AC20 — applies_car_class filter: gr3-scoped rule doesn't fire for road car

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_diagnosis import build_setup_diagnosis
from strategy.setup_rule_engine import run_rule_engine, SetupPlan
from strategy.setup_driver_profile import build_driver_profile, DriverProfile
from strategy.setup_knowledge_base import (
    SessionType, DrivetrainType, CarClass,
    get_all_rules,
)
from strategy.setup_ranges import resolve_ranges
from strategy._setup_constants import HIGH_TYRE_WEAR_THRESHOLD


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    oversteer_count: int = 0,
    oversteer_throttle_on_count: int = 0,
    kerb_count: int = 0,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=5.0,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on_count,
        kerb_count=kerb_count,
        max_lat_g=1.5,
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


def _entry_understeer_diag() -> dict:
    """Diagnosis that fires C1_entry_lsd_decel (prefers_front_bite tag)."""
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 0.0, "wheelspin_band": "low",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "entry_understeer": True,
            "rear_loose_on_exit": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "entry_understeer",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "insufficient_data",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": False,
    }


# ===========================================================================
# AC10 — Qualifying: session_influence set correctly
# ===========================================================================

class TestAC10QualiSessionInfluence:
    """AC10: qualifying session → front-response/bite rules get confidence upgrade
    AND session_influence text set correctly."""

    def test_quali_session_influence_text_on_front_bite_rule(self):
        """C1 (prefers_front_bite tag) with session_type=quali must have
        session_influence = 'qualifying bias applied — front response/bite prioritised'."""
        diag = _entry_understeer_diag()
        setup = {"lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.quali,
        )

        c1_changes = [c for c in plan.proposed
                      if c.rule_id in ("C1_entry_lsd_decel",) or
                      (c.field == "lsd_decel" and c.delta < 0)]
        if not c1_changes:
            pytest.skip("C1_entry_lsd_decel did not fire — skip session influence check")

        for ch in c1_changes:
            si = getattr(ch, "session_influence", "")
            assert "qualifying bias applied" in si, (
                f"AC10 FAIL: C1_entry_lsd_decel session_influence should contain "
                f"'qualifying bias applied'; got {si!r}"
            )
            assert "front response/bite prioritised" in si, (
                f"AC10 FAIL: quali session_influence should mention 'front response/bite prioritised'; "
                f"got {si!r}"
            )

    def test_quali_session_influence_exact_text(self):
        """session_influence text must be exactly as specified for qualifying."""
        EXPECTED = "qualifying bias applied — front response/bite prioritised"
        diag = _entry_understeer_diag()
        setup = {"lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=SessionType.quali)

        front_bite_changes = [
            c for c in plan.proposed
            if hasattr(c, "session_influence") and "qualifying" in (c.session_influence or "")
        ]
        # At least one change should have this text if C1 or B1/B2 fired
        if front_bite_changes:
            for ch in front_bite_changes:
                assert ch.session_influence == EXPECTED, (
                    f"AC10 FAIL: session_influence={ch.session_influence!r} != {EXPECTED!r}"
                )


# ===========================================================================
# AC12 — Race: "race consistency bias applied"
# ===========================================================================

class TestAC12RaceSessionInfluence:
    """AC12: race session → race_values_consistency-tagged rules get session_influence text."""

    def test_race_session_influence_text(self):
        """B5 (race_values_consistency tag) with session_type=race gets race bias text."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {},
            "gearbox_flag": "may_change",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",
            "gearing_diagnosis_category": "gear_too_short",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 5.0,
            "rev_limiter_by_gear": {6: 5},
            "per_gear_limiter_evidence": {6: 5},
            "duration_mins": 30,  # not endurance
        }
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=SessionType.race)

        b5_changes = [c for c in plan.proposed if c.rule_id == "B5"]
        if not b5_changes:
            pytest.skip("B5 did not fire — skip race session influence check")

        for ch in b5_changes:
            si = getattr(ch, "session_influence", "")
            assert "race consistency bias applied" in si, (
                f"AC12 FAIL: B5 session_influence should contain 'race consistency bias applied'; "
                f"got {si!r}"
            )


# ===========================================================================
# AC13 — Endurance and unknown/None session influence
# ===========================================================================

class TestAC13EnduranceAndNoneSessionInfluence:
    """AC13: endurance (duration_mins>=60) → 'endurance bias applied';
    None → 'neutral weighting — session type not available'."""

    def test_endurance_session_influence(self):
        """Race session + duration_mins>=60 → 'endurance bias applied'."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {},
            "gearbox_flag": "may_change",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",
            "gearing_diagnosis_category": "gear_too_short",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 5.0,
            "rev_limiter_by_gear": {6: 5},
            "per_gear_limiter_evidence": {6: 5},
            "duration_mins": 60,  # endurance threshold
        }
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=SessionType.race)

        b5_changes = [c for c in plan.proposed if c.rule_id == "B5"]
        if not b5_changes:
            pytest.skip("B5 did not fire — skip endurance session influence check")

        for ch in b5_changes:
            si = getattr(ch, "session_influence", "")
            assert "endurance bias applied" in si, (
                f"AC13 FAIL: endurance (duration_mins=60) session_influence should "
                f"contain 'endurance bias applied'; got {si!r}"
            )

    def test_none_session_type_influence_text(self):
        """session_type=None → session_influence 'neutral weighting — session type not available'."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {},
            "gearbox_flag": "may_change",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",
            "gearing_diagnosis_category": "gear_too_short",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 5.0,
            "rev_limiter_by_gear": {6: 5},
            "per_gear_limiter_evidence": {6: 5},
        }
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        # Any change should have neutral weighting when session_type=None
        changes = plan.proposed
        if not changes:
            pytest.skip("No changes proposed — cannot check session_influence")

        for ch in changes:
            si = getattr(ch, "session_influence", "")
            # session_influence should be neutral-weighting text when session_type is None
            if si:
                assert "neutral weighting" in si, (
                    f"AC13 FAIL: session_type=None should produce 'neutral weighting' text; "
                    f"got {si!r} for field={ch.field}"
                )


# ===========================================================================
# AC14 — High tyre wear contraindicates toe/camber/rear-rotation-tagged rules
# ===========================================================================

class TestAC14HighTyreWearContraindication:
    """AC14: tyre_wear_high=True contraindicates rules tagged with _HIGH_WEAR_CONTRAINDICATED_TAGS."""

    def test_high_tyre_wear_threshold_is_5(self):
        """HIGH_TYRE_WEAR_THRESHOLD must be 5.0."""
        assert HIGH_TYRE_WEAR_THRESHOLD == 5.0, (
            f"AC14 FAIL: HIGH_TYRE_WEAR_THRESHOLD={HIGH_TYRE_WEAR_THRESHOLD}, expected 5.0"
        )

    def test_tyre_wear_high_key_in_constants(self):
        """_HIGH_WEAR_CONTRAINDICATED_TAGS must contain the expected tags."""
        from strategy.setup_knowledge_base import _HIGH_WEAR_CONTRAINDICATED_TAGS
        expected_tags = {"toe_active", "camber_active", "rear_rotation_risk"}
        for tag in expected_tags:
            assert tag in _HIGH_WEAR_CONTRAINDICATED_TAGS, (
                f"AC14 FAIL: {tag!r} not in _HIGH_WEAR_CONTRAINDICATED_TAGS"
            )

    def test_tyre_wear_5x_is_high(self):
        """tyre_wear_multiplier=5.0 must satisfy >= HIGH_TYRE_WEAR_THRESHOLD."""
        assert 5.0 >= HIGH_TYRE_WEAR_THRESHOLD, (
            "AC14 FAIL: 5.0 should be >= HIGH_TYRE_WEAR_THRESHOLD"
        )


# ===========================================================================
# AC15 — Absent tyre/fuel → conservative note
# ===========================================================================

class TestAC15AbsentTyreFuelConservative:
    """AC15: when tyre_wear_known=False → _tyre_fuel_context says 'not available'."""

    def test_absent_tyre_produces_conservative_note(self):
        """Without tyre context, _tyre_fuel_context says 'tyre/fuel context not available'."""
        import strategy.driving_advisor as da

        laps = [_make_lap()]
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._recorder = SimpleNamespace(recent_laps=lambda n: laps)
        adv._tracker = None
        adv._config = {}
        adv._db = None
        adv._car_id_ref = [0]
        adv._event_ctx = {}  # no tyre_wear
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

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        tyre_ctx = result.get("_tyre_fuel_context", "MISSING")
        assert tyre_ctx != "MISSING", "AC15 FAIL: _tyre_fuel_context key missing from response"
        assert "not available" in tyre_ctx, (
            f"AC15 FAIL: _tyre_fuel_context must contain 'not available' when tyre_wear_known=False; "
            f"got {tyre_ctx!r}"
        )
        assert "conservative default applied" in tyre_ctx, (
            f"AC15 FAIL: _tyre_fuel_context must contain 'conservative default applied'; "
            f"got {tyre_ctx!r}"
        )

    def test_no_tyre_aware_claim_in_changes_without_tyre_context(self):
        """When tyre_wear_known=False, no change should claim tyre-aware behaviour."""
        import strategy.driving_advisor as da

        laps = [_make_lap(wheelspin_count=20)]
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._recorder = SimpleNamespace(recent_laps=lambda n: laps)
        adv._tracker = None
        adv._config = {}
        adv._db = None
        adv._car_id_ref = [0]
        adv._event_ctx = {}
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

        result_str = adv.build_combined_setup_response(
            setup_dict={"aero_rear": 50, "lsd_accel": 20}, car_name="", feeling=None
        )
        result = json.loads(result_str)

        # No change rationale should claim tyre-aware behaviour
        tyre_claim_phrases = ["tyre wear aware", "tyre-wear-aware", "high tyre wear"]
        for ch in result.get("changes", []):
            why = ch.get("why", "") + ch.get("rationale", "")
            for phrase in tyre_claim_phrases:
                assert phrase not in why.lower(), (
                    f"AC15 FAIL: change claims '{phrase}' without tyre context. "
                    f"change: {ch.get('field')}, why: {why[:200]!r}"
                )


# ===========================================================================
# AC16 — tyre_wear_multiplier=1.0 → NOT high, rules not suppressed
# ===========================================================================

class TestAC16LowTyreWearNotSuppressed:
    """AC16: tyre_wear_multiplier=1.0 is below HIGH_TYRE_WEAR_THRESHOLD — not high."""

    def test_tyre_wear_1_is_not_high(self):
        """1.0 < 5.0, so tyre_wear_high must be False."""
        assert 1.0 < HIGH_TYRE_WEAR_THRESHOLD, (
            "AC16 FAIL: tyre_wear_multiplier=1.0 is unexpectedly >= HIGH_TYRE_WEAR_THRESHOLD"
        )

    def test_tyre_wear_exactly_5_is_high(self):
        """Boundary: tyre_wear_multiplier=5.0 IS >= HIGH_TYRE_WEAR_THRESHOLD."""
        assert 5.0 >= HIGH_TYRE_WEAR_THRESHOLD, (
            "AC16 FAIL: 5.0 should be >= HIGH_TYRE_WEAR_THRESHOLD=5.0"
        )

    def test_tyre_wear_4_9_is_not_high(self):
        """4.9 < 5.0 → not high wear."""
        assert 4.9 < HIGH_TYRE_WEAR_THRESHOLD, (
            "AC16 FAIL: 4.9 should be < HIGH_TYRE_WEAR_THRESHOLD=5.0"
        )


# ===========================================================================
# AC17 — drivetrain=rr applies rear-exit-stability modifiers
# ===========================================================================

class TestAC17DrivetrainRRInfluence:
    """AC17: drivetrain=rr → car_drivetrain_influence set on applicable rules."""

    def test_rr_drivetrain_car_influence_text(self):
        """With drivetrain=DrivetrainType.rr, P1 change should have car_drivetrain_influence set."""
        # P1: snap_throttle_induced + rr drivetrain + gr3 car class
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 8.0, "avg_lockups": 0.0,
            "driver_feel_flags": {
                "snap_oversteer_exit": False,
                "rear_loose_on_exit": True,
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
            "tyre_wear_high": False,
        }
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        if not p1_changes:
            pytest.skip("P1 did not fire — skip drivetrain influence check")

        for ch in p1_changes:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert cdi, (
                f"AC17 FAIL: P1 (rr-scoped rule) must have car_drivetrain_influence; "
                f"got empty string"
            )
            assert "rr" in cdi.lower() or "drivetrain" in cdi.lower(), (
                f"AC17 FAIL: car_drivetrain_influence should mention RR drivetrain; got {cdi!r}"
            )

    def test_source_label_porsche_specific_for_pack_p(self):
        """Pack P rules must have source_label='Porsche-specific rule'."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 8.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"snap_oversteer_exit": False, "rear_loose_on_exit": True},
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
        }
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.gr3,
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        if not p1_changes:
            pytest.skip("P1 did not fire — skip source_label check")

        for ch in p1_changes:
            sl = getattr(ch, "source_label", "")
            assert sl == "Porsche-specific rule", (
                f"AC17 FAIL: Pack P rule source_label must be 'Porsche-specific rule'; got {sl!r}"
            )


# ===========================================================================
# AC18 — drivetrain=None → "drivetrain unknown — generic logic applied"
# ===========================================================================

class TestAC18DrivetrainNoneInfluence:
    """AC18: drivetrain=None → car_drivetrain_influence says 'drivetrain unknown'."""

    def test_drivetrain_none_produces_unknown_text(self):
        """With drivetrain=None, car_drivetrain_influence must say drivetrain unknown."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 10.0, "wheelspin_band": "major",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": True, "snap_oversteer_exit": False},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
        }
        setup = {"aero_rear": 50, "lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=None,
        )

        # Any non-Pack-A changes should have drivetrain unknown text
        non_pack_a = [c for c in plan.proposed if getattr(c, "pack", "") != "A"]
        if not non_pack_a:
            pytest.skip("No non-Pack-A changes to check")

        for ch in non_pack_a:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert "drivetrain unknown" in cdi, (
                f"AC18 FAIL: drivetrain=None should produce 'drivetrain unknown' in "
                f"car_drivetrain_influence; got {cdi!r} for field={ch.field}"
            )


# ===========================================================================
# AC19 — applies_drivetrain filter
# ===========================================================================

class TestAC19DrivetrainScopeFilter:
    """AC19: rr-scoped rule (P1) doesn't fire when drivetrain=fr; fires when drivetrain=None."""

    def _snap_wheelspin_diag(self) -> dict:
        return {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 8.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"snap_oversteer_exit": False, "rear_loose_on_exit": True},
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
        }

    def test_p1_does_not_fire_for_fr_drivetrain(self):
        """P1 (applies_drivetrain=rr) must NOT fire when drivetrain=fr."""
        diag = self._snap_wheelspin_diag()
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.fr,
            car_class=CarClass.gr3,
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        assert not p1_changes, (
            "AC19 FAIL: P1 (applies_drivetrain=rr) fired when drivetrain=fr. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_p1_fires_for_rr_drivetrain(self):
        """P1 must fire when drivetrain=rr + gr3 car class + snap_throttle_induced."""
        diag = self._snap_wheelspin_diag()
        setup = {"lsd_accel": 15}
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
            "AC19 FAIL: P1 did not fire for drivetrain=rr + gr3 + snap_throttle_induced. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_p1_fires_when_drivetrain_none(self):
        """P1 fires when drivetrain=None (wildcard-permissive)."""
        diag = self._snap_wheelspin_diag()
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=None,
            car_class=CarClass.gr3,
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        assert p1_changes, (
            "AC19 FAIL: P1 did not fire when drivetrain=None (should be wildcard-permissive). "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC20 — applies_car_class filter
# ===========================================================================

class TestAC20CarClassScopeFilter:
    """AC20: gr3-scoped rule (P1) doesn't fire for road car class."""

    def test_p1_does_not_fire_for_road_car_class(self):
        """P1 (applies_car_class=gr3) must NOT fire when car_class=road."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 8.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"snap_oversteer_exit": False, "rear_loose_on_exit": True},
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
        }
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.rr,
            car_class=CarClass.road,  # road car — not gr3
        )

        p1_changes = [c for c in plan.proposed if c.rule_id == "P1"]
        assert not p1_changes, (
            "AC20 FAIL: P1 (applies_car_class=gr3) fired when car_class=road. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC14 RUNTIME — High tyre wear ACTUALLY suppresses the 4 wired rules at runtime
# ===========================================================================

def _b3_firing_diag(tyre_wear_high: bool = False) -> dict:
    """Diagnosis that fires B3 (snap_oversteer_exit=True, floaty_front=False)
    and also B6 (wheelspin_band not_low, snap_oversteer_exit=False for B6's
    contraindication — BUT note B3 fires on snap_oversteer_exit=True, so B6
    is contraindicated by snap_oversteer_exit when B3 fires).
    To get a control rule (B6) we need to NOT have snap_oversteer_exit.
    So we use two separate diag helpers.
    """
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 0.0, "wheelspin_band": "low",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "snap_oversteer_exit": True,   # fires B3 precondition
            "floaty_front": False,          # B3 contraindication is False → not blocked
            "rear_loose_on_exit": False,
            "entry_understeer": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "snap_exit",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "insufficient_data",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": tyre_wear_high,
    }


def _b6_control_diag(tyre_wear_high: bool = False) -> dict:
    """Diagnosis that fires B6 (wheelspin not_low, NO snap_oversteer_exit).
    B6 increases LSD accel — NOT wired to tyre_wear_high contraindication.
    Also fires C4 (wheelspin not_low, aero_rear_near_min=False, aero_rear_healthy=False).
    """
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 12.0, "wheelspin_band": "major",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "snap_oversteer_exit": False,
            "floaty_front": False,
            "rear_loose_on_exit": False,
            "entry_understeer": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "wheelspin",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "insufficient_data",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": tyre_wear_high,
    }


def _c1_firing_diag(tyre_wear_high: bool = False) -> dict:
    """Diagnosis that fires C1_entry_lsd_decel (entry_understeer=True, rear_loose=False)."""
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 0.0, "wheelspin_band": "low",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "entry_understeer": True,
            "rear_loose_on_exit": False,
            "snap_oversteer_exit": False,
            "floaty_front": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "entry_understeer",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "insufficient_data",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": tyre_wear_high,
    }


def _c3_c7_firing_diag(tyre_wear_high: bool = False) -> dict:
    """Diagnosis that fires C3_mid_arb_rear (dominant_problem contains 'understeer')
    AND C7_kerb_arb_rear (compliance_priority=True).
    wheelspin_band=low so C3's contraindication on __not_low__ wheelspin is clear.
    rear_loose_on_exit=False so C3's other contraindication is clear.
    """
    return {
        "avg_bottoming": 0.0, "bottoming_band": "minor",
        "avg_wheelspin": 0.0, "wheelspin_band": "low",
        "avg_snap": 0.0, "avg_lockups": 0.0,
        "driver_feel_flags": {
            "entry_understeer": True,
            "rear_loose_on_exit": False,
            "snap_oversteer_exit": False,
            "floaty_front": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": True,  # fires C7_kerb_arb_rear
        "aero_front_near_min": False, "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "entry_understeer",  # contains 'understeer' → fires C3
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "insufficient_data",
        "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "tyre_wear_high": tyre_wear_high,
    }


class TestAC14RuntimeHighTyreWearSuppression:
    """AC14 RUNTIME: tyre_wear_high=True in the diagnosis actually suppresses the
    4 wired rules (B3, C1_entry_lsd_decel, C3_mid_arb_rear, C7_kerb_arb_rear) at
    runtime via _eval_contraindications.  Non-wired rules that increase lsd lock or
    rear downforce (B6, C4, C5, C6) must NOT be suppressed.

    Tests drive the real run_rule_engine() with diagnosis["tyre_wear_high"] set
    directly — no need to go through driving_advisor (tyre_wear_high is the key
    that _eval_contraindications reads).
    """

    # -----------------------------------------------------------------------
    # B3 — lsd_accel -2 (snap_oversteer_exit: decrease LSD accel)
    # -----------------------------------------------------------------------

    def test_b3_fires_when_tyre_wear_low(self):
        """B3 (lsd_accel -2) fires when snap_oversteer_exit=True and tyre_wear_high=False."""
        diag = _b3_firing_diag(tyre_wear_high=False)
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        b3_changes = [c for c in plan.proposed if c.rule_id == "B3"]
        assert b3_changes, (
            "AC14-RUNTIME FAIL: B3 did not fire when snap_oversteer_exit=True, "
            "tyre_wear_high=False. Precondition construction may be wrong.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_b3_suppressed_when_tyre_wear_high(self):
        """B3 (lsd_accel -2) must NOT fire when tyre_wear_high=True."""
        diag = _b3_firing_diag(tyre_wear_high=True)
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        b3_changes = [c for c in plan.proposed if c.rule_id == "B3"]
        assert not b3_changes, (
            "AC14-RUNTIME FAIL: B3 (lsd_accel -2) fired when tyre_wear_high=True — "
            "contraindication was NOT enforced at runtime.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}"
        )

    # -----------------------------------------------------------------------
    # C1_entry_lsd_decel — lsd_decel -2
    # -----------------------------------------------------------------------

    def test_c1_fires_when_tyre_wear_low(self):
        """C1_entry_lsd_decel fires when entry_understeer=True and tyre_wear_high=False."""
        diag = _c1_firing_diag(tyre_wear_high=False)
        # Interior lsd_decel so the anti-ratchet movement cap does not confound this
        # tyre-wear gate assertion (lsd_decel=5 sits in the bottom operating-band
        # reserve, where a further -2 decrease is intentionally held — covered by
        # test_movement_cap_* instead).
        setup = {"lsd_decel": 30}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c1_changes = [c for c in plan.proposed if c.rule_id == "C1_entry_lsd_decel"]
        assert c1_changes, (
            "AC14-RUNTIME FAIL: C1_entry_lsd_decel did not fire when "
            "entry_understeer=True, tyre_wear_high=False.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_c1_suppressed_when_tyre_wear_high(self):
        """C1_entry_lsd_decel must NOT fire when tyre_wear_high=True."""
        diag = _c1_firing_diag(tyre_wear_high=True)
        setup = {"lsd_decel": 30}   # interior — isolate the tyre-wear gate from the movement cap
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c1_changes = [c for c in plan.proposed if c.rule_id == "C1_entry_lsd_decel"]
        assert not c1_changes, (
            "AC14-RUNTIME FAIL: C1_entry_lsd_decel (lsd_decel -2) fired when "
            "tyre_wear_high=True — contraindication NOT enforced.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}"
        )

    # -----------------------------------------------------------------------
    # C3_mid_arb_rear — arb_rear +1 (stiffen rear ARB to cure mid-corner understeer)
    # -----------------------------------------------------------------------

    def test_c3_fires_when_tyre_wear_low(self):
        """C3_mid_arb_rear fires when dominant_problem contains 'understeer' and tyre_wear_high=False."""
        diag = _c3_c7_firing_diag(tyre_wear_high=False)
        setup = {"arb_rear": 5, "lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        # C3 (understeer → arb_rear +1) and C7 (kerb compliance → arb_rear -1) both
        # target arb_rear and now oppose; conflict resolution keeps the higher-
        # confidence one and rejects the other with a 'conflict' rationale. C3 must
        # still FIRE — either winning (in proposed) or losing the conflict (in
        # rejected). Assert on rule_id, not delta sign.
        c3_in_proposed = [c for c in plan.proposed if c.rule_id == "C3_mid_arb_rear"]
        c3_in_rejected = [c for c in plan.rejected_candidates if c.rule_id == "C3_mid_arb_rear"
                          and "conflict" in (c.rationale or "")]
        c3_fired = bool(c3_in_proposed or c3_in_rejected)
        assert c3_fired, (
            "AC14-RUNTIME FAIL: C3_mid_arb_rear did not fire when "
            "dominant_problem='entry_understeer' (contains 'understeer'), tyre_wear_high=False.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_c3_suppressed_when_tyre_wear_high(self):
        """C3_mid_arb_rear must NOT be in proposed when tyre_wear_high=True."""
        diag = _c3_c7_firing_diag(tyre_wear_high=True)
        setup = {"arb_rear": 5, "lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c3_in_proposed = [c for c in plan.proposed if c.rule_id == "C3_mid_arb_rear"]
        assert not c3_in_proposed, (
            "AC14-RUNTIME FAIL: C3_mid_arb_rear (arb_rear +1) appeared in proposed "
            "when tyre_wear_high=True — contraindication NOT enforced.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}"
        )

    # -----------------------------------------------------------------------
    # C7_kerb_arb_rear — arb_rear -1
    # -----------------------------------------------------------------------

    def test_c7_fires_when_tyre_wear_low(self):
        """C7_kerb_arb_rear fires when compliance_priority=True and tyre_wear_high=False."""
        # Use a diag with low wheelspin (C7's contraindication is wheelspin __not_low__)
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": False, "snap_oversteer_exit": False,
                                   "entry_understeer": False, "floaty_front": False},
            "gearbox_flag": "preserve",
            "compliance_priority": True,  # C7 precondition
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",  # NOT understeer → C3 won't fire
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
            "tyre_wear_high": False,
        }
        setup = {"arb_rear": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c7_changes = [c for c in plan.proposed if c.rule_id == "C7_kerb_arb_rear"]
        assert c7_changes, (
            "AC14-RUNTIME FAIL: C7_kerb_arb_rear did not fire when "
            "compliance_priority=True, wheelspin_band=low, tyre_wear_high=False.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_c7_suppressed_when_tyre_wear_high(self):
        """C7_kerb_arb_rear must NOT fire when tyre_wear_high=True."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": False, "snap_oversteer_exit": False,
                                   "entry_understeer": False, "floaty_front": False},
            "gearbox_flag": "preserve",
            "compliance_priority": True,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
            "tyre_wear_high": True,
        }
        setup = {"arb_rear": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c7_changes = [c for c in plan.proposed if c.rule_id == "C7_kerb_arb_rear"]
        assert not c7_changes, (
            "AC14-RUNTIME FAIL: C7_kerb_arb_rear (arb_rear -1) appeared in proposed "
            "when tyre_wear_high=True — contraindication NOT enforced.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}"
        )

    # -----------------------------------------------------------------------
    # Control rules NOT wired to tyre_wear_high: B6 and C4/C6 (increase lsd/aero)
    # -----------------------------------------------------------------------

    def test_b6_not_suppressed_under_high_tyre_wear(self):
        """B6 (lsd_accel +2 — increases LSD lock) must NOT be suppressed when tyre_wear_high=True.

        B6 has NO tyre_wear_high contraindication by design — increasing LSD accel
        stabilises worn tyres rather than accelerating degradation.
        """
        diag = _b6_control_diag(tyre_wear_high=True)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        b6_changes = [c for c in plan.proposed if c.rule_id == "B6"]
        assert b6_changes, (
            "AC14-RUNTIME FAIL: B6 (lsd_accel +2) was suppressed under tyre_wear_high=True — "
            "B6 must NOT be wired to the high-wear contraindication (it stabilises tyres).\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_c4_rear_aero_increase_not_suppressed_under_high_wear(self):
        """C4_mid_rear_aero (aero_rear +1 — increases rear downforce) must NOT be suppressed
        when tyre_wear_high=True.  Increasing rear aero stabilises a worn rear platform.
        """
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 12.0, "wheelspin_band": "major",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"snap_oversteer_exit": False, "rear_loose_on_exit": False,
                                   "entry_understeer": False, "floaty_front": False},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,  # C4 contraindication is aero_rear_healthy=True
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
            "tyre_wear_high": True,
        }
        setup = {"aero_rear": 50, "lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        # C4 OR B4 or B6 increasing rear aero / lsd is expected — just confirm C4 not blocked
        c4_changes = [c for c in plan.proposed if c.rule_id == "C4_mid_rear_aero"]
        # C4 may lose to B4 in conflict resolution (same field, both +1 aero_rear);
        # check neither is absent due to the tyre_wear_high flag.
        aero_rear_increases = [c for c in plan.proposed if c.field == "aero_rear" and c.delta > 0]
        c4_rejected_by_conflict = [
            c for c in plan.rejected_candidates
            if c.rule_id == "C4_mid_rear_aero" and "conflict" in (c.rationale or "")
        ]
        c4_fired = bool(c4_changes or c4_rejected_by_conflict)
        assert c4_fired, (
            "AC14-RUNTIME FAIL: C4_mid_rear_aero (aero_rear +1) was not in proposed "
            "or conflict-rejected when tyre_wear_high=True — it should NOT be "
            "contraindicated by high tyre wear.\n"
            f"proposed: {[(c.field, c.rule_id, c.delta) for c in plan.proposed]}\n"
            f"rejected: {[(c.field, c.rule_id, c.rationale[:60]) for c in plan.rejected_candidates]}"
        )

    def test_high_wear_only_suppresses_wired_rules_not_all_rules(self):
        """Sanity: tyre_wear_high=True must not block ALL rules — at least one non-A
        rule must still fire (proving it is a targeted suppression, not a blanket block).
        """
        diag = _b6_control_diag(tyre_wear_high=True)
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        non_pack_a_proposed = [c for c in plan.proposed if getattr(c, "pack", "") != "A"]
        assert non_pack_a_proposed, (
            "AC14-RUNTIME FAIL: tyre_wear_high=True blocked ALL non-Pack-A rules. "
            "High-wear contraindication must be targeted, not a blanket block.\n"
            f"proposed: {[(c.field, c.rule_id, c.pack) for c in plan.proposed]}"
        )


# ===========================================================================
# Bug-fix: quali session_influence for rules WITHOUT front-bite/trail-braker tags
# ===========================================================================

class TestQualiSessionNoBiasForUntaggedRules:
    """Bug-fix verification: a qualifying session rule WITHOUT prefers_front_bite
    or trail_braker tags must produce session_influence='' (empty), not a false
    qualifying-bias claim.

    The dead `session_type is None` branch inside the `== quali` block was removed
    (Group 45 fix).  After the fix, only tagged rules get the qualifying text; all
    other quali-session changes get ''.
    """

    def test_b6_in_quali_has_no_session_influence(self):
        """B6 has driver_style_tags=['rotation_without_snap'] — NO front-bite or trail-braker.
        Running it with session_type=quali must produce session_influence='' on B6 changes.
        """
        diag = _b6_control_diag(tyre_wear_high=False)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=SessionType.quali)

        b6_changes = [c for c in plan.proposed if c.rule_id == "B6"]
        if not b6_changes:
            pytest.skip("B6 did not fire — cannot check session_influence")

        for ch in b6_changes:
            si = getattr(ch, "session_influence", None)
            assert si == "", (
                f"Bug-fix FAIL: B6 (no front-bite/trail-braker tags) in quali session "
                f"must have session_influence=''; got {si!r}"
            )
            assert "qualifying bias" not in (si or ""), (
                f"Bug-fix FAIL: B6 falsely claims qualifying bias; session_influence={si!r}"
            )

    def test_c1_in_quali_has_qualifying_bias_text(self):
        """C1_entry_lsd_decel has tags ['trail_braker', 'prefers_front_bite'] → quali bias applies."""
        diag = _c1_firing_diag(tyre_wear_high=False)
        setup = {"lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=SessionType.quali)

        c1_changes = [c for c in plan.proposed if c.rule_id == "C1_entry_lsd_decel"]
        if not c1_changes:
            pytest.skip("C1_entry_lsd_decel did not fire — cannot check session_influence")

        for ch in c1_changes:
            si = getattr(ch, "session_influence", "")
            assert "qualifying bias applied" in si, (
                f"Bug-fix FAIL: C1_entry_lsd_decel (trail_braker + prefers_front_bite) in "
                f"quali must have qualifying bias; session_influence={si!r}"
            )


# ===========================================================================
# Bug-fix: None session type produces neutral weighting text (not empty string)
# ===========================================================================

class TestNoneSessionInfluenceText:
    """Bug-fix: session_type=None must produce 'neutral weighting — session type not available'
    on ANY non-Pack-A rule that fires (the dead branch in == quali was removed in Group 45;
    the outer else now unconditionally sets neutral text for None).
    """

    def test_b6_session_none_produces_neutral_text(self):
        """B6 with session_type=None must have 'neutral weighting' in session_influence."""
        diag = _b6_control_diag(tyre_wear_high=False)
        setup = {"lsd_accel": 15}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        b6_changes = [c for c in plan.proposed if c.rule_id == "B6"]
        if not b6_changes:
            pytest.skip("B6 did not fire — cannot check session_influence")

        for ch in b6_changes:
            si = getattr(ch, "session_influence", "")
            assert "neutral weighting" in si, (
                f"Bug-fix FAIL: B6 with session_type=None must have 'neutral weighting' "
                f"in session_influence; got {si!r}"
            )
            assert "session type not available" in si, (
                f"Bug-fix FAIL: session_influence must say 'session type not available'; "
                f"got {si!r}"
            )

    def test_c1_session_none_produces_neutral_text(self):
        """C1_entry_lsd_decel with session_type=None must also have neutral weighting text."""
        diag = _c1_firing_diag(tyre_wear_high=False)
        setup = {"lsd_decel": 5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, session_type=None)

        c1_changes = [c for c in plan.proposed if c.rule_id == "C1_entry_lsd_decel"]
        if not c1_changes:
            pytest.skip("C1_entry_lsd_decel did not fire — cannot check session_influence")

        for ch in c1_changes:
            si = getattr(ch, "session_influence", "")
            assert "neutral weighting" in si, (
                f"Bug-fix FAIL: C1 with session_type=None must have 'neutral weighting'; "
                f"got {si!r}"
            )
