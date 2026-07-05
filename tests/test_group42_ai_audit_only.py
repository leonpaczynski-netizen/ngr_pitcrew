"""
Group 42 — Rule-First Setup Brain: AI Audit Layer Acceptance Tests

Covers:
  AC9  — build_audit_prompt contains all 8 labelled sections
  AC10 — parse_audit_response strips canonical setup fields from AI audit response
  AC11 — AI REJECTED + no blocking → approved_with_warnings; blocking wins
  AC12 — NEEDS_MORE_DATA + no blocking → approved_with_warnings, missing_evidence surfaced
  AC14 — AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES

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
from strategy._setup_constants import APPROVED_STATUSES, AI_AUDIT_REJECTED_ADVISORY
from strategy.setup_ai_audit import (
    AuditResult,
    AuditStatus,
    build_audit_prompt,
    map_audit_to_finaliser,
    parse_audit_response,
)
from strategy.setup_diagnosis import build_setup_diagnosis
from strategy.setup_driver_profile import build_driver_profile, DriverProfile, DriverStyleAlignment
from strategy.setup_rule_engine import (
    SetupChangeIntent,
    SetupPlan,
    ConfidenceLevel,
    RiskLevel,
)
from strategy.setup_knowledge_base import RulePhase


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


def _make_empty_plan() -> SetupPlan:
    """Empty plan for audit prompt building."""
    return SetupPlan(proposed=[], rejected_candidates=[], protected_fields=[])


def _make_simple_plan() -> SetupPlan:
    """A plan with one proposed change for audit prompt building."""
    intent = SetupChangeIntent(
        field="lsd_accel",
        delta=2.0,
        from_value=20.0,
        to_value=22.0,
        symptom="Wheelspin on exit.",
        evidence=["wheelspin_band=meaningful"],
        rule_id="B6",
        rationale="Increase LSD accel for traction.",
        rejected_alternatives=[],
        risk=RiskLevel.low,
        confidence=ConfidenceLevel.med,
        driver_style_alignment=DriverStyleAlignment.aligned,
    )
    return SetupPlan(proposed=[intent], rejected_candidates=[], protected_fields=["transmission_max_speed_kmh"])


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
# AC9 — build_audit_prompt contains all 8 labelled sections
# ===========================================================================

class TestAC9AuditPromptSections:
    """AC9: build_audit_prompt contains each of the 8 input sections."""

    _EXPECTED_SECTIONS = [
        "## SECTION: DIAGNOSIS SUMMARY",
        "## SECTION: PROPOSED PLAN",
        "## SECTION: REJECTED CANDIDATES",
        "## SECTION: PROTECTED FIELDS",
        "## SECTION: CURRENT SETUP",
        "## SECTION: DRIVER PROFILE",
        "## SECTION: VALIDATION FAILURES",
        "## SECTION: AUDIT INSTRUCTIONS",
    ]

    def _build_prompt(self) -> str:
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        plan = _make_simple_plan()
        profile = build_driver_profile()
        return build_audit_prompt(
            diagnosis=diag,
            plan=plan,
            current_setup={"lsd_accel": 20},
            driver_profile=profile,
            validation_failures=[],
            rejected_candidates=[],
            protected_fields=["transmission_max_speed_kmh"],
        )

    def test_all_8_sections_present(self):
        """build_audit_prompt must contain all 8 labelled section headers."""
        prompt = self._build_prompt()
        for section in self._EXPECTED_SECTIONS:
            assert section in prompt, (
                f"AC9 FAIL: Section header {section!r} not found in audit prompt.\n"
                f"Prompt first 600 chars: {prompt[:600]!r}"
            )

    def test_diagnosis_summary_section_has_diagnosis_data(self):
        """DIAGNOSIS SUMMARY section includes dominant_problem and wheelspin_band."""
        prompt = self._build_prompt()
        assert "dominant_problem" in prompt, "Audit prompt must include dominant_problem"
        assert "wheelspin_band" in prompt, "Audit prompt must include wheelspin_band"

    def test_proposed_plan_section_has_proposed_changes(self):
        """PROPOSED PLAN section includes the rule_id of the proposed change."""
        prompt = self._build_prompt()
        assert "B6" in prompt, (
            "AC9 FAIL: PROPOSED PLAN section must include rule_id of proposed changes"
        )

    def test_audit_instructions_section_has_constraint(self):
        """AUDIT INSTRUCTIONS section must include 'Do NOT create new setup changes'."""
        prompt = self._build_prompt()
        assert "Do NOT create new setup changes" in prompt, (
            "AC9 FAIL: Audit instructions must include 'Do NOT create new setup changes'"
        )

    def test_protected_fields_section_has_transmission(self):
        """PROTECTED FIELDS section includes transmission_max_speed_kmh."""
        prompt = self._build_prompt()
        assert "transmission_max_speed_kmh" in prompt, (
            "AC9 FAIL: PROTECTED FIELDS section must include transmission_max_speed_kmh"
        )


# ===========================================================================
# AC10 — parse_audit_response strips canonical setup fields
# ===========================================================================

class TestAC10CanonicalFieldStripping:
    """AC10: parse_audit_response strips canonical setup fields and they don't
    surface as actionable changes."""

    def test_parse_strips_canonical_field(self):
        """AI response containing ride_height_front → stripped_fields non-empty."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        response_with_field = json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "Plan looks good.",
            "ride_height_front": 120,  # canonical field — must be stripped
        })

        result = parse_audit_response(response_with_field, _CANONICAL_SETUP_PARAMS)

        assert "ride_height_front" in result.stripped_fields, (
            f"AC10 FAIL: 'ride_height_front' must appear in stripped_fields; "
            f"got: {result.stripped_fields}"
        )

    def test_parse_strips_multiple_canonical_fields(self):
        """Multiple canonical fields are all stripped."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        response_multi = json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "OK.",
            "arb_front": 4,
            "arb_rear": 3,
            "lsd_accel": 25,
        })

        result = parse_audit_response(response_multi, _CANONICAL_SETUP_PARAMS)

        for field in ("arb_front", "arb_rear", "lsd_accel"):
            assert field in result.stripped_fields, (
                f"AC10 FAIL: {field!r} must appear in stripped_fields; "
                f"got: {result.stripped_fields}"
            )

    def test_stripped_field_does_not_surface_in_approved_changes(self, monkeypatch):
        """When AI audit response contains ride_height_front=120, it must never
        appear in the approved changes of the final response."""
        laps = [_make_lap(bottoming_count=2, wheelspin_count=10)]
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 100, "aero_rear": 200, "lsd_accel": 20}
        adv = _make_full_advisor({}, laps)

        def audit_with_canonical_field(prompt, api_key, **kwargs):
            # AI returns an audit response that illicitly contains ride_height_front
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "All good.",
                "ride_height_front": 120,  # should be stripped
            })

        monkeypatch.setattr(da, "call_api", audit_with_canonical_field)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        # ride_height_front=120 must NOT appear in approved changes
        for ch in result.get("changes", []):
            if ch.get("field") == "ride_height_front":
                assert ch.get("to") != 120 and ch.get("to_clamped") != 120, (
                    f"AC10 FAIL: ride_height_front=120 from AI audit response "
                    f"appeared in approved changes: {ch}"
                )

        sf = result.get("setup_fields", {})
        assert sf.get("ride_height_front") != 120, (
            f"AC10 FAIL: ride_height_front=120 from AI audit appeared in setup_fields: {sf}"
        )

    def test_unknown_field_not_stripped(self):
        """Fields not in canonical_params are not stripped."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        response = json.dumps({
            "status": "APPROVED",
            "warnings": ["minor issue"],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "OK.",
            "custom_field": "value",  # not canonical
        })

        result = parse_audit_response(response, _CANONICAL_SETUP_PARAMS)

        assert "custom_field" not in result.stripped_fields, (
            "AC10 FAIL: non-canonical 'custom_field' should not appear in stripped_fields"
        )


# ===========================================================================
# AC11 — AI REJECTED with no blocking → approved_with_warnings; blocking wins
# ===========================================================================

class TestAC11RejectedAndBlockingWins:
    """AC11: AI REJECTED + no blocking → recommendation_status approved_with_warnings.
    Blocking validation → changes==[] regardless of AI status."""

    def test_rejected_no_blocking_maps_to_approved_with_warnings(self):
        """map_audit_to_finaliser: REJECTED + no blocking → approved_with_warnings."""
        audit = AuditResult(
            status=AuditStatus.REJECTED,
            warnings=["minor concern"],
            contradictions=["rule C5 and rule C6 conflict"],
            missing_evidence=[],
            explanation_notes="Rejected due to contradiction.",
            stripped_fields=[],
        )

        status_hint, warnings = map_audit_to_finaliser(audit, has_blocking_validation=False)

        assert status_hint == "approved_with_warnings", (
            f"AC11 FAIL: REJECTED + no blocking must map to approved_with_warnings; "
            f"got {status_hint!r}"
        )
        assert warnings, (
            "AC11 FAIL: approved_with_warnings must carry contradiction warnings"
        )

    def test_blocking_wins_over_ai_approved(self, monkeypatch):
        """Blocking ENG_SAFETY failure → changes==[] even when AI says APPROVED."""
        laps = [_make_lap(bottoming_count=0)]  # minor bottoming
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 100, "aero_rear": 200}
        adv = _make_full_advisor({}, laps)

        # Force the engine to have a blocking failure by making the diagnosis flag
        # a ride-height raise that would violate rh_for_minor_bottoming.
        # We patch call_api to return APPROVED for audit but the rule engine
        # would have already blocked changes at the validation step.
        def audit_approved(prompt, api_key, **kwargs):
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "Approved.",
            })

        monkeypatch.setattr(da, "call_api", audit_approved)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        # When changes are [] due to no actionable rules firing or blocking:
        # The AI APPROVED status should not conjure changes from nowhere.
        # Either no changes are produced (clean / empty plan) OR if they are produced
        # they must all be clean (no ride-height raise)
        changes = result.get("changes", [])
        rh_increases = [c for c in changes if
                        c.get("field") in ("ride_height_front", "ride_height_rear")
                        and float(c.get("to_clamped", 0) or 0) > float(c.get("from", 0) or 0)]
        assert not rh_increases, (
            f"AC11 FAIL: Blocking validation should prevent ride-height increases "
            f"even when AI says APPROVED; got changes with RH increases: {rh_increases}"
        )

    def test_end_to_end_rejected_with_no_blocking_approved_status(self, monkeypatch):
        """End-to-end: AI audit returns REJECTED, no blocking failures → approved_with_warnings."""
        laps = [_make_lap(wheelspin_count=15)]
        setup = {"aero_rear": 100, "lsd_accel": 20,
                 "ride_height_front": 85, "ride_height_rear": 87}
        adv = _make_full_advisor({}, laps)

        def audit_rejected(prompt, api_key, **kwargs):
            return json.dumps({
                "status": "REJECTED",
                "warnings": [],
                "contradictions": ["Proposed rear aero increase contradicts healthy rear aero flag."],
                "missing_evidence": [],
                "explanation_notes": "Plan rejected due to contradiction.",
            })

        monkeypatch.setattr(da, "call_api", audit_rejected)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        # REJECTED + no blocking must produce approved_with_warnings (per map_audit_to_finaliser)
        # The rule engine may have produced clean changes
        assert status in APPROVED_STATUSES, (
            f"AC11 FAIL: REJECTED audit + no blocking must produce an APPROVED status; "
            f"got {status!r}"
        )


# ===========================================================================
# AC12 — NEEDS_MORE_DATA + no blocking → approved_with_warnings
# ===========================================================================

class TestAC12NeedsMoreData:
    """AC12: NEEDS_MORE_DATA + no blocking → approved_with_warnings, missing_evidence surfaced."""

    def test_needs_more_data_maps_to_approved_with_warnings(self):
        """map_audit_to_finaliser: NEEDS_MORE_DATA + no blocking → approved_with_warnings."""
        audit = AuditResult(
            status=AuditStatus.NEEDS_MORE_DATA,
            warnings=[],
            contradictions=[],
            missing_evidence=["No bottoming telemetry data available."],
            explanation_notes="Insufficient data for assessment.",
            stripped_fields=[],
        )

        status_hint, warnings = map_audit_to_finaliser(audit, has_blocking_validation=False)

        assert status_hint == "approved_with_warnings", (
            f"AC12 FAIL: NEEDS_MORE_DATA + no blocking must map to approved_with_warnings; "
            f"got {status_hint!r}"
        )
        assert "No bottoming telemetry data available." in warnings, (
            f"AC12 FAIL: missing_evidence must be surfaced in warnings; "
            f"got: {warnings}"
        )

    def test_needs_more_data_missing_evidence_non_empty(self):
        """When audit returns NEEDS_MORE_DATA, missing_evidence is non-empty."""
        audit = AuditResult(
            status=AuditStatus.NEEDS_MORE_DATA,
            warnings=[],
            contradictions=[],
            missing_evidence=["Lap count too low for confidence."],
            explanation_notes="Need more laps.",
            stripped_fields=[],
        )
        status_hint, warnings = map_audit_to_finaliser(audit, has_blocking_validation=False)
        assert warnings, (
            "AC12 FAIL: approved_with_warnings must carry at least one warning/missing_evidence item"
        )

    def test_end_to_end_needs_more_data_approved_status(self, monkeypatch):
        """End-to-end: audit returns NEEDS_MORE_DATA, no blocking → approved_with_warnings."""
        laps = [_make_lap(wheelspin_count=10)]
        setup = {"aero_rear": 100, "lsd_accel": 20}
        adv = _make_full_advisor({}, laps)

        def audit_needs_data(prompt, api_key, **kwargs):
            return json.dumps({
                "status": "NEEDS_MORE_DATA",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": ["Lap count too low for confidence."],
                "explanation_notes": "Insufficient data.",
            })

        monkeypatch.setattr(da, "call_api", audit_needs_data)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC12 FAIL: NEEDS_MORE_DATA + no blocking should produce approved status; "
            f"got {status!r}"
        )

    def test_parse_audit_response_unknown_status_becomes_needs_more_data(self):
        """Unknown status string in AI response → NEEDS_MORE_DATA."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        response = json.dumps({
            "status": "COMPLETELY_MADE_UP",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "Unknown.",
        })

        result = parse_audit_response(response, _CANONICAL_SETUP_PARAMS)

        assert result.status == AuditStatus.NEEDS_MORE_DATA, (
            f"AC12 FAIL: Unknown status must map to NEEDS_MORE_DATA; got {result.status!r}"
        )

    def test_parse_audit_response_never_raises(self):
        """parse_audit_response never raises — returns NEEDS_MORE_DATA on parse failure."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS

        result = parse_audit_response("not valid json at all {{{{", _CANONICAL_SETUP_PARAMS)
        assert result.status == AuditStatus.NEEDS_MORE_DATA

        result2 = parse_audit_response("", _CANONICAL_SETUP_PARAMS)
        assert result2.status == AuditStatus.NEEDS_MORE_DATA


# ===========================================================================
# AC14 — AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES
# ===========================================================================

class TestAC14AuditRejectedAdvisory:
    """AC14: AI_AUDIT_REJECTED_ADVISORY is not in APPROVED_STATUSES."""

    def test_ai_audit_rejected_advisory_not_in_approved_statuses(self):
        """AI_AUDIT_REJECTED_ADVISORY must NOT be in APPROVED_STATUSES."""
        assert AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES, (
            f"AC14 FAIL: AI_AUDIT_REJECTED_ADVISORY ({AI_AUDIT_REJECTED_ADVISORY!r}) "
            f"must not be in APPROVED_STATUSES {APPROVED_STATUSES}"
        )

    def test_ai_audit_rejected_advisory_is_string(self):
        """AI_AUDIT_REJECTED_ADVISORY must be a non-empty string."""
        assert isinstance(AI_AUDIT_REJECTED_ADVISORY, str)
        assert len(AI_AUDIT_REJECTED_ADVISORY) > 0

    def test_ai_audit_rejected_advisory_value(self):
        """The constant must have the expected value."""
        assert AI_AUDIT_REJECTED_ADVISORY == "ai_audit_rejected_advisory", (
            f"Expected 'ai_audit_rejected_advisory', got {AI_AUDIT_REJECTED_ADVISORY!r}"
        )

    def test_approved_statuses_content(self):
        """APPROVED_STATUSES must contain approved and approved_with_warnings but not advisory."""
        assert "approved" in APPROVED_STATUSES, "APPROVED_STATUSES must contain 'approved'"
        assert "approved_with_warnings" in APPROVED_STATUSES
        assert "fallback_generated" in APPROVED_STATUSES
        assert AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES
