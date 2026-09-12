"""Anchor each corner to a place on the earth instead of to a ruler that stretches.

**Corner identity is unstable because it is keyed to lap distance, and lap
distance is the unreliable channel.** Over 307 Monza laps the integrated
distance ranged from 203 m to 11,187 m; there is a gate that discards any lap
disagreeing with the session median by more than 2%. A corner window written as
"1,972 m to 2,018 m" is anchored to a ruler that stretches, so the apex appears
to move even when the car does not.

The packet carries world coordinates, and they do not stretch. Measured across
Monza's 50 sessions spanning 13 days, two clean laps overlay to a **median
1.01 m** with the bounding boxes agreeing to 2.6 m on a 1,256 x 2,164 m track -
and that residual is racing line, not origin drift. `CLAUDE.md` 3.3 names this
approach `track-map` and calls it preferred, and `corner_model.SOURCE_TRACK_MAP`
has existed as a constant since the model was written.

This tool measures the case before anything is changed. For each corner it
reports the apex scatter **both ways** - in lap distance, as the archive keys it
today, and in world coordinates. If the second is not materially tighter there
is no case and nothing should be rewired.

    python tools/build_track_map.py --circuit fuji-international-speedway-full-course
    python tools/build_track_map.py --event 6
    python tools/build_track_map.py --event 6 --apply     # store the world anchors

Read-only without `--apply`.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store  # noqa: E402

# A lap whose frames are too sparse cannot place an apex. The same floor the
# derivation uses, for the same reason.
MIN_FRAMES = 500


def _traces(store, circuit_key: str):
    """Clean laps at this circuit, as (distance, x, z, speed) per frame."""
    rows = store._query(
        "SELECT l.id, l.session_id, l.lap_num FROM laps l "
        "JOIN sessions s ON s.id = l.session_id "
        "JOIN setup_sheets sh ON sh.id = s.setup_sheet_id "
        "WHERE sh.circuit_key = ? AND l.lap_time_ms > 0 "
        "AND COALESCE(l.off_track_s, 0) = 0 AND COALESCE(l.spin_s, 0) = 0 "
        "AND COALESCE(l.is_pit_lap, 0) = 0 AND COALESCE(l.is_out_lap, 0) = 0",
        (circuit_key,))
    out = []
    for row in rows:
        try:
            frames = store.get_lap_frames(row["id"])["frames"]
        except Exception:                                    # noqa: BLE001
            continue
        if isinstance(frames, list):
            seq = [(f.get("lap_distance_m"), f.get("pos_x"), f.get("pos_z"),
                    f.get("speed_kph")) for f in frames]
        else:
            n = len(frames.get("pos_x") or [])
            seq = [(frames["lap_distance_m"][i], frames["pos_x"][i],
                    frames["pos_z"][i], frames["speed_kph"][i])
                   for i in range(n)]
        seq = [t for t in seq if None not in t and not any(
            isinstance(v, float) and math.isnan(v) for v in t)]
        if len(seq) >= MIN_FRAMES:
            out.append(seq)
    return out


def _apex(seq, start_m: float, end_m: float):
    """The slowest frame inside this corner's window, as (distance, x, z)."""
    best = None
    for d, x, z, v in seq:
        if not start_m <= d <= end_m:
            continue
        if best is None or v < best[0]:
            best = (v, d, x, z)
    return None if best is None else (best[1], best[2], best[3])


def _spread(points):
    """Median distance of each point from the group's median centre."""
    if len(points) < 3:
        return None, None, None
    cx = statistics.median(p[0] for p in points)
    cz = statistics.median(p[1] for p in points)
    d = sorted(math.hypot(x - cx, z - cz) for x, z in points)
    return (cx, cz), d[len(d) // 2], d[int(len(d) * 0.9)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--circuit")
    ap.add_argument("--event", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    store = Store()
    try:
        circuit = args.circuit
        if args.event and not circuit:
            found = store._query(
                "SELECT DISTINCT sh.circuit_key c FROM sessions s "
                "JOIN setup_sheets sh ON sh.id = s.setup_sheet_id "
                "WHERE s.event_id = ? AND sh.circuit_key IS NOT NULL",
                (args.event,))
            circuit = found[0]["c"] if found else None
        if not circuit:
            print("need --circuit, or an --event that resolves one")
            return 2

        model = store.get_corner_model(circuit)
        if model is None:
            print(f"no corner model stored for {circuit}")
            return 2

        traces = _traces(store, circuit)
        print(f"\n{circuit}")
        print(f"model v{model.version} ({model.source}), {len(model.corners)} "
              f"corners, {len(traces)} clean laps\n")
        if len(traces) < 3:
            print("too few clean laps to anchor anything")
            return 1

        print(f"{'corner':7} {'laps':>5} {'lap-dist sd':>12} "
              f"{'world med':>10} {'world p90':>10}   verdict")
        anchors = {}
        for corner in model.corners:
            found = [_apex(t, corner.start_m, corner.end_m) for t in traces]
            found = [f for f in found if f is not None]
            if len(found) < 3:
                print(f"  {corner.id:<5} {len(found):>5}   too few apexes")
                continue
            ds = [f[0] for f in found]
            mean = sum(ds) / len(ds)
            sd_m = math.sqrt(sum((d - mean) ** 2 for d in ds) / len(ds))
            centre, med, p90 = _spread([(f[1], f[2]) for f in found])
            better = med is not None and med < sd_m
            print(f"  {corner.id:<5} {len(found):>5} {sd_m:12.1f} "
                  f"{med:10.2f} {p90:10.2f}   "
                  f"{'world is tighter' if better else 'no improvement'}")
            if centre:
                anchors[corner.id] = {"apex_x": round(centre[0], 2),
                                      "apex_z": round(centre[1], 2),
                                      "world_sd_m": round(med, 2),
                                      "laps": len(found)}

        if not anchors:
            print("\nnothing anchored")
            return 1

        worlds = [a["world_sd_m"] for a in anchors.values()]
        print(f"\nworld-space apex scatter: median {statistics.median(worlds):.2f} m "
              f"across {len(anchors)} corners")

        if args.apply:
            payload = json.loads(store._query(
                "SELECT corners_json FROM corner_models WHERE circuit_key = ?",
                (circuit,))[0]["corners_json"])
            corners = (payload["corners"] if isinstance(payload, dict)
                       and "corners" in payload else payload)
            for corner in corners:
                if corner["id"] in anchors:
                    corner.update(anchors[corner["id"]])
            if isinstance(payload, dict) and "corners" in payload:
                payload["corners"] = corners
            else:
                payload = corners
            # **The source is written too, and only when it is true.**
            # This updated `corners_json` and never `source`, so a
            # world-anchored model still exported as `auto-segment` - the one
            # declaration `CLAUDE.md` §3.2 requires it to make, and the whole
            # basis on which `refusals.md` says corner names may not be used.
            # **Partially anchored is not a track map**: a model with any
            # corner still derived from speed minima carries the weaker
            # source, because the export declares one source for the model.
            loose = [corner["id"] for corner in corners
                     if corner["id"] not in anchors]
            source = "auto-segment" if loose else "track-map"
            with store._write() as conn:
                conn.execute(
                    "UPDATE corner_models SET corners_json = ?, source = ?, "
                    "updated_at = datetime('now') WHERE circuit_key = ?",
                    (json.dumps(payload), source, circuit))
            print(f"world anchors written for {len(anchors)} corners; "
                  + (f"source is now `track-map`" if not loose else
                     f"source stays `auto-segment` - {len(loose)} corner(s) "
                     f"still derived: {', '.join(map(str, loose[:6]))}"))
        else:
            print("Nothing written. Re-run with --apply.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
