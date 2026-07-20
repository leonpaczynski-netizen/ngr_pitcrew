# UAT — Engineering Brain Phase 51–53 (Event Command Centre, Live Orchestration, Certification)

Branch `eng-brain-phase51-53-event-command-centre`. Developed headlessly. Offscreen Qt construction and
deterministic domain/persistence tests were executed; **live-GUI visual UX and live GT7 telemetry UAT
were NOT run in this environment.** Legend: PASS (automated) · PARTIAL (core proved automatically; live
visual/GT7 step not run) · NOT RUN.

## `/ui-ux-pro-max` design gate (mandatory)

Invoked before the Home view-model + navigation (commit 3). Query: operations command centre home,
next-action hierarchy, live pit-wall low-density, event selector, dark.

**Recommendations received:** Real-Time/Operations IA (status/metrics first); Dark Mode + green/amber/red
status; one primary CTA; loading-state feedback for async; tabular numerals; heading hierarchy.
**Adopted:** status hero + ONE primary action + key metrics + timeline + navigation; loading state during
the off-thread refresh; explicit event selector (never auto-pick); NGR status tones; tag-not-colour.
**Rejected/deferred:** the engine's Fira/blue-amber palette and marketing hero/CTA framing (kept the NGR
brand and a status hero). NGR immersion: the active event is the first Home surface, the next action is
one prominent card, the timeline communicates weeks of preparation, and specialist tabs are reached as
"departments" via quick actions.

## Staged results

- **Stage A — Primary Home (monthly Porsche Cup):** PARTIAL. Command Centre is the first Home widget;
  next action, timeline, cumulative learning and specialist navigation proved via
  `test_phase51_command_centre*`, `test_phase51_dashboard_integration`, `test_phase51_53_golden`. Live
  visual layout NOT run.
- **Stage B — Multiple events:** PASS (automated). Explicit selection required, never newest-by-default;
  evidence does not cross-contaminate (`resolve_active_cycle`, candidate-payload invariance).
- **Stage C — Live Practice:** PARTIAL. Start readiness, live view, binding, debrief handover and
  cumulative update proved via `test_phase52_*`; live GT7 telemetry NOT run.
- **Stage D — Restart & recovery:** PASS (automated). Interrupted-not-complete, recovery classification,
  no fabricated completion (`test_phase53_resume`).
- **Stage E — Qualifying:** PARTIAL. Low-density mode proved (`test_phase52_live_modes`); live NOT run.
- **Stage F — Race:** PARTIAL. Safety-focused mode, no pit commands, learning carry-forward proved; live
  NOT run.
- **Stage G — Event revision:** PASS (automated). Impact assessment, completed history unchanged, lock/
  strategy reopening where justified (`test_phase53_revision_reopen_cert`).
- **Stage H — Visual experience:** NOT RUN (requires a live visual session).

## Operational certification (this slice)

Per-area proof: domain areas (active-cycle resolution, live activity, binding, resume, revision, lock-
reopening, certification) = **AUTOMATED**; UI areas (Home Command Centre, panel) = **OFFSCREEN**; live
areas (live GT7 practice/qualifying/race, visual UX) = **NOT_TESTED / not run**.

**Overall `OperationalCertification` state: `AUTOMATED_ONLY`** — bounded by the weakest area. Live and
operational certification are deliberately unreachable here: they require live-GT7 evidence and cannot be
granted from automated/offscreen tests alone. No live or operational certification is claimed.

## What was proved, by means

- Source inspection: authority reuse (no competing event/setup/experiment/outcome/strategy/session/voice
  authority); Apply gate + voice gate untouched; Home refresh writes nothing.
- Unit + property/metamorphic tests: resolution, next-action, start-readiness, completion gate, binding,
  cumulative update, resume, dropout, revision, lock-reopening, certification bounds.
- Runtime (DB) tests: read-only Command Centre view, constant query shape (1/20 sessions), byte-identical
  DB across refreshes.
- Offscreen UI tests: panel + Home construction, off-thread build, stale-worker rejection, handlers.
- NOT proved here: live visual UX, live GT7 telemetry, on-screen live/lock/finalise interactions.
