# Program 3 — Canonical Event Spine: Implementation State

**Status:** Phases A–I implemented and merged to `master`. **Phase J (certification)
complete** — see `docs/PROGRAM3_PHASE_J_CERTIFICATION.md` (43 cert tests, 0 defects,
GO for controlled live activation). K (golden end-to-end UAT) remains and requires the
fully-assembled system + live GT7/PSVR2 testing. This document is the §32 completion
record and closes gate #30 (documentation reflects actual implementation).

**Baseline at start:** `master` `3c3446e`, DB v31, Rule-Engine 46.0.
**Now:** DB **v40**, Rule-Engine 46.0. All Program-3 work landed via PRs #98, #99, #100
(+ the Phase-I learning-model PR). Additive/idempotent throughout; frozen goldens
(`config_id`, fan-out allowlist) untouched; Apply-gate / `TestLiveSafety` unchanged;
deterministic/offline/advisory doctrine held; runtime race-prep data never committed.

---

## What shipped, by phase

### A — Audit
`docs/PROGRAM3_PHASE_A_AUDIT.md` — current-state map + gap matrix vs the 31 gates. Verdict: the spine largely already existed → extend-and-unify, not rebuild.

### B — Schema & identity (DB v31 → v38)
- **v32** UUIDv7 identity on 8 core tables (ordering-preserving backfill; `config_id` decoupled + untouched; one-time DB backup).
- **v33** event-programme `cycle_id` slug → UUID (+ `legacy_cycle_id`, `get_cycle_by_event`).
- **v34** planned `session_plans` vs actual `session_runs` + `stints`; laps cross-referenced.
- **v35** immutable, parent-chained `strategy_revisions` + `race_state_snapshots`.
- **v36** `car_spec_revisions` + `track_model_versions`.
- **v37** `driver_profile_versions` (real history / effective dates).
- **v38** legacy `RESOLVED/RESOLVED_WITH_WARNING/AMBIGUOUS` classification + read-only `quarantine_records` view (ambiguous rows never guessed into an event).

### C — Context unification
- **C1** `session_run` identity wired into the recording path (`open_session` stamps `sessions.uuid` + opens a run/stint; `write_lap` stamps `lap_records.uuid`/`session_run_id`/`stint_id`; `bind_session_to_activity` links the run to its plan). `main.py` hot-path unchanged.
- **C6** car name resolved from the GT7 packet id (`sessions.car_name`), not the coincidental `cars.id`.
- **C2–C5 deferred** (documented): given the dual-key architecture and that `open_session` already resolves the `EngineeringContextKey`, these were low-value/high-risk; folded into later phases where consumers exist.

### D — UI wiring (designed via /ui-ux-pro-max)
- **D1** context header gains a Strategy label + a distinct recording pill (colour+text+glyph, never colour alone).
- **D2** typed shell command vocabulary (`ui/shell_commands.py`) + `LiveShellBridge.dispatch()` (additive; ~40 signal handlers untouched).
- **D3** one complete, shared event-switch reset (`_reset_context_caches()`) replacing three drifting copies.

### E — Session orchestration (pure domain layer + live integration)
- **E1** single `EngineerMode` authority. **E16** qualifying state machine. **E14** live practice brief. **E12** `EngineerOrchestrator` composing them (strict superset). **Live integration:** `_feed_live` routes the engineer line through `orchestrate()`.

### F — PTT audit trail (DB v39)
- `ptt_interactions` + pure `PttInteractionRecord`; every interaction stamped with context + intent + resolution. **No raw-transcript column/field** (push_to_talk invariant).

### G — Dynamic strategy revisions
- An accepted replan snapshots the triggering state and appends an immutable `strategy_revision` referencing it. Advisory only (records, executes nothing).

### H — Event debrief (§20)
- Pure `build_event_debrief()` + `SessionDB.build_event_debrief_for_event()`. Every finding tagged by **provenance** (measured_fact / deterministic_inference / driver_report / unresolved).

### I — Cross-event learning (DB v40)
- **Workflow:** `learning_proposals` + `learning_decisions`; propose → accept/reject/edit/defer; rejected learning is never re-proposed without new evidence and never an active prior.
- **Model:** `evaluate_learning_transfer()` / `rank_priors_for_target()` — extends the existing exact-outranks-transfer doctrine (per the 2026-08-01 decision, not a parallel archetype system): exact-context layers apply at full strength, broader layers only as a halved-strength prior, more-specific suppresses broader.

---

## Acceptance-gate status (Program 3 §31)

✅ met · 🟡 foundation in place, needs live UAT / J-K · ⛔ not yet

| # | Gate | Status |
|---|---|---|
| 1 | Immutable unique event identity | ✅ (events.uuid; active pointer via cycle) |
| 2 | Every page consumes the same event identity | ✅ |
| 3 | Wrong event can't persist on another page | ✅ (central AppState + complete reset) |
| 4 | Every session plan belongs to one event | ✅ |
| 5 | Every actual run has one run identity | ✅ (session_runs) |
| 6 | Telemetry needs valid session context | ✅ (run opened at recording) |
| 7 | Every lap traceable to event/session/run/car/setup/track-model | ✅ |
| 8 | Event switching atomic | ✅ (shared reset; stale workers rejected) |
| 9 | Stale workers can't write into the new event | ✅ |
| 10 | Restart restores exact context or clearly none | ✅ (no auto-active) |
| 11 | Engineer mode matches persisted session type | ✅ (E1 authority) |
| 12 | PTT can't silently change mode | ✅ |
| 13 | Practice has objective + completion | ✅ (E14 brief) |
| 14 | Coaching uses correctly scoped evidence | 🟡 (existing coach; scoping via spine) |
| 15 | Qualifying uses correct context | ✅ (E16 machine) — 🟡 live activation needs UAT |
| 16 | Auditable state snapshot at lap/material trigger | ✅ (on accepted replan) — 🟡 per-lap needs UAT |
| 17 | Material incidents create immutable strategy revisions | ✅ (on accept) — 🟡 broader triggers need UAT |
| 18 | Debrief separates fact / inference / driver report | ✅ (H provenance) |
| 19 | Learning proposals show evidence/applicability/confidence | ✅ |
| 20 | Driver can accept/reject/edit/defer learning | ✅ |
| 21 | One event can't redefine the global driver profile | ✅ (driver-gated promotion) |
| 22 | Exact context outranks transferable learning | ✅ (I model) |
| 23 | Rejected learning doesn't influence future recs | ✅ (suppression) |
| 24 | Ambiguous legacy evidence quarantined | ✅ (v38) |
| 25 | Setup Brain gets only correctly scoped evidence | ✅ (certified Phase J: J6) |
| 26 | Race Strategy gets only correctly scoped evidence | ✅ (certified Phase J: J7) |
| 27 | Apply + safety gates unchanged | ✅ |
| 28 | New migrations + tests pass | ✅ |
| 29 | Existing regressions green | ✅ (6 pre-existing reds in 4 families, all pre-date Program 3 — proven on base 3c3446e; see Phase J cert) |
| 30 | Docs reflect implementation | ✅ (this document) |

---

## Follow-ups that require live GT7/PSVR2 UAT (Phase K)

The domain layers are built and unit-tested; these activations were deliberately **not**
landed blind because they can only be validated in a real session:

- Activate the qualifying state machine (E16) + live practice brief (E14) inside `_feed_live` (the seam exists via the orchestrator).
- Broader PTT capture (driver reports / queries) beyond strategy acks.
- Broader strategy-revision triggers (rain / damage / fuel deviation) + per-lap `race_state_snapshots`.

## Remaining phases

- **J — Brain certification: ✅ COMPLETE** (`docs/PROGRAM3_PHASE_J_CERTIFICATION.md`; 43 cert tests, 0 defects; gates #25–26 certified; GO for controlled live activation).
- **K — End-to-end UAT + docs:** the seven golden UAT scenarios (§30) against the assembled stack, plus your on-hardware GT7/PSVR2 testing.

## Pre-existing test reds (NOT introduced by Program 3)
Reproduced on the base commit with all Program-3 changes stashed: `test_ofr2_session_db` recommendation_scoring hash-pin; two `test_group18e` (old dup-lap vs the v30 index); two `test_uat_shell_remediation::TestU4HomeSaysSomething`; `test_live_shell_bridge::test_refresh_feeds_appstate_and_garage`.
