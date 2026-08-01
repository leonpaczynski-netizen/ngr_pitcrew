"""Program 3 Phase G — an accepted replan records an immutable strategy revision (§16-17).

Advisory only: accepting a replan via PTT snapshots the triggering race state and
appends a NEW immutable, parent-chained strategy revision referencing it. It records;
it executes nothing and mutates no live plan.
"""

import json
import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from data.session_db import SessionDB
from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell

_app = QApplication.instance() or QApplication([])


def _bridge_with_active_run(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    sid = db.open_session(333, "Fuji", "Race", event_id=5)   # C1: opens a session_run
    run = db.get_run_for_session(sid)
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=None,
                        config={"strategy": {}, "active_cycle_id": "cyc-1"}, db=db)
    b._live_session_id = lambda: sid            # stub the active recording session
    b._live_decision = {"recommendation": "REPLAN_URGENT", "fuel_remaining": 25}
    return db, b, run["run_id"]


def test_accept_records_immutable_revision_and_snapshot(tmp_path):
    db, b, run_id = _bridge_with_active_run(tmp_path)
    b._record_strategy_revision_on_accept({"stops": 2, "compound": "RM"})

    revs = db.get_strategy_revisions(run_id)
    assert len(revs) == 1
    r = revs[0]
    assert r["trigger"] == "ptt_accept" and r["is_active"] == 1
    assert json.loads(r["plan_json"])["stops"] == 2
    assert r["communicated"] == 1
    # a race-state snapshot was captured at the material moment and referenced
    snaps = db.get_snapshots_for_run(run_id)
    assert len(snaps) == 1
    assert r["race_state_snapshot_id"] == snaps[0]["snapshot_id"]
    assert snaps[0]["trigger"] == "ptt_accept"


def test_second_accept_appends_a_new_immutable_revision(tmp_path):
    db, b, run_id = _bridge_with_active_run(tmp_path)
    b._record_strategy_revision_on_accept({"stops": 1})
    b._record_strategy_revision_on_accept({"stops": 2})
    revs = db.get_strategy_revisions(run_id)
    assert [x["revision_index"] for x in revs] == [1, 2]
    # the first plan is preserved (not mutated); only the latest is active
    assert json.loads(revs[0]["plan_json"])["stops"] == 1
    assert revs[1]["parent_revision_id"] == revs[0]["revision_id"]
    assert db.get_active_strategy_revision(run_id)["revision_index"] == 2


def test_accept_branch_wires_the_revision():
    import inspect
    src = inspect.getsource(LiveShellBridge._on_voice_strategy_ack)
    assert "_record_strategy_revision_on_accept" in src


def test_no_db_is_safe(tmp_path):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=None, config={}, db=None)
    b._record_strategy_revision_on_accept({"stops": 2})   # must not raise
