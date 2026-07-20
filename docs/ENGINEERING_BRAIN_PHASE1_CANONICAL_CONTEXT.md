# Engineering Brain — Phase 1: Canonical Engineering Context & Identity Bridge

**Status:** implemented on branch `eng-brain-phase1-canonical-context` (from `master` @ `c611d79`).
**Schema:** SQLite `user_version` **19 → 20** (`DB_VERSION = 20`). `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** architecture + data-foundation only. No vehicle-dynamics physics, no new
setup rules, no UI redesign, no automatic setup application, no automatic pit calls,
no experiment/outcome loop (those are Phase 2+).

## Why

The app had grown several *incompatible* identity systems:

- sessions & strategy records key on **`config_id`** (a 10-char match key);
- engineering & track records key on **`layout_id` / `track_location_id`**;
- some track fields are **free text**;
- applied setups, setup lineage, lap records, driver feedback and per-corner
  evidence did **not** all share one joinable engineering context.

That split blocks reliable cross-session engineering learning and honest
before/after setup comparison. Phase 1 creates **one deterministic, evidence-honest
identity spine** that future recommendations, applied setups, telemetry sessions,
driver feedback, per-corner evidence, experiments and outcomes can all share.

## The core engineering context

```
this driver + this car + this track + this layout + this event
+ this discipline + this GT7 version + this applied setup
+ this setup lineage + this telemetry session and run
```

## Single-source ownership rules

| Concern | Owner | Notes |
|---|---|---|
| **Canonical engineering identity** | `data/engineering_context_key.py::EngineeringContextKey` | The ONE identity spine. Pure, typed, deterministic. |
| **`config_id` match key** | `data/working_race_config.py::WorkingRaceConfig.compute_config_id` | **Compatibility ID. Never recalculated by the engineering module.** Frozen golden vectors in `tests/test_race_config_id_hash.py`. |
| **`layout_id` / `track_location_id`** | `data/track_context.py` (canonical), `data/event_context.py` | Authoritative track/layout identity; flow INTO the context as components. |
| Event truth | `data/event_context.py` | Composed behind the engineering-context boundary, not replaced. |
| Persistence of contexts | `data/session_db.py` (v20 tables) | Additive bridge; no existing table altered. |

**This group does NOT create a second competing event/session/setup/track context
system.** It composes the existing canonical read models behind a new identity
boundary.

## The pure identity module — `data/engineering_context_key.py`

Pure: **no PyQt, no DB, no network, no generative AI**; resolvers never raise.

### `EngineeringContextKey` (frozen dataclass)

13 `Optional[str]` components — `None` means **genuinely unknown / unavailable**
(never a manufactured placeholder), a string means **known** (normalised):

`driver_id, car_id, track_location_id, layout_id, event_id, discipline,
gt7_version, config_id, setup_id, applied_checkpoint_id, lineage_id, session_id,
run_id`

Numeric ids normalise through `_norm`: `None` / `""` / whitespace / `0` (the
schema's unset sentinel) → **unknown**, so a default id never masquerades as
authoritative identity.

### Two versioned identifiers

- **`fingerprint()`** — the FULL identity fingerprint over all 13 components.
  Deterministic; any material change (or enrichment of a previously-unknown field)
  yields a different value. Shape: `eck_v1:<16 hex>`.
- **`scope_fingerprint()`** — the STABLE physical-scope join key over
  `(driver_id, car_id, track_location_id, layout_id, gt7_version)` **only** —
  invariant to session / run / setup / discipline / event / config. Shape:
  `eck_v1:scope:<16 hex>`. **This is the key future setup experiments and outcomes
  join on** for before/after comparison: a telemetry session, an applied-setup
  checkpoint, a lineage node and a driver-feedback record taken on the same
  car/track/layout resolve to the SAME scope even though their volatile components
  differ.

Both are versioned by `FINGERPRINT_VERSION = "eck_v1"` so the algorithm can evolve
without silently re-keying stored joins. A KNOWN empty string and an UNKNOWN field
serialize differently (`§` vs a `\x00∅` token), so "known-but-blank" never collides
with "genuinely unknown".

### Honest resolution

`EngineeringContextResolution` returns far more than an id:

- `context` (the key), `status`, `provenance` (per-field source), `unresolved`,
  `ambiguous`, `warnings`, `fingerprint_version`.

`ResolutionStatus`: **COMPLETE / PARTIAL / AMBIGUOUS / UNRESOLVED / INVALID**.

**Ambiguity is reported, never guessed.** A free-text track alone never invents a
`layout_id`. If unambiguous track-library candidates are supplied and exactly one
matches, the layout resolves (provenance `track_library`, with a warning); >1
candidates → `AMBIGUOUS` (field left unresolved); 0 → unknown with a compatibility
warning. Different layouts at one venue stay distinct.

### Enrichment without contradictory duplicates

`EngineeringContextKey.enrich(other)` fills THIS key's unknown fields from `other`,
returning `(enriched_key, conflicting_fields)`. A field known in BOTH with
DIFFERENT values is a **conflict**: left unchanged (this key wins) and reported.
Enrichment can only ever ADD identity, never silently overwrite — so a partial
context is later enriched without creating a contradictory duplicate identity.

Driver feedback uses this: `resolve_feedback_against_session_context` inherits the
session's already-resolved identity (so it shares the session's `scope_fingerprint`)
and enriches with the feedback's own `config_id` / `setup_id`.

## The compatibility bridge — DB schema v20 (additive)

Two **standalone** tables (touch no existing table; `CREATE IF NOT EXISTS` ⇒
idempotent migration `_migrate_v20`):

- **`engineering_context`** — one row per distinct canonical context, keyed by its
  versioned full `fingerprint` (**UNIQUE**). Stores the 13 components (SQL `NULL`
  = genuinely unknown), the stable `scope_fingerprint`, the resolution `status`,
  and JSON `provenance` / `unresolved` / `ambiguous` / `warnings` for evidence
  honesty. Indexed by `scope_fingerprint`, `(car_id, track_location_id, layout_id)`
  and `config_id`.
- **`engineering_context_links`** — a compatibility BRIDGE from an existing record
  `(source_kind, source_id)` to a context `fingerprint` (+ `scope_fingerprint`),
  so historical rows resolve **without a destructive column migration**.
  `UNIQUE(source_kind, source_id)` makes linking idempotent (`INSERT OR REPLACE`).

`source_kind ∈ {session, applied_checkpoint, setup_lineage, driver_feedback, …}`.

### SessionDB API (best-effort, existing lock/commit conventions; never partial)

- `upsert_engineering_context(resolution) -> fingerprint|None` — `INSERT OR IGNORE`
  by fingerprint (idempotent, atomic single statement ⇒ never a partial write). An
  empty/invalid resolution is **not** stored (unknown identity is not a
  manufactured row).
- `link_engineering_context(source_kind, source_id, fingerprint, scope)` — idempotent.
- `resolve_and_link_engineering_context(resolution, source_kind, source_id)` —
  upsert + bridge in one call; returns `None` (no link) when there is no usable
  identity — an unresolved record stays honestly unlinked but still queryable.
- `get_engineering_context(fingerprint)`,
  `get_engineering_context_for_source(source_kind, source_id)`,
  `get_engineering_contexts_by_scope(scope)`,
  `get_engineering_context_links_by_scope(scope)`.

## Production integration points (minimal, high-value)

Wired at four stable write boundaries in `data/session_db.py`, each **best-effort
and outside the write lock** (a context failure never affects the underlying write):

1. `open_session(...)` → `source_kind='session'` (optional `layout_id`/`driver_id`/
   `gt7_version` kwargs feed the context ONLY; the sessions row is unchanged).
2. `save_applied_checkpoint(...)` → `source_kind='applied_checkpoint'`.
3. `record_lineage(...)` → `source_kind='setup_lineage'`.
4. `write_feedback(...)` → `source_kind='driver_feedback'`, **inheriting the
   session's stored context** (shares its scope, adds setup_id).

**Proof:** a newly created session, applied-setup checkpoint, setup-lineage node and
driver-feedback record for the same car/track/layout all resolve to the SAME
`scope_fingerprint` — without relying on free-text coincidence.

## Compatibility decisions

- **`config_id`** — algorithm and golden vector **unchanged**; it flows into the
  context as the `config_id` component only. The engineering module never imports
  `compute_config_id` and never recalculates it.
- **`layout_id` / `track_location_id`** — authoritative when present; a free-text
  track never silently conflates layouts.
- **Free-text tracks** — kept as compatibility input; resolved to a layout only on
  a single unambiguous track-library candidate, else left unknown/ambiguous.

## Known limitations (honest)

- The `sessions` table does **not** store `layout_id`; for a session and a
  layout-bearing checkpoint to join, the caller must pass `layout_id` at
  `open_session`. Legacy sessions (no layout) resolve to a *partial* context with
  `layout_id` unknown and therefore do not join layout-scoped records — which is
  the correct, honest behaviour (we cannot prove the legacy session's layout).
- `driver_id` and `gt7_version` are not yet persisted per-record; when unknown they
  stay `None` consistently, so records still join on the remaining scope.
- No UI surface consumes the context yet (out of scope for Phase 1).

## What Phase 1 deliberately does NOT do

No recommendation/experiment table, no outcome scoring, no physics, no new setup
recommendations, no UI redesign, no dashboard-mixin decomposition, no dormant-engine
deletion, no clean-lap consolidation, no strategy-math change, no telemetry-threshold
change, no new track reference-path assets.

**Next group:** Engineering Brain Phase 2 — Persisted Setup Experiments &
Recommendation Evidence Ledger (references this context via `scope_fingerprint`).
