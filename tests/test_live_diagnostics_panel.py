"""Live Activation 1 — the diagnostics panel widget (§9)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _panel(qapp):
    from ui.components.live_diagnostics import LivePracticeDiagnosticsPanel
    return LivePracticeDiagnosticsPanel()


def _dispose(p, qapp):
    # Deterministic teardown (Win/Py3.14 undisposed-widget crash guard).
    p.close()
    p.deleteLater()
    qapp.processEvents()


def _active():
    return {
        "active": True, "recording_state": "recording", "connected": True,
        "valid_lap_count": 6, "session_type": "practice",
        "event_id": "42", "event_programme_id": "cyc-1", "session_plan_id": "plan-1",
        "session_run_id": "run-abc", "stint_id": "stint-1", "car_id": "333",
        "car_spec_revision_id": "spec-1", "setup_snapshot_id": "setup-1",
        "context_revision_id": "ctx-1", "driver_profile_version_id": "drv-1",
        "track_model_version_id": "trk-1",
    }


def test_inactive_by_default(qapp):
    p = _panel(qapp)
    try:
        assert p.is_expanded() is False
        assert p._body.isHidden() is True           # collapsed
        assert "NOT STARTED" in p._state_pill.text()
        assert p._laps.isHidden() is True           # no count while inactive
    finally:
        _dispose(p, qapp)


def test_active_recording_renders_state_and_ids(qapp):
    p = _panel(qapp)
    try:
        p.set_diagnostics(_active())
        assert "RECORDING" in p._state_pill.text()
        assert "LIVE" in p._conn_pill.text()
        assert p._laps.text() == "6 valid laps"
        assert p._values["session_run_id"].text() == "run-abc"
        assert p._values["session_plan_id"].text() == "plan-1"
        assert p._values["event_id"].text() == "42"
        assert p._values["session_run_id"].toolTip() == "run-abc"
    finally:
        _dispose(p, qapp)


def test_disconnected_shows_no_signal_danger(qapp):
    p = _panel(qapp)
    try:
        d = _active()
        d["recording_state"] = "disconnected"
        d["connected"] = False
        p.set_diagnostics(d)
        assert "DISCONNECTED" in p._state_pill.text()
        assert "NO SIGNAL" in p._conn_pill.text()
    finally:
        _dispose(p, qapp)


def test_expander_reveals_body(qapp):
    p = _panel(qapp)
    try:
        p.set_diagnostics(_active())
        assert p._body.isHidden() is True
        p._toggle.setChecked(True)
        assert p._body.isHidden() is False and p.is_expanded()
        assert "▾" in p._toggle.text()
    finally:
        _dispose(p, qapp)


def test_reverting_to_inactive_hides_values(qapp):
    p = _panel(qapp)
    try:
        p.set_diagnostics(_active())
        p.set_diagnostics({"active": False, "recording_state": "not_started"})
        assert p._laps.isHidden() is True
        assert p._values["session_run_id"].text() == "—"
        assert "NOT STARTED" in p._state_pill.text()
    finally:
        _dispose(p, qapp)


def test_never_raises_on_garbage(qapp):
    p = _panel(qapp)
    try:
        p.set_diagnostics(None)              # type: ignore
        p.set_diagnostics({"active": True})  # missing fields
        assert p._values["event_id"].text() == "—"
    finally:
        _dispose(p, qapp)
