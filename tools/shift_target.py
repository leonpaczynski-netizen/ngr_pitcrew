"""How far to short-shift for a given race, and where it turns against you.

`shift_points.py` answers "where does the next gear start pulling harder?" -
the fastest place to shift, ignoring fuel. This answers the other question,
the one asked on the grid: **how much rpm do I give up, and where does giving
up more start costing me?**

**The benefit has two parts, and missing the second one is what made the first
version of this file wrong.**

* *Discrete* - a drop deep enough to delete a pit stop is worth the pit loss
  and a transit all at once.
* *Continuous* - and much the larger part over a race: **every litre not taken
  on is a second not spent stationary.** At 1 L/s and 27 laps, 2.1 L per 1000
  rpm is 57 seconds of refuelling per 1000 rpm, against 15 seconds of lap time
  at the measured cost. That keeps paying long after the stop count settles,
  which is why "the smallest drop that buys the stop" is not the answer.

So there IS a peak, and this walks the whole curve to find it. Two things end
it: the marginal rate falling below the exchange rate, and the lap cliff.

**The break-even is exact and worth knowing by heart.** Both benefit and cost
scale with the same lap count, so it cancels: short-shifting pays while

    litres per 1000 rpm / refuel rate  >  seconds per 1000 rpm

At Monza that is 2.12 against a measured 0.57-1.71, so the marginal rate is
still positive at any drop he can hold, and the binding constraint is not the
rate at all - it is **the lap cliff**, the drop at which the lap time finally
costs a whole lap and hands back everything the fuel bought.

**The dominant uncertainty is the seconds, not the litres.** The A/B pins the
fuel side hard (t 13.9) and cannot resolve the time side (t 1.3); the two
defensible readings differ threefold and move the optimum from 1200 rpm to
2600. So `--sensitivity` sweeps the cost coefficient and prints the optimum
against each, and the honest answer to "what should I run" is the drop that is
safe across that whole range rather than the peak of any one line.

Measured at Monza, 18 Aug 2026, sessions 50 and 51: he drove **849 rpm** while
intending 600. That is comfortably on the right side of the peak on both
readings of his own data - it would only be an overshoot if the cost were as
bad as 3 s/1000 rpm, which is the old unresolvable fit and not what the A/B
says.

**The coefficients are per car and per circuit and must be measured.** They
come from a paired A/B: two runs at genuine pace, same setup and tyre,
differing only in shift rpm. `tools/shortshift_trade.py` will NOT give you
these - it demeans within session, so a deliberate two-session A/B is exactly
the contrast it discards.

    python tools/shift_target.py --event 1 --from-sessions 50 51
    python tools/shift_target.py --event 1 --from-sessions 50 51 --sensitivity
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
MAX_RPM = 3000
# Below this the car is not being driven, it is being nursed, and the linear
# coefficients stop describing anything real.
MIN_BURN_L = 1.5
ROUND_TO = 50
# The sensitivity table asks about shape, not position, so it steps coarsely.
SENSITIVITY_STEP = 100
# **How far past the measured drop the straight line may be believed.**
#
# Both coefficients come from ONE pair of runs at one separation - 849 rpm at
# Monza - and they are fitted as straight lines through it. Nothing in the data
# says the fuel saving stays linear at three times that, and plenty says it
# cannot: at 2450 rpm the same line predicts 1.5 L/lap, which is not a car
# being driven. Left unbounded the sweep cheerfully recommends exactly that,
# because within its own arithmetic the marginal litre never stops paying.
#
# So the recommendation is capped at this multiple of the measured drop and the
# cap is stated. Beyond it the honest answer is not a bigger number, it is
# another A/B at the bigger separation.
TRUSTED_MULTIPLE = 1.5
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


def sweep(inputs, base_burn, base_lap_ms, litres_per_1000, seconds_per_1000,
          step: int = STEP_RPM):
    """Walk the whole curve. Returns (rows, best, knee, cliff).

    `best` is the drop that scores highest - **most laps first, then least
    time.** Ranking on time alone rewards a plan for finishing early one lap
    down, which is how the limiter's three-stop line once came out on top.
    `knee` is where a stop first falls away and `cliff` is where a lap is first
    lost; both are reported because they are the two things the driver can feel
    the consequences of.
    """
    def plan_at(drop):
        burn = base_burn - litres_per_1000 * drop / 1000.0
        if burn <= MIN_BURN_L:
            return None
        trial = dataclasses.replace(
            inputs, fuel_per_lap_l=burn,
            lap_time_ms=base_lap_ms + 1000.0 * seconds_per_1000 * drop / 1000.0)
        plans = model.recommend(trial)
        if not plans:
            return None
        best = max(plans, key=lambda p: (sum(s.laps for s in p.stints),
                                         -p.total_time_s))
        return (drop, burn, trial.lap_time_ms / 1000.0, len(best.stints) - 1,
                sum(s.laps for s in best.stints), best.total_time_s, best)

    rows, knee, cliff, prev = [], None, None, None
    for drop in range(0, MAX_RPM + 1, step):
        row = plan_at(drop)
        if row is None:
            break
        if prev is not None:
            if knee is None and row[3] < prev[3]:
                knee = row
            if cliff is None and row[4] < prev[4]:
                cliff = row
        rows.append(row)
        prev = row
    best = max(rows, key=lambda r: (r[4], -r[5]))
    return rows, best, knee, cliff


def report(inputs, burn, lap_ms, litres, seconds, *, verbose=True,
           step: int = STEP_RPM, trusted: float | None = None):
    rows, best, knee, cliff = sweep(inputs, burn, lap_ms, litres, seconds, step)
    # The peak may sit outside the range the coefficients were measured over.
    # Report it, but recommend the best drop that is still inside it - see
    # `TRUSTED_MULTIPLE`.
    peak = best
    if trusted is not None:
        inside = [r for r in rows if r[0] <= trusted]
        if inside:
            best = max(inside, key=lambda r: (r[4], -r[5]))

    def describe(row):
        plan = row[6]
        return (f"{row[3]} stop(s), "
                + " + ".join(f"{s.laps}{s.compound}" for s in plan.stints)
                + f", {row[4]} laps, {row[5]:.1f} s")

    if verbose:
        print(f"{'drop':>6} {'burn':>7} {'lap s':>8} {'stops':>6} {'laps':>5} "
              f"{'race s':>9}")
        for row in rows:
            mark = ''
            if knee and row[0] == knee[0]:
                mark += '   stop deleted'
            if cliff and row[0] == cliff[0]:
                mark += '   <<< A LAP LOST'
            if row[0] == best[0]:
                mark += '   *** best ***'
            if row[0] % (step * 10) == 0 or mark:
                print(f"{row[0]:6d} {row[1]:7.3f} {row[2]:8.3f} {row[3]:6d} "
                      f"{row[4]:5d} {row[5]:9.1f}{mark}")
        print(f"\n  limiter    {describe(rows[0])}")
        if knee:
            print(f"  {knee[0]:4d} rpm   {describe(knee)}   <- the stop falls away")
        if trusted is not None and peak[0] > trusted:
            print(f"  {peak[0]:4d} rpm   {describe(peak)}   <- the line's peak, "
                  f"but {peak[0]/trusted*TRUSTED_MULTIPLE:.1f}x the measured "
                  f"drop - extrapolated, not measured")
        print(f"  {best[0]:4d} rpm   {describe(best)}   <- best inside the data"
              if trusted is not None else
              f"  {best[0]:4d} rpm   {describe(best)}   <- best")
        if cliff:
            print(f"  {cliff[0]:4d} rpm   {describe(cliff)}   <- a lap is lost, "
                  f"do not go here")
    return best, knee, cliff


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
    ap.add_argument("--measured-drop", type=float, default=None,
                    help="the rpm separation the coefficients were measured "
                         "over; the recommendation is capped at "
                         f"{TRUSTED_MULTIPLE}x it")
    ap.add_argument("--sensitivity", action="store_true",
                    help="sweep the cost coefficient - the half the data "
                         "cannot resolve, and the half that moves the answer")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = ap.parse_args()

    store = Store(args.db)
    inputs, _ = evidence.build_inputs(store, args.event, remember=False)

    burn, lap_ms, measured_drop = args.burn, args.lap_ms, args.measured_drop
    if args.from_sessions:
        print(f"coefficients from sessions {args.from_sessions[0]} and "
              f"{args.from_sessions[1]}:")
        drop, lp1000, sp1000, burn_ab, lap_ab = coefficients(
            store, *args.from_sessions)
        print(f"\n  usage-weighted drop {drop:.0f} rpm")
        print(f"  fuel  {lp1000:+.3f} L per 1000 rpm")
        print(f"  time  {sp1000:+.3f} s per 1000 rpm")
        litres, seconds = lp1000, sp1000
        measured_drop = measured_drop or drop
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

    exchange = litres / (inputs.refuel_rate_lps or 1.0)
    trusted = (measured_drop * TRUSTED_MULTIPLE) if measured_drop else None
    print(f"\nstarting from {burn:.3f} L/lap at {lap_ms/1000:.3f} s, "
          f"tank {inputs.fuel_capacity_l:.0f} L, refuel "
          f"{inputs.refuel_rate_lps} L/s")
    print(f"break-even {exchange:.2f} s per 1000 rpm - above this the marginal "
          f"litre stops paying for itself\n")

    if args.sensitivity:
        # **The seconds are the uncertain half and they move the answer most,
        # so show that rather than hiding it behind one number.** The measured
        # value is bracketed by two readings of the same A/B that differ
        # threefold; a recommendation that only holds for one of them is not a
        # recommendation.
        print(f"  {'s/1000rpm':>10} {'best drop':>10} {'laps':>5} "
              f"{'stops':>6} {'lap cliff':>10}")
        for cost in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
            # Coarser here on purpose: the sensitivity table is about the
            # SHAPE across cost coefficients, and 50 rpm of resolution on each
            # line is plenty for that at an eighth of the wall-clock.
            best, _knee, cliff = report(inputs, burn, lap_ms, litres, cost,
                                        verbose=False, step=SENSITIVITY_STEP)
            here = " <- measured" if abs(cost - seconds) < 0.25 else ""
            print(f"  {cost:10.2f} {best[0]:10d} {best[4]:5d} {best[3]:6d} "
                  f"{cliff[0] if cliff else 0:10d}{here}")
        print(f"\n  measured for this car: {seconds:.2f} s per 1000 rpm.")
        print(f"  Run the drop that is safe across the whole range this data "
              f"cannot rule out,\n  not the peak of any one line.")
        return

    best, _knee, cliff = report(inputs, burn, lap_ms, litres, seconds,
                                trusted=trusted)
    if best[0] == 0:
        print(f"\nNo drop up to {MAX_RPM} rpm beats the limiter. Short-shifting "
              f"buys nothing this race - stay on the limiter and take the fuel.")
        return
    target = -(-best[0] // ROUND_TO) * ROUND_TO
    print(f"\n**Short-shift {target} rpm.**")
    print(f"The measured cost is {seconds:.2f} against a break-even of "
          f"{exchange:.2f}, so the marginal litre "
          f"{'still pays' if seconds < exchange else 'no longer pays'}.")
    if cliff:
        print(f"Do not pass {cliff[0]} rpm: the lap time costs a whole lap "
              f"there and hands back everything the fuel bought.")
    if trusted is not None:
        print(f"Capped at {trusted:.0f} rpm - {TRUSTED_MULTIPLE}x the "
              f"{measured_drop:.0f} rpm the coefficients were measured over. "
              f"To justify more, run the A/B at the bigger separation.")
    print(f"\nRun --sensitivity before trusting one number - the seconds are "
          f"the half this data cannot resolve, and they move the peak.")


if __name__ == "__main__":
    main()
