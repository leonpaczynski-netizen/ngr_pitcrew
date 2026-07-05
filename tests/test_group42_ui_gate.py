"""
Group 42 — I4/AC17 UI Gate: _display_setup_result Apply-button visibility tests

Covers the C1 defect fix: absent/empty/None/unrecognised recommendation_status
must all prevent the Apply button from appearing, and must show the legacy banner.

These tests exercise the ACTUAL _display_setup_result path (SetupBuilderMixin)
using a headless QApplication and a real SetupFormWidget at result-tuple position 4.

The critical truth table:
  absent / "" / None / unrecognised → _is_legacy=True → Apply HIDDEN, legacy banner shown
  "approved" / "approved_with_warnings" / "fallback_generated" → Apply VISIBLE (if fields present)
  "validation_failed" / "blocked_no_safe_recommendation" → Apply HIDDEN
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Must be set before any QApplication is created so the tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402
from ui.setup_form_widget import SetupFormWidget  # noqa: E402
from ui.setup_builder_ui import SetupBuilderMixin  # noqa: E402


# ---------------------------------------------------------------------------
# QApplication fixture (module scope — one QApp per process)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Minimal stub host for SetupBuilderMixin._display_setup_result
# ---------------------------------------------------------------------------

class _StubHost(SetupBuilderMixin):
    """Minimal host for _display_setup_result.

    SetupBuilderMixin._display_setup_result reads self._setup_result_text
    (to pass the hasattr guard), self._config (for tuning-compliance check),
    and _active_config_id() (for history save — returns None to make it a no-op).
    All button/text routing goes via _form at tuple position 4.
    """

    def __init__(self):
        # Satisfy the hasattr guard at line 1126
        self._setup_result_text = QTextEdit()
        self._config = {}
        self._last_setup_context = None
        self._last_setup_ai_fields = {}

    def _build_setup_context(self, **kwargs):
        return None

    def _active_config_id(self):
        """Return None so the history-save block is a no-op."""
        return None


# ---------------------------------------------------------------------------
# Helper: build a minimal Group 42 JSON payload
# ---------------------------------------------------------------------------

def _make_payload(
    recommendation_status=None,
    changes: list | None = None,
    setup_fields: dict | None = None,
) -> str:
    """Build a minimal valid JSON payload for _display_setup_result."""
    payload: dict = {
        "analysis": "Test analysis from rule engine.",
        "primary_issue": "test",
        "changes": changes if changes is not None else [],
        "setup_fields": setup_fields if setup_fields is not None else {},
        "rejected_changes": [],
        "validation_errors": [],
        "validation_warnings": [],
        "engineering_validation_errors": [],
        "engineering_validation_failed": False,
        "fallback_used": False,
        "deterministic_plan": {
            "proposed_count": 0,
            "rejected_candidate_count": 0,
            "protected_fields": [],
        },
    }
    if recommendation_status is not None:
        payload["recommendation_status"] = recommendation_status
    # Deliberately omit recommendation_status when None (to test the absent-key case)
    return json.dumps(payload)


def _call_display(stub: _StubHost, form: SetupFormWidget, payload_str: str) -> None:
    """Call _display_setup_result routing via the SetupFormWidget at position 4."""
    stub._display_setup_result(
        ("success", payload_str, "analyse_setup", None, form)
    )


# ===========================================================================
# I4 / AC17 UI gate — _display_setup_result Apply-button visibility
# ===========================================================================

class TestDisplaySetupResultApplyGate:
    """Verify _display_setup_result gates the Apply button correctly.

    Truth table (the C1 fix):
      absent status (no key)    → _is_legacy=True  → Apply HIDDEN
      ""  (empty string)        → _is_legacy=True  → Apply HIDDEN
      None-rendered (absent)    → _is_legacy=True  → Apply HIDDEN
      "unrecognised_xyz"        → _is_legacy=True  → Apply HIDDEN
      "approved"                → _is_legacy=False → Apply VISIBLE (when fields present)
      "validation_failed"       → _is_legacy=False → Apply HIDDEN
    """

    @pytest.fixture
    def host_and_form(self, qapp):
        host = _StubHost()
        host._setup_result_text  # ensure it exists
        form = SetupFormWidget("Race", host)
        return host, form

    def test_absent_status_hides_apply_button(self, host_and_form):
        """No recommendation_status key in payload → Apply button must be hidden.

        This is the C1 defect scenario: before the fix, absent status could set
        _status_approved=True via the old logic.
        """
        host, form = host_and_form

        # Payload with NO recommendation_status key and actionable fields
        payload = _make_payload(
            recommendation_status=None,  # will be omitted from JSON
            changes=[{"field": "arb_rear", "from": 3, "to": 4,
                      "setting": "Rear ARB", "why": "test", "to_clamped": 4}],
            setup_fields={"arb_rear": 4},
        )
        # Remove recommendation_status from JSON entirely (simulate absent key)
        data = json.loads(payload)
        data.pop("recommendation_status", None)
        payload = json.dumps(data)

        _call_display(host, form, payload)

        # isHidden() checks the widget's own hidden flag; isVisible() also checks parent
        # visibility which is False for unshown widgets. Use isHidden() for correctness.
        assert form._btn_apply_ai_setup.isHidden(), (
            "AC17 C1 DEFECT: Apply button is NOT hidden for a payload with ABSENT "
            "recommendation_status. _display_setup_result must treat absent status as "
            "legacy_unknown and hide Apply."
        )

    def test_empty_string_status_hides_apply_button(self, host_and_form):
        """recommendation_status='' → Apply button must be hidden."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="",
            changes=[{"field": "arb_rear", "from": 3, "to": 4,
                      "setting": "Rear ARB", "why": "test", "to_clamped": 4}],
            setup_fields={"arb_rear": 4},
        )

        _call_display(host, form, payload)

        assert form._btn_apply_ai_setup.isHidden(), (
            "AC17 C1 DEFECT: Apply button is NOT hidden for recommendation_status=''. "
            "Empty string must be treated as legacy_unknown → Apply hidden."
        )

    def test_unrecognised_status_hides_apply_button(self, host_and_form):
        """recommendation_status='some_old_status_xyz' → Apply button must be hidden."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="some_old_status_xyz_999",
            changes=[{"field": "arb_rear", "from": 3, "to": 4,
                      "setting": "Rear ARB", "why": "test", "to_clamped": 4}],
            setup_fields={"arb_rear": 4},
        )

        _call_display(host, form, payload)

        assert form._btn_apply_ai_setup.isHidden(), (
            "AC17 C1 DEFECT: Apply button is NOT hidden for unrecognised recommendation_status. "
            "Unrecognised status must be treated as legacy_unknown → Apply hidden."
        )

    def test_absent_status_shows_legacy_banner(self, host_and_form):
        """No recommendation_status key → the rendered HTML contains the legacy banner text."""
        host, form = host_and_form

        data = json.loads(_make_payload(recommendation_status=None))
        data.pop("recommendation_status", None)
        payload = json.dumps(data)

        _call_display(host, form, payload)

        html = form._setup_result_text.toHtml()
        assert "Legacy recommendation" in html, (
            "AC17 DEFECT: Legacy banner text ('Legacy recommendation') not found in rendered HTML "
            "for absent recommendation_status. "
            f"HTML snippet: {html[:500]!r}"
        )
        assert "cannot apply" in html, (
            "AC17 DEFECT: Legacy banner must say 'cannot apply' for absent status. "
            f"HTML snippet: {html[:500]!r}"
        )

    def test_empty_string_status_shows_legacy_banner(self, host_and_form):
        """recommendation_status='' → legacy banner shown in HTML."""
        host, form = host_and_form

        payload = _make_payload(recommendation_status="")
        _call_display(host, form, payload)

        html = form._setup_result_text.toHtml()
        assert "Legacy recommendation" in html, (
            "AC17 DEFECT: Legacy banner missing for empty-string recommendation_status. "
            f"HTML snippet: {html[:500]!r}"
        )

    def test_unrecognised_status_shows_legacy_banner(self, host_and_form):
        """Unrecognised status → legacy banner shown in HTML."""
        host, form = host_and_form

        payload = _make_payload(recommendation_status="totally_unknown_legacy_value")
        _call_display(host, form, payload)

        html = form._setup_result_text.toHtml()
        assert "Legacy recommendation" in html, (
            "AC17 DEFECT: Legacy banner missing for unrecognised recommendation_status. "
            f"HTML snippet: {html[:500]!r}"
        )

    def test_approved_status_shows_apply_when_fields_present(self, host_and_form):
        """recommendation_status='approved' with approved fields → Apply visible."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="approved",
            changes=[{"field": "arb_rear", "from": 3, "to": 4,
                      "setting": "Rear ARB", "why": "test", "to_clamped": 4}],
            setup_fields={"arb_rear": 4},
        )

        _call_display(host, form, payload)

        # not isHidden() means the button has been set to show (visible to parent)
        assert not form._btn_apply_ai_setup.isHidden(), (
            "AC17 regression: Apply button IS HIDDEN for recommendation_status='approved' "
            "with numeric fields present. The gate is too strict — approved status "
            "with fields must show Apply."
        )

    def test_approved_with_warnings_shows_apply_when_fields_present(self, host_and_form):
        """recommendation_status='approved_with_warnings' with fields → Apply not hidden."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="approved_with_warnings",
            changes=[{"field": "arb_rear", "from": 3, "to": 4,
                      "setting": "Rear ARB", "why": "test", "to_clamped": 4}],
            setup_fields={"arb_rear": 4},
        )

        _call_display(host, form, payload)

        assert not form._btn_apply_ai_setup.isHidden(), (
            "AC17 regression: Apply button IS HIDDEN for 'approved_with_warnings' with fields. "
            "approved_with_warnings is in APPROVED_STATUSES and must show Apply."
        )

    def test_validation_failed_hides_apply_button(self, host_and_form):
        """recommendation_status='validation_failed' → Apply button must be hidden."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="validation_failed",
            changes=[],
            setup_fields={},
        )

        _call_display(host, form, payload)

        assert form._btn_apply_ai_setup.isHidden(), (
            "Safety defect: Apply button is NOT hidden for validation_failed status. "
            "Blocked recommendations must never show Apply."
        )

    def test_blocked_no_safe_recommendation_hides_apply(self, host_and_form):
        """recommendation_status='blocked_no_safe_recommendation' → Apply hidden."""
        host, form = host_and_form

        payload = _make_payload(
            recommendation_status="blocked_no_safe_recommendation",
            changes=[],
            setup_fields={},
        )

        _call_display(host, form, payload)

        assert form._btn_apply_ai_setup.isHidden(), (
            "Safety defect: Apply button is NOT hidden for blocked_no_safe_recommendation."
        )
