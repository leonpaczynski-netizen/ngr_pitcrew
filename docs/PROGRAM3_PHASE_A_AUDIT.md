# NGR Pit Crew — Program 3, Phase A: Current-State Architecture Audit

**Status:** Phase A complete (audit only — no production code changed).
**Date:** 2026-08-01
**Author:** Claude (Opus 4.8), commissioned via Program 3 brief.

---

## 0. Checkpoint verification (Program 3 §2)

| Item | Verified value | Source |
|---|---|---|
| Branch | `master` | `git branch --show-current` |
| HEAD commit | `3c3446e` (merge PR #97 — proven-library wiring, 2026-07-30) | `git rev-parse HEAD` |
| Working tree | 3 tracked-modified (`data/setup_history.json`, one accepted-model JSON, `.claude/settings.local.json`) + 28 untracked | `git status` |
| Untracked files | **All runtime race-prep data** (track models, calibration laps, refinement ledgers). Per project doctrine these are user artifacts and must **never** be committed. | doctrine + inspection |
| DB schema version | **v31** (`PRAGMA user_version = 31`) | `data/session_db.py:1348` |
| Rule-engine version | **`46.0`** | `strategy/_setup_constants.py:79` |
| DB_VERSION constant | `31` | `strategy/_setup_constants.py:135` |
| Test baseline | ~**10,392 passing / 27 skipped / 0 failed** (register candidate `b9ecdb4`) | `MASTER_TESTING_REGISTER.md:12` |
| Known env flakiness | PyQt6 + Win + Py3.14 segfault constructing `EventCommandCentrePanel` under pytest — environmental, run suite in batches/quarters | `MASTER_TESTING_REGISTER.md:3` |

### Doc-vs-reality discrepancies (a Program 3 §2 finding in itself)

The three doctrine docs are **stale relative to git**:

- `docs/CURRENT_CLAUDE_HANDOFF.md` tail ends at **Group 17O (2026-06-25)**; register/handoff cite **DB v28 / v27 migration** as newest — but the code is at **v31** (migrations v29 lap-integrity, v30 dedupe+UNIQUE, v31 spin_count all landed since).
- The "426 tests green" figure is stale; the authoritative recent run is ~10,392.

**Conclusion:** git is the source of truth here, not the docs. Acceptance gate #30 ("Documentation accurately reflects actual implementation") is **currently failing** and is the cheapest gate to close.

---

## 1. Headline finding — the spine largely EXISTS

Program 3's premise is that "the app does not yet have one authoritative event, session and run identity flowing consistently." That is **only partially true**. A great deal of the requested architecture already exists and is tested. Program 3 is therefore best executed as **unify + extend + fill-gaps + certify**, not "rebuild from the data layer outward."

**Already present and solid:**

- **Identity spine:** `EngineeringContextKey` (`data/engineering_context_key.py`) — a frozen, versioned (`eck_v1`) 13-field identity value object with `fingerprint()` (full identity) and `scope_fingerprint()` (stable physical-scope join key over driver/car/track/layout/gt7_version). Persisted as `engineering_context.fingerprint TEXT UNIQUE`.
- **Canonical live state:** `CanonicalLiveRaceState` (`strategy/canonical_live_race_state.py`, `canonical_live_race_state_v1`) — immutable, rebuilt per invalidation, with per-field availability/confidence and an "unknown-stays-unknown" doctrine.
- **UI read model:** `AppState` (`ui/app_state.py`) — immutable, Qt-free aggregate of `EventContext`/`SessionContext`/`StrategyContext`; owned by `PitCrewController`, one `state_changed` signal.
- **Active-event resolution:** `resolve_active_cycle()` (`strategy/active_cycle_resolution.py`, `active_cycle_resolution_v2`) — **explicitly rejects latest-row-wins**; forces `EVENT_REQUIRES_SELECTION` even for a single active cycle. No auto-activate.
- **Stale-worker protection:** `is_stale_snapshot()` (`strategy/live_restart_recovery.py`) + dashboard `nav_key = (active_cycle_id, activity_id)` guards on every background worker.
- **Passive pages:** grep across `ui/components/` for `active_cycle_id|event_id|SELECT|cursor` → **zero matches**. No widget queries the DB or holds private event state.
- **Session-mode is driver-declared, not inferred:** `live_shell_bridge.py:2386` forces `set_session_type_override(...)`; forces PRACTICE even when GT7 auto-classifies a lobby as RACE.
- **Advisory-only live surface:** `ui/components/live_pit_wall.py` locked by `TestLiveSafety` (`tests/test_live_pit_wall.py:64`) — source may not contain `set_plan(`/`apply(`/`execute_pit`.
- **Contradiction handling:** Phase 29 (`knowledge_contradiction.py`, `contradiction_resolution_status.py`) — scoped conclusions, explicitly **no averaging / no majority vote**, demands a discriminating test.
- **Exact-over-transfer precedence:** `contextual_knowledge_activation.py` class order + `material_context.py` trust ladder.

**The real architectural gap** (Program 3's core diagnosis, precisely located):
The **live runtime** identifies context with a *lighter* `(active_cycle_id, activity_id)` string tuple, while the **setup-experiment/DB** path uses the richer `EngineeringContextKey`. **The two identity systems are not unified, and there is no `session_run_id`/revision-token distinguishing a planned session from each actual run.** This is the seam Program 3 must close.

---

## 2. Current-state by dimension

### 2.1 Database (`data/session_db.py`, 9,273 lines, v31)

- **All core PKs are integer autoincrement; no UUIDs anywhere.** Legacy core (`sessions`, `events`, `lap_records`, `setups`) is integer-keyed; the Engineering-Brain layer (v20+) uses text keys (`fingerprint`, `semantic_digest`, `cycle_id`/`activity_id` slugs). Bridged by text/`CAST`, not FKs.
- **Foreign keys are convention-only.** `PRAGMA foreign_keys = ON` is set but there are **zero `REFERENCES`/`FOREIGN KEY` clauses**. Integrity is app-code only; orphans are structurally possible.
- **"Session" = one actual recorded run.** No planned-vs-actual-run rows. Planned side = `race_plans` + `event_preparation_activities` + explicit `event_preparation_activity_sessions` binding ("sessions are NEVER auto-bound").
- `event_preparation_cycles` (`cycle_id TEXT PK`) is the de-facto **event-programme container**.
- **Absent tables:** `strategy_revision`, `car_spec_revision`, `driver_profile_version`, `track_model_version`, any PTT/engineer-message/debrief table, any persisted `race_state_snapshot`.
- **Active event is persisted in config JSON keyed by the event NAME string** (`active_event_id` actually holds `events.name`); `active_cycle_id` is a `cycle-{slug(name)}` text slug. Not the immutable `events.id`.
- **Immovable golden:** `_compute_race_config_id = sha256("{track}|{car}|{length_key}")[:10]` — the 10-char key every lap-bank/setup-history/session row is keyed by. Frozen in `tests/test_race_config_id_hash.py:55` — **DO NOT regenerate**.

### 2.2 Canonical context services

- No single god-object; ownership is split into frozen read models + `AppState` aggregate + `EngineeringContextKey` identity + `CanonicalLiveRaceState`.
- Stale-guard token = `(active_cycle_id, activity_id)` string tuple. **No `session_run_id` / revision counter** in the guard.
- `EngineeringContextKey` is wired mainly into the setup-experiment/DB path, **not** threaded through the live pit-wall workers.

### 2.3 UI (new NGR shell — default; classic `MainWindow` hidden, `NGR_CLASSIC_UI=1` to reveal)

- `PitCrewShell` = `QStackedWidget` + left `NavRail`, 11 nav destinations + `event_setup`. Pages are passive `render(app_state, view)` renderers.
- Persistent `EventHeaderBar` on every page: Event · Car · Track · Stage · Setup · connection pill. **Missing: explicit Strategy field, session-run id, dedicated recording indicator.**
- **Commands are signal-name convention, not typed command objects** — no `SelectEvent`/`StartSessionRun` dataclasses.
- **Event switching is soft/ad-hoc:** writes `active_cycle_id`, nulls a *hand-maintained, duplicated* list of bridge caches, lets the 750ms `refresh()` timer repopulate. Does **not** stop workers, blank read models, or rebuild pages. Not atomic.
- All mutation centralised in `live_shell_bridge.py` → services/façade; no widget writes storage.

### 2.4 PTT & Engineer

- Keyword-spotting over a fixed vocabulary (`voice/command_vocabulary.py`), not free-form. Deterministic grammar (`strategy/push_to_talk.py`).
- Session modes flowing at runtime: `practice` / `qualifying` / `race` / `track_modelling`. "Coaching" is a PTT/advisor concern, **not** a distinct session mode today.
- **No single Engineer Orchestrator** — behaviour scattered across `announcer.py`, `live_engineer_session.py`, `audio_first_engineer.py`, `ngr_live_pit_wall.py`, routed de-facto by the bridge.
- `SessionType` enum: canonical at `telemetry/state.py:66` (UNKNOWN/PRACTICE/QUALIFYING/RACE); a second lowercase enum for setup rules at `strategy/setup_knowledge_base.py:153`.
- **PTT interactions are NOT persisted with rich context.** By deliberate design: `push_to_talk.py:18` "Raw transcripts never enter engineering fingerprints." Only an in-memory intent fingerprint (action/class/flags) + a feedback draft (`enters_canonical=False`). **This conflicts with Program 3 §19** (which wants raw transcript + full context persisted).

### 2.5 Debrief & cross-event learning

- Debrief exists as a **launch/binding/cumulative-update gate** (`binding_debrief_workflow.py`, `activity_binding.py`) + a **presentation screen** (`ui/components/debrief_view.py` with contradictions/carry-forward slots). **No single aggregating debrief service** — callers assemble sections.
- All 8 transfer/learning modules exist (see §1). Learning is scoped by **full-context fingerprint + ordinal relation ladder + architecture-based transfer** (same drivetrain/layout/category).
- **The §21 6-layer archetype model (global-driver → vehicle-archetype → track-archetype → car-specific → track-layout → event) is ABSENT.** The existing philosophy is different — and arguably more conservative.
- Driver-profile versioning: **plumbing only** — a mutating version string with no effective-dates/prior-version/change-log; the DB read *ignores* the version.
- **No first-class `learning_proposal`/`learning_decision` object** with driver accept/reject/edit/defer.
- **No persistent rejected-learning suppression.**

### 2.6 Tests

- 747 test files, ~10,392 passing. Config Safety Guardrail autouse fixture fails the run if any test mutates the real `config.json`.
- Wiring-seam safety net: `tests/test_full_event_simulation.py` drives the **real** shell↔bridge↔window↔db stack through a 9-stage lifecycle + 6 branch cases.
- Immovable goldens: `tests/test_race_config_id_hash.py` (config_id), frozen fan-out allowlist (`tests/test_legacy_fanout_phase_5.py`), ~53 golden suites.
- Identity/stale regressions pinned by `test_home_no_auto_active.py`, `test_uat_defect_073_event_activation.py`, `test_phase60_live_worker.py`, `test_phase61_restart_eventswitch.py`.
- Event/session-identity UAT defects (DEF-P1-*, DEF-UAT-073-011) are mostly **Fixed-awaiting-retest**, not open.

---

## 3. Gap matrix — Program 3's 31 acceptance gates

Legend: ✅ Present (preserve) · 🟡 Partial (extend existing) · ⛔ Absent (new build)

| # | Gate | State | Note |
|---|---|---|---|
| 1 | Every event one immutable unique identity | 🟡 | `events.id` is immutable, but the active pointer uses the NAME string / slug, not the id |
| 2 | Every page consumes same active event identity | ✅ | Central `AppState` + `EventHeaderBar`; pages passive |
| 3 | Wrong event cannot persist on another page | 🟡 | Central state helps; edit-without-reactivate stale-card path still open |
| 4 | Every session plan belongs to one event | 🟡 | `event_preparation_activities`→cycle→event; "plan" concept thin |
| 5 | Every actual run has one session-run identity | 🟡 | `sessions.id` exists; no explicit run id distinct from plan; no `session_run_id` |
| 6 | Telemetry cannot be stored without valid session context | 🟡 | Guarded in code; no FK; DEF-P1-001 history of `session_id=0` |
| 7 | Every lap traceable to event/session/run/car/setup/track-model | 🟡 | Most links present; no `track_model_version`, no run id, no FKs |
| 8 | Event switching atomic | ⛔ | Soft/ad-hoc; no worker quiescence or read-model blanking |
| 9 | Stale workers cannot write into new event | ✅ | `nav_key` guards + `is_stale_snapshot` |
| 10 | Restart restores exact context or clearly no active run | 🟡 | `active_cycle_id` gate + no-auto-active; "exact run" restore weaker |
| 11 | Engineer mode matches persisted session type | ✅ | Driver-declared override |
| 12 | PTT cannot silently change Engineer mode | ✅ | Confirmed |
| 13 | Practice has explicit objective + completion | 🟡 | Activity objective/state exist; §14 brief (controlled vars/target laps/stop conditions) not modelled |
| 14 | Coaching uses correctly scoped approved evidence | 🟡 | Evidence scoping strong; coaching-as-mode weak |
| 15 | Qualifying uses correct qualifying context | 🟡 | Mode exists; §16 state machine partial |
| 16 | Race Strategy creates auditable snapshot at lap completion | ⛔ | `CanonicalLiveRaceState` is in-memory; no persisted `race_state_snapshot` |
| 17 | Material incidents create immutable strategy revisions | ⛔ | No `strategy_revision` table; replan advisory only |
| 18 | Debrief separates fact/inference/driver report | 🟡 | Sections exist; explicit provenance-typing not formalised |
| 19 | Learning proposals show evidence/applicability/confidence | 🟡 | Computed internally; not surfaced as a proposal |
| 20 | Driver can accept/reject/edit/defer learning | ⛔ | No `learning_decision` |
| 21 | One event cannot redefine global driver profile | 🟡 | ≥2-setup/trend guards; no explicit "global" tier or one-event guard |
| 22 | Exact context outranks general transferable learning | ✅ | Class order + trust ladder |
| 23 | Rejected learning does not influence future recs | ⛔ | No rejected-learning store |
| 24 | Ambiguous legacy evidence quarantined | ⛔ | v29 backfills event_id; no RESOLVED/AMBIGUOUS/ORPHANED classification |
| 25 | Setup Brain receives only correctly scoped evidence | 🟡 | Scoping strong; certification against unified spine pending |
| 26 | Race Strategy receives only correctly scoped evidence | 🟡 | As #25 |
| 27 | Apply and safety gates unchanged | ✅ | Must preserve (TestLiveSafety, Apply-gate) |
| 28 | New migrations + tests pass | — | N/A until built |
| 29 | Existing regression suites green | ✅ | ~10,392 baseline |
| 30 | Documentation reflects actual implementation | ⛔ | Docs stale (claim v28/Group-17O vs actual v31) |

**Tally:** ✅ 7 · 🟡 15 · ⛔ 7 (+ #28 pending). The programme is ~⅓ already met, ½ needs extension of tested foundations, and only ~⅕ is genuinely new.

---

## 4. Material conflicts requiring a decision before implementation

Program 3 §4/§33 forbid modifying protected invariants unless documentation authorises it. Three programme requirements collide with existing tested invariants:

1. **PTT transcript persistence (§19) vs "raw transcripts never persist."** §19 wants raw transcript + full context stored per interaction. The current design deliberately never stores raw transcripts (`push_to_talk.py:18`). **Options:** (A) build the audit trail from the intent fingerprint + context only, preserving the invariant; (B) override the invariant and store transcripts. *Recommend A.*

2. **6-layer archetype learning (§21) vs full-context-fingerprint + architecture-based transfer.** The existing model is a different, arguably more conservative philosophy. **Options:** (A) map programme concepts onto the existing model and extend it; (B) build archetype tiers as literally specified. *Recommend A.*

3. **UUID identity (§6) vs integer-autoincrement + golden `config_id`.** Wholesale UUID migration would threaten the frozen `config_id` key. **Options:** (A) treat existing immutable ids (`events.id`, `cycle_id`, content digests) as "the repository's approved equivalent" and add missing identities additively; (B) migrate to UUIDs. *Recommend A* (Program 3 §6 explicitly allows "the repository's approved equivalent").

---

## 5. Revised implementation plan (extend, don't rebuild)

Faithful to Program 3's phase letters and priority order, reframed around what actually exists. Each phase is an independently reviewable branch + focused commits; migrations additive (v32+); goldens untouched; regression green between phases.

- **Phase B — Schema & identity (additive migrations v32+):** promote immutable `event_id` as the active pointer; add explicit `session_run` identity (planned-vs-actual); add `strategy_revision`, `race_state_snapshot`, `learning_proposal`/`learning_decision`, `driver_profile_version` tables; add integrity checks/indices where safe; legacy `RESOLVED/AMBIGUOUS/ORPHANED` classification + read-only quarantine. Golden `config_id` untouched.
- **Phase C — Context unification:** thread `EngineeringContextKey` into the live runtime; add `session_run_id`/revision token to the stale guard, unifying the two identity systems.
- **Phase D — UI wiring:** typed commands (`SelectEvent`, `StartSessionRun`, …); atomic event-switch (worker quiescence → blank read models → rebuild); header Strategy/run/recording fields. *(Invoke `/ui-ux-pro-max` here.)*
- **Phase E — Session orchestration:** single Engineer Orchestrator; practice brief (§14); qualifying state machine (§16); coaching mode (§15).
- **Phase F — Engineer & PTT integration:** route Engineer through canonical context; PTT context audit trail (per decision #1).
- **Phase G — Dynamic strategy revisions:** per-lap `race_state_snapshot` persistence + immutable `strategy_revision` chain on material triggers.
- **Phase H — Debrief:** aggregating debrief service + fact/inference/driver-report provenance typing.
- **Phase I — Cross-event learning:** `learning_proposal`/`learning_decision` + rejected-suppression + driver-profile versioning (per decision #2).
- **Phase J — Brain certification:** certify Setup Brain + Race Strategy against the unified spine.
- **Phase K — End-to-end UAT + docs:** golden UAT scenarios 1–7; refresh doctrine docs (closes gate #30).

**Recommended first increment: Phases B + C + D (the spine).** Everything else depends on it, and it matches Program 3's own priority order (1. DB identity → 2. canonical context → 3. UI wiring). Stop for review after the spine before session-orchestration work.

---

## 6. Safety guarantees to hold throughout

Deterministic rule-first; offline; AI audit-only / never authors setup values / never bypasses Apply; no auto-setup-application; advisory-only pit wall (`TestLiveSafety`); immutable evidence; additive migrations; no golden regeneration (`config_id`, fan-out allowlist); no silent reassignment of ambiguous legacy data; runtime race-prep data files never committed.
