# Engineering Brain — Program 2, Phase 14: Mechanism-Constrained Intervention Hypotheses

**Status:** implemented on branch `eng-brain-phase14-mechanism-constrained-interventions` (from `f3d4e90`, the Phase-13 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** a deterministic, READ-ONLY reasoning layer that converts a valid Phase-13 `MechanismAnnotatedDiagnosis` into structured **intervention hypotheses** — scientifically-defensible controlled-test *directions* constrained by the supported physical mechanism. A hypothesis is NOT a setup recommendation and NOT an authored setup change.

It answers *"given what we currently believe is happening physically, what controlled intervention directions are defensible to test next?"* — never *"set this value to X."* It authors no numeric setup value, applies/approves/persists nothing, and mutates no diagnosis / outcome / working window / calibration / setup history / active setup. It duplicates neither the Phase-12 knowledge, the Phase-13 mechanism model, nor the Program-1 sign graph — it consumes all three. No ML/statistics/NLP/black-box/AI/network.

## 1. Objective
Between mechanism explanation (Phase 13) and setup synthesis, produce for each supported/competing mechanism a bounded, evidence-gated controlled-test direction with expected response, trade-offs, protected-good protection, required evidence, test design, rejection criteria and an explicit status.

## 2. Architecture & authority hierarchy
Canonical telemetry/driver evidence → validity/recurrence gates → canonical diagnosis → mechanism annotation (Phase 13) → **mechanism-constrained intervention hypotheses (Phase 14)** → existing deterministic setup synthesis & rule authority → Apply gate → manual user action. Phase 14 sits at level 5: it may inform later selection but replaces/overrides/mutates nothing above or below it.

## 3. Domain model (`strategy/intervention_hypothesis.py`, pure)
- **`InterventionHypothesisStatus`** — `TESTABLE`, `CONDITIONAL`, `INSUFFICIENT_EVIDENCE`, `COMPETING_MECHANISMS`, `CONTRADICTED_BY_OUTCOME`, `BLOCKED_BY_WORKING_WINDOW`, `BLOCKED_BY_SAFETY_OR_VALIDITY`, `NOT_EVALUABLE`, `OUT_OF_SCOPE`.
- **`InterventionDirection`** — qualitative only: increase/decrease/stiffen/soften/raise/lower/move_forward/move_rearward/shorten/lengthen/increase_locking/decrease_locking/alter_balance/isolate_for_testing/preserve_current_state/no_defensible_direction.
- **`InterventionTestKind`** — single_field_isolated / paired_coupled / multi_field_constrained / preserve_and_observe / evidence_collection_only.
- **`InterventionTarget`**, **`ExpectedResponse`**, **`ControlledTestDesign`**, immutable **`InterventionHypothesis`** (no numeric value / Apply flag / approval flag / mutation callback / persistence), and **`InterventionHypothesisSet`** (retains the source annotation unchanged; testable / conditional / competing / blocked / preserve buckets; deterministic fingerprint).

## 4. Authority reuse (consumed, never copied)
- **Phase 13:** `MechanismStatus`, `MechanismAnnotatedDiagnosis` (candidates + `intervention_field` + `intervention_direction_contradicted` + evidence grade + contradicting-evidence source types), `knowledge_versions`, `mechanism_map.candidates_for` (template flags: `is_driver_technique`, `requires_speed_context`, `intervention_field`), `SessionDB.build_mechanism_annotations`.
- **Phase 12:** `vehicle_dynamics.explain_component(...).axis_effects` is the **single directional sign authority** used to resolve every qualitative direction; `setup_interactions.explain_interaction` for coupling justification.
- **Program 1:** `gearbox_evidence` (gearing states + `final_drive_lengthens/shortens` invariant), the working-window lockouts + outcome history folded through the Phase-13 annotation and the optional `outcome_history` input, canonical parameter semantics (`PARAMETER_INTERACTIONS` via Phase 12).

## 5. Direction resolution (never inferred from a name)
`_resolve_direction(issue_type, component, field, gearbox_state)`:
1. **Gearing** (`TRANSMISSION`/`final_drive`): uses the canonical `gearbox_evidence` state — `conflicting`/`unknown` → `no_defensible_direction`; `too_short` or wheelspin → **lengthen** (lower ratio); `too_long` → **shorten** (higher ratio). The final-drive invariant is preserved.
2. **Brakes** (two-sided): issue-specific rule (`front_lock`→move rearward; `rear_loose_under_braking`→move forward).
3. **Everything else:** the issue's canonical goal axis (`_ISSUE_GOAL_AXIS`) resolved against `explain_component(component).axis_effects` — `direction = increase if (sign>0)==want_more else decrease`, then labelled (stiffen/soften/raise/lower/increase-locking/…). No signed effect → `no_defensible_direction` (evidence collection).

## 6. Eligibility gates (hard, before ranking)
Set-level: an invalid / insufficient / not-evaluable / out-of-scope source annotation blocks the whole set (explained). Per hypothesis: driver technique → `OUT_OF_SCOPE`; contradicted mechanism or prior single-field regression on the field → `CONTRADICTED_BY_OUTCOME`; failed-direction lockout → `BLOCKED_BY_WORKING_WINDOW`; no defensible direction / unknown gearing → `INSUFFICIENT_EVIDENCE`; aero without speed context → `CONDITIONAL`; competing mechanism → `COMPETING_MECHANISMS`; supported + graded → `TESTABLE`.

## 7. Mechanism-to-intervention mapping
Each Phase-13 mechanism candidate carries its canonical `intervention_field`; Phase 14 maps mechanism family → intervention family through that field + the sign authority. It is mechanism-constrained, not a symptom→setting lookup: wheelspin yields competing traction-demand / gear / rear-platform / differential hypotheses — the differential direction is only ever competing/blocked, never auto-generated.

## 8. Confirmed-good protection & minimum-effective intervention
Every hypothesis surfaces the protected-good behaviours (from the annotation) as `protected_good_at_risk` and in the rejection criteria; trade-offs are the *other* axes the field moves (from the sign authority). Ordering prefers single-field isolated tests; coupled tests are permitted only where a prior coupled outcome improved the field-set (capped at `MAX_COUPLED_FIELDS = 2`, crediting the SET, never a single field).

## 9. Controlled test design
Qualitative only (`ControlledTestDesign`): variable under test as a *bounded direction step* (never a number), hold-constant list, baseline checkpoint reference, compound/fuel parity, min clean laps, recurrence expectation, corner context, positive/negative signal, rejection + reversal conditions, A/B/A vs preserve-and-observe, and single-field attributability.

## 10. Outcome-aware constraints
`outcome_history` (Program-1 owned, read-only): a prior single-field regression blocks that direction (`CONTRADICTED_BY_OUTCOME`) while the physics mechanism is retained; a prior coupled improvement enables a paired hypothesis crediting the set; nothing here mutates the outcome record or calibration.

## 11–18. Subsystem rules
LSD stays a three-axis model (initial/accel/decel); wheelspin never auto-increases accel locking; a failed LSD direction is blocked. Aero requires speed context (else conditional/insufficient) and never fabricates load numbers. Springs/dampers/ARB/platform are reasoned separately; damper velocity & suspension travel are declared unavailable. Camber/toe trade-offs come from the sign authority. Gearing obeys the gearbox-evidence state + final-drive invariant. Brake balance separates front-lock vs rear-instability; ballast is never a first-line fix.

## 19. Ranking
Deterministic order: status priority → evidence grade → single-field-before-coupled → stable hypothesis id (explicit non-semantic tie-break). Hard gates run first; ties stay ties.

## 20. Rendering (`strategy/intervention_hypothesis_render.py`)
Sectioned, driver/engineer-readable: source observation, supported/competing mechanisms, proposed hypotheses (by bucket), why plausible, protected-good, trade-offs, coupling, missing evidence, controlled test, rejection criteria, status, safety. Never emits a numeric value, "Apply"/"approve", false certainty, or "the fix is".

## 21. Runtime integration
`SessionDB.build_intervention_hypotheses(**ctx)` — READ-ONLY; composes the Phase-13 `build_mechanism_annotations` aggregate **exactly once** (which itself composes cross-session memory + prediction calibration) and runs the pure Phase-14 reasoning. No per-hypothesis / per-experiment query; empty path returns immediately; writes nothing; DB stays v25.

## 22. UI integration
`InterventionHypothesisPanel` (+ pure `ui/intervention_hypothesis_vm.py`) embedded in the **Development History** page beneath the Phase-13 panel. Structured section cards grouped by diagnosis; competing hypotheses visible together; **no Apply / Approve / Revert / value editor.** The heavy build runs OFF the Qt thread via the existing `MechanismAnnotationWorker(QThread)`; the panel renders the finished immutable dict on the UI thread.

## 23. Determinism
Identical canonical inputs → identical ordering, ids, statuses, grades, test designs, rendered content, `to_dict()` and `content_fingerprint`; verified within-process, across repeated calls, across DB restart, with input ordering changed and irrelevant evidence added. No timestamps / random / object addresses / row order in fingerprints.

## 24. Persistence decision — NONE (proof)
The whole hypothesis set is a pure function of the Phase-13 annotation (itself regenerated from immutable Phase-8/11 records + static Phase-12 knowledge) plus read-only inputs. Same inputs → byte-identical fingerprint across restart (`test_M_populated_history_production_path`, `test_restart_determinism`). No migration; `DB_VERSION` stays **25**.

## 25. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase14_intervention_domain.py` | 17 | direction resolution, eligibility, mapping, coupled/single, test design, rendering |
| `tests/test_phase14_golden_uat.py` | 14 | Scenarios A–N incl. real SessionDB production path + restart |
| `tests/test_phase14_properties.py` | 34 | the 40 property/metamorphic invariants |
| `tests/test_phase14_safety.py` | 10 | no-AI / no-Qt-in-domain / no-DB-in-domain / no-shadow-authority / read-only / versions |
| `tests/test_phase14_query_shape.py` | 4 | single-aggregate reuse, no N+1, cheap empty path, renderer touches no DB |
| `tests/test_phase14_ui_construction.py` | 5 | panel/page construction, no Apply/Approve, off-thread worker |

All 84 pass; Phase 12/13 (154), frozen/no-AI/config/fan-out/session_db (80), setup-synthesis + Program-1 (254) and the broad non-UI strategy regression stay green.

## 26. Safety guarantees
Pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; owns no Apply/Approve/Revert/authoring/persistence; defines no shadow sign graph / dynamics / interaction / LSD / aero table; invents no GT7 channel or numeric value; leaves every Program-1 / Phase-12 / Phase-13 authority canonical; `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 25 unchanged.

## 27. Known limitations
- The aggregate production path does not yet auto-derive per-corner speed context or the gearbox-evidence state, so aero and gearing hypotheses default to conditional / evidence-collection there (the pure API accepts both explicitly).
- Coupled hypotheses currently fire only from a prior coupled-improvement signal; interaction-driven coupling is modelled but conservatively gated.
- Driver preference is consumed as an advisory note; it never changes a status.

## 28. Manual UAT
Porsche 911 RSR '17 @ Fuji: create a recurring entry-understeer diagnosis; open the Development History page; confirm the Phase-14 panel shows a bounded "soften front ARB" candidate controlled test with trade-offs, protected-good, missing evidence, controlled-test design and rejection criteria — and no numeric value and no Apply control; verify a failed-direction field appears blocked; restart and confirm identical output + fingerprint; confirm no protected runtime file and no DB record changed.

## 29. Deferred work / recommended Phase 15
**Phase 15 — Minimum-Effective Experiment Synthesis Handoff:** hand the top defensible hypothesis (still evidence-gated, still manual-Apply) to the existing deterministic setup-synthesis / experiment-selection authority so it can propose the smallest legal numeric step — with Phase 14 supplying the mechanism-constrained direction and Program-1 owning the value, the Apply gate and the outcome loop. Not started.
