# Engineering Brain — Phase 11: Post-Flight Engineering Reconciliation & Prediction Calibration

**Status:** implemented on branch `eng-brain-phase11-postflight-reconciliation` (from `master` @ Phase 10 `fa9d1f4`).
**Schema:** **additive migration to v25** — `DB_VERSION` 24 → **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** a READ-ONLY OBSERVER above Phases 1–10. After a completed experiment it
deterministically compares what the Engineering Brain PREDICTED (the Phase-10 pre-flight
review) against what ACTUALLY occurred (the Phase-3 outcome + Phase-6 residual state). It
never changes experiments, outcomes, memory, working windows or setup values — it only
compares expectation with reality. No AI, no prediction, no learning, no statistics.

## 1. Problem solved

Phase 10 tells the driver what to expect before an experiment. Phase 11 answers, after it
runs, *"how accurate was our engineering expectation?"* — reconciling every predicted
consequence and checklist item against the observed reality, computing deterministic
accuracy metrics, and appending an immutable calibration record.

## 2. Starting checkpoint

`eng-brain-phase11-postflight-reconciliation` from `master` @ Phase 10 `fa9d1f4` (Phases
2–10 stacked; master at Phase 1). Golden `config_id`, frozen fan-out allowlist, Apply-gate
predicate and engine-wiring-status all unchanged.

## 3. Existing authorities reused (no duplication)

| Concern | Reused authority |
|---|---|
| The prediction | Phase 10 `build_experiment_preflight` review (consequences + checklist + risk) |
| The actual outcome | Phase 3 `setup_experiment_outcomes` (status + protected verdicts) |
| The residual state | Phase 6 `residual_issues_from_outcome` |
| The memory context | Phase 8 `MemoryContextKey` (via `_memory_context_for_experiment`) |

Nothing else is consumed. Phase 11 re-evaluates no lap and re-derives no outcome.

## 4. New modules (all pure: Qt-free, DB-free, UI-free, network-free, AI-free, never raise, no clock/random)

- **`strategy/postflight_reconciliation.py`** — `reconcile_consequences(preflight, outcome,
  residuals)` classifies every predicted consequence as CONFIRMED / PARTIALLY_CONFIRMED /
  NOT_OBSERVED / CONTRADICTED / INSUFFICIENT_EVIDENCE / UNKNOWN. `ReconciliationRecord` +
  `build_reconciliation_record` assemble the immutable calibration record (idempotent
  `record_key`, time-independent `content_fingerprint`).
- **`strategy/preflight_validation.py`** — `validate_checklist(preflight, outcome, residuals)`
  evaluates every checklist item: did the expected risk appear, did the protected behaviour
  remain protected, did the interaction occur, did the regression happen, was the confidence
  appropriate? → `ChecklistValidation` (MATERIALISED / DID_NOT_MATERIALISE / INSUFFICIENT /
  N/A + a `useful` flag).
- **`strategy/prediction_accuracy.py`** — `compute_accuracy(consequences, checklist)` →
  `PredictionAccuracy`: primary-consequence, side-effect, risk, constraint, historical-transfer
  and checklist accuracies + overall, with confirmed/contradicted counts. Plain deterministic
  ratios — no statistics.

## 5. Reconciliation model

Each predicted consequence is matched to an observable in the outcome/residuals:
- **Primary effect** ← the target issue's residual state (resolved → CONFIRMED, improved-but-present
  → PARTIALLY, unchanged → NOT_OBSERVED, worsened → CONTRADICTED), falling back to the overall
  outcome status.
- **Side effect** ← whether a matching regression family appeared (keyword→family map).
- **Historical** ← whether history repeated (improved → CONFIRMED, regressed → CONTRADICTED).
- **Working window** ← whether a regression violated the window.
- **Interaction** ← whether a coupled-family issue appeared (else INSUFFICIENT/NOT_OBSERVED).

## 6. Prediction validation (checklist)

Every Phase-10 checklist item is checked against reality: protected-conflict warnings vs
actual protected verdicts, window warnings vs actual regressions, "similar succeeded/failed"
vs the outcome, regression-risk warnings vs whether the regression happened, coupled-interaction
warnings vs observed coupled effects, and outstanding-residual notes vs the residual state.
Each carries whether it MATERIALISED and whether it was USEFUL (correctly anticipated reality).

## 7. Calibration records (DB v25 — additive, append-only, immutable)

`_migrate_v25` adds ONE standalone table `engineering_reconciliation_records` (CREATE IF NOT
EXISTS ⇒ idempotent). One immutable row per completed experiment reconciliation: the
prediction fingerprint, the outcome status, the accuracy, and the full reconciliation JSON,
keyed by a UNIQUE `record_key`. `INSERT OR IGNORE`; never UPDATE/DELETE.

**Why a migration (unlike Phases 9/10, which were regenerable):** the prediction is a
point-in-time input made BEFORE the experiment; after the outcome exists the memory has
changed, so the prediction is not reliably regenerable. The immutable calibration log must
persist to accumulate cross-experiment.

## 8. Orchestrator (SessionDB, read-only)

`record_experiment_reconciliation(experiment_id, preflight_review, …)` — fetches the completed
Phase-3 outcome + Phase-6 residuals, builds the reconciliation record, and persists it
(append-only, idempotent). `get_reconciliation_records(…)` + `build_prediction_calibration(…)`
aggregate the immutable records into a deterministic calibration summary (mean accuracies +
confirmed/contradicted counts + elevated-risk regressions). All read-only; write only the
append-only log.

## 9. UI — the Post-Flight Review panel

- `ui/postflight_review_vm.py` — pure Qt-free view-model (prediction vs observed, confirmed
  expectations, unexpected behaviour, per-category accuracy, checklist validation, lessons,
  calibration summary).
- `ui/postflight_review_panel.py` — `PostFlightReviewPanel`, a self-contained read-only panel
  with **no Apply controls** (asserted).
- Surfaced in the existing **Development History** page: the panel shows the aggregate
  prediction calibration for the current context (populated read-only from
  `build_prediction_calibration`). No new tab, no registry change.

## 10. Determinism & purity verification

- All 3 core modules verified free of random/wall-clock/sqlite/Qt/network.
- Reconciliation record `record_key` + `content_fingerprint` are time-independent
  (`test_record_time_independent_and_idempotent`).
- Calibration fold is restart-deterministic (`test_calibration_fold_and_restart_determinism`).
- Inputs are never mutated (`test_inputs_not_mutated`).

## 11. Schema / contract changes

`_migrate_v25` + `_DDL_V25` (one additive table). `DB_VERSION` 24 → 25. `RULE_ENGINE_VERSION`
`46.0`. Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status untouched. Version guards advanced (group55–61 → guard v26;
session_db/phase8-9-10 persistence tests track `DB_VERSION`).

## 12. Tests

`tests/test_phase11_{reconciliation,validation,persistence,orchestrator,view_model}.py`
(36 non-UI) + `tests/test_phase11_ui_construction.py` (3 UI — run individually). Golden UAT
drives the real `review_and_learn` loop (Porsche RSR @ Fuji), builds the Phase-10 pre-flight
for the same experiment, then reconciles prediction vs actual and asserts the primary
consequence was confirmed and the calibration record persisted.

## 13. Known limitations / deferred

- The reconciler receives the Phase-10 pre-flight as an input (the caller captures it at
  proposal time); an automatic capture-at-apply-time hook that stores the prediction so
  reconciliation is fully hands-free is deferred.
- Side-effect and interaction reconciliation use a deterministic keyword→family map; a
  physics-precise axis→symptom model is deferred.
- The Development History page shows the aggregate calibration; a per-experiment post-flight
  view wired into the Setup Builder outcome flow is deferred.

## 14. Recommended Phase 12

**Calibration-informed confidence** — deterministically fold the accumulated calibration
(how accurate each prediction category has been for a context) into the Phase-10 pre-flight's
confidence labelling, so repeatedly-accurate predictions read as more trustworthy and
repeatedly-wrong ones are flagged — still a pure observer, still never changing the
recommendation or any authority.
