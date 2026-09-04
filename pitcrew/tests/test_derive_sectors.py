"""The re-derive, which is the function that can NULL 548 rows of the archive.

It had no test at all. That matters more than the usual reason: it is not a
migration, so nothing gates it on a schema version, and `--restamp` is
explicitly allowed to *retire* sector times a previous run wrote. A bug here
does not fail loudly, it quietly empties columns.

The property that makes it safe is that it is idempotent against an unchanged
catalogue — run it twice and the second run changes nothing — and that it only
retires a lap the model genuinely no longer accepts.
"""
from __future__ import annotations

import json
import zlib

import pytest

from pitcrew.analysis import lap_sectors
from pitcrew.store.db import Store
from pitcrew.store.schema import derive_sectors
from pitcrew.telemetry.recorder import FRAME_FIELDS

# **`resolve.circuit_key("Test", "Full Course")` spells it this way.**
# The catalogue, `track_layouts.slug` and the resolver all have to agree
# or the model comes back for a circuit nothing is filed under.
CIRCUIT = "test-full-course"
LENGTH = 6000.0
LAP_MS = 120_000


def _blob(count=600, lap_ms=LAP_MS, length_m=LENGTH):
    """One lap of frames in the recorder's on-disk shape."""
    index = {name: position for position, name in enumerate(FRAME_FIELDS)}
    rows = []
    step = length_m / (count - 1)
    for i in range(count):
        row = [None] * len(FRAME_FIELDS)
        row[index["t_ms"]] = round(i * lap_ms / (count - 1))
        row[index["lap_distance_m"]] = round(i * step, 2)
        row[index["pos_x"]] = round(i * step, 2)
        row[index["pos_y"]] = 0.0
        row[index["pos_z"]] = 0.0
        rows.append(row)
    payload = {"fields": list(FRAME_FIELDS), "rows": rows, "_v": 2}
    return zlib.compress(json.dumps(payload).encode())


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A database with one event, one session and two laps that carry frames.

    The catalogue is monkeypatched rather than a real circuit used, so the
    test does not move when a real entry is added or improved.
    """
    monkeypatch.setitem(
        lap_sectors.SECTOR_LINES, CIRCUIT,
        {"lines_m": (2000.0, 4000.0), "source": lap_sectors.SOURCE_LANDMARK,
         "note": "a test circuit"})
    db = Store(tmp_path / "pitcrew.db")
    with db._write() as conn:                       # noqa: SLF001 - a test
        cur = conn.execute(
            "INSERT INTO tracks (name, slug, created_at) "
            "VALUES (?,?, datetime('now'))", ("Test", "test"))
        conn.execute(
            "INSERT INTO track_layouts (track_id, layout, length_m, slug, "
            "created_at) VALUES (?,?,?,?, datetime('now'))",
            (cur.lastrowid, "Full Course", LENGTH, CIRCUIT))
    event_id = db.create_event(name="T", track="Test", layout="Full Course",
                               car_name="C")
    session_id = db.start_session(event_id, "practice")
    with db._write() as conn:                       # noqa: SLF001 - a test
        for lap_num, lap_ms in ((1, LAP_MS), (2, LAP_MS)):
            cur = conn.execute(
                "INSERT INTO laps (session_id, lap_num, lap_time_ms, "
                "recorded_at) VALUES (?,?,?, datetime('now'))",
                (session_id, lap_num, lap_ms))
            conn.execute(
                "INSERT INTO lap_frames (lap_id, sample_hz, frame_count, blob) "
                "VALUES (?,?,?,?)", (cur.lastrowid, 60.0, 600, _blob()))
    yield db
    db.close()


def _sectors(store):
    return [dict(row) for row in store._query(          # noqa: SLF001 - a test
        "SELECT lap_num, sector1_ms, sector_model FROM laps ORDER BY lap_num")]


def test_it_cuts_the_laps_it_can(store):
    with store._write() as conn:                    # noqa: SLF001 - a test
        written = derive_sectors(conn)
    assert written == 2
    rows = _sectors(store)
    assert all(row["sector1_ms"] for row in rows)
    assert all(row["sector_model"].startswith(CIRCUIT) for row in rows)


def test_running_it_twice_changes_nothing(store):
    """Idempotence is the property that makes a tool safe to run after every
    catalogue edit. Without it, the honest answer to "what would this do" is
    unavailable."""
    with store._write() as conn:                    # noqa: SLF001 - a test
        derive_sectors(conn)
    before = _sectors(store)
    with store._write() as conn:                    # noqa: SLF001 - a test
        again = derive_sectors(conn)
    assert again == 0
    assert _sectors(store) == before


def test_a_restamp_on_an_unchanged_catalogue_also_changes_nothing(store):
    """**The counter has to be honest.** With `restamp` the stamp-match skip
    is disabled, so every admissible lap is re-cut - and counting those as
    written reported "would write 548 laps" on an archive where nothing would
    change."""
    with store._write() as conn:                    # noqa: SLF001 - a test
        derive_sectors(conn)
    before = _sectors(store)
    with store._write() as conn:                    # noqa: SLF001 - a test
        again = derive_sectors(conn, restamp=True)
    assert again == 0
    assert _sectors(store) == before


def test_moving_the_lines_re_cuts_the_stored_laps(store, monkeypatch):
    """The whole reason this is not a migration: adding or improving a
    catalogue entry has to reach the laps already on disk."""
    with store._write() as conn:                    # noqa: SLF001 - a test
        derive_sectors(conn)
    was = _sectors(store)[0]

    monkeypatch.setitem(
        lap_sectors.SECTOR_LINES, CIRCUIT,
        {"lines_m": (1000.0, 5000.0), "source": lap_sectors.SOURCE_TIMING_LINE,
         "note": "moved"})
    with store._write() as conn:                    # noqa: SLF001 - a test
        written = derive_sectors(conn, restamp=True)
    assert written == 2
    now = _sectors(store)[0]
    assert now["sector1_ms"] != was["sector1_ms"]
    assert now["sector_model"] != was["sector_model"]


def test_a_restamp_retires_a_lap_the_model_no_longer_accepts(store,
                                                             monkeypatch):
    """CLAUDE.md rule 10: a rule that refuses a reading has to be able to
    refuse its own baseline, and a lap cut under a looser gate IS that
    baseline. Tightening `SPAN_RATIO` had to be able to take back the seven
    laps the old bound let through."""
    with store._write() as conn:                    # noqa: SLF001 - a test
        derive_sectors(conn)
    assert all(row["sector1_ms"] for row in _sectors(store))

    # Nothing can satisfy this, so every lap becomes inadmissible.
    monkeypatch.setattr(lap_sectors, "SPAN_RATIO", (1.5, 2.0))
    with store._write() as conn:                    # noqa: SLF001 - a test
        written = derive_sectors(conn, restamp=True)
    assert written == 2
    for row in _sectors(store):
        assert row["sector1_ms"] is None
        # **The stamp goes too.** A stamp beside three nulls would latch the
        # refusal, and nothing could ever ask again.
        assert row["sector_model"] is None


def test_without_restamp_a_stale_lap_is_left_alone(store, monkeypatch):
    """`--restamp` is the deliberate act. A plain run only fills in laps that
    have no sectors at all, so it can never take anything away."""
    with store._write() as conn:                    # noqa: SLF001 - a test
        derive_sectors(conn)
    before = _sectors(store)
    monkeypatch.setattr(lap_sectors, "SPAN_RATIO", (1.5, 2.0))
    with store._write() as conn:                    # noqa: SLF001 - a test
        assert derive_sectors(conn, restamp=True) == 2
    # Put them back, then confirm the non-restamp path re-fills rather than
    # refusing to touch a null.
    monkeypatch.undo()
    monkeypatch.setitem(
        lap_sectors.SECTOR_LINES, CIRCUIT,
        {"lines_m": (2000.0, 4000.0), "source": lap_sectors.SOURCE_LANDMARK,
         "note": "a test circuit"})
    with store._write() as conn:                    # noqa: SLF001 - a test
        assert derive_sectors(conn) == 2
    assert _sectors(store) == before


def test_a_circuit_with_no_lines_and_no_length_writes_nothing(store,
                                                              monkeypatch):
    """No catalogue entry AND no circuit length means no axis to cut on, and
    `model_for` returns None rather than inventing one."""
    monkeypatch.delitem(lap_sectors.SECTOR_LINES, CIRCUIT)
    with store._write() as conn:                    # noqa: SLF001 - a test
        conn.execute("DELETE FROM track_layouts WHERE slug = ?", (CIRCUIT,))
        conn.execute("UPDATE laps SET sector1_ms = NULL, sector2_ms = NULL, "
                     "sector3_ms = NULL, sector_model = NULL")
        assert derive_sectors(conn, restamp=True) == 0
    assert all(row["sector1_ms"] is None for row in _sectors(store))
