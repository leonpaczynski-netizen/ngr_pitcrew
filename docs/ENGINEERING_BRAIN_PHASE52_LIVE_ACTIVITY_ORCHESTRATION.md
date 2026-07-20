# Engineering Brain — Phase 52: Live Activity Orchestration

Program 2, Phase 52. Read-only, deterministic, offline, no AI. Connects an Event Preparation activity to
real setup state, telemetry, live advisories, explicit binding, debrief and cumulative learning. It
advances no state automatically, applies no setup, binds no session, records no outcome.

## Activity lifecycle & start readiness — `strategy/live_activity.py`

`LiveActivityState` (12): PLANNED · PREFLIGHT · READY · ACTIVE · INTERRUPTED · TELEMETRY_LOST ·
SESSION_ENDED · BINDING_REQUIRED · DEBRIEF_REQUIRED · COMPLETED · INVALID · ABANDONED.

`assess_start_readiness(ActivityExecutionContext)` → one check per requirement; `can_start` is True only
when every BLOCKING check is OK (voice + tyre selection are non-blocking — voice is off by default and a
tyre may legitimately be unknown). Universal gates: active cycle, activity bound, event context, discipline,
run plan, setup restrictions, deadline, plan-fresh, telemetry (when required), applied-setup fingerprint
match. Type-specific: setup experiment (delta + preflight), coaching (held-constant setup + exactly one
objective), tyre test (compatible compound + multiplier), fuel test (multiplier + fuel window), qualifying
sim (qualifying setup), race sim (race setup + strategy objective).

`assess_completion(...)` — an activity reaches COMPLETED only with EXPLICIT confirmations (session binding
where telemetry is required, evidence classification, driver feedback, debrief confirmation); never
automatic. Abandoned/invalid short-circuit to terminal states.

## Live modes — `strategy/live_activity_modes.py`

Three deliberately low-density views over the existing live-advisory authorities (referenced, not
re-implemented): PracticeLiveView (FOCUSED), QualifyingLiveView (MINIMAL — it structurally cannot carry
Practice experiment detail), RaceLiveView (SAFETY — `issues_commands` hard-coded False; no unsupported
pit/tyre/fuel command; voice off by default). Stable-identity fingerprints exclude live counters/advisory.

## Binding, debrief, cumulative update — `strategy/activity_binding.py`

Candidate ranking reuses `strategy.session_binding.rank_candidate_sessions` (context+setup match; recency
only a tie-breaker; `auto_bind_forbidden`; explicit selection always required). `debrief_kind_for` /
`assess_debrief_readiness` route a bound activity to the correct debrief (Practice run / Qualifying review /
Race debrief), and a debrief cannot begin before an explicit binding where telemetry is required.
`plan_cumulative_update`: only VALID / LIMITED evidence updates the cumulative programme (LIMITED is
labelled + capped); INVALID / MISMATCHED / ABANDONED update NOTHING and cannot strengthen confidence.
Same-cycle accumulation is guaranteed by the Phase-48 monotonic evidence membership — a new session never
resets lineage / windows / coaching / tyre / fuel / strategy / readiness / confidence.

## Tests

`test_phase52_live_activity.py` (17), `test_phase52_live_modes.py` (6), `test_phase52_binding_debrief.py` (8).
