# NGR Pit Crew — UAT Diagnosis, Defect Register and Remediation Plan

**Date:** 7 August 2026
**Trigger:** Hardware UAT, night of 6 August 2026
**Codebase:** `C:\Projects\VR_Dashboard` (analysed against a snapshot taken 7 Aug 07:10)
**Scope:** Diagnosis only — no code has been changed. Implementation awaits sign-off.

---

## 1. The four symptoms you reported

1. Setups are still wrong.
2. Driver feedback was ignored.
3. The app ran one practice session and went straight to qualifying, without working through the tyres or settling the setup.
4. During track modelling it told you to box, then after you came out it still asked you to drive the pit lane.

All four are real, all four are reproducible from the source, and three of the four were confirmed against artefacts already sitting on your disk. They are not four unrelated bugs. They are four expressions of the same structural problem.

## 2. The structural finding

The project has built an extensive engineering doctrine — practice exit criteria, tyre-compound coverage, convergence ladders, evidence saturation, run plans, feedback arbitration, pit-lane corroboration — and then, during the migration to the new shell, wired almost none of it to the surface the driver actually uses.

I checked the live call graph for the modules that are supposed to govern a race weekend. These have **no non-test callers reachable from `main.py` or `ui/`**: `discipline_workflow`, `preparation_transitions`, `race_weekend` / `RaceWeekendPhase`, `evidence_coverage`, `coverage_dimension`, `evidence_saturation`, `tyre_evidence`, `readiness_grade`, `engineering_run_plan`, `run_candidate_selection`, `preflight_validation`, `setup_decision` (the driver-feedback arbiter, explicitly marked deprecated in its own docstring), and `tyre_curves` (imported by nothing at all).

So the 11,000 passing tests are testing a system that is largely not the system you drove last night. That is why software verification kept looking healthy while hardware UAT kept finding basics broken. This is the single most important thing to fix, and it is a wiring and gating problem more than an intelligence problem.

A second, equally consequential finding sits underneath the setup complaint: **the car data the engineering brain needs does not exist.** `data/car_specs.json` holds 579 cars but only `category`, `pp_rating`, `power_hp`, `weight_kg`, `aspiration`. Zero entries have `drivetrain`. Zero have `num_gears`. `data/car_setup_ranges.json` covers **four cars**. `data/car_weight_distribution.json` covers thirteen. There are no spring rates, no downforce figures, no wheelbase, no CG height, no GT7 slider limits or step sizes anywhere in the repository. Everything else is generic constants or percentages of a hand-written global range table.

---

## 3. Defect register

Severity: **P1** = blocks a trustworthy race weekend. **P2** = degrades quality or hides failure. **P3** = correctness debt.

### A — Base setup quality

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| A1 | P1 | **Synthesis-primary discards the engineered setup and replaces it with a walk from the midpoint of the *generic legal range*.** `centre = (lo+hi)/2`, `val = centre + (synth − centre) × 0.6`. With 575 of 579 cars falling back to `GENERIC_DEFAULTS`, "neutral" for springs is 10.5 Hz and for ride height 130 mm. | `strategy/setup_synthesis.py:431-437`, `strategy/setup_engineering_context.py:130` |
| A2 | P1 | **The confidence gate that should hold A1 back is always open.** `trustworthy = bool(lap_len and corners)` → shaping `"medium"` → passes the `{high, medium}` test. A track *seed* (length + expected corner count, no measured model) is enough. | `strategy/setup_synthesis.py:410`, `strategy/setup_engineering_context.py:159`, `strategy/track_tune_profile.py:138` |
| A3 | P1 | **Your proven Porsche setups are seeded and then overwritten.** Proven values enter via `proven_seed_overrides` but are never written into `context.working_windows`, so the `w.preferred is not None` guard that protects them never fires. | `strategy/driving_advisor.py:2633-2641` vs `strategy/setup_synthesis.py:423` |
| A4 | P1 | **Gearbox is a car-agnostic geometric spread, and the default runtime path authors a final drive with no gears.** Every 6-speed car gets 3.800/2.558/1.722/1.159/0.780/0.525 and FD 4.25 from two global constants, with no reference to engine, redline or track. Worse, the shell reads `num_gears` from `car_specs.json`, which has that key for **no car**, so `num_gears = 0` → a final drive is written with zero ratios. | `strategy/setup_baseline.py:243-366`, `:91-92`; `services/setup_inputs.py:181` |
| A5 | P1 | **Drivetrain defaults to empty, which silently becomes FR with flat neutral springs.** The classic form's "Auto-detect" resolves to `""`; `data/car_drivetrains.json` (527 cars) is never consulted on that path. | `ui/setup_form_widget.py:353-354`, `strategy/setup_engineering.py:89`, `:425-431` |
| A6 | P2 | **Three code paths author "the same" base setup with different inputs,** so the Base/Quali/Race comparison table disagrees with the sheet that gets applied (e.g. camber front 1.0 shown vs 2.3 applied). | `strategy/setup_authoring.py:296-307`, `strategy/driving_advisor.py:2719-2733`, `ui/setup_builder_ui.py:2264` |
| A7 | P2 | **Range data is thin and internally contradictory, and preference windows are treated as legal limits.** Four curated cars; generic ARB 1–7 while the curated cars use 1–10; ballast 0–200 in ranges vs 0–150 in the form spinbox. No step/increment model exists anywhere. | `strategy/setup_ranges.py:23-50`, `ui/car_ranges_dialog.py`, `ui/setup_form_widget.py:326` |
| A8 | P2 | **Low confidence is laundered into "approved".** `confidence.overall = "low"` is overwritten by `recommendation_status = "approved"`; the "too many changes" and "no-op" warnings are filtered out; a 30-field baseline reports zero warnings and enables Apply with an empty banner. | `strategy/setup_baseline.py:908-911`, `strategy/driving_advisor.py:786-815`, `:2812`, `ui/setup_builder_ui.py:76-77` |
| A9 | P2 | **Provenance labels lie.** Fields fall back to the "insufficient data → neutral" spring model and are still labelled "engineered for car + track + objective"; `_disposition_for_change` defaults unmatched provenance to AUTHORED. The eight "driver preference" flags evaluate True for every user, including two that directly oppose each other. | `strategy/setup_baseline.py:678-683`, `:783-787`; `strategy/setup_authoring.py:222`; `strategy/setup_driver_profile.py:71-90` |
| A10 | P2 | **Nine silent `except Exception: pass` blocks around the enrichment layers.** A run where the driver profile, history, proven library, chassis seeds and spring model all failed is indistinguishable in the response from a fully-enriched run. | `strategy/driving_advisor.py:2621, 2640, 2670, 2698, 2716, 2775, 2848, 2898, 2919` |
| A11 | P3 | Tyre compound and car class are accepted by the baseline builder and never used. `tyre_curves.py` has no importer in the repository. | `strategy/setup_baseline.py:537-542` |

**Verified end-to-end output** for `Mercedes-AMG GT3 '20` at Monza, status `approved`, zero warnings: springs 13.4/14.9 Hz, ride height 108/119 mm, camber 2.3 front / **4.8 rear**, toe front −0.47, LSD initial 48, aero 695/800. A Gr.3 car runs roughly 55–70 mm ride height, and rear camber above front is backwards. This is what A1 + A2 produce.

### B — Driver feedback

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| B1 | P1 | **New-shell feedback is never persisted.** `_on_feedback` tries `record_driver_feedback`, `_record_driver_feedback`, `save_driver_feedback` on the window. **None of the three exists in production code** — only in a test stub — and the loop is wrapped in `except: pass`. The only copy is `self._last_feedback`, an in-memory attribute lost on restart. | `ui/live_shell_bridge.py:4487-4506`; the sole `db.write_feedback` caller is `ui/dashboard.py:6274` (classic form) |
| B2 | P1 | **Analyse reads the last *submitted* dict, not the form.** Fill in all 14 dropdowns, navigate to Garage, press Analyse without pressing "Submit feedback" → 100% of it is ignored, and the headline blames missing evidence rather than the missing click. | `ui/live_shell_bridge.py:4325-4328` |
| B3 | P1 | **Any internal error converts full feedback into an all-clear.** One bad value makes the diagnosis throw; the conservative fallback ships `driver_feel_flags: {}` and the driver sees "no change recommended" with no error anywhere. | `strategy/setup_diagnosis.py:2079-2080`, `:1997`, `:453`; `strategy/driving_advisor.py:1553-1554` |
| B4 | P1 | **The database cannot hold most of what the form captures.** The `driver_feedback` table has 7 columns; the form has 14 fields. Traction, rotation, braking confidence, drive-out, straight-line, kerb, bottoming, gear choice and confidence are dropped on write, and `fuel_behaviour`/`overall`/`corners` name-mismatch their columns. | `data/session_db.py:103-118`, `:10186-10208` |
| B5 | P1 | **The classic form mis-keys two fields, destroying them on every write.** `label.lower().replace(" ","_").replace("/","_")` yields `mid-corner` and `rear_under_braking`; the writer reads `mid_corner` and `rear_braking`. Mid-corner and rear-under-braking always persist as empty string. | `ui/dashboard.py:6204` vs `:6073`, `:6075` |
| B6 | P2 | **The acknowledgement exists but never reaches you.** `build_feedback_dispositions` produces exactly the "I heard X, I did Y" record. It renders only in the classic UI, inside a collapsed `<details>`. `AnalysisResult` never extracts it, so the new shell structurally cannot show it. | `strategy/setup_diagnosis.py:1044`, `ui/setup_builder_ui.py:3673-3699`, `services/setup_service.py:351-360` |
| B7 | P2 | **Vocabulary gaps swallow specific complaints.** Mid-corner *oversteer*, exit *understeer* and gear "too short" are unmapped. `straight_line`, `confidence`, `tyre_condition`, `overall` and `corners` have no consumer in the brain at all — the corner selector's value is read once, only to be excluded from a display string. | `strategy/setup_diagnosis.py:419`, `:424-428`, `:444-448`; `strategy/practice_run_review.py:276` |
| B8 | P2 | **Stale feedback carries silently across disciplines.** `_last_feedback` is never cleared by start-run, record-run, discard-run, discipline change or begin-qualifying, so a qualifying analysis can quietly reuse a practice verdict. In the classic path it is worse: submissions are *appended* into the free-text box, so contradictory history accumulates permanently. | `ui/live_shell_bridge.py:4497`; `ui/dashboard.py:6242-6250` |
| B9 | P2 | **Rules suppress feedback-driven changes with no trace.** Protected/allowed-field locks and `delta == 0` return silently with no rejection entry; contraindications suppress silently. | `strategy/setup_rule_engine.py:849-861`, `:870-871` |
| B10 | P2 | **The driver-profile learning loop can never fire from real data.** It needs 4 sessions, 3 corroborations and 2× dominance, and matches on `"understeer"` while the form writes `"Too much understeer"` — and the rows it reads are mostly never written (B1/B4/B5). | `strategy/driver_profile_evolution.py:33-35`, `:49-50`, `:108-109` |
| B11 | P3 | The proper structured `DriverFeedback` arbiter — the module that would make feedback a first-class evidence tier — is dead code by explicit declaration. | `strategy/setup_decision.py:63`, `:155-169` |
| B12 | P3 | **There is no voice capture surface for driver feedback at all.** `voice/` contains zero references to feedback, feel, understeer or oversteer. If any of last night's feedback was spoken, nothing received it. | `voice/command_vocabulary.py`, `voice/query_listener.py`, `voice/voice_controller.py` |

### C — Session progression

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| C1 | P1 | **There is no race-weekend state machine on the live path.** Five state machines exist; none sequences the disciplines. `RaceWeekendPhase` — the one that would — has zero references outside its own definition. `assess_discipline_workflow`'s own docstring says "it gates nothing autonomously", and it has no practice branch at all. | `strategy/race_weekend.py:41`; `strategy/discipline_workflow.py:6`, `:37`, `:58` |
| C2 | P1 | **The objective engine rotates on breadth, so one sample retires a domain.** Ranking is by confidence order first; a single sample lifts a domain from NONE to EMERGING, which outranks every untouched domain. Runtime-verified: `setup_qualifying` is nominated as the **third** objective from every starting configuration. | `strategy/preparation_evidence.py:343`, `:351`, `:357` |
| C3 | P1 | **One lap counts as one complete evidence sample, and one telemetry session can be counted three times.** `is_valid = laps > 0`, no clean-lap floor (the `MIN_CLEAN_LAPS = 5` constant is used elsewhere). The binding key is `(activity_id, session_id)` and nothing checks whether that session is already bound. One on-track run, recorded three times, satisfies base, race and qualifying. | `data/session_db.py:7648`, `:1128`; `strategy/practice_run_recording.py:240`; `ui/live_shell_bridge.py:2094` |
| C4 | P1 | **"Begin Qualifying" performs the transition with no check whatsoever.** The handler body contains zero validation. The only defence is a disabled button, and its readiness mapping treats `developing`, `adequate`, `strong` and `unknown` as non-blocking — only the literal string `missing` blocks. | `ui/live_shell_bridge.py:3603-3632`; `ui/components/qualifying_readiness.py:148`; `ui/shell_feed_adapters.py:385` |
| C5 | P1 | **Selecting the Qualifying tab in the Garage silently converts the live session.** `_on_discipline` sets the discipline, and `refresh()` pushes `set_session_type_override(SessionType.QUALIFYING)` on every 750 ms tick. The Garage offers only Race and Qualifying — there is no Practice/Base tab — so building a qualifying setup has already put the app in qualifying. | `ui/live_shell_bridge.py:3583`, `:670`, `:3715-3721`; `ui/components/setup_workspace.py:46` |
| C6 | P1 | **Per-compound tyre coverage is computed correctly and gates nothing.** Its only consumers are a progress label and a combo-box nudge. It also disables itself entirely — "no restriction" — if the event's `available_tyres` is empty. | `ui/live_shell_bridge.py:2725`, `:2736`, `:2718`; `strategy/programme_map.py:198`, `:236` |
| C7 | P1 | **No "driver is comfortable with the setup" gate exists anywhere.** `grep -i comfortab` across the non-test tree returns only CSS comments. | — |
| C8 | P2 | **No multi-run practice plan is ever generated.** Activities are minted one at a time on demand. The three modules that produce real plans are all disconnected; the new shell imports `build_test_plan` from `setup_test_plan`, **which does not exist** (the module exports `build_test_sequence`), and swallows the ImportError. | `services/event_setup.py:375`; `strategy/practice_run_recording.py:142`; `ui/setup_recommendation_vm.py:250-254` |
| C9 | P2 | **The programme map and the objective engine contradict each other on screen.** The map says three runs to cover a domain; the objective engine moves off it after one. | `strategy/programme_map.py:29` vs `strategy/preparation_evidence.py:357` |
| C10 | P2 | **The convergence ladder is fed partly synthetic inputs** — `outstanding_experiments` is hardcoded to 0 and `has_final_confirmation` is never set — and reaches the UI only to show or hide the Lock button. Nothing in the qualifying path reads it. | `data/session_db.py:7660-7670`; `ui/live_shell_bridge.py:3318` |
| C11 | P2 | The "Start Race" readiness list is explicitly documented as "never hard-stop" and proceeds on a Yes/No dialog. | `ui/live_shell_bridge.py:2339`, `:3641` |

### D — Track model and pit lane

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| D1 | P1 | **The "box this lap" prompt is not wired to any pit detection.** In that prompt, "box" means *press the Stop recording button*. `stop_capture` has exactly one caller — a widget click. No telemetry path calls it. Your physical pit stop was a no-op for the modelling workflow, the pit lap scored as usable, convergence still held, and the same callout fired again on the next clean lap. **This is the primary cause of what you saw.** In VR you cannot press the button, so the flow cannot advance. | `data/track_convergence.py:148` (prompt) vs `ui/live_shell_bridge.py:2667`, `:2671-2674` (only caller) |
| D2 | P1 | **Off-by-N-laps bug in pit-lane mapping.** `_pit_lane_baseline_laps` is read from the *old* session immediately **before** `start_session()` allocates a new session with `laps = []`. The gate `len(laps) <= baseline` then requires N more laps, where N is the pre-approval lap count (typically 5–7), before a single mapping attempt is made. The pit lap you just drove is discarded with the old session. | `ui/live_shell_bridge.py:2521` → `:2526` → `:2546`; `data/track_calibration_runtime.py:207` |
| D3 | P1 | **Pit-lane mapping is structurally impossible for an already-approved track.** `map_pit_lane` refuses unless `session.artefact("station_map")` is loaded, and `refresh_disk_readiness` never loads it from disk while `select_track` clears the artefact dict. The map *renderer* has a disk fallback; the mapper does not. So after any restart, "Approve the track model before mapping the pit lane" is unanswerable. | `services/track_modelling.py:116`; `data/track_modelling_session.py:120`, `:163`; cf. `ui/live_shell_bridge.py:2626` |
| D4 | P1 | **Pit lane is not a step in the state machine and not part of on-disk readiness.** The six-step rail (`IDENTIFY → CAPTURE → BUILD → REVIEW → VALIDATE → ACTIVATE`) has no pit action, state or message. The outstanding step lives only in `_pit_lane_mode`, an in-memory flag lost on restart. **Confirmed on your disk:** the Monza model has `"accepted": true` beside `"pit_lane": null`. | `data/track_modelling_coordinator.py:52`, `:68`, `:96`; `data/track_readiness_disk.py`; `data/track_models/*.station_map.json` |
| D5 | P2 | **Pit-lap detection is disabled, so pit laps inflate the clean-lap count.** `pit_detection_enabled` defaults False and no production caller opts in, so `lap.is_pit_lap` is never True. Convergence therefore never excludes a pit lap, the classic tab shows "Pit lane: not detected" forever, and the lap export omits the flag entirely so it could not survive a save anyway. | `data/track_calibration.py:868`, `:932`, `:1275-1283`; `data/track_calibration_runtime.py:317` |
| D6 | P2 | **The geometric threshold is too wide.** Detection requires the car to be more than **60 m** from the nearest station; most pit lanes run 15–30 m from the racing line. A correct traversal returns "I couldn't see the pit lane on that lap". | `data/track_station_map.py:623` |
| D7 | P2 | **Even a successful mapping goes to a store the live engineer never reads.** Modelling writes `station_map.pit_lane`; the live pit-lane resolver reads `data/track_library`, whose `index.json` is `{"tracks": []}`. Live pit corroboration is permanently inert. | `ui/live_ui.py:886`, `data/track_library.py`, `data/track_library/index.json` |
| D8 | P2 | The instruction "a drive-through is enough — no need to stop" is unsatisfiable by the only telemetry pit detector that exists, which requires refuelling or a ≥3 s stop below 10 km/h **in RACING phase**. Modelling runs in Time Trial, where that phase never occurs. | `data/track_convergence.py:170` vs `telemetry/state.py:665-691`; `data/track_calibration_runtime.py:238` |
| D9 | P3 | `_try_map_pit_lane` runs roughly 12 million distance computations in pure Python, synchronously on the Qt thread inside a 750 ms timer, wrapped in a bare `except: pass`. A slow or failing attempt is indistinguishable from a no-op. No tests cover either pit-lane function. | `ui/live_shell_bridge.py:2534-2557` |

### E — Cross-cutting

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| E1 | P2 | **The stray-window guard has never run.** `main.py` calls `os.path.join` / `os.path.dirname` without importing `os`; the `NameError` is swallowed. This is the mitigation for the still-unconfirmed flashing/focus-stealing box. | `main.py:791-796` (imports at `:7-14`) |
| E2 | P2 | Two shells and two feedback forms coexist, and only the classic path has working persistence. The migration doc lists `_record_driver_feedback` as Stage 2 — planned, not done. | `docs/SINGLE_SYSTEM_MIGRATION.md` §2 |
| E3 | P3 | `PROJECT_STATE.md`, `REQUIREMENTS.md` and the three root-level UAT scripts all describe the classic tab layout the driver no longer sees. The UAT scripts are blank templates with empty defect registers; any UAT run from them mis-navigates. | `SETUP_BUILDER_UAT.md`, `LIVE_RACE_ENGINEER_UAT.md`, `STRATEGY_BUILDER_UAT.md` |
| E4 | P3 | Setup history `config_id` hashes track name + car + length, not `layout_id`, so two layouts of one track share history. | `PROJECT_STATE.md`, deferred list |

---

## 4. How to improve the base setup process

The current process is: build a physics-informed setup, then throw it away and walk from the midpoint of a generic slider range. Improving it is not a matter of better reasoning — the reasoning layer is decent and largely unused. Six changes, in dependency order.

**Anchor, never centre.** The neutral reference for every field must be a physical baseline, not the midpoint of a legal range. In order of preference: the car's GT7 stock setup, then the nearest proven setup you have run, then a class archetype (Gr.3, Gr.4, Gr.B, road). The midpoint of `(0, 1000)` downforce is not an engineering position, it is an absence of one. Delete `centre = (lo + hi) / 2` from the synthesis path and replace it with `anchor = resolve_anchor(car, track, discipline)`.

**Build the car model — this is the real bottleneck.** No reasoning improvement survives contact with 4-car range coverage and zero drivetrain data. What is needed per car: drivetrain, gear count, GT7 slider minimum/maximum/step for each adjustable parameter, stock ride height, stock spring rates, stock downforce, stock gearing, and weight distribution. Three sources, used together. Seed drivetrain from the existing `car_drivetrains.json` (527 cars, already on disk, currently unused by the setup path). Seed limits and stock values from class archetypes, so an unmapped Gr.3 inherits sane Gr.3 numbers rather than generic ones. Then capture actuals from the game: a "record this car's sliders" screen where the driver types the min, max and step GT7 shows for a car once, and it is stored permanently. Start with the NGR fleet — the Porsche Cup and Supercars grids — which is a few dozen cars, not 579. Until a car has real data, it must be visibly marked as running on archetype defaults.

**One authoring path, with an explicit provenance tier per field.** Collapse the three current authors into one. Every field carries a tier: PROVEN (this car, this track, this discipline), TRANSFERRED (same car elsewhere, or same class), ENGINEERED (physics model with real car data), ARCHETYPE (class default), GENERIC (last resort). The Garage shows the tier per field. Only ENGINEERED and above may carry the label "engineered for car + track + objective". A sheet where most fields are GENERIC should say so at the top, not present as "approved".

**Make confidence able to say no.** Replace `trustworthy = bool(lap_len and corners)` with a real evidence bar — an accepted track model with reviewed segments, plus a minimum number of clean laps on this car at this track. Below the bar, synthesis is advisory and the engineered baseline stands. And stop laundering `confidence.overall = "low"` into `recommendation_status = "approved"`: the status must be the minimum of the two, and the filtered warnings must come back.

**Author a gearbox from evidence or not at all.** Gears should come from measured top speed and longest-straight length in the track model plus the car's redline. If those are unknown, author nothing and say "keep the stock gearing" — that is a better answer than a final drive of 4.25 with no ratios attached, which is what the default path currently ships.

**Fail loud.** Replace every `except Exception: pass` in the enrichment chain with a recorded degradation. The response should carry a `degradations[]` list, and the Garage should render it. "I built this without your history, without the proven library and without a spring model" is a useful sentence. Silence is not.

One structural addition: there should be a **Base** sheet. The Garage currently offers only Race and Qualifying, so there is nowhere for a base setup to live, and no anchor from which the two disciplines are deltas. Base is the anchor; race and qualifying are explained deltas from it.

---

## 5. Remediation plan

### Phase 0 — Stop the bleeding (half a day)

Small, unambiguous, high-value fixes that make the next UAT worth running.

| Fix | Defect |
|---|---|
| Persist new-shell feedback: implement the write path instead of probing for three non-existent methods | B1 |
| Correct the pit-lane baseline off-by-N: read the lap count *after* `start_session()`, or set it to 0 | D2 |
| Load the station map from disk in `map_pit_lane`, reusing the renderer's existing fallback | D3 |
| Raise the synthesis confidence bar so a track seed no longer authorises overwriting the engineered setup | A2 |
| Resolve drivetrain and gear count from `car_drivetrains.json`; author no gears when the count is unknown | A4, A5 |
| Add `import os` to `main.py` | E1 |
| Stop overwriting low confidence with "approved"; restore the filtered warnings | A8 |

### Phase 1 — Base setup correctness (your stated priority)

Car data model and archetype table; single authoring path with provenance tiers; anchor-based synthesis; evidence-based gearbox; degradation reporting; a Base sheet in the Garage. Fixes A1, A3, A6, A7, A9, A10, A11.

Verification: golden-file tests asserting that a Gr.3 baseline lands in physically sane windows (ride height 50–80 mm, front camber ≥ rear camber, spring frequencies within class band), plus a regression asserting that a proven setup survives synthesis unchanged.

### Phase 2 — Close the feedback loop

Widen the `driver_feedback` schema to hold all 14 fields; fix the classic key mangling; map the missing vocabulary; surface `feedback_dispositions` in the new shell as a visible "what I did with what you told me" panel; clear `_last_feedback` on run and discipline boundaries; make suppressed rules emit a rejection record; re-enable the arbiter or delete it. Fixes B2–B11. B12 (voice feedback capture) is a scoping decision, not a bug fix.

### Phase 3 — One weekend state machine with real gates

Promote `RaceWeekendPhase` to the authoritative sequencer and route every transition through it. Enforce practice exit criteria: per-compound coverage, a clean-lap floor, convergence state, and an explicit driver-comfort confirmation. Generate a multi-run practice plan up front. Prevent one telemetry session binding to multiple activities. Make the Garage discipline tab stop mutating the live session type. Fixes C1–C11.

### Phase 4 — Track modelling and pit lane

Make pit lane a first-class step in the coordinator with on-disk readiness; drive the transition from telemetry rather than a button the driver cannot press in VR; re-enable pit-lap detection with a threshold that matches real pit lanes; write the mapped pit lane to the store the live engineer actually reads; move the mapping computation off the Qt thread. Fixes D1, D4–D9.

### Phase 5 — Re-certify

Rewrite the UAT scripts against the new shell's eleven nav destinations (the current ones target classic tab names and are blank templates), then run the certification standard already described in the project doc: practice, then qualifying, then race, one at a time, instrumented for failure.

---

## 6. Decisions I need from you

1. **Sequencing.** Phase 0 then Phase 1 (base setup) as you prioritised — or Phase 0 then Phase 3, on the argument that a correct setup delivered through a broken weekend flow still can't be validated?
2. **Car data sourcing.** Is a "type in this car's GT7 slider ranges once" capture screen acceptable, starting with the NGR fleet? That is the fastest credible path to real data, but it puts the work on you.
3. **The classic shell.** Retire it now, or keep the dual path? Several defects exist only because two shells and two feedback forms coexist.
4. **Scope of this session.** Shall I implement Phase 0 now, against a branch, with tests — or do you want to review this register first?

---

*No files in `C:\Projects\VR_Dashboard` have been modified. A source snapshot was taken to `_to_delete\pitcrew_src.tar.gz` in the repo root — safe to delete.*
