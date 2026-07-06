"""Group 47 — outcome-verification explainability tests.

Follows the Group 46 UI-test pattern: pure formatter behaviour + source-level
assertions on the render path + backend-wiring checks.  This avoids the known
PyQt cross-file segfault on Windows/Python 3.14 while still proving the
"Learning outcome" surface exists, is gated, and stays honest.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_outcome_verification import format_learning_outcome_explanation


def _row(rule_id="P1", verdict="improved", target="exit_traction"):
    return {"rule_id": rule_id, "verdict": verdict, "target_issue": target}


# ---------------------------------------------------------------------------
# Pure formatter
# ---------------------------------------------------------------------------

class TestFormatter:
    def test_empty_when_no_outcomes(self):
        assert format_learning_outcome_explanation([]) == ""
        assert format_learning_outcome_explanation(None) == ""

    def test_empty_when_only_insufficient(self):
        rows = [_row(verdict="insufficient_data"), _row(verdict="")]
        assert format_learning_outcome_explanation(rows) == ""

    def test_improved_majority_upgrades(self):
        rows = [_row(verdict="improved"), _row(verdict="improved"),
                _row(verdict="improved"), _row(verdict="worsened")]
        out = format_learning_outcome_explanation(rows)
        assert "Learning outcome:" in out
        assert "improved exit traction" in out
        assert "3 of 4" in out
        assert "upgraded one step" in out

    def test_worsened_majority_downgrades_and_mentions_gating(self):
        rows = [_row(verdict="worsened"), _row(verdict="worsened"),
                _row(verdict="improved")]
        out = format_learning_outcome_explanation(rows)
        assert "worsened exit traction" in out
        assert "downgraded one step" in out
        assert "gated" in out.lower()

    def test_always_includes_honest_disclaimer(self):
        out = format_learning_outcome_explanation([_row(), _row()])
        assert "confidence/ranking" in out
        assert "does not author setup values" in out
        assert "bypass validation" in out

    def test_groups_by_rule_id(self):
        rows = [_row(rule_id="P1", verdict="improved"),
                _row(rule_id="B3", verdict="worsened", target="brake_stability")]
        out = format_learning_outcome_explanation(rows)
        assert "Rule P1" in out
        assert "Rule B3" in out
        assert "brake stability" in out

    def test_never_raises_on_malformed_rows(self):
        rows = [{"rule_id": None}, {}, {"verdict": 123}, _row()]
        # Must not raise; returns a string.
        assert isinstance(format_learning_outcome_explanation(rows), str)

    def test_no_actionable_setup_values_in_text(self):
        """The explanation is prose about confidence — it never emits a setup
        value/apply directive that could be misread as actionable."""
        out = format_learning_outcome_explanation(
            [_row(verdict="improved"), _row(verdict="improved")]
        ).lower()
        for banned in ("apply this", "set to", "change to", "new value", "click apply"):
            assert banned not in out


# ---------------------------------------------------------------------------
# Render-path source assertions (segfault-free)
# ---------------------------------------------------------------------------

class TestRenderPath:
    def test_display_extracts_learning_outcome_explanation(self):
        from ui.setup_builder_ui import SetupBuilderMixin
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        assert "_learning_outcome_explanation" in src, (
            "Group 47: _display_setup_result must read _learning_outcome_explanation"
        )

    def test_display_gates_block_on_non_empty(self):
        from ui.setup_builder_ui import SetupBuilderMixin
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        # The block is only assembled when the explanation is non-empty.
        assert "if _lo_expl:" in src, (
            "Group 47: learning-outcome block must be gated on a non-empty string"
        )
        assert "_learning_outcome_html" in src

    def test_display_html_included_in_output(self):
        from ui.setup_builder_ui import SetupBuilderMixin
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        # The block must actually be concatenated into the rendered html.
        assert "+ _learning_outcome_html" in src


# ---------------------------------------------------------------------------
# Backend wiring
# ---------------------------------------------------------------------------

class TestBackendWiring:
    def test_driving_advisor_populates_explanation_key(self):
        import strategy.driving_advisor as da
        src = inspect.getsource(da)
        assert "_learning_outcome_explanation" in src, (
            "driving_advisor must populate the _learning_outcome_explanation payload key"
        )
        assert "format_learning_outcome_explanation" in src

    def test_dashboard_records_group47_evidence(self):
        import ui.dashboard as dash
        src = inspect.getsource(dash)
        # The scoring pass wires the Group 47 verification into record_learning_outcome.
        assert "_verify_change_outcome" in src
        assert "outcome_kind=" in src
        assert "target_issue=" in src
