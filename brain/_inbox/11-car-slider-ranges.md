# Car Slider Ranges — The Register

**What this is:** the recorded min/max of every per-car slider, read off each car's own settings screen in game. Once a car is in `range_records` (entered once on the app's **Car** screen), its limits are what every percent-of-range figure is taken against.

**Why it matters more than it looks.** GT7 derives each slider's endpoints from per-car chassis data — lever ratio, corner mass, suspension travel. Natural frequency, ride height, downforce and gearing limits differ between every car; many road cars cannot reach 3.50 Hz at all, some race cars exceed 5.00. A percent-of-range recommendation is only convertible into a number you can type once the range is known. Recording a car's ranges once removes the estimate from every sheet that car ever gets.

---

# 🟢 ALL FOUR CARS READ ON v1.71 — and the register is `range_records` (11 Sep 2026)

**The record is the database, not this file.** Every car's endpoints live in `data/pitcrew.db` `range_records`, entered once on the app's **Car** screen (`CLAUDE.md` §1a: the range record stayed). Nothing reads the JSON blocks below - they fed the retired HTML tool - so they are history, marked, and never updated again. The table here was checked against the database, read-only, on 11 Sep 2026.

**GT7 v1.71 (20 August 2026) said, in the official update notes, that adjustment ranges were revised for suspension, differential and aerodynamics. They were. Four cars have now been read on v1.71 (`range_records`, checked 11 Sep 2026) and the same five endpoints moved on all four.**

| Car | Status |
|---|---|
| **Porsche 911 RSR (991) '17** | ✅ v1.71, verified. Re-read 21 Aug; the record was updated 5 Sep and its `lsd_b` reads **0 – 100**, not the 21 Aug 99 - the one-click question §0.2 raised |
| **Porsche 911 GT3 R (992) '22** | ✅ v1.71, verified, 22 Aug 2026. New car — see §0.1 |
| **Lamborghini Huracán GT3 '15** | ✅ v1.71, verified, 24 Aug 2026 — see §0.2 |
| **Ford Shelby GT350R '16** | ✅ **v1.71, verified, 23 Aug 2026 — read, and never absorbed by this file** until the experiment ledger's contradiction S1 found it on 11 Sep |

**What the Shelby's v1.71 reading settles.** Its LSD reads **0 – 30 / 0 – 100 / 0 – 100**, the same as all three Gr.3 cars: the LSD ranges are **class-independent - outcome 1** of "What was unknown" below - and the rule to issue LSD in absolutes is **retired**. Damper expansion reads 30 – 60 on all four. **And on this road car two chassis-derived endpoints did move:** natural frequency is 2.00 – 4.00 Hz at both ends (1.88 – 3.70 / 2.00 – 3.90 on v1.70) and front downforce 50 – 150 (60 – 160); ride height and rear downforce held. So PD's "aerodynamics" meant endpoints on the Shelby, not only initial settings. **`game_version` is recorded on all four records.**

## §0.2 ⭐ The Huracán — the class comparison, and it reproduces on all five

**Read 24 Aug 2026 by the driver, filed in `data/pitcrew.db` stamped v1.71, verified.** This is the reading `§0.1` asked for and the worksheet's first checkbox.

| Parameter | Huracán v1.70 | RSR, 21 Aug | 992, 22 Aug | **Huracán, 24 Aug** |
|---|---|---|---|---|
| LSD initial torque | 5 – 60 | 0 – 30 | 0 – 30 | **0 – 30** ✅ |
| LSD acceleration | 5 – 60 | 0 – 100 | 0 – 100 | **0 – 100** ✅ |
| LSD braking | 5 – 60 | 0 – **99** | 0 – **100** | **0 – 100** ✅ |
| Damper expansion F | 30 – 50 | 30 – 60 | 30 – 60 | **30 – 60** ✅ |
| Damper expansion R | 30 – 50 | 30 – 60 | 30 – 60 | **30 – 60** ✅ |

**Every other endpoint is unchanged from its v1.70 reading**, which is itself worth recording: the patch moved five cells and left the other seventeen alone, on the only car in the register that has a before-and-after on the same chassis.

**Three consequences.**

1. **The change is at least Gr.3-wide, and it is a version effect, not a car effect.** Three cars, two manufacturers, two drivetrain layouts (RR and MR), one class — the same five endpoints, the same values. This is the first reading with a genuine *before* column on the same car, so it also rules out the possibility that the RSR's "v1.70" figures (borrowed from this very car) were wrong to begin with.
2. **`lsd_b` is 0 – 100 and the RSR's 99 is the odd reading.** §0.1 flagged this as a cell wanting a second look. Two cars now read 100 against the RSR's 99. ~~Re-read the RSR's LSD braking ceiling~~ **Closed: the RSR's record, updated 5 Sep 2026, reads 0 – 100** - the 21 Aug 99 was the one-click misread.
3. **Percent-of-range reasoning is restored for this car**, and the standing instruction to express LSD in absolutes no longer applies to the Huracán. It no longer applies to the Shelby either: its v1.71 reading (23 Aug) carries the same three scales.

> **Answered 11 Sep 2026, from `range_records`: fleet-wide on every car read - the Shelby's v1.71 LSD is 0 – 30 / 0 – 100 / 0 – 100.** The question as it stood on 24 Aug: **Gr.3-wide, or fleet-wide? The Shelby is now the only test left.** A Gr.N road car whose other endpoints differ wildly (ride height 75–160, NF 1.88–3.70, downforce 60–160) and which still reads the old 5–60 LSD. **If it re-reads as 0–30 / 0–100 / 0–100, the change is fleet-wide.** Five minutes.

### ⚠️ What the re-read does to sheets already written against the old scale

**Nothing was clamped** — all three of Rev D's LSD values and both damper-expansion values still sit inside the new endpoints, so `setups/2026-08-17-huracan-watkins-glen-long-revD.md` parses without loss. **But what they mean as a fraction of range has moved, and on one axis it moved a long way:**

| Rev D value | % of v1.70 range | **% of v1.71 range** | |
|---|---:|---:|---|
| `lsd_i` 6 | 2 % | **20 %** | ⚠️ **the ceiling halved (60 → 30).** The one axis where the physical meaning most plausibly moved with it |
| `lsd_a` 18 | 24 % | **18 %** | |
| `lsd_b` 28 | 42 % | **28 %** | |
| `de_f` 42 | 60 % | **40 %** | rebound headroom above it that did not exist before |
| `de_r` 36 | 30 % | **20 %** | |

**Any published figure quoted as an absolute LSD number is now ambiguous** until its game version is known — including `05-track-reference.md`'s per-circuit "LSD acceleration sensitivity" bands, every one of which was written against 5 – 60. On the new scale those numbers are not merely stale, they address a different slider.

**Full measurement write-up, with the telemetry that came from the same session: `17-v1.71-measured-results.md` §6.**

## §0.1 ⭐ The 992 GT3 R — a new car, and it settles half of `17` §6's open question

**Read 22 Aug 2026, filed in `data/pitcrew.db` stamped v1.71, verified.** This is the first reading this car has ever had; there is no v1.70 column for it and there never will be.

**It reproduces the RSR's v1.71 register on 20 of 22 parameters, including all five moved endpoints:**

| Parameter | v1.70 (Huracán / Shelby) | RSR, 21 Aug | **992 GT3 R, 22 Aug** |
|---|---|---|---|
| LSD initial torque | 5 – 60 | 0 – 30 | **0 – 30** ✅ |
| LSD acceleration | 5 – 60 | 0 – 100 | **0 – 100** ✅ |
| LSD braking | 5 – 60 | 0 – 99 | **0 – 100** ⚠️ |
| Damper expansion F | 30 – 50 | 30 – 60 | **30 – 60** ✅ |
| Damper expansion R | 30 – 50 | 30 – 60 | **30 – 60** ✅ |

**`17` §6 closed with an explicit caveat and this addresses it.** That caveat was that the RSR's "v1.70 column" had been borrowed from the Huracán, so the comparison rested on the assumption that two Gr.3 cars shared endpoints. **A second Gr.3 car, different manufacturer, read a day later, reproducing all five — makes the version the cause rather than the car.**

**Status: [MEASURED — two cars, in house]. The LSD and damper-expansion changes are not car-specific.**

> **Answered 11 Sep 2026 - fleet-wide (see the top).** As it stood: **Gr.3-wide, or fleet-wide?** Both cars read so far are Gr.3. **The Shelby decides it** — a road car whose other endpoints differ wildly (ride height 75–160, NF 1.88–3.70, downforce 60–160) and which still reads the old 5–60 LSD. **If it re-reads as 0–30 / 0–100 / 0–100, the change is fleet-wide. Five minutes.**

### ⚠️ Two cells on the 992 that want a second look

| Cell | 992 reads | Every other car in the register | |
|---|---|---|---|
| **`top` (max speed setting)** | **150 – 450** | **200 – 800** — all three, including the Shelby | **The only cell in the whole register that breaks pattern.** 200–800 looks universal rather than per-car. Unused so far, so it costs nothing to re-check — but it poisons every gearbox calculation on this car if it is wrong. |
| **`lsd_b`** | 0 – **100** | RSR read 0 – **99** on 21 Aug | **Closed 5 Sep 2026:** the RSR's record reads 0 – 100, so the 99 was the one-click misread. |

**First sheet issued against this register: `setups/2026-08-22-992-gt3r-spa-24h.md`** — and its 20 values parsed with **0 clamped**, which is an independent confirmation that the recorded endpoints admit the values written against them.

## ⭐ What moved on the RSR

| Parameter | v1.70 | **v1.71** | Change |
|---|---|---|---|
| **LSD initial torque** | 5 – 60 | **0 – 30** | floor to 0, **ceiling halved** |
| **LSD acceleration sensitivity** | 5 – 60 | **0 – 100** | floor to 0, ceiling +40 |
| **LSD braking sensitivity** | 5 – 60 | **0 – 99** | floor to 0, ceiling +39 |
| **Damper expansion — front** | 30 – 50 | **30 – 60** | ceiling +10 |
| **Damper expansion — rear** | 30 – 50 | **30 – 60** | ceiling +10 |

**The other seventeen endpoints did not move.** Ride height, natural frequency, ARB, damper compression, camber, toe, downforce, brake balance, maximum speed and final gear all read exactly as they did on v1.70.

**This is a much narrower change than the patch notes implied.** PD named suspension, differential and aerodynamics; on this car the diff moved a great deal, one suspension parameter moved a little, and **aerodynamics did not move at all** despite the notes calling out race cars specifically.

## ⭐ The 0/0/0 report is confirmed — and the bigger half was not reported at all

The community report carried in `16` §5 was **[COMMUNITY — single source]**: one GTPlanet player saying the Fully Customisable Diff could now be set to 0/0/0. **It is now [MEASURED — IN HOUSE]. All three LSD parameters floor at 0.**

**But the part nobody reported is the part that matters more: the three LSD axes no longer share a scale.**

On v1.70 all three ran **5–60**. They now run **0–30**, **0–100** and **0–99**. Three parameters that were interchangeable in proportional terms are now three different rulers.

> ### 🔴 This is the percent-of-range trap, for the third time, and this time it is worse
>
> This file has already caught the same failure mode twice — the natural-frequency heuristic on the RSR and the ride-height heuristic on the Shelby. Both were rules that changed meaning when transported across a class boundary. **This one changes meaning without going anywhere at all.**
>
> **Worked example, on the sheet you are actually racing.** Rev B's RSR diff reads **initial 5 / acceleration 14 / braking 24**:
>
> | | v1.70 (5–60) | **v1.71** | Range now |
> |---|---|---|---|
> | Initial torque **5** | 0 % of range | **16.7 %** | 0–30 |
> | Acceleration **14** | 16.4 % | **14.0 %** | 0–100 |
> | Braking **24** | 34.5 % | **24.2 %** | 0–99 |
>
> **The absolute values are untouched and the car drives as built** — Job 0 confirmed that, and the telemetry confirmed it independently (gear ratios byte-identical, `17` §1). **What changed is every proportional statement ever made about them.** Initial torque at 5 used to be *sitting on the floor*; it is now a sixth of the way up.
>
> **Rule, 21 Aug: issue LSD in absolute values only, on every car, until all three are re-read. ⭐ RETIRED 11 Sep 2026:** all four cars read on v1.71 carry the same three scales in `range_records` (0 – 30 / 0 – 100 / 0 – 100), so a percent of range means one thing again. And when they are re-read, record the three ranges separately rather than as one "LSD 5–60" line — that shorthand is what made this invisible.

## ✅ What was unknown - answered 11 Sep 2026: outcome 1, class-independent (the Shelby reads 0 – 30 / 0 – 100 / 0 – 100)

**Whether the new LSD ranges are class-independent.**

The register's strongest structural result is that most endpoints are identical across cars and classes — LSD 5–60 was **confirmed on three cars across two classes**, one of the most solid entries in the file. **That entry is now half-dead: confirmed changed on one Gr.3 car, unknown on the other two.**

Three outcomes, and they are not equally likely:

1. **All three cars now read 0–30 / 0–100 / 0–100** (the RSR's 99 re-read as 100 on 5 Sep) → the parameter stays class-independent and the register absorbs the change cleanly. **Most likely, on the evidence of everything else in this file.**
2. **The two Gr.3 cars match but the Shelby differs** → LSD ranges have become class-derived, which would be a new structural fact and would move three parameters from the class-independent column to the chassis-derived one.
3. **All three differ** → LSD ranges are now per-car, like ride height. This would be the biggest structural change the register has ever recorded.

**Ten minutes on the other two cars settles it.** Do the Huracán first — it is the same class, so it separates outcome 1 from outcomes 2 and 3 immediately.

---

## 📋 The re-read worksheet

**Done — all four cars are read on v1.71, in `range_records`.**

- [x] **Porsche 911 RSR (991) '17** — Gr.3, MR — ✅ done 21 Aug 2026
- [x] **Lamborghini Huracán GT3 '15** — Gr.3, MR — ✅ **done 24 Aug 2026. Reproduced all five. See §0.2.**
- [x] **Ford Shelby GT350R '16** — Gr.N, FR road car — ✅ **read 23 Aug 2026 on v1.71, verified; this file found out on 11 Sep. Outcome 1.**

**On the remaining two, read all 22 parameters** — not just the five that moved on the RSR. A parameter that held on a Gr.3 car may not hold on a road car, and the whole point of the register is that it does not guess.

**Three additions to the procedure, all still outstanding:**

1. **⭐ Record the step size while the screen is open.** Five seconds per slider. **Now five sessions overdue**, and it was not captured on the RSR re-read either. It is the only thing standing between every click count in every sheet being an instruction rather than an estimate.
2. **⭐ Note the new defaults, not just the endpoints.** 1.71 revised initial settings as well as ranges. The default is a free datapoint about where PD think the car should sit.
3. **⭐ Record the game version in the app.** `game_version` was **NULL** on all three range records on 21 Aug; **it is recorded on all four now (checked 11 Sep 2026).** **The 21 Aug reading is only distinguishable from a v1.70 reading by its date.** That is Standing Rule 10 not being enforced by the tool, and it is now the highest-priority Pit Crew defect.

---

## How a car gets added

1. In game, open the car's settings sheet. For each parameter, drag the slider to each end and read the number.
2. On the app's **Car** screen, pick the car, enter them, mark them as read off this car's own sheet, and save. They go into `range_records` in `pitcrew.db`, and every prompt and export reads them from there.
3. Nothing is copied into this file: **the database is the register.** Add the car to the status table at the top, with its version.

Takes about five minutes per car. **It now needs doing again after every physics-tagged patch — 1.71 proved that in writing and then in measurement.**

**Record the whole set, not the interesting half.** A partial entry blanks the parameters it omits, which drops them out of the brief entirely.

---

## ⭐ The structural finding — class-independent vs chassis-derived

**Established on v1.70 across three cars and two classes. Partially re-tested on v1.71.**

| **Class-independent — identical on all three cars, across Gr.3 and Gr.N** | **Chassis-derived — different on every car, and the spans differ enormously** |
|---|---|
| ARB F/R 1–10 · damper compression F/R 20–40 % · **damper expansion F/R** · camber F/R 0.0–6.0 ° · toe F/R −1.00…+1.00 ° · **LSD initial / acceleration / braking** · brake balance −5…+5 · maximum speed 200–800 km/h · final gear 2.000–5.000 | **ride height** front and rear · **natural frequency** front and rear · **downforce** front and rear |
| **16 sliders** | **6 sliders** |

> **⚠️ Arithmetic correction, 21 Aug 2026.** Earlier revisions of this file described the split as **"13 of 22 class-independent, 9 chassis-derived"** and that phrasing is repeated in `07` and `08`. Counting the sliders individually as the register lists them gives **16 and 6**. The structural claim is unaffected — it is the count that was wrong, not the finding — but the "9 chassis-derived endpoints" phrasing should be read as **6** wherever it appears.

**Of the 16 class-independent sliders, five have now moved on v1.71** — the three LSD axes and both damper expansion sliders — **and they moved identically on all four cars read** (11 Sep, `range_records`) - so "class-independent" survived v1.71 for them.

**The 6 chassis-derived sliders did not move on the RSR at all** - nor on the Huracán or the 992. **On the Shelby two of them did** (natural frequency to 2.00 – 4.00 Hz, front downforce to 50 – 150; 11 Sep, `range_records`): chassis-derived is per-car in its patch behaviour too.

### The rule this produces, and it has now been broken in three ways

| Parameter | Express targets as | Because | Caught on |
|---|---|---|---|
| **Natural frequency** | **absolute Hz** | Floors range from 2.00 Hz (Shelby on v1.71; 1.88 on v1.70) to 3.00 Hz (Gr.3). A percent-of-range target puts a Gr.3 car at 4.4–4.6 Hz — a full 1.0 Hz stiffer than it has ever raced well on. | RSR, 11 Aug |
| **Ride height** | **percent of range** (or mm scaled to the span) | Spans range from 25 mm (Gr.3 front) to 85 mm (Shelby, both ends) — a **3.4× difference**. `08` B1's "3–5 clicks above minimum" means 20 % of range on a Gr.3 car and **6 %** on the Shelby. | **Shelby, 16 Aug** |
| **Toe, camber** | **absolute degrees** | Range is class-independent, and percent hides how small the useful steps are — 5 % of toe range is 0.10°, twice the smallest change worth making. | RSR, 11 Aug |
| **Downforce** | **absolute points, plus the front-share percentage** | Spans vary by class more than anything else on the sheet (Gr.3 total 850–1150; Shelby total 200–450 on v1.71, 210–460 on v1.70). | Shelby, 13 Aug |
| **⭐ LSD, all three axes** | **percent of range again, from 11 Sep 2026** (absolutes 21 Aug – 11 Sep) | The three axes ran a shared 5–60 scale for the life of this register and now run **0–30, 0–100 and 0–100** - on all four cars read, so the scale is class-independent again. A proportional statement made before 20 August still addresses a different slider. | **RSR, 21 Aug; retired on all four, 11 Sep** |

> **The general lesson, now in three parts.** A heuristic must declare **(a)** whether it is absolute or proportional, **(b)** which version of the game its range was read on, and **(c)** — the new one — **it must not share a range statement across parameters that merely happen to agree.** "LSD 5–60" was a convenience that bundled three independent sliders into one fact. When they diverged, the bundle hid it.

---

## The register

### ✅ Porsche 911 RSR (991) '17 — Gr.3, MR — **v1.71**

**Recorded 2026-08-21 · GT7 v1.71 · read off the car's own settings screen · superseded by the record's 5 Sep 2026 update, which reads LSD braking 0 – 100 - `range_records` is current, and this table keeps the 21 Aug reading**

**Changed rows are marked. Everything unmarked read identically to the v1.70 block below it.**

| Parameter | Min | Max | Span | vs v1.70 |
|---|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | 25 mm | same |
| Ride height — rear | 60 mm | 90 mm | 30 mm | same |
| Natural frequency — front | 3.00 Hz | 5.00 Hz | 2.00 Hz | same |
| Natural frequency — rear | 3.00 Hz | 5.00 Hz | 2.00 Hz | same |
| Anti-roll bar — front | 1 | 10 | universal | same |
| Anti-roll bar — rear | 1 | 10 | universal | same |
| Damper compression — front | 20 % | 40 % | universal | same |
| Damper compression — rear | 20 % | 40 % | universal | same |
| **Damper expansion — front** | **30 %** | **60 %** | **30** | ⭐ **max 50 → 60** |
| **Damper expansion — rear** | **30 %** | **60 %** | **30** | ⭐ **max 50 → 60** |
| Camber — front | 0.0 ° | 6.0 ° | 6.0 ° | same |
| Camber — rear | 0.0 ° | 6.0 ° | 6.0 ° | same |
| Toe — front | −1.00 ° | +1.00 ° | 2.00 ° | same |
| Toe — rear | −1.00 ° | +1.00 ° | 2.00 ° | same |
| **LSD initial torque** | **0** | **30** | **30** | ⭐ **5–60 → 0–30** |
| **LSD acceleration sensitivity** | **0** | **100** | **100** | ⭐ **5–60 → 0–100** |
| **LSD braking sensitivity** | **0** | **99** | **99** | ⭐ **5–60 → 0–99** (5 Sep record: 0 – 100) |
| Downforce — front | 350 | 450 | 100 | same |
| Downforce — rear | 500 | 700 | 200 | same |
| Brake balance | −5 | +5 | universal | same |
| Maximum speed (auto-set) | 200 km/h | 800 km/h | generator span | same |
| Final gear | 2.000 | 5.000 | 3.000 | same |

*History only - nothing reads this block; the record is `range_records`, entered on the app's Car screen (11 Sep 2026).*

```json
{
 "Porsche 911 RSR (991) '17": {
  "date": "2026-08-21", "version": "1.71", "cat": "Gr.3", "verified": true,
  "note": "v1.71 re-read. LSD all three axes and damper expansion moved; 17 endpoints unchanged. Step sizes still not recorded.",
  "r": {
   "rh_f": [55, 80], "rh_r": [60, 90],
   "nf_f": [3, 5], "nf_r": [3, 5],
   "arb_f": [1, 10], "arb_r": [1, 10],
   "dc_f": [20, 40], "dc_r": [20, 40],
   "de_f": [30, 60], "de_r": [30, 60],
   "cam_f": [0, 6], "cam_r": [0, 6],
   "toe_f": [-1, 1], "toe_r": [-1, 1],
   "lsd_i": [0, 30], "lsd_a": [0, 100], "lsd_b": [0, 99],
   "df_f": [350, 450], "df_r": [500, 700],
   "bb": [-5, 5], "top": [200, 800], "fg": [2, 5]
  }
 }
}
```

#### What this measurement changed

**1. ⭐ A genuinely open differential is buildable for the first time.** All three axes floor at 0. `08` A4 calls LSD braking sensitivity *"your entire off-throttle and on-brake rear-stability toolkit"* — that toolkit just gained territory at the end this driver uses least. **An open-on-overrun diff would be a larger rotation source than anything else in the rear-stability stack**, and nobody in the community has explored it because it did not exist eight days ago.

**2. ⭐ Acceleration sensitivity gained 40 points of ceiling at the exact moment the case for running it low got weaker.** `17` §1 measured driven-wheel slip under power down **40–60 %** on this car. The whole argument for low accel lock is protecting progressive exit traction against wheelspin — **there is much less wheelspin to protect against, and the range now runs to 100.** Both facts point the same way. The measured value of 14 was established on v1.70 against the old torque map and is now the least reliable number on the sheet. **This is the highest-value single-slider test available.**

**3. Initial torque's ceiling halved, which is the one that constrains rather than frees.** 5–60 → 0–30. Anything above 30 on an old published tune is no longer expressible. Not a problem for this programme — `08` B1 runs initial at 5–8 and calls high preload *"a silent cause of the persistent mid-corner push you hate"* — but it invalidates a chunk of the community's back catalogue outright.

**4. Damper expansion gained 10 points of ceiling and lost nothing.** 30–50 → 30–60. The baseline runs **40 front / 38 rear**, which was 50 % / 40 % of the old range and is now **33 % / 27 %**. **The sheet is proportionally softer in rebound than it reads**, and the stiff end of rebound is now unexplored. Note that `08` A4 wants rear expansion *lower* for lift-off stability, so the new headroom is at the end this car has least use for — the opposite of the LSD result.

**5. Aerodynamics did not move, despite the patch notes naming race cars specifically.** Front 350–450, rear 500–700, unchanged. **Either PD's "race cars" meant a different subset, or the revision was to initial settings rather than endpoints on this car.** Worth confirming on the Huracán before treating Gr.3 aero ranges as settled.

**6. Ride height and natural frequency did not move**, so the RSR's front NF of 3.05 Hz still sits five clicks off a 3.00 floor. **The cheapest clamp detector on the car reads clean**, which is the independent confirmation of Job 0.

#### What still isn't known for this car

**Step sizes — still not recorded, and the settings screen was open on 21 August.** Five sessions overdue. Every click count in every RSR sheet remains an estimate.

**New defaults not recorded.** 1.71 revised initial settings; what PD now think this car should sit at was not written down.

**`game_version` was NULL in the database** on this very record on 21 Aug. **Recorded since (checked 11 Sep 2026).**

---

### 🔴 Porsche 911 RSR (991) '17 — Gr.3, MR — **v1.70, superseded**

**Recorded 2026-08-11 · GT7 v1.70 · kept as the comparison record. Do not issue.**

*History only - nothing reads this block; the record is `range_records`, entered on the app's Car screen (11 Sep 2026).*

```json
{
 "Porsche 911 RSR (991) '17 [v1.70 ARCHIVE]": {
  "date": "2026-08-11", "version": "1.70", "cat": "Gr.3", "verified": false,
  "note": "SUPERSEDED by the 2026-08-21 v1.71 re-read. Historical record only.",
  "r": {
   "rh_f": [55, 80], "rh_r": [60, 90],
   "nf_f": [3, 5], "nf_r": [3, 5],
   "arb_f": [1, 10], "arb_r": [1, 10],
   "dc_f": [20, 40], "dc_r": [20, 40],
   "de_f": [30, 50], "de_r": [30, 50],
   "cam_f": [0, 6], "cam_r": [0, 6],
   "toe_f": [-1, 1], "toe_r": [-1, 1],
   "lsd_i": [5, 60], "lsd_a": [5, 60], "lsd_b": [5, 60],
   "df_f": [350, 450], "df_r": [500, 700],
   "bb": [-5, 5], "top": [200, 800], "fg": [2, 5]
  }
 }
}
```

**The five findings this v1.70 reading produced still stand, because four of them are about parameters that did not move:**

**1. The 70–80 % natural-frequency heuristic is wrong on this car.** On a 3.00–5.00 Hz range that is **4.40–4.60 Hz** — the top of the racing-tyre band and stiffer than any Gr.3 setup has business being. **Anchor natural frequency in absolute Hz**, roughly 3.9–4.2 Hz front with the rear a click or two above. **Range unchanged on v1.71, so this finding carries over intact.**

**2. Toe is ±1.00°, not ±0.50°.** `02` §3.6 understates it by a factor of two. **Issue toe in absolute degrees.** **Range unchanged on v1.71.**

**3. Front downforce is nearly fixed; the rear is the whole aero lever.** Front spans 100 points, rear 200. Balance window **33.3 % front** to **47.4 % front**. Total 850–1150 matches the published Gr.3 figure of ≈1150. **Range unchanged on v1.71 — and this is the finding that was most expected to move.**

**4. The car has +5 mm of rake built into its own minimums.** Quote rake as *rear-minus-front in mm*. **Range unchanged on v1.71.**

**5. Camber tops out at 6.0°, not 10.0°**, so 1.2° is 20 % of range. **Range unchanged on v1.71.**

**6. ⚠️ The "four universal claims confirmed" note is the one that did not survive.** It recorded ARB 1–10, LSD 5–60, brake balance −5…+5 and the damper windows as matching `02`'s predictions. **LSD and damper expansion have both since moved.** ARB and brake balance held.

---

### 🔴 Lamborghini Huracán GT3 '15 — Gr.3, MR — **v1.70, superseded**

**Recorded 2026-08-13 · GT7 v1.70 · superseded by the 24 Aug v1.71 reading (§0.2) · kept as the comparison record**

**On v1.70 this car's ranges were identical to the RSR's on all 22 parameters.** That was the register's strongest result. **It is now a hypothesis again** — and testing it is the single most informative five minutes left in this file, because it separates "LSD ranges are class-independent" from "LSD ranges are now per-car."

| Parameter | Min | Max | Span |
|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | 25 mm |
| Ride height — rear | 60 mm | 90 mm | 30 mm |
| Natural frequency — front | 3.00 Hz | 5.00 Hz | 2.00 Hz |
| Natural frequency — rear | 3.00 Hz | 5.00 Hz | 2.00 Hz |
| Anti-roll bar — front | 1 | 10 | universal |
| Anti-roll bar — rear | 1 | 10 | universal |
| Damper compression — front | 20 % | 40 % | universal |
| Damper compression — rear | 20 % | 40 % | universal |
| Damper expansion — front | 30 % | 50 % | ⚠️ **RSR now reads 30–60** |
| Damper expansion — rear | 30 % | 50 % | ⚠️ **RSR now reads 30–60** |
| Camber — front | 0.0 ° | 6.0 ° | 6.0 ° |
| Camber — rear | 0.0 ° | 6.0 ° | 6.0 ° |
| Toe — front | −1.00 ° | +1.00 ° | 2.00 ° |
| Toe — rear | −1.00 ° | +1.00 ° | 2.00 ° |
| LSD initial torque | 5 | 60 | ⚠️ **RSR now reads 0–30** |
| LSD acceleration sensitivity | 5 | 60 | ⚠️ **RSR now reads 0–100** |
| LSD braking sensitivity | 5 | 60 | ⚠️ **RSR now reads 0–99** |
| Downforce — front | 350 | 450 | 100 |
| Downforce — rear | 500 | 700 | 200 |
| Brake balance | −5 | +5 | universal |
| Maximum speed (auto-set) | 200 km/h | 800 km/h | generator span |
| Final gear | 2.000 | 5.000 | 3.000 |

*History only - nothing reads this block; the record is `range_records`, entered on the app's Car screen (11 Sep 2026).*

```json
{
 "Lamborghini Huracán GT3 '15": {
  "date": "2026-08-13", "version": "1.70", "cat": "Gr.3", "verified": false,
  "note": "STALE — v1.70 reading. The RSR's v1.71 re-read moved 5 endpoints. Re-read required before any sheet.",
  "r": {
   "rh_f": [55, 80], "rh_r": [60, 90],
   "nf_f": [3, 5], "nf_r": [3, 5],
   "arb_f": [1, 10], "arb_r": [1, 10],
   "dc_f": [20, 40], "dc_r": [20, 40],
   "de_f": [30, 50], "de_r": [30, 50],
   "cam_f": [0, 6], "cam_r": [0, 6],
   "toe_f": [-1, 1], "toe_r": [-1, 1],
   "lsd_i": [5, 60], "lsd_a": [5, 60], "lsd_b": [5, 60],
   "df_f": [350, 450], "df_r": [500, 700],
   "bb": [-5, 5], "top": [200, 800], "fg": [2, 5]
  }
 }
}
```

#### What this measurement changed

**The Huracán's ranges were identical to the RSR's — every endpoint, all 22 parameters.** That confirmed the hypothesis this file was built to test, and produced four consequences:

1. **3.00–5.00 Hz, 55–80 / 60–90 mm ride height, 350–450 / 500–700 downforce and ±1.00° toe as Gr.3 class defaults.** **On v1.71 the RSR still reads all four of these identically, so this survives — for the RSR.**
2. **⚠️ Two cars is a pattern, not a proof.** Both MR Gr.3 from the same era. An FR Gr.3 car would stress it properly.
3. **The RSR's findings apply verbatim** — absolute Hz, absolute degrees.
4. **The +5 mm built-in rake applies here too.** The Laguna sheet's "+8 mm rake" and Watkins Glen's "+9 mm" are only +3 and +4 mm of *added* rake.

> **⚠️ 21 Aug 2026 — and the diff numbers on every Huracán sheet are now doubly exposed.** Rev D runs **LSD 6 / 18 / 28**. If this car's ranges moved as the RSR's did, those sit at **20 % / 18 % / 28 %** of the new ranges rather than **1.8 % / 23.6 % / 41.8 %** of the old ones. **The car will drive as built — but do not reason proportionally about that diff until the ranges are read.**

#### What still isn't known for this car

**Step sizes.** Click counts on both sheets assume GT7's usual increments.

**Gearing constant K is still assumed at ≈1045 rather than measured.** One reading in top gear closes it. **⚠️ And `17` §2 measured the RSR's top speed down 3.9 km/h on v1.71, outside the whole pre-patch range — so K on this car needs measuring on v1.71 regardless of what it read before.**

---

### 🔴 Ford Shelby GT350R '16 — Gr.N, FR road car — **v1.70, superseded**

**Recorded 2026-08-13, filed 16 Aug · GT7 v1.70 · superseded by the 23 Aug v1.71 reading (`range_records`, verified): natural frequency 2.00 – 4.00 Hz both ends, front downforce 50 – 150, damper expansion 30 – 60, LSD 0 – 30 / 0 – 100 / 0 – 100; every other endpoint as below · kept as the comparison record**

**This was the class-independence test, and it came back outcome 1** (the top of this file). If this car's LSD also read 0–30 / 0–100 / 0–99, the parameter stays class-independent and the register absorbs 1.71 cleanly. If it reads anything else, three sliders move from the class-independent column to the chassis-derived one and the 16/6 split becomes 13/9.

| Parameter | Min | Max | Span | vs Gr.3 (v1.70) |
|---|---|---|---|---|
| **Ride height — front** | **75 mm** | **160 mm** | **85 mm** | **3.4× the span** |
| **Ride height — rear** | **95 mm** | **180 mm** | **85 mm** | **2.8× the span** |
| **Natural frequency — front** | **1.88 Hz** | **3.70 Hz** | **1.82 Hz** | **floor 1.12 Hz softer** |
| **Natural frequency — rear** | **2.00 Hz** | **3.90 Hz** | **1.90 Hz** | **floor 1.00 Hz softer** |
| Anti-roll bar — front | 1 | 10 | universal | same ✅ |
| Anti-roll bar — rear | 1 | 10 | universal | same ✅ |
| Damper compression — front | 20 % | 40 % | universal | same ✅ |
| Damper compression — rear | 20 % | 40 % | universal | same ✅ |
| Damper expansion — front | 30 % | 50 % | universal | ⚠️ **RSR now 30–60** |
| Damper expansion — rear | 30 % | 50 % | universal | ⚠️ **RSR now 30–60** |
| Camber — front | 0.0 ° | 6.0 ° | 6.0 ° | same ✅ |
| Camber — rear | 0.0 ° | 6.0 ° | 6.0 ° | same ✅ |
| Toe — front | −1.00 ° | +1.00 ° | 2.00 ° | same ✅ |
| Toe — rear | −1.00 ° | +1.00 ° | 2.00 ° | same ✅ |
| LSD initial torque | 5 | 60 | universal | ⚠️ **RSR now 0–30** |
| LSD acceleration sensitivity | 5 | 60 | universal | ⚠️ **RSR now 0–100** |
| LSD braking sensitivity | 5 | 60 | universal | ⚠️ **RSR now 0–99** |
| **Downforce — front** | **60** | **160** | **100** | **same span, 290 lower** |
| **Downforce — rear** | **150** | **300** | **150** | **narrower, 350 lower** |
| Brake balance | −5 | +5 | universal | same ✅ |
| Maximum speed (auto-set) | 200 km/h | 800 km/h | generator span | same ✅ |
| Final gear | 2.000 | 5.000 | 3.000 | same ✅ |

*History only - nothing reads this block; the record is `range_records`, entered on the app's Car screen (11 Sep 2026).*

```json
{
 "Ford Shelby GT350R '16": {
  "date": "2026-08-13", "version": "1.70", "cat": "Gr.N", "verified": false,
  "note": "STALE — v1.70 reading. The RSR's v1.71 re-read moved 5 endpoints. This car is the class-independence test.",
  "r": {
   "rh_f": [75, 160], "rh_r": [95, 180],
   "nf_f": [1.88, 3.7], "nf_r": [2, 3.9],
   "arb_f": [1, 10], "arb_r": [1, 10],
   "dc_f": [20, 40], "dc_r": [20, 40],
   "de_f": [30, 50], "de_r": [30, 50],
   "cam_f": [0, 6], "cam_r": [0, 6],
   "toe_f": [-1, 1], "toe_r": [-1, 1],
   "lsd_i": [5, 60], "lsd_a": [5, 60], "lsd_b": [5, 60],
   "df_f": [60, 160], "df_r": [150, 300],
   "bb": [-5, 5], "top": [200, 800], "fg": [2, 5]
  }
 }
}
```

#### What this measurement changed

**1. ⭐ It split the register into class-independent and chassis-derived parameters.** 16 of 22 endpoints identical to both Gr.3 cars; only ride height, natural frequency and downforce differ. **A first sheet for any new car can be issued in absolute numbers for those 16 on day one, whatever the class** — subject now to the v1.71 re-read.

**2. ⭐ It caught a broken heuristic in `08` B1, and the break is the mirror image of the RSR's.** B1 states ride height in **absolute clicks**. Written against 25 / 30 mm Gr.3 spans, 5 clicks is **20 % of range**; on this car's 85 mm spans the identical instruction produces **6 %**.

> The rule silently changed meaning by more than 3× crossing from Gr.3 to Gr.N. It put three consecutive Yas Marina sheets on 80 / 98 mm while the driver spun four times in fifteen race laps and struck kerbs at 8 of 10 corners. **Rewrite B1's ride-height line as percent of range.** Tested on `setups/2026-08-16-shelby-yas-marina-revC.md` at 89 / 107 mm (16.5 % / 14.1 %).

**3. The natural-frequency floor was 1.88 / 2.00 Hz on v1.70 (2.00 / 2.00 on v1.71)** — a full Hz softer than any Gr.3 car reaches. This car has run 3.05 / 3.20 Hz on all three sheets, **64 % / 63 % of its v1.70 range**, materially stiff for a heavy road car on aggressive kerbs. `01` §11 records that stiffening it at Sainte-Croix cost grip over bumps and worsened throttle exit. **There is a great deal of unused softness and none of it has been tried.**

**4. +20 mm of rake is built into the minimums** (75 / 95), against +5 mm on the Gr.3 cars — so every Yas Marina sheet's "+18 mm rake" is in fact **−2 mm of added rake.**

**5. Downforce is a different animal — total 210 to 460 points**, against Gr.3's 850–1150. Balance window **20.0 %** to **51.6 %** front. Front downforce is a *large* lever here, not the ±50-point trim it is on a Gr.3 car. **⚠️ The RSR's aero ranges did not move on v1.71 despite the notes naming race cars. If this road car's aero also holds, the aero line in the patch notes refers to initial settings rather than endpoints — a useful structural finding, free with the re-read.**

**6. ⚠️ "Camber, toe, dampers, ARB, LSD and brake balance confirmed for a third time across two classes" is now partly overtaken.** Camber, toe, damper compression, ARB and brake balance held on the RSR's v1.71 read. **LSD and damper expansion did not.**

#### What still isn't known for this car

**Step sizes** — five sessions overdue.

**Gearing constant K is closed for this car** — the one thing here the other two lack. **K = 1,096 ± 1 %**, measured twice independently (1,101 on 13 Aug from a limiter strike; 1,091 on 16 Aug from a non-limiter point in 6th). **⚠️ 21 Aug: `17` §2 measured the RSR's terminal speed down 1.4 % on v1.71, below the floor of twenty pre-patch sessions. K is a v1.70 constant like everything else here — re-close it on the next Shelby session.**

---

## Key map

The short keys in the JSON, in tool order.

| Key | Parameter | Unit | Per-car? |
|---|---|---|---|
| `rh_f` / `rh_r` | Ride height front / rear | mm | **yes — and the SPAN varies 3.4×, so target in percent of range.** Unchanged on v1.71 (RSR) |
| `nf_f` / `nf_r` | Natural frequency front / rear | Hz | **yes — and the FLOOR varies 1 Hz, so target in absolute Hz.** Unchanged on v1.71 on the three Gr.3 cars; **moved on the Shelby (2.00 – 4.00)** |
| `arb_f` / `arb_r` | Anti-roll bar front / rear | index | no — 1–10, confirmed ×3, two classes. **Held on v1.71** |
| `dc_f` / `dc_r` | Damper compression front / rear | % (damping ratio) | no — 20–40, confirmed ×3. **Held on v1.71** |
| `de_f` / `de_r` | Damper expansion front / rear | % (damping ratio) | ⭐ **MOVED on v1.71: 30–50 → 30–60, the same on all four cars read** |
| `cam_f` / `cam_r` | Camber front / rear | degrees | no — 0.0–6.0 confirmed ×3. **Held on v1.71.** Issue in absolute degrees |
| `toe_f` / `toe_r` | Toe front / rear | degrees, signed | no — ±1.00 confirmed ×3. **Held on v1.71.** Issue in absolute degrees, never percent |
| `lsd_i` | LSD initial torque | index | ⭐ **MOVED: 5–60 → 0–30 on all four** |
| `lsd_a` | LSD acceleration sensitivity | index | ⭐ **MOVED: 5–60 → 0–100 on all four** |
| `lsd_b` | LSD braking sensitivity | index | ⭐ **MOVED: 5–60 → 0–100 on all four** (the RSR's 21 Aug "99" reads 100 in its 5 Sep record) |
| `awd` | Front/rear torque distribution | % front | **yes**, AWD only |
| `df_f` / `df_r` | Downforce front / rear | points | **yes — varies enormously by class.** **Unchanged on v1.71 on the three Gr.3 cars; the Shelby's front moved (50 – 150)** |
| `bb` | Brake balance | integer | no — −5 to +5, confirmed ×3. **Held on v1.71** |
| `top` | Maximum speed (auto-set) | km/h | no — 200–800 confirmed ×3. **Held on v1.71.** Generator, not a trim |
| `fg` | Final gear | ratio | no — 2.000–5.000 confirmed ×3. **Held on v1.71** |
| `version` | **The game version the reading was taken on** | string | **Mandatory (Standing Rule 10). A range without a version is not a measurement.** **Recorded on all four records (checked 11 Sep 2026)** |

> **⭐ Do not write the three LSD axes as a single "LSD 5–60" line ever again.** They agreed for the life of this register and diverged on 20 August, and the shorthand is what made the divergence invisible.

---

## Priority order for measuring

1. ✅ **Done 24 Aug - re-read the Huracán on v1.71.** **The class comparison** — it separates "LSD ranges are class-independent" from "per-car" in one reading, and it unblocks every Huracán sheet including Rev D.
2. ✅ **Done 23 Aug - re-read the Shelby on v1.71** (outcome 1; two of its chassis-derived endpoints moved). **The class-independence test**, and it also settles whether the aero-range line in the patch notes means endpoints or initial settings.
3. **Step sizes on any car whose screen is open.** Free. **Five sessions overdue and missed again on the 21 Aug RSR read.**
4. **New defaults**, on all three. 1.71 revised initial settings and none have been recorded.
5. **A third Gr.3 car — ideally FR, not MR.** The Mustang Gr.3 or the M6. Two identical MR Gr.3 cars is suggestive; a matching FR car would confirm the 6 chassis-derived endpoints are a Gr.3 constant rather than an MR-Gr.3 one. **More interesting on v1.71, because the steering-geometry rework was explicitly per car.**
6. **A second road car**, to promote or complicate the 16/6 split.
7. Anything the league calendar forces next.

For a car raced once, generic windows plus a flag on anything near a limit is enough. Recording pays off on the cars that come back.

---

## What to re-check after a patch

**Standing Rule 11, and 1.71 has now validated it twice — once in the patch notes and once in measurement.**

> **After any physics-tagged update, re-read the register in full — every recorded car, all 22 parameters — before any sheet is issued.** Read the patch notes for the words "adjustment range" first; if they appear, the re-read is mandatory rather than precautionary.

**Two lessons specific to how 1.71 actually landed:**

- **The patch notes over-described the change.** Three categories were named; on the RSR, one moved a lot, one moved slightly, and **aerodynamics did not move at all**. **Read the notes to decide whether to measure, never to decide what the numbers are.**
- **The notes also under-described it.** Nothing in them said the three LSD axes would stop sharing a scale, and that is the change with the widest blast radius across this knowledge base. **The measurement found something the documentation did not contain — which is the entire argument for keeping this register.**

**And record the version on every entry (Standing Rule 10).** A range without a version is not a measurement, because there is no way to know when it stopped being true. **It was failing in the tool on 21 Aug; all four records carry it now (checked 11 Sep 2026).**

Related: `17-v1.71-measured-results.md` §6 for the full write-up of the 21 Aug reading, `16-update-1.71-physics-change.md` §6 for the 1.71 case, `02-gt7-setup-parameters.md` §3.0 for how the endpoints are derived, and `09-setup-sheet-format.md` for why every per-car value is issued as percent-of-range plus clicks plus absolute.
