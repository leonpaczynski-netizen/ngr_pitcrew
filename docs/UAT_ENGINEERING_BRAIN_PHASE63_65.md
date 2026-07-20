# UAT — Engineering Brain Phase 63–65 (PSVR2 Audio-First, Push-to-Talk, Adaptive Live Strategy)

Branch `eng-brain-phase63-65-vr-adaptive-strategy` from `master @ 26c0975`. Developed headlessly. **Manual
visual UAT, live GT7 telemetry UAT, physical TTS UAT, physical microphone/PTT UAT and PSVR2 driving UAT
were NOT run in this environment.** Automated results are NOT physical/live UAT.

Evidence categories (strict): source inspection · unit tests · property/metamorphic tests · runtime-DB
tests · static snapshots · deterministic replay · offscreen UI · manual visual UAT · live GT7 telemetry ·
physical TTS · physical microphone & PTT · PSVR2 driving.

## `/ui-ux-pro-max` design gate (mandatory)

**Invoked** before designing the audio-first hierarchy, PTT config, voice/listening status, transcript
read-back, strategy-update cards, acknowledgement/recovery states, VR-safe controls, the Live-tab visual
fallback, and the garage strategy-review presentation (commit 6, before the UI).

- **Recommendations received:** contrast ≥4.5:1; always-visible status feedback; convey meaning by text +
  tag, never colour alone; one primary action/message at a time; progressive disclosure; tabular figures
  for numeric data; glanceable hierarchy; whitespace to group.
- **Adopted:** audio is the PRIMARY live channel and the panel is the non-VR FALLBACK; an always-visible
  voice/listening STATUS line leads; ONE low-density live-strategy card (headline → confidence → next
  review) with an acknowledgement affordance; detailed candidate tables DEFERRED to the garage/strategy-
  review (progressive disclosure); recovery cards on voice failure / telemetry loss; high-contrast NGR
  tones; meaning by tag + text.
- **Rejected / deferred:** a full Live-tab redesign (high-risk — the audio panel is added additively below
  the pit wall); the live QTimer cadence (deferred to live UAT — refresh fires on Live-tab activation); the
  full tracker→LiveStrategyState live mapping (needs a real race — deferred to live UAT; the panel shows an
  honest INSUFFICIENT_EVIDENCE / voice-disabled state without a feed).
- **How it supports PSVR2:** essential information is SPOKEN (priority-ordered, workload-gated, concise), so
  the driver does not depend on the screen; PTT (press-and-hold) drives interaction + confirmation without
  looking at the PC; the visual surface is a fallback for non-VR users and post-session review.
- **Official-logo compliance:** this slice renders NO logo in any new surface (the audio panel + VM draw no
  logo); the existing Home logo asset is untouched.

## Staged UAT

- **Stage A — Physical TTS:** voice disabled by default (proven by unit tests + the safety suite);
  priority/duration/mute/repeat/adapter-failure fallback proven at the domain level. **Physical TTS on a
  real audio device: NOT RUN.**
- **Stage B — PSVR2 Practice:** run-objective-as-speech + workload gating proven at the domain level.
  **Wearing PSVR2 and driving without viewing the PC: NOT RUN.**
- **Stage C — PTT:** binding, press-and-hold lifecycle, repeat, mute-coaching, status, feedback handling,
  read-back, confirm/cancel, ambiguity → no unintended engineering update — all proven by unit tests.
  **Physical keyboard/controller/wheel-button UAT: NOT RUN.**
- **Stage D — Live GT7 Race strategy:** pre-race plan comparison, fuel divergence, deterministic replan,
  strategy message, acknowledgement (executes nothing), continued monitoring — proven by unit + metamorphic
  tests. **Live GT7 race feed: NOT RUN.**
- **Stage E — Pace divergence:** recalculation + small-noise-no-spam proven by unit tests. **Live: NOT RUN.**
- **Stage F — Time-certain race:** completed-lap projection, extra-stop-loses-a-lap (rejected) and
  extra-stop-gains-a-lap (allowed with assumptions) proven by unit + metamorphic tests. **Live: NOT RUN.**
- **Stage G — Driver-reported conditions:** rain/damage read-back + driver-reported confidence labelling +
  no fabricated telemetry proven by unit tests. **Physical voice UAT: NOT RUN.**
- **Stage H — Failure & recovery:** voice failure → visual fallback; telemetry loss → reduced confidence,
  no message storm — proven by unit tests. **Physical device disconnect UAT: NOT RUN.**
- **Stage I — Full VR experience:** **NOT RUN** (requires PSVR2 + a live race).

Each Stage-I item (info-without-screen / per-discipline audio / practical PTT in VR / no overwhelm / clear
strategy updates / explained changes / user control / post-session detail / NGR feel / no hidden mutation)
is marked **NOT RUN** pending PSVR2 + live-race UAT.

## Certification (do-not-fabricate honoured)

`audio_strategy_certification()` = per-area (23 areas): deterministic domain areas AUTOMATED; physical-
audio / microphone / wheel-button / PSVR2 / live-GT7-race areas = **NONE** with required-next-evidence.
Overall bounded below OPERATIONALLY_READY. Automated tests did NOT grant physical voice, microphone,
wheel-button, PSVR2 usability, or live GT7 race-strategy certification.

## Proof by category

- **Source inspection:** no-AI/no-network/no-keys/no-new-listener; DB-free + Qt-free domain; Apply + voice
  gates untouched (`tests/test_phase63_65_safety.py`).
- **Unit tests:** audio priority/workload/window/state; PTT grammar/reports/feedback/read-back; strategy
  objectives/divergence/projections/candidates/decision/message/monitor.
- **Property/metamorphic:** voice cannot alter strategy maths; PTT/ack execute nothing; ambiguous speech
  changes nothing; unavailable weather never becomes verified rain; small noise never spams; material fuel
  divergence changes ranking; time-certain never trades completed laps for a faster average; stale
  telemetry never high-confidence; event switch invalidates stale work.
- **Runtime-DB / static-snapshot:** the production build touches no DB; PTT binding config is dict-isolated.
- **Offscreen UI:** panel construction + rendering; dashboard stale-worker rejection.
- **Deterministic replay / manual visual / live GT7 / physical TTS / physical mic-PTT / PSVR2:** NOT RUN.
