# Engineering Brain — Phase 54: Persisted Activity State & Command Centre Truth

Program 2, Phase 54. Read-only, deterministic, offline, no AI. Replaces the Command Centre's four
previously-defaulted inputs (`pending_binding`, `pending_debrief`, `strategy_final_ready`,
`lock_ready_disciplines`) with canonical persisted or deterministically-derived state.

## Canonical activity truth — `strategy/canonical_activity_state.py`

`ActivityFact` carries PERSISTED facts (activity state, `session_ended`, `has_binding`,
`has_debrief_outcome`, feedback, `invalidated`, candidate count). Derivations:

- `derive_pending_binding` — pending only when the run ENDED + candidate session(s) exist + no canonical
  binding + activity requires telemetry + not abandoned/invalid. Telemetry existing alone is never enough.
- `derive_pending_debrief` — pending only when a canonical binding exists + requires debrief + no
  canonical outcome + not abandoned/invalid.
- `derive_activity_state` — deterministic `LiveActivityState`; `COMPLETED` requires persisted COMPLETED +
  binding + recorded outcome (a bare persisted COMPLETED is not canonically complete).
- `check_consistency` — read-only `ActivityStateConsistencyReport`; NEVER repairs. Detects
  completed-without-binding, debrief-without-session, two-active-activities, locked-without-record,
  strategy-final-without-race-lock, selected-cycle-missing, cross-cycle-binding, wrong-discipline-debrief.

## Persisted signals (SessionDB) — `build_command_centre_truth`

Resolves cycle + activities + bindings + candidate telemetry sessions with a CONSTANT number of bounded
queries (no N+1); writes nothing. Persisted canonical signals: `IN_PROGRESS` = the run occurred
(`session_ended`); `COMPLETED` = the explicit debrief/outcome workflow finished (`has_debrief_outcome`).
`candidate_session_count` counts UNBOUND context-matching sessions.

## Setup-lock & strategy-finalisation readiness — `strategy/setup_strategy_readiness.py`

`derive_setup_lock_readiness` — lock is ELIGIBLE (not locked) when convergence permits and it is not
already locked; LOCK_READY never implies LOCKED. `derive_strategy_finalisation_readiness` — finalisation
is ELIGIBLE (not finalised) when maturity is FINALISATION_READY and not already finalised;
FINALISATION_READY never implies FINALISED. `build_setup_strategy_readiness` reports per-discipline lock
readiness + strategy readiness, respecting the persisted lock/strategy records (v28 `setup_lock_json` /
`strategy_final_json`).

## Command Centre wiring

`build_event_command_centre_view` now derives the four flags from these authorities when a cycle resolves
(placeholder defaults removed): a run that ended yields "Bind the latest Practice session"; after binding
yields "Complete the session debrief"; otherwise the cumulative objective. Still exactly ONE primary
action; still constant query count; still writes nothing.

## Persistence conclusion

No v29 migration required. All durable explicit decisions live in existing v28 structures
(`event_preparation_activities.state`, `event_preparation_activity_sessions`,
`event_preparation_cycles.setup_lock_json` / `strategy_final_json`) plus existing outcome tables. Viewing
and Home refresh create no activity records.

## Tests

`test_phase54_canonical_truth.py` (21), `test_phase54_truth_db.py` (8),
`test_phase54_lock_strategy_readiness.py` (10), `test_phase54_next_action_truth.py` (7).
