"""Re-judge the opening lap of every stored session as an out-lap, or not.

    python tools/flag_out_laps.py                     # report, change nothing
    python tools/flag_out_laps.py --sessions 113-124  # a range, or 113,114
    python tools/flag_out_laps.py --apply             # back up, then write

**Why this exists.** The live flag came from a pit EXIT, and a pit exit needs
a pit ENTRY first - which a lap that begins already in the pit box never has.
So the opening lap of every lobby session reached the database as
`is_out_lap = 0`: twelve Daytona sessions in a row, five of them 91-95 s
against a 104 s lap, and `min(lap_time_ms)` over the event returned a
pit-exit-to-line fragment nobody drove as a lap. The rule that fixes it for
sessions recorded from now on is `pitcrew.analysis.runs.opening_lap_verdict`;
this applies THAT rule - imported, not restated - to what is already on disk.

**It only ever sets the flag.** No lap is deleted, no time is rewritten, no
aggregate is recomputed, and a flag that is already set is never cleared, by
this tool or by the rule - a `1` on an opening lap is either the driver's or
the detector's, and both outrank a re-reading. Where the rule cannot say
(`None`), the row is left exactly as it was: missing is left missing, never
guessed (CLAUDE.md rule 3).

The dry run opens the database READ-ONLY and touches nothing. `--apply` copies
`pitcrew.db` (and its `-wal`/`-shm` siblings, where present) to
`pitcrew.db.bak-before-out-laps-<YYYYMMDD-HHMMSS>` first, then writes through
`Store.set_lap_flags`.

The unit is the session's first lap only. The out-lap AFTER a stop is
`tools/reaggregate.py`'s job, and the two do not overlap.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pitcrew.analysis.runs import OpeningLap, opening_lap_verdict    # noqa: E402
from pitcrew.store.db import DEFAULT_DB_PATH                          # noqa: E402
from pitcrew.telemetry.recorder import (                              # noqa: E402
    FRAME_FIELDS,
    decode_frames,
    standing_start_ms,
)

SET = "SET"                  # stored 0, rule says out-lap: the one write
KEPT = "already flagged"     # stored 1, rule agrees
NOT_OUT = "not an out-lap"   # stored 0, rule agrees
CANNOT_SAY = "left as is"    # rule cannot say; the row is not touched
DISAGREES = "stored 1, rule says not - left (this tool never clears)"


@dataclass(frozen=True)
class Finding:
    session_id: int
    kind: str
    practice_mode: str | None
    lap_id: int
    lap_num: int
    lap_time_ms: int
    stored: bool
    standing_start_ms: int | None
    standing_source: str        # "column", "frames", or "none"
    verdict: OpeningLap

    @property
    def action(self) -> str:
        if self.verdict.is_out_lap is None:
            return CANNOT_SAY
        if self.verdict.is_out_lap:
            return KEPT if self.stored else SET
        return DISAGREES if self.stored else NOT_OUT

    @property
    def writes(self) -> bool:
        return self.action == SET

    def describe(self) -> str:
        standing = ("no frames" if self.standing_start_ms is None
                    else f"{self.standing_start_ms / 1000:.1f} s at rest"
                    + (" (from frames)" if self.standing_source == "frames"
                       else ""))
        return (f"s{self.session_id} {self.kind} "
                f"{self.practice_mode or 'undeclared'} "
                f"lap {self.lap_num} {self.lap_time_ms / 1000:.3f} s "
                f"stored={int(self.stored)} {standing}"
                f"\n      -> {self.action}: {self.verdict.reason}")


def _parse_sessions(spec: str | None) -> set[int] | None:
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


def _standing_from_frames(conn: sqlite3.Connection, lap_id: int) -> int | None:
    """`standing_start_ms` re-read off the stored frames, by the recorder's
    own function - so a lap recorded before the column existed is judged by
    the same threshold as one recorded after."""
    row = conn.execute(
        "SELECT blob, sample_hz FROM lap_frames WHERE lap_id = ?",
        (lap_id,)).fetchone()
    if row is None:
        return None
    frames = decode_frames(row["blob"])
    rows = [[frame.get(name) for name in FRAME_FIELDS] for frame in frames]
    return standing_start_ms(rows, row["sample_hz"] or 60.0)


def read_findings(conn: sqlite3.Connection,
                  sessions: set[int] | None) -> list[Finding]:
    rows = conn.execute(
        "SELECT laps.id AS lap_id, laps.session_id, laps.lap_num, "
        "       laps.lap_time_ms, laps.is_out_lap, laps.standing_start_ms, "
        "       sessions.kind, sessions.practice_mode "
        "FROM laps JOIN sessions ON sessions.id = laps.session_id "
        "WHERE laps.lap_num = 1 "
        "ORDER BY laps.session_id").fetchall()
    findings = []
    for row in rows:
        if sessions is not None and row["session_id"] not in sessions:
            continue
        standing = row["standing_start_ms"]
        source = "column"
        if standing is None:
            standing = _standing_from_frames(conn, row["lap_id"])
            source = "frames" if standing is not None else "none"
        verdict = opening_lap_verdict(
            session_kind=row["kind"],
            practice_mode=row["practice_mode"],
            standing_start_ms=standing)
        findings.append(Finding(
            session_id=row["session_id"], kind=row["kind"],
            practice_mode=row["practice_mode"], lap_id=row["lap_id"],
            lap_num=row["lap_num"], lap_time_ms=row["lap_time_ms"],
            stored=bool(row["is_out_lap"]), standing_start_ms=standing,
            standing_source=source, verdict=verdict))
    return findings


def back_up(db_path: Path) -> Path:
    """Copy the database and its WAL/SHM siblings, named the way every other
    pre-migration backup in `data/` is named."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name(f"{db_path.name}.bak-before-out-laps-{stamp}")
    shutil.copy2(db_path, target)
    for suffix in ("-wal", "-shm"):
        sibling = db_path.with_name(db_path.name + suffix)
        if sibling.exists():
            shutil.copy2(sibling, target.with_name(target.name + suffix))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--sessions", default=None,
                        help="restrict the report to these session ids: "
                             "'113-124' or '113,114,120'")
    parser.add_argument("--apply", action="store_true",
                        help="back the database up, then write the flags; "
                             "without it, report only")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No database at {db_path}.")
        return 1
    sessions = _parse_sessions(args.sessions)

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        findings = read_findings(conn, sessions)
    finally:
        conn.close()

    if not findings:
        print("No opening laps to judge.")
        return 0

    for finding in findings:
        print(" ", finding.describe())
    tally: dict[str, int] = {}
    for finding in findings:
        tally[finding.action] = tally.get(finding.action, 0) + 1
    print()
    for action, count in sorted(tally.items(), key=lambda item: -item[1]):
        print(f"  {count:3d}  {action}")
    to_write = [f for f in findings if f.writes]

    if not args.apply:
        print(f"\nNothing written. {len(to_write)} flag(s) would be set; "
              f"re-run with --apply.")
        return 0
    if not to_write:
        print("\nNothing to write.")
        return 0

    backup = back_up(db_path)
    print(f"\nBacked up to {backup}")
    from pitcrew.store.db import Store
    store = Store(db_path)
    try:
        for finding in to_write:
            store.set_lap_flags(finding.lap_id, is_out_lap=1)
    finally:
        store.close()
    print(f"Set is_out_lap = 1 on {len(to_write)} lap(s) in {db_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
