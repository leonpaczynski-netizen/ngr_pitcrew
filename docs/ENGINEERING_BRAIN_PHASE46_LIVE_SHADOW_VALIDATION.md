# Engineering Brain — Program 2, Phase 46: Replay & Shadow-Mode Live Validation

Read-only, offline, deterministic. Part of the **Phases 45–47** slice. DB stays **v27**; rule engine
**46.0**. Validates the Phase-44 advisory engine against realistic telemetry BEFORE voice is enabled.

## Authorities

| Module | Owns |
| --- | --- |
| `strategy/telemetry_replay.py` | deterministic replay harness + injected clock. |
| `strategy/prompt_timing.py` | message-duration budget + timing assessment. |
| `strategy/shadow_advisory.py` | shadow-mode advisory run, ledger, readiness gate. |
| `data/session_db.py` | `build_live_shadow_validation_report` (read-only). |

## Replay architecture

`replay_telemetry(frames, playback_speed, start_monotonic)` replays supplied trustworthy frames against
`TelemetryReplayClock` (injected monotonic time; adjustable playback speed; pause via a frame flag).
Each `ReplayCycle` is tagged FRAME / LAP_BOUNDARY / PIT_ENTRY / PIT_EXIT / STALE_GAP /
SEGMENT_TRANSITION; a gap > 1 sim-second (or a `stale` flag) marks the resumed frame stale and sets
`telemetry_fresh=False`; a `context_mismatch` frame flag is supported for tests. It fabricates no
telemetry. Output is deterministic for identical input; the SEMANTIC content fingerprint is
playback-speed-independent (monotonic times scale, decisions do not).

## Shadow mode

`run_shadow_replay` runs the Phase-44 engine over each cycle EXACTLY as live mode would (build snapshot
→ candidates → arbitrate → timing budget), delivering nothing by voice and writing nothing. It records
`ShadowDeliveryRecord`s (eligible/selected/delayed/suppressed/expired/superseded, delivery window,
reason, confidence, estimated duration, would-voice) and a session-scoped in-memory ledger (operational
runtime state, never engineering knowledge — it does not alter any semantic fingerprint). Shadow and
voice-eligible modes call the SAME engine, so they select the same advisory.

## Timing & workload validation

Prompt timing is measured from injected replay/telemetry time (no machine-speed assertions). Workload
gates (from the engine) delay routine prompts in braking / turn-in / apex / high-workload; stop-critical
may bypass but stays concise. The shadow summary reports `high_workload_deliveries` and
`stale_deliveries` (both 0 in a coherent run).

## Message-duration budget

`estimate_spoken_seconds` = word count / a configured speaking-rate band (150 wpm). Per-priority caps:
coaching cue ≤ 2.5 s (very short), stop-critical immediate + concise, detailed explanation deferred to
pits/post-session. Prompts that cannot fit the available window are rejected before voice exists.

## Live-readiness gates

`LiveRunValidationSummary.readiness`: NOT_READY → REPLAY_VALIDATED → SHADOW_READY →
LIVE_SHADOW_VALIDATED → VOICE_ELIGIBLE_WITH_LIMITATIONS → VOICE_ELIGIBLE. A coherent replay reaches
SHADOW_READY; VOICE_ELIGIBLE requires an explicit real live-GT7 shadow confirmation (never set in
replay). `voice_gate_allows()` keeps voice unavailable below the voice-eligible gate.

## Query shape

`build_live_shadow_validation_report` resolves context once, reuses the run plan + portfolio, and writes
nothing; per-packet evaluation adds no DB query (the ledger and snapshots are in memory).

## Safety

Pure/offline; no wall-clock (injected clock); no speech; no DB write.
