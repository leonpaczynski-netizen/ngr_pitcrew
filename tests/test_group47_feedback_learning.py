"""Group 47 — driver feedback learning tests.

Covers classify_driver_feedback and how feedback folds into verify_outcome:
  • positive feedback supports a confidence upgrade ONLY when telemetry agrees
  • negative feedback can downgrade (flat telemetry + "worse" → WORSE/worsened)
  • vague feedback creates no strong learning
  • contradictory feedback → MIXED (or INSUFFICIENT when telemetry is also weak)
  • telemetry safety regressions are NEVER overridden by positive feedback

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_outcome_verification import (
    OutcomeVerdict, MetricSnapshot, verify_outcome, classify_driver_feedback,
    outcome_to_learning_verdict, TARGET_EXIT_TRACTION,
)


def _v(before, after, feedback=""):
    return verify_outcome(
        rule_id="P1", car_id=7, track="Fuji", layout_id="full_course",
        target_issue=TARGET_EXIT_TRACTION, before=before, after=after,
        driver_feedback=feedback,
    )


# ---------------------------------------------------------------------------
# Feedback classification
# ---------------------------------------------------------------------------

class TestClassifyFeedback:
    @pytest.mark.parametrize("text", [
        "better", "much better", "fixed exit traction", "more grip", "feels planted",
    ])
    def test_positive(self, text):
        assert classify_driver_feedback(text) == "better"

    @pytest.mark.parametrize("text", [
        "worse", "rear still loose", "made braking worse", "more understeer", "nervous",
    ])
    def test_negative(self, text):
        assert classify_driver_feedback(text) == "worse"

    @pytest.mark.parametrize("text", ["no change", "about the same", "no difference"])
    def test_neutral(self, text):
        assert classify_driver_feedback(text) == "no_change"

    def test_contradictory_is_mixed(self):
        assert classify_driver_feedback("exit better but braking worse") == "mixed"

    @pytest.mark.parametrize("text", ["", None, "hmm", "the car"])
    def test_vague_is_unknown(self, text):
        assert classify_driver_feedback(text) == "unknown"


# ---------------------------------------------------------------------------
# Feedback → outcome folding
# ---------------------------------------------------------------------------

class TestFeedbackFolding:
    def test_positive_supports_upgrade_only_when_telemetry_agrees(self):
        improving_before = MetricSnapshot(wheelspin=10.0, clean_laps=6)
        improving_after = MetricSnapshot(wheelspin=4.0, clean_laps=6)
        with_pos = _v(improving_before, improving_after, "fixed exit traction")
        without = _v(improving_before, improving_after, "")
        assert with_pos.outcome == OutcomeVerdict.IMPROVED
        assert without.outcome == OutcomeVerdict.IMPROVED
        # Positive feedback that agrees with telemetry strengthens confidence.
        assert with_pos.confidence > without.confidence

    def test_positive_feedback_does_not_manufacture_improvement_on_flat_telemetry(self):
        # Flat telemetry + positive feedback must NOT become IMPROVED (feedback
        # alone never authors an improvement verdict).
        r = _v(MetricSnapshot(wheelspin=5.0, clean_laps=6),
               MetricSnapshot(wheelspin=5.1, clean_laps=6), "feels better")
        assert r.outcome != OutcomeVerdict.IMPROVED

    def test_negative_feedback_downgrades_flat_telemetry(self):
        r = _v(MetricSnapshot(wheelspin=5.0, clean_laps=6),
               MetricSnapshot(wheelspin=5.1, clean_laps=6), "rear still loose")
        assert r.outcome == OutcomeVerdict.WORSE
        assert outcome_to_learning_verdict(r.outcome) == "worsened"

    def test_vague_feedback_creates_no_strong_learning(self):
        r = _v(MetricSnapshot(wheelspin=5.0, clean_laps=6),
               MetricSnapshot(wheelspin=5.1, clean_laps=6), "hmm")
        assert r.outcome == OutcomeVerdict.UNCHANGED
        assert r.confidence <= 0.5  # weak — no strong learning

    def test_contradictory_feedback_yields_mixed(self):
        # Telemetry improved, but the driver's own words conflict → mixed.
        r = _v(MetricSnapshot(wheelspin=10.0, clean_laps=6),
               MetricSnapshot(wheelspin=4.0, clean_laps=6),
               "exit better but braking worse")
        assert r.outcome == OutcomeVerdict.MIXED
        assert outcome_to_learning_verdict(r.outcome) == "neutral"  # never an upgrade

    def test_telemetry_regression_not_overridden_by_positive_feedback(self):
        # Wheelspin got clearly worse; positive feedback must not rescue it.
        r = _v(MetricSnapshot(wheelspin=4.0, clean_laps=6),
               MetricSnapshot(wheelspin=10.0, clean_laps=6), "feels great")
        assert r.outcome == OutcomeVerdict.WORSE
        assert "telemetry" in r.safety_notes.lower()

    def test_feedback_only_no_telemetry_stays_insufficient(self):
        # No measured metric (thin laps) + strong feedback → still insufficient;
        # feedback alone cannot author a verdict.
        r = _v(MetricSnapshot(wheelspin=10.0, clean_laps=1),
               MetricSnapshot(wheelspin=4.0, clean_laps=1), "totally fixed")
        assert r.outcome == OutcomeVerdict.INSUFFICIENT_EVIDENCE
