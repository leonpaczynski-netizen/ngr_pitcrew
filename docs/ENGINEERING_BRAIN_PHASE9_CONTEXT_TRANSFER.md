# Engineering Brain — Phase 9: Cross-Context Engineering Transfer & Regression Risk Intelligence

**Status:** implemented on branch `eng-brain-phase9-context-transfer` (from `master` @ Phase 8 `da53569`).
**Schema:** **NO migration** — `DB_VERSION` stays **24**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** a READ-ONLY OBSERVER that sits ABOVE Phases 1–8. Before a setup experiment is
proposed it surfaces every relevant lesson already learned in COMPATIBLE contexts. It
evaluates no evidence, creates no experiment, chooses no experiment, modifies no working
window, mutates nothing, and **NEVER blocks**. No AI, no prediction, no probability, no
natural-language reasoning — only deterministic rule-based classification.

## 1. Problem solved

Phase 8 records what was learned per context. Phase 9 answers, before you try something,
*"what already happened in similar situations?"* — surfacing previously successful/failed
experiments, stable working windows, protected behaviours, known-unstable combinations and
known-ineffective directions, plus the regression risks a proposed change would run into,
each with a deterministic match strength and its evidence.

## 2. Starting checkpoint

`eng-brain-phase9-context-transfer` from `master` @ Phase 8 `da53569` (Phases 2–8 stacked;
master at Phase 1). Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status all unchanged.

## 3. Existing authorities reused (no duplication)

| Concern | Reused authority |
|---|---|
| Immutable per-review records | Phase 8 `engineering_development_records` (read-only) |
| Per-context memory fold | Phase 8 `build_history` + `build_engineering_memory` |
| Protected-knowledge constraints | Phase 8 `ConstraintKind` + per-record `protected_knowledge` (already derived) |
| Issue / working-window facts | Phase 8 `IssueMemory` / `WorkingWindowEvolution` |
| Car class for the RELATED tier | existing `cars.category` column |

Phase 9 defines **no** new outcome/residual/recurrence/identity/window authority.

## 4. Context matching hierarchy (fixed — never a probability)

`context_transfer.classify_context_match` returns one of five deterministic strengths, or
excludes the context entirely (never mixed):

| Tier | Strength | Rule |
|---|---|---|
| 1 | **DIRECT_MATCH** | same driver, car, track, layout, discipline, gt7 version |
| 2 | **STRONG_MATCH** | same driver + car, different track |
| 3 | **RELATED_MATCH** | same driver + track, similar car class (different car; class from `cars.category`) |
| 4 | **WEAK_MATCH** | same vehicle, different discipline |
| 5 | **UNKNOWN** | general engineering knowledge (weak commonality — same car) |

Every match states WHY it matched (the reason string) and which sessions/experiments
produced it. RELATED never fires without real class data (honest — never guesses a class).

## 5. Transfer model

`EngineeringTransfer` objects (`context_transfer.build_context_transfers`), ranked
strongest-match-first then confirmed-first then by support count:

- `SUCCESSFUL_EXPERIMENT` / `FAILED_EXPERIMENT` (field, direction, value, outcome, sessions, experiments)
- `STABLE_WINDOW` (converged learned window), `PROTECTED_BEHAVIOUR`
- `KNOWN_UNSTABLE`, `INEFFECTIVE_DIRECTION`

Each carries `strength`, `match_reason`, `supporting_sessions`, `supporting_experiments`,
`confidence`, and `confirmed` (high confidence + ≥2 sessions) vs provisional.

## 6. Engineering constraints

`engineering_constraints.derive_constraints` folds the per-record Phase-8 protected
knowledge + protected behaviours from all compatible contexts into de-duplicated
`EngineeringConstraint`s (kind, field, direction, value, evidence source, supporting
sessions/experiments, times reinforced, confidence). A constraint is **confirmed** when
high-confidence, supported by ≥2 sessions, and from at least a STRONG match; otherwise
provisional. Human details: *"never reduce X below N"*, *"avoid moving X <dir>"*,
*"known unstable: …"*, *"protect: …"*.

## 7. Regression-risk model (never blocks)

`regression_risk.assess_regression_risk(constraints, transfers, proposed_change=…)` flags,
before Phase 5 candidates are displayed:

- `KNOWN_FAILED_DIRECTION` — proposed direction matches a failed-direction lockout
- `PREVIOUSLY_UNSTABLE_RANGE` — field/value previously produced a regression
- `PROTECTED_FIELD_CONFLICT` — proposed field is a protected behaviour
- `WORKING_WINDOW_EDGE` — proposed value at/beyond a learned window edge
- `REPEATED_REGRESSION` — field regressed in ≥2 prior experiments
- `CONFIDENCE_WEAKNESS` — the field's supporting evidence is only provisional

Severity is HIGH/MEDIUM/LOW/INFO. It **only reports** — authority to accept/reject stays
with Phases 3/5/6. Works with or without a proposed change (standing advisory).

## 8. Orchestrator (SessionDB, read-only, no migration)

`build_engineering_context(car, track, layout_id, discipline, driver, gt7_version,
compound, proposed_change=None)` — fetches candidate records (`car` OR `track` OR `driver`),
resolves car classes from `cars.category`, classifies matches, builds transfers + constraints
+ risks, and returns them with per-artifact fingerprints. Read-only; regenerates from the
immutable Phase-8 records; writes nothing.

## 9. UI — the Engineering Context panel

- `ui/engineering_context_vm.py` — pure Qt-free view-model (matched contexts, successful
  fixes, failures, stable windows, protected behaviours, constraints, regression risks).
- `ui/engineering_context_panel.py` — `EngineeringContextPanel`, a self-contained read-only
  advisory with **no Apply and no decision controls** (asserted).
- Surfaced inside the existing **Development History** page (a section above the scorecard),
  populated read-only for the current context; the dashboard passes `build_engineering_context`
  alongside `build_cross_session_memory`. No new tab, no registry change.

## 10. Determinism & purity verification

- All 3 core modules verified free of random/wall-clock/sqlite/Qt/network.
- Transfers / constraints / risks are order-independent and restart-deterministic
  (per-artifact fingerprints identical on rebuild — `test_restart_determinism`).
- Matching is deterministic rule-based; RELATED requires real class data.

## 11. Schema / contract changes

**None.** No migration (`DB_VERSION` 24, `RULE_ENGINE_VERSION` 46.0). No new table, no new
tab. Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status untouched.

## 12. Tests

`tests/test_phase9_{context_transfer,constraints,regression_risk,orchestrator,view_model}.py`
(36 non-UI) + `tests/test_phase9_ui_construction.py` (3 UI — run individually). Golden UAT
drives the real `review_and_learn` loop (Porsche RSR @ Fuji) then queries the Phase-9 advisory.

## 13. Known limitations / deferred

- The panel is surfaced in the Development History page and populated for the current context
  with no proposed change; wiring it into the Setup Builder to react to a specific proposed
  candidate (live `proposed_change`) is deferred (the orchestrator already supports it).
- RELATED matching uses `cars.category` equality; a richer car-similarity model (drivetrain,
  weight/PP bands) is deferred.
- `driver` / `gt7_version` are honest inputs (default unknown when the app cannot resolve them).

## 14. Recommended Phase 10

**Proactive experiment pre-flight:** at the moment Phase 5 proposes a candidate, attach the
Phase-9 advisory to that specific candidate (feed the proposed field/direction/value in) and
render the regression risks + relevant constraints inline beside the candidate — still a pure
observer subordinate to the Phase-3/5/6 decision authority, still never blocking.
