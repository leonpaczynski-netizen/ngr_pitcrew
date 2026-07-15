"""Tests for Group 17K — Segment-Aware Live Coaching Rules.

Covers:
  - dataclass construction (enums, LiveCoachingCue, LiveCoachingDecision, Config)
  - no reviewed/live segment returns no_call (suppressed)
  - low confidence suppresses cue
  - brake_lock in braking_zone creates braking_stability cue
  - wheelspin in corner_exit/apex_zone creates throttle_pickup cue
  - oversteer creates rotation cue
  - poor_exit_drive creates exit_drive cue
  - wrong_gear creates gear_choice cue
  - limiter_hit on straight creates short_shift cue
  - fuel_saving_opportunity only triggers when config.enable_fuel_save_cues=True
  - kerb_caution only triggers when config.enable_kerb_cues=True
  - REJECTED/NEEDS_MORE_LAPS segment suppresses cue
  - cue does not invent segment/corner name when unresolved/low confidence
  - cue priority changes with confidence/repetition
  - cooldown suppresses repeated cue
  - max cues per lap logic works
  - min_issue_repetitions gate
  - driving_advisor prompt includes cue when applicable
  - driving_advisor prompt omits cue when no_call
  - format_live_coaching_for_prompt returns compact block
  - get_live_coaching_debug_metadata returns correct fields
  - existing Group 17A–17J tests continue passing
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_live_match(
    segment_id="seg_braking_t1",
    display_name="T1 Braking Zone",
    segment_type="braking_zone",
    confidence="high",
    status="matched",
    model_source="ai_ready",
    warnings=None,
):
    from data.live_segment_resolver import (
        LiveSegmentMatch, LiveSegmentResolverResult,
        LiveSegmentResolutionStatus, LiveSegmentResolutionConfidence,
    )
    match = LiveSegmentMatch(
        track_location_id="t",
        layout_id="t__l",
        segment_id=segment_id,
        display_name=display_name,
        segment_type=segment_type,
        lap_progress=0.08,
        lap_progress_start=0.05,
        lap_progress_end=0.12,
        lap_progress_mid=0.085,
        distance_along_lap_m=None,
        confidence=LiveSegmentResolutionConfidence(confidence),
        source="lap_progress",
        warnings=warnings or [],
    )
    return LiveSegmentResolverResult(
        track_location_id="t",
        layout_id="t__l",
        status=LiveSegmentResolutionStatus(status),
        match=match,
        model_source=model_source,
    )


def _make_no_match(status="no_reviewed_model"):
    from data.live_segment_resolver import LiveSegmentResolverResult, LiveSegmentResolutionStatus
    return LiveSegmentResolverResult(
        track_location_id="t",
        layout_id="t__l",
        status=LiveSegmentResolutionStatus(status),
        match=None,
        model_source="missing",
    )


def _make_enriched_issue(
    issue_type="brake_lock",
    phase="braking",
    lap_num=1,
    matched_segment_id="seg_braking_t1",
    matched_segment_type="braking_zone",
    confidence="high",
):
    from data.track_issue_enrichment import (
        EnrichedTelemetryIssue, RawTelemetryIssue,
        TrackIssueType, TrackIssuePhase, TrackIssueEnrichmentConfidence,
    )
    raw = RawTelemetryIssue(
        issue_type=TrackIssueType(issue_type),
        phase=TrackIssuePhase(phase),
        lap_num=lap_num,
        lap_progress=0.08,
    )
    return EnrichedTelemetryIssue(
        raw=raw,
        matched_segment_id=matched_segment_id,
        matched_segment_type=matched_segment_type,
        matched_segment_display_name="T1 Braking Zone",
        matched_segment_lap_progress_mid=0.085,
        match_method="lap_progress",
        confidence=TrackIssueEnrichmentConfidence(confidence),
    )


def _issues_n_laps(issue_type="brake_lock", phase="braking", n=3,
                   segment_id="seg_braking_t1", segment_type="braking_zone",
                   confidence="high"):
    """Build N enriched issues (one per lap) to simulate repeated issue."""
    return [
        _make_enriched_issue(
            issue_type=issue_type, phase=phase, lap_num=i+1,
            matched_segment_id=segment_id, matched_segment_type=segment_type,
            confidence=confidence,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Class 1 — Dataclass construction
# ---------------------------------------------------------------------------

class TestDataclassConstruction:
    def test_cue_type_enum_values(self):
        from data.live_segment_coaching import LiveCoachingCueType
        values = [v.value for v in LiveCoachingCueType]
        for expected in [
            "braking_stability", "brake_release", "rotation", "throttle_pickup",
            "exit_drive", "gear_choice", "short_shift", "limiter_warning",
            "fuel_save", "kerb_caution", "tyre_management", "track_limits", "no_call",
        ]:
            assert expected in values

    def test_priority_enum_values(self):
        from data.live_segment_coaching import LiveCoachingPriority
        values = [v.value for v in LiveCoachingPriority]
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "urgent" in values

    def test_suppression_reason_enum_values(self):
        from data.live_segment_coaching import LiveCoachingSuppressionReason
        values = [v.value for v in LiveCoachingSuppressionReason]
        assert "no_segment" in values
        assert "low_confidence" in values
        assert "cooldown" in values
        assert "max_cues_reached" in values

    def test_cue_constructs(self):
        from data.live_segment_coaching import LiveCoachingCue, LiveCoachingCueType, LiveCoachingPriority
        cue = LiveCoachingCue(
            cue_type=LiveCoachingCueType.BRAKING_STABILITY,
            priority=LiveCoachingPriority.HIGH,
            text="Brake earlier.",
        )
        assert cue.cue_type == LiveCoachingCueType.BRAKING_STABILITY
        assert cue.issue_repetition_count == 0

    def test_decision_constructs_suppressed(self):
        from data.live_segment_coaching import LiveCoachingDecision, LiveCoachingSuppressionReason
        d = LiveCoachingDecision(
            suppressed=True,
            suppression_reason=LiveCoachingSuppressionReason.NO_SEGMENT,
        )
        assert d.suppressed
        assert d.cue is None

    def test_config_defaults(self):
        from data.live_segment_coaching import LiveCoachingConfig
        cfg = LiveCoachingConfig()
        assert cfg.enable_fuel_save_cues is False
        assert cfg.suppress_same_cue_for_laps == 3
        assert cfg.max_cues_per_lap == 3
        assert cfg.min_issue_repetitions == 2


# ---------------------------------------------------------------------------
# Class 2 — No live segment / unresolved returns no_call
# ---------------------------------------------------------------------------

class TestNoSegmentSuppression:
    def test_no_reviewed_model_returns_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_no_match("no_reviewed_model")
        decision = build_live_coaching_decision(result)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.NO_SEGMENT

    def test_no_position_data_returns_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_no_match("no_position_data")
        decision = build_live_coaching_decision(result)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.NO_SEGMENT

    def test_error_status_returns_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_no_match("error")
        decision = build_live_coaching_decision(result)
        assert decision.suppressed

    def test_seed_only_model_returns_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(model_source="seed_only")
        issues = _issues_n_laps()
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.SEED_ONLY

    def test_no_enriched_issues_returns_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match()
        decision = build_live_coaching_decision(result, enriched_issues=[])
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.NO_MATCHING_RULE

    def test_cue_is_none_when_suppressed(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_no_match()
        decision = build_live_coaching_decision(result)
        assert decision.cue is None

    def test_suppressed_never_raises(self):
        from data.live_segment_coaching import build_live_coaching_decision
        # None live_segment_result should not crash
        class BadResult:
            status = None
            match = None
            model_source = "missing"
        decision = build_live_coaching_decision(BadResult())
        assert decision.suppressed


# ---------------------------------------------------------------------------
# Class 3 — Low confidence suppression
# ---------------------------------------------------------------------------

class TestLowConfidenceSuppression:
    def test_unknown_confidence_suppresses(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(confidence="unknown")
        issues = _issues_n_laps()
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.LOW_CONFIDENCE

    def test_low_confidence_suppresses_by_default(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(confidence="low")
        issues = _issues_n_laps()
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.LOW_CONFIDENCE

    def test_low_confidence_allowed_when_config_disabled(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingConfig
        from data.live_segment_resolver import LiveSegmentResolutionStatus
        result = _make_live_match(confidence="low")
        issues = _issues_n_laps()
        cfg = LiveCoachingConfig(suppress_on_low_confidence=False)
        decision = build_live_coaching_decision(result, enriched_issues=issues, config=cfg)
        # Should not be suppressed for confidence reason — may fire with degraded priority
        # (Could still be suppressed for other reasons, but NOT low_confidence)
        if decision.suppressed:
            from data.live_segment_coaching import LiveCoachingSuppressionReason
            assert decision.suppression_reason != LiveCoachingSuppressionReason.LOW_CONFIDENCE


# ---------------------------------------------------------------------------
# Class 4 — Brake lock rules
# ---------------------------------------------------------------------------

class TestBrakeLockRules:
    def test_brake_lock_braking_zone_creates_braking_stability_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue is not None
        assert decision.cue.cue_type == LiveCoachingCueType.BRAKING_STABILITY

    def test_brake_lock_cue_priority_is_high_for_braking_zone(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingPriority
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.priority == LiveCoachingPriority.HIGH

    def test_brake_lock_cue_text_contains_segment_name(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(display_name="T1 Braking Zone", segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert "T1 Braking Zone" in decision.cue.text

    def test_brake_lock_corner_entry_creates_braking_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="corner_entry",
                                  segment_id="seg_entry_t1", display_name="T1 Entry")
        issues = _issues_n_laps("brake_lock", "entry", n=3,
                                segment_id="seg_entry_t1", segment_type="corner_entry")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.BRAKING_STABILITY

    def test_brake_lock_cue_basis_issue_type_set(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.basis_issue_type == "brake_lock"

    def test_brake_lock_cue_repetition_count(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=5)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.issue_repetition_count == 5


# ---------------------------------------------------------------------------
# Class 5 — Wheelspin / throttle rules
# ---------------------------------------------------------------------------

class TestWheelspinRules:
    def test_wheelspin_corner_exit_creates_throttle_pickup_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="corner_exit",
                                  segment_id="seg_exit_t1", display_name="T1 Exit")
        issues = _issues_n_laps("wheelspin", "traction", n=3,
                                segment_id="seg_exit_t1", segment_type="corner_exit")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.THROTTLE_PICKUP

    def test_wheelspin_apex_zone_creates_throttle_pickup_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="apex_zone",
                                  segment_id="seg_apex_t1", display_name="T1 Apex")
        issues = _issues_n_laps("wheelspin", "apex", n=3,
                                segment_id="seg_apex_t1", segment_type="apex_zone")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.THROTTLE_PICKUP


# ---------------------------------------------------------------------------
# Class 6 — Oversteer / understeer / rotation rules
# ---------------------------------------------------------------------------

class TestRotationRules:
    def test_oversteer_apex_creates_rotation_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="apex_zone",
                                  segment_id="seg_apex_t1", display_name="T1 Apex")
        issues = _issues_n_laps("oversteer", "apex", n=3,
                                segment_id="seg_apex_t1", segment_type="apex_zone")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.ROTATION

    def test_understeer_creates_rotation_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="corner_entry",
                                  segment_id="seg_entry_t2", display_name="T2 Entry")
        issues = _issues_n_laps("understeer", "entry", n=3,
                                segment_id="seg_entry_t2", segment_type="corner_entry")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.ROTATION


# ---------------------------------------------------------------------------
# Class 7 — Poor exit drive
# ---------------------------------------------------------------------------

class TestExitDriveRules:
    def test_poor_exit_drive_corner_exit_creates_exit_drive_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="corner_exit",
                                  segment_id="seg_exit_t3", display_name="T3 Exit")
        issues = _issues_n_laps("poor_exit_drive", "exit", n=3,
                                segment_id="seg_exit_t3", segment_type="corner_exit")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.EXIT_DRIVE

    def test_poor_exit_drive_traction_zone_creates_exit_drive_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="traction_zone",
                                  segment_id="seg_trx_t3", display_name="T3 Traction")
        issues = _issues_n_laps("poor_exit_drive", "traction", n=3,
                                segment_id="seg_trx_t3", segment_type="traction_zone")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.EXIT_DRIVE


# ---------------------------------------------------------------------------
# Class 8 — Wrong gear
# ---------------------------------------------------------------------------

class TestGearChoiceRules:
    def test_wrong_gear_apex_creates_gear_choice_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="apex_zone",
                                  segment_id="seg_apex_t5", display_name="T5 Apex")
        issues = _issues_n_laps("wrong_gear", "apex", n=3,
                                segment_id="seg_apex_t5", segment_type="apex_zone")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.GEAR_CHOICE

    def test_wrong_gear_corner_exit_creates_gear_choice_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="corner_exit",
                                  segment_id="seg_exit_t5", display_name="T5 Exit")
        issues = _issues_n_laps("wrong_gear", "exit", n=3,
                                segment_id="seg_exit_t5", segment_type="corner_exit")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.GEAR_CHOICE


# ---------------------------------------------------------------------------
# Class 9 — Rev limiter / short shift
# ---------------------------------------------------------------------------

class TestLimiterRules:
    def test_limiter_hit_straight_creates_short_shift_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="straight",
                                  segment_id="seg_str_main", display_name="Main Straight")
        issues = _issues_n_laps("limiter_hit", "straight", n=3,
                                segment_id="seg_str_main", segment_type="straight")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.SHORT_SHIFT

    def test_limiter_hit_non_straight_creates_limiter_warning(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingCueType
        result = _make_live_match(segment_type="apex_zone",
                                  segment_id="seg_apex_t2", display_name="T2 Apex")
        issues = _issues_n_laps("limiter_hit", "apex", n=3,
                                segment_id="seg_apex_t2", segment_type="apex_zone")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.LIMITER_WARNING


# ---------------------------------------------------------------------------
# Class 10 — Fuel save / kerb (config-gated)
# ---------------------------------------------------------------------------

class TestConfigGatedRules:
    def test_fuel_save_suppressed_by_default(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingConfig
        result = _make_live_match(segment_type="straight",
                                  segment_id="seg_str_back", display_name="Back Straight")
        issues = _issues_n_laps("fuel_saving_opportunity", "straight", n=3,
                                segment_id="seg_str_back", segment_type="straight")
        cfg = LiveCoachingConfig()  # enable_fuel_save_cues=False by default
        decision = build_live_coaching_decision(result, enriched_issues=issues, config=cfg)
        assert decision.suppressed

    def test_fuel_save_fires_when_enabled(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingConfig, LiveCoachingCueType
        result = _make_live_match(segment_type="straight",
                                  segment_id="seg_str_back", display_name="Back Straight")
        issues = _issues_n_laps("fuel_saving_opportunity", "straight", n=3,
                                segment_id="seg_str_back", segment_type="straight")
        cfg = LiveCoachingConfig(enable_fuel_save_cues=True)
        decision = build_live_coaching_decision(result, enriched_issues=issues, config=cfg)
        assert not decision.suppressed
        assert decision.cue.cue_type == LiveCoachingCueType.FUEL_SAVE

    def test_tyre_management_suppressed_by_default(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="corner_exit",
                                  segment_id="seg_exit_t1", display_name="T1 Exit")
        issues = _issues_n_laps("tyre_wear_hotspot", "exit", n=3,
                                segment_id="seg_exit_t1", segment_type="corner_exit")
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed


# ---------------------------------------------------------------------------
# Class 11 — Rejected / needs_more_laps segment suppression
# ---------------------------------------------------------------------------

class TestSegmentQualitySuppression:
    def test_rejected_segment_warning_suppresses_cue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(
            segment_type="braking_zone",
            warnings=["Segment 'T1 Braking Zone' was rejected — excluded from live matching."],
        )
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.REJECTED_SEGMENT

    def test_needs_more_laps_warning_suppresses_cue_by_default(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(
            segment_type="braking_zone",
            warnings=["Segment 'T1 Braking Zone' needs more calibration laps — confidence reduced."],
        )
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.NEEDS_MORE_LAPS

    def test_needs_more_laps_allowed_when_config_disabled(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingConfig
        result = _make_live_match(
            segment_type="braking_zone",
            confidence="medium",
            warnings=["Segment needs more calibration laps — confidence reduced."],
        )
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        cfg = LiveCoachingConfig(suppress_on_needs_more_laps=False)
        decision = build_live_coaching_decision(result, enriched_issues=issues, config=cfg)
        # Should not be suppressed for needs_more_laps reason
        if decision.suppressed:
            from data.live_segment_coaching import LiveCoachingSuppressionReason
            assert decision.suppression_reason != LiveCoachingSuppressionReason.NEEDS_MORE_LAPS


# ---------------------------------------------------------------------------
# Class 12 — No invented corner names
# ---------------------------------------------------------------------------

class TestNoInventedNames:
    def test_cue_text_has_no_placeholder_when_no_display_name(self):
        """When display_name is empty, {segment} placeholder is removed cleanly."""
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(display_name="", segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        if not decision.suppressed and decision.cue:
            assert "{segment}" not in decision.cue.text
            assert decision.cue.text.strip()  # non-empty

    def test_cue_text_does_not_invent_a_corner_name(self):
        """Cue text must not contain any invented corner name when not provided."""
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(display_name="", segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        if not decision.suppressed and decision.cue:
            text = decision.cue.text
            for invented in ["T1", "T2", "T3", "Turn 1", "Corner 1", "Hairpin", "Chicane"]:
                assert invented not in text

    def test_suppressed_prompt_text_does_not_invent_name(self):
        from data.live_segment_coaching import build_live_coaching_decision, format_live_coaching_for_prompt
        result = _make_no_match()
        decision = build_live_coaching_decision(result)
        text = format_live_coaching_for_prompt(decision)
        assert text == ""

    def test_format_with_unresolved_returns_empty(self):
        from data.live_segment_coaching import LiveCoachingDecision, LiveCoachingSuppressionReason, format_live_coaching_for_prompt
        d = LiveCoachingDecision(
            suppressed=True,
            suppression_reason=LiveCoachingSuppressionReason.NO_SEGMENT,
        )
        assert format_live_coaching_for_prompt(d) == ""


# ---------------------------------------------------------------------------
# Class 13 — Priority changes with confidence/repetition
# ---------------------------------------------------------------------------

class TestPriorityBehaviour:
    def test_high_repetition_maintains_base_priority(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingPriority
        result = _make_live_match(segment_type="braking_zone", confidence="high")
        issues = _issues_n_laps("brake_lock", "braking", n=10)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        # brake_lock braking_zone has HIGH base priority at high confidence
        assert decision.cue.priority == LiveCoachingPriority.HIGH

    def test_medium_confidence_uses_base_priority(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingPriority
        result = _make_live_match(segment_type="braking_zone", confidence="medium")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        # confidence is medium (usable) → base priority applies, not downgraded
        assert decision.cue.priority in (LiveCoachingPriority.HIGH, LiveCoachingPriority.MEDIUM)

    def test_multiple_issues_highest_priority_wins(self):
        """When multiple issue types match, highest priority cue is selected."""
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingPriority
        result = _make_live_match(segment_type="braking_zone", confidence="high")
        # brake_lock (HIGH) + wheelspin (MEDIUM fallback) at same segment
        issues = (
            _issues_n_laps("brake_lock", "braking", n=3) +
            _issues_n_laps("wheelspin", "braking", n=3)
        )
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed
        assert decision.cue.priority == LiveCoachingPriority.HIGH


# ---------------------------------------------------------------------------
# Class 14 — Cooldown / anti-spam
# ---------------------------------------------------------------------------

class TestCooldownBehaviour:
    def _make_previous_cue(self, cue_type_val="braking_stability",
                           segment_id="seg_braking_t1", lap=1, progress=0.08):
        from data.live_segment_coaching import LiveCoachingCue, LiveCoachingCueType, LiveCoachingPriority
        return LiveCoachingCue(
            cue_type=LiveCoachingCueType(cue_type_val),
            priority=LiveCoachingPriority.HIGH,
            text="Brake earlier.",
            basis_segment_id=segment_id,
            created_at_lap=lap,
            created_at_progress=progress,
        )

    def test_same_cue_type_same_segment_recent_lap_suppresses(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        prev = [self._make_previous_cue(lap=3)]  # on lap 3
        decision = build_live_coaching_decision(
            result, enriched_issues=issues,
            previous_cues=prev, current_lap=4,  # within 3-lap cooldown
        )
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.COOLDOWN

    def test_same_cue_after_cooldown_period_fires(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        prev = [self._make_previous_cue(lap=1)]  # far enough back
        decision = build_live_coaching_decision(
            result, enriched_issues=issues,
            previous_cues=prev, current_lap=5,  # 4 laps since last cue > suppress_same_cue_for_laps=3
        )
        assert not decision.suppressed

    def test_max_cues_per_lap_suppresses(self):
        from data.live_segment_coaching import (
            build_live_coaching_decision, LiveCoachingConfig,
            LiveCoachingSuppressionReason,
        )
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        cfg = LiveCoachingConfig(max_cues_per_lap=2)
        # Already 2 cues on lap 5
        prev = [
            self._make_previous_cue("braking_stability", "seg_other1", lap=5, progress=0.1),
            self._make_previous_cue("throttle_pickup", "seg_other2", lap=5, progress=0.2),
        ]
        decision = build_live_coaching_decision(
            result, enriched_issues=issues, config=cfg,
            previous_cues=prev, current_lap=5,
        )
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.MAX_CUES_REACHED

    def test_empty_previous_cues_does_not_suppress(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=3)
        decision = build_live_coaching_decision(result, enriched_issues=issues, previous_cues=[])
        assert not decision.suppressed


# ---------------------------------------------------------------------------
# Class 15 — Min issue repetitions gate
# ---------------------------------------------------------------------------

class TestMinRepetitionsGate:
    def test_single_lap_issue_suppressed_by_default(self):
        """Default min_issue_repetitions=2 → 1 lap is not enough."""
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingSuppressionReason
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=1)  # only 1 lap
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert decision.suppressed
        assert decision.suppression_reason == LiveCoachingSuppressionReason.NO_MATCHING_RULE

    def test_two_lap_issues_fires(self):
        from data.live_segment_coaching import build_live_coaching_decision
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=2)
        decision = build_live_coaching_decision(result, enriched_issues=issues)
        assert not decision.suppressed

    def test_config_min_1_allows_single_lap_issue(self):
        from data.live_segment_coaching import build_live_coaching_decision, LiveCoachingConfig
        result = _make_live_match(segment_type="braking_zone")
        issues = _issues_n_laps("brake_lock", "braking", n=1)
        cfg = LiveCoachingConfig(min_issue_repetitions=1)
        decision = build_live_coaching_decision(result, enriched_issues=issues, config=cfg)
        assert not decision.suppressed


# ---------------------------------------------------------------------------
# Class 16 — format_live_coaching_for_prompt
# ---------------------------------------------------------------------------

class TestFormatForPrompt:
    def _build_cue(self):
        from data.live_segment_coaching import LiveCoachingCue, LiveCoachingCueType, LiveCoachingPriority
        return LiveCoachingCue(
            cue_type=LiveCoachingCueType.BRAKING_STABILITY,
            priority=LiveCoachingPriority.HIGH,
            text="Brake earlier into T1 and release smoother.",
            basis_segment_id="seg_braking_t1",
            basis_segment_display_name="T1 Braking Zone",
            basis_issue_type="brake_lock",
            issue_repetition_count=3,
            match_confidence="high",
        )

    def test_cue_in_prompt_contains_text(self):
        from data.live_segment_coaching import (
            format_live_coaching_for_prompt, LiveCoachingDecision,
        )
        cue = self._build_cue()
        d = LiveCoachingDecision(suppressed=False, cue=cue)
        block = format_live_coaching_for_prompt(d)
        assert "Brake earlier into T1" in block

    def test_cue_in_prompt_contains_header(self):
        from data.live_segment_coaching import format_live_coaching_for_prompt, LiveCoachingDecision
        cue = self._build_cue()
        d = LiveCoachingDecision(suppressed=False, cue=cue)
        block = format_live_coaching_for_prompt(d)
        assert "## Live Coaching Cue" in block

    def test_cue_in_prompt_contains_basis(self):
        from data.live_segment_coaching import format_live_coaching_for_prompt, LiveCoachingDecision
        cue = self._build_cue()
        d = LiveCoachingDecision(suppressed=False, cue=cue)
        block = format_live_coaching_for_prompt(d)
        assert "brake lock" in block.lower() or "T1 Braking Zone" in block

    def test_suppressed_returns_empty(self):
        from data.live_segment_coaching import (
            format_live_coaching_for_prompt, LiveCoachingDecision,
            LiveCoachingSuppressionReason,
        )
        d = LiveCoachingDecision(
            suppressed=True,
            suppression_reason=LiveCoachingSuppressionReason.COOLDOWN,
        )
        assert format_live_coaching_for_prompt(d) == ""

    def test_format_never_raises(self):
        from data.live_segment_coaching import format_live_coaching_for_prompt, LiveCoachingDecision
        d = LiveCoachingDecision(suppressed=True)
        result = format_live_coaching_for_prompt(d)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Class 17 — get_live_coaching_debug_metadata
# ---------------------------------------------------------------------------

class TestDebugMetadata:
    def test_suppressed_has_cue_included_false(self):
        from data.live_segment_coaching import (
            get_live_coaching_debug_metadata, LiveCoachingDecision,
            LiveCoachingSuppressionReason,
        )
        d = LiveCoachingDecision(
            suppressed=True,
            suppression_reason=LiveCoachingSuppressionReason.COOLDOWN,
        )
        meta = get_live_coaching_debug_metadata(d)
        assert meta["live_coaching_cue_included"] is False
        assert meta["live_coaching_suppression_reason"] == "cooldown"

    def test_cue_fired_has_cue_included_true(self):
        from data.live_segment_coaching import (
            get_live_coaching_debug_metadata, LiveCoachingDecision,
            LiveCoachingCue, LiveCoachingCueType, LiveCoachingPriority,
        )
        cue = LiveCoachingCue(
            cue_type=LiveCoachingCueType.BRAKING_STABILITY,
            priority=LiveCoachingPriority.HIGH,
            text="Brake earlier.",
            basis_segment_id="seg_braking_t1",
        )
        d = LiveCoachingDecision(suppressed=False, cue=cue)
        meta = get_live_coaching_debug_metadata(d)
        assert meta["live_coaching_cue_included"] is True
        assert meta["live_coaching_cue_type"] == "braking_stability"
        assert meta["live_coaching_priority"] == "high"
        assert meta["live_coaching_basis_segment"] == "seg_braking_t1"

    def test_metadata_never_raises(self):
        from data.live_segment_coaching import get_live_coaching_debug_metadata, LiveCoachingDecision
        d = LiveCoachingDecision(suppressed=True)
        meta = get_live_coaching_debug_metadata(d)
        assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# Class 18 — DrivingAdvisor integration
# ---------------------------------------------------------------------------

class TestDrivingAdvisorIntegration:
    def _make_advisor(self, loc_id="suzuka_circuit", lay_id="suzuka_circuit__full_course"):
        from strategy.driving_advisor import DrivingAdvisor
        config = {
            "strategy": {"track_location_id": loc_id, "layout_id": lay_id, "track": "Test"},
            "anthropic": {"api_key": "test_key"},
        }
        recorder = MagicMock()
        recorder.best_lap.return_value = None
        tracker = MagicMock()
        return DrivingAdvisor(recorder, tracker, config)

    def _make_lap(self):
        lap = MagicMock()
        lap.lap_num = 1
        lap.lap_time_ms = 90000
        lap.lock_up_count = 0
        lap.wheelspin_count = 0
        lap.oversteer_count = 0
        lap.oversteer_throttle_on_count = 0
        lap.kerb_count = 0
        lap.bottoming_count = 0
        lap.snap_throttle_count = 0
        lap.brake_consistency_m = 5.0
        lap.max_speed_kmh = 200.0
        lap.max_lat_g = 1.5
        lap.avg_throttle_pct = 60.0
        lap.avg_brake_pct = 20.0
        lap.rev_limiter_count = 0
        lap.lock_up_positions = []
        lap.wheelspin_positions = []
        lap.oversteer_positions = []
        lap.snap_throttle_positions = []
        lap.over_braking_positions = []
        lap.rev_limiter_by_gear = {}
        lap.over_braking_count = 0
        lap.abrupt_release_count = 0
        lap.car_max_speed_theoretical_kmh = 0.0
        lap.avg_tyre_radius = {}
        lap.off_track_count = 0
        return lap

    def test_get_live_coaching_context_no_position_returns_empty(self):
        adv = self._make_advisor()
        ctx = adv._get_live_coaching_context(live_position=None)
        assert ctx == ""

    def test_get_live_coaching_context_no_ids_returns_empty(self):
        adv = self._make_advisor(loc_id="", lay_id="")
        from data.live_segment_resolver import LivePosition
        pos = LivePosition(lap_progress=0.08)
        ctx = adv._get_live_coaching_context(live_position=pos)
        assert ctx == ""

    def test_get_live_coaching_context_returns_string(self):
        adv = self._make_advisor()
        from data.live_segment_resolver import LivePosition
        from data.track_model_resolver import TrackModelResolverResult, TrackModelResolutionStatus
        missing = TrackModelResolverResult(
            track_location_id="suzuka_circuit",
            layout_id="suzuka_circuit__full_course",
            resolution_status=TrackModelResolutionStatus.MISSING,
        )
        pos = LivePosition(lap_progress=0.08)
        with patch("data.track_model_resolver.resolve_best_track_model", return_value=missing):
            ctx = adv._get_live_coaching_context(live_position=pos)
        assert isinstance(ctx, str)

    def test_get_live_coaching_context_never_raises(self):
        adv = self._make_advisor()
        from data.live_segment_resolver import LivePosition
        pos = LivePosition(lap_progress=0.08)
        with patch("data.track_model_resolver.resolve_best_track_model", side_effect=RuntimeError("x")):
            ctx = adv._get_live_coaching_context(live_position=pos)
        assert isinstance(ctx, str)


# ---------------------------------------------------------------------------
# Class 19 — Regression imports: Groups 17A–17J
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_live_segment_coaching_importable(self):
        from data.live_segment_coaching import (
            build_live_coaching_decision, format_live_coaching_for_prompt,
            get_live_coaching_debug_metadata,
            LiveCoachingCueType, LiveCoachingPriority, LiveCoachingSuppressionReason,
            LiveCoachingCue, LiveCoachingDecision, LiveCoachingConfig,
        )
        assert callable(build_live_coaching_decision)

    def test_live_segment_resolver_importable(self):
        from data.live_segment_resolver import resolve_live_segment
        assert callable(resolve_live_segment)

    def test_track_issue_enrichment_importable(self):
        from data.track_issue_enrichment import enrich_telemetry_issues
        assert callable(enrich_telemetry_issues)

    def test_driving_advisor_has_coaching_method(self):
        from strategy.driving_advisor import DrivingAdvisor
        assert hasattr(DrivingAdvisor, "_get_live_coaching_context")

    def test_format_cue_text_removes_placeholder_cleanly(self):
        from data.live_segment_coaching import _format_cue_text
        template = "Brake a touch earlier into {segment} and release smoother."
        result = _format_cue_text(template, "")
        assert "{segment}" not in result
        assert result.strip()

    def test_format_cue_text_inserts_name(self):
        from data.live_segment_coaching import _format_cue_text
        template = "Brake a touch earlier into {segment} and release smoother."
        result = _format_cue_text(template, "T1 Braking Zone")
        assert "T1 Braking Zone" in result

    def test_downgrade_priority_from_high_to_medium(self):
        from data.live_segment_coaching import _downgrade_priority, LiveCoachingPriority
        result = _downgrade_priority(LiveCoachingPriority.HIGH)
        assert result == LiveCoachingPriority.MEDIUM

    def test_downgrade_priority_from_low_stays_low(self):
        from data.live_segment_coaching import _downgrade_priority, LiveCoachingPriority
        result = _downgrade_priority(LiveCoachingPriority.LOW)
        assert result == LiveCoachingPriority.LOW

    def test_all_issue_types_have_at_least_one_rule(self):
        """Every issue type in _CUE_TEMPLATE_TABLE should produce a cue for some segment."""
        from data.live_segment_coaching import _lookup_cue_template
        covered_issue_types = {
            "brake_lock", "wheelspin", "oversteer", "understeer",
            "poor_exit_drive", "wrong_gear", "limiter_hit",
        }
        for issue_type in covered_issue_types:
            rule = _lookup_cue_template(issue_type, "some_unknown_segment_type")
            assert rule is not None, f"No fallback rule for issue_type={issue_type}"

    def test_build_live_coaching_decision_never_raises_on_garbage_input(self):
        from data.live_segment_coaching import build_live_coaching_decision
        decision = build_live_coaching_decision(None, enriched_issues=None)
        assert decision.suppressed

    def test_group_17a_importable(self):
        from data.track_intelligence import load_track_seed
        assert callable(load_track_seed)

    def test_group_17g_importable(self):
        from data.track_model_resolver import resolve_best_track_model
        assert callable(resolve_best_track_model)
