"""Live Activation 1 — telemetry → coordinator driving (end-to-end, offline).

Drives the REAL LiveShellBridge reconciliation (_drive_live_practice) against a real SessionDB
seeded with the full spine + a fake window that simulates GT7 telemetry (connection + live
session id + completed laps). Proves: the app activates from the PLANNED session (never from
telemetry), adopts the live session as one canonical run, feeds completed laps, survives a
disconnect/reconnect, blocks honestly on missing context, and finalises on record.
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


class _FakeWindow:
    """Minimal window with the telemetry hooks the driving reads."""
    def __init__(self, live_sid, car_id, connected=True):
        self._dispatcher = _Dispatcher()
        self._dispatcher._session_id = live_sid
        self._car_id = car_id
        self._connected = connected

    def _build_session_context(self):
        return types.SimpleNamespace(connected=self._connected)

    def _current_car_id(self):
        return self._car_id


def _seed_db(tmp_path, *, car_id=333, event_id=42, with_revisions=True):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    db.upsert_preparation_cycle({
        "cycle_id": "cyc-1", "event_id": event_id, "event_name": "Cup R3", "track": "Fuji",
        "car": "GT-R", "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
        "explicit_state": "active"})
    db.upsert_preparation_activity({
        "activity_id": "cyc-1::baseline_practice::1", "cycle_id": "cyc-1",
        "activity_type": "baseline_practice", "order_index": 0, "state": "in_progress"})
    if with_revisions:
        db.add_car_spec_revision(car_id=car_id, car_name="GT-R", event_id=event_id, label="base")
        db.append_driver_profile_version(version_label="v1", reason="seed")
    # the live telemetry session the dispatcher "opened" (creates the canonical run + stint + ctx)
    live_sid = db.open_session(car_id, "Fuji", "Practice", car_name="GT-R", event_id=event_id)
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


def _write_lap(db, sid, lap_num, ms, *, is_pit=False):
    db.write_lap(sid, lap_num, ms, 0.0, None, event_id=42, session_type="Practice", is_pit_lap=is_pit)


def test_activation_adopts_live_session_and_feeds_laps(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True)
    shell, b = _bridge(qapp, db, win)
    try:
        # telemetry connected + a planned practice activity open → activate, adopting live_sid
        b._drive_live_practice()
        assert b._live_practice is not None
        assert b._live_practice.is_recording
        # ONE canonical run for the live session (adopted, not a second one)
        run = db.get_run_for_session(live_sid)
        assert run is not None and b._live_practice.run_id == run["run_id"]
        assert run["session_plan_id"] == "cyc-1::baseline_practice::1"

        # two completed laps land in the DB (the "telemetry") → next tick feeds them
        _write_lap(db, live_sid, 1, 91000)
        _write_lap(db, live_sid, 2, 89000)
        b._drive_live_practice()
        assert b._live_practice.valid_lap_count == 2

        # a pit lap records but does not count
        _write_lap(db, live_sid, 3, 130000, is_pit=True)
        b._drive_live_practice()
        assert b._live_practice.valid_lap_count == 2
        assert b._live_practice.invalid_lap_count == 1
    finally:
        _dispose(shell, qapp)


def test_disconnect_then_reconnect_resumes_same_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_practice()
        run_id = b._live_practice.run_id
        _write_lap(db, live_sid, 1, 90000)
        b._drive_live_practice()

        win._connected = False                       # telemetry drops
        b._drive_live_practice()
        assert b._live_practice.state.value == "disconnected"

        win._connected = True                        # same session returns
        b._drive_live_practice()
        assert b._live_practice.is_recording and b._live_practice.run_id == run_id
    finally:
        _dispose(shell, qapp)


def test_missing_context_blocks_activation_with_reason(qapp, tmp_path):
    # no car-spec / driver-profile revisions → required context unresolved → BLOCKED, no run
    db, live_sid = _seed_db(tmp_path, with_revisions=False)
    win = _FakeWindow(live_sid, car_id=333, connected=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_practice()
        assert b._live_practice is None
        assert "car_spec_revision_id" in b._live_practice_block or \
               "driver_profile_version_id" in b._live_practice_block
    finally:
        _dispose(shell, qapp)


def test_record_finalises_the_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True)
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_practice()
        _write_lap(db, live_sid, 1, 90000)
        b._drive_live_practice()
        b._on_record_run()
        assert b._live_practice.state.value == "completed"
        assert db.get_session_run(b._live_practice.run_id)["status"] == "completed"
    finally:
        _dispose(shell, qapp)
