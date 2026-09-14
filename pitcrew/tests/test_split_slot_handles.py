"""Splitting a gap handle that named a board slot back into its cars.

`tools/split_slot_handles.py` re-reads the recording because nothing in
`gap_reads` says who was really on the row - so what is pinned here is what it
refuses: a missing database, a missing recording, a reading whose row changed
around it, and a database that moved since the dry run. The recording itself
is replaced by boards whose ids are given; `test_board_identity_s176.py` is
the test against real frames.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

from pitcrew.store.db import Store

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tool():
    sys.path.insert(0, str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location(
        "split_slot_handles", ROOT / "tools" / "split_slot_handles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["split_slot_handles"] = module
    spec.loader.exec_module(module)
    return module


def bits(seed):
    return np.random.default_rng(seed).random((16, 64)) > 0.6


@pytest.fixture
def archive(tmp_path):
    """Session 1 with a recording on file and four readings under '78'."""
    db = tmp_path / "pitcrew.db"
    store = Store(db)
    store.save_driver("Rocky", bits(1))
    store.close()
    video = tmp_path / "race.mp4"
    video.write_bytes(b"")
    conn = sqlite3.connect(db)
    with conn:
        conn.execute("INSERT INTO sessions (id, event_id, kind, started_at, "
                     "video_path, video_started_at) VALUES (1, 1, 'race', "
                     "'2026-09-14T20:00:00', ?, '2026-09-14T20:00:00')",
                     (str(video),))
        for rid, side, at_s in ((1, "ahead", 10.0), (2, "ahead", 20.0),
                                (3, "behind", 30.0), (4, "ahead", 40.0)):
            conn.execute("INSERT INTO gap_reads (id, session_id, lap, side, "
                         "gap_s, at_s, position, subject, recorded_at) VALUES "
                         "(?, 1, 1, ?, 1.5, ?, 6, '78', 'x')",
                         (rid, side, at_s))
        conn.execute("INSERT INTO gap_reads (id, session_id, lap, side, gap_s, "
                     "at_s, position, subject, recorded_at) VALUES "
                     "(5, 1, 1, 'ahead', 1.5, 10.0, 6, 'Rocky', 'x')")
    conn.close()
    return db


def boards_for(tool, roster):
    """Video seconds -> boards. Our row is index 1 of three.

    10 s: Rocky above us on 9/10/11. 20 s: an unnamed car on 19/20/21.
    30 s: the same unnamed car BELOW us on 29/30/31. 40 s: Rocky on 39, the
    unnamed car on 40 - a pass inside the window.
    """
    unnamed = bits(7)
    own = bits(3)
    out = {}

    def board(above, below):
        ids = roster.see_frame([above, own, below])
        return tool.Board(own=1, ids=ids)

    for s in (9, 10, 11):
        out[s] = board(bits(1), bits(9))
    for s in (19, 20, 21):
        out[s] = board(unnamed, bits(9))
    for s in (29, 30, 31):
        out[s] = board(bits(9), unnamed)
    out[39] = board(bits(1), bits(9))
    for s in (40, 41):
        out[s] = board(unnamed, bits(9))
    return out


@pytest.fixture
def planned(tool, archive, monkeypatch):
    monkeypatch.setattr(tool, "monotonic_offset",
                        lambda db, sid: (72000.0, 71999.9, 72000.1, 72000.0))
    monkeypatch.setattr(tool, "walk",
                        lambda video, start, end, roster, cache=None:
                        boards_for(tool, roster))
    return archive


def subjects(db):
    conn = sqlite3.connect(db)
    try:
        return dict(conn.execute("SELECT id, subject FROM gap_reads"))
    finally:
        conn.close()


def test_apply_refuses_a_database_that_does_not_exist(tool, tmp_path, capsys):
    missing = tmp_path / "nope" / "pitcrew.db"
    assert tool.main(["--session", "1", "--handles", "78", "--apply",
                      "--db", str(missing)]) == 2
    assert "refusing" in capsys.readouterr().out
    assert not missing.exists() and not missing.parent.exists()


def test_apply_without_a_named_database_is_refused(tool, capsys):
    assert tool.main(["--session", "1", "--handles", "78", "--apply"]) == 2
    assert "--db" in capsys.readouterr().out


def test_no_recording_is_listed_and_left_alone(tool, archive, capsys):
    conn = sqlite3.connect(archive)
    with conn:
        conn.execute("UPDATE sessions SET video_path = 'C:/gone.mp4'")
    conn.close()
    before = subjects(archive)
    assert tool.main(["--session", "1", "--handles", "78", "--apply",
                      "--db", str(archive)]) == 0
    assert "no recording on file" in capsys.readouterr().out
    assert subjects(archive) == before


def test_the_dry_run_splits_by_what_the_row_read_and_writes_nothing(
        tool, planned, capsys):
    before = planned.read_bytes()
    assert tool.main(["--session", "1", "--handles", "78",
                      "--db", str(planned)]) == 0
    out = capsys.readouterr().out
    assert "'78': 4 gap readings -> 2 cars, 1 unknown" in out
    assert "Rocky" in out and "78.1" in out
    assert "--apply --db" in out
    assert planned.read_bytes() == before


def test_apply_reattributes_marks_and_logs_every_row(tool, planned):
    assert tool.main(["--session", "1", "--handles", "78", "--apply",
                      "--db", str(planned)]) == 0
    # The same unnamed car on both sides is one label; a pass inside the
    # window is unknown, never the car of a neighbouring second.
    assert subjects(planned) == {1: "Rocky", 2: "78.1", 3: "78.1", 4: None,
                                 5: "Rocky"}
    conn = sqlite3.connect(planned)
    try:
        repairs = conn.execute(
            "SELECT row_id, field, old_value, new_value, reason, resolved_by "
            "FROM identity_repairs WHERE table_name = 'gap_reads' "
            "ORDER BY CAST(row_id AS INTEGER)").fetchall()
    finally:
        conn.close()
    assert [(r[0], r[2], r[3]) for r in repairs] == [
        ("1", "78", "Rocky"), ("2", "78", "78.1"), ("3", "78", "78.1"),
        ("4", "78", None)]
    assert all(r[1] == "subject" and r[5] == tool.RESOLVED_BY for r in repairs)
    assert "changed within" in repairs[3][4]


def test_a_database_that_moved_since_the_plan_gets_nothing(tool, planned):
    conn = sqlite3.connect(f"file:{planned.as_posix()}?mode=ro", uri=True)
    plan = tool.plan_session(conn, 1, ["78"], None)
    conn.close()
    conn = sqlite3.connect(planned)
    with conn:
        conn.execute("UPDATE gap_reads SET subject = 'Someone' WHERE id = 3")
    conn.close()
    with pytest.raises(RuntimeError, match="nothing was written"):
        tool.apply(planned, [plan])
    assert subjects(planned)[1] == "78"
    conn = sqlite3.connect(planned)
    try:
        assert conn.execute("SELECT COUNT(*) FROM identity_repairs WHERE "
                            "table_name = 'gap_reads'").fetchone()[0] == 0
    finally:
        conn.close()


def test_all_takes_every_subject_and_leaves_a_right_one_alone(tool, planned,
                                                               capsys):
    """Reading 5 was filed as Rocky and the row read Rocky: unchanged, and
    not logged. The sticky lookup ran for named drivers too, so `--all`
    re-derives them rather than trusting a name."""
    assert tool.main(["--session", "1", "--all", "--apply",
                      "--db", str(planned)]) == 0
    assert "'Rocky': 1 gap readings -> 1 cars, 0 unknown, 1 unchanged" in \
        capsys.readouterr().out
    assert subjects(planned)[5] == "Rocky"
    conn = sqlite3.connect(planned)
    try:
        logged = {r[0] for r in conn.execute(
            "SELECT row_id FROM identity_repairs WHERE table_name = "
            "'gap_reads'")}
    finally:
        conn.close()
    assert "5" not in logged and logged == {"1", "2", "3", "4"}


def test_a_cached_chunk_comes_back_bit_for_bit(tool, tmp_path):
    rows = {10: (1, [bits(1), None, bits(2)]), 11: (None, [])}
    path = tmp_path / "rows.npz"
    tool.save_chunk(path, rows)
    back = tool.load_chunk(path)
    assert set(back) == {10, 11}
    assert back[11] == (None, [])
    own, names = back[10]
    assert own == 1 and names[1] is None
    assert (names[0] == bits(1)).all() and (names[2] == bits(2)).all()
