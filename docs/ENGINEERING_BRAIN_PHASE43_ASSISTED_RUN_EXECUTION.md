# Engineering Brain — Program 2, Phase 43: Assisted Practice Execution & Explicit Outcome Capture

Read-only, offline, deterministic, advisory-only. Part of the **Phases 42–44 Assisted Runtime
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose & authorities

Turns the Phase-40 run plan into a real, user-controlled practice workflow. It ASSISTS and VALIDATES;
it never autonomously applies a setup, creates an experiment, binds a session or records an outcome.
The canonical Apply gate and the existing explicit experiment/outcome workflows remain the sole
mutation routes.

| Module | Owns |
| --- | --- |
| `strategy/assisted_run_workflow.py` | the 12-state workflow, setup-fingerprint verification, block gates. |
| `strategy/session_binding.py` | candidate-session ranking; explicit selection required. |
| `strategy/assisted_outcome_capture.py` | structured outcome review (reuses Phase-41), explicit-confirm gate. |

## Workflow states

`PLAN_READY`, `PREFLIGHT_REQUIRED`, `SETUP_CONFIRMATION_REQUIRED`, `READY_TO_RUN`, `RUN_ACTIVE`,
`RUN_COMPLETED`, `SESSION_BINDING_REQUIRED`, `OUTCOME_REVIEW_REQUIRED`, `READY_TO_RECORD`, `RECORDED`,
`INVALID`, `ABANDONED`. The evaluator never advances past a gate the user has not explicitly confirmed.

## Setup fingerprint verification

`verify_setup` compares the expected active setup to the CURRENT canonical applied setup by fingerprint
(`setup_hash`) — a canonical fingerprint is trusted over any button click. It returns `MATCH` /
`MISMATCH` (wrong setup) / `UNEXPECTED_CHANGE` (a field also changed from the parent that was not the
controlled change → the run would be confounded) / `UNVERIFIABLE` (no canonical fingerprint — confirm
manually). No setup is applied from this workflow; navigation to the existing Apply workflow is
permitted but the Apply gate remains the sole mutation route.

## Preflight & READY_TO_RUN blocking

Reuses the canonical experiment preflight. `READY_TO_RUN` is blocked when: the wrong setup is active
(fingerprint mismatch), context materially differs (Phase-42 material trust `INCOMPATIBLE`/
`REFERENCE_ONLY`), a protected/unplanned field changed unexpectedly, preflight has unresolved blockers,
required session identity is missing, the candidate is stale/superseded, or the run-plan fingerprint no
longer matches the current plan.

## Session candidate & binding rules

`rank_candidate_sessions` scores candidates by car/track/layout/compound/setup-fingerprint/clean-laps,
lists per-session matches + mismatches + confidence, and **never auto-binds**: `auto_bind_forbidden` and
`requires_explicit_selection` are always true, recency is only a final stable tie-breaker (never
primary), and equally-matched sessions are flagged `ambiguous` for explicit choice. The newest session
is never bound merely because it is newest.

## Assisted outcome capture & canonical write path

`build_assisted_outcome_review` builds the structured review from a **bound** session's observation by
reusing the canonical Phase-41 run-outcome + closed-loop authorities (target problem, expected/observed,
feedback, protected regressions, lap/consistency/tyre/fuel effects, validity, attribution limitations
from Phase-42 material trust, rollback, promotion, next action, knowledge-update proposal). Readiness:
`NOT_READY` (unbound) / `REVIEW_REQUIRED` / `READY_TO_RECORD` (explicit confirm) / `BLOCKED` (invalid
run). `FEEDBACK_OPTIONS` align with canonical findings (improved/worse/unchanged/mixed/could_not_judge/
not_tested). **The confirmed result is written ONLY through the existing canonical experiment-outcome
workflow** — no alternative outcome table or persistence path is introduced.

## Audit trail

A reference audit trail records who confirmed the run, the context/setup/run-plan fingerprints, the
linked experiment + telemetry session, and the explicit outcome confirmation — with **no wall-clock in
any semantic fingerprint**.

## Explicit write boundaries & safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; no setup values. Applies nothing, creates no
experiment, binds no session, records no outcome; the Apply gate and canonical outcome workflow are the
only mutation routes.
