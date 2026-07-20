# UAT — Engineering Brain Phases 45–47 (Provenance / Live Shadow / Voice)

Preferred setup: Porsche 911 RSR '17, Fuji Full Course, one Base/Race experiment, a known applied +
parent setup, at least one valid telemetry session.

## Execution status (honest)

This environment is **headless (offscreen Qt, no display, no audio device, no live GT7 feed)**. Stages A
and B were executed **programmatically** against a real `SessionDB`. Stage C (live GT7 shadow) and Stage
D (voice) **could not be executed** (no telemetry feed, no audio). A replay test is not live GT7 UAT; an
offscreen Qt test is not voice UAT.

### Stage A — Context provenance (EXECUTED programmatically)

| # | Step | Result |
| --- | --- | --- |
| A1 | Create event with known tyre/fuel/BoP/tuning | PASS (fixture) |
| A2 | Create an explicit context snapshot | PASS (`capture_context_snapshot`) |
| A3 | Verify stored snapshot values | **PASS** — stored tyre×5, fuel×3, BoP off |
| A4 | Edit the event | PASS (fixture) |
| A5 | Old snapshot unchanged | **PASS** — old still resolves tyre×5, BoP off |
| A6 | New evidence gets the new context | **PASS** — new resolves tyre×8, BoP on |
| A7 | The two contexts do not merge as exact | **PASS** — different semantic digests |
| A8 | Viewing the UI creates no snapshot | **PASS** — snapshot count unchanged after a runtime report |

### Stage B — Replay shadow (EXECUTED programmatically)

| # | Step | Result |
| --- | --- | --- |
| B1 | Replay a lap/session | PASS (`replay_telemetry`) |
| B2 | Current segment + workload state | PASS |
| B3 | Eligible prompts | PASS |
| B4 | Delayed prompts | PASS (high-workload deliveries = 0) |
| B5 | Expired prompts | PASS (unit) |
| B6 | Stale telemetry suppression | **PASS** — stale deliveries = 0 |
| B7 | Repetition limits | PASS (unit: cooldown/per-lap) |
| B8 | Stop-critical priority | PASS (unit) |
| B9 | Inspect shadow ledger | PASS (`LiveRunValidationSummary` records) |
| B10 | No audio produced | **PASS** — shadow imports no TTS; readiness SHADOW_READY (voice not eligible) |

### Stage C — Live GT7 shadow (NOT RUN — needs a live GT7 feed)

Steps C1–C8: **NOT RUN.** The deterministic equivalents (segment/workload gating, invalid/stale
suppression, run-completion guidance, no-DB-mutation) are proven by unit + runtime tests.

### Stage D — Voice (NOT RUN — needs live audio + shadow readiness)

Steps D1–D14: **NOT RUN** (headless, no audio device; and voice stays gated below VOICE_ELIGIBLE, which
requires a live-GT7 shadow confirmation). The deterministic equivalents are proven by unit tests: voice
disabled by default, exact-message delivery, cooldown, stop-critical interruption, acknowledge, repeat
once, mute, context-change flush, adapter-failure visual-only fallback, session-end cleanup, and
no-strategy-command.

## To run the remaining stages in the live app

1. **Stage C:** launch NGR Pit Crew with a live GT7 feed, voice DISABLED; open Development History →
   Assisted Runtime; run a controlled practice run; confirm target-corner prompt timing, no detailed
   prompt during braking/turn-in/apex, suppression in invalid/stale states, run-completion guidance, and
   that advisory evaluation mutates no DB.
2. **Stage D:** only after the shadow readiness gate passes, explicitly enable voice; test outside a run;
   run a low-risk session; verify exact approved messages, routine cooldown, stop-critical priority,
   acknowledge, repeat once, mute lap/session; change the active setup and confirm queued messages are
   cancelled; simulate adapter failure → visual-only fallback; confirm no pit/tyre/fuel/setup command is
   spoken; disable voice → immediate silence. Record PASS/FAIL/PARTIAL/NOT RUN per step.
