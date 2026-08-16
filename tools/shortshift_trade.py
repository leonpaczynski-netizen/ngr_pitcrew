"""What short-shifting actually costs and saves, from laps he really drove.

He short-shifts by hand, and his upshift rpm varies lap to lap. That variation
is a natural experiment: fuel burn and lap time are both measured beside it, so
the trade can be fitted from his own driving instead of quoted from a guide.

    python tools/shortshift_trade.py --event 1
    python tools/shortshift_trade.py --car "Porsche 911 RSR (991) '17"

**Two traps are baked into this file because each one produced a confident
wrong answer first.**

**1. The throttle must be read BEFORE the lift, not at the shift.** The frame
immediately before a gear change reads about 50% throttle - that is the lift
for the shift itself. Gating on it to find "upshifts under power" therefore
rejects every real upshift and reports that the driver has never short-shifted.
Measured: 14 genuine upshifts on a Monza lap, 0 of them surviving that gate.
The throttle is read `LOOKBACK` frames earlier, which asks the question that
was meant - was he accelerating into this shift?

**2. Sessions must be demeaned before anything is believed.** Pooled raw over
76 laps, lap time correlated with upshift rpm at t = +2.50, r = +0.279 - which
says shifting EARLIER makes him FASTER, and is nonsense. It is a between-
session artefact: his low-rpm sessions happened also to be his quicker ones.
Within sessions the slopes scatter from -11 to +18 s per 1000 rpm and only one
of five is nominally significant. **The fixed-effects fit is the answer and the
pooled one is printed only as the warning it is.**

What it found on the Porsche at Monza, 69 laps across 5 sessions:

    fuel      +1.762 L per 1000 rpm   95% CI [+0.922, +2.603]   t +4.11
    lap time  +3.269 s per 1000 rpm   95% CI [-3.602, +10.140]  t +0.93

So a 300 rpm short-shift **saves 0.53 L/lap** and costs an amount that 69 laps
cannot resolve - **bounded at about 1.08 s/lap** at the top of its interval.
That asymmetry is the whole finding, and it follows from the noise floors: one
lap's fuel has a sigma of 0.081 L against a sigma of 0.918 s on lap time.

**The rule it supports:** short-shift by exactly the drop that makes the fuel
target and no more, because every rpm below the crossover buys fuel with a real
if unmeasured slice of lap time.

    required drop rpm = (litres per lap to save) / slope * 1000

**Never a fuel map.** He runs map 1 only, having tested that other maps lose
more lap time than they save against short-shifting, lift-and-coast and a tow.
That is also why this fit is clean: `laps.fuel_map` is null on every lap
because he never touches it, so nothing here is confounded by a map change.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import DEFAULT_DB_PATH, Store          # noqa: E402

# How far back the throttle is read. Six frames is 100 ms - clear of the lift
# for the shift, close enough that it is still the same acceleration.
LOOKBACK = 6
# A gear needs this many upshifts in a lap before its median is used, so one
# odd change does not become "the rpm he shifts at".
MIN_SHIFTS_PER_GEAR = 2
# A session needs this many usable laps to contribute a within-session slope.
MIN_LAPS_PER_SESSION = 6
# Only a degenerate case is rejected outright: no variation at all means there
# is nothing to regress. **Anything above that is judged by the confidence
# interval, not by a threshold on the spread.** An earlier version put this at
# 50 rpm and refused to fit the Porsche data, whose WITHIN-session spread is
# about 33 rpm - and which nonetheless yields the fuel slope at t = +4.11,
# because 69 laps of a small consistent effect is still an effect. A guard on
# the input that overrules the statistics is a guard that hides results.
MIN_RPM_SD = 10.0


def _usable(row) -> bool:
    """The stint spec's filter, so every series in this app agrees on a lap."""
    (_, _, _, ms, fuel, _, pit, out, excluded, off, spin, crawl) = row
    if excluded or pit or out or not ms:
        return False
    if fuel is None or fuel <= 0.05:
        return False
    return ((off or 0) < 2.0 and (crawl or 0) < 0.5 and (spin or 0) < 0.08)


def _laps(con, store, *, event: int | None, car: str | None):
    if event is not None:
        where, params = "s.event_id = ?", (event,)
    elif car is not None:
        where, params = "e.car_name = ?", (car,)
    else:
        raise SystemExit("give --event or --car")
    return con.execute(f"""
        SELECT l.id, l.session_id, l.lap_num, l.lap_time_ms, l.fuel_used,
               l.fuel_start, l.is_pit_lap, l.is_out_lap, l.excluded,
               l.off_track_s, l.spin_s, l.crawl_s
        FROM laps l
        JOIN sessions s ON s.id = l.session_id
        JOIN events   e ON e.id = s.event_id
        WHERE {where}
        ORDER BY l.session_id, l.lap_num
    """, params).fetchall()


def _shift_rpm(store, lap_id) -> tuple[dict[int, float], int] | None:
    """Median upshift rpm per gear for one lap, and how many shifts it saw."""
    payload = store.get_lap_frames(lap_id)
    if not payload:
        return None
    frames = payload["frames"]
    if len(frames) <= LOOKBACK:
        return None
    gear = np.array([int(f.get("gear") or 0) for f in frames])
    rpm = np.array([f.get("rpm") or 0.0 for f in frames])
    throttle = np.array([f.get("throttle_pct") or 0.0 for f in frames])

    shifts: dict[int, list[float]] = defaultdict(list)
    for i in range(LOOKBACK, len(gear)):
        if not (gear[i] == gear[i - 1] + 1 and gear[i - 1] >= 1):
            continue
        # See trap 1 in the module docstring: the throttle at i-1 is the lift
        # for the shift, not the throttle he was carrying into it.
        if throttle[i - LOOKBACK:i].max() < 90.0:
            continue
        shifts[int(gear[i - 1])].append(float(rpm[i - 1]))
    per_gear = {g: float(np.median(v)) for g, v in shifts.items()
                if len(v) >= MIN_SHIFTS_PER_GEAR}
    if not per_gear:
        return None
    return per_gear, sum(len(v) for v in shifts.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=int)
    parser.add_argument("--car")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--drop", type=float, default=300.0,
                        help="rpm drop to express the trade for")
    parser.add_argument("--laps", action="store_true",
                        help="print every lap that fed the fit")
    args = parser.parse_args()

    store = Store(args.db)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = _laps(con, store, event=args.event, car=args.car)
    if not rows:
        raise SystemExit("no laps for that event or car")

    records = []
    for row in rows:
        if not _usable(row):
            continue
        found = _shift_rpm(store, row[0])
        if found is None:
            continue
        per_gear, count = found
        records.append({
            "session": row[1], "lap": row[2], "time_s": row[3] / 1000.0,
            "fuel": float(row[4]), "shifts": per_gear, "count": count,
            "rpm": float(np.mean(list(per_gear.values()))),
        })

    print(f"{len(rows)} laps, {len(records)} usable with upshift data")
    if len(records) < MIN_LAPS_PER_SESSION:
        raise SystemExit("not enough laps carrying upshifts to fit anything")

    if args.laps:
        print(f"\n{'ses':>4} {'lap':>4} {'time':>9} {'fuel':>6} {'n':>3}  "
              f"upshift rpm by gear")
        for r in records:
            gears = " ".join(f"g{g}:{v:.0f}"
                             for g, v in sorted(r["shifts"].items()))
            print(f"{r['session']:>4} {r['lap']:>4} {r['time_s']:>9.3f} "
                  f"{r['fuel']:>6.3f} {r['count']:>3}  {gears}")

    by_session = defaultdict(list)
    for r in records:
        by_session[r["session"]].append(r)
    usable_sessions = {s: rs for s, rs in by_session.items()
                       if len(rs) >= MIN_LAPS_PER_SESSION}

    all_rpm = np.array([r["rpm"] for r in records])
    print(f"\nupshift rpm: mean {all_rpm.mean():.0f}, "
          f"{all_rpm.min():.0f}-{all_rpm.max():.0f}, sd {all_rpm.std(ddof=1):.0f}")

    # ---------------------------------------------------- the warning, first
    pooled_r = np.corrcoef(all_rpm, [r["time_s"] for r in records])[0, 1]
    print(f"\nPOOLED lap-time correlation is {pooled_r:+.3f} - and it is NOT "
          f"the answer.\nSee trap 2: pooling across sessions produced a "
          f"significant nonsense result.\nThe fixed-effects fit below is what "
          f"this tool reports.")

    if not usable_sessions:
        raise SystemExit(
            f"\nno session has {MIN_LAPS_PER_SESSION}+ usable laps, so nothing "
            f"can be demeaned - and the pooled fit above is not trustworthy")

    # ------------------------------------------------------- fixed effects
    xs, fuels, times = [], [], []
    for rs in usable_sessions.values():
        rpm = np.array([r["rpm"] for r in rs])
        xs.append(rpm - rpm.mean())
        fuels.append(np.array([r["fuel"] for r in rs]) - np.mean([r["fuel"] for r in rs]))
        times.append(np.array([r["time_s"] for r in rs]) - np.mean([r["time_s"] for r in rs]))
    x = np.concatenate(xs)
    n, k = len(x), len(usable_sessions)
    if x.std(ddof=1) < MIN_RPM_SD:
        raise SystemExit(
            f"upshift rpm varies by only {x.std(ddof=1):.0f} rpm within "
            f"sessions - he shifted at the same point every lap, so there is "
            f"no experiment here")

    print(f"\nFIXED EFFECTS - {n} laps across {k} sessions, each demeaned")
    results = {}
    for name, y, unit in (("fuel", np.concatenate(fuels), "L"),
                          ("lap time", np.concatenate(times), "s")):
        slope = float((x * y).sum() / (x * x).sum())
        residual = y - slope * x
        dof = max(1, n - k - 1)
        se = float(np.sqrt((residual ** 2).sum() / dof / (x * x).sum()))
        lo, hi = slope - 1.96 * se, slope + 1.96 * se
        results[name] = (slope, lo, hi)
        print(f"  {name:9s} {slope * 1000:+8.3f} {unit}/1000rpm  "
              f"95% CI [{lo * 1000:+.3f}, {hi * 1000:+.3f}]  t {slope / se:+5.2f}")
        print(f"  {'':9s} a {args.drop:.0f} rpm drop: "
              f"{-slope * args.drop:+.3f} {unit}/lap  "
              f"CI [{-hi * args.drop:+.3f}, {-lo * args.drop:+.3f}]")

    fuel_slope, fuel_lo, _ = results["fuel"]
    time_slope, time_lo, _ = results["lap time"]
    print("\nthe rule this supports:")
    if fuel_lo <= 0:
        print("  the fuel saving is not established on this data - do not "
              "convert a fuel shortfall into an rpm drop from it")
    else:
        print(f"  required drop (rpm) = litres/lap to save / "
              f"{fuel_slope * 1000:.3f} * 1000")
        # **The worst case for a DROP is the LOWER end of the slope's
        # interval, not the upper.** A positive slope means higher rpm costs
        # time, so dropping rpm at the top of the interval SAVES the most -
        # which is the best case, and reporting it as the worst would tell the
        # driver a short-shift's downside is three times what it is.
        print(f"  worst-case cost at {args.drop:.0f} rpm: "
              f"{-time_lo * args.drop:+.2f} s/lap "
              f"(bottom of the interval, not a measurement)")
        print("  short-shift by the drop the fuel target needs and no more - "
              "every rpm\n  below the crossover buys fuel with lap time that "
              "is real but unmeasured.")


if __name__ == "__main__":
    main()
