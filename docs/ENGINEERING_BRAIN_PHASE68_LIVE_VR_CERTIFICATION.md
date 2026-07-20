# Engineering Brain — Phase 68: Live GT7, PSVR2 & Adaptive-Strategy Certification

Program 2, Phase 68. Read-only, deterministic, offline, no AI. Certifies the full Phase 66–68 VR
race-engineer workflow honestly and records defect remediation. Adds no unrelated breadth.

## Per-area certification — `strategy/event_programme_certification.py` (extended)

`LIVE_VR_CERTIFICATION_AREAS` = the **31** areas of the workflow. `live_vr_certification()`:

- **AUTOMATED** (deterministic domain, proven by unit/property tests): real-tracker mapping, race clock,
  fuel burn, pace divergence, tyre proxy, pit detection, lap-count strategy, time-certain strategy, revised
  candidate ranking, command grammar, read-back, driver-report confirmation, workload-aware delivery,
  TTS/PTT coordination, telemetry loss, repeated replanning, revised-plan acknowledgement.
- **OFFSCREEN**: Live-tab strategy card, visual fallback.
- **NONE + required-next-evidence** (never grantable headlessly): physical TTS, keyboard/controller/wheel
  PTT, microphone recognition, device failure, PSVR2 Practice/Qualifying/Race, session binding, debrief,
  cumulative learning.

Overall = **NOT_TESTED**, bounded by the untested live/physical areas. **Per-area and overall are shown
separately** (in the UI VM). The 10-level hierarchy is unchanged (NOT_TESTED → AUTOMATED_ONLY →
OFFSCREEN_VALIDATED → REPLAY_VALIDATED → VISUAL_UAT_PARTIAL/VALIDATED → LIVE_GT7_PARTIAL/VALIDATED →
OPERATIONALLY_READY_WITH_LIMITATIONS → OPERATIONALLY_READY), with the strict evidence caps.

## Not awarded from automated substitutes

Physical voice from fake adapters; microphone from grammar unit tests; PTT without a physical control;
PSVR2 without using PSVR2; live strategy from static snapshots; operational readiness while critical audio
or strategy paths remain untested. `effective_level` for every NONE area is NOT_TESTED.

## Strategy UAT scenarios (validated at the domain/unit level)

Baseline-valid (no spam), fuel higher/lower than forecast, pace slower/faster, tyre earlier/later,
time-certain extra-stop-loses-a-lap (rejected) / gains-a-lap (allowed with assumptions), driver-reported
rain/damage (stays driver-reported), telemetry dropout (no high-confidence replan), confirmed pit (updated
once, never double-counted). Each material update speaks: what changed → why → revised recommendation →
expected gain/avoided loss → confidence → next review trigger (concise headline; detail visual).

## Recommendation vs execution

The engineer may recommend an earlier/later pit window, stopping this lap, extending/shortening a stint,
saving fuel, increasing pace, changing the fuel target or tyre, adding/removing a stop. **All remain
advisory** — acknowledgement executes nothing in GT7.

## Defect remediation (this slice)

1. **Time-certain ranking** upgraded from `(-laps, stop_delta, label)` to the full Audit-B hierarchy
   (max completed laps → finishing position → total time → pit-loss exposure → legal-completion confidence →
   fuel-at-finish margin → fragility → stable label). Regression: `test_equal_lap_candidates_use_meaningful_
   tiebreak_not_id`, `test_label_is_only_final_tiebreak`.
2. **Uncertain recognition labelling** — an ambiguous (UNRECOGNISED) utterance no longer carries a driver-
   report label; only a non-ambiguous DRIVER_REPORT is labelled. Regression:
   `test_uncertain_recognition_cannot_update_race_state`.
3. **PTT lifecycle enum** extended (pressed/recognised/ambiguous/failed) to cover the full spec lifecycle.

## Tests

`tests/test_phase68_certification.py` (7) + the metamorphic suite in `tests/test_phase66_68_safety.py`.
