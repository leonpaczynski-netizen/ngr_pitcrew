# What is in the car — Huracán GT3 '15 · Mount Panorama Circuit

**Round 7, NGR GR3 Season 1 · 14 Sep 2026 · GT7 v1.71**

**This file is the ONLY place a setup value for this car+circuit may be written down.**
Everything else — memory, `RECONCILIATION.md`, session notes — links here and restates
nothing. Car-level direction verdicts live in `huracan-gt3-AXIS-REGISTER.md` and are not
repeated here.

| source | what it is worth |
|---|---|
| `SCREEN` | read off the GT7 settings screen. Ground truth for 23 of 24 values. |
| `FEED` | verified from telemetry. Only the gearbox can be. |
| `ISSUED` | what Ludo asked for. **A request, not a reading.** Never promote without a screenshot. |

---

## Rank zero — ✅ `SCREEN` CONFIRMED, 8 Sep 2026

**Settings-screen screenshot received the same day it was issued.** All 14 suspension,
aero and differential values match the issued sheet exactly, and the gearbox is the only
row still unverified.

| | screen reads | |
|---|---|---|
| body height | 64 / 70 | ✅ |
| anti-roll bar | 5 / 6 | ✅ |
| damping compression | 20 / 20 | ✅ |
| damping expansion | 50 / 44 | ✅ |
| natural frequency | 3.70 / 3.90 | ✅ |
| negative camber | 2.0 / 1.2 | ✅ |
| toe | 0.00 / 0.12 | ✅ |
| diff initial / accel / braking | 6 / 18 / 35 (rear only — MR, front column reads 0) | ✅ |
| downforce | 410 / 635 | ✅ |
| ECU output | 94 | ✅ as asked |
| ballast / position | 55 / −29 | ✅ |
| power restrictor | 99 | ✅ |
| top speed | 300 | ✅ |
| compound | RS / RS | ✅ |
| torque distribution | 0 : 100, no torque vectoring | — MR, as expected |

**Weight is exactly on the limit: 1,275 → 1,285 kg. PP 752.54 → 747.32.**

### ⚠️ Power landed at 536 BHP against a 540 limit — 4 bhp given away

`SCREEN`, 8 Sep. Not a mistake, a granularity problem. The two screen readings give
**6.0 bhp per ECU point exactly** (96 → 548, 94 → 536), so:

| ECU / restrictor | bhp | |
|---|---|---|
| 94 / 99 | **536.0** `SCREEN` | legal, 4 under |
| 95 / 99 | 542.0 `DERIVED` | **over the limit** |
| 94 / 100 | ~541.4 `DERIVED` | **over the limit** |
| 95 / 98 | ~536.5 `DERIVED` | legal, no better |

⇒ **536 may be the closest this car gets to 540 from below**, and the derived rows are
arithmetic off two screen readings, not measurements. **Check 94/100 and 95/98 on the screen
and keep whichever reads highest at or under 540.** If none beats 536, 536 is the answer and
the 4 bhp is unreachable.

### ⚠️ The ballast moved the weight balance forward — noted, NOT changed

**43:57 → 44:56** `SCREEN`. The +10 kg went in at position −29, which is forward.
**Mid-corner on this car is FRONT-limited** (`AXIS-REGISTER`: front slips about twice the
rear in every setup tested), so adding front weight is arguably the wrong direction —
but **ballast position has never been tested on this car**, the move is 1 % of the balance,
and rearward weight would cost traction at Forrest's Elbow, the highest-value exit here.
**Held at −29. Logged as a candidate test, not a change.**

### The gearbox is the one row the screen cannot confirm

The ratios sit behind *Manual Adjustment* and are not in the shot. **`FEED` is the only
ground truth for the box** — verify with `analysis/gearing.fitted_ratios` off the first
Bathurst lap, against 3.022 / 2.450 / 1.972 / 1.598 / 1.285 / 1.030.

---

## The round, resolved from the league hub

| | | source |
|---|---|---|
| format | **20 laps**, standing start | `Series.defaultLobbySettings` — Rd7 carries no override |
| tyre wear | **2×** | series default |
| fuel | **3×**, refuel rate 1 | series default |
| power / weight | **540 bhp / 1285 kg** | `SeriesCarEntry` — Rd7 carries no `RoundCarOverride` |
| BoP | **off**, tuning open | `carRegulations.bopEnabled = false` |
| compounds | RS · RM · RH · IM · WET | series default |
| weather | RANDOM — **but this track cannot rain in GT7** | `track_layouts.rain = 0` for `mount-panorama-circuit-full-course`; Spa and Fuji carry `rain = 1`, this does not |
| circuit | 6,213 m · 23 corners · 174 m elevation | `track_layouts` id 82 · hub `officialSpecs` |

⚠️ **Hub reading rule, learned this day:** a round row stores only what DIFFERS from the
series default. An empty `RoundCarOverride` means *inherited*, never *unpublished*.

⚠️ **The power/weight change is real and it is the one thing on this sheet that is not a
judgement call.** Daytona (Rd6) overrode to 550 bhp / 1275 kg and the car currently reads
**548 BHP / 1,275 kg**. Bathurst inherits 540 / 1285 ⇒ **−8 bhp and +10 kg**.

---

## The sheet as issued — 8 Sep 2026

Percent of the car's own slider range in brackets (`range_records`, verified, v1.71,
measured 24 Aug 2026).

| | Daytona race sheet (what is in the car) | **Bathurst, issued** | moved | why |
|---|---|---|---|---|
| ride height `rh` | 58 / 64 (12 % / 13 %) | **64 / 70** (36 % / 33 %) | ⬆ **+6 / +6** | clearance for the crests. **Rake held at exactly 6 mm** — the confirmed value |
| natural freq `nf` | 3.90 / 4.10 (45 % / 55 %) | **3.70 / 3.90** (35 % / 45 %) | ⬇ **−0.20 / −0.20** | the mountain's crowned, off-camber road. Front/rear split preserved |
| anti-roll `arb` | 5 / 6 (44 % / 56 %) | **5 / 6** | — | this car wants LESS roll — `arb_f` softer refuted twice. Springs carry the compliance, ARBs carry the roll |
| damping compression `dc` | 20 / 20 (0 % / 0 %) | **20 / 20** | — | ⛔ **already on the floor of the slider.** The circuit asks for soft compression and there is none left to give |
| damping expansion `de` | 46 / 44 (53 % / 47 %) | **50 / 44** (67 % / 47 %) | ⬆ **front only** | settle the front between the walls on the descent. **Rear held: `de_r` up was REFUTED 8 Sep** (44→52 lost throttle rotation and brought the rear brake lock back) |
| camber `cam` | 2.0 / 1.2 | **2.0 / 1.2** | — | camber is a ride-height lever here (2.8 mm/deg). The platform is being moved deliberately; do not move it twice |
| toe | 0.00 / +0.12 | **0.00 / +0.12** | — | `toe_f` 0.00 removed a front braking asymmetry on 3 Sep and that fix is holding |
| diff `lsd` i/a/b | 6 / 18 / 35 | **6 / 18 / 35** | — | `lsd_a` 18 is already inside the reference's 20–28 band and 14→20 is inside the instrument's floor. `lsd_b` 35 held — see the trigger below |
| downforce `df` | 410 / 635 (60 % / 68 %) | **410 / 635** | — | measured 4 Sep: this car's whole wing range is 3–6 % of aero load and moved nothing. Held, and named as a test the instrument probably cannot resolve here |
| gearbox | 3.022 / 2.450 / 1.972 / 1.598 / 1.285 / 1.030 `FEED` | **unchanged** | — | see below |
| top speed slider | 300 | **300** | — | |
| ECU | 96 | **≈94 — set to the readout** | ⬇ | to land ≤ 540 bhp |
| restrictor | 99 | **99** | — | |
| ballast / position | 45 / −29 | **55 / −29** | ⬆ **+10 kg** | to land ≥ 1285 kg |
| compound | RS / RS | **RS** for practice | — | race compound is a race-plan question, not settled here |
| brake balance `bb` | 0 | **0** | — | see the conflict below |

---

## The gearbox — held, and this is measured rather than assumed

**6th gear is already cut for Conrod.** `K6 = 36.004 km/h per 1000 rpm` (`FEED`, Daytona),
hard cut at 8,650–8,670 rpm ⇒ **6th tops out at ~311 km/h**. Observed maximum at Daytona was
**294.8 km/h**, so there is ~16 km/h of headroom, and Bathurst runs 10 bhp *less* with 10 kg
*more*. Conrod with a tow should arrive at The Chase near the top of 6th without sitting on
the limiter — which is precisely what `05-track-reference.md` §Mount Panorama asks for.
⇒ **do not touch 6th.**

⚠️ **1st and 2nd over the mountain are the open half, and they are `[UNMEASURED]`.** The
reference calls Bathurst gearing "a genuinely two-part problem". The Daytona box has never
been asked to cover six 1st-to-2nd-gear corners in a row. **Run the box as it stands, then
re-cut from `tools/shift_points.py` against the mountain frames.**

**Shift table issued** (`shift_points` id 5, keyed to `mount-panorama-circuit-full-course`):
performance **8,600 in 1 / 2 / 3**, fuel-saving **7,450 in 1 / 2 / 3**, **gears 4–6 silent**.

---

## The two conflicts, surfaced and not averaged

### 1. Brake balance — the track reference says forward, the car says never

`05-track-reference.md` §Mount Panorama: *"Brake bias: two to three clicks forward. The Chase
mandates it."*

**Refused, and the refusal is measured on this car and this driver.** His fronts already lock
past the ABS working point under braking — Turn 1 front slip minimum a **median 0.878**
against an RS working point of 0.92–0.935. Moving bias forward makes the axle that is already
failing fail earlier. ⚠️ On this car **`bb +1` is rearward**, so "forward" here means negative.

**Held at `bb` 0.** A generic circuit note does not outrank a measurement taken on this car
with this driver. ⭐ **His in-car trim is his to make — record it, never correct it.**

### 2. Rake versus clearance — the tension named in the axis register, and it dissolves

The register flagged these as pulling opposite ways. They do not: **rake is the difference
between the ends, clearance is the level of both.** Raising both by 6 mm buys the clearance
the crests need and leaves the 6 mm rake exactly where it was confirmed. In percent of range
the front/rear reading stays symmetric too (36 % / 33 %, against 12 % / 13 % before).
⇒ **Settled. Not a tension.**

---

## What this predicts, and what would falsify it

| prediction | falsified by |
|---|---|
| **The car survives Skyline and The Dipper without going light or bottoming.** Ride height +6 mm and springs −0.20 are aimed here. | sustained suspension-height excursions toward the observed minimum over the crests, or the driver reporting the car going light |
| **6th arrives at The Chase off the limiter, on the limiter only with a tow.** | rev-limiter frames in 6th on Conrod without a tow ⇒ 6th is too short and the box must be re-cut |
| **`lsd_b` 35 holds the rear under braking at The Chase.** Pre-loaded answer if not: `lsd_b` up. It killed rear brake lock at Daytona (0-in-5 at 40 against 2-in-15 at 35) but halved entry rotation — **a price worth paying at a 290 km/h downhill stop lined with wall, and not worth it at Daytona.** | rear slip below 0.90 under braking into The Chase on more than one lap in five |
| **The three gears that beep are the right three.** The mountain is 1st–3rd work. | the driver reporting the beep arriving late over the mountain ⇒ the 550→540 bhp change moved the crossover more than expected |

## What is silent, and says so

- **No map.** `lap_frames` carries no Bathurst lap, so the circuit cannot be drawn from his
  own driving. It can be, after the first run.
- **No corner model, no corner names the app may speak.** `data_health.py`: *"no corner
  observations — nothing to claim"*, *"corner model: none stored"*. Corner names in this file
  come from the league hub's `driverIntelligence` and are **his** vocabulary, not the app's.
- **No pit loss.** `tracks.pit_loss_secs` is NULL for Mount Panorama. The reference estimates
  28–30 s at medium-high confidence and it is an estimate. **Measure it.**
- **No tyre model, no wear rate, no stint length.** All of it needs laps. The race plan is a
  separate turn and it has nothing to stand on yet.

---

# Session 151 — 8 Sep 2026, 10 laps, first laps ever driven here

**Sheet as issued, `SCREEN`-confirmed. RS/RS. Best 2:03.003 on the last lap, still improving.**
⭐ **Gearbox `FEED`-verified unchanged** — 3.022 / 2.450 / 1.972 / 1.598 / 1.285 / 1.030.
**Rank zero is now fully closed on this circuit: 23 values by screen, the box by feed.**

Lap times: 2:06.3 · 2:16.3 · 2:11.8 · **2:03.7 · 2:03.4** · 2:04.1 · 2:04.1 · 2:04.2 · **2:03.0**
(lap 1 out-lap excluded). Sector 2 — the mountain — is now his **most repeatable** sector:
43.5 / 43.4 / 44.7 / 43.3 / 43.6 / 43.5 after 45.8 / 45.6 / 49.2 early.

## `[DRIVER REPORT]` — and the correction that changed the diagnosis

> *"felt good a little touchy across the top of the mountain through skyline"* …
> *"it's not light on skyline its very pointed which is good but almost too much,
> that could also be me getting used to car and track"*

⚠️ **The first reading of "touchy" was going-light. It was wrong, and he corrected it before
any analysis was done.** Had the correction not come, the compliance prediction would have
been scored as falsified and ride height would have moved for a symptom that does not exist.
**"Touchy" is not a symptom word in this driver's vocabulary — resolve it before using it.**

## Predictions from the initial sheet, checked

| prediction | outcome |
|---|---|
| car survives Skyline without going light or bottoming | **Not falsified, and not confirmed either.** He reports NOT light. The falsifier did not fire — which is weaker than a confirmation. Recorded as `unresolvable` on `rh_f`, direction up. |
| 6th arrives at The Chase off the limiter | **Held.** 282.5 km/h at 5,000 m in 6th, no tow, against a ~311 km/h limiter. Conrod tops out with room to spare. |
| `lsd_b` 35 holds the rear at The Chase | **Held.** Zero frames of rear slip below 0.90 anywhere in the braking zone. **`lsd_b` up stays holstered.** |
| the three gears that beep are the right three | **Held.** No report of a late beep; the mountain runs 2nd–4th. |

## What the mountain actually did — Skyline, 3,000–3,150 m

| lap | min speed | catching the back end | min suspension |
|---|---|---|---|
| 2 · 3 · 4 | 115.7 · 151.0 · 118.9 km/h | **26 · 42 · 17 frames** | 217 · 228 · 234 mm |
| 5 · 6 · 7 · 8 · 9 · 10 | 179.6 · 177.0 · 185.6 · 182.2 · 188.6 · 185.1 | **0 · 0 · 0 · 0 · 0 · 0** | 246–248 mm |

⭐ **He was right about himself.** Zero catches on six consecutive laps, roughly **60 km/h more
minimum speed**, and the lap-to-lap spread four times tighter (15.93 → 3.91 km/h). The early
suspension unloading is **downstream of being sideways**, not of the spring and ride-height
change — which is exactly why `rh_f` is recorded `unresolvable` rather than confirmed.

**And the car is inside its grip there:** front 0.9953 against rear 0.9947, neither axle above
1.00, 197 frames off both pedals. *"Almost too much"* is eagerness, not the car letting go.

## ⚠️ What he did NOT report — The Cutting

**The worst traction zone on the circuit, and it is not improving.** 56 % of on-power frames
spinning the rears (`DERIVED`, 646 frames, laps 5–10), by lap: 47 · 58 · 59 · 54 · 25 · **88 %**
— scattered, not converging, and worst on his fastest lap.

**It is a traction limit, not a differential question.** Rear left/right slip gap median
**0.0073** ⇒ both wheels together. ⛔ Do not reach for `lsd_a`: the wheel-speed split says
nothing about the diff on this car and it wrongly closed that axis for a week.

⭐ **AND IT DOES NOT BUY A SETUP CHANGE, because the car-wide number is normal.** Whole-lap
wheelspin 5.4 % here against Daytona's 7.0 / 5.8 / 5.5 %. The Cutting is a steep uphill 3rd-gear
full-throttle exit and this is what that costs. **A telemetry-only flag buys a question, not a
change** — so it is a question.

## The balance finding, and why it is NOT attributed

Mid-corner front/rear slip gap is **0.001–0.004 at every zone here** against roughly **0.011**
at Daytona, where the front slipped about twice the rear in all six setups tested. The car is
far more balanced mid-corner — consistent with *"very pointed"*.

⛔ **Not attributed to any one change.** Four things moved at once, by design, because it is a
new circuit: ride height, spring rate, front rebound, and the ballast shifting the balance
43:57 → 44:56. Any of them, or the circuit's own corners, could carry it. **Two candidates
worth naming for later:** front rebound 46 → 50 (front stays planted on turn-in) and the
forward ballast (more front load on a car whose chronic weakness is a front-limited middle).
**Ballast position remains one of 22 axes never tested on this car.**

## Decision — NO CHANGE

Ten laps at a brand-new circuit, still improving, the driver likes the car, the symptom he
raised is resolving on its own, and the one measurable defect is normal for the car. **Moving
anything now throws away the baseline and chases an adaptation curve.**
