# UAT — Engineering Brain Phase 60–62 (Production Live Activation, Complete Event Loop, Certification)

Branch `eng-brain-phase60-62-production-live-activation`. Developed headlessly. **Manual visual UAT, live
GT7 telemetry UAT, and physical voice UAT were NOT run in this environment.** Automated results are NOT
manual/live/voice UAT. Evidence categories (strict): unit tests · property/metamorphic tests · runtime DB
tests · static runtime-snapshot tests · deterministic telemetry replay · offscreen UI tests · manual
visual UAT · live GT7 telemetry · physical voice UAT.

## `/ui-ux-pro-max` design gate (mandatory)

Invoked before the production Live-tab UI (commit 4). **Received:** glanceable heading hierarchy, high-
contrast readability, status feedback. **Adopted:** the `NgrLivePitWallPanel` is the FIRST widget of the
Live tab (primary driver surface; one coordinated low-density NGR message leads); existing telemetry +
track-map panels subordinate below; glanceable heading hierarchy; high-contrast NGR tones; mode-distinct
Practice/Qualifying/Race. **Rejected/deferred:** a full Live-tab redesign (high-risk — added additively);
the live QTimer cadence (deferred to live UAT — refresh fires on Live-tab activation). Cognitive load: one
primary message + one advisory; detail deferred to garage/debrief. NGR immersion: the active event +
activity lead every live frame; one coordinated NGR voice.

**Official-logo compliance:** this slice renders NO logo in any new surface (the pit-wall panel + VM draw
no logo). The existing Home logo asset is untouched. Verified: no new UI module contains logo generation/
recolour/redraw tokens (`test_phase60_62_safety::test_new_ui_modules_do_not_generate_or_alter_the_logo`).

## Staged results

- **Stage A — Production navigation:** the Live tab hosts the pit wall; opening Live never starts the
  activity (unit/offscreen tests). Visual transition = manual visual UAT — NOT run.
- **Stage B — Real GT7 Practice:** adapter, match, session-end→binding, debrief, cumulative update proven
  by unit + static runtime-snapshot tests; the **real GT7 feed was NOT run**.
- **Stage C — Mismatch handling:** wrong setup/car/track/unverifiable-layout proven (blocked / limited /
  no exact evidence) — golden tests.
- **Stage D — Telemetry recovery:** advisories stop, no completion, no duplicate — unit tests; live NOT run.
- **Stage E — Qualifying / Stage F — Race:** low-density / safety modes + no-commands + finalised-strategy
  precondition proven by unit tests; live NOT run.
- **Stage G — Voice:** derive_voice_status gating proven; **physical voice UAT NOT run** (no audio device).
- **Stage H — Full NGR experience:** manual visual UAT — NOT run.

## Certification (do-not-fabricate honoured)

`production_event_certification()` = per-area, overall **NOT_TESTED** (bounded by live areas). Automated
tests did NOT award visual/live/operational; offscreen did NOT award visual; static snapshots are NOT
replay; replay is NOT live GT7; silent adapter tests are NOT physical voice UAT. `runtime_field_limitations`
records the honest per-field status (proxy applied-setup fingerprint blocks exact setup identity /
attribution, not Practice pace). **Operational readiness: NOT awarded.**

## What was proved, by category

- **Unit tests:** context resolution, controller, briefing/launch, discipline workflow, binding/debrief,
  restart/event-switch, certification.
- **Property/metamorphic tests:** build-DB-free, opening/refresh-cannot-start/complete, mismatch-cannot-
  strengthen, stale-cannot-advise, event-switch-rejects-stale, voice-cannot-manufacture, automated-cannot-
  award-live.
- **Runtime DB tests:** production build touches no DB; config selection explicit-only.
- **Static runtime-snapshot tests:** adapter + controller over constructed tracker snapshots.
- **Offscreen UI tests:** Live-tab + pit-wall panel construction; off-thread worker; stale-worker + event-
  switch rejection.
- **Deterministic replay / manual visual UAT / live GT7 / physical voice UAT:** NOT run.
