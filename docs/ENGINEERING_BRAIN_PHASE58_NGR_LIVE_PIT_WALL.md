# Engineering Brain — Phase 58: Driver-Facing NGR Live Pit Wall

Program 2, Phase 58. Read-only, deterministic, offline, no AI. The driver-facing live experience for
Practice / Qualifying / Race. It assembles ONE coordinated NGR team message (never several competing
voices), changes no state, and issues no pit/tyre/fuel/setup command.

## Pit-wall domain — `strategy/ngr_live_pit_wall.py`

`build_ngr_live_pit_wall` assembles the strict low-density hierarchy: (1) NGR event + activity, (2)
objective, (3) context + setup match, (4) telemetry state, (5) a SINGLE advisory, (6) evidence progress,
(7) stop condition / next action, (8) voice status. `LivePitWallMode` is driven by the ACTIVITY TYPE (a
setup experiment developing the race setup is Practice-mode; a race simulation / official race is
Race-mode; qualifying / quali-sim is Qualifying-mode; session end → Transition; stale → Recovery). Purpose
notes respect the activity purpose (no mid-run setup-change encouragement; coaching shows one objective;
tyre/fuel tests promote no setup conclusion). The single advisory is SUPPRESSED on stale telemetry or a
blocked (hard mismatch) activity. `next_action` never contains an autonomous command.

## Integration — `strategy/live_pit_wall_integration.py`

- `derive_voice_status` — DISABLED by default; GATED below `VOICE_ELIGIBLE` (via
  `shadow_advisory.voice_gate_allows` — a UI button can NEVER manufacture ELIGIBLE); MUTED / ACTIVE /
  ADAPTER_FAILURE (visual fallback). Reuses the Phase-47 controller readiness.
- `coordinate_single_advisory` — ONE coordinated message (highest-priority DELIVERED decision,
  deterministic tie-break); empty when suppressed or nothing delivered.
- `resolve_garage_return` — explicit choices at session end (bind / review-with-limitations / abandon) and
  telemetry loss (resume / bind-recovered / replacement-run / review / mark-invalid / abandon); inactive
  while running. Never auto-binds, never auto-completes.

## Coordinated pit-wall roles

The UI may attribute evidence to Chief Engineer / Race Engineer / Performance / Strategy / Driver Coach /
Crew Chief — these are VIEWS over shared evidence, not independent agents. The driver receives one
coordinated communication stream.

## UI (post `/ui-ux-pro-max`)

`ui/ngr_live_pit_wall_vm.py` (Qt-free) + `ui/ngr_live_pit_wall_panel.py` render the 8-item hierarchy,
glanceable and high-contrast; the driving hierarchy is replaced by a transition/recovery card at session
end / telemetry loss. Hosted in the Development History surface for offscreen construction; the production
placement is the Live tab with a telemetry-driven off-thread refresh (the remaining live-UAT wiring).
Voice states shown: visual-only / disabled / gated / eligible / active / muted / adapter-failure.

## Tests

`test_phase58_pit_wall.py` (10), `test_phase58_pit_wall_ui.py` (5), `test_phase58_integration.py` (11).
