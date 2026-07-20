# NGR Event Preparation — Architecture & Provenance-Layer Audit

Authoritative ownership map for the Engineering Brain Phase 48–50 slice (NGR Event Preparation Cycle,
Engineering Convergence, and the Immersive Race Weekend). Pre-phase audit performed against the working
tree at `eng-brain-phase45-47-provenance-live-voice @ 0447375` (`DB_VERSION == 27`,
`RULE_ENGINE_VERSION == "46.0"`). All Phase 48–50 additions are **additive** and **read-only** except
for the explicit persistence writers listed in §4.

## 1. Core product doctrine

An NGR race event is not a self-contained weekend — it has a **preparation cycle** that may span weeks
between championship rounds:

```
Event Opens → Preparation Cycle → Practice Programme → Engineering Convergence
→ Setup Lock-In → Strategy Finalisation → Race Weekend Experience → Post-Race Debrief
→ Knowledge Carried Forward
```

Every Practice session collected for one upcoming round belongs to the **same cumulative engineering
programme**. The system must never treat those sessions as disconnected mini-events. The race is the
*climax* of weeks of professional preparation, not a fresh start.

## 2. Provenance layering (the four responsibilities)

The audit confirmed four cleanly-separable responsibilities. Phase 48–50 introduces **Layer B** (the
missing layer) and read-only orchestration over B; it does not alter A, C, or D.

### Layer A — Immutable event environment (WHO/WHERE/UNDER-WHAT-RULES)
driver · car · track · layout · NGR series · round · event rules · BoP · tuning permissions · power /
weight restrictions · tyres · tyre multiplier · fuel multiplier · refuel rate · weather policy · GT7
version · rule-engine version.

- **Owners today:** the `events` table (`_DDL_V1`, keyed by `name`; holds track + rules/BoP/tyre/fuel
  policy) and the Phase-45 immutable snapshots (`engineering_context_snapshots` /
  `engineering_context_snapshot_refs`, sole writer `SessionDB.capture_context_snapshot`).
- **Gap found:** the `events` table has **no** columns for series, round, car, layout, or dates, and it
  models a single race (`laps` / `duration_mins`). It structurally assumes a short, weekend-confined
  event. Layer A is therefore *partially* represented; the immutable environment fingerprint that
  matters for evidence compatibility already lives in the Phase-45 snapshot content.

### Layer B — Event preparation programme (WHEN/WHAT-ACTIVITIES) — **NEW in Phase 48**
preparation start · official event date · Practice schedule · optional Practice · Qualifying date/time ·
Race date/time · deadlines · setup-lock date · strategy-finalisation date · planned run programme ·
completed / pending activities.

- **Owner today:** none. No cycle, no timeline, and — critically — **no query groups sessions by
  event/round**. Sessions carry a flat integer `sessions.event_id` that is written at `open_session`
  but never used as a query predicate; Practice is only queryable *by track*. Practice evidence is thus
  fragmented by track, not grouped by upcoming round.
- **Phase 48 introduces:** `EventPreparationCycle` (domain authority, pure) + a v28 additive persistence
  pair (`event_preparation_cycles`, `event_preparation_activities`) that references `events.id` and
  carries series/round/car/layout/dates/format-profile as its **own** columns, plus an event-scoped
  Practice query. Layer B never mutates Layer A: the cycle *references* the immutable environment, it
  does not redefine it.

### Layer C — Engineering execution (WHAT-WAS-RUN)
applied setup · parent setup · discipline · run plan · experiment · telemetry session · objective ·
selected tyre · starting fuel · target laps · driver feedback.

- **Owners (reused, untouched):** `ActiveSetupAuthority.mark_applied` (the single canonical Apply gate),
  `setup_experiment.py` / `setup_experiment_outcome.py`, `sessions` + `open_session`, the Phase-1
  context spine (`engineering_context` / `engineering_context_links`).

### Layer D — Outcome & learning (WHAT-WAS-LEARNED)
measured telemetry · driver feedback · experiment result · promotion / rollback · coaching progression ·
tyre + fuel model update · strategy update · next engineering action.

- **Owners (reused, untouched):** `setup_outcome_learning.py`, `setup_working_window.py`,
  `driver_development_state.py`, `coaching_priority.py`, `closed_loop_report.py`,
  `race_strategy_evidence.py`, `tyre_curves.py`, and the shared read `SessionDB._build_knowledge_chain`.

## 3. Reuse map (authorities Phase 48–50 consumes, never re-implements)

| Concern | Canonical authority (reused) |
| --- | --- |
| Immutable environment snapshot | `strategy/engineering_context_snapshot.py`, `SessionDB.capture_context_snapshot` |
| Context scope / equivalence | `strategy/engineering_context_scope.py`, `context_equivalence.py`, `material_context.py` |
| Event definition / CRUD | `events` table, `SessionDB.upsert_event/get_event/get_all_events/get_event_id`, `EventPlannerMixin` |
| Applied setup + Apply gate | `data/setup_state_authority.py::ActiveSetupAuthority.mark_applied` |
| Setup lineage / lockout / rollback | `strategy/setup_lineage.py`, `setup_outcome_learning.py` |
| Experiments / preflight / outcomes | `strategy/setup_experiment.py`, `setup_experiment_outcome.py` |
| Working windows | `strategy/setup_working_window.py`, `working_window.py` |
| Driver development / coaching | `strategy/driver_development_state.py`, `coaching_priority.py` |
| Team brief / closed-loop | `strategy/race_engineer_team_brief.py`, `closed_loop_report.py` |
| Tyre + fuel + strategy evidence | `strategy/tyre_curves.py`, `tyre_degradation.py`, `race_strategy_evidence.py` |
| Shared knowledge read | `SessionDB._build_knowledge_chain` (built once; returns programme/transfer/playbook/timeline/records) |
| Live advisory / replay / shadow / voice | `strategy/live_advisory_engine.py`, `telemetry_replay.py`, `shadow_advisory.py`, `voice/voice_controller.py` |
| Voice gate | `strategy/shadow_advisory.py::voice_gate_allows` (VOICE_ELIGIBLE only) |
| Deterministic fingerprints | per-module `_dumps`+`_fp` (sorted-key ASCII JSON, `allow_nan=False`, version-prefixed sha256[:24]); canonical serializer `strategy/assurance_chain_serialization.py` |
| Off-thread UI | `ui/mechanism_annotation_worker.py::MechanismAnnotationWorker` + stale-result guard |

Phase 48–50 must **not** create a competing event authority, setup state, experiment system, outcome
system, strategy engine, coaching engine, telemetry-session model, context store, voice decision
authority, or Event Planner.

## 4. Persistence ownership (writers)

| Table (layer) | Sole writer | Trigger |
| --- | --- | --- |
| `engineering_context_snapshots` / `_refs` (A) | `SessionDB.capture_context_snapshot` | explicit only (session finalize / experiment / outcome / applied checkpoint / assisted confirm) |
| `events` (A) | `SessionDB.upsert_event` | explicit event save |
| `event_preparation_cycles` (B) — **v28** | `SessionDB.upsert_preparation_cycle` | explicit event/cycle creation |
| `event_preparation_activities` (B) — **v28** | `SessionDB.upsert_preparation_activity` / `bind_session_to_activity` | explicit activity creation / session binding |
| applied baseline (C) | `ActiveSetupAuthority.mark_applied` | "Applied in Game" (the frozen Apply gate) |

**Viewing invariant:** viewing/navigating the preparation cycle, refreshing a dashboard, replaying, or
evaluating a live advisory **never** writes a row. Only explicit event creation, activity creation,
session binding, setup lock, strategy finalisation, or an existing canonical outcome workflow may write.

## 5. Additive v28 migration plan

Following the established ladder pattern (`_DDL_VN` string → append to `_DDL` → `if version < N` guard →
`_migrate_vN` → bump `DB_VERSION`):

1. `strategy/_setup_constants.py` — `DB_VERSION = 28`.
2. `_DDL_V28` — `event_preparation_cycles` (identity + timeline + lock/strategy state) and
   `event_preparation_activities` (typed, ordered, optional/scheduled, session-bound), both
   `CREATE TABLE IF NOT EXISTS` + indices.
3. `_migrate_v28` — `executescript(_DDL_V28)`; idempotent; touches no legacy row; legacy sessions keep
   `event_id` and gain **no** retroactive cycle association (unknown, never fabricated).
4. Update the two "current schema" assertions to `28`; leave the v26 → v27 step proofs literal.

Legacy cycle association is left **unknown where it cannot be proved** — no back-fill, no fabricated
binding. See the per-phase docs (`ENGINEERING_BRAIN_PHASE48_*`, `PHASE49_*`, `PHASE50_*`) for the
as-built domain, and `UAT_ENGINEERING_BRAIN_PHASE48_50.md` for staged UAT.

## 6. Future NGR League Hub boundary (contract only, no networking)

Phase 48–50 defines a stable future import contract (`NgrEventManifest`, `NgrEventManifestVersion`,
`NgrEventRevision`, `NgrEventManifestValidation`, `NgrEventImportPort`, `NgrRegisteredDriverReference`)
but implements **no** API, network, authentication, or automatic import. The Hub will eventually be the
NGR league/event authority; Pit Crew remains the engineering authority. Imported data must become an
**immutable local event snapshot**; Hub revisions must never silently rewrite completed Practice, setup,
or Race history. Offline manual event creation is never removed.
