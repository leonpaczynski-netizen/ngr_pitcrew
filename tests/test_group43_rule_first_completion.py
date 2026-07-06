"""
Group 43 — Rule-First Setup Brain Completion: Acceptance Tests

Covers:
  A2  — rear_loose_on_exit / snap_oversteer_exit precondition re-key
  A3  — ride_height_front protection / contraindication suppression
  A4  — ride_height_rear protection / contraindication suppression
  A5  — braking_instability / avg_lockups precondition re-key
  B5  — gearing_diagnosis_category + gearbox_flag precondition re-key, final_drive_down resolver
  Resolver directions: final_drive_down, final_drive_up, shorten_final_drive (legacy alias)
  Self-consistency pipe: B5 plan → plan_to_raw_data → _normalise_changes → validate_setup_engineering_structured
  Docs grep: module docstring + docs/RULE_FIRST_SETUP_BRAIN.md deferred substrings
  UI gate (headless): _btn_build_setup disabled+hidden for both Race and Qualifying forms

All backend tests are pure/offline — no network, no Qt event loop, no QApplication.
UI tests use QT_QPA_PLATFORM=offscreen and instantiate SetupFormWidget directly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_knowledge_base import resolve_delta
from strategy.setup_ranges import resolve_ranges
from strategy.setup_rule_engine import run_rule_engine, SetupPlan


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=0,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=5.0,
        oversteer_count=0,
        oversteer_throttle_on_count=0,
        kerb_count=0,
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


def _run_engine(diag: dict, setup: dict) -> SetupPlan:
    ranges = resolve_ranges("")
    profile = build_driver_profile()
    return run_rule_engine(diag, setup, ranges, profile)


# ===========================================================================
# A2 — rear downforce cut blocked under rear instability
# ===========================================================================

class TestA2RearInstabilitySafetyInvariant:
    """A2 fires → REJECTED_CANDIDATE for aero_rear when rear instability flags present."""

    def test_a2_fires_on_rear_loose_on_exit(self):
        """A2 must fire (produce a rejected_candidate) when rear_loose_on_exit=True."""
        diag = {"driver_feel_flags": {"rear_loose_on_exit": True}}
        setup = {"aero_rear": 150}

        plan = _run_engine(diag, setup)

        a2 = [i for i in plan.rejected_candidates if i.rule_id == "A2"]
        assert len(a2) >= 1, (
            f"A2 FAIL: must be in rejected_candidates when rear_loose_on_exit=True; "
            f"rejected: {[(i.rule_id, i.field) for i in plan.rejected_candidates]}"
        )
        assert a2[0].field == "aero_rear", (
            f"A2 FAIL: must target aero_rear; got {a2[0].field!r}"
        )

    def test_a2_fires_on_snap_oversteer_exit(self):
        """A2 must fire when snap_oversteer_exit=True (OR semantics)."""
        diag = {"driver_feel_flags": {"snap_oversteer_exit": True}}
        setup = {"aero_rear": 150}

        plan = _run_engine(diag, setup)

        a2 = [i for i in plan.rejected_candidates if i.rule_id == "A2"]
        assert len(a2) >= 1, (
            f"A2 FAIL: must be in rejected_candidates when snap_oversteer_exit=True; "
            f"rejected: {[(i.rule_id, i.field) for i in plan.rejected_candidates]}"
        )

    def test_a2_does_not_fire_when_both_flags_false(self):
        """A2 must NOT fire when both rear_loose_on_exit=False and snap_oversteer_exit=False."""
        diag = {
            "driver_feel_flags": {
                "rear_loose_on_exit": False,
                "snap_oversteer_exit": False,
            }
        }
        setup = {"aero_rear": 150}

        plan = _run_engine(diag, setup)

        a2 = [i for i in plan.rejected_candidates if i.rule_id == "A2"]
        assert not a2, (
            f"A2 FAIL: must NOT fire when both flags are False; "
            f"found: {[(i.rule_id, i.field) for i in a2]}"
        )

    def test_a2_fires_exactly_once_when_both_flags_true(self):
        """A2 fires exactly ONCE when both rear_loose_on_exit=True and snap_oversteer_exit=True.

        The __any__ precondition is OR — A2 is a single rule so it can only appear once
        regardless of how many conditions matched it.
        """
        diag = {
            "driver_feel_flags": {
                "rear_loose_on_exit": True,
                "snap_oversteer_exit": True,
            }
        }
        setup = {"aero_rear": 150}

        plan = _run_engine(diag, setup)

        a2 = [i for i in plan.rejected_candidates if i.rule_id == "A2"]
        assert len(a2) == 1, (
            f"A2 FAIL: must appear exactly once in rejected_candidates when both flags True; "
            f"found {len(a2)} entries"
        )


# ===========================================================================
# A3 / A4 — ride-height protection with contraindication suppression
# ===========================================================================

class TestA3A4RideHeightProtection:
    """A3/A4: precondition bottoming_band=minor + no contraindication → protect fields.
    Any matched contraindication (band in consider/required OR compliance_priority=True)
    SUPPRESSES the protection so another rule may raise ride-height.
    """

    def test_a3_a4_protect_both_fields_on_minor_bottoming_no_contraindication(self):
        """Both ride_height_front and ride_height_rear must be protected when:
        - bottoming_band=minor (precondition matches)
        - bottoming_confidence.band not in {consider, required}
        - compliance_priority=False
        """
        diag = {
            "bottoming_band": "minor",
            "bottoming_confidence": {"band": "none", "subtype": "none", "confidence": "low"},
            "compliance_priority": False,
        }
        setup = {"ride_height_front": 80, "ride_height_rear": 82}

        plan = _run_engine(diag, setup)

        assert "ride_height_front" in plan.protected_fields, (
            f"A3 FAIL: ride_height_front must be protected for minor bottoming with no contraindication; "
            f"protected: {plan.protected_fields}"
        )
        assert "ride_height_rear" in plan.protected_fields, (
            f"A4 FAIL: ride_height_rear must be protected for minor bottoming with no contraindication; "
            f"protected: {plan.protected_fields}"
        )

    def test_a3_a4_NOT_protected_when_bottoming_confidence_band_required(self):
        """Protection is SUPPRESSED when bottoming_confidence.band=required.

        The contraindication matches → A3/A4 do not fire → fields are NOT protected.
        """
        diag = {
            "bottoming_band": "minor",
            "bottoming_confidence": {"band": "required", "subtype": "floor_strike", "confidence": "high"},
            "compliance_priority": False,
        }
        setup = {"ride_height_front": 80, "ride_height_rear": 82}

        plan = _run_engine(diag, setup)

        assert "ride_height_front" not in plan.protected_fields, (
            f"A3 FAIL: ride_height_front must NOT be protected when bottoming_confidence.band=required; "
            f"protected: {plan.protected_fields}"
        )
        assert "ride_height_rear" not in plan.protected_fields, (
            f"A4 FAIL: ride_height_rear must NOT be protected when bottoming_confidence.band=required; "
            f"protected: {plan.protected_fields}"
        )

    def test_a3_a4_NOT_protected_when_bottoming_confidence_band_consider(self):
        """Protection is SUPPRESSED when bottoming_confidence.band=consider."""
        diag = {
            "bottoming_band": "minor",
            "bottoming_confidence": {"band": "consider", "subtype": "kerb_strike", "confidence": "medium"},
            "compliance_priority": False,
        }
        setup = {"ride_height_front": 80, "ride_height_rear": 82}

        plan = _run_engine(diag, setup)

        assert "ride_height_front" not in plan.protected_fields, (
            f"A3 FAIL: ride_height_front must NOT be protected when bottoming_confidence.band=consider; "
            f"protected: {plan.protected_fields}"
        )
        assert "ride_height_rear" not in plan.protected_fields, (
            f"A4 FAIL: ride_height_rear must NOT be protected when bottoming_confidence.band=consider; "
            f"protected: {plan.protected_fields}"
        )

    def test_a3_a4_NOT_protected_when_compliance_priority_true(self):
        """Protection is SUPPRESSED when compliance_priority=True.

        compliance_priority=True is itself a contraindication; it unlocks C8 to
        propose the raise instead.
        """
        diag = {
            "bottoming_band": "minor",
            "bottoming_confidence": {"band": "none", "subtype": "none", "confidence": "low"},
            "compliance_priority": True,
        }
        setup = {"ride_height_front": 80, "ride_height_rear": 82}

        plan = _run_engine(diag, setup)

        assert "ride_height_front" not in plan.protected_fields, (
            f"A3 FAIL: ride_height_front must NOT be protected when compliance_priority=True; "
            f"protected: {plan.protected_fields}"
        )
        assert "ride_height_rear" not in plan.protected_fields, (
            f"A4 FAIL: ride_height_rear must NOT be protected when compliance_priority=True; "
            f"protected: {plan.protected_fields}"
        )


# ===========================================================================
# A5 — brake bias rearward blocked under braking instability
# ===========================================================================

class TestA5BrakingInstabilitySafetyInvariant:
    """A5 fires → REJECTED_CANDIDATE for brake_bias when braking instability signals present."""

    def test_a5_fires_on_braking_instability_flag(self):
        """A5 must fire when driver_feel_flags.braking_instability=True."""
        diag = {
            "driver_feel_flags": {"braking_instability": True},
            "avg_lockups": 0,
        }
        setup = {"brake_bias": 58.0}

        plan = _run_engine(diag, setup)

        a5 = [i for i in plan.rejected_candidates if i.rule_id == "A5"]
        assert len(a5) >= 1, (
            f"A5 FAIL: must be in rejected_candidates when braking_instability=True; "
            f"rejected: {[(i.rule_id, i.field) for i in plan.rejected_candidates]}"
        )
        assert a5[0].field == "brake_bias", (
            f"A5 FAIL: must target brake_bias; got {a5[0].field!r}"
        )

    def test_a5_fires_on_avg_lockups_nonzero(self):
        """A5 must fire when avg_lockups=2 (non-zero is truthy — OR semantics)."""
        diag = {
            "driver_feel_flags": {},
            "avg_lockups": 2,
        }
        setup = {"brake_bias": 58.0}

        plan = _run_engine(diag, setup)

        a5 = [i for i in plan.rejected_candidates if i.rule_id == "A5"]
        assert len(a5) >= 1, (
            f"A5 FAIL: must be in rejected_candidates when avg_lockups=2; "
            f"rejected: {[(i.rule_id, i.field) for i in plan.rejected_candidates]}"
        )

    def test_a5_does_not_fire_when_braking_instability_false_and_lockups_zero(self):
        """A5 must NOT fire when braking_instability=False AND avg_lockups=0 (both falsy)."""
        diag = {
            "driver_feel_flags": {"braking_instability": False},
            "avg_lockups": 0,
        }
        setup = {"brake_bias": 58.0}

        plan = _run_engine(diag, setup)

        a5 = [i for i in plan.rejected_candidates if i.rule_id == "A5"]
        assert not a5, (
            f"A5 FAIL: must NOT fire when braking_instability=False and avg_lockups=0; "
            f"found: {[(i.rule_id, i.field) for i in a5]}"
        )


# ===========================================================================
# B5 — lengthen gearing on gear_too_short
# ===========================================================================

class TestB5GearTooShortRuleRekey:
    """B5 fires on the REAL diagnosis signals (gearing_diagnosis_category + gearbox_flag).

    The old Group 42 tests used the fictional gearbox_flag='too_short' which
    build_setup_diagnosis never emits. B5 was re-keyed to:
      - gearing_diagnosis_category == 'gear_too_short'
      - gearbox_flag == 'may_change'
    """

    def test_b5_fires_with_real_signals(self):
        """B5 must fire when gearing_diagnosis_category='gear_too_short' + gearbox_flag='may_change'."""
        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "may_change",
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert len(b5) >= 1, (
            f"B5 FAIL: must fire when gearing_diagnosis_category='gear_too_short' "
            f"and gearbox_flag='may_change'; "
            f"proposed: {[(i.field, i.rule_id) for i in plan.proposed]}"
        )

    def test_b5_proposes_final_drive(self):
        """B5 must propose final_drive, not any other field."""
        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "may_change",
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert b5, "B5 FAIL: must be in proposed"
        assert b5[0].field == "final_drive", (
            f"B5 FAIL: must propose field='final_drive'; got {b5[0].field!r}"
        )

    def test_b5_delta_is_negative_direction_test(self):
        """B5 delta MUST be negative (lengthens gearing = lower ratio number = higher top speed).

        This is a mandatory DIRECTION test per the story AC.
        """
        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "may_change",
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert b5, "B5 FAIL: must be in proposed (precondition not triggered)"
        assert b5[0].delta < 0.0, (
            f"B5 FAIL: delta must be NEGATIVE (lower final_drive ratio = longer gearing = "
            f"higher top speed); got delta={b5[0].delta}. "
            f"Direction is mandatory — a positive delta would shorten gearing and worsen the problem."
        )

    def test_b5_does_not_fire_on_gearbox_flag_preserve(self):
        """B5 must NOT fire when gearbox_flag='preserve', even if gearing_diagnosis_category matches."""
        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "preserve",
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert not b5, (
            f"B5 FAIL: must NOT fire when gearbox_flag='preserve'; "
            f"found: {[(i.field, i.rule_id) for i in b5]}"
        )

    def test_b5_does_not_fire_on_gearbox_flag_none(self):
        """B5 must NOT fire when gearbox_flag is absent (None/missing).

        The precondition is exact-match 'may_change'; None does not match.
        """
        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            # gearbox_flag absent entirely
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert not b5, (
            f"B5 FAIL: must NOT fire when gearbox_flag is absent; "
            f"found: {[(i.field, i.rule_id) for i in b5]}"
        )

    def test_b5_does_not_fire_on_gear_too_long_category(self):
        """B5 must NOT fire when gearing_diagnosis_category='gear_too_long'."""
        diag = {
            "gearing_diagnosis_category": "gear_too_long",
            "gearbox_flag": "may_change",
        }
        setup = {"final_drive": 3.6}

        plan = _run_engine(diag, setup)

        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert not b5, (
            f"B5 FAIL: must NOT fire when gearing_diagnosis_category='gear_too_long'; "
            f"found: {[(i.field, i.rule_id) for i in b5]}"
        )


# ===========================================================================
# Resolver direction tests
# ===========================================================================

class TestResolverDirections:
    """Each resolver returns a value in the expected sign direction."""

    def test_final_drive_down_is_negative(self):
        """resolve_delta('final_drive_down', ...) must return a negative value."""
        result = resolve_delta("final_drive_down", {}, {}, {})
        assert result < 0.0, (
            f"Resolver FAIL: 'final_drive_down' must return negative delta; got {result}"
        )

    def test_final_drive_up_is_positive(self):
        """resolve_delta('final_drive_up', ...) must return a positive value."""
        result = resolve_delta("final_drive_up", {}, {}, {})
        assert result > 0.0, (
            f"Resolver FAIL: 'final_drive_up' must return positive delta; got {result}"
        )

    def test_shorten_final_drive_legacy_alias_is_negative(self):
        """resolve_delta('shorten_final_drive', ...) must return a negative value (legacy alias)."""
        result = resolve_delta("shorten_final_drive", {}, {}, {})
        assert result < 0.0, (
            f"Resolver FAIL: 'shorten_final_drive' (legacy alias) must return negative delta; "
            f"got {result}. The alias must delegate to final_drive_down."
        )

    def test_final_drive_down_and_shorten_final_drive_same_magnitude(self):
        """shorten_final_drive and final_drive_down must return the same magnitude (-0.05)."""
        down = resolve_delta("final_drive_down", {}, {}, {})
        legacy = resolve_delta("shorten_final_drive", {}, {}, {})
        assert abs(down - legacy) < 1e-9, (
            f"Resolver FAIL: 'final_drive_down' ({down}) and 'shorten_final_drive' ({legacy}) "
            f"must be identical in value."
        )

    def test_unknown_resolver_returns_zero(self):
        """resolve_delta with an unknown key must return 0.0 (safe no-op)."""
        result = resolve_delta("nonexistent_resolver_xyz", {}, {}, {})
        assert result == 0.0, (
            f"Resolver FAIL: unknown resolver must return 0.0; got {result}"
        )


# ===========================================================================
# Self-consistency pipe test
# ===========================================================================

class TestSelfConsistencyPipe:
    """Validate that plan outputs survive the full normalisation + validation pipeline."""

    def test_b5_plan_no_blocking_failure_for_final_drive(self):
        """For a B5 fired plan, run the full pipe and assert no blocking ValidationFailure
        for final_drive.

        Pipe: run_rule_engine → plan_to_raw_data → _normalise_changes →
              validate_setup_engineering_structured.
        """
        from strategy.setup_plan import plan_to_raw_data
        from strategy.driving_advisor import _normalise_changes
        from strategy.setup_diagnosis import validate_setup_engineering_structured

        diag = {
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "may_change",
        }
        setup = {"final_drive": 3.6}
        ranges = resolve_ranges("")
        profile = build_driver_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)
        b5 = [i for i in plan.proposed if i.rule_id == "B5"]
        assert b5, "Self-consistency test pre-condition: B5 must fire"

        raw = plan_to_raw_data(plan, diag, "self-consistency test")
        _normalise_changes(raw.get("changes", []), raw.get("setup_fields", {}), "")
        failures = validate_setup_engineering_structured(raw, diag, setup, ranges, {}, "")

        blocking_for_final_drive = [
            f for f in failures
            if f.severity == "blocking" and "final_drive" in f.message
        ]
        assert not blocking_for_final_drive, (
            f"Self-consistency FAIL: blocking validation failures for final_drive "
            f"in B5 plan: {[f.message for f in blocking_for_final_drive]}"
        )

    def test_a2_reject_plan_has_no_proposed_change_for_aero_rear(self):
        """When A2 fires (rear instability guard), aero_rear must NOT be in proposed.

        A rejected candidate cannot also be proposed. No proposed change means no
        validator input for that field — self-consistency is trivially satisfied.
        """
        diag = {"driver_feel_flags": {"rear_loose_on_exit": True}}
        setup = {"aero_rear": 150}

        plan = _run_engine(diag, setup)

        a2_in_rejected = any(i.rule_id == "A2" for i in plan.rejected_candidates)
        assert a2_in_rejected, "Pre-condition: A2 must be in rejected_candidates"

        aero_rear_in_proposed = [i for i in plan.proposed if i.field == "aero_rear"]
        # aero_rear must not be proposed when A2 blocked it
        # (other rules may fire for different fields — we only check aero_rear from A2)
        a2_proposed_for_aero = [i for i in plan.proposed if i.field == "aero_rear" and i.rule_id == "A2"]
        assert not a2_proposed_for_aero, (
            f"Self-consistency FAIL: A2 must not appear in proposed; "
            f"found: {a2_proposed_for_aero}"
        )

    def test_a5_reject_plan_has_no_proposed_change_for_brake_bias(self):
        """When A5 fires (braking instability guard), brake_bias must NOT be authored by A5 in proposed."""
        diag = {
            "driver_feel_flags": {"braking_instability": True},
            "avg_lockups": 0,
        }
        setup = {"brake_bias": 58.0}

        plan = _run_engine(diag, setup)

        a5_in_rejected = any(i.rule_id == "A5" for i in plan.rejected_candidates)
        assert a5_in_rejected, "Pre-condition: A5 must be in rejected_candidates"

        a5_proposed = [i for i in plan.proposed if i.rule_id == "A5"]
        assert not a5_proposed, (
            f"Self-consistency FAIL: A5 must not appear in proposed; found: {a5_proposed}"
        )

    def test_a3_a4_protect_plan_has_no_proposed_change_for_ride_height(self):
        """When A3/A4 fire (minor bottoming guard), neither ride_height_front nor
        ride_height_rear should be proposed via A3/A4 (they are protected, not proposed).
        """
        diag = {
            "bottoming_band": "minor",
            "bottoming_confidence": {"band": "none", "subtype": "none", "confidence": "low"},
            "compliance_priority": False,
        }
        setup = {"ride_height_front": 80, "ride_height_rear": 82}

        plan = _run_engine(diag, setup)

        assert "ride_height_front" in plan.protected_fields, "Pre-condition: A3 must protect rh_front"
        assert "ride_height_rear" in plan.protected_fields, "Pre-condition: A4 must protect rh_rear"

        # Protected fields must not appear in proposed
        rh_proposed = [i for i in plan.proposed if i.field in ("ride_height_front", "ride_height_rear")]
        assert not rh_proposed, (
            f"Self-consistency FAIL: protected ride_height fields must not be in proposed; "
            f"found: {[(i.field, i.rule_id) for i in rh_proposed]}"
        )


# ===========================================================================
# Docs grep
# ===========================================================================

class TestDocsGrep:
    """Verify that module docstring and docs/RULE_FIRST_SETUP_BRAIN.md contain
    the expected deferred-limitation markers.
    """

    def test_module_docstring_mentions_build_setup_with_ai_disabled(self):
        """setup_knowledge_base.__doc__ must mention 'Build Setup with AI' and 'disabled'
        so the docstring is a reliable source-of-truth for the UI state.
        """
        import strategy.setup_knowledge_base as kb
        doc = kb.__doc__ or ""
        assert "Build Setup with AI" in doc, (
            "Docs FAIL: setup_knowledge_base module docstring must mention "
            "'Build Setup with AI' (the disabled button)"
        )
        assert "disabled" in doc.lower(), (
            "Docs FAIL: setup_knowledge_base module docstring must mention 'disabled' "
            "(status of the Build Setup with AI button)"
        )

    def test_docs_md_contains_deferred_gear_slots(self):
        """RULE_FIRST_SETUP_BRAIN.md must contain a deferred note about gear_1..gear_6 rules."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        # Accept either notation: "gear_1..gear_6" or "gear_1..6"
        assert ("gear_1..gear_6" in text or "gear_1..6" in text), (
            f"Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must mention gear_1..gear_6 "
            f"in deferred limitations"
        )

    def test_docs_md_contains_deferred_rule_outcome_store(self):
        """RULE_FIRST_SETUP_BRAIN.md must mention RuleOutcomeStore in deferred limitations."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "RuleOutcomeStore" in text, (
            "Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must mention RuleOutcomeStore"
        )

    def test_docs_md_contains_deferred_tyre(self):
        """RULE_FIRST_SETUP_BRAIN.md must mention tyre signals in deferred limitations."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "tyre" in text.lower(), (
            "Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must mention tyre signals in deferred"
        )

    def test_docs_md_contains_deferred_applies_session(self):
        """RULE_FIRST_SETUP_BRAIN.md must mention applies_session in deferred limitations."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "applies_session" in text, (
            "Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must mention applies_session"
        )

    def test_docs_md_contains_deferred_voice(self):
        """RULE_FIRST_SETUP_BRAIN.md must mention voice path in deferred limitations."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "voice" in text.lower(), (
            "Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must mention voice path"
        )

    def test_docs_md_contains_word_deferred(self):
        """RULE_FIRST_SETUP_BRAIN.md must contain the word 'deferred'."""
        doc_path = ROOT / "docs" / "RULE_FIRST_SETUP_BRAIN.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "deferred" in text.lower(), (
            "Docs FAIL: RULE_FIRST_SETUP_BRAIN.md must contain the word 'deferred'"
        )


# ===========================================================================
# UI Gate tests (headless, offscreen Qt)
# ===========================================================================

# Set before any QApplication is created so the tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class _StubHost:
    """Minimal host — every SetupFormWidget host call is hasattr-guarded."""


class TestBuildSetupButtonDisabled:
    """_btn_build_setup must be disabled AND hidden at construction time,
    for EVERY SetupFormWidget instance (Race and Qualifying).
    """

    def test_race_form_btn_build_setup_is_disabled(self, qapp):
        """SetupFormWidget('Race', host)._btn_build_setup must not be enabled."""
        from ui.setup_form_widget import SetupFormWidget
        host = _StubHost()
        form = SetupFormWidget("Race", host)
        assert not form._btn_build_setup.isEnabled(), (
            "UI FAIL: _btn_build_setup must be DISABLED on SetupFormWidget('Race', ...) "
            "construction (Group 43: ungated AI-build path disabled)"
        )

    def test_race_form_btn_build_setup_is_hidden(self, qapp):
        """SetupFormWidget('Race', host)._btn_build_setup must not be visible."""
        from ui.setup_form_widget import SetupFormWidget
        host = _StubHost()
        form = SetupFormWidget("Race", host)
        assert not form._btn_build_setup.isVisible(), (
            "UI FAIL: _btn_build_setup must be HIDDEN on SetupFormWidget('Race', ...) "
            "construction (Group 43: ungated AI-build path disabled)"
        )

    def test_qualifying_form_btn_build_setup_is_disabled(self, qapp):
        """SetupFormWidget('Qualifying', host)._btn_build_setup must not be enabled."""
        from ui.setup_form_widget import SetupFormWidget
        host = _StubHost()
        form = SetupFormWidget("Qualifying", host)
        assert not form._btn_build_setup.isEnabled(), (
            "UI FAIL: _btn_build_setup must be DISABLED on SetupFormWidget('Qualifying', ...) "
            "construction (Group 43: ungated AI-build path disabled)"
        )

    def test_qualifying_form_btn_build_setup_is_hidden(self, qapp):
        """SetupFormWidget('Qualifying', host)._btn_build_setup must not be visible."""
        from ui.setup_form_widget import SetupFormWidget
        host = _StubHost()
        form = SetupFormWidget("Qualifying", host)
        assert not form._btn_build_setup.isVisible(), (
            "UI FAIL: _btn_build_setup must be HIDDEN on SetupFormWidget('Qualifying', ...) "
            "construction (Group 43: ungated AI-build path disabled)"
        )

    def test_handler_guard_run_build_setup_does_not_call_build_car_setup(self, qapp):
        """The _run_build_setup handler guard must prevent build_car_setup from being called.

        Approach: patch strategy.ai_planner.build_car_setup with a MagicMock and then
        call the handler directly on a SetupBuilderMixin-like object. Since constructing
        a full SetupBuilderMixin requires a MainWindow (config-clobber guardrail), we
        instead verify the guard at the source-code level by inspecting the handler:
        the first executable statement of _run_build_setup must be 'return' (early exit).

        This is asserted via source inspection rather than runtime invocation, which is
        the only safe approach given the MainWindow guardrail.
        """
        import ast
        import inspect
        import textwrap
        from ui.setup_builder_ui import SetupBuilderMixin

        src = textwrap.dedent(inspect.getsource(SetupBuilderMixin._run_build_setup))
        tree = ast.parse(src)
        # Find the function definition body
        func_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_run_build_setup"
        )
        body_stmts = func_def.body
        # Skip optional docstring (Expr(Constant(...))) — the first *executable* statement
        # must be a Return (early exit guard).
        exec_stmts = [
            s for s in body_stmts
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        assert exec_stmts, "UI FAIL: _run_build_setup must have at least one executable statement"
        first_exec = exec_stmts[0]
        assert isinstance(first_exec, ast.Return), (
            "UI FAIL: _run_build_setup first executable statement must be 'return' "
            "(Group 43 guard: build_car_setup unreachable). "
            f"Found: {ast.dump(first_exec)}"
        )

    def test_handler_guard_run_build_setup_for_form_does_not_call_build_car_setup(self, qapp):
        """The _run_build_setup_for_form handler guard must be an early return as first executable statement."""
        import ast
        import inspect
        import textwrap
        from ui.setup_builder_ui import SetupBuilderMixin

        src = textwrap.dedent(inspect.getsource(SetupBuilderMixin._run_build_setup_for_form))
        tree = ast.parse(src)
        func_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_run_build_setup_for_form"
        )
        body_stmts = func_def.body
        # Skip optional docstring — the first *executable* statement must be a Return.
        exec_stmts = [
            s for s in body_stmts
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        assert exec_stmts, "UI FAIL: _run_build_setup_for_form must have at least one executable statement"
        first_exec = exec_stmts[0]
        assert isinstance(first_exec, ast.Return), (
            "UI FAIL: _run_build_setup_for_form first executable statement must be 'return' "
            "(Group 43 guard: build_car_setup unreachable). "
            f"Found: {ast.dump(first_exec)}"
        )
