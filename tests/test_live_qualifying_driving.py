"""Live Activation 2 — telemetry → qualifying coordinator driving (end-to-end, offline).

Drives the REAL LiveShellBridge reconciliation (_drive_live_qualifying) against a real SessionDB
seeded with the full spine + a fake window that simulates GT7 telemetry (connection + live
session id + an on-track flag + completed laps). Proves: the app activates from the PLANNED
qualifying activity (never from telemetry), adopts the live session as one canonical run, drives
the qualifying phase machine off the on-track (pit-exit/box) edges + completed laps, tracks the
personal best, survives disconnect/reconnect, blocks honestly on missing context, does not
activate on a practice activity, and finalises on record.
"""
from __future__ import annotations

import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Dispatcher:
    def __init__(self):
        self._session_id = 0


class _FakeTracker:
    """Minimal tracker exposing the read-only on-track flag the qualifying driving reads."""
    def __init__(self, on_track=None):
        self.live_on_track = on_track


class _FakeWindow:
    """Minimal window with the telemetry hooks the driving reads."""
    def __init__(self, live_sid, car_id, connected=True, on_track=None):
        self._dispatcher = _Dispatcher()
        self._dispatcher._session_id = live_sid
        self._car_id = car_id
        self._connected = connected
        self._tracker = _FakeTracker(on_track)

    def _build_session_context(self):
        return types.SimpleNamespace(connected=self._connected)

    def _current_car_id(self):
        return self._car_id


def _seed_db(tmp_path, *, car_id=333, event_id=42, with_revisions=True,
             activity_type="qualifying_simulation", session_type="Qualifying"):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    db.upsert_preparation_cycle({
        "cycle_id": "cyc-1", "event_id": event_id, "event_name": "Cup R3", "track": "Fuji",
        "car": "GT-R", "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
        "explicit_state": "active"})
    db.upsert_preparation_activity({
        "activity_id": f"cyc-1::{activity_type}::1", "cycle_id": "cyc-1",
        "activity_type": activity_type, "order_index": 0, "state": "in_progress"})
    if with_revisions:
        db.add_car_spec_revision(car_id=car_id, car_name="GT-R", event_id=event_id, label="base")
        db.append_driver_profile_version(version_label="v1", reason="seed")
    live_sid = db.open_session(car_id, "Fuji", session_type, car_name="GT-R", event_id=event_id)
    return db, live_sid


def _bridge(qapp, db, win):
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=win, config={"active_cycle_id": "cyc-1"}, db=db,
                        spawn=lambda fn: fn())
    return shell, b


def _dispose(shell, qapp):
    shell.close()
    shell.deleteLater()
    qapp.processEvents()


def _write_lap(db, sid, lap_num, ms, *, is_out=False, is_pit=False):
    db.write_lap(sid, lap_num, ms, 0.0, None, event_id=42, session_type="Qualifying",
                 is_out_lap=is_out, is_pit_lap=is_pit)


def test_activation_adopts_live_session_and_tracks_best_lap(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=False)
    shell, b = _bridge(qapp, db, win)
    try:
        # telemetry connected + a planned qualifying activity open → activate, adopting live_sid
        b._drive_live_qualifying()
        assert b._live_qualifying is not None
        assert b._live_qualifying.is_recording
        # ONE canonical run for the live session (adopted, not a second one)
        run = db.get_run_for_session(live_sid)
        assert run is not None and b._live_qualifying.run_id == run["run_id"]
        assert run["session_plan_id"] == "cyc-1::qualifying_simulation::1"
        assert b._live_qualifying.phase == "preparation"

        # driver leaves the pits → out-lap begins (attempt 1)
        win._tracker.live_on_track = True
        b._drive_live_qualifying()
        assert b._live_qualifying.phase == "out_lap"
        assert b._live_qualifying.attempt == 1

        # out-lap completes → the flying lap is underway
        _write_lap(db, live_sid, 1, 140000, is_out=True)
        b._drive_live_qualifying()
        assert b._live_qualifying.phase == "flying_lap"

        # flying lap completes → personal best recorded
        _write_lap(db, live_sid, 2, 90000)
        b._drive_live_qualifying()
        assert b._live_qualifying.phase == "lap_complete"
        assert b._live_qualifying.best_lap_ms == 90000

        # box, go again, improve on a second attempt
        win._tracker.live_on_track = False
        b._drive_live_qualifying()
        assert b._live_qualifying.phase == "preparation"
        win._tracker.live_on_track = True
        b._drive_live_qualifying()
        assert b._live_qualifying.attempt == 2
        _write_lap(db, live_sid, 3, 141000, is_out=True)
        b._drive_live_qualifying()
        _write_lap(db, live_sid, 4, 89000)
        b._drive_live_qualifying()
        assert b._live_qualifying.best_lap_ms == 89000
    finally:
        _dispose(shell, qapp)


def test_practice_activity_does_not_activate_qualifying(qapp, tmp_path):
    # A practice activity is open → the qualifying gate blocks (wrong session type), no run.
    db, live_sid = _seed_db(tmp_path, activity_type="baseline_practice", session_type="Practice")
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()
        assert b._live_qualifying is None
    finally:
        _dispose(shell, qapp)


def test_missing_context_blocks_activation_with_reason(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path, with_revisions=False)
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()
        assert b._live_qualifying is None
        assert "car_spec_revision_id" in b._live_qualifying_block or \
               "driver_profile_version_id" in b._live_qualifying_block
    finally:
        _dispose(shell, qapp)


def test_disconnect_then_reconnect_resumes_same_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()
        run_id = b._live_qualifying.run_id

        win._connected = False                       # telemetry drops
        b._drive_live_qualifying()
        assert b._live_qualifying.state.value == "disconnected"

        win._connected = True                        # same session returns
        b._drive_live_qualifying()
        assert b._live_qualifying.is_recording and b._live_qualifying.run_id == run_id
    finally:
        _dispose(shell, qapp)


def test_diagnostics_report_qualifying_identity_and_best(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()          # activate + pit-exit
        _write_lap(db, live_sid, 1, 140000, is_out=True)
        b._drive_live_qualifying()          # out-lap → flying
        _write_lap(db, live_sid, 2, 90000)
        b._drive_live_qualifying()          # flying → PB

        d = b.live_qualifying_diagnostics()
        assert d["active"] and d["session_type"] == "qualifying"
        assert d["best_lap_ms"] == 90000
        assert d["qualifying_phase"] == "lap_complete"
        assert "90.000" in d["headline"]
        assert d["session_plan_id"] == "cyc-1::qualifying_simulation::1"
    finally:
        _dispose(shell, qapp)


def test_record_finalises_the_qualifying_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()
        _write_lap(db, live_sid, 1, 140000, is_out=True)
        b._drive_live_qualifying()
        b._on_record_run()
        assert b._live_qualifying.state.value == "completed"
        assert db.get_session_run(b._live_qualifying.run_id)["status"] == "completed"
    finally:
        _dispose(shell, qapp)


def test_qualifying_engineer_speaks_on_phase_edges(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    spoken: list = []

    class _Announcer:
        def announce(self, text, priority, source):
            spoken.append((text, source))

    win = _FakeWindow(live_sid, car_id=333, connected=True, on_track=False)
    win._announcer = _Announcer()
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_qualifying()          # preparation
        line = b._speak_qualifying_engineer()
        assert "one lap" in line.lower()
        # same phase again → silent (anti-chatter)
        assert b._speak_qualifying_engineer() == ""

        win._tracker.live_on_track = True
        b._drive_live_qualifying()          # out-lap
        assert "out-lap" in b._speak_qualifying_engineer().lower()

        _write_lap(db, live_sid, 1, 140000, is_out=True)
        b._drive_live_qualifying()          # flying
        assert "commit" in b._speak_qualifying_engineer().lower()

        _write_lap(db, live_sid, 2, 90000)
        b._drive_live_qualifying()          # PB
        assert "personal best" in b._speak_qualifying_engineer().lower()
        assert any(src == "qualifying_engineer" for _t, src in spoken)
    finally:
        _dispose(shell, qapp)
