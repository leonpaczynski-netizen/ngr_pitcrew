"""Did 1.71 change braking, and does it reward braking later?

Two different questions and they must not be answered with one number.

**What he did.** Brake point relative to the apex, and how long the brake is
held while the wheel is turned. He was deliberately moving his markers in this
session, so a change here is a driver input, not a physics measurement, and
saying otherwise would credit the patch with his experiment.

**What the tyre did.** `17` §1 measured the slipping regime under power and
found driven-wheel slip down 40-60%. The braking side is the same channel with
the sign reversed: `slip_*` is wheel surface speed over car speed, so under
brake the interesting figure is the MINIMUM - how far below rolling the wheels
get. **That one is a property of the game and not of the driver**, and it is
the thing that would actually reward braking later.

Braking events are found rather than assumed: contiguous runs of real brake
pressure, matched across laps by where on the lap they start. No corner model
is needed and none is trusted.
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                           # noqa: E402

EVENT = 1
BRAKE_ON = 20.0          # real pressure, not a brush
MIN_EVENT_FRAMES = 8     # ~130 ms at 60 Hz
MATCH_BIN_M = 250.0      # events starting within this are the same corner
TRAIL_STEER_DEG = 8.0    # turned, not straight-line braking
WHEELS = ("fl", "fr", "rl", "rr")


def braking_events(frames: list[dict]) -> list[dict]:
    out, run = [], []
    for f in frames:
        if (f.get("brake_pct") or 0) > BRAKE_ON and f.get("lap_distance_m") is not None:
            run.append(f)
        else:
            if len(run) >= MIN_EVENT_FRAMES:
                out.append(_summarise(run, frames))
            run = []
    if len(run) >= MIN_EVENT_FRAMES:
        out.append(_summarise(run, frames))
    return [e for e in out if e]


def _summarise(run: list[dict], all_frames: list[dict]) -> dict | None:
    start_d = run[0]["lap_distance_m"]
    if run[-1]["lap_distance_m"] <= start_d:
        return None

    after = [f for f in all_frames
             if f.get("lap_distance_m") is not None
             and start_d <= f["lap_distance_m"] <= start_d + 600
             and f.get("speed_kph")]
    if not after:
        return None
    apex = min(after, key=lambda f: f["speed_kph"])

    slips = []
    for f in run:
        vals = [f.get(f"slip_{w}") for w in WHEELS]
        vals = [v for v in vals if v is not None]
        if vals:
            slips.append(min(vals))
    trail = [f for f in run if abs(f.get("steering_deg") or 0) > TRAIL_STEER_DEG]

    return {
        "start_d": start_d,
        "to_apex_m": apex["lap_distance_m"] - start_d,
        "apex_kph": apex["speed_kph"],
        "peak_brake": max((f.get("brake_pct") or 0) for f in run),
        "min_slip": min(slips) if slips else None,
        "trail_frames": len(trail),
        "frames": len(run),
    }


def collect(store, version: str, limit: int) -> dict[int, list[dict]]:
    rows = store._query(
        "SELECT l.id FROM laps l JOIN sessions s ON s.id = l.session_id "
        "WHERE s.event_id = ? AND s.game_version = ? AND l.excluded = 0 "
        "  AND l.is_out_lap = 0 AND l.is_pit_lap = 0 "
        "  AND COALESCE(l.off_track_s, 0) < 2.5 AND COALESCE(l.spin_s, 0) = 0 "
        "ORDER BY l.id DESC LIMIT ?", (EVENT, version, limit))
    by_corner: dict[int, list[dict]] = defaultdict(list)
    used = 0
    for row in rows:
        stored = store.get_lap_frames(row["id"])
        if not stored:
            continue
        used += 1
        for event in braking_events(stored["frames"]):
            by_corner[int(event["start_d"] // MATCH_BIN_M)].append(event)
    print(f"  {version}: {used} laps, "
          f"{sum(len(v) for v in by_corner.values())} braking events")
    return by_corner


def med(events, key):
    vals = [e[key] for e in events if e.get(key) is not None]
    return st.median(vals) if vals else None


def main() -> int:
    store = Store()
    try:
        pre = collect(store, "1.70", 16)
        post = collect(store, "1.71", 12)
        shared = [b for b in sorted(set(pre) & set(post))
                  if len(pre[b]) >= 4 and len(post[b]) >= 3]

        print(f"\n  {len(shared)} braking zones with enough laps on both sides\n")
        print(f"  {'zone@m':>7} {'n':>7}  {'brake->apex m':>20} "
              f"{'apex km/h':>21}  {'trail %':>15}  {'min slip':>26}")
        print("  " + "-" * 104)

        deltas, slip_pre_all, slip_post_all = [], [], []
        for b in shared:
            a, z = pre[b], post[b]
            ta, tz = med(a, "to_apex_m"), med(z, "to_apex_m")
            ka, kz = med(a, "apex_kph"), med(z, "apex_kph")
            sa, sz = med(a, "min_slip"), med(z, "min_slip")
            pa = 100 * st.median([e["trail_frames"] / e["frames"] for e in a])
            pz = 100 * st.median([e["trail_frames"] / e["frames"] for e in z])
            deltas.append(tz - ta)
            if sa is not None and sz is not None:
                slip_pre_all.append(sa)
                slip_post_all.append(sz)
            slip_txt = (f"{sa:.4f} -> {sz:.4f} {sz - sa:+.4f}"
                        if sa is not None and sz is not None else "")
            print(f"  {b * MATCH_BIN_M:>7.0f} {len(a):>3}/{len(z):<3} "
                  f"{ta:>7.0f} -> {tz:<6.0f} {tz - ta:+5.0f} "
                  f"{ka:>7.1f} -> {kz:<6.1f} {kz - ka:+6.1f}  "
                  f"{pa:>5.1f} -> {pz:<5.1f}  {slip_txt:>26}")

        print(f"\n  median change in brake-to-apex distance: "
              f"{st.median(deltas):+.0f} m")
        print("    positive = braking EARLIER (longer run to the apex), "
              "negative = LATER")
        if slip_pre_all:
            print(f"\n  median minimum slip under brake: "
                  f"{st.median(slip_pre_all):.4f} -> {st.median(slip_post_all):.4f}"
                  f"  ({st.median(slip_post_all) - st.median(slip_pre_all):+.4f})")
            print("    1.0000 is rolling true. LOWER means the wheel slides "
                  "further below road speed under braking;")
            print("    HIGHER means it holds better - which is what would "
                  "reward braking later.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
