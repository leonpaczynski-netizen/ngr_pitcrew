# Engineering Brain — Phase 57: Real GT7 Runtime Adapter

Program 2, Phase 57. Read-only, deterministic, offline, no AI. Connects the existing real telemetry
tracker to the canonical `LiveActivityRuntimeSnapshot` (Phase 55). Creates NO new UDP listener / polling
loop / telemetry tracker.

## Telemetry ownership (audit)

GT7 packets enter via the existing daemon `telemetry.listener.UDPListener` (off the UI thread) and update
`telemetry.state.RaceStateTracker` (lap records, session type, fuel, tyre, phase). This slice REUSES that
pipeline: the dashboard reads the tracker into a normalised `TrackerRuntimeSnapshot` (a thin, thread-safe
read); this domain never touches the tracker, socket, or DB directly.

## Immutable runtime adapter — `strategy/gt7_live_adapter.py`

`TrackerRuntimeSnapshot` (normalised tracker read) + `SelectedActivityContext` (the expected context —
purpose/discipline comes ONLY from the selected activity, never inferred from telemetry) →
`Gt7LiveActivityAdapter.build_runtime_snapshot` maps them onto the canonical `LiveActivityRuntimeSnapshot`.
Unknown values stay unknown; a verified match is never inferred from missing data. `evaluate_freshness`
uses an INJECTED monotonic time (never the wall clock) and gates expiry only. `evaluate_live_runtime`
reuses the canonical Phase-55 classifier — **replay and live use the SAME match rules** — and computes
evidence progress. A real live tracker (which cannot produce the engineering context digest) yields the
honest `MATCH_WITH_LIMITATIONS`; `EXACT` requires the context digest, compound and run-plan all known.

## Runtime cadence & cache — `strategy/live_runtime_cache.py`

`runtime_cache_key` is an OPERATIONAL invalidation key (cycle/activity/setup/context/run-plan/session-end)
that EXCLUDES volatile live counters (lap/segment/fuel/speed) — a telemetry packet alone never
invalidates the cache, and the key is never an engineering fingerprint. `LiveEvaluationCadence` bounds
advisory re-evaluation: re-evaluate on force (explicit binding / stale→fresh), on key change, or when the
cadence interval elapses (injected monotonic time). Invalidate when the active event, selected activity,
setup fingerprint, event context, run plan changes, the session ends, telemetry becomes stale, or an
explicit binding occurs. Thread model: high-frequency ingestion (existing listener) → a single live
worker builds immutable snapshots → the UI renders; no DB read per packet; no rebuild of the Event
Preparation Cycle / Engineering Brain / strategy per packet.

## Session start/end — `strategy/live_runtime_authority.py`

`evaluate_runtime_transition` ties the immutable evaluation + the previous running flag to the canonical
Phase-55 session-end detector: NOT_SELECTED / STARTED / RUNNING / STALE / BLOCKED (hard mismatch
suppresses routine advisories) / ENDED_BINDING_REQUIRED / ENDED_INSUFFICIENT. A probable end freezes the
final snapshot and hands to explicit binding; `activity_completed` is ALWAYS False. A telemetry-dropout
end still permits binding when valid laps were collected before the dropout (a recoverable session).

## Tests

`test_phase57_adapter.py` (16), `test_phase57_cadence_cache.py` (6), `test_phase57_runtime_authority.py`
(10). These are STATIC runtime-snapshot tests (constructed snapshots) — not the replay timeline.
