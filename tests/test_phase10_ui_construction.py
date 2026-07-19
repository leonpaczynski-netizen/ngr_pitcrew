"""Engineering Brain Phase 10 — Pre-Flight Review panel construction test.

Run individually: Windows/PyQt teardown can segfault AFTER a clean pass. Asserts the
panel builds, renders a real result, and exposes NO Apply / approval controls.
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
    for oid, eid in ((1, 10), (2, 11)):
        outcome = {"id": oid, "experiment_id": eid, "status": "confirmed_improvement",
                   "confidence_level": "high", "scope_fingerprint": "sf",
                   "test_session_id": str(300 + oid), "protected": [],
                   "failed_directions": []}
        exp = {"id": eid, "scope_fingerprint": "sf",
               "changes": [{"field": "lsd_accel", "from_value": "20", "to_value": "25",
                            "delta_direction": "increase"}]}
        res = [{"issue_key": "k", "family": "traction", "issue_type": "exit_wheelspin",
                "axle": "rear", "phase": "exit", "segment_id": "T4", "corner_name": "T4",
                "residual_state": "resolved", "is_new": False, "is_regression": False,
                "still_present": False, "protected_good": False, "confidence": "high"}]
        rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                      working_windows=[], residuals=res,
                                      recorded_at=f"2026-07-0{oid}T10:00",
                                      session_date=f"2026-07-0{oid}")
        db._persist_development_record(rec, created_at=rec.recorded_at)
    selection = {"candidate_id": "c1", "target_issue": "exit_wheelspin", "field": "lsd_accel",
                 "direction": "increase", "current_value": 22.0, "proposed_value": 25.0,
                 "expected_positive_effect": "increases exit traction",
                 "expected_negative_effects": ["may reduce power-oversteer resistance"],
                 "protected_behaviours_at_risk": [], "supporting_evidence": ["x"],
                 "window_relationship": "inside_window", "evidence_grade": "medium"}
    return db.build_experiment_preflight(selection, car="RSR", track="Fuji",
                                         layout_id="fc", discipline="Race")


def test_panel_constructs_and_renders(app):
    from ui.preflight_review_panel import PreFlightReviewPanel
    w = PreFlightReviewPanel()
    w.update_result(_result())
    assert w._checklist.rowCount() >= 1
    assert w._consequences.rowCount() >= 1
    w.deleteLater()


def test_panel_safe_on_empty(app):
    from ui.preflight_review_panel import PreFlightReviewPanel
    w = PreFlightReviewPanel()
    w.update_result(None)
    w.update_result({"ok": False})
    assert w._checklist.rowCount() == 0
    w.deleteLater()


def test_panel_has_no_apply_or_approval_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.preflight_review_panel import PreFlightReviewPanel
    w = PreFlightReviewPanel()
    w.update_result(_result())
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label and "approve" not in label
        assert "accept" not in label and "save" not in label
    w.deleteLater()
