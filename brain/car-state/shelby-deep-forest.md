# Ford Shelby GT350R '16 — Deep Forest Raceway, Full Course

**The ONLY place a setup value for this car+circuit may be written.** Every
other file links here and restates nothing — including the chat that issued it.
Each run records its source: **SCREEN** (settings screenshot — ground truth) ·
**FEED** (telemetry; the gearbox is the only value the feed can verify) ·
**ISSUED** (a request, not a reading).

> ✅✅ **FULLY VERIFIED, 6 Sep 2026 — and this is the first complete record in
> the programme.** Settings screenshot for the 22 page values, Manual Adjustment
> read for the six ratios and the final gear, and the driver for brake balance.
> **23 of 23. Nothing is left as ISSUED.**
>
> The RSR came closest before, at 14 of 14 *visible* — but its gearbox and its
> brake balance were both still unread. **This car is the only one whose every
> setup value has a source, and whose gearbox is confirmed twice over — SCREEN
> and FEED, in agreement.** It took eleven days of asking.
>
> **One value differed from the record and it was never on a sheet at all:**
> **brake balance is `-2`.** Every sheet says `0`, except Road Atlanta Rev B
> which says `-1`. `-2` is **two clicks FORWARD** on this car. His own in-car
> trim — recorded, never corrected.

**Event: NGR Supercars Series 1, Rd6 · Deep Forest Raceway · 6 Sep 2026 10:30 UTC**
*(hub round `cmrbgn23c000s01n04rlhn39h`, `lobbySettingsOverrides = null`, so the
series defaults below apply unmodified.)*

```
  30 MINUTES, timed  + 180 s finish delay   ->  ~19-20 laps
  2x tyre / 2x fuel · initial fuel 100 L · refuel 2.0 L/s
  0 mandatory stops · STANDING start · grid by FASTEST LAP
  Weather FIXED / CLEAR · RS / RM / RH  (no wets, no inters)
  ABS PROHIBITED · TCS PROHIBITED · countersteer PROHIBITED
  BoP OFF, tuning ALLOWED, weight limit 1335 kg, category ROAD_CAR
  Full Course · 4,253 m · 18 corners · Gr.3 reference 1:26-1:29
```

**Range record: measured 23 Aug 2026, GT7 v1.71, `verified = 1`.** Post-patch,
so it survives the 20 Aug discontinuity. Percentages below are against it.

---

# Rev A — **SCREEN-confirmed 6 Sep 2026.** Mechanicals carried from sheet 50.

Sheet 50 `Red Bull Ring Short race Rev B` is the setup session 101 (the Round 5
race) actually ran. **Every mechanical value is held for Deep Forest** — the
reasoning is in `brain/_inbox/setups/2026-09-06-shelby-deep-forest.md` §3.

```
                                RACE (Rev A)                  % of range
──────────────────────────────────────────────────────────────────────────────
TYRES
  Front / rear compound   Racing Soft                         RS/RM/RH allowed

SUSPENSION
  Body height    Front    89 mm                               16.5%
                 Rear     107 mm                              14.1%
  Natural freq.  Front    3.05 Hz                             52.5%
                 Rear     3.20 Hz                             60.0%
  Anti-roll bar  Front    5    <- SCREEN, dispute CLOSED      44.4%
                 Rear     4                                   33.3%
  Damping compr. Front    24                                  20.0%
                 Rear     28                                  40.0%
  Damping expan. Front    40                                  33.3%
                 Rear     38                                  26.7%
  Camber angle   Front    1.4 deg                             23.3%
                 Rear     1.0 deg                             16.7%
  Toe angle      Front    -0.05 deg                           47.5%
                 Rear     +0.10 deg                           55.0%

DIFFERENTIAL  — absolutes on this sheet. The absolutes-only rule is RETIRED
               (retired 11 Sep 2026: all four cars read on v1.71 carry 0-30 / 0-100 / 0-100 - `11`)
  Initial torque          5
  Acceleration sens.      17     <- doctrine wants 20-26 here; HELD, see sheet
  Braking sens.           34

AERODYNAMICS
  Downforce      Front    150                                 100.0%  (MAXED)
                 Rear     260                                 73.3%

BRAKES
  Brake balance           -2   <- SCREEN 6 Sep 2026           30.0%
                          TWO CLICKS FORWARD on this car. His own trim, and
                          it has drifted forward across the season: sheets say
                          0, he stated -1 on 23 Aug, the car reads -2 today.
                          With ABS PROHIBITED that is 20% of the bias range.
                          His to make, mine to record and NEVER to correct.

PERFORMANCE
  Ballast / position      109 kg @ 0    <- SCREEN, CONFIRMED IN THE CAR
                          Total weight reads 1,335 kg = EXACTLY the series
                          weight limit, so the MASS is a regulation, not a
                          lever. Only the POSITION (0) is tunable.
  ECU / restrictor        100% / 100%   <- SCREEN

TRANSMISSION  — ⚠️ SUPERSEDED BY REV B, below. Rev A ran session 133.
  Gear ratios             3.400 / 2.410 / 1.760 / 1.500 / 1.320 / 1.165
                          SCREEN (Manual Adjustment, 6 Sep) **and** FEED
                          (sessions 101 and 133), in agreement.
  Final gear              3.600                               53.3%
  Top Speed readout       270    <- SCREEN. Records said 265, carried over from
                          sheet 45 and never re-read after the box was hand-cut.
                          270 is the READOUT of THIS box. See below.
  Shift beep              ISSUED 6 Sep 2026, `shift_points` id 2:
                          performance 8500 / 8250 / 8250 (gears 1-3 only)
                          fuel-saving 8000 / 7750 / 7750
                          GEARS 4, 5, 6 SILENT ON PURPOSE.
──────────────────────────────────────────────────────────────────────────────
```

## The gearing constant, re-derived 6 Sep 2026 — **[MEASURED]**

Across 156 laps and three different gearboxes, `ratio x (km/h per rpm)` is
constant within a session at **0.0345**, and the rev limiter sits at
**~8,800 rpm**. So:

```
      K  =  ratio  x  speed at which that gear reaches the limiter  =  304 km/h
```

Road Atlanta and RBR return the same constant to **0.3%**, which also confirms
they ran the same final gear (3.600) and the same rolling radius. Speeds at the
limiter for the box above:

| gear | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| km/h at limiter | 89 | 126 | 173 | 203 | 230 | **261** |

This supersedes the "`top` is the road speed at which 6th reaches the limiter"
rule written on the RBR sheet, which was refuted when `top` 265 produced a 6th
topping at 291 km/h. `top` is a **spacing** slider; **K is the invariant.**

### And the readout moves the WRONG WAY — measured 6 Sep 2026

With the ratios now read off the screen, the two RBR boxes can be compared
directly, and the result is worth keeping:

| box | Top Speed readout | 6th ratio | 6th ACTUALLY tops at |
|---|---:|---:|---:|
| sheet 45, auto-generated | **265** | 1.050 | **290 km/h** |
| sheet 50, hand-cut *(current)* | **270** | 1.165 | **261 km/h** |

**The readout went UP by 5 while the real top speed went DOWN by 29.** So
`Top Speed (Automatically Adjusted)` is not a top speed, is not the generator
input once you have hand-cut, and is not any gear's limiter speed. **Never read
a road speed off it.** Record it, ignore it, and reason from K.

---

## What GT7's own readout says about this car — 6 Sep 2026

| | |
|---|---|
| Performance Points | **723.61** (the 575.47 in `07-car-profiles.md` is pre-1.71 and void). No PP cap on this series. |
| Weight / balance | **1,335 kg**, **54 : 46 front**. FR, NA, Voodoo 5.2 L. |
| Power / torque | 606 BHP · 64.3 kgf·m |
| **Stability** | Low speed **-0.29 (Neutral)** · **high speed -0.50 (UNDER)** |
| Rotational G | 1.43 @ 60 · 1.52 @ 120 · 1.74 @ 240 km/h |

⚠️ **Three independent indicators now say the front is this car's limit**, and
Deep Forest is the circuit where that costs the most (its own reference names
front tyre life as lever #1):

1. GT7's own readout: **high-speed understeer, -0.50**.
2. Measured wear at RBR: **front-left is the limiter in all four sessions**, at
   ~1.6x the front-right.
3. **Two clicks of forward brake bias with ABS prohibited**, plus `lsd_b` 34
   holding the rear stable on entry.

`df_f` is already **maxed at 100.0% of range**, so the only aero move left that
helps the front is to **lower `df_r`**. That is run 2 on the sheet.

## Open against this car

| | Status |
|---|---|
| **`arb_f` 4 or 5** | ✅ **CLOSED 6 Sep 2026 — it is 5.** App sheet 31 (Road Atlanta Rev B) reads 4 and is the wrong record. See `RECONCILIATION` AS1. |
| **Ballast 109 kg @ 0** | ✅ **CLOSED 6 Sep 2026** — in the car, and the mass is a regulation. |
| **FFB / Fanatec settings post-1.71** | ✅ **CLOSED 6 Sep 2026** — driver: *"DD+ wheel settings are perfect, in game FFB 6 SEN 10."* Grip readings from here are valid. |
| **The Round 5 wheelbase fault** | ✅ **EXPLAINED, not a car problem.** Driver: the wheelbase **locked up from a Fanatec GT7 error after the 1.71 update**, since fixed by a Fanatec firmware update. This is what ended session 101 — laps 14 and 15 carry 20.2 s and 10.4 s off-track and the run stops at 15:04 with 904 s left. **Nothing after lap 13 of that race describes the car.** |
| **Top Speed 265 vs 270** | 🔴 **NEW, OPEN.** One tap on Manual Adjustment settles it. |
| **Six ratios** | ⚠️ FEED-verified at session 101 and matching sheet 50, but **not re-read since**, and the Top Speed readout has moved. |
| **`lsd_a` 17 -> 24** | **PROPOSED 26 Aug, NEVER RUN.** Sheet 50 still reads 17. Demoted below the aero test. |

---

## History

| Date | Circuit | Sheet | Source | Note |
|---|---|---|---|---|
| 13 Aug | Yas Marina | 5 / 12 / 18 | ISSUED | v1.70, pre-patch — void as evidence |
| 23 Aug | Road Atlanta | 31 | ISSUED | `arb_f` 4 here, 5 everywhere else |
| 27 Aug | RBR Short | 45 | ISSUED | `top` 265 auto box |
| 29 Aug | RBR Short | 50 | ISSUED | hand-cut box + `de_r` 32->38, **two changes in one run** |
| 6 Sep | Deep Forest | this file | ISSUED | all mechanical values held |

---

# Rev B — **gearbox only. FEED-CONFIRMED in session 134, 6 Sep 2026.**

> ✅ **The feed reads `3.400 / 2.330 / 1.600 / 1.360 / 1.205 / 1.085` on every
> lap of session 134** — the box you set is the box that ran. Rank zero stays
> 23 of 23.

**Nothing else on the sheet moves.** Rev A's 22 non-transmission values
stand exactly as SCREEN-confirmed above.

```
TRANSMISSION
  Gear ratios      3.400 / 2.330 / 1.600 / 1.360 / 1.205 / 1.085
  Final gear       3.600  (unchanged)
  Top Speed        will re-read after the cut - it is a readout, record it only

  Shift beep       shift_points, re-issued for THIS box:
                   performance   1: 8500   2: 8500   3: 8250
                   fuel saving   1: 8000   2: 8000   3: 7750
                   gears 4, 5, 6 SILENT
```

## Why — session 133, 4 clean laps, 21,780 frames

**K re-derived here: 304.6 km/h** (limiter median 8,798 rpm, 998 limiter frames,
constant 0.03463 across six gears with 3.6% spread). That is a **third
independent circuit agreeing with the 304 from Road Atlanta and Red Bull Ring.**

**The whole top of the box is a wall.** Every gear-stint peaked at its own
ceiling, not where the driver chose:

| gear | tops at | stints/lap | peak reached (median) | |
|---|---:|---:|---:|---|
| 3 | 173.1 | 6.8 | — | upshift range only **4.1 km/h** wide |
| 4 | 203.1 | 6.8 | **199.3** | 11 of 27 stints peak 199-203 |
| 5 | 230.8 | 4.0 | **230.1** | at the ceiling |
| 6 | 261.5 | 1.8 | **261.1** | **Vmax 265.2 · 998 limiter frames** |

Driver-discretion shifts scatter (up 1→2 spans 32.0 km/h, up 2→3 spans 20.3).
Forced shifts do not: **up 3→4 spans 4.1, up 4→5 spans 4.1, up 5→6 spans 4.5.**
He has no say in where 3, 4 and 5 end, and 6 ends before the circuit does.

**The measured effect of the new 3rd (tops 190.4 instead of 173.1):** of 27
fourth-gear stints across 4 laps, **9 never exceeded 190.4 km/h** — they were
short hops between linked corners, 0.5-6.0 s long. Those collapse into a single
3rd-gear sequence. **≈4.5 gearchanges per lap removed**, and that is precisely
the driver's report: *"some gears are between corners."*

**And the cascade is forced, not a preference.** Lengthen 3rd to 190 and 4th at
203 becomes a 13 km/h gear; move 4th to 224 and 5th at 231 becomes a 6 km/h
gear. Gears 3-6 move together or not at all.

**Every landing rpm sits on measured ground:**

| shift | lands at | measured comparison |
|---|---:|---|
| 1→2 | 6,033 | tool: landing 5,843 gave 6.63 m/s² vs 6.29 staying — stronger after the shift |
| 2→3 | 6,041 | tool: landing 6,038 gave 4.67 m/s² |
| 3→4 | 7,478 | **spacing preserved**: old 3/4 ratio-step 0.852, new 0.850 |
| 4→5 | 7,795 | old step 0.880, new 0.886 |
| 5→6 | 7,922 | old step 0.883, new 0.900 |

Because the 3/4 step is preserved to 0.2%, the archive's **3→4 = 8,250
[MEASURED, 6,932 frames]** transfers directly. 2→3 goes later (8,500) because
its drop got bigger. Gears 4-6 stay silent: the archive has 76 and 14 frames
there and that has not changed.

---

## Rev B verified — session 134, 5 clean laps, 6 Sep 2026

**All three predictions held, and the gear-change estimate was accurate to 0.4.**

| prediction | result |
|---|---|
| gear changes drop ~4.5/lap | **31.2 → 26.4 = −4.9/lap** ✅ |
| the 998 limiter frames in 6th go to ~0 | **6th now has ZERO** ✅ (250/lap → 59/lap overall, none in 6th) |
| Vmax rises above 265.2 | **265.2 → 272.8 km/h (+7.6)** ✅ |
| 2→3 does not feel flat despite landing 400 rpm lower | no complaint from the driver ✅ |

Headroom, after: gear 3 **+8.0**, gear 4 **+3.4**, gear 5 **+1.0**, gear 6
**+14.4** km/h. Before, gears 5 and 6 had +0.7 and +0.3 — they were walls.

**Fuel fell with the box: 8.196 → 7.842 L/lap (−4.3%)**, which is the limiter
frames coming back as useful acceleration.

**One item left open, and it is small.** 2nd gear now runs past its own ceiling —
peak 134.7 against 130.7 — and holds **199 of the 293 remaining limiter frames
(39.8/lap)**. Gears 1, 4 and 5 hold the rest; **6th holds none.** Lengthening 2nd
to ~2.260 would clear it, but it would move the 2→3 shift point that session 134
has just validated. **Not worth a fourth box iteration before this race.**

---

## Tyre wear — MEASURED here for the first time, 6 Sep 2026

Session 134, HUD gauge, OBS on, 5 readings, monotone on all four wheels.
**Regression slope over laps 2-6:**

| wheel | %/lap | %/km | stint `0.85/w` |
|---|---:|---:|---:|
| Front left | 2.215 | 0.521 | 38.4 laps |
| **Front right** | **2.808** | **0.660** | **30.3 laps** ← limiter |
| Rear left | 1.967 | 0.462 | 43.2 laps |
| Rear right | 2.778 | 0.653 | 30.6 laps |

**The tyre does not bind.** 30.3 laps against a ~20.5-lap race — a 1.5× margin.

Two things this settles:

1. **The circuit reference's wear figure is refuted by a factor of ~4.** It
   says 13-16 laps at 1×, which halves to 6.5-8 at 2×. Measured: **30.3**. Filed
   as `RECONCILIATION` AS4.
2. **`wearSeverity` is anti-predictive here.** Deep Forest is graded **5** and
   Red Bull Ring **3**, yet Deep Forest's worst wheel runs **0.66 %/km** against
   RBR's measured **0.90-1.35 %/km**. Deep Forest is the *gentler* circuit per
   kilometre.

**The axle signature flipped and flattened.** At RBR the front-left led at ~1.6×
the front-right; here the **front-right** leads at 1.27× the front-left, and the
front/rear split is only 5.9% (front mean 2.512, rear mean 2.373). That is a
direction-balanced circuit behaving as its reference said it would — the one
part of that entry that held.
