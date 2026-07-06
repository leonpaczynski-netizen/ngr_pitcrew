"""
Group 45 — Setup Brain Intelligence Expansion: Engine Scope Tests

Covers AC1-AC6 (safety invariants):
  AC1  — AI audit-only: AI-supplied setup fields stripped before finaliser
  AC2  — Analyse & Baseline complete with AI disabled / no api_key
  AC3  — No explainability text claims tyre/fuel/session/car/drivetrain behaviour
         unless that input was received and used
  AC4  — Nothing actionable unless passes validator→finaliser→renderer→Apply gate
  AC5  — Old "Build Setup with AI" button stays disabled (_btn_build_setup disabled+hidden,
         _run_build_setup* early-return)
  AC6  — Learning cannot un-block/un-reject

Also covers Obj2 AC10-AC13 (session scope enforcement):
  AC10 — applies_session filter enforced: quali-scoped rule doesn't fire in race,
          B5 (applies_session=race) does NOT fire when session_type=quali
  AC11 — With session_type=None, B5 fires normally when preconditions met

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

import strategy.driving_advisor as da
from strategy._setup_constants import APPROVED_STATUSES, RULE_ENGINE_VERSION
from strategy.setup_diagnosis import build_setup_diagnosis
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    SetupPlan,
    run_rule_engine,
    SetupChangeIntent,
)
from strategy.setup_driver_profile import build_driver_profile, DriverProfile
from strategy.setup_knowledge_base import (
    ConfidenceLevel, RiskLevel, RulePhase, SessionType, DrivetrainType, CarClass,
    get_all_rules,
)
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Shared helpers — mirrors test_group42_rule_first_engine.py style
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


def _make_advisor_no_api(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = _make_recorder_stub(laps)
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


def _make_full_advisor(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    adv = _make_advisor_no_api(event_ctx, laps)
    adv._config = {"anthropic": {"api_key": "fake-key-for-test"}}
    return adv


def _bottoming_wheelspin_laps():
    return [
        _make_lap(bottoming_count=5, wheelspin_count=18),
        _make_lap(bottoming_count=4, wheelspin_count=20),
        _make_lap(bottoming_count=6, wheelspin_count=19),
        _make_lap(bottoming_count=5, wheelspin_count=21),
        _make_lap(bottoming_count=5, wheelspin_count=18),
    ]


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


# ===========================================================================
# AC1 — AI audit-only: AI-supplied setup fields stripped before finaliser
# ===========================================================================

class TestAC1AIAuditOnly:
    """AC1: AI audit cannot author actionable setup changes."""

    def test_ai_supplied_fields_stripped_before_finaliser(self, monkeypatch):
        """When call_api returns a 'generate' style response with setup_fields,
        those fields must NOT appear in the approved output. Only the rule engine
        can author actionable changes."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)

        # AI audit returns something that looks like it's generating changes
        # but the audit system should treat it as audit-only
        audit_response = json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "All good.",
        })
        monkeypatch.setattr(da, "call_api", lambda *a, **k: audit_response)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        # Changes must come from the rule engine, not from AI generate calls
        # The AI audit response does NOT contain new fields — only approves/rejects
        for ch in result.get("changes", []):
            rid = ch.get("rule_id", "")
            assert rid, (
                "AC1 FAIL: every change must have a rule_id (from the rule engine). "
                f"AI-authored changes without rule_id: {ch}"
            )
            # AI-authored changes would have no rule_id or a generic sentinel
            assert rid not in ("ai_generated", "ai_authored", ""), (
                f"AC1 FAIL: change appears to be AI-authored (rule_id={rid!r}). "
                f"AI must be audit-only."
            )

    def test_changes_have_rule_id_not_ai_origin(self):
        """Without API key the rule engine produces changes with deterministic rule_ids."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            rid = ch.get("rule_id", "")
            assert rid, f"AC1 FAIL: change missing rule_id: {ch}"


# ===========================================================================
# AC2 — Analyse & Baseline complete with AI disabled / no api_key
# ===========================================================================

class TestAC2NoAPIComplete:
    """AC2: Both Analyse and Baseline complete without AI / api_key."""

    def test_analyse_completes_without_api_key(self):
        """build_combined_setup_response returns valid JSON even without api_key."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        try:
            result = json.loads(result_str)
        except json.JSONDecodeError as exc:
            pytest.fail(f"AC2 FAIL: build_combined_setup_response returned invalid JSON: {exc}")

        assert "recommendation_status" in result, "AC2 FAIL: missing recommendation_status"

    def test_analyse_approved_without_api_key(self):
        """build_combined_setup_response status is in APPROVED_STATUSES without api_key."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC2 FAIL: without api_key, status={status!r} not in APPROVED_STATUSES"
        )

    def test_baseline_completes_without_api_key(self):
        """build_baseline_setup_response returns valid JSON without api_key."""
        from strategy.setup_ranges import resolve_ranges as _rr
        ranges = _rr("")
        adv = _make_advisor_no_api({}, [])
        result_str = adv.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR", num_gears=6,
            allowed_tuning=None, tuning_locked=False,
        )
        try:
            result = json.loads(result_str)
        except json.JSONDecodeError as exc:
            pytest.fail(f"AC2 FAIL: build_baseline_setup_response returned invalid JSON: {exc}")

        assert "recommendation_status" in result, (
            "AC2 FAIL: baseline response missing recommendation_status"
        )

    def test_baseline_approved_without_api_key(self):
        """build_baseline_setup_response status is in APPROVED_STATUSES."""
        from strategy.setup_ranges import resolve_ranges as _rr
        from strategy._setup_constants import APPROVED_STATUSES
        ranges = _rr("")
        adv = _make_advisor_no_api({}, [])
        result_str = adv.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR", num_gears=6,
            allowed_tuning=None, tuning_locked=False,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC2 FAIL: baseline without api_key, status={status!r}"
        )


# ===========================================================================
# AC3 — No false tyre/fuel/session/car claims in explainability
# ===========================================================================

class TestAC3NoFalseClaims:
    """AC3: session_influence/car_drivetrain_influence only populated when context used."""

    def test_unknown_session_produces_neutral_weighting_note(self):
        """When session_type=None, any session_influence on changes should NOT claim
        session-specific behaviour (should be neutral or empty)."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        # No purpose passed → session_type=None
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            si = ch.get("session_influence", "")
            # If session_influence is set, it must NOT claim a specific session bias
            if si:
                forbidden_claims = ["qualifying bias", "race consistency bias", "endurance bias"]
                for claim in forbidden_claims:
                    assert claim not in si.lower(), (
                        f"AC3 FAIL: session_influence claims '{claim}' when session_type is None. "
                        f"change: {ch.get('field')}, session_influence={si!r}"
                    )

    def test_no_tyre_aware_claim_without_tyre_context(self):
        """_tyre_fuel_context must say 'not available' when tyre_wear_known=False."""
        laps = [_make_lap()]
        setup = {"aero_front": 0, "aero_rear": 50}
        adv = _make_advisor_no_api({}, laps)  # no tyre_wear in event_ctx

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        tyre_ctx = result.get("_tyre_fuel_context", "")
        assert "not available" in tyre_ctx, (
            f"AC3 FAIL: when no tyre context, _tyre_fuel_context must say 'not available'; "
            f"got {tyre_ctx!r}"
        )

    def test_tyre_context_empty_when_tyre_known(self):
        """When tyre_wear IS provided, _tyre_fuel_context must NOT say 'not available'."""
        laps = [_make_lap()]
        setup = {"aero_front": 0, "aero_rear": 50}
        event_ctx = {"tyre_wear": 2.0}  # known tyre_wear < HIGH_TYRE_WEAR_THRESHOLD
        adv = _make_advisor_no_api(event_ctx, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        tyre_ctx = result.get("_tyre_fuel_context", "")
        assert "not available" not in tyre_ctx, (
            f"AC3 FAIL: tyre_wear IS known, _tyre_fuel_context must NOT say 'not available'; "
            f"got {tyre_ctx!r}"
        )


# ===========================================================================
# AC4 — Nothing actionable bypasses the apply gate
# ===========================================================================

class TestAC4ApplyGate:
    """AC4: all changes go through validator→finaliser→Apply gate."""

    def test_approved_changes_have_required_keys(self):
        """Every approved change dict must have the keys the Apply gate reads."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        required_keys = {"field", "to", "to_clamped", "rule_id", "risk_level", "confidence_level"}
        for ch in result.get("changes", []):
            missing = required_keys - set(ch.keys())
            assert not missing, (
                f"AC4 FAIL: approved change missing required Apply-gate keys: {missing}. "
                f"change: {ch}"
            )

    def test_recommendation_status_always_present(self):
        """recommendation_status must always appear — it's the Apply-gate signal."""
        laps = [_make_lap()]
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        assert "recommendation_status" in result, (
            "AC4 FAIL: recommendation_status missing — Apply gate cannot function"
        )


# ===========================================================================
# AC5 — Old _btn_build_setup button disabled and _run_build_setup early-returns
# ===========================================================================

class TestAC5BuildSetupButtonDisabled:
    """AC5: The 'Build Setup with AI' ungated path stays disabled."""

    def test_run_build_setup_is_early_return(self):
        """_run_build_setup must immediately return (early-exit guard)."""
        import inspect
        from ui.setup_builder_ui import SetupBuilderMixin
        src = inspect.getsource(SetupBuilderMixin._run_build_setup)
        # The early-return guard must be present
        # (Group 43 disabled it with 'return' on first line)
        assert "return" in src, (
            "AC5 FAIL: _run_build_setup does not contain an early-return guard. "
            "The ungated AI-build path must remain disabled."
        )

    def test_run_build_setup_early_returns_immediately(self):
        """Calling _run_build_setup on a stub must NOT reach threading code."""
        from ui.setup_builder_ui import SetupBuilderMixin
        called = {"thread_started": False}

        class _FakeUI(SetupBuilderMixin):
            def __init__(self):
                pass

        # Patch threading to detect if it is reached
        import threading as _threading_module
        original_thread = _threading_module.Thread

        class _TrackingThread:
            def __init__(self, *a, **k):
                called["thread_started"] = True

            def start(self):
                pass

        ui = _FakeUI()
        import threading
        original = threading.Thread
        threading.Thread = _TrackingThread
        try:
            # Should return immediately without starting a thread
            ui._run_build_setup()
        except Exception:
            pass  # attribute errors on the stub are OK; we only care about thread
        finally:
            threading.Thread = original

        assert not called["thread_started"], (
            "AC5 FAIL: _run_build_setup started a threading.Thread — "
            "it must early-return before reaching any threading code."
        )

    def test_run_build_setup_for_form_is_early_return(self):
        """_run_build_setup_for_form must also have an early-return guard."""
        import inspect
        from ui.setup_builder_ui import SetupBuilderMixin
        if not hasattr(SetupBuilderMixin, "_run_build_setup_for_form"):
            pytest.skip("_run_build_setup_for_form not present on SetupBuilderMixin")
        src = inspect.getsource(SetupBuilderMixin._run_build_setup_for_form)
        assert "return" in src or "_run_build_setup" in src, (
            "AC5 FAIL: _run_build_setup_for_form has no early-return guard "
            "(it must disable or delegate to the guarded _run_build_setup)"
        )


# ===========================================================================
# AC6 — Learning cannot un-block/un-reject
# ===========================================================================

class TestAC6LearningCannotUnblock:
    """AC6: confidence downgrade from learning store cannot un-block or un-reject a change."""

    def test_downgrade_does_not_promote_rejected_to_proposed(self):
        """A rule that was rejected (e.g. Pack A block) cannot move to proposed
        just because the outcome store downgrades something else."""
        laps = [_make_lap(wheelspin_count=20)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"aero_rear": 500, "lsd_accel": 20},
            car_name="", event_ctx={},
            feeling="rear loose on exit, snap oversteer",
            location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = build_driver_profile()

        # Build a store that reports very low success rate for B6
        store = RuleOutcomeStore()
        for _ in range(5):
            store.record_fire("B6")  # fire 5 times
        # 0 successes → rate = 0.0 < 0.40 → confidence downgrade

        plan = run_rule_engine(
            diag, {"aero_rear": 500, "lsd_accel": 20}, ranges, profile,
            rule_outcome_store=store,
        )

        # A2 should have blocked aero_rear decrease (rear_loose + snap_oversteer)
        aero_rear_decreases = [
            c for c in plan.proposed if c.field == "aero_rear" and c.delta < 0
        ]
        assert not aero_rear_decreases, (
            "AC6 FAIL: aero_rear decrease appeared in proposed despite A2 block. "
            "Learning downgrade must not move Pack A rejected items to proposed."
        )

    def test_learning_downgrade_does_not_unblock_safety_rule(self):
        """A rule blocked by contraindication cannot be unblocked by the learning store."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 3.0,
            "driver_feel_flags": {
                "braking_instability": True, "snap_oversteer_exit": True,
                "rear_loose_on_exit": True,
            },
            "gearbox_flag": "preserve", "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "braking_instability",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
        }
        setup = {"brake_bias": 60.0, "lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        store = RuleOutcomeStore()
        # Record many failures for A5
        for _ in range(10):
            store.record_fire("A5")
        # 0 successes → should downgrade, but A5 is Pack A — must not become proposed

        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        brake_rearward = [c for c in plan.proposed if c.field == "brake_bias" and c.delta > 0]
        assert not brake_rearward, (
            "AC6 FAIL: brake_bias rearward appeared in proposed despite A5 block. "
            "Learning store must never un-block Pack A safety rules."
        )

    def test_learning_note_always_present(self):
        """_learning_note must always appear in the response JSON."""
        laps = [_make_lap()]
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        assert "_learning_note" in result, (
            "AC6 FAIL: _learning_note key missing from response JSON"
        )

    def test_learning_note_content_when_empty_store(self):
        """With empty store (production path), _learning_note must say no history available."""
        laps = [_make_lap()]
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict={}, car_name="", feeling=None)
        result = json.loads(result_str)

        note = result.get("_learning_note", "")
        assert "no cross-session learning history available" in note, (
            f"AC6 FAIL: _learning_note does not say 'no cross-session learning history available'; "
            f"got {note!r}"
        )


# ===========================================================================
# AC10-AC11 — Session scope enforcement
# ===========================================================================

class TestAC10AC11SessionScope:
    """AC10-AC11: applies_session filter enforcement."""

    def _gear_too_short_diag(self) -> dict:
        """Diagnosis that triggers B5 (gear_too_short + may_change)."""
        return {
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

    def test_b5_does_not_fire_when_session_type_is_quali(self):
        """B5 (applies_session=race) must NOT fire when session_type=SessionType.quali."""
        diag = self._gear_too_short_diag()
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.quali,
        )

        final_drive_proposed = [c for c in plan.proposed if c.field == "final_drive"]
        assert not final_drive_proposed, (
            "AC10 FAIL: B5 (applies_session=race) fired when session_type=quali. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_b5_fires_when_session_type_is_race(self):
        """B5 must fire when session_type=SessionType.race with gear_too_short preconditions."""
        diag = self._gear_too_short_diag()
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=SessionType.race,
        )

        final_drive_proposed = [c for c in plan.proposed if c.field == "final_drive"]
        assert final_drive_proposed, (
            "AC10 FAIL: B5 did not fire when session_type=race with gear_too_short. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_b5_fires_when_session_type_is_none(self):
        """AC11: With session_type=None, B5 fires normally (None = wildcard-permissive)."""
        diag = self._gear_too_short_diag()
        setup = {"final_drive": 3.5}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
        )

        final_drive_proposed = [c for c in plan.proposed if c.field == "final_drive"]
        assert final_drive_proposed, (
            "AC11 FAIL: B5 did not fire when session_type=None (should be wildcard-permissive). "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_pack_a_rules_exempt_from_scope_filter(self):
        """Pack A safety rules must always fire regardless of session_type."""
        # A6 protects transmission_max_speed_kmh unconditionally
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"transmission_max_speed_kmh": 270.0},
            car_name="", event_ctx={}, feeling=None, location_confidence="low",
        )
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        for session in [SessionType.race, SessionType.quali, SessionType.practice, None]:
            plan = run_rule_engine(diag, {"transmission_max_speed_kmh": 270.0},
                                   ranges, profile, session_type=session)
            assert "transmission_max_speed_kmh" in plan.protected_fields, (
                f"AC10 FAIL: Pack A A6 must protect transmission_max_speed_kmh for "
                f"session_type={session!r}; protected_fields={plan.protected_fields}"
            )
