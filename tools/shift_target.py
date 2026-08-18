"""How far to short-shift for a given race, and why not one rpm further.

`shift_points.py` answers "where does the next gear start pulling harder?" -
the fastest place to shift, ignoring fuel. This answers the other question,
the one asked on the grid: **the race needs a certain number of stops, so how
much rpm do I have to give up to get it, and no more?**

**The sweet spot is a threshold, not a peak, and that is the whole point.**
Short-shifting has a continuous cost - every rpm below the crossover is lap
time, always - against a benefit that arrives in one lump when the tank finally
stretches far enough to delete a pit stop. There is no interior optimum to hill
-climb toward: below the threshold you are paying for nothing, and above it you
are paying for something already bought. So the answer is the **smallest drop
that buys the stop**, found by walking the drop upward through the same
`strategy.recommend` that plans the race, and stopping at the step where the
stop count falls.

Measured at Monza on 18 Aug 2026, sessions 50 and 51: the drop needed was
**370 rpm, called as 400**, and he drove **849** - a usage-weighted mean across
13 upshifts a lap, while intending 600. The surplus bought fuel the race had no
way to score.

**The threshold is set by the tank, not by the lap-time cost, and that is what
makes the answer trustworthy.** Run at 0.573 s/1000 rpm or at 1.714 - the two
defensible readings of the same A/B, a factor of three apart - and the
threshold does not move. Excluding the out-laps by hand moves it 370 to 390.
Every one of those rounds to the same 400, which is the number a driver can
actually hold. A quantity this insensitive to its own inputs is one worth
acting on.

**The two coefficients are per car and per circuit and must be measured.**
`--litres-per-1000` and `--seconds-per-1000` come from a paired A/B: two runs
at genuine pace, same setup and tyre, differing only in shift rpm.
`tools/shortshift_trade.py` will NOT give you these from mixed sessions - it
demeans within session, so a deliberate two-session A/B is exactly the contrast
it discards. Derive them from the pair directly, as `--from-sessions` does.

    python tools/shift_target.py --event 1 --from-sessions 50 51
    python tools/shift_target.py --event 1 --litres-per-1000 2.124
"""
from __future__ import annotations

import argparse
import dataclasses
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import DEFAULT_DB_PATH, Store          # noqa: E402
from pitcrew.strategy import evidence, model                 # noqa: E402

# The sweep. 10 rpm is finer than anyone can hold with a beep, which is the
# point: the answer is rounded up to `ROUND_TO` before it is offered, so the
# precision is spent on locating the threshold rather than on pretending the
# driver can sit on it.
STEP_RPM = 10
MAX_RPM = 2000
ROUND_TO = 50
# Only full-throttle upshifts count, and the throttle is read BEFORE the lift
# for the shift itself - the frame at the gear change reads about 50% because
# GT7 cuts for the shift, so gating on it rejects every real upshift. Same trap
# as `shortshift_trade`, same fix.
LOOKBACK = 20
FULL_THROTTLE = 95.0


def upshifts(frames):
    """(gear, rpm) for every full-throttle upshift in a lap."""
    out, prev = [], None
    for index, frame in enumerate(frames):
        gear = frame["gear"]
        if prev is not None and gear == prev + 1 and 1 <= prev <= 7:
            window = frames[max(0, index - LOOKBACK):index]
            if window and max(f["throttle_pct"] for f in window) >= FULL_THROTTLE:
                out.append((prev, max(f["rpm"] for f in window)))
        prev = gear
    return out


def coefficients(store, fast_session: int, slow_session: int):
    """Litres and seconds per 1000 rpm, from one paired A/B.

    The drop is **weighted by how often each gear is actually shifted**, not
    averaged flat. Third to fourth happens four times a lap at Monza and first
    to second once; a flat mean over the five gears would describe a lap nobody
    drives. `min` of the two shift counts is used, so a gear only reached in
    one of the two runs cannot invent a drop.
    """
    per = {}
    burns, laps = {}, {}
    for session in (fast_session, slow_session):
        rows = [r for r in store.list_laps(session)
                if not r["excluded"] and not r["is_out_lap"]
                and not r["is_pit_lap"] and not r["crawl_s"] and not r["spin_s"]]
        if not rows:
            raise SystemExit(f"session {session} has no clean laps to compare")
        agg = {}
        for row in rows:
            stored = store.get_lap_frames(row["id"])
            if not stored:
                continue
            for gear, rpm in upshifts(stored["frames"]):
                agg.setdefault(gear, []).append(rpm)
        per[session] = {g: (st.mean(v), len(v) / len(rows)) for g, v in agg.items()}
        burns[session] = st.mean(r["fuel_used"] for r in rows)
        laps[session] = st.mean(r["lap_time_ms"] for r in rows) / 1000.0
        print(f"  session {session}: {len(rows)} clean laps, "
              f"{burns[session]:.3f} L/lap, {laps[session]:.3f} s")

    numerator = denominator = 0.0
    print(f"\n  {'shift':8} {'fast':>8} {'slow':>8} {'drop':>7} {'per lap':>9}")
    for gear in sorted(set(per[fast_session]) & set(per[slow_session])):
        fast, n_fast = per[fast_session][gear]
        slow, n_slow = per[slow_session][gear]
        shared = min(n_fast, n_slow)
        numerator += (fast - slow) * shared
        denominator += shared
        print(f"  {gear}->{gear+1:<5} {fast:8.0f} {slow:8.0f} "
              f"{fast - slow:7.0f} {shared:9.1f}")
    if denominator <= 0:
        raise SystemExit("the two sessions share no gear - nothing to compare")
    drop = numerator / denominator
    if drop <= 0:
        raise SystemExit(
            f"session {slow_session} shifted {-drop:.0f} rpm HIGHER than "
            f"{fast_session} - name the faster-shifting session first")
    d_fuel = burns[fast_session] - burns[slow_session]
    d_time = laps[slow_session] - laps[fast_session]
    return (drop, 1000 * d_fuel / drop, 1000 * d_time / drop,
            burns[fast_session], laps[fast_session] * 1000)


def sweep(inputs, base_burn, base_lap_ms, litres_per_1000, seconds_per_1000):
    """The smallest drop that changes the plan, and what it changes it to."""
    def plan_at(drop):
        trial = dataclasses.replace(
            inputs,
            fuel_per_lap_l=base_burn - litres_per_1000 * drop / 1000.0,
            lap_time_ms=base_lap_ms + 1000.0 * seconds_per_1000 * drop / 1000.0)
        plans = model.recommend(trial)
        if not plans:
            return None
        # Most laps first, then least time. Ranking on time alone rewards a
        # plan for finishing early one lap down.
        return max(plans, key=lambda p: (sum(s.laps for s in p.stints),
                                         -p.total_time_s))

    start = plan_at(0)
    if start is None:
        raise SystemExit("no plan at the limiter - fix the event inputs first")
    base_stops = len(start.stints) - 1
    base_laps = sum(s.laps for s in start.stints)
    for drop in range(STEP_RPM, MAX_RPM + 1, STEP_RPM):
        got = plan_at(drop)
        if got is None:
            continue
        stops = len(got.stints) - 1
        laps = sum(s.laps for s in got.stints)
        if stops < base_stops or laps > base_laps:
            return drop, start, got
    return None, start, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--from-sessions", nargs=2, type=int, metavar=("FAST", "SLOW"),
                    help="derive the coefficients from a paired A/B: the "
                         "higher-shifting session first")
    ap.add_argument("--litres-per-1000", type=float)
    ap.add_argument("--seconds-per-1000", type=float, default=None)
    ap.add_argument("--burn", type=float, help="L/lap at the limiter")
    ap.add_argument("--lap-ms", type=float, help="lap time at the limiter")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = ap.parse_args()

    store = Store(args.db)
    inputs, _ = evidence.build_inputs(store, args.event)

    burn, lap_ms = args.burn, args.lap_ms
    if args.from_sessions:
        print(f"coefficients from sessions {args.from_sessions[0]} and "
              f"{args.from_sessions[1]}:")
        drop, lp1000, sp1000, burn_ab, lap_ab = coefficients(
            store, *args.from_sessions)
        print(f"\n  usage-weighted drop {drop:.0f} rpm")
        print(f"  fuel  {lp1000:+.3f} L per 1000 rpm")
        print(f"  time  {sp1000:+.3f} s per 1000 rpm")
        litres, seconds = lp1000, sp1000
        burn = burn if burn is not None else burn_ab
        lap_ms = lap_ms if lap_ms is not None else lap_ab
    else:
        if args.litres_per_1000 is None:
            raise SystemExit("give --from-sessions or --litres-per-1000")
        litres, seconds = args.litres_per_1000, args.seconds_per_1000 or 0.0
    if burn is None:
        burn = inputs.fuel_per_lap_l
    if lap_ms is None:
        lap_ms = inputs.lap_time_ms
    if not burn or not lap_ms:
        raise SystemExit("no burn or lap time to start from")

    print(f"\nstarting from {burn:.3f} L/lap at {lap_ms/1000:.3f} s, "
          f"tank {inputs.fuel_capacity_l:.0f} L, refuel "
          f"{inputs.refuel_rate_lps} L/s\n")

    drop, base, better = sweep(inputs, burn, lap_ms, litres, seconds)
    def describe(plan):
        return (f"{len(plan.stints)-1} stop(s), "
                + " + ".join(f"{s.laps}{s.compound}" for s in plan.stints)
                + f", {sum(s.laps for s in plan.stints)} laps, "
                  f"{plan.total_time_s:.1f} s")

    print(f"  limiter      {describe(base)}")
    if drop is None:
        print(f"\nNo drop up to {MAX_RPM} rpm changes the plan. Short-shifting "
              f"buys nothing this race - stay on the limiter and take the fuel.")
        return
    print(f"  at {drop:4d} rpm  {describe(better)}")
    target = -(-drop // ROUND_TO) * ROUND_TO
    print(f"\n**Short-shift {target} rpm.** That is the smallest drop that buys "
          f"the change, rounded up to {ROUND_TO}.")
    print(f"Every rpm past it is lap time spent on fuel the race cannot score: "
          f"at {seconds:.3f} s per 1000 rpm, overshooting by 500 costs "
          f"{seconds/2:.2f} s a lap for nothing.")


if __name__ == "__main__":
    main()
