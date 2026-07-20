# UAT — Engineering Brain Phase 66–68 (Canonical Live Race State, Physical VR Comms, Certification)

Branch `eng-brain-phase66-68-live-vr-certification` from `eng-brain-phase63-65-vr-adaptive-strategy @
fddfb17` (authoritative merged base `master @ 26c0975`). Developed headlessly. **Manual visual UAT, live
GT7 telemetry, physical TTS, physical microphone/PTT and PSVR2 driving were NOT run in this environment.**

Evidence categories (strict): source inspection · unit tests · property/metamorphic tests · runtime-DB
tests · static snapshots · deterministic replay · offscreen UI · manual visual UAT · live GT7 telemetry ·
physical TTS · physical microphone · physical PTT · PSVR2 driving.

## `/ui-ux-pro-max` design gate (mandatory)

**Invoked** before designing the live-strategy status, PTT binding workflow, mic/recognition status,
strategy-update presentation, acknowledgement/telemetry-limitation/recovery states, PSVR2 setup checks,
certification displays and garage strategy review (before the Phase-67 UI).

- **Received:** contrast ≥4.5:1; always-visible status feedback; meaning by text+tag not colour; one
  primary action/message; progressive disclosure; tabular figures; labelled form steps; explain unavailable
  states rather than hiding them.
- **Adopted:** PTT binding as a labelled step form (select type → press-to-bind → show → test → clear →
  restore-default) with inline conflict + unavailable-device messaging; always-visible mic/recognition
  status; a PSVR2 readiness pass/fail checklist (TTS ok / PTT bound / voice enabled; mic optional); per-area
  **and** overall certification shown SEPARATELY as a card list (NONE areas neutral + required-next-evidence);
  detailed candidate tables in the garage panel, not while driving; recovery cards for voice/telemetry loss.
- **Rejected / deferred:** a live QTimer cadence and a full Live-tab redesign (deferred; the audio panel +
  binding panel are additive); rich device pickers (best-effort enumeration only).
- **Supports the no-screen driver:** essential info is SPOKEN (priority-ordered, workload-gated, concise);
  PTT (press-and-hold) drives interaction + read-back confirmation without looking at the PC; the binding /
  readiness / certification surfaces are garage-only (never needed while driving); the visual panels serve
  non-VR users and post-session review. **No NGR logo rendered/altered in any new surface.**

## Staged UAT

- **Stage A — Real live-state mapping:** tracker→canonical mapping, race clock, fuel, pace, pit state, and
  the panel leaving INSUFFICIENT_EVIDENCE with a valid feed — proven by unit + metamorphic tests. **Live GT7
  feed: NOT RUN.**
- **Stage B — Physical TTS:** disabled-by-default + priority/interrupt/mute/repeat/failure proven at the
  domain level. **Physical TTS on a real device: NOT RUN.**
- **Stage C — Physical PTT:** binding, press-and-hold lifecycle, status/plan requests, rain report, read-back,
  cancel-ambiguous, no unintended mutation — proven by the runtime-controller tests (fakes). **Physical
  keyboard/controller/wheel UAT: NOT RUN.**
- **Stage D — PSVR2 Practice:** objective-as-speech, workload-safe advisories, PTT, garage review — proven at
  the domain level. **PSVR2 driving: NOT RUN.**
- **Stage E — Live Race fuel divergence / F — pace & tyre / G — time-certain:** replanning, thresholds,
  extra-stop-loses/gains-a-lap, deterministic ranking + explanation — proven by unit + metamorphic tests.
  **Live GT7 race: NOT RUN.**
- **Stage H — Driver reports:** rain/damage read-back + driver-reported labelling + confidence — proven by
  unit tests. **Physical voice UAT: NOT RUN.**
- **Stage I — Recovery:** telemetry loss degrades honestly (no high-confidence replan, no message storm),
  mic disconnect → visual fallback — proven by unit tests. **Physical device UAT: NOT RUN.**
- **Stage J — Full VR Race experience:** **NOT RUN** (requires PSVR2 + a live race). Each of the 10 items
  (audio-only info / usable PTT / concise messages / discipline-distinct behaviour / explained changes /
  advisory pit recommendations / no hidden mutation / post-drive detail / NGR-team feel / no headset removal)
  is marked **NOT RUN**.

## Certification (do-not-fabricate honoured)

`live_vr_certification()` = per-area (31): deterministic domain AUTOMATED; Live-tab card + visual fallback
OFFSCREEN; physical-audio / microphone / keyboard-controller-wheel PTT / PSVR2 / live-GT7 binding-debrief-
learning = **NONE** with required-next-evidence. Overall **NOT_TESTED**. No physical/live certification was
awarded from automated substitutes.

## Proof by category

- **Source inspection:** no-AI/network/keys/cloud-recognition; no new listener; DB-free + Qt-free domain;
  Apply + voice gates intact (`test_phase66_68_safety.py`).
- **Unit tests:** canonical mapping, clock, fuel/pace/tyre/pit, cadence, tie-breaks, adapters, coordination,
  binding, PTT lifecycle, certification, PSVR2 readiness.
- **Property/metamorphic:** identical telemetry → identical decision; live packet cannot write DB; audio
  device cannot alter strategy; PTT cannot apply a setup; ack cannot execute a pit; uncertain recognition
  cannot update race state; telemetry loss never high-confidence; time-certain never trades completed laps;
  confirmed pit not double-counted; identical conditions do not spam; event switch invalidates stale work;
  driver-reported rain never verified.
- **Runtime-DB / static-snapshot / offscreen-UI:** production build touches no DB; PTT binding dict-isolated;
  panel construction + dashboard stale-worker rejection.
- **Deterministic replay / manual visual / live GT7 / physical TTS / physical microphone / physical PTT /
  PSVR2 driving:** NOT RUN.
