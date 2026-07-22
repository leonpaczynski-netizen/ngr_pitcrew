# NGR Pit Crew — UI Rebuild Completion Report

**Branch:** `ui-rebuild-ngr-pit-crew`
**Base:** master `d79a5eb`
**Status at time of writing:** Display layer + live-data bridge + cutover complete on the branch; live-rig verification and full physical UAT outstanding (see Known Limitations).

---

## 1. Verified starting branch & commit
- Started from working branch `uat-defect-073-navigation-and-home-state` @ `ec486eb` (already merged to `origin/master`).
- True master fetched: `d79a5eb`. Local `master` fast-forwarded to it; fresh branch `ui-rebuild-ngr-pit-crew` cut from `d79a5eb`.

## 2. Ending branch & commit
- `ui-rebuild-ngr-pit-crew`, 37 commits (see §23).

## 3–4. Feature Factory / UI-UX Pro Max output
- Decomposition into F0–F9 with acceptance criteria and dependency order (`docs/NGR_PIT_CREW_UI_REBUILD_PLAN.md`).
- Design system: OLED-dark operations-console, NGR brand-locked (green accent, Segoe UI, tabular figures), status = colour+icon+text. The engine's blue/Orbitron default was rejected per brand (`docs/NGR_PIT_CREW_UI_ARCHITECTURE.md`).

## 5. Current-state problems identified
Flat 13-tab dashboard, fragmented state, setup renderer-vs-plan divergence, live panels refreshing only on tab-activation, buried guidance/debrief, the 3-panel setup maze, ~12 hidden-logic sites. (Full: `docs/NGR_PIT_CREW_UI_AUDIT.md`.)

## 6–8. New IA / event workflow / pages
Persistent shell (nav rail · event header · progress rail · guided-action column) + the guided journey: **Home · Active Event · Garage · Practice · Qualifying · Race Strategy · Live Pit Wall · Debrief · Engineering Library · Settings**.

New pages/components (all in `ui/components/` + `ui/pit_crew_shell.py`):
- Shell chrome: `NavRail`, `EventHeaderBar`, `ProgressRail`, `EngineerGuidanceCard`(+VM), atoms (`StatusPill`, `ConfidenceMeter`, buttons, `Card`).
- Garage: `SetupWorkspace` (discipline selector + Changed fields / **GT7 full setup sheet** / Lineage / Compare), `gt7_settings_sheet`, `setup_lineage`, `setup_comparison`, gearbox objectives.
- Practice: `run_card`, `practice_feedback` (structured), `practice_outcome` (verdict + adaptive action).
- `qualifying_readiness`, `strategy_plan`, `live_pit_wall`, `debrief_view`, `engineering_library`.
- Spine: `ui/app_state.py`, `ui/pit_crew_controller.py`, `ui/live_shell_bridge.py`, `ui/new_shell_launch.py`.

## 9. Existing components retired / demoted
- Classic `MainWindow` is no longer the front surface (still constructed; hosts backend + services the bridge reads). Reachable via Settings → "Open classic tools & settings".
- (Full retirement of the classic editable surfaces — Setup Builder form, Track Modelling, Event Planner — is deferred; see Known Limitations.)

## 10. Domain services reused (unchanged)
`strategy/*` (driving_advisor, setup_ranges, setup_recommendation, setup_lineage, setup_strategy_readiness, race_strategy_*, canonical_live_race_state, event_command_centre, gearbox_*), `data/*` (event/session/strategy contexts, session_db builders, setup_state_authority, applied_checkpoint, setup_transcribe), `telemetry/*`, `voice/*`. **No engineering logic was added to the UI.**

## 11. Business logic moved out of UI
`strategy/setup_feedback_evidence.py` (from dashboard.py), `strategy/gearbox_objectives.py`. `SetupRecommendationVM.applied_field_values()` unifies shown==applied.

## 12–17. Workflow improvements
- **Setup:** single workspace, discipline selector (maze removed), lineage tree, comparison, GT7 full sheet, shown==applied.
- **Practice:** run card → structured review (worse-prominent) → outcome (verdict + adaptive Keep/Revert/Refine).
- **Qualifying:** readiness checklist, Soft-tyres, Begin gated on blockers.
- **Strategy:** recommended+alternatives, measured-vs-assumed, replan triggers, **no setup-apply (safety-tested)**.
- **Live:** glanceable KPI tiles, freshness + map-trust always shown, advisory-only (safety-tested).
- **Debrief:** improved/regressed prominent, predictions, carry-forward, state-based action.

## 18. Accessibility
Colour+icon+text status (never colour-only); visible NGR-green focus rings; keyboard-navigable controls; tabular figures; reduced-motion-friendly (no essential motion).

## 19. Performance
`AppState` immutable + single controller broadcast (no per-widget polling); bridge refresh throttled (750 ms) + signal-driven; `LivePitWall.set_state` cheap for per-frame use; heavy geometry kept off the packet path.

## 20–22. Files added / modified / removed
- **Added:** `ui/app_state.py`, `ui/pit_crew_controller.py`, `ui/pit_crew_shell.py`, `ui/new_shell_launch.py`, `ui/live_shell_bridge.py`, `ui/components/*` (13 modules), `strategy/setup_feedback_evidence.py`, `strategy/gearbox_objectives.py`, `preview_new_shell.py`, `run_new_shell_preview.bat`, `docs/NGR_PIT_CREW_UI_*.md`, `tests/test_*` (23 new files).
- **Modified:** `ui/dashboard.py` (import extraction), `ui/ngr_theme.py` (additive tokens), `ui/setup_recommendation_vm.py` (`applied_field_values`), `ui/setup_builder_ui.py` (`current_recommendation_vm`), `main.py` (launch flag + cutover).
- **Removed:** none yet (dead-path removal deferred to full classic retirement).

## 24–25. Test results / regression
- **New UI-rebuild tests: 182 passed together, 0 failed.**
- **Full batched regression: 9,945 passed, 0 rebuild-caused failures.** One batch crashed and one test reported "failed" — both are the **pre-existing Win/Py3.14 PyQt segfault** hitting `EventCommandCentrePanel` construction under pytest. **Confirmed by running the exact test on clean master `d79a5eb` in an isolated worktree: it crashes identically there** (the panel constructs fine outside pytest; my changes are not in its import/execution path). No golden fixtures were edited. **No test failure is attributable to the rebuild.**

## 26. Safety verification
Safety tests assert: the strategy surface exposes no setup-apply control; the live surface issues no pit/fuel/strategy command; Garage Apply routes only through the classic gated path; `applied_field_values()` == displayed rows (shown==applied). Deterministic functionality requires no API key.

## 27–28. DB / rule-engine version
`DB_VERSION` = **28** (unchanged). `RULE_ENGINE_VERSION` = **"46.0"** (unchanged). UI-only; no schema/rule change.

## 29. Runtime files
User runtime data (`data/*`, `active_setup_state.json`, `config.json`) **untouched**; config-safety guardrail green.

## 30–31. Manual / physical UAT status
`docs/NGR_PIT_CREW_UI_REBUILD_UAT.md` authored; desktop cases runnable, **physical/live-GT7/PSVR2/voice/PTT cases remain NOT TESTED**.

## 32. Known limitations (updated after live wiring)
**Now genuinely live** — `LiveShellBridge` feeds every surface from its canonical service each refresh (Home guidance, Garage setup+recommendation, Practice run card, Qualifying readiness, Race Strategy plan, Live Pit Wall from canonical live state, Debrief from cross-session memory) and routes **every** action to real behaviour (Analyse/Apply/Revert, Settings save, run Start, feedback persist, outcome keep/revert/refine, Qualifying Begin, Strategy Approve, Debrief next-action, Library→classic panel, guidance Read-aloud). Adapters in `ui/shell_feed_adapters.py`; 207 new UI tests green.

Remaining, honestly:
- **Needs live-rig sanity check (data mappings + write path):** the feed adapters map documented service shapes and the action handlers try the real method names defensively, but end-to-end behaviour against a real GT7 session / populated DB is unverified here. Verify during UAT: Garage Apply persists to the car; feedback/read-aloud call the real methods; the mapped fields read correctly.
- **Practice Outcome verdict** is not yet fed from the post-run telemetry-vs-feedback reconciliation (that runs in the classic review flow); it stays empty until a real review exists.
- **Race Strategy** populates once a race plan has been built (`window._last_race_plan_result`); a native "Build plan" trigger is not yet added.
- **Editable classic surfaces** — Setup Builder *manual field editing*, Track Modelling, Event Planner — remain classic (reachable via Settings → Advanced). Everyday config (Settings) and running the setup brain (Garage → Analyse) are native.
- Full-suite regression can't be run green in one process here (pre-existing segfault); validated in batches.

## 33. Deferred items
Full classic-surface rebuild + retirement; live-rig verification of Apply-to-car; per-frame live telemetry wiring of the Live Pit Wall from `canonical_live_race_state`; lineage/comparison fed from real DB experiments; golden-fixture-free full regression.

## 34. Recommended next action
Run `python preview_new_shell.py` (safe, sample data) to review; then, off-race-weekend, launch the real app (`python main.py`, new shell is now default) and verify the live bridge against a GT7 session — confirm the Garage shows your real setup and that Apply persists — before merging to master.
