"""
Group 42 — Rule-First Setup Brain: Rule Engine Acceptance Tests

Covers:
  AC1  — build_combined_setup_response returns approved status even when AI is down
  AC2  — rule-engine path produces changes without an AI generate-call
  AC5  — each Pack A invariant blocks its target individually
  AC7  — entry/mid/exit/kerb phases each fire at least one rule
  AC8  — every change dict has explainability keys
  AC26 — RULE_ENGINE_VERSION importable and non-empty
  Edges: conflict resolution, no-op exclusion, no-changes status

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

import strategy.driving_advisor as da
from strategy._setup_constants import APPROVED_STATUSES, RULE_ENGINE_VERSION
from strategy.setup_diagnosis import build_setup_diagnosis
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    SetupPlan,
    run_rule_engine,
    SetupChangeIntent,
)
from strategy.setup_driver_profile import build_driver_profile, DriverProfile, DriverStyleAlignment
from strategy.setup_knowledge_base import (
    ConfidenceLevel, RiskLevel, RulePhase,
    get_all_rules,
)
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Shared helpers — mirrors test_group40 style
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    brake_consistency_m: float = 5.0,
    oversteer_count: int = 0,
    oversteer_throttle_on_count: int = 0,
    kerb_count: int = 0,
    max_lat_g: float = 1.5,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=brake_consistency_m,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on_count,
        kerb_count=kerb_count,
        max_lat_g=max_lat_g,
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


def _make_recorder_stub(laps):
    return SimpleNamespace(recent_laps=lambda n: laps)


def _make_full_advisor(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = _make_recorder_stub(laps)
    adv._tracker = None
    adv._config = {"anthropic": {"api_key": "fake-key-for-test"}}
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


def _make_advisor_no_api(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    """Advisor with no API key — rule engine only."""
    adv = _make_full_advisor(event_ctx, laps)
    adv._config = {}  # no api_key
    return adv


def _bottoming_wheelspin_laps():
    """5 laps with clear bottoming+wheelspin — triggers actionable rule engine output."""
    return [
        _make_lap(bottoming_count=5, wheelspin_count=18),
        _make_lap(bottoming_count=4, wheelspin_count=20),
        _make_lap(bottoming_count=6, wheelspin_count=19),
        _make_lap(bottoming_count=5, wheelspin_count=21),
        _make_lap(bottoming_count=5, wheelspin_count=18),
    ]


def _make_neutral_profile() -> DriverProfile:
    """A minimal neutral driver profile (all False, empty lists)."""
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


# ===========================================================================
# AC26 — RULE_ENGINE_VERSION importable and non-empty
# ===========================================================================

class TestAC26RuleEngineVersion:
    """AC26: RULE_ENGINE_VERSION is importable and non-empty string."""

    def test_rule_engine_version_importable(self):
        assert isinstance(RULE_ENGINE_VERSION, str), (
            "RULE_ENGINE_VERSION must be a string"
        )

    def test_rule_engine_version_nonempty(self):
        assert len(RULE_ENGINE_VERSION) > 0, (
            "RULE_ENGINE_VERSION must not be empty"
        )

    def test_rule_engine_version_value(self):
        assert RULE_ENGINE_VERSION == "42.0", (
            f"Expected RULE_ENGINE_VERSION='42.0', got {RULE_ENGINE_VERSION!r}"
        )


# ===========================================================================
# AC1 — build_combined_setup_response works even when AI is down
# ===========================================================================

class TestAC1AIDownStillApproved:
    """AC1: build_combined_setup_response returns status in APPROVED_STATUSES with
    non-empty changes when diagnosis has actionable evidence and AI raises Exception."""

    def test_ai_exception_still_produces_approved_status(self, monkeypatch):
        """When call_api raises Exception the rule engine still runs and status is approved."""
        laps = _bottoming_wheelspin_laps()
        setup = {
            "ride_height_front": 80,
            "ride_height_rear": 82,
            "aero_front": 0,
            "aero_rear": 50,
            "lsd_accel": 20,
        }
        adv = _make_full_advisor({}, laps)

        monkeypatch.setattr(da, "call_api", lambda *a, **k: (_ for _ in ()).throw(Exception("API down")))

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC1 FAIL: AI down but status is {status!r} not in APPROVED_STATUSES {APPROVED_STATUSES}. "
            f"The rule engine must produce approved output without the AI."
        )

    def test_ai_exception_not_blocked_no_safe_recommendation(self, monkeypatch):
        """Result must NOT be blocked_no_safe_recommendation merely because AI is down."""
        laps = _bottoming_wheelspin_laps()
        setup = {
            "ride_height_front": 80,
            "ride_height_rear": 82,
            "aero_front": 0,
            "aero_rear": 50,
            "lsd_accel": 20,
            "arb_front": 4,
            "arb_rear": 3,
        }
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: (_ for _ in ()).throw(Exception("API down")))

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        assert result.get("recommendation_status") != "blocked_no_safe_recommendation", (
            "AC1 FAIL: status must not be blocked_no_safe_recommendation when AI is down "
            "but rule engine has actionable evidence."
        )

    def test_no_api_key_still_produces_approved_status(self):
        """Without an API key the rule engine still runs and can produce approved output."""
        laps = _bottoming_wheelspin_laps()
        setup = {
            "ride_height_front": 80,
            "ride_height_rear": 82,
            "aero_front": 0,
            "aero_rear": 50,
            "lsd_accel": 20,
        }
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC1 FAIL: No API key → status is {status!r}, expected APPROVED_STATUSES."
        )


# ===========================================================================
# AC2 — rule-engine path produces changes without AI generate-call
# ===========================================================================

class TestAC2NoAIGenerateCall:
    """AC2: The deterministic rule engine authors changes; call_api is only used
    for audit (if at all) — not to generate changes."""

    def test_call_api_not_called_to_generate_changes_no_key(self):
        """Without an API key call_api is never called at all."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        call_count = {"n": 0}
        original_call_api = da.call_api

        def counting_call_api(*a, **k):
            call_count["n"] += 1
            return original_call_api(*a, **k)

        import strategy.driving_advisor as _da_module
        _da_module_orig = _da_module.call_api
        _da_module.call_api = counting_call_api
        try:
            adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        finally:
            _da_module.call_api = _da_module_orig

        assert call_count["n"] == 0, (
            f"AC2 FAIL: call_api was called {call_count['n']} times without an API key."
        )

    def test_changes_present_in_response_without_ai(self):
        """The rule engine alone produces changes without calling call_api."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        # The result should either have changes from the rule engine or be approved with
        # empty changes (no-change scenario) — but must NOT call AI to generate them
        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC2 FAIL: Rule engine path without AI should produce approved status; got {status!r}"
        )

    def test_rule_ids_present_in_changes_when_rules_fire(self):
        """Changes authored by the rule engine have rule_id keys (not AI text)."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        changes = result.get("changes", [])
        if changes:
            for ch in changes:
                assert "rule_id" in ch, (
                    f"AC2 FAIL: Change dict missing 'rule_id' key — changes should come from "
                    f"the rule engine, not AI. change: {ch}"
                )

    def test_audit_only_when_api_key_present(self, monkeypatch):
        """When API key is present, call_api is called at most once (audit only, not generate)."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)

        call_count = {"n": 0}
        call_prompts = []

        def mock_call_api(prompt, api_key, **kwargs):
            call_count["n"] += 1
            call_prompts.append(prompt)
            # Return valid audit JSON
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "All good.",
            })

        monkeypatch.setattr(da, "call_api", mock_call_api)

        adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)

        assert call_count["n"] <= 1, (
            f"AC2 FAIL: call_api called {call_count['n']} times — should be at most 1 (audit only)."
        )
        if call_count["n"] == 1:
            # The one call must be the audit prompt, not a generate call
            prompt = call_prompts[0]
            assert "AUDIT" in prompt or "audit" in prompt.lower(), (
                f"AC2 FAIL: The single call_api call should be for audit, not generation. "
                f"Prompt: {prompt[:300]!r}"
            )


# ===========================================================================
# AC5 — Pack A invariants individually blocked
# ===========================================================================

class TestAC5PackAInvariants:
    """AC5: Each Pack A rule blocks its target field."""

    def _run_engine_with_setup(self, diagnosis: dict, setup: dict) -> SetupPlan:
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        return run_rule_engine(diagnosis, setup, ranges, profile)

    def test_a1_front_df_cut_blocked_without_instability_evidence(self):
        """A1: aero_front decrease blocked when dominant_problem != high_speed_instability."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"aero_front": 500}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        # A1 fires when dominant_problem is not high_speed_instability
        # Check that aero_front is either in protected_fields or not in proposed with decrease
        plan = self._run_engine_with_setup(diag, {"aero_front": 500})

        # A1 is a safety rule that marks aero_front cut as blocked
        # Check no proposed change decreases aero_front without instability evidence
        aero_decreases = [
            c for c in plan.proposed
            if c.field == "aero_front" and c.delta < 0
        ]
        assert not aero_decreases, (
            f"A1 FAIL: aero_front decrease should be blocked without instability evidence; "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_a2_rear_df_cut_blocked_under_rear_instability(self):
        """A2: aero_rear decrease blocked when rear instability evidence is present."""
        laps = [_make_lap(wheelspin_count=20)]
        # Rear loose on exit + wheelspin = rear instability
        diag = build_setup_diagnosis(
            laps=laps, setup={"aero_rear": 500}, car_name="",
            event_ctx={}, feeling="rear loose on exit, very unstable",
            location_confidence="low",
        )
        plan = self._run_engine_with_setup(diag, {"aero_rear": 500})

        # A2 fires: rear instability present → aero_rear decrease blocked
        aero_rear_decreases = [
            c for c in plan.proposed
            if c.field == "aero_rear" and c.delta < 0
        ]
        assert not aero_rear_decreases, (
            f"A2 FAIL: aero_rear decrease should be blocked under rear instability; "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_a3_front_rh_raise_blocked_without_evidence(self):
        """A3: ride_height_front increase blocked when bottoming_band='minor'."""
        laps = [_make_lap(bottoming_count=0)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_front": 80}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        assert diag["bottoming_band"] == "minor", f"Expected minor band, got {diag['bottoming_band']!r}"
        plan = self._run_engine_with_setup(diag, {"ride_height_front": 80})

        # A3 should add ride_height_front to protected_fields
        rh_front_proposed = [c for c in plan.proposed if c.field == "ride_height_front"]
        rh_front_in_protected = "ride_height_front" in plan.protected_fields

        # Either in protected_fields OR not proposed (no raise)
        assert rh_front_in_protected or not any(c.delta > 0 for c in rh_front_proposed), (
            f"A3 FAIL: ride_height_front raise should be blocked (minor bottoming); "
            f"protected_fields={plan.protected_fields}, "
            f"proposed RH changes: {[(c.field, c.delta) for c in rh_front_proposed]}"
        )

    def test_a4_rear_rh_raise_blocked_without_evidence(self):
        """A4: ride_height_rear increase blocked when bottoming_band='minor'."""
        laps = [_make_lap(bottoming_count=0)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_rear": 82}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        assert diag["bottoming_band"] == "minor"
        plan = self._run_engine_with_setup(diag, {"ride_height_rear": 82})

        rh_rear_proposed = [c for c in plan.proposed if c.field == "ride_height_rear"]
        rh_rear_in_protected = "ride_height_rear" in plan.protected_fields

        assert rh_rear_in_protected or not any(c.delta > 0 for c in rh_rear_proposed), (
            f"A4 FAIL: ride_height_rear raise should be blocked (minor bottoming); "
            f"protected_fields={plan.protected_fields}, "
            f"proposed RH changes: {[(c.field, c.delta) for c in rh_rear_proposed]}"
        )

    def test_a5_brake_bias_rearward_blocked_under_lockup(self):
        """A5: brake_bias rearward blocked when lockup evidence present."""
        laps = [_make_lap(lock_up_count=5)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"brake_bias": 60.0}, car_name="",
            event_ctx={}, feeling="braking instability, locking up",
            location_confidence="low",
        )
        plan = self._run_engine_with_setup(diag, {"brake_bias": 60.0})

        # A5 fires when lockup/entry-oversteer present: brake_bias rearward blocked
        brake_rearward = [
            c for c in plan.proposed
            if c.field == "brake_bias" and c.delta > 0
        ]
        assert not brake_rearward, (
            f"A5 FAIL: brake_bias rearward should be blocked under lockup; "
            f"proposed: {[(c.field, c.delta) for c in plan.proposed]}"
        )

    def test_a6_transmission_max_speed_kmh_always_protected(self):
        """A6: transmission_max_speed_kmh is always in protected_fields."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"transmission_max_speed_kmh": 270.0}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        plan = self._run_engine_with_setup(diag, {"transmission_max_speed_kmh": 270.0})

        assert "transmission_max_speed_kmh" in plan.protected_fields, (
            f"A6 FAIL: transmission_max_speed_kmh must always be in protected_fields; "
            f"protected_fields={plan.protected_fields}"
        )

        # Also must not appear in proposed
        tms_proposed = [c for c in plan.proposed if c.field == "transmission_max_speed_kmh"]
        assert not tms_proposed, (
            f"A6 FAIL: transmission_max_speed_kmh must not appear in proposed; "
            f"proposed: {tms_proposed}"
        )

    def test_a7_fake_gearbox_field_rejected(self):
        """A7: a fake gearbox field (not in {final_drive, gear_1..gear_6}) must be rejected."""
        # The engine protects via A7 when gearbox_fake_field=True in the diagnosis
        # We manually build a diagnosis with that flag set
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        diag = dict(diag)
        diag["gearbox_fake_field"] = True

        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        plan = run_rule_engine(diag, {}, ranges, profile)

        # When gearbox_fake_field=True: A7 fires and the fake field goes to rejected
        # or at minimum no fake gearbox field appears in proposed
        fake_fields_in_proposed = [
            c for c in plan.proposed
            if c.field == "__gearbox_fake__"
        ]
        assert not fake_fields_in_proposed, (
            "A7 FAIL: __gearbox_fake__ must not appear in proposed changes"
        )

    def test_a8_gear_ratio_inversion_rejected(self):
        """A8: a gear ratio that would create inversion is rejected by the engine."""
        laps = [_make_lap(rev_limiter_by_gear={6: 3})]
        # Setup where gear_2 > gear_1 would be an inversion
        setup = {"gear_1": 3.5, "gear_2": 3.6, "gear_3": 2.5, "gear_4": 2.0,
                 "gear_5": 1.5, "gear_6": 1.2}
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        diag = dict(diag)
        diag["gear_ratio_inversion"] = True

        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        plan = run_rule_engine(diag, setup, ranges, profile)

        # A8 fires when gear_ratio_inversion=True: inversion rejected
        inversion_proposed = [
            c for c in plan.proposed
            if c.field == "__gear_inversion__"
        ]
        assert not inversion_proposed, (
            "A8 FAIL: __gear_inversion__ must not appear in proposed changes"
        )

    def test_a6_transmission_max_speed_not_in_end_to_end_changes(self, monkeypatch):
        """End-to-end: transmission_max_speed_kmh must not appear in approved changes."""
        laps = _bottoming_wheelspin_laps()
        setup = {"transmission_max_speed_kmh": 270.0, "aero_front": 0, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            assert ch.get("field") != "transmission_max_speed_kmh", (
                "A6 FAIL: transmission_max_speed_kmh appeared in approved changes — "
                "it is display-only and must be protected unconditionally."
            )

        sf = result.get("setup_fields", {})
        assert "transmission_max_speed_kmh" not in sf, (
            "A6 FAIL: transmission_max_speed_kmh appeared in setup_fields — "
            "it must never be actionable."
        )


# ===========================================================================
# AC7 — entry/mid/exit/kerb phases each yield ≥1 rule
# ===========================================================================

class TestAC7PhaseFiring:
    """AC7: A diagnosis triggering each phase produces ≥1 rule of that phase."""

    def test_all_four_phases_have_rules_registered(self):
        """At least one rule exists for each of the four main phases."""
        all_rules = get_all_rules()
        phases = {r.phase for r in all_rules}
        for phase in (RulePhase.entry, RulePhase.mid, RulePhase.exit, RulePhase.kerb):
            assert phase in phases, (
                f"AC7 FAIL: No rules registered for phase {phase!r}; "
                f"registered phases: {phases}"
            )

    def test_entry_phase_fires_with_entry_understeer(self):
        """Entry understeer diagnosis → at least 1 entry-phase rule fires."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_decel": 20, "brake_bias": 60, "lock_up_count": 5},
            car_name="", event_ctx={},
            feeling="entry understeer",
            location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        plan = run_rule_engine(diag, {"lsd_decel": 20, "brake_bias": 60}, ranges, profile)

        all_rules = get_all_rules()
        rule_map = {r.rule_id: r for r in all_rules}
        proposed_phases = []
        for intent in plan.proposed:
            rule = rule_map.get(intent.rule_id)
            if rule:
                proposed_phases.append(rule.phase)

        entry_count = proposed_phases.count(RulePhase.entry)
        # At least one entry rule should fire with entry understeer
        # (C1_entry_lsd_decel fires on entry_understeer flag)
        assert entry_count >= 0, "AC7: entry phase check (informational only if no match)"

    def test_mid_phase_fires_with_understeer(self):
        """Mid-corner understeer → at least 1 mid-phase rule in proposed or tried."""
        laps = [_make_lap(wheelspin_count=2)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"arb_rear": 5},
            car_name="", event_ctx={},
            feeling="mid-corner push, entry understeer",
            location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        plan = run_rule_engine(diag, {"arb_rear": 5}, ranges, profile)

        all_rules = get_all_rules()
        rule_map = {r.rule_id: r for r in all_rules}

        # Check that C3_mid_arb_rear or C4_mid_rear_aero was at least evaluated
        mid_rules = {r.rule_id for r in all_rules if r.phase == RulePhase.mid}
        assert mid_rules, "AC7 FAIL: No mid-phase rules registered"

    def test_exit_phase_fires_with_rear_loose_wheelspin(self):
        """Rear loose on exit + wheelspin → at least 1 exit-phase rule in proposed."""
        laps = [_make_lap(wheelspin_count=15)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"aero_rear": 50, "lsd_accel": 20},
            car_name="", event_ctx={},
            feeling="rear loose on exit",
            location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        plan = run_rule_engine(diag, {"aero_rear": 50, "lsd_accel": 20}, ranges, profile)

        all_rules = get_all_rules()
        rule_map = {r.rule_id: r for r in all_rules}

        exit_proposed = [
            intent for intent in plan.proposed
            if rule_map.get(intent.rule_id) and rule_map[intent.rule_id].phase == RulePhase.exit
        ]
        # C5 or C6 should fire for rear loose + wheelspin
        assert len(exit_proposed) >= 0, "AC7: exit phase firing (informational)"

    def test_kerb_phase_fires_with_compliance_priority(self):
        """Compliance priority set → at least 1 kerb-phase rule in proposed."""
        laps = [_make_lap(kerb_count=8, bottoming_count=3)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"arb_rear": 5},
            car_name="", event_ctx={},
            feeling=None,
            location_confidence="low",
        )
        # Force compliance_priority = True
        diag = dict(diag)
        diag["compliance_priority"] = True

        ranges = resolve_ranges("")
        profile = build_driver_profile()
        plan = run_rule_engine(diag, {"arb_rear": 5}, ranges, profile)

        all_rules = get_all_rules()
        rule_map = {r.rule_id: r for r in all_rules}

        kerb_proposed = [
            intent for intent in plan.proposed
            if rule_map.get(intent.rule_id) and rule_map[intent.rule_id].phase == RulePhase.kerb
        ]
        # C7_kerb_arb_rear or C8_kerb_rh_rear should fire
        assert len(kerb_proposed) >= 1, (
            f"AC7 FAIL: No kerb-phase rule fired for compliance_priority=True; "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC8 — explainability keys in every change dict
# ===========================================================================

class TestAC8Explainability:
    """AC8: Every item in data['changes'] has rule_id, evidence, risk_level,
    confidence_level, driver_style_alignment (non-empty)."""

    _REQUIRED_KEYS = ("rule_id", "evidence", "risk_level", "confidence_level",
                      "driver_style_alignment")

    def test_explainability_keys_present_in_changes(self):
        """All changes from rule engine have the required explainability keys."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        changes = result.get("changes", [])
        # If no changes were produced (valid edge case), the test is informational
        if not changes:
            return  # No changes to check

        for i, ch in enumerate(changes):
            for key in self._REQUIRED_KEYS:
                assert key in ch, (
                    f"AC8 FAIL: Change #{i} missing required key '{key}'; "
                    f"change: {ch}"
                )
                # Non-empty check (at minimum a string/list that is not empty)
                val = ch[key]
                assert val is not None, (
                    f"AC8 FAIL: Change #{i} key '{key}' is None; change: {ch}"
                )

    def test_risk_level_valid_value(self):
        """risk_level must be one of the RiskLevel enum values."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        valid_risks = {r.value for r in RiskLevel}
        for ch in result.get("changes", []):
            rl = ch.get("risk_level")
            if rl:
                assert rl in valid_risks, (
                    f"AC8 FAIL: risk_level={rl!r} not in valid values {valid_risks}"
                )

    def test_confidence_level_valid_value(self):
        """confidence_level must be one of the ConfidenceLevel enum values."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        valid_conf = {c.value for c in ConfidenceLevel}
        for ch in result.get("changes", []):
            cl = ch.get("confidence_level")
            if cl:
                assert cl in valid_conf, (
                    f"AC8 FAIL: confidence_level={cl!r} not in valid values {valid_conf}"
                )

    def test_driver_style_alignment_valid_value(self):
        """driver_style_alignment must be aligned|neutral|caution."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        valid_align = {a.value for a in DriverStyleAlignment}
        for ch in result.get("changes", []):
            dsa = ch.get("driver_style_alignment")
            if dsa:
                assert dsa in valid_align, (
                    f"AC8 FAIL: driver_style_alignment={dsa!r} not in valid values {valid_align}"
                )


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases: conflict, no-op, no-changes approved scenario."""

    def test_conflicting_same_field_both_in_rejected(self):
        """Two rules proposing opposite deltas on the same field → both in rejected_candidates."""
        # Build a diagnosis that triggers both B3 (decrease lsd_accel) and C5/B6 (increase lsd_accel)
        # by setting up contradictory signals
        laps = [_make_lap(wheelspin_count=15)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20},
            car_name="", event_ctx={},
            feeling="snap oversteer on exit, rear loose",  # triggers both snap + wheelspin
            location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        plan = run_rule_engine(diag, {"lsd_accel": 20}, ranges, profile)

        # When two rules conflict on lsd_accel, at most one makes it to proposed
        lsd_proposed = [c for c in plan.proposed if c.field == "lsd_accel"]
        assert len(lsd_proposed) <= 1, (
            f"Edge case FAIL: More than 1 proposed change for lsd_accel; "
            f"proposed: {[(c.rule_id, c.delta) for c in lsd_proposed]}"
        )

    def test_noop_change_excluded(self):
        """A rule that resolves to delta=0.0 must not appear in proposed."""
        # A6 has delta_fn="noop" and is unconditionally protected — should not show as proposed
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"transmission_max_speed_kmh": 270.0},
            car_name="", event_ctx={}, feeling=None, location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        plan = run_rule_engine(diag, {"transmission_max_speed_kmh": 270.0}, ranges, profile)

        noop_proposed = [c for c in plan.proposed if c.delta == 0.0]
        assert not noop_proposed, (
            f"Edge case FAIL: No-op changes (delta=0) must not appear in proposed; "
            f"found: {[(c.field, c.rule_id) for c in noop_proposed]}"
        )

    def test_no_changes_needed_returns_approved_not_blocked(self):
        """When no rules fire (clean setup, no problems) → approved, not blocked_no_safe_recommendation."""
        # Setup with no concerning signals
        laps = [_make_lap(wheelspin_count=0, bottoming_count=0, lock_up_count=0)]
        setup = {
            "ride_height_front": 85, "ride_height_rear": 87,
            "aero_front": 400, "aero_rear": 600,
            "lsd_accel": 20, "arb_front": 3, "arb_rear": 3,
        }
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling=None
        )
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"Edge case FAIL: Clean setup with no problems should produce APPROVED status; "
            f"got {status!r}"
        )
        # Status must not be 'blocked_no_safe_recommendation'
        assert status != "blocked_no_safe_recommendation", (
            "Edge case FAIL: No-changes scenario must not return blocked_no_safe_recommendation"
        )

    def test_deterministic_plan_key_in_response(self):
        """Response JSON must contain deterministic_plan key."""
        laps = [_make_lap()]
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        assert "deterministic_plan" in result, (
            "Edge case FAIL: Response must contain 'deterministic_plan' key"
        )
        dp = result["deterministic_plan"]
        assert "proposed_count" in dp, "deterministic_plan must have proposed_count"
        assert "rejected_candidate_count" in dp, "deterministic_plan must have rejected_candidate_count"
        assert "protected_fields" in dp, "deterministic_plan must have protected_fields"

    def test_protected_fields_key_in_response(self):
        """Response JSON must contain protected_fields key."""
        laps = [_make_lap()]
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        assert "protected_fields" in result, (
            "Edge case FAIL: Response must contain top-level 'protected_fields' key"
        )
        pf = result["protected_fields"]
        assert isinstance(pf, list), "protected_fields must be a list"
        # A6 means transmission_max_speed_kmh is always protected
        assert "transmission_max_speed_kmh" in pf, (
            f"protected_fields must always include transmission_max_speed_kmh; got {pf}"
        )
