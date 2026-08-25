"""Corners as fixed places on the earth, derived from the shape of the track.

**The corner is currently defined BY its apex, so the corner moves when the
driving does.** That is circular, and it is why identity flips: re-anchor the
model and every observation changes which corner it belongs to, with nothing
about the car changed. Anchoring the same apex to world coordinates instead of
lap distance halves the scatter but keeps the circularity - it makes the wrong
thing more precise.

This separates the two. A corner becomes **a fixed region**, derived from the
curvature of the mean path that every clean lap agrees on; the apex is then a
**measurement inside it**, free to move. Identity cannot flip, because nothing
about it depends on any single lap.

Two things make the mean path trustworthy as a reference:

* **It is built in world coordinates, by arc length**, never from
  `lap_distance_m` - which is the unreliable channel this whole exercise exists
  to stop depending on (203 m to 11,187 m over 307 Monza laps).
* **The world origin is stable.** Verified across Monza's 50 sessions over 13
  days: two clean laps overlay to a median 1.01 m, bounding boxes agreeing to
  2.6 m on a 1,256 x 2,164 m track.

    python tools/geometric_corners.py --event 6
    python tools/geometric_corners.py --circuit autodromo-nazionale-monza-full-course

Read-only. It reports the regions it finds and compares them with the stored
auto-segmented model; it writes nothing.
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store  # noqa: E402

# How many points the mean path is resampled to. One point per few metres on a
# 4-6 km circuit, which is finer than any corner boundary needs to be and cheap.
SAMPLES = 1000
# Curvature above this is "turning", in 1/m. A 200 m radius is 0.005; most
# racing corners are far tighter. Deliberately generous so a fast sweeper is
# still found - a corner missed is worse than a straight briefly included.
CURVATURE_TURNING = 0.004
# A run of turning samples shorter than this is noise in the path, not a corner.
MIN_CORNER_M = 40.0
# How far a curvature peak must stand above the straightest point beside it,
# as a fraction of the peak itself, before it is a corner rather than a ripple.
#
# **Prominence rather than a higher threshold, and the difference matters.** A
# ripple partway through a sweeper can have high curvature and still not be a
# corner; a gentle kink between two straights can have low curvature and be
# one. Height alone cannot separate them and no setting of it can - which is
# why raising the threshold traded four kilometre-long regions for thirty-one
# fragments. Prominence asks the question that actually distinguishes them:
# does the track straighten out either side of this, or is it part of
# something longer? It is scale-free, so it needs no per-circuit tuning.
MIN_PROMINENCE = 0.45


def _laps(store, circuit_key: str):
    rows = store._query(
        "SELECT l.id FROM laps l JOIN sessions s ON s.id = l.session_id "
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
            pts = [(f.get("pos_x"), f.get("pos_z")) for f in frames]
        else:
            n = len(frames.get("pos_x") or [])
            pts = [(frames["pos_x"][i], frames["pos_z"][i]) for i in range(n)]
        pts = [p for p in pts if p[0] is not None and p[1] is not None
               and not (math.isnan(p[0]) or math.isnan(p[1]))]
        if len(pts) > 500:
            out.append(pts)
    return out


def _resample(points, samples: int = SAMPLES):
    """One lap as `samples` points, evenly spaced by WORLD arc length.

    Arc length rather than the game's distance channel: the whole point is to
    stop depending on the ruler that stretches.
    """
    cum, total = [0.0], 0.0
    for i in range(1, len(points)):
        total += math.hypot(points[i][0] - points[i - 1][0],
                            points[i][1] - points[i - 1][1])
        cum.append(total)
    if total <= 0:
        return None
    out, j = [], 0
    for k in range(samples):
        want = total * k / samples
        while j + 1 < len(cum) and cum[j + 1] < want:
            j += 1
        if j + 1 >= len(points):
            out.append(points[-1])
            continue
        span = cum[j + 1] - cum[j]
        f = 0.0 if span <= 0 else (want - cum[j]) / span
        out.append((points[j][0] + f * (points[j + 1][0] - points[j][0]),
                    points[j][1] + f * (points[j + 1][1] - points[j][1])))
    return out, total


def mean_path(laps):
    """The line every clean lap agrees on, as `SAMPLES` world points.

    Median rather than mean at each index: one lap that ran wide should not
    drag the reference every other lap is measured against.
    """
    resampled, lengths = [], []
    for pts in laps:
        got = _resample(pts)
        if got:
            resampled.append(got[0])
            lengths.append(got[1])
    if len(resampled) < 3:
        return None, None, None
    path = [(statistics.median(r[k][0] for r in resampled),
             statistics.median(r[k][1] for r in resampled))
            for k in range(SAMPLES)]
    # How far each lap sits from that reference - the number that says whether
    # a single mean path is a fair description of how he drives the circuit.
    spread = []
    for r in resampled:
        spread.append(statistics.median(
            math.hypot(r[k][0] - path[k][0], r[k][1] - path[k][1])
            for k in range(SAMPLES)))
    return path, statistics.median(lengths), statistics.median(spread)


def curvature(path, length_m: float):
    """Signed curvature at each sample, in 1/m, by the circumscribed circle."""
    step = length_m / len(path)
    out = []
    for i in range(len(path)):
        a, b, c = path[i - 2], path[i], path[(i + 2) % len(path)]
        # Cross product of the two chords gives twice the triangle area; the
        # circumradius follows. Zero area is a straight.
        cross = ((b[0] - a[0]) * (c[1] - a[1])
                 - (b[1] - a[1]) * (c[0] - a[0]))
        ab = math.hypot(b[0] - a[0], b[1] - a[1])
        bc = math.hypot(c[0] - b[0], c[1] - b[1])
        ca = math.hypot(a[0] - c[0], a[1] - c[1])
        out.append(0.0 if min(ab, bc, ca) <= 0 or cross == 0
                   else 2.0 * cross / (ab * bc * ca))
    return out, step


def regions(curv, step_m: float):
    """One region per curvature PEAK, bounded by the troughs either side.

    **The threshold version was the wrong shape and tuning it would have been
    the wrong fix.** Asking "is the car turning here" chains a whole section
    into one corner as soon as the straights between its parts fall below the
    threshold - at Fuji it returned four regions for about sixteen corners, two
    of them near a kilometre long. Lowering the threshold splits sweepers in
    half instead; there is no setting that is right everywhere, which is the
    sign that the question is wrong rather than the number.

    A corner is not "where curvature is high", it is **where curvature peaks**.
    Each local maximum of |curvature| is one corner, and its extent runs to the
    minimum either side - the straightest point between it and its neighbours.
    The count then falls out of the track's own shape instead of out of a
    constant, and a complex reads as the several corners it is rather than one
    long one.

    `MIN_CORNER_M` still applies, because two peaks a few metres apart are one
    corner seen through the noise in the path rather than two.
    """
    n = len(curv)
    mag = [abs(k) for k in curv]
    # A peak has to stand above a genuine straight somewhere, or every wobble
    # on a straight becomes a corner. This is the only threshold left and it
    # rejects noise rather than defining a corner.
    floor = CURVATURE_TURNING
    peaks = [i for i in range(n)
             if mag[i] >= floor
             and mag[i] >= mag[(i - 1) % n] and mag[i] > mag[(i + 1) % n]]
    if not peaks:
        return []

    # Merge peaks closer together than a corner can be - the same peak seen
    # twice through a ripple in the median path.
    merged = [peaks[0]]
    for i in peaks[1:]:
        if (i - merged[-1]) * step_m < MIN_CORNER_M:
            if mag[i] > mag[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)

    # Then keep only the peaks the track actually straightens out either side
    # of. See `MIN_PROMINENCE` for why height alone cannot decide this.
    def trough(a: int, b: int) -> float:
        return min(mag[j % n] for j in range(a, b + 1))

    kept = []
    for idx, peak in enumerate(merged):
        prev_peak = merged[idx - 1] if idx else merged[-1] - n
        next_peak = (merged[idx + 1] if idx + 1 < len(merged)
                     else merged[0] + n)
        prominence = mag[peak] - max(trough(prev_peak, peak),
                                     trough(peak, next_peak))
        if mag[peak] > 0 and prominence / mag[peak] >= MIN_PROMINENCE:
            kept.append(peak)
    merged = kept or merged

    out = []
    for idx, peak in enumerate(merged):
        prev_peak = merged[idx - 1] if idx else merged[-1] - n
        next_peak = merged[idx + 1] if idx + 1 < len(merged) else merged[0] + n
        # Walk out to the straightest point between this peak and each
        # neighbour. That boundary is a property of the track, not a setting.
        start = min(range(prev_peak, peak + 1), key=lambda j: mag[j % n])
        end = min(range(peak, next_peak + 1), key=lambda j: mag[j % n])
        out.append((start % n, end % n))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--circuit")
    ap.add_argument("--event", type=int)
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

        laps = _laps(store, circuit)
        print(f"\n{circuit}")
        print(f"{len(laps)} clean laps")
        path, length, spread = mean_path(laps)
        if path is None:
            print("too few clean laps to build a mean path")
            return 1
        print(f"mean path: {length:.0f} m by world arc length, "
              f"laps sit a median {spread:.2f} m from it")

        stored = store.get_corner_model(circuit)
        if stored:
            print(f"stored model: v{stored.version} ({stored.source}), "
                  f"{len(stored.corners)} corners, "
                  f"lap_length {stored.lap_length_m:.1f} m")

        curv, step = curvature(path, length)
        found = regions(curv, step)
        print(f"\ncurvature finds {len(found)} corner region(s) "
              f"at |k| >= {CURVATURE_TURNING} /m:\n")
        print(f"{'id':<5} {'from_m':>8} {'to_m':>8} {'len_m':>7} "
              f"{'radius_m':>9}  direction")
        total = len(curv)
        for n, (a, b) in enumerate(found, start=1):
            # A region that crosses the start line wraps, so the span is walked
            # rather than sliced - a slice of it comes back empty.
            span = (b - a) % total + 1
            peak = max((curv[(a + k) % total] for k in range(span)), key=abs)
            print(f"T{n:<4} {a * step:8.0f} {b * step:8.0f} "
                  f"{span * step:7.0f} {1.0 / abs(peak):9.0f}  "
                  f"{'left' if peak > 0 else 'right'}")
        print("\nNothing written - this reports the regions it would define.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
