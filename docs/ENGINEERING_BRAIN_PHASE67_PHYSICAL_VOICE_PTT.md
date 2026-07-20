# Engineering Brain — Phase 67: Physical Offline Voice & PTT Bring-Up

Program 2, Phase 67. Concrete local Windows adapters behind the Phase 63–64 ports — no new framework
(win32com is an existing dependency; ctypes is stdlib). All adapters import lazily, are disabled by default,
never listen continuously, contact no network, and never raise.

## Offline TTS

Reuses the existing `voice/advisory_voice_port.py` (SAPI5 via win32com, disabled-default, failure-safe) —
already production-shaped: output-device init, async speak, cancellation (`stop`), priority interruption
(via the Phase-47 queue), failure fallback (permanent disable → visual-only), and a test message gated to
when a run is not active. No cloud.

## Offline recognition — `voice/windows_sapi_recognition.py`

`WindowsSapiRecognitionPort` implements the Phase-64 `SpeechRecognitionPort` using the OFFLINE Windows SAPI
in-process recogniser (`SAPI.SpInprocRecognizer` + a command grammar built from the Phase-64 phrases). It is
grammar-based, PTT-gated (`start_listening`/`stop_listening` — active only while PTT is held, never
continuous), persists no raw audio, and surfaces confidence + ambiguity. `recognition_kind` is
`command_grammar` — **never presented as natural-language understanding.** **Honest limitation:** SAPI
recognition reliability varies by machine/language pack; where the local recogniser is unavailable or
unreliable, `is_available` is False and the app falls back to the deterministic fake / disabled port. The
certification marks microphone recognition as needing **physical-mic UAT** — never certified from unit tests.

## Physical PTT input adapters

- `voice/keyboard_ptt.py` — `KeyboardPttInputPort`: polls a virtual-key code via ctypes
  `user32.GetAsyncKeyState` (a POLL, **not** a global hook — nothing to leak on shutdown, no focus theft,
  no permission prompt).
- `voice/joystick_ptt.py` — `JoystickPttInputPort`: polls a joystick/gamepad/wheel BUTTON via ctypes winmm
  `joyGetPosEx` (wheel buttons appear to Windows as joystick buttons — covers direct-drive wheels and
  controllers with **no Fanatec-specific code** and no new SDK).

Both use the Phase-64 hardware-neutral `PushToTalkBinding`; `input_code` is operational config, excluded
from every engineering fingerprint.

## Binding workflow — `strategy/ptt_tts_coordination.py`

`validate_binding` rejects reserved keyboard keys (Esc/Enter/Win/Tab/Alt) and controls already bound
elsewhere (conflict detection); `apply_binding` writes only a VALID binding via the safe config helper;
`clear_binding` returns to unbound; `default_binding` is keyboard F13 (uncommon, low-conflict). The Qt
`ui/ptt_binding_panel.py` presents the workflow (select type → press-to-bind → show → test → clear →
restore-default), unavailable-device messaging, a PSVR2 readiness checklist, and the per-area + overall
certification — a garage/settings surface, never a driving surface.

## PTT lifecycle + TTS coordination — `voice/ptt_runtime_controller.py`

`PttRuntimeController` drives the full lifecycle (idle / pressed / listening / recognising / recognised /
ambiguous / awaiting-confirmation / cancelled / timed-out / unavailable / failed). On a PRESS edge it starts
listening and applies `decide_ptt_tts_action` → **pause routine speech but PRESERVE an active safety/critical
message** (never talk over the driver). On RELEASE it stops listening, recognises, classifies with the
Phase-64 grammar, decides read-back, and **rejects stale recognition** captured before an event/activity
switch (`is_stale_recognition`). Ambiguous recognition triggers nothing. No engineering mutation; the mic is
never continuous.

## Driver-report & operational-command semantics (Audit C)

Read-back-then-confirm feeds a CONFIRMED driver report into the live race-state adapter, labelled
driver-reported (never verified telemetry, never an automatic outcome). `return_to_garage` is a safe
operational **intent** — it never auto-completes, binds or records an activity. See Audit C for the full
per-command mutation-boundary table.

## Tests

`tests/test_phase67_physical_voice_ptt.py` (13) + `tests/test_phase67_68_lifecycle_ui.py` (lifecycle + UI).
