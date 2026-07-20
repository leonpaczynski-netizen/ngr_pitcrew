# Engineering Brain — Phase 64: Push-to-Talk Driver Interaction

Program 2, Phase 64. Read-only, deterministic, offline, no AI. Lets the PSVR2 driver talk to the engineer
without removing the headset or looking at the PC. `strategy/push_to_talk.py` (pure domain) +
`voice/ptt_input_port.py` + `voice/speech_recognition_port.py` (thin ports, disabled by default).

## Hardware-neutral PTT

`PushToTalkBinding` (kind = keyboard / controller-button / wheel-button / unset; `input_code`;
`activation` = press-and-hold [default] / toggle-when-explicitly-configured; label). **No hard-coded
Fanatec button; no specific wheel/controller required.** `PushToTalkInputPort` is the hardware-neutral
abstraction — a `DisabledPttInputPort` (default; listens to nothing) + a deterministic `FakePttInputPort`.
A concrete local Windows adapter would live behind this boundary and must audit shutdown/focus/permission/
conflict before any global hook. `input_code` is operational config — **excluded from every engineering
fingerprint**.

## PTT lifecycle + offline recognition

The mic is **not continuously listening** by default; recognition occurs only while PTT is held (or
toggled when explicitly configured). States: IDLE / LISTENING / RECOGNISING / AWAITING_CONFIRMATION /
CANCELLED / TIMED_OUT / UNAVAILABLE. `SpeechRecognitionPort` is OFFLINE-ONLY (no cloud API, no network, no
API key, no upload) with a `DisabledSpeechRecognitionPort` default, a deterministic `FakeSpeechRecognition
Port`, and a `recognition_kind` (`none` / `command_grammar` / `local_dictation`) so callers report the
TRUE capability. This slice ships the honest **deterministic command grammar** with a clean adapter
boundary for richer local recognition — it never pretends a grammar is natural-language understanding.

## Four command classes

`recognize_command(DriverUtterance)` → `DriverCommandIntent` (fingerprint excludes the raw transcript):

- **Safe operational** (acknowledge/repeat/mute/unmute/mute-coaching/resume-coaching/cancel/status/fuel-
  status/tyre-status/current-plan/next-pit-window/return-to-garage/dismiss) — execute immediately; **never
  alter engineering knowledge.**
- **Strategy requests** (strategy-update / plan-viable / what-if-stop-now / can-extend / can-save-fuel /
  fallback-plan) — request an assessment; **never force a change.**
- **Driver reports** (rain/track-drying/damage/front-damage/rear-damage/grip-dropping/fuel-differs/brakes-
  unstable/traffic) — labelled `DriverReportLabel` (driver-reported / unverified / confirmed-by-readback /
  corroborated-by-telemetry / conflicting-with-telemetry / unavailable-for-verification). **A spoken report
  never becomes exact telemetry evidence.**
- **Engineering feedback** (better/worse/no-change/more-understeer/rear-unstable-exit/gearing-long/tyre-deg)
  — becomes a **DRAFT** (`DriverFeedbackDraft`); it never enters canonical learning until confirmed through
  the existing outcome/feedback workflow (`enters_canonical` is always False here).

## Ambiguity, read-back & confirmation

An **ambiguous** utterance (PTT not held OR confidence < 0.55) is UNRECOGNISED and triggers nothing.
`decide_readback` requires a concise read-back for any report/feedback utterance (strategy-affecting,
evidence-affecting, setup/damage/weather). `apply_readback_response` (confirm / correct / cancel / repeat /
review-in-garage): CONFIRM promotes a report to *confirmed-by-readback* (still not telemetry) and a
feedback item to a DRAFT; everything else records nothing. `label_driver_report_against_telemetry`
corroborates a report ONLY when telemetry is available AND agrees; disagreement → conflicting; otherwise
driver-reported / unavailable-for-verification.

## Config safety

`read_ptt_binding` / `write_ptt_binding` operate on a plain config dict (the caller persists it via the
existing atomic `save_config`), explicit-user-action only — operational config, never an engineering
write.

## PTT / TTS coordination

The Phase-47 `VoiceController` pauses/cancels routine speech and preserves urgent messages; the audio-state
gate suppresses routine speech in telemetry-stale / critical-only states. Raw transcripts never enter
engineering fingerprints; recognition confidence + ambiguity are exposed.

## Tests

`tests/test_phase64_ptt.py` (18).
