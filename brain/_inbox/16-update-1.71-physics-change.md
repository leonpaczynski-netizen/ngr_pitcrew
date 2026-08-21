# Update 1.71 — The Physics Change

**Released 20 August 2026 · GT7 v1.71 / 1.710 · this document opened 21 August 2026**
**Status: the knowledge base is now split into pre-1.71 and post-1.71. Nothing in the pre-1.71 half has been re-verified yet.**

---

## 0. Read this first

Standing Rule 1 says *"any GT7 setup published before August 2024 is void; anything before February 2025 is suspect."* **1.71 is the third event of that kind, and it is the largest since 1.49.** It touches the tyre model, the steering geometry of every car, the damper model, the default settings *and the adjustment ranges* of suspension, differential and aerodynamics, Performance Points across the whole fleet, both driving assists, and the damage model.

**The single strongest piece of evidence for how big it is comes from Polyphony themselves: they reset every ranking board in the game** — World Circuits, Licence Centre, Missions, Music Rally — and re-issued the Circuit Experience and Licence target times. PD do not reset leaderboards for a handling tweak. They reset them when old lap times are no longer comparable to new ones.

**What this document is.** The authoritative record of what changed, what it invalidates in this knowledge base, and what has to be re-measured before we can trust our own numbers again. It is a changelog and a work order, not a tuning guide. The tuning guides are `02`, `03`, `04` and `08`, each of which now carries a 1.71 banner pointing here.

**What this document is not.** It is not a set of new setup values. **Two days after a physics update, nobody has any — including us, and including every tuner on the internet.** §10 is explicit about how thin the public record currently is, and §12 is the plan for filling it ourselves.

### Confidence tags used here

- **[CONFIRMED]** — stated in the official Polyphony update notice. Quoted verbatim where the exact wording matters.
- **[PRESS]** — reported by GTPlanet, Traxion or MP1ST, interpreting the official notes rather than quoting them.
- **[COMMUNITY]** — a player report. Per Standing Rule 3 these are hypotheses, never facts. Single-source community claims are labelled as such.
- **[INFERRED]** — our own reasoning from the above. Ours to defend, and ours to be wrong about.
- **[UNKNOWN — MUST MEASURE]** — the honest state of most of the interesting questions. See §12.

---

## 1. The official change list

Everything in this section is **[CONFIRMED]** from the Update Notice (1.71) unless marked otherwise.

### 1.1 Tyres

> "The algorithm has been updated, focusing on the simulation when tyres are slipping."
> "Road surface resistance (rolling resistance) has been optimised."
> "Tyre heating and wear values have been adjusted."
> "The amount of tyre grip lost when 'Grip Reduction Off Track' is set to 'Real' has been adjusted."

Four separate changes, and note what the first one says: the rework is **concentrated in the slipping regime** — behaviour at and beyond the limit, not the linear range. **[PRESS]** GTPlanet reads this as "new calculations for rolling resistance, heating, and wear, primarily when the tires are slipping," and Traxion reports PD emphasising grip-loss simulation to produce "different car behaviour on the limit."

**The direction of the heating and wear change is not stated.** "Adjusted" is all we have. Faster or slower, hotter or cooler, is unknown.

### 1.2 Suspension, steering geometry and dampers

> "The steering geometry for each car has been optimised, improving the simulation of turning forces."
> "Damper attenuation characteristics have been changed to make stance changes and road surface tracking feel more natural."

"For each car" is doing a lot of work in the first line — this is a per-car change applied across the roster, not a global constant.

### 1.3 Defaults **and adjustment ranges**

> "Initial suspension settings and adjustment ranges have been fixed."
> "Initial differential gear settings and adjustment ranges have been fixed."
> "The initial aerodynamics settings and adjustment ranges on race cars have been fixed."

Aerodynamics defaults were also adjusted on certain road cars.

> **⚠️ This is the line with the largest consequence for us, and it is easy to skim past.** "Adjustment ranges have been fixed" means **the endpoints of the sliders moved** — not just the values they start at. `11-car-slider-ranges.md` is a register of exactly those endpoints, measured on v1.70. **Every entry in it is now unverified.** See §6.
>
> The word "fixed" here reads as *revised* / *corrected* (a translation from the Japanese notes), not as *frozen*. Nothing suggests the sliders became non-adjustable.

**The notes say nothing about what happens to saved car settings.** [PRESS] MP1ST explicitly notes the absence: "the patch notes do not explicitly address whether existing saved car settings require adjustment." Whether an existing tune survives intact, gets clamped to a new range, or gets reset is **[UNKNOWN — MUST MEASURE]** and it is the first thing to check in game (§12, Job 0).

### 1.4 Performance Points

PP was adjusted across the game. Event regulations were changed for the **Lightweight K Cup** and the **Power Pack Bump Drafting** event. **[PRESS]** Traxion describes it as a recalculation across the fleet, made necessary by the physics changes, and notes it may force adjustment for cars previously built to a specific PP cap.

### 1.5 Driving assists

> "The behaviour of the Traction Control (TCS) assist intervention has been optimised."
> "The slip ratio control and cornering brake behaviour under ABS has been adjusted."

### 1.6 Engine, throttle and gearing

- "Throttle control characteristics when drifting have been improved" and "car speed control on partial throttle has been improved" — **[PRESS]** GTPlanet attributes both to a new engine torque control map.
- **[PRESS]** The **downshift-prevention** system was adjusted: forced downshifts and engine over-rev are now possible earlier than under the December 2025 (1.66) implementation, though still more restricted than before 1.66.
- **Maximum RPM adjusted on six race cars:** Lexus RC F GT500 '16, Nissan GT-R NISMO GT500 '16, Super Formula SF19 (Honda and Toyota), Super Formula SF23 (Honda and Toyota). **None of our three cars is on this list** — which makes an unchanged limiter a useful internal consistency check during the comparison runs.
- Gear shift-up behaviour changed on the Red Bull X2019 models.
- Hyundai IONIQ 5 N front/rear torque distribution now freely adjustable, 0:100 to 100:0.
- Fuel consumption adjusted on two hybrids: Nissan Qashqai e-Power '22, Honda CR-V e:HEV '21. **Not a general fuel-model change** — two specific cars.

### 1.7 Damage

> "Adjusted the collision forces under which damage is incurred as well as the effects of damage to driving."

A new **"Championship"** mechanical damage setting was added:

> "Cars will be damaged in the same way as on the 'Light' setting, but from more minor collisions. Furthermore, recovery time will vary depending on severity."

So: **Light's damage severity, triggered by a lower collision threshold, with variable recovery time.** It sits between Light and full/Heavy in overall harshness — harsher than Light in *how often* it triggers, not in *how much* it hurts each time.

### 1.8 Penalties, leaderboards and hardware

- "Toned down the Shortcut Penalty judgement criteria."
- "All event ranking boards have been reset" — Music Rally, World Circuits, Licence Centre, Missions. Circuit Experience and Licence test target times were adjusted.
- Fanatec **FullForce** support (GT DD Pro pending a firmware update); Fanatec Auto Setup parameters optimised; steering wheel force feedback and **understeer vibration** adjusted; wireless controller steering and pedal response tuned.
- PS5 Pro PlayStation Spectral Super Resolution updated.

### 1.9 Content (no engineering consequence, recorded for completeness)

Four cars: Caterham Seven Superlight R500 '08, Hyundai IONIQ 6 N '25, Toyota Chaser Tourer V '97, Toyota Mark II Tourer V '97 (Caterham added to Brand Central). Three new World Circuits events. Circuit de Barcelona-Catalunya Rallycross layout added to Circuit Experience. Engine swaps for ten cars at Collector Level 50 — **including the Mitsubishi Lancer Evolution IX MR GSR '06 and the Ford Focus RS '18, both AWD, which `06` §8.3 identifies as the most PP-under-rated archetype in the game.** Whistler added to Scapes. Seasonal Menu added post-completion.

---

## 2. The invalidation ledger

What 1.71 does to each document in this knowledge base. **Every "void" below means the claim must be re-established, not that its replacement is known.**

| Doc | Status after 1.71 | What specifically is at risk |
|---|---|---|
| `01-driver-profile-leon.md` | **Mostly intact** | The driver's technique, non-negotiables and hardware philosophy are properties of Leon, not of the patch. But §11's accumulated car/track learnings were all measured on ≤v1.70 — the *diagnoses* stand, the *numbers* do not. |
| `02-gt7-setup-parameters.md` | **Ranges void; effects suspect** | Every stated slider range (§3.x). LSD 5–60 specifically — see §5. The symptom→fix tables are directional and probably survive, but the damper and steering-geometry reworks (§4) hit them directly. |
| `03-gt7-tyre-and-fuel-model.md` | **⚠️ Worst affected. Wear and heat sections void.** | §1.3 wear ratios, §2 the whole wear model, §2.4 lap-time-lost-per-wear table, §3 temperature, §4.4 stint-length derivations, §8 the tyre-friendly-setup logic. **Including our own [MEASURED — IN HOUSE] Laguna and Monza results.** See §3 below. |
| `04-race-vs-qualifying.md` | **Deltas suspect; framework intact** | The quali/race philosophy, the λ scalar and the mid-stint principle are engineering reasoning, not GT7 facts — they survive. The parameter deltas in §2 were calibrated on 1.49-lineage physics. §6.1's "tyre temperature is functionally inert" claim is now directly contradicted by a patch that adjusted tyre heating. |
| `05-track-reference.md` | **Largely intact; gearing targets suspect** | Circuit geometry doesn't patch. Downforce levels, gearing targets and pit deltas were derived under old aero defaults and old ranges. **Terminal-speed figures are exposed to the rolling-resistance change — see §3.3.** *(Also carries an outstanding correction: Monza's front wear side is left, not right.)* |
| `06-car-building-and-pp.md` | **PP content void** | PP was recalculated fleet-wide. Every build in the league may have moved relative to its cap. The *mechanism* (PP is a simulation, not a formula) is unaffected; the numbers are. **The file predicted this in its own §1.4 uncertainty flag.** |
| `07-car-profiles.md` | **Handling character suspect** | Per-car steering geometry was reworked — so the three cars may have moved *differently from each other*, which puts the comparative section (§6) most at risk. |
| `08-playbook-leon.md` | **Baseline sheet void; hierarchy intact** | Part B's baseline numbers were built on v1.70 ranges and v1.70 physics. The change hierarchy, the seven divergences and the session protocol are method, and method survives a patch. |
| `09-setup-sheet-format.md` | **Intact** | A format, not a fact. |
| `10-pit-crew-data-format.md` | **Intact as a spec, but incomplete** | **`meta.gameVersion` is missing and is now required by Standing Rule 10.** Priority-one fix. |
| `11-car-slider-ranges.md` | **⚠️ Entirely unverified — all three cars** | This file exists to record slider endpoints. 1.71 moved slider endpoints. See §6. |
| `12`–`14` (Pit Crew lineage) | **Intact as specs** | But the app's range library inherits `11`'s now-stale numbers. |
| `15-pitcrew-detector-audit.md` | **Intact, and more important than before** | Rules 8 and 9 exist because telemetry lied. With every physics baseline unverified, the discipline of not letting a flag buy a change matters more, not less. |
| `setups/` (all sheets) | **Pre-1.71. Historical record and control group.** | See §7 and `setups/00-PRE-1.71-NOTICE.md`. |

---

## 3. Tyres and strategy — the priority

This is where the damage is worst and where the re-measurement effort goes first.

### 3.1 What we actually know

**[CONFIRMED]** Four things changed: the slipping-regime algorithm, rolling resistance, heating values, wear values, and off-track grip loss on the "Real" setting.

**That is the complete list of what is known. The direction and magnitude of every one of them is unstated.**

### 3.2 Why this is worse for us than for most people

`03` is the most heavily worked document in this knowledge base, and almost all of its authority came from the post-1.49 model being *stable* for two years. Specifically at risk:

1. **§1.3.1 — the Laguna Racing Soft measurement.** Huracán GT3, RS, 2× wear: 11–12 laps before fall-off. **And the Monza result alongside it** — RSR, Racing Hard, 8×: 15 laps with ~9 ms/lap true degradation. **These were our two most valuable numbers and both are now v1.70 numbers.** They do not automatically transfer. They are not deleted — they remain the correct *method*, valid historical datapoints, and now the control groups for the comparison runs.
2. **§2.2's piecewise curve** (flat to ~50%, progressive to ~90%, cliff beyond). The cliff was a 1.49 artefact. A patch that rewrites the slipping regime is exactly the kind of patch that reshapes a cliff. **[UNKNOWN — MUST MEASURE]**
3. **§2.5's driving-style ranking**, which puts lateral slip first by a wide margin. That ranking came from 1.49 making sliding the dominant wear source. 1.71 explicitly re-does the slipping simulation. The ranking could be reinforced, softened, or inverted. **[UNKNOWN — MUST MEASURE]**
4. **§3's temperature section**, which concluded temperature is "real but rudimentary" and, in `04` §6.1, "functionally invisible in practice." **A patch that adjusts tyre heating values is prima facie evidence that heat is being taken more seriously.** [INFERRED] These two documents already disagreed with each other about temperature; 1.71 makes resolving that disagreement a live priority rather than a curiosity.
5. **§8.1's core principle** — "a tyre-friendly setup is one that reduces the slip angle required to generate a given lateral force." This is sound vehicle dynamics and survives as reasoning. Whether it still describes *GT7's* wear function is the open question.

### 3.3 Rolling resistance — the quiet one, and the one with the cleanest available probe

"Road surface resistance (rolling resistance) has been optimised" is the least discussed line in the notes and it has direct strategic consequences [INFERRED]:

- Rolling resistance is a **fuel** term as much as a tyre term. A change here moves L/lap independently of anything the driver does.
- It is also a **top-speed and gearing** term. Terminal velocity at the end of a straight is set by drag *and* rolling resistance.
- **Every fuel figure in `03` §5 and every gearing target in `05` is therefore suspect**, not just the tyre numbers. So is every gearing constant K we hold: the RSR's measured 1,128, the Shelby's 1,096, and the Huracán's unresolved 1112.6 / 1092.5 extrapolations.

Note that 1.49's notes contained the *same* line about rolling resistance. So this is PD returning to a term they have tuned before, not touching it for the first time.

> **⭐ And it has the single cleanest measurement available to this programme — see §12 Job 2A.** Rolling resistance shows up loudest as **terminal speed on a long straight at a drag-limited circuit**. We have ~200 laps of RSR data at Monza, including a clean-air Vmax reading of **278.7 km/h at 8,009 rpm against a measured 8,600 rpm limiter**. **That combination — the most drag-limited circuit in regular use, against the largest baseline in the knowledge base, with a documented no-tow terminal-speed observation — is the best instrument anyone has for this change, and it is sitting unused.**

### 3.4 What this means for strategy right now

**Do not plan a stint on any number currently in this knowledge base.** `03` §1.3.1's own standing rule already covers this and it now applies to everything:

> **No modelled wear figure in this knowledge base may be used to select a race compound. Measure one stint at the actual multiplier, then choose.**

The rule was written because a *model* was 1.8× wrong at Laguna, and reinforced when the same model proved 5× wrong at Monza. It now applies for a third reason: because the *measurements* are from a previous version of the game.

---

## 4. Suspension, steering geometry and dampers

**[CONFIRMED]** Two changes, both structural:

**Steering geometry, per car, "improving the simulation of turning forces."** [INFERRED] Steering geometry governs how steer angle and suspension travel convert into slip angle and camber gain at the front axle. If PD reworked it per car, then:

- **Camber sensitivity may have changed.** `03` §8.3's headline finding — that in GT7 negative camber *reduces* grip in a way that doesn't match reality — is a symptom of the geometry model. A geometry rework is precisely what would fix or change that. **This is the single most testable claim affected, and `03` §10 already lists the front/rear camber swap check as "five minutes to falsify."** It is now worth doing for real.
- **Toe sensitivity may have changed** for the same reason. Note that GT7 front-toe behaviour was *already* disputed (`08` A3) — a genuinely contested parameter has just been re-rolled, and may finally resolve cleanly.
- **Turn-in character is per-car**, so the three cars in `07` may have moved differently from each other.

**Damper attenuation, "to make stance changes and road surface tracking feel more natural."** [INFERRED] "Stance changes" is pitch and roll transitions; "road surface tracking" is bump compliance. Together they are the two things damping is for, so this is a genuine damper model change rather than a value tweak.

Consequences to test, not to assume:
- `04` §2.4's race-trim damper deltas (−2 to −5 compression, −2 to −3 expansion) were tuned against the 1.49 damper model.
- The 20–40 / 30–50 damper windows in `11` are *ranges*, and ranges were explicitly revised (§1.3). **The windows themselves may have moved**, independently of what the values now do.
- **`02` §3.4's quirk that "post-1.49, dampers do less than you expect"** is exactly the complaint this change reads as a response to. **If dampers do more now, `02`'s four-quadrant table gets stronger and the workflow ordering changes.**
- **The 1.49 bottoming problem.** `00-INDEX` Settled Facts records it as real and still live in 2026, with 1.55 having addressed only short-period bumps. A damper attenuation rework plus revised suspension defaults is the most plausible candidate yet for changing it. **Status: [UNKNOWN — MUST MEASURE].** Do not assume it is fixed; do not assume it is unchanged. Rule 8 still stands — the trigger is the driver symptom or a four-wheel mean-heave figure, never a Pit Crew `bottoming` flag.

---

## 5. The differential

**[CONFIRMED]** "Initial differential gear settings and adjustment ranges have been fixed."

**[COMMUNITY — single source, GTPlanet undocumented-changes thread]** One player reports:

> "Fully Customizable Diff can be set to 0/0/0 — never before that was possible."

If true, this is a **structural change, not a tweak**. The LSD scale in `02` and `11` is recorded as **5–60 on all three parameters, confirmed on three cars across two classes**. A floor of 0 means:

- **A genuinely open differential is now buildable** for the first time in the series.
- Every LSD baseline in this knowledge base — `03` §8.5's per-layout table, `04` §2.5's quali/race deltas, `08`'s baseline sheet — was written against a floor of 5. Those numbers are not wrong *per se*, but the space below them is new and unexplored.
- **Our own best LSD finding is directly in the firing line.** The Huracán's MR acceleration-sensitivity baseline of 15 proved to be "a ceiling, not a midpoint, on a restricted build," with 14 resolving power-on mid-corner understeer that 18 caused — **and the RSR at Monza independently landed on 14 from 16.** Two cars, two circuits, same direction. **Both findings are about the bottom of a 5–60 range. If the range now starts at 0, the useful territory extends further down than we have ever looked.**

> **Do not act on this yet.** It is one person's report, two days after release, and it is a range claim — exactly the kind of thing §12's first job settles in thirty seconds by opening the settings screen. **Confirm it before it changes a single setup.**

---

## 6. The slider register is void

`11-car-slider-ranges.md` records min/max for 22 parameters on three cars, measured on v1.70. Its own closing section anticipated this exactly:

> "Update 1.49 and 1.55 both pushed new default suspension and differential settings to large parts of the car list. Whether they moved the *endpoints* as well as the defaults is not documented either way. After any physics-tagged update, spot-check ride height and natural frequency on one recorded car before trusting the register."

**1.71 removes the ambiguity. The notes say adjustment ranges were revised, for suspension, differential and aerodynamics.** A spot-check is no longer sufficient — the whole register needs re-reading.

What is at stake if it is used stale:

- **The 13/9 split** — 13 class-independent parameters vs 9 chassis-derived — is the register's headline finding and the basis for issuing 13 sliders in absolute numbers on day one for any new car. **All three of the categories PD named (suspension, differential, aero) contain parameters on both sides of that split.** The split may survive, may shift, or may dissolve.
- **The Gr.3 class constants** (3.00–5.00 Hz, 55–80 / 60–90 mm, 350–450 / 500–700 downforce, ±1.00° toe) underpin every Gr.3 sheet.
- **Percent-of-range targets silently change meaning when a range moves.** This is the same failure mode that `11` documents twice already — the natural-frequency heuristic on the RSR, the ride-height heuristic on the Shelby. A moved endpoint does it to every parameter at once, without anyone noticing.

**The cheapest clamp detector on any car we own: the RSR's front natural frequency sits at 3.05 Hz on a 3.00 Hz floor — five clicks.** If that floor moved at all, the settings screen shows it immediately.

**Action: re-read all three cars. 15 minutes total. It is the single highest-value quarter hour available and it blocks everything else.** See §12.

---

## 7. The archived setups

All sheets under `setups/` were built and run on v1.70 or earlier. They are now **historical record and control group**: valid as a log of what was tried, why, and what the driver reported, and invalid as a source of values to type into the game. **A folder-level notice is filed at `setups/00-PRE-1.71-NOTICE.md`, and the most consequential sheets carry their own banners.**

They are being stamped rather than deleted, for three reasons:

1. **The diagnoses are the valuable part, and diagnoses survive patches.** "Power-on mid-corner understeer from lap 1, resolved by dropping LSD accel from 18 to 14" is a reasoning chain. Only the two numbers are version-dependent.
2. **They are the control group.** When a car is re-baselined on 1.71, the pre-1.71 sheet is the only thing to compare it against. Delete it and the comparison is gone. **This is not abstract — §12 Job 2A is built entirely on the existence of ~200 laps of prior RSR data at Monza, and on the Rev B sheet that documents its numbers.**
3. **The 17 Aug win** (`setups/2026-08-17-huracan-watkins-glen-long-revC.md`) is the reference for what a working setup felt like on this car. Rev D exists to build on it.

**What must not happen: a 1.71 session run on a pre-1.71 sheet without saying so.** That is Standing Rule 9's failure mode — diagnosing a car that isn't the car on the circuit — amplified by a physics change.

---

## 8. Assists

**[CONFIRMED]** TCS intervention behaviour "optimised"; ABS "slip ratio control and cornering brake behaviour" adjusted.

Both matter to this driver specifically. `03` §2.5 records TCS as costing up to two tenths per corner under the 1.49 model while measurably reducing rear wear on spin-prone cars — a real trade with a known price. **That price is now unknown.** [INFERRED] "Optimised" intervention most often means less intrusive, which would lower the cost of running TCS 1 and change the sprint-vs-stint calculus in `03` §2.5. It could equally mean earlier intervention. Untested either way.

ABS "cornering brake behaviour" is the more interesting line: it names the trail-braking phase directly. `04` §2.8 and `01`'s technique notes both lean on trail-braking behaviour under ABS. **And it is the direct test of `08` A4's central claim** — that the rear can be stabilised mechanically, at brake balance 0, using LSD braking sensitivity. That claim has now held across four sessions on two cars, including Monza with ABS Weak and the three heaviest stops in Gr.3. **[UNKNOWN — MUST MEASURE] on this version.**

Also relevant to feel rather than physics: **steering wheel force feedback and understeer vibration were adjusted**, and Fanatec Auto Setup parameters were optimised. On a DD Extreme this is worth a deliberate check — an FFB change can be misread as a grip change, and on an 18 Nm wheel it will be felt clearly. **Separate the two before diagnosing anything.**

> **⚠️ And it is a live contamination risk for every measurement in §12.** A back-to-back comparison against pre-1.71 data is only valid if the wheel is delivering the same forces it was. **Confirm the wheel settings before any of the comparison runs, not after.**

---

## 9. Damage — the "Championship" setting

**[CONFIRMED]** Collision force thresholds and the driving effects of damage were both adjusted, and a new **Championship** setting was added: Light's damage severity, from more minor collisions, with recovery time varying by severity.

**League relevance.** This is a regulation lever, not a setup lever, and it is a good one for a no-BoP open-tuning league:

- It penalises contact more readily than Light without the race-ending consequences of full damage.
- **Variable recovery time is the genuinely new mechanic** — a light brush costs less than a heavy hit, rather than both costing the same fixed penalty.
- [INFERRED] It should reduce the "dive-bomb is free" problem in first-lap traffic, which is exactly the risk `04` §3.3 prices in when it argues for biasing setup toward the start in packed opening laps.

**Setup consequence, if the league adopts it** [INFERRED]: it raises the value of everything in `04` §7.2 and §7.3 — braking stability off-line, predictability under contact, compliance. It shifts the λ scalar's "expected traffic" term upward. **Worth raising with whoever sets the league regulations before the next round**, alongside the PP re-scrutineering (`06` §9.3).

---

## 10. What the community record actually says — and does not

This section exists to stop anyone, including a future session of this project, from over-reading day-two forum chatter.

**As of 21 August 2026, roughly one day after release, there is no substantive public tuning analysis of 1.71.** Checked: the GTPlanet undocumented-changes thread for 1.71, the GTPlanet news thread, and general search. Findings:

| Claim | Source | Standing |
|---|---|---|
| Fully Customisable Diff can be set to 0/0/0 | GTPlanet undocumented-changes thread, **one player** | **[COMMUNITY — single source]**. High value if true. Confirm in game (§12). |
| "Throttle feels and looks a lot more linear" | Same thread, **one player** | **[COMMUNITY — single source]**. Consistent with the confirmed torque-map change, so plausible, but it is an impression. |
| Players recalibrating suspension setups post-update | Same thread, general | **[COMMUNITY]**. Expected behaviour after any physics patch; carries no information about direction. |
| Sophy support extended to LMH and other cars; Aston Martin Vantage '18 added, Ford Focus RS '18 removed | Same thread | **[COMMUNITY]**. Not engineering-relevant to us. |

**No measured wear data. No stint lengths. No lap-time deltas. No temperature findings. No confirmed PP movements on specific cars. No first-hand report on whether saved tunes survived.**

> **[INFERRED] The practical conclusion is the useful one: for the next week or two, anyone with measured 1.71 data has an advantage, and the measurements are cheap.** The gap `03` §10 has always complained about — that nobody publishes controlled post-patch wear data — is at its widest right now, and it applies to the whole field equally. This is the best opportunity this programme has had to build a real edge, and it closes as the community catches up.
>
> **⭐ And we have something almost nobody else does: a large pre-patch baseline on a fixed car/track combination.** ~200 laps of RSR data at Monza is a *distribution*, not a datapoint — which means a post-patch run can be tested against a known median and a known spread rather than compared to a single lap. **That is a level of rigour the forums will not reach for weeks, if at all.** See §12 Job 2A.
>
> **Corollary, and it is Standing Rule 4 with a new edge:** any "GT7 1.71 tune" appearing in the next fortnight was almost certainly not measured. Anything mentioning tyre pressure, caster, brake pressure, or high/low-speed damper splits is pattern-matched from another sim and unreliable throughout — that test has not changed.

---

## 11. What is now known to be *unknown*

Consolidated, because this is the honest state of the knowledge base and it should be visible in one place.

**Tyres and strategy**
1. Direction and magnitude of the wear change. Faster? Slower?
2. Whether the ~50% inflection and ~90–95% cliff still exist, and where.
3. Whether lateral slip is still the dominant wear mechanism.
4. Whether tyre heat now does something the driver can feel — warm-up, optimum window, overheating.
5. Whether the RH:RM:RS ratio moved (it was never measured pre-1.71 either).
6. Whether rolling resistance changed fuel L/lap and terminal speed.

**Chassis**
7. Every slider endpoint on all three cars.
8. Whether LSD now floors at 0.
9. What the steering geometry rework did to camber and toe sensitivity.
10. What the damper attenuation change did to the 20–40 / 30–50 working windows — and whether dampers got their authority back.
11. Whether the 1.49 bottoming problem survived.

**Build**
12. Where each of our three builds now sits on PP.
13. Whether aero defaults moving changed the PP cost of aero (aero was never PP-free and moved non-monotonically).

**Assists, hardware and technique**
14. TCS intervention cost per corner.
15. ABS cornering-brake behaviour under trail braking — and with it, whether `08` A4's brake-balance-0 approach still holds.
16. How much of any felt change is FFB rather than grip.
17. **Whether the short-shift points are still right.** The technique won the 17 Aug race and the Pit Crew shift beep encodes RPM points derived against the old torque map. **1.71 replaced that map.** Repeatability is unaffected; optimality is not.

**Carried over from before 1.71 and still open** — these did not go away, and several got cheaper to close now that a full re-measurement session is happening anyway: slider step sizes (four sessions overdue), the Huracán gearing constant K, the drivetrain declaration to Pit Crew, the Watkins Glen corner-ID mapping, and `05`'s Monza wear-side correction. See `00-INDEX` Open Items.

---

## 12. The re-measurement protocol

Ordered by *information per minute*, not by importance. Everything early is cheap and unblocks something else.

### Job 0 — Does the old tune still exist? (2 minutes, do this first)

Open a car that has a saved sheet and, **before changing anything, read the current values off the settings screen and compare them to the archived sheet.**

Three possible outcomes, and each sends the work in a different direction:
- **Values unchanged** → tunes survived; the register re-read (Job 1) is the only urgent chassis work.
- **Values changed to new defaults** → every saved setup in the garage is gone; re-entering them from the archived sheets is the first task, and §7's stamped sheets become operationally essential rather than historical.
- **Some values changed, others not** → the changed ones were clamped by a moved range. **This is the most informative outcome**, because the clamped values map out exactly where the new endpoints are.

**Record which one happened, verbatim, before touching anything.**

> **⚠️ Job 0 is a hard prerequisite for Job 2A.** A back-to-back against ~200 laps of history is only a physics comparison if the car is in the same state of tune. If anything was clamped or reset, you are comparing two different cars and the baseline stops being a control. **Do Job 0 on the RSR against `setups/2026-08-12-rsr-monza-revB.md` §4, not only on the Huracán.**

### Job 1 — Re-read the slider register (15 minutes, 5 per car)

All 22 parameters, all three cars: Porsche 911 RSR (991) '17, Lamborghini Huracán GT3 '15, Ford Shelby GT350R '16. Same procedure as before — drag each slider to each end, read the number.

**Three additions to the procedure this time:**
- **Record the step size while the screen is open.** Four sessions overdue, five seconds per slider, and every click count in every sheet is an estimate until it is done. *(The RSR's natural-frequency step is already known: 0.01 Hz.)*
- **Check the LSD floor explicitly** (§5). If it reads 0, that is the confirmation, and it is worth its own line in the register.
- **Note the new defaults, not just the endpoints.** 1.71 revised initial settings as well as ranges, and `06` §1.2 records a single-source claim that PP is computed from the *default* diff and suspension settings — which, if true, is the mechanism by which a car's PP could move with no user action at all.

Compare against the v1.70 entries and note every change. **This blocks every sheet that can be issued, so it goes first.**

### Job 1b — Confirm the wheel (5 minutes)

1.71 adjusted **steering wheel force feedback and understeer vibration**, and optimised **Fanatec Auto Setup parameters**. **On an 18 Nm DD Extreme that reads exactly like a grip change**, and it would be baked silently into every comparison that follows.

Confirm the settings are where you left them, and take a couple of laps consciously separating "the wheel feels different" from "the car has less grip." **Do this before Job 2A, not after.**

### ⭐ Job 2A — The Monza RSR control run (30 minutes) — *driver's proposal, 21 Aug 2026*

**Porsche 911 RSR (991) '17, Monza, Racing Hard, 10 laps, 8× tyre / 3× fuel, against ~200 laps of pre-1.71 data on the same car and circuit.**

**Why this is the strongest single measurement available, and it is not primarily about tyres:**

1. **It is the only comparison in the programme with a real baseline distribution.** Every other measurement here is n=1 with no error bar. **~200 laps gives a known median *and* a known spread**, so a 10-lap run can establish whether a delta lies outside normal session-to-session variance rather than merely differing from one previous lap. `03` §4.1 already identifies driver variance as the largest error term in every measurement we take; this is the only run that can quantify it away.
2. **Monza is the best available probe for the rolling-resistance change** (§3.3) — the least-discussed line in the patch notes and the one with the widest blast radius (fuel, gearing, terminal speed). A drag-limited circuit with two long straights is where a change in road-surface resistance is loudest, and the RSR is the most straight-line-limited car in the garage (`07` §2.2), which makes it the most sensitive instrument.
3. **Racing Hard over 10 laps isolates grip and resistance from wear** — the compound gave 15 laps with ~9 ms/lap true degradation on v1.70, so it barely degrades over that distance. The run measures the physics change without the wear change confounding it. **That is a feature of the design, not a limitation.**

**The baseline, from `setups/2026-08-12-rsr-monza-revB.md` (11 Aug 2026, 36 laps, 28 counted):**

| Measure | v1.70 baseline | What a change tells you |
|---|---|---|
| **Clean-air Vmax in 6th** | **278.7 km/h @ 8,009 rpm** | ⭐ **Rolling resistance.** The cleanest single probe available. |
| **Observed limiter** | **8,600 rpm** | Should be unchanged — the RSR is not on 1.71's max-RPM list (§1.6). **If it reads differently, something bigger happened.** |
| **Gearing constant K** | **1,128.3** | Derived from the two above. Re-derives for free. |
| **Median, 28 counted laps** | **1:49.180** | ⭐ **Pace.** The spread matters as much as the median. |
| **Best clean valid lap** | **1:46.828** | ⚠️ **NOT 1:44.912** — that is a timing artefact (it burned 0.16 L) and comparing against it would manufacture a phantom ~2 s regression. |
| **Fuel, map 1, no short-shift** | **6.566 L/lap**, independently confirmed at 6.571 | ⭐ Rolling resistance from the other side. **Note the no-short-shift condition — see the run-mode decision below.** |
| **True degradation, RH @ 8×** | **~9 ms/lap** (raw −17.8, net of fuel burn-off) | If 10 laps shows materially more, **that is the wear change, measured, with a control.** |
| **Four-corner temps, lap 36** | FL 74.5 · FR 68.3 · RL 85.7 · RR 82.6 °C | ⭐ **The heat probe.** 1.71 adjusted tyre heating values, and `03` §3 and `04` §6.1 openly disagree about whether temperature matters at all. **Nearly a free answer to a two-week-old contradiction.** |
| **Limiting corners** | FL 0.79, RL 0.84 — both **left**, because Monza's three sustained corners are rights | **If the limiting corner changes side, that is a steering-geometry signal.** |

**⭐ Run mode — short-shift, with a full-RPM tail. Driver's call, 21 Aug, and it is the right one.**

The Rev B baseline was recorded at map 1 with no short-shifting. **But the driver reports that across the ~200-lap Monza history, few laps were run at full RPM** — most were short-shifted, as at Watkins Glen. **The point of this run is the size of the comparison set, so match the dominant baseline, not the documented session.** Running full-RPM would compare against a thin slice and discard the run's only real advantage.

Three things make that hold up:

- **Use the app's shift beep.** Short-shifting is a *driver input*; if the shift points wander, that is variance stacked on top of the physics delta. The beep makes it repeatable, and **repeatability is what a controlled comparison needs — not optimality.**
- **⚠️ The beep's RPM points were derived against the old torque map, which 1.71 replaced.** They may no longer be the *best* points. **That does not hurt this comparison** — as long as the beep fires where it fired before, the comparison is clean. It does make "should I still be short-shifting there?" a separate and genuinely interesting question (§11 item 17).
- **The Vmax reading is unaffected by the choice.** You reach terminal speed at full throttle in 6th at the end of the main straight regardless of how you got up through the gears. **The single most diagnostic number in the run does not care about run mode at all.**

**Then add 2–3 full-RPM laps at the end.** Five minutes, and it touches the documented 6.566 L/lap and 1:49.180 references directly. **One run, both comparisons.**

**Prerequisites — without these the run is worthless:**
- **Job 0 on the RSR**, against Rev B §4. If any value was clamped or reset, the baseline stops being a control.
- **Job 1 on the RSR** (5 minutes, same session). **Check front natural frequency first** — it sits at 3.05 Hz on a 3.00 floor, five clicks, which makes it the cheapest clamp detector on the car.
- **Job 1b — confirm the wheel.**
- **Match the multipliers: 8× tyre, 3× fuel.** The fuel and wear baselines are meaningless against different ones. **And confirm the tyre multiplier actually reads 8×** — Rev B §5.1 flagged that check as never done, and the whole baseline rests on it.
- **Same compound (Racing Hard), same assists (ABS Weak, TCS 0), same sheet, clean air for the Vmax reading.**

**What to record, in this order:**
- **Driver report, verbatim, before looking at any number** — Standing Rule 7. Especially on the grip-to-slip transition (`04` §1.2a), which 1.71's slipping-regime rework targets directly, and on kerb behaviour at the chicanes (the damper change — `08` A7).
- **Vmax in 6th and the rpm at it**, clean air, no tow.
- **Median and spread over the 10 laps**, against the historical median and spread.
- **Sector times**, so a delta can be localised to straights (resistance/drag) versus corners (grip/geometry).
- **L/lap**, short-shift and full-RPM separately.
- **Four-corner tyre temps at a fixed lap.**
- **Which corner's gauge is worst**, and on which side.

**The two most diagnostic numbers are Vmax and the median lap.** Vmax moved but median didn't → rolling resistance. Median moved but Vmax didn't → grip or geometry. Both moved → the sector times separate them.

**What it will not answer:** tyre wear at a meaningful rate. Hards over 10 laps will not move the gauge far. **Jobs 2 and 3 below still stand** — these are complementary, not competing.

> **This job goes before Job 2 in execution order**, because it is the one with the control group and because its result calibrates how much to trust everything measured afterwards. If it shows the RSR's pace and terminal speed essentially unchanged at Monza, that materially narrows what 1.71 did. If it shows a large delta, every subsequent measurement gets read in that light.

### Job 2 — The tyre stint, on the car and track that matter (30 minutes)

Per Leon's stated priority, tyres and strategy come before everything else.

**Huracán GT3, Watkins Glen Long, Racing Soft, at the multiplier the league actually races.** Full fuel, genuine race pace, run until fall-off is *felt*, not until the gauge reads a number (`03` §4.4's procedural notes stand).

Record per lap: lap time, wear percentage at all four corners, and the lap at which the balance shifts. That gives, in one run:
- the new stint length,
- whether the cliff still exists and where,
- which axle is limiting now,
- and a direct comparison against the pre-1.71 Watkins Glen stints — including the Rev D finding that RS showed no measurable fall-off inside 12 laps at 2×, which is the single conclusion a race would be planned around.

**Then the run that has been asked for four sessions running and never taken: a rear-left gauge reading at lap 6 and lap 12.** It is five seconds of attention inside a run that is happening anyway.

**Blocked on one thing that has also been asked for twice: the Watkins Glen corner-ID mapping.** Pit Crew's segmenter finds 9 corners on an 11-turn circuit. Without the mapping, corner-level results from this run are unattributable.

### Job 3 — The RM comparison run (30 minutes)

Same car, same track, same multiplier, **Racing Medium.** This closes the RH:RM:RS ratio question that `03` §10 has had open since the document was written, and it is only cheap while Job 2's conditions are still set up. **Do it in the same session or it will not get done.**

### Job 4 — PP audit on all three builds (10 minutes)

Read the current PP of each of the three cars as built. Compare to the figures in the setup sheets. **If a build has moved relative to a league cap, that is a race-weekend problem, not a tuning problem, and it needs raising with the organisers immediately.**

While in the build screens: re-check whether the Fully Customisable Suspension PP cost (measured at +9.1 PP on one car pre-1.71) has moved, whether aero's PP behaviour is still non-monotonic, and whether body rigidity and wide-body still *lower* PP (`06` §6.6 — free performance if they do).

### Job 5 — Camber and front toe A/B (30 minutes, one session)

The steering geometry rework makes these the most likely long-standing findings to have changed, and both have been listed as five-minute tests for two weeks.

**Camber:** same car, same track, three laps each at front camber 0.5°, 1.5°, 2.5°. If more camber still costs grip, `03` §8.3 survives. If it doesn't, **that is the biggest single tuning change 1.71 brings us** and it rewrites the camber guidance in `02`, `03`, `07` and `08`. Run the front/rear swap check at the same time.

**Front toe:** −0.05 / 0.00 / +0.05, three clean laps each (`08` A3). GT7's most disputed parameter, sitting on the driver's #1 priority, on the car being raced — **outstanding for four sessions**, and toe sensitivity is downstream of the same reworked geometry, so the dispute has just been re-rolled.

### Job 6 — Tyre temperature, finally (30 minutes, telemetry required)

`03` §3.2 and `04` §6.1 disagree about whether GT7's tyre temperature matters. 1.71 adjusted heating values. **Log `tyreTemp[4]` across a stint and correlate against sector times.**

`03` §10 has called this "the most valuable and most tractable remaining item" and "the highest-value original testing available to you and nobody has done it publicly" since the document was written. **That was true before the patch adjusted heating. It is more true now** — and Job 2A's four-corner comparison against a known baseline is a free head start on it.

### Job 7 — Assists baseline (15 minutes)

Three laps TCS 0, three laps TCS 1, same car and track. Note the per-corner cost and whether intervention feels earlier or later than before (`03` §2.5 puts the v1.70 price at up to two tenths per corner).

**And re-establish the braking reference**: ABS Weak, brake balance 0, LSD braking sensitivity as on the sheet. `08` A4's central claim — that the rear can be stabilised mechanically without moving bias forward — has held four sessions running on two cars, and 1.71's ABS cornering-brake change is exactly what would test it.

### Job 8 — Re-baseline each car (one session each, after Jobs 1, 2A and 2)

Only once the ranges are known and the comparison runs are in. Start from the pre-1.71 sheet as a *starting point*, not as a setup, and re-walk the change hierarchy in `08`. **One change per run, three clean laps minimum** — Standing Rule 5 does not get suspended because the patch is new. If anything it matters more: with every baseline unverified, a two-change run is uninterpretable.

### Execution order, if time is short

**Job 0 → Job 1 → Job 1b → Job 2A → Job 2 → Job 3 → Job 5 → Job 4 → Job 6 → Job 7 → Job 8.**

The first four are about ninety minutes and between them establish: whether the garage survived, what the sliders can do, whether the wheel is lying to you, and how big the physics change actually is against a real baseline. **Everything after that is easier to interpret for having done them.**

---

## 13. New standing rules

Applied in `00-INDEX` as rules 10, 11 and 12.

> **10. Every setup sheet, measurement and telemetry packet carries its game version.** `03`'s maintenance note already requires date, car, track and multiplier on every measurement. **Version joins that list.** A number without a version is a number that cannot be trusted after the next patch — and there is always a next patch. **Currently unenforceable on Pit Crew exports: `meta.gameVersion` is missing from the packet. Priority-one fix.**

> **11. After a physics-tagged update, the slider register is re-read before any sheet is issued.** 1.71 revised adjustment ranges explicitly. `11`'s "spot-check one car" guidance was written when it was ambiguous whether endpoints ever moved; it is not sufficient now. Full re-read, all recorded cars, before the first sheet.

> **12 (proposed, pending Job 2A). Where a baseline distribution exists, measure against the distribution, not against a single prior result.** The knowledge base's recurring weakness is n=1 findings presented with more confidence than they can carry — the wear model was 1.8× wrong at Laguna and 5× wrong at Monza, and `08` Part G's meta-lesson documents both. **A median and a spread is a different class of evidence from a lap time.** Where a car/track combination has accumulated history, use it — **and match the run to the dominant condition in that history, not to whichever session happens to be written up.**

And an amendment to the existing Rule 1:

> **1 (amended).** Any GT7 setup published before August 2024 is void; anything before February 2025 is suspect; **anything before 20 August 2026 is pre-1.71 and must be re-validated before use, including our own.**

---

## Sources

**Official (Polyphony Digital / gran-turismo.com)**
- [Update Notice (1.71) — GT7 Updates (GB)](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html)
- [Update Notice (1.71) — GT7 Updates (US)](https://www.gran-turismo.com/us/gt7/news/00_3638095.html)

**Press**
- [Gran Turismo 7 Update 1.71 Arrives With Major Physics Changes & Fanatec FullForce Support — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Gran Turismo 7's latest update brings sweeping physics changes, resets leaderboards — Traxion](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [Gran Turismo 7 August Update Races Out via Patch 1.71/1.710 — MP1ST](https://mp1st.com/title-updates-and-patches/gran-turismo-7-august-update-races-out-via-patch-1-71-1-710)

**Community (treat as hypotheses — Standing Rule 3)**
- [Gran Turismo 7 Undocumented Changes Thread (1.71) — GTPlanet](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-1-71.439041/)
- [GT7 Update 1.71 news thread — GTPlanet](https://www.gtplanet.net/forum/threads/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support.438254/)

**Prior physics-update lineage, for comparison**
- [Update Details (1.49)](https://www.gran-turismo.com/us/gt7/news/00_3114934.html) · [Update Notice (1.55)](https://www.gran-turismo.com/gb/gt7/news/00_3399040.html) · [DG EDGE — 1.49 Breakdown](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424)

**In-house baselines for the comparison runs**
- `setups/2026-08-12-rsr-monza-revB.md` — the Monza card: Vmax, limiter, K, fuel, median, degradation, four-corner temps
- `setups/2026-08-17-huracan-watkins-glen-long-revD.md` — the Watkins Glen card, and the sheet that won
- `setups/2026-08-10-huracan-laguna-seca.md` §9 — the first two measured results

---

**Maintenance note, 21 August 2026.** This document was opened the day after 1.71 released, on official notes plus three press sources plus a near-empty community record. **It is deliberately short on answers and long on questions, because that is the true state of things.** As the jobs in §12 come back, the findings belong in the documents they correct — `03` for tyres, `11` for ranges, `02` for parameters — with this file updated to point at them rather than duplicating them. When every job in §12 is closed, this document becomes a historical record and the banners in the other files come down.

**Amendments, same day.** **Job 2A added** — the Monza RSR control run, proposed by the driver. It is the only measurement in the protocol with a baseline distribution behind it, and it goes before Job 2 in execution order for that reason. **Its run mode was then corrected to short-shift-primary with a full-RPM tail**, on the driver's report that most of the Monza history was short-shifted — which is Standing Rule 12's second clause arriving before the rule was even ratified.
