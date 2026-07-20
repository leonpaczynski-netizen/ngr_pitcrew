# Engineering Brain — Phase 60: Production Live-Tab Activation

Program 2, Phase 60. Read-only, deterministic, offline, no AI. Moves the NGR Live Pit Wall from a
development surface into the real driver-facing Live tab, fed by the existing telemetry pipeline.

## Production pipeline & thread model

`UDPListener → RaceStateTracker → normalised TrackerRuntimeSnapshot → GT7 live adapter → canonical live
snapshot → pit-wall view model → Live-tab UI`. **No new listener / socket / packet parser / polling loop.**

| Stage | Thread |
| --- | --- |
| telemetry listener (`UDPListener`) / tracker update (`RaceStateTracker`) | existing daemon thread |
| normalised snapshot + adapter + match + pit-wall build | **live worker off the UI thread** (`MechanismAnnotationWorker`) |
| render | UI thread (`_on_live_pit_wall_ready`) |
| stale-result protection | drop stale worker + a result for a previously-selected (event, activity) |
| shutdown | controller shutdown; no duplicate consumers |

`ui/dashboard.py`: `_build_tracker_runtime_snapshot` reads the tracker into an immutable snapshot (thin
read; unknown fields empty); `_refresh_live_pit_wall` runs `build_live_pit_wall_view` off the UI thread;
`_on_live_pit_wall_ready` renders and drops stale/event-switched results. `strategy/live_pit_wall_build.py`
(`build_live_pit_wall_view`) is DB-FREE — no query, no write per packet; the activity context is resolved
once on invalidation.

## Runtime context resolution (Audit B remediation) — `strategy/runtime_context_resolution.py`

Composes the live context digest from resolved canonical local state (car + track + layout confirmed with
sufficient map-match confidence → the live digest is set to the expected event-context digest, a
legitimate composition, not fabricated telemetry). An EXACT match becomes possible when the context is
confirmed AND the applied-setup fingerprint (a LOCAL PROXY from `ActiveSetupAuthority` — GT7 does not
broadcast the setup) matches the expected one, and compound + run-plan are known. Honest limitations are
preserved (proxy setup fingerprint; low map-match keeps the layout limited).

## Controller state machine — `strategy/live_pit_wall_controller.py`

`LivePitWallRuntimeState` (15) + `LivePitWallNavigationContext` (operational nav; **opening Live never
starts the activity** — `started` requires an explicit action) + `reduce_live_state`: production state
(no-active-event / no-selected-activity / awaiting-start / starting / exact-match / limited-match /
hard-mismatch / live / telemetry-stale / telemetry-lost / binding-required / review / abandoned /
returning). `UNVERIFIABLE` → `LIMITED_MATCH`; a stale-derived end → `TELEMETRY_LOST` (recoverable); a
clean end → `BINDING_REQUIRED`. Refresh never completes the activity.

## Production placement (post `/ui-ux-pro-max`)

The `NgrLivePitWallPanel` is the FIRST widget of the Live tab (the primary driver surface); the existing
telemetry + track-map panels remain below it (reused, not duplicated — the pit wall consumes the existing
map-match confidence). The Development History diagnostic panel is retained as a developer surface, not
the driver surface. The live QTimer cadence is deferred to live UAT; the refresh fires on Live-tab
activation.

## Tests

`test_phase60_context_and_controller.py` (17), `test_phase60_live_worker.py` (6),
`test_phase60_live_tab_integration.py` (4).
