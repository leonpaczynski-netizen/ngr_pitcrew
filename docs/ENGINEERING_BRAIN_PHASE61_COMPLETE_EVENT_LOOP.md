# Engineering Brain — Phase 61: Complete Driver Event Loop

Program 2, Phase 61. Read-only, deterministic, offline, no AI. Completes the real workflow from activity
preparation through live running, session binding, debrief and Command Centre update. Advances nothing on
its own.

## Briefing & explicit launch — `strategy/driver_event_loop.py`

`ActivityBriefing` (event / activity / objective / setup / run-plan / target laps + corners / evidence
required / held-constant / stop conditions / readiness blockers). `decide_activity_launch` reuses the
Phase-52 `assess_start_readiness`: launch requires readiness satisfied AND explicit confirmation — opening
the briefing never launches; a blocked readiness never launches even when confirmed. `advance_event_loop`
is the deterministic loop (BRIEFING → READINESS → LIVE → SESSION_END → BINDING → DEBRIEF →
CUMULATIVE_UPDATE → COMMAND_CENTRE_RETURN): it NEVER skips binding or debrief, and NEVER reaches cumulative
update without an explicitly-confirmed outcome.

## Discipline workflow — `strategy/discipline_workflow.py`

`assess_discipline_workflow` returns the pit-wall mode (by activity type) + discipline preconditions:
Qualifying requires the qualifying setup discipline (low-density view); Race requires the race setup
discipline AND a finalised-or-explicitly-accepted strategy state (a not-finalised strategy is an advisory
warning surfaced in the Race view, never an autonomous block). Practice reflects purpose.

## Binding, debrief & Command Centre return — `strategy/binding_debrief_workflow.py`

`build_binding_workflow` presents candidates ranked by the canonical ranker for EXPLICIT selection
(context beats recency; auto-bind forbidden; newest never defaulted). `decide_debrief_launch` routes a
bound activity to the correct debrief and requires binding first. `plan_cumulative_event_update` updates
cumulative event knowledge ONLY after an explicitly-confirmed outcome AND only for VALID/LIMITED evidence
(invalid/mismatched/abandoned update nothing). `resolve_command_centre_return` refreshes the Command
Centre FROM CANONICAL TRUTH (no manual UI flags).

## Restart & event-switch — `strategy/live_restart_recovery.py`

`resolve_live_restart` restores the selected event/activity + pending binding/debrief after restart
(reusing Phase-53 `programme_resume`); an interrupted activity is never restored COMPLETED; the restored
nav is never started/entered. `is_stale_snapshot` is the pure event-switch rule (a snapshot/worker for one
(event, activity) must not update a different current one; mirrors the dashboard stale guard).

## Tests

`test_phase61_briefing_launch.py` (8), `test_phase61_discipline_workflow.py` (7),
`test_phase61_binding_debrief.py` (7), `test_phase61_restart_eventswitch.py` (6).
