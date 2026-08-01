"""Program 3 Phase B — schema v35: immutable strategy revisions + race-state snapshots.

Verifies the append-only revision chain (a replan never mutates the prior plan, it
appends a parent-chained revision; only the latest is active) and snapshot persistence.
"""

import json

from data.session_db import SessionDB


def test_tables_exist(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 35
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategy_revisions", "race_state_snapshots"} <= tables


def test_race_state_snapshots_append_only(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    s1 = db.append_race_state_snapshot(session_run_id="run-1", event_id=5, lap_number=1,
                                       trigger="lap_complete", state_json='{"fuel": 40}')
    s2 = db.append_race_state_snapshot(session_run_id="run-1", event_id=5, lap_number=4,
                                       trigger="rain", state_json='{"fuel": 25}')
    assert s1 != s2
    snaps = db.get_snapshots_for_run("run-1")
    assert [s["lap_number"] for s in snaps] == [1, 4]
    assert json.loads(snaps[1]["state_json"])["fuel"] == 25


def test_strategy_revision_chain_is_immutable(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    v1 = db.append_strategy_revision(session_run_id="run-1", event_id=5, trigger="pre_race",
                                     plan_json='{"stops": 1}', reason="baseline plan")
    v2 = db.append_strategy_revision(session_run_id="run-1", event_id=5, trigger="fuel_evidence",
                                     plan_json='{"stops": 2}', reason="fuel burn higher than planned")
    v3 = db.append_strategy_revision(session_run_id="run-1", event_id=5, trigger="rain",
                                     plan_json='{"stops": 2, "tyres": "wet"}', reason="rain reported")

    revs = db.get_strategy_revisions("run-1")
    assert [r["revision_index"] for r in revs] == [1, 2, 3]
    assert [r["revision_id"] for r in revs] == [v1, v2, v3]
    # parent chain preserved
    assert revs[0]["parent_revision_id"] == ""
    assert revs[1]["parent_revision_id"] == v1
    assert revs[2]["parent_revision_id"] == v2
    # the ORIGINAL plan is not mutated — v1 still says one stop
    assert json.loads(revs[0]["plan_json"])["stops"] == 1
    # only the latest revision is active
    active = db.get_active_strategy_revision("run-1")
    assert active["revision_id"] == v3
    assert sum(r["is_active"] for r in revs) == 1


def test_revisions_are_scoped_per_run(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    a1 = db.append_strategy_revision(session_run_id="run-A", event_id=1, plan_json="{}")
    b1 = db.append_strategy_revision(session_run_id="run-B", event_id=2, plan_json="{}")
    assert db.get_active_strategy_revision("run-A")["revision_id"] == a1
    assert db.get_active_strategy_revision("run-B")["revision_id"] == b1
    assert len(db.get_strategy_revisions("run-A")) == 1  # runs don't bleed together
