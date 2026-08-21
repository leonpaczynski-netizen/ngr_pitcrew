# The Leon Playbook — GT7 Physics Translated Into Your Driving Style

**The master working document.** Everything else in this knowledge base is reference material. This is the file that says *what to actually do*, for you specifically, on GT7's actual physics.

**Context assumed:** custom league, **no BoP, open garage tuning**, mixed sprint and multi-stop formats across a season, Fanatec DD Extreme + ClubSport V3 load cell, sometimes running no ABS.

> **Updated 10 Aug 2026 — this file now contains measured results, not just synthesis.** Two tests on the Huracán at Laguna Seca produced the first ✅ **[MEASURED]** entries in the knowledge base, and both **overturned guidance that appears in this document**. They are folded into A5, C3, D3, E2 and G below. Where a measured result and a sourced claim disagree, **the measurement wins.**

---

# 🔴 STATUS, 21 AUGUST 2026 — THIS FILE IS MID-REVALIDATION

**GT7 v1.71 (20 Aug 2026) is a physics update, and it is the largest since 1.49.** Full changelog and work order: **`16-update-1.71-physics-change.md`**.

**The body of this document was written against v1.70.** Read it with that in mind, and read `16` §12 first — Job 0 takes two minutes and tells you whether the tunes in your garage even survived the patch.

## What survived and what did not

**Survived — this is most of the file, and it is the reason the playbook is the working document:**

- **Part A's structure.** The seven divergences are statements about *where your instincts and GT7 differ*. Some of the specific divergences need re-checking; the discipline of looking for them does not.
- **A4's central translation** — LSD braking sensitivity is your entire off-throttle rear-stability toolkit, because GT7 has no engine-braking map, no brake pressure and no preload in Nm. **Still true. Still the most important line in this document.**
- **The rear-stability stack (A4), the change hierarchy, and F1's session sequence.** Method, not numbers.
- **F2's four diagnostic questions.** These diagnosed the Laguna case to a single slider with no telemetry. They work on any version of any sim.
- **The measurement discipline in Part G**, and its meta-lesson: both in-house measurements overturned something this document asserted with confidence. **That lesson just got a third confirmation from a direction nobody planned for — the game changed underneath the measurements.**

**Did not survive, or is unverified:**

- **B1's baseline sheet.** Built on v1.70 slider ranges. 1.71 revised adjustment ranges for suspension, differential and aero. **Do not issue B1 as absolute numbers until `11-car-slider-ranges.md` is re-read** (15 minutes, `16` §12 Job 1).
- **A1's camber rule.** 1.71 reworked per-car steering geometry — the model that produces GT7's anomalous camber behaviour. **A1 may now be wrong in either direction.** Highest-priority re-test.
- **A7's ride-height-first rule for kerbs and bumps.** 1.71 changed damper attenuation and revised suspension defaults. Whether the 1.49 arch-rub problem survived is [UNKNOWN].
- **A5.1 and D3.1 — the accel-14 finding.** Measured on v1.70, and 1.71 introduced a new engine torque control map, which changes the torque that finding responds to. **Re-test before reusing 14.**
- **C3.1's wear measurement.** A v1.70 number. Historical, and still the correct method.
- **Everything in Part E about how the three cars behave.** Steering geometry was reworked *per car*, so the three may have moved differently from each other.
- **D2's PP table.** The free/costs split should survive as a mechanism; PP was recalculated fleet-wide, so the numbers have not.

## What to do first

**Do not build a setup yet.** Run `16` §12 in order:

| | | Time |
|---|---|---|
| **Job 0** | Did the saved tunes survive? Read the settings screen against the archived sheet **before touching anything**. | 2 min |
| **Job 1** | Re-read the slider register, all three cars. **Blocks every sheet.** | 15 min |
| **Job 7a** | Confirm the wheel. FFB, understeer vibration and Fanatec Auto Setup all changed — on an 18 Nm DD that reads exactly like a grip change. | 5 min |
| **⭐ Job 2A** | **The Monza RSR control run** — 10 laps, Racing Hard, 8× / 3×, **short-shifted on the app's beep**, against ~200 laps of pre-1.71 data. **Your own proposal, and it is the strongest measurement available.** | 30 min |
| **Job 2** | The Huracán tyre stint at Watkins Glen. | 30 min |

**That is about ninety minutes, and it rebuilds the foundation this document stands on.**

**And then apply C3.1's corollary to the whole programme:** every defensive setting on the sheet should be able to name the measured limit it is protecting against. **Right now none of them can, because none of the limits have been measured on this version.** So build the car you can drive, leave the tyre-saving budget unspent, and go and measure.

---

## PART A — The seven things GT7 does that your instincts don't expect

These are the places where your dossier's engineering language and GT7's actual model diverge. Each one is a trap you can fall into by reasoning correctly from real-world engineering.

### A1. Camber does NOT give you turn-in. It is a mid-corner tool, and GT7 over-punishes it.

> **⚠️⚠️ 1.71 PUTS THIS WHOLE ITEM IN QUESTION.** The update notes say: *"The steering geometry for each car has been optimised, improving the simulation of turning forces."* **Steering geometry is precisely the model that governs how steer angle and suspension travel convert into slip angle and camber gain — which is the mechanism behind everything below.**
>
> If GT7 still over-punishes camber, A1 stands unchanged. If the geometry rework fixed it, **A1 is now backwards and you have been leaving mid-corner grip on the table.** Either outcome is a big result. `16` §12 Job 5 is a ten-minute A/B at 0.5 / 1.5 / 2.5 front camber, and it should be run before any camber value is issued on v1.71.

Your profile's number-one demand is **immediate front response**. The natural real-world reach for that is front camber. **In GT7 that is the wrong lever and it actively costs you the thing you care about most.** *(v1.70 statement.)*

- GT7 front camber affects **mid-corner**, not turn-in. This was publicly corrected on GTPlanet against guides that imported turn-in behaviour from other sims.
- GT7 penalises negative camber far more than reality does — it gives up **longitudinal** grip fast. More camber = **worse braking and worse traction**. For a driver whose primary weapon is "hard, accurate braking plus deep progressive trail release," that is a direct tax on your strength.
- Old RSR/Huracán community tunes run **−3.0°**. Modern post-1.49 baselines run **−1.0 to −2.0° front, −1.0 to −1.5° rear**.

**Rule for you: front camber 1.0–1.5° as the starting point, and treat every increase as a braking-performance debit.** Sweep it properly with the Data Logger rather than assuming. **⭐ And on v1.71, sweep it before assuming even the direction.**

> **⚠️ Caution added 10 Aug 2026 — the other failure mode.** Camber also gets set low *defensively*, to protect a tyre-wear budget. When that budget turns out to be bigger than modelled (see C3), the low camber is unpaid-for lap time. The Laguna Huracán ran 1.0°/1.0° against a wear limit that proved ~1.8× softer than predicted. **After any wear measurement that beats the model, re-open camber.** It is the setting most likely to have been over-protected.
>
> **⭐ 21 Aug — and now camber is exposed from both ends at once:** the wear budget it was protecting is unmeasured on this version, *and* the geometry model that made it expensive was reworked. **It is simultaneously the most over-constrained setting on the sheet and the cheapest one to test.** Job 5.

### A2. Turn-in in GT7 is owned by front toe, front compression damping, brake balance and front ARB.

That is the real toolkit for your non-negotiable #1. Ranked for you:

1. **Front compression damping LOWER** (−2 to −4). Lets load transfer forward faster → more front bite exactly at the moment of turn-in. The most underrated front-response tool in GT7 and it costs nothing elsewhere. **⚠️ 1.71 changed damper attenuation characteristics — "stance changes" is exactly this. Re-verify that the lever still works this way, and check the 20–40 window is still 20–40.**
2. **Front ARB softer −1.** More front grip, but note it acts mid-corner, not at the instant of turn-in.
3. **Front toe** — but see A3, this needs testing, not assuming.
4. **Brake balance rearward** — but you have explicitly rejected leaning on brake bias, so this stays a trim. **⚠️ 1.71 adjusted ABS slip-ratio control and cornering brake behaviour.**

> **⚠️ None of these is the answer to a *power-on* mid-corner push.** That is an accel-LSD problem (A5), and reaching for this list because it ranks higher in your change hierarchy will mask the cause while costing you roll control or entry stability. This is not hypothetical — it was the exact trap avoided at Laguna, and pre-registered and avoided again at Monza. See A5.

### A3. Front toe behaviour in GT7 is genuinely disputed — possibly inverted. You must A/B it per car.

Your profile says "mild front toe-out is generally compatible with the desired initial response," and your Fuji RSR test moved front toe −0.10 → −0.15 with a good result. **Keep the empirical result; distrust the mechanism.**

- **Position A (a well-supported GTPlanet thread):** in GT7, front toe-**out** promotes *understeer/stability* — the opposite of real life.
- **Position B (praiano63, the most widely-used GT7 tuner):** front toe-out gives *more instant reaction to wheel input on entry* — conventional.
- Both agree on one thing: **front toe-in makes the front lazier and the car steadier.** Since "lazy front" is your single most-hated trait, that at least is a firm rule — **do not run front toe-in on your cars.**

**Protocol:** on every new car, before building anything else, run **−0.05 / 0.00 / +0.05** front toe, three clean laps each, and record which gives you the initial bite. It costs 15 minutes and prevents building an entire setup on a false premise.

⚠️ **Still outstanding on the Huracán as of 21 Aug 2026 — now for the fourth session running.** It remains the highest-value 15 minutes available on the car you are actually racing.

> **⭐ And 1.71 makes it more interesting rather than less.** Toe sensitivity is downstream of steering geometry, which was just reworked per car. **A genuinely disputed parameter has just been re-rolled.** If the dispute was an artefact of the old geometry model, this test may finally give a clean answer. Run it in the same session as the camber A/B (Job 5) — same car, same track, same conditions, and both are ten minutes.

Also note: **front toe beyond roughly ±0.05° introduces steering oscillation at speed on some cars.** And note the range is **±1.00°**, not ±0.50° — `11` measured it — **so re-confirm the range on v1.71 before converting any percentage.**

### A4. Your "fix the rear mechanically, not with brake bias" rule has a specific GT7 name: **LSD braking sensitivity.**

This is the most important single translation in this document. **And it survives 1.71 intact — it is a statement about what GT7 does and does not expose, not about a physics value.**

GT7 has **no engine-braking map**. It has no brake pressure, no brake ducts, no differential preload in Nm. That means:

> **LSD braking sensitivity IS your entire off-throttle and on-brake rear-stability toolkit**, alongside rear toe and rear damping.

Your Watkins Glen Shelby session — rear locking with no ABS, brake bias forward rejected as a solution — is precisely the problem LSD braking sensitivity exists to solve. Raising it **+5 to +15** is the single most effective structural fix for entry instability and lift-off snap in GT7.

The catch: **braking sensitivity that is too high makes the car refuse to turn in on the brakes.** For a deep trail-braker that is the failure mode on the other side. So this parameter is your primary tuning axis, worked in **2-point steps**.

> **⭐ 1.71 note, and it could be significant.** The diff's adjustment range was revised, and **[COMMUNITY — single source]** one player reports the Fully Customisable Diff can now be set to **0/0/0**, which was never previously possible. The scale in this document is 5–60 throughout.
>
> **If the floor really is 0, your primary tuning axis just got longer at the end you use least — and a genuinely open diff on the overrun would be a larger rotation source than anything in A4 or C1.** It also means the *quali* end of the LSD scale has territory nobody has explored. **Confirm it on the settings screen (Job 1) before it changes anything.** One person, two days after release.

**The rear-stability stack, in your hierarchy order:**

| Priority | Lever | Direction | Notes |
|---|---|---|---|
| 1 | **LSD braking sensitivity** | **Higher** +2 at a time | The main event. Stop when turn-in starts to dull. |
| 2 | **Rear expansion (rebound) damping** | **Lower** −2 to −4 | A rear that extends too fast on lift unloads abruptly. Counter-intuitive but correct. ⚠️ *1.71 damper rework* |
| 3 | **Rear toe-in** | +0.05 to +0.10 | Cheap, effective, costs top speed and tyre life. Trim, not foundation. |
| 4 | **Front compression damping** | Higher +2 to +4 | Reduces the pitch-forward spike. Conflicts with A2 — this is the real tension in your setup. ⚠️ *1.71 damper rework* |
| 5 | **Reduce rake** toward level | −2 to −3 mm | Positive rake promotes entry rotation. |
| 6 | **Rear ARB softer** −1 | More rear grip mid-corner | |
| 7 | Brake bias forward | Last resort | You've ruled this out as a permanent answer. Agreed. |

**Note the tension at #4.** Front compression damping is simultaneously your best turn-in tool (lower) and a rear-stability tool (higher). That conflict *is* your setup problem in one line. Resolve it by taking rear stability from #1–#3 (which don't touch the front) and keeping front compression **low** for bite.

**Validated in practice, and now twice.** The Laguna Huracán ran **LSD braking 26** (up from the MR baseline of 20) with **brake balance at 0**, against a heavy downhill stop taken while turning in, on ABS Weak, in a high-yaw-inertia car — no entry-stability complaint across the test programme. The **RSR at Monza** ran **braking 24 at bias 0** across the three heaviest stops in Gr.3, also without complaint. **The stack works — the rear can be stabilised without moving bias forward.** ⚠️ *Both v1.70, and 1.71 adjusted ABS cornering brake behaviour, which is the phase this solves for. Re-establish early — it is one of this document's central claims.*

### A5. A heavily locked diff breaks away as a unit — and it also pushes. Run acceleration sensitivity LOW.

**[SINGLE SOURCE — verified as such, see caveat]** One well-regarded GT7 guide describes the breakaway behaviour directly:

> *"When you break traction with higher locking numbers, the transition from having grip to losing grip with BOTH rear tires is quite a sharp loss of traction."*

> **⚠️ Caveat from verification.** Only one source states this, and no other GT7 LSD reference corroborates it. More importantly, **this is not a GT7 anomaly** — a heavily locked diff approaches a spool, and a spool axle breaks away as a unit in every sim and in reality. Treat it as ordinary diff physics, which happens to matter a lot to you because progressive exit traction is a non-negotiable.
>
> **⭐ And because it is ordinary physics rather than a GT7 quirk, it is the part of A5 most likely to have survived 1.71 untouched.** The *values* below are the exposed part.

**Rule for you: run acceleration sensitivity LOW and prove you need more.** Modern MR baseline is **15**; FR is **25**. Your Fuji RSR change of accel **25 → 20** was moving in the correct direction and matched to the correct symptom.

**Diagnosis before adjustment** — the GT7-specific test:

- **Inside rear wheel lights up alone on exit** → accel sensitivity is too LOW → raise it.
- **Both rears let go together, feels like a snap** → accel sensitivity is too HIGH → lower it.
- **The car pushes wide mid-corner *while you are on throttle*** → accel sensitivity is too HIGH → lower it. **This is the third failure mode and it is the one that caught us out.**

Watch the on-screen tyre indicators to tell the first two apart. Do not guess. **This diagnostic is symptom-based and version-independent — it still works.**

#### ✅ A5.1 — MEASURED, 10 Aug 2026: the MR baseline of 15 is a ceiling on a restricted build

**⚠️ v1.70 result. See the re-test note at the end.**

**Huracán GT3, Laguna Seca, 525 bhp / 1300 kg, restrictor 70 / ECU 97, TCS 0, ABS Weak.**

Accel sensitivity was set to **18** — chosen by splitting the difference between the MR baseline (15) and generic Laguna guidance calling for **20–28** to protect the T11 traction exit. The result was **power-on mid-corner understeer through T2–T5, present from lap 1, cold and hot.** Notably **T11 — the corner 18 was aimed at — did not complain.**

**Accel 18 → 14 resolved it completely.** Driver: *"lsd change sorted it perfect."*

**Four things to carry forward:**

1. **On a restricted build, start BELOW the layout baseline, not above it.** A power restrictor cuts top-end while largely preserving low-end torque, so a restricted car delivers proportionally **more** torque in the early corner-exit phase than its headline power implies. More early torque through a locked diff is the direct recipe for power-on push. **Every published tune is an unrestricted max-PP build and none of them account for this.**
2. **Re-test accel sensitivity whenever you move the restrictor.** They are coupled. See D3.
3. **Never import a track's generic diff guidance without checking the build it assumes.** Track norms are written for cars with a different torque curve to yours.
4. **The corner that is NOT complaining is diagnostic.** T11's silence localised the fault in one step: the value was correct where it was aimed and wrong everywhere else. **Ask which corners are fine, every time.**

**And the restraint that paid:** front ARB 5→4 and front downforce 425→450 were both queued as fallbacks. Neither was needed. Both would have "fixed" a power-on symptom by adding front grip — masking the cause while giving up roll control or entry stability. **Diagnose, then adjust.**

> **✅ Independently confirmed at Monza, on a different car.** The RSR reported *"will not hold line on maintenance throttle"* — the same third failure mode — and the temperature signature settled it: the **outside rear ran 11 °C hotter than the front-left while the inside front sat coldest on the car**, which is a car being dragged round on its rear axle rather than steered on its front. **Accel 16 → 14**, and Rev A had pre-registered exactly that branch. *(`setups/2026-08-12-rsr-monza-revB.md` §2.1.)* **Two cars, two circuits, same diagnosis, same direction.**

> **⚠️⚠️ 21 Aug 2026 — re-test 14 before reusing it. Two independent reasons.** **1.71 introduced a new engine torque control map** (citing improved partial-throttle speed control), and this finding is entirely an argument about torque *shape*; and **the diff's adjustment range was revised**, possibly flooring at 0 instead of 5, which is a finding about the bottom of the range.
>
> **All four conclusions above survive** — they are about method, about restricted builds, and about diagnosis. **The number 14 does not.** Add a fifth: **re-test accel sensitivity after a physics update, not only after a restrictor change.**

### A6. The single biggest fix for your wheelspin is not the diff. It is 1st, 2nd and 3rd gear.

Your Fuji telemetry recorded **22 wheelspin events in one lap** on the RSR. Your dossier already identifies 2nd as "the traction-control gear." GT7 backs this hard:

> **Lengthening 1st/2nd/3rd is the #1 ranked fix for exit traction limitation in GT7, ahead of every LSD and suspension change** — and it is massively underused.

And here is why this matters enormously in *your* league specifically:

> **Gear ratios, brake balance and the entire suspension sheet cost ZERO PP.** Under a no-BoP PP-capped ruleset, all of your chassis and gearbox tuning is free performance. Aero, power, weight and tyres cost PP. Nothing else does. **⚠️ The mechanism should survive 1.71; the PP numbers were recalculated fleet-wide — see D2.**

**Gearbox procedure (order matters, this is the #1 GT7 gearbox error):**

1. **Maximum Speed slider FIRST.** It is a *generator*, not a trim — touching it wipes every individual ratio you have set. Never touch it again after step 3.
2. **Final drive** to scale the whole set.
3. **Individual ratios.** Set 1st from the slowest corner, not from launch. Lengthen the lower gears deliberately.
4. **Validate against actual pull, not a target number.** Your Fuji note — 271 km/h actual vs a 300 km/h nominal target — is the correct methodology: *gear to the speed you actually reach at the end of the straight with tow, then check which gear you're in at every corner exit.*
5. Space with **diminishing increments**.
6. **Re-gear after any aero or power change.**

> **⭐ Add a seventh step for 1.71: re-gear after the patch, full stop.** *"Road surface resistance (rolling resistance) has been optimised"* moves terminal speed independently of drag and power. **Step 4's methodology — gear to the speed you actually reach — is exactly the right response and needs no change.** It is the *targets* that are stale, not the method.
>
> **Three gearing constants are now all reopened at once:** the Huracán's K (never closed — 1112.6 vs 1092.5, 1.8 % apart), the **RSR's K = 1,128 with a measured limiter of 8,600 rpm**, and the Shelby's K = 1,096. **One lap each — hold a gear to the limiter on a long straight and read the speed. The RSR's re-take happens for free inside the Monza control run's full-RPM tail laps.**

> **One nuance from Laguna:** the long-lower-gears argument is weaker on a soft compound than on a hard one, because more rear grip means less wheelspin for a given gear. If a lengthened 2nd feels lazy out of a slow corner on Softs, shortening it a click is a legitimate option rather than a trap.

### A7. Post-1.49, kerb and bump problems are a RIDE HEIGHT problem, not a damper problem.

> **⚠️⚠️ 1.71 is the most plausible candidate yet for changing this, and it is the one item in Part A where being wrong is dangerous rather than just slow.** The update changed **damper attenuation characteristics** ("stance changes and road surface tracking") and revised **initial suspension settings and adjustment ranges**. Those are the two things this item is about.
>
> **Status: [UNKNOWN]. Do not assume the arch-rub problem is fixed; do not assume it is unchanged.** `00-INDEX`'s Settled Facts entry has been annotated accordingly. **The trigger remains the driver symptom or a four-wheel mean-heave figure — never the Pit Crew `bottoming` flag (Standing Rule 8, and the reason that rule exists cost us 5 mm of ride height for nothing).**
>
> `04` §8 Test 3 is the honest way to find out: quali-minimum ride height, one lap on a full tank, note bottoming and instability, raise the rear 3 mm, repeat.

*(v1.70 statements below.)*

- 1.49 caused widespread bottoming and — critically — **wheel-arch contact that can physically prevent the car from steering.** A car that abruptly refuses to turn after a kerb or a compression is almost always arch rub, not a balance problem.
- **Ride heights went up permanently.** Setting both ends to minimum on principle is now actively slow.
- **Dampers do less than they used to.** If a 4-point damper change does nothing, that is now normal. **⚠️ This is the specific claim 1.71's damper rework most directly targets — "to make stance changes and road surface tracking feel more natural" reads like a response to exactly this complaint. If dampers do more now, A7's ordering changes.**

**Kerb/bump fix order for you:**

1. **Raise ride height 3–5 mm** at the affected end. Always first now.
2. Reduce compression damping toward the bottom of its window (30 → 25).
3. Reduce expansion damping (40 → 35) — a slow-rebounding damper *packs down* over successive kerb strikes.
4. **Soften ARBs −1 to −2 both ends.**
5. Soften natural frequency 1–2 clicks.
6. Reduce camber.

**Diagnostic distinction that saves you a session:**

| Symptom | Cause | Fix |
|---|---|---|
| Hops once and settles | Too stiff | Springs and ARBs |
| Bounces repeatedly for 1–3 seconds | Frequency mismatch | Large NF change (±0.3 Hz), **not** small damper tweaks |
| Bangs, then won't steer | **Arch contact** | Ride height only. Nothing else works. |

**This table is symptom-based and is the part of A7 most likely to survive** — the three symptoms are physically distinct regardless of what the damper model does. **The ordering of the fix list above it is the exposed part.**

> **✅ And the table has been used in anger, successfully.** The RSR at Monza reported *"bounces repeatedly after a kerb"* — the middle row, cleanly — which **overrode a queued ride-height change that would have been the wrong branch.** The fix was a −0.30 Hz natural-frequency change at both ends, not dampers and not ride height. *(`setups/2026-08-12-rsr-monza-revB.md` §2.2.)* **This is why the playbook carries a three-row table instead of a single "kerbs → raise the car" rule.**

---

## PART B — Your baseline philosophy, expressed in GT7 sliders

> **🔴 B1 IS THE MOST VERSION-EXPOSED SECTION IN THIS DOCUMENT.** It is a sheet of absolute numbers and percentages built against v1.70 slider ranges, and 1.71 revised the adjustment ranges for suspension, differential and aerodynamics.
>
> **Do not issue B1 as numbers until `11-car-slider-ranges.md` is re-read** — 15 minutes, `16` §12 Job 1. Until then it is a statement of *philosophy* (low camber, low initial torque, front compression low, brake balance neutral), and the philosophy is still yours.
>
> **And note the specific trap this file has already fallen into twice**, both recorded in `11`: a heuristic that doesn't declare whether it is absolute or proportional changes meaning silently when it crosses a class boundary. **A moved range does the same thing without crossing anything.** The ride-height row below is stated in *clicks* and is the known-broken one — `11` caught it meaning 20% of range on a Gr.3 car and 6% on the Shelby. **Rewrite it as percent of range when the new ranges arrive.**

### B1. The starting sheet

| Parameter | Your starting value | Why, for you |
|---|---|---|
| **Ride height F** | 3–5 clicks above car minimum ⚠️ *known broken — state as % of range* | Never minimum. Post-1.49 arch rub is real and it kills the front response you need. |
| **Ride height R** | 5–8 clicks above minimum ⚠️ *same* | Mild positive rake. Rake is a mechanical effect in GT7, **not** an aero one. |
| **Natural frequency** | Racing tyres ~70–80% of slider, **rear ≥ front** ⚠️ *known broken on Gr.3 — anchor in absolute Hz* | Softer front + stiffer rear = rotation with a stable platform. `11` caught this putting a Gr.3 car at 4.4–4.6 Hz. |
| **ARB F/R** | MR: **6 / 3–4** · FR: **6 / 4** | Front stiffer to control roll, rear soft to protect rear grip. Then soften front one step when you want more front bite — your proven move. |
| **Damper compression F/R** | **28 / 30** | Front deliberately at the low end for turn-in bite (A2). ⚠️ *1.71 damper rework; window may have moved* |
| **Damper expansion F/R** | **40 / 38** | Rear expansion low-ish for lift-off stability (A4 #2). Expansion should exceed compression. ⚠️ *same* |
| **Camber F/R** | **1.2 / 1.2** | Low. GT7 taxes camber against braking and traction — your two strengths. **But don't go lower than this defensively without a measured wear reason (A1).** ⚠️ **Suspended pending the Job 5 A/B — 1.71 reworked steering geometry.** |
| **Toe F** | **0.00**, then A/B ±0.05 | Never toe-**in**. Beyond that, test — do not assume (A3). |
| **Toe R** | **+0.05 to +0.10** | Mild rear toe-in. Your recurring stabiliser. Keep it small. |
| **LSD initial torque** | **5–8** | Low. High preload is a silent cause of the persistent mid-corner push you hate. ⚠️ **Floor may now be 0 rather than 5 — confirm (A4).** |
| **LSD acceleration** | MR **15** · FR **25** · **restricted MR: start at 14** | Low, and prove you need more (A5). ✅ The restricted-MR figure is measured — ⚠️ **on v1.70, against the old torque map. Re-test.** |
| **LSD braking** | MR **20** · FR **10**, then walk up +2 | Your primary rear-stability axis (A4). |
| **Brake balance** | **0 (neutral)** | Per your explicit preference. A trim, applied last. **The −5…+5 range and the sign convention are settled and unaffected.** |
| **Downforce** | Max front, then trim rear until high-speed balance is right | And **never trim rear first for top speed.** ⚠️ *1.71 revised aero defaults and ranges on race cars* |
| **TCS** | **0** for quali, **1** for race | TCS 1 costs near-nothing and catches the worst exits. If you need TCS 3+, the diff or gearing is wrong. **On a soft compound over a short stint the case for race TCS is weaker — reassess per event.** ⚠️ **1.71 "optimised" TCS intervention behaviour. The v1.70 price was up to two tenths per corner; the new price is unknown (`16` §12 Job 7).** |
| **ABS** | **Weak** | See B3. ⚠️ **1.71 adjusted ABS slip-ratio control and cornering brake behaviour.** |

### B2. Where the ARB numbers came from, and why your Fuji move was right

Your tested Fuji change — **front ARB 5→4, front toe −0.10→−0.15, LSD accel 25→20, rear toe 0.20→0.25** — is a near-perfect worked example, because it addressed entry/mid understeer *and* loose throttle exit simultaneously without touching brake bias:

- Front ARB softer → more front mid-corner grip
- Front toe more out → more entry bite (correct *for that car*, empirically validated)
- LSD accel down → frees rotation under power and reduces the both-wheels-let-go snap
- Rear toe in → rear exit security to pay for the freed diff

One flag: **rear toe 0.25 is fairly large by GT7 standards.** It is the biggest alignment contributor to tyre wear and it costs straight-line speed. Try recovering some of that stability from LSD braking sensitivity or rear expansion damping instead, and pull rear toe back toward +0.15.

> **A note on that Fuji change in light of A5.1.** It moved four things at once. It worked, so it stands — but the Laguna case shows what you get from moving **one** thing: an unambiguous causal result you can carry to the next car and the next circuit. **Four-change packages fix races; one-change tests build the knowledge base.** Use the first when you're short on time and the second whenever you aren't.
>
> **⭐ 21 Aug — and for the next few sessions, use the second almost exclusively.** With every baseline unverified, a four-change run on v1.71 is uninterpretable: you would not know which change did what, against a car whose behaviour you can no longer predict. **Standing Rule 5 is not suspended for the rebuild; it matters more during it.**

### B3. ABS, and the brake balance sign convention

- **ABS: Weak is the competitive meta on a wheel.** It exposes brake balance's real effect and shortens stopping distances versus Default, without the rear-lock exposure of Off.
- **Update 1.55 (Jan 2025) changed ABS and TCS intervention strength.** Any brake-balance intuition formed before that is suspect.
- **⭐ Update 1.71 (Aug 2026) changed both again:** *"The behaviour of the Traction Control (TCS) assist intervention has been optimised"* and *"The slip ratio control and cornering brake behaviour under ABS has been adjusted."* **Any brake-balance intuition formed before 20 August 2026 is now suspect in exactly the same way.** The "cornering brake behaviour" line names the trail-braking phase directly, which is your primary technique — this is a change you should expect to *feel*.

**Brake balance sign convention — settled, and unaffected by 1.71.** **Negative = more FRONT bias. Positive = more REAR bias.** Three independent sources state the sign and all three agree; I looked specifically for a source asserting the opposite and found none. Two caveats:

- The value is a **delta from each car's own factory bias**, not an absolute F/R percentage. "Start at neutral" means *start at that car's neutral*.
- One published RSR tune runs **−3**. On the corrected convention that is **notably front-biased**. Do not adopt it. Start at 0.

> **⭐ And one hardware note that belongs here, because it will otherwise be misdiagnosed as a brake problem.** 1.71 adjusted **steering wheel force feedback and understeer vibration**, and optimised **Fanatec Auto Setup parameters**. On an 18 Nm DD Extreme that is a change you will feel immediately. **Before diagnosing anything about grip or balance on your first 1.71 session, confirm the wheel settings are where you left them and consciously separate "the wheel feels different" from "the car has less grip."** They are easy to confuse and expensive to confuse. F1 step 0 already covers this — do not skip it this time.

---

## PART C — Race vs qualifying, in your terms

### C1. The scalar

Your Fuji RSR pair is the template:

| | Quali | Race | Delta |
|---|---|---|---|
| Ride height F/R | 55 / 59 mm | 56 / 63 mm | Race higher, more rake |
| ARB F/R | 7 / 7 | 7 / 6 | Race softer rear = more rear grip |
| Natural frequency F/R | 3.50 / 3.60 Hz | 3.35 / 3.45 Hz | Race ~0.15 Hz softer both ends |

That is a **calmer, more compliant, more rear-secure race car** — exactly right. The principle: *"the race car was intentionally calmer and less peaky for consistency and tyre protection."*

**The principle survives 1.71. The absolute values are v1.70 and sit on ranges that may have moved.**

### C2. The decision rule for a mixed-format season

| Format | Philosophy | How far to deviate from quali trim |
|---|---|---|
| **Time trial / pure hot lap** | Pure quali | 100% quali. No compromise. |
| **Sprint, no stop, <20 min** | Quali-lean | ~80% quali. Mild degradation management only. |
| **Sprint, 1 mandatory stop, 20–40 min** | Balanced, set for **mid-stint** | ~50/50. Your league's most common case. |
| **Long, multi-stop, 45+ min** | Race | Full race trim. Tyre life and fuel dominate. |
| **Endurance** | Race + fuel | Race trim plus deliberate long top gear for economy. |

**The mid-stint principle:** set the car up so it is neither undriveable on lap 1 with full fuel nor sluggish at the end of the stint.

> **⚠️ Sanity-check the format before applying the scalar.** The table assumes tyre life is the thing being protected. At Laguna the measured stint length made tyres a non-issue and **fuel** the binding constraint — which puts the event nearer the "sprint" column than its 20-lap length suggests. **Classify the event by what actually binds, not by its duration.**
>
> **⭐ 21 Aug — and on v1.71 you cannot classify the event at all until you have measured a stint**, because you do not know what binds. **That is the argument for running the measurements before the next race weekend, not after it.** Also add `04` §5.1's temporary fifth input: **+0.1 on the λ scalar for the first two or three outings on unfamiliar physics**, on the asymmetry argument — too conservative costs hundredths, too aggressive costs a race.

### C3. Tyre wear is the dominant race variable — but check *how* dominant before you pay for it

> **⚠️ Every post-1.49 fact below is a v1.70 fact. 1.71 rewrote the slipping regime, adjusted tyre heating and wear values, and optimised rolling resistance. See `03`'s exposure banner.**

Post-1.49 facts that should change how you drive a race stint:

- **Lateral slip is the dominant wear source.** *"If you can hear the tyres, you are paying for it."* Audible squeal is free telemetry. **⚠️ This is the claim 1.71 most directly re-opened — the update focuses on the slipping simulation specifically.**
- **Tyres fall off a cliff past ~50% wear — worth over a second per lap.** **⚠️ Whether the cliff survived is unknown.**
- **Trail braking's wear cost went up.** 1.49 increased oversteer sensitivity to trail braking. **Trail braking is still the fast technique** — but in a high-multiplier stint, shortening the trail phase is a legitimate ~0.1 s/lap trade for real tyre life.
- **Short-shifting cost ~0.5 s/lap and cut fuel consumption 20%** — and reduces rear tyre wear as a side effect. A genuine double win for high-multiplier rounds. **This is the technique that won the 17 Aug Watkins Glen race, via the Pit Crew shift beep, and it dropped that circuit's worst corner from 1.57 s lost to 101 ms with no setup change at all. ⚠️ 1.71 introduced a new engine torque control map — re-check the shift points.**

#### ✅ C3.1 — MEASURED, 10 Aug 2026: our wear estimates were 1.8× too pessimistic

**⚠️ v1.70 result. Historical, and still the correct method. Do not plan a compound choice on it.**

**Huracán GT3, Laguna Seca, Racing Soft, 2× tyre wear, race pace from full fuel: ~11–12 laps before fall-off** (22–24 laps of 1× wear).

The pre-test model predicted 6–7 real laps. **The measured Soft roughly equalled the modelled Hard — an error of about two compound grades.**

**What went wrong, and what to stop doing:**

1. **An invented elevation penalty.** The estimate added wear because Laguna has 55 m of climb and "vertical load cycling" seemed likely to matter. Plausible physics, **zero supporting evidence.** **Withdrawn.** Do not apply it at Bathurst or Sainte-Croix either.
2. **Pessimistic generic base rates.** Generic "Gr.3 at circuit X" wear figures are not reliable for a specific car — the reference material itself notes that **car-to-car variation rivals compound-to-compound variation.**
3. **A reputation treated as a number.** The Huracán's "2nd worst in the MR field" ranking is from a 2019 GT Sport test at 10× on Hards. It is *relative*, *stale*, and at different settings. It was being used as if it were an absolute stint length.

**The consequences, and they were expensive:**

- The race was built around **Racing Hards** it did not need. The measured RS→RH delta **at Laguna specifically** is **1.412 s/lap** — over 20 laps that is roughly **28 seconds, more than a full pit stop.**
- Camber, rear platform, rear aero and the diff were all set conservatively to protect a budget that was nearly twice as large as assumed.

> **✅ And it happened again at Monza, worse.** The RSR ran **15 laps on Racing Hards at 8× with no measurable lap-time loss** — gauge and stopwatch agreeing, true degradation ~9 ms/lap. **The knowledge-base model predicted 2.5–3.1 laps: a 5× miss**, against Laguna's 1.8×. Same failure mode. *(`setups/2026-08-12-rsr-monza-revB.md` §5.1.)* **Two cars, two circuits, both times the model was pessimistic and both times it cost real strategy.**

**The standing rule:**

> **No modelled wear figure may be used to select a race compound. Measure one stint at the multiplier you will actually race, then choose.** One practice run. The alternative is racing a compound a second a lap slower than necessary for the whole event.
>
> **⭐ 21 Aug extension: "no modelled figure" now includes every measured figure taken on a previous version of the game — including both of ours.** Failure mode 3 above was *a reputation treated as a number*. **A stale measurement treated as current is the same error with better provenance.**

**And the corollary, which is the part that generalises past tyres:** durability you don't consume is pace you paid for and threw away. **Every defensive setting on the sheet — low camber, soft platform, conservative diff, TCS — should be able to name the measured limit it is protecting against.** If it can't, test it.

> **⭐ Apply that corollary honestly right now and the answer is uncomfortable: on v1.71, not one setting on the sheet can name a measured limit.** So the instruction is: **build the car you can drive, leave the tyre-saving budget unspent, and go and measure.** Do not carry forward v1.70's conservatism on faith — it was wrong by 1.8× the last time it was checked, and by 5× the time before.

### C4. Multipliers — how to calibrate your league

**Multipliers are believed to be simple linear rate scalars** — at multiplier N, each lap counts as N laps of wear. Stint length ∝ 1/N.

> **⚠️ [ASSUMED — widely used, never tested]** Verification downgraded this. The evidence is two informal forum statements and one calibration method that *assumes* linearity rather than demonstrating it. **Note that `03-gt7-tyre-and-fuel-model.md` §4.1 tags the same claim [CONFIRMED] — that tag overstates the evidence and this file's reading should win.** Nobody reports it failing, so act on it — but **calibrate at the multiplier you will actually race**, not at 50×.
>
> **⭐ 1.71 note: the multiplier *mechanism* scales a rate and is unlikely to have been touched. The rate it scales did change.** So this item is unchanged in status — still assumed, still untested — while every number it has ever been applied to is now stale.

**Does C3.1 settle it?** No. A single-multiplier measurement cannot distinguish "base rate lower than modelled" from "2× is gentler than linear." **Both remain live**, and running the same car/track/compound at 2× and 4× would settle it in under an hour. Promoted to the backlog (G5).

**One thing C3.1 does establish: 2× is a much gentler multiplier than it sounds.** It gave 11–12 laps on the *softest* compound on a car with a bad wear reputation. **Treat 2× as barely strategic, not demanding.** ⚠️ **On v1.70. If 1.71 made wear faster, this conclusion inverts — and it is the sort of conclusion that quietly sets a league's whole calendar.**

**Polyphony's own design pattern** is the best calibration reference: **4×–8× tyre with 2×–3× fuel over 10–15 laps forces exactly one stop.** Tyre wear is deliberately scaled ~2× harder than fuel.

> **⭐ And this is the cheapest free calibration available right now.** PD will re-tune their Daily Race multipliers to the new wear model. **Watch the first few post-1.71 Daily Race configurations** — if the multipliers drop at similar lap counts, wear got faster; if they rise, slower. It costs nothing to read and it is a direct signal from the people who have the source code.

> **Our 20-lap Laguna event inverts that ratio** — 2× tyre against 3× fuel. The measured outcome confirms the consequence: tyres cover the race comfortably and **fuel is the binding constraint**, which sets everyone's stop window to the same lap and produces convoy racing. Worth raising with whoever sets the multipliers.

**⚠️ If your league's multipliers were set before July 2024, they may be producing more stops than intended.** One benchmark: *"I could do an entire Spa 1 hour race on a single set of RH… now they just last 1 stint of 8 laps."* ⚠️ That claim sits awkwardly beside C3.1 — **another reason to measure rather than infer.** **⭐ And the same warning now applies to any multiplier set before 20 August 2026, which is all of them.**

**Road cars are disproportionately punished post-1.49** — use roughly half the multiplier for road-car classes as for Gr.3/Gr.4. *(Relevant to the Shelby programme; unverified on 1.71.)*

---

## PART D — Your no-BoP, open-tuning league

### D1. The single most important fact

> **There is no closed-form PP formula, and there almost certainly cannot be one.** PP is the output of an internal *physics simulation*. The proof: after 1.49 changed the physics engine, some cars returned **no PP value at all** — a warning triangle. An arithmetic formula cannot fail to compute; a simulation can fail to converge.

Practical consequence: **you cannot calculate your way to an optimal build. You have to test.** But you can exploit the structure:

> **⭐ 21 Aug — and D1 just predicted 1.71 correctly, which is a good sign for the reasoning.** If PP is the output of a physics simulation, then **changing the physics necessarily changes PP** — and that is exactly what happened: PD recalculated Performance Points across the fleet as a direct consequence of the physics work. **This is not a rebalance PD chose; it is a side effect they had to absorb.** Fourth time since launch.
>
> **The practical consequence for a no-BoP PP-capped league is immediate and it is a race-weekend problem, not a tuning problem: your three builds may have moved relative to the cap.** Read the current PP of each car as built and compare it to the figure on its setup sheet (`16` §12 Job 4, 10 minutes). **If a build is now over the cap, you find out now or you find out at scrutineering.**

### D2. What costs PP and what doesn't

| Free (zero PP cost) | Costs PP |
|---|---|
| **Entire suspension sheet** — ride height, springs, ARBs, dampers, camber, toe | Power (all engine upgrades) |
| **All gear ratios and final drive** | Weight reduction stages |
| LSD *values* (the part costs PP; the numbers don't) | **Tyre compound** |
| Brake balance — *believed free, unverified* | **Aero downforce** |
| | Ballast |
| | *Fitting* any of the adjustable parts above |

**This is the whole game in a PP-capped league.** Your chassis and gearbox work — exactly where your engineering strength lies — is entirely free. Spend your effort there first, always.

**The free/costs *split* is a structural property of how PD account for PP and should survive 1.71. The *amounts* were all recalculated.**

> **⭐ And post-1.71 the free half is worth more than usual.** The entire community's setup knowledge went stale on 20 August — every published tune, every tier list. **Free sliders are the one axis nobody can copy from a published tune, and right now there are no current published tunes to copy from at all.**

Three precision points:

- **The distinction that trips people up: *fitting* the part costs PP; *moving the slider* afterwards does not.** Fully Customisable Suspension was measured at **+9.1 PP** on one car. **⚠️ Re-measure — Job 4.**
- **Brake balance is the one gap.** No source tests it either way. The inference that it's free is strong but it is inference.
- **Do not extend "chassis tuning is free" to aero.** Downforce is PP-affecting and **non-monotonically so** — reducing rear downforce has been reported to *raise* PP by ~10 on some cars. Always press Triangle after an aero change. **⚠️ And 1.71 revised aero defaults *and ranges* on race cars, so the non-monotonic behaviour may have a different shape now. Press Triangle more, not less.**

> **⚠️ And note that tyre compound costs PP.** If you change compound after setting a build to a cap — as happened at Laguna, going Hard → Soft — **re-read the PP number before committing.**

**Efficient PP recovery:** get under the cap using **forward-positioned ballast** (usually the largest PP reduction per kg), then spend the reclaimed points on power. PP responds to ballast **non-linearly and jumpily**.

**Two exploitable quirks:**
- **Wide body always LOWERS PP** despite improving the car.
- **Body rigidity can raise *or* lower PP** depending on what suspension is fitted. Always press Triangle and re-check.

**⚠️ Both quirks are PP-simulation behaviours and both need re-confirming on v1.71 before being exploited. They are cheap to check while doing Job 4.**

### D3. Restrictor vs ECU

Not equivalent, and the choice should follow the track:

| | Power Restrictor | ECU Output |
|---|---|---|
| Curve effect | Cuts **top-end**, largely preserves low-end torque | Scales the **entire** curve proportionally |
| Use when | Twisty/traction-limited track — keep the torque you use, pay in top speed you don't | Fast track — more predictable |

**Re-gear after either.**

> #### ✅ D3.1 — The consequence nobody writes down, confirmed 10 Aug 2026
>
> A restrictor doesn't just make the car slower — **it changes the shape of the torque delivery in a way that alters your chassis balance.** Because the restrictor cuts top-end and keeps the bottom, a restricted car has **proportionally more torque in the early corner-exit phase** than its headline power figure implies.
>
> **On an MR car with TCS 0 that means more wheelspin risk AND more power-on understeer than you would predict, despite the lower power number.** At Laguna this made an accel-LSD value of 18 — already below the track norm of 20–28 — badly too much lock, producing mid-corner push from lap 1. **14 fixed it.**
>
> **Three standing rules:**
> 1. **Re-test LSD acceleration sensitivity after every restrictor change**, alongside re-gearing. Treat them as one job.
> 2. **On a restricted build, start accel sensitivity below the layout baseline**, not at it.
> 3. **Discount published tunes further than you already do.** They are unrestricted max-PP builds; their diff numbers assume a torque curve you do not have.
>
> **⭐ 4. NEW, 21 Aug 2026 — re-test accel sensitivity after a physics update too.** 1.71 introduced a new engine torque control map. **The whole of D3.1 is an argument about torque *shape*, and PD just changed how torque is delivered.** The reasoning holds; the value 14 does not until it is re-run.
>
> **⭐ And note the confirming contrast: the Watkins Glen Huracán runs restrictor 99 — effectively unrestricted — and wants accel 18, where restricted-at-Laguna wanted 14.** *(`setups/…-revD.md` §7.)* **Removing the restrictor pushes the correct value up, exactly as D3.1 predicts.** That is the finding working in both directions, which is worth more than either measurement alone.
>
> **If you need to shed more PP: take it from the restrictor, not the ECU.** More restrictor keeps hurting only the top end you aren't using. More ECU flattens the torque you need out of slow corners — but note it also *reduces* the low-end torque bias, so an ECU-heavy build may want slightly **more** accel lock than a restrictor-heavy one at the same power. Untested; flagged as a hypothesis.

### D4. League fairness note

In open no-BoP racing, PP is a poor proxy for lap time, and certain archetypes are systematically underrated by it. If your league is capped by PP rather than by class, expect exploit cars to appear. Worth raising with your organiser before it becomes a mid-season argument — see `06-car-building-and-pp.md` §9.

> **⭐ Two things to raise with the organiser now, both of them 1.71 consequences and both better raised before a round than after one:**
>
> 1. **PP moved fleet-wide.** In a PP-capped no-BoP league that is a re-scrutineering event for every car on the grid, not just yours. Some builds will have gained headroom and some will be over.
> 2. **The new "Championship" mechanical damage setting** — Light's severity, triggered from more minor collisions, with recovery time varying by severity. **This is a genuinely good option for a league that wants to price contact without ending races**, and it did not exist before 20 August. See `16` §9.

---

## PART E — Your three cars

Full profiles in `07-car-profiles.md`. The decisions that matter.

> **⚠️ Everything in Part E describes how these cars behaved on v1.70. 1.71 reworked steering geometry *"for each car"* — which means the three may have moved differently from one another, and the comparisons between them are as exposed as the descriptions of them.** Re-establish each car's character on its first 1.71 outing before trusting any of it. **F2's four diagnostic questions are the tool for that, and they work fine on a car you no longer know.**

### E1. Porsche 911 RSR (991) '17 — your benchmark, and the car with the best baseline

- **MR, not RR** — verified, and a matter of record from GT7's own car description. **Unaffected by 1.71.** 4.0 NA flat-six, 509 bhp @ 8,100, 1,243 kg, PP 720.74 ⚠️ *(PP recalculated fleet-wide — re-read)*.
- **Post-1.49 it improved materially.** MR cars gained "massively improved stability" and now edge FR cars. Currently rated one of the best all-rounders in Gr.3 with "very few weaknesses." ⚠️ *A post-1.49, pre-1.71 assessment — and the MR-edges-FR verdict is a hypothesis again.*
- **Best tyre wear of your three cars** — balanced front-to-rear. ⚠️ *Reputation only. But see the Monza result: **15 laps on RH at 8× with ~9 ms/lap true degradation**, which is a real measurement on this car, on v1.70.*
- **Weakest straight-line speed of the three.** Cornering-precision circuits suit it (Lago Maggiore, Dragon Trail Gardens, Autopolis, Suzuka, Brands Hatch). Monza, Le Mans, Tokyo, Sardegna punish it. ⚠️ *Rolling resistance changed — terminal speeds moved.*
- **Failure mode: throttle timing, not lift timing.** It punishes throttle before the car is straightening. It is *not* an RR pendulum. **✅ Confirmed at Monza — "will not hold line on maintenance throttle", resolved by accel 16 → 14.**
- **Setup priority for you:** LSD braking sensitivity (start ~20, not the 50 the old lobby tunes use), then rear ARB / rear NF for exit rotation, then gearing to protect the most important corner exit.
- **⭐ Gearing is measured on this car and it is exemplary: K = 1,128, limiter 8,600 rpm, and 6th sitting at 98.9 % of peak-power rpm at clean-air Vmax** with 7.4 % of rev range in hand for the tow. *(`setups/2026-08-12-rsr-monza-revB.md` §3.)* ⚠️ *That ratio is precisely what rolling resistance moves — it is the first thing the Monza control run re-measures, on the full-RPM tail laps.*

> **⭐⭐ This is the car for `16` §12 Job 2A, and it is the strongest measurement in the whole protocol.** ~200 laps of pre-1.71 data at Monza gives a **distribution** — a known median and a known spread — where every other measurement in the knowledge base is n=1 with no error bar. **Monza is also the best available probe for the rolling-resistance change**, being the most drag-limited circuit in regular use, on the most straight-line-limited car in the garage. **Run it short-shifted, because that is what most of those 200 laps were.** Baseline card, run mode and full method: the Rev B sheet's banner.

> ⚠️ The two published GT7 RSR tunes are **March–April 2022, pre-1.49**, and run camber −3.0 and LSD 15/40/50. Do not start there. **They are now three physics generations old.**

### E2. Lamborghini Huracán GT3 '15 — reassessed, and it is better than we thought

- **MR, 5.2 V10, ~576 bhp, 1,230 kg.** Real straight-line ability the Porsche lacks. Strong braking, deep entries.
- **Higher polar moment** — the long V10 set well back. Once yaw starts it develops with more momentum and is harder to arrest. It rewards **one decisive rotation input**, not continuous modulation, because modulation on a high-inertia car mostly generates rear scrub. **⭐ A mass-distribution argument — the least version-exposed claim in this entry, and the right thing to reason from while everything else is being re-established.**

**✅ What changed on 10 Aug 2026 — two measured results, both overturning prior guidance:**

**1. The diff wants 14, not 15–28.** See A5.1 and D3.1. Below the MR baseline, far below the track norm, and the fix for a power-on push that was present from lap 1. **This is now the car's starting point on any traction-limited circuit with a restrictor fitted.** ⚠️ **On v1.70, against the old torque map. Re-test before reusing.**

**2. The tyre-life reputation is overstated.** This document previously called wear *"the defining weakness and it is not marginal,"* on the strength of a 2019 GT Sport ranking (2nd-worst in the MR field, "undrivable by lap 6"). Measured: **11–12 laps at 2× on Racing Softs at race pace from full fuel.** That comfortably covers a 10-lap stint with margin, on the *softest* compound available. ⚠️ **On v1.70.**

**The 2019 ranking may still be right in relative terms** — nothing here tested the Huracán against the McLaren or the RSR. But *relative* worst-in-class and *absolute* unraceable are different claims, and only the first is supported. **The old advice — "treat as a sprint weapon, re-test before committing to endurance" — should now read: measure a stint, then decide. Do not rule it out on reputation.**

> **⭐ And that instruction is now the whole of what this entry says, because the measurement it was built on is a version behind.** The Huracán is the car for `16` §12 Job 2 — it is the one you race, it has the most recent working setup (Rev D), and **it won on 17 August from P5.** **One 30-minute stint at Watkins Glen rebuilds this entry and half of `03` with it.**

**Revised setup principle.** The old organising question was *"does this buy me rear tyre life?"* — which produced low camber, a soft rear platform, near-max rear downforce and a conservative diff. **The better question is: "is this change paying for itself, or am I protecting against a limit I haven't measured?"** Rear downforce still passes (free grip, no wear cost). Camber currently fails and is queued for testing.

**Still open on this car:** front toe never A/B'd (A3, fourth session); ballast −25 vs −50 never compared; whether accel 14 holds on worn Softs; **which corner actually goes first**; the gearing constant K still an extrapolation; **the Watkins Glen corner-ID mapping, asked for twice and never answered — and Job 2 runs at Watkins Glen, so it is needed now.**

### E3. The Shelby — resolved, and it is the **Shelby GT350R '16**

**Ford Shelby GT350R '16**, a road car (Gr.N), not a Gr.3 machine. FR, 5,163 cc flat-plane-crank V8, 525 bhp @ 7,500, **1,658 kg**, PP 575 ⚠️ *(PP recalculated — re-read, and 575 sits in the middle of the 550–650 band `06` §8.2 identifies as worst for PP-vs-lap-time mismatch)*.

That weight is the headline: **355 kg heavier than a Gr.3 Mustang.** Far more mass to manage into braking zones and correspondingly more tyre wear. Combined with the flat-plane crank's peaky delivery, a genuinely demanding platform.

- **FR character:** entry understeer to manage, exit traction limitation, and **it will not rotate for free.** You have to manufacture rotation with brake bias, front geometry and a looser entry diff. **⭐ If the LSD floor really did drop to 0, this car benefits most of the three — "a looser entry diff" now has somewhere further to go.**
- **LSD FR baseline: 5 / 25 / 10.** Accel 25 is markedly higher than the MR 15 — FR cars need more locking to put power down. ⚠️ **But per D3.1, if you ever run this car restricted and it pushes on throttle, come DOWN from 25 before touching front grip.**
- **The Watkins Glen unresolved item — rear locking with no ABS — should be attacked as: ABS Weak, LSD braking sensitivity up in +2 steps, rear expansion damping down, rear ride height up from the 95 mm floor.** Brake bias stays at neutral. **⚠️ The 95 mm floor is a v1.70 reading and 1.71 revised suspension ranges — re-read it (Job 1) before using it as a floor.**
- **This car has the most unused softness of the three** — `11` records it running 3.05 / 3.20 Hz on a 1.88–3.70 / 2.00–3.90 Hz range, i.e. ~64% of its own range, on a heavy road car with aggressive kerbs, and none of the softness below that has ever been tried. **⚠️ Re-read the range first; the whole observation depends on where the floor is.**

> ⚠️ **Worth checking:** if your league runs Gr.3 rounds, the **Ford Mustang Gr.3** (FR, 568 bhp, 1,300 kg, PP 716) exists and is a completely different proposition. It is also almost entirely undocumented by the community — no BoP data, no published tunes, absent from every 2026 tier list. In an open-tuning league that is arguably an *advantage*.
>
> **⭐ And that advantage just got bigger.** Post-1.71 the *entire* community tuning record is stale, so the gap between a documented car and an undocumented one has narrowed to nearly nothing. **For the next few weeks, everyone is tuning an undocumented car.** It would also be the FR Gr.3 data point `11` has wanted since 13 August, which would settle whether the 9 chassis-derived endpoints are a Gr.3 constant or an MR-Gr.3 one.

---

## PART F — The engineer's working protocol

### F1. Session sequence

> **⭐ For the first sessions on v1.71, four jobs come before step 0.** They are `16` §12 Jobs 0, 1, 7a and 2A/2: confirm the tunes survived (2 min), re-read the slider ranges (15 min), confirm the wheel (5 min), then take a comparison measurement (30 min). **Nothing below step 4 is meaningful until the ranges are known, and nothing about compound or strategy is meaningful until a stint is measured.**

0. **Validate hardware.** Throttle calibration, load-cell brake calibration, steering range, FFB profile. Step zero, not a formality. **⭐ And genuinely not a formality this time — 1.71 adjusted FFB and understeer vibration and changed Fanatec Auto Setup parameters. Separate "the wheel feels different" from "the car has less grip" before anything else (B3).**
1. **Rule out arch rub / bottoming.** Post-1.49, before diagnosing any balance problem: raise ride height 3–5 mm and re-test. **⚠️ Status on 1.71 unknown (A7) — but the step costs one run and the failure mode it catches is severe, so keep it.**
2. **Platform.** Ride height + natural frequency, both ends. Get the car off the bump stops.
3. **Gears.** Free in PP, and the fix for your most-recorded defect. Max Speed slider → final drive → individual ratios. Never touch Max Speed again. **⭐ Re-gear on 1.71 regardless of anything else — rolling resistance changed.**
4. **Aero and PP-affecting parts.** Lock the PP budget before spending time on feel. **⭐ And on 1.71, read the PP number *before* you start, not just after — the build may already be over the cap (D1).**
5. **✅ MEASURE THE STINT.** Three laps at race pace from full fuel, at the multiplier you will actually race, on the compound you think you want. **This step is new, it costs 10 minutes, and skipping it cost a second a lap at Laguna (C3.1) and rebuilt a whole race plan at Monza.** Do it before you spend any setting on tyre protection. **⭐ On v1.71 this is not optional and not last — it is the reason to book the session.**
6. **Rear stability at neutral brake bias.** LSD braking sensitivity, rear expansion damping, rear toe. This comes before front-bite work.
7. **Front response.** Front compression damping low, front ARB, front toe (A/B tested).
8. **Mid-corner with ARBs — but diagnose the throttle state first.** Coasting push → front grip. Power-on push → accel LSD (A5).
9. **Exit traction.** Diagnose wheelspin type first (inside-wheel vs both-wheels vs push), then LSD accel.
10. **Dampers** as fine transient trim. **⚠️ And re-learn what they do — 1.71 changed the damper model (A7).**
11. **Camber sweep**, one axle at a time, Data Logger on. **Sweep upward if step 5 showed wear headroom. ⭐ On v1.71, sweep it regardless — the steering geometry rework may have changed the sign of the answer (A1).**
12. **Toe**, last, ±0.05 steps. **In absolute degrees, never percent.**
13. **Brake balance**, last of all, as a session trim.
14. **Re-check ride height and PP** — everything above changed both, and a compound change moves PP too.

**Discipline:** one change per run, three clean laps minimum, record the change and the time. If you can't feel it and the Data Logger can't see it, revert it. **⭐ And record the game version alongside the change — Standing Rule 10. A measurement without a version has an expiry date nobody can read.**

**⭐ And record the *run mode* too — Standing Rule 12.** Short-shifted and full-RPM laps are different measurements of the same car, and a comparison that mixes them is not a comparison. **When re-measuring against history, match the run to the dominant condition in that history, not to whichever session happens to be written up.**

### F2. The four diagnostic questions

Before changing anything in response to a driver complaint, establish:

1. **Where is your right foot?** — off throttle, trailing brake, or on power. This is the single highest-information question and it forks the whole diagnosis.
2. **Which corners — and which corners are FINE?** The silent corner localises the fault. At Laguna, T11's silence identified the problem in one step.
3. **From lap 1, or does it develop?** Separates setup from degradation, thermal and fuel-load effects.
4. **Is the car built as written?** Rules out build error before engineering effort is spent. **⭐ And post-1.71 this question has a new failure mode: the patch may have reset or clamped saved values. Standing Rule 9 already requires confirming which sheet is physically in the car; Job 0 is that question asked once, globally.**

**These four questions diagnosed the Laguna case to a single slider with no telemetry.** They cost one message. Ask them every time.

> **⭐ They are also the most valuable thing in this document right now, precisely because they need no baseline.** A symptom-based diagnostic works on a car whose behaviour you can no longer predict. **While the reference numbers are being rebuilt, diagnose from symptoms and the driver report — Standing Rule 7 — and let the numbers catch up.**

### F3. Use the Data Logger

Added in Spec III (1.65, Dec 2025), expanded in 1.67 and 1.68. **Direct lap-vs-lap telemetry comparison in any single-player event including Online Time Trials.** Not available in Daily Races or GTWS — but your league runs custom races and lobbies, so for practice and setup work it is available to you.

Use it for **every camber sweep, every toe test, and every stint measurement.**

> **⚠️ One 1.71 caveat: every reference lap and ghost recorded before 20 August 2026 is on old physics, and PD reset all the in-game ranking boards for exactly that reason.** Comparisons against your own old laps will show a delta that is partly the patch and partly you. **Rebuild your reference laps early in the re-baselining, or you will spend the season chasing a ghost that was set in a different game.**
>
> **⭐ The Monza control run is the exception that proves the rule, and the reason it works.** Comparing 10 new laps against ~200 old ones *is* mixing the patch with your driving — **but with a large enough baseline you can tell them apart**, because you know the historical spread and can ask whether the delta falls outside it. **That is the whole argument for Job 2A, and it is why it goes first.** It is also why the run mode has to match the history: short-shifted, because that is what most of those 200 laps were.

---

## PART G — The measurement backlog

Ranked by value to you. **Two items closed on 10 Aug 2026, two more at Monza on 12 Aug. 1.71 reopened most of them and added a new tier above everything else.**

### ⭐ Tier 0 — the 1.71 rebuild. Everything below is blocked on these.

**Execution order matters here. Run them top to bottom.**

| # | Test | Time | Why it is in this position |
|---|---|---|---|
| **0a** | **Did the saved tunes survive the patch?** Read the car's settings screen against its archived sheet **before touching anything**. | **2 min** | Determines whether the garage needs re-entering at all. If some values changed and others didn't, the changed ones map out where the new ranges are. **And it is a hard prerequisite for 0d** — a comparison run is only a physics comparison if the car is in the same state of tune. |
| **0b** | **Re-read the slider register — all three cars, 22 parameters.** Record **step sizes** and check the **LSD floor** while the screens are open. | **15 min** | 1.71 revised adjustment ranges in writing. **Blocks every sheet.** Also closes the step-size item that has been overdue for four sessions, for free. **Cheapest clamp detector: the RSR's front NF sits at 3.05 Hz on a 3.00 floor — five clicks. If that floor moved at all, it shows there first.** |
| **0c** | **Confirm the wheel.** FFB, understeer vibration and Fanatec Auto Setup parameters all changed. | **5 min** | On an 18 Nm DD this reads exactly like a grip change, and it would be baked silently into every measurement that follows. **Do it before 0d, not after.** |
| **⭐ 0d** | **THE MONZA CONTROL RUN.** Porsche 911 RSR, Monza, **Racing Hard, 10 laps, 8× tyre / 3× fuel**, sheet unchanged, clean air. Against the 11 Aug baseline: **Vmax 278.7 km/h @ 8,009 rpm · 6.566 L/lap · median 1:49.180 · best clean 1:46.828 · ~9 ms/lap degradation · four-corner temps FL 74.5 / FR 68.3 / RL 85.7 / RR 82.6.** | **30 min** | **The only measurement in the programme with a baseline *distribution* behind it** — everything else is n=1 with no error bar. **Monza is also the best probe available for the rolling-resistance change**, on the most straight-line-limited car in the garage. **Vmax and median lap are the two diagnostic numbers:** Vmax moved but median didn't → rolling resistance; median moved but Vmax didn't → grip or geometry; both → sector times separate them. Full card: `setups/2026-08-12-rsr-monza-revB.md`. **⭐ RUN MODE — short-shift on the app's beep for the first 7–8 laps.** That is the dominant condition across the ~200-lap Monza history, and the size of that comparison set is the entire point of this run — match the history, not the single session that happens to be written up. **Then add 2–3 full-RPM laps at the end** to touch the documented no-short-shift references (6.566 L/lap, median 1:49.180) and to re-take Vmax and K. **Two run modes, one session, and the −20 % short-shift fuel saving gets re-measured for free.** ⚠️ *Confirm the tyre multiplier really reads 8× — that check was never done.* |
| **0e** | **The tyre stint** — Huracán, Watkins Glen Long, **Racing Soft**, league multiplier, full fuel, run to *felt* fall-off. Take the **rear-left gauge reading at lap 6 and lap 12**. | **30 min** | Rebuilds the top half of `03` and half of E2, on the car you race and the circuit you race it at. Closes G4 (which corner goes first) for free. **The rear-left reading has now been asked for four sessions running.** ⚠️ *Needs the Watkins Glen corner-ID mapping, asked for twice and never answered.* |
| **0f** | **RM comparison stint**, same car/track/multiplier. | **30 min** | Closes the RH:RM:RS ratio that has been open since `03` was written. **Only cheap while 0e's conditions are still set up — do it in the same session or it will not get done.** |
| **0g** | **Camber A/B (0.5 / 1.5 / 2.5 front) + the front/rear swap check + the front toe A/B**, all in one session. | **30 min** | 1.71 reworked per-car steering geometry. **Three of the oldest open questions in the knowledge base all got re-rolled at once, and they share a session.** |
| **0h** | **PP audit on all three builds.** Plus: re-measure the Fully Customisable Suspension PP cost, and re-check whether body rigidity and wide-body still lower PP. | **10 min** | PP moved fleet-wide. **A race-weekend problem, not a tuning problem.** |

**0a through 0d is about ninety minutes and answers the four questions everything else depends on:** did the garage survive, what can the sliders do, is the wheel lying to you, and how big is the physics change against a real baseline.

### Tier 1 — the standing backlog

| # | Test | Status | Time |
|---|---|---|---|
| 1 | **Front toe A/B — never run on either Gr.3 car** (−0.05 / 0.00 / +0.05) | ❌ **Open — fourth session running.** GT7's most disputed parameter, sitting directly on your #1 priority. **Folded into 0g — the geometry rework makes it more interesting, not less, and may finally resolve it cleanly.** | 20 min |
| 2 | **Tyre wear per lap at race multiplier, per compound, per track** | ⚠️ **Reopened by 1.71.** Both v1.70 results (Laguna RS 2× = 11–12 laps; Monza RH 8× = 15 laps) stand as history and as controls. **Superseded by 0d, 0e and 0f.** | 30 min/track |
| 3 | **Fuel consumption at 3× on the Laguna Huracán, map 2, with and without short-shifting** | ❌ **Open, and now exposed twice** — the estimate came from the method that produced the 1.8× tyre error, *and* 1.71 optimised rolling resistance, which moves L/lap directly. **0d re-measures L/lap on the RSR in both run modes for free.** | 20 min |
| 4 | **Which corner/tyre goes first on the Huracán** | ❌ **Open.** The model assumed front-right; the car's reputation says rear. **Closes for free during 0e.** *(On the RSR it is already measured: front-left and rear-left at Monza, because the three sustained corners are rights.)* | free |
| 5 | **Multiplier linearity — same car/track/compound at 2× and 4×** | ❌ **Open.** Every stint conversion rests on it, the two reference docs disagree on how well-evidenced it is, and C3.1 is equally consistent with linearity or non-linearity. **Status unchanged by 1.71 — the mechanism wasn't touched, the rate was.** | 30 min |
| 6 | **Camber sweep on both Gr.3 cars** | ❌ **Open, and newly urgent for a second reason.** Was justified by wear headroom; now also justified by the geometry rework. **Folded into 0g.** | 30 min |
| 7 | **Ballast −25 vs −50 on the Huracán** | ❌ **Open.** And now interacts with 0h, since PP moved and ballast position is the free-PP exploit. | 20 min |
| 8 | **Confirm accel 14 on Racing Softs and on worn tyres** | ❌ **Open — and 14 itself now needs re-establishing first** (A5.1, D3.1). New torque map. | free during a stint |
| 9 | **Fuel weight penalty in s/L/lap** | ❌ Open. Genuine gap in the public record; needed to compute stop strategy properly. **Monza run 5 came close — 98.6 L across 15 laps with near-zero degradation is almost a clean measurement of it.** | 30 min |
| 10 | **Pit lane time loss** at each league circuit | ❌ Open. The number that most changes strategy — **and one of the few things 1.71 did not touch, so a measurement taken now will not go stale.** *(Watkins Glen: the 17 Aug stop cost 51.3 s total including ~26 L of refuel.)* | 5 min/track |
| 11 | **Gearing constants K on all three cars, on v1.71** | ❌ Open. Huracán's K was never closed (1112.6 vs 1092.5); **the RSR's 1,128 and the Shelby's 1,096 were closed on v1.70 and reopened by the rolling-resistance change.** The RSR's re-take is free inside 0d's full-RPM tail. | 1 lap each |
| 12 | **Does brake balance move PP?** | ❌ Open. Matters only near a cap — **which more builds now are.** | 2 min |
| 13 | **⭐ TCS 0 vs TCS 1 cost per corner on v1.71** | ❌ Open. The v1.70 price was up to two tenths per corner; 1.71 "optimised" intervention. **Changes the B1 recommendation.** | 15 min |
| 14 | **⭐ Tyre temperature window from telemetry** | ❌ Open. `03` §3 and `04` §6.1 **openly contradict each other** on whether temperature matters, and 1.71 adjusted heating values. **Nobody has published this for any version of GT7.** *(And 0d gives a free four-corner comparison against a known baseline.)* | 30 min |
| 15 | **⭐ Correct `05-track-reference.md`'s Monza wear side** — it says front-right; measured front-left | ❌ Open since 12 Aug. Circuit geometry, unaffected by the patch. | 5 min |
| 16 | **⭐ Re-derive the short-shift beep points against the new torque map** | ❌ Open. The Pit Crew beep's RPM points were derived on v1.70 and 1.71 introduced a new engine torque control map, so they may no longer be optimal. **Does not block 0d** — an unchanged beep is a *more* consistent comparison instrument, not a less one — but it should be re-derived before the next race. | 20 min |
| — | ~~Huracán tyre life post-1.49~~ · ~~Huracán LSD accel~~ · ~~RSR gearing K~~ · ~~RSR Monza stint~~ | ✅ Closed on v1.70 — **all four reopened by 1.71**, through no fault of the measurements. | — |
| — | ~~Slider step sizes~~ | ❌ Four sessions overdue — **folded into 0b, no excuse left.** | — |

**Everything measured goes back into this knowledge base with a date, a game version and a run mode.** That is what turns it from a reference into an advantage.

> **The meta-lesson, and it now has three parts.**
>
> **One: our reasoning was wrong.** Both Laguna measurements overturned something this document asserted with confidence — that published diff guidance was a safe starting point, and that this car's tyre wear made it unsuitable for anything but sprints. **Both claims were plausible, well-argued, and wrong.** Monza then found the wear model wrong by 5×, worse than Laguna's 1.8×.
>
> **Two: the game moved.** 1.71 demoted every one of those measurements — not because they were poor, but because the physics underneath them changed. **The response is not to measure less. It is to version-stamp everything and re-measure after every physics patch** (Standing Rules 10 and 11).
>
> **Three, and this is the new one: structural knowledge outlives measurements.** Look at what survived the patch and what didn't. **The claims grounded in what GT7 *doesn't have* — no engine-braking map, no tyre pressure, no damper speed split — all held. So did the ones grounded in ordinary physics, mass distribution and polar moment. What fell over were the claims about how a particular version *behaved*.** Measure anyway; but know which kind of claim you are making, and weight your confidence accordingly.
>
> **And the prize on the table right now: nobody in the community has post-1.71 data either.** The public record is emptier than it has been since 1.49, the measurements are cheap, and **you have something almost nobody else does — a large pre-patch baseline on a fixed car and circuit.** The window closes as everyone else catches up.

---

## Reference index

| File | Contents |
|---|---|
| **`16-update-1.71-physics-change.md`** | **⭐ The 1.71 changelog and work order. What changed, what it invalidates, what is now unknown, and the re-measurement protocol. Read before any setup work.** |
| `01-driver-profile-leon.md` | Your dossier — the driver model, technique, symptom dictionary, accumulated learnings |
| `02-gt7-setup-parameters.md` | Every slider: ranges, effects, GT7 quirks, full symptom→fix diagnosis tables. **Ranges void post-1.71; §10's symptom tables are the part to use during the rebuild** |
| `03-gt7-tyre-and-fuel-model.md` | Compounds, wear model, multipliers, fuel, pit stops, wet weather. **Worst affected by 1.71 — carries a full section-by-section exposure banner** |
| `04-race-vs-qualifying.md` | Parameter-by-parameter quali/race deltas, fuel load, stint degradation, decision rules. **Framework intact, magnitudes suspect; §8's validation protocol is the useful part now** |
| `05-track-reference.md` | 42 circuits: downforce, kerbs, braking, gearing, wear, pit loss, top levers. **⚠️ Carries an outstanding correction — Monza's front wear side is LEFT** |
| `06-car-building-and-pp.md` | PP mechanics, upgrades, restrictor vs ECU, ballast, engine swaps, min-max build strategy. **PP numbers void post-1.71; mechanism intact — and §1.4 predicted the patch** |
| `07-car-profiles.md` | RSR, Huracán, Mustang/Shelby — specs, character, wear, baselines, comparison. **Character is a pre-1.71 observation, and geometry was reworked per car** |
| **`08-playbook-leon.md`** | **This file.** The synthesis. Start here, after `16`. |
| `09-setup-sheet-format.md` | The required output layout for every setup |
| `10-pit-crew-data-format.md` | The Pit Crew ingestion spec. **⭐ `meta.gameVersion` is now required and is missing** |
| `11-car-slider-ranges.md` | The range register. **⚠️ All three cars unverified post-1.71 — carries the re-read worksheet** |
| `15-pitcrew-detector-audit.md` | What the Pit Crew flags actually measure. **Unaffected by 1.71 and more important during the rebuild, not less** |
| `setups/00-PRE-1.71-NOTICE.md` | **Why every archived sheet is a control group rather than a setup, and the Job 0 procedure** |
| `setups/2026-08-12-rsr-monza-revB.md` | **The Monza baseline card for the control run — including the run-mode decision.** Also the best data-integrity section in the archive — four Pit Crew defects, still live |
| `setups/2026-08-17-huracan-watkins-glen-long-revD.md` | **The most recent Huracán sheet** — the post-mortem on the 17 Aug win. **Pre-1.71** |
| `setups/2026-08-10-huracan-laguna-seca.md` | The §9 test log — the first two measured results in full. **Pre-1.71** |
