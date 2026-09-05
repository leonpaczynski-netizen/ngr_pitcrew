"""Where on the lap did a setup change land? Sectors first, then distance bins.

    python tools/where_the_change_landed.py --before 129 130 --after 132
    python tools/where_the_change_landed.py --before 129 --after 132 --bins

**Lap time cannot show a tune working, and that is measured.** His lap-to-lap
spread is 0.918 s, which puts the whole-lap detection floor at 1.74 s - above
the entire 0.5-1.5 s/lap degradation band, and above every setup effect this
project has tried to measure. The Ludo audit of 4 Sep 2026 put it plainly: no
instrument in the app could show a tune working.

That is an argument about the WHOLE LAP and it does not carry to the parts.
A setup change is usually local - a spring rate shows up where the car is
loaded, a diff where it is putting power down, a wing where it is fast. The
lap adds that one effect to nine other corners of noise.

The arithmetic is worth stating, because the opposite is usually assumed. A
corner is 3-4x noisier than a whole lap **in relative terms** - true, and it is
why per-corner input coaching is refused. But for an effect concentrated in one
place, what matters is absolute scatter. If ten corners contribute
independently then the lap's 0.918 s is sqrt(10) times one corner's, so a
corner carries about 0.29 s. A 0.3 s change hiding inside a 0.918 s lap spread
is a third of the noise; the same change inside its own corner is all of it.
**Cutting the lap up is not a finer version of the same measurement. It is a
better one, for anything not spread evenly around the circuit.**

### Two cuts, answering different questions

**Sectors** are cheap, always present and comparable across runs - but only
where both runs were cut on the SAME model. GT7 broadcasts no sectors; these
are the app's own, and the rack can hold two sets of lines. Comparing S2
across two models compares two pieces of road, so this refuses instead.

**Distance bins** are the sharp instrument: 100 m at a time,
`d/v_after - d/v_before`, which sums back to the lap-time delta as an
identity. Each bin is then labelled by what the car was doing **in the BEFORE
run only**, so the classification cannot be moved by the thing being measured.

### What this may not be used for

The bin total is an identity - it reconstructs a delta that was actually
driven. It is **not** a bank of opportunities. Never add up per-corner "time
available" and call it a lap time: that total is session scatter, and scatter
is a state rather than a loss.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                           # noqa: E402

BIN_M = 100.0
# A bin or a sector needs this many laps a side before it is worth a number.
MIN_LAPS_PER_SIDE = 3
# His measured lap-to-lap sigma, and the floor it implies for a whole lap.
LAP_SIGMA_S = 0.918
LAP_FLOOR_S = 1.74


def laps_for(store, session_ids):
    """Clean, counted laps only.

    **Excursions come out before anything is compared.** Daytona T1 once read
    r=-0.86 against lap time and collapsed to -0.30 when two off-track laps
    came out - its 12.8 km/h of scatter fell to 2.8. An incident lap is not a
    slower lap, it is a different lap.
    """
    if not session_ids:
        return []
    marks = ",".join("?" for _ in session_ids)
    rows = store._query(
        "SELECT l.id, l.lap_num, l.lap_time_ms, l.compound, l.session_id, "
        "       l.sector1_ms, l.sector2_ms, l.sector3_ms, l.sector_model "
        "FROM laps l WHERE l.session_id IN (" + marks + ") "
        "  AND l.excluded = 0 AND l.is_out_lap = 0 AND l.is_pit_lap = 0 "
        "  AND COALESCE(l.off_track_s, 0) = 0 "
        "  AND COALESCE(l.spin_s, 0) = 0 "
        "  AND l.lap_time_ms IS NOT NULL ORDER BY l.id",
        tuple(session_ids))
    return [dict(row) for row in rows]


def sector_table(before, after):
    """S1/S2/S3 either side, or a refusal saying why they do not compare."""
    models = {lap["sector_model"] for lap in before + after
              if lap["sector_model"]}
    print("\n  SECTORS")
    if not models:
        print("    no lap on either side carries sectors - nothing to compare")
        return
    if len(models) > 1:
        print("    REFUSED: " + str(len(models)) + " sector models across "
              "these runs, so S1 either side is not the same piece of road.")
        for model in sorted(models):
            print("      " + str(model))
        return

    total = 0.0
    for index in (1, 2, 3):
        key = "sector" + str(index) + "_ms"
        was = [lap[key] for lap in before if lap[key]]
        now = [lap[key] for lap in after if lap[key]]
        if len(was) < MIN_LAPS_PER_SIDE or len(now) < MIN_LAPS_PER_SIDE:
            print("    S%d  silent - %d before / %d after, needs %d each"
                  % (index, len(was), len(now), MIN_LAPS_PER_SIDE))
            continue
        # The spread either side, so the delta is read against it rather than
        # on its own. A delta inside the scatter is not a finding.
        spread = max(st.pstdev(was) if len(was) > 1 else 0.0,
                     st.pstdev(now) if len(now) > 1 else 0.0)
        delta = (st.median(now) - st.median(was)) / 1000.0
        total += delta
        verdict = "  <- inside the scatter" if abs(delta) * 1000 < spread else ""
        print("    S%d  %7.3f -> %7.3f   %+6.3f s   (n %d/%d, 1sd %.3f s)%s"
              % (index, st.median(was) / 1000, st.median(now) / 1000, delta,
                 len(was), len(now), spread / 1000, verdict))
    print("    sum of sectors: %+.3f s" % total)
    # **It will not equal the whole-lap delta, and that is arithmetic rather
    # than a fault.** The median of the sums is not the sum of the medians:
    # the quickest S1 and the quickest S2 usually came from different laps.
    # Reading the gap between them as an error is the mistake this line
    # exists to prevent.
    print("        (medians do not add up to the lap delta - the best S1 and "
          "the best S2 are usually different laps)")


def trace(store, lap_id):
    """Per distance bin: (speed kph, throttle %, |steering deg|) samples."""
    stored = store.get_lap_frames(lap_id)
    if not stored:
        return {}
    out = defaultdict(list)
    for frame in stored["frames"]:
        distance, speed = frame.get("lap_distance_m"), frame.get("speed_kph")
        if distance is None or speed is None or speed <= 5:
            continue
        out[int(distance // BIN_M)].append(
            (speed, frame.get("throttle_pct") or 0.0,
             abs(frame.get("steering_deg") or 0.0)))
    return out


def median_by_bin(store, laps, label):
    speed, throttle, steer = defaultdict(list), defaultdict(list), defaultdict(list)
    used = 0
    for lap in laps:
        got = trace(store, lap["id"])
        if not got:
            continue
        used += 1
        for index, samples in got.items():
            speed[index].append(st.median(s for s, _, _ in samples))
            throttle[index].append(st.median(t for _, t, _ in samples))
            steer[index].append(st.median(a for _, _, a in samples))
    print("    %s: %d laps with frames" % (label, used))
    counts = {index: len(values) for index, values in speed.items()}
    return ({i: st.median(v) for i, v in speed.items()},
            {i: st.median(v) for i, v in throttle.items()},
            {i: st.median(v) for i, v in steer.items()}, counts)


def main():
    parser = argparse.ArgumentParser(
        description="Where on the lap a setup change landed.")
    parser.add_argument("--before", nargs="+", type=int, required=True,
                        metavar="SESSION", help="session ids before the change")
    parser.add_argument("--after", nargs="+", type=int, required=True,
                        metavar="SESSION", help="session ids after it")
    parser.add_argument("--bins", action="store_true",
                        help="also read every lap's frames (slow) and "
                             "attribute the delta by distance")
    args = parser.parse_args()

    store = Store()
    try:
        before = laps_for(store, args.before)
        after = laps_for(store, args.after)
        print("  before: sessions %s, %d clean laps" % (args.before, len(before)))
        print("  after : sessions %s, %d clean laps" % (args.after, len(after)))
        if len(before) < MIN_LAPS_PER_SIDE or len(after) < MIN_LAPS_PER_SIDE:
            print("\n  not enough clean laps - %d a side is the floor, and "
                  "that is already generous" % MIN_LAPS_PER_SIDE)
            return 1

        # **The compound is the first confound, not an afterthought.** A
        # softer tyre wearing a setup's clothes is the standing trap here.
        was = {lap["compound"] for lap in before if lap["compound"]}
        now = {lap["compound"] for lap in after if lap["compound"]}
        if was != now:
            print("\n  ** COMPOUND DIFFERS: %s -> %s. Whatever follows is the "
                  "change AND the tyre, and they cannot be separated here."
                  % (was or "unrecorded", now or "unrecorded"))

        lap_before = st.median(lap["lap_time_ms"] for lap in before) / 1000
        lap_after = st.median(lap["lap_time_ms"] for lap in after) / 1000
        print("\n  WHOLE LAP  %.3f -> %.3f   %+.3f s"
              % (lap_before, lap_after, lap_after - lap_before))
        print("    Lap-to-lap sigma is %.3f s, so the whole-lap detection "
              "floor is %.2f s. Read the parts below, not this."
              % (LAP_SIGMA_S, LAP_FLOOR_S))

        sector_table(before, after)

        if not args.bins:
            print("\n  (pass --bins to attribute the delta by distance; it "
                  "reads every lap's frames and is slow)")
            return 0

        print("\n  DISTANCE BINS")
        v_before, thr, steer, n_before = median_by_bin(store, before, "before")
        v_after, _, _, n_after = median_by_bin(store, after, "after")

        rows, thin = [], 0
        for index in sorted(set(v_before) & set(v_after)):
            if (n_before.get(index, 0) < MIN_LAPS_PER_SIDE
                    or n_after.get(index, 0) < MIN_LAPS_PER_SIDE):
                thin += 1
                continue
            speed_was, speed_now = v_before[index], v_after[index]
            if speed_was <= 0 or speed_now <= 0:
                continue
            seconds = (BIN_M / (speed_now / 3.6)) - (BIN_M / (speed_was / 3.6))
            rows.append((index, speed_was, speed_now, seconds,
                         thr[index], steer[index]))

        if not rows:
            print("    no bin has enough laps on both sides")
            return 1
        total = sum(row[3] for row in rows)
        print("    %d bins of %.0f m compared, %d skipped for too few laps"
              % (len(rows), BIN_M, thin))
        print("    reconstructed delta over those bins: %+.3f s" % total)

        def group(name, test):
            picked = [row for row in rows if test(row)]
            if not picked:
                return
            loss = sum(row[3] for row in picked)
            share = 100 * loss / total if total else 0.0
            print("    %-38s %3d bins  %5.2f km  %+6.3f s  (%5.1f%%)"
                  % (name, len(picked), len(picked) * BIN_M / 1000, loss, share))

        # Labelled from the BEFORE traces only, so the label cannot be moved
        # by the change being measured.
        print("\n    by what the car was doing BEFORE the change:")
        group("flat out, straight (>95% thr, <5 deg)",
              lambda r: r[4] > 95 and r[5] < 5)
        group("flat out, turning (>95% thr, >=5 deg)",
              lambda r: r[4] > 95 and r[5] >= 5)
        group("part throttle, turning (>=5 deg)",
              lambda r: r[4] <= 95 and r[5] >= 5)
        group("part throttle, straight (<5 deg)",
              lambda r: r[4] <= 95 and r[5] < 5)

        gained = sorted(rows, key=lambda r: r[3])[:5]
        lost = sorted(rows, key=lambda r: -r[3])[:5]
        print("\n    biggest gains, by distance into the lap:")
        for index, was_v, now_v, seconds, _t, _s in gained:
            print("      %6.0f m  %6.1f -> %6.1f km/h  %+.3f s"
                  % (index * BIN_M, was_v, now_v, seconds))
        print("    biggest losses:")
        for index, was_v, now_v, seconds, _t, _s in lost:
            print("      %6.0f m  %6.1f -> %6.1f km/h  %+.3f s"
                  % (index * BIN_M, was_v, now_v, seconds))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
