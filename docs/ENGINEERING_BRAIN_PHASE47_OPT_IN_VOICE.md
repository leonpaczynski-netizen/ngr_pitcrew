# Engineering Brain — Program 2, Phase 47: Opt-In Offline Voice & Acknowledgement

Read-only w.r.t. engineering state, offline, deterministic. Part of the **Phases 45–47** slice. DB stays
**v27**; rule engine **46.0**. Voice is a controlled DELIVERY adapter for advisories that already passed
the Phase-44 and Phase-46 gates.

## Voice architecture (adapter boundary)

| Module | Owns | Imports Windows/TTS? |
| --- | --- | --- |
| `strategy/voice_delivery.py` | pure request + abstract port + Disabled/Fake ports + VoiceQueue | **No** (TTS-free) |
| `voice/advisory_voice_port.py` | Windows offline SAPI5 adapter (`VoiceOutputPort`) | yes, LAZILY inside `enable()` |
| `voice/voice_controller.py` | driver: queue + port + gates + failure handling | no top-level TTS import |
| `ui/assisted_runtime_panel.py` | opt-in voice controls + status cards | no |

Core strategy/engineering modules never import Windows or TTS libraries. The Windows adapter reuses the
project's existing OFFLINE SAPI5 engine (win32com) — no new/cloud TTS, no API, no LLM, no network.

## Opt-in behaviour

Voice is **disabled by default**. Starting the app / opening the panel / entering a session speaks
NOTHING. The user explicitly enables it (per session), it is visibly active, immediately disableable,
and auto-disabled after an unrecoverable adapter failure. Voice may only be attempted when the
live-validation readiness is VOICE_ELIGIBLE(_WITH_LIMITATIONS) (`voice_gate_allows`).

## Voice content

Speaks ONLY the exact approved advisory message — never generates, rewrites, paraphrases, appends
filler, combines prompts, or speaks suppressed/expired prompts. Long-form explanation stays visual /
post-session.

## Queue & priority

Pure `VoiceQueue`: single active spoken message; a stop-critical prompt INTERRUPTS a routine active
message; a routine prompt never interrupts another; dedup by semantic key; cooldown (injected monotonic
clock); cancel-all on stale context / plan change / session end / voice disabled; per-lap and per-session
limits. A lower-priority message never delays a stop-critical warning.

## Acknowledgement

Explicit driver actions: acknowledge, repeat once (same approved message, no new recommendation, bypasses
cooldown), dismiss, mute prompt type for the session, mute coaching for the lap, disable voice for the
session. **Acknowledgement is operational runtime state — it never becomes driver feedback or experiment
outcome evidence.**

## Voice configuration

Restrained surface: enabled, voice selection (where locally available), speaking rate, volume, test
voice, max routine-prompt duration, repeat permitted. Test voice is unavailable during an active timed
run (it cannot interfere with live prompts).

## Voice safety & failure handling

Voice does not speak when: readiness below the gate, telemetry stale, context stale, active setup
mismatch, run plan stale, session ended, voice disabled, prompt expired, prompt in cooldown, a routine
prompt cannot fit before the next high-workload segment, or a higher-priority message is active. On any
adapter failure the controller disables voice, records FAILED adapter health, preserves the advisory
visually, and does not retry continuously — it never crashes the dashboard and writes no engineering
state.

## Strategy-command prohibition

Phase 47 never speaks: pit now, change tyres, select a fuel map, save fuel, push, defend, overtake,
change brake balance, or change setup. Strategy awareness remains visual-only unless it is an
informational, non-command advisory already permitted by Phase 44.

## Determinism

Voice configuration (enabled / voice name / rate / volume) is operational preference and changes NO
engineering fingerprint. The queue is deterministic given the injected monotonic `now`. A voice failure
changes no engineering conclusion.

## Deferred

Live GT7 voice UAT (not runnable in a headless environment); non-SAPI5 engines; steering-wheel input
integration; any autonomous strategy/pit action.
