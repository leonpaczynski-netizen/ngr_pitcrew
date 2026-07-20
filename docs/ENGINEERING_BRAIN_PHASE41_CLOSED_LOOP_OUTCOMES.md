# Engineering Brain — Program 2, Phase 41: Outcome Reconciliation & Best-Known Promotion

Read-only, offline, deterministic, advisory-only. Part of the **Phases 39–41 Closed-Loop Development**
slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose & authorities

`strategy/engineering_run_outcome.py` reconciles a completed session against the run plan;
`strategy/closed_loop_report.py` closes the loop with a read-only knowledge-update proposal and one next
action. Both reuse the existing outcome/reconciliation/calibration doctrine and create no competing
outcome record, apply nothing, and promote nothing.

## Session binding & run validity

`assess_run_validity(observation, run_plan)` binds context / applied setup / parent / candidate /
telemetry session / clean laps / conditions and classifies: `VALID`, `VALID_WITH_LIMITATIONS`,
`INVALID` (wrong setup applied / candidate not tested), `CONTEXT_MISMATCH`, `CONFOUNDED` (unplanned
field, undisclosed technique, weather, wrong compound), `INSUFFICIENT_EVIDENCE` (too few clean laps,
incomplete telemetry, interruption). Only `VALID` / `VALID_WITH_LIMITATIONS` count for learning.

## Expected vs observed

`compare_expected_observed` → `IMPROVED` / `REGRESSED` / `UNCHANGED` / `MIXED` / `INCONCLUSIVE` /
`NOT_TESTED`. A protected/critical regression dominates → `REGRESSED`. A faster lap **alone** never
establishes improvement: for Race, worse consistency/tyres/fuel with a faster lap → `MIXED`.

## Best-known setup promotion eligibility

`assess_promotion` → `BEST_KNOWN_ELIGIBLE` / `PROVISIONAL` / `REQUIRES_CONFIRMATION` / `NOT_ELIGIBLE` /
`ROLLBACK_RECOMMENDED` / `SUPERSEDED` / `CONTEXT_LIMITED`, with visible considerations (exact context,
valid run, clean laps, target improvement, protected intact, independence, correct baseline). A setup is
only ever "current best-known for an exact context" (discipline included) — never universally
optimal/ultimate. `BEST_KNOWN_ELIGIBLE` requires a valid, improved, protected-intact, independently
repeated result against the correct baseline. **The applied setup is never mutated**; actual application
stays behind the frozen Apply gate.

## Rollback behaviour

`REGRESSED` / protected loss → `ROLLBACK_RECOMMENDED`; the closed-loop report's primary action is
`roll_back` (single-field) or `isolate_field` (multi-field bundle — the fields stay SUSPECT). A
successful rollback outcome informs future candidate selection.

## Knowledge-update proposal (explicit persistence boundary)

A READ-ONLY proposal of what the existing authorities *would* learn IF the outcome is explicitly
recorded: working-window addition/avoidance, field direction confirmed/suspected, interaction suspected,
protected-behaviour strengthened, prediction calibration, transfer limitation, candidate
retired/repeated, rollback, next experiment. **Nothing is written through a new path.** An
invalid/confounded/insufficient run proposes no window change; a coaching-only run updates only driver
knowledge, never setup windows.

## Next engineering action

Exactly ONE primary action: confirm / repeat / refine / reverse / roll back / isolate a field / test a
competing mechanism / collect missing telemetry / coaching-only run / freeze setup + prepare strategy /
stop (event too close) / accept current best-known / collect controlled baseline. Secondary actions are
listed separately and never conflict.

## UI workflow, query shape & fingerprints

The read-only three-step workflow (Evidence Readiness → Practice Run Plan → Outcome Review) is exposed by
`ClosedLoopWorkflowPanel` in Development History; `SessionDB.build_closed_loop_workflow_report` builds it
off the Qt thread (reused worker + stale-guard). Viewing passes `observation=None`, so nothing is
written merely from viewing. Fingerprints cover canonical context identity, exact evidence membership,
transfer membership, selected candidate, run-plan content, session binding, run validity, observed
outcome, promotion eligibility and the ordered next action; they exclude object/machine identity, paths,
UI state, destinations, wall-clock, random ids and DB row order.

## Deferred (not started)

Live in-session voice coaching, automatic pit calls, automatic setup application, autonomous experiment
execution and outcome auto-persistence remain **deferred** by design — this slice proves the loop can be
run and trusted read-only first.

## Safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; no setup values; never mutates the applied setup,
persists an outcome, creates an experiment, or bypasses the Apply gate.
