# Engineering Brain — Phase 66: Canonical Live Race-State Mapping

Program 2, Phase 66. Read-only, deterministic, offline, no AI. Builds the trustworthy adapter from the
existing `RaceStateTracker` + canonical local authorities into the Phase-65 Adaptive Strategy Brain —
**activating** the strategy runtime for real GT7 races. `strategy/canonical_live_race_state.py` (pure;
Qt-free, DB-free, no wall clock; never raises). Creates NO listener/socket/tracker.

## State composition

`build_canonical_live_race_state(tracker, …)` composes ONE immutable `CanonicalLiveRaceState` from a thin,
duck-typed read of the tracker (`race_type`, `laps_recorded`, `laps_in_race`, `timed_duration_minutes`,
`last_fuel`, `avg_fuel_per_lap`, `best_lap_ms`, `pit_stops_completed`, `laps_since_pit`, `tyre_age_laps`,
`in_pit`, `pit_state_confidence`, `last_position`, `tyre_compound`, `car_name`/`track`/`layout_id`) +
injected elapsed time + the pre-race plan (fuel/pace/pit-loss) + confirmed PTT driver reports. **No DB query
per packet** — event/plan context is resolved on invalidation (`LiveStrategyEvaluationContext`) and reused.
`to_live_strategy_state()` yields the Phase-65 `LiveStrategyState` the brain consumes.

## Race clock (`RaceClockState`)

- **Lap-count** (`RaceType.LAP`): current lap, scheduled laps (`laps_in_race`), `laps_remaining`, completed
  stops, required stops/tyre rules.
- **Time-certain** (`RaceType.TIMED`): race duration (`timed_duration_minutes`), injected elapsed,
  `remaining_s`, `expected_completed_laps` (`project_time_certain`), pit-stop time cost, and
  `additional_stop_changes_lapcount` (does +1 stop lose a completed lap?). Finishing-lap rules are
  configurable NGR event semantics (`finishing_lap_semantics`) — not all timed races share one end rule.

## Field-availability matrix

Every field carries `availability` (measured / derived / driver-reported / unavailable) + `confidence`.
**Unknown stays unknown.** GT7 provides no direct tyre condition (proxy only), weather, damage, penalties or
safety-car — these are UNAVAILABLE unless a confirmed PTT report supplies them (then driver-reported,
never verified telemetry). See `ENGINEERING_BRAIN_PHASE66_68_PREPHASE_AUDITS.md` (Audit A) for the full
matrix. Volatile control inputs (speed/throttle/brake/steering/gear) are workload-only and excluded from
the fingerprint.

## Fuel / pace / tyre models (robust)

- **Fuel:** compares planned vs live burn using a ROBUST multi-lap mean (drops the single most-extreme
  sample — one anomalous lap never drives the value), plus remaining fuel and expected-at-stop/finish.
- **Pace:** clean-lap MEDIAN (invalid/traffic/pit/out-laps excluded), plus consistency (stddev).
- **Tyre:** degradation is a labelled PROXY from lap-time drift across a stint (≥4 laps); `tyre_deg_is_proxy`
  is always True and the field's confidence is LOW — GT7 gives no direct tyre condition.

## Pit state

`PitState` (not-in-pit / pit-entry-suspected / pit-confirmed / pit-exit / stop-completed / uncertain) reuses
the tracker's `in_pit` + `pit_state_confidence`; a weak signal is `uncertain` and never increments the pit
count.

## Evaluation cadence

`EvaluationCadence.triggers(...)` fires strategy evaluation only at bounded triggers — lap completion,
confirmed pit event (a stop-count increment, never double-counted), material fuel/pace/tyre change,
remaining-time threshold, confirmed driver report, event-rule risk, explicit PTT request. **Never a full
recalculation per packet.**

## Production activation

`ui/dashboard.py` `_refresh_audio_engineer` now maps the REAL tracker into the canonical state when a live
Race is present, so the Live-tab strategy card leaves INSUFFICIENT_EVIDENCE with a valid feed — and stays
INSUFFICIENT where inputs are genuinely unavailable. Off the UI thread; DB-free; stale-worker guarded.

## Tests

`tests/test_phase66_live_race_state.py` (18) + `tests/test_phase66_68_safety.py` (metamorphic).
