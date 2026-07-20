# Engineering Brain — Program 2, Phase 44: Live Advisory Prompt Engine Foundation

Read-only, offline, deterministic, advisory-only. Part of the **Phases 42–44 Assisted Runtime
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.
**Voice output is deferred.**

## Purpose & authorities

Begins live race-engineer delivery using safe, deterministic **text** prompts. No voice/TTS, no
automatic pit calls, no fuel/tyre/strategy commands (strategy prompts are read-only awareness only).

| Module | Owns |
| --- | --- |
| `strategy/live_advisory.py` | the prompt model, visible priority, and candidate builders. |
| `strategy/live_advisory_engine.py` | safety gates, priority arbitration, deterministic suppression. |
| `strategy/runtime_snapshot.py` | the immutable per-evaluation snapshot (maps existing inputs). |

## Prompt model

`AdvisoryPrompt`: prompt_type, priority, source_authority, context_fingerprint, run_plan_fingerprint,
target_segment, delivery_window, message, rationale, confidence, evidence_freshness, expiry_lap,
cooldown_seconds, suppression_key, ack_required, prompt_class (informational / cautionary /
stop_critical).

## Advisory priority (explicit, visible — no black box)

1 safety/invalid-run stop · 2 context/setup mismatch · 3 run-plan stop condition · 4 measurement-lap
instruction · 5 target-corner coaching · 6 evidence collection · 7 informational progress · 8 strategy
awareness. Only the top-priority survivor of a tick is delivered (supersession).

## Safe delivery windows & gates

Hard staleness gates suppress ANY prompt: stale telemetry, changed context (fingerprint mismatch),
stale plan / run-plan fingerprint change, expired (lap past expiry), target corner already passed, or
the advice conflicts with the plan. Window gates (skipped for `stop_critical`) delay non-critical
prompts in high-workload segments (braking / turn-in / apex) and off-window, and enforce a per-prompt-
type minimum confidence. Preferred windows: straights, pit lane, before a measurement lap, after the
finish line, after the session, low-workload segments. Detailed prompts are never delivered during
braking/turn-in/apex; a safety **stop** may be delivered at any non-stale moment.

## Suppression & deduplication (deterministic, injected clock)

Semantic suppression keys, cooldowns (via an **injected monotonic clock** — `now_monotonic` — that
drives cooldown ONLY and never enters a fingerprint), per-lap (1) and per-session limits, supersession,
expiry, stale-plan/stale-telemetry rejection, and acknowledgement where appropriate. The engine emits
NOTHING when nothing is deliverable — no dashboard woodpecker.

## Coaching limits

Only ONE primary coaching objective is active during a controlled run (the approaching target corner's
objective); simultaneous braking/steering/gearing/throttle coaching is not produced unless the plan is
explicitly an observational baseline.

## Strategy-awareness limits

Read-only awareness only (plan evidence incomplete, tyre/fuel evidence required, event-deadline protect
the best-known setup). No automatic pit calls, fuel targets, tyre-change or strategy commands.

## Runtime snapshot & UI

`build_runtime_snapshot` maps existing canonical inputs (context fingerprint, run plan, assisted-workflow
state, Phase-42 material trust, a read-only telemetry frame) into a stable snapshot — no second telemetry
authority. The read-only `AssistedRuntimePanel` shows Run State / Live Advisory / Evidence Progress as
ONE coordinated pit-wall (not competing radios). The heavy build runs off the Qt thread; the dashboard
injects `time.monotonic()` for cooldown and carries the suppression state forward across refreshes; a
stale-worker guard protects it. No voice engine, TTS, auto-Apply, auto experiment/outcome, or auto pit
command is added.

## Query shape & determinism

`SessionDB.build_assisted_runtime_report` resolves context once, reuses the shared chain's single
bounded read and the Phase-17 portfolio composed once; query count is constant across 5 / 50 / 500
records. Fingerprints exclude object/machine identity, paths, UI state, wall-clock, random ids, audio
device state and DB row order; runtime elapsed time is used only for cooldown.

## Deferred

Voice/TTS delivery, automatic pit calls, autonomous strategy commands, automatic setup application,
automatic experiment creation and automatic outcome recording remain **deferred** by design.
