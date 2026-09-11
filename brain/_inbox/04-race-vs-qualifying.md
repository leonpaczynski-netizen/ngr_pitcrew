# RACE SETUP vs QUALIFYING SETUP IN GRAN TURISMO 7

**Professional sim-racing engineering reference — GT7 (PS5), post-1.49 physics era**
*Compiled August 2026. Applies to GT7 v1.49 (Jul 2024) through the current 2026 builds. Primary focus: Gr.3 under BoP, but the principles generalise to Gr.4, Gr.2, Gr.1 and PP-limited road-car classes.*
***⚠️ 21 Aug 2026 — 1.71 banner added below. The body is a v1.70 record.***

---

# 🟠 1.71 EXPOSURE BANNER

**GT7 v1.71 (20 August 2026) is a physics update.** Full detail: `16-update-1.71-physics-change.md`.

**The good news, and it is real: this document survives 1.71 better than any other reference in the knowledge base.** Most of what is here is *engineering reasoning* — why a race setup differs from a qualifying setup, how to think about the mid-stint principle, how traffic changes the objective function. **Reasoning does not patch.** What patches is the numbers the reasoning gets applied to.

## What survives, what does not

| Section | Status | Note |
|---|---|---|
| **§0 ground rules** | **Intact** | Which contexts allow setup changes is a game-mode fact. |
| **§1 core philosophy** | **Intact** | Two objective functions, the six concrete statements, the compromise curve and its asymmetry. This is the most durable material in the knowledge base. **§1.2(a)'s claim that GT7's grip-to-slip transition is "unusually abrupt" and "binary" is the one line to re-verify** — 1.71 explicitly reworked the slipping regime, and if the transition became more progressive, the "sit further from the edge than in ACC or iRacing" advice softens. |
| **§2 parameter deltas** | **⚠️ Magnitudes suspect throughout** | Every "−2 to −5 clicks" style number was calibrated on 1.49-lineage physics. The **directions** are reasoning-led and should hold; the **magnitudes** are not measured on this version. |
| **§2.1 aero** | **Suspect** | Aero defaults *and adjustment ranges* were revised on race cars. The percent-of-range track baselines are unsafe until `11` is re-read. *(Re-read: all four cars on v1.71, 11 Sep 2026 - the gate is met.)* |
| **§2.2 springs and ARBs** | **Mostly intact** | The 3–5 Hz race / 1.1–1.5 Hz road figures are PD's own manual. **The range floors and ceilings behind them may have moved** — check `11`. |
| **§2.3 ride height and the fuel platform** | **⚠️ In play** | 1.71 changed damper attenuation and revised suspension defaults and ranges. The bottoming behaviour this section is built around is the most likely thing in it to have changed. |
| **§2.4 damping** | **⚠️ Most exposed section here** | *"Damper attenuation characteristics have been changed to make stance changes and road surface tracking feel more natural."* Both of those are what damping does. The deltas here need re-deriving. |
| **§2.5 LSD** | **⚠️ Range may have moved** | Written against a 5–60 scale. One community report says the floor is now 0 — `16` §5. If true, the "maximise rotation" quali philosophy has new territory below it. |
| **§2.6 gearing** | **Suspect via rolling resistance** | The slipstream and heavier-car arguments are sound. The specific "+5 to +15 km/h" allowance depends on terminal speeds, and rolling resistance was optimised. |
| **§2.7 camber and toe** | **⚠️ Highest-priority re-test** | 1.71: *"The steering geometry for each car has been optimised."* That is the model producing GT7's anomalous camber behaviour. See `03` §8.3 and `16` §12 Job 5. |
| **§2.8 brake balance** | **⚠️ Re-test the feel** | The sign convention and the stint-management pattern are intact. But 1.71 adjusted *"slip ratio control and cornering brake behaviour under ABS"* — which names the trail-braking phase directly. |
| **§3 fuel load** | **Mostly intact** | 100 L universal tank, cannot underfuel, the mid-stint principle — all unaffected. **§3.2's 4%/8% fuel-map arithmetic is exposed to the new engine torque control map.** |
| **§3.3 the mid-stint principle** | **Intact** | The quadratic argument is mathematics. The deviation triggers are judgement. Both survive. |
| **§4 tyre degradation** | **⚠️ Void as fact** | §4.1's list is *what 1.49 did*. 1.71 re-does the slipping simulation on top of it. §4.2's front-vs-rear conclusions are re-opened. **§4.2's own instruction — "Never assume. Measure." — is the section's surviving content.** |
| **§5 the λ decision rule** | **Intact** | A heuristic for weighting, not a physics claim. The multiplier bands feeding it depend on `03`, which is void. |
| **§6 one-lap technique** | **⚠️ §6.1 tyre temperature is directly contradicted** | See below. The rest of §6 is intact. **§6.3's downshift-protection note needs updating: 1.71 relaxed it.** |
| **§7 traffic and racecraft** | **Intact, and more valuable** | Slipstream economy, braking stability, defensive drivability. **The new "Championship" damage setting raises the value of everything here** — see `16` §9. |
| **§8 validation protocol** | **⭐ The most useful section in the document right now** | Six tests, all of which need running again. Tests 2 and 5 are now `16` §12 Jobs 2 and 6. |
| **§9 confidence and caveats** | **Needs 1.71 added to the version-risk list** | Done inline below. |

## The one direct contradiction

**§6.1 states that tyre temperature is "functionally invisible in practice"** and that "there is no meaningful warm-up phase in GT7."

**1.71's notes say: "Tyre heating and wear values have been adjusted."**

That is not proof the claim is now wrong — PD can adjust a parameter that remains practically inert. But it is a direct signal that heat is a live, tuned part of the model, and it puts this document in open disagreement with `03` §3, which calls temperature "real but rudimentary" with measurable cold-tyre effects and a 2–3 corner warm-up.

**These two documents have always disagreed. 1.71 makes it worth settling.** §8's Test 5 — cold start, immediate flying lap, versus a flying lap after three warm-up laps — resolves it in ten minutes, and `16` §12 Job 6 extends it with telemetry. **Until then, treat §6.1's "no warm-up phase" as [CONTESTED], not as established.**

## What to do with this document in the meantime

**Use it for direction, not for magnitude.** "Race trim wants softer damping than quali trim" is safe. "Race trim wants 3 clicks less compression" is a v1.70 number.

**And the section that matters most this fortnight is §8.** Every validation test in it was written for exactly this situation.

---

## 0. GROUND RULES: WHAT YOU CAN ACTUALLY CHANGE, AND WHERE

Before any of the theory matters, you have to know which GT7 context you are in, because GT7 is unusual among sims in that **the setup sheet is frequently locked**. This is the single most important practical filter on everything below.

| Context | Setup freedom | Qualifying mechanism | Fuel/wear |
|---|---|---|---|
| **Sport Mode Daily Race** | Usually "Settings Adjustment: Partially Allowed". In 2025–26 this is most often **brake balance only**; some weeks extend to **brake balance + downforce**, or **brake balance + differential + suspension**. Occasional "free rein" weeks exist. | Separate open hot-lap session, unlimited attempts, run any time before the race | Set per race by multiplier (0x, 1x, 2x, 3x, 5x, 6x…) |
| **Sport Mode Time Trial / Lap Time Challenge** | Varies by event; some allow tuning, most are fixed-spec. BoP became toggleable in Time Trials in **v1.68 (Mar 2026)** | The event *is* the qualifying lap | Fuel and wear off |
| **GT World Series (Manufacturers / Nations)** | Varies by round; several rounds permit setup work under BoP | Formal qualifying session or aggregate TT | Long races with wear + fuel |
| **Custom Race / Private Lobby / Endurance** | **Full setup freedom** | Whatever you configure | Whatever you configure |

**Consequence:** in the majority of Daily Races the quali-vs-race distinction collapses into three levers — brake balance, TCS, and fuel map — plus *driving*. The full parameter-by-parameter discussion below is aimed at lobbies, custom endurance races, GTWS rounds, and the "settings allowed" Daily weeks. Do not skip Section 7; in locked-setup racing, racecraft *is* your setup.

**A second GT7 quirk that shapes everything:** in Sport Mode the qualifying lap is a **standalone time-trial session with fuel consumption and tyre wear disabled**, run at a different point in time from the race, on a fresh-tyre, low-load car. You are therefore not making the F1 parc-fermé compromise of one setup serving both sessions — *if the week allows tuning, you can legitimately run a genuine quali trim for the hot lap and a genuine race trim for the race.* Most drivers never exploit this. It is free lap time on the grid.

---

## 1. THE CORE PHILOSOPHY

### 1.1 Two different objective functions

A **qualifying setup** maximises a single scalar: the minimum achievable time for one lap, given a car with new tyres, minimum fuel, clean air, and a driver who has already accepted that the car may be unusable on lap two. The optimisation is *unconstrained by survivability*. There is no penalty term for tyre energy, no penalty term for driver workload, no penalty term for recoverability after a mistake, and no requirement that the balance still be correct in twenty laps' time.

A **race setup** maximises something entirely different: the *integral* of speed over a stint, subject to constraints. Formally, you are minimising

> Σ(lap times) + (pit time) + (time lost to errors) + (time lost in traffic) − (time gained overtaking)

…across a car whose mass falls by ~75 kg from lights-out to the flag, whose tyres lose grip monotonically and asymmetrically, and which will spend a meaningful fraction of the race in another car's wake with reduced downforce and elevated tyre energy.

### 1.2 What that means concretely, in parameters

The abstraction resolves into six concrete engineering statements:

**(a) Quali trades stability for response; race trades response for stability.** A quali car can be set with a rear that is deliberately underdamped and under-supported on entry, because a driver who knows exactly where the car will step out can carry that rotation for one lap. Over a stint, the same rear costs more in correction-induced tyre energy and in the occasional off than it ever returns in cornering speed. In GT7 specifically, this matters more than in most sims because the **grip-to-slip transition is unusually abrupt** — GT7 gives you very little progressive warning, and once the rear is gone the only recovery is near-total throttle release. A car that is on the edge in GT7 is not "lively", it is binary. Race trim should sit further from that edge than you would set in, say, ACC or iRacing.

> **⚠️ 21 Aug 2026 — this is the single claim in §1 that 1.71 puts in question.** The update *"focuses on the simulation when tyres are slipping"* and PD describe it as producing "different car behaviour on the limit." If the transition became more progressive, the advice to sit further back from the edge softens, and race trim can be more aggressive than this document assumes. **If it became sharper, the advice hardens.** Either way it is a felt, driver-reportable change and should be the first thing noted on the first 1.71 outing — Rule 7, the driver report is primary evidence.

**(b) Quali optimises for the car's condition at one instant; race optimises for the car's condition at the mid-point of the stint.** The quali car is set up for 100% tyre, ~0 kg fuel. The race car should be set up for ~50% tyre life, ~50% fuel — which means it is deliberately *wrong* at both ends of the stint, symmetrically, rather than right at one end and catastrophic at the other. (Section 3.3.)

**(c) Quali is a corner-speed optimisation; race is often a corner-exit-and-straight-line optimisation.** Downforce that is free in clean air is not free behind a car, and cornering speed you cannot deploy because you are stuck behind someone is worth zero. Race trim is systematically lower-drag than the pure single-lap optimum whenever overtaking is required. (Sections 2.1 and 7.)

**(d) Quali accepts tyre energy; race spends tyre energy as a budget.** This is quantifiable in real engineering. Michelin's Canopy work shows that deliberately cutting rear tyre wear energy from 1.9 MJ to 1.5 MJ (a ~21% reduction) costs ~1.3 s/lap if you simply drive slower — but that **setup changes to brake balance, mechanical balance and aero balance can claw back a meaningful fraction of it**, recovering up to ~0.13 s/lap for a 10% wear reduction when all three are optimised together. That is the entire justification for a distinct race setup: you are buying tyre life at a better exchange rate than the driver can buy it with his right foot.

**(e) Quali assumes zero errors; race prices in error probability.** If a knife-edge setup is 0.15 s/lap faster but produces one half-spin per stint (≈3 s) and two extra corrections per lap (≈0.05 s each plus tyre energy), it is net negative over anything longer than about eight laps. **⚠️ 1.71's new "Championship" damage setting, if the league adopts it, raises the cost of an error again — see `16` §9.**

**(f) Quali is a one-shot; race is a control problem.** The race car must remain *adjustable from the cockpit*. GT7 lets you change brake balance, traction control and fuel map on the fly via the MFD. A good race setup deliberately leaves headroom in those three so that the driver has authority to re-balance the car as fuel burns and tyres go off. A quali setup can and should burn all its adjustment range on the one lap.

### 1.3 The compromise curve

Plot lap time vs. "aggression" (rearward balance, stiffness, low-drag, low-compliance). Quali sits at the minimum of the *single-lap* curve. The *stint-average* curve has its minimum at a distinctly less aggressive point, and — critically — the stint curve is **steeper on the aggressive side**. Being 10% too conservative in race trim costs you a few hundredths a lap. Being 10% too aggressive costs you a tenth a lap *plus* degradation *plus* incident risk. **When in doubt in race trim, err conservative.** This asymmetry is the single most useful heuristic in this document.

> **⭐ And it is the right posture for the whole 1.71 transition.** With every baseline unverified, the asymmetry argument says the same thing at the programme level that it says at the setup level: **the cost of being too conservative on the first post-patch outings is small and the cost of being too aggressive is not.** Re-baseline from the safe side.

---

## 2. PARAMETER-BY-PARAMETER DELTAS

> **⚠️ Directions reasoning-led and expected to hold. Magnitudes are v1.70 and unverified — see the banner.**

### 2.0 Summary table

| Parameter | Quali direction | Race direction | Typical delta (GT7 sliders) | Confidence |
|---|---|---|---|---|
| Total downforce | At or near single-lap optimum | Optimum minus a step, if overtaking required | −1 to −3 clicks total; up to −15% of range at high-speed circuits | High |
| Aero balance | Slightly rear-light (sharper) | Slightly rear-biased (stable) | Shift 1 click of front off / 1 click of rear on | High |
| Natural frequency (springs) | Toward the stiff end of the working window | 5–15% softer, front-biased softening | e.g. Racing tyres 4.2/4.4 Hz → 3.9/4.2 Hz | Medium |
| ARB | Stiffer, more rear-biased | Softer overall; rear 1 click softer relative to front | −1 front, −1 to −2 rear on the 1–10 scale | Medium |
| Ride height | At the aggressive minimum | +2 to +5 mm both ends, rear-biased raise | Preserve or slightly increase rake | Medium |
| Damping | Higher, tighter control | Lower compression especially; more compliance | −2 to −5 on compression, −2 to −3 on expansion (of the 20–40 / 30–50 scales) | Medium **⚠️ 1.71 damper rework** |
| LSD initial torque | Low (5–10) | Low-to-moderate (5–15) | +0 to +5 | Medium **⚠️ v1.70 scale; the floor is 0 on v1.71 (`range_records`)** |
| LSD accel | Moderate–high for exit drive | Slightly lower for tyre preservation | −5 to −10 | Medium |
| LSD braking | Low for rotation | Higher for entry stability | +5 to +15 | Medium |
| Gearing | Optimised for the fastest single lap in clean air | Longer top end for slipstream/defence; adjusted for heavier car | Final drive/top speed +5 to +15 km/h of theoretical | High **⚠️ rolling resistance changed** |
| Camber | Marginally more negative | Marginally less negative | −0.2° to −0.5° change | Medium **⚠️ steering geometry reworked** |
| Toe | Front more toe-out, rear less toe-in | Front toward neutral, rear more toe-in | 0.03°–0.10° per end | Medium |
| Brake balance | At the rearward edge of usable | 1–2 clicks forward at race start, walked rearward through the stint | −5..+5 scale; typically +1 to +2 relative to quali, then back | High **⚠️ ABS cornering behaviour adjusted** |
| Ballast | Not used (adds mass) | Only as a PP/BoP tool, never as a race-trim tool | n/a | High |

---

### 2.1 Aero: downforce level and balance

**How GT7 models it.** GT7 exposes front and rear downforce as separate sliders, in arbitrary per-car units, with car-specific ranges. Two GT7-specific facts dominate the tuning:

1. **The rear wing generates substantially more force per click than the front splitter.** Front and rear ranges are not commensurate. Moving rear downforce one click is a much larger aero-balance event than moving front one click. Always make front-end aero adjustments the fine tool and rear the coarse tool.
2. **Downforce is a first-order performance lever in GT7 — usually the first thing worth touching.** Cornering performance responds strongly.

> **⚠️ 21 Aug: 1.71 revised initial aerodynamics settings *and adjustment ranges* on race cars, plus initial settings on certain road cars.** Both statements above are structural and should survive. **The percent-of-range track baselines below are not usable until `11-car-slider-ranges.md` is re-read** — a moved span changes what every percentage means.

**Track-level baselines (community-standard starting points, expressed as % of each car's slider range):**

| Circuit archetype | Front | Rear | Examples |
|---|---|---|---|
| Low-speed / high-downforce | 70–80% | 90–100% | Tsukuba, Laguna Seca, Autopolis, Dragon Trail Gardens |
| Mid-speed | 40–60% | 55–75% | Suzuka, Fuji, Brands Hatch, Watkins Glen, Goodwood |
| High-speed / low-drag | 10–30% | 20–40% | Monza, Spa, Le Mans, Sardegna Road A, Special Stage Route X |

**The lap-time trade.** The correct mental model is the *isochronal* one: an aero step that adds cornering speed and an aero step that adds straight-line speed can produce identical lap times by different routes. The classical statement is Michelin's: "adding downforce makes your car stick to the track better, allowing faster cornering. However, with downforce comes drag that slows the car on the straights."

Practically, for a Gr.3 car in GT7:

- **On a downforce-limited circuit** (Tsukuba, Autopolis, Dragon Trail Gardens, Deep Forest), removing a click of rear downforce costs roughly 0.1–0.25 s/lap in the corners and returns almost nothing on the straights. Run maximum. There is no quali-vs-race aero decision worth making — run max in both.
- **On a balanced circuit** (Suzuka, Fuji, Brands Hatch), the curve is flat near the optimum. A click either side is worth ~0.03–0.08 s. This is where the *race* consideration overrides the *lap-time* consideration: take the lower-drag side of a flat optimum, because straight-line speed is worth more in a race than in a hot lap.
- **On a drag-limited circuit** (Monza, Le Mans, Sardegna Road A, Route X), each click of rear wing can cost 3–8 km/h of terminal speed and 0.1–0.3 s on a long straight while returning less in the corners. Quali may still want the higher setting if the circuit has a decisive high-speed corner (Monza's Parabolica, Spa's Blanchimont); **race trim should almost always take less wing than the single-lap optimum.**

**The overtaking correction — the crucial race-specific term.** Downforce that is optimal in clean air is *not* optimal at 1.0 s behind another car. Two effects compound:

- Your effective downforce is reduced in the wake, so a car set up right on the aero-limited edge understeers or goes light exactly where you need it (fast corners, entry to the braking zone for the overtake).
- The car ahead has the same drag reduction from your presence that you have from theirs — GT7's slipstream is a real, sizeable effect on top speed — but a *lower-drag* car converts a tow into a bigger closing speed than a high-drag car does.

**Rule:** in a race where you expect to start out of position and must pass, take **one to three clicks less total downforce than the single-lap optimum**, taken predominantly off the rear, and re-balance the front down by roughly half as many clicks to hold aero balance. Verify by checking that your terminal speed at the end of the longest straight increases by at least 3–4 km/h; below that the trade is not worth the corner-speed loss.

**Aero balance, quali vs race.** Quali wants the aero balance at the sharp end — as far forward as the driver can hold in fast corners — because turn-in response in high-speed corners is where single-lap time hides. Race wants it a step rearward: a rear-biased aero platform gives high-speed stability that (i) survives dirty air, (ii) reduces rear slip angle and therefore rear tyre energy, and (iii) reduces the correction workload that dominates late-stint lap-time variance. **Delta: one click of front downforce off and/or one click of rear on, relative to quali.**

---

### 2.2 Spring rates (natural frequency) and anti-roll bars

**GT7 units.** GT7 expresses springs as **natural frequency in Hz**, not spring rate in N/mm. Per Polyphony's own manual: road cars on comfort/sports tyres generally sit at **1.1–1.5 Hz**, race cars on racing tyres at **3–5 Hz**. Community values: ~1.2 Hz comfort, ~1.8 Hz sports, ~4.0 Hz racing. GT7's sliders also build in a natural rear offset — the rear range starts and ends higher than the front — so "the same slider position front and rear" already gives you a stiffer rear.

Because GT7 works in frequency rather than rate, **it has already normalised for sprung mass at the reference condition**. This is subtle but important: it means that when you add 75 kg of fuel, the *actual* natural frequency of the car drops below the number on the sheet, more at the axle nearer the tank. You are not driving the frequency you dialled in; you are driving a lower one on lap 1 and converging on the dialled figure as fuel burns.

**Quali direction.** Stiffer, toward the top of the working window. Stiff springs give:
- Faster load transfer and therefore sharper response — free time in direction changes (Suzuka esses, Maggots/Becketts-type sequences).
- A more stable aero platform: less pitch under braking and acceleration, less ride-height variation, more consistent downforce, which is worth real time on high-speed circuits.
- Less roll, allowing lower static camber to work (see 2.7).

The cost — poor bump compliance, reduced mechanical grip over kerbs and bumps, higher tyre load fluctuation and therefore higher wear energy — is a *stint* cost, not a *lap* cost. Quali doesn't pay it.

**Race direction.** Soften by roughly **5–15%**, weighted toward the front. Reasons:
1. **Fuel compliance.** With a full tank the car is heavier and sits lower; a stiff-sprung car set at minimum ride height will bottom out on lap 1 and the resulting understeer is severe. Softer springs plus a small ride-height raise (2.3) is the standard mitigation.
2. **Tyre preservation.** Stiffer springs and ARBs reduce tyre compliance and increase peak contact-patch load fluctuation, which increases wear. This is the mainstream community view (explicitly hedged as untested by some, but consistent with real-world tyre-energy modelling).
3. **Bump and kerb tolerance.** Race lines are not qualifying lines. Under pressure you will use more kerb, take defensive lines, and run off-line over marbles and dust. A compliant car is faster in those conditions and, more importantly, does not spit you off.
4. **Post-1.49 GT7 rewards it.** The 1.49 physics rework made the car feel heavier, made the grip-to-slip transition sharper, and made *sliding and direction changes* — not braking and acceleration — the dominant tyre-wear mechanisms. Anything that reduces transient sliding (compliance, softer platform, gentler damping) is now directly a tyre-life lever. **⚠️ 1.71 reworked the slipping regime. Reason 4 is the one to re-verify; reasons 1–3 are mechanical and hold.**

**ARBs.** GT7 uses a 1–10 scale. Common drivetrain baselines: FR front 6 / rear 4; FF front 4 / rear 6. Race-trim delta from quali: **soften both by roughly one click, and soften the rear one click more than the front**, i.e. move the roll-stiffness distribution forward. A more forward roll-stiffness distribution loads the rear axle more evenly in roll, reducing peak rear-outside tyre load and rear slip angle. This is the classic real-world "run more understeer in the race to protect the rear tyres" move — precisely the mechanism described in professional practice, where qualifying setups favour more oversteer for maximum one-lap response while race setups deliberately add understeer to cut rear slip angles and degradation.

**Caveat for GT7 specifically:** GT7's ARBs are blunt instruments compared to real cars, and very stiff ARBs make the transition to slip even more abrupt than the tyre model already does. Do not use ARBs as your primary balance tool in race trim. Use aero balance and LSD; use ARBs for the last 20%.

---

### 2.3 Ride height, rake, and the fuel-loaded aero platform

> **⚠️ 1.71 exposure is high here.** Damper attenuation changed, and suspension defaults *and ranges* were revised. The bottoming behaviour this section is built around is the most likely thing in it to have moved — and `00-INDEX` records the 1.49 bottoming problem as a Settled Fact that is now explicitly back to [UNKNOWN]. See `16` §4.

**GT7 model.** Ride height is set in mm per axle with a car-specific minimum. Lower = lower CoG = less roll = more grip, up to the point where the car bottoms out or the arches rub, at which point you get a sudden and severe understeer/instability event. Rake (rear higher than front) is described by experienced GT7 tuners as producing "the most drastic effects on the way your car behaves": **positive rake sharpens rotation and turn-in precision; negative rake favours top speed and stability.**

**Standard starting point:** front 3–5 clicks above the car's minimum, rear 5–8 clicks above minimum. That automatically produces positive rake. Bumpy circuits: add 2–3 clicks both ends.

> **⚠️ This is the heuristic `11-car-slider-ranges.md` caught being wrong on the Shelby** — stated in absolute clicks, it means 20% of range on a Gr.3 car and 6% on a Gr.N road car. **Use percent of range, and only once `11` is re-read on v1.71.**

**What a full tank does to the platform.** This is the most under-appreciated race-setup effect in GT7.

- A ~75 kg fuel load on a ~1,250–1,350 kg Gr.3 car is **~5.5–6% of vehicle mass**. That mass sits in the tank, which is behind the driver and near or slightly ahead of the rear axle on most Gr.3 cars.
- That load compresses the springs. On a 4 Hz race spring the static deflection change is small in absolute terms — order 3–6 mm — but on a car set 5 mm off its minimum, 4 mm is most of your bump travel.
- The compression is **not symmetric**: it is rear-biased for most Gr.3 layouts. So a full tank **reduces your rake** — it squats the rear, flattens or negatives the platform, and shifts your aerodynamic balance rearward while simultaneously moving your *mass* balance rearward.

**The compound effect on lap 1 with full fuel:**
- Less rake → less front aero bite → **entry understeer**.
- Rear-biased mass → more longitudinal inertia → **longer braking distances and a car that wants to rotate under trail-braking once you finally get it to turn** (a nasty combination: understeer on entry, snap on release).
- Less rear ride height → higher bottoming risk over compressions and kerbs → occasional sharp instability.

**Race-trim response.** Two options, and you generally want both in moderation:

1. **Raise both ends 2–4 mm from the quali height**, biased to the rear (e.g. front +2, rear +4), so that the *fuel-loaded* platform sits at the rake you actually want, rather than the *empty* platform sitting there. You are setting the ride height for the loaded condition, not the unloaded one.
2. **Soften the front slightly and/or add front downforce** to compensate for the rake loss on lap 1, accepting that the car will get slightly nose-heavy in feel as the tank empties.

The trap to avoid: setting ride height at the qualifying minimum, then loading the car and discovering that lap 1 is 2.5 s off the pace not because of mass but because you are riding on the floor.

**Quali direction.** As low as the circuit allows without bottoming, with the rake that gives sharpest turn-in — you have a light car and one flying lap, so run it on the deck. On a very smooth circuit and a fuel-off qualifying session you can go a click or two lower than you would ever dare in race trim.

**Race direction.** +2 to +5 mm, rear-biased, and preserve or slightly increase static rake so that the loaded car still has front bite.

*Confidence note: GT7's ride-height-sensitive aero modelling is not publicly documented, and community sources do not confirm whether downforce coefficients vary continuously with instantaneous ride height. The mechanical and bottoming effects described above are unambiguous; treat the aero-map sensitivity as a working hypothesis and validate with the test in Section 8.*

---

### 2.4 Damping

> **⚠️⚠️ This is the section 1.71 hit most directly.** *"Damper attenuation characteristics have been changed to make stance changes and road surface tracking feel more natural."* **Stance changes** are pitch and roll transitions; **road surface tracking** is bump compliance. Those are the two things damping does. This is a model change, not a value tweak. **Every delta below needs re-deriving on v1.71, and the 20–40 / 30–50 windows themselves need re-reading in `11`.**

**GT7 model.** Compression (bound) and expansion (rebound) per axle, expressed as damping ratios on scales that in practice run about **20–40 for compression and 30–50 for expansion**, with a widely-taught baseline of **30 compression / 40 expansion** and the working rule that **expansion should exceed compression**. GT7 tuners who dug into 1.49 believe the damper and motion-ratio model — more than natural frequency — was the actual source of the update's handling change. **That is worth holding onto: if the damper model was where 1.49's felt change lived, it is a good bet for where 1.71's does too.**

**Why race setups run more compliance.** Four distinct reasons, all of them stint-scale:

1. **Tyre-load control over a stint.** High damping controls the platform beautifully on a smooth, ideal line. It also transmits every bump directly into contact-patch load fluctuation. Over 15–20 laps, load fluctuation is wear energy. Since 1.49 explicitly weighted wear toward sliding, and a momentarily unloaded tyre slides, damping down is a wear lever.
2. **Recoverability.** GT7's abrupt grip-to-slip transition means the car's behaviour at the limit is unforgiving. A less-damped car takes longer to transfer load, which gives the driver a marginally longer window to catch a slide. In a sim where recovery is already hard, buying transition time is worth real race pace.
3. **Kerbs and off-line surfaces.** Race trim has to survive kerbs, defensive lines, and running wide. Lower compression is the standard answer for bumpy surfaces (drop 2–3 clicks toward minimum), and every race line is a bumpy line eventually.
4. **Fuel load.** Damping ratios were dialled at a reference sprung mass. Adding 75 kg raises the mass the damper has to control, meaning the *effective* damping ratio falls. This means you can afford slightly less on the sheet at the start... but as fuel burns, effective damping rises and the car becomes progressively tighter and more nervous. If you set damping for the empty car, the full car will float. If you set damping for the full car, the empty car will skate. **Set it for the mid-stint condition** and accept a slightly floaty lap 1 and a slightly tight final lap.

**Concrete deltas from quali to race:** *(v1.70 magnitudes — re-derive)*
- **Compression: −2 to −5 clicks**, both axles, weighted to the front if the car is front-limited on wear.
- **Expansion: −2 to −3 clicks**, both axles. Do not soften expansion below the point where the car starts to pitch and wallow into braking zones, which in GT7 shows up as a vague, delayed front and a rear that goes light on release.
- **For long endurance stints, drop all four values 1–2 clicks** from the sprint-race figure. Consistency over 30–40 laps is worth more than a hundredth of peak response.

**Asymmetric damping as a race tool.** A cheap and effective race-trim move: **raise rear compression relative to front**. This resists the rear squatting under power, which reduces exit understeer *and* reduces rear wheelspin — a tyre-life win and a lap-time win simultaneously, especially on tracks with slow, long-duration exits.

---

### 2.5 LSD: rotation vs. tyre preservation

> **⚠️ 1.71: "Initial differential gear settings and adjustment ranges have been fixed."** And **[COMMUNITY — single source]** the diff may now floor at 0/0/0 rather than 5/5/5 (`16` §5). If so, the "maximise rotation" quali philosophy below has genuinely new territory beneath it — **a truly open diff on the overrun would be a bigger rotation source than anything this section describes.** Confirm the range before exploring it.

**GT7 model.** Fully-customisable LSD with three parameters — **Initial Torque, Acceleration Sensitivity, Braking Sensitivity** — each on a **5–60** scale on v1.70 - **0–30 / 0–100 / 0–100 on v1.71** (`range_records`). Low = open, high = locked. Initial Torque sets the baseline preload/locking threshold and controls how quickly the diff transitions between open and locked. Acceleration Sensitivity controls locking under power; Braking Sensitivity controls locking under lift/braking.

**Drivetrain baselines** (widely-used starting points, Initial/Accel/Braking):

| Layout | Initial | Accel | Braking |
|---|---|---|---|
| FR | 5 | 25 | 10 |
| MR | 5 | 15 | 20 |
| RR | 5 | 15 | 25 |
| FF | 10 | 35 | 8 |
| AWD (rear unit) | 5–11 | 15–25 | 5–14 |

Another common, more general baseline is **5/30/5** with the middle number adjusted for turn-in feel.

**The quali philosophy: maximise rotation.**
- **Low Initial Torque (5–10)** — a diff that unlocks readily allows snappy, immediate transitions and lets the inside rear spin up freely in slow corners, which rotates the car. Sharper turn-in, more agility, more one-lap time.
- **Low Braking Sensitivity (5–15)** — an open diff on the overrun lets the rear axle differentiate under trail-braking, which is a large rotation source in GT7. This is one of the biggest single-lap levers on Gr.3.
- **Accel Sensitivity at the point of best drive** — usually moderate-to-high (25–40 on FR, v1.70 scale), because you want maximum traction out of the last corner onto the timing straight and there is no wear penalty to worry about.

**The race philosophy: preserve the rears and reduce workload.**
- **Initial Torque up slightly (+0 to +5).** A little more preload makes the diff's behaviour more predictable and less prone to the abrupt lock/unlock transitions that upset a GT7 car at the limit. It costs a little turn-in.
- **Braking Sensitivity up meaningfully (+5 to +15).** This is the single highest-value race-trim LSD change. More braking lock ties the rear axle together on entry and dramatically reduces the entry snap that GT7's tyre model punishes so severely. It costs rotation, which you replace with brake balance and aero balance. It buys stability under trail-braking into every overtaking zone (Section 7) and it cuts rear tyre energy from repeated corrections.
- **Accel Sensitivity down slightly (−5 to −10).** A very locked-on-power diff drags the inside rear through the corner, scrubbing it, and — in GT7 — can produce a sudden dual-wheel breakaway on exit rather than a progressive one-wheel spin. Lower accel sensitivity is gentler on the rears over a stint. The exception is low-grip / high-torque situations (wet, cold, very slow hairpins, or heavily degraded rears) where **more** accel lock actually reduces net wheelspin. Test both.

> **Cross-reference:** `03` §8.5 records our own in-house result that the MR accel baseline of 15 is a **ceiling, not a midpoint, on a restricted build** — 18 produced power-on mid-corner understeer on the Huracán, 14 resolved it. **That was measured on v1.70, and 1.71 introduced a new engine torque control map, which changes the torque that finding responds to. Re-test before reusing 14.**

**Interaction with wear.** As the rears go off, a heavily-locked-on-power diff amplifies the loss: the axle now breaks traction as a unit. As the fronts go off, a heavily-locked-on-braking diff amplifies understeer on entry. If you know from testing which end degrades first, bias your LSD compromise to protect that end at the *start* and let it become correct at the end. (Section 4.)

---

### 2.6 Gearing

**GT7 model.** Full ratio control per gear plus a "Top Speed (Automatically Adjusted)" slider and a final drive. The standard practical method is the **"gearbox flip"**: set the final drive to maximum, drag the Top Speed slider fully left, then set the final drive to minimum, which unlocks the individual gear ratios for free adjustment. From there, set gears evenly spaced, note their individual top speeds, and re-target each. A typical good baseline is **a long first gear and a short top gear, with the spacing between gears decreasing slightly as you go up**.

> **⚠️ 1.71: rolling resistance was optimised.** Terminal velocity at the end of a straight is set by drag *and* rolling resistance, so **every gearing target in this section and in `05-track-reference.md` is exposed.** Also relevant: the **Huracán's gearing constant K** was already an unresolved extrapolation (1112.6 vs 1092.5), and the **Shelby's K = 1,096** was closed on v1.70. Both need re-closing on v1.71 — one lap each.

**Quali gearing.** Optimise for the single lap in clean air:
- Top gear should reach terminal velocity *at the braking point of the fastest straight*, not before. Any speed capability you don't use is wasted ratio.
- Ratio breaks placed to avoid an upshift in the middle of a critical corner exit or over a crest.
- No slipstream allowance — you are alone.

**Race gearing.** Four separate corrections, all pushing the same direction (longer):

1. **The car is heavier.** 75 kg on a Gr.3 car means measurably slower acceleration on lap 1. If you gear for the empty-car acceleration profile you will be bouncing off the limiter in the wrong places when light and struggling to pull the top gear when heavy. Gear for the mid-fuel condition.
2. **Slipstream.** GT7's slipstream is strong — strong enough that on high-speed circuits the terminal speeds seen in a race are meaningfully higher than in qualifying. If your top gear is on the limiter at your quali terminal speed, you will hit the limiter mid-tow and *lose the entire benefit of the draft at the exact moment you are trying to pass*. **Add 5–15 km/h of theoretical top speed over the quali optimum on any circuit with a long straight.** This is one of the cheapest, most-frequently-missed race-trim gains in GT7.
3. **Defence.** The same logic applies in reverse. A car being towed past you is exploiting your low top-end. Longer gearing is defensive.
4. **Traffic.** In a race you accelerate from off-line, out of slow corners, and from lower minimum speeds after being baulked. A gearbox with a usable, torquey lower-mid range is worth more than one perfectly optimised for a clean flying lap.

**Starts.**
- **Standing start.** GT7 standing starts punish wheelspin heavily, and false starts are penalised (any movement before the lights triggers a power-limiter penalty). Gearing for a standing start wants a **first gear that is long enough to not be traction-limited to the redline** but short enough to actually leave the line. The transmission-tuning practice for launch is to **increase gear spread so the penultimate gear reaches roughly the speed the first gear would have reached in a tightly-packed 'box** — this gives longer lower gears and better off-line acceleration without sacrificing top speed. Practically, if you can see the tyres lighting up through first, lengthen first. Also consider running one step of TCS for the launch only and switching it off via the MFD on the run to turn one. **⚠️ 1.71 optimised TCS intervention behaviour — re-test what a step of TCS costs before relying on this.**
- **Rolling start** (the GT7 Daily Race default for most Gr.3 races). Launch gearing is irrelevant; what matters is the ratio you are in at the moment the green flag drops and whether you have a clean, un-interrupted pull to turn one. Check which gear you are in at the start line and make sure you don't need an upshift in the first 100 m of the run. Rolling starts also mean **no tyre-warm-up concern at all** and no launch penalty risk — but they compress the field, making turn-one racecraft and braking stability the decisive factors (Section 7). **⚠️ "No tyre-warm-up concern" rests on §6.1, which 1.71 puts in question — see the banner.**

---

### 2.7 Camber and toe

> **⚠️⚠️ Highest-priority re-test in this document.** 1.71: *"The steering geometry for each car has been optimised, improving the simulation of turning forces."* Steering geometry governs how steer angle and suspension travel convert into slip angle and camber gain — **which is exactly the model producing GT7's anomalous camber behaviour.** `16` §12 Job 5 is a ten-minute A/B. Until it is run, treat everything below as [CONTESTED] rather than [TESTED].

**Camber.**

GT7 penalises excessive camber more aggressively than most sims. The mechanism is straightforward: excessive static negative camber means the tyre "never fully reaches its maximum grip," and it costs you longitudinal grip under braking and acceleration where the contact patch is running flat. Typical published ranges: **road-course front −2.0° to −3.0°, rear −1.0° to −2.0°** in one guide; **front −1.5° to −2.0°, rear −1.0° to −1.5°** for sports tyres in another. The consistent structural advice is: **more camber for softer suspension setups, less camber for stiffer ones** — because a soft car rolls more and needs the static angle to recover the dynamic one.

*Practical GT7 consensus, flagged as requiring per-car validation:* many competitive GT7 Gr.3 setups run notably less camber than a real GT3 car would, often in the **0.0° to −2.0° front** window, because GT7's braking-phase penalty for camber is significant and its cornering-phase reward is modest. Optimise for peak sustained lateral-G readings rather than for a number that looks right.

- **Quali:** you can afford **0.2°–0.5° more negative** than race trim. You are running one lap on new tyres; the extra peak lateral grip in the highest-load corners is free and the wear penalty never arrives. Some drivers also add front camber specifically for quali on circuits dominated by long, high-load corners — this mirrors real practice, where qualifying setups historically ran up to a degree more front camber.
- **Race:** back it off **0.2°–0.5°**. Reasons: (i) less camber = more even wear across the contact patch = longer tyre life; (ii) less camber = better straight-line braking stability, which is what you need to attack and defend; (iii) as the tyre wears, the effective profile changes and an aggressive static angle becomes progressively less well-matched; (iv) with a heavier car the dynamic camber gain differs from the light-car condition you tuned in.
- If you have softened springs and ARBs for the race (2.2), the car will roll more, which *recovers* some dynamic camber — so a portion of the static reduction is compensated automatically. Don't double-count.

**Toe.**

GT7 baseline: **front 0.00°, rear +0.05° to +0.08° (toe-in)**. The universal warning is that **any deviation from neutral increases tyre scrub, wear, and straight-line speed loss** — GT7 models this and it is not negligible on a long stint or a long straight.

- **Front toe-out (negative)** improves initial turn-in but reduces sustained cornering speed and adds scrub.
- **Front/rear toe-in (positive)** improves braking and acceleration stability, particularly on RWD cars.

**Quali:** a small amount of **front toe-out (0.05°–0.15°)** buys real turn-in bite on a single lap. Rear toe-in can be reduced toward neutral for more rotation, accepting a nervier car. The scrub-induced wear and the couple of km/h of top speed are irrelevant over one lap.

**Race:** move front toe back **toward 0.00°** (or a hair of toe-in on very high-speed circuits for braking stability), and **increase rear toe-in by 0.03°–0.08°**. Rationale:
- Rear toe-in is the cheapest stability-under-braking and stability-in-dirty-air setting in the game.
- Reduced toe deviation cuts scrub, saving both tyre life and straight-line speed — on a long-straight circuit, the top-speed saving alone can be worth more than the turn-in you gave up.
- With a full tank, the car's rear is heavier and more inertial; extra rear toe-in is exactly the right compensation.

**Note the range.** `11-car-slider-ranges.md` measured toe at **±1.00°**, twice what `02` §3.6 assumed. **Always issue toe in absolute degrees, never as a percentage** — and re-confirm the range on v1.71 before doing either.

---

### 2.8 Brake balance and fuel burn

> **⚠️ 1.71: "The slip ratio control and cornering brake behaviour under ABS has been adjusted."** That names the trail-braking phase directly, which is where most of this section lives. The **sign convention and the stint-management pattern are intact**; what a given click *feels* like is not.

**GT7 model.** Brake balance runs on a **−5 to +5** scale, negative = front bias, positive = rear bias. It is **adjustable live from the MFD during the race**, which makes it the primary in-race balance tool — and it is the *one setting that is essentially always adjustable even when Daily Race regulations lock everything else.* Since 1.49, brake bias adjustments have noticeably greater effects on stability than before, and the standard advice is to keep it near zero on most cars and test changes on slow laps before committing.

Drivetrain baselines: **MR: 0 to −1; FR: +2 to +3; FF: +5; AWD: slightly front-biased.** (Note that different GT7 sources use opposite sign conventions for this slider — always confirm the direction empirically on your own car before trusting a published number. **`00-INDEX` Settled Facts has this closed: negative = front, positive = rear, and the value is a delta from each car's factory bias.**)

**Quali.** Set it as far rearward as you can hold. Rear brake bias is a rotation source: it lets you trail-brake deeper and rotate the car on entry, which is where a large share of single-lap time lives in GT7. You have new tyres, a light car and one lap; the elevated lock-up risk and the rear-tyre energy cost are irrelevant.

**Race start.** Start **1–2 clicks more forward than quali**. With a full tank:
- Total mass is up ~6%, so absolute braking energy is up ~6% and stopping distances are longer.
- Longitudinal load transfer under braking is up in absolute terms, so the front axle is carrying proportionally more of the vertical load — which nominally argues for *more* front bias.
- But the extra fuel mass sits behind the CoG, adding rearward static weight, which nominally argues for more *rear* bias.

These partially cancel, and the net direction depends on the car. What does *not* cancel: **the full-fuel car has more inertia and less margin for error into every braking zone in the opening laps, when the field is packed.** Forward bias reduces the chance of a rear lock, a snap, and a first-lap incident. That risk-adjusted argument dominates the theoretical one. **⚠️ And with the new "Championship" damage setting available, a first-lap incident may cost more than it used to — `16` §9.**

**Through the stint.** As fuel burns:
1. Total mass falls by up to ~75 kg. Braking is easier; the front axle is less loaded in absolute terms.
2. The mass loss is rear-biased (the tank empties), so the static balance migrates **forward** as the race goes on. A rear-heavy car at the start becomes a more neutral or nose-heavy car at the end.
3. Simultaneously, the tyres degrade — and *which* end degrades faster determines what you need (Section 4).

**The practical management pattern for a Gr.3 stint:**

| Stint phase | Brake balance action | Why |
|---|---|---|
| Laps 1–3 (full fuel, cold pack, traffic) | Start at race baseline (quali +1 to +2 forward) | Maximum stability when the risk of a race-ending error is highest |
| Mid-stint (~50% fuel) | Walk it back 1 click rearward | Car is lighter and more balanced; you can now use the rear for rotation |
| Late stint, if front-limited wear | Continue rearward, or hold | Rotation must come from the rear because the front can no longer generate it |
| Late stint, if rear-limited wear | Move forward 1–2 clicks | Protect the fading rears; accept understeer over a spin |

This is a **live, per-lap tool.** The best GT7 race drivers touch brake balance several times per stint. Treat the sheet value as a starting point, not an answer. **This pattern is one of the most robust things in the knowledge base — it is a response to fuel burn and wear direction, both of which still exist on v1.71.**

---

## 3. FUEL LOAD EFFECTS

### 3.1 The numbers

| Quantity | Value | Source/confidence |
|---|---|---|
| GT7 fuel tank capacity | **100 L for every car in the game**, road car or race car | Confirmed, community-verified |
| Mass of a full tank | **~75 kg** (100 L × ~0.75 kg/L racing gasoline) | Derived; GT7 does not publish its density constant |
| Gr.3 BoP mass (2025–26 era) | **~1,250–1,350 kg** depending on car and BoP level. The March 2025 BoP cut ~40 hp per car on average and added weight to most | Confirmed via GTPlanet BoP reporting |
| Full tank as fraction of car mass | **~5.5–6.0%** | Derived |
| Gr.3 fuel burn at 1× | **~2–3 L/lap** on a typical 90–120 s circuit; scales linearly with the multiplier (3× → 6–9 L/lap; 5× → 10–15 L/lap) | Community-typical; verify per car/track **⚠️ rolling resistance changed in 1.71** |
| Real-world lap-time sensitivity to mass | **~0.25–0.40 s per 10 kg** in professional circuit racing | Documented |
| **Estimated GT7 Gr.3 full-vs-empty lap-time delta** | **~1.5–2.5 s/lap** on a 90–120 s circuit; more on power-limited/long-straight tracks, less on downforce-limited/short-lap tracks | **Derived, not directly measured — validate per car and track using the protocol in Section 8** |
| **Estimated gain per lap of fuel burned (1× Gr.3)** | **~0.04–0.08 s/lap** | Derived |

Fuel weight *is* modelled in Gran Turismo and has been for generations — GT4-era controlled tests already showed measurable per-lap gains from reduced fuel, scaling with straight-line content (a fifth of a second at Grand Valley, close to a full second at La Sarthe). GT7's implementation is more sophisticated, and the effect is proportionally larger in a low-mass, aero-heavy Gr.3 car than in the road cars those tests used.

**Cross-check:** 75 kg / 1,300 kg = 5.8% mass. Real-world sensitivity of ~0.25–0.40 s per 10 kg corresponds to ~1.9–3.0 s for 75 kg on a lap of the length these figures were derived on. That is consistent with the 1.5–2.5 s estimate above. Treat 2 s as your planning number for a Gr.3 car on a mid-length circuit and refine by measurement.

### 3.2 A critical GT7 constraint: you cannot underfuel

**In GT7 you must start every race with a full tank.** There is no fuel-load strategy at the start — no quali-fuel-run, no underfuelling for a lighter first stint, no fuel-for-the-first-stint-only. Your only levers are:

- **Fuel map / fuel mixture**, set before the race and adjustable live via the MFD.
- **Refuel quantity at the pit stop** — you *can* choose to take partial fuel and run lighter to the flag.
- **Driving technique** (short-shifting, lift-and-coast).

This has a direct setup consequence: **your race setup must be survivable at exactly 100 L**. You cannot escape lap 1 by starting light. And it makes the pit-stop fuel decision a genuine setup-adjacent strategic choice — taking only the fuel you need to reach the flag can be worth several tenths a lap on the second stint. **This is corroborated in-house: refuel volume is worth ~1.0 s per litre, against ~0.07 s per lap of stop-lap delay — a 14× ratio, measured at Watkins Glen. Optimise litres, not lap.**

**Fuel map data (verified test results):** each step of leaner fuel mixture **reduces power by ~4% and fuel consumption by ~8%**. Fuel map 6 gives roughly a 20% power reduction for roughly a 50% reduction in fuel consumed per distance. Separately, **short-shifting before the redline** was measured at roughly half a second of lap time for a **20% fuel saving** — an outstanding exchange rate, and often better than running a leaner map. And fuel map 3 with no coasting produces approximately the same lap time and consumption as fuel map 1 with 3 s of lift-and-coast per lap. **⚠️ 1.71 introduced a new engine torque control map. The 4%/8% arithmetic is now overdue for a re-test — `03` §10 item 6.**

*Setup implication:* if you plan to run a leaner map or short-shift, you are running with less power for most of the race. That changes your optimal gearing (shorter ratios become viable), your LSD accel sensitivity (less torque to manage), and your downforce (less power means drag hurts relatively more, arguing for less wing). **Do not set the car up on full-power hot laps and then race it on map 4.**

### 3.3 The mid-stint principle

**Statement.** Set the car up to be optimal at the *mid-point of the stint* — approximately 50% fuel and approximately 50% of the tyre life you expect to use — rather than optimal at either end.

**Justification.** Lap time as a function of "setup wrongness" is approximately quadratic near the optimum. If you set up for the start condition, you are 100% wrong at the end; if you set up for the mid-point, you are 50% wrong at both ends. Because the error is squared, 2 × (0.5)² = 0.5 is better than 1 × (1.0)² = 1.0. You lose half as much total time.

There is also a variance argument: a mid-stint setup has a smaller worst-case error, which matters because the *tails* of the setup-wrongness distribution are where you crash.

**This is mathematics and it survives 1.71 unchanged. What the patch affects is where the mid-point *is* — which depends on the stint length, which is now unmeasured.**

**How to execute it in practice.**
1. Run your baseline setup for a full representative stint, logging lap times and noting balance at laps 1, mid, and last.
2. Identify the balance at the mid-point lap. That is the balance you are optimising.
3. Adjust the sheet until the mid-stint lap feels neutral and is the fastest lap of the stint (excluding the very first flying lap, which is anomalously fast on new tyres).
4. Confirm lap 1 is *drivable* and the final lap is *not falling off a cliff*.

**When to deviate — deliberately bias toward the start:**
- **Very short races (≤5 laps)** where fuel burns less than a quarter of the tank. The mid-point *is* nearly the start. Set up for a nearly-full car.
- **Standing starts** and any format where turn one is decisive. A car that is unstable on lap 1 will not have a lap 20.
- **Races where you start out of position** and must make places early. Track position won in the opening laps compounds; pace at the end of a stint in clear air does not.
- **High fuel multipliers with short races** (e.g. 5× fuel, 12 laps) where you burn a large fraction of the tank fast — the balance migration is rapid and steep, and a car that survives the heavy opening laps is worth more.
- **Wet or cold conditions**, where lap 1 risk is elevated across the board.
- **⭐ NEW — the first outings on unfamiliar physics.** With every baseline unverified post-1.71, lap-1 drivability is worth more than late-stint optimisation, because you cannot yet predict what the late stint will do.

**When to deviate — deliberately bias toward the end:**
- **Long stints in clean air** where you expect to be alone and the decisive laps are the last ones before a stop, or the final laps of the race.
- **Races decided on the final lap** — a one-stop sprint where you know you will be in a fight at the flag.
- **Very low fuel multipliers (1×) with high tyre wear (6×)** — mass barely changes, so the mid-stint principle should be applied to *tyre* condition rather than fuel condition.
- **When you are chasing** and the strategic model says you must be fastest in the closing laps to catch the car ahead.

**The multiplier tells you which effect dominates.** GT7 daily races publish fuel and tyre multipliers separately, and they are frequently decoupled — a 2026-era Daily might run 1× fuel / 6× tyre wear, or 3× fuel / 5× tyre wear, or 2× fuel / 6× tyre. **Read them before you tune.**
- **High fuel multiplier, low tyre multiplier** → the mass/balance migration dominates. Set up for mid-fuel, manage brake balance forward-to-rearward, and prioritise a stable full-tank car.
- **Low fuel multiplier, high tyre multiplier** → degradation dominates. Set up for mid-tyre-life, prioritise tyre preservation (softer platform, lower LSD accel, less camber, less toe deviation), and be prepared to shift balance to protect whichever end goes first.
- **Both high** → the balance migrates from "heavy and rear-biased on fresh tyres" to "light and front-biased on worn tyres." These two effects can be additive or opposed depending on which axle degrades. Model them explicitly.

---

## 4. TYRE DEGRADATION OVER A STINT

> **⚠️⚠️ Void as fact on v1.71.** §4.1 is a description of *what 1.49 did*, and 1.71 re-does the slipping simulation on top of it. §4.2's front-vs-rear conclusions are re-opened, and per-car steering geometry was reworked, so the three cars may have moved differently from each other. **§4.2's own closing instruction — "Never assume. Measure." — is the surviving content of this section.** The measurement is `16` §12 Job 2.

### 4.1 How GT7 models degradation post-1.49

Update 1.49 (July 2024) fundamentally rewrote this. The verified changes:

- **Tyres experience a significant drop in performance after the 50% wear mark**, with degradation severe enough that **lap times increase by a second or more per lap** in the late phase.
- **The dominant wear mechanism changed.** Sliding and directional changes now cause more degradation than braking and acceleration. This is the single most important fact for setup: **anything that reduces lateral sliding is now a first-order tyre-life lever, and anything that reduces longitudinal load is second-order.**
- **Aggressive driving produces markedly higher degradation than smooth inputs** — the correlation between actual vehicle dynamics and the wear calculation was tightened.
- **The wear indicator was rescaled** with a larger red band to give better resolution. Note that the *visual* cliff and the *actual* cliff are not the same: community observation puts the real performance collapse deeper into the indicator than the colour suggests — around the 90–95%-red region rather than at first red.
- **Front-to-rear wear distribution shifted.** Multiple players reported that setups that were previously balanced now show **the fronts wearing noticeably faster than the rears**. Absolute wear rates also rose sharply — a Spa 1-hour that used to be doable on one set of Racing Hards became an 8-lap-per-stint proposition.

### 4.2 Which end goes first — the verification the brief asked for

**The premise "typically toward understeer on RWD" is directionally correct for post-1.49 GT7, but it is car-, track- and setup-dependent, and it was closer to the opposite before 1.49.**

The evidence:

- **Pre-1.49 Gr.3 MR testing** found **rears generally wearing faster than fronts** across most mid-engined cars, most pronounced on the Lamborghini Huracán, with the McLaren 650S more balanced. A minority (Peugeot VGT, GTI VGT) wore the fronts more.
- **Post-1.49 reports** describe the front/rear load distribution modelling as changed, with **fronts wearing much faster than the rears** on setups that had previously been balanced. This is consistent with 1.49's other changes: front tyres were given more direct cornering response but lower overall grip, and understeer *and* oversteer were both increased.

**The reliable synthesis — the "amplification rule":** the most robust finding across all GT7 tyre-wear testing is that **whatever the car does on fresh tyres, it does more of on worn tyres.** Oversteer-prone cars become progressively more difficult and less recoverable: the Ferrari 458 GT3, already prone to losing the rear under braking on new tyres, becomes destabilised by "the slightest steering while braking" on worn rubber, with recovery windows lengthening dramatically. Understeer-dominant cars simply become more understeery, requiring progressively earlier braking through the stint.

> **The amplification rule is the part of this section most likely to survive 1.71**, because it is a statement about the *shape* of degradation rather than its rate or its axle bias. It is also the most useful thing here, since it lets you predict late-stint behaviour from lap-1 behaviour without knowing the wear model at all. **Lean on it while the model is unknown.**

**Working conclusions for Gr.3:** *(v1.70 — re-open on 1.71)*

| Layout / condition | Typical late-stint migration | Pre-compensation |
|---|---|---|
| **FR Gr.3** (Supra, Mustang, Aston, Corvette, Viper, RCZ, WRX) on a track with long-radius, high-load corners | **Toward understeer** — front-limited | Bias the sheet slightly oversteery on fresh tyres; keep brake bias rearward headroom; consider slightly more front downforce than the fresh-tyre optimum |
| **MR / RR Gr.3** (Huracán, 650S, NSX, 911 RSR, RX-Vision) on a track with slow, traction-limited exits | **Toward power oversteer** — rear-limited | Bias slightly understeery on fresh tyres; keep brake bias *forward* headroom; lower LSD accel sensitivity; more rear downforce |
| **Any car, very high tyre multiplier (5–6×)** | Migration is fast and steep; the last third of the stint is a different car | Set up unambiguously for mid-stint; plan an in-race balance-management sequence, not a static setup |
| **Any car, 1× wear, sprint** | Negligible migration | Ignore degradation entirely; tune for fresh-tyre pace |

**Never assume. Measure.** The correct procedure is Section 8's stint test with the tyre-wear MFD page open, noting the wear percentage of each corner at 25/50/75/100% of the stint. This takes twenty minutes and is worth more than any published guidance including this document. **⭐ Post-1.71 this stops being good advice and becomes the only option.**

### 4.3 How to pre-compensate

The principle: **build a setup that is deliberately wrong in the opposite direction on fresh tyres, in proportion to the migration you have measured.**

**If front-limited (migrating to understeer):**
- Start the stint with the car **slightly oversteery/pointy** — you will "grow into" the balance.
- Front downforce: **one click more than the fresh-tyre optimum**, so that as the front tyre loses mechanical grip you retain aerodynamic front bite in the fast corners.
- Front springs and front ARB: **softer** than the fresh-tyre optimum, to increase front mechanical grip and reduce front tyre load fluctuation.
- Front camber: **less negative** than usual, to spread the wear across the contact patch rather than eating the inside shoulder.
- Brake balance: start moderately forward, **plan to move rearward** as the fronts go — you'll need the rear to help rotate.
- LSD braking sensitivity: don't overdo it. A very locked entry diff will fight a fading front axle.
- **Driving:** the biggest single-lap-time saving late in a front-limited stint is braking earlier and straighter. Trail-braking a dead front tyre generates enormous slip with zero rotation.

**If rear-limited (migrating to power oversteer):**
- Start the stint with the car **slightly understeery/safe.**
- Rear downforce: **one click more** than the fresh-tyre optimum, so the aero holds the rear as the mechanical grip fades.
- Roll-stiffness distribution: **forward** (softer rear ARB / stiffer front ARB relative to the fresh optimum) to unload the rear-outside tyre in roll.
- Rear toe-in: **+0.03° to +0.05°** more than the fresh optimum.
- LSD acceleration sensitivity: **lower**, to avoid the dual-wheel breakaway that GT7 produces from a locked axle on dead rears.
- Rear compression damping: **slightly higher**, to resist squat and reduce exit wheelspin.
- Brake balance: **plan to move forward** as the rears go.
- **Driving:** short-shift the last two gears out of slow corners. This saves fuel *and* rear tyre, and post-1.49 it costs very little. *(This is the technique that won the 17 Aug Watkins Glen race.)*

**Universal wear reducers (apply to any race setup):**
- Minimise toe deviation from neutral at both ends — toe scrub is a direct wear cost.
- Optimise camber for peak sustained lateral G, not for a copied number; correctly-set camber measurably extends tyre life.
- Reduce total sliding: this is now the dominant wear term post-1.49, so compliance, progressive damping and a non-knife-edge balance are all tyre-life measures, not just comfort measures. **⚠️ The claim 1.71 most directly re-opened.**
- Consider **more** downforce for tyre saving on high-speed circuits: real engineering shows high downforce preserves tyres by reducing slip in high-speed corners, and can recover roughly half the lap time lost to a 10% tyre-saving target. The catch, again from real engineering, is that high downforce **increases fuel consumption through drag** — so in a fuel-limited race this trade reverses. Know which resource is limiting you.

> **⭐ And the rule `03` §8.6 now carries: do not spend any of these against an unmeasured wear limit.** Every item above costs something. Post-1.71 the wear limit is unmeasured by definition. **Until Job 2 comes back, build the car the driver can drive and leave the tyre-saving budget unspent.**

---

## 5. THE DECISION RULE

### 5.1 The scalar

Define a single blend parameter **λ ∈ [0, 1]**, where λ = 0 is pure qualifying trim and λ = 1 is pure race trim. Every parameter delta in Section 2 is then applied as λ × (full race delta).

**Compute λ from four inputs:**

| Input | Contribution to λ |
|---|---|
| **Stint length** (laps you must run on one set) | 1–3 laps: 0.0 · 4–8 laps: 0.2 · 9–15 laps: 0.5 · 16–25 laps: 0.75 · 26+: 1.0 |
| **Tyre wear multiplier** | 0×: −0.3 · 1×: −0.1 · 2–4×: 0 · 5–6×: +0.2 · 10×+: +0.3 |
| **Fuel multiplier** | 0×: −0.2 · 1×: 0 · 2–3×: +0.1 · 5×+: +0.2 |
| **Expected traffic** (grid position vs. pace) | Clear air / pole: −0.1 · Mid-grid: +0.1 · Back of grid, must overtake: +0.2 (and specifically bias toward low-drag and braking stability) |

Clamp to [0, 1]. This is a heuristic, not physics — but it forces you to consider all four inputs rather than defaulting to "I'll just use my time-trial setup", which is what most drivers do and which is worth several tenths a lap over a stint.

> **⭐ 21 Aug — a fifth input, for this fortnight only: physics familiarity.** With every baseline unverified, add **+0.1** on the first two or three outings after a physics update. §1.3's asymmetry argument is the justification: too conservative costs hundredths, too aggressive costs a race. Remove it once a stint has been measured.

### 5.2 The decision table

| Format | Example (GT7) | λ | Governing philosophy | Concrete actions |
|---|---|---|---|---|
| **Pure Time Trial** | Sport Mode Lap Time Challenge, world-record hunting, Daily Race qualifying | **0.0** | Single-lap optimum, absolute | Max attack. Stiff, low, minimal ride height, aggressive rake, maximum-rotation LSD (low initial, low braking sens.), rearward brake bias, front toe-out, more camber, gearing exactly to the braking point. Accept a car that would be undriveable for 3 laps. |
| **Sprint, no stop, 0× fuel & 0× wear** | Daily Race B, 5 laps, wear/fuel off | **0.05–0.15** | Qualifying setup with a survivability tax | Essentially the quali car, with: brake balance +1 forward, LSD braking sensitivity +5, one click less rear wing if you must overtake. Nothing else changes. |
| **Sprint, no stop, 1× fuel & 1× wear** | Daily Race B, 5 laps, Red Bull Ring, RM | **0.2–0.3** | Quali car with a full tank and lap-1 traffic | Add: ride height +2 mm rear, brake balance +1–2 forward for the opening laps, gearing +5 km/h for the slipstream, rear toe-in +0.03°. Fuel burn over 5 laps ≈ 10–15 L — not decisive, but the *full-tank lap 1* matters. |
| **Sprint, one stop, moderate multipliers** | Daily Race C, 12–20 laps, 2–3× fuel, 5–6× wear, mandatory stop | **0.5–0.7** | Genuine race trim, two stints, mid-stint optimisation | Full Section 2 deltas at ~60% magnitude. Set up for mid-stint on stint 1. Plan an explicit brake-balance and fuel-map schedule. Choose partial refuel to run light on stint 2. Reserve one aero click of margin for the pass. |
| **Medium race, one stop, high wear** | Custom race, 20–30 laps, 1× fuel, 6× wear | **0.7–0.85** | Tyre-life-dominated | Full deltas weighted heavily toward wear reduction: softer platform, less camber, less toe deviation, lower LSD accel, forward roll-stiffness distribution if rear-limited. Mid-*tyre-life* optimisation, not mid-fuel. |
| **Long multi-stop / endurance** | 1-hour+ custom races, GTWS endurance rounds, Nürburgring 4h format | **0.9–1.0** | Consistency and survivability above all | Drop all four damper values 1–2 clicks from the sprint figure. Softest platform you can still drive fast on. Maximum stability. Gearing for mid-fuel and traffic. Full in-race MFD management plan (fuel map, brake bias, TCS). Accept a car that is 0.3 s/lap off the single-lap optimum in exchange for a 0.1 s standard deviation over 30 laps. |
| **Wet or changing conditions** | Any GT7 race with dynamic weather | **1.0+** | Beyond race trim | Raise ride height further, soften further, add downforce, more forward brake bias, lower LSD accel. GT7 models standing water and spray; the risk-adjusted optimum is well past the dry race setup. |
| **Locked setup (brake balance only)** | Most 2025–26 Daily Races | **n/a** | Racecraft is the setup | Your only levers are brake balance, TCS and fuel map. Spend your preparation on the brake-bias schedule (Section 2.8) and on Section 7. |

### 5.3 A special GT7 case: exploiting the split session

Because Sport Mode qualifying is a **separate session with fuel and wear disabled**, and because you can change the car between sessions in weeks where tuning is allowed, the correct workflow is:

1. Build the **λ = 0 quali car**. Set your grid time with it. Iterate until you have a time you're satisfied with.
2. **Rebuild to the λ-appropriate race car.** Do a full stint on it.
3. Race the race car.

Almost nobody does step 2. Doing it is worth roughly a tenth to three tenths a lap of race pace *and* a meaningful reduction in incident risk. It is the highest-leverage under-exploited mechanic in GT7 Sport Mode.

**A caution:** verify per week whether your setup actually applies. BoP races override many customisations, and there are long-standing community complaints about suspension settings not persisting between Daily Races in Sport Mode. **Check the car settings screen immediately before the race, every time.** ⭐ **This is now Standing Rule 9 in general form — confirm which sheet is physically in the car before diagnosing anything — and post-1.71 it is doubly required, because the patch may have reset or clamped saved values (`16` §12 Job 0).**

---

## 6. ONE-LAP TECHNIQUE — WHAT MAKES A GT7 QUALI SETUP FAST

### 6.1 GT7-specific conditions in qualifying

**Fuel:** consumption is disabled in Sport Mode qualifying and Time Trials. The car is effectively at minimum load throughout. There is no "burn a lap of fuel before the flying lap" strategy — it does nothing.

**Tyres:** brand-new, at optimum condition, with no wear accumulating. There is no undercut of the tyre's life, no build-up over an out-lap, no falling off the end.

**Tyre temperature:** GT7 *does* have a tyre temperature model — the telemetry exposes it and tyres display cold (blue) under some conditions — but it is **functionally invisible in practice**. Experienced players report never seeing a blue tyre in an actual race across hundreds of hours, and the mechanic only manifests after long stationary periods. **Practical conclusion: there is no meaningful warm-up phase in GT7. Do not plan out-laps around tyre warm-up. Your first flying lap can be your fastest lap.** This is a fundamental difference from ACC, iRacing, LMU and rFactor 2, and it changes everything about one-lap preparation.

> **⚠️⚠️ 21 Aug 2026 — DOWNGRADED TO [CONTESTED]. Do not rely on this.**
>
> Two reasons. **First, it was never agreed within this knowledge base:** `03` §3.2 says the opposite — cold tyres have materially less grip, out-lap braking distances are longer, warm-up takes 2–3 corners, and there are reported track-temperature interactions. These two documents have always disagreed and the disagreement was never resolved.
>
> **Second, 1.71 states: "Tyre heating and wear values have been adjusted."** That is not proof this claim is now wrong — PD can adjust a parameter that stays practically inert — but it is a direct signal that heat is a live, tuned part of the model.
>
> **Test 5 in Section 8 resolves the practical question in ten minutes** (cold start + immediate flying lap vs. flying lap after three warm-up laps). `16` §12 Job 6 resolves the mechanism with telemetry. **Until one of them is run, plan out-laps as if warm-up matters** — the asymmetry argument again: assuming warm-up exists when it doesn't costs a fraction of an out-lap; assuming it doesn't when it does costs a qualifying lap.

*Confidence: high on the observable behaviour, moderate on the mechanism.* **⚠️ Both downgraded — the observable behaviour was observed on a previous version.**

**Track state:** GT7 models ambient temperature, humidity and track surface temperature within its physics, and Polyphony has stated as much. What it does **not** convincingly model is progressive rubbering-in / track evolution from repeated laps in the way iRacing or ACC do — community expectation of meaningful player-driven track evolution has consistently outrun the implementation. **Practical conclusion: there is no reliable "wait for the track to rubber in" effect in GT7 qualifying.** However, ambient/track temperature does vary with time of day in scheduled sessions, and grip does vary between lobbies for that reason. If your session has a time-of-day setting, cooler conditions generally mean more grip.

**BoP:** as of **v1.68 (March 2026)**, BoP can be toggled on in Time Trials. Check whether your event is BoP-on or BoP-off, because the optimal car and the optimal setup differ.

**⭐ Leaderboards:** **1.71 reset every ranking board in the game** — World Circuits, Licence Centre, Missions, Music Rally — and re-issued Circuit Experience and Licence target times. **Any personal reference time from before 20 August 2026 is not comparable to a time set now.** If you use ghosts or reference laps as a coaching tool (§6.3), the references need rebuilding.

### 6.2 The one-lap setup checklist

Given the above, the GT7 quali setup is simple to state:

1. **Maximum rotation, minimum stability margin.** Low LSD initial torque, low LSD braking sensitivity, rearward brake balance, front toe-out, rear toe-in near neutral. In a game with no warm-up phase and no wear, the only thing you are protecting is one lap. **⚠️ "No warm-up phase" is now [CONTESTED] — see §6.1.**
2. **Lowest viable ride height, sharpest viable rake.** Bottoming is the only constraint. With no fuel load, you can run lower than any race setting.
3. **Stiff platform.** Response and aero-platform stability, both of which are pure single-lap currency.
4. **Aero at the true single-lap optimum, with no overtaking discount.** On downforce-limited circuits that means maximum; on Monza-type circuits it means finding the genuine minimum-lap-time point, which is often *more* wing than drivers instinctively run because a hot lap has no straight-line-defence requirement.
5. **Gearing exactly to the braking point.** No slipstream allowance. Every km/h of unused top speed is wasted ratio.
6. **Marginally more camber than race trim** (+0.2° to −0.5° more negative), in the direction that maximises sustained lateral G in the circuit's highest-load corner. **⚠️ Suspended pending the Job 5 camber A/B — see §2.7.**
7. **Fuel map 1.** Maximum power. There is no reason to run anything else with consumption off.

### 6.3 GT7 quirks that decide hot laps

- **The abrupt grip-to-slip transition.** GT7 gives you very little warning at the limit and very little recovery authority — throttle modulation does not recover a slide the way it does in other sims; near-total lift is often the only option. A quali setup must be aggressive but must stop short of the point where a small overdrive costs you the whole lap. Find that point deliberately, in practice, and set the car one small step back from it. **⚠️ 1.71 reworked the slipping regime specifically. Re-find that point before trusting where it used to be.**
- **Short-shifting can be faster.** Verified: shifting at the redline is *slower* in quite a few Gr.3 cars, independent of fuel considerations. Some GT7 cars fall off a torque cliff at the top of the range and the shift is worth more than the last 500 rpm. Test the last two gears on your circuit's most important exits — this is free lap time that most drivers never look for. **⚠️ 1.71 introduced a new engine torque control map and adjusted maximum RPM on six race cars (none of ours). Re-test the shift points.**
- **Downshift protection (v1.66, Dec 2025).** GT7 prevents downshifting from excessively high RPM with manual transmissions. **⭐ UPDATED: 1.71 relaxed this.** Forced downshifts and engine over-rev are now possible **earlier** than under the December 2025 implementation, though still more restricted than pre-1.66. **If you previously abandoned an aggressive down-the-'box braking technique because 1.66 blocked it, re-test it — some of that authority is back.**
- **Brake balance sensitivity increased post-1.49.** Bias changes have a much larger stability effect than they used to. The standard advice — keep it near zero and test changes on slow laps — is well-founded. In quali you will run further from zero than that advice suggests, but you should know exactly where the cliff is. **⚠️ 1.71 adjusted ABS cornering brake behaviour.**
- **ABS.** Some events prohibit ABS (a February 2026 Daily Race C ran ABS-prohibited). Without ABS, brake balance becomes vastly more consequential and the quali philosophy of aggressive rearward bias becomes dangerous. Move it forward and prioritise not locking.
- **Use the tools.** Load a faster driver's ghost with sector resets and progress from slower to faster references rather than chasing the alien directly; use the Delta telemetry corner-by-corner to find the specific habit (usually insufficient or excessive trail-braking) that is costing you. As of v1.68 the data-logging suite also gained a Drift Analyzer, which is useful for quantifying slide angles — and therefore, post-1.49, tyre wear. **⚠️ Reference ghosts from before 20 Aug 2026 are on old physics — see §6.1.**

---

## 7. TRAFFIC AND RACECRAFT

> **This section is intact, and 1.71 made it more valuable rather than less.** The new "Championship" damage setting — Light's severity, triggered from more minor collisions, with variable recovery time — prices contact more readily than before. **If the league adopts it, everything in §7.2 and §7.3 goes up in value and the λ scalar's traffic term goes up with it.** See `16` §9.

This section matters disproportionately in GT7, because in most Daily Races it is the *only* dimension you can influence.

### 7.1 Top-speed trim and the slipstream economy

GT7's slipstream is a substantial effect — notably stronger than in many sims, and strong enough that whole race formats (Special Stage Route X one-lap events) are built around it, with slipstreaming and bump-drafting as the primary skills.

**The engineering consequences:**

1. **Never gear so that you hit the limiter in a tow.** If your top gear is exactly right in clean air, it is wrong in a slipstream, and it is wrong at precisely the moment you need it. Add 5–15 km/h of theoretical top speed on any circuit with a straight long enough to complete a pass. This is worth more than the tenth of a corner-exit acceleration you give up.
2. **Low-drag trim converts a tow better than high-drag trim.** Two cars with equal power but different wing settings gain different amounts from the same slipstream — the lower-drag car has a higher terminal velocity and therefore a longer runway before the tow's benefit saturates. If your race plan is "pass on the straight," take the wing off.
3. **The tow is symmetric — plan for defence too.** If you qualify well and expect to be defending, longer gearing and lower drag protect you. If you qualify badly and expect to attack, the same choices help. There is essentially no race scenario in which qualifying-optimal top-end gearing is correct.
4. **Bump-drafting is a real technique in GT7** but penalties remain enabled for violent contact. Trim for the tow, not for the shove. **⚠️ And 1.71 both adjusted collision damage thresholds and changed the PP regulations on the Power Pack Bump Drafting event — PD are actively tuning this area.**

### 7.2 Braking stability into overtaking zones

**The overtake happens in the braking zone, not on the straight.** The straight only sets up the geometry. What decides whether you complete the move is whether you can brake later than the car ahead **from the inside line, off the racing line, on a dusty and marbled surface, with reduced downforce from having just been in their wake, into a corner you will now enter from the wrong angle.**

A quali setup fails all of those conditions. A race setup should be built for them:

- **LSD braking sensitivity high** (2.5). This is the single most important overtaking-stability parameter. A locked-on-entry rear axle lets you brake late off-line without the rear stepping out. It costs turn-in you don't need at the apex of an overtaking move anyway.
- **Rear toe-in** (2.7). Cheap, effective straight-line and trail-brake stability.
- **Brake balance forward of the quali value** (2.8), and adjustable live. Move it forward one click before you commit to an attack sequence and back afterwards. This is a legitimate in-race tactic that almost nobody uses.
- **Rear aero balance** (2.1). A rear-biased aero platform survives the dirty-air downforce loss on the run up to the braking zone; a front-biased one goes light and you arrive at the braking point unable to commit.
- **Sufficient ride height and compliance** (2.3, 2.4). Off-line braking means bumps, dust and kerbs. A car set on its bump stops for a clean-line qualifying lap will not brake off-line.
- **Post-1.49 note:** cars "feel heavier and require earlier braking" than pre-1.49, and brake bias has a larger effect on stability. Both facts favour a conservative, forward-biased, stable braking setup in race trim. **⚠️ 1.71 adjusted ABS slip-ratio control and cornering brake behaviour — re-establish the braking reference before racing on it.**

### 7.3 Defensive drivability

The defensive requirements are different again:

- **Traction out of slow corners** is the primary defensive quality. If they can't get alongside on the exit, they can't attack on the straight. This argues for **more** LSD acceleration sensitivity and rear compression damping than the pure tyre-preservation optimum — a real conflict with Section 4's advice. Resolve it by circuit: on a track with one decisive slow-corner-onto-long-straight sequence, favour traction; elsewhere, favour tyre life.
- **The ability to take a defensive line without losing the car.** Defensive lines are tighter, later-apexing, and involve more kerb and more off-line surface than the racing line. A compliant, stable, softly-damped car can defend for ten laps; a knife-edge car will make a mistake within three.
- **Predictability under contact.** GT7 racing involves contact. A car with a high roll centre, stiff ARBs and minimal compliance is destabilised by a light nudge; a compliant car absorbs it. This is an unglamorous but genuinely decisive race-setup consideration. **⭐ And under the Championship damage setting, contact now also carries a mechanical cost with a variable recovery time — so absorbing a nudge cleanly is worth more than it was.**
- **Top-end for the defence** (7.1). Same lever, opposite use.

### 7.4 The traffic-adjusted lap-time budget

An explicit accounting exercise worth doing before every race:

| Item | Typical cost/gain |
|---|---|
| Being stuck behind one car for a lap on a track where you're 0.4 s/lap faster | −0.4 s, plus elevated tyre energy from dirty air |
| Failing an overtake and having to re-set for a lap | −0.5 to −1.5 s |
| A half-spin from a race setup that was too aggressive | −3 to −6 s, plus possible penalty |
| One click less rear wing, on a high-speed circuit | +0.05 to +0.15 s/lap in clean air lost, but +3–8 km/h terminal speed → often the difference between completing and failing a pass |
| A brake-balance click forward for the opening 3 laps | ~0.05 s/lap slower, materially lower lap-1 incident probability |
| **⭐ Contact under the Championship damage setting** | **Light-severity mechanical damage with a recovery time that scales with the hit. Prices in above every "it's only a nudge" line.** |

**The conclusion is consistent:** in any format with traffic, the race-trim compromises pay for themselves several times over. The only format where a quali setup is genuinely optimal for a race is a race you start from pole, lead from lights to flag, and finish with fresh tyres — which is to say, a time trial with extra steps.

---

## 8. VALIDATION PROTOCOL — HOW TO VERIFY ALL OF THIS FOR YOUR CAR

> **⭐ 21 August 2026 — this is now the most useful section in the document.** Every test below was written for exactly the situation 1.71 created. **Tests 2 and 5 are `16` §12 Jobs 2 and 6 and should be run first.** None of the six has a valid v1.71 result.

None of the above substitutes for measurement. Much GT7 tuning knowledge is community consensus rather than documented physics, and GT7's physics have changed materially (1.49, 1.52, 1.55, 1.66, 1.68, **1.71**). Use these tests.

**Test 1 — Fuel weight sensitivity (30 min).**
Custom race, your car, your circuit, fuel consumption 1×, tyre wear off. Run 15 laps at consistent pace. Plot lap time against remaining fuel. The slope is your car/track fuel sensitivity in s/L. Multiply by 100 to get your full-vs-empty delta. Also note the *balance* at 100 L, 50 L and 10 L. **⚠️ Rolling resistance changed in 1.71 — this test also re-establishes L/lap.**

**Test 2 — Tyre degradation profile (30 min).**
Same setup, fuel off, tyre wear at the multiplier your target race uses. Run to the tyre's useful end. Record per-lap: lap time, and the wear percentage of each of the four corners from the MFD. This tells you (a) your real cliff point, (b) which axle is limiting, (c) the shape of the degradation curve. **This is the single highest-value test in the document.** **⭐ = `16` §12 Job 2. Run it on the Huracán at Watkins Glen, at the league multiplier, from full fuel, to *felt* fall-off rather than a gauge number.**

**Test 3 — Ride height / fuel platform interaction (20 min).**
Set ride height at your quali minimum. Run one lap with a full tank. Note bottoming, understeer and any instability over compressions. Raise the rear 3 mm. Repeat. Find the height at which the full-tank car behaves. That is your race ride height floor. **⚠️ 1.71 changed damper attenuation and suspension defaults — and this test is also the honest way to find out what happened to the 1.49 bottoming problem, since the Pit Crew `bottoming` flag is not a valid trigger (Standing Rule 8).**

**Test 4 — Aero isochrone (20 min).**
Three configurations: quali-optimal wing, −2 clicks rear, −4 clicks rear (with front re-balanced by half). For each, record (a) best lap in clean air, (b) terminal speed at the end of the longest straight. Plot. The correct race setting is the one where the terminal-speed gain exceeds the lap-time loss by enough to complete a pass, given the closing speed you need. **⚠️ Aero ranges were revised on race cars — re-read `11` first or the "clicks" are meaningless.**

**Test 5 — Warm-up (10 min).**
Cold start from a stationary car, immediate flying lap. Then three warm-up laps and a flying lap. Same conditions. If the delta is under a tenth, GT7's tyre temperature is irrelevant for your purposes and you can plan single-out-lap qualifying attempts. **⭐ Now settles a live disagreement between this document (§6.1) and `03` §3.2, on a version where PD explicitly adjusted tyre heating. Ten minutes to close a two-week-old contradiction.**

**Test 6 — Slipstream gearing (10 min).**
Lobby with one other car (or a ghost/AI). Note your terminal speed at the end of the longest straight in clean air and in a full tow. If the tow speed hits the limiter, lengthen the final drive until it does not. **⚠️ Doubles as the rolling-resistance check, and closes the Huracán's gearing constant K if run in top gear at the limiter.**

**⭐ Test 7 — NEW, 21 Aug 2026: the assists and FFB baseline (15 min).**
Three laps TCS 0, three laps TCS 1, same car and track. Note the per-corner cost and whether intervention feels earlier or later than before (`03` §2.5 puts the v1.70 price at up to two tenths per corner).

**And before any of it: re-check the wheel.** 1.71 adjusted steering wheel force feedback and understeer vibration, and optimised Fanatec Auto Setup parameters. **On an 18 Nm DD Extreme, an FFB change is easy to misread as a grip change and expensive to misread.** Confirm the wheel settings are where they were and consciously separate "the wheel feels different" from "the car has less grip" before diagnosing anything else.

---

## 9. CONFIDENCE AND CAVEATS

- **Well-documented and verified:** GT7's 100 L universal fuel tank; the 1.49 tyre and physics changes (post-50%-wear drop, sliding-dominant wear, increased understeer *and* oversteer, greater brake-bias sensitivity); fuel-mixture arithmetic (−4% power / −8% consumption per step); official natural-frequency ranges (3–5 Hz race, 1.1–1.5 Hz road); the Daily Race settings-restriction regime and multipliers; qualifying being a separate no-wear/no-fuel session; the March 2025 Gr.3 BoP power cut; downshift protection in 1.66; BoP-in-Time-Trials in 1.68. **⚠️ The 1.49 physics items are now historical rather than current — see the banner.**
- **Community consensus, well-supported but not officially documented:** slider baselines (damper 20–40/30–50, LSD 5–60 on v1.70, ARB 1–10, downforce percentage bands by track type), the rake-vs-rotation relationship, the "expansion above compression" convention, drivetrain-specific LSD and brake-bias baselines, tyre-temperature being practically inert. **⚠️ The slider baselines are explicitly revised by 1.71; tyre-temperature-inert is downgraded to [CONTESTED].**
- **Derived from real-world race engineering and applied by analogy — validate in-game:** the specific magnitudes of the quali-to-race parameter deltas, the ~1.5–2.5 s/lap Gr.3 fuel delta, the mid-stint principle's quantitative form, ride-height-sensitive aero mapping in GT7, and the λ decision scalar. **This tier is the least affected by 1.71 — real-world race engineering does not patch.**
- **Actively contested / car-dependent:** which axle degrades first. Pre-1.49 Gr.3 MR data showed rear-limited behaviour; post-1.49 reports show front-limited behaviour on many cars. **Measure it (Test 2) rather than assuming.** **⭐ And now: whether tyre temperature is practically relevant (§6.1 vs `03` §3.2), and whether GT7's grip-to-slip transition is still binary (§1.2a).**
- **Version risk.** GT7 has shipped physics-affecting updates in 1.49, 1.52, 1.55, 1.66, 1.68 **and 1.71**. Re-validate baselines after every major patch, and treat published setups older than the current physics build as starting points only. **⭐ 1.71 is the largest since 1.49: it reworked the tyre slipping model, per-car steering geometry, damper attenuation, the adjustment ranges of suspension / differential / aero, PP fleet-wide, both assists, and the damage model — and PD reset every leaderboard in the game. See `16-update-1.71-physics-change.md`.**

---

## SOURCES

**GT7 physics, updates and official material**
- [Update Notice (1.71) — Gran Turismo official](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html) — **the current baseline**
- [GTPlanet — Update 1.71 Arrives With Major Physics Changes](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Traxion — 1.71 brings sweeping physics changes, resets leaderboards](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [Update Details (1.49) — Gran Turismo official](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)
- [Update Details (1.66) — Gran Turismo official](https://www.gran-turismo.com/us/gt7/news/00_3200508.html)
- [Update Notice (1.65) — Gran Turismo official](https://www.gran-turismo.com/gb/gt7/news/00_8101458.html)
- [Update Notice (1.60) — Gran Turismo official](https://www.gran-turismo.com/us/gt7/news/00_5548493.html)
- [Gran Turismo 7 / Updates — Gran Turismo Wiki](https://gran-turismo.fandom.com/wiki/Gran_Turismo_7/Updates)
- [Gran Turismo 7 Physics Update 1.49 — Breakdown (DG EDGE)](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424)
- [GT7 Update Finally Puts to Rest a Tire Mystery (The Drive)](https://www.thedrive.com/news/gt7-update-finally-puts-to-rest-a-tire-mystery-thats-haunted-me-for-years)
- [Surprise GT7 Update Brings Bugfixes and Power Pack Rebalancing (GTPlanet)](https://www.gtplanet.net/gran-turismo-7-update-166-bugfixes-20251211/)
- [GT7's Latest BOP Update Just Nerfed Every Gr.3 Car (GTPlanet)](https://www.gtplanet.net/gran-turismo-7-bop-change-20250327/)
- [Balance of Performance — Gran Turismo Wiki](https://gran-turismo.fandom.com/wiki/Balance_of_Performance)
- [Sport Mode (GT7) — Gran Turismo Wiki](https://gran-turismo.fandom.com/wiki/Sport_Mode_(GT7))

**GT7 tuning references**
- [Gran Turismo 7 Tuning Guide: Every Setting Explained (Coach Dave Academy, 2026)](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)
- [The Complete GT7 Tuning Cheat Sheet (Flux89)](https://www.flux89.com/guides/gt7-tuning-cheat-sheet)
- [GT7 Car Setup for Beginners: What Every Setting Actually Does (ShiftPoint Guide)](https://www.shiftpointguide.com/setups/gt7-beginners-setup-guide)
- [How To Tune in Gran Turismo 7 (SimRacingSetup)](https://simracingsetup.com/gran-turismo/how-to-tune-in-gran-turismo-7/)
- [Understanding Natural Frequency in Gran Turismo 7 (DG EDGE)](https://www.dg-edge.com/articles/guides-tuning/understanding-natural-frequency-in-gran-turismo-7/407)
- [Mastering Brake Balance in Gran Turismo 7 (DG EDGE)](https://www.dg-edge.com/articles/guides-equipment/mastering-brake-balance-in-gran-turismo-7/360)
- [FILO Engineering — GT7 Transmission Overview](https://www.filoengineering.com/home/gran-turismo-7/tuning-setups/tuning-theory/transmission-overview)
- [Gran Turismo 7: Tuning and Setup Guide (Red Bull)](https://www.redbull.com/ca-en/gran-turismo-7-tuning-setup-tips-guide)
- [GT7 Tuning: The Ultimate Guide (RacingGames.gg)](https://racinggames.gg/article/gran-turismo-7-the-ultimate-tuning-guide-suspension-transmission-differential-nitrous-ballast-ecu-aerodynamics)
- [Doughtinator — Ultimate GT7 Tuning Guide](https://doughtinator.com/en-us/blogs/guides/tuning)

**GTPlanet forum threads (community data and testing)**
- [Gran Turismo 7 Undocumented Changes Thread (1.71)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-1-71.439041/)
- [Natural frequency in 1.49](https://www.gtplanet.net/forum/threads/natural-frequency-in-1-49.427861/)
- [Fuel Capacity and Tuning Components](https://www.gtplanet.net/forum/threads/fuel-capacity-and-tuning-components.406837/)
- [Test Results: Fuel Mixture Settings and Other Fuel-Saving Techniques](https://www.gtplanet.net/forum/threads/test-results-fuel-mixture-settings-and-other-fuel-saving-techniques.369387/)
- [BoP Fuel Efficiency Comparison](https://www.gtplanet.net/forum/threads/bop-fuel-efficiency-comparison.407551/)
- [Gr.3 MR cars tire wear test](https://www.gtplanet.net/forum/threads/gr-3-mr-cars-tire-wear-test.384914/)
- [Tyre wear..](https://www.gtplanet.net/forum/threads/tyre-wear.411748/)
- [Reducing Tyre Wear with suspension tuning](https://www.gtplanet.net/forum/threads/reducing-tyre-wear-with-suspension-tuning.408750/)
- [Best methods to tire saving?](https://www.gtplanet.net/forum/threads/best-methods-to-tire-saving.383149/)
- [GT7 tire model](https://www.gtplanet.net/forum/threads/gt7-tire-model.409503/)
- [Tyre temperature (page 4)](https://www.gtplanet.net/forum/threads/tyre-temperature.418092/page-4)
- [Gran Turismo 7 Track Conditions](https://www.gtplanet.net/forum/threads/gran-turismo-7-track-conditions.394429/)
- [What exactly is different in Racing vs Qualifying in Sport Mode](https://www.gtplanet.net/forum/threads/what-exactly-is-different-in-racing-vs-qualifying-in-sport-mode-aka-online-vs-offline-physics.385737/)
- [Where is the state of GT7 Tuning?](https://www.gtplanet.net/forum/threads/where-is-the-state-of-gt7-tuning.429998/)
- [GT7 Daily Races - Tuning…](https://www.gtplanet.net/forum/threads/gt7-daily-races-tuning%E2%80%A6.422718/)
- [Car Settings don't Translate to a Race](https://www.gtplanet.net/forum/threads/car-settings-don%E2%80%99t-translate-to-a-race.424628/)
- [Does Less fuel equal lighter car?](https://www.gtplanet.net/forum/threads/does-less-fuel-equal-lighter-car.98763/)
- [Racing soft tires vs medium](https://www.gtplanet.net/forum/threads/racing-soft-tires-vs-medium.427384/)
- [GT7 Max Tuning, Downforce and Special Parts Database](https://www.gtplanet.net/forum/threads/gran-turismo-7-max-tuning-downforce-and-special-parts-database.433059/)

**GT7 race formats and regulations**
- [GT7 Daily Races Explained (Coach Dave Academy)](https://coachdaveacademy.com/tutorials/gt7-daily-races-explained/)
- [GT7 Time Trials Explained (Coach Dave Academy)](https://coachdaveacademy.com/tutorials/gt7-time-trials-explained/)
- [GT7 Daily Races: It's a Setup! (GTPlanet, Jul 2024)](https://www.gtplanet.net/gran-turismo-7-daily-races-20240708/)
- [GT7 Daily Races: Speed Demons (GTPlanet, Jul 2025)](https://www.gtplanet.net/gran-turismo-7-daily-races-20250728/)
- [GT7 Daily Races: Toyota Tuner Trial (GTPlanet, Feb 2026)](https://www.gtplanet.net/gran-turismo-7-daily-races-20260209/)
- [GT7: A guide to race strategy and pit stops (Strat Packer)](https://stratpack.blog/2022/04/01/gran-turismo-7-guide-race-strategy-pit-stops)
- [How to adjust fuel map in Gran Turismo 7 (RacingGames.gg)](https://racinggames.gg/article/how-to-adjust-fuel-map-gran-turismo-7)
- [What is the Slipstream Effect? (Samurai Gamers)](https://samurai-gamers.com/gran-turismo-7/what-is-slipstream-effect/)
- [Gran Turismo World Series (Wikipedia)](https://en.wikipedia.org/wiki/Gran_Turismo_World_Series)

**Motorsport race engineering (applied by analogy)**
- [Enhancing the Art of Race Car Setup: The Ultimate Balance (Michelin Canopy)](https://simulation.michelin.com/canopy/technical-articles/enhancing-the-art-of-race-car-setup-the-ultimate-balance)
- [Get a grip on tyre saving (Michelin Canopy)](https://simulation.michelin.com/canopy/technical-articles/get-a-grip-on-tyre-saving)
- [Fuel Load and Lap Time Explained (The Motorsport Metrics)](https://themotorsportmetrics.com/fuel-load-and-lap-time/)
- [F1 Qualifying vs Race Pace Explained (The Motorsport Metrics)](https://themotorsportmetrics.com/f1-qualifying-vs-race-pace/)
- [5 Factors Impacting Qualifying vs Race Pace (F1 Briefing)](https://f1briefing.com/5-factors-impacting-qualifying-vs-race-pace/)
- [Difference between qualifying and race trim (Autosport Technical Forum)](https://forums.autosport.com/topic/161582-difference-between-qualifying-and-race-trim/)
- [Racing setup (Wikipedia)](https://en.wikipedia.org/wiki/Racing_setup)
