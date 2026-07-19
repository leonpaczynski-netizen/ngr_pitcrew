"""Engineering Brain Phase 11 — Post-Flight Review panel construction test.

Run individually: Windows/PyQt teardown can segfault AFTER a clean pass. Asserts the
panel builds, renders a real result + calibration, and exposes NO Apply controls.
"""
import pytest

_qt = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


_RESULT = {"ok": True, "record": {
    "predicted_risk": "moderate", "outcome_status": "confirmed_improvement",
    "accuracy": {"overall_accuracy": 0.95, "primary_consequence_accuracy": 1.0,
                 "side_effect_accuracy": 1.0, "risk_accuracy": 0.0,
                 "constraint_accuracy": 1.0, "historical_transfer_usefulness": 1.0,
                 "checklist_usefulness": 1.0, "confirmed_count": 4, "contradicted_count": 0},
    "consequence_reconciliations": [
        {"predicted": "increases exit traction", "status": "confirmed",
         "observed": "resolved", "reason": "target resolved"}],
    "checklist_validations": [
        {"label": "Inside learned window", "expectation": "stays inside",
         "outcome": "did_not_materialise", "useful": True, "reason": "no violation",
         "status": "ok"}]}}
_CALIB = {"ok": True, "calibration": {"reconciliations": 2, "overall_accuracy": 0.9,
                                      "confirmed_total": 6, "contradicted_total": 1}}


def test_panel_constructs_and_renders(app):
    from ui.postflight_review_panel import PostFlightReviewPanel
    w = PostFlightReviewPanel()
    w.update_result(_RESULT)
    w.update_calibration(_CALIB)
    assert w._confirmed.rowCount() >= 1
    assert w._accuracy.rowCount() >= 1
    assert w._calibration.rowCount() >= 1
    w.deleteLater()


def test_panel_safe_on_empty(app):
    from ui.postflight_review_panel import PostFlightReviewPanel
    w = PostFlightReviewPanel()
    w.update_result(None)
    w.update_result({"ok": False})
    assert w._confirmed.rowCount() == 0
    w.deleteLater()


def test_panel_has_no_apply_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.postflight_review_panel import PostFlightReviewPanel
    w = PostFlightReviewPanel()
    w.update_result(_RESULT)
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label and "approve" not in label and "save" not in label
    w.deleteLater()
