"""Engineering Brain Phase 9 — Engineering Context panel construction test.

Run individually: Windows/PyQt teardown can segfault AFTER a clean pass. Asserts the
panel builds, renders a real result, and exposes NO Apply / decision controls.
"""
import pytest

_qt = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def _result():
    from data.session_db import SessionDB
    from strategy.development_history import MemoryContextKey, build_development_record
    db = SessionDB(":memory:")
    ctx = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race")
    outcome = {"id": 1, "experiment_id": 10, "status": "regression",
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": "300", "protected": [],
               "failed_directions": [{"field": "lsd_accel", "direction": "increase",
                                      "magnitude": "30", "severity": "high"}]}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "lsd_accel", "from_value": "20", "to_value": "30",
                        "delta_direction": "increase"}]}
    res = [{"issue_key": "k", "family": "traction", "issue_type": "oversteer",
            "axle": "rear", "phase": "exit", "segment_id": "T4", "corner_name": "T4",
            "residual_state": "new", "is_new": True, "is_regression": False,
            "still_present": True, "protected_good": False, "confidence": "high"}]
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                  working_windows=[], residuals=res,
                                  recorded_at="2026-07-01T10:00", session_date="2026-07-01")
    db._persist_development_record(rec, created_at=rec.recorded_at)
    return db.build_engineering_context(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race",
        proposed_change={"field": "lsd_accel", "direction": "increase", "value": "32"})


def test_panel_constructs_and_renders(app):
    from ui.engineering_context_panel import EngineeringContextPanel
    w = EngineeringContextPanel()
    w.update_result(_result())
    assert w._matches.rowCount() >= 1
    assert w._risks.rowCount() >= 1
    w.deleteLater()


def test_panel_safe_on_empty(app):
    from ui.engineering_context_panel import EngineeringContextPanel
    w = EngineeringContextPanel()
    w.update_result(None)
    w.update_result({"ok": False})
    assert w._risks.rowCount() == 0
    w.deleteLater()


def test_panel_has_no_apply_or_decision_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.engineering_context_panel import EngineeringContextPanel
    w = EngineeringContextPanel()
    w.update_result(_result())
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label and "save" not in label and "revert" not in label
        assert "accept" not in label and "select" not in label
    w.deleteLater()
