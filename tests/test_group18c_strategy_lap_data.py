"""Tests for Group 18C — get_strategy_lap_data() on SessionDB.

Covers:
  1. DB-only: both compounds returned from DB
  2. UI-only: car_id=0 skips DB, returns ui_table_data
  3. Gap fill: DB compound + UI compound merged
  4. DB precedence: DB value wins when compound appears in both
  5. session_id=0: laps from multiple sessions are returned
  6. Both empty: car_id with no laps and empty ui_table_data returns {}
  7. Per-compound DB precedence: DB list length wins over UI list length
  8. Unknown session_id: no DB rows found; ui_table_data returned as-is
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    d = SessionDB(":memory:")
    yield d
    d.close()


def _open(db: SessionDB, car_id: int = 1, track: str = "Trial Mountain") -> int:
    return db.open_session(car_id, track, "race")


# ---------------------------------------------------------------------------
# Test 1 — DB-only
# ---------------------------------------------------------------------------

def test_db_only(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="Soft")
    db.write_lap(sid, 2, 96000, 3.0, None, compound="Soft")
    db.write_lap(sid, 3, 98000, 3.0, None, compound="Medium")

    result = db.get_strategy_lap_data(1, "Trial Mountain", sid, {})

    assert set(result.keys()) == {"Soft", "Medium"}
    assert result["Soft"] == [95000.0, 96000.0]
    assert result["Medium"] == [98000.0]


# ---------------------------------------------------------------------------
# Test 2 — UI-only (car_id=0 skips DB)
# ---------------------------------------------------------------------------

def test_ui_only(db):
    ui = {"Hard": [100000.0, 101000.0]}
    result = db.get_strategy_lap_data(0, "Trial Mountain", 0, ui)
    assert result == {"Hard": [100000.0, 101000.0]}


# ---------------------------------------------------------------------------
# Test 3 — Gap fill: DB has Soft, UI has Hard
# ---------------------------------------------------------------------------

def test_gap_fill(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="Soft")

    result = db.get_strategy_lap_data(1, "Trial Mountain", sid, {"Hard": [100000.0]})

    assert "Soft" in result
    assert "Hard" in result
    assert result["Soft"] == [95000.0]
    assert result["Hard"] == [100000.0]


# ---------------------------------------------------------------------------
# Test 4 — DB precedence: DB wins when same compound in both
# ---------------------------------------------------------------------------

def test_db_precedence(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="Soft")
    db.write_lap(sid, 2, 96000, 3.0, None, compound="Soft")

    result = db.get_strategy_lap_data(
        1, "Trial Mountain", sid, {"Soft": [99000.0]}
    )

    assert result["Soft"] == [95000.0, 96000.0]


# ---------------------------------------------------------------------------
# Test 5 — session_id=0: laps from all sessions returned
# ---------------------------------------------------------------------------

def test_session_id_zero_returns_all_sessions(db):
    sid1 = _open(db)
    db.write_lap(sid1, 1, 95000, 3.0, None, compound="Soft")

    sid2 = _open(db)
    db.write_lap(sid2, 1, 96000, 3.0, None, compound="Soft")

    result = db.get_strategy_lap_data(1, "Trial Mountain", 0, {})

    # Both session laps should be present (2 laps for Soft)
    assert "Soft" in result
    assert len(result["Soft"]) == 2


# ---------------------------------------------------------------------------
# Test 6 — Both empty: car_id with no laps and empty ui_table_data
# ---------------------------------------------------------------------------

def test_both_empty(db):
    result = db.get_strategy_lap_data(999, "Trial Mountain", 0, {})
    assert result == {}


# ---------------------------------------------------------------------------
# Test 7 — Per-compound DB precedence: DB list length beats UI list length
# ---------------------------------------------------------------------------

def test_db_compound_list_length_wins(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="SH")
    db.write_lap(sid, 2, 96000, 3.0, None, compound="SH")
    db.write_lap(sid, 3, 97000, 3.0, None, compound="SH")

    result = db.get_strategy_lap_data(
        1, "Trial Mountain", sid, {"SH": [99000.0, 100000.0]}
    )

    assert len(result["SH"]) == 3
    assert result["SH"] == [95000.0, 96000.0, 97000.0]


# ---------------------------------------------------------------------------
# Test 8 — Unknown session_id: DB returns nothing, ui_table_data returned
# ---------------------------------------------------------------------------

def test_unknown_session_id_falls_back_to_ui(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="Soft")

    # session_id=999 doesn't exist
    result = db.get_strategy_lap_data(
        1, "Trial Mountain", 999, {"Hard": [100000.0]}
    )

    assert "Soft" not in result
    assert result.get("Hard") == [100000.0]


# ---------------------------------------------------------------------------
# Test 9 — AC5: blank-compound laps in DB are excluded (via
#           get_compound_lap_sequences which filters compound != '')
# ---------------------------------------------------------------------------

def test_blank_compound_laps_excluded(db):
    sid = _open(db)
    db.write_lap(sid, 1, 95000, 3.0, None, compound="Soft")
    db.write_lap(sid, 2, 97000, 3.0, None, compound="")   # blank — must be excluded

    result = db.get_strategy_lap_data(1, "Trial Mountain", sid, {})

    assert set(result.keys()) == {"Soft"}
    assert result["Soft"] == [95000.0]
    # The blank-compound lap's time (97000) must not appear in any list
    all_times = [t for ts in result.values() for t in ts]
    assert 97000.0 not in all_times
