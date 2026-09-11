# GT7 Tyre & Fuel Model — Sim-Racing Engineering Reference
**Compiled August 2026 · Baseline build: GT7 v1.70 (June 2026), post-Spec III**
**Updated 10 Aug 2026 — first in-house measured wear result added (§1.3.1). See also §4.1 note.**
**⚠️ Updated 21 Aug 2026 — 1.71 exposure banner added below. The body of this document is unchanged and is a v1.70 record.**

---

# 🔴 1.71 EXPOSURE BANNER — READ BEFORE USING ANY NUMBER BELOW

**GT7 v1.71 (20 August 2026) changed the tyre model.** The official notes state, verbatim:

> "The algorithm has been updated, focusing on the simulation when tyres are slipping."
> "Road surface resistance (rolling resistance) has been optimised."
> "Tyre heating and wear values have been adjusted."
> "The amount of tyre grip lost when 'Grip Reduction Off Track' is set to 'Real' has been adjusted."

**The direction and magnitude of every one of those is unstated.** Faster or slower wear, hotter or cooler running, is unknown. Nobody has measured it — see `16-update-1.71-physics-change.md` §10 for the state of the public record, which as of 21 Aug is essentially empty.

**This document is the worst-affected file in the knowledge base**, because almost all of its authority came from the post-1.49 model being stable for two years. Full context: `16-update-1.71-physics-change.md`, especially §3 and §12.

## What is void, section by section

| Section | Status on v1.71 | Why |
|---|---|---|
| **§1.1 compound ladder** | **Intact** | The 13 compounds and their ordering are game structure, not physics values. |
| **§1.2 grip deltas** | **Suspect** | The Laguna Porsche 963 RS→RH figure (1.412 s/lap) and the ~1 s/step rule of thumb are v1.70-and-earlier. A slipping-regime rework moves compound deltas directly. |
| **§1.3 relative wear rates** | **Void** | The assumed RH:RM:RS ≈ 1.0:1.4:2.0 was never measured pre-1.71 and is now doubly untethered. |
| **§1.3.1 the Laguna RS measurement** | **⚠️ Historical.** Not deleted, not transferable | 11–12 laps at 2× on v1.70. Still the correct *method* and a valid *historical* datapoint. **It may no longer describe the game.** Its standing rule — measure before choosing a compound — is now more binding, not less. |
| **§1.4 the RH/RM/RS trade-off** | **Framework intact, inputs void** | The four-number decision structure (Δt, D, L, P) is sound engineering. Every value fed into it is a v1.70 value. |
| **§2.1 what 1.49 changed** | **Superseded in part** | 1.49's changes are history. 1.71 re-does the slipping simulation on top of them. |
| **§2.2 the piecewise curve** | **Void** | Flat → progressive → cliff at ~90–95% was a 1.49 artefact. A patch that rewrites the slipping regime is exactly what reshapes a cliff. **Whether a cliff still exists is unknown.** |
| **§2.3 the indicator** | **Probably intact** | The gauge is a UI element. Its non-linear relationship to grip depends on §2.2, so the *warning* stands even if the shape changed. |
| **§2.4 lap time lost per unit wear** | **Void** | Every row is a v1.70 estimate. |
| **§2.5 driving style ranking** | **Void as a ranking** | Lateral slip was dominant *because 1.49 made it so*. 1.71 explicitly re-does the slipping simulation. The ranking could be reinforced, softened or inverted. Item 5 (braking/acceleration demoted) and item 8 (elevation withdrawn) are the least exposed. |
| **§2.6 front/rear asymmetry by drivetrain** | **Suspect** | Per-car steering geometry was reworked in 1.71, which is a front-axle slip-angle change. Which axle goes first is now an open question again on all three cars. |
| **§3 temperature** | **⚠️ Actively in play** | 1.71 "adjusted tyre heating values." This document calls heat "real but rudimentary"; `04` §6.1 calls it "functionally invisible in practice." **Those two already disagreed. The patch makes resolving it a priority, not a curiosity.** See `16` §12 Job 6. |
| **§3.4 no tyre pressure** | **Intact** | Still not in the game. Rule 4 stands. |
| **§4.1 multipliers as linear scalars** | **Intact as a mechanism, and still [CONTESTED]** | Multipliers scale a rate; that shouldn't change. The underlying rate did. The playbook's downgrade of the [CONFIRMED] tag still wins. |
| **§4.3 Sport Mode calibration table** | **Void as calibration** | Those events were designed against v1.70 wear. PD will re-tune Daily Race multipliers to the new model; until they publish new ones, the ratio pattern (tyre scaled ~2× harder than fuel) is the only part worth carrying forward. |
| **§4.4 deriving stint length** | **Method intact, must be re-run** | The 3-lap procedure with usable fraction 0.85 is exactly the right instrument. Every output it has produced is stale. |
| **§4.5 recommended multipliers by format** | **Void** | If wear got faster, these produce more stops than intended; if slower, fewer. Do not publish league regulations from this table until a stint is measured. |
| **§5 the fuel model** | **⚠️ Suspect via rolling resistance** | Tank capacity (100 L) and fuel-map structure are unaffected. **But "rolling resistance has been optimised" is a fuel term as much as a tyre term** — every L/lap figure in §5.2 may have moved, independently of driver input. §5.5's 4%/8% fuel-map rule was already flagged as GT Sport-era and is now overdue for a re-test. |
| **§6 pit stops** | **Intact** | Pit travel time is a track constant. Refuel rate is an event property. Neither was touched. |
| **§7 wet weather** | **Suspect** | Off-track grip loss on "Real" was adjusted, and wet compounds live at the extreme of the slipping regime. Section 7.5's wet setup table is reasoning-led and should survive directionally. |
| **§8 setup consequences** | **⚠️ Mixed — read carefully** | §8.1's core principle is vehicle dynamics and survives as *reasoning*. Whether it still describes GT7's *wear function* is the open question. **§8.3 camber is the most likely single item to have changed** — 1.71 reworked per-car steering geometry, which is exactly the model that produced GT7's anomalous camber behaviour. **§8.5 LSD baselines are written against the v1.70 5–60 range; v1.71 reads 0–30 / 0–100 / 0–100 on every car in `range_records`.** |
| **§9 league quick reference** | **Void as numbers, intact as advice** | Items 1–8 of "things to tell your drivers" are behavioural and mostly survive. Item 3 (sliding kills tyres) is the one to re-verify. Item 9 — *measure before you choose* — is the whole document now. |
| **§10 known gaps** | **All still open, and several got cheaper** | The temperature-window item and the camber-swap item are now the two highest-value tests available, because the patch made both live. |

## The rule this banner produces

> **Every wear, stint-length, fuel-consumption and compound-choice number in this document is a v1.70 number until re-measured on v1.71. Do not plan a race on any of them.**

This is not new policy — it is §1.3.1's own standing rule, extended. That rule was written because a *model* was 1.8× wrong. It now also applies because the *measurement* is from a previous version of the game.

**The re-measurement plan is `16-update-1.71-physics-change.md` §12.** Jobs 2 and 3 — one RS stint and one RM stint on the Huracán at Watkins Glen at the league multiplier — rebuild the top half of this document in a single session and close the RH:RM:RS ratio question that §10 item 1 has had open since this file was written.

**When those runs come back, the results go here**, tagged `[MEASURED — IN HOUSE]` with date, car, track, multiplier **and version** (Standing Rule 10), and this banner shrinks to the sections still outstanding.

---

## 0. How to read this document

GT7's tyre and fuel models are **not documented by Polyphony Digital**. Almost nothing below comes from published coefficients; it comes from telemetry inspection, controlled community testing, and official patch-note language. I have tagged claims:

- **[CONFIRMED]** — official Polyphony source, or directly readable in the UDP telemetry stream.
- **[TESTED]** — reproducible community testing with methodology stated.
- **[MEASURED — IN HOUSE]** — measured by this driver, in this league's actual conditions. **Outranks everything above for our own use.**
- **[CONSENSUS]** — broad agreement among competitive drivers, no controlled test.
- **[UNVERIFIED]** — plausible, widely repeated, but I could not find a source that actually measured it. **Treat as a hypothesis to test yourself.**

**Critical version warning.** Update **1.49 (24 July 2024)** rewrote the tyre wear and heat model. Update **1.55 (30 Jan 2025)** further changed wet/dirty-surface grip. **Update 1.71 (20 Aug 2026) reworked the slipping regime, rolling resistance, heating and wear values, and off-track grip loss — see the banner above.** **Any tyre-wear or strategy guide dated before July 2024 is wrong** — including most of the well-known YouTube content and essentially all GT Sport-derived data. Where I use pre-1.49 or GT Sport data (because nothing newer exists), I say so explicitly. **Everything below is a v1.70 record.**

---

## 1. Tyre compounds

### 1.1 The full ladder

GT7 ships 13 compounds in three street/track families plus specials. Ordered by dry asphalt grip, lowest to highest:

| # | Compound | Short | Family | Typical use |
|---|---|---|---|---|
| 1 | Comfort Hard | CH | Comfort | Stock economy/classic cars, drift practice, low-PP events |
| 2 | Comfort Medium | CM | Comfort | Stock road cars |
| 3 | Comfort Soft | CS | Comfort | Sunday Cup / low-PP racing, "road car" league regs |
| 4 | Sports Hard | SH | Sports | ~500–550PP road-car racing |
| 5 | Sports Medium | SM | Sports | Mid-PP road car racing, Daily Race A one-makes |
| 6 | Sports Soft | SS | Sports | ~600PP road-car racing, Gr.4-adjacent road cars |
| 7 | Racing Hard | RH | Racing | Default fitment on all Gr.1–Gr.4 cars; endurance |
| 8 | Racing Medium | RM | Racing | Default competitive Gr.3/Gr.4 sprint compound |
| 9 | Racing Soft | RS | Racing | Qualifying, short stints, opening stints |
| 10 | Racing Intermediate | RI | Wet | Damp / drying / light rain |
| 11 | Racing Heavy Wet | RW | Wet | Standing water, heavy rain |
| 12 | Dirt | — | Special | Gravel/rally layouts only |
| 13 | Snow | — | Special | Snow layouts only (Chamonix etc.) |

**[CONFIRMED]** Compound-to-real-world mapping was made explicit at 1.49 with the Michelin licence: Comfort = Pilot Sport 4S, Sports = Pilot Sport Cup 2 R, Racing = Pilot Sport slick, Intermediate/Wet = Pilot Sport GT, Dirt = Pilot Sport Gravel, Snow = Pilot Alpin 5. **Note: the Michelin branding was removed at v1.63 (Sept 2025) and Dunlop was added as a supplier at v1.65 (Dec 2025).** The compound *physics* did not change with the branding swap — only the sidewall art and sponsor presence. The Michelin mapping remains the best available description of what each compound is *meant* to represent.

### 1.2 Grip deltas

There is no published friction coefficient table. The best quantitative anchors available:

**Family steps (large).** **[TESTED]** Lateral-G measurements at the Comfort end show roughly **0.09–0.10 g per step** between CH→CM and CM→CS. For reference, a '68 Charger on CH pulls ~0.78 g in GT7. This is a very coarse ladder — one Comfort step is a bigger grip change than the entire Racing Hard→Soft range.

**Racing family steps (small).** **[TESTED]** Porsche 963 at **Laguna Seca**, five timed laps per compound, controller, TCS 3:
- Racing Soft: 1:14.718 average, 1:14.144 best
- Racing Hard: 1:16.130 average, 1:15.324 best
- **Delta RS→RH = 1.412 s/lap average, 1.18 s on best lap.**

> **⚠️ This is the most directly applicable datapoint in the entire document for our current programme, because it is at our circuit.** Over a 20-lap race, choosing RH over RS costs roughly **28 seconds** — more than a full pit stop (~18–20 s at Laguna). Any compound decision at Laguna that trades pace for durability must clear that bar, and it is a high bar. Caveats: Gr.1 car, controller, TCS 3, so treat the magnitude as directional for a Gr.3 car on a wheel with TCS 0. The *sign and rough scale* are what matter.

**[CONSENSUS]** The widely used rule of thumb in Sport Mode is **~1 second per compound step per "average" lap** in Gr.3, i.e. RS→RM ≈ 0.5–0.8 s, RM→RH ≈ 0.5–0.8 s, RS→RH ≈ 1.0–1.5 s. The Laguna Seca test above sits at the low end of that band and the author explicitly noted "the deficit isn't as large as I had expected," attributing it to the circuit's low-speed, technical character.

**The delta scales with corner load, not lap length.** Practical guidance for a league:
- **Low-speed, high-lateral-load circuits** (Tsukuba, Kyoto Yamagiwa, Tokyo Expressway, Dragon Trail Seaside): compound delta is *smaller* in absolute seconds but the softer compound is disproportionately harder to keep alive.
- **High-speed, aero-dominated circuits** (Le Mans, Monza, Spa, Fuji): mechanical grip matters less, so the compound delta shrinks further — sometimes to under 0.4 s/lap between RM and RH. On these tracks RH one-stoppers become very strong.
- **Heavy traction-and-braking circuits** (Road Atlanta, Bathurst, Interlagos, Red Bull Ring): compound delta is largest and degradation punishes softs hardest — the classic strategy-race profile.

**Intermediates in the dry.** **[TESTED]** Racing Intermediates and Sports Softs are near-indistinguishable on dry asphalt, and carry the same PP. Intermediates are effectively a "grooved Sports Soft" in the dry — they are *not* a downgraded racing slick. Do not let anyone run inters as a dry loophole compound in a Sports-tyre-regulated class; they are legitimately competitive there.

### 1.3 Relative wear rates

**[UNVERIFIED — this was the single biggest gap in the public record, and it remains so for the RH:RM:RS *ratio*.]** No one has published a controlled, post-1.49 measurement of RH vs RM vs RS wear per lap. GTPlanet threads asking for exactly this chart conclude that the testing burden (2–3 race distances per car/track/compound) has kept anyone from producing it.

What can be said:

**[CONSENSUS]** The commonly assumed ratio is approximately **RH : RM : RS ≈ 1.0 : 1.4 : 2.0** in wear per lap — i.e. a soft set lasts roughly half as long as a hard set. This is consistent with observed Sport Mode race design (see §4.3) but has not been measured directly. **⚠️ See §1.3.1 — our one in-house absolute measurement suggests the *absolute* rates in circulation are far too pessimistic, even if this ratio is right.**

**[TESTED]** Wet compounds degrade *very* fast, especially once the track dries. Community reporting is unanimous that "wet tyres degradation is really fast" and that this — not grip — is the binding constraint on staying out on wets through a drying phase.

**[TESTED, pre-1.49 but directionally still valid]** Car-to-car variation in wear rate is comparable in magnitude to compound-to-compound variation. A Gr.3 MR test at Lago Maggiore (8 laps, 10x wear, RH, BoP on) found the McLaren 650S could run **1–2 laps longer than the Lamborghini Huracán** before becoming undriveable — on the same compound. **For a league, this matters more than most organisers realise: BoP equalises pace, not tyre life.** If your regs allow free car choice with high wear multipliers, tyre life becomes the dominant performance differentiator and you will see the field converge on 3–4 cars.

### 1.3.1 ✅ [MEASURED — IN HOUSE] Racing Soft at Laguna Seca, 10 Aug 2026

**The first real post-1.49 wear number in this knowledge base.**
**⚠️ 21 Aug 2026: this is a v1.70 measurement. It stands as history and as method. It may no longer describe the game. See the banner.**

| | |
|---|---|
| Car | Lamborghini Huracán GT3 '15, 525 bhp / 1300 kg, restrictor 70, 70 kg ballast |
| Circuit | WeatherTech Raceway Laguna Seca (3.6 km, 55 m elevation) |
| Compound | **Racing Soft** |
| Multiplier | **2× tyre wear** |
| Conditions | **Race pace, full-fuel start** — representative stint conditions, not a hot-lap run |
| **Result** | **~11–12 laps before fall-off** |
| **Normalised** | **22–24 laps of 1× wear** |
| Game version | v1.70 |

**Why this matters beyond the one event: it invalidated a modelled estimate by roughly 1.8×.** The pre-test model predicted RS would give ~6–7 real laps at 2×. It gave 11–12. The measured **Soft** roughly equalled the modelled **Hard**.

**Diagnosis of the model error — two contributors, one of them clearly mine:**

1. **An invented elevation penalty.** The estimate added wear on the reasoning that 55 m of climb produces vertical load cycling beyond what corner speeds suggest. That is plausible physics with **no supporting data anywhere in this document or the public record.** It should not be applied to Bathurst, Sainte-Croix, or any other elevation circuit until someone measures one. **Consider it withdrawn.**
2. **A pessimistic base rate.** The generic Gr.3 wear figures in circulation appear to be too harsh, at least at this circuit and this multiplier. Note §1.3's own warning that **car-to-car variation rivals compound-to-compound variation** — a generic "Gr.3 at Laguna" number was never going to be reliable for a specific car.

**What this does *not* establish.** It does not test multiplier linearity (§4.1), because there is no second multiplier to compare against. It does not establish the RH:RM:RS ratio, because only RS was run. **One more run on RM at the same track and multiplier would calibrate the whole ladder for this car** and is the cheapest high-value test available. *(21 Aug: this is now `16` §12 Job 3, and it must be re-done on v1.71 rather than at Laguna on v1.70.)*

**The standing rule this produces:**

> **No modelled wear figure in this knowledge base may be used to select a race compound. Measure one stint at the actual multiplier, then choose.** The cost of measuring is one practice run. The cost of getting it wrong at Laguna is ~1.4 s/lap (§1.2) for the whole race — about 28 seconds, or more than a pit stop.
>
> **21 Aug 2026 extension: "no modelled figure" now includes every measured figure taken on a previous game version — including this one.**

Full context and the strategy rebuild it forced: `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 2.

### 1.4 The RH / RM / RS trade-off in Gr.3

Build the decision from four numbers:

- **Δt** = lap-time delta between compounds (s/lap) — measure it, don't assume it
- **D** = degradation rate on each compound (s/lap of additional loss)
- **L** = stint length in laps
- **P** = pit lane time loss (s) — see §6

**The crossover heuristic.** **[CONSENSUS]** A worn soft is roughly equivalent to a fresh medium at around **50–60% worn**. Past that the soft is worse than a fresh medium and you are losing time to a car that stopped. This is a *heuristic offered by an AI in a GTPlanet thread and it was challenged in that same thread* — I flag it because you will see it repeated everywhere. Treat 50–60% as a starting hypothesis to calibrate, not a fact.

**The 1.49 cliff dominates everything.** **[CONFIRMED via patch-note language + TESTED]** Since 1.49, all racing compounds show a sharp performance collapse rather than smooth linear decay (§2). This changes the classic calculus: in a linear-degradation sim you optimise the integral of pace over the stint; **in GT7 you optimise the point at which you fall off the cliff.** A soft stint that is one lap too long can cost more than the entire compound advantage. **⚠️ 21 Aug: whether the cliff survived 1.71 is unknown — see the banner, §2.2 row.**

**Practical Gr.3 decision rules:**

| Scenario | Choice |
|---|---|
| Sprint, no mandatory stop, ≤6 laps, low wear multiplier | RS — no reason not to |
| One mandatory stop, both compounds required | RS first (burn them while the fuel load is heavy and the field is dirty-air-bound), RM/RH for the longer second stint. This is the standard and it is standard for a reason: the softs' cliff arrives sooner, and you'd rather hit it at lap 5 with a pit window open than at lap 12 with the flag out. |
| One stop, free compound choice, medium-length race | RM both stints is almost always the safe answer; RH-RH one-stop wins if pit loss is high (Le Mans, Sarthe) |
| **One stop, free compound choice, and a *measured* stint length that comfortably covers each stint** | **Take the softest compound that fits.** Durability you don't consume is pace you paid for and threw away. This is the case that caught us out at Laguna — see §1.3.1. |
| Long stint mandated by fuel, high wear multiplier | RH. Once a stint exceeds the RM cliff point, the RM's grip advantage is negative for the back half of the stint |
| Dirty air / heavy traffic expected | Shade harder. Following costs tyre life (extra steering correction, sliding), and dirty air reduces front grip, which is where 1.49 concentrated wear |

**The counterintuitive one:** on tracks where a hard-tyre one-stop and a soft-tyre two-stop are within a couple of seconds on paper, **take the harder, longer strategy**. GT7's pit stops are slow and variable (§6), the safety-car equivalent doesn't exist to bail you out, and the cliff is punishing. Fewer stops has lower variance.

**The counterintuitive one's limit, added 10 Aug 2026:** that rule is about **number of stops**, not about compound. Once the number of stops is fixed by fuel — as it was at Laguna, where fuel forces a stop regardless — **the durability argument for a harder compound evaporates entirely** and you should take the softest compound that survives the stint. Do not let "fewer stops is right in GT7" bleed into "harder compounds are right in GT7." They are different claims and only the first is supported.

---

## 2. The tyre wear model

### 2.1 What 1.49 actually changed

**[CONFIRMED — official patch notes, gran-turismo.com]** Update 1.49's tyre section states that low-speed cornering stability and kerb interaction were improved, **"surface resistance (rolling resistance) has been optimized,"** and **racing tyre heat and wear characteristics were adjusted**. Wet grip reduction and hydroplaning were separately recalibrated.

> **⚠️ Note the wording overlap.** 1.71's notes contain nearly the same two lines — rolling resistance optimised, tyre heating and wear values adjusted. **PD are returning to terms they have tuned before, not touching them for the first time.** That is mildly reassuring about the *kind* of change (a re-tune rather than a rewrite) and says nothing at all about its size or direction.

**[TESTED]** Community breakdown of the resulting behaviour:
1. Tyres suffer a **significant performance drop past roughly 50% wear**, worth **over one second per lap**.
2. **Sliding and steering now generate more wear than braking and acceleration do.** This is the single most important change. Pre-1.49, wear tracked longitudinal load; post-1.49 it tracks lateral slip.
3. **Front tyres wear faster than rears**, particularly from sliding on entry, with rears "relatively unaffected" on many cars.
4. Left/right asymmetric wear became visible on some cars for the first time.

### 2.2 Linear or cliff?

**Both, in sequence.** The best characterisation available:

- **Phase 1 (0 → ~50% wear):** near-flat. **[TESTED]** "Tyres are very similar by lap times" through the early part of the cycle. Losses in this phase are on the order of tenths, not seconds. Do not panic-pit here.
- **Phase 2 (~50 → ~90% wear):** progressive degradation, order **0.5–1.5 s/lap** cumulative loss. Handling balance shifts before the stopwatch does — front-limited understeer on entry appears first on most Gr.3 cars.
- **Phase 3 (>~90–95% wear):** **cliff.** **[TESTED]** "At around 95% red there is basically no traction anymore." The car becomes genuinely undriveable, not merely slow. Rear breakaway without warning is the typical failure mode on RR and MR cars.

**Engineering implication for strategy modelling.** Do not fit a linear degradation model to GT7. Fit a **piecewise function**: flat, then linear, then a wall. The optimal stint length is "as long as possible without entering Phase 3," and because Phase 3 onset is sharp, **the cost of overshooting is far greater than the cost of undershooting.** Build one lap of margin into league strategy advice.

**[CONSENSUS caveat]** There are credible reports of the wear *indicator* over-reading remaining life on specific cars — most notoriously the Dodge Viper Gr.3, where drivers reported the car was sliding badly at a displayed 70% remaining. High-torque cars appear to lose *usable* grip well ahead of the displayed wear number. **Advise your league drivers to trust their lap times and the car's behaviour over the gauge.**

### 2.3 The indicator

**[TESTED]** The HUD tyre gauge is a **bar per corner that fills with red from one end as wear accumulates**. "The full white gauge represents 100% of no wear, half red bar 50% wear." The red range was visually widened in a post-launch update to make degradation more legible.

**Mapping colour to grip — important accuracy note.** GT7's wear indicator is **not** the classic GT1–GT4 blue/green/yellow/orange/red temperature-and-wear indicator. It is a **linear fill bar showing tread remaining, and it does not encode grip.** There is no published mapping from bar position to a grip coefficient, and the relationship is demonstrably non-linear because of the cliff (§2.2). Specifically:

- **~100% white → ~50% red:** grip is essentially intact. The bar has moved halfway; you have lost tenths.
- **~50% → ~90% red:** grip falling progressively. The bar's second half is worth vastly more lap time than its first half.
- **>~90% red:** grip collapse.

**In other words the bar is roughly linear in tread and roughly quadratic-then-discontinuous in grip.** A driver reading "half my bar is left" and assuming half their performance is left is making a large error in the safe direction, and a driver at 90% assuming they have 10% of a stint left is making a large error in the dangerous direction.

Note also **[TESTED]** that the same displayed bar position means different things on different compounds — a GT Sport-era observation but the mechanism (different total tread life per compound mapped onto the same-length bar) is unchanged.

### 2.4 Lap time lost per unit of wear

Consolidating what is measurable:

| Wear state | Approximate lap-time loss vs fresh (Gr.3, dry) | Confidence |
|---|---|---|
| 0–25% | ~0.0–0.15 s | [CONSENSUS] |
| 25–50% | ~0.15–0.4 s | [CONSENSUS] |
| 50% | ~0.4–0.6 s, balance shift begins | [TESTED, 1.49 breakdown] |
| 50–75% | rising to ~1.0–1.5 s | [TESTED] |
| 75–90% | 1.5–2.5 s, increasingly inconsistent | [CONSENSUS] |
| >90% | 2.5 s+ and effectively undriveable; corner-exit traction gone | [TESTED] |

**[TESTED, GT Sport-era but corroborated post-1.49]** In FF cars specifically, drivers report losing **up to 2 seconds per lap on worn tyres versus fresh** — the extreme end of the range, and consistent with front-limited wear being the dominant mode.

### 2.5 How driving style changes wear rate

Post-1.49, ranked by impact:

**1. Lateral slip / sliding — dominant.** **[TESTED]** 1.49 explicitly made "sliding and turning" the primary wear source. Any sustained slip angle beyond the peak-grip window burns tyre. Audible tyre squeal is the free telemetry: **if you can hear the tyres, you are paying for it.** A driver who slides the car to a 0.2 s/lap faster lap will lose that and more within four laps at any meaningful wear multiplier.

**2. Aggressive turn-in.** **[TESTED]** 1.49 increased understeer sensitivity to "premature or excessive steering input." Turning in early and adding lock mid-corner produces exactly the front slip the model now punishes. **The single biggest tyre-saving change most drivers can make is turning in later and using less total steering angle**, accepting a slightly wider entry.

**3. Wheelspin.** **[CONSENSUS]** Corner-exit spin is the primary rear wear source. On high-torque Gr.3 cars this can invert the normal front-biased wear. **[TESTED]** Running TCS 1–3 measurably reduces rear wear on spin-prone cars — but **[TESTED]** TCS costs up to **two tenths per corner** under the 1.49 model, so this is a real trade, not a free win. Rule of thumb: TCS 0–1 for sprints, TCS 1–2 for long high-wear stints on torque-heavy cars, TCS 3+ only for wet or damage-limitation. **⚠️ 21 Aug: 1.71 "optimised" TCS intervention behaviour. The two-tenths price is unknown on this version — `16` §12 Job 7.**

**4. Trail braking.** **[TESTED]** 1.49 increased oversteer sensitivity to trail braking. Heavy trail braking now generates combined-slip loading at the front and can provoke rear rotation — both wear-generating. **Trail braking is still the fast technique**; the change is that its wear cost went up. In a high-multiplier stint, shortening the trail phase and getting the car straight-braked earlier is a valid tyre-saving lever worth perhaps a tenth a lap. **⚠️ 1.71 adjusted ABS "cornering brake behaviour," which names this phase directly.**

**5. Braking and acceleration in isolation.** **[TESTED]** Explicitly *demoted* by 1.49 relative to sliding. Straight-line braking, even hard, is comparatively cheap. Front lock-ups without ABS remain expensive.

**6. Kerbs.** **[CONSENSUS]** 1.49 and 1.55 both changed damper/kerb interaction, and the community position is that kerbs cost tyre life through the load spike and the momentary slip on re-contact. Effect size is unmeasured and probably second-order compared to items 1–3. **[TESTED]** Off-track excursions cost more: 1.55 made tyres pick up dirt with a grip penalty, though it also made them **"clean off quicker"** than before. **⚠️ 1.71 changed both damper attenuation and off-track grip loss on "Real."**

**7. Track width usage.** **[TESTED]** Using the full width of the road to maximise corner radius reduces peak lateral load and is a genuine, free tyre-saving measure. This is the one technique that is simultaneously faster and kinder.

**8. Elevation change — [WITHDRAWN as a wear factor].** Earlier working notes assumed that heavy elevation change (Laguna's 55 m, Bathurst, Sainte-Croix) adds wear through vertical load cycling. **There is no evidence for this anywhere**, and the one circuit where it was built into a prediction produced a wear result 1.8× better than modelled (§1.3.1). Do not apply an elevation penalty until someone measures one.

### 2.6 Front/rear asymmetry by drivetrain

**[TESTED, GT Sport-era ordering, confirmed directionally post-1.49]** Ranking from kindest to harshest overall tyre usage: **FR > MR > 4WD > FF.**

| Layout | Wear bias | Notes |
|---|---|---|
| **FF** | Heavily **front** | Worst case. Fronts do steering *and* traction *and* most braking. **[TESTED]** "Atrocious" tyre wear; 4WD cars that were behind early "easily catch up and get past" as the stint develops. Dominant on power tracks (Monza, Le Mans), destroyed on handling tracks (Nürburgring GP, Tokyo Central). |
| **FR** | Mild **front** bias post-1.49 | The most balanced layout. Front bias comes from the 1.49 entry-slide wear mechanism rather than from traction. |
| **MR** | Varies by car — **this is the key finding** | **[TESTED]** Lago Maggiore Gr.3 MR test: Huracán **rear**-biased and undriveable by lap 6–7; McLaren 650S **rear**-biased "by a bit" but the longest-lasting car tested; Porsche 911 RSR **even front-to-rear**. MR cars are not a homogeneous category for tyre life. |
| **RR** | **Rear** | Rear weight bias plus rear traction. Combined with 1.49's sharper oversteer sensitivity, RR cars punish trail braking hardest. Typically want brake balance forward. |
| **4WD** | Most **even**, moderate total | Traction split across four corners. Middle of the field on absolute life but the flattest degradation curve, which makes 4WD strong in long stints and in changeable conditions. |

**Balancing the wear with brake bias.** **[TESTED]** Shifting brake balance **rearward reduces front wear**, and this is the standard fix for front-limited cars — it was one of the few interventions in the GTPlanet suspension/wear thread with actual test support behind it. Shifting forward saves the rears on RR/MR cars. This is a *free* adjustment: it is available mid-race via the MFD, so drivers can rebalance wear on the fly as a stint develops. **This should be in your league's briefing pack.** Note **[TESTED]** that 1.49 made brake bias have a "more noticeable effect on the car's stability" than before, and that many fast drivers now run BB 0 as the baseline.

---

## 3. Tyre temperature and pressure

> **⚠️ This section is the one 1.71 most directly put in play. "Tyre heating and wear values have been adjusted" is an explicit statement that heat is a live, tuned parameter. See `16` §12 Job 6 — logging `tyreTemp[4]` across a stint is now the highest-value original test available, and it was already the highest-value one before the patch.**

### 3.1 Temperature — yes, it is modelled

**[CONFIRMED]** GT7 exposes a **`tyreTemp[4]`** field in its UDP telemetry stream, per corner (FL, FR, RL, RR). Temperature is unambiguously simulated. **[CONFIRMED]** 1.49's patch notes explicitly list adjustment to **"racing tire heat and wear characteristics,"** confirming heat is a live, tuned part of the model. **1.71's notes repeat the same kind of statement.**

**[CONSENSUS]** The community assessment is that it is **real but rudimentary** — "it's always been in the game, but they don't really talk about it, probably because it's quite rudimentary." There is no evidence of a multi-layer carcass/surface/core thermal model of the kind ACC or iRacing run. Expect a single bulk temperature per corner. **⚠️ Note that `04` §6.1 goes further and calls temperature "functionally invisible in practice." These two documents disagree, they always have, and 1.71 makes the disagreement worth settling.**

### 3.2 What it does to grip

**[TESTED]**
- **Cold tyres have materially less grip.** Braking distances are noticeably longer on an out-lap. Drivers consistently report fresh tyres "feel a bit off at first" after a stop.
- **Warm-up takes roughly 2–3 corners**, not 2–3 laps. GT7's warm-up is fast compared to modern sims.
- Under-temperature symptoms: **"a slight disconnected feeling to the road when steering and a lack of overall grip when accelerating and braking."** Vague front end plus poor traction is the signature.
- **Ambient and track temperature matter.** Drivers report tyres being "better towards the end than at the beginning, because the track itself is colder at night" — i.e. GT7 models a track-temperature interaction, and in hot conditions overheating is a real effect, not just cold-tyre warm-up.

**[UNVERIFIED]** **No one has published the optimal temperature window per compound in degrees.** A direct GTPlanet thread asking this question ("GT7 Tire Temperature windows") received no numerical answer. FILO Engineering references temperature threshold tables in °C and °F and per-track starting temperatures, but the values are not in the accessible text. **If you want a temperature window for your league, you will have to derive it: log `tyreTemp` via SimHub/GT7 telemetry, sweep pace, and correlate against sector times.** This is the highest-value original testing available to you and nobody has done it publicly.

### 3.3 Out-lap procedure

Practical guidance, **[CONSENSUS]**:
- Weave *gently* — GT7's warm-up responds to lateral load, but aggressive weaving on cold tyres generates slip, which generates wear, which under 1.49 is expensive.
- Prioritise **braking energy** over steering: two or three firm straight-line brake applications warm the fronts faster and more cheaply than scrubbing.
- Budget approximately **one corner-complex of caution**, then commit. GT7 does not reward a full slow out-lap; you will lose more track position than you gain in tyre temperature.
- **In a league with an in-lap/out-lap under a pit-stop-required format, the out-lap deficit is typically 0.5–1.5 s** — build this into any undercut calculation.

### 3.4 Tyre pressure — no

**[CONFIRMED, and this matters because it is frequently misstated]** **GT7 has no tyre pressure adjustment.** It is not in the tuning menu, it is not in the MFD, and it is not displayed anywhere in the HUD or telemetry. Pressure is not a tunable parameter and there is no evidence it is dynamically simulated as a driver-visible variable at all. **Unchanged by 1.71.**

Corollaries for league regulation:
- You cannot regulate pressures, mandate minimum pressures, or use pressure as a BoP lever.
- **Camber is your only static contact-patch adjustment** (§8.3), which is why it carries more weight in GT7 than in sims that expose pressure.
- Anyone offering you a "GT7 optimal tyre pressure" setup sheet is either confused with another title or fabricating.

---

## 4. Wear and fuel multipliers

### 4.1 What the multipliers actually do

**[CONFIRMED]** The multipliers are **simple linear rate scalars**. "1x means real. 2x means it depletes twice as fast. 3x means it depletes 3 times as fast." Equivalently and more usefully: **at a multiplier of N, each lap driven counts as N laps of wear (or N laps of fuel burn).**

This is worth stating plainly because it is the property your whole league calendar depends on: **the multipliers do not change the shape of the degradation curve, only its horizontal scale.** The 50% inflection and the 90–95% cliff occur at the same *fraction of tyre life* regardless of multiplier; the multiplier just determines how many laps that fraction takes. This means:

- **Stint length in laps ∝ 1/N.** Doubling the multiplier halves the stint.
- **Lap-time loss per lap of a stint ∝ N.** At 10x, you lose ten times as much pace per lap as at 1x.
- **A stint length calibrated at one multiplier converts exactly to another.** If a compound lasts 20 laps at 4x, it lasts 10 at 8x and 40 at 2x.

**[TESTED, minor caveat]** The linearity assumption is what everyone uses and it holds well, but the standard community calibration method explicitly flags that it "assumes tyre wear is consistent each lap," which is only true if the driver's pace and style are consistent. In practice a driver's *own* variance is a larger error term than any non-linearity in the multiplier.

> **⚠️ Documented conflict with the playbook — read this before relying on the conversion.** `08-playbook-leon.md` §C4 downgrades this same claim to **[ASSUMED — widely used, never tested]**, on the grounds that the evidence is two informal forum statements plus a calibration method that *assumes* linearity rather than demonstrating it. That is a fair criticism of the [CONFIRMED] tag used above, and **the playbook's more conservative reading should win** — the tag here overstates the evidence.
>
> **Our own 10 Aug 2026 measurement does not resolve it.** A single-multiplier result cannot distinguish "base rate lower than modelled" from "2× gentler than linear," and both remain live (§1.3.1). The practical rule is unchanged and cheap: **calibrate at the multiplier you will actually race.** Do not calibrate at 50× and convert down.
>
> **21 Aug 2026:** the multiplier *mechanism* is not something 1.71 is likely to have touched — it scales a rate. **The rate it scales did change.** So this section's logic survives and every number it has ever been applied to does not.

### 4.2 The available range

**[CONFIRMED]** Custom Race and lobby settings both expose independent **Tyre Wear** and **Fuel Consumption** multipliers, each settable to **Off** or a positive integer multiplier. Sport Mode Daily Races use values from 1x to 8x in current practice.

**[UNVERIFIED — verify in your own build before writing regulations]** The maximum available value differs between Custom Race and Online Lobby and has changed across updates. Community testing methodology references using **50x** in a Custom Race / Time Trial context for rapid wear calibration. Values above ~20x are essentially only useful as a measurement instrument, not as a race format — **and per §4.1, a high-multiplier calibration converted down to a low race multiplier is exactly the inference our Laguna result casts doubt on.**

### 4.3 Calibration data from Sport Mode (2025–2026)

Polyphony's own race designers are the best available source of "what multiplier produces what strategy," because these events are tuned to force a specific number of stops. Recent verified combinations:

| Date | Track / Class | Laps | Tyre | Fuel | Compounds | Resulting strategy |
|---|---|---|---|---|---|---|
| Mar 2026 | Kyoto Yamagiwa Rev, Gr.4 | 14 | **4x** | 3x | RS + RM, both mandatory | Forced 1 stop; RS first, RM long second stint |
| May 2026 | Dragon Trail Seaside, Gr.4 | 11 | **4x** | 2x | RH + RM | "A stop to swap compounds is unavoidable" — forced 1 stop |
| Dec 2025 | Red Bull Ring, Gr.3 | 12 | **6x** | 2x | RM + RS | Forced 1 stop; "wringing the most out of the Softs before they drop off a cliff is of vital importance" |
| Mar 2026 | Trial Mountain Rev, Gr.3 | 11 | **8x** | 3x | RH mandatory | Forced 1 stop; RM-then-RH or RH-then-RM both viable |
| 2024 | Road Atlanta, Gr.3 | 15 | **4x** | 2x | RM + RS mandatory | Forced 1 stop |
| Aug 2026 | Tokyo Expressway East, Gr.3 | 10 | 1x | 1x | RH | No stop, pure pace |
| Aug 2026 | Monza / Red Bull Ring | 4–5 | 1x | 1x | SS / RM | No stop |

**The pattern is consistent and very usable:**

> **Sprint (no stop): 1x tyre, 1x fuel, 4–10 laps.**
> **One-stop strategy race: 4x–8x tyre, 2x–3x fuel, 10–15 laps.**

Notice that Polyphony **scales tyre wear roughly 2x harder than fuel**. This is deliberate: it makes the *tyre* the binding constraint and the fuel a secondary consideration, which produces more interesting racing than a fuel-limited race where everyone stops on the same lap. **I would recommend you copy this ratio.**

> **⚠️ 21 Aug 2026: every row above is a v1.70 event, designed against v1.70 wear.** PD will re-tune Daily Race multipliers to the new model, and when they do, this table rebuilds itself for free — **watch the first few post-1.71 Daily Race configurations, they are the cheapest calibration signal available and they cost nothing to read.** Until then the only part worth carrying forward is the *ratio* (tyre scaled ~2× harder than fuel), which is a design philosophy rather than a physics measurement.

> **Note on our own 20-lap / 2× tyre / 3× fuel Laguna event:** it inverts Polyphony's ratio — fuel is scaled *harder* than tyres. The measured outcome (§1.3.1) confirms the consequence: **tyres comfortably cover the race in two stints and fuel is the binding constraint.** That produces the convoy-racing risk this section warns about, since everyone's stop window is set by the same fuel number rather than by their own tyre management. Worth raising with whoever set the multipliers.

### 4.4 Deriving stint length for your own formats

**Method — 15 minutes per car/track/compound combination.** **⚠️ 21 Aug: the method is intact and is exactly the right instrument. Every output it has produced so far is a v1.70 number. Re-run it.**

1. Open a Custom Race or lobby at the target track with the target car and compound.
2. Set tyre wear to the **multiplier you will actually race** — see the §4.1 warning about calibrating high and converting down.
3. Run **3 laps at genuine race pace** (not qualifying pace, not cruising), **from a representative fuel load**.
4. Read the wear gauge. Compute **w = (wear consumed) / 3** = wear fraction per lap.
5. Stint length **L = 0.85 / w**.

Use **usable fraction = 0.85**, not 1.0. You want the stint to end before the cliff at ~90%, with a lap of margin. **⚠️ 0.85 is derived from the 1.49 cliff position. If 1.71 moved or removed the cliff, this constant moves with it — which is why Job 2 in `16` §12 says run to *felt* fall-off rather than to a gauge number.**

**[Added 10 Aug 2026]** Two procedural notes from the Laguna run, which is the only time this method has actually been executed in-house:

- **Run from full fuel.** A light-fuel calibration run flatters the number; the heaviest part of a stint is the start.
- **Run it long enough to see the fall-off, not just to read the gauge.** The useful output was "11–12 laps *then falling off*" — a behavioural observation, not a gauge reading. Given §2.3's warning that the gauge does not encode grip, the felt fall-off point is the better datum.

### 4.5 Recommended multipliers by format

For a mixed-format league, **[CONSENSUS + derived from §4.3]**. **⚠️ 21 Aug: void as regulation guidance until a v1.71 stint is measured.** If wear got faster these produce more stops than intended; if slower, fewer. **Do not publish league regulations from this table yet.**

| Format | Race length | Tyre | Fuel | Expected stops |
|---|---|---|---|---|
| Sprint | 5–8 laps / ~10 min | Off or 1x | Off or 1x | 0 |
| Feature sprint | 10–12 laps / ~20 min | 3x–4x | 2x | 0–1 (strategy choice — the best format for close racing) |
| Standard one-stopper | 12–16 laps / ~25–30 min | 5x–7x | 2x–3x | 1 forced |
| Two-stopper | 20–25 laps / ~45 min | 8x–10x | 3x–4x | 2 |
| Mini-endurance | 60 min | 6x–8x | 3x–4x | 2–3 |
| Endurance | 90–120 min | 4x–6x | 2x–3x | 3–4 |
| "Realistic" endurance | 2 hr+ | 1x–2x | 1x–2x | Fuel-limited only |

**Three warnings from the record:**

1. **[TESTED]** At **1x, tyre wear is effectively a non-event.** Multiple drivers report that at 1x "you never would have to fuel" and tyres last indefinitely. If you want strategy, you need 3x minimum. **[MEASURED — IN HOUSE] 2× is closer to the 1× end than expected**: it gave 11–12 laps on the *softest* compound on a car with a reputation as the second-worst in its class for wear. **Treat 2× as a barely-strategic multiplier, not a demanding one.**

2. **[TESTED]** Post-1.49, wear rates went up substantially at a given multiplier. One driver's benchmark: *"I could do an entire Spa 1 hour race on a single set of RH tyres… now they just last 1 stint of 8 laps."* **If your league has settings inherited from before July 2024, they are producing roughly twice the stops you intended. Re-calibrate.** ⚠️ Note this claim sits uneasily beside our measurement — either that benchmark is from a much higher multiplier, or wear varies far more by circuit and car than the generic figures imply. **Another reason to measure rather than infer.**

3. **Road cars are disproportionately punished.** **[TESTED]** Under the 1.49 model, road cars on Comfort/Sports compounds degrade far worse than race cars, with some "nearly undriveable after 4 laps" at elevated multipliers. **Use lower multipliers for road-car classes than for Gr.3/Gr.4 — roughly half.** *(Relevant to the Shelby programme, and unverified on 1.71.)*

### 4.5.1 Spec III regulation tools (v1.65+)

**[CONFIRMED]** Spec III (v1.65, Dec 2025) added lobby settings that materially expand what a league can enforce:
- **Minimum Number of Pit Stops** — enforce a one- or two-stopper directly.
- **Required Tire Type Change** — force use of two compounds.
- **Slipstream Strength: Disabled** — new option; previously the weakest setting was still non-zero.
- New regulation filters: **Year range, Drivetrain, Aspiration**.

If your league regulations pre-date December 2025 and use text rules for mandatory stops, **move them into the lobby settings.**

**⭐ Added 21 Aug 2026 — the 1.71 addition to this list: the "Championship" mechanical damage setting.** Light's damage severity, triggered from more minor collisions, with recovery time varying by severity. It is a genuinely useful middle option for a no-BoP league — it prices contact without ending races. See `16` §9.

---

## 5. The fuel model

> **⚠️ 21 Aug 2026 — the quiet 1.71 exposure.** "Road surface resistance (rolling resistance) has been optimised" is a **fuel** term as much as a tyre term, and it is also a **terminal-speed and gearing** term. Every L/lap figure in §5.2 may have moved without anything the driver does changing. Tank capacity and fuel-map structure are unaffected.

### 5.1 Tank capacity

**[CONFIRMED — read directly from the UDP telemetry `fuelCapacity` field]**

- **Most cars: 100 litres.** This is a hard standardisation, not a coincidence — it applies to a Honda S660 and an LMP1 alike.
- **Karts: 5 litres.**
- **Electric cars: 0.**

**[CONFIRMED]** `fuelLevel` is reported in litres, so telemetry gives you exact consumption rather than the HUD's percentage.

**Consequence for league engineering:** because every car has the same 100 L tank, **fuel range is purely a function of consumption rate**, and consumption differences between cars translate directly into stint-length differences. This is a real, un-BoP'd performance differentiator.

### 5.2 Burn rate

**[TESTED]** Fuji Speedway, Gr.3, BoP on (mid-speed), RM, driven to the red zone as in a final-lap scenario, **2x fuel multiplier**:
- **Best: 3.1 L/lap** — Lexus RC F GT3 '17, Aston Martin DBR9, Ford GT LM Test Car
- **Worst: Peugeot L500R/VGT Gr.3**, over **1 L/lap** worse than the best
- **Porsche 911 GT3 R (992) '22** singled out as the best economy/pace compromise under then-current BoP
- 45 of 50 cars within 1 second of each other at Fuji — **pace is BoP'd tightly; fuel economy is not**

At 2x, 3.1 L/lap → **1.55 L/lap at 1x** → **~64 laps of Fuji on a tank at 1x**. At 2x fuel that's ~32 laps; at 4x, ~16.

**[TESTED]** Normalised consumption by class (Spa, 10x multiplier, Comfort Soft, BoP on), best in class:
| Class | Best | L/100 km |
|---|---|---|
| Gr.1 | Porsche 919 Hybrid '16 | 27.13 |
| Gr.4 | Audi TT Cup '16 / Honda NSX Gr.4 | 32.84 |
| Gr.2 | Nissan GT-R Nismo GT500 '16 / NSX Concept-GT '16 | 34.27 |
| Gr.3 | Jaguar F-type Gr.3 / Nissan GT-R Nismo GT3 '13 | 41.40 |

Note **Gr.1 hybrids are dramatically more economical than Gr.3** — a factor that dominates Gr.1 endurance strategy.

**[TESTED]** Consumption is highly sensitive to power modifications: on a test car, a fully upgraded engine consumed **+35% fuel for −8 s lap time**, while a fully restricted engine used **−55% fuel for +19 s lap time**. Broadly, **fuel scales worse than linearly with power**, which is why fuel maps beat de-tuning (§5.4).

> **⚠️ Note for restricted builds.** That −55% figure is for a *fully* restricted engine. Our Laguna car runs restrictor 70, which should be buying a meaningful economy gain over an unrestricted equivalent — a reason to expect the modelled 17–19 lap fuel range to be **pessimistic**, in the same direction the tyre model was wrong. Measure before planning around it.

### 5.3 Fuel weight and lap time

**[TESTED]** A full 100 L petrol tank weighs approximately **73 kg** (≈88 kg for diesel). GT7 models this as real mass.

**[UNVERIFIED — this is a genuine gap]** **No one has published a controlled measurement of seconds-per-litre in GT7.** The forum record contains anecdote and an active minority arguing it's placebo. There is no test with stated methodology.

**Recommended working figure, derived rather than measured:** using the standard motorsport approximation of **~0.03 s per lap per 10 kg** on a typical 90-second circuit, 73 kg of fuel is worth roughly **0.20–0.25 s/lap between full and empty**, i.e. **~0.003 s per litre per lap**, scaling with lap duration. **You should measure it yourself** — it's a 30-minute test and it directly affects every undercut calculation.

**Strategic consequence:** at ~0.2 s/lap full-to-empty the fuel weight effect is real but **second-order compared to tyre degradation**. The main exception is qualifying, where GT7 Sport Mode qualifying runs an empty tank by default — meaning **your qualifying setup is a low-fuel setup and your race setup is not.**

### 5.4 Fuel maps

**[CONFIRMED — official Gran Turismo World Series guide, gran-turismo.com]** GT7's fuel map is a **six-level** control adjusted via the MFD (D-pad). **"Setting this meter to Level 1 will give them the most power, but it'll also use more fuel."**

> **Direction: 1 = richest / maximum power / maximum consumption. 6 = leanest / minimum power / minimum consumption.**

**Accuracy note.** Several third-party outlets state the range is 1–5, and at least one states the direction is inverted. **They are wrong.** The official Polyphony source is unambiguous on both count and direction.

**Requirement:** a **Fully Customisable Computer** (4,500 Cr) must be fitted for the fuel map to be adjustable on a road car. Gr.1–Gr.4 race cars have it as standard.

### 5.5 The power/consumption trade at each map

**[TESTED — GT Sport-era; the mechanism was not changed by 1.49 and the community continues to use it, but treat the exact percentages as approximate]** **⚠️ 21 Aug: 1.71 introduced a new engine torque control map. §10 item 6 — "whether the 4%/8% rule survived 1.49" — is now "whether it survived 1.71," and it is more likely to have moved than before.**

The measured rule: **each step of fuel map reduces power by ~4% and fuel consumed by ~8%.**

| Map | Power | Fuel consumed | Notes |
|---|---|---|---|
| **1** | 100% | 100% | Race pace, overtaking, final stint |
| **2** | ~96% | ~92% | The default "free" saving — the cheapest step on the ladder |
| **3** | ~92% | ~84% | Standard cruise setting |
| **4** | ~88% | ~76% | Meaningful pace loss appears |
| **5** | ~84% | ~68% | Defensive / heavy-save |
| **6** | ~80% | **~50%** | Non-linear final step |

**Map 6 is the anomaly and the key insight.** The final step gives roughly **double the marginal saving** of the intermediate steps. **[TESTED]** Corroborated in GT7: FM6 delivered **79% fuel remaining** on a Jaguar F-type where an equivalent ECU reduction to 85% delivered only **68% remaining** — **"fuel maps are more fuel efficient than reducing the power via the power restrictor and the ECU."**

**[TESTED]** There is **no reliable conversion between fuel map and ECU%/restrictor%** — the effects differ across NA, turbo, and supercharged engines. Don't try to BoP by substituting one for the other.

**Practical map usage:**
- **[TESTED]** Real endurance example (Peugeot L750R, Gr.1): FM6 achieves ~10 laps per tank at Road Atlanta, but *"with fuel maps 3 and lower you will be gaining ground."* The winning strategies used **2–3 stops at low maps** rather than one long FM6 stint — **the fuel-saving stint was slower than the extra pit stop.** Always check this.
- **[CONSENSUS]** The strong general play is a **dynamic** map: FM1 in traffic and on overtakes, FM5/6 when in a slipstream. Saving fuel in a tow costs almost nothing.

### 5.6 Fuel-saving techniques

Ranked by efficiency (fuel saved per second of lap time surrendered):

**1. Slipstream saving — best ratio, effectively free.** **[TESTED]** Dropping the fuel map while in another car's tow is the highest-value technique in GT7. In a Gr.3 pack race, a driver who disciplines themselves to hit FM5/6 every time they're in a tow can save 10–15% of a stint's fuel for near-zero lap time.

**2. Short shifting.** **[TESTED]** Shifting before the limiter cost **~0.5 s/lap and cut fuel consumption by 20%.** Better than most fuel-map steps. It also **reduces rear tyre wear** by keeping the engine out of the peak-torque region on exit — a genuine double win, and the first thing to teach drivers in a high-multiplier league. *(This is the technique that won the 17 Aug Watkins Glen race, via the Pit Crew shift beep.)*

**3. Fuel map 6 in isolation.** ~50% consumption for ~20% power. Best deployed as a *segment* tool — FM6 down the long straights only.

**4. Lift and coast.** **[TESTED]** Similar fuel-saved-per-second-lost ratio to fuel map settings — not superior, but *additive*, applicable per-corner, and it also reduces brake and tyre load. Coast 50–100 m early into the heaviest braking zones only.

**5. Longer gearing.** **[CONSENSUS]** Taller final drive cuts consumption. Worth doing on power circuits; counterproductive on tight ones.

**6. Reduced downforce / drag.** **[CONSENSUS]** Less drag = less fuel. On a technical circuit it costs tyre life (§8.4), so it's a poor trade there.

**7. Weight reduction.** **[CONSENSUS]** Mostly a car-choice consideration.

**A caution on interaction:** fuel maps and tyre wear are **coupled**. A leaner map produces less torque, which produces less wheelspin, which reduces rear wear. **In the closing laps of a high-wear stint, FM2–3 is often faster than FM1** because the traction you gain exceeds the power you lose. Very few drivers do this.

---

## 6. Pit stops

> **21 Aug 2026 — this section is the least exposed in the document.** Pit travel time is a track constant, refuel rate is an event property, and 1.71 touched neither. Use it with confidence. The one second-order effect: **the volume of fuel needed changes if rolling resistance moved L/lap**, even though the cost per litre does not.

### 6.1 Pit lane time loss

**[TESTED, but the best available data is old — this is a real gap for GT7 specifically]** The most complete published pit-delta table is GT5-era. Directionally useful for track *ranking* only:

| Track | Pit delta (s) |
|---|---|
| Circuit de la Sarthe | ~44 |
| Daytona Road Course | ~40 |
| Nürburgring Nordschleife | ~28 |
| Circuit de la Côte d'Azur (Monaco) | ~29 |

Methodology worth adopting: measure **from the point the game takes over on pit entry to the point it hands control back on exit**, minus the time to cover that same distance on track.

**[TESTED, GT Sport-era]** Full stop durations including drive-through:
- **Mount Panorama, Gr.3:** 30.28 s (48% fuel taken) to 36.10 s (89% fuel taken)
- **Circuit de la Sarthe, Gr.1:** 35.93 s (40% fuel) to 40.77 s (74% fuel)
- **Autodrome Lago Maggiore Centre:** ~15.5 s

**Two findings that matter more than the absolute numbers:**

1. **[TESTED]** *"Pit travel time + tyre change time is locked for each track variant."* The fixed component is a **track constant, not a car variable**. Measure once per track and it's valid for your whole grid.
2. **[TESTED]** The **only** meaningful variable is fuel taken, at roughly **0.5–1.0 s per 10% of tank**.

**[TESTED]** There is a long-standing quirk in which contact with the pit wall on entry shaves ~0.5 s off the stop by skipping animation frames. Treat as a bug; consider banning it in league regulations.

**Practical planning figures [CONSENSUS, derived from the above]:**
- **Short pit lanes** (Lago Maggiore, Tsukuba): **15–22 s**
- **Typical GP circuits** (Spa, Brands Hatch, Red Bull Ring, Fuji, Interlagos, **Laguna Seca ~18–20 s**): **22–32 s**
- **Long pit lanes** (Le Mans, Daytona, Nürburgring 24h, Tokyo Expressway): **35–45 s**

**Measure your league's tracks.** A 25 s assumption on a track that's actually 38 s will invert every strategy call you publish.

### 6.2 Refuelling rate

**[TESTED]** *"All cars in-game are at 100 L fuel tanks, refuel rate is room/race set and not car-dependent."*

1. **Refuel rate is a property of the event, not the car.** **[CONSENSUS]** Some events appear to run different refuel multipliers, meaning Polyphony scales refuel rate alongside the fuel consumption multiplier so fill time stays proportionate to burn.
2. **[UNVERIFIED]** The absolute rate in litres/second is **not published**. The observable proxy implies roughly **10–20 seconds to fill from empty**, i.e. on the order of **5–10 L/s** — inference, not measurement.

**[TESTED]** There is a **5–10 second dead time** at the start of every stop before refuelling begins. Part of the fixed track constant.

### 6.3 Tyre changes and partial changes

**[CONFIRMED]** In the pit menu the driver selects a tyre compound **or selects "don't change tyres."** Refuelling then begins automatically and can be stopped at any point. A **diamond marker** on the fuel gauge indicates the fuel required to reach the finish — GT7's built-in strategy calculator, and it is accurate.

**Partial tyre changes: NO.** **[CONFIRMED]** GT7 does **not** support changing only the fronts or only the rears, and there is **no option to fit different compounds front and rear.**

This interacts badly with §2.6:
- On a strongly front-limited car, you are throwing away substantial rear life at every stop.
- You **cannot** solve axle-asymmetric wear with a pit strategy. **The only levers are brake balance (mid-race, via MFD) and setup (§8).**

### 6.4 Computing the optimal stop strategy

**Inputs to gather:**
- `P` = pit lane time loss, seconds (§6.1) — track constant
- `F` = refuel time penalty ≈ 0.075 s per % of tank taken
- `Δ` = compound lap-time delta, s/lap (§1.2) — **measure, don't assume**
- `L_max(c)` = laps before compound *c* reaches ~85% wear at your multiplier (§4.4) — **measure, don't model (§1.3.1)**
- `D(c, n)` = cumulative degradation loss at lap *n* of a stint — piecewise per §2.2
- `W` = fuel weight penalty ≈ 0.003 s/L/lap (§5.3 — measure this)
- `R` = race distance in laps

**Shortcuts that hold in GT7 specifically:**

1. **The cliff dominates.** The problem reduces to **"which set of stint lengths, all ≤ L_max, minimises the number of stops while keeping me on the fastest compound I can sustain?"** *(⚠️ conditional on the cliff surviving 1.71.)*

2. **The one-stop test.** Strategy A (one stop, harder compound) beats Strategy B (two stops, softer compound) when:
   > **P + F·fuel > Δ_compound × R_softer_laps + (degradation saved)**

   With GT7's slow pit stops and small compound deltas, **the pit loss usually wins. Fewer stops is right in GT7 more often than in most sims.** *(Pit loss is unaffected by 1.71; the compound delta and degradation terms are not.)*

3. **⚠️ But when the stop count is already fixed by fuel, the compound question decouples entirely** — take the softest compound that survives the stint. See §1.4.

4. **The undercut is weak in GT7.** The out-lap cold-tyre penalty (§3.3, ~0.5–1.5 s) plus the long pit delta means the undercut needs a large tyre-condition difference to pay. The **overcut is comparatively strong**. Advise your drivers accordingly; most sim racers arrive with F1-derived undercut instincts that don't transfer. *(Exception: circuits where overtaking is near-impossible and track position outweighs the arithmetic — Laguna is one ⚠️ *[re-flagged 11 Sep 2026: no in-house measurement supports the exception, and the one stop measured at a hard-to-pass circuit, Deep Forest, paid a 1.41 s out-lap - see `05`'s banner]*.)* **⚠️ The out-lap penalty term depends on tyre warm-up, and 1.71 adjusted heating values. If warm-up got slower, the undercut got weaker still; if faster, it got stronger.**

5. **Take fuel only to the diamond, plus one lap of margin.**

---

## 7. Wet weather

### 7.1 What GT7 models

**[CONFIRMED]** GT7 simulates:
- **Dynamic weather** with a **rain radar / weather map** in the MFD
- A **track wetness state** that evolves as rain falls and the surface dries
- **Aquaplaning / hydroplaning as a distinct physics effect** — 1.49 explicitly recalibrated it
- **Standing water** modelled separately from a merely damp surface
- **Surface contamination** — 1.55 altered wet/dirty grip loss and made tyres **clean off quicker**

**[CONFIRMED]** Both 1.49 and 1.55 changed wet behaviour. **Any wet-weather guidance from before 2025 should be re-verified.** **⚠️ 1.71 adjusted off-track grip loss on the "Real" setting and reworked the slipping regime, where wet compounds spend most of their life. Treat this whole section as suspect on v1.71 — the reasoning in §7.5 should survive directionally, the numbers in §7.2 should not.**

### 7.2 The wet grip curve

**[TESTED]** At **Spa in daytime heavy rain, Heavy Wets were ~7–8 s/lap faster than Intermediates.** At the same track at dawn with lighter rain, that gap collapsed to **0.2 s/lap.**

A ~40x change in compound advantage across a modest change in rainfall. Practical reading:

- **Wet compound choice is very high-stakes and very condition-sensitive.**
- **The gap is asymmetric.** Being on wets when you should be on inters costs you a little. Being on inters when you should be on wets costs you the race. **Err wet.**

**[TESTED]** Slicks in the rain are **not slow, they are unusable.** There is no heroic slick-in-the-wet play in GT7.

**[TESTED]** Sports Softs are *"still ok enough in the wet with some cars, far better than racing slicks."* Worth knowing for road-car classes without access to Racing Intermediates.

### 7.3 Aquaplaning

**[TESTED]** Modelled as a **sudden, largely unwarned loss of grip** in standing water. **Speed-dependent and location-dependent** — puddles form in consistent, learnable places.

- **Puddle locations are the wet line.** GT7 models **water accumulation in specific spots** rather than a rubbered-in dry line. The wet line is about **avoiding standing water**.
- **Aquaplaning is not recoverable.** The only mitigation is speed reduction before entering the water.
- **[CONSENSUS]** GT7's rain visuals do not reliably indicate physics severity. **Trust the track wetness indicator, not the windscreen.**

### 7.4 Choosing and timing wet tyres

| Condition | Compound |
|---|---|
| Damp, drying, light rain, dawn/dusk | **Intermediate** |
| Sustained rain, midday, standing water forming | **Heavy Wet** |
| Spa in rain, any time of day | **Heavy Wet** — this track pools badly |
| Night + rain | **Heavy Wet** |

**Time of day matters materially** — track temperature drives evaporation and standing-water accumulation.

**Timing the change.** Wet compounds degrade very fast, so the dominant error is **going to wets too early** on a drying track. But slicks in genuine rain are unusable, so going to wets too late is a race-ender. Procedure:
1. Watch the **rain radar**, not the sky.
2. Change **on the lap the radar shows the cell arriving**.
3. When drying, **stay out one lap longer than feels right.**

### 7.5 Wet setup

| Parameter | Wet direction | Why |
|---|---|---|
| **Downforce** | **Increase toward maximum** | Grip is scarce, speeds are lower, drag cost is small. The single most valuable wet change. |
| **Ride height** | **Raise slightly, both ends** | Reduces aquaplaning susceptibility; softens the platform. |
| **Springs / natural frequency** | **Soften** | Softer = more progressive load build = more warning before breakaway. |
| **Anti-roll bars** | **Soften both ends** | Keeps all four tyres loaded over uneven wet surfaces. |
| **Dampers** | **Reduce compression and expansion a few clicks** | Slower load transitions = fewer sudden grip losses. |
| **Camber** | **Reduce** | Maximum contact patch under straight-line braking and traction. |
| **Toe** | **Toward neutral** | Scrub is grip you can't afford. |
| **LSD acceleration sensitivity** | **Reduce significantly** | A locking diff in the wet produces simultaneous four-wheel breakaway. **The most underrated wet change.** |
| **LSD initial torque** | **Reduce** | Improves low-speed rotation on a wet surface. |
| **Brake balance** | **Forward 1–2 clicks** | Rear lock-up in the wet is the most common spin cause. |
| **TCS** | **Raise to 2–4** | The one situation where the TCS penalty is comfortably worth paying. |
| **Gearing** | **Lengthen lower gears** | Reduces the torque available to spin the wheels. The more common wet approach in GT7. |

> **⚠️ 21 Aug: if the LSD floor really did drop to 0 (`16` §5), the two LSD rows above gain new territory below them for the first time.** "Reduce significantly" and "reduce" were written against a floor of 5. Worth a deliberate wet test once the range is confirmed.

---

## 8. Setup consequences

> **⚠️ 21 Aug 2026 — mixed exposure, read the banner's §8 row before using this section.** §8.1's core principle is vehicle dynamics and survives as reasoning; whether it still describes GT7's wear function is open. **§8.3 (camber) is the most likely single item in this document to have changed**, because 1.71 reworked per-car steering geometry — the exact model that produced GT7's anomalous camber behaviour. **§8.5 (LSD) is written against the v1.70 5–60 range; on v1.71 every car in `range_records` reads 0–30 / 0–100 / 0–100, so its numbers are a direction only.**

### 8.1 The core principle

GT7 post-1.49 punishes **lateral slip** above all else (§2.5). Therefore **a tyre-friendly setup is one that reduces the slip angle required to generate a given lateral force, and that transitions load slowly enough for the driver to stay inside the slip window.**

That is a different objective from "maximum peak grip," and it is why the fastest single-lap setup is frequently not the fastest race setup. The good news: the two objectives conflict less than most people assume. **[TESTED]** *"If it's very comfortable for you to drive you will naturally be smoother and get less tyre wear."*

### 8.2 Parameter-by-parameter

| Parameter | Softer/lower | Stiffer/higher | Tyre life direction |
|---|---|---|---|
| **Springs (natural frequency)** | More mechanical grip, more roll, slower transitions | Sharper response, less compliance | **Softer is kinder.** [CONSENSUS] |
| **Anti-roll bars** | More grip on that axle, more roll | Less roll, more load transfer outboard | **Softer on the wearing axle.** [TESTED] *"Too stiff and the inside wheel lifts off"* — loading one tyre with the work of two. |
| **Dampers (compression)** | Absorbs bumps | Controls dive/squat, harsh over kerbs | **Lower compression on bumpy circuits.** [TESTED] **Reduce all damper values 1–2 clicks for endurance racing.** ⚠️ *1.71 changed damper attenuation characteristics — re-test.* |
| **Dampers (expansion)** | Tyre stays loaded longer | Sharper platform recovery | Keep expansion above compression. Starting point: compression 30, expansion 40. ⚠️ *The 20–40 / 30–50 windows are ranges, and ranges were revised — confirm in `11` before using.* |
| **Ride height / rake** | Lower = less roll, lower CoG | — | [TESTED] *"Ride height, and especially rake, will hold the most drastic effects."* Excessive positive rake induces rotation → rear slip → rear wear. |
| **Downforce** | Less drag, less grip | More grip, more drag and fuel | **[TESTED] More downforce is better for tyre management** — max except on high-speed tracks. Aero grip is grip you get without asking the tyre for slip angle. ⚠️ *Aero defaults and ranges were revised on race cars.* |
| **Brake balance** | — | — | **Move away from the wearing axle.** The only mid-race-adjustable wear lever. |

### 8.3 Camber and wear

**[TESTED] In GT7, increasing negative camber generally reduces grip, in a way that does not match real-world behaviour.** A detailed GTPlanet investigation reports *"negative camber will result in less grip in corners, no matter the tire, no matter the stiffness of the suspension, no matter the car,"* with braking performance also degrading.

**[UNVERIFIED]** A 2024 report claims front and rear camber inputs may be **swapped** in GT7. Not corroborated; worth a five-minute A/B.

> **⚠️⚠️ 21 Aug 2026 — this is the highest-priority re-test in the document.** 1.71: *"The steering geometry for each car has been optimised, improving the simulation of turning forces."* Steering geometry is precisely the model that governs how steer angle and suspension travel convert into slip angle and camber gain. **The anomalous camber behaviour described above is a symptom of that model, and PD have just reworked it per car.**
>
> If more camber still costs grip, this section survives intact. **If it doesn't, this is the single biggest tuning change 1.71 brings us**, and it rewrites the camber guidance in `02`, `08` and here. `16` §12 Job 5 is a ten-minute A/B at 0.5° / 1.5° / 2.5° front camber. **Run the front/rear swap check in the same session — it has been listed as "five minutes to falsify" since this document was written and it is now genuinely live.**

**Practical guidance (v1.70, pending the Job 5 re-test):**

- **Use less camber than real-world intuition suggests.** Widely used ranges: **Racing tyres −2.0° to −2.5° front, −1.5° to −2.0° rear**; many fast GT7 drivers run **−1.0° to −2.0° front, −0.5° to −1.5° rear**.
- **[TESTED] To reduce wear on a specific axle, reduce camber on that axle by ~0.3°.**
- **Every car has its own sweet spot.** *(And now, explicitly, its own steering geometry — the rework was per car, so the three cars may have moved differently from each other.)*
- **In the wet, reduce camber** (§7.5).

> **⚠️ Note added 10 Aug 2026:** camber is often set conservatively *because* of a projected wear limit. When the wear projection turns out to be pessimistic (§1.3.1), that conservatism becomes unpaid-for lap time. **Re-examine camber after any wear measurement that beats the model** — it is the setting most likely to have been over-protected.

### 8.4 Toe and wear

**[TESTED] Toe is the most direct wear parameter in GT7 and it is unambiguous.** *"The more you deviate from neutral, the more you will scrub, which results in more tyre wear and reduced straight line speed."*

- **Front toe: 0.00° is the endurance default.**
- **Rear toe: +0.05° (slight toe-in)** is the standard stabilising value; short-wheelbase cars may want +0.08° to +0.10°.
- **[TESTED] "Don't use toe to fix handling problems."** Fix balance with ARBs, dampers, and diff.
- **[TESTED] Minimise toe deviation specifically for endurance racing.**

**⚠️ 21 Aug: toe sensitivity is downstream of steering geometry too.** The ±1.00° range in `11` is a v1.70 reading. Re-confirm the range, then re-confirm that the scrub relationship still holds.

### 8.5 LSD and rear tyre life

The differential is the **primary rear-tyre-wear control** in GT7, and it is under-used.

**[TESTED]** GT7 exposes three parameters on a 5–60 scale: **Initial Torque**, **Acceleration Sensitivity**, **Braking Sensitivity**.

> **⚠️⚠️ 21 Aug 2026 — the range may have moved.** 1.71: *"Initial differential gear settings and adjustment ranges have been fixed."* **[COMMUNITY — single source]** One GTPlanet player reports the Fully Customisable Diff can now be set to **0/0/0**, which was never previously possible. If confirmed, a genuinely open differential is buildable for the first time in the series, and **every baseline in the table below is written against a floor that no longer exists.** Confirm on the settings screen before acting on it — `16` §5 and §12 Job 1.

| Parameter | Higher | Effect on rear wear |
|---|---|---|
| **Acceleration sensitivity** | Both rear wheels driven together out of corners | **Dominant rear-wear control.** High values → both rears spin together → total rear slip rises sharply on exit. Reducing this is the biggest single rear-tyre-life gain available in setup. |
| **Initial torque** | Diff locked at all times | Constant low-level scrub through every corner, and forces understeer the driver corrects with more steering — compounding front wear. **Keep low (5–10).** |
| **Braking sensitivity** | Rear axle locked together on entry | Affects entry stability. High values reduce rotation but can cause rear scrub on entry. MR/RR cars want this higher. |

**[TESTED] Baseline values by layout:**

| Layout | Initial | Accel | Braking |
|---|---|---|---|
| FR | 5 | 25 | 10 |
| FF | 10 | 35 | 8 |
| MR | 5 | 15 | 20 |
| RR | 5 | 15 | 25 |

**For a high-wear stint, reduce acceleration sensitivity by 5–10 from these baselines.** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see §8.5's banner row]*

> **✅ [MEASURED — IN HOUSE, 10 Aug 2026] The MR accel baseline of 15 is a ceiling, not a midpoint, on a restricted build.** The Huracán at Laguna produced power-on mid-corner understeer from lap 1 at accel 18 (a value chosen from track-specific guidance calling for 20–28). **14 resolved it completely.** The mechanism: a **power restrictor cuts top-end while preserving low-end torque**, so a restricted car delivers proportionally *more* torque in the early corner-exit phase than its headline power suggests — and more early torque through a locked diff is the direct recipe for power-on push. **Published tunes are unrestricted max-PP builds and do not account for this. Re-test accel sensitivity whenever the restrictor moves.** ⚠️ *[v1.70. On v1.71 the one in-house test of lowering accel was refuted - Huracán, Daytona, s145; `02` §10.5 is CONTESTED.]* Full write-up: `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 1.
>
> **⚠️ 21 Aug: this is our best LSD finding and it is directly in the firing line.** It is a claim about the *bottom* of the v1.70 5–60 range. The range does now start at 0 (`range_records`, v1.71), so the useful territory extends further down than we have ever looked — and 1.71 also introduced a new engine torque control map, which changes the torque this finding is a response to. **Re-test on v1.71 before reusing 14.**

**Note the FF row:** the recommended FF accel sensitivity (35) is the highest of any layout, which is precisely why FF cars destroy front tyres (§2.6). **FF cars in a high-wear league are a trap: they qualify well and finish badly.**

### 8.6 Building a car that is kind to its tyres without being slow

**The changes that cost you nothing:**

1. **Maximum downforce** (except on genuinely aero-limited circuits).
2. **Neutral front toe.**
3. **Brake balance rearward 1–2 clicks** on a front-limited car. Free, and adjustable mid-race.
4. **Full track width.**
5. **Short shifting on exit.** Saves 20% fuel and rear tyre for ~0.5 s/lap — and on worn tyres it's often *faster*.

**The changes that cost a little and pay a lot in a long stint:**

6. **Soften ARBs 1–2 clicks on the wearing axle.**
7. **Reduce damper compression and expansion 1–2 clicks each.**
8. **Reduce LSD acceleration sensitivity 5–10.** ⚠️ *[v1.70 5–60 scale: a direction, not a number]*
9. **Reduce camber ~0.3° on the wearing axle.**
10. **Soften springs slightly.**

**The changes to avoid:**

- **Do not stiffen your way to a fast lap.**
- **Do not use large camber values.**
- **Do not use toe to fix balance.**
- **Do not run TCS 0 on a torque-heavy RR/MR car in a high-multiplier race** just because it's faster on lap 1.
- **⚠️ Do not over-protect against a wear limit you have not measured.** Every item on the list above costs something. Spending all of them against a modelled wear figure that turns out to be 1.8× pessimistic is how you build a slow car for no reason (§1.3.1).
- **⚠️ NEW, 21 Aug — do not spend any of them against a v1.70 wear figure either.** Post-1.71, the wear limit is unmeasured by definition. Until Job 2 comes back, build the car the driver can drive and leave the tyre-saving budget unspent.

**Recommended tuning order** **[TESTED]**: Tyres → Downforce → Ride height → Natural frequency → Anti-roll bars → Dampers → Camber → Toe → LSD → Transmission → Brake balance.

**Set up on a heavy tank.** GT7 qualifying runs an empty tank; the race does not.

---

## 9. Quick-reference summary for league operations

**Multiplier presets (Gr.3/Gr.4; halve for road-car classes):** **⚠️ v1.70 figures — do not publish regulations from these until a v1.71 stint is measured.**
| Format | Tyre | Fuel |
|---|---|---|
| Sprint, no stop | 1x | 1x |
| Strategy sprint (optional stop) | 3–4x | 2x |
| Forced one-stop | 5–7x | 2–3x |
| Forced two-stop | 8–10x | 3–4x |
| Mini-endurance (60 min) | 6–8x | 3–4x |

**Constants to measure once per track:** pit lane time loss; compound lap-time delta; **wear per lap at the multiplier you will actually race**, for each compound.
**Constants to measure once, globally:** fuel weight penalty (s/L/lap); tyre temperature window per compound.
**⭐ And now, per Standing Rule 10: every one of them carries its game version, because a patch resets the lot.**

**Things to tell your drivers:**
1. The tyre gauge lies about grip. Watch your lap times and the balance shift.
2. There is a cliff at ~90%. One lap too long costs more than the whole compound advantage. *(⚠️ v1.70 — unverified on 1.71.)*
3. Sliding is what kills tyres now, not braking. If you hear them, you're paying. *(⚠️ the claim 1.71 most directly re-opened.)*
4. Brake balance is your mid-race wear tool. Move it away from the axle that's going.
5. Fuel-save in the tow. It's free.
6. Short shift. It saves fuel *and* rear tyres.
7. The overcut beats the undercut in GT7 — except where overtaking is impossible ⚠️ *[re-flagged 11 Sep 2026: that exception is unmeasured; see `05`'s banner]*.
8. Err wet.
9. **Measure your stint before you pick your compound. Every wear number in this document that wasn't measured here has been wrong at least once.**
10. **⭐ NEW — and every wear number that *was* measured here was measured on a previous version of the game.**

---

## 10. Known gaps — original testing worth commissioning

1. **Post-1.49 wear-rate ratio RH:RM:RS**, measured. ⚠️ **Partially open, and reset by 1.71.** RS was measured in-house at one car/track/multiplier on v1.70 (§1.3.1); **one RM run at the same conditions would calibrate the ladder** — now `16` §12 Job 3, to be run on v1.71 at Watkins Glen rather than at Laguna.
2. **Tyre temperature windows in °C per compound**, from telemetry. **The most valuable and most tractable remaining item, and 1.71 made it more so by adjusting heating values.** `16` §12 Job 6.
3. **Fuel weight in s/L/lap**, measured. A 30-minute test.
4. **Refuel rate in L/s**, measured with a stopwatch and the telemetry `fuelLevel` field.
5. **Current GT7 pit deltas per track.** The published table is GT5-era.
6. **Whether the 4%/8% fuel-map rule survived 1.49** — **now, whether it survived 1.71's new engine torque control map.** More likely to have moved than before.
7. **The front/rear camber swap claim.** Five minutes to falsify. **Now genuinely live** — 1.71 reworked per-car steering geometry. `16` §12 Job 5.
8. **Fuel consumption at 3× on the Laguna Huracán build.** Modelled only, by the method that produced the 1.8× tyre error — **and now also exposed to the rolling-resistance change.**
9. **Multiplier linearity at low multipliers.** §4.1's [CONFIRMED] tag overstates the evidence and the playbook downgrades it. Running the same car/track/compound at 2× and 4× would settle it in under an hour.
10. **⭐ NEW — everything in `16` §11.** Direction and magnitude of the 1.71 wear change; whether the cliff survived; whether lateral slip is still dominant; whether tyre heat is now driver-relevant; what rolling resistance did to L/lap and terminal speed.

---

## Sources

**Official (Polyphony Digital / gran-turismo.com)**
- [Update Notice (1.71) — GT7 Updates](https://www.gran-turismo.com/gb/gt7/news/00_3638095.html) — **the current baseline**
- [Update Details (1.49) — GT7 Updates](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)
- [Update Notice (1.55) — GT7 Updates](https://www.gran-turismo.com/gb/gt7/news/00_3399040.html)
- [Update Notice (1.65) — Spec III](https://www.gran-turismo.com/us/gt7/news/00_8101458.html)
- [The Gran Turismo 7 Spec III Update overview](https://www.gran-turismo.com/us/news/00_4185758.html)
- ["Gran Turismo World Series" World Finals Beginner's Guide](https://www.gran-turismo.com/sg/gt7/news/00_3949205)
- [GT7 Online Manual — In-Race Settings / MFD](https://www.gran-turismo.com/au/gt7/manual/race/04)
- [GT7 Online Manual — The Pit Menu](https://www.gran-turismo.com/au/gt7/manual/race/07)
- [Beyond the Apex — Driving According to Drivetrain Type](https://www.gran-turismo.com/mx/gt7/apex/driving_technique/13)

**In-house measured data (highest authority for our own use — but see Standing Rule 10: every entry is version-stamped)**
- `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 1 — LSD acceleration, validated 14 — **v1.70**
- `setups/2026-08-10-huracan-laguna-seca.md` §9 Test 2 — Racing Soft, 2×, Laguna: 11–12 laps — **v1.70**
- `01-driver-profile-leon.md` §11 — the diagnostic method behind both

**Physics update analysis**
- [GTPlanet — Update 1.71 Arrives With Major Physics Changes](https://www.gtplanet.net/gran-turismo-7-update-1-71-arrives-with-major-physics-changes-fanatec-fullforce-support-20260820/)
- [Traxion — 1.71 brings sweeping physics changes, resets leaderboards](https://traxion.gg/gran-turismo-7s-latest-update-brings-sweeping-physics-changes-resets-leaderboards/)
- [DG EDGE — GT7 Physics Update 1.49 Breakdown](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424)
- [DG EDGE — Update 1.55: Physics Improvements](https://www.dg-edge.com/articles/news/gran-turismo-7-update-1-55-new-cars-sophy-ai-and-physics-improvements/452)
- [GTPlanet — Update 1.55 Is Now Available](https://www.gtplanet.net/gran-turismo-7-update-1-55-is-now-available-physics-changes-four-new-cars-and-more/)
- [autoevolution — How 1.49 Improves the Car Physics Simulation Model](https://www.autoevolution.com/news/how-gran-turismo-7-s-update-149-improves-the-car-physics-simulation-model-237495.html)

**Tyre model, wear, and compounds**
- [GTPlanet — Tyre wear..](https://www.gtplanet.net/forum/threads/tyre-wear.411748/)
- [GTPlanet — Tire wear model seems broken now](https://www.gtplanet.net/forum/threads/tire-wear-model-seems-broken-now.411190/)
- [GTPlanet — Gr.3 MR cars tire wear test](https://www.gtplanet.net/forum/threads/gr-3-mr-cars-tire-wear-test.384914/)
- [GTPlanet — Racing soft tires vs medium](https://www.gtplanet.net/forum/threads/racing-soft-tires-vs-medium.427384/)
- [GTPlanet — Is There A Tire Wear Chart?](https://www.gtplanet.net/forum/threads/is-there-a-tire-wear-chart.431035/)
- [GTPlanet — Current tire wear list (methodology)](https://www.gtplanet.net/forum/threads/gran-turismo-sport-current-tire-wear-list.387661/)
- [GTPlanet — Drivetrains and Tyre Wear](https://www.gtplanet.net/forum/threads/drivetrains-and-tyre-wear.380738/)
- [GTPlanet — Best methods to tire saving?](https://www.gtplanet.net/forum/threads/best-methods-to-tire-saving.383149/)
- [GTPlanet — Reducing Tyre Wear with suspension tuning](https://www.gtplanet.net/forum/threads/reducing-tyre-wear-with-suspension-tuning.408750/)
- [Academia.edu — GT7 Experiment: The Effect of Tyre Grip on Lap Time (Porsche 963, Laguna Seca)](https://www.academia.edu/169237784/GT7_Experiment_The_Effect_of_Tyre_Grip_on_Lap_Time)
- [Gran Turismo Wiki — Tires](https://gran-turismo.fandom.com/wiki/Tires)

**Temperature and pressure**
- [GTPlanet — Tyre temperature](https://www.gtplanet.net/forum/threads/tyre-temperature.406736/)
- [GTPlanet — GT7 Tire Temperature windows](https://www.gtplanet.net/forum/threads/gt7-tire-temperature-windows.431495/)
- [GTPlanet — Why doesn't Gran Turismo's tyre model feature adjustable pressures?](https://www.gtplanet.net/forum/threads/why-doesnt-gran-turismos-tyre-model-feature-adjustable-pressures.309340/)
- [FILO Engineering — Tyres Overview](https://www.filoengineering.com/home/gran-turismo-7/tuning-setups/tuning-theory/tyres-overview)

**Telemetry**
- [MacManley/gt7-udp — GT7 UDP Telemetry Parser field reference](https://github.com/MacManley/gt7-udp)
- [GTPlanet — Overview of GT7 Telemetry Software](https://www.gtplanet.net/forum/threads/overview-of-gt7-telemetry-software.418011/)

**Fuel**
- [GTPlanet — Test Results: Fuel Mixture Settings and Other Fuel-Saving Techniques](https://www.gtplanet.net/forum/threads/test-results-fuel-mixture-settings-and-other-fuel-saving-techniques.369387/)
- [GTPlanet — Fuel consumption data](https://www.gtplanet.net/forum/threads/fuel-consumption-data.410418/)
- [GTPlanet — Altering ECU + Restrictor to find Fuel Map Equivalents](https://www.gtplanet.net/forum/threads/altering-ecu-restrictor-to-find-fuel-map-equivalents.418559/)
- [GTPlanet — Does weight of fuel actually affect vehicle performance?](https://www.gtplanet.net/forum/threads/does-weight-of-fuel-actually-affect-vehicle-performance.309988/)
- [GTPlanet — Gr.1 Prototype Series Road Atlanta: Tips & Tricks](https://www.gtplanet.net/forum/threads/gr-1-prototype-series-race-road-atlanta-tips-tricks.414318/)
- [note.com / Apex Evolution — GT7 Gr.3 Car Fuel Economy Database](https://note.com/apexevolution/n/n9946c500557f?hl=en)
- [OverTake — Lift and Coast: The Key to Extending Your Stints](https://www.overtake.gg/news/lift-and-coast-the-key-to-extending-your-stints.1233/)

**Pit stops**
- [GTPlanet — Estimated Pit Stop Duration](https://www.gtplanet.net/forum/threads/estimated-pit-stop-duration.381486/)
- [GTPlanet — Pit Delta Times for All Tracks](https://www.gtplanet.net/forum/threads/pit-delta-times-for-all-tracks.237451/)
- [GTPlanet — Do cars refuel at different speeds during pit stops?](https://www.gtplanet.net/forum/threads/do-cars-refuel-at-different-speeds-during-pit-stops.419240/)
- [Strat Packer — GT7: A guide to race strategy and pit stops](https://stratpack.blog/2022/04/01/gran-turismo-7-guide-race-strategy-pit-stops)

**Multipliers and race formats**
- [GTPlanet — Realistic Tyre wear and fuel depletion?](https://www.gtplanet.net/forum/threads/realistic-tyre-wear-and-fuel-depletion.377343/)
- [GTPlanet — How to determine tyre wear for custom races?](https://www.gtplanet.net/forum/threads/how-to-determine-tyre-wear-for-custom-races.420448/)
- [GTPlanet Daily Races — Kyoto Yamagiwa Gr.4 (Mar 2026)](https://www.gtplanet.net/144526-2/)
- [GTPlanet Daily Races — Dragon Trail Seaside Gr.4 (May 2026)](https://www.gtplanet.net/gran-turismo-7-daily-races-wrong-way-round-the-ring-20260518/)
- [GTPlanet Daily Races — Red Bull Ring Gr.3 (Dec 2025)](https://www.gtplanet.net/gran-turismo-7-daily-races-20251229/)
- [GTPlanet Daily Races — all-1x week (Aug 2026)](https://www.gtplanet.net/gran-turismo-7-daily-races-running-like-clockwork-20260803/)
- [Coach Dave Academy — GT7 Daily Races Explained](https://coachdaveacademy.com/tutorials/gt7-daily-races-explained/)

**Wet weather**
- [GTPlanet — Wets vs Intermediate](https://www.gtplanet.net/forum/threads/wets-vs-intermediate.390792/)
- [GTPlanet — Race Intermediate vs Sports Soft Tyres](https://www.gtplanet.net/forum/threads/race-intermediate-vs-sports-soft-tyres.405635/)
- [GTPlanet — Wet weather is awful…](https://www.gtplanet.net/forum/threads/wet-weather-is-awful%E2%80%A6.407132/)

**Setup and tuning**
- [Flux89 — GT7 Tuning Cheat Sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet)
- [Coach Dave Academy — GT7 Tuning Guide: Every Setting Explained (2026)](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/)
- [GTPlanet — Negative camber, negative experience](https://www.gtplanet.net/forum/threads/negative-camber-negative-experience.411540/)
- [GTPlanet — Increasing Tyre Life](https://www.gtplanet.net/forum/threads/increasing-tyre-life.311747/)
- [GTPlanet — Complete GT7 Tuning Cheat Sheet](https://www.gtplanet.net/forum/threads/complete-gt7-tuning-cheat-sheet-cross-referenced-guide-with-starting-values-for-every-setting.436897/)
- [FILO Engineering — Tuning Theory](https://www.filoengineering.com/home/gran-turismo-7/tuning-setups/tuning-theory)

---

**Maintenance note, 10 Aug 2026.** This document was built from official patch notes, telemetry field definitions, controlled community tests, and Sport Mode race configurations. As of this revision it also contains **in-house measured data**, which is tagged **[MEASURED — IN HOUSE]** and outranks every other tag for our own decisions. The first such measurement invalidated a modelled prediction by ~1.8× and forced a compound change mid-programme — a good argument for adding to this tier aggressively. **Every measurement gets a date, a game version, a car, a track and a multiplier, or it is not worth recording.**

**Maintenance note, 21 Aug 2026.** Update 1.71 landed on 20 August and the exposure banner at the top of this file is the result. **No content was deleted** — the body remains a complete v1.70 record, which is exactly what it needs to be so that post-1.71 measurements have something to be compared against. As Jobs 2, 3, 5 and 6 from `16-update-1.71-physics-change.md` §12 come back, their results go into the relevant sections tagged `[MEASURED — IN HOUSE]` **with the version stamp**, and the corresponding rows come out of the banner. When the banner is empty, this becomes a v1.71 document.
