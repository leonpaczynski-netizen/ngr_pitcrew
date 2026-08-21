"""Where on the lap did 1.71's 2.5 seconds go?

The driver's hypothesis: **rolling resistance rose and top speed fell, and that
is the lap time.** The alternatives are grip and adaptation, and a lap-time
median cannot tell the three apart because they all produce one slower number.

They differ in *where*. Drag and rolling resistance cost time where the car is
fast and on full throttle. A grip change costs it where the car is turning. So
the lap is cut into distance bins, each lap's speed trace is read into them, and
the time difference per bin is computed as `d/v_post - d/v_pre`. Summed, it
reconstructs the lap-time delta; separated, it says which hypothesis owns it.

Bins are then classified by what the car was doing in them, from the pre-patch
laps only - so the classification cannot be moved by the thing being measured.
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                           # noqa: E402

BIN_M = 100.0
EVENT = 1
MAX_PRE = 14


def laps_for(store, version: str, kinds: tuple[str, ...]) -> list[dict]:
    rows = store._query(
        "SELECT l.id, l.lap_num, l.lap_time_ms, l.compound, l.off_track_s, "
        "       l.spin_s, s.id AS sid, s.kind, s.game_version "
        "FROM laps l JOIN sessions s ON s.id = l.session_id "
        "WHERE s.event_id = ? AND s.game_version = ? "
        "  AND l.excluded = 0 AND l.is_out_lap = 0 AND l.is_pit_lap = 0 "
        "  AND l.lap_time_ms IS NOT NULL "
        "ORDER BY l.id", (EVENT, version))
    return [dict(r) for r in rows if r["kind"] in kinds]


def trace(store, lap_id: int) -> dict[int, list[tuple[float, float, float]]]:
    """Per distance bin: (speed kph, throttle %, |steering deg|) samples."""
    stored = store.get_lap_frames(lap_id)
    if not stored:
        return {}
    out: dict[int, list] = defaultdict(list)
    for f in stored["frames"]:
        d, v = f.get("lap_distance_m"), f.get("speed_kph")
        if d is None or v is None or v <= 5:
            continue
        out[int(d // BIN_M)].append(
            (v, f.get("throttle_pct") or 0.0, abs(f.get("steering_deg") or 0.0)))
    return out


def median_by_bin(store, laps: list[dict], label: str):
    speed: dict[int, list[float]] = defaultdict(list)
    throttle: dict[int, list[float]] = defaultdict(list)
    steer: dict[int, list[float]] = defaultdict(list)
    used = 0
    for lap in laps:
        got = trace(store, lap["id"])
        if not got:
            continue
        used += 1
        for b, samples in got.items():
            speed[b].append(st.median(s for s, _, _ in samples))
            throttle[b].append(st.median(t for _, t, _ in samples))
            steer[b].append(st.median(a for _, _, a in samples))
    print(f"  {label}: {used} laps with frames")
    return ({b: st.median(v) for b, v in speed.items()},
            {b: st.median(v) for b, v in throttle.items()},
            {b: st.median(v) for b, v in steer.items()})


def main() -> int:
    store = Store()
    try:
        post = laps_for(store, "1.71", ("practice",))
        pre = [lap for lap in laps_for(store, "1.70", ("practice",))
               if not (lap["off_track_s"] or 0) and not (lap["spin_s"] or 0)]
        # Match the compound the post-patch run was on.
        compounds = {lap["compound"] for lap in post if lap["compound"]}
        if compounds:
            pre = [lap for lap in pre if lap["compound"] in compounds]
        pre = pre[-MAX_PRE:]

        print(f"compound(s) post-patch: {compounds or 'unrecorded'}")
        print(f"post laps: {len(post)}   pre laps (clean, matched): {len(pre)}\n")
        if not pre or not post:
            print("not enough matched laps to compare")
            return 1

        pre_v, pre_t, pre_s = median_by_bin(store, pre, "pre-patch 1.70")
        post_v, _, _ = median_by_bin(store, post, "post-patch 1.71")

        shared = sorted(set(pre_v) & set(post_v))
        print(f"\n  {len(shared)} shared distance bins of {BIN_M:.0f} m\n")

        rows = []
        for b in shared:
            vp, vq = pre_v[b], post_v[b]
            if vp <= 0 or vq <= 0:
                continue
            # seconds to cover the bin, at each version's median speed
            dt = (BIN_M / (vq / 3.6)) - (BIN_M / (vp / 3.6))
            rows.append((b, vp, vq, dt, pre_t[b], pre_s[b]))

        total = sum(r[3] for r in rows)
        print(f"  reconstructed lap-time delta: {total:+.2f} s\n")

        # Classified on the PRE-patch traces only, so the label cannot be moved
        # by the change being measured.
        def group(rows, name, test):
            sel = [r for r in rows if test(r)]
            if not sel:
                return
            loss = sum(r[3] for r in sel)
            share = 100 * loss / total if total else 0
            dist = len(sel) * BIN_M
            print(f"  {name:<34} {len(sel):>3} bins  {dist / 1000:>5.2f} km  "
                  f"{loss:+6.2f} s  ({share:5.1f}% of the loss)")

        print("  where the time went, by what the car was doing:")
        group(rows, "flat out, straight (>95% thr, <5 deg)",
              lambda r: r[4] > 95 and r[5] < 5)
        group(rows, "flat out, turning (>95% thr, >=5 deg)",
              lambda r: r[4] > 95 and r[5] >= 5)
        group(rows, "part throttle / braking (<95% thr)",
              lambda r: r[4] <= 95)

        print("\n  and by how fast the car was going there:")
        group(rows, "above 220 km/h", lambda r: r[1] > 220)
        group(rows, "140-220 km/h", lambda r: 140 < r[1] <= 220)
        group(rows, "below 140 km/h", lambda r: r[1] <= 140)

        worst = sorted(rows, key=lambda r: r[3], reverse=True)[:8]
        print("\n  the eight worst bins:")
        for b, vp, vq, dt, thr, steer in worst:
            print(f"    {b * BIN_M:>5.0f} m  {vp:6.1f} -> {vq:6.1f} km/h  "
                  f"{dt:+.3f} s   thr {thr:3.0f}%  steer {steer:4.1f} deg")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
