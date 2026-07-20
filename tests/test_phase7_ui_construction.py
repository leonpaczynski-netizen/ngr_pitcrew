"""Engineering Brain Phase 7 — live monitor widget construction test.

Run this file individually: Windows/PyQt teardown can segfault AFTER a clean pass.
Asserts the panel builds, renders a real orchestrator result, and exposes NO Apply /
setup-authoring control (the monitor is a read-only observer).
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
    db = SessionDB(":memory:")
    sid = 500
    for i in range(1, 8):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)", (sid, 7, "Fuji", i, 95000))
    db._conn.commit()
    occ = lambda lap: {"session_id": sid, "setup_checkpoint_id": "", "lap_number": lap,
                       "segment_id": "T1", "corner_phase": "apex",
                       "issue_type": "understeer", "axle": "front",
                       "severity": 0.6, "confidence": 0.8}
    db.save_issue_occurrences(7, "Fuji", "", [occ(n) for n in (1, 2, 3, 4)])
    return db.build_live_engineering_state(sid, car_id=7, track="Fuji",
                                           scope_fingerprint="A", discipline="race")


def test_monitor_constructs_and_renders(app):
    from ui.live_engineering_monitor import LiveEngineeringMonitor
    w = LiveEngineeringMonitor()
    w.update_result(_result())
    # resolved table has the resolved understeer row
    assert w._resolved.rowCount() >= 1
    assert w._timeline.rowCount() >= 1
    w.deleteLater()


def test_monitor_safe_on_empty(app):
    from ui.live_engineering_monitor import LiveEngineeringMonitor
    w = LiveEngineeringMonitor()
    w.update_result(None)
    w.update_result({"ok": False})
    assert w._active.rowCount() == 0
    w.deleteLater()


def test_monitor_has_no_apply_or_authoring_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.live_engineering_monitor import LiveEngineeringMonitor
    w = LiveEngineeringMonitor()
    w.update_result(_result())
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label
        assert "save" not in label
        assert "revert" not in label
    w.deleteLater()
