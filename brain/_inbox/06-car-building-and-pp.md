# Gran Turismo 7 — Car Building, Performance Points, and Min-Maxing for Open-Tuning Leagues

**Knowledge base document · Compiled August 2026 · Game version reference: Update 1.70 (June 2026)**
**⚠️ Updated 21 Aug 2026 — 1.71 banner added below. The body is a v1.70 record.**

**Scope:** written for a league running **no BoP, open garage tuning, PP-capped classes**. Under those rules the build *is* the competition, and the PP system is the ruleset you are gaming.

---

# 🟠 1.71 BANNER — PP MOVED FLEET-WIDE

**This document predicted 1.71, and the prediction is worth reading back before anything else.** §1.4 closes with:

> *"**Uncertainty flag:** an August 2026 update was teased at time of writing. Any physics touch re-rolls PP across the board. **A league must pin its ruleset to a game version and re-validate builds after every patch.** This is not optional in GT7 — it has happened at least three times since launch."*

**It happened on 20 August 2026. Update 1.71 adjusted Performance Points across the game**, as a direct consequence of a physics rework covering the tyre slipping model, per-car steering geometry, damper attenuation, and the default settings *and adjustment ranges* of suspension, differential and aerodynamics. Event regulations were separately changed for the **Lightweight K Cup** and the **Power Pack Bump Drafting** event. Full changelog: `16-update-1.71-physics-change.md`.

**That makes it the fourth time. §9.3's version-lock rule is no longer advice — it is the thing that just happened to your grid.**

## What this means, in order of urgency

**1. Your three builds may have moved relative to the league cap. This is a race-weekend problem, not a tuning problem.**
Read the current PP of each car **as built** and compare it to the figure on its setup sheet. Ten minutes, `16` §12 Job 4. If a build is now over, you find out today or you find out at scrutineering. If it is now *under*, you have free headroom and someone else will find theirs first.

**2. Every PP number in this document is a v1.70 observation.** That includes the ones this file was most confident about:
- Fully Customisable Suspension at **+9.1 PP**
- Sports Soft tyres at **+27.5 PP** on a TVR Tuscan Speed 6
- Racing Intercooler at **+3.03 PP**
- ECU 100 → 99 costing **14.32 PP**
- 200 kg of ballast ≈ **20 PP**
- Nitrous ≈ **0 PP**

**None of these are deleted — they remain the only controlled measurements in the public record, and they are the right *kind* of number.** They are simply pre-1.71. Re-measure the ones your build depends on.

**3. The *mechanisms* survive, and they are the valuable half of this document.** PP is simulation-derived (§0), parts cost PP while settings are free (§1.2), the restrictor and the ECU shape the curve differently (§4), ballast position is a free-PP exploit (§5.5), body rigidity often lowers PP (§6.6), and PP is a poor proxy for lap time (§8.2). **None of that is a number. All of it still holds.**

**4. One mechanism claim got *stronger*, not weaker.** §0's argument that PP is a physics simulation rather than a formula predicts that changing the physics necessarily re-rolls PP. **1.71 is the fourth confirmation.** This is not a rebalance PD chose — it is a side effect they had to absorb, which is why the PP line in the notes sits alongside the physics lines rather than in a balance section.

**5. Expect new anomalies, and have the rule ready before someone builds a season around one.** §9.3's written anomaly rule exists because the LSD bug (−139 PP), the gear-ratio threshold bug (+41 PP), and the post-1.49 no-PP-value cars all appeared *after* physics changes. **A patch this size will produce new ones.** In particular, watch for:
- **Cars returning no PP value at all** — the 1.49 failure mode. Triggers were Racing Softs, carbon-ceramic brakes, Fully Customisable Suspension, superchargers and engine swaps. If a build loses its number, work through that list.
- **Aero**, because 1.71 revised aero defaults *and adjustment ranges* on race cars. §1.4 already records the aero→PP sign as car-dependent and unpredictable; a range change gives it new shapes to be unpredictable in. **Press Triangle more, not less.**
- **The two free-performance quirks** (§6.6 wide body and body rigidity lowering PP) — both are PP-simulation behaviours and both need re-confirming before being exploited.

**6. Two things to raise with the organiser now, both better raised before a round than after one.**
- **PP moved fleet-wide**, so this is a re-scrutineering event for the whole grid, not just for you.
- **1.71 added a "Championship" mechanical damage setting** — Light's damage severity, triggered from more minor collisions, with recovery time varying by severity. **It is a genuinely good regulation tool for a no-BoP league that wants to price contact without ending races**, and it belongs in §9.2's Tier 2 list. See `16` §9.

## What to re-measure, and when

**During the Job 4 PP audit (10 minutes, while the build screens are already open):**
- Current PP of all three cars as built, against their setup sheets
- Fully Customisable Suspension's PP cost (was +9.1)
- Whether body rigidity and wide-body still *lower* PP
- Whether nitrous is still 0 PP — **and if it is, §9.2's ban is still the right call**

**Deferred until a build actually needs it:** the compound-step PP costs, the ECU/restrictor PP curve, the ballast PP-per-kg. **All are car-specific and were always meant to be measured on the car rather than read from a table** — the patch changes nothing about that instruction, only about how stale the illustrative numbers are.

---

## 0. Read this first — the single most important fact

**There is no published PP formula, and there almost certainly is no closed-form formula to find.**

PP in GT7 is not `f(power, weight, tyres)`. It is the output of an **internal physics simulation**: the game runs the car through a synthetic evaluation (acceleration runs, cornering/lateral-G tests, high-speed stability checks) using the *live physics engine*, and reduces the result to a single number.

The strongest public evidence for this:

- When Update 1.49 (July 2024) changed the physics engine, a number of cars came back with **no PP value at all** — a warning triangle instead of a number, making them unusable in every mode including custom races. GTPlanet's administrator explained it as: *"In their current state of tune, something about them breaks the physics simulation and a PP value cannot be calculated."* A number cannot fail to compute if it is an arithmetic formula; a simulation can fail to converge. ([GTPlanet — PP Issue!](https://www.gtplanet.net/forum/threads/pp-issue.427864/))
- The same moderator on the 1.49 PP shifts: *"The changes in Performance Points are down to the physics engine change. This is the third time it's occurred since launch."* ([GTPlanet — #StopNerfingCars](https://www.gtplanet.net/forum/threads/stopnerfingcars.427824/)) **⭐ 1.71 makes four.**
- Community attempts at reverse-engineering conclude the same. From the most recent dedicated thread: *"The PP score is determined by simulation, you can't reverse engineer it"* — the inputs include wheelbase, track width, suspension geometry, mass and CoG location, body rigidity, front/rear downforce and drag, per-axle tyre spec, the full torque curve and turbo transient behaviour, drivetrain layout, gearbox, clutch, flywheel, diff and brakes, *and* hidden variables not exposed to the player. The thread's practical conclusion was that a neural network trained on observed data is the only viable predictor. ([GTPlanet — GT7 Tuning Reverse Engine PP ratios](https://www.gtplanet.net/forum/threads/gt7-tuning-reverse-engine-pp-ratios.438245/))

> **⭐ Note how well that input list predicts 1.71's damage.** It names **suspension geometry**, **the full torque curve**, **front/rear downforce and drag**, and **per-axle tyre spec** — and 1.71 reworked steering geometry per car, introduced a new engine torque control map, revised aero defaults and ranges, and changed the tyre model. **Four of the named PP inputs moved at once.** A large PP re-roll was the only possible outcome.

**Consequence for your league:** you cannot compute a build's PP offline. You must build empirically in the garage, watching the PP readout change. But the *simulation's blind spots are stable and exploitable*, and that is what the rest of this document is about.

> **Uncertainty flag:** every PP delta quoted in this document is a *single observed data point on a specific car in a specific state of tune*. PP responses are strongly non-linear and car-dependent. Treat all numbers as order-of-magnitude guidance, not constants. Re-measure on the actual car. **⭐ And as of 21 Aug 2026, every one of them is also from a previous game version.**

---

## 1. The PP System

### 1.1 What the simulation appears to measure

From the pattern of observed PP responses, the evaluation weights roughly these things:

| Measured quantity | Weight in PP | Evidence |
|---|---|---|
| Straight-line acceleration / power-to-weight | **Very high** | Every power and weight change moves PP immediately and predictably |
| Top speed / high-speed capability | **High** | Reducing top-end power (restrictor) drops PP hard |
| Lateral G (cornering grip) | **High** | Tyre compound is the single biggest step-change in PP |
| High-speed rotational G (stability/yaw) | **Moderate, and erratic** | Ballast *position* — which changes almost nothing physically — can swing PP disproportionately |
| Braking | **Low** | Brake upgrades barely move PP |
| Aero/downforce | **Low and inconsistent in sign** | See §1.4 |
| Suspension *settings* | **Zero** | Confirmed: settings do not enter PP |
| Diff *settings* | **Zero** | Confirmed |
| Gear *ratios* | **Zero to ~±1 PP** | See §6.3 — historically exploitable, largely patched |

A GTPlanet administrator's summary of the bias: *"The PP system gives higher numbers for straight line speed and lateral g."* ([GTPlanet — Why does increasing body rigidity lower the PP?](https://www.gtplanet.net/forum/threads/why-does-increasing-body-rigidity-lower-the-pp.424639/))

> **⭐ 1.71 note on this table: the *structure* is what matters and it should survive.** Which quantities the sim weights heavily is a property of how PD built the evaluation, not of the physics values it runs on. **But two rows deserve a re-check on v1.71:** the tyre row (the tyre model changed, so a compound step may buy a different amount of lateral G and therefore cost different PP) and the aero row (defaults and ranges both moved).

### 1.2 The critical structural exploit: settings are free, parts are not

This is the foundation of every min-max build in GT7, and **it is a structural property of how PD account for PP rather than a physics value. It survives 1.71.**

> **Installing a part changes PP. Adjusting that part's sliders does not.**

- Fitting Fully Customisable Suspension costs PP (one observed case: **+9.1 PP**, 594.01 → 603.11 on a TVR Tuscan Speed 6 — **⚠️ v1.70, re-measure**). But every slider it unlocks — ride height, natural frequency/spring rate, dampers, ARBs, camber, toe — is **PP-free**. ([GTPlanet — Strange PP changes when changing parts](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/); [Doughtinator — Suspension](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/suspension))
- Fitting a Fully Customisable LSD costs PP. Initial torque / accel sensitivity / braking sensitivity are **PP-free**.
- Fitting a Fully Customisable transmission costs PP. The ratios you then choose are **PP-free**.
- Wing angle / downforce sliders on an installed wing: **PP-affecting but weakly and inconsistently** (see §1.4). Note that PP is reportedly calculated *from the default settings of adjustable suspension and diff*, not your chosen values. ([Coach Dave Academy — GT7 Tuning Explained, 2026](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/))

> **⚠️⚠️ That last sentence is the one line in §1.2 that 1.71 directly threatens, and it is worth pausing on.** If PP really is computed from the **default settings** of adjustable suspension and diff, then **1.71 changing those defaults changes PP even on a car whose parts and sliders you never touched.** That is a plausible mechanism for a build moving under a cap with no user action at all — and it is exactly why Job 4 reads the *current* number rather than reasoning about what should have changed.
>
> *(The claim is single-source and was never independently verified. Flag it as [CONTESTED] and let the audit settle it: if PP moved on a car whose parts are unchanged, this is the likeliest explanation.)*

**Therefore:** the correct build philosophy under a PP cap is to spend PP on the *hardware that unlocks free adjustment*, then extract lap time from the free sliders. A perfectly-tuned car and a default-tuned car with identical parts show the **same PP** and can be several seconds apart. In a no-BoP open-tuning league, setup skill is a completely unregulated performance axis.

### 1.3 What Update 1.49 actually changed

1.49 (July 2024) was **not a redesign of the PP formula**. It was a physics-engine overhaul, and because PP is simulation-derived, every car's PP was recomputed against the new physics. The stated 1.49 physics changes ([gran-turismo.com — Update 1.49](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)):

- Suspension geometry calculation improved → different cornering physics and accel/decel stability
- Steering geometry calculation improved
- Damper behaviour over bumps and kerbs refined
- Tyre model: low-speed cornering and kerb stability changed; **rolling/surface resistance "optimised"**; racing tyre heat and wear characteristics adjusted
- Wet grip and hydroplaning revised
- Default suspension and aero settings changed on race cars and some road cars
- Official note: *"Performance Points (PP) for all featured cars have been updated."*

> **⭐ Read that list beside 1.71's and the resemblance is the most useful thing in this section.** Steering geometry, damper behaviour, rolling resistance, tyre heat and wear, default suspension and aero settings, PP updated across the board — **1.71 hit the same six items.** The difference is that 1.71 *also* revised the **adjustment ranges**, which 1.49 did not say it did.
>
> **That makes 1.49's documented downstream effects the best available prior for what to expect from 1.71.** Read the three bullets below as a forecast, not as history — and note that none of them is a forecast anyone should act on before measuring.

Observed downstream effects on builds:

- **Engine-swapped cars were hit hardest.** Engine swaps *jumped* in PP. Documented example: a Lancer with the Escudo engine swap required **−80 hp** to come back to 600 PP. A rotary-swapped MX-5 took a "massive HP drop." ([GTPlanet — Update 1.49 thread, p.41](https://www.gtplanet.net/forum/threads/gran-turismo-7-update-1-49-eiger-nordwand-six-new-cars-physics-changes-more.427531/page-41))
- **Broadly, cars got faster under the new physics, so PP went up, so PP-capped builds had to be detuned** — meaning effective lap times at a given PP cap got *slower* for many cars. Documented: the Ford Mustang Gr.3 Road Car lost **83 hp** to sit at 700 PP; Mach Forty and Toyota Corolla MORIZO were heavily cut for WTC 600. ([GTPlanet — #StopNerfingCars](https://www.gtplanet.net/forum/threads/stopnerfingcars.427824/))
- **Some builds broke entirely** (no PP computable). Common triggers reported: Racing Soft tyres, carbon-ceramic brakes, Fully Customisable Suspension, superchargers, engine swaps, certain aero settings — disproportionately on classic American muscle (Superbird, Corvette C3, Camaro). Workarounds were per-car: step down a tyre grade, remove carbon brakes, change aero or suspension. ([GTPlanet — PP Issue!](https://www.gtplanet.net/forum/threads/pp-issue.427864/))

### 1.4 Post-1.49 changes (1.50 → 1.71)

- **1.55 (Jan 2025)** is the other update with a PP note: *"Performance Points (PP) for some cars have been updated."* It also changed tyre cornering-load dependency, wet racing-line grip, and off-track dirty-tyre penalties, plus default aero on Gr.1/race cars and default suspension/diff on some road cars. ([gran-turismo.com — Update 1.55](https://www.gran-turismo.com/us/gt7/news/00_3399040.html))
- **1.66 → 1.70 (2025–mid-2026)** are predominantly content updates (cars, events, engine swaps, the WEC Hypercar drop in 1.70, June 2026) plus repeated **"Power Pack" rival/performance rebalancing**. No documented PP-system overhaul. ([GTPlanet — GT7 game update tag](https://www.gtplanet.net/tag/gran-turismo-7-game-update/); [gran-turismo.com — Update 1.70](https://www.gran-turismo.com/us/gt7/news/00_1814793.html))
- **⭐ 1.71 (20 Aug 2026) — the fourth PP re-roll.** Performance Points adjusted across the game, driven by a physics rework of the tyre slipping model, per-car steering geometry, damper attenuation, and the defaults *and adjustment ranges* of suspension, differential and aerodynamics. Event regulations changed for the **Lightweight K Cup** and the **Power Pack Bump Drafting** event. PD also reset every ranking board in the game. ([Update Notice (1.71)](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html); full changelog in `16-update-1.71-physics-change.md`)

> **⚠️ Uncertainty flag — the original, kept verbatim because it was right:** *"an August 2026 update was teased at time of writing. Any physics touch re-rolls PP across the board. **A league must pin its ruleset to a game version and re-validate builds after every patch.** This is not optional in GT7 — it has happened at least three times since launch."*
>
> **⭐ It has now happened four times. The rule stands unchanged and is overdue for actual use — see §9.3 and `16` §12 Job 4.**

### 1.5 Which upgrades give the most performance per PP — the headline answer

**⚠️ The ranking is a reasoning-led structure and should survive; the illustrative PP numbers inside it are v1.70.**

Ranked best-to-worst value under a PP cap:

1. **Nitrous / Overtake system — reportedly adds *zero* PP.** ~100,000 Cr. per car, Extreme tab, output adjustable. If this holds in your game version it is the single most broken item in the parts catalogue for a PP-capped league. **Verify on your version, then ban it.** ⭐ *"On your version" now means v1.71 — re-verify during Job 4, then keep the ban.* ([DiamondLobby — GT7 tuning setups](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/))
2. **Free settings** (suspension, diff, gearing, brake bias, ARBs, camber, toe, fuel/power maps). Infinite lap time for 0 PP. This is where the real advantage lives. **⭐ And post-1.71 it is where the advantage is *largest*, because the entire community's setup knowledge just went stale at once and free sliders are the axis nobody can copy from a published tune.**
3. **Weight reduction Stage 1–2.** Cheap in credits, improves accel + braking + cornering simultaneously, and PP cost is modest relative to the three-way gain. Traditional community build order puts it second only to tyres.
4. **Parts that unlock free sliders** — Fully Customisable Suspension, Fully Customisable LSD, Fully Customisable Racing transmission. You pay a modest one-time PP toll for unlimited free tuning.
5. **Tyre compound** — the biggest raw lap-time step available, but also the biggest PP step. See §2.
6. **Peak power** — expensive in PP and heavily weighted by the PP sim. This is the *last* thing to buy, and the first thing to trim.
7. **Brakes** — cheap in PP, small but real lap time gain, near-free. Fit them.
8. **Body rigidity / roll cage** — *often lowers PP* (see §6.6). Effectively a negative-cost upgrade if the car responds well.
9. **Aero/wings** — inconsistent in both PP sign and lap-time benefit; test per car. **⚠️ 1.71 revised aero defaults and adjustment ranges on race cars — the inconsistency now has a new shape.**

**On aero specifically:** independent testing found GT7 aerodynamics have startlingly small lap-time effect — a car with ~1,300 lbf of downforce lapped only **0.1 s** faster than a no-aero baseline, and the **no-aero build was 524 PP against 545 PP for the street-aero build**, i.e. the aero build paid 21 PP for 0.1 s. The same source notes GT7 downforce figures are quoted at roughly **130 mph / 210 kph**, and that dividing total (front + rear) downforce by ~900 approximates a lift coefficient. ([Occam's Racer — GT7 Aerodynamics](https://occamsracers.com/2024/04/19/gt7-aerodynamics/))

Contradicting this, other players report **reducing rear downforce by ~50% *increased* PP by ~10** on some cars — the sim rewarding the resulting higher top speed. ([GTPlanet — Tuning system is completely broken in GT7](https://www.gtplanet.net/forum/threads/tuning-system-is-completely-broken-in-gt7.406139/page-2))

> **Flag:** the sign of the aero→PP relationship is car-dependent and not reliably predictable. Test it directly on each build. But the general finding — *aero costs more PP than it delivers lap time on most road cars* — is well supported.
>
> **⭐ 21 Aug: and 1.71 gave aero a fresh set of defaults and endpoints on race cars, so both the sign and the magnitude need re-testing per build. Press Triangle after every aero change — the habit was already correct and is now mandatory.** Note the interaction with `11-car-slider-ranges.md`: if the downforce span moved, a "click" of wing is a different amount of downforce than it was, which changes both the lap time and the PP it buys.

---

## 2. Tyre Compound vs PP

### 2.1 The compound ladder

Comfort Hard → Comfort Medium → Comfort Soft → Sports Hard → Sports Medium → Sports Soft → Racing Hard → Racing Medium → Racing Soft, plus Racing Intermediate and Racing Wet, plus Dirt/Snow.

### 2.2 PP cost

**Tyres are the largest single PP step in the game**, because the PP sim heavily weights lateral G, and compound is the only thing that changes lateral G by a step function.

Concrete measured example: on a TVR Tuscan Speed 6, going from stock tyres to **Sports Soft cost +27.5 PP** (566.51 → 594.01) — **⚠️ v1.70**. ([GTPlanet — Strange PP changes when changing parts](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/))

> **Uncertainty flag — this is important and I will not invent numbers.** There is **no publicly verified table of PP-per-compound-step**. The cost is not constant: it scales with how much grip the compound actually unlocks on *that* car (mass, power, downforce, drivetrain), so a heavy, high-downforce car pays a different toll than a light one. As a working planning heuristic derived from the one solid data point and community reports, **a single compound step commonly lands somewhere in the ~10–30 PP range**, with steps inside the Racing family (RH→RM→RS) generally cheaper than steps that cross a family boundary (SS→RH). **Measure it on your car; do not plan a build against an assumed constant.**
>
> **⭐ 21 Aug — and 1.71 gives a specific reason to expect this to have moved.** The PP cost of a compound step is a function of *how much lateral G that step unlocks*, and 1.71 changed the tyre model. **If the compounds' relative grip changed, their relative PP cost changed with it.** The instruction is unchanged — measure on your car — but the ~10–30 PP band should now be treated as a v1.70 band rather than a current one.

Also note: **the PP system includes tyre compound at all** is itself a design choice that many experienced hosts consider a mistake, precisely because it lets builders arbitrage grip against power. ([GTPlanet — PP Racing and Tuned road cars](https://www.gtplanet.net/forum/threads/pp-racing-and-tuned-road-cars.424806/))

### 2.3 When to spend PP on tyres vs power

The trade is: **a compound step buys you cornering speed everywhere; the equivalent PP in power buys you speed only where the throttle is open.**

Buy the softer tyre when:
- The track is **corner-dense** (Tsukuba, Suzuka East, Autopolis, Dragon Trail Gardens, Deep Forest, most Circuit Experience layouts). Grip compounds over many corners; power does not.
- The car is **low-powered relative to its chassis** — a light, well-balanced car with modest power converts grip to lap time extremely efficiently.
- The race is **short / no tyre wear** or wear multiplier is low. Softs' PP cost is fixed, but their lap-time benefit decays with wear.
- You are **traction-limited** on corner exit (high-torque RWD). Grip here pays twice: cornering *and* acceleration.

Buy the power instead when:
- The track is **straight-dominated** (Le Mans, Special Stage Route X, Monza, Daytona Road, High Speed Ring, Tokyo Expressway).
- The race is **long with high tyre wear** — you are paying full PP for softs and then throwing the advantage away over a stint, or pitting more.
- The car already has **abundant grip** (high downforce, AWD, low mass) and is power-limited.

**The stint-length caveat that decides most endurance builds:** a soft tyre's PP cost is charged at the start line and never refunded. Over a long stint the compound's advantage bleeds away, but the power you *didn't* buy is gone for the whole race. For long-format league races, **harder tyre + more power is usually the correct arbitrage**; for sprints, **softer tyre + less power**.

> **⚠️⚠️ 21 Aug — this whole section is downstream of the wear model, and the wear model is unmeasured on v1.71.** Every "buy the softer tyre when… the race is short / wear is low" clause depends on knowing how fast the compound decays. **`03`'s exposure banner voids all of that, and `08` C3.1 records what happened the last time a compound was chosen from a modelled wear figure: the Laguna race was built around Racing Hards it did not need, at a cost of ~28 seconds.**
>
> **The instruction that supersedes this section until Job 2 comes back: measure one stint at the multiplier you will actually race, then choose the compound, then price the PP.** In that order.

**League note:** locking the compound (see §9) removes this entire axis and is by far the most effective single levelling tool available to a host. **⭐ And post-1.71 it also removes the axis nobody can currently reason about, which is a second argument for it this month.**

---

## 3. Power Tuning — every path, and what it does to the *curve*

> **⚠️ 1.71 introduced a new engine torque control map** (the notes cite improved throttle control when drifting and improved car speed control on partial throttle), **and adjusted maximum RPM on six race cars** — Lexus RC F GT500 '16, Nissan GT-R NISMO GT500 '16, Super Formula SF19 Honda and Toyota, Super Formula SF23 Honda and Toyota. **None of our three cars is on that list.**
>
> **This section is about the *shape* of the torque curve, so a new torque control map is directly relevant to it.** The parts catalogue and the qualitative curve-shaping descriptions should survive; §3.3's PP quirk — that the sim penalises a badly-distributed powerband — is a property of the evaluation and should also survive. **What needs re-checking is whether a given part still shapes the curve the same way, and §3.1's efficiency ranking.**

### 3.1 The catalogue

Sorted by tuning-shop tab (Sports → Club Sports → Semi-Racing → Racing → Extreme):

**Intake / exhaust / ECU (small, linear, efficient)**
- **Sports / Racing Air Filter** — small broad gain across the range. Cheap in credits (Sports Air Filter ~600 Cr.) and cheap in PP. Efficient.
- **Sports / Semi-Racing / Racing Exhaust (Muffler)** — small-to-moderate broad gain, weighted slightly to the top end as you go up the tiers. Efficient.
- **Racing Exhaust Manifold** — moderate gain, mostly mid-to-top. Efficient.
- **Sports / Sports-Cat / Racing Catalytic Converter** — small broad gain.
- **Sports Computer / Full Control Computer (ECU)** — the Sports ECU is a small flat gain. **The Full Control Computer is the important one: it unlocks the Output Adjustment slider** (see §4). Fit it on any car you intend to trim to a cap.
- **Racing Intercooler** — small gain on forced-induction cars. Measured: **+3.03 PP** (598.35 → 601.38) on one car — genuinely small. **⚠️ v1.70.** ([GTPlanet](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/))

**Internals (moderate, curve-shaping)**
- **Engine Balancing / Tune-Up** — raises the rev ceiling slightly and cleans up the top end.
- **High-Lift Camshaft** (and **High Lift Camshaft S**, special part) — shifts the curve **up the rev range**. Gains top-end power, can *cost* low-end torque. Bad for driveability on a torque-reliant car; good on a high-revving NA engine.
- **Racing Crankshaft** — raises rev limit / improves response.
- **Titanium Racing Con-Rods & Pistons** (special) — **raises the rev limit**, which is what actually lets a high-RPM turbo deliver boost over a wider band. This part is a *force multiplier* for high-RPM forced induction, not a standalone power part.
- **Bore Up / Stroke Up** (and **Bore Up S / Stroke Up S**) — displacement increase. **Stroke Up broadens low-end torque; Bore Up favours top-end.** These are the most driveability-friendly big power adds on an NA car: they lift the *whole* curve rather than peaking it.

**Forced induction (large, curve-destroying if chosen badly)**
- **Turbocharger: Low RPM / Medium RPM / High RPM / Ultra-High RPM** (Ultra-High is a special/roulette part, purchasable at Collector Level 50 since 1.34).
- **Supercharger: Low-End Torque / High-End Torque variants** (and **High-RPM S Supercharger**, special).
- **Anti-Lag System** — toggleable; keeps the turbo spooled.

**Extreme**
- **Nitrous / Overtake System** — ~100,000 Cr., adjustable output vs depletion rate. **Reportedly adds no PP.**
- **Engine Swap** — see §7.
- **New Engine / New Body** — a full reset, useful for undoing permanent modifications (see §5).

Sources: [SimRacingSetup — GT7 Tuning Shop guide](https://simracingsetup.com/gran-turismo/how-to-upgrade-your-car-in-gran-turismo-7/); [DiamondLobby](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/); [GTPlanet — Special/Ultimate Parts](https://www.gtplanet.net/forum/threads/special-ultimate-parts.405370/)

> **Uncertainty flag:** there is **no published per-part PP cost table**, and there cannot be a universal one — PP is simulated, so the same part costs different PP on different cars. The only exceptions worth stating with confidence are the two extremes: **nitrous ≈ 0 PP** and **intercooler ≈ +3 PP** on the one measured case. **⚠️ Both v1.70.**

**⭐ Engine swaps, 1.71 additions.** Ten cars gained engine-swap availability at Collector Level 50: Mercedes-Benz 300 SEL 6.8 AMG '71, Mercedes-Benz SLS AMG '10, Caterham Seven Superlight R500 '08, Ford Focus RS '18, Gran Turismo Red Bull X2014 Junior, Mitsubishi Lancer Evolution IX MR GSR '06, Porsche 911 GT3 (996) '01, Suzuki Swift Sport '07, Toyota Chaser Tourer V '97, Toyota Mark II Tourer V '97. **The Evo IX and the Focus RS are the two worth a league organiser's attention — both are the AWD-plus-swap archetype §8.3 and §9.1 identify as the most under-rated category in the game.** See §7.

### 3.2 Turbo choice — the driveability decision

The four turbo variants trade spool speed against peak boost:

| Variant | Spool | Curve shape | Best for |
|---|---|---|---|
| **Low RPM** | Fastest | *"Spools up quicker giving more lower end grunt"*, power jumps earlier in the rev range | Technical tracks, frequent downshifts, low-speed corner exits |
| **Medium RPM** | Moderate | *"The balanced one"* | Default choice; most circuits |
| **High RPM** | Slow | *"Takes more revs to full spool but once she is she puts out more power"* — builds slowly, peaks higher | Long-straight tracks: Le Mans, Monza, Spa, SSRX |
| **Ultra-High RPM** | Slowest | Highest peak, narrowest usable band | Top speed builds only |

([GTPlanet — Turbo RPM variations](https://www.gtplanet.net/forum/threads/can-someone-explain-the-benefits-of-different-turbo-rpm-variations.406714/))

**The parts that ruin driveability:**
- **High / Ultra-High RPM turbos on a car with a low rev ceiling.** You get a violent, narrow power spike near the limiter, huge off-boost lag, and an unmanageable throttle map. On RWD with racing tyres this is a snap-oversteer generator.
- **High-Lift Camshaft on a torque-dependent engine** — hollows out the mid-range you were relying on.

**The mitigations:**
- **Titanium Con-Rods & Pistons** raise the rev limit, widening the band a high-RPM turbo can actually use. Fit these *before* going Ultra-High RPM.
- **Anti-Lag** keeps the turbo lit and, per community consensus, *"negates a lot of the advantages of the low and mid tier turbos,"* making **high-RPM turbo + anti-lag** the strongest overall competitive combination. ([GTPlanet](https://www.gtplanet.net/forum/threads/can-someone-explain-the-benefits-of-different-turbo-rpm-variations.406714/))
- **Fully Customisable transmission** — with free gear ratios you can gear *around* a narrow powerband, keeping the engine inside the boost window. This is the free-slider exploit applied to power delivery.

> **⚠️ 1.71's new torque control map is described as improving "car speed control on partial throttle."** If partial-throttle delivery genuinely became more linear — one community report says *"throttle feels and looks a lot more linear"*, single-source and unverified — **then the driveability penalty of a peaky turbo may be smaller than it was**, which would make the §3.3 exploit better rather than worse. **Untested. Do not build a season on it.**

### 3.3 The PP quirk that matters most here

**A worse powerband can be worth *more* peak power at the same PP.** Community observation: *"Ultra-high RPM turbos"* produce higher peak power but **lower** PP than medium-RPM alternatives, because the PP sim penalises a poorly-distributed powerband — it measures acceleration through the sim's shift points, not peak hp. Similarly, *"excess power without control"* rates lower than deliverable power. ([GTPlanet — Why does PP go down when you do this?](https://www.gtplanet.net/forum/threads/why-does-pp-go-down-when-you-do-this.419649/))

**This is a first-class exploit.** Fit the peaky, high-RPM setup — which the PP sim rates poorly because *its* driver model can't use it — then use free gear ratios and your own throttle control to actually use it. You bank the peak power at a PP discount. The Suzuki Escudo with High RPM Turbo at 799 PP is the canonical example: described as *"the fastest cheat car,"* able to run with Gr.2 machinery.

**This is a property of the evaluation's driver model rather than of the physics values, so it should survive 1.71 — but the *magnitude* of the discount is a v1.70 observation and the sim now runs on different physics. Re-check on any build that depends on it.**

**Efficient power parts (best hp per PP, best driveability):** air filter → exhaust → manifold → ECU → intercooler → stroke up → medium turbo.
**Inefficient / risky:** ultra-high-RPM turbo without rev-limit support, high-lift cam on a torquey engine, big supercharger on a light RWD chassis (also implicated in the post-1.49 no-PP bug).

---

## 4. Power Restrictor vs ECU Output Adjustment

These are **not the same tool** and the difference decides how you trim to a cap.

> **⭐ This section has a live, measured in-house consequence that goes well beyond PP — see `08` D3.1.** A restrictor cuts top-end while largely preserving low-end torque, so **a restricted car delivers proportionally more torque in the early corner-exit phase than its headline power implies** — which on an MR car with TCS 0 produces power-on understeer, and which made an LSD accel value of 18 badly too much lock on the Huracán at Laguna. **14 fixed it.**
>
> **⚠️ That finding was measured on v1.70, and 1.71 introduced a new engine torque control map. The reasoning holds; the number 14 needs re-establishing.** And add a fourth standing rule to D3.1's three: **re-test LSD acceleration sensitivity after a physics update, not just after a restrictor change.**

### 4.1 Mechanism

| | **ECU Output Adjustment** (needs Full Control Computer) | **Power Restrictor** (Performance Adjustment) |
|---|---|---|
| What it models | Electronic power limit across the **full RPM range** | An **airflow restriction** at the intake |
| Effect on curve | *"Decreases power and torque proportionally across the whole RPM range"* — the curve is scaled down uniformly, keeping its **shape** | *"More effects top end horsepower, but lower end torque remains less affected"* — the curve is **squashed at the top**, low-end largely preserved |
| Torque at a given peak hp | **Less** usable torque | **More** usable torque |
| Fuel consumption | **Better** (genuinely reduces engine output) | **Worse** relative to ECU at the same hp |
| PP reduction efficiency | Reduces PP **more** per unit of hp removed | Reduces PP less per unit of hp removed |

Sources: [Doughtinator — ECU and Performance Adjustment](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/ecu-and-performance-adjustment); [GTPlanet — Output Adjustment vs Power Restrictor](https://www.gtplanet.net/forum/threads/whats-the-difference-between-output-adjustment-and-power-restrictor.410141/); [Coach Dave Academy](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)

Restated plainly: **the restrictor takes the top off the curve; the ECU shrinks the whole curve.**

**The mechanism is a description of what the two tools do to a torque curve and should survive 1.71. The fuel-consumption row is the exposed one — 1.71 optimised rolling resistance, which moves L/lap independently of engine output.**

### 4.2 Which is better for trimming to a PP cap?

**It depends on which side of the trade you want, and the answer is not universal.**

- **For raw performance at a given PP:** the **Power Restrictor** generally leaves more usable torque, so the car is quicker out of corners and in the mid-range for the same headline hp. Direct comparison testing on SSRX found the restrictor gave *"slightly better performance"* than the ECU. ([GTPlanet — Best way to lose 20PP](https://www.gtplanet.net/forum/threads/best-way-to-lose-20pp-and-the-winner-is.409458/))
- **For maximum PP reduction per unit of pain:** the **ECU** reduces PP more aggressively — you shed more PP for less absolute power loss because the PP sim weights top-end and top speed so heavily.
- **For endurance / fuel-limited races:** the **ECU** wins clearly. Same test: ECU reduction gave *better fuel economy* than the restrictor at the same power. Over a long stint that is worth more than the mid-range torque.

**The magnitudes are large.** One measured case: moving the ECU from **100 → 99** (a 1% cut) removed **14.32 PP** (601.38 → 587.06) — **⚠️ v1.70**. ([GTPlanet](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/))

> **Flag:** a 1%-for-14-PP ratio is extreme and clearly not universal — it was measured on one specific car near a threshold. But it demonstrates the key practical point: **PP response to power is steeply non-linear and can be near-discontinuous.** Never assume linearity when trimming.
>
> **⭐ And that non-linearity is exactly why a fleet-wide PP re-roll can move a build a long way for no apparent reason. A car sitting near one of these thresholds on v1.70 may have crossed it.** Read the number; do not reason about it.

### 4.3 Recommended practice

1. **Build the car over the cap deliberately**, with the parts you want (which unlock free sliders and the right power curve shape).
2. **Trim with the restrictor first** — it preserves the mid-range you actually drive on.
3. If the restrictor alone can't reach the cap, or the race is fuel-critical, **switch to or add ECU reduction**. The two stack.
4. **Fine-tune the last 1–3 PP with ballast**, which is the least performance-destructive tool (§5.3).
5. If you find yourself *far* over the cap, **remove a part** rather than restricting heavily — a heavily-restricted big engine is worse than an unrestricted right-sized one, because you paid PP for peak power the restrictor then deleted.
6. **⭐ NEW — re-test LSD acceleration sensitivity after any restrictor change, and after any physics patch.** Treat it as part of the same job as re-gearing. `08` D3.1.

---

## 5. Weight

### 5.1 Weight Reduction stages

Six stages, all **permanent and irreversible** (only a "New Body" purchase from the Extreme tab resets them):

| Stage | Where |
|---|---|
| Stage 1 | Sports tab (~3,000 Cr.) |
| Stage 2 | Club Sports tab |
| Stage 3 | Semi-Racing tab |
| Stage 4 | Racing tab |
| Stage 5 | Special part — roulette (3★) / purchasable at Collector Level 50 |
| Stage 6 | Special part — roulette (4★) |

([DiamondLobby](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/); [GTPlanet — Special/Ultimate Parts](https://www.gtplanet.net/forum/threads/special-ultimate-parts.405370/))

> **Uncertainty flag:** the **kg or % removed per stage varies per car and is not published**. Read the in-game preview before purchasing — it shows the resulting weight.

> **⭐ 21 Aug — and note the irreversibility point in a patch context.** §5.2 point 2 warns that over-stripping a car loses tuning range you cannot get back. **A fleet-wide PP re-roll is exactly the scenario that warning was written for: if 1.71 pushed a build over its cap, an over-stripped car has fewer ways to come back down.** Do the Job 4 audit before buying any further weight reduction.

### 5.2 Is weight reduction always desirable?

**No.** Three reasons, in increasing order of importance:

1. **It costs PP.** Lower weight improves accel, braking and cornering simultaneously, so the PP sim charges for all three. In a PP-capped class you are paying real PP for it.
2. **It is irreversible.** If you over-strip a car you cannot undo it without buying a New Body. In a league where you may need to fit under multiple caps across a season, an over-stripped car has lost tuning range.
3. **It changes balance in ways you may not want.** Stripping mass generally removes it unevenly and reduces the car's polar moment, making it more responsive and *more nervous*. On a car that was already loose (rear-engined 911s, mid-engined cars, high-power RWD) the stripped car can be harder to drive despite being "better" on paper. GT7's PP sim also reads a lighter car as faster, so you pay for the nervousness.

**Also note:** more weight **increases tyre degradation**, which matters enormously in endurance formats — this argues for weight reduction in long races even at PP cost, because the alternative (ballast to trim PP) worsens wear. **⚠️ The size of that effect depends on the wear model, which is unmeasured on v1.71.**

**Recommended default:** **Stage 1–2 on almost everything** (excellent PP-to-benefit ratio, moderate balance disruption). **Stages 3+ only when you've confirmed the car tolerates it** and you actually need the accel/braking. Stages 5–6 are for extreme builds and are effectively irreversible commitments.

### 5.3 Ballast — mass and position

**Ballast Weight:** 0 to **200 kg**, adjustable **1 kg at a time**.
**Ballast Position:** **−50 (fully forward) to +50 (fully rearward)**, 0 = neutral.
Both live under **Performance Adjustment** (Club Sports tab). Removable, reversible, free to change.

([Doughtinator — ECU and Performance Adjustment](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/ecu-and-performance-adjustment); [Gamepur — how to lower PP](https://www.gamepur.com/guides/how-to-lower-pp-performance-points-in-gran-turismo-7))

> **⚠️ 1.71 note: these are *adjustment ranges*, and 1.71 revised adjustment ranges for suspension, differential and aerodynamics — ballast is not named in that list.** So 0–200 kg and −50…+50 are probably intact. **"Probably" is not "verified": confirm both while doing the Job 4 audit, since the screens are already open. It costs five seconds and `11-car-slider-ranges.md` exists because assuming a range is the exact error that keeps recurring.**

**PP cost of ballast:** the best public data point is a controlled test on the Aston Martin DP-100: **200 kg of ballast reduced PP by ~20 points** while having *"almost no impact to performance (max speed) or fuel economy."* **⚠️ v1.70.** ([GTPlanet — Best way to lose 20PP](https://www.gtplanet.net/forum/threads/best-way-to-lose-20pp-and-the-winner-is.409458/))

> **Critical caveat on that test, raised in the same thread and worth repeating loudly:** it was run on **SSRX — a straight-line oval.** Of course 200 kg cost nothing there. On a real circuit, 200 kg destroys braking, turn-in, and tyre wear. **Ballast is not a free PP reduction; it is a PP reduction that costs you almost nothing on straights and a lot in corners.** Use small amounts for fine-tuning; do not use 200 kg as a strategy on a corner-heavy track.

**Rule of thumb from the data point:** roughly **10 kg ≈ 1 PP** on a heavy hypercar. Expect a *steeper* PP-per-kg on light cars (a lighter car's power-to-weight moves further per kg). **Measure it.**

### 5.4 Ballast position and weight distribution — the actual effect

**What the game shows you:** GT7 displays **front/rear weight distribution as a percentage pair** (e.g. 56/44) and updates it live as you move the ballast position slider. Use the readout — do not guess.

**How much ballast shifts distribution by 1%?**

> **Flag: there is no verified published constant, and there cannot be one.** The relationship is non-uniform and depends on (a) the car's total mass, (b) how much ballast is fitted, and (c) the starting distribution. The clearest community statement of the dependency: *"the lower the weight / more weight lost, the less clicks you have to move to shift 1 percent of distribution."* The position slider is quantised finely enough that the displayed integer percentage rounds (48.4 displays as 48; 48.5 as 49). ([GTPlanet — Ballast question](https://www.gtplanet.net/forum/threads/ballast-question.323207/) — GT6-era thread; GT7 behaves the same way in the UI, but **treat this specific source as carried-over rather than GT7-verified**.)

**A first-principles estimate you can sanity-check against the in-game readout:**

For a car of mass *M* with rear weight fraction *r*, adding ballast mass *m* at the fully-rearward position (approximately over the rear axle):

```
new rear fraction ≈ (r·M + m) / (M + m)
```

Worked example: 1,400 kg car at 50:50, +100 kg fully rear → (700+100)/1500 = **53.3% rear**, i.e. ~3.3 points from 100 kg → **roughly 1% of distribution per ~30 kg at full rear** on a car of that mass. A 1,000 kg car: (500+100)/1100 = 54.5% → ~1% per ~22 kg. A 1,800 kg car: ~1% per ~39 kg.

**Use this only to know what order of magnitude to reach for; read the exact value off the game's display.** **⭐ This one is arithmetic and is the single most patch-proof paragraph in the document.**

**Handling effect of ballast position:**
- **Rearward ballast (+):** increases rear grip under acceleration (better traction out of corners for RWD), but causes **over-rotation off-throttle and on corner entry** — the car pivots. Also worsens braking stability.
- **Forward ballast (−):** loads the front, sharpens turn-in, and **reduces rear-engine oversteer** — the standard fix for a tail-happy 911 or a mid-engined car that snaps. Costs corner-exit traction.
- One documented practical build: fit **Weight Reduction Stage 1**, then **add ballast back up to the stock kerb weight, placed fully rearward** — which cured a car that was *"excessively unstable during braking."* This is a neat trick: you get the *distribution* control without the *net weight* penalty, at whatever PP the Stage 1 + ballast combination nets out to. ([GTPlanet — Weight and weight distribution](https://www.gtplanet.net/forum/threads/weight-and-weight-distribution.428334/))

**The important counter-argument:** 50:50 is not automatically the target. As an experienced tuner put it, *"50:50 would only be ideal if the car is designed around this weight distribution."* Moving distribution away from factory without re-tuning springs, dampers and ARBs to suit will usually make the car worse, not better. **Ballast position is a suspension-tuning tool and must be tuned alongside the suspension, not instead of it.**

> **⭐ And on v1.71 that coupling cuts the other way too:** the suspension you would re-tune it alongside has revised defaults and ranges, and per-car steering geometry moved. **Do the ballast sweep after the range re-read (Job 1), not before it.**

### 5.5 The ballast PP exploit

**Ballast *position* — which barely changes the car physically — can cause disproportionate PP swings.** Community reports describe *"drastic"* PP changes from small position moves, attributed to the simulation's **"High Speed Rotational G"** measurement: shifting mass changes the car's yaw response in the sim's stability test, and the sim over-weights that result.

The practical form of the exploit: *"the PP numbers can reduce greatly by simply moving the Ballast positioning forwards by a few points"* — so **combine forward ballast with extra power or extra front downforce to maximise performance within a PP limit.**

([GTPlanet — Why does PP go down when you do this?](https://www.gtplanet.net/forum/threads/why-does-pp-go-down-when-you-do-this.419649/); [Doughtinator](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/ecu-and-performance-adjustment))

**This is the single most reliable fine-tuning exploit available, and league organisers should know it exists.** Sweep the ballast position slider from −50 to +50 in small steps on any completed build and record PP at each step; you will frequently find several free PP sitting at a position that is also *good* for the car.

> **⭐ 21 Aug — this exploit is a *mechanism* (the sim over-weights high-speed rotational G) and should survive, but the map has certainly changed.** The sim's yaw-stability test now runs on reworked steering geometry and a changed damper model, so **where the free PP sits along the slider is a new question on every car.** The sweep is the same five minutes it always was, and it is worth redoing on any build that is now near its cap. **If a build came out of the patch over the cap, this is the first place to look for the points back** — before touching the restrictor, and long before removing a part.

---

## 6. Drivetrain and Chassis Upgrades

### 6.1 Brakes

Four tiers (Brembo-licensed):

1. **Sports Brake Pads** — entry level; consistent friction to ~600°C, stable when cold, no warm-up needed.
2. **Sport / TY3 Brake Discs** — Type-3 baffled discs; *"improves performance consistency, and increases brake modulation, ensuring more responsive and repeatable braking."*
3. **Racing Caliper Kit** — BM-series monoblock aluminium calipers, 4–8 opposed pistons, slotted or drilled discs; *"greater braking torque and a more responsive, stable braking performance."* Caliper colour customisable in GT Auto.
4. **Carbon-Ceramic (CCM-R) Discs** — big unsprung weight saving, no warping at high temperature, reliable in the wet.

([Brembo — GT7 brake tuning guide](https://www.brembo.com/en/live-our-energy/gaming/gt7-tuning); [Traxion — Brembo partnership](https://traxion.gg/new-gran-turismo-7-tuning-options-revealed-in-brembo-partnership-announcement/))

**PP verdict:** brakes are **cheap in PP** for the lap time they return, and community build orders consistently list them as an early buy. **Fit them on essentially every build.**

**Three caveats:**
- Don't over-buy. As one guide puts it, *"if your car is only peaking at around 120 MPH, then it is best to just go for the Sports Brake Kit"* — carbon-ceramics on a slow car is PP spent on braking capacity the tyres can't use.
- **Carbon-ceramic brakes were one of the components implicated in the post-1.49 "no PP value" bug.** If a build loses its PP number, the carbon brakes are one of the first things to swap out. **⭐ Keep this to hand — 1.71 is the same class of event as 1.49, and this is the first thing to try if a car comes back with a warning triangle.**
- **Brake balance is adjustable during a race via the MFD and costs zero PP** *(believed free — never actually tested; `08` Part G item 12, two minutes to close)*. **⚠️ And 1.71 adjusted ABS slip-ratio control and cornering brake behaviour, so what a click of bias *does* has changed even though what it costs has not.**

### 6.2 Clutch, Flywheel, Propeller Shaft

- **Racing Clutch / Sports Clutch** — reduces rotational inertia; faster rev pickup and shifts.
- **Racing / Lightweight Flywheel** — lower rotational inertia; faster engine response, but a light flywheel makes the car more prone to bogging or stalling out of slow corners and can make throttle modulation twitchier.
- **Carbon Propeller Shaft** (special part, roulette / CL50) — reduces driveline rotational mass.

These are **small, cheap PP additions with small but genuine gains**, and their benefit is in *response* rather than peak numbers — which the PP sim measures only partially. **Reasonable value; fit them on serious builds.**

> **Flag:** I could not find controlled measurements of their individual PP cost. Expect single-digit PP each; verify in the garage.

### 6.3 Transmission

Five types:

| Type | Description |
|---|---|
| **Normal** | Stock |
| **Close Ratio Low** | Fixed close-ratio set with low overall gearing — short tracks |
| **Close Ratio High** | Fixed close-ratio set with high overall gearing — short tracks, higher top speed |
| **Fully Customisable Manual** | Fully adjustable; supports clutch + H-pattern shifter, or manual shift delay with paddles |
| **Fully Customisable Racing** | Fully adjustable; paddle/button shifting only, **very quick gear changes** |

([Doughtinator — Transmission](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/transmission))

**PP behaviour:** installing an upgraded transmission **changes PP**. But *"for customisable gear ratios, the exact ratios and top speeds that are used has no effect on your car's PP rating."*

> **Conflicting evidence flag.** One source states gearing has **zero** PP effect; another reports gear changes moving PP by **±1 point**, and documents a historical bug where changing 6th gear from **2.082 to 2.081** swung PP from **696.88 → 738.32** (a 41-point jump) — attributed to the car crossing a **150 mph threshold** in the simulation's stability test. ([GTPlanet — Tuning system is completely broken](https://www.gtplanet.net/forum/threads/tuning-system-is-completely-broken-in-gt7.406139/page-2)) **That specific bug is from 2022 and is very likely patched, but the underlying lesson stands: the PP sim has discrete thresholds, and gearing can push a car across one.** If a build's PP jumps inexplicably, check whether gearing changed its simulated top speed.
>
> **⭐ 21 Aug — and 1.71 gives that lesson a new route to bite.** *"Road surface resistance (rolling resistance) has been optimised"* changes the top speed a given gearbox actually reaches. **A build whose simulated top speed sat just under a threshold may now sit just over it, with no gearing change at all.** If a car's PP moved unexpectedly and its parts are unchanged, this is the second thing to check after §1.2's defaults-based mechanism.

**Recommendation:** **Fully Customisable Racing** on nearly every competitive build. Free ratios are the primary tool for making a peaky, PP-discounted power curve driveable, and the fast shifts are worth real time. Use Fully Customisable Manual only if the driver runs a clutch and H-pattern.

**Gearing method:** a **long 1st gear** (especially with high power, to control wheelspin), a **short final/top gear** so you actually reach the limiter at the end of the longest straight, and **progressively decreasing spacing** between ratios. Check the achievable top speed in each gear against the track. **⭐ Re-gear on v1.71 regardless of anything else — rolling resistance changed. `08` A6.**

### 6.4 Suspension — which type unlocks which sliders

**This matters more than almost anything else in the build, because the sliders are free.**

| Type | Adjustable |
|---|---|
| **Normal** | Nothing (standard production suspension) |
| **Street** | Nothing (slightly lower/stiffer than Normal) |
| **Sports** | Nothing (slightly lower/stiffer than Street) |
| **Height-Adjustable Sports** | **Ride height, damping, natural frequency, camber angle** |
| **Fully Customisable** | **Everything** — including extended ride-height range, anti-roll bars, toe angles; stiffest defaults |

([Doughtinator — Suspension](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/suspension))

**All racing (Gr.) cars ship with Fully Customisable Suspension as standard.**

**Pairing guidance:** Normal/Street/Sports suspension pairs with Comfort or Sports tyres. **If you are on Racing tyres you should be on Height-Adjustable Sports or Fully Customisable** — the fixed setups cannot control the grip.

**PP:** installing the part costs PP (one observed case **+9.1 PP** — **⚠️ v1.70, re-measure during Job 4**). **Every setting it unlocks is PP-free.** This is the highest-leverage purchase in the game for a PP-capped league.

**Typical slider ranges you unlock** (from a current cheat-sheet — car-class dependent): natural frequency ~1.40–3.30 Hz on a sports road car; ride height e.g. 80–180 mm on a lightweight road car; anti-roll bars on a universal 1–10 scale; dampers roughly compression 20–40 / expansion 30–50 as a working baseline; camber typically −0.8° to −2.5° depending on compound; toe baselines around front 0.00° / rear +0.05°. ([Flux89 — GT7 Tuning Cheat Sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet))

> **Flag:** those are starting-point ranges from one guide, not universal truths. Note also that GT7 uses **natural frequency (Hz)** rather than raw spring rates.
>
> **⚠️⚠️ 21 Aug — this paragraph is now actively misleading and should not be used.** 1.71 states in the official notes that **initial suspension settings and adjustment ranges have been revised**, and the ranges above are third-party v1.70 figures that were never verified against our own cars anyway. **`11-car-slider-ranges.md` is the authority for our three cars, it is being re-read, and its measured Gr.3 figures already differed from this cheat-sheet by wide margins** (toe ±1.00° not ±0.50°; camber 0.0–6.0° not −0.8 to −2.5°). **Use the register, not this row.**

### 6.5 Differential (LSD)

Progression:
1. **One-Way LSD** — fixed, non-adjustable
2. **Two-Way LSD** — adjustable
3. **Fully Customisable LSD** — full access: **Initial Torque, Acceleration Sensitivity, Braking Sensitivity** (5–60 on v1.70; 0–30 / 0–100 / 0–100 on v1.71)
4. **Active LSD Controller** — on compatible cars

**PP:** installing costs PP; **the settings are PP-free.** ([DiamondLobby](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/); [Coach Dave Academy](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/))

**Tuning direction:** high values = more locked; low = more open. The standard approach is *"as high as you're comfortable with for acceleration"* and *"as low as you can manage for braking."* A typical FR baseline: initial torque 5, acceleration 25, braking 10 (v1.70 5–60 scale - a direction only on v1.71's 0–30 / 0–100 / 0–100).

> **⚠️⚠️ 21 Aug — the 5–60 scale may no longer be 5–60.** 1.71: *"Initial differential gear settings and adjustment ranges have been fixed."* **[COMMUNITY — single source]** One GTPlanet player reports the Fully Customisable Diff can now be set to **0/0/0**, which was never previously possible in the series.
>
> **If confirmed, a genuinely open differential is buildable for the first time**, and every LSD baseline in this knowledge base is written against a floor that no longer exists. `03` §8.5, `04` §2.5 and `08` B1 all assume 5. **Confirm on the settings screen — `16` §12 Job 1 — before it changes a single setup.**

> **Historical bug worth knowing:** on a TVR Tuscan Speed 6, fitting the Fully Customisable LSD dropped PP by **−139.74** (603.11 → 463.37), and an LSD setting of 10/51/20 (v1.70-era scale) took it to **−143.09** (603.11 → 460.02) — the car was massively under-rated while being *faster*. The bug was described as *"very simple but incredibly hard to recreate."* ([GTPlanet](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/)) **Almost certainly patched — but this class of bug recurs after every physics change.** A league should have a rule for it (see §9).
>
> **⭐ And note the specific relevance now: that bug involved LSD *settings* moving PP, which they are not supposed to do at all.** 1.71 revised the diff's defaults and ranges. **If PP is really computed from the *default* diff settings (§1.2), a changed default is a changed PP on every car with an adjustable diff fitted.** This is the most likely single explanation for unexpected PP movement on our three cars, all of which run Fully Customisable LSDs.

### 6.6 Body Rigidity and Roll Cage

- **Increase Body Rigidity** — Semi-Racing tab. **Permanent and irreversible** (only "New Body" resets it).
- **Roll Cage** — GT Auto. Similar effect: *"enhances the structural rigidity of a car making it less susceptible to flexing,"* improving agility.
- Older/high-mileage cars also have **Body Rigidity Restoration** available in GT Auto, which returns a degraded chassis to stock stiffness.

**The PP quirk — and it is a genuinely useful one:**

**Increasing body rigidity frequently *lowers* PP.** The mechanism, per the best community explanation: a stiffer body distributes load more evenly across left and right wheels in a corner, producing less roll, which the PP sim reads as **more understeery** and therefore slower — even though a properly re-tuned car is faster afterwards. *"Making the car more rigid will have the weight more distributed across the left and right wheels more creating less roll in the turn and appear to be more 'understeery' in nature."* ([GTPlanet — Why does increasing body rigidity lower the PP?](https://www.gtplanet.net/forum/threads/why-does-increasing-body-rigidity-lower-the-pp.424639/))

**But it is not reliable.** The same thread reports rigidity *raising* PP on a stock Honda Beat and *lowering* it on the same car once aero was fitted — the response is context-dependent on what else is installed.

**Practical use:** always test rigidity/cage on a completed build. If it lowers PP, you have found free performance — a genuinely better car for negative PP cost. Then re-tune the suspension softer to restore the rotation you lost.

**Wide-body kits** (GT Auto) reportedly **consistently decrease PP** — another candidate free-performance item, though they add weight and change aero.

> **⭐ 21 Aug — re-confirm both before exploiting either.** The rigidity quirk depends on how the PP sim reads roll, and 1.71 changed damper attenuation and revised suspension defaults — **which is to say it changed how the car rolls in the sim's cornering test.** The wide-body quirk depends on aero, and aero defaults and ranges moved on race cars. **Both are five-minute checks during the Job 4 audit, and both were free performance on v1.70, so they are worth the five minutes.**

---

## 7. Engine Swaps

### 7.1 How they work

Swaps are bought from **GT Auto**, replacing the car's engine wholesale with one from another car in the game. Availability is gated behind **Collector Level** (many at CL 50) and, historically, roulette-ticket engine drops; later updates (including 1.67, 1.68, 1.70 and **1.71** in 2026) have steadily converted these to purchasable. There are on the order of **270 swap combinations** catalogued. Prices range from ~¥109,000 for a Suzuki Swift engine to ~1,350,000 Cr. for the Ferrari Enzo unit. ([gtplus.app — GT7 engine swaps](https://gtplus.app/gt7/engine-swaps))

Key mechanics:
- The swap **replaces the engine and its entire tuning tree** — you re-buy engine upgrades for the new unit.
- The **chassis, drivetrain layout and weight distribution stay the car's own.** This is the whole point: you get a big engine in a small, light, well-balanced (or AWD) chassis.
- Purchasing a **New Engine** from the Extreme tab reverts to stock.

**⭐ 1.71 added swaps for ten cars at CL50** (full list in §3.1). **The two a league organiser should care about are the Mitsubishi Lancer Evolution IX MR GSR '06 and the Ford Focus RS '18** — both AWD, which §8.3 and §9.1 identify as the single most under-rated category in the PP system. **An AWD chassis that just gained swap access is precisely the archetype §9.2 recommends regulating.**

### 7.2 Meta-defining swaps

**⚠️ Every PP figure in this table is pre-1.71 and several are pre-1.49. Treat the *archetypes* as the content and the numbers as illustrative.**

| Car + Engine | Why it matters |
|---|---|
| **Suzuki Cappuccino '91 + Mazda 13B-REW (RX-7)** | The archetypal PP cheat car. Historically ran ~550 PP and was *"vastly superior (a lot faster) than most other cars out there with the same PP."* Near 200 mph in a kei car. |
| **Honda Beat '91 + Honda K20C1 (Civic Type R '20)** | Mid-500s PP, ~190 mph at High Speed Ring, described as behaving like a Gr.3 car. |
| **De Tomaso Pantera + Ford Coyote V8** | *"Performs like a 600PP car"* in 550 PP clubman events. |
| **Suzuki V6 Escudo Pikes Peak + High RPM Turbo** | 799 PP, *"the fastest cheat car,"* runs with Gr.2. (Also now has a swap of its own as of 1.70.) |
| **Nissan Skyline R34 GT-R + Nissan VRH35Z (R92CP)** | ~1000 bhp, 270+ mph. AWD + big power = strong under PP. The R32 variant is noted for great fuel economy even detuned to 700 PP. |
| **Mazda 3 '19 + Mazda R26B (787B rotary)** | Reportedly *"adds almost 200+ performance points"*; AWD stability, excellent for endurance. |
| **Porsche Cayman GT4 '16 + Windsor 351** | Balanced power-to-handling; 300+ mph; a known online meta build. |
| **Subaru BRZ + LS7 (7.8 L V8)** | ~1,037 bhp in a light RWD chassis. |
| **Ferrari F40 '92 + Ferrari F140B (Enzo)** | Tunes cleanly under 600 PP for WTC 600. |
| **Nissan GT-R Nismo '17 + Bugatti Chiron 8.0 W16** | *"Over 1800 BHP"*, 300+ mph. Extreme. |
| **Toyota HiAce Van + LS7** | 1000 bhp van. Comedy, but a real PP outlier. |
| **Honda Civic EK9 + K-swap** | ~697 PP and *"crazy fast"* for time attack. |

Sources: [Operation Sports — 10 Best GT7 Engine Swaps](https://www.operationsports.com/best-gran-turismo-7-engine-swaps-ranked/); [GTPlanet — PP "cheat cars"](https://www.gtplanet.net/forum/threads/pp-cheat-cars.413680/); [GTPlanet — fastest 700pp car](https://www.gtplanet.net/forum/threads/fastest-700pp-car.406597/)

### 7.3 PP implications

**Two things to understand:**

1. **Update 1.49 substantially nerfed swaps.** Engine-swapped cars saw the biggest PP *increases* of any category — the Lancer/Escudo needing −80 hp to return to 600 PP is the clearest documented case. The pre-1.49 swap meta is **not** the current meta, and any build list dated before July 2024 is stale. **⭐ And 1.71 is the same class of event, so expect swap PP to move again — most likely by the largest margin of any category, for the same structural reason. Any swap build near a cap should be re-read first.**
2. **Swaps are still systematically under-rated by PP, just less than before.** The reason is structural: the PP sim rates the *car* — a light chassis with a huge engine gets rated primarily on its power-to-weight in the sim's acceleration test, and the sim's driver model does not capture how devastating a 700 kg chassis with 400 hp is on a real circuit, nor does the sim properly credit AWD traction. The exploit is *fundamental to a simulation-derived single-number rating*, so it will never fully go away. **This reasoning is version-independent and survives 1.71 intact.**

**Practical rule:** **an engine swap into a small, light, low-drag chassis is the highest-value PP-per-lap-time move in the game.** Which is exactly why leagues regulate them (§9).

---

## 8. Build Strategy — a working method

### 8.1 The procedure

**Step 0 — Pin the version.** Record the game version (**now 1.71, 20 August 2026**). Any patch touching physics re-rolls PP. Re-validate the whole grid after each update. **⭐ This step is live right now, not hypothetical — `16` §12 Job 4.**

**Step 1 — Choose the car for the *track*, not the cap.**
The PP cap is a constraint, not an objective. Ask: is the circuit power-dominated (Le Mans, Monza, SSRX, Tokyo) or grip-dominated (Tsukuba, Suzuka East, Deep Forest, Gardens)? Then pick a chassis whose *weakness* the PP sim overvalues and whose *strength* it undervalues (see §8.3).

**Step 2 — Establish the baseline.**
Buy the car, note stock PP, run a reference lap on the actual race track with a default setup. This is your control. **⭐ Post-1.71 every existing reference lap is on old physics — PD reset their own leaderboards for exactly this reason. Re-establish the control lap before comparing anything to it.**

**Step 3 — Buy the free-slider hardware first.**
Fully Customisable Suspension (or Height-Adjustable Sports if PP is tight), Fully Customisable LSD, Fully Customisable Racing transmission, Full Control Computer (ECU — you need it for Output Adjustment), brakes. These cost a modest one-time PP toll and unlock unlimited free tuning.

**Step 4 — Test the negative-cost items.**
Fit body rigidity / roll cage and check PP. Fit a wide-body and check PP. Sweep the ballast position slider −50 → +50 with a small ballast load and record PP at each notch. Any of these that *lower* PP is free performance. Bank them. **⭐ All three need re-testing on v1.71 — the sim's roll and yaw tests now run on reworked geometry and a changed damper model.**

**Step 5 — Weight reduction Stage 1–2.** Check the car still handles. Stop if it gets nervous. **⭐ And do the Job 4 audit before buying any more — weight reduction is irreversible and you may need the tuning range to come back under a cap that just moved.**

**Step 6 — Decide the tyre compound, and treat it as a fixed budget line.**
Choose the compound from the §2 logic (track corner density, stint length, wear multiplier), commit the PP, and build the rest around what's left. **⚠️ On v1.71, §2's logic cannot be applied until a stint is measured (`16` §12 Job 2). Measure, then choose, then price.**

**Step 7 — Add power until you exceed the cap.**
Efficient parts first (filter → exhaust → manifold → intercooler → stroke/bore up), then forced induction chosen for *curve shape* per §3.2. Deliberately overshoot the cap — you want to be trimming down, not scraping up.

**Step 8 — Trim to the cap.**
- Power Restrictor first (preserves mid-range torque).
- ECU Output Adjustment if you need more reduction, or if the race is fuel-limited.
- Ballast mass for the last few PP — small amounts only.
- Ballast position for the final 1–3 PP and for balance simultaneously.
- **⭐ And re-test LSD accel sensitivity afterwards — the restrictor changes the torque shape the diff has to manage (§4, `08` D3.1).**

**Step 9 — Spend the free sliders.**
Now tune suspension, diff, gearing and brake bias properly. **PP does not move.** This is where the actual lap time is. Gear specifically to keep the engine in whatever narrow band your PP-discounted power curve gave you. **⚠️ On v1.71 this step is blocked until `11-car-slider-ranges.md` is re-read — you cannot issue percent-of-range targets against unknown endpoints.**

**Step 10 — Verify.**
Re-run the reference lap. Compare against the baseline and against a rival archetype at the same PP. If you're not clearly ahead, the PP was spent wrong — usually too much on power, not enough on the free stuff.

### 8.2 The caveat: PP is a poor proxy for lap time

State this plainly to your league. Documented examples of same-PP, wildly-different-performance:

- **R33/R34 Skyline vs NSX at 550 PP, Nürburgring: the Skylines were 6–8 seconds a lap faster.** The NSX's PP calculation penalises its upgrades far more heavily, so it gets less car per point. ([GTPlanet — PP similarities but huge time differences](https://www.gtplanet.net/forum/threads/pp-similarities-but-huge-time-differences.418308/))
- **Aston Martin DP-100 vs a van, both at 600 PP:** the DP-100 wins endurance races; *"the van would likely get lapped once or twice."*
- **A 570 PP Escudo tune outperforms much higher-PP alternatives.** ([GTPlanet](https://www.gtplanet.net/forum/threads/why-does-pp-go-down-when-you-do-this.419649/))
- Host experience: *"You can enter cars roughly on the same PP level that will perform like if they were more than 100PP apart"* — with the **550–650 PP band identified as the worst-affected range**. ([GTPlanet — PP Racing and Tuned road cars](https://www.gtplanet.net/forum/threads/pp-racing-and-tuned-road-cars.424806/))

**Why it fails structurally:** you are compressing at least ten independent variables — power, brakes, weight, CoG, chassis geometry, tyre compound, downforce, drag, gear ratios, suspension — into one scalar. *"It's impossible to compress them into a single number without losing almost all of the information."* And the system explicitly ignores suspension and diff settings and largely ignores gearing, so **identical-PP cars can differ by seconds purely from setup**.

**This section is an argument, not a measurement. It survives 1.71 completely — and the Shelby sits at PP 575, in the middle of the worst-affected band.**

### 8.3 Car archetypes systematically UNDER-rated by PP (the exploit list)

**These are structural biases in how a single scalar compresses a ten-dimensional problem. They are the most patch-proof content in this document.**

Build these:

1. **AWD, in general.** The most consistent structural bias. *"4WDs are pretty strong under the PP system"* and *"AWD systems receive insufficient PP weighting, allowing four-wheel-drive vehicles to wipe the floor with the rear-wheel drives."* The sim's acceleration test does not adequately credit AWD's traction advantage out of slow corners or in the wet. **GT-Rs, Evos, WRXs, Audis, and AWD swaps are the default meta pick.** **⭐ And 1.71 just gave the Evo IX and the Focus RS engine swaps.**
2. **Light chassis with a big swapped engine.** Cappuccino/13B, Beat/K20, Pantera/Coyote, Escudo. The sim under-rates how good a very light car is everywhere except top speed.
3. **Peaky, high-RPM forced-induction builds.** The sim penalises a badly-distributed powerband, so you get peak power at a discount, then gear around it.
4. **Excellent-handling, modest-power cars.** Alfa Romeo 4C (repeatedly cited, and also fuel-efficient), Mitsubishi Evo V (*"maybe the best handling car"* at 600 PP with no performance parts), Porsche 911 Carrera 2 '92. PP does not measure "easy to drive fast for 30 laps."
5. **Light + high-downforce specials.** Radical SR1 at 600 PP — low weight and high downforce that PP prices cheaply.
6. **Classic racers.** Jaguar D-Type/E-Type, Aston Martin DB3S, Ferrari 250 GT — well-tuned versions punch far above their PP.
7. **Cars with excellent fuel economy** in endurance formats. PP contains **no fuel-consumption term at all**. A car that saves one stop over an hour beats a faster car for free. The 911 Carrera 2 '92, the R32 GT-R with R92CP swap, and the Alfa 4C are all cited for this. **⭐ And 1.71 optimised rolling resistance, which moves fuel consumption independently of anything the builder chose — so the economy ranking may have reshuffled while PP still contains no term for it. That is a bias that just got *harder* to see, not easier.**
8. **Anything running nitrous**, if it genuinely costs 0 PP.

### 8.4 Archetypes OVER-rated by PP (avoid, unless the rules force you)

- **Heavy, high-downforce, high-power cars.** They pay full PP for aero that returns almost nothing in lap time (§1.4) and full PP for weight-hauling power.
- **High-aero road cars generally.** 21 PP for 0.1 s is a terrible trade.
- **Cars with intrinsically high top speed but poor cornering.** The sim over-weights straight-line and top-end, so these are priced expensively and don't deliver on real circuits.
- **NSX-type cars** whose PP calculation punishes upgrades disproportionately — you get less car per point.
- **Anything you can't drive consistently.** *"Power is nothing without control"* — this is both the PP sim's philosophy and, over a race distance, correct. **⭐ And this month, "anything you can't drive consistently" includes any car you have not re-baselined since 20 August.**

---

## 9. League Fairness — what dominates and what to regulate

### 9.1 What dominates open, no-BoP, PP-capped racing

In descending order of how much they distort a grid:

1. **AWD** — the biggest structural bias in the PP system. In an open field with a single PP cap, AWD cars will win.
2. **Engine-swapped light cars** — Cappuccino, Beat, Pantera, Escudo, small hatches with V8s.
3. **Nitrous** — if it truly adds 0 PP, it is unregulatable by the PP cap by definition.
4. **Setup depth** — invisible to PP, and worth seconds. Your best tuner will beat your best driver. **⭐ And post-1.71 setup depth is worth *more* than usual, because everyone's setup knowledge reset at once and the field's published tunes are all stale. This is the window.**
5. **Fuel economy in endurance** — completely absent from PP.
6. **Peaky-turbo + custom-gearing builds** — peak power at a PP discount.
7. **Whatever bug the current patch has introduced.** After every physics update, a handful of part combinations mis-rate. This has recurred at least three times since launch. **⭐ Four, now — and 1.71's anomalies have not been found yet, by anyone. Expect them within a fortnight.**

### 9.2 What organisers typically ban or limit

Ranked by effectiveness-per-unit-of-annoyance:

**Tier 1 — do these**

- **Mandate a tyre compound (or a maximum compound).** The single most effective levelling tool available. Direct host testimony: *"Adding a tyre restriction is the easiest way to level a playing field, i.e. 600pp + SS and you'll find the field much tighter."* Removing the tyre-vs-power arbitrage collapses most of the PP system's variance in one line of regulation. **⭐ And it is doubly attractive right now: it removes the one axis nobody in the league can currently reason about, since the wear model is unmeasured on v1.71.**
- **Ban or heavily restrict engine swaps.** Either ban outright, or maintain a whitelist. This kills the single largest category of PP cheat cars. **⭐ Note that 1.71 added ten new swaps, two of them AWD — a whitelist written before 20 August is now incomplete.**
- **Ban nitrous / overtake systems.** A zero-PP performance item cannot coexist with a PP cap.
- **Split by drivetrain, or apply a PP handicap to AWD.** E.g. AWD runs 10–20 PP below RWD. This is a crude fix for a real structural bias. *(The magnitude is a judgement call — no published number exists. Start at 10 PP and iterate from lap-time data.)*

**Tier 2 — commonly used**

- **A specific-car or specific-class list** rather than a bare PP cap. A PP cap alone is not a class; PP variance in the 550–650 band alone can exceed 100 PP of real performance.
- **Ban roulette-only "special" parts** (Ultra-High RPM Turbo, High-RPM S Supercharger, Bore/Stroke Up S, High Lift Cam S, Ti rods/pistons, Carbon Propshaft, Weight Reduction Stage 5/6) — they are luck-gated as well as performance-distorting, though CL50 purchasing has reduced the fairness argument.
- **Cap ballast, or ban ballast position adjustment**, to close the free-PP exploit in §5.5.
- **Ban wide-body kits** if they are found to reduce PP on your version.
- **Ban or cap maximum downforce** — mostly to prevent a specific outlier rather than for balance, since aero is weak in GT7.
- **Weight floor** (minimum kerb weight) to stop Stage 4–6 stripping.
- **Mandatory pit stop / minimum tyre change** to neutralise the fuel-economy exploit in endurance formats. *(GT7 exposes both directly as lobby settings since Spec III — see `03` §4.5.1.)*
- **⭐ NEW — set mechanical damage to "Championship."** Added in 1.71: Light's damage severity, but triggered from more minor collisions, with recovery time varying by severity. **It prices contact without ending races, which is the middle ground leagues have not previously had** — Light was too forgiving to deter dive-bombs, and full damage too punitive. **Recommend adopting it, and note that it raises the value of braking stability and predictability-under-contact in every setup (`04` §7).**

**Tier 3 — the pragmatic alternative**

- **Run a custom league BoP.** Several league-service outfits publish per-car power/weight adjustments precisely because PP alone is insufficient. If your league is serious and stable, hand-tuned per-car power and weight multipliers, iterated from actual race data, will always beat any PP-cap regulation. ([FILO Engineering — Custom BoP for Leagues](https://www.filoengineering.com/home/gran-turismo-7/filo-engineering-custom-bop-for-leagues) — *note: this page blocks automated retrieval; verify content directly*)
- **The nuclear option that most public championships take:** *"Tuning is prohibited"* — fixed cars, factory BoP, brake balance the only permitted adjustment, plus a mandated tyre compound (e.g. softs in qualifying, mediums in the race). See the [International GT Challenge Cup rules](https://www.thesimgrid.com/championships/7373/rules) for a representative example. Obviously not what your league wants, but it is the benchmark for what "fair" costs.

### 9.3 Two housekeeping rules every GT7 league needs

1. **Version-lock and re-validate.** Publish the game version the ruleset applies to. After any update that touches physics, PP values move across the entire grid and existing builds must be re-checked. This has happened **four times** since launch (1.49 being the largest, **1.71 the most recent**). Without this rule, half your grid becomes illegal overnight and the other half becomes unexpectedly fast.

   > **⭐ 21 Aug 2026: this rule is live.** The ruleset needs re-pinning from 1.70 to 1.71, and every car on the grid needs re-reading. **Raise it with the organiser this week — before a round, not after one.** This document flagged the possibility in §1.4 before the patch existed; the flag was right, and the value of having written it down is that nobody now has to argue about whether a re-scrutineering is warranted.

2. **Have a written anomaly rule.** Something like: *"Any build whose PP value is demonstrably inconsistent with its measured performance — e.g. a part combination that produces an anomalous PP drop — may be declared ineligible by the organiser."* The LSD bug (−139 PP), the gear-ratio threshold bug (+41 PP), and the post-1.49 no-PP-value cars are all precedents. New ones appear after every physics patch, and you need the authority to act before someone builds a season around one.

   > **⭐ And the next fortnight is precisely when this rule earns its keep.** 1.71's anomalies have not been discovered yet — by us or by the wider community (`16` §10). **If the league does not already have this clause written down, adding it now is a five-minute job that will look extremely prescient in three weeks.**

---

## Summary — the ten things that actually matter

1. **PP is simulated, not calculated.** No formula exists. Build empirically.
2. **Parts cost PP; settings are free.** Buy the hardware that unlocks sliders, then extract lap time from the sliders. This is the core min-max lever.
3. **Physics changes re-roll all PP — four times so far: 1.49, 1.55, and now 1.71 (20 Aug 2026).** Engine swaps are hit hardest. Anything published before the current patch is stale. **⭐ Audit your builds against the cap now.**
4. **Tyres are the biggest PP step** (~10–30 PP per compound step, car-dependent; one measured case +27.5 PP on v1.70). Soft tyres for sprints and corner-dense tracks; power for straights and endurance — **but measure the stint before choosing the compound (`03` §1.3.1).**
5. **The restrictor cuts the top end; the ECU shrinks the whole curve.** Restrictor for mid-range torque, ECU for maximum PP reduction and fuel economy. PP response to power is steeply non-linear (one measured case: 1% ECU = 14.3 PP). **And the restrictor's torque-shape effect changes your LSD accel setting (`08` D3.1).**
6. **Ballast is the fine-tuning tool** (~10 kg ≈ 1 PP on a heavy car), and **ballast *position* is a free-PP exploit** — sweep the slider and record PP at every notch. **The first place to look for points back if a build came out of 1.71 over the cap.**
7. **Body rigidity and wide-bodies often *lower* PP** — free performance if the car responds well. Test them, and re-test them on v1.71.
8. **AWD, light-chassis engine swaps, fuel-efficient cars, and great-handling low-power cars are systematically under-rated.** Heavy high-aero high-power cars are over-rated. **These biases are structural and survive patches.**
9. **PP is a poor proxy for lap time.** 6–8 second gaps at identical PP are documented. The 550–650 PP band is the worst — **and the Shelby sits at 575.**
10. **For a fair league: mandate a tyre compound, ban engine swaps and nitrous, handicap AWD, version-lock the ruleset, reserve the right to disqualify anomalous builds — and consider the new "Championship" damage setting.**

---

## Sources

**1.71 (the current baseline)**
- [gran-turismo.com — Update Notice (1.71)](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html)
- [GTPlanet — Update 1.71 Arrives With Major Physics Changes](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Traxion — 1.71 brings sweeping physics changes, resets leaderboards](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [GTPlanet — Undocumented Changes Thread (1.71)](https://www.gtplanet.net/forum/threads/gran-turismo-7-undocumented-changes-thread-1-71.439041/)

**PP mechanics and anomalies**
- [GTPlanet — GT7 Tuning Reverse Engine PP ratios](https://www.gtplanet.net/forum/threads/gt7-tuning-reverse-engine-pp-ratios.438245/)
- [GTPlanet — PP Issue! (post-1.49 cars with no PP value)](https://www.gtplanet.net/forum/threads/pp-issue.427864/)
- [GTPlanet — #StopNerfingCars](https://www.gtplanet.net/forum/threads/stopnerfingcars.427824/)
- [GTPlanet — Update 1.49: Eiger Nordwand, Six New Cars, Physics Changes (p.41)](https://www.gtplanet.net/forum/threads/gran-turismo-7-update-1-49-eiger-nordwand-six-new-cars-physics-changes-more.427531/page-41)
- [GTPlanet — Why does PP go down when you do this?](https://www.gtplanet.net/forum/threads/why-does-pp-go-down-when-you-do-this.419649/)
- [GTPlanet — Why does increasing body rigidity lower the PP?](https://www.gtplanet.net/forum/threads/why-does-increasing-body-rigidity-lower-the-pp.424639/)
- [GTPlanet — Strange PP changes when changing parts](https://www.gtplanet.net/forum/threads/strange-pp-changes-when-changing-parts.409005/)
- [GTPlanet — PP "cheat cars"](https://www.gtplanet.net/forum/threads/pp-cheat-cars.413680/)
- [GTPlanet — PP similarities but huge time differences](https://www.gtplanet.net/forum/threads/pp-similarities-but-huge-time-differences.418308/)
- [GTPlanet — PP Racing and Tuned road cars](https://www.gtplanet.net/forum/threads/pp-racing-and-tuned-road-cars.424806/)
- [GTPlanet — Best way to lose 20PP — and the winner is…](https://www.gtplanet.net/forum/threads/best-way-to-lose-20pp-and-the-winner-is.409458/)
- [GTPlanet — What's the difference between "Output Adjustment" and "Power Restrictor"?](https://www.gtplanet.net/forum/threads/whats-the-difference-between-output-adjustment-and-power-restrictor.410141/)
- [GTPlanet — Can someone explain the benefits of different Turbo RPM variations?](https://www.gtplanet.net/forum/threads/can-someone-explain-the-benefits-of-different-turbo-rpm-variations.406714/)
- [GTPlanet — Special/Ultimate Parts](https://www.gtplanet.net/forum/threads/special-ultimate-parts.405370/)
- [GTPlanet — Weight and weight distribution](https://www.gtplanet.net/forum/threads/weight-and-weight-distribution.428334/)
- [GTPlanet — Ballast question (GT6-era, mechanics carried over)](https://www.gtplanet.net/forum/threads/ballast-question.323207/)
- [GTPlanet — PP upgrade to win races - for dummies!](https://www.gtplanet.net/forum/threads/pp-upgrade-to-win-races-for-dummies.405296/)
- [GTPlanet — What cars are best to try and mod to 700PP](https://www.gtplanet.net/forum/threads/what-cars-are-best-to-try-and-mod-to-700pp.430986/)
- [GTPlanet — Fastest 700pp car?](https://www.gtplanet.net/forum/threads/fastest-700pp-car.406597/)
- [GTPlanet — Tuning system is completely broken in GT7 (p.2)](https://www.gtplanet.net/forum/threads/tuning-system-is-completely-broken-in-gt7.406139/page-2)
- [GTPlanet — Racing soft tires vs medium](https://www.gtplanet.net/forum/threads/racing-soft-tires-vs-medium.427384/)
- [GTPlanet — Evaluation Performance Tuning Project for all GT7 cars](https://www.gtplanet.net/forum/threads/evaluation-performance-tuning-project-for-all-gt7-cars.407110/)
- [GTPlanet — Gran Turismo 7 Game Update tag (2026 update index)](https://www.gtplanet.net/tag/gran-turismo-7-game-update/)

**Official update notices**
- [gran-turismo.com — Update Details (1.49)](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)
- [gran-turismo.com — Notice: Update 1.55](https://www.gran-turismo.com/us/gt7/news/00_3399040.html)
- [gran-turismo.com — Update Notice (1.70)](https://www.gran-turismo.com/us/gt7/news/00_1814793.html)

**Parts, tuning and building**
- [OverTake.gg — Huge Gran Turismo 7 Handling 1.49 Update Out Now](https://www.overtake.gg/news/huge-gran-turismo-7-handling-1-49-update-out-now.2289/)
- [Occam's Racer — GT7 Aerodynamics](https://occamsracers.com/2024/04/19/gt7-aerodynamics/)
- [Doughtinator — ECU and Performance Adjustment](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/ecu-and-performance-adjustment)
- [Doughtinator — Suspension](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/suspension)
- [Doughtinator — Transmission](https://doughtinator.com/en-us/blogs/ultimate-gran-turismo-7-tuning-guide/transmission)
- [Coach Dave Academy — GT7 Tuning Guide: Every Setting Explained (2026)](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)
- [DiamondLobby — Best Tuning Setups for GT7](https://diamondlobby.com/gran-turismo-7/best-tuning-setups-for-gt7/)
- [SimRacingSetup — How To Upgrade Your Car in Gran Turismo 7](https://simracingsetup.com/gran-turismo/how-to-upgrade-your-car-in-gran-turismo-7/)
- [Flux89 — The Complete GT7 Tuning Cheat Sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet)
- [Brembo — GT7 Guide: How to Upgrade Car Brakes](https://www.brembo.com/en/live-our-energy/gaming/gt7-tuning)
- [Traxion — New GT7 tuning options revealed in Brembo partnership](https://traxion.gg/new-gran-turismo-7-tuning-options-revealed-in-brembo-partnership-announcement/)
- [Traxion — GT7 June 2026 update (1.70)](https://traxion.gg/gran-turismo-7-june-2026-update-everything-you-need-to-know/)
- [gtplus.app — Complete list of GT7 engine swaps](https://gtplus.app/gt7/engine-swaps)
- [Operation Sports — 10 Best Gran Turismo 7 Engine Swaps, Ranked](https://www.operationsports.com/best-gran-turismo-7-engine-swaps-ranked/)
- [Gamepur — How to lower PP in Gran Turismo 7](https://www.gamepur.com/guides/how-to-lower-pp-performance-points-in-gran-turismo-7)
- [The SimGrid — International GT Challenge Cup rules (example locked-tuning ruleset)](https://www.thesimgrid.com/championships/7373/rules)
- [FILO Engineering — Custom BoP for Leagues](https://www.filoengineering.com/home/gran-turismo-7/filo-engineering-custom-bop-for-leagues) *(page blocks automated retrieval — verify manually)*

---

### Note on what I could not verify

Three things the brief asked for do not exist in verifiable public form, and I have not invented them:

1. **A PP formula or per-part PP cost table.** PP is simulation-derived; no such table can be universally correct, and none is published.
2. **A PP-per-tyre-compound-step constant.** Only one controlled measurement is publicly available (+27.5 PP for stock → Sports Soft on a TVR Tuscan Speed 6, on v1.70).
3. **A kg-per-1%-weight-distribution constant for ballast.** The relationship depends on car mass, ballast load and starting distribution. I have given a first-principles estimate (~1% per ~30 kg at full rear on a 1,400 kg car) and flagged it as derived, not sourced. Read the exact figure from the game's live front/rear distribution readout.

**⭐ A fourth, added 21 August 2026: the PP effect of update 1.71 on any specific car.** PD state that Performance Points were adjusted across the game and name no cars and no magnitudes. **Nobody outside Polyphony knows what your build is worth now.** Read the number off the car.
