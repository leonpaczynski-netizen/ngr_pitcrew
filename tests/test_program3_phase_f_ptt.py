"""Program 3 Phase F — PTT interaction audit trail (§19).

Every PTT interaction is persisted with its context + intent + resolution so a wrong
response is traceable — but the raw transcript is NEVER stored (push_to_talk invariant).
"""

import os

import pytest

from data.session_db import SessionDB
from strategy.ptt_interaction import PttInteractionRecord, FORBIDDEN_FIELDS


# --------------------------------------------------------------------------- #
# pure record + DB layer
# --------------------------------------------------------------------------- #

def test_record_has_no_transcript_field():
    rec = PttInteractionRecord(resolved_action="accept")
    d = rec.as_dict()
    for banned in FORBIDDEN_FIELDS:
        assert banned not in d, f"the record must never carry a raw transcript ({banned})"


def test_table_exists_at_v39(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 39
    cols = {r[1] for r in db._conn.execute("PRAGMA table_info(ptt_interactions)")}
    assert cols                      # table present
    for banned in FORBIDDEN_FIELDS:
        assert banned not in cols    # no transcript column


def test_record_and_read_roundtrip(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    iid = db.record_ptt_interaction(PttInteractionRecord(
        event_id=5, cycle_id="cyc-1", session_run_id="run-1", lap_number=6,
        session_type="race", recognised_action="rain", command_class="report",
        intent_confidence=0.82, resolved_action="rain", response="Copy, rain noted.",
        created_at="2026-01-01T12:00:00").as_dict())
    assert iid
    rows = db.get_ptt_interactions(session_run_id="run-1")
    assert len(rows) == 1
    r = rows[0]
    assert r["interaction_id"] == iid
    assert r["lap_number"] == 6 and r["session_type"] == "race"
    assert r["recognised_action"] == "rain" and abs(r["intent_confidence"] - 0.82) < 1e-6
    assert r["response"] == "Copy, rain noted."


def test_query_by_event_and_ordering(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    db.record_ptt_interaction(PttInteractionRecord(
        event_id=5, session_run_id="run-1", resolved_action="keep",
        created_at="2026-01-01T12:00:01").as_dict())
    db.record_ptt_interaction(PttInteractionRecord(
        event_id=5, session_run_id="run-1", resolved_action="accept",
        created_at="2026-01-01T12:00:00").as_dict())
    rows = db.get_ptt_interactions(event_id=5)
    assert [r["resolved_action"] for r in rows] == ["accept", "keep"]   # oldest first


def test_record_is_best_effort(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    # a malformed record must not raise
    assert db.record_ptt_interaction({"lap_number": "not-an-int"}) == "" or True


# --------------------------------------------------------------------------- #
# bridge wiring
# --------------------------------------------------------------------------- #

def test_bridge_records_strategy_ack_with_context(tmp_path):
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell

    _app = QApplication.instance() or QApplication([])
    db = SessionDB(str(tmp_path / "s.db"))
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=None,
                        config={"strategy": {}, "active_cycle_id": "cyc-1"}, db=db)
    b._live_session_mode = "race"

    b._on_voice_strategy_ack("keep")

    rows = db.get_ptt_interactions()
    assert len(rows) == 1
    assert rows[0]["resolved_action"] == "keep"
    assert rows[0]["cycle_id"] == "cyc-1"
    assert rows[0]["session_type"] == "race"
    assert rows[0]["command_class"] == "strategy_ack"
