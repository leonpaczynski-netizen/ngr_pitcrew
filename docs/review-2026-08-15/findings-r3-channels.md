# Round 3, F1 + F2 — the measurement layer

## THE AXIS IS SETTLED. Yaw is `angvel_y`. No live capture needed.

Three independent proofs from the owner's own stored data, all agreeing:

1. **The vertical axis is world +Y, proved by a channel already in every blob.**
   `road_plane_y` is the road-surface normal's Y component: **0.9873 → 1.0** across all
   918,673 frames, mean 0.9991. A normal that is unit-length in Y means up is world +Y.
   Yaw is rotation about the vertical ⇒ yaw is `angvel_y`. Not inference from a name.
2. **`angvel_z` is ROLL, not merely "not yaw".** Correlated over all 132 laps against three
   candidate signals: ground-track yaw rate **−0.036**, longitudinal jerk **−0.006**, and the
   derivative of suspension roll asymmetry `(FL+RL)−(FR+RR)` **+0.622** (range +0.375 to
   +0.847). Only the roll signal responds. Matches `packet.py:243-245`'s own
   `rot_pitch, rot_yaw, rot_roll` = x, y, z ordering exactly.
3. **Integration over a closed lap.** Stored `yaw_rate` sums to **−1.6°/lap** (median, range
   −11.8 to +19.9). Ground-track yaw sums to **−360.0°/lap**, and all three circuits are
   clockwise so the sign is right. A channel returning to zero over a closed circuit is a
   bounded body-attitude rate; it cannot be yaw.

Residual uncertainty: the sign convention of `angvel_y` (+ = left or right). Thirty seconds of
live capture settles it — park flat, turn slowly through one full circle, check exactly one
axis integrates to 2π.

## REPAIR, DO NOT RE-CAPTURE — this CORRECTS the final critic

The final critic said every existing corner aggregate "must be re-captured, not re-aggregated."
**That is wrong, and the correction saves 132 laps of the owner's data.**
- Yaw and `lat_g` are **recoverable from the blob**: `pos_x`/`pos_z` are stored at full 60 Hz
  rounded to 1 cm, and at racing speed the car moves 1.3 m per frame, so a heading derivative
  over ±6 frames (0.2 s) is accurate to well under 0.01 rad/s. That reconstruction produced
  every ground-truth number here, including the 2.50 g peak and the −360.0°/lap integral.
  Corner windows are seconds long and lap-distance-keyed, so 0.2 s of smoothing costs nothing.
- Slip is recoverable **arithmetically** — divide by 2π. No information lost.
- 31 of 37 channels are physically sound.
- **Caveat, the one real limit:** the reconstruction gives GROUND-TRACK yaw, not BODY yaw —
  they differ by the rate of change of chassis sideslip. Second-order for corner metrics and
  the understeer flag; NOT second-order for any future sideslip channel. Mark the repaired
  column with its source, as the existing `lap_distance_m` repair already does.

## P1 — `slip_*` is 2π too large. VERIFIED BY THE ORCHESTRATOR.
`recorder.py:171` computes `surface_ms = abs(rps[i]) * radius[i] * _TWO_PI`, treating GT7's
per-wheel channel as rev/s. **It is rad/s** — surface speed is already `omega * radius`.
Orchestrator's own check on 2,045 straight-line coasting frames (>150 km/h, throttle <3%,
brake <3%): **median `slip_fl` = 6.2832**, ratio to 2π = **1.00000**. A rolling wheel must
read 1.0.
Consequences measured over all 918,673 frames:
- `wheelspin` true on **714,224 of 716,154 throttle-on frames (99.7%)**; corrected, 3.98%.
- `lockup` true on **271 of 129,764 brake-on frames (0.2%)**; corrected, 8.9%.
- The shipped export carries `"wheelspin": 23` on **all nine** Watkins Glen corners — a perfect
  23/23 — and **no lockup anywhere**. A driver who trail-brakes deep by design has never once
  been shown a lockup.
The declared 8% trip point is really "any wheel above 17.2% of rolling speed"; the declared
15% lockup is really an **86.5% lock**.
**The tests encode the same error:** `conftest.py:55-57 rolling_wheel_rps` synthesises rev/s,
so `test_rolling_wheels_give_unit_slip` asserts 1.0 against a fabricated input. The fixture
cannot catch the bug.
Independent sanity check: at the observed 282.66 km/h top speed with stored radius 0.355 m,
rad/s gives 221 rad/s = 2,110 rpm (correct); rev/s would give 13,300 rpm.

## P1 — `understeer-mid` is computed from roll rate, and correcting the channel does NOT rescue it
Two agents converged with different methods, and this is the important nuance:
- With the stored channel it fires on **54.2%** of 749 corner-lap windows, **22 of 25** corner
  objects. Shipped export: **7 of 9** Watkins Glen corners.
- **Ablation:** hardwiring the yaw term to True fires on **95.5-98.9%** of windows — the
  steering term alone cannot fail. `steering_deg` full lock is 180° and the driver's median
  peak is 47-155°, so a five-frame 0.5°/frame rise is just turn-in.
- Substituting ground-track yaw still fires on **59.0%** of windows and **23 of 25** corners.
So the flag has no discriminating power on either side. **It should not be emitted at all until
the detector is rebuilt** with magnitude thresholds (steering rise in deg/s, and yaw at least a
stated fraction below what speed + steering angle imply through the wheelbase — `packet.py`
exposes `wheelbase_m`, constant 2.516 m on the RSR). Both constants belong in `thresholds.py`
so `as_export()` can declare them.

## P1 — `trail-brake-instability` requires no COINCIDENCE
`_flags` ANDs two independent whole-window predicates: `_countersteered` scans the whole corner
for any sign reversal, `_braking_while_turned` scans the whole corner for any trail-brake frame.
A correction on exit and a trail-brake on entry, hundreds of ms apart, raise the flag.
**For a driver whose entire technique is trail-braking deep, it degenerates into an alias for
`countersteer`.** Measured: **234 of 749 windows (31.2%)** as built; **4 of 749 (0.5%)** with the
contract's coincidence rule. Monza carries it on T1, T2, T5 — three of six corners; should be none.

## P1 — the bottoming reference is ONE session-wide minimum, so other setup sheets can never flag
Sharpens G13. `bottoming_reference` takes the min per wheel across every counted lap of the whole
event, but an event spans several runs on several **setup sheets**, and ride height and spring
rate ARE setup values. Every lap on any other sheet sits structurally outside the 3 mm band.
Measured: event 1 (Monza) spans sheets 1 and 3 (nf_f 3.35/3.05, nf_r 3.50/3.20). Per-sheet minima
differ by **4.8 to 13.6 mm** against a 3.0 mm band. The export uses sheet 3's minima, so
`bottoming` fires on **0 of 461 Monza windows**. The driver reads "no bottoming" and leaves ride
height alone.
CLAUDE.md §3.3 item 3 says "a static/steady-state reference per car **per setup**" — per setup,
not per event. Fix: key on `(car, setup_sheet_id)` and derive from straight-line frames outside
every corner window so a corner cannot define its own floor. On the owner's data that hold-out
reference raises bottoming from 1/25 to 6/25 corner objects.

## P1/P2 — spin detection has never fired on a real lap
`incidents.py:198` thresholds `abs(yaw_rate) > 1.2 rad/s`, applied to a channel whose rms is
0.069-0.079 rad/s — seventeen times below the threshold.
Agent A: **0 spins across all 108 diagnostic laps**; ground-track yaw flags **6**.
Agent B: **1** flagged (lap 27), and on inspection it is chassis ringing over a kerb — true yaw
never exceeds 0.56 rad/s there — while true yaw flags **7**.
Both agree the stored `spin_s` on every lap row is meaningless. Blast radius: `mark_incidents`
feeds `classify_exclusions`, which decides `counted_laps`, so a lap he knows he spun on stays in
the pace, fuel and wear numbers. Agent B notes 4 of the 7 true-yaw laps are already struck by
hand, which is why it held this at P2.
**The v5 back-fill is gated on `crawl_s IS NULL` and will NOT re-run on its own** — it must be
re-triggered after the channel fix.

## P2 — `int()` truncation, and for bottoming the window VARIES WITHIN ONE SESSION
Sharpens G16. Three detectors truncate ms→frames. Bottoming demands 2 frames (33 ms) where 50 ms
is declared; countersteer 17 frames (283 ms) where 300 is declared; kerb-strike 5 frames (83 ms)
where 100 is declared.
**Worse:** `interval_ms` is recomputed per window from `t_ms`, which straddles 16.66667, so
`int()` lands either side of 3.0. Measured: **2 frames on 254 windows, 3 frames on 495** —
intervals 16.661871 to 16.671329. Two corners of the same circuit are tested against different
rules and the export declares neither.
Fix: `math.ceil`, and take the interval from the lap's stored `sample_hz` rather than re-deriving
per window.

## P2 — `thresholds.as_export()` omits the constants deciding four of eight flags
Omits `BOTTOMING_MIN_MS`, `BOTTOMING_BAND_MM` (the whole bottoming rule), `COUNTERSTEER_WINDOW_MS`,
`KERB_STRIKE_WINDOW_MS`, `TRAIL_BRAKE_MIN_BRAKE_PCT`, `THROTTLE_ON_PCT`, `BRAKE_ON_PCT`,
`ON_TRACK_SURFACES`. The understeer rule (0.5°/frame for 5 frames) is **hardcoded in
`_understeers_mid` and does not exist in thresholds.py at all**, so it can never be exported.
Contract §7.1: "Restate them in `derived.thresholds` on every export, so that retuning a detector
does not read as a change in the car."

## P2 — `countersteer` fires on CHICANE DIRECTION CHANGES
An auto-segmented corner is one speed minimum with 80 m separation, so a chicane is ONE window
and its left-right transition is a >10° sign reversal by construction. At Monza it fires on
**77/77, 71/77, 71/77** laps at T1, T2, T5 — Rettifilo, Roggia, Ascari, the circuit's three
chicanes — and 12/76 and 1/77 at the four single-direction corners. Median magnitudes of the two
sides at T1: **72° and 14°** — a full direction change, then the trace clipping past the 10°
threshold. Not a correction.

## P2 — `lat_g` is speed × ROLL rate; the FORMULA IS CORRECT, the axis is the whole error
`abs(speed_ms * angvel_z)/9.81` is the right expression for v·ω_yaw applied to the wrong ω.
Recomputing from ground-track yaw gives a per-lap 99.9th percentile of **2.50 g** (p10 2.09,
p90 2.83) — exactly the 2-3 g a Gr.3 car produces. Stored gives 3.17 g p99.9 and a max of
**8.463 g**. Held at P2 only because **nothing reads it** — grep returns recorder.py:58, 308, 326
and nothing else, and the contract has no lateral-g field.

## P2 — below 2 m/s the slip channels store a SYNTHETIC 1.0
`_slip_ratios` returns a hard `(1.0,1.0,1.0,1.0)` below `_MIN_SPEED_FOR_SLIP_MS`, written with
nothing marking it unmeasured — and 1.0 is exactly "rolling true", the most benign REAL reading
the channel has. 30,172 frames (3.3%).
**Sharp observation:** the 2π bug is currently the only thing making the fabrication detectable
(a genuine rolling-true reading stores as 6.283, and an exact 1.0 never occurs above 2 m/s in
918,673 frames). **Fixing 2π removes that accidental separation** — so the two fixes must land
together, with the floor returning `None`. CLAUDE.md §4.3: 1.0 is this channel's zero.

## `captures/` IS NOT REAL TELEMETRY — CLAUDE.md §7 fixture does not exist
All **2,030 datagrams across all 204 files are byte-identical copies of one synthetic packet**
(`packet_id = 0`, `speed_ms = 40.0`, `angvel_x = angvel_y = angvel_z = 0.0`). One file has zero
records; record timestamps span 0.6 ms. A test artefact, not telemetry.
CLAUDE.md §7 asks for a real recorded session checked in as THE test fixture. There isn't one —
**the raw-capture path has never been exercised against a live stream in a form anyone kept.**
Worth fixing before UAT independently of everything else.

## Channel audit: 6 of 37 outside plausible range, all from two lines of code
Sound and explicitly confirmed: `speed_kph`, `throttle_pct`/`brake_pct` (0-255→% applied exactly
once), `steering_deg` (**correlates +0.922 with ground-track yaw**, hard-clamps at ±180.00 with
**0 wrap events**), `steering_norm` (normalised by π, confirmed — the 1080° rim would not clamp
at exactly ±1.0), `susp_mm_*` (travel range 75-81 mm, correct order), `body_height_mm` (median
50.6 mm — real ride heights in mm not metres), `surf_*`, `gear` (0 only at 0-19.9 km/h),
`rpm`, `rev_limiter`, `pos_*`, `road_plane_d` (**name now honest** after the prior repair),
`road_plane_y`, `time_of_day_ms`, `fuel_l`.
Watch items: `temp_*` reaches 185.9 °C but only 0.079% of samples exceed 130 °C — consistent with
lockup/wheelspin spikes, not falsified; corner means FL 74.0 / FR 69.5 / RL 81.2 / RR 78.7 is a
sane rear-biased RWD asymmetry. `lap_distance_m` integrates 0.8% short at Monza, 1.5% at Yas,
**2.5% at Watkins Glen** — outside the "within a percent" claim in `repair_frames`' own docstring,
though consistent lap to lap, which is what corner windows need.
`tyre_radius_m`: the column is generic but the source is `packet.tyre_radius_rl` only
(recorder.py:339) — correct as the driven-wheel radius for `gearing.py` on three RWD cars,
**would need revisiting for an AWD car.**

## FLAG RATES — as built vs all corrections applied (749 windows, 25 corner objects)
```
flag                     as built          corrected       objects (built->corrected)
bottoming                  8 ( 1.1%)        42 ( 5.6%)        1/25 ->  6/25
countersteer             272 (36.3%)       272 (36.3%)        8/25 ->  8/25
wheelspin                747 (99.7%)       396 (52.9%)       25/25 -> 18/25
lockup                     2 ( 0.3%)        76 (10.1%)        0/25 ->  8/25
trail-brake-instability  234 (31.2%)         4 ( 0.5%)*       5/25 ->  0/25
understeer-mid           406 (54.2%)       442 (59.0%)       22/25 -> 23/25
off-track                 70 ( 9.3%)        70 ( 9.3%)        1/25 ->  1/25
kerb-strike              363 (48.5%)       372 (49.7%)       14/25 -> 14/25
```
*with the contract's coincidence rule applied

**Verdicts per flag:**
- `wheelspin` — **NOISE.** 99.7% of windows, all 25 corners. Nothing in the shipped export's
  wheelspin column is information.
- `lockup` — **NOISE (dead).** 2 windows in 749, 0 corners.
- `understeer-mid` — **NOISE.** Fails on both sides; correcting the channel does not save it.
- `trail-brake-instability` — **NOISE.** 234 → 4 with the coincidence rule.
- `bottoming` — **CONTAMINATED and currently silent** (0 of 461 Monza windows).
- `countersteer` — **CONTAMINATED.** Marks chicane transitions.
- `kerb-strike` — **CONTAMINATED (mildly).** Reads `susp_mm_*` directly; no correction moves it
  materially. Most defensible of the derived flags, but 48.5% still deserves a threshold review.
- `off-track` — **TRUSTWORTHY.** Direct read of `surf_*` against the contract's rule, unchanged
  by every correction. (`incidents.py:186` requires two wheels off where `_off_track` requires
  one; the contract says one, so `corners.py` is right and the difference is intentional.)

Only ONE of the five payloads in `exports/` has a `corners` section at all — consistent with
corner detection having been broken until the `road_distance_m` repair. Rebuilt with all
corrections, its nine corners go: `understeer-mid` 7/9 → 8/9, `wheelspin` 9/9 → 6/9,
`bottoming` 0/9 → 1/9, `lockup` 0/9 → 2/9. **T3 loses its only flag; T6 swaps wheelspin for
lockup.**
