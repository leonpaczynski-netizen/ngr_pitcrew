# Engineering Brain — Program 2, Phase 13: Mechanism-Annotated Diagnosis

**Status:** implemented on branch `eng-brain-phase13-mechanism-annotated-diagnosis` (from `6010d5b`, the Phase-12 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the strict bridge between **Program 1** ("what happened?") and **Program 2 / Phase 12** ("why could it have happened?"). For an already-decided canonical Program-1 diagnosis it produces an auditable, evidence-linked explanation of the vehicle-dynamics **mechanisms** behind it, by querying the Phase-12 knowledge authority. It preserves the canonical diagnosis unchanged and decides nothing.

It NEVER decides whether an observation occurred, a lap is valid, an issue recurs, an experiment improved the car, a change is safe, or which experiment is selected; it authors no setup value, delta, Apply or Revert; it mutates no outcome, working window, lockout or prediction calibration; and it duplicates neither the Phase-12 knowledge nor the Program-1 directional sign graph (it consumes both). No ML, no statistics, no NLP, no black-box scoring, no network, no AI.

## 1. Problem solved
A canonical Program-1 diagnosis states *what* recurred (e.g. "rear wheelspin at T4 exit on 4/5 valid laps"). Phase 13 attaches *why*: the physically-supported mechanism(s), the load-transfer mode, the relevant component interactions, the competing explanations that the evidence cannot separate, the GT7 channels that make it uncertain, and the controlled evidence that would distinguish the mechanisms — without becoming a second recommendation engine and without bypassing any canonical decision.

## 2. Starting checkpoint
Branch `eng-brain-phase13-mechanism-annotated-diagnosis` created from `6010d5b` (Phase-12 tip; Program-1 Phases 1–11 + Program-2 Phase 12 present). Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and engine-wiring-status verified unchanged. `DB_VERSION = 25`, `RULE_ENGINE_VERSION = "46.0"`.

## 3. Program 1 authorities reused (subordinate to, never replaced)
| Concern | Reused authority (value-strings consumed) |
|---|---|
| Canonical issue identity + residual taxonomy | `engineering_issue.IssueFamily` / `issue_family_for` / `ResidualState` |
| Per-corner phase / evidence + forbidden channels | `corner_evidence.CornerPhase` / `_FABRICATED_METRIC_KEYS` |
| Lap validity | `engineering_lap_validity.LapValidityStatus` |
| Experiment outcome status | `setup_experiment_outcome.OutcomeStatus` |
| Canonical decision status | `setup_decision_status.SetupDecisionState` (INVALID/INCONCLUSIVE gate) |
| Working window / failed direction | `working_window.LearnedWorkingWindow.locked_directions()` / protected knowledge |
| Post-flight reconciliation | `postflight_reconciliation.ReconciliationStatus` |
| Prediction accuracy | `prediction_accuracy.PredictionAccuracy` (read-only reference) |
| Cross-session memory | `SessionDB.build_cross_session_memory` (issues, protected knowledge, protected behaviours) |
| Prediction calibration | `SessionDB.build_prediction_calibration` (reconciliation records) |
| Directional sign graph | `setup_synthesis.PARAMETER_INTERACTIONS` (consumed, fingerprinted; never redefined) |

## 4. Phase 12 knowledge authorities reused (composed, never copied)
`vehicle_dynamics.explain_component` / `Component` / `ComponentGroup`; `load_transfer.explain_transfer` / `TransferMode` (7 modes); `handling_balance.explain_phase` / `HandlingPhase` (8 phases); `setup_interactions.explain_interaction` / `interactions_for` / `InteractionType` / `lsd_model` / `aero_model`. Every mechanism sentence is pulled at annotation time from these — Phase 13 stores no mechanism prose of its own.

## 5. Separation of observation, mechanism and intervention
- **Observation** (Program 1) — whether/where/how-often it happened, validity, recurrence, outcome. Phase 13 never alters it.
- **Mechanism** (Phase 13, from Phase 12) — the physics interpretation, explicitly flagged `physics_informed`, never presented as raw telemetry.
- **Intervention** (existing authoring/selection authorities) — Phase 13 identifies which component families are physically relevant but authors no value, delta, Apply or Revert.

## 6. Mechanism annotation domain (`strategy/mechanism_annotation.py`)
Immutable, frozen dataclasses with `to_dict()`:
- **`MechanismStatus`** — `SUPPORTED`, `SUPPORTED_WITH_LIMITATIONS`, `PLAUSIBLE`, `COMPETING`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`, `NOT_EVALUABLE`, `OUT_OF_SCOPE`, `INVALID_SOURCE_DIAGNOSIS` (never collapsed to one %).
- **`ConclusionKind`** — `DIRECT_OBSERVATION` / `PHYSICS_INFORMED` / `PROVISIONAL`; **`EvidenceGrade`** — `STRONG/MODERATE/WEAK/INSUFFICIENT`; **`EvidenceRelation`** — `SUPPORTS/CONTRADICTS/NEUTRAL`.
- **`MechanismEvidenceLink`** — traceable evidence (source_type, session/run/checkpoint/experiment/outcome/lap/segment ids, phase, axle, validity/recurrence state, feedback/prediction id, exclusion reason, context fingerprint) with a relation + conclusion kind. Only fields the source exposes are populated (no fabricated ids).
- **`CausalMechanismCandidate`** — stable id, name, Phase-12 refs, phase, transfer mode, primary + secondary components, interactions, primary physical cause + secondary effects (pulled from Phase 12), GT7 limitations, supporting/contradicting evidence, missing discriminators, status, grade, conclusion kind, scope/setup compatibility, experiment/prediction relationship, outcome consistency, intervention field + `intervention_direction_contradicted`, reasoning, knowledge ref, deterministic sort key.
- **`MechanismComparison`** — pairwise; keeps two mechanisms `indistinguishable` when GT7 cannot separate them (`gt7_can_distinguish=false`), with the required controlled observation.
- **`MechanismAnnotatedDiagnosis`** — the canonical result: `source_diagnosis` retained **unchanged**, context, canonical issue, corners/phases/axles, primary/secondary/competing/contradicted mechanisms, comparisons, interactions, load-transfer explanation, GT7 limitations, evidence gaps, required discriminating evidence, protected-good behaviours, outcome consistency, prediction relationship, overall status, audit trail, `content_fingerprint`, `knowledge_versions`, `schema_version`.

## 7. Eligibility gates (`_eligibility`, run before any grading)
Blocks (and still explains why) when: canonical decision is `INVALID`; source comparison is `invalid_comparison`; diagnosis superseded / stale-checkpoint / checkpoint-ambiguous → `INVALID_SOURCE_DIAGNOSIS`. Family `unknown`/`consistency` → `OUT_OF_SCOPE`. No structural mechanism map / unresolved handling phase (too broad, e.g. generic "understeer" with no phase) → `NOT_EVALUABLE`. Residual `insufficient_evidence`/`not_observed`/`ambiguous`, evidence only from invalid laps, or below recurrence → `INSUFFICIENT_EVIDENCE`. No amount of weak evidence overrides a hard gate.

## 8. Diagnosis→mechanism mapping (`strategy/mechanism_map.py`)
A fixed, auditable table of `MechanismTemplate`s keyed by the canonical `issue_type`, each pointing only at Phase-12 concepts (Component / HandlingPhase / TransferMode / interaction pairs) plus a `role_hint`, `intervention_field`, `requires_speed_context` and `is_driver_technique` flag. Matching is structural (issue family / type / axle / phase), never free-text. `resolve_handling_phase` maps Program-1 phase strings and issue-type-implied phases to Phase-12 `HandlingPhase`, lifting to `HIGH_SPEED_STABILITY` only with genuine high-speed context. Covers every required category: braking lockup, rear braking instability, entry/mid/exit understeer & oversteer, wheelspin, poor drive-out, wrong-gear/gearing, kerb, bottoming, high-speed aero, tyre degradation, fuel — using existing canonical issue types only.

## 9. Load-transfer annotation
The driving mechanism's Phase-12 `TransferMode` is explained via `explain_transfer` (mechanism, balance effect, GT7 note) plus a direction sentence (which axle gains/loses). **No numeric loads** — the note states GT7 exposes no individual tyre load, so direction only.

## 10. Component-interaction annotation
Constrained to the primary component's interactions **with the diagnosis-relevant secondaries** (via `interactions_for` + the template's explicit pairs) — never a flat graph dump. Each is labelled amplifies / trades-against / enables-gates / caps-masks from `InteractionType`, with mechanism + GT7 note.

## 11. LSD treatment
A wheelspin diagnosis is **never** auto-explained as insufficient/excessive LSD locking. The primary mechanism is driven-wheel **traction demand** (`TRANSMISSION`); differential locking, gear selection, rear-load/platform and tyre condition remain **competing**. A prior LSD-accel increase that failed appears as a Program-1 failed-direction lockout → the LSD candidate's intervention is flagged `intervention_direction_contradicted` (kept as a possible mechanism, never a cure), and Phase 13 proposes no LSD change.

## 12. Aero treatment
Aero candidates require genuine high-speed evidence; without it they stay `PLAUSIBLE` and cannot become primary. Mechanical/platform mechanisms remain visible; the missing speed-dependent discriminator is listed; no downforce/CoP values are fabricated.

## 13. Spring/damper/ARB/platform treatment
No "stiffer front → understeer" shortcuts. Kerb/bump is a transient platform mechanism; damper velocity and suspension travel are declared unavailable, so over-stiff damping is never asserted as proven.

## 14. Gear & drive-out treatment
Gear/torque mechanisms use `TRANSMISSION` with engine-torque and shift-RPM declared unavailable (never fabricated). Poor drive-out keeps competing causes — wrong gear (primary when mapped), wheelspin, differential interaction, excess understeer, and delayed/abrupt throttle (driver technique, `PLAUSIBLE`, never a setup mechanism).

## 15–18. Primary / secondary / competing / contradicted selection
A single `SUPPORTED` primary survives only when a `role_hint=primary`, phase-and-axle-compatible, non-speed-gated, non-technique candidate strictly out-ranks all other primaries on `(role, phase-match, axle-match, grade)`; ties demote to `COMPETING` (no auto-winner). Secondary = other supported. Competing/plausible retained with comparisons. Contradicted = mechanisms whose **prediction** was contradicted post-flight. A confirmed outcome never by itself proves a mechanism; a regression disproves the intervention direction, not necessarily the physical mechanism.

## 19. GT7 observability
Per issue family, the annotation names the unavailable channels (individual tyre load, differential lock state, damper velocity, suspension travel, aero load, engine torque, tyre temperature/wear) — aligned with Program-1's `_FABRICATED_METRIC_KEYS`. None is ever treated as observed.

## 20. Experiment-outcome & 21. prediction-calibration relationship
Single-field vs multi-field (attribution unsafe) is distinguished; outcome consistency notes improvement/regression honestly. The prediction relationship references the Phase-11 reconciliation primary-effect status (`supported`/`partially_supported`/`contradicted`/…) and accuracy, with an explicit "prediction calibration is owned by Phase 11 and is read-only here" note — Phase 13 mutates no calibration.

## 22. Confidence & evidence grading
Deterministic `EvidenceGrade` from residual severity, recurrence, valid-lap count, sessions, corner/phase/axle specificity, driver-feedback agreement, telemetry support, outcome consistency, reconciliation presence, minus GT7-limitation and contradiction penalties. Hard eligibility gates run first.

## 23. Runtime integration
`SessionDB.build_mechanism_annotations(**ctx)` (read-only) composes `build_cross_session_memory` + `build_prediction_calibration` and calls the pure `annotations_from_memory` — each cross-session `IssueMemory` is one canonical diagnosis; failed directions come from protected knowledge, prediction relationship from the reconciliation records. Regenerable, restart-identical; writes nothing; DB stays v25.

## 24. UI integration
A read-only `MechanismAnnotationPanel` (pure `ui/mechanism_annotation_vm.py`, renderer `strategy/mechanism_annotation_render.py`) embedded in the **Development History** page (alongside Phases 9/11/12). Structured cards per diagnosis with separated sections: What the app observed / Most-supported mechanism / Load transfer / Secondary interactions / Competing mechanisms / GT7 limitations / Experiment & prediction relationship / Evidence needed. **No Apply / Revert / setup controls.**

## 25. Persistence decision — NONE (proof)
Annotations regenerate deterministically from: canonical diagnoses (immutable Phase-8 development records folded into cross-session memory), Phase-11 reconciliation records, the static Phase-12 knowledge, and the sign-graph fingerprint. Same inputs → byte-identical `content_fingerprint` across restart (test `test_scenario_L_db_production_path_and_restart_determinism`). No audit information is created that isn't already durable in the source records. Therefore **no migration**; `DB_VERSION` stays **25**.

## 26. Threading
`SessionDB.build_mechanism_annotations` runs OFF the Qt thread via `MechanismAnnotationWorker(QThread)` (mirrors `TrackModelBuildWorker`); the finished immutable dict is delivered to the panel on the UI thread. The panel performs no annotation work — it renders a pre-built dict. Verified: build runs on a non-main thread; the signal handler runs on the main thread.

## 27. Determinism & 28. safety guarantees
Pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free (timestamps are data). It defines no sign graph or dynamics registry, invents no GT7 channel, owns no Apply/Revert/authoring, and leaves every Program-1 and Phase-12 authority canonical.

## 29. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase13_mechanism_map.py` | 26 | knowledge consumption, required categories, phase resolution, no-duplicate-knowledge |
| `tests/test_phase13_mechanism_annotation.py` | 29 | eligibility, support/contradiction, interactions, load transfer, experiment & prediction relationship, rendering |
| `tests/test_phase13_golden_uat.py` | 12 | Scenarios A–L incl. real SessionDB production path + restart determinism |
| `tests/test_phase13_properties.py` | 19 | the 25 metamorphic invariants + no-migration |
| `tests/test_phase13_safety.py` | 11 | no-AI / no-Qt-in-domain / no-DB-in-domain / no-sign-dup / no-invented-channel |
| `tests/test_phase13_ui_construction.py` | 6 | panel/page construction, no Apply/Revert, off-thread worker |

All 103 (118 with parametrisation) pass; Phase 8–12 (370) and the broad strategy regression (734) stay green.

## 30. Known limitations
- The aggregate integration annotates cross-session `IssueMemory` diagnoses; per-experiment `valid_laps` is proxied by `times_observed` (memory does not carry a lap count).
- Speed context and driver-feedback agreement are consumed when supplied but are not yet auto-derived from telemetry in the aggregate builder.
- Mechanism comparisons are capped at a deterministic 12-pair prefix for display.

## 31. Deferred work
- Per-experiment (single-diagnosis) surfaces in Setup Diagnosis Review / Experiment Outcome Review (this phase integrates only the Development History aggregate).
- Auto-derived speed context per corner from live/reference telemetry.

## 32. Manual UAT
See §27 of the task brief — Porsche 911 RSR '17 @ Fuji: drive valid laps to create a recurring issue, open the canonical diagnosis (unchanged), open the mechanism explanation, confirm separated observation vs interpretation, correct phase/load-transfer/interactions, explicit GT7 limits, no setup value, no Apply control; run one controlled experiment, confirm outcome relationship shown, improvement not treated as proof, failed LSD direction visible, prediction reconciliation shown; restart and confirm identical annotation + fingerprint; confirm no protected runtime file changed and no working-window/outcome/prediction record changed from viewing.

## 33. Recommended Phase 14
**Mechanism-Constrained Intervention Hypotheses** — use this annotation to constrain which setup subsystems are physically eligible for a controlled experiment, still passing through Program-1 evidence gates, working windows, failed-direction lockouts, protected-good behaviour, minimum-effective intervention, pre-flight prediction, manual Apply and post-flight reconciliation. Not started.
