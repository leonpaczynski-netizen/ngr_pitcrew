# Driver Profile — Leon Paczynski

**Archetype: Front-end-led Precision Attacker**
Deep trail braking · Immediate turn-in · Controlled rotation · Smooth early throttle · Trustworthy rear

*Canonical source: `Leon_Paczynski_GT7_Driver_Engineering_Dossier.pdf`, 10 August 2026. This markdown version is the working copy the engineer reads before every setup. Where this file and the PDF disagree, the more recent repeated preference wins — see the document rule below.*

**Document rule (inherited from the dossier):** where historical feedback conflicts, use the **most recent repeated preference** as the primary rule, and preserve older evidence as context rather than pretending the driver has never evolved.

---

## 1. One-sentence setup target

> **Immediate nose response, controlled rotation, and a stable rear platform that allows deep trail braking and early progressive throttle without snap, skate or rear locking.**

## 2. Default instruction to the engineer

> **Build me a car I can attack on the brakes, rotate on release, and commit to throttle early. Keep the front alive and the rear trustworthy. Do not buy stability by giving me understeer.**

---

## 3. The five non-negotiables

1. Strong front response at initial turn-in and under trail braking.
2. No persistent mid-corner push. A tiny safety margin is acceptable; a car that washes wide is not.
3. Rear stability through hard braking, downshifts and brake release. Rotation must be **progressive, not a surprise**.
4. Progressive exit traction permitting early partial throttle, then full throttle, without wheelspin or abrupt diff lock.
5. Information-rich controls: wheel and pedal settings must **reveal** front lock, rear brake traction, weight transfer and grip loss rather than simply adding heaviness.

## 4. What not to engineer

- A "planted but slow" car that achieves stability by dulling the front axle.
- A nervous rear that requires excessive front brake bias to survive braking zones.
- An over-stiff platform that loses grip over bumps or kerbs.
- A diff so tight the car will not finish rotation, or so open it snaps into wheelspin.
- Gearboxes that look theoretically fast but do not put the engine in the useful range at the actual circuit.

---

## 5. Technique model

### Braking
- Firm initial straight-line application, then a **smooth bleed as steering angle is introduced**.
- Carries brake pressure deeper than a conservative driver; uses **release rate to control yaw**.
- Braking is a passing strength — late-braking opportunities are a natural overtaking tool.
- Needs the rear axle to stay settled during downshifts and the trail phase. Rear locking, skating or a floating rear immediately damages confidence and consistency.
- **Sometimes runs no ABS.** When ABS is off, rear stability becomes even more important. A tune that only works with brake bias pushed heavily forward is **not a finished solution**.

### Steering and rotation
- Prefers **one clean steering input** and minimal mid-corner corrections.
- Wants immediate nose response rather than waiting for the chassis to take a set.
- Rotates using brake pressure, brake release, weight transfer, downshift timing and steering **together**.
- Comfortable attacking kerbs **when the platform has enough compliance**.
- Fastest when aggression is tolerated by the car — not when the rear becomes unpredictable.

### Throttle
- Smooth, progressive application is the baseline trait.
- **Evolved target: early partial throttle, typically a 5–20% opening once the nose is pointed**, building progressively as rotation completes.
- Prefers a rear that feels alive and connected, but not one that snaps or spins the tyres.
- **Predictable exit traction is more valuable than a car that rotates spectacularly but delays throttle commitment.**

---

## 6. Preferred vehicle balance by corner phase

| Phase | Target | Engineering meaning |
|---|---|---|
| Braking | Very high confidence | Stable rear, clear front load, no rear lock/skate, good pitch support |
| Initial turn-in | Aggressive response | Immediate bite, light/communicative nose, progressive yaw |
| Trail-brake phase | Controlled rotation | Rear must follow the front without snap or float |
| Mid-corner | Neutral to tiny safety margin | No sustained push; holds line on modest maintenance throttle |
| Early throttle | Progressive hook-up | Small throttle before steering is fully unwound, without power oversteer |
| Full-throttle exit | Planted acceleration | Minimal wheelspin, no abrupt diff lock, confidence to commit early |
| Kerbs / bumps | Compliant platform | Tyres stay loaded; no skipping or losing both axles over surface changes |

**The key distinction — trustworthy vs safe.** A safe setup simply removes rotation. That is not the target. The correct setup preserves the ability to attack the brake zone and rotate the car, but removes the unpredictable rear events that interrupt that attack. **Front response is protected; rear stability is engineered mechanically** through platform control, geometry, differential behaviour and appropriate aero.

---

## 7. Preferred change hierarchy

When multiple controls could address the same symptom, work down this list. It exists to stop one problem being solved by creating another.

| Order | Control family | Why |
|---|---|---|
| 1 | **Hardware / calibration** | Bad data makes a good chassis look wrong |
| 2 | **Brake stability / rear support** | The driving style depends on trail braking |
| 3 | **Mechanical front grip / ARB / geometry** | Front response is the primary performance language |
| 4 | **LSD axis targeted to symptom** | Large diff changes flip the balance quickly |
| 5 | **Ride height / rake** | Useful, but introduces brake and aero side effects |
| 6 | **Aero balance** | Powerful at speed; must respect drag and fuel economics |
| 7 | **Brake bias** | Fine tuning only, after the mechanical platform is correct |

> **⚠️ One standing exception, added 10 Aug 2026.** The hierarchy is a tie-breaker for when *several* controls could plausibly address a symptom. It is **not** a licence to reach for a higher-ranked control when the symptom has already been diagnosed to a specific one. A **power-on** mid-corner push is diagnostically an accel-LSD problem (#4); reaching for front ARB or front aero (#3, #6) because they rank higher will mask it while giving up roll control or entry stability. **Diagnose first, then apply the hierarchy only among the controls that actually fit the diagnosis.** See §11, Huracán / Laguna Seca.

## 8. Do / Don't rules

| | Rule | Why |
|---|---|---|
| **DO** | Give the front axle authority | Fastest when the nose responds immediately |
| **DO** | Stabilise the rear mechanically under brake | Deep trail braking is central to the style |
| **DO** | Use small, isolated A/B changes (~2 points on LSD) | Subtle balance shifts are felt; large changes hide causality |
| **DO** | Build race tunes around total stint time | Tyres, fuel and pit time matter more than one lap |
| **DO** | Protect bump compliance | Bumpy tracks have repeatedly punished over-stiff setups |
| **DO** | Ask which corners are *not* complaining | The corner a value was set for, staying silent while others push, localises the fault fast |
| **DON'T** | Solve instability by making the front dull | Removes the driver's biggest weapon |
| **DON'T** | Depend on front-heavy brake bias | Disliked, and it masks rear problems |
| **DON'T** | Assume more LSD lock always means more traction | Causes power-understeer and delays throttle |
| **DON'T** | Import generic track guidance without checking the build | Track norms assume an unrestricted car; a restrictor changes the answer |
| **DON'T** | Trim rear aero first for top speed | Braking/fast-corner confidence can cost more than drag saves |
| **DON'T** | Tune around unverified pedal/FFB behaviour | The Watkins Glen throttle-calibration case proved the risk |

---

## 9. Symptom dictionary — driver language → engineering diagnosis

| Driver says | Likely cause | First engineering response |
|---|---|---|
| "Pushes wide mid-corner" — **and I'm off throttle / trailing brake** | Front mechanical grip, too much front roll stiffness, insufficient rotation | Soften front ARB one step; review front toe; add front aero. **Do not touch accel LSD — it isn't engaged.** |
| "Pushes wide mid-corner" — **and I'm on throttle** | **Excessive acceleration lock**, or gearing putting the engine in peak torque too early | **Reduce LSD acceleration in 2–4 point steps. This is the whole answer more often than not** — see §11, Huracán / Laguna. ⚠️ *[CONTESTED on v1.71: Huracán, Daytona - lowering it −6 pp was refuted (s145); raising it moved the derived rotation index up, at a cost of 2 spins in 10 laps - see `02` §10.5. The Laguna result is v1.70, on the old 5–60 scale.]* Only if that fails, look at front grip. |
| "Initial turn-in is lazy" | Front response / geometry / platform | More front bite via mild toe-out, front aero or controlled rake; keep rear braking stable |
| "Rear is excited/sketchy on brakes" | Rear decel stability, lock-up, platform control | Stabilise rear mechanically: brake LSD / rear toe / platform support. Do **not** rely on large front BB |
| "Rear is floating" | Insufficient rear support or poor rebound/aero balance | Add platform control / rear support; review rebound and rear aero |
| "Loses rear when I lift" | Lift-off oversteer | Stabilise rear decel, reduce excessive rake/stiffness, preserve compliance |
| "Loose on throttle exit" | Power oversteer, wheelspin, diff/gearing | **Check pedal calibration first**; then rear toe, accel LSD direction, 2nd gear, rear support |
| "Won't hook up under throttle" | Too much wheelspin or insufficient rear load | Longer lower gear, more rear support, geometry/diff correction, smoother torque delivery |
| "Won't rotate under throttle" | Excessive acceleration lock / too much rear security | Reduce accel LSD slightly to free rotation without removing braking stability ⚠️ *[CONTESTED on v1.71: lowering it did not bring on-power rotation back on the Huracán at Daytona (s145) - `02` §10.5]* |
| "Undriveable over bumps" | Platform too stiff | Soften spring/bar/rebound axis; keep tyres in contact rather than chasing response |
| "Gearbox too long/short" | Ratio spread mismatch | Validate actual gear reached at end of straight and corner-exit rpm; then adjust individual ratios/final |

> **The four questions that resolve almost any balance complaint.** Ask them before changing anything: **(1) where is your right foot?** (2) **which corners — and which corners are fine?** (3) **from lap 1, or does it develop?** (4) **is the car built as written?** The Laguna Huracán case (§11) was diagnosed to a single slider from these four answers alone, with no telemetry.

---

## 10. Car character fit

| Car | Fit | Why |
|---|---|---|
| **Porsche 911 RSR '17 Gr.3** | **Excellent** | Rearward mass bias supports brake-release rotation while retaining exit traction when tuned correctly. The benchmark car. |
| Alfa Romeo Gr.3 | Strong | Suits the responsive front end and natural rotation |
| Peugeot Gr.3 | Strong | Fits the front-led, trail-braking preference better than pushier alternatives |
| **Lamborghini Huracán Gr.3** | Useful general GT3 baseline | Now used as the general GT3 hardware/FFB profile reference; requires clear front information and rear traction feedback. **Runs a notably free diff on accel — 14, below the MR baseline. See §11.** |
| Mitsubishi Lancer Gr.3 | Poorer natural fit | Pushy/AWD character resists trail-brake rotation |
| Toyota Supra Gr.3 | Less natural | Historically needed more work for front response and rotation |
| BMW M6 Gr.3 | Less natural | Large/inert character conflicts with immediate front response |
| **Shelby GT350R '16** | Challenging but informative | Heavy FR platform repeatedly exposes the need to balance front rotation, rear brake stability, bump compliance and power traction |
| Ford Escort RS Cosworth '92 | Stability-biased AWD lesson | Forgiving traction but pushy; Bathurst exposed rear-braking instability despite AWD security |

> **⚠️ Correction logged 10 Aug 2026 — RSR layout.** The dossier describes the RSR's advantage as "rear-engine traction." The GT7 911 RSR (991) '17 is **MR, not RR** — the 2017 991 RSR is the first 911 to move the flat-six ahead of the rear axle, and GT7 classifies it as MR with a roughly 46:54 F:R static bias. The *empirical* learnings in §11 stand; the *mechanism* should be read as mid-engine with rearward bias. Practical consequence: the RSR's failure mode is **throttle-timing-sensitive exit rotation**, not RR lift-off pendulum snap, and its LSD braking sensitivity should start lower than an RR baseline would suggest. Approved by the driver.

---

## 11. Accumulated car/track learnings

### Porsche 911 RSR '17 — the reference car
It is the clearest match to the driver profile: responsive nose, strong brake-release rotation, rear traction that supports early throttle. When it is wrong the symptoms are highly diagnostic — rear nervousness on brake, mid-corner push from diff/platform, or wheelspin on exit.

**Fuji Full Course**
- Needs both front bite in the technical final sector and rear confidence to attack braking and traction zones.
- A previous quali/race pair deliberately separated the philosophies: **quali ≈ 55/59 mm ride height, ARB 7/7, 3.50/3.60 Hz; race ≈ 56/63 mm, ARB 7/6, 3.35/3.45 Hz** — the race car intentionally calmer and less peaky for consistency and tyre protection.
- Telemetry showed **22 wheelspin events in one lap** with no lock-ups or oversteer recorded, and braking inconsistency around 22.6 m. Lesson: the biggest loss can be traction/braking *repeatability* even when the lap doesn't look spectacularly unstable.
- Top speed was ~271 km/h against a nominal 300 km/h target — so lengthening the gearbox would have been the wrong response. **Ratios must follow actual pull, not a target-speed number.**
- A tested response to entry/mid understeer plus loose throttle exit: **front ARB 5→4, front toe −0.10→−0.15, LSD accel 25→20, rear toe 0.20→0.25.** A good template — add front bite *and* rear exit security simultaneously. ⚠️ *[v1.70 5–60 scale; and on v1.71 lowering accel against a push is CONTESTED - Huracán, Daytona, s145, `02` §10.5]*

**Spa**
- Reinforced high-speed platform stability and sufficient rear aero. Must be able to commit through fast loaded sections without the rear going nervous.
- Throttle trace showed a tendency to release brake early, coast, then sit on a prolonged 30–35% throttle plateau. Coaching target: **smoother brake taper and earlier brake-to-throttle overlap** once rotation is under control.
- The lesson is not "use more throttle" — it is to **eliminate dead time** between brake release and a stable, purposeful partial-throttle phase.

**Monza (with chicane)**
- Priority order changes: reduce drag, lengthen 2nd, keep kerb compliance, make braking stability non-negotiable.
- Quali can carry the more aggressive aero/platform choice; the 50-minute race at high tyre/fuel multipliers needs an efficient low-drag car that still stays straight and settled under repeated heavy braking.
- With refuelling at **1 L/s**, race fuel economy has direct pit-lane value. Lower drag and longer gearing can be worthwhile if they reduce fuel used without compromising braking or traction.

**Watkins Glen / high-speed circuits (general RSR rule)**
Firm platform support, sufficient rear downforce, stable brake-side differential behaviour, mild rear toe-in, and **less aggressive front toe-out than on slower circuits.** Front response is still required, but the car cannot be knife-edge through fast direction changes.

### Lamborghini Huracán GT3 '15 — Laguna Seca, 10 Aug 2026 ✅ **first validated result on this car** (v1.70)

⚠️ *v1.70, a void version: the values below are what was run, not a setting (§1a - a value set on a car lives in `brain/car-state/`), and the LSD scales changed on v1.71 (`11`). **And the direction is CONTESTED on v1.71:** lowering accel for a power-on push was refuted on this car at Daytona (s145) - `02` §10.5.*

**The case.** Race build: 525 bhp / 1300 kg, restrictor 70, ECU 97, 70 kg ballast at −25, Racing Hards, brake bias 0, LSD 6 / **18** / 26. Symptom reported: *"car is understeering and not rotating mid corner."*

**Diagnosis from four questions, no telemetry:**

| Question | Answer | What it ruled out |
|---|---|---|
| Where is your right foot? | **On throttle** | Front mechanical grip — the diff is engaged, so the diff is a live suspect |
| Which corners? | **T2, T3, T4, T5** — and **not T11** | T11 is the corner 18 was set for. Its silence localised the fault |
| From lap 1? | **Yes, cold or hot** | Tyre degradation, front-right wear limit, thermal effects |
| Built as written? | **Yes** | Build error, driver deviation |

**Change: LSD acceleration 18 → 14, single isolated change. Result: fixed completely.** Driver: *"lsd change sorted it perfect."*

**Why 18 was wrong.** It was set by splitting the difference between the MR baseline (15) and generic Laguna guidance (20–28 for the T11 exit). Two errors compounded:

1. **Generic track guidance assumes an unrestricted car.** A restrictor-70 engine keeps its low-end torque and loses only top end, so it delivers proportionally *more* torque in the early corner-exit phase than the headline 525 bhp implies. More early torque through a heavily locked diff is the recipe for power-on push. **The restrictor setting and the accel-LSD value are coupled — re-test accel whenever the restrictor moves.**
2. **The value was aimed at one corner and paid for by every other.** T11 is a single dominant traction exit; T2–T5 are picked up on throttle with steering still wound on. Optimising for the former taxed the latter.

**The generalisable rules:**

- **For this car: 14 is the accel-sensitivity starting point on traction-limited, slow-corner circuits with a restrictor fitted** — *below* the MR baseline of 15, not above it. Go up only where one dominant traction exit sets the lap time.
- **Do not import a track's generic diff guidance without checking the build it assumes.**
- **The corner that is *not* complaining is diagnostic.** Ask for it every time.
- **A freer diff on this car is doubly right:** less lock means less rear scrub, and rear tyre life is the Huracán's scarce resource. The rotation fix and the stint-length fix pointed the same way — which is rare, and worth checking for on every future Huracán change.

**Restraint that paid.** Front ARB 5→4 and front downforce 425→450 were both queued as fallbacks and neither was needed. Both would have "fixed" a power-on symptom by adding front grip — masking the cause while giving up roll control at T6/T9 or entry stability. **This is the case that turned "diagnose before adjusting" from a principle into a logged result.**

**Still open on this car:** front toe never A/B'd; ballast −25 never compared against −50; whether 14 holds up on worn Hards; whether qualifying (Racing Softs, no stint to protect, T11 feeding the only straight) can carry 16–18. Full detail in `setups/2026-08-10-huracan-laguna-seca.md` §9.

### Shelby GT350R '16 — what it has taught us

**Sainte-Croix B**
- Initial pattern: rear loose on acceleration **plus** mid-corner understeer. The hydraulic throttle damper improved some exit control but did not eliminate the underlying chassis issue.
- Trail braking exposed a sketchy rear and rear step-out — confirming the car needed **better rear decel support, not simply more front rotation**.
- Changes that stiffened the car or removed rear security created grip loss over bumps and worsened throttle exit. **Sainte-Croix needs compliance.**
- The second-last downhill/left sequence is a useful diagnostic corner — mid-corner push there remained visible even after other areas improved.
- Consistency stayed limited while the rear was loose on exit. **The correct end state is not a faster single lap; it is a car that repeats the same balance lap after lap.**

**Watkins Glen Short — recent test sequence**
- Baseline: mid-corner understeer, throttle behaviour initially acceptable.
- As front rotation improved, the driver still wanted **more initial turn-in and more mid-corner bite** — confirming how sensitive the style is to a front axle that doesn't respond immediately.
- **Rear braking remained the major defect.** Moving brake bias forward for stability was explicitly rejected as the desired solution; going forward of neutral is not acceptable as a permanent answer.
- **No ABS in that session** made rear locking the dominant problem, which makes rear platform and brake-side LSD tuning the primary engineering target.
- After the throttle was recalibrated, exit behaviour changed and became more lively — **invalidating part of the previous exit diagnosis** and reinforcing hardware-calibration checking as step zero.
- Rear ride-height constraint: minimum **95 mm** rear on that setup. Stability must be found within the available geometry, not by assuming unlimited ride-height adjustment.

> **Shelby conclusion.** This car is the clearest proof that the ideal setup is **"front sharp, rear supported, platform compliant."** If any one of those three is missing, the Shelby magnifies the problem.

### Other learnings

- **Ford Escort RS Cosworth '92 — Bathurst.** Rear instability under braking through the Dipper. **AWD traction does not equal braking stability.** A car can feel secure on power yet rotate too abruptly when unloaded downhill under brake release. Rear decel control and bump compliance remain essential.
- **Brands Hatch GP — 525 bhp / 1300 kg build.** Mid-corner understeer on acceleration; needed both more hook-up and a slightly more pointed entry. Gearbox development moved from far too long to too short — ratio tuning must be iterative and based on actual corner exits and 6th-gear usage. Fuel testing showed the car roughly two laps short of making the event without refuelling in an economy mode: **gearing and fuel-saving are strategic variables, not just performance variables.** *(Note: "mid-corner understeer on acceleration" on the same 525 bhp restricted package is the same signature later resolved at Laguna by dropping accel LSD. Worth re-testing there.)* ⚠️ *[v1.70. On v1.71 lowering accel against a power-on push is CONTESTED - refuted on the Huracán at Daytona (s145), `02` §10.5.]*
- **Laguna Seca 20-lap build.** Gearbox too long plus a car that pushed wide. Reinforces the normal priority order: first restore usable front/mid-corner rotation, then set ratios around the actual speed range of the track rather than a maximum-speed number Laguna will never use. **Resolved 10 Aug 2026 — see the Huracán entry above; the push was accel LSD.**
- **Yas Marina Gr.4 selection.** The Alfa Gr.4 was rejected for excessive understeer. **Vehicle selection should screen for natural front response and rotation before investing heavily in setup.** A theoretically quick car that constantly fights the driver's rotation style is usually the wrong race choice.

---

## 12. Track archetype tuning rules

| Archetype | Examples | Default engineering priority |
|---|---|---|
| High-speed flowing | Spa, Watkins Glen, High Speed Ring | Rear aero/security, firm controlled platform, conservative front toe-out, longer gearing, stable brake LSD |
| Stop-start / heavy braking | Monza, parts of Fuji | Brake stability first, kerb compliance, longer 2nd, efficient aero, traction off slow exits |
| Bumpy / elevation | Bathurst, Sainte-Croix B | Mechanical compliance, rear decel stability, avoid over-stiff bars/rebound, predictable weight transfer |
| Technical medium speed | Fuji final sector, Brands Hatch | Strong front bite, controlled mid-corner rotation, careful accel-LSD tuning, front tyre management |
| Low top-speed / short straights | Laguna Seca style | Shorter useful ratio spread, prioritise mechanical grip and rotation over theoretical maximum speed. **Keep accel LSD low — a sequence of on-throttle corners punishes lock far more than one big traction exit rewards it.** |

---

## 13. Hardware and control philosophy

**Current rig**
- Fanatec DD Extreme wheelbase, updated to **18 Nm** capability
- Fanatec ClubSport V3 pedals, **load cell brake**, with a **hydraulic damper on the throttle**
- PS5 / GT7, with PSVR2 used heavily in the broader rig

**Feedback philosophy.** The wheel is *"a stethoscope with a steering rim attached."* Maximum useful **information** is the goal, not maximum heaviness. The driver wants to feel front loading, understeer onset, front locking, rear brake traction, rear instability and weight transfer early enough to act on it.

- Low filtering and fast response are preferred where they preserve detail.
- **GT7 in-game sensitivity has been run at 10**; reducing it materially reduced the ability to feel front lock and rear braking traction. That feedback channel is performance-critical.
- Force feedback, pedal damping and chassis setup must be considered together. A throttle damper can improve modulation **but must not become a hidden compensation for a traction problem.**

> **Engineering principle.** If the driver cannot feel the onset of the problem, the setup cannot be exploited consistently. Control-system tuning is part of the race-engineering package, not a separate cosmetic preference.

---

## 14. Head race engineer operating procedure

The sequence for every new car/circuit combination.

1. **Validate controls first** — throttle calibration, brake calibration / load-cell behaviour, steering range, FFB profile. Do not tune around faulty hardware.
2. **Build braking stability at neutral brake bias.** The rear must survive hard braking and the trail phase before chasing extra rotation.
3. **Lock in initial front response** with the smallest mechanical/geometry changes that achieve immediate bite.
4. **Fix mid-corner balance without sacrificing the rear.** Front ARB, front toe, diff acceleration and controlled rake are the targeted tools — **and the throttle-state question decides which of them applies.**
5. **Solve early-throttle traction.** Determine whether the problem is wheelspin/snap or power-understeer *before* choosing the LSD direction.
6. **Tune bump and kerb compliance.** If both ends lose grip over surface changes, soften the relevant platform control instead of adding stiffness.
7. **Build the gearbox around real corner-exit rpm and end-of-straight gear usage.** 2nd and 3rd are performance tools, not placeholders.
8. **Optimise aero for the event, not the time trial.** For races, include fuel cost, refuelling speed and tyre degradation in the decision.
9. **Run an A/B validation on one variable group at a time.** Preserve the driver's comments verbatim so a future setup can trace cause and effect.
10. **Only after the car is mechanically right** should brake bias become a small track/session adjustment rather than a rescue setting.

## 15. Future setup decision tree

| Question | Trigger | Action |
|---|---|---|
| Rear unstable under braking? | YES | Hold front-bite changes. Fix rear decel/platform first. Review brake LSD, rear toe, rebound/compliance, aero. Keep BB near neutral. |
| Rear stable, but turn-in lazy? | YES | Add front response in small steps: front mechanical grip / toe / aero, or modest rake. |
| Turn-in good, mid-corner pushes? | YES | **Ask where the right foot is — this is the fork.** Coasting → mechanical front grip. Power-on → **accel LSD down first, everything else second.** Validated at Laguna, §11 - on v1.70. ⚠️ *[CONTESTED on v1.71: lowering it was refuted on the Huracán at Daytona (s145) - `02` §10.5.]* |
| Mid-corner good, exit loose? | YES | Confirm pedal calibration, then distinguish snap wheelspin from gradual oversteer. Adjust LSD / rear toe / gearing accordingly. |
| Car loses both axles over bumps? | YES | Reduce stiffness / rebound severity. Do not solve with more aero alone. |
| Car stable but feels dead? | YES | Restore front communication/rotation. Do not accept "safe but slow." |
| Race fuel cost high? | YES | Evaluate lower drag, longer gearing and fuel-saving against total pit-time gain. |

---

## 16. Resolved contradictions (profile evolution)

- **Mid-corner understeer.** An early questionnaire suggested tolerance for slight mid-corner understeer. Later repeated feedback is more specific: a tiny safety margin is acceptable, but persistent push is disliked and costs confidence. **Current rule: neutral-to-slightly-safe, never lazy or washing wide.**
- **Brake balance.** Older setup work sometimes used rearward bias to unlock rotation; unstable no-ABS tests required temporary forward movement. The current explicit preference is **not to rely on forward brake bias**. Resolution: mechanical rear stability first, then brake balance around neutral as a fine adjustment.
- **LSD acceleration.** Some cases benefited from *reducing* accel sensitivity to free the car on throttle; other snap-wheelspin cases justified a small *increase*. These are not contradictions — they are **two different failure modes**. The profile demands diagnosis before adjustment. **Strengthened 10 Aug 2026:** the Laguna Huracán case confirms *reduction* as the correct direction for the power-on-push failure mode, and confirms that the diagnosis can be made from the driver's own description without telemetry.
- **Throttle style.** Naturally smooth, but the target has evolved from "smooth on throttle" to **intentionally using early partial throttle once the car is pointed** — converting rotation into acceleration sooner without provoking the rear.

---

## 17. Canonical driver profile card

| Attribute | Current engineering definition |
|---|---|
| Driver archetype | Front-end-led Precision Attacker |
| Primary lap-time weapon | Hard, accurate braking plus deep progressive trail release |
| Turn-in preference | Immediate / high bite |
| Mid-corner preference | Neutral with minimal safety understeer only |
| Rotation preference | Progressive, generated by weight transfer and brake release |
| Throttle preference | Early partial (5–20%), smooth progression, minimal wheelspin |
| Rear tolerance | **Low** tolerance for snap, skate, lock or float |
| Brake-bias philosophy | Car should work near neutral; do not hide rear instability with front BB |
| Suspension philosophy | Responsive front, compliant/stable rear, kerb/bump capable |
| Geometry philosophy | Mild front toe-out, mild rear toe-in, track-speed dependent |
| Diff philosophy | Stability-biased braking; acceleration **low and proven upward, never assumed** |
| Aero philosophy | Enough rear support first; trim drag only when stability remains |
| Gearbox philosophy | Circuit-specific, 2nd/3rd exit-focused, real top-gear validation |
| Race philosophy | Total stint/race time, fuel/pit economics, repeatability |
| Feedback philosophy | Information over heaviness; feel lock, slip and weight transfer |

---

## 18. How this profile is maintained

- Every new tune states **which driver-profile rules it is using**.
- Every test records the driver's exact symptom **by corner phase**: brake, entry, mid, early throttle, full exit, kerbs/bumps — **and the throttle state, and which corners were fine.**
- Every change identifies its **expected effect before** the driver tests it.
- When a change works, preserve both the value **and the reason it worked**. When it fails, preserve the failure too — failed changes are engineering evidence.
- **Preserve the changes that were considered and *not* made, and why.** The Laguna case is only fully useful because the rejected fallbacks are recorded alongside the fix.
- Qualifying and race setups stay separate whenever tyre, fuel or pit economics matter.
- Telemetry and video review distinguish **driver technique loss from setup loss** before changing the car.
- New evidence from a specific car or circuit can override a local rule, but should **not silently overwrite the core profile** unless the same preference repeats across multiple sessions.
