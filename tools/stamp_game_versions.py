"""Backfill the GT7 version onto sessions recorded before the column existed.

    python tools/stamp_game_versions.py --before 2026-08-20 --was 1.70 --since 1.71
    python tools/stamp_game_versions.py --before 2026-08-20 --was 1.70 --since 1.71 --apply

**Why this exists.** `sessions.game_version` was added on 21 Aug 2026, the day
after update 1.71 reworked GT7's tyre model, per-car steering geometry, damper
attenuation and the adjustment ranges of suspension, differential and aero.
Until then the version was resolved from the event or from settings, and
neither can be right across a patch: event 1 holds 44 sessions spanning 11 to
21 August, so whichever single value it carries is wrong for one side of the
20th.

**Every version is passed in, none is assumed.** The script will not guess what
was installed on any date - that is the driver's knowledge, not the database's.
`--since` is optional precisely because "what am I on now" is a question only he
can answer, and leaving it out stamps only the sessions whose version is known
from the past and leaves the recent ones NULL for him to set deliberately.

**NULL is a legitimate outcome and is left alone.** A session that says nothing
about its version is honest. One that reports the version installed after it
was recorded is not, and is the failure this whole change exists to stop.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.paths import DATA_DIR                           # noqa: E402


def _rows(conn, sql, args=()):
    conn.row_factory = sqlite3.Row
    return list(conn.execute(sql, args))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True,
                    help="ISO date of the patch, e.g. 2026-08-20. Sessions "
                         "STARTED before this get --was.")
    ap.add_argument("--was", required=True,
                    help="The version installed before that date, e.g. 1.70.")
    ap.add_argument("--since",
                    help="The version installed on and after it, e.g. 1.71. "
                         "Omit to leave post-patch sessions NULL.")
    ap.add_argument("--db", default=str(DATA_DIR / "pitcrew.db"))
    ap.add_argument("--apply", action="store_true",
                    help="Write. Without it, nothing is changed.")
    args = ap.parse_args()

    try:
        cutoff = dt.date.fromisoformat(args.before).isoformat()
    except ValueError:
        raise SystemExit(f"--before must be an ISO date, got {args.before!r}")

    conn = sqlite3.connect(args.db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)")]
    if "game_version" not in cols:
        raise SystemExit("sessions has no game_version column - run the app "
                         "once so the migration adds it, then retry.")

    before = _rows(conn, "SELECT id, event_id, kind, started_at FROM sessions "
                         "WHERE game_version IS NULL AND started_at < ? "
                         "ORDER BY id", (cutoff,))
    after = _rows(conn, "SELECT id, event_id, kind, started_at FROM sessions "
                        "WHERE game_version IS NULL AND started_at >= ? "
                        "ORDER BY id", (cutoff,))

    print(f"database: {args.db}")
    print(f"patch date: {cutoff}\n")
    print(f"  {len(before):3d} unstamped sessions before it -> {args.was}")
    for r in before[-3:]:
        print(f"        e{r['event_id']} s{r['id']:<3} {r['kind']:<8} {r['started_at']}")
    if len(before) > 3:
        print(f"        ... and {len(before) - 3} earlier")

    if args.since:
        print(f"\n  {len(after):3d} unstamped sessions on or after it -> {args.since}")
    else:
        print(f"\n  {len(after):3d} unstamped sessions on or after it -> LEFT NULL "
              f"(pass --since to stamp them)")
    for r in after:
        print(f"        e{r['event_id']} s{r['id']:<3} {r['kind']:<8} {r['started_at']}")

    # Events carrying a version that is merely misspelt. "1.7" and "1.70" are
    # the same claim written two ways, and a reader comparing strings sees two
    # different games.
    ragged = [r for r in _rows(conn, "SELECT id, name, game_version FROM events")
              if r["game_version"] and r["game_version"] != r["game_version"].strip()
              or (r["game_version"] or "").count(".") == 1
              and len((r["game_version"] or "").split(".")[1]) == 1]
    if ragged:
        print("\n  events whose version is written short:")
        for r in ragged:
            print(f"        event {r['id']}  {r['game_version']!r}  ({r['name']})")

    # **The slider register is a measurement too, and 1.71 moved endpoints.**
    # `range_records` carries a `game_version` column that nothing ever filled,
    # because the writer took it from the active event rather than from the
    # installed game - and the active event's was blank. The register therefore
    # holds the RSR's v1.71 endpoints beside the Shelby's and Huracan's v1.70
    # ones with nothing marking the difference, which matters because 1.71
    # moved the three LSD axes off a shared 5-60 onto 0-30, 0-100 and 0-99.
    regs = _rows(conn, "SELECT car_name, measured_date, game_version "
                       "FROM range_records WHERE game_version IS NULL "
                       "ORDER BY measured_date")
    if regs:
        print("\n  unstamped slider registers:")
        for r in regs:
            side = args.was if r["measured_date"] < cutoff else args.since
            print(f"        {r['measured_date']}  {r['car_name']:<34} -> "
                  f"{side or 'LEFT NULL (pass --since)'}")

    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    with conn:
        conn.execute("UPDATE sessions SET game_version = ? "
                     "WHERE game_version IS NULL AND started_at < ?",
                     (args.was, cutoff))
        if args.since:
            conn.execute("UPDATE sessions SET game_version = ? "
                         "WHERE game_version IS NULL AND started_at >= ?",
                         (args.since, cutoff))
        for r in regs:
            side = args.was if r["measured_date"] < cutoff else args.since
            if side:
                conn.execute("UPDATE range_records SET game_version = ? "
                             "WHERE car_name = ?", (side, r["car_name"]))
        for r in ragged:
            fixed = r["game_version"].strip()
            if fixed.count(".") == 1 and len(fixed.split(".")[1]) == 1:
                fixed = f"{fixed}0"
            conn.execute("UPDATE events SET game_version = ? WHERE id = ?",
                         (fixed, r["id"]))
    stamped = sum(1 for r in regs
                  if (args.was if r["measured_date"] < cutoff else args.since))
    print(f"\nwritten: {len(before)} sessions before, "
          f"{len(after) if args.since else 0} sessions after, "
          f"{stamped} registers, {len(ragged)} events tidied.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
