# GT7 Race Engineering — Knowledge Base Index

**Driver:** Leon Paczynski · **Role:** Head Race Engineer
**Established:** 10 August 2026 · **Game baseline: GT7 v1.71 (20 August 2026) — physics update, see `16-update-1.71-physics-change.md`**
**Previous baseline:** v1.70 (June 2026), post-1.49 physics lineage
**Competition context:** custom league — **no BoP, open garage tuning**, mixed sprint and multi-stop formats across a season
**Hardware:** Fanatec DD Extreme (18 Nm) · ClubSport V3 pedals, **load cell** brake, hydraulic throttle damper · PS5 · PSVR2

---

## 🔴 STATUS — 21 August 2026: the knowledge base is mid-revalidation

**Update 1.71 (20 Aug 2026) changed the tyre model, the steering geometry of every car, the damper model, the default settings *and the adjustment ranges* of suspension / differential / aerodynamics, Performance Points fleet-wide, both driving assists, and the damage model.** Polyphony reset every ranking board in the game, which is their own statement that old lap times no longer compare to new ones.

**Consequences right now:**

- **`11-car-slider-ranges.md` is unverified in full.** Adjustment ranges were explicitly revised. No sheet should be issued until all three cars are re-read. **15 minutes.**
- **`03-gt7-tyre-and-fuel-model.md` is the worst affected document**, including our own measured Laguna and Monza wear results. Every stint length and compound choice in it is a v1.70 number.
- **Every sheet in `setups/` is pre-1.71.** Historical record and control group, not values to type in. See `setups/00-PRE-1.71-NOTICE.md`.
- **PP moved fleet-wide.** Our three builds may have moved relative to the league cap. This is a race-weekend problem, not a tuning problem.

### The first ninety minutes, in order

**`16-update-1.71-physics-change.md` §12 is the protocol.** The short version:

| | Job | Time |
|---|---|---|
| **0** | **Did the saved tunes survive the patch?** Read the car's settings screen against its archived sheet **before touching anything**. Three outcomes, three different next steps. | **2 min** |
| **1** | **Re-read the slider register** — all three cars, 22 parameters, plus step sizes and the LSD floor. **Blocks every sheet.** | **15 min** |
| **7a** | **Confirm the wheel.** 1.71 changed FFB, understeer vibration and Fanatec Auto Setup. On an 18 Nm DD that reads exactly like a grip change. | **5 min** |
| **⭐ 2A** | **The Monza RSR control run** — 10 laps, Racing Hard, 8× / 3×, against ~200 laps of pre-1.71 data. **The only measurement in the programme with a baseline *distribution* behind it.** Baseline card: `setups/2026-08-12-rsr-monza-revB.md`. | **30 min** |
| **2** | **The tyre stint** — Huracán, Watkins Glen Long, RS, league multiplier, full fuel, to *felt* fall-off. Rear-left gauge at lap 6 and lap 12. | **30 min** |

**Those five rebuild the foundation everything else stands on.** Jobs 3–8 (RM comparison, PP audit, camber and toe A/B, tyre temperature, assists, per-car re-baseline) follow in `16` §12.

---

## Read this first

**`08-playbook-leon.md` is the working document.** It translates GT7's actual physics into this driver's specific style, and it is where every setup decision starts. Everything else is reference material it draws on.

**Until the 1.71 re-measurement is done, read `16` alongside it.** The playbook's *method* survived the patch; its *numbers* have not been re-verified.

## The files

| File | What it is | When to open it |
|---|---|---|
| **`16-update-1.71-physics-change.md`** | **⚠️ The 1.71 changelog and work order.** What changed, what it invalidates document by document, what is now known to be unknown, and the prioritised re-measurement protocol. | **Now, and before any setup work, until the protocol in §12 is closed** |
| **`08-playbook-leon.md`** | **The synthesis.** GT7 physics expressed through Leon's driving style: the seven places his instincts and GT7 diverge, his baseline sheet in GT7 sliders, race-vs-quali decision rules, his three cars, the session protocol, and the measurement backlog. | **Always. Start here** (after `16`) |
| `01-driver-profile-leon.md` | The driver model: non-negotiables, technique by corner phase, change hierarchy, do/don't rules, symptom dictionary, accumulated car/track learnings, hardware philosophy. Canonical source is the 10 Aug 2026 dossier PDF. | Before any new setup; when interpreting driver feedback |
| `02-gt7-setup-parameters.md` | Every slider on the GT7 sheet: units, how per-car ranges are derived, effect of every direction, GT7-specific quirks, and full ranked symptom→fix diagnosis tables. **Ranges void post-1.71; §10's symptom tables are the part to use during the rebuild.** | Mid-session, when something needs fixing |
| `03-gt7-tyre-and-fuel-model.md` | Compounds, the wear model, what actually consumes tyre, wear/fuel multipliers and how to calibrate them, fuel maps and saving, pit stops, wet weather. **⚠️ Worst affected by 1.71 — carries a full section-by-section exposure banner.** | Race strategy; league multiplier setting |
| `04-race-vs-qualifying.md` | Parameter-by-parameter quali/race deltas, fuel-load effects, how balance migrates over a stint, the format decision table, one-lap technique, racecraft trim. **Framework intact; magnitudes suspect. §8's validation protocol is the most useful part right now.** | Before every race weekend |
| `05-track-reference.md` | 42 circuits — downforce level, dominant corner types, kerbs and elevation, braking zones, traction-limited exits, gearing targets, wear character, pit loss, and the top three levers at each. Plus summary matrices and league calendar archetypes. **⚠️ Gearing targets exposed to the rolling-resistance change. Also carries an outstanding correction: Monza's front wear side is LEFT, not right.** | Choosing a setup direction for a specific round |
| `06-car-building-and-pp.md` | How PP actually works (it's a simulation, not a formula), every upgrade path, restrictor vs ECU, ballast and weight, engine swaps, min-max build strategy, and league-fairness notes. **PP numbers void post-1.71; mechanism intact — and §1.4 predicted the patch.** | **Critical for this league** — no BoP means the build is half the competition |
| `07-car-profiles.md` | Porsche 911 RSR '17, Lamborghini Huracán GT3 '15, and the full Mustang/Shelby disambiguation — specs, handling character, wear, braking, aero, setup levers, available baselines. **Handling character is a pre-1.71 observation, and geometry was reworked *per car* — so §6's comparisons are the most exposed part.** | Picking a car; starting a new car's setup |
| `09-setup-sheet-format.md` | The required output layout for every setup: GT7 in-game order, percent-of-range plus clicks plus absolute, what always accompanies the sheet, and the race-primary / quali-as-delta rule. | Every time a setup is issued |
| `10-pit-crew-data-format.md` | The ingestion spec for the Pit Crew app's session export — JSON envelope, corner-level aggregates, flag vocabulary, fixed units, build order. **⭐ `meta.gameVersion` is now a required field, per Standing Rule 10, and is currently missing.** | When the Pit Crew export changes, or when its output arrives |
| `11-car-slider-ranges.md` | **The range register.** Recorded min/max for every per-car slider, read off each car's own settings screen. **⚠️ All three cars unverified post-1.71 — re-read before any sheet. Carries the re-read worksheet.** | When a car's ranges are measured, and whenever a sheet is issued for a car that is in the register |
| `12-pitcrew-app-brief.md` · `13-pitcrew-v1.2-gearing-and-strategy.md` · `14-prompt-builder-into-pitcrew.md` | The Pit Crew app's own specification lineage. | When changing the app |
| **`15-pitcrew-detector-audit.md`** | **⚠️ What the Pit Crew flags actually measure.** Opened 17 Aug 2026 after `bottoming` and `understeer-mid` were both shown to be artefacts. Also logs the stale `setup` block, the broken calls ledger, and the gearing-constant error. **Unaffected by 1.71 and more important during the rebuild, not less.** | **Before trusting any corner flag, and before letting telemetry buy a setup change** |

The original dossier PDF is stored alongside these as `Leon_GT7_Driver_Engineering_Dossier.pdf`.

Setup sheets live under `claude/gt7/setups/`. **All are pre-1.71** — see `setups/00-PRE-1.71-NOTICE.md`, which lists them, names the most recent sheet per car, and carries the Job 0 procedure.

---

## Tooling

The **GT7 Race Engineering** artifact (desktop Cowork sidebar) is the front end for this knowledge base. Three tabs:

1. **New Setup Brief** — car and circuit pickers, event format, build, slider ranges, assists and context. Emits a structured brief to paste into a project session.
2. **Driver Feedback** — carries car, circuit and event across from the brief. Session-type aware (practice / quali / time trial / completed race), captures the setup as run, symptoms by corner phase, pace, tyre and fuel data, optional Pit Crew telemetry, and driver notes verbatim. Emits a setup-refinement prompt asking for a diagnosis, revised sheets and a delta table.
3. **Quick Reference** — change hierarchy, rear-stability stack, GT7 traps, baseline sheet.

**Slider ranges persist per car.** The tool holds a range library keyed by car. Picking a car whose ranges are in `11-car-slider-ranges.md` loads its real limits automatically and flags them as verified; anything else falls back to generic race-car or road-car windows and says so. Browser storage is unavailable in artifacts, so this register **is** the persistence layer; if a range record arrives and is not written here, it is lost.

> **⚠️ 1.71 note.** The tool's range library is loaded from `11`, and `11` is a v1.70 record. **Until the register is re-read, the tool is confidently serving stale limits and marking them "verified."** Treat every auto-loaded range as unverified until `11` is updated, and re-enter the new numbers there first so the tool inherits them.

---

## Standing rules

1. **Any GT7 setup published before August 2024 is void; anything before February 2025 is suspect; ⭐ anything before 20 August 2026 is pre-1.71 and must be re-validated before use — including our own.** Update 1.49 (Jul 2024) rewrote the physics, tyre wear and geometry model. 1.55 (Jan 2025) did a second pass and changed ABS/TCS intervention. **1.71 (Aug 2026) reworked the tyre slipping model, per-car steering geometry, damper attenuation, and the adjustment ranges of suspension, differential and aero.** Most published tunes and most YouTube advice predate all three.
2. **Reason in slider position and percentage of range, not absolute values** — except where `11-car-slider-ranges.md` says otherwise. Natural frequency, toe and camber are issued in absolute units; ride height and downforce in percent of range plus absolute. **⚠️ Percent-of-range silently changes meaning when a range moves, and 1.71 moved ranges. This rule is only safe once `11` is re-read.**
3. **Confidence is tagged in the reference docs.** `[GAME]` = verifiable in-game fact. `[STRONG]` = multiple independent sources plus physical plausibility. `[COMMUNITY]` = widely held, not rigorously shown. `[CONTESTED]` = sources actively disagree. `[VERSION]` = changed with a patch. Treat `[CONTESTED]` items as hypotheses to test, never as facts.
4. **Discard any guide mentioning tyre pressure, caster, brake pressure, or high/low-speed damper splits.** None of these exist in GT7. Their presence means the guide was pattern-matched from another sim — most likely AI-generated — and is unreliable throughout. **⭐ Second tell, added 21 Aug: any post-1.71 tuning content quoting confident absolute values. Nobody has measured anything yet.**
5. **One change per run. Three clean laps minimum. Record the change and the result.** If the driver can't feel it and the Data Logger can't see it, revert it. **Not suspended for the 1.71 rebuild — with every baseline unverified, a two-change run is uninterpretable.**
6. **Every measurement taken goes back into this knowledge base with a date and a game version.** That is what turns a reference into an advantage. Slider ranges are a measurement — they go in `11-car-slider-ranges.md`.
7. **The driver report is primary evidence.** Read it literally rather than smoothing it into generic symptoms. Where telemetry and the driver disagree, that disagreement is the finding — say which is being trusted and why.
8. **17 Aug 2026 — a telemetry-only flag may not buy a setup change. It may only buy a question or a measurement.** Rule 7 was overridden exactly once, in `setups/2026-08-17-huracan-watkins-glen-long-revC.md` §3.4, to raise a car on a `bottoming` flag the driver had not felt. The next packet showed the flag was firing on body roll. **Cost: 5 mm of ride height and 2 mm of rake, changed for no reason.** See `15-pitcrew-detector-audit.md`.
9. **17 Aug 2026 — confirm which sheet was physically in the car before diagnosing anything.** One line, every session. The Pit Crew `setup` block has now been stale three sessions out of three, and on the third it would have produced a completely coherent diagnosis of a car that was not on the circuit. **While that defect is live, never omit a key from a reply block — re-assert every value.** **⭐ And 1.71 adds a second failure mode: the *car* may hold different values than the sheet, if the patch reset or clamped them. Job 0 is this rule asked once, globally.**
10. **⭐ NEW, 21 Aug 2026 — every setup sheet, measurement and telemetry packet carries its game version.** `03`'s maintenance note already requires date, car, track and multiplier on every measurement. Version joins that list. A number without a version cannot be trusted after the next patch, and there is always a next patch. **This is currently unenforceable on Pit Crew exports — `meta.gameVersion` is missing from the packet. Priority-one fix.**
11. **⭐ NEW, 21 Aug 2026 — after a physics-tagged update, the slider register is re-read in full before any sheet is issued.** `11`'s old "spot-check one car" guidance was written when it was ambiguous whether endpoints ever moved. 1.71 says in the official notes that they did. Full re-read, every recorded car, first.
12. **⭐ PROPOSED, pending the Monza control run — where a baseline distribution exists, measure against the distribution, not against a single prior result.** This knowledge base's recurring weakness is n=1 findings carried with more confidence than they can bear: `03` §1.3.1 (model 1.8× wrong at Laguna), `setups/…-rsr-monza-revB.md` §5.1 (model 5× wrong at Monza), and `08` Part G's meta-lesson all document measurements that were plausible, well-argued and wrong. **A median and a spread is a different class of evidence from a lap time.** Where a car/track combination has accumulated history, use it. **`16` §12 Job 2A is the first time this has been possible.**

---

## Settled facts

Checked by an adversarial verification pass on 10 Aug 2026, plus later confirmations. **Each is now annotated for 1.71 exposure.**

- **Brake balance: negative = more FRONT bias, positive = more REAR.** Three sources state the sign, all agree, none dissent. The value is a **delta from each car's factory bias**, not an absolute percentage. *Unaffected by 1.71 — a sign convention, not a physics value. But ABS cornering-brake behaviour was adjusted, so what a given click **does** may have changed.*
- **The 911 RSR '17 is MR.** GT7's own car description says so explicitly. *Unaffected. The single most load-bearing correction in `07` and it needs no re-checking.*
- **Suspension, gear ratios and LSD *values* cost zero PP.** *Fitting* the parts does (Fully Customisable Suspension measured at +9.1 PP on one car). Aero is **not** free and moves PP non-monotonically. *⚠️ The mechanism should survive, but PP was recalculated fleet-wide and aero defaults moved. Re-measure the +9.1 figure — `16` §12 Job 4.*
- **1.49's bottoming / wheel-arch-contact problem is real and still live in 2026.** 1.55 addressed short-period bumps only, not the ride-height floor. A car that suddenly refuses to turn is a ride-height problem. ⚠️ **The problem is real; the Pit Crew `bottoming` flag is not a valid trigger for it** — see rule 8 and `15-pitcrew-detector-audit.md` §1. The trigger is the driver symptom, or a four-wheel mean-heave figure. *⚠️ 1.71 reworked damper attenuation and revised suspension defaults and ranges. **Status is now [UNKNOWN]: do not assume fixed; do not assume unchanged.** `16` §4.*
- **17 Aug 2026 — first win.** Huracán GT3 at Watkins Glen Long, P1 from P5, on `setups/2026-08-17-huracan-watkins-glen-long-revC.md` with Racing Soft both stints and the app's shift beep (short-shifting the slow exits). Post-mortem and Rev D: `setups/2026-08-17-huracan-watkins-glen-long-revD.md`. *The result stands as history. The setup is pre-1.71 and is now the best control group we have on that car.*
- **Refuel volume is worth ~1.0 s per litre; stop lap is worth ~0.07 s per lap of delay inside the legal window.** A 14× ratio, measured at Watkins Glen. **Optimise litres, not lap.** *⭐ The **ratio** is a property of pit mechanics and fuel mass, neither of which 1.71 touched — it survives. The **L/lap input** to the refuel formula did move, via rolling resistance. Re-measure the input; keep the rule.*
- **⭐ Monza's front wear side is LEFT, not right** — measured FL 0.79 vs FR 0.63, because Lesmo 1, Lesmo 2 and the Parabolica are all right-handers. `05-track-reference.md` still has it backwards. *Circuit geometry — unaffected by 1.71, and **still not corrected in `05`.***

---

## Open items

Tracked in full in `08-playbook-leon.md` Part G. **The 1.71 re-measurement protocol in `16` §12 now sits above all of them**, and several of the pre-existing items close for free inside it.

**Blocking everything (from `16` §12):**

0. **Did the saved tunes survive the patch?** Two minutes. Read the settings screen against the archived sheet before touching anything. Determines whether the next hour is a re-read or a rebuild.
1. **Re-read the slider register — all three cars, all 22 parameters.** 15 minutes. Blocks every sheet. **Record step sizes and check the LSD floor while the screen is open** (items 4 and the LSD question below, closed for free).
2. **⭐ The Monza RSR control run.** 10 laps, RH, 8× / 3×, matched conditions, against the 11 Aug baseline. **The only measurement available with a distribution behind it, and the cleanest probe for the rolling-resistance change.** Baseline card and full method: `setups/2026-08-12-rsr-monza-revB.md`.
3. **One measured tyre stint on the car and track that matter.** Huracán, Watkins Glen Long, RS, race multiplier, full fuel, to felt fall-off. **Take the rear-left gauge reading at lap 6 and lap 12.**

**Pre-existing, still open:**

1. ~~No post-1.49 tyre wear data exists publicly~~ → **now: no post-1.71 tyre wear data exists for anyone, us included.** The two in-house measurements (Laguna RS 2× = 11–12 laps; Monza RH 8× = 15 laps, ~9 ms/lap degradation) are v1.70 numbers. **The rear-left gauge reading at lap 6 and lap 12 has now been asked for four sessions running and never taken.** Still the single highest-value five seconds available, and now also the fastest read on what 1.71 did to wear.
2. **Multiplier linearity has never actually been tested** — only assumed. Calibrate at the multiplier you race, not by conversion across a wide gap. *Unchanged in status by the patch; the mechanism scales a rate, and the rate moved.*
3. **Gearing constants.** The Huracán's K is an extrapolation (1112.6 vs 1092.5, 1.8 % apart) — **closable in one lap** by holding 5th to the limiter on the long straight. The RSR's K = 1,128 / limiter 8,600 and the Shelby's K = 1,096 were both *closed* on v1.70. *⚠️ Rolling resistance changed, so all three need re-taking — and the RSR's re-take happens for free inside Job 2A.*
4. ~~**Slider step sizes** on any recorded car~~ → **folded into Job 1.** Four sessions overdue; five seconds each; unavoidable now the register is being re-read. *(The RSR's natural-frequency step is known: 0.01 Hz, settled 12 Aug.)*
5. **Declare the drivetrain (MR / RWD) to Pit Crew.** One field; it turns the contaminated wheelspin channel into a working one. Outstanding since 14 Aug.
6. **The Watkins Glen corner-ID mapping.** Pit Crew's auto-segmenter finds 9 corners on an 11-turn circuit and names them T1–T9. Which named corner is which has been asked for twice and never answered. *Now blocking — Job 2's corner-level results are unattributable without it.*
7. **Front toe A/B, never run on either Gr.3 car.** GT7's most disputed parameter, sitting on the driver's #1 priority. *Now more interesting: toe sensitivity is downstream of the steering geometry 1.71 reworked, so the dispute has been re-rolled and may finally resolve cleanly. Paired with the camber A/B in `16` §12 Job 5.*
8. **`05-track-reference.md`'s Monza wear-side correction.** Outstanding since 12 Aug. Five minutes.
9. **Pit Crew export defects** — `meta.gameVersion` missing (now Standing Rule 10, priority one), `wear.byCompound` fabricating compound labels, `bestLapMs` accepting invalid laps, the `fittedFinalGear` contradiction, and the absent `corners` array. Full list: `setups/2026-08-12-rsr-monza-revB.md` §9.

**New, opened by 1.71 (full list in `16` §11):** LSD floor of 0 (single community source, unconfirmed); camber sensitivity after the steering-geometry rework; whether the wear cliff still exists; whether tyre heat is now driver-relevant; PP position of all three builds; TCS intervention cost; whether the 1.49 bottoming problem survived; and whether the damper model got its authority back.

**For the league organiser, both better raised before a round than after one:** PP moved fleet-wide, so the whole grid needs re-scrutineering against the cap (`06` §9.3); and 1.71 added a **"Championship" mechanical damage setting** — Light's severity from more minor collisions, with variable recovery time — which is the middle ground a no-BoP league has not previously had (`16` §9).

Two claims were deliberately downgraded rather than deleted, and the reasoning is preserved in the playbook: the "both rear wheels let go at once" LSD behaviour (single-source, and ordinary spool physics rather than a GT7 anomaly), and multiplier linearity (widely used, never measured).
