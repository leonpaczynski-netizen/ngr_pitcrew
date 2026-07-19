"""Engineering Brain Phase 8 — Development History page construction test.

Run this file individually: Windows/PyQt teardown can segfault AFTER a clean pass.
Asserts the page builds, renders a real cross-session result, and exposes NO Apply /
setup-authoring control (it is a read-only cross-session memory view).
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
    ctx = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race",
                           compound="RH")
    for i, (status, state, present) in enumerate([
            ("no_meaningful_change", "unchanged", True),
            ("confirmed_improvement", "resolved", False)], start=1):
        outcome = {"id": i, "experiment_id": 10 + i, "status": status,
                   "confidence_level": "high", "scope_fingerprint": "sf",
                   "test_session_id": str(300 + i), "protected": [],
                   "failed_directions": []}
        exp = {"id": 10 + i, "scope_fingerprint": "sf",
               "changes": [{"field": "toe_front", "from_value": "0.1", "to_value": "0.2"}]}
        res = [{"issue_key": "k", "family": "rotation", "issue_type": "understeer",
                "axle": "front", "phase": "apex", "segment_id": "T1",
                "corner_name": "Turn 1", "residual_state": state, "is_new": False,
                "is_regression": False, "still_present": present,
                "protected_good": False, "confidence": "high"}]
        rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                      working_windows=[], residuals=res,
                                      recorded_at=f"2026-07-0{i}T10:00",
                                      session_date=f"2026-07-0{i}")
        db._persist_development_record(rec, created_at=rec.recorded_at)
    return db.build_cross_session_memory(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race", compound="RH")


def test_page_constructs_and_renders(app):
    from ui.development_history_page import DevelopmentHistoryPage
    w = DevelopmentHistoryPage()
    w.update_result(_result())
    assert w._experiments.rowCount() == 2
    assert w._timeline.rowCount() >= 1
    w.deleteLater()


def test_page_safe_on_empty(app):
    from ui.development_history_page import DevelopmentHistoryPage
    w = DevelopmentHistoryPage()
    w.update_result(None)
    w.update_result({"ok": False})
    assert w._resolved.rowCount() == 0
    w.deleteLater()


def test_page_has_no_apply_or_authoring_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.development_history_page import DevelopmentHistoryPage
    w = DevelopmentHistoryPage()
    w.update_result(_result())
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label and "save" not in label and "revert" not in label
    w.deleteLater()
