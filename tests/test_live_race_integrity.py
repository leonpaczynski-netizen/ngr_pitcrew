"""Live Activation 3 — post-session race integrity audit (pure) + the bridge quarantine gate."""
from __future__ import annotations

import os
import types

import pytest

from strategy.live_race_integrity import IntegritySeverity, audit_race_session

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _run(**over):
    r = dict(run_id="run-1", session_id=1, event_id="42", session_type="Race",
             session_plan_id="cyc-1::race::1", status="completed")
    r.update(over)
    return r


def _laps(n=3):
    return [{"lap_num": i, "lap_time_ms": 95000 + i} for i in range(1, n + 1)]


def _expected(**over):
    e = dict(event_id="42", car_id="333", track_id="fuji", layout_id="gp", session_type="race")
    e.update(over)
    return e


# ================================ pure audit =================================
def test_coherent_race_is_promotable():
    rep = audit_race_session(run=_run(), laps=_laps(), expected=_expected())
    assert rep.ok and rep.promotion_allowed and rep.laps_checked == 3
    assert not rep.blockers


def test_invalid_run_id_blocks():
    rep = audit_race_session(run=_run(run_id="0"), laps=_laps(), expected=_expected())
    assert not rep.promotion_allowed
    assert any(i.code == "invalid_run_id" for i in rep.blockers)


def test_broken_session_link_blocks():
    rep = audit_race_session(run=_run(session_id=0), laps=_laps(), expected=_expected())
    assert any(i.code == "broken_session_link" for i in rep.blockers)


def test_wrong_session_type_blocks():
    rep = audit_race_session(run=_run(session_type="Qualifying"), laps=_laps(), expected=_expected())
    assert not rep.promotion_allowed
    assert any(i.code == "wrong_session_type" for i in rep.blockers)


def test_event_mismatch_blocks():
    rep = audit_race_session(run=_run(event_id="99"), laps=_laps(), expected=_expected())
    assert any(i.code == "event_mismatch" for i in rep.blockers)


def test_placeholder_car_blocks():
    rep = audit_race_session(run=_run(), laps=_laps(), expected=_expected(car_id="0"))
    assert any(i.code == "invalid_car_id" for i in rep.blockers)


def test_duplicate_lap_number_blocks():
    laps = _laps() + [{"lap_num": 2, "lap_time_ms": 94000}]
    rep = audit_race_session(run=_run(), laps=laps, expected=_expected())
    assert not rep.promotion_allowed
    assert any(i.code == "duplicate_lap_number" for i in rep.blockers)


def test_contradictory_car_blocks():
    rep = audit_race_session(run=_run(), laps=_laps(), expected=_expected(),
                             session={"car_id": "999", "track": "fuji"})
    assert any(i.code == "contradictory_car" for i in rep.blockers)


def test_contradictory_track_blocks():
    rep = audit_race_session(run=_run(), laps=_laps(), expected=_expected(),
                             session={"car_id": "333", "track": "spa"})
    assert any(i.code == "contradictory_track" for i in rep.blockers)


def test_orphan_run_is_limitation_not_blocker():
    rep = audit_race_session(run=_run(), laps=[], expected=_expected())
    assert rep.ok  # no blocker
    assert not rep.promotion_allowed  # ...but nothing to promote
    assert any(i.code == "orphan_run" and i.severity == IntegritySeverity.LIMITATION
               for i in rep.issues)


def test_zero_length_lap_is_limitation():
    laps = [{"lap_num": 1, "lap_time_ms": 95000}, {"lap_num": 2, "lap_time_ms": 0}]
    rep = audit_race_session(run=_run(), laps=laps, expected=_expected())
    assert rep.promotion_allowed  # one valid lap present; zero-length is only a limitation
    assert any(i.code == "zero_length_laps" for i in rep.limitations)


def test_unknown_layout_is_limitation():
    rep = audit_race_session(run=_run(), laps=_laps(), expected=_expected(layout_id=""))
    assert rep.promotion_allowed
    assert any(i.code == "unknown_layout" for i in rep.limitations)


def test_never_raises_on_garbage():
    rep = audit_race_session(run=None, laps=None, expected=None)
    assert not rep.promotion_allowed  # invalid everything → blocked, but no exception


# ========================= bridge quarantine gate ============================
@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _race_bridge(qapp, tmp_path):
    from data.session_db import SessionDB
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell

    db = SessionDB(str(tmp_path / "s.db"))
    db.upsert_preparation_cycle({"cycle_id": "cyc-1", "event_id": 42, "event_name": "R", "track": "Fuji",
                                 "car": "GT-R", "official_race_date": "2026-06-21",
                                 "format_profile_id": "multiweek", "explicit_state": "active"})
    db.upsert_preparation_activity({"activity_id": "cyc-1::race::1", "cycle_id": "cyc-1",
                                    "activity_type": "race", "order_index": 0, "state": "in_progress"})
    db.add_car_spec_revision(car_id=333, car_name="GT-R", event_id=42, label="base")
    db.append_driver_profile_version(version_label="v1", reason="seed")
    db.save_approved_strategy("cyc-1", {"candidate_id": "plan-1"})
    live_sid = db.open_session(333, "Fuji", "Race", car_name="GT-R", event_id=42)

    win = types.SimpleNamespace(
        _dispatcher=types.SimpleNamespace(_session_id=live_sid), _car_id=333, _connected=True,
        _tracker=types.SimpleNamespace(phase="racing", pit_phase="not_in_pit", race_type="lap"),
        _build_session_context=lambda: types.SimpleNamespace(connected=True),
        _current_car_id=lambda: 333)

    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=win, config={"active_cycle_id": "cyc-1"}, db=db,
                        spawn=lambda fn: fn())
    return db, live_sid, shell, b


def test_bridge_quarantines_empty_race_session(qapp, tmp_path):
    """A race that recorded no laps is finalised as history but held — nothing to promote."""
    db, live_sid, shell, b = _race_bridge(qapp, tmp_path)
    try:
        b._drive_live_race()
        assert b._live_race is not None and b._live_race.is_recording
        b._on_record_run()                       # no laps written
        rep = b.race_session_integrity()
        assert rep and not rep["promotion_allowed"]
        assert any(i["code"] == "orphan_run" for i in rep["issues"])
        assert b._live_race.state.value == "completed"   # finalised (history), not deleted
    finally:
        shell.close(); shell.deleteLater(); qapp.processEvents()


def test_bridge_promotes_coherent_race_session(qapp, tmp_path):
    """A coherent race with real laps passes the audit and is promotable."""
    db, live_sid, shell, b = _race_bridge(qapp, tmp_path)
    try:
        b._drive_live_race()
        db.write_lap(live_sid, 1, 95000, 0.0, None, event_id=42, session_type="Race")
        db.write_lap(live_sid, 2, 94000, 0.0, None, event_id=42, session_type="Race")
        b._drive_live_race()
        b._on_record_run()
        rep = b.race_session_integrity()
        assert rep and rep["promotion_allowed"] and rep["laps_checked"] == 2
    finally:
        shell.close(); shell.deleteLater(); qapp.processEvents()
