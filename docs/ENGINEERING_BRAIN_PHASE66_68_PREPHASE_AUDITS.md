# Engineering Brain — Phases 66–68 Pre-Phase Audits & Phase 63–65 Corrections

Performed on branch `eng-brain-phase66-68-live-vr-certification` from `eng-brain-phase63-65-vr-adaptive-
strategy @ fddfb17` (authoritative merged base `master @ 26c0975`). Additive — no earlier commit amended.

## Checkpoint (verified)

Branch `…phase63-65… @ fddfb17`; working tree clean of source changes (only runtime/app-state files); all
**9** Phase 63–65 commits present (`76cc666`→`fddfb17`); `master` = `origin/master` = `26c0975`; the branch
is **not pushed / no PR / not merged**; Phase 2–62 history is on master; `DB_VERSION == 28`,
`RULE_ENGINE_VERSION == 46.0`; the production Live Pit Wall is in `TAB_LIVE`; the sole GT7 pipeline is
`telemetry/listener.py` (UDPListener) + `telemetry/state.py` (RaceStateTracker); Apply + voice gates intact;
`audio_strategy_certification()` overall = `not_tested` (live/voice ungranted). Runtime hashes:
`active_setup_state.json` e84aeb9a…, `data/setup_history.json` 91ed583e…, `.claude/settings.local.json`
a71b52a7…. 102 Phase 63–65 focused tests pass. The pre-implementation full suite was launched (see the
completion report / testing register for whether it completed under load).

## Phase 63–65 report corrections (mandatory)

- The **authoritative starting base was the merged `master @ 26c0975`** (PR #75). The old Phase 60–62 branch
  name (`eng-brain-phase60-62-production-live-activation`) was **not** the authoritative base — it is a
  now-merged feature branch that remains present on the remote.
- The Phase 63–65 **pre-implementation full regression was attempted but did NOT complete** due to resource
  contention (concurrent focused test runs starved it; it ran >2h vs the ~52-min baseline and was stopped).
  It must not be described as rerun successfully.
- The Phase 63–65 **final complete regression DID pass: 10,210 passed / 27 skipped / 0 failed / 10,237
  collected (3129.50s)**.
- Phase 63–65 **Live strategy has production UI placement but not real tracker-fed runtime activation** — the
  panel showed an honest INSUFFICIENT_EVIDENCE default because the tracker→`LiveStrategyState` mapping was
  deferred. **Phase 66 supplies that mapping.**
- Phase 63–65 **PTT and recognition are architecture + grammar complete, not physically certified** — the
  ports were disabled-default abstractions with deterministic fakes. **Phase 67 supplies concrete Windows
  adapters** (still requiring physical UAT for certification).

## Audit A — live-state field availability matrix (real tracker + canonical local authorities)

Source key: **T** = `RaceStateTracker` property; **P** = live packet (`tracker._prev`); **L** = canonical
local authority (Event Prep / activity / setup / Race Plan / event rules); **D** = confirmed PTT driver
report; **—** = unavailable from GT7.

| Field | Source | Measured/Derived | Availability | Confidence | Fingerprint? | Cert consequence |
| --- | --- | --- | --- | --- | --- | --- |
| current lap | T `laps_recorded` | measured | available | high | yes | mapping certifiable |
| scheduled lap count | T `laps_in_race` | measured | available (lap races) | high | yes | lap-count clock |
| elapsed race time | T (`_race_start_time`) / clock | derived | available (racing) | high | yes | race clock |
| remaining race time | T `timed_duration_minutes` − elapsed | derived | available (timed) | high | yes | time-certain clock |
| scheduled race duration | T `timed_duration_minutes` | measured | available (timed) | high | yes | time-certain clock |
| race type | T `race_type` (LAP/TIMED/UNLIMITED) | measured | available | high | yes | selects clock model |
| position | T `last_position` / P `current_position` | measured | available | high | yes | finishing-pos tie-break (where trustworthy) |
| car / track | T `car_name` / `track` | measured | available | high | yes | context |
| layout | L map-match / T `layout_id` | derived | limited | medium | yes | layout confidence |
| speed / throttle / brake / steering / gear | P | measured | available | high | **no** (volatile) | workload gate |
| fuel remaining | T `last_fuel` | measured | available | high | yes | fuel model |
| fuel burn (avg/live) | T `avg_fuel_per_lap` + multi-lap | derived | available | medium | yes | fuel projection |
| lap pace | T `best_lap_ms` + P last-lap + clean-lap median | derived | available | medium | yes | pace projection |
| clean / invalid lap | T/P clean-lap flags | measured | available | medium | yes | pace validity |
| stint start / age | T `pit_stint_state` / `laps_since_pit` | derived | available | medium | yes | stint model |
| pit-lane state | T `in_pit` / `pit_state_confidence` | measured+derived | available | medium | yes | pit detection (no weak increment) |
| pit-stop count | T `pit_stops_completed` | derived | available | medium | yes | pit model (no double-count) |
| compound | T `tyre_compound` | measured (may be unknown pre-lap) | limited | low-medium | yes | tyre model |
| tyre-age proxy | T `tyre_age_laps` | derived proxy | limited | low | yes | **PROXY only** |
| tyre degradation | lap-time drift / corner/traction/brake | derived **proxy** | limited | low | yes | **PROXY — GT7 gives no direct tyre condition** |
| map-match confidence | L segment resolver | derived | available | medium | yes | layout/pit corroboration |
| traffic | pace-outlier heuristic | derived | limited | low | no | pace exclusion |
| weather / wetness | — (else **D**) | driver-reported | unavailable unless reported | driver-reported | yes (label) | never verified telemetry |
| damage | — (else **D**) | driver-reported | unavailable unless reported | driver-reported | yes (label) | never verified telemetry |
| penalties | — (else **D**) | driver-reported | unavailable unless reported | driver-reported | yes (label) | never verified telemetry |
| safety-car / interruption | — | unavailable | unavailable | none | no | unsupported (explicit) |
| Race setup fingerprint | L `ActiveSetupAuthority` | **local proxy** | limited | proxy | yes | GT7 doesn't broadcast setup → attribution cap |
| pre-race strategy | L Race Plan | measured | available (if built) | high | yes | plan comparison |
| event rules | L event settings | measured | available (if configured) | high | yes | legal-completion / RULES_UNVERIFIED |

**Unknown stays unknown** — no field above is fabricated; unavailable fields are reported explicitly.

## Audit B — time-certain ranking hierarchy

The exact deterministic optimisation hierarchy for time-certain candidates:

1. **maximise expected completed laps** (primary — never traded for a faster average);
2. expected finishing position (where trustworthy — position known + not stale);
3. lowest projected total elapsed time;
4. lowest pit-loss exposure (fewer/cheaper stops);
5. highest legal-completion confidence (required-stop/tyre rules satisfied);
6. safest fuel-at-finish margin;
7. lowest fragility (least sensitive to assumption error);
8. **stable label** — the FINAL tie-break only.

Equal-completed-lap candidates must NOT be ordered by candidate ID except as the last stable tie-break.
Phase 66 replaces the Phase-65 `rank_candidates` time-certain key `(-laps, stop_delta, label)` with this
full hierarchy.

## Audit C — PTT operational-command semantics

| Command | Class | Only requests info | Sets temp operational intent | Alters audio pref | Requires confirm | Can modify engineering state |
| --- | --- | --- | --- | --- | --- | --- |
| status / fuel_status / tyre_status / current_plan / next_pit_window | safe-operational | **yes** | no | no | no | **NO** |
| acknowledge / dismiss / repeat / cancel | safe-operational | — | acknowledgement receipt only | no | no | **NO** |
| mute / unmute / mute_coaching / resume_coaching | safe-operational | no | no | **yes** | no | **NO** |
| strategy_update / plan_viable / what_if_stop_now / can_extend / can_save_fuel / fallback_plan | strategy-request | **yes (asks for an assessment)** | no | no | no | **NO** (never forces a change) |
| return_to_garage (after this lap) | safe-operational | no | **yes — temporary operational intent only** | no | no | **NO — must NOT auto-complete/bind/record** |
| driver reports (rain/damage/…) | driver-report | no | no | no | **yes (read-back)** | **NO** (label only, never verified telemetry, never outcome) |
| engineering feedback | feedback | no | no | no | **yes (read-back)** | **NO** (DRAFT only; canonical only via existing workflow) |

`return_to_garage` is the sharpest case: it is an advisory **intent** the driver hears acknowledged; it
does not complete, bind, or record an activity (enforced by a Phase-67 test).

## Audit D — concrete adapter inventory (prefer existing dependencies; no large new framework)

| Facility | Existing capability | Phase-67 plan |
| --- | --- | --- |
| offline TTS | `voice/advisory_voice_port.py` + `voice/announcer.py` — **SAPI5 via win32com** (existing dep) | **reuse** + validate production support (device readiness, cancel, priority interrupt, failure fallback, shutdown, test-when-not-driving) |
| local command recognition | none present; **win32com SAPI in-proc grammar recognition** available (`SAPI.SpInprocRecognizer` / `SpInProcRecoContext`) | concrete `WindowsSapiRecognitionPort` behind the Phase-64 port — offline, grammar-based, PTT-gated, lazy win32com import, disabled default; **reliability unverified without a physical mic → honest limitation** |
| keyboard PTT | **ctypes** `user32.GetAsyncKeyState` (poll, not a global hook) | concrete `KeyboardPttInputPort` — offline, no new dep, no hook |
| controller / wheel button | **ctypes** winmm `joyGetPosEx` (joystick+wheel buttons) / XInput | concrete `JoystickPttInputPort` — best-effort, disabled default (wheel buttons appear as joystick buttons) |
| microphone / audio-output selection | SAPI `GetAudioOutputs` / recognition audio inputs | best-effort enumeration surfaced in the binding UI |

**No new framework added.** win32com is already a project dependency; ctypes is stdlib. All concrete
adapters import lazily, are disabled by default, never listen continuously, and never touch the network.
