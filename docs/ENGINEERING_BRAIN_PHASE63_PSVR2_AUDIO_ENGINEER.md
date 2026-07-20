# Engineering Brain — Phase 63: PSVR2 Audio-First Race Engineer

Program 2, Phase 63. Read-only, deterministic, offline, no AI. Makes the production live experience
operational when the driver (PSVR2) cannot see the desktop. Verbal delivery becomes the primary live
channel; the visual UI is preserved as a fallback. `strategy/audio_first_engineer.py` (pure; Qt-free,
DB-free, no wall clock; never raises).

## VR runtime mode

`VrRuntimeMode` = DESKTOP | AUDIO_FIRST. Audio-first mode makes speech primary but **preserves the normal
visual UI, requires no PC interaction while driving, is optional for non-VR users, and never alters
engineering conclusions, evidence fingerprints or voice eligibility.**

## The single message-priority authority

`EngineerMessageIntent` (9) → `classify_message_priority` → `EngineerMessagePriority` (1 = highest):
safety/critical-mismatch → severe car-condition warning → material strategy change → pit-window/fuel-
critical → session transition → setup-test instruction → lap/stint status → coaching → informational. A
lower-priority message never interrupts a higher-priority one; unknown intents are INFORMATIONAL (never
urgent). Safety + car-condition are stop-critical (may interrupt an active routine message via the
Phase-47 queue).

## Workload-aware delivery

`assess_driver_workload(context)` → LOW / MODERATE / HIGH / UNKNOWN from trustworthy live context
(braking, corner segment, steering, throttle, speed, pit lane, stopped, telemetry freshness). Routine
messages are delivered only in a LOW window (straight / pit lane / stopped). **Unknown workload is
conservative (never LOW).** `decide_speech_window(priority, workload)` → SPEAK_NOW / DEFER / OVERRIDE:
urgent priorities (safety/car-condition/strategy/pit-fuel) OVERRIDE the workload gate; routine messages
DEFER outside a low window.

## Concise duration budgets

`message_duration_budget(priority)`: urgent ≤1.5–2.0s; routine coaching/lap-status ≤2.5s; material strategy
= concise 3.0s headline first (detail deferred to the garage/on request). No paragraph-length radio while
driving.

## Coordinated communication

One NGR radio channel. Evidence may originate from Chief/Race/Performance/Strategy/Coach/Crew roles — these
are role labels over shared canonical evidence, **not independent agents**.

## Voice / listening states + operational readiness

`resolve_audio_engineer_state(...)` → ONE composite `AudioFirstEngineerState` at a time (visual-only,
voice-disabled, voice-gated, voice-ready, voice-active, PTT-active, muted, recognition-unavailable,
TTS-unavailable, adapter-failure, telemetry-stale, critical-only) + `AudioOperationalReadiness`
(NOT_AUDIO_FIRST / READY / DEGRADED / UNAVAILABLE). Voice can never be manufactured eligible — `gate_allows`
comes from the canonical Phase-46 voice gate.

## Voice failure

Adapter failure / TTS-unavailable → readiness UNAVAILABLE, the **visual pit wall is preserved**, no retry
loop, engineering conclusions unchanged, no outcome recorded, and the failure is visible in the state +
certification. `decide_engineer_speech` gates delivery: in telemetry-stale / critical-only states only
stop-critical messages pass; nothing passes when voice is not deliverable.

## Tests

`tests/test_phase63_audio_engineer.py` (20).
