# GT7 VR Dashboard — Master Testing Register

> Last updated: 2026-07-20 (**Engineering Brain PROGRAM 2, Phases 45-47 — Immutable Provenance, Live Shadow Validation & Opt-In Voice (combined slice)** — deterministic offline slice on ONE branch `eng-brain-phase45-47-provenance-live-voice` (from Phase-42-44 tip `ce01383`): immutable context provenance -> replay+shadow validation -> opt-in OFFLINE voice for already-approved prompts only. Committed locally; NOT pushed / no PR / not merged; master unchanged @ `3d7c6af`; **DB v26 -> v27** (only bump; RULE_ENGINE 46.0 unchanged; `_setup_constants.py` otherwise byte-identical). **Correction A** stale `test_phase6_wiring::test_no_migration_no_new_telemetry_table` repaired (now proves the real Phase-6 invariant vs a fresh DB; PASSES at v27). **Correction B** mechanism-level context caps added. **Commands + totals:** `pytest tests/test_phase45_context_provenance.py tests/test_phase46_replay_shadow.py tests/test_phase47_voice.py tests/test_phase45_47_{golden,query_shape,safety,migration,ui}.py tests/test_phase6_wiring.py` = **76 passed**. Bumped 47 DB_VERSION==26 / user_version==26 guard assertions to 27 (intentional). **NEW suites:** `test_phase45_context_provenance.py`[10] (deterministic serialization + event_name-excluded, material-edit-changes-digest, capture persists+dedups, immutable content, semantic equivalence across DBs, **event-edit reconstruction proof** [x5 survives edit to x8; contexts not merged], legacy partial never-fabricated, missing-ref unknown, fresh DB v27, unknown-never-exact), `test_phase46_replay_shadow.py`[11] (deterministic replay + events, speed-independent semantics, injected clock, short-fits/long-defers duration budget, stop-critical immediate, shadow no-high-workload/no-stale delivery => SHADOW_READY, VOICE_ELIGIBLE needs live confirm, **shadow==direct-engine selection**, stale-gap-no-duplicate), `test_phase47_voice.py`[15] (disabled default speaks nothing, disabled/Windows port silent, exact-message delivery, below-gate no speech, stop-critical interrupts routine, routine-non-interrupt, acknowledge/repeat-once/mute-type/mute-lap, adapter-failure disables+no-crash, session-end/context-change flush, **no-strategy-command**, test-voice-blocked-during-run, **voice settings not in engineering fingerprint**), `test_phase45_47_golden.py`[5] (snapshot digest stable across instances, event-edit doesn't change old digest, shadow summary deterministic, voice queue deterministic under injected clock, replay stable), `test_phase45_47_query_shape.py`[5] (runtime+shadow write nothing, viewing persists no snapshot, **constant query count 5/50/500**, snapshot ref lookup <=2 queries no N+1), `test_phase45_47_safety.py`[7] (6 strategy modules incl. voice_delivery no forbidden imports/tokens incl. NO TTS/win32/wall-clock, Windows port imports TTS lazily only, never-raise, versions v27, snapshot capture explicit-write-only, voice modules no AI/cloud), `test_phase45_47_migration.py`[6] (fresh DB creates v27 snapshot tables, migrate from legacy v26, repeated startup idempotent, preserves existing data, transactional rollback safety, no runtime-file change), `test_phase45_47_ui.py`[5] (voice controls only [no strategy/apply], button reflects enabled, snapshot+validation cards, handlers fire, refresh creates no snapshot). **Property/metamorphic proven:** editing an event cannot alter an existing snapshot; adding unknown legacy records cannot create exact context; missing material field cannot increase confidence; shadow==voice-mode selection; changing voice settings cannot change engineering fingerprints; stale telemetry cannot produce a voice request; acknowledgement cannot change setup knowledge; voice failure cannot record an outcome; high-priority supersedes low; routine cannot bypass workload gates; expired cannot be spoken; repeated packets no unbounded duplicates; UI refresh cannot create a snapshot; only explicit workflows write snapshot refs. **Regression:** the 47 version-guard suites (Phase 10-44) pass at v27; corrected Phase-6 test green. **Manual UAT:** Stage A (provenance) + Stage B (replay shadow) EXECUTED programmatically (old snapshot survives event edit; not merged; viewing writes no snapshot; shadow SHADOW_READY, 0 high-workload/stale deliveries, no audio); **Stage C (live GT7) + Stage D (voice) NOT RUN** (headless, no telemetry/audio device). NO Golden `config_id`/Apply-gate change; no runtime/user files staged. Docs: `docs/ENGINEERING_BRAIN_PHASE{45,46,47}_*.md` + pre-phase corrections + `docs/UAT_ENGINEERING_BRAIN_PHASE45_47.md`. **Voice is a delivery channel only, never an engineering authority; no setup ultimate. Program 2 now spans Phases 12-47; Phase 48 NOT started.**)
>
> Prior update: 2026-07-20 (**Engineering Brain PROGRAM 2, Phases 42-44 — Trustworthy Assisted Runtime Activation (combined slice)** — deterministic offline READ-ONLY ADVISORY runtime slice on ONE branch `eng-brain-phase42-44-assisted-runtime-activation` (from the Phase-39-41 tip `a57d25a`): material context capture -> user-confirmed practice execution -> explicit outcome capture -> safely-gated live advisory text. Committed locally; NOT pushed / no PR / not merged; master unchanged @ `3d7c6af`; **DB stays v26** (no migration/persistence/write); RULE_ENGINE 46.0; `_setup_constants.py` byte-identical. **Phase 39-41 file-count correction:** git `--name-status` = 28 added / 28 modified / 0 deleted = **56 total** (report's 56 correct; '57' overcount). **Commands + totals:** `pytest tests/test_phase42_material_context.py tests/test_phase43_assisted_workflow.py tests/test_phase44_live_advisory.py tests/test_phase42_44_{golden,query_shape,safety,runtime,ui}.py` = **64 passed**. Qt harness combined `pytest tests/ -k \"phase18 or phase22 or phase25 or phase31 or phase36_38_ui or phase39_41_ui\"` = **298+ passed/0 failed** (drive_worker fix holds). **NEW suites:** `test_phase42_material_context.py`[12] (field trust states, unknown-neither-match-nor-difference, tyre/fuel/BoP cap only their domains, driver-technique not blocked, equivalent event, legacy visible never-discarded, unknown-can't-become-known-by-reordering, more-unknowns-never-exact, snapshot fp), `test_phase43_assisted_workflow.py`[14] (setup fingerprint mismatch blocks, unexpected field confounds, unverifiable without fp, correct=>READY_TO_RUN, preflight/stale-plan block, unconfirmed stays at confirmation, changing active setup invalidates, two-equal-sessions ambiguous not-auto-newest, wrong-compound flagged, no-outcome-until-explicit-confirm, unbound-no-outcome, invalid-run blocked), `test_phase44_live_advisory.py`[15] (applicable-only candidates, no-applicable=>nothing, context-mismatch supersedes coaching, stop-critical in high-workload, high-workload suppresses coaching, cooldown+per-lap deterministic under injected clock, stale-telemetry/stale-plan/passed-corner suppress, enough-evidence completion, strategy low-priority, one-coaching-objective, now_monotonic-not-in-fp, shuffled-candidates-stable), `test_phase42_44_golden.py`[3] (material + advisory render deterministic+ASCII, no setup values), `test_phase42_44_query_shape.py`[4] (writes-nothing, **constant query count across 5/50/500 records**, empty truthful), `test_phase42_44_safety.py`[6] (8 pure modules no forbidden imports/tokens incl. NO wall-clock/voice/AI, never-raise, no-AI/apply/voice in SessionDB entries, versions, read-only advisories), `test_phase42_44_runtime.py`[4] (DB byte-identical before/after, deterministic across restart + different monotonic clock, context change alters fp, user_version 26), `test_phase42_44_ui.py`[9] (3-card panel construct, empty/none-safe, no Apply/experiment/voice buttons, accessible names, page embed+forwarder, prior panels coexist, UI-refresh-writes-no-outcome, stale-worker ignored, off-thread via drive_worker). **Property/metamorphic proven:** unknown material context can't strengthen exact confidence; more unknown records can't make context exact; transferred evidence can't become exact by volume; changing active setup invalidates the run plan; unconfirmed session can't produce a recorded outcome; stale telemetry can't deliver a prompt; higher priority supersedes lower; repeated evaluation in cooldown produces no duplicate; a prompt past its window expires; coaching-only can't modify setup knowledge; different event id with verified-equivalent conditions stays usable; materially-different tyre/fuel can't stay exact; shuffled inputs stable; now_monotonic not in any fingerprint. **Regression:** Phase 39-41/36-38/33-35/32 suites green; no-AI + Apply-gate green (prior entries). **Manual UAT:** offscreen end-to-end executed (legacy not silently exact; wrong setup blocks READY_TO_RUN; high-workload delivers stop/none; page builds 3-card panel; DB byte-identical after viewing; user_version 26) - full live-GUI UAT with real telemetry NOT run in this headless environment. NO version-guard bumps; Golden `config_id` + Apply-gate UNCHANGED; no runtime/user files staged. Docs: `docs/ENGINEERING_BRAIN_PHASE{42,43,44}_*.md` + Phase 39-41 corrections + `docs/UAT_ENGINEERING_BRAIN_PHASE42_44.md`. **No setup ultimate; voice deferred. Program 2 now spans Phases 12-44; Phase 45 NOT started.**)
>
> Prior update: 2026-07-20 (**Engineering Brain PROGRAM 2, Phases 39-41 — Closed-Loop Engineering Development (combined slice)** — a deterministic offline READ-ONLY ADVISORY slice on ONE branch `eng-brain-phase39-41-closed-loop-development` (from the Phase-36-38 tip `2cbe077`) proving a complete engineering loop: context-safe evidence -> candidate selection -> controlled practice-run plan -> observed outcome -> reconciliation -> knowledge-update proposal -> promotion/rejection/rollback. Committed locally; NOT pushed / no PR / not merged; master unchanged @ `3d7c6af`; **DB stays v26**; RULE_ENGINE 46.0; `_setup_constants.py` byte-identical. **Pre-phase audit A-D:** A REMEDIATED (context-scoped chain, classify-before-aggregate), B REMEDIATED (regression bundle vs field), C REMEDIATED (setup independence), D RESOLVED (Qt harness test-only fix). **Commands + totals:** `pytest tests/test_phase39_context_pipeline.py tests/test_phase39_attribution.py tests/test_phase40_run_plan.py tests/test_phase41_outcomes.py tests/test_phase39_41_{golden,query_shape,safety,runtime,ui}.py` = **73 passed**. Qt harness reproduction+fix: `pytest tests/ -k \"phase16 or phase17 or phase18 or phase22 or phase23 or phase25 or phase26 or phase27 or phase28 or phase29 or phase30 or phase31\"` was 10 failed/707 passed BEFORE the fix, now **717 passed/0 failed**; full UI+runtime combined `pytest tests/ -k \"ui_construction or phase33_35_ui or phase36_38_ui or phase33_35_runtime or phase39_41_ui\"` = **203+ passed/0 failed**. **NEW suites:** `test_phase39_context_pipeline.py`[14] (pre-aggregation scoping, exact fingerprint invariant to +100 Daytona, shuffle-stable, equivalence equivalent/materially-different/incompatible/transfer, transfer-overlay separation, adding-incompatible-cannot-improve-exact), `test_phase39_attribution.py`[10] (multi-field bundle blocks + fields SUSPECT, multi-field cannot prove every field causal, single-field confirmed, reversal confirms, interaction-suspected on repeat, irrelevant-variation not independent, relevant independent, non-independent-not-driver, independent+driver=technique, production validation flags + no repair), `test_phase40_run_plan.py`[12] (selects highest-value single-field, rejects protected-good risk, deadline declines high-interaction, retired excluded, held-constant, bundle reduces confidence, validity gate has discipline+compound, quali/race objectives distinct, no-candidate collection, deadline posture, determinism, applied-setup alters fp), `test_phase41_outcomes.py`[16] (wrong compound confounded, few clean laps insufficient, candidate-not-tested invalid, faster-but-worse-race MIXED not-eligible, regression rollback, valid+repeat best-known-eligible, single provisional, quali not assumed race, invalid run no window change, coaching-only no setup knowledge, multi-field isolate, best-known+near freeze+strategy, property faster-lap-alone-never-promotes-race), `test_phase39_41_golden.py`[5] (run-plan+closed-loop render deterministic+ASCII, no apply instruction, changed observed alters fp, invalid run doesn't change proven window), `test_phase39_41_query_shape.py`[6] (evidence/run-plan/workflow write nothing, constant query count small-vs-large, exact fp present, empty truthful), `test_phase39_41_safety.py`[6] (9 pure modules no forbidden imports/tokens, never-raise-on-garbage, read-only advisories, versions, no-AI/no-apply in SessionDB entries), `test_phase39_41_runtime.py`[4] (DB byte-identical before/after, deterministic across restart + now_date-independent, context change alters fp, exact fp stable), `test_phase39_41_ui.py`[9] (3-step panel construct, empty/none-safe, no Apply/experiment buttons, accessible names, page embed+forwarder, prior panels coexist, regression->rollback in review, stale-worker ignored, off-thread via drive_worker). **Property/metamorphic proven:** adding incompatible evidence cannot improve exact confidence; a multi-field regression cannot prove every field causal; an invalid run cannot modify a proven working window; a faster lap cannot promote a Race setup; a coaching-only run cannot alter setup knowledge; transferred evidence never counts as exact independent; shuffled rows don't change canonical output; reversal evidence can alter a prior directional conclusion. **Regression:** Phase 32/33-35 + Phase 36-38 suites green; no-AI + Apply-gate suites green (see prior entries). **Manual UAT:** written guide `docs/ENGINEERING_BRAIN_PHASE39_41_MANUAL_UAT.md` provided but NOT executed in a live GUI this session. NO version-guard bumps; Golden `config_id` + Apply-gate UNCHANGED; no runtime/user files staged. Docs: `docs/ENGINEERING_BRAIN_PHASE{39,40,41}_*.md` + pre-phase-audit + manual-UAT. **No setup is ever ultimate/optimal. Program 2 now spans Phases 12-41; Phase 42 NOT started.**)
>
> Prior update: 2026-07-20 (**Engineering Brain PROGRAM 2, Phases 36-38 — Context-Safe Race-Engineer Activation (combined slice)** — a deterministic offline READ-ONLY ADVISORY activation slice on ONE branch `eng-brain-phase36-38-race-engineer-activation` (from the Phase-33-35 tip `9f64ce7`) that turns the whole Engineering Brain into ONE coordinated race-engineer team plan for the current event, in eight explicit layers. Committed locally; NOT pushed / no PR / not merged; master unchanged @ `3d7c6af`; **DB stays v26** (no migration/persistence/DB write); RULE_ENGINE 46.0; `_setup_constants.py` byte-identical. **Phase 36:** `strategy/engineering_context_scope.py` (immutable `EngineeringContextScope`; missing context explicit via `_UNKNOWN` sentinel; `context_fingerprint` over SEMANTIC identity only — different driver/car/track/layout/discipline never collide; `relate_context`, EXACT requires the FULL identity) + `strategy/contextual_knowledge_activation.py` (+render): classify every record vs the scope into EXACT_CONTEXT / EXPLICITLY_TRANSFERABLE / REFERENCE_ONLY / EXCLUDED / UNVERIFIABLE with a reason; transfer ONLY via the canonical Phase-23 `evaluate_transfer` (mapped from record domains) — same car/driver alone insufficient; other-track handling transfers, other-track gearbox/track EXCLUDED (Daytona can't shape a Fuji window); contamination guard. **Phase 37:** `strategy/setup_outcome_learning.py` (EXACT-context lineage; delta→verdict; repeat/hold/reverse/BLOCK no-repeat guard, unblock only on later equal/stronger improvement; folds Phase-3 NEVER_MOVE_DIRECTION/KNOWN_UNSTABLE; rollback anchor = last non-worsening state; protected behaviours) + `strategy/setup_working_window.py` (per-field windows; proven values UNION not average; regression values→AVOID; converged→PROTECT; co-change interactions; independence; exact-context + single-discipline so Quali/Race separate; mature window survives one noisy record) + `strategy/driver_development_state.py` (repeated per-corner residuals→dimensions; strength/development-area/emerging/insufficient by aggregate score + trend, latest session never assumed better; attribution technique/track/setup/combined) + `strategy/coaching_priority.py` (few falsifiable priorities, driver-attributable only, each with corner/phase, current↔desired, why, ONE technique focus, measurable success criterion, confirming telemetry, falsifier, hold-setup-constant, gearing/drive-out assessment). **Phase 38:** `strategy/race_engineer_team_brief.py` (+render): ONE coordinated Chief/Setup/Performance/Coach/Strategy brief (views not authorities), contradiction resolution by SEQUENCING with hold-constant (coaching-vs-experiment, explore-vs-rollback), ONE ordered coherent plan, references (never creates) an existing canonical experiment, never labels an incremental step an ultimate setup, states missing evidence as a collection plan, subordinate fingerprints. Read-only `SessionDB.build_race_engineer_team_brief(...)` resolves context ONCE, reuses `_build_knowledge_chain` ONCE, computes 36-38 purely in memory, never calls lower public builders, constant query count small-vs-large, no N+1, writes nothing. UI `ui/race_engineer_team_vm.py` + `ui/race_engineer_team_panel.py` (`RaceEngineerTeamPanel`; NO Apply/mutation/experiment/campaign/schedule/editable-grade/AI/auto-export controls) in Development History beneath the Phase-33-35 panel; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker guard. Also **corrected the Phase 33-35 fingerprint wording** (semantic identity IS material; runtime/object/machine identity excluded; accidental source-row order excluded; canonical semantic priority order MAY be material). **NEW suites (68 tests, all passed): `tests/test_phase36_context.py`[11]** (fingerprint stability, missing-context explicit, completeness grades, discipline normalisation, different-identity-never-collides, insertion-order-excluded, EXACT-requires-full-identity, unverifiable, Daytona-gearbox-excluded-dynamics-transferable, shuffle-stable, incompatible-evidence-cannot-raise-exact-count), **`tests/test_phase37_setup_learning.py`[12]** (lineage order/verdicts, failed-direction blocked, block-stands-without-stronger-evidence, stronger-evidence-overturns-block, protected-knowledge blocks, rollback target = prior good, protected behaviour preserved, successful experiment updates window, AVOID on regression, inconclusive not promoted, windows-not-averaged, mature window survives noise), **`tests/test_phase37_driver_coaching.py`[9]** (trail-brake progression across 3 points = improving/technique, latest-good-not-promoted, persistent exit-wheelspin stays a priority, gear/drive-out assessment + hold-constant, problem-across-setups=technique/track, problem-after-one-delta=setup, setup-only not coached, shuffle-stable, more-evidence-never-reduces-count), **`tests/test_phase38_team_brief.py`[9]** (rollback-first plan, coaching-vs-experiment sequenced, ordered numbered plan, empty=honest collection plan, not-ultimate-setup, subordinate fingerprints, strategy honest without race plan, deterministic + shuffle-stable, destination-style change no semantic effect), **`tests/test_phase36_38_golden.py`[5]** (activation+brief render deterministic+ASCII, all role sections, no apply-instruction leak, rollback-first), **`tests/test_phase36_38_query_shape.py`[4]** (Phase-22 once + lower public builders never called, constant query count small-vs-large, writes nothing, empty truthful), **`tests/test_phase36_38_safety.py`[5]** (no forbidden imports/tokens across the 7 pure modules, never-raise-on-garbage, advisory declares not-a-setup/certification, DB v26/rule 46.0), **`tests/test_phase36_38_runtime.py`[5]** (DB byte-identical before/after, deterministic across restart + now_date-independent, exact evidence classified from real records, context change alters fingerprint), **`tests/test_phase36_38_ui.py`[8]** (panel construct/empty/none-safe, no Apply/experiment buttons, no setup values, page embed+forwarder, prior panels coexist, stale-worker ignored, build off UI thread). All suites pass standalone; Phase 32 + Phase 33-35 regression green. NO version-guard bumps; Golden `config_id` + Apply-gate UNCHANGED; no runtime/user files staged. Docs: `docs/ENGINEERING_BRAIN_PHASE{36,37,38}_*.md`. **The brief is NOT a certification and never claims a final/ultimate setup. Program 2 now spans Phases 12-38; Phase 39 NOT started.**)
>
> Prior update: 2026-07-20 (**Engineering Brain PROGRAM 2, Phases 33-35 — Assurance Review Pack (combined slice) + Phase 32 audit remediation** — deterministic offline READ-ONLY ADVISORY external-review slice on ONE branch `eng-brain-phase33-35-assurance-review-pack` (from Phase-32 tip `0e88b8e`): assurance-chain EXPORT (33), baseline->candidate COMPARISON (34), external REVIEW PACKAGE (35). Committed locally; NOT pushed / no PR / not merged; master unchanged @ `3d7c6af`; **DB stays v26** (no migration/persistence/DB write); RULE_ENGINE 46.0; `_setup_constants.py` byte-identical. Phase-32 audit remediation: fingerprint now covers EVERY material candidate field (13 mutation tests); (domain,investigation_type) grouping verified intentional; exact counts (Phase 32 = 11 added/6 modified) corrected in the Phase-32 doc. ONE canonical serializer (sorted-key ASCII JSON, allow_nan=False, 6-dp float norm + non-finite reject, content digests + timestamp-free fingerprints, fixed CHAIN_PHASE_ORDER). Fingerprint hierarchy: subordinate -> assurance-chain (over RECOMPUTED content digests, label-reuse-proof) -> canonical-manifest -> comparison (direction-material) -> review-package (over sorted (kind,digest); destination-free). Doctrine: newer!=better, no timestamp authority, domain-gone=incomparable, contradiction-closed-without-independence=unverified, assumption-dropped-without-evidence!=improvement, readiness-up-needs-independence, corroboration-gated grade movement, INCOMPATIBLE=no trend. Strict baseline loader (rejects Infinity/NaN/non-JSON/tampered/forged/path-traversal/duplicate/unknown-enum; no pickle/eval/import; recomputes not trusts). Writer is the ONLY file writer (explicit destination, staged/atomic/verified/cleanup, no db/runtime/secrets/paths, byte-deterministic zip). Read-only SessionDB entries reuse the chain ONCE, never call lower Phase 23-32 builders, baseline validation performs ZERO DB reads, constant query count, no N+1, Phase-29 gate unchanged. UI AssuranceReviewPackPanel: explicit Preview/Compare/Export actions, off-thread build+write, stale guards, NO Apply/experiment/campaign/schedule/editable controls, destination shown outside report, nothing auto-exports. **NEW suites (135 tests, all passed): `tests/test_phase32_fingerprint.py`[13] (every material field mutation + shuffle stability + cross-domain grouping), `tests/test_phase33_export.py`[14] (complete 26-32 inclusion, subordinate fps, canonical/section ordering, restart+shuffled-row identical, material-change alters chain fp, tamper detect, empty/negative-only/fully-assured, no setup values, real-DB no-write), `tests/test_phase34_comparison.py`[19] (compat/partial/incompat/unverifiable, all delta categories, deleted!=resolution, closed-without-evidence unverified, assumption-dropped!=improvement, readiness needs independence, timestamp ignored, direction-material fp, incompatible no-trend), `tests/test_phase35_package.py`[20] (deterministic spec/artifacts/report/manifest/digests/fp, explicit destination, no implicit writes, overwrite guard, failed-write cleanup, no source-paths/secrets/forbidden-files, deterministic byte-identical zip, re-open+verify, corrupted fails, forged/malformed/non-finite/path-traversal/duplicate/unknown-enum rejection, valid round-trip), `tests/test_phase33_35_query_shape.py`[7] (chain once, lower Phase 23-32 entries never called, constant query count, bounded full-scan reads, baseline validation zero DB reads, no writes, empty+negative-only), `tests/test_phase33_35_safety.py`[34] (no AI/LLM/key/optimiser/scheduler, pure modules no Qt/DB/wall-clock/pickle/file-IO, no setup/apply/experiment/campaign/schedule, loader no pickle/eval, no setup values, package no forbidden files/secrets, explicit-destination-only, DB v26/rule 46.0/_setup_constants byte-identical/no migration, no-AI scan), `tests/test_phase33_35_golden.py`[8] (12 fixtures restart-identical + distinct fingerprints, no timestamps/paths/random ids), `tests/test_phase33_35_runtime.py`[6] (DB byte-identical before/after, repeated/restart/shuffled-row identical, package independent verify + corruption fail, end-to-end dashboard export off UI thread no DB mutation, refuses without destination), `tests/test_phase33_35_ui.py`[14] (construct standalone, empty/none/error safe, only 3 explicit-action buttons + no editable controls, no setup values, export explicit-only, status outside report, baseline-invalid visible, incompatible no-trend, coexistence, stale-worker ignored, worker off UI thread).** All suites pass standalone; Phase 32 regression green; combined Phase 26-35 UI run 85 passed (intermittent shared-app.exec() harness artifact did not reproduce this run). NO version-guard bumps; Golden `config_id` + Apply-gate UNCHANGED; no runtime/user files staged. Runtime verified as above. Docs: `docs/ENGINEERING_BRAIN_PHASE{33,34,35}_*.md`. **An export/review package is NOT an independent certification. Program 2 now spans Phases 12-35; Phase 36 NOT started.**)
>
> Prior update: 2026-07-20 (**Engineering Brain PROGRAM 2, Phase 32 — Assurance-Driven Engineering Priority** — a deterministic offline READ-ONLY ADVISORY system converting the Phase-31 assurance FINDINGS into a PRIORITISED list of EVIDENCE INVESTIGATIONS to improve programme assurance; branch `eng-brain-phase32-assurance-priority` (from the Phase-31 tip `4b485be`). Priority ORDER not schedule; no dates/sessions/resources; no experiment/campaign/setup/Apply/AI/optimiser/scheduler; never guarantees a grade increase (impact POTENTIAL). Reuses Phase-17 info-gain DOCTRINE (does NOT import its candidates), Phase-22 chain, Phase 25–31 products; mutates none. **NO migration / NO new persistence / NO DB write — `DB_VERSION` stays 26** (restart + shuffled-legal-row-order identical rendering AND fingerprint; no timestamps). InvestigationPriorityBand 6, InvestigationType 10; transparent scoring (raw·weight·contribution, info_gain 3.0 highest). Doctrine: severity NOT sole rule (infeasible/dependent blocker→DEFER; cross-leverage can outrank single blocker); independent>dependent repetition; contradictions need DISCRIMINATING evidence (never majority/recency); assumptions stay assumptions; missing≠negative; confirmed-good protected; duplicates merge→leverage; deterministic prerequisites DEFER dependents behind prereqs; no scheduling; tie-break band→score→blocker→leverage→info_gain→cost→canonical domain→type→id. NEW pure `strategy/assurance_engineering_priority.py` + `strategy/assurance_engineering_priority_render.py`. NEW read-only `SessionDB.build_assurance_engineering_priority_report` (reuses shared _build_knowledge_chain ONCE; computes Phase-26/27/28/29/30/31 purely in-memory; never calls lower SessionDB builders; no N+1; renderer zero DB; writes nothing). UI: `ui/assurance_engineering_priority_vm.py` + `ui/assurance_engineering_priority_panel.py` (`AssuranceEngineeringPriorityPanel`; NO Apply/Run/Create/Schedule/editable-priority controls — asserted; `[COLLECT]`/`[DEFER]` text tags not colour alone) in Development History beneath the Phase-31 verdict; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase32_{domain[20],scoring[13],golden[9],integration[8],safety[14],ui_construction[11]}.py` (75, all passed)** — domain (finding→investigation mapping per category, dedup/merge+leverage, dependency ordering, infeasible deferral, confirmed-good protected, missing≠negative, fully-assured no-action, empty, no setup values/dates), scoring (every dimension visible + weights + exact contribution maths + score=Σ; blocker/leverage/info-gain drivers; effort/duplication/dependency penalties; infeasible not actionable; deterministic tie-break under shuffle), golden = 8 mandated scenarios (one blocking contradiction; multi-finding one-leverage investigation; stale version-sensitive; readiness capped by assumptions; severe blind spots no negative conclusion; dependent needs independent first; fully assured; negative-only no-known-domain) + shuffle/ordering stability, integration (Phase-22 once + nine lower SessionDB Phase-23..31 builders never called via monkeypatch + constant query count no N+1 + bounded full-scan history reads + renderer-no-DB + DB-hash/counts/user_version unchanged + negative-only builds + empty truthful + result shape), safety (no forbidden imports/wall-clock/setup-gen/experiment/campaign/schedule/Apply/optimiser/scheduler/AI, no Phase-17 portfolio import, never-guarantees-grade, no setup-value/date leak, _setup_constants byte-identical, runtime files not staged, DB v26/rule 46.0, no-AI scan), UI (construct/empty/no-action/none/error-safe; no mutation/priority controls; score breakdown + dependencies visible; no setup values; page embed + forwarder; prior panels coexist; stale-worker ignored; off-thread). Regression: Phase 30/31 integration green. Qt caveat: UI off-thread test uses shared `app.exec()` — passes standalone; full 26–32 combined UI run 71 passed (intermittent multi-file timing artifact did not reproduce). NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical; no runtime/user files staged. Runtime: DB byte-identical after repeated builds, restart + shuffled-legal-row-order identical rendering + fingerprint, user_version 26, query count constant (7 vs 7), no setup-value/date leak, ASCII-clean, negative-only visible, empty truthful, fully-assured no-action. Doc: `docs/ENGINEERING_BRAIN_PHASE32_ASSURANCE_PRIORITY.md`. **Program 2 now Phases 12–32; Phase 33 NOT started.**)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 31 — Knowledge Assurance & Audit Report (FINAL)** — the FINAL layer of Program 2: a deterministic offline READ-ONLY AUDIT of the whole knowledge programme (re-validation 26 + coverage 27 + readiness 28 + contradiction 29 + assumptions 30) for assurance FINDINGS, grading whether the knowledge can be ASSURED; branch `eng-brain-phase31-knowledge-assurance` (from the Phase-30 tip `8265ea3`). Reports findings ONLY; authors no setup, changes nothing. A single BLOCKING finding PREVENTS ASSURED (→ NOT_ASSURED); defects = hidden assumptions/unresolved conflicts/regressions/missing-transfer-boundaries/single-context-or-dependent-reliance/critical-blind-spots/stale-or-version-unaddressed/unknown-attribute-or-unverified-proxy-reliance/readiness-vs-coverage-and-readiness-vs-assumption-inconsistency/NON-DETERMINISM (sub-report lacking a content fingerprint)/DATA_MUTATION; grade RULE-BASED over visible severity counts (NOT opaque score), exposes counts+rule; too-little-knowledge → INSUFFICIENT_EVIDENCE. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps; audit self-check flags any non-deterministic sub-report). AssuranceFindingType 22; AssuranceSeverity 5; ProgrammeAssuranceGrade 5 (ladder no-known→INSUFFICIENT, blocking→NOT_ASSURED, major→PARTIALLY, moderate/minor→WITH_LIMITATIONS, else→ASSURED). NEW pure `strategy/assurance_finding.py`, `strategy/assurance_grade.py` (grade_assurance), `strategy/knowledge_assurance.py` (audit→(findings,has_known); dedup by (type,domain); structural fingerprint self-check; CLEAN when nothing above informational), `strategy/programme_assurance_report.py` (build_programme_assurance_report) + render. NEW entry `SessionDB.build_programme_assurance_report` (READ-ONLY; reuses shared _build_knowledge_chain [Phase-22 once + records]; computes Phase-26/27/28/29/30 purely in-memory; never calls Phase-23/24/25/26/27/28/29/30 DB entries; no N+1; renderer zero DB; writes nothing). UI: `ui/engineering_assurance_vm.py` + `ui/engineering_assurance_panel.py` (`EngineeringAssurancePanel`; NO Apply/edit/schedule controls — asserted; `[VERDICT]`/`[REVIEW]` text tags not colour alone) near the TOP of Development History beneath the Phase-28 readiness executive summary; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase31_{domain[16],golden[10],integration[8],safety[13],ui_construction[12]}.py` (59, all passed)** — domain (22/5/5 vocabulary; each audit derivation open-contradiction-blocking/regression-blocking/assumption-reliance/caps-readiness-mismatch/non-determinism/no-known/clean/dedup + full grade ladder), golden = mandated behaviours 1–10 (clean ASSURED; open contradiction NOT_ASSURED; regression NOT_ASSURED; major PARTIALLY; moderate WITH_LIMITATIONS; no-known INSUFFICIENT; non-determinism blocking; ready-with-capping-assumption mismatch; proxy+attribute reliance; restart/shuffle identical + counts exposed), integration (P22 once + P23/24/25/26/27/28/29/30 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape + real pipeline raises no non-determinism/mutation finding), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority, blocking prevents ASSURED, grade rule-based no-opaque-score, defect finding types recognised, no setup-value leak, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: Phase 26/27/28/29/30 integration green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE31_KNOWLEDGE_ASSURANCE.md`. **Program 2 engineering-knowledge-assurance stack (Phases 12–31) COMPLETE; Phase 32 NOT started.**)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 30 — Engineering Assumption Register** — a deterministic offline READ-ONLY advisory layer that makes explicit the ASSUMPTIONS the current knowledge relies on but has NOT established (transfer/single-context-generalisation/dependent-as-independent/currency/confirmed-good-persists/version-stability/contradiction-side/unknown-attribute/unverified-proxy); branch `eng-brain-phase30-assumption-register` (from the Phase-29 tip `2254996`). Classifies each + states impact; lists ONLY assumptions, NEVER facts. Reuses Phase-24 boundaries + Phase-25/26/27/29 verbatim. FACTS ≠ ASSUMPTIONS (is_factual gates: strong+current+no-gaps+no-open-contradiction → NO assumption); assumptions can ONLY CAP readiness NEVER create it (AssumptionImpact has no positive member; IMPACT_READINESS_CAP never lifts above ready); conservative bounds LABELLED. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps). AssumptionType 16; AssumptionStatus 8; AssumptionImpact 6. NEW pure `strategy/assumption_classification.py`, `strategy/assumption_impact.py` (IMPACT_READINESS_CAP), `strategy/engineering_assumption.py` (is_factual + derive_domain_assumptions), `strategy/programme_assumption_register.py` (build_programme_assumption_register; per-domain + programme-level from Phase-24 boundaries) + render. NEW entry `SessionDB.build_programme_assumption_register` (READ-ONLY; reuses shared _build_knowledge_chain [Phase-22 once + records]; computes Phase-26/27/29 purely in-memory; never calls Phase-23/24/25/26/27/29 DB entries; no N+1; renderer zero DB; writes nothing). UI: `ui/engineering_assumption_vm.py` + `ui/engineering_assumption_panel.py` (`EngineeringAssumptionPanel`; NO Apply/edit/schedule controls — asserted; `[REVIEW]`/`[BOUND]` text tags not colour alone) in Development History beneath the Phase-29 panel; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase30_{domain[13],golden[10],integration[7],safety[13],ui_construction[12]}.py` (55, all passed)** — domain (16/8/6 enums; is_factual; each derivation rule; contradiction-side only when open-with-standing; every assumption caps), golden = mandated behaviours 1–10 (factual no assumptions; single-context generalisation; dependent independence; currency; confirmed-good persistence; version-stability; assumptions only cap never create; conservative bound labelled; facts not listed; no fabricated domains + restart/shuffle identical), integration (P22 once + P23/24/25/26/27/29 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority, facts≠assumptions, assumptions only cap, conservative bound labelled, no setup-value leak, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: Phase 28/29 integration green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE30_ASSUMPTION_REGISTER.md`.)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 29 — Knowledge Contradiction Resolution** — a deterministic offline READ-ONLY advisory layer that finds per known domain where the evidence CONTRADICTS itself (a confirming AND a regressing conclusion for the same domain) and resolves each disagreement: by context, by stronger independent evidence, by supersession, or genuinely OPEN; branch `eng-brain-phase29-contradiction-resolution` (from the Phase-28 tip `c67607a`). Resolution STATUS ONLY; willing to say the evidence does not tell us which is right. Reuses canonical Phase-25 `_record_domains` verbatim; grounds every contradiction in REAL records. NEVER resolved by majority/averaging (count decides nothing; larger dependent count never wins); dependent NEVER defeats independent (independence = distinct sessions + high confidence, NOT count); newer does NOT auto-win (supersession needs later AND STRONGER, checked before independence so recency alone never decides); version/context mismatch SURFACED as a visible cause; a contradiction MAY stay UNRESOLVED. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps). ContradictionCause 19 (context 9 + evidence-quality 5 + directional 2 + residual 3); ContradictionStatus 9; ladder context→supersession→independence→both-weak→insufficient→UNRESOLVED. NEW pure `strategy/contradiction_cause.py` (context_difference_causes + CONTEXT_RESOLVING_CAUSES), `strategy/contradiction_resolution_status.py` (resolve; never majority/recency), `strategy/knowledge_contradiction.py` (detect_contradiction→KnowledgeContradiction; per-side signals = independence not count), `strategy/programme_contradiction_report.py` (build_programme_contradiction_report; contradiction exists only where a domain has BOTH sides) + render. NEW entry `SessionDB.build_programme_contradiction_report`. **The shared `_build_knowledge_chain` gate was RELAXED** to "known_domains OR any recorded evidence" (regressions retire domains out of known_domains, so the old gate hid the contradiction evidence; the Phase-25 timeline already keeps negative learning visible → strict improvement; Phase 26/27/28 confirmation-tests unaffected; empty programmes still yield no chain). No N+1; renderer zero DB; writes nothing. UI: `ui/engineering_contradiction_vm.py` + `ui/engineering_contradiction_panel.py` (`EngineeringContradictionPanel`; NO Apply/edit/schedule controls — asserted; `[OPEN]`/`[RESOLVED]` text tags not colour alone) in Development History beneath the Phase-27 panel; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase29_{domain[15],golden[10],integration[6],safety[13],ui_construction[12]}.py` (56, all passed)** — domain (19 causes/9 statuses; context-difference detection; full ladder: context / independence-not-count / newer-not-auto-win / later-and-stronger / genuine-unresolved / both-weak; detect_contradiction end-to-end), golden = mandated behaviours 1–10 (genuine stays unresolved; context resolves; version mismatch surfaced; independent beats dependent; majority never decides; newer not auto-win; later-and-stronger supersedes; both-weak insufficient; requires both sides; no fabricated domains + restart/shuffle identical), integration (P22 once + P23/24/25 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority, reuses _record_domains, never majority/recency, contradiction may stay open, version mismatch visible, no setup-value leak, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: Phase 25/26/27/28 (107) green after the shared-chain gate relaxation; no-AI scan green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE29_CONTRADICTION_RESOLUTION.md`.)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 28 — Engineering Knowledge Readiness Report** — the EXECUTIVE-SUMMARY CAPSTONE of Program 2: a deterministic offline READ-ONLY advisory layer stating per known domain WHETHER the evidence supports RELYING on the knowledge for a decision (ready / within limits / provisional / not yet ready) + a TRANSPARENT RULE-BASED programme grade; branch `eng-brain-phase28-knowledge-readiness` (from the Phase-27 tip `d0a9ff7`). Readiness STATUS ONLY — "ready" means the evidence supports relying on it, NEVER "apply this setup"; never marks unvalidated knowledge ready. Synthesises Phase-25 convergence + Phase-26 re-validation + Phase-27 coverage verbatim; invents NO domains. Unvalidated (converging/mixed/insufficient/unknown) is NEVER READY; a recorded conflict/regression BLOCKS readiness AND prevents a HIGH grade; grade is RULE-BASED over visible counts (NOT an opaque score/weight), exposing counts+fired rule; too-few-assessable → INSUFFICIENT_EVIDENCE. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps). KnowledgeReadinessStatus 11 (RELYABLE={ready,ready_with_limitations,context_bound_only}, BLOCKING={conflicted,regressed}); ProgrammeReadinessGrade 4 (MIN_ASSESSABLE=2, HIGH_RELYABLE_FRACTION=0.75, MEDIUM=0.40). NEW pure `strategy/knowledge_readiness.py` (classify_readiness→KnowledgeReadinessItem), `strategy/readiness_grade.py` (grade_programme→grade+counts+rule+reasons), `strategy/programme_readiness_report.py` (build_programme_knowledge_readiness_report; buckets + executive summary + grade detail) + `strategy/programme_readiness_report_render.py`. NEW entry `SessionDB.build_programme_knowledge_readiness_report` (READ-ONLY; reuses shared _build_knowledge_chain [Phase-22 once + records], computes Phase-26/27 purely in-memory; never calls Phase-23/24/25/26/27 DB entries; no N+1; renderer zero DB; writes nothing). UI: `ui/engineering_readiness_vm.py` + `ui/engineering_readiness_panel.py` (`EngineeringReadinessPanel`; NO Apply/edit/schedule controls — asserted; `[READY]`/`[REVIEW]` text tags not colour alone) at the TOP of Development History (executive summary); OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase28_{domain[20],golden[10],integration[7],safety[13],ui_construction[12]}.py` (62, all passed)** — domain (11-status ladder + rule-based grade: HIGH needs no blocker, single blocker prevents HIGH, insufficient-when-too-few, counts/rule exposed, low/empty), golden = mandated behaviours 1–10 (strong→ready; conflict/regression block; version→needs-revalidation; critical blind spot→needs-more-evidence; context-bound→context-bound-only; superseded→not ready; insufficient→INSUFFICIENT_EVIDENCE grade; single blocker prevents HIGH + counts exposed; no fabricated domains + 'ready' never marks unvalidated + restart/shuffle identical), integration (P22 once + P23/24/25/26/27 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority/redefined enums, grade rule-based no-opaque-score, unvalidated-never-ready, ready-never-means-apply-setup, no setup-value leak, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: Phase 26/27 integration green after reusing the shared chain; no-AI scan green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE28_KNOWLEDGE_READINESS.md`.)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 27 — Evidence Coverage & Blind-Spot Mapping** — a deterministic offline READ-ONLY advisory layer ABOVE the Phase-25 convergence authority: maps per known domain WHERE evidence is well supported and WHERE more evidence would strengthen confidence (a "blind spot") across 18 visible COVERAGE DIMENSIONS, ranking blind spots by severity; branch `eng-brain-phase27-evidence-coverage` (from the Phase-26 tip `23695ef`). Coverage STATUS ONLY — recommends no setup, schedules no test, creates no experiment/campaign, never treats absence of evidence as a negative result. Reuses Phase-23 transfer + Phase-25 convergence + Phase-26 re-validation verbatim; invents NO domains; reuses the canonical Phase-25 `_record_domains` mapping. MISSING (untested) is DISTINCT from REGRESSION_ONLY (a recorded negative), never conflated — missing means untested never wrong; a blind spot is NOT a fault (early-stage gaps → INFORMATIONAL); large DEPENDENT count is never strong coverage; one distinct track/car/driver/compound/discipline/version = SINGLE_CONTEXT_ONLY; severity = reliance (maturity/confidence/confirmed-good) vs evidence robustness (independent lines/contexts/convergence) — strong claim on thin evidence → CRITICAL/MATERIAL, unresolved conflict in relied-upon domain → CRITICAL. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps). 18 dimensions = context-breadth (track/layout/car/driver/discipline/gt7_version/tyre_compound/corner_phase/corner_type) + evidence-quality (independent_replication/repeated_confirmation/high_confidence_evidence/regression_check/confirmed_good_verification/conflict_resolution/convergence_achieved/transfer_validation/revalidation_currency); CoverageStatus 9; BlindSpotSeverity 5. NEW pure `strategy/coverage_dimension.py` (3 enums + visible thresholds + GAP_STATUSES), `strategy/evidence_coverage.py` (coverage_signals + assess_domain_coverage→DomainCoverage), `strategy/knowledge_blind_spot.py` (classify_blind_spot→KnowledgeBlindSpot; reliance×robustness ladder; "not a fault…untested never wrong"), `strategy/programme_coverage_report.py` (build_programme_evidence_coverage_report; buckets via reused mapping) + `strategy/programme_coverage_report_render.py`. SHARED `SessionDB._build_knowledge_chain` MODIFIED to ADDITIVELY return the evidence records it read (single bulk read preserved) so Phase 27 derives breadth with NO 2nd query; NEW entry `SessionDB.build_programme_evidence_coverage_report` (READ-ONLY; Phase-26 revalidation computed purely in memory; never calls Phase-23/24/25/26 DB entries; no N+1; renderer zero DB; writes nothing). UI: `ui/engineering_coverage_vm.py` + `ui/engineering_coverage_panel.py` (`EngineeringCoveragePanel`; NO Apply/edit/schedule controls — asserted; `[REVIEW]`/`[COVERED]` text tags not colour alone) in Development History; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker protection. **NEW suites `tests/test_phase27_{domain[17],golden[10],integration[7],safety[13],ui_construction[12]}.py` (69, all passed)** — domain (18 enums/orderings; MISSING≠REGRESSION; signal counting; per-dimension rules; blind-spot severity confirmed-good-thin→critical, emerging→informational, conflict-relied-upon→critical; never framed as fault), golden = mandated behaviours 1–10 (missing not negative; blind spot not problem; large dependent not strong; single context not multi; multi-context independent well-covered; confirmed-good thin raised; unresolved conflict critical; only-positive leaves failure untested; revalidation currency from P26; no fabricated domains + restart/shuffle identical), integration (P22 once + P23/24/25/26 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape + no setup-value leak), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority/redefined enums, reuses _record_domains, MISSING distinct from REGRESSION, no setup-value leak, safe blind-spot framing, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: Phase 25/26 (58) green after the chain change; no-AI architecture scan green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE27_EVIDENCE_COVERAGE.md`.)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 26 — Knowledge Decay & Re-validation Status** — a deterministic offline READ-ONLY advisory layer ABOVE the Phase-25 convergence authority: reports per knowledge domain whether established knowledge stays CURRENT/PROTECTED or may need RE-VALIDATION (context/version change or weakened evidence: conflict/regression/dependence/unknown date-or-context); branch `eng-brain-phase26-knowledge-revalidation` (from the Phase-25 tip `30de0bb`). STATUS ONLY — schedules nothing, no reminders/future dates/test plan/setup; never touches the Apply gate. Age ALONE never decays: NO date arithmetic in the pure layer (`timedelta`/`days_since`/`fromisoformat`/`strptime`/`max_age` absent + asserted; no fixed expiry). Dates are evidence data never authority; newer never auto-more-correct; a version change re-validates ONLY version-sensitive domains, version-insensitive NOT invalidated; confirmed-good stays PROTECTED unless explicitly invalidated; conflict weakens without deleting history; regression weakens/retires; superseded/retired stay visible-but-inactive; unknown→insufficient not auto-invalidate. **NO migration / NO persistence — `DB_VERSION` stays 26** (restart + shuffled-row + different-legal-order identical fingerprint; no timestamps). NEW pure `strategy/revalidation_reason.py` (`RevalidationReason` 20; reason emitted only when explicit signal present; GT7 reason gated on version_sensitive+version_changed), `strategy/knowledge_decay.py` (`programme_context_changes` — version_changed when excluded other-group shares source car+driver but differs in gt7_version; changed_fields from P22 `excluded_reasons.differing_fields` VERBATIM; `decay_signals`; `MIN_INDEPENDENT_FOR_ROBUST`=2), `strategy/revalidation_status.py` (`KnowledgeFreshnessStatus` 12 + `FRESHNESS_PRIORITY` + `classify_revalidation` deterministic ladder), `strategy/programme_revalidation_report.py` (`build_revalidation_report`) + `strategy/programme_revalidation_report_render.py`. NEW shared `SessionDB._build_knowledge_chain` (P22 report ONCE, then P23 transfer + P24 playbook + P25 timeline PURELY in memory via ONE bounded `_timeline_evidence_records` bulk read; never the P23/24/25 DB entries) consumed by NEW entry `SessionDB.build_programme_revalidation_report` (READ-ONLY; no N+1; renderer zero DB; writes nothing). UI: `ui/engineering_revalidation_vm.py` + `ui/engineering_revalidation_panel.py` (`EngineeringRevalidationPanel`; NO Apply/Freeze/Complete/Execute/edit/schedule controls — asserted; `[PROTECT]`/`[REVIEW]` text tags not colour alone) in Development History; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker-result protection. **NEW suites `tests/test_phase26_{domain[20],golden[10],integration[7],safety[13],ui_construction[12]}.py` (70, all passed)** — domain (context-change detection, decay signals, reason gating, full classification ladder, fingerprint stability), golden = mandated behaviours 1–10 (age stays current; unknown date; version-sensitive re-validates; version-insensitive protected; context narrows to aid; conflict weakens without deleting; regression weakens/retires; confirmed-good protected; superseded visible-but-inactive; restart+shuffle identical), integration (P22 once + P23/24/25 DB entries never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged + empty cheap + result shape), safety (no forbidden imports/wall-clock/setup-gen/scheduling, no duplicate authority/redefined enums, no date arithmetic, no setup-value leak, safety-denial language present, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence + off-thread. Regression: no-AI architecture scan green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` git-verified byte-identical. Runtime: DB byte-identical after repeated runs, restart-identical fingerprint, user_version 26, no setup-value leak, ASCII-clean. Doc: `docs/ENGINEERING_BRAIN_PHASE26_KNOWLEDGE_REVALIDATION.md`.)
>
> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 25 — Stable Knowledge Timeline & Convergence** — a deterministic offline read-only TEMPORAL knowledge layer: how understanding evolved, where evidence genuinely converged through INDEPENDENT repeated evidence, where unresolved, and where apparent repetition is only duplicated/dependent; branch `eng-brain-phase25-knowledge-timeline` (from the Phase-24 tip `8fae013`). Dates are evidence data only — recency never = correctness. NEVER generates setup values/recommends changes/schedules/creates experiments-campaigns/optimises/applies/mutates. No ML/stats/NLP/AI/scheduling/optimiser. **NO migration / NO persistence — `DB_VERSION` stays 26** (rebuilt from immutable records; restart- + shuffled-row-identical fingerprint; no timestamps). NEW pure `strategy/evidence_independence.py` (`EvidenceIndependence` 7; same-source repeats never = multiple confirmations; P22/23/24 re-statements one lineage), `strategy/knowledge_transition.py` (`KnowledgeTransitionType` 18; conflict/regression/supersession/uncertainty never collapsed; newer-weaker→NO_MATERIAL_CHANGE), `strategy/knowledge_timeline.py` (`TimelinePoint` + `build_timeline`; internal sort → insertion-order independent), `strategy/knowledge_convergence.py` (`ConvergenceStatus` 10; strong needs ≥2 independent lines + established maturity + no unresolved regression/conflict; context-bound never strong; reuses P22 maturity/confidence + P24 confirmed-good), `strategy/programme_timeline_report.py` (joins P22 graph + P24 playbook + records; VISIBLE P22 keyword maps; regression counts from raw records so negative learning visible) + `strategy/programme_timeline_report_render.py`. Orchestrator `SessionDB.build_programme_knowledge_timeline` (READ-ONLY; P22 report ONCE, P23+P24 PURELY [never their DB entries], ONE bounded bulk read [query count constant]; no N+1; writes nothing). UI: `ui/engineering_timeline_vm.py` + `ui/engineering_timeline_panel.py` (`EngineeringTimelinePanel`; NO Apply/Create-Experiment/Schedule/Optimise/setup-editor controls — asserted; states tagged `[PROTECT]`/`[REVIEW]` not colour alone) in Development History; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker-result protection. **NEW suites `tests/test_phase25_{independence[13],convergence[36],timeline[14],integration[5],golden[11],safety[10],ui_construction[10]}.py` (93, all passed)** — independence (same-record/session/campaign/independent/unknown, dependent repeats don't inflate), convergence+transition (strong-needs-independent, dependent-no-false-converge, confirmed-good distinct, conflict/regression/retired/superseded/context-bound, newer-weaker-no-override, stronger-reopens), timeline (chronological+deterministic tie-breaks, unknown/equal dates, insertion-order-independent, conflict introduce+resolve visible, history not overwritten, no-timestamp fingerprint), integration (P22 once + P23/P24 DB never called + constant query count no N+1 + renderer-no-DB + DB-hash/counts/user_version unchanged), golden 1/2/3/5/7/8/9/10 + empty, safety (no setup-gen/values/writes, no scheduler/optimiser, no 2nd graph/transfer, session_date-not-recorded_at, _setup_constants unchanged, no-AI scan), UI + stale-worker + coexistence. Regression: Phase 17–24 non-UI (84) + session_db/no-AI (34) + Phase 22/23/24 UI (7+7+9) + Apply-gate/config-safety (125, 1 skip) green. NO version-guard bumps. Golden `config_id` + Apply-gate UNCHANGED. `_setup_constants.py` + protected runtime files git-verified byte-identical. Runtime: independent convergence + dependent non-convergence + confirmed-good + regression/retired + conflict + unknown dates + cross-car excluded; table counts + DB-file SHA-256 unchanged, user_version 26, restart-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE25_KNOWLEDGE_TIMELINE.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 24 — Cross-Programme Engineering Playbook** — assembles reusable engineering knowledge across the car stable into a deterministic read-only INVESTIGATION playbook (NOT a baseline setup); branch `eng-brain-phase24-engineering-playbook` (from the Phase-23 tip `4559bed`). NEVER generates/copies setup values, recommends a starting setup, applies/schedules/optimises, creates experiments/campaigns, mutates/persists, recreates a knowledge graph, or reinterprets Phase-23 transfer (TransferLevel reused verbatim). No ML/stats/NLP/AI/optimisation/scheduling. **NO migration / NO persistence — `DB_VERSION` stays 26** (rebuilt from immutable records; no timestamps in fingerprint), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/stable_themes.py` (`StableEngineeringTheme` per established source domain, grounded not keyword), `strategy/investigation_priority.py` (6 categories via deterministic ladder + transparent weighted score over 11 VISIBLE dimensions/weights/caps; masking_conflict), `strategy/knowledge_boundary.py` (`BoundaryType` 16 incl unknown_vehicle_attribute never-guessed + unverified_transfer_proxy), `strategy/new_programme_brief.py` (per target + explicit no-setup-transferred statement), `strategy/engineering_playbook.py` (`build_engineering_playbook`; joins Phase-22 graph + Phase-23 candidates, deterministic tie-breakers) + `strategy/engineering_playbook_render.py`. Orchestrator `SessionDB.build_programme_engineering_playbook` (READ-ONLY; Phase-22 report EXACTLY ONCE, Phase-23 transfer PURELY [never the Phase-23 DB entry, no 2nd Phase-22 build], no N+1; writes nothing). UI: `ui/engineering_playbook_vm.py` + `ui/engineering_playbook_panel.py` (`EngineeringPlaybookPanel`; NO Apply/Create-Experiment/Schedule/Optimise/setup-editor/import/copy-setup controls — asserted) in Development History; OFF Qt thread via reused `MechanismAnnotationWorker` + stale-worker-result protection. **NEW suites `tests/test_phase24_{domain[27],transfer_integration[10],query_shape[4],golden[7],safety[12],ui_construction[16]}.py` (76, all passed)** — domain (grounded themes, recurrence, confirmed-good extraction, failed-direction preservation, contradiction handling, boundaries, unknown-attrs, fingerprint-no-timestamps, stable ordering, empty/single), transfer-integration (levels unchanged, NOT_TRANSFERABLE stays, SUPPORTED no setup values, gearbox car/track, track/fuel isolation, driver same-driver, version cap, unknown conservative, proxy labelled, no setup-field values), query-shape (Phase-22 built once + Phase-23 DB entry never called + constant vs campaign count no N+1 + renderer-no-DB), golden 1/2/4/5/6 + real production path [all table counts + DB-file sha256 unchanged] + restart determinism, safety (no setup-gen/apply/optimiser/scheduler, no 2nd graph, TransferLevel reused, no-write, _setup_constants unchanged, no-AI scan), UI construction + stale-worker + prior-phase coexistence + off-thread. Regression: Phase 17–23 non-UI (57) + session_db/no-AI (34) + Phase 22/23 UI (7+7) + config-safety (30) + Apply-gate (test_group41+setup_apply_checkpoint+phase3_coherence = 95, 1 skip) all green. NO version-guard bumps (DB unchanged). Golden `config_id` + frozen fan-out allowlist + Apply-gate UNCHANGED. `_setup_constants.py` + protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE24_ENGINEERING_PLAYBOOK.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 23 — Knowledge Transfer Eligibility & Cross-Car Engineering Reuse** — a deterministic engineering-KNOWLEDGE transfer layer (NOT setup transfer): is established knowledge reusable in another compatible context? branch `eng-brain-phase23-knowledge-transfer` (from the Phase-22 tip `0ce6721`). Transfers NO setup, recommends applying NOTHING, imports NOTHING; every level fixed by VISIBLE deterministic rules. No ML/stats/NLP/AI/optimisation/scheduling/graph-libraries. **NO migration / NO persistence — `DB_VERSION` stays 26** (all reconstructed from immutable records), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/transfer_rules.py` (rules VISIBLE CONSTANTS each why+authority: same_manufacturer/drivetrain/layout/race_category/suspension_architecture[proxy]/compatible_gt7_version/same_driver; `car_attributes` from GT7 car name, unknown stays unknown; `DOMAIN_TRANSFER_CLASS` 17 domains → architecture_dependent/handling_drivetrain/car_track_specific/context_bound/driver_specific), `strategy/knowledge_transfer.py` (`TransferLevel` 6 + `evaluate_transfer`; level ONLY by rules + domain class; established-source gate; gearbox only-if-explicitly-supported; context-bound/driver/version handling), `strategy/engineering_reuse.py` (`summarise_reuse` reusable/needs_more_evidence/not_reusable + isolated; never recommends applying), `strategy/programme_transfer_report.py` (source-domain × target + reuse + visible rule catalogue) + `strategy/programme_transfer_report_render.py`. Orchestrator `SessionDB.build_programme_transfer_report` (READ-ONLY; composes Phase-22 report ONCE; no per-campaign query; writes nothing). UI: `ui/engineering_transfer_vm.py` + `ui/engineering_transfer_panel.py` (`EngineeringTransferPanel`; NO Apply/Execute/Import/Copy-Setup/edit controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`. **NEW suites `tests/test_phase23_{transfer_rules,eligibility,golden,query_shape,safety,ui_construction}.py` (62)** — transfer-rules (car-attribute derivation known/unknown/empty + rule eval + visible catalogue + domain classes), eligibility (established gate + architecture SUPPORTED/LOW + context-bound/gearbox/driver-specific/version + handling-on-drivetrain + reuse grouping/isolation), golden A–C + real production path [writes nothing] + restart determinism + empty DB + ASCII render, query-shape (constant vs campaign count no N+1, renderer-no-DB), safety (no forbidden imports/wall-clock, no setup-transfer/apply/import/copy [no argmax/heapq/optimi/sklearn/numpy/networkx], visible rule constants, unlike-never-transfer, no-write, never-recommends-applying, no-AI scan), UI construction + prior-phase coexistence + off-thread + no controls. NO version-guard bumps (DB unchanged). Phase 20–22 non-UI regression (incl. touched session_db/dashboard/development_history_page) green; no-AI architecture guard green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE23_KNOWLEDGE_TRANSFER.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 22 — Engineering Knowledge Graph & Multi-Event Knowledge Roll-Up** — the first programme-level knowledge graph: deterministic explainable map of what the Brain knows / how well / on what evidence / what's unknown, organised by ENGINEERING DOMAIN, rolled up across compatible events; branch `eng-brain-phase22-knowledge-graph` (from the Phase-21 tip `30df17e`). NOT AI/graph-theory/ML/optimisation/scheduling. NEVER decides/optimises/schedules/completes/applies/mutates. No ML/stats/NLP/AI/Bayesian/graph-libraries/network. **NO migration / NO persistence — `DB_VERSION` stays 26** (all reconstructed from immutable records), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/engineering_knowledge_graph.py` (`KnowledgeDomain` 17 + `build_knowledge_graph`; VISIBLE FIELD/FAMILY/MECHANISM_DOMAIN_KEYWORDS maps unmapped→no domain NO inference; DomainKnowledge state/confidence/maturity/uncertainty each reason+source+calculation + supporting campaigns/experiments/mechanisms/evidence + limitations; ALL domains enumerated, empty→MISSING), `strategy/multi_event_rollup.py` (`build_rollup`; compat key car+discipline+gt7_version+driver, track/layout may differ; NEVER merges unlike contexts, exclusions name differing fields), `strategy/knowledge_maturity.py` (`KnowledgeMaturity` 7 + `classify_maturity`, ladder over Phase-19/20/21, no invented weighting), `strategy/programme_knowledge_report.py` (rolls up + graphs primary group) + `strategy/programme_knowledge_report_render.py`. Orchestrator `SessionDB.build_programme_knowledge_report` (READ-ONLY; 1 SELECT DISTINCT → distinct events; Phase-21 season report ONCE per compatible event + enrich with knowledge_state; incompatible surfaced not merged; writes nothing). UI: `ui/engineering_knowledge_graph_vm.py` + `ui/engineering_knowledge_graph_panel.py` (`EngineeringKnowledgeGraphPanel`; NO Apply/Approve/Freeze/Complete/Execute/edit/schedule controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`. **NEW suites `tests/test_phase22_{maturity,knowledge_graph,rollup,golden,query_shape,safety,ui_construction}.py` (71)** — maturity (7 levels reachable+explained+sourced), knowledge-graph (visible non-inferred mapping + aggregation + missing domains + multi-track/conflict limitations + large graph[60] + no graph libs), rollup (compatible merge + incompatible-not-merged+reason + dedup + report assembly + determinism), golden A–C + real production path [writes nothing] + restart determinism + empty DB, query-shape (constant query count vs campaign count no N+1, renderer-no-DB), safety (no forbidden imports/wall-clock, no scheduling/execution/optimisation [no argmax/heapq/dijkstra/kmeans/sklearn/numpy/networkx/igraph], visible domain maps, unlike-never-merged, no-write, completion-stays-Phase-18, no-AI scan), UI construction + prior-phase coexistence + off-thread + no controls. NO version-guard bumps (DB unchanged). Phase 19–21 non-UI regression (incl. touched session_db/dashboard/development_history_page) green; no-AI architecture guard green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE22_ENGINEERING_KNOWLEDGE_GRAPH.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 21 — Season Development Plan & Cross-Campaign Knowledge Map** — a deterministic READ-ONLY season-level planning layer (Engineering Director's dashboard) understanding the programme as a whole; branch `eng-brain-phase21-season-development` (from the Phase-20 tip `dd0f1ea`). ONLY EXPLAINS engineering state; NEVER decides/optimises/reprioritises/schedules/completes/applies/creates. No ML/stats/NLP/AI/Bayesian/graph-optimisation/clustering/scheduling. **NO migration / NO persistence — `DB_VERSION` stays 26** (all reconstructed from existing records), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/season_development.py` (`summarize_season`; each metric value+reason+source+calculation; totals reuse Phase-17 value + Phase-19 cost verbatim), `strategy/cross_campaign_map.py` (`CampaignRelationship` 9 + `build_cross_campaign_map`; O(n²) pairwise; every edge evidence-grounded reason+supporting_evidence+authority never inferred; DUPLICATES/CONTRADICTS/DEPENDS_ON/SUPPORTS[shared mechanism+asymmetry, directional]/OVERLAPS/BLOCKED_BY/RELATED/ISOLATED; NOT graph search/ML), `strategy/season_knowledge_map.py` (`SeasonKnowledgeState` 9 + `classify_campaign_knowledge`; ladder over Phase-18/19/20; reason+source+factors), `strategy/season_engineering_report.py` (joins Phase-18/19/20 per campaign_id, preserves order, runs 3 layers) + `strategy/season_engineering_report_render.py`. Orchestrator `SessionDB.build_season_engineering_report` (READ-ONLY; composes Phase-18 programme ONCE, derives Phase-19 efficiency + Phase-20 quality purely + 1 registry + 1 calibration read; no N+1; writes nothing). UI: `ui/engineering_season_vm.py` + `ui/engineering_season_panel.py` (`EngineeringSeasonPanel`; NO Apply/Approve/Freeze/Complete/Execute/edit/schedule controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`. **NEW suites `tests/test_phase21_{knowledge_map,relationships,development,golden,query_shape,safety,ui_construction}.py` (72)** — knowledge-map (all 9 states reachable+explained+sourced), relationships (all types reachable + evidence-grounded + isolated + large-count[40] + duplicate-id + no-graph-optimisation), development (metrics with reason/source/calc + report assembly all 3 layers + order preserved), golden A–B + real production path [writes nothing] + restart determinism + empty DB, query-shape (single build, constant query count no N+1, renderer-no-DB), safety (no forbidden imports/wall-clock, no scheduling/execution, no optimiser/graph-search[no argmax/heapq/dijkstra/kmeans/sklearn/numpy/networkx], evidence-grounded edges, no-write, completion-stays-Phase-18, no-AI scan), UI construction + prior-phase coexistence + off-thread + no controls. NO version-guard bumps (DB unchanged). Phase 18–20 non-UI regression (incl. touched session_db/dashboard/development_history_page) green; no-AI architecture guard green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE21_SEASON_DEVELOPMENT.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 20 — Confidence-Weighted Evidence & Development ROI** — three deterministic ADVISORY-ONLY analysis layers built ABOVE Phase 19 that MEASURE knowledge confidence / development ROI / campaign opportunity and decide nothing; branch `eng-brain-phase20-confidence-and-roi` (from the Phase-19 tip `f95345e`). Completion stays Phase-18-governed; frozen Apply gate unchanged. NEVER completes/freezes/abandons/applies/creates-experiments/alters-outcomes/re-ranks/recomputes-Phase-17-value-or-Phase-19-cost/auto-prioritises. No ML/stats/NLP/AI/optimiser/Bayesian. **NO migration / NO persistence — `DB_VERSION` stays 26** (all reconstructed from existing records), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/knowledge_confidence.py` (`ConfidenceLevel` 6 + `assess_campaign_confidence`; 7 components each reason/source/calculation; overall = equal-weighted mean of INCLUDED components + named-constant bands + visible caps [<MIN_REPEATABILITY→MEDIUM, conflicting→LOW, regression+0-confirm→VERY_LOW, no-evidence→UNKNOWN]; prediction_accuracy context-level excluded when uncalibrated), `strategy/development_roi.py` (`estimate_campaign_roi`; knowledge NOT lap time; info-gain+cost reused verbatim from Phase 19; priority_reason is explanation not ranking; NOT an optimiser), `strategy/campaign_opportunity.py` (`classify_campaign_opportunity` 8 outcomes+UNKNOWN; reads Phase-18 completion never overrides), `strategy/knowledge_quality.py` (composes 3 per campaign, preserves order) + `strategy/engineering_knowledge_quality_render.py`. Orchestrator `SessionDB.build_engineering_knowledge_quality` (READ-ONLY; reuses Phase-19 `build_engineering_efficiency` ONCE read-only + 1 calibration read; no N+1; writes nothing). UI: `ui/engineering_confidence_vm.py` + `ui/engineering_confidence_panel.py` (`EngineeringConfidencePanel` — distinct from Phase-12 `EngineeringKnowledgePanel`; NO Apply/Approve/Freeze/Complete/Execute/edit controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`. **NEW suites `tests/test_phase20_{confidence,roi,opportunity,golden,query_shape,safety,ui_construction}.py` (74)** — confidence (levels/caps/component-monotonicity/calibration-inclusion/equal-weighted-mean/thresholds/determinism/garbage), roi (info+cost reused-not-recomputed, no-testable→0, gap=1−conf, discriminating-closes-more, risk levels, not-lap-time, disclaims-ranking), opportunity (all outcomes reachable + never-overrides-Phase-18-completion + factors visible), golden A–C + real production path [writes nothing] + restart determinism + empty DB, query-shape (single build, constant query count no N+1, renderer-no-DB), safety (no forbidden imports/wall-clock, no completion/execution, not-an-optimiser [no sort/rank/argmax/heapq], value/cost-not-recomputed, no-write, completion-stays-Phase-18, no-AI scan), UI construction + Phase-12 coexistence + off-thread + no controls. NO version-guard bumps (DB unchanged). Phase 12–19 non-UI regression (incl. touched session_db/dashboard/development_history_page) green; no-AI architecture guard green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE20_CONFIDENCE_AND_ROI.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 19 — Campaign Persistence, Evidence Saturation & Cost of Knowledge** — three deterministic ADVISORY-ONLY layers built ABOVE Phase 18 that MEASURE campaign age / evidence saturation / cost of knowledge and decide nothing; branch `eng-brain-phase19-campaign-persistence` (from the Phase-18 tip). Saturation INDEPENDENT of status; completion stays Phase-18-governed; frozen Apply gate unchanged. NEVER completes/freezes/abandons/applies/creates-experiments/alters-outcomes/re-ranks/recomputes-Phase-17-value. No ML/stats/NLP/AI. **ADDITIVE IDEMPOTENT migration — `DB_VERSION` 25 → 26** (new standalone metadata-only `engineering_campaign_registry`; no existing table/column/query altered), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/evidence_saturation.py` (`EvidenceSaturation` 6 + `assess_saturation`; signals+named thresholds+reasons all visible; status never reads campaign status), `strategy/engineering_cost_model.py` (`estimate_experiment_cost` A/B/A laps+time+fuel+tyres+value_per_lap/minute/info_gain_per_tyre_set with value reused verbatim from Phase 17; `plan_budget` greedy fit in Phase-17 rank order, not an optimiser), `strategy/campaign_persistence.py` (`CampaignRegistryEntry` metadata-only + `campaign_age_days` [dates as data] + `build_engineering_efficiency`), `strategy/engineering_efficiency_render.py`. ONLY new write `SessionDB.record_engineering_campaigns` (idempotent — preserves first_seen/creation_session + user notes/archive; refreshes last_seen/completion_state) + `get_campaign_registry`/`set_campaign_note`; `SessionDB.build_engineering_efficiency` (READ-ONLY by default, reuses `build_engineering_campaign_programme` ONCE + 1 registry read no N+1; opt-in registry capture only when `register_session_id` passed, touches ONLY the registry). UI: `ui/engineering_efficiency_vm.py` + `ui/engineering_efficiency_panel.py` (`EngineeringEfficiencyPanel`, NO Apply/Approve/Freeze/Complete/Execute/edit controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`. **NEW suites `tests/test_phase19_{saturation,cost,persistence,golden,query_shape,safety,ui_construction}.py` (66)** — saturation (every status reachable+explained, thresholds/signals visible, independent-of-status, no hidden numbers, garbage-safe), cost/budget (A/B/A laps, coupled, value-reused-not-recomputed, greedy fit no optimiser, only-testable planned), persistence (registry round-trip, age, efficiency assembly, idempotent provenance, notes/archive preserved on rewrite, restart, migration idempotency, opt-in capture), golden A–C + real production path [writes only registry] + restart determinism + empty DB, query-shape (single build, constant query count no N+1, renderer-no-DB), safety (no forbidden imports/wall-clock, no completion/execution, value-not-recomputed, versions, read-only build, capture-touches-only-registry, no-AI scan), UI construction + off-thread + no controls. **Version-guard bump: Phase 8–18 DB-version assertions updated 25 → 26** (legitimate version-bump maintenance; 260 re-green). no-AI architecture + config-safety guards green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE19_CAMPAIGN_PERSISTENCE.md`.)

> Prior update: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 18 — Engineering Campaigns & Multi-Session Development Planning** — a deterministic READ-ONLY layer grouping a Phase-17 portfolio into coherent multi-session vehicle-development CAMPAIGNS; branch `eng-brain-phase18-engineering-campaigns` (from `60a7e48`, Phase-17 tip). Orchestrates existing authorities (ranking=Phase 17, lifecycle=Phase 16, outcomes/reconciliation/calibration=Program 1); NEVER applies/approves/freezes/creates-experiments/alters-outcomes/writes-records/hidden-weighting/re-ranks/marks-unvalidated-complete. No ML/stats/NLP/AI. **NO migration — `DB_VERSION` stays 25**, `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/engineering_campaign.py` (`CampaignIdentity`/`CampaignObjective`[bounded/traceable]/`CampaignStatus` 8 [NOT_STARTED/ACTIVE/BLOCKED/VALIDATION_REQUIRED/READY_TO_FREEZE/COMPLETED/ABANDONED/STALE]/`CampaignStageType` 7 [DEFINE/DISCRIMINATE/INTERVENE/REVIEW/VALIDATE/FREEZE/RACE_READY]/`CampaignRole` 7/`CompletionCriterion`/`CampaignProgress`[progress_pct=criteria_satisfied/total, factors visible, no magic numbers]/`EngineeringCampaign`/`EngineeringCampaignProgramme`; deterministic grouping by objective key (issue-family,region); multi-session outcome projection from immutable dev records; stale detection; recommended focus + roadmap; `build_campaign_programme`), `strategy/engineering_campaign_render.py` (summary+list+detail+roadmap, no Apply/freeze wording). Orchestrator `SessionDB.build_engineering_campaign_programme` (READ-ONLY; reuses Phase-17 `build_experiment_portfolio` ONCE [+projected outcome history so Phase-17 retirement fires] + 1 dev-record read + 1 calibration read; no N+1) + `_campaign_outcome_history`. UI: pure `ui/engineering_campaign_vm.py` + `ui/engineering_campaign_panel.py` (`EngineeringCampaignPanel`, NO Apply/Approve/Revert/freeze/edit/create controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`; frozen Apply gate + existing lifecycle remain the only execution routes. **NEW suites `tests/test_phase18_{campaign_domain,golden,safety,query_shape}.py` (36) + `tests/test_phase18_ui_construction.py` (5)** — identity/scoping/grouping/objective/stages/status/progress/criteria/validation-required/ready-to-freeze/completed/blocked/stale/retirement/incompatible-context/determinism/rendering, golden UAT A–D (rear-braking VALIDATION_REQUIRED / exit-traction regression-retired / confirmed READY_TO_FREEZE / stale) + real production path + restart, no mutation/apply/freeze/execution/AI + no duplicate ranking/lifecycle + never-complete-unvalidated + versions, query-shape (single portfolio build, constant query count no N+1, cheap empty, renderer-no-DB), UI construction + off-thread + no controls. NO version-guard bumps. Phase 12–17 non-UI (451) + setup-experiment/outcome/preflight/postflight/reconciliation (207) + broad non-UI strategy regression (2409) green; every UI construction module passes per-file (12→18; UI-worker tests run per-file per the documented PyQt isolation requirement). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Protected runtime files git-verified byte-identical. Doc: `docs/ENGINEERING_BRAIN_PHASE18_ENGINEERING_CAMPAIGNS.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 17 — Experiment Portfolio Optimisation & Information-Gain Selection** — the deterministic engineering PLANNER (before Phase 15) that ranks legal experiments by ENGINEERING VALUE (information gain FIRST, not lap time); branch `eng-brain-phase17-experiment-portfolio-optimisation` (from `3cc36e8`, Phase-16 tip). CONSUMES Phase-15 bounded experiments + embedded Phase-14 hypotheses + outcome history + prediction calibration + working-window/confirmed-good; replaces none. NEVER mutates/applies/writes/duplicates. No ML/stats/NLP/AI. **NO migration — `DB_VERSION` stays 25**, `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/experiment_portfolio.py` (13 INDIVIDUALLY-VISIBLE value dimensions, `DIMENSION_WEIGHTS` exposed, information_gain highest; `ValueDimension`/`ExperimentValuation`/`EngineeringPortfolio`; `PortfolioRole` HIGHEST_VALUE/ALTERNATIVE/DEFERRED/BLOCKED/REDUNDANT/OBSOLETE; `DependencyKind` SUPERSEDES/MUTUALLY_EXCLUSIVE/UNNECESSARY_IF_FAILS/DEPENDS_ON; retirement already-confirmed/rejected/superseded→OBSOLETE; `SessionSuitability` unknown-lowers-confidence-never-invents; advisory roadmap experiment→review→validate→freeze→race; `build_portfolio`), `strategy/experiment_portfolio_render.py` (visible dimensions + roadmap, "information gain first not lap time", no Apply wording). Orchestrator `SessionDB.build_experiment_portfolio` (READ-ONLY; reuses Phase-15 build ONCE + calibration; no N+1). UI: pure `ui/engineering_plan_vm.py` + `ui/engineering_plan_panel.py` (`EngineeringPlanPanel`, NO Apply/Approve/Revert/edit controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`; frozen Apply gate remains the sole mutation route. **NEW suites `tests/test_phase17_{portfolio_domain,golden,safety,query_shape}.py` (32) + `tests/test_phase17_ui_construction.py` (5)** — generation/ranking/info-gain/visible-dimensions/retirement/redundancy/dependencies/roadmap/ties/session-awareness/determinism/rendering, real-DB production path + restart, no mutation/apply/writes/AI + no hidden optimisation + no duplicate scoring/lifecycle + learning-not-lap-time, query-shape (single-aggregate reuse, no N+1, cheap empty, renderer-no-DB), UI construction + off-thread + no controls. NO version-guard bumps. Phase 12–16 non-UI (352) + frozen/no-AI/config/fan-out/session_db + broad non-UI strategy regression (2384) green; every UI construction module passes per-file (12→17; UI-worker tests run per-file per the documented PyQt isolation requirement). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE17_EXPERIMENT_PORTFOLIO_OPTIMISATION.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 16 — Guarded Experiment Lifecycle & Postflight Loop Closure** — the deterministic READ-ONLY orchestration that CLOSES the loop by CONNECTING existing authorities (no new experiment system/Apply path/outcome recorder/reconciler); branch `eng-brain-phase16-guarded-experiment-lifecycle` (from `1f90367`, Phase-15 tip). Converts a READY Phase-15 bounded experiment → canonical `SetupExperiment` request (via existing `build_experiment_from_recommendation`) → existing Phase-10 preflight; and for an executed experiment assembles a read-only closed-loop summary from the existing Phase-3 outcome + Phase-11 reconciliation + prediction calibration. NEVER applies/bypasses-Apply/persists-duplicates/creates-outcome-or-reconciliation/invents-feedback/simulates/mutates. No ML/stats/NLP/AI. **NO migration — `DB_VERSION` stays 25**, `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/experiment_lifecycle.py` (`ExperimentLifecycleState` 16 + `LifecycleTrace` unbroken provenance chain + `ExperimentExecutionRequest`/`ExperimentExecutionResult`/`ExperimentLifecycleSummary`; `build_execution_request` [READY candidate → canonical SetupExperiment status=draft], `assemble_execution_result` [preflight ok→READY_FOR_MANUAL_APPLY / fail→PREFLIGHT_FAILED], `assemble_lifecycle_summary` [from existing records]), `strategy/experiment_lifecycle_render.py` (ordered loop-stage rows, no Apply wording). Orchestrator `SessionDB.build_experiment_execution` (one candidate → EXISTING Phase-10 preflight; read-only) + `SessionDB.build_engineering_lifecycle` (aggregate; reuses Phase-15 build ONCE + calibration + reconciliation records — no N+1). UI: pure `ui/engineering_lifecycle_vm.py` + `ui/engineering_lifecycle_panel.py` (`EngineeringLifecyclePanel`, NO Apply/Approve/Revert/edit controls — asserted) in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`; frozen Apply gate remains the sole mutation route. **NEW suites `tests/test_phase16_{lifecycle_domain,golden,safety,query_shape}.py` (30) + `tests/test_phase16_ui_construction.py` (5)** — creation/traceability/preflight-apply-outcome-reconciliation-prediction routing, real-DB production path (aggregate + single-candidate execution through the real preflight) + restart, no duplicate lifecycle/apply/outcome/reconciliation/calibration + connects-existing-only + no-shadow-model + read-only + versions, query-shape (single-aggregate reuse, no N+1, cheap empty, renderer-no-DB), UI construction + off-thread + no controls. NO version-guard bumps. Phase 12–15 (341) + frozen/no-AI/config/fan-out/session_db (80) + experiment/outcome/preflight/postflight/reconciliation (285) + broad non-UI strategy regression (2000) green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. **Engineering Brain loop closed end-to-end.** Doc: `docs/ENGINEERING_BRAIN_PHASE16_GUARDED_EXPERIMENT_LIFECYCLE.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 15 — Minimum-Effective Experiment Synthesis Handoff** — the deterministic READ-ONLY handoff from a valid testable Phase-14 hypothesis into the existing setup-synthesis/setup-experiment authorities; output = a BOUNDED setup-experiment candidate: the SMALLEST legal reversible numeric step off the canonical applied baseline; branch `eng-brain-phase15-minimum-effective-experiment-synthesis` (from `8e48beb`, Phase-14 tip). Never auto-applies / bypasses the Apply gate / invents limits / builds a second synthesiser / optimises the car / silently changes coupled fields / mutates diagnosis-mechanism-outcome-calibration-setup-history-active-setup / persists an experiment. No ML/stats/NLP/AI. **NO migration — `DB_VERSION` stays 25**, `RULE_ENGINE_VERSION` 46.0. CONSUMES: baseline=`setup_state_authority.evaluate_analysis_gate`+`ActiveSetup`+`compute_setup_hash`; step/quantiser=`experiment_selection.legal_step`+`setup_synthesis._round`; bounds=`setup_ranges.resolve_ranges`; final-drive invariant=`gearbox_evidence`; lockouts=`working_window.locked_directions()`. NEW pure `strategy/experiment_synthesis.py` (`ExperimentSynthesisStatus` 12 + `BaselineSetupReference`/`ParameterExperimentDelta`/`BoundedSetupExperiment`/`ExperimentSynthesisResult`; minimum-effective one-step `_round(baseline ± legal_step)` range-checked no-clamp, justified larger step bounded to 2; single-field default, coupled only when Phase-14 marked paired ≤2 fields REQUIRES_COUPLED_EXPERIMENT; `build_baseline_reference`/`synthesize_bounded_experiments`/`synthesize_from_report`), `strategy/experiment_synthesis_render.py` (numeric baseline vs candidate WITH provenance; no editable/Apply/optimal). Doctrine: baseline = canonical applied setup, blocks on missing/incomplete/mismatch/stale/drift (no fallback); wheelspin never auto-LSD; failed direction blocked; prior single-field regression → BLOCKED_BY_PRIOR_REGRESSION (physics kept); competing → CONDITIONAL discriminating only; unknown/conflicting gearbox → no gearing; count-only bottoming → no platform; aero low-speed → never ready; ties stay ties. Orchestrator `SessionDB.build_bounded_setup_experiments` (READ-ONLY; reuses `build_intervention_hypotheses` ONCE + `resolve_ranges` once — no N+1; applied setup from caller's ActiveSetupAuthority). UI: pure `ui/experiment_synthesis_vm.py` + `ui/experiment_synthesis_panel.py` (`ExperimentSynthesisPanel`, numeric shown, NO editable/Apply/Approve/Revert — asserted) embedded in Development History; build OFF Qt thread via reused `MechanismAnnotationWorker`; frozen Apply gate remains the only mutation route. **NEW suites `tests/test_phase15_{synthesis_domain,golden_uat,properties,safety,query_shape}.py` (98) + `tests/test_phase15_ui_construction.py` (5)** — baseline authority, minimum-step/legality/quantisation, single-field/coupled, direction+final-drive invariant, rendering, golden UAT A–R (incl. real SessionDB production path + restart), the 64 property/metamorphic invariants, no-AI/no-Qt-in-domain/no-DB-in-domain/no-shadow-authority/read-only, query-shape (single-aggregate reuse, no N+1, cheap empty, renderer-no-DB), UI construction + off-thread worker + no editable/Apply controls. NO version-guard bumps. Phase 12/13/14 (238) + frozen/no-AI/config/fan-out/session_db (80) + setup-state/selection/ranges (143) + broad non-UI strategy regression (1531) green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE15_MINIMUM_EFFECTIVE_EXPERIMENT_SYNTHESIS.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 14 — Mechanism-Constrained Intervention Hypotheses** — a deterministic READ-ONLY reasoning layer converting a valid Phase-13 `MechanismAnnotatedDiagnosis` into scientifically-defensible controlled-test DIRECTIONS constrained by the supported physical mechanism; branch `eng-brain-phase14-mechanism-constrained-interventions` (from `f3d4e90`, Phase-13 tip). A hypothesis is NOT a recommendation and NOT an authored change — never "set this value to X". NEVER authors a numeric value / applies / approves / persists; mutates no diagnosis/outcome/working-window/calibration/setup-history/active-setup; duplicates neither Phase-12 knowledge, the Phase-13 model, nor the Program-1 sign graph. No ML/stats/NLP/black-box/AI. **NO migration — `DB_VERSION` stays 25** (regenerable; restart-identical fingerprints), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/intervention_hypothesis.py` (`InterventionHypothesisStatus` 9 + `InterventionDirection` qualitative + `InterventionTestKind` + `InterventionTarget`/`ExpectedResponse`/`ControlledTestDesign`/`InterventionHypothesis`/`InterventionHypothesisSet`; direction from the canonical sign authority `explain_component(...).axis_effects` — never from the name — gearing via `gearbox_evidence` state + final-drive invariant; `build_intervention_hypotheses`/`hypotheses_from_report`), `strategy/intervention_hypothesis_render.py` (12 sections, no numeric values / Apply / approval). Doctrine: wheelspin NEVER auto-increases LSD locking; failed direction → BLOCKED_BY_WORKING_WINDOW (mechanism kept); prior single-field regression → CONTRADICTED_BY_OUTCOME (physics kept); confirmed outcome never proves a mechanism; coupled only from a prior coupled-improvement capped at 2 fields crediting the SET; aero needs speed context; count-only bottoming insufficient; unknown/conflicting gearbox → no direction; driver preference never overrides evidence/lockout. Orchestrator `SessionDB.build_intervention_hypotheses` (READ-ONLY; reuses `build_mechanism_annotations` ONCE — zero per-hypothesis/N+1 queries). UI: pure `ui/intervention_hypothesis_vm.py` + `ui/intervention_hypothesis_panel.py` (`InterventionHypothesisPanel`, NO Apply/Approve/Revert — asserted) embedded in Development History; build OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`. **NEW suites `tests/test_phase14_{intervention_domain,golden_uat,properties,safety,query_shape}.py` (79) + `tests/test_phase14_ui_construction.py` (5)** — direction/eligibility/mapping/coupled/test-design/rendering, golden UAT A–N (incl. real SessionDB production path + restart), the 40 property/metamorphic invariants, no-AI/no-Qt-in-domain/no-DB-in-domain/no-shadow-authority/read-only/versions, query-shape (single-aggregate reuse, no N+1, cheap empty, renderer-no-DB), UI construction + off-thread worker. NO version-guard bumps. Phase 12/13 (154) + frozen/no-AI/config/fan-out/session_db (80) + setup-synthesis/Program-1 (254) + broad non-UI strategy regression (1410) green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE14_MECHANISM_CONSTRAINED_INTERVENTIONS.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 13 — Mechanism-Annotated Diagnosis** — the strict bridge from Program 1 "what happened?" to Phase-12 "why could it have happened?"; branch `eng-brain-phase13-mechanism-annotated-diagnosis` (from `6010d5b`, Phase-12 tip). For an already-decided canonical Program-1 diagnosis it produces an auditable, evidence-linked explanation of the vehicle-dynamics MECHANISMS behind it (from the Phase-12 authority) and keeps the diagnosis UNCHANGED. NEVER decides observation/validity/recurrence/improvement/safety/selection; authors no setup value/delta/Apply/Revert; mutates no outcome/working-window/lockout/prediction-calibration; duplicates neither Phase-12 knowledge nor the Program-1 sign graph. No ML/stats/NLP/black-box/AI. **NO migration / NO persistence — `DB_VERSION` stays 25** (regenerates from immutable Phase-8 + Phase-11 records + static Phase-12 knowledge; restart-identical fingerprints), `RULE_ENGINE_VERSION` 46.0. NEW pure `strategy/mechanism_map.py` (structural `MechanismTemplate` table keyed by canonical `issue_type` → Phase-12 Component/HandlingPhase/TransferMode/interaction pairs; `resolve_handling_phase`), `strategy/mechanism_annotation.py` (`MechanismStatus` 9 states + `ConclusionKind`/`EvidenceGrade`/`EvidenceRelation` + `MechanismEvidenceLink`/`CausalMechanismCandidate`/`MechanismComparison`/`MechanismAnnotatedDiagnosis`; `annotate_diagnosis` eligibility→phase-resolve→Phase-12 query→support/contradiction→primary/secondary/competing/contradicted ranking→outcome+prediction reconcile; `annotations_from_memory`), `strategy/mechanism_annotation_render.py` (sectioned renderer; observation vs interpretation separated, no setup values/Apply wording). Doctrine: wheelspin primary = traction demand (TRANSMISSION) not auto-LSD; prior failed LSD direction flags the LSD candidate intervention `contradicted` (kept, never a cure); aero PLAUSIBLE without speed evidence; confirmed outcome never proves a mechanism; GT7-unavailable channels declared never fabricated. Orchestrator `SessionDB.build_mechanism_annotations` (READ-ONLY, writes nothing). UI: pure `ui/mechanism_annotation_vm.py` + `ui/mechanism_annotation_panel.py` (`MechanismAnnotationPanel`, structured cards, NO Apply/Revert — asserted) embedded in Development History; build runs OFF the Qt thread via `ui/mechanism_annotation_worker.py` (`MechanismAnnotationWorker(QThread)`). **NEW suites `tests/test_phase13_{mechanism_map,mechanism_annotation,golden_uat,properties,safety}.py` (97) + `tests/test_phase13_ui_construction.py` (6)** — knowledge-consumption, eligibility, support/contradiction, interactions, load-transfer, experiment+prediction relationship, rendering, golden UAT A–L (incl. real SessionDB production path + restart determinism), the 25 property/metamorphic invariants, no-AI/no-Qt-in-domain/no-DB-in-domain/no-sign-dup/no-invented-channel, UI construction + off-thread worker. NO version-guard bumps (no migration). Phase 8–12 (370) + broad strategy regression (734) green. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE13_MECHANISM_ANNOTATED_DIAGNOSIS.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain PROGRAM 2, Phase 12 — Deterministic Vehicle Dynamics Knowledge Engine** — a NEW read-only EXPLANATORY authority (not a replacement for Program 1); branch `eng-brain-phase12-vehicle-dynamics` (from `master` Phase 11 `0923f5c`). Explains the PHYSICAL MECHANISM behind each setup element ("what physical mechanism is creating this behaviour?"). NEVER creates experiments / ranks candidates / overrides evidence / modifies outcomes-memory-working-windows. No ML, no statistics, no NLP, no black-box scoring. **NO migration / NO persistence — `DB_VERSION` stays 25**, `RULE_ENGINE_VERSION` 46.0; the knowledge is static deterministic code (restart-identical fingerprints). CONSUMES Program-1 `setup_synthesis.PARAMETER_INTERACTIONS` as the SINGLE directional-sign source (never duplicates/contradicts it) and layers mechanism + GT7 knowledge on top. NEW pure `strategy/vehicle_dynamics.py` (`Component` 25 elements + `ComponentGroup` suspension/differential/aero/tyres/brakes/transmission/weight-transfer/alignment + `EngineeringExplanation` primary-mechanism/secondary-interactions/gt7-limitations/raise-lower-effect/axis-effects-from-graph; `explain_component`/`explain_change` [direction flips axis signs]/`build_knowledge_report`/`build_engineering_knowledge`), `strategy/load_transfer.py` (`TransferMode` longitudinal/lateral/combined/pitch/roll/yaw/platform + `LoadTransferRelation`), `strategy/handling_balance.py` (`HandlingPhase` corner-entry/trail-braking/initial-rotation/mid-corner/exit-traction/power-on-rotation/straight-line/high-speed + `PhaseExplanation` w/ key components + load-transfer modes + understeer/oversteer-if), `strategy/setup_interactions.py` (`ComponentInteraction` spring↔damper/damper↔ARB/ride-height↔aero/camber↔tyre/toe↔stability/diff↔suspension + `InteractionType` reinforcing/opposing/enabling/limiting + detailed LSD model [initial/accel/decel] + aero model [front/rear/ride-height/platform/high-speed]). GT7-specific behaviour modelled separately per component/mode/phase/interaction (bottoming, LSD response, tyre wear, aero ride-height gating, platform sensitivity). UI: pure `ui/engineering_knowledge_vm.py` + `ui/engineering_knowledge_panel.py` (`EngineeringKnowledgePanel` grouped by system, 13 tables, NO Apply controls — asserted); embedded in the existing Development History page (static reference, no DB call, no new tab). **NEW suites `tests/test_phase12_{vehicle_dynamics,models,view_model}.py` (36) + `tests/test_phase12_ui_construction.py` (3, individual)** incl. property (every component fully explained + GT7 note), metamorphic (raise/lower sign flip), consistency (axis effects exactly match Program-1 graph, all axes canonical), determinism/restart, golden knowledge assertions, safety (no setup-authoring/experiment-selection/mutation calls). NO version-guard bumps (no migration). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE12_VEHICLE_DYNAMICS.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain Phase 11 — Post-Flight Engineering Reconciliation & Prediction Calibration** — additive READ-ONLY OBSERVER ABOVE Phases 1-10; branch `eng-brain-phase11-postflight-reconciliation` (from `master` Phase 10 `fa9d1f4`). After a completed experiment, deterministically compares what the Brain PREDICTED (Phase-10 pre-flight) vs what ACTUALLY occurred (Phase-3 outcome + Phase-6 residuals). NEVER changes experiments / outcomes / memory / working windows / setup values — only compares expectation with reality. No AI, no prediction, no learning, no statistics. **SCHEMA: `user_version` 24 → 25** (`DB_VERSION = 25`; `_migrate_v25` + `_DDL_V25` add ONE additive, append-only, IMMUTABLE table `engineering_reconciliation_records`); `RULE_ENGINE_VERSION` unchanged (46.0). Migration justified (unlike Phases 9/10's regenerable no-migration): the prediction is a point-in-time input made BEFORE the experiment, NOT reliably regenerable after the outcome changes memory — so the calibration log persists. NEW pure `strategy/postflight_reconciliation.py` (`reconcile_consequences` → CONFIRMED/PARTIALLY_CONFIRMED/NOT_OBSERVED/CONTRADICTED/INSUFFICIENT_EVIDENCE/UNKNOWN per predicted consequence [primary ← target residual state, side-effect ← matching regression family, historical ← history-repeated, working-window ← window-held, interaction ← coupled family]; `ReconciliationRecord`+`build_reconciliation_record` idempotent record_key + time-independent fingerprint), `strategy/preflight_validation.py` (`validate_checklist` → every checklist item MATERIALISED/DID_NOT_MATERIALISE/INSUFFICIENT/N-A + `useful` flag: did the risk appear, did protected stay protected, did the interaction occur, did the regression happen, was confidence appropriate), `strategy/prediction_accuracy.py` (`compute_accuracy` → primary/side-effect/risk/constraint/historical-transfer/checklist accuracies + overall + confirmed/contradicted counts; plain deterministic ratios). Orchestrator `SessionDB.record_experiment_reconciliation` (append-only, idempotent, INSERT OR IGNORE, never UPDATE/DELETE, writes only its own log) + `get_reconciliation_records` + `build_prediction_calibration` (deterministic regenerable calibration summary). UI: pure `ui/postflight_review_vm.py` + `ui/postflight_review_panel.py` (`PostFlightReviewPanel`, NO Apply controls — asserted); embedded in the existing Development History page showing the aggregate prediction calibration (NO new tab). **NEW suites `tests/test_phase11_{reconciliation,validation,persistence,orchestrator,view_model}.py` (36) + `tests/test_phase11_ui_construction.py` (3, individual)** incl. all 6 reconciliation statuses, checklist materialised/did-not/useful, accuracy full/empty/deterministic, v25 migration, append-only immutability, restart-deterministic calibration fold, context isolation, writes-only-its-log, inputs-never-mutated, golden UAT through the real review_and_learn loop then reconcile prediction vs actual. Version guards advanced: group55-61 → guard v26; session_db/phase8-9-10 track `DB_VERSION`. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE11_POSTFLIGHT_RECONCILIATION.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain Phase 10 — Engineering Experiment Pre-Flight Review** — additive READ-ONLY OBSERVER ABOVE Phases 1-9; branch `eng-brain-phase10-preflight-review` (from `master` Phase 9 `b979be0`). Before the selected experiment is shown to the driver, performs a deterministic engineering pre-flight review of the EXACT Phase-5 selection. NEVER creates experiments / changes priorities-ranking / changes setup values / blocks recommendations / changes working windows / mutates evidence-memory-outcomes. No AI, no prediction, no statistical inference. **NO migration — `DB_VERSION` stays 24**, `RULE_ENGINE_VERSION` 46.0; the review is a deterministic regenerable function of the Phase-5 candidate + Phase-9 context + Phase-8 memory + canonical `PARAMETER_INTERACTIONS` (restart-identical fingerprints). NEW pure `strategy/change_consequences.py` (`derive_consequences` → PRIMARY_EFFECT [candidate's own interaction-graph positive effect] / SIDE_EFFECT [its coupled negatives] / HISTORICAL [Phase-9 successful/failed transfers w/ sessions] / WORKING_WINDOW / INTERACTION; `coupled_fields` derives coupling via shared handling axes — no new physics), `strategy/engineering_checklist.py` (`build_checklist` → ✓/⚠/? items [inside window, protected conflict, similar succeeded/failed, only-one-session, regression risks, coupled interaction, outstanding residuals] each w/ why+sessions+confidence+context; `RiskLevel` LOW/MODERATE/HIGH/UNKNOWN descriptive-only, never changes the recommendation), `strategy/preflight_review.py` (`build_preflight_review` echoes the EXACT selection verbatim + 12 fixed sections [evidence quality/working-window/protected impact/historical success+failure/regression risk/known constraints/interaction risks/coupled fields/driver familiarity/outstanding residuals/current state] + consequences + checklist + risk + time-independent fingerprint). Orchestrator `SessionDB.build_experiment_preflight` (read-only, NO persistence, writes nothing, NEVER blocks; builds Phase-9 context + Phase-8 memory for the proposed change). UI: pure `ui/preflight_review_vm.py` + `ui/preflight_review_panel.py` (`PreFlightReviewPanel`, NO Apply/approval controls — asserted); a compact pre-flight summary is surfaced beside the proposed experiment in the Setup Builder outcome flow (`_display_outcome_result`, guarded best-effort). NO new tab/migration. **NEW suites `tests/test_phase10_{change_consequences,engineering_checklist,preflight_review,orchestrator,view_model}.py` (40) + `tests/test_phase10_ui_construction.py` (3, individual)** incl. all 5 consequence kinds + coupled-fields, checklist items + risk LOW/MODERATE/HIGH/UNKNOWN, never-mutates-inputs, experiment-echoed-verbatim, section-emitted-only-when-content, restart-determinism, writes-nothing, no-selection→not-ok, golden UAT through the real review_and_learn loop then pre-flight a follow-up. NO version-guard bumps (no migration/tab change). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE10_PREFLIGHT_REVIEW.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain Phase 9 — Cross-Context Engineering Transfer & Regression Risk Intelligence** — additive READ-ONLY OBSERVER ABOVE Phases 1-8; branch `eng-brain-phase9-context-transfer` (from `master` Phase 8 `da53569`). Before an experiment is proposed, surfaces every relevant lesson from COMPATIBLE historical contexts. REPORTS ONLY — evaluates no evidence, creates/chooses no experiment, modifies no working window, mutates nothing, NEVER BLOCKS. No AI, no prediction, no probability. **NO migration — `DB_VERSION` stays 24**, `RULE_ENGINE_VERSION` 46.0; transfers/constraints/risks are deterministic regenerable FOLDS over the immutable Phase-8 `engineering_development_records` (restart-identical fingerprints). NEW pure `strategy/context_transfer.py` (5-tier fixed hierarchy `classify_context_match` → DIRECT/STRONG/RELATED/WEAK/UNKNOWN, incompatible contexts EXCLUDED not mixed, every match states WHY + which sessions/experiments; `EngineeringTransfer` SUCCESSFUL/FAILED_EXPERIMENT/STABLE_WINDOW/PROTECTED_BEHAVIOUR/KNOWN_UNSTABLE/INEFFECTIVE_DIRECTION ranked strongest-first + confirmed-vs-provisional; folds per-context memory via Phase-8 `build_history`/`build_engineering_memory` — no duplicated logic; RELATED needs real `cars.category` class data, never guesses), `strategy/engineering_constraints.py` (`derive_constraints` folds per-record Phase-8 protected-knowledge + protected-behaviours → `EngineeringConstraint` w/ evidence source + supporting sessions/experiments + times-reinforced; confirmed = high-conf + ≥2 sessions + ≥STRONG match), `strategy/regression_risk.py` (`assess_regression_risk` NEVER blocks → KNOWN_FAILED_DIRECTION/PREVIOUSLY_UNSTABLE_RANGE/PROTECTED_FIELD_CONFLICT/WORKING_WINDOW_EDGE/REPEATED_REGRESSION/CONFIDENCE_WEAKNESS w/ HIGH/MED/LOW/INFO severity; works with or without a proposed change). Orchestrator `SessionDB.build_engineering_context` (read-only, NO persistence, writes nothing; car classes from `cars.category`; candidate pool = car OR track OR driver) + `get_development_records_for_context_search` + `_car_class_map`. UI: pure `ui/engineering_context_vm.py` + `ui/engineering_context_panel.py` (`EngineeringContextPanel`, NO Apply/decision controls — asserted); embedded in the existing Development History page (NO new tab, NO registry change). **NEW suites `tests/test_phase9_{context_transfer,constraints,regression_risk,orchestrator,view_model}.py` (36) + `tests/test_phase9_ui_construction.py` (3, individual)** incl. full matching hierarchy, RELATED-needs-class, incompatible-excluded, transfer ranking + order-invariance, constraint provenance + confirmed-vs-provisional, all 6 risk kinds, never-blocks/empty-safe, restart-determinism, writes-nothing, golden UAT through the real review_and_learn loop. NO version-guard bumps (no migration/tab change). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE9_CONTEXT_TRANSFER.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain Phase 8 — Cross-Session Engineering Development Memory & Driver Progress Intelligence** — additive; the permanent engineering memory ABOVE Phases 1-7; branch `eng-brain-phase8-development-memory` (from `master` Phase 7 `dfc70a9`). Answers "what have we learned over every previous session?" — NOT "what happened today?". DECIDES NOTHING: no experiment selection, no setup authoring, no lap evaluation, no evidence mutation, no history rewriting. NO AI, no network, no prediction. **SCHEMA: `user_version` 23 → 24** (`DB_VERSION = 24`, `_migrate_v24` + `_DDL_V24`: ONE additive append-only IMMUTABLE table `engineering_development_records`); `RULE_ENGINE_VERSION` unchanged (46.0). Migration justified (unlike Phases 4/6/7): the memory context key needs driver/gt7_version/compound, only fully known at review time — so the immutable record is captured WITH its full context; memory/metrics are deterministic FOLDS over the stored record_json (regenerable → restart-identical fingerprints). NEW pure `strategy/development_history.py` (`MemoryContextKey` driver/car/track/layout/discipline/gt7/compound — incompatible contexts NEVER merge; `DevelopmentRecord` idempotent `record_key` + time-independent `content_fingerprint`, captures changes/residual-states/improvements/regressions/protected-behaviours/working-window-snapshot/derived protected-knowledge `ConstraintKind` NEVER_MOVE_DIRECTION/NEVER_BELOW/NEVER_ABOVE/PREFERRED_RANGE/KNOWN_UNSTABLE/PROTECTED_BEHAVIOUR; `build_history` chronological+dedup; `build_timeline`), `strategy/engineering_memory.py` (`IssueMemory` recurrence/resolved/fix-history + `WorkingWindowEvolution` + `ProtectedKnowledgeItem` reinforced + `EngineeringMemory` fold), `strategy/progress_metrics.py` (`numeric_trend` single-session-never-flips; `ProgressMetrics` success/resolution rate + recurring-reduced + convergence + brake/entry/exit/driver/confidence trends + velocity/efficiency; `EngineeringScorecard`+`ScorecardBand`; `SessionComparison`+`compare_latest_sessions`). Orchestrators `SessionDB.record_engineering_development` (append-only, idempotent, INSERT OR IGNORE, never UPDATE/DELETE) wired into `review_and_learn` (best-effort) + `build_cross_session_memory`/`build_development_history`/`get_development_records` (read-only folds). UI: pure `ui/development_history_vm.py` + `ui/development_history_page.py` (`DevelopmentHistoryPage`, NO Apply/Save/Revert — asserted); NEW **"Development History" tab** (index 12) wired via `dashboard.py`+`tab_registry.py`+`product_flow.py` (13 tabs). **NEW suites `tests/test_phase8_{development_history,engineering_memory,progress_metrics,persistence,golden_uat,view_model}.py` (50) + `tests/test_phase8_ui_construction.py` (3, individual)** incl. time-independent+idempotent record, append==no-rewrite immutability, restart-determinism, context isolation (different compound → 0 records), single-session-never-flips, golden UAT through the real review_and_learn loop (Porsche RSR @ Fuji, multi-session), observer-writes-nothing. Version guards advanced: group55-61 → guard v25; `test_session_db`/`test_phase5_persistence`/`test_phase6_golden_uat` track `DB_VERSION`; tab registry/count → 13. Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE8_DEVELOPMENT_MEMORY.md`.)
>
> Prior: 2026-07-19 (**Engineering Brain Phase 7 — Live Engineering State Monitor & Session Development Ledger** — additive READ-ONLY OBSERVER; branch `eng-brain-phase7-live-state-monitor` (from `master` Phase 6 `abfa14b`). **NO migration — `DB_VERSION` stays 23**, `RULE_ENGINE_VERSION` unchanged (46.0); the live state + ledger are a deterministic regenerable function of persisted `corner_issue_occurrences` + the Phase-4 lap-validity authority (proven by restart-determinism UAT). Phase 7 DECIDES NOTHING — no experiment selection, no evidence scoring, no lap evaluation, no setup authoring, no working-window mutation, no candidate reordering. NEW pure `strategy/state_transitions.py` (Trend `IMPROVING/UNCHANGED/WORSENING/FLUCTUATING/INSUFFICIENT_EVIDENCE` + IssueStatus `UNKNOWN/NEW/ACTIVE/RECOVERING/STABLE/RESOLVED/PROTECTED/DAMAGED`; `detect_trend` window-fraction over valid laps only with a ≥2-lap support rule so ONE exceptional lap can never flip a trend; `next_status` recovery/regression/protected paths), `strategy/live_engineering_state.py` (`LiveIssueState`+`ConsistencyMeasures` engineering-measurements-not-driver-ratings+`SessionHealth`/`SessionHealthBand`+`LiveEngineeringState` w/ time-independent fingerprint; `update_live_state` pure order-independent fold, excluded/non-comparable laps never count), `strategy/session_development.py` (append-only immutable `SessionDevelopmentLedger`; positional `sequence_no` never a timestamp; `append_snapshot` returns NEW ledger; `build_session_ledger` byte-equal to incremental append). Orchestrator `SessionDB.build_live_engineering_state` (read-only, NO persistence, writes nothing). UI pure `ui/live_engineering_vm.py` (health rows, issue tables, per-lap `▇/·` trend sparkline, timeline) + `ui/live_engineering_monitor.py` (`LiveEngineeringMonitor` widget, NO Apply/Save/Revert controls — asserted); `dashboard.py` untouched. **NEW suites `tests/test_phase7_{state_transitions,live_state,ledger,orchestrator,view_model}.py` (55 passed) + `tests/test_phase7_ui_construction.py` (3, run individually)** incl. single-lap-no-flip (both directions), append==rebuild, restart-determinism, order-invariance metamorphic, pit/out-lap exclusion, golden resolution timeline, observer-writes-nothing, no-Apply-control. NO version-guard bumps (no migration); no new table (`live_engineering*`/`development_ledger*` asserted absent). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE7_LIVE_STATE_MONITOR.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 6 — Live Residual-Issue Detection & Multi-Symptom Experiment Planning** — additive; branch `eng-brain-phase6-residual-experiment-planning` (from `master` Phase 5 `535aed9`). **NO migration — `DB_VERSION` stays 23**, `RULE_ENGINE_VERSION` unchanged (46.0); the plan is a deterministic regenerable function of the Phase-3 outcome + Phase-5 windows (proven by restart-determinism UAT). NEW pure `strategy/engineering_issue.py` (canonical issue identity excluding display text + 12-state residual taxonomy; RESOLVED gated on adequate comparable evidence; NEW needs authorable test recurrence), `strategy/engineering_state.py` (`EngineeringStateSnapshot` w/ time-independent fingerprint), `strategy/experiment_planning.py` (priority precedence + hard exclusion, conflict detection, rule-based clustering, `build_development_plan` w/ ONE immediate + queued hypotheses + invalidation triggers). Orchestrator `SessionDB.build_engineering_plan` (regenerable, no persistence); `review_and_learn` returns `engineering_plan`; off-thread; UI renders state+plan (advisory). Reuses Phase 3 outcome (re-classified), Phase 4 assembly/decision, Phase 5 selector (no competing selector). **NEW suites `tests/test_phase6_{residual_detection,priority_planning,golden_uat,wiring}.py` (70 passed)** incl. golden UAT A/B/F/G/J/L (one-resolved-one-remains, new-regression-prioritised, failed-LSD-blocked, one-off-lap-excluded, no-change-justified, restart-determinism). NO version-guard bumps (no migration). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE6_RESIDUAL_EXPERIMENT_PLANNING.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 5 — Working-Window Learning, Successful-Direction Reinforcement & Minimum-Effective Experiment Selection** — additive; branch `eng-brain-phase5-working-window-learning` (from `master` Phase 4 `52628af`). **SCHEMA: `user_version` 22 → 23** (`DB_VERSION = 23`); `RULE_ENGINE_VERSION` unchanged (46.0). NEW pure `strategy/working_window.py` (learned window = deterministic function of an append-only evidence ledger; confidence never over-claims; regression locks direction, never averaged), `strategy/experiment_selection.py` (physics-informed one-field-one-step candidates via the interaction graph, HARD dead-end gates, 5-stage deterministic selection subordinate to `resolve_setup_decision`, honest no-selection, test protocol). EXTENDED `corner_evidence.py` (`from_corner_slip_aggregate` + `unify_corner_observations` — dedup by stable identity, slip can't inflate recurrence, unlinked ineligible). MIGRATED `practice_capture.resolve_clean_lap` → adapter over the ONE `engineering_lap_validity` authority (behaviour preserved). Additive DB v23 (`_migrate_v23`, idempotent): `setup_working_window_evidence` (UNIQUE triple → idempotent) + `setup_working_windows` (materialised). Orchestrators `learn_from_experiment_outcome`/`select_next_experiment`/`review_and_learn`; off-thread review worker rewired. **NEW suites `tests/test_phase5_{working_window,experiment_selection,corner_unification,lap_validity_migration,persistence,golden_uat,wiring}.py` (95 passed)** incl. golden UAT A-J through the production loop. Version-guard tests bumped (`test_session_db`→23, group55-61 ceiling→v24, Phase 3/4 version tests→DB_VERSION). Golden `config_id` + frozen fan-out allowlist + Apply-gate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE5_WORKING_WINDOW_LEARNING.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 4 — Canonical Evidence Authorities, Unified Clean-Lap Semantics & Live Per-Corner Outcome Assembly** — additive; branch `eng-brain-phase4-canonical-evidence` (from `master` Phase 3 `6314c05`). **NO migration — `DB_VERSION` stays 22**, `RULE_ENGINE_VERSION` unchanged (46.0); existing `corner_issue_occurrences` (session+checkpoint keyed, live-populated) provides sufficient durable linkage. FOUR pure authorities: `strategy/engineering_lap_validity.py` (VALID/VALID_WITH_LIMITATIONS/INVALID/UNRESOLVED + purpose policy; unifies the 6 scattered clean-lap rules; all rejection reasons retained), `strategy/corner_evidence.py` (canonical per-corner observation + recurrence REUSING practice_pattern RecurrenceThresholds; excluded events/raw-count never inflate recurrence; no invented channels), `strategy/setup_evidence_assembly.py` + SessionDB `assemble_setup_experiment_evidence`/`review_experiment_outcome` (baseline/test selection RESOLVED/PARTIAL/AMBIGUOUS/MISSING/INCOMPATIBLE — never picks newest; production per-corner assembly), `strategy/setup_decision_status.py` `resolve_setup_decision` (13 driver-facing states; contradictions→INVALID). Dormant `arbitrate_setup_decision` formally deprecated (unwired). Off-thread 'Review Test Outcome' rewired to `review_experiment_outcome` (closes Phase-3 live per-corner gap). **NEW suites `tests/test_phase4_{lap_validity,corner_evidence,evidence_assembly,setup_decision,golden_uat}.py` (86 passed)** incl. 3 Fuji RSR golden cases (confirmed/regression/insufficient) through the production assembly path. NO version-guard bumps needed (no migration). Golden `config_id` + frozen fan-out allowlist + Apply-gate predicate + engine-wiring-status UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE4_CANONICAL_EVIDENCE.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 3 — Closed-Loop Outcome Evaluation, Regression Detection & Failed-Direction Learning** — additive; branch `eng-brain-phase3-outcome-evaluation` (from `master` Phase 2 `b6f6dd4`). **SCHEMA: `user_version` 21 → 22** (`DB_VERSION = 22`); `RULE_ENGINE_VERSION` unchanged (`46.0`). NEW pure `strategy/setup_experiment_outcome.py`: 6 outcome states + deterministic `evaluate_outcome`, evidence-association resolver (resolved/ambiguous/mismatch/unresolved), lap-validity gate, median whole-lap + per-corner recurrence comparison, primary-target + supporting criteria, protected-behaviour enforcement, driver/telemetry arbitration, `build_failed_direction_learning` (lockout/caution/none). Additive DB v22 (`_migrate_v22`, idempotent): five standalone `setup_experiment_outcome*` + `setup_experiment_failed_directions` tables; immutable outcome (audit-only supersede/invalidate); atomic create w/ ROLLBACK. `has_outcome_record` now gates COMPLETED honestly. Orchestrator `evaluate_setup_experiment` drives the lifecycle + feeds existing lockout/rollback consumers. Off-thread 'Review Test Outcome' UI seam (read-only). **NEW suites `tests/test_setup_outcome_{domain,persistence,integration,golden_uat}.py` (79 passed)** incl. 2 Fuji RSR golden scenarios (confirmed→completed→no-lockout; protected regression→rejected→scoped lockout). Version-guard tests updated (`test_session_db`→22, `test_setup_experiment_persistence`→DB_VERSION, group55–61 migration ceiling → v23). Golden `config_id` + frozen fan-out allowlist + Apply-gate predicate UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE3_OUTCOME_EVALUATION.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 2 — Persisted Setup Experiments & Recommendation Evidence Ledger** — additive; branch `eng-brain-phase2-setup-experiments` (from `master` `3d7c6af`, Phase 1 fast-forwarded onto master). **SCHEMA: `user_version` 20 → 21** (`DB_VERSION = 21`); `RULE_ENGINE_VERSION` unchanged (`46.0`). NEW pure `strategy/setup_experiment.py`: `SetupExperiment` domain (enums + frozen models), deterministic `validate_transition` (honesty gates: APPLIED needs checkpoint, READY_FOR_REVIEW needs test evidence, COMPLETED needs a Phase-3 outcome), `compare_proposed_vs_applied` (MATCH/PARTIAL_MATCH/MISMATCH/UNVERIFIABLE), timestamp-free `compute_idempotency_key`, `build_experiment_from_recommendation` (None when not actionable). Additive DB v21 (`_migrate_v21`, idempotent): six standalone `setup_experiment*` tables; atomic create w/ full ROLLBACK; append-only evidence + state history. Wired at Setup Builder Analyse (`_display_setup_result`, analyse-only; baseline Build explicitly excluded) + Apply (`_on_changes_applied_in_game`). Every experiment references the Phase 1 `scope_fingerprint`. **NEW suites `tests/test_setup_experiment_{domain,persistence,integration}.py` (80 passed).** Version-guard tests updated (`test_session_db`→21, `test_engineering_context_bridge`→DB_VERSION, group55–61 migration ceiling → v22). Golden `config_id` vector + frozen fan-out allowlist + Apply-gate predicate UNCHANGED. Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE2_SETUP_EXPERIMENTS.md`.)
>
> Prior: 2026-07-18 (**Engineering Brain Phase 1 — Canonical Engineering Context & Identity Bridge** — additive; branch `eng-brain-phase1-canonical-context` (from `master` `c611d79`). Architecture/data-foundation only. **SCHEMA: `user_version` 19 → 20** (`DB_VERSION = 20`, `strategy/_setup_constants.py`); `RULE_ENGINE_VERSION` unchanged (`46.0`). NEW pure module `data/engineering_context_key.py`: `EngineeringContextKey` (13 `Optional[str]` identity components, `None`=genuinely-unknown), versioned FULL `fingerprint()` + STABLE `scope_fingerprint()` (driver/car/track_location/layout/gt7 join key), `EngineeringContextResolution` (status COMPLETE/PARTIAL/AMBIGUOUS/UNRESOLVED/INVALID + per-field provenance + unresolved/ambiguous/warnings), resolvers for session/checkpoint/lineage/feedback, honest ambiguity (free-text track never invents a layout), enrichment without contradictory duplicates. Additive DB v20 (`_migrate_v20`, idempotent): standalone `engineering_context` (UNIQUE fingerprint) + `engineering_context_links` (bridge `(source_kind, source_id)`→fingerprint). Wired best-effort at `open_session`/`save_applied_checkpoint`/`record_lineage`/`write_feedback`. **NEW suites `tests/test_engineering_context_key.py` + `tests/test_engineering_context_bridge.py` (62 passed).** Version-guard tests updated (`test_session_db` → 20; `test_group55–61` migration-hook ceilings → v21). **Regression (run in chunks per the documented Win/Py3.14 PyQt teardown segfault): non-UI 5408+ passed / 0 new failures; UI files individually green.** Golden `config_id` vector + frozen fan-out allowlist UNCHANGED. Pre-existing failure noted (unrelated to Phase 1): `test_diagnostic_tab_cleanup::test_dead_imports_removed` (`_seg_rename` dead alias in `ui/track_modelling_ui.py`, present on `master`). Runtime files git-verified untouched. Doc: `docs/ENGINEERING_BRAIN_PHASE1_CANONICAL_CONTEXT.md`.)
>
> Prior: 2026-07-13 (**Group 64 — Setup-Authoring Architecture & Discipline Intelligence Remediation** — additive; branch `group64-setup-authoring-discipline-intelligence` (from `master` `9d2b276`). **The manual UAT after Group 63 still produced near-identical Base/Quali/Race setups + a lone ARB change labelled "approved" + a contradictory bottoming state + a weak `gear_too_short_spin` + proven values that never reached authoring.** Group 63 fixed the incremental evidence pipeline; the remaining failures were structural. NEW `strategy/setup_authoring.py` (PURE): `SetupObjective` (BASE/QUALIFYING/RACE, first-class), immutable `SetupAuthoringContext`, documented `EVIDENCE_PRECEDENCE`, `FieldDisposition` (11 states), `author_full_field_plan` (full-field plan + a disposition for EVERY adjustable field + objective-specific per-field justification), `author_discipline_setups`, `objective_from_session_type`. RC1 discipline: `discipline_field_plan` surface on `build_baseline_setup_response` — Base/Quali/Race authored separately from ONE context (rows = base/quali/race value + `differs` + disposition + proven); RSR diverges ≥9 fields. RC2 history→authoring: `build_baseline_seed_overrides` lifts the LSD triplet (geometry tier ≤2, LSD tier ≤3 cross-track starting window) marked PROVEN_HISTORY_SEED; aero/brakes/gearing/ride-height still never lifted. RC3 bottoming: `_bottoming_display_state` reconciles count band + consequence impact into ONE canonical `diagnosis["bottoming_display_state"]`; UI header renders it (no "required"+"normal"). RC4 wheelspin: `_classify_wheelspin_subtype(location_trustworthy, driver_says_gearing_too_long)` gates `gear_too_short_spin` → weak becomes `unknown` (test), contradiction `conflicting_evidence`. RC5 completeness: `RECO_*` states + `assess_recommendation_completeness` wired into `build_combined_setup_response` → `recommendation_completeness` + downgrade plain-approved→`partial_recommendation` when confirmed problems (incl. telemetry wheelspin + secondaries) are untreated; `wheelspin` arms the finaliser gate; UI Section 18 completeness panel. Constants: NONE (`RULE_ENGINE_VERSION` unchanged, `user_version` 14). Schema/migrations: NONE. New suites `tests/test_group64_setup_authoring.py` (13) + `tests/test_group64_uat_integration.py` (12); updated `test_group39` (wheelspin gate) + `test_followups_history_lift_candidates` (LSD lift). **Full suite run in halves (documented Win/Py3.14 PyQt full-run segfault): 4755 + 2592 = 7347 passed, 32 skipped, 0 failed.** Safety spine intact: deterministic/rule-first/AI-audit-only; AI never authors/validates-invalid/bypasses-Apply; no auto-Apply; disabled AI-build stays disabled; Strategy-Brain authority untouched; runtime files (`data/setup_history.json`, `data/track_models/*`) NOT staged (modified by the manual UAT before this work). Docs: `docs/AUDIT_setup_brain_group64.md`, `docs/UAT_setup_brain_group64.md`.)
> Prior: 2026-07-08 (**Group 61 — Raw Live Packet Road Distance Semantics Capture & Stateful Live Progress Stabiliser Wiring** — read-only, advisory-only; branch `group61-raw-live-road-distance-semantics-stabiliser-wiring` (from clean `master` `1e86ef7`). **Added a read-only raw live-packet road_distance capture workflow (to finally settle the field's LIVE semantics via a manual ≥3-lap UAT), a NON_DISTANCE_LIKE verdict, and wired the Group 60 stabiliser into a stateful DISPLAY-ONLY live path — without changing production strategy/pit/fallback behaviour.** NO new live semantics confirmed this sprint (real in-game raw capture is a manual step); the shipped Fuji/Daytona captures now classify as NON_DISTANCE_LIKE (per-lap span ~117/~430 m ≪ lap length); production fallback UNCHANGED, promotion still gated on a CONFIRMED raw capture. No pit calls, no commands, no voice, no auto-refresh, no schema migration. 1 NEW pure module + 4 NEW test files + additive wiring. NEW `data/live_road_distance_capture.py` (PURE, Qt/DB/AI/file-write-free, never raises): `LiveRoadDistanceCapture` accumulates raw packet samples (road_distance + pos + speed + lap markers), counts valid/invalid/missing/negative/no-lap, emits laps[] for the Group 60 analyser; `add_packet` read-only (never mutates packet); impossible None/NaN/inf counted-not-stored, negatives kept+flagged; `analyse_live_capture` delegates to Group 60. Added `RoadDistanceSemanticsStatus.NON_DISTANCE_LIKE` (additive) + `CaptureAnalysisResult.capture_status` (promotes to NON_DISTANCE_LIKE when span_covers_lap is False; `.status` unchanged, `.confirmed` now also requires span covers lap). `LiveProgressStabiliserState` holder (retains prev progress, AUTO-RESETS on track|layout|car identity change; never changes value, never inflates, no pit contact). `build_live_replan_snapshot` gained `stabiliser_state` → stabilisation computed AFTER apply_pit_lane_evidence, stored as display fields `stabilised_confidence`/`stabiliser_notes`/`stabiliser_jumped` on LiveReplanResult; **pit corroboration keeps using RAW track_progress, byte-for-byte unchanged**; no-state callers identical. Render adds a "position stability"/"stabilised progress confidence (jitter guard)" line only on downgrade/continuity. Dashboard holds `_live_stabiliser_state` (lazy) + OFF-by-default `_raw_rd_capture` (single guarded read-only feed line in `_poll_ui_queue`, inert when None) + `start_/stop_/raw_road_distance_capture_report` methods. UAT: `run_raw_live_capture_uat(kind)` + `build_raw_live_capture_fixture` + `save_raw_capture_to_path(capture, path)` (writes ONLY to an explicit path — pure module writes nothing). Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group61_{live_road_distance_capture, live_road_distance_semantics, stabiliser_wiring, safety_invariants}.py` — **43 pure/offline tests, all pass ~1 s** (1 Group 60 report-label assertion loosened). Safety: new pure modules no Qt/AI/DB import + no file writes; no api_key; no setup-authoring; fallback never HIGH / never lifts pit / never mutates pit count; a jumped (downgraded) frame does NOT change pit_corroboration/pit_evidence vs a stable frame; global nearest wins over a bad hint (crossing fixture); state resets across identities; Apply-gate + disabled AI-build intact; `user_version` 13; Group 48/49 deterministic; calibration capture files byte-identical. Regression: Group 55–61 (389), Group 48/49/53/54 + telemetry state/pit + reference/track (992), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files git-verified untouched. `docs/UAT_RACE_STRATEGY.md` + `docs/TRACK_LIBRARY_SCHEMA.md` updated. See "Raw Live Packet Road-Distance Capture & Stateful Stabiliser Wiring (Group 61)" at the end of this file.)
> Prior: 2026-07-07 (**Group 60 — Real Capture Road Distance Semantics UAT & Correctness-Preserving Live Progress Stabilisation** — read-only, advisory-only; branch `group60-road-distance-semantics-uat-progress-stabilisation` (from clean `master` `2a94780`). **Ran the Group 59 validator against the repo's REAL multi-lap calibration captures + added a correctness-preserving live-progress stabiliser (pure, tested, NOT force-wired) — without changing production live behaviour.** HONEST FINDING: the shipped Fuji + Daytona captures do NOT confirm cumulative road_distance semantics (Fuji → INSUFFICIENT_EVIDENCE, Daytona → INCONSISTENT) — the captured field spans only ~117 m (Fuji) / ~430 m (Daytona) per lap, far below the ~4441/~5420 m lap lengths, so it does NOT measure cumulative lap distance in this post-processed calibration data; the report says so and refuses to confirm; the live fallback's cumulative assumption stays unvalidated (already capped + disclosed). Still needs a RAW-live-packet capture UAT to settle true live semantics. No pit calls, no commands, no voice, no auto-refresh, no schema migration. 2 NEW pure modules + 4 NEW test files + 1 additive UAT helper. NEW `data/road_distance_capture_analysis.py` (PURE, Qt/DB/AI/file-write-free, never raises): `extract_lap_observations` (per-lap start/end/min/max/span/sample-count; skips <2 finite samples, ignores NaN/inf, tolerates missing lap numbers), `analyse_capture_road_distance` (→ Group 59 RoadDistanceSample → analyse_road_distance_semantics + span-vs-lap-length red flag + clear next_action), `build_capture_report` (human-readable, NO false-certainty). Thin READ-ONLY loaders `load_capture_laps_from_calibration_file` + `analyse_calibration_capture` (via resolve_trusted_lap_length). Confirms nothing the validator doesn't. NEW `data/live_progress_stabiliser.py` (PURE): `nearest_station_stabilised` ALWAYS returns GLOBAL nearest (full scan = correctness anchor; local continuity window only sets continuity_ok, NEVER overrides — safe on crossings/hairpins/chicanes/parallel sections); `stabilise_progress` NEVER changes the reported progress value and ONLY downgrades confidence (cap LOW) on an implausible jump (lap-wrap aware, near-zero backward jitter tolerated), NEVER inflates, fallback never HIGH, touches NO pit state. Goal 2 honored: nothing confirmed → NO production fallback behaviour changed; stabiliser tested but NOT force-wired (snapshot builder stateless; wiring needs stateful live loop → deferred). `ui/race_strategy_uat.py::run_real_capture_road_distance_uat(kind)` — real fuji/daytona + synthetic cumulative/reset/inconsistent/insufficient/unknown/empty through the SAME analyse_capture_road_distance path. NO change to strategy/race_strategy_live_replan.py, data/live_track_progress.py, data/live_track_progress_fallback.py, telemetry/state.py, or ui/dashboard.py. Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group60_{road_distance_capture_analysis, capture_uat_helper, progress_stabilisation, safety_guards}.py` — **55 pure/offline tests, all pass ~1.6 s.** Safety: new pure modules no Qt/AI/DB import + no file writes (read-only Path.read_text); no api_key; no setup-authoring; approved path wins; fallback never HIGH / never lifts pit / never mutates pit count; global nearest always wins over a bad hint (crossing/parallel fixture); implausible jump downgrades never inflates; Fuji capture file byte-identical after analysis; Apply-gate + disabled AI-build intact; `user_version` 13; Group 48/49 deterministic. Regression: Group 55–60 (346), Group 48/49/53/54 + telemetry state/pit + reference/track (960), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files git-verified untouched. `docs/UAT_RACE_STRATEGY.md` + `docs/TRACK_LIBRARY_SCHEMA.md` updated. See "Real-Capture Road-Distance Semantics & Progress Stabilisation (Group 60)" at the end of this file.)
> Prior: 2026-07-07 (**Group 59 — Approved Reference Path Asset Expansion & Road Distance Semantics Validation** — read-only, advisory-only; branch `group59-reference-path-assets-road-distance-validation` (from clean `master` `f8dd70c`). **Adds a deterministic validator for GT7 `road_distance` zero-point semantics + hardens the reference-path asset registry + honestly discloses the fallback's unvalidated cumulative assumption**, without inventing data or raising confidence. **NO new production reference-path assets added** — the repo already ships TWO trustworthy calibration-sourced approved paths (Fuji Full Course + Daytona Road Course, 200 stations each, Porsche RSR, conf 1.0), both already loading/registering/resolving trusted lap length; Group 59 verified + hardened the foundation rather than fabricating any. No pit calls, no commands, no voice, no auto-refresh, no schema migration. 1 NEW pure module + 5 NEW test files + additive registry-validator/render/UAT wiring. NEW `data/road_distance_semantics.py` (PURE, Qt/DB/AI/file-write-free, never raises): `RoadDistanceSample`/`RoadDistanceLapEvidence`/`RoadDistanceSemanticsResult` + `RoadDistanceSemanticsStatus` (CUMULATIVE_CONFIRMED / PER_LAP_RESET_CONFIRMED / INCONSISTENT / INSUFFICIENT_EVIDENCE / UNKNOWN); `build_lap_evidence` + `analyse_road_distance_semantics` + `format_road_distance_semantics`. Rejects NaN/inf, tolerates missing lap numbers (positional), flags negative deltas, compares per-lap delta to a TRUSTED lap length (5% tol, only when given), needs ≥2 laps, NEVER assumes the answer. Validator does NOT change live behaviour automatically — the live render only adds an HONEST disclosure that the fallback ASSUMES cumulative semantics ("road-distance semantics: cumulative behaviour assumed from lap-start reference" / "zero-point validation: insufficient evidence (per-track validation pending)") + a capped-confidence warning. `data/reference_path_loader.py` gained `validate_reference_path_candidate(path, *, expected_track_id, expected_layout_id)` → {ok, errors, warnings, track_id, layout_id, station_count, lap_length_m, source} with clear errors for missing ids / <2 stations / bad JSON / identity mismatch. `ui/race_strategy_uat.py::run_road_distance_semantics_uat(kind)` offline helper. Precedence unchanged: approved map match (MEDIUM/HIGH) wins → fallback (never HIGH, never lifts pit, excluded from pit-lane corroboration by source) → honest missing. NO telemetry/state.py or dashboard.py change (Group 58 already exposes live_lap_distance/live_road_distance + wires fallback inputs). Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group59_{reference_path_assets, road_distance_semantics, live_replan_semantics_render, fallback_quality_guards, safety_guards}.py` — **58 pure/offline tests, all pass ~0.7 s.** Safety: semantics no Qt/AI/DB-write/file import; new modules no api_key + no setup-authoring; approved path wins; fallback never HIGH / never lifts pit / never creates a pit / never mutates pit count; Fuji reference file byte-identical after analysis; Apply-gate + disabled AI-build intact; `user_version` 13; Group 48/49 scoring deterministic. Regression: Group 53–59 (424), Group 48/49 + telemetry state/pit + reference/track (973), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files git-verified untouched. `docs/UAT_RACE_STRATEGY.md` + `docs/TRACK_LIBRARY_SCHEMA.md` updated. See "Reference Path Assets & Road-Distance Semantics Validation (Group 59)" at the end of this file.)
> Prior: 2026-07-07 (**Group 58 — Road Distance Fallback & Reference Path Asset Expansion Foundation** — read-only, advisory-only; branch `group58-road-distance-fallback-assets` (from clean `master` `0d09217`). **Adds a safe, lower-confidence fallback for live track progress when no approved reference path exists** (GT7 cumulative `road_distance` + a TRUSTED lap length → approximate normalised progress), plus a reference-path asset registry foundation. No pit calls, no commands, no voice, no auto-refresh, no schema migration. 1 NEW pure module + 5 NEW test files + additive tracker/precedence/render/registry wiring. NEW `data/live_track_progress_fallback.py` (PURE, Qt/DB/AI/file-write-free, never raises): `resolve_progress_from_road_distance(*, lap_distance_m, road_distance, lap_length_m, identity_ok, track_id, layout_id)` → Group 56 `LiveTrackProgressResult` tagged `source="road_distance_fallback"`. **Confidence NEVER HIGH:** MEDIUM = accurate in-bounds per-lap distance + trusted lap length + known identity; LOW = wrapped value or cumulative-road_distance-only; UNKNOWN = missing/invalid/NaN/inf/negative or identity mismatch. `format_road_distance_fallback_evidence` + `is_fallback_result`. PRECEDENCE (build_live_replan_snapshot): usable MEDIUM/HIGH approved map match wins → else fallback if it yields progress → else honest LOW/UNKNOWN; fallback NEVER overrides a usable map match. Fallback is DISPLAY-ONLY for pits: `apply_pit_lane_evidence` excludes fallback-source progress from pit-lane corroboration → fallback can never lift pit confidence, creates no pit event, mutates no pit count. Tracker: `road_distance` is cumulative so a `_road_distance_lap_start` reference is captured at each lap start (PRE_RACE/pit-exit/lap-complete, NOT the mid-lap fuel-baseline tweak); NEW read-only `live_road_distance` (raw) + `live_lap_distance` (cumulative − lap-start, only while RACING/IN_PIT). Registry foundation in `data/reference_path_loader.py`: `list_available_reference_paths` (read-only, shipped = Fuji + Daytona), `reference_path_asset_summary` (honest available/unavailable), `resolve_trusted_lap_length` (asset → manifest → None; NEVER invents a length). Dashboard `_resolve_road_distance_fallback_context()` supplies `(lap_distance_m, road_distance, lap_length_m)` read-only. Render dispatches on source: fallback shows `track progress: NN.N% via GT7 road-distance fallback` + `progress confidence: … (fallback)` + `approved reference path unavailable` + `approximate and lower confidence than map matching`; overall `ReplanConfidence` UNCHANGED. No fake assets fabricated. Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group58_{road_distance_fallback, live_progress_precedence, live_replan_fallback_render, reference_asset_registry, safety_guards}.py` — **44 pure/offline tests, all pass ~0.9 s.** Safety: fallback no Qt/AI/DB-write/file import; new modules no api_key + no setup-authoring; fallback never HIGH; never creates a pit / mutates pit count / lifts pit evidence to HIGH; Apply-gate + disabled AI-build intact; `user_version` 13; Group 48/49 scoring deterministic. Regression: Group 53–58 strategy (366), telemetry state/pit + Group 48/49 + track/reference (823), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files untouched. `docs/UAT_RACE_STRATEGY.md` updated. See "Road Distance Fallback & Asset Expansion Foundation (Group 58)" at the end of this file.)
> Prior: 2026-07-07 (**Group 57 — Approved Reference Path Assets & Live Progress Activation** — read-only, advisory-only; branch `group57-reference-path-assets-progress-activation` (from clean `master` `4014857`). **Makes Group 56 live track progress actually activate by discovering + loading approved reference-path assets read-only.** The repo ALREADY ships a real calibration-sourced Fuji Full Course reference path (200 stations, Porsche RSR, confidence 1.0) → Fuji progress now genuinely resolves HIGH. No pit calls, no commands, no voice, no auto-refresh, no track-model mutation, no schema migration. 1 NEW pure module + 5 NEW test files + additive manifest/render/dashboard wiring. NEW `data/reference_path_loader.py` (PURE, Qt/DB/AI-free, read-only, never raises): `ReferencePathAsset` + `ReferencePathLoadResult` (`.has_stations`); `load_reference_path_file` (parses BOTH explicit `reference_path_v1` AND existing Group 17 calibration shape `track_location_id`+`points`), `find_reference_path_candidates` (scans `data/track_models/` + track-library, ranks by identity), `load_reference_path_for_layout`, `reference_path_to_track_stations` (→ Group 56 `TrackPathStation`), `validate_reference_path_identity`. Rejects NaN/inf, skips malformed stations, handles zero/neg lap length + duplicate distances; calibration build-notes → metadata (not live warnings); tolerant identity match (canonical id OR display-name tokens). Track library: optional backward-compatible `reference_path` manifest block (absent → `{}`) + `load_track_reference_path`. Dashboard `_resolve_live_track_progress_context()` REWRITTEN to use canonical `EventContext.track_location_id`/`layout_id` (Group 56 used display name + missed the file), loads via the new loader, validates identity, returns `(live_position, reference_stations, identity_ok, reference_path_source, reference_path_warnings)`; old `_load_reference_path_readonly` removed. `strategy/race_strategy_live_replan.py`: `build_live_replan_snapshot` gained `reference_path_source`/`reference_path_warnings`; `LiveReplanResult` carries them; render adds `reference path: loaded (...)` Found line + routes load warnings to Missing (unavailable/no-stations) or Warning (mismatch/malformed); overall `ReplanConfidence` UNCHANGED. Progress NEVER creates a pit; LOW/UNKNOWN/mismatched never lifts pit confidence. Road-distance fallback (§6) DEFERRED to Group 58. No fake production geometry invented (Fuji asset is genuine calibration output). Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group57_{reference_path_loader, track_library_reference_path, live_progress_activation, replan_reference_path_render, safety_guards}.py` — **52 pure/offline tests, all pass ~0.9 s.** Safety: loader no Qt/AI/DB-write + writes no files; new modules no api_key + no setup-authoring; missing/mismatched path never usable; never crashes on garbage-file grid; real Fuji asset byte-identical after load; Apply-gate + disabled AI-build intact; `user_version` 13. Regression: Group 54–57 + track-lib + map/station/calibration + telemetry state (1123), Group 48–53 strategy (453), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files untouched. `docs/UAT_RACE_STRATEGY.md` + `docs/TRACK_LIBRARY_SCHEMA.md` updated. See "Approved Reference Path Assets & Live Progress Activation (Group 57)" at the end of this file.)
> Prior: 2026-07-07 (**Group 56 — Live Position → Track Progress Resolver** — read-only, advisory-only; branch `group56-live-position-track-progress` (from clean `master` `cc4697f`). **Converts live GT7 world position (X/Y/Z) into a normalised lap progress (0.0–1.0) by matching to the nearest station on an approved/reference track path — unlocking real Group 55 pit-lane corroboration during live telemetry.** No pit calls, no commands, no voice, no auto-refresh, no track-model mutation, no schema migration. 1 NEW pure module + 5 NEW test files + additive tracker/adapter/render/dashboard wiring. NEW `data/live_track_progress.py` (PURE, Qt/DB/AI/file-write-free, never raises): `TrackProgressConfidence` (UNKNOWN/LOW/MEDIUM/HIGH; `.is_usable_for_pit`=MEDIUM/HIGH) + frozen `TrackPathStation` + `LiveTrackProgressResult` (`.has_progress`/`.usable_for_pit`); `build_track_path_stations` (ReferencePath `.points` / TrackStationMap `.stations` / dict/list; malformed skipped), `nearest_station` (XZ plane, ignores elevation), `normalise_distance_to_progress` (wraps; None on zero/invalid lap length), `estimate_lateral_offset` (+left/−right), `resolve_live_track_progress`, `format_live_track_progress_evidence`. Thresholds MIRROR `data/track_map_matching.py`: HIGH ≤5 m / MEDIUM ≤20 m / LOW ≤60 m / else UNKNOWN; identity mismatch caps LOW+warns; NaN/inf/missing → UNKNOWN. REUSE not rebuild: `ReferencePath`/`ReferencePathPoint` as station source + read-only `import_reference_path_json` loader; no calibration run, no track-model mutation. Tracker: read-only `live_world_position` property → `(x,y,z,speed_kph)` from last packet else None. `strategy/race_strategy_live_state.py`: `LiveReplanStateResult` gained `track_progress`; NEW `resolve_live_progress_evidence` + `attach_track_progress`; `apply_pit_lane_evidence` now consumes MEDIUM/HIGH track progress when no explicit `live_progress` (LOW/UNKNOWN → position_unknown fallback, never lifts). `strategy/race_strategy_live_replan.py`: `build_live_replan_snapshot` gained `live_position`/`reference_stations`/`identity_ok` (+ `_position_from_source`); `LiveReplanResult` carries `track_progress`; render shows track-progress %, distance-along-lap, position-match confidence, "pit-lane map used live track progress", honest Missing + Warning lines; overall `ReplanConfidence` UNCHANGED (≤ MEDIUM — progress is supporting evidence). Dashboard `_resolve_live_track_progress_context()` + `_load_reference_path_readonly()` load an approved path read-only (no calibration/mutation) → (None,None,True) graceful degrade. Progress NEVER creates a pit event; Group 54 owns pit events, Group 55 owns corroboration. Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group56_{live_track_progress, track_progress_adapter, live_replan_progress_integration, pit_lane_progress_bridge, safety_guards}.py` — **64 pure/offline tests, all pass ~0.7 s.** Safety: resolver no Qt/DB/AI/file-writes; new modules no api_key + no setup-authoring; unknown/LOW progress never usable-for-pit; resolver never crashes on garbage; progress never creates a pit / never touches pit count; Apply-gate predicate + disabled AI-build intact; `user_version` 13. Regression: Group 48–55 strategy + telemetry state/tracker/pit + track map/station/calibration (996), Group 48–53 strategy (453), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files untouched. `docs/UAT_RACE_STRATEGY.md` updated. Caveat: no approved reference-path file ships in the repo → live progress typically resolves "approved reference path unavailable" until one exists (test-only `fuji_reference_path()` fixture). See "Live Position → Track Progress (Group 56)" at the end of this file.)
> Prior: 2026-07-07 (**Group 55 — Track-Specific Pit-Lane Mapping & Pit Confidence Upgrade** — evidence-quality (read-only); branch `group55-track-pit-lane-mapping` (from clean `master` `7ff7433`). **Adds an independent corroborating line of pit evidence: if live lap-progress falls inside a track's KNOWN pit-lane corridor, a detected pit event is stronger.** No pit calls, no commands, no voice, no auto-refresh, no track-model mutation, no schema migration. 1 NEW pure module + 5 NEW test files + additive schema/tracker/adapter/render wiring. NEW `data/pit_lane_resolver.py` (PURE, Qt/DB/AI/file-write-free, never raises): `PitLaneZone` (UNKNOWN/NOT_PIT_LANE/PIT_ENTRY/PIT_LANE/PIT_EXIT) + `PitLaneMappingConfidence` (NONE/LOW/MEDIUM/HIGH) + frozen `PitLaneSegment`/`PitLaneResolution` (`.is_inside_pit_lane`); `normalise_progress` (wrap 0–1, reject NaN/inf), `progress_in_wrapped_range` (spans crossing start/finish, inclusive ends, zero-width never matches), `resolve_pit_lane_zone` (narrowest span wins; UNKNOWN on no-mapping/progress-unknown; NOT_PIT_LANE when position known off-corridor), `build_pit_lane_segments_from_track_context`, `resolve_pit_lane_from_track_context`, `segments_mapping_confidence`. NEVER infers a pit lane from racing segments — explicit `pit_lane` metadata only. Track library: optional `pit_lane` dict added to `TrackLayoutManifest` (absent → `{}`) + `load_track_pit_lane` (dedicated `pit_lane.json` wins, else manifest inline, else None) — backward-compatible; only Daytona ships (no pit-lane) → None → Group 54 fallback; no Fuji production entry invented (test-only `fuji_pit_lane_mapping()` fixture). Tracker: read-only `in_pit` property added. `strategy/race_strategy_live_state.py`: `LiveReplanStateResult` gained pit_in_progress/pit_lane_zone/pit_lane_source/pit_lane_mapping_confidence/pit_evidence_confidence/pit_corroboration; NEW `apply_pit_lane_evidence` — no mapping → Group 54 preserved; progress unknown → no upgrade; inside corridor + refuel pit (MEDIUM) → HIGH; inside + speed-only (LOW) → MEDIUM at most; in-pit but on-track → CONTRADICTION (no upgrade + warning); low-confidence map cannot certify HIGH. NEVER touches pit_stops_completed/tyre_age_laps (Group 54 owns events), never fabricates a stop. `strategy/race_strategy_live_replan.py`: `build_live_replan_snapshot` gained `track_context`+`live_progress`; overall replan confidence UNCHANGED (still ≤ MEDIUM — pit-evidence is a separate signal); `render_live_replan_text` shows zone/corroboration/pit-confidence + honest Missing + contradiction Warning; no "Pit Now". Dashboard `_resolve_live_pit_lane_context()` resolves (track_context, live_progress) or (None, None) → graceful degrade (GT7 broadcasts no normalised lap-progress today → typically None). Constants: NONE (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group55_{pit_lane_resolver, live_pit_lane_adapter, live_replan_pit_confidence, track_library_pit_lane_schema, safety_guards}.py` — **73 pure/offline tests, all pass ~0.7 s.** Safety: resolver no Qt/DB/AI/file-writes; new modules no api_key + no setup-authoring; corroboration never creates a pit / never treats unknown mapping as safe / never crashes on malformed data; Apply-gate predicate + disabled AI-build intact; `user_version` 13. Regression: Group 48–54 strategy suites (754), telemetry state/tracker/pit (564 incl. new `in_pit`), track-library (92), dashboard constructs (13 `test_ui_structure_smoke`). Runtime files untouched. `docs/UAT_RACE_STRATEGY.md` + `docs/TRACK_LIBRARY_SCHEMA.md` updated. See "Track-Specific Pit-Lane Mapping (Group 55)" at the end of this file.)
> Prior: 2026-07-07 (**Group 54 — Race Strategy Brain Phase 8: Live Pit & Tyre-Age State Tracking** — evidence-quality (read-only); branch `group54-live-pit-tyre-age-tracking` (from clean `master` `2081f88`). **Added a read-only live pit-stop counter + laps-since-pit / tyre-age tracker so live replan can judge tyre age + pit count honestly** — resolves the Group 53 LOW-confidence cap. No auto pit calls, no voice, no driver commands, no setup changes. 1 NEW pure module + 7 NEW test files + additive tracker/adapter wiring. DISCOVERY: `RaceStateTracker` ALREADY detects pit entry/exit (fuel-refuel + conservative sustained-stop heuristic → PIT_ENTRY/PIT_EXIT); GT7 has NO pit flag; the app just never counted stops or aged the stint — Group 54 adds that on top (no fabricated signal). NEW `telemetry/pit_state.py` (PURE): `PitStintState` + `PitEvent`/`PitDetectionConfidence` (HIGH=no-pit-yet-certain / MEDIUM=refuel / LOW=speed-only / UNKNOWN) + pure updaters `start_stint_tracking`/`apply_lap_completed`/`apply_pit_event` (dedups same-lap, ignores negative laps, NONE never counts)/`apply_manual_pit` + `classify_pit_confidence`. RaceStateTracker: holds a PitStintState; start at RACING; apply_lap_completed in `_check_lap`; apply_pit_event in `_exit_pit`; read-only getters pit_stops_completed/laps_since_pit/tyre_age_laps/pit_state_confidence/pit_stint_state; runtime-only, no persistence, no crash on partial packets. `strategy/race_strategy_live_state.py` maps tracker tyre_age + pit count into RaceReplanState ONLY at HIGH/MEDIUM (LOW → not populated but low-confidence estimate surfaced; UNKNOWN → missing). CONFIDENCE: pre-pit/post-refuel-pit → MEDIUM (was LOW in Group 53); unknown/low-conf tyre → LOW; missing fuel/distance → INSUFFICIENT; never forced HIGH. UI: no dashboard.py change — enhanced pure `render_live_replan_text` lists pit/stint under Found/Missing. `run_fuji_live_replan` gained pre_pit_healthy/just_pitted/missing_pit fixtures. Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group54_{pit_state_model, pit_detection, tracker_pit_state, live_adapter_pit_state, live_replan_confidence, porsche_fuji_pit_state, strategy_safety_regression}.py` — **63 pure/offline tests (pure model + REAL tracker via MagicMock packets + SQLite `:memory:`), all pass ~2 s.** tracker_pit_state exercises real wiring. Safety tests: modules no Qt import + no setup-authoring + no api_key + no Apply/approve + no setup-history write (content-hash); missing pit never safe; Apply-gate predicate + disabled AI-build intact; SessionDB read-only. Regression: Group 53/52/51/50/49/48 strategy suites + telemetry state suites (119) + Group 47/46 subsets green; dashboard constructs (13 `test_ui_structure_smoke`). Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. Known caveat: run UI files individually on Win/Py3.14 (PyQt cross-file segfault); Group 54's suites are Qt-free. Tyre-age is an approximation (detected pit assumed to change tyres; GT7 doesn't report it). `docs/UAT_RACE_STRATEGY.md` updated. See "Race Strategy Brain Phase 8 — Live Pit & Tyre-Age (Group 54)" at the end of this file.)
> Prior: 2026-07-07 (**Group 53 — Race Strategy Brain Phase 7: Live Current-State Replan Input** — live wiring (read-only); branch `group53-live-replan-current-state` (from clean `master` `bbf2198`). **Wired the Group 52 replan foundation to the app's EXISTING read-only live race-state source.** Read live state → compare to the pre-race plan → advisory-only snapshot with honest missing-state. No auto pit calls, no voice, no driver commands, no setup changes. 2 NEW pure modules + 6 NEW test files + extended UAT helper + upgraded read-only UI surface. DISCOVERY (honest): app HAS current lap (laps_recorded), remaining time (computed_remaining_ms)/laps (laps_remaining), fuel % (packet.fuel_level/fuel_capacity), live burn (avg_fuel_per_lap), strategy/UI-tagged compound (_current_compound); does NOT track live tyre age / pit-stop count / required-compounds → missing (so snapshots are typically LOW_CONFIDENCE/INSUFFICIENT and say so). NEW `strategy/race_strategy_live_state.py` (PURE, no Qt/DB/IO/AI, never raises): `build_replan_state_from_tracker`/`_from_live_packet`/`_from_dashboard_context`/`extract_live_replan_state`/`summarise_live_state_sources` → `LiveReplanStateResult` (RaceReplanState + per-field state_sources {live_telemetry/strategy-UI tag/missing} + warnings + missing_state + live_fuel_per_lap); drops impossible values (fuel>capacity, negative lap); unknown→missing. NEW `strategy/race_strategy_live_replan.py` (PURE): `build_live_replan_snapshot(*, pre_race_result, live_source|live_state, event_settings, latest_fuel_samples, generated_at)` → `LiveReplanResult` (state/state_sources/readiness/snapshot/driver_message/missing_state/warnings/safety_notes/generated_at; .status/.confidence); feeds live burn into Group 52 snapshot; `render_live_replan_text` + Fuji fixtures. UI (`ui/dashboard.py`, additive): read-only "Live Replan Readiness (read-only, advisory only)" group + "Refresh Live Replan Snapshot" button → `_refresh_live_replan_snapshot()` (reads _tracker+_last_packet read-only, compares vs stored _last_race_plan_result); NO auto-loop/timer/voice/pit-call/Apply/API-key. `ui/race_strategy_uat.py::run_fuji_live_replan(kind)` (healthy/fuel_short/missing fixtures, offline). Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group53_{live_state_adapter, live_replan_snapshot, live_replan_ui_surface, live_replan_safety, porsche_fuji_live_replan, strategy_regression}.py` — **70 pure/offline tests (duck-typed mocks + SQLite `:memory:`; UI guarantees source-verified), all pass in <1.5 s.** Safety tests: live modules no Qt import + no setup-authoring imports + no I/O + no api_key + no Apply/approve capability + no setup-history write (content-hash); unknown tyre never high confidence; missing fuel→INSUFFICIENT; Apply-gate predicate + disabled AI-build intact; Group 48/49 scoring deterministic; dashboard constructs (13 `test_ui_structure_smoke`). Regression: Group 52/51/50/49/48 strategy suites + Group 47/46 subsets green. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. Known caveat: run UI files individually on Win/Py3.14 (PyQt cross-file segfault); Group 53's own suites are Qt-free. `docs/UAT_RACE_STRATEGY.md` updated. See "Race Strategy Brain Phase 7 — Live Current-State Replan (Group 53)" at the end of this file.)
> Prior: 2026-07-07 (**Group 52 — Race Strategy Brain Phase 6: Manual UAT Remediation & Live Replan Readiness Foundation** — UAT + read-only foundation; branch `group52-race-strategy-uat-replan-readiness` (from clean `master` `a32c694`). **Verified the Group 48–51 Race Plan surface under Porsche RSR/Fuji UAT (NO defects found) + added a pure, read-only, advisory-only foundation for future live replan.** No new strategy maths, no live telemetry, no automatic pit calls. 1 NEW pure module + 6 NEW test files + extended UAT helper + read-only UI placeholder. `ui/race_strategy_uat.py` extended with `run_fuji_race_plan_uat_check(n_laps, fuel)` → structured `FujiUatCheckResult` (event/session validation, readiness_level, clean_lap_count, fuel/tyre flags, candidate_count, recommended_strategy, one_stop/two_stop_total_time, push_plan_rejected_or_not_recommended, missing_evidence, warnings, safety_checks dict, passed, failure_reasons); deterministic offline; UAT OUTCOME = no defects (full 12-lap + incomplete 4-lap/no-fuel scenarios both correct). NEW `strategy/race_strategy_replan.py` (PURE, no Qt/DB/IO, never raises): `RaceReplanState` (all fields default unknown None; unknown tyre NEVER assumed safe), `validate_replan_state`, `assess_replan_readiness` → `ReplanReadinessLevel` (READY/PARTIAL/LOW_CONFIDENCE/INSUFFICIENT_EVIDENCE; no fuel/compound/distance→INSUFFICIENT, tyre unknown→LOW_CONFIDENCE), `build_replan_snapshot(*, pre_race_result, state, …)` → `RaceReplanSnapshot` (advisory-only: compares reported fuel to pre-race burn over laps-to-next-stop; options = pre-race Group 48 scored candidates labelled "pre-race estimate"; confidence capped MEDIUM/LOW; INSUFFICIENT_EVIDENCE when critical state/plan missing; carries "Advisory only — no pit call, setup change, or driver command is applied."), `render_replan_snapshot_text`, `replan_placeholder_message`. UI (`ui/dashboard.py`, additive): small read-only "Live Replan Readiness: not connected yet …" placeholder label at the bottom of the Race Plan group (no button/loop/wiring). Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group52_{race_plan_uat_harness, race_plan_uat_remediation, replan_state, replan_snapshot, replan_safety, strategy_regression}.py` — **64 pure/offline tests (SQLite `:memory:`; UI guarantees source-verified), all pass in <1.5 s.** Safety tests: replan module no Qt import + no setup-authoring imports + no I/O + no Apply/approve capability + no setup-history write (content-hash) + honest placeholder; Apply-gate predicate + disabled AI-build intact; Group 48/49 scoring deterministic; dashboard still constructs (13 `test_ui_structure_smoke`). Regression: Group 51/50/49/48 strategy suites + Group 47/46 subsets green. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. Known caveat: run UI files individually on Win/Py3.14 (PyQt cross-file segfault); Group 52's own suites are Qt-free. `docs/UAT_RACE_STRATEGY.md` updated. See "Race Strategy Brain Phase 6 — UAT & Replan Foundation (Group 52)" at the end of this file.)
> Prior: 2026-07-06 (**Group 51 — Race Strategy Brain Phase 5: Race Plan UAT Hardening & Session Selection Polish** — UI/usability; branch `group51-race-plan-uat-hardening` (from clean `master` `6938218`). **The Group 50 Race Plan surface is now reliable, understandable, and ready for real manual UAT.** Hardening + usability only — NO strategy-maths changes. 2 NEW pure Qt-free modules + 6 NEW test files + ADDITIVE UI wiring in `ui/dashboard.py`. NEW `ui/race_strategy_readiness_vm.py` (PURE, no Qt): `ReadinessLevel` (READY/PARTIAL/LOW_CONFIDENCE/INSUFFICIENT_EVIDENCE) + `CheckStatus` enums; `build_race_plan_readiness(*, samples, event_settings)` → `RacePlanReadiness` (per-field statuses + overall + readiness_message + next_best_action + found/missing); `build_session_diagnostics(...)` → `SessionDiagnostics`; `validate_event_settings(...)` → `EventSettingsValidation` (warnings + field_status + can_run); `empty_state_messages(...)` + `strategy_result_message(...)`; `list_recent_matching_sessions(db, car_id, track, limit)` (read-only, get_practice_sessions only); `render_readiness_html(...)`; never raises, invents nothing. NEW `ui/race_strategy_uat.py` (offline UAT helper): `FUJI_UAT_EVENT_SETTINGS` + `build_fuji_uat_db`/`build_fuji_uat_context`/`run_fuji_uat` reproduce the RSR/Fuji scenario deterministically in-memory. UI (`ui/dashboard.py`, additive): read-only session selector `_rp_session_combo` + `_btn_rp_refresh_sessions` + `_rp_session_status` + `_rp_readiness_status` labels; `_selected_race_plan_session_id()`/`_populate_race_plan_sessions()`/`_refresh_race_plan_diagnostics()` (read-only); `_run_race_plan()` prepends readiness+diagnostics banner + "Before you rely on this" guidance; NO API key, NO Apply/approve controls, NO setup writes. Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group51_{race_plan_readiness, session_selection_vm, event_settings_validation, race_plan_empty_states, strategy_surface_hardening, porsche_fuji_uat_path}.py` — **81 pure/offline tests (mock/read-only DB + SQLite `:memory:`; Qt guarantees source-verified), all pass in <1 s.** 1 Group 50 test updated (`test_group50_strategy_surface.py`) for the legitimate new read-only Refresh button (no-Apply/approve intent preserved). Safety tests assert: Apply-gate predicate + disabled AI-build line intact, readiness module + Group 50 VM have no Qt import + import no setup-authoring, SessionDB read path read-only, no setup-history write (content-hash), Group 48/49 scoring deterministic; dashboard still constructs (13 `test_ui_structure_smoke` pass, run individually). Regression: Group 50/49/48 strategy suites + Group 47/46 subsets green. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. Known caveat: run UI files individually on Win/Py3.14 (PyQt cross-file segfault); Group 51's own suites are Qt-free. New doc `docs/UAT_RACE_STRATEGY.md`. See "Race Strategy Brain Phase 5 — UAT Hardening (Group 51)" at the end of this file.)
> Prior: 2026-07-06 (**Group 50 — Race Strategy Brain Phase 4: Driver-Facing Race Plan Surface** — UI/presentation; branch `group50-race-strategy-surface` (from clean `master` `7b65fbd`). **The Group 48/49 strategy engine is now surfaced to the driver in the Strategy Builder as a clean, read-only Race Plan.** Presentation/integration only — NO strategy-maths changes. 1 NEW pure Qt-free view-model module + 6 NEW test files + a purely ADDITIVE UI block in `ui/dashboard.py`. NEW `ui/race_strategy_vm.py` (PURE, no Qt import): `RacePlanViewModel` + `build_race_plan_view_model(SessionStrategyResult)` + section formatters (`format_race_time` mm:ss.s, `compound_name`, stint/candidate/evidence/missing/risk/safety) + `render_race_plan_html(vm)` + `candidate_table_rows(vm)`/`CANDIDATE_TABLE_COLUMNS` + `run_race_plan_from_session(...)`/`run_race_plan_from_event_context(...)`; evidence rows carry a `category` ∈ {measured, derived, event, manual, default, missing}; risk = recommended plan's own flags + cross-plan "Rear traction fragile: push strategy not recommended." note; never raises, deterministic. UI (`ui/dashboard.py`, additive): `_build_race_plan_group()` in the Strategy Builder tab (intro + 2 small manual inputs Pit-loss s / Starting-fuel % + "Build Race Strategy" button → `_run_race_plan()` + read-only `_race_plan_text` HTML + `_race_plan_table`); `_assemble_race_plan_inputs()` reads canonical EventContext + resolved session id + car id; `_run_race_plan()` derives rear-fragility from the structured DriverProfile; NO API key, NO Apply/approve controls, NO setup writes. Session-backed with honest fallback (no session → INSUFFICIENT_EVIDENCE + visible missing evidence). Porsche RSR/Fuji surface: one-stop 51:52.0 beats two-stop 52:28.0 (+36.0s), SessionDB-measured pace/fuel + derived tyre proxy, push flagged rear-fragile + never recommended, no Apply action. Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group50_{race_strategy_vm, strategy_surface, strategy_candidate_table, strategy_evidence_display, strategy_safety_regression, porsche_fuji_strategy_surface}.py` — **70 pure/offline tests (mock DB + SQLite `:memory:`; Qt guarantees source-verified, not via QApplication), all pass in <1 s.** Safety tests assert: Apply-gate predicate + disabled AI-build line intact, Race Plan group/method has no Apply/approve capability, reads no API key, writes no setup history (content-hash), VM imports no setup-authoring module + no Qt import, SessionDB adapter read-only, Group 48/49 scoring deterministic; dashboard still constructs (13 `test_ui_structure_smoke` pass, run individually). Regression: Group 49 + 48 strategy suites + Group 47/46 subsets green. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. Known caveat: run UI files individually on Win/Py3.14 (PyQt cross-file segfault); Group 50's own suite is Qt-free. See "Race Strategy Brain Phase 4 — Driver-Facing Surface (Group 50)" at the end of this file.)
> Prior: 2026-07-06 (**Group 49 — Race Strategy Brain Phase 3: SessionDB Evidence Integration** — backend only; branch `group49-strategy-sessiondb-integration` (from clean `master` `df78535`). **The Group 48 strategy brain now builds evidence from real stored SessionDB telemetry instead of only caller-supplied samples.** 5 NEW pure `strategy/` modules + 6 NEW test files + two tiny ADDITIVE edits: read-only `SessionDB.get_session_meta(...)` (no schema change) and an optional `evidence_sources` field on the Group 48 `StrategyExplanation` (Group 48 behaviour byte-identical when unset). NEW `strategy/race_strategy_session_adapter.py` (READ-ONLY: `get_session_meta` + `get_session_laps` only; never writes/raises; `SessionStrategySamples` + `extract_session_strategy_samples(...)`; clean laps, fuel from `fuel_used`|`fuel_start-fuel_end`, per-compound pace; tyre-wear = disclosed proxy DERIVED from within-stint lap-time drift, ≥3 consecutive same-compound laps; safe on no-DB/no-session/no-laps/car-track mismatch). NEW `strategy/race_strategy_from_session.py` (`build_strategy_evidence_from_session(...)` + `build_strategy_evidence_from_event_context(...)` → `SessionEvidenceResult`; feeds samples+event settings into Group 48 `build_strategy_evidence`; fabricates nothing; `source_summary` classifies each input SessionDB-measured/event-setting/default/missing). NEW `strategy/race_strategy_pipeline.py` (`recommend_strategy_from_session(...)`/`recommend_strategy_from_event_context(...)` → frozen `SessionStrategyResult`; illegal excluded; Group 48 safety-aware tie-break; no learning parameter; standing read-only/strategy-only safety notes). NEW `strategy/race_strategy_session_explain.py` (`build_session_explanation(...)` reuses Group 48 builder + per-input provenance lines). NEW `strategy/race_strategy_session_benchmark.py` (seeds in-memory `SessionDB(":memory:")` with 12 RSR/Fuji laps; one-stop beats two-stop by ~36 s on total race time; push flagged rear-fragile + not recommended; offline). Constants: NONE (`DB_VERSION` 13, `RULE_ENGINE_VERSION` 46.0). Schema/migrations: NONE. New suites `tests/test_group49_{strategy_session_adapter, strategy_from_session, strategy_pipeline, strategy_session_explainability, porsche_fuji_session_strategy, strategy_safety_regression}.py` — **73 pure/offline tests (mock DB + SQLite `:memory:`), all pass in <1 s.** Safety tests assert: Apply-gate predicate string + disabled AI-build line intact, pipeline leaks no setup-field tokens, no apply/approve capability, imports no setup-authoring module, writes nothing to `data/setup_history.json` (content-hash before/after), no learning parameter, driver memory can't flip legality or change total-time maths, Group 48 scoring deterministic. Regression: Group 48 (95) + Group 47 (73) + Group 46 subset (91/1 skip) + Groups 41–45 non-UI + `test_session_db` (326/1 skip) green. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. See "Race Strategy Brain Phase 3 — SessionDB Integration (Group 49)" at the end of this file.)
> Prior: 2026-07-06 (**Group 48 — Race Strategy Brain Phase 2: Telemetry-Based Strategy Intelligence** — backend only; branch `group48-race-strategy-intelligence` (from clean `master` `1c5890e`). **Purely additive: 5 NEW pure `strategy/` modules + 6 NEW test files; no existing file modified.** The Pit Crew now ranks race strategies by estimated TOTAL race time (not fastest lap) from real evidence, with honest confidence and a category-separated explanation. NEW `strategy/race_strategy_evidence.py` (`StrategyConfidence` enum HIGH/MEDIUM/LOW/INSUFFICIENT_EVIDENCE + frozen `RaceStrategyEvidence` + `build_strategy_evidence(...)`/`evidence_from_race_params(...)`; records missing evidence, never fabricates; race pace = MEDIAN clean lap; confidence gating no-lap/no-fuel→INSUFFICIENT, weak-pit-maths→LOW, soft-gaps step down). NEW `strategy/race_strategy_candidates.py` (`generate_candidates` → no/one/two/three-stop + `1stop_fuelsave`/`2stop_push`/`1stop_compound_switch`, stable IDs, pace-free fuel/refuel/pit maths; LEGALITY hard gate — mandatory stops, per-stint fuel ≤ 100 L, required compounds all fit; illegal returned-but-flagged, excluded from `legal_candidates()`). NEW `strategy/race_strategy_scorer.py` (`score_candidates` ranks by green_base + degradation_cost + pit_time + fuel_saving_cost + compound_cost, all itemised; measured tyre-wear only; `recommend_strategy` safety-aware tie-break `SAFETY_TIE_TOLERANCE_S=5.0`; `fuel_save_worth_it`; driver memory touches confidence/risk/tie-break ONLY). NEW `strategy/race_strategy_explain.py` (`StrategyExplanation.to_text()` keeps KNOWN/CALCULATED/ASSUMPTION/MISSING/RISK separate, no "perfect strategy" language). NEW `strategy/race_strategy_benchmark.py` (Porsche 911 RSR '17/Fuji/~50min/8× tyre/3× fuel/1 L/s refuel; reads rear-fragility from the structured Group 42 `DriverProfile`; proves one-stop beats two-stop by ~36 s, push plan flagged for rear fragility + never recommended). Constants: NONE changed (`DB_VERSION` stays 13, `RULE_ENGINE_VERSION` stays 46.0). Schema/migrations: NONE. New suites `tests/test_group48_{strategy_evidence, strategy_candidates, strategy_scorer, strategy_confidence, strategy_ui_explainability, porsche_fuji_strategy_benchmark}.py` — **95 pure/offline tests, all pass in <1 s.** Safety tests assert: strategy surface leaks no setup-field tokens, no apply/approve capability, imports no setup-authoring module, Apply-gate predicate string + disabled AI-build line in `ui/setup_builder_ui.py` intact, driver memory cannot flip legality or change total-time maths. Regression: Group 47 (73) + Group 46 (151/1 skip) + Groups 41–45 non-UI (351/1 skip) green; no existing file modified. Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched. See "Race Strategy Brain Phase 2 (Group 48)" at the end of this file.)
> Prior: 2026-07-06 (**Group 45 — Setup Brain Intelligence Expansion** — backend + UI; branch `ofr2-quali-race-disciplines` (on top of Group 44). **The rule-first Setup Brain became context-aware: session type, tyre-wear, drivetrain, and car-class now genuinely shape which rules fire and how confident/ranked they are — WITHOUT inventing precision (delta magnitudes unchanged; context affects filtering, confidence, ranking, contraindication, and explanation only).** Architecture preserved: Pit Crew owns the decision, AI stays audit-only (`parse_audit_response` strips canonical params; `map_audit_to_finaliser` never un-blocks; voice narration-only); both Analyse and Baseline run through the one validator → funnel → renderer → Apply gate; the old AI build path stays disabled; everything works with AI disabled. ENGINE SCOPE FILTER (`strategy/setup_rule_engine.py::_scope_matches`): `applies_session`/`applies_drivetrain`/`applies_car_class` now enforced at runtime; `any`/`None` = wildcard-permissive; Pack A EXEMPT; all-rules-filtered-out → valid empty `SetupPlan`. CONTEXT RESOLUTION (`strategy/driving_advisor.py`): Analyse reads `_event_ctx` (tyre_wear→tyre_wear_multiplier, fuel_multiplier, duration_mins) + `purpose`→`SessionType`, `car_specs.category`→`CarClass`, `drivetrain` (precedence: UI combo > `CAR_DRIVETRAIN_OVERRIDES {"Porsche 911 RSR (991) '17":"rr"}` > empty DB → None); Baseline gets SCALAR params only (no EventContext). DRIVER-PROFILE ACTIVE WEIGHTING: bounded {−1,0,+1} rank tiebreaker when confidence equal (magnitudes UNCHANGED). SESSION/TYRE/FUEL: session biases confidence (quali→front-bite/trail-braker; race→safety/consistency; endurance=race+duration>=60); `HIGH_TYRE_WEAR_THRESHOLD=5.0` sets `diagnosis["tyre_wear_high"]` which CONTRAINDICATES 4 tyre-abusing rules (B3 lsd_accel-down, C1_entry_lsd_decel lsd_decel-down, C3_mid_arb_rear + C7_kerb_arb_rear rear-ARB-soften); increase-lock/downforce rules NOT suppressed; fuel READ but only informational. PORSCHE PACK P (`register_pack("P",...)`): rule P1 cautious traction-first lsd_accel increase (rr+gr3, contraindicated on `snap_oversteer_exit`); no P2 (A2 covers rear-downforce); asserts RR via overrides. GEARBOX: B5b (gear_too_long→final_drive_up) added to B5; "limiter_before_braking" maps to existing gear_too_short (not faked); `per_gear_limiter_evidence` exposed, full per-gear rules DEFERRED; monotonic ordering now NON-INCREASING (equal ratios allowed; engine + `gearbox_ratio_inversion` validator both strict-`>`). LEARNING SEAM: live-but-EMPTY `RuleOutcomeStore` (was None) — hook wired but never fires without samples; `_learning_note`; persistence + feed DEFERRED; learning CANNOT un-block/un-reject/bypass validation/make AI actionable. EXPLAINABILITY: `source_label`/`session_influence`/`car_drivetrain_influence`/`pack` on each approved + rejected change, populated HONESTLY (positive claim only when context used, else explicit neutral string); baseline labels never claim telemetry. `RULE_ENGINE_VERSION`="45.0". New suites `tests/test_group45_engine_scope.py`, `test_group45_gear_monotonic.py`, `test_group45_context_signals.py`, `test_group45_porsche_pack.py`, `test_group45_explainability.py`, `test_group45_learning.py`, `test_group45_baseline_context.py`, `test_group45_ui_context.py`; 3 existing tests reconciled (`RULE_ENGINE_VERSION` "42.0"→"45.0"; baseline lsd_decel bias nets differently with `rotation_without_snap`; inversion validator strict-`>`). All Group 45 tests pass; the ~18 pre-existing frozen-allowlist/schema failures are KNOWN, unrelated, and untouched; run tests IN HALVES on Win/Py3.14 (flaky PyQt teardown segfault). `docs/RULE_FIRST_SETUP_BRAIN.md` (§ Group 45 + § 14 dedicated "Setup Brain Intelligence Expansion"), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 45), `docs/UAT_SETUP_BRAIN.md` (§ Group 45). See "Setup Brain Intelligence Expansion (Group 45)" at the end of this file.)
> Prior: 2026-07-06 (**Group 44 — Rule-First From-Scratch Setup Baseline Generator** — backend + UI; branch `ofr2-quali-race-disciplines` (on top of Group 43); delivered via the feature-factory chain. **Restores the capability lost when Group 43 disabled "Build Setup with AI" — the app can now author a COMPLETE safe starting setup for a car with NO telemetry, deterministically, with the AI NEVER called.** A new **"Build Baseline Setup"** button (`_btn_baseline`) sits separate from the still-disabled `_btn_build_setup` (Group 43 guards untouched). Why a new module (not `run_rule_engine`): the rule engine emits DELTAS off a telemetry diagnosis, so with no telemetry almost no rules fire — a separate ABSOLUTE-VALUE author was required. NEW `strategy/setup_baseline.py`: `NEUTRAL_SEEDS` (single source of truth for neutral physics defaults; matches the form seeds in `ui/setup_form_widget.py` — lsd_front_initial/accel/decel take the FORM values 10/15/5, differing from the `ai_planner` parser fallbacks 0/0/0); `build_baseline_setup(car, ranges, drivetrain, num_gears, profile, allowed_tuning, tuning_locked) -> raw_data dict` (plan_to_raw_data shape) authors ALL 33 actionable `_CANONICAL_SETUP_PARAMS` (34 minus display-only transmission_max_speed_kmh) as ABSOLUTE values via neutral seed → driver-profile bias (`_PROFILE_BIAS_TABLE`) → clamp to `resolve_ranges(car)`; gearbox (`_build_gearbox_changes`) = final_drive midpoint of `_FINAL_DRIVE_RANGE (2.5,6.0)` + a strictly-DECREASING geometric gear sequence inside `_GEAR_RATIO_RANGE (0.5,4.0)` (monotonic by construction → `gearbox_ratio_inversion` can never fire); locked categories excluded + named by human category; every change carries a source label ("neutral default"/"range midpoint"/"driver-profile biased"/"conservative default, not diagnosed"). ORCHESTRATOR `DrivingAdvisor.build_baseline_setup_response(...)`: `build_driver_profile()` → `build_baseline_setup` → `validate_setup_engineering_structured` (neutral baseline passed as BOTH the `setup` arg AND the proposed setup_fields → zero delta) → `_filter_baseline_artifact_warnings` (drops ONLY WARNING-severity failures whose message contains "is a no-op" or "too many changes"; the severity guard `if vf.severity == "warning"` is the OUTER condition → cannot suppress a blocking failure) → `_finalise_recommendation` → JSON identical in shape to `build_combined_setup_response`. NO api_key read, NO call_api, NO audit. FRONTEND: new `_btn_baseline` (enabled+visible; added to `_RACE_ALIASES`) in `ui/setup_form_widget.py` + `ui/setup_builder_ui.py` handlers `_generate_baseline_setup`/`_generate_baseline_setup_for_form` (daemon thread → `_baseline_result_queue` in `ui/dashboard.py`) → `_display_baseline_result` DELEGATES to the shared `_display_setup_result` renderer + Apply gate; Group 43 `_btn_build_setup`/`_run_build_setup*` guards untouched. New suites `tests/test_group44_baseline_generator.py` (86 backend) + `tests/test_group44_baseline_ui.py` (64 UI/integration). **406 green together with group41 + group42 (all) + group43; 0 fail** — the SAME 8 pre-existing frozen-allowlist track-modelling guards remain (unrelated, untouched); run tests in halves on Win/Py3.14 (flaky PyQt teardown segfault). `docs/RULE_FIRST_SETUP_BRAIN.md` (§ Group 44). See "Rule-First Setup Baseline Generator (Group 44)" at the end of this file.)
> Prior: 2026-07-05 (**Group 42 — Rule-First Setup Brain** — backend + UI + DB. **The Setup Brain inverted from AI-first to RULE-FIRST**: deterministic race-engineering rules are now the PRIMARY source of setup recommendations; the AI is demoted to an AUDIT-ONLY layer (approve/warn/reject/request-more-data) that CANNOT author actionable setup changes. ONE source of truth for actionable changes: the deterministic rule engine. New flow in `build_combined_setup_response`: diagnose (`build_setup_diagnosis`) → `build_driver_profile()` → `run_rule_engine()` → `SetupPlan` → `plan_to_raw_data` → `_normalise_changes` → `validate_setup_engineering_structured` → if blocking `_build_deterministic_fallback` (NOT AI) → else if API key `call_api` for AI AUDIT ONLY → `parse_audit_response` (strips any canonical setup field keys) → `map_audit_to_finaliser` → `_finalise_recommendation` (unchanged funnel). NEW backend modules (all `strategy/`, pure Python): `setup_knowledge_base.py` (rule catalogue + `register_pack`/`get_all_rules`/`resolve_delta`; enums RulePhase/RiskLevel/ConfidenceLevel/DrivetrainType/CarClass/SessionType; NamedTuples SetupRule/SetupEvidence; **22 rules** — Pack A A1–A8 safety invariants, Pack B B1–B6 driver-style adaptation, Pack C/D C1_entry_lsd_decel/C2_entry_brake_bias/C3_mid_arb_rear/C4_mid_rear_aero/C5_exit_lsd_accel/C6_exit_rear_aero/C7_kerb_arb_rear/C8_kerb_rh_rear handling-phase starter set; remaining per-setting Pack C deferred, extensible via register_pack; delta resolvers = named-string lookups in `_DELTA_RESOLVERS`, no stored callables); `setup_driver_profile.py` (`DriverProfile` NamedTuple + `DriverStyleAlignment` enum; `build_driver_profile()` derives 8 booleans from the existing `PERSONAL_DRIVER_TUNING_MODEL`/`DRIVER_HARD_CONSTRAINTS`; never raises — driver style is now a DATA STRUCTURE for ranking + contraindications); `setup_rule_engine.py` (`SetupChangeIntent`/`SetupPlan` NamedTuples; `run_rule_engine(diagnosis, setup, ranges, profile, allowed_tuning=None, rule_outcome_store=None)` — Pack A protects fields, conflict resolution → rejected `conflict:<id>`, no-op exclusion, gear-count gating, confidence-downgrade hook; `RuleOutcomeStore` fire/success counts keyed rule_id/car/track/driver_profile_version, `get_success_rate` None below MIN_OUTCOME_SAMPLES; never raises → empty plan); `setup_plan.py` (`plan_to_raw_data` emits the raw_data dict the funnel consumes incl. confidence + validation_targets; `rejected_to_json`); `setup_ai_audit.py` (`AuditStatus` APPROVED/APPROVED_WITH_WARNINGS/REJECTED/NEEDS_MORE_DATA + `AuditResult`; `build_audit_prompt` 8 labelled sections; `parse_audit_response(text, canonical_params)` STRIPS any canonical param key + logs stripped_fields, unknown status → NEEDS_MORE_DATA, never raises; `map_audit_to_finaliser` — REJECTED/NEEDS_MORE_DATA + no blocking → approved_with_warnings advisory, a blocking engineering failure ALWAYS wins). Constants in `_setup_constants.py`: `RULE_ENGINE_VERSION="42.0"`, `MIN_OUTCOME_SAMPLES=3`, `LOW_SUCCESS_RATE=0.40`, `AI_AUDIT_REJECTED_ADVISORY="ai_audit_rejected_advisory"` (NOT in APPROVED_STATUSES). VOICE PATH constrained to NARRATION-ONLY via `_strip_actionable_for_voice(data)` (zeroes changes/setup_fields pre-normalisation); full voice rule-first rebuild deferred. DB v11 (`data/session_db.py::_migrate_v11`) adds 8 nullable TEXT cols to `setup_recommendations` (deterministic_plan_json, ai_audit_json, validation_status, approved_changes_json, rejected_changes_json, diagnosis_json, driver_profile_version, rule_engine_version), blob preserved + now POPULATED on insert (`_rec_parser.py` + `insert_setup_recommendations`). LEGACY SAFETY (closes Group 41's caveat): `data/setup_history.py` adds `is_legacy_unknown`/`normalise_validation_status`/`LEGACY_UNKNOWN` — absent/None/unrecognised status → legacy_unknown = DISPLAY-ONLY, NO Apply (previously could default to approved). LEARNING: `RuleOutcomeStore` FOUNDATION ONLY (downgrade hook implemented + unit-tested, live wiring + persistence DEFERRED, `rule_outcome_store=None`; no fake ML). UI (`ui/setup_builder_ui.py::_display_setup_result` + `ui/setup_form_widget.py`): diagnosis → "Pit Crew recommendation" (approved changes + collapsed "Why Pit Crew recommended this": symptom/rationale/evidence/rejected_alternatives/risk_level/confidence_level/driver_style_alignment) → "Protected fields" → "Rejected candidate changes" → "AI audit" → "Rejected AI output — not for use"; legacy banner; Apply relabelled "Apply Pit Crew recommendation", hidden unless status ∈ APPROVED_STATUSES AND approved changes present AND not legacy. RESPONSE CONTRACT: per-change keys inside each `changes` item (symptom, evidence, rule_id, rationale, rejected_alternatives, risk_level, confidence_level, driver_style_alignment) + new top-level `ai_audit`/`deterministic_plan`/`protected_fields`. New suites `tests/test_group42_rule_first_engine.py`, `test_group42_ai_audit_only.py`, `test_group42_driver_style.py`, `test_group42_legacy_storage.py`, `test_group42_handling_phases.py`, `test_group42_voice_path_safety.py`, `test_group42_ui_gate.py` (136 new) + 17 rewritten (test_group38 TestRegenerateOnceOrchestration, test_group40 TestAC9DeterministicFallback, test_group41 ×2, test_group27 ×1). All green, zero new regressions; the SAME 8 pre-existing frozen-allowlist track-modelling guards remain (unrelated). Run tests in halves on Win/Py3.14 (flaky PyQt teardown segfault). `docs/RULE_FIRST_SETUP_BRAIN.md` (NEW architecture doc), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42), `docs/UAT_SETUP_BRAIN.md` (Rule-First section). See "Rule-First Setup Brain (Group 42)" at the end of this file.)
> Prior: 2026-07-05 (**Group 41 — Setup Builder Engineering Validation Gate** — backend + UI. `strategy/setup_diagnosis.py` + `strategy/driving_advisor.py` + `strategy/_setup_constants.py` (NEW) + `strategy/_rec_parser.py` + `data/setup_history.py` + `ui/setup_builder_ui.py`. RECOMMENDATION LIFECYCLE with explicit statuses (generated, validation_failed, retry_requested, retry_failed, approved, approved_with_warnings, fallback_generated, blocked_no_safe_recommendation; `APPROVED_STATUSES = {approved, approved_with_warnings, fallback_generated}` in `_setup_constants.py`). SINGLE FINALISATION FUNNEL `_finalise_recommendation` in driving_advisor.py — BOTH AI paths (`build_setup_advice_response`, `build_combined_setup_response`) route through it, producing a frozen `SetupRecommendationResult` dataclass (status/approved_changes/approved_fields/rejected_changes/analysis/primary_issue/engineering_errors/validation_warnings/fallback_used/raw_json), embedded into the returned JSON (keys: recommendation_status, changes, setup_fields, rejected_changes, engineering_validation_errors, validation_warnings, fallback_used). DISPLAY SAFETY (`ui/setup_builder_ui.py::_display_setup_result`): "CHANGES TO MAKE IN CAR SETUP" renders ONLY when status ∈ APPROVED_STATUSES and approved_changes non-empty (iterates approved_changes only); Apply button HIDDEN (not disabled) unless approved-ish with non-empty approved_fields, applies approved_fields only via `SetupFormWidget.apply_ai_fields`; rejected output only in a collapsed "Rejected AI output — not for use" section (validation_failed/retry_failed/blocked_no_safe_recommendation), no apply path. VALIDATOR SEVERITY: `ValidationFailure(code, message, severity)` + `validate_setup_engineering_structured()` (legacy `validate_setup_engineering` still returns byte-identical prefixed strings); ANY blocking-severity failure (safety-prefix OR structural — malformed_schema/invalid_units/locked-field) forces validation_failed (retry_failed if retried) + approved_changes=[]; out-of-range is a WARNING (clamping forces the applied value back in range). NEW BLOCKING RULES: `snap_throttle_lsd_accel_gate` (snap_throttle_induced + lsd_accel > 4), `kerb_strike_rh_over_increment` (kerb_strike bottoming + rear RH increase > 3mm), `gearbox_fake_field` (transmission_max_speed_kmh used as actionable), `gearbox_ratio_inversion` (a gear ratio not strictly lower than the gear below). NEW WARNING: `gearbox_out_of_range` (final_drive outside 2.5–6.0 or any gear outside 0.5–4.0 — conservative invented constants pending per-car ranges). REAL GEARBOX FIELDS: final_drive + gear_1..gear_6 now actionable (added to `_CANONICAL_SETUP_PARAMS` + `_CAT_FIELDS["transmission"]`; `_normalise_changes` expands `gear_ratios:[...]` into gear_N keys; surfaced/applied via SetupFormWidget); transmission_max_speed_kmh DEMOTED to display-only (`_DISPLAY_ONLY_FIELDS`) — readable for diagnosis/top-speed classification, stripped from approved output, never an actionable change; `gearbox_category_mismatch` now also blocks final_drive/gear_1..6 on a preserve gearing category. STRICT RETRY CONTRACT: `_build_retry_prompt` lists each blocking failure code + max delta + forbidden fields + forbids repeating rejected changes; a retry with any blocking failure becomes retry_failed (never approved); banner reworded "AI recommendation rejected after retry" (was "survived a correction attempt"). DETERMINISTIC FALLBACK ENGINE (`_build_deterministic_fallback`) now emits 1–3 real conservative changes that pass the same validator (respecting RH-increment/LSD-subtype/rake gates); if nothing safe → blocked_no_safe_recommendation + "run more laps". PERSISTENCE respects validation state: `data/setup_history.py::save_entry` takes `validation_status` and routes non-approved to a `_rejected_<config_id>` diagnostic bucket; DB `setup_recommendations` row now carries the final lifecycle status (`_rec_parser.py` extracts recommendation_status, was default 'proposed'). WORDING/LOGIC FIXES: kerb_strike bottoming described distinctly from true floor contact (no longer forces RH "required"); snap_throttle_induced no longer asserts "inside rear spins" (no telemetry), classified mixed setup/driver; old "top speed below target ⇒ no gearing change" leakage removed (gearing can change on power-band/driver evidence, display-only caveat on transmission_max_speed_kmh). `_ENG_SAFETY_PREFIXES` deduplicated to shared `ENG_SAFETY_PREFIXES` in `_setup_constants.py` (imported by driving_advisor + setup_diagnosis). AMENDMENT B (UI real-estate): the redundant read-only "Race Conditions (from Event Planner)" group box removed from the Setup Builder header (duplicated Event Planner + Home Race Setup card, same EventContext); 320px header cap lifted; `_sync_setup_builder_from_event` retains all functional side effects (BoP toggle, permissions, spinbox rebind, RE-brief load, prefill, qual-form sync). AMENDMENT C: Home "Race Setup" card now shows a Damage line (sourced from `EventContext.damage`). New suite `tests/test_group41_validation_gate.py` (AC0–AC14). **Full suite: 5505 pass / 8 fail / 6 skip** — the 8 fails are the SAME pre-existing frozen-allowlist guards (`ui/track_modelling_ui.py::_tm_restore_last_track`, unrelated track-modelling tech debt, NOT this sprint), zero new regressions. NOTE: running the ENTIRE suite in one process can hit a flaky native PyQt teardown segfault on Windows/Python 3.14; running in two halves (or by group) completes clean at 5505 pass / 8 pre-existing fail — an environmental test-isolation artifact, not a product defect. See "Setup Builder Engineering Validation Gate (Group 41)" at the end of this file.)
> Prior: 2026-07-05 (**Group 40 — Setup Diagnosis Hardening** — pure Python backend. `strategy/setup_diagnosis.py` + `strategy/driving_advisor.py`. NEW: `_classify_bottoming_confidence(...)` → `bottoming_confidence` dict (band/subtype/confidence); `_rh_permitted_increment(...)` — confidence-gated ride-height increment limiter; `_derive_driver_feel_traction_status(...)` → `driver_feel_traction_status` ("good"/"degraded"/"unknown"); `_build_deterministic_fallback(...)` — safe no-change response for engineering-retry failures; `aero_rear_healthy` bool (fraction-of-max threshold, 0.80*hi, no false positives on generic-range cars). NEW VALIDATION RULES: `rh_increment_exceeds_confidence` (composes with rh_for_minor_bottoming), `rh_rake_risk` (rear delta >= 4mm without front change), `lsd_large_change_gated` (subtype-gated LSD increase cap), `lsd_blocked_driver_feel` (traction good + LSD increase blocked). HARDENED: `lsd_reversal_without_evidence` now requires delta >= 5 AND includes `delta=N` in reason string. `_derive_dominant_problem` + `_derive_tuning_priority` both respect `aero_rear_healthy` (skip rear-aero priority when near-max). `format_diagnosis_for_prompt` renders all three new keys with AI-directive text. `_validate_setup_response` gains `rh_rake_risk` structural check (> 3mm rear-only). CONSERVATIVE DICT updated with all three new keys. New tests: `test_group40` (test-verifier, S1–S10 + AC9 fallback + key parity). **Full suite: 5359 pass / 6 skip / 8 fail** — same 8 pre-existing frozen-allowlist failures, zero new regressions.)
> Prior: 2026-07-05 (**Setup Brain Upgrade — Professional Race Engineer Diagnosis** — the setup-diagnosis brain (`strategy/setup_diagnosis.py`) now reasons about WHY a symptom appears before the AI touches a setup; backend-only, no UI surface, branch `ofr2-quali-race-disciplines` (on top of OFR-2). Two production files: `strategy/setup_diagnosis.py` + `strategy/driving_advisor.py`. NEW app-side GEARING DIAGNOSIS `_classify_gearing(...)` → `gearing_diagnosis_category` (7 categories) via a priority decision table, fed by the new pure `_derive_top_gear_frame_signals(frames, top_gear)` over ~10Hz `LapStats.frames`. The flawed rule REMOVED (the `gear_note` "Do NOT lengthen gears" block, old `DRIVER_HARD_CONSTRAINTS` #8 → now 8, `gearbox_edit_when_preserve`) → replaced by `gearbox_category_mismatch` (Fuji RSR power-band now ALLOWS a gearbox change). NEW `_classify_wheelspin_subtype(...)` → `wheelspin_subtype` (7 values) with honest deferrals (`inside_wheel_spin` NEVER emitted — no per-wheel slip; `rear_platform_stiffness` folds into mixed; kerb_unload_spin is a kerb-count proxy). NEW `compliance_priority` bool (`_detect_compliance_priority`) raises natural-freq/damping UNPROMPTED. Dominant re-order (severe wheelspin > "consider" bottoming). LSD ANTI-OSCILLATION `validate_setup_engineering`+`rec_history`+rule `lsd_reversal_without_evidence` (rec_history resolved by the CALLER from STRUCTURED `data/setup_history.json` + DB `worsened` verdict — no new config["strategy"] read). FEEDBACK CHRONOLOGY: `_get_driver_feedback_context` splits Latest vs Earlier with trend tags via `DrivingAdvisor._feedback_trend_tag`. SCHEMA FIX: `not-present` added to `issue_classification`. New keys present on the conservative/error path too. New tests `tests/test_group39_setup_brain_upgrade.py` (~72, AC1–AC9 + frame-signal units); 4 re-pointed in `tests/test_group38_setup_diagnosis.py` (constraint 9→8, rule rename). `docs/SETUP_BRAIN_UPGRADE.md` (NEW). **Full suite: 5356 pass / 6 skip / 8 fail** — the 8 fails are ALL pre-existing frozen-allowlist guards from the already-committed `ui/track_modelling_ui.py::_tm_restore_last_track` config["strategy"] consumer (unrelated track-modelling tech debt, NOT this sprint); ~72 new tests green, zero regressions. See "Setup Brain Upgrade" at the end of this file.)
> Prior: 2026-07-03 (**Tab Navigation Refactor — Named Tab Lookup** — retires the hard-coded tab-index risk flagged since the Product Consolidation audit. New **`ui/tab_registry.py`** (pure, no PyQt6): one stable key per existing tab (`TAB_LIVE`…`TAB_HOME`), `DEFAULT_TAB_ORDER` = the current visual order 0–13 in one place (a source-scan test proves it mirrors the real addTab sequence; a runtime count check warns on drift), `TabRegistry` key↔index mapping that never raises on bad input, `key_for_title()` ⚙-decoration-safe reverse lookup, `TAB_BASE_TITLES` cross-checked against `product_flow.TAB_ROLES`. `ui/dashboard.py`: **`_on_tab_changed` dispatches by stable key** (same 8 activation behaviours, zero `index == N` comparisons); navigation helpers `get_tab_index`/`has_tab`/`current_tab_key`/`select_tab` (all safe on unknown keys; `select_tab` holds the only remaining `_tabs.setCurrentIndex` call site); the 3 jump sites now `select_tab(TAB_PRACTICE_REVIEW/TAB_SETUP_BUILDER/TAB_EVENT_PLANNER)`; visibility guards use `current_tab_key() != TAB_AI_LOG/TAB_HOME`; `_home_tab_index` retired. **Tab order byte-identical (all 14 addTab lines pinned), Home stays appended at 13, diagnostic tabs + ⚙ markers unchanged, no logic/prompt/mapping/PTT/voice/persistence/fan-out change.** New tests `test_tab_navigation_registry.py` (33); 6 legacy tests updated in place to the key-based home (group12c AI-Log dispatch, group14 DEF-P2-033 flush guard ×2, group3 history→Practice-Review jump, diagnostic-cleanup + home-dashboard dispatch scans). **Full suite: 4512 pass / 6 skip / 0 fail.** See "Tab Navigation Refactor" at the end of this file.)
> Prior: 2026-07-03 (**Diagnostic Tab Cleanup — Low-Risk UI Dags Removal** — executes the Product Consolidation Audit's §9 items 1/3/4. DELETED: the 7 hidden, never-signal-connected legacy per-segment review buttons + their unreachable `_tm_review_*` handlers + `_tm_refresh_review_buttons`/no-op `_tm_refresh_approval_panel` + 8 dead imports + 4 never-applied style strings (`ui/track_modelling_ui.py`; pure review functions in `data/track_segment_review.py` retained); the dead, never-rendered `_TELEMETRY_REFERENCE_HTML` constant. RENAMED: "Race Config ID" → **"Session Match Key"**; Diagnostics "Rem(clk)"/"rem_ms(raw)"/"Ann queue" → "Time left:"/"remaining_time_ms:"/"Voice queue:"; window title + Guide h1 → **"Next Gear Racing Pit Crew"**. GUIDE FIXED: stale Step 8 (described a "Dashboard" tab with quick-links that never existed) now describes the real Home tab; API-key bullet now points at the Strategy Builder field (audit's "Settings duplicate" claim corrected — no Settings key field exists); new "Tool tabs (⚙) … safe to ignore" note; "pip install" tooltip line removed. NO CHANGE to tab order, `_on_tab_changed` indices, Home Dashboard, diagnostic tabs, any logic/prompt/mapping/PTT/voice/persistence, or the two `config["strategy"]` fan-outs (pinned by test). New tests `test_diagnostic_tab_cleanup.py` (25); `test_group24` `_tm_` floor 54→46 (9 deleted methods enumerated). **Full suite: 4479 pass / 6 skip / 0 fail.** See "Diagnostic Tab Cleanup" at the end of this file.)
> Prior: 2026-07-03 (**Home Dashboard Build — Race Engineer Command Centre** — the missing home/overview surface (REQUIREMENTS.md §12.2, audit §1.1) is now built. New `ui/home_dashboard_vm.py` (pure Python — `HomeDashboardState`/`HomeDashboardCard`/`HomeDashboardStatus`/`HomeDashboardWarning`/`HomeDashboardNextAction`; `build_home_dashboard_state()` never raises; six sections: Race Setup / Track Intelligence / Setup Brain / Strategy Brain / AI Input Safety / Next Best Action, all read from the four canonical contexts + the AI snapshot core + `build_flow_state_summary()`). New **Home tab APPENDED at index 13** (`_build_home_tab` — indices 0–12 and `_on_tab_changed` dispatches unchanged; no tab reordered/renamed/removed); refresh on tab-shown + guarded `_home_refresh_if_visible()` hooks after event set-active / `_update_race_config` / setup result display / track-truth refresh — no polling, no new workers. Display-only: source-scans prove the home methods write nothing (no config["strategy"], no persist, no DB/file writes). Stale indicators surfaced in plain English (setup-vs-event, setup-vs-strategy, strategy-vs-event, track mismatch, AI legacy fallback). New tests `test_home_dashboard_vm.py` (52). **Full suite: 4454 pass / 6 skip / 0 fail.** See "Home Dashboard Build" at the end of this file.)
> Prior: 2026-07-03 (**AI Snapshot Migration — Frozen Context Inputs** — `data/ai_context_snapshot.py` threads frozen, owner-documented snapshots of the four canonical contexts into the AI-input paths: `StrategyAISnapshot`/`PracticeAnalysisSnapshot` race-params (each path's exact legacy defaults preserved, incl. DEF-P1-005 practice tuning-absent→LOCKED) + `SetupAISnapshot` (build-setup 0.0 defaults); byte-identical to the verbatim legacy expressions when stores are in sync — proven incl. a byte-identical `_build_race_prompt` text test; documented intentional difference: fresh DB event values supersede stale fan-out copies; staleness (strategy/setup/track vs event) detected at build time and printed under GT7_AI_DEBUG. Migrated: `_assemble_strategy_inputs`, `_run_ai_analysis`, `_run_practice_analysis`, `_run_build_setup` (+ frozen worker-thread rec metadata), `_setup_analyse_ai`. No prompt wording/intelligence changed; all legacy stores retained. New tests `test_ai_context_snapshot.py` (41); 20 legacy source-scans updated in place. **Full suite: 4402 pass / 6 skip / 0 fail.** See "AI Snapshot Migration" at the end of this file.)
> Prior: 2026-07-03 (**State Consolidation 4 — TrackContext** — canonical track/layout read model `data/track_context.py` owning identity (ids/display names/combined id, priority TM-combos → EventContext → config ids → seed) + model-artefact availability (seed metadata/corner windows/coordinate geometry/reference path/calibration laps/station map/reviewed+accepted model/lap offset — flags echo the existing audits, no geometry truth invented) + modelling/alignment/lap-offset status, keyed to `EventContext.change_hash` with tri-state `matches_event` / `mismatches_event` / `is_stale_for_event` / live-mapping gate helpers; `docs/TRACK_CONTEXT_MIGRATION.md` registers all 16 track state stores with duplication verdicts; migrated `_tm_refresh_track_truth_panel` identity (combo-sourced, behaviour-preserving) + `_last_track_context` captured. All legacy track files/loaders/resolver/calibration code retained. New tests `test_track_context.py` (68). **Full suite: 4361 pass / 6 skip / 0 fail.** See "State Consolidation 4 — TrackContext" at the end of this file.)
> Prior: 2026-07-03 (**State Consolidation 3 — SetupContext** — canonical setup-recommendation read model `data/setup_context.py` owning purpose / source / adjustments / baseline+target setup / confidence / validation, keyed to `EventContext.change_hash` + `StrategyPromptSnapshot.snapshot_id` so stale setups are detectable (reads event/strategy only as keys, never duplicating them); `SetupPromptSnapshot` freezes a consistent setup+event+strategy state for a future AI prompt; `docs/SETUP_CONTEXT_MIGRATION.md` registers every setup store; migrated `_setup_type_prefix` (purpose) + `_display_setup_result` captures the context. Legacy setup config/DB storage retained. New tests `test_setup_context.py` (67). **Full suite: 4293 pass / 6 skip / 0 fail.** See "State Consolidation 3 — SetupContext" at the end of this file.)
> Prior: 2026-07-03 (**State Consolidation 2 — StrategyContext** — canonical strategy-plan read model `data/strategy_context.py` owning stint plan / stops / fuel burn / `config_id` / degradation assumptions / tolerances, reading event/race rules from EventContext (never duplicating them); `StrategyPromptSnapshot` freezes a consistent event+strategy state for AI prompts; `docs/STRATEGY_CONTEXT_MIGRATION.md` registers every strategy-specific dependency; one low-risk consumer migrated (`_refresh_lap_bank` config_id ★). `config["strategy"]` retained as legacy compatibility. New tests `test_strategy_context.py` (53). **Full suite: 4226 pass / 6 skip / 0 fail.** See "State Consolidation 2 — StrategyContext" at the end of this file.)
> Prior: 2026-07-03 (**State Consolidation 1 — EventContext** — canonical event/race read model `data/event_context.py` normalising the DB-event and `config["strategy"]` schemas; `docs/EVENT_CONTEXT_MIGRATION.md` registers every `config["strategy"]` dependency; one low-risk consumer migrated (`_refresh_telemetry_context`). `config["strategy"]` retained as legacy compatibility. New tests `test_event_context.py` (38). **Full suite: 4173 pass / 6 skip / 0 fail.** See "State Consolidation 1 — EventContext" at the end of this file.)
> Prior: 2026-07-03 (**Product Consolidation Sprint** — audit + safe first-pass UI clean-up. New `docs/PRODUCT_CONSOLIDATION_AUDIT.md` + `ui/product_flow.py` (single-source tab roles / 13-step journey / `build_flow_state_summary()`); "Debug"→"Diagnostics" tab, ⚙ tool-tab markers, Track Modelling "5. Seed Geometry" / "Track Model Status" renames. No feature added, no backend removed, no tab reordered. New tests `test_consolidation_product_flow.py` (27). **Full suite: 4135 pass / 6 skip / 0 fail.** See "Product Consolidation Sprint" at the end of this file.)
> Prior: 2026-07-03 (DEF-17U-UAT-007: Time Trial calibration laps falsely classified as pit-in / unusable — **FIXED**. Pit-in detection now OFF by default (`build_reference_path(..., pit_detection_enabled=False)`); new `PARTIAL_START` / `PARTIAL_STOP` lap quality so mid-lap start/stop slices no longer block valid laps. New tests: `test_def17u_uat007_calibration_build.py` (~35), `test_def17u_uat007_partial_laps.py` (44). **Full suite: 4200+ passed** (only failing test `test_group28_analyse_prompt_ranges` is a pre-existing, unrelated failure). See "DEF-17U-UAT-007" at the end of this file.
> Prior: 2026-07-03 (Group 18A: Track Truth Library, Calibration Wizard, Station-Based Map Matching Foundation — **4053 pass / 6 skip / 0 fail** — 45 new tests across `test_group18a_track_truth.py` (26), `test_group18a_track_truth_matcher.py` (9), `test_group18a_track_truth_calibration.py` (10). Foundation only — Setup/Strategy/Live-Engineer not yet rewired to consume `TrackTruthModel`. See "Group 18A — Track Truth Foundation" at the end of this file.
> Prior: 2026-07-02 (Integration: Setup Brain + Strategy Outcome — **3984 pass / 6 skip / 0 fail** — full combined suite, merged to `master` via `integration/setup-brain-strategy-overhaul` — merging `feature/setup-diagnosis-engine` + `feature/strategy-outcome-comparison`. Merged after automated tests passed; **runtime UAT still pending** (SETUP_BUILDER_UAT.md + STRATEGY_BUILDER_UAT.md). Remote https://github.com/leonpaczynski-netizen/ngr_pitcrew (`origin/master` at merge commit `7254835`). See "Integration — Setup Brain + Strategy Outcome" at the end of this file.
> Read PROJECT_STATE.md first, then this file, before touching any code.
>
> Note: detailed session notes for Groups 17P–25 live in `docs/CURRENT_CLAUDE_HANDOFF.md`. Groups 26–38 and the lettered groups (A/B/C/D/E) + Qualifying Mode are summarised at the end of this file under "Groups 26–38 + Lettered Groups (Strategy / Race-Engineer / Setup Overhaul)".

---

## Open Defects

### P1 Critical

---

**ID:** DEF-P1-001
**Title:** Session opens on first lap completion, not on mode selection
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_on_live_mode_changed()` in `ui/dashboard.py` now calls `_db.open_session()` immediately and pushes the session id to the dispatcher via `set_session_id()`. Auto-open logic removed from `EventDispatcher._dispatch()`. `EventDispatcher` gains a `tracker` parameter (fixes latent `AttributeError`). RACE_STARTED retains a fallback open only when `_session_id == 0`.
**Description:** `open_session()` was triggered by the EventDispatcher on the first LAP_COMPLETED event, not when the user selects a Live mode. `_autosave_db` was never set to `True` so the entire DB write path was dead code.
**Expected Behaviour:** When the user changes the Live tab mode selector (Practice / Qualifying / Race), the dashboard immediately calls `_db.open_session()` and stores the resulting `session_id`. All subsequent lap saves use that session. No lap is ever written with `session_id = 0`.
**Acceptance Criteria:**
- Select Practice mode on the Live tab before any lap has completed.
- Query `SELECT id, session_type FROM sessions ORDER BY id DESC LIMIT 1` — a row exists immediately (before any lap).
- Outlap is saved with the correct `session_id` and `session_type = 'practice'`.
- Switching from Practice to Race opens a new session row with `session_type = 'race'`.

---

**ID:** DEF-P1-002
**Title:** Outlaps silently discarded after pit exit
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** DEF-P1-001 fix (session opened on mode change) ensures `session_id > 0` when the outlap fires. The stale print statement in `_exit_pit()` corrected to read "will be recorded as out-lap". State.py already records outlaps with `is_out_lap=True`; the only barrier was `session_id == 0` causing `write_lap()` to be skipped — now resolved.
**Description:** `telemetry/state.py` detects an outlap after a pit exit and silently drops the lap record with a print statement. The lap time is non-zero and valid for tyre warm-up analysis. The spec requires outlaps to be recorded and labelled, not dropped.
**Expected Behaviour:** Outlaps are recorded with `is_out_lap = True` and written to `lap_records`. They are displayed in Practice Review with a visual indicator (e.g., "(out)" suffix or distinct row colour). The lap time is preserved for AI and tyre temperature analysis.
**Acceptance Criteria:**
- Complete an outlap after a pit stop in Practice mode.
- `SELECT lap_num, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` — the outlap row exists with `is_out_lap = 1`.
- Practice Review displays the outlap row with a distinct style or label.
- AI coaching does not use the outlap for pace benchmarking (excluded from best-lap calculations).

---

---

**ID:** DEF-P1-003
**Title:** Practice Review "Save Session" crashes with AttributeError on _lbl_bank_status
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_set_bank_status(self, msg: str)` helper with `hasattr` guard to `ui/dashboard.py`. Replaced all 20 bare `self._lbl_bank_status.setText(` calls throughout the file with `self._set_bank_status(` using replace_all. Method returns silently when `_lbl_bank_status` is absent. `_refresh_lap_bank()` already had its own guard and was unaffected.
**Reported:** 2026-06-21
**Root Cause:** SUP-002 (P6-A) removed `_build_practice_lap_bank_group()`, which created `self._lbl_bank_status` at line 3680. The "Save Session" button at line 6298 still calls `_save_session_to_db()`, which references `self._lbl_bank_status` at lines 2841, 2856, and 2865 without a `hasattr` guard. Only the early-exit path at lines 2817/2822 has the guard. The first unguarded reference at line 2841 raises `AttributeError: 'MainWindow' object has no attribute '_lbl_bank_status'`.
**Description:** Clicking "Save Session" in Practice Review crashes the application. The status label widget was removed as part of the P6-A session-loader removal but the save method was not updated to match.
**Expected Behaviour:** Saving a session succeeds silently or displays a status message in an appropriate location. Application does not crash.
**Acceptance Criteria:**
- Click "Save Session" in Practice Review with at least one live lap in the table. Session is saved to DB. No crash.
- If save fails, an error is shown (QMessageBox or equivalent) rather than raising an unhandled exception.
- `SELECT * FROM sessions ORDER BY id DESC LIMIT 1` reflects the newly saved session.

---

**ID:** DEF-P1-004
**Title:** Practice Analysis AI prompt uses wrong race type — timed race shown as 1-lap race
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `race_type: str = "lap"` and `duration_mins: int = 0` optional fields to `RaceParams` dataclass in `strategy/ai_planner.py`. In `_run_practice_analysis()` (`ui/dashboard.py`), added `"race_type": _psc.get("race_type", "lap")` and `"duration_mins": int(_psc.get("race_duration_minutes", 0))` to the `race_params` dict. In `_build_practice_prompt()`, added `race_len_line` local variable that branches on `params.race_type`: timed → `"Race duration: {duration_mins} minutes (Timed Race)"`, lap → `"Race length: {total_laps} laps"`. Template uses `- {race_len_line}` instead of the hardcoded string.
**Reported:** 2026-06-21
**Related:** DEF-P3-004, Addendum A1
**Root Cause:** `RaceParams` dataclass (`ai_planner.py` line 69) has `total_laps: int` but no `race_type` or `duration_mins` field. `_run_practice_analysis()` (`dashboard.py` line 3096) always passes `total_laps = int(_psc.get("total_laps", 25))` regardless of race type. When the active event is a timed race, `total_laps` may be 1 (the laps spinbox default if the user never set it) or any incorrect value, because the laps field is not disabled for timed races (DEF-P3-004 unfixed). `_build_practice_session_prompt()` in `ai_planner.py` uses `params.total_laps` with no timed-race branch, producing "Race length: 1 laps" in the AI prompt.
**Description:** Event Planner is configured as Timed Race. Full Practice Analysis prompt tells the AI "Race length: 1 laps." All strategy recommendations are based on a 1-lap race rather than the correct duration. Confirmed by AI prompt evidence: "Race length: 1 laps."
**Expected Behaviour:** Practice Analysis prompt must respect the active event's race type. For timed races, prompt contains "Race duration: X minutes, Timed Race" and no lap count. For lap races, prompt contains "Race length: N laps."
**Acceptance Criteria:**
- Set Event Planner to Timed Race, 40 minutes. Set event active. Run Practice Analysis.
- AI prompt (via `GT7_AI_DEBUG=1`) contains "Timed Race" and "40 minutes" — not "1 laps."
- Set Event Planner to Lap Race, 25 laps. Set event active. Re-run. Prompt contains "25 laps."

---

**ID:** DEF-P1-005
**Title:** Practice Analysis AI prompt sends full setup including BoP-locked fields
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12a) — Root cause confirmed: `_psc.get("tuning", True)` default in `_run_practice_analysis()` caused tuning_locked=False when "tuning" key absent from config (old config, or silent exception). Changed to `False` default (absent key = locked = safe). Also fixed `except Exception: pass` → traceback logging. Debug print added (GT7_AI_DEBUG).
**Fix:** Added `tuning_locked: bool = False` and `allowed_tuning: list = field(default_factory=list)` to `RaceParams` dataclass. Added `_TUNING_CATEGORY_KEYS` and `_ALL_TUNING_CATS` constants to `ai_planner.py`. `_build_practice_prompt()` now: when `tuning_locked`, appends `## EVENT RULES — TUNING LOCKED` block and replaces setup block with locked notice; when `allowed_tuning` is set, appends `## EVENT TUNING RESTRICTIONS` block and filters setup dict to only pass allowed keys to `format_setup_for_prompt()`. `_run_practice_analysis()` in `dashboard.py` now populates `tuning_locked` and `allowed_tuning` from `_psc` (strategy config). See tests `TestBoPPromptRestrictions` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P2-007, Addendum A2
**Root Cause:** `_run_practice_analysis()` (`dashboard.py` line 3126) calls `self._current_setup_dict()` which returns ALL setup fields unconditionally. It does not pass `tuning_locked` or `allowed_tuning` to `analyse_practice_session()`. The `ai_planner.analyse_practice_session()` function has no parameters for BoP or tuning restrictions and builds its prompt without any constraint block. Contrast with `build_combined_setup_response()` in `driving_advisor.py` which does accept `allowed_tuning` and `tuning_locked`. The practice analysis is on a completely separate prompt-building path that has never had constraint injection implemented.
**Description:** Event is configured as BoP with tuning not allowed. The Practice Analysis AI prompt includes full setup fields: ride height, springs, dampers, ARB, camber, toe, aero, LSD, ballast, power restrictor, gear ratios. AI produces setup change recommendations for fields that are locked by BoP. Confirmed by AI prompt evidence showing full setup payload.
**Expected Behaviour:** When `_config["strategy"]["bop"] = True` and `tuning = False`, the practice analysis prompt excludes editable setup fields and contains a `## EVENT RULES — TUNING LOCKED` block instructing the AI to give driving advice only. When categories are partially restricted, only allowed fields are included.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Run Practice Analysis.
- Prompt debug output does not contain ride height, spring rate, aero, LSD, or gear ratio values as editable recommendations.
- Prompt contains "TUNING LOCKED" or equivalent instruction.
- AI response contains no suspension/aero/differential change recommendations.

---

**ID:** DEF-P1-006
**Title:** Tyre compound lap counts in AI prompt do not match Practice Review lap log
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Three-part fix: (1) `_add_bank_lap_row()` in `dashboard.py` now prefers the DB-supplied `compound` value over any existing `_lap_compound_tags` entry for the same lap number. (2) `_import_bank_session()` clears stale `_lap_compound_tags` entries for laps being loaded before populating them. (3) `get_session_laps()` in `session_db.py` already returns `compound`; `_add_bank_lap_row()` now correctly uses it. See `TestCompoundTagPreference` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P3-003, Addendum A4
**Root Cause:** `_run_practice_analysis()` (`dashboard.py` line 3107) reads compounds from `_compound_at_row(row)`, which reads the QComboBox widget at col 13. For laps loaded from History, `_add_bank_lap_row()` populates the compound from `lap.get("compound") or ""`. FIX-012 (AWR-005) added compound write to `write_lap()`, but AWR-005 has not been runtime-verified — compounds may not have been persisted to DB for the tested session. When loaded from history, laps with empty compound fall through to the `_lap_compound_tags` inheritance chain or `_default_lap_compound`, which may assign all laps the same default. Additionally, `_lap_compound_tags` persists across session loads and can carry stale data from a previous session, overriding the correct DB values for reloaded laps.
**Description:** Practice session contained significantly more laps on Racing Medium than Racing Soft. AI prompt reported RM: 7 laps, RS: 17 laps — approximately the reverse of actual. AI strategy was based on entirely wrong compound distribution. Confirmed by AI prompt evidence.
**Expected Behaviour:** `lap_data_by_compound` passed to AI must exactly match the compound assignment visible in the Practice Review lap table at the time the analysis is run.
**Acceptance Criteria:**
- Load a session with 15 RM laps and 7 RS laps into Practice Review. Verify visually in the table.
- Run Practice Analysis. Prompt (via debug) shows `"RM": 15, "RS": 7` (or equivalent names).
- Reloading the session does not change compound assignments.

---

**ID:** DEF-P1-007
**Title:** Strategy Builder fuel burn (3.0 L/lap) disagrees with Practice Review lap log (>4.0 L/lap)
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_loaded_session_avg_fuel: float = 0.0` attribute to `MainWindow`. `_import_bank_session()` computes the average fuel used across non-pit laps from the loaded session and stores it in `_loaded_session_avg_fuel`. `_computed_fuel_burn_lpl()` now uses a three-level priority: (1) `_loaded_session_avg_fuel` if > 0, (2) `self._tracker.avg_fuel_per_lap` if > 0, (3) config fallback. `_add_lap_row()` resets `_loaded_session_avg_fuel = 0.0` when a live lap arrives so the live tracker takes over. See `TestFuelBurnSource` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P2-009
**Root Cause:** DEF-P2-009 unified the fuel average display by pointing both sources to `tracker.avg_fuel_per_lap`. However, `tracker.avg_fuel_per_lap` only reflects laps from the **current live session** (accumulated since the last tracker reset). If the user loaded laps from History into Practice Review (FIX-013), those historical laps are in the table but are NOT fed into the tracker's rolling average. The tracker saw zero or few live laps (3.0 L/lap average from live), while the historical laps in the table show 4.0+ L/lap per row. The two values are from different data sources: tracker average = live session only; lap table col 8 = all rows including loaded historical laps.
**Description:** Strategy Builder Fuel Burn Auto shows 3.0 L/lap. Every lap row in Practice Review shows >4.0 L/lap fuel used. Single source of truth requirement is violated. AI prompt fuel burn and strategy recommendations are based on wrong data.
**Expected Behaviour:** The fuel burn shown in Strategy Builder must agree with the average fuel per lap derived from the laps currently visible in Practice Review. If historical laps are loaded, the fuel average must update to reflect them.
**Acceptance Criteria:**
- Load 10 historical laps averaging 4.2 L/lap into Practice Review.
- Strategy Builder Fuel Burn Auto updates to ~4.2 L/lap.
- Practice Analysis prompt receives ~4.2 L/lap as `fuel_burn`.
- Manually verify: `sum(col 8 values) / row_count` matches displayed average.

---

**ID:** DEF-P1-008
**Title:** Practice mode triggers RACE_FINISHED announcement after timed event duration elapses
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `and self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition at `telemetry/state.py` line 292. The condition now only fires when the session override is not PRACTICE. Race mode (`SessionType.RACE`) and unset override (None) still fire correctly.
**Reported:** 2026-06-21
**Root Cause:** `_on_event_set_active()` at `dashboard.py` line 7350 calls `tracker.set_race_config(RaceType.TIMED, duration_minutes=40)`, setting `_manual_race_type = RaceType.TIMED` and `_timed_race_duration_ms = 2,400,000 ms`. In practice mode, `_phase_transitions()` still transitions `PRE_RACE → RACING` when speed > 80 km/h and `_race_start_time = time.monotonic()` is set (line 512 in state.py) regardless of `_session_type_override`. After 40 minutes of practice, `computed_remaining_ms()` returns 0, satisfying the `RACE_FINISHED` conditions at state.py lines 289-302. The RACE_FINISHED event fires and the announcer says "Race ended at 40 minutes" during a Practice session.
**Description:** While running Practice Mode on the Live tab, the voice engineer announced "Race ended at 40 minutes." The active event was configured as a 40-minute timed race. The race timer fires correctly for an actual timed race, but it incorrectly fires during a Practice session when the same event is active.
**Expected Behaviour:** RACE_FINISHED logic must be suppressed entirely when `_session_type_override == SessionType.PRACTICE`. The race completion announcements, phase transition to FINISHED, and any post-race UI changes must not occur during practice regardless of the event's race type.
**Acceptance Criteria:**
- Set a 40-minute timed race event active. Switch Live tab to Practice mode. Run practice for 40+ minutes.
- No "Race finished" announcement. No `RACE_FINISHED` event in debug log.
- Switch to Race mode and start a timed session. After 40 minutes the announcement fires correctly.

---

**ID:** DEF-P1-009
**Title:** Event load does not restore saved Event variables (tyre_wear, fuel_mult, avail_tyres, req_tyres)
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix:** `_on_event_selected()` in `ui/dashboard.py`. Root cause: `_evt_tyre_wear`, `_evt_fuel_mult`, and `_evt_refuel_rate` are `QSpinBox` (integer-only) widgets, but the DB schema stores `tyre_wear`, `fuel_mult`, and `refuel_rate_lps` as `REAL` columns. SQLite returns `REAL` as Python `float`; PyQt6's `QSpinBox.setValue()` raises `TypeError` on a float argument. The broad `except Exception: pass` silently swallowed this error, leaving those spinboxes at their default value of 1 and preventing all subsequent field population (fuel_mult, avail_tyres, req_tyres, tuning categories, notes) from executing. Fix: wrapped all three REAL→QSpinBox assignments in `int(round(...))`. Secondary fix: changed `except Exception: pass` to `except Exception: import traceback; traceback.print_exc()` so future exceptions are visible. Tertiary fix: tuning permissions group visibility in `_on_event_selected` changed from `_bop_on and _tun_on` to `bool(_tun_on)` to match `_update_tuning_perms_visibility()`.
**Reported:** 2026-06-22 (UAT Group 2–4)
**Root Cause A:** Event persistence/reload broken
**Description:** When a previously saved event is selected in Event Planner, all form fields reset to their defaults instead of restoring the saved values. Affected fields: tyre wear multiplier, fuel multiplier, available tyres, required/mandatory tyres, tuning categories. Track, name, race type, laps, and duration loaded correctly (those spinboxes have INTEGER DB columns and Qt accepts int).
**Expected Behaviour:** Selecting a saved event from the Event Planner list restores all 17 fields to their saved values without requiring a "Set Active" click.
**Acceptance Criteria:**
- Save an event with Tyre Wear = 2, Fuel Mult = 3, Available = Racing Hard + Medium, Required = Racing Hard, BoP=On, Tuning=Off.
- Click the event in the list. Confirm all five fields restore to saved values (not defaults).
- Click "Set Active". Confirm Strategy Builder fuel multiplier shows ×3, tyre wear ×2.
- Verify `_config["strategy"]["tyre_wear_multiplier"] == 2` and `_config["strategy"]["fuel_mult"] == 3` in debug or by running Practice Analysis and checking the prompt.

---

**ID:** DEF-P1-010
**Title:** AI Debug / AI Log tab not visible after AI calls
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Reported:** 2026-06-22 (UAT Group 2)
**Root Cause C:** `call_api()` raised `RuntimeError` before reaching `_fire_log_hook()` when `GT7_AI_DEBUG=1` was set
**True Root Cause:** In `strategy/_ai_client.py`, the `if _AI_DEBUG:` block printed the prompt to stdout then raised `RuntimeError`. The `_fire_log_hook()` call is inside the `try/except` block that follows — unreachable when the RuntimeError is raised. Result: DB never written, bridge signal never emitted, AI Log tab empty for every intercepted call.
**Fix:** Added `_fire_log_hook(AILogEntry(..., success=False, error_msg="AI_DEBUG mode active..."))` immediately before the `raise RuntimeError` in the debug branch. Dry-run entries now appear in the AI Log tab with the full prompt captured.
**Description:** AI API calls succeed (strategy generates, driver feedback appears in AI prompt, PTT coaching returns responses), but nothing appears in the AI Log tab after any call. `GT7_AI_DEBUG=1` environment variable produces console output but not an AI Log entry. The log hook was never reached in debug mode.
**Expected Behaviour:** After any AI call (Practice Analysis, coaching, setup), the AI Log tab shows an entry with: model used, token count, prompt preview, response preview, and timestamp. With `GT7_AI_DEBUG=1` set, the AI Log tab shows a dry-run entry (success=False, error_msg="AI_DEBUG mode active...") with the full prompt captured.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1` (PowerShell). Run Practice Analysis or PTT coaching.
- Console output contains the full prompt text.
- Switch to AI Log tab. At least one entry exists with model, feature name, and success=✗.
- Click the entry — Prompt tab shows the full prompt text.
- `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.
- Without `GT7_AI_DEBUG`, make a real API call. AI Log shows a success entry with token count and cost.
**Blocked by:** None (independent of DEF-P1-009). Unblocks verification of DEF-P2-007, DEF-P2-016, DEF-P4-002.

---

**ID:** DEF-P1-011
**Title:** Strategy Builder Fuel Burn Auto shows stale "last session" value after switching events
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Reported:** 2026-06-22 (Phase 2 Smoke Test — user observed 3 L/lap matching event fuel_mult=3×)
**Root Cause:** `_on_event_set_active()` calls `_sync_setup_builder_from_event()` which only updates `_lbl_fuel_burn_display` when `tracker.avg_fuel_per_lap > 0`. When no live telemetry is active the label is left showing the persisted `config["strategy"]["fuel_burn_per_lap"]` value (e.g. 3.0 from a previous session) with the text "(last session)". The number coincidentally matched the fuel multiplier (both 3), causing user confusion.
**Fix:** Added reset block at the end of `_on_event_set_active()` (after `_sync_setup_builder_from_event()`). When both `tracker.avg_fuel_per_lap <= 0` AND `_loaded_session_avg_fuel <= 0`, `_lbl_fuel_burn_display` is reset to "— (complete practice laps to calibrate)". Live-data and loaded-session cases are preserved.
**Expected Behaviour:** After clicking Set Active on a new event with no live telemetry and no historical session loaded, the Fuel Burn Auto label shows "— (complete practice laps to calibrate)", not a stale numeric value from a previous session.
**Acceptance Criteria:**
- Ensure no live GT7 connection and no session loaded in Practice Review.
- Create a new event with Fuel Multiplier = 3×. Click Set Active.
- Navigate to Strategy Builder. Fuel Burn Auto shows "— (complete practice laps to calibrate)", not "3.00 L/lap (last session)".
- Load a historical session from History tab. Fuel Burn Auto updates to "X.XX L/lap (loaded session)".
**AWR:** AWR-040
**Group:** 11

---

### P2 High

---

**ID:** DEF-P2-001
**Title:** Practice mode laps recorded with session_type = 'race'
**Status:** Verified Fixed — 2026-06-21 (developer confirmed practice sessions appear as Practice in Practice Review)
**Fix:** `_on_live_mode_changed()` now calls `tracker.set_session_type_override()` (already did this) AND opens the session with the correct type string ("practice"/"qualifying"/"race"). The session type passed to `open_session()` now comes from the mode selector, not from a hardcoded string inside the dispatcher. At startup `_on_live_mode_changed()` is already called with the saved mode (line 499 in dashboard.py).
**Description:** `LapRecord.session_type` was derived from `_race_is_active` in `telemetry/state.py`. If a race session completed and the user switched to Practice, `_race_is_active` remained True. Practice laps were written with `session_type = 'race'`.
**Expected Behaviour:** The session type written to `lap_records.session_type` always matches the Live tab mode selector at the time the lap is completed.
**Acceptance Criteria:**
- Set Live tab to Practice. Complete two laps. `SELECT session_type FROM lap_records ORDER BY id DESC LIMIT 2` — both rows return `'practice'`.
- Switch to Race mode. Complete one lap. That row returns `'race'`.
- No lap written with `session_type = 'race'` when the mode selector shows Practice.

---

**ID:** DEF-P2-002
**Title:** Fuel-low and pit voice alerts fire during Practice sessions
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_on_pit()` and `_on_fuel_low()` in `voice/announcer.py` now guard `in ("practice", "qualifying")` instead of `== "practice"`. Both alerts are suppressed in Practice and Qualifying modes; Race mode still fires them. Qualifying was also unguarded — fixed in the same change.
**Description:** `VoiceAnnouncer._on_pit()` and `_on_fuel_low()` have no session-mode guard. Both alerts fire regardless of whether the current Live mode is Practice, Qualifying, or Race. In Practice these alerts are distracting and irrelevant.
**Expected Behaviour:** Fuel-low and pit advice alerts are suppressed when `_session_mode == 'practice'`. All other voice features (coaching, PTT responses, lap time announcements) remain active in Practice mode.
**Acceptance Criteria:**
- Set Live tab to Practice. Drop fuel to below the low-fuel threshold mid-lap. No fuel-low alert is spoken.
- Cross the pit entry line in Practice. No pit box advice is spoken.
- Switch to Race. Same fuel level — fuel-low alert fires as expected.
See `TestPitFuelAlertSuppression` in `test_group5_fixes.py`.

---

**ID:** DEF-P2-003
**Title:** Required Tyres field is a single dropdown, not a checkbox subset of Available Tyres
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. `_req_tyre_checks` checkbox grid was already implemented in `_build_event_planner_tab()`. `_avail_toggled()` callback enforces the subset rule. `_on_event_save()` writes a JSON list to `req_tyres`. `_on_event_selected()` restores checkboxes from the list with backward-compat string fallback. `_on_event_set_active()` writes `required_tyres` list and `mandatory_compounds` string to strategy config. See `TestRegisterCorrections` in `test_group6_fixes.py`.
**Description:** The Event Planner "Required Tyre" field is a single `QComboBox`. The spec requires a checkbox grid matching the Available Tyres selection. Required tyres must always be a subset of available tyres — enabling a compound as Required that is not Available must be prevented at the UI level.
**Expected Behaviour:** Required Tyres is a checkbox grid. Each compound is enabled only when that compound is also checked in Available Tyres. Unchecking an Available Tyre automatically unchecks the same compound in Required Tyres. Multiple required tyres can be selected simultaneously.
**Acceptance Criteria:**
- Enable Racing Hard and Racing Medium in Available Tyres. Both Required Tyres checkboxes become enabled.
- Uncheck Racing Hard in Available. Racing Hard Required checkbox is automatically unchecked and disabled.
- Save the event. `SELECT req_tyres FROM events WHERE name = ?` returns a JSON array of the checked codes.
- Load the event. Required Tyre checkboxes restore to the saved state.

---

**ID:** DEF-P2-004
**Title:** Setup Builder contains a BoP checkbox duplicating Event Planner
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_chk_bop` was removed from Setup Builder (no longer in source). `_current_setup_dict()` reads `bop_race` from `_config["strategy"]["bop"]`. `_get_bop_data_for_car()` reads from the same source. Race Conditions group has `_lbl_rc_bop` and `_lbl_rc_tuning` read-only labels populated by `_sync_setup_builder_from_event()`. `_on_event_set_active()` writes `strat["bop"]` from `_evt_bop`. See `TestBoPSourceOfTruth` in `test_group4_fixes.py`.
**Description (original):** `_chk_bop` in the Setup Builder allowed the user to manually toggle BoP independently of the active Event. This created a split source of truth.

---

**ID:** DEF-P2-005
**Title:** Tuning Permissions group only appears when BoP is ALSO enabled — not when Tuning is checked alone
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_update_tuning_perms_visibility()` in `dashboard.py` changed from `show = self._evt_bop.isChecked() and self._evt_tuning.isChecked()` to `show = self._evt_tuning.isChecked()`. The Tuning Permissions group now appears whenever "Tuning allowed" is checked, regardless of BoP state. See `TestTuningPermissionsVisibility` in `test_group4_fixes.py`.
**Root Cause:** The visibility condition incorrectly required both checkboxes. Tuning restrictions can apply without BoP (e.g., series-mandated category restrictions in non-BoP classes).

---

**ID:** DEF-P2-006
**Title:** Setup Builder does not enforce tuning permissions — all fields editable under BoP lock
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** After `_sync_setup_builder_from_event()` in `_on_event_set_active()`, an explicit unconditional call to `_apply_setup_permissions(strat.get("bop", False), strat.get("tuning", True), strat.get("allowed_tuning_categories", []))` was added. Belt-and-suspenders call fires regardless of DB lookup result.
**Description:** When an Event has BoP enabled with tuning not permitted, Setup Builder displays all fields as editable. There is no locked banner, no per-category disabling, and no warning that setup changes are not allowed for this event.
**Expected Behaviour:** `_apply_setup_permissions(bop, tuning_allowed, allowed_cats)` is called whenever the active event changes. When `tuning_allowed = False`, all setup fields except tyre dropdowns and metadata are disabled and a banner is shown. When categories are restricted, only those fields are enabled. Tyre dropdowns are always enabled regardless of BoP status.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Set it active. Setup Builder shows the locked banner. All spinboxes and dropdowns (except tyre compound) are disabled.
- Set Event with BoP=On, Tuning=Yes, Allowed=Suspension+BrakeBalance. Only suspension and brake balance fields are editable. Tyre dropdowns remain enabled.
- Set Event with BoP=Off. All fields are editable.

---

**ID:** DEF-P2-007
**Title:** AI coaching and setup advice does not respect tuning lock
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix (three parts):**
1. **Prompt constraint injection**: `_tuning_constraint_block()` in `driving_advisor.py` injects either `## EVENT RULES — TUNING LOCKED` (full lock) or `## EVENT TUNING RESTRICTIONS` (partial) into all prompt builders. All three advisor methods (`build_coaching_response`, `build_setup_advice_response`, `build_combined_setup_response`) accept and pass `tuning_locked` and `allowed_tuning`.
2. **Caller propagation**: `_setup_analyse_ai()` reads `_config["strategy"]["allowed_tuning_categories"]` and `tuning` flag and passes them. `_run_practice_analysis()` includes them in `RaceParams`. `query_listener.py` coaching and setup_advice paths read and pass both params.
3. **AI output validation**: `validate_ai_setup_response(response, tuning_locked, allowed_tuning)` added to `ai_planner.py`. Detects violations (locked-category keyword + action verb within 200 chars) and returns a list of violated category codes. `_display_setup_result()` and `_display_practice_results()` in `dashboard.py` both call the validator and prepend an amber warning banner if violations are detected.
See `TestAITuningConstraintPropagation` and `TestAIOutputValidation` in `test_group4_fixes.py`.

---

**ID:** DEF-P2-008
**Title:** PTT speech-to-text does not function reliably in Practice mode
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Source scan confirmed: (1) `main.py` starts `QueryListener` unconditionally at line 566 — no mode gate; (2) `_handle_trigger()` already has `try/except Exception` with `traceback.print_exc()` and `_emit_ptt_status(f"PTT ERROR: {_e}")`; (3) `_handle_trigger_inner()` has no session_mode guard — PTT responds in all modes. No code change required; defect was a documentation gap.
**Description:** PTT trigger fires (keyboard listener active) but `_handle_trigger()` may fail silently in Practice mode. No debug output confirms whether the failure is in transcription, intent routing, or AI call. The QueryListener may not be started for all Live modes.
**Expected Behaviour:** PTT works identically in Practice, Qualifying, and Race modes. Debug tab shows PTT status transitions: TRANSMITTING → PROCESSING → RADIO READY (or ERROR with traceback). `QueryListener` is started unconditionally at app startup regardless of initial Live mode.
**Acceptance Criteria:**
- Switch Live tab to Practice. Press PTT key. Debug tab shows "TRANSMITTING".
- Speak a coaching query. Debug tab shows "PROCESSING" then "RADIO READY".
- AI response is spoken and logged to AI log.
- If transcription fails, Debug tab shows "ERROR: <reason>" with traceback.
See `TestPTTPracticeMode` in `test_group5_fixes.py`.

---

**ID:** DEF-P2-009
**Title:** Fuel Burn Auto shows stale value after session reload from History
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix (Group 8):** Both `_on_history_load_session()` and `_import_bank_session()` in `dashboard.py` now update `_lbl_fuel_burn_display` immediately after computing `_loaded_session_avg_fuel`. Previously the label was only set at widget creation time (startup) and was never refreshed after a History reload. Fix: `if hasattr(self, "_lbl_fuel_burn_display") and self._loaded_session_avg_fuel > 0: self._lbl_fuel_burn_display.setText(f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")`. Fuel average correctly excludes pit laps and out-laps (now that their DB flags are correctly written by the DEF-P2-013 fix). See `TestHistoryLoadSessionMapping` in `test_group8_session_reload.py`.
**Fix (Group 2 — earlier partial fix):** `dashboard.py` Practice Review lap table replaced `self._logger.avg_fuel_per_lap()` with `getattr(self._tracker, "avg_fuel_per_lap", 0.0)`. `strategy/engine.py` already used `self._tracker.avg_fuel_per_lap` directly.
**Description:** After loading a historical session from History into Practice Review, the Strategy Builder Fuel Burn Auto label still shows the value from app startup (either "—" or the previous live session average). `_loaded_session_avg_fuel` was being set correctly, but the UI label was never refreshed.
**Expected Behaviour:** After loading a session from History, the Strategy Builder Fuel Burn label shows the average fuel per lap from the loaded session (excluding pit laps and out-laps). `_computed_fuel_burn_lpl()` returns the loaded session average and the display reflects it immediately.
**Acceptance Criteria:**
- Load a 10-lap session from History where the average fuel is ~3.0 L/lap. Strategy Builder Fuel Burn label updates to "3.00 L/lap (loaded session)" immediately.
- Run Practice Analysis — `fuel_burn_per_lap` in the prompt matches the loaded session average.
- Pit laps and out-laps are excluded from the average (their fuel values are not representative).

---

**ID:** DEF-P2-010
**Title:** Driver feedback form embedded in Setup Builder instead of Practice Review
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix (three parts):**
1. Removed `layout.addWidget(self._build_driver_feedback_form())` from `_build_setup_builder_tab()`.
2. Added `layout.addWidget(self._build_driver_feedback_form())` to `_build_practice_review_tab()` after the Practice AI Analysis group.
3. Updated `_on_driver_feedback_submit()`: `_setup_feeling_input` access guarded with `hasattr`; `session_id=0` replaced with `getattr(self, "_session_id", 0)` so feedback links to the active session; `_setup_analyse_ai()` call removed (it belongs to Setup Builder, not Practice Review).
See `TestDriverFeedbackLocation` in `test_group6_fixes.py`.
**Description:** The driver feedback form (corner entry, mid-corner, exit stability, etc.) is placed inside the Setup Builder tab. Per spec §4.3, post-session feedback is a Practice Review prompt. Drivers finishing a stint must not navigate to Setup Builder to submit handling notes.
**Expected Behaviour:** Driver feedback form is accessible from Practice Review via a "Submit Feedback" button or collapsible section. Submitting from Practice Review writes to `driver_feedback` linked to the current session. That feedback then appears in subsequent AI coaching prompts.
**Acceptance Criteria:**
- Practice Review tab contains a "Submit Feedback" button or collapsible feedback form.
- Submitting feedback from Practice Review writes a row to `driver_feedback` linked to the current session.
- That row appears in the next AI coaching prompt under "## Recent Driver Feedback".

---

---

**ID:** DEF-P2-011
**Title:** Practice Review session summary includes outlaps and invalid laps in best/average calculations
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Three-part fix: (1) `get_session_laps()` in `session_db.py` now SELECTs `is_out_lap` in addition to `is_pit_lap`. (2) `_add_bank_lap_row()` and `_add_lap_row()` in `dashboard.py` now store `{"is_out_lap": ..., "is_pit_lap": ...}` in the col 0 item's `Qt.ItemDataRole.UserRole` data. Outlap rows display "Practice (OL)" in col 1 and use a dark green `#003A1A` background. (3) `_refresh_practice_summary()` now reads the UserRole flag per row and skips any row with `is_out_lap=True` from best lap, average lap, and average fuel calculations. Total row count still includes outlaps. See `TestOutlapSummaryLogic` and `TestOutlapDB` in `test_group3_fixes.py`.
**Reported:** 2026-06-21
**Root Cause:** `_refresh_practice_summary()` (`dashboard.py` line 6782) iterates all rows, reads col 3 (lap time ms), and includes every row where `ms > 0`. There is no mechanism to identify outlap rows: `_add_lap_row()` does not store `is_out_lap` in any table column or item data, and `_add_bank_lap_row()` has no `is_out_lap` parameter. The `get_session_laps()` query does not return `is_out_lap` even though it is stored in `lap_records`. Outlap times (typically 10–40% slower than a flying lap) inflate the average and may affect best-lap identification if displayed alongside regular laps.
**Description:** Practice Review Session Summary best lap and average lap calculations include outlaps and should not. DEF-P1-002 fix ensured outlaps are recorded with `is_out_lap=True`, but the summary calculation does not filter them out.
**Expected Behaviour:** Outlaps are excluded from best lap, average lap, and average fuel calculations. Outlaps are still displayed in the lap table with a visual indicator (e.g., "OL" label or distinct background colour) but are not used in summary statistics.
**Acceptance Criteria:**
- Complete an outlap (4s slower than lap pace). Session Summary best lap is not the outlap.
- Load a session containing an outlap from History. Outlap row visible in table. Summary best and average exclude it.
- Outlap row has a distinct visual style (colour or label).

---

**ID:** DEF-P2-012
**Title:** Practice Analysis prompt sends wrong tyre wear multiplier (2.0× instead of actual event value)
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_run_practice_analysis()` in `dashboard.py` now reads `tyre_wear_multiplier` from `_psc` (strategy config) immediately before building `race_params`, ensuring no stale cached value is used. Added a debug log: `print(f"[PracticeAnalysis] tyre_wear_multiplier={_tyre_wear:.2f} (from Event config)")`. See `TestTyreWearSource` source scan test in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P1-004, Addendum A3
**Root Cause:** `_run_practice_analysis()` reads `tyre_wear_multiplier` from `_psc.get("tyre_wear_multiplier", 1.0)` where `_psc = self._config.get("strategy", {})`. This value is set by `_on_event_set_active()` from `self._evt_tyre_wear.value()`. If the active event was last saved with tyre wear = 2.0 and the user hasn't re-activated the event after changing the wear multiplier, the stale 2.0 value is sent to the AI. The `_wear_note()` function in `ai_planner.py` (line 432) converts `tyre_wear_multiplier != 1.0` into "Race tyre wear is X× faster than practice." When `tyre_wear_multiplier == 1.0`, it correctly outputs "Tyre wear rate is the same as in practice."
**Description:** Event Planner had tyre wear configured equal to practice. Practice Analysis prompt stated "Race tyre wear is 2.0× faster than practice." This is factually incorrect. Confirmed by AI prompt evidence.
**Expected Behaviour:** `tyre_wear_multiplier` in the practice analysis prompt must exactly match the currently active event's tyre wear multiplier. If the event has 1.0x wear, prompt must say "Tyre wear rate is the same as in practice."
**Acceptance Criteria:**
- Set Event tyre wear to 1.0x. Set event active. Run Practice Analysis.
- Prompt contains "Tyre wear rate is the same as in practice."
- Set tyre wear to 1.5x. Re-activate event. Re-run. Prompt contains "1.5× faster."

---

**ID:** DEF-P2-013
**Title:** Pit stop indicator lost after session reload from History
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12b investigation) — Code investigation confirmed both load paths (`_on_history_load_session` and `_import_bank_session`) correctly pass `is_pit_lap` via `get_session_laps()`. Zero values in retesting were from pre-Group-8 session data (wrote `is_pit_lap=0` by default). New sessions recorded after Group 8 have correct values. DEF-P2-022 root cause hypothesis was incorrect.
**Fix (Group 8 — complete fix):** `main.py` EventDispatcher `write_lap()` call now passes `is_pit_lap=bool(getattr(record, "is_pit_lap", False))` and `is_out_lap=bool(getattr(record, "is_out_lap", False))`. Also passes `delta_ms` and `session_type`. These four fields were silently defaulting to 0/False/"" because they were not forwarded from the `LapRecord`. The UI-side fixes (Groups 2+3) were correct but had no effect because the DB column was always 0. See `TestMainWriteLapPassesPitFlag` in `test_group8_session_reload.py`.
**Fix (Groups 2+3 — partial):** `get_session_laps()` extended to SELECT `is_pit_lap`; `_add_bank_lap_row()` extended to accept and apply `is_pit_lap` (amber background `#4A4000`, "Yes" in col 11); both `_on_history_load_session()` and `_import_bank_session()` updated to pass `is_pit_lap=bool(lap.get("is_pit_lap", 0))`.
**Reported:** 2026-06-21
**Root Cause:** `main.py` EventDispatcher called `write_lap()` without forwarding `is_pit_lap`, `is_out_lap`, `delta_ms`, or `session_type` from the `LapRecord`. These all defaulted to 0/False/"". The DB column `is_pit_lap` was therefore always 0. Live display reads from the `LapRecord` in memory and showed correctly; the reload path reads from DB and always found 0.
**Root Cause (original — already fixed Groups 2+3):** `get_session_laps()` only selected `lap_num, lap_time_ms, compound, fuel_used`. `is_pit_lap` was stored in DB but not retrieved. `_add_bank_lap_row()` always wrote `""` for col 11.
**Description:** After reloading a session from History into Practice Review, pit stop laps that were correctly marked with a pit indicator when originally recorded show as blank in the Pit column. The data is in the DB but not retrieved or displayed.
**Expected Behaviour:** Pit stop indicator (col 11, "Yes") is preserved after session reload. Rows that were pit laps retain the amber background and "Yes" marker.
**Acceptance Criteria:**
- Complete a pit stop lap in Practice. Save session. Reload from History. The pit lap row shows "Yes" in the Pit column with amber background.
- Non-pit laps show blank in the Pit column.
- `get_session_laps()` returns `is_pit_lap` field in its result dict.

---

**ID:** DEF-P2-014
**Title:** Fuel Start and Fuel End not persisted to DB and missing after session reload
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12b investigation) — Same finding as DEF-P2-013: code is correct for new sessions. History detail shows `fuel_used` (always persisted); `fuel_start`/`fuel_end` are persisted by Group 8 fix for sessions recorded after that fix. Pre-Group-8 sessions have 0.0 defaults. AWR-043 must use a session recorded after Group 8 to pass.
**Fix (Group 8 — additional fix):** The secondary effect of DEF-P2-013 (is_out_lap always 0 in DB) meant outlap fuel values were included in the loaded session average, skewing the Fuel Burn Auto display. With Group 8's fix to write `is_out_lap` correctly, the fuel average now correctly excludes outlaps. `_lbl_fuel_burn_display` is also now refreshed after session load (see DEF-P2-009 fix). See `TestGetSessionLapsColumns` in `test_group8_session_reload.py`.
**Fix (Group 2 — schema + write path):** Added `fuel_start REAL NOT NULL DEFAULT 0.0` and `fuel_end REAL NOT NULL DEFAULT 0.0` columns to `_DDL_BASE` `lap_records` table in `session_db.py`. Added `_V2_ALTER_COLUMNS` list and `_migrate_v2()` method (idempotent ALTER TABLE with duplicate-column guard). `_migrate()` dispatcher now runs v2. `write_lap()` signature extended with `fuel_start: float = 0.0` and `fuel_end: float = 0.0`; both columns added to the INSERT (now 33 `?` placeholders). `get_session_laps()` SELECT extended to return `is_pit_lap, fuel_start, fuel_end`. `_add_bank_lap_row()` extended to accept and display these values. `main.py` EventDispatcher passes `fuel_start=getattr(record, "fuel_start", 0.0)` and `fuel_end=getattr(record, "fuel_end", 0.0)` to `write_lap()`. See `TestFuelStartEndDB` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Root Cause:** `write_lap()` (`session_db.py` line 817) does not write `fuel_start` or `fuel_end` columns — neither exists in the `lap_records` INSERT statement. `LapRecord` carries both fields but they are never passed to `write_lap()`. The EventDispatcher at `main.py` calls `write_lap(..., fuel_used=...)` without fuel_start or fuel_end. `get_session_laps()` does not return them. `_add_bank_lap_row()` always writes `"—"` for col 6 (fuel_start) and col 7 (fuel_end) at lines 2694-2695.
**Description:** After reloading a practice session from History, the Fuel Start and Fuel End columns are blank ("—") for all laps. These values are available at lap-record time but are never written to the database.
**Expected Behaviour:** Fuel Start and Fuel End per lap are stored in `lap_records` and restored when loading from History. Reloaded rows show numeric fuel start/end values.
**Acceptance Criteria:**
- Complete 3 laps in Practice. Each lap's Fuel Start and Fuel End are populated in the table.
- Reload the same session from History. Fuel Start and Fuel End columns show the same values.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 3` returns non-zero values.

---

**ID:** DEF-P2-015
**Title:** Top speed target in AI prompt shows invalid value (~11 km/h) instead of actual target speed
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix:** Changed `if ms > 0:` to `if ms >= 50:` in `_refresh_gear_ratios()` at `ui/dashboard.py`. Values below 50 km/h are now treated as raw-field artefacts and not written to `_spin_top_speed`. The spinbox stays at 0 (shows "—"), and `_current_setup_dict()` sends `transmission_max_speed_kmh: 0` which the AI ignores. See `TestTopSpeedGuard` in `test_group6_fixes.py`.
**Reported:** 2026-06-21
**Related:** Addendum A5
**Root Cause:** `transmission_max_speed_kmh` property in `packet.py` (line 312) computes `self.transmission_max_speed * 3.6`. The raw `transmission_max_speed` field in the GT7 UDP packet is not a speed in m/s — reverse-engineering of the GT7 packet format shows this field may encode the transmission type index, a gear ratio scaling factor, or an unused value that happens to be ~3.0. Multiplying a ratio/index value (~3.0) by 3.6 gives ~11 km/h. `_capture_gear_ratios()` at `dashboard.py` line 5639 writes this invalid value directly to `_spin_top_speed`. `_current_setup_dict()` at line 4691 sends `"transmission_max_speed_kmh": int(self._spin_top_speed.value())`, passing 11 km/h to `analyse_practice_session()`.
**Description:** AI prompt reports "Top speed target: 11 km/h." No GT7 car has a top speed target near 11 km/h. This nonsense value pollutes the AI setup recommendation.
**Expected Behaviour:** If the captured top speed value is below 50 km/h, treat it as not captured and send 0 or omit the field. The prompt should not contain an invalid top speed target. Minimum valid GT7 top speed target is approximately 120 km/h.
**Acceptance Criteria:**
- Run a practice lap. `_spin_top_speed` shows either 0 ("—") or a realistic value ≥ 120 km/h.
- AI prompt does not contain "11 km/h" or any value < 50 km/h for top speed target.
- If `transmission_max_speed_kmh` < 50, it is excluded from the setup dict payload.

---

**ID:** DEF-P2-016
**Title:** Practice Analysis requests race strategy from AI without validating input data integrity
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added a validation gate in `_run_practice_analysis()` before the AI call. Builds `_validation_warnings: list[str]` checking: (1) timed race with `duration_mins < 5`, (2) lap race with `total_laps < 2`, (3) `fuel_burn_per_lap <= 0`, (4) no compound with ≥ 2 laps. If any warning present, shows an HTML warning dialog with the list, logs `"[PracticeAnalysis] Validation blocked"`, and returns without calling AI. See `TestValidationGateLogic` in `test_group2_fixes.py` and source-scan test `test_source_contains_validation_gate`.

---

**ID:** DEF-P2-017
**Title:** Qualifying mode may trigger RACE_FINISHED logic on timed events
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. DEF-P2-QRF (Group 5, 2026-06-21) implemented a two-layer fix: (1) `telemetry/state.py` timed-race RACE_FINISHED condition excludes both `SessionType.PRACTICE` and `SessionType.QUALIFYING`; (2) `voice/announcer.py` `_on_race_finish()` guards `_session_mode != "race"` as a belt-and-suspenders fallback. See `TestQualifyingRaceFinished` in `test_group5_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P1-008
**Root Cause:** The DEF-P1-008 fix at `telemetry/state.py` adds `self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition. This suppresses the event during practice but not during qualifying. A qualifying session with a timed event active (e.g., a 15-minute qualifying session configured in Event Planner) will still have `_race_start_time` set when the car exceeds 80 km/h, and `computed_remaining_ms()` will reach 0 after the configured timed duration. If the user pauses the game (`packet.loading = True`) at that point, RACE_FINISHED fires and the voice engineer announces race completion during qualifying.
**Description:** RACE_FINISHED logic should only run in Race mode. Practice and Qualifying must never trigger race-finished events, race-completion announcements, or the FINISHED phase transition. DEF-P1-008 fixed the Practice case but left Qualifying unguarded.
**Expected Behaviour:** The RACE_FINISHED condition is only evaluated when `_session_type_override == SessionType.RACE` or `_session_type_override is None` (auto-detect, assumed race context). Practice and Qualifying overrides suppress the event entirely.
**Acceptance Criteria:**
- Set a timed event active. Switch Live tab to Qualifying mode. Drive for the full timed duration. No "Race finished" announcement.
- `RACE_FINISHED` does not appear in the Debug tab event log during qualifying.
- Practice mode: same — no RACE_FINISHED (existing AWR-011 covers this).
- Race mode: RACE_FINISHED still fires correctly after the configured duration.
**Reported:** 2026-06-21
**Related:** DEF-P1-004, DEF-P1-005, DEF-P1-006, Addendum A6
**Root Cause:** `_run_practice_analysis()` calls `analyse_practice_session()` unconditionally once `lap_data_by_compound` is non-empty. There is no pre-flight validation of: race type correctness, compound distribution accuracy, fuel burn source consistency, BoP/tuning permissions loading, or tyre wear multiplier accuracy. The AI receives a strategy request built from potentially incorrect race length (1 lap), wrong compound counts, wrong fuel burn source, full setup with locked fields, and wrong tyre wear — producing a response that is internally consistent but based on bad data. Detected when actual testing showed all five prompt inputs were wrong simultaneously.
**Description:** Practice Analysis sends a three-strategy race recommendation request to AI even when the prompt's race type, compound history, fuel burn, BoP restrictions, and tyre wear are all incorrect. The AI response appears plausible but is based on wrong data throughout.
**Expected Behaviour:** Before calling the AI, `_run_practice_analysis()` validates: race type is correctly resolved, compound data matches the visible lap table, fuel burn is from a live or loaded source (not a stale tracker value), BoP/tuning restrictions are loaded, and no obviously invalid values (top speed < 50 km/h, race laps < 2 for a lap race) are present. If validation fails, the Analysis button is disabled or a warning panel is shown listing the data quality issues.
**Acceptance Criteria:**
- With a timed race event active and 0 live laps (tracker has no fuel data), Practice Analysis button shows a data quality warning rather than sending the AI call.
- After loading historical laps with correct compound tags and an activated event, the button becomes available and the prompt passes validation.
- Debug tab logs each validation check and its result before the AI call.

---

**ID:** DEF-P2-018
**Title:** Outlap row has no visual identification in Practice Review
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 3 partial)
**Related:** DEF-P1-002 (outlap recording fix — was Partially Fixed)
**Description:** Outlaps are now saved to the DB with `is_out_lap=1` (DEF-P1-002 fix) but the Practice Review lap table displays them with the same style as normal laps. No "OL" label, no dark green row background, and no "(out)" suffix on the lap time. Drivers cannot distinguish outlap from push lap at a glance.
**Expected Behaviour:** Outlap rows in Practice Review display with a distinct visual style: dark green (`#003A1A`) row background OR an "OL" label in column 1 next to the lap number. The lap time column shows "(out)" suffix or is otherwise flagged. The outlap is excluded from best-lap calculations in the Session Summary.
**Acceptance Criteria:**
- Complete a pit stop and outlap in Practice mode.
- Practice Review: the outlap row has visually distinct styling (dark green or "OL" label).
- `is_out_lap = 1` in the DB for that row.
- Session Summary best lap excludes the outlap.

---

**ID:** DEF-P2-019
**Title:** Tyre compound change on existing lap does not propagate to subsequent laps
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Superseded by DEF-P2-026 (same defect, clearer spec)
**Reported:** 2026-06-22 (UAT Group 5 partial)
**Related:** DEF-P3-003 (new lap compound inheritance — was Partially Fixed); DEF-P2-026 (same defect re-reported with clearer spec)
**Fix:** `_on_compound_selected()` in `ui/dashboard.py` previously stopped propagation at the first row with any different compound string. Since every row is pre-tagged with `_default_lap_compound`, this stopped at row `start_row + 1` every time. Fix: removed the `existing and existing != norm` break condition and replaced it with a check for `is_pit_lap` in the row's UserRole data. Propagation now continues through all laps until the next pit lap boundary.
**AWR:** AWR-048
**Group:** 13

---

**ID:** DEF-P2-020
**Title:** Live tab tyre label shows available/required tyres from Event, not current fitted compound
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Superseded by DEF-P2-027 (same defect, full priority spec)
**Reported:** 2026-06-22 (UAT Group 5 partial)
**Related:** DEF-P3-002 (live tyre label — was Partially Fixed); DEF-P2-027 (same defect re-reported with full priority hierarchy spec)
**Fix:** See DEF-P2-027. `_get_current_tyre_compound()` and `_refresh_live_tyre_label()` implement Priority 1 (active race plan current stint) → Priority 2 (Setup Builder front tyre) → Priority 3 ("Not Set"). `mandatory_compounds` no longer used as tyre source. Label prefix changed to "Current Tyre:". Wired to `_on_tyre_preset_changed()`, `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, and `_setup_tyre_f.currentTextChanged`.
**AWR:** AWR-049
**Group:** 13

---

**ID:** DEF-P2-023
**Title:** Pit Lap Not Captured During Live Session (no-refuel stops)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Pit lap detection is entirely fuel-based — `_fuel_gained >= _pit_threshold (0.5L)` must be exceeded before `_enter_pit()` is called and `_pit_lap = True` is set. When the driver pits without refueling (e.g., tyre change only), `_fuel_gained` stays at 0 and the pit stop is never detected. The lap during which the car was in the pit box is written to DB with `is_pit_lap = 0`.
**Root cause:** `telemetry/state.py` `_phase_transitions()` only triggers `_enter_pit()` via the fuel accumulation path. No fallback for speed=0 service stops.
**Fix:** Added `_low_speed_start: float = 0.0` tracker variable. In `_phase_transitions()`, when `self._phase == RacePhase.RACING` and `p.speed_kmh < 10`: if timer not running, start it; if timer running for ≥ 3.0 seconds, call `_enter_pit()`. Reset timer when speed rises back above 10 km/h or when `_enter_pit()` fires. Timer also reset in `_enter_pit()` itself to prevent double-firing if fuel detection fires at the same time.
**Expected Behaviour:** When the driver comes to a full stop in the pit box for ≥ 3 seconds (with or without refueling), `is_pit_lap = 1` is written to `lap_records`. Practice Review shows amber background on the pit stop lap.
**Acceptance Criteria:**
- Run Practice session. Pit and take 0 fuel (tyre change only). Continue.
- `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` — the pit lap row has `is_pit_lap = 1`.
- Practice Review shows amber background for that lap.
- Outlap after the no-fuel pit stop shows `is_out_lap = 1`.
**AWR:** AWR-045
**Group:** 13

---

**ID:** DEF-P2-024
**Title:** Outlap Metadata Lost After History Reload (Save Session button path)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Outlap is visible in Practice Review during a live session (correct `is_out_lap = True` from `LapRecord`). After the user clicks Save Session, clears the session, and reloads from History, the outlap flag is gone — the row shows as a normal lap. The save path via `_save_session_to_db()` was calling `write_lap()` with only 6 positional arguments, omitting `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`, `delta_ms`, and `session_type`. All omitted fields default to 0/False/"" in the DB.
**Root cause:** `ui/dashboard.py` `_save_session_to_db()` line 2935: `self._db.write_lap(sid, lap.lap_num, lap.lap_time_ms, lap.fuel_used, stats, compound)` — no keyword arguments for the lap metadata fields.
**Fix:** Extended the `write_lap()` call with `fuel_start=getattr(lap, "fuel_start", 0.0)`, `fuel_end=getattr(lap, "fuel_end", 0.0)`, `is_pit_lap=bool(getattr(lap, "is_pit_lap", False))`, `is_out_lap=bool(getattr(lap, "is_out_lap", False))`, `delta_ms=int(getattr(lap, "delta_ms", 0))`, `session_type=(lap.session_type.value if hasattr...)`.
**Acceptance Criteria:**
- Run Practice session with outlap. Save Session → Clear → Load from History.
- Outlap row in Practice Review shows dark green background and "Practice (OL)" label.
- `SELECT is_out_lap FROM lap_records ORDER BY id DESC LIMIT 10` — outlap row has `is_out_lap = 1`.
**AWR:** AWR-046
**Group:** 13

---

**ID:** DEF-P2-025
**Title:** Fuel Data Lost After History Reload (Save Session button path)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Same root cause as DEF-P2-024. `_save_session_to_db()` omitted `fuel_start` and `fuel_end` from the `write_lap()` call. After Save Session + History reload, Fuel Start and Fuel End columns in Practice Review show "—" (0.0 in DB) even though the live session showed non-zero values.
**Root cause:** Same as DEF-P2-024 — missing keyword args in `_save_session_to_db()`.
**Fix:** Same as DEF-P2-024 — `fuel_start=getattr(lap, "fuel_start", 0.0)` and `fuel_end=getattr(lap, "fuel_end", 0.0)` now passed.
**Acceptance Criteria:**
- Run Practice session with ≥ 3 laps. Fuel Start and Fuel End are non-zero live. Save Session → Clear → Load from History.
- Practice Review Fuel Start and Fuel End columns show non-zero numeric values matching the live session.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 5` — non-zero values.
**AWR:** AWR-047
**Group:** 13

---

**ID:** DEF-P2-026
**Title:** Tyre Compound Propagation Only Updates Selected Lap (duplicate of DEF-P2-019)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Same defect as DEF-P2-019, more specific reproduction steps
**Reported:** 2026-06-22 (UAT)
**Related:** DEF-P2-019 (same root cause, same fix)
**Fix:** See DEF-P2-019.
**AWR:** AWR-048
**Group:** 13

---

**ID:** DEF-P2-027
**Title:** Live Tab Displays Event Required Tyre Instead of Current Fitted Compound
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT — extended spec provided)
**Related:** DEF-P2-020 (same root cause, full priority hierarchy spec added)
**Description:** The Live tab `_lbl_live_tyre_compound` label was set from `strategy["mandatory_compounds"]` (the event's Required Tyre field). Required tyres are race rules (what must be used at some point), not the current fitted compound. The user received a detailed spec requiring a priority hierarchy.
**Fix:** Added `_get_current_tyre_compound()` that checks (1) active race plan current incomplete stint `.compound`, (2) Setup Builder front tyre `_setup_tyre_f.currentText()`, (3) returns "Not Set". Added `_refresh_live_tyre_label()` that sets label to `"Current Tyre: {compound}"`. Wired to: `_on_tyre_preset_changed()` (fires on stint change), `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, and `_setup_tyre_f.currentTextChanged`. `mandatory_compounds` removed entirely from the live tyre label logic.
**Acceptance Criteria:**
- Load a race plan with Stint 1 = Racing Medium, Stint 2 = Racing Soft. Live tab shows "Current Tyre: Racing Medium". After pit stop completes Stint 1, shows "Current Tyre: Racing Soft".
- No race plan loaded, Setup Builder front tyre = Racing Hard → Live tab shows "Current Tyre: Racing Hard".
- No race plan, no setup tyre → Live tab shows "Current Tyre: Not Set".
- Required tyres from Event are NOT shown in the current tyre label.
**AWR:** AWR-049
**Group:** 13

---

**ID:** DEF-P2-021
**Title:** AI Log list does not auto-select new entries; timestamp and status format incomplete
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12c) — Three fixes: (1) Timestamp: `[:19].replace("T"," ")` → YYYY-MM-DD HH:MM:SS. (2) Status: "✓ OK"/"✗ FAIL"/"⊘ DRY-RUN" (dry-run detected via duration_ms==0 and "AI_DEBUG" in error_msg). (3) Auto-select: `_ai_log_pending_select` flag set in `_on_ai_log_entry()`; flushed by `_flush_ai_log_pending_select()` when AI Log tab (index 11) becomes active via `_on_tab_changed()`.
**Reported:** 2026-06-22 (Phase 2 Smoke Test — user reported "no visible AI log entry" after Practice Analysis with GT7_AI_DEBUG=1)
**Note:** Originally misreported as DEF-P2-019 (that ID is already taken by "Compound change not propagating forward").
**Root Cause:** `_add_ai_log_list_item()` called `scrollToBottom()` after appending the new item, but if the AI Log tab was not the currently visible tab when the `bridge.ai_log_entry` signal fired (QueuedConnection → delayed), `scrollToBottom()` had no visual effect. When the user later navigated to the AI Log tab, they saw the top of the list (DB-loaded history) and missed the new entry sitting at the bottom without selection. DB-loaded startup entries appeared populated; the user clicked one and saw the Prompt tab — but could not find the new live entry.
**Fix:** `_add_ai_log_list_item()` now accepts `auto_select: bool = False`. When `True`, calls `setCurrentRow(count - 1)` after `addItem()`, selecting the newly added item. `_on_ai_log_entry()` (the live signal handler) passes `auto_select=True`; `_on_ai_log_entry_dict()` (DB startup load) keeps the default `False` to avoid disrupting startup ordering.
**Expected Behaviour:** When a new AI call completes (or fails in debug mode), the entry is added to the AI Log list AND automatically selected. When the user navigates to the AI Log tab the new entry is highlighted, and the detail pane (Details, Prompt, Payload, Response tabs) immediately shows that entry's data.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Run Practice Analysis (with ≥ 2 laps and valid fuel data).
- Navigate to AI Log tab. The most recent entry is highlighted (selected) automatically.
- Entry shows ✗, feature="Practice Analysis", timestamp from the run.
- Prompt sub-tab shows the intercepted prompt (requires Developer Mode enabled in Settings).
**AWR:** AWR-041
**Group:** 11

---

**ID:** DEF-P2-022
**Title:** History session detail and Practice Review load path use different data sources — pit flag and fuel data missing in Practice Review
**Status:** CLOSED — Root cause hypothesis incorrect (2026-06-22 Group 12b investigation)
**Reported:** 2026-06-22 (discovered during AWR-040 runtime retest)
**Investigation conclusion:** Both load paths (`_on_history_load_session()` and `_import_bank_session()`) use the SAME `get_session_laps()` SELECT which correctly returns `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`. Both methods correctly pass all fields to `_add_bank_lap_row()`. `write_lap()` in `main.py` correctly receives `fuel_start`, `fuel_end`, `is_pit_lap` from `LapRecord`. The History detail panel shows only `fuel_used` (not `fuel_start`/`fuel_end`); the user's comparison was between different columns. Zero values observed in AWR-040 retest were caused by testing with pre-Group-8 session data that had `DEFAULT 0.0` for newly-added columns. No code change required. Tests in `test_group12b_history_practice_mapping.py` verify correctness.
**Related:** DEF-P2-013, DEF-P2-014
**Group:** 12

---

---

**ID:** DEF-P1-012
**Title:** Practice Analysis prompt provides setup changes even when tuning is locked (BoP event)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_build_practice_prompt()` in `strategy/ai_planner.py` had both a `constraint_block` saying "DO NOT recommend setup changes" AND a fixed `## Instructions` line asking for "3–5 Setup changes". The AI followed the explicit instruction over the constraint.
**Fix:** The `setup_changes` instruction at line 685 is now a Python conditional. When `params.tuning_locked=True`: "No setup changes…Tuning is locked…do NOT recommend any setup changes." When `not params.tuning_locked`: original "3–5 changes following the endurance priority order…" text.
**Acceptance Criteria:**
- BoP event, Tuning Off → run Practice Analysis → AI response contains "tuning not permitted" or "setup changes not recommended"; no specific setup change values.
- Non-BoP event → AI response still provides 3–5 setup changes.
**AWR:** AWR-050
**Group:** 14

---

**ID:** DEF-P2-029
**Title:** Outlap metadata row silently skipped when write_lap receives stats=None
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `write_lap()` in `data/session_db.py` had `if stats is None: return 0` as first statement in the method body. Outlap after manual "Save Session" following a clear had no recorder stats → row was never written.
**Fix:** Removed the `if stats is None: return 0` guard. All stat field accesses made None-safe (`stats.field if stats else 0`). `positions_blob` JSON uses conditional list expressions. Metadata-only rows (zeros for telemetry) are now written and return a valid row id. Updated docstring explains the behaviour.
**Acceptance Criteria:**
- Practice session with outlap. Click "Save Session". Click "Clear". Click "Save Session" again. Query `SELECT is_out_lap FROM lap_records WHERE is_out_lap=1` — row exists.
- The outlap appears in History with `is_out_lap=1` and `fuel_start`/`fuel_end` non-zero.
**AWR:** AWR-051
**Group:** 14

---

**ID:** DEF-P2-030
**Title:** Save Session button creates a duplicate session when live session already open
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_save_session_to_db()` called `_db.open_session()` unconditionally. `_on_live_mode_changed()` also called `_db.open_session()` at mode-change time. Clicking Save Session during a live session created a second session row with `total_laps = 0` plus re-inserted all laps.
**Fix:** `_save_session_to_db()` now reads `self._dispatcher._session_id`. If > 0, it reuses that session and only calls `update_lap_compound()` + `update_lap_setup_id()` per lap (laps already written by EventDispatcher). Falls back to full `open_session()` path only when no live session exists.
**Acceptance Criteria:**
- Start Practice mode (session auto-opened). Complete 3 laps. Click "Save Session". Query `SELECT COUNT(*) FROM sessions` — exactly 1 session row, not 2. Compound tags applied to existing session rows.
**AWR:** AWR-052
**Group:** 14

---

**ID:** DEF-P2-031
**Title:** Qualifying outlap calming phrase never fires when using Qualifying override in Live tab
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_exit_pit()` in `telemetry/state.py` emitted `PIT_EXIT` with `session_type=self._session_type.value` (packet-detected). In a custom race, this is often `unknown` or `practice`. `voice/announcer.py` checks `event.data.get("session_type") == "qualifying"` to fire the outlap calming phrase — which therefore never matched.
**Fix:** `_exit_pit()` now uses `_session_type_override.value` when `_session_type_override is not None`, falling back to `self._session_type.value` otherwise. Same pattern already used for `LapRecord.session_type` on lines 708–711.
**Acceptance Criteria:**
- Set Live tab mode to Qualifying. Do a flying lap and come into the pits. Exit the pit. The qualifying outlap calming phrase is heard from the announcer.
**AWR:** AWR-053
**Group:** 14

---

**ID:** DEF-P2-032
**Title:** Pit fuel commentary spoken in Qualifying mode (pit/fuel alerts not suppressed)
**Status:** Already Fixed (Group 5) — Regression Guard Added (Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** Investigation showed both `_on_pit()` and `_on_fuel_low()` in `announcer.py` already guard against `"qualifying"` in `in ("practice", "qualifying")` check. No production code change needed.
**Fix:** Source-scan regression guards added to `tests/test_group14_uat_remediation.py` `TestQualifyingAlertSuppression` class.
**Acceptance Criteria:**
- Qualifying mode → fill fuel in pit → NO pit commentary spoken.
- Qualifying mode → low fuel → NO fuel-low alert spoken.
**AWR:** AWR-054
**Group:** 14

---

**ID:** DEF-P2-033
**Title:** AI Log auto-select fires on hidden widget — new entry not visible when navigating to AI Log tab
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_on_ai_log_entry()` called `_add_ai_log_list_item(auto_select=True)` which called `setCurrentRow()` immediately. If the AI Log tab (index 11) was not the active tab, `setCurrentRow()` had no visible effect. When the user later navigated to the tab the new entry was unselected.
**Fix:** Removed `auto_select=True`. Added `QTimer.singleShot(0, self._flush_ai_log_pending_select)` for deferred execution. `_flush_ai_log_pending_select()` now checks `self._tabs.currentIndex() != 11`; if the tab is not active, returns without clearing the flag. `_on_tab_changed(11)` calls `_flush_ai_log_pending_select()` so the selection fires as soon as the user navigates to the tab.
**Acceptance Criteria:**
- Run Practice Analysis with AI Log tab NOT visible. Navigate to AI Log tab. The new entry is automatically selected.
- Run Practice Analysis with AI Log tab visible. New entry is selected immediately on completion.
**AWR:** AWR-055
**Group:** 14

---

**ID:** DEF-P2-034
**Title:** AI Log entry timestamps show UTC time instead of local time
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `strategy/_ai_client.py` used `_dt.datetime.utcnow().isoformat()` for all 3 `AILogEntry` `timestamp` fields (debug dry-run, success, and error paths). `utcnow()` returns UTC time with no timezone info; for users in non-UTC timezones the timestamp is wrong.
**Fix:** All 3 occurrences changed to `_dt.datetime.now().isoformat()` which returns local wall-clock time.
**Acceptance Criteria:**
- Run a Practice Analysis. Navigate to AI Log tab. The timestamp on the new entry matches the current local time (not UTC).
**AWR:** AWR-056
**Group:** 14

---

**ID:** DEF-P2-035
**Title:** Garage tab does not show DB-saved setups; setup query exceptions silently swallowed
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_on_garage_car_selected()` in `ui/dashboard.py` had two bare `except Exception: pass` blocks around the sessions query and setup query. Exceptions were invisible. The `get_setups_for_car()` method existed in `SessionDB` but was never called from the Garage tab — only `get_all_sessions()` was called, and setups came from `config.json` only.
**Fix:** Both `except Exception: pass` blocks replaced with `import traceback; traceback.print_exc()`. Added a DB setups block: resolves `car_id` from recent sessions for the displayed car name; calls `self._db.get_setups_for_car(car_id)`; populates `_garage_setups_table` rows with name, notes excerpt, and creation date.
**Acceptance Criteria:**
- Run Practice Analysis that produces AI setup recommendations. Navigate to Garage. Select the car. The saved setup appears in the Setups table.
- Introduce a deliberate exception (disconnect DB). Check console — traceback is printed, app does not crash.
**AWR:** AWR-057
**Group:** 14

---

**ID:** DEF-P1-013
**Title:** Strategy Analysis race_params missing race_type, duration_mins, tuning_locked, allowed_tuning, bop, avail_tyres
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_ai_analysis()` race_params dict extended with `race_type`, `duration_mins`, `tuning_locked`, `allowed_tuning`, `bop`, `avail_tyres`. `RaceParams` dataclass extended with `bop: bool = False` and `avail_tyres: list = field(default_factory=list)`. `_build_race_prompt()` injects `tuning_block`, `bop_line`, and `avail_line`.
**AWR:** AWR-058
**Group:** 15

---

**ID:** DEF-P1-014
**Title:** Practice Analysis worker uses car_id=0 and opens new DB connection
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_practice_analysis()` now captures `_hist_db = self._db`, `_hist_track`, `_hist_car_name` before spawning `_worker()`. Worker calls `_hist_db.get_car_id(_hist_car_name)` to resolve car_id. No new DB connection opened.
**AWR:** AWR-059
**Group:** 15

---

**ID:** DEF-P2-036
**Title:** PTT coaching and setup_advice missing car_name, car_specs, compound
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `QueryListener.__init__()` gains `_car_specs_ref: dict` and `update_car_specs()` method. `_handle_trigger_inner()` coaching and setup_advice branches now pass `car_name`, `car_specs`, `compound`. Dashboard calls `update_car_specs()` in `_on_event_set_active()`.
**AWR:** AWR-064
**Group:** 15

---

**ID:** DEF-P2-037
**Title:** PTT setup_advice reads stale config["car_setup"] instead of live setup
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `QueryListener.__init__()` gains `_active_setup_getter` and `set_active_setup_getter()`. setup_advice branch uses getter if set, falls back to config. Dashboard wires `set_active_setup_getter(self._current_setup_dict)` at startup.
**AWR:** AWR-065
**Group:** 15

---

**ID:** DEF-P2-038
**Title:** Practice Analysis race_params missing bop field
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_practice_analysis()` race_params extended with `"bop": bool(_psc.get("bop", False))`. `_build_practice_prompt()` injects `bop_line` when `params.bop` is True.
**AWR:** AWR-060
**Group:** 15

---

**ID:** DEF-P2-039
**Title:** avail_tyres missing from RaceParams, both race_params dicts, and prompts
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `avail_tyres` added to `RaceParams`, both race_params dicts, `build_car_setup()`, `_build_setup_from_scratch_prompt()`. `_build_race_prompt()` and `_build_practice_prompt()` inject `avail_line`. `_run_build_setup()` passes `avail_tyres` and `req_tyres`.
**AWR:** AWR-061
**Group:** 15

---

**ID:** DEF-P2-040
**Title:** Driver feedback not passed to Practice Analysis AI
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `analyse_practice_session()` and `_build_practice_prompt()` gain `driver_feedback_str: str = ""`. Worker queries `get_recent_feedback(car_id, track, limit=5)`, formats rows, passes `driver_feedback_str`. Prompt injects `feedback_section` when non-empty.
**AWR:** AWR-062
**Group:** 15

---

**ID:** DEF-P2-041
**Title:** Previous AI recommendations not included in Practice Analysis prompt
**Status:** Fixed — Partially Effective (2026-06-23 runtime validation — see DEF-P3-013)
**Fix:** `analyse_practice_session()` and `_build_practice_prompt()` gain `prev_ai_str: str = ""`. Worker queries `get_recent_ai_recommendations("Practice Analysis", car_id, track, limit=2)`, truncates to 300 chars each, passes `prev_ai_str`. Prompt injects `prev_ai_section` when non-empty.
**AWR:** AWR-063
**Group:** 15

---

**ID:** DEF-P3-009
**Title:** Race prompt hardcodes "N laps" even for timed races
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_build_race_prompt()` computes `race_len_line` conditionally: `"Race duration: N minutes (Timed Race)"` when `params.race_type == "timed"`, else `"Race length: N laps"`. Prompt uses `{race_len_line}`.
**AWR:** AWR-066
**Group:** 15

---

**ID:** DEF-P3-010
**Title:** build_car_setup missing race context (tyre wear, fuel mult, avail_tyres, req_tyres, race_type)
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `build_car_setup()` and `_build_setup_from_scratch_prompt()` gain `tyre_wear_multiplier`, `fuel_multiplier`, `avail_tyres`, `req_tyres`, `race_type`. Prompt injects `_race_ctx_block`. `_run_build_setup()` reads all values from `_sc_build` and passes them.
**AWR:** AWR-067
**Group:** 15

---

**ID:** DEF-P3-011
**Title:** _DATA_QUALITY_NOTE absent from ai_planner.py prompts
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_DATA_QUALITY_NOTE` constant added to `ai_planner.py` (mirrors `driving_advisor.py`). Injected into both `_build_race_prompt()` and `_build_practice_prompt()`.
**AWR:** AWR-068
**Group:** 15

---

**ID:** DEF-P3-012
**Title:** _display_strategy_results does not validate AI output for tuning violations
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_display_strategy_results()` calls `validate_ai_setup_response()` on each strategy option's setup_changes text. If violations found, an orange warning banner is prepended to the strategy HTML. Banner shows F5A623 styling consistent with event lock banners.
**AWR:** AWR-069
**Group:** 15

---

**ID:** DEF-P3-013
**Title:** AILogEntry missing car_id and track — get_recent_ai_recommendations() always returns empty
**Status:** Fixed (2026-06-23 Group 15A)
**Root cause:** `AILogEntry` dataclass (`strategy/_ai_client.py:32`) had no `car_id` or `track` fields. `call_api()` constructed `AILogEntry` without them; `_asdict(entry)` passed to `log_ai_interaction()` wrote `car_id=0, track=""` for every `ai_interactions` row. `get_recent_ai_recommendations(feature, car_id, track)` filters on real car_id, so always returned `[]`.
**Fix (Group 15A):**
1. `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields (with defaults so existing code is not broken)
2. `call_api()` gains `car_id: int = 0` and `track: str = ""` kwargs; all three `AILogEntry` construction sites thread them through
3. `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` in `ai_planner.py` gain `car_id: int = 0`; pass `car_id=car_id, track=params.track` / `track=track` to `call_api()`
4. All four `call_api()` sites in `DrivingAdvisor` pass `car_id=self._car_id_ref[0], track=self._config.get("strategy", {}).get("track", "")`
5. `_run_ai_analysis()` resolves `_car_id_strat` before worker; passes `car_id=_car_id_strat` to `analyse_strategy()`
6. `_run_practice_analysis()` passes `car_id=_car_id_hist` to `analyse_practice_session()`
7. `_run_build_setup()` resolves `_car_id_build` before worker; passes `car_id=_car_id_build` to `build_car_setup()`
8. `_on_ai_log_entry_dict()` in dashboard reconstructs AILogEntry from DB rows with `car_id` and `track` populated
**AWR:** AWR-063 (now CLOSED)
**Group:** 15A
**Tests:** `tests/test_group15a_ai_log_car_track.py` (56 tests — all pass)

---

### P3 Medium

---

**ID:** DEF-P3-001
**Title:** Brake balance spinbox step increment unverified
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Source scan confirmed `_setup_bb.setSingleStep(1)` at `ui/dashboard.py:3984`. Called immediately after widget creation in `_build_car_setup_group()`. No code change required — already correct.
**Description:** `_setup_bb` is created by a helper function that may not call `setSingleStep(1)`. In GT7 the brake balance adjustment is 1 unit per click. If the step defaults to a non-1 value the control does not match in-game behaviour.
**Expected Behaviour:** Each click of the brake balance spinbox changes the value by exactly 1.
**Acceptance Criteria:**
- Click the up arrow on the brake balance spinbox once. Value increments by exactly 1.
- Click the down arrow once. Value decrements by exactly 1.
- Range is confirmed against GT7 in-game brake balance scale.
See `TestBrakeBalanceStep` in `test_group5_fixes.py`.

---

**ID:** DEF-P3-002
**Title:** Active tyre compound not displayed on Live Race Engineer tab
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_lbl_live_tyre_compound` already existed in Live tab (created at `ui/dashboard.py:606`). Added update call in `_on_live_mode_changed()` so the label refreshes from `_config["strategy"]["mandatory_compounds"]` whenever mode changes. `_sync_setup_builder_from_event()` also updates it when an event is set active (existing behaviour confirmed).
**Description:** The Live tab tyre widget shows four temperature circles but no label indicating the current compound (e.g., "Racing Medium"). The compound is available in `_config["strategy"]["mandatory_compounds"]`.
**Expected Behaviour:** A compound label (`_lbl_live_tyre_compound`) appears above the tyre temperature grid on the Live tab. It updates when the event is set active and when the mode changes.
**Acceptance Criteria:**
- Set an event with Required Tyre = Racing Hard and set it active. Live tab shows "Tyre: Racing Hard" above the temperature circles.
- Change to Racing Medium and set active. Label updates without restart.
- No event set — label shows "Tyre: —".
See `TestLiveTyreCompoundDisplay` in `test_group5_fixes.py`.

---

**ID:** DEF-P3-003
**Title:** Newly arriving laps in Practice Review do not inherit tyre compound from previous lap
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** In `_add_bank_lap_row()`, before the `existing_tag` assignment, added compound inheritance logic: if `compound` is empty and `lap_num` not yet in `_lap_compound_tags`, resolves compound from the highest-numbered prior key in `_lap_compound_tags` or falls back to `_default_lap_compound`.
**Description:** When a new lap row is appended to the Practice Review table, it always initialises the compound selector to `_default_lap_compound` regardless of what the previous lap's compound was.
**Expected Behaviour:** When a new lap row is added, it checks the compound on the previous lap (`_lap_compound_tags.get(lap_num - 1, _default_lap_compound)`) and initialises the selector to that value.
**Acceptance Criteria:**
- Set lap 5 compound to "Racing Medium" in Practice Review.
- Complete lap 6. The newly added row shows "Racing Medium" as the default compound.
- Change lap 6 to "Racing Hard". Complete lap 7. Lap 7 shows "Racing Hard".
- Laps before lap 5 are unchanged.

---

**ID:** DEF-P3-004
**Title:** Race type mutual exclusivity not enforced in Event Planner
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. `_on_race_type_changed()` was already implemented in `_build_event_planner_tab()`: disables `_evt_laps` when "timed" selected, disables `_evt_duration` otherwise, and is called once at build time for immediate enforcement. `_on_event_set_active()` correctly uses `"timed" if "timed" in rt_str.lower() else "lap"`. DEF-P1-004 fix ensures AI prompt uses `race_type` and `duration_mins` fields. See `TestRegisterCorrections` in `test_group6_fixes.py`.
**Description:** When "Timed Race" is selected in the race type dropdown, the Laps field remains editable. The AI prompt may receive `total_laps = 1` for a timed race, producing an incorrect strategy recommendation.
**Expected Behaviour:** Selecting "Timed Race" disables and dims the Laps spinbox. Selecting "Lap Race" disables and dims the Duration spinbox. The AI prompt builder uses a "timed race" description and `race_laps = 0` for timed races.
**Acceptance Criteria:**
- Select "Timed Race" in Event Planner. Laps field is greyed out and non-interactive.
- Select "Lap Race". Duration field is greyed out.
- Save a timed race event and set it active. AI setup prompt contains "timed race" not "1-lap race".

---

**ID:** DEF-P3-005
**Title:** Pit window is static and not recalculated on fuel or pace deviation
**Status:** Open
**Description:** Pit window is fixed at `stint.end_lap - 2` (warning) / `stint.end_lap` (box call). It is not updated when actual fuel consumption or lap pace deviates from the strategy plan.
**Expected Behaviour:** After each lap, the strategy engine checks actual fuel remaining and current pace against the planned stint. If deviation exceeds tolerance, the pit window recalculates and a revised box call is issued. `_replan_after_overdue()` considers fuel state, not only lap count.
**Acceptance Criteria:**
- Use 30% more fuel than the plan over 5 laps. Pit window moves earlier by at least 1 lap. Voice alert indicates the revised window.
- Save 20% fuel. Pit window extends by at least 1 lap.
- Pit window recalculation is logged in the Debug tab.

---

**ID:** DEF-P3-006
**Title:** Practice Review session summary not recalculated after loading from History
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_refresh_practice_summary()` method that iterates `_lap_table`, reads lap time ms (col 3) and fuel used (col 8), and updates `_lbl_pr_best`, `_lbl_pr_avg`, `_lbl_pr_fuel`, `_lbl_pr_laps`. Called at end of `_on_history_load_session()` and also at end of `_add_lap_row()` (live laps) to keep summary consistent during live sessions.
**Description:** When a historical session is loaded from the History tab into Practice Review, the Session Summary group (Best Lap, Avg Lap, Avg Fuel/Lap, Laps) is not recalculated from the newly loaded rows.
**Expected Behaviour:** After `_on_history_load_session()` populates the lap table, the session summary labels are immediately recalculated: best time, average time, average fuel per lap, and total lap count.
**Acceptance Criteria:**
- Load a historical session with 10 laps from History.
- Practice Review Session Summary shows the correct best lap, average lap, average fuel, and lap count.
- These values match a manual calculation from the same session in History.

---

---

**ID:** DEF-P3-007
**Title:** Disabled race type alternate field not visually dimmed when race type changes
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 6 partial)
**Related:** DEF-P3-004 (race type mutual exclusivity — was Partially Fixed)
**Description:** When "Timed Race" is selected in Event Planner, the Laps spinbox is correctly disabled (setEnabled(False)) but its text colour does not change. It appears the same as enabled fields. The user cannot visually distinguish which field is active without clicking it. Same issue in reverse when switching to Lap Race (Duration spinbox disabled but not greyed).
**Expected Behaviour:** The disabled spinbox should have visibly muted text colour (e.g., `#555` on the dark background). The enabled spinbox should have normal white text.
**Acceptance Criteria:**
- Select Timed Race in Event Planner. Laps spinbox text appears greyed/muted.
- Select Lap Race. Duration spinbox text appears greyed/muted; Laps spinbox returns to normal white.

---

**ID:** DEF-P3-008
**Title:** Top speed target never populated from valid practice telemetry
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 6 partial)
**Related:** DEF-P2-015 (top speed artefact guard — was Partially Fixed)
**Description:** The 11 km/h invalid artefact is correctly rejected by the `ms >= 50` guard (DEF-P2-015 fix). However, no valid top speed reading ever populates `_spin_top_speed` during a real practice session — the field always shows "—". The telemetry field used may not actually capture the session maximum speed, or the `>= 50` threshold may be too high and reject real low-speed readings early in the session.
**Expected Behaviour:** After driving at least one full lap that includes a straight, `_spin_top_speed` should show the highest speed recorded during that lap or session (typically 120–350 km/h for GT7 cars on normal circuits).
**Acceptance Criteria:**
- Drive at least one lap in Practice mode on any circuit with a straight.
- Setup Builder → Transmission → Top Speed shows a value ≥ 120 km/h (or "—" only if the telemetry data genuinely never exceeded 50 km/h on that lap).
- `SELECT MAX(max_speed_kmh) FROM lap_records WHERE session_id = <active_session>` returns a plausible value (> 0).

---

### P4 Low

---

**ID:** DEF-P4-001
**Title:** PTT button and voice status indicator are in Settings tab only
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_live_ptt_status_lbl` QLabel to the Live tab info row (after the Mode combo, before the stretch). `_on_ptt_status()` now updates both `_ptt_status_lbl` (Settings tab) and `_live_ptt_status_lbl` (Live tab). Status transitions (RADIO READY / TRANSMITTING / PROCESSING / ENGINEER RESPONDING) visible on the Live tab during a race without switching tabs.
**Description:** The PTT button and voice/microphone status indicator are located in the Settings tab. During an active race the driver cannot leave the Live tab to check PTT status or trigger a query. Spec §12.8 requires both controls on the Live Race Engineer tab.
**Expected Behaviour:** PTT button and voice status indicator appear on the Live Race Engineer tab, accessible without tab switching during a race. Settings tab may retain configuration-level controls.
**Acceptance Criteria:**
- Live Race Engineer tab contains a visible PTT button and voice status indicator.
- Pressing PTT from the Live tab triggers the full recording and response cycle.
- Voice status transitions (IDLE / TRANSMITTING / PROCESSING / RADIO READY) are visible on the Live tab.
See `TestPTTOnLiveTab` in `test_group5_fixes.py`.

---

**ID:** DEF-P4-002
**Title:** AI model hardcoded to claude-sonnet-4-6 instead of claude-opus-4-8
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_MODEL` constant removed from `strategy/_ai_client.py`; replaced with `_DEFAULT_MODEL = "claude-opus-4-8"`. `call_api()` gains `model: str | None = None` parameter; resolves `effective_model` with whitespace guard before falling back to `_DEFAULT_MODEL`. All `AILogEntry(model=...)` fields updated. `model` parameter added to `analyse_strategy`, `analyse_practice_session`, `build_car_setup`, `analyse_tyre_degradation` in `ai_planner.py` and `propose_profile_update` in `profile_updater.py`. All 4 `call_api` callers in `driving_advisor.py` and all 5 dashboard call sites pass `model=self._config.get("anthropic", {}).get("model") or None`.
**Description:** `strategy/_ai_client.py` has the model string hardcoded to `claude-sonnet-4-6`. The project default is `claude-opus-4-8`. No model selection UI exists.
**Expected Behaviour:** Default model is `claude-opus-4-8`. A model selector in Settings allows the user to choose between available Claude models. Selected model is persisted to config and used for all AI calls.
**Acceptance Criteria:**
- AI interaction log shows `"model": "claude-opus-4-8"` for all calls where no override is set.
- Settings tab contains a model selector.
- Changing the model in Settings causes the next AI call to use the newly selected model.

---

**ID:** DEF-P4-003
**Title:** Fuel formula uses additive lap safety instead of percentage multiplier
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_fuel_target_for_next()` and `build_fuel_check_response()` in `strategy/engine.py` now use `avg × laps × multiplier`. Module-level `_FUEL_MULTIPLIERS = {"safe": 1.08, "balanced": 1.05, "aggressive": 1.02}` added. Strategy mode read from `config["fuel"]["strategy"]` (defaults to "balanced"). `safety_margin_laps` additive pattern removed. 9 new unit tests added covering all three multipliers and edge cases. All 48 tests pass.
**Description:** `strategy/engine.py` `_fuel_target_for_next()` computed fuel as `avg × (laps + safety_margin_laps)`. Spec §18.1 requires `safe_fuel = avg × laps_remaining × multiplier` with per-strategy margins: Safe 8%, Balanced 5%, Aggressive 2%.
**Expected Behaviour:** Fuel target uses a percentage multiplier over laps remaining. Safe = 1.08, Balanced = 1.05, Aggressive = 1.02.
**Acceptance Criteria:**
- With `avg_fuel_per_lap = 3.0L` and 10 laps remaining, Balanced strategy targets 31.5L. ✓ (test passes)
- Safe strategy targets 32.4L. ✓ Aggressive targets 30.6L. ✓
- Unit test covers all three multipliers. ✓

---

**ID:** DEF-P2-QRF
**Title:** Race-finished announcement fires in Qualifying mode
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix (two-part):**
1. `voice/announcer.py` `_on_race_finish()`: added mode guard at top — `if _session_mode != "race": return`. Announcement now only fires when announcer is in Race mode.
2. `telemetry/state.py` timed race RACE_FINISHED path: changed `!= SessionType.PRACTICE` to `not in (SessionType.PRACTICE, SessionType.QUALIFYING)`. Prevents the RACE_FINISHED event from being emitted at all when session type is Practice or Qualifying.
**Description:** When the qualifying timer expired or lap count matched the race lap count while in Qualifying mode, `EventType.RACE_FINISHED` was emitted and `_on_race_finish()` announced "Race finished" to the driver. The timed race path in `state.py` guarded against Practice but not Qualifying.
**Expected Behaviour:** "Race finished" is only spoken when the Live mode is Race. Practice and Qualifying timers do not trigger the race-finished announcement.
**Acceptance Criteria:**
- Set Live mode to Qualifying. Let a timed session end. No "Race finished" announcement.
- Set Live mode to Race. Complete the race. Announcement fires correctly.
- Practice laps never trigger race-finished regardless of lap count.
See `TestQualifyingRaceFinished` in `test_group5_fixes.py`.

---

## Open Enhancements

---

**ID:** ENH-001
**Title:** Dashboard tab redesign
**Status:** Deferred — pending design decision
**Description:** The Dashboard tab was specified as the primary landing screen providing at-a-glance overview of active event, car, setup, strategy, and session state. It was suppressed in Architecture Stabilisation. See SUP-001.
**Expected Behaviour:** A Dashboard tab provides a single-screen summary with quick-links to other tabs. All summary fields populate from the active event and session state.
**Acceptance Criteria:** Dashboard tab renders without error. Active event, car, setup, and session state are displayed correctly.

---

**ID:** ENH-002
**Title:** PTT intents — should_push, save_fuel, where_losing_time not implemented
**Status:** Open
**Description:** Three intents from spec §19 are absent from `voice/query_listener.py` `_INTENT_KEYWORDS`. All other 13 intents are implemented.
**Expected Behaviour:** Saying "should I push?", "how much fuel can I save?", or "where am I losing time?" triggers the corresponding intent and returns an AI-generated response using current session context.
**Acceptance Criteria:** All three intents resolve from natural speech input. Responses reference current session data.

---

**ID:** ENH-003
**Title:** Strategy-becoming-impossible scenario not detected or announced
**Status:** Open
**Description:** When fuel remaining drops below a viable 1-stop strategy and tyre life is insufficient to extend the stint, no warning is issued. The driver may continue unaware the strategy is no longer achievable.
**Expected Behaviour:** `strategy/engine.py` detects when no valid stint plan can reach the end of the race. A voice alert fires once. A recalculation attempt is made and logged in Debug.
**Acceptance Criteria:** Simulated fuel-critical scenario triggers the voice alert and a Debug log entry. Alert fires once, not on every lap.

---

**ID:** ENH-004
**Title:** Live Race Engineer tab missing fuel target, estimated laps remaining, and pit window display
**Status:** Open
**Description:** The Live tab shows a fuel bar but not numeric fuel target, estimated laps remaining on current fuel, or pit window. Spec §9.3 and §12.8 require all three.
**Expected Behaviour:** Live tab displays current fuel (L), fuel target for next stint (L), estimated laps remaining on current fuel, and pit window (earliest — latest lap to box). All values update after each lap.
**Acceptance Criteria:** After lap 5 of a 25-lap race, all four values are visible and correct.

---

**ID:** ENH-005
**Title:** Practice Review missing per-lap tyre temperature trends
**Status:** Open
**Description:** Practice Review lap table has a Compound column but no tyre temperature data. Spec §12.6 requires tyre temperature trends per lap. `LapRecord` and `lap_records` do not store `tyre_temp_average`.
**Expected Behaviour:** Practice Review lap table includes average tyre temperature per lap sourced from `lap_records.tyre_temp_avg`.
**Acceptance Criteria:** After 5 laps, each row shows an average tyre temperature matching the DB value.

---

**ID:** ENH-006
**Title:** Setup Builder missing structured test plan output
**Status:** Open
**Description:** AI responses contain test plan suggestions in free text but no structured test plan widget exists. Spec §12.5 requires a dedicated test plan display.
**Expected Behaviour:** After an AI setup recommendation, a "Test Plan" section displays as a structured list: outlap checks, key corners to evaluate, conditions to watch for.
**Acceptance Criteria:** After AI Setup Analysis, a structured Test Plan section appears with at least 3 specific items.

---

**ID:** ENH-007
**Title:** AI driver feedback interpretation function not implemented
**Status:** Open
**Description:** Spec §14.1 requires a discrete `driver_feedback_interpretation` AI function that takes raw driver ratings and returns a structured handling diagnosis. Feedback is stored but never interpreted as a standalone AI call.
**Expected Behaviour:** Submitting driver feedback triggers an AI interpretation call returning: primary handling diagnosis, likely setup cause, suggested investigation area. Result stored in `ai_interactions` with `feature = 'feedback_interpretation'`.
**Acceptance Criteria:** Submitting feedback with corner entry understeer and exit oversteer triggers the interpretation call. Response contains a handling diagnosis. One `ai_interactions` row added with `feature = 'feedback_interpretation'`.

---

**ID:** ENH-008
**Title:** AI model selector not available in Settings
**Status:** Open
**Description:** No Settings UI exists to change the AI model. Related to DEF-P4-002.
**Expected Behaviour:** Settings tab contains a model selector dropdown. Selection is saved to `config["anthropic"]["model"]` and used for all subsequent AI calls.
**Acceptance Criteria:** Changing the model and rerunning an AI call shows the new model ID in the AI interaction log.

---

## Superseded Requirements

---

**ID:** SUP-001
**Title:** Dashboard tab
**Status:** Superseded — deferred to future redesign
**Description:** Specified as the primary landing screen. Not built and officially suppressed during Architecture Stabilisation. Tracked as ENH-001 for future redesign.
**Expected Behaviour:** N/A — requirement removed from current scope.
**Acceptance Criteria:** N/A.

---

**ID:** SUP-002
**Title:** Session Loader in Practice Review
**Status:** Superseded — removed in P6-A (2026-06-21)
**Description:** Session Loader widget (track/car dropdowns, session combo, Load and Delete buttons) embedded in Practice Review tab. Historical session loading now belongs exclusively to the History tab. `_build_practice_lap_bank_group()` call removed from `_build_practice_review_tab()`.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Practice Review contains no Session Loader widget. History tab provides session loading.

---

**ID:** SUP-003
**Title:** Car selector in Event Planner
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only car label (`_lbl_evt_active_car`) displayed in Event Planner. Car selection is owned by the Garage tab. Label removed as it added no functional value.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Event Planner contains no car label row.

---

**ID:** SUP-004
**Title:** Car selector in Setup Builder
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only car label (`_lbl_setup_car`) in Setup Builder form. Removed. Car is read from `_config["strategy"]["car"]` at call time.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Setup Builder contains no "Car:" read-only label row.

---

**ID:** SUP-005
**Title:** Track selector in Setup Builder
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only track label (`_lbl_setup_track`) in Setup Builder form. Removed. Track is read from `_config["strategy"]["track"]` wherever needed.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Setup Builder contains no "Track:" read-only label row.

---

**ID:** SUP-006
**Title:** Pit loss and lap/fuel tolerance spinboxes in Strategy Builder
**Status:** Superseded — removed in P6-C (2026-06-21)
**Description:** Three `QDoubleSpinBox` widgets (`_ai_pit_loss`, `_ai_lap_tolerance`, `_ai_fuel_tolerance`) allowed manual entry of race detail parameters in Strategy Builder. Values now come from active event config defaults. Widgets removed; callers updated to use `_config["strategy"].get("pit_loss_secs", 23.0)`.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Strategy Builder AI Analysis group contains no pit loss, lap tolerance, or fuel tolerance spinboxes.

---

**ID:** SUP-007
**Title:** Manual fuel burn input in Strategy Builder
**Status:** Superseded — removed in P6-C (2026-06-21)
**Description:** Manual fuel burn spinbox existed in Strategy Builder. Fuel burn is now authoritative from `RaceStateTracker.avg_fuel_per_lap`. Manual override removed.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Strategy Builder contains no manual fuel burn input spinbox.

---

**ID:** SUP-008
**Title:** Tyres in BoP tuning permissions
**Status:** Superseded — removed in P6-D (2026-06-21)
**Description:** "Tyre compound selection" was listed as a tuning category in `_TUNING_CATEGORIES`. In GT7 tyres are always freely changeable regardless of BoP. The entry was removed. Tyre widgets are always enabled in `_apply_setup_permissions()` unconditionally.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Tuning permissions list does not include a "Tyres" entry. Tyre dropdowns are always enabled in Setup Builder.

---

## Fixed Issues

---

**ID:** FIX-001
**Title:** Schema migration infrastructure missing — no PRAGMA user_version guard
**Status:** Fixed — 2026-06-20
**Description:** No schema version tracking. DDL ran on every startup. Fixed by adding `_migrate()` dispatcher, `PRAGMA user_version` read/write, idempotent `ALTER TABLE` via try/except per column, and `PRAGMA foreign_keys = ON` on every connection.

---

**ID:** FIX-002
**Title:** Missing DB tables — events, cars, user_profile, setups, lap_telemetry
**Status:** Fixed — 2026-06-20
**Description:** Five tables required by the spec did not exist. Created in schema v1 migration: `events`, `cars` (seeded from car_specs.json), `user_profile`, `setups`, `lap_telemetry` (compressed frame blob per lap). FK columns added to `sessions` and `lap_records`.

---

**ID:** FIX-003
**Title:** Events stored only in config.json with no DB backup or FK integrity
**Status:** Fixed — 2026-06-20
**Description:** All Event Planner CRUD redirected to `_db.upsert_event()`. Startup migration seeds DB from config on first run. `config["events"]` is no longer the authoritative store.

---

**ID:** FIX-004
**Title:** Setups stored only in config.json — diverged from setup_snapshots table
**Status:** Fixed — 2026-06-21
**Description:** Setup CRUD redirected to `setups` table via `_db.save_setup()` and `_db.update_setup()`. `get_all_setups_legacy()` added for backward-compatible loading. `_migrate_setups_to_db()` seeds DB from config on first run. `_setup_save()` writes to DB on every save.

---

**ID:** FIX-005
**Title:** Per-frame telemetry discarded after each lap — no TelemetrySample table
**Status:** Fixed — 2026-06-21
**Description:** `last_lap_frames()` added to `LapTelemetryRecorder`. EventDispatcher calls `recorder.last_lap_frames()` after each lap and passes the frame list to `write_lap(frames=...)`. Frames are zlib-compressed and stored in `lap_telemetry`.

---

**ID:** FIX-006
**Title:** Extended LapStats fields not persisted to lap_records
**Status:** Fixed — 2026-06-21
**Description:** `oversteer_count`, `oversteer_throttle`, `kerb_count`, `bottoming_count`, `snap_throttle_count`, `max_lat_g`, `off_track_count`, `tyre_temp_avg`, `is_out_lap`, `is_pit_lap`, `delta_ms`, `position`, `session_type`, `event_positions_json` columns added via migration and populated in `write_lap()`.

---

**ID:** FIX-007
**Title:** Driver feedback never injected into AI prompts
**Status:** Fixed — 2026-06-21
**Description:** `get_recent_feedback(car_id, track, limit=5)` added to `SessionDB`. `_get_driver_feedback_context()` added to `DrivingAdvisor`. All three prompt builders include a "## Recent Driver Feedback" section when feedback records exist for the current car and track.

---

**ID:** FIX-008
**Title:** Previous AI recommendations never fed back into prompts — AI amnesia
**Status:** Fixed — 2026-06-21
**Description:** `get_recent_ai_recommendations(feature, car_id, track, limit=2)` added to `SessionDB`. `_get_previous_ai_context(feature)` added to `DrivingAdvisor`. All prompt builders include a "## Previous AI Recommendations" section (truncated to 300 chars each) when prior calls exist for the same feature, car, and track.

---

**ID:** FIX-009
**Title:** Event profile not included in AI prompts
**Status:** Fixed — 2026-06-21
**Description:** `set_event_context(event_dict)` and `_get_event_context_block()` added to `DrivingAdvisor`. All prompts include a "## Event Rules" section covering track, race type, tyre wear, fuel multiplier, BoP, weather, damage, and required tyres. `_on_event_set_active()` calls `set_event_context()`.

---

**ID:** FIX-010
**Title:** Tyre compound not passed to AI calls
**Status:** Fixed — 2026-06-21
**Description:** `compound: str = ""` parameter added to all three `build_*_response()` and `_build_*_prompt()` methods in `DrivingAdvisor`. Compound injected as "Current tyre compound: X" in the header block. `_setup_analyse_ai()` passes compound from `_config["strategy"]["mandatory_compounds"]`.

---

**ID:** FIX-011
**Title:** AI prompts did not distinguish measured, calculated, and estimated data
**Status:** Fixed — 2026-06-21
**Description:** `_DATA_QUALITY_NOTE` class constant added to `DrivingAdvisor`. All prompts include a "## Data Quality Note" section with source annotations. Inline metric tags added throughout prompt builders.

---

**ID:** FIX-012
**Title:** Active tyre compound not written to lap_records
**Status:** Fixed — 2026-06-21
**Description:** `set_compound(compound: str)` added to `RaceStateTracker`. `_on_compound_selected()` in dashboard calls `self._tracker.set_compound(norm)`. EventDispatcher reads `self._tracker._current_compound` at lap save time and passes it to `write_lap(compound=...)`.

---

**ID:** FIX-013
**Title:** History tab Load button had no implementation
**Status:** Fixed — 2026-06-21
**Description:** `_on_history_load_session()` was a stub delegating to the removed session loader. Replaced with a direct implementation reading `_hist_selected_session_id`, calling `_db.get_session_laps(sid)`, and populating Practice Review via `_add_bank_lap_row()`.

---

**ID:** FIX-014
**Title:** Session mode not pushed to tracker and announcer at startup
**Status:** Fixed — 2026-06-21
**Description:** `set_session_mode()` and `set_session_type_override()` were only called from `_on_live_mode_changed()`. If the user never changed mode, tracker and announcer stayed at construction defaults. Fixed by calling `_on_live_mode_changed(config["live"]["mode"])` in the startup sequence.

---

## Awaiting Retest

Items here are code-complete and pass all 45 unit tests. Runtime verification against the running application and live GT7 telemetry is required before promotion to Fixed Issues.

---

**ID:** AWR-001
**Title:** Per-lap frame telemetry — verify frame_count populated after real lap
**Status:** Awaiting runtime verification
**Description:** FIX-005 is implemented. Requires a real lap to confirm `lap_telemetry` rows are written with non-zero frame counts.
**Expected Behaviour:** After completing one lap, `lap_telemetry` contains a row with `frame_count > 0`.
**Acceptance Criteria:** `SELECT frame_count FROM lap_telemetry ORDER BY id DESC LIMIT 1` returns a value > 0 immediately after the first lap.

---

**ID:** AWR-002
**Title:** Events persist from DB after config.json events section removed
**Status:** Awaiting runtime verification
**Description:** FIX-003 is implemented. Requires a restart test with `config["events"]` absent to confirm DB is authoritative.
**Expected Behaviour:** App loads event list from DB on startup with no errors and no dependency on `config["events"]`.
**Acceptance Criteria:** Delete `events` key from config.json. Restart app. Event Planner populates correctly from DB.

---

**ID:** AWR-003
**Title:** Setups persist from DB across restarts
**Status:** Awaiting runtime verification
**Description:** FIX-004 is implemented. Requires restart test to confirm `get_all_setups_legacy()` returns correct setups from DB.
**Expected Behaviour:** Saved setups appear in the setup list after restart without relying on config.json.
**Acceptance Criteria:** Save a new setup. Restart app. Setup appears in the list without config.json entry.

---

**ID:** AWR-004
**Title:** AI prompts contain driver feedback, event profile, and previous recommendations sections
**Status:** Awaiting runtime verification
**Description:** FIX-007 through FIX-009 implemented. Requires an AI call with `GT7_AI_DEBUG=1` to verify prompt structure.
**Expected Behaviour:** Debug log for an AI coaching call shows all three injected sections where data exists.
**Acceptance Criteria:** Prompt debug output contains "## Recent Driver Feedback", "## Event Rules", and "## Previous AI Recommendations" (where data exists for that car/track).

---

**ID:** AWR-005
**Title:** Active compound written to lap_records after each lap
**Status:** Awaiting runtime verification
**Description:** FIX-012 implemented. Requires setting a compound in Practice Review and completing a lap.
**Expected Behaviour:** The compound selected in Practice Review is present in `lap_records.compound` for each lap completed after the selection.
**Acceptance Criteria:** Set compound to "Racing Medium". Complete a lap. `SELECT compound FROM lap_records ORDER BY id DESC LIMIT 1` returns `'Racing Medium'`.

---

**ID:** AWR-006
**Title:** History tab Load populates Practice Review lap table
**Status:** Awaiting runtime verification
**Description:** FIX-013 implemented. Requires runtime test to confirm rows load from History into Practice Review. Note: session summary recalculation after load is tracked separately as DEF-P3-006.
**Expected Behaviour:** Selecting a session in History and clicking Load populates the Practice Review lap table with all laps from that session.
**Acceptance Criteria:** Select a session with at least 5 laps from History. Lap table in Practice Review shows all 5 rows. (Session summary recalculation tracked under DEF-P3-006.)

---

**ID:** AWR-007
**Title:** Strategy Builder AI analysis runs without error after spinbox removal
**Status:** Awaiting runtime verification
**Description:** P6-C removed `_ai_pit_loss`. `_run_ai_analysis()` now reads from `_config["strategy"].get("pit_loss_secs", 23.0)`. Requires a Strategy Builder AI run to confirm no AttributeError.
**Expected Behaviour:** Strategy Builder AI analysis completes. No AttributeError referencing `_ai_pit_loss`, `_ai_lap_tolerance`, or `_ai_fuel_tolerance`.
**Acceptance Criteria:** Run AI analysis in Strategy Builder. No errors in console. AI payload includes `"pit_loss_secs"` sourced from config.

---

**ID:** AWR-008
**Title:** Setup Builder and Event Planner show no removed car/track labels
**Status:** Awaiting runtime verification
**Description:** P6-B removed `_lbl_setup_car`, `_lbl_setup_track`, and `_lbl_evt_active_car`. Requires visual and error-free confirmation.
**Expected Behaviour:** Setup Builder has no "Car:" or "Track:" read-only label rows. Event Planner has no "Car:" read-only label row. No AttributeError in `_sync_setup_builder_from_event()`.
**Acceptance Criteria:** Open both tabs. Labels are absent. Set an event active. No errors in console.

---

**ID:** AWR-009
**Title:** Save Session does not crash after _lbl_bank_status removal (DEF-P1-003)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-003 added `_set_bank_status()` helper and replaced all 20 bare `.setText()` call sites. Requires a runtime click of "Save Session" in Practice Review to confirm no AttributeError.
**Expected Behaviour:** Clicking "Save Session" with at least one live lap in the table saves the session to the DB without crashing. Status feedback (if any) is silent when `_lbl_bank_status` is absent.
**Acceptance Criteria:**
- Click "Save Session" in Practice Review with ≥ 1 live lap. No AttributeError. No crash.
- `SELECT id, total_laps FROM sessions ORDER BY id DESC LIMIT 1` reflects the saved session.
- If the DB write fails, the error is caught and no unhandled exception propagates to the user.

---

**ID:** AWR-010
**Title:** Practice Analysis prompt shows correct race type for timed and lap events (DEF-P1-004)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-004 added `race_type` and `duration_mins` to `RaceParams` and branches the prompt on race type. Unit tests pass. Requires a live Practice Analysis run with `GT7_AI_DEBUG=1` to confirm the prompt content.
**Expected Behaviour:** Prompt for a timed race event contains "Race duration: X minutes (Timed Race)" and not "Race length: N laps". Prompt for a lap race contains "Race length: N laps".
**Acceptance Criteria:**
- Set Event Planner to Timed Race, 40 minutes. Set event active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Debug log contains "Race duration: 40 minutes (Timed Race)". Does not contain "Race length: 1 laps" or "Race length:" at all.
- Set Event Planner to Lap Race, 25 laps. Set event active. Re-run.
- Debug log contains "Race length: 25 laps".

---

**ID:** AWR-011
**Title:** Practice mode does not trigger RACE_FINISHED after timed event duration (DEF-P1-008)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-008 added `_session_type_override != SessionType.PRACTICE` guard to the RACE_FINISHED condition in `telemetry/state.py`. Unit tests pass for both suppression (practice) and correct firing (race). Requires a 40-minute live practice session to confirm silence.
**Expected Behaviour:** With a 40-minute timed race event active and Live tab in Practice mode, no "Race ended" voice announcement and no RACE_FINISHED event after 40 minutes.
**Acceptance Criteria:**
- Set 40-minute timed race event active. Switch to Practice mode. Drive for 40+ minutes. No "Race ended" announcement.
- `RACE_FINISHED` does not appear in the Debug tab event log.
- Switch to Race mode with the same event. After 40 minutes, the announcement fires correctly.

---

**ID:** AWR-012
**Title:** Practice Analysis prompt respects BoP tuning lock (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-005 added constraint block injection to `_build_practice_prompt()`. Unit tests pass. Requires a live Practice Analysis run with BoP enabled.
**Expected Behaviour:** With BoP=On, Tuning=Off: prompt contains "TUNING LOCKED" and no setup field values. With partial restrictions: prompt contains "EVENT TUNING RESTRICTIONS" listing locked categories.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Activate event. Run Practice Analysis with `GT7_AI_DEBUG=1`. Prompt contains "TUNING LOCKED". No ride height, spring, aero, or LSD numeric values in setup section.
- Set Event with BoP=On, Tuning=Yes, Allowed=[suspension]. Prompt contains "EVENT TUNING RESTRICTIONS" listing aero and differential as locked. Suspension values appear; aero values do not.

---

**ID:** AWR-013
**Title:** Tyre compound counts in Practice Analysis prompt match lap table (DEF-P1-006)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-006 corrects compound resolution in `_add_bank_lap_row()` and clears stale `_lap_compound_tags` on session load. Requires loading a session with a known compound mix.
**Expected Behaviour:** After loading a session with 15 RM laps and 7 RS laps, the Practice Analysis prompt compound counts match the visible table counts exactly.
**Acceptance Criteria:**
- Load session with 15 RM + 7 RS laps. Verify table shows correct compounds. Run Practice Analysis with `GT7_AI_DEBUG=1`. Prompt shows RM: 15, RS: 7 (or equivalent) — not the reverse.
- Reload the session a second time. Counts unchanged.

---

**ID:** AWR-014
**Title:** Fuel burn in Strategy Builder matches average from loaded historical session (DEF-P1-007)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-007 adds `_loaded_session_avg_fuel` which takes priority over the live tracker. Requires loading a historical session and checking the Strategy Builder fuel display.
**Expected Behaviour:** After loading 10 historical laps averaging 4.2 L/lap, Strategy Builder Fuel Burn shows ~4.2 L/lap. After a live lap completes, reverts to live tracker.
**Acceptance Criteria:**
- Load a session with laps averaging 4.2 L/lap from History. Strategy Builder Fuel Burn Auto updates to ~4.2. Practice Analysis prompt receives 4.2 as `fuel_burn`.
- Complete one live lap (any value). Strategy Builder Fuel Burn updates to the live tracker value.

---

**ID:** AWR-015
**Title:** Fuel start and fuel end appear after session reload (DEF-P2-014)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-014 adds `fuel_start`/`fuel_end` columns to DB (v2 migration) and wires them through `write_lap()`, `get_session_laps()`, and `_add_bank_lap_row()`. Requires completing laps and reloading.
**Expected Behaviour:** After completing laps and reloading from History, Fuel Start and Fuel End columns show the correct per-lap values.
**Acceptance Criteria:**
- Complete 3 laps in Practice. Each row shows numeric Fuel Start and Fuel End.
- Reload the session from History. Same columns show the same values.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 3` returns non-zero values.

---

**ID:** AWR-016
**Title:** Tyre wear multiplier in Practice Analysis prompt matches current event setting (DEF-P2-012)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-012 ensures `tyre_wear_multiplier` is read freshly from `_psc` each call. Debug log added. Requires activating an event with a specific wear value and running Practice Analysis.
**Expected Behaviour:** Prompt tyre wear matches the active event exactly. Debug log shows `[PracticeAnalysis] tyre_wear_multiplier=X.XX (from Event config)`.
**Acceptance Criteria:**
- Set event tyre wear to 1.0x. Activate. Run Practice Analysis. Prompt: "Tyre wear rate is the same as in practice." Console: `tyre_wear_multiplier=1.00`.
- Set to 1.5x. Re-activate. Re-run. Prompt: "1.5× faster." Console: `tyre_wear_multiplier=1.50`.

---

**ID:** AWR-017
**Title:** Practice Analysis validation gate blocks AI call on bad data (DEF-P2-016)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-016 adds a validation gate before the AI call. Requires testing with an empty session and with a valid session.
**Expected Behaviour:** With no fuel data and fewer than 2 laps, Practice Analysis shows a warning dialog. With valid data (≥ 2 laps, fuel > 0, correct race config), the AI call proceeds normally.
**Acceptance Criteria:**
- With 0 live laps and a timed race event with duration < 5 min active: clicking Run Analysis shows a warning dialog listing the issues. No AI API call made.
- After loading a valid session with ≥ 2 laps on one compound and fuel data: clicking Run Analysis proceeds to the AI call.

---

**ID:** AWR-018
**Title:** Outlap rows excluded from best/avg summary in Practice Review (DEF-P2-011)
**Status:** Awaiting runtime verification
**Test run:** 117/122 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-011 adds `is_out_lap` to `get_session_laps()`, stores the flag in row UserRole data, and filters it in `_refresh_practice_summary()`. Requires a live outlap to confirm the visual indicator and summary exclusion.
**Expected Behaviour:** After recording an outlap, the lap row shows dark green background and "Practice (OL)" label. Session summary best lap and average exclude the outlap time and fuel.
**Acceptance Criteria:**
- Complete an outlap (first lap after leaving pits). Practice Review shows the row with dark green background and "Practice (OL)" in the session column.
- Session Summary best lap is NOT the outlap time even if it's faster than all other laps.
- Load a session containing an outlap from History. Same visual and exclusion behaviour.

---

**ID:** AWR-019
**Title:** Pit stop indicator and outlap flag persist after History reload (DEF-P2-013)
**Status:** Awaiting runtime verification
**Test run:** 117/122 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-013 is complete (Group 2 + Group 3 side effects). Requires runtime confirmation after a pit lap is saved and reloaded.
**Expected Behaviour:** Pit lap rows show amber background and "Yes" in the Pit column after reload. Outlap rows show dark green and "Practice (OL)" after reload.
**Acceptance Criteria:**
- Complete a pit stop lap. Save session. Reload from History. Pit lap row shows amber background and "Yes" in Pit column.
- Complete an outlap. Reload. Outlap row shows dark green and "Practice (OL)".
- `SELECT is_pit_lap, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` reflects correct values.

---

**ID:** AWR-020
**Title:** Tuning Permissions group visible without BoP (DEF-P2-005)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** `_update_tuning_perms_visibility()` now uses `self._evt_tuning.isChecked()` only (removed BoP gate). Requires confirming the group appears correctly in the UI.
**Expected Behaviour:** Check "Tuning allowed" in Event Planner without enabling BoP → Tuning Permissions group is visible and all category checkboxes are shown. Uncheck Tuning → group hides.
**Acceptance Criteria:**
- Check "Tuning allowed" only. The Tuning Permissions group appears listing all categories.
- Uncheck Tuning. Group hides.
- Check both BoP and Tuning. Group remains visible.
- Check Suspension + Brake Balance. Save event. Active event has `allowed_tuning_categories = ["suspension", "brake_balance"]` in `_config["strategy"]`.

---

**ID:** AWR-021
**Title:** BoP status flows from Event Planner to Setup Builder Race Conditions (DEF-P2-004)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** No `_chk_bop` in Setup Builder. Race Conditions group shows `_lbl_rc_bop` / `_lbl_rc_tuning` from event. Requires confirming the flow in the UI.
**Expected Behaviour:** Set event BoP=Yes, Tuning=No → activate it → Setup Builder Race Conditions shows "BoP: Yes" and "Tuning Allowed: Not Allowed". Change event to BoP=No → activate → shows "BoP: No".
**Acceptance Criteria:**
- Setup Builder has no BoP checkbox anywhere.
- Activating BoP=Yes event → Race Conditions "BoP: Yes", all setup fields except tyres disabled, locked banner shown.
- Activating BoP=No event → Race Conditions "BoP: No", all setup fields enabled.

---

**ID:** AWR-022
**Title:** AI output validation flags locked tuning recommendations (DEF-P2-007)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** `validate_ai_setup_response()` added to `ai_planner.py`. Display handlers call it. Requires runtime test with a locked event.
**Expected Behaviour:** With tuning locked, if AI response recommends "increase rear downforce", an amber "Event Restriction Warning" banner appears at the top of the Setup Builder result and/or Practice Analysis result.
**Acceptance Criteria:**
- Set event BoP=On, Tuning=No. Run Setup Analyse. If AI mentions any locked field with an action verb, an amber warning banner appears before the AI response text.
- If AI complies with the tuning constraint (no locked field recommendations), no banner appears.
- Prompt debug log (GT7_AI_DEBUG=1) shows the `## EVENT RULES — TUNING LOCKED` block.

---

**ID:** AWR-029
**Title:** Top speed shows "—" for invalid capture, not ~11 km/h (DEF-P2-015)
**Status:** Awaiting runtime verification
**Test run:** 204/209 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_refresh_gear_ratios()` now only writes `_spin_top_speed` when `ms >= 50`. Requires driving a car with telemetry to confirm the spinbox shows "—" or a realistic value.
**Expected Behaviour:** After a lap with telemetry active, `_spin_top_speed` shows either "—" (no valid capture) or a realistic value ≥ 120 km/h. AI prompt does not contain "11 km/h" or any top speed < 50 km/h.
**Acceptance Criteria:**
- Connect PS5 telemetry. Drive one lap. Check Setup Builder Transmission → Top Speed field. Shows "—" or ≥ 120 km/h.
- Run Setup Analyse or Practice Analysis. Prompt does NOT contain "11 km/h".

---

**ID:** AWR-030
**Title:** Driver feedback form appears in Practice Review, not Setup Builder (DEF-P2-010)
**Status:** Awaiting runtime verification
**Test run:** 204/209 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Form relocated from Setup Builder to Practice Review. `_on_driver_feedback_submit()` now writes `session_id` from `_session_id`. Requires runtime confirmation of placement and DB write.
**Expected Behaviour:** Practice Review tab shows "Driver Feedback — After Stint" group below the Practice AI Analysis group. Setup Builder does not show this form. Submitting feedback writes a DB row linked to the active session.
**Acceptance Criteria:**
- Open Practice Review tab. "Driver Feedback — After Stint" group is visible with all combo selectors.
- Open Setup Builder tab. No "Driver Feedback" section present.
- Select a live mode (e.g., Practice). Complete one lap. Open Practice Review. Submit feedback with "Corner Entry: Too much oversteer". `SELECT * FROM driver_feedback ORDER BY id DESC LIMIT 1` shows a row with `session_id > 0`.
- Run AI coaching. Prompt debug log (GT7_AI_DEBUG=1) contains "## Recent Driver Feedback" with the submitted entry.

---

---

**ID:** AWR-031
**Title:** Event load restores all saved variables after Group 7 fix (DEF-P1-009)
**Status:** Awaiting runtime verification
**Test run:** 237/242 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_on_event_selected()` now casts REAL DB values to `int(round(...))` before passing to QSpinBox. The silent exception suppressor is removed.
**Expected Behaviour:** Selecting a saved event in Event Planner restores all fields: Tyre Wear ×, Fuel Mult ×, Available Tyres (checkboxes), Required Tyres (checkboxes), BoP, Tuning, Tuning Categories, Track, Race Type, Laps/Duration, Notes.
**Acceptance Criteria:**
- Save event: Tyre Wear=2, Fuel Mult=3, Available=RM+RH, Required=RH, BoP=On, Tuning=Off.
- Click event in list (do NOT click Set Active yet). Verify all five fields match saved values.
- Click Set Active. Confirm Strategy Builder shows ×2 wear, ×3 fuel.
- Run Practice Analysis. Prompt (GT7_AI_DEBUG=1) must contain `## EVENT RULES — TUNING LOCKED`.

---

**ID:** AWR-032
**Title:** AI Practice Analysis prompt contains BoP/tuning restrictions after Group 7 fix (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 237/242 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_run_practice_analysis()` already builds `tuning_locked` and `allowed_tuning` from `_config["strategy"]`. After Group 7, these values are now correct because the event load works. Needs runtime verification that the AI prompt actually receives the restriction block.
**Expected Behaviour:** Event with BoP=On, Tuning=Off activated → Practice Analysis prompt contains `## EVENT RULES — TUNING LOCKED`. AI response does not recommend suspension, aero, or gearbox changes.

---

**ID:** AWR-033
**Title:** Pit flag persists after History reload (DEF-P2-013 Group 8 fix)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `main.py` now passes `is_pit_lap` and `is_out_lap` from `LapRecord` to `write_lap()`. Previously these defaulted to 0. New sessions will correctly record these flags in the DB.
**Expected Behaviour:** Complete a pit stop lap. Reload from History. The pit lap row shows amber background and "Yes" in the Pit column. Non-pit laps show blank.
**Acceptance Criteria:**
- Complete a pit stop lap. Save session. Reload from History.
- Pit lap row shows amber background (#4A4000) and "Yes" in Pit column.
- `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` — at least one row shows is_pit_lap = 1.

---

**ID:** AWR-034
**Title:** Fuel Burn Auto updates on History reload (DEF-P2-009 Group 8 fix)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_on_history_load_session()` and `_import_bank_session()` now update `_lbl_fuel_burn_display` after setting `_loaded_session_avg_fuel`. Previously the label was only set at startup and never refreshed.
**Expected Behaviour:** Load a historical session. Strategy Builder Fuel Burn label immediately updates to the loaded session average. The value excludes pit laps and out-laps.
**Acceptance Criteria:**
- Load a session with known average fuel (e.g., ~3.5 L/lap). Strategy Builder Fuel Burn label shows approximately 3.50 L/lap immediately after load.
- Label text ends with "(loaded session)".

---

**ID:** AWR-035
**Title:** Fuel start/end and session_type correctly written to DB for new sessions (DEF-P2-014 / DEF-P2-013 support)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `main.py` now also passes `delta_ms` and `session_type` to `write_lap()`. These previously defaulted to 0/"". Fuel start/end have been passed since Group 2. This AWR confirms all fields are now correctly written in new sessions.
**Expected Behaviour:** After driving laps, `SELECT lap_num, session_type, fuel_start, fuel_end, is_pit_lap, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` shows non-empty session_type, non-zero fuel_start/end, and correct pit/out flags.
**Acceptance Criteria:**
- Drive 3 laps in Practice mode.
- `SELECT session_type, fuel_start, fuel_end, is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 3` — session_type = 'practice', fuel_start > 0, fuel_end > 0.
**Acceptance Criteria:**
- Activate a BoP=On, Tuning=Off event. Run Practice Analysis with tagged laps.
- Console (GT7_AI_DEBUG=1) shows `## EVENT RULES — TUNING LOCKED` in prompt.
- AI response makes no suspension/aero/transmission change recommendations.
- Activate a BoP=Off, Tuning=On, Allowed=Suspension+Brake event. Prompt shows `## EVENT TUNING RESTRICTIONS` with locked category list.

---

**ID:** AWR-036
**Title:** AI Log tab shows dry-run entry after GT7_AI_DEBUG call (DEF-P1-010 Group 9 fix)
**Status:** Awaiting runtime verification
**Test run:** 292/297 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `call_api()` now fires `_fire_log_hook()` with a `success=False` dry-run entry before raising `RuntimeError` in the `_AI_DEBUG` branch. AI Log tab must show intercepted calls.
**Expected Behaviour:** After any AI call made with `GT7_AI_DEBUG=1` set: AI Log tab shows an entry with feature name, model, `success=✗`, and the full prompt accessible in the Prompt sub-tab. DB records the entry with `success=0`.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1; python main.py` (PowerShell).
- Run Practice Analysis with at least two tagged laps.
- Console shows the full prompt text surrounded by `=` separators.
- Switch to AI Log tab. At least one entry visible with `✗` status indicator.
- Click the entry. Prompt sub-tab shows the full prompt text.
- `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.
- Without `GT7_AI_DEBUG`, real API call appears in AI Log with `✓` status and token count.

---

**ID:** AWR-037
**Title:** BoP On + Tuning Off → prompt contains "## EVENT RULES — TUNING LOCKED" (DEF-P1-005/DEF-P2-007)
**Status:** FAILED (2026-06-22) — Prompt still passes full tuning block with BoP=On, Tuning=Off active; "## EVENT RULES — TUNING LOCKED" not present; prompt not contain correct BoP/tuning context; AI response recommends locked setup changes; DEF-P1-005 reopened
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 tests prove `_build_practice_prompt()` inserts the tuning locked constraint block when `tuning_locked=True`. `RaceParams` correctly derives this from `not bool(_psc.get("tuning"))` in `_run_practice_analysis()`. Requires a live run to confirm the end-to-end path.
**Expected Behaviour:** With BoP=On, Tuning=Off active: Practice Analysis prompt contains `## EVENT RULES — TUNING LOCKED` and no editable setup field values. AI response contains no suspension/aero/differential change recommendations.
**Acceptance Criteria:**
- Set Event: BoP=On, Tuning=No. Set Active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Prompt contains `## EVENT RULES — TUNING LOCKED`.
- Setup section shows "[TUNING LOCKED — setup changes not permitted for this Event]" not numeric values.
- AI response section contains no ride height, spring rate, or aero recommendation.

---

**ID:** AWR-038
**Title:** Partial tuning allowed → locked setup fields replaced with ? in prompt (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 tests prove `_build_practice_prompt()` filters the setup dict to only pass allowed category keys to `format_setup_for_prompt()`. Locked keys show as `?` in the prompt. Requires a live run with partial tuning permissions.
**Expected Behaviour:** With BoP=On, Tuning=Yes, Allowed=[brake_balance]: prompt contains `## EVENT TUNING RESTRICTIONS`, brake_bias value appears, ride height shows as `?/?`.
**Acceptance Criteria:**
- Set Event: BoP=On, Tuning=Yes, Allowed=[Brake Balance]. Set Active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Prompt contains `## EVENT TUNING RESTRICTIONS`.
- Prompt shows `Brake bias: <actual value>` — not `?`.
- Prompt shows `Ride Height F/R: ?/? mm` — not actual ride height value.

---

**ID:** AWR-039
**Title:** Practice Analysis blocks AI call on insufficient input data (DEF-P2-016)
**Status:** Awaiting runtime verification
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 source-scan tests prove the validation gate checks `total_laps < 2`, `fuel_burn_per_lap <= 0`, `duration_mins < 5`, and `>= 2 laps per compound` — and that the `return` statement precedes `def _worker()`. Requires a live test with bad input to confirm the warning dialog fires before any API call.
**Expected Behaviour:** With 0 or 1 tagged laps, or with fuel_burn_per_lap = 0: clicking Run Practice Analysis shows a warning dialog listing the validation failures. No API call is made. No entry appears in AI Log.
**Acceptance Criteria:**
- Clear Practice Review (0 laps). Click Run Analysis. Warning dialog appears listing validation failure. No AI Log entry added.
- Set a Timed Race event with duration < 5 minutes active. Click Run Analysis. Warning dialog appears.
- Load a valid session (≥ 2 laps, fuel data present). Click Run Analysis. AI call proceeds normally.

---

**ID:** AWR-040
**Title:** Fuel Burn Auto resets to uncalibrated after Set Active with no live/loaded data (DEF-P1-011)
**Status:** PARTIAL PASS (2026-06-22) — PASSED: uncalibrated display after Set Active with no data; live telemetry path; loaded session average (fuel burn label). FAILED: Practice Review rows missing pit flag and fuel_start/fuel_end after History load — DEF-P2-013 and DEF-P2-014 reopened; root cause is data mapping divergence (DEF-P2-022)
**Test run:** 317/322 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 11 source-scan tests confirm `_on_event_set_active()` resets `_lbl_fuel_burn_display` when `avg_fuel_per_lap <= 0 AND _loaded_session_avg_fuel <= 0`. Requires live test with no telemetry and no loaded session.
**Expected Behaviour:** After clicking Set Active on any event with no live telemetry and no historical session loaded, Strategy Builder shows "— (complete practice laps to calibrate)" for Fuel Burn Auto.
**Acceptance Criteria:**
- Ensure no GT7 connection. Do not load a session.
- Create an event with Fuel Multiplier = 3×. Click Set Active.
- Navigate to Strategy Builder. Fuel Burn Auto shows "— (complete practice laps to calibrate)", not "3.00 L/lap (last session)".
- Load a session from History. Fuel Burn Auto updates to "X.XX L/lap (loaded session)".

---

**ID:** AWR-041
**Title:** AI Log list auto-selects new entry from live AI call (DEF-P2-021)
**Status:** FAILED (2026-06-22) — PASSED: entry visible; feature=Practice Analysis; Prompt sub-tab shows prompt. FAILED: entry NOT auto-selected on tab navigation; timestamp shows only HH:MM:SS, not date+time; status text does not distinguish dry-run from failure; DEF-P2-021 reopened with expanded scope
**Test run:** 317/322 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 11 source-scan tests confirm `_on_ai_log_entry()` passes `auto_select=True` so new live entries are auto-selected in the AI Log list via `setCurrentRow()`. Requires GT7_AI_DEBUG=1 run.
**Expected Behaviour:** After Practice Analysis with GT7_AI_DEBUG=1, navigating to AI Log tab shows the dry-run entry highlighted (selected) without requiring manual scroll.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Load ≥ 2 laps (valid fuel data). Run Practice Analysis.
- Switch to AI Log tab. Most recent entry is auto-selected (highlighted).
- Detail pane shows feature="Practice Analysis", success=✗, timestamp from this run.

---

**ID:** AWR-042
**Title:** BoP=On + Tuning=Off → runtime prompt contains TUNING LOCKED (DEF-P1-005)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12a confirms `_run_practice_analysis()` uses `get("tuning", False)` so absent or False "tuning" key → tuning_locked=True. Requires runtime test with a real event configured BoP=On, Tuning=Off.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Set it active. Run with `$env:GT7_AI_DEBUG=1`.
- Console output shows `tuning=False tuning_locked=True`.
- AI prompt (Prompt sub-tab) contains "TUNING LOCKED" or "## EVENT RULES — TUNING LOCKED".
- No ride height, spring rate, aero, or gear ratio recommendations in AI response.

---

**ID:** AWR-043
**Title:** History load shows pit flag and fuel_start/end for post-Group-8 sessions (DEF-P2-013/014)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12b investigation confirmed code is correct. AWR-043 must use a session recorded AFTER Group 8 was applied (not legacy data). Pit laps and fuel_start/fuel_end should appear correctly.
**Acceptance Criteria:**
- Record a new Practice session with ≥ 1 pit stop after Group 8 fix is applied.
- Go to History tab. Select the new session. Load to Practice Review.
- Pit stop lap row shows "Yes" in Pit column (amber background).
- Fuel Start and Fuel End columns show non-zero numeric values.
- `SELECT fuel_start, fuel_end, is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` confirms non-zero values.

---

**ID:** AWR-044
**Title:** AI Log entry auto-selected with full date+time and "⊘ DRY-RUN" status (DEF-P2-021)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12c implemented three fixes: timestamp format, status labels, and pending-select flush on tab activation. Requires GT7_AI_DEBUG=1 run.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Load ≥ 2 laps with valid fuel data. Run Practice Analysis.
- Navigate to AI Log tab. Most recent entry is auto-selected (highlighted), no manual scroll needed.
- Entry text shows: `[YYYY-MM-DD HH:MM:SS] Practice Analysis — ⊘ DRY-RUN — 0ms`.
- Prompt sub-tab shows the intercepted prompt (Developer Mode enabled).

---

**ID:** AWR-045
**Title:** No-refuel pit stop detected with `is_pit_lap = 1` (DEF-P2-023)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** Speed-based pit detection added. Requires a real Practice session with a no-refuel stop to confirm the 3-second stationary timer fires correctly.
**Acceptance Criteria:**
- Practice session with at least one pit stop where no fuel is taken.
- After the pit stop lap completes, `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` shows `is_pit_lap = 1` for that lap.
- Practice Review shows amber background on the pit stop lap row.
- Outlap following the no-fuel stop shows `is_out_lap = 1`.

---

**ID:** AWR-046
**Title:** Outlap persists after Save Session + History reload (DEF-P2-024)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_save_session_to_db()` now passes `is_out_lap` to `write_lap()`. Requires confirming the full save→clear→reload round-trip.
**Acceptance Criteria:**
- Run Practice session with outlap. Save Session button → Clear session → go to History tab → load session into Practice Review.
- Outlap row shows dark green background and "Practice (OL)" label (not plain "Practice").
- `SELECT is_out_lap FROM lap_records ORDER BY id DESC LIMIT 10` — outlap row has `is_out_lap = 1`.

---

**ID:** AWR-047
**Title:** Fuel Start/End columns populated after Save Session + History reload (DEF-P2-025)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_save_session_to_db()` now passes `fuel_start`/`fuel_end` to `write_lap()`. Requires confirming round-trip.
**Acceptance Criteria:**
- Run Practice session (≥ 3 laps). Note Fuel Start and Fuel End values in Practice Review. Save Session → Clear → History load.
- Practice Review Fuel Start and Fuel End columns show the same non-zero values as the live session.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 5` — non-zero values.

---

**ID:** AWR-048
**Title:** Compound change propagates to all laps until next pit stop (DEF-P2-019/026)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_on_compound_selected()` now stops propagation at `is_pit_lap` boundary instead of at any different compound. Requires a session with ≥ 10 laps to verify forward fill.
**Acceptance Criteria:**
- Practice session with 10+ laps. Change lap 4 compound to Racing Soft.
- Laps 5 through the session end all update to Racing Soft automatically.
- Laps 1–3 are unchanged.
- If a pit lap exists at lap 7, propagation stops at lap 7 (lap 8+ unchanged).

---

**ID:** AWR-049
**Title:** Live tab "Current Tyre" shows race plan stint compound (DEF-P2-020/027)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_get_current_tyre_compound()` implements three-priority hierarchy. Requires runtime verification of all three fallback levels.
**Acceptance Criteria:**
- Load a race plan (2 stints: S1=Racing Medium, S2=Racing Soft). Live tab shows "Current Tyre: Racing Medium". After pit stop, shows "Current Tyre: Racing Soft".
- Clear the race plan. Setup Builder front tyre = Racing Hard. Live tab shows "Current Tyre: Racing Hard".
- Set Setup Builder front tyre to blank/none. Live tab shows "Current Tyre: Not Set".
- Required tyres from Event never appear in the "Current Tyre:" label.

---

## Remediation Plan — 2026-06-21 Testing Session

> Priority order: Fix crashes first, then AI prompt accuracy, then data loss, then UI cosmetics.
> Do not implement fixes without updating this file and running `pytest` after each group.

---

### Group 8 — Session Reload Mapping (COMPLETED 2026-06-22)

**Defects:** DEF-P2-013, DEF-P2-014, DEF-P2-009
**Test result:** 274 passed / 279 collected / 5 skipped (Qt display) / 0 failed

**Root cause (DEF-P2-013 and DEF-P2-009):** `main.py` EventDispatcher called `write_lap()` without forwarding `is_pit_lap`, `is_out_lap`, `delta_ms`, or `session_type` from the `LapRecord`. All four parameters defaulted to 0/False/"". The DB therefore always stored `is_pit_lap = 0` and `is_out_lap = 0`. The live display read directly from the `LapRecord` object in memory (showing correct values); the reload path read from the DB (always 0 → pit flag missing, outlaps included in fuel average).

**Root cause (DEF-P2-009):** After `_on_history_load_session()` set `_loaded_session_avg_fuel`, the `_lbl_fuel_burn_display` widget in Strategy Builder was never refreshed. It was only populated at widget creation time (app startup) and never again.

**Fix 1 — `main.py` write_lap() extended (DEF-P2-013, DEF-P2-014 support, DEF-P2-009 support):**
Added `is_pit_lap=bool(getattr(record, "is_pit_lap", False))`, `is_out_lap=bool(getattr(record, "is_out_lap", False))`, `delta_ms=int(getattr(record, "delta_ms", 0))`, `session_type=(record.session_type.value if hasattr(record.session_type, "value") else str(...))` to the `write_lap()` call in `EventDispatcher._dispatch()`.

**Fix 2 — `ui/dashboard.py` fuel burn display refreshed (DEF-P2-009):**
Both `_on_history_load_session()` and `_import_bank_session()` now update `_lbl_fuel_burn_display` immediately after setting `_loaded_session_avg_fuel`: `self._lbl_fuel_burn_display.setText(f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")`.

**AWR-033:** Pit flag and out-lap flag persist in DB for new sessions → reload shows pit flag with amber background.
**AWR-034:** Fuel Burn Auto label updates to loaded session average immediately on History reload.
**AWR-035:** session_type, fuel_start, fuel_end, delta_ms all correctly written to DB for new sessions.

---

### Group 10 — AI Prompt BoP Context (COMPLETED 2026-06-22)

**Defects:** DEF-P1-005, DEF-P2-007, DEF-P2-016
**Test result:** 305 passed / 310 collected / 5 skipped (Qt display) / 0 failed
**Scope:** Test coverage only. No production code was changed.

**Investigation conclusion:** All three defects were correctly implemented in Groups 2–4. The root cause of UAT failures was Root Cause A (event persistence broken — Group 7), not missing production code. After Group 7, BoP/tuning values correctly reach `_config["strategy"]` and propagate to `_build_practice_prompt()` via `RaceParams`.

**Tests added — `tests/test_group10_ai_prompt_bop.py`** (13 tests in 3 classes):

- `TestPracticePromptSetupFiltering` (5 tests): Directly calls `_build_practice_prompt()` with known setup dict values and `RaceParams` combinations. Confirms: (1) `tuning_locked=True` replaces setup block with TUNING LOCKED text and adds `## EVENT RULES — TUNING LOCKED`; (2) `allowed_tuning=["brake_balance"]` includes `brake_bias` value but filters `ride_height_front` to `?`; (3) partial restriction adds `## EVENT TUNING RESTRICTIONS`; (4) no restriction passes all setup field values through.
- `TestPracticeValidationGate` (5 tests): Source-scan of `_run_practice_analysis()`. Confirms: validation gate checks `total_laps < 2`, `fuel_burn_per_lap <= 0`, `duration_mins < 5`, and `>= 2 laps per compound`. Confirms `return` statement precedes `def _worker()` — proving the gate exits before any API call.
- `TestRaceParamsBoPFields` (3 tests): Confirms `RaceParams` dataclass has `tuning_locked: bool = False` and `allowed_tuning` fields. Confirms `_run_practice_analysis()` derives `tuning_locked` as `not bool(_psc.get("tuning"))` and reads `allowed_tuning_categories` from strategy config.

**AWR-037:** BoP On + Tuning Off → live prompt contains `## EVENT RULES — TUNING LOCKED` (end-to-end runtime check)
**AWR-038:** Partial tuning allowed → locked fields show as `?` in live prompt (end-to-end runtime check)
**AWR-039:** Practice Analysis validation dialog fires before AI call when input data is invalid (runtime check)

---

### Group 13 — Live Session Defects: Pit Detection, Save Session, Compound Propagation, Live Tyre (COMPLETED 2026-06-22)

**Defects:** DEF-P2-023, DEF-P2-024, DEF-P2-025, DEF-P2-019/026, DEF-P2-020/027
**Test result:** 389 passed / 394 collected / 5 skipped (Qt display) / 0 failed

**13a — DEF-P2-023: Speed-based pit detection fallback:**
Fuel-only pit detection missed no-refuel stops entirely. Added `_low_speed_start: float = 0.0` to `_reset()`. In `_phase_transitions()`, under `RacePhase.RACING` guard: if `p.speed_kmh < 10`, start timing; if stationary for ≥ 3.0s, call `_enter_pit()`. Timer reset on speed recovery or when `_enter_pit()` fires. `_enter_pit()` also resets `_low_speed_start = 0.0` to prevent double-trigger.

**13b — DEF-P2-024 + DEF-P2-025: Save Session passes all LapRecord fields:**
`_save_session_to_db()` called `write_lap()` with only 6 positional args — omitted `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`, `delta_ms`, `session_type`. All defaulted to 0/False/"" in DB. The automatic EventDispatcher write (in `main.py`) was already correct; only the manual Save Session button path was broken. Fixed by adding all 6 keyword args with `getattr(lap, ...)` safe reads.

**13c — DEF-P2-019/026: Compound propagation stops at pit lap boundary:**
`_on_compound_selected()` broke propagation at the first row with any different compound string. Since every new lap row is pre-tagged with `_default_lap_compound`, the fill stopped at `start_row + 1`. Removed `if existing and existing != norm: break`. Added check: read `is_pit_lap` from col-0 UserRole data; if true, break. Fill now continues through all laps of the current stint.

**13d — DEF-P2-020/027: Live tyre label shows actual compound via priority hierarchy:**
Label previously read `mandatory_compounds` (race rules, not fitted compound). Replaced with:
- `_get_current_tyre_compound()`: Priority 1 = active race plan first-incomplete-stint `.compound`; Priority 2 = `_setup_tyre_f.currentText()`; Priority 3 = "Not Set".
- `_refresh_live_tyre_label()`: updates label with `"Current Tyre: {compound}"`.
- Wired to: `_on_tyre_preset_changed()` (stint change), `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, `_setup_tyre_f.currentTextChanged`.
- Label initial text changed to "Current Tyre: Not Set".
- Group 5 tests updated to assert new "Current Tyre:" prefix and `_refresh_live_tyre_label()` call pattern.

**Tests added — `tests/test_group13_live_session_defects.py`** (26 tests in 4 classes):
- `TestSpeedBasedPitDetection` (6): `_low_speed_start` initialized; speed < 10 threshold; 3.0s timeout; RACING phase guard; reset in `_enter_pit`.
- `TestSaveSessionPassesAllFields` (7): `fuel_start=`, `fuel_end=`, `is_pit_lap=`, `is_out_lap=`, `delta_ms=`, `session_type=`, `getattr(lap,` in `_save_session_to_db`.
- `TestCompoundPropagationStopsAtPitLap` (3): stops at `is_pit_lap`; reads UserRole; no `existing != norm` break.
- `TestLiveTyreLabelPriorityHierarchy` (10): `_get_current_tyre_compound` exists; P1 reads strategy_engine; P1 checks completed; P2 reads `_setup_tyre_f`; P3 returns "Not Set"; `_refresh_live_tyre_label` exists and calls helper; "Current Tyre:" prefix; `_on_tyre_preset_changed` calls refresh; `mandatory_compounds` not in helper.

**AWR-045:** No-refuel pit stop → `is_pit_lap=1`, `is_out_lap=1` in DB (DEF-P2-023)
**AWR-046:** Save Session + History reload → outlap shows dark green "Practice (OL)" label (DEF-P2-024)
**AWR-047:** Save Session + History reload → Fuel Start/End columns non-zero (DEF-P2-025)
**AWR-048:** Compound change on lap 4 → laps 5–end all update; stops at pit lap if present (DEF-P2-019/026)
**AWR-049:** Race plan loaded → "Current Tyre: Racing Medium"; after pit → "Current Tyre: Racing Soft"; no plan → setup tyre; nothing → "Not Set" (DEF-P2-020/027)

---

### Group 14 — UAT No-Go Remediation (COMPLETED 2026-06-22)

**Defects:** DEF-P1-012, DEF-P2-029, DEF-P2-030, DEF-P2-031, DEF-P2-032, DEF-P2-033, DEF-P2-034, DEF-P2-035
**Test result:** 426 passed / 431 collected / 5 skipped (Qt display) / 0 failed

**14a — DEF-P1-012: Practice prompt instructs AI to provide setup changes even when tuning is locked:**
`_build_practice_prompt()` in `strategy/ai_planner.py` line 685 had a fixed `## Instructions` line always asking for "3–5 Setup changes". The `constraint_block` said DO NOT recommend setup changes, but the explicit instruction overrode it. Fix: the `setup_changes` instruction is now a Python conditional — `"3–5 changes…"` when `not params.tuning_locked`; `"No setup changes…Tuning is locked…do NOT recommend any setup changes"` when `tuning_locked=True`.

**14b — DEF-P2-029: Outlap silently skipped when write_lap receives stats=None:**
`write_lap()` had `if stats is None: return 0` before entering the DB write block, silently dropping outlap metadata rows. Removed the guard. All stat field accesses made None-safe (`stats.field if stats else 0`). `positions_blob` JSON uses list comprehension with `if stats else []`. Metadata-only rows (zeros for telemetry) are now written and return a valid lap_record id.

**14c — DEF-P2-030: Save Session button creates a duplicate session:**
`_save_session_to_db()` called `open_session()` unconditionally, duplicating the session already opened by `_on_live_mode_changed()`. Fix: reads `self._dispatcher._session_id`; if > 0, skips `open_session()` and only calls `update_lap_compound()` + `update_lap_setup_id()` per lap. The fallback (no live session) retains the full `open_session()` path for manual saves.

**14d — DEF-P2-031: Qualifying outlap calming phrase never fires:**
`_exit_pit()` in `telemetry/state.py` emitted `PIT_EXIT` with `session_type=self._session_type.value` (packet-detected — often `unknown` in custom races). `voice/announcer.py` checks `event.data.get("session_type") == "qualifying"`. Fix: `_exit_pit()` now uses `_session_type_override.value` when set, falling back to `_session_type` otherwise — same pattern already used for `LapRecord.session_type`.

**14e — DEF-P2-032: Qualifying suppression for pit/fuel alerts (already fixed in Group 5):**
Investigation confirmed both `_on_pit()` and `_on_fuel_low()` in `announcer.py` already check `in ("practice", "qualifying")`. No production code change needed. Regression guard added to test file.

**14f — DEF-P2-033: AI Log auto-select fires on hidden widget:**
`_on_ai_log_entry()` called `_add_ai_log_list_item(auto_select=True)` which triggered `setCurrentRow()` even when the AI Log tab was not visible — the call had no effect. Fix: removed `auto_select=True`; added `QTimer.singleShot(0, self._flush_ai_log_pending_select)` instead. `_flush_ai_log_pending_select()` now checks `self._tabs.currentIndex() != 11` and returns early (leaving `_ai_log_pending_select = True`) if the tab is not active. `_on_tab_changed(11)` re-calls the flush when the user navigates there.

**14g — DEF-P2-034: AI Log timestamps stored in UTC, displayed as local time:**
All 3 occurrences of `_dt.datetime.utcnow().isoformat()` in `strategy/_ai_client.py` changed to `_dt.datetime.now().isoformat()`. This applies to the debug dry-run path, the success path, and the except/error path.

**14h — DEF-P2-035: Garage tab shows no DB setups; exceptions silently swallowed:**
`_on_garage_car_selected()` had bare `except Exception: pass` around both the sessions query and the setup query. Replaced with `traceback.print_exc()`. Added a DB setups block: looks up `car_id` from recent sessions for the displayed car name, calls `get_setups_for_car(car_id)`, and populates `_garage_setups_table` rows from the results.

**Tests added — `tests/test_group14_uat_remediation.py`** (37 tests in 7 classes):
- `TestBoPPromptSetupChangesConditional` (4): setup_changes instruction references tuning_locked; locked branch present; 3–5 changes in unlocked branch; DO NOT directive in locked branch.
- `TestBoPPromptRoundTrip` (4): Live calls to `_build_practice_prompt()`. Locked prompt contains TUNING LOCKED; no ride_height value; no "3–5 changes". Unlocked prompt has "3–5 changes".
- `TestWriteLapNoneStats` (5): write_lap returns nonzero id; preserves is_out_lap; preserves fuel_start/end; zeros telemetry; increments total_laps.
- `TestSaveSessionNoduplication` (4): reads `_dispatcher._session_id`; calls `update_lap_compound`; returns early before `open_session`; existing_sid guard precedes open_session.
- `TestPitExitSessionTypeOverride` (4): `_exit_pit` uses override; fallback to detected; checks `is not None`; logic correctness.
- `TestQualifyingAlertSuppression` (3): regression guards for `_on_pit`, `_on_fuel_low`, `_on_race_finish`.
- `TestAiLogAutoSelectQTimer` (5): QTimer used; pending_select flag set; flush checks currentIndex; flag left set when tab not visible; no auto_select=True.
- `TestAiLogLocalTimestamp` (3): no utcnow(); datetime.now() present; replace("T"," ") display format retained.
- `TestGarageDbIntegration` (5): get_all_sessions called; get_setups_for_car called; traceback.print_exc used; method exists; zero-lap sessions filtered out.

**AWR-050:** Practice Analysis with BoP+Tuning Off → AI response says "tuning not permitted" and provides no setup changes (DEF-P1-012)
**AWR-051:** Pit outlap recorded in DB with is_out_lap=1 when manual Save Session clicked after clear (DEF-P2-029)
**AWR-052:** Save Session with live session active → no duplicate session in History; compound tags applied to existing session (DEF-P2-030)
**AWR-053:** Qualifying mode → pit exit → outlap calming phrase heard from announcer (DEF-P2-031)
**AWR-054:** Practice mode → fuel low → NO voice alert (DEF-P2-032 regression guard)
**AWR-055:** AI call completes → AI Log tab auto-scrolls to new entry when tab is visible; flag deferred when tab hidden (DEF-P2-033)
**AWR-056:** AI Log entry timestamps match local clock time, not UTC (DEF-P2-034)
**AWR-057:** Garage tab → car with DB-saved setups → setup rows appear in setups table (DEF-P2-035)

**AWR-058:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_run_ai_analysis()` race_params dict includes all 6 new fields (race_type, duration_mins, tuning_locked, allowed_tuning, bop, avail_tyres). `_build_race_prompt()` injects tuning_block, bop_line, avail_line. (DEF-P1-013)
**AWR-059:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_worker()` captures `_hist_db`, `_hist_track`, `_hist_car_name` before thread start; calls `_hist_db.get_car_id(_hist_car_name)` not hardcoded 0. (DEF-P1-014)
**AWR-060:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_run_practice_analysis()` race_params includes `"bop": bool(_psc.get("bop", False))`; `_build_practice_prompt()` injects bop_line. (DEF-P2-038)
**AWR-061:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `avail_tyres` in both race_params dicts, RaceParams dataclass, `build_car_setup()`, `_build_setup_from_scratch_prompt()`, and both prompt builders. (DEF-P2-039)
**AWR-062:** CLOSED (2026-06-23 runtime validation) — Source confirmed: worker queries `get_recent_feedback(car_id, track, limit=5)`, formats rows into `_driver_feedback_str`, passes to `analyse_practice_session()`. Produces output when feedback exists for this car+track. (DEF-P2-040)
**AWR-063:** CLOSED (2026-06-23 Group 15A) — DEF-P3-013 fixed. `AILogEntry` now has `car_id`/`track` fields. All `call_api()` sites, `ai_planner.py` functions, `DrivingAdvisor` methods, and dashboard callers thread real car_id and track to every `ai_interactions` row. `get_recent_ai_recommendations()` now returns results when matching data exists. (DEF-P2-041 / DEF-P3-013)
**AWR-064:** CLOSED (2026-06-23 runtime validation) — Source confirmed: coaching branch reads `_car_name_ql`, `_car_specs_ql = self._car_specs_ref`, `_compound_ql` and passes all three to `build_coaching_response()`. Dashboard calls `update_car_specs()` in `_on_event_set_active()`. (DEF-P2-036)
**AWR-065:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_active_setup_getter` checked first; dashboard wires `set_active_setup_getter(self._current_setup_dict)` at startup. Falls back to config only if getter not set. (DEF-P2-037)
**AWR-066:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `race_len_line` computed conditionally on `params.race_type == "timed"`; prompt uses `{race_len_line}`. Hardcoded "N laps" string removed. (DEF-P3-009)
**AWR-067:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `build_car_setup()` and `_build_setup_from_scratch_prompt()` accept all 5 new params; `_race_ctx_block` constructed and injected; `_run_build_setup()` reads and passes all from `_sc_build`. (DEF-P3-010)
**AWR-068:** CLOSED (2026-06-23 runtime validation) — `_DATA_QUALITY_NOTE` constant confirmed in `ai_planner.py` and injected into both prompts. AWR-063 blocker now resolved via DEF-P3-013 fix (Group 15A). (DEF-P3-011)
**AWR-069:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_display_strategy_results()` imports `validate_ai_setup_response`, iterates options, checks setup_changes text, prepends orange `F5A623` banner when violations found. (DEF-P3-012)

---

### Group 16 — Phase 2: Per-Lap Telemetry in Practice and Strategy Prompts (COMPLETED 2026-06-23)

**Roadmap:** Phase 2 (2-A / 2-B / 2-C / 2-D from SMART_RACE_ENGINEER_ROADMAP.md)  
**Test result:** 643 passed / 648 collected / 5 skipped (Qt display) / 0 failed  
**New tests:** `tests/test_group16_per_lap_telemetry.py` — 74 tests

**Files changed:**
- `telemetry/recorder.py` — `TelemetryFrame` gains `tyre_temp_fl/fr/rl/rr: float = 0.0`; `LapStats` gains `tyre_temp_fl/fr/rl/rr_avg: float = 0.0`; `_compute_stats()` computes per-corner averages (frames with temp > 0 only, rounded to 1 dp); `record_frame()` feeds tyre temps from packet
- `data/session_db.py` — `lap_records` DDL adds 4 tyre_temp avg columns; `_V3_ALTER_COLUMNS` + `_migrate_v3()` + PRAGMA user_version=3 guard added; `write_lap()` persists tyre temp avgs; `get_session_laps()` gains `exclude_pit`, `exclude_out`, `limit` params + expanded SELECT (telemetry fields); `get_recent_fuel_sequence()` returns chronological per-lap fuel (L/lap) excluding pit/out/zero-fuel laps; `get_compound_lap_sequences()` returns per-compound lap-time sequences with session filter and limit-per-compound cap
- `strategy/ai_planner.py` — `_build_per_lap_telemetry_block()` formats per-lap table (lock_up, spin, oversteer+T, kerb, lat-g, optional tyre temps); `_build_fuel_trend_block()` formats avg/std-dev/95th-pct fuel trend (Phase 2-B); `_build_compound_sequence_block()` formats per-compound sequences with linear-regression deg rate (Phase 2-C); `analyse_practice_session()` + `_build_practice_prompt()` gain `per_lap_telemetry: list | None = None`; `analyse_strategy()` + `_build_race_prompt()` gain `fuel_sequence: list | None = None` and `compound_sequences: dict | None = None`
- `ui/dashboard.py` — `_run_practice_analysis()` captures `_hist_session_id` before thread, queries `get_session_laps()` with exclude_pit/exclude_out/limit=5, passes `per_lap_telemetry` to `analyse_practice_session()`; `_run_ai_analysis()` queries `get_recent_fuel_sequence()` + `get_compound_lap_sequences()` before thread, passes both to `analyse_strategy()`

---

### Group 15A — AILogEntry car_id/track Fix (COMPLETED 2026-06-23)

**Defect:** DEF-P3-013  
**Test result:** 569 passed / 574 collected / 5 skipped (Qt display) / 0 failed  
**New tests:** `tests/test_group15a_ai_log_car_track.py` — 56 tests

**Files changed:**
- `strategy/_ai_client.py` — `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields; `call_api()` gains matching kwargs; all three `AILogEntry` construction sites (debug, success, exception) pass them through
- `strategy/ai_planner.py` — `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` gain `car_id: int = 0`; thread to `call_api()` with `track=params.track` / `track=track`
- `strategy/driving_advisor.py` — all four `call_api()` sites pass `car_id=self._car_id_ref[0], track=self._config.get("strategy", {}).get("track", "")`
- `ui/dashboard.py` — `_run_ai_analysis()` resolves `_car_id_strat` before worker; `_run_practice_analysis()` passes `car_id=_car_id_hist`; `_run_build_setup()` resolves `_car_id_build` before worker; `_on_ai_log_entry_dict()` passes `car_id`/`track` when reconstructing AILogEntry from DB rows

**AWR-063:** CLOSED — previous AI recommendations in Practice Analysis will now be found when a prior run for the same car+track exists in `ai_interactions`.

---

### Group 12 — BoP/Tuning Runtime Fix + History Mapping Investigation + AI Log Display (COMPLETED 2026-06-22)

**Defects:** DEF-P1-005 (12a), DEF-P2-013/014/022 (12b), DEF-P2-021 (12c)
**Test result:** 363 passed / 368 collected / 5 skipped (Qt display) / 0 failed

**12a — DEF-P1-005 root cause confirmed and fixed:**
Bug: `_psc.get("tuning", True)` in `_run_practice_analysis()` (line 3183). With default `True`, absent "tuning" key → `not bool(True)` = `tuning_locked=False` — practice analysis sends full setup even when event was configured with Tuning=Off. Old configs (pre-Group-7) or configs where `_on_event_set_active()` silently failed (due to `except Exception: pass`) lacked the "tuning" key entirely.
- Fix 1: `_psc.get("tuning", False)` → absent key = locked (safe default).
- Fix 2: `except Exception: pass` → `import traceback; traceback.print_exc()` in `_on_event_set_active()` so future failures are visible.
- Fix 3: `GT7_AI_DEBUG` context print block added after `race_params` dict built — shows bop, tuning, tuning_locked, allowed_tuning, race_type, fuel_mult, tyre_wear to stdout.

**12b — DEF-P2-022/013/014 investigation: code correct, hypothesis incorrect:**
Both load paths (`_on_history_load_session()` and `_import_bank_session()`) use same `get_session_laps()` SELECT returning all required columns. Both pass all fields to `_add_bank_lap_row()`. `write_lap()` in `main.py` correctly passes `fuel_start`, `fuel_end`, `is_pit_lap` from `LapRecord`. Zero values in AWR-040 retest were pre-Group-8 session data with DEFAULT 0. DEF-P2-022 closed. DEF-P2-013/014 status updated. No production code change required.

**12c — DEF-P2-021 three remaining issues fixed:**
- Timestamp: `entry.timestamp[:19].replace("T", " ")` → YYYY-MM-DD HH:MM:SS (shows date, not just HH:MM:SS).
- Status: "✓ OK" / "✗ FAIL" / "⊘ DRY-RUN" (dry-run when duration_ms==0 and "AI_DEBUG" in error_msg).
- Auto-select: `_ai_log_pending_select = True` set in `_on_ai_log_entry()`; `_flush_ai_log_pending_select()` new helper; `_on_tab_changed()` calls flush for index 11 (AI Log tab). `setCurrentRow(count-1)` re-applied when tab becomes visible.

**Tests added — `tests/test_group12a_bop_tuning_propagation.py`** (12 tests in 4 classes):
- `TestTuningLockedDefault` (4): Confirms get("tuning", False) not True; key in race_params; allowed_tuning in race_params.
- `TestOnEventSetActiveExceptionLogging` (2): No bare except:pass; traceback present.
- `TestStratIsReference` (3): setdefault used; strat["tuning"] written; strat["bop"] written.
- `TestDebugContextPrint` (3): GT7_AI_DEBUG gate; tuning_locked in debug; bop in debug.

**Tests added — `tests/test_group12b_history_practice_mapping.py`** (20 tests in 5 classes):
- `TestGetSessionLapsSelect` (4): fuel_start/end, is_pit_lap, is_out_lap in SELECT.
- `TestHistoryLoadSessionMapping` (4): _on_history_load_session passes all 4 fields.
- `TestImportBankSessionMapping` (4): _import_bank_session passes all 4 fields.
- `TestAddBankLapRowDisplay` (4): _add_bank_lap_row uses is_out_lap, is_pit_lap, fuel_start, fuel_end.
- `TestWriteLapStoresAllFields` (4): write_lap INSERT includes all 4 fields.

**Tests added — `tests/test_group12c_ai_log_display.py`** (12 tests in 3 classes):
- `TestAiLogTimestampFormat` (3): [:19] replace T; not [11:19].
- `TestAiLogStatusText` (5): OK/FAIL/DRY-RUN labels; AI_DEBUG detection; duration_ms==0.
- `TestAiLogPendingSelect` (6): pending flag set; flush method exists; flush reads flag; flush calls setCurrentRow; tab_changed handles index 11; flush clears flag.

**AWR-042:** BoP=On, Tuning=Off → runtime prompt contains TUNING LOCKED; `GT7_AI_DEBUG=1` stdout shows `tuning=False tuning_locked=True` (DEF-P1-005)
**AWR-043:** Load session (recorded AFTER Group 8 fix) from History into Practice Review → pit flag "Yes" in pit column; fuel_start/fuel_end show numeric values (DEF-P2-013/014)
**AWR-044:** After Practice Analysis with GT7_AI_DEBUG=1, navigate to AI Log tab → new entry auto-selected; timestamp shows YYYY-MM-DD HH:MM:SS; status shows "⊘ DRY-RUN" (DEF-P2-021)

---

### Group 11 — UI Display Fixes (COMPLETED 2026-06-22)

**Defects:** DEF-P1-011, DEF-P2-021
**Test result:** 313 passed / 318 collected / 5 skipped (Qt display) / 0 failed

**Root cause (DEF-P1-011):** `_on_event_set_active()` calls `_sync_setup_builder_from_event()` which only updates `_lbl_fuel_burn_display` when `tracker.avg_fuel_per_lap > 0`. When no live telemetry is present, the label retains the initialisation value from `config["strategy"]["fuel_burn_per_lap"]` (e.g. `3.0` from a prior session). This stale value was displayed as "3.00 L/lap (last session)". In the smoke test the number coincidentally equalled the event fuel multiplier (both 3×), causing confusion.

**Fix (DEF-P1-011) — `ui/dashboard.py` `_on_event_set_active()`:**
Added reset block after `_sync_setup_builder_from_event()` call. When `tracker.avg_fuel_per_lap <= 0 AND _loaded_session_avg_fuel <= 0`, resets `_lbl_fuel_burn_display` to `"— (complete practice laps to calibrate)"`. Live telemetry and loaded-session paths are unchanged.

**Root cause (DEF-P2-021):** `_add_ai_log_list_item()` appended the new item and called `scrollToBottom()`. However `bridge.ai_log_entry` uses `QueuedConnection` (cross-thread delivery) so the slot fires after the current timer tick. If the AI Log tab is not visible at that moment, `scrollToBottom()` has no visual effect. When the user navigated to the tab they saw the DB-loaded startup history at the top and missed the new entry at the bottom. The user clicked an old entry and saw the Prompt sub-tab (from that historical entry) — this explained "Prompt tab populated. Prompt text visible."

**Fix (DEF-P2-021) — `ui/dashboard.py` `_add_ai_log_list_item()` and `_on_ai_log_entry()`:**
Added `auto_select: bool = False` parameter to `_add_ai_log_list_item()`. When `True`, calls `setCurrentRow(count - 1)` after `addItem()`, selecting and highlighting the new entry. `_on_ai_log_entry()` (live signal) passes `auto_select=True`. `_on_ai_log_entry_dict()` (DB startup load) keeps `auto_select=False` to avoid disrupting history load order.

**Tests added — `tests/test_group11_ui_display_fixes.py`** (12 tests in 3 classes):
- `TestFuelBurnLabelResetOnEventSwitch` (4 tests): Source-scan of `_on_event_set_active()`. Confirms: checks `avg_fuel_per_lap`, checks `_loaded_session_avg_fuel`, resets `_lbl_fuel_burn_display` to uncalibrated text, reset is conditional on `<= 0`.
- `TestAiLogAutoSelect` (4 tests): Source-scan of `_add_ai_log_list_item()` and related methods. Confirms: `auto_select` parameter present, `setCurrentRow` called when flag is set, `_on_ai_log_entry` passes `auto_select=True`, `_on_ai_log_entry_dict` does NOT pass `auto_select=True`.
- `TestFuelBurnLiveTelemetryUpdate` (4 tests): Source-scan of `_refresh_telemetry_context()`. Confirms: reads `avg_fuel_per_lap` from tracker, updates `_lbl_fuel_burn_display`, uses "from telemetry" label suffix to distinguish from loaded-session values, guards update with `avg > 0` check. (Note: History-load path covered in Group 8 — `TestHistoryLoadSessionMapping.test_updates_fuel_burn_display_after_load` and `TestImportBankSessionMapping.test_updates_fuel_burn_display_after_load`.)

**AWR-040:** Fuel Burn Auto resets to uncalibrated after Set Active with no live/loaded data (DEF-P1-011)
**AWR-041:** AI Log list auto-selects new live entry after Practice Analysis (DEF-P2-021)

---

### Group 9 — AI Debug / Log Visibility (COMPLETED 2026-06-22)

**Defects:** DEF-P1-010
**Test result:** 292 passed / 297 collected / 5 skipped (Qt display) / 0 failed

**Root cause:** `call_api()` in `strategy/_ai_client.py` raised `RuntimeError` in the `_AI_DEBUG` branch before reaching the `try/except` block that contains both `_fire_log_hook()` calls. When `GT7_AI_DEBUG=1` was set:
- Prompt was printed to stdout (visible in Debug tab terminal output)
- `RuntimeError` was raised immediately
- `_fire_log_hook()` was never called
- `db.log_ai_interaction()` was never called
- `bridge.ai_log_entry` signal was never emitted
- AI Log tab received no entry

The same issue existed for the missing API key path (`ValueError` before hook), but the primary test scenario used `GT7_AI_DEBUG=1`.

**Fix — `strategy/_ai_client.py`:**
Added `_fire_log_hook(AILogEntry(...))` immediately before `raise RuntimeError` in the `_AI_DEBUG` block. Dry-run entries use:
- `success=False`
- `response="[AI_DEBUG dry-run — no API call made]"`
- `error_msg="AI_DEBUG mode active — prompt intercepted, no API call made"`
- `duration_ms=0`, `prompt_tokens=0`, `response_tokens=0`, `estimated_cost=0.0`
- `feature`, `model`, `prompt` from the actual call arguments

No changes to `dashboard.py`, `session_db.py`, or `main.py` — the signal chain was already fully wired and correct.

**AWR-036:** Launch with `$env:GT7_AI_DEBUG=1`. Run Practice Analysis. AI Log tab shows dry-run entry with feature name and full prompt text. `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.

---

### Group 7 — Event Persistence (COMPLETED 2026-06-22)

**Defects:** DEF-P1-009
**Unblocks:** DEF-P1-005 (AI prompt BoP context — was blocked by wrong tyre_wear/tuning values in strategy config)
**Test result:** 237 passed / 242 collected / 5 skipped (Qt display) / 0 failed

**Root cause identified:** `_evt_tyre_wear`, `_evt_fuel_mult`, and `_evt_refuel_rate` are `QSpinBox` (integer-only) widgets, but their corresponding DB columns (`tyre_wear`, `fuel_mult`, `refuel_rate_lps`) are `REAL` in the SQLite schema. `get_all_events()` returns Python `float` values; PyQt6's `QSpinBox.setValue()` raises `TypeError` on a float argument. The `except Exception: pass` in `_on_event_selected()` silently swallowed this TypeError, leaving the spinboxes at 1 (minimum/default) and skipping all remaining field population in the function (lines 7322–7357 never executed).

**Fix 1 — int cast for REAL→QSpinBox in `_on_event_selected()`:**
Changed three bare `setValue(evt.get(...))` calls to `setValue(int(round(evt.get(...) or default)))` for `tyre_wear`, `fuel_mult`, and `refuel_rate_lps`. All other fields (laps, duration, mandatory_stops) are INTEGER columns and return Python int — no cast needed.

**Fix 2 — Exception handler now prints traceback:**
Changed `except Exception: pass` to `except Exception: import traceback; traceback.print_exc()`. Silent exception suppression was the reason the root cause was invisible for so long.

**Fix 3 — Tuning perms group visibility consistency:**
`_on_event_selected()` was using `_bop_on and _tun_on` for the tuning permissions group visibility while `_update_tuning_perms_visibility()` correctly used `_tun_on` only. Fixed to `bool(_tun_on)` to match the design intent (tuning perms visible whenever Tuning is enabled, regardless of BoP).

**AWR-031:** Event load restores tyre_wear, fuel_mult, avail_tyres, req_tyres, tuning cats from saved values (not defaults). Set Active pushes correct multipliers to Strategy Builder and AI prompt.

**AWR-032:** DEF-P1-005 BoP prompt restrictions — after Group 7 fix, BoP/tuning values correctly reach `_config["strategy"]` and are forwarded to `_run_practice_analysis()` as `tuning_locked` / `allowed_tuning`. Requires runtime verification that AI prompt shows `## EVENT RULES — TUNING LOCKED` for a BoP=On event.

---

### Group 1 — Crash Fixes (COMPLETED 2026-06-21)

**Defects:** DEF-P1-003, DEF-P1-004, DEF-P1-008
**Test result:** 65 passed / 70 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-009, AWR-010, AWR-011)

**DEF-P1-003: _lbl_bank_status AttributeError — DONE**
- Added `_set_bank_status(self, msg: str)` helper with `hasattr` guard to `ui/dashboard.py`.
- Replaced all 20 bare `self._lbl_bank_status.setText(` calls via replace_all.
- `_refresh_lap_bank()` was already safe (has its own guard); no change needed there.

**DEF-P1-004: Timed race shown as 1-lap race in Practice Analysis prompt — DONE**
- Added `race_type: str = "lap"` and `duration_mins: int = 0` to `RaceParams` dataclass.
- Read `strat["race_type"]` and `strat["race_duration_minutes"]` in `_run_practice_analysis()`.
- `_build_practice_prompt()` now branches: timed → "Race duration: X minutes (Timed Race)", lap → "Race length: N laps".

**DEF-P1-008: Practice mode triggers RACE_FINISHED — DONE**
- Added `and self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition at `telemetry/state.py` line 292.
- Race mode and None override still fire. Qualifying is unguarded → tracked as DEF-P2-017.

---

### Group 2 — AI Prompt Accuracy + Data Persistence (COMPLETED 2026-06-21)

**Defects:** DEF-P1-005, DEF-P1-006, DEF-P1-007, DEF-P2-012, DEF-P2-014, DEF-P2-016
**Test result:** 98 passed / 103 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-012 through AWR-017)

**DEF-P1-005: Full setup payload ignores BoP restrictions — DONE**
- Added `tuning_locked` / `allowed_tuning` to `RaceParams`. `_build_practice_prompt()` in `ai_planner.py` injects constraint block. `_TUNING_CATEGORY_KEYS` maps category codes to setup dict keys for filtering.

**DEF-P1-006: Compound counts wrong in AI prompt — DONE**
- DB compound preferred over stale `_lap_compound_tags` in `_add_bank_lap_row()`. Stale tags cleared before session load in `_import_bank_session()`.

**DEF-P1-007: Fuel burn disagrees between Strategy Builder and lap log — DONE**
- `_loaded_session_avg_fuel` attribute set on historical load, cleared on live lap, checked first in `_computed_fuel_burn_lpl()`.

**DEF-P2-012: Wrong tyre wear multiplier — DONE**
- `_run_practice_analysis()` reads `tyre_wear_multiplier` fresh from `_psc` each call. Debug log added.

**DEF-P2-014: fuel_start / fuel_end not persisted to DB — DONE**
- Schema v2 migration adds `fuel_start`/`fuel_end` columns. `write_lap()` extended. `get_session_laps()` returns them. `main.py` dispatcher passes them.

**DEF-P2-016: No validation gate before AI call — DONE**
- Validation gate checks: timed race duration ≥ 5 min, lap race ≥ 2 laps, fuel burn > 0, ≥ 2 laps on one compound. Shows warning dialog and aborts if any fail.

---

### Group 3 — Session Reload Accuracy (COMPLETED 2026-06-21)

**Defects:** DEF-P2-011, DEF-P2-013
**Test result:** 117 passed / 122 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-018, AWR-019)

**DEF-P2-011: Outlaps included in summary — DONE**
- `get_session_laps()` now SELECTs `is_out_lap`. `_add_bank_lap_row()` accepts and stores `is_out_lap` in UserRole; displays "Practice (OL)" + dark green `#003A1A`. `_add_lap_row()` stores UserRole flags and uses `#003A1A` for outlap rows. `_refresh_practice_summary()` reads UserRole per row and skips outlap rows from best/avg/fuel.

**DEF-P2-013: Pit indicator lost after reload — DONE (fixed by Group 2)**
- `get_session_laps()` returns `is_pit_lap`. `_add_bank_lap_row()` uses it. Callers pass it. Group 3 additionally stores it in UserRole data. Side-effects of DEF-P2-014 fix covered this defect.

**Also fixed (side effects):**
- `_on_history_load_session()` now clears stale `_lap_compound_tags` before loading (was missing, `_import_bank_session()` had it). Also computes `_loaded_session_avg_fuel` (was missing from History tab path — only `_import_bank_session()` had it). Fuel average now excludes both pit laps and outlaps.

---

### Group 4 — BoP and Tuning Permissions (COMPLETED 2026-06-21)

**Defects:** DEF-P2-004, DEF-P2-005, DEF-P2-007 (DEF-P2-006 already fixed in Group 2)
**Test result:** 156 passed / 161 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-020, AWR-021, AWR-022)

**DEF-P2-004: BoP independent source removed — DONE**
- `_chk_bop` removed; `_current_setup_dict()` reads from `_config["strategy"]["bop"]`; Race Conditions group has read-only `_lbl_rc_bop` and `_lbl_rc_tuning` labels populated by `_sync_setup_builder_from_event()`.

**DEF-P2-005: Tuning permissions visibility fixed — DONE**
- `_update_tuning_perms_visibility()` changed from `bop.isChecked() and tuning.isChecked()` to `tuning.isChecked()` only. Group now shows whenever Tuning is enabled, regardless of BoP.

**DEF-P2-006: Setup Builder field locking — DONE (Group 2)**
- `_apply_setup_permissions()` fully implemented; tyre widgets always re-enabled; locked banner shown when tuning disabled.

**DEF-P2-007: AI output validation added — DONE**
- Prompt constraint blocks already injected by `_tuning_constraint_block()`. New: `validate_ai_setup_response()` in `ai_planner.py` post-processes AI output for locked-field violations. `_display_setup_result()` and `_display_practice_results()` in `dashboard.py` call it and prepend an amber warning banner if violations are detected.

---

### Group 5 — Live Mode + Voice Guards (COMPLETED 2026-06-21)

**Defects:** DEF-P2-002, DEF-P2-008, DEF-P2-QRF (new), DEF-P3-001, DEF-P3-002, DEF-P4-001
**Test result:** 187 passed / 192 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-023 through AWR-028)

**DEF-P2-002: Pit/fuel alerts now suppressed in Qualifying — DONE**
- `announcer.py` `_on_pit()` and `_on_fuel_low()` guard changed from `== "practice"` to `in ("practice", "qualifying")`.

**DEF-P2-008: PTT in Practice — CONFIRMED ALREADY WORKING**
- Source scan: `QueryListener` started unconditionally in `main.py:566`. `_handle_trigger()` has `try/except` + `traceback.print_exc()` + `_emit_ptt_status("PTT ERROR: ...")`. No mode guard in `_handle_trigger_inner()`. No code change needed.

**DEF-P2-QRF: Qualifying race-finished defect — DONE**
- `announcer.py` `_on_race_finish()`: added `if _session_mode != "race": return` guard as first line.
- `state.py` timed-race RACE_FINISHED path: changed `!= SessionType.PRACTICE` to `not in (SessionType.PRACTICE, SessionType.QUALIFYING)`.

**DEF-P3-001: Brake balance step — CONFIRMED ALREADY CORRECT**
- `_setup_bb.setSingleStep(1)` at `dashboard.py:3984`. No code change needed.

**DEF-P3-002: Live tyre compound label — DONE**
- Added `_lbl_live_tyre_compound` update in `_on_live_mode_changed()` — reads `mandatory_compounds` from strategy config and refreshes the label.

**DEF-P4-001: PTT status on Live tab — DONE**
- Added `_live_ptt_status_lbl` QLabel to Live tab info row (after Mode combo).
- `_on_ptt_status()` now updates both `_ptt_status_lbl` (Settings) and `_live_ptt_status_lbl` (Live).

---

**AWR-023:** Qualifying session — pit/fuel alerts silent
**AWR-024:** Qualifying timer end — no "Race finished" announcement
**AWR-025:** Practice timer end — no "Race finished" announcement
**AWR-026:** Practice PTT press — TRANSMITTING → PROCESSING → RADIO READY visible on Live tab
**AWR-027:** Event set active with compound — Live tab shows "Tyre: Racing Hard" (etc.)
**AWR-028:** Brake balance spinbox — each click changes value by exactly 1

---

### Group 6 — UI Placement + Data Quality (COMPLETED 2026-06-22)

**Defects:** DEF-P2-010, DEF-P2-015
**Register corrections:** DEF-P2-003, DEF-P2-017, DEF-P3-004 (all implemented; register was stale)
**Test result:** 204 passed / 209 collected / 5 skipped (Qt display) / 0 failed

**DEF-P2-015: Top speed ~11 km/h artefact — DONE**
- `_refresh_gear_ratios()` in `dashboard.py`: changed `if ms > 0:` to `if ms >= 50:`.
- Raw-field artefact (~3.0 raw × 3.6 = ~11 km/h) no longer written to `_spin_top_speed`.
- Spinbox shows "—" (special value text for 0). AI prompt receives `transmission_max_speed_kmh: 0`, which is excluded from setup recommendations.

**DEF-P2-010: Driver feedback form relocated to Practice Review — DONE**
- Removed `_build_driver_feedback_form()` call from `_build_setup_builder_tab()`.
- Added `_build_driver_feedback_form()` call to `_build_practice_review_tab()` (after Practice AI Analysis group).
- `_on_driver_feedback_submit()` updated: `_setup_feeling_input` guarded with `hasattr`; `session_id` uses `getattr(self, "_session_id", 0)`; `_setup_analyse_ai()` call removed (wrong tab context).

**Register corrections (code already correct, register was stale):**
- **DEF-P2-003** (Required Tyres checkbox grid): `_req_tyre_checks` already implemented; marked Fixed.
- **DEF-P2-017** (Qualifying RACE_FINISHED): Fixed via DEF-P2-QRF in Group 5; marked Fixed.
- **DEF-P3-004** (Race type mutual exclusivity): `_on_race_type_changed()` already implemented; marked Fixed.

**AWR-029:** Top Speed field shows "—" or ≥ 120 km/h (not ~11 km/h) after telemetry
**AWR-030:** Driver Feedback form visible in Practice Review; absent from Setup Builder

---

### (Original) Group 4 — Session Data Persistence (SUPERSEDED — completed in Groups 2 + 3)

**Defects:** DEF-P2-013 (completed in Group 3), DEF-P2-014 (completed in Group 2)

**DEF-P2-013: Pit stop indicator lost after reload — DONE (see Group 3 above)**

**DEF-P2-014: fuel_start/fuel_end not persisted — DONE (see Group 2)**

**Original plan for reference:**
- Step 1 (now done): Add `is_pit_lap` to the SELECT in `get_session_laps()`.
- Step 2: Add `is_pit_lap: bool = False` parameter to `_add_bank_lap_row()`.
- Step 3: When `is_pit_lap`, set col 11 to "Yes" and apply amber background (same logic as `_add_lap_row()`).
- Test: Save a pit lap. Reload from History. Col 11 shows "Yes" with amber background.

**DEF-P2-014: Fuel start/end not persisted**
- File: `data/session_db.py`, `telemetry/state.py` or `main.py`
- Step 1: Add `fuel_start REAL NOT NULL DEFAULT 0.0` and `fuel_end REAL NOT NULL DEFAULT 0.0` columns to `lap_records` via schema migration (version bump in `_migrate()`).
- Step 2: Pass `fuel_start` and `fuel_end` from `LapRecord` into `write_lap()`.
- Step 3: Add `fuel_start`, `fuel_end` to `get_session_laps()` SELECT.
- Step 4: Pass values through `_add_bank_lap_row()` and populate cols 6 and 7.
- Test: Complete a lap. Reload from History. Cols 6 (Fuel Start) and 7 (Fuel End) show non-zero values matching the live session.

---

### Group 5 — Session/Mode Logic

**Defects:** DEF-P1-007, DEF-P2-011, DEF-P2-017
**DEF-P1-008 was in this group — now DONE (Group 1).**

**DEF-P1-007: Fuel burn source mismatch**
- File: `ui/dashboard.py` — `_refresh_practice_summary()` and Strategy Builder fuel auto
- Fix: When historical laps are loaded into Practice Review via `_on_history_load_session()`, compute a session-scoped fuel average from the loaded rows and push it to a local `_loaded_session_avg_fuel` attribute. The Strategy Builder Fuel Burn Auto field reads from `self._loaded_session_avg_fuel` if set, falling back to `self._tracker.avg_fuel_per_lap` for live sessions only.
- Test: Load 10 historical laps averaging 4.2 L/lap. Strategy Builder shows ~4.2. Live session with 3.0 L/lap avg shows 3.0 when no historical session is loaded.

**DEF-P2-017: Qualifying mode may trigger RACE_FINISHED on timed events**
- File: `telemetry/state.py` — RACE_FINISHED condition (same block as DEF-P1-008 fix, line 292)
- Fix: Extend the existing Practice guard to also exclude Qualifying. Change:
  `and self._session_type_override != SessionType.PRACTICE`
  to:
  `and self._session_type_override not in (SessionType.PRACTICE, SessionType.QUALIFYING)`
- Tests required:
  - Qualifying mode does not fire RACE_FINISHED (new test in `TestRaceFinishedPracticeGuard`)
  - Practice mode still suppressed (existing AWR-011 + test)
  - Race mode still fires (existing test)
  - None override still fires (existing test)
- Test: Set timed event active. Switch Live tab to Qualifying mode. Drive for full duration. No "Race finished" announcement.
- Note: One-line change. Low risk. Can be batched with Group 1 if approved before Group 5.

**DEF-P2-011: Best lap includes outlaps**
- File: `ui/dashboard.py` — `_refresh_practice_summary()` (line 6782), `_add_lap_row()` (line 2156)
- Step 1: In `_add_lap_row()`, store `is_out_lap` as `Qt.ItemDataRole.UserRole` data on the lap time cell (col 3). Pass `is_out_lap` as a parameter (default `False`).
- Step 2: In `_refresh_practice_summary()`, skip rows where col 3 item's `UserRole` data is `True`.
- Step 3: For `_add_bank_lap_row()`, pass `is_out_lap` from the DB row and store it similarly.
- Test: Record an outlap (~30 s slower than pace). Session Summary best lap is not the outlap. Average fuel excludes the outlap.

---

### Group 6 — UI Behaviour

**Defects:** DEF-P2-005

**DEF-P2-005: Tuning Permissions group requires BoP to appear**
- File: `ui/dashboard.py` — `_update_tuning_perms_visibility()` (line 6996)
- Fix: Change condition from `self._evt_bop.isChecked() and self._evt_tuning.isChecked()` to `self._evt_tuning.isChecked()`.
- Test: Check Tuning without BoP — group appears. Uncheck Tuning — group hides. Check both — group still appears.

---

### Implementation Constraints

- Fix each group atomically. Run `python -m pytest tests/ -v` after each group. Do not proceed to the next group if tests fail.
- Each fix must include a regression test in `tests/` that would have caught the defect.
- Do not implement fixes until this analysis is confirmed complete by user.
- **Group 1 COMPLETE (2026-06-21).** 65/70 tests pass. AWR-009/010/011 awaiting runtime.
- Group 2 partial compound dependency: DEF-P2-012 (tyre wear) needs Group 3 for accuracy verification; DEF-P1-005, DEF-P2-015, DEF-P2-016 have no compound dependency.
- DEF-P2-017 (qualifying guard) is a one-line extension of the Group 1 state.py fix — can be batched with Group 2 or treated as Group 5.
- Groups 4, 5, 6 are independent of each other and can be done in parallel if needed.

---

### Group 17 (user Group 16) — Corner-Level Telemetry Learning (2026-06-23)

**New tests:** `tests/test_group17_corner_learning.py` — 64 tests, all pass

**Coverage:**
- CornerIssue dataclass and ISSUE_TYPES constant
- `_corner_id_from_xyz()` — XZ world bucket snapping (100 m grid)
- PATH A (`detect_issues_from_lap_records`) — brake_lock, wheelspin, oversteer from event_positions_json
- Repeated-issue thresholds: ≥3 laps OR ≥30% of valid laps
- One-off events below both thresholds not flagged
- Multiple distinct corners produce separate issues
- Malformed JSON in event_positions_json skipped safely
- PATH B (`detect_corner_events_from_frames`) — frame-by-frame brake lock + exit wheelspin detection
- `detect_issues_from_frame_data` — aggregate per-lap events with thresholds
- `strong_drive_confirmed` excluded from repeated-issue list
- `merge_issues()` — PATH B overwrites PATH A for same (corner_id, issue_type)
- Fix verification: fixed, improved, unchanged, worse, not_enough_data
- `build_corner_summary_for_prompt()` — header, corner IDs, issue types, %, setup focus, fix status, max_issues cap
- `get_setup_advice()` — all major issue types return non-empty lists
- SessionDB schema v4: `corner_issues` table created, `PRAGMA user_version = 4`
- `save_corner_issues()` — accepts CornerIssue objects and plain dicts
- `get_corner_issues()` — filtered by car_id and track
- `get_previous_corner_issues()` — excludes current session_id, different car returns empty
- Safe degradation: missing JSON field, missing pos/wheel fields in frames, verify_fix with sparse dicts

**Files changed:**
- NEW: `data/corner_learning.py`
- `data/session_db.py` — _DDL_V4, _migrate_v4(), save_corner_issues(), get_corner_issues(), get_previous_corner_issues(), get_session_laps() adds event_positions_json to SELECT
- `strategy/ai_planner.py` — corner_issues_summary param in _build_practice_prompt(), analyse_practice_session(), _build_race_prompt(), analyse_strategy()
- `strategy/driving_advisor.py` — corner_issues_summary param in build_coaching_response(), _build_coaching_prompt(), build_setup_advice_response(), _build_setup_prompt(), _build_combined_prompt()
- `ui/dashboard.py` — corner learning wired in _run_practice_analysis() (PATH A detection, save, verify, prompt); _run_ai_analysis() reads saved issues for strategy prompt
- `tests/test_group16_per_lap_telemetry.py` — test_user_version_is_3 updated to >= 3

**Tests Run:** 707 pass / 5 skip / 0 fail (712 collected)

---

### Group 18 — DEF-P3-014 Startup Residual Strategy/Race Config Activation (2026-06-23)

**Defect:** Running `python main.py` with a previously saved event/plan printed:
```
[Strategy] plan set: 2 stints
[StateTracker] race config: timed, duration=40.0 min
[StateTracker] race config: timed, duration=40.0 min
```
No strategy plan should be active and no race config should be pushed to StateTracker until the user explicitly activates one.

**Root Causes:**

1. `main.py` lines 361–365 (removed): called `strategy_engine.set_plan()` at startup with `config["strategy"]["stops"]` — immediately activated the Live Race Engineer.

2. `main.py` lines 509–527 (removed): applied `tracker.set_race_config()` from persisted `config["race"]` / `config["strategy"]["race_type"]` on startup before window opened — first StateTracker print.

3. `ui/dashboard.py` `_update_race_config()` (removed block): called `tracker.set_race_config()` during `_build_strategy_builder_tab()` construction on every startup — second StateTracker print.

4. `ui/dashboard.py` `_on_event_set_active()` line 7801 (fixed): imported `from telemetry.tracker import RaceType` — module does not exist. Import was silently caught by `except Exception`, so `set_race_config()` never fired from the explicit user activation path. Fixed to `from telemetry.state import RaceType`.

**Fixes Applied:**

- `main.py`: Removed `set_plan()` call with saved stops (stops remain available in config for Strategy Builder UI population in `dashboard.__init__`)
- `main.py`: Removed entire `set_race_config()` startup block (both `config["race"]` path and strategy fallback)
- `ui/dashboard.py` `_update_race_config()`: Removed the `if race_type in ("timed", "lap"):` tracker-push block (11 lines). Config persistence and label update remain.
- `ui/dashboard.py` `_on_event_set_active()`: Fixed import `telemetry.tracker` → `telemetry.state`

**New tests:** `tests/test_group18_startup_no_plan.py` — 21 tests, all pass

**Coverage:**
- StateTracker starts with UNKNOWN race type and zero duration
- RaceStrategyEngine starts with empty stints and inactive
- `main.py` source: no `set_plan()` call in `main()` function
- `main.py` source: no `set_race_config()` call in `main()` function
- `_update_race_config()` source: no `set_race_config()` call
- `_update_race_config()` still calls `_persist_config()`
- `_on_event_set_active()` source: no `telemetry.tracker` import
- `telemetry.tracker` module confirmed non-existent
- `set_plan([])` leaves engine inactive
- `set_plan([Stint(...)])` populates stints but `_active` remains False
- Empty-stint engine ignores events (no-op)
- `set_race_config()` changes `_manual_race_type` and `_timed_race_duration_ms`
- `computed_remaining_ms()` returns -1 when no config set (correct idle state)
- Config with saved stops does not auto-activate engine after fix
- Config with race_type does not auto-push to tracker after fix
- Zero `set_race_config()` calls during simulated startup

**Architecture boundary preserved:** `_on_event_set_active()` (explicit user action) remains the ONLY path that calls `tracker.set_race_config()`.

**Tests Run:** 728 pass / 5 skip / 0 fail (733 collected)

---

### Group 17A — Track Intelligence Seed Loader and Track Modelling Foundation (2026-06-24)

**New module:** `data/track_intelligence.py` — typed seed loader for `docs/track_modelling_seed/track_modelling_seed.yaml`.

**Dataclasses added:**
- `TrackSeedMetadata` — schema name, version, purpose, track/layout counts
- `CalibrationCarProfile` — primary calibration car facts (Porsche 911 RSR '17)
- `TrackLayoutSeed` — layout facts: length, corners, elevation, pit delta, flags, modelling status
- `TrackLocationSeed` — location grouping layouts, aliases, region/country/surface flags
- `TrackSeedLoadResult` — load result with errors, warnings, duplicate detection, unknown status tracking

**Enum added:**
- `TrackModellingStatus` — 9 values: `not_modelled`, `seed_only`, `telemetry_sampled`, `reference_path_built`, `segment_detected`, `user_reviewed`, `practice_refined`, `race_validated`, `engineer_grade`
- Helper methods: `is_ready_for_calibration()`, `is_ready_for_ai()`, `missing_calibration_requirements()`

**Functions added:**
- `load_track_seed(yaml_path, force_reload)` — loads + validates YAML, caches on success
- `get_track_locations()` — returns all 41 track locations
- `get_track_layouts()` — returns flat list of all 121 layouts
- `resolve_track_layout(track_location_id, layout_id)` — exact lookup by IDs
- `search_track_layouts(query)` — case-insensitive substring search across names and aliases
- `build_seed_track_context_for_prompt(track_location_id, layout_id)` — AI prompt context block with caveat for unmodelled layouts

**Validation checks:**
- File exists check
- Required metadata fields (`schema_name`, `schema_version`, `generated_utc`)
- At least one calibration car profile
- Non-empty tracks list
- Unknown modelling_status values preserved and reported
- Duplicate layout IDs detected and reported
- Layout ID prefix match (warning if mismatch)
- Alias clash with other location IDs (warning if found)

**Caching:** Results cached after first successful load from default path. Custom path never pollutes cache.

**Documentation:** `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` created.

**Coverage:**
- All 9 enum values exist and are correct strings
- `is_ready_for_calibration()`: False below `telemetry_sampled`, True at and above
- `is_ready_for_ai()`: False below `segment_detected`, True at and above
- `missing_calibration_requirements()`: non-empty for unmodelled, empty for engineer_grade
- Seed file exists and loads without errors
- Metadata fields populated: schema_name, schema_version
- 41 track locations loaded
- 121 layouts loaded (flat list)
- Calibration car: Porsche 911 RSR, 509 BHP, 1243 kg, RH tyres, Gr.3 MR
- No duplicate layout IDs in real seed
- Fuji Full Course: 4563m, 16 corners, 17s pit delta, rain=True
- Daytona Road Course: 5729m
- Deep Forest Reverse: notes populated
- All layouts have valid `TrackModellingStatus` enum values
- Missing file → failure result
- Invalid YAML → failure result
- Missing schema_name → error reported
- Missing calibration cars → error reported
- Empty tracks → error reported
- Unknown modelling_status → preserved in `unknown_modelling_statuses`
- Duplicate layout_id → detected in `duplicate_layout_ids`
- Root not a dict → failure result
- Valid custom seed → success
- 41 locations returned, all have IDs and display names
- All locations have at least one layout
- Flat layout list is 121 items, all `TrackLayoutSeed`
- All layouts have `track_location_id` populated
- Resolve known layout returns correct object
- Resolve unknown location → None
- Resolve unknown layout → None
- Search by display name (Fuji → 2 layouts)
- Search case-insensitive
- Search by location ID substring
- Empty query → empty list
- No-match query → empty list
- Search by alias (custom seed)
- Search "Reverse" returns only reverse layouts
- `build_seed_track_context_for_prompt` returns non-empty string
- Context contains track name and layout name
- Context contains seed data caveat for unmodelled layouts
- Context contains calibration car boundary note
- Unknown location → error string
- Unknown layout → error string
- Fuji Full Course context includes "4563"
- Context includes modelling_status
- Second `load_track_seed()` call returns same cached object
- `force_reload=True` returns different object with same metadata
- Custom path does not write to global cache
- Cache reset to None behaves correctly

**Tests Run:** 791 pass / 5 skip / 0 fail (796 collected)

---

### Group 17B — Track Modelling UI Foundation (2026-06-24)

**New module:** `ui/track_modelling_vm.py` — pure-Python view model, no PyQt6 dependency.

**Modified:** `ui/dashboard.py` — tab 12 "Track Modelling" added; `_build_track_modelling_tab()`, `_tm_on_tab_shown()`, all `_tm_*` slots and widgets.

**View model functions tested:**
- `format_layout_facts(layout, loc)` — 27-row list; None → UNKNOWN_VALUE; bools → Yes/No/Unknown; units appended (m, s, %)
- `format_readiness(layout)` — seed_only flag, calibration readiness, AI readiness, missing steps count + drill-down rows
- `format_calibration_car(car)` — 509 BHP, 1243 kg, RH, Gr.3, MR; PP (stock) present only when set
- `get_seed_warning_text(layout)` — SEED DATA ONLY for not_modelled/seed_only; PARTIAL TELEMETRY for sampled/path_built; empty for segment_detected+; "No layout selected" for None
- `is_seed_only(layout)` — True for not_modelled, seed_only; False for sampled+; True for None
- `build_location_display_items(seed_result)` — 41 items, sorted alphabetically, correct IDs
- `build_layout_display_items(seed_result, loc_id)` — Fuji=2, Spa=2+, empty for unknown; failed seed → []
- `get_selected_location(seed_result, loc_id)` — resolves known; None for unknown/empty
- `get_selected_layout(seed_result, loc_id, lay_id)` — resolves Fuji full (4563m); None for unknown
- `build_prompt_preview(seed_result, loc_id, lay_id)` — placeholder for empty ids; Fuji content >100 chars; includes caveat; error text for failed seed
- `describe_seed_load_status(seed_result)` — version, 41 locations, 121 layouts; FAILED for errors; warning count
- `CALIBRATION_CAR_BOUNDARY_NOTE` — non-empty, mentions Porsche, mentions independence
- `SEED_WARNING_TEXT` — non-empty, mentions SEED, mentions calibration

**Tests Run:** 892 pass / 5 skip / 0 fail (897 collected)

---

### Group 17C — Calibration Lap Capture and Reference Path Builder (2026-06-24)

**New module:** `data/track_calibration.py` — pure Python, no PyQt6 dependency.

**Data models:**
- `TelemetrySample` — one GT7 telemetry snapshot with `from_frame()` duck-typed factory; `steering=None` (not in GT7); `is_off_track` from `road_plane_y < 0.5 AND speed > 20 kph`; `is_in_pit_lane=None`
- `LapQualityResult`, `CalibrationLap`, `CalibrationSession`, `ReferencePathPoint`, `ReferencePath`, `CalibrationBuildResult`
- `CalibrationLapQuality` enum: `USABLE`, `LOW_CONFIDENCE`, `REJECTED`
- `CalibrationSource` enum: `GT7_TELEMETRY_LIVE`, `IMPORTED_JSON`, `SYNTHETIC_TEST`

**Quality rejection rules:** too few samples (<50), all-zero xyz, coordinate jump >100 m, pit lane >10%, off-track >30%, duration outlier (>2×/<0.5× session median), path length outlier

**Distance/progress helpers:** `point_distance_3d`, `estimate_path_length`, `detect_coordinate_jumps`, `cumulative_distances`, `normalize_to_lap_progress`, `resample_to_buckets`

**Reference path:** `build_reference_path(session)` — 200 buckets, averaged x/y/z/speed, cumulative distance, confidence from fill rate × lap count; requires ≥ 2 usable laps

**File I/O:** `export_reference_path_json`, `import_reference_path_json` (temp dir safe)

**UI:** Disabled placeholder buttons added to Track Modelling tab right panel (Start/Stop Calibration Session, Build Reference Path, status label). No live wiring.

**Test coverage:**
- `TelemetrySample` supports optional/missing channels
- `from_frame()` factory duck-typed; `steering` always None; `is_off_track` from road_plane_y heuristic
- `CalibrationSession` defaults: `porsche_911_rsr_991_2017`, empty laps, GT7_TELEMETRY_LIVE source
- Lap quality: rejects too few samples, all-zero xyz, coordinate jumps, excessive pit/off-track, duration/path outliers
- `point_distance_3d`, `estimate_path_length`, circle circumference accuracy
- Teleport/jump detection: threshold exclusive, multiple jumps
- `cumulative_distances` monotonically increasing, length = sample count
- `normalize_to_lap_progress` 0.0→1.0, monotonic, degenerates to zeros
- `resample_to_buckets` n_buckets count, all samples assigned, ordered progress
- `build_reference_path`: fails with no/1 lap, succeeds ≥2, correct IDs, confidence 0–1, distance monotonic, rejected laps excluded
- Export/import roundtrip preserves all fields; missing file raises; creates nested output dir
- `assess_session_laps` session-median outlier detection
- Regression: Group 17A/17B imports still clean; seed loads; constants valid

**Tests Run:** 994 pass / 5 skip / 0 fail (999 collected)

---

### Group 17D — Live Telemetry Calibration Session Wiring (2026-06-24)

**New module:** `data/track_calibration_runtime.py` — pure Python, no PyQt6 dependency.

**Adapter helpers (pure functions):**
- `can_capture_calibration_sample(packet)` — guards intake; returns False for paused/loading/off-track or exception
- `infer_lap_number(packet, fallback)` — `laps_completed + 1` when ≥ 0; fallback when -1 (practice mode)
- `packet_to_calibration_sample(packet, lap_number)` — duck-typed GT7Packet → `TelemetrySample`; `steering=None` (not in GT7 protocol); `is_in_pit_lane=None`; `is_off_track` from `road_plane_y < 0.5 AND speed > 20 kph`; returns None on invalid/exception

**State machine:** `CalibrationCaptureState` enum: `INACTIVE`, `RECORDING`, `STOPPED`, `BUILT`, `ERROR`

**Controller:** `TrackCalibrationCaptureController`
- `start_session(track_location_id, layout_id, calibration_car_id=PRIMARY)` — fails with ERROR state if IDs blank
- `add_sample_from_packet(packet)` — RECORDING only; infers lap number; closes current lap on boundary; groups into `CalibrationLap` objects
- `stop_session()` — flushes in-progress lap; transitions to STOPPED
- `evaluate_laps()` — delegates to `assess_session_laps()`
- `build_reference_path()` — delegates to `build_reference_path()`; transitions to BUILT on success
- `save_reference_path(output_dir)` — delegates to `export_reference_path_json()`
- `get_status_summary()` — dict with 15 fields for UI status labels
- Properties: `can_start`, `can_stop`, `can_build`, `can_save`, `is_recording`

**`ui/dashboard.py` changes:**
- `SignalBridge.calibration_packet = pyqtSignal(object)` — cross-thread ~10 Hz packet delivery
- Import `TrackCalibrationCaptureController`
- Calibration group rebuilt with 4 active buttons (Start/Stop/Build/Save) and 5 status labels
- `self._tm_controller = TrackCalibrationCaptureController()` stored on window
- `_tm_on_layout_changed()` and `_tm_clear_detail_panels()` call `_tm_update_cal_buttons()`
- New slots: `_tm_on_calibration_packet`, `_tm_start_session`, `_tm_stop_session`, `_tm_build_path`, `_tm_save_path`, `_tm_update_cal_buttons`, `_tm_update_cal_status`
- `_connect_signals()` wires all 5 new connections

**`main.py` changes:**
- `_cal_pkt_counter = [0]` closure variable
- Every 6th packet in `on_packet()`: `bridge.calibration_packet.emit(packet)` — ~10 Hz subsampling

**Test coverage (81 tests, 10 test classes):**
- `TestCanCaptureSample` — valid, not-on-track, paused, loading, missing/exception attrs
- `TestInferLapNumber` — 0/1/5/negative/missing/exception cases; fallback propagation
- `TestPacketToCalibrationSample` — field mapping, steering=None, pit=None, off-track heuristic, threshold boundary, paused/invalid/malformed → None
- `TestCalibrationCaptureState` — all 5 enum values
- `TestControllerStart` — inactive state, blank IDs fail, valid IDs succeed, Porsche default, custom car, reset on restart
- `TestControllerSampling` — captures while recording; ignores when inactive/stopped/paused/off-track
- `TestControllerLapGrouping` — samples grouped by lap number, boundary detection, multi-lap, flush on stop, lap time from timestamps, practice mode fallback
- `TestControllerStop` — state transition, double-stop fails, can_build guard
- `TestControllerBuild` — fails while recording/no session/no laps/1 lap; succeeds with 2 good laps; state=BUILT; can_save; rebuild ok
- `TestControllerSave` — None before build, temp dir roundtrip, saved path in summary
- `TestControllerStatusSummary` — 15 required keys; state values at each lifecycle stage
- `TestButtonStateProperties` — all can_start/can_stop/can_build/can_save transitions
- `TestControllerEvaluateLaps` — empty without session; returns per-lap results
- `TestRegressionImports` — Groups 17A/17B/17C/17D all importable

**Tests Run:** 1075 pass / 5 skip / 0 fail (1080 collected)

---

### Group 17E — Automatic Track Segment Detection (2026-06-24)

**New module:** `data/track_segment_detection.py` — pure Python, no PyQt6 dependency.

**Enums:**
- `TrackSegmentType` (12 values): `start_finish`, `straight`, `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone`, `gear_zone`, `limiter_zone`, `fuel_saving_candidate`, `kerb_or_bump_candidate`, `unknown`
- `TrackSegmentDirection`: `left`, `right`, `unknown`
- `TrackSegmentDetectionConfidence`: `high`, `medium`, `low`, `insufficient`

**Dataclasses:**
- `SegmentDetectionConfig` — 13 configurable thresholds (brake/throttle/curvature/RPM/kerb/fuel-save/straight)
- `DetectedTrackSegment` — per-segment output with `segment_id`, `segment_type`, `display_name`, progress bounds, `confidence`, `evidence`, `warnings`, `source_lap_count`, `turn_number`, optional `calibration_car_id` (set for car-specific segments)
- `SegmentDetectionResult` — full detection output with corner count, expected count, confidence, errors, warnings

**Private helpers (7):**
- `_smooth(values, window)` — centred rolling average
- `_compute_headings_xz(samples)` — heading from consecutive X/Z positions; zeros when no position variation
- `_angular_diff(a, b)` — normalised angular difference (-π, π]
- `_compute_curvature(headings, cum_dists)` — heading change rate per metre (rad/m); smoothed
- `_find_local_minima(values, min_drop)` — local minima where drop ≥ min_drop from preceding max
- `_find_local_maxima(values)` — local maxima
- `_has_position_variation(samples)` — True when total XZ movement > 1 m

**Per-lap detection:** `detect_segments_from_lap(lap, config, track_location_id, layout_id) → list[DetectedTrackSegment]`
- Computes lap_progress, smoothed speed, XZ headings, curvature
- Finds speed minima as apex candidates; walks back/forward for braking onset and exit
- Emits per-corner: `braking_zone` (0–80% of entry-to-apex), `corner_entry` (80–100%), `apex_zone` (±3% around apex), `corner_exit` (apex to 60% of exit), `traction_zone` (60–100% of exit)
- Fills inter-corner gaps with `straight` or `fuel_saving_candidate` (span ≥ 8% + avg throttle > 70%)
- All braking/traction zones tagged with `calibration_car_id = PRIMARY_CALIBRATION_CAR_ID`
- Single-lap confidence: LOW (speed-only) or MEDIUM (curvature evidence)

**Multi-lap detection:** `detect_track_segments(session, reference_path, layout_seed, config) → SegmentDetectionResult`
- Extracts USABLE laps only (REJECTED ignored)
- Per-lap corner detection, then `_cluster_apex_progress` groups by proximity (2.5% merge radius)
- Clusters in ≥ 2 laps → confirmed corners; < 2 laps → warning + excluded
- Confidence: HIGH (≥ 3 laps + curvature), MEDIUM (≥ 2 laps), LOW (1 lap), INSUFFICIENT (0)
- `layout_seed.corners_expected` used for count mismatch warning ONLY — no corners invented
- Auxiliary: gear zones (modal gear at apex ±3 samples), limiter zones (RPM ≥ 92% observed max), kerb candidates (Z-spike consistent across ≥ 2 laps), fuel-save candidates (inter-corner gaps ≥ 8%)

**Corner numbering:** `assign_corner_numbers(segments, expected_corner_count) → list[DetectedTrackSegment]`
- Sorts apex zones by `lap_progress_mid`, assigns T1/T2/T3…
- Mismatch warning on all apex segments when |detected − expected| > 2
- Never invents or removes corners to match expected count

**JSON I/O:**
- `export_segment_detection_json(result, output_dir, session_id) → Path` — schema `segment_detection_result_v1`
- `import_segment_detection_json(json_path) → SegmentDetectionResult` — raises `FileNotFoundError`, `ValueError`
- Filename: `<track_loc>__<layout>__segments__<session_id>.json`

**`ui/dashboard.py` changes:**
- Import: `from data.track_segment_detection import detect_track_segments as _detect_track_segments`
- "Detect Segments" button (5th button in Calibration group; enabled when `ctrl.can_save`)
- 3 status labels: `_tm_lbl_seg_summary`, `_tm_lbl_seg_expected`, `_tm_lbl_seg_status`
- `_tm_detect_segments()` method: fetches session from `ctrl._session`, fetches layout seed from UI state, calls `_detect_track_segments`, updates all labels; shows `QMessageBox.warning` on failure
- `_connect_signals()` wires `_tm_btn_detect_segs.clicked → _tm_detect_segments`
- `_tm_update_cal_buttons()` sets `_tm_btn_detect_segs.setEnabled(ctrl.can_save)`

**Car-specific vs track-geometry boundary:**
- `calibration_car_id` set on: `braking_zone`, `corner_entry`, `traction_zone`, `limiter_zone`, `fuel_saving_candidate`, `gear_zone`
- NOT set on: `apex_zone`, `straight`, `corner_exit`, `kerb_or_bump_candidate` (geometry candidates)
- All car-specific segments carry warning: "Car-specific — Porsche RSR, not universal"

**GT7 limitations documented:**
- `steering=None` in all GT7 packets → corner direction from XZ heading only
- No per-sample `is_in_pit_lane` → pit laps excluded by session-level quality assessment only
- `yaw_rate` (angvel_z) available as secondary curvature evidence (not primary)

**Test coverage (99 tests, 22 test classes):**
- `TestEnums` — 5 tests: all 12 segment types, direction, confidence, str-comparability
- `TestDataclasses` — 4 tests: config defaults/custom, DetectedTrackSegment, SegmentDetectionResult
- `TestSmooth` — 5 tests: empty, single, constant, length, spike reduction
- `TestHeadings` — 4 tests: straight X, constant position, single sample, empty
- `TestCurvature` — 2 tests: straight → zero, empty
- `TestLocalMinima` — 5 tests: finds minimum, too-small drop, empty, two-long, multiple minima
- `TestStraightDetection` — 4 tests: straight produces straight/fuel-save, no apex, no braking, spans most of lap
- `TestBrakingZoneDetection` — 4 tests: detected, car_id set, car warning, comes before apex
- `TestApexZoneDetection` — 4 tests: detected, speed evidence, middle range, mid equals midpoint
- `TestCornerExitDetection` — 3 tests: detected, after apex, has evidence
- `TestTractionZoneDetection` — 3 tests: detected, car_id set, after apex
- `TestGearZoneDetection` — 2 tests: detected in corner, has car_id
- `TestLimiterZoneDetection` — 4 tests: detected when high RPM, car_id, RPM evidence, covers only high-RPM samples
- `TestFuelSavingCandidateDetection` — 4 tests: long straight is candidate, low throttle not candidate, car_id, car warning
- `TestKerbCandidateDetection` — 3 tests: detected across 2 laps, single lap not reported, Z-spike evidence
- `TestCornerNumbering` — 4 tests: T1/T2/T3 assigned, progress order, display name, non-apex unchanged
- `TestCornerCountMismatch` — 3 tests: mismatch produces warning, warning on apex segments, small mismatch no warning
- `TestNoInventedCorners` — 2 tests: count not inflated to match expected, apex count equals detected_corner_count
- `TestMissingPositionData` — 3 tests: zero-position adds warning, does not crash, direction warning on segments
- `TestRejectedLapsIgnored` — 3 tests: all rejected fails, rejected not in source count, mixed session still detects
- `TestEmptyMalformedSessions` — 4 tests: empty fails safely, no-samples graceful, single-sample graceful, too-few returns empty list
- `TestJsonRoundtrip` — 9 tests: creates file, filename contains IDs, preserves success/segments/corner-count/types/turn-numbers, missing file raises, wrong schema raises
- `TestMultiLapConfidence` — 5 tests: 2-lap ≥ medium, confirmed corners source_count ≥ 2, success=True, has segments, track location propagated
- `TestDetectFromLap` — 4 tests: returns list, valid progress range, sorted by progress, single-lap ≤ MEDIUM
- `TestRegressionImports` — 6 tests: 17A–17E all importable, all segment types have string values

**Tests Run:** 1174 pass / 5 skip / 0 fail (1179 collected)

---

### Group 17F — Segment Review and Track Model Approval (2026-06-24)

**New module:** `data/track_segment_review.py` (pure Python, no PyQt6)

**Enums:**
- `SegmentReviewStatus` (8 values): `unreviewed`, `confirmed`, `renamed`, `split_required`, `merge_required`, `rejected`, `needs_more_laps`, `engineer_validated`
- `SegmentReviewAction` (7 values): `confirm`, `rename`, `reject`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `promote_engineer_validated`

**Dataclasses:**
- `ReviewedTrackSegment` — original detection fields preserved + review state (`review_status`, `reviewed_display_name`, `review_notes`, `reviewed_at`, `last_action`); `display_name` property returns override or original; `is_reviewed` property
- `TrackModelReviewResult` — detection metadata + `list[ReviewedTrackSegment]`; `detection_warnings` always preserved; `last_reviewed_at` updated on every action

**Action functions (7 — all mutate in place, return review):**
- `confirm_segment(review, segment_id, notes="")` → CONFIRMED + reviewed_at + last_action
- `rename_segment(review, segment_id, new_name, notes="")` → RENAMED + reviewed_display_name; blank name ignored
- `reject_segment(review, segment_id, notes="")` → REJECTED
- `mark_needs_more_laps(review, segment_id, notes="")` → NEEDS_MORE_LAPS
- `mark_split_required(review, segment_id, notes="")` → SPLIT_REQUIRED
- `mark_merge_required(review, segment_id, notes="")` → MERGE_REQUIRED
- `promote_engineer_validated(review, segment_id, notes="")` → ENGINEER_VALIDATED (CONFIRMED only; UNREVIEWED ignored)

**Aggregate helpers:**
- `review_completion_pct(review) → float` — 0–100%; empty = 100%
- `is_ai_ready(review) → (bool, list[str])` — 5-blocker rule set:
  1. Segments must exist
  2. All apex_zone segments reviewed (not UNREVIEWED)
  3. No NEEDS_MORE_LAPS segments
  4. No SPLIT_REQUIRED / MERGE_REQUIRED segments
  5. Required types detected: straight, braking_zone, apex_zone, corner_exit

**JSON I/O:**
- `export_review_json(review, output_dir, session_id) → Path` — schema `track_model_review_result_v1`
- `import_review_json(json_path) → TrackModelReviewResult` — raises `FileNotFoundError`, `ValueError`
- Filename: `<loc>__<layout>__reviewed_segments__<session_id>.json`

**`ui/track_modelling_vm.py` additions:**
- `format_segment_row(seg) → dict` — display values for table row (8 keys)
- `format_review_summary(review) → dict` — approval panel display (8 keys)
- `get_review_button_states(review, selected_segment_id) → dict` — 7 button enabled states

**`ui/dashboard.py` changes:**
- Import block: `track_segment_review` action functions + vm helpers
- `_tm_detection_result`, `_tm_review_result`, `_tm_selected_segment_id` instance variables
- `_tm_detect_segments()` auto-creates `TrackModelReviewResult` and populates table on success
- "Segment Review" QGroupBox: 8-col read-only QTableWidget, 6 action buttons (colour-coded), "Save Reviewed Model" button + save-path label
- "Review Approval" QGroupBox: 7 stat labels (detected/reviewed/confirmed/rejected/needs-laps/completion%/ai-ready/blockers)
- 11 new methods: `_tm_refresh_seg_table`, `_tm_on_seg_selected`, `_tm_refresh_review_buttons`, `_tm_refresh_approval_panel`, `_tm_review_confirm/rename/reject/needs_laps/split/merge/save`
- `_connect_signals()`: 8 new connections

**Deferred:**
- Graphical split/merge segment editing (currently review flags only)
- Integration into Setup Builder / Strategy Builder / Practice Analysis / Live prompts (Group 17G+)
- `modelling_status` promotion after review save

**Test coverage (122 tests, 14 test classes):**
- `TestSegmentReviewStatus` — 5 tests: 8 values, str comparability, isinstance str
- `TestSegmentReviewAction` — 4 tests: 7 values, str comparability, all actions
- `TestReviewedTrackSegment` — 7 tests: defaults, is_reviewed, display_name property
- `TestTrackModelReviewResult` — 4 tests: construction, defaults, created_at
- `TestCreateReviewFromDetection` — 9 tests: all-unreviewed, counts, field preservation, direction
- `TestConfirmSegment` — 7 tests: status, reviewed_at, unknown id, last_action, notes, return
- `TestRenameSegment` — 7 tests: status, name change, display_name, unknown id, blank name, reviewed_at
- `TestRejectSegment` — 4 tests: status, reviewed_at, unknown id, last_action
- `TestMarkNeedsMoreLaps` — 4 tests: status, reviewed_at, unknown id, last_action
- `TestMarkSplitRequired` — 3 tests: status, unknown id, last_action
- `TestMarkMergeRequired` — 3 tests: status, unknown id, last_action
- `TestPromoteEngineerValidated` — 4 tests: CONFIRMED→VALIDATED, UNREVIEWED blocked, unknown id, last_action
- `TestReviewCompletionPct` — 5 tests: 0%, partial%, 100%, empty=100%, mixed statuses
- `TestIsAIReady` — 10 tests: all blocker branches, true when all confirmed, ready with rejected apexes
- `TestAIReadyMissingTypes` — 4 tests: missing straight/braking/exit blocks, all types present no blocker
- `TestExportImportJSON` — 10 tests: file created, filename, schema, roundtrip fields, missing file raises, wrong schema raises
- `TestViewModelSegmentRow` — 7 tests: keys, status labels, turn number, progress, warnings
- `TestViewModelReviewSummary` — 7 tests: None dashes, counts, completion%, ai_ready, blockers
- `TestReviewButtonStates` — 7 tests: None all-false, no-selection, with-selection, save enabled/disabled
- `TestDetectionWarningsPreserved` — 3 tests: detection warnings visible, car warnings on segments, confirmation doesn't clear
- `TestRegressionImports` — 8 tests: 17A–17F importable, status/action values are strings

**Tests Run:** 1296 pass / 5 skip / 0 fail (1301 collected)

---

### Group 17G — Approved Track Model Resolver and Modelling Status Promotion (2026-06-24)

**New module:** `data/track_model_resolver.py` (pure Python, no PyQt6)

**Enums:**
- `TrackModelSourceType` (6 values): `seed_only`, `detected_unreviewed`, `reviewed_model`, `ai_ready_reviewed_model`, `engineer_validated_model`, `missing`
- `TrackModelResolutionStatus` (6 values): `found`, `found_with_warnings`, `seed_only_fallback`, `not_ai_ready`, `missing`, `error`

**Dataclasses:**
- `ResolvedTrackModel`: track_location_id, layout_id, source_type, modelling_status, ai_ready, review_completion_pct, segment/confirmed/rejected/needs_more_laps/warning counts, blockers, warnings, source_path, reviewed_model, seed_layout
- `TrackModelResolverResult`: resolution_status, resolved_model, all_candidate_paths, errors, warnings

**Discovery functions:**
- `list_reviewed_track_models(base_dir)` → all `*__reviewed_segments__*.json`, newest first
- `find_reviewed_models_for_layout(loc, layout, base_dir)` → filtered by prefix, newest first
- `load_reviewed_track_model(path)` → delegates to `import_review_json`
- `resolve_best_track_model(loc, layout, base_dir)` → best model with maturity priority

**Resolution priority logic:**
1. engineer_validated_model (any ENGINEER_VALIDATED segment) → rank 5
2. ai_ready_reviewed_model (is_ai_ready = True) → rank 4
3. reviewed_model (file exists, not AI-ready) → rank 3
4. seed_only (no reviewed file; seed entry found) → rank 1
5. missing (no seed entry either) → rank 0

When maturity equal: prefer newest by created_at, filename as tie-breaker.
Malformed files silently skipped; errors recorded in `TrackModelResolverResult.errors`.

**Schema extension (`data/track_segment_review.py`):**
- `TrackModelReviewResult.modelling_status: Optional[str] = None` (new optional field)
- `export_review_json()` computes and writes `modelling_status` (engineer_grade / user_reviewed / segment_detected)
- `import_review_json()` reads `modelling_status`; old files get `None` (backward-compatible)

**Prompt context builder (not wired to AI yet):**
- `build_resolved_track_context_for_prompt(loc, layout, base_dir) → str`
  - Missing → "MISSING" message
  - Seed-only → seed context + "No reviewed track model" warning
  - Reviewed → source, modelling status, AI-ready, segment summary, confirmed list, boundary note, blockers
  - Always includes Porsche RSR boundary note

**`ui/track_modelling_vm.py` addition:**
- `format_resolver_summary(resolver_result) → dict` — 8 keys: source_type (human label), modelling_status, ai_ready, blockers, model_path, warnings, resolution_status, candidate_count

**`ui/dashboard.py` changes:**
- Import: `resolve_best_track_model as _resolve_track_model`, `format_resolver_summary as _format_resolver_summary`
- `_tm_resolver_result` instance variable
- "Resolver Status" QGroupBox: 5 labels (source, status, AI-ready, candidates, file) + blockers + warnings
- `_tm_review_save()` calls `_tm_refresh_resolver()` after successful save
- `_tm_on_layout_changed()` calls `_tm_refresh_resolver()` to show pre-existing models
- `_tm_refresh_resolver()` — resolves model, formats summary, updates labels (AI-ready colour-coded)

**Deferred:**
- Integration into Setup Builder, Strategy Builder, Practice Analysis, Live Race Engineer (Group 17H+)
- Graphical split/merge editing
- Auto-detection of track/layout from telemetry

**Test coverage (68 tests, 13 test classes):**
- `TestListReviewedTrackModels` — 5 tests: empty dir, infix filter, non-json, sorted newest-first, multiple tracks
- `TestFindReviewedModelsForLayout` — 4 tests: matching layout, missing track, multiple versions, empty dir
- `TestLoadReviewedTrackModel` — 3 tests: valid file, missing file raises, bad schema raises
- `TestResolverSeedOnlyFallback` — 4 tests: seed fallback, ai_ready false, has warning, missing for unknown track
- `TestResolverNotAIReady` — 4 tests: resolution status, source type, blockers preserved, ai_ready false
- `TestResolverAIReady` — 5 tests: resolution status, source type, ai_ready flag, no blockers, modelling_status
- `TestResolverPriority` — 3 tests: ai_ready > not-ai-ready, engineer_validated > ai_ready, newest when equal
- `TestResolverMalformedFiles` — 3 tests: skip malformed + continue, all malformed falls to seed, wrong schema error
- `TestCandidatePathsTracked` — 1 test: all candidate paths in result
- `TestModellingStatusInJSON` — 5 tests: ai-ready=user_reviewed, not-ready=segment_detected, validated=engineer_grade, import reads it, old file returns None
- `TestBuildResolvedTrackContextForPrompt` — 8 tests: all branches (seed/missing/ai-ready/not-ready/engineer-validated)
- `TestViewModelResolverSummary` — 7 tests: None dashes, keys, ai_ready yes/no, source label, blockers, path, count
- `TestEngineerValidatedModel` — 3 tests: source type, modelling_status, resolution FOUND
- `TestWarningsPreserved` — 3 tests: detection warnings in resolved, segment warnings, warning_count
- `TestRegressionImports` — 9 tests: 17A–17G importable, enum string values

**Tests Run:** 1364 pass / 5 skip / 0 fail (1369 collected)

---

### Group 17I — Telemetry Issue to Segment Enrichment (2026-06-24)

**New module:** `data/track_issue_enrichment.py`

**Test file:** `tests/test_group17i_track_issue_enrichment.py` — 76 tests, 15 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 6 | Enum values, field defaults |
| TestExactSegmentIdMatch | 2 | Exact segment_id match; fallthrough when ID not in model |
| TestLapProgressMatch | 3 | Range match; outside-range nearest fallback; boundary values |
| TestDistanceAlongLapMatch | 1 | distance_along_lap_m → reference path → segment |
| TestXYZNearestMatch | 2 | XYZ nearest via reference path; no reference path → UNRESOLVED |
| TestUnresolvedFallback | 3 | Warning content; unresolved_count tracked; no evidence → UNRESOLVED |
| TestSeedOnlyConfidence | 2 | Seed-only → LOW/UNRESOLVED; missing → UNRESOLVED |
| TestRejectedSegmentHandling | 3 | REJECTED → UNRESOLVED; NEEDS_MORE_LAPS → LOW; UNREVIEWED capped |
| TestImplicationMappings | 11 | brake_lock, wheelspin, limiter, poor_exit, wrong_gear, oversteer, understeer |
| TestPromptSummary | 7 | Segment name/type/count; no invented names for unresolved; grouping |
| TestIssuesFromLapStats | 9 | All five position list types; XYZ populated; lap_num; empty |
| TestIssuesFromCornerIssues | 8 | Type mapping; corner_id decode; phase map; empty |
| TestDrivingAdvisorEnrichment | 6 | Returns string; empty without IDs; no raise; coaching/setup prompts |
| TestFullPipeline | 3 | End-to-end XYZ→segment→prompt; resolver exception; multi-lap |
| TestRegressionImports | 10 | All 17A–17H modules importable; decode_corner_id edge cases |

**Full suite result: 1574 pass / 5 skip / 0 fail (after 17J added)**

---

### Group 17J — Live Current Segment Resolver (2026-06-24)

**New module:** `data/live_segment_resolver.py`

**Test file:** `tests/test_group17j_live_segment_resolver.py` — 78 tests, 17 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 7 | Enum values, field defaults, dataclass construction |
| TestExactSegmentIdMatch | 3 | Exact match; HIGH confidence for ai_ready; unknown ID falls through |
| TestLapProgressMatch | 5 | Range match; start/end boundary; outside bounds → nearest; nearest → lower confidence |
| TestDistanceAlongLapMatch | 1 | distance_along_lap_m → reference path → lap_progress → segment |
| TestXYZNearestMatch | 2 | XYZ via reference path; no reference path → no_position_data |
| TestNoReviewedModel | 3 | seed_only → no_reviewed_model; missing → no_reviewed_model; warning present |
| TestNoPositionData | 2 | None position; empty position (all None fields) |
| TestNotAiReadyModel | 2 | Reviewed-not-AI-ready allows match with warning; confidence ≤ MEDIUM |
| TestPreviousNextSegment | 5 | Next present; previous present; start/finish wraparound; three-segment; single segment |
| TestRejectedSegmentExclusion | 2 | Rejected excluded from match; all rejected → no_segment_bounds |
| TestSegmentConfidenceDegradation | 3 | needs_more_laps → degraded + warning; unreviewed excluded by default; unreviewed included when config set |
| TestFormatLiveSegmentForEngineer | 8 | Name/confidence/next in text; nearest fallback note; no_reviewed_model/no_position_data/error safe text; no invented names |
| TestPacketToLivePosition | 9 | Valid packet; paused/loading/off-track/zero-xyz → None; lap_progress not set; distance not set; missing attrs; exception |
| TestGetLiveSegmentContextForPrompt | 4 | No model → ""; matched → prompt block; prompt includes segment type; no position → no invented names; never raises |
| TestDrivingAdvisorLiveSegment | 7 | No position → ""; no IDs → ""; returns string; does not raise; coaching/setup prompts include live segment |
| TestResolverErrorHandling | 3 | Exception → error status; malformed segments safe; all rejected → no_segment_bounds |
| TestRegressionImports | 11 | All 17A–17I importable; DrivingAdvisor has method; XZ-only distance verified; speed_kph populated; text length reasonable |

**Full suite result: 1574 pass / 5 skip / 0 fail**

---

### Group 17K — Segment-Aware Live Coaching Rules (2026-06-24)

**New module:** `data/live_segment_coaching.py`

**Test file:** `tests/test_group17k_live_segment_coaching.py` — 78 tests, 19 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 6 | Enum values (all 13 cue types, 4 priorities, 12 suppression reasons), dataclass defaults, config defaults |
| TestNoSegmentSuppression | 7 | no_reviewed_model/no_position_data/error → NO_SEGMENT; seed_only → SEED_ONLY; no issues → NO_MATCHING_RULE; cue=None when suppressed; garbage input never raises |
| TestLowConfidenceSuppression | 3 | unknown → LOW_CONFIDENCE; low by default → LOW_CONFIDENCE; low allowed when config disabled |
| TestBrakeLockRules | 6 | brake_lock+braking_zone → BRAKING_STABILITY HIGH; corner_entry → MEDIUM; cue text includes segment name; basis_issue_type set; repetition count |
| TestWheelspinRules | 2 | wheelspin+corner_exit → THROTTLE_PICKUP; wheelspin+apex_zone → THROTTLE_PICKUP |
| TestRotationRules | 2 | oversteer+apex → ROTATION; understeer+corner_entry → ROTATION |
| TestExitDriveRules | 2 | poor_exit_drive+corner_exit → EXIT_DRIVE; poor_exit_drive+traction_zone → EXIT_DRIVE |
| TestGearChoiceRules | 2 | wrong_gear+apex_zone → GEAR_CHOICE; wrong_gear+corner_exit → GEAR_CHOICE |
| TestLimiterRules | 2 | limiter_hit+straight → SHORT_SHIFT; limiter_hit+other → LIMITER_WARNING |
| TestConfigGatedRules | 3 | fuel_save suppressed by default; fires when enable_fuel_save_cues=True; tyre_management suppressed by default |
| TestSegmentQualitySuppression | 3 | rejected warning → REJECTED_SEGMENT; needs_more_laps warning → NEEDS_MORE_LAPS; allowed when config disabled |
| TestNoInventedNames | 4 | No {segment} literal in output; no invented corner names when display_name empty; suppressed format → ""; format with unresolved → "" |
| TestPriorityBehaviour | 3 | High repetition maintains base priority; medium confidence base priority; multi-issue → highest priority wins |
| TestCooldownBehaviour | 4 | Same cue+segment within 3 laps → COOLDOWN; same cue after N laps → fires; max_cues_per_lap → MAX_CUES_REACHED; empty previous_cues does not suppress |
| TestMinRepetitionsGate | 3 | Single lap suppressed (default min=2); 2 laps fires; config min=1 allows single |
| TestFormatForPrompt | 5 | Cue text in block; header present; basis line present; suppressed → ""; never raises |
| TestDebugMetadata | 3 | Suppressed → cue_included=False + reason; cue fired → cue_included=True + type/priority/segment; never raises |
| TestDrivingAdvisorIntegration | 6 | No position → ""; no IDs → ""; returns string; never raises; coaching prompt includes coaching block; coaching prompt omits block when no_call |
| TestRegressionImports | 12 | All modules importable; DrivingAdvisor has method; format_cue_text insert/remove; downgrade_priority low→low/high→medium; all covered issue types have fallback rule; garbage input safe; 17A+17G importable |

**Full suite result: 1652 pass / 5 skip / 0 fail**

---

### Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping (2026-06-24)

**New module:** `data/lap_distance_mapper.py` (pure Python, no PyQt6)

**Enums:** `LapDistanceMappingStatus` (mapped / mapped_with_wrap / no_distance_data / no_track_length / invalid_offset / error), `LapDistanceMappingConfidence` (high / medium / low / unknown)

**Dataclasses:** `LapStartOffsetCalibration` (track_location_id, layout_id, calibration_source, track_length_m, gt7_start_distance_m, model_start_distance_m, offset_m, confidence, sample_count, source_session_id, created_at, warnings), `LapDistanceMappingResult` (status, distance_along_lap_m, lap_progress, wrapped, confidence, warnings, offset_m, track_length_m), `LapDistanceMapperConfig` (min_track_length_m, clamp_progress)

**Core functions:**
- `normalise_distance(distance_m, track_length_m) -> float` — modulo wrap to [0, track_length); handles negatives; raises on ≤ 0 length
- `calculate_lap_start_offset(gt7_start, model_start, track_length) -> float` — normalised offset
- `map_road_distance_to_lap_distance(road_distance_m, offset_m, track_length_m, config) -> LapDistanceMappingResult` — full error-status returns
- `map_road_distance_to_lap_progress(road_distance_m, offset_m, track_length_m, config) -> LapDistanceMappingResult` — 0.0–1.0 clamped

**Calibration helpers:** `create_offset_zero()`, `create_offset_from_reference_path()`, `load_offset_calibration_for_track()`

**JSON persistence:** `export_offset_calibration_json(calibration, output_dir)` → `<loc>__<lay>__lap_offset.json`; `import_offset_calibration_json(path)`

**`data/live_segment_resolver.py` updates (Group 17L):**
- `LivePosition` gains `road_distance_m: Optional[float] = None` (raw GT7 field)
- `packet_to_live_position()` now populates `road_distance_m` from packet
- `enrich_position_with_road_distance(position, offset_calibration) -> LivePosition` added
- `resolve_live_segment()` gains optional `offset_calibration` parameter; Priority 3 now maps road_distance via offset before caller-supplied distance
- Matching priority updated to: segment_id → lap_progress → road_distance+offset → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved

**69 tests** in `tests/test_group17l_lap_distance_mapper.py`

| Test group | Count | What it covers |
|---|---|---|
| normalise_distance | 8 | normal, over-length, exact wrap, negative, zero, zero track raises, negative track raises |
| calculate_lap_start_offset | 5 | zero/nonzero gt7/model starts, equal → 0, raises on zero |
| map_road_distance_to_lap_distance | 10 | success, wrap, no_distance_data, no_track_length, below_min, invalid_offset, wrap warning text |
| map_road_distance_to_lap_progress | 8 | basic, start, near-end clamping, wrap, always [0,1], no data, no track length, result fields |
| Calibration helpers | 8 | create_offset_zero, from_reference_path (basic/nonzero gt7/none/empty/zero-length/session_id), confidence |
| JSON persistence | 4 | export creates file, import reads, round-trip all fields, missing file raises |
| packet_to_live_position | 4 | road_distance_m populated, None when missing, distance_along_lap_m still None, paused=None |
| enrich_position_with_road_distance | 5 | enriches, no-op (already set), no-op (no cal), no-op (no road_dist), returns new instance |
| resolve_live_segment integration | 4 | uses road_distance, prefers lap_progress, safe without calibration, wrap warnings propagated |
| load_offset_calibration_for_track | 2 | returns None when not found, loads when found |
| result field checks | 3 | stores offset/track_length, status is str-enum, no_distance_data str value |
| calibration fields | 1 | all fields preserved |
| config + edge cases | 4 | default config, clamp disabled, multiple wraps, session_id |
| regression | 3 | 17A–17K imports, road_distance_m field exists, optional field |

**Full suite result after Group 17L: 1721 pass / 5 skip / 0 fail**

---

### Group 17M — Runtime UAT and Calibration Workflow Hardening (2026-06-24)

**New module:** `data/track_modelling_runtime_check.py`

**New file:** `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist

**`ui/track_modelling_vm.py` additions:**
- `_WORKFLOW_ERROR_MESSAGES` — 11-key dict mapping error keys to human-readable strings
- `get_workflow_error_message(error_key)` — safe lookup with unknown-key fallback
- `get_calibration_button_states(ctrl_state, has_track, has_completed_laps, has_ref_path, has_review_model, selected_segment_id=None, has_track_length=False)` — returns 15-key bool dict for all workflow buttons
- `format_calibration_status_extended(status_summary, last_packet_age_s=None)` — returns dict with: state_text, recording_indicator, packet_age, sample_count, lap_count, path_info, saved_path
- `format_lap_offset_status(offset_calibration=None, track_length_m=None)` — returns dict with: status, offset_m, confidence, track_length, source, warnings, provisional_note
- `format_live_resolver_status_summary(loc_id, lay_id, resolver_result=None, offset_calibration=None, live_position=None, live_segment_result=None)` — returns newline-separated status string

**`data/track_modelling_runtime_check.py` (new):**
- `RuntimeCheckResult` dataclass — 14 fields covering track/resolver/offset/live status; `summary_text()` method
- `run_track_modelling_runtime_check()` — never raises; duck-typed arguments; aggregates full pipeline status

**`data/lap_distance_mapper.py` change:**
- `create_offset_zero()` — default source changed from `"manual"` to `"zero_offset"`; added `ValueError` on non-positive track_length_m

**`ui/dashboard.py` additions:**
- `_tm_lbl_packet_age` — packet age label in calibration group (green/amber/red based on age)
- `_tm_last_packet_time` and `_tm_offset_calibration` instance variables
- Lap Offset Calibration QGroupBox — Create Zero Offset / Load Offset / Save Offset buttons; status/detail/warning labels; provisional note
- `_tm_update_packet_age_label()` — refreshes packet age label from wall-clock timestamp
- `_tm_get_track_length_m()` — derives track length from reference path or seed
- `_tm_update_offset_status()` — refreshes all offset calibration labels
- `_tm_create_zero_offset()` — creates provisional zero calibration; shows dialog on missing track length
- `_tm_load_offset()` — loads calibration from JSON; shows informational dialog when not found
- `_tm_save_offset()` — saves calibration to JSON; updates status label
- Signal connections for the three new offset buttons

**94 tests** in `tests/test_group17m_runtime_hardening.py`

| Test group | Count | What it covers |
|---|---|---|
| TestWorkflowErrorMessages | 4 | all 11 keys non-empty, unknown key safe, track mention, GT7 mention |
| TestCalibrationButtonStatesInactive | 5 | start with/without track, stop/build/review all disabled |
| TestCalibrationButtonStatesRecording | 3 | stop enabled, start/build disabled while recording |
| TestCalibrationButtonStatesStopped | 4 | build with/without laps, start enabled, stop disabled |
| TestCalibrationButtonStatesBuilt | 4 | save_path, detect_segments enabled/disabled |
| TestCalibrationButtonStatesReview | 4 | confirm with/without selection, save_review with/without model |
| TestCalibrationButtonStatesOffsetActions | 5 | create_zero with/without track/length, load_offset with/without track |
| TestFormatCalibrationStatusExtended | 11 | inactive/recording/stopped/built text, packet age ms/warn, sample count, recording indicator, saved path |
| TestFormatLapOffsetStatus | 10 | no-cal, offset display, provisional/validated, warnings, track_length |
| TestFormatLiveResolverStatusSummary | 12 | no track, track shown, resolver/offset/position/segment display |
| TestRuntimeCheckResult | 5 | summary_text no track, with track, warnings, errors, offset_m |
| TestRunTrackModellingRuntimeCheck | 17 | no track, with track, resolver source extraction, offset provisional/validated, live position, live segment, never-raises, bad object |
| TestZeroOffsetCalibrationCreation | 5 | valid, track_ids, confidence LOW, zero length raises, negative length raises |
| TestRegressionImports | 6 | all 17A–17M imports, existing vm functions unchanged |

**Full suite result after Group 17M: 1815 pass / 5 skip / 0 fail**

---

### Group 17M UAT Defect Remediation (2026-06-25)

**Defects addressed:**
- DEF-17M-UAT-001 — Lap count mismatch display (8 shown / 5 valid confusion)
- DEF-17M-UAT-002 — Detect Segments crash (`seed_result.layouts` AttributeError)
- DEF-17M-UAT-003 — Saved reference path not discoverable after restart

**New functions:**
- `ui/track_modelling_vm.py` — `format_lap_count_info(status_summary) -> dict[str, str]` (3 keys: captured_text, quality_text, explanation)
- `ui/track_modelling_vm.py` — `format_file_audit_status(audit) -> dict[str, str]` (4 keys: saved_text, detail_text, load_status, extras_text)
- `data/track_calibration.py` — `reference_path_filename(loc_id, lay_id) -> str`
- `data/track_calibration.py` — `TrackModelFileAudit` dataclass (13 fields, `summary_line()`, `ref_path_status_text()`)
- `data/track_calibration.py` — `audit_track_model_files(loc_id, lay_id, search_dir=None) -> TrackModelFileAudit` (never raises)

**Dashboard changes:**
- `_tm_update_cal_status()` — uses `format_lap_count_info()` for clear lap count display; tooltip shows partial segment explanation
- `_tm_detect_segments()` — split into outer error catcher + `_tm_detect_segments_safe()` inner; crash wrapped in try/except with QMessageBox
- `_tm_detect_segments_safe()` — fixed `seed_result.layouts` → `get_selected_layout()`; disk fallback when no active session
- `_tm_on_layout_changed()` — calls `_tm_audit_and_show_saved_files()` to populate UI from disk on restart
- `_tm_audit_and_show_saved_files()` — new method; reads audit, updates save-path label, build-info label, offset label, Detect Segments button enabled state

**New test file:** `tests/test_group17m_uat_defects.py` (49 tests)

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestFormatLapCountInfo | 11 | no laps, recording, stopped, built, gap explanation, singular, edge cases |
| TestSeedResultLayoutsAccess | 5 | layouts attr absence, get_selected_layout correct use, wrong loc/lay |
| TestDetectSegmentsNoCrash | 3 | empty session, None seed, real layout seed |
| TestReferencePathFilename | 2 | filename format, ID-based naming |
| TestAuditTrackModelFilesNotFound | 5 | all false, loc/lay stored, expected path, never raises |
| TestAuditTrackModelFilesFound | 8 | exists, load_ok, point count, confidence, laps, modified, wrong track, Daytona integration |
| TestAuditTrackModelFilesCorrupt | 2 | corrupt JSON, empty JSON |
| TestFormatFileAuditStatus | 6 | no file, load ok, load failed, reviewed extras, offset extras, no extras |
| TestTrackModelFileAuditSummaryLine | 5 | no loc/lay, not found, found+load ok, status text no file, with file |
| TestRoundTripSaveAndAudit | 2 | save→audit→load round trip, crash-restart simulation |

**Full suite result after Group 17M UAT Remediation: 1864 pass / 5 skip / 0 fail**

---

### Group 17N UAT Defect Remediation (2026-06-25)

**Defect fixed:** DEF-17N-UAT-004 — Detect Segments requires a live calibration session despite a saved reference path existing.

**Root cause:** `detect_track_segments()` requires raw `CalibrationLap` objects with per-sample `TelemetrySample` data. `save_reference_path()` only persisted the 200-point aggregated `ReferencePath` JSON; raw lap samples were discarded on every app restart.

**Files modified:**
- `data/track_calibration.py` — Added `calibration_laps_filename()`, `export_calibration_laps_json()`, `import_calibration_laps_json()`. Updated `TrackModelFileAudit` with `calibration_laps_exists`, `calibration_laps_usable_count`, `can_detect_segments` (property), `is_legacy_ref_path_only` (property). `audit_track_model_files()` now audits the laps file. `summary_line()` includes lap count.
- `data/track_calibration_runtime.py` — `save_reference_path()` now writes both the reference path JSON and the calibration laps JSON in one call.
- `ui/dashboard.py` — `_tm_detect_segments_safe()` rewritten with three-path logic: active session / load from disk / legacy format dialog. `_tm_audit_and_show_saved_files()` updated with `can_detect_segments`/`is_legacy_ref_path_only` button logic.
- `ui/track_modelling_vm.py` — `format_file_audit_status()` now includes laps count in `detail_text` and distinguishes "Detect Segments ready" vs legacy format message in `load_status`.

**New test file:** `tests/test_group17n_uat_defects.py` — 41 tests

| Test class | Count | What it proves |
|---|---|---|
| `TestCalibrationLapsFilename` | 2 | Filename format, distinct from ref path |
| `TestExportCalibrationLapsJson` | 8 | File creation, USABLE-only filtering, field preservation, metadata, empty list, multiple laps, dir creation |
| `TestImportCalibrationLapsJson` | 10 | Returns CalibrationSession, track/car IDs preserved, lap count, sample round-trip, quality, error raising, session_id, yaw_rate |
| `TestSaveReferencePathAlsoSavesLaps` | 3 | Controller.save_reference_path() writes both files; lap count matches |
| `TestAuditIncludesCalibrationLaps` | 8 | Laps file detected, usable count, no-file state, can_detect_segments, is_legacy_ref_path_only |
| `TestDetectSegmentsFromLoadedLaps` | 4 | Loaded session has USABLE laps; detect_track_segments does not raise; returns SegmentDetectionResult; empty session returns failure |
| `TestFormatFileAuditStatusWithLaps` | 3 | Laps present in detail_text, legacy message, no ref path |
| `TestDaytonaBehaviourWithExistingFile` | 1 | Pre-17N Daytona file detected as legacy (skipped if file absent) |
| `TestRoundTripSaveReloadDetect` | 2 | Full pipeline: save → restart → detect without live session; controller save_reference_path produces both files |

**Also fixed:** `tests/test_group17m_uat_defects.py::TestFormatFileAuditStatus::test_file_found_load_ok_saved_text` — updated to match 17N-aware `format_file_audit_status()` behaviour (ref path only → legacy; both files → ready). Added `test_file_found_legacy_no_laps_shows_preformat_message` for the legacy case.

**Full suite result after Group 17N UAT Remediation: 1906 pass / 5 skip / 0 fail**

---

### Group 17N UAT-005 Defect Remediation (2026-06-25)

**Defect fixed:** DEF-17N-UAT-005 — "No Usable Calibration Laps" message lacks actionable rejection diagnostics.

**Root causes:**
1. `CalibrationLap.quality` defaults to `REJECTED` and was never updated after `build_reference_path()` assessed the laps as USABLE. `detect_track_segments()` filters by `quality == USABLE` → finds none → generic "No USABLE calibration laps" error even after successful Build.
2. `_tm_build_path()` only showed `result.errors`, discarding per-lap rejection reasons in `result.warnings`.

**Files modified:**
- `data/track_calibration.py` — `build_reference_path()` now mutates `CalibrationLap.quality` and `quality_reasons` after assessment (runs on both success and failure paths). Added `diagnose_calibration_session(session) -> dict` (structured diagnostic snapshot, never raises).
- `data/track_segment_detection.py` — Added `assess_session_laps` to imports. Added `_build_no_usable_laps_errors(session) -> list[str]` helper that re-assesses quality and builds per-lap diagnostic error lines. `detect_track_segments()` calls this instead of the hardcoded generic message.
- `ui/track_modelling_vm.py` — Added `format_build_failure_diagnostics(result, session=None) -> str` (multi-line dialog text: primary error, lap counts, per-lap rejection reasons, car ID, context-specific recommended action). Added `_min_samples()` helper.
- `ui/dashboard.py` — Added `format_build_failure_diagnostics as _format_build_diag` to track_modelling_vm import. `_tm_build_path()` now calls `_format_build_diag(result, session)` instead of `"\n".join(result.errors)`.
- `tests/test_group17n_uat_defects.py` — Updated `TestDaytonaBehaviourWithExistingFile::test_daytona_ref_path_is_legacy_until_resaved` to handle the three-way state (no laps file / laps file with 0 usable / laps file with >0 usable).

**New test file:** `tests/test_group17n_uat005_defects.py` — 32 tests

| Test class | Count | What it proves |
|---|---|---|
| `TestDiagnoseCalibrationSession` | 9 | Empty, all-usable, all-rejected, mixed, off-track, per-lap detail, car id, sample count, never-raises |
| `TestBuildReferencePathMutatesLapQuality` | 4 | Usable laps marked USABLE, rejected marked REJECTED, quality_reasons populated, failed build still mutates |
| `TestDetectSegmentsNoUsableLapsDiagnostics` | 7 | Empty session, rejected with reasons, count in error, car id, off-track advice, UDP advice, successful-session-works |
| `TestFormatBuildFailureDiagnostics` | 10 | String returned, counts, primary error, warnings, car id, no-laps message, UDP/off-track/one-usable advice, never-raises |
| `TestIntegrationBuildFailThenBuildSucceed` | 2 | Add laps → build succeeds → detect works; warnings surface in dialog text |

**Full suite result after Group 17N UAT-005 Remediation: 1938 pass / 5 skip / 0 fail**

---

### Group 17O — Seeded 1m Track Map, Width Corridor, Map Matching, Visual Verification (2026-06-25)

**New test file:** `tests/test_group17o_track_station_map.py` — 76 tests

| Class | Count | Coverage |
|-------|-------|----------|
| `TestBuildTrackStationMap` | 9 | station count, IDs, confidence, corners_expected, empty raises, headings, curvature, spacing |
| `TestResamplePath` | 5 | straight path, spacing accuracy, single point, empty list, 3D y preservation |
| `TestFindNearestStation` | 4 | exact match, between stations, empty raises, off-track |
| `TestStationMAndProgress` | 3 | start, midpoint, progress bounded 0-100 |
| `TestLateralOffset` | 4 | centreline zero, left positive, right negative, magnitude |
| `TestEdgeDistances` | 3 | equal edges on centreline, left reduces near-left, non-negative |
| `TestMissingWidth` | 2 | zero width falls back to default, empty map returns UNKNOWN |
| `TestPitAndOutlapDetection` | 5 | low speed, far from track, on track, outlap before crossing, not outlap after |
| `TestDaytonaSeedednCorners` | 7 | count=12, T1-T12 IDs, ascending stations, placeholder confidence, corners_expected, no corners map, placeholders fill to expected |
| `TestTelemetryOverlaySeparation` | 4 | no braking event fields, geometry-only fields, corner phase enum, segment types excluded |
| `TestDrawingPrimitives` | 10 | draw data returned, centreline, edges match length, corner labels count, no dot without match, has_map, empty map, no PyQt import, valid bounds, status text |
| `TestCarDotPrimitive` | 5 | dot created, position near station, confidence reflects match, no dot for pit, screen projection |
| `TestLowConfidenceState` | 5 | far=UNKNOWN, medium distance=MEDIUM, centreline=HIGH, warnings non-empty, confidence color green |
| `TestLegacyRefPathHandling` | 5 | 200-pt produces valid map, 200-pt corners, 200-pt matchable, curvature non-flat, JSON roundtrip |
| `TestWidthModel` (bonus) | 4 | unused pct at centreline, near-left detected, near-right detected, centreline not near-edge |
| `test_no_pyqt_in_data_modules` | 1 | none of the 3 data modules import PyQt6 |

**Full suite result after Group 17O: 2014 pass / 5 skip / 0 fail**

---

### Group 17O UAT Remediation — DEF-17O-UAT-001/002/003 (2026-06-25)

**New test file:** `tests/test_group17o_uat_defects.py` — 23 tests

| Class | Count | Coverage |
|-------|-------|----------|
| `TestDef17OUAT001RefPathAttribute` | 6 | Controller has no `_ref_path`; correct attribute is `_last_build_result.reference_path`; station map builds from ref path; `has_map=True`; None/empty → no map |
| `TestDef17OUAT002OverlayFiltering` | 9 | `_TELEMETRY_OVERLAY_SEG_TYPES` defined; GEAR_ZONE, LIMITER_ZONE, FUEL_SAVING_CANDIDATE, KERB_OR_BUMP_CANDIDATE in set; geometry types NOT in set; filtering removes overlays; review result filtering; count calculation |
| `TestDef17OUAT003DaytonaCornerCount` | 8 | seed=12 → 12 seeded corners; station map authoritative over detection count; placeholders fill gap; 12 corner labels in draw data; status text includes count; detection result count can differ from station map |

**Defects fixed in `ui/dashboard.py`:**
- DEF-17O-UAT-001: `_tm_try_build_station_map()` now accepts optional `ref_path` param; when None, reads `ctrl._last_build_result.reference_path` (not the non-existent `ctrl._ref_path`)
- DEF-17O-UAT-001 (disk path): `_tm_detect_segments_safe()` disk-load branch now also loads saved reference path and builds station map if not already built
- DEF-17O-UAT-002: Added `_TELEMETRY_OVERLAY_SEG_TYPES` frozenset; after `_create_seg_review()`, filters `review.segments` to geometry types only; segment count label shows geometry-only count
- DEF-17O-UAT-003: Summary labels now prefer station map corner counts when `_tm_station_map` is available; shows `"{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated"`

**New imports added to `ui/dashboard.py`:**
- `import_reference_path_json as _import_ref_path` from `data.track_calibration`
- `TrackSegmentType as _TrackSegmentType` from `data.track_segment_detection`

**Full suite result after Group 17O UAT Remediation Round 1: 2037 pass / 5 skip / 0 fail**

---

### Group 17O UAT Remediation Round 2 — DEF-17O-UAT-004/005/006/007/008 (2026-06-25)

**Updated test file:** `tests/test_group17o_uat_defects.py` — 40 tests (+17 new)

| Class | Count | Coverage |
|-------|-------|----------|
| `TestDef17OUAT002OverlayFiltering` | 10 (+1) | Added `test_braking_and_traction_zones_are_overlay`; reclassified BRAKING_ZONE/TRACTION_ZONE as car-specific overlays (Porsche RSR warnings); updated `test_geometry_types_not_in_overlay_set` and `test_review_segment_filtering_preserves_geometry` |
| `TestDef17OUAT004StationMapCountDisplay` | 3 | Station count non-zero; count formatted in label with "Map:" prefix; station count != reference path point count (different metrics) |
| `TestDef17OUAT005SeedLookupFix` | 5 | `TrackSeedLoadResult` has no `.layouts`; has `.track_locations`; `get_selected_layout()` navigates nested structure; returns None on wrong IDs; full pipeline test (get_selected_layout → SimpleNamespace → build_track_station_map with 12 corners) |
| `TestDef17OUAT007MapDisplayFix` | 2 | Seed lookup succeeds → draw data `has_map=True`, 12 corner labels; no seed → draw data still `has_map=True` |
| `TestDef17OUAT008StationMapPersistence` | 6 | export creates .json file; import roundtrip preserves station count; import roundtrip preserves 12 corners; find_station_map_path returns path after export; returns None when not exported; imported map produces valid draw data with 12 corner labels |

**Defects fixed in `ui/dashboard.py`:**
- DEF-17O-UAT-005/007 (CRITICAL seed bug): `_tm_try_build_station_map()` — replaced `for layout in self._tm_seed_result.layouts:` (AttributeError: `TrackSeedLoadResult` has `.track_locations` not `.layouts`) with `get_selected_layout(self._tm_seed_result, loc_id, lay_id)`; also reads `loc_id` from location combo (was missing)
- DEF-17O-UAT-006: Added `_TrackSegmentType.BRAKING_ZONE` and `_TrackSegmentType.TRACTION_ZONE` to `_TELEMETRY_OVERLAY_SEG_TYPES` — both carry "Car-specific — Porsche RSR" warnings and are NOT universal track geometry
- DEF-17O-UAT-004: After successful station map build in `_tm_try_build_station_map()`, updates `_tm_lbl_build_info` to show `"Path: N pts | Conf: X | Map: N stations / N corners"` instead of path-only
- DEF-17O-UAT-008 (persistence): `_tm_try_build_station_map()` now calls `_export_station_map()` after each build (best-effort, silent on failure); added `_tm_try_load_station_map_from_disk(loc_id, lay_id)` called from `_tm_on_layout_changed()` — auto-loads saved station map from `data/track_models/` when layout is selected
- Turn column: `_tm_refresh_seg_table()` now matches each segment to the nearest `SeededCorner` by `lap_progress_mid` (< 15% threshold) when `turn_number` is None — populates Turn column for non-apex segments (braking, entry, exit, corner_exit) from station map corner IDs

**New imports added to `ui/dashboard.py`:**
- `export_station_map_json as _export_station_map`, `import_station_map_json as _import_station_map`, `find_station_map_path as _find_station_map_path` from `data.track_station_map`

**Full suite result after Group 17O UAT Remediation Round 2: 2054 pass / 5 skip / 0 fail**

---

### Group 17H — Track Intelligence AI Prompt Integration (2026-06-24)

**New module:** `strategy/track_context_prompt.py`

**Public function:**
- `get_track_context_for_ai(track_location_id, layout_id) -> str`
  - Missing/empty IDs: returns `"Track Intelligence unavailable: no selected track/layout was provided."`
  - Present: delegates to `build_resolved_track_context_for_prompt()` from `data.track_model_resolver`
  - Resolver exception: returns safe error note with exception class and message; never raises

**`strategy/ai_planner.py` changes:**
- `RaceParams.track_location_id: str = ""` and `RaceParams.layout_id: str = ""` new optional fields
- `_build_race_prompt(track_context="")` — injects section before `## Practice lap times`
- `_build_practice_prompt(track_context="")` — injects section before `## Practice lap times`
- `_build_setup_from_scratch_prompt(track_context="")` — injects section after race conditions block
- `build_car_setup(track_location_id="", layout_id="")` — calls `get_track_context_for_ai()`, passes context to prompt builder; adds `track_context_included`, `track_location_id`, `layout_id` to `structured_payload`
- `analyse_strategy()` — resolves context from `params.track_location_id/layout_id`; adds debug metadata to `structured_payload`; adds "Track Intelligence unavailable" to `_warnings` when IDs missing
- `analyse_practice_session()` — same

**`strategy/driving_advisor.py` changes:**
- `DrivingAdvisor._get_track_intelligence_context()` — reads from `config["strategy"]["track_location_id"/"layout_id"]`; calls `get_track_context_for_ai()`; never raises
- `_build_coaching_prompt()` — `track_intel_block` prepended in `extra_sections`
- `_build_setup_prompt()` — same
- `_build_combined_prompt()` — same

**`ui/dashboard.py` changes:**
- `_tm_on_layout_changed()` — stores `loc_id`/`lay_id` to `config["strategy"]["track_location_id"/"layout_id"]`
- `_run_ai_analysis()` — passes `track_location_id`/`layout_id` from config into `RaceParams`
- `_run_practice_analysis()` — same; debug print updated with track context presence info
- `_run_build_setup()` — reads `_track_loc_id`/`_layout_id_build` from config; passes to `build_car_setup()`

**Context injection summary:**
- Missing IDs → "Track Intelligence unavailable" note in every AI prompt
- Seed-only → seed context + "seed data only — NOT validated" warning
- Not AI-ready → reviewed segments + blockers + explicit "NOT AI-READY" caveat
- AI-ready → full segment summary + confirmed list + Porsche boundary note
- Engineer-validated → same as AI-ready but with "Engineer-validated" source label

**Deferred:**
- Live current-segment lookup
- Telemetry-to-segment issue enrichment
- Wiring `layout_id` from Event Planner (currently only from Track Modelling tab selection)
- `_build_feeling_prompt` track context injection
- Track auto-detection from telemetry

**Test coverage (56 tests, 16 test classes):**
- `TestGetTrackContextMissingIds` — 6 tests: None loc, None layout, empty loc, empty layout, both None, returns string
- `TestGetTrackContextCallsResolver` — 3 tests: resolver called when IDs present, receives exact IDs, real seed returns section
- `TestGetTrackContextErrorSafety` — 4 tests: RuntimeError, ImportError, error returns string, does not raise
- `TestRaceParamsFields` — 5 tests: default empty, default empty, set loc, set layout, both coexist
- `TestBuildRacePromptTrackContext` — 3 tests: injected when provided, no crash when empty, before practice lap times
- `TestBuildPracticePromptTrackContext` — 3 tests: injected, no crash, before practice lap times
- `TestBuildSetupFromScratchTrackContext` — 3 tests: injected, no crash, forwarded via build_car_setup
- `TestAnalyseStrategyTrackContext` — 2 tests: payload true when IDs set, payload false when missing
- `TestAnalysePracticeSessionTrackContext` — 2 tests: payload flag true, flag false when missing
- `TestDrivingAdvisorTrackIntelligence` — 4 tests: warning when no IDs, calls resolver, returns string on error, does not raise
- `TestCoachingPromptTrackIntelligence` — 3 tests: included when IDs set, warning when missing, in extra_sections
- `TestSetupPromptTrackIntelligence` — 3 tests: included when IDs set, warning when missing, combined prompt included
- `TestSeedOnlyContextWarning` — 2 tests: seed includes not-validated warning, missing track returns non-empty string
- `TestMissingLayoutIdSafety` — 2 tests: analyse_strategy no crash, build_car_setup no crash
- `TestBuildCarSetupPayloadDebug` — 2 tests: payload true when IDs set, payload false when missing
- `TestRegressionImports` — 9 tests: 17A–17H importable, RaceParams has new fields, DrivingAdvisor has method, get_track_context returns string

**Tests Run:** 1420 pass / 5 skip / 0 fail (1425 collected)

---

### Group 31 — Race-Engineer Prompt Directives, Validation, and Bottoming Classifier (2026-06-29)

**Primary file:** `strategy/driving_advisor.py`
**Secondary files:** `telemetry/recorder.py`, `ui/setup_builder_ui.py`
**Test file:** `tests/test_group31_race_engineer.py` (144 tests)

**New module-level functions added to `strategy/driving_advisor.py`:**
- `_validate_setup_response(parsed, car_name, allowed_tuning, locked_fields, setup) -> dict` — 7-check validation layer; appends `validation_errors` list to parsed JSON; never silently drops changes
- `_classify_bottoming_location(bottoming_positions, loc_id, lay_id) -> str` — delegates to `enrich_telemetry_issues`; votes on segment type; returns category string or "unknown"
- `_derive_locked_fields(allowed_tuning) -> set[str]` — maps allowed-tuning categories to canonical param names; has comments for unmapped categories (steering, nitrous)
- `_race_engineer_directives(..., setup=None) -> str` — generates AC1–AC13 directive text including I1 ride-height-at-max detection

**Changes to existing functions:**
- `_normalise_changes`: added no-op stripping (from == to_clamped → drop change)
- `_get_previous_ai_context(feature, prior_outcomes=None)`: renders structured block when prior_outcomes is a non-empty list
- `build_setup_advice_response`: max_tokens 1000→1500; post-call normalise+validate+locked-strip
- `build_combined_setup_response`: max_tokens 1200→1500 (C2); C1 setup_fields rebuild after normalise; C3a locked-field strip from both changes and setup_fields; normalise+validate; passes `prior_outcomes`
- `_build_setup_prompt` and `_build_combined_prompt`: inject `_race_engineer_directives` block + extended JSON schema (AC8 keys: `primary_issue`, `issue_classification`, `validation_targets`, `do_not_change_reasoning`, `confidence`, `expected_validation`)

**Changes to `telemetry/recorder.py`:**
- `LapStats`: added `bottoming_positions: list = field(default_factory=list)`
- `_compute_stats`: captures rising-edge XYZ on bottoming events (mirrors snap_throttle_positions pattern)

**Changes to `ui/setup_builder_ui.py`:**
- Added `_format_validation_errors_banner(validation_errors: list) -> str` pure module-level helper (C3b)
- `_display_setup_result`: reads `validation_errors` from parsed JSON; renders banner before changes list

**Defects fixed:**
- C1/I3: `build_combined_setup_response` now rebuilds `setup_fields` from surviving normalised changes after `_normalise_changes` strips no-ops
- C2: `build_combined_setup_response` max_tokens corrected to 1500 (was 1200)
- C3a: locked-field changes stripped from both `changes` and `setup_fields` after validation in both entry points
- C3b: `validation_errors` rendered as orange banner in `_display_setup_result`
- I1/AC3: `_race_engineer_directives` now accepts `setup` dict; emits explicit "do NOT recommend raising" when ride height is at per-car max with bottoming present; emits "IS permissible" when below max
- I5: `_derive_locked_fields` has inline comments explaining that `steering` and `nitrous` categories have no canonical setup params mapped yet

**Acceptance criteria covered:**
- AC1: Per-car range clamping enforced; prompts state unit and step (Hz, kg, °, mm)
- AC2: Ride-height reported in mm, springs in Hz; camber always ≤ 0 (negative convention)
- AC3: Ride-height escalation sequence (springs → ARB → damper → RH); at-max → no-op warning; I1 explicit names fields
- AC4: Stable braking preserved — "do NOT change brake_bias" when lockups < 0.5 and consistency < 15 m
- AC5: AC5 smallest-effective-change instruction in prompt
- AC6: Snap-throttle driver-input separation when snap > 0 and os_throttle_on > 0
- AC7: Issue classification (`setup-limited`, `driver-input-limited`, `mixed`, `insufficient-data`)
- AC8: Extended JSON schema keys injected into prompt
- AC9: Track zone context from bottoming/oversteer positions; "low confidence" when positions empty
- AC10: Bottoming count and classifier output injected when avg_bottom > 0
- AC11: Race-objective framing (lap race: stint/tyre; timed: time-window/fuel)
- AC12: Short-sample warning when laps < 20% of event laps
- AC13: Smallest-effective-change instruction
- AC14: Server-side validation (unresolvable field, out-of-range, locked, no-op, string-not-number, >4 changes, setup_fields mismatch)

**Test classes:**
- `TestAC1RangeAuthority` — 3 tests
- `TestAC1RangeAuthorityAugmented` — 2 tests (per-car min/max override)
- `TestAC2Units` — 4 tests
- `TestAC3RideHeightEscalation` — 4 tests
- `TestAC3RideHeightEscalationAugmented` — 6 tests (includes I1 at-max vs below-max)
- `TestAC4StableBraking` — 5 tests
- `TestAC5SmallestEffectiveChange` — 2 tests
- `TestAC6SnapThrottleDriverInput` — 4 tests
- `TestAC7IssueClassification` — 4 tests
- `TestAC8ExtendedJsonSchema` — 5 tests
- `TestAC9ZoneContext` — 4 tests
- `TestAC10BottomingCount` — 4 tests
- `TestAC11RaceObjectiveFraming` — 4 tests
- `TestAC12ShortSampleWarning` — 3 tests
- `TestAC13SmallestEffectiveChange` — 2 tests
- `TestAC14ValidationErrors` — 7 tests
- `TestModuleLevelFunctionsExist` — 4 tests
- `TestNormaliseChangesRegression` — 3 tests
- `TestClassifyBottomingLocation` — 4 tests
- `TestPriorOutcomesStructuredBlock` — 5 tests
- `TestPromptPriorOutcomesIntegration` — 3 tests
- `TestPorsche963ReferenceFailureCase` — 7 tests (end-to-end scenario with per-car ranges)
- `TestC1CombinedRebuildSetupFieldsAfterNoOpStrip` — 2 tests
- `TestC2MaxTokensBehavioural` — 2 tests (captures max_tokens via call_api stub)
- `TestC3aLockedFieldStripped` — 2 tests
- `TestC3bValidationErrorsBanner` — 5 tests (pure helper, no Qt)
- `TestI1AC3RideHeightAtMax` — 5 tests

**Full suite result after Group 31: 3426 pass / 6 skip / 0 fail**

---

## Groups 26–38 + Lettered Groups (Strategy / Race-Engineer / Setup Overhaul)

> Added 2026-07-02. These groups landed across commits `6440a00` (Group 31),
> `7cf7d4f` (race-engineer overhaul: Groups 26–36 + A/B/C/D/E + Qualifying),
> and `1dea1e3` (Groups 37/37b/38). Each entry lists the primary files and the
> test file with its test count. Full suite after all of these: **3813 pass /
> 6 skip / 0 fail**.

### Group 26 — Setup Overhaul (2026-06-28)
Setup-advice prompt/parse overhaul: `GENERIC_DEFAULTS` / `resolve_ranges` /
`save_car_ranges` / `_parse_setup_recommendation`; prompt contradiction fixes
(ARB, LSD, dampers, toe); race-vs-qualifying session objective text; hybrid race
context + race-engineer brief; driver-profile knowledge-base sections; seven-label
reasoning structure.
- Files: `strategy/setup_ranges.py`, `strategy/driving_advisor.py`, `knowledge/gt7_tuning_reference.md`
- Test: `tests/test_group26_setup_overhaul.py` — 66 tests

### Group 27 — Setup Overhaul 2 (2026-06-28)
`build_car_setup`: `max_tokens=6000`, `_is_truncated`, retry logic, double-failure
`RuntimeError`; camber positive 0–6 convention across defaults/resolve/parse/prompt/JSON;
displayed AI suggestions clamped to ranges with "(clamped to …)" annotation; apply-highlight
/ clear-on-save wiring.
- Files: `strategy/driving_advisor.py`, `strategy/setup_ranges.py`, `data/car_setup_ranges.json`, `ui/setup_builder_ui.py`
- Test: `tests/test_group27_setup_overhaul2.py` — 86 tests

### Group 28 — Analyse-path Per-Car Ranges in Prompt (2026-06-28)
The telemetry/feeling "Analyse / Get Setup Fix" prompts previously listed field
names only, so the AI never saw the car's real bounds. New shared
`_valid_ranges_block(car_name)` helper (built from the same `resolve_ranges()`
data the parser clamps against) injected into all three analyse prompts.
- Files: `strategy/driving_advisor.py`
- Test: `tests/test_group28_analyse_prompt_ranges.py` — 21 tests

### Group 29 — Tyre Wear Multiplier: No Practice→Race Scaling (2026-06-28)
Removed practice→race wear scaling globally. The one configured multiplier is the
wear rate for BOTH sessions; practice laps ARE race laps. Fixes double-counting for
drivers who set the same wear in practice and race.
- Files: `strategy/engine.py`, `strategy/ai_planner.py`
- Test: `tests/test_group29_tyre_wear_no_scaling.py` — 9 tests

### Group 30 — Track-Map Projection Cache (2026-06-28)
`project_to_screen()` caching to cut per-frame allocation without ever serving a
stale live car dot (the live path mutates `draw_data.car_dot` in place each packet).
- Files: `ui/track_map_vm.py`
- Test: `tests/test_group30_projection_cache.py` — 6 tests

### Group 31 — Shift Indicator / RPM Beep (backend + Group C UI) (2026-06-29)
Backend: `should_shift_beep` / `resolve_threshold` pure helpers; new
`shift_rpm_qual` / `shift_rpm_race` parse fields + prompt text. Group C (frontend):
Live-tab shift-beep settings persist to `config["shift_beep"]` and mirror to
read-only Setup spinboxes; live/practice mode snapshots; AI setup-apply writes both
qual+race thresholds.
- Files: `voice/announcer.py`, `ui/dashboard.py`, `ui/setup_builder_ui.py`, `strategy/driving_advisor.py`
- Tests: `tests/test_group31_shift_beep.py` — 47 tests; `tests/test_group31b_shift_beep_ui.py` — 18 tests
- (Race-Engineer Prompt Directives / validation / bottoming classifier — see the earlier "Group 31" section above; 144 tests in `test_group31_race_engineer.py`.)

### Group 32 — Feasibility-Gated Race Strategy Prompt Pipeline (2026-06-30)
New `strategy/feasibility.py` feasibility gate integrated with the AI strategy
prompt pipeline. Estimates race laps, checks compound eligibility, rejects
short/impossible stints and infeasible stop counts BEFORE any AI call; emits named
`DataGap`s instead of silent fallbacks; `FeasibilityReport` + `StrategyResult`.
- Files: `strategy/feasibility.py` (new), `strategy/ai_planner.py`
- Test: `tests/test_group32_feasibility_gate.py` — 84 tests

### Group 33 — Dashboard Wiring for Feasibility-Gated StrategyResult (2026-06-30)
UI consumes the new `StrategyResult`: `_display_strategy_results` reads
`result.strategies` explicitly; `_build_feasibility_html` renders rejected
strategies / data gaps / assumptions / calculation notes (empty sections produce
no header); timed-race lap estimate uses `estimate_race_laps` (ceil) + best clean
lap of the most-sampled compound, matching the feasibility module exactly.
- Files: `ui/dashboard.py`
- Test: `tests/test_group33_strategy_result_wiring.py` — 38 tests

### Group 34 — Acceptance: Validated, Feasibility-Gated Race Strategy Prompt (2026-06-30)
End-to-end acceptance for the feasibility pipeline (AC1–AC12 + edge cases): named
data gaps, timed-race lap ceil, pre-AI rejection of impossible stop counts, stop
counts from measured data, strategy names decoupled from speed rank, 4 top-level
output fields, data-quality summary with std-dev, RS/RH blocked without ≥8 clean
laps, pit_time formula, risk fields, tuning-lock, explicit prompt rules.
- Files: `strategy/feasibility.py`, `strategy/ai_planner.py`, `ui/dashboard.py`
- Test: `tests/test_group34_strategy_feasibility_acceptance.py` — 131 tests

### Group 35 — Mid-Race AI Re-plan + Qualifying Engineer (Group B backend) (2026-07-01)
`engine._request_replan` (in-flight idempotency); pace trigger fires at
`slow_lap_count >= 4`; tyre-deg breach trigger; `apply_replan` preserves completed
stints + sets new `start_lap`; `_on_pit_exit` resets `_adapted_plan`; qualifying ack
fires once in qualifying mode; `_build_race_prompt` gains a MID-RACE RE-PLAN block
when `race_situation` populated; orchestrator + dashboard wiring.
- Files: `strategy/engine.py`, `strategy/ai_planner.py`, `strategy/strategy_orchestrator.py`, `ui/dashboard.py`
- Test: `tests/test_group35_midrace_replan.py` — 51 tests

### Group 36 — Group B AC Verification (qualifying + mid-race re-plan) (2026-07-01)
Fills AC gaps not covered by Group 35 / Qualifying Mode: qualifying ack uses
`Priority.HIGH`; race-finish announcement suppressed in qualifying; descriptive
replan reason at `slow_lap_count >= 4`; `race_situation` dict contains all required
keys; `apply_replan` resets `_slow_lap_count` / clears `_replan_in_flight`; adapted
plan announcement includes new pit lap + target pace; in-flight guard completeness.
- Files: `strategy/engine.py`, `strategy/ai_planner.py`, `voice/announcer.py`, `ui/dashboard.py`
- Test: `tests/test_group36_groupB_ac_verification.py` — 51 tests

### Group 37 — Relative-Compound Tyre Degradation Point (2026-07-02)
New `strategy/relative_degradation.py::compute_relative_degradation`. A compound's
optimal stint length is measured against the next-harder compound's mean baseline
pace (skipped-tier aware: RS→RM→RH). Hardest compound, single compound, and wet
compounds fall back to cliff detection. Handles never-degrades (optimal=0,
not_yet_degraded), degrade-from-lap-1, and outlier laps that must not trigger a run.
- Files: `strategy/relative_degradation.py` (new)
- Test: `tests/test_group37_relative_degradation.py` — 44 tests

### Group 37b — Engine Integration: Harder-Baseline Degradation Alert (2026-07-02)
`RaceStrategyEngine.set_degradation_cache` + `_check_tyre_degradation` fire a live
alert when a compound's rolling average crosses its harder-compound baseline; falls
back to the reference-plus-threshold rule when no baseline is cached.
- Files: `strategy/engine.py`
- Test: `tests/test_group37b_engine_harder_baseline.py` — 16 tests

### Group 38 — Acceptance: Relative-Compound Tyre Degradation (2026-07-02)
Full AC1–AC12 + edge-case acceptance against the real implementation
(`relative_degradation.py`, `ai_planner._build_degradation_prompt`, `engine`
degradation cache/alert, `feasibility.check_compound_eligibility`,
`config.json degradation_consecutive_laps`, `data/tyres.py` ordering). Feasibility
gate rejects zero-optimal ("not yet degraded") entries; LIFE ordering (RS ≤ RM ≤ RH)
enforced after merge.
- Files: `strategy/relative_degradation.py`, `strategy/ai_planner.py`, `strategy/engine.py`, `strategy/feasibility.py`
- Test: `tests/test_group38_relative_degradation_acceptance.py` — 73 tests

### Group A — Live Tab Cleanup (2026-07-01)
Live-tab session combo is never driven by telemetry (manual always wins from the
first packet; auto-sync block removed). `tracker.session_type` honours
`_session_type_override`. Live-tab map widget/label/column removed (the Track
Modelling tab keeps its map via `_tm_map_widget`); dead `_live_map_widget` refs
removed; `test_group24_live_map_autoload.py` deleted. `set_race_active()` called from
`_on_live_mode_changed` (True only for "Race").
- Files: `ui/dashboard.py`, `telemetry/state.py`
- Tests: `tests/test_groupA_combo_no_autosync.py` — 20; `tests/test_groupA_live_tab_cleanup.py` — 26; `tests/test_groupA_session_override_property.py` — 6

### Group D — Structured Setup Naming + Local-Time Timestamp (2026-07-01)
Pure naming/numbering helpers in `ui/setup_name_helper.py`; mixin
`_generate_setup_name`; save-guard + prefill wiring; old helper removed;
`setup_history` timestamp is local time (no `timezone.utc`).
- Files: `ui/setup_name_helper.py` (new), `ui/setup_builder_ui.py`, `data/setup_history.py`
- Test: `tests/test_groupD_setup_naming_timestamp.py` — 29 tests

### Group E — Pit-Lap Exclusion + Track-Map Loop Closure (2026-07-01)
First lap (lowest lap_number) always rejected as out-lap; `detect_pit_lap_raw` laps
rejected; clean non-first non-pit laps accepted (one result per lap, ordered);
`closure_gap_m` computed; renderer closes the centreline (not the pit-lane
polyline); `None` station_map → empty centreline.
- Files: `data/track_geometry_builder.py`, `ui/track_map_widget.py`
- Test: `tests/test_group_e_pit_lap_exclusion.py` — 27 tests

### Qualifying Mode — Completion Feature (2026-07-01)
Voice delta announcements after a qualifying lap; flying-lap tyre-warning
suppression; `get_best_practice_lap_ms` DB method; auto-reference delta.
- Files: `strategy/engine.py`, `voice/announcer.py`, `ui/dashboard.py`
- Test: `tests/test_qualifying_mode.py` — 22 tests

---

## Integration — Setup Brain + Strategy Outcome (2026-07-02)

Combined integration branch `integration/setup-brain-strategy-overhaul` (off `master`)
merges two feature branches, in order: (1) `feature/setup-diagnosis-engine`, then
(2) `feature/strategy-outcome-comparison`. Both merges were clean (no conflicts;
`strategy/ai_planner.py` auto-merged — the branches touched disjoint regions).
**Combined full suite: 3984 pass / 6 skip / 0 fail.** Awaiting runtime UAT before
merge to `master`.

### Setup Brain (`feature/setup-diagnosis-engine`)
App-side deterministic setup diagnosis is built BEFORE the AI call and the AI's
answer is validated AFTER (regenerate-once, then surface — never silently applied).
- **New `strategy/setup_diagnosis.py`:** `build_setup_diagnosis` (bands: bottoming
  minor `<0.5` / moderate `0.5–1.0` / consider `>1.0` / required `>2.0`; wheelspin
  meaningful `>5` / major `>10` / severe `>15`; aero near-min = within 10% of range),
  `validate_setup_engineering` (rejects ride-height-for-minor-bottoming,
  rear-aero-cut-with-wheelspin, aero-at-min-with-floaty-understeer,
  gearbox-edit-when-preserve, locked-field, bad units — composes the existing
  per-car validator), `_parse_driver_feel`, `format_diagnosis_for_prompt`,
  `_derive_location_confidence` (low-confidence track model blocks ride-height
  justified by corner-location data), constants `PERSONAL_DRIVER_TUNING_MODEL` +
  `DRIVER_HARD_CONSTRAINTS` injected at all three prompt sites.
- **Gearbox preserved** when the driver says it is good, in race AND qualifying,
  unless telemetry proves a specific gear problem.
- **Bug fixes:** `strategy/_ai_client.py` springs label N/mm → **Hz** (and aero
  kg → downforce); `strategy/driving_advisor.py` event context renders timed races
  as "N minutes, Timed Race" and singular "1 lap".
- **History learning:** `data/setup_history.py` stores structured liked/hated labels
  and emits "do not repeat hated" / "prefer confidence-improving" / "subjective
  confidence is a performance variable" directives.
- **UI:** `ui/setup_builder_ui.py` engineering-validation-failed banner, App-diagnosis
  summary line, and Liked/Hated + Applied feedback controls.
- Files: `strategy/setup_diagnosis.py` (new), `strategy/driving_advisor.py`,
  `strategy/ai_planner.py`, `strategy/_ai_client.py`, `data/setup_history.py`,
  `ui/setup_builder_ui.py`.
- Test: `tests/test_group38_setup_diagnosis.py` — 74 tests (incl. the Porsche
  RSR '17 / Fuji 50-min regression + regenerate-once orchestration).

### Strategy Outcome (`feature/strategy-outcome-comparison`)
Strategy Builder now compares TOTAL RACE OUTCOMES deterministically instead of
listing stints.
- **New `strategy/outcome.py`:** `compute_outcome` (T_race = degraded-pace lap
  integral incl. tyre-cliff step + pit time = n_stops·pit_loss + Σ ceil(fuel/refuel
  rate), 100 L tank; confidence drops when deg data is thin) and `compare_outcomes`
  (ranks by deterministic time, computes delta-vs-fastest).
- **Additive wiring:** `StrategyOption` gains `deterministic_time_s`,
  `delta_vs_fastest_s`, `outcome_confidence`, `rank_by_time`; populated in
  `_parse_strategies` from the live params + degradation cache. AI's
  `estimated_time_s`, `stints` shape, and list order are unchanged (Load Strategy N /
  replan / voice untouched).
- **UI:** `ui/dashboard.py` `_build_strategy_html` shows app-computed time with
  "+X.Xs vs fastest", a confidence badge, a "#N by time" rank, and the
  previously-hidden tyre/fuel/undercut/AI-confidence risk fields; "pit loss"
  relabelled "pit time".
- Files: `strategy/outcome.py` (new), `strategy/ai_planner.py`, `ui/dashboard.py`.
- Tests: `tests/test_group39_strategy_outcome.py` — 53; `tests/test_group40_strategy_card_rendering.py` — 44.

### Deferred / carried forward
- Setup history key omits track `layout_id` (`config_id` re-hash risk) — deferred.
- From-scratch "Build Setup with AI" has the constraint prompt text but not the
  post-AI validation/regenerate loop (no telemetry at build time) — deferred.
- Strategy finishing-position prediction needs rival telemetry not in the pipeline
  today — deferred.

---

## Group 18A — Track Truth Foundation (2026-07-03)

Builds the foundation for a proper **Track Truth** system so the app stops treating
curvature-only detected corners as authoritative track truth. Product principle:
**no mapped-corner confidence ⇒ no high-confidence setup/strategy recommendation.**
Foundation only — no Setup/Strategy/Live-Engineer rewrite. **45 new tests. Full suite:
4053 pass / 6 skip / 0 fail.**

### Files added
- `data/track_truth.py` (new) — pure-Python Track Truth data model + validation + AI guard.
  Enums `TrackTruthStatus` / `TrackTruthConfidence` / `TrackTruthSource` /
  `TrackTruthValidationIssue`; dataclasses `TrackStation`, `CornerWindow`, `CornerComplex`,
  `SectorMarker`, `PitLaneDefinition`, `TrackTruthManifest`, `TrackTruthModel`,
  `TrackTruthValidationResult`; schema constants `track_truth_model_v1` /
  `track_truth_manifest_v1`; functions `track_truth_model_to_dict` /
  `track_truth_model_from_dict` (None on schema mismatch, never raises) /
  `export_track_truth_model_json` / `import_track_truth_model_json` /
  `resolve_track_truth_model(track_id, layout_id, base_dir=None)` /
  `validate_track_truth_model(model)` / `can_use_track_truth_for_ai_corner_context(result)`.
- `data/track_truth_matcher.py` (new) — station-based live map-matching foundation.
  `TrackTruthMatchInput`, `TrackTruthMatchResult`,
  `match_track_truth_position(inp, model, validation=None)` (never raises). Weighted
  `_score_candidate` (spatial + heading + monotonic-progress + lap-wrap +
  max-plausible-movement + pit awareness), swappable for HMM/Viterbi later. Confidence bands
  mirror `track_map_matching.py` (≤5 m HIGH / ≤20 m MEDIUM / ≤60 m LOW / else NONE).
- `data/track_truth_calibration.py` (new) — calibration wizard foundation.
  `TrackTruthWizardStage` (NOT_STARTED → CAPTURE_CENTRELINE → CAPTURE_LEFT_EDGE →
  CAPTURE_RIGHT_EDGE → OPTIONAL_HOT_LAP → BUILD_PROPOSED → VALIDATE → ACCEPT),
  `TrackTruthWizardState`, `TrackTruthCalibrationWizard`. Illegal transitions are no-ops
  setting `state.error`; `accept()` is the only route to ACCEPT and persists via
  `save_seed_geometry_to_library`; geometry building delegated through a defensive wrapper
  around `data/track_geometry_builder.build_seed_geometry` (no duplicate algorithm);
  `abandon()` resets and writes no file.

### Files modified (additive only)
- `ui/track_modelling_vm.py` — `format_track_truth_status(model, validation, track_id=None,
  layout_id=None) -> dict` (20-key value+`_color` dict; `"—"`/`"#888888"` placeholder for
  None; four display states; uses "Track Truth" / "Map Alignment" / "Live Mapping Ready").
- `ui/track_modelling_ui.py` — "Track Truth / Mapping" QGroupBox panel +
  `_tm_refresh_track_truth_panel()` wired into `_tm_on_layout_changed`, `_tm_run_alignment`,
  `_tm_accept_track_model`, `_tm_rebuild_model`, `_tm_try_load_accepted_model`. Headless-VM
  tests only (no Qt test, per project convention) — needs manual UAT.

### New schema
`track_truth_model_v1` (envelope with nested `track_truth_manifest_v1` + corner_windows /
corner_complexes / sectors / stations / pit_lane). **Runtime-built** from the existing library
manifest + semantic_model — **no new JSON file added to the library.** Full field list in
`docs/TRACK_LIBRARY_SCHEMA.md`.

### Validation gates
- `is_accepted` = no blockers. Blockers: non-monotonic stations, progress out of 0–100,
  `lap_length ≤ 0`, apex outside window, complex referencing a missing corner ID, sector out
  of range, `corners_expected > 0` with no windows, and `NO_COORDINATE_GEOMETRY` (exact text
  *"Coordinate geometry unavailable — high-confidence corner mapping is blocked"*).
- `is_usable_for_live_mapping` = `is_accepted` AND stations present AND
  `manifest.corners_are_seed_verified` (explicit growth field, default False).
- `is_usable_for_ai_corner_context` = `is_usable_for_live_mapping` AND
  `manifest.seed_geometry_available`.
- AI guard `can_use_track_truth_for_ai_corner_context()` returns True only when accepted AND
  usable for AI corner context; None → False.
- Single-member complex is a **warning**, not a blocker. `summary` never says "accepted" when
  not accepted; a rejected model with geometry gets `status = NO_DATA`.

### Daytona status
Runtime Track Truth built from Daytona's existing manifest + semantic model (12 corners, 3
sectors, 2 complexes incl. Horseshoe/T10T11). Because Daytona has no `geometry.seed_map.json`,
the model has zero stations → `NO_COORDINATE_GEOMETRY` blocker → `is_accepted = False` → AI
corner context BLOCKED. `availability.seed_geometry` stays `false`. Acceptance stays blocked
until a real seed geometry exists.

### Test coverage (45 tests)
| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_group18a_track_truth.py` | 26 | Model, dict/JSON round-trip (None on schema mismatch), runtime resolve, all validation gates, blockers/warnings, AI guard, Daytona-blocked case |
| `tests/test_group18a_track_truth_matcher.py` | 9 | Candidate scoring, confidence bands, monotonic-progress/lap-wrap, pit awareness, never-raises |
| `tests/test_group18a_track_truth_calibration.py` | 10 | Wizard stage machine, illegal-transition no-ops, delegated build wrapper, accept-only-to-ACCEPT, abandon resets |

### Deferred
Wiring `TrackTruthModel` into Setup Brain / Strategy Brain / Live Race Engineer; full
HMM/Viterbi matcher (scaffold only); a real Daytona `geometry.seed_map.json`; non-Daytona
tracks; automated boundary generation; deep AI prompt integration; automatic track ID.

**Full suite result after Group 18A: 4053 pass / 6 skip / 0 fail**

---

## DEF-17U-UAT-007 — Time Trial Calibration Laps Falsely Classified as Pit-In / Unusable (2026-07-03)

**Defect fixed:** DEF-17U-UAT-007 — clean GT7 Time Trial calibration laps were rejected and the reference-path build failed with *"Not enough usable laps to build reference path (0 usable, need 2)"*, wrongly reporting the clean laps as "pit-in laps" and the first/last partial laps as generic outliers.

**Symptom (Post-Group-17U UAT):** User drove 5 clean Time Trial laps (captured as 7 slices), never pitted. Build failed; diagnostics reported 7 captured laps, rejected lap 1 as an outlier (18.1s / 749m vs session median 128.7s / 6171m), detected laps 2–6 as "pit-in laps", rejected lap 7 (40 samples < 50), and concluded "All calibration laps appear to be pit-in laps."

**Root causes:**
1. GT7 Custom UDP telemetry has no reliable per-sample pit-lane flag (`TelemetrySample.is_in_pit_lane` is always `None`). Pit-in was inferred by `detect_pit_lap_raw()` purely from XZ-centroid geometry (contiguous run > 60 m from lap centroid for > 10 s) — false-positives on normal Time Trial laps.
2. Short partial first/last laps (captured when Start/Stop is pressed mid-lap) poisoned the session median and were mislabelled as generic outliers.

**Files modified:**
- `data/track_calibration.py` — `build_reference_path(session, *, pit_detection_enabled=False)` (pit detection now DISABLED by default; `detect_pit_lap_raw()` only called when opted in). New `CalibrationLapQuality` values `PARTIAL_START` / `PARTIAL_STOP` (first/last lap classified partial when path length < `PARTIAL_LAP_PATH_FRACTION`=0.5 of the interior/complete-lap median AND samples ≥ `MIN_CALIBRATION_SAMPLES`=50; guarded to sessions with > 2 laps). Session median duration/path computed from complete (non-partial) laps only. Partial laps excluded from build and NOT counted in `rejected_lap_count`. `CalibrationBuildResult` gained `partial_start_count`, `partial_stop_count`, `rejected_too_few_samples`, `rejected_path_length`, `pit_detection_enabled`. `diagnose_calibration_session()` surfaces the partial counts, `pit_detection_enabled`, and per-lap `"partial_start"` / `"partial_stop"` quality strings.
- `ui/track_modelling_vm.py` — `format_no_usable_laps()` gives a count-based failure message ("Pit detection: off", complete-candidate count, partial / too-few-samples / path-length breakdown); never says "pit-in" or "Drive a clean lap first" when complete candidates existed but were rejected. `format_build_failure_diagnostics()` shows the new breakdown, filters pit warnings when pit detection is off, and only recommends "Avoid pit stops" when pit detection ran. `_CAL_LAP_QUALITY_LABELS` maps `partial_start`→"Partial (start)", `partial_stop`→"Partial (stop)".
- `ui/track_modelling_ui.py` — Track Modelling build handler only shows the prominent pit warning label when `result.pit_detection_enabled` is True.
- `data/track_segment_detection.py` — no-usable-laps summary now also reports an "N partial" count so the numbers reconcile with the total captured.

**New test files:**

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_def17u_uat007_calibration_build.py` | ~35 | data/build layer: pit detection off by default, PARTIAL_START/STOP classification, median from complete laps only, partial laps excluded from build and not counted as rejected, new `CalibrationBuildResult` fields, `diagnose_calibration_session()` surfacing; exact UAT 7-lap regression builds a reference path |
| `tests/test_def17u_uat007_partial_laps.py` | 44 | UI formatters/labels: `format_no_usable_laps()` count-based message + no "pit-in"/"clean lap" wording when pit off, `format_build_failure_diagnostics()` breakdown + pit-warning filtering, `_CAL_LAP_QUALITY_LABELS` partial-start/stop labels |

**Updated test file:** `tests/test_group21b_missing_coverage.py` — 2 opt-in pit tests now pass `pit_detection_enabled=True`.

**Full suite result after DEF-17U-UAT-007 remediation: 4200+ passed.** The only failing test (`test_group28_analyse_prompt_ranges`) is a pre-existing failure in unrelated in-progress "setup ranges" work (`strategy/driving_advisor.py`), not part of this fix.

---

## Product Consolidation Sprint (2026-07-03)

Audit + safe first-pass UI clean-up. **No feature added, no backend capability
removed, no tab reordered.** Full suite after: **4135 pass / 6 skip / 0 fail**
(27 new tests). See `docs/PRODUCT_CONSOLIDATION_AUDIT.md` for the full audit.

### What was audited
All 13 top-level tabs (`ui/dashboard.py`, `ui/setup_builder_ui.py`,
`ui/track_modelling_ui.py`) against the intended 13-step race-engineer journey
and `REQUIREMENTS.md §12`. Produced: per-tab KEEP/MOVE/RENAME/MERGE/DELETE/
HIDE_UNTIL_READY verdicts with line refs; duplicate-workflow list (fuel burn in 3
tabs, API key in 2, track/layout selection in 3 places); stale-label list;
diagnostic-controls-in-normal-flow list; a 14-item single-source-of-truth
ownership table with ranked violations (worst: `config["strategy"]` event
fan-out); and a 9-context target architecture (EventContext…DiagnosticsContext).

### What was changed (low-risk, display-only / additive)
- **`ui/product_flow.py` (NEW, pure Python, no PyQt6)** — single source of truth
  for tab roles, the 13-step journey, tab-title decoration, and
  `build_flow_state_summary()` (next-action logic for the future home surface).
- **`ui/dashboard.py`** — tab 7 "Debug" → "Diagnostics";
  `_apply_product_flow_tab_markers()` prefixes the four tool tabs (Telemetry,
  Diagnostics, AI Log, Track Modelling) with a ⚙ marker from `product_flow`.
  Idempotent; tab indices (hard-coded in `_on_tab_changed`) unchanged.
- **`ui/track_modelling_ui.py`** — "5. Track Model Alignment" → "5. Seed Geometry"
  (section only builds seed geometry; alignment metrics live in Section 4);
  "Resolver Status" → "Track Model Status".

### What was intentionally NOT changed
`config["strategy"]` event fan-out (SSOT-1), track/layout split three ways
(SSOT-2), setups dual-resident in config+DB (SSOT-3), the 7 hidden legacy
per-segment buttons (`track_modelling_ui.py:517–524`, still `getattr`-referenced),
and the Track Modelling jargon glossary. All documented in the audit §5/§8/§9 as
higher-risk refactors for a follow-up sprint.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_consolidation_product_flow.py` (NEW) | 27 | tab-role classification, diagnostic-tab set, journey→workflow-tab integrity, 13 ordered steps, tab-title decoration idempotency + prefix-insensitivity, `build_flow_state_summary()` gate ordering (first-unmet next action, ready/pending partition, complete state), and source-scans confirming the Debug→Diagnostics / Section-5 / Resolver renames and preserved tab indices |
| `tests/test_group23b_ui_cleanup.py` (UPDATED) | — | Section-5 expected title updated "5. Track Model Alignment" → "5. Seed Geometry" |

### Manual UAT steps
1. Launch the app. Confirm the tab bar shows **six clean workflow tabs** (Live
   Race Engineer, Event Planner, Garage, Setup Builder, Practice Review, Strategy
   Builder), and that **Telemetry, Diagnostics, AI Log, Track Modelling** carry a
   ⚙ prefix marking them as tools. The former "Debug" tab now reads
   "⚙ Diagnostics".
2. Click through every tab — all open without error; no behaviour changed.
3. Track Modelling: Section 5 header reads "5. Seed Geometry"; the status panel
   in Section 4 reads "Track Model Status" (was "Resolver Status"). All
   calibration/segment/alignment functions still work.
4. Confirm no working feature regressed (Event Planner, Setup Builder AI, Strategy
   Builder, Live race panel, PTT/voice, calibration build).

### Recommended next sprint
**"State Consolidation 1 — EventContext":** introduce `EventContext`, remove the
`config["strategy"]` event fan-out, route Setup/Strategy/Live reads through it,
and render the home/overview panel from `build_flow_state_summary`.

---

## State Consolidation 1 — EventContext (2026-07-03)

First step of the target architecture from `docs/PRODUCT_CONSOLIDATION_AUDIT.md`
(§7). Creates a canonical **EventContext** read model that owns active
event/race configuration truth, without changing behaviour. **No feature added,
no backend removed, no UI rebuilt, no tab reordered.** `config["strategy"]` is
**retained as legacy compatibility.** Full suite after: **4173 pass / 6 skip /
0 fail** (38 new tests).

### What was built
- **`data/event_context.py` (NEW, pure Python — no PyQt6, no DB, no I/O)**:
  - `EventContext` — frozen dataclass, normalised field names, convenience
    (`is_timed`/`is_lap_race`/`tuning_locked`/`race_length_text`/`summary_line`/
    `to_summary_lines`/`to_dict`).
  - `EventContextSource` enum — EMPTY / DB_EVENT / LEGACY_STRATEGY / MERGED.
  - `EventContextValidationResult` + `validate_event_context()` — warnings, never
    exceptions (missing car/track, timed-without-duration, lap-without-laps,
    tuning-locked-but-categories-listed, no available tyres, empty context).
  - `build_event_context(event, strategy, active_event_id)` — DB-event-first
    resolution so an edited+saved event never returns a stale value; overlays
    `car` + `track_location_id`/`layout_id` from the strategy snapshot (the events
    table doesn't store them); falls back to strategy entirely when no DB record.
    Reconciles the two schemas (`tyre_wear`↔`tyre_wear_multiplier`,
    `duration_mins`↔`race_duration_minutes`, `refuel_rate_lps`↔`refuel_speed_lps`,
    `req_tyres`↔`required_tyres`). Never raises.
  - `compute_change_hash()` — deterministic 12-char marker over the canonical
    fields (change detection for future snapshot invalidation).
  - `flow_flags()` — bridge feeding `ui.product_flow.build_flow_state_summary`.
- **`docs/EVENT_CONTEXT_MIGRATION.md` (NEW)** — the `config["strategy"]`
  dependency register: the single fan-out writer (`_on_event_set_active`), all
  ~35 read sites with enclosing method + fields + risk, split into EVENT-CONFIG
  (migration candidates) vs NON-EVENT (StrategyContext/app-settings), and the
  migration + StrategyContext/SetupContext next-step plan.
- **`ui/dashboard.py`** — `_build_event_context()` helper (defensive; DB event +
  `config["strategy"]` + `active_event_id` → EventContext). **One low-risk
  consumer migrated**: `_refresh_telemetry_context()` reads event/car/track from
  EventContext (the DEF-P1-011 fuel-burn behaviour is unchanged and still
  source-scanned by `test_group11_ui_display_fixes.py`).

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_event_context.py` (NEW) | 38 | build sources (empty/db/legacy/merged); field-name normalisation for both schemas; timed-stays-timed & lap-stays-lap & singular "1 lap" & weird-token normalisation; BoP + tuning-locked/allowed + multipliers + refuel preserved; **DB-first beats stale strategy** + change-hash detects edits + deterministic hash; validation warnings without crashes + garbage-input safety; legacy strategy-only build; `flow_flags`→`build_flow_state_summary` interop; frozen immutability; `to_dict`/summary; dashboard source-scan (`_build_event_context` exists, `_refresh_telemetry_context` uses it and preserves avg_fuel_per_lap/'from telemetry') |

### Acceptance criteria — status
- Full suite passes — **yes (4173/6/0)**.
- EventContext exists + covered by tests — **yes**.
- `docs/EVENT_CONTEXT_MIGRATION.md` lists all `config["strategy"]` deps — **yes**.
- No working feature removed — **yes**.
- `config["strategy"]` retained; EventContext is the preferred read path — **yes**.
- ≥1 low-risk consumer reads from EventContext — **yes (`_refresh_telemetry_context`)**.
- Clear StrategyContext/SetupContext next plan — **yes (migration doc §6–§7)**.
- Behaviour unchanged except safer/clearer event handling — **yes**.

### Manual UAT steps
1. Set an event active (Event Planner → "Set as Active"). On the Telemetry tab,
   confirm Event / Car / Track show the same values as before.
2. Edit the active event's tyre-wear/fuel/laps and re-save; confirm no crash and
   displays remain consistent.
3. Switch between a timed event and a lap event; confirm the timed one still
   reads as timed and the lap one as a lap race everywhere they were before.
4. Confirm no behaviour changed in Setup Builder, Strategy Builder, Live tab,
   AI prompts, PTT/voice (all still read `config["strategy"]` this sprint).

### Next sprint
**State Consolidation 2 — StrategyContext**: owns `stops`/`fuel_burn_per_lap`/
`config_id`/ref-lap fields, reads event fields from EventContext, freezes a
prompt snapshot per AI call. Then SetupContext (diagnosis cache keyed on
`EventContext.change_hash`), migrate the low-risk read-only consumers, and remove
the `_on_event_set_active` fan-out. Also: render the home/overview panel via
`build_flow_state_summary(**flow_flags(ctx))`.

---

## State Consolidation 2 — StrategyContext (2026-07-03)

Second step of the target architecture from `docs/PRODUCT_CONSOLIDATION_AUDIT.md`
(§7); follows State Consolidation 1 — EventContext and depends on it. Creates a
canonical **StrategyContext** read model that owns *only* strategy-plan state and
**reads event/race rules from EventContext** rather than duplicating them, so the
two can never drift. **No feature added, no backend removed, no UI rebuilt, no
tab reordered.** `config["strategy"]` is **retained as legacy compatibility.**
Full suite after: **4226 pass / 6 skip / 0 fail** (53 new tests).

### What was built
- **`data/strategy_context.py` (NEW, pure Python — no PyQt6, no DB, no I/O)**:
  - `StrategyContext` — frozen dataclass owning `config_id`, `stint_plan`
    (`StintPlanEntry` tuple), `planned_stops`, `pit_laps`, `fuel_burn_per_lap`,
    optional `starting_fuel`/`fuel_margin`/`refuel_required`, `pit_loss_secs`,
    `degradation_consecutive_laps`, `tyre_degradation_available`,
    `lap_time_tolerance_ms`, `fuel_tolerance_liters`, `source`, `change_hash`
    (strategy fields only), `event_change_hash` (which event it was built
    against). Convenience: `has_active_strategy`/`total_planned_laps`/
    `has_fuel_burn`/`compound_sequence`/`summary_line`/`to_summary_lines`/`to_dict`.
  - `StintPlanEntry` — frozen; `to_dict()` round-trips back to the legacy
    `stops` dict shape (`{laps, compound, ref_lap_ms, pace_threshold_ms}`) so
    existing engine code (`Stint.from_dict`) is unaffected.
  - `StrategyContextSource` enum — EMPTY / LEGACY_STRATEGY / GENERATED.
  - `StrategyContextValidationResult` + `validate_strategy_context()` — keeps
    `strategy_warnings`/`strategy_missing` **separate** from `event_warnings`/
    `event_missing` (folds in `validate_event_context` when an EventContext is
    supplied). Warnings, never exceptions.
  - `StrategyPromptSnapshot` + `build_strategy_prompt_snapshot()` — a
    value-copied freeze of a consistent EventContext race config + StrategyContext
    plan for AI race-plan prompts; stays stable even if `config["strategy"]` is
    mutated afterwards. `snapshot_id` = stable hash of
    `(event_change_hash, strategy_change_hash)`.
  - `build_strategy_context(strategy, event_context, tyre_degradation, source)` —
    reads strategy fields from `config["strategy"]`, **ignores** event fields in
    that dict (they belong to EventContext), records only the event's
    `change_hash`. Never raises; EMPTY on missing/garbage input.
  - `compute_change_hash()` — deterministic 12-char marker over the **strategy**
    fields only (event changes tracked separately via `event_change_hash`).
- **`docs/STRATEGY_CONTEXT_MIGRATION.md` (NEW)** — ownership boundary table
  (rate-vs-number split: `mandatory_stops`/`refuel_rate_lps` stay EventContext;
  *planned* stops + pit laps are StrategyContext); every strategy-specific
  `config["strategy"]` field with writer/readers; migrated + deferred consumers;
  risks; SetupContext next-step plan.
- **`ui/dashboard.py`** — `_build_strategy_context()` helper (defensive;
  `config["strategy"]` + `_build_event_context()` + `_tyre_degradation_cache` →
  StrategyContext). **One low-risk consumer migrated**: `_refresh_lap_bank()`
  reads the active `config_id` from StrategyContext for the practice-lap-bank ★
  marker.

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_strategy_context.py` (NEW) | 53 | build sources (empty/legacy/generated-override); strategy fields preserved (config_id, fuel burn, stint-plan parse, planned-stops + pit-laps derivation incl. 3-stint/2-stop, degradation fields + default, tolerances, optional fuel fields present/absent); **ownership boundary** (no event/race attributes; event fields in the strategy dict ignored; event read from EventContext via `event_change_hash`); change markers (identical→same hash; plan/fuel edits change it; **strategy hash ignores event fields**; **event hash changes independently while strategy hash stays**; deterministic); robustness (garbage/malformed stints/None don't crash); validation **strategy-vs-event separation** (missing plan/fuel = strategy; missing car = event; combined `.warnings`); frozen prompt snapshot (combines event+strategy; stable id; **stays frozen when legacy config mutates later**; id changes on event or strategy change; defensive without event_context; to_dict); serialisation + immutability (frozen context + frozen stint entry); legacy round-trip (config_id/fuel-burn match legacy reads, stops→dict round-trip); dashboard source-scans (`_build_strategy_context` helper + `_refresh_lap_bank` migration) |

### Acceptance criteria — status
- Full suite passes — **yes (4226/6/0)**.
- StrategyContext exists + covered by tests — **yes**.
- EventContext remains the canonical owner of event/race config — **yes** (StrategyContext reads it, owns no event field).
- StrategyContext owns only strategy-plan state — **yes** (ownership-boundary tests enforce it).
- `config["strategy"]` retained for compatibility — **yes**.
- `docs/STRATEGY_CONTEXT_MIGRATION.md` exists and is specific — **yes**.
- ≥1 low-risk read-only consumer migrated — **yes (`_refresh_lap_bank` config_id ★)**.
- No working feature removed; no tab reordered; no track mapping / Setup Brain change — **yes**.
- Behaviour unchanged except safer/clearer strategy-state handling — **yes**.
- Clear next-sprint recommendation (SetupContext keyed on EventContext.change_hash + StrategyContext snapshot identity) — **yes (migration doc §9)**.

### Manual UAT steps
1. Build/apply a stint plan in Strategy Builder, then open the Practice Lap Bank
   (filter by Track + Car): confirm sessions recorded under the current race
   config still show the ★ marker exactly as before.
2. Change the active event (which recomputes `config_id`): confirm the ★ marker
   follows the new config with no crash.
3. Confirm no behaviour changed in Strategy Builder analysis, Live race panel,
   AI strategy prompts, PTT/voice (all still read `config["strategy"]` this
   sprint — only the lap-bank marker was migrated).

### Next sprint
**SetupContext** keyed on `EventContext.change_hash` **and**
`StrategyPromptSnapshot.snapshot_id`: owns the current setup + cached setup
diagnosis, reads legality from EventContext and plan assumptions from
StrategyContext, invalidates the cache when either hash changes. Then migrate the
deferred AI-input consumers (`_assemble_strategy_inputs`/`_run_ai_analysis`/
`_launch_replan_worker`) to the frozen `StrategyPromptSnapshot`, and remove the
`config["strategy"]` fan-out once every consumer reads a context.

---

## State Consolidation 3 — SetupContext (2026-07-03)

Third step of the target architecture from `docs/PRODUCT_CONSOLIDATION_AUDIT.md`
(§7); follows State Consolidation 1 — EventContext and 2 — StrategyContext and
depends on both. Branch `state-consolidation-3-setup-context` (the three prior
consolidation sprints were committed as `1dca4a5` on
`fix/def-17u-uat007-timetrial-calibration` first). Creates a canonical
**SetupContext** read model that owns *only* setup-recommendation state and is
**keyed** to `EventContext.change_hash` and `StrategyPromptSnapshot.snapshot_id`
so a setup built against one event/strategy can be detected as stale under
another. **No feature added, no backend removed, no UI rebuilt, no tab reordered,
no live PTT/voice change.** Legacy setup config/DB storage is **retained as
compatibility.** Full suite after: **4293 pass / 6 skip / 0 fail** (67 new tests).

### What was built
- **`data/setup_context.py` (NEW, pure Python — no PyQt6, no DB, no I/O, no AI)**:
  - `SetupContext` — frozen dataclass owning `setup_id`/`config_id`/`setup_label`,
    `purpose`, `source`, `car`/`track`/track ids (setup is *for* a car+track;
    read from the setup dict, falling back to EventContext), `adjustments`
    (`SetupChangeEntry` tuple), `changed_fields`, frozen `baseline_setup` /
    `target_setup` (value-copied item tuples with dict accessors), `reason_summary`,
    `primary_issue`, `confidence`, `validation_warnings`, `applied`, `change_hash`
    (setup fields only), and the `event_change_hash` / `strategy_snapshot_id` /
    `telemetry_diagnosis_hash` keys it was built against. Keying helpers
    `matches_event` / `is_stale_for_event` / `is_stale_for_strategy` /
    `is_missing_identity` / `matches_purpose`; display `summary_line` /
    `to_summary_lines` / `to_dict`.
  - `SetupChangeEntry` — frozen; `to_dict()` round-trips the AI `changes` shape
    (`{field, from, to, why}`); `_parse_adjustments` accepts `setting`/`field`
    aliases and skips malformed rows.
  - `SetupContextSource` enum — EMPTY / AI / GENERATED / MANUAL / SAVED_DB /
    LEGACY_CONFIG (inferred: recommendation → AI; setup_id → SAVED_DB; else MANUAL).
  - `SetupPurpose` enum — QUALIFYING / RACE / PRACTICE / TEST / UNKNOWN;
    `normalise_purpose()` maps "Qualifying Setup"/"Race Setup", history
    `build_qual`/`build_race`, or free text; never raises.
  - `SetupContextValidationResult` + `validate_setup_context()` — keeps
    `setup_warnings`/`setup_missing` **separate** from `staleness_warnings`
    (event drift, strategy drift, purpose mismatch). `.warnings` concatenates.
  - `SetupPromptSnapshot` + `build_setup_prompt_snapshot()` — a value-copied
    freeze of the setup recommendation with the event + strategy keys it was
    built against; stays stable even if the source setup dict / config mutates
    later; `snapshot_id` = stable hash of the event + strategy + setup + diagnosis
    change markers. **Exists for a future AI-setup-prompt migration; the
    high-risk prompt paths are NOT migrated this sprint.**
  - `build_setup_context(setup, recommendation, event_context, strategy_snapshot,
    diagnosis, purpose, source, applied)` — reads event/strategy fields only as
    `change_hash` / `snapshot_id` keys (never copied as owned state); never raises;
    EMPTY on missing/garbage input.
  - `compute_change_hash()` — deterministic 12-char marker over the **setup**
    fields only (event/strategy tracked via their own hashes).
- **`docs/SETUP_CONTEXT_MIGRATION.md` (NEW)** — every setup store (config
  `car_setup.setups`; DB `setups` / `setup_recommendations` / `setup_snapshots` /
  `lap_records.setup_id`; the AI response payload; diagnosis + `setup_history`)
  with writers/readers, the ownership boundary, what was migrated, deferred
  consumers, stale/prompt/validation risks, and the TrackContext/AI-input next plan.
- **`ui/setup_builder_ui.py`** — `_build_setup_context()` helper (defensive;
  `_current_setup_dict()` + `_build_event_context()` + a `StrategyPromptSnapshot`
  → SetupContext). **Migrated**: `_setup_type_prefix()` derives the Q/R purpose via
  `normalise_purpose` / `SetupPurpose.QUALIFYING`; `_display_setup_result()`
  captures the canonical `SetupContext` into `self._last_setup_context` (read-only
  and additive — no change to the displayed HTML, history save, or apply button).

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_setup_context.py` (NEW) | 67 | `normalise_purpose` (qual/race/practice/test/unknown/enum/garbage); build sources (empty/saved_db/manual/ai/overrides); setup fields preserved (identity, purpose-from-setup_type, adjustments parse, changed-fields union, baseline+target dicts, reason/confidence/primary_issue, validation warnings, applied, explicit purpose); **ownership boundary** (no event/race attrs, no strategy-plan attrs, event via change_hash only, strategy via snapshot_id only, to_dict excludes them); **qualifying-vs-race distinguishable** (+ different change_hash, matches_purpose); keying & staleness (matches_event; **stale when event change_hash changes**; **stale when strategy snapshot_id changes**; empty never stale; missing identity; setup hash changes on recommendation change; **setup hash ignores event/strategy**; diagnosis hash; deterministic); robustness (garbage/malformed changes/None/bad setup_id/validate never raise); validation **setup-vs-staleness separation** (empty, missing identity, unknown purpose, stale event → staleness not setup, stale strategy, purpose mismatch, combined `.warnings`); frozen prompt snapshot (combines setup+event+strategy keys, stable id, **stable after legacy mutation**, id changes on event/setup change, to_dict); serialisation + immutability (frozen context + frozen change entry) + legacy setup-dict compat; setup_builder source-scans (`_build_setup_context` helper, `_setup_type_prefix` uses normalise_purpose, `_display_setup_result` captures `_last_setup_context`) |

### Acceptance criteria — status
- Full suite passes — **yes (4293/6/0)**.
- SetupContext exists + covered by tests — **yes**.
- EventContext remains canonical owner of event/race config — **yes** (SetupContext reads it only as a key).
- StrategyContext remains canonical owner of strategy-plan state — **yes** (read only via snapshot_id).
- SetupContext owns only setup-recommendation state — **yes** (ownership-boundary tests enforce it).
- Legacy setup config/DB storage retained — **yes**.
- `docs/SETUP_CONTEXT_MIGRATION.md` exists and is specific — **yes**.
- ≥1 low-risk read-only consumer migrated — **yes (`_setup_type_prefix` purpose; `_display_setup_result` captures the context)**.
- No working feature removed; no tab reordered; no track mapping; no PTT/voice change — **yes**.
- Behaviour unchanged except safer/clearer setup-state handling — **yes**.
- Clear next-sprint recommendation — **yes (TrackContext, or migrate deferred AI-input consumers to frozen snapshots; migration doc §9)**.

### Manual UAT steps
1. In Setup Builder, switch the setup type between Race and Qualifying and save a
   setup: confirm the auto-generated name prefix is still `R`/`Q` exactly as before.
2. Run "Analyse & Get Setup Fix": confirm the analysis, changes list, diagnosis
   banner, validation banners, and Apply button behave exactly as before (the new
   `_last_setup_context` capture is invisible).
3. Confirm no behaviour changed in Build Setup with AI, apply/save, Garage setups,
   History, live PTT/voice (all still read the legacy stores this sprint).

### Next sprint
Either **TrackContext** (unify track/layout SSOT-2; owns reference path / station
map / corner-segment model / seed geometry / track-truth; SetupContext and
StrategyContext read corner context from it) **or** migrate the deferred
AI-input consumers to frozen snapshots (`build_setup_advice_response` /
`build_combined_setup_response` / `_assemble_strategy_inputs` / `_run_ai_analysis`
threading EventContext + StrategyPromptSnapshot + SetupPromptSnapshot, proving
prompts unchanged) and then surface the stale-setup indicator from
`_last_setup_context`. **Recommended: TrackContext first.**

---

## State Consolidation 4 — TrackContext (2026-07-03)

Fourth step of the target architecture from `docs/PRODUCT_CONSOLIDATION_AUDIT.md`
(§7); follows State Consolidations 1–3 and targets **SSOT-2** ("track/layout
split three ways"). Branch `state-consolidation-4-track-context` (from
`state-consolidation-3-setup-context` @ `d9c6231`). Creates a canonical
**TrackContext** read model owning *only* track/layout identity + model-artefact
availability + status, keyed to `EventContext.change_hash`. **No track mapping
feature added, no UI rebuilt, no tab reordered, no persistence format changed,
no PTT/voice change, no Daytona geometry accuracy claims.** All legacy track
seed/library/reference-path/station-map/resolver/calibration code is **retained
unchanged.** Full suite after: **4361 pass / 6 skip / 0 fail** (68 new tests).

### What was built
- **`data/track_context.py` (NEW, pure Python — no PyQt6, no UI, no DB, no
  network/AI, no file I/O)**:
  - `TrackIdentity` — frozen; `track_location_id`/`layout_id` + display names +
    `combined_id` (`<loc>__<lay>`, matching every per-layout file convention) +
    `is_complete`.
  - `TrackMapAvailability` — frozen; seed metadata / lap-length / corner-window /
    sector / complex / **coordinate-geometry** availability + `seed_source`
    (track_library/legacy_fallback/none) + reference path (with point count) /
    calibration laps / station map (with station count) / reviewed model /
    accepted model / lap offset. **Every flag echoes what the existing audits
    said — True means "artefact exists / validator accepted", never "geometry
    is accurate".**
  - `TrackGeometryStatus` — frozen; `modelling_status` (resolver value wins,
    seed fallback), `ai_ready`, resolver `resolution_status` +
    `model_source_type`, `corners_expected`, seed/model lap lengths, and the
    three Track Truth gates **echoed tri-state** (None = no validation run).
  - `TrackAlignmentStatus` — frozen; `available` (requires an alignment-shaped
    object — garbage never reads as a computed alignment), match status,
    accepted (+at), lap delta, blocker/warning counts, corner position match.
  - `TrackContextSource` — EMPTY / TRACK_MODELLING_UI / EVENT_CONTEXT /
    LEGACY_STRATEGY / SEED_LIBRARY. Identity resolution priority: explicit TM
    combo selection → EventContext ids → `config["strategy"]` ids → seed objects.
  - `TrackContext` — the above + lap-offset status
    (not_loaded/provisional_zero/calibrated/on_disk_not_loaded) + confidence +
    `change_hash` (identity+availability+status **only** — event drift tracked
    separately via `event_change_hash`). Staleness/mismatch helpers:
    `matches_event` (**tri-state** — None when no comparable identity),
    `mismatches_event` (True only on a possible-and-failing comparison),
    `is_stale_for_event`, `can_attempt_live_mapping` (conservative: identity +
    station map, says nothing about accuracy), `live_mapping_blockers()`.
  - `TrackContextValidationResult` + `validate_track_context()` — keeps
    `identity_warnings`/`identity_missing` separate from
    `availability_warnings` (what's absent) and `staleness_warnings` (event
    mismatch/drift). Warnings, never exceptions.
  - `build_track_context(...)` — duck-typed over the results the **existing**
    loaders already produce (`SeedAuditResult`, `TrackModelFileAudit`,
    `TrackModelResolverResult`, `TrackModelAlignmentResult`,
    `LapStartOffsetCalibration`, `TrackTruthValidationResult`, seed objects,
    station map object or bare flag). Never raises; EMPTY on garbage.
  - `flow_flags(ctx)` — **splat-safe** `ui.product_flow` bridge (returns only
    accepted kwargs) composable with `event_context.flow_flags` via dict merge.
- **`docs/TRACK_CONTEXT_MIGRATION.md` (NEW)** — the §7 SSOT audit: all 16 track
  state items (selected track/layout, TM combo state, display names, seed
  metadata/windows/coordinate map, reference path, station map, reviewed model,
  accepted model, lap offset, alignment result, live map-matching identity,
  Track Truth, modelling status) with current owner, files:lines, duplication
  verdict and future owner; every file format (unchanged); migrated + deferred
  consumers; stale-model / alignment / library / identity-fallback risks; next
  sprint.
- **`ui/track_modelling_ui.py`** — `_build_track_context()` helper (assembles
  from combo ids + loaded seed layout + the same `audit_layout_seed` /
  `audit_track_model_files` audits the tab already runs on layout change +
  `_tm_station_map` / `_tm_alignment_result` / `_tm_offset_calibration` +
  `_build_event_context()`; read-only; never raises). **Migrated**:
  `_tm_refresh_track_truth_panel()` reads track/layout identity through
  TrackContext and captures `self._last_track_context`. **Strictly
  behaviour-preserving** — only a combo-sourced identity
  (`TrackContextSource.TRACK_MODELLING_UI`) drives the panel, so an empty combo
  selection keeps showing the empty state (the context's event/config fallback
  is deliberately not used there).

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_track_context.py` (NEW) | 68 | identity resolution (**UI combos beat config**, builds from EventContext identity, from legacy strategy ids, seed-only, name-only weak identity, combined_id); availability (seed metadata/windows/count/source; **seed geometry absent stays False — Daytona-style honesty**; ref path ± / calibration laps / station map via flag AND via object / reviewed / accepted; all-false when nothing supplied); geometry status (seed modelling status, **resolver value wins**, tri-state truth gates None-when-absent and **echoed-False when validation blocked**); alignment (represented / unavailable / accepted / **garbage string not available**); lap offset (not_loaded / provisional_zero / calibrated / on_disk_not_loaded); change markers (identical→same; changes on identity/availability/alignment; **ignores event change — tracked via event_change_hash**; deterministic); staleness/mismatch (tri-state matches_event by ids, mismatch, **None when uncomparable**, display-name fallback, is_stale_for_event, live-mapping gate + blockers incl. no-identity); ownership boundary (no event/strategy/setup fields; event read only as change_hash; to_dict excludes them); robustness (garbage/None everything, validate on junk, **broken station_count() defensive**); validation separation (empty; missing layout = identity; missing data = availability; event mismatch = staleness; `.warnings` concatenation; **missing-geometry warning persists even when everything else is accepted**); serialisation + summary lines + **splat-safe flow_flags into build_flow_state_summary** + frozen immutability (ctx + all sub-structures); track_modelling source-scans (`_build_track_context` helper reads event ctx + volatile state + audits; truth panel uses ctx identity + captures `_last_track_context` + combo-source guard; **legacy combo→config fan-out intentionally unchanged**) |

### Acceptance criteria — status
- Full suite passes — **yes (4361/6/0)**.
- TrackContext exists + covered by tests — **yes**.
- EventContext / StrategyContext / SetupContext remain canonical owners of their state — **yes** (ownership-boundary tests enforce; TrackContext reads the event only as a key).
- TrackContext owns only track/layout/map/corner/segment identity + availability state — **yes**.
- Legacy track modelling, seed, reference path, station map, resolver, calibration code compatible — **yes (untouched; regression suite green)**.
- `docs/TRACK_CONTEXT_MIGRATION.md` exists and is specific — **yes (16-item SSOT audit with file:line)**.
- ≥1 low-risk read-only consumer migrated — **yes (`_tm_refresh_track_truth_panel` identity + `_last_track_context` capture)**.
- No working feature removed; no tab reordered; no new track mapping feature; no PTT/voice change — **yes**.
- No Daytona geometry accuracy claims — **yes (test-enforced: geometry stays unavailable, truth gates echo False, validation keeps warning)**.
- Behaviour unchanged except safer/clearer track-state handling — **yes**.
- Clear next-sprint recommendation — **yes (AI Snapshot Migration, or Home Dashboard Build; migration doc §8)**.

### Manual UAT steps
1. Open the ⚙ Track Modelling tab, select Daytona → Road Course: confirm the
   Track Truth / Mapping panel shows exactly the same values as before
   (Daytona still blocked — no seed geometry).
2. Clear the layout selection (pick "— Select layout —"): confirm the truth
   panel returns to its empty "—" state exactly as before.
3. Build/load a station map and run alignment: confirm the alignment panel and
   accept-button behaviour are unchanged.
4. Confirm live map dot, calibration capture, segment detection, lap offset
   buttons and all AI features behave exactly as before (none were migrated).

### Next sprint
**AI Snapshot Migration** — thread frozen `EventContext` +
`StrategyPromptSnapshot` + `SetupPromptSnapshot` + a TrackContext snapshot into
the AI-input paths (`_run_practice_analysis`, `_assemble_strategy_inputs`,
`_run_ai_analysis`, `build_setup_advice_response`,
`get_track_context_for_ai`), proving prompts byte-identical before/after, then
surface the captured stale indicators (`_last_setup_context`,
`_last_track_context`). Alternative first step: **Home Dashboard Build** —
render the missing home/overview panel from
`build_flow_state_summary(**{**event_flags, **track_flags, …})`, which now has
real inputs from all four contexts.

---

## AI Snapshot Migration — Frozen Context Inputs (2026-07-03)

Follows State Consolidations 1–4 and consumes all four read models. Branch
`ai-snapshot-migration-context-freeze` (from `state-consolidation-4-track-context`
@ `45b48d5`). Threads **frozen, owner-documented snapshots** into the AI-input
preparation paths so prompts receive consistent, non-stale, non-mixed state.
**A migration/safety sprint: no prompt wording changed, no setup/strategy
intelligence changed, no track mapping change, no PTT/voice change, no tab
reordered, no legacy store removed.** Full suite after: **4402 pass / 6 skip /
0 fail** (41 new tests; 20 legacy source-scan tests updated in place).

### What was built
- **`data/ai_context_snapshot.py` (NEW, pure Python — no PyQt6/UI/network/AI/DB/file-I/O)**:
  - `AIContextSnapshot` (frozen core) — combined `snapshot_id` (stable hash of
    payload + component markers), the four component keys (`event_change_hash`,
    `strategy_change_hash`, `setup_snapshot_id`, `track_change_hash`), `source`
    (CONTEXTS / LEGACY_ONLY / EMPTY), build `warnings` + `stale_warnings`;
    `validate_ai_context_snapshot()`.
  - `StrategyAISnapshot` + `build_strategy_ai_snapshot()` — frozen `race_params`
    for `_assemble_strategy_inputs`/`_run_ai_analysis` (feeds `RaceParams(**…)`)
    + `config_id` (StrategyContext). `fuel_burn_override` carries the
    telemetry-derived `_computed_fuel_burn_lpl()` where the legacy path used it.
  - `PracticeAnalysisSnapshot` + `build_practice_analysis_snapshot()` — same
    shape, kept distinct because the practice path's **DEF-P1-005 safe default
    (unknown tuning flag → LOCKED)** differs from the strategy paths' unlocked
    default; both regimes preserved exactly.
  - `SetupAISnapshot` + `build_setup_ai_snapshot()` — the 17 event/track fields
    the setup AI paths need, preserving the **build-setup legacy defaults
    (refuel/pit-loss 0.0**, unlike the strategy paths' 10.0/23.0).
  - Field owners documented per input: event/race truth → EventContext;
    fuel burn (non-override)/pit loss/config_id → StrategyContext; track ids →
    TrackContext; setup identity → SetupPromptSnapshot; telemetry fuel burn →
    caller-supplied (TelemetryContext sprint later).
  - Staleness detected at build: strategy-built-against-older-event,
    setup-generated-for-previous-event, Track-Modelling-vs-event mismatch.
  - `LEGACY_ONLY` fallback evaluates the **exact legacy expressions** and
    records a warning — never silent when a clean context exists. Builders
    never raise.
- **`docs/AI_SNAPSHOT_MIGRATION.md` (NEW)** — all 11 AI prompt/input paths with
  pre-sprint sources and migrated/deferred status, per-input owners, the
  byte-identity proof list, the 4 documented intentional differences, the 20
  updated legacy tests, remaining legacy dependencies, next sprint.
- **`ui/dashboard.py`** — `_build_strategy_ai_snapshot()` /
  `_build_practice_ai_snapshot()` helpers (thread `_build_event_context()` +
  `_build_strategy_context()` + `_build_track_context()` + legacy dict; never
  raise). **Migrated:** `_assemble_strategy_inputs` (also serving the mid-race
  re-plan via `_launch_replan_worker`), `_run_ai_analysis` (race_params +
  `config_id` from the snapshot), `_run_practice_analysis` (race_params; the
  GT7_AI_DEBUG stdout line now shows snapshot id/source + stale warnings —
  debug-only surfacing, no UI change).
- **`ui/setup_builder_ui.py`** — `_build_setup_ai_snapshot()` helper (also
  threads the captured `_last_setup_context` as a `SetupPromptSnapshot`).
  **Migrated:** `_run_build_setup` (16 scattered `config["strategy"]` event
  reads → one frozen snapshot; the worker thread's recommendation metadata now
  uses the frozen track/layout — the mid-flight config re-read is removed),
  `_setup_analyse_ai` (allowed/locked/mandatory-compounds).

### Byte-identical prompt proof
`tests/test_ai_context_snapshot.py` captures the pre-migration expressions
**verbatim** and proves race-params equality for: full synced state, fuel-burn
override, lap race, BoP+locked, no-DB-event (legacy-strategy-only context),
absent-key defaults (25 laps / 10.0 refuel / 23.0 pit / 2.0 burn), present-zero
preservation (0 never replaced by a default), practice tuning-absent → locked,
strategy tuning-absent → unlocked, and the setup-path defaults ("Unknown" car,
0.0/0.0, empty compounds string) — plus **`test_prompt_text_byte_identical`**
on the real `_build_race_prompt` output.

### Intentional differences (each with a focused test)
1. **Fresh DB event supersedes a stale fan-out copy** (the migration's purpose)
   — `test_edited_db_event_supersedes_stale_config`.
2. **Practice tuning flag: DB truth over the blind locked default** when the
   config key is missing but a DB event exists —
   `test_practice_tuning_absent_but_db_event_present_uses_db_truth`
   (absent-everywhere still → LOCKED, DEF-P1-005 preserved).
3. GT7_AI_DEBUG stdout format (debug print only, never prompt text).
4. Build-setup `race_laps` is now always `int` (legacy passed the raw config
   value uncast; same value for every real config).

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_ai_context_snapshot.py` (NEW) | 41 | golden byte-identity (verbatim legacy expressions vs snapshots, 13 scenarios incl. prompt-text); snapshot semantics (schema/source, id stable, id changes per **each** of the four contexts, frozen-after-legacy-mutation, garbage safety, EMPTY source, to_dict); legacy fallback (matches legacy expressions exactly, practice default, setup inputs); staleness (stale strategy vs event, stale setup vs event, track/event mismatch, no false staleness when synced, validation flags LEGACY_ONLY); source scans (migrated methods route through snapshots and contain **no direct config event-field reads**; dashboard + setup_builder helpers thread the contexts; build-setup worker uses frozen track ids) |
| Updated in place (20 tests) | — | `test_group7` (BoP context), `test_group10` (tuning_locked derivation), `test_group12a` (DEF-P1-005 default), `test_group15` (DEF-P1-013 / DEF-P2-038 / DEF-P2-039 race-param fields), `test_group2` (tyre-wear source), `test_group36` AC8 (runtime stubs now route through the real snapshot builder; session-id invariants still exercise the real `_assemble_strategy_inputs`). Every update guards the SAME invariant behaviourally at its new home. |

### Acceptance criteria — status
- Full suite passes — **yes (4402/6/0)**.
- AI snapshot module exists + covered by tests — **yes**.
- Event/Strategy/Setup/Track contexts remain canonical owners — **yes** (snapshot documents the owner of every value).
- Migrated AI-input paths read from frozen snapshots — **yes (5 paths)**.
- Prompt output byte-identical where equivalent data exists — **yes (proven)**; intentional differences documented + tested — **yes (4)**.
- Legacy config compatibility intact; no store removed — **yes**.
- No feature removed / tab reordered / track mapping / intelligence change — **yes**.
- `docs/AI_SNAPSHOT_MIGRATION.md` exists and is specific — **yes**.
- Remaining legacy AI-input dependencies documented — **yes (§7 of the doc)**.
- Clear next-sprint recommendation — **yes (Home Dashboard Build)**.

### Manual UAT steps
1. Set an event active, tag practice laps, run **Full Practice Analysis** with
   `GT7_AI_DEBUG=1`: the dry-run prompt in the AI Log must show the same race
   parameters as before; stdout shows the snapshot id/source line.
2. Run **Race Strategy Analysis**: identical prompt inputs (track, laps/duration,
   wear/fuel multipliers, BoP/tuning, tyres) in the AI Log prompt view.
3. Edit the active event (e.g. tyre wear) WITHOUT re-clicking "Set as Active",
   run an analysis: the prompt now reflects the fresh DB value (intentional).
4. **Build Setup with AI** and **Analyse & Get Setup Fix**: unchanged behaviour;
   recommendations still save with correct track/layout metadata.
5. Confirm PTT/voice, live map, calibration and all non-AI features unchanged.

### Next sprint
**Home Dashboard Build** — render the missing home/overview panel from
`build_flow_state_summary(**{**event_flags, **track_flags, …})` and surface the
now-available staleness indicators (`AIContextSnapshot.stale_warnings`,
`_last_setup_context`, `_last_track_context`) as display-only status rows.
Afterwards: TelemetryContext (fuel-burn/lap-stats ownership), then remove the
`_on_event_set_active` + Track Modelling combo fan-outs once every consumer
reads a context.

---

## Home Dashboard Build — Race Engineer Command Centre (2026-07-03)

> Branch `home-dashboard-command-centre` (from `ai-snapshot-migration-context-freeze`
> @ `f8e9a9d`). Full doc: `docs/HOME_DASHBOARD_BUILD.md`.
> **Full suite: 4454 pass / 6 skip / 0 fail** (52 new tests).

### What was built
The Dashboard/home tab specified in `REQUIREMENTS.md §12.2` and found missing by
the Product Consolidation Audit (§1.1). **Display-only** — it reads the four
canonical contexts and owns/mutates no domain state; no race/setup/strategy/
track-mapping/calibration/AI-prompt/PTT/voice logic changed; no tab reordered
or removed.

- **`ui/home_dashboard_vm.py` (NEW, pure Python)** — no PyQt6/AI/DB/network/
  file-I/O (source-scanned). `build_home_dashboard_state()` (never raises;
  garbage-safe per section) → `HomeDashboardState` with five cards
  (Race Setup, Track Intelligence, Setup Brain, Strategy Brain, AI Input
  Safety) + `HomeDashboardNextAction` from `product_flow.build_flow_state_summary()`.
  `build_flow_flags()` derives the gate booleans from the contexts
  (event/car/track/tuning from EventContext + TrackContext identity override;
  `has_setup` = SetupContext active; `has_strategy` = a stint plan exists —
  a bare config does not satisfy the gate; telemetry flags caller-supplied).
  `format_card_html()`/`format_next_action_html()` pure renderers with escaping.
- **`ui/dashboard.py`** — Home tab **appended at index 13** (indices 0–12 and
  every `_on_tab_changed` dispatch unchanged — pinned by source-scan);
  `_build_home_tab` (next-action banner + five card labels + Refresh button),
  `_build_home_dashboard_state` (reads `_build_event_context` /
  `_build_strategy_context` / `_build_track_context` / `_last_setup_context` /
  `_build_strategy_ai_snapshot` — the snapshot build is pure computation, no
  AI call), `_home_has_practice_laps` (read-only DB query), `_home_refresh`,
  `_home_refresh_if_visible` (no-op unless Home is the current tab).
- **Refresh hooks (no polling / workers / signals)** — tab-shown; Refresh
  button; end of `_on_event_set_active`; end of `_update_race_config`; end of
  `_display_setup_result` (setup_builder_ui, hasattr-guarded); end of
  `_tm_refresh_track_truth_panel` (track_modelling_ui, hasattr-guarded).
- **`ui/product_flow.py`** — "Home" registered as a workflow tab (diagnostic
  set unchanged).
- Documented approximations: `has_valid_laps` = recorded laps exist;
  `live_active` = telemetry connected (proper truth deferred to a
  SessionContext/TelemetryContext sprint).

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_home_dashboard_vm.py` (NEW) | 52 | empty state; event-only; incomplete event warnings; fresh/stale strategy vs event; plan-less strategy; uncalibrated fuel; fresh setup matching current event; stale setup vs event; stale setup vs strategy snapshot; setup missing identity; full track data ready; missing track identity; seed metadata without geometry; station map unavailable → live mapping blocked; track-vs-event mismatch; AI snapshot clean / legacy fallback / stale / bare-core / missing; next-best-action ordering across the whole journey + progress partition + plan-required strategy gate; no developer jargon in any display string; stale wording matches the spec examples; never-raises on garbage in every slot incl. attribute-raising objects; HTML escaping; source-scans (Home appended after tab 12, original addTab lines + `_on_tab_changed` dispatches unchanged, diagnostic tabs present, home reads from canonical contexts, home methods write no state, hooks guarded, no QTimer/QThread/worker, VM import purity) |

### Acceptance criteria — status
- Full test suite passes — **yes (4454/6/0)**.
- Home Dashboard visible in the app — **yes (Home tab, index 13)**.
- Built from canonical contexts + `build_flow_state_summary()` — **yes**.
- Shows event / strategy / setup / track / AI snapshot / warnings / next action — **yes**.
- Display-only, owns/mutates no domain state — **yes (source-scanned)**.
- No tab reordered / diagnostic tab removed — **yes (source-scanned)**.
- No setup/strategy/track-mapping/AI-prompt/PTT/voice/live change — **yes**.
- View-model tests + safe UI integration tests — **yes (52)**.
- `docs/HOME_DASHBOARD_BUILD.md` exists and is specific — **yes**.
- Clear next-sprint recommendation — **yes (Diagnostic Tab Cleanup, or Legacy
  Fan-Out Removal Phase 1 as the higher-risk alternative)**.

### Manual UAT steps
1. Launch the app → open the **Home** tab (last tab). Cards render; with no
   active event every card reads "Not set up yet" and the banner suggests
   creating an event in Event Planner.
2. Set an event active in Event Planner → return to Home (or keep it open):
   Race Setup card shows the event summary; next action advances.
3. Edit the active event (e.g. laps) and re-save WITHOUT rebuilding the
   strategy → Home shows "Strategy plan was built before the current event
   settings changed." once a plan exists.
4. Display a setup recommendation in Setup Builder → Setup Brain card shows
   label/purpose/source/changes; change the event → stale warning appears.
5. Confirm tab order: all 13 original tabs unchanged, Home appended last;
   Telemetry/Diagnostics/AI Log/Track Modelling still present with ⚙ markers.
6. Confirm the Home tab never blocks any workflow (informational only).

### Next sprint
**Diagnostic Tab Cleanup** (audit §9 items 1–4: delete the 7 hidden legacy
per-segment buttons + handlers, Strategy Builder API-key defers to Settings,
hide/rename "Race Config ID", move the Guide's telemetry byte reference,
Diagnostics wording pass) — or **Legacy Fan-Out Removal Phase 1** (begin
retiring the `_on_event_set_active` → `config["strategy"]` fan-out behind the
now-complete context layer) as the higher-value / higher-risk alternative.

---

## Diagnostic Tab Cleanup — Low-Risk UI Dags Removal (2026-07-03)

> Branch `diagnostic-tab-cleanup-ui-dags` (from `home-dashboard-command-centre`
> @ `d96b967`). Full doc: `docs/DIAGNOSTIC_TAB_CLEANUP.md`.
> **Full suite: 4479 pass / 6 skip / 0 fail** (25 new tests).

### What was done
Low-risk UI cleanup executing the audit's §9 items 1/3/4. The entire diff is
deletions of dead UI, label text and Guide HTML — **no logic, prompt, mapping,
PTT/voice, persistence, tab-order or fan-out change** (pinned by source-scans).

- **7 legacy per-segment review buttons DELETED** (`ui/track_modelling_ui.py`):
  the Confirm/Rename/Reject/Needs More Laps/Split Required/Merge Required/
  Save Reviewed Model buttons were hidden at creation AND never
  `clicked.connect`-ed, so the 7 `_tm_review_*` handlers were unreachable.
  Deleted: widgets + save-path label, 4 never-applied style strings,
  `_tm_refresh_review_buttons` (+2 call sites), the no-op
  `_tm_refresh_approval_panel` (+1 call site), the 7 handlers, and 8
  now-unused imports. **Retained:** the pure review-action functions in
  `data/track_segment_review.py` + `ui/track_modelling_vm.get_review_button_states`
  (own coverage in `test_group17f`/`test_group17m`; import test proves intact).
- **`_TELEMETRY_REFERENCE_HTML` DELETED** (`ui/dashboard.py`, ~143 lines):
  dead code — defined but never rendered anywhere (the audit thought it was
  embedded in the Guide; it wasn't).
- **Renames:** "Race Config ID:" → **"Session Match Key:"** (+ plain-English
  tooltip; value/`config_id` mechanics untouched); Diagnostics "Rem(clk):" →
  "Time left:", "rem_ms(raw):" → "remaining_time_ms:" (matches the raw-field
  row's real field names), "Ann queue:" → "Voice queue:" (creation + setText
  sites together); window title + Guide h1 "GT7 VR Dashboard" → **"Next Gear
  Racing Pit Crew"** (product renamed 2026-06-23; only user-facing sites).
- **Guide fixes:** Step 8 no longer describes a phantom "Dashboard" tab with
  quick-link buttons — it now describes the real Home tab; the API-key bullet
  points at `api_key.txt` or the **Strategy Builder** field (the audit's
  "Settings duplicate" claim was wrong — no Settings key field exists; the
  editable field + all `self._ai_api_key` AI callers untouched, relocation
  deferred); new "Tool tabs (⚙) … safe to ignore during a normal race weekend"
  note; "pip install requests beautifulsoup4" removed from the web-refresh
  tooltip.
- **Deferred (documented in the cleanup doc §2.9):** Track Modelling jargon
  glossary, Telemetry raw-row hiding, API-key relocation to Settings, and the
  two `config["strategy"]` fan-outs (out of scope; a test pins they still exist).

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_diagnostic_tab_cleanup.py` (NEW) | 25 | all 8 deleted widgets / 9 deleted methods / 8 dead imports gone with zero string or getattr references remaining in either UI module; backend review functions still importable (UI-only removal); renames present + stale labels absent (Session Match Key, Time left, remaining_time_ms, Voice queue, product name, no pip install); Guide fixed (no phantom Dashboard step, Home step + Command Centre present, API-key bullet → Strategy Builder, tool-tab note, dead telemetry constant gone); tab order pinned incl. Home at 13; `_on_tab_changed` dispatches unchanged; diagnostic tabs still built; product_flow diagnostic set unchanged; Home Dashboard wiring intact; both legacy fan-outs untouched; no strategy writes in touched areas; API-key field still exists |
| `tests/test_group24_track_modelling_extraction.py` (updated) | — | `_tm_` method-count floor 54 → 46; the 9 deleted methods enumerated in the test comment |

### Acceptance criteria — status
- Full test suite passes — **yes (4479/6/0)**.
- Cleanup document exists and is specific — **yes (`docs/DIAGNOSTIC_TAB_CLEANUP.md`,
  per-item verdict/risk/action tables incl. corrected audit findings)**.
- 7 legacy buttons safely removed — **yes (deleted; unreachability proven)**.
- Developer-only labels hidden/renamed — **yes**.
- Tab order unchanged / Home Dashboard functional / diagnostics available — **yes (source-scanned)**.
- No setup/strategy/track-mapping/AI-prompt/AI-plumbing/PTT/voice change — **yes**.
- No legacy fan-out removal attempted — **yes (pinned by test)**.
- Clear next-sprint recommendation — **yes (Tab Navigation Refactor — Named
  Tab Lookup, then move Home Dashboard to index 0)**.

### Manual UAT steps
1. Launch the app: window title reads "Next Gear Racing Pit Crew".
2. Guide tab: title updated; intro explains the ⚙ tool tabs; Step 8 describes
   the Home tab; API-key bullet names the Strategy Builder tab.
3. Strategy Builder: the row under the separator reads "Session Match Key:"
   and still shows the hash + track/car/length detail; lap bank unaffected.
4. Diagnostics tab: rows read "Time left:", "remaining_time_ms:",
   "Voice queue:" and update live as before.
5. Track Modelling: Segment Detection → Segment Diagnostics table and the
   whole-model Accept workflow behave exactly as before (nothing visible
   changed — the deleted controls were already invisible).
6. Confirm tab order and the Home tab are unchanged.

### Next sprint
**Tab Navigation Refactor — Named Tab Lookup** — replace the hard-coded tab
indices in `_on_tab_changed` (0–12 + `_home_tab_index`) with
lookup-by-title/object so tabs can finally be reordered safely; then **move
Home Dashboard to index 0** and enable its deferred click-to-navigate
(`docs/HOME_DASHBOARD_BUILD.md` §5). Alternative higher-risk track: **Legacy
Fan-Out Removal Phase 1**.

---

## Tab Navigation Refactor — Named Tab Lookup (2026-07-03)

> Branch `tab-navigation-named-lookup` (from `diagnostic-tab-cleanup-ui-dags`
> @ `c4eafdf`). Full doc: `docs/TAB_NAVIGATION_REFACTOR.md`.
> **Full suite: 4512 pass / 6 skip / 0 fail** (33 new tests; 6 updated in place).

### What was done
Navigation infrastructure only — **tab order, per-tab activation behaviour,
the Home tab position, the diagnostic tabs, the ⚙ markers, and every logic
layer are unchanged** (pinned by source-scans).

- **`ui/tab_registry.py` (NEW, pure Python)** — stable keys `TAB_LIVE`,
  `TAB_EVENT_PLANNER`, `TAB_GARAGE`, `TAB_SETUP_BUILDER`, `TAB_PRACTICE_REVIEW`,
  `TAB_STRATEGY_BUILDER`, `TAB_TELEMETRY`, `TAB_DIAGNOSTICS`, `TAB_GUIDE`,
  `TAB_SETTINGS`, `TAB_HISTORY`, `TAB_AI_LOG`, `TAB_TRACK_MODELLING`,
  `TAB_HOME`; `DEFAULT_TAB_ORDER` (the current visual order 0–13, the single
  place a future reorder edits); `TabRegistry` (`register` duplicate-safe,
  `index_of` → -1 unknown, `key_at` → None out-of-range/garbage, `has`,
  `count`, `keys` — never raises); `key_for_title()` strips the ⚙ decoration
  (lookup itself is positional, so decorated labels can never break it);
  `TAB_BASE_TITLES` cross-checked against `product_flow.TAB_ROLES` by test.
- **`ui/dashboard.py`** — registry built in `_setup_ui` right after the
  unchanged addTab block (+ count-mismatch warning); `_on_tab_changed`
  resolves `key_at(index)` and dispatches by key — a 1:1 translation of the
  old index table; helpers `get_tab_index` / `has_tab` / `current_tab_key` /
  `select_tab` (only sanctioned `setCurrentIndex` site; False on unknown
  keys); jumps migrated (`setCurrentIndex(4/3/1)` →
  `select_tab(TAB_PRACTICE_REVIEW/TAB_SETUP_BUILDER/TAB_EVENT_PLANNER)`);
  guards migrated (`currentIndex() != 11` → `current_tab_key() != TAB_AI_LOG`;
  `_home_tab_index` → `current_tab_key() != TAB_HOME`, attribute retired).
  Mixins never touched `self._tabs` — no changes there.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_tab_navigation_registry.py` (NEW) | 33 | every tab keyed (14, unique) + titles cross-checked vs product_flow; visual order preserved incl. Home last; **DEFAULT_TAB_ORDER mirrors the real addTab sequence (source-extracted)**; key↔index round trip; missing-key/-index/garbage safety; duplicate registration no-op; empty registry safe; ⚙-decorated titles resolve; unknown titles → None; lookup proven positional; module purity; `_on_tab_changed` has zero raw index comparisons + all 8 key→handler pairs; only `select_tab` calls `setCurrentIndex`; no numeric `currentIndex()` checks; `_home_tab_index` retired; 3 jump sites named; visibility guards keyed; helpers defined/safe/stateless; registry+count guard at setup; jump-target key→index mapping proven; all 14 addTab lines pinned; Home after Track Modelling; diagnostic tabs + markers; no strategy writes; fan-out untouched |
| Updated in place (6 tests) | — | `test_group12c` (AI-Log dispatch → `TAB_AI_LOG`), `test_group14` DEF-P2-033 flush guard ×2 (`current_tab_key()`/`TAB_AI_LOG`), `test_group3` (history jump → `select_tab(TAB_PRACTICE_REVIEW)`), `test_diagnostic_tab_cleanup` + `test_home_dashboard_vm` (`_on_tab_changed` scans → key names + handler names). Every update guards the SAME invariant at its key-based home. |

### Acceptance criteria — status
- Full suite passes — **yes (4512/6/0)**.
- Named tab registry exists — **yes (`ui/tab_registry.py`)**.
- `_on_tab_changed` dispatches by stable key, no raw hard-coded indices — **yes (source-scanned)**.
- Tab order unchanged / Home stays at current position / diagnostics available / ⚙ markers work — **yes (pinned)**.
- No setup/strategy/track/AI-prompt/AI-plumbing/PTT/voice change; no fan-out removal — **yes**.
- `docs/TAB_NAVIGATION_REFACTOR.md` exists and is specific — **yes**.
- Clear next-sprint recommendation — **yes (Home Dashboard Promotion)**.

### Manual UAT steps
1. Launch: tab bar identical to before (14 tabs, same order, ⚙ markers).
2. Click through History / Setup Builder / Strategy Builder / Practice
   Review / Telemetry / AI Log / Track Modelling / Home — each tab's
   on-show refresh behaves exactly as before.
3. History → "Load into Practice Review" jumps to Practice Review; Garage
   setup double-click jumps to Setup Builder; Garage "Load to Event ↩"
   returns to Event Planner.
4. Trigger an AI call from a non-AI-Log tab, then open ⚙ AI Log — the newest
   entry is auto-selected (deferred-select guard still works).
5. Home tab still refreshes on show and via its hooks.

### Next sprint
**Home Dashboard Promotion — Move Home to index 0 and add click-to-navigate**:
move the Home `addTab` call + `TAB_HOME` to the front of `DEFAULT_TAB_ORDER`
together (update the order-pinning tests), open the app on Home, and wire the
Home cards / next-action banner to `select_tab(...)` (map the flow summary's
tab names via `key_for_title`). Alternative higher-risk track: **Legacy
Fan-Out Removal Phase 1**.

---

## Home Dashboard Promotion — Move Home to Index 0 and Add Click Navigation (2026-07-03)

> Branch `home-dashboard-promotion` (from `tab-navigation-named-lookup`
> @ `3b7c9c9`). Full doc: `docs/HOME_DASHBOARD_PROMOTION.md`.
> **Full suite: 4533 pass / 6 skip / 0 fail** (new promotion test file; 4
> order-pinning suites updated in place).

### What was done
UI navigation only — **no setup/strategy/track-mapping/AI-prompt/AI-snapshot/
telemetry/PTT/voice/calibration/persistence/context-ownership change; no
`config["strategy"]` fan-out removed; no new hard-coded index; `select_tab`
still the only `setCurrentIndex` site** (pinned by source-scans).

- **`ui/tab_registry.py`** — `DEFAULT_TAB_ORDER` now **leads with `TAB_HOME`**
  (comments renumbered 0–13); every non-Home tab keeps its previous relative
  order (each +1). Header docstring updated. The positional registry re-derives
  every index — no code/API change. New order: Home / Live / Event Planner /
  Garage / Setup Builder / Practice Review / Strategy Builder / Telemetry ⚙ /
  Diagnostics ⚙ / Guide / Settings / History / AI Log ⚙ / Track Modelling ⚙.
- **`ui/dashboard.py`** — Home `addTab` moved to first (`# 0`);
  `select_tab(TAB_HOME)` at the end of `_setup_ui` (open on Home by key); one
  guarded `_home_refresh()` at the end of `__init__` (first render — selecting
  an already-current index emits no `currentChanged`); `_build_home_tab` adds a
  per-card **"Open <Tab>" button** + a next-action button (pointing-hand cursor,
  tooltip, hover accent); new helpers `_home_navigate` (tab-change only, `has_tab`
  guard), `_home_navigate_next_action`, `_home_update_next_action_button`
  (maps the flow summary's tab **name** via `key_for_title`), `_home_nav_button_text`
  (label from undecorated `TAB_BASE_TITLES`) + shared `_HOME_NAV_BTN_QSS`;
  `_home_refresh` updates the next-action button; Guide HTML "Home tab (last
  tab)" → "(first tab, shown when the app opens)".
- **`ui/home_dashboard_vm.py`** — `CARD_TAB_KEYS` mapping + `tab_key_for_card()`
  (imports the pure `ui/tab_registry` key constants — still no PyQt6): Race
  Setup→Event Planner, Track Intelligence→Track Modelling, Setup Brain→Setup
  Builder, Strategy Brain→Strategy Builder, AI Input Safety→AI Log. **Stable
  keys only — never labels** (⚙-decoration-safe).
- **`ui/product_flow.py`** — "Home appended at index 13" note → "first tab
  (index 0)".

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_home_dashboard_promotion.py` (NEW) | 20 | Home leads `DEFAULT_TAB_ORDER` (index 0) + is the first addTab in source; app selects Home via `select_tab(TAB_HOME)`; guarded `_home_refresh()` at end of `__init__`; `DEFAULT_TAB_ORDER` still mirrors the real addTab sequence; card→tab mapping exact + covers every card in `CARD_ORDER` + values are real registry keys + unknown/empty/None card → None; AI Input Safety → a ⚙ diagnostic tab; `_home_navigate` uses `select_tab`+`has_tab`; nav + next-action methods change tab only (no config['strategy'] write / persist / save / upsert / `_run_ai`/`_run_build_setup`/`_run_practice`/`_launch_`/`start_tracker`/calibration/QThread/QTimer); cards wire buttons by key (`tab_key_for_card(key)` + `_home_navigate(k)`); next-action button maps name via `key_for_title` + `has_tab`; button text from `TAB_BASE_TITLES`; no new raw `setCurrentIndex`; all diagnostic tabs built + ⚙ markers applied + diagnostic set unchanged |
| Updated in place (4 suites) | — | `test_tab_navigation_registry` (Home-first visual order + `index==0` + non-Home relative order preserved; jump-target indices +1 (`TAB_HOME`=0, `TAB_EVENT_PLANNER`=2, `TAB_SETUP_BUILDER`=4, `TAB_PRACTICE_REVIEW`=5, `TAB_AI_LOG`=12, `TAB_TRACK_MODELLING`=13); positional `key_at(7)`=Telemetry; renumbered addTab pins; Home leads before every other tab); `test_home_dashboard_vm` (Home leads before Track Modelling + renumbered pins); `test_diagnostic_tab_cleanup` (renumbered tab-order pins); `test_consolidation_product_flow` (Track Modelling #13 / AI Log #12). Same invariants at the renumbered order. |

### Acceptance criteria — status
- Full suite passes — **yes (4533/6/0)**.
- Home Dashboard is the first visible tab / app opens on Home by default — **yes** (headless smoke: 14 tabs, tab 0 = Home, `current_tab_key()` = `home`).
- Home cards navigate to relevant tabs by named keys — **yes** (smoke: Setup Brain→setup_builder, Track→track_modelling, next-action→event_planner).
- No new hard-coded indices; `select_tab` the only tab-selection path — **yes (source-scanned)**.
- Diagnostic tabs remain / ⚙ markers still work — **yes (pinned)**.
- No setup / strategy / track / AI-prompt / AI-plumbing / PTT / voice / live-race change; no `config["strategy"]` fan-out removal — **yes**.
- `docs/HOME_DASHBOARD_PROMOTION.md` exists and is specific — **yes**.
- Clear next-sprint recommendation — **yes (Legacy Fan-Out Removal Phase 1)**.

### Manual UAT steps
1. Launch: the app opens on the **Home** tab (Race Engineer Command Centre),
   which is now the **first** tab; the tab bar shows 14 tabs, Home leading, the
   rest in their previous relative order with ⚙ markers intact.
2. On Home, each mapped card shows an "Open <Tab>" button: Race Setup → Event
   Planner, Track Intelligence → Track Modelling, Setup Brain → Setup Builder,
   Strategy Brain → Strategy Builder, AI Input Safety → AI Log. Clicking each
   switches to that tab and nothing else.
3. The Next Best Action banner shows an "Open <Tab>" button pointing at the
   recommended tab; clicking it navigates there. With the journey complete the
   button hides.
4. Navigating from a card does not start any AI call, telemetry, calibration,
   or save — it only changes tabs (the target tab's normal on-show refresh runs,
   same as a manual click).
5. All prior tab behaviours (History/Setup/Strategy/Practice syncs, AI-Log
   deferred-select, Track Modelling on-show, Home refresh) still work.

### Next sprint
**Legacy Fan-Out Removal Phase 1** — migrate the low-risk read-only
`config["strategy"]` consumers onto `EventContext`/`StrategyContext`, keeping
the `_on_event_set_active` fan-out writer as compatibility until every reader is
migrated. Alternative: **SessionContext / TelemetryContext** to make Home's
`has_valid_laps` / `live_active` approximations owner-backed truth.

---

## Config Safety Guardrails (2026-07-03)

> Branch `config-safety-guardrails` (from `home-dashboard-promotion`
> @ `69289ba`). Full doc: `docs/CONFIG_SAFETY_GUARDRAILS.md`.
> **Full suite: 4567 pass / 6 skip / 0 fail** (34 new tests).

### What was done
Safety + test-isolation only — **no setup/strategy/track-mapping/AI-prompt/
AI-input/telemetry/PTT/voice/calibration/workflow change; `config["strategy"]`
and both fan-outs untouched.** The only config-schema change is materialising
the already-effective `strategy.degradation_consecutive_laps: 2` default.

**Why:** the app rewrites `config.json` during normal use *and during
`MainWindow` construction* (api-key auto-load from `api_key.txt` + `config_id`
derivation → `_persist_config`). The Home Dashboard Promotion smoke run built
`MainWindow` against the real `config.json` and clobbered the user's settings;
the file is gitignored, so there was no git recovery copy.

- **`config_paths.py` (NEW, pure Python — no PyQt6, no app imports)** — single
  owner of config path resolution + IO + the guardrail. `DEFAULT_CONFIG` (moved
  from `main.py`, re-exported there; materialises `degradation_consecutive_laps:
  2`); `resolve_config_path(explicit)` (`--config` → `NGR_CONFIG_PATH` →
  `config.json`); `is_test_environment()` / `is_real_config_path()` /
  `real_config_access_blocked()` (test env + real path + not
  `NGR_ALLOW_REAL_CONFIG=1`); `load_config()` (deep-merge, never raises; refuses
  to READ the real config under tests → defaults, no secret exposure);
  `save_config(path, cfg, *, backup=True)` (refuses to WRITE the real config
  under tests → `ConfigSafetyError`; serialise-first so no partial writes; `.bak`
  backup; atomic `tmp` + `os.replace`); `write_default_config()`.
- **`main.py`** — `DEFAULT_CONFIG`/`load_config` imported from `config_paths`
  (re-exported); `main()` resolves via `resolve_config_path(explicit)`.
- **`ui/dashboard.py _persist_config()`** — delegates to `save_config(...,
  backup=True)`; catches `ConfigSafetyError` (logs, never crashes). ~22 call
  sites unchanged; normal runs write the real config exactly as before (now
  atomic + `.bak`).
- **`.gitignore`** — also ignores `config.json.bak` / `config.json.tmp`.
- **`tests/conftest.py` (NEW)** — `temp_config_path` fixture (isolated config
  from `DEFAULT_CONFIG` in `tmp_path`; no `api_key.txt` in its dir) +
  `_guard_real_config` session-autouse net (SHA-256 of the real config
  before/after the run — fails the suite if any test mutated it).

### New test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_config_safety_guardrails.py` (NEW) | 31 | resolve precedence (explicit > env > default); `is_test_environment` true under pytest; `is_real_config_path` (real / temp / empty / None); `real_config_access_blocked` (real blocked, temp never, opt-out disables, falsey opt-out stays blocked); `load_config` (missing → defaults, temp merge over defaults, corrupt → defaults, real-under-tests → defaults + no key leak + not the shared dict, doesn't mutate `DEFAULT_CONFIG`); `save_config` (writes temp; refuses real → `ConfigSafetyError`; atomic no `.tmp` leftover; `.bak` holds the previous; no `.bak` on first write; non-serialisable never writes partial; non-dict rejected); `write_default_config` seeds `deg=2`; `DEFAULT_CONFIG` deg=2 + empty api_key + `main` re-export identity; **no real `sk-ant-api\d+-…` value in any repo `.py`**; `.gitignore` protects config + `.bak`/`.tmp`; `config.json` not git-tracked; `main` uses `resolve_config_path`; `_persist_config` uses the guarded saver (no raw `open`/`json.dump`) |
| `tests/test_config_safety_smoke.py` (NEW) | 3 | `pytest.importorskip("PyQt6")` + offscreen. Constructs the real `MainWindow` against a temp config: wired to the temp path, no api-key leak, real `config.json` byte-identical (SHA-256) before/after; persist-to-temp writes only the temp file; a window mistakenly wired to the real path is **blocked** (logged no-op, not a crash, real file unchanged) |

### Acceptance criteria — status
- Full suite passes — **yes (4567/6/0)**.
- Real `config.json` not touched by tests or headless smoke runs — **yes** (session-autouse SHA-256 guard + smoke assertions; verified no `.bak`/`.tmp`/diff after a full run).
- Explicit temp config path mechanism for tests — **yes** (`temp_config_path` fixture; `NGR_CONFIG_PATH`; `resolve_config_path`).
- MainWindow smoke construction is safe — **yes** (`test_config_safety_smoke.py`).
- No API keys/secrets committed, logged, or copied into fixtures — **yes** (fixture hashes not raw bytes; source-scan asserts no real key value; temp dirs have no `api_key.txt`).
- Normal user app config behaviour still works — **yes** (guard is test-mode only; `_persist_config` writes the real config in prod, now atomic + `.bak`).
- No setup/strategy/track-mapping/AI-prompt/AI-input/PTT/voice/live-race change — **yes**.
- `docs/CONFIG_SAFETY_GUARDRAILS.md` exists and is specific — **yes**.
- Clear next-sprint recommendation — **yes (Legacy Fan-Out Removal Phase 1)**.

### Manual UAT steps
1. `python main.py` — app launches normally, opens on Home (see SMK-001), reads
   and (on a settings change) writes the real `config.json` as before; a
   `config.json.bak` appears after the first save.
2. `python main.py --config C:\tmp\ngr.json` (or set `NGR_CONFIG_PATH`) — the app
   uses that file instead; the real `config.json` is untouched.
3. `python -m pytest` — full suite green; the real `config.json` is byte-identical
   afterwards (the session guard fails loudly otherwise). No `config.json.tmp` /
   `.bak` left in the repo root from tests.

### Next sprint
**Legacy Fan-Out Removal Phase 1** — migrate the low-risk read-only
`config["strategy"]` consumers onto `EventContext`/`StrategyContext`, keeping the
`_on_event_set_active` fan-out writer as compatibility until every reader is
migrated.

---

## Legacy Fan-Out Removal Phase 1 — Read-Only Consumer Migration (2026-07-03)

> Branch `legacy-fanout-removal-phase-1` (from `config-safety-guardrails`
> @ `d206be2`). Full doc: `docs/LEGACY_FANOUT_PHASE_1.md`.
> **Full suite: 4589 pass / 6 skip / 0 fail** (22 new tests).

### What was done
Consumer-migration only — **every migrated read is byte-identical to the
expression it replaces (proven by test); no behaviour change; `config["strategy"]`
and both fan-out writers preserved.**

- **`ui/dashboard.py`** — new `_active_config_id()` accessor returning
  `StrategyContext.config_id` (strategy-owned, `str(...)`-coerced → byte-identical
  to `config["strategy"].get("config_id", "")`); `_sync_practice_from_event` reads
  the car from `EventContext.car` (car resolves strategy-first there and the events
  table never stores a car → byte-identical).
- **`ui/setup_builder_ui.py`** — the four `config_id` reads now call
  `self._active_config_id()`: `_refresh_setup_history_combo` +
  `_on_setup_history_selected` (read-only history lookups) and
  `_display_setup_result` + `_run_build_setup` (history-save keys). **Zero raw
  `config_id` reads remain in the file.**
- **Preserved / deferred** (documented in `docs/LEGACY_FANOUT_PHASE_1.md`): both
  fan-out writers (Set-as-Active `_on_event_set_active`; Track Modelling combo
  `track_location_id`/`layout_id`); the DB-first event-rule reads
  (track/tyre_wear/fuel_mult/tuning/bop/race-length — not byte-identical to the
  strategy-first raw reads, so a Phase 2 job); the `config_id` hash
  `_compute_race_config_id`; telemetry-owned `_computed_fuel_burn_lpl`; all
  AI-input reads (already snapshot-migrated).

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_1.py` (NEW) | 22 | **Byte-identity:** `StrategyContext.config_id == config["strategy"].get("config_id","")` across absent/empty/string; `EventContext.car == config["strategy"].get("car","")` strategy-only + with a DB event that has no car. **Migrated consumers:** `_active_config_id` uses `_build_strategy_context().config_id`; setup_builder has no raw `config_id` reads + 4 helper calls; the two history lookups use the helper and read no raw `config["strategy"]`; `_sync_practice_from_event` reads `_build_event_context().car`, not raw. **Writers preserved:** `_on_event_set_active` still fans `strat["track"]`/`["bop"]`/`["tuning"]`/`["event_id"]`; Track Modelling still writes `track_location_id`/`layout_id`; `config["strategy"]` not removed. **No new fan-out:** migrated methods write no `config["strategy"]`; setup_builder writes none; Track Modelling's only strategy writes are the two combo ids. **Invariants:** tab order Home-first; config-safety guardrail still blocks real writes. |

### Acceptance criteria — status
- Full suite passes — **yes (4589/6/0)**.
- No real `config.json` writes during tests/smoke — **yes** (all pure-Python; session guard intact).
- `docs/LEGACY_FANOUT_PHASE_1.md` exists and is specific — **yes** (classifies every remaining reader).
- Several low-risk read-only consumers migrated where safe — **yes** (5 config_id sites + 1 car site).
- Remaining readers documented + classified — **yes** (EVENT_CONFIG/STRATEGY_PLAN/TRACK_IDENTITY/SETUP_STATE/AI_INPUT/LEGACY_REQUIRED/WRITER).
- Fan-out writers remain; no new writers introduced — **yes (pinned)**.
- No setup/strategy/track/AI-prompt/PTT/voice/live-race change; Home Dashboard still first + functional — **yes**.
- Clear next-sprint recommendation — **yes (SessionContext/TelemetryContext, then Phase 2)**.

### Manual UAT steps
1. Set an active event, build/save a setup — the setup-history combo still lists
   entries for the current session match key, and selecting one still shows its
   reasoning (config_id now sourced from StrategyContext).
2. Switch to Practice Review with an active event — the car combo still
   auto-selects the event's car.
3. Confirm nothing else changed: strategy/setup labels, AI prompts, tab order,
   Home landing all behave exactly as before.

### Next sprint
**SessionContext / TelemetryContext** (additive, low-risk) to give the
telemetry/session layer a canonical read model and unblock Home's
`has_valid_laps`/`live_active` approximations, then **Legacy Fan-Out Removal
Phase 2** for the DB-first-precedence event-rule consumers.

---

## SessionContext / TelemetryContext (2026-07-03)

> Branch `session-telemetry-context` (from `master` @ `c94e4ad`).
> Full doc: `docs/SESSION_CONTEXT_MIGRATION.md`.
> **Full suite: 4614 pass / 6 skip / 0 fail** (25 new tests).

### What was done
Additive canonical read model + **byte-identical** consumer migration — the
telemetry-layer peer of Event/Strategy/Setup/Track contexts. No telemetry / PTT /
voice / live-race / calibration / setup / strategy / track / AI / tab-order
change; `config["strategy"]` and both fan-out writers preserved.

- **`data/session_context.py` (NEW, pure Python — no PyQt6/DB/I/O)** —
  `SessionContext` frozen dataclass (connected, packet_count, laps_recorded,
  active_session_id, is_recording, live_active = connected, live_mode,
  telemetry_avg_fuel_per_lap, fuel_burn_per_lap + fuel_burn_source
  [LOADED_SESSION/TELEMETRY/CONFIG_FALLBACK], has_practice_laps, has_valid_laps,
  source [EMPTY/LIVE]); `connection_text()`/`recording_text()`/`is_live`/
  `to_dict()`/`flow_flags()`; `build_session_context(...)` never raises.
  **Byte-identity:** `fuel_burn_per_lap` reproduces `_computed_fuel_burn_lpl`'s
  3-tier fallback (loaded session → live telemetry → config fallback 2.0);
  `connected` reproduces `tracker is not None and getattr(tracker,"_connected",
  False)` (resolves False today — a real connection signal can later be wired in
  one place).
- **`ui/dashboard.py`** — new `_build_session_context(*, has_practice_laps,
  has_valid_laps)` helper (safe tracker getters + the `config["strategy"]` fuel
  fallback as the single legacy bridge read + `config["live"]["mode"]`).
  Migrated: `_computed_fuel_burn_lpl` → `self._build_session_context().fuel_burn_per_lap`
  (flagship — the config fuel read now lives only in the builder);
  `_build_home_dashboard_state` → `session_ctx.live_active` / `.has_practice_laps`
  / `.has_valid_laps`; `_refresh_telemetry_context` → `sctx.connection_text()` /
  `.packet_count` / `.recording_text()` / `.telemetry_avg_fuel_per_lap`.
- **Deferred:** real connection state (now a one-place change); a true
  lap-validity owner (`has_valid_laps` still approximated); `_home_has_practice_laps`
  keeps the DB query; live-render tracker reads (tyre labels/fuel bar/countdown/
  per-packet UI) left alone.

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_session_context.py` (NEW) | 25 | Fuel-burn 3-tier **byte-identity** vs a verbatim copy of the old `_computed_fuel_burn_lpl` (parametrized) + source classification + default 2.0; connection→live_active/text, recording from active_session_id (incl. id 0 vs None), packet/lap coercion, live-mode default, source EMPTY vs LIVE; never-raises on garbage; ownership boundary (no car/track/config_id/stint_plan/setup/layout fields); `flow_flags` bridge; `to_dict` schema; module purity (no PyQt6/sqlite). **Source-scans:** `_build_session_context` reads the tracker via safe getters + the fuel/mode bridge; `_computed_fuel_burn_lpl` delegates to the context (no inline `avg_fuel_per_lap` / `config.get("strategy"`); `_build_home_dashboard_state` uses `session_ctx.live_active` (no `getattr(self._tracker,"_connected"`); `_refresh_telemetry_context` uses `connection_text`/`packet_count`/`recording_text` (no tracker-internal reads); migrated methods write no `config["strategy"]`. Home-first + config-safety guardrail invariants. |

### Acceptance criteria — status
- Full suite passes — **yes (4614/6/0)**.
- Canonical telemetry/session read model added — **yes (`data/session_context.py`)**.
- Home `live_active`/`has_practice_laps`/`has_valid_laps` + telemetry status labels + `_computed_fuel_burn_lpl` sourced from the context — **yes**.
- Byte-identical (no behaviour change) — **yes (proven by test)**.
- No telemetry/PTT/voice/live-race/setup/strategy/track/AI/tab-order change; `config["strategy"]` + fan-out writers preserved — **yes**.
- No real config touched by tests — **yes (pure-Python; session guard intact)**.
- Clear next-sprint recommendation — **yes (Legacy Fan-Out Removal Phase 2, or wire real connection state)**.

### Manual UAT steps
1. Telemetry (⚙) tab — Connection / Packets / Recording / fuel-burn labels read
   exactly as before (Recording flips Yes/No with an active session; fuel shows
   "N.NN L/lap (from telemetry)" only when a live average exists).
2. Home Dashboard — the live/practice signals in the Next Best Action and cards
   are unchanged.
3. Strategy fuel numbers (which use `_computed_fuel_burn_lpl`) are identical to
   before: loaded session average, else live telemetry, else the config default.

### Next sprint
**Legacy Fan-Out Removal Phase 2** — migrate the DB-first-precedence event-rule
display/validation consumers (`_sync_strategy_from_event`,
`_sync_setup_builder_from_event`, tuning/BoP validation) to EventContext,
accepting + testing the behaviour change, then begin retiring the Set-as-Active
fan-out. Alternatively, **wire the real UDP-listener connection signal into
SessionContext** (now a one-place change).

---

## Legacy Fan-Out Removal Phase 2 — Event-Rule Display-Label Migration (2026-07-03)

> Branch `legacy-fanout-removal-phase-2` (from `master` @ `c94e4ad`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_2.md`.
> **Full suite: 4629 pass / 6 skip / 0 fail** (15 new tests).

### What was done
Scope was set by an explicit product decision — **display labels only**. The
Strategy/Setup event-context **readout labels** now reflect DB-first
`EventContext` (consistent with what the strategy/setup AI already consumes since
the AI Snapshot Migration). The **functional** paths — setup-permission gating
(`_apply_setup_permissions`), the BoP toggle (`_on_bop_toggled`), the spinbox
rebind — deliberately still read the active `config["strategy"]` fan-out, so
**which setup fields are editable is unchanged**.

- **Why DB-first is correct here:** `_on_event_save` writes event edits to the DB
  (+`config["events"]`) but NOT `config["strategy"]`; only `_on_event_set_active`
  writes the fan-out. So an edited-but-not-reactivated event has a fresh DB record
  and a stale fan-out. The AI already reads DB-first, so the labels were showing
  stale values that disagreed with the AI inputs — Phase 2 aligns them.
- **Byte-identity (in-sync):** all event multipliers/counts are integer `QSpinBox`
  values, so the migrated labels wrap `int()` (`"2×"` stays `"2×"`, not `"2.0×"`).
  `race_type` is safe because `EventContext` normalises the DB combo text
  (`"Timed Race"`) and the fan-out token (`"timed"`) to the same value. The full
  rendered Strategy context line and the Setup readout labels were verified
  byte-identical for an in-sync event/fan-out pair.
- **`ui/dashboard.py _sync_strategy_from_event`** — `_lbl_strategy_event_ctx`
  (track/car/length/Wear/Fuel/Refuel, int-wrapped) + `_lbl_fuel_mult_display`,
  via one `ev_ctx = self._build_event_context()`. `_update_race_config()` writer,
  `_get_mandatory_compounds()`, and the no-active-event branch unchanged.
- **`ui/setup_builder_ui.py _sync_setup_builder_from_event`** —
  `_lbl_setup_event_ctx` (track/car) + `_lbl_rc_*`
  (race_type/length/fuel/wear/mand_pits/weather/damage + bop/tuning labels). Left
  on the fan-out: refuel/req_tyre/avail_tyres labels (complex fallbacks) and the
  functional `_bop`/`_tuning`/`_cats` → `_apply_setup_permissions`/`_on_bop_toggled`
  + `_rebound_setup_spinboxes`.

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_2.py` (NEW) | 15 | **In-sync byte-identity** of the migrated label values (numeric int-preserved, string, bool, normalised `race_type`) + an integer-formatting guard (`"×2"`, `"5 L/s"`); **DB-first divergence** — an edited-not-reactivated event shows DB truth (wear/fuel/bop/tuning/weather/duration), car/track ids stay strategy-sourced; **source-scans** that both sync methods build `EventContext` and read the migrated labels from it, that the functional gating still reads `config["strategy"]` (`sc.get("bop"/"tuning"/"allowed_tuning_categories")`) and is fed the sc-derived `_bop`/`_tuning`/`_cats` (`_apply_setup_permissions(_bop, _tuning, _cats)`), that `_update_race_config()` is still called, and that no raw wear/fuel strategy reads remain in the strategy label; Set-as-Active writer + Home-first + config-guardrail invariants. |

### Acceptance criteria — status
- Full suite passes — **yes (4629/6/0)**.
- Event-rule display labels sourced from EventContext (DB-first) — **yes**.
- Functional gating unchanged (chosen scope) — **yes (still reads `config["strategy"]`, pinned)**.
- Byte-identical in the in-sync case — **yes (verified full rendered strings + field tests)**.
- Behaviour change documented + tested — **yes (`docs/LEGACY_FANOUT_PHASE_2.md` + diverged tests)**.
- No setup-logic/strategy-calc/track-mapping/AI-prompt/PTT/voice/tab-order change; `config["strategy"]` + both fan-out writers preserved — **yes**.
- No real config touched by tests — **yes**.
- Clear next-sprint recommendation — **yes (Phase 3 functional gating w/ product sign-off, or wire real connection state)**.

### Manual UAT steps
1. Set an event active — the Strategy and Setup event-context readout labels show
   exactly what they did before (byte-identical to the fan-out).
2. Edit that event in Event Planner and click **Save** (do NOT click "Set as
   Active"); open the Strategy/Setup tabs — the readout **labels** now show the
   edited values (matching what the AI would use). The editable setup fields /
   BoP gating are unchanged (still reflect the last activation).
3. Click "Set as Active" again — labels and gating agree, as before.

### Next sprint
**Phase 3 — functional gating (needs product sign-off)**: migrate the
setup-permission/BoP inputs + the tuning/BoP AI-response validation to DB-first
EventContext (changes which fields are editable in the diverged case); consider
first making `_on_event_save` re-sync (or drop) the fan-out so DB and config can't
diverge, enabling the Set-as-Active fan-out to be retired. Alternative: wire the
real UDP-listener connection signal into `SessionContext`.

---

## Legacy Fan-Out Removal Phase 3 — Functional Gating / Validation Migration (2026-07-03)

> Branch `legacy-fanout-removal-phase-3` (from `master` @ `4e6721b`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_3.md`.
> **Full suite: 4649 pass / 6 skip / 0 fail** (20 new tests; 2 Phase 2 pins
> updated in place).

### What was done
Scope was set by an explicit product decision — **"flip reads only"**. The two
remaining **functional** `config["strategy"]` consumers now read DB-first
`EventContext`; the fan-out writers are untouched (Phase 4's job).

- **Setup-permission gating** (`ui/setup_builder_ui.py
  _sync_setup_builder_from_event`) — feeds the unchanged `_on_bop_toggled` +
  `_apply_setup_permissions` from `ev_ctx.bop_enabled` / `ev_ctx.tuning_allowed`
  / `list(ev_ctx.allowed_tuning_categories)` (was `bool(sc.get("bop"/"tuning",
  …))` / `sc.get("allowed_tuning_categories", [])`). Gating LOGIC unchanged —
  only its inputs moved.
- **DEF-P3-012 strategy-options tuning validation** (`ui/dashboard.py`) —
  `_strat_locked` / `_strat_allowed` now come from `_build_event_context()`
  (`tuning_locked` / `allowed_tuning_categories`); the
  `validate_ai_setup_response` call is unchanged.
- **Deliberately NOT migrated:** `_on_event_set_active`'s own
  `_apply_setup_permissions(strat.get(...))` call — inside the writer, `strat`
  was just written from the UI widgets (fresh by construction; pinned by test).

**Behaviour:** byte-identical in the in-sync case. In the diverged case (event
edited + Saved, not re-activated) the signed-off change applies: **which setup
fields are editable, and the tuning validation, follow the fresh DB truth** —
removing the Phase 2 inconsistency where labels showed DB truth while the lock
state enforced the stale fan-out. **Reader consistency is now complete** (AI
inputs, labels, gating, validation all DB-first); the fan-out remains only for
its writers, minor label fallbacks (refuel/req/avail), the car spinbox rebind,
`_get_mandatory_compounds`, the no-event branch, and the context-builders'
legacy-bridge inputs.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_3.py` (NEW) | 20 | **In-sync byte-identity** of the gating trio (`bop_enabled`/`tuning_allowed`/`allowed_tuning_categories`) and the validation inputs (`tuning_locked`, allowed list) vs the verbatim old expressions — parametrized across unrestricted / BoP-on / fully-locked / partially-restricted + empty-state defaults; **DB-first divergence** — an edited-not-reactivated event flips the gating inputs and the lock state; **source-scans** — gating inputs and DEF-P3-012 read EventContext, zero raw `sc.get("bop"/"tuning"/"allowed_tuning_categories")` left at either site, gating calls unchanged (`_on_bop_toggled(_bop)`, `_apply_setup_permissions(_bop, _tuning, _cats)`), `_apply_setup_permissions` body pinned (logic untouched, no config reads), validator still called per option, the writer-internal permission call still reads fresh `strat`; fan-out writers + Home-first + config-guardrail invariants. |
| `tests/test_legacy_fanout_phase_2.py` (updated in place) | 15 | The two "functional gating still reads fan-out" pins became "gating calls intact" + "permission call signature unchanged" — the invariant that evolved with the Phase 3 sign-off. |

### Acceptance criteria — status
- Full suite passes — **yes (4649/6/0)**.
- Functional gating + validation sourced from DB-first EventContext — **yes**.
- Byte-identical in-sync; diverged behaviour change signed off + tested — **yes**.
- Gating/validation logic unchanged (inputs only) — **yes (bodies pinned)**.
- Fan-out writers preserved; no new writers — **yes (pinned)**.
- No setup-recommendation/strategy-calc/track-mapping/AI-prompt/PTT/voice/tab-order change — **yes**.
- No real config touched by tests — **yes**.
- Clear next-sprint recommendation — **yes (Phase 4: re-sync on save → migrate last readers → retire the writer)**.

### Manual UAT steps
1. Set an event active — Setup Builder lock state/banner and editable fields are
   exactly as before (byte-identical to the fan-out).
2. Edit that event's tuning/BoP rules in Event Planner and **Save** (do NOT
   re-activate); open Setup Builder — the lock banner and editable fields now
   follow the edited DB values (and match the readout labels + what the AI
   would use). Run a strategy analysis — the tuning-violation warning uses the
   same edited rules.
3. Click "Set as Active" — everything agrees, as before.

### Next sprint
**Legacy Fan-Out Removal Phase 4 — retire the divergence, then the fan-out:**
(1) `_on_event_save` re-syncs the fan-out when the saved event is active
(config-only); (2) migrate the last minor readers (refuel/req/avail fallbacks,
`_get_mandatory_compounds`, car rebind); (3) retire the Set-as-Active fan-out
writer (keep `config["strategy"]` only as the context-builders' input).
Alternative: wire the real UDP-listener connection signal into `SessionContext`.

---

## Legacy Fan-Out Removal Phase 4 — Divergence Elimination + Last Readers (2026-07-03)

> Branch `legacy-fanout-removal-phase-4` (from `master` @ `e356879`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_4.md`.
> **Full suite: 4667 pass / 6 skip / 0 fail** (18 new tests; 11 legacy pins
> updated in place).

### What was done
- **`dashboard._fanout_event_to_strategy(evt_name)` (NEW)** — the Set-as-Active
  fan-out block extracted **verbatim** (event-RULE fields only: track /
  race-type / length / wear / fuel / stops / weather / damage / refuel /
  required+available tyres + the `mandatory_compounds` names string / bop /
  tuning / cats / event_id). **Config-dict only** — no tracker / advisor /
  query-listener / sync / persist side effects; never touches the strategy-PLAN
  fields (`car`, `config_id`, `stops`, fuel/tolerances). `_on_event_set_active`
  behaviour unchanged (save → helper → all its activation side effects).
- **Re-sync on Save** — `_on_event_save` calls the helper **only when the saved
  event IS the active event**, before its existing `_persist_config()`. The DB
  record and the fan-out can no longer diverge; after an edit+Save, DB-first
  AND legacy readers agree immediately. Activation side effects (tracker race
  config, advisor context) remain exclusive to "Set as Active" — unchanged from
  before, where Save updated them never. Derived `config_id` still refreshes on
  the next strategy-tab sync (same timing as before).
- **Last readers migrated (byte-identical in-sync):**
  `_get_mandatory_compounds` → `EventContext.required_tyres` codes mapped to
  display names via `data.tyres.get_by_code` (the same mapping the fan-out
  writer used to build its string); setup-tab refuel label
  (`int(ev_ctx.refuel_rate_lps)` keeps the QSpinBox formatting), required /
  available tyre labels (same codes), car spinbox rebind (`ev_ctx.car`).
  **`_sync_setup_builder_from_event` no longer reads `config["strategy"]` at
  all** (dead `sc` removed).
- **Writer retirement investigated + deferred (§5 of the doc):** retiring the
  Set-as-Active writer today breaks the app — `car` / `config_id` / the stint
  plan live ONLY in the fan-out (events table stores none of them; the contexts
  read them FROM it), and ~25 readers remain (live-session open, BoP checks,
  degradation params, the `_compute_race_config_id` hash, restore paths,
  AI-snapshot bridges). With re-sync the fan-out can no longer go stale, so
  retirement is a mechanical Phase 5: re-home those fields, migrate the ~25
  reads, delete the writer.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_4.py` (NEW) | 18 | The real `_fanout_event_to_strategy` bound to a widget stub (types.MethodType + MagicMock): writes ALL event-rule fields (incl. the compounds names string via the real `data.tyres` mapping and the timed/lap race-type normalisation both ways); NEVER touches `car`/`config_id`/`stops`/`fuel_burn_per_lap`; returns the live `config["strategy"]` dict; calls no persist/sync. Save-path source-scans: the guarded call (`if name == active_event_id`) sits BEFORE `_persist_config()`; `_on_event_save` stays config-only (no `set_race_config`/advisor/listener/sync/permission calls); `_on_event_set_active` keeps its side effects and carries NO inline fan-out. Reader migrations: `_get_mandatory_compounds` byte-identity vs the old string-parse (via the shared name mapping) + reads EventContext; refuel/req/avail/car label equivalence; `_sync_setup_builder_from_event` reads no `config["strategy"]`. Track-Modelling writer + Home-first + config-guardrail invariants. |
| Updated in place (11 legacy pins) | — | The strat-write pins moved with the block (same invariants, new home): `test_group7_event_persistence` `TestEventSetActiveStratKeys` ×7 (incl. save-precedes-fan-out ordering, now vs the helper call), `test_group12a_bop_tuning_propagation` `TestStratIsReference` ×3, `test_group4_fixes` ×1, plus the Phase 1/2/3 writer-preserved pins (helper + Set-as-Active-invokes-it). |

### Acceptance criteria — status
- Full suite passes — **yes (4667/6/0)**.
- DB event and fan-out can no longer diverge — **yes (re-sync on Save, guarded to the active event)**.
- Re-sync is config-only; activation side effects unchanged — **yes (pinned)**.
- Last named readers migrated byte-identically — **yes**; setup sync fully off the fan-out.
- Writer retirement handled honestly — **deferred with a concrete dependency list (Phase 5)**; both writers still present and pinned.
- No setup-logic/strategy-calc/track-mapping/AI-prompt/PTT/voice/tab-order change — **yes**.
- No real config touched by tests — **yes**.
- Clear next-sprint recommendation — **yes (Phase 5 writer retirement, or SessionContext connection signal)**.

### Manual UAT steps
1. Set an event active — identical behaviour to before (fan-out written, tracker/
   advisor/syncs all fire).
2. Edit the ACTIVE event (e.g. tyre wear, BoP) and click **Save** only — the
   Strategy/Setup labels, gating, AND the legacy readers (e.g. session match key
   detail after visiting the Strategy tab) all reflect the edit; no
   re-activation needed. The tracker's race type still updates only on
   "Set as Active" (as before).
3. Edit and Save a NON-active event — the active race config is untouched.
4. Mandatory-compound and available-tyre labels read exactly as before.

### Next sprint
**Legacy Fan-Out Removal Phase 5 — retire the writer:** re-home `car` /
`config_id` / plan state (DB or the contexts), migrate the remaining ~25 fan-out
reads, then delete the Set-as-Active writer and the compatibility dict.
Alternative smaller job: wire the real UDP-listener connection signal into
`SessionContext`.

---

## Legacy Fan-Out Removal Phase 5 — Functional Readers + Frozen Allowlist Guard (2026-07-03)

> Branch `legacy-fanout-removal-phase-5` (from `master` @ `b58545e`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_5.md`.
> **Full suite: 4682 pass / 6 skip / 0 fail** (15 new tests; 2 legacy pins
> updated in place).

### What was done
Scope was set by an explicit product decision — **"Functional + guard"** — after
the sprint-opening audit found full writer retirement **blocked**: telemetry-path
reads in `main.py _dispatch` (per-lap DB tagging + fallback race-session open —
an EventContext there means a DB query per lap event), the
`_compute_race_config_id` **hash** (byte-stability paramount), the restore
writers, plan-state persistence (stops/fuel/tolerances/config_id have no DB
home), and the context-builder bridges. All mapped in the doc's **Phase 6
retirement plan** (dispatcher session-tag snapshot → hash proof + pinned
vectors → restore redesign → plan-state home → reshape bridges).

**Functional readers migrated (byte-identical in-sync; post-Phase-4 always in
sync):**
- `dashboard._on_live_mode_changed` live-session open tagging — `EventContext`
  `track`/`car`/`event_id` + `_active_config_id()` (StrategyContext).
- Degradation params — `tyre_wear_multiplier` (EventContext) +
  `degradation_consecutive_laps` (StrategyContext); still read on the UI thread
  before the worker spawns.
- BoP checks — `_get_bop_data_for_car` + the reload-BoP gate →
  `EventContext.bop_enabled` / `.car`.
- `setup_builder._current_setup_dict` event-identity fields — car (with the
  `or "Unknown Car"` fallback preserved), track, weather (feeding the same
  condition map), bop — via one `_ev_ctx`. Voice-thread-safe (the query
  listener's setup getter): SessionDB is `check_same_thread=False` + locked.
- Setup-save `event_id` — `int(_build_event_context().event_id or 0)`.

**No product decision reads the legacy dict any more.**

**Frozen allowlist:** `tests/test_legacy_fanout_phase_5.py::FROZEN_ALLOWLIST`
pins all **41 remaining `config["strategy"]` access sites** across 40
`(file, method)` entries (dashboard 29, setup_builder 14/9 methods,
track_modelling 3, main.py 2), each annotated (writer / bridge / hash / plan /
restore / cosmetic / telemetry-path). The scan requires exact equality: a NEW
consumer fails with a pointer to the contexts; a silent removal fails until the
allowlist is shrunk in the same commit.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_5.py` (NEW) | 15 | Frozen-allowlist exact match + the no-new/no-silently-removed guard; byte-identity for every migrated read (session-tagging fields incl. empty defaults; degradation params incl. the 1.0/2 defaults; BoP gate + car incl. empty→closed; setup-dict identity fields incl. the "Unknown Car" fallback); source-scans that the five migrated methods read the contexts with zero raw reads left; fan-out writer + Phase 4 save re-sync + Home-first + config-guardrail invariants. |
| `tests/test_group4_fixes.py` (updated ×2) | — | `TestBoPSourceOfTruth` — the invariant was "BoP from event state, never a widget"; the event-state source is now the canonical EventContext (`bop_enabled`), the never-a-widget assertion unchanged. |

### Acceptance criteria — status
- Full suite passes — **yes (4682/6/0)**.
- Functional readers on canonical contexts; byte-identical in-sync — **yes (tested)**.
- Frozen allowlist blocks new consumers and silent removals — **yes (exact-equality scan)**.
- Writer retirement handled honestly — **blocked items mapped for Phase 6; writer + re-sync + TM combo writer preserved and pinned**.
- No setup-logic/strategy-calc/track-mapping/AI-prompt/PTT/voice/tab-order change — **yes**.
- No real config touched by tests — **yes**.
- Clear next-sprint recommendation — **yes (SessionContext connection signal, Phase 6a dispatcher snapshot, or product work)**.

### Manual UAT steps
1. Start a Practice/Qualifying/Race session with an active event — the session
   row in History carries the same track/car/session-match-key/event linkage as
   before.
2. Run Analyse Degradation — identical parameters/results (wear multiplier and
   consecutive-lap window unchanged).
3. With a BoP event active, the BoP data/label behave exactly as before; with
   BoP off, `_get_bop_data_for_car` still returns nothing.
4. Save a setup — it links to the same event id; voice queries about the current
   setup still work (getter now context-backed).

### Next sprint
The fan-out series is at its natural pause (staleness impossible since Phase 4;
no functional decision on the dict; guard in place). Options: **wire the real
UDP-listener connection signal into SessionContext** (one-place change,
user-visible), **Phase 6a — dispatcher session-tag snapshot** (first concrete
writer-retirement step), or **return to product work** (e.g. deferred OFR-1
between-race learning loop).

---

## Legacy Fan-Out Removal Phase 6a — Dispatcher SessionTag Snapshot (2026-07-04)

> Branch `legacy-fanout-phase-6a-dispatcher-tag` (from `master` @ `b010882`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_6A.md`.
> **Full suite: 4703 pass / 6 skip / 0 fail** (21 new tests; the Phase 5
> frozen allowlist consciously shrunk in the same commit — the guard held).

### What was done
Retirement-map item 1 (`docs/LEGACY_FANOUT_PHASE_5.md` §4): **the telemetry
pipeline no longer touches `config["strategy"]` at runtime.** The
EventDispatcher's two `_dispatch` reads (per-lap DB tagging `event_id`; the
fallback race-session open track/car/config_id/event_id) are replaced by a
frozen **SessionTag** pushed from the UI.

- **`data/session_context.SessionTag` (NEW, pure)** — frozen dataclass;
  `from_strategy()` reproduces the dispatcher's original reads verbatim;
  coercing `build_session_tag()`. Immutable → attribute swap is atomic under
  the GIL (no lock between the UI writer and dispatcher reader threads).
- **`EventDispatcher` (main.py)** — seeds the tag at construction from the
  config it receives (one-time, before the thread starts — the single remaining
  main.py bridge read; allowlist `("main.py","__init__"):1` replaces
  `("main.py","_dispatch"):2`); `set_session_tag()` None-safe swap; `_dispatch`
  reads only the tag; **`self._config` removed entirely**.
- **`MainWindow._push_session_tag()` (NEW)** — builds from `EventContext`
  (`track`/`car`/`event_id`) + `_active_config_id()` (StrategyContext) —
  byte-identical per the Phase 5 proofs; never raises. Push sites: end of
  `_update_race_config` (Set-as-Active, garage car select, and the
  session-config restore ALL funnel through it), `_on_event_save`'s
  active-event re-sync branch (after `_fanout_event_to_strategy`; ordering
  pinned), and end of `__init__` (belt-and-braces before `dispatcher.start()`).
- **Dead-default note (pinned by test):** the old fallback-open used
  `strat.get("track", "Unknown")`, but `DEFAULT_CONFIG` has always materialised
  `strategy.track = ""` — the "Unknown" default never fired; the real behaviour
  (empty string) is preserved.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_legacy_fanout_phase_6a.py` (NEW) | 21 | SessionTag pure model (`from_strategy` verbatim vs the legacy expressions; defaults incl. `None`; the dead-"Unknown" note pinned against `DEFAULT_CONFIG`; coercion; immutability); context-built tag == strategy-built tag (in-sync + empty); the **real `EventDispatcher`** constructed with mocks, thread never started: construction seed, no-config seed empty, None-safe swap, `RACE_STARTED` opens the session with exactly the tag fields (car_id from the ref + track/car/config_id/event_id from the tag), `LAP_COMPLETED` writes `event_id` from the tag, an updated tag is used by the next event; source-scans (`_dispatch` has zero config reads; the dispatcher config attr is gone; the push helper builds from the contexts and never reads config; all three push sites wired incl. the after-fan-out ordering in `_on_event_save`); SessionTag model purity; fan-out writer + Phase 4 re-sync + Home-first + config-guardrail invariants. |
| `tests/test_legacy_fanout_phase_5.py` (updated) | — | `FROZEN_ALLOWLIST`: `("main.py","_dispatch"):2` removed, `("main.py","__init__"):1` added (the construction-time seed — bridge, out of the hot path). The exact-equality guard failed until this conscious update — working as designed. |

### Acceptance criteria — status
- Full suite passes — **yes (4703/6/0)**.
- Telemetry pipeline free of runtime `config["strategy"]` reads — **yes** (`_dispatch` config-free; dispatcher holds no config dict).
- Tag byte-identical to the old reads — **yes** (verbatim `from_strategy` + context-equivalence tests; push coverage means in-sync always).
- No lock added to the hot path — **yes** (immutable swap, GIL-atomic).
- Push coverage complete — **yes** (all tag-field write flows funnel through the three push sites; table in the doc).
- Fan-out writer / re-sync / TM combo writer / hash / restores / bridges untouched — **yes (pinned)**.
- No telemetry semantics/announcer/strategy-engine/PTT/voice/setup/strategy/track/AI/tab-order change — **yes**.
- Clear next-sprint recommendation — **yes**.

### Manual UAT steps
1. Set an event active, start a Practice session — laps written to the DB carry
   the same event linkage as before; History rows unchanged in shape.
2. With no session open, let a race start on-track (fallback open) — the session
   row carries the active event's track/car/session-match-key/event id exactly
   as before.
3. Edit the ACTIVE event and Save (no re-activate), then complete a lap — the
   lap's event linkage reflects the saved event (fresh tag).
4. Garage → "Select for Event" with a different car, then drive — new laps tag
   with the new car via the refreshed session context.

### Next sprint
Retirement-map item 2: **`_compute_race_config_id` hash byte-stability proof**
(pin hash vectors → prove EventContext-sourced inputs identical in-sync →
migrate the hash inputs). Alternative: **wire the real UDP-listener connection
signal into `SessionContext`** (Home's `live_active` becomes real), or return to
product work (OFR-1).

---

## SessionContext Real Connection Signal (2026-07-04)

> Branch `session-context-real-connection` (from `master` @ `ebbaed4`).
> Full doc: `docs/SESSION_CONTEXT_MIGRATION.md` §5a.
> **Full suite: 4721 pass / 6 skip / 0 fail** (18 new tests).

### What was done
The one-place change promised by the SessionContext sprint, delivered — plus a
wider latent-bug fix found during it.

- **`MainWindow(udp_listener=...)` (NEW param)** — duck-typed (`.connected` /
  `.total_received` / `.parse_errors` / `.packet_rate`, all real properties on
  `telemetry/listener.UDPListener`; `connected` is packet-timeout based: True on
  receive, False after 3 s of silence). `main()` passes the listener (created
  before the window). Listener attrs are plain bool/int/float — GIL-atomic
  cross-thread reads; no locks added.
- **`_build_session_context`** — prefers the listener for `connected` +
  `packet_count`; the legacy tracker-getattr fallbacks are retained verbatim
  (byte-identical to the old always-False/0 behaviour when no listener is
  wired — the existing 25-test SessionContext suite passes unchanged). Through
  the existing context plumbing, **Home's `live_active`, the journey step-12
  flow gate, and `_refresh_telemetry_context`'s Connection/Packets labels
  become real automatically.**
- **`_update_telemetry_labels` (diagnostics panel) — latent bug fixed:** it
  read FOUR phantom tracker attributes (`_connected`, `_packet_count`,
  `_error_count`, `_packet_rate_hz` — none ever existed on RaceStateTracker),
  so the panel was frozen at "Disconnected / 0 / — Hz / Not started". It now
  reads the listener's four real stats, with the old fallbacks preserved when
  no listener is wired.
- **Intended behaviour change (the point):** with SimHub streaming, the Home
  Live signals and the Telemetry tab show Connected with live packet counts;
  3 s of silence → Disconnected. Everything else byte-identical.

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_session_connection_signal.py` (NEW) | 18 | The REAL `_build_session_context` bound to widget-free stubs: connected listener → live context + `flow_flags.live_active`; packet totals flow; disconnected listener; listener-beats-tracker; a listener missing the expected attrs degrades safely to disconnected/0. No-listener fallbacks reproduce the old frozen state exactly (no tracker; tracker-without-attrs; real tracker fields like `laps_recorded` still flow). The REAL `_update_telemetry_labels` on stubs — lit panel ("Connected"/"500"/"3"/"59.9 Hz") vs the old frozen state ("Disconnected"/"0"/"— Hz"). Wiring source-scans: ctor param stored, `main()` passes `udp_listener=listener`, the builder prefers-listener-with-fallback (legacy expressions retained verbatim), the panel reads all four listener stats. The `UDPListener` property contract (connected/total_received/parse_errors/packet_rate are properties) pinned against the real class. Phase 5 frozen allowlist still matches exactly; Home-first + config-guardrail invariants. |

### Acceptance criteria — status
- Full suite passes — **yes (4721/6/0)**.
- Home `live_active` / telemetry labels reflect the real UDP state — **yes** (one-place change via SessionContext inputs).
- No-listener behaviour byte-identical to before — **yes (fallbacks pinned; existing SessionContext suite unchanged)**.
- No locks added to cross-thread reads — **yes (GIL-atomic plain attrs)**.
- Diagnostics-panel phantom-attr bug fixed with behaviour preserved sans listener — **yes**.
- No telemetry semantics / PTT / voice / setup / strategy / track / AI / tab-order change; no new `config["strategy"]` consumers (allowlist exact) — **yes**.
- Clear next-sprint recommendation — **yes**.

### Manual UAT steps
1. Launch with SimHub streaming GT7 telemetry — the status bar shows connected
   (as before), AND now: the Telemetry (⚙) tab's Connection/Packets labels show
   "Connected" with a climbing packet count; the Diagnostics connection group
   shows live rate ("~60 Hz") and totals.
2. Home tab — the live/racing signals (step-12 gate, Live card status) reflect
   the actual connection; stop SimHub and after ~3 s they drop to disconnected.
3. Run the app without SimHub — everything reads Disconnected/0 exactly as
   before.

### Next sprint
**Phase 6b — `_compute_race_config_id` hash byte-stability proof**
(retirement-map item 2: pin hash vectors → prove EventContext-sourced inputs
identical in-sync → migrate the hash inputs), or **return to product work**
(deferred OFR-1 between-race learning loop) — the state architecture is
consolidated and the Home Dashboard is now fully truthful.

---

## Legacy Fan-Out Removal Phase 6b — config_id Hash Byte-Stability Proof (2026-07-04)

> Branch `legacy-fanout-phase-6b-hash-proof` (from `master` @ `8e9fcb6`).
> Full doc: `docs/LEGACY_FANOUT_PHASE_6B.md`.
> **Full suite: 4738 pass / 6 skip / 0 fail** (17 new tests; purely additive —
> no production code changed).

### What was done
Retirement-map item 2 delivered as **proof + pins**; the migration half is
provably **blocked** and folds into items 3/4.

- **The blocker (restore-divergence):** `_load_session_config` (lap-bank "load
  historical session") deliberately writes a historical session's track/car +
  race params into the working `config["strategy"]` WITHOUT changing the active
  event, then recomputes the id — the id must follow the RESTORED session.
  `EventContext.track`/rules are DB-first → an EventContext-sourced hash would
  pin the id to the active event mid-restore, silently breaking the feature.
  Outside restores the two sources are provably identical (post-Phase-4 always
  in sync — tested). `car` alone is always-safe (strategy-first), but hash
  inputs must move together. **Corrected map:** item 2's migration merges into
  item 3 (restore redesign) / item 4 (working-race-config home) — to be done
  under the golden vectors added here.
- **Golden vectors** — five literal (inputs → id) pairs frozen from the shipped
  algorithm, exercised through the REAL `_compute_race_config_id` bound to a
  widget-free stub; includes the empty/default `'||l25' → 05e6d2f288` (a real
  id observed in the field on 2026-07-03). The test header forbids regenerating
  vectors on failure — a mismatch means history re-keying; the CODE must be
  fixed.

### New test file

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_race_config_id_hash.py` (NEW) | 17 | Golden vectors ×5 through the real method; `DEFAULT_CONFIG` hashes to the empty vector; 10-char lowercase-hex shape + determinism; per-input sensitivity (track/car/race-type/length each change the id); the algorithm's own `l25`/`t60` absent-key defaults pinned (explicitly distinct from EventContext's 0 defaults); unknown race-type tokens hash as lap; source-level verbatim pin (raw-string format, `sha256(...)[:10]`, the 25/60 defaults, the working-config input source); in-sync EventContext equivalence (a future migration is safe OUTSIDE restores) + the restore-divergence demonstration (the blocker) + car's strategy-first safety; Phase 5 frozen allowlist untouched; Home-first + config-guardrail invariants. |

### Acceptance criteria — status
- Full suite passes — **yes (4738/6/0)**.
- Hash algorithm + inputs tamper-evident — **yes (golden vectors + source pin)**.
- EventContext equivalence proven where true; migration blocker demonstrated, not hand-waved — **yes**.
- Retirement map corrected — **yes (item 2 → items 3/4)**.
- Zero behaviour change; allowlist untouched — **yes**.
- Clear next-sprint recommendation — **yes**.

### Manual UAT steps
None — no production code changed. (Regression safety: any future edit that
would re-key the lap bank / setup history / session match keys now fails the
golden-vector suite loudly.)

### Next sprint
**Retirement-map item 3 — restore-writer redesign** (a first-class "working
race config" flow + home, item 4, so the hash inputs, restore writers, and
plan-state persistence migrate together under the golden vectors), or
**return to product work** (deferred OFR-1 between-race learning loop).

---

## Working Race Config Read Model (2026-07-04)

> Branch `working-race-config` (from `master` @ `7f4a95a`).
> Full doc: `docs/WORKING_RACE_CONFIG.md`.
> **Full suite: 4760 pass / 6 skip / 0 fail** (25 new tests; hash-vector suite
> updated in place; `FROZEN_ALLOWLIST` consciously reshaped).

### What was done
Retirement-map item 3, **reader half** (explicit product decision: "read model +
readers"; the writer half — writers write a typed object, dict fields become
derived — is deferred with item 4).

- **`data/working_race_config.py` (NEW, pure)** — `WorkingRaceConfig` (frozen:
  track, car, raw race_type token, `total_laps` default **25**,
  `race_duration_minutes` default **60** — the hash's own absent-key defaults,
  deliberately distinct from EventContext's 0 — plus the stored `config_id`).
  `from_strategy()` verbatim; one documented hardening (garbage lengths coerce
  to defaults instead of raising). **Owns the match-key algorithm**
  (`length_key` / `hash_raw` / `compute_config_id()` = `sha256[:10]`); the 6b
  golden vectors still exercise the REAL dashboard method through the new
  delegation — byte-identity proven end-to-end. `length_text()` for the
  Strategy-tab detail. Semantics per 6b: usually mirrors the active event;
  deliberately holds a restored historical session's config during a lap-bank
  restore (why the concept exists apart from EventContext).
- **Migrated readers** via the new `_working_race_config()` builder (the single
  bridge read for the concept): `_compute_race_config_id` (delegates);
  `_update_race_config` label + `race_configs` snapshot values (the `config_id`
  WRITE stays — it's the writer); `_sync_strategy_from_event` no-event missing
  checks; `_save_session_to_db` session tagging (a saved session is tagged with
  what it actually ran under, incl. a restored config).
- **Allowlist movement (net −3 direct readers):** `_compute_race_config_id` /
  `_sync_strategy_from_event` / `_save_session_to_db` entries removed;
  `_update_race_config` 2→1 (write only); `_working_race_config` +1 (bridge).
- **Milestone: the reader side of the whole consolidation is complete** —
  remaining `config["strategy"]` access = writers, context/AI bridges,
  plan-state persistence, and cosmetic reads, all allowlisted and annotated.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_working_race_config.py` (NEW) | 25 | `from_strategy` verbatim reads; the 25/60 absent-key defaults; None-safety; the documented garbage-coercion hardening; immutability; `length_key`/`hash_raw`; `compute_config_id` asserted against the golden vectors directly on the model; unknown race-type hashes as lap; `length_text` display; schema + module purity; source-scans for all four migrated consumers (incl. the config_id write remaining in `_update_race_config` and the snapshot fields fed from the model); writers-untouched pins (`_fanout_event_to_strategy`, `_load_session_config`); reshaped-allowlist exactness; Home-first + config-guardrail invariants. |
| `tests/test_race_config_id_hash.py` (updated in place) | 18 | The `_bind` stub now binds the REAL `_working_race_config` builder too, so the golden vectors exercise the full delegated dashboard path end-to-end; the source-level algorithm pin moved to `data/working_race_config.py` (same invariant, new home) + a new dashboard-delegation pin. Vectors unchanged and green — byte-identity proven. |

### Acceptance criteria — status
- Full suite passes — **yes (4760/6/0)**.
- Working config named + typed; match-key algorithm owned by the model — **yes**.
- Golden vectors green through the delegated path (no re-keying) — **yes**.
- All targeted readers migrated; allowlist consciously reshaped — **yes (net −3)**.
- Writers untouched (deferred with item 4) — **yes (pinned)**.
- No behaviour change (labels/snapshot/tagging identical; one documented garbage-hardening) — **yes**.
- Clear next-sprint recommendation — **yes**.

### Manual UAT steps
1. Set an event active — the Strategy tab's Session Match Key line (id + track /
   car / length detail) reads exactly as before.
2. Load a historical session from the lap bank — the match key still re-keys to
   the restored session's config (the restore feature intact).
3. Save a session — it is tagged with the same track/car/match key as before.

### Next sprint
**Item 3 writer-half + item 4** — writers write the typed `WorkingRaceConfig`
(or a successor store); the dict's event-rule fields become derived
compatibility; plan-state gets a durable home — the actual fan-out deletion,
now guarded end-to-end by the golden vectors + the frozen allowlist. Or
**product work** (deferred OFR-1 between-race learning loop).

---

## Fan-Out Rule-Cache Deletion (2026-07-04)

> Branch `fanout-rule-cache-deletion` (from `master` @ `8d7c500`).
> Full doc: `docs/FANOUT_RULE_CACHE_DELETION.md`.
> **Full suite: 4777 pass / 6 skip / 0 fail** (16 new tests; 12 legacy pins
> updated in place).

### What was done
**The Product Consolidation audit's original SSOT violation is deleted**
(explicit product decision: "delete the rule cache"; the full schema migration
was declined as the highest-risk option).

- `_fanout_event_to_strategy` no longer writes the 12 event-RULE fields
  (`tyre_wear_multiplier`, `fuel_mult`, `mandatory_stops`, `weather`, `damage`,
  `refuel_speed_lps`, `required_tyres`, `mandatory_compounds`, `avail_tyres`,
  `bop`, `tuning`, `allowed_tuning_categories`). It now writes only the
  legitimate **working-config core**: track, race_type, laps/total_laps,
  race_duration_minutes (match-key hash + lap-bank restore inputs) and
  event_id (session tagging). Existing configs keep old rule keys as harmless
  unread leftovers (pinned: neither refreshed nor removed).
- **Invisibility proofs (the sprint's evidence, all tested):** EventContext
  resolves every rule DB-event-first per field (fallback fires only on `None`
  fields; the DB record AND the `config["events"]` mirror that `_active_event()`
  falls back to carry all rules) → rules identical with fresh/stale/no cache,
  field-by-field. The AI snapshots' CONTEXTS source yields identical frozen
  `race_params` with/without the legacy rule keys (LEGACY_ONLY fires only with
  no active event — a state where the fan-out never ran anyway). The match-key
  hash reads core fields only (golden vectors green).
- **Touch-ups:** `_on_event_set_active`'s writer-internal
  `_apply_setup_permissions` call DELETED — redundant since Phase 3 (the
  activation sync applies permissions from the just-saved DB event via
  EventContext with identical values), and its cached inputs no longer exist.
  Driving-advisor fallback hardened: `set_event_context(_evt_full or
  self._active_event() or strat)` — the no-DB path now gets full rules via the
  events mirror.
- **Residual edge (accepted at scoping):** an ancient DB event row with NULL
  rule columns would fall back to frozen-stale leftovers instead of a fresh
  cache; any event re-save writes full records and heals the row.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_fanout_rule_cache_deletion.py` (NEW) | 16 | The shrunk helper on a widget stub (core-only writes; plan state never touched; stale leftover keys left alone); the invisibility proofs (EventContext rules identical core-vs-stale-cache + sourced from the DB event + the `config["events"]` mirror covers the no-DB fallback; AI snapshot CONTEXTS `race_params` identity; match key unaffected); source-scans (zero rule writes in the helper + the core pinned; the redundant permission call gone with the sync intact; the advisor fallback hardened; activation side effects intact); frozen-allowlist exactness + a golden-vector spot check + Home-first + config-guardrail invariants. |
| Updated in place (12 pins) | — | Invariant evolved from "the fan-out writes the rules (so downstream sees them)" to "the rules are NOT cached — DB-only via EventContext; the working-config core IS written": `test_group7_event_persistence` `TestEventSetActiveStratKeys` ×6 flipped to deletion pins (+1 new core-writes pin); `test_group12a_bop_tuning_propagation` ×2 (the "key must exist for _run_practice_analysis" reason is obsolete — snapshots' CONTEXTS source; LEGACY_ONLY requires no event); `test_group4_fixes` ×1; `test_legacy_fanout_phase_1` writer pin (core fields); `test_legacy_fanout_phase_3` gating pin (redundant-call deletion; invariant holds via the sync); `test_legacy_fanout_phase_4` helper stub test (core-only + rules absent). |

### Acceptance criteria — status
- Full suite passes — **yes (4777/6/0)**.
- The event-rule cache deleted; working-config core + plan state preserved — **yes**.
- Invisibility proven (not asserted) — **yes (field-by-field EventContext, AI race_params identity, mirror fallback, hash spot-check)**.
- Gating at activation unchanged (redundant call removed, sync carries it) — **yes (pinned)**.
- No behaviour change for any active-event workflow; residual edge documented — **yes**.
- Allowlist exact; golden vectors green; no new consumers — **yes**.
- Clear next-sprint recommendation — **yes (product work / OFR-1)**.

### Manual UAT steps
1. Set an event active — Setup Builder lock state, BoP gating, all labels, AI
   analyses, and the Session Match Key behave exactly as before.
2. Edit the active event's rules and Save — gating/labels/AI still follow the
   edit (DB-first), as since Phase 3.
3. Inspect config.json after activation — the strategy section now gains only
   track/race-format/event_id (+ plan state); the old rule keys linger
   untouched from previous versions (harmless).
4. Lap-bank restore and session saving still key/tag exactly as before.

### Next sprint
**Return to product work (recommended)** — the consolidation series has reached
its goal. Standing item: **OFR-1 between-race learning loop**. Optional
architectural tail: the plan-state schema migration (item 4 remainder), only
if/when a feature needs it.

---

## OFR-1 — Between-Race Learning Loop, Loop 1: Setup Self-Scoring (2026-07-04)

> Branch `ofr1-between-race-learning` (from `master` @ `f0a23aa`).
> Full doc: `docs/OFR1_BETWEEN_RACE_LEARNING.md`. Roadmap spec:
> `docs/SMART_RACE_ENGINEER_ROADMAP.md` OFR-1 / §5 Loop 1 / §6.4 / Phase 3-B.
> **Full suite: 4948 pass / 6 skip / 0 fail** (171 new tests; pre-feature
> baseline 4777). Built via the **/feature-factory** chain with human approval
> gates (story, brief, findings); builder output checkpoint-committed before
> each verifier stage.

### What was built
After each session the app self-scores the AI's applied setup recommendations
against measured before/after telemetry and feeds the results into future setup
prompts. Scope (product decision): roadmap **Loop 1 only**.

- **`data/recommendation_scoring.py` (NEW, pure)** — clean-lap windows
  (non-pit/non-out; majority compound); handling-vs-laptime target
  classification from the why-text; verdicts with explicit thresholds
  (improved: Δt<−200 ms or handling agreement ≥0.6 with Δt≤+100; worsened:
  Δt>+300 ms or agreement <0.3 with Δt>0; **mixed-signal override**: Δt clearly
  improved but agreement <0.3 → neutral); confidence from evidence quality
  (−0.1/clean-lap-below-6 each side, −0.15 mixed signals, +0.1 driver-feedback
  bonus, ×1/N attribution split, clamp); **honesty gates** (missing
  before_metrics or <3 clean laps either side → insufficient_data, confidence
  0.0); **no tyre-radius signal**; `format_performance_block()` renders the
  roadmap-§6.4 plain-English block (≥0.5 confidence only).
- **`data/session_db.py`** — migration v9 (`score_confidence REAL DEFAULT
  -1.0` unscored sentinel, `score_verdict ''`, `score_details '{}'`) + 6
  methods: `get_applied_unverified_recs` (cross-layout guard),
  `get_laps_for_scoring`, `get_previous_session_id`, `persist_score`
  (**write-once**), `has_learning_for_car_track`, `get_scored_recs_for_prompt`
  (≥0.5, verdict-filtered, LIMIT 5). The pre-existing after_metrics write-once
  contract untouched.
- **`ui/dashboard.py`** — `_trigger_scoring_pass` (never raises / never blocks
  session open / zero `config["strategy"]` reads; after-session resolved via
  `get_previous_session_id` per the approved brief correction — NOT the
  never-populated `outcome_session_id`; own-session recs skipped; feedback
  queried once via `get_recent_feedback`; Home refresh on ≥1 real verdict);
  call sites after session-open in `_on_live_mode_changed` (ev_ctx) and
  `_save_session_to_db` (wrc); `_build_home_dashboard_state` derives
  **`learning_saved`** from `has_learning_for_car_track` — journey step 13 is
  live, DB-derived, restart-proof.
- **`strategy/driving_advisor.py`** — `_get_previous_ai_context` injects the
  scored block FIRST; when non-empty it REPLACES the free-text recommendation
  history (never both); defensive fallback preserves pre-feature behaviour.

### Factory verification + fix round
43-test acceptance suite: **all 11 ACs + 4 edge cases PASS** (end-to-end: real
trigger over real :memory: DB; §6.4 block via the real advisor path; step-13
via the real flow summary; purity/allowlist/no-radius/no-Loop-2-3-tables
scans). Validator findings, all fixed + re-verified: **C1** dead mixed-signal
branch → restructured, now reachable + tested; **I1** feedback bonus never
activated → wired; **I2** a forbidden `config["strategy"]["layout_id"]` read in
the advisor → removed (literal `''`, matching stored recs) AND the frozen
allowlist scan **extended to `strategy/driving_advisor.py`** (15 pre-existing
bridge entries frozen — the scan gap that hid I2 is closed); minors m1/m2.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_recommendation_scoring.py` (NEW) | 57 | verdict matrix incl. boundaries + the now-reachable mixed-signal override; both honesty gates; target classification; attribution split; feedback bonus; clean-lap deductions; §6.4 block rendering incl. oversteer-on-throttle + threshold/insufficient filtering + malformed-row safety; AST purity + no-radius scans |
| `tests/test_recommendation_scoring_db.py` (NEW) | 45 | migration v9 defaults; full round-trip; write-once; layout guard (match/mismatch/''-''); get_previous_session_id ordering; has_learning False→True; prompt-query threshold/limit/verdict filters |
| `tests/test_ofr1_trigger_wiring.py` (NEW) | 26 | trigger body scans (no config reads, no outcome_session_id, except-wrapped, feedback query present, no hardcoded False); both call sites after open_session; home-gate scans; behavioural stubs (real method + mocked DB): scoring happens, own-session skip, db-None safe, feedback True/False flows into compute |
| `tests/test_ofr1_acceptance.py` (NEW) | 43 | one end-to-end test per AC1–AC11 + 4 edge cases (see the AC table in the doc) |
| Updated in place | — | schema-pin tests 8→9 (test_group18b — also stale name fixed — and test_group18e); `tests/test_legacy_fanout_phase_5.py` `_SCAN_FILES` + FROZEN_ALLOWLIST extended (driving_advisor ×15) |

### Acceptance criteria — status
All 11 story ACs verified PASS by the independent acceptance suite (automatic
trigger; write-once verdict+confidence; handling-metrics-not-laptime-alone;
evidence-quality confidence; insufficient-data honesty; §6.4 prompt block with
0.5 threshold; learning_saved gate; no tyre-radius; allowlist unchanged-then-
consciously-extended; purity + isolated tests; Loops 2–3 untouched) plus the 4
edge cases (multi-rec split, cross-layout, compounds recorded, own-session skip).

### Manual UAT steps
1. Apply an AI setup recommendation (Setup Builder), drive ≥3 clean laps,
   change mode / save session; then start the next session on the same car+
   track — console logs `[Learning] scored N recommendation(s)…` and the
   History DB row carries verdict + confidence + details.
2. Ask for setup advice again on that car+track — the prompt (visible in ⚙ AI
   Log) opens with "Performance of Previous Recommendations" listing the
   change, expected effect, measured deltas, verdict.
3. Home tab — journey step 13 ("Save learning…") shows complete once a real
   verdict exists; fresh car/track combos still show it pending.
4. Drive <3 clean laps and re-trigger — the recommendation is marked
   insufficient_data, never a fabricated verdict.

### Next
Drive sessions to accumulate scores. Build candidates: **OFR-2** (race vs
qualifying telemetry disciplines) or a History-tab surface for scored
recommendations.

---

## OFR-2 — Separate Race vs Qualifying Telemetry Disciplines, Core Split (2026-07-04)

> Branch `ofr2-quali-race-disciplines` (from `master` @ `82ca7c3`).
> Full doc: `docs/OFR2_SEPARATE_DISCIPLINES.md`. Roadmap spec:
> `docs/SMART_RACE_ENGINEER_ROADMAP.md` OFR-2 / §2 / §3.
> **Full suite: 5217 pass / 6 skip / 0 fail** (269 new tests; pre-feature
> baseline 4948). Feature-factory run with approval gates; checkpoints
> committed before every verifier stage.

### What was built
The setup-BUILD and practice-analysis prompts now feed **discipline-aware
telemetry** (the objective text has branched since Group 26; the telemetry now
matches). QUALIFYING = peak metrics: best lap [measured], peak lateral G
[estimated] + derivation note, lock-up count, brake consistency (m), oversteer
rotation split (throttle-on vs entry) + an explicit "steering corrections and
rival traffic/dirty-air are not measured signals" line. RACE = consistency/
efficiency: fuel/lap [measured], lock-up / wheelspin / snap-throttle rates,
lap-time std-dev ("N/A (1 lap)"), per-corner tyre temps ("— not recorded" when
absent). **Every other purpose — unknown, practice, test — keeps today's
generic block BYTE-FOR-BYTE** (the None-sentinel contract).

- **`strategy/telemetry_disciplines.py` (NEW, pure)** — the block builder;
  canonical `normalise_purpose()` routing (strings/enums/None); zero-clean-laps
  honesty; no tyre-radius; [measured]/[calculated]/[estimated] labels.
- **`strategy/ai_planner.py`** — `_build_practice_prompt(session_purpose=None)`
  (discipline block replaces the generic table only when non-None; exact
  fallback otherwise); `_build_setup_from_scratch_prompt(per_lap_telemetry=None)`
  with a `{_telem_section}` that renders "" for unknown/no-laps (prompt
  byte-identical); param threading through `build_car_setup` /
  `analyse_practice_session`. Strategy prompts untouched.
- **RF1 (approved brief correction):** `practice_orchestrator` resolves the
  discipline ITSELF via new `db.get_session_type(session_id)` — the analysed
  session's stored type is the single source; the UI passes nothing (the
  live-mode combo would be wrong for historical sessions).
- **RF2 (approved brief correction):** `ui/setup_builder_ui._resolve_recent_laps`
  fetches the most recent car+track session's laps on the UI thread and wires
  them into `build_car_setup` — without this the story's headline surface was
  inert. Setup combo's session type also threads into the setup snapshot.
- **`data/session_db.py`** — `get_session_laps` +`snap_throttle_count`
  +`brake_consistency_m` and `latest: bool = False` (True → the LAST `limit`
  laps in ascending order); new `get_session_type`.
- **`data/ai_context_snapshot.py`** — `discipline: str = "unknown"` on
  SetupAISnapshot + PracticeAnalysisSnapshot only (hash-excluded, defensive).

### Factory verification + fix round
114-test acceptance suite: **all 11 ACs + 6 edge classes PASS** (real prompt
builders; RF1 by source-scan + live DB round-trip; AC5 byte-identity both
paths; AC7 objective strings + strategy signatures + the pre-existing
byte-identity suite). Validator findings, all fixed + re-verified:
**C1 (CRITICAL)** — PRACTICE/TEST purposes fell through to the RACE block
(free-practice sessions ARE stored as "practice") → only quali/race branch,
everything else returns the sentinel, real-DB practice byte-identity test
added; **I1 (MAJOR)** — `limit=5` returned the EARLIEST laps (full-fuel opening
stint) → `latest=True` semantics, RF2 wiring updated, ordering tests added;
I2/M3 coverage gaps + M1/M2 polish.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_telemetry_disciplines.py` (NEW) | 48 | both blocks' full content incl. labels/derivation/disclaimer/oversteer split/std-dev/"N/A (1 lap)"/temps rules; zero-clean-laps; the None sentinel for unknown/practice/test/enum inputs; purity scans |
| `tests/test_ofr2_prompts.py` (NEW) | 28 | prompt-level integration: quali/race blocks present; UNKNOWN byte-identity; objective strings unchanged; strategy prompt signatures unchanged |
| `tests/test_ofr2_snapshot.py` (NEW) | 26 | discipline defaults + derivations; StrategyAISnapshot negative |
| `tests/test_ofr2_session_db.py` (NEW) | 30 | new columns; get_session_type round-trip; latest=True ordering (8–12 vs 1–5) |
| `tests/test_ofr2_setup_wiring.py` (NEW) | 23 | `_resolve_recent_laps` scans + behavioural stubs incl. latest=True |
| `tests/test_ofr2_acceptance.py` (NEW) | 114 | one end-to-end test per AC + edge classes incl. declared-purpose-wins and the practice→generic byte-identity |

### Acceptance criteria — status
All 11 story ACs + 6 edge-case classes verified PASS by the independent
acceptance suite; frozen allowlist and prompt byte-identity suites unchanged
and green.

### Manual UAT steps
1. Build a **Qualifying Setup** with recent laps on the car/track — the AI Log
   prompt shows the peak-metrics block + the not-measured disclaimer; advice
   reads one-lap-focused.
2. Build a **Race Setup** — the prompt shows fuel/lap, event rates, lap-time
   consistency, tyre temps; advice reads stint-focused.
3. Run Full Practice Analysis on a saved **qualifying** session — quali block;
   on a **practice** session — the familiar generic table, unchanged.
4. No car/track history yet → prompts render exactly as pre-OFR-2.

### Next
Drive quali + race sessions and compare the advice. Build candidates:
History-tab surface for OFR-1's scored recommendations; Phase 2-B/2-C strategy
telemetry; plan-state schema migration.

---

## Setup Brain Upgrade — Professional Race Engineer Diagnosis (2026-07-05)

> Branch `ofr2-quali-race-disciplines` (built on top of the OFR-2 work).
> Backend-only — no UI surface. Two production files:
> `strategy/setup_diagnosis.py` + `strategy/driving_advisor.py`.
> Full doc: `docs/SETUP_BRAIN_UPGRADE.md`.
> **Full suite: 5356 pass / 6 skip / 8 fail** — the 8 failures are ALL
> pre-existing frozen-allowlist guard tests from the already-committed
> `ui/track_modelling_ui.py::_tm_restore_last_track` `config["strategy"]`
> consumer (unrelated track-modelling tech debt, NOT this sprint), left to the
> track-modelling owner; ~72 new tests all green, zero regressions.

### What was built
The setup-diagnosis brain now reasons like a race engineer about **why** a
symptom appears before the AI touches a setup.

- **GEARING DIAGNOSIS (app-side).** `_classify_gearing(...)` →
  `gearing_diagnosis_category` ∈ {gear_too_short, gear_too_long,
  top_gear_power_band_limited, traction_limited_acceleration,
  drag_or_power_limited, limiter_limited, insufficient_data} via a priority
  decision table (top-gear limiter below/at target → gear_too_short/
  limiter_limited; below-target + severe wheelspin + no top-gear limiter →
  traction_limited; below-target + early-peak-power + accel-fade → power-band-
  limited; else drag/long/insufficient). Fed by the new pure
  `_derive_top_gear_frame_signals(frames, top_gear)` (accel_fade_detected,
  peak_power_early over the ~10Hz `LapStats.frames`; degrades to
  insufficient_data when frames absent; tunable module constants — accel-fade
  throttle %, min samples, peak-power RPM fraction, speed-drop %, kerb-proximity
  window).
- **The flawed rule REMOVED.** The `gear_note` "Do NOT recommend lengthening
  gears" block in `_build_combined_prompt`, old `DRIVER_HARD_CONSTRAINTS`
  constraint #8 (now **8** constraints), and the `gearbox_edit_when_preserve`
  validator rule are gone — replaced by `gearbox_category_mismatch`, which only
  blocks gear changes for insufficient_data/gear_too_long/limiter_limited (or a
  driver-flagged-good gearbox); the Fuji RSR power-band case now **ALLOWS** a
  gearbox change.
- **WHEELSPIN SUBTYPE.** `_classify_wheelspin_subtype(...)` →
  `wheelspin_subtype` ∈ {both_rear_spin, snap_throttle_induced, kerb_unload_spin,
  gear_too_short_spin, aero_instability, mixed, insufficient_data}. Honest
  deferrals: `inside_wheel_spin` is NEVER emitted (no per-wheel slip ratio in the
  GT7 packet); `rear_platform_stiffness` folds into `mixed` (no damper baseline);
  kerb_unload_spin uses kerb_count>0 as a proximity proxy (no kerb-position
  channel).
- **COMPLIANCE PRIORITY.** `_detect_compliance_priority(feeling, avg_kerb)` →
  `compliance_priority` bool — when the driver reports stiffness/kerb-upset/
  undulation terms AND kerb events/lap > 2, natural frequency / damping is raised
  to first-or-second in `_derive_tuning_priority` WITHOUT the driver asking, and
  `format_diagnosis_for_prompt` emits an explicit compliance instruction.
- **DOMINANT re-order.** `_derive_dominant_problem` — severe/major wheelspin now
  outranks a "consider"-band bottoming call unless driver feel explicitly cites
  bottoming (new `bottoming` entry in `_FEEL_VOCABULARY`).
- **LSD ANTI-OSCILLATION.** `validate_setup_engineering` gains a `rec_history`
  param + rule `lsd_reversal_without_evidence` — fires on an unevidenced LSD-accel
  direction reversal; skips when a `worsened` verdict backs it, when there is no
  prior/first rec, or when history is unavailable. The reversal reason carries
  prior value, new value, both directions, and `reversal_reason`. rec_history is
  resolved by the **CALLER** (`build_setup_advice_response`,
  `build_combined_setup_response`) from STRUCTURED `data/setup_history.json`
  changes + the DB `worsened` verdict — **no new `config["strategy"]` read**
  (config_id sourced from `_event_ctx`).
- **FEEDBACK CHRONOLOGY.** `_get_driver_feedback_context` splits "Latest feedback
  (weight highest)" vs "Earlier feedback", with per-field trend tags
  current/improving/worsening/resolved via `DrivingAdvisor._feedback_trend_tag`
  (newest-first; keyword-based improving detection) — latest now dominates old.
- **SCHEMA FIX.** `not-present` added to the allowed `issue_classification` values
  in both prompt builders + `_race_engineer_directives`; the invalid
  `"not currently an issue"` example removed.
- All new keys (gearing_diagnosis_category, wheelspin_subtype,
  compliance_priority) are present in **both** the normal and the conservative/
  error-path diagnosis dicts.

### New / updated test files

| Test file | Count | Coverage |
|-----------|------:|----------|
| `tests/test_group39_setup_brain_upgrade.py` (NEW) | ~72 | AC1 Fuji RSR gearing; AC2 traction-limited; AC3 categories + error-path keys; AC4 compliance; AC5 wheelspin subtype (incl. never-inside-wheel-spin); AC6 LSD anti-oscillation; AC7 feedback trend + Scenario 5 latest-wins; AC8 dominant precedence; AC9 not-present schema; frame-signal unit tests |
| `tests/test_group38_setup_diagnosis.py` (updated in place) | 4 | re-pointed: constraint count 9→8; rule rename `gearbox_edit_when_preserve` → `gearbox_category_mismatch` |

### Acceptance criteria — status
All story ACs (AC1–AC9) verified by the new suite; ~72 new tests green, zero
regressions. The 8 pre-existing frozen-allowlist failures are unrelated
track-modelling tech debt and remain for the track-modelling owner.

### Manual UAT steps
1. Build a **Race Setup** on a car/track with a wheelspin-heavy stint — the AI
   Log prompt shows the wheelspin subtype + gearing category reasoning; the
   Fuji RSR power-band case allows a gearbox change (no more blanket refusal).
2. Give repeated driver feedback about a stiff car over kerbs — compliance is
   raised in the tuning priority unprompted, with an explicit instruction.
3. Give newer feedback contradicting older feedback — the Latest block dominates
   and per-field trend tags read current/improving/worsening/resolved.

### Deferred / limitations
`inside_wheel_spin` & `rear_platform_stiffness` subtypes deferred (no
per-wheel-slip / no damper baseline); `kerb_unload_spin` is a count-proxy, not
true spatial proximity; the LSD `worsened`-verdict join matches the DB
`recommendation_text` blob for `"lsd_accel"` (functional but the one fragile
join — a structured follow-up candidate); no UI surface for the new diagnosis
keys yet (a follow-on story); the 8 pre-existing track-modelling allowlist
failures are not this sprint's.

---

## Setup Builder Engineering Validation Gate (Group 41) (2026-07-05)

> Branch `ofr2-quali-race-disciplines` (built on top of Group 40).
> Backend + UI. Production files: `strategy/setup_diagnosis.py`,
> `strategy/driving_advisor.py`, `strategy/_setup_constants.py` (NEW),
> `strategy/_rec_parser.py`, `data/setup_history.py`, `ui/setup_builder_ui.py`.
> Full docs: `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 41),
> `docs/UAT_SETUP_BRAIN.md` (manual checklist).
> **Full suite: 5505 pass / 8 fail / 6 skip** — the 8 failures are the SAME
> pre-existing frozen-allowlist guard tests
> (`ui/track_modelling_ui.py::_tm_restore_last_track`, unrelated track-modelling
> tech debt, NOT this sprint), zero new regressions.

### What was built
A hard gate between the AI's raw setup output and what the driver can see or
apply. Unsafe or malformed recommendations are blocked; only validator-approved
changes reach the "CHANGES TO MAKE" section and the Apply button.

- **RECOMMENDATION LIFECYCLE.** Explicit statuses — generated,
  validation_failed, retry_requested, retry_failed, approved,
  approved_with_warnings, fallback_generated, blocked_no_safe_recommendation.
  `APPROVED_STATUSES = {approved, approved_with_warnings, fallback_generated}`
  in `strategy/_setup_constants.py`.
- **SINGLE FINALISATION FUNNEL.** `_finalise_recommendation` in
  `driving_advisor.py` — both AI paths (`build_setup_advice_response`,
  `build_combined_setup_response`) route through it, producing a frozen
  `SetupRecommendationResult` dataclass (status, approved_changes,
  approved_fields, rejected_changes, analysis, primary_issue,
  engineering_errors, validation_warnings, fallback_used, raw_json). Fields are
  embedded into the returned JSON (keys: recommendation_status, changes,
  setup_fields, rejected_changes, engineering_validation_errors,
  validation_warnings, fallback_used).
- **DISPLAY SAFETY** (`ui/setup_builder_ui.py::_display_setup_result`). The
  "CHANGES TO MAKE IN CAR SETUP" section renders ONLY when status ∈
  APPROVED_STATUSES and approved_changes is non-empty (iterating
  approved_changes only). The Apply button is HIDDEN (not just disabled) unless
  approved-ish with non-empty approved_fields, and applies approved_fields only
  (via `SetupFormWidget.apply_ai_fields`). Rejected AI output appears only in a
  collapsed "Rejected AI output — not for use" section (validation_failed,
  retry_failed, blocked_no_safe_recommendation), visually distinct, no apply
  path.
- **VALIDATOR SEVERITY.** `strategy/setup_diagnosis.py` adds
  `ValidationFailure(code, message, severity)` and
  `validate_setup_engineering_structured()`; legacy
  `validate_setup_engineering` still returns byte-identical prefixed strings.
  ANY blocking-severity failure (safety-prefix OR structural — malformed_schema
  / invalid_units / locked-field) forces validation_failed (retry_failed if
  retried) and approved_changes=[]. out-of-range is a WARNING because the
  clamping mechanism forces the applied value back into range (the clamped
  in-range value is what lands in approved output).
- **NEW BLOCKING RULES.** `snap_throttle_lsd_accel_gate` (snap_throttle_induced
  wheelspin + lsd_accel increase > 4); `kerb_strike_rh_over_increment`
  (kerb_strike bottoming + rear ride-height increase > 3mm); `gearbox_fake_field`
  (transmission_max_speed_kmh used as an actionable field);
  `gearbox_ratio_inversion` (a gear ratio not strictly lower than the gear
  below it). **NEW WARNING:** `gearbox_out_of_range` (final_drive outside
  2.5–6.0 or any gear outside 0.5–4.0 — conservative invented constants pending
  per-car range data).
- **REAL GEARBOX FIELDS.** final_drive and gear_1..gear_6 are now actionable
  setup fields (added to `_CANONICAL_SETUP_PARAMS` and
  `_CAT_FIELDS["transmission"]`; `_normalise_changes` expands a
  `gear_ratios:[...]` list into individual gear_N keys; surfaced/applied via
  SetupFormWidget). transmission_max_speed_kmh is DEMOTED to display-only (in
  `_DISPLAY_ONLY_FIELDS`) — still readable for diagnosis / top-speed-target
  classification, but stripped from approved_changes/approved_fields and never
  emitted as an actionable change. `gearbox_category_mismatch` now also blocks
  final_drive/gear_1..6 changes when the gearing diagnosis is a preserve
  category.
- **STRICT RETRY CONTRACT.** `_build_retry_prompt` lists each blocking failure
  code + max allowed delta + forbidden fields and forbids repeating rejected
  changes. A retry that still has any blocking failure becomes retry_failed
  (never approved). The old banner wording "survived a correction attempt" is
  removed; the reworded banner reads "AI recommendation rejected after retry".
- **DETERMINISTIC FALLBACK ENGINE.** `_build_deterministic_fallback` now emits
  1–3 real conservative changes that pass the same validator (respecting
  ride-height increment / LSD subtype / rake gates); if nothing safe can be
  produced the status is blocked_no_safe_recommendation with a "run more laps"
  message.
- **PERSISTENCE RESPECTS VALIDATION STATE.** `data/setup_history.py::save_entry`
  takes `validation_status` and routes non-approved statuses to a
  `_rejected_<config_id>` diagnostic bucket instead of the primary/current
  bucket; the DB `setup_recommendations` row now carries the final lifecycle
  status (`strategy/_rec_parser.py` extracts recommendation_status from the
  JSON) instead of the default 'proposed'.
- **WORDING / LOGIC FIXES.** kerb_strike bottoming is described distinctly from
  true floor contact and no longer forces ride-height as "required";
  snap_throttle_induced wheelspin no longer asserts "inside rear spins" (no
  inside-wheel telemetry exists) and is classified as mixed setup/driver; the
  old "top speed below target ⇒ no gearing change" leakage is removed so gearing
  can change on power-band/driver evidence (with a display-only caveat on
  transmission_max_speed_kmh).
- **DEDUP.** `_ENG_SAFETY_PREFIXES` deduplicated to a single shared constant
  `ENG_SAFETY_PREFIXES` in `strategy/_setup_constants.py`, imported by both
  driving_advisor and setup_diagnosis.
- **AMENDMENT B (UI real-estate cleanup).** The redundant read-only "Race
  Conditions (from Event Planner)" group box was removed from the Setup Builder
  header (it duplicated Event Planner + the Home Race Setup card, all sourced
  from the same EventContext). The 320px header cap was lifted so the space
  flows to the setup view. `_sync_setup_builder_from_event` retains all
  functional side effects (BoP toggle, setup permissions, spinbox rebind,
  RE-brief load, prefill, qual-form sync).
- **AMENDMENT C.** The Home "Race Setup" card now shows a Damage line (the one
  race-condition field that had only been on the removed Setup Builder block),
  sourced from `EventContext.damage`.

### New / updated test files

| Test file | Coverage |
|-----------|----------|
| `tests/test_group41_validation_gate.py` (NEW) | AC0–AC14: lifecycle statuses, finalisation funnel + embedded JSON keys, display-safety gating (CHANGES/Apply visibility), validator severity (blocking vs out-of-range warning), the four new blocking rules + the out-of-range warning, real gearbox fields + transmission_max_speed_kmh demotion, strict retry contract → retry_failed, deterministic fallback / blocked_no_safe_recommendation, persistence bucket routing + DB lifecycle status, wording/logic fixes, Amendments B & C |

### Acceptance criteria — status
All story ACs (AC0–AC14) verified by the new suite; zero new regressions. The
8 pre-existing frozen-allowlist failures are unrelated track-modelling tech
debt and remain for the track-modelling owner.

### Test-run note (Windows / Python 3.14)
Running the ENTIRE suite in one process can hit a flaky native PyQt teardown
segfault. Running in two halves (or by group) completes clean at 5505 passed /
8 pre-existing failures / 6 skipped. This is an environmental test-isolation
artifact, not a product defect.

### Manual UAT
Full manual checklist (Porsche 911 RSR '17 at Fuji): `docs/UAT_SETUP_BRAIN.md`.

### Deferred / limitations
- Gearbox ratio ranges (final_drive 2.5–6.0, gears 0.5–4.0) are invented
  constants, not per-car data; `gearbox_out_of_range` is therefore a WARNING,
  not a hard block, to avoid false-blocking legitimate setups. Tighten to
  per-car ranges + blocking once range data exists.
- The DB `_rec_parser` stores the full JSON blob as recommendation_text for
  structured setup responses (pre-existing behaviour, not human-readable in the
  DB).
- Flaky full-suite PyQt segfault on Windows/Py3.14 (see above).

---

## Rule-First Setup Brain (Group 42) (2026-07-05)

> Branch `ofr2-quali-race-disciplines` (built on top of Group 41).
> Backend + UI + DB. New production files (all `strategy/`, pure Python):
> `setup_knowledge_base.py`, `setup_driver_profile.py`, `setup_rule_engine.py`,
> `setup_plan.py`, `setup_ai_audit.py`. Changed: `strategy/_setup_constants.py`,
> `strategy/driving_advisor.py`, `strategy/_rec_parser.py`,
> `data/setup_history.py`, `data/session_db.py` (v11), `ui/setup_builder_ui.py`,
> `ui/setup_form_widget.py`.
> Full docs: `docs/RULE_FIRST_SETUP_BRAIN.md` (architecture),
> `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42), `docs/UAT_SETUP_BRAIN.md`
> (Rule-First Setup Brain UAT).
> **All Group 42 tests green (136 new + 17 rewritten); zero new regressions.**
> The only failures remain the SAME 8 pre-existing frozen-allowlist guards
> (`ui/track_modelling_ui.py::_tm_restore_last_track`, unrelated track-modelling
> tech debt).

### What was built
The Setup Brain is inverted from AI-first to **RULE-FIRST**. The deterministic
rule engine authors setup changes; the AI is an **audit-only** layer that can
approve / warn / reject / request-more-data but **cannot author actionable setup
changes**. ONE source of truth for actionable recommendations: the rule engine.

- **NEW FLOW** (`build_combined_setup_response`): diagnose → `build_driver_profile()`
  → `run_rule_engine()` → `SetupPlan` → `plan_to_raw_data` → `_normalise_changes`
  → `validate_setup_engineering_structured` → if blocking `_build_deterministic_fallback`
  (NOT AI) → else if API key `call_api` for AI AUDIT ONLY → `parse_audit_response`
  (strips canonical setup keys) → `map_audit_to_finaliser` → `_finalise_recommendation`
  (unchanged funnel).
- **RULE CATALOGUE** (`setup_knowledge_base.py`): `register_pack`/`get_all_rules`/
  `resolve_delta`; enums RulePhase/RiskLevel/ConfidenceLevel/DrivetrainType/
  CarClass/SessionType; NamedTuples SetupRule/SetupEvidence; **22 rules** — Pack A
  A1–A8 (safety invariants), Pack B B1–B6 (driver-style adaptation), Pack C/D
  (C1_entry_lsd_decel, C2_entry_brake_bias, C3_mid_arb_rear, C4_mid_rear_aero,
  C5_exit_lsd_accel, C6_exit_rear_aero, C7_kerb_arb_rear, C8_kerb_rh_rear —
  handling-phase starter set; remaining per-setting Pack C deferred; extensible
  via register_pack). Delta resolvers are named-string lookups in
  `_DELTA_RESOLVERS` (no stored callables).
- **DRIVER PROFILE AS DATA** (`setup_driver_profile.py`): `DriverProfile`
  NamedTuple + `DriverStyleAlignment` enum; `build_driver_profile()` derives 8
  booleans (prefers_front_bite, dislikes_floaty_front, dislikes_snap_exit,
  trail_braker, rotation_without_snap, prefers_rear_stability, protects_downforce,
  race_values_consistency) from the existing `PERSONAL_DRIVER_TUNING_MODEL`/
  `DRIVER_HARD_CONSTRAINTS`; never raises. Consumed by the engine for ranking +
  contraindications.
- **RULE ENGINE** (`setup_rule_engine.py`): `SetupChangeIntent`/`SetupPlan`
  NamedTuples; `run_rule_engine(...)` — Pack A protects fields, conflict
  resolution moves both same-field opposite candidates to rejected with
  `conflict:<id>`, no-op exclusion, gear-count gating, confidence-downgrade hook;
  `RuleOutcomeStore` fire/success counts keyed rule_id/car/track/
  driver_profile_version, `get_success_rate` None below MIN_OUTCOME_SAMPLES;
  never raises → empty plan on error.
- **AI AUDIT ONLY** (`setup_ai_audit.py`): `AuditStatus` (APPROVED/
  APPROVED_WITH_WARNINGS/REJECTED/NEEDS_MORE_DATA) + `AuditResult`;
  `build_audit_prompt` 8 labelled sections; `parse_audit_response(text,
  canonical_params)` STRIPS any key in canonical_params (logs stripped_fields),
  unknown status → NEEDS_MORE_DATA, never raises; `map_audit_to_finaliser` —
  REJECTED/NEEDS_MORE_DATA + no blocking → approved_with_warnings advisory
  (`ai_audit_rejected_advisory`), a blocking engineering failure ALWAYS wins.
- **CONSTANTS** (`_setup_constants.py`): `RULE_ENGINE_VERSION="42.0"`,
  `MIN_OUTCOME_SAMPLES=3`, `LOW_SUCCESS_RATE=0.40`,
  `AI_AUDIT_REJECTED_ADVISORY="ai_audit_rejected_advisory"` (NOT in
  APPROVED_STATUSES). APPROVED_STATUSES unchanged.
- **VOICE PATH** (`build_setup_advice_response`): NARRATION-ONLY via
  `_strip_actionable_for_voice(data)` (zeroes changes=[]/setup_fields={}
  pre-normalisation). Full rule-first voice rebuild deferred.
- **DB v11** (`data/session_db.py::_migrate_v11`): 8 nullable TEXT columns on
  `setup_recommendations` (deterministic_plan_json, ai_audit_json,
  validation_status, approved_changes_json, rejected_changes_json,
  diagnosis_json, driver_profile_version, rule_engine_version); blob preserved +
  POPULATED on insert (`_rec_parser.py` + `insert_setup_recommendations`).
- **LEGACY SAFETY** (closes Group 41's caveat): `data/setup_history.py` adds
  `is_legacy_unknown`/`normalise_validation_status`/`LEGACY_UNKNOWN` — a rec with
  absent/None/unrecognised status is legacy_unknown = DISPLAY-ONLY, NO Apply.
- **LEARNING** — `RuleOutcomeStore` FOUNDATION ONLY (downgrade hook implemented
  + unit-tested; live wiring + persistence DEFERRED, `rule_outcome_store=None`;
  no fake ML).
- **UI** — section order diagnosis → "Pit Crew recommendation" (each change with
  a collapsed "Why Pit Crew recommended this") → "Protected fields" → "Rejected
  candidate changes" → "AI audit" → "Rejected AI output — not for use"; legacy
  banner; Apply relabelled "Apply Pit Crew recommendation", hidden unless status
  ∈ APPROVED_STATUSES AND approved changes present AND not legacy.
- **RESPONSE CONTRACT** — per-change keys inside each `changes` item (symptom,
  evidence, rule_id, rationale, rejected_alternatives, risk_level,
  confidence_level, driver_style_alignment) + top-level `ai_audit`,
  `deterministic_plan` {proposed_count, rejected_candidate_count,
  protected_fields}, `protected_fields`.

### New / updated test files

| Test file | Coverage |
|-----------|----------|
| `tests/test_group42_rule_first_engine.py` (NEW) | The rule-first flow: `run_rule_engine` produces the plan (Pack A protected fields, conflict resolution → rejected `conflict:<id>`, no-op exclusion, gear-count gating, confidence downgrade), `plan_to_raw_data` feeds the funnel, and the deterministic engine — not the AI — authors changes |
| `tests/test_group42_ai_audit_only.py` (NEW) | AI is audit-only: `parse_audit_response` strips any canonical setup field key (logs stripped_fields), unknown status → NEEDS_MORE_DATA, never raises; `map_audit_to_finaliser` (REJECTED/NEEDS_MORE_DATA + no blocking → approved_with_warnings advisory; blocking engineering failure always wins) |
| `tests/test_group42_driver_style.py` (NEW) | `build_driver_profile()` derives the 8 booleans from the driver constants, never raises (neutral defaults), and the engine ranks/contraindicates against the profile (driver_style_alignment aligned/neutral/caution) |
| `tests/test_group42_legacy_storage.py` (NEW) | DB v11 migration + the 8 new columns populated on insert; `is_legacy_unknown`/`normalise_validation_status`/`LEGACY_UNKNOWN` — absent/unknown status → legacy_unknown display-only; `_rejected_` bucket routing (`ai_audit_rejected_advisory`) |
| `tests/test_group42_handling_phases.py` (NEW) | The Pack C/D handling-phase rules (C1–C8) fire on the right phase/symptom, and RuleOutcomeStore's confidence-downgrade hook (samples≥MIN_OUTCOME_SAMPLES + success_rate<LOW_SUCCESS_RATE) |
| `tests/test_group42_voice_path_safety.py` (NEW) | `_strip_actionable_for_voice` zeroes changes/setup_fields so the voice path (`build_setup_advice_response`) can never surface actionable setup changes |
| `tests/test_group42_ui_gate.py` (NEW) | Display gate: "Pit Crew recommendation" vs "AI audit" sections, "Why Pit Crew recommended this" explainability, protected/rejected sections, legacy banner, Apply "Apply Pit Crew recommendation" hidden unless approved + non-legacy |
| `tests/test_group38_setup_diagnosis.py` (rewritten) | TestRegenerateOnceOrchestration — re-pointed to the rule-first flow |
| `tests/test_group40_diagnosis_hardening.py` (rewritten) | TestAC9DeterministicFallback — re-pointed to `_build_deterministic_fallback` on the rule-first blocking path |
| `tests/test_group41_validation_gate.py` (rewritten) | 2 tests re-pointed to the rule-first funnel |
| `tests/test_group27_setup_overhaul2.py` (rewritten) | 1 test re-pointed |

### Acceptance criteria — status
All Group 42 tests green (136 new + 17 rewritten); zero new regressions. The 8
pre-existing frozen-allowlist failures are unrelated track-modelling tech debt.

### Test-run note (Windows / Python 3.14)
Running the ENTIRE suite in one process can hit a flaky native PyQt teardown
segfault; run in two halves (or by group). Environmental artifact, not a defect.

### Manual UAT
Full manual checklist (Porsche 911 RSR '17 at Fuji): `docs/UAT_SETUP_BRAIN.md`
(Rule-First Setup Brain UAT) — confirms the rule engine authors safe
driver-aligned traction/LSD changes (no generic ride-height raise, downforce not
cut first), the AI audit cannot author changes, legacy_unknown is display-only,
and the voice path is narration-only.

### Deferred / limitations
- `RuleOutcomeStore` live wiring + cross-session persistence (foundation only
  today).
- The remaining per-setting Pack C rules (C/D is a handling-phase starter set,
  extensible via `register_pack`).
- Full DB migration off the recommendation_text JSON blob (the 8 v11 columns are
  populated, but the blob is still the primary store).
- Full rule-first rebuild of the voice path (narration-only for now).
- The 8 pre-existing track-modelling allowlist failures remain for the
  track-modelling owner.

---

## Setup Brain Learning & Race Context (Group 46) (2026-07-06)

> Branch `ofr2-quali-race-disciplines` (built on top of Group 45). Backend + UI +
> DB. Changed: `data/session_db.py` (v12), `strategy/driving_advisor.py`,
> `strategy/setup_rule_engine.py`, `strategy/setup_diagnosis.py`,
> `strategy/setup_baseline.py`, `strategy/_setup_constants.py`, `ui/dashboard.py`,
> `ui/setup_builder_ui.py`.
> Full docs: `docs/RULE_FIRST_SETUP_BRAIN.md` (§ 15 "Setup Brain Learning & Race
> Context" — the dedicated honest account), `docs/SETUP_BRAIN_UPGRADE.md`
> (§ Group 46 changelog), `docs/UAT_SETUP_BRAIN.md` (§ Group 46 UAT).
> **All Group 46 tests pass (122 new); version/schema tests reconciled; the
> ~7–20 pre-existing frozen-allowlist / OFR failures are KNOWN, unrelated, and
> untouched.** Run the suite IN HALVES on Win/Py3.14 (flaky PyQt teardown
> segfault).

### What was built
The rule-first Setup Brain now **learns across sessions** (a real SQLite-backed
rule-outcome feed), its **Analyse** recommendations are shaped by **fuel load**
and by **fuller per-gear telemetry**, the from-scratch **Baseline** is now
**numerically biased by session type**, and the Porsche pack inherits the new
confidence layers — all **without** changing *who* authors setups. The
architecture is preserved: telemetry + feedback + setup + car/track/session
context + learning history → deterministic diagnosis → deterministic rule
recommendation → validation → AI audit-only → approved-only display/apply. The AI
still cannot author setup values / add approved fields / un-block / un-reject /
author per-gear values; both paths work with the AI disabled; the Apply gate is
unchanged. `RULE_ENGINE_VERSION` is now **"46.0"** (was "45.0"); DB `user_version`
is now **12** (was 11); `HIGH_FUEL_MULTIPLIER_THRESHOLD=5.0`; `HIGH_SUCCESS_RATE=0.60`.

- **Cross-session learning persistence + feed**: NEW SQLite table
  `learning_outcomes` (`data/session_db.py::_migrate_v12`; PRAGMA user_version
  11→12; additive `CREATE TABLE IF NOT EXISTS`, idempotent; columns
  id/ts/car_id/track/layout_id/session_id/session_type/rule_id/source_path/verdict/
  confidence/driver_profile_version/rule_engine_version + index on
  (car_id,track,layout_id)) — **DELIBERATELY NOT persisted to
  `data/setup_history.json`** (that file is a user-local artifact owned by
  `setup_history.py`; learning lives entirely in the gitignored DB).
  `record_learning_outcome(...)` (INSERT, never raises) written from the OFR-1
  scoring pass (`ui/dashboard.py::_trigger_scoring_pass`) after `persist_score`,
  per approved rule_id, skipping insufficient_data;
  `get_learning_outcomes(car_id,track,layout_id)` returns `[]` on any error. FEED:
  `build_combined_setup_response` loads scoped rows into a real `RuleOutcomeStore`
  before `run_rule_engine` (improved→fire+success; worsened/neutral→fire;
  insufficient_data→skip); UPGRADE (`>=MIN_OUTCOME_SAMPLES=3` samples AND
  success_rate `>=HIGH_SUCCESS_RATE=0.60` → +1) / DOWNGRADE (`<LOW_SUCCESS_RATE=0.40`
  → −1), one step, validator-gated, cannot un-block/un-reject/author;
  `learning_influence` set ONLY when a step actually happened; `_learning_note`
  reflects real loaded history.
- **Fuel-multiplier influence (Analyse)**: `diagnosis["fuel_multiplier"]` (value) +
  `diagnosis["fuel_high"]` (`>=5.0`; unknown→False) injected; `_process_rule`
  UPGRADES confidence of traction/stability fields (`_FUEL_TRACTION_STABILITY_FIELDS`
  = lsd_accel/lsd_initial/arb_rear/aero_rear/ride_height_rear, delta>0), NOTE-ONLY
  for rotation/aero-cut (`_FUEL_ROTATION_FIELDS`, delta<0); NO new deltas;
  `fuel_influence` set only when the effect occurred + appended to the change's
  `evidence`; fuel=1.0/absent → no bias, no claim.
- **Session-specific NUMERICAL baseline tuning**: `_SESSION_BIAS_TABLE`
  (qualifying/sprint/endurance/practice/unknown → {field:delta}) accumulated into
  the SAME bias dict as the driver-profile table; `_normalise_session_for_bias`
  (endurance = race & duration_mins>=60; duration<=0 NOT endurance);
  `build_baseline_setup` + `build_baseline_setup_response` gained a `duration_mins`
  param; a per-field `session_changed` flag gates `session_influence` so it claims
  a session bias ONLY for fields that actually moved.
- **Fuller per-gear intelligence (REAL detection)**: `setup_diagnosis` genuinely
  detects `wheelspin_by_gear` (throttle>0.7, speed>2 m/s, rear-wheel-speed>1.3×,
  bucketed by active gear, normalized PER-LAP); `bog_by_gear`/`lockups_by_gear`
  honestly None; `_emit_per_gear_changes` proposes `gear_N` ONLY on a real indexed
  signal (rev-limiter-in-gear on gear_too_short OR `wheelspin_by_gear[N] >=
  _PER_GEAR_WHEELSPIN_THRESHOLD=2.0`); conservative ±0.03; rule_id `"PG_{N}"`,
  `source_label` "per-gear rule"; `final_drive` (B5/B5b) untouched;
  `per_gear_explanation` records proposed/not-proposed for every gear.
- **Porsche RSR extension**: existing Pack P auto-benefits from the fuel/tyre/
  learning confidence layers (no new authored rule); AC37 benchmark verified.

### New test files

| Test file | Coverage |
|-----------|----------|
| `tests/test_group46_learning_persistence.py` (NEW) | `_migrate_v12` creates `learning_outcomes` (idempotent, additive, user_version 11→12); `record_learning_outcome` inserts + never raises + skips insufficient_data; `get_learning_outcomes` scopes by car_id/track/layout_id + returns `[]` on error; NOT written to `setup_history.json`; the feed loads scoped rows into a real `RuleOutcomeStore` (improved→fire+success; worsened/neutral→fire; skip insufficient_data); UPGRADE `>=3` samples & `>=0.60`, DOWNGRADE `<0.40`, one step, validator-gated; learning cannot un-block/un-reject/author; `learning_influence`/`_learning_note` honesty; **AC16 single-winner-per-field** learning-safety assertion |
| `tests/test_group46_fuel_influence.py` (NEW) | `fuel_multiplier`/`fuel_high` injected (unknown→False, never a false claim); high fuel UPGRADES traction/stability field confidence (`_FUEL_TRACTION_STABILITY_FIELDS`, delta>0), NOTE-ONLY for rotation/aero-cut (`_FUEL_ROTATION_FIELDS`, delta<0, no downgrade); NO new deltas (magnitudes unchanged); `fuel_influence` set only when the effect occurred; fuel=1.0/absent → no bias; **fuel-renders-into-evidence** test (the string appears in the change's `evidence` list / UI) |
| `tests/test_group46_baseline_session_modifiers.py` (NEW) | `_SESSION_BIAS_TABLE` accumulates into the same bias dict (clamp/round/validator unchanged); `_normalise_session_for_bias` (qualifying / sprint <60 / endurance >=60 / practice / unknown; duration<=0 NOT endurance); `duration_mins` threaded into `build_baseline_setup`/`build_baseline_setup_response`; session baselines differ numerically; `session_changed` gate → `session_influence` claims a bias only for fields that actually moved (else "session noted — no numerical change"; unknown → "") |
| `tests/test_group46_per_gear.py` (NEW) | `wheelspin_by_gear` genuinely detected + normalized per-lap; `bog_by_gear`/`lockups_by_gear` honestly None; `_emit_per_gear_changes` proposes `gear_N` ONLY on real indexed evidence (limiter-in-gear on gear_too_short OR wheelspin `>=2.0`); conservative ±0.03; gated on `gearbox_flag=="may_change"`; same clamp + strict-`>` monotonic + validator; rule_id `"PG_{N}"`/`source_label` "per-gear rule"; `final_drive` untouched; "top speed low" alone with no evidence → no gear change + explanation; `per_gear_explanation` per every gear |
| `tests/test_group46_porsche_pack.py` (NEW) | **AC37** RSR/Fuji integrated regression (50 min / high tyre + fuel / rear-loose + mid-push + floaty-front / snap-throttle-wheelspin + top-speed-low + entry-stable + possible-bottoming): traction-first before/instead of aero-cut; no rear-downforce reduction; no rearward brake bias; no generic ride-height raise without bottoming confidence; no top-speed gear-lengthening as the primary wheelspin fix; no AI-authored values; passes the Apply gate; Pack P auto-benefits from the fuel/tyre/learning layers |
| `tests/test_group46_ui_explainability.py` (NEW) | `learning_influence` / `fuel_influence` / `session_influence` render honestly (positive claim only when the effect actually occurred, else the explicit neutral string); baseline labels never claim telemetry; per-gear `source_label`; the fuel influence appears in the existing UI evidence rows (at-most-2-new-rows constraint respected) |

### Reconciled existing tests
Version/schema tests were updated for **legitimate** changes (not to paper over
regressions): (1) `RULE_ENGINE_VERSION` "45.0" → "46.0" (`test_group42_rule_first_engine`);
(2) DB `user_version` → 12 in `test_group42_legacy_storage`,
`test_group18b_rec_persistence`, `test_session_db`, `test_group18e_setup_history`.

### Acceptance criteria — status
All Group 46 tests pass (122 new). The ~7–20 pre-existing frozen-allowlist / OFR
failures are known, unrelated, and untouched.

### Test-run note (Windows / Python 3.14)
Running the ENTIRE suite in one process can hit a flaky native PyQt teardown
segfault; run in two halves (or by group). Environmental artifact, not a defect.

### Deferred / limitations
- **Baseline path does NOT consume rule-confidence learning** — it does not run the
  rule engine, so baseline change dicts carry an honest EMPTY `learning_influence`;
  learning shapes the Analyse path only.
- **`source_path="Baseline"` recording is not yet wired** — the baseline path does
  not insert a scored `setup_recommendations` row, so only `"Analyse"` is written
  in production today (schema/method support it).
- **`learning_outcomes.session_type` is stored as `""`** — `setup_recommendations`
  has no session_type column; scope is enforced by car_id + track + layout_id; a
  JOIN / column is deferred.
- **`bog_by_gear` + `lockups_by_gear` per-gear detection deferred** — GT7's 10 Hz
  telemetry has no reliable signal; per-gear evidence today is limiter + wheelspin.
- A fuel-specific *delta* rule (fuel is confidence/ranking-only, not a new change).
- The ~7–20 pre-existing frozen-allowlist / OFR failures remain for their owners.

---

## Setup Brain Intelligence Expansion (Group 45) (2026-07-06)

> Branch `ofr2-quali-race-disciplines` (built on top of Group 44). Backend + UI.
> Changed: `strategy/setup_rule_engine.py`, `strategy/driving_advisor.py`,
> `strategy/setup_knowledge_base.py`, `strategy/setup_baseline.py`,
> `strategy/_setup_constants.py`, `ui/setup_builder_ui.py`.
> Full docs: `docs/RULE_FIRST_SETUP_BRAIN.md` (§ 14 "Setup Brain Intelligence
> Expansion" — the dedicated honest account), `docs/SETUP_BRAIN_UPGRADE.md`
> (§ Group 45 changelog), `docs/UAT_SETUP_BRAIN.md` (§ Group 45 UAT).
> **All Group 45 tests pass; 3 existing tests reconciled for legitimate
> behaviour changes; the ~18 pre-existing frozen-allowlist / schema failures are
> KNOWN, unrelated, and untouched.** Run the suite IN HALVES on Win/Py3.14
> (flaky PyQt teardown segfault).

### What was built
The rule-first Setup Brain became **context-aware** without changing *who*
authors setups. Session type, tyre-wear, drivetrain, and car-class now genuinely
shape **which rules fire and how confident / ranked they are** — but **delta
magnitudes are unchanged** (context affects filtering, confidence, ranking,
contraindication, and explanation only; it never invents precision). The
architecture is preserved: Pit Crew owns the decision, the AI stays audit-only,
both Analyse and Baseline run through the one validator → funnel → renderer →
Apply gate, and everything works with the AI disabled. `RULE_ENGINE_VERSION` is
now **"45.0"** (was "42.0"); `HIGH_TYRE_WEAR_THRESHOLD=5.0`.

- **Engine scope filter** (`_scope_matches`): `applies_session` /
  `applies_drivetrain` / `applies_car_class` are now enforced at runtime;
  `any`/`None` = wildcard-permissive (unknown never filters); **Pack A EXEMPT**;
  all-rules-filtered-out → valid empty `SetupPlan` (no raise).
- **Context resolution** (`driving_advisor.py`): Analyse reads `_event_ctx`
  (tyre_wear → tyre_wear_multiplier, fuel_multiplier, duration_mins) + new params
  `purpose` → `SessionType`, `car_specs.category` → `CarClass`, `drivetrain`
  (precedence: UI combo > `CAR_DRIVETRAIN_OVERRIDES` > empty DB → None);
  **Baseline receives scalar params only** (no EventContext).
- **Driver-profile active weighting**: bounded {−1,0,+1} rank tiebreaker when
  confidence is equal (magnitudes UNCHANGED); baseline `_PROFILE_BIAS_TABLE`
  gained trail_braker → brake_bias −0.5 + rotation_without_snap → lsd_decel −2.
- **Session / tyre / fuel**: session biases confidence (quali → front-bite /
  trail-braker; race → safety-phase / consistency; endurance = race +
  duration>=60); high tyre-wear CONTRAINDICATES 4 tyre-abusing rules (B3,
  C1_entry_lsd_decel, C3_mid_arb_rear, C7_kerb_arb_rear); increase-lock /
  downforce rules NOT suppressed; fuel READ but only informational.
- **Porsche Pack P** (`register_pack("P",...)`): rule P1 cautious traction-first
  lsd_accel increase (rr + gr3, contraindicated on `snap_oversteer_exit`); no P2
  (existing Pack A A2 covers rear-downforce, so P2 was intentionally omitted);
  asserts RR via `CAR_DRIVETRAIN_OVERRIDES`.
- **Gearbox**: B5b (gear_too_long → final_drive_up) added to B5;
  "limiter_before_braking" maps to existing gear_too_short (documented, not
  faked); `per_gear_limiter_evidence` exposed, full per-gear rules DEFERRED;
  monotonic ordering now NON-INCREASING (equal ratios allowed; engine +
  `gearbox_ratio_inversion` validator both strict-`>`).
- **Learning seam**: live-but-EMPTY `RuleOutcomeStore` (was None) — hook wired
  but never fires without samples; `_learning_note`; persistence + a
  success-recording feed DEFERRED; learning CANNOT un-block / un-reject / bypass
  validation / make the AI actionable.
- **Explainability**: `source_label` / `session_influence` /
  `car_drivetrain_influence` / `pack` on each approved + rejected change,
  populated HONESTLY (a positive claim only when the context was used, else the
  explicit neutral string); baseline labels never claim telemetry evidence.

### New test files

| Test file | Coverage |
|-----------|----------|
| `tests/test_group45_engine_scope.py` (NEW) | `_scope_matches` enforcement: `applies_session` / `applies_drivetrain` / `applies_car_class` now filter at runtime; `any`/`None` is wildcard-permissive (unknown context never drops a rule); Pack A safety rules are EXEMPT from scope filtering; all-rules-filtered-out returns a valid empty `SetupPlan` (no raise) |
| `tests/test_group45_gear_monotonic.py` (NEW) | Gearbox: B5b (gear_too_long → final_drive_up) proposes correctly; B5 (gear_too_short → final_drive_down) unchanged; limiter_limited stays preserve; monotonic ordering is NON-INCREASING (equal adjacent ratios ALLOWED, only a strict inversion rejected "monotonic ordering violation"); engine and the `gearbox_ratio_inversion` validator agree on strict-`>` |
| `tests/test_group45_context_signals.py` (NEW) | Session bias (quali / race / endurance confidence shifts, magnitudes unchanged); high tyre-wear (`>=5.0`) sets `tyre_wear_high` and suppresses exactly the 4 tyre-abusing rules (B3, C1, C3, C7) while NOT suppressing increase-lock / downforce rules; missing tyre/fuel context yields the honest "not available" note; fuel read but only informational |
| `tests/test_group45_porsche_pack.py` (NEW) | Pack P registered; rule P1 fires on snap-throttle wheelspin for rr+gr3, contraindicated on `snap_oversteer_exit`; no P2 (A2 covers rear-downforce, all cars); changes labelled "Porsche-specific rule"; RR asserted via `CAR_DRIVETRAIN_OVERRIDES`, overridable by the manual combo |
| `tests/test_group45_explainability.py` (NEW) | Each approved + rejected change carries `source_label` / `session_influence` / `car_drivetrain_influence` / `pack`; honest population (positive claim only when context used, else explicit neutral string); baseline `_LABEL_*` labels never claim telemetry |
| `tests/test_group45_learning.py` (NEW) | Production constructs a live-but-EMPTY `RuleOutcomeStore`; the hook never fires without samples (behaviour unchanged); `_learning_note` present; learning cannot un-block a safety rule / un-reject / bypass validation / make the AI actionable |
| `tests/test_group45_baseline_context.py` (NEW) | Baseline receives scalar `session_type` / `tyre_wear_multiplier` / `car_class` only (no EventContext); baseline `session_influence` records a session was noted but is NOT session-tuned; the new `_PROFILE_BIAS_TABLE` entries; the opposing lsd_decel biases net to zero on a both-flags profile |
| `tests/test_group45_ui_context.py` (NEW) | Both UI analyse handlers (`_setup_analyse_ai` / `_setup_analyse_ai_for_form`) and both baseline callers thread the new context params; the renderer shows a small `source_label` row |

### Reconciled existing tests
Three existing tests were updated for **legitimate** behaviour changes (not to
paper over regressions): (1) `RULE_ENGINE_VERSION` "42.0" → "45.0"; (2) the
baseline lsd_decel bias now nets differently with `rotation_without_snap`;
(3) the `gearbox_ratio_inversion` validator now uses strict `>` (allowing equal
adjacent ratios), agreeing with the engine.

### Acceptance criteria — status
All Group 45 tests pass. The ~18 pre-existing frozen-allowlist / schema failures
are known, unrelated, and untouched.

### Test-run note (Windows / Python 3.14)
Running the ENTIRE suite in one process can hit a flaky native PyQt teardown
segfault; run in two halves (or by group). Environmental artifact, not a defect.

### Deferred / limitations
- Cross-session `RuleOutcomeStore` persistence + a success-recording feed (e.g.
  from OFR-1 `recommendation_scoring` verdicts) — the seam is in place but EMPTY
  in production, so recommendations do not yet self-tune.
- Full per-gear individual ratio proposal rules — `per_gear_limiter_evidence`
  exists for future use; broad final-drive-only logic ships today.
- Session-specific NUMERICAL baseline tuning — session context is recorded on
  baseline changes but does not yet change baseline values.
- A fuel-specific rule — the fuel multiplier is read but only informational.
- The two opposing lsd_decel baseline bias entries (`race_values_consistency` +2
  vs `rotation_without_snap` −2) net to zero on a profile carrying both flags.
- The ~18 pre-existing frozen-allowlist / schema failures remain for their owners.

---

## Rule-First Setup Baseline Generator (Group 44) (2026-07-06)

> Branch `ofr2-quali-race-disciplines` (built on top of Group 43). Delivered via
> the feature-factory chain. Backend + UI. New production file:
> `strategy/setup_baseline.py` (NEW, pure Python). Changed:
> `strategy/driving_advisor.py`, `ui/setup_form_widget.py`,
> `ui/setup_builder_ui.py`, `ui/dashboard.py`.
> Full docs: `docs/RULE_FIRST_SETUP_BRAIN.md` (§ 3b Group 44 — the from-scratch
> baseline generator as a second rule-first authoring path).
> **All Group 44 tests green (86 backend + 64 UI/integration); 406 green together
> with group41 + group42 (all) + group43; 0 fail; zero new regressions.**
> The only failures remain the SAME 8 pre-existing frozen-allowlist guards
> (`ui/track_modelling_ui.py::_tm_restore_last_track`, unrelated track-modelling
> tech debt).

### What was built
Group 43 disabled the ungated "Build Setup with AI" path, and since Group 42 the
AI is audit-only and cannot author a setup — leaving no way to produce a complete
starting setup for a car with **no telemetry**. Group 44 restores that
capability **deterministically, with the AI NEVER called**, via a **second
rule-first authoring path** distinct from the delta/Analyse path.

- **Why not `run_rule_engine`?** The Analyse engine emits DELTAS off a telemetry
  diagnosis; with no telemetry almost no rules fire, so it cannot author a
  from-scratch full-field setup. A separate ABSOLUTE-VALUE author was required.
- **BACKEND** (`strategy/setup_baseline.py`): `NEUTRAL_SEEDS` (single source of
  truth for neutral physics defaults; matches the form seeds in
  `ui/setup_form_widget.py` — lsd_front_initial/accel/decel take the FORM values
  10/15/5, differing from the `ai_planner` parser fallbacks 0/0/0);
  `build_baseline_setup(car, ranges, drivetrain, num_gears, profile,
  allowed_tuning, tuning_locked) -> raw_data dict` (plan_to_raw_data shape)
  authors ALL 33 actionable `_CANONICAL_SETUP_PARAMS` (34 minus display-only
  transmission_max_speed_kmh) as ABSOLUTE values via neutral seed →
  driver-profile bias (`_PROFILE_BIAS_TABLE`) → clamp to `resolve_ranges(car)`.
- **GEARBOX** (`_build_gearbox_changes`): final_drive = midpoint of
  `_FINAL_DRIVE_RANGE (2.5,6.0)`; gear_1..gear_num_gears = a strictly-DECREASING
  geometric sequence inside `_GEAR_RATIO_RANGE (0.5,4.0)` — **monotonic by
  construction, so `gearbox_ratio_inversion` can never fire** — sized to the car's
  gear count (>6 capped, ≤1 → single gear@2.0, 0 → none); ranges
  function-local-imported from `setup_diagnosis` (source of truth, try/except
  fallback to local constants).
- **LOCKED categories** (via `_derive_locked_fields`) excluded from actionable
  output + named by human category (e.g. "Suspension, Aero") in the analysis text;
  tuning_locked=True → empty changes. Every change carries a source label
  ("neutral default" / "range midpoint" / "driver-profile biased" / "conservative
  default, not diagnosed" — the last is honest: camber/toe/dampers/springs/
  lsd_initial/lsd_front_initial have NO engineering authority; the baseline is a
  safe STARTING POINT, not an optimum).
- **ORCHESTRATOR** `DrivingAdvisor.build_baseline_setup_response(car_name, ranges,
  drivetrain, num_gears, allowed_tuning, tuning_locked, session_type="Race") ->
  JSON str`: `build_driver_profile()` → `build_baseline_setup` →
  `validate_setup_engineering_structured` (neutral baseline passed as BOTH the
  `setup` arg AND the proposed setup_fields so increment/comparison rules see zero
  delta) → `_filter_baseline_artifact_warnings` → `_finalise_recommendation` →
  JSON identical in shape to `build_combined_setup_response`. NO api_key read, NO
  call_api, NO audit; a clean neutral baseline returns status "approved" with
  validation_warnings == [].
- **WARNING FILTER** (`_filter_baseline_artifact_warnings`): drops ONLY
  WARNING-severity failures whose message contains "is a no-op" or "too many
  changes" (definitional artifacts of a full-field from==to baseline); ALL
  blocking failures pass through unfiltered — the severity guard `if vf.severity
  == "warning"` is the OUTER condition, proven unable to suppress a blocking
  failure.
- **FRONTEND**: new `_btn_baseline` "Build Baseline Setup" (enabled+visible; added
  to `_RACE_ALIASES`) in `ui/setup_form_widget.py` + `ui/setup_builder_ui.py`
  handlers `_generate_baseline_setup`/`_generate_baseline_setup_for_form` (daemon
  thread → `_baseline_result_queue` in `ui/dashboard.py`, polled) →
  `_display_baseline_result` re-enables the baseline button then DELEGATES to the
  shared `_display_setup_result` renderer + Apply gate (no duplication); advisor
  accessor `self._driving_advisor`; Group 43 `_btn_build_setup`/`_run_build_setup*`
  guards untouched.

### New test files

| Test file | Coverage |
|-----------|----------|
| `tests/test_group44_baseline_generator.py` (NEW, 86) | Backend: `build_baseline_setup` produces FULL-FIELD output (all 33 actionable params authored as absolute values); the no-AI guarantee (`build_baseline_setup_response` reads no api_key, calls no `call_api`, runs no audit); gearbox is MONOTONIC strictly-decreasing so `gearbox_ratio_inversion` can never fire (and gear-count sizing: >6 capped, ≤1 single gear, 0 none); transmission_max_speed_kmh stays DISPLAY-ONLY (never actionable); driver-profile BIAS via `_PROFILE_BIAS_TABLE` shifts the right fields then clamps to `resolve_ranges`; source labels; locked-category exclusion + human-category naming + tuning_locked → empty changes; `_filter_baseline_artifact_warnings` drops only the no-op/too-many-changes WARNING artifacts and NEVER a blocking failure; a clean baseline finalises as "approved" with validation_warnings == [] |
| `tests/test_group44_baseline_ui.py` (NEW, 64) | UI/integration: the `_btn_baseline` handlers route through the validator → funnel → Apply-gate; `_display_baseline_result` delegates to the shared `_display_setup_result` renderer (no duplicate render path); the daemon-thread → `_baseline_result_queue` polling; the Group 43 guard REGRESSION (`_btn_build_setup` still disabled, its `_run_build_setup*` guards untouched); Apply pushes the baseline fields into the form |

### Acceptance criteria — status
All Group 44 tests green (86 + 64). 406 green together with group41 + group42
(all) + group43; 0 fail; zero new regressions. The 8 pre-existing
frozen-allowlist failures are unrelated track-modelling tech debt.

### Test-run note (Windows / Python 3.14)
Running the ENTIRE suite in one process can hit a flaky native PyQt teardown
segfault; run in two halves (or by group). Environmental artifact, not a defect.

### Deferred / limitations
- `_btn_baseline` is enabled-at-construction with a runtime car/track guard (no
  proactive disable) — consistent with `_btn_analyse_setup`; the shared renderer
  also re-enables `_btn_analyse_setup` after a baseline (harmless).
- The "no telemetry baseline" symptom label is generic even on the
  driver-profile-biased fields.
- The no-authority fields (camber/toe/dampers/springs/lsd_initial/
  lsd_front_initial) are conservative defaults, not engineered values.
- The old `build_car_setup` AI-authoring path remains dead-in-tree behind the
  Group 43 guards.
- Build candidates: wire `RuleOutcomeStore` live-learning + persistence; per-car
  gearbox ratio bounds (promote `gearbox_out_of_range` to blocking); track-type
  biasing of the baseline.
- The 8 pre-existing track-modelling allowlist failures remain for the
  track-modelling owner.

---

## Setup Brain Outcome Verification & Learning Loop 2 (Group 47)

Branch `group47-setup-brain-outcome-learning` (on top of Group 46 @ `249410e`).

### New tests (73)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group47_outcome_verification.py` | 26 | IMPROVED/UNCHANGED/WORSE/MIXED/INSUFFICIENT classification; target inference; no-signal → insufficient; verdict bridge; model-safety (no setup-authoring surface, pure imports) |
| `test_group47_feedback_learning.py` | 25 | feedback classification; positive supports upgrade only with telemetry agreement; negative-on-flat downgrades; vague → weak; contradictory → mixed; telemetry regression not overridden |
| `test_group47_learning_persistence.py` | 9 | v13 additive columns; migration idempotent; old v12 DB upgrade without data loss; SQLite-only round-trip; setup_history JSON NOT in learning path; Group 46 call still works |
| `test_group47_ui_explainability.py` | 13 | formatter content/disclaimer/grouping/robustness; gated render-path source assertions; backend wiring |

### Reconciled version tests (DB v12 → v13)
`test_session_db`, `test_group18b_rec_persistence`, `test_group18e_setup_history`,
`test_group42_legacy_storage`, `test_group46_learning_persistence`.
`RULE_ENGINE_VERSION` unchanged at 46.0 (Group 47 changes no rule proposals).

### Results (run in groups; UI files individually on Win/Py3.14)
- Group 47: 73 passed.
- Group 46: 106 non-UI passed / 1 skipped; UI explainability 16 passed (isolated).
- Groups 38–45 non-UI: 694 passed / 1 skipped. AC37 RSR/Fuji benchmark: 9 passed.
- UI files (group42_ui_gate 10, group44_baseline_ui 64, group45_ui_context 14):
  all passed individually.

### Known / pre-existing (unrelated to Group 47)
- `test_recommendation_scoring_db::test_v9_schema_version` asserts the stale v10
  and fails on master too (DB is ≥ v12). Pre-existing; not touched.
- Full single-process suite can hit the native PyQt teardown segfault on
  Win/Py3.14 — run in halves / UI files individually. Environmental, not a defect.
- The ~7–20 frozen-allowlist / OFR track-modelling failures remain for their owner.

---

## Race Strategy Brain Phase 2 (Group 48)

**Branch:** `group48-race-strategy-intelligence` (from clean `master` `1c5890e`, Group 47 merged).
**Scope:** backend only — 5 NEW pure `strategy/` modules + 6 NEW test files. **No existing
file was modified**, so every Group 43–47 guarantee holds by construction. Strategy
intelligence ranks race candidates by estimated **total race time**, not fastest lap.

### Modules under test (all pure: no PyQt / DB / AI / file I/O; never raise)
- `strategy/race_strategy_evidence.py` — `StrategyConfidence` enum, frozen
  `RaceStrategyEvidence`, `build_strategy_evidence(...)`, `evidence_from_race_params(...)`.
- `strategy/race_strategy_candidates.py` — `generate_candidates(...)`,
  `legal_candidates(...)`, `StrategyCandidate`, `Legality`/`RiskLevel`.
- `strategy/race_strategy_scorer.py` — `score_candidate(s)(...)`,
  `recommend_strategy(...)`, `fuel_save_worth_it(...)`, `StrategyScore`/`StrategyRecommendation`.
- `strategy/race_strategy_explain.py` — `build_explanation(...)`, `StrategyExplanation`.
- `strategy/race_strategy_benchmark.py` — `run_benchmark()`, `build_benchmark_evidence()`.

### New suites (95 tests, all pure/offline, all pass in <1 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group48_strategy_evidence.py` | 24 | build from available fields; missing fuel/tyre/pit-loss/refuel/lap/compound recorded; refuel included when present; legality fields carried; NO invented metrics; median (not min) pace; `evidence_from_race_params` bridge |
| `test_group48_strategy_candidates.py` | 24 | one/two-stop generated; no-stop legal only when fuel-feasible; mandatory stops + mandatory compounds respected (illegal excluded); stable/deterministic IDs; laps sum to race laps; fuel/pit maths (loss + refuel); fuel unknown → zero, not guessed |
| `test_group48_strategy_scorer.py` | 22 | ranked by total race time; extra stop penalised (pit loss + refuel); high degradation justifies an extra stop ONLY when maths supports; fresher-tyre plan loses when pit cost high; fuel-save preferred only when it wins; missing evidence lowers confidence; safety tie-break |
| `test_group48_strategy_confidence.py` | 16 | HIGH/MEDIUM/LOW/INSUFFICIENT gating and ordering; no-lap/no-fuel → INSUFFICIENT; weak pit maths → LOW; soft gaps step down; never HIGH with core data missing |
| `test_group48_strategy_ui_explainability.py` | 20 | explanation shows plan + confidence; KNOWN/CALCULATED/ASSUMPTION/MISSING/RISK separated; missing evidence + risk flags shown; no "perfect strategy" wording; **SAFETY**: no setup-field tokens, no apply/approve capability, imports no setup-authoring module, Apply-gate predicate + disabled AI-build line intact, driver memory can't flip legality or change the maths |
| `test_group48_porsche_fuji_strategy_benchmark.py` | 13 | legal recommendation; carries fuel + tyre multipliers + 1 L/s refuel; timed-race lap estimate; one-stop beats two-stop on total time; pit + refuel + degradation cost present; rear-fragility flag true → push plan flagged + not recommended; driver-readable explanation; determinism |

### Benchmark result (RSR / Fuji / ~50 min / 8× tyre / 3× fuel / 1 L/s refuel)
One-stop (~3103 s) beats two-stop (~3139 s) by ~36 s; `2stop_push` flagged for rear
fragility and never recommended; explanation names fuel/tyre/pit/refuel/confidence/missing.

### Results
- Group 48: **95 passed** (all six files together, <1 s).
- Regression: Group 47 (73) + Group 46 (151 passed / 1 skipped) + Groups 41–45 non-UI
  (351 passed / 1 skipped) — all green. No existing file modified.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Deferred (honest)
Rival modelling, steering-angle metrics, automatic track mapping, weather-radar, ML
training, AI-authored strategy numbers, AI-Build re-enable, live pit-wall voice, large UI
redesign — all stand. Wiring the evidence builder to pull live `SessionDB` samples is the
scoped next step; today the caller supplies the samples. No new Qt surface was added.

---

## Race Strategy Brain Phase 3 — SessionDB Integration (Group 49)

**Branch:** `group49-strategy-sessiondb-integration` (from clean `master` `df78535`, Group 48 merged).
**Scope:** backend only — 5 NEW pure `strategy/` modules + 6 NEW test files, plus two
ADDITIVE edits to existing files (a read-only `SessionDB.get_session_meta` method and an
optional `evidence_sources` field on the Group 48 `StrategyExplanation`). The Group 48
strategy brain now builds its evidence from real stored SessionDB telemetry.

### Modules under test
- `strategy/race_strategy_session_adapter.py` (READ-ONLY) — `SessionStrategySamples`,
  `extract_session_strategy_samples(...)`.
- `strategy/race_strategy_from_session.py` — `build_strategy_evidence_from_session(...)`,
  `build_strategy_evidence_from_event_context(...)`, `SessionEvidenceResult`.
- `strategy/race_strategy_pipeline.py` — `recommend_strategy_from_session(...)`,
  `recommend_strategy_from_event_context(...)`, `SessionStrategyResult`.
- `strategy/race_strategy_session_explain.py` — `build_session_explanation(...)`,
  `evidence_source_lines(...)`.
- `strategy/race_strategy_session_benchmark.py` — `run_session_benchmark()`,
  `build_benchmark_db()`, `seed_benchmark_session(...)`.
- Additive: `data/session_db.py::get_session_meta` (read-only),
  `strategy/race_strategy_explain.py::StrategyExplanation.evidence_sources`.

### New suites (73 tests, all pure/offline, all pass in <1 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group49_strategy_session_adapter.py` | 20 | reads clean lap / fuel / compound samples; derives tyre-wear from lap drift; fuel from start-end fallback; records missing fuel/tyre/compound; safe on no-db/no-session/no-laps/car-track mismatch; read-only (mock exposes only the two read methods); pit-lap collection |
| `test_group49_strategy_from_session.py` | 15 | builds evidence from a real `:memory:` SessionDB; preserves event settings; uses measured data; confidence drops on missing fuel (→INSUFFICIENT) / tyre; no-session → INSUFFICIENT; pit-loss/refuel/tyre-mult unknowns not invented; source summary names SessionDB; EventContext bridge |
| `test_group49_strategy_pipeline.py` | 12 | full result shape; ranked by total time; recommendation legal; illegal excluded from scored; safety tie-break avoids push; warnings + safety notes; no-session honest; explanation names SessionDB; imports no setup-authoring module |
| `test_group49_strategy_session_explainability.py` | 12 | source lines from summary + garbage-safe; explanation shows SessionDB/event/default; confidence + missing shown; no false certainty; no setup-field tokens; Group 48 caller-sample path keeps `evidence_sources == []` and renders no source section |
| `test_group49_porsche_fuji_session_strategy.py` | 12 | SessionDB-backed benchmark runs offline; carries 8×/3×/1 L/s; one-stop beats two-stop on total time; pit+refuel+degradation present; recommendation legal; rear flag true → push flagged + not recommended; explanation says SessionDB (measured + derived); determinism; reusable seed helper |
| `test_group49_strategy_safety_regression.py` | 11 | Apply-gate predicate + disabled AI-build line intact; result has no apply/approve; no setup-field tokens leak; modules import no setup-authoring; pipeline writes nothing to `data/setup_history.json` (content-hash before/after) and never imports/writes it; driver memory can't flip legality or change total-time; pipeline has no learning parameter; Group 48 scoring deterministic |

### Benchmark result (RSR / Fuji, all from SessionDB)
12 seeded practice laps (rising +0.08 s/lap drift, ~4.0 L/lap) → one-stop (~3112 s) beats
two-stop (~3148 s) on total race time; confidence HIGH; explanation names each input's
source; `2stop_push` flagged rear-fragile and never recommended. Offline, no AI.

### Results
- Group 49: **73 passed** (all six files together, <1 s).
- Regression: Group 48 (95) + Group 47 (73) + Group 46 subset (91 passed / 1 skipped) +
  Groups 41–45 non-UI + `test_session_db` (326 passed / 1 skipped) — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0. `get_session_meta` is an
additive read-only method (no DDL, no PRAGMA change).

### Known caveats / deferrals
SessionDB stores no explicit tyre-wear or pit-loss column, so tyre degradation is a
disclosed lap-drift proxy and pit loss stays event-supplied. No new Qt UI surface — wiring
`recommend_strategy_from_session(...)` into the Strategy tab is the next step. All Group 48
deferrals stand.

---

## Race Strategy Brain Phase 4 — Driver-Facing Surface (Group 50)

**Branch:** `group50-race-strategy-surface` (from clean `master` `7b65fbd`, Group 49 merged).
**Scope:** UI/presentation — 1 NEW pure Qt-free view-model module + 6 NEW test files, plus a
purely ADDITIVE UI block in `ui/dashboard.py` (a Race Plan group in the Strategy Builder tab).
No strategy-maths change; no schema change.

### Modules under test
- `ui/race_strategy_vm.py` (PURE, no Qt) — `RacePlanViewModel`, `build_race_plan_view_model`,
  section formatters, `format_race_time`/`compound_name`/`fuel_map_label`,
  `render_race_plan_html`, `candidate_table_rows`, `CANDIDATE_TABLE_COLUMNS`,
  `run_race_plan_from_session`, `run_race_plan_from_event_context`.
- `ui/dashboard.py` (additive) — `_build_race_plan_group`, `_assemble_race_plan_inputs`,
  `_run_race_plan` (guarantees source-verified, not by constructing a QApplication).

### New suites (70 tests, all pure/offline, all pass in <1 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group50_race_strategy_vm.py` | 24 | time/compound/fuel-map primitives; VM builds; title/confidence/total/gap/stint/candidate/evidence/risk/safety formatting; evidence categories; renderers; **no Qt import in the VM module** |
| `test_group50_strategy_surface.py` | 13 | runner uses session when available; readable explanation; high confidence with full session; safe honest fallback on missing session; lower confidence when tyre missing; event-context runner; Qt method reads no API key / has no apply+setup-history / build button wired / group in tab (source-verified) |
| `test_group50_strategy_candidate_table.py` | 10 | stable columns; one/two-stop rows; all required fields; total time + gap; pit/refuel + deg cost; risk on push; confidence shown; one Recommended; illegal not shown as recommended; row/column count |
| `test_group50_strategy_evidence_display.py` | 12 | measured/event/derived/missing/manual classification; garbage-safe; VM shows measured+derived+event; missing when pit-loss absent; HTML shows evidence sources; no false certainty |
| `test_group50_strategy_safety_regression.py` | 15 | Apply-gate predicate + disabled AI-build intact; method/group no apply/approve/api-key/setup-history capability; VM surface no setup tokens + no apply attr; no setup-history write (content-hash); VM imports no setup-authoring; SessionDB adapter read-only (read-only proxy DB); Group 48 + VM determinism |
| `test_group50_porsche_fuji_strategy_surface.py` | 8 | surface builds offline; 8×/3×/1 L/s scenario; one-vs-two-stop total-time visible; total time displayed; SessionDB source appears; derived tyre labelled; missing evidence when incomplete; push not recommended; no setup Apply action |

### Benchmark result (RSR / Fuji, via the Group 49 in-memory benchmark)
One-stop **51:52.0** beats two-stop **52:28.0 (+36.0s)**; race pace + fuel SessionDB measured,
tyre degradation derived; push plan flagged rear-fragile and never recommended; no Apply action.

### Results
- Group 50: **70 passed** (all six files together, <1 s). Qt-free (guarantees source-verified).
- Dashboard construction: **13 passed** (`test_ui_structure_smoke`, run individually) — confirms
  the new Race Plan group builds inside the Strategy Builder tab.
- Regression: Group 49 + Group 48 strategy suites + Group 47/46 subsets — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals
No session browser (the surface uses the active/resolved session). Tyre degradation is a
disclosed lap-drift proxy; pit loss is manual/event-supplied. All Group 48/49 deferrals stand.
Run UI test files individually on Win/Py3.14 (PyQt cross-file segfault); Group 50's own suite is
Qt-free so it runs together cleanly.

---

## Race Strategy Brain Phase 5 — UAT Hardening (Group 51)

**Branch:** `group51-race-plan-uat-hardening` (from clean `master` `6938218`, Group 50 merged).
**Scope:** UI/usability hardening — 2 NEW pure Qt-free modules + 6 NEW test files, plus
ADDITIVE session-selector/readiness wiring in `ui/dashboard.py`. No strategy-maths change;
no schema change. 1 Group 50 test updated for the new read-only Refresh button.

### Modules under test
- `ui/race_strategy_readiness_vm.py` (PURE, no Qt) — `build_race_plan_readiness`,
  `build_session_diagnostics`, `validate_event_settings`, `empty_state_messages`,
  `strategy_result_message`, `list_recent_matching_sessions`, `render_readiness_html`;
  `ReadinessLevel`/`CheckStatus` enums; `RacePlanReadiness`/`SessionDiagnostics`/
  `EventSettingsValidation`/`SessionSummary` dataclasses.
- `ui/race_strategy_uat.py` — `FUJI_UAT_EVENT_SETTINGS`, `build_fuji_uat_db`,
  `build_fuji_uat_context`, `run_fuji_uat`.
- `ui/dashboard.py` (additive) — `_selected_race_plan_session_id`,
  `_populate_race_plan_sessions`, `_refresh_race_plan_diagnostics`, extended
  `_build_race_plan_group`/`_assemble_race_plan_inputs`/`_run_race_plan`
  (guarantees source-verified, not by constructing a QApplication).

### New suites (81 tests, all pure/offline, all pass in <1 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group51_race_plan_readiness.py` | 15 | READY/PARTIAL/LOW_CONFIDENCE/INSUFFICIENT grading; mismatch; specific next-best-action; missing not hidden; no fake session evidence; never raises |
| `test_group51_session_selection_vm.py` | 15 | selected session id / "No session selected"; match OK/mismatch messaged; clean-lap + fuel/tyre/compound flags; not-found; no-clean-laps; recent list filtered by car+track; read-only |
| `test_group51_event_settings_validation.py` | 12 | missing race length (blocks) / refuel / pit loss / car / track warned; Porsche-Fuji + lap-race pass; manual pit loss labelled MANUAL; layout NA; garbage/empty/None never crash |
| `test_group51_race_plan_empty_states.py` | 16 | driver-readable actionable messages for no session / not found / car mismatch / no-clean / below-min / fuel / tyre / compound / race length / refuel / pit loss; deduped; not vague; result-level reason surfaced |
| `test_group51_strategy_surface_hardening.py` | 13 | run/diagnostics/populate methods read no API key + no setup-history/apply + read-only (source); readiness + plan render when evidence/sections empty; no false certainty |
| `test_group51_porsche_fuji_uat_path.py` | 10 | RSR/Fuji readiness offline; 8×/3×/1 L/s represented; one-vs-two-stop comparison; SessionDB measured evidence; missing evidence when incomplete; push not recommended; no Apply action; determinism |

### Results
- Group 51: **81 passed** (all six files together, <1 s). Qt-free (guarantees source-verified).
- Group 50 (with the 1 updated surface test): **70 passed**.
- Dashboard construction: **13 passed** (`test_ui_structure_smoke`, run individually).
- Regression: Group 50/49/48 strategy suites + Group 47/46 subsets — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals
Session selector is a small read-only dropdown (recent sessions for the current car+track),
not a browser; no session editing/deleting. Tyre degradation is a disclosed lap-drift proxy;
pit loss is manual/event-supplied. No new strategy maths. All Group 48–50 deferrals stand.
Run UI test files individually on Win/Py3.14 (PyQt cross-file segfault); Group 51's own
suites are Qt-free so they run together cleanly. New doc: `docs/UAT_RACE_STRATEGY.md`.

---

## Race Strategy Brain Phase 6 — UAT & Replan Foundation (Group 52)

**Branch:** `group52-race-strategy-uat-replan-readiness` (from clean `master` `a32c694`, Group 51 merged).
**Scope:** UAT verification + a read-only, advisory-only replan foundation — 1 NEW pure module +
6 NEW test files, an extended UAT helper, and a read-only UI placeholder. No strategy-maths change;
no schema change. **UAT outcome: no defects found** in the Group 48-51 Race Plan surface.

### Modules under test
- `ui/race_strategy_uat.py` (extended) — `run_fuji_race_plan_uat_check`, `FujiUatCheckResult`.
- `strategy/race_strategy_replan.py` (NEW, PURE) — `RaceReplanState`, `validate_replan_state`,
  `assess_replan_readiness`, `build_replan_snapshot`, `render_replan_snapshot_text`,
  `replan_placeholder_message`; `ReplanReadinessLevel`/`ReplanConfidence`/`RaceReplanReason` enums;
  `RaceReplanStateValidation`/`RaceReplanReadiness`/`RaceReplanOption`/`RaceReplanSnapshot` dataclasses.
- `ui/dashboard.py` (additive) — read-only "Live Replan Readiness" placeholder label
  (`_rp_replan_placeholder`); guarantees source-verified.

### New suites (64 tests, all pure/offline, all pass in <1.5 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group52_race_plan_uat_harness.py` | 12 | RSR/Fuji UAT check runs offline + passes; event/session validated; readiness READY; clean-lap count; fuel + tyre proxy; one-vs-two-stop times (51:52.0 / 52:28.0); push not recommended; safety checks pass; incomplete scenario honest (INSUFFICIENT + missing visible); determinism |
| `test_group52_race_plan_uat_remediation.py` | 9 | (no defects found — behaviour pins) selected session drives build; readiness agrees with pipeline confidence; manual pit loss labelled MANUAL; missing refuel in missing evidence; no-session renders without crash; no-clean-laps actionable message; candidate table legal-only; no false certainty |
| `test_group52_replan_state.py` | 18 | READY/PARTIAL/LOW_CONFIDENCE/INSUFFICIENT grading; missing fuel/compound/distance flagged; unknown tyre NOT treated as safe; required-compound status preserved; invalid lap no crash; empty state INSUFFICIENT; no fake state |
| `test_group52_replan_snapshot.py` | 13 | plan still viable; fuel-below-expected needs review + options; INSUFFICIENT when critical state / no pre-race plan; LOW confidence when tyre unknown; options are pre-race estimates; advisory-only safety notes; missing state visible; latest fuel samples honoured; no setup tokens |
| `test_group52_replan_safety.py` | 10 | replan module no Qt import + no setup-authoring + no I/O; snapshot no Apply attrs; advisory-only notes; placeholder honest ("not connected yet", lists required fields, no false certainty); no setup-history write (content-hash); Apply-gate predicate + disabled AI-build intact |
| `test_group52_strategy_regression.py` | 12 | Group 48 scoring + pipeline deterministic; SessionDB read-only proxy works; Race Plan + replan modules reference no api_key; `_run_race_plan` reads no API key; VM/readiness/replan modules Qt-free + no setup-authoring imports |

### Results
- Group 52: **64 passed** (all six files together, <1.5 s). Qt-free (guarantees source-verified).
- Dashboard construction: **13 passed** (`test_ui_structure_smoke`, run individually).
- Regression: Group 51/50/49/48 strategy suites + Group 47/46 subsets — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals (Group 53+)
The replan foundation is state-model-only — it does not connect live telemetry, make pit calls,
send driver commands, or apply anything. Deferred: full live replan, telemetry subscription/loop,
automatic pit-call prompts, pit-wall voice, weather radar, rival modelling, steering metrics, ML,
AI-authored numbers, AI-Build re-enable, track-mapping, session editing/deleting, large session
browser, poster generation. Run UI test files individually on Win/Py3.14 (PyQt cross-file
segfault); Group 52's own suites are Qt-free so they run together cleanly.

---

## Race Strategy Brain Phase 7 — Live Current-State Replan (Group 53)

**Branch:** `group53-live-replan-current-state` (from clean `master` `bbf2198`, Group 52 merged).
**Scope:** wire the Group 52 replan foundation to the app's existing read-only live race-state
source — 2 NEW pure modules + 6 NEW test files, an extended UAT helper, and an upgraded
read-only UI surface. No strategy-maths change; no schema change.

### Live-state discovery (documented)
Available live: current lap (`tracker.laps_recorded`), remaining time (`computed_remaining_ms`,
timed) / laps (`laps_remaining`, lap race), fuel % (`packet.fuel_level/fuel_capacity`), live
burn (`avg_fuel_per_lap`), strategy/UI-tagged compound (`_current_compound`). **NOT tracked
live → missing:** tyre age, pit-stop count, required-compounds-used, weather/damage/safety-car.

### Modules under test
- `strategy/race_strategy_live_state.py` (NEW, PURE) — `build_replan_state_from_tracker`,
  `build_replan_state_from_live_packet`, `build_replan_state_from_dashboard_context`,
  `extract_live_replan_state`, `summarise_live_state_sources`, `LiveReplanStateResult`.
- `strategy/race_strategy_live_replan.py` (NEW, PURE) — `build_live_replan_snapshot`,
  `render_live_replan_text`, `LiveReplanResult`, Fuji fixtures.
- `ui/race_strategy_uat.py` (extended) — `run_fuji_live_replan(kind)`.
- `ui/dashboard.py` (additive) — `_refresh_live_replan_snapshot`, Live Replan Readiness group
  (guarantees source-verified).

### New suites (70 tests, all pure/offline, all pass in <1.5 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group53_live_state_adapter.py` | 21 | extracts lap/elapsed/remaining/fuel; compound from strategy tag; live burn surfaced; fuel missing without packet; tyre age + pit count always missing; impossible fuel / zero capacity / negative lap dropped; packet lap not trusted; dashboard path; dispatcher; never raises; no I/O/setup/AI |
| `test_group53_live_replan_snapshot.py` | 15 | healthy → still viable MEDIUM; fuel-short → needs review + options; missing fuel/distance → INSUFFICIENT; unknown tyre caps LOW; missing state visible; advisory-only notes; no setup rec; generated_at passthrough; tracker-path |
| `test_group53_live_replan_ui_surface.py` | 12 | Refresh button + read-only surface (source); no api_key / no apply / no setup-history; renders via pure text; requires pre-race plan; no QTimer/loop; no voice/pit-call; run_race_plan stores result; group labelled read-only/advisory |
| `test_group53_live_replan_safety.py` | 10 | live modules no Qt import + no setup-authoring + no I/O/AI/api_key; result/snapshot no apply attrs; advisory-only notes; no setup-history write (content-hash); Apply-gate + disabled AI-build intact; unknown tyre never high confidence; missing fuel → INSUFFICIENT |
| `test_group53_porsche_fuji_live_replan.py` | 12 | 50min/8×/3×/1 L/s represented; pre-race one-stop; healthy viable; fuel-short needs review; missing INSUFFICIENT; push not promoted; advisory-only; no setup Apply in text; determinism |
| `test_group53_strategy_regression.py` | ~ | Group 48 scoring + pipeline deterministic; SessionDB read-only proxy; live+strategy modules reference no api_key; strategy modules Qt-free; Group 52 build_replan_snapshot still works |

### Results
- Group 53: **70 passed** (all six files together, <1.5 s). Qt-free (guarantees source-verified).
- Dashboard construction: **13 passed** (`test_ui_structure_smoke`, run individually).
- Regression: Group 52/51/50/49/48 strategy suites + Group 47/46 subsets — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals (Group 54+)
The app does not track live tyre age or pit-stop count, so live snapshots are typically
LOW_CONFIDENCE (tyre unknown) or INSUFFICIENT_EVIDENCE — honestly. Adding a read-only
laps-since-pit / pit-stop counter to the tracker would raise confidence and is the natural
next step. Deferred: full live replan loop, automatic pit-call prompts, pit-wall voice,
telemetry subscription loops, weather radar, rival modelling, steering metrics, ML,
AI-authored numbers, AI-Build re-enable, track-mapping, session editing/deleting, large
session browser, poster generation. Run UI test files individually on Win/Py3.14 (PyQt
cross-file segfault); Group 53's own suites are Qt-free so they run together cleanly.

---

## Race Strategy Brain Phase 8 — Live Pit & Tyre-Age (Group 54)

**Branch:** `group54-live-pit-tyre-age-tracking` (from clean `master` `2081f88`, Group 53 merged).
**Scope:** read-only live pit-stop counter + laps-since-pit / tyre-age tracking — 1 NEW pure
module + 7 NEW test files + additive tracker/adapter wiring. No strategy-maths change; no
schema change. Resolves the Group 53 caveat (snapshots capped at LOW because tyre age + pit
count were untracked).

### Discovery
`RaceStateTracker` already detects pit entry/exit (fuel-refuel + a conservative sustained-stop
heuristic → `PIT_ENTRY`/`PIT_EXIT`). GT7 broadcasts **no** pit flag. Group 54 adds a counter +
stint-age on top of that existing detection — it fabricates no new pit signal.

### Modules under test
- `telemetry/pit_state.py` (NEW, PURE) — `PitStintState`, `PitEvent`, `PitDetectionConfidence`,
  `start_stint_tracking`, `apply_lap_completed`, `apply_pit_event`, `apply_manual_pit`,
  `classify_pit_confidence`.
- `telemetry/state.py` (additive) — read-only pit getters + `_check_lap`/`_exit_pit`/RACING wiring.
- `strategy/race_strategy_live_state.py` (extended) — maps tyre age + pit count into RaceReplanState.
- `strategy/race_strategy_live_replan.py` (extended) — pit/stint state in the render + fixtures.

### New suites (63 tests, all pure/offline, all pass in ~2 s)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group54_pit_state_model.py` | 15 | honest-unknown init; start tracking (0 pits HIGH); lap increments; pit counts once + resets stint; dup same-lap not double-counted; NONE never counts; confidence carried; manual pit; classify; no I/O |
| `test_group54_pit_detection.py` | ~ | explicit refuel MEDIUM; manual labelled; speed-only LOW; noise/NONE not counted; fuel jitter LOW not MEDIUM; event-without-tracking not counted; tracker wiring present |
| `test_group54_tracker_pit_state.py` | ~ | getters exist + default; `_check_lap` ages the stint (real wiring); `_exit_pit` counts refuel-pit MEDIUM / speed-only LOW + resets; robustness; no file writes |
| `test_group54_live_adapter_pit_state.py` | ~ | HIGH/MEDIUM maps tyre+pit as live; LOW not populated but labelled + warned; UNKNOWN missing; source summary; dashboard path carries pit state |
| `test_group54_live_replan_confidence.py` | ~ | known tyre+pit lifts to MEDIUM; unknown/low-conf caps LOW; not forced HIGH; missing fuel/distance stays INSUFFICIENT; pit uncertainty prevents false high |
| `test_group54_porsche_fuji_pit_state.py` | ~ | pre_pit_healthy MEDIUM + shows laps-since-pit/pit-count; just_pitted 1 pit/fresh tyres; missing_pit LOW; suspicious signal not counted; advisory-only, no "box box"/"pit now", no setup Apply |
| `test_group54_strategy_safety_regression.py` | ~ | modules no Qt/setup-authoring/api_key; result no apply attrs; no setup-history write (content-hash); pit_state no file writes; Apply-gate + disabled AI-build intact; missing pit not safe; SessionDB read-only |

### Results
- Group 54: **63 passed** (all seven files together, ~2 s). Qt-free (guarantees source-verified).
- Telemetry state regression (I modified `state.py`): **119 passed** across the tracker suites.
- Dashboard construction: **13 passed** (`test_ui_structure_smoke`, run individually).
- Regression: Group 53/52/51/50/49/48 strategy suites + Group 47/46 subsets — all green.
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`,
  `data/track_models/*`, `accepted_model.json`, `*reviewed_segments*`) untouched.

### Schema / migrations
NONE. `DB_VERSION` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals (Group 55+)
Tyre age is an approximation — a detected pit is assumed to include a tyre change (GT7 does
not report tyre changes); before the first pit it is exact. Pit detection uses the existing
fuel-refuel (MEDIUM) + speed-only (LOW) heuristics; track-specific pit-lane mapping for higher
confidence is a Group 55+ dependency if pursued. Deferred: automatic pit-call prompts, pit
command recommendations, pit-wall voice, auto-refresh loops, weather radar, rival modelling,
steering metrics, ML, AI-authored numbers, AI-Build re-enable, track-mapping / track-model
mutation, session editing/deleting, large session browser, poster generation. Run UI test
files individually on Win/Py3.14 (PyQt cross-file segfault); Group 54's suites are Qt-free.

---

## Track-Specific Pit-Lane Mapping (Group 55)

**Objective.** Improve pit *confidence* with track-specific pit-lane mapping. Group 54 counts
pit stops + ages the stint but pit confidence rests on tracker heuristics only (refuel = MEDIUM,
speed-only = LOW; GT7 has no pit flag). Group 55 lets the app say "the car was inside the known
pit-lane corridor when the pit event occurred, so the pit/stint evidence is stronger." **Evidence-
quality only — no pit strategy commands.** Read-only, advisory-only.

**New pure module — `data/pit_lane_resolver.py`.** Qt/DB/AI/file-write-free; deterministic; never
raises. Enums `PitLaneZone` (UNKNOWN/NOT_PIT_LANE/PIT_ENTRY/PIT_LANE/PIT_EXIT) + `PitLaneMappingConfidence`
(NONE/LOW/MEDIUM/HIGH). Frozen `PitLaneSegment` (zone/start_progress/end_progress/label/source/confidence,
`.wrapped`/`.span`) + `PitLaneResolution` (zone/confidence/source/message/matched_segment_label/track_id/
layout_id, `.is_inside_pit_lane`/`.has_mapping`). Functions: `normalise_progress` (wraps into 0–1, rejects
None/garbage/NaN/inf), `progress_in_wrapped_range` (inclusive ends, spans crossing start/finish, zero-width
never matches), `resolve_pit_lane_zone` (narrowest matching span wins; UNKNOWN when no segments or progress
unknown; NOT_PIT_LANE when position known but off-corridor), `build_pit_lane_segments_from_track_context`
(skips malformed/partial entries; `available:false` → []; unknown zone strings ignored), `segments_mapping_confidence`,
`resolve_pit_lane_from_track_context` (attaches ids). **A pit lane is NEVER inferred from racing segments.**

**Track library (backward-compatible).** `TrackLayoutManifest` gained optional `pit_lane` dict (absent → `{}`);
`_parse_...` unchanged for all existing fields. New `load_track_pit_lane(track_id, layout_id, base_dir=)` —
dedicated `layouts/<id>/pit_lane.json` wins, else manifest inline `pit_lane`, else None. Missing pit-lane data
is valid. The only shipped track (Daytona) has no pit-lane data → None → Group 54 fallback. No production Fuji
entry invented; test-only `fuji_pit_lane_mapping()` fixture lives in `strategy/race_strategy_live_replan.py`.

**Tracker.** Read-only `in_pit` property added to `RaceStateTracker` (`_phase == IN_PIT`) — corroboration
context only; applies nothing.

**Live adapter — `strategy/race_strategy_live_state.py`.** `LiveReplanStateResult` gained `pit_in_progress`,
`pit_lane_zone`, `pit_lane_source`, `pit_lane_mapping_confidence`, `pit_evidence_confidence`, `pit_corroboration`.
`build_replan_state_from_tracker` reads `in_pit`. NEW `apply_pit_lane_evidence(result, *, track_context, live_progress)`:
no mapping → Group 54 preserved exactly (+ "map unavailable"); progress unknown → no upgrade (+ "progress unavailable"
/ "not corroborated"); inside corridor + refuel pit (MEDIUM) → **HIGH**; inside + speed-only (LOW) → **MEDIUM at most**;
in-pit but position on track → **CONTRADICTION** (no upgrade + warning); low-confidence (estimated) map caps at MEDIUM.
Never touches `pit_stops_completed`/`tyre_age_laps`, never fabricates a stop.

**Live replan + render — `strategy/race_strategy_live_replan.py`.** `build_live_replan_snapshot` gained
`track_context` + `live_progress`, calls `apply_pit_lane_evidence`; `LiveReplanResult` carries the pit-lane fields.
Overall `ReplanConfidence` UNCHANGED (still ≤ MEDIUM — the pit-evidence confidence is a separate signal, never forces
overall HIGH). `render_live_replan_text` adds `pit lane zone: … (track model)`, `pit detection corroborated by pit-lane
map`, `pit confidence: …`, honest Missing lines, and a contradiction `Warning:` line. No "Pit Now" wording.

**Dashboard.** `_resolve_live_pit_lane_context()` resolves `(track_context, live_progress)` from the event track/layout
via `load_track_pit_lane`, else `(None, None)`. GT7 broadcasts no normalised lap-progress today → live_progress typically
None → app degrades to exact Group 54 behaviour.

### Test files (all `tests/test_group55_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group55_pit_lane_resolver.py` | 30 | normalise (range/wrap/negative/None/NaN/inf); wrapped range (normal/boundary/crossing-line/invalid/zero-width); resolve zone (entry/body/exit-wrap/on-track/progress-unknown/no-segments/narrowest-wins); build segments (fuji 3; missing/available-false/malformed skipped; NO inference from racing segments; object-like); mapping confidence (library MEDIUM / empty NONE / engineer HIGH); from-context (ids attached / missing UNKNOWN) |
| `test_group55_live_pit_lane_adapter.py` | 15 | Group 54 preserved (no context / no progress / never touches pit-count+tyre-age); corroboration (body detected; refuel→HIGH; speed-only→MEDIUM cap; low-conf map cap; contradiction when in-pit off-corridor; on-track not-in-pit ≠ contradiction); tracker path reads `in_pit`; real tracker exposes `in_pit` |
| `test_group55_live_replan_pit_confidence.py` | 13 | full snapshot: refuel-in-lane→HIGH pit evidence; speed-only capped MEDIUM; no-map preserves Group 54; OVERALL confidence never forced HIGH; render shows zone/corroboration/pit-confidence/missing-map/missing-progress/contradiction; render never says "pit now"/"box now" |
| `test_group55_track_library_pit_lane_schema.py` | 9 | manifest parses inline pit_lane / absent → `{}`; loader from dedicated file / from manifest / missing→None / malformed→None; resolver consumes loaded block; real Daytona has no pit_lane (None) |
| `test_group55_safety_guards.py` | 15 | resolver no Qt/DB/AI import + no file writes; new modules no api_key + no setup-authoring; no Apply/command attrs; render no command wording; corroboration never creates a pit; graceful degrade on malformed data + bad progress; unknown mapping not "inside/safe"; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14` |

### Results
- Group 55: **73 passed** (all five files together, ~0.7 s). Pure/offline; Qt guarantees source-verified.
- Regression: Group 48–54 strategy suites **754 passed**; telemetry state/tracker/pit **564 passed** (incl. new `in_pit`);
  track-library **92 passed**; dashboard construction **13 passed** (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`,
  `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`) untouched.

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0. The `pit_lane` manifest block is
purely additive and optional (older manifests parse to `{}`).

### Known caveats / deferrals (Group 56+)
GT7 does not yet expose a normalised 0–1 lap-progress, so the corroboration path typically reports "live track
progress unavailable" in the live app and degrades to Group 54 behaviour — wiring a real progress source
(world-XYZ + reference-path) is the natural next step. No production `pit_lane` entry ships for any track
(exercised via a test-only Fuji fixture). Pit-lane mapping corroborates but never creates pit events; pit count
+ tyre age still come solely from the Group 54 tracker. All prior Group 54 deferrals stand. Run UI test files
individually on Win/Py3.14 (PyQt cross-file segfault); Group 55's suites are Qt-free.

---

## Live Position → Track Progress (Group 56)

**Objective.** Give Group 55 a reliable live lap-progress. Group 55 corroborates a detected pit event
against a known pit-lane corridor, but the app produced no normalised live progress. Group 56 converts
live GT7 world position (X/Y/Z) into a read-only normalised lap progress (0.0–1.0) by matching the car
to the nearest station on an approved/reference track path. **Read-only, advisory-only.** Position
resolves progress; it NEVER creates a pit stop (Group 54 owns pit events, Group 55 owns corroboration).

**New pure module — `data/live_track_progress.py`.** Qt/DB/AI/file-write-free; deterministic; never
raises. `TrackProgressConfidence` (UNKNOWN/LOW/MEDIUM/HIGH; `.is_usable_for_pit` = MEDIUM/HIGH only).
Frozen `TrackPathStation` (index/x/y/z/distance_along_lap_m/progress?/heading_rad?) + `LiveTrackProgressResult`
(progress/distance_along_lap_m/nearest_station_index/nearest_distance_m/lateral_offset_m/confidence/source/
message/warnings/track_id/layout_id; `.has_progress`, `.usable_for_pit`). Functions: `build_track_path_stations`
(from a ReferencePath `.points`, a TrackStationMap `.stations`, or a dict/list — malformed/partial entries
skipped, never crashing), `nearest_station` (XZ plane; ignores Y elevation), `normalise_distance_to_progress`
(wraps; None on zero/invalid lap length), `estimate_lateral_offset` (+left/−right; needs orientation),
`resolve_live_track_progress`, `format_live_track_progress_evidence`. **Confidence thresholds mirror the
existing `data/track_map_matching.py`:** HIGH ≤5 m, MEDIUM ≤20 m, LOW ≤60 m, beyond → UNKNOWN. Identity
mismatch caps at LOW and warns; NaN/inf/missing position or path → UNKNOWN (never guesses).

**Reuse, not rebuild.** Uses the app's existing geometry vocabulary: `ReferencePath`/`ReferencePathPoint`
(x,y,z,distance_along_lap_m,lap_progress) as the station source, the XZ-plane + 5/20/60 m thresholds from
`track_map_matching`, and the read-only on-disk loader `import_reference_path_json`. No calibration workflow
is run; no track model is mutated during live operation.

**Tracker.** NEW read-only `live_world_position` property on `RaceStateTracker` → `(x, y, z, speed_kph)`
from the last packet (`self._prev`), else None. Applies nothing, writes nothing, creates no pit event.

**Live adapter — `strategy/race_strategy_live_state.py`.** `LiveReplanStateResult` gained a `track_progress`
field. NEW `resolve_live_progress_evidence(*, position, reference_stations, track_context, ...)` and
`attach_track_progress(result, progress_result)`. **`apply_pit_lane_evidence` now consumes a MEDIUM/HIGH
track-progress attached to the result when no explicit `live_progress` is supplied**; LOW/UNKNOWN progress
falls through to the existing "position unknown" path (never lifts pit confidence). An explicit
`live_progress` still overrides.

**Live replan + render — `strategy/race_strategy_live_replan.py`.** `build_live_replan_snapshot` gained
`live_position`, `reference_stations`, `identity_ok` (position also derived from the source via
`_position_from_source`); it resolves progress, attaches it, and Group 55 corroboration picks it up.
`LiveReplanResult` carries `track_progress`. `render_live_replan_text` adds `track progress: NN.N% lap
(track model)`, `distance along lap: N m`, `position match: <conf> confidence, N m from reference path`,
`pit-lane map used live track progress`, honest Missing lines (`live world position unavailable` /
`approved reference path unavailable` / `track progress unavailable…`), and `Warning:` lines (far from
path / low-confidence not used / wrong layout). **Overall `ReplanConfidence` unchanged (still ≤ MEDIUM).**

**Dashboard.** `_resolve_live_track_progress_context()` reads the tracker's `live_world_position` and loads
an approved reference path read-only via `_load_reference_path_readonly()` (existing `import_reference_path_json`;
no calibration, no writes), passing `(live_position, reference_stations, identity_ok)` into the snapshot.
Returns `(None, None, True)` when unavailable → degrades to exact Group 55 behaviour.

### Test files (all `tests/test_group56_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group56_live_track_progress.py` | 26 | build stations (points / station-map pct / malformed); normalise (basic/wrap/zero-lap/NaN/inf); nearest (exact/between/empty/ignores-elevation/duplicate-distances); lateral offset sign + no-orientation; HIGH/MEDIUM/LOW/UNKNOWN thresholds; far-off UNKNOWN; identity mismatch caps LOW; missing path/position; NaN position; partial-dict station; Fuji fixture round-trip; render found/missing |
| `test_group56_track_progress_adapter.py` | 10 | resolve evidence (valid→progress / missing position / missing path / identity mismatch warns); tracker `live_world_position` default-None + reads last packet; Group 55 fallback preserved (no progress / LOW not used); MEDIUM/HIGH feeds resolver; explicit progress overrides attached |
| `test_group56_live_replan_progress_integration.py` | 13 | snapshot carries progress; render shows progress/distance/position-match; in-pit-lane corroborates; graceful degrade (no position / no ref path); overall confidence never forced HIGH; no "pit now"/command wording |
| `test_group56_pit_lane_progress_bridge.py` | 6 | LOW progress no lift; UNKNOWN progress no lift; MEDIUM may lift; speed-only pit capped MEDIUM even with HIGH progress; progress in pit lane w/o event creates nothing; progress never touches pit count |
| `test_group56_safety_guards.py` | 15 | resolver no Qt/DB/AI import + no file writes; new modules no api_key + no setup-authoring; no Apply/command attrs; render no command wording; unknown/LOW progress not usable-for-pit; resolver never crashes on garbage grid; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14` |

### Results
- Group 56: **64 passed** (all five files together, ~0.7 s). Pure/offline; Qt guarantees source-verified.
- Regression: Group 48–55 strategy + telemetry state/tracker/pit + track map/station/calibration **996 passed**
  (`-k` union); Group 48–53 strategy **453 passed**; dashboard construction **13 passed**
  (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`,
  `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`) untouched.

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Known caveats / deferrals (Group 57+)
No approved reference-path file ships in the repo today, so in the live app progress typically resolves as
"approved reference path unavailable" until a reference path exists for the track/layout (exercised via the
test-only `fuji_reference_path()` fixture). Deferred: GT7 `road_distance` as a fallback progress source when
world-position matching is weak; per-track approved reference-path files; a local search window / hysteresis
for faster live nearest-station matching. All prior Group 55 deferrals stand. Progress corroborates but never
creates pit events; LOW/UNKNOWN progress never lifts pit confidence. Run UI test files individually on
Win/Py3.14 (PyQt cross-file segfault); Group 56's suites are Qt-free.

---

## Approved Reference Path Assets & Live Progress Activation (Group 57)

**Objective.** Make Group 56 live track progress usable in real UAT. Group 56 converts a live world
position into progress, but only if an approved reference path exists for the current track/layout — and
the app previously guessed a filename and missed the real asset. Group 57 adds a read-only loader that
DISCOVERS + loads approved/reference-path files, validates identity, and converts them to Group 56 stations.
**The repo already ships a real calibration-sourced Fuji Full Course reference path** (200 stations, Porsche
RSR, confidence 1.0), so Fuji progress now genuinely resolves HIGH near the path. Read-only, advisory-only;
reference-path matching NEVER creates a pit event.

**New pure module — `data/reference_path_loader.py`.** Qt/DB/AI-free; read-only; never raises; never writes.
`ReferencePathAsset` (track_id/layout_id/source/path/stations/lap_length_m/warnings/metadata) +
`ReferencePathLoadResult` (asset/available/source/message/warnings; `.has_stations`). Functions:
`load_reference_path_file` (parses the explicit `reference_path_v1` shape AND the existing Group 17
calibration shape `track_location_id`+`points`), `find_reference_path_candidates` (scans `data/track_models/`
+ track-library `reference_path.json`, ranks by identity match), `load_reference_path_for_layout`,
`reference_path_to_track_stations` (→ Group 56 `TrackPathStation` via `build_track_path_stations`),
`validate_reference_path_identity`. Rejects NaN/inf, skips malformed stations, handles zero/negative lap
length + duplicate distances, keeps historical calibration build-notes in metadata (not live warnings), and
uses tolerant identity matching (canonical id OR display-name tokens) so "Fuji Speedway" still finds
`fuji_international_speedway`.

**Reference path format.** Explicit `reference_path_v1` (`schema_version`/`track_id`/`layout_id`/`source`/
`lap_length_m`/`stations[{index,x,y,z,distance_along_lap_m,progress}]`), documented in
`docs/TRACK_LIBRARY_SCHEMA.md`. The existing Group 17 calibration files are supported unchanged. No fake
production geometry was invented — the shipped Fuji asset is genuine calibration output.

**Track-library integration.** Optional `reference_path` pointer block on `TrackLayoutManifest` (absent → `{}`;
backward-compatible) + `load_track_reference_path(track_id, layout_id)`. Real geometry lives in the referenced
file; discovery primarily scans `data/track_models/`.

**Dashboard.** `_resolve_live_track_progress_context()` rewritten to use the canonical
`EventContext.track_location_id`/`layout_id` (Group 56 used the display `track` name and missed the file),
call `load_reference_path_for_layout`, validate identity, convert to stations, and return
`(live_position, reference_stations, identity_ok, reference_path_source, reference_path_warnings)`. The old
filename-guessing `_load_reference_path_readonly` was removed. No calibration run, nothing mutated.

**Render.** `build_live_replan_snapshot` gained `reference_path_source`/`reference_path_warnings`;
`LiveReplanResult` carries them. `render_live_replan_text` adds a Found line `reference path: loaded
(<friendly source>)`, routes load warnings to Missing (`approved reference path unavailable` /
`reference path has no usable stations`) or Warnings (`reference path track/layout mismatch` /
`reference path malformed, ignored`). Overall `ReplanConfidence` unchanged; identity mismatch still caps
Group 56 progress at LOW (never lifts pit confidence).

### Test files (all `tests/test_group57_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group57_reference_path_loader.py` | 18 | loads v1 + Group 17 shapes; converts to TrackPathStation; identity (exact/mismatch/tolerant); missing/malformed JSON; missing stations; bad station values skipped; NaN/inf rejected; zero/neg lap length; duplicate distances; build-notes → metadata; never writes; discovery ranking; real Fuji asset loads |
| `test_group57_track_library_reference_path.py` | 8 | manifest `reference_path` block parses; older manifests → `{}`; coexists with `pit_lane`; `load_track_reference_path` returns block / None; real Daytona has no block (safe) |
| `test_group57_live_progress_activation.py` | 13 | loaded path feeds Group 56; progress matches station; missing/malformed fallback; identity mismatch caps LOW; MEDIUM/HIGH feeds Group 55 (PIT_LANE → HIGH); LOW cannot lift; progress never touches pit count; no-event no-lift even in pit lane |
| `test_group57_replan_reference_path_render.py` | 6 | `reference path: loaded` Found line; missing path honest; no-stations warning; mismatch Warning; no "pit now"/command wording |
| `test_group57_safety_guards.py` | 12 | loader no Qt/AI/DB-write import + writes no files; no api_key + no setup-authoring; no Apply attrs; missing/mismatch never usable; never crashes on garbage grid; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14`; real Fuji asset byte-identical after load |

### Results
- Group 57: **52 passed** (all five files together, ~0.9 s). Pure/offline.
- Regression: Group 54–57 + track-library + map/station/calibration + telemetry state **1123 passed** (`-k` union);
  Group 48–53 strategy **453 passed**; dashboard construction **13 passed** (`test_ui_structure_smoke`, individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*` incl. the Fuji
  reference path, `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`) untouched.

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0. The `reference_path` manifest block is
purely additive and optional (older manifests parse to `{}`).

### Known caveats / deferrals (Group 58+)
Only Fuji + Daytona ship reference-path files; other tracks report "approved reference path unavailable" until a
path is added. The lower-confidence GT7 `road_distance` fallback progress source is DEFERRED to Group 58 (kept
scope tight — the core activation works with the real Fuji asset). A local nearest-station search window /
hysteresis for faster live matching is also deferred. Reference-path matching corroborates but never creates pit
events; LOW/UNKNOWN/mismatched progress never lifts pit confidence. Run UI test files individually on Win/Py3.14
(PyQt cross-file segfault); Group 57's suites are Qt-free.

---

## Road Distance Fallback & Asset Expansion Foundation (Group 58)

**Objective.** Add a safe, lower-confidence fallback for live track progress when no approved reference
path exists, and lay a foundation for adding more approved reference-path assets. Preferred path is
unchanged (approved reference path + live world position → MEDIUM/HIGH map-matched progress); the fallback
is `road_distance` + trusted lap length → approximate progress, clearly labelled lower confidence, never
equivalent to map matching, and never used to lift pit confidence.

**New pure module — `data/live_track_progress_fallback.py`.** Qt/DB/AI/file-write-free; deterministic; never
raises. `resolve_progress_from_road_distance(*, lap_distance_m=None, road_distance=None, lap_length_m=None,
identity_ok=True, track_id=None, layout_id=None)` → a Group 56 `LiveTrackProgressResult` tagged
`source="road_distance_fallback"`. Prefers an accurate per-lap `lap_distance_m`; falls back to
`road_distance mod lap_length` when only the cumulative total is known. **Confidence NEVER HIGH:** MEDIUM =
accurate in-bounds per-lap distance + trusted lap length + known identity; LOW = value wrapped or
cumulative-only; UNKNOWN = missing/invalid/NaN/inf/negative inputs or identity mismatch. `is_fallback_result`
+ `format_road_distance_fallback_evidence` (always labels "approximate", "lower confidence than map matching").

**Precedence (`strategy/race_strategy_live_replan.py`).** `build_live_replan_snapshot` gained `lap_distance_m`,
`road_distance`, `lap_length_m`. Order: (1) usable MEDIUM/HIGH approved map match wins; (2) else the fallback
if it yields progress; (3) else the primary's honest LOW/UNKNOWN (or fallback UNKNOWN). The fallback NEVER
overrides a usable map-matched result.

**Fallback is display-only for pits.** `apply_pit_lane_evidence` (in `race_strategy_live_state.py`) now
excludes `road_distance_fallback` progress from the pit-lane corroboration auto-feed (guarded by source). So
fallback progress can be displayed but can NEVER lift pit confidence, create a pit event, or mutate a pit count.

**Tracker (`telemetry/state.py`).** `road_distance` is a running total (not per-lap), so a
`_road_distance_lap_start` reference is captured at each lap start — mirroring `_fuel_lap_start`, at PRE_RACE,
pit-exit, and lap-complete (NOT the mid-lap fuel-baseline adjustment). NEW read-only properties:
`live_road_distance` (raw cumulative) and `live_lap_distance` (cumulative − lap-start, only while RACING/IN_PIT,
else None). Both apply nothing and create no pit event.

**Registry foundation (`data/reference_path_loader.py`).** `list_available_reference_paths(search_roots=None)`
(read-only, deterministic list of shipped assets — Fuji + Daytona today), `reference_path_asset_summary`
(honest available/unavailable message), `resolve_trusted_lap_length` (approved-asset lap_length → track-library
manifest → None; never invents a length). No fake production assets were fabricated.

**Dashboard.** `_resolve_road_distance_fallback_context()` returns `(lap_distance_m, road_distance,
lap_length_m)` read-only from the tracker + trusted lap-length helper; threaded into the snapshot. Returns
`(None, None, None)` when unavailable → the fallback simply does not activate.

### Test files (all `tests/test_group58_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group58_road_distance_fallback.py` | 13 | MEDIUM/LOW/UNKNOWN rules; never HIGH; identity mismatch; missing/zero/neg lap length; missing road distance; NaN/inf/neg never crash; progress in [0,1); labelling |
| `test_group58_live_progress_precedence.py` | 9 | approved path wins over fallback; fallback activates when no approved path; not activated on invalid road distance / missing lap length; unusable primary falls back; fallback never corroborates pit; fallback never HIGH |
| `test_group58_live_replan_fallback_render.py` | 4 | fallback labelled approximate/lower-confidence; approved path not labelled fallback; no-progress case; no command wording |
| `test_group58_reference_asset_registry.py` | 8 | lists real Fuji + Daytona assets; deterministic order; scoped search root; availability summary honest; trusted lap length from asset; missing → None (not invented) |
| `test_group58_safety_guards.py` | 10 | fallback no Qt/AI/DB-write/file import; no api_key + no setup-authoring; never HIGH; never creates a pit / mutates pit count / lifts to HIGH; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14`; Group 48/49 scoring deterministic |

### Results
- Group 58: **44 passed** (all five files together, ~0.9 s). Pure/offline.
- Regression: Group 53–58 strategy **366 passed**; telemetry state/pit + Group 48/49 + track/reference **823 passed**
  (`-k` union); dashboard construction **13 passed** (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`,
  `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`) untouched (git-verified).

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### How to add an approved reference-path asset (Group 58 foundation)
Drop a `*.reference_path.json` into `data/track_models/` (or a track-library layout dir) using either the
explicit `reference_path_v1` shape or the Group 17 calibration shape (`track_location_id` + `points`). The
loader discovers it by scanning + identity match; `list_available_reference_paths()` will then include it and
`resolve_trusted_lap_length()` will prefer its lap length. Do NOT invent geometry — only import real approved
calibration output.

### Known caveats / deferrals (Group 59+)
Only Fuji + Daytona ship approved reference paths; other tracks use the road-distance fallback (if a trusted
lap length exists) or honestly report "approved reference path unavailable". The fallback's per-lap distance is
derived from the lap-start reference (GT7 `road_distance` is cumulative); using the raw packet field's absolute
zero-point across more tracks is deferred until its semantics are confirmed. A local nearest-station search
window / hysteresis is also deferred. Fallback is advisory-only, never HIGH, never lifts pit confidence, never
creates pit events. Run UI test files individually on Win/Py3.14 (PyQt cross-file segfault); Group 58's suites
are Qt-free.

---

## Reference Path Assets & Road-Distance Semantics Validation (Group 59)

**Objective.** Expand approved reference-path coverage where trustworthy assets already exist, and add a
deterministic foundation for confirming GT7 `road_distance` zero-point semantics across tracks — improving
coverage and confidence WITHOUT inventing data. The evidence hierarchy is unchanged: approved map matching
(highest quality) > road-distance fallback (lower confidence, never HIGH, never lifts pit) > honest missing.

**No new production assets added.** The repo already ships two trustworthy calibration-sourced approved
reference paths — Fuji Full Course and Daytona Road Course (200 stations each, Porsche 911 RSR, confidence
1.0) — both already discovered/registered by the Group 57/58 loader and both resolving a trusted lap length.
Group 59 verified this with tests and hardened the foundation instead of fabricating any geometry.

**New pure module — `data/road_distance_semantics.py`.** Qt/DB/AI/file-write-free; deterministic; never
raises. `RoadDistanceSample(lap_number, start_distance, end_distance)`, `RoadDistanceLapEvidence`
(delta, matches_lap_length), `RoadDistanceSemanticsResult` (status/laps/mean_delta/lap_length_m/
appears_cumulative/warnings/missing). `RoadDistanceSemanticsStatus`: CUMULATIVE_CONFIRMED /
PER_LAP_RESET_CONFIRMED / INCONSISTENT / INSUFFICIENT_EVIDENCE / UNKNOWN. `build_lap_evidence` +
`analyse_road_distance_semantics` + `format_road_distance_semantics`. Classification: cumulative =
starts strictly increase AND start(N+1) ≈ end(N) (continuous) AND deltas plausible vs lap length; reset =
every lap start near zero AND deltas ≈ lap length AND consistent; negative deltas or both-signals-match →
INCONSISTENT; <2 laps → INSUFFICIENT_EVIDENCE; no usable samples → UNKNOWN. Rejects NaN/inf, tolerates
missing lap numbers (positional index), compares to a trusted lap length only when supplied (5% tolerance).

**Registry hardening — `data/reference_path_loader.py`.** NEW `validate_reference_path_candidate(path, *,
expected_track_id="", expected_layout_id="")` → `{ok, errors, warnings, track_id, layout_id, station_count,
lap_length_m, source}`. Clear, actionable errors for incomplete/malformed candidates (file not found, bad
JSON, no usable stations, missing track/layout id, <2 stations, identity mismatch). Read-only; never raises;
invents nothing. Complements the existing `list_available_reference_paths` / `reference_path_asset_summary` /
`resolve_trusted_lap_length` registry helpers from Group 58.

**Live render disclosure (conservative).** When the road-distance fallback is active, `render_live_replan_text`
adds honest disclosure lines: `road-distance semantics: cumulative behaviour assumed from lap-start reference`,
`zero-point validation: insufficient evidence (per-track validation pending)`, plus a warning that the fallback
uses unconfirmed cumulative semantics and confidence stays capped. The validator does NOT change live behaviour
automatically. Approved-path progress shows no semantics disclosure.

**UAT helper.** `ui/race_strategy_uat.py::run_road_distance_semantics_uat(kind)` returns a deterministic
`RoadDistanceSemanticsResult` for `kind` ∈ {cumulative, reset, inconsistent, insufficient, unknown} — offline,
no game, no writes.

### Test files (all `tests/test_group59_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group59_reference_path_assets.py` | 15 | Fuji + Daytona load + validate identity; registry lists both; trusted lap length for known / None for unknown; summary available/unavailable; candidate validator ok / missing file / malformed JSON / missing stations / identity mismatch; real Fuji asset validates |
| `test_group59_road_distance_semantics.py` | 20 | cumulative/reset detection; inconsistent (negative delta); insufficient (1 lap); unknown (empty/NaN); lap evidence deltas + lap-length match; missing lap number → index; dict samples; bad values skipped; garbage never raises; negative lap length ignored; conservative delta-vs-lap-length; render |
| `test_group59_live_replan_semantics_render.py` | 6 | fallback discloses cumulative assumption + insufficient-evidence; labelled lower confidence; never implies equivalence to map matching; no command wording; approved path has no semantics disclosure |
| `test_group59_fallback_quality_guards.py` | 7 | approved path wins over fallback (incl. real asset); fallback never HIGH; activates only with trusted lap length; fallback never corroborates pit / never touches pit count |
| `test_group59_safety_guards.py` | 10 | semantics no Qt/AI/DB-write/file import; no api_key + no setup-authoring; result has no apply attrs; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14`; Group 48/49 deterministic; Fuji reference file byte-identical after analysis |

### Results
- Group 59: **58 passed** (all five files together, ~0.7 s). Pure/offline.
- Regression: Group 53–59 **424 passed**; Group 48/49 + telemetry state/pit + reference/track **973 passed**
  (`-k` union); dashboard construction **13 passed** (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*`,
  `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`) untouched (git-verified).

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Approved assets after this sprint
Fuji Full Course (`fuji_international_speedway` / `fuji_international_speedway__full_course`) and Daytona Road
Course (`daytona_international_speedway` / `daytona_international_speedway__road_course`) — both real calibration
output, discovered by scan + identity match. No new production assets were added.

### Known caveats / deferrals (Group 60+)
No trustworthy reference-path assets exist to import beyond Fuji + Daytona — do NOT fabricate. GT7 `road_distance`
zero-point behaviour is still formally UNCONFIRMED across tracks (the new validator is the tool to confirm it on
real multi-lap captures; the live fallback continues to assume cumulative semantics with capped confidence and
discloses this). A strictly correctness-preserving local nearest-station search window / hysteresis (Group 58's
deferred item) remains deferred — a naive window can miss the global nearest on paths with crossings/parallel
sections. Fallback remains advisory-only, never HIGH, never lifts pit confidence, never creates pit events. Run
UI test files individually on Win/Py3.14 (PyQt cross-file segfault); Group 59's suites are Qt-free.

---

## Real-Capture Road-Distance Semantics & Progress Stabilisation (Group 60)

**Objective.** Confirm/refuse GT7 `road_distance` cumulative-vs-reset semantics from REAL multi-lap captures
(using the Group 59 validator as the authority) and add correctness-preserving live-progress stabilisation —
evidence first, safety second, speed third. No fake geometry, no fake certainty, no production behaviour change
from weak evidence.

**HONEST REAL-CAPTURE FINDING.** The repo ships real per-sample `road_distance` in the Fuji + Daytona
calibration captures (7 usable laps each). Fed through the Group 59 validator: **Fuji → INSUFFICIENT_EVIDENCE,
Daytona → INCONSISTENT.** The captured `road_distance` spans only ~117 m (Fuji) / ~430 m (Daytona) per lap —
far below the ~4441 m / ~5420 m lap lengths — and returns to a near-constant value at the start/finish line.
**Conclusion: the captured field does NOT measure cumulative lap distance in this (post-processed calibration)
data.** The report surfaces this as a span-vs-lap-length red flag and refuses to confirm. The live fallback's
cumulative assumption therefore remains UNVALIDATED; it is already capped + disclosed (Group 59) and Group 60
changes nothing about it. **Still needs:** a RAW-live-packet capture (not post-processed calibration) over ≥3
clean laps to settle the field's true live semantics.

**New pure module — `data/road_distance_capture_analysis.py`.** Qt/DB/AI/file-write-free; never raises.
`CaptureLapObservation` (lap_number, start/end/min/max distance, sample_count; `.delta`, `.span`) +
`CaptureAnalysisResult` (track/car ids, lap_count, observations, lap_length_m, semantics result, max_span_m,
span_covers_lap, next_action, warnings; `.status`, `.confirmed`). `extract_lap_observations` (skips <2 finite
samples, ignores NaN/inf, tolerates missing lap numbers), `analyse_capture_road_distance` (→ Group 59 validator
+ span-vs-lap red flag when max span < 50% of lap length + a clear next_action), `build_capture_report`
(human-readable rows, no false-certainty wording). Thin READ-ONLY loaders `load_capture_laps_from_calibration_file`
+ `analyse_calibration_capture` (via `resolve_trusted_lap_length`) — read via `Path.read_text`, never write.

**New pure module — `data/live_progress_stabiliser.py`.** `nearest_station_stabilised(position, stations, *,
hint_index, window)` ALWAYS returns the GLOBAL nearest (full scan); a local continuity window only sets a
`continuity_ok` flag and NEVER overrides the global result — provably safe on crossings/hairpins/chicanes/
parallel sections. `stabilise_progress(current, previous=None, *, max_progress_jump=0.15, continuity_ok=None)`
NEVER changes the reported progress value and ONLY downgrades confidence (cap at LOW) on an implausible jump
(lap-wrap aware; near-zero backward jitter tolerated); confidence is never inflated; fallback never becomes
HIGH; it touches NO pit state. Implemented + fully tested but NOT force-wired into the live pipeline (the
snapshot builder is stateless; wiring needs a stateful live loop holding previous progress → deferred).

**UAT helper.** `ui/race_strategy_uat.py::run_real_capture_road_distance_uat(kind)` — `kind ∈ {fuji, daytona}`
analyses the real shipped captures; `{cumulative, reset, inconsistent, insufficient, unknown, empty}` runs
deterministic synthetic laps — both through the same `analyse_capture_road_distance` path. Offline, no writes.

**No production live behaviour changed.** No edits to `strategy/race_strategy_live_replan.py`,
`data/live_track_progress.py`, `data/live_track_progress_fallback.py`, `telemetry/state.py`, or `ui/dashboard.py`.

### Test files (all `tests/test_group60_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group60_road_distance_capture_analysis.py` | 21 | extraction (boundaries/span, <2 samples skipped, missing lap number, NaN/inf); cumulative/reset/inconsistent/insufficient/unknown; no-lap-length; span-below-lap red flag; garbage never raises; REAL Fuji/Daytona load-but-not-confirmed; missing capture honest; report no-false-certainty + shows deltas/lap-length |
| `test_group60_capture_uat_helper.py` | 11 | synthetic cumulative/reset/inconsistent/insufficient/unknown/empty; real fuji/daytona not-confirmed; clear next action present; report renders |
| `test_group60_progress_stabilisation.py` | 14 | global nearest wins over bad hint; continuity true when hint correct; crossing/parallel returns global not local; implausible jump downgrades (value unchanged); small step no-downgrade; lap wrap plausible; never inflates; unknown stays unknown; None-safe; fallback never HIGH; touches no pit fields |
| `test_group60_safety_guards.py` | 9 | new pure modules no Qt/AI/DB import + no file writes (read-only Path.read_text); no api_key; no setup-authoring; results no apply attrs; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14`; Group 48/49 deterministic; fallback still never lifts pit; Fuji capture file byte-identical after analysis |

### Results
- Group 60: **55 passed** (all four files together, ~1.6 s). Pure/offline.
- Regression: Group 55–60 **346 passed**; Group 48/49/53/54 + telemetry state/pit + reference/track **960 passed**
  (`-k` union); dashboard construction **13 passed** (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*` incl. the
  calibration captures, `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`)
  untouched (git-verified; capture files byte-identical after analysis).

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Was road_distance cumulative/reset confirmed? Did production behaviour change?
**Not confirmed by real capture fixtures** (Fuji INSUFFICIENT_EVIDENCE, Daytona INCONSISTENT; span << lap
length). **Only tooling was added** — production live fallback behaviour did **not** change. Progress
stabilisation was **implemented (pure) + tested** but **not wired** into the live pipeline.

### Known caveats / deferrals (Group 61+)
The calibration captures are post-processed and do not settle the true LIVE `road_distance` semantics — a raw
live-packet capture over ≥3 clean laps is still needed. The stabiliser is ready to wire once a stateful live
loop holds previous progress. No approved reference-path assets exist to import beyond Fuji + Daytona (do NOT
fabricate). All prior Group 59 deferrals stand. Run UI test files individually on Win/Py3.14 (PyQt cross-file
segfault); Group 60's suites are Qt-free.

---

## Raw Live Packet Road-Distance Capture & Stateful Stabiliser Wiring (Group 61)

**Objective.** Create a raw live-packet capture workflow to finally determine what GT7 `road_distance` means
in LIVE telemetry (calibration data is post-processed and can't answer it), then wire the Group 60 stabiliser
only where safe. Evidence first, confidence second, drama never. No faked certainty; no production promotion
without confirmed live evidence.

**What was proven / not proven.** The tooling exists; **no NEW live semantics were confirmed** this sprint —
that requires a manual in-game raw capture over ≥3 clean laps. The Group 60 finding is now classified honestly:
the shipped Fuji/Daytona captures resolve to **NON_DISTANCE_LIKE** (per-lap span ~117/~430 m ≪ lap length).
**Production fallback behaviour is UNCHANGED**; promotion stays gated on a CONFIRMED (cumulative/reset) raw
capture whose span covers the lap.

**New pure module — `data/live_road_distance_capture.py`.** Qt/DB/AI/file-write-free; never raises.
`RawRoadDistanceSample` + `LiveRoadDistanceCapture` (read-only accumulator): `add_sample`/`add_packet`
(read-only; never mutates the packet) count valid/invalid(NaN/inf)/missing(None)/negative(kept+flagged)/
no-lap-number; `to_laps`/`to_capture_dict`/`summary`; `analyse_live_capture` delegates to the Group 60 flow.

**Semantics — `NON_DISTANCE_LIKE`.** Added an additive `RoadDistanceSemanticsStatus.NON_DISTANCE_LIKE` and a
`CaptureAnalysisResult.capture_status` property that promotes to it when `span_covers_lap is False` (the field
is not a lap-distance measure). `.status` (raw validator) is unchanged so Group 60 tests stand; `.confirmed`
now also requires the span to cover the lap. The report prints both "Semantics status (validator)" and
"Capture verdict".

**Stateful stabiliser — `LiveProgressStabiliserState`.** Retains previous progress; **auto-resets when the
identity key (`track|layout|car`) changes**; produces a `StabilisedProgress`. Never changes the reported value,
never inflates confidence, touches no pit state.

**DISPLAY-ONLY wiring.** `build_live_replan_snapshot` gained `stabiliser_state`. Stabilisation is computed
**after** `apply_pit_lane_evidence`, so pit corroboration keeps using the RAW `track_progress` unchanged. The
stabilised confidence + notes are stored as separate display fields (`stabilised_confidence`,
`stabiliser_notes`, `stabiliser_jumped`) on `LiveReplanResult`; the render adds a "position stability" /
"stabilised progress confidence (jitter guard)" line only on a downgrade/continuity note. No `stabiliser_state`
→ identical behaviour (all existing callers/tests).

**Dashboard.** Holds `_live_stabiliser_state` (lazy) passed into the refresh; and an OFF-by-default
`_raw_rd_capture` fed by one guarded read-only line in `_poll_ui_queue` (inert when None). New methods
`start_raw_road_distance_capture()` / `stop_raw_road_distance_capture()` / `raw_road_distance_capture_report()`.

**UAT.** `run_raw_live_capture_uat(kind)` (cumulative/reset/non_distance/inconsistent/insufficient) +
`build_raw_live_capture_fixture(...)` + `save_raw_capture_to_path(capture, path)` — the single, explicit,
isolated place a capture may be persisted (to a caller-supplied path only; the pure module writes nothing).

### Test files (all `tests/test_group61_*.py`)
| File | Tests | Covers |
| --- | --- | --- |
| `test_group61_live_road_distance_capture.py` | 13 | accumulate raw samples + metadata/position; NaN/inf/None/negative counting; packet without road_distance; garbage never raises; lap-number grouping; missing lap markers grouped; insufficient laps; cumulative confirmed; non-distance-like small-span; module writes no files |
| `test_group61_live_road_distance_semantics.py` | 13 | cumulative/reset/inconsistent/insufficient/NON_DISTANCE_LIKE via raw UAT helper; trusted lap-length + deltas in report; non-distance honest report incl. "not changed"; capture-verdict shown; next action present |
| `test_group61_stabiliser_wiring.py` | 12 | global nearest wins over bad hint (crossing); small step keeps confidence; implausible jump downgrades (value unchanged); never inflates; state resets on identity change; lap wrap not a jump; no-state identical; jump downgrades display but NOT pit; identity-change resets in live path |
| `test_group61_safety_invariants.py` | 9 | new pure modules no Qt/AI/DB/file-writes; no api_key; no setup-authoring; fallback never HIGH; fallback+stabiliser never lift pit / never mutate pit count; Apply-gate + disabled AI-build intact; no setup-history write; `user_version` 13 / no `_migrate_v14`; Group 48/49 deterministic; calibration files byte-identical |

### Results
- Group 61: **43 passed** (all four files together, ~1 s). Pure/offline.
- Regression: Group 55–61 **389 passed**; Group 48/49/53/54 + telemetry state/pit + reference/track **992 passed**
  (`-k` union); dashboard construction **13 passed** (`test_ui_structure_smoke`, run individually).
- Runtime files (`.claude/settings.local.json`, `data/setup_history.json`, `data/track_models/*` incl.
  calibration captures, `data/track_library/**`, `accepted_model.json`, `*reviewed_segments*`, user `config.json`)
  untouched (git-verified; capture files byte-identical after analysis).

### Schema / migrations
NONE. SQLite `user_version` stays 13; `RULE_ENGINE_VERSION` stays 46.0.

### Was live road_distance semantics confirmed? Did production behaviour change?
**Not confirmed** — the raw in-game capture is a manual UAT step. **Only tooling + the stabiliser display wiring
were added.** Production fallback behaviour did **not** change; the road-distance fallback stays lower-confidence,
never HIGH, excluded from pit corroboration. Fallback-confidence promotion remains gated on a CONFIRMED raw
capture (cumulative/reset with span covering the lap).

### Known caveats / deferrals (Group 62+)
Only a real in-game raw capture over ≥3 clean laps can confirm live `road_distance` semantics — the module +
UAT helper are ready for it. No approved reference-path assets exist beyond Fuji + Daytona (do NOT fabricate).
The stabiliser is display-only by design; feeding stabilised confidence back into any decision path would be a
future change requiring its own safety review. Run UI test files individually on Win/Py3.14 (PyQt cross-file
segfault); Group 61's suites are Qt-free.

---

## Setup Brain UAT-2 — Porsche RSR Race Setup Evidence-Pipeline Repair (Group 63)

Branch `group63-setup-brain-race-engineer-uat2` from `master` `b951e06` — committed, NOT pushed. A second Setup
Brain UAT (Porsche 911 RSR (991) '17 race setup) exposed connected defects surviving the 16-phase remediation:
a wrong `Final Drive 4.25→4.20` (lengthening) for an unused sixth, bottoming marked dominant/required on event
count with no impact, LSD triplet + camber not evaluated. Root-cause report: `docs/AUDIT_setup_brain_uat2_group63.md`;
design: `docs/RULE_FIRST_SETUP_BRAIN.md` §17. Deterministic/rule-first/AI-audit-only preserved; **no schema
migration** (`RULE_ENGINE_VERSION` unchanged, `user_version` 14); no auto-Apply; no fabrication.

**Repairs.** (RC-A) feedback flags `lsd_feel_wrong` / `rear_loose_under_braking` / `gearing_too_long` + braking-vs-exit
phase disambiguation (`setup_diagnosis.py`). (RC-B) new pure `strategy/gearbox_evidence.py` — final-drive directional
invariant (`4.25→4.20 = LONGER`) + five-state `derive_gearing_state`; `_classify_gearing` uses the real gear count,
treats a 0 top-speed target as UNKNOWN, gates the straight-specific claim on location confidence, and a driver
"unused sixth" report → `conflicting_evidence` (preserve, validator-enforced). (RC-C) `_classify_bottoming_impact`
(5 classes) grades by consequence not count; `mid_corner_understeer` + new flags can be dominant. (RC-D) new pure
`strategy/lsd_reasoning.py` + `lsd_initial` resolvers — all three LSD fields evaluated vs the proven prior with
executable controlled tests. (RC-E/F) proven values surface unconditionally + drive the tests; `dominant_required`
generalised beyond bottoming; bare `final_drive` no longer "addresses" wheelspin; three new self-guarding UI panels.

**Tests:** `tests/test_group63_setup_brain_uat2.py` — **40 pure/offline tests, all pass ~0.5 s**, incl. the full
Porsche RSR integration fixture (proves: no final-drive lengthening; gearing UNKNOWN not gear_too_short; bottoming
not REQUIRED; all 3 LSD fields evaluated with proven 22/8/33 transferred cross-track; targeted tests present; every
feedback item dispositioned; `recommendation_status=evidence_required` — NOT applyable). One assertion in
`tests/test_group38_setup_diagnosis.py` was updated to the corrected invariant (a limiter reading with no top-speed
target is now UNKNOWN→preserve, not gear_too_short→may_change) + a companion preserve test added. Regression:
~2791 setup-brain/advisor tests + 13 `test_ui_structure_smoke` green. Runtime files git-verified untouched.
**Pre-existing unrelated failure:** `test_home_dashboard_promotion::test_no_new_raw_setcurrentindex` (two
`_tabs.setCurrentIndex(idx)` sites in `ui/dashboard.py`, byte-identical to master — not caused by Group 63).
Safety: new pure modules have no Qt/AI/DB import and no file writes; AI stays audit-only (cannot author values,
cannot validate invalid evidence, cannot bypass the Apply gate); disabled AI-build stays disabled.

## Engineering Brain Program 2 — Phases 48-50 (Event Preparation Cycle & Immersive Race Weekend)

Branch `eng-brain-phase48-50-event-preparation-cycle` @ `0447375`→(12 commits); DB v27→v28 (additive);
rule 46.0 unchanged; committed-not-pushed; master unchanged `3d7c6af`. 145 new tests across 13 files:
`test_phase48_cycle_identity.py`[15], `test_phase48_transitions.py`[11], `test_phase48_evidence.py`[18],
`test_phase49_convergence.py`[13], `test_phase49_setup_lock.py`[8], `test_phase49_strategy_maturity.py`[8],
`test_phase49_finalisation_risk.py`[11], `test_phase50_race_weekend.py`[15], `test_phase48_50_ui.py`[6],
`test_phase48_50_persistence.py`[11], `test_phase48_50_hub_manifest.py`[8], `test_phase48_50_safety.py`[9],
`test_phase48_50_golden.py`[12]. Property/metamorphic: valid-add-never-reduces-evidence,
invalid-never-raises-confidence, coaching≠setup, quali≠race, unknown-fuel-caps, incompatible-does-not-
strengthen, order-independence, refresh-cannot-advance/lock/finalise. Query shape proven constant (1/6/20
sessions, sqlite trace callback, no N+1); runtime DB byte-identical across reads; v28 migration
fresh/upgrade/idempotent. **DB-version sweep:** ~50 current-schema literals across ~40 phase/group files
bumped 27→28; v26→v27 step proofs decoupled to `== DB_VERSION`. **Pre-existing failures left unchanged
(already red at `0447375`):** `test_phase6_golden_uat::test_no_migration_needed` and
`test_phase33_35_safety::test_no_schema_migration_added_by_slice`. Safety: new modules have no AI/network/
TTS/key/Qt (VMs Qt-free); Apply gate untouched; voice gate owned by `shadow_advisory`; nothing auto-locks/
finalises/binds/applies. Manual UAT: Stages A/D PASS (automated), B/C/E/F/G PARTIAL, H NOT RUN (headless).

## Engineering Brain Program 2 — Phases 51-53 (Event Command Centre, Live Orchestration, Certification)

Branch `eng-brain-phase51-53-event-command-centre` @ `ef49d6c`→(10 commits); DB v28 unchanged (NO new
migration); rule 46.0 unchanged; committed-not-pushed; master unchanged `3d7c6af`. 117 new tests across 10
files: `test_phase51_command_centre.py`[17], `test_phase51_command_centre_ui.py`[6],
`test_phase51_dashboard_integration.py`[7], `test_phase52_live_activity.py`[17],
`test_phase52_live_modes.py`[6], `test_phase52_binding_debrief.py`[8], `test_phase53_resume.py`[11],
`test_phase53_revision_reopen_cert.py`[17], `test_phase51_53_golden.py`[19], `test_phase51_53_safety.py`[9].
Property/metamorphic: Home-refresh-cannot-advance, selection-cannot-change-evidence, restart-cannot-
complete, telemetry-loss-cannot-increase-confidence, newest-cannot-auto-bind, invalid-cannot-update-
maturity, noisy-lap-cannot-reopen, corroborated-critical-can-reopen, revision-cannot-rewrite-history,
voice-cert-not-from-Home. Query shape proven constant (1/20 sessions, sqlite trace); Command Centre view
byte-identical across refreshes. Off-thread refresh + stale-worker rejection mirror the canonical pattern.
**Audit A repaired the 9 pre-existing failures** (7x group55-61 + phase6_golden_uat `_migrate_v26 not in`
→ `_migrate_v{DB_VERSION+1}`; phase33_35 moving-HEAD diff pinned to slice tip 9f64ce7). Safety: new modules
have no AI/network/TTS/key/Qt (VMs Qt-free); no new migration; Apply gate + voice gate untouched; nothing
auto-completes/locks/finalises/binds/applies. Manual UAT: Stages B/D/G PASS (automated), A/C/E/F PARTIAL, H
NOT RUN. Operational certification = AUTOMATED_ONLY (live GT7 not run headlessly).

## Engineering Brain Program 2 — Phases 54-56 (Canonical Truth, Live GT7 Bridge, Certification)

Branch `eng-brain-phase54-56-live-operational-certification` @ `da9d6db`->(11 commits); DB v28 UNCHANGED
(NO new migration); rule 46.0 unchanged; committed-not-pushed; master unchanged `3d7c6af`. 112 new tests
across 11 files: `test_phase54_canonical_truth.py`[21], `test_phase54_truth_db.py`[8],
`test_phase54_lock_strategy_readiness.py`[10], `test_phase54_next_action_truth.py`[7],
`test_phase55_bridge_match.py`[9], `test_phase55_bridge_views.py`[8], `test_phase55_session_end.py`[9],
`test_phase56_certification.py`[11], `test_phase56_certification_ui.py`[5], `test_phase54_56_golden.py`[16],
`test_phase54_56_safety.py`[8]. Property/metamorphic: refresh-cannot-change-pending, unbound-cannot-
complete, lock-readiness-cannot-lock, strategy-readiness-cannot-finalise, newest-cannot-autobind,
telemetry-cannot-strengthen, selection-cannot-change-evidence, config-cannot-change-fingerprint,
automated-cannot-award-live, replay-cannot-award-visual, offscreen-cannot-award-operational. Query shape
constant (1/20 sessions); truth + Command Centre views byte-identical across refreshes. **P51-53 report
corrections applied**: file counts 26 A / 15 M / 0 D = 41 (was 20/11/31), test count 117 (golden 19 not
20), UAT terminology (automated != manual UAT). Safety: new modules no AI/network/TTS/key/Qt (VMs Qt-
free); no new migration; Apply gate + voice gate untouched; nothing auto-completes/binds/locks/finalises.
Certification = NOT_TESTED overall (live areas unrun); manual visual + live GT7 UAT NOT run.

## Engineering Brain Program 2 — Phases 57-59 (Real GT7 Runtime, NGR Live Pit Wall, Event Certification)

Branch `eng-brain-phase57-59-live-gt7-event-certification` @ `00111b4`->(10 commits); DB v28 UNCHANGED (NO
new migration); rule 46.0; committed-not-pushed; master unchanged `3d7c6af`. 90 new tests across 9 files:
`test_phase57_adapter.py`[16], `test_phase57_cadence_cache.py`[6], `test_phase57_runtime_authority.py`[10],
`test_phase58_pit_wall.py`[10], `test_phase58_pit_wall_ui.py`[5], `test_phase58_integration.py`[11],
`test_phase59_certification.py`[7], `test_phase57_59_golden.py`[17], `test_phase57_59_safety.py`[8].
Property/metamorphic: same-sequence-same-decision, ui-refresh-cannot-advance, mismatch-cannot-strengthen,
stale-cannot-deliver-advice, voice-cannot-be-manufactured, voice-settings-cannot-alter-fingerprint,
single-advisory-never-multiple-voices, event-switch-invalidates-cache, automated/replay certification caps.
**P54-56 corrections applied**: exact counts 24 A / 6 M / 0 D = 30 (added = 6 strategy + 2 UI + 11 tests +
5 docs; the "9 strategy + 4 docs" narrative was wrong); STATIC runtime-snapshot tests are NOT replay.
Safety: new modules create NO telemetry listener (reuse the daemon UDPListener), are DB-free + Qt-free (VMs
Qt-free); no new migration; Apply gate + voice gate untouched; telemetry evaluation touches no DB; nothing
auto-completes/binds. Certification = per-area, overall NOT_TESTED (live areas unrun); manual visual + live
GT7 + physical voice UAT NOT run.

## Engineering Brain Program 2 — Phases 60-62 (Production Live Activation, Complete Event Loop, Operational Certification)

Branch `eng-brain-phase60-62-production-live-activation` @ `fd66f74`->(11 commits); DB v28 UNCHANGED (NO new
migration); rule 46.0; committed-not-pushed; master unchanged `3d7c6af`. 89 new tests across 10 files:
`test_phase60_context_and_controller.py`[17], `test_phase60_live_worker.py`[6],
`test_phase60_live_tab_integration.py`[4], `test_phase61_briefing_launch.py`[8],
`test_phase61_discipline_workflow.py`[7], `test_phase61_binding_debrief.py`[7],
`test_phase61_restart_eventswitch.py`[6], `test_phase62_certification.py`[8],
`test_phase60_62_golden.py`[17], `test_phase60_62_safety.py`[9]. Property/metamorphic: build-is-DB-free,
opening/refresh-cannot-start-or-complete, mismatch-cannot-strengthen, stale-cannot-advise,
event-switch-rejects-stale-snapshot, voice-cannot-be-manufactured, automated-cannot-award-live. Golden net
found ONE controller defect (`UNVERIFIABLE`->generic LIVE) remediated to `LIMITED_MATCH`. **P57-59
corrections applied**: exact counts 21 A / 6 M / 0 D = 27 (6 M = 2 SOURCE + 4 DOCS; `ngr_live_pit_wall.py`
is ADDED not modified); the live modules were pure domain at `fd66f74` (off-thread worker is Phase 60);
applied-setup fingerprint is a LOCAL PROXY; static snapshot != replay; runtime files untouched. Safety:
new modules create NO telemetry listener (reuse the daemon UDPListener), are DB-free + Qt-free; the
production build touches no DB; no new migration; Apply gate + voice gate untouched; `active_cycle_id`
selection is explicit-only; no new UI module renders/alters the official NGR logo; nothing
auto-completes/binds/launches. `production_event_certification()` = per-area, overall NOT_TESTED (live-GT7/
visual/voice areas NONE); `runtime_field_limitations()` records honest per-field status. Deterministic
replay + manual visual + live GT7 + physical voice UAT NOT run (headless).
