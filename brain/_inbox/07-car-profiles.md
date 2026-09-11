# GT7 Car Engineering Profiles — Porsche 911 RSR (991) '17, Lamborghini Huracán GT3 '15, and the "Shelby GT3500" Question

**Compiled:** August 2026 · **Game version context:** the body of this document was written against **GT7 v1.70 (June 2026)**. Physics baseline was post-1.49 (July 2024), with further handling drift through 1.66.

**Last updated:** 21 Aug 2026 — **1.71 banner added below.** Prior update 10 Aug 2026: two **driver-validated in-game results** added to the Huracán profile — LSD acceleration (§3.6.1) and the first post-1.49 tyre wear measurement for any car in this document (§3.3.1). Everything else remains sourced research or flagged inference.

---

# 🟠 1.71 BANNER — THE CARS MAY HAVE MOVED, AND THEY MAY HAVE MOVED DIFFERENTLY FROM EACH OTHER

**GT7 v1.71 (20 August 2026) states, in the official notes:**

> *"The steering geometry **for each car** has been optimised, improving the simulation of turning forces."*

**"For each car" is the phrase that matters for this document.** This is a per-car change applied across the roster, which means the three cars profiled here **may have moved differently from one another** — and this file's most valuable content is precisely the *comparisons* between them (§6). A per-car geometry rework can reorder a comparison table without changing any car's spec sheet.

1.71 also reworked the tyre model's slipping regime, changed damper attenuation, revised the defaults *and adjustment ranges* of suspension, differential and aerodynamics, recalculated Performance Points fleet-wide, adjusted both driving assists, and reset every ranking board in the game. Full changelog: `16-update-1.71-physics-change.md`.

## What is void, what is intact

| Content | Status | Note |
|---|---|---|
| **§0.1 the RSR is MR, not RR** | ✅ **Intact and important** | A drivetrain layout is a matter of record — GT7's own car description says so. **The single most load-bearing correction in this file is unaffected.** |
| **§0.2 / §4 the Shelby disambiguation** | ✅ **Intact** | Which cars exist is not a physics claim. |
| **Specifications** (power, weight, displacement, dimensions) | ✅ **Intact** — except PP | Spec sheets do not patch. |
| **All PP figures** (RSR 720.74, Huracán 738.66, Mustang Gr.3 716.44, Shelby 575.47) | ⚠️ **Void** | PP was recalculated fleet-wide. **Read the current number off each car — `16` §12 Job 4.** |
| **§1 physics context** | ⚠️ **Superseded in part** | The post-1.49 characterisations are history. 1.71 sits on top of them. See the addendum below. |
| **§2.2 / §3.2 / §5.2 handling character** | ⚠️ **Pre-1.71 observations** | Per-car steering geometry was reworked. Re-establish on the first outing using `08` F2's four diagnostic questions. |
| **§2.3 / §3.3 tyre wear character** | ⚠️ **Void as numbers** | Both the 2019 GT Sport rankings *and* the in-house v1.70 measurement predate the new tyre model. |
| **§3.3.1 the Laguna wear measurement** | ⚠️ **Historical** | 11–12 laps at 2× on RS. Still the correct *method* and a valid control for comparison. **May no longer describe the game.** |
| **§3.6.1 the accel-14 validation** | ⚠️ **Re-test required** | 1.71 introduced a new engine torque control map, and the diff's range was revised. **The reasoning survives; the number does not.** See below. |
| **§3.1 verified slider ranges** | ⚠️ **Void** | Read off the car on v1.70. 1.71 revised adjustment ranges in writing. `11-car-slider-ranges.md` is the authority and is being re-read. |
| **§2.7 / §3.7 / §5.7 baseline setups** | ⚠️ **Starting points only, and now on unverified ranges** | The 2022 sheets were already three physics generations stale; they are now four. |
| **§6 comparative section** | ⚠️ **The most exposed part of the document** | Per-car geometry rework can reorder comparisons. §6.3's trail-braking ranking depends on mass distribution (intact) *and* on how each car converts brake pressure into yaw (reworked). |
| **§7 data gaps** | ⚠️ **Several reopened** | See the addendum at §7. |

## The three things to re-test first, in order

1. **Huracán LSD acceleration sensitivity.** §3.6.1's finding — that 14 beats the MR baseline of 15 and beats the track norm of 20–28 on a restricted build — is **an argument about torque *shape*, and 1.71 changed how torque is delivered.** The three transferable conclusions all survive; the value 14 needs re-establishing. **And if the diff floor really did drop from 5 to 0 (`16` §5), the useful territory extends below anywhere we have looked.**
2. **Camber on both Gr.3 cars.** §2.7 flags the 2022 tunes' −3.0° as a pre-1.49 max-grip choice, and the modern baseline as −1.0 to −2.0°. **1.71 reworked the exact model that made heavy camber expensive in GT7.** If the penalty softened, the modern baseline is now over-conservative. `16` §12 Job 5, ten minutes.
3. **Which car actually suits the driver now.** §6.3 ranks the RSR first for a heavy trail-braker, on mass distribution plus low polar moment plus 1.49's brake-bias sensitivity. **Mass distribution and polar moment are intact; the other two terms moved** — 1.71 adjusted ABS slip-ratio control and cornering brake behaviour, which is the trail-braking phase directly. **The ranking is a hypothesis again.**

## One thing 1.71 makes *better* for this programme

§5.2 records that the Mustang Gr.3 is **absent from every major Gr.3 recommendation list, with no BoP data and no published tune**, and concludes: *"in a no-BoP open-tuning league, that is arguably an advantage."*

**Post-1.71 the entire community tuning record is stale, so the gap between a documented car and an undocumented one has narrowed to nearly nothing.** For the next few weeks everyone is tuning an undocumented car. It would also supply the **FR Gr.3 data point** `11-car-slider-ranges.md` has wanted since 13 August, which is the test that decides whether the nine chassis-derived slider endpoints are a Gr.3 constant or merely an MR-Gr.3 one.

---

## 0. Two corrections to flag before anything else

### 0.1 The 911 RSR is NOT an RR car

The brief describes the Porsche 911 RSR (991) '17 as "Gr.3, rear-engined RR layout." **This is incorrect, both in reality and in GT7.**

The 2017 991-generation RSR is the first 911 in history to use a **mid-engine layout** — Porsche moved the 4.0-litre flat-six forward of the rear axle line to permit a much larger rear diffuser. [GTDB lists the GT7 car explicitly as **MR**](https://gtdb.io/gt7/car/911-rsr-991-17/), describing it as "the first in 911 history to feature a mid-engine layout." Coach Dave Academy's 2026 Gr.3 tier list also [categorises it under **MR cars**](https://coachdaveacademy.com/tutorials/best-gr-3-cars-in-gran-turismo-7/).

This matters enormously for setup work: **you should not be tuning this car with RR assumptions.** An RR-derived LSD baseline (high braking sensitivity to stop the rear stepping out on entry), heavy front toe-out to fight entry understeer, and a big rearward weight-transfer allowance are all the wrong starting point. The RSR wants an MR playbook.

Caveat: it retains a rearward static bias — a single GT7 settings screenshot posted to GTPlanet shows **46:54 front:rear** ([K2P, March 2022](https://www.gtplanet.net/forum/threads/looking-for-a-good-base-setup-for-the-911rsr-991-17.405427/)). That is rearward, but it is normal MR territory, not RR (an RR 911 road car sits nearer 38:62). Treat this figure as single-source and unverified against current BoP.

**⭐ This correction is entirely unaffected by 1.71, and it is worth saying so explicitly: it is the highest-value single line in this document and it does not need re-checking.**

Unverified: several search results referenced a "Porsche 911 GT3 R" setup guide for GT7. I could not confirm whether GT7 contains a 911 GT3 R as a separate Gr.3 entry alongside the RSR. Worth checking in-game.

### 0.2 "Shelby GT3500" does not exist

There is no such car. See §4 for the full disambiguation — the short version is that the name appears to be a collision of "GT350" and "GT500," and the driver's actual third car is the **Ford Shelby GT350R '16**.

---

## 1. Physics context: what post-1.49 means for these cars

The July 2024 update 1.49 replaced GT7's car physics simulation model. Per [DG-EDGE's breakdown](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424):

- **Tyre degradation became far more punishing.** There is "a significant drop in performance" as tyres wear, making tyre management materially more important than pre-1.49.
- **Both understeer and oversteer sensitivity increased.** The car responds more sharply to steering input; entry mistakes now cascade into the acceleration phase rather than being absorbed.
- **Brake bias changes have a much more noticeable effect on stability.** Brake balance moved from a fine-trim tool to a primary balance lever. Directly relevant to a load-cell trail-braker.
- **FFB strength was reduced overall**, with some cars needing roughly +60% on the FFB setting to restore previous feel.

Subsequent updates continued the trend. Coach Dave Academy's 2026 tier list states that **"MR cars have become much easier to drive on this update"** with "massively improved stability," and that in their testing **MR cars now edge FR cars overall.** FR cars are characterised as "safer to drive" and better in the wet.

**Implication:** two of the driver's three cars (Porsche, Lamborghini) are MR and sit on the favoured side of the current physics. The Mustang Gr.3 / Shelby are FR.

> **⚠️ Calibration warning added 10 Aug 2026.** The "1.49 made degradation far more punishing" claim is well-sourced and directionally right, but it has repeatedly been used in this knowledge base to justify **pessimistic absolute wear estimates**, and the first in-house measurement (§3.3.1) came in **~1.8× better than the model predicted.** "Degradation is more punishing than it was" is not the same claim as "tyres will not last." Do not let the former generate the latter.

### ⭐ 1.0 Addendum, 21 Aug 2026 — what 1.71 adds on top

Every bullet above is now **history rather than current state**. 1.71's own list, from the official notes:

- **Tyre algorithm updated, focusing on the simulation when tyres are slipping**; rolling resistance optimised; **tyre heating and wear values adjusted**; off-track grip loss on "Real" adjusted.
- **Steering geometry optimised for each car**, improving the simulation of turning forces.
- **Damper attenuation characteristics changed** to make stance changes and road-surface tracking feel more natural.
- **TCS intervention behaviour optimised**; **ABS slip-ratio control and cornering brake behaviour adjusted**.
- **Steering wheel force feedback and understeer vibration adjusted**; Fanatec Auto Setup parameters optimised.

**Four consequences for this document specifically:**

1. **The "MR cars now edge FR cars" verdict is a 2026-pre-1.71 assessment and is now a hypothesis.** It came from the 1.49-lineage stability gains. A per-car geometry rework is exactly the kind of change that reshuffles a layout-level ranking. **Two of the three cars here are MR and the conclusion favours them — which is a reason to check it rather than to keep leaning on it.**
2. **The "brake bias is now a primary lever" point survives, but what a click does has changed.** 1.71 adjusted ABS cornering brake behaviour — the trail-braking phase by name.
3. **The FFB note now has a 1.71 twin, and it is a diagnostic trap.** 1.49 reduced FFB strength; 1.71 adjusted FFB and understeer vibration and changed Fanatec Auto Setup parameters. **On an 18 Nm DD Extreme, an FFB change reads as a grip change.** Confirm the wheel settings before diagnosing any car's character — `08` B3 and F1 step 0.
4. **The 10 Aug calibration warning above is now doubly binding.** It cautions against letting "degradation is more punishing" generate "tyres will not last." **Post-1.71 nobody knows which direction degradation moved at all** — so the warning applies to pessimism *and* optimism equally. Measure (`16` §12 Job 2) before characterising any car's wear.

### 1.1 What you can actually adjust under BoP

Per [GTPlanet's BoP discussion](https://www.gtplanet.net/forum/threads/bop-and-upgrades-tuning.428202/):

- **BoP On / Settings Disabled:** everything is locked. No setup work is possible at all.
- **BoP On / Settings Partially Allowed:** the game builds a temporary setting sheet using only the parts the car *originally shipped with*, all at default values. **Only stock-equipped adjustable parts can be touched.**

So the setup sheets below apply to **lobbies, custom races, and time trial** — which is what this league runs (no BoP, open tuning). In BoP-locked Dailies the levers reduce to: tyre compound, brake balance via MFD, fuel map, TCS, and driving technique.

> **⭐ 21 Aug — note the interaction with 1.71 that is easy to miss.** BoP-partial mode builds its temporary sheet from **default values**, and **1.71 revised the initial (default) suspension, differential and aero settings.** So in any BoP-partial context, the car you get handed is a different car than it was last week, before you touch anything. Not directly relevant to this league's open-tuning rounds, but relevant to any Daily Race practice used as a reference.

---

## 2. Car Profile — Porsche 911 RSR (991) '17 (Gr.3)

### 2.1 Specifications

| Parameter | Value | Source |
|---|---|---|
| Category | Gr.3 / Racing Car | [GTDB](https://gtdb.io/gt7/car/911-rsr-991-17/) |
| Drivetrain | **MR** (mid-engine, RWD) | GTDB |
| Engine | 4.0 L (4,000 cc) flat-six, mounted ahead of rear axle | GTDB |
| Aspiration | Naturally aspirated | GTDB |
| Stock power | 509 BHP @ 8,100 rpm | GTDB |
| Stock weight | 1,243 kg | GTDB |
| PP (stock) | 720.74 — ⚠️ **v1.70; PP recalculated fleet-wide in 1.71** | GTDB |
| Price | Cr. 450,000, Brand Central | GTDB |
| Weight distribution | **46:54 F:R** — single source, unverified | [GTPlanet K2P, Mar 2022](https://www.gtplanet.net/forum/threads/looking-for-a-good-base-setup-for-the-911rsr-991-17.405427/) |
| BoP power/weight | **498 hp / 1,280 kg** — ⚠️ **March 2022 data, pre-1.49, almost certainly superseded** | [GTPlanet Gr.3 BoP thread](https://www.gtplanet.net/forum/threads/group-3-bop-list-and-discussion.405641/) |

⚠️ **BoP figures are stale.** The only community-compiled Gr.3 BoP table dates to March 2022. The current authoritative source is [gt-engine.com's Gr.3 spec page](https://gt-engine.com/gt7/cars/gr3/gr3-01-specs.html), which blocks automated fetching — **read the current numbers off that page or off the in-game BoP screen directly.**

**⭐ Note: this league runs no BoP, so the BoP row is context rather than a constraint. The PP row is the one that matters, and it is the one 1.71 moved.**

### 2.2 Fundamental handling character

**⚠️ A pre-1.71 characterisation. Per-car steering geometry was reworked — re-establish on the first outing.**

**What it does well.** Coach Dave Academy (2026) rates it as *"one of the best all rounder cars in GT7 thanks to the latest update,"* citing *"the stability you now get in MR cars coupled with the usual Porsche strengths under braking and cornering,"* and notes it has *"very few weaknesses."* SoloX credits *"its grip and nimbleness."*

**What it does badly.** Straight-line speed. A GTPlanet contributor summarised it as a car that *"lacks in straight line speed"* but excels in the corners. The 4.0 NA flat-six is the smallest-displacement engine of the three cars here and it shows on long straights. **⚠️ 1.71 optimised rolling resistance, which moves terminal speed — the deficit may be a different size now.**

**The specific failure mode.** The same GTPlanet thread notes it *"needs good throttle control."* My engineering read — flagged as **reasoning, not a citation** — is that this is classic MR mid-corner-to-exit behaviour rather than an RR snap. With 54% of the mass behind the driver and a NA engine that delivers its torque high in the rev range, the failure is a **progressive power-oversteer rotation on exit** if the throttle is applied before the car is straightening. It is not the vicious pendulum snap of a genuine RR car.

The practical consequence: **the RSR punishes throttle timing, not lift timing.** A driver expecting RR lift-off snap will be defending against the wrong thing.

> **⭐ This reasoning rests on mass distribution and torque-curve shape.** Mass distribution is intact. **Torque-curve shape is not — 1.71 introduced a new engine torque control map.** The conclusion is likely to survive, since a high-revving NA flat-six is still a high-revving NA flat-six, but the *severity* of the throttle-timing penalty is a fresh question.

### 2.3 Tyre wear character

The best data available is **GT Sport-era and heavily caveated** ([GTPlanet Gr.3 MR tyre wear test](https://www.gtplanet.net/forum/threads/gr-3-mr-cars-tire-wear-test.384914/), 2019; Lago Maggiore GP, 8 laps, 10× wear, Racing Hard):

- The RSR showed **balanced front-to-rear wear**, with minimal grip loss. *"A very decent car"* that *"remained stable even at lap 8."*
- Ranked **4th least affected** of the MR Gr.3 field — behind only the McLaren 650S GT3 and Alfa Romeo 4C, and comfortably better than the Ferrari 458 and Lamborghini Huracán.

⚠️ 2019 data from a different game with a different tyre model. **Treat the ranking as directional character, not as numbers.** **⭐ And it is now three tyre models ago: GT Sport → 1.49 → 1.71.**

**Stint length: no reliable public GT7 data exists**, because building the dataset would require *"2-3x the race length"* of testing per car-track-compound combination. **Measure it — see §3.3.1 for how badly the estimates can miss.**

**Reasoning, not data:** with balanced wear and a 46:54 bias, the RSR's limiting corner on a typical clockwise circuit will be the **front-left** rather than a rear, which is unusual for an MR car and consistent with it being described as balanced. Verify with a tyre readout run.

### 2.4 Braking and trail-braking

This is the RSR's headline strength. Coach Dave's 2026 assessment calls out *"the usual Porsche strengths under braking and cornering."* Mid-engine mass concentration plus a rearward bias gives strong stability under heavy braking — the rear axle carries useful load into the braking zone rather than going light, which is exactly the condition a heavy trail-braker wants.

**⭐ The mass-distribution half of that argument is intact. The other half — how the car behaves under ABS while turning — is exactly what 1.71 adjusted.**

**Brake balance starting point.** The one full GT7 setup found for this car used **−3** ([K2P, GTPlanet, March 2022](https://www.gtplanet.net/forum/threads/looking-for-a-good-base-setup-for-the-911rsr-991-17.405427/)). ⚠️ Pre-1.49, from a self-described inexperienced tuner, and 1.49 made brake bias substantially more sensitive. **Start at 0.**

⚠️ **Sign convention.** The playbook (`08-playbook-leon.md` §B3) resolves the GT7 brake-balance sign as **negative = more FRONT bias, positive = more REAR bias**, verified across three independent sources. On that convention K2P's −3 is **front-biased**. Read direction from the playbook, not from older notes. **⭐ The sign convention is unaffected by 1.71.**

### 2.5 Aero character

**Low-drag-limited, cornering-biased.** Observed downforce settings from two independent GT7 tunes:

- **425 front / 575 rear** — [Kavo Gaming "max grip" circuit tune](https://kavogaming.com/porsche-911-rsr-best-circuit-grip-tune-gran-turismo-7/) (April 2022, mod. Nov 2024)
- **430 front / 590 rear** — K2P, GTPlanet (March 2022)

⚠️ Full adjustable downforce range unverified for this car. **⭐ Not true as of 11 Aug 2026 — `11-car-slider-ranges.md` measured it at front 350–450 / rear 500–700. But 1.71 revised aero adjustment ranges on race cars, so it is unverified again.**

**Circuits that suit it:** cornering-heavy precision circuits — Lago Maggiore, Dragon Trail Gardens, Autopolis, Suzuka, Brands Hatch. **Circuits that punish it:** Monza, Le Mans, Sardegna, Circuit de la Sarthe, Tokyo Expressway.

Context: [Occam's Racer's GT7 aerodynamics analysis](https://occamsracers.com/2024/04/19/gt7-aerodynamics/) argues GT7's aero model is comparatively crude and concludes aerodynamics are "virtually meaningless" relative to real racing. Take that as a caution against over-investing in downforce trimming versus mechanical grip work.

### 2.6 Setup levers that matter most

**Reasoning, flagged**, built on the sourced character above:

1. **Brake balance (and its in-race migration).** Post-1.49 this is the most sensitive stability control on the car. **⚠️ And 1.71 adjusted ABS cornering brake behaviour — re-establish the reference.**
2. **LSD braking sensitivity.** For an MR car this is the corner-entry stability control. Flux89's MR baseline is **20**, versus 25 for RR. Both GT7 tunes found for this car use **50**, which is a max-grip lobby choice, not a trail-braker's choice. **⚠️ Baselines assume a 5–60 range; 1.71 revised the diff range and it may now floor at 0 (`16` §5).**
3. **Rear downforce / rake balance.** Governs the top-speed-versus-rotation trade.
4. **Rear ARB and rear natural frequency.** The direct handles on exit-phase rotation, the car's actual failure mode.
5. **Gearing.** Because the car is straight-line-limited, final drive selection to protect the most important corner exit is worth more here than on a car with power in hand. **⚠️ Rolling resistance changed — re-gear.**

### 2.7 Baseline setup — medium-downforce circuit

⚠️ **Both available sheets are March–April 2022 and PRE-1.49 — now four physics generations stale.** Use as structural starting points only.

| Setting | Kavo Gaming (Apr 2022) | K2P / GTPlanet (Mar 2022) | Flux89 modern baseline (v1.2) |
|---|---|---|---|
| Ride height F/R | 60 / 70 | 60 / 70 | F: 3–5 clicks above min; R: 5–8 above min |
| Natural frequency F/R | 3.50 / 3.50 | 3.50 / 3.50 | Racing: 70–80% of slider; rear ≥ front |
| ARB F/R | 5 / 5 | 5 / 5 | F 4–6, R 3–6 |
| Damper compression F/R | 32 / 32 | 30 / 30 | 30 / 30 |
| Damper expansion F/R | 40 / 40 | 40 / 40 | 40 / 40; must exceed compression |
| Camber F/R | −3.0 / −3.0 | −3.0 / −3.0 | F −1.5 to −2.0, R −1.0 to −1.5 |
| Toe F/R | 0.20 / 0.00 | 0.10 out / 0.20 in | F 0.00, R +0.05 |
| LSD initial | 15 | 15 | MR: 5 |
| LSD accel | 40 | 40 | MR: 15 |
| LSD braking | 50 | 50 | MR: 20 |
| Downforce F/R | 425 / 575 | 430 / 590 | — |
| Brake balance | not specified | −3 | Start at 0 |
| Final drive | 3.800 | — | — |

Note the very large divergence between the 2022 lobby tunes and the modern baseline on **camber** (−3.0 vs −1.5/−2.0) and **LSD** (15/40/50 vs 5/15/20). My reading is that 1.49's tyre model changes made heavy static camber and heavy diff lock more costly, and that the 2022 numbers reflect a max-grip, tyre-wear-indifferent qualifying philosophy. **Start from the modern MR baseline and add locking/camber only as the car demonstrates it needs it** — and note §3.6.1, where even the modern MR baseline proved too much lock on a restricted build.

> **⭐⭐ 21 Aug — and this is the most interesting open question in the file.** That reading attributes the 2022-vs-modern camber divergence to **1.49's tyre model** making heavy camber costly. **1.71 reworked per-car steering geometry — the other half of the mechanism that makes camber expensive in GT7.**
>
> **So one of two things is true, and a ten-minute A/B distinguishes them:** either the camber penalty is a tyre-model property and survives, in which case the modern baseline stands; or it was substantially a geometry-model artefact, in which case **the 2022 tunes' −3.0° may be closer to right than anything issued since.** `16` §12 Job 5. **Nobody should be issuing a camber value on either of the Gr.3 cars until that test is run.**

**⚠️ Note also that the ride-height and natural-frequency rows are stated as percent-of-range or clicks-above-minimum, and 1.71 revised the ranges. `11-car-slider-ranges.md` must be re-read before either can be converted into a number.**

### 2.8 GT7-specific quirks and BoP history

- **The MR reclassification is the biggest quirk.** See §0.1. **Unaffected by 1.71.**
- **Post-1.49 it got materially better.** Pre-1.49 rankings that placed it mid-pack should be discounted. **⚠️ And post-1.71 nobody knows where it sits — the MR-edges-FR verdict is a hypothesis again (§1.0).**
- **BoP history is poorly documented publicly.** *"There is no way to see the BOP settings for a car unless you buy it."*

---

## 3. Car Profile — Lamborghini Huracán GT3 '15 (Gr.3)

**This is the best-documented car in this knowledge base, because it is the only one with in-house measured data — and as of 21 Aug 2026 that data is one game version behind, which makes it the car most urgently in need of a session.** It is also the car that won on 17 August and the one `16` §12 Jobs 2, 3 and 5 are all written around.

### 3.1 Specifications

| Parameter | Value | Source |
|---|---|---|
| Category | Gr.3 / Racing Car | [GTDB](https://gtdb.io/gt7/car/huracan-gt3-15/) |
| Drivetrain | **MR** (mid-rear engine, RWD) | GTDB |
| Engine | 5.2 L (5,204 cc) V10, longitudinal mid-rear | GTDB |
| Aspiration | Naturally aspirated | GTDB |
| Stock power | 576 BHP @ 8,000 rpm | GTDB |
| Stock torque | 59.2 kgfm @ 6,500 rpm | GTDB |
| Stock weight | 1,230 kg | GTDB |
| PP (stock) | 738.66 — ⚠️ **v1.70; recalculated in 1.71** | GTDB |
| Dimensions | 4,458 × 2,050 × 1,130 mm | GTDB |
| Weight distribution | **Not found.** Real Huracán GT3 is approx. 42:58 rearward — ⚠️ **not verified for GT7** | — |
| BoP power/weight | **484 hp / 1,275 kg** — ⚠️ **March 2022, pre-1.49, superseded** | [GTPlanet Gr.3 BoP thread](https://www.gtplanet.net/forum/threads/group-3-bop-list-and-discussion.405641/) |

**Slider ranges — ⚠️ VOID ON v1.71.** Read in-game on v1.70 (driver-supplied, 10 Aug 2026), open-tuning build:

| Slider | Range (v1.70 — unverified on 1.71) |
|---|---|
| Body height, front | 55–80 mm |
| Body height, rear | 60–90 mm |
| Natural frequency | 3.00–5.00 Hz |
| Downforce, front | 350–450 |
| Downforce, rear | 500–700 |

**1.71 states that initial suspension, differential and aerodynamic settings *and their adjustment ranges* were revised. All five rows above are unverified.** The full 22-parameter record and the re-read worksheet live in `11-car-slider-ranges.md`; that file is the authority and this table is a summary of it. *(The remaining ranges — ARB, damper, LSD, toe, camber, gearing — were closed there on 13 Aug and are likewise now unverified.)*

### 3.2 Fundamental handling character

**What it does well.** SoloX credits *"good performance and braking efficiency"* enabling deep corner entries, and ranks it **3rd** in their best-Gr.3 list. The high stock PP (738.66 vs the Porsche's 720.74) reflects a genuinely potent package — the 5.2 V10 gives it real straight-line ability the Porsche lacks.

**Its two real failure modes, in the order you will meet them:**

**1. Power-on mid-corner understeer from lap 1, if the acceleration diff is set conventionally.** ✅ **Confirmed in-house on v1.70.** See §3.6.1. It presents as "the car won't rotate," it is present cold and hot, and it is trivially fixable — but it will be misdiagnosed as a front-grip problem by anyone who doesn't ask which pedal is down.

**2. Stint-scale rear tyre degradation.** *(Sourced, GT Sport-era)* Rear tyres degrade more than fronts and the car became *"almost… undrivable"* after lap 6 in the 2019 test. ⚠️ **See §3.3.1 — the in-house measurement is far kinder than this reputation implies, and the reputation should be downgraded accordingly.**

*(Reasoning, flagged)* The Huracán carries a large, heavy V10 mounted longitudinally, set well rearward and relatively high. That gives a higher polar moment of inertia than the compact flat-six RSR: **once yaw starts, it develops with more momentum and is harder to arrest.**

> **⭐ Polar moment is a mass-distribution property and is the least version-exposed claim in this profile. It survives 1.71 unchanged, and it is therefore the right thing to reason from while everything else is being re-established.**

⚠️ **Neither Coach Dave Academy's 2026 tier list nor the GTPlanet "Best Gr.3 car?" thread discusses the Huracán at all.** Coach Dave explicitly excluded "niche track-specialists." Its absence from a 2026 all-rounder list, while the RSR is praised in the same list, is itself a signal — **though note that a wear reputation built on 2019 data may be a large part of why it is dismissed.** **⭐ And on 17 August 2026 this car won a race from P5, which is a more relevant datapoint than any tier list.**

### 3.3 Tyre wear character — the reputation, and the measurement that partly contradicts it

**The reputation.** From the [GTPlanet MR wear test](https://www.gtplanet.net/forum/threads/gr-3-mr-cars-tire-wear-test.384914/) (Lago Maggiore GP, 8 laps, 10× wear, Racing Hard):

- *"At lap 5, the tires feel really bad… At lap 6, the car almost feels undrivable."*
- **Rear tyres degraded more than fronts** — clearly rear-axle-limited.
- Ranked **2nd worst of the entire MR Gr.3 field**, behind only the Ferrari 458 Italia GT3.
- The RSR in the same test was stable through lap 8 with balanced wear.

⚠️ **This is 2019 GT Sport data at 10× on Hards.** It has been treated in this knowledge base as if it were current and absolute. It is neither.

### 3.3.1 ✅ [MEASURED — IN HOUSE] Racing Soft, 2×, Laguna Seca · 10 Aug 2026

**The first post-1.49 tyre wear measurement for any car in this document.**
**⚠️ 21 Aug 2026: a v1.70 measurement. Historical, and still the correct method. It may no longer describe the game.**

| | |
|---|---|
| Build | 525 bhp / 1300 kg, restrictor 70, ECU 97, 70 kg ballast @ −25 |
| Circuit | WeatherTech Raceway Laguna Seca (3.6 km, 55 m elevation) |
| Compound | **Racing Soft** — the *softest* available |
| Multiplier | **2× tyre wear** |
| Conditions | **Race pace, full-fuel start** |
| **Result** | **~11–12 laps before fall-off** (22–24 laps of 1× wear) |
| Model predicted | ~6–7 real laps. **Wrong by ~1.8×.** |
| **Game version** | **v1.70** |

**What this changes about how to read this car:**

1. **The "2nd worst in the field" ranking is not a usable absolute number.** It is a 2019 *relative* ranking at a different multiplier, on a different compound, in a different game. The car did 11–12 laps at 2× on **Softs** — which comfortably covers a 10-lap stint with margin. **Stop treating the Huracán as unraceable over a stint.**
2. **The ranking may still be right in *relative* terms.** Nothing here tests the Huracán against the RSR or the McLaren. If the whole field's absolute wear is gentler than assumed, the Huracán can be both "2nd worst" and "perfectly fine for a 10-lap stint."
3. **Every wear-motivated setup compromise on this car should be re-examined.** Low camber, soft rear platform, near-max rear downforce, conservative diff — several of these were set to protect a wear budget that turned out to be substantially larger than modelled. Camber in particular is flagged as probably over-protected.

> **⭐ 21 Aug — and the meta-lesson of this entry now applies to the entry itself.** Point 1 says a stale *relative ranking* was being used as a current *absolute number*. **A v1.70 measurement used on v1.71 is the same error with better provenance.** The instruction that follows from this measurement — measure a stint, then choose — is the part that transfers. The number 11–12 is not.
>
> **This is why `16` §12 Job 2 runs on this car: to re-take this measurement on v1.71, at Watkins Glen where the car actually races, with the pre-1.71 result as the control.**

**Which corner goes first — still reasoning, still unverified.** The model assumed the **front-right** at Laguna (a predominantly left-hand circuit, so the outside-front carries sustained load), against the car's own **rear**-limited reputation. Nobody has confirmed which actually went first. **Next measurement priority — and it closes for free inside Job 2.**

Full write-up and the strategy rebuild it forced: `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 2. Wear-model implications: `03-gt7-tyre-and-fuel-model.md` §1.3.1.

### 3.4 Braking and trail-braking

SoloX specifically credits *"braking efficiency"* enabling deep entries. The rearward mass bias helps here in the same way it does on the Porsche.

However — **reasoning, flagged** — the Huracán's higher yaw inertia means trail-braking rotation, once initiated, is harder to modulate than on the RSR. The Porsche rotates crisply and settles; the Lamborghini rotates with more commitment. A heavy trail-braker will find it rewards a **single decisive rotation input** rather than continuous modulation, because continuous modulation on a high-inertia car mostly generates rear tyre scrub.

**⭐ This is a polar-moment argument and survives 1.71. It is the most reliable driving-technique claim in this profile.**

**Brake balance.** ⚠️ No GT7-specific published figure. The only sheet located ([Team Shmo, GT Sport era](http://www.teamshmo.com/gt-sport/gtsport-track/lamborghini-huracan-gt3-15/)) used **−1**.

✅ *In-house, 10 Aug 2026: the Laguna build ran **brake balance 0**, with entry stability taken from LSD braking sensitivity (26) instead of bias. No stability complaint was reported across the test programme.* This supports the driver-profile position that this car's entry stability can be found mechanically without moving bias forward — which matters, because forward bias would load the front-right, the tyre the circuit limits on.

> **⚠️ 21 Aug — the *principle* stands (find entry stability mechanically, not with bias) but the *value* 26 needs re-establishing.** 1.71 adjusted ABS slip-ratio control and cornering brake behaviour, and revised the diff's adjustment range. Both terms in "LSD braking 26 with bias at 0" moved.

### 3.5 Aero character

**Higher-downforce, higher-power — a more complete package than the Porsche.** The 5.2 V10 means it does not have the RSR's straight-line deficit.

⚠️ **Downforce range** (§3.1): **front 350–450, rear 500–700** on v1.70. The GT Sport Team Shmo reference figures (400 / 760) are confirmed **not transferable** — the rear figure exceeds the GT7 slider maximum entirely. **⚠️ 1.71 revised aero adjustment ranges on race cars; re-read before using either number.**

**Race-validated aero balance point:** the Laguna build ran **425 front / 695 rear** (≈38% front share) for the race and **450 / 675** (≈40%) for qualifying. Rear near maximum is the deliberate choice on this car — rear downforce is the only source of rear grip carrying **no tyre-wear penalty**, and the car has straight-line speed to spend on the drag.

> **⭐ That reasoning — rear downforce is wear-free rear grip — is the strongest aero argument in the knowledge base and it survives 1.71 as reasoning.** But note it is expressed as *absolute points on a range that may have moved*, and "rear near maximum" only means something once the maximum is known. **Re-read the range, then re-derive the number, then keep the principle.**

**Circuits that suit it — reasoning, flagged.** Power-rich character favours circuits with straights where the V10 pays (Monza, Sardegna, Tokyo Expressway, Le Mans). **⚠️ The old blanket advice — "treat as a sprint car, avoid long formats" — is now weaker than it looks**, given §3.3.1. Re-derive per event from a measured stint rather than from the car's reputation.

### 3.6 Setup levers that matter most

The old organising question for this car was *"does this buy me rear tyre life?"* **That question is now demoted**, because the wear budget is larger than assumed (§3.3.1). The better question is *"is this change paying for itself, or am I protecting against a limit I haven't measured?"*

> **⭐ 21 Aug — apply that question honestly on v1.71 and the answer is that *nothing* on the sheet can currently name a measured limit.** So: build the car the driver can drive, leave the tyre-saving budget unspent, and go and measure. Do not carry v1.70's conservatism forward on faith — it was wrong by 1.8× the last time it was checked.

1. **✅ LSD acceleration sensitivity — #1, and it is not close.** See §3.6.1. It decides whether the car rotates at all, and it also governs rear scrub. Rare case where the balance fix and the tyre-life fix are the same change in the same direction. **⚠️ Re-test on v1.71 — new torque map, revised diff range.**
2. **Rear downforce.** The cheapest rear grip available — no wear penalty. On a car with straight-line speed in hand, spending it here is a better trade than on the Porsche.
3. **LSD braking sensitivity.** With brake bias held at neutral (per the driver profile), this is the entire entry-stability toolkit. The Laguna build used 26, up from the MR baseline of 20. Not yet walked to a validated optimum.
4. **Rear tyre load management** — rear natural frequency, rear ARB, rear ride height. Still valid, but **apply less aggressively than previously advised** until a wear measurement justifies it.
5. **Camber.** Post-1.49 GT7 taxes camber against braking and traction, so low is right in principle. But the Laguna build's 1.0°/1.0° was set partly against a wear limit that proved soft — **flagged as probably over-conservative and queued for testing at 1.2/1.1.** **⚠️⚠️ And now doubly live: 1.71 reworked the steering geometry that makes camber expensive. Test the direction before assuming it, and widen the sweep beyond 1.2/1.1 — `16` §12 Job 5 runs 0.5 / 1.5 / 2.5.**
6. **Fuel map / short-shifting.** On this car short-shifting is a **double win**: ~20% fuel for ~0.5 s/lap, *and* it keeps the V10 out of peak torque on exit, which is where the rears get spent. **⭐ This is the technique that won the 17 Aug Watkins Glen race, via the Pit Crew shift beep. ⚠️ 1.71's new torque control map means the shift points want re-checking.**

#### 3.6.1 ✅ VALIDATED — LSD acceleration sensitivity: start at **14**, not 15, and never at the track norm

**⚠️ Validated on v1.70. Re-test required — see the note at the end of this subsection.**

**Test:** Laguna Seca, 10 Aug 2026, GT7 v1.70. Open tuning, no BoP. 525 bhp / 1300 kg, **power restrictor 70 / ECU 97**, 70 kg ballast at −25, brake bias 0, TCS 0, ABS Weak.

**Symptom at accel 18:** power-on mid-corner understeer through **T2, T3, T4, T5**, present **from lap 1, cold and hot**. Neutral off throttle; ran wide as soon as throttle was picked up. **T11 — the corner 18 was chosen for — did not complain.**

**Change:** accel sensitivity **18 → 14**, single isolated change. **Result: resolved completely.**

**Three transferable conclusions:**

1. **The MR baseline of 15 is a ceiling on this car, not a midpoint.** Community and track-specific guidance for Laguna calls for 20–28 to protect the T11 traction exit. On this car with a restrictor fitted that is badly wrong, and wrong from the first lap.
2. **The restrictor is the reason, and this generalises to any restricted build.** A power restrictor cuts top-end while largely preserving low-end torque, so a restricted Huracán delivers proportionally *more* torque in the early corner-exit phase than its headline power implies. More early torque through a locked diff is the direct recipe for power-on push. **Re-test accel sensitivity whenever the restrictor moves.** No published tune accounts for this, because published tunes are unrestricted max-PP builds.
3. **The diagnosis is available from the driver's description alone.** Four questions — where is your right foot, which corners, from lap 1 or with wear, built as written — localised this to one slider with no telemetry. **The corner that stayed silent (T11) was the tell**: it was the corner the value had been aimed at, which meant the value was right where it was pointed and wrong everywhere else.

**What was NOT changed, and why it matters:** front ARB (5→4) and front downforce (425→450) were both queued as fallbacks. Neither was needed. Both would have masked a power-on symptom by adding front grip, at the cost of roll control or entry stability.

**Open questions on this value:**
- Does 14 hold on **worn** tyres? The test was on fresh rubber. If the inside rear starts spinning late in a stint, the answer is TCS 1 and short-shifting — **not** more accel lock.
- ⚠️ **Compound provenance:** the test ran against a sheet specifying Racing Hards, but the race has since moved to Racing Softs (§3.3.1). The failure mode was diff-torque driven rather than grip-level driven, so the result should carry — but a confirmation pass on Softs is queued.
- Can **qualifying** carry more? Currently also at 14, adopted rather than tested.
- Does the **Brands Hatch** 525 bhp build have the same problem? Its logged symptom — "mid-corner understeer on acceleration" on the same restricted package — is the identical signature. Strong candidate for a retro-fix.

> **⚠️⚠️ 21 Aug 2026 — re-test 14 before reusing it. Two independent reasons.**
>
> **First, the torque map changed.** 1.71 introduced a new engine torque control map, citing improved partial-throttle speed control. **This finding is entirely an argument about torque *shape* in the early corner-exit phase — which is the thing PD just re-authored.** Conclusion 2 above is the load-bearing one and it is the one most exposed.
>
> **Second, the diff range changed.** 1.71 revised the differential's initial settings and adjustment ranges, and **[COMMUNITY — single source]** one report says the Fully Customisable Diff now floors at **0/0/0** rather than 5. If true, **the useful territory extends below anywhere this test looked** — and this is a finding about the bottom of the range.
>
> **All three transferable conclusions survive** — they are about method, about restricted builds in general, and about diagnosis. **The number 14 does not.** Add a fourth conclusion: **re-test accel sensitivity after a physics update, not only after a restrictor change.**

### 3.7 Baseline setup

⚠️ **No usable public BoP-spec GT7 setup sheet exists for the Huracán GT3.** What exists:

- **[AdrenaTune Max Gr3 Tunes, GTPlanet](https://www.gtplanet.net/forum/threads/adrenatune-max-gr3-tunes.406118/)** (April 2022) — numbers embedded in an image attachment ("LamboMax.png"), not machine-readable. Pre-1.49 max-tune sheet.
- **[Team Shmo GT Sport sheet](http://www.teamshmo.com/gt-sport/gtsport-track/lamborghini-huracan-gt3-15/)** — ⚠️⚠️ Gran Turismo **Sport**, 692 hp / 1,094 kg max-tune. Rear downforce figure exceeds the GT7 slider maximum. **Do not use.**

**Use this instead — the in-house baseline**, derived from the Laguna Seca race build (`setups/2026-08-10-huracan-laguna-seca.md`, Rev D).

> **⚠️⚠️ 21 Aug — this table is a v1.70 sheet and must not be typed into a v1.71 car as-is.** The most recent Huracán sheet is `setups/2026-08-17-huracan-watkins-glen-long-revD.md`, and it is also pre-1.71. **Both are starting points and control groups, not setups.** `16` §12 Job 0 — read the car's current values against Rev D before touching anything, because the patch may have reset or clamped them.

| Setting | Starting value | Status |
|---|---|---|
| **Race compound** | **Racing Soft** | ✅ **MEASURED on v1.70** — 11–12 laps at 2×, §3.3.1. **Pick the compound from a measured stint, never from a model — and never from a stint measured on a previous version.** |
| LSD initial torque | 6 | Modelled — low, per the "high preload causes silent mid-corner push" rule. ⚠️ *Floor may now be 0, not 5* |
| **LSD acceleration** | **14** | ✅ **VALIDATED on v1.70** — §3.6.1. Below the MR baseline of 15. ⚠️ **Re-test: new torque map** |
| LSD braking | 26 | Modelled — up from MR baseline 20, carrying the stability brake bias is not allowed to carry. ⚠️ *ABS cornering behaviour changed* |
| Brake balance | 0 | ✅ Ran without complaint across the test programme |
| Camber F/R | 1.0 / 1.0 | Modelled, and **flagged as probably over-conservative**. ⚠️⚠️ **Suspended pending the Job 5 A/B — the geometry model was reworked** |
| Toe F/R | 0.00 / +0.06 | Modelled. Front toe **never A/B tested on this car** — outstanding for a fourth session |
| Damper compression F/R | 27 / 27 | Modelled, biased soft for compliance. ⚠️ *Damper model changed; window may have moved* |
| Damper expansion F/R | 44 / 36 | Modelled. Front firm for crest recovery, rear soft for lift-off stability. ⚠️ *same* |
| ARB F/R | 5 / 3 | Modelled. Soft rear to protect rear grip |
| Natural frequency F/R | 3.30 / 3.45 Hz | Modelled — bottom quarter of the 3.00–5.00 range. ⚠️ *Range unverified on 1.71* |
| Ride height F/R | 64 / 72 mm | Modelled — well above the 55/60 floors, per the post-1.49 arch-rub rule. ⚠️ *Floors unverified; arch-rub status unknown* |
| Downforce F/R | 425 / 695 | Modelled — rear near max, the only wear-free rear grip. ⚠️ *Aero range revised on race cars* |
| Ballast | 70 kg @ −25 | Provisional. Ran without complaint; never A/B'd against −50. ⚠️ *And PP moved, so the ballast's PP job may have changed* |

**Adjust from here by circuit type:** move ballast toward −50 and accel sensitivity upward only at rear-limited, traction-dominated circuits where one dominant exit sets the lap time. At twisty, multi-exit circuits — the Laguna archetype — **stay at 14 and stay off full-forward ballast.**

### 3.8 GT7-specific quirks and BoP history

- **The accel-diff sensitivity is the headline quirk**, newly established: this car wants materially less acceleration lock than published guidance, and dramatically less than track-specific advice suggests, especially on a restricted build (§3.6.1). **⚠️ Established on v1.70.**
- **The tyre-wear reputation needs revising.** The 2019 ranking is relative, pre-1.49, and at a different multiplier and compound. The one real measurement is far kinder (§3.3.1). **Do not rule this car out of a format on reputation — measure a stint.** **⭐ That instruction is now the entire content of the entry: the measurement it rests on is a version behind, and the fix is the same as it was — measure a stint.**
- **Conspicuous absence from 2026 recommendation lists.** Coach Dave Academy's 2026 tier list does not mention it. Whether this is genuine decline, curation, or a wear reputation compounding on stale data is unclear. **⭐ It won a race on 17 Aug 2026 from P5. Weight that above the tier lists.**
- **BoP:** 484 hp / 1,275 kg as of March 2022. No later public data. *(Irrelevant to this league's no-BoP rounds.)*

---

## 4. The "Shelby GT3500" Question — Disambiguation

**No car named "Shelby GT3500" exists in GT7 or in reality.** The name appears to be a conflation of **GT350** and **GT500**.

**⭐ This entire section is a question of which cars exist. It is unaffected by 1.71 — except that 1.71 added four new cars (Caterham Seven Superlight R500 '08, Hyundai IONIQ 6 N '25, Toyota Chaser Tourer V '97, Toyota Mark II Tourer V '97), none of which is a Shelby or a Mustang.**

### 4.1 What exists in GT7

| Car | In GT7? | Layout | Power | Weight | PP ⚠️ *all v1.70* | Category | Source |
|---|---|---|---|---|---|---|---|
| **Ford Mustang Gr.3** | ✅ Yes | FR | 568 BHP @ 7,000; 61.2 kgfm @ 6,000 | 1,300 kg | 716.44 | Gr.3 racing car | [GTDB](https://gtdb.io/gt7/car/mustang-gr-3/), [Fandom](https://gran-turismo.fandom.com/wiki/Ford_Mustang_Gr.3) |
| **Ford Mustang Gr.4** | ✅ Yes | FR | 395 BHP @ 6,500 | 1,400 kg | 632.77 | Gr.4 racing car | [GTDB](https://gtdb.io/gt7/car/mustang-gr-4/) |
| **Ford Mustang Gr.3 Road Car** | ✅ Yes | FR | 502 BHP @ 7,000 | 1,500 kg | 572.51 | Gr.3 / Road Car | [GTDB](https://gtdb.io/gt7/car/mustang-gr-3-road-car/) |
| **Ford Shelby GT350R '16** | ✅ Yes | FR | 525 BHP @ 7,500; 5,163 cc flat-plane V8 | 1,658 kg | 575.47 | Road Car / Gr.N | [GTDB](https://gtdb.io/gt7/car/shelby-gt350r-16/) |
| **Shelby G.T.350 '65** | ✅ Yes | FR | 304 HP @ 6,000 | 1,270 kg | 476.82 | Road Car / Gr.N | [GTDB](https://gtdb.io/gt7/car/g-t-350-65/) |
| **Shelby Cobra 427 '66** | ✅ Yes | FR | 484 BHP @ 6,500 | 1,068 kg | 584.01 | Road Car / Gr.N | [GTDB](https://gtdb.io/gt7/car/cobra-427-66/) |
| **Ford Mustang Gr.B Rally Car** | ✅ Yes | — | — | — | — | Gr.B | [GT.com](https://www.gran-turismo.com/us/gt7/carlist/id/car3229) |
| **Shelby GT350R Gr.4** | ❌ Does not exist | — | — | — | — | — | The Gr.4 Mustang is a GT Original based on the Mustang GT Premium Fastback '15 |
| **Shelby GT500 (any year)** | ❌ Not found | — | — | — | — | — | ⚠️ Absence-of-evidence — verify in-game |
| **Ford Mustang GT3 (real IMSA/WEC car)** | ❌ Not in GT7 | — | — | — | — | — | GT7's Mustang Gr.3 is a Gran Turismo Original, not this car |

### 4.2 Resolution

**Resolved:** the driver profile confirms the car in use is the **Ford Shelby GT350R '16** (Sainte-Croix and Watkins Glen sessions; three Yas Marina setup sheets through 16 Aug 2026). The Mustang Gr.3 profile below is retained because it remains the relevant option if the league runs Gr.3 rounds.

---

## 5. Car Profile — Ford Mustang Gr.3

### 5.1 Specifications

| Parameter | Value | Source |
|---|---|---|
| Category | Gr.3 / Racing Car | [GTDB](https://gtdb.io/gt7/car/mustang-gr-3/) |
| Drivetrain | **FR** (front engine, RWD) | GTDB, Fandom |
| Stock power | 568 BHP @ 7,000 (GTDB) / 549 BHP (Fandom) — ⚠️ **sources disagree** | GTDB, Fandom |
| Stock torque | 61.2 kgfm @ 6,000 rpm | GTDB |
| Stock weight | 1,300 kg | Both agree |
| Displacement | ⚠️ **GTDB shows "NaN cc."** Base car is a 5.0 V8 | GTDB |
| PP (stock) | 716.44 — ⚠️ **v1.70** | GTDB |
| Dimensions | 4,923 × 2,000 × 1,280 mm | GTDB |
| Base model | Ford Mustang GT Premium Fastback '15 | Fandom |
| Origin | **Gran Turismo Original**, first appeared in GT Sport | Fandom |
| BoP power/weight | ⚠️ **"(Unknown)"** — never documented | [GTPlanet Gr.3 BoP thread](https://www.gtplanet.net/forum/threads/group-3-bop-list-and-discussion.405641/) |

### 5.2 Fundamental handling character

⚠️ **This car is very poorly covered.** It is **absent from every major Gr.3 recommendation list examined** — Coach Dave Academy 2026, SoloX, and the GTPlanet "Best Gr.3 car?" thread. **No BoP data. No published tune.**

That absence is itself the finding. **A driver running it is largely on their own for setup data — which, in a no-BoP open-tuning league, is arguably an advantage.**

> **⭐⭐ 21 Aug — and 1.71 just made that advantage much larger, at least temporarily.** The entire community tuning record went stale on 20 August: every published tune, every tier list, every BoP table now describes a previous version of the game. **The gap between a well-documented car and an undocumented one has narrowed to almost nothing, because for the next few weeks nobody has current data on anything.**
>
> **There is a second, concrete reason to consider this car now:** `11-car-slider-ranges.md` has wanted an **FR Gr.3** data point since 13 August. Both recorded Gr.3 cars are MR, and the register's strongest finding — that their 22 slider endpoints are identical — is *"suggestive, not proof,"* because two same-layout cars from the same era prove less than a contrasting one would. **An FR Gr.3 car settles whether the nine chassis-derived endpoints are a Gr.3 constant or an MR-Gr.3 one, and 1.71 has just re-rolled all of them, so the measurement has to be taken fresh regardless.**

**What can be said with confidence:**

- It is **FR** — the only front-engined car of the three, on the less-favoured side of the current MR-versus-FR balance, but the more forgiving side for wet and racecraft. **⚠️ The MR-versus-FR verdict is a pre-1.71 assessment — see §1.0.**
- At **1,300 kg** it matches the RSR and is 70 kg heavier than the Huracán at stock.
- Its **2,000 mm width and 4,923 mm length** make it one of the physically largest cars in Gr.3 — matters for traffic and narrow circuits. **⭐ And more so if the league adopts 1.71's "Championship" damage setting, which triggers damage from more minor collisions (`16` §9).**

**The specific failure mode — reasoning, flagged.** Standard FR Gr.3 character: **corner-exit traction limitation**, plus more entry understeer to manage. The trade is that when it does let go, it does so more progressively.

### 5.3 Tyre wear character

⚠️ **No data.** The GT Sport MR wear test did not cover FR cars.

**Reasoning, flagged:** an FR Gr.3 car with an exit-traction limitation will typically be **rear-limited on wear from traction events** and **front-limited on wear from entry understeer** — it can burn both ends depending on style. Verify empirically. **And given §3.3.1, verify before assuming it is bad.**

### 5.4 Braking and trail-braking

**Reasoning, flagged:** the front weight bias gives strong initial braking stability, making it **the most forgiving of the three for aggressive initial brake application** but the **least rewarding for deep trail-braking** — the mechanism that generates trail-brake rotation (unloading a rear axle carrying significant static mass) is weaker when the rear carries less mass.

A heavy trail-braker will find it requires **more deliberate rotation induction** — more rear brake bias, more front toe-out, a looser diff on entry.

**⭐ If the diff floor really did drop to 0, "a looser diff on entry" now has somewhere further to go — and this is the car archetype that most needs it (`16` §5).**

**Brake balance.** No published figure. Start at **0** and walk toward rear bias until entry rotation appears.

### 5.5 Aero character

⚠️ **No downforce range data.** Occam's Racer's generic Gr.3 figures (450 lb front / 700 lb rear) are category-wide. **⚠️ And 1.71 revised aero adjustment ranges on race cars, so even the two measured Gr.3 cars' ranges no longer supply a reference.**

**Reasoning, flagged:** large frontal area suggests a relatively high-drag body. Combined with the **highest torque figure of the three cars**, the likely character is **strong low-to-mid-speed acceleration, moderate terminal top speed** — suiting medium-speed circuits with hard acceleration zones.

### 5.6 Setup levers that matter most

**Reasoning, flagged:**

1. **LSD acceleration sensitivity.** For an FR car this is the primary exit-traction control. Flux89's FR baseline is **5 / 25 / 10**. ⚠️ **But see §3.6.1 before treating 25 as a floor:** on a restricted build, published accel figures assume a torque curve you don't have. If this car shows power-on mid-corner push, come *down* from 25 in 2-point steps before touching front grip. **⭐ And 1.71's new torque control map means published accel figures now assume a torque curve *nobody* has.**
2. **Rear ARB / rear spring rate.** Softer rear = more mechanical rear grip on power.
3. **Front toe and front ARB.** The tools for fighting FR entry understeer.
4. **Brake balance.** How a trail-braker gets this car to rotate.
5. **Weight distribution / ballast.** The one car of the three where moving mass rearward has a large payoff.

### 5.7 Baseline setup

⚠️ **No published GT7 setup exists.** Build from the [Flux89 v1.2](https://www.flux89.com/guides/gt7-tuning-cheat-sheet) FR baseline:

| Setting | Starting value |
|---|---|
| Damper compression F/R | 30 / 30 |
| Damper expansion F/R | 40 / 40; must exceed compression |
| ARB F/R | Front 4–6, rear 3–6 |
| Camber F/R | −1.5 to −2.0° / −1.0 to −1.5° ⚠️ *suspended pending the Job 5 camber A/B* |
| Toe F/R | 0.00° / +0.05° |
| Natural frequency | 70–80% of slider; rear slightly stiffer ⚠️ *known-broken heuristic on Gr.3 — anchor in absolute Hz, see `11`* |
| Ride height | Front 3–5 clicks above min; rear 5–8 above ⚠️ *known-broken heuristic — state as percent of range, see `11`* |
| LSD (FR) | **5 / 25 / 10** — treat accel 25 as a *ceiling* on a restricted build ⚠️ *floor may now be 0* |
| Brake balance | Start at 0 |
| Downforce | Max front first, then trim rear for high-speed balance ⚠️ *aero ranges revised* |

### 5.8 Notes on the alternative candidates

**Ford Mustang Gr.4** — FR, 395 BHP, 1,400 kg, PP 632.77. 100 kg heavier than the Gr.3 car with 30% less power: more of a momentum car, more tyre-limited relative to its power.

**Ford Shelby GT350R '16** — **the driver's actual third car.** FR road car, Gr.N, 5,163 cc flat-plane-crank V8, 525 BHP @ 7,500, **1,658 kg**, PP 575.47. The flat-plane crank means a peaky, high-revving delivery (real-world redline 8,250 rpm per [Traxion](https://traxion.gg/audi-r8-lms-gt3-evo-ii-and-ford-mustang-shelby-gt350r-coming-to-gran-turismo-7/)). At 1,658 kg it is **355 kg heavier than the Mustang Gr.3** — far more mass into braking zones and much more tyre wear. See driver profile §11 for the Sainte-Croix and Watkins Glen findings. ⚠️ GTDB's prose calls it "based on the seventh generation Mustang," which is wrong for a '16 model; treat GTDB's prose as unreliable while its numbers appear sound.

> **⭐ Two 1.71 notes on the Shelby specifically, because it is a car actually in the garage:**
>
> **1. ⚠️ Overtaken by the re-read: the car reads PP 723.61 on v1.71** (`brain/car-state/shelby-deep-forest.md`), so the 575.47 above is void and the car no longer sits in the 550–650 band that `06` §8.2 identifies as the worst-affected range for PP-vs-lap-time mismatch.
>
> **2. `11-car-slider-ranges.md` records that this car ran its natural frequency well up its v1.70 range on the Yas Marina sheets (the positions are the sheets', not this file's - §1a) — on a 1,658 kg road car at a circuit with aggressive kerbs — and that none of the softness below that has ever been tried.** That remains the single most interesting unexplored direction on this car. **The range has been read on v1.71 (23 Aug, `range_records`): 2.00–4.00 Hz at both ends**, so the floor moved up at the front; take any natural-frequency figure for this car as a percent of that range, from its car-state file.

### 5.9 ⭐ Ford Shelby GT350R '16 — the measured profile, v1.71 (plan row 2.8, 11 Sep 2026)

**[MEASURED — IN HOUSE]** unless tagged. The archive is **213 laps in 24 sessions**; **177 are on v1.71** — Road Atlanta 51 (23 Aug), Red Bull Ring Short 69 (27–30 Aug), Deep Forest 57 (6 Sep). Yas Marina's 36 (13–16 Aug) are v1.70 and **void**. Every value set on the car lives in `brain/car-state/shelby-*.md`, not here (§1a); this section says what the car does.

**The front axle is this car's limit — three independent indicators.**
1. **Wear:** the worst wheel is a front at both circuits measured — the front-left at Red Bull Ring (0.90–1.35 %/km at 2x, ~1.6x the front-right, four sessions, monotone) and the front-right at Deep Forest (0.66 %/km, leading the front-left 1.27x on a direction-balanced circuit).
2. **[DERIVED by GT7]** its own stability readout: **−0.50 high speed (Under), −0.29 low speed (Neutral)** — GT7's own labels (`brain/car-state/shelby-deep-forest.md`).
3. **Braking, ABS prohibited:** the front locks on almost every lap at every v1.71 circuit — **37 of 41** laps at Road Atlanta, **44 of 62** at Red Bull Ring, **47 of 47** at Deep Forest (front slip below 0.90, brake over 40 %, over 60 km/h).

**His rear-lock complaint was real, and the fix overshot.** Rear lock ran **8 of 41** laps at Road Atlanta, with opposite lock on 6; as the bias moved forward (his trim) it fell to **0 of 62** at Red Bull Ring and **2 of 47** at Deep Forest, while the front lock deepened (at Deep Forest the median of each lap's minimum front slip was 0.663, all four wheels on tarmac, and every lap locked). ⚠️ Across circuits this is **suggestive, not measured** — different sheets, different tracks; the clean test is within one circuit. **A locked front rotates the car less on release, not more** (r = +0.504 over 153 braking events), so a front-locking snap is not a mechanism on this car.

**Rake is not the lever.** Both ride-height floors are 20 mm apart, so the car sits nose-down at minimum slider already; the front runs further off its floor than the rear, in percent of range (the positions live in its car-state file, not here). The opposite asymmetry from the Huracán at Daytona — same question, opposite answer.

**Gearing.** `top` is a gear-**spacing** slider, not a top speed. The invariant is **K = ratio x speed at the limiter = 304 km/h** (limiter ~8,800 rpm), agreeing to 0.3 % between Road Atlanta and Red Bull Ring. **GT7's "Top Speed (Automatically Adjusted)" readout moves the wrong way** on this car — on a hand-cut box it rose 5 while the real top speed fell 29 km/h. Never read a road speed off it.

**Fuel — observed, not a rule.** Practice burn ran above race burn at Road Atlanta (−3.5 %) and Red Bull Ring (−9.2 %). **At Deep Forest it did not:** the race's last stint burned 7.92 L/lap against practice's 7.84, because the driving changed mid-race - +0.47 L/lap when he stopped coasting and +0.23 more when he stopped short-shifting. **Never discount the fill for the last stint: size it from the live burn at the hose.** A practice-rate fill cut by 9 % would have run him dry by about 5 L over those seven laps.

**Open, and each is a test not yet run:** the natural-frequency softness below anything tried (§5.8 note 2); whether `lsd_b` up lets him bring the bias back without the rear lock returning (the Huracán precedent, never issued here because 47 laps at Deep Forest do not show the problem); and 2nd gear running past its own ceiling at Deep Forest.

**Ford Mustang Gr.3 Road Car** — FR, 502 BHP, 1,500 kg, PP 572.51. Despite the name it is **not** a Gr.3 competitor.

**Shelby Cobra 427 '66** — FR, 6,977 cc, 484 BHP, **1,068 kg**, PP 584.01. Extreme power-to-weight with 1960s chassis dynamics; a specialist, not a race car.

---

## 6. Comparative Section — Driving Style Demand

> **⚠️⚠️ 21 Aug 2026 — this is the most 1.71-exposed section in the document, and it is worth being precise about why.** The update reworked steering geometry **for each car**. A comparison table is a set of *relative* claims, and a per-car change can reorder relatives without changing any absolute. **Mass distribution, polar moment and layout are intact and are the safest terms to reason from. Everything downstream of "how this car converts input into yaw" is a hypothesis again.**

### 6.1 The three cars in one table

| | **Porsche 911 RSR (991) '17** | **Lamborghini Huracán GT3 '15** | **Ford Mustang Gr.3** |
|---|---|---|---|
| Layout | MR (mid-engine flat-six) | MR (mid-rear V10) | FR (front V8) |
| Stock power / weight | 509 BHP / 1,243 kg | 576 BHP / 1,230 kg | 568 BHP / 1,300 kg |
| Stock PP ⚠️ *v1.70* | 720.74 | 738.66 | 716.44 |
| Mass concentration | **Lowest polar moment** ✅ *intact* | **Highest polar moment** ✅ *intact* | Middle, mass ahead of front axle ✅ *intact* |
| Current standing | **Rising** on v1.70. "Best all-rounder" (Coach Dave 2026) ⚠️ *pre-1.71* | **Under-rated on stale data.** Absent from 2026 lists; wear reputation built on 2019 figures now partly contradicted — **and it won on 17 Aug 2026** | **Undocumented.** Absent from all lists; no BoP or tune data — **and post-1.71 so is everything else** |
| Straight-line | **Weakest** | **Strongest** | Middle — highest torque, likely high drag |
| Tyre wear reputation | Best of the three (2019 test) | Worst of the three (2019 test) | Unknown |
| **Tyre wear, measured** | ❌ none | ⚠️ **RS, 2×, Laguna: 11–12 laps — on v1.70** | ❌ none |
| Failure mode | Exit-phase power rotation; throttle-timing sensitive | **Power-on push if accel diff is set conventionally (✅ confirmed on v1.70)**, then stint-scale rear degradation | Exit traction limitation; entry understeer |
| LSD accel starting point | MR baseline 15 (untested) | **14 ✅ validated on v1.70 — re-test on 1.71** | FR baseline 25 (untested; treat as ceiling if restricted) |
| Documentation quality | Good publicly — 2 full GT7 setups (2022), current reviews | Poor publicly — **but by far the best documented internally**: full absolute-value sheets, two validated results, one race win | **Very poor — nothing** |
| **Post-1.71 status** | Ranges void, character unverified, PP unread | **Ranges void, two measured results one version behind — the car Jobs 2, 3 and 5 are written around** | Never measured — **and now the most attractive it has ever been, as the FR Gr.3 range datapoint** |

### 6.2 How the driving style demand differs

**The Porsche demands throttle discipline.** Its mass is concentrated and its inertia low, so it changes direction willingly and recovers from yaw quickly. What it will not tolerate is throttle before the car is straightening. It gives you rotation cheaply and asks you to pay for it on exit. Because it is straight-line-limited, lap time comes from corner speed.

**The Lamborghini demands a freer diff than anyone tells you — and less caution than its reputation suggests.** The 10 Aug 2026 results reframed this car twice in one day. The diff finding: **the setting that makes it rotate is also the setting that makes the tyres last**, because less acceleration lock means less rear scrub. Where most cars force a trade between balance and stint length, the Huracán's accel axis moves both the same way — making it the first thing to set and the last thing to compromise.

The wear finding cuts the other way against received wisdom: **the car is not as fragile as its 2019 ranking implies.** Its style demand remains **early, decisive rotation followed by a clean, unloaded exit** — minimise time with the rear axle simultaneously loaded laterally and longitudinally. But the engineering conclusion that used to follow ("therefore compromise everything for rear life") no longer follows automatically. Measure the stint first.

**The Mustang demands rotation manufacturing.** The only car of the three that will not rotate for free. It wants to run wide on entry and spin the inside rear on exit. It rewards deliberate driving: get the braking done, use brake bias and front geometry to force the nose, then be patient with the throttle. Most forgiving of the three when you get it wrong; least generous when you get it right.

> **⭐ Of these three characterisations, the Lamborghini's is the one built on measurements and therefore the one most exposed to 1.71.** The Porsche's and the Mustang's rest on layout and mass distribution, which are intact. **Ironically the best-evidenced entry is the least reliable right now** — which is itself the argument for re-measuring rather than for measuring less. Same lesson as `08` Part G.

### 6.3 Which suits a heavy trail-braker on a load-cell pedal

**Ranked on v1.70: 1) Porsche 911 RSR, 2) Lamborghini Huracán GT3, 3) Ford Mustang Gr.3.**

**⚠️ Two of the three supporting arguments moved in 1.71. Treat the ranking as a hypothesis until the first outing on each car.**

**The Porsche is the clear match.**

1. **Rearward mass bias (46:54) is what makes trail-braking work.** A car with meaningful static rear mass has rear tyre load to give up progressively; a front-biased car does not. **✅ Intact — mass distribution does not patch.**
2. **Low polar moment means the rotation is modulable.** This is what a load-cell pedal buys you — fine, repeatable pressure adjustments deep into a corner producing proportional response. **✅ Intact.**
3. **1.49 made brake bias a much more powerful lever**, and the RSR has the mass distribution to make bias changes meaningful. **⚠️ 1.71 adjusted ABS slip-ratio control and cornering brake behaviour — the trail-braking phase by name. This term is unverified.**

**The Lamborghini is a good but less linear match.** It has the rearward bias and the braking strength, but the high polar moment makes the pressure-to-yaw relationship less linear: more to start the rotation, more to stop it. Continuous trail-brake modulation on a rear-limited car also costs rear tyre. **That last objection is now softer than it was** — the wear budget is larger than assumed — but it has not disappeared, and it remains the reason to prefer one decisive input on this car. **⚠️ And the wear-budget softening was measured on v1.70, so the objection's current strength is unknown in both directions.**

**The Mustang is the weakest match.** FR layout means less static rear mass to unload and less rotation available per unit of brake pressure. Trail-braking yields the least return per unit of driver effort. **✅ A layout argument — intact.**

### 6.4 Practical recommendations

**⭐ Re-ordered 21 Aug 2026 — the 1.71 rebuild comes first. Full protocol: `16` §12.**

0. **⭐ Run `16` §12 Jobs 0, 1 and 2 before any setup work.** Did the tunes survive (2 min) → re-read the slider ranges on all three cars (15 min) → one measured stint on the Huracán at Watkins Glen (30 min). **Forty-seven minutes rebuilds the foundation everything below stands on.**
1. **Re-baseline the Porsche as an MR car.** Switching from RR assumptions to the modern MR baseline is likely to unlock immediate trail-braking gains. **Still true, and §0.1 is unaffected by the patch.**
2. **Recalibrate brake balance post-1.49 — and now post-1.71.** Start near 0 and adjust in single clicks. 1.71 adjusted ABS cornering brake behaviour, so the reference needs re-establishing on both Gr.3 cars.
3. ~~**Done — the Huracán's accel diff is set.**~~ **⚠️ Reopened by 1.71's new torque control map.** The three transferable conclusions in §3.6.1 stand; the value 14 needs re-testing.
4. ~~**Done — the Huracán's Laguna stint length is measured.**~~ **⚠️ Reopened by the new tyre model.** The instruction stands and is stronger than ever: **repeat this on every new event before choosing a compound.** `16` §12 Job 2.
5. **Measure which corner goes first on the Huracán.** The one thing §3.3.1 did not establish. **Closes for free inside Job 2 — and the Watkins Glen corner-ID mapping is needed for it, which has been asked for twice and never answered.**
6. **Re-test the Brands Hatch 525 bhp build at accel 14.** Its logged "mid-corner understeer on acceleration" is the same signature the Laguna test resolved. **⚠️ Do this after re-establishing the accel value on v1.71, not before.**
7. **⭐ NEW — run the camber A/B on both Gr.3 cars.** 1.71 reworked the geometry model that makes camber expensive in GT7. **§2.7's open question — whether the 2022 tunes' −3.0° or the modern −1.0 to −2.0° is right — may finally have a different answer.** `16` §12 Job 5, ten minutes.
8. **⭐ NEW — read current PP off all three cars.** Fleet-wide re-roll; the league is PP-capped and no-BoP. `16` §12 Job 4.
9. **Read current BoP off gt-engine.com or in-game.** All public BoP data is from March 2022. *(Lowest priority — this league runs no BoP.)*

---

## 7. Explicit Data Gaps

| Gap | Status |
|---|---|
| **⭐ Post-1.71 anything, on any of the three cars** | ❌ **Nothing measured. The whole document is a v1.70 record.** `16` §12 is the plan. |
| **Current (post-1.49, now post-1.71) Gr.3 BoP power/weight** for all three cars | ❌ Not obtained. Only March 2022 data. gt-engine.com blocks automated access. *(Low priority — no-BoP league.)* |
| **Current PP for all three cars** | ❌ **NEW, and it is a race-weekend problem.** PP recalculated fleet-wide in 1.71. `16` §12 Job 4, ten minutes. |
| **Slider ranges on all three cars, on v1.71** | ❌ **NEW and blocking.** 1.71 revised adjustment ranges in writing. `11-car-slider-ranges.md` is the register and the re-read worksheet. **15 minutes, blocks every sheet.** |
| **Weight distribution** for Huracán GT3 and Mustang Gr.3 | ❌ Not found. Only the RSR's 46:54 (single source, 2022). **Unaffected by the patch.** |
| **Post-1.49 GT7 tyre wear data** | ⚠️ **Reopened.** The Huracán / RS / 2× / Laguna measurement (§3.3.1) is a v1.70 number. **Nothing for the RSR or the Mustang, nothing for RM or RH on any car, and nothing at all on v1.71.** |
| **Which axle/corner goes first on the Huracán** | ❌ Model assumed front-right; the car's reputation says rear. Unresolved. **Closes for free inside Job 2.** |
| **Stint lengths for the RSR and Mustang** | ❌ Not available. Must be measured. |
| **A current, BoP-spec setup sheet for the Huracán GT3** | ⚠️ **In-house sheets exist but are pre-1.71** — Rev D (`setups/2026-08-17-huracan-watkins-glen-long-revD.md`) is the most recent. **Control group, not a setup.** No *public* sheet exists at all. |
| **Huracán LSD acceleration starting point** | ⚠️ **Reopened.** Closed at 14 on v1.70; 1.71 introduced a new torque control map and revised the diff range. |
| **Whether the LSD floor is now 0 rather than 5** | ❌ **NEW.** [COMMUNITY — single source]. Thirty seconds to confirm on the settings screen. **High value if true** — it extends the useful territory below anywhere we have looked. |
| **Whether GT7 still over-punishes camber** | ❌ **NEW and high-value.** 1.71 reworked per-car steering geometry. If the penalty softened, the camber guidance in `02`, `03`, `07` and `08` is all wrong in the same direction. **Ten minutes.** |
| **Huracán front toe direction** | ❌ Never A/B tested — **fourth session running.** And toe sensitivity is downstream of the reworked steering geometry, so the disputed parameter has just been re-rolled. Shares a session with the camber A/B. |
| **Huracán ballast position** — is −25 better than −50? | ❌ Ran without complaint at −25 but never compared. **And ballast position is `06` §5.5's free-PP exploit, which now matters more because PP moved.** |
| **Whether accel 14 holds on Racing Softs and on worn tyres** | ❌ Validated on fresh rubber against a Hards-spec sheet — **and 14 itself now needs re-establishing first.** |
| **Any setup sheet at all for the Mustang Gr.3** | ❌ None found anywhere. **And post-1.71 that is a much smaller disadvantage than it was.** |
| **Mustang Gr.3 displacement / stock power** | ❌ GTDB returns "NaN cc"; power conflicts 568 vs 549 BHP. |
| **Whether a Porsche 911 GT3 R exists in GT7** | ⚠️ Unverified. |
| **Whether any Shelby GT500 exists in GT7** | ⚠️ Not found, but absence-of-evidence only. |

**Highest-value next steps, revised 21 Aug 2026:** run `16` §12 Jobs 0–2 (47 minutes: tunes survived? → ranges → one stint), then Job 5 (10 minutes: camber and front toe A/B, which closes two of the oldest gaps in this table at once), then Job 4 (10 minutes: PP audit). **Between them they close, or make progress on, nine rows of the table above.**

---

## Sources

**1.71 (the current baseline)**
- [gran-turismo.com — Update Notice (1.71)](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html)
- [GTPlanet — Update 1.71 Arrives With Major Physics Changes](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Traxion — 1.71 brings sweeping physics changes, resets leaderboards](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [GTPlanet — Undocumented Changes Thread (1.71)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-1-71.439041/)

**Car specifications**
- [Porsche 911 RSR (991) '17 — GTDB](https://gtdb.io/gt7/car/911-rsr-991-17/)
- [Lamborghini Huracán GT3 '15 — GTDB](https://gtdb.io/gt7/car/huracan-gt3-15/)
- [Ford Mustang Gr.3 — GTDB](https://gtdb.io/gt7/car/mustang-gr-3/)
- [Ford Mustang Gr.4 — GTDB](https://gtdb.io/gt7/car/mustang-gr-4/)
- [Ford Mustang Gr.3 Road Car — GTDB](https://gtdb.io/gt7/car/mustang-gr-3-road-car/)
- [Ford Shelby GT350R '16 — GTDB](https://gtdb.io/gt7/car/shelby-gt350r-16/)
- [Shelby G.T.350 '65 — GTDB](https://gtdb.io/gt7/car/g-t-350-65/)
- [Shelby Cobra 427 '66 — GTDB](https://gtdb.io/gt7/car/cobra-427-66/)
- [Ford Mustang Gr.3 — Gran Turismo Wiki (Fandom)](https://gran-turismo.fandom.com/wiki/Ford_Mustang_Gr.3)
- [Ford Mustang Gr.4 — Gran Turismo Wiki (Fandom)](https://gran-turismo.fandom.com/wiki/Ford_Mustang_Gr.4)
- [Gr.3 Car Specs — GT ENG!NE](https://gt-engine.com/gt7/cars/gr3/gr3-01-specs.html) *(inaccessible to automated fetch — read manually)*

**In-house validated data — highest authority for our own decisions, and now version-stamped**
- `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 1 — LSD acceleration, validated 14 — **v1.70**
- `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 2 — Racing Soft, 2×, Laguna: 11–12 laps — **v1.70**
- `setups/2026-08-17-huracan-watkins-glen-long-revD.md` — the most recent Huracán sheet, post-mortem on the 17 Aug win — **v1.70**
- `11-car-slider-ranges.md` — all three cars' slider endpoints — **v1.70, being re-read**
- `01-driver-profile-leon.md` §11 — the diagnostic method behind both measurements

**Handling character, rankings and reviews**
- [Best Gr.3 Cars in GT7: The Top Tier List (2026) — Coach Dave Academy](https://coachdaveacademy.com/tutorials/best-gr-3-cars-in-gran-turismo-7/)
- [The 9 Best GR.3 Cars in Gran Turismo 7 — SoloX](https://solox.gg/best-gr3-cars-in-gran-turismo-7/)
- [Best Gr.3 car? — GTPlanet](https://www.gtplanet.net/forum/threads/best-gr-3-car.406214/)

**Tyre wear**
- [Gr.3 MR cars tire wear test — GTPlanet](https://www.gtplanet.net/forum/threads/gr-3-mr-cars-tire-wear-test.384914/) — ⚠️ GT Sport, 2019
- [Is There A Tire Wear Chart? — GTPlanet](https://www.gtplanet.net/forum/threads/is-there-a-tire-wear-chart.431035/)
- [GT7 Gr.3 Car Fuel Economy Database (v1.70) — apexevolution](https://note.com/apexevolution/n/n9946c500557f?hl=en)

**Setups and tuning**
- [Porsche 911 RSR Best Circuit Grip Tune — Kavo Gaming](https://kavogaming.com/porsche-911-rsr-best-circuit-grip-tune-gran-turismo-7/) — ⚠️ April 2022
- [Looking for a good base setup for the 911RSR (991) '17 — GTPlanet](https://www.gtplanet.net/forum/threads/looking-for-a-good-base-setup-for-the-911rsr-991-17.405427/) — ⚠️ March 2022, pre-1.49
- [AdrenaTune — Max Gr3 Tunes — GTPlanet](https://www.gtplanet.net/forum/threads/adrenatune-max-gr3-tunes.406118/) — ⚠️ April 2022, image attachments
- [The Complete GT7 Tuning Cheat Sheet (v1.2) — Flux89](https://www.flux89.com/guides/gt7-tuning-cheat-sheet)
- [GT7 Tuning Guide: Every Setting Explained (2026) — Coach Dave Academy](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)
- [Lamborghini Huracán GT3 '15 — Team Shmo](http://www.teamshmo.com/gt-sport/gtsport-track/lamborghini-huracan-gt3-15/) — ⚠️⚠️ GT **Sport**, max-tune, not GT7 BoP

**BoP and physics**
- [Group 3 BOP List and Discussion — GTPlanet](https://www.gtplanet.net/forum/threads/group-3-bop-list-and-discussion.405641/) — ⚠️ March 2022
- [BOP and upgrades/tuning — GTPlanet](https://www.gtplanet.net/forum/threads/bop-and-upgrades-tuning.428202/)
- [GT7 Physics Update 1.49 Breakdown — DG EDGE](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424)
- [Update Details (1.49) — gran-turismo.com](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)
- [GT7 Aerodynamics — Occam's Racer (April 2024)](https://occamsracers.com/2024/04/19/gt7-aerodynamics/)

**Background**
- [Audi R8 LMS GT3 evo II and Ford Mustang Shelby GT350R coming to GT7 — Traxion](https://traxion.gg/audi-r8-lms-gt3-evo-ii-and-ford-mustang-shelby-gt350r-coming-to-gran-turismo-7/)
- [Porsche 911 RSR (2017) — Wikipedia](https://en.wikipedia.org/wiki/Porsche_911_RSR_(2017))

---

**How to read the evidence tiers in this document.** Claims are marked as **sourced facts** (links and dates), **explicitly flagged reasoning** (engineering inference from sourced character), **acknowledged unknowns**, and — as of 10 Aug 2026 — **✅ driver-validated in-game results**, which outrank all three. The two results added on that date each overturned something this document previously asserted: the first that published diff guidance was safe to start from, the second that this car's tyre wear made it unsuitable for anything but sprints. **Both were plausible, well-argued, and wrong. Weight the measured tier accordingly.**

**⭐ And a fifth tier, added 21 Aug 2026 by necessity: the game version a claim was established on.** Update 1.71 demoted both of the validated results above — not because the measurements were poor, but because the game moved underneath them. **A measured result outranks reasoning only while the physics it was measured on is still running.** Every claim in this file now needs a date *and* a version, per Standing Rule 10. The reasoning tiers — layout, mass distribution, polar moment — turned out to be the durable ones, which is a useful thing to know about which kind of claim to invest in.
