# Engineering Brain — Phases 45–47 Pre-Phase Corrections (A & B)

Read-only audit + corrections applied before the Phase 45–47 work. No earlier commit is amended.

## Correction A — Stale Phase 6 regression test

**Root cause.** `tests/test_phase6_wiring.py::test_no_migration_no_new_telemetry_table` asserted
`"_DDL_V26" not in src and "_migrate_v26" not in src`. That was true when written (before Phase 19), but
Phase 19 legitimately introduced database version 26 (`_DDL_V26` / `_migrate_v26`), so the test forbade
the entire legitimate migration chain rather than the actual Phase-6 invariant. It failed identically at
every recent checkpoint (unrelated to the intervening slices).

**Correction.** The test now proves the real Phase-6 invariant against a freshly-created database:
`PRAGMA user_version == DB_VERSION` (schema coherent with the *legitimate* migration chain, including
v26 and the new v27); no residual/telemetry persistence table exists (Phase 6 residual detection is
pure); and no telemetry table exists beyond the canonical base stores
(`{lap_telemetry, corner_slip_telemetry}`). It does not weaken migration safety generally. Verified
against: the v26 checkpoint (passes), the new Phase-45 v27 schema (passes), a fresh DB and a migrated
legacy DB (migration tests in the Phase-45 suite).

## Correction B — Mechanism-level context sensitivity

**Root cause.** The Phase-42 coarse `DOMAIN_REQUIRED` map let some legacy records stay *exact* for
`setup_working_windows` / `driver_technique` / `vehicle_dynamics` even when the material *setup* or
*event* conditions a specific mechanism depends on were unknown.

**Correction.** Added a finer `MECHANISM_REQUIRED` map + `field_to_mechanism` + a field-level
`build_field_working_window_trust`, so a specific setup field caps to `PARTIAL_CONTEXT` when its
mechanism's material conditions are unknown:

| Mechanism | Required (must be a known match for exact) |
| --- | --- |
| gearing_acceleration | car, track, layout, BoP, power, weight, discipline, gt7, applied-setup, compound |
| aero | car, track, layout, BoP, power, weight, discipline, gt7, applied-setup |
| suspension_ride_height | car, track, layout, discipline, compound, applied-setup |
| lsd_traction | car, discipline, compound, applied-setup |
| driver_technique | driver, car, track (broad transfer; limitations retained) |

Legacy records carry only the memory key (driver/car/track/layout/discipline/compound/gt7) — they lack
BoP/restrictions/applied-setup identity — so gearing/aero/suspension/LSD legacy evidence is now
correctly capped to `PARTIAL_CONTEXT`, while driver_technique stays exact. Full-context evidence (with
applied-setup identity + restrictions known) is exact. Every eligibility decision still exposes required
/ known / missing / inferred fields, the confidence cap and the reason. The coarse `DOMAIN_REQUIRED`
map is retained for backward compatibility; `build_material_context_trust` accepts either a domain or a
mechanism key.

## Phase 42–44 documentation caveats (stated per the task)

1. The Phase-6 regression test was **stale** and is corrected as above.
2. The Phase 42–44 **offscreen UAT did not prove live GT7 prompt usability** — only that the code paths
   construct and behave deterministically headlessly.
3. A **semantic fingerprint without persisted snapshot content was insufficient** for permanent
   historical reconstruction — Phase 45 persists immutable snapshot **content** (a v27 table), not just
   a fingerprint or a reference to a mutable event.
4. The broad domain-level context requirements **required mechanism-level refinement** (Correction B).

## Post-slice corrections (recorded during the Phase 48–50 slice)

These five items were verified directly against the working tree and Git before Phase 48 began. No
Phase 45–47 commit is amended; this is an additive documentation correction.

### 1. Exact ordered Phase 45–47 commit hashes and subjects

The slice landed as ten focused commits on `eng-brain-phase45-47-provenance-live-voice`
(parent `ce01383`, the Phase 42–44 tip):

| # | Hash | Subject |
| --- | --- | --- |
| 1 | `fdea935` | Eng Brain P2 Phase 45-47 (1/10): stale Phase-6 test repair (Correction A) + context-sensitivity (Correction B) |
| 2 | `4cc0f44` | Eng Brain P2 Phase 45-47 (2/10): Phase 45 immutable context-snapshot domain |
| 3 | `470cc67` | Eng Brain P2 Phase 45-47 (3/10): Phase 45 schema migration (v27) + snapshot capture/reference |
| 4 | `d2da493` | Eng Brain P2 Phase 45-47 (4/10): Phase 45 legacy handling + historical reconstruction |
| 5 | `dfdba59` | Eng Brain P2 Phase 45-47 (5/10): Phase 46 telemetry replay + message-duration budget |
| 6 | `a228d94` | Eng Brain P2 Phase 45-47 (6/10): Phase 46 shadow-mode advisory validation |
| 7 | `65a78e3` | Eng Brain P2 Phase 45-47 (7/10): Phase 47 offline voice adapter + delivery queue |
| 8 | `d43c58a` | Eng Brain P2 Phase 45-47 (8/10): Phase 47 voice controller + acknowledgement + UI + failure handling |
| 9 | `8c0407a` | Eng Brain P2 Phase 45-47 (9/10): SessionDB shadow-validation + snapshot preview + voice wiring |
| 10 | `0447375` | Eng Brain P2 Phase 45-47 (10/10): tests, golden fixtures, runtime verification and documentation |

### 2. Clarified migration wording (v26 → v27)

Phase 45 is the **first** `DB_VERSION` bump since Phase 19 (v25 → v26). `_migrate_v27`
(`data/session_db.py`) is a pure **additive** step: it `executescript(_DDL_V27)`, which is two
`CREATE TABLE IF NOT EXISTS` statements plus one index — it never rewrites, drops, or back-fills any
existing row. On a fresh database every table is created up-front by the concatenated `_DDL` and the
migration ladder is a no-op against already-present tables; on a legacy v26 database only the two new
snapshot tables are added and `user_version` advances 26 → 27. The step is idempotent across repeated
opens. No legacy session, event, experiment, outcome, working-window, or context row is touched.

### 3. Snapshot and snapshot-reference writer ownership (single canonical boundary)

`SessionDB.capture_context_snapshot(content, *, ref_kind="", ref_key="", captured_at=None)` is the
**only** public method that writes either the `engineering_context_snapshots` content table (content-
addressed by `semantic_digest`, `INSERT OR IGNORE` → dedup) **or** the `engineering_context_snapshot_refs`
mapping table. It is **explicit-only**: viewing, refreshing, replaying, live-advisory evaluation, and
every `build_*_report` read-model perform SELECT-only access and never call it (proven by
`tests/test_phase45_47_safety.py::test_snapshot_capture_is_explicit_write_only`). The intended explicit
callers are session-finalize, experiment-create, outcome-record, applied-setup checkpoint, and
assisted-run confirm. The digest excludes `event_name` (display-only), audit time, row identity, and
paths, so the same environment content dedups to one immutable row regardless of when or under what
event label it was captured.

### 4. Database-version assertion audit

Of the test files that reference the schema version, all but two assert
`PRAGMA user_version == DB_VERSION` **dynamically** (imported constant) and therefore follow a bump
automatically and correctly. Only the following pin a **literal**:

- `tests/test_phase45_47_migration.py` lines 30, 39, 80 legitimately prove the **v26 → v27**
  Phase-45 migration lands at exactly `27` (they simulate a legacy v26 DB). These are version-specific
  step proofs and **remain literal 27** even after later bumps.
- `tests/test_phase45_47_migration.py:16` (`== DB_VERSION == 27`) and
  `tests/test_phase45_47_safety.py:71` (`assert DB_VERSION == 27`) conflate "current schema" with the
  literal 27; when `DB_VERSION` advances these must move to the new current value (or, better, assert
  `== DB_VERSION` and prove the v27 tables separately).

**Correction to this audit (recorded during the Phase 48–50 slice).** The count above was too small.
The repository convention is that *each phase's test suite pins the current schema version as a
literal* and bumps it every slice (Phase 45 itself moved a large set of `… == 26` assertions to `27`).
A full sweep at v28 found the current-schema literal in **~50 assertions across ~40 phase/group test
files** (patterns `== DB_VERSION == N`, `fetchone()[0] == N`, `== v0 == N`, `== uv_before == N`,
`uv == N`, `uv0 == N`, and `DB_VERSION == N and RULE_ENGINE_VERSION == …`). The Phase 48–50 slice
bumped every such **current-schema** literal 27 → 28, decoupled the genuine **v26 → v27 step proofs**
in `test_phase45_47_migration.py` to `== DB_VERSION` + table-existence checks, and left unrelated
literals (e.g. a `len(labels) == 27` UI count) untouched. Two guards were verified to be **pre-existing
failures already red at the `0447375` checkpoint** and were left unchanged, as they belong to prior
slices and are out of scope here:

- `tests/test_phase6_golden_uat.py::test_no_migration_needed` — asserts `"_migrate_v26" not in src`,
  but `_migrate_v26` has existed since Phase 19 (same stale-guard class as Correction A above).
- `tests/test_phase33_35_safety.py::test_no_schema_migration_added_by_slice` — diffs
  `4b485be..HEAD` for `_setup_constants.py`, already non-empty at the checkpoint because Phase 45
  bumped `DB_VERSION` 26 → 27 relative to that Phase-32 baseline.

### 5. Environment-snapshot vs execution-binding audit result

The immutable **event-environment identity** (driver / car / track / layout / rules / BoP / restrictions
/ tyre + fuel multipliers / GT7 version / rule-engine version) captured by
`engineering_context_snapshot` is cleanly separate from **execution/session identity** (applied setup,
parent setup, discipline, run plan, experiment, telemetry session, objective, feedback). The snapshot
digest is content-addressed over environment fields only and deliberately excludes execution identity
and audit time; execution rows (`sessions`, `setup_experiments`, `engineering_context_links`) reference
context by the Phase-1 scope spine, not the reverse. This separation is what lets Phase 48 add a
**preparation-programme** layer (grouping many execution sessions under one upcoming round) without
mutating or re-binding any immutable environment snapshot.
