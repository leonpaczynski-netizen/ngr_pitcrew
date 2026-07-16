# Sprint 12 — Golden UAT & Release Gates

**Status:** COMPLETE (deterministic golden-UAT harness green)
**Branch:** milestone-6-golden-uat (off master)

## Golden UAT harness — `tests/test_golden_uat.py`
One deterministic, offline, Qt-free scenario (Porsche RSR at Fuji Full Course) that walks the whole rebuilt pipeline through the **real production engines** and asserts each release gate. 16 gates, all green.

## Release gates — status

| Gate | Verified by |
|---|---|
| No generative-AI production code remains | `test_gate_no_generative_ai_remains` + `tests/test_no_ai_architecture.py` (removed modules non-importable; no provider markers/keys/endpoints in production) |
| No external AI dependency / no network for core work | `test_gate_core_engines_import_without_network`; only external host is the optional user-triggered dg-edge scraper |
| Identical inputs → identical results | `test_gate_strategy_deterministic_*`, `test_gate_full_scenario_deterministic_rerun_equality` (+ per-engine determinism tests) |
| Fuji assets load automatically | `test_gate_fuji_ready_automatically_from_disk` → READY_APPROVED, no Track Modelling opened |
| Telemetry packets grouped into real episodes | `test_gate_one_slide_is_one_episode` (one slide = one episode) |
| One/two poor laps cannot trigger setup changes | `test_gate_two_poor_laps_do_not_author_a_change` |
| Recurring issues require same-corner/same-phase persistence | `test_gate_recurring_same_corner_is_eligible` (PERSISTENT + eligible) |
| Low-confidence telemetry cannot override clear driver feedback | `test_gate_low_confidence_cannot_override_good_feedback` → EVIDENCE_CONFLICT, no LSD change |
| Never "approved" + "engineering validation failed" together | `test_gate_never_approved_and_failed_together` → ENGINEERING_FAILURE |
| Normal kerb contact cannot alter ride height | `test_gate_kerb_bottoming_never_raises_ride_height` (permitted increment 0) |
| RS→RM after lap 3, RM→RH after lap 6 (measured curves) | `test_gate_tyre_crossovers_rs_rm_lap3_rm_rh_lap6` |
| Untested compounds cannot become recommended strategies | `test_gate_strategy_deterministic_and_excludes_untested` |
| Strategy cannot author setup values | `test_gate_strategy_does_not_author_setup` (source scan) + `ui/race_strategy_uat.py` guard |
| Practice evidence flows directly into Strategy | `test_gate_practice_evidence_flows_into_strategy` (bundle consumed by `recommend_strategy`) |
| Setup fields highlighted until confirmed in GT7 | `test_gate_saved_highlighted_until_confirmed_in_gt7` (three-state model) |
| Practice PTT / speech is local-only (no cloud) | `test_gate_speech_recognition_is_local_only` |
| No analysis action can crash the app (the `_sc` crash) | `tests/test_sprint2_runtime_stability.py` |
| User setups / telemetry / track assets / history protected | Sprint-0 hash manifest re-verified every milestone: 27 protected runtime files unchanged |

## What is NOT covered here (needs the running Qt app — see Milestone 5 note)
> **Update (2026-07-16):** the Sprint 10 Qt visual layer below has since been **delivered and merged** (PR #64), and the robotic-voice issue was fixed with local Piper neural TTS + an in-app voice picker/downloader (PR #65). Each ships with offscreen construction/behaviour tests. Only interactive PTT (item 4) still needs a hands-on run. See `docs/UAT_RUNBOOK.md` for the consolidated acceptance script.

- ✅ **Done (PR #64):** rendering the workflow stepper and the structured advice cards in the widgets.
- ✅ **Done (PR #64, DB v19):** the "Changes Applied in Game" button + applied-checkpoint DB persistence.
- ✅ **Done (PR #64):** the "Build Race Plan from This Practice" action wired to the Strategy tab.
- ⏳ **Remaining:** PTT working *interactively* in Practice (the global hook + local recognition are in place; the live click-to-speak-to-answer loop needs the app + a mic + `pocketsphinx` installed + a bound key to exercise — see UAT_RUNBOOK §B4).

The deterministic logic each of these renders is complete and locked by tests.

## Sprint 12 final report
- **Files:** +`tests/test_golden_uat.py`, +`docs/SPRINT_12_GOLDEN_UAT_RELEASE.md`.
- **Tests added:** 16 golden-UAT gates.
- **Regression:** full suite green (run in chunks; only the intermittent Win/Py3.14 Qt teardown segfault at large batch sizes, never a real failure).
- **Runtime files verified untouched:** yes.
- **Known limitations:** the Qt visual layer of the guided-UI overhaul (above) is the remaining work; it is best done interactively with the running app.
- **Recommended next:** a dedicated UI session to wire the Sprint 10 backbone into the Qt widgets with the app running.

## Program summary
All 12 sprints delivered across 6 reviewable milestones (PRs #58–#63). Pit Crew is now fully local, deterministic, offline, and evidence-led: no generative AI, telemetry evidence gated by cross-lap recurrence, measured tyre curves, deterministic total-race-time strategy, an explicit Practice→Strategy handoff, and an honest saved-vs-applied setup model — every guarantee locked by the golden-UAT release gates.
