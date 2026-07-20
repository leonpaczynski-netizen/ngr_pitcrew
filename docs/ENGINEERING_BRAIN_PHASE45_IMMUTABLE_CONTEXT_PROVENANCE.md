# Engineering Brain — Program 2, Phase 45: Immutable Engineering Context Provenance

Read-only-by-default, offline, deterministic. Part of the **Phases 45–47 Provenance / Live / Voice**
slice. **DB v26 → v27** (justified additive migration); rule engine **46.0** unchanged.

## Why a snapshot (not a reference)

A reference to a mutable Event Planner record is not historical provenance: editing the event would
retroactively change what old evidence means. Phase 45 persists the exact SEMANTIC context content at
capture time, immutably.

## Authority ownership

| Module / entity | Owns |
| --- | --- |
| `strategy/engineering_context_snapshot.py` | pure snapshot content, canonical serialization, digest, fingerprint, validation. |
| `strategy/historical_context_resolution.py` | recover a record's historical context (per-field source markers). |
| `data/session_db.py` (v27 tables + methods) | persistence + references (explicit-write-only). |

## Snapshot fields

30 semantic fields: driver, car, car_variant, track, layout_id, event_id, discipline, compound,
compound_policy, bop_state, tuning_permitted, power_restriction, weight_restriction, tyre_multiplier,
fuel_multiplier, refuel_rate, race_type, race_duration, race_lap_objective, weather, grip_state,
assist_policy, gt7_version, rule_engine_version, data_schema_version, applied_setup_id,
applied_setup_fingerprint, parent_setup_id, run_plan_fingerprint, experiment_id. `event_name` is
display-only. Unknown fields stay empty (never fabricated).

## Semantic fingerprint

Full sha256 `semantic_digest` over the canonical (sorted-key, ASCII, allow_nan=False) semantic content +
schema id, via the shared serializer; plus a short display `short_fingerprint`. The digest EXCLUDES:
database row id, insertion order, machine identity, filesystem paths, UI state, wall-clock capture time,
and `event_name`. Two contents differing only in display/audit-time compare equal; any material edit
changes the digest.

## Persistence schema (v27)

Two additive tables (`CREATE IF NOT EXISTS`, idempotent, touching no existing table):

- `engineering_context_snapshots(semantic_digest PK, short_fingerprint, schema_version, eval_version,
  content_json, validation_state, captured_at)` — content-addressed by digest ⇒ dedup; `captured_at` is
  an operational audit timestamp, never in the digest.
- `engineering_context_snapshot_refs(ref_kind, ref_key, semantic_digest, created_at, PK(ref_kind,
  ref_key))` — one snapshot per canonical record; indexed by digest.

Migration: `_migrate_v27` + `DB_VERSION 26 → 27`. Fresh DB → v27; legacy v26 DB upgrades additively;
repeated startup idempotent; existing data preserved; transaction-level rollback safe. `RULE_ENGINE_VERSION`
unchanged.

## Capture boundaries (explicit-write-only)

`capture_context_snapshot(content, ref_kind, ref_key)` is the ONLY writer, called only from explicit
workflows (session finalize / experiment create / outcome record / applied-setup checkpoint / assisted-
run confirm). Viewing a panel or refreshing the dashboard captures NOTHING (the runtime report includes
only a pure snapshot PREVIEW). Immutability: content-addressed `INSERT OR IGNORE` — identical content
re-uses the existing row; existing records may reference it; later event edits do not change stored
content.

## Legacy records & reconstruction

`resolve_historical_context` prefers a directly-persisted snapshot; each field is marked
`directly_persisted` / `resolved_through_reference` / `inferred_with_limitations` / `unknown`. A legacy
record without a snapshot resolves to all-UNKNOWN (`legacy_partial`) — never back-filled from the current
event. **Event-edit reconstruction proof (test):** event tyre×5/fuel×3/BoP off, snapshot captured; event
edited to ×8/×5/on; the old evidence still resolves to ×5/×3/off, new evidence to the new conditions,
and the two contexts have different digests (not merged as exact).

## Context sensitivity (Correction B)

Mechanism-level requirements (`MECHANISM_REQUIRED` + `build_field_working_window_trust`) cap gearing /
aero / suspension / LSD legacy evidence to `PARTIAL_CONTEXT` when their material setup/event conditions
(BoP / restrictions / applied-setup identity) are unknown, while driver_technique stays broadly
transferable. See the pre-phase corrections doc.

## Safety

Pure snapshot/resolution modules (no Qt/DB/network/AI/clock/random); the DB writer is explicit-only and
additive; no runtime files modified by migration.
