# Engineering Brain — Phases 69–71 Pre-Phase Audits (UAT Activation Gate)

Performed on branch `eng-brain-phase69-71-uat-activation-gate`, created from clean **`master @ 1f4545c`**
(the PR #76 merge commit — Engineering Brain Programs 1 & 2 through Phase 68). Additive only — no earlier
commit is amended. Phases 69–71 are **pre-UAT activation, not operational certification**: they make the
merged Phase-68 production paths observable, deterministically testable and safely gated for physical UAT.
No new intelligence, strategy, setup, telemetry or voice features are introduced.

## Checkpoint (verified before any change)

| # | Check | Result |
|---|-------|--------|
| 1 | Start branch | was `master` (switched off the merged `…phase66-68` branch) |
| 2 | HEAD | `1f4545c` (PR #76 merge) |
| 3 | `master` vs `origin/master` | both `1f4545c` (synchronised) |
| 4 | Working tree | only pre-existing runtime/app-state files (untracked + 3 modified data files) |
| 5 | Pre-existing runtime files | `.claude/settings.local.json`, `data/setup_history.json`, `…accepted_model.json` (M); `active_setup_state.json`, `…candidate_model.json`, `…candidate_reference_path.json`, `…refinement_ledger.jsonl`, `…__lap_offset.json`, `…__reviewed_segments…json`, `data/track_library/tracks/fuji…/`, `data/track_models/_refine_pending/` (untracked) |
| 6 | `DB_VERSION` | `28` (`strategy/_setup_constants.py:132`) |
| 7 | `RULE_ENGINE_VERSION` | `"46.0"` (`strategy/_setup_constants.py:79`) |
| 8 | Phase 63–68 modules + tests | present (`strategy/{audio_first_engineer,push_to_talk,adaptive_live_strategy,canonical_live_race_state}.py`, `voice/ptt_runtime_controller.py`, `strategy/event_programme_certification.py`; `tests/test_phase6[3-8]_*`) |
| 9 | Canonical mapping | `strategy/canonical_live_race_state.py` = the sole `RaceStateTracker → LiveStrategyState` path |
| 10 | Dashboard consumes canonical path | yes (`ui/dashboard.py:995,1016` in `_refresh_audio_engineer`) |
| 11 | Phase 67 Windows voice/PTT adapters | present (`voice/{windows_sapi_recognition,keyboard_ptt,joystick_ptt,piper_tts}.py`) behind the existing ports |
| 12 | `live_vr_certification()` areas | **31** separate `CertificationArea` |
| 13 | Physical areas / overall | physical_tts / keyboard_ptt / controller_ptt / wheel_ptt / microphone_recognition / device_failure / psvr2_* / session_binding / debrief / cumulative_learning = **NONE**; overall = **`NOT_TESTED`** |
| 14 | Duplicate listener | none — sole listener `telemetry/listener.py` (UDPListener); `diagnose.py` is a standalone unimported debug script |
| 15 | Runtime files unmodified | yes (hashes recorded; see completion report) |
| 16 | Inherited regression | **10,277 passed / 27 skipped / 0 failed** (10,304 collected — matches `pytest --collect-only`) |

No checkpoint materially differs. Implementation proceeds.

## Audit A — End-to-end production path (`RaceStateTracker` → surfaces)

The single live path, traced from the tracker to every surface:

```
telemetry/listener.py (UDPListener, sole socket)
  → telemetry/state.py RaceStateTracker (the only calculator)
  → strategy/canonical_live_race_state.build_canonical_live_race_state(tracker, …)   [thin duck-typed read]
  → CanonicalLiveRaceState  (availability matrix: MEASURED / DERIVED / DRIVER_REPORTED / UNAVAILABLE)
  → .to_live_strategy_state() → strategy/adaptive_live_strategy.LiveStrategyState
  → decide_replan() → StrategyReplanDecision (+ generate/rank candidates, time-certain Audit-B hierarchy)
  → strategy/live_audio_strategy_build.build_live_audio_strategy_view(…)
        · resolve_audio_engineer_state (audio-first composite state + readiness)
        · assess_driver_workload → decide_engineer_speech (priority × workload × window × budget)
        · build_strategy_driver_message (concise audio-first headline)
  → dashboard._refresh_audio_engineer (OFF the Qt thread via MechanismAnnotationWorker; stale-guarded)
  → ui/vr_audio_engineer_panel (visual fallback) + ui/ngr_live_pit_wall_panel (Live tab)
  → voice/ptt_runtime_controller (PTT lifecycle; mic gated to PTT-held; grammar classify; read-back)
  → strategy/event_programme_certification.live_vr_certification() (honest 31-area cert)
```

Findings:

- **No duplicate calculation.** Fuel (`avg_fuel_per_lap` / robust median of samples), pace (best-lap or
  clean-lap median), lap count (`laps_recorded`), pit (`in_pit` / `pit_stops_completed`) are read from the
  tracker; the canonical adapter derives clock/stint/tyre-proxy but never re-implements tracker maths. The UI
  renders finished dicts only — no business logic in a panel.
- **Honest unknowns.** Tyre condition is a labelled **proxy** (`tyre_deg_is_proxy=True`, availability
  `DERIVED`, confidence `LOW`); weather/damage/penalty are `UNAVAILABLE` unless a **confirmed** PTT report
  supplies them (then `DRIVER_REPORTED`, never verified). Missing fuel/clock/pit/tyre stay unknown — no safe
  default. `decide_replan` returns `INSUFFICIENT_EVIDENCE` when inputs or telemetry freshness are missing.
- **Bounded refresh.** `EvaluationCadence` and `StrategyMonitor` (cooldown + fingerprint dedup) gate
  evaluation/announcements — never per-packet. Timing is injected (monotonic seconds), so it is deterministic
  and thread-affinity-free; the heavy build runs off the Qt thread with a stale-worker guard.
- **Defect / limitation identified (not a bug):** the dashboard reads the *richer* strategy-context caches
  (`_live_race_elapsed_s`, `_live_fuel_plan`, `_live_pace_plan_s`, `_live_fuel_samples`,
  `_live_clean_lap_times`, `_live_pit_loss_s`, `_live_driver_reports`) via `getattr(self, …, None)`, and
  **no writer populates them** (confirmed by source grep). They are honest forward hooks — the canonical
  adapter reads them as `None`, so with a bare tracker feed the panel correctly stays at
  `INSUFFICIENT_EVIDENCE`/`PLAN_STILL_OPTIMAL`. Phase 69's runtime snapshot records these as
  explicitly-absent so a diagnostician sees *why* the strategy is quiet, rather than mistaking silence for a
  fault. No behavioural change is warranted.
- **Where unknown could become certainty:** none found on the live path. The only place a report could gain
  authority is `apply_readback_response` (CONFIRM → `confirmed_by_readback`, still not telemetry) and
  `label_driver_report_against_telemetry` (corroborated only when telemetry is available AND agrees). Both
  are conservative.

## Audit B — Session lifecycle

Traced: app start (no telemetry) → first packet → session identify → session/event change → Practice→Qual→
Race transitions → pit entry/stop/exit → lap rollover → race completion → telemetry loss → reconnect →
shutdown.

- The tracker owns lap/fuel/pit/pace state and is reset by `_on_reset_clicked → tracker.reset()`;
  `_on_live_mode_changed` opens a new DB session and re-targets the tracker session type.
- The Phase 63–68 runtime helpers are **stateful across packets**: `EvaluationCadence` (`_last_lap`,
  `_last_pit_stops`), `StrategyMonitor` (`_last_fp`, `_last_at`) and `PttRuntimeController`
  (`_was_pressed`, `_state`). They are **not currently instantiated as long-lived dashboard members** on the
  live path (the panel rebuild is stateless per refresh), so there is no *current* leak — but Phase 69 will
  formalise a single reset seam so that when these are activated they cannot inherit a prior session's lap
  counter, pit count, cooldown fingerprint or pending recognition. Persistent, legitimately event-scoped
  engineering knowledge (DB records, Event Prep cycle) is written only through existing authorities and must
  **not** be cleared by a live reset.
- Stale-result protection already exists: both `_on_live_pit_wall_ready` and `_on_audio_engineer_ready` drop
  a worker whose `nav_key` (cycle_id, activity_id) no longer matches the current selection.
- `is_stale_recognition(nav_key, current_nav_key)` rejects a PTT utterance recognised before an event/
  activity switch — the correct anti-leak for voice.

Phase 69.3 therefore *verifies* and *formalises* (does not rewrite) reset: one pure `SessionResetPlan` +
dashboard seam that clears exactly the transient live-runtime keys, preserving persistent knowledge.

## Audit C — Offline / bench testability (the narrow seam)

The narrowest legal injection seam is the **duck-typed tracker read** consumed by
`build_canonical_live_race_state(tracker, …)`. Every downstream authority (canonical mapping →
`LiveStrategyState` → `decide_replan`/`rank_candidates` → `build_live_audio_strategy_view` →
`live_vr_certification`) is a **pure function of that state plus injected scalars** (elapsed, plan, samples,
pit-loss, driver reports, workload context). A bench scenario therefore constructs a lightweight immutable
**data holder** exposing the tracker's read attributes (`race_type`, `laps_recorded`, `laps_in_race`,
`timed_duration_minutes`, `last_fuel`, `avg_fuel_per_lap`, `best_lap_ms`, `tyre_compound`, `laps_since_pit`,
`tyre_age_laps`, `in_pit`, `pit_state_confidence`, `pit_stops_completed`, `last_position`, `car_name`,
`track`, `layout_id`) and feeds the **real production functions**. It copies **no** algorithm. This exercises
the full path with zero network, zero listener, zero device I/O.

## Audit D — Physical certification truth

Every Phase-68 area classified against what can legitimately test it:

| Class | Areas |
|-------|-------|
| Automatically / bench testable (software) | real_tracker_mapping, race_clock, fuel_burn, pace_divergence, tyre_proxy, pit_detection, lap_count_strategy, time_certain_strategy, revised_candidate_ranking, command_grammar, read_back, driver_report_confirmation, workload_aware_delivery, tts_ptt_coordination, telemetry_loss, repeated_replanning, revised_plan_acknowledgement |
| Offscreen (UI construction) | live_tab_strategy_card, visual_fallback |
| Physical-device only | physical_tts, keyboard_ptt, controller_ptt, wheel_ptt, microphone_recognition, device_failure |
| PSVR2 only | psvr2_practice, psvr2_qualifying, psvr2_race |
| Live-GT7 only | session_binding, debrief, cumulative_learning |

`live_vr_certification()` hard-codes the physical/live areas to `EvidenceType.NONE` and the offscreen areas to
`OFFSCREEN`; `build_event_programme_certification` bounds the overall level by the weakest area
(`_EVIDENCE_MAX`: `AUTOMATED → automated_only`, `OFFSCREEN → offscreen_validated`, `NONE → not_tested`) and
withholds `operationally_ready` unless a human grant AND every area at a live level AND no blocker. **No unit
test or object construction can promote a physical area to PASS.** Phase 71's readiness evaluator and bench
harness both inherit and re-assert this: bench passes only ever touch software areas, and
`OPERATIONALLY_CERTIFIED` is unreachable while any required physical/live area is untested.

## Consequences for Phases 69–71

1. **Phase 69** adds one pure `LiveUatRuntimeSnapshot` + read-only builder over the real objects, formalises
   the session-reset seam, and adds a read-only UAT diagnostics surface on the existing developer/UAT page.
2. **Phase 70** adds a deterministic bench harness that injects state at the Audit-C seam and reuses every
   production authority; 67 scenarios; deterministic aggregate report; software-only certification effects.
3. **Phase 71** adds manual UAT evidence (explicit user entry, never auto-PASS), a release-candidate manifest,
   and a pure readiness evaluator that can never output `OPERATIONALLY_CERTIFIED` from software evidence.
