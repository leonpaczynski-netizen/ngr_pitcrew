# GRAN TURISMO 7 — COMPLETE TUNING SHEET REFERENCE
### Professional sim-racing engineering knowledge base entry
**Compiled: August 2026 · Body written against GT7 v1.70 (June 2026), post-1.49 physics lineage**
**⚠️ Updated 21 Aug 2026 — 1.71 banner added below. Every slider range in this document is now unverified.**

---

# 🟠 1.71 BANNER — RANGES VOID, EFFECTS SUSPECT, STRUCTURE INTACT

**GT7 v1.71 (20 August 2026)** reworked the tyre slipping model, **per-car steering geometry**, **damper attenuation**, the default settings **and adjustment ranges** of suspension / differential / aerodynamics, Performance Points fleet-wide, both driving assists, and the damage model. Full changelog: `16-update-1.71-physics-change.md`.

## The one-line version

> **This document tells you what each slider *is* and what direction it *does*. That survives. It also tells you what each slider's *range* is and how *strongly* it acts. That does not.**

## What is void

| Content | Why |
|---|---|
| **Every stated range** — §3.1 ride height, §3.2 natural frequency, §3.4 damper 20–40 / 30–50, §3.5 camber, §3.6 toe ±0.50, §4 LSD 5–60, §5 aero | 1.71: *"Initial suspension settings and **adjustment ranges** have been fixed."* Same for the differential and for aerodynamics on race cars. **PD say in the official notes that the endpoints moved.** `11-car-slider-ranges.md` is the authority for our three cars and is being re-read. |
| **§3.5 camber — the whole section** | ⚠️⚠️ **The highest-priority re-test in the knowledge base.** §3.5's headline claim is that GT7 over-penalises negative camber. That behaviour is a product of the **steering geometry model**, and 1.71 reworked steering geometry **per car**. If the penalty softened, this section is wrong in a direction that has been costing mid-corner grip. `16` §12 Job 5, ten minutes. |
| **§3.6 toe — the contested core** | Toe sensitivity is downstream of the same geometry model. GT7's front-toe behaviour was **already disputed** (Position A vs Position B below); that dispute has now been re-rolled. Also note `11` measured toe at **±1.00°**, twice the ±0.50 stated in §3.6 — so this section was already understated by a factor of two before the patch. |
| **§3.4 dampers — the four-quadrant table's magnitudes** | 1.71: *"Damper attenuation characteristics have been changed to make stance changes and road surface tracking feel more natural."* **Stance changes = pitch and roll; road-surface tracking = bump compliance.** That is both of the things damping does. §3.4's quirk #1 — *"post-1.49, dampers do less than you expect"* — is exactly the complaint this change reads as a response to. **If dampers do more now, the whole four-quadrant table gets stronger and the workflow ordering in §11 changes.** |
| **§4 LSD 5–60** | Diff ranges revised. **[COMMUNITY — single source]** one GTPlanet player reports the Fully Customisable Diff can now be set to **0/0/0**, which was never previously possible. **If true, a genuinely open differential is buildable for the first time in the series** and every baseline in §4.2 sits against a floor that no longer exists. `16` §5. |
| **§5 aero magnitudes and the % -of-range track table** | Aero defaults *and ranges* revised on race cars. A percent-of-range target means nothing until the range is re-read. *(Re-read: all four cars on v1.71 in `range_records`, 11 Sep 2026 - the gate is met.)* |
| **§8.4 PP** | Recalculated fleet-wide. The **mechanism** (PP is a simulated test drive, not a formula) is untouched and in fact predicted this; the numbers are not. `06` has the detail. |
| **§7.5 / §9.1 ABS and TCS** | 1.71: TCS intervention behaviour *"optimised"*; ABS *"slip ratio control and cornering brake behaviour"* adjusted. §7.5's note that 1.55 changed these now needs a second entry — **and "cornering brake behaviour" names the trail-braking phase directly**, which is this driver's primary technique. |

## What survives, and it is most of the document's value

- **§2.2 — what GT7 does NOT have.** No tyre pressure, no caster, no brake pressure, no bump stops, no high/low-speed damper split, no engine-braking map. **1.71 removed nothing and added nothing here.** The four consequences that follow from it — camber and toe as the only contact-patch tools, ride height as the only bottoming defence, LSD braking sensitivity as the entire off-throttle toolkit — are structural and permanent.
- **§0.2 — the AI-content-farm test.** Any guide listing tyre pressure, caster, brake pressure or damper speed splits is pattern-matched from another sim. **This test is about to be more useful than it has ever been**: post-1.71 "tunes" will appear long before anyone has measured anything.
- **§10 — the symptom→fix tables.** These are *rankings of which lever owns which corner phase*. The phases still exist and the levers still own them. **Directions hold; magnitudes need re-calibrating.** §10.1's three opening questions — driver or setup, arch rub or balance, which phase — are the most durable content here.
- **§6 — the transmission section.** The Maximum Speed slider is still a generator that wipes your ratios. The flip method still works. ⚠️ *Gearing **targets** are exposed, because rolling resistance changed and that moves terminal speed.*
- **§3.0's reasoning about *why* ranges are per-car** — lever ratio, corner mass, travel; `Kw = 4π²F²M`; damping as a ratio auto-scaled to spring rate. **The mechanism explains why the endpoints moved and why they had to be re-read.**
- **§7.1's brake-balance sign convention.** Settled independently in `00-INDEX`: negative = front, positive = rear, and the value is a delta from factory bias. **A convention, not a physics value.**

## The two things to do before using this document again

1. **Re-read `11-car-slider-ranges.md`** — 15 minutes, all three cars, and it unblocks every number here. `16` §12 Job 1.
2. **Run the camber and front-toe A/B** — 30 minutes, one session, and it settles whether §3.5 and §3.6 still describe the game. `16` §12 Job 5.

**Until then: use this document for *what a lever does*, never for *what value to set*.**

---

## 0. HOW TO READ THIS DOCUMENT

### 0.1 Confidence tagging
GT7 is a closed-box simulation. Polyphony Digital publishes no physics documentation beyond short in-game blurbs and the *Beyond the Apex* guide. Almost everything below the level of "what the slider is called" is community-derived. I have tagged claims:

- **[GAME]** — verifiable in-game fact (slider name, range, unit, unlock requirement).
- **[STRONG]** — consistent across multiple independent, experienced sources and matches physical expectation.
- **[COMMUNITY]** — widely held by respected GT7 tuners but not rigorously demonstrated; may be car-specific.
- **[CONTESTED]** — sources actively disagree; treat as a hypothesis to test yourself.
- **[VERSION]** — known to have changed with a patch; check against your current build.

> **⚠️ 21 Aug 2026 — note what 1.71 did to the [GAME] tag specifically.** A slider's **range** was previously the most reliable class of fact in this document: you could read it off the screen and it did not move. **1.71 moved them.** So a [GAME] range is now a [GAME] *reading on a stated version* — which is Standing Rule 10 in its most concrete form. Every range in this file should be read as "[GAME], v1.70".

### 0.2 A warning about secondary sources
A large fraction of GT7 "tuning guides" published since ~2024 are AI-generated content farms. Diagnostic tells: they list **tyre pressure**, **caster angle**, **brake pressure**, or **high/low-speed damper splits** as GT7 settings. **None of these exist in GT7.** Any guide containing them has been pattern-matched from Assetto Corsa / iRacing / Forza and should be discarded wholesale. This trap caught at least two of the top-ranking Google results during research for this document, and a well-publicised GTPlanet "Complete Cheat Sheet" (thread 436897) was publicly corrected by experienced tuners for exactly this class of error — its author admitted to having "extrapolated specific values" via AI and re-issued it using slider *positions* rather than absolute values.

> **⭐ 21 Aug — and there is now a second tell, which will be more common than the first for the next month: any GT7 tuning content published after 20 August 2026 that quotes confident absolute values.** Nobody has measured anything on 1.71 yet (`16` §10). A guide that reads exactly as it did on 19 August has not been re-tested; a guide with new numbers and no methodology has invented them. **Both are Standing Rule 4 material.**

---

## 1. VERSION CONTEXT — WHAT CHANGED AND WHEN

Tuning advice in GT7 has a short shelf life. The relevant timeline:

| Version | Date | Physics-relevant content |
|---|---|---|
| **1.49** | 25 Jul 2024 | **Major physics overhaul.** Revised suspension *geometry* calculations, revised **damper attenuation**, new steering geometry (wheel + pad), revised tyre rolling resistance, revised low-speed tyre behaviour, new racing-tyre **heating and degradation** model, revised wet/dirty grip loss, new FFB torque-range calculation. **New default suspension and aero settings pushed to all race cars and many road cars.** All PP values recalculated. All Circuit Experience / Licence / Mission leaderboards wiped. |
| 1.50–1.52 | Aug–Oct 2024 | Physics **bug fixes** following 1.49 fallout; second engine-swap slot |
| 1.54 | Nov 2024 | PS5 Pro enhancements |
| **1.55** | 30 Jan 2025 | **Second physics pass.** Changed how suspension reacts to **short-period bumps** (direct response to the post-1.49 bouncing/kerb problem). Changed tyre loading and wet/dirt grip loss; tyres clean off faster after off-track. New steering geometry on wheels + new steering algorithm on pad sticks/buttons. **Changed TCS and ABS intervention strength.** Changed default aero on Gr.1 and other race cars; changed default suspension and **differential** settings on many cars. Leaderboards wiped again. |
| 1.56–1.63 | Feb–Sep 2025 | No documented physics changes. Wheel compatibility, Sophy, content. Michelin branding removed (1.63) |
| **1.65 "Spec III"** | 4 Dec 2025 | **Data Logger** added — lap-vs-lap telemetry comparison in any single-player event including Online Time Trials (not usable in Daily Races / GTWS). 22 new engine swaps. Power Pack DLC (Sophy 3.0). F3500-A tweaks |
| 1.66 | 11 Dec 2025 | **Downshift protection** added — prevents downshifting from excessively high RPM on manual transmissions |
| 1.67 | 30 Jan 2026 | Data Logger graph types expanded |
| 1.68 | 12 Mar 2026 | **BoP toggle for Time Trials**; **Drift Analyzer** added to Data Logger |
| 1.69 | 23 Apr 2026 | Power Pack Challenges |
| 1.70 | 11 Jun 2026 | Five new cars incl. prototypes |
| **⭐ 1.71** | **20 Aug 2026** | **Third major physics pass, and the largest since 1.49.** Tyre algorithm reworked **focusing on the slipping regime**; rolling resistance optimised; **tyre heating and wear values adjusted**; off-track grip loss on "Real" adjusted. **Steering geometry optimised for each car.** **Damper attenuation characteristics changed.** **Initial suspension, differential and aerodynamic settings AND ADJUSTMENT RANGES revised.** New engine torque control map (partial throttle, drifting). Downshift protection relaxed vs 1.66. **PP adjusted across the game.** **TCS intervention optimised; ABS slip-ratio control and cornering brake behaviour adjusted.** New "Championship" mechanical damage setting; collision damage thresholds changed. FFB and understeer vibration adjusted; Fanatec Auto Setup optimised; FullForce support. **All event ranking boards reset.** |

### 1.1 The three practical consequences of 1.49 for tuners

**⚠️ Read this section as history. 1.71 revisits all three of the underlying mechanisms — see §1.2.**

1. **Ride heights went up, permanently.** 1.49's revised geometry + damper attenuation caused widespread **bottoming-out and wheel-arch contact**. GTPlanet threads document cars that were fine pre-1.49 suddenly "crashing under severe compression," bouncing for seconds after a kerb strike, and — critically — **wheel-arch rub that physically prevents the car from turning**. The workaround that emerged was: stiffen springs by roughly a third, raise ride height, and reduce camber (e.g. 1.0° front / 1.5° rear on racing tyres). Tuners reported having to run Gallardos and Enzos at "off-road" ride heights even with springs maxed. 1.55 partially fixed the short-period-bump component but **did not fully restore pre-1.49 low ride heights.** **[VERSION][STRONG]**

2. **Dampers stopped behaving like classical spring-oscillation controllers.** Multiple tuners report post-1.49 that damper values "are not controlling the oscillation of the spring" in the way the pre-1.49 model did, and that **tyre sidewall stiffness now dominates** part of the response that dampers used to own. Practical effect: damper changes are less powerful than they used to be, and spring rate + tyre choice do more of the work. **[VERSION][COMMUNITY]**

3. **Aero now interacts with spring choice much more.** Because downforce compresses the suspension into the new geometry model, high-downforce cars often need higher natural frequency than the classic "match to weight" calculation suggests, purely to keep the car off the bump stops at speed. **[VERSION][COMMUNITY]**

**Rule for this knowledge base: treat any GT7 setup published before August 2024 as void, any published before February 2025 as suspect, and ⭐ any published before 20 August 2026 as pre-1.71 and requiring re-validation — including our own.**

### ⭐ 1.2 The 1.71 consequences, and why they map onto 1.49's three

**Read this beside §1.1: 1.71 touches the same three mechanisms, from the other direction.**

1. **Ride height and bottoming — [UNKNOWN], and that is the honest answer.** 1.71 changed **damper attenuation** and revised **initial suspension settings and adjustment ranges**. Those are the two levers behind §1.1's item 1. **It is the most plausible candidate yet for the 1.49 arch-rub problem changing — but PD did not say so, and nobody has tested it.** Do not assume fixed; do not assume unchanged. `00-INDEX` Settled Facts is annotated accordingly, and Standing Rule 8 still holds: the trigger is the driver symptom or a four-wheel mean-heave figure, never a telemetry flag.

2. **Dampers — plausibly reversed.** §1.1 item 2 says dampers do *less* than they used to. **1.71's stated goal is to make "stance changes and road surface tracking feel more natural"** — which is what you would write if you were addressing exactly that complaint. **If dampers now do more, §3.4 becomes a stronger tool and §11's workflow ordering (platform → gears → aero → ARBs → LSD → brakes → dampers) may want dampers earlier.** Test before reordering.

3. **Aero–spring interaction — unchanged in mechanism, but both inputs moved.** Aero defaults and ranges were revised on race cars, and suspension ranges were revised too. The interaction §1.1 item 3 describes still exists; the numbers on both sides of it do not.

**And one mechanism 1.49 and 1.71 share that §1.1 does not list: rolling resistance.** Both patches say it was "optimised." **It is a fuel term, a terminal-speed term and a gearing term** — so it silently moves L/lap, top speed, and every gearing constant K in the knowledge base, without the driver changing anything. `16` §3.3.

---

## 2. WHAT IS ACTUALLY ON THE SHEET — AND WHAT ISN'T

### 2.1 The complete adjustable inventory

| Group | Item | Unlock requirement |
|---|---|---|
| **Tyres** | Front compound, Rear compound (independently) | Purchased from Tuning Shop |
| **Suspension** | Body Height F/R · Anti-Roll Bar F/R · Damping Ratio Compression F/R · Damping Ratio Expansion F/R · Natural Frequency F/R · Camber F/R · Toe F/R | Height-Adjustable Sports (height + limited) or **Fully Customisable** (all) |
| **Differential** | Initial Torque · Acceleration Sensitivity · Braking Sensitivity — per driven axle. AWD adds **Front/Rear Torque Distribution** | Limited-Slip Differential (Club Sports) / Fully Customisable LSD; Torque-Vectoring Centre Diff for AWD |
| **Aerodynamics** | Downforce Front, Downforce Rear | Adjustable aero parts from GT Auto (road cars); built-in on race cars |
| **Transmission** | Maximum Speed (auto-set) · Gear 1..n ratios · Final Gear ratio | Fully Customisable Manual or **Fully Customisable Racing** |
| **Brakes** | Brake Balance (single delta value) | **Brake Controller** (Tuning Shop) |
| **Performance Adj.** | Power Restrictor % · ECU Output Adjustment % · Ballast (kg) · Ballast Position | Power Restrictor / Full Control Computer / Ballast, all Tuning Shop |
| **Other installed parts** | Weight Reduction stages · Body Rigidity Improvement · Wide Body · Nitrous output % · Anti-Lag · Hydraulic Handbrake · engine swap · turbo/supercharger tier | Tuning Shop tiers: Sports → Club Sports → Semi-Racing → Racing → Extreme |
| **Assists (not on sheet)** | TCS 0–5 · ASM · Countersteering Assist · ABS Default/Weak/Off | Menu-level, free |
| **In-race MFD** | Fuel Map · Brake Balance · TCS | Fully Customisable Computer needed for fuel map |

Up to **10 saved setting sheets per car**, renameable/duplicable. Triangle recalculates PP; L1/R1 cycle through the last five states. **[GAME]**

> **⭐ 21 Aug — the "10 saved sheets per car" line is now operationally important.** 1.71 says nothing about what happens to saved settings. **Before overwriting anything, duplicate the current sheet** so the pre-1.71 state is preserved on the car itself, not just in `setups/`. And **read the current values against the archived sheet first** — `16` §12 Job 0. If some values changed and others did not, the changed ones were clamped by a moved range, and they map out where the new endpoints are.

### 2.2 What GT7 does NOT have (and why it matters)

**⭐ This section is the most durable in the document. 1.71 removed nothing and added nothing here.**

Absent versus a full-fat sim: **tyre pressure**, **caster**, **kingpin/scrub radius**, **bump steer**, **roll centre**, **brake pressure**, **brake ducts/temperature**, **bump stops / packers / third spring**, **high-speed vs low-speed damper split**, **differential preload in Nm**, **rake-driven aero maps**, **engine braking maps**, **fuel-load-dependent ride height**, **spring rate in N/mm as a direct entry**, **steering lock/steering angle**.

**Consequences you must internalise:**
- With no tyre pressure, **camber and toe are your only tyre-contact-patch and tyre-temperature tools.** Everything real engineers do with pressure has to be done with camber, toe, ARB and springs. **⚠️ And 1.71 reworked the geometry model that governs both of them — which makes the camber/toe A/B (§3.5, §3.6) more urgent than it looks, because these two are carrying more load in GT7 than in any other sim.**
- With no bump stops or packers, **the only defence against bottoming is ride height, spring rate, and compression damping.** This is why 1.49 hurt so much. **⚠️ All three were touched by 1.71.**
- With a single damper curve per direction, **you cannot separate kerb response from body control.** Any damper setting that survives kerbs is a compromise for body control and vice versa.
- With no engine-brake map, **LSD braking sensitivity is your entire off-throttle rear-stability toolkit** (alongside brake balance and rear toe). **⭐ This is the single most important structural fact in the document for this driver — `08` A4 is built on it — and it is unaffected by 1.71.**

---

## 3. SUSPENSION

### 3.0 Ranges are per-car — how the min/max are actually derived

> **🔴 And as of 1.71 they are also per-*version*.** The official notes state that initial suspension settings **and adjustment ranges** were revised. **Every range quoted in §3 is a v1.70 reading.** The mechanism below explains *why* PD were able to move them, and why a re-read is the only way to recover them: the endpoints are derived from stored chassis data, so a patch that re-authors that data re-authors every endpoint at once.

GT7 stores per-car chassis data that determines every slider's endpoints. There is no universal range for suspension items. From community reverse-engineering (GT Pro Tune developer, GTPlanet lever-ratio thread):

- Each car has a **lever ratio (motion ratio) stored in the range ~0.5–1.5**, plus suspension type, unsprung mass per corner, and total suspension travel. **[COMMUNITY]**
- **Natural Frequency min/max scales with corner mass and available travel.** The slider is presented in Hz, but the underlying quantity is wheel rate: `F = (1/2π)·√(Kw/M)`, therefore `Kw = 4π²·F²·M`. Because M (corner mass) varies with car weight and distribution, **the same Hz number is a very different spring rate on a 900 kg Gr.4 car than on a 1600 kg road car** — which is exactly why "use 3.5 Hz on racing softs" is bad advice. Road cars often cannot reach 3.50 Hz at all; some race cars reach 5.00 Hz. **[STRONG]**
- **Body Height min/max is bounded by modelled suspension travel and body geometry**, which is why race cars frequently have a *maximum* rear ride height around 85 mm while road cars can go far higher. Advice quoting absolute mm figures is therefore near-useless across classes. **[STRONG]**
- **Damping is a ratio, not a force.** The percentage is damping ratio ζ against critical damping: `Ccrit = 2·√(K·M)`, `C = ζ·Ccrit`. **100% = critically damped.** The damped frequency is `Fdamp = Fnat·√(1−ζ²)`. Because it's a ratio, **changing spring rate changes the absolute damping force even if you leave the damper number alone** — GT7 auto-scales it. This is a major GT7-specific quirk: in most sims dampers are absolute and must be re-tuned after a spring change; **in GT7 the damper numbers are already spring-normalised.** **[STRONG]**

**Practical implication:** always record and reason in **slider position / % of range**, not absolute values, when writing car-agnostic guidance.

> **⚠️⚠️ 21 Aug — and that practical implication has a failure mode 1.71 just triggered.** Percent-of-range is only stable while the range is. **When an endpoint moves, every percent-of-range target silently changes meaning, and the sheet still reads like a sheet.** `11-car-slider-ranges.md` documents this happening twice already for a different reason (a heuristic crossing a class boundary); a moved range does it to every parameter at once.
>
> **The rule that replaces it, per `11`: every heuristic must declare whether it is absolute or proportional, *and* which version its range was read on.** Standing Rules 10 and 11.

---

### 3.1 Body Height (Ride Height) — Front and Rear

**Unit:** millimetres. **[GAME]**
**Range:** ⚠️ **v1.70 reading** — per-car; race cars commonly ~50–90 mm, road cars on Height-Adjustable Sports commonly ~60–160 mm. Step size 1 mm on most cars. **[GAME, v1.70]** *(Our measured cars: Gr.3 55–80 front / 60–90 rear; Shelby Gr.N 75–160 / 95–180. See `11`.)*
**PP effect:** none. **[STRONG]** *(Mechanism unaffected by 1.71.)*

**Lowering (both ends):**
- Lowers CoG → less lateral load transfer → **more total grip, less roll**. Primary benefit.
- Slightly quicker steering response, flatter platform.
- **Risk:** bottoming out, and post-1.49, **wheel-arch contact that can physically lock steering**. A car that suddenly refuses to turn mid-corner after a kerb or a compression is almost always arch rub, not a balance problem. **[VERSION][STRONG]** **⚠️ Status on 1.71: [UNKNOWN] — see §1.2 item 1.**
- Reduces effective bump travel → worse over kerbs and elevation change.

**Raising (both ends):**
- More compliance, better kerb/bump absorption, more predictable over crests.
- More roll and load transfer → less peak grip.
- Sometimes *faster* on bumpy tracks despite the theory (Nordschleife, Sardegna, Tokyo joints). **[COMMUNITY]**

#### Rake — the GT7-specific truth
**This is one of the most misunderstood items in GT7.**

- GT7 does **not** appear to model a rake-dependent aerodynamic map. The downforce numbers you set in the aero section are what you get; there is no evidence that raising the rear increases rear downforce as it would in a real underbody-aero car. **[COMMUNITY]** Occam's Racer's controlled testing showed GT7's whole aero system produces surprisingly small lap-time effects (see §5.1), which further argues against a rich rake-aero model.
- Rake in GT7 works primarily as a **mechanical** effect: it alters roll-centre heights and therefore the front/rear split of lateral load transfer, and it shifts static weight distribution slightly.
- **Consensus direction: positive rake (rear higher than front) → more rotation / more entry oversteer / more front grip.** Negative rake (nose-up) is broadly discouraged. **[COMMUNITY]**
- **Dead myth:** "lower the rear for top speed." This worked in GT4/GT5/GT6. In GT7 it does not meaningfully help top speed, and it invites arch rub. Explicitly called out as obsolete by experienced GT7 tuners. **[STRONG]**

**Typical starting point:** front 3–5 clicks above the car's minimum, rear 5–8 clicks above minimum — i.e. a modest positive rake with real travel in reserve at both ends. **[COMMUNITY]**

> **⚠️ This exact heuristic is documented as broken in `11-car-slider-ranges.md`.** Stated in *clicks*, it means **20% of range on a Gr.3 car and 6% on the Shelby** — a 3× change of meaning across a class boundary, which put three consecutive Yas Marina sheets 5 mm off the floor while the driver spun four times in fifteen laps. **State it as percent of range, and only once the ranges are re-read.**
>
> **Also note the built-in rake trap `11` records:** both sliders at minimum is *already* +5 mm of positive rake on the Gr.3 cars and **+20 mm** on the Shelby. **Quote rake as rear-minus-front in mm, with the built-in figure alongside**, or the number reads as several times more aggressive than it is.

**Common mistakes:**
1. Setting both ends to minimum on principle. Post-1.49 this is actively slow on most cars.
2. Using rake as a primary balance tool. It's coarse and it interacts with bottoming; use ARBs and springs first.
3. Not re-checking ride height after adding downforce or ballast — both compress the car statically/dynamically.
4. Tuning ride height on a smooth track then racing on a bumpy one.
5. **⭐ Quoting it in clicks. See above.**

---

### 3.2 Natural Frequency (spring rate)

**Unit:** Hz (undamped ride frequency of that axle). **[GAME]**
**Range:** ⚠️ **v1.70** — per-car, typically ~0.80–5.00 Hz across the whole game; a given car exposes a subset. Step 0.01–0.05 Hz depending on car. **[GAME, v1.70]** *(Measured: Gr.3 3.00–5.00; Shelby 1.88–3.70 front / 2.00–3.90 rear. The RSR's step is **0.01 Hz**, settled 12 Aug.)*
**PP effect:** none. **[STRONG]**

**Official guidance (in-game manual / Beyond the Apex):** road cars on Comfort or Sports tyres **~1.1–1.5 Hz**; race cars on Racing tyres **~3–5 Hz**. **[GAME]**
A commonly cited community refinement: Comfort ≈ 1.2 Hz, Sports ≈ 1.8 Hz, Racing ≈ 4.0 Hz as a *starting* anchor, then adjusted for downforce and mass. **[COMMUNITY]**

**Why frequency and not N/mm:** frequency is mass-normalised, so it's the correct currency for comparing across cars. Two cars both at 2.5 Hz feel comparably stiff regardless of weight.

**Increasing NF (stiffer):**
- Less roll, less pitch, less dive/squat → **faster load transfer**, sharper response.
- Better platform control for downforce (prevents the car sinking onto its bump stops at speed).
- Less mechanical grip; worse on bumps and kerbs; more likely to skate.
- Stiffening **one end** takes grip away from that end (classic balance lever): stiffer front → understeer; stiffer rear → oversteer.

**Decreasing NF (softer):**
- More mechanical grip, more compliance, better on bumps/kerbs.
- Slower response, more roll, more weight transfer, more lag between input and load build.
- Too soft → wallow, mid-corner instability, bottoming, and post-1.49, arch contact.

**Front/rear split — GT7 tendencies [COMMUNITY]:**
| Layout | Typical direction |
|---|---|
| FR | Front at/near soft end; rear varied to trade rotation vs traction. Rear generally **stiffer than front**. |
| MR | Both toward the soft end — MR cars in GT7 are entry-oversteer-prone and stiff fronts make it worse. |
| FF | Front minimum, rear noticeably stiffer (~50–60% of range) to unload the rear and kill understeer. |
| AWD | Similar to FF: soft front, stiffer rear. |

A widely used heuristic: **softer front + stiffer rear = more rotation and a more stable platform**, with exceptions for cars that are already loose.

**GT7 quirks and mistakes:**
- **The single biggest error is copying absolute Hz values between cars.** 3.5 Hz is unreachable on many road cars and mid-range on some race cars.
- **⭐ And the mirror-image error, documented in `11`: quoting NF as *percent of range* when the floor is high.** The "70–80% of range" heuristic puts a Gr.3 car at **4.40–4.60 Hz** — a full 1.0 Hz stiffer than either of our Gr.3 cars has ever raced well on, because their floor is *already* race-stiff at 3.00 Hz. **Issue natural frequency in absolute Hz.**
- Post-1.49, **springs took over work that dampers used to do.** If the car feels uncontrolled, try spring rate before dampers. **⚠️ 1.71 may have handed some of that back — see §1.2 item 2.**
- If the car "bounces twice" as load comes off a corner, the suspension frequency and the tyre's effective frequency are fighting. Change NF, not dampers, first. **[COMMUNITY]** *(This diagnosis was used successfully on the RSR at Monza — `setups/2026-08-12-rsr-monza-revB.md` §2.2 — and is one of the cleanest applications of §10.9's three-row table in the record.)*
- High-downforce cars often need *higher than calculated* NF purely to stop aero over-compressing the suspension. **[VERSION][COMMUNITY]**
- Suspension settings **do not affect PP**, so there is never a PP reason to compromise here.

---

### 3.3 Anti-Roll Bars — Front and Rear

**Unit:** dimensionless stiffness index. **Range: 1–10 on essentially every car**, integer steps. This is one of the few genuinely universal scales in GT7. **[GAME, v1.70 — confirmed on three cars across two classes in `11`]**
**PP effect:** none. **[STRONG]**

> **⚠️ ARB is not named in 1.71's revised-range list** (which covers suspension, differential and aerodynamics) — but ARB *is* suspension, so the 1–10 scale should be confirmed rather than assumed. Five seconds during the Job 1 re-read.

ARBs act **only in roll**, i.e. they are a **mid-corner / steady-state** tool. They do nothing in pure heave (both wheels compressing equally) and nothing under straight-line braking or acceleration. Use them for mid-corner balance; use springs and dampers for entry/exit transients. **[STRONG]**

**Stiffer front ARB:** less front roll, more front lateral load transfer → **less front grip → more mid-corner understeer.** Sharper initial steering feel, but the front gives up earlier.
**Softer front ARB:** more front grip mid-corner, slower/lazier initial response.
**Stiffer rear ARB:** less rear grip mid-corner → **more oversteer**, more rotation.
**Softer rear ARB:** more rear grip, more understeer, more stability.

**Baselines by layout [COMMUNITY]:**

| Layout | F | R | Reasoning |
|---|---|---|---|
| FR | 6 | 4 | Front-heavy; resist front roll, keep rear planted |
| FF | 4 | 6 | Stiff rear to kill inherent understeer; soft front for traction+grip |
| MR / RR | 6 | 3 | Tame entry oversteer, protect rear grip |
| AWD | 5 | 5 | Neutral start |

**Common mistakes:**
1. Using ARBs to fix entry or exit problems. They barely act there. Entry = dampers/brake balance/front toe; exit = LSD/rear springs/rear damping.
2. Running both bars very stiff. This makes the car mid-corner-grip-limited at both ends and horrible on kerbs. Total roll stiffness should be set by springs; ARBs distribute it.
3. Forgetting ARBs are integers — one click is a large step on a light car. On a Gr.4/road car, one click can be worth more than a 0.2 Hz spring change.
4. Not re-checking ARBs after a spring change. ARB *contribution* as a fraction of total roll stiffness changes when springs change.
5. **⭐ Reaching for a front ARB change to cure a *power-on* mid-corner push.** That is an accel-LSD problem (§4.1, §10.5). Adding front grip masks the cause and costs roll control — the trap documented twice in-house, at Laguna and at Monza.

---

### 3.4 Dampers — Compression and Expansion, Front and Rear

> **⚠️⚠️ THE MOST 1.71-EXPOSED SECTION IN THIS DOCUMENT.** *"Damper attenuation characteristics have been changed to make stance changes and road surface tracking feel more natural."* **Stance changes** are pitch and roll transitions; **road surface tracking** is bump compliance. Those are the two things damping does — so this is a model change, not a value tweak. **Both the windows below and the four-quadrant table's magnitudes need re-establishing.**

**Unit:** percentage = **damping ratio ζ** relative to critical damping. **[STRONG]**
**Range:** ⚠️ **v1.70** — per-car, but **for roughly 99% of cars the in-game range was ~20–40 for Compression and ~30–50 for Expansion.** A minority of cars (very light and/or very high-downforce — Formula, Gr.1) expose different windows, and drag/drift-oriented setups on some cars reach the mid-teens. **[GAME/COMMUNITY, v1.70]** — this figure comes from GTPlanet tuner *Techlet* correcting the GT Pro Tune calculator, which was outputting values above what the game would accept, and was **independently confirmed on three of our own cars across two classes** (`11`). **That triple confirmation is exactly what makes a change here easy to detect: if the window reads anything other than 20–40 / 30–50 on a Gr.3 car, 1.71 moved it.**

**GT7 splits dampers only two ways: Compression (bump) and Expansion (rebound). There is NO high-speed/low-speed split.** Do not import ACC/iRacing "slow bump / fast bump" thinking. **[GAME]** **⭐ Structural — unaffected by 1.71.**

**Because the value is a ratio, GT7 auto-rescales absolute damping force when you change spring rate.** You do not need to re-tune dampers after a spring change to preserve damping character — only if you want to change character. This is the opposite of most sims. **[STRONG]** **⭐ Also structural, and it is why the RSR's paired NF change (`revB` §4.2) was balance-neutral by construction.**

#### The four-quadrant effects table
This is the most useful damper model for GT7, cross-referenced from DG-Edge and consistent with FILO/sim.doctor:

| Damper | Higher (stiffer) | Lower (softer) |
|---|---|---|
| **Front Compression** | Resists nose dive; slows forward load transfer → **reduces entry oversteer**, reduces rotation on the brakes | Allows faster forward load transfer → **reduces entry understeer**, more front bite on turn-in |
| **Rear Compression** | Resists squat; keeps weight forward under power → **reduces exit understeer** but **costs rear traction** | Allows rear to squat → **reduces exit oversteer**, more traction, less exit rotation |
| **Front Expansion** | Slows front extension; keeps front loaded longer → **reduces exit understeer**, keeps front tyre in contact | Front rises quickly → load moves rearward → **reduces exit oversteer**, more mid-corner understeer |
| **Rear Expansion** | Slows rear extension; controls body roll build → **reduces entry understeer** | Rear rises quickly → **reduces entry oversteer**, stabilises the rear off the brakes |

**⭐ The *directions* in this table are load-transfer physics and should survive. The *magnitudes* are what 1.71 changed.**

**Working ranges [COMMUNITY, v1.70]:** start both ends at the middle of their windows — roughly **Compression 28–32, Expansion 38–42** for a typical car. Then move in 2-point steps.

**The "expansion > compression" rule.** Widely repeated as absolute. It is a **good default** — rebound should generally exceed bump so the wheel returns in a controlled way — and GT7's per-car ranges are literally built around it (20–40 vs 30–50). But it is a heuristic, not a physical law, and the overlap region exists for a reason. **[COMMUNITY]** **⚠️ Note the rule is *derived from the ranges*. If the ranges moved, re-derive it.**

**GT7-specific quirks and mistakes:**
1. **Post-1.49, dampers do less than you expect.** If a 4-point damper change does nothing, that is normal now; go to springs or ARBs. **[VERSION]** **⚠️⚠️ This is the specific complaint 1.71 reads as a response to. If it is no longer true, damper changes get their authority back and this quirk inverts.** Test before assuming either way.
2. **Harsh rear compression causes oscillation and "skating."** A specific, repeatedly-reported GT7 failure: too much rear compression under combined longitudinal + lateral load makes the rear tyres chatter and lose grip abruptly rather than progressively. **[COMMUNITY]**
3. **Dampers are the wrong first tool for kerbs.** They matter, but ride height and spring rate matter more in GT7. **⚠️ Also exposed — this ordering is downstream of quirk 1.**
4. Do not chase symmetry for its own sake. Front and rear dampers legitimately differ; but keeping the **absolute damping coefficient C matched front-to-rear** (which the GT Pro Tune calculator does explicitly, even when NF differs F/R) is a defensible engineering starting point.
5. Changing dampers by 1 point is below the noise floor for most drivers. Move in 2s or 3s.

---

### 3.5 Camber — Front and Rear

> **🔴 THE HIGHEST-PRIORITY RE-TEST IN THE KNOWLEDGE BASE.** 1.71: *"The steering geometry **for each car** has been optimised, improving the simulation of turning forces."* **Steering geometry governs how steer angle and suspension travel convert into slip angle and camber gain — which is the mechanism behind everything below.**
>
> **If GT7 still over-penalises camber, this section stands. If it doesn't, this section is wrong in a direction that has been costing mid-corner grip on every car in the garage, and `03` §8.3, `07` §2.7 and `08` A1 are all wrong with it.** `16` §12 Job 5: three laps each at 0.5° / 1.5° / 2.5° front camber. Ten minutes. **Run the front/rear swap check (mistake 5 below) in the same session.**
>
> **Until it is run, treat this section as [CONTESTED] rather than [STRONG], and do not issue a camber value.**

**Unit:** degrees, displayed as a positive number that means **negative camber** (top of wheel leaning in). **[GAME]**
**Range:** ⚠️ **v1.70** — per-car, typically 0.0 up to 8.0–10.0. Step 0.1°. **[GAME, v1.70]** *(Measured **0.0–6.0°** on all three of our cars, across two classes — so the 8–10 figure is wrong for at least Gr.3 and Gr.N. See `11`.)*
**PP effect:** none. **[STRONG]**

#### The single most important GT7 camber fact
**GT7 punishes negative camber far more heavily than real racing does, and far more than other sims.** This is the most consistently reported alignment quirk in the game, across years and versions. Players repeatedly report: *"Every single time I increased negative camber I got much less grip"* — including significantly worse straight-line braking. **[STRONG, v1.70 — now [CONTESTED], see banner]**

The mechanism is that GT7's tyre model gives up longitudinal grip to camber very quickly, and the mid-corner lateral gain is smaller than the theory predicts. The result is a much lower optimum than you'd run in reality.

**Also note the widely repeated GT7 observation that front camber in GT7 primarily affects MID-CORNER, not turn-in.** Guides that say "add front camber for turn-in" are importing behaviour from other sims and were publicly corrected on this point on GTPlanet. Turn-in in GT7 is governed by front toe, front compression damping, brake balance and front ARB. **[COMMUNITY]**

**Working values [COMMUNITY, v1.70], noting sources disagree at the top end:**

| Compound | Front | Rear |
|---|---|---|
| Comfort | 0.8–1.5 | 0.5–1.0 |
| Sports | 1.5–2.0 | 1.0–1.5 |
| Racing | 1.5–2.5 (many fast tuners run **1.0–1.5**) | 1.5–2.0 |
| Post-1.49 anti-bottoming setups | ~1.0 | ~1.5 |
| AWD road cars (praiano-style) | 0.4–0.8 | 0.4–0.8 |

**Every car has its own sweet spot; the spread between 0.4 and 2.5 in the table above is real, not sloppiness.** The honest procedure is a sweep: fix everything else, run 0.0 / 0.5 / 1.0 / 1.5 / 2.0 / 2.5 on one axle over 3 clean laps each, and take the best average. Use the **Data Logger (1.65+)** to compare directly.

**⭐ And "every car has its own sweet spot" is now literally true in a new way: 1.71 optimised steering geometry *per car*, so the three cars in the garage may have moved differently from each other.** A camber sweep on the Huracán does not transfer to the RSR.

**Increasing negative camber:** more mid-corner lateral capacity (up to a small optimum), then falling off; **immediately worse braking and traction**; more inner-shoulder wear; slightly slower straight-line.
**Decreasing toward zero:** better braking and traction, better straight-line, longer tyre life; less mid-corner peak at high roll angles.

**Common mistakes:**
1. Copying real-world GT3 camber (−3.5° to −4.0°). In GT7 that is a large net loss. **⚠️ On v1.70. If the geometry rework softened the penalty, the 2022-era tunes' −3.0° may be closer to right than anything issued since — `07` §2.7.**
2. Adding camber to fix understeer. It's the wrong tool — it costs you braking and may not help mid-corner at all.
3. Adding camber after softening springs "to compensate for roll." GT7 doesn't reward that trade the way reality does.
4. Ignoring the post-1.49 interaction: **excess camber worsens the arch-contact problem** because it changes where the tyre sits in the arch. Reducing camber is part of the standard post-1.49 bottoming fix. **⚠️ Arch-rub status on 1.71 is [UNKNOWN].**
5. There is a long-running (unverified) community theory that front and rear camber are swapped internally in GT7. Treat as folklore, but it is cheap to test. **[CONTESTED]** **⭐ And now genuinely live — a geometry rework is exactly the kind of change that would fix such a bug, or introduce one. Five minutes, in the same session as the sweep.**
6. **⭐ Setting camber low *defensively*, to protect a tyre-wear budget you have not measured.** `08` A1 records this as the mirror-image failure: the Laguna Huracán ran 1.0°/1.0° against a wear limit that proved ~1.8× softer than modelled, which made the conservatism unpaid-for lap time. **Post-1.71 no wear limit is measured at all, so this trap is currently wide open.**

---

### 3.6 Toe — Front and Rear

> **⚠️ Also downstream of the reworked steering geometry, and this section was already the most disputed in the document.** See the banner. **Front toe has been on the "A/B it on every car" list since this file was written and has never been run on the Huracán — four sessions outstanding.** `16` §12 Job 5 pairs it with the camber sweep.

**Unit:** degrees. Positive = **toe-in**, negative = **toe-out**. **[GAME]**
**Range:** ⚠️ **v1.70, and this figure is known to be understated** — stated here as roughly **−0.50 to +0.50** on most cars (praiano63 references rear values above +0.60 on some), step 0.01°. **[GAME/COMMUNITY, v1.70]**

> **📝 CORRECTION, outstanding since 11 Aug 2026 and now folded in:** `11-car-slider-ranges.md` measured toe at **−1.00° to +1.00°** on all three cars across two classes — **twice the span stated above.** The consequence is that **5% of the toe range is 0.10°, which is twice the size of the smallest change worth making**, so **toe must always be issued in absolute degrees, never as a percentage.** The scalpel-not-sledgehammer rule below is unaffected; the numbers are simply a much smaller slice of the slider than this section assumed.

**PP effect:** none. **[STRONG]**

Toe is the highest-sensitivity-per-click item on the entire sheet. **A change of 0.05° is a real, feelable change. A change of 0.20° is enormous.** "Toe is a scalpel, not a sledgehammer."

#### GT7's peculiar toe behaviour — the contested core
This is the most genuinely disputed area in GT7 tuning, and you should know both positions.

**Position A — "GT7 front toe is reversed."** A well-known GTPlanet thread ("I've solved what is the 'oversteery' mess that is GT7") argues that in GT7, **adding front toe-OUT promotes understeer / stability**, the opposite of real-world behaviour where toe-out sharpens turn-in and destabilises. Multiple posters in that thread report success with the reversed approach; several others report no effect or car-dependent results. **[CONTESTED]**

**Position B — conventional but skewed.** Veteran tuner **praiano63**, whose GT7 tunes are among the most widely used, describes conventional-ish behaviour but with GT7-specific emphasis:
- **Front toe-IN (0 to +0.10):** *smoother*, *slower reaction to wheel input when placing the front end*, car is *more steady* from mid-corner to exit. Used on FF, FR and lazy MR cars.
- **Front toe-OUT (0 to −0.30):** *more instant reaction to wheel input on entry*, encourages natural oversteer, helps hold the line with more margin for correction. Used on tail-happy MR and nearly all RR cars.

Note that these two positions are not as far apart as they look: both agree that **front toe-in makes the front lazier and the car steadier**, and that front toe is a *stability* control rather than a raw turn-in control. The disagreement is about whether toe-out actively *creates* understeer or merely creates a sharper, more oversteer-prone car that some drivers then perceive as running wide.

> **⭐ 21 Aug — and here is the genuinely interesting possibility.** If the dispute was an artefact of the old steering-geometry model, **1.71 may have just resolved it** — in either direction. A parameter that two experienced groups could not agree on for years has been re-authored per car. **The A/B is the same 15 minutes it always was, and the answer may finally be clean.**
>
> The one point both positions agree on is the firm rule and it is the one to keep: **front toe-in makes the front lazier and the car steadier.** For a driver whose single most-hated trait is a lazy front (`08` A3), that is enough to keep front toe-in off the sheet regardless of how the dispute resolves.

**Practical recommendation for a knowledge base: do not assume either. Front toe is the one parameter you should A/B test on every car**, +0.05 vs 0.00 vs −0.05, before building the rest of the setup around it.

**Rear toe is much less contested [STRONG]:**
- **Rear toe-IN** = rear stability, rear grip, resistance to snap oversteer, straight-line stability under braking. This is GT7's most reliable "make the rear stop scaring me" lever.
  - Low-power cars: **+0.10 to +0.25**
  - Powerful road cars: **+0.25 to +0.60**, working together with downforce and LSD
  - Generic safe default: **+0.05 to +0.20**
- **Rear toe-OUT** is rarely used; primarily on **4WD and FF cars** with a heavy, lazy, understeering front end, where it lets the rear rotate. Max around **−0.50**. Also used deliberately in drift setups.
- Drift reference point: front **−0.50** toe-out, rear **+0.50** toe-in. **[COMMUNITY]**

**Costs of toe in GT7:**
- **Drag and scrub.** Toe at either end costs straight-line speed. Rear toe-in is the classic "buy stability with top speed" trade. On Le Mans / Route X / Tokyo, big rear toe is measurably slow.
- **Tyre wear.** Toe is the single largest alignment contributor to wear in GT7. If one axle is wearing out, toe is the first thing to pull toward zero. **⚠️ Wear model changed in 1.71 — the size of this cost is unknown.**
- **Oscillation.** Exceeding roughly ±0.05° front toe on some cars introduces steering oscillation / twitchiness at speed. **[COMMUNITY]**

**Common mistakes:**
1. Using toe as a primary balance tool. It's a trim, applied last.
2. Fixing snap oversteer with +0.30 rear toe and shipping the setup. You've hidden the problem and bought a slow car. Find the real cause (LSD accel sensitivity, rear damping, rear spring, exit gearing) first.
3. Not zeroing toe when chasing a top-speed setup.
4. Changing front and rear toe in the same run.
5. **⭐ Quoting toe as a percentage of range.** See the correction above — 5% is 0.10°, twice the smallest useful step.

---

## 4. DIFFERENTIAL / LSD

**Unit:** dimensionless index. **Range: 5–60 on effectively all cars**, integer steps. Universal scale. **[GAME, v1.70 — confirmed on three cars across two classes in `11`]**

> **⚠️⚠️ 21 Aug — the floor may no longer be 5.** 1.71: *"Initial differential gear settings and **adjustment ranges** have been fixed."* **[COMMUNITY — single source, GTPlanet undocumented-changes thread]** one player reports the Fully Customisable Diff can now be set to **0/0/0**, *"never before that was possible."*
>
> **If confirmed, a genuinely open differential is buildable for the first time in the series.** Every baseline in §4.2 is written against a floor of 5, and the space below them is unexplored. It matters most for **§4.1 Braking Sensitivity** — an open diff on the overrun is a larger rotation source than anything this section describes — and for **`08` A4**, where LSD braking sensitivity is the driver's entire off-throttle toolkit.
>
> **One person, two days after release. Confirm it on the settings screen (`16` §12 Job 1, thirty seconds) before it changes a single setup.**

**Unlock:** Limited-Slip Differential from Club Sports; AWD torque split needs the Torque-Vectoring Centre Differential. **[GAME]**
**PP effect:** the *part* affects PP; the values generally do not. **[COMMUNITY]** **⚠️ But note `06` §1.2's single-source claim that PP is computed from the *default* settings of adjustable suspension and diff — if true, 1.71 changing those defaults changes PP on cars nobody touched.**

### 4.1 The three parameters

**Initial Torque (5–60)**
The always-on preload — the baseline locking present *regardless* of throttle or brake state, and it adds to both the acceleration and braking locking effects. At 5 it is effectively an open-ish diff at zero load; at 60 the car behaves close to spool at low load.
- **Increase →** more locked at all times. Smoother, more predictable transitions; more straight-line stability; **more mid-corner understeer** and more steering effort/scrub; more tyre wear on the driven axle.
- **Decrease →** freer differential, more rotation, sharper direction change, but more sensitive to throttle and more prone to inside-wheel spin.
- **GT7 practice: keep this LOW (5–10) on almost everything.** The main exception is deliberately over-locked drag and drift setups.

**Acceleration Sensitivity (5–60)**
How aggressively the diff locks under throttle.
- **Increase →** more locking on power. Better traction out of slow corners; kills inside-wheel spin; but makes the car **want to drive in a straight line and stop turning** under throttle → power understeer.
- **Decrease →** more rotation on throttle, better ability to steer with the throttle; risk of one-wheel spin and lost drive.
- **The critical GT7 quirk:** *"when you break traction with higher locking numbers, the transition from having grip to losing grip with BOTH rear tires is quite a sharp loss of traction."* In GT7, a high accel-sens diff doesn't slide progressively — it lets go of both driven wheels at once. **This is why GT7 tuners run much lower acceleration sensitivity than real-world or other-sim practice would suggest.** **[STRONG]**

> **📝 Downgraded in `08` A5, and the downgrade stands:** that quirk is **single-source**, and more importantly **it is not a GT7 anomaly** — a heavily locked diff approaches a spool, and a spool axle breaks away as a unit in every sim and in reality. **Treat it as ordinary diff physics.** That reframing is why it survives 1.71 untouched while the *values* around it do not.

> **⚠️ And 1.71 introduced a new engine torque control map.** Acceleration sensitivity is the parameter that manages torque delivery to the driven axle, so **every accel value in the knowledge base is a response to a torque curve that has been re-authored** — including the in-house measured 14 on the restricted Huracán (`08` A5.1) and the 18 that superseded it when the restrictor came off (`setups/…-revD.md` §7). **Re-test before reusing either.**

**Braking Sensitivity (5–60)**
How much the diff locks off-throttle and under braking. This is GT7's substitute for an engine-braking map.
- **Increase →** more locking on the overrun. Stabilises corner entry, reduces lift-off and trail-brake oversteer; **the car becomes less keen to turn in.** Especially powerful on rear-weight-biased cars (RR/MR) to kill entry snap.
- **Decrease →** freer on entry, more rotation under braking and on lift.
- Because GT7's cars — especially MR and RR — are entry-oversteer-prone, **braking sensitivity is often the highest of the three numbers on those layouts**, which looks wrong to anyone coming from other sims.

> **⚠️ 1.71 adjusted ABS *"slip ratio control and cornering brake behaviour"* — which names the exact phase braking sensitivity operates in.** The two interact: this parameter's whole job is to manage the rear axle while the brakes are on and the car is turning. **`08` A4's rear-stability stack is the knowledge base's most-used procedure and it needs re-establishing on 1.71 before its values are trusted.**

### 4.2 Baselines

**⚠️ All written against a 5–60 range, on v1.70 physics, and against a torque map 1.71 replaced.**

**RWD — front-engine (FR)** *[COMMUNITY, converged from flux89 + DG-Edge]*
- Init **5–10** / Accel **25–35** / Brake **8–15**
- Rationale: FR cars are traction-limited on exit and reasonably stable on entry, so accel-sens carries the load. DG-Edge cites the Aston Martin Vantage V12 at low init / **35** accel / low brake specifically because it is "tail happy."

**RWD — mid-engine (MR)**
- Init **5** / Accel **15** / Brake **20–30**
- Rationale: MR has rear weight and good natural traction; the enemy is entry rotation. DG-Edge cites the 911 RSR at **5 / 15 / aggressive-high brake**, allowing early aggressive throttle without losing the rear.

> **✅ In-house correction to the MR row, and it is one of the knowledge base's better findings:** on a **restricted** build, **15 is a ceiling, not a midpoint.** The Huracán at Laguna produced power-on mid-corner understeer from lap 1 at accel 18; **14 resolved it completely.** The mechanism is that a power restrictor cuts top-end while preserving low-end torque, so a restricted car delivers proportionally *more* torque in the early corner-exit phase than its headline power implies — and published tunes are all unrestricted max-PP builds. **Re-test accel sensitivity whenever the restrictor moves.** `08` A5.1 / D3.1. **⚠️ Measured on v1.70 against the old torque map; the reasoning carries, the number needs re-establishing.**

**RWD — rear-engine (RR, e.g. 911)**
- Init **5** / Accel **15** / Brake **25–35**
- Rationale: as MR but more so. High braking sensitivity is the primary tool for stopping the pendulum.

> ⚠️ **Note for this garage: the 911 RSR '17 is MR, not RR** — GT7's own car description says so, and it is the first 911 to use a mid-engine layout. **Use the MR row, not this one.** `07` §0.1.

**FWD (FF)**
- Init **8–12** / Accel **30–40** / Brake **5–10**
- Rationale: FF needs locking to put power down out of slow corners without lighting up the inside front. Keep braking sensitivity low or you add entry understeer to a car that already has it. Very high accel-sens will cause torque-steer-like pull and heavy front tyre wear.

**AWD (4WD)**
GT7 gives you **a front diff, a rear diff, and a Front/Rear Torque Distribution split.** All three interact and AWD is the hardest layout in the game to tune.
- Broad principle from GTPlanet: **"low values on the rear and high-ish values at the front make it more predictable accelerating out of corners."** **[COMMUNITY]**
- Worked example (Subaru WRX Gr.B road car): **Front 5/13/5, Rear 5/17/5, Centre 30:70 rear-biased.** Alternative offered in the same thread: front fully open at **5/5/5** with rear **5/25/5**.
- Generic starting point: Front **5/10/5**, Rear **8/20/10**.
- **Torque Distribution** is expressed as a front:rear ratio (e.g. 30:70). Rearward bias → more rotation, more oversteer character, less understeer, more rear tyre wear. Forward bias → more stability, more understeer, safer in the wet, more front tyre wear.
- **Tune the suspension first on AWD.** GT7's default AWD suspension setups are strongly understeery, and trying to fix that with the diff produces a car that is both understeery *and* unpredictable. The suspension "does a lot of the work here."
- **⭐ 1.71 note:** the Hyundai IONIQ 5 N's torque distribution is now freely adjustable **0:100 to 100:0**, and 1.71 added engine swaps for two AWD cars (Lancer Evo IX, Focus RS). Not relevant to this garage, but relevant to league regulation — `06` §9.1 identifies AWD as the largest structural bias in the PP system.

### 4.3 Diagnostic shortcuts

**⭐ Symptom-based and version-independent. This table is the most durable content in §4 — it works on a car whose behaviour you can no longer predict.**

| Observation | Change |
|---|---|
| Inside driven wheel lights up on exit | **Raise** acceleration sensitivity |
| Car snaps suddenly (not progressively) on power | **Lower** acceleration sensitivity (GT7's both-wheels-let-go quirk) |
| **Car pushes wide mid-corner *while on throttle*** | **Lower** acceleration sensitivity — the third failure mode, and the one that caught us out twice |
| Rear steps out on entry / on lift | **Raise** braking sensitivity |
| Car won't turn in on the brakes | **Lower** braking sensitivity |
| Car won't turn mid-corner at any throttle | **Lower** initial torque |
| Car feels nervous/darty in a straight line | **Raise** initial torque slightly |

**Watch the on-screen tyre indicators to tell the first two apart. Do not guess** — and **ask where the driver's right foot is before anything else** (`08` F2). That single question forks the whole diagnosis and has resolved two in-house cases to a single slider with no telemetry at all.

### 4.4 Common mistakes
1. **Running acceleration sensitivity too high.** The most common GT7 diff error. It feels safe in a straight line and then bites both rear wheels at once.
2. **Using initial torque as a general stability knob.** It costs mid-corner turn-in everywhere on the lap.
3. Tuning the diff before the suspension, especially on AWD and FF.
4. Copying real GT3 diff philosophy (high preload). GT7 does not reward it.
5. Ignoring braking sensitivity because "I don't have engine braking to tune." In GT7 it *is* your engine-braking tuning.
6. **⭐ Importing a track's generic diff guidance without checking the build it assumes.** Laguna's published norm of 20–28 accel was written for unrestricted max-PP cars; on the restricted Huracán it was nearly double what the car wanted. `08` A5.1.

---

## 5. AERODYNAMICS

> **⚠️ 1.71: "The initial aerodynamics settings and adjustment ranges on race cars have been fixed,"** plus adjusted initial settings on certain road cars. **Every range and every percent-of-range target in §5 is unverified.** Note the asymmetry: the notes name *ranges* for race cars but only *initial settings* for road cars — **if that asymmetry is real, the Shelby's aero range may have moved less than the two Gr.3 cars'. Worth checking; it would be a useful structural finding.**

**Unit:** a bare number with no displayed unit. Occam's Racer's analysis concludes the figures are **pounds of downforce at roughly 130 mph / 210 km/h**, validated against real data (the 911 GT3 RS makes a reported 895 lb at 124 mph; scaled to 130 mph gives 984 lb, versus GT7's listed 1000). Older GT Sport-era community belief was kilograms. **Treat as "downforce points, monotonic with real downforce"** and reason in ratios. **[COMMUNITY]**
**Range:** entirely per-car. **[GAME, v1.70]** *(Measured: Gr.3 350–450 front / 500–700 rear; Shelby Gr.N 60–160 / 150–300. See `11`.)*
**PP effect:** YES — aero is one of the few setup items that moves PP. **[STRONG]** **⚠️ And PP was recalculated fleet-wide, so press Triangle after every aero change — more, not less.**

### 5.1 Magnitudes by category (Occam's Racer, 2024)

| Category | Total downforce (front + rear) | Examples |
|---|---|---|
| Formula / LMP-tier | 2,500–3,500 | Formula ≈ 3,500; RB X2019 ≈ 2,600 |
| Gr.1 / GT500 | 1,500–2,000 | GT-One ≈ 1,500; GT500 ≈ 1,900 |
| Gr.2 / Gr.3 | 1,150–1,300 | BRZ GT300 ≈ 1,300; Gr.3 ≈ 1,150 |
| Gr.4 / full street aero kit | 250–550 | Gr.4 ≈ 550; street aero ≈ 500 |
| Road cars | 20–250 | C8 ≈ 130; M2 CS ≈ 60 |

**Aero balance:** GT7's stock aero distribution clusters around **~40% front**, and it does *not* track weight distribution — the FWD-converted Nismo GT-R LM runs a 50/50 aero split against a 65% front weight bias. So **do not set aero balance to match weight balance in GT7.** Start from the car's default ratio and move from there. **⚠️ 1.71 revised the defaults you would be starting from.**

### 5.2 The uncomfortable finding you need to know
Occam's Racer ran a controlled same-car test swapping aero packages:

| Package | Lap time |
|---|---|
| No aero | 2:06.845 |
| Street aero | 2:07.006 |
| Gr.4 aero | 2:07.076 |
| Gr.3 aero | 2:06.730 |

**1,300 lb of downforce was worth about one tenth of a second** over the whole lap. In real racing this would be several seconds. **[COMMUNITY, single-source but methodologically careful]**

**Implications:**
- **Aero in GT7 is far weaker in absolute lap-time terms than it should be, but far more powerful as a BALANCE tool than as a grip tool.** Use it to shape the car's high-speed behaviour, not to buy lap time.
- Under a PP cap, **aero is often the wrong place to spend points.** A very common and effective GT7 strategy for PP-restricted races (Sardegna WTC800 etc.): **max the rear wing, minimise the front wing.** This deliberately induces mild high-speed understeer, keeps the car safe, and — because low front downforce is cheap in PP — frees a large PP budget for power. **[COMMUNITY]**
- Conversely, in unrestricted racing on a corner-heavy track, more total downforce is still the right answer.

**⭐ One in-house refinement that survives 1.71 as reasoning:** on a rear-limited car, **rear downforce is the only source of rear grip carrying no tyre-wear penalty** — which makes it a better trade than its raw lap-time value suggests, and is why the Huracán runs its rear wing near maximum (`07` §3.5). **The reasoning holds; "near maximum" only means something once the maximum is re-read.**

### 5.3 Front vs rear

**Increase front downforce:** more front grip at speed → better high-speed turn-in and mid-corner; **shifts balance toward oversteer at speed**; more drag; raises PP. Reduces high-speed understeer, which is GT7's default road-car failure mode (hypercars with 0 front downforce "plow" through fast corners).
**Decrease front downforce:** high-speed understeer, more stability, less drag, lower PP.
**Increase rear downforce:** more rear grip at speed → **high-speed stability**, better under braking from high speed, better traction in fast corners; more drag; raises PP.
**Decrease rear downforce:** faster in a straight line, livelier and less stable at speed.

**Track-type starting points, as % of each slider's range [COMMUNITY, v1.70]:**

| Track type | Front | Rear |
|---|---|---|
| Low-speed / high-downforce (Tsukuba, Suzuka East, Autopolis) | 70–80% | 90–100% |
| Mixed (Suzuka, Spa, Fuji, Brands) | 40–60% | 55–75% |
| High-speed (Le Mans, Route X, Monza, Tokyo) | 10–30% | 20–40% |

The Coach Dave Academy method is also sound: **max the front, then bring the rear down until high-speed balance is right.** **⭐ And note `11`'s finding that on Gr.3 cars the front span is only 100 points against the rear's 200 — so "max the front" costs almost nothing and the rear is the whole aero lever.**

### 5.4 Which cars have adjustable aero
- **All Gr.1 / Gr.2 / Gr.3 / Gr.4 / Group cars and most race cars:** built-in adjustable front and rear downforce. **[GAME]**
- **Road cars:** need aero parts bought from **GT Auto** — front splitter, side skirts, rear wing, and rear **diffuser**. Only once the relevant part is fitted does that end become adjustable. Many road cars can have a *fixed*, non-adjustable value. **[GAME]**
- **Diffuser quirks** documented in the GT7 max-tuning database: an alternate diffuser type adds **+200 rear downforce and zero front**; some diffusers require the **wide body** first; and at least one diffuser type is flagged as functionally **bugged** on some cars. **[COMMUNITY]**
- **Convertibles are modelled oddly** — a tested convertible produced ~40% of the equivalent hardtop's downforce, and some cars that manifestly should have aero (E30 M3, 190E DTM) list zero. **[COMMUNITY]**
- **GT7 does not model lift** on street cars. Real road cars generate lift at speed; in GT7 they simply have low or zero downforce. This makes GT7 road cars artificially stable at high speed. **[COMMUNITY]**

### 5.5 Common mistakes
1. Expecting downforce to produce real-world lap-time gains. It won't (§5.2).
2. Matching aero balance to weight balance. GT7 doesn't work that way.
3. Spending PP on front downforce when the same points would buy more power.
4. Forgetting that adding rear downforce compresses the rear at speed — re-check ride height and rear NF afterward.
5. Not re-checking gearing after an aero change. Drag changes your top speed and therefore your final drive. **⭐ And 1.71 changed rolling resistance, which does the same thing without you touching anything.**

---

## 6. TRANSMISSION

**Unlock:** Fully Customisable Manual (works with clutch + H-pattern, has a manual shift delay) or **Fully Customisable Racing** (optimised for paddles, faster shifts). **Use Racing unless you specifically want clutch/H-pattern.** **[GAME]**
**PP effect:** installing an upgraded transmission changes PP; **the actual ratios and top speed you set do not affect PP.** **[COMMUNITY]** This makes gearing "free" performance under a PP cap — one of the highest-value moves available.

> **⚠️ 1.71: rolling resistance was optimised, which moves terminal speed independently of drag and power.** The **mechanics** of this section are untouched. **Every gearing *target* is exposed** — including both gearing constants in the knowledge base: the RSR's measured **K = 1,128 (limiter 8,600)** and the Shelby's **K = 1,096**. Both were closed on v1.70 and both need re-taking. **One lap each: hold a gear to the limiter on a long straight and read the speed.**

### 6.1 The three controls and how they interact

1. **Maximum Speed (the "auto-set" slider).** This is a **generator**, not a trim. Moving it **re-derives the entire gear set** from scratch to reach the specified top speed and **discards every individual gear ratio edit you have made.** It must be the FIRST thing you touch. **[GAME/STRONG]**
   - Slider left = lower target top speed = **shorter, more tightly-spaced gears**.
   - Slider right = higher target = **longer, more widely-spaced gears**.
2. **Final Gear.** Scales the whole set. Changing it after you've set individual gears does **not** wipe them; it shifts every ratio together.
3. **Individual gear ratios (1st … 6th/7th/8th/9th).** Each gear's own min/max is clamped by its neighbours, so you cannot cross ratios.

### 6.2 The "transmission flip" / gear-stretch method
This is the standard GT7 procedure for getting a gear set that would otherwise be unreachable. **[COMMUNITY, long-established]**

1. Reset the transmission to default.
2. Push the **Maximum Speed slider fully left** — this produces the tightest possible spacing.
3. Now drag the **Final Gear** slider **leftward** (numerically lower / longer). This "flips" and stretches the whole box, giving a set that is simultaneously close-ratio *and* long-legged — a combination the auto-set slider alone will not produce.
4. Now set the individual gears: 1st toward its left extreme, top gear toward its right extreme, and space the intermediates.
5. Finally re-trim the Final Gear to land your exact target top speed.

### 6.3 Building a gear set properly

**Governing principle (eran0004, GTPlanet):** *"The goal of transmission tuning is to try to stay as close to peak power as possible for as long as possible."*

**Procedure:**
1. **Read the dyno.** Open the car's power/torque graph in the garage. Note the RPM of peak power and how steeply power falls after it. **A peaky engine wants close ratios; a flat torque curve tolerates wide ratios.**
2. **Determine your target top speed.** Drive the longest straight on the target track and note the speed you actually reach. Set the box so you hit the rev limiter *at or just after* the braking point in top gear — not 400 m before it. **⭐ This step is the correct response to 1.71's rolling-resistance change: it measures rather than assumes, so the method needs no revision — only re-running.**
3. **Set 1st gear from the slowest corner**, not from launch. If the slowest corner is taken at 60 km/h, 1st gear should be usable there. On high-power RWD cars, deliberately **lengthen 1st, 2nd and 3rd** to reduce wheelspin — GT7's traction model rewards this heavily. **[COMMUNITY]**
4. **Space with diminishing increments.** A real GT7 tuner's Gr.3 pattern: **1st 120 km/h, 2nd 170 (+50), 3rd 215 (+45), …** — each step smaller than the last. This keeps the engine in the power band as aero drag increasingly dominates in the upper gears. A common shorthand is "lower gears wide, upper gears close."
5. **Check the shift RPM.** After each upshift, the engine should land at or just above the start of the meaty part of the curve. **⚠️ 1.71 introduced a new engine torque control map — re-check where the meaty part is.**
6. **Endurance trick:** deliberately set an artificially high target top speed so top gear runs at lower RPM on the straights. This **materially improves fuel economy** and is standard practice for WTC600/700/800. **[COMMUNITY]**

**⭐ One in-house benchmark worth keeping, and it shows what "right" looks like:** the RSR at Monza sat at **8,009 rpm at clean-air Vmax against a peak-power point of 8,100 — 98.9%**, with 7.4% of rev range still in hand for the tow. *(`setups/2026-08-12-rsr-monza-revB.md` §3. ⚠️ v1.70; that ratio is precisely what rolling resistance moves.)*

### 6.4 Common mistakes
1. **Touching Maximum Speed after setting individual gears.** You will lose all of them. This is the #1 GT7 gearbox error.
2. Gearing for the car's theoretical top speed rather than the speed actually reached on the track's longest straight.
3. Leaving 1st gear stock on a 700+ hp RWD car — you will spin up out of every hairpin no matter what the LSD says.
4. Not re-gearing after an aero change (drag changed) or a power change (band moved). **⭐ Or after a physics patch that changes rolling resistance.**
5. Forgetting km/h → mph is ×0.62.
6. Using a fixed Close Ratio Low/High box because it was cheaper. Those are non-adjustable and almost always leave time on the table.
7. **⭐ Deriving a gearing constant K by extrapolation from a non-limiter observation.** Two extrapolations on the same Huracán gearbox disagreed by 1.8% (1112.6 vs 1092.5). **Hold a gear to the limiter and read the speed — one lap closes it exactly.**

---

## 7. BRAKES

**What is adjustable:** **Brake Balance only** — a single value, **range −5 to +5**, integer steps. **[GAME, confirmed on three cars in `11`]**
**Unlock:** **Brake Controller** from the Tuning Shop. **[GAME]**
**What is NOT adjustable:** brake pressure, brake force, brake ducts, brake temperature, ABS strength via the setup sheet, per-axle brake torque. **[GAME]**

> **⚠️ Brake balance is **not** named in 1.71's revised-range list, and −5…+5 is a symmetric integer scale rather than chassis-derived, so it is likely intact. Confirm during the Job 1 re-read anyway — five seconds. What 1.71 *did* change is what a click **does**: ABS slip-ratio control and cornering brake behaviour were both adjusted.**

### 7.1 Sign convention — READ THIS
**The GT7 brake balance value is a DELTA from the car's own factory bias, not an absolute F/R percentage.** A "0" on a Gr.3 car and a "0" on a road car are completely different real biases. **[STRONG]**

**On direction, sources conflict and you should verify in-game.** The weight of evidence — DG-Edge, Coach Dave Academy, and the practical usage patterns of GTPlanet veterans (*"Forward brake balance (−5) helps me stop the cars sooner"*; *"I run most FR cars at −1 or −2"* for stability; *"+1 or +2 for more even tire wear"* on a car whose fronts wear first) — points to:

> **Negative = more FRONT bias. Positive = more REAR bias.**

At least one otherwise-good guide (Doughtinator) states the opposite. **[CONTESTED]** — **Verification test, 60 seconds:** on a straight, set the value to one extreme, brake hard with ABS off (or Weak), and observe which axle locks first. Do it once per game version and record the result.

> **✅ SETTLED.** `00-INDEX` Settled Facts records this as closed by an adversarial verification pass: three independent sources state the sign, all three agree, and a deliberate search for a dissenting source found none. **Negative = front, positive = rear, and the value is a delta from factory bias.** **A convention, not a physics value — unaffected by 1.71.** *(The 60-second test above is still worth running once on 1.71 as a free sanity check while you are on track for something else.)*

Throughout this document I use **negative = front**.

### 7.2 Effects

**More front bias (toward −5):**
- Shorter stopping distance on most cars (fronts carry more load under braking).
- Much more stable in a straight line and under trail braking.
- **Understeer on the brakes**; car resists rotating on entry.
- Front tyres wear faster; risk of front lock-up with ABS off/weak.

**More rear bias (toward +5):**
- **Rotation on entry** — the core trail-braking tool.
- Longer stopping distances.
- Instability, rear lock-up, snap on release.
- Evens out tyre wear on cars that eat their fronts (most of them).

### 7.3 Practical values by layout

| Layout | Typical | Reasoning |
|---|---|---|
| FR | 0 to +2 (some run −1/−2 for stability) | Front-heavy; a little rear bias restores rotation. Sources genuinely split here — DG-Edge recommends +2/+3 on an AMG; GTPlanet FR drivers commonly run −1/−2. Car-dependent. |
| MR | 0 to −1 | Prevent rear lock-up on an already-loose entry |
| RR | −1 to −2 | Same, more so |
| FF | +2 to +5 (some cars want max rear) | Frees the front tyres to steer instead of stopping; DG-Edge cites +5 on a Peugeot RCZ |
| AWD | 0 (default) | Usually already sensible |

> **⭐ In-house position, and it is a deliberate departure:** this driver runs **brake balance 0 as a standing rule** and takes rear stability from **LSD braking sensitivity** instead (`08` A4). That has now held across four sessions on two cars, including Monza with ABS Weak and the three heaviest stops in Gr.3, and Watkins Glen in a race won from P5. **It is one of the better-validated claims in the knowledge base — and 1.71's ABS cornering-brake change is exactly what would test it. Re-confirm early.**

### 7.4 In-race brake balance adjustment — the practical use case
Brake balance is adjustable **live via the MFD** (d-pad right to cycle displays). This is one of the highest-value in-race tools in GT7 and is badly underused. **[GAME]**

Use it for:
1. **Fuel burn.** As the tank empties, weight comes off the rear (on most cars) and the car gains entry rotation. Moving **toward the front** progressively through a stint keeps entry consistent.
2. **Tyre degradation.** As fronts go off, move **rearward** to shift work onto the fresher rears and extend front life. As rears go off, move forward.
3. **Wet weather / track drying.** Move forward in the wet (rear lock is catastrophic on a slick track), back toward baseline as it dries.
4. **Section-by-section.** Some drivers run more front bias for a heavy-braking chicane and more rear for a slow hairpin sequence.
5. **Overtaking.** A click of rear bias for one lap makes late-braking dives possible; take it back out immediately.

**Discipline:** change one click, drive two corners, decide. Do not stack changes under pressure.

**⭐ This whole subsection is a response to fuel burn and wear direction, both of which still exist on 1.71. `04` §2.8's stint-management pattern is the fuller version and it survives intact.**

### 7.5 ABS and TCS interaction
- **ABS: Default / Weak / Off.** Not on the setup sheet — it's a driving-assist menu item. **[GAME]**
- **1.55 changed ABS and TCS intervention strength.** Brake balance settings from before Jan 2025 may behave differently on the same car today. **[VERSION][STRONG]**
- **⭐ 1.71 changed both again.** *"The behaviour of the Traction Control (TCS) assist intervention has been optimised"* and *"The slip ratio control and cornering brake behaviour under ABS has been adjusted."* **Any brake-balance intuition formed before 20 August 2026 is suspect in exactly the same way** — and *"cornering brake behaviour"* names the trail-braking phase directly, which is this driver's primary technique. **[VERSION][STRONG]**
- **ABS: Weak** is the meta for competitive GT7 with a wheel — it exposes brake balance's real effect and shortens stopping distances, at the cost of lockup risk. On ABS: Default, extreme brake balance settings are partly masked by the assist, which is why some players report brake balance "does nothing."

> **⚠️ And a hardware confound to rule out before diagnosing any of this:** 1.71 also adjusted **steering wheel force feedback and understeer vibration**, and optimised **Fanatec Auto Setup parameters**. On an 18 Nm DD Extreme that is felt immediately and reads exactly like a grip or braking change. **Confirm the wheel settings first, and separate "the wheel feels different" from "the car brakes differently."** `16` §12 Job 7.

---

## 8. PERFORMANCE ADJUSTMENT, WEIGHT, AND PP

**⚠️ PP was recalculated across the fleet in 1.71. Every PP figure anywhere in the knowledge base is a v1.70 figure. `06-car-building-and-pp.md` carries the full treatment; `16` §12 Job 4 is the ten-minute audit.**

### 8.1 Ballast

**Weight:** 0–200 kg, in steps. **[GAME]**
**Position:** **−50 (fully forward) to +50 (fully rearward)**. **[GAME]** The number is a position index, not kg or mm.
**PP effect:** yes, and often **non-linear and jumpy** — single clicks can cause "drastic" PP swings. **[COMMUNITY]**

> **⚠️ Ballast is not named in 1.71's revised-range list. Confirm both ranges during Job 4 anyway** — `11` exists because assuming a range is the error that keeps recurring.

**Rearward ballast (+):**
- Moves weight distribution rearward → more traction on the driven axle for RWD, more rotation on entry, **risk of over-rotation and pendulum behaviour**.
- Increases rear tyre wear.
- Famous plug-and-play GT7 recipe for high-power RWD: **200 kg fully rearward + max rear downforce** to make an unmanageable car accelerate cleanly. Crude, effective, costs you PP and agility. **[COMMUNITY]**

**Forward ballast (−):**
- Counteracts rear-heavy handling; adds front grip and entry stability; adds understeer.
- Adds front tyre wear.
- **Usually the bigger PP reduction per kg** — forward ballast is the efficient way to buy PP headroom.

**Best-practice PP workflow [COMMUNITY]:** get under the PP cap using **forward-positioned ballast**, then spend the reclaimed PP on power or front downforce. Ballast is also the standard fix for a car whose weight distribution is fundamentally wrong for the track — e.g. a rear-unstable-under-braking car fixed with "level 1 light body + ballast back to stock curb weight, positioned fully rearward."

> **⭐ 21 Aug — ballast *position* is `06` §5.5's free-PP exploit, and it is the first place to look if a build came out of 1.71 over its cap.** Sweep −50 to +50 and record PP at each notch. The mechanism (the PP sim over-weights high-speed rotational G) should survive; **where the free PP sits along the slider is a new question on every car**, because the sim's yaw test now runs on reworked geometry and a changed damper model. **Do the sweep after the range re-read, not before.**

**Mistakes:** treating ballast as a first-line balance tool (it costs absolute performance — always try suspension, LSD and aero first); forgetting that added mass changes your natural frequency requirement (`Kw = 4π²F²M`), so springs need re-checking; not accounting for PP jumpiness when hunting an exact cap.

### 8.2 Power Restrictor vs ECU Output Adjustment
Two different ways to remove power. **They are not equivalent.** **[STRONG]**

| | Power Restrictor | ECU Output Adjustment |
|---|---|---|
| Mechanism | Restricts airflow | Electronic limit across the whole rev range |
| Effect on curve | Cuts **top-end horsepower** while largely preserving low-end torque — reshapes the curve | Scales the **entire** curve proportionally |
| Use when | You need corner-exit torque but must lose top-end/PP (twisty tracks) | You want the car to feel identical, just less powerful |
| Side effect | Changes optimal gearing | Small fuel-economy gain |
| Unlock | Power Restrictor part | Full Control Computer |
| PP | Reduces | Reduces |

**Practical:** on a tight, traction-limited track, the restrictor is usually the better tool — you keep the torque you actually use and pay for it in top speed you don't. On a fast track, the ECU is more predictable. **Re-gear after either.**

> **⭐ And re-test LSD acceleration sensitivity after either** — the restrictor changes the *shape* of the torque the diff has to manage, which is the mechanism behind the in-house accel-14 finding (§4.2, `08` D3.1). **Treat re-gearing and re-testing the diff as one job. 1.71's new torque control map means this now applies after a patch as well as after a restrictor change.**

### 8.3 Weight Reduction and Body Rigidity

**Weight Reduction** comes in numbered stages (Lightweight Level 1, 2, 3, …), each removing a fixed mass and **raising PP**. Stages are cumulative and irreversible in effect (though you can add ballast back). Lighter = better acceleration, braking, direction change, and lower tyre wear — but under a PP cap, weight reduction *costs* you PP you might rather spend elsewhere. The "light body + ballast" combination (fit the light body, then add ballast where you want it) is the standard way to buy **weight distribution control** at the cost of PP. **[STRONG]**

**⚠️ Irreversible, and PP just moved fleet-wide. Do the Job 4 audit before buying any further weight reduction** — an over-stripped car has fewer ways to come back under a cap that shifted.

**Body Rigidity Improvement** behaves counter-intuitively in GT7's PP model. Experienced tuners' explanation: *"a car that's made too stiff for its old, floppy suspension will be worse in corners"* (so PP goes **down**), while *"a car that's too floppy for its new, sparkly suspension will be better in corners with a rigidity increase"* (PP goes **up**). **Rigidity can raise or lower PP depending on what suspension is fitted.** **[COMMUNITY]** Always check PP after fitting it. **⚠️ The mechanism depends on how the PP sim reads roll — and 1.71 changed damper attenuation and revised suspension defaults, which is to say it changed how the car rolls in the sim's cornering test. Re-test.**

**Wide Body** always **lowers PP** despite improving handling — one of the most exploitable quirks in GT7's PP system. It also unlocks certain diffusers. **[COMMUNITY]** **⚠️ Depends on aero, which moved. Re-test.**

### 8.4 How PP actually works

Kazunori Yamauchi has stated PP is derived by the game **driving your car on a virtual test track** and deriving a performance number, rather than from a closed-form formula. **[STRONG]**

Consequences:
- PP weights **straight-line speed and lateral g** most heavily. **[COMMUNITY]**
- **Suspension settings do not affect PP at all** — ride height, springs, ARBs, dampers, camber, toe are entirely free. So are gear ratios and brake balance. **[STRONG]** This is enormous: under a PP cap, **all of your chassis tuning is free performance.**
- Aero, power, weight, tyres, and installed parts *do* affect PP.
- Downforce has a non-monotonic PP effect: *"you get more grip (higher PP), but at some point if you don't have enough power you lose top speed (lower PP)."* On an underpowered car, **adding downforce can lower PP.** **[COMMUNITY]**
- The system has acknowledged bugs and inconsistencies; the virtual test drive occasionally produces anomalous results. Always press Triangle to recalculate after any change, and re-check before entering a capped event.

> **⭐⭐ 21 Aug — this section predicted 1.71 and got it exactly right, which is worth noting because it tells you which claims to trust.** If PP is the output of a simulated test drive rather than a formula, then **changing the physics necessarily re-rolls PP** — and that is what happened, for the fourth time since launch (1.49, 1.55, 1.71). **It was not a rebalance PD chose; it was a side effect they had to absorb**, which is why the PP line sits alongside the physics lines in the notes rather than in a balance section.
>
> **The structural claims here survive. The numbers do not.** And the last bullet — *the virtual test drive occasionally produces anomalous results* — is a standing warning that is about to matter: after 1.49, some cars returned **no PP value at all**, with Racing Softs, carbon-ceramic brakes, Fully Customisable Suspension, superchargers and engine swaps all implicated. **If a build loses its PP number on 1.71, work through that list.** `06` §9.3 has the league rule that this warrants.

---

## 9. EVERYTHING ELSE

### 9.1 Traction Control (TCS)
**Range 0–5**, not on the setup sheet — it's a driving assist, but it is per-car-saved and functionally part of the setup. **[GAME]**
- **TCS 0:** fastest in theory; required for any competitive time-trial work; mandatory on dirt/snow (TCS actively hurts on loose surfaces).
- **TCS 1:** the common "insurance" setting — most players report near-zero measurable lap-time cost while catching the worst exits.
- **TCS 2:** useful on very high-power RWD, in the wet, or late in a stint on worn tyres.
- **TCS 4–5:** significantly slows corner exit; keeps the car on track for less experienced drivers.
- **Mechanism:** GT7's TCS brakes the spinning wheel and feeds power back gradually. Higher settings mean **longer intervention periods**, which is where the lap time goes.
- **1.55 changed TCS intervention strength** — old TCS advice may not hold. **[VERSION]**
- **⭐ 1.71 "optimised" TCS intervention behaviour.** `03` §2.5 puts the v1.70 price at up to **two tenths per corner**; that price is now unknown, and "optimised" most often means less intrusive — which would make TCS 1 cheaper and change the sprint-vs-stint calculus. **Untested in either direction. `16` §12 Job 7: three laps at 0, three at 1.** **[VERSION]**
- **Use it dynamically:** raising TCS by one as the rear tyres degrade is a legitimate in-race strategy via the MFD.
- **If you need TCS 3+, tune the LSD instead.** Persistent wheelspin is a diff/gearing/rear-spring problem, not a TCS problem.

### 9.2 Steering angle
**GT7 has no steering-lock / maximum-steering-angle setting on the tuning sheet.** Steering geometry is per-car and fixed. What you *can* change:
- **Countersteering Assist** (on/off) — a driving assist; must be off for serious work.
- **Wheel rotation and force settings** in the peripheral/game options.
- 1.49 and 1.55 both **changed steering geometry** (wheel) and the **steering algorithm** (pad sticks/buttons). If a car's turn-in feel changed without you touching it, that's why. **[VERSION][GAME]**

> **⭐⭐ 1.71 makes three.** *"The steering geometry **for each car** has been optimised, improving the simulation of turning forces."* **This is the most consequential single line in the patch notes for this document**, because steering geometry is upstream of camber (§3.5), toe (§3.6) and turn-in feel generally — and because *"for each car"* means the effect may differ between the cars in the garage rather than shifting everything equally.
>
> **If a car's turn-in feel changed without you touching it, that is now the most likely reason** — and the second most likely is that 1.71 also adjusted **wheel force feedback and understeer vibration**, which feels similar and is not the same thing. **Separate them before diagnosing.**

### 9.3 Hydraulic Handbrake
An **Extreme**-tier Tuning Shop part. It is a **binary install**, not a tunable value — it gives you a handbrake input for drifting, gymkhana and rally-style driving. No numeric setting on the sheet. **[GAME]**

### 9.4 Nitrous / Overtake
An **Extreme**-tier part with an **output percentage** setting: the percentage dictates how strong the boost is when triggered. Higher = bigger power spike, more PP, more traction risk. Banned or unavailable in most competitive events. **[GAME/COMMUNITY]** **⚠️ Reportedly costs 0 PP — if that still holds on 1.71, it remains unregulatable by a PP cap and should stay banned. `06` §9.2.**

### 9.5 Anti-Lag System
A turbo part reducing spool lag; sold in tiers. It changes throttle response and therefore **how your LSD acceleration sensitivity and gearing behave** — an anti-lag car applies torque far more abruptly, which in GT7's model means the "both wheels let go at once" failure mode arrives sooner. Re-check the diff after fitting it. **[COMMUNITY]** **⚠️ And 1.71's new engine torque control map changes throttle response independently — same interaction, new baseline.**

### 9.6 Fuel Map (in-race only)
Adjustable via MFD; requires the **Fully Customisable Computer** (≈ Cr. 4,500). **[GAME]**

> **📝 CORRECTION.** This section states the range as "1 to 5 or 6 depending on car." **`03` §5.4 settles it from the official Gran Turismo World Series guide: the fuel map is a six-level control on every car, 1 to 6, with 1 = richest / maximum power.** Several third-party outlets state 1–5 and at least one inverts the direction; **they are wrong, and the official Polyphony source is unambiguous on both count and direction.**

Higher numbers reduce engine output and improve consumption. The MFD estimates remaining laps at the selected map. Fuel map, not tuning, is the primary endurance-strategy lever — combined with the long-top-gear trick from §6.3.

**⚠️ The 4%-power-per-step / 8%-fuel-per-step arithmetic (`03` §5.5) is GT Sport-era and was already overdue for re-testing. 1.71's new torque control map makes it more likely to have moved, not less.**

### 9.7 Downforce-less cars
Many road cars, classics and one-makes have **zero adjustable aero at either end** (and no available parts). For these, everything aero would have done must be done mechanically:
- High-speed stability → **rear toe-in** (+0.15 to +0.30), higher rear NF, higher LSD braking sensitivity, forward brake balance.
- High-speed turn-in → front toe, front ARB, lower front ride height.
- Accept that the car's high-speed balance is essentially fixed and tune the low-speed behaviour instead.
- Note GT7 **does not model lift** on street cars, so a downforce-less GT7 car is *more* stable at speed than its real counterpart would be — don't over-correct.

### 9.8 The Data Logger (1.65+) — your new diagnosis tool
Added in Spec III (Dec 2025), expanded in 1.67 (more graph types) and 1.68 (Drift Analyzer). It allows **direct lap-versus-lap telemetry comparison between any two laps, in any cars, at a given circuit**, across all single-player events **including Online Time Trials**. It is **not** available in Daily Races or GTWS rounds. **[GAME]**

This changes the tuning workflow fundamentally: for the first time you can do a genuine A/B on a setting rather than relying on feel. **Use it for every camber sweep, every toe test, and to settle the brake-balance sign convention question in §7.1.**

> **⭐ 21 Aug — and it is the right instrument for the whole 1.71 rebuild.** `16` §12's jobs are almost all A/B comparisons. **One caveat: every reference lap and ghost recorded before 20 August 2026 is on old physics — PD reset their own leaderboards for exactly that reason.** A comparison against your own old laps mixes the patch with your driving. **Rebuild the reference laps early.**

---

## 10. DIAGNOSIS — SYMPTOM TO FIX

> **⭐ THE MOST DURABLE SECTION IN THIS DOCUMENT, AND THE ONE TO USE DURING THE REBUILD.** These tables rank *which lever owns which corner phase*. The phases still exist and the levers still own them. **Directions hold; magnitudes need re-calibrating.** A symptom-based diagnostic is exactly what you want on a car whose behaviour you can no longer predict — and it needs no baseline to work.

### 10.1 How to use these tables
Fixes are **ranked by effectiveness** — try #1 first. Change **one thing at a time**, run **three clean laps**, and use the Data Logger. If a fix produces no detectable change, undo it before trying the next; stacked null changes are how setups rot.

**Tags (plan row 2.8, 11 Sep 2026).** Every fix row below is **[COMMUNITY]** — a pre-1.71 community ranking — unless it carries its own tag. **[IN-HOUSE ✅]**, **[IN-HOUSE ❌]** and **[CONTESTED]** are scored in `brain/ledger/<car>-<circuit>.md` on v1.71, with the car and circuit named: one car at one circuit is a direction, not a ranking. **The ordering of every table is still the community's** — none has been re-ranked from in-house evidence. Values quoted as "+5" or "−2 to −4" are the community's absolute steps; on v1.71 issue a change in percent of the car's own range (`11`).

**Before you touch anything, ask three questions:**
1. **Is it the setup or the driver?** A car that only misbehaves when you're 5 km/h too hot on entry is a driving problem.
2. **Is it arch rub or bottoming?** Post-1.49, a car that abruptly refuses to turn, or bounces for seconds after a kerb, is a **ride height** problem masquerading as a balance problem. Raise ride height 3–5 mm and re-test before diagnosing anything else. **[VERSION]** **⚠️ Status on 1.71 [UNKNOWN] — keep the step; it costs one run and the failure mode it catches is severe.**
3. **Which phase?** Entry (braking → turn-in), mid (steady state, off/neutral throttle), exit (throttle applied → track-out). Different phases, different tools. Getting this wrong is the root of most bad setups.

> **⭐ Add a fourth, from `08` F2, and it is the highest-information question of the four: *where is the driver's right foot?*** Off throttle, trailing brake, or on power. It forks the whole diagnosis and has twice resolved an in-house case to a single slider with no telemetry at all. **And a fifth: *which corners are FINE?*** The silent corner localises the fault — at Laguna, T11's silence identified the problem in one step.
>
> **⚠️ And for the next few sessions, a sixth: is the car built as written?** 1.71 may have reset or clamped saved values (`16` §12 Job 0), and the Pit Crew `setup` block has been stale three sessions out of three. **Confirm which sheet is physically in the car before diagnosing anything.** Standing Rule 9.

### 10.2 Which parameters own which phase

| Phase | Primary tools | Secondary |
|---|---|---|
| **Entry / braking** | Brake balance, front compression damping, rear expansion damping, LSD braking sensitivity, front toe | Rake, rear toe, front NF |
| **Mid-corner** | ARBs (F/R), natural frequency split, camber, aero balance | LSD initial torque, ride height |
| **Exit / traction** | LSD acceleration sensitivity, rear NF, rear compression damping, gearing | Rear toe, rear downforce, ballast position, TCS |
| **Straight line** | Rear toe, camber, aero total, gearing, LSD initial torque | Ride height |

---

### 10.3 Corner-entry understeer under trail braking

| # | Fix | Direction | Notes |
|---|---|---|---|
| 1 | **Brake balance** | Rearward (toward +) | Fastest, free, adjustable in-race. 1 click at a time. **[IN-HOUSE ✅]** RSR, Sardegna: +10 pp then +20 pp, more entry rotation, driver report and rear slip (ABS on, so the front slip channel was blind). On the RSR the steps were issued as sheet changes (Rev B, Rev C); where the bias moves by his own hand it is his trim - recorded, never corrected (`brain/driver.md`). |
| 2 | **LSD braking sensitivity** | **Lower** | Often the true culprit, especially on RR/MR where it's set high for stability. **[IN-HOUSE, one direction only]** Huracán, Daytona: *raising* it +5 pp cost entry rotation at T1 by more than 2x (s147, confirmed as a cost) — the driver's "lsd_b is too high". **Lowering it is untested in house:** the one step down (s127, −5 pp, his own ask) is open |
| 3 | **Front compression damping** | **Lower** (−2 to −4) | Lets weight transfer forward faster; more front bite on turn-in |
| 4 | **Rear expansion damping** | **Higher** (+2 to +4) | Controls rear rise, keeps the platform rotating |
| 5 | **Front toe** | Test **both** directions ±0.05 | GT7's contested area; A/B it, don't assume |
| 6 | **Front ARB** | Softer −1 | Also affects mid-corner |
| 7 | **Rake** | More positive (raise rear / lower front, 2–3 mm) | Coarse; watch bottoming |
| 8 | **Front downforce** | Up / rear down | Only meaningful on genuinely high-speed entries |
| 9 | **Ballast position** | Rearward | Last resort; costs elsewhere |

**GT7 traps:** adding front camber (won't help — camber is mid-corner in GT7 and costs braking); softening front springs (this is a *load transfer rate* problem, and springs are slower-acting than dampers); assuming your car has entry understeer when it actually has arch rub.

---

### 10.4 Mid-corner understeer

| # | Fix | Direction |
|---|---|---|
| 1 | **Front ARB softer** or **rear ARB stiffer** (−1 / +1) — the canonical mid-corner lever. **[IN-HOUSE ✅]** rear bar stiffer on two cars: Huracán, Daytona (+22.2 pp, middle-sector median −0.449 s, s149) and RSR, Sardegna (one click, driver "perfect", s158). The rotation index missed both — see the ledgers. **[IN-HOUSE ❌ front bar softer]** Huracán, Daytona: −22.2 pp refuted - rotation unchanged and roll up (s148; its axis register: refuted twice) |
| 2 | **Front natural frequency** softer 1–2 clicks (and/or rear stiffer) |
| 3 | **LSD initial torque** lower — high preload is a hidden cause of persistent mid-corner push |
| 4 | **Front camber** — sweep it; in GT7 this *is* the mid-corner tool, but the optimum is low |
| 5 | **Aero balance** — front up / rear down (only matters above ~150 km/h). **[IN-HOUSE ✅]** RSR, Sardegna: front wing +20 pp twice, "much better" then "much more pointed", no measurable top-speed cost (Rev D/E) |
| 6 | **Rear toe** toward zero — big rear toe-in is a silent understeer generator |
| 7 | **Ride height** — lower the front 2–3 mm |
| 8 | **Ballast** forward-to-rearward shift |

**Traps:** stacking front camber (GT7's optimum is 1.0–2.5°, not 3.5°); adding front downforce on a slow track where it does nothing.

> **⚠️⚠️ AND THE BIG ONE, WHICH HAS CAUGHT US TWICE: check the throttle state first.** If the push happens **on throttle**, this is the wrong table — go to §10.5 and lower LSD acceleration sensitivity. Every fix listed above adds front grip, which *masks* a power-on push while costing roll control or entry stability. **At Laguna, front ARB and front downforce were both queued as fallbacks and neither was needed once the diff was right. At Monza, the same trap was pre-registered and avoided again.**

---

### 10.5 Corner-exit understeer (power understeer)

| # | Fix | Direction |
|---|---|---|
| 1 | **LSD acceleration sensitivity — LOWER.** The dominant cause. High accel-sens makes GT7 cars "want to drive in a straight line and not continue turning". **[CONTESTED on v1.71, on a DERIVED index]** Huracán, Daytona: lowering it −6 pp did NOT bring the on-power rotation index back (s145, refuted), and raising it moved that index up, monotonic across two steps (s146, confirmed) - the opposite of this row. But the net +6 pp over the baseline sat inside the floor (unresolvable), and the higher setting cost **2 T5-exit spins in 10 laps**. The index is [DERIVED]; the driver prefers the higher setting, his call (rule 1). The two v1.70 validations below are the other side |
| 2 | **Rear ARB stiffer** +1 |
| 3 | **Rear compression damping higher** (+2 to +4) — keeps weight forward under power |
| 4 | **Front expansion damping higher** (+2 to +4) — keeps the front loaded through track-out |
| 5 | **Rear natural frequency stiffer** |
| 6 | **Rear toe** toward zero |
| 7 | **Ballast rearward** (increases rear grip but also increases rotation — mixed) |
| 8 | **Shorten the gear** you're in, so you're using more of the power band and less brute torque |

**AWD-specific:** shift **torque distribution rearward**, and open the **front** diff (lower front accel sensitivity). GT7 AWD exit understeer is nearly always a front-diff-too-locked problem.
**FWD-specific:** exit understeer is usually a **traction** problem, not a balance problem — raise front accel sensitivity, soften front springs, lengthen 1st/2nd.

**⭐ Fix #1 is the single most validated entry in this whole section — twice in-house, on two different cars, at two different circuits.** *(Huracán/Laguna −7.3 pp; RSR/Monza −3.6 pp, of the v1.70 range.)* **⚠️ Both are v1.70 and 1.71 replaced the torque map. And on v1.71 the one in-house test ran the other way (the tag on #1), so the direction is contested too, not only the magnitude.**

---

### 10.6 Corner-entry oversteer / instability turning in on the brakes

| # | Fix | Direction |
|---|---|---|
| 1 | **Brake balance forward** (toward −) — instant, in-race adjustable |
| 2 | **LSD braking sensitivity HIGHER** (+5 to +15) — the most effective structural fix, especially MR/RR. **[IN-HOUSE ✅]** Huracán, Daytona: +12 pp removed the rear brake lock at the first corner (s126); the price is less rotation on release, and at +5 pp more it cost entry rotation (s147) |
| 3 | **Rear toe-in** +0.05 to +0.15 |
| 4 | **Front compression damping higher** (+2 to +4) — slows the load transfer onto the nose |
| 5 | **Rear expansion damping lower** (−2 to −4) — lets the rear settle instead of levering itself up |
| 6 | **Reduce rake** — equalise ride heights; positive rake promotes entry rotation. **[IN-HOUSE ❌ for entry instability]** Huracán, Daytona: rear ride height −20 pp did NOT cut the T1 opposite-lock laps (5 of 15, refuted) - though it held on pace and on his report, a different claim (confirmed). On the Shelby there is no ledger row: that rake is not its lever is an argument from its range record alone (both floors are 20 mm apart) |
| 7 | **Front ARB stiffer** +1 |
| 8 | **Front NF stiffer** / rear softer |
| 9 | **Rear downforce up** (only above ~150 km/h) |
| 10 | **Ballast forward** |

**⭐ For this driver, take #2, #3 and #5 before #1** — brake balance stays at 0 as a standing preference and the rear is stabilised mechanically (§7.3, `08` A4). That approach has held across four sessions on two cars. **⚠️ 11 Sep 2026: not the standing preference on the RSR or the Shelby.** The RSR moved it rearward at Sardegna (`brain/ledger/rsr-sardegna-road-track-a.md`, confirmed), and the Shelby runs it forward of centre by his own trim (`brain/car-state/shelby-deep-forest.md`). **The Shelby's own data argue for the old approach on that car** - its front locks on 47 of 47 laps at Deep Forest (`07` §5.9) - and the call is his.

---

### 10.7 Snap oversteer on lift

Lift-off oversteer is a **transient** and needs transient tools. Note the GT7-specific observation that much of what players call snap oversteer in GT7 actually occurs **under acceleration**, not deceleration — so first confirm which you have.

| # | Fix | Direction |
|---|---|---|
| 1 | **LSD braking sensitivity HIGHER** — the single best lift-off fix in GT7 |
| 2 | **Rear expansion damping LOWER** — a rear that extends too fast on lift unloads the rear tyres abruptly |
| 3 | **Rear toe-in** +0.10 |
| 4 | **Rear ARB softer** −1 |
| 5 | **Rear NF softer** — a stiff rear on a soft front will snap |
| 6 | **Reduce rear camber** — excess rear camber reduces the rear's longitudinal reserve and makes the letting-go sharper |
| 7 | **Front compression higher** — reduces the pitch-forward spike |
| 8 | **Ballast forward** |

**If the snap is actually on-throttle:** go straight to **LSD acceleration sensitivity — lower**. GT7's high-lock diffs release both driven wheels simultaneously, which is exactly what a "snap" feels like. This is the most under-diagnosed problem in GT7.

---

### 10.8 Instability under straight-line braking

| # | Fix | Direction |
|---|---|---|
| 1 | **Brake balance forward** |
| 2 | **LSD braking sensitivity higher** — **[IN-HOUSE ✅, into a corner]** Huracán, Daytona: +12 pp removed the rear lock braking into T1 (s126) |
| 3 | **Rear toe-in** +0.05 to +0.10 |
| 4 | **Reduce camber at BOTH ends** — GT7 penalises camber's longitudinal cost heavily; excess camber is a common and unrecognised cause of poor braking |
| 5 | **Rear expansion damping higher** |
| 6 | **Reduce rake** to level |
| 7 | **Front toe to 0.00** — remove any toe-out |
| 8 | **Rear downforce up** for high-speed braking zones |
| 9 | **Check for bottoming under braking** — front ride height up 2–3 mm |

**Also check:** ABS setting (a car that's fine on Default and terrible on Weak is a brake-balance problem, not a chassis problem), and whether you're braking over a crest or camber change. **⚠️ And on 1.71, whether the wheel's FFB settings changed — see §7.5.**

---

### 10.9 Poor kerb riding / bouncing / hopping over kerbs

This is **the** signature GT7 post-1.49 problem, only partly addressed by 1.55's short-period-bump changes. **[VERSION]** **⚠️ And the area 1.71's damper attenuation change most directly targets — *"road surface tracking"* is kerb behaviour by another name. Re-establish before trusting the ordering below.**

| # | Fix | Direction |
|---|---|---|
| 1 | **Raise ride height** 3–5 mm at the affected end (or both) — always try this first now |
| 2 | **Reduce compression damping** toward the bottom of its window (e.g. 30 → 25). **[CONTESTED in house - the driver and the instrument disagree]** Huracán, Daytona Bus Stop kerb: softer both ends, the body swing did not fall (refuted) and the driver says it is fixed (confirmed). Both kept, not averaged (rule 1) |
| 3 | **Reduce expansion damping** (e.g. 40 → 35) — a slow-rebounding damper packs down over successive kerb strikes |
| 4 | **Soften ARBs** −1 to −2 both ends — ARBs transmit single-wheel kerb inputs across the axle and are a huge kerb-hop contributor |
| 5 | **Soften natural frequency** 1–2 clicks |
| 6 | **Reduce camber** — part of the standard post-1.49 recipe; changes how the tyre sits in the arch |
| 7 | **Reduce downforce** if very high — aero preload eats your bump travel |

**Diagnostic distinction:**
- **Hops once and settles** → too stiff. Springs and ARBs.
- **Bounces repeatedly for 1–3 seconds** → damping/spring frequency mismatch, or the known post-1.49 compression bug. Try a *large* NF change (±0.3 Hz) rather than small damper tweaks — if the car "bounces twice" as load comes off, that's a frequency mismatch.
- **Bangs and then won't steer** → **arch contact.** Ride height only. No other fix works.

> **⭐ This three-row table is the most useful diagnostic in the document and it is symptom-based, so it survives.** It has been used successfully in anger: the RSR at Monza reported *"bounces repeatedly"*, which picked the middle row cleanly and **overrode a queued ride-height change that would have been the wrong branch** (`setups/2026-08-12-rsr-monza-revB.md` §2.2). **The ordering of the numbered list above it is what needs re-checking; the three rows do not.**

---

### 10.10 Traction limitation on exit (wheelspin)

| # | Fix | Direction | Notes |
|---|---|---|---|
| 1 | **Lengthen 1st / 2nd / 3rd gears** | Longer | Massively underused in GT7 and often the largest single gain on high-power RWD |
| 2 | **LSD acceleration sensitivity** | **Raise** if the *inside* wheel is spinning; **lower** if both are letting go together | Watch the on-screen tyre indicators to tell which |
| 3 | **Rear natural frequency softer** 1–2 clicks | Softer | More compliance = more contact |
| 4 | **Rear compression damping lower** (−2 to −4) | Lets the rear squat and load up |
| 5 | **Rear ARB softer** −1 | More rear grip |
| 6 | **Ballast rearward** | + | Very effective on RWD; costs entry stability |
| 7 | **Rear downforce up** | Only helps above ~120 km/h |
| 8 | **Reduce rear camber** toward 1.0–1.5 | Camber costs longitudinal grip in GT7 |
| 9 | **Rear toe-in** +0.05 | Cheap stability under power |
| 10 | **TCS 1** | Insurance, ~free in lap time ⚠️ *price unknown on 1.71* |
| 11 | **Power restrictor** | Only if the car is genuinely undriveable |

**⭐ And a twelfth that is not on the sheet at all: short-shift the slow exits.** Costs ~0.5 s/lap, cuts fuel ~20%, and keeps the engine out of peak torque on exit — a traction tool on a torque-limited car. **It is what won the 17 Aug Watkins Glen race**, and it dropped that circuit's worst corner from 1.57 s lost to 101 ms with no setup change at all. ⚠️ *New torque map in 1.71 — re-check the shift points.*

---

### 10.11 Excessive tyre wear on one axle

GT7 **does** model per-axle wear, and **fronts almost always wear faster than rears** — including on FR and MR cars — because of combined braking and steering load. **[COMMUNITY]** **[CONTESTED in house on v1.71]** the RSR's worst wheel at Sardegna is the **rear-right**, throughout a full-length stint (confirmed); the Shelby's is a front at Red Bull Ring and Deep Forest, where the front/rear split was only 5.9 %. **⚠️ A post-1.49 characterisation. 1.71 adjusted wear values and reworked the slipping regime; which axle goes first is an open question again. `03`'s banner has the detail.**

**Front tyres wearing out:**
| # | Fix |
|---|---|
| 1 | **Brake balance rearward** — the highest-leverage fix, and adjustable mid-race. GT Sport/GT7 veterans consider this the primary tool |
| 2 | **Front toe toward 0.00** — toe is the biggest alignment contributor to wear |
| 3 | **Front camber −0.3 to −0.5°** |
| 4 | **Front ARB softer** — less load transfer onto the loaded front |
| 5 | **Reduce front downforce** (if it's causing sustained high load). **[IN-HOUSE: no measured effect at this size, tested the other way]** Huracán, Daytona: front wing +40 pp and rear +25 pp, aimed at rear wear, moved no measured load or wear (runs 5-6). Reducing it was not tested; the direction is not refuted |
| 6 | **Ballast rearward** |
| 7 | Address any mid-corner understeer — a pushing car scrubs its fronts continuously |

**Rear tyres wearing out:**
| # | Fix |
|---|---|
| 1 | **LSD acceleration sensitivity −5** — high locking scrubs both rear tyres on every exit. *(−5 was 9 pp of the v1.70 5–60 range; on v1.71's 0–100 read it as a direction.)* |
| 2 | **Rear toe toward 0.00** — big rear toe-in is expensive in wear |
| 3 | **Rear camber −0.3 to −0.5°** |
| 4 | **Brake balance forward** |
| 5 | **Rear ARB softer** |
| 6 | **Ballast forward** |
| 7 | Lengthen lower gears to stop wheelspin |

**General wear reducers:** softer springs and ARBs improve compliance and reduce scrub over bumps; less total camber and toe at both ends; and the fuel map — a car in map 3 makes less torque and spins less. **[IN-HOUSE, v1.71]** short-shifting cut the RSR's rear-right wear on Racing Medium by 8.7 % within one stint at Sardegna (confirmed), did not measurably move it on Racing Hard, and cost about 1.0 s/lap — so it did not buy an extra lap. Note that **1.49 introduced a new racing-tyre heating and degradation model**, so wear behaviour and optimum strategy changed materially in July 2024. **[VERSION]** **⭐ And 1.71 adjusted heating and wear values again — see `03`.**

> **⚠️⚠️ Before spending any of these: `03` §8.6's rule.** *Every defensive setting on the sheet should be able to name the measured limit it is protecting against.* **On v1.71 not one of them can, because no wear limit has been measured.** The last time conservatism was spent against an unmeasured limit it cost ~28 seconds at Laguna and the model was 1.8× wrong; at Monza it was 5× wrong. **Build the car the driver can drive, leave the tyre-saving budget unspent, and go and measure.**

---

### 10.12 Other symptoms

| Symptom | Ranked fixes |
|---|---|
| **Car feels "on tiptoes" / skates over the surface** | 1. Reduce NF both ends. 2. Reduce compression damping. 3. Soften ARBs. 4. Raise ride height. |
| **Car feels wallowy / vague / slow to respond** | 1. Increase NF both ends. 2. Stiffen ARBs +1. 3. Increase compression damping. 4. Lower ride height (if travel allows). |
| **Poor straight-line stability / darty** | 1. Rear toe-in +0.05 to +0.10. 2. Front toe to 0.00. 3. Increase LSD initial torque slightly. 4. Reduce excessive camber. 5. Increase rear downforce. 6. Check for negative rake. |
| **Car bottoms out / scrapes** | 1. Raise ride height 3–5 mm. 2. Stiffen NF. 3. Increase compression damping. 4. Reduce downforce if extreme. |
| **Rear "chatters"/skates under combined braking+cornering** | Reduce **rear compression damping** — this specific oscillation mode is documented in GT7. |
| **Car won't rotate at ANY point on the lap** | 1. LSD initial torque down. 2. Rear toe toward 0. 3. Front ARB softer / rear stiffer. 4. Check total camber isn't excessive. |
| **Car won't hold line on maintenance throttle** | **LSD acceleration sensitivity down.** Confirmed in-house on the RSR at Monza — the tell was the outside rear running 11 °C hotter than the front-left while the inside front sat coldest on the car. |
| **Great in slow corners, terrible in fast ones** | Aero balance and rear NF. Slow-corner behaviour is mechanical; fast-corner behaviour is aero + platform stiffness. Tune them separately. |
| **Terrible in slow corners, great in fast ones** | Mechanical grip: soften springs and ARBs, reduce LSD initial torque, check gearing for the slowest corner. |
| **Inconsistent lap to lap** | Usually too stiff, too much camber, or too much LSD lock. Soften everything 10% and re-baseline. |
| **⭐ Everything feels different and you changed nothing** | **Check the game version first.** Then check the wheel's FFB settings (1.71 changed FFB and understeer vibration), then confirm the car is built as written (the patch may have clamped values). Only then diagnose the chassis. |

---

## 11. RECOMMENDED WORKFLOW

> **⭐ For the first sessions on 1.71, three jobs come before step 1** — `16` §12: confirm the saved tunes survived (2 min), re-read the slider ranges (15 min), and take one comparison measurement (30 min). **Steps 1–3 below cannot be executed meaningfully until the ranges are known.**

1. **Fix the platform first.** Ride height + natural frequency, both ends. Get the car off the bump stops and out of the arches. Post-1.49 this is mandatory, not optional.
2. **Gears.** Free in PP. Max Speed slider → final drive → individual gears. Do this before balance work, because gearing changes exit behaviour. **⭐ And re-gear on 1.71 regardless — rolling resistance changed.**
3. **Aero (if adjustable) and any PP-affecting parts.** Lock in your PP budget before spending time on chassis feel. **⭐ Read the PP number *before* you start too — the build may already be over the cap.**
4. **Mid-corner balance with ARBs.** Coarse, effective, integer steps.
5. **LSD.** Start low: init 5, accel 15–25, brake 10–20 depending on layout. Fix exit traction and entry stability here, not with toe.
6. **Brake balance.** Set the entry phase.
7. **Dampers.** Fine-tune the entry and exit transients using the four-quadrant table. **⚠️ If 1.71 gave dampers back their authority (§1.2 item 2), this step may deserve to move earlier. Test before reordering.**
8. **Camber sweep.** One axle at a time, Data Logger on. **⚠️ Sweep it on 1.71 regardless of what the sheet says — the geometry rework may have changed the sign of the answer.**
9. **Toe.** Last. Trim only. ±0.05 steps. **In absolute degrees, never percent.**
10. **Ballast.** Only if steps 1–9 couldn't get there.
11. **Re-check ride height and PP.** Everything you did changed the static and dynamic ride height and possibly the PP.

**Discipline rules:** one change per run; three clean laps minimum; write down what you changed and the resulting time; if you can't feel it and the Data Logger can't see it, revert it. **⭐ And record the game version alongside the change — Standing Rule 10.**

---

## 12. GT7 QUIRK SUMMARY — THE TWELVE THINGS THAT DIFFER FROM REAL ENGINEERING

**Annotated 21 Aug 2026 for 1.71 exposure. ✅ = structural, survives. ⚠️ = in play.**

1. ⚠️⚠️ **Negative camber is heavily over-penalised.** GT7's optimum is roughly half real-world values, and camber costs braking and traction immediately. Front camber acts **mid-corner**, not at turn-in. *— **The steering geometry model behind this was reworked per car. Highest-priority re-test in the knowledge base.***
2. ✅ **Dampers are damping RATIOS**, auto-scaled to spring rate. Change springs and the damper numbers still mean the same thing. Opposite to most sims. *— Structural. Unaffected.*
3. ✅ **No high/low-speed damper split.** One curve per direction, per end. *— Structural.*
4. ✅ **Rake does not drive aero.** It is a mechanical effect only. The GT4-era "lower the rear for top speed" trick is dead and now causes arch rub. *— The aero half is structural; the arch-rub half is [UNKNOWN] on 1.71.*
5. ⚠️ **Aero is nearly worthless for lap time but valuable for balance and expensive in PP.** 1,300 lb of downforce measured at ~0.1 s per lap. *— Aero defaults, ranges and PP all moved.*
6. ✅ **High LSD locking produces a simultaneous two-wheel breakaway**, not a progressive slide. Run lower acceleration sensitivity than you would anywhere else. *— Ordinary spool physics rather than a GT7 anomaly, which is why it survives. The **values** do not.*
7. ✅ **LSD braking sensitivity is your only engine-braking tool** and is therefore often the largest number on the diff for MR/RR cars. *— Structural, and the single most important line in this document for this driver. ⚠️ The range may now floor at 0.*
8. ✅ **Suspension, gearing and brake balance are all FREE in PP.** Chassis tuning has no PP cost whatsoever. *— Structural. And it is where the advantage lives while everyone else's published tunes are stale.*
9. ⚠️ **Body rigidity can lower PP**, and **wide body always lowers PP** despite improving the car. *— Both depend on how the PP sim reads roll and aero. Re-test.*
10. ⚠️ **Front toe behaviour is genuinely disputed** and may be inverted relative to reality. Test it per-car; never assume. *— Downstream of the reworked geometry. The dispute has been re-rolled — and may finally be resolvable.*
11. ⚠️ **Post-1.49 bottoming and arch contact can physically prevent steering.** A car that suddenly won't turn is a ride-height problem, not a balance problem. Always rule this out first. *— [UNKNOWN] on 1.71. Keep ruling it out; the step is cheap and the failure mode is severe.*
12. ✅ **No tyre pressure, no caster, no brake pressure.** Camber, toe, ARB and springs must do all the work those would normally do — which is why GT7 setups look strange to engineers from other platforms. *— Structural, permanent, and the reason quirks 1 and 10 matter as much as they do.*

> **⭐ The pattern in that annotation is worth reading on its own.** **The quirks that survive are the ones grounded in what GT7 *doesn't have* (2, 3, 7, 12) or in ordinary physics (6).** **The ones in play are the ones grounded in how a particular version of GT7 *behaved* (1, 5, 9, 10, 11).**
>
> **That is a general lesson about which claims to invest in** — and it matches what `07` found independently: the durable tiers turned out to be layout, mass distribution and polar moment, while the measured results were the ones the patch demoted. **Structural knowledge outlives measurements. Measure anyway — but know which kind of claim you are making.**

---

## SOURCES

**1.71 (the current baseline)**
- [Update Notice (1.71) — gran-turismo.com](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html)
- [GTPlanet — Update 1.71 Arrives With Major Physics Changes](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Traxion — 1.71 brings sweeping physics changes, resets leaderboards](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [MP1ST — 1.71/1.710 patch notes](https://mp1st.com/title-updates-and-patches/gran-turismo-7-august-update-races-out-via-patch-1-71-1-710)
- [GTPlanet — Undocumented Changes Thread (1.71)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-1-71.439041/)

**Official / first-party**
- [GT7 Update 1.49 — official announcement (gran-turismo.com)](https://www.gran-turismo.com/us/news/00_5537934.html)
- [GT7 Update 1.49 — PlayStation Blog](https://blog.playstation.com/2024/07/24/gran-turismo-7-update-1-49-brings-six-new-cars-updated-physics-simulation-model-and-more-on-july-24/)
- [GT7 Spec III Update — official (gran-turismo.com)](https://www.gran-turismo.com/us/news/00_4185758.html)
- [GT7 Spec III & Power Pack DLC — PlayStation Blog](https://blog.playstation.com/2025/12/03/gran-turismo-7-spec-iii-power-pack-dlc-available-december-4/)
- [Update Notice 1.70 — gran-turismo.com](https://www.gran-turismo.com/us/gt7/news/00_1814793.html)
- [Update Details 1.66 — gran-turismo.com](https://www.gran-turismo.com/us/gt7/news/00_3200508.html)
- [Beyond the Apex — Anti-Roll Bars (gran-turismo.com)](https://www.gran-turismo.com/hk/gt7/apex/settings/03)
- [Beyond the Apex — Camber Angle / Suspension Geometry](https://www.gran-turismo.com/us/gt7/apex/settings/06)
- [Beyond the Apex — Limited-Slip Differential](https://www.gran-turismo.com/sg/gt7/apex/settings/07)
- [GT7 Online Manual — Tuning Shop](https://www.gran-turismo.com/gb/gt7/manual/tuningshop/01)
- [GT7 Online Manual — Race settings](https://www.gran-turismo.com/au/gt7/manual/race/04)

**GTPlanet — patch coverage and forums**
- [GT7 Update 1.49 Now Available — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-149-available-20240725/)
- [GT7 Update 1.49 Preview — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-149-preview-20240724/)
- [GT7 Update 1.55 — Physics Changes — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-1-55-is-now-available-physics-changes-four-new-cars-and-more/)
- [GT7 Spec III Update 1.65 & Power Pack DLC — GTPlanet](https://www.gtplanet.net/gran-turismo-7-spec-iii-available-now-20251204/)
- [GT7 Update 1.62 — GTPlanet](https://www.gtplanet.net/gt7-update-162-20250828/)
- [Post Update 1.49 Suspension Compression Issues — Possible Glitch?](https://www.gtplanet.net/forum/threads/post-update-1-49-suspension-compression-issues-possible-glitch.428734/page-2)
- [Natural frequency in 1.49](https://www.gtplanet.net/forum/threads/natural-frequency-in-1-49.427861/)
- [GT Pro Tune — The GT7 Tuning Calculator (main thread)](https://www.gtplanet.net/forum/threads/gt-pro-tune-the-gt7-tuning-calculator-tune-every-car-in-gran-turismo-with-this-app.417540/)
- [GT Pro Tune — damper range discussion (page 23)](https://www.gtplanet.net/forum/threads/gt-pro-tune-the-gt7-tuning-calculator-tune-every-car-in-gran-turismo-with-this-app.417540/page-23)
- [Suspension tuning — Lever ratio](https://www.gtplanet.net/forum/threads/suspension-tuning-lever-ratio.412121/)
- [Complete GT7 Tuning Cheat Sheet — with expert corrections](https://www.gtplanet.net/forum/threads/complete-gt7-tuning-cheat-sheet-cross-referenced-guide-with-starting-values-for-every-setting.436897/)
- [Negative camber — negative experience](https://www.gtplanet.net/forum/threads/negative-camber-negative-experience.411540/)
- [Best toe settings (praiano63)](https://www.gtplanet.net/forum/threads/best-toe-settings.390580/)
- [I've solved what is the 'oversteery' mess that is GT7](https://www.gtplanet.net/forum/threads/ive-solved-what-is-the-oversteery-mess-that-is-gt7.407968/)
- [I need advice on LSD tuning for AWD vehicles](https://www.gtplanet.net/forum/threads/i-need-advice-on-lsd-tuning-for-awd-vehicles.415620/)
- [GT7: how to fix RWD oversteer / spinning](https://www.gtplanet.net/forum/threads/gt7-how-to-fix-rwd-oversteer-spinning-the-easy-plug-play-way.423485/)
- [Why does increasing body rigidity lower the PP?](https://www.gtplanet.net/forum/threads/why-does-increasing-body-rigidity-lower-the-pp.424639/)
- [Weight and weight distribution](https://www.gtplanet.net/forum/threads/weight-and-weight-distribution.428334/)
- [Reducing tyre wear with suspension tuning](https://www.gtplanet.net/forum/threads/reducing-tyre-wear-with-suspension-tuning.408750/)
- [In a nutshell — how does brake balance benefit you](https://www.gtplanet.net/forum/threads/in-a-nutshell-how-does-brake-balance-benefit-you.377825/)
- [Brake balance — a newbie question](https://www.gtplanet.net/forum/threads/break-balance-a-newbie-question.397590/)
- [Traction control](https://www.gtplanet.net/forum/threads/traction-control.405890/)
- [How to tune gears](https://www.gtplanet.net/forum/threads/how-to-tune-gears.348306/)
- [Setting up transmission](https://www.gtplanet.net/forum/threads/setting-up-transmission.423419/)
- [AdrenaTune — Max Gr.3 Tunes](https://www.gtplanet.net/forum/threads/adrenatune-max-gr3-tunes.406118/)
- [The ridiculous downforce values for road cars](https://www.gtplanet.net/forum/threads/the-ridiculous-downforce-values-for-road-cars.395864/)
- [GT7 Max Tuning, Downforce and Special Parts Database](https://www.gtplanet.net/forum/threads/gran-turismo-7-max-tuning-downforce-and-special-parts-database.433059/)
- [GT7 Undocumented Changes Thread (1.49/1.50)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-update-1-49-1-50.427767/)
- [GT7 Undocumented Changes Thread (1.60)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-update-1-60.432709/)
- [Praiano's Tunes: Settings for GT7](https://www.gtplanet.net/forum/threads/praianos-tunes-settings-for-gt7.404868/page-2)
- [CTRL Garage — Tunes](https://www.gtplanet.net/forum/threads/ctrl-garage-tunes.416425/)

**Technical analysis**
- [GT7 Aerodynamics — Occam's Racer (measured downforce analysis)](https://occamsracers.com/2024/04/19/gt7-aerodynamics/)

**Dedicated tuning guides**
- [Doughtinator — Ultimate GT7 Tuning Guide (index)](https://doughtinator.com/en-us/blogs/guides/tuning)
- [Doughtinator — Settings Sheet Overview](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/settings-sheet-overview)
- [Doughtinator — Suspension](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/suspension)
- [Doughtinator — Differential and LSD](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/differential-and-lsd-settings)
- [Doughtinator — Aerodynamics](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/aerodynamics)
- [Doughtinator — ECU, Power and Ballast](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/ecu-and-performance-adjustment)
- [Doughtinator — Transmission](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/transmission)
- [Doughtinator — Brake Balance](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/brake-balance)
- [DG-Edge — Understanding Natural Frequency in GT7](https://www.dg-edge.com/articles/guides-tuning/understanding-natural-frequency-in-gran-turismo-7/407)
- [DG-Edge — Understanding Damper Ratios in GT7](https://www.dg-edge.com/articles/guides-tuning/understanding-damper-ratios-in-gran-turismo-7/405)
- [DG-Edge — Understanding LSD in GT7](https://www.dg-edge.com/articles/guides-tuning/understanding-limited-slip-differential-lsd-in-gran-turismo-7/408)
- [DG-Edge — Mastering Brake Balance in GT7](https://www.dg-edge.com/articles/guides-equipment/mastering-brake-balance-in-gran-turismo-7/360)
- [Sim Doctor — Tuning Guide: Damping](https://www.sim.doctor/sim-doctor-tuning-guide-damping)
- [Coach Dave Academy — GT7 Tuning Explained (2026)](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)
- [Coach Dave Academy — Delta for GT7 (AI coaching & data logger)](https://coachdaveacademy.com/gran-turismo-7/)
- [Flux89 — Complete GT7 Tuning Cheat Sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet)
- [SimRacingSetup — How to Tune in GT7](https://simracingsetup.com/gran-turismo/how-to-tune-in-gran-turismo-7/)
- [SimRacingSetup — GT7 Tuning Shop Guide](https://simracingsetup.com/gran-turismo/how-to-upgrade-your-car-in-gran-turismo-7/)
- [DiamondLobby — GT7 Tuning Guide (drag/drift numeric examples)](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/)
- [RacingGames.gg — GT7 Ultimate Tuning Guide](https://racinggames.gg/article/gran-turismo-7-the-ultimate-tuning-guide-suspension-transmission-differential-nitrous-ballast-ecu-aerodynamics)
- [RacingGames.gg — How to adjust fuel map in GT7](https://racinggames.gg/gran-turismo/how-to-adjust-fuel-map-gran-turismo-7/)
- [RacingGames.gg — GT7 Update 1.49 Patch Notes](https://racinggames.gg/article/gran-turismo-7-update-1-49-patch-notes)
- [Red Bull — GT7 Tuning and Setup Guide](https://www.redbull.com/gb-en/gran-turismo-7-tuning-setup-tips-guide)
- [GT Pro Tune / GT Tuning Assistant (calculator defaults)](https://gt-tuning-assistant.vercel.app/)
- [OverTake.gg — GT7 1.49 Handling Update](https://www.overtake.gg/news/huge-gran-turismo-7-handling-1-49-update-out-now.2289/)
- [Autoevolution — How GT7's 1.49 improves the physics model](https://www.autoevolution.com/news/how-gran-turismo-7-s-update-149-improves-the-car-physics-simulation-model-237495.html)
- [Gran Turismo Wiki — GT7 Updates list](https://gran-turismo.fandom.com/wiki/Gran_Turismo_7/Updates)
- [Gran Turismo Wiki — Performance Points](https://gran-turismo.fandom.com/wiki/Performance_Points)
- [Traxion — GT7 1.69 update](https://traxion.gg/gran-turismo-7s-next-three-cars-confirmed/)
- [Aero League Racing — Getting started with telemetry in GT7](https://www.aeroleagueracing.com/2023/10/12/how-to-set-up-software-to-read-car-telemetry-in-gran-turismo-7/)

**Sources examined and deliberately down-weighted** (contain GT7-nonexistent settings such as tyre pressure, caster, or brake pressure — flagged for the knowledge base as unreliable): shiftpointguide.com, cloakdaggerdc.com, coludi.com, carscounsel.com.
