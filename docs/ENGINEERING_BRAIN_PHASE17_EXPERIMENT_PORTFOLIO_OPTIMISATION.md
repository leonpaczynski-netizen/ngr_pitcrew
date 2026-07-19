# Engineering Brain — Program 2, Phase 17: Experiment Portfolio Optimisation & Information-Gain Selection

**Status:** implemented on branch `eng-brain-phase17-experiment-portfolio-optimisation` (from `3cc36e8`, the Phase-16 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the deterministic engineering PLANNER that sits immediately before Phase 15 and answers *"which experiment should the driver perform next?"* — optimising for **engineering value (information gain first), not lap time**. It CONSUMES the existing authorities (Phase-15 bounded experiments, the Phase-14 hypotheses embedded in each synthesis result, outcome history, prediction calibration, working-window protection, confirmed-good behaviour) and replaces none of them.

It NEVER mutates a setup / experiment / outcome / reconciliation / calibration, applies anything, writes to the database, or duplicates any lifecycle or scoring authority. No AI/network.

## 1. Core principle
The objective is not the fastest setup — it is the experiment with the greatest **engineering value**: reduce uncertainty, test the strongest mechanism, protect confirmed-good behaviour, minimise setup disturbance, maximise attribution quality, and improve future engineering knowledge. **Information gain is the primary optimisation objective** (highest weight); lap time is not a scoring dimension.

## 2. Architecture
Phase 17 is the planner immediately before Phase 15. It consumes the Phase-15 synthesis aggregate (the legal bounded experiments across all diagnoses, with their embedded Phase-14 hypothesis sets) + prediction calibration + optional outcome history + session context, and ranks them. It replaces no synthesis / lifecycle / preflight / Apply / outcome / reconciliation / calibration authority.

## 3. Ranking dimensions (individually visible — no black box)
`ExperimentValuation` carries all **13** dimensions, each a 0..1 `ValueDimension` with its score, **visible weight** and rationale; the engineering value is the transparent weighted mean (weights exposed as `DIMENSION_WEIGHTS` on every portfolio):
1. **information_gain** (weight 3.0 — PRIMARY) — discriminates competing mechanisms + isolates one variable + weak current evidence.
2. mechanism_discrimination (2.0). 3. attribution_quality (1.5). 4. reversibility (1.0). 5. protection_of_confirmed_good (1.5). 6. low_masking_risk (1.0). 7. low_interaction_complexity (1.0). 8. low_driver_workload (0.75). 9. session_suitability (1.0). 10. remaining_uncertainty (1.5). 11. proven_history_usefulness (0.5). 12. prediction_calibration_benefit (1.0). 13. future_engineering_value (1.0).

## 4. Portfolio & roles
`EngineeringPortfolio` classifies every candidate into `PortfolioRole`: `HIGHEST_VALUE` (the single best next experiment, only when it strictly out-ranks the runner-up), `ALTERNATIVE`, `DEFERRED` (conditional / needs coupling first), `BLOCKED` (synthesis blocked), `REDUNDANT` (superseded), `OBSOLETE` (retired). Experiments are never duplicated (deduped by `candidate_id`); a genuine tie keeps both as alternatives (no artificial winner).

## 5. Dependency graph
`ExperimentDependency` models relationships deterministically: `SUPERSEDES` (same field+direction across diagnoses — the higher-value one is kept, the rest are redundant), `MUTUALLY_EXCLUSIVE` (opposite directions on the same field cannot both be tested from one baseline), `UNNECESSARY_IF_FAILS`/`DEPENDS_ON` (for a competing-mechanism diagnosis, the follow-ups depend on the highest-value discriminating test — unnecessary if it isolates the cause).

## 6. Retirement rules
A candidate is `OBSOLETE` when its (field, coarse-direction) is already confirmed (`confirmed_improvement`/`partial_improvement`) or already rejected (`regression`) in the outcome history, or superseded by a higher-value same-field experiment. Retired experiments are shown with their reason (never silently dropped).

## 7. Session awareness
`session_context` (practice_minutes_remaining, tyre_sets_available, fuel, weather, session_objective, weekend_phase) drives `session_suitability` (`SUITABLE`/`MARGINAL`/`UNSUITABLE`/`UNKNOWN`). Unavailable information is never invented — an empty/unknown context yields `UNKNOWN` and a lower `session_suitability` score.

## 8. Engineering roadmap
A deterministic advisory roadmap: experiment (highest value) → review → (a second independent, non-dependent experiment → review) → validate → freeze → race. It remains advisory; nothing is applied.

## 9. Runtime integration (read-only)
`SessionDB.build_experiment_portfolio(**ctx, applied_setup=..., session_identity=..., session_context=..., outcome_history=...)` — composes the Phase-15 `build_bounded_setup_experiments` aggregate **once** + `build_prediction_calibration`, then runs the pure planner. No per-candidate DB query; query count is constant regardless of diagnosis count; empty path is cheap; renderer touches no DB. Writes nothing; DB stays v25.

## 10. UI integration
`EngineeringPlanPanel` (+ pure `ui/engineering_plan_vm.py`, renderer `strategy/experiment_portfolio_render.py`) embedded in the **Development History** page beneath the Phase-16 panel. It shows the highest-value next experiment, the visible value dimensions, alternatives, deferred/blocked/obsolete/redundant, dependencies and the roadmap. **No Apply / Approve / Revert control and no editing** — the frozen Apply gate remains the only route to the car. Build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`.

## 11. Determinism & persistence
Identical inputs → identical ranking, roles, dependencies, roadmap, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses. Nothing persisted; `DB_VERSION` stays **25**.

## 12. Safety guarantees (proven)
No setup / experiment / outcome / calibration mutation; no Apply path; **no hidden optimisation** (dimensions + weights are visible, and lap time is not a dimension); no AI; no DB writes (the runtime path leaves `engineering_development_records` and `user_version` unchanged); no duplicate lifecycle or scoring authority (the planner reimplements no synthesis / lifecycle / evidence-grading); pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 25 are unchanged; protected runtime files byte-identical.

## 13. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase17_portfolio_domain.py` | 17 | generation, ranking, info-gain, visible dimensions, retirement, redundancy/dependencies, roadmap, ties, session awareness, determinism, rendering |
| `tests/test_phase17_golden.py` | 3 | real SessionDB production path + restart determinism |
| `tests/test_phase17_safety.py` | 9 | no mutation/apply/writes/AI, no hidden optimisation, no duplicate scoring/lifecycle, learning-not-lap-time, versions |
| `tests/test_phase17_query_shape.py` | 3 | aggregate reuse, no N+1, cheap empty, renderer-no-DB |
| `tests/test_phase17_ui_construction.py` | 5 | panel/page, no Apply/edit controls, off-thread |

All 37 pass. Phase 12–16 non-UI (352) + frozen/no-AI/config/fan-out/session_db + broad non-UI regression (2384) green; every UI construction module passes per-file (12→17). (UI-worker tests must run per-file — the documented cross-file PyQt `app.exec()` isolation requirement — not a code defect.)

## 14. Known limitations
- The aggregate path passes no explicit `session_context`/`outcome_history` from the dashboard yet (defaults to unknown session + the annotation-carried history); the pure API accepts both explicitly.
- `proven_history_usefulness` is a fixed modest score in this phase (a richer proven-history signal is deferred).
- Redundancy is keyed on coarse (field, increase/decrease) direction; finer magnitude-aware supersession is deferred.

## 15. Manual UAT
Porsche 911 RSR '17 @ Fuji: create two recurring diagnoses; open the Development History page; confirm the Phase-17 Engineering Plan panel shows the highest-value next experiment with every value dimension visible (information gain weighted highest), alternatives, any redundant/obsolete/deferred experiments with reasons, the dependency graph and the advisory roadmap (experiment → review → validate → freeze → race), and no Apply/edit control; supply a session context with 0 practice minutes and confirm suitability drops to unsuitable; restart and confirm identical output + fingerprint; confirm no protected runtime file and no DB row changed.

## 16. Deferred work / recommended Phase 18
**Phase 18 — Cross-Session Development Campaign & Convergence Detection:** sequence the ranked portfolio into a multi-session campaign, detect when the working windows have converged (diminishing information gain) and recommend freezing, and re-open the plan when a cross-session regression is detected — still through every existing gate and manual Apply. Not started.
