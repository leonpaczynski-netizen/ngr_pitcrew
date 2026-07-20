# Engineering Brain — Phases 69–71: Pre-UAT Activation, Bench Certification & Manual Evidence Gate

Branch `eng-brain-phase69-71-uat-activation-gate`, from clean **`master @ 1f4545c`** (PR #76 merge, Programs
1 & 2 through Phase 68). **These phases are pre-UAT activation, NOT operational certification.** They make
the merged Phase-68 production paths observable, deterministically testable and safely gated for physical
UAT. No new intelligence, strategy, setup, telemetry or voice feature is introduced.

> **Honesty statement (mandatory).** Automated and bench tests certify SOFTWARE behaviour only. They do NOT
> certify the physical microphone, wheel/keyboard PTT, physical TTS, PSVR2 or live GT7. Those remain
> **untested** until the user records real UAT evidence. No new UDP/telemetry listener was introduced (the
> sole listener remains `telemetry/listener.py`). No automatic pit call, tyre/fuel change, driver/game
> command or setup Apply capability exists anywhere in this slice. `DB_VERSION` stays **28**;
> `RULE_ENGINE_VERSION` stays **46.0**; no schema change.

## What landed

| Phase | Adds | Key modules |
|-------|------|-------------|
| 69 | Observable runtime + session hardening + read-only diagnostics UI | `strategy/live_uat_runtime_snapshot.py`, `strategy/live_session_lifecycle.py`, `ui/uat_runtime_vm.py`, `ui/uat_runtime_panel.py` |
| 70 | Deterministic offline bench harness (67 scenarios) + report + runner UI | `strategy/bench_uat_harness.py`, `ui/bench_uat_vm.py`, `ui/bench_uat_panel.py` |
| 71 | Manual UAT evidence + release-candidate manifest + readiness evaluator + entry UI | `strategy/manual_uat_evidence.py`, `strategy/release_candidate_manifest.py`, `data/manual_uat_store.py`, `ui/manual_uat_vm.py`, `ui/manual_uat_panel.py` |

All three UAT surfaces are hosted on the **developer/UAT Development History page** (never the driver Command
Centre). The runtime snapshot is built OFF the Qt thread with a stale-worker guard; the bench runner runs OFF
the Qt thread; manual writes are explicit and persist beside the user's config
(`manual_uat_evidence.json`, atomic write, never a runtime data file, never setup history).

### The exact candidate build for manual UAT

Manual UAT must run against the tip of `eng-brain-phase69-71-uat-activation-gate` (the completion report
records the exact commit). The release-candidate manifest identifies it: branch, commit, parent, DB v28, rule
engine 46.0, automated + bench totals, listener status, runtime-file integrity, and the manual results.

### Readiness decision (honest, no hidden scoring)

`evaluate_manual_uat_readiness` returns one of `READY_FOR_MANUAL_UAT`, `CONDITIONAL_FOR_MANUAL_UAT`,
`NOT_READY_FOR_MANUAL_UAT`, `OPERATIONALLY_CERTIFIED`:

- `OPERATIONALLY_CERTIFIED` is **impossible** while any required physical/live area is not PASS, and it also
  requires an explicit operational grant. Green unit tests alone, or green bench alone, can never reach it.
- A failed safety / telemetry-integrity / strategy-authority / certification-integrity check →
  `NOT_READY_FOR_MANUAL_UAT`.
- With no evidence supplied the default is `NOT_READY` (never optimistic).
- **Expected maximum state before physical testing: `READY_FOR_MANUAL_UAT`.**

## Staged UAT procedures

Record each observation in the Manual UAT panel (Development History): pick the area, set PASS / FAIL /
BLOCKED / NOT_RUN, enter expected vs observed, notes, a defect reference on failure, and an evidence
reference (screenshot/clip path). A FAIL or BLOCKED auto-flags retest-required. Prior evidence is superseded,
never overwritten.

### Stage 1 — Desktop smoke test (no telemetry)
1. Launch the app. **Expected:** main window opens; all tabs build; no crash.
2. Navigate every tab incl. Development History. **Expected:** no freeze; panels render read-only.
3. Check Windows scaling at 100/125/150%. **Expected:** text/controls legible, no clipping.
4. Open the UAT Runtime panel. **Expected:** `[NO FEED]`, objective UNKNOWN, evidence gaps listed, cert
   overall NOT_TESTED.
5. Click **Run Bench UAT (offline)**. **Expected:** button disables, runs off-thread, returns `BENCH READY`
   67/67, 0 failed, 0 safety failures; UI never freezes.
6. Reset Session. **Expected:** transient live state cleared; no stale advice remains.
   *Record areas:* application_startup, desktop_visual_layout, windows_scaling, live_dashboard_readability.

### Stage 2 — Stationary GT7 test (in pits)
1. Start GT7, sit in the pit box, connect telemetry. **Expected:** UAT Runtime shows `[LIVE FEED]`, packet
   age small.
2. Confirm event/session binding fields populate. 3. Confirm fuel + race-clock mapping match the game.
4. Disconnect the network briefly, then reconnect. **Expected:** `[STALE FEED]` then `[LIVE FEED]`; strategy
   returns INSUFFICIENT while stale; no stale recommendation persists.
   *Record areas:* telemetry_connection, telemetry_reconnect, race_clock, fuel_mapping.

### Stage 3 — Practice session
1. Run several clean laps. **Expected:** pace evidence gains samples; fuel burn estimate stabilises (robust
   median; one bad lap doesn't swing it). 2. Confirm the tyre-age proxy is shown and clearly labelled a
   PROXY, not measured wear. 3. Trigger a pit entry/stop/exit. **Expected:** pit state transitions; count
   increments once. 4. Confirm strategy cadence is bounded (no per-packet spam) and no audio flooding.
   *Record areas:* pace_mapping, tyre_age_proxy, pit_entry, pit_stop, pit_exit, lap_rollover, audio_cooldown.

### Stage 4 — Controlled race (accelerated fuel/tyre multipliers to force adaptation)
Test higher- and lower-than-forecast fuel burn, early tyre crossover, a completed pit stop, a revised pit
window, lap-count strategy, time-certain strategy, the extra-lap boundary, and the recommendation
explanation; acknowledge a recommendation. **Expected:** advice adapts to real evidence; a time-certain extra
stop that costs a completed lap is REJECTED; acknowledgement executes nothing.
   *Record areas:* lap_count_adaptive_strategy, time_certain_adaptive_strategy, strategy_explanation_quality.

### Stage 5 — Physical voice / PTT
Bind and test keyboard PTT, then wheel/joystick PTT; acquire the microphone; speak a clear utterance, an
ambiguous one, and a low-confidence one; exercise the confirmation flow and a timeout. **Expected:** the mic
is live only while PTT is held; a clear command is recognised; an ambiguous/low-confidence utterance produces
NO driver-report label and NO action; a report requires read-back; a timeout does nothing.
   *Record areas:* keyboard_ptt, wheel_joystick_ptt, physical_microphone, recognition_confidence,
   ambiguous_speech, confirmation_flow.

### Stage 6 — PSVR2
With the headset on and the screen ignored: check audibility, message length, priority, cooldown,
interruption, driver workload, and timing in braking/cornering. **Expected:** important advice is
understandable without the screen; routine messages defer to low-workload windows; urgent messages override.
   *Record areas:* physical_tts, psvr2_audibility, psvr2_timing, psvr2_driver_workload.

### Stage 7 — Operational rehearsal
Pre-race briefing → live binding → race execution with adaptive advice → a pit cycle → finish → debrief →
cumulative knowledge update → record certification evidence. **Expected:** the whole loop is usable in VR;
knowledge updates only through the existing authorities.
   *Record area:* live_gt7_operational_suitability. Only after ALL required physical/live areas are PASS and
   an explicit operational grant is given can readiness reach `OPERATIONALLY_CERTIFIED`.

## Defect-recording guidance
On any FAIL: set the area to FAIL, write the observed behaviour, add a defect reference (issue id / short
slug) and an evidence reference (screenshot/clip). The area is auto-flagged retest-required and the readiness
evaluator drops to `NOT_READY_FOR_MANUAL_UAT` until resolved. Do not mark an area PASS from memory — record it
at the time of the test.

## Audits
The pre-implementation audits (A end-to-end path, B session lifecycle, C bench seam, D physical
certification truth) are in `docs/ENGINEERING_BRAIN_PHASE69_71_PREPHASE_AUDITS.md`.
