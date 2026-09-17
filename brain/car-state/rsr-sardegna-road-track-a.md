# Porsche 911 RSR (991) '17 — Sardegna Road Track, Layout A

**The ONLY place a setup value for this car+circuit may be written.** Every
other file links here and restates nothing — including the chat that issued it.
Each run records its source: **SCREEN** (settings screenshot — ground truth) ·
**FEED** (telemetry; the gearbox is the only value the feed can verify) ·
**ISSUED** (a request, not a reading).

**Event 11 · NGR Porsche Cup Rd. 9 · GT7 v1.71 · no BoP, open tuning**
*(confirmed by the driver, 5 Sep 2026 — gearbox and performance ARE settable.)*

```
  50 MINUTES, timed  ->  ~27 laps        events.race_laps holds MINUTES when
  8x tyre / 3x fuel                      race_type='time' — execution.py:31
  0 mandatory stops · rolling start
  Weather changeable, rule Random · RS / RM / RH / IM / HW
  Refuel 1.0 L/s (hub) · pit loss 20.0 s declared (track ref: 20-22 s, low conf.)
  Layout A · 5,113 m · 15 corners · Gr.3 ~1:50-1:54
```

**Range record: measured 21 Aug 2026, GT7 v1.71, verified.** Its endpoints
reconcile exactly with Rev C §5's percentages, which is an independent check
that both records describe the same car. *(`measured_date` reads 2026-09-05
because a re-save restamps it — the endpoints did not move. RECONCILIATION AL4.)*

---

# Rev A — **SCREEN, confirmed in the car 5 Sep 2026**

Carried from **`_inbox/setups/2026-08-21-rsr-monza-revC.md` §5** (SCREEN,
confirmed on the car 21 Aug 2026). **Three values change for this circuit.**
Everything else is byte-identical to Monza.

> ✅ **Settings screenshot read 5 Sep 2026: 14 of 14 visible values match this
> sheet exactly** — tyres, downforce, body height, ARB, both damping pairs,
> natural frequency, camber, toe, and all three differential axes. **This is
> the first fully clean rank-zero check on file** after five consecutive
> sessions in which the record was wrong. The RSR is now the only car whose
> record and car are known to agree.
>
> ⚠️ **Not visible on that screen and still unverified: the six gear ratios and
> the final gear** (behind *Manual Adjustment*), and brake balance (in-car, and
> separately confirmed `0` by the driver the same day).

```
                                RACE (Rev A)              QUALIFYING (Rev A)
──────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound          Racing Hard  [see §3]      Racing Soft
  Rear compound           Racing Hard  [see §3]      Racing Soft

SUSPENSION
  Body height    Front    60 mm · 20.0%              60 mm · 20.0%   <- NOT lowered
                 Rear     68 mm · 26.7%              68 mm · 26.7%   <- NOT lowered
  Anti-roll bar  Front    5 · 44.4%                  6 · 55.6%
                 Rear     3 · 22.2%                  4 · 33.3%
  Damping compr. Front    23 · 15.0%                 25 · 25.0%
                 Rear     25 · 25.0%                 27 · 35.0%
  Damping expan. Front    38 · 26.7%                 39 · 30.0%
                 Rear     38 · 26.7%   <- CHANGED    40 · 33.3%
  Natural freq.  Front    3.40 Hz · 20.0%  <- CHANGED  3.55 Hz · 27.5%
                 Rear     3.60 Hz · 30.0%  <- CHANGED  3.75 Hz · 37.5%
  Camber angle   Front    1.0 deg · 16.7%            1.2 deg · 20.0%
                 Rear     1.0 deg · 16.7%            1.2 deg · 20.0%
  Toe angle      Front    0.00 deg                   -0.05 deg
                 Rear     +0.08 deg                  +0.05 deg

DIFFERENTIAL  — absolutes on this sheet. The absolutes-only rule is RETIRED
               (retired 11 Sep 2026: all four cars read on v1.71 carry 0-30 / 0-100 / 0-100 - `11`)
  Initial torque          5                          5
  Acceleration sens.      14   [see §4]              16
  Braking sens.           24                         22

AERODYNAMICS
  Downforce      Front    400 · 50.0%  <- CHANGED    400 · 50.0%
                 Rear     600 · 50.0%  <- CHANGED    600 · 50.0%

BRAKES
  Brake balance           0                          0
                          CONFIRMED 0 IN THE CAR, driver, 5 Sep 2026.
                          Do NOT move forward — standing refusal.

PERFORMANCE — SCREEN, 5 Sep 2026. Nothing here is a tuning lever on this sheet.
  ECU output adjustment   100 %                     100 %
  Ballast / positioning   0 kg / 0                  0 kg / 0
  Power restrictor        100 %                     100 %
  Nitrous / overtake      None                      None
  Torque-vectoring CD     None                      None
  F/R torque distribution 0 : 100  (RWD — this is why the differential's
                          FRONT column reads 0/0/0 and only the rear column
                          is operative)

TRANSMISSION  — unchanged pending the Vmax lap, §5
  Top Speed (Auto Adj.)   READS 300 km/h — see §5.1. This is a READOUT of the
                          ratios below, NOT the 200 generator input.
  Gear ratios             2.727 / 1.925 / 1.529 / 1.288 / 1.152 / 1.062
                          ⚠️ NOT yet read off the screen — behind Manual Adjustment
  Final gear              3.550                     ⚠️ likewise unverified
  Short-shift             on the beep — 7,400 rpm in 1st-5th, 8,500 in 6th
──────────────────────────────────────────────────────────────────────────────
```

> ⟂ **League limits, from the hub (added 7 Sep 2026):** Porsche Cup
> `carRegulations` — **509 BHP, 1,243 kg, drivetrain MR**. Every sheet on
> this file is bounded by them; the app's event row now carries them as
> `power_limit_bhp` / `weight_limit_kg`.

## 0. What the settings screen confirmed on its own account

Three facts the screenshot settles that were previously assumed, single-sourced
or void. All **SCREEN, 5 Sep 2026, GT7 v1.71**.

| Fact | Was | Now |
|---|---|---|
| **Drivetrain MR** | `07-car-profiles.md` §0.1, called "the highest-value single line in this document" | ✅ **Confirmed on the car, post-1.71.** The screen reads `Drivetrain MR` |
| **Front-rear weight balance 46 : 54** | §0.1: a single GTPlanet screenshot from March 2022, flagged *"single-source and unverified against current BoP"* | ✅ **Confirmed on the car, post-1.71.** No longer single-source, and the MR playbook it justifies is safe |
| **Performance Points** | 720.74, **void** — PP was recalculated fleet-wide by 1.71 | ✅ **Stock 720.40 · this tune 756.32.** Re-read as `16` §12 Job 4 required. No round on file declares a `pp_cap`, so 756.32 is unconstrained — worth one glance at the regs |

**Not interpreted: the Stability readout** (Low −0.31, High −0.35, both marked
*Neutral*, against a stock −0.33 / −0.18). There is no documented sign
convention for this instrument anywhere in the knowledge base. The direction is
consistent with the added downforce, but "consistent with" is not a reading.
**Recorded, not used.** If it is ever calibrated, this is a baseline datapoint.

## 1. Why only three values moved

Monza is the lowest-downforce circuit in the game and the Monza sheet is
trimmed accordingly — downforce at 20%/20%, springs at 2.5%/10%, near the
floor of both ranges. Sardegna A is a **medium-downforce, continuously
undulating** circuit of sustained-load sweepers (`05` §2.12). Those two facts
are the entire delta.

- **Aero to the midpoint, by equal percentage front and rear.** 20%/20% ->
  50%/50%. Moving both by the same fraction of range leaves the aero balance
  exactly where he is used to it; only the level changed.
- **Springs up, 2.5%/10% -> 20%/30%.** Same +10 pp front-to-rear offset he
  already runs. This is what carries the undulation.
- **Rear expansion damping 34 -> 38**, matching the front, for the crests.
  On an MR car with a rearward static bias a fast-extending rear goes light
  over a crest. **This is the least-evidenced of the three and the first to
  back out.**

## 2. Two lines of the track reference were REFUSED

`05-track-reference.md` §2.12 recommends both of these at Sardegna. Both are
standing driver refusals. RECONCILIATION AL1/AL2.

| Doctrine says | Refused because | What was done instead |
|---|---|---|
| *"ride height 2 clicks up"* | Driver, 1 Sep 2026: *"increasing ride height should be a last option not a first."* The Spa lesson is the same shape — **being soft is why the car had to be high** | Springs took the undulation. Height held at 60/68 |
| *"brake bias one to two clicks forward"* | Standing refusal — front bias locks his fronts and creates understeer | `bb 0`. His lever is LSD braking sensitivity, already at 24 |

**Ride height is also held for QUALIFYING**, departing from Rev C which
dropped it to 58/65 at Monza. Monza is flat; Sardegna's defining feature is
continuous elevation, and dropping the car 2/3 mm over crests it has never
driven risks the exact bottoming the springs were raised to prevent. Take the
quali gain from ARBs, damping, camber and the RS tyre instead. **[DOCTRINE]**

## 3. The compound call cannot be made yet — and it decides the stop count

**Fuel does not bind here. The tyre does. That is the opposite of Monza.**

| | Evidence | Status |
|---|---|---|
| Fuel, short-shifting | **5.282 L/lap**, 10 laps, Monza | MEASURED on v1.71 |
| Fuel, map 1 full RPM | 6.736 L/lap, 2 laps, Monza | PROVISIONAL |
| Fuel at Sardegna | **4.4-5.4 L/lap** — 88% of Monza's length at ~58% full throttle, but more wing | **[ASSUMED]** |
| Tank range | at least 18.5 laps even pessimistically, of 27 | one stop covers it |
| **Tyre, RH at 8x** | **worst wheel REAR-LEFT, 0.05897 and 0.06034 /lap** (Monza session 52, two stints, `wear_source = hud-video`) -> **L = 0.85/w = 14.1-14.4 laps** | **VOID TWICE: pre-1.71, and Monza** |

1.71 adjusted tyre heating and wear values. Rev C §3.3 flagged tyre life as the
one unknown that can change the stop count and **it is still open**. Sardegna's
sustained-load sweepers should be harder on tyres than Monza's short corners,
so the honest expectation is *worse than 14 laps, not better*.

```
  w <= 0.055/lap  ->  L >= 15.5  ->  ONE STOP (14+13), held late as the weather stop
  w  ~ 0.060/lap  ->  L  ~ 14.2  ->  ONE STOP, no margin
  w >= 0.068/lap  ->  L <= 12.5  ->  TWO STOPS, +21 s of transit
```

**Run 2 below settles this.** Until it does, the plan is one stop as the working
case with two stops live, and that is stated as uncertainty, not hidden.

## 4. Why LSD acceleration stayed at 14

`05` §2.12 says 22-28 for Sardegna's hairpin exit. **Not taken.** Rev C holds
the LSD acceleration question open as a **full-span sweep** (`16` §12 Job 2B),
not a slider nudge: 1.71 cut the wheelspin it manages by 40-60%, doubled its
range to 0-100, and replaced the torque map it was tuned against. Nudging
toward doctrine answers an open question with a guess. The sweep is its own
run and it is not this weekend's priority.

## 5. Gearing — hold, then act on one lap without asking

### 5.1 The screen reads 300, the record says 200, and they do not disagree

Rev C §5 writes the transmission line as *"Max speed setting 200 km/h —
generator only. SET FIRST, THEN NEVER AGAIN."* The car's screen reads
**Top Speed (Automatically Adjusted): 300 km/h**. That looks like the record
being wrong for a sixth session. **It is not, and here is the check:**

```
  Rev C MEASURED 6th at the limiter, on v1.71   =  302.1 km/h
  K / (ratio6 x final) = 1139 / (1.062 x 3.550) =  302.1 km/h
  The screen's auto-adjusted readout            =  300     km/h   (0.7% apart)
```

**200 was the generator input used to lay the ratios out; 300 is GT7's computed
readout of the ratios that resulted.** They are different quantities and both
are correct. The readout independently corroborates the measured limiter speed.

⚠️ **But Rev C's wording invites exactly this misreading**, and a value that
looks wrong on the screen is how a sheet gets "corrected" back to something it
never was. Amend Rev C's line to name it as the *generator input* and record
the readout beside it.

⛔ **The one thing this does NOT prove is that the ratios are unchanged.** The
readout would also sit near 300 for a box regenerated at a top-speed setting of
300. **Open Manual Adjustment and read the six ratios and the final gear before
run 3** — if they are not `2.727 / 1.925 / 1.529 / 1.288 / 1.152 / 1.062` and
`3.550`, then K = 1,139 does not apply and §5.2's table below is void.

### 5.2 The table

Monza Rev C measured, on v1.71: **6th at the limiter = 302.1 km/h**,
**K = 1,139**, limiter **8,600 rpm**, peak power 8,100 rpm.

The current final gear of 3.550 puts the limiter at 302.1 km/h. **Sardegna's
back straight will not reach that**, so 6th is almost certainly too long and
the top of the box is wasted. But the terminal speed here is unmeasured and
will not be guessed.

**Measure clean Vmax in 6th down the back straight, then read this table.**
Formula: `final gear = 1,139 / (1.062 x clean Vmax x 1.03)`, where x1.03 is a
tow allowance **[ASSUMED — Sardegna's tow is unmeasured]**.

| Clean Vmax measured | Target at limiter | **Set final gear to** |
|---|---|---|
| 240 km/h | 247 | **4.34** |
| 250 km/h | 258 | **4.17** |
| 260 km/h | 268 | **4.01** |
| 270 km/h | 278 | **3.86** |
| 280 km/h | 288 | **3.72** |
| 290 km/h | 299 | **3.59** |
| *293 km/h* | *302* | *3.550 — current, no change needed* |

**Final gear shortens every gear, not just 6th.** `05` §2.12 wants **2nd for
the hairpin**; if 2nd becomes too short there, the fix is the `top` generator
value and a full regeneration, not a second final-gear trim. Check the hairpin
on the next lap after any change.

## 6. The runs — 18 laps, about 35 minutes

1. **Shakedown, 3 clean laps.** Confirms the sheet and gives a first lap time.
2. **12 laps on RH at 8x, race pace, full tank, gauge read at laps 5 and 10.**
   **This is the whole job.** It returns `w` *and* the fuel burn from one run —
   §5.2 requires race pace from a full tank anyway. It settles one stop vs two,
   and it is the run Rev C asked for on 21 August. **If there is time for only
   one run, this is it.**
3. **3 laps for terminal speed** down the back straight, then §5's table.

## 7. Predictions — check these at the debrief

- **The springs should let the platform settle faster over the crests without
  sinking.** **Falsified if** the car feels harsh over the moderate kerbs or
  loses rear grip on sweeper exits — then the spring move is wrong and rear
  expansion damping (§1) is the first thing back out, before the springs.
- **`w` at or below 0.055/lap kills the two-stop worry**, and the plan becomes
  one stop held late to double as the weather stop, exactly as at Monza.
  **Falsified if** `w` is 0.068 or above — then it is two stops and +21 s.
- **Fuel lands between 4.4 and 5.4 L/lap short-shifting.** **Falsified**
  outside that band, which would mean the throttle-share scaling from Monza is
  the wrong model and needs replacing with a measurement, not a correction.

## 8. Still open on this car+circuit

- **Wheel / FFB settings after 1.71.** Unconfirmed across the whole programme.
  1.71 changed force feedback, understeer vibration and the Fanatec Auto Setup
  parameters. On an 18 Nm base an FFB change reads exactly like a grip change,
  and Rev A is about to be judged on feel. **Confirm before run 1.**
- **Compound.** RH assumed on the Monza precedent at the same 8x. RM's wear
  ratio has never been measured on any version.
- **Pit loss at Sardegna.** Declared 20.0 s; track reference says 20-22 s at
  low confidence. Never measured here. It is a track constant — measure once.

---

## Change log

| Date | Rev | What | Source |
|---|---|---|---|
| 5 Sep 2026 | A | First sheet. nf 3.05/3.20 -> 3.40/3.60, df 370/540 -> 400/600, de_r 34 -> 38. All else carried from Monza Rev C | ISSUED |
| 5 Sep 2026 | — | `bb 0` confirmed present in the car; no BoP, open tuning confirmed | driver |
| 5 Sep 2026 | A | **Settings screenshot: 14 of 14 visible values match Rev A.** First clean rank-zero check on file | SCREEN |
| 5 Sep 2026 | — | MR and 46:54 weight balance confirmed post-1.71; PP re-read, stock 720.40 / tuned 756.32 | SCREEN |
| 5 Sep 2026 | — | Top Speed readout 300 reconciled against the measured 302.1 limiter — see §5.1. Gear ratios still unread | SCREEN |

---

# Session 128 — Rev A ran. 5 Sep 2026, 15 laps, GT7 v1.71

**Rank zero CLOSED, both halves, for the first time on this programme.**
14 of 14 visible values by SCREEN; the six gear ratios by **FEED**, byte-identical
on all 15 laps (`2.727 / 1.925 / 1.529 / 1.288 / 1.152 / 1.062`). The final drive
is still not directly readable, but K = 1,139 with 3.550 reproduces 302.1 km/h,
which matches the screen's 300 readout — corroborated, not verified.

Clean laps 4, 7, 8, 9, 11, 12, 14, 15 (no spin, no crawl, off-track under 0.6 s):
`106.431 · 103.340 · 103.857 · 103.090 · 103.138 · 103.068 · 106.435 · 102.917`.
**Lap 2 108.802 -> lap 15 102.917: -5.9 s across one run.** The driver's own read —
*"more about learning the track"* — is correct and it dominates every setup effect
on file. No lap-time comparison is worth anything here yet.

## The three Rev A predictions

| Prediction | Outcome |
|---|---|
| Springs settle the platform without sinking | ✅ **HELD.** Body height min 16.72 mm, but only **0.27%** of 46,241 clean frames below 25 mm, **all four wheels on tarmac**, at median **262 km/h** and lat_g **0.27** — straight-line aero compression at lap distance 100-200 m and 4,500-4,600 m, i.e. the two ends of the main straight. Not a kerb strike, not cornering bottoming. Driver reported no harshness |
| `w` at or below 0.055/lap kills the two-stop case | ❌ **UNTESTED.** `wear_fl` is null on all 15 laps — **the gauge sampled nothing.** Known cause: the wear sampler stops permanently ~30 s in with no OBS windowed projector open |
| Fuel 4.4-5.4 L/lap short-shifting | ❌ **FALSIFIED as a model**, untested as stated — **he had no beep to short-shift on, because no shift table existed.** Measured at full RPM: **6.29-6.61, median 6.50 L/lap** |

### Why the fuel model was wrong, and the correction

I scaled Monza's burn by **distance** (Sardegna is 88% of Monza) and throttle
share. Per **second** the two circuits are the other way round:

```
  Monza    6.736 L/lap / 109.5 s = 0.0615 L/s     (full RPM, v1.71)
  Sardegna 6.500 L/lap / 103.0 s = 0.0631 L/s     +2.6%
```

**Fuel tracks time under load, not distance** — and Rev A's extra wing adds drag,
which is the +2.6%. Corrected model for any future circuit: take the measured
L/s, multiply by this circuit's lap time, add 2-3% for a downforce increase.

## The balance finding — driver and telemetry AGREE

Driver report: *"could be a little bit more pointed on entry and rotate mid
corner more."* **[DRIVER REPORT]**

**7,326 braking frames, clean laps, all four wheels on tarmac. [MEASURED]**

```
  front axle below 0.90 slip   15.89%        deepest front   0.8227
  rear  axle below 0.90 slip    0.00%        deepest rear    0.9209
                                (zero frames, not a rounding)

  cornering-braking frames:  front mean 0.9528  ·  rear mean 0.9728  ·  gap -0.0200
```

**His fronts lock. His rears never do.** A locked front tyre makes no lateral
force, which is exactly a car that will not point.

### Where it lives — and it is NOT aero

| Speed band | front < 0.90 | rear < 0.90 |
|---|---|---|
| 0-80 km/h | 18.90% | 0.00% |
| 80-120 | 8.99% | 0.00% |
| **120-160** | **23.68%** | 0.00% |
| **160-200** | **27.24%** | 0.00% |
| 200-300 | 4.29% | 0.00% |

It peaks at **120-200 km/h** and is at its *best* above 200. An aero-balance
fault would be worst where aero is strongest. **This is mechanical.**

### A reading I made and then retracted in the same pass

Pooled over all braking frames the front L/R split reads **FL-FR = -0.0135**,
which looks like a standing left-front bias against a measured floor of
0.003-0.006. **Split by corner direction it flips sign symmetrically**
(-0.0258 turning one way, +0.0201 the other). It is the **inside front
unloading**, not a car asymmetry, and the pooled figure was an artefact of this
circuit turning predominantly one way (10,776 frames against 6,923). **No toe
asymmetry to fix here.** Unlike Daytona Run 4, where the same signature was real.

### And an error of mine in Rev A itself

Rev A §1 claims moving downforce *"by the same fraction of range leaves the aero
balance exactly where he is used to it."* **That is wrong.** `df_f` spans 100 and
`df_r` spans 200, so 50% of each is not the same absolute change:

```
  Monza     370 / 540  ->  front share 40.7%
  Rev A     400 / 600  ->  front share 40.0%     the front went DOWN
```

Small, and in the direction of his complaint — but the speed-band table above
says aero is not the cause, so **this is a correction to make, not the fix to
try.** Restoring the Monza ratio at rear 600 would be `df_f 411`. **Held back**
so it does not confound the brake-balance run.

## Rev B — ONE change

**Brake balance one click REARWARD.** The rear axle is at **0.00%** lock
incidence across 7,326 braking frames; it has the entire margin. This is the
lever his own doctrine reaches for and the one the data points at.

⚠️ **Which sign is rearward on this car is not established.** `brain/driver.md`
records the Shelby at `bb -1` = forward and the Huracán at `bb +1` = rearward —
**both consistent with negative = forward, positive = rearward**, though the
refusal card warns signs differ by car. Expectation is `bb +1`; **confirm on the
MFD before running.** See RECONCILIATION AM2.

### The falsifier, and why it is not the obvious number

⛔ **Do NOT judge this on the front-lock percentage.** Its measured noise floor
is **8.5-9.6 pp** and the change worth making is smaller than that — the same
trap that retracted a 5.9 pp toe finding once already.

✅ **Judge it on the front-minus-rear mean slip gap in braking frames**, now
**-0.0200**. Both axles are read in the same frame, so session variation cancels;
the nearest measured floor for that class of instrument is the front L/R split's
**0.003-0.006**.

- **Predicts:** the gap narrows to **-0.010 or shallower** — 2-3x the floor.
- **Falsified if:** rear frames below 0.90 exceed **2%**, or he reports the rear
  stepping out on entry. Either means the click went too far or the wrong way.
- **Cost:** 3 clean laps.

## The gearbox is the bigger prize, and it is a separate run

```
  6th gear:  NEVER ENGAGED — 0 frames of 48,640 clean tarmac frames
  5th gear:  11.8% of the lap · top speed reached 265.1 km/h
  1st gear:  16.3% of the lap
  rev limiter firing: 666 frames per 8 laps  = ~1.4 s/lap bouncing, gears 1-3
```

The box is Monza's, cut for 302.1 km/h at the limiter, on a circuit that reaches
265. **Two of six gears are dead weight and he is hitting the limiter in the
three he uses most.** That is a spread problem, not a final-drive problem — the
fix is the `top` generator and a full regeneration, then I compute the final
drive from K = 1,139. **It re-issues the shift table.**

## Shift table — ISSUED 5 Sep 2026, `shift_points` id 1

```
  performance   1: 8500   2: 8500   3: 8500   4: 8500      5, 6: SILENT
  fuel saving   1: 7400   2: 7400   3: 7400   4: 7400      5, 6: SILENT
```

Performance from the RSR archive over 270 laps: this gear still wins at every
comparable bin up to 8,500 rpm in 1st-4th, so hold to 8,500 — just under the
limiter measured here (median **8,618** in 1st). That also removes the bouncing.
**5 and 6 are absent on purpose**: 6th is never engaged and 5th is the top gear
used, so there is no upshift to cue and a padded number would sound identical to
a measured one. Fuel table is the 7,400 he already ran at Monza, measured there
at **-21.6% fuel for ~0.5 s/lap** [MEASURED at Monza v1.71; ASSUMED transferable].

## Strategy, re-derived on measured pace

**Lap 102.9-103.1 s, not the reference's 1:50-1:54 — that band is 7+ s wrong
(RECONCILIATION AM1). 50 min / 103 s = 29 laps, not 27.**

| | Full RPM | Short-shifting at 7,400 |
|---|---|---|
| Fuel per lap | **6.50 L** [MEASURED, 15 laps] | 5.10 L [DERIVED, -21.6%] |
| Tank range | 15.4 laps | 19.6 laps |
| 29 laps needs | 188.5 L -> add 88.5 | 147.9 L -> add 47.9 |
| One stop costs | 88.5 s refuel + 21 s transit = **110 s** | 47.9 + 21 = **69 s** |
| Lap-time price | — | ~0.5 s/lap x 29 = 14.5 s |

**Short-shifting is worth about 26 s net over the race.** That is why the beep
above matters more than any slider on this sheet.

⚠️ **The tyre is now the marginal constraint, not fuel.** One stop = two stints
of **14.5 laps**; the only wear estimate on file is **14.1-14.4 laps**, and it is
pre-1.71 and from Monza. **It is still unmeasured, and it is still the run that
matters most.** Open the OBS windowed projector before the next stint or the
gauge will sample nothing again.

---

# Gearbox — the "6th gear is unused" finding, RETRACTED as a loss. 5 Sep 2026

**Driver confirmations logged this turn:** FFB unchanged since 1.71 (rank zero 1b
CLOSED). **`bb +1` is REARWARD on this car** — the sign is now established for the
RSR and it matches the convention already implied by the Shelby and Huracán
(negative forward, positive rearward). RECONCILIATION AM2 can be closed on the
driver's word for this car.

## K, re-derived from session 128 rather than quoted

`K = speed_kph x ratio x final x (8600 / rpm)`, full throttle, off the limiter:

| gear | n | K median | p5 - p95 |
|---|---|---|---|
| 1 | 1,347 | 1081.8 | 1035 - 1107 |
| 2 | 6,149 | 1118.5 | 1090 - 1125 |
| 3 | 10,253 | 1128.6 | 1122 - 1133 |
| 4 | 10,793 | 1133.6 | 1127 - 1138 |
| 5 | 5,285 | **1137.2** | 1133 - 1141 |

**K rises with gear because low gears carry more wheel slip under power.** The
high-gear value is the honest one for top-speed work: **K = 1,137**, against
Monza Rev C's quoted 1,139. **Corroborated across two circuits and two sessions.**
Do not use the pooled 1,130.6 — it is dragged down by 1st and 2nd.

## ⛔ RETRACTED: "6th is never engaged" is not a loss

Session 128's finding stands as an observation — 0 frames of 48,640 — but the
conclusion drawn from it, that the box is *"too long"* and wants a shorter final
drive, is **wrong**. Final drive does not change gear spacing; it shifts the whole
box. So the proposed fix renames 5th as 6th and changes nothing:

```
  5th now         1.152 x 3.550 = 4.0896
  6th at 3.850    1.062 x 3.850 = 4.0887      0.02% apart

  rpm at the measured 265.1 km/h terminal:  8,199 now   ·   8,197 after
```

**Peak power is 8,100 rpm. 5th already sits at 8,199 at terminal speed.** The top
of this box is correctly sized for this circuit. There is nothing to win there,
and the earlier §"the gearbox is the bigger prize" framing overstated it.

## The real loss, and it is at the other end

```
  1st gear used from        51.5 km/h upward
  1st gear tops at         ~117   km/h
  limiter frames in 1st     316 over 8 clean laps  =  0.66 s/lap
  median speed while limited in 1st            121.8 km/h
  slowest point on the lap                      51.5 km/h (p1 66.3)
```

**`top` is set to 200 — the minimum of the [200, 800] range**, which is what
produces a very short 1st and a very long 6th simultaneously: the widest spread
the car will generate. Shortening the final drive makes 1st *worse*.

**Only `top` lengthens 1st.** Precedent for the direction, not the magnitude:
`project_rbr_short_practice_2026_08_27` — on the Shelby, raising `top` to 265
moved 1st **+46.6%** and 6th only **+3.0%**. Direction transfers; the number does
not, because the mapping is per-car.

## The probe — costs zero laps

**Set `top` = 240 and screenshot Manual Adjustment (six ratios + final drive).
Do not drive it.** `top` 200 is a known point; 240 gives a second, and two points
solve this car's mapping. Then the final drive is computed exactly from K = 1,137
to land 6th just above terminal with all six gears working and 1st long enough to
stop bouncing.

**240 is [ASSUMED] and is a probe, not a setting** — it is a transfer of the
Shelby's sensitivity, which is precisely the kind of transfer this file refuses
for a real number. If it lands tall, the second point still fixes the mapping.

## ⚠️ Do not run the gearbox and `bb +1` together

Shorter gearing raises rpm at a given road speed, which raises **engine braking on
the rear axle** — moving the front-minus-rear slip gap in the *same direction* as
`bb +1`. Run together, neither is attributable, and the Rev B falsifier is void.

**Order:** `bb +1` alone, 3 clean laps → `top` screenshot (no track time) →
gearbox → **then** the 12-lap wear stint with the OBS projector open, on the final
package, because short-shifting changes rear wear too.

**A ratio change re-issues `shift_points` id 1.** The live table is cut for the
current box.

---

# Gearbox solved against the speed trace — 5 Sep 2026, `top` 240 probe returned

## ⛔ RETRACTION: the limiter bouncing is SHIFT TIMING, not gearing

Session 128's *"666 limiter frames, 0.66 s/lap in 1st, the box is too short"* is
**wrong as a gearing conclusion.** Simulated against the session's own **32,483
full-throttle tarmac frames**, upshifting at 8,500:

```
  CURRENT box (top 300, final 3.550):  rev-limited on 0.00% of frames
  1st tops at 117.4 km/h · he was bouncing at a median of 121.8 km/h
```

**He was holding the gear past its limiter, not running out of gear.** The fix is
the shift beep already issued as `shift_points` id 1, not a ratio change. A
driving artefact was read as a hardware fault — the same class of error as
crediting the setup for what the compound did.

## `top` mapped on this car — and it is the opposite of the Shelby precedent

| | 1st | 6th | spread 1st/6th |
|---|---|---|---|
| `top` = 300 | 2.727 | 1.062 | 2.568 |
| `top` = 240 | 3.041 | 1.348 | 2.256 |

**Higher `top` = LONGER gears AND a WIDER spread.** The RBR Shelby note
(`project_rbr_short_practice_2026_08_27`) transferred the direction wrongly for
this car; only the method transferred. **`top` sets the spread; the final drive
scales the whole box without touching the spread.** Two independent levers.

**Corollary: Rev C's "Max speed setting 200" was stale.** The box was at `top`
300 all along, which is what the settings screen's "Top Speed (Automatically
Adjusted) 300" was reporting. §5.1's reconciliation of 200-versus-300 as
"generator input versus readout" is **superseded — they were the same field, and
the record was simply out of date.**

## The recommendation, scored against his own speeds

Full-throttle tarmac frames, 8 clean laps, upshift at 8,500, K = 1,137:

| box | limited | mean rpm | % above 7,500 | 1st tops | 6th tops |
|---|---|---|---|---|---|
| current top300 f3.550 | 0.00% | 7,685 | 68.0% | 117.4 | 301.6 |
| top300 f3.900 | 0.00% | 7,802 | 76.2% | 106.9 | 274.5 |
| **top240 f3.050** | **0.00%** | **7,813** | **76.9%** | **122.6** | **276.5** |
| top240 f3.100 | 0.00% | 7,833 | 78.2% | 120.6 | 272.1 |

**ISSUED: `top` 240, final drive 3.050.** Better on every axis simultaneously —
powerband share 68.0% -> 76.9%, and **1st gets LONGER** (117.4 -> 122.6), giving
the beep more room rather than less. 6th tops at 276.5, **11 km/h above the
measured solo terminal of 265.1**, which is the tow headroom; f3.100 scores
marginally higher but leaves only 7 km/h and risks meeting the limiter in a
slipstream.

**Honest size of the prize:** modest, and **invisible against a -5.9 s/lap
learning curve** — do not look for it in lap time. It is verifiable without lap
time: mean rpm at full throttle and % above 7,500 are computable from any future
session and are properties of the box, not of the driving.

## ⚠️ CONDITIONAL — the 6th-gear row does not reconcile

`K_display = speed x ratio x final` at 8,500 rpm, off the Manual Adjustment page:

```
  1st  105 x 3.041 x 3.550 = 1133.5      4th  197 x 1.621 x 3.550 = 1133.6
  2nd  137 x 2.329 x 3.550 = 1132.7      5th  221 x 1.446 x 3.550 = 1134.5
  3rd  168 x 1.900 x 3.550 = 1133.2      6th  251 x 1.348 x 3.550 = 1201.1  <- 6% out
```

Five gears agree to 0.16%. The sixth does not. **Either the ratio is 1.272 and
251 km/h is right, or the ratio is 1.348 and the speed should read 237.**

- **On 1.348 (assumed above): final drive 3.050.**
- **On 1.272: final drive 3.230.**

**Confirm the 6th row before entering the final drive.** Most likely a misread of
the screenshot rather than a game inconsistency, but the two answers are 6% apart
and that is the difference between using 6th and never reaching it.

## Shift table on the new box

`shift_points` id 1 is cut for the CURRENT box and must be re-issued once the
ratios change. On the new box 6th comes into use, so gear 5 gains an upshift:
**performance {1-4: 8500, 5: 8000}, fuel {1-5: 7400}**, 6th silent. The 5->6
point of 8,000 rpm comes from the RSR archive on the old box; the inter-gear step
changes only from 1.0847 to 1.0727, so it carries [MEASURED on the old box,
ASSUMED across this ratio change].

## Order still stands

`bb +1` alone, 3 clean laps -> gearbox -> re-issued shift table -> the 12-lap wear
stint with the OBS projector open. **Never the gearbox and `bb +1` together:**
shorter gearing raises rear-axle engine braking, moving the front-rear slip gap
the same way `bb +1` does.

---

# Session 129 — Rev B (`bb +1`) ran. 5 Sep 2026, 8 laps, GT7 v1.71

**Rank zero:** gear ratios read byte-identical to session 128 on all 8 laps, so
the box did not move — it was genuinely a one-change run. `bb` itself has no
ground truth in the feed and rests on the driver's word.

Laps: `120.803(out) · 104.224 · 109.352 · 125.991 · 104.149 · 104.907 · 104.120 ·
119.757`. **Two spins, off-track on all 8.** Only ONE lap survives session 128's
strict cleanliness filter, so every figure below is reported on **both** filters,
applied identically to both sessions.

## ❌ THE PREDICTION IS FALSIFIED

| | s128 (bb 0) | s129 (bb +1) | moved |
|---|---|---|---|
| **strict** filter, front−rear slip gap | −0.0200 | −0.0193 | **+0.0007** |
| **wider** filter, front−rear slip gap | −0.0191 | −0.0176 | **+0.0014** |

**Predicted: narrows to −0.010 or shallower.** Delivered: +0.0007 to +0.0014 —
**an order of magnitude short, and inside the instrument's own 0.003-0.006 floor.**
The rear-lock falsifier did not trip either: rear below 0.90 is **0.00%** in both.

And nothing else moved. Deceleration off the speed trace, heavy braking:

```
  s128   mean 19.04 m/s2   median 19.12   p90 23.12   p99 24.67
  s129   mean 19.05 m/s2   median 19.11   p90 23.12   p99 24.75
```

Identical to two decimal places. Rear slip under heavy braking: p5 0.9344 ->
0.9310, median 0.9605 -> 0.9594. Nothing.

## ⛔ WHY — the instrument cannot see brake balance, and this was knowable

Front slip under heavy braking piles up in a narrow band instead of spreading:

```
  s128   p25 0.8899   MEDIAN 0.9196   ·  47.2% of frames inside 0.86-0.92
  s129   p25 0.8945   MEDIAN 0.9273   ·  43.6% of frames inside 0.86-0.92
```

**That is ABS regulating, not the tyre choosing.** This project measured the ABS
working point on 24 Aug 2026 and it is set by compound: **RH = 0.112 slip, i.e. a
slip ratio of 0.888** (`project_brake_cue_and_wear_2026_08_24`). The front axle
is pinned there whatever the brake balance commands. **The slip channel measures
the ABS controller, not the bias.**

**This is my error and it was avoidable.** The proposal gate says the test must
clear the noise floor of its instrument — I checked the floor and never checked
whether the instrument was *causally connected* to the thing being changed. A
figure already in this project's own memory said it was not.

⚠️ **`events.abs_setting` is NULL for event 11.** ABS being on is *inferred from
the plateau above*, which is evidence rather than assumption — but the declared
value is missing and should be filled.

## ✅ What survives from session 128, restated correctly

The headline was *"front below 0.90 on 15.89%, rear on 0.00%."* The front half
was misread: **frames below 0.90 on the front are the front axle sitting at its
ABS working point, which is where it should be under heavy braking.** That is not
a fault.

**The rear half stands, and it is the whole finding:**

> **The rears never come near their ABS band at all** — 0.00% below 0.90, p5
> 0.931 against a working point of 0.888. The front axle is at its limit and the
> rear axle is not being asked for anything.

So the direction of Rev B was right and **one click was simply too small to change
which axle limits the car.** The rears moved p5 0.9344 -> 0.9310 and stayed far
from regulation.

## ⚠️ No driver report was given for this run

With ABS active and the slip channels pinned, **the driver's feel is the only
working instrument for brake balance.** Rule 1 makes his report primary evidence
in any case; here it is the *only* evidence. Nothing further should be changed on
this axis until he says what the car did on entry.

**Do not read the lap times.** s128 reached 102.917 across 15 laps with the track
learned in; s129 is 8 scrappy laps with two spins from a cold start. The learning
curve alone was -5.9 s/lap in the previous session.

## Where this goes next — no change issued

Three options, and the choice needs his report first:

1. **He felt it better** -> keep `bb +1`, record it, move on to the gearbox. The
   change is real and simply below what the telemetry can resolve.
2. **He felt nothing** -> the click is too small to matter. A larger step (`+2`
   to `+3`) is arguable, with **rear p5 slip** as the instrument (currently 0.931,
   room to fall ~4 points before it reaches the 0.888 ABS band) rather than
   anything on the front axle.
3. **He felt it worse / looser** -> revert to `bb 0`. His in-car trim is his to
   make and is recorded, never corrected.

**Not proposed: escalating to `+3` blind.** That is dose-escalation without an
instrument, on the axis that produced two spins this session.

---

# Rev B CONFIRMED, Rev C issued — 5 Sep 2026

## ✅ `bb +1` CONFIRMED — by the driver, on his report alone

> **[DRIVER REPORT], 5 Sep 2026:** *"more rotation on entry and I could move my
> brake markers forward."*

Both halves are gains, and no downside was reported. **`bb +1` is kept and is now
the car's state.**

**The telemetry did not disagree with him — it was BLIND.** That distinction
matters and must not be recorded as a driver-versus-data conflict: front slip
under braking is pinned by ABS at the compound working point (RH 0.888), so it
could not have moved whatever the bias did. A blind instrument is not a dissenting
witness. See `feedback_abs_pins_the_slip_channel`.

**This is the fifth consecutive session in which the driver's account beat, or
outlived, a derived metric.**

## The rear axle IS a valid instrument — measured, not assumed

Concentration inside a 0.06-wide band centred on the RH ABS working point,
heavy-braking frames (brake > 60%):

| | front | rear |
|---|---|---|
| session 128 | **46.2% inside the ABS band** — regulated | **0.0%** — free |
| session 129 | **42.4% inside the ABS band** — regulated | **0.0%** — free |

**The front axle reports the ABS controller. The rear axle reports the tyre.**
So rear slip is open-loop here and may be used as a falsifier; front slip may not.
This holds only while the rear stays out of regulation — **if a future step drives
rear p5 to ~0.888, the rear instrument goes blind too** and the driver's report
becomes the only one again.

## Rev C — `bb +1` -> `bb +3`  (ONE change)

**Evidence:** [DRIVER REPORT] the first click was all upside · [MEASURED] rear p5
slip 0.9310 against an ABS working point of 0.888, so the rear is still **0.043**
away from being asked for everything it has.

**Why two clicks rather than one.** The single measured click moved rear p5 by
**−0.0034 — exactly on the 0.003-0.006 floor.** Another single click would be
unmeasurable again. Two clicks projects to **−0.0068**, clearing the floor by
~1.5x. **This is bracketing, not dose-escalation:** if +3 overshoots, +2 is the
answer and it has been found in two runs instead of four.

- **Predicts:** rear p5 slip **0.9310 -> ~0.9242**, and the driver reports more
  entry rotation again with braking still stable.
- **Falsified if:** the rear steps out on brake RELEASE — his known signature
  (`project_daytona_run3_2026_09_03`: the rear steps out from stored steering
  cashed at the brake release). **That result means +2 is the answer, not that
  the direction was wrong.**
- **Cost:** 3 clean laps. Session 129 produced only one lap through the filter —
  two spins and off-track on all eight — so clean laps are the binding input.
- **Bound:** do not go past +3 without a new report. `bb` is 10% of range per
  click and he trail-brakes deep by design.

## Order after Rev C — unchanged, and the reason the wear stint is LAST

1. **Gearbox**, pending the 6th-gear ratio: `1.348` -> final **3.050**;
   `1.272` -> final **3.230**. Re-issues `shift_points` id 1.
2. **The 12-lap wear stint, OBS windowed projector open.** Failed to sample twice
   now. It decides one stop versus two: one stop is two stints of **14.5 laps**
   against an estimate of **14.1-14.4** that is pre-1.71 AND from Monza.

**It must run last, on the final package.** Rearward brake bias moves braking work
onto the rear axle, and **the rear was already the limiting tyre at Monza**
(rear-left worst, 0.059-0.060/lap). Measuring wear before the bias is settled
measures a car he will not race.

---

## Gearbox CONFIRMED — the 6th-gear display anomaly is systematic, 5 Sep 2026

`K_display = speed x ratio x final`, read off Manual Adjustment on both boxes:

| | gears 1-5 mean K | 6th implied K | 6th overstated by |
|---|---|---|---|
| `top` 300 (in the car) | 1134.5 (spread 4.2) | 1202.7 | **x1.0601** |
| `top` 240 (the probe) | 1133.5 (spread 1.8) | 1201.1 | **x1.0597** |

**The same factor on two different gearboxes, to four decimals.** GT7's top-gear
row is not speed-at-8,500 like the other five — it is a different quantity
(most likely an estimated terminal speed). **It is not a misread and not a game
inconsistency: the printed RATIOS are correct throughout.**

**Therefore 6th = 1.348 on the probe was right, and the answer is `top` 240 +
final drive 3.050**, as issued. The alternative reading would have been actively
harmful: at final 3.230, 6th tops at **261.1 km/h, below the measured 265.1
terminal**, putting him on the limiter down the straight — the exact fault the
change is meant to remove.

```
  top 240 · final 3.050
  1: 122.6   2: 160.1   3: 196.2   4: 230.0   5: 257.8   6: 276.5   km/h at limiter
```

**Rule for future gearbox screenshots on this car: reconcile gears 1-5 only, and
divide the 6th-gear speed by 1.060 before using it. Or ignore it and compute from
the ratio, which is what the ratio is for.**

**Status at the time of the Rev C run:** the car is on the ORIGINAL box
(`top` 300, final 3.550) — the probe was reverted, correctly, so Rev C is a
single-change run. `shift_points` id 1 is cut for this box and remains correct;
it must be re-issued when the gearbox is fitted.

---

# Session 130 + Rev D — 5 Sep 2026, GT7 v1.71

**Rank zero:** gear ratios byte-identical across sessions 128, 129 and 130 — the
box has not moved. `bb` rests on the driver's word: **`+3`, confirmed in the car.**

## ✅ Rev C CONFIRMED — and I under-predicted it by 3x

> **[DRIVER REPORT]:** *"+3 bb felt even better."*

| | bb 0 (s128) | bb +1 (s129) | bb +3 (s130) |
|---|---|---|---|
| rear p5 slip, heavy braking | 0.9344 | 0.9310 | **0.9118** |
| rear frames inside the ABS band | 0.0% | 0.0% | **6.4%** |

**Predicted 0.9242; delivered 0.9118.** The response is **super-linear** — I sized
the step by linear extrapolation from a single click and understated it ~3x.
Record that: one click is not a unit of anything on this axis.

**`bb +3` is the END of this axis, and the data says why:** the rear has begun
entering ABS regulation (0.0% -> 6.4%). Past this point the rear instrument goes
blind exactly as the front one already is, and the driver's report becomes the
only evidence again. **The bracket closed on the good side. Do not go past +3.**

## The corner he named — identified, and it is real

> **[DRIVER REPORT]:** *"having trouble with understeer mid corner still,
> especially 3rd last turn of the lap, a fast left hander."*

Segmenting his best lap (s130 lap 5, 102.865 s) on sustained lateral load, and
resolving direction from **suspension asymmetry** (a LEFT turn loads the RIGHT
wheels; GT7's channel is larger-is-more-compressed) rather than from the steering
sign, which has no established convention here:

**3rd-from-last corner = lap distance 3,641-3,788 m · LEFT · 166-177 km/h ·
peak 2.34 g.** His description matches exactly.

**[MEASURED] It is the highest-lateral-load corner on the lap** — 1.87 g mean
against the next-highest 1.73 — and he is **braking through 38%** of it (33%
coasting, 30% on throttle, across 17 clean passes). **The car is not uniquely bad
there; that corner asks for more front grip than any other, so it is where the
car runs out first.** That is why he feels it there and not elsewhere.

## ⛔ I CANNOT SEE THE UNDERSTEER — the instrument fails its own floor

Steering-per-g index (`mean|steering_norm| / mean|lat_g|`, |lat_g|>1.2) in that
corner, **17 clean passes across three sessions with the aero UNCHANGED
throughout — so this spread IS the floor**:

```
  range 0.0410 - 0.1463 · mean 0.1004 · sd 0.0312
  2sd = 0.0624 = 62.2% OF THE MEAN
```

A **3.5x spread on an unchanged car.** Pooled across every fast corner (>150 km/h)
the floor only falls to **31.3%**. **No claim about mid-corner balance can be
carried by this instrument, at this corner or pooled.** This is the charter's
corner-noise finding reproducing itself on a new circuit.

**So the change below is bought by the DRIVER REPORT, which is permitted — a
telemetry-only flag may not buy a setup change, but a driver report may.** The
verdict on it will also be his; there is no telemetry arbiter available.

## ❌ And it corrects an error of mine, in the same direction

Rev A §1 claimed equal-percentage-of-range aero was balance-neutral. `df_f` spans
100 and `df_r` spans 200, so it was not:

```
  Monza    370 / 540   front share 40.66%
  Rev A    400 / 600   front share 40.00%   <- front aero was REMOVED
  Rev D    420 / 600   front share 41.18%
```

Downforce scales with v-squared, so the error bites hardest at exactly the corner
he named. Held back during the brake-balance work to avoid confounding it; that
work is now closed.

## Rev D — ONE change: `df_f` 400 -> 420 (50% -> 70% of range)

- **Predicts:** more front bite mid-corner, most noticeably at the fast left.
- **Falsified if:** the rear feels loose on the way OUT of the fast corners —
  the signature of too much front wing. **That result means 410 is the answer,**
  not that the direction was wrong.
- **Instrument:** his report. **The telemetry cannot arbitrate this** (62% floor)
  and must not be quoted as if it could.
- **Cost:** 3 clean laps.

## Gearbox — issued, to be fitted AFTER the aero run

```
  top 240 · final 3.050 · ratios 3.041 / 2.329 / 1.900 / 1.621 / 1.446 / 1.348
  km/h at the 8,600 limiter:  1:122.6  2:160.1  3:196.2  4:230.0  5:257.8  6:276.5
  terminal 265.1 lands in 6th (5th tops 257.8) with 11 km/h of tow headroom
  1st gets LONGER: 117.4 -> 122.6, so the beep gains room rather than losing it
```

**⚠️ The new shift table is deliberately NOT written yet.** `shift_points` id 1 is
cut for the CURRENT box. Writing the new table before the box is fitted would beep
a 5->6 upshift he cannot use on the old box, and **a wrong beep is worse than
silence** — the beep is held to the live-call standard. Issue it the moment he
confirms the gearbox is in: **8,500 in gears 1-4, 8,000 in 5th** (measured over
270 RSR laps), **7,400 fuel-saving in 1-5**, 6th silent.

## ⚠️ Why the aero and the gearbox must not go in together

The new box changes **which gear he is in through the named corner** and raises
rpm at a given road speed — so **rear-axle engine braking changes on a corner
where he is on the brakes 38% of the time.** With no telemetry arbiter for
balance, his report is the entire verdict, and it has to be clean.

**Order:** `df_f` 420 alone (3 laps) -> gearbox + new shift table (3 laps) ->
**12-lap wear stint, OBS projector open** (race-critical, failed to sample twice).
**If time is short, drop the gearbox, not the wear stint.** One stop needs two
stints of 14.5 laps against an estimate of 14.1-14.4 that is pre-1.71 AND from
Monza.

---

# Session 131 — Rev D (`df_f` 420) ran. 5 Sep 2026, 4 laps

**Rank zero:** gearbox byte-identical across 128/129/130/131. `bb +3` and
`df_f 420` rest on the driver's word.

**Cleanest session of the day: 3 clean laps of 3, ZERO spins**, off-track
0.08-1.15 s — against session 130's two spins. Lap times 103.820 / 103.315 /
103.170. Not a comparison (3 laps, no time to build) but the tidiness is worth
noting; it is consistent with a more predictable car and equally with him
settling, and **it cannot be attributed.**

## ✅ Rev D CONFIRMED — on the driver's report, as designed

> **[DRIVER REPORT]:** *"that's much better, probably still some adjustment to
> make it perfect but def better."*

The change was bought by his report and the verdict is his report. **The
telemetry was never going to arbitrate this** (62% floor) and it did not.

## ✅ [MEASURED] Twenty units of front wing cost NO measurable top speed

```
  df_f 400   s128 mean 260.4  ·  s129 262.3  ·  s130 260.8
  df_f 420   s131 mean 261.2   [261.5, 261.2, 261.0]
```

All inside the project's measured terminal floor of **0.56-2.77 km/h**, and
s131's own spread (0.5 km/h over 3 laps) is the tightest on file here. **There is
drag headroom to add more front wing.** This is a real measurement and it is what
licenses Rev E.

## ⛔ RETRACTED IN THE SAME PASS: the lateral-g "confirmation"

Peak lat_g in the named corner rose **2.191 -> 2.824 (+0.633 g)** against a
**within-session** floor of 0.532 g (s128, 11 laps, one setup, sd 0.152). All
high-g frames on tarmac, no kerb strike. It reads like a clean hit.

**The control kills it.** Between s128 and s129 the same number moved **+0.411 g
with NO aero change** — a brake-balance click plus a session of learning. The
cleanest available comparison, s130 -> s131 (same `bb`, aero the only difference),
is **+0.456**. **A no-change drift of the same magnitude exists, so the effect is
not attributable.**

**The lesson, and it is the second time:** a within-session floor is not a
control. `project_spin_grip_recovery_2026_09_03` died the same way — an effect
that cleared its floor and then failed a placebo, because the real variable was
time. **Between-session drift on this car at this circuit is large and positive
while he is still learning the track (-5.9 s/lap in session 128 alone).** Any
cross-session comparison here needs a no-change control before it means anything.

## Rev E — ONE change: `df_f` 420 -> 440 (70% -> 90% of range)

- **Basis:** [DRIVER REPORT] the same lever at the same step size just delivered
  "much better" · [MEASURED] no drag cost, so the step is free on the straight.
- **Predicts:** more front bite again, mostly at the fast corners.
- **Falsified if:** the rear goes loose on fast-corner exit -> **430 is the
  answer**, not a wrong direction.
- **Instrument:** his report. **The corner index (62% floor) and peak lat_g
  (no valid control) may NOT be quoted as verdicts.**
- **Cost:** 3 clean laps.

**⚠️ This is the last big step on this lever** — ten units remain above 440. The
next moves, if needed, are `df_r` 600 -> 570 or `arb_f` 5 -> 4, **and which one
depends on a question only he can answer:**

> **Where is the residual understeer now — still the fast corners, or has it
> moved to the slower ones?** Front wing does almost nothing below ~120 km/h. If
> what is left is in the slow corners, more wing cannot reach it and the ARB is
> the tool. `unmeasurable_because` the corner index floor is 62% of its mean.

## ⚠️ ENGINEERING PRIORITY — say this plainly to him

Balance is good and improving on his own account. **The tyre wear number is still
unknown and has failed to sample twice**, and it is the only open item that
changes the RACE: one stop is two stints of **14.5 laps** against an estimate of
**14.1-14.4** that is pre-1.71 **and** from Monza.

- **Three runs left:** `df_f` 440 -> gearbox + new shift table -> 12-lap wear
  stint with the OBS windowed projector open.
- **One run left:** **go straight to the wear stint on the current 420 package.**
  A known tyre number is worth more to the race than the last increment of front
  grip.

---

# Session 132 — Rev E (`df_f` 440) ran. 5 Sep 2026, 7 laps. AERO WORK CLOSED.

## ✅ Rev E CONFIRMED — on the driver's report, which is the evidence

> **[DRIVER REPORT]:** *"that corner feels much better and car feels much more
> pointed all round track."*

**Three consistent reports across two steps** (420 "much better", 440 "much more
pointed all round"), plus **[MEASURED] zero drag cost**. That is what carries the
decision. **`df_f` 440 is kept and the aero axis is CLOSED** — ten units remain to
450 and they are not worth a run.

**New best lap: 102.345** (lap 7, no off-track), against 102.865 (s130) and
102.917 (s128).

## His timing claim — checked, and half of it is stronger than he put it

Clean laps only (no spin/crawl, off-track <= 1.6 s), app sectors
`thirds:1704/3409`:

| session | setup | n | S1 best | S2 best | S3 best | lap best |
|---|---|---|---|---|---|---|
| 128 | df_f 400 bb 0 | 11 | 35.353 | 34.277 | 32.909 | 102.917 |
| 129 | df_f 400 bb +1 | 4 | 35.178 | 34.535 | 33.296 | 104.120 |
| 130 | df_f 400 bb +3 | 2 | 35.484 | 34.302 | **32.898** | 102.865 |
| 131 | df_f 420 bb +3 | 3 | 35.243 | 34.384 | 33.019 | 103.170 |
| **132** | **df_f 440 bb +3** | **2** | **35.026** | **34.179** | 32.985 | **102.345** |

**Best S1 and best S2 on file — his claim is factually correct.** And stronger
than he stated: they came from a **2-clean-lap** session beating an **11-lap**
one, and s132's S1 **median** (35.156) is quicker than s128's best S1 **lap**
(35.353). The distribution moved, not just the tail.

## ⛔ But "proves the aero helped all round track" does NOT survive the control

Median sector movement with **aero unchanged** (128/129/130 are all df_f 400):

```
  s128 -> s129:  S1 -0.489   S2 -0.054   S3 +0.980
  s129 -> s130:  S1 +0.258   S2 -0.416   S3 -1.064
```

Median sector movement across **the whole aero change**:

```
  s130 -> s132:  S1 -0.384   S2 +0.159   S3 -0.167
```

**A no-change step moved S1 MORE (-0.489) than the entire aero change did
(-0.384), and S2's median got WORSE (+0.159) across the aero steps.** The timing
is *consistent with* the aero helping and cannot separate it from learning. Within
-session sd is 0.03-0.90 s on n=2-11.

**Same failure mode as the lateral-g retraction earlier the same day**
(`feedback_within_session_floor_is_not_a_control`). Flagged here specifically
because **the result agreed with the engineer** — that is when the control matters
most. **The conclusion is unchanged: keep 440.** Only the evidence class changes,
from [MEASURED] to [DRIVER REPORT].

## ⚠️ OPEN QUESTION — S3 is the fast sector and it moved least

Sector boundaries 1,704 m and 3,409 m put **all three of the lap's fastest corners
in S3**: 3,467-3,594 m (R, 219 km/h), **3,641-3,788 m (L, 176 km/h — the corner he
complained about)**, and 4,499-4,680 m (R, 220 km/h).

**Front downforce scales with v-squared, so S3 should have gained most. It gained
least** (-0.167 median across the aero change; the only sector not to set a best).

Not explained, and **not explained away** — n=2 clean laps in s132. Recorded as an
open question. If it persists once there are more clean laps on this package, the
reading would be that the front-wing gain is NOT where the physics says it should
be, and that is worth knowing.

## Priority — the aero is done, the race is not

**Both remaining items outrank another balance run:**

1. **Fit the gearbox** — `top` 240, final 3.050, ratios 3.041 / 2.329 / 1.900 /
   1.621 / 1.446 / 1.348.
2. **12-lap wear stint on it, OBS windowed projector open.** Failed to sample on
   **three** sessions now. It decides one stop vs two: one stop is two stints of
   **14.5 laps** against an estimate of **14.1-14.4** that is pre-1.71 **and**
   from Monza.

**Run them together** — the first two or three laps of the stint double as the
gearbox shakedown, and the wear number does not care about attribution. **Issue
the new shift table the moment he confirms the box is in:** 8,500 in gears 1-4,
**8,000 in 5th**, 7,400 fuel-saving in 1-5, 6th silent.

---

# 9 Sep 2026 — the week's rake and suspension work, applied to this car. **NO CHANGE ISSUED.**

`ludo refine`. No new laps. Everything below is re-derived from sessions
128–132 (5 Sep, 40 laps, 35 non-out, all RH, GT7 v1.71) and written to the
measurement store — ids 79–87, verdicts 10–14. **Rank zero was not re-opened:**
the 5 Sep SCREEN check stands and nothing has been asked of the car since.

## 1. The Daytona rake finding does NOT fire here — and that is the answer to the question asked

`reference_rake_percent_of_range` says read both ends as **percent of their own
range**, because "12 mm" at Daytona was really **12 % front against 33 % rear**.

| | slider | range | % of range |
|---|---|---|---|
| `rh_f` | 60 mm | [55, 80] | **20.0 %** |
| `rh_r` | 68 mm | [60, 90] | **26.7 %** |

**6.7 pp apart, against Daytona's 21 pp.** The two ends sit at nearly the same
place in their own travel. `+8 mm` of rake is real but **+5 mm of it is the
floor difference between the two ranges** — only +3 mm was ever a choice.
⇒ **No rake correction is indicated. [MEASURED]**

## 2. The Bathurst floor check — nothing is spent

Every suspension slider, in percent of its own range: `rh_f` 20.0 · `rh_r` 26.7 ·
`nf_f` 20.0 · `nf_r` 30.0 · `dc_f` **15.0** · `dc_r` 25.0 · `de_f` 26.7 ·
`de_r` 26.7. **All eight in the bottom third, none on a floor.** `dc_f` is the
closest at three clicks — worth knowing, not yet a constraint. Unlike the
Huracán at Bathurst, this circuit's headline levers are all still available.

## 3. Where the platform actually is — mapped, not asserted

Body height, 35 clean laps: **median 52.1 mm**, and two places where it drops.

| Where | Distance | Speed | Lowest (median across laps) | What the car is doing |
|---|---|---|---|---|
| **The climb off the line** | 100–260 m | 260 km/h | **18.8 mm** | dead straight, \|lat g\| < 0.5, all four tarmac — **surface bounce, not load** |
| **The long right onto the straight** | 4,490–4,700 m | 220 km/h | **24.6 mm** | full throttle, sustained 1.2–1.9 lat g, kerb frames at 4,570–4,586 |

⚠️ **This corrects the Rev A prediction check in one respect.** That reading called
both zones *"straight-line aero compression … not a kerb strike, not cornering
bottoming"*. The 100–260 m end is exactly that. **The 4,490–4,700 m end is not** —
it is a loaded corner with kerb contact, and the lowest single reading on file
(6.7 mm) is there. The *conclusion* is unchanged — the driver reported no
harshness and the car is not scraping — but the second zone was misdescribed.

## 4. [MEASURED] The nose sinks ~3 mm through a run on this car — and the cause is CONFOUNDED

Per-lap medians on the clean straight, front suspension channel against fuel:

- **s128 alone (11 laps, one tyre set, 74 L → 9 L): +0.0337 mm/L, se 0.0061** —
  5.5× its own error. s129 +0.0334, s130 +0.0467. Consistent across three runs.
- Rear: **+0.0165 mm/L**. ⇒ **the front moves 1.7× the rear**, so the rake
  *flattens* as the run goes on and comes back on a fresh full tank.

⛔ **Fuel and tyre wear are perfectly collinear within a run and I cannot separate
them.** `tyre_radius_m` is a constant 0.355 in the feed, so it is no help, and the
between-session estimate (+0.0115 ± 0.0443, n=6) cannot distinguish +0.03 from
zero. **What survives either way: the nose sits ~3 mm lower at the end of a stint
than at the start.**

⚠️ **Two doctrine lines fail against this.** `04-race-vs-qualifying.md` §2.3 says a
full tank squats the **rear** and flattens the platform — on this car it is the
**front** that moves, and 1.7× as much. And the Huracán read **+0.0060 mm/L**,
so importing that "not present" result here would have been wrong by 5×.
**Measure it per car. → RECONCILIATION.**

## 5. [MEASURED, weak] The aero programme moved the front platform and the springs never followed

Fuel slope removed (fitted on s128 alone), session-median residual on the straight:

```
  s128  df_f 400   +0.20 mm       null control: the three df_f 400
  s129  df_f 400   -0.46 mm       sessions spread 0.66 mm
  s130  df_f 400   -0.04 mm
  s131  df_f 420   +0.01 mm   <- twenty units of wing moved NOTHING
  s132  df_f 440   +1.10 mm   <- 1.7x the null spread, n=6 laps
```

In **the long right onto the straight**: **+1.42 mm, 2.2× that zone's own
lap-to-lap floor (0.633 mm)**, rear unmoved (0.0×). So Rev C→E's 40 units of
front wing (50 % → 90 % of range) put ~1.4 mm into the front spring rather than
the tyre, in the one corner that loads it longest.

⚠️ **Held to "suggestive", not settled**, for three reasons: 6 laps at 440; 1.10
against a 0.66 control spread; and 420 → 440 doing all of it while 400 → 420 did
none, which is either a non-linearity or noise. **It does NOT explain the S3 open
question** — the other two fast corners in S3 moved 1.0× and 0.2× of their own
floors, i.e. not at all. **One corner, not the sector.**

## 6. Why no change is issued

- **There is no symptom.** Rev E closed on *"much more balanced"*. A
  telemetry-only flag may not buy a setup change.
- **A front spring is a platform move**, and one-change-at-a-time will misjudge
  it. `reference_setup_platform_before_sliders`.
- **The wear stint outranks it.** It has failed to sample three times, and it
  decides one stop against two. Nothing displaces it.

## 7. What the next run buys for free

The 12-lap wear stint from a full tank **is** the fuel/wear platform sweep, at
double the lever arm of anything on file. No extra laps. Read it for §4 as well
as for `w`.

## 8. Pre-loaded, not issued

**If** he reports the nose going light late in a stint, or understeer arriving in
the fast corners as the fuel burns off, the answer is **`nf_f` 3.40 → 3.60 Hz
(20 % → 30 % of range)** — the front spring, not ride height (standing refusal)
and not more wing (440 of 450 is spent). **[ASSUMED]** until he reports.

## 9. The store had nothing on this car — now it has nine rows and five verdicts

`untested_axes` returned **everything** for this car+circuit before today.
`rh_f`, `rh_r`, `nf_f`, `dc_f` are now written as **`untested`** so the absence
is visible; `df_f` up is written **`confirmed`** on the driver's report with the
platform side-effect attached.

## Open predictions — check these at the next debrief

| Prediction | Falsified if |
|---|---|
| The nose sinks ~3 mm from full tank to empty over the 12-lap stint | the front channel is flat across the stint, or moves < 1 mm |
| That sink is fuel, not tyre wear, so it resets on the out-lap after the stop | the front stays low after fresh tyres and a full tank |
| The car feels different late in a stint at the front, not the rear | he reports the change at the rear, or reports none |

---

# 9 Sep 2026, later — the driver closed §4's confound, and the wear claim on this file is wrong

## 10. ✅ §4 RESOLVED. It is fuel, and the tank is in the nose

> **[DRIVER REPORT], 9 Sep 2026, unprompted:** *"the reason the front gets higher
> on low fuel is the tank for an MR is in the front not the back like an FR"*

§4 above closed with *"the cause is confounded and I cannot separate fuel from
tyre wear."* **That refusal was wrong and it was checkable in two minutes.**

1. **GT7 never shrinks the tyre.** `tyre_radius_m` is a per-car constant on every
   frame — Huracán **0.3525** across the whole 20-lap Daytona race (2.7 % → 39 %
   worn, a pit stop, then 0 → 28 %), RSR **0.355** across 33 %. **Wear has no
   channel through which it could move ride height.**
2. **The sign is wrong for wear anyway.** Wear would put the car *lower* late in
   a run; the measurement has it *rising*. And on a 46 : 54 car wear would take
   the **rear** first — the opposite of the measured 1.7 : 1 front bias.

⇒ **The finding stands and strengthens: front +0.0337 mm/L, rear +0.0165 mm/L,
and the cause is FUEL.** The 911 carries its tank in the nose ahead of the
driver, so burning it lifts the front. It is also why a mid-engined car reads
46 : 54. `04-race-vs-qualifying.md` §2.3 is an FR statement and is end-for-end
wrong on any 911. → **RECONCILIATION AU1a**, `reference_fuel_tank_position_moves_ride_height`.

**The lesson, and it is the expensive half:** a confound needs a **mechanism with
the right sign** and a **channel that can carry it**. Neither was checked before
`unresolvable` was written. ⚠️ **`tyre_radius_m` is a chassis constant, not a
wear proxy** — nothing may read wear off it.

## 11. ⛔ "The wear gauge failed to sample three times" is WRONG, and it has been repeated at Rev C, D and E

**Session 128 is correctly described — 15 laps, all null.** Sessions **130, 131
and 132 all sampled**, `wear_source = 'hud-video'`, every lap after the out-lap.
**13 laps of gauge data have been sitting on file since 5 September.**

Fitted per wheel, Racing Hard, **at the race's own 8× multiplier** (no conversion,
so no `[ASSUMED]` linearity step):

```
  FL 0.0394   FR 0.0458   RL 0.0488   RR 0.0528   per lap, mean of three runs
  worst wheel REAR-RIGHT  ->  L = 0.85 / 0.0528 = 16.1 laps
```

against the standing figure of **0.05897–0.06034 ⇒ 14.1–14.4 laps**, which is
pre-1.71 **and** from Monza and was flagged VOID TWICE when it was written.

⚠️ **This does NOT retire the stint, for two stated reasons:**

- **The gauge ticks in 36ths.** Over a 5-lap span that is **±0.0056/lap**, so the
  honest band is **13.9 to 17.0 laps** — and it still straddles the **14.5** a
  one-stop needs.
- **All three runs sample only 8–39 % of tyre life.** CLAUDE.md §5.1: degradation
  is **piecewise**. An early-life rate is a **lower bound** on the late one and
  may never be projected through the knee.

⇒ **What was missing was a stint 12 laps long, not a working gauge.** Correct the
claim; keep the run. It is still the highest-value thing on the car.

## 12. The worst wheel moved axle-side from Monza, and that is measured

Monza's worst was the **rear-LEFT**. Here it is the **rear-RIGHT**, and the
reason is the circuit: over 101,641 frames above 0.6 lat g across sessions
128–132, **59.7 % of the loaded cornering is LEFT-hand turns**, and those lefts
carry **1.5× the mean lateral load** of the rights (0.739 against 0.483). A
left-hander loads the right-hand wheels. **Do not carry Monza's axle-side across.**

Rows: `measurement` 88–92. → **RECONCILIATION AU2a**.

## Open predictions — amended

| Prediction | Falsified if |
|---|---|
| The nose rises ~3 mm as the tank empties over the 12-lap stint, and resets on the out-lap after a refuel | the front channel is flat across the stint, or does not reset after the stop |
| Rear-right stays the worst wheel over a full-length stint | any other wheel leads at 12 laps |
| The full-stint rate is **at or above** 0.0528/lap — the short runs are a lower bound | the 12-lap rate comes in below 0.0528, which would mean the early runs over-read |

---

# Sessions 153/154/155 - 9 Sep 2026, 35 laps, ALL THREE COMPOUNDS. Rev F issued.

**Rank zero CLOSED on the gearbox.** The new box is IN: ratios `3.041 / 2.329 /
1.900 / 1.621 / 1.446 / 1.348` **FEED-verified byte-identical on all 35 laps**.
Everything else rests on the 5 Sep SCREEN check plus his word on `bb +3` /
`df_f 440`.

> **[DRIVER REPORT], 10 Sep 2026 - and it changes the standing rule:**
> *"me not complaining about the car doesn't mean it's got the best setup I
> don't know what I don't know and if you see something in the telemetry that
> could be improved or can transfer learning from another car we should
> absolutely try it."*
>
> The 9 Sep entry declined to propose anything with *"there is no symptom"* as
> its first reason. **That reason is retired.** Silence from the driver is not a
> clean bill of health - he cannot report a deficit he has never felt the
> absence of. `feedback_no_complaint_is_not_a_good_setup`.

## 13. FUEL BINDS HERE. Section 3's headline is overturned.

Section 3 says *"Fuel does not bind here. The tyre does. That is the opposite of
Monza."* **It is wrong, and the error was the `[ASSUMED]` 4.4-5.4 L/lap.**

**Measured: 7.046 L/lap** at the race's 3x, over 67 counted laps. So a 100 L tank
is **14.2 laps**. Over 28 laps:

- **RH's stint ceiling is 13 laps and it is FUEL** - the tyre would go 17.1.
- 2 x 13 = 26 < 28, so **there is no one-stop at full send, on any compound.**

## 14. The compound sweep - measured, worst wheel REAR-RIGHT throughout

| | wear/lap | tyre laps | fuel laps | stint cap | pace vs RH |
|---|---|---|---|---|---|
| **RH** | 0.0498 | 17.1 | 14.2 | **13, fuel** | - |
| **RM** | 0.0668 | 12.7 | 14.2 | **12, tyre** | **-1.71 s** |
| **RS** | 0.1500 | 5.7 | 14.2 | **5, tyre** | -2.15 s |

**Pace is fuel-matched, not session medians.** All three ran from a full tank on
one evening, so pairing on lap number pairs on fuel load: RM-RH median **-2.11 s**
over 5 clean pairs; best-lap RH 102.399 against RM 100.692 gives **-1.71**, and
the conservative end is used. WARNING: **not a same-session back-to-back** - the
strategy engine refuses a delta for exactly this reason, and track evolution
across the evening favours the later (softer) runs. **The run that settles it:
three short runs, one per compound, in ONE session, same fuel.**

WARNING: **the RM 12-lap cap is the 0.85 rule, and he beat it.** He ran 14, and
**lap 13 at 89% worn was a normal 101.578**. The slow lap 14 was **the tank
going dry** (`fuel_end` 0.0), not the cliff. The **RS did cliff**: 118.2 s at
89%, 141.4 s at 100%.

## 15. THE RACE PLAN - RM two-stop, full send

```
  RM12 / RM7 / RM9    2 stops, FULL SEND               <- fastest, 28 laps
  RH14 / RH14         1 stop,  300 rpm saving           +17.1 s
  RH13 / RS5 / RH10   2 stops, full send                +30.3 s
  RH13 / RH7 / RH8    2 stops, full send                +39.9 s
```

**Short-shifting makes the RM plan WORSE - +3.8 s at 300 rpm, +7.6 s at 600.**
The RM plan is **tyre**-limited at 12 laps, and fuel saved on a tyre-limited
stint buys nothing while the lap time is paid in full. It pays **only** on RH,
where it lifts the fuel ceiling from 13 to 14 and **deletes a stop** - the Monza
structure exactly (`reference_shortshift_daytona_vs_monza`). So **the fuel table
is for the RH fallback ONLY.**

**The measured saving here is Sardegna's own:** `+2.254 L/1000 rpm` (t 2.92, 34
laps, fixed effects). At 1.0 L/s that buys **2.254 s of standing time per 1000
rpm**. The lap-time **cost** could not be fitted here (CI +/-23 s) - the usable
figure is **Monza's controlled A/B on this same car, ~1.9 s/1000 rpm**.

WARNING: **THE REFUEL RATE HAS NEVER BEEN MEASURED.** ~115 L at the event page's
1.0 L/s is ~115 s of standing time - **more than six times the gap between the
top two plans.** One practice stop taking fuel, with the app recording, settles
it. **Highest-value measurement available and it costs one lap.**

## 16. "More pointed" - measured, and it is NOT a mid-corner grip problem

**First, an instrument correction.** Pooled across all throttle, front-minus-rear
slip reads **-0.011**, which looks like a rear-limited car. **It is an artefact
of mixing throttle bands** - the rear axle's slip is *drive* slip:

| throttle | F-R slip | reading |
|---|---|---|
| coast, <5% | **+0.0003** | **dead neutral** |
| 5-40% | -0.0047 | rear driving |
| 40-90% | -0.0328 | rear driving |

**Split by throttle before reading this channel.** True mid-corner balance is
neutral, against the Huracan's +0.011 at Daytona (understeer) and +0.001..+0.004
at Bathurst ("very pointed").

**The deficit is in the PHASE, not the balance.** Steering per unit of yaw:

```
  trail-braking (brake >60%)   69.9      <- the car rotates
  brake release (5-60%)        82.6
  neutral mid-corner          108.2      <- 55% MORE lock for the same rotation
```

Noise floor **9.89** (worst odd/even split within one unchanged session). **The
car turns in well and stops rotating the moment the brake is gone** - which is
precisely the phase he is asking about, and precisely the phase a trail-braker
lives in.

**And the front is the limiting axle**: front slip below 0.92 on **19.8%** of
trail-brake frames against the rear's **4.5%** (15.9% on 5 Sep). `bb` is already
at `+3` rearward; that lever is spent.

## 17. Rev F - ONE change: `arb_r` 3 -> 5

**The sheet in percent of its own range, front minus rear:**

```
  rh   -6.7 pp     nf  -10.0 pp     dc  -10.0 pp     de  0.0 pp     cam  0.0 pp
  arb  +22.2 pp   <<<  the ONLY mechanical axis biased to the FRONT
```

`arb_f` 5 = **44.4%**, `arb_r` 3 = **22.2%**. Carried from Monza, never touched
here, and it is roll stiffness at the front - which is understeer. **Nobody
complained for a month, and that is the point of section 13's driver note.**

- **[TRANSFER]** Huracan at Daytona: `arb_r` 4 -> 6 **confirmed** on sector time
  (S2 -0.449 s) plus *"the best it has"* - and it was **invisible to every
  rotation index on file**, recorded as instrument blindness.
  `project_daytona_setup_day_2026_09_08`.
- **Why not `arb_f` down:** the Spa lesson - softening a front bar on a soft,
  high car adds roll and tests as a failure alone. `arb_r` up is the measured
  direction.
- **Why not more wing:** `df_f` 440 is **90%** of [350, 450]. Spent.
- **Why two clicks:** matching `arb_f` at 44.4%, and one click has already proved
  unmeasurable on this car's `bb`. **Bracketing - if +5 overshoots, 4 is the
  answer and it is found in two runs instead of four.**
- **Predicts:** lock-per-yaw at neutral mid-corner falls from **108.2** by more
  than **9.89**; he reports the car finishing the corner without extra steering.
- **Falsified if:** the rear steps out on **brake release** - his known
  signature. **That means 4, not that the direction is wrong.**
- **Cost:** 3 clean laps.

## 18. Shift table RE-ISSUED - and the number I pre-issued was wrong

`tools/shift_points.py` on the new box: **every gear 1-5 reports LIMITER**,
including 5->6 (won at all 3 comparable bins up to 8,500 in session 153's 14
laps, and again in 154). **The pre-issued "8,000 in 5th" was `[ASSUMED]` off the
OLD box's ratio step and is measured wrong on this one.**

Now **8,500 in gears 1-5** (just under the observed cut, median 8,567 over 7,322
rev-limiter frames), **6th silent** - there is no 6->7 to cue. Fuel table **7,400
in 1-5**, extended to 5th because 5th is a working gear on this box.

**Box prediction HELD:** 6th is genuinely used - 11,223 full-throttle frames,
max **262.8 km/h** against a predicted 276.5 at the limiter, so the tow headroom
is there and 6th never meets the limiter.

## Open predictions

| Prediction | Falsified if |
|---|---|
| `arb_r` 5 drops mid-corner lock-per-yaw by more than 9.89 from 108.2 | it moves less than that, or rises |
| He reports the car finishing corners with less steering | he reports no change, or a loose rear on brake release (then `arb_r` 4) |
| The refuel rate measures at 1.0 L/s +/-0.1 | it does not - and then the whole stop-count table is re-run |
| A same-session three-compound run reproduces RM -1.71 s vs RH | RM comes in under -1.0 s, which closes the RM/RH gap to ~3 s and puts the RH one-stop back in play |

## 19. THE PLAN IN 15 IS WRONG. The driver was right, on two counts. 10 Sep 2026

> **[DRIVER REPORT]:** *"the one stop on hards won me monza by 13 seconds over
> the 2 stop on mediums, we save 2 litres a lap and it only cost 1 second of lap
> time so was a net gain of 1 second per lap. Applying the same fuel saving
> principle as we did at monza also increases tyre life as we aren't running as
> hard so would open a one stop on mediums."*

**Both halves check out, and section 15's recommendation is retired.**

### 19a. His Monza numbers, verified from the archive

Sessions 50 and 51, the controlled A/B, same car, same tyre, 18 minutes apart:

```
  full send    7.432 L/lap   109.223 s      short-shift   5.635 L/lap   109.941 s
  ->  1.797 L/lap saved (-24.2%) for +0.718 s/lap  =  NET +1.08 s/lap at 1.0 L/s
```

**He under-sold it.** He remembered 2 L for 1 s; it was 1.80 L for 0.72 s.

### 19b. My two errors in section 15

1. **I used the wrong fuel number.** Section 15 used Sardegna's own fixed-effects
   gradient, `+2.254 L/1000 rpm`, fitted on a natural upshift spread of about
   **60 rpm within a session**. A deliberate 600 rpm drop is ten times beyond
   that variation. **Monza proved this method understates the real saving**: its
   own gradient predicted ~1.06 L/lap for 600 rpm and the controlled A/B measured
   **1.80**. The A/B percentage is the transferable figure - same car, same
   driver, controlled - and it is **-24.2%**, not the -9.6% I used.
2. **I ignored the tyre-life half entirely.** CLAUDE.md section 5.3 states it:
   short-shifting *"saves ~20% fuel for ~0.5 s/lap AND reduces rear tyre wear."*
   **The limiting wheel here is the REAR-RIGHT on all three compounds** - exactly
   the wheel it protects. I modelled saving as fuel-only, concluded it "buys
   nothing on a tyre-limited stint", and that conclusion is circular: saving
   relieves the very constraint I said it could not touch.

### 19c. THE THING THAT DECIDES IT - saving buys a whole extra LAP

This is a **timed** race. Standing time is laps.

```
                                    laps   standing time (transit + dead + fuel)
  full send, mediums, 2 stops        28     170.5 s   (40 + 15 + 115)
  save 600 rpm, mediums, 1 stop      29      90.4 s   (20 +  8 +  63)
  save 600 rpm, hards,   1 stop      29      90.6 s   (20 +  8 +  63)
  save 300 rpm, hards,   1 stop      28     111.8 s   (20 +  8 +  84)
```

**Saving cuts up to 80 seconds of standing still.** The lap-time cost over 29 laps
is about 21 s. Net ~59 s - more than half a lap - and it is enough to cross from
**28 laps to 29**. A lap up outranks every time comparison on the page.

⚠️ **300 rpm is NOT enough**: it lands at 28 laps, dead level with the full-send
medium two-stop. **The full Monza-sized drop is what buys the lap.**

### 19d. How many laps on the hards - the answer to his question

```
  full send   7.05 L/lap:  tyre 17.1 | fuel 14.2  ->  14.2 laps, FUEL-limited
  save 300    6.19 L/lap:  tyre 17.1 | fuel 16.1  ->  16.1 laps, FUEL-limited
  save 600    5.34 L/lap:  tyre 17.1 | fuel 18.7  ->  17.1 laps, TYRE-limited
```

**Seventeen laps on the hards with the full save, and the tank is no longer what
stops you - the tyre is.** 17 + 12 covers 29 laps in one stop.

### 19e. Where it lands, and the one thing still unmeasured

All 600-rpm plans complete 29 laps. Ranked:

```
  mediums 1 stop  RM15 / RM14   needs tyre life +20%     3053.8 s   <- best
  mediums 2 stop  RM13 / RM7 / RM9  needs +10%           3084.6 s   +31 s
  hards   1 stop  RH17 / RH12   needs NOTHING            3091.5 s   +38 s
  mediums 2 stop  RM12 / RM8 / RM9  needs nothing        3090.1 s   +36 s
```

⇒ **Two claims, and they carry different weight:**

- **SAVE FUEL. That is settled** and does not depend on the tyre question at all
  - every saving plan is a lap up on every full-send plan.
- **Which compound is NOT settled**, because it turns on a tyre-life benefit that
  is **`[UNMEASURED]` here**. With +20% the medium one-stop wins by 38 s; with
  none, the hard one-stop and the medium two-stop are within 1.4 s - a coin flip.

⛔ **The tyre-life effect CANNOT be fitted from what is on file.** Every lap in
sessions 153/154/155 ran within **62 rpm** of every other, and the gauge moves in
36ths (0.0278) - half a lap's wear per tick. It needs the same controlled A/B
that settled the fuel question at Monza.

### 19f. The run that settles it - and it re-orders the runs

**A 12-lap MEDIUM stint, short-shifting throughout, from a full tank.** It is
directly comparable to session 154 - same compound, same circuit, same setup,
one variable - and it returns three things at once: the fuel saving on this
circuit, the tyre-life effect, and whether the medium reaches 14 laps.

⚠️ **THIS MUST RUN BEFORE `arb_r`, and section 17's ordering is corrected.**
A stiffer rear bar moves rear-tyre load, which is the very thing the wear stint
measures. Changing the bar first destroys the only clean comparison available.
**`arb_r` stays at 3 for this run.** If the bar has already been moved to 5, put
it back for the stint or the comparison is gone.

**Order: wear stint on the current car -> `arb_r` 3 -> 5, three clean laps.**

### 19g. Open predictions - amended

| Prediction | Falsified if |
|---|---|
| Short-shifting 600 rpm saves 20-25% fuel here, as at Monza | the stint burns more than 6.0 L/lap |
| It costs under 1.0 s/lap | the clean-lap median is more than 1.0 s off session 154's 101.578 |
| It measurably lowers rear-right wear | the 12-lap gauge trace matches session 154's within one tick |
| Saving puts him on 29 laps rather than 28 | race pace lands more than ~20 s off plan, which drops it back to 28 and the whole board becomes a tie |

## 20. The beep set to fuel-save for tonight - and WHY it needed a hack. 10 Sep 2026

> **[DRIVER]:** *"set shift beep to fuel save and I will test RH and RM tonight
> with fuel saving"*

### 20a. Short-shift CANNOT be engaged in a practice session. There is no path.

`Controller.set_short_shift()` (controller.py:426) is what flips the beep onto the
fuel table. **Its only production caller is controller.py:5326, inside the live
race-engineer call handler.** There is no UI control - `grep -rn "short_shift"
pitcrew/ui/` returns one unrelated comment.

⇒ **In practice there are no engineer calls, so the issued fuel table can never
reach the wheel.** He would be asked to short-shift with no cue: the exact
failure the comment at controller.py:5310 was written about - *"'Short-shift
450.' reached his ears and nothing reached the beep."*

**This is the "both ends built, caller skipped" pattern again**, and it is now a
first-class practice activity rather than a race-only one, because the whole
medium-vs-hard race decision turns on a tyre measurement taken in practice.
Filed as app work.

### 20b. The workaround, and it MUST be undone

`shift_points` id 1 now reads **`performance` = 7,400 in gears 1-5, `fuel_saving`
empty.** That is the fuel-saving number promoted into the performance slot so
that it actually beeps.

⛔ **THIS IS NOT THE PERFORMANCE TABLE.** The measured one for this box is
**8,500 in gears 1-5** (every gear reports LIMITER; observed cut median 8,567
over 7,322 rev-limiter frames). It is recorded in the row's own note and here.
**Restore both columns after tonight.**

### 20c. What tonight measures, and the one number that is a stretch

**Two stints, RH and RM, short-shifting throughout, from a full tank** - directly
against sessions 153 (RH) and 154 (RM), same car, same setup, same circuit, one
variable. Three answers at once:

1. the fuel saving on **this** circuit, at last (the 60 rpm within-session spread
   could never give it);
2. the **lap-time cost** here, which Sardegna's own fit could not resolve at all
   (CI +/-23 s);
3. **whether short-shifting extends rear-right tyre life** - the unmeasured term
   that decides medium-one-stop against hard-one-stop.

⚠️ **7,400 is 1,100 rpm below the performance point - nearly TWICE the ~600 rpm
the Monza A/B measured.** So Monza's `-24.2% fuel / +0.718 s per lap` does **not**
predict tonight, and the cost at 1,100 rpm is `[UNMEASURED]`. **Deliberate:** the
deepest drop gives the clearest tyre signal, and rpm can be handed back later
whereas data not collected cannot. If the lap-time cost comes in above about
**1.5 s/lap**, the answer is to back the table off toward 8,000 rather than to
abandon saving - the fuel prize is a whole lap and it is not close.

### 20d. Order matters and `arb_r` still waits

`arb_r` stays at **3** tonight. A stiffer rear bar moves rear-tyre load, which is
exactly what these stints measure. **Wear stints first, then the bar.**

### 20e. Open predictions

| Prediction | Falsified if |
|---|---|
| RH at 7,400 burns 5.3-5.6 L/lap | it burns over 6.0, i.e. under 15% saved |
| RM at 7,400 burns about the same as RH did | the two compounds differ by more than 0.3 L/lap |
| Lap-time cost lands between 0.7 and 1.5 s/lap | it exceeds 1.5 s/lap, and the table backs off to 8,000 |
| Rear-right wear per lap drops below the full-send RH 0.0498 / RM 0.0668 | the gauge trace matches the full-send stints within one tick, and the medium one-stop dies |
| RH reaches 17 laps on one tank | it does not, and the hard one-stop needs a deeper drop still |

---

# Sessions 156 + 157 - 10 Sep 2026. The fuel-saving test. Rev G: `arb_r` 3 -> 5.

**33 laps.** s156 = RH, 19 laps, short-shifting throughout at ~7,343 rpm.
s157 = RM, 14 laps, short-shifting to lap 9 then **full send from lap 10** -
the driver stopped saving when a rival entered the practice lobby.

> **[DRIVER REPORT]:** *"I had to stop fuel saving in second stint on mediums
> half way through as a rival entered practice lobby and I didn't want him to
> see my strat."*

⭐ **That accident produced the best measurement of the week.** Stopping halfway
turned session 157 into a **within-stint A/B on ONE set of tyres** - same set,
same fuel trajectory, same session, one variable at lap 10. Nothing I could have
designed would have controlled it better.

## 21. What short-shifting actually does here - MEASURED

```
                       upshift    fuel L/lap    best lap    wear RR /lap
  RH  s153 full send      8449        7.027      102.627    0.0498 +/-0.0006
  RH  s156 SAVING         7343        5.165      103.708    0.0491 +/-0.0005
  RM  s154 full send      8470        7.167      100.692    0.0668 +/-0.0006
  RM  s157 SAVING  L1-9   7384        5.247      102.396    0.0645 +/-0.0013
  RM  s157 full send L10+ 8389        6.670      101.397    0.0706 +/-0.0019
```

**Fuel: -26.5% on the hard, -21.3% on the medium.** Both bigger than Monza's
-24.2%/-21% band predicted for a drop this size, and the hard ran **19 laps on
one tank**, finishing on 1.7 L.

**Lap-time cost: 1.00 s/lap**, measured within the stint (102.396 against
101.397 on the same tyres). The RH between-session figure agrees: **+1.081**.

⛔ **THIS IS THE NUMBER THAT KILLED THE 29TH LAP.** Section 19c predicted 29 laps
using **Monza's +0.718 s at ~600 rpm**. At ~1,000 rpm it costs **1.0-1.1 s/lap**,
and that is enough to put every plan back on **28**. The saving is still worth
having - it is worth 60-95 seconds of standing time - but **it does not buy a
lap, and I said it would.** Section 19c's headline is retracted.

## 22. The tyre question, ANSWERED - and the answer differs by compound

| | wear saving vs full send | verdict |
|---|---|---|
| **Racing Medium** | 0.0645 against 0.0706 = **-8.7%** | **REAL.** 0.0061 against a combined error of 0.0023 = **2.7x** |
| **Racing Hard** | 0.0491 against 0.0498 = **-1.4%** | **NOT MEASURABLE.** 0.0007 against a combined error of 0.0008 |

**The control that makes the medium result stand:** at full send throughout
(s154) the wear rate is **flat with tyre age** - 0.0671 over laps 1-9 against
0.0683 over laps 9-14, **+1.7%**. So tonight's **+9.5% step at the switch** is
the shift point, not the tyre getting older.

⚠️ **The hard result is weaker evidence than the medium one** and must not be
quoted as equally strong: it is a **between-session** comparison, and the
between-session offset has already bitten this project once
(`feedback_within_session_floor_is_not_a_control`). The medium result is
within one stint and has no such hole.

⚠️ **I cannot explain why the medium responds and the hard does not.** Recorded
as a fact, not dressed in a mechanism. `feedback_never_assume_investigate_or_ask`.

## 23. Where the race stands - and every plan is now 28 laps

**Once he is saving, FUEL STOPS BINDING AND THE TYRE BINDS** - RH saving has
19.4 laps of fuel against 17.3 of tyre; RM saving 19.1 against 13.2. That
inverts section 13 for the second time and it is the structural fact to hold on
to.

```
  RM saving, 2 stops   13 / 7 / 8    3012.2 s   113 s standing   <- fastest
  RM saving  800 rpm   13 / 7 / 8    3013.2 s   126 s
  RM full send, 2 st   12 / 7 / 9    3023.5 s   175 s
  RH saving, 1 STOP    17 / 11       3024.4 s    80 s            <- +12.2 s
  RH full send, 2 st   13 / 7 / 8    3066.6 s   170 s
```

⚠️ **The top two are 12 seconds apart and that is inside what my compound pace
delta can carry.** It rests on `RM -1.935 s/lap vs RH`, taken from best laps
across sessions rather than a same-session back-to-back. **12 seconds is not a
recommendation, it is a tie**, and the hard one-stop wins on everything that is
not on the stopwatch: **half the standing time, one pit exit instead of two, one
chance of a bad stop instead of two, and 17-lap stints instead of 13.**

⇒ **No race call is made yet.** The compound decision waits on a same-session
three-compound run. It is not needed before the `arb_r` work.

## 24. Rev G - `arb_r` 3 -> 5, and the baseline MOVED

The proposal is unchanged from section 17. **What changed is the number it will
be judged against.**

```
  9 Sep,  s153/154/155 full send   108.22
  10 Sep, s157 L10-14 full send     99.55   <- THE BASELINE FOR THIS TEST
  10 Sep, s157 L1-9  saving         97.99
  10 Sep, s156 saving               99.95
```

⛔ **The whole baseline drifted about 9 points overnight** - just inside the 9.89
floor, so it is not a finding, but **judging `arb_r` against 108.22 would credit
the bar with roughly a floor's worth of movement it did not earn.** Use **99.55**.

✅ **Short-shifting does NOT move this instrument** - within one stint, saving
97.99 against full send 99.55 = **1.56**, well inside the floor. So the
instrument is clean; only its zero moved.

⇒ **Run the `arb_r` test on RACING MEDIUM at FULL SEND**, to match s157 laps
10-14 exactly. Three clean laps.

- **Predicts:** lock-per-yaw falls from **99.55** by more than **9.89**, and he
  reports the car finishing the corner without extra steering.
- **Falsified if:** the rear steps out on **brake release** - his signature.
  **That means `arb_r` 4, not that the direction is wrong.**
- ⚠️ **The instrument may be blind to this axis.** At Daytona `arb_r` 4->6 was
  invisible to every rotation index on file and showed up only as sector time
  and his own report. **If lock-per-yaw does not move, that is NOT a refutation**
  - it is recorded as instrument blindness, and his report decides.

## 25. Open predictions

| Prediction | Falsified if |
|---|---|
| `arb_r` 5 drops lock-per-yaw by more than 9.89 from 99.55 | it moves less - and then his report decides, not the index |
| He reports the car finishing corners with less steering | he reports no change, or a loose rear on brake release (then 4) |
| The medium's 8.7% wear saving holds over a second stint | a repeat within-stint A/B lands inside 3% |
| A same-session three-compound run reproduces RM about 1.9 s/lap faster than RH | it comes in under 1.2 s, and the hard one-stop wins outright |

## 26. Why the beep died in the medium stint - DIAGNOSED, and it is a product defect

> **[DRIVER REPORT]:** *"the shift beep died in the medium stint why?"*

**It did die, he is right, and it went silent in FOUR of six gears for the last
five laps.** Nothing in the log said so - `pitcrew.log` carries no beep line
after the table loaded at 19:47:32, and no error. He found it by noticing the
silence, which is the only instrument there was.

### 26a. The mechanism

`shift_beep.py`, `should_beep()` - the hysteresis flag `shift_above` is cleared
only here, with `REARM_FRACTION = 0.95`:

```python
  re_armed = shift_above
  if rpm < threshold * REARM_FRACTION:
      re_armed = False
```

**The beep re-arms only if the revs fall below 95% of the threshold.** On a
close-ratio box an upshift does not drop them that far, so the beep survives
only while:

```
      shift_rpm / ratio_step  <  threshold x 0.95
```

**This box's upper steps are 1.1721, 1.1210 and 1.0727.** At a 7,400 threshold
that tolerates shifts up to **8,240 / 7,881 / 7,541 rpm** in 3->4, 4->5, 5->6.
He was shifting at **~8,390**.

### 26b. Measured off session 157 - the landing rpm is the minimum over the 0.5 s after each change

```
  SAVING, laps 2-9   (shifting ~7,380)          FULL SEND, laps 10-14 (shifting ~8,390)
    1->2  floor 6052   re-armed 24/24            1->2  floor 6608   re-armed 17/17
    2->3  floor 6278   re-armed 32/32            2->3  floor 6998   re-armed 17/22
    3->4  floor 6477   re-armed 41/41            3->4  floor 7238   re-armed  0/25   SILENT
    4->5  floor 6667   re-armed 45/45            4->5  floor 7498   re-armed  0/18   SILENT
    5->6  floor 6811   re-armed 22/23            5->6  floor 7652   re-armed  0/2    SILENT
```

**164 of 165 shifts re-armed while he followed the beep. Zero of 45 re-armed in
3rd, 4th and 5th once he stopped.** The moment he went back to full send the
hysteresis latched and never released.

### 26c. This is CLAUDE.md rule 10, and it is not my hack's fault alone

The 7,400 threshold was the one-night promotion (section 20b), and it is what
opened the gap between the beep and where he actually shifts. **But the latch is
latent in the design and would fire identically on the intended path** - the
fuel table engaged normally is the same 7,400 threshold, and the instant he
stops following it the upper gears go quiet. **That is exactly when he most
needs to hear it.**

Rule 10: *"a rule that refuses a reading must be able to refuse its own
baseline... it is a latch unless something can retire the reference"* - and its
second half, *"log the accepts, not only the refusals"*. `ShiftBeep.beeps`
counts and **nothing ever reports it**, which is why a whole stint went by.

⛔ **And silence is ambiguous by design here**: a gear with no issued threshold
is deliberately silent. So at the wheel a broken beep and a designed silence are
the same sound. Filed as app work.

### 26d. Tonight is SAFE, and here is the arithmetic

The beep is back on **8,500**, which re-arms at 8,075. At that threshold the
tolerated shift points are **10,544 / 9,898 / 9,465 / 9,052 / 8,662 rpm** - all
above the ~8,450 he actually shifts at. **Every gear re-arms.** This is also why
nothing was wrong on 9 Sep: that table's threshold matched his shift point.

⚠️ **The general rule to check before issuing any future fuel table on a
close-ratio box:** `threshold x 0.95 x ratio_step` must exceed the highest rpm
the driver might shift at, **in every gear the table names** - not the rpm the
table asks for.

---

# Session 158 - 10 Sep 2026, 19 laps. `arb_r` CONFIRMED at 4, NOT 5. Rev H.

> **[DRIVER REPORT]:** *"ran on ARB rear 5 couldn't get my worst corner turned
> mid corner. went to ARB rear 4 and it's perfect. 5-5 was better for all but
> one corner, it points on turn in perfect but lacked mid corner turn on 5-5
> than 5-4."*

**Both settings ran in one session and the split had to be found, not assumed.**
Lap 11 carries `crawl_s` 11.43 s and fuel jumping **31.4 -> 93.1 L** - he came in,
refuelled and changed the bar. ⇒ **laps 2-10 = two clicks, laps 12-19 = one
click**, lap 11 excluded. Both blocks cover the same fuel range (93 -> ~40 L).
⚠️ `is_pit_lap` reads **0** on lap 11 despite the refuel - the pit detector missed
it again, and only the fuel jump gives the split away.

## 27. The bracket worked, and one click is the answer

| | two clicks (laps 2-10) | one click (laps 12-19) |
|---|---|---|
| catching the back end | **197.7 frames/lap** | **18.5 frames/lap** |
| laps with a spin | **6 of 9** | **0 of 8** |
| clean laps | 1 of 9 | 6 of 8 |
| best lap | 101.916 | **100.455** |

**10.7x fewer catches.** The best lap is the best Racing Medium lap on file
(previous 100.692) - but it is inside his own lap-to-lap noise and is
**corroboration, not evidence. The evidence is his report and the catch count.**

**Two clicks found the ceiling in one run instead of four**, which is exactly
what the bracket was for.

## 28. ⛔ THE ROTATION INDEX WAS FOOLED, AND HE WAS RIGHT

```
  baseline (s157, full send)      99.55
  two clicks   arb_r 5            79.12   <- 20.4 BELOW baseline = 2.1x the floor
  one click    arb_r 4           100.31   <- on the baseline, says nothing
```

**By the instrument, two clicks did exactly what section 24 predicted** - it fell
by far more than the 9.89 floor, in the predicted direction. **The prediction
would have been scored CONFIRMED. It was measuring the wrong thing.**

**Oversteer produces yaw for free.** At two clicks the rear was sliding - 198
opposite-lock frames a lap and six spins in nine laps - so the car generated yaw
per degree of lock without turning where he wanted it. **`steering_deg_per_yaw_rate`
cannot tell "the car is rotating" from "the rear is going away", and it scores a
loose car well.**

⇒ **NEVER quote this index as a rotation verdict without a stability count beside
it.** Written to the store as its own `unresolvable` verdict so the axis result
above cannot be read as the index having worked. It is blind in **both**
directions here: at the setting he calls perfect it sits on the baseline.

**This is CLAUDE.md rule 1 doing its job** - the driver's report is primary
evidence, telemetry is corroboration, and *where the two disagree, that
disagreement is the finding*. It disagreed, it was checkable, and the check
sided with him.

## 29. Where the bar bit - and it is a mechanical-grip story

Catches per lap, two clicks against one, 100 m bins:

```
  3,700-3,800 m   164 km/h     34  ->   4
  3,800-3,900 m    47 km/h     58  ->   4
  4,100-4,200 m    68 km/h     72  ->   7      <- the slowest corner on the lap
  every other bin on the lap    0  ->   0
```

**92 % of it falls in two SLOW corners, and every fast corner is clean at both
settings.** That is what a roll-stiffness lever does: it trades rear mechanical
grip, and mechanical grip only decides anything where the wing is not carrying
the car. At 200+ km/h the extra bar was free - which is precisely his *"better
for all but one corner."*

**His account and the data agree line by line:** turn-in improved everywhere
(more rear roll stiffness, more rotation entering), and the one place it cost
him is where the rear had no aero to lean on.

Map: `sardegna-arb-catches-2026-09-10.png`.

## 30. Where the proposal was wrong, and it matters for the next one

Section 24's falsifier read: *"the rear steps out on brake release - his
signature. That means `arb_r` 4."* **The conclusion was right and the stated
symptom was wrong.** What happened was not a brake-release snap; it was
**losing mid-corner rotation in the slow corners, with spins**. Had the
falsifier been applied literally - watching brake release only - the run would
have been scored as "not falsified" and two clicks would have been kept.

⇒ **A falsifier should name the AXIS's failure mode, not the driver's habitual
one.** A rear bar too stiff costs rear mechanical grip; where that shows up is
wherever mechanical grip is what the car is standing on, which is the slow
corners - not necessarily in the phase the driver most often complains about.

## 31. ⚠️ THE WEAR NUMBERS WERE TAKEN ON THE OLD BAR

Every tyre rate on this file - RH 0.0498 / 0.0491, RM 0.0668 / 0.0645 - was
measured at `arb_r` **3**. The car now runs **4**, which loads the rear axle
differently, and **the rear-right is the wheel that ends every stint.** The whole
race plan rests on numbers taken on a car he is no longer driving.

⇒ **The next run is a 12-lap Racing Medium stint on the final bar, full send,
gauge open.** It re-baselines the number the race turns on. The three-compound
same-session run follows it; nothing else needs doing to the car.

## 32. Open predictions

| Prediction | Falsified if |
|---|---|
| RM rear-right wear on `arb_r` 4 stays within one gauge tick of 0.0668/lap | it moves more, and every stint length on file is re-derived |
| The 10.7x drop in catches holds over a full stint | catches climb back above ~60 a lap as the tyres go off |
| He reports no loose rear over 12 laps | he does, and `arb_r` goes back to 3 |

## 33. ⛔ RETRACTION: section 29's "two slow corners" was built on a contaminated speed profile

> **[DRIVER REPORT]:** *"no the corner I couldn't work is the 3rd last it's a
> blind left hander at about 165km/h"*

**He is right and section 29 is withdrawn.** Three separate errors, and the first
caused the rest.

### 33a. The 47 km/h corner does not exist

Section 29 quoted `3,800-3,900 m at 47 km/h`. **There is no 47 km/h corner
there.** That speed profile was taken over ALL nine `arb_r` 5 laps, six of which
contained a spin - so the bin median is **him already off the road**. Measured on
clean laps at the final setting, the same stretch runs at **187-206 km/h**:

```
  metres     arb_r 5, all laps     arb_r 4, clean laps
   3750             162                    176
   3800              59                    187
   3850              44                    197
   3900              70                    206
```

**I selected on the outcome and then described the survivors as terrain.** Same
error shape as RECONCILIATION AU2 on 9 Sep - filter on a symptom, then report the
filtered set's character as though it were the place.

### 33b. His corner is FAST, not slow

Corner minima from clean laps on the final setup, 20 m bins:

```
   600 m   97 kph  LEFT      3,020 m   77 kph  LEFT
 1,380 m   98 kph  right     3,700 m  172 kph  LEFT   <- HIS CORNER
 1,880 m  125 kph  LEFT      4,100 m   70 kph  LEFT
```

**The blind left at ~3,700 m, apex 172 km/h.** The car-state file already named
it at Rev D as *"3,641-3,788 m (L, 176 km/h - the corner he complained about)"*.
**He has flagged this same corner before and I pinned a different one.**

⇒ **The map was wrong and has been redrawn** (`sardegna-arb-catches-2026-09-10.png`).

### 33c. The mechanical-grip story is withdrawn

Section 29 concluded the bar *"only bit where the car is leaning on mechanical
grip, not wing."* **That does not survive.** Where the car FIRST got away on each
of the nine laps:

```
  1,337 · 1,471 · 1,970 · 3,066 · 3,075 · 3,705 · 3,718 · 4,206 m   (one lap clean)
```

**All over the lap.** And catches per lap by region: his corner **43.7**, the slow
left after it **76.4**, **everything else 77.6**. Not 92 % in two corners - that
figure came from 500 m zones that swallowed the aftermath of each loss.

⇒ **The rear was loose everywhere at two clicks.** His corner is where it *cost*
him, because it is fast and blind and demands commitment - not because it is the
only place the bar bit. **A corner can be where a fault is felt without being
where it lives.**

### 33d. What survives, unchanged

- **`arb_r` 4 confirmed.** His report, plus **197.7 -> 18.5 catches a lap** and
  six spins in nine laps becoming zero in eight.
- **In his corner alone: 43.7 -> 5.6 catches a lap.**
- **The rotation index was fooled** (section 28). Unaffected by this retraction -
  if anything strengthened: the index scored a car that was loose *everywhere* as
  rotating better.

### 33e. The lesson, and it is the same one twice in three days

**Never build a speed or terrain profile from laps selected by the symptom you
are studying.** Compute the reference profile from clean laps at a known-good
setting, then overlay the symptom on it. Both times this bit, the error looked
like a physical finding and read perfectly plausibly.

⚠️ **And ask him what he calls the corner before naming it.** He calls this one
*"the 3rd last"*; the app's own model finds six corners on a fifteen-corner
circuit, so it cannot count to it. **His numbering is the vocabulary.**

---

# Session 159 - 12-lap race sim vs Div 2, 10 Sep 2026. **WON IT, P1.**

**P1 at the flag**, after losing 10.2 s and two places on lap 3. P1 -> P3 (lap 3)
-> P2 (lap 4) -> **P1 from lap 8 to the flag**. Racing Mediums, no stop, full
send, on `arb_r` 4. 81.7 L used of a full tank.

## 34. The three open predictions

### ✅ 1. WEAR ON THE NEW BAR - HELD, and almost exactly

**0.0660 +/- 0.0008 per lap** against the **0.0668** measured on `arb_r` 3.
Difference **0.0008** against a gauge tick of 0.0278. ⇒ **the bar did not move
the wear rate, and every stint length on file stands.** That was the one thing
that could have invalidated the race plan and it did not.

### ✅ 2. NO DEGRADATION - trend over laps 4-12 is **-0.043 +/- 0.065 s/lap**

Flat, on Racing Mediums run to **80.6 % worn**. Third independent confirmation
that this compound does not fall away before ~90 %.

### ⛔ 3. "NO LOOSE REAR" - one spin, and IT WAS NOT THE CAR

Lap 3, in **his blind left**. The frames are unambiguous:

```
  3,737 m   169 km/h   54.3 deg lock   1.46 g   TTTT
  3,750 m   167 km/h   34.0 deg lock   1.30 g   TGTG   <- FRONT-LEFT AND REAR-LEFT ON GRASS
  3,762 m    16 km/h  -180.0 deg lock                  <- spun
```

**He ran out of road on the exit and put the left-hand pair on the grass. The
spin followed the grass; the grass did not follow a slide.** Off-tarmac frames
in that corner: **lap 3 = 42, lap 5 = 85, lap 10 = 10.** Three laps of running
wide in the same place.

⇒ **This is track limits, not the setup** - the same shape as the Daytona Round 6
debrief, where 4 of 5 offs were track limits. `arb_r` is not implicated and must
not be moved for it.

## 35. ⛔ THE CATCH COUNT DOES NOT SURVIVE A RACE, AND MY PREDICTION MIS-USED IT

Whole-race average is **57.6 catches a lap** against **18.5** in practice on the
same car - which reads as a 3x regression. **It is not. Split by what he was
doing:**

```
  FREE AIR      laps 2, 6, 10, 11        median   7 a lap   <- BETTER than practice's 18.5
  in traffic    laps 4, 5, 7             median  25
  RACING        laps 1, 3, 8, 9, 12      median 123
        lap 1  the pack off the line          54
        lap 3  the spin                      186
        lap 8  took the lead P2 -> P1        144
        lap 9  first lap defending P1         87
        lap 12 last lap                      123
```

**Every high lap is a racing event and every quiet lap is free air.** In clean
air the car is *better* than it tested in practice.

⇒ **`opposite_lock_frames_per_lap` measures the driver's SITUATION as much as the
car.** It is a clean instrument in practice and a contaminated one in a race.
**Prediction 2 was not falsified - the metric was mis-specified**, and had I
scored it literally I would have concluded the bar had gone backwards. Any future
use of it across a race must be split by free air against traffic first.

## 36. ⭐ [MEASURED] RACING BURNS 5.7 % LESS FUEL THAN PRACTICE

**6.760 L/lap racing against 7.167 hot-lapping.** A 100 L tank therefore goes
**14.8 laps, not 14.0** - which lengthens every fuel-bound stint in the plan.

⚠️ **Do NOT adopt it into the race plan yet.** He spent this race in a pack, and
a tow is the obvious candidate; a 28-lap race led from the front may burn the
practice rate instead. **`unmeasurable_because` the app cannot see proximity to
another car** - §5.3 of CLAUDE.md says the same about detecting a tow. **Ask him
whether he was in traffic, or measure it on a race led alone.**

## 37. Pace, and the price of the one mistake

```
  race best      100.944 (lap 2)        practice best 100.455
  race median    101.771 over 9 clean racing laps
  lap 3 S3        43.271 against a 33.101 median   ->  10.2 s lost, two places
```

**He won by driving the other eleven laps well enough to absorb a ten-second
mistake.** The incident is the largest single item in the race and it is his
line, not the car - which is the more useful finding, because it is free to fix.

## 38. Open predictions

| Prediction | Falsified if |
|---|---|
| The blind-left exit is a repeatable track-limits problem, not a one-off | he runs the same line clean over a full stint with no off-tarmac frames there |
| Racing fuel of 6.760 L/lap is a TOW effect | a race led alone from the front also comes in near 6.76 |
| In free air on this bar he stays under ~10 catches a lap | a clean-air lap goes above 30 |

## 39. The fuel drop was partly WEATHER - the driver's hypothesis, tested. 11 Sep 2026

> **[DRIVER REPORT]:** *"I was in a tow and you should know that from the app
> pulling gap to car in front and screen shots"* - then - *"lobby is random
> weather so maybe that was the cause?"*

**Two corrections to section 36, both his.**

**1. I said the app could not see proximity. It can** - `gap_reads` holds the
gap ahead and behind. Read, it shows a **0.323 s tow on lap 6** and clean air from
lap 8 when he took the lead. **Fuel towing laps 2-7: 6.747 L/lap. Leading alone
laps 8-12: 6.768.** The tow explains **0.02 of the 0.41 L/lap** gap to practice.

**2. It was not "race pace" either.** Every 10 Sep session burns ~6.7 (s157
L10-14 6.705, s158 6.758, s159 6.749); every 9 Sep session burns ~7.1 (s153
7.063, s154 7.174, s155 7.079). **It is a day-level difference, not race vs
practice.**

### The wind test

Same gear + same speed = same rpm = same engine output, so a change in
acceleration is a change in air resistance. Main straight, flat out, off the
limiter, straight line:

```
                      5th, 235-245 km/h      6th, 255-262 km/h
  9 Sep   s153 RH           1.222
          s154 RM           1.306                  0.444
          s155 RS           1.194
  10 Sep  s157 RM L10-14    1.333
          s158 RM           1.528                  1.028
          s159 RM race      1.583                  1.139
```

Setup between s154 and s158 changed only `arb_r`, which does not touch drag, and
s158 carried MORE fuel. **So the extra resistance on 9 Sep was a headwind on the
main straight.** Terminal speed there rose **+6-7 km/h**; the back straight, at
**94 deg** to it, did not move - the signature of wind along one axis.
**Sardegna cannot rain (`track_layouts.rain = 0`), so "random weather" here is
wind.**

### What it explains and what it does not

- ✅ the main-straight speed gain, and part of the fuel drop;
- ⚠️ **not all of it** - rev-limiter time fell **3.16 -> 1.0-1.35 s/lap** in gears
  1-4 all round the lap, and coasting rose **0.8 s/lap**, mostly lifting into the
  125 km/h left at ~1,900 m. Those are driving.
- ⛔ **tested and wrong:** the silent 5th-gear beep on 9 Sep. The limiter time was
  in 1st-4th, not 5th.
- ⚠️ **s157 does not fit cleanly** - windy-ish acceleration (1.333) with low fuel
  (6.705), on 3 laps. The weather may have been changing through that evening.
  **Wind and driving cannot be split exactly from what is on file.**

### What it does to the plan - NOTHING, and that is the useful part

```
                     windy-day fuel         calm-day fuel
  RM saving, 2 stop   29 laps  leader        29 laps  leader
  RM full send        29 laps  +12.2 s       29 laps  +9.8 s
  RH saving, 1 stop   29 laps  +14.3 s       29 laps  +15.7 s
  RH full send        28 laps  a lap down    28 laps  a lap down
```

**The order is identical at either fuel rate.** Every plan except RH full send
now reaches 29 laps because sessions 158/159 moved the engine's reference lap
**102.778 -> 102.261 s**.

⚠️ **The app's planner now defaults to 6.751 L/lap** - the calm-day figure,
weighted towards the newest sessions. **Load fuel on the windy figure (~7.1)**:
the lobby weather is random, and in a timed race running dry is the one outcome
with no recovery. That is not a spare lap - it is the weather's own range.

**Still no compound call** - section 23 stands: the top plans sit ~12-16 s apart
on a cross-session compound delta, which is a tie. The same-session
three-compound run is still the thing that settles it.

---

## 40. RACE PLAN DECIDED BY THE DRIVER - one stop, Racing Mediums, fuel-save stints. 11 Sep 2026

> **[DRIVER]:** *"race will be one stop on mediums, we will know the fuel rate when
> we fill up based on what we have used and george will know the wind conditions
> from the first stint."* - and - *"fuel save saved tyres and fuel and can make a
> one stop on RM work."*

**The engine agrees, on the same inputs, calm day or windy:**

```
  RM one stop, saving      29 laps   RM15 / RM14   fastest
  RM two stops, saving     29 laps                 +31.5 / +32.3 s
  RM two stops, full send  29 laps                 +34.5 / +37.4 s
  RH one stop, saving      29 laps                 +41.9 / +40.9 s
```

Fuel on saving stints: **74-89 L per stint** - fits, calm or windy. (My first
answer led with full-send rows, which do not apply to this plan. Recorded as
`feedback_hold_the_agreed_plan`.)

**Fuel at the stop - confirmed in code.** George sizes the fill from *this
race's* burn: `coordinator.py:814-854` uses the current stint's measured rate
once it has three clean laps, and `calls.py` `fuel_target_l` sizes the fill from
it. Nothing reads wind directly, and nothing needs to - the stint-1 burn carries
it.

**The two open items, and neither changes the plan:**

1. **Rear-right past 89% is unmeasured on this compound.** Saving rate 0.0645/lap
   puts it at ~90% after 14 laps and **~97% after 15**. The last clean medium lap
   on file is 89% (s154 L13, 101.578). The Soft cliffed at 89-100%. **One practice
   run settles it: a 15-lap RM stint, saving, from full.**
2. **George will say "Tyres are at the end of their window" at ~85% in each
   stint** - `calls.py` `_tyre()`, hard-coded `0.85`, LOW confidence. It is a
   report. **It cannot add a stop** if the approved plan's playbook does not allow
   one (`_within_the_playbook` strips structural actions). No plan is stored for
   event 11 yet.

**Stint order proposed: 15 first, 14 second** (the engine's own split). The long
stint runs while a stop is still available - if the rear falls away at 90%+, he
can box a lap early. Run the other way round, the 97% laps are the last laps of
the race with no remedy.

## 41. Stint order set by the driver: 14 then 15. And the app cannot arm the plan yet. 11 Sep 2026

> **[DRIVER]:** *"14 then 15 track position is more important and tyres wear less
> with less weight from slightly less fuel in second stint"*

**Order is his call and it stands: RM14 / RM15, fuel-save stints, one stop.**

**The weight claim, checked - the data does not show it.** Rear-right wear, heavy
half of a stint against light half, same tyre set each time:

```
  s154 RM full send   0.0675 -> 0.0665   -1%
  s159 RM race        0.0619 -> 0.0694   +12%
  s153 RH full send   0.0496 -> 0.0506   +2%
  s156 RH saving      0.0472 -> 0.0515   +9%
```

Fuel and tyre age fall and rise together inside a stint, so this cannot separate
them - but "lighter wears less" appears in none of them. ⇒ **Budget stint 2 at the
same rate or worse: 15 laps projects to ~97-100% on the rear-right, at the flag,
with no stop left.** The 15-lap RM saving practice stint is now the single most
important run before the race.

### The plan could not be written into George

Dry-run through `from_dict` -> `validate` (clean) -> `stamp` -> `certify`:

```
  refused: stint 1 runs 14 laps on a tank that reaches 13
  refused: stint 2 runs 15 laps on a tank that reaches 13
  unchecked: stint length, because no wear rate has been measured
```

`certify` prices fuel reach off `inputs.fuel_per_lap_l` - the event's FULL-SEND
burn (6.751) - and nothing in a plan can declare a saving stint. It is enforced
at the write door, at approval (`approve_stored_strategy`) and at the grid
(`start_race`), so there is no route round it. **It would have refused the Monza
one-stop that won.** Its tyre check reads `inputs.wear_per_lap` (None) instead of
the per-compound measured wear, so it skips the one part of this plan that is
genuinely tight. **Nothing was written.** Filed as app work.

Also: no plan field can arm the fuel-save beep. George engages short-shift only
when fuel projects short, and stint 1 at 14 laps is not fuel-short - it saves for
the tyre - so as things stand he would save with no cue.

**Until the certifier is fixed:** race without an armed plan (the Race screen
offers it), short-shift from the beep table by hand, and George still sizes the
fill from the stint-1 burn.

---

# Session 177 - 29-lap race sim, RM/RM one stop, 15 Sep 2026. **P1 laps 17-26, finished P8.**

**Rank zero:** gearbox byte-identical to s159 (FEED). The other values rest on the Rev H sheet
(`arb_r` 4) and are **not re-confirmed** - screenshot asked for. **MFD read off the OBS capture**
(video t = race elapsed + ~15 s), not from memory or the event row:

| laps | brake balance | TCS |
|---|---|---|
| 1-8 | +3 (never shown on screen - his word) | 1 from the green |
| 8-11 | +2 | 1 |
| 11-22 (across the stop) | +1 | 1 (3 on the in-lap, back to 1 on the out-lap) |
| 23-29 | 0 | 1 -> **3 at L27** -> **5 during L28** |

## 42. What happened

- Stint 1 RM laps 1-13 + in-lap 14, P14 -> P3 by lap 6. Fill **60.6 L**. Stint 2 RM laps 15-29.
- **P1 from lap 17 to 26.** Car #89 (RH, stopped L15) closed **25 s -> 4.5 s** laps 18-25.
- **L27 (RR 89 %):** off at **the blind left** (~3,748 m) - right-hand pair on the grass first,
  then the spin. Third time on file in that corner (s159 L3). Track limits, not the car. -> P5.
- **L28 (RR 97 %):** 106.8 s, every sector slow, TCS 5 intervening on 16.7 % of the lap.
- **L29 (RR 100 %):** **three spins on tarmac**, all four wheels on the road, each at 0-7 %
  throttle - the cliff. **And the tank ran dry.** 162 s lap, P4 -> P8.

## 43. The medium cannot do 14-15 laps - §40 open item 1 CLOSED, and §41's warning came true

`[MEASURED]` measurement ids 129-131. RR 0.068/lap to ~80 %, then **3 gauge ticks a lap instead
of 2** in both stints. Past 89 % the medium goes: an off on the first lap past it, +4.5 s on the
next, undriveable on the last. §41 predicted "15 laps projects to ~97-100 % on the rear-right, at
the flag, with no stop left" - **confirmed, and the consequence was worse than the wording.**
Usable life on this car at this pace: **12 laps (~81 %)**, 13 at the outside (~89 %).

`[MEASURED]` id 133: **RH at the saving beep ran 19 laps to 94 % with no pace loss** (s156).

## 44. Fuel - the fill was margin-free

`[DERIVED]` id 136. Installed burn at the stop 5.519 L/lap x 15 laps = 82.8 L against 83.7 L aboard.
Stint 2 burned **5.60**: laps 20, 21 and 28 were shifted at ~8,000 rpm (the chase), plus the
L29 spins. Short by ~0.5 L; it cost ~60 s and four places. George logged *"Fuel reaches the flag
now. Plan stands."* and *"Save fuel from here. 9 litres light - about 1.6 laps."* four seconds
apart after the stop - **app work**, not a car finding. **Who chose 60.6 L is asked.**

## 45. TCS and brake balance - what the frames can and cannot say

- **TCS** (id 134): on 1 the flag fires on ~0.4 % of a lap. 3 and 5 came on a dead tyre and did
  not prevent the L29 spins, which were **off throttle, where TCS does not act**. Resolves the
  Sardegna half of `reference_gt7_flags_and_abs_signature`: **TCS 1 was in the car.**
- **Brake balance** (id 135), +3 laps 2-7 against +1 laps 16-21, same tyre age: rear p5 slip
  under heavy braking **0.9321 -> 0.9417**, rear in the ABS band **1.8 % -> 0.0 %** - less rear
  braking work, ~1.6x the floor, the direction a forward move should give. **Confounded:** +3 was
  passing cars, +1 was leading in free air, 16 L lighter. `[DRIVER REPORT]` *"I think +1 is
  best."* **His report decides; the frames lean the same way and cannot separate it from traffic.**
  ⚠️ `bb +3` was confirmed on **RH** on 5 Sep (s130); +1 is from **RM** - whether the hard wants
  +1 or +3 is asked, not assumed.

## 46. RACE PLAN PROPOSED - RM 12 -> RH to the flag. Awaiting his yes. 15 Sep 2026

**[DRIVER]** *"need a combo of RH + RM not sure which order."*

**The binding limit is the tyre** - the medium's cliff - in both orders; fuel binds only in the
RH-first order's opening stint (below). The app's planner cannot rank this: `pace_delta_s = 0.0`
for every compound, so it picks RH/RH. Measured gap at the saving beep **+1.14 s/lap** (id 132).

| plan | tyre on the last lap | cost against RM12/RH17 `[DERIVED]` |
|---|---|---|
| **RM 12 -> RH 16-17** | RH ~81-87 % (no cliff on file to 94 %) | - |
| RH 16 -> RH 13 (planner's pick) | RH ~66 % | +13 s (12 more laps on the hard) |
| RM 10/10/9, two stops | RM ~68 % | +13 s (second stop ~32 s off today's pit lap, against 19 s of hard) |
| RH 17 -> RM 12 | **RM ~81-89 %, the cliff at the flag** | ~0 s on pace; see why not |
| RM 14/15 (the §41 plan) | RM 97-100 % | **refuted today** |

**Why the medium first:** (1) the tyre with the cliff runs while a stop is still available -
box a lap early and the hard has two measured laps in hand; (2) a 17-lap opening stint on the
hard needs 94-99 L of the 100 L he starts with and nothing can top it up - on a windy day it runs
dry before the stop; the medium-first long stint gets a fill sized off his own stint-1 burn; (3)
he starts in traffic, which is when the faster tyre earns most (P14 -> P3 in six laps today).
**The price:** he defends on the slower tyre at the end.

**Window:** box end of lap 12; earliest 11 (hard to ~92 %), latest 13 (medium to ~89 %).
**Fill:** laps left x stint-1 burn + **3 L** (~3 s in the box, bought against today's 60 s).
**Lap count is on a knife edge:** today lap 28 ended 3.1 s before the clock with ~14.5 s of
incidents in it; 17 laps on the hard adds ~19 s. **28 or 29 - fuel for 29.**

**Certifier dry run (nothing written):** RM 12 / RH 16 at 28 laps -> *Driveable* (stint length
unchecked: no wear rate). RM 12 / RH 17 at 29 -> refused (clock allows ~28; tank reserve caps
16). RH 17 / RM 12 -> refused (stint 1 on a tank that reaches 16).

## 47. Open predictions

| Prediction | What would prove it wrong |
|---|---|
| RM to the end of lap 12 stays above today's stint-1 pace with no off-track caused by the tyre | a tyre-led slide on tarmac before the stop, or RR past 89 % by lap 12 |
| RH 16-17 laps at the saving beep reaches the flag under 90 % with lap times flat | RR past 90 % before the last lap, or the last three laps >1 s off the stint median |
| A +3 L fill reaches the flag with 2-4 L left | dry again, or more than ~6 L left |
| +1 brake balance holds on the hard | he reaches for the MFD in the hard stint |

## 48. Answers, settings screen, and the plan ARMED - 15 Sep 2026, later

**SCREEN, 15 Sep 2026 - "current setup and this was run in latest race sim".** Every visible value
matches the sheet on file: tyres RM/RM · body height 60/68 · anti-roll bar 5/**4** · compression
23/25 · expansion 38/38 · natural frequency 3.40/3.60 · camber 1.0/1.0 · toe 0.00/+0.08 · LSD
5/14/24 · downforce **440**/600 · ECU 100 · ballast 0/0 · restrictor 100 · transmission Fully
Customisable: Racing, **Top Speed 240** (ratios by FEED, identical) · 509 BHP · 1,243 kg · 46:54 ·
PP **746.59**. Stability readout Low -0.31 / High -0.18 (Rev A read -0.31 / -0.35) - recorded,
not interpreted (§0). **Rank zero closed for s177.**

- `[DRIVER]` *"george recommended much more fuel I chose that fuel"* - the 60.6 L was his, against
  George's larger fill (sized to the flag with a lap of margin, `calls.fuel_target_l`). §44's
  shortfall is a fill choice, not a George sizing fault. The contradictory log pair stands as app work.
- `[DRIVER]` *"I'll stick with +1 for now, I moved to 0 to try and save rear tyres"* - measured
  (id 138): rear-right 0.0675/lap on +1 against 0.069 on 0, same set. **No saving visible**, inside
  one gauge tick over four laps.
- **TCS 1/3/5** (id 137): no level cost measurable drive (full-throttle acceleration 5.1-5.6 m/s²
  on all three). The one matched pair - last flying lap on TCS 1 against the in-lap on TCS 3 -
  shows **less wheelspin out of corners on a more worn tyre** (16.8 % -> 10.6 %). TCS 5 could not
  hold a 100 % tyre and the last-lap spins were off throttle. **Level and tyre wear moved together
  all race, so this is a hint, not a finding.**

**Plan decided by the driver: RM 12 -> RH 17, fuel-save.** `[DRIVER]` *"George needs to accept
this through fuel saving it's been proven in practice."*

**ARMED as strategy 33** (approved, certified *Driveable*; unchecked: stint length). Written as
**RM 12 / RH 16, 28 laps**, because the certifier refuses 17: (1) its tank reach adds a reserve lap
at the event burn 5.586 L/lap -> 16; (2) its clock charges each stop the next stint's whole load at
the pump and allows ~28. **It drives the same race:** George boxes on lap 12 and sizes the fill to
the flag off the live clock and live burn, so a 29-lap race is filled for 17. What it cannot do
yet is know the stints are fuel-save stints - filed as app work (declared fuel-save stints: tank
reach and clock on the measured saving burn, and the fuel-save beep armed for them).
Playbook: fuel_short -> short_shift · tyre_short -> bring_stop_forward (stint 1, not before lap 11)
· stop_missed -> recost_to_flag · fuel_long, incident, rain -> report_only.

## 49. George now runs the fuel-save beep and the 29-lap ceiling - strategy 34 ARMED. 15 Sep 2026

`[DRIVER]` *"Georges fuel number recommended was 96L not even close ... the race can never be more
than 29 laps ... write the fuel save into George it's critical and set the shift beeps for fuel
save ..."*

**Why 96 L:** George counts laps left as `ceil(clock left / lap)` while the clock still holds the
stop (~16-17 laps), and in a timed race whose count is "not firm" adds a whole spare lap. 23.1 L in,
15 laps left, installed burn 5.519 -> 82.8 L needed at pit exit. Replayed with the ceiling:
**84.4 L** (15 laps + 1.6 L measured spread).

**Built (commit f3eea5a):** plan fields `max_race_laps`, `fuel_burns {save, full}`, stint
`fuel_save`; certify reaches fuel-save stints on the saving burn; George caps laps at the ceiling
(count firm, no spare lap), starts each declared stint on the fuel-saving points (7,400 in 1st-5th,
`shift_points` id 1), goes to full revs on the run to the flag when the tank reaches at the full
burn with the fill's margin + 1 L, and back to saving when it stops reaching; says *"Full beeps.
Fuel reaches the flag."* / *"Fuel-save beeps."* A box or any other call no longer releases the
saving beep. The beep returns to full revs at race close.

**Strategy 34 (approved, supersedes 33):** RM 12 -> RH 17, both `fuel_save`, `max_race_laps` 29,
`fuel_burns` save 5.25 [MEASURED s156/s157 at the beep] / full 6.76 [MEASURED s158/s159] - replaced
by this race's own burn after two clean laps on a column. Certified with one warning (clock model
allows ~28; ceiling 29).

**Predictions for the next sim:** (1) the stop fill George names lands within ~2 L of laps left x
stint-1 burn; (2) no "Full beeps" in stint 1; in stint 2 it comes only once the tank reaches 29 at
full revs; (3) the beep is on 7,400 from the grid. **Proves it wrong:** a fill 5 L+ over; a full-revs
switch followed by a fuel-short call inside three laps; the beep at 8,500 on lap 1.

---

# Session 179 - 28-lap race sim on strategy 34 (RM 12 -> RH), 15 Sep 2026 evening. **P17 -> P1 laps 17-25, spin L26, finished P4.**

**Rank zero:** not re-confirmed for s179 - the s177 SCREEN (§48) is the last ground truth; asked. Brake
balance and TCS for tonight were not read off the video.

## 50. Debrief

`[DRIVER]` *"George told me too much fuel"* · *"RM to RH worked but RH feel slippery into the cold in evening"*

**Plan against actual.** Stints 12 / 16 (plan 12 / 17 at a 29-lap ceiling). RM RR 72 % at lap 11; RH RR 83 %
at the flag, clean laps 102.1-103.8. Burn 5.34 over 22 green laps. Stop 23.6 s ex-fuel + 60.8 L at 1.00 L/s.
Game clock 17:33 at the green, 21:00 (its stop) from lap 20.

**Fuel** (measurement 141, `[DERIVED]`). Arrived 36.0 L, left 96.8 on George's *"Fuel to 97 litres. 17 laps
after the box"*. 16 laps needed ~85 L -> **12 L over**: ~5 L was lap 29, genuinely live (a clean stint 2 ends
lap 28 with ~6 s on the clock) until the L18 and L26 spins took ~32 s; **~6 L was a spare lap past the 29-lap
ceiling, which cannot run** - ~6 s stood in the box. Replay of the same laps on the same code: 91 L and a
"Full beeps" at lap 22. Live: 97 L and no full-beeps call in the log, yet shifts went 7,400 -> 8,400 from L25
(L25/L27 102.1 against ~103.3 saving). Flag 4.9 L. **App work**, filed.

**The hard in the evening** (139-140, `[MEASURED]`). Free-air RH laps 19-24 (P1) against daylight RH at the
same tyre age and fuel: exit wheelspin 4.1 % v 2.3 % (s156) / 1.95 % (s153); tyre temps within 1-2 °C; **~1.2 s
a lap quicker**. The control kills the attribution: tonight's **daylight medium** ran 2.8 % against s177's 1.1 %
at the same game clock, and s177's evening medium (0.9 %) was no looser than its daylight (1.1 %) with rears 2-3 °C
cooler. ⇒ tonight was looser on exits from the green, on both tyres; **the evening is not visible in it**, and
the feed carries no track temperature. His report stands as primary evidence; unresolvable on telemetry.

**Every off was the blind left** (142). L9 RM 58 %: rear stepped out mid-corner at 2-11 % throttle, all four on
tarmac. L18 RH 31 %: throttle 81 -> 14 % at ~55° lock, yaw doubled on the lift, then kerb/grass, then the spin.
L26 RH 72 %: ~8 km/h more entry speed, never back on throttle, right-hand pair on the grass first. Two of three
are off-throttle rear slides on tarmac - TCS cannot act there. With s177 L27 and s159 L3 this corner owns every
off on file in the race sims. Not a single-lap input marker (CLAUDE.md 23 Aug amendment) - a pooled best-corner
build is the route if he wants it.

**No setup change.** One evening's report against a control that shows the same looseness in daylight is not a
basis for moving a slider on both compounds. Asked: rank zero, where the slip is felt and on which pedal,
whether the dark matters at the blind left, and who switched to full revs at lap 25.

**§50 answers, same night.** Full revs from lap 25 was his call off the fuel readout. The hard "felt looser as
the stint went on" - wheelspin out of corners rose with wear the same way the daylight hard's did (s156), so that
trend is wear-shaped; the evening still cannot be separated from it. **Lap 29** (143): the offs cost L9 6.5 s,
L18 11.4 s, L26 22.2 s against a race that ended lap 28 26.9 s past the clock. No single off lost the lap; lap 26
with either other did. Lap 26 alone: 4.7 s short - inside George's ~6 s spare-lap fuel. Had 29 been on, full revs
from lap 25 would have run dry (32.6 L with 5 to go).

**Not visibility** - `[DRIVER]` *"adjusting from RM to RH and less grip"*. Over 13 hard laps he took the blind left at the
hard's own speed (minimum ~160 km/h, same as s156 practice; free-air medium ~164). The two hard offs were the laps at
or past the top of that range: L18 minimum 166; L26 arrived 215 km/h against 183-199 on every other hard lap. The
medium-to-hard swap inside one session has only ever been driven in the two race sims.

## 51. RH -> RM considered after s179 - recommendation: keep RM 12 -> RH 17. 15 Sep 2026

`[DRIVER]` *"should we try RH to RM or leave it as it is?"* - asked because the swap to the hard is the hard direction to adapt to (§50).

**Binding limit, hard first: the TANK.** Saving burns on file: 5.18 (s156 practice), 5.35 (s179 both stints), 5.59 (s177
stint 2, chase laps). A 17-lap hard opening stint from 100 L: 91 L at 5.35 (9 L left), 95 L at 5.59 (5 L left); **18 laps
at 5.59 is dry**. So the hard-first stint is capped at 17, and the medium must then do 12 whatever happens.
**Medium at 12 laps:** RR 72 % at L11 (s179), 81 % at L12 and 89 % at L13 (s177) - one lap from the cliff.
⇒ Hard first: any extra burn or a longer race moves a lap onto the tyre with no lap to give, at the flag, with no stop
left (the s177 ending). Medium first: the stop is sized from his own burn, and the hard has room either side (83 % after
16 tonight incl. 4 at full revs; 94 % at 19 in s156). Same fuel added in the box either way (~55 L).
**What hard-first buys:** the swap goes to MORE grip; the medium runs light at the end. **What it costs:** the start in
traffic on the slower tyre, and the only flexible stint becomes the one that cannot flex.
**Decision offered: keep RM 12 -> RH 17**, and practise the swap (3-4 laps RM, box, 5-6 laps RH) so the first lap on
the hard after a medium is not in a race. Falsifier for keeping it: a practised swap still produces an off on the hard.
His call; strategy 34 unchanged.

## 52. Rd 9 qualifying - NO SETUP CHANGE. 15 Sep 2026, for 16 Sep 20:30

`[DRIVER]` *"one out lap and one flying lap only in porsche cup"*. Hub, series defaults (division not on the hub):
5 min + 120 s continuation, **20 L fixed**, tyre wear and fuel SAME_AS_RACE (8x / 3x), slipstream DISABLED,
grid by fastest lap. Qualifying plan id 35 written (fuel 20, one run: out-lap + one flyer).

- **Tyre:** Racing Soft. Only soft laps on file are s155 (9 Sep, `arb_r` one click softer than the car now,
  `bb +3`): 100.247 on its first full lap - the app's reference lap - then 102.3 / 100.5 / 101.0 as the
  rear-right lost ~14 % a lap, cliff at 89 %. Best medium 100.455 (s158 L16, current bar, 65.9 L). One lap each,
  inside his own scatter: the soft is quicker on doctrine, not on a clean comparison.
- **Fuel:** out-lap + flyer ~14 L at 7.0-7.2 L/lap [MEASURED s153-155]; ~6 L spare. Not a lever.
- **Why no slider moves:** nothing can be tried before the one lap that sets the grid; the Rev A quali column is
  [DOCTRINE] from before Rev B-H and was never driven; the last untried step on this car (`arb_r` +2) spun 6 of 9
  laps (§27). He has driven the car clean at under 25 L (s179 L27 102.1 at 18.5 L).
- **Gap named:** the current bar (4) has never run on the soft; s155's lap 1 began at speed, so no real pit-lane
  out-lap on the soft exists here. `bb` on the soft is his: the only soft laps ran +3, he races the medium on +1.
- **Beep:** Practice screen with the Qualifying intent -> performance table. The Race screen would arm strategy 34's
  fuel-save beep (checked in `controller.py` `_follow_fuel_mode` / `_arm_quali`).

**Prediction:** a clean flyer on the soft lands within ~0.5 s of 100.247. **Wrong if** a clean flyer is slower than the
best medium (100.455) - then the soft is not buying the lap on this car and the out-lap is the suspect.

## 53. Quali practice (s181) and the swap practice (s180) - 15 Sep 2026, late. NO SETUP CHANGE.

**Rank zero:** gearbox by FEED identical to the fitted box on both sessions. Other values rest on the s177 SCREEN (§48).
`bb` for both runs not known - asked.

**s181 - Racing Soft, pit-lane out-lap + 3 flyers, at 100 L** (not the lobby's 20 L). Measurement 144.
- Flyers **99.745 · 99.640 · 100.088** (L4 1.17 s off-track). **The first flyer is 0.1 s off the best** - fastest two
  laps on file here. Tyre temps flat from flyer 1 to 3 (FL ~60, FR 65, RL ~64, RR 69 by lap mean): the out-lap does the
  whole warm-up, as at Deep Forest. RR 14 % after the out-lap, 28 % after flyer 1.
- **The current bar on the soft closes §52's gap:** no spin on any flyer. Soft ~0.8 s quicker than the best medium on file
  (100.455, s158, ~66 L) at similar fuel - two sessions, not a same-set A/B, but far outside his lap-to-lap scatter.
- **20 L tomorrow is ~58 kg lighter, the nose (tank) most:** [DERIVED] ~0.2 s at 0.003 s/L/lap, and the balance change is
  UNMEASURED on the soft. He has driven the hard clean at 18.5 L (s179 L27).
- **Out-lap off at the blind left:** right-rear onto the grass first at **101 km/h, throttle closed** for 1.5 s before,
  294 grass frames, spin to 26 km/h, then a reset. Cause asked - with one out-lap tomorrow, this is the lap that cannot go wrong.
- L4 right-front onto the grass at the blind-left exit at 173 km/h minimum (L2/L3 170, clean).

**s180 - the swap practice §51 asked for (RM 6 laps, box, RH 4 laps).** The blind left had grass under a wheel on RM L1, a
spin to a stop on RM L3 (~3,790 m), and **every hard lap after the out-lap**: L9 146 frames (1.95 s off, min 139 km/h),
L10 71, L11 7 - right front first each time, and the laps got quicker (103.8 · 102.1 · 101.7). **§51's falsifier - "a
practised swap still produces an off on the hard" - fires on the hard's first flying lap.** Race-plan question, not quali;
reopened for his call, strategy 34 unchanged.

**Tonight, pooled over both sessions:** 7 of 15 flying/out laps put a wheel on the grass at the blind-left exit.
[MEASURED, pooled, no input marker issued - CLAUDE.md 23 Aug amendment.]

## 54. Per-lap targets issued to George - strategy 36 ARMED. 16 Sep 2026, race day

`[DRIVER]` *"the lap time delta for each compound and fuel burn rates for George to manage me to"*.

**NO SETUP CHANGE.** The plan is strategy 34's, unchanged: RM 12 -> RH 17, both stints on the 7,400
beep, pit lap 12, 29-lap ceiling. What is new is the four lap times George judges every lap against
and two burns re-measured off last night's race. Written as **strategy 36, approved and armed**
(measurements 145-151; `race_knowledge` for event 11 filled the same turn).

### The four targets, and where each came from

| | full revs (8,500) | on the beep (7,400) | at |
|---|---|---|---|
| **RM** | 101.300 s `[DERIVED]` | **102.300 s** `[MEASURED]` | 46 L |
| **RH** | 102.210 s `[MEASURED]` | **103.260 s** `[MEASURED]` | 49 L |

- **RM saving** - s177 laps 17-26, free air at P1 on the current bar, n=8, sd 0.62 s. Those laps
  shifted ~7,550, ~150 rpm above the issued beep, so on the beep it is if anything a touch quick.
- **RH saving** - s179 laps 19-24, free air at P1, n=6, sd **0.22 s**: the tightest lap-time set on
  file for this car and circuit.
- **RH full revs** - s179 laps 25, 27, 28, three laps after the saving laps on the *same set*.
  Implies a beep-to-full-revs delta of **1.05 s/lap**, which reproduces s157's within-stint 1.00 s
  on the medium. The method validates itself here.
- **RM full revs is the weak one.** Three readings, 0.8 s apart: 101.300 `[DERIVED]` from the saving
  target minus the 1.00 s within-stint delta; 101.774 `[MEASURED]` racing (s159, n=9, 10 Sep);
  100.985 `[MEASURED]` in practice (s158 laps 12-19, n=8). The derived one was passed because a
  *within-session* delta is immune to the day-to-day pace drift that separates the other two
  (§50: 15 Sep was looser all night on both tyres). **Three full-revs laps in tonight's practice
  settle it.**
- Compound gap from these four: **RH is 0.96 s/lap slower on the beep, 0.91 s at full revs.**
  Measurement 132 put it at 1.14 s on the old rear bar.

### ⛔ NO WEAR TERM ON EITHER TARGET, and that is deliberate

The app's `pace_loss_s` charges **1.00 s** across the 50-90 % band. Measured on this car it is
**+0.10 s** (RM, s177 laps 17-26, free air) and **+0.23 s** (RH, s179 laps 14-24) - and on s156 the
curve over-charged a 94 % hard by **4.2 s** on a lap that lost nothing. Both stints tonight finish
at 81-83 %, which is exactly where the curve is worst, so a wear term would have George calling him
~0.8 s slow on the last third of every stint. Passed as `wear_per_lap_source: "author"` with no
value - answered, not zeroed (rule 3). **The wear RATES are unchanged and still size the stints.**

Honest caveat: within-session learning and traffic push the measured slope both ways (s177 stint 1
gives **-0.62 s** across the band), so the real finding is that **pace loss is not resolvable on
these laps** - not that it is zero. Measurement 151.

### Burns, re-measured off s179

- **Saving 5.33 L/lap** `[MEASURED]` - 19 green laps actually on the beep (7,390-7,444 rpm): RM 5.34,
  RH 5.32. Replaces strategy 34's 5.25, which came from the 10 Sep practice pair on the **old bar**.
  s177's 5.49 was driven 150-230 rpm above the beep, which is the whole difference.
- **Full revs 6.86 L/lap** `[MEASURED]` - s179 laps 25/27/28, the only full-revs laps in a race on
  this car this week and at the load band where the release actually happens. Heavier-load figures
  are 6.75 (s159 n=10) and 6.76 (s158 n=8). The richer figure holds the beep slightly longer, the
  safe direction after §50 (full revs from lap 25 would have run dry on a 29-lap race).
- **Saving costs 1.00-1.05 s/lap and buys 1.53 L/lap.**

### Replayed against the two race sims before arming

s179 free air at P1, laps 19-25 and 27: delta **within +/-0.06 s** every lap, saving and full revs
alike, burn within 0.03 L. Traffic laps read correctly slow (lap 2 from P17: +3.1 s). s177 free-air
stint 2 median +0.1 s; its burn reads +0.1 to +0.3 L over, which is the session shifting above the
beep showing up exactly as it should.

## 55. Open predictions from §54

| Prediction | Falsified if |
|---|---|
| In free air on the beep he runs within 0.3 s of 102.30 (RM) and 103.26 (RH) | he is consistently more than 0.5 s either side with no traffic and no incident |
| The hard's target holds flat to the flag with no wear term | his clean hard laps drift more than 0.5 s slower over the stint |
| Saving burns 5.33 +/- 0.10 L/lap on the 7,400 beep | two clean saving laps come in outside 5.2-5.45 |
| RM at full revs lands nearer 101.3 than 101.8 | three clean full-revs medium laps median 101.7 or slower |

## 56. Rank zero CLOSED and the compound order CLOSED - 16 Sep 2026, before the lunchtime sim

`[DRIVER]` *"settings haven't changed bb +1"* · *"RM to RH"* · *"I am doing another full race sim at lunch today"*

- **Rank zero 1a answered.** No value has moved since the s177 settings-screen photograph (§48),
  and brake balance is **+1**. That photo plus his confirmation is the ground truth for tonight;
  no new screenshot needed unless something moves. Rank zero 1b (FFB after 1.71) was closed 5 Sep.
- **§51 and §53 CLOSED: medium first.** He has taken RM 12 -> RH 17. §53's falsifier - *"a practised
  swap still produces an off on the hard"* - fired on s180, and it is recorded as fired; his call
  stands over it, and the reason it survives is §51's arithmetic, which the falsifier does not
  touch: a hard-first opening stint is tank-capped at 17 laps, which forces the medium to 12 at the
  flag with one lap left before its cliff. **Strategy 36 is the plan, unchanged.**
- **The lunchtime sim is the falsification run for §55.** Run on the Race screen so strategy 36 arms
  and George calls the targets; every one of §55's four predictions is scored by it.

### ⚠️ What the sim cannot answer, and one thing to check before the green

- **It cannot produce a full-revs MEDIUM lap.** George holds the saving beep to the stop on a
  fuel-save stint, so stint 1 will be entirely on the beep. §54's weak figure (RM at full revs,
  three readings 0.8 s apart) therefore stays open unless a separate 4-lap run is driven - and it is
  only ever used if the medium becomes the run to the flag, so it is a contingency number, not a
  race number.
- **It will add n to the HARD at full revs for free**, because George releases the beep on the run to
  the flag. Present n is 3.
- **⚠️ THE GAME CLOCK IS UNVERIFIED FOR THE RACE.** Both race sims greened at in-game **17:33** and
  ran to the 21:00 pin (s177, s179 - `tod_start_ms`). The event row says **19:22**, `clock_source`
  `typed`, and the hub publishes no start time at all for this round - only
  `variableTimeSpeedRate: 6`, which matches. So **every target on file was measured from a 17:33
  green.** If the league lobby greens at 19:22 the whole race runs about two hours later in game
  than anything measured, and his *"the hard feels slippery into the cold in the evening"* (§50)
  would land on the entire race rather than its last third. **Asked.** Because `clock_source` is
  `typed`, `record_measured_clock` will never overwrite it from the feed - the latch
  `hub/calendar.py` names. App work if it needs clearing, not car work.

# Session 183 - 29-lap race sim on strategy 36, 16 Sep 2026 lunchtime. **WON IT, P1.** Race day.

**Rank zero:** `[DRIVER]` nothing moved since the s177 screen; `bb` **+1** (§56). Gearbox by FEED unchanged.

## 57. Debrief - the targets held, the fill did not, and TCS 3 cost nothing

`[DRIVER]` *"still too much fuel advised"* · *"had to go to TCS 3 at end of race"*

P10 -> P1 from lap 6, stop end of lap 12, P20 -> P1 by lap 16, lap 25 spin to P3, back to **P1 at the
flag**. 29 laps - the ceiling ran. Measurements 153-162; **strategy 37 written and armed** off it.

### ⛔ The fill: 6 L over, and the cause is in the app, not the plan

George, lap 12: *"Fuel to 97 litres. 17 laps after the box, **at the practice burn**."* Seventeen laps
at the measured beep burn is **91.2 L**. He asked for 97: **6 L, and therefore ~6 s standing at the
pump** at 1.00 L/s. **Identical to s179's 97 L, and now the cause is known.**

`ExpectationTracker.note_lap` flags any lap carrying `short_shift_rpm` as a saving lap and `_clean()`
drops it - correct for a one-off engineer instruction, which is what it was written for. But since
the `fuel_save` plan field a whole stint declares the beep, and then **every lap carries it**: 500.0
on all 29 laps here, including laps 27-29 which he drove at full revs. So `green_laps()` never
reaches `BURN_LAPS_NEEDED`, **`"burn installed on lap N"` logged ZERO times**, and
`state.fuel_per_lap_l` held practice's ~5.586 for the whole race. Every fuel sentence rested on it.

⇒ **CLAUDE.md rule 10 again**: a filter that on this class of plan can never be satisfied, failing
silently - the only clue in the whole race was four words inside one spoken call. App work, filed.

**What he actually drove, and why 97 was not punished:** laps 13-26 on the beep burned **5.346**
L/lap; laps 27-29 at full revs burned **6.865**. He finished on **1.07 L**. The 6 L of over-fill was
spent on a full-revs endgame he chose after the lap-25 spin - so it was used, not wasted, but by
accident rather than by plan. **The arithmetic says do not plan it:** 3 full-revs laps cost
3 x 1.52 = **4.5 L = 4.5 s at the pump** and buy 3 x 0.835 = **2.5 s on track**. Net **-2 s**.
Strategy 37 therefore fills stint 2 to **93 L** and stays on the beep.

### ✅ The targets held. The hard's apparent 0.9 s is off-track time, not pace

| | scored against strategy 36 | |
|---|---|---|
| RM saving | **+0.30 s** median, n=10 | §55 row 1 **HELD** |
| RH saving, all green | +0.92 s median, n=14 | looks falsified |
| RH saving, **no wheel off the road** | **+0.15 s**, n=5 | §55 row 1 **HELD** |
| burn on the beep | RM 5.421, RH 5.370 against a 5.33 target | §55 row 3 **HELD** |
| flat target, no wear term | hard's clean laps did not drift over 13 laps | §55 row 2 **HELD** |

**The hard stint spent 14.15 s off the road over 16 laps, against 2.37 s over 10 medium laps**, and
13 of the race's 27 excursions fall in the 3,550-3,850 m band - the blind left and its approach.
That corner is still where the road position goes. Pooled; no input marker issued.

Targets re-derived pooled over all three race sims and re-issued as **strategy 37**: RM
**102.370** saving / 101.535 full at 52 L; RH **103.387** saving / **102.552** full at 50 L; burns
**5.365** on the beep and **6.88** at full revs. §54's weak figure is now bracketed by its two direct
readings (101.00 practice, 101.79 racing) where it was not before.

### ✅ TCS 3 cost nothing - and it does not protect against what actually bit him

TCS 3 from lap 25 is **visible in the feed**: flag bit 11 on 6.8-9.2 % of moving frames against
0.1-1.9 % on TCS 1 (measurement 159). His report is corroborated - **exit wheelspin rose 4.71 %
(lap 14) to 8.40 % (lap 24)** across the hard stint against 3.23-6.10 % on the medium, with the
rear-right surface up 69.5 -> 76.4 degC. Endogenous with wear and temperature; the s183 wear gauge
FAILED (read 1.00 on laps 1-4 of a fresh medium, then nothing), so it ties to no wear number.

**Cost:** 2nd/3rd full-throttle 80-160 km/h gave **5.43 m/s2 on TCS 3 against 5.08 on TCS 1, on an
older tyre**. Raw that is 2.9x the 0.125 lap-to-lap floor - but the TCS 1 laps rise +0.033/lap on
their own, and once that trend is carried forward the residual is +0.11, **inside the floor**.
⇒ **TCS 3 cost no acceleration.** Any gain is not resolvable. Same direction as measurement 137.

### ⚠️ The lap-25 spin was NOT the blind left, and it is the same input as s179 L18

At ~700 m, the left after the opening right. Throttle **77 -> 9 -> 2 -> 1 %** while the steering ran
to -61.7 deg; **yaw reversed and doubled on the lift** (+0.234 -> -0.775, lat g 2.75), then all four
onto the grass at 711 m, spin to a stop, U-turn, rejoin. P1 -> P3, 11.1 s.

s179 L18, at 3,700 m: throttle 89 -> 81 -> **14 %** at ~55 deg lock, yaw doubled on the lift, off.
**Two of the three largest losses on file are the same thing at two different corners: an
off-throttle rear release at high lock.** So the failure mode is **the lift, not the corner** - and
**TCS cannot act on a closed throttle**, which is why TCS 3 did not stop it and will not tonight.

**No setup change.** One mechanism, two instances, seven hours before a race is not a basis for
moving a slider. The coast side of the diff (`lsd_b`) is the direct lever and has never been swept
on this car; the LSD sweep is already open in the ledger. **Offered for after the race.**

## 58. Open predictions from §57

| Prediction | Falsified if |
|---|---|
| Filling stint 2 to 93 L reaches the flag with 1-2 L in hand on the beep | he finishes under 0.5 L or over 4 L with no full-revs laps |
| George says ~97 L again at tonight's stop, from the practice burn | he says 91-93, or the log carries "burn installed on lap N" |
| Free air on the beep lands within 0.3 s of 102.370 (RM) and 103.387 (RH) | consistently more than 0.5 s either side, clean and unimpeded |
| The next big loss is an off-throttle rear release at high lock, wherever it happens | it is a braking lock-up, or a mid-corner slide with throttle applied |

## 59. 6th gear - ISSUED 1.348 -> 1.318, for the tow, NOT for the fuel. 16 Sep 2026, race day

`[DRIVER]` *"6th gear is close to revving out I want to lengthen it to reduce fuel burn more"*

**Rank zero, FEED:** ratios byte-identical to 9 Sep - 3.041 / 2.329 / 1.900 / 1.621 / 1.446 /
**1.348**, `top` 240, final 3.050. Nothing has moved; he has got quicker on the same box.

### His premise is confirmed, and it belongs to ONE stint (measurement 164)

| | 6th top rpm, s183 | 6th top speed | headroom to the cut |
|---|---|---|---|
| **Medium**, free air (L6-11) | 8,390-8,439 | 268.3-269.5 km/h | **7.5 km/h** |
| Medium, in traffic (L3) | 8,491 | 271.4 km/h | 5.1 km/h |
| **Hard** (L14-26) | 8,083-8,332 | ~258-266 km/h | 10-18 km/h |

Cut ~8,515-8,589 (this session's own limiter frames, gears 1-5); 6th tops at **276.5 km/h**.
**Zero limiter frames in 6th all race.** The Rev F box was cut for ~11 km/h of tow headroom
(ledger 3a, 9 Sep) and **that intent is no longer met on the medium** - 7.5 km/h and falling as he
improves. The race runs `slipstream: REALISTIC` in a 26-car field of identical cars.

### ⛔ The FUEL case does not survive its own arithmetic

6th burns **27.1 % of the race's fuel in 18.0 % of the lap time** (measurement 165) - 1.5x its share,
because it is 95 % full throttle. So it is the right gear to attack. But:

- **Peak power is at or above the cut** (measurement 166): a x v at WOT, drag-corrected by matching
  the same rpm across gears 3/4/5/6, still RISES to 8,375 rpm in 3rd. **There is no power band above
  his terminal.** Every metre of lengthening moves terminal DOWN the curve.
- **The obvious curve is a trap** (measurement 167): fuel rate in 6th runs 0.064 L/s at 7,125 rpm to
  0.112 at 8,375 - but in a fixed gear rpm and road speed are locked, so that slope is drag as much
  as fuel flow. Lengthening changes rpm at a given speed and does **not** change the drag. Reading
  the saving off it would overstate it by an unknown factor.
- **The prize, sized honestly.** A 4-5 % lengthening is worth about 1.8 L over the race = **1.8 s at
  the pump**, one-off. It costs perhaps 0.1-0.15 s/lap of drive - which over 29 laps is **3-4 s**.
  ⇒ **net loss**, and I cannot size the lap-time half from anything on file. `unmeasurable_because`
  no ratio A/B has ever been driven on this car.

### What is issued, and why 1.318

**6th: 1.348 -> 1.318** (-2.2 %). Nothing else moves - not `top`, not the final drive, not gears 1-5.

- 6th at the cut: 276.5 -> **282.8 km/h**. Tow headroom on the medium 7.5 -> **13.8 km/h**, back past
  the box's own design intent.
- Cost: rpm at 269 km/h falls 8,421 -> 8,233; power there 249.3 -> 247.9, **-0.55 %**. Terminal
  falls about **0.5 km/h** `[DERIVED]`. Below anything he can feel and below the 0.56-2.77 km/h
  terminal floor on this project.
- Fuel: about **1 L over the race** `[DERIVED]`, a side effect, not the reason.
- 5->6 landing on the saving beep: 6,899 -> 6,742 rpm. Still on the strong part of the curve.

**⚠️ THE SHIFT TABLE DOES NOT CHANGE, and here is why rather than "it is fine".** 6th is silent
because there is no 6->7 to cue, and lengthening 6th cannot change that. It does deepen the 5->6
drop, which moves the optimal 5->6 upshift LATER - but the performance table already has 5->6 at
**8,500, the limiter**, so it cannot move later. `shift_points` id 1 stands, both columns, unchanged.

### Prediction and falsifier

**Predicts:** zero limiter frames in 6th all race including behind a car; free-air terminal within
1 km/h of 269 on the medium; burn 0.02-0.05 L/lap lighter on matched laps.
**Falsified if:** terminal drops more than 1.5 km/h, or he reports the car going soft onto the
straight, or 6th tops below 8,000 rpm in free air on the medium - then it goes straight back to 1.348.

**VERIFY BEFORE THE GREEN:** `fitted_ratios` off his first practice lap must read
3.041 / 2.329 / 1.900 / 1.621 / 1.446 / **1.318** with gears 1-5 untouched. GT7's gear sliders can
drag their neighbours; the feed is the only honest check and it is the one setup value it can make.

### §59 CONFIRMED BY SCREEN - 16 Sep 2026, before/after photographs of Manual Adjustment

**ISSUED -> SCREEN.** Both screens read: `top` 240, Final **3.050**, and
1st **3.041**/122 · 2nd **2.329**/160 · 3rd **1.900**/196 · 4th **1.621**/230 · 5th **1.446**/257,
with 6th **1.348 -> 1.318**. **Gears 1-5 and the final drive did not move** - the thing that had to
be checked, because GT7's gear sliders can drag their neighbours. PP 746.59 on both, unchanged by
the ratio (and matching §52's SCREEN). Power 509 BHP / weight 1,243 kg = the round's limits exactly.

**The x1.060 sixth-row anomaly reproduced on both boxes**, which is an independent check that the
screens are being read correctly: gears 1-5 mean `K = speed x ratio x final` = **1,134.9**
(spread 5.6; the 5 Sep record is 1,134.5, spread 4.2), while 6th implies 1,200.5 before
(**x1.0578**) and 1,202.0 after (**x1.0591**) against the recorded x1.0601 / x1.0597.

⇒ **The screen's 299 km/h is not the top of 6th.** Computed from the ratio, as §"Gearbox CONFIRMED"
says to: **276.0 -> 282.3 km/h at 8,500 rpm, +6.3.** Against today's free-air medium terminal of
269.0 km/h that is **7.0 -> 13.3 km/h of tow headroom**, and rpm at 269 km/h falls 8,421 -> 8,234.
Both land inside the §59 prediction (282.8 km/h, 13.8 km/h, 8,233 rpm).

## 60. Rd 9 race debrief (s188, 16 Sep; debriefed 17 Sep 2026) - nothing in the car moves

**Nothing on the sheet changes.** Rank zero stands at §59's SCREEN. Ledger 3f carries the rows.

- ⛔ **Dry at the flag.** George: *"Fuel to 89 litres. 17 laps after the box, at this race's burn."*
  Strategy 37 said 93 L. Tank 88.1 L at L13, race burn 5.21 L/lap, **0.00 L from ~4,976 m of L29**,
  coasted 245 -> 228 km/h to the line (~0.3 s, no place). "Fuel good to the flag" was said every lap
  from L14 to L28 on a margin of about nothing. The b51f680 fix installed the race burn and the fill
  lost its spare litres with it. App work (measurement 168).
- **Plan held:** RM 12 -> RH 17 as planned, stop 24.3 s ex-fuel, pace RM +0.17 / RH -0.42 s on target.
- **Race craft:** four places lost up the inside of left-handers off a tow (measurement 170); Rocky
  closed ~0.9 s/lap from L16 and a catch on lap 25-26 was projectable from L20 (measurement 169).
- **L29 T3 was contact** - `[DRIVER]` *"boxhead hit me I have lodged a ticket"*; the lateral-g collapse at turn-in agrees (measurement 172).
- **Driver request 17 Sep:** George to flag a car close enough behind that he must defend, especially onto the long straights. App task filed.
- **6th gear:** limiter never touched; terminal speed confounded by wind - unresolvable (measurement 171).
