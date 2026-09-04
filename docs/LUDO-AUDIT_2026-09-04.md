# Ludo audit — how setups are built, what is and is not working, and the app link

**4 Sep 2026 · v1.71 · read-only audit of the `ludo` skill, the knowledge base, `data/pitcrew.db`,
`brain/RECONCILIATION.md`, and the Spa (event 9) and Daytona (event 10) programmes. Validated by
an adversarial critic pass; every correction it made is folded in and marked ⟂.**

Files: `.claude/skills/ludo/` · `brain/_inbox/` · `brain/RECONCILIATION.md` §H–X · `brain/car-state/huracan-daytona.md` ·
`pitcrew/store/db.py` · `pitcrew/prompts/` · `pitcrew/hub/` · `pitcrew/strategy/handover.py` · `tools/`.

---

## 0. The answer in five lines

1. **No instrument in the programme can show a tune "working".** Lap-time noise (2σ 1.66 % of a lap, ≈1.75 s at Daytona,
   2.77 s spread at Spa) is larger than any setup effect, and seven derived handling indices have been calibrated and
   discarded. The only judge left is the driver's report, which the charter already makes primary. Ludo is not failing
   to find a tune; the programme cannot show any tune succeeding except by feel. ⟂
2. **The record is wrong about the car and the app cannot see it.** Eight consecutive sessions with a wrong setup record;
   12 Daytona sessions with no sheet bound; the change ledger writes the same seven rows five times; two people change
   the car (driver in the garage, Ludo on paper) and one of them records. This morning's five A/B runs reproduced it:
   five screenshots in Downloads, zero rows in the database.
3. **The regulations the driver keeps having to recite are already in the hub** (`Series.defaultLobbySettings`,
   `RoundCarOverride`: 550 BHP / 1,275 kg for Daytona, mandatory stops 1, multipliers, ABS) and nothing in `pitcrew/`
   reads them. The hand-entered event row is the stale one (`mandatory_stops = 0` on event 10). ⟂
4. **Ludo's doctrine is unmeasured lore.** `02` §10 symptom tables: 230 lines, three confidence tags, four rows with a
   measurement behind them, all v1.70. The Shelby has no measured profile at all.
5. **What does work:** the refusal card, predictions with falsifiers scored in `RECONCILIATION.md`, within-car telemetry
   comparisons (diff lock by gear, front L/R slip split, body height at matched speed, K-based gearbox cutting), the
   strategy optimiser, and the settings-screen screenshot as the rank-zero instrument. Keep all of it.

---

## 1. What Ludo is, and what it is not

- A Claude Code skill (`SKILL.md` 21 KB, five references, eleven evals). Six modes, a shared spine, a refusal card,
  a recording obligation.
- **There is no setup-recommendation engine in the app.** `pitcrew/` holds a symptom vocabulary (`data/gt7_symptoms.json`,
  eight groups) rendered into a prompt, descriptive corner flags (`analysis/corners.py`, "gates nothing"), and a stint
  optimiser (`strategy/model.recommend`). All symptom → slider reasoning happens in the LLM session from
  `brain/_inbox/02` §10, the driver's report and ad-hoc frame queries.
- The app supplies the record (`setup_sheets`, `setup_changes`, `range_records`), the 60 Hz archive (`lap_frames`),
  two gates (`prompts.questions.resolve`, `tyre_models.speakable`), and the export.

## 2. The measured track record since 1.71

### Spa Round 5 (event 9, 27–31 Aug)
| sheet | vs previous | note |
|---|---|---|
| v2 (38) | 8 sliders moved | issued from Fuji v1 before any Spa lap |
| v3 (46) | 1 (`lsd_i`) | |
| v4 (54) | 1 (`de_f`) | |
| v5 (55) | 7 | ⟂ a **transcription of the car** on 31 Aug (bb from the driver, `de_r` from the 50 the car actually had), not a seven-move design |

- 31 Aug: three changes in 45 minutes on 2–3-lap samples (J5); eight over the day on 2–6-lap samples, most with an
  excursion (K3). ⟂
- The null control (p99 lateral g > 180 km/h) was flat across nine sessions, but that instrument measures the tyre's
  high-speed limit in 6th-gear corners where the diff is 97 % locked at every setting; it could not have seen the
  balance changes that were being attempted. Honest reading: **nothing could be shown to work**, not "nothing worked". ⟂
- Race s112: P6; four of five off-track runs at Blanchimont, throttle lifted there on 17 of 19 laps.
- Verdict reversals on file: `lsd_a` "refuted" carried three times when only raising had been tested (I1); ride height
  raised for bottoming when springs were the lever (L1); `de_r` re-asserted at 36 while the car read 50 (H6).
  ⟂ The draft's "`toe_f` reverted when it was right (L3)" is **wrong**: V2/W2 measured toe-out producing the asymmetric
  front-left lock, and reverting it removed it. The revert was right.

### Daytona Round 6 (event 10, 1–4 Sep)
12 sessions, no sheet in `setup_sheets`, no document in `brain/_inbox/setups/`. Scoring the predictions in
`RECONCILIATION.md` §R–X: **seven confirmed** (R1 terminal, R3 excursion 3.6 % out, T1 gearbox, W2 release snap, W5,
X1 wear side, K1 refuel rate) against **five missed or overturned** (W1 dead band, W7 unresolved, X5 wrong falsifier,
T2 drag cost, S1). ⟂ The process improved markedly on Spa: platform priced in millimetres, 6th cut from measured K,
toe fix confirmed on its own channel (front L/R split 0.0669 → 0.0241), wear map recovered from the recording.

The driver's read beat Ludo's on about ten occasions. ⟂ Half were **Ludo's own errors with the answer already on
file** (unused ride-height A/B in the archive, wind test not run, reading the wrong of two markdown records, misreading
its own 13 Aug turbo document, falsifier arithmetic). Half were **genuinely missing inputs**: brake bias moved in-car,
camber moved after the screenshot, the regulations, the turbo, the gauge not sampled live.

### This morning's five A/B runs (sessions 120–124) — recorded today in `brain/car-state/huracan-daytona.md`
Wing 420/600 · 420/650 · 410/635 baseline · camber 1.0/1.0 · camber 4.0/4.0. **Two clean laps in five sessions.**
Wear rate identical at the gauge's resolution in all five (RR 0.0556/lap, replicating the race stint's 0.0570);
front camber 1.0 → 4.0 does not move front surface temperature; the 50-click rear-wing spread is 2.0 km/h of terminal,
inside the floor. GT7's Measure readout responds to aero (high-speed stability −0.45 → −0.36) and is inert to camber.
Nothing else is comparable across the runs. Five screenshots, zero database rows.

## 3. What is not working, ranked by cost

1. **Rank zero.** Nothing reads GT7's tuning screen; `sessions.setup_sheet_id` is NULL on all 12 Daytona sessions
   because no Daytona sheet was ever filed; only the gearbox (ratios, not final drive) is feed-verifiable; the driver
   trims in the garage between and after runs (bb, `cam_f`) with nothing recording it. The car-state file is a hand
   workaround. Driver, 3 Sep: *"you need to log changes much better."*
2. **"Works" has no operational definition at the resolution the process pretends to.** See §0.1. Every judgement
   that used lap time was noise; the survivors measure mechanisms, not merit.
3. **The one-change rule is stated everywhere and honoured only by accident.** Spa v2 moved eight; three changes in
   45 minutes; Daytona run 4 carried three. ⟂ V14 states the rule's real content — *separable instruments*, not a count —
   and the skill has no "platform" mode that says which coupled sets are legitimate and how they are judged.
4. **Doctrine.** `02` §10 has three confidence tags in 230 lines and four measured rows (v1.70); `02:1002` (lengthen
   1–3, rank-one exit fix) contradicts `17`'s measurement; the Shelby profile is the Mustang Gr.3; three Spa/Daytona
   calls in `05` refused on measurement and `05` never amended; `09`'s template still says `gameVersion 1.70`.
5. **The record drifts because it is in five places.** `dc_r` 26 vs 30 in two files (caught by the driver).
   `11-car-slider-ranges.md` still carries the Shelby as stale v1.70 and a `verified: false` JSON block while
   `range_records` (the only thing code loads) has all four cars verified v1.71 — and `gt7-brain/SKILL.md` tells Ludo to
   read `11` before issuing any sheet. Spa, Fuji and Daytona reasoning live only in memory files and `RECONCILIATION.md`;
   `check_setup_sheets.py` looks in `setups/`. `RECONCILIATION.md` §H–X and `driver.md` are **uncommitted** since 25 Aug.
   The memory index is over its load limit.
6. **The change ledger is a session counter.** `Store.note_sheet_change` (`db.py:894-902`) walks back to the last
   *different* sheet, so the 54 → 55 delta is filed at sessions 107, 108, 109, 110 and 112 (35 rows for one revision;
   plus 17 junk rows at s102 for keys that never changed). The export emits all of them undeduped. ⟂ Commit `4e7f665`
   already added `reason`/`source` and `tools/log_setup_change.py`; the walk-back baseline is the half that remains.
7. **Tests that cannot resolve what they test.** Seven derived indices discarded after calibration; the front-lock
   percentage has an 8.5–9.6 pp floor and retracts a "front lock halved" number. Survivors: within-axle splits,
   diff lock by gear, body height at matched speed, K, the recovered gauge.
8. **Wear.** ⟂ 33 of 61 v1.71 sessions carry at least one wear lap (driver entry or `hud-video`); 2 of 84
   `tyre_models` rows are speakable; no production code reads `tyre_models` (only `tools/data_health.py`). The live
   sampler reads an OBS projector, not the recording, and the 3 Sep race had none.
9. **Skill claims the code does not support.** "`tyre_models` is the single source" (no production reader);
   `resolve()` is already run by the app on every Engineer-screen refresh; `RACE_PLAN`/`QUALI_PLAN` question kinds are
   unreachable from the UI; `gather` can attach a sheet from another circuit; `data_health` can report another car's key.
10. **Evals test refusals, not the failures that happened.** None for multi-change sheets, rank-zero before diagnosis,
    dead-band falsifiers, judging on a 2-lap sample, or platform versus trim.

## 4. What is working — keep

- The refusal card with the number re-derived (the Bus Stop refusal V10 is the model).
- Predictions with falsifiers, scored in a supersession ledger. Nothing else in the project produces learning.
- Telemetry-first, within-car comparisons: rear never locks (0.00 % over 24+ laps, three circuits); diff lock by gear;
  front L/R slip split as the toe signature; wind via opposite-facing straights; `dc_r` timing via squat rate;
  K-based gearbox cuts verified to 0.3 %.
- Reading the driver: his report is the brief and his overrides are scored.
- The strategy path (`build_inputs` → `recommend` → `certify`), refuel rate measured 1.0009 L/s against 1.0 declared.
- The settings-screen screenshot: 23 of 24 values, zero laps. It works in VR too (run 1a was a VR weekend). ⟂
- Daytona platform arithmetic — springs and ride height priced in the same units, first time.

## 5. The app link

### 5.1 Hub
`pitcrew/hub/read.py` opens the NGR hub's Prisma SQLite read-only. It reads drivers, series, entries, rounds, results,
points. ⟂ **The hub DB also holds** `Series.defaultLobbySettings` (tyre/fuel multipliers, refuel rate, lap count,
weather mode, BoP flag, tuning allowed, compounds, mandatory stops, ABS, countersteer) and `RoundCarOverride`
(Huracán 550 BHP / 1,275 kg for Round 6, dated 29 Jul). Nothing in `pitcrew/` reads them. Known defects: `events.series`
typed in the Event screen is dropped by `controller._on_event_saved`; `series_teammates` has no production writer;
`rounds().track` is read by nothing; round status is `SCHEDULED` on all 57 rows; track strings carry an encoding fault.

### 5.2 Event selector
Sets one key, `app_state.active_event_id`, with ~28 dependants (session creation, circuit key, sheet binding, strategy,
George's arm, range-record version). **The picker can go; the event row cannot.** Proposal: the next hub round for the
series you are entered in becomes the active event, prefilled with track, car, and the regulations from
`defaultLobbySettings` + `RoundCarOverride` with `source = hub`; the driver overrides by exception. ⟂ This is the reverse
of "regs entered once per round" — the hub is the better source and the hand-entered row is the one that has been wrong.
Preconditions: persist `events.series`; map hub track strings to `circuit_key`; a deterministic `events.name`.

### 5.3 Ludo ↔ George
The handover is real and production-wired: `strategy/handover.py` (triggers, actions, structural actions gated),
stored in `strategies.plan_json["handover"]`, read by `RaceCoordinator` at every arm, three doors (`accept`, CLI,
MCP `write_strategy`/`propose_strategy`/`write_race_knowledge`/`write_setup_sheet`), journaled to `engineer_writes`.
**`engineer_writes` has two rows in the whole archive** (29 Aug, RBR). Every Spa and Daytona sheet, plan and note went
in by hand or not at all. George reads the plan, playbook, practice evidence, event row and `race_knowledge`; he does
not read the setup sheet (only the shift beep) or `tyre_models`. `radio` holds eleven rows.

Division of labour that the code already supports and the practice should follow:
- **Ludo** (before/after): platform and trim decisions, sheet + prediction + falsifier, plan + playbook, debrief scoring,
  doctrine amendments. Every write through MCP, journaled.
- **App** (always): the record (one sheet per run with provenance, ranges per car with version history, regs per round
  from the hub), capture (UDP, gauge, settings screen), gates, the run card.
- **George** (live): executes the playbook, reads the run card into the brief, refuses by name what the feed cannot
  carry, logs radio.

### 5.4 Per-run setup confirmation — "the run card"
Nothing reads the tuning screen; the capture stack reads the gauge, leaderboard, pit columns, compound disc, roster
names, HUD digits and times. Rank zero today is the driver photographing the screen and Ludo transcribing by eye.

Proposal, with the critic's objections built in ⟂:
1. **Session-start gate.** The app shows the sheet it believes is in the car (or "no sheet") and requires one of:
   a settings-screen capture attached to the session; or a driver-declared delta list (`key value reason`). A bare
   "as issued" click is recorded as a *claim* with who/when, never as `source = screen`. Without one of these the
   session is `setup_unconfirmed`, George says so in the brief, and the export refuses (it already refuses on
   `sheets_disagree`).
2. **Brake balance is not on the settings page.** The gate asks for it by voice or one field, every run.
3. **Mid-visit changes.** Garage entries between runs of one visit are where the last two defects were. A "changed
   something in the garage" PTT report intent, and the settings capture re-taken at each out-lap, close that hole.
4. **One sheet per run, always** — but a cloned sheet is only allowed when it carries per-value `source` rows
   (`screen`/`driver`/`issued`). A silent clone is the 23 Aug wrong-sheet defect in new clothes.
5. **Settings-screen reader.** GT7's tuning pages are fixed-layout 2D on the console output regardless of VR; the app
   already template-matches digits without OCR. Even an attached screenshot with no reading is a step up — provenance
   survives. Reading it is the same instrument class as `hud_digits.py`.
6. **Ledger from the gate.** Confirmations write `setup_changes` with source and reason; fix the walk-back baseline
   (previous session's sheet, one row per transition); dedupe the export.
7. **Ranges.** Keep the Car screen → `range_records` as the only range store (user constraint, 4 Sep); add a history
   row per game version instead of overwriting; retire the JSON block in `11`.

## 6. Recommendations, in order of return per hour

1. Read `defaultLobbySettings` + `RoundCarOverride` from the hub into the event row with `source = hub`. Removes the
   "fifth naming" defect (M1/P/Q) and the `mandatory_stops = 0` error outright.
2. Bind a sheet to every session via the run card (§5.4), and make Ludo's sheet writes go through MCP so
   `engineer_writes` is the journal it was built to be.
3. Fix `note_sheet_change`'s baseline and the export dedupe.
4. Give Ludo a `platform` mode: coupled sets (`nf`/`rh`/`dc`/`df`) judged on clearance instruments for *cost* and on
   the driver's report for *merit* — and say so. Keep `trim` as one slider on its named channel with a stated floor.
   Lap time is never the judge in either.
5. Every sheet revision carries the instrument and its measured floor per change, a prediction with a complementary
   falsifier from the same expression, and a minimum clean-lap count. Add evals for exactly these.
6. Collapse the record: car-state file generated from the database, not by hand; commit `brain/` on every debrief;
   trim the memory index under its load limit.
7. Tag every `02` §10 row measured/void; file the refuted `05` calls into `05`; fix `09`'s template version.
8. Make the OBS projector check a pre-session gate George refuses to start without, or capture from the recording.
