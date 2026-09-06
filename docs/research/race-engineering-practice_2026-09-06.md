# How professional race engineering actually works — research brief

**6 Sep 2026.** Web research, practitioner sources preferred, GT7 items dated and
anything pre-Aug-2024 flagged void. Feeds `docs/ENGINEERS-ASSESSMENT-AND-PLAN_2026-09-06.md` §1.

---

## 1. Pre-event preparation

- Vehicle build spec for this track; if never visited, derived by comparison to a similar venue (Collins Ltd).
- Test plan starting from "what do we want to learn", not what to run.
- Run plan per session, to the minute: purpose per run (install / test item / short-run / long-run), fuel, tyre set, the setup delta carried (Dymott, Friday).
- Pre-prepared alternative setups so unexpected adjustments cost no track time (Dymott, Thursday).
- Decision matrix / contingency tree for the likely scenarios, because meetings are time-compressed (Collins Ltd).
- Tyre allocation across practice / quali / race; preliminary strategy discussion.
- Fault list from previous events reviewed with fixes.
- Strategy model inputs: tyre model (base pace, deg rate, life), pit loss; McLaren reduces it to "tyre behaviour and pit loss" (Raceteq, Jul 2024).
- Pit loss measured in practice: (in-lap + out-lap) − 2 × clean lap; a circuit constant (F1 Briefing).
- Between sessions hand the crew only the **change list**, never a fresh full sheet; a pre-event sheet gets a cover memo of what differs (Fey, 2010).
- Run-sheet structure (ONE RACEHUB): lap table with lap *type*, setup as run, tyre block, fuel block, weather per run, driver and engineer comment blocks, KPIs, issues, RunCompare view (Paceteq).

## 2. Practice session workflow

- Install lap, then a baseline run from the previous visit's data (Racing Car Dynamics).
- One parameter, both directions, big enough to feel: too small "could take you in the wrong direction" (Collins Ltd).
- **A-B-A is not optional**: "you always need to go back again, to make sure that the driver isn't just improving in himself" (Devine, F1); ~10 laps per config (Williams, YDD).
- 5–7 laps per interval yields 3–5 usable flying laps (RCD).
- Sequencing: tyre temps → mechanical balance → aero → gear ratios → damper fine-tune (RCD).
- Metrics: trends over multiple laps, never one lap; strip traffic laps; present only when confident (Collins Ltd). Chosen setup is "the fastest setup your driver feels comfortable exploiting" (Braun, IndyCar).
- Tell the driver what changed and why before the run.
- Debrief: after each run, driver feedback recorded; ~15 min after the session, run-by-run, so the group has "a single version of events" (Dymott). Williams post-race form: engineers first (balance, changes, reliability), then driver (Vowles, Jul 2024). YDD: debrief **immediately** before data contaminates it.
- Debrief sheet (YDD, Sep 2024): writable track map; one topic per pass (gears, braking…); each corner in four phases — braking stability, entry (steer + brake bleed), mid (max steer), exit (unwind + throttle); 1–5 scale under/oversteer per phase, written at the location.
- "Data can tell engineers what happened. Drivers often explain why" — the driver is the early-warning system (Brady, BTCC, Jun 2026).
- Overnight: databases updated with run plans, summaries and setups (Dymott).

## 3. Qualifying preparation

- Final practice run is low fuel / new tyre / full engine mode (Dymott, Saturday).
- The engineer's quali job is timing the garage exit and having fuel fills and tyre sets right; fuel is the minimum for the planned runs.
- Out-lap is a scripted procedure: accelerate and brake aggressively at chosen points, back off, create a gap before the last corners (F1 Atlas, Apr 2026); in 2026 F1 scripted to the second against a ~2 °C window (The Race, May 2026).
- On the in-lap collect balance, brake feel trend, tyre state, whether another push is realistic.

## 4. Live race strategy

- "We recalculate a lot, like every lap or change of position" (Collins, Sky, Apr 2023). Three model variables: degradation, pit-loss, tyre life + compound delta. Live inputs: live deg, overtaking difficulty, relative pace, live wear, ambient (Raceteq 2024).
- **Deviation detection is the core live product**: "the software is giving you some indication that degradation is higher than you expected" (Collins).
- Per-lap checklist: fuel-to-end and laps in hand to flag (one definition, named); tyre life vs plan and deg slope vs expected; pit loss under current conditions; gap ahead/behind projected to pit exit and who you rejoin behind; undercut value = fresh-tyre delta × laps until rival stops vs pit loss; overcut when the car staying out holds pace; pre-programmed SC/incident scenarios so the call is instant.
- Communication: one engineer, one voice; talk on straights, never at braking points (Motorsport.tech). Standard vocabulary: "box this lap", "li-co", "B-bal four is available", "diff mid plus one, **suggestion**" — the suffix marks advice vs instruction (F1 Briefing). Short phrase + confirmation.
- Disagreement: filter emotion, keep the technical core; the driver's live read is leading evidence (Gannon/Haas; Brady). F2: "if you lose that trust, you are done."

## 5. Pit stop execution

- The plan says *when*; the stop is re-sized at the moment: fuel window recomputed after a stop for the minimum remaining stops (Autopedia); sim tools sell "live race replanning" (LMU Tools).
- Stop cost decomposed: fixed dead time + fuel time + tyre time + lane transit; overfuelling adds weight, underfuelling forces a stop (Fanatec).
- Fuel quantity and tyre choice read back before pit entry; a moved stop lap means a moved fill (laps remaining × burn − aboard), never the original number.

## 6. Rival intelligence

- "Race strategists spend the same amount of time analysing the competitiveness of their rivals as they do themselves", updated live (Raceteq 2024).
- Per rival: stint length so far, stop count and lap, pace vs tyre age, whether their deg is steeper (Catapult RaceWatch, Jun 2024).
- Fed into undercut/overcut threat windows, who you rejoin behind, whether a rival can make the end without stopping.

## 7. Post-race debrief and learning loop

- Analysis starts at the flag; formal debrief ~2 h; engineers first, then driver; strategy reviewed in separate forums; "an open forum where you display all of the issues" (Vowles 2024).
- Stored artefacts: run plans, summaries, setups per event into the database (Dymott); a "pattern database of how each parameter affects vehicle behaviour" from the one-change tests (Collins Ltd).
- Scoring: predicted vs measured on the model's three variables.

## 8. Division of labour

- Race engineer makes final calls during sessions and carries responsibility; performance engineer advises and recommends, rarely decides live; flow is PE prepares options → RE filters and applies → driver feedback informs both (Track Team Driver; Red Bull).
- Documents passing between them: run plan, setup sheet + change list, run summaries, overlays, the strategy pre-plan.
- F2 (closest small-team analogue): one engineer does setup, strategy and scrutineering — the collapse works because the *authority* rule survives: whoever is live decides; the garage role recommends and stands down (Carlin, FIA F2, Mar 2022).

## 9. GT7-specific, post-Aug-2024 only

- **1.49 (25 Jul 2024)**: tyre algorithm rewritten around slip; tyres "cliff" rather than fade, warning signs ~90 % on the gauge; sliding costs far more than braking; fronts die first on entry (Barbara, Jul 2024; DG Edge: >50 % wear "a second or more per lap"). Fraga won the 2024 final on a triple-stop.
- **1.55 (30 Jan 2025)**: reduced load dependency in cornering, faster grip recovery off-track, suspension smoothing.
- **Measured on 1.55, Feb 2025**: wear vs temperature is curved with a compound-specific knee — RS ~88 °C, RM ~90 °C, RH ~93 °C — beyond which wear "gets exponentially worse" (GTPlanet test). Surface temp is a wear *rate* input. **Pre-1.71: suspect until re-measured.**
- **1.71 (20 Aug 2026)**: tyre heating/wear revised again, ABS slip ratio and cornering-brake behaviour changed, damper simulation changed, default setups corrected.
- **Pit stop**: tyres then fuel, sequential; 5–10 s dead time; refuel rate is a lobby setting in L/s; all tanks 100 L.
- **Fuel map**: the quoted 96/92/88/84/80 % power and 50 % consumption at map 6 are GT Sport era — **void**; no public post-1.49 re-measurement. The short-shift figure (~20 % fuel for ~0.5 s/lap) is likewise old; both need in-house calibration.
- No public tyre-wear database exists; this archive is already the best dataset on the subject.

## 10. What an ideal single-driver sim race engineering system must do

1. Per-session run plan with per-run purpose, fuel, tyre, setup delta, lap type (garage)
2. One-change, both-directions, big-enough discipline; prompt for the A-B-A leg (garage)
3. Tag every lap out/in/push/long/traffic; exclude non-clean before comparison (both)
4. Driver's report first, on a track map, four phases per corner, 1–5 (garage)
5. Run-by-run single version of events after every session (garage)
6. Parameter-effect database in percent of range (garage)
7. Pit loss per circuit from in/out laps (both)
8. Piecewise wear model with source and n; temp knee as a rate input (both)
9. Detect deg-higher-than-expected each lap and say so (live)
10. Fuel-to-end, laps-in-hand-to-flag, laps-to-stop as separately named quantities (live)
11. Gap ahead/behind projected to pit exit; who you rejoin behind (live)
12. Undercut/overcut thresholds vs each rival's stint age (live)
13. Per-rival stint length, stop laps, pace vs tyre age; can they make the end (live)
14. Pre-programmed incident branches (both)
15. Fill re-sized at the stop from laps remaining × burn − aboard, read back (live)
16. Stop cost decomposed; which term dominates (both)
17. Instruction then short reason, on a straight, with a confirmation word (live)
18. Every call marked instruction / suggestion / unconfirmed (live)
19. Driver override accepted, re-plan from it (live)
20. Quali out-lap scripted; garage exit timed (both)
21. Every live call logged with inputs and confidence (both)
22. Predicted vs actual scored after each race (garage)
23. Track book per circuit (garage)
24. Never derived-as-measured; every number carries source and n (both)
25. All live state reset at session boundaries (both)

## Sources

- Dymott, G. (ex-Williams) — Race Engineering day by day: Thursday, Friday (Mar 2022), Saturday (Oct 2022), schoolofraceengineering.co.uk
- Collins Ltd — Race engineering tips (2021), collinslimited.uk
- Fey, B. — Setup Sheets Part 3 (2010), buddyfey.blogspot.com
- Paceteq — ONE RACEHUB Run Sheet Layouts
- Racing Car Dynamics — Plan a practice session
- Your Data Driven — testing method / A-B-A (upd. Jun 2024); driver feedback method (upd. Sep 2024)
- Williams — Vowles on the post-race debrief (Jul 2024)
- Morson Edge — human-data partnership (Brady, BTCC, Jun 2026)
- ESPN — driver/engineer relationship (Gannon/Grosjean, 2018)
- FIA F2 — engineers do it all (Carlin, Mar 2022)
- Track Team Driver — RE vs PE; Red Bull — Guide to race engineering; Williams careers — performance engineer (2025)
- Sky Sports — Bernie Collins on strategy (Apr 2023); Collins, *How to Win a Grand Prix* (2024)
- Raceteq — how F1 teams determine the fastest strategy (Jul 2024)
- Catapult — strategy across championships (Jun 2024)
- Motorsport.com — undercut/overcut/SC explained (Jul 2023); F1 Briefing — delta time; radio for strategy; Motorsport.tech — radios
- F1 Atlas — out lap explained (Apr 2026); The Race — 2026 out-lap demands (May 2026)
- Autopedia — pit stop / fuel window; Fanatec — endurance sim pit strategy; LMU Tools
- GT7: Traxion 1.49; Barbara interview (Jul 2024); DG Edge 1.49 breakdown; 1.55 notice (Jan 2025); GTPlanet heat-vs-wear test (Feb 2025); 1.71 notice (Aug 2026); GTPlanet pit stops explained (2022); refuel rate (2023); tyre-wear chart thread (2025); fuel mixture tests (GT Sport era, void)

**Gaps not closable from public sources**: post-1.49 fuel-map measurement; published GT7 undercut/overcut or cold-out-lap delta; the *format* of a rival dossier.
