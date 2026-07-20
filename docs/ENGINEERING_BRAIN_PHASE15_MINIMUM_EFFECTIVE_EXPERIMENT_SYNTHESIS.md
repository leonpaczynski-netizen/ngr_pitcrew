# Engineering Brain — Program 2, Phase 15: Minimum-Effective Experiment Synthesis Handoff

**Status:** implemented on branch `eng-brain-phase15-minimum-effective-experiment-synthesis` (from `8e48beb`, the Phase-14 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the deterministic, READ-ONLY handoff from a valid, testable Phase-14 intervention hypothesis into the existing setup-synthesis / setup-experiment authorities. The output is a BOUNDED setup-experiment candidate: the smallest legal, reversible, evidence-appropriate numeric setup step that tests the hypothesis without unnecessarily disturbing confirmed-good behaviour.

It answers *"what is the smallest legal, reversible numeric experiment that tests this hypothesis?"* — never *"what is the final ideal setup?"*. It NEVER auto-applies, bypasses the Apply gate, invents parameter limits, builds a second synthesiser, optimises the whole car, silently changes coupled fields, mutates the diagnosis / mechanism / outcome / calibration / setup-history / active-setup, or persists an experiment. No AI/network.

## 1. Objective & authority hierarchy
Phase 15 is a constrained handoff layer between mechanism-constrained intervention (Phase 14) and the existing deterministic setup-synthesis / setup-experiment / preflight / Apply-gate authorities. Hierarchy: telemetry → validity/recurrence → canonical diagnosis → mechanism annotation (P13) → intervention hypothesis (P14) → **bounded-experiment synthesis (P15)** → setup-synthesis → setup-experiment → preflight → **Apply gate (only mutation route)** → manual action → postflight → calibration.

## 2. Authority reuse (consumed, never duplicated)
- **Baseline:** `data.setup_state_authority.evaluate_analysis_gate` + `ActiveSetup` + `data.applied_checkpoint.compute_setup_hash` — the single canonical applied-setup authority + fingerprint.
- **Legal step / quantisation:** `experiment_selection.legal_step` + `setup_synthesis._round`.
- **Legal bounds:** `setup_ranges.resolve_ranges`.
- **Final-drive invariant:** `gearbox_evidence` (lower ratio = LONGER gearing).
- **Working-window lockouts:** `working_window.LearnedWorkingWindow.locked_directions()`.
- **Phase 14:** `InterventionHypothesis(Set)`, target/direction/protected-good/test-design/status, `SessionDB.build_intervention_hypotheses`. Phases 12/13 flow in transitively through the P14 hypothesis.
- No shadow parameter-range table, step-size table, setup synthesiser, Apply path, working-window system, or history authority is introduced.

## 3. Domain model (`strategy/experiment_synthesis.py`, pure)
- **`ExperimentSynthesisStatus`** — `READY_FOR_PREFLIGHT`, `CONDITIONAL`, `NO_ELIGIBLE_HYPOTHESIS`, `INSUFFICIENT_EVIDENCE`, `BLOCKED_BY_WORKING_WINDOW`, `BLOCKED_BY_PRIOR_REGRESSION`, `BLOCKED_BY_LEGALITY`, `BLOCKED_BY_INTERACTION_RISK`, `BLOCKED_BY_BASELINE_STATE`, `REQUIRES_COUPLED_EXPERIMENT`, `NOT_EVALUABLE`, `OUT_OF_SCOPE`.
- **`BaselineSetupReference`** — the canonical applied setup + hash + identity + completeness/legality/active + `is_valid_baseline` + block reason.
- **`ParameterExperimentDelta`** — one bounded field change (baseline/candidate/delta/direction/legal low/high/step/exactly-one-step/larger-step-reason/role/trade-offs/source ids).
- **`BoundedSetupExperiment`** — immutable candidate (baseline ref, deltas, unchanged-field count + preserved-fields fingerprint, expected response, protected-good, test protocol, preflight requirements, rejection criteria, reversal, attribution scope, status, content fingerprint). No Apply/approval flag / callback / persistence.
- **`ExperimentSynthesisResult`** — source hypothesis set (unchanged), baseline, selected candidate, alternatives, rejected + reasons, unresolved conflicts, preflight readiness, safety statement, deterministic fingerprint.

## 4. Baseline authority
Defaults automatically to the canonical applied setup (`ActiveSetup.to_record()`), validated by `evaluate_analysis_gate` (blocks NO_ACTIVE_SETUP / NOT_APPLIED / IDENTITY_MISMATCH / INCOMPLETE_SNAPSHOT / STALE) plus a re-computed-hash drift check (`baseline_drift`). Never falls back to defaults or a last-viewed setup; a candidate setup is never used unless canonically applied. An invalid baseline → whole set `BLOCKED_BY_BASELINE_STATE`, no candidates.

## 5. Hypothesis eligibility
`TESTABLE` → proceeds (may reach `READY_FOR_PREFLIGHT`); `CONDITIONAL` and `COMPETING_MECHANISMS` → proceed only to a `CONDITIONAL` *discriminating* single-field test (never ready, never an auto-winner); `CONTRADICTED_BY_OUTCOME` → `BLOCKED_BY_PRIOR_REGRESSION`; `BLOCKED_BY_WORKING_WINDOW` → blocked; `INSUFFICIENT_EVIDENCE`/`NOT_EVALUABLE`/`OUT_OF_SCOPE`/`BLOCKED_BY_SAFETY_OR_VALIDITY` → blocked. Hard gates run before numeric synthesis.

## 6. Minimum-effective numeric step
`proposed = _round(field, baseline ± legal_step(field))`; verified within `resolve_ranges` bounds, not a no-op, not below the measurable threshold, direction not locked, not a failed direction. Out of range → no candidate (`BLOCKED_BY_LEGALITY`, never clamped to a disguised no-op). A larger-than-one-step move is allowed only with a canonical justification from a fixed allowed set (dead band / non-uniform discrete / threshold crossing / prior one-step inconclusive / one-step meaningless), bounded to `MAX_JUSTIFIED_STEPS = 2`; removing it restores the one-step result.

## 7. Direction sign (from Phase 14, never the name)
`InterventionDirection` → `+1/-1` field move: stiffen/raise/increase/increase-locking/move-rearward/shorten → +1; soften/lower/decrease/decrease-locking/move-forward/lengthen → -1. Gearing keeps the invariant (lengthen = lower final-drive ratio; shorten = higher). `alter_balance`/`isolate`/`preserve`/`no_defensible_direction` → no numeric.

## 8. Single-field vs coupled
Single-field is preferred and default (exactly one field changes; every other field preserved; attribution single-field). Coupled synthesis only when the Phase-14 hypothesis was `paired_coupled` → status `REQUIRES_COUPLED_EXPERIMENT` (≤ `MAX_COUPLED_FIELDS = 2`, roles primary/compensatory, attribution to the pair) until the coupling + preflight are fully specified. No "change everything" candidates; no silent compensating field.

## 9. Interaction-risk gate
Before accepting: working-window lockout on the field → `BLOCKED_BY_WORKING_WINDOW`; prior single-field regression → `BLOCKED_BY_PRIOR_REGRESSION`; protected-good behaviours are surfaced (never silently disturbed) and appear in the rejection criteria. It may allow / narrow / require coupling / require evidence / block — it never silently adds fields.

## 10. Parameter-specific behaviour
LSD stays three-axis (wheelspin never auto-increases accel locking; failed LSD direction blocked; "LSD feels wrong" alone has no canonical issue → no experiment; a valid initial-torque hypothesis → one legal step of `lsd_initial` only). Aero requires speed context (low-speed → never ready). Springs/dampers/ARB/ride-height are per-corner independent (distinct field mapping: `dampers_front_comp` ≠ `dampers_rear_comp` ≠ `*_ext`). Count-only bottoming → no platform experiment. Camber/toe use canonical `_round` (toe sign preserved). Gearing uses the gearbox-evidence state + final-drive invariant; unknown/conflicting → no gearing experiment. Brake balance uses the legal step and the Phase-14 two-sided direction. Ballast only from an eligible ballast hypothesis and only with legal headroom.

## 11. Controlled test protocol
Baseline fingerprint, changed field(s), unchanged-field guarantee, direction, candidate value(s), compound/fuel parity, min clean laps, warm-up treatment, corner + handling phase, positive/adverse signals, canonical recurrence/outcome rejection rules (no fabricated numeric telemetry thresholds), recurrence requirement, A/B/A vs preserve-and-observe, attribution, and whether it enters postflight.

## 12. Preflight & Apply gate & lifecycle
The candidate declares its preflight requirements (baseline valid/complete/matched, legal + on-increment, differs + correct direction, only-changed-fields, window permits, coupling specified). It becomes `READY_FOR_PREFLIGHT` only when all synthesis-level gates pass; the existing Phase-10 `build_experiment_preflight` / `preflight_validation` remains the full pre-flight authority and is not duplicated. The candidate carries the provenance the canonical `SetupExperiment` needs (baseline, changed fields, expected response, protected behaviours, attribution, reversal, source hypothesis/mechanism/diagnosis, fingerprints) but Phase 15 creates/persists/applies nothing — the existing explicit experiment workflow and the frozen Apply gate remain the only routes.

## 13. Ranking & ties
Deterministic order: evidence grade → single-field preference → one-step preference → protects-confirmed-good → stable candidate id (non-semantic tie-break). Hard gates first. A genuine tie (same sort prefix) is not auto-selected — both candidates are returned as alternatives with an explicit `unresolved_conflicts` note requiring manual choice before preflight.

## 14. Runtime integration & query shape
`SessionDB.build_bounded_setup_experiments(**ctx, applied_setup=..., session_identity=...)` — READ-ONLY; composes the Phase-14 `build_intervention_hypotheses` aggregate **exactly once**, loads `resolve_ranges(car)` once, and runs the pure Phase-15 reasoning against the caller-supplied canonical applied setup. Proven: it issues the same read queries as the hypothesis build (no extra), the count is constant regardless of diagnosis count (no N+1), the empty path is cheap (≤6 reads), and the renderer touches no DB. No writes; DB stays v25.

## 15. UI integration & numeric rendering
`ExperimentSynthesisPanel` (+ pure `ui/experiment_synthesis_vm.py`) embedded in the **Development History** page beneath the Phase-14 panel. It renders numeric baseline vs candidate values with provenance (Phase 15's purpose is a bounded numeric experiment) but has **no editable numeric controls and no Apply/Approve/Revert controls** — every value comes from canonical data + legal semantics, baseline/candidate are always distinguished, display rounding never changes the stored value, and no value is labelled optimal or applied. Build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`.

## 16. Determinism (proof)
Identical inputs → identical eligibility, baseline, candidate values, deltas, preserved-field fingerprints, status, ordering, rendered output, `to_dict()` and `content_fingerprint`; verified across repeated calls, reordered/irrelevant evidence, and DB restart. No timestamps / random / row order / object addresses in fingerprints.

## 17. Persistence decision — NONE
The candidate is reproducible from the canonical applied setup + Phase-14 hypothesis + canonical parameter semantics + outcome history + working-window state. Nothing is persisted for caching. `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` **46.0**.

## 18. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase15_synthesis_domain.py` | 17 | baseline authority, minimum step, single-field, coupled, legality, direction/invariant, rendering |
| `tests/test_phase15_golden_uat.py` | 18 | Scenarios A–R incl. real SessionDB production path + restart |
| `tests/test_phase15_properties.py` | 35 | the 64 property/metamorphic invariants |
| `tests/test_phase15_safety.py` | 8 | no-AI / no-Qt-in-domain / no-DB-in-domain / no-shadow-authority / read-only / versions |
| `tests/test_phase15_query_shape.py` | 4 | single-aggregate reuse, no N+1, cheap empty, renderer-no-DB |
| `tests/test_phase15_ui_construction.py` | 5 | panel/page construction, no editable/Apply controls, off-thread |

All 103 pass; Phase 12/13/14 (238), frozen/no-AI/config/fan-out/session_db (80), setup-state/selection/ranges (143), broad non-UI regression (1531) stay green.

## 19. Safety guarantees
Pure domain is Qt-free, DB-free (no sqlite/SessionDB), network-free, AI-free, random-free, wall-clock-free; owns no Apply/approve/save/persist capability; defines no shadow range/step/synthesiser authority; never mutates diagnosis/mechanism/outcome/calibration/setup-history/active-setup; the frozen Apply gate remains the only mutation route; `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 25 unchanged; protected runtime files byte-identical.

## 20. Known limitations
- The aggregate production path passes `working_windows={}` (lockouts are already carried by the Phase-14 hypothesis status); the pure API accepts `LearnedWorkingWindow` objects for a direct re-check.
- Coupled candidates require the compensating field/roles to be supplied downstream (they stay `REQUIRES_COUPLED_EXPERIMENT`).
- `final_drive` has no default range for many cars, so gearing candidates need a car with a defined final-drive range or an explicit range override.
- Larger-than-one-step justification is accepted as a structured input; auto-derivation of dead-bands from the working window is deferred.

## 21. Manual UAT
Porsche 911 RSR '17 @ Fuji: apply a complete setup in game; drive valid laps to create a recurring entry-understeer diagnosis; open the Development History page; confirm the Phase-15 panel shows baseline vs candidate (e.g. soften front ARB 4 → 3, one legal step), all other fields preserved, protected-good, trade-offs, test protocol, rejection + reversal, and no editable/Apply control; change the applied setup and confirm synthesis blocks on mismatch/stale; restart and confirm identical output + fingerprint; confirm no protected runtime file and no DB record changed.

## 22. Deferred work / recommended Phase 16
**Phase 16 — Guarded Experiment Lifecycle & Postflight Loop Closure:** let the user convert a `READY_FOR_PREFLIGHT` candidate into the canonical `SetupExperiment` through the existing explicit workflow, route it through Phase-10 preflight and the frozen Apply gate, then close the loop through Phase-3 outcome + Phase-11 reconciliation — with Phase 15 supplying the bounded candidate and Program 1 owning creation, Apply, outcome and calibration. Not started.
