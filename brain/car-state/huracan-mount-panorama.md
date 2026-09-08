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

## Rank zero — nothing here is `SCREEN` yet

**Issued 8 Sep 2026, before a single lap has been driven at this circuit.** Every row below
is `ISSUED`. The sheet does not become fact until a settings-screen screenshot comes back.

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
