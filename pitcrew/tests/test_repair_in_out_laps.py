"""The archive repair for THE RULE, on a copy of real laps - never the live file.

`tools/repair_in_out_laps.py` plans with `analysis.reaggregate.plan_session`
and writes nothing without `--apply`. Here it runs against a scratch database
holding only the laps that break the rule on the owner's archive (and the
three sessions 56bf65f changed), blobs copied byte for byte out of the live
database opened READ-ONLY. Skips where that database is absent.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pitcrew.analysis.reaggregate import rule_violations

LIVE_DB = Path("C:/Projects/VR_Dashboard/data/pitcrew.db")

needs_live_db = pytest.mark.skipif(
    not LIVE_DB.is_file(), reason="the owner's database is not on this machine")


REPAIR_LAPS = {19: [13, 14, 15], 49: [11, 12, 13, 14], 53: [13, 14, 15],
               60: [1, 2], 74: [1, 2, 3], 88: [4, 5, 6, 7], 93: [1, 2],
               108: [4, 5, 6], 149: [6, 7, 8], 158: [10, 11, 12]}


def copy_of_real_laps(target: Path) -> None:
    """A scratch database holding only these laps, blobs byte for byte."""
    from pitcrew.store.db import Store

    Store(target).close()
    source = sqlite3.connect(f"file:{LIVE_DB.as_posix()}?mode=ro", uri=True)
    dest = sqlite3.connect(target)
    try:
        dest.execute("INSERT INTO events (id, name, track, created_at, "
                     "updated_at) VALUES "
                     "(1, 'copy', 't', '2026-09-15', '2026-09-15')")
        for session_id, nums in REPAIR_LAPS.items():
            dest.execute("INSERT INTO sessions (id, event_id, kind, started_at) "
                         "VALUES (?, 1, 'practice', '2026-09-15')", (session_id,))
            for num in nums:
                row = source.execute(
                    "SELECT l.id, l.lap_time_ms, l.is_pit_lap, l.is_out_lap, "
                    "f.sample_hz, f.frame_count, f.blob, l.excluded, "
                    "l.exclusion_reason FROM laps l "
                    "JOIN lap_frames f ON f.lap_id = l.id "
                    "WHERE l.session_id = ? AND l.lap_num = ?",
                    (session_id, num)).fetchone()
                dest.execute(
                    "INSERT INTO laps (id, session_id, lap_num, lap_time_ms, "
                    "is_pit_lap, is_out_lap, excluded, exclusion_reason, "
                    "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-09-15')",
                    (row[0], session_id, num, row[1], row[2], row[3], row[7],
                     row[8]))
                dest.execute(
                    "INSERT INTO lap_frames (lap_id, sample_hz, frame_count, "
                    "blob) VALUES (?, ?, ?, ?)", (row[0], row[4], row[5], row[6]))
        dest.commit()
    finally:
        dest.close()
        source.close()


def stored_violations(db: Path) -> list[tuple]:
    from tools.repair_in_out_laps import read_laps

    conn = sqlite3.connect(db)
    try:
        return rule_violations(read_laps(conn))
    finally:
        conn.close()


@needs_live_db
def test_the_repair_takes_the_violations_to_zero_on_a_copy(tmp_path, capsys):
    from tools.repair_in_out_laps import main

    db = tmp_path / "copy.db"
    copy_of_real_laps(db)
    # Read off the stored flags: a pit row also flagged out-lap, after a lap
    # that is not an in-lap, is a row holding its own out-lap (session 53 lap
    # 14) - so session 49 lap 13, 74 lap 2 and 149 lap 7 pass here too, and it
    # takes their frames to show they are not stops at all.
    assert sorted(stored_violations(db)) == [(60, 1, 2), (88, 6, 7), (93, 1, 2)]

    assert main(["--db", str(db)]) == 0                 # dry run
    assert len(stored_violations(db)) == 3              # nothing written

    assert main(["--db", str(db), "--apply"]) == 0
    assert stored_violations(db) == []
    out = capsys.readouterr().out
    assert "s158 lap 12" not in out, "the lap after a reset is never struck"
    assert "s108 lap 6" not in out
    assert "s53 lap 15" not in out, "the row after a merged in-lap counts"

    conn = sqlite3.connect(db)
    flags = dict(((s, n), (p, o, e, r)) for s, n, p, o, e, r in conn.execute(
        "SELECT session_id, lap_num, is_pit_lap, is_out_lap, excluded, "
        "exclusion_reason FROM laps"))
    conn.close()
    assert flags[(19, 14)][:2] == (1, 1) and flags[(19, 15)][:2] == (0, 0)
    assert flags[(53, 14)][:2] == (1, 1) and flags[(53, 15)][:2] == (0, 0)
    assert flags[(158, 11)] == (0, 0, 1, "reset")
    assert flags[(158, 12)] == (0, 0, 0, None)
    assert flags[(108, 5)] == (0, 0, 1, "reset")
    assert flags[(108, 6)] == (0, 0, 0, None)
    assert flags[(49, 12)][:2] == (1, 0) and flags[(49, 13)][:2] == (0, 1)
    assert list(tmp_path.glob("copy.db.bak-before-in-out-laps-*"))


def test_apply_refuses_a_database_that_does_not_exist(tmp_path):
    from tools.repair_in_out_laps import main

    missing = tmp_path / "nope.db"
    assert main(["--db", str(missing), "--apply"]) == 2
    assert not missing.exists()
