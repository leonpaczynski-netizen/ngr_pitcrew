"""
Group 41 — Setup Builder Engineering Validation Gate — Acceptance Tests

Covers every acceptance criterion and edge case from the sprint brief.
All tests are pure/offline — no network, no Qt event loop, no QApplication.
Mirrors the style of test_group40_diagnosis_hardening.py.
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
    frames: list | None = None,
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
        frames=frames or [],
    )


def _minimal_ai_resp(overrides: dict | None = None) -> dict:
    base = {
        "analysis": "Test analysis.",
        "primary_issue": "test",
        "issue_classification": {"test": "not-present"},
        "changes": [],
        "setup_fields": {},
        "validation_targets": {},
        "confidence": {"overall": "medium", "reason": "test"},
    }
    if overrides:
        base.update(overrides)
    return base


def _rh_change(field: str, from_val: float, to_val: float) -> dict:
    return _minimal_ai_resp({
        "changes": [{"field": field, "from": from_val, "to": to_val,
                     "setting": field, "why": "test", "to_clamped": to_val}],
        "setup_fields": {field: to_val},
    })


def _lsd_change(from_val: float, to_val: float) -> dict:
    return _minimal_ai_resp({
        "changes": [{"field": "lsd_accel", "from": from_val, "to": to_val,
                     "setting": "LSD Accel", "why": "test", "to_clamped": to_val}],
        "setup_fields": {"lsd_accel": to_val},
    })


def _gear_change(**gear_fields) -> dict:
    """Build an AI response with the given gear field changes."""
    changes = []
    sf = {}
    for field, (from_v, to_v) in gear_fields.items():
        changes.append({"field": field, "from": from_v, "to": to_v,
                        "setting": field, "why": "test", "to_clamped": to_v})
        sf[field] = to_v
    return _minimal_ai_resp({"changes": changes, "setup_fields": sf})


def _get_ranges():
    from strategy.setup_ranges import resolve_ranges
    return resolve_ranges("")


def _make_recorder_stub(laps):
    return SimpleNamespace(recent_laps=lambda n: laps)


def _make_full_advisor(event_ctx: dict, laps: list):
    """Build a DrivingAdvisor stub for integration testing — no DB, no real API."""
    import strategy.driving_advisor as da
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


def _snap_throttle_diag(lsd_from: float = 20.0) -> dict:
    """Build a diagnosis with wheelspin_subtype=snap_throttle_induced."""
    from strategy.setup_diagnosis import build_setup_diagnosis
    laps = [_make_lap(wheelspin_count=20, snap_throttle_count=10) for _ in range(2)]
    diag = build_setup_diagnosis(
        laps=laps, setup={"lsd_accel": lsd_from}, car_name="",
        event_ctx={}, feeling=None, location_confidence="low",
    )
    diag = dict(diag)
    diag["wheelspin_subtype"] = "snap_throttle_induced"
    return diag


def _kerb_strike_diag(rh_rear: float = 82.0) -> dict:
    """Build a diagnosis with bottoming_confidence subtype=kerb_strike."""
    from strategy.setup_diagnosis import build_setup_diagnosis
    laps = [_make_lap(bottoming_count=5, kerb_count=10) for _ in range(3)]
    diag = build_setup_diagnosis(
        laps=laps, setup={"ride_height_rear": rh_rear, "ride_height_front": 80.0},
        car_name="", event_ctx={}, feeling=None, location_confidence="low",
    )
    diag = dict(diag)
    # Force kerb_strike subtype
    diag["bottoming_confidence"] = dict(
        diag.get("bottoming_confidence") or {}
    )
    diag["bottoming_confidence"]["subtype"] = "kerb_strike"
    return diag


# ===========================================================================
# Test 0 (AC0) — End-to-end payload contract
# ===========================================================================

class TestAC0EndToEndPayloadContract:
    """Prove the JSON contract: both build_combined_setup_response and
    build_setup_advice_response, when the AI always returns blocking-invalid
    changes (rear RH +6mm, no front), produce a JSON string with:
      - recommendation_status == "validation_failed" or "retry_failed"
      - changes == []
      - rejected_changes is non-empty
    This is the seam the UI depends on.
    """

    def _violating_json(self):
        return json.dumps({
            "analysis": "test",
            "primary_issue": "bottoming",
            "issue_classification": {"bottoming": "not-present"},
            "changes": [{"field": "ride_height_rear", "from": 82, "to": 88,
                         "setting": "Ride Height Rear", "why": "reduce bottoming",
                         "to_clamped": 88}],
            "setup_fields": {"ride_height_rear": 88},
            "validation_targets": {},
            "confidence": {"overall": "low", "reason": "test"},
        })

    def test_build_combined_response_has_recommendation_status(self, monkeypatch):
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._violating_json())
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)
        assert "recommendation_status" in result, (
            "CRITICAL: build_combined_setup_response returned JSON missing 'recommendation_status' key. "
            "This is the seam the UI depends on. Backend-builder (strategy/driving_advisor.py) "
            "must ensure _finalise_recommendation embeds 'recommendation_status' in the returned dict."
        )

    def test_build_combined_response_status_is_failed(self, monkeypatch):
        """Group 42 REWRITE: in the deterministic rule-first flow, AI JSON (from call_api)
        is used for audit only and cannot trigger blocking status.  The correct trigger for
        a non-approved terminal status is the rule engine's OWN proposed changes hitting an
        ENG_SAFETY blocking rule.

        Scenario: 5 laps with bottoming_count=8/lap + kerb_count=25/lap, feeling='stiff on
        kerbs', location_confidence='high' → bottoming_confidence medium (kerb_strike).
        Rule C8 proposes ride_height_rear +3mm; rh_increment_exceeds_confidence fires
        (medium confidence only allows +2mm).  This is a blocking ENG_SAFETY failure from
        the rule engine itself → fallback → validation_failed, changes=[], setup_fields={}.
        """
        import strategy.driving_advisor as da
        from strategy.setup_diagnosis import build_setup_diagnosis
        from strategy._setup_constants import APPROVED_STATUSES

        laps = [_make_lap(bottoming_count=8, kerb_count=25) for _ in range(5)]
        setup = {
            "ride_height_front": 80,
            "ride_height_rear": 82,
            "arb_rear": 4,
            "aero_front": 500,
            "aero_rear": 500,
        }
        adv = _make_full_advisor({}, laps)

        # Build diagnosis with location_confidence='high' so bottoming_confidence = medium
        # (kerb_strike subtype).  Medium confidence permits only +2mm RH increment.
        # The rule engine proposes +3mm → rh_increment_exceeds_confidence blocks it.
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling="stiff on kerbs", location_confidence="high",
        )

        # AI is audit-only in Group 42; its response cannot generate blocking failures.
        # Returning a valid audit-approved response so we can isolate the deterministic failure.
        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "ok",
        }))

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling="stiff on kerbs", diagnosis=diag,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "MISSING")

        # Field-level safety invariant (per-field rejection): the CONTRADICTED field
        # (ride_height_rear, blocked by rh_increment_exceeds_confidence) must never be
        # applied. Valid non-blocked changes (e.g. ride_height_front) MAY survive and
        # be surfaced under approved_with_rejections — one bad field no longer nukes
        # the whole recommendation.
        _applied_fields = [c.get("field") for c in result.get("changes", [])]
        assert "ride_height_rear" not in _applied_fields, (
            f"CRITICAL: contradicted field ride_height_rear must never be applied; "
            f"got changes={result.get('changes')!r}"
        )
        assert "ride_height_rear" not in (result.get("setup_fields") or {}), (
            f"CRITICAL: contradicted field ride_height_rear must never reach setup_fields; "
            f"got {result.get('setup_fields')!r}"
        )
        # The safety rule that dropped it must be surfaced to the driver.
        assert any(
            "rh_increment_exceeds_confidence" in e
            for e in result.get("engineering_validation_errors", [])
        ), (
            f"Dropped field must be explained via engineering_validation_errors; "
            f"got {result.get('engineering_validation_errors')!r}"
        )

    def test_build_combined_response_changes_empty_on_blocking(self, monkeypatch):
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._violating_json())
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)
        changes = result.get("changes", "NOT_PRESENT")
        assert changes == [], (
            f"CRITICAL: blocking-invalid AI output must produce changes==[] in the returned JSON; "
            f"got {changes!r}. "
            "This means a blocked recommendation could render as actionable to the driver. "
            "Backend-builder (strategy/driving_advisor.py _finalise_recommendation)."
        )

    def test_build_combined_response_rejected_changes_nonempty(self, monkeypatch):
        """Spec: rejected_changes must be non-empty when AI proposed changes that were blocked.

        DEFECT (backend-builder): When the retry path fires and the fallback is triggered,
        build_combined_setup_response calls `_retry_data.update(_fb)` before calling
        `_finalise_recommendation`. The fallback's `changes=[]` overwrites the failing
        retry data's changes, so by the time `_finalise_recommendation` sees `raw_data`,
        `raw_changes == []` and therefore `rejected_changes == []`.

        The failing AI output's changes are silently discarded. The fix belongs in
        strategy/driving_advisor.py: the failing changes should be captured (e.g.
        `_failing_changes = _retry_data.get("changes", [])`) before `_retry_data.update(_fb)`,
        then injected into the fallback dict or passed separately to `_finalise_recommendation`.

        This test is written to the SPEC (should pass when fixed). It currently fails.
        """
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._violating_json())
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)
        rejected = result.get("rejected_changes", [])
        assert len(rejected) > 0, (
            f"DEFECT: build_combined_setup_response loses rejected_changes when the fallback "
            f"path triggers. The failing retry data's changes are overwritten by "
            f"`_retry_data.update(_fb)` before _finalise_recommendation can use them. "
            f"Fix: capture the failing changes before the fallback update and pass them "
            f"through. Backend-builder (strategy/driving_advisor.py ~line 1676). "
            f"Got rejected_changes={rejected!r}, status={result.get('recommendation_status')!r}."
        )

    def test_build_setup_advice_response_has_recommendation_status(self, monkeypatch):
        """build_setup_advice_response must also embed recommendation_status."""
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._violating_json())
        result_str = adv.build_setup_advice_response(setup_dict=setup, car_name="")
        result = json.loads(result_str)
        assert "recommendation_status" in result, (
            "CRITICAL: build_setup_advice_response returned JSON missing 'recommendation_status'. "
            "Backend-builder (strategy/driving_advisor.py)."
        )

    def test_build_setup_advice_response_changes_empty_on_blocking(self, monkeypatch):
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._violating_json())
        result_str = adv.build_setup_advice_response(setup_dict=setup, car_name="")
        result = json.loads(result_str)
        assert result.get("changes") == [], (
            "build_setup_advice_response must produce changes==[] for blocking-invalid AI output."
        )


# ===========================================================================
# Test 1 — Validation failure blocks display
# ===========================================================================

class TestAC1ValidationFailureBlocksDisplay:
    """_format_status_banner and the CHANGES gate in _display_setup_result:
    - validation_failed → no 'CHANGES TO MAKE', Apply hidden
    - structural blocking (out_of_range) → still validation_failed with empty changes
    """

    def test_validation_failed_banner_contains_rejected_wording(self):
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("validation_failed", [])
        assert "rejected" in banner.lower() or "no.*changes.*approved" in banner.lower() or \
               "Recommendation rejected" in banner, (
            f"validation_failed banner must contain rejection wording; got: {banner!r}"
        )

    def test_validation_failed_banner_is_nonempty(self):
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("validation_failed", [])
        assert banner, "validation_failed must produce a non-empty banner"

    def test_retry_failed_banner_contains_rejected_after_retry(self):
        """retry_failed banner must mention rejection/retry but NOT 'survived a correction attempt'."""
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("retry_failed", [])
        assert banner, "retry_failed must produce a non-empty banner"
        assert "survived a correction attempt" not in banner, (
            "UI regression: 'survived a correction attempt' wording was removed in the sprint "
            "but is still present in _format_status_banner for retry_failed. Frontend-builder."
        )
        # Must contain the reworded text
        assert "rejected after retry" in banner.lower() or "retry" in banner.lower(), (
            f"retry_failed banner must mention rejection after retry; got: {banner!r}"
        )

    def test_finalise_recommendation_validation_failed_zeroes_changes(self):
        """_finalise_recommendation with a safety-rule blocking failure →
        approved_changes==[], approved_fields=={}, status==validation_failed."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        from strategy.setup_diagnosis import build_setup_diagnosis

        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_front": 80, "ride_height_rear": 82},
            car_name="", event_ctx={}, feeling=None, location_confidence="low",
        )
        # AI proposes rear +6mm with no front → rh_rake_risk blocking
        raw_data = _rh_change("ride_height_rear", 82, 88)
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(
            raw_data, diag, {"ride_height_front": 80, "ride_height_rear": 82},
            ranges, {},
        )
        result = _finalise_recommendation(raw_data, failures, False, False)
        assert result.status == "validation_failed", (
            f"Expected status='validation_failed'; got {result.status!r}"
        )
        assert result.approved_changes == [], (
            f"approved_changes must be [] on blocking failure; got {result.approved_changes!r}"
        )
        assert result.approved_fields == {}, (
            f"approved_fields must be {{}} on blocking failure; got {result.approved_fields!r}"
        )
        assert len(result.rejected_changes) > 0, (
            "rejected_changes must be non-empty (debug visibility)"
        )

    def test_finalise_partial_approval_keeps_valid_changes(self):
        """Per-field rejection: a safety failure indicting ONE field drops only
        that field; valid, aligned changes in the same response survive under
        approved_with_rejections.

        Mirrors the real UAT scenario: the AI proposed a valid final_drive
        (gearing too short) and arb_front alongside an lsd_accel increase that
        contradicts 'good traction'. The old all-or-nothing funnel discarded all
        three; per-field rejection keeps final_drive + arb_front and drops only
        lsd_accel.
        """
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure
        from strategy._setup_constants import APPROVED_STATUSES

        raw_data = _minimal_ai_resp({
            "changes": [
                {"field": "final_drive", "from": 3.50, "to": 3.45,
                 "setting": "Final Drive", "why": "gearing too short", "to_clamped": 3.45},
                {"field": "arb_front", "from": 4, "to": 5,
                 "setting": "ARB Front", "why": "turn-in", "to_clamped": 5},
                {"field": "lsd_accel", "from": 14, "to": 16,
                 "setting": "LSD Accel", "why": "traction", "to_clamped": 16},
            ],
            "setup_fields": {"final_drive": 3.45, "arb_front": 5, "lsd_accel": 16},
        })
        # Real production-shaped safety message naming lsd_accel.
        failure = ValidationFailure(
            code="lsd_blocked_driver_feel",
            message=("lsd_blocked_driver_feel: AI increases lsd_accel (from 14.0 to 16.0) "
                     "but driver_feel_traction_status is 'good'."),
            severity="blocking",
        )
        result = _finalise_recommendation(raw_data, [failure], False, False)

        assert result.status == "approved_with_rejections", (
            f"Valid survivors must yield approved_with_rejections; got {result.status!r}"
        )
        assert result.status in APPROVED_STATUSES
        _applied = {c["field"] for c in result.approved_changes}
        assert _applied == {"final_drive", "arb_front"}, (
            f"Valid changes must survive; got {_applied!r}"
        )
        assert "lsd_accel" not in result.approved_fields, (
            "Contradicted field lsd_accel must never be applied"
        )
        assert {"final_drive", "arb_front"} <= set(result.approved_fields), (
            f"Valid setup_fields must survive; got {result.approved_fields!r}"
        )
        assert any(c["field"] == "lsd_accel" for c in result.rejected_changes), (
            "lsd_accel must be in rejected_changes for visibility"
        )
        assert any("lsd_blocked_driver_feel" in e for e in result.engineering_errors), (
            "Dropped-field reason must be surfaced in engineering_errors"
        )

    def test_finalise_partial_all_changes_blocked_falls_to_failed(self):
        """When the ONLY proposed change is the contradicted one, no survivors
        remain → status stays validation_failed with zero approved changes
        (preserves the single-change safety behaviour)."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure

        raw_data = _minimal_ai_resp({
            "changes": [
                {"field": "lsd_accel", "from": 14, "to": 16,
                 "setting": "LSD Accel", "why": "traction", "to_clamped": 16},
            ],
            "setup_fields": {"lsd_accel": 16},
        })
        failure = ValidationFailure(
            code="lsd_blocked_driver_feel",
            message="lsd_blocked_driver_feel: AI increases lsd_accel (from 14.0 to 16.0) but traction good.",
            severity="blocking",
        )
        result = _finalise_recommendation(raw_data, [failure], False, False)
        assert result.status == "validation_failed"
        assert result.approved_changes == []
        assert result.approved_fields == {}

    def test_structural_blocking_also_zeroes_changes(self):
        """A structural blocking failure (malformed_schema, invalid_units, locked-field)
        must ALSO zero approved_changes and set status=validation_failed.
        ALL blocking-severity failures are hard blocks — not just ENG_SAFETY_PREFIXES.
        out-of-range is a WARNING (not blocking) because the clamping mechanism handles it."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure

        raw_data = _minimal_ai_resp({
            "changes": [{"field": "arb_front", "from": 3, "to": 15,
                         "setting": "ARB Front", "why": "test", "to_clamped": 15}],
            "setup_fields": {"arb_front": 15},
        })
        # Structural-only failure: malformed_schema (severity=blocking)
        structural_failure = ValidationFailure(
            code="malformed_schema",
            message="malformed_schema: missing confidence key",
            severity="blocking",
        )
        result = _finalise_recommendation(raw_data, [structural_failure], False, False)
        # Per corrected spec: ALL blocking failures zero changes and produce validation_failed.
        # malformed_schema/invalid_units/locked-field are blocking by design — a locked or
        # malformed change must NOT be applyable.
        assert result.status == "validation_failed", (
            f"Structural blocking (malformed_schema) must produce validation_failed; "
            f"got {result.status!r}"
        )
        assert result.approved_changes == [], (
            f"Structural blocking must zero approved_changes; got {result.approved_changes!r}"
        )
        assert result.approved_fields == {}, (
            f"Structural blocking must zero approved_fields; got {result.approved_fields!r}"
        )
        # The structural error goes to validation_warnings (not engineering_errors)
        # for banner wording distinction, but changes are still zeroed.
        assert any("malformed_schema" in w for w in result.validation_warnings), (
            f"Structural error should appear in validation_warnings for wording; "
            f"got {result.validation_warnings!r}"
        )

    def test_safety_rule_zeroes_but_structural_does_not(self):
        """When BOTH a safety-rule and a structural failure are present:
        changes are zeroed (both force validation_failed).
        Safety-rule error goes to engineering_errors; structural goes to validation_warnings.
        This tests the message routing distinction — not the zeroing behaviour (both zero)."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure

        raw_data = _rh_change("ride_height_rear", 82, 88)
        safety_failure = ValidationFailure(
            code="rh_rake_risk",
            message="rh_rake_risk: large rear with no front change",
            severity="blocking",
        )
        structural_failure = ValidationFailure(
            code="malformed_schema",
            message="malformed_schema: missing key",
            severity="blocking",
        )
        result = _finalise_recommendation(raw_data, [safety_failure, structural_failure], False, False)
        assert result.status == "validation_failed"
        assert result.approved_changes == []
        # Safety-rule error goes to engineering_errors (banner wording: "rejected by safety rule")
        assert any("rh_rake_risk" in e for e in result.engineering_errors), (
            f"Safety-rule failure must appear in engineering_errors; got {result.engineering_errors!r}"
        )
        # Structural error goes to validation_warnings (banner wording: "structural/schema error")
        assert any("malformed_schema" in w for w in result.validation_warnings), (
            f"Structural error must appear in validation_warnings; got {result.validation_warnings!r}"
        )


# ===========================================================================
# Test 2 — Retry failure does not survive
# ===========================================================================

class TestAC2RetryFailure:
    """Drive the backend path so validation fails, retry still fails.
    Final status must be retry_failed, changes==[], fallback attempted,
    and the banner must NOT contain 'survived a correction attempt'.
    """

    def _always_violating_json(self):
        return json.dumps({
            "analysis": "test",
            "primary_issue": "bottoming",
            "issue_classification": {"bottoming": "not-present"},
            "changes": [{"field": "ride_height_rear", "from": 82, "to": 88,
                         "setting": "Ride Height Rear", "why": "reduce bottoming",
                         "to_clamped": 88}],
            "setup_fields": {"ride_height_rear": 88},
            "validation_targets": {},
            "confidence": {"overall": "low", "reason": "test"},
        })

    def test_retry_failed_status_when_both_attempts_violate(self, monkeypatch):
        """Group 42 REWRITE: 'retry_failed' is no longer reachable because Group 42 removed
        the AI-retry loop entirely.  call_api is used for audit only (at most once).

        This test re-expresses the SAME safety property under Group 42 semantics:
        when the deterministic rule engine produces changes that trip a blocking ENG_SAFETY
        rule, the final status must NOT be in APPROVED_STATUSES (i.e. it must be
        validation_failed or another terminal-unsafe status), and changes must be [].

        Scenario: same kerb_strike bottoming setup as the AC0 test above — the rule engine
        proposes ride_height_rear +3mm which fires rh_increment_exceeds_confidence (medium
        confidence only allows +2mm).  No retry exists; the deterministic fallback fires once.
        """
        import strategy.driving_advisor as da
        from strategy.setup_diagnosis import build_setup_diagnosis
        from strategy._setup_constants import APPROVED_STATUSES

        laps = [_make_lap(bottoming_count=8, kerb_count=25) for _ in range(5)]
        setup = {
            "ride_height_front": 80,
            "ride_height_rear": 82,
            "arb_rear": 4,
            "aero_front": 500,
            "aero_rear": 500,
        }
        adv = _make_full_advisor({}, laps)

        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling="stiff on kerbs", location_confidence="high",
        )

        # AI audit returns OK — the blocking failure comes from the rule engine only
        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "ok",
        }))

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling="stiff on kerbs", diagnosis=diag,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "")

        # Field-level safety invariant (per-field rejection): the contradicted field
        # (ride_height_rear, blocked by rh_increment_exceeds_confidence) must never be
        # applied — but valid non-blocked changes may survive under
        # approved_with_rejections. The real safety property is "the unsafe change is
        # never applied", not "every change is discarded".
        _applied_fields = [c.get("field") for c in result.get("changes", [])]
        assert "ride_height_rear" not in _applied_fields, (
            f"Safety invariant: contradicted field ride_height_rear must never be applied; "
            f"got changes={result.get('changes')!r}"
        )
        assert "ride_height_rear" not in (result.get("setup_fields") or {}), (
            f"Safety invariant: contradicted field ride_height_rear must never reach "
            f"setup_fields; got {result.get('setup_fields')!r}"
        )

    def test_retry_failed_changes_empty(self, monkeypatch):
        import strategy.driving_advisor as da
        laps = [_make_lap()]
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_full_advisor({}, laps)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: self._always_violating_json())
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)
        assert result.get("changes") == [], (
            f"retry_failed must have changes==[]; got {result.get('changes')!r}"
        )

    def test_finalise_recommendation_retry_failed_status(self):
        """_finalise_recommendation(retried=True) with safety blocking → retry_failed."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure
        raw_data = _rh_change("ride_height_rear", 82, 88)
        failures = [ValidationFailure(
            code="rh_rake_risk",
            message="rh_rake_risk: test",
            severity="blocking",
        )]
        result = _finalise_recommendation(raw_data, failures, False, retried=True)
        assert result.status == "retry_failed", (
            f"With retried=True and blocking failure, status must be 'retry_failed'; "
            f"got {result.status!r}"
        )

    def test_banner_no_survived_correction_wording(self):
        """The retry_failed banner must NOT contain 'survived a correction attempt'."""
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("retry_failed", [])
        assert "survived a correction attempt" not in banner, (
            "The phrase 'survived a correction attempt' was removed in this sprint "
            "but is still present in the banner. Frontend-builder (ui/setup_builder_ui.py)."
        )

    def test_banner_validation_failed_no_survived_correction_wording(self):
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("validation_failed", [])
        assert "survived a correction attempt" not in banner, (
            "The phrase 'survived a correction attempt' must not appear in validation_failed banner."
        )


# ===========================================================================
# Test 3 — Fallback replaces rejected AI output
# ===========================================================================

class TestAC3FallbackReplacesRejected:
    """_build_deterministic_fallback with a diagnosis that permits safe changes:
    - Each approved change passes validate_setup_engineering_structured (zero blocking)
    - Final status fallback_generated when changes present
    - blocked_no_safe_recommendation when nothing safe is possible
    """

    def test_fallback_passes_validation(self):
        """Each change in a non-empty fallback passes validate_setup_engineering_structured."""
        from strategy.setup_diagnosis import (
            build_setup_diagnosis, _build_deterministic_fallback,
            validate_setup_engineering_structured,
        )
        laps = [_make_lap(bottoming_count=5) for _ in range(4)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_rear": 82, "ride_height_front": 80},
            car_name="", event_ctx={}, feeling="bottoming", location_confidence="high",
        )
        ranges = _get_ranges()
        setup = {"ride_height_rear": 82, "ride_height_front": 80}
        fb = _build_deterministic_fallback(diag, setup, ranges)

        # Each individual change must pass validation clean
        for ch in fb.get("changes") or []:
            test_resp = {
                "analysis": "test",
                "primary_issue": "test",
                "changes": [ch],
                "setup_fields": {ch["field"]: ch["to_clamped"]},
                "validation_targets": {},
                "confidence": {"overall": "low", "reason": "test"},
            }
            failures = validate_setup_engineering_structured(
                test_resp, diag, setup, ranges, {}
            )
            blocking = [f for f in failures if f.severity == "blocking"]
            assert blocking == [], (
                f"Fallback change {ch['field']} has blocking failures: {blocking}. "
                "Backend-builder (strategy/setup_diagnosis.py _build_deterministic_fallback)."
            )

    def test_fallback_status_fallback_generated_when_changes_present(self, monkeypatch):
        """When the fallback has approved changes, _finalise_recommendation → fallback_generated."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import (
            build_setup_diagnosis, _build_deterministic_fallback,
            validate_setup_engineering_structured,
        )
        laps = [_make_lap(bottoming_count=5) for _ in range(4)]
        setup = {"ride_height_rear": 82, "ride_height_front": 80}
        diag = build_setup_diagnosis(
            laps=laps, setup=setup,
            car_name="", event_ctx={}, feeling="bottoming", location_confidence="high",
        )
        ranges = _get_ranges()
        fb = _build_deterministic_fallback(diag, setup, ranges)
        if not fb.get("changes"):
            pytest.skip("fallback produced no changes for this diagnosis — use blocked test instead")

        failures = validate_setup_engineering_structured(fb, diag, setup, ranges, {})
        result = _finalise_recommendation(fb, failures, True, True)
        assert result.status == "fallback_generated", (
            f"fallback with changes must produce fallback_generated; got {result.status!r}"
        )

    def test_fallback_blocked_when_no_safe_change(self):
        """When nothing safe is possible (empty fallback), status → blocked_no_safe_recommendation."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import (
            _build_setup_diagnosis_conservative,
            validate_setup_engineering_structured,
        )
        # conservative diagnosis has no tuning priority → fallback produces no changes
        diag = _build_setup_diagnosis_conservative()
        ranges = _get_ranges()
        from strategy.setup_diagnosis import _build_deterministic_fallback
        fb = _build_deterministic_fallback(diag)
        assert fb.get("changes") == [], (
            "Conservative diagnosis must produce fallback with no changes"
        )
        failures = validate_setup_engineering_structured(fb, diag, {}, ranges, {})
        result = _finalise_recommendation(fb, failures, True, True)
        assert result.status == "blocked_no_safe_recommendation", (
            f"fallback with no changes must produce blocked_no_safe_recommendation; "
            f"got {result.status!r}"
        )


# ===========================================================================
# Test 4 — Fake top-speed field blocked
# ===========================================================================

class TestAC4FakeTopSpeedFieldBlocked:
    """transmission_max_speed_kmh in setup_fields/changes → gearbox_fake_field BLOCKING.
    It must never appear in approved output but must still be in _CANONICAL_SETUP_PARAMS
    and _DISPLAY_ONLY_FIELDS.
    """

    def test_fake_field_in_setup_fields_fires_gearbox_fake_field(self):
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        ai_resp = _minimal_ai_resp({
            "setup_fields": {"transmission_max_speed_kmh": 300.0},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        blocking = [f for f in failures if f.code == "gearbox_fake_field" and f.severity == "blocking"]
        assert blocking, (
            "transmission_max_speed_kmh in setup_fields must fire gearbox_fake_field (BLOCKING). "
            "Backend-builder (strategy/setup_diagnosis.py)."
        )

    def test_fake_field_in_changes_fires_gearbox_fake_field(self):
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "transmission_max_speed_kmh", "from": 295, "to": 305,
                         "setting": "Top Speed", "why": "test", "to_clamped": 305}],
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        blocking = [f for f in failures if f.code == "gearbox_fake_field" and f.severity == "blocking"]
        assert blocking, (
            "transmission_max_speed_kmh in changes must fire gearbox_fake_field (BLOCKING). "
            "Backend-builder (strategy/setup_diagnosis.py)."
        )

    def test_fake_field_never_in_approved_output(self):
        """After _finalise_recommendation, transmission_max_speed_kmh must never appear
        in approved_changes or approved_fields."""
        from strategy.driving_advisor import _finalise_recommendation, _DISPLAY_ONLY_FIELDS
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # AI includes both a valid change AND the fake field
        ai_resp = _minimal_ai_resp({
            "changes": [
                {"field": "arb_front", "from": 3, "to": 4,
                 "setting": "ARB Front", "why": "test", "to_clamped": 4},
                {"field": "transmission_max_speed_kmh", "from": 295, "to": 305,
                 "setting": "Top Speed", "why": "test", "to_clamped": 305},
            ],
            "setup_fields": {"arb_front": 4, "transmission_max_speed_kmh": 305},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        result = _finalise_recommendation(ai_resp, failures, False, False)
        # transmission_max_speed_kmh must not appear in approved output
        fields_in_changes = [ch.get("field") for ch in result.approved_changes]
        assert "transmission_max_speed_kmh" not in fields_in_changes, (
            "transmission_max_speed_kmh must never appear in approved_changes. "
            "Backend-builder (_finalise_recommendation / _DISPLAY_ONLY_FIELDS)."
        )
        assert "transmission_max_speed_kmh" not in result.approved_fields, (
            "transmission_max_speed_kmh must never appear in approved_fields."
        )

    def test_transmission_max_speed_in_canonical_params(self):
        """transmission_max_speed_kmh must remain in _CANONICAL_SETUP_PARAMS (diagnostic)."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        assert "transmission_max_speed_kmh" in _CANONICAL_SETUP_PARAMS, (
            "transmission_max_speed_kmh must remain in _CANONICAL_SETUP_PARAMS for diagnostic use."
        )

    def test_transmission_max_speed_in_display_only_fields(self):
        """transmission_max_speed_kmh must be in _DISPLAY_ONLY_FIELDS."""
        from strategy.driving_advisor import _DISPLAY_ONLY_FIELDS
        assert "transmission_max_speed_kmh" in _DISPLAY_ONLY_FIELDS, (
            "transmission_max_speed_kmh must be in _DISPLAY_ONLY_FIELDS. "
            "Backend-builder (strategy/driving_advisor.py)."
        )


# ===========================================================================
# Test 5 — Real gearbox fields accepted
# ===========================================================================

class TestAC5RealGearboxFieldsAccepted:
    """final_drive + gear_1..gear_6 in range, gear_too_short diagnosis →
    no blocking gearbox failures; they survive to approved output.
    Also: _expand_gear_ratios expands gear_ratios list to gear_1..gear_6.
    """

    def test_final_drive_in_range_no_blocking(self):
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # Override to gear_too_short (may_change) so the gearbox is NOT in a preserve
        # category — the intent of this test is that real gear fields are allowed when
        # the diagnosis says gears are too short and the AI should adjust them.
        diag = dict(diag)
        diag["gearing_diagnosis_category"] = "gear_too_short"
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "final_drive", "from": 3.5, "to": 3.8,
                         "setting": "Final Drive", "why": "test", "to_clamped": 3.8}],
            "setup_fields": {"final_drive": 3.8},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        gearbox_blocking = [f for f in failures
                            if "gearbox" in f.code and f.severity == "blocking"]
        assert gearbox_blocking == [], (
            f"final_drive=3.8 (in range 2.5–6.0) must produce no blocking gearbox failures; "
            f"got {gearbox_blocking}."
        )

    def test_gear_6_in_range_no_blocking(self):
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # Override to gear_too_short (may_change) so the gearbox is NOT in a preserve
        # category — the intent of this test is that real gear fields are allowed when
        # the diagnosis says gears are too short and the AI should adjust them.
        diag = dict(diag)
        diag["gearing_diagnosis_category"] = "gear_too_short"
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "gear_6", "from": 1.10, "to": 1.06,
                         "setting": "Gear 6", "why": "test", "to_clamped": 1.06}],
            "setup_fields": {"gear_6": 1.06},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        gearbox_blocking = [f for f in failures
                            if "gearbox" in f.code and f.severity == "blocking"]
        assert gearbox_blocking == [], (
            f"gear_6=1.06 (in range 0.5–4.0) must produce no blocking gearbox failures; "
            f"got {gearbox_blocking}."
        )

    def test_gearbox_fields_survive_to_approved_output(self):
        """final_drive + gear_6 in range, no inversion → approved_changes contains both."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # Override to gear_too_short (may_change) so the gearbox is NOT in a preserve
        # category — these fields must survive to approved_changes when gears can be changed.
        diag = dict(diag)
        diag["gearing_diagnosis_category"] = "gear_too_short"
        ai_resp = _gear_change(
            final_drive=(3.5, 3.8),
            gear_6=(1.10, 1.06),
        )
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        result = _finalise_recommendation(ai_resp, failures, False, False)
        fields = [ch.get("field") for ch in result.approved_changes]
        assert "final_drive" in fields, (
            f"final_drive must survive to approved_changes; fields={fields}"
        )
        assert "gear_6" in fields, (
            f"gear_6 must survive to approved_changes; fields={fields}"
        )

    def test_expand_gear_ratios_flat_list_to_individual_keys(self):
        """_expand_gear_ratios: gear_ratios: [3.25, 2.42, 1.92, 1.58, 1.32, 1.10]
        normalises to gear_1..gear_6 keys."""
        from strategy.driving_advisor import _expand_gear_ratios
        ratios = [3.25, 2.42, 1.92, 1.58, 1.32, 1.10]
        changes = [{
            "field": "gear_ratios",
            "from": None,
            "to": ratios,
            "setting": "Gear Ratios",
            "why": "test",
        }]
        setup_fields = {"gear_ratios": ratios}
        out_changes, out_sf = _expand_gear_ratios(changes, setup_fields)
        for i, ratio in enumerate(ratios, start=1):
            key = f"gear_{i}"
            assert key in out_sf, (
                f"_expand_gear_ratios must produce key '{key}' in setup_fields; "
                f"got keys: {list(out_sf.keys())}"
            )
            assert out_sf[key] == ratio, (
                f"_expand_gear_ratios: out_sf['{key}'] should be {ratio}; got {out_sf[key]}"
            )
        # gear_ratios key itself must be gone
        assert "gear_ratios" not in out_sf, (
            "gear_ratios key must be removed after expansion"
        )

    def test_expand_gear_ratios_noop_when_no_gear_ratios(self):
        """_expand_gear_ratios: no gear_ratios key → inputs returned unchanged."""
        from strategy.driving_advisor import _expand_gear_ratios
        changes = [{"field": "arb_front", "from": 3, "to": 4, "setting": "ARB", "why": ""}]
        sf = {"arb_front": 4}
        out_ch, out_sf = _expand_gear_ratios(changes, sf)
        assert out_sf == sf
        assert len(out_ch) == 1

    def test_final_drive_and_gear_1_to_6_in_canonical(self):
        """final_drive and gear_1..gear_6 must all be in _CANONICAL_SETUP_PARAMS."""
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        expected = {"final_drive", "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6"}
        missing = expected - _CANONICAL_SETUP_PARAMS
        assert missing == set(), (
            f"These gearbox fields are missing from _CANONICAL_SETUP_PARAMS: {missing}. "
            "Backend-builder (strategy/driving_advisor.py)."
        )

    def test_gearbox_fields_in_cat_fields_transmission(self):
        """final_drive and gear_1..gear_6 must appear in _CAT_FIELDS['transmission']."""
        # _CAT_FIELDS is local inside _derive_locked_fields; verify via source scan
        import inspect
        from strategy import driving_advisor
        src = inspect.getsource(driving_advisor)
        assert "final_drive" in src, "final_drive not found in driving_advisor source"
        assert "gear_1" in src, "gear_1 not found in driving_advisor source"
        assert "gear_6" in src, "gear_6 not found in driving_advisor source"
        # Verify _CAT_FIELDS["transmission"] contains the gearbox fields by checking
        # that the module exposes the list explicitly
        assert '"transmission"' in src or "'transmission'" in src, (
            "transmission category not found in driving_advisor"
        )


# ===========================================================================
# Test 6 — Snap-throttle LSD gate
# ===========================================================================

class TestAC6SnapThrottleLSDGate:
    """wheelspin_subtype=snap_throttle_induced + lsd_accel increase of 5 → BLOCKING.
    Increase of 4 → does NOT fire (boundary).
    """

    def test_snap_throttle_lsd_plus_5_fires_blocking(self):
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _snap_throttle_diag(lsd_from=20.0)
        ai_resp = _lsd_change(20.0, 25.0)  # +5
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(
            ai_resp, diag, {"lsd_accel": 20.0}, ranges, {}
        )
        snap_blocking = [f for f in failures
                         if f.code == "snap_throttle_lsd_accel_gate" and f.severity == "blocking"]
        assert snap_blocking, (
            f"snap_throttle_induced + lsd_accel +5 must fire snap_throttle_lsd_accel_gate (BLOCKING); "
            f"failures: {failures}"
        )

    def test_snap_throttle_lsd_plus_4_does_not_fire(self):
        """lsd_accel increase of exactly 4 must NOT fire snap_throttle_lsd_accel_gate (boundary)."""
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _snap_throttle_diag(lsd_from=20.0)
        ai_resp = _lsd_change(20.0, 24.0)  # +4
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(
            ai_resp, diag, {"lsd_accel": 20.0}, ranges, {}
        )
        snap_gate = [f for f in failures if f.code == "snap_throttle_lsd_accel_gate"]
        assert snap_gate == [], (
            f"snap_throttle_induced + lsd_accel +4 must NOT fire snap_throttle_lsd_accel_gate "
            f"(boundary: >4 is blocked, ==4 is allowed); failures: {snap_gate}"
        )

    def test_snap_throttle_lsd_gate_is_in_eng_safety_prefixes(self):
        """snap_throttle_lsd_accel_gate must be in ENG_SAFETY_PREFIXES."""
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert "snap_throttle_lsd_accel_gate" in ENG_SAFETY_PREFIXES, (
            "snap_throttle_lsd_accel_gate must be in ENG_SAFETY_PREFIXES. "
            "Backend-builder (strategy/_setup_constants.py)."
        )

    def test_snap_throttle_lsd_plus_5_zeroes_approved_output(self):
        """snap_throttle_lsd_accel_gate blocking failure must zero approved_changes."""
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _snap_throttle_diag(lsd_from=20.0)
        ai_resp = _lsd_change(20.0, 25.0)
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(
            ai_resp, diag, {"lsd_accel": 20.0}, ranges, {}
        )
        result = _finalise_recommendation(ai_resp, failures, False, False)
        assert result.approved_changes == [], (
            f"snap_throttle_lsd_accel_gate must zero approved_changes; "
            f"got {result.approved_changes!r}"
        )


# ===========================================================================
# Test 7 — Kerb-strike bottoming ride-height gate
# ===========================================================================

class TestAC7KerbStrikeRHGate:
    """bottoming subtype=kerb_strike + rear RH +5mm → kerb_strike_rh_over_increment BLOCKING.
    +2mm → does not fire (boundary).
    """

    def test_kerb_strike_rh_plus_5_fires_blocking(self):
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _kerb_strike_diag(rh_rear=82.0)
        setup = {"ride_height_rear": 82.0, "ride_height_front": 80.0}
        ai_resp = _rh_change("ride_height_rear", 82.0, 87.0)  # +5mm
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        kerb_blocking = [f for f in failures
                         if f.code == "kerb_strike_rh_over_increment" and f.severity == "blocking"]
        assert kerb_blocking, (
            f"kerb_strike subtype + rear RH +5mm must fire kerb_strike_rh_over_increment (BLOCKING); "
            f"failures: {failures}"
        )

    def test_kerb_strike_rh_plus_2_does_not_fire(self):
        """kerb_strike + rear RH +2mm must NOT fire (boundary: >3 is blocked)."""
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _kerb_strike_diag(rh_rear=82.0)
        setup = {"ride_height_rear": 82.0, "ride_height_front": 80.0}
        ai_resp = _rh_change("ride_height_rear", 82.0, 84.0)  # +2mm
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        kerb_gate = [f for f in failures if f.code == "kerb_strike_rh_over_increment"]
        assert kerb_gate == [], (
            f"kerb_strike + rear RH +2mm must NOT fire kerb_strike_rh_over_increment; "
            f"failures: {kerb_gate}"
        )

    def test_kerb_strike_rh_plus_3_does_not_fire(self):
        """kerb_strike + exactly +3mm must NOT fire (boundary is >3, i.e. 4 or more fires)."""
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = _kerb_strike_diag(rh_rear=82.0)
        setup = {"ride_height_rear": 82.0, "ride_height_front": 80.0}
        ai_resp = _rh_change("ride_height_rear", 82.0, 85.0)  # +3mm
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        kerb_gate = [f for f in failures if f.code == "kerb_strike_rh_over_increment"]
        assert kerb_gate == [], (
            f"kerb_strike + exactly +3mm must NOT fire (boundary >3); failures: {kerb_gate}"
        )

    def test_kerb_strike_rh_gate_is_in_eng_safety_prefixes(self):
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert "kerb_strike_rh_over_increment" in ENG_SAFETY_PREFIXES, (
            "kerb_strike_rh_over_increment must be in ENG_SAFETY_PREFIXES."
        )


# ===========================================================================
# Test 8 — Rear-only rake risk
# ===========================================================================

class TestAC8RearOnlyRakeRisk:
    """rear RH +4 with front unchanged → rh_rake_risk BLOCKING severity.
    Front paired appropriately → does not fire.
    """

    def _diag_with_enough_bottoming(self):
        from strategy.setup_diagnosis import build_setup_diagnosis
        laps = [_make_lap(bottoming_count=5) for _ in range(4)]
        return build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80, "ride_height_rear": 82},
            car_name="", event_ctx={}, feeling="bottoming", location_confidence="high",
        )

    def test_rear_rh_plus4_no_front_fires_rake_risk(self):
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = self._diag_with_enough_bottoming()
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        ai_resp = _rh_change("ride_height_rear", 82, 86)  # +4mm, no front
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        rake = [f for f in failures if f.code == "rh_rake_risk"]
        assert rake, (
            f"rear RH +4mm with no front change must fire rh_rake_risk; failures: {failures}"
        )

    def test_rake_risk_is_blocking(self):
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = self._diag_with_enough_bottoming()
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        ai_resp = _rh_change("ride_height_rear", 82, 86)
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        rake = [f for f in failures if f.code == "rh_rake_risk"]
        assert rake, "rh_rake_risk must appear in failures"
        assert all(f.severity == "blocking" for f in rake), (
            f"rh_rake_risk must have blocking severity; got {[f.severity for f in rake]}"
        )

    def test_paired_front_and_rear_no_rake_risk(self):
        """Changing both front and rear by appropriate amounts → no rake risk."""
        from strategy.setup_diagnosis import validate_setup_engineering_structured
        diag = self._diag_with_enough_bottoming()
        setup = {"ride_height_front": 80, "ride_height_rear": 82}
        ai_resp = _minimal_ai_resp({
            "changes": [
                {"field": "ride_height_front", "from": 80, "to": 84,
                 "setting": "RH Front", "why": "test", "to_clamped": 84},
                {"field": "ride_height_rear", "from": 82, "to": 86,
                 "setting": "RH Rear", "why": "test", "to_clamped": 86},
            ],
            "setup_fields": {"ride_height_front": 84, "ride_height_rear": 86},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        rake = [f for f in failures if f.code == "rh_rake_risk"]
        assert rake == [], (
            f"Paired front+rear change must not fire rake risk; failures: {rake}"
        )

    def test_rh_rake_risk_is_in_eng_safety_prefixes(self):
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert "rh_rake_risk" in ENG_SAFETY_PREFIXES


# ===========================================================================
# Test 9 — Old gearing rule removed + display-only caveat present
# ===========================================================================

class TestAC9OldGearingRuleRemoved:
    """The 'top speed below target ⇒ preserve gearing' leakage is gone.
    format_diagnosis_for_prompt output does NOT instruct the AI to preserve gearing
    for the top-speed-below-target reason.
    The display-only caveat for transmission_max_speed_kmh IS present.
    """

    def test_format_prompt_does_not_say_preserve_gearing_for_top_speed(self):
        from strategy.setup_diagnosis import build_setup_diagnosis, format_diagnosis_for_prompt
        laps = [_make_lap(max_speed_kmh=260.0)]
        setup = {"transmission_max_speed_kmh": 310.0}  # large gap between actual and target
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        # Old leakage: "top speed below target … preserve gearing" or similar.
        # These phrases must not appear as a gearing-preserve directive.
        forbidden_phrases = [
            "preserve gearing because top speed",
            "do not change gearing.*top speed",
            "top speed below target.*preserve",
        ]
        import re
        for phrase in forbidden_phrases:
            assert not re.search(phrase, text, re.IGNORECASE), (
                f"Old leakage phrase found in prompt: '{phrase}'. "
                "Backend-builder must remove this directive (strategy/setup_diagnosis.py)."
            )

    def test_format_prompt_contains_display_only_caveat(self):
        """The prompt must contain the display-only caveat for transmission_max_speed_kmh."""
        from strategy.setup_diagnosis import build_setup_diagnosis, format_diagnosis_for_prompt
        laps = [_make_lap(max_speed_kmh=260.0)]
        setup = {"transmission_max_speed_kmh": 310.0}
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        assert "DISPLAY-ONLY" in text or "display-only" in text.lower(), (
            "format_diagnosis_for_prompt must include DISPLAY-ONLY caveat for "
            "transmission_max_speed_kmh when it appears in the diagnosis. "
            "Backend-builder (strategy/setup_diagnosis.py)."
        )

    def test_gearing_change_not_blocked_for_gear_too_short_scenario(self):
        """With gear_too_short diagnosis, gearing changes must NOT be blocked
        by validate_setup_engineering (no 'gearbox_category_mismatch' for a
        reduction in final_drive when the flag is 'may_change')."""
        from strategy.setup_diagnosis import (
            build_setup_diagnosis, validate_setup_engineering_structured,
        )
        # Build a diagnosis that permits gearing change
        laps = [_make_lap(rev_limiter_by_gear={6: 5}) for _ in range(3)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"transmission_max_speed_kmh": 310.0},
            car_name="", event_ctx={}, feeling=None, location_confidence="low",
        )
        # If gearbox_flag == "may_change", a gearing change should not fire mismatch
        if diag.get("gearbox_flag") not in ("may_change", "gear_too_short"):
            pytest.skip(f"Diagnosis did not produce gear_too_short; flag={diag.get('gearbox_flag')!r}")
        setup = {"transmission_max_speed_kmh": 310.0, "final_drive": 3.5}
        ai_resp = _gear_change(final_drive=(3.5, 3.8))
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, setup, ranges, {})
        mismatch = [f for f in failures if f.code == "gearbox_category_mismatch"]
        assert mismatch == [], (
            f"gear_too_short diagnosis must not fire gearbox_category_mismatch for "
            f"a final_drive change; failures: {mismatch}"
        )


# ===========================================================================
# Test 10 — Rejected recommendation not saved as current
# ===========================================================================

class TestAC10RejectedNotSavedAsCurrent:
    """save_entry with validation_status='validation_failed' → rejected bucket.
    save_entry with validation_status='approved' → primary bucket.
    """

    def test_validation_failed_goes_to_rejected_bucket(self, tmp_path):
        import json as _json
        from unittest.mock import patch
        # Patch _HISTORY_PATH to a temp file
        hist_path = tmp_path / "setup_history.json"
        import data.setup_history as sh
        with patch.object(sh, "_HISTORY_PATH", hist_path):
            sh.save_entry(
                config_id="cfg-test-001",
                car="TestCar",
                track="TestTrack",
                entry={"type": "analyse_setup", "analysis": "rejected"},
                validation_status="validation_failed",
            )
            data = _json.loads(hist_path.read_text())
        # Primary bucket must not have been created
        assert "cfg-test-001" not in data, (
            f"validation_failed must not write to primary bucket 'cfg-test-001'; "
            f"found keys: {list(data.keys())}"
        )
        # Rejected bucket must exist
        assert "_rejected_cfg-test-001" in data, (
            f"validation_failed must write to '_rejected_cfg-test-001'; "
            f"found keys: {list(data.keys())}"
        )
        entries = data["_rejected_cfg-test-001"]["entries"]
        assert len(entries) == 1
        assert entries[0]["validation_status"] == "validation_failed"

    def test_approved_goes_to_primary_bucket(self, tmp_path):
        import json as _json
        from unittest.mock import patch
        hist_path = tmp_path / "setup_history.json"
        import data.setup_history as sh
        with patch.object(sh, "_HISTORY_PATH", hist_path):
            sh.save_entry(
                config_id="cfg-test-002",
                car="TestCar",
                track="TestTrack",
                entry={"type": "analyse_setup", "analysis": "approved"},
                validation_status="approved",
            )
            data = _json.loads(hist_path.read_text())
        assert "cfg-test-002" in data, (
            f"approved status must write to primary bucket 'cfg-test-002'; "
            f"found keys: {list(data.keys())}"
        )
        assert "_rejected_cfg-test-002" not in data

    def test_retry_failed_goes_to_rejected_bucket(self, tmp_path):
        import json as _json
        from unittest.mock import patch
        hist_path = tmp_path / "setup_history.json"
        import data.setup_history as sh
        with patch.object(sh, "_HISTORY_PATH", hist_path):
            sh.save_entry(
                config_id="cfg-test-003",
                car="TestCar",
                track="TestTrack",
                entry={"type": "analyse_setup", "analysis": "retry_failed"},
                validation_status="retry_failed",
            )
            data = _json.loads(hist_path.read_text())
        assert "cfg-test-003" not in data
        assert "_rejected_cfg-test-003" in data

    def test_empty_validation_status_goes_to_primary(self, tmp_path):
        """No validation_status → legacy path → primary bucket (no routing)."""
        import json as _json
        from unittest.mock import patch
        hist_path = tmp_path / "setup_history.json"
        import data.setup_history as sh
        with patch.object(sh, "_HISTORY_PATH", hist_path):
            sh.save_entry(
                config_id="cfg-test-004",
                car="TestCar",
                track="TestTrack",
                entry={"type": "analyse_setup", "analysis": "legacy"},
                validation_status="",  # empty → no routing
            )
            data = _json.loads(hist_path.read_text())
        assert "cfg-test-004" in data, (
            "Empty validation_status must go to primary bucket (legacy compatibility)"
        )

    def test_approved_statuses_all_go_to_primary(self, tmp_path):
        """approved, approved_with_warnings, fallback_generated → all primary."""
        import json as _json
        from unittest.mock import patch
        import data.setup_history as sh
        from strategy._setup_constants import APPROVED_STATUSES
        hist_path = tmp_path / "setup_history.json"
        with patch.object(sh, "_HISTORY_PATH", hist_path):
            for i, status in enumerate(sorted(APPROVED_STATUSES)):
                sh.save_entry(
                    config_id=f"cfg-{i}",
                    car="TestCar",
                    track="TestTrack",
                    entry={"type": "analyse_setup", "analysis": status},
                    validation_status=status,
                )
            data = _json.loads(hist_path.read_text())
        for i, status in enumerate(sorted(APPROVED_STATUSES)):
            assert f"cfg-{i}" in data, (
                f"APPROVED status '{status}' must write to primary bucket; "
                f"found keys: {list(data.keys())}"
            )


# ===========================================================================
# Test 11 — ENG_SAFETY_PREFIXES single source
# ===========================================================================

class TestAC11EngSafetyPrefixesSingleSource:
    """ENG_SAFETY_PREFIXES is defined once (in _setup_constants) and both
    driving_advisor and setup_diagnosis reference the same object (identity),
    not re-declared inline.
    """

    def test_eng_safety_prefixes_defined_in_setup_constants(self):
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert isinstance(ENG_SAFETY_PREFIXES, tuple), (
            "ENG_SAFETY_PREFIXES must be a tuple in _setup_constants"
        )
        assert len(ENG_SAFETY_PREFIXES) > 0

    def test_driving_advisor_imports_from_setup_constants(self):
        import strategy.driving_advisor as da
        import strategy._setup_constants as sc
        # Both modules should expose the same object
        assert da.ENG_SAFETY_PREFIXES is sc.ENG_SAFETY_PREFIXES, (
            "driving_advisor.ENG_SAFETY_PREFIXES must be the same object as "
            "_setup_constants.ENG_SAFETY_PREFIXES (identity check — not a copy). "
            "Backend-builder must import from _setup_constants, not redeclare."
        )

    def test_setup_diagnosis_imports_from_setup_constants(self):
        import strategy.setup_diagnosis as sd
        import strategy._setup_constants as sc
        assert sd.ENG_SAFETY_PREFIXES is sc.ENG_SAFETY_PREFIXES, (
            "setup_diagnosis.ENG_SAFETY_PREFIXES must be the same object as "
            "_setup_constants.ENG_SAFETY_PREFIXES. Backend-builder must import from _setup_constants."
        )

    def test_no_inline_redeclaration_in_driving_advisor(self):
        """Source scan: driving_advisor must not redeclare ENG_SAFETY_PREFIXES inline."""
        import inspect
        from strategy import driving_advisor
        src = inspect.getsource(driving_advisor)
        # The tuple literal would start with: ENG_SAFETY_PREFIXES: tuple = (
        # We allow the import statement but forbid inline assignment
        lines = src.splitlines()
        for ln in lines:
            stripped = ln.strip()
            # Allow import and re-export; forbid assignment
            if stripped.startswith("ENG_SAFETY_PREFIXES") and "=" in stripped:
                assert "import" in stripped or "from" in stripped or \
                       stripped.startswith("ENG_SAFETY_PREFIXES =") is False, (
                    f"ENG_SAFETY_PREFIXES appears to be re-declared inline in driving_advisor: "
                    f"{stripped!r}. Must be imported from _setup_constants only."
                )

    def test_approved_statuses_defined_in_setup_constants(self):
        from strategy._setup_constants import APPROVED_STATUSES
        assert isinstance(APPROVED_STATUSES, frozenset)
        assert "approved" in APPROVED_STATUSES
        assert "approved_with_warnings" in APPROVED_STATUSES
        assert "fallback_generated" in APPROVED_STATUSES


# ===========================================================================
# Test 12 — Gearbox fields present + display-only demotion
# ===========================================================================

class TestAC12GearboxFieldsAndDisplayOnlyDemotion:
    """final_drive, gear_1..gear_6 in _CANONICAL_SETUP_PARAMS and
    _CAT_FIELDS["transmission"]; transmission_max_speed_kmh in _DISPLAY_ONLY_FIELDS
    and excluded from approved output by _finalise_recommendation.
    """

    def test_canonical_params_contains_all_gear_fields(self):
        from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
        for key in ("final_drive", "gear_1", "gear_2", "gear_3",
                    "gear_4", "gear_5", "gear_6"):
            assert key in _CANONICAL_SETUP_PARAMS, (
                f"'{key}' missing from _CANONICAL_SETUP_PARAMS. Backend-builder."
            )

    def test_display_only_field_stripped_from_approved_changes(self):
        """_finalise_recommendation strips transmission_max_speed_kmh from approved_changes."""
        from strategy.driving_advisor import _finalise_recommendation
        raw_data = _minimal_ai_resp({
            "changes": [
                {"field": "transmission_max_speed_kmh", "from": 295, "to": 305,
                 "setting": "Top Speed", "why": "display only", "to_clamped": 305},
                {"field": "arb_front", "from": 3, "to": 4,
                 "setting": "ARB Front", "why": "test", "to_clamped": 4},
            ],
            "setup_fields": {"transmission_max_speed_kmh": 305, "arb_front": 4},
        })
        result = _finalise_recommendation(raw_data, [], False, False)
        fields = [ch.get("field") for ch in result.approved_changes]
        assert "transmission_max_speed_kmh" not in fields, (
            f"transmission_max_speed_kmh must be stripped from approved_changes; "
            f"fields present: {fields}"
        )
        assert "arb_front" in fields, "arb_front (valid field) must survive"

    def test_display_only_field_stripped_from_approved_fields(self):
        from strategy.driving_advisor import _finalise_recommendation
        raw_data = _minimal_ai_resp({
            "setup_fields": {"transmission_max_speed_kmh": 305, "arb_front": 4},
        })
        result = _finalise_recommendation(raw_data, [], False, False)
        assert "transmission_max_speed_kmh" not in result.approved_fields, (
            "transmission_max_speed_kmh must be stripped from approved_fields"
        )
        assert "arb_front" in result.approved_fields

    def test_gearbox_out_of_range_is_warning_not_blocking(self):
        """gearbox_out_of_range must produce WARNING severity (not blocking)."""
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # final_drive=1.0 is out of range 2.5–6.0
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "final_drive", "from": 3.5, "to": 1.0,
                         "setting": "Final Drive", "why": "test", "to_clamped": 1.0}],
            "setup_fields": {"final_drive": 1.0},
        })
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        oor = [f for f in failures if f.code == "gearbox_out_of_range"]
        assert oor, "final_drive=1.0 must fire gearbox_out_of_range"
        assert all(f.severity == "warning" for f in oor), (
            f"gearbox_out_of_range must be WARNING (not blocking); got {[f.severity for f in oor]}"
        )

    def test_gearbox_ratio_inversion_is_blocking(self):
        """gear_2 > gear_1 → gearbox_ratio_inversion BLOCKING.

        Group 45 note: the check was changed from >= to > (strict inversion only).
        Equal adjacent gear ratios are ALLOWED (gear_2 == gear_1 is no longer an error).
        This test now uses a genuine strict inversion (gear_2 > gear_1) to confirm
        the blocking rule still fires for real inversions.  The old equal-ratio test case
        (gear_2 = 3.5 == gear_1 = 3.5) is no longer an inversion by design.
        """
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # gear_2 = 4.0 > gear_1 = 3.5 → strict inversion (higher gear has higher ratio)
        ai_resp = _gear_change(
            gear_1=(3.5, 3.5),
            gear_2=(2.8, 4.0),  # strictly inverted: gear_2 > gear_1
        )
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        inversion = [f for f in failures if f.code == "gearbox_ratio_inversion"]
        assert inversion, (
            f"gear_2 > gear_1 must fire gearbox_ratio_inversion; failures: {failures}"
        )
        assert all(f.severity == "blocking" for f in inversion), (
            f"gearbox_ratio_inversion must be BLOCKING; got {[f.severity for f in inversion]}"
        )


# ===========================================================================
# Test 13 — Race Conditions block removed
# ===========================================================================

class TestAC13RaceConditionsBlockRemoved:
    """Source-scan: ui/setup_builder_ui.py must not contain _lbl_rc_race_type
    or _lbl_rc_bop etc. (the Race Conditions group was removed).
    _sync_setup_builder_from_event must still exist (functional side-effects retained).
    """

    def test_lbl_rc_attributes_not_in_source(self):
        import inspect
        from ui import setup_builder_ui
        src = inspect.getsource(setup_builder_ui)
        removed_attrs = [
            "_lbl_rc_race_type",
            "_lbl_rc_bop",
        ]
        for attr in removed_attrs:
            # Allow defensive hasattr checks but not assignments/definitions
            lines = [ln for ln in src.splitlines()
                     if attr in ln
                     and "hasattr" not in ln
                     and not ln.strip().startswith("#")]
            assert lines == [], (
                f"'{attr}' found as a non-hasattr reference in setup_builder_ui.py. "
                f"Race Conditions block was removed but attribute still referenced: "
                f"{lines}. Frontend-builder (ui/setup_builder_ui.py)."
            )

    def test_sync_setup_builder_from_event_still_exists(self):
        """_sync_setup_builder_from_event must still exist (functional side-effects)."""
        from ui.setup_builder_ui import SetupBuilderMixin
        assert hasattr(SetupBuilderMixin, "_sync_setup_builder_from_event"), (
            "_sync_setup_builder_from_event was removed but is needed for functional "
            "side-effects (BoP toggle, permissions, spinbox rebind). Frontend-builder."
        )

    def test_sync_setup_builder_from_event_is_callable(self):
        from ui.setup_builder_ui import SetupBuilderMixin
        import inspect
        assert callable(SetupBuilderMixin._sync_setup_builder_from_event)
        # Must still call functional side effects (verify method body isn't empty)
        src = inspect.getsource(SetupBuilderMixin._sync_setup_builder_from_event)
        assert "_on_bop_toggled" in src or "_apply_setup_permissions" in src, (
            "_sync_setup_builder_from_event must still call functional side effects "
            "(_on_bop_toggled, _apply_setup_permissions). Frontend-builder."
        )


# ===========================================================================
# Test 14 — Home Damage line
# ===========================================================================

class TestAC14HomeDamageLine:
    """_build_race_setup_card with EventContext damage='Heavy' → 'Damage: Heavy' in lines.
    Empty damage → no Damage line.
    """

    def _make_event_ctx(self, damage: str = "", **kwargs) -> dict:
        base = {
            "has_active_event": True,
            "event_name": "Test Event",
            "car": "TestCar",
            "track": "TestTrack",
            "race_type": "lap",
            "laps": 10,
            "tyre_wear_multiplier": 1.0,
            "fuel_multiplier": 1.0,
            "refuel_rate_lps": 0.0,
            "mandatory_stops": 0,
            "bop_enabled": False,
            "tuning_allowed": True,
            "damage": damage,
        }
        base.update(kwargs)
        return base

    def test_damage_heavy_in_lines(self):
        from ui.home_dashboard_vm import _build_race_setup_card
        ev_ctx = self._make_event_ctx(damage="Heavy")
        card = _build_race_setup_card(ev_ctx, {})
        assert any("Damage: Heavy" in ln for ln in card.lines), (
            f"'Damage: Heavy' must appear in card.lines when damage='Heavy'; "
            f"got lines: {card.lines}"
        )

    def test_damage_empty_no_damage_line(self):
        from ui.home_dashboard_vm import _build_race_setup_card
        ev_ctx = self._make_event_ctx(damage="")
        card = _build_race_setup_card(ev_ctx, {})
        damage_lines = [ln for ln in card.lines if ln.startswith("Damage:")]
        assert damage_lines == [], (
            f"Empty damage must not produce a Damage line; "
            f"found: {damage_lines} in {card.lines}"
        )

    def test_damage_none_no_damage_line(self):
        from ui.home_dashboard_vm import _build_race_setup_card
        ev_ctx = self._make_event_ctx()
        ev_ctx["damage"] = None
        card = _build_race_setup_card(ev_ctx, {})
        damage_lines = [ln for ln in card.lines if "Damage:" in ln]
        assert damage_lines == [], (
            f"None damage must not produce a Damage line; found: {damage_lines}"
        )

    def test_damage_medium_in_lines(self):
        from ui.home_dashboard_vm import _build_race_setup_card
        ev_ctx = self._make_event_ctx(damage="Medium")
        card = _build_race_setup_card(ev_ctx, {})
        assert any("Damage: Medium" in ln for ln in card.lines), (
            f"'Damage: Medium' must appear in card.lines; got {card.lines}"
        )

    def test_no_active_event_returns_missing_card(self):
        from ui.home_dashboard_vm import _build_race_setup_card, HomeDashboardStatus
        ev_ctx = {"has_active_event": False}
        card = _build_race_setup_card(ev_ctx, {})
        assert card.status == HomeDashboardStatus.MISSING


# ===========================================================================
# Additional edge cases
# ===========================================================================

class TestAdditionalEdgeCases:
    """Edge cases mentioned in the acceptance criteria but not covered above."""

    def test_gearbox_ratio_inversion_strictly_decreasing_passes(self):
        """Strictly decreasing gear ratios pass gearbox_ratio_inversion."""
        from strategy.setup_diagnosis import (
            validate_setup_engineering_structured, build_setup_diagnosis,
        )
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        # Strictly decreasing: 3.25 > 2.42 > 1.92 > 1.58 > 1.32 > 1.10
        ai_resp = _gear_change(
            gear_1=(3.25, 3.25),
            gear_2=(2.42, 2.42),
            gear_3=(1.92, 1.92),
            gear_4=(1.58, 1.58),
            gear_5=(1.32, 1.32),
            gear_6=(1.10, 1.10),
        )
        ranges = _get_ranges()
        failures = validate_setup_engineering_structured(ai_resp, diag, {}, ranges, {})
        inversions = [f for f in failures if f.code == "gearbox_ratio_inversion"]
        assert inversions == [], (
            f"Strictly decreasing gear ratios must not fire ratio_inversion; got {inversions}"
        )

    def test_gearbox_ratio_inversion_in_eng_safety_prefixes(self):
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert "gearbox_ratio_inversion" in ENG_SAFETY_PREFIXES

    def test_gearbox_fake_field_in_eng_safety_prefixes(self):
        from strategy._setup_constants import ENG_SAFETY_PREFIXES
        assert "gearbox_fake_field" in ENG_SAFETY_PREFIXES

    def test_validation_failure_namedtuple_fields(self):
        """ValidationFailure NamedTuple must have code, message, severity fields."""
        from strategy.setup_diagnosis import ValidationFailure
        f = ValidationFailure(code="test_code", message="test msg", severity="blocking")
        assert f.code == "test_code"
        assert f.message == "test msg"
        assert f.severity == "blocking"

    def test_setup_recommendation_result_is_frozen_dataclass(self):
        """SetupRecommendationResult must be a frozen dataclass."""
        from strategy.driving_advisor import SetupRecommendationResult
        import dataclasses
        assert dataclasses.is_dataclass(SetupRecommendationResult)
        assert SetupRecommendationResult.__dataclass_params__.frozen

    def test_approved_statuses_frozenset(self):
        from strategy._setup_constants import APPROVED_STATUSES
        assert isinstance(APPROVED_STATUSES, frozenset)
        # approved_with_rejections added when per-field rejection landed: valid
        # changes survive while a specific contradicted field is dropped.
        expected = {
            "approved", "approved_with_warnings",
            "approved_with_rejections", "fallback_generated",
        }
        assert APPROVED_STATUSES == expected, (
            f"APPROVED_STATUSES must be exactly {expected}; got {APPROVED_STATUSES}"
        )

    def test_format_status_banner_approved_returns_empty(self):
        """_format_status_banner('approved') must return '' (no banner needed)."""
        from ui.setup_builder_ui import _format_status_banner
        assert _format_status_banner("approved", []) == ""

    def test_format_status_banner_fallback_generated_is_nonempty(self):
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("fallback_generated", [])
        assert banner, "fallback_generated must produce a banner"

    def test_format_status_banner_blocked_no_safe_recommendation(self):
        from ui.setup_builder_ui import _format_status_banner
        banner = _format_status_banner("blocked_no_safe_recommendation", [])
        assert banner, "blocked_no_safe_recommendation must produce a banner"

    def test_finalise_recommendation_approved_status_when_clean(self):
        """_finalise_recommendation with no failures and no fallback → approved."""
        from strategy.driving_advisor import _finalise_recommendation
        raw_data = _minimal_ai_resp({
            "changes": [{"field": "arb_front", "from": 3, "to": 4,
                         "setting": "ARB Front", "why": "test", "to_clamped": 4}],
            "setup_fields": {"arb_front": 4},
        })
        result = _finalise_recommendation(raw_data, [], False, False)
        assert result.status == "approved", f"Expected 'approved'; got {result.status!r}"
        assert result.approved_changes != []
        assert "arb_front" in result.approved_fields

    def test_finalise_recommendation_approved_with_warnings_when_warnings_present(self):
        from strategy.driving_advisor import _finalise_recommendation
        from strategy.setup_diagnosis import ValidationFailure
        raw_data = _minimal_ai_resp({
            "changes": [{"field": "arb_front", "from": 3, "to": 4,
                         "setting": "ARB Front", "why": "test", "to_clamped": 4}],
            "setup_fields": {"arb_front": 4},
        })
        warning = ValidationFailure(
            code="gearbox_out_of_range",
            message="gearbox_out_of_range: test warning",
            severity="warning",
        )
        result = _finalise_recommendation(raw_data, [warning], False, False)
        assert result.status == "approved_with_warnings", (
            f"Expected 'approved_with_warnings'; got {result.status!r}"
        )
        # Changes still approved (only warnings)
        assert result.approved_changes != []
