"""Restore laps GT7 counted and the app did not.

    python tools/repair_dropped_laps.py --session 88            # report only
    python tools/repair_dropped_laps.py --session 88 --gt7-time 114972 --apply
    python tools/repair_dropped_laps.py --all                   # survey the archive

**GT7 takes the car over at pit entry, and the start/finish crossing inside
that sequence never reaches the app.** So a stop whose pit lane spans the line
produces two of the game's laps and one of the app's rows. Fuji, 24 Aug 2026,
session 88: 19 rows for a 20-lap race, row 5 spanning 256.2 s of a 141.3 s
"lap", every row after it dated one lap early, and the race never registering
as finished.

**The witness has been in the archive the whole time.** `laps.laps_completed`
is GT7's own counter, stamped on every row and read by nothing. Across
session 88 it steps by one on every row except row 5, where it steps 5 -> 7.
That difference is the dropped lap, and it needs no video to find.

Four things are wrong and this repairs all four:

* the row count is short by one, so anything dividing consumed life by laps
  run divides by 19 instead of 20 - a 5.3% overstatement at Fuji;
* every row after the stop carries a lap number one too low;
* the surviving row's frames cover two laps, so its corner windows, its lap
  distance and its own duration all disagree with its `lap_time_ms`;
* the lap GT7 timed has no row at all.

The frames are not lost - they are the second half of a two-lap blob - so the
blob is split at the boundary rather than a frameless row being invented. The
first lap keeps its own frames and the second is re-stamped from zero.

**Read-only until `--apply`, and it refuses to run twice**: a session whose
counter already steps by one everywhere has nothing to repair.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import DEFAULT_DB_PATH, Store          # noqa: E402
from pitcrew.telemetry.recorder import (                     # noqa: E402
    FRAME_FIELDS,
    FRAME_SCHEMA_VERSION,
    _VERSION_KEY,
    decode_frames,
    encode_frames,
)


class Drop:
    """One place a session lost a crossing, and what it costs."""

    def __init__(self, row: dict, before: dict, missing: int) -> None:
        self.row = row
        self.before = before
        self.missing = missing

    def __str__(self) -> str:
        return (f"row {self.row['lap_num']} (id {self.row['id']}): GT7's "
                f"counter steps {self.before['laps_completed']} -> "
                f"{self.row['laps_completed']}, so {self.missing} crossing(s) "
                f"went missing inside it")


def drops(laps: list[dict]) -> list[Drop]:
    """Every row across which GT7 counted more laps than the app filed.

    Silent where the column is null: a session recorded before the counter was
    stored is unknown, not clean. Saying nothing about it is the honest
    answer, and saying "no drops" would not be.
    """
    found = []
    for before, row in zip(laps, laps[1:]):
        here, prior = row.get("laps_completed"), before.get("laps_completed")
        if here is None or prior is None:
            continue
        if here - prior > 1:
            found.append(Drop(row, before, here - prior - 1))
    return found


def split_frames(store: Store, lap_id: int, at_ms: int):
    """The blob's two halves, and the second re-stamped from zero.

    Returns `(head_rows, tail_rows, sample_hz, version)` in `FRAME_FIELDS` order,
    ready for `encode_frames`.

    **The version is carried across.** Re-encoding a lap without its original
    stamp moves the analysis's yaw source underneath it; `encode_frames` has
    the whole account of what that cost the last time it happened.
    """
    raw = store._query("SELECT * FROM lap_frames WHERE lap_id = ?", (lap_id,))
    if not raw:
        return None
    row = raw[0]
    decoded = decode_frames(row["blob"])
    if not decoded:
        return None
    version = int(decoded[0].get(_VERSION_KEY, FRAME_SCHEMA_VERSION))

    head, tail = [], []
    for frame in decoded:
        t = frame.get("t_ms")
        if t is None:
            continue
        (head if t < at_ms else tail).append(frame)
    if not head or not tail:
        return None

    def as_rows(frames, rebase: int):
        out = []
        for frame in frames:
            values = [frame.get(name) for name in FRAME_FIELDS]
            values[FRAME_FIELDS.index("t_ms")] = frame["t_ms"] - rebase
            out.append(values)
        return out

    return as_rows(head, 0), as_rows(tail, at_ms), row["sample_hz"], version


def report(store: Store, session_id: int) -> list[Drop]:
    laps = store.list_laps(session_id)
    if not laps:
        raise SystemExit(f"session {session_id} has no laps")
    found = drops(laps)
    counted = sum(d.missing for d in found)
    print(f"session {session_id}: {len(laps)} rows filed, "
          f"{len(laps) + counted} laps counted by GT7")
    if not found:
        print("  GT7's counter steps by one on every row - nothing to repair")
        return found
    for drop in found:
        print(f"  {drop}")
        meta = store.frames_meta(drop.row["id"])
        if meta and meta["frame_count"] and meta["sample_hz"]:
            span = meta["frame_count"] / meta["sample_hz"]
            print(f"      its frames span {span:.1f} s against a stated "
                  f"lap time of {drop.row['lap_time_ms'] / 1000:.3f} s")
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db")
    ap.add_argument("--session", type=int)
    ap.add_argument("--all", action="store_true",
                    help="survey every session and change nothing")
    ap.add_argument("--gt7-time", type=int,
                    help="the missing lap's time in ms, from GT7's own lap "
                         "list. Required for --apply: the app never timed "
                         "this lap, so the figure cannot come from the "
                         "archive, and a lap time this tool invented would "
                         "be indistinguishable from one the game reported")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()

    if args.all:
        rows = store._query(
            "SELECT DISTINCT session_id FROM laps ORDER BY session_id")
        total = 0
        for row in rows:
            found = drops(store.list_laps(row["session_id"]))
            if found:
                total += 1
                print(f"session {row['session_id']}: "
                      f"{sum(d.missing for d in found)} lap(s) dropped")
        print(f"\n{total} session(s) carry a dropped lap")
        return 0

    if args.session is None:
        raise SystemExit("--session or --all")

    found = report(store, args.session)
    if not found or not args.apply:
        if found:
            print("\nreport only - pass --apply (with --gt7-time) to repair")
        return 0

    if len(found) > 1:
        raise SystemExit(
            "more than one drop in this session, and each needs its own "
            "measured lap time - repair them one at a time")
    if args.gt7_time is None:
        raise SystemExit(
            "--gt7-time is required: the app never timed the missing lap, so "
            "its duration has to come from GT7's own lap list (the replay's "
            "on-screen times), not from this tool")

    drop = found[0]
    if drop.missing != 1:
        raise SystemExit(f"{drop.missing} laps went missing here; this "
                         f"repairs one")

    split = split_frames(store, drop.row["id"], args.gt7_time)
    if split is None:
        raise SystemExit(
            f"the blob for lap id {drop.row['id']} does not split at "
            f"{args.gt7_time} ms - check the time against GT7's lap list")
    head, tail, sample_hz, version = split

    laps = store.list_laps(args.session)
    after = [r for r in laps if r["lap_num"] >= drop.row["lap_num"]]
    print(f"\nrepairing session {args.session}:")
    print(f"  splitting {len(head) + len(tail)} frames at "
          f"{args.gt7_time} ms -> {len(head)} + {len(tail)}")
    print(f"  renumbering {len(after)} row(s) from "
          f"{drop.row['lap_num']} to {drop.row['lap_num'] + 1}")

    with store._write() as conn:
        # Descending, because `laps` is UNIQUE(session_id, lap_num) and an
        # ascending pass would collide with the row it has not moved yet.
        for row in sorted(after, key=lambda r: -r["lap_num"]):
            conn.execute("UPDATE laps SET lap_num = ? WHERE id = ?",
                         (row["lap_num"] + 1, row["id"]))
            conn.execute("UPDATE grip_observations SET lap_num = ? "
                         "WHERE lap_id = ?", (row["lap_num"] + 1, row["id"]))

        # The surviving row keeps the SECOND lap - it is the one its
        # `lap_time_ms`, its fuel and its wear reading all describe.
        conn.execute(
            "UPDATE lap_frames SET blob = ?, frame_count = ? WHERE lap_id = ?",
            (encode_frames(tail, version=version), len(tail), drop.row["id"]))

        # And the lap GT7 timed gets its row back, with the first half of the
        # frames. Everything the app never measured for it stays null.
        cur = conn.execute(
            "INSERT INTO laps (session_id, lap_num, lap_time_ms, delta_ms, "
            "is_pit_lap, is_out_lap, laps_completed, recorded_at, "
            "exclusion_reason) VALUES (?, ?, ?, 0, 1, 0, ?, ?, ?)",
            (args.session, drop.row["lap_num"], args.gt7_time,
             drop.before["laps_completed"] + 1, drop.row["recorded_at"],
             "restored from GT7's own lap counter and lap list; the app "
             "never saw its crossing"))
        new_id = cur.lastrowid
        conn.execute(
            "INSERT INTO lap_frames (lap_id, sample_hz, frame_count, blob) "
            "VALUES (?, ?, ?, ?)",
            (new_id, sample_hz, len(head),
             encode_frames(head, version=version)))

    print(f"  restored lap {drop.row['lap_num']} as id {new_id}")
    print("\nre-run `tools/derive_grip_observations.py --apply` and "
          "`tools/reaggregate.py` for this session: the corner windows of the "
          "split laps are derived from frames that have just changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
