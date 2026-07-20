# UAT — Engineering Brain Phase 57–59 (Real GT7 Runtime, NGR Live Pit Wall, Event Certification)

Branch `eng-brain-phase57-59-live-gt7-event-certification`. Developed headlessly. **Manual visual UAT,
live GT7 telemetry UAT, and physical voice UAT were NOT run in this environment.** Automated results are
NOT manual/live UAT. Evidence categories (used strictly, per Audit C): unit tests · property/metamorphic
tests · runtime DB tests · **static runtime-snapshot tests** · deterministic telemetry replay · offscreen
UI tests · manual visual UAT · live GT7 telemetry · physical voice UAT.

## `/ui-ux-pro-max` design gate (mandatory)

Invoked before the live pit-wall UI (commit 6). **Received:** high-contrast readability, status feedback,
glanceable layout. **Adopted:** a glanceable low-cognitive-load hierarchy (ONE primary message), high-
contrast NGR tones, mode-distinct headers (Practice/Qualifying/Race look different; Qualifying minimal,
Race safety), single advisory suppressed on stale/blocked, transition/recovery cards replace the driving
hierarchy at session end / telemetry loss, meaning by tag+tone. **Rejected/deferred:** bulk-actions/form-
submit results (N/A to a live HUD); production placement in the Live tab + telemetry-driven off-thread
refresh (deferred — not visually verifiable headlessly). Cognitive load: exactly one primary message and
one advisory; detail deferred to the debrief. NGR experience: the active event + activity lead every live
frame; the pit wall is one coordinated NGR voice.

## Staged results

- **Stage A — Command Centre → live transition:** proven at the domain/unit level (next action, pit-wall
  assembly); the visual transition is manual visual UAT — NOT run.
- **Stage B — Real GT7 Practice:** the adapter, match, session-end→binding, garage-return are proven by
  static runtime-snapshot + unit tests; the **real GT7 feed step was NOT run**.
- **Stage C — Setup mismatch:** proven (blocked, no evidence, advisory suppressed) —
  `test_phase57_59_golden`.
- **Stage D — Telemetry loss:** proven (advisories stop, incomplete, no duplicate) — unit tests; live NOT run.
- **Stage E — Qualifying / Stage F — Race:** minimal/safety modes + no-commands proven by unit tests; live NOT run.
- **Stage G — Voice:** derive_voice_status gating proven by unit tests; **physical voice UAT NOT run**.
- **Stage H — Full event experience:** manual visual UAT — NOT run.

## Certification (do-not-fabricate honoured)

`live_event_certification()` = per-area, overall **NOT_TESTED** (bounded by live areas). 20 areas
AUTOMATED, 1 OFFSCREEN, 10 NONE (each with required-next-evidence). Automated tests did NOT award visual/
live/operational; offscreen did NOT award visual; static snapshots are NOT replay; replay is NOT live GT7;
visual-only is NOT voice UAT. No operational readiness claimed.

## What was proved, by category

- **Unit tests:** adapter mapping, freshness, cadence/cache, runtime transitions, pit-wall assembly, voice
  status, garage return, certification.
- **Property/metamorphic tests:** same-sequence-same-decision, refresh-cannot-advance, mismatch-cannot-
  strengthen, stale-cannot-deliver-advice, voice-cannot-be-manufactured/alter-fingerprint, single-advisory,
  automated/replay certification caps.
- **Runtime DB tests:** Command Centre + truth views byte-identical across refreshes; telemetry evaluation
  touches no DB.
- **Static runtime-snapshot tests:** the match classifier + adapter over constructed snapshots.
- **Offscreen UI tests:** pit-wall panel + Development History page construction.
- **Deterministic telemetry replay / manual visual UAT / live GT7 / physical voice UAT:** NOT run.
