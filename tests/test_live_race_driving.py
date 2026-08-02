"""Live Activation 3 — telemetry → race coordinator driving (end-to-end, offline).

Drives the REAL LiveShellBridge reconciliation (_drive_live_race) against a real SessionDB seeded
with the full spine + an approved race plan + a fake window that simulates GT7 telemetry
(connection + live session id + race/pit phase + completed laps). Proves: the app activates from
the PLANNED race activity (never from telemetry), requires a coherent race plan, adopts the live
session as one canonical run, drives the race phase machine off the canonical race-state edges +
completed laps, counts pit stops, survives disconnect/reconnect, blocks honestly on a missing
race plan or incomplete context, does not activate on a practice activity, and finalises on record.
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
    """Minimal tracker exposing the canonical race-state signals the race driving reads."""
    def __init__(self, phase="idle", pit_phase="not_in_pit"):
        self.phase = phase
        self.pit_phase = pit_phase
        self.race_type = "lap"


class _FakeWindow:
    def __init__(self, live_sid, car_id, connected=True, phase="idle"):
        self._dispatcher = _Dispatcher()
        self._dispatcher._session_id = live_sid
        self._car_id = car_id
        self._connected = connected
        self._tracker = _FakeTracker(phase)

    def _build_session_context(self):
        return types.SimpleNamespace(connected=self._connected)

    def _current_car_id(self):
        return self._car_id


def _seed_db(tmp_path, *, car_id=333, event_id=42, with_revisions=True,
             activity_type="race", with_plan=True, plan=None):
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
    if with_plan:
        db.save_approved_strategy("cyc-1", plan or {"candidate_id": "plan-1", "name": "1-stop"})
    live_sid = db.open_session(car_id, "Fuji", "Race", car_name="GT-R", event_id=event_id)
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
    db.write_lap(sid, lap_num, ms, 0.0, None, event_id=42, session_type="Race",
                 is_out_lap=is_out, is_pit_lap=is_pit)


def test_activation_adopts_live_session_and_records_laps(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="idle")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        assert b._live_race is not None and b._live_race.is_recording
        run = db.get_run_for_session(live_sid)
        assert run is not None and b._live_race.run_id == run["run_id"]
        assert run["session_plan_id"] == "cyc-1::race::1"
        assert b._live_race.phase == "waiting"

        # lights out: idle → racing
        win._tracker.phase = "racing"
        b._drive_live_race()
        assert b._live_race.phase == "race_start"

        # a racing lap
        _write_lap(db, live_sid, 1, 95000)
        b._drive_live_race()
        assert b._live_race.phase == "racing" and b._live_race.completed_laps == 1

        # pit sequence: racing → in_pit → racing counts one stop
        win._tracker.phase = "in_pit"
        b._drive_live_race()
        assert b._live_race.phase == "pit_entry"
        win._tracker.phase = "racing"
        b._drive_live_race()
        assert b._live_race.pit_stops_completed == 1
    finally:
        _dispose(shell, qapp)


def test_missing_race_plan_blocks_activation(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path, with_plan=False)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        assert b._live_race is None
        assert "race plan" in b._live_race_block.lower()
    finally:
        _dispose(shell, qapp)


def test_practice_activity_does_not_activate_race(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path, activity_type="baseline_practice")
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        assert b._live_race is None
    finally:
        _dispose(shell, qapp)


def test_missing_context_blocks_activation_with_reason(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path, with_revisions=False)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        assert b._live_race is None
        assert ("car_spec_revision_id" in b._live_race_block
                or "driver_profile_version_id" in b._live_race_block)
    finally:
        _dispose(shell, qapp)


def test_disconnect_then_reconnect_resumes_same_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        run_id = b._live_race.run_id
        win._connected = False
        b._drive_live_race()
        assert b._live_race.state.value == "disconnected"
        win._connected = True
        b._drive_live_race()
        assert b._live_race.is_recording and b._live_race.run_id == run_id
    finally:
        _dispose(shell, qapp)


def test_reconnect_does_not_duplicate_laps(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        _write_lap(db, live_sid, 1, 95000)
        _write_lap(db, live_sid, 2, 94000)
        b._drive_live_race()
        assert b._live_race.completed_laps == 2
        # drop + resume; the same laps must not be re-finalised
        win._connected = False
        b._drive_live_race()
        win._connected = True
        b._drive_live_race()
        b._drive_live_race()
        assert b._live_race.completed_laps == 2
        assert b._live_race.last_finalised_lap == 2
    finally:
        _dispose(shell, qapp)


def test_diagnostics_report_race_identity(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        _write_lap(db, live_sid, 1, 95000)
        b._drive_live_race()
        d = b.live_race_diagnostics()
        assert d["active"] and d["session_type"] == "race"
        assert d["completed_laps"] == 1
        assert d["race_plan_id"] == "plan-1"
        assert d["session_plan_id"] == "cyc-1::race::1"
        assert "Lap 1" in d["headline"]
    finally:
        _dispose(shell, qapp)


def test_record_finalises_the_race_run(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        _write_lap(db, live_sid, 1, 95000)
        b._drive_live_race()
        b._on_record_run()
        assert b._live_race.state.value == "completed"
        assert b._live_race.phase == "finished"
        assert db.get_session_run(b._live_race.run_id)["status"] == "completed"
    finally:
        _dispose(shell, qapp)


def test_race_ptt_answers_from_bridge(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="racing")
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()
        # A bounded intent returns an honest answer (may be "unknown" with the minimal fake tracker),
        # never an exception; an unsupported intent is honestly refused.
        ans = b.answer_race_ptt("fuel")
        assert isinstance(ans, str) and ans
        refusal = b.answer_race_ptt("what's the airspeed of a swallow")
        assert "only answer" in refusal.lower()
        # repeat echoes the previous answer
        laps_ans = b.answer_race_ptt("laps_remaining")
        assert b.answer_race_ptt("repeat") == laps_ans
    finally:
        _dispose(shell, qapp)


def test_race_engineer_speaks_on_phase_edges(qapp, tmp_path):
    db, live_sid = _seed_db(tmp_path)
    spoken: list = []

    class _Announcer:
        def announce(self, text, priority, source):
            spoken.append((text, source))

    win = _FakeWindow(live_sid, car_id=333, connected=True, phase="idle")
    win._announcer = _Announcer()
    shell, b = _bridge(qapp, db, win)
    try:
        b._drive_live_race()                 # waiting
        assert "grid" in b._speak_race_engineer().lower()
        assert b._speak_race_engineer() == ""   # same phase → silent (anti-chatter)
        win._tracker.phase = "racing"
        b._drive_live_race()                 # race_start
        assert "lights out" in b._speak_race_engineer().lower()
        assert any(src == "race_engineer" for _t, src in spoken)
    finally:
        _dispose(shell, qapp)
