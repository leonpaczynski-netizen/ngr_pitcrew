"""Same-setup and between-run floors for the lap-share instruments - plan rows 5.0 / 5.7.

    python tools/instrument_floors.py --car "Lamborghini Huracán GT3 '15" --circuit daytona
    python tools/instrument_floors.py --session 118 --session 119
    python tools/instrument_floors.py --car ... --circuit ... --write   # measurement rows

**Read-only unless `--write`**, and the database is opened `mode=ro` for every
read. `--write` records one measurement row per session per metric through
`Store.record_measurement` - an analysis row, which the driver has said may be
written as the work goes (14 Sep 2026).

A floor is not a verdict on the instrument. It is the first of the four checks
in `pitcrew/analysis/instrument_gate.py`; the known-answer and pinned-channel
checks still have to pass before full-throttle or braking share is quoted as
evidence about a setup change.

**What a session's laps have to be to count.** Not excluded, not an out lap, no
fuel added, under 1 s off track, and within 5 % of the session's median lap -
the last to keep a spin or a traffic lap from being read as the instrument's
noise. **Every session is assumed to be one unchanged setup**, which is not
always true (brake balance moves mid-session); until plan row 5.4a maps laps to
revisions, a floor from a session with a change in it is too wide, never too
narrow, and the output says the assumption.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.driving import read_frames  # noqa: E402
from pitcrew.analysis.resolve import circuit_key  # noqa: E402
from pitcrew.analysis.instrument_gate import (  # noqa: E402
    same_setup_floor,
)
from pitcrew.telemetry.recorder import decode_frames, repair_frames  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "data" / "pitcrew.db"
METRICS = (("full_throttle_pct", "%"), ("braking_pct", "%"), ("coast_pct", "%"))
PACE_WINDOW = 1.05


def _connect():
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sessions_for(conn, car: str | None, circuit: str | None,
                 ids: list[int]) -> list[sqlite3.Row]:
    if ids:
        marks = ",".join("?" * len(ids))
        return conn.execute(
            f"SELECT s.id, s.game_version, e.car_name, e.track, e.layout "
            f"FROM sessions s JOIN events e ON e.id = s.event_id "
            f"WHERE s.id IN ({marks}) ORDER BY s.id", ids).fetchall()
    return conn.execute(
        "SELECT s.id, s.game_version, e.car_name, e.track, e.layout "
        "FROM sessions s JOIN events e ON e.id = s.event_id "
        "WHERE e.car_name LIKE ? AND (e.track || ' ' || COALESCE(e.layout,'')) LIKE ? "
        "AND s.kind = 'practice' ORDER BY s.id",
        (f"%{car or ''}%", f"%{circuit or ''}%")).fetchall()


def lap_reads(conn, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT l.lap_num, l.lap_time_ms, l.off_track_s, l.fuel_added_l, "
        "       l.is_out_lap, f.blob, f.sample_hz "
        "FROM laps l JOIN lap_frames f ON f.lap_id = l.id "
        "WHERE l.session_id = ? AND COALESCE(l.excluded, 0) = 0 "
        "ORDER BY l.lap_num", (session_id,)).fetchall()
    times = sorted(r["lap_time_ms"] for r in rows if r["lap_time_ms"])
    median = times[len(times) // 2] if times else None
    out = []
    for r in rows:
        if (not r["lap_time_ms"] or median is None
                or r["lap_time_ms"] > median * PACE_WINDOW
                or r["is_out_lap"] or r["fuel_added_l"]
                or (r["off_track_s"] or 0.0) >= 1.0):
            continue
        read = read_frames(repair_frames(decode_frames(r["blob"]), r["sample_hz"]))
        out.append({"lap": r["lap_num"], **{m: getattr(read, m) for m, _ in METRICS}})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--car")
    parser.add_argument("--circuit")
    parser.add_argument("--session", type=int, action="append", default=[])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if not (args.session or (args.car and args.circuit)):
        parser.error("give --session, or --car and --circuit")

    conn = _connect()
    sessions = sessions_for(conn, args.car, args.circuit, args.session)
    if not sessions:
        print("no practice sessions match")
        return 1
    per_session: dict[int, list[dict]] = {}
    print("Assumes each session is one unchanged setup (plan row 5.4a not built).")
    for s in sessions:
        laps = lap_reads(conn, s["id"])
        per_session[s["id"]] = laps
        cells = []
        for metric, _ in METRICS:
            floor = same_setup_floor([lap[metric] for lap in laps])
            cells.append(f"{metric} " + (f"{floor.median:.2f}/{floor.p90:.2f}"
                                         if floor.established else "-"))
        print(f"s{s['id']} v{s['game_version']} n={len(laps):2d}  " + "  ".join(cells))

    # **No between-run floor here.** It needs runs known to share one setup,
    # and a session list across a car-state's changes would fold every
    # change's effect into the "noise". Plan row 5.4a provides the grouping.
    print("between-run floor: not computed - needs sessions known to share one "
          "setup (plan row 5.4a)")

    if args.write:
        from pitcrew.engineer.measurements import Measurement
        from pitcrew.store.db import Store
        store = Store(DB)
        written = 0
        for s in sessions:
            laps = per_session[s["id"]]
            for metric, unit in METRICS:
                values = [lap[metric] for lap in laps if lap[metric] is not None]
                floor = same_setup_floor(values)
                if not floor.established:
                    continue
                store.record_measurement(Measurement(
                    car_name=s["car_name"], metric=metric,
                    value=statistics.fmean(values), unit=unit, scope="session",
                    source="DERIVED",
                    # Derived off frames, so it has a circuit (NULL means a
                    # property of the car - `Measurement`).
                    circuit_key=circuit_key(s["track"], s["layout"]),
                    n=len(values), n_basis="clean laps",
                    noise_floor=floor.p90, floor_method=floor.method + " (p90)",
                    tool="tools/instrument_floors.py", session_ids=(s["id"],),
                    game_version=s["game_version"],
                    measured_on=date.today().isoformat(),
                    note="session assumed one unchanged setup; gate checks (c)(d) not yet run"))
                written += 1
        print(f"wrote {written} measurement rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
