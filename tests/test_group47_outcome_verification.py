"""Group 47 — Outcome Verification & Learning Loop 2: model + safety tests.

Covers the pure classification model in strategy/setup_outcome_verification.py:
  • improvement / worse / unchanged / mixed / insufficient-evidence classification
  • target-issue inference from changed fields
  • the verdict bridge into the Group 46 learning vocabulary
  • SAFETY: the model authors no setup values, cannot unblock rejected changes,
    cannot touch the Apply gate, and returns INSUFFICIENT_EVIDENCE for issues with
    no telemetry signal (no invented steering-angle / rival metrics).

All tests are pure/offline — no DB, no Qt, no network.
"""
from __future__ import annotations

import sys
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_outcome_verification import (
    OutcomeVerdict, MetricSnapshot, OutcomeVerificationResult,
    verify_outcome, outcome_to_learning_verdict, infer_target_issue_from_fields,
    TARGET_EXIT_TRACTION, TARGET_BOTTOMING, TARGET_BRAKE_STABILITY, TARGET_ROTATION,
    TARGET_UNKNOWN, MIN_CLEAN_LAPS,
)


def _v(target, before, after, feedback=""):
    return verify_outcome(
        rule_id="R", car_id=7, track="Fuji", layout_id="full_course",
        target_issue=target, before=before, after=after, driver_feedback=feedback,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassification:
    def test_improved_when_target_metric_improves_enough(self):
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=10.0, clean_laps=6),
               MetricSnapshot(wheelspin=4.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.IMPROVED
        assert r.confidence > 0.0
        assert "wheelspin" in r.evidence_summary

    def test_worse_when_target_metric_deteriorates(self):
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=4.0, clean_laps=6),
               MetricSnapshot(wheelspin=10.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.WORSE

    def test_unchanged_when_movement_too_small(self):
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=5.0, clean_laps=6),
               MetricSnapshot(wheelspin=5.2, clean_laps=6))
        assert r.outcome == OutcomeVerdict.UNCHANGED

    def test_mixed_when_one_issue_improves_another_worsens(self):
        # Exit traction improves (wheelspin 10→4) but bottoming worsens (1→5).
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=10.0, bottoming=1.0, clean_laps=6),
               MetricSnapshot(wheelspin=4.0, bottoming=5.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.MIXED
        assert "new problem" in r.evidence_summary.lower()

    def test_mixed_when_secondary_metric_disagrees(self):
        # brake_stability: lock_up improves but brake_consistency worsens.
        r = _v(TARGET_BRAKE_STABILITY,
               MetricSnapshot(lock_up=8.0, brake_consistency=2.0, clean_laps=6),
               MetricSnapshot(lock_up=2.0, brake_consistency=9.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.MIXED

    def test_insufficient_when_thin_laps_either_side(self):
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=10.0, clean_laps=MIN_CLEAN_LAPS - 1),
               MetricSnapshot(wheelspin=4.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.INSUFFICIENT_EVIDENCE
        assert r.confidence == 0.0

    def test_insufficient_when_target_metric_absent(self):
        # rotation target but oversteer signal not measured on the after side.
        r = _v(TARGET_ROTATION,
               MetricSnapshot(oversteer=5.0, clean_laps=6),
               MetricSnapshot(oversteer=-1.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.INSUFFICIENT_EVIDENCE

    def test_bottoming_improved(self):
        r = _v(TARGET_BOTTOMING,
               MetricSnapshot(bottoming=6.0, clean_laps=6),
               MetricSnapshot(bottoming=1.0, clean_laps=6))
        assert r.outcome == OutcomeVerdict.IMPROVED

    def test_never_raises_on_garbage(self):
        r = verify_outcome(
            rule_id="R", car_id=0, track="", layout_id="",
            target_issue=TARGET_EXIT_TRACTION,
            before=MetricSnapshot(wheelspin=float("nan"), clean_laps=6),
            after=MetricSnapshot(wheelspin=4.0, clean_laps=6),
        )
        assert isinstance(r, OutcomeVerificationResult)


# ---------------------------------------------------------------------------
# Target inference
# ---------------------------------------------------------------------------

class TestTargetInference:
    def test_traction_fields(self):
        assert infer_target_issue_from_fields(["lsd_accel"]) == TARGET_EXIT_TRACTION
        assert infer_target_issue_from_fields(["aero_rear"]) == TARGET_EXIT_TRACTION

    def test_bottoming_fields(self):
        assert infer_target_issue_from_fields(["ride_height_rear"]) == TARGET_BOTTOMING
        assert infer_target_issue_from_fields(["springs_front"]) == TARGET_BOTTOMING

    def test_brake_fields(self):
        assert infer_target_issue_from_fields(["brake_bias"]) == TARGET_BRAKE_STABILITY

    def test_traction_wins_priority(self):
        # When both traction and rotation fields present, traction (safety) wins.
        assert infer_target_issue_from_fields(["aero_front", "lsd_accel"]) == TARGET_EXIT_TRACTION

    def test_unknown_field(self):
        assert infer_target_issue_from_fields(["tyre_pressure_xyz"]) == TARGET_UNKNOWN
        assert infer_target_issue_from_fields([]) == TARGET_UNKNOWN


# ---------------------------------------------------------------------------
# No-signal issues honestly return insufficient evidence (no invented metrics)
# ---------------------------------------------------------------------------

class TestNoInventedMetrics:
    @pytest.mark.parametrize("target", ["understeer", "front_bite", TARGET_UNKNOWN, ""])
    def test_unsupported_targets_return_insufficient(self, target):
        r = _v(target,
               MetricSnapshot(clean_laps=6), MetricSnapshot(clean_laps=6))
        assert r.outcome == OutcomeVerdict.INSUFFICIENT_EVIDENCE
        assert r.confidence == 0.0


# ---------------------------------------------------------------------------
# Verdict bridge to Group 46 learning vocabulary
# ---------------------------------------------------------------------------

class TestVerdictBridge:
    def test_improved_maps_to_improved(self):
        assert outcome_to_learning_verdict(OutcomeVerdict.IMPROVED) == "improved"

    def test_worse_maps_to_worsened(self):
        assert outcome_to_learning_verdict(OutcomeVerdict.WORSE) == "worsened"

    def test_unchanged_maps_to_neutral(self):
        assert outcome_to_learning_verdict(OutcomeVerdict.UNCHANGED) == "neutral"

    def test_mixed_never_boosts_confidence(self):
        # MIXED → neutral means it is fire-only in the feed: never an upgrade.
        assert outcome_to_learning_verdict(OutcomeVerdict.MIXED) == "neutral"

    def test_insufficient_maps_to_insufficient_data(self):
        # The Group 46 feed skips 'insufficient_data' rows entirely.
        assert outcome_to_learning_verdict(OutcomeVerdict.INSUFFICIENT_EVIDENCE) == "insufficient_data"


# ---------------------------------------------------------------------------
# SAFETY — the model has no authority to author setup or bypass gates
# ---------------------------------------------------------------------------

class TestSafety:
    def test_result_exposes_no_setup_value_fields(self):
        """The result carries a classification/explanation ONLY — no setup values,
        no field/to/apply attributes that could be misread as actionable."""
        r = _v(TARGET_EXIT_TRACTION,
               MetricSnapshot(wheelspin=10.0, clean_laps=6),
               MetricSnapshot(wheelspin=4.0, clean_laps=6))
        field_names = set(r.__dataclass_fields__.keys())
        forbidden = {"to", "to_clamped", "value", "setup", "apply", "field_value",
                     "new_value", "recommended_value", "changes", "setup_fields"}
        assert not (field_names & forbidden), (
            f"Outcome result must not expose setup-authoring fields; found {field_names & forbidden}"
        )

    def test_module_does_not_import_ai_or_db(self):
        """Purity: the module imports no AI client, no sqlite3, no PyQt, no I/O.

        Checks actual import statements via AST (not substrings — the docstring
        deliberately names these libraries to describe what it avoids)."""
        import ast
        import strategy.setup_outcome_verification as mod
        tree = ast.parse(inspect.getsource(mod))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        banned = {"sqlite3", "openai", "anthropic", "PyQt6", "requests",
                  "urllib", "os", "json"}
        assert not (imported & banned), (
            f"Purity violation — module imports {imported & banned}"
        )

    def test_module_defines_no_apply_or_write_functions(self):
        """The public surface classifies/explains only — nothing applies or writes."""
        import strategy.setup_outcome_verification as mod
        public = [n for n in dir(mod) if not n.startswith("_")]
        for name in public:
            low = name.lower()
            assert not any(w in low for w in ("apply", "write", "persist", "author", "commit")), (
                f"Model exposes a mutation-shaped symbol: {name!r}"
            )
