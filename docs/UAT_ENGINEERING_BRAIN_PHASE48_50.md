# UAT — Engineering Brain Phase 48–50 (Event Preparation Cycle & Immersive Race Weekend)

Branch `eng-brain-phase48-50-event-preparation-cycle`. This slice was developed headlessly. Offscreen
Qt construction and deterministic domain/persistence tests were executed; **live-GUI visual UX and live
GT7 telemetry UAT were NOT run in this environment**. Each stage below is marked with what was actually
proved and by what means.

Legend: PASS (automated) · PARTIAL (core proved automatically; live visual/GT7 step not run) ·
NOT RUN (requires a live session).

## `/ui-ux-pro-max` design gate (mandatory)

Invoked before any UI work (commit 10). Query: professional motorsport race-engineering desktop
dashboard, timeline, dark, data-dense.

**Primary recommendations received:** Real-Time / Operations information architecture (status/metrics
first, data-dense but scannable); Dark Mode (OLED) with green/amber/red status colours; tabular /
monospaced numerals for data columns and timers; visual hierarchy via size/spacing/contrast, not colour
alone; one primary action per surface; SVG (not emoji) iconography; 150–300 ms hover transitions.

**Adopted:** the Real-Time/Operations IA (preparation home = next-action banner + horizontal timeline
strip + status/progress/convergence/strategy/readiness cards); dark high-contrast status tones reused
from the existing NGR theme; every card/timeline node carries a **text status tag + tone** (never colour
alone); tabular numerals for laps/counts/countdown; advisory tint on read-only surfaces so they never
read as an actionable Apply; a single clear next-action per surface; horizontal timeline scrolls inside
its own region (page body never scrolls horizontally).

**Not adopted / deferred (with reasons):** the engine's *Fira Code / Fira Sans + blue/amber palette* and
the *landing-hero/CTA* framing — rejected to preserve the established NGR brand design system
(`ui/ngr_theme.py`) for cross-app consistency (the "consistency" rule outranks a font/colour swap); the
*top-level Home-screen navigation restructure* making the preparation cycle the literal Home spine —
deferred because it is a high-risk change to a ~9000-line `dashboard.py` that cannot be visually
validated headlessly. The panels are instead placed in the proven Development History surface consistent
with every prior eng-brain slice, and the Home-spine integration is recorded as the recommended next
step.

## Staged results

### Stage A — Monthly Porsche Cup preparation — PASS (automated)
Event opening three weeks before race day, six Practice activities under ONE cycle, previous learning
retained, next activity/objective clear. Proved by `test_scenario_monthly_porsche_cup_one_programme`,
`test_report_accumulates_evidence_and_stays_context_safe`, `test_cycle_binds_every_activity_to_one_identity`.

### Stage B — Setup development — PARTIAL
Lineage accumulation, failed-direction lockout, working-window maturation and Base/Qualifying/Race
separation proved via `test_phase48_evidence.py` + `test_phase49_convergence.py`. The live "Applied in
Game" Apply flow and on-screen lineage were NOT driven (headless).

### Stage C — Driver development — PARTIAL
A coaching-only run improves driver technique but does NOT alter setup working windows —
`test_coaching_only_run_does_not_touch_setup_or_working_window`,
`test_scenario_optional_coaching_does_not_change_setup`. Live coaching GUI NOT run.

### Stage D — Tyre & fuel modelling — PASS (automated)
Tyre/fuel samples accumulate; incompatible compound / unknown multiplier excluded or capped; strategy
confidence rises only from relevant evidence — `test_phase48_evidence.py`,
`test_phase49_strategy_maturity.py`, `test_scenario_tyre_matures_fuel_capped_by_unknown_multiplier`.

### Stage E — Convergence & lock-in — PARTIAL
Candidate comparison, protected strengths/unresolved risks, and explicit lock (refresh cannot
lock/unlock; post-lock restrictions) proved via `test_phase49_convergence.py` + `test_phase49_setup_lock.py`.
The on-screen lock button interaction was NOT driven.

### Stage F — Strategy finalisation — PARTIAL
Primary/alternative plans, tyre/fuel/pit-loss/pace assumptions, explicit finalisation and visible
low-confidence assumptions proved via `test_phase49_finalisation_risk.py`. The on-screen strategy meeting
was NOT driven.

### Stage G — Official Race Weekend — PARTIAL
Final arrival, briefing acknowledgement, scrutineering verdicts, chief-engineer plan, qualifying, race
briefing and debrief proved via `test_phase50_race_weekend.py`; panels construct and render offscreen
(`test_phase48_50_ui.py`). Live GT7 race and live visual UX were NOT run.

### Stage H — Experience review — NOT RUN
Requires a live visual session to judge whether the three-week preparation *feels* connected to one race
and whether specialist tools feel like departments in one team. Offscreen Qt testing is not full visual
UX UAT; replay is not live GT7 UAT.

## What was proved, by means

- **Source inspection**: authority reuse (no competing event/setup/experiment/outcome/strategy/coaching/
  telemetry/context/voice authority); Apply gate untouched; voice gate owned by `shadow_advisory`.
- **Unit + property/metamorphic tests**: cumulative-evidence invariants, convergence/lock/finalisation
  gates, deterministic fingerprints, context safety, session purpose.
- **Runtime (DB) tests**: v28 migration (fresh/upgrade/idempotent), constant query shape, byte-identical
  DB across reads, viewing creates no rows.
- **Offscreen UI tests**: panel + Development-History-page construction and render.
- **NOT proved here**: live visual UX, live GT7 telemetry, on-screen lock/finalise/apply interactions.
