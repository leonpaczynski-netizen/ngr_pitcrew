"""Make every stored in-lap and out-lap obey THE RULE, from the frames.

    python tools/repair_in_out_laps.py --db data/pitcrew.db              # report
    python tools/repair_in_out_laps.py --db data/pitcrew.db --sessions 19,108,158
    python tools/repair_in_out_laps.py --db data/pitcrew.db --apply      # write

The driver, 15 Sep 2026: *"A lap in the same session after an in lap has to
be an out lap."* On the archive it did not hold: eleven stored pit laps were
followed by a lap that was not an out-lap, because the live path put the
out-lap flag on the in-lap itself wherever the pit exit came before the next
crossing, and because some "pit laps" were never stops at all - a practice
reset, a crash, the out-lap of a stop whose line came before the box.

**What an in-lap is** lives in `pitcrew/analysis/reaggregate.py` and is read
off the frames by the one stop detector (`telemetry/pit_detect`). **What an
out-lap is** lives in `pitcrew/analysis/runs.out_lap_after_in_lap`. This tool
restates neither; it plans with `reaggregate.plan_session` and writes.

**Dry run by default.** It opens the database read-only and changes nothing.
`--apply` refuses a path that does not exist (it will not create an empty
database and report success), backs the database up with SQLite's backup API
to `<db>.bak-before-in-out-laps-<stamp>`, then writes each change guarded on
the value it read - a row something else changed in between is skipped and
reported, never overwritten. Every change is printed, and on `--apply` also
written to `<db>.in-out-laps-<stamp>.log`.

It only ever moves `is_pit_lap` and `is_out_lap`. No lap is deleted, no time
is rewritten, and an out-lap flag is never cleared.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pitcrew.analysis.reaggregate import (                  # noqa: E402
    FlagChange,
    plan_session,
    rule_violations,
)
from pitcrew.telemetry.recorder import decode_frames         # noqa: E402

LAP_COLUMNS = ("id", "session_id", "lap_num", "lap_time_ms", "is_pit_lap",
               "is_out_lap")


def parse_sessions(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    wanted: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            low, high = part.split("-", 1)
            wanted.update(range(int(low), int(high) + 1))
        elif part:
            wanted.add(int(part))
    return wanted


def read_laps(conn: sqlite3.Connection,
              sessions: set[int] | None = None) -> list[dict]:
    """Every stored lap in session and lap order, with its sample rate."""
    rows = conn.execute(
        "SELECT laps.id, laps.session_id, laps.lap_num, laps.lap_time_ms, "
        "       laps.is_pit_lap, laps.is_out_lap, lap_frames.sample_hz "
        "FROM laps LEFT JOIN lap_frames ON lap_frames.lap_id = laps.id "
        "ORDER BY laps.session_id, laps.lap_num").fetchall()
    laps = []
    for row in rows:
        lap = dict(zip(LAP_COLUMNS + ("sample_hz",), row))
        if sessions is not None and lap["session_id"] not in sessions:
            continue
        lap["sample_hz"] = lap["sample_hz"] or 60.0
        laps.append(lap)
    return laps


def frames_reader(conn: sqlite3.Connection):
    def frames_for(lap_id: int):
        row = conn.execute("SELECT blob FROM lap_frames WHERE lap_id = ?",
                           (lap_id,)).fetchone()
        return decode_frames(row[0]) if row else None
    return frames_for


def by_session(laps: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for lap in laps:
        grouped.setdefault(lap["session_id"], []).append(lap)
    return grouped


def plan(conn: sqlite3.Connection,
         sessions: set[int] | None = None) -> tuple[list[dict], list[FlagChange]]:
    laps = read_laps(conn, sessions)
    frames_for = frames_reader(conn)
    changes: list[FlagChange] = []
    for session_laps in by_session(laps).values():
        changes.extend(plan_session(session_laps, frames_for))
    return laps, changes


def applied(laps: list[dict], changes: list[FlagChange]) -> list[dict]:
    """The laps as they would read with the changes made."""
    moved = {(change.lap_id, change.column): change.target
             for change in changes}
    out = []
    for lap in laps:
        lap = dict(lap)
        for column in ("is_pit_lap", "is_out_lap"):
            if (lap["id"], column) in moved:
                lap[column] = moved[(lap["id"], column)]
        out.append(lap)
    return out


def print_violations(title: str, violations: list[tuple]) -> None:
    print(f"{title}: {len(violations)}")
    for session_id, in_lap, next_lap in violations:
        print(f"    s{session_id}: in-lap {in_lap}, lap {next_lap} not an out-lap")


def back_up(db_path: Path, stamp: str) -> Path:
    """A consistent copy through SQLite's own backup API - a file copy of a
    database in WAL mode can miss what the WAL still holds."""
    target = db_path.with_name(f"{db_path.name}.bak-before-in-out-laps-{stamp}")
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def write(db_path: Path, changes: list[FlagChange]) -> tuple[int, list[FlagChange]]:
    """Each change guarded on the value planned from; one transaction."""
    written, skipped = 0, []
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for change in changes:
                cursor = conn.execute(
                    f"UPDATE laps SET {change.column} = ? "
                    f"WHERE id = ? AND {change.column} = ?",
                    (change.target, change.lap_id, change.stored))
                if cursor.rowcount == 1:
                    written += 1
                else:
                    skipped.append(change)
    finally:
        conn.close()
    return written, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True,
                        help="the database to read, and with --apply to write")
    parser.add_argument("--sessions", default=None,
                        help="restrict to these session ids: '19,108' or '100-120'")
    parser.add_argument("--apply", action="store_true",
                        help="back up, then write; without it, report only")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"No database at {db_path} - refusing (nothing was created).")
        return 2
    sessions = parse_sessions(args.sessions)

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        laps, changes = plan(conn, sessions)
    finally:
        conn.close()

    before = rule_violations(laps)
    after = rule_violations(applied(laps, changes))
    print_violations("THE RULE broken now", before)
    print()
    for change in changes:
        print("  ", change.describe())
    print(f"\n{len(changes)} change(s) planned.")
    print_violations("THE RULE broken after the changes", after)

    if not args.apply:
        print("\nDry run: nothing written. Re-run with --apply to write.")
        return 0
    if not changes:
        print("\nNothing to write.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = back_up(db_path, stamp)
    print(f"\nBacked up to {backup}")
    written, skipped = write(db_path, changes)
    log_path = db_path.with_name(f"{db_path.name}.in-out-laps-{stamp}.log")
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(f"repair_in_out_laps {stamp} on {db_path}\n")
        handle.write(f"backup: {backup}\n")
        for change in changes:
            state = "SKIPPED (row changed since planning)" \
                if change in skipped else "written"
            handle.write(f"{state}: {change.describe()}\n")
    print(f"Wrote {written} change(s) to {db_path}; "
          f"{len(skipped)} skipped because the row had changed.")
    for change in skipped:
        print("   skipped:", change.describe())
    print(f"Log: {log_path}")
    return 0 if not skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
