# Engineering Brain — Phase 50: Immersive NGR Race Weekend

Program 2, Phase 50. Read-only, deterministic, offline, no AI. The official race weekend is the CLIMAX
of the preparation cycle — built FROM the accumulated Practice evidence, never rebuilt from scratch on
arrival. Issues no automatic pit/tyre/fuel command; voice is disabled by default and may not bypass the
`VOICE_ELIGIBLE` gate.

## Module — `strategy/race_weekend.py`

- `RaceWeekendPhase` (13): final_arrival → driver_briefing → garage_readiness →
  final_engineering_meeting → official_practice → qualifying_prep → qualifying → qualifying_review →
  race_strategy_confirmation → grid_readiness → race → post_race_debrief → event_complete.
- **FinalArrivalSummary** — draws sessions/valid-laps/setup+driver-dev/tyre+fuel+strategy confidence/
  quali+race setup fingerprints/unresolved risks/blockers/next action from the accumulated programme.
- **DriverBriefing** + `acknowledge_briefing` — only event-applicable rules (never fabricated); requires
  explicit acknowledgement; acknowledgement is runtime state (excluded from the fingerprint).
- **VirtualScrutineering** — aggregates checks to `CLEARED` / `CLEARED_WITH_WARNINGS` / `GARAGE_HOLD` /
  `UNVERIFIABLE` / `NOT_APPLICABLE`; unverifiable checks are not fabricated (any FAIL → hold; else any
  UNVERIFIABLE → unverifiable; else any WARN → warnings; else all N/A → not-applicable; else cleared).
- **ChiefEngineerFinalMeeting** — one coherent plan; quali/race setups separate; voice state surfaced.
- **QualifyingExperience** (deliberately low-density) + **QualifyingReview** (grid/sector/corner/
  reconsideration flags/post-quali restrictions).
- **RaceBriefing** + `acknowledge_race_briefing` — explicit strategy acknowledgement + grid-ready
  confirmation (grid-ready requires acknowledgement first).
- **RaceRuntimeProfile** — fixed safety-first priority order (`safety`, `setup_or_context_mismatch`,
  `car_condition`, `race_plan_status`, `tyre_and_fuel_awareness`, `pit_window_awareness`,
  `strategy_viability`, `restrained_coaching`, `information_progress`); `issues_pit_commands` always
  False; voice disabled by default, gated by `voice_eligible`. Reuses (references, never re-implements)
  `live_advisory_engine`, `shadow_advisory`, `voice_controller`.
- **PostRaceDebrief** — result/pace/tyre/fuel/strategy/incidents/penalties/setup+driver/decisions/
  promotion-rollback/lessons — carries confirmed learning forward through the existing canonical
  authorities.

## UI (post `/ui-ux-pro-max` design gate)

Pure Qt-free view-models `ui/event_preparation_vm.py` + `ui/race_weekend_vm.py`; panels
`ui/event_preparation_panel.py` (banner + horizontal preparation timeline strip using actual
activities/dates + progress/convergence/strategy/readiness cards) + `ui/race_weekend_panel.py`. Both are
read-only, dict-driven (`update_result`), with no Apply/lock/finalise control, and reuse the NGR theme
tokens (`card_qss`, `banner_qss`, `heading_qss`, status tones, advisory tint). Meaning is always carried
by a text tag + tone, never colour alone. Wired into the Development History page with
`update_event_preparation` / `update_race_weekend` forwarders. Design decisions (adopted vs. rejected)
are recorded in `UAT_ENGINEERING_BRAIN_PHASE48_50.md` and the completion report.

## Future NGR League Hub boundary — `strategy/ngr_event_manifest.py`

Contract only: `NgrEventManifest` (immutable local snapshot), `NgrEventManifestVersion`,
`NgrEventRevision`, `NgrEventManifestValidation`, `NgrEventImportPort` / `OfflineNgrEventImportPort`,
`NgrRegisteredDriverReference`. No API, no network, no authentication, no automatic import. A revision
diff flags whether prior evidence stays compatible but never rewrites completed history; the fingerprint
excludes the revision number. Offline manual creation is never removed; the Hub is never required.

## Tests

`test_phase50_race_weekend.py` (15); UI `test_phase48_50_ui.py` (6); Hub `test_phase48_50_hub_manifest.py`
(8); golden `test_phase48_50_golden.py` (12); safety `test_phase48_50_safety.py` (9).
