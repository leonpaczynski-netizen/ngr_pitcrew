"""Engineering Brain Phase 7 — Qt-free view-model tests for the live monitor."""
import pytest

from data.session_db import SessionDB
from ui import live_engineering_vm as vm


@pytest.fixture
def result():
    db = SessionDB(":memory:")
    sid = 400
    for i in range(1, 8):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)", (sid, 7, "Fuji", i, 95000))
    db._conn.commit()
    occ = lambda lap: {"session_id": sid, "setup_checkpoint_id": "", "lap_number": lap,
                       "segment_id": "T1", "corner_phase": "apex",
                       "issue_type": "understeer", "axle": "front",
                       "severity": 0.6, "confidence": 0.8}
    db.save_issue_occurrences(7, "Fuji", "", [occ(n) for n in (5, 6, 7)])  # worsening
    return db.build_live_engineering_state(sid, car_id=7, track="Fuji",
                                           scope_fingerprint="A", discipline="race")


def test_health_rows_present(result):
    rows = vm.health_summary_rows(result["live_state"])
    keys = {k for k, _ in rows}
    assert "Active issues" in keys and "Health" in keys


def test_issue_rows_have_all_columns(result):
    rows = vm.issue_rows(result["live_state"])
    assert rows
    assert all(len(r) == len(vm.ISSUE_TABLE_COLUMNS) for r in rows)


def test_active_rows_include_worsening_issue(result):
    rows = vm.active_issue_rows(result["live_state"])
    assert any("understeer" in r[0] for r in rows)


def test_trend_sparkline_matches_valid_window(result):
    state = result["live_state"]
    valid = state["valid_lap_numbers"]
    issue = state["issues"][0]
    spark = vm.trend_sparkline(issue, valid)
    assert len(spark) == len(valid)
    assert set(spark) <= {"▇", "·"}
    # laps 5,6,7 affected → last three glyphs are present markers
    assert spark.endswith("▇▇▇")


def test_timeline_rows_have_columns(result):
    rows = vm.timeline_rows(result)
    assert rows
    assert all(len(r) == len(vm.TIMELINE_COLUMNS) for r in rows)


def test_is_empty_on_bad_result():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": False})
    assert vm.is_empty({"ok": True, "live_state": {"issues": []},
                        "ledger": {"events": []}})


def test_band_label_is_human():
    assert "Degrading" in vm.health_band_label({"health": {"band": "degrading"}})
    assert vm.health_band_label({}) != ""
