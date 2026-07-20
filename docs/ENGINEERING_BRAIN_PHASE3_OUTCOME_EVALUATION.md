# Engineering Brain — Phase 3: Closed-Loop Outcome Evaluation, Regression Detection & Failed-Direction Learning

**Status:** implemented on branch `eng-brain-phase3-outcome-evaluation` (from `master` @ Phase 2 `b6f6dd4`).
**Schema:** SQLite `user_version` **21 → 22** (`DB_VERSION = 22`). `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** deterministic outcome engine only — NO new physics, NO new setup-authoring
rules, NO large UI redesign, NO automatic setup application, NO automatic rollback.

## Why

Phase 2 persisted every setup recommendation as a reversible experiment with a
hypothesis, structured changes, protected behaviours, a test protocol and a
canonical `scope_fingerprint`. Phase 3 closes the loop: it judges an APPLIED
experiment against measured test evidence and produces an **immutable engineering
outcome**, driving the lifecycle to COMPLETED/REJECTED and recording scoped
failed-direction learning for confirmed regressions.

## Doctrine (what "success" is NOT)

A change is not successful merely because the driver completed laps, lap time
improved once, one positive feeling was reported, one symptom vanished, or the
apply produced no error. An experiment is judged against its persisted hypothesis,
targeted symptoms, success/failure criteria, protected-good behaviours, valid
**repeatable** telemetry, driver feedback, the parent baseline, and confounders.
**An honest inconclusive outcome is preferred over a fabricated conclusion.**

## Composition (reuses existing authorities — no competing engines)

| Concern | Reused authority |
|---|---|
| Canonical identity | Phase 1 `scope_fingerprint` (obtained via the Phase 1 API, never recomputed) |
| Experiment + lifecycle | Phase 2 `SetupExperiment`, `validate_transition`, evidence ledger |
| Clean-lap windows | `data/recommendation_scoring.aggregate_lap_window` (clean = not pit/out) |
| Repeatability classes | `strategy/practice_pattern_analysis.RecurrenceThresholds` (isolated / emerging / recurring / strongly_recurring) |
| Verdict vocabulary | `improved / worsened / neutral / insufficient_data` |
| Failed-direction consumers | `strategy/setup_lineage.blocked_rules_from_outcomes`, `rollback_from_lineage`; `learning_outcomes` + `setup_lineage` tables |
| Driver feedback | deterministic structured fields (no generative text) |

## Pure domain — `strategy/setup_experiment_outcome.py`

Qt-free, DB-free, UI-free, network-free, AI-free; never raises for ordinary
missing-evidence. `OUTCOME_EVAL_VERSION = "setup_outcome_v1"`.

**Outcome states:** `CONFIRMED_IMPROVEMENT`, `PARTIAL_IMPROVEMENT`,
`NO_MEANINGFUL_CHANGE`, `REGRESSION`, `CONFOUNDED`, `INSUFFICIENT_EVIDENCE`.
Supporting enums: `CriterionVerdict` (met/partially_met/not_met/regressed/
unmeasurable/insufficient_evidence), `ProtectedVerdict` (preserved/minor_regression/
material_regression/unmeasurable), `CornerVerdict`, `AssociationStatus`
(resolved/ambiguous/mismatch/unresolved), `DriverTelemetryAgreement`, `NextAction`,
`LearningStrength` (lockout/caution/none), `ConfidenceLevel`.

**Aggregate `SetupExperimentOutcome`** carries: experiment id, scope fingerprint,
parent + applied-checkpoint refs, test session/run, eval version, status,
confidence + level, evidence completeness, criteria results, protected-behaviour
results, per-corner + whole-lap comparisons, regressions/improvements/neutral
findings, confounders, missing evidence, driver-agreement + summary, decision
rationale, next action, rollback eligibility + target, learning eligibility,
failed-direction records, and a deterministic idempotency key.

### Evidence association (never free-text coincidence)

`resolve_experiment_evidence_association(...)` returns an explicit
RESOLVED/AMBIGUOUS/MISMATCH/UNRESOLVED. It rejects/flags: scope-fingerprint
mismatch, applied-checkpoint mismatch, test session recorded before apply, absent
parent baseline, and **multiple plausible experiments → AMBIGUOUS** (never silently
picks the newest). Feedback that references a different setup is excluded.

### Test-validity gate

`evaluate_lap_validity(...)` builds validity from the clean-lap window authority:
valid laps = clean laps (pit/out already excluded); repeatability is assessable
only at ≥ `min_required` (the persisted Phase-2 `test_protocol.min_clean_laps`,
else 3). Reports total/valid/rejected laps + reasons, telemetry completeness, setup
identity + track-position confidence. An isolated bad lap cannot justify a verdict.

### Before-vs-after comparison

* **Whole-lap** (`compare_whole_lap`) — **median** lap time (never fastest alone),
  lap-time stdev (consistency), incident count. Materially faster ≤ −200 ms;
  materially slower ≥ +300 ms; consistency-regressed ≥ +250 ms stdev.
* **Per-corner** (`compare_corners`) — keyed on (segment/corner, issue_type);
  classifies each side's recurrence and returns improved/unchanged/regressed/
  unmeasurable. A repeatable same-corner pattern outweighs one isolated event; a
  metric is only compared when genuinely available on both sides. No invented GT7
  channels (no steering angle, tyre-wear %, or true slip).

### Criteria + protected behaviours

The **primary target criterion** is the diagnosed symptom judged by per-corner
recurrence at the target corners (never general lap time). Persisted free-text
success criteria are supporting (a regressed one still triggers regression). Each
protected behaviour matches ONLY its own corners; a new recurring issue there is a
MATERIAL regression. **A material protected regression prevents CONFIRMED_IMPROVEMENT**
(and normally forces REGRESSION) — a target win never hides it.

### Driver / telemetry arbitration

`arbitrate_driver_vs_telemetry` preserves disagreement: agree→strong, positive
telemetry + negative driver→partial/downgrade, wrong-setup feedback→excluded. The
deterministic outcome status never depends on generative text interpretation.

### Deterministic decision table (`decide_outcome`)

1. association not RESOLVED → **INSUFFICIENT_EVIDENCE**
2. any confounder → **CONFOUNDED**
3. validity insufficient → **INSUFFICIENT_EVIDENCE**
4. target regressed / material protected regression / any criterion regressed /
   new repeatable issue / median materially slower → **REGRESSION**
5. target met + no protected regression + confidence ≥ threshold + driver not
   disagreeing → **CONFIRMED_IMPROVEMENT**
6. some targets/partial/minor protected regression → **PARTIAL_IMPROVEMENT**
7. valid but nothing material changed → **NO_MEANINGFUL_CHANGE**
8. else → **INSUFFICIENT_EVIDENCE**

### Failed-direction learning + minimum-effective intervention

`build_failed_direction_learning` fires ONLY on a REGRESSION with sufficient valid
evidence. Strong, single-field, repeatable → **LOCKOUT**; weaker or **compound
(multi-field)** → **CAUTION** with low attribution confidence (prefer an isolation
follow-up rather than a wrong field-level lockout). Never from an invalid/
confounded/insufficient test; scoped to this driver/car/track/layout only — never
global. `build_next_action` recommends retain / retain-successful-direction /
revert / repeat-more-laps / isolate-field / reduce-magnitude / test-opposite /
protect-window — it never applies them.

Metamorphic guarantees (tested): stronger improvement can't reduce a success
verdict without another material regression; unrelated isolated noise can't flip an
improvement to a regression; a protected regression can't improve the outcome;
fewer valid laps can't raise confidence; changing scope/checkpoint breaks
association; evaluation order doesn't change the result.

## Persistence — DB schema v22 (additive, five standalone tables)

`_migrate_v22` (`CREATE IF NOT EXISTS` ⇒ idempotent; touches no existing table):

- **`setup_experiment_outcomes`** — the IMMUTABLE outcome, keyed by UNIQUE
  `idempotency_key`. Only the audit columns `superseded_by` / `invalidated_reason`
  are ever UPDATEd; the engineering conclusion is never overwritten. First-class
  indexed join columns: experiment_id, scope_fingerprint, applied_checkpoint_id,
  test_session_id, status.
- **`setup_experiment_outcome_criteria`** / **`_protected`** / **`_corners`** —
  append-only per-criterion / protected-behaviour / per-corner verdicts.
- **`setup_experiment_failed_directions`** — scoped lockout/caution learning
  (driver, car, track, layout, discipline, field, from/to, direction, magnitude,
  symptom, corners, confidence, attribution confidence, evidence count, rule id).

### Repository + orchestration APIs (SessionDB)

`create_experiment_outcome` (atomic BEGIN/COMMIT, full ROLLBACK on any child
failure; idempotent by key — duplicate evaluation returns the existing id),
`get_experiment_outcome`, `get_latest_experiment_outcome`,
`list_experiment_outcomes`, `supersede_experiment_outcome` (audited),
`invalidate_experiment_outcome` (audited), `list_failed_directions_by_scope`,
`list_failed_directions_for_field`, `find_latest_reviewable_experiment`, and the
high-level **`evaluate_setup_experiment(...)`** orchestrator.

`_experiment_gate_state` now computes `has_outcome_record` from a real
(non-superseded, non-invalidated) outcome row — so **COMPLETED is honestly gated**:
it is impossible without a persisted Phase-3 outcome.

## Lifecycle

`evaluate_setup_experiment` drives, via Phase-2 validated + append-only transitions:

```
APPLIED → TEST_IN_PROGRESS → READY_FOR_REVIEW → COMPLETED | REJECTED
```

`CONFIRMED_IMPROVEMENT` / `PARTIAL_IMPROVEMENT` / `NO_MEANINGFUL_CHANGE` may
COMPLETE (policy `complete_on_success`); `REGRESSION` → REJECTED; **CONFOUNDED and
INSUFFICIENT_EVIDENCE stay in READY_FOR_REVIEW** (reviewable, never falsely
completed or rejected). Transition validation is never bypassed; no auto-apply or
rollback.

## Feeding the existing consumers

On a LOCKOUT-strength confirmed regression the orchestrator writes a `worsened`
`learning_outcomes` row (consumed by `blocked_rules_from_outcomes`) and stamps the
latest lineage node `worsened` (consumed by `rollback_from_lineage`) — so Phase 3
learning flows into the EXISTING recommendation-time lockout/rollback path, not a
new engine. A CAUTION writes neither (the `setup_experiment_failed_directions` row
is the caution record). Insufficient/confounded write nothing. A later stronger
successful result can supersede a prior outcome (audited `superseded_by`), and a
later `improved` learning outcome lifts a rule block via the existing consumer —
history is never deleted.

## Production integration

- **Orchestrator:** `SessionDB.evaluate_setup_experiment(...)` — gathers clean-lap
  windows from the DB (OFR-1 authority), resolves association, evaluates, persists
  the immutable outcome atomically, attaches TEST/DRIVER_REVIEW/OUTCOME evidence to
  the Phase-2 ledger, drives the lifecycle, and feeds the existing consumers.
- **Driver-triggered UI action:** the Setup Builder form gains a **"Review Test
  Outcome"** button (`ui/setup_form_widget.py`), revealed once an applied experiment
  exists. Its handler (`ui/setup_builder_ui.py::_review_experiment_outcome`) runs
  the evaluation on a **worker thread** (never the telemetry UDP thread) and renders
  a compact summary — status, confidence, valid laps, regressions/improvements,
  next action, and whether a caution/lockout was recorded — via an off-thread queue
  drained in `dashboard.py::_poll_ui_queue`. Read-only: it never applies or reverts.

## Known limitations

- The live UI review path gathers whole-lap windows from the DB but does not yet
  auto-assemble per-corner baseline/test observations from live telemetry (run→
  corner mapping) — without them a live review is honestly INSUFFICIENT/NO_MEANINGFUL.
  The engine fully supports per-corner evidence (proven by tests + the golden UAT);
  wiring the live per-corner assembly + a single canonical clean-lap authority is
  exactly **Phase 4** (Canonical Evidence Authorities & Unified Clean-Lap /
  Setup-Decision Semantics).
- Driver-review structured parsing consumes the existing deterministic feedback
  fields; richer symptom-rating capture is a later concern.

## Golden UAT (Porsche 911 RSR '17 @ Fuji Full Course)

`tests/test_setup_outcome_golden_uat.py`:
1. Repeatable T1 front lockup → controlled brake-bias change → applied checkpoint
   MATCH → 5 valid laps → T1 lockup drops 5/5 → 1/5 repeatably, mid-corner + rear
   traction preserved, median lap not regressed, driver confirms → **CONFIRMED_IMPROVEMENT**
   → **COMPLETED**, **no lockout**.
2. Target improves slightly but rear-exit wheelspin becomes recurring (protected
   rear traction) → **REGRESSION** → **REJECTED**, a scoped **LOCKOUT** learning
   record is created, parent remains the rollback target, **no automatic rollback**.

## Phase 4 prerequisites

Phase 4 will unify the clean-lap definition and per-corner evidence into canonical
authorities and wire live per-corner assembly into the review path. All Phase 3
hooks (validity gate, per-corner comparison, evidence phases, outcome immutability,
failed-direction scoping) already exist and are stable.
