"""Program 3 Phase J — J1 canonical evidence scoping + J2 event isolation.

Certifies, through the REAL SessionDB + the REAL resolver/stale-guard (no mocks that
bypass the repository boundary), that evidence is scoped to the exact authorised
context and that a wrong event/session can never leak into it.
"""

import pytest

from data.session_db import SessionDB
from data.ids import new_id
from strategy.active_cycle_resolution import (
    resolve_active_cycle, CycleCandidate, ActiveCycleResolutionState as S,
)
from strategy.live_restart_recovery import is_stale_snapshot
from strategy.ptt_interaction import PttInteractionRecord


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


# --------------------------------------------------------------------------- #
# J1 — canonical evidence scoping
# --------------------------------------------------------------------------- #

def test_j1_latest_session_is_event_scoped(tmp_path):
    db = _db(tmp_path)
    a = db.open_session(1, "Monza", "Practice", event_id=5)
    db.write_lap(a, 1, 92_000, 2.0, None)
    b = db.open_session(1, "Monza", "Practice", event_id=9)   # ONLY event_id differs
    db.write_lap(b, 1, 91_000, 2.0, None)
    # exact-event evidence never crosses events
    assert db.get_latest_session_for_event(5) == a
    assert db.get_latest_session_for_event(9) == b


def test_j1_runs_revisions_ptt_are_event_scoped(tmp_path):
    db = _db(tmp_path)
    sa = db.open_session(1, "Fuji", "Race", event_id=5)
    sb = db.open_session(1, "Fuji", "Race", event_id=9)
    ra, rb = db.get_run_for_session(sa)["run_id"], db.get_run_for_session(sb)["run_id"]
    db.append_strategy_revision(session_run_id=ra, event_id=5, trigger="pre_race", plan_json="{}")
    db.append_strategy_revision(session_run_id=rb, event_id=9, trigger="pre_race", plan_json="{}")
    db.record_ptt_interaction(PttInteractionRecord(event_id=5, session_run_id=ra,
                                                   recognised_action="rain").as_dict())

    assert {r["run_id"] for r in db.get_session_runs_for_event(5)} == {ra}
    assert {r["session_run_id"] for r in db.get_strategy_revisions_for_event(5)} == {ra}
    assert all(p["event_id"] == 5 for p in db.get_ptt_interactions(event_id=5))
    assert db.get_ptt_interactions(event_id=9) == []            # none leaked


def test_j1_laps_are_session_scoped(tmp_path):
    db = _db(tmp_path)
    a = db.open_session(1, "Fuji", "Race", event_id=5)
    db.write_lap(a, 1, 90_000, 2.0, None)
    db.write_lap(a, 2, 89_900, 2.0, None)
    b = db.open_session(1, "Fuji", "Race", event_id=5)
    db.write_lap(b, 1, 91_000, 2.0, None)
    assert db.count_valid_laps(a) == 2 and db.count_valid_laps(b) == 1
    assert len(db.get_laps_for_scoring(a)) == 2                 # only this session's laps


# --------------------------------------------------------------------------- #
# J2 — event isolation (metamorphic / adversarial)
# --------------------------------------------------------------------------- #

def test_j2_changing_only_event_id_prevents_cross_event_reuse(tmp_path):
    db = _db(tmp_path)
    a = db.open_session(1, "Monza", "Practice", event_id=5)
    db.write_lap(a, 1, 92_000, 2.0, None)
    # a metamorphic clone that differs ONLY in event_id
    b = db.open_session(1, "Monza", "Practice", event_id=6)
    db.write_lap(b, 1, 92_000, 2.0, None)
    assert db.get_latest_session_for_event(5) != db.get_latest_session_for_event(6)
    assert db.get_latest_session_for_event(6) == b             # never event 5's row


def test_j2_changing_only_run_preserves_history_but_not_active_ownership(tmp_path):
    db = _db(tmp_path)
    # one plan, two actual runs — distinct, never merged
    r1 = db.create_session_run(session_plan_id="plan-1", session_type="practice", status="complete")
    r2 = db.create_session_run(session_plan_id="plan-1", session_type="practice", status="recording")
    assert r1 != r2
    runs = db.get_runs_for_plan("plan-1")
    assert {x["run_id"] for x in runs} == {r1, r2}             # both preserved
    # the failed/old run does not own the active state of the other
    assert db.get_session_run(r1)["status"] == "complete"
    assert db.get_session_run(r2)["status"] == "recording"


def test_j2_stale_worker_is_rejected(tmp_path):
    # a worker built for one (event, activity) must not write into a different one
    assert is_stale_snapshot(snapshot_event="ev-A", snapshot_activity="run-1",
                             current_event="ev-B", current_activity="run-1") is True
    assert is_stale_snapshot(snapshot_event="ev-A", snapshot_activity="run-1",
                             current_event="ev-A", current_activity="run-2") is True
    assert is_stale_snapshot(snapshot_event="ev-A", snapshot_activity="run-1",
                             current_event="ev-A", current_activity="run-1") is False


def test_j2_no_latest_row_wins_for_active_event(tmp_path):
    # two non-terminal cycles + no explicit selection → the resolver refuses to guess
    cands = [CycleCandidate(cycle_id="c1", explicit_state=""),
             CycleCandidate(cycle_id="c2", explicit_state="")]
    res = resolve_active_cycle(cands, selected_cycle_id="", now_date="2026-08-01")
    assert res.state == S.EVENT_REQUIRES_SELECTION
    assert res.resolved_cycle_id == ""


def test_j2_completed_or_abandoned_cannot_become_active(tmp_path):
    cands = [CycleCandidate(cycle_id="c1", explicit_state="complete"),
             CycleCandidate(cycle_id="c2", explicit_state="abandoned")]
    res = resolve_active_cycle(cands, selected_cycle_id="", now_date="2026-08-01")
    assert res.state == S.NO_ACTIVE_EVENT
    assert res.resolved_cycle_id == ""


def test_j2_quarantined_records_excluded_from_event_scoped_evidence(tmp_path):
    db = _db(tmp_path)
    # a legacy session with no event (event_id 0) is AMBIGUOUS → quarantined
    import sqlite3
    from data.session_db import _DDL
    p = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(p)
    conn.executescript(_DDL)
    conn.execute("INSERT INTO sessions(id, event_id, date_utc) VALUES(1, 0, '2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO lap_records(session_id, lap_num, lap_time_ms) VALUES(1,1,90000)")
    conn.execute("PRAGMA user_version=31")
    conn.commit(); conn.close()
    ldb = SessionDB(p)
    assert ldb.is_session_quarantined(1) is True
    # a quarantined (event-less) session never surfaces as any real event's evidence
    assert ldb.get_latest_session_for_event(0) == 0
    assert ldb.get_session_runs_for_event(5) == []
