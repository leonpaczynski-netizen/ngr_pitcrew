# Engineering Brain — Phase 2: Persisted Setup Experiments & Recommendation Evidence Ledger

**Status:** implemented on branch `eng-brain-phase2-setup-experiments` (from `master` @ `3d7c6af`, the Phase 1 tip fast-forwarded onto master).
**Schema:** SQLite `user_version` **20 → 21** (`DB_VERSION = 21`). `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** durable evidence ledger only. It does NOT perform before/after outcome
scoring, automatic success/failure judgement, physics, new setup rules, new
strategy maths, auto-apply, auto-pit, UI redesign, or mixin decomposition (Phase 3+).

## Why

Phase 1 gave every session/checkpoint/lineage/feedback record a shared canonical
identity (`scope_fingerprint`). Phase 2 turns every **setup recommendation** into a
persisted, traceable, reversible **engineering experiment** anchored to that
identity, so the Engineering Brain can later answer: what problem, on which
driver/car/track/layout/event/discipline, which setup applied, what evidence
justified it, which values changed, what should improve, what must be protected,
what counts as success/regression, how many laps, which corners, what to restore on
failure, and which later telemetry/feedback belongs to the experiment.

## Doctrine

A recommendation is a controlled, reversible experiment:

```
Observe → Diagnose → Form hypothesis → Define protected behaviours
→ Propose minimum effective changes → Persist experiment → Apply setup
→ Gather test evidence → Evaluate outcome (Phase 3)
```

Unknown evidence stays unknown. The system never invents corner attribution,
confidence, expected gains, applied values, driver outcomes, telemetry evidence or
rollback success.

## Ownership

| Concern | Owner |
|---|---|
| **Experiment identity + lifecycle** | `strategy/setup_experiment.py::SetupExperiment` (pure) |
| Canonical engineering identity | Phase 1 `data/engineering_context_key.py` (used, never recomputed) |
| Persistence + repository APIs | `data/session_db.py` (v21 tables + methods) |
| Recommendation source-of-truth | the parsed advisor `_data` JSON dict (NOT rendered HTML) |

Phase 2 creates **no** competing event/session/setup/track/context system; it
composes Phase 1 and the existing deterministic setup engine.

## Pure domain — `strategy/setup_experiment.py`

Qt-free, DB-free, UI-free, network-free, AI-free. Imports ONLY the pure Phase 1
identity module to obtain (never recompute) the context fingerprints; never
imports PyQt, UI, SessionDB, or setup-Apply modules.

- **Enums:** `ExperimentStatus` (DRAFT, READY_FOR_APPLY, APPLIED, TEST_IN_PROGRESS,
  READY_FOR_REVIEW, COMPLETED, REJECTED, REVERTED, CANCELLED, INVALID),
  `ChangeRole` (PRIMARY/SUPPORTING/PROTECTED/DEFERRED), `ChangeKind`
  (DIAGNOSTIC/PERFORMANCE), `EvidencePhase` (BASELINE, DIAGNOSIS, RECOMMENDATION,
  APPLY_VERIFICATION, TEST, DRIVER_REVIEW, OUTCOME), `EvidenceStance`,
  `HandlingPhase` (entry/mid_corner/exit/braking/traction/platform/gearing/
  tyre_fuel), `AppliedMatchState` (MATCH/PARTIAL_MATCH/MISMATCH/UNVERIFIABLE).
- **Frozen models:** `ExperimentChange`, `ProtectedBehaviour`, `TestProtocol`,
  `ExperimentEvidence`, `ExperimentHypothesis`, `StateTransition`, `SetupExperiment`.
- **Two identifiers on the experiment:** the Phase 1 `scope_fingerprint` (the stable
  before/after join key) and the full `context_fingerprint`, plus
  `context_status` / `context_unresolved` / `context_warnings`.
- **Idempotency:** `compute_idempotency_key(exp)` = versioned sha256 over
  `{schema, scope_fingerprint, parent_setup_id, recommendation_source,
  rule_engine_version, rec_status, ORDERED (field,to_value) actionable changes}`.
  **Never a timestamp**, and stable under change reordering — so repeated
  rendering / tab-switching / reopening a recommendation reproduces the same key
  and never creates a duplicate experiment.
- **State machine:** `VALID_TRANSITIONS` graph + `validate_transition(...)` with
  honesty gates: READY_FOR_APPLY needs actionable changes; APPLIED needs a
  checkpoint link; READY_FOR_REVIEW needs test evidence; **COMPLETED needs a
  Phase-3 outcome record (unavailable until Phase 3)**. Terminal states have no
  exits. No automatic progression.
- **Applied-value verification:** `compare_proposed_vs_applied(proposed, applied)`
  → MATCH / PARTIAL_MATCH / MISMATCH / UNVERIFIABLE, using canonical field ids,
  numeric tolerance only for numeric-vs-numeric, literal string equality
  otherwise (never coerces unrelated units), reporting missing fields and
  preserving actual applied values.
- **Builder:** `build_experiment_from_recommendation(data, ...)` maps the parsed
  advisor `_data` dict → a DRAFT `SetupExperiment`, or returns `None` when the
  recommendation is not actionable (status ∉ `APPROVED_STATUSES`, or no approved
  changes). Captures recommendation-time evidence via
  `recommendation_evidence_from_data`.

## Persistence — DB schema v21 (additive, six standalone tables)

`_migrate_v21` (`CREATE IF NOT EXISTS` ⇒ idempotent; touches no existing table):

- **`setup_experiments`** — the immutable creation record. `idempotency_key` is
  UNIQUE. First-class indexed join columns: `scope_fingerprint`,
  `context_fingerprint`, `parent_setup_id`, `lineage_id`, `applied_checkpoint_id`,
  `session_id`, `status`, `created_at`. Administrative mutable columns only:
  `status`, `applied_checkpoint_id`, `applied_match_state`,
  `applied_comparison_json`.
- **`setup_experiment_changes`** — append-only structured deltas (field, subsystem,
  from/to (NULL = unknown), direction, magnitude, unit, rationale, expected effect,
  side effects, contraindications, role, kind, order, rule_id, provenance).
- **`setup_experiment_protected_behaviours`** — confirmed-good behaviours to preserve.
- **`setup_experiment_test_protocol`** — 1:1 deterministic test plan (min/preferred
  clean laps NULL when unknown, target corners, success/failure criteria,
  rollback target, …).
- **`setup_experiment_evidence`** — append-only evidence ledger (references +
  structured summaries + phase + stance + provenance; **never telemetry blobs**).
- **`setup_experiment_state_history`** — append-only lifecycle transitions.

Unknown numeric values are `NULL` (not placeholder strings). JSON is used only for
genuinely nested payloads; all join fields are first-class columns.

### Repository APIs (SessionDB — existing lock/commit conventions; no raw SQL to UI)

`create_setup_experiment` (atomic BEGIN/COMMIT, full ROLLBACK on any child
failure; idempotent by `idempotency_key`), `get_setup_experiment`,
`list_setup_experiments_by_scope / _by_parent_setup / _by_lineage / _by_checkpoint /
_by_session`, `append_experiment_evidence` (append-only),
`transition_experiment_state` (validates via the domain; gate predicates are read
from stored DB state so they cannot be faked), `get_experiment_state_history`,
`get_experiment_evidence`, `find_applyable_experiment_for_scope`,
`link_experiment_applied_checkpoint` (→ APPLIED + comparison; idempotent per
checkpoint), `invalidate_setup_experiment`, `cancel_setup_experiment`, and two
orchestration seams `record_recommendation_experiment` /
`link_apply_to_experiment`.

## Idempotency rule

An experiment is de-duplicated by `idempotency_key` (see above). `create_setup_
experiment` pre-checks the UNIQUE key and returns the existing id rather than
writing a duplicate. Repeated Analyse rendering, tab switching, or reopening the
recommendation view therefore never creates a second experiment.

## Production integration

- **Analyse (create):** `ui/setup_builder_ui.py::_display_setup_result` — after the
  advisor JSON is parsed and `_status_approved` is computed, for
  `entry_type == "analyse_setup"` only, it calls
  `db.record_recommendation_experiment(data, ...)`. Best-effort, outside the Apply
  gate, never blocks the UI. The gate predicate itself is unchanged.
- **Apply (link):** `ui/setup_builder_ui.py::_on_changes_applied_in_game` — after
  `save_applied_checkpoint`, it calls `db.link_apply_to_experiment(...)`, which
  resolves the same Phase 1 scope, finds the experiment awaiting apply, links the
  checkpoint (→ APPLIED) and stores the proposed-vs-applied comparison. It does
  **not** auto-apply and **never** alters the original recommendation.

### Baseline Build — explicit decision (NOT an experiment)

The baseline **Build** path (`build_baseline_setup_response`,
`entry_type == "baseline_setup"`) is deliberately excluded. A from-scratch
full-field baseline is a **setup artefact**, not a controlled reversible test of a
hypothesis against a parent setup: it has no parent-relative diagnosis, no
minimum-effective-intervention delta, and no protected-behaviour contract to test.
Only the incremental, hypothesis-driven Analyse path creates an experiment.

## Immutability & audit

After creation, the hypothesis, proposed changes, evidence snapshot, test protocol,
expected effects, protected behaviours, confidence and rollback target are never
overwritten. Corrections are append-only (amendment evidence, state history,
superseding experiment, or administrative INVALID/CANCELLED with a reason). A
proposed-vs-applied MISMATCH is recorded alongside the record and never rewrites the
original recommendation.

## Mismatch handling & rollback

`link_experiment_applied_checkpoint` stores `applied_match_state` +
`applied_comparison_json` on the parent row (visible in structured output) and
appends the APPLIED transition. The `rollback_target` (the parent / proven setup)
is captured at creation and is never changed by an apply mismatch.

## What Phase 2 deliberately does NOT do

Before/after outcome scoring, success/failure judgement, contraindication /
failed-direction *learning* (only existing lockout evidence is captured, faithfully),
new setup authoring, physics, strategy maths, telemetry thresholds, UI redesign,
new track assets, dormant-engine deletion. COMPLETED remains unreachable in
production until Phase 3 supplies an outcome record.

## Phase 3 — DELIVERED

Phase 3 (Closed-Loop Outcome Evaluation, Regression Detection & Failed-Direction
Learning) is now implemented — see `docs/ENGINEERING_BRAIN_PHASE3_OUTCOME_EVALUATION.md`.
It added DB v22 (`setup_experiment_outcomes` + children + `setup_experiment_failed_directions`),
`strategy/setup_experiment_outcome.py`, and the `evaluate_setup_experiment`
orchestrator; `has_outcome_record` is now real so COMPLETED is honestly gated.
The original Phase-3-prerequisite notes below are retained for history.

Phase 3 (Closed-Loop Outcome Evaluation, Regression Detection & Failed-Direction
Learning) will: add an outcome table, attach TEST / DRIVER_REVIEW / OUTCOME-phase
evidence to each experiment, compute before/after per-corner deltas keyed on
`scope_fingerprint`, judge improvement/regression against the persisted
success/failure criteria and protected behaviours, drive READY_FOR_REVIEW →
COMPLETED / REJECTED, and turn confirmed regressions into failed-direction lockouts.
All hooks (evidence phases, gate predicates, comparison, immutable protected
behaviours, rollback target) already exist in Phase 2.
