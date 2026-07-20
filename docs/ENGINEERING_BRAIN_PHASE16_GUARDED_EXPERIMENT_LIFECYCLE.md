# Engineering Brain — Program 2, Phase 16: Guarded Experiment Lifecycle & Postflight Loop Closure

**Status:** implemented on branch `eng-brain-phase16-guarded-experiment-lifecycle` (from `1f90367`, the Phase-15 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the deterministic, READ-ONLY orchestration layer that CLOSES the Engineering-Brain loop by *connecting existing authorities*. It creates no new experiment system, Apply path, outcome recorder or reconciler. It converts a READY Phase-15 bounded experiment into a canonical `SetupExperiment` request (via the existing `build_experiment_from_recommendation`), routes it through the existing Phase-10 preflight, and — for an already-executed experiment — assembles a read-only closed-loop summary from the existing Phase-3 outcome, Phase-11 reconciliation and prediction-calibration records.

It NEVER: applies a setup, bypasses the frozen Apply gate, persists/duplicates an experiment, creates an outcome or reconciliation, invents driver feedback, simulates results, or mutates any diagnosis / mechanism / hypothesis / setup-history / active-setup / calibration. The only mutation route to the car remains the frozen Apply gate; the only experiment-persistence route remains the existing explicit `create_setup_experiment` workflow. No AI/network.

## 1. Mission — the loop is now closed
```
Evidence → Diagnosis → Physics → Mechanism (P13) → Hypothesis (P14) → Smallest legal experiment (P15)
  → Canonical SetupExperiment → Phase-10 Preflight → frozen Apply gate → driver test
  → Phase-3 Outcome → Phase-11 Reconciliation → Prediction Calibration   ← Phase 16 connects these
```
Phase 16 introduces no duplicate workflow — it is the thin, deterministic wiring that makes the Engineering Brain a complete closed-loop engineering process.

## 2. Authority hierarchy & ownership (all reused, none recreated)
`SetupExperiment` + `build_experiment_from_recommendation` (canonical experiment), `create_setup_experiment` (persistence), the frozen **Apply gate** (`APPROVED_STATUSES` + `applied_checkpoint.compute_apply_status`), Phase-10 `SessionDB.build_experiment_preflight`, Phase-3 `setup_experiment_outcome` (+ `get_latest_experiment_outcome`), Phase-11 `record_experiment_reconciliation`/`get_reconciliation_records`/`build_prediction_calibration`, the working-window authority, `SessionDB` experiment history (`get_setup_experiment`), the canonical applied setup (`setup_state_authority`), and Phase-15 `BoundedSetupExperiment` (+ `build_bounded_setup_experiments`). Phase 16 owns **only** the orchestration wiring.

## 3. Orchestration responsibilities
1. **Forward path** (`build_execution_request` → `assemble_execution_result`): map a READY Phase-15 candidate to the canonical experiment + Phase-10 preflight `selection`, run the existing preflight (read-only), and route to a lifecycle state.
2. **Closed loop** (`assemble_lifecycle_summary`): read the existing experiment status + Phase-3 outcome + Phase-11 reconciliation + calibration and assemble the full, traceable summary.
Nothing is lost between stages; nothing is created.

## 4. Domain model (`strategy/experiment_lifecycle.py`, pure)
- **`ExperimentLifecycleState`** — `NOT_ACTIONABLE`, `EXPERIMENT_BUILT`, `PREFLIGHT_FAILED`, `READY_FOR_MANUAL_APPLY`, `AWAITING_APPLY`, `APPLIED`, `TEST_IN_PROGRESS`, `READY_FOR_REVIEW`, `OUTCOME_RECORDED`, `RECONCILED`, `CALIBRATED`, `COMPLETED`, `REJECTED`, `REVERTED`, `BLOCKED`, `UNKNOWN`.
- **`LifecycleTrace`** — the unbroken provenance chain (diagnosis_key → mechanism_ids → hypothesis_ids → hypothesis_set_fingerprint → synthesis_candidate_id/fingerprint → baseline_setup_hash → experiment_id/idempotency_key → outcome_id → prediction_fingerprint → reconciliation_record_key) with `is_unbroken_to(stage)`.
- **`ExperimentExecutionRequest`** — the canonical experiment to create through the existing workflow (recommendation data + `SetupExperiment.to_dict()` unpersisted + Phase-10 selection + trace). It is a request, not a mutation.
- **`ExperimentExecutionResult`** — request + preflight review + lifecycle state + next action + trace + fingerprint.
- **`ExperimentLifecycleSummary`** — the full closed-loop view (diagnosis/mechanism/hypothesis/synthesis/experiment/preflight/apply/outcome/reconciliation/calibration + per-stage states + trace + fingerprint).
These are orchestration objects only — the canonical experiment remains the real `SetupExperiment` (`schema setup_experiment_v1`).

## 5. Lifecycle routing
- Non-READY / no-delta candidate → `NOT_ACTIONABLE` (no experiment).
- READY candidate → canonical `SetupExperiment` (status `draft`) built via `build_experiment_from_recommendation` with `recommendation_status="approved"` (honest: a bounded change that passed every synthesis gate, framed as a TEST).
- Preflight build ok → `READY_FOR_MANUAL_APPLY` (next action: review, then create + apply through the existing workflow + frozen Apply gate — manual). Preflight build fails (`ok=false`/None) → `PREFLIGHT_FAILED`.
- Persisted experiment status → mapped state (`applied`/`test_in_progress`/`ready_for_review`/`completed`/…).
- Outcome present → `OUTCOME_RECORDED`; reconciliation present → `RECONCILED`; calibration reflects it → `CALIBRATED`.

## 6. Traceability
Every stage preserves links back through diagnosis → mechanism → hypothesis → synthesis → experiment → outcome → reconciliation → prediction. `LifecycleTrace.is_unbroken_to(stage)` is a deterministic completeness check; `_with(...)` never blanks an existing link (monotonic accumulation). The Phase-15 synthesis fingerprint survives verbatim into the lifecycle trace.

## 7. Runtime integration (read-only)
- `SessionDB.build_experiment_execution(candidate, ...)` — one candidate → canonical request → **existing** Phase-10 preflight → `ExperimentExecutionResult`. Read-only: builds + validates only; writes nothing; applies nothing.
- `SessionDB.build_engineering_lifecycle(**ctx, applied_setup=..., session_identity=...)` — the aggregate overview: reuses the Phase-15 `build_bounded_setup_experiments` aggregate **once** plus `build_prediction_calibration` + `get_reconciliation_records`, and assembles one `ExperimentLifecycleSummary` per diagnosis (forward chain + aggregate closed-loop). No per-diagnosis DB scan; query count is constant regardless of diagnosis count; the empty path is cheap; the renderer touches no DB.

## 8. UI integration
`EngineeringLifecyclePanel` (+ pure `ui/engineering_lifecycle_vm.py`, renderer `strategy/experiment_lifecycle_render.py`) embedded in the **Development History** page beneath the Phase-15 panel. It shows, per diagnosis, the ordered loop stages (diagnosis → mechanism → hypothesis → bounded experiment → canonical experiment → preflight → awaiting manual Apply → outcome → reconciliation → prediction calibration) with per-stage state and full traceability. **No Apply / Approve / Revert control and no editing** — the frozen Apply gate remains the only route to the car. The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`.

## 9. Determinism & persistence
Identical inputs → identical lifecycle state, traceability, ordering, rendered output, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses in fingerprints. Nothing is persisted (the summary is a pure function of existing records); `DB_VERSION` stays **25**.

## 10. Safety guarantees (proven)
No duplicate Apply / Experiment / Outcome / Reconciliation / Prediction-Calibration; no automatic setup changes; no DB writes except through the existing lifecycle (the runtime path writes nothing — `setup_experiments` and `engineering_reconciliation_records` counts are unchanged after a build); no shadow experiment model (the canonical experiment stays `setup_experiment_v1`); pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 25 are unchanged; protected runtime files byte-identical.

## 11. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase16_lifecycle_domain.py` | 15 | creation, traceability, preflight/apply/outcome/reconciliation/prediction routing, determinism, rendering |
| `tests/test_phase16_golden.py` | 4 | real SessionDB production path (aggregate + single-candidate execution through the real Phase-10 preflight) + restart |
| `tests/test_phase16_safety.py` | 8 | no duplicate lifecycle/apply/recording, connects-existing-only, no shadow model, read-only, versions |
| `tests/test_phase16_query_shape.py` | 3 | aggregate reuse, no N+1, cheap empty, renderer-no-DB |
| `tests/test_phase16_ui_construction.py` | 5 | panel/page, no Apply/edit controls, off-thread |

All 35 pass; Phase 12–15 (341), frozen/no-AI/config/fan-out/session_db (80), experiment/outcome/preflight/postflight/reconciliation (285), broad non-UI regression (2000) stay green.

## 12. Known limitations
- `build_experiment_execution` builds and validates the canonical experiment but does not persist it — persistence + Apply remain the existing explicit workflow + frozen Apply gate (by design).
- The aggregate `build_engineering_lifecycle` shows the closed-loop side (outcome/reconciliation/calibration) at the context (aggregate) level because synthesised candidates are not yet executed; the per-experiment `assemble_lifecycle_summary` gives the exact closed loop for an executed experiment id.
- Preflight is advisory and never blocks (Phase-10 doctrine); `PREFLIGHT_FAILED` means the preflight *build* failed, not a veto.

## 13. Manual UAT
Porsche 911 RSR '17 @ Fuji: apply a complete setup; create a recurring entry-understeer diagnosis; open the Development History page; confirm the Phase-16 Engineering Lifecycle panel shows the chain diagnosis → mechanism → hypothesis → bounded experiment → (canonical experiment / preflight ready) → awaiting manual Apply, with full traceability and no Apply/edit control; create + apply the experiment through the existing workflow and frozen Apply gate; drive the test laps; review the outcome; confirm the panel now shows outcome → reconciliation → calibration and the trace is unbroken; restart and confirm identical output + fingerprint; confirm no protected runtime file and no DB row changed merely from viewing.

## 14. Deferred work / recommended Phase 17
**Phase 17 — Autonomous Development Cadence & Regression Guard:** with the loop closed, sequence multiple diagnoses into a deterministic development programme (one experiment at a time, respecting working-window locks, failed-direction lockouts and protected-good), auto-detect when a prior gain regresses across sessions, and surface a prioritised, evidence-gated next-experiment queue — still through every existing gate and manual Apply. Not started.
