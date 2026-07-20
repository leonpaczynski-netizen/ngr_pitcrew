# Engineering Brain — Phase 55: Live GT7 Activity Execution Bridge

Program 2, Phase 55. Read-only, deterministic, offline, no AI. Connects the selected NGR preparation
activity to real GT7 telemetry runtime state while preserving explicit user control. Starts nothing,
applies nothing, binds nothing, completes nothing.

## Immutable runtime snapshot & matching — `strategy/live_activity_bridge.py`

`LiveActivityRuntimeSnapshot` is ONE immutable per-evaluation snapshot (selected activity, expected-vs-
live car/track/layout/discipline/setup/context, lap/session/telemetry-freshness/segment/fuel/tyre/clean+
invalid, objective/target/valid laps, run-plan, voice/advisory readiness). Built once per evaluation,
never rebuilt per telemetry packet.

`classify_live_activity_match` yields 11 outcomes: hard mismatches first (car/track/layout/discipline/
setup/context), `TELEMETRY_STALE`, `ACTIVITY_NOT_SELECTED`; a required unknown field yields
`UNVERIFIABLE` (unknown is NEVER a verified match); a full known match yields `EXACT_ACTIVITY_MATCH`; a
known match with a non-critical unknown yields `MATCH_WITH_LIMITATIONS`. `match_permits_evidence` gates
evidence to EXACT / MATCH_WITH_LIMITATIONS only. The stable fingerprint excludes volatile live counters.

## Bridge views — `strategy/live_bridge_views.py`

`build_practice_bridge` / `build_qualifying_bridge` / `build_race_bridge` combine the snapshot + match
with the Phase-52 low-density views. A hard mismatch or stale telemetry BLOCKS the activity and permits
no evidence; advisories are suppressed on stale telemetry. Qualifying stays MINIMAL; Race stays SAFETY
with `issues_commands=False` and surfaces the mismatch as a critical warning.

## Session-end, recovery, handover — `strategy/live_session_detection.py`

`detect_session_end` never completes an activity — a run that ended with permitted evidence becomes
`BINDING_REQUIRED` (snapshot frozen, awaiting EXPLICIT binding); a run with no bindable evidence becomes
`ENDED_INSUFFICIENT`. `build_binding_handover` reuses the canonical ranker (auto-bind forbidden; newest
never auto-selected) and routes to the correct debrief. `handle_telemetry_dropout` reuses
`programme_resume.resolve_telemetry_dropout` (suppress advisories, preserve evidence, no duplicate
session, no completion). Replay/shadow validation does NOT award live-GT7 certification.

## Tests

`test_phase55_bridge_match.py` (9), `test_phase55_bridge_views.py` (8), `test_phase55_session_end.py` (9).
