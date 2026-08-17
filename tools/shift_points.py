"""Where to shift, per car and per gear, measured off his own laps.

GT7 broadcasts no torque curve and no power curve. It broadcasts **speed, rpm,
gear and the gear ratios, at 60 Hz**, and acceleration is the derivative of
speed - so the shift point can be derived from a car's own behaviour on track
instead of being guessed, copied from a forum, or left as one number for every
gear and every car.

**The comparison, and why it is fair.** The upshift point is the lowest rpm at
which the next gear's acceleration beats this one's. The two are compared at
the rpm the engine actually lands on after the shift, `rpm x ratio_next /
ratio_current`, which is the **same road speed** - so aerodynamic drag, the
one force that would otherwise contaminate a comparison between gears, is the
same on both sides and cancels. Each (gear, rpm) bin is a single road speed by
construction, which is what makes the binning honest.

**What this is not.** It is derived, not measured: nothing in the feed states
engine torque. What makes it usable under this project's rules is that it is
derived from *his* car, on *his* laps, and can be re-run against any session.
Bin width bounds the precision - a shift point is reported to the bin, and the
bins are 250 rpm.

**Contamination that is real and is not corrected.** Full-throttle frames from
a corner exit carry lateral load and, on some circuits, gradient. Both add
scatter rather than bias in one direction, and the median within each bin is
what keeps a handful of them from moving the answer. A circuit with sustained
elevation change deserves a second opinion from a flatter one.

    python tools/shift_points.py --session 41
    python tools/shift_points.py --car "Ford Shelby GT350R '16"
    python tools/shift_points.py --session 41 --short-shift 500
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import DEFAULT_DB_PATH, Store          # noqa: E402

# 250 rpm: fine enough that a shift point is actionable, coarse enough that
# every bin in the gears that matter carries tens of samples. Narrower bins
# looked more precise and were mostly noise.
BIN_RPM = 250.0
# Below this many frames a bin is not reported. A shift point resting on three
# frames of one corner exit is not a measurement of the car.
MIN_BIN_FRAMES = 8
# A gear with less than this in total is skipped entirely - first gear on most
# circuits, and anything only used on a standing start.
MIN_GEAR_FRAMES = 60
# The stencil the speed channel is differenced over. Speed is stored to
# 0.1 km/h and the car covers little in one frame, so a single-frame difference
# is mostly quantisation; +-2 frames is 67 ms and smooths that without hiding
# the shape of the curve.
STENCIL = 2


def _laps_for(con, store, *, session: int | None,
              car: str | None) -> list[tuple[int, str | None]]:
    """(lap_id, gear_ratios_json) for the requested car or session."""
    if session is not None:
        rows = con.execute(
            "SELECT id, gear_ratios FROM laps WHERE session_id = ? "
            "ORDER BY lap_num", (session,)).fetchall()
        return [(r[0], r[1]) for r in rows]
    if car is None:
        raise SystemExit("give --session or --car")
    rows = con.execute("""
        SELECT l.id, l.gear_ratios FROM laps l
        JOIN sessions s ON s.id = l.session_id
        JOIN events   e ON e.id = s.event_id
        WHERE e.car_name = ?
        ORDER BY l.session_id, l.lap_num
    """, (car,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def _ratios(rows: list[tuple[int, str | None]]) -> list[float] | None:
    """The gearbox as fitted, read off the packet rather than off a sheet."""
    for _, raw in rows:
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        values = [float(x) for x in (parsed or []) if x]
        if len(values) >= 2:
            return values
    return None


def _curves(store, rows) -> dict[int, dict[float, tuple[float, int]]]:
    """Median acceleration per (gear, rpm bin), at full throttle on tarmac."""
    per_gear: dict[int, list[np.ndarray]] = {}
    for lap_id, _ in rows:
        payload = store.get_lap_frames(lap_id)
        if not payload:
            continue
        frames = payload["frames"]
        if len(frames) < 2 * STENCIL + 1:
            continue
        speed = np.array([f.get("speed_kph") or 0.0 for f in frames]) / 3.6
        rpm = np.array([f.get("rpm") or 0.0 for f in frames])
        gear = np.array([int(f.get("gear") or 0) for f in frames])
        throttle = np.array([f.get("throttle_pct") or 0.0 for f in frames])
        brake = np.array([f.get("brake_pct") or 0.0 for f in frames])
        tarmac = np.array([(f.get("surf_fl") or "T") == "T" for f in frames])
        # **The rev limiter is not a shift point, and it looked like the best
        # one.** GT7 cuts fuel on the limiter, so those frames read close to
        # zero acceleration - and a bin full of them is a bin where the next
        # gear wins by a mile. On the RSR that put gear 1's answer at "shift
        # at 9000" off 13 frames reading 0.00 m/s^2, which is the fuel cut and
        # not a gearbox fact. The flag is broadcast; it just was not read.
        limited = np.array([bool(f.get("rev_limiter")) for f in frames])

        k = STENCIL
        accel = np.zeros_like(speed)
        accel[k:-k] = (speed[2 * k:] - speed[:-2 * k]) / (2 * k / 60.0)
        usable = ((throttle >= 99.0) & (brake <= 1.0) & (gear >= 1)
                  & (rpm > 0) & tarmac & ~limited)
        # A frame is contaminated by the cut for as long as the derivative
        # window can see one, since acceleration here is a centred difference.
        for offset in range(1, STENCIL + 1):
            usable[offset:] &= ~limited[:-offset]
            usable[:-offset] &= ~limited[offset:]
        usable[:k] = False
        usable[-k:] = False
        for g in range(1, 9):
            sel = usable & (gear == g)
            if sel.sum():
                per_gear.setdefault(g, []).append(
                    np.column_stack([rpm[sel], accel[sel]]))

    curves: dict[int, dict[float, tuple[float, int]]] = {}
    for g, chunks in per_gear.items():
        data = np.vstack(chunks)
        if len(data) < MIN_GEAR_FRAMES:
            continue
        r, a = data[:, 0], data[:, 1]
        edges = np.arange(np.floor(r.min() / BIN_RPM) * BIN_RPM,
                          r.max() + BIN_RPM, BIN_RPM)
        index = np.digitize(r, edges)
        curve = {}
        for b in range(1, len(edges)):
            sel = index == b
            if sel.sum() >= MIN_BIN_FRAMES:
                curve[float(edges[b - 1])] = (float(np.median(a[sel])),
                                              int(sel.sum()))
        if curve:
            curves[g] = curve
    return curves


def _crossover(curves, ratios, gear):
    """Where the next gear starts winning, or why it cannot be said.

    Returns `(kind, detail)`. `kind` is one of:
      "shift"        - a crossover inside the data, with the rpm
      "limiter"      - this gear wins everywhere it was compared: pull it
      "data-limited" - too few comparable bins to make either claim
    """
    nxt = gear + 1
    if gear not in curves or nxt not in curves or gear > len(ratios) - 1:
        return "data-limited", "no data for one of the two gears"
    drop = ratios[gear] / ratios[gear - 1]
    compared = 0
    highest = None
    for rpm in sorted(curves[gear]):
        here, n_here = curves[gear][rpm]
        landed = rpm * drop
        key = min(curves[nxt], key=lambda x: abs(x - landed))
        if abs(key - landed) > BIN_RPM / 2.0:
            # The next gear was never driven at the rpm this shift would land
            # on. Silence, not a verdict - this is the case that made the
            # Porsche look like "no crossover" when it may only have been
            # missing bins.
            continue
        compared += 1
        highest = rpm
        there, n_there = curves[nxt][key]
        if there >= here:
            return "shift", {
                "rpm": rpm, "accel_here": here, "accel_next": there,
                "landed": landed, "drop": drop,
                "frames_here": n_here, "frames_next": n_there,
                "compared_bins": compared,
            }
    if compared < 3:
        return "data-limited", (
            f"only {compared} rpm bins could be compared - the next gear was "
            f"not driven at the rpm these shifts land on")
    return "limiter", (
        f"this gear won at all {compared} comparable bins, up to "
        f"{highest:.0f} rpm - pull it to the limiter, or drive higher rpm "
        f"in the next gear to extend the comparison")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=int)
    parser.add_argument("--car")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--short-shift", type=float, default=500.0,
                        help="rpm below the shift point to cost as a "
                             "short-shift")
    parser.add_argument("--table", action="store_true",
                        help="print the full acceleration table")
    args = parser.parse_args()

    store = Store(args.db)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = _laps_for(con, store, session=args.session, car=args.car)
    if not rows:
        raise SystemExit("no laps for that session or car")

    ratios = _ratios(rows)
    curves = _curves(store, rows)
    if not curves:
        raise SystemExit("no full-throttle running in those laps")

    label = f"session {args.session}" if args.session else args.car
    print(f"{label}: {len(rows)} laps")
    print(f"gear ratios: "
          + (", ".join(f"{r:.3f}" for r in ratios) if ratios else "NOT RECORDED"))
    print()
    for g in sorted(curves):
        frames = sum(n for _, n in curves[g].values())
        lo, hi = min(curves[g]), max(curves[g])
        print(f"  gear {g}: {frames:6d} full-throttle frames, "
              f"{len(curves[g]):2d} bins, {lo:.0f}-{hi + BIN_RPM:.0f} rpm")

    if args.table:
        print("\nmedian acceleration, m/s^2 (frames)")
        for rpm in sorted({r for c in curves.values() for r in c}):
            line = f"{rpm:6.0f} "
            for g in sorted(curves):
                cell = curves[g].get(rpm)
                line += (f"  g{g} {cell[0]:5.2f}({cell[1]:4d})" if cell
                         else " " * 15)
            print(line)

    if not ratios:
        raise SystemExit(
            "\nno gear ratios recorded on these laps - the crossover needs "
            "them to know what rpm a shift lands on")

    print("\nupshift points, measured:")
    table: dict[int, float] = {}
    for g in sorted(curves):
        kind, detail = _crossover(curves, ratios, g)
        if kind == "shift":
            table[g] = detail["rpm"]
            print(f"  {g}->{g+1}  SHIFT AT {detail['rpm']:.0f} rpm   "
                  f"{detail['accel_here']:.2f} m/s^2 here vs "
                  f"{detail['accel_next']:.2f} landing at "
                  f"{detail['landed']:.0f}   "
                  f"({detail['frames_here']}/{detail['frames_next']} frames, "
                  f"{detail['compared_bins']} bins compared)")
        elif kind == "limiter":
            print(f"  {g}->{g+1}  LIMITER      {detail}")
        else:
            print(f"  {g}->{g+1}  UNKNOWN      {detail}")

    if table:
        print("\nas a per-gear table:")
        print("  " + json.dumps({str(k): round(v) for k, v in table.items()}))

    # ------------------------------------------------- what short-shifting costs
    #
    # **The comparison has to be stay-versus-shift at the same moment**, not
    # this gear now against this gear later. The first version of this printed
    # the current gear's acceleration at the short-shift rpm against its
    # acceleration at the shift point, which only shows that the curve falls
    # with rpm - it is true, it looks like a benefit, and it is not the
    # question. What short-shifting actually costs is the acceleration given
    # up **at the instant of the early shift**: what the car would have made
    # staying in this gear, less what it makes in the next one at the rpm it
    # lands on. By construction that is positive below the crossover, which is
    # exactly why the crossover is the shift point.
    if table and args.short_shift > 0:
        print(f"\nwhat short-shifting {args.short_shift:.0f} rpm early costs "
              f"at the moment of the shift:")
        for g, rpm in sorted(table.items()):
            early = rpm - args.short_shift
            stay_key = min(curves[g], key=lambda x: abs(x - early))
            if abs(stay_key - early) > BIN_RPM / 2.0 or g + 1 not in curves:
                print(f"  gear {g}: no measured bin at {early:.0f} rpm")
                continue
            drop = ratios[g] / ratios[g - 1]
            landed = early * drop
            shift_key = min(curves[g + 1], key=lambda x: abs(x - landed))
            if abs(shift_key - landed) > BIN_RPM / 2.0:
                print(f"  gear {g}: gear {g+1} was never driven at "
                      f"{landed:.0f} rpm - cannot cost it")
                continue
            stay = curves[g][stay_key][0]
            shifted = curves[g + 1][shift_key][0]
            print(f"  gear {g}->{g+1} at {stay_key:.0f}: "
                  f"stay {stay:.2f} m/s^2 vs shift {shifted:.2f} "
                  f"(landing {landed:.0f}) - costs {stay - shifted:+.2f} m/s^2")
        print("  (positive is the acceleration given up by shifting early - "
              "the price of the fuel saved)")


if __name__ == "__main__":
    main()
