# Program 3 — Phase B Design: Canonical Identity, Migration Plan & Legacy Classification

**Status:** DESIGN — for review before any `data/session_db.py` change.
**Branch:** `feat/program3-spine-2026-08-01` · **Baseline:** DB v31, Rule-Engine 46.0.
**Precursors:** [Phase A audit](PROGRAM3_PHASE_A_AUDIT.md) + UUID blast-radius inventory.

---

## 1. Decision & rationale

**Approach: transitional dual-key UUIDv7.** Every core entity gains a real, canonical **UUIDv7** identity that flows outward to UI / telemetry context / Engineer / strategy / learning and becomes *the* cross-system id. The existing INTEGER PK is **retained internally** during transition so the ~50 `ORDER BY id`/`MAX(id)` queries, 14 `lastrowid` writers, and the `id==0` sentinels keep working while we repoint consumers.

This honours the "full UUID identity" decision (UUID is the identity everything keys on) while the blast-radius inventory's verdict — *"a hard PK swap is NOT safe"* — is respected. The two facts that make this clean:

1. **`config_id` is provably decoupled** (`data/working_race_config.py:112-117` = `sha256("track|car|length")[:10]`; no integer id feeds it). The golden `config_id` and every `config_id`-keyed artifact (`setup_history.json`, DB columns) are **byte-for-byte untouched**.
2. **UUIDv7 is time-sortable.** Native `uuid.uuid7()` (Python 3.14.2, confirmed present). For *existing* rows we backfill a UUIDv7 whose 48-bit timestamp = the row's own `date_utc`/`created_at`, tie-broken by integer id → `ORDER BY uuid` reproduces `ORDER BY (date, id)`. So the moment a query is later repointed from `id` to `uuid`, its "latest row" semantics are preserved, not corrupted.

**Non-negotiables held:** additive migrations only; idempotent + reversible; no golden regenerated (`config_id`, fan-out allowlist); no ambiguous legacy row guessed into a context; Apply-gate / `TestLiveSafety` untouched; runtime race-prep data files never committed.

---

## 2. Canonical identity specification

### 2.1 Identity primitive

- **`uuid7()`** (RFC 9562 v7) for all new identities. 36-char canonical string, stored `TEXT`.
- A single helper `data/ids.py::new_id()` (→ `str(uuid.uuid7())`) and `backfill_id(created_iso, seq)` (deterministic ordering-preserving v7 from a timestamp + monotonic seq) so backfill is centralised and testable.
- The already-TEXT engineering spine (`engineering_context`, `setup_experiments`, `event_preparation_*`, …) needs its cross-ref columns **populated** with these UUIDs — no type change.

### 2.2 Entity → identity map

| Program-3 identity | Backing table | Today | Phase B |
|---|---|---|---|
| `event_id` | `events` | INTEGER PK, pointer stored as **name** in config | add `uuid TEXT UNIQUE`; config strategy pointer migrates to uuid |
| `event_programme_id` | `event_preparation_cycles` | `cycle_id` TEXT slug | **REPLACE** slug with a UUID (decision 2026-08-01); remap child refs + config pointer + `_cycle_id_for` in **v33** |
| `session_plan_id` | **new** `session_plans` (from `event_preparation_activities`) | activity `activity_id` slug | formalise: an activity **is** a planned session; add `uuid` |
| `session_run_id` | **new** `session_runs` | *absent* — `sessions.id` conflates plan+run | **new table**: one row per actual execution of a plan; `uuid` PK |
| `stint_id` | **new** `stints` | *absent* | **new table**; `uuid` PK; FK→`session_run` |
| `lap_id` | `lap_records` | INTEGER PK | add `uuid`; add `session_run_uuid`, `stint_uuid` |
| `car_id` | `cars` / GT7 packet | packet id (external) | **unchanged** — packet id stays; `cars.id` gets a `uuid` only for the surrogate |
| `car_spec_revision_id` | **new** `car_spec_revisions` | *absent* | **new table** (BoP/spec snapshot per event); `uuid` PK |
| `setup_snapshot_id` | `setup_snapshots` | INTEGER PK | add `uuid` |
| `setup_lineage_id` | `setup_lineage` | INTEGER PK | add `uuid` |
| `strategy_revision_id` | **new** `strategy_revisions` | *absent* (JSON snapshots only) | **new table**; immutable chain; `uuid` PK + `parent_uuid` |
| `driver_profile_version_id` | **new** `driver_profile_versions` | version string, DB ignores it | **new table**; effective dates + prior-version + change-set |
| `track_model_version_id` | **new** `track_model_versions` | on-disk slug files only | **new table** registering approved model versions; `uuid` PK |
| `race_state_snapshot_id` | **new** `race_state_snapshots` | in-memory only | **new table**; persisted per-lap/material snapshot; `uuid` PK |
| `ptt_interaction_id` | (Phase F) | not persisted | deferred to Phase F (see conflict §4 of audit) |
| `engineer_message_id` | `ai_interactions` (+`uuid`) | INTEGER PK | add `uuid` |
| `event_debrief_id` | **new** `event_debriefs` | activity state only | Phase H; `uuid` PK |
| `learning_observation/proposal/decision_id` | **new** tables | *absent* | Phase I; `uuid` PKs |

### 2.3 The planned-vs-actual model (the core new distinction)

```
event_programme (cycle)                 [event_preparation_cycles + uuid]
  └── event                             [events + uuid]
        └── session_plan                [= event_preparation_activities, formalised + uuid]
              └── session_run           [NEW: one row per actual execution]
                    └── stint           [NEW]
                          └── lap        [lap_records + session_run_uuid + stint_uuid]
```

- A `session_run` binds to exactly one `session_plan`; a **new telemetry recording creates or explicitly resumes an identified `session_run`**. Failed/successful/comparison runs of the same plan are **distinct rows** (never merged by name/type).
- Legacy `sessions` rows map 1:1 to a backfilled `session_run` (each historical session was one execution). The `sessions` table is retained; `session_runs` initially *shadows* it (dual-key) so existing writers keep functioning.

---

## 3. Migration sequence (additive, idempotent, reversible)

One focused migration per commit — never one oversized migration. Each guarded by `PRAGMA user_version`, each re-runnable, each with an explicit down-note.

| Ver | Adds | Backfill | Reversible via |
|---|---|---|---|
| **v32** | `uuid` columns on `events`, `sessions`, `setups`, `setup_snapshots`, `lap_records`, `setup_lineage`, `cars`, `ai_interactions`; unique indices | ordering-preserving UUIDv7 from each row's `date_utc`/`created_at`+id | columns are additive; down = drop columns/indices |
| **v33** | `session_runs`, `session_plans` (formalise activities), `stints`; cross-ref uuid cols on `lap_records` | 1:1 `sessions`→`session_run`; activities→`session_plan`; laps→run; single-stint default | drop new tables/cols |
| **v34** | `strategy_revisions` (parent chain), `race_state_snapshots`, `car_spec_revisions`, `track_model_versions` | register current approved track models from disk; seed strategy v1 from existing approved plans | drop new tables |
| **v35** | `driver_profile_versions` (effective/prior/change-set) | seed v1 from current `user_profile` + `"v1.0-hardcoded"` | drop new table |
| **v36** | legacy-classification columns + `quarantine_records` view; integrity indices | classify every id-bearing row (§5) | drop col/view |

**Idempotency pattern** (every migration): guard column adds with a `PRAGMA table_info` check (the v31 `spin_count` add already uses this duplicate-column guard); guard table creates with `CREATE TABLE IF NOT EXISTS`; backfill only rows where `uuid IS NULL`. Running v32→v36 twice is a no-op.

**Backfill ordering proof obligation:** a test asserts that for the seeded fixture DB, `SELECT id FROM t ORDER BY uuid` == `SELECT id FROM t ORDER BY date_utc, id` for each backfilled table. This is the guard that makes later `id`→`uuid` repointing safe.

---

## 4. Code-hazard handling (from the blast-radius inventory)

Phase B **adds identity; it does not repoint consumers.** So most hazards are deferred to Phase C by design, but each has an explicit plan:

1. **`lastrowid` writers (14):** unchanged in v32–v36 (integer PK retained). New rows also get a `uuid` via `new_id()` at insert. When a writer later needs to hand out identity, it returns the `uuid`, not `lastrowid`.
2. **`ORDER BY id`/`MAX(id)` (~50):** **untouched in Phase B.** They keep using integer id. Phase C repoints only those that cross a context boundary, and only after the ordering-preservation test passes.
3. **`session_id==0` / `event_id==0` sentinels:** **untouched in Phase B.** A dedicated Phase-C task replaces the overloaded sentinel with an explicit `Optional`/`ALL_HISTORY` marker (esp. `main.py` dispatcher hot-path and `dashboard.py:2726` "all history" query). Flagged, not touched, now — this is a behavioural change that needs its own commit + tests.
4. **`config["strategy"]["event_id"]` raw integer:** v32 adds the event `uuid`; a Phase-C task migrates the config pointer to store the event uuid (with a read-time fallback that resolves a legacy integer/name). Config writes stay backward-compatible.
5. **`cars.id` vs GT7 packet `car_id` latent coupling (`session_db.py:3399/3353`):** documented as a pre-existing ambiguity; v32 does **not** alter `car_id` semantics. Resolving the conflation is a scoped Phase-C task, not smuggled into the migration.

---

## 5. Legacy-data classification (Program 3 §27)

v36 classifies every id-bearing legacy row into exactly one bucket — **without guessing**:

- **`RESOLVED`** — full reliable context (event + car + config_id + valid session link) present and consistent.
- **`RESOLVED_WITH_WARNING`** — resolvable but with a soft inconsistency (e.g. `event_id=0` but a bound cycle exists via `event_preparation_activity_sessions`; recoverable via the v29 backfill path).
- **`AMBIGUOUS`** — multiple plausible contexts and no deterministic tiebreak (e.g. a session whose config_id matches >1 event). **Never assigned to the most-likely event.**
- **`ORPHANED`** — dangling reference (e.g. `lap_records.session_id` with no `sessions` row; already-known orphans the v30 dedupe pruned telemetry for).

Deliverables: a **migration report** (counts per bucket + reasons), a **read-only `quarantine_records` view** exposing `AMBIGUOUS`/`ORPHANED` for manual review, and a rule that **quarantined rows never feed driver learning**. Classification is a stored column, not a guess-and-move.

---

## 6. Rollback / backup

- Pre-migration: the migration writes a one-time timestamped DB copy `session.db.pre_v32.bak` (guarded so it only snapshots once, before the first Program-3 migration runs). **Approved 2026-08-01.**
- Each migration's down-note is documented; because all changes are additive (new columns/tables/views), a rollback is "ignore the new columns" — no data loss for existing readers.
- The golden suites (`test_race_config_id_hash.py`, fan-out allowlist) are the tripwire: if any migration perturbs `config_id` or the allowlist, those tests fail the run.

---

## 7. Test plan (Program 3 §29 — DB level)

New suites, all offline/DB-only (no PyQt):
- `test_program3_migration_v32_v36.py` — fresh-DB build; migrate from a seeded v31; **idempotency** (run twice = no-op); **ordering-preservation** (§3 proof obligation); reversibility notes exercised.
- `test_program3_identity_uuid.py` — every core row has a unique non-null uuid; `new_id()`/`backfill_id()` shape + monotonicity.
- `test_program3_session_run.py` — planned-vs-actual: a plan can have N runs; runs never merged by name/type; failed run ≠ successful run.
- `test_program3_legacy_classification.py` — the four buckets; **no AMBIGUOUS row is auto-assigned**; quarantined rows excluded from learning reads.
- `test_program3_config_id_untouched.py` — asserts `config_id` and `setup_history.json` keys identical pre/post migration (belt-and-suspenders over the frozen golden).
- Full batched regression stays green (~10,392), run in quarters per the known Win/Py3.14 PyQt segfault.

---

## 8. Explicit Phase-B non-goals (deferred, not forgotten)

- Repointing the ~50 `ORDER BY id` queries or the `id==0` sentinels (→ Phase C).
- Threading `EngineeringContextKey`/uuid through the live runtime + revision-token stale guard (→ Phase C).
- Typed commands + atomic event switch + header fields (→ Phase D).
- PTT audit trail (→ Phase F, pending the transcript-persistence decision).
- Archetype vs full-context learning philosophy (→ Phase I).
- Populating `strategy_revisions`/`race_state_snapshots` at runtime (→ Phase G); v34 only creates the tables + seeds v1.

---

## 9. Reviewer decisions (2026-08-01)

1. **DB backup on first migrated launch** — ✅ Yes, write a one-time `session.db.pre_v32.bak`.
2. **Programme identity** — ✅ **Replace** the `cycle_id` slug with a UUID (v33, with code churn to config/`resolve_active_cycle`/`race_plan`/activity binding/`_cycle_id_for`).
3. Increment scope unchanged: v32 purely additive first.
