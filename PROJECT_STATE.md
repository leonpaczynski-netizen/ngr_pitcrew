# GT7 Pit Crew Project State

## Current Mode
Architecture Stabilisation Mode.

Do not add new features until core data flow, persistence, telemetry storage, and AI context are stable.

## Repository / Build Status (2026-07-14 — Engineering Brain Phase 1: closed-loop lockout)

**Branch `engineering-brain-phase1-closed-loop` from `master` @ merge `b2da2bf` — committed locally.** First slice of the "Engineering Intelligence Plan of Attack" (docs/ENGINEERING_BRAIN_PLAN.md): stop the app repeatedly making the car worse.

**NEW `strategy/setup_lineage.py` (pure):** `SetupExperiment` (parent + changes + each change's expected symptoms) / `ExperimentOutcome` (better/worse/unchanged + per-symptom + new problems); `attribute_change_outcomes` → EFFECTIVE/INEFFECTIVE/HARMFUL/UNKNOWN (harm attributed only via targeted-worse or a DIRECT side effect, so an ineffective change isn't blamed for another's damage — matches the plan's ARB=ineffective / LSD-accel=harmful example); `failed_directions` scoped to car+track+objective+field+direction (a Fuji failure is never a global ban); `apply_direction_lockout` (overturnable by explicit new evidence); `rollback_target`/`rollback_advice`; `blocked_rules_from_outcomes` (block a rule that worsened the car ≥2× and never improved; a later `improved` lifts it).

**Rule-engine lockout wired:** `run_rule_engine(..., blocked_rule_ids=…)` — a locked rule is surfaced as REJECTED (with reason), never proposed; Pack-A safety protection still runs first. `build_combined_setup_response` builds the lockout from the `learning_outcomes` it already loads (scoped car+track+layout) and surfaces `closed_loop_lockouts`. **No schema migration** — consumes data already captured by `_trigger_scoring_pass`.

**Then delivered (same branch): field-level lockout across all authors** (`_rule_field_directions` + `failed_directions_from_learning_outcomes` → the balance solver + driver-fit changes respect failed directions, not just the rule engine); **lineage persistence** (additive **DB migration v15**: standalone `setup_lineage` table; `record_lineage`/`get_lineage`/`record_lineage_outcome_by_rec`; wired into `apply_recommendation_for_car_track` + the scoring pass); **contradiction hard-fail** (`detect_diagnosis_contradictions` — gearing/wheelspin/bottoming; withholds changes on contradicted fields, surfaces `diagnosis_contradictions`); **rollback advisory** (`rollback_from_lineage` → `rollback` surface when the last scored setup tested worse). **DB_VERSION 14→15** (`strategy/_setup_constants.py`); the migration is additive + idempotent (new table only, `CREATE IF NOT EXISTS`), touching no existing table.

**Tests:** `tests/test_setup_lineage.py` (20) + `test_session_db` (v15) + 7 stale "no-new-migration" guards (Groups 55–61, read-only sprints) updated to allow v15 / guard v16. Full suite (halves + UI files individual): **~7377 passed, 0 failed.** Safety spine intact. **Remaining Phase 1 (UI-only, low value):** explicit better/worse combo + rollback button in Practice Review (direction is already derived + feeds lineage).

## Repository / Build Status (2026-07-14 — Setup Brain: Engineer Evolution, phase 4 — per-corner authoring)

**Branch `group64-setup-authoring-discipline-intelligence` (continued) — committed + pushed; PR #44.** Adds resolution beyond corner density: the setup now shapes to the track's ACTUAL per-corner character.

**NEW `strategy/corner_profile.py` (pure):** `load_reviewed_segments(loc, layout)` merges the track's reviewed per-corner segment files (read-only; corner entry/apex/exit windows + direction, plus car-behaviour zones — kerb/bump, braking, traction, limiter). `build_corner_profile` derives the corner character; `corner_profile_intents` maps it to engineering intents. **Honesty:** the shipped per-corner data has NO speed/radius, so the tight-vs-open window-width ratio is retained for reporting only — authoring fires only on the RELIABLE signals: kerb load (→ ride-height margin + front compliance), braking zones (→ front support under braking), traction zones / traction-limited exits (→ rear downforce for drive-off). Confidence capped at MEDIUM (proxy); per-corner note surfaced in `engineering_reasoning`. Wired into the engineering layer (supersedes the coarse corner-density mechanical-grip heuristic when present) via both authoring entry points. **Real result:** Fuji's 24 detected kerb/bump zones now lift ride height (63→66) and soften the front spring for compliance.

**Tests:** NEW `tests/test_corner_profile.py` (8). Full suite (halves + UI files individual): **~7400 passed, 32 skipped, 0 failed.** Safety spine intact; reviewed-segments loader is read-only and defensive (files may be absent); no schema migration. This completes the four staged engineer-evolution items.

## Repository / Build Status (2026-07-14 — Setup Brain: Engineer Evolution, phase 3 — evidence-scaled driver fit)

**Branch `group64-setup-authoring-discipline-intelligence` (continued) — committed + pushed; part of PR #44.** Closes audit Gap 3 (thin driver layer): the driver profile applied fixed one-click nudges (two self-cancelling), scaled to nothing, and touched no value on the telemetry path.

**NEW `strategy/driver_fit.py` (pure):** each driver preference is a DIRECTION + a COMFORT THRESHOLD (fraction of the car's legal range). `derive_driver_fit(profile, current_setup, ranges)` fires a move ONLY when the current value actively violates the preference, scaled by how far past the threshold it sits × strength × range — and is ZERO once the field is on the driver's side ("don't fix what fits"). Opposing preferences net-resolve into a comfort band (rotation-without-snap vs consistency on the braking diff). Range-aware (one "click" = the same fraction of a 1–10 and a 1–40 bar). Wired into: (a) baseline + discipline authoring (against the neutral seed; **proven-history-seeded fields excluded** so it never double-counts a validated value), and (b) the **telemetry path** — composed into the balance set for fields the solver neither moved nor deferred (`BalanceSolution.deferred_fields` respected), plus an advisory `driver_fit_reasoning` surface shown on every analyse (the audit's "zero on the telemetry path" is closed). UI: `_driver_fit_html` panel.

**Tests:** NEW `tests/test_driver_fit.py` (9) — evidence-scaling, already-fits-no-move, range-awareness, band resolution, honesty, both-path integration. Full suite (halves; some UI files individual due to the documented PyQt teardown segfault): **~7392 passed, 32 skipped, 0 failed.** Safety spine intact; driver-fit moves flow through the same validator + Apply gate; no schema migration.

## Repository / Build Status (2026-07-14 — Setup Brain: Engineer Evolution, phase 2 — balance solver)

**Branch `group64-setup-authoring-discipline-intelligence` (continued) — committed locally, NOT pushed.** Closes audit Gap 6 ("defer instead of engineer"): when several conflicting complaints (entry understeer + mid push + rear loose on power + rear locks under braking) previously collapsed to one dominant, emptied the proposed set via per-field contraindications, and returned `evidence_required` with NO setup — the app now **authors a coherent setup**.

**NEW `strategy/setup_balance_solver.py` (pure):** `solve_balance(diagnosis, current_setup, ranges)` reasons over the whole car at once and produces a coordinated compromise — **free the front** (soften front bar, front toe-out, more front aero), **plant the rear** (more rear aero + toe-in, softer rear bar), **brake forward** — with per-move reasons, an explicit understeer-vs-power-oversteer trade-off note, and a test protocol. **Safety by construction:** brake bias only moves forward under instability (never rearward); LSD acceleration lock is never increased when the rear is loose (left to a test); ambiguous LSD braking left to a test; every move one conservative step, range-clamped. The moves flow through the SAME `validate_setup_engineering_structured` funnel + Apply gate. NEW apply-eligible status `balance_recommendation` (added to `APPROVED_STATUSES`), honestly framed as a balance change to TEST. Wired into `build_combined_setup_response` (fires only when ≥2 confirmed complaints would otherwise defer). UI: status banner + a grouped `balance_solution` panel (entry / exit / braking + trade-off + test plan).

**Proof:** the exact Group 63 UAT scenario that returned `evidence_required` / no changes now returns `balance_recommendation` with a validated 6-field coordinated setup (arb_front 6→5, toe_front 0→-0.03, aero_rear 590→620, toe_rear 0.05→0.1, arb_rear 5→4, brake_bias 0→-1); LSD accel correctly NOT touched. **Tests:** NEW `tests/test_balance_solver.py` (13). Updated 2 Group 63 UAT tests (`test_authors_coordinated_balance_not_deferral`, audit-only) + `APPROVED_STATUSES` governance test to the new behavior. Full suite in halves: **~7372 passed, 32 skipped, 0 failed.** Safety spine intact; no schema migration. **Staged:** deeper evidence-scaled driver influence; corner-type (radius/speed) authoring from the per-corner data.

## Repository / Build Status (2026-07-13 — Setup Brain: Engineer Evolution, phase 1)

**Branch `group64-setup-authoring-discipline-intelligence` (continued) — committed locally, NOT pushed.** After the Group 64 safety work, a reframing brief asked the Setup Brain to *reason like a race engineer*, not a validator. A four-thread architectural audit (`docs/AUDIT_setup_brain_engineer_evolution.md`) proved: **no vehicle model** (power/weight exist for 579 cars but only feed AI-prompt text), **one track knob** (all rich geometry collapses to a 3-value `aero_bias`; gearing-to-straight claimed in docstrings but absent; elevation computed and read by nothing), **thin driver layer** (8 fixed nudges, 2 self-cancel, zero on the telemetry path), **no objective functions** (Base/Quali/Race = fixed `_SESSION_BIAS_TABLE`), **no coupling** (every field independent; arbitration only annotates), and **defer-instead-of-engineer** on multi-complaint feedback.

**Phase-1 implementation — NEW `strategy/setup_engineering.py` (pure):** a `VehicleModel` built from real `car_specs.json` (drivetrain→engine location, power/weight→power-to-weight, balance tendency) + `derive_engineering_intents(vehicle, track, objective, driver)` producing **coupled directional intents** (field, direction, bounded magnitude, reason, evidence, `couples_with`) + a `final_drive_lean`. It reasons from first principles: RR car → front bite + rear stability + brake-forward; straight-heavy track → longer gearing + high-speed support; corner-dense → shorter gearing + mechanical grip; elevation → ride-height margin (uses the previously-dead field); race protects the RR rear tyre, quali sharpens. Intents flow through the SAME neutral-seed→clamp→validate pipeline via new `build_baseline_setup(engineering_bias=…, final_drive_lean=…)` params (default None/0 → **byte-identical** legacy output) and are wired into `build_baseline_setup_response` + `setup_authoring.author_full_field_plan`. Response gains an `engineering_reasoning` surface (vehicle model + per-intent why + coupling). **Result: Fuji vs a twisty circuit now differ across gearing, springs, ARB, and ride height — not just aero.**

**Tests:** NEW `tests/test_engineering_reasoning.py` (12). Full suite in halves: **7360 passed, 32 skipped, 0 failed.** Safety spine intact: deterministic, AI-audit-only, no auto-Apply, range/legality clamps unchanged, no schema migration. **Staged (not yet built):** the multi-complaint balance-solver (Gap 6 — author a coordinated compromise instead of `evidence_required`) and deeper evidence-scaled driver influence.

## Repository / Build Status (2026-07-13 — Group 64: Setup-authoring architecture & discipline intelligence)

**Branch `group64-setup-authoring-discipline-intelligence` from `master` @ `9d2b276` — committed locally, NOT pushed.** The manual UAT after Group 63 still produced near-identical Base/Qualifying/Race setups, a lone `ARB Front 6→5` labelled "approved", a contradictory bottoming state (`required` header vs `NORMAL_OR_EXPECTED` panel), a weak `gear_too_short_spin`, and proven values that never reached authoring. Group 63 had repaired the *incremental* evidence pipeline; Group 64 adds the missing **complete, objective-specific, full-field authoring architecture** and closes the render/status-layer gaps. Root-cause report: `docs/AUDIT_setup_brain_group64.md`. Deterministic/rule-first/AI-audit-only preserved; **no schema migration** (`RULE_ENGINE_VERSION` unchanged, `user_version` 14).

- **NEW `strategy/setup_authoring.py`** — canonical `SetupObjective` (BASE/QUALIFYING/RACE), immutable `SetupAuthoringContext`, documented `EVIDENCE_PRECEDENCE`, `FieldDisposition` (11 states), `author_full_field_plan` (composes the deterministic generator, assigns a disposition to EVERY adjustable field, attaches objective-specific per-field justification) + `author_discipline_setups`.
- **RC1 discipline** — baseline response gains a `discipline_field_plan` surface authoring Base/Quali/Race as separate full-field setups from ONE context (per-field base/quali/race values + `differing_fields` + dispositions). Base/Quali/Race genuinely diverge (≥9 fields for the RSR).
- **RC2 proven history → authoring** — `build_baseline_seed_overrides` now lifts the LSD triplet (geometry tier ≤2, LSD tier ≤3 as a cross-track starting window), marked `PROVEN_HISTORY_SEED`.
- **RC3 bottoming** — new `bottoming_display_state` reconciles count band + consequence impact into ONE canonical state; UI header reads it (no more `required`+`normal`).
- **RC4 wheelspin** — `_classify_wheelspin_subtype` requires location-trustworthy, non-contradicted evidence before `gear_too_short_spin`; else `unknown` (→ test) / `conflicting_evidence`.
- **RC5 completeness** — `RECO_*` state vocabulary + `assess_recommendation_completeness`: a plan is complete only when every active confirmed problem (incl. telemetry wheelspin + secondaries) is addressed or covered by a targeted test, else downgraded to `partial_recommendation`; `wheelspin` now arms the finaliser gate; UI shows a completeness verdict + untreated list.

**Tests:** NEW `tests/test_group64_setup_authoring.py` (13) + `tests/test_group64_uat_integration.py` (12); updated `test_group39` (wheelspin gate) + `test_followups_history_lift_candidates` (LSD lift). **Full suite run in halves (documented PyQt full-run segfault): 4755 + 2592 = 7347 passed, 32 skipped, 0 failed.** Runtime files git-verified untouched (data/setup_history.json + track models were modified by the manual UAT before this work and are intentionally NOT staged).

## Repository / Build Status (2026-07-13 — Group 63: Setup Brain UAT-2 remediation)

**Branch `group63-setup-brain-race-engineer-uat2` from `master` @ `b951e06` — committed locally, NOT pushed.** A second Setup Brain UAT (Porsche 911 RSR race setup) exposed connected defects that survived the 16-phase Race-Engineer remediation: a wrong `Final Drive 4.25→4.20` (lengthening) for an unused sixth, bottoming marked dominant/required on event count with no impact, and the LSD triplet + camber never meaningfully evaluated. Root-cause report: `docs/AUDIT_setup_brain_uat2_group63.md`. The repair fixes the **evidence pipeline** (deterministic/rule-first/AI-audit-only preserved; no schema migration; `RULE_ENGINE_VERSION` unchanged; `user_version` stays 14):
- **Feedback parsing** — new `lsd_feel_wrong` / `rear_loose_under_braking` / `gearing_too_long` flags + braking-vs-exit phase disambiguation (`strategy/setup_diagnosis.py`).
- **Gearbox** — new pure `strategy/gearbox_evidence.py` (final-drive directional invariant `4.25→4.20=LONGER`; five-state `TOO_SHORT/APPROPRIATE/TOO_LONG/UNKNOWN/CONFLICTING`); `_classify_gearing` uses the real gear count, treats a 0 top-speed target as UNKNOWN, gates the straight-specific claim on location confidence, and a driver "unused sixth" report → `conflicting_evidence` (preserve). Wrong final-drive rejected at diagnosis AND by the validator.
- **Bottoming** — `_classify_bottoming_impact` grades by demonstrated consequence (5 classes); count-only "required" → UNKNOWN + demoted; handling complaints (incl. `mid_corner_understeer`) can now be dominant.
- **LSD triplet** — new pure `strategy/lsd_reasoning.py` + `lsd_initial` resolvers; all three fields evaluated vs the proven same-car prior with executable controlled tests.
- **Coherence** — `dominant_required` generalised beyond bottoming; a bare `final_drive` no longer "addresses" wheelspin; UI gains LSD-triplet / bottoming-impact / targeted-test panels.

**Tests:** `tests/test_group63_setup_brain_uat2.py` (40, incl. the full Porsche RSR integration fixture); ~2791 setup-brain/advisor + 13 UI-smoke green; runtime files git-verified untouched. Pre-existing unrelated failure: `test_home_dashboard_promotion::test_no_new_raw_setcurrentindex` (dashboard.py byte-identical to master).

## Repository / Build Status (2026-07-11 — Group 62 Delivered + Pre-UAT Audit & Defect Resolution)

**Current tip: `master` @ `0b73d0d` (PR #41, Group 62).** Beyond the Group 61 entry below, master now also carries **Group 62 — No-ABS Awareness** (per-event "ABS allowed" toggle into setup/strategy/coaching) and **UI Passes 1–6** (NGR Enterprise theme foundation, action-hierarchy, Track Modelling trust badge, driver-facing copy, History empty-state, button hierarchy).

**SCHEMA: SQLite `user_version` is now `14`** (was 13). Group 62 added `_migrate_v14` → additive `events.abs INTEGER NOT NULL DEFAULT 1` (idempotent duplicate-column guard; DEFAULT 1 = ABS allowed, behaviour-preserving). The `DB_VERSION` constant (`strategy/_setup_constants.py`) is bumped to `14` to match. **`RULE_ENGINE_VERSION` stays `46.0`.** (NOTE: the Group 55–61 entries below say "`user_version` 13" — that was correct at the time; the current value is 14.)

**Pre-UAT audit (2026-07-11): CONDITIONAL GO.** Full read-only audit confirmed the Engineer Brain safety spine intact (AI audit-only/can't author, Apply gate keys on validated result, legacy AI-build disabled+hidden, live replan read-only/advisory, road-distance fallback never HIGH, stabiliser display-only, learning bounded ±1 + scoped, SessionDB reads read-only) and that the audit mutated no runtime files. Defects then resolved:
- **A1 (fixed):** docs + `DB_VERSION` corrected to Group 62 / v14 (this entry).
- **A5 (fixed):** `_car_id_build` now set in the live Analyse flow so Apply→session learning linkage fires (`ui/setup_builder_ui.py`).
- **A6 (fixed):** advisor event-context + analysed-car scope re-pushed on Garage "Select for Event" (`ui/dashboard.py`).
- **B3 (fixed):** tyre-wear "sample" in the strategy explanation now labelled "(proxy, derived from lap-time drift)".
- **B5 (fixed):** `datetime.utcnow()` → `datetime.now(timezone.utc)` (`strategy/_rec_parser.py`).
- **Test suite greened:** the 38 benign failures (schema-version assertions after the v13→v14 bump, frozen-allowlist governance guards for the new read-only `ui/track_modelling_ui.py::_tm_restore_last_track` consumer, and stale pre-Group-42 AI-authoring tests in `test_group31`) were updated to the current invariants / skipped as obsolete. No production regression was involved.
- **Accepted / documented (no code change, by decision):** **A3** legacy `RaceStrategyEngine` voice pit calls ("box this lap") kept as intended advisory radio (user-activated, cannot execute a pit in GT7); **A4** the deterministic safe-fallback is left fail-safe ("validation failed, no changes" on a safety-blocked analyse) and deferred for a proper post-UAT fix; **B2** the planner `fuel_burn_per_lap` single-sample estimate lifting strategy confidence off INSUFFICIENT is a known LOW limitation on the non-SessionDB bridge path.

## Repository / Build Status (2026-07-08 — Group 61 Delivered)

**Group 61 — Raw Live Packet Road Distance Semantics Capture & Stateful Live Progress Stabiliser Wiring** DELIVERED (2026-07-08). Branch `group61-raw-live-road-distance-semantics-stabiliser-wiring` from clean `master` (`1e86ef7`, Group 60 merged). Read-only, advisory-only. Adds a raw live-packet road_distance capture workflow (to finally settle the field's LIVE semantics via a manual ≥3-lap UAT), a `NON_DISTANCE_LIKE` verdict (the shipped Fuji/Daytona captures now classify as non-distance-like), and wires the Group 60 stabiliser into a stateful, **DISPLAY-ONLY** live path. NEW pure `data/live_road_distance_capture.py` (Qt/DB/AI/file-write-free; accumulates raw samples, rejects NaN/inf/None, keeps+flags negatives, emits laps[] for the Group 60 analyser). `LiveProgressStabiliserState` holder (auto-resets on track/layout/car change; never changes value, never inflates, no pit contact). `build_live_replan_snapshot` gained `stabiliser_state` → stores `stabilised_confidence`/`stabiliser_notes`/`stabiliser_jumped` computed AFTER pit corroboration, so **pit path is byte-for-byte unchanged**; no-state callers identical. Dashboard holds the state + an OFF-by-default read-only raw capture (`start_/stop_/report` methods; single guarded feed line in `_poll_ui_queue`). UAT: `run_raw_live_capture_uat`, `build_raw_live_capture_fixture`, `save_raw_capture_to_path` (explicit path only). **No new live semantics were confirmed** (real in-game raw capture is a manual step); production fallback behaviour UNCHANGED; promotion still gated on a CONFIRMED raw capture. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **43 new Group 61 tests pass**; regression green (Group 55–61 389; Group 48/49/53/54 + telemetry/pit + reference/track 992; dashboard smoke 13). Runtime files git-verified untouched. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 60 Delivered)

**Group 60 — Real Capture Road Distance Semantics UAT & Correctness-Preserving Live Progress Stabilisation** DELIVERED (2026-07-07). Branch `group60-road-distance-semantics-uat-progress-stabilisation` from clean `master` (`2a94780`, Group 59 merged). Read-only, advisory-only. **HONEST REAL-CAPTURE FINDING:** running the Group 59 validator over the shipped Fuji + Daytona calibration captures does NOT confirm cumulative `road_distance` semantics (Fuji → INSUFFICIENT_EVIDENCE, Daytona → INCONSISTENT) — the captured field spans only ~117 m (Fuji) / ~430 m (Daytona) per lap, far below lap length, so it does not measure cumulative lap distance in this post-processed calibration data. The report says so honestly; **production live fallback behaviour is UNCHANGED** (it already caps confidence + discloses the assumption). NEW pure `data/road_distance_capture_analysis.py` (extract lap-boundary observations from captures → Group 59 validator + span-vs-lap red flag + human-readable report; read-only calibration loader). NEW pure `data/live_progress_stabiliser.py`: `nearest_station_stabilised` ALWAYS returns the global nearest (local continuity window never overrides — safe on crossings/parallel sections); `stabilise_progress` never changes the position value and only DOWNGRADES confidence on implausible jumps (lap-wrap aware), never inflates, never HIGH-ifies fallback, touches no pit state. Stabiliser implemented + tested but NOT force-wired (snapshot builder is stateless; wiring deferred). `run_real_capture_road_distance_uat(kind)` UAT helper (real fuji/daytona + synthetic scenarios through one path). No confirmed semantics → no automatic behaviour promotion (Goal 2). **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). No change to live replan/resolver/fallback/tracker/dashboard. **55 new Group 60 tests pass**; regression green (Group 55–60 346; Group 48/49/53/54 + telemetry/pit + reference/track 960; dashboard smoke 13). Runtime files git-verified untouched. Still needs: a RAW-live-packet road_distance capture UAT to settle the field's true live semantics. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 59 Delivered)

**Group 59 — Approved Reference Path Asset Expansion & Road Distance Semantics Validation** DELIVERED (2026-07-07). Branch `group59-reference-path-assets-road-distance-validation` from clean `master` (`f8dd70c`, Group 58 merged). Read-only, advisory-only. **No new production reference-path assets were added** — the repo already ships two trustworthy calibration-sourced approved paths (Fuji Full Course + Daytona Road Course, 200 stations each, Porsche RSR, confidence 1.0), both already loading/registering/resolving trusted lap length; Group 59 verified this and hardened the foundation rather than fabricating any. NEW pure `data/road_distance_semantics.py` (Qt/DB/AI/file-write-free, never raises): validates GT7 `road_distance` zero-point semantics from lap-boundary samples → CUMULATIVE_CONFIRMED / PER_LAP_RESET_CONFIRMED / INCONSISTENT / INSUFFICIENT_EVIDENCE / UNKNOWN; rejects NaN/inf, flags negative deltas, compares per-lap delta to a trusted lap length (5% tol), needs ≥2 laps, never assumes the answer. `reference_path_loader.validate_reference_path_candidate` gives clear errors for malformed/incomplete candidate assets. Live render adds an HONEST disclosure that the fallback ASSUMES cumulative semantics ("zero-point validation: insufficient evidence") with capped confidence — it does NOT change live behaviour automatically. `run_road_distance_semantics_uat` UAT helper. Fallback still never HIGH, never lifts pit confidence, never creates a pit event; approved path still wins. Local nearest-station search window (§5) deferred to Group 60 (strict correctness-preservation is non-trivial). **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). No `telemetry/state.py` or `ui/dashboard.py` change needed. **58 new Group 59 tests pass**; regression green (Group 53–59 424; Group 48/49 + telemetry/pit + reference/track 973; dashboard smoke 13). Runtime files git-verified untouched. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 58 Delivered)

**Group 58 — Road Distance Fallback & Reference Path Asset Expansion Foundation** DELIVERED (2026-07-07). Branch `group58-road-distance-fallback-assets` from clean `master` (`0d09217`, Group 57 merged). Read-only, advisory-only: adds a **lower-confidence fallback** for live track progress when no approved reference path exists — estimating normalised progress from GT7 cumulative `road_distance` + a TRUSTED lap length — plus a reference-path asset registry foundation. NEW pure `data/live_track_progress_fallback.py` (Qt/DB/AI/file-write-free; **confidence NEVER HIGH** — MEDIUM for accurate in-bounds per-lap distance, LOW when wrapped/cumulative-only, UNKNOWN on invalid/mismatch). Precedence: usable MEDIUM/HIGH approved map match wins → else road-distance fallback → else honest LOW/UNKNOWN; **fallback never overrides a usable map match and never lifts pit confidence** (excluded from pit-lane corroboration by source). Tracker gains a per-lap `_road_distance_lap_start` reference + read-only `live_road_distance`/`live_lap_distance` properties. Registry helpers `list_available_reference_paths`/`reference_path_asset_summary`/`resolve_trusted_lap_length` (never invents a length). Render labels fallback progress as approximate/lower-confidence. Fallback creates no pit event, mutates no pit count. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **44 new Group 58 tests pass**; regression green (Group 53–58 strategy 366; telemetry/pit + Group 48/49 + track 823; dashboard smoke 13). Runtime files untouched. Caveat: only Fuji + Daytona ship approved reference paths; other tracks use the fallback or report unavailable. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 57 Delivered)

**Group 57 — Approved Reference Path Assets & Live Progress Activation** DELIVERED (2026-07-07). Branch `group57-reference-path-assets-progress-activation` from clean `master` (`4014857`, Group 56 merged). Read-only, advisory-only: discovers + loads approved/reference-path assets so Group 56 live track progress actually activates. **The repo already ships a real calibration-sourced Fuji Full Course reference path** (200 stations, Porsche RSR, confidence 1.0) — Fuji progress now genuinely resolves HIGH near the path. NEW pure `data/reference_path_loader.py` (Qt/DB/AI-free, read-only, never raises; parses the explicit `reference_path_v1` shape + existing Group 17 calibration shape; discovers by scanning `data/track_models/`; validates identity; converts to Group 56 `TrackPathStation`). Optional backward-compatible `reference_path` track-library manifest block + `load_track_reference_path`. Dashboard `_resolve_live_track_progress_context()` rewritten to use canonical `EventContext.track_location_id`/`layout_id` (Group 56 used the display name and missed the file) + surface provenance. Render adds `reference path: loaded (...)` Found line + honest Missing/Warning routing. **Progress NEVER creates a pit event; LOW/UNKNOWN/mismatched progress never lifts pit confidence.** Reuses `ReferencePath`/`build_track_path_stations` read-only — no calibration run, no mutation (real Fuji file byte-identical after load). Road-distance fallback (§6) deferred to Group 58. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **52 new Group 57 tests pass**; regression green (Group 54–57 + track-lib + map/station/calibration + telemetry 1123; Group 48–53 strategy 453; dashboard smoke 13). See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `docs/TRACK_LIBRARY_SCHEMA.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 56 Delivered)

**Group 56 — Live Position → Track Progress Resolver** DELIVERED (2026-07-07). Branch `group56-live-position-track-progress` from clean `master` (`cc4697f`, Group 55 merged). Read-only, advisory-only: converts live GT7 world position (X/Y/Z) into a normalised lap progress (0.0–1.0) by matching to the nearest station on an approved/reference track path, **unlocking real Group 55 pit-lane corroboration during live telemetry**. NEW pure `data/live_track_progress.py` (Qt/DB/AI/file-write-free; thresholds mirror `track_map_matching`: HIGH ≤5 m / MEDIUM ≤20 m / LOW ≤60 m / else UNKNOWN); read-only tracker `live_world_position` property; `resolve_live_progress_evidence` + `attach_track_progress` in the live adapter; `live_position`/`reference_stations` threaded through the replan runner + render. **MEDIUM/HIGH progress feeds Group 55 pit-lane corroboration; LOW/UNKNOWN never lifts pit confidence.** Progress NEVER creates a pit event (Group 55 owns corroboration, Group 54 owns pit events). Overall live-replan confidence unchanged (still ≤ MEDIUM). Reuses existing geometry (`ReferencePath`, `import_reference_path_json`) read-only — no calibration run, no track-model mutation. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **64 new Group 56 tests pass**; regression green (Group 48–55 strategy + telemetry + track map/station/calibration 996; Group 48–53 strategy 453; dashboard smoke 13). Caveat: no repo currently ships an approved reference-path file, so live progress typically resolves as "approved reference path unavailable" until one exists (exercised via test-only `fuji_reference_path()` fixture). See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 55 Delivered)

**Group 55 — Track-Specific Pit-Lane Mapping & Pit Confidence Upgrade** DELIVERED (2026-07-07). Branch `group55-track-pit-lane-mapping` from clean `master` (`7ff7433`, Group 54 merged). Read-only, advisory-only, **evidence-quality only**: if live lap-progress falls inside a track's *known* pit-lane corridor, a detected pit event is corroborated and its confidence can lift (refuel pit MEDIUM→HIGH; speed-only LOW→MEDIUM at most; contradictions warn; low-confidence maps cap at MEDIUM). **Pit-lane mapping corroborates but never CREATES a pit event** — pit count + tyre age still come solely from the Group 54 tracker. Missing mapping degrades to exact Group 54 behaviour. NEW pure `data/pit_lane_resolver.py`; optional backward-compatible `pit_lane` block on the track-library schema (`load_track_pit_lane`); read-only tracker `in_pit` property; corroboration threaded through the Group 53/54 live adapter + replan render. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Overall live-replan confidence still capped ≤ MEDIUM (never HIGH from proxy tyre/pace). **73 new Group 55 tests pass**; regression green (Group 48–54 strategy 754, telemetry state/tracker/pit 564, track-library 92, dashboard smoke 13). Caveat: GT7 broadcasts no normalised lap-progress yet, so the live corroboration path typically reports "progress unavailable" and falls back to Group 54; wiring a real progress source is Group 56+. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `docs/TRACK_LIBRARY_SCHEMA.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-05 — Group 40 Delivered)

**Group 40 — Setup Diagnosis Hardening** DELIVERED (2026-07-05). Pure Python backend sprint on top of Group 39. Key additions: `bottoming_confidence` (band/subtype/confidence), `driver_feel_traction_status`, `aero_rear_healthy` (0.80×hi fraction-of-max threshold). New validation rules: `rh_increment_exceeds_confidence`, `rh_rake_risk`, `lsd_large_change_gated`, `lsd_blocked_driver_feel`. Hardened `lsd_reversal_without_evidence` (delta >= 5 guard). Deterministic fallback (`_build_deterministic_fallback`) for post-retry engineering failures. **Full suite: 5359 pass / 6 skip / 8 fail** (8 pre-existing frozen-allowlist failures, unchanged). Branch: `ofr2-quali-race-disciplines`.

## Repository / Build Status (2026-07-02)

- **Full test suite:** 3984 pass / 6 skip / 0 fail (6 skips require a Qt display).
- **Git:** the two shipped feature branches `feature/setup-diagnosis-engine` and `feature/strategy-outcome-comparison` were combined on `integration/setup-brain-strategy-overhaul` (clean, no conflicts) and **merged to `master`** (merge commit `7254835`, pushed to `origin/master`). Merged after automated tests passed; **runtime UAT still pending**. Remote: **https://github.com/leonpaczynski-netizen/ngr_pitcrew**.
- **Secrets:** `api_key.txt` and `config.json` are gitignored — not tracked, not pushed.
- **Latest work (Setup Brain + Strategy Outcome — documented in MASTER_TESTING_REGISTER.md):**
  - **Setup Brain:** app-side deterministic setup diagnosis BEFORE the AI call (`strategy/setup_diagnosis.py`), driver tuning-model + hard-constraints injected at the top of every setup prompt, post-AI engineering validation with regenerate-once-then-surface, low-confidence track-model guard, structured liked/hated setup-history learning. Bug fixes: springs shown in **Hz** (was N/mm); timed race renders as **"N minutes, Timed Race"** (was "1 laps, Lap Race").
  - **Strategy Outcome:** deterministic total-race-time comparison (`strategy/outcome.py`) — strategies ranked head-to-head with delta-vs-fastest, confidence, and previously-hidden tyre/fuel/undercut/AI-confidence risk fields surfaced on the cards; refuel time uses the actual refuel rate; "pit loss" relabelled "pit time".
- **Detailed session notes** for Groups 17P–25 live in `docs/CURRENT_CLAUDE_HANDOFF.md`.

### Deferred / carried forward (next remediation group)
- **Setup history key omits track layout:** `config_id` hashes track-name+car+length, not `layout_id`. Two layouts of the same track can share history (config_id re-hash risk if changed — deferred to avoid regressing Event Planner/history/strategy).
- **From-scratch "Build Setup with AI":** receives the driver tuning-model + hard-constraints prompt text but NOT the post-AI engineering-validation/regenerate loop (no telemetry exists at build-from-scratch time). Only the "Analyse & Get Setup Fix" flow is fully validated.
- **Strategy finishing-position prediction:** requires rival/opponent telemetry not present in the pipeline today. Remains deferred as genuinely new scope.

## Phase 1 Fix Status (2026-06-21)

| Defect | Title | Status |
|--------|-------|--------|
| DEF-P1-001 | Session opens on first lap completion | Fixed — Awaiting Retest |
| DEF-P1-002 | Outlaps silently discarded after pit exit | Fixed — Awaiting Retest |
| DEF-P2-001 | Practice mode laps recorded as race | Fixed — Awaiting Retest |
| DEF-P2-009 | Fuel burn calculated in three locations | Fixed — Awaiting Retest |
| DEF-P4-003 | Fuel formula uses additive lap safety | Fixed — Awaiting Retest |

All 54 unit tests pass (5 skipped — require Qt display). Batch A complete (2026-06-21).

## Current Priority
Fix foundation issues in this order:

1. Database and persistence
2. Single source of truth
3. Telemetry persistence
4. AI context and debug logging
5. Session/lap integrity
6. Remove superseded UI/features

## Architecture Rules

Event Planner owns:
- Event name
- Track
- Layout
- Race type
- Race length
- Fuel multiplier
- Refuel rate
- Tyre wear multiplier
- BoP status
- Tuning allowed status
- Available tyres
- Required tyres
- Weather/rain risk
- Damage settings

Garage owns:
- Cars
- Active car
- Car setup history
- Car session history

Setup Builder consumes:
- Active Event
- Active Car
- Driver profile
- Event race conditions
- Event tuning permissions

Strategy Builder consumes:
- Active Event
- Active Car
- Selected setup
- Practice telemetry
- Driver feedback

Practice Review consumes:
- Loaded session from History

History owns:
- Session loading
- Session filtering
- Previous session access

Live Race Engineer consumes:
- Active Event
- Selected strategy if manually loaded
- Live telemetry
- Active tyre compound

Settings owns:
- AI settings
- Voice settings
- PTT settings
- Telemetry connection settings
- Driver profile

## Superseded Requirements

Remove or do not rebuild:
- Dashboard tab unless redesigned later
- Session loader in Practice Review
- Car selector in Event Planner
- Car selector in Setup Builder
- Track selector in Setup Builder
- Race detail fields in Strategy Builder
- Fuel burn input in Strategy Builder
- Tyres in BoP tuning permissions

## Current Critical Defects

### P1-001 Telemetry Not Persisted
Per-frame telemetry is captured in memory but discarded after each lap.

Required:
Create TelemetrySample table and persist telemetry samples linked to session/lap.

### P1-002 Events and Setups Stored In config.json
Events and setups live in config.json with no relational integrity.

Required:
Move event, car, setup, session, strategy data into SQLite.

### P1-003 Missing DB Tables
Missing required tables:
- UserProfile
- EventProfile
- Car
- TelemetrySample

Required:
Create schema and migrations.

### P1-004 AI Context Incomplete
Driver feedback and previous AI recommendations are not passed into AI prompts.

Required:
AI calls must include driver feedback, previous recommendations, tuning permissions, event context, car, setup, and telemetry summary.

### P1-005 Session/Lap Integrity
Practice laps missing, duplicate lap risk exists, and practice mode recorded as race laps.

Required:
Fix lap saving, duplicate prevention, session type mapping, and history loading.

## Current High Priority Defects

- PTT button and voice status must be on Live Race Engineer, not only Settings.
- Fuel multiplier must not be treated as litres per lap.
- Pit window must recalculate dynamically.
- Car data exists in multiple locations and must be unified.
- Setup data exists in multiple locations and must be unified.
- Driver feedback form belongs in Practice Review, not Setup Builder.
- History loading must reliably load recent sessions.
- Session summary must recalculate after History loads a session.

## AI Rules

Every AI call must log to Debug and AIInteraction table:

- Feature name
- Timestamp
- Prompt
- Structured payload
- Response
- Model
- Token usage
- Estimated cost
- Duration
- Errors

AI must distinguish:
- Measured data
- Calculated data
- Inferred data
- Driver feedback

AI must not recommend locked setup changes.

If BoP is enabled and aero is not allowed, AI must not recommend aero changes.

## Tyre Rules

Available tyres and required tyres are selected in Event Planner.

Tyres are always changeable, including under BoP.

Tyres are not part of tuning permissions.

Required tyres must be a subset of available tyres.

Sports tyres must be supported everywhere Racing tyres are supported.

## Setup Builder Rules

Setup Builder must show as read-only:

- Active car
- Track
- Layout
- Race conditions
- BoP status
- Tuning permissions

Editable fields depend on Event tuning permissions.

Brake balance increments by 1.

Setup type must be:
- Race Setup
- Qualifying Setup

## Live Race Engineer Rules

Live Race Engineer is the first tab.

On app startup:
- No strategy is loaded by default.

PTT must work in:
- Practice
- Qualifying
- Race

PTT behaviour is already correct:
- Tap once
- Radio click
- Record approx. 2 seconds
- Radio click
- Process speech

Only improve immersion, do not change behaviour.

## Telemetry Priorities

Telemetry must support:

- Rev limiter events
- Gear usage
- Max speed
- World XYZ location
- Road surface if available
- Tyre radius if available
- Raw throttle
- Raw brake
- Brake lock detection
- Wheel spin detection
- Grip loss confidence
- Location-based issue grouping

## Gearbox Engineering Rules

AI gearbox advice must use telemetry evidence:

- Final gear usage on longest straight
- Rev limiter location and duration
- Max speed before braking zone
- Corner exit RPM
- Gear usage by corner
- Qualifying vs race setup type
- Slipstream risk
- Fuel saving requirements

AI must not give generic gearbox advice without telemetry context.

## Development Workflow

Claude must:

1. Read PROJECT_STATE.md.
2. Read MASTER_TESTING_REGISTER.md.
3. Never create duplicate defects.
4. Never remove defects without marking them Fixed.
5. Never add new features while P1 defects exist.
6. Update both documents after every coding task.
7. Reference defect IDs in commits and responses.

## Current Working Instruction For Claude

When working on this project:

1. Read this file first.
2. Read MASTER_TESTING_REGISTER.md second.
3. Only inspect files directly related to the active task.
4. Do not scan the whole repo unless asked.
5. Do not re-analyse architecture unless asked.
6. Provide a short plan before editing.
7. Make the smallest safe change.
8. Run relevant tests.
9. Update this file and MASTER_TESTING_REGISTER.md after changes.
10. Keep final response concise.