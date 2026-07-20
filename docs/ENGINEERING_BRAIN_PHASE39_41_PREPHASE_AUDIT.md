# Engineering Brain — Program 2, Phases 39–41: Pre-Phase Audit & Remediation

Read-only, offline, deterministic. This document records the mandatory pre-phase audit (A–D) that
governs the Phase 39–41 closed-loop slice, the findings, and where each is remediated. DB stays
**v26**; rule engine **46.0**; `strategy/_setup_constants.py` unchanged.

## Audit A — Context filtering before aggregation

**Finding: REMEDIATION REQUIRED.** The shared `SessionDB._build_knowledge_chain` builds the Phase-22
programme knowledge (`build_programme_knowledge_report`) whose compatibility group is
`COMPATIBILITY_FIELDS = (car, discipline, gt7_version, driver)` — it deliberately **excludes track,
layout and compound** ("same car / discipline / GT7 version / driver — different tracks may merge";
the Phase-22 graph even emits an "evidence spans N track(s)" limitation). The single bounded evidence
read `_timeline_evidence_records(car, discipline, gt7_version, driver)` returns records across **all**
tracks/layouts/compounds. Therefore Phase 22–32 maturity, convergence, assurance grade and priority
are computed over **cross-track** evidence **before** any Phase-36 context classification.

Note: the Phase-37 outputs delivered in the previous slice (working windows, setup-outcome learning,
driver-development, coaching) were already built **only** from the Phase-36 `EXACT_CONTEXT` records, so
those specific outputs are context-safe. The contamination risk is confined to the Phase 22–32
aggregates and anything that consumes them for an *exact-context* conclusion.

**Remediation (Phase 39):** a new `strategy/context_scoped_chain.py::ContextScopedKnowledgeChain`
classifies every raw record against the current `EngineeringContextScope` **first**, then builds
exact-context conclusions from exact records only, keeps a separate explicitly-transferable overlay,
and excludes reference-only / excluded / unverifiable evidence from every exact-context aggregate. The
closed loop (Phases 40–41) consumes the context-scoped chain, never the cross-track Phase 22–32
aggregates, for exact-context reasoning. Metamorphic proof: adding 100 incompatible Daytona records
leaves Fuji exact-context evidence counts, convergence, working windows and best-known eligibility
byte-identical (they are functions of the exact record set only).

## Audit B — Multi-field regression attribution

**Finding: REMEDIATION REQUIRED.** The previous-slice `strategy/setup_outcome_learning.py` blocks
**every** changed `(field, direction)` in a worsened record. For a single-field change that is correct
field-level causation; for a **multi-field** change it silently converts correlation into field-level
causation.

**Remediation (Phase 39):** `strategy/regression_attribution.py` introduces
`RegressionAttribution` with states `BUNDLE_REGRESSION_CONFIRMED`, `FIELD_DIRECTION_SUSPECT`,
`FIELD_DIRECTION_CONFIRMED`, `INTERACTION_SUSPECTED`, `ATTRIBUTION_INSUFFICIENT`. A multi-field
worsened delta blocks the **bundle** immediately but marks each field `FIELD_DIRECTION_SUSPECT`. A
field only becomes `FIELD_DIRECTION_CONFIRMED` with corroboration: a single-field controlled
experiment, independent repeated experiments, valid reversal evidence, a strong canonical mechanism +
matching telemetry, or independently corroborated outcome history. The existing conservative
bundle-block (safety) is retained; the attribution layer qualifies causal confidence and drives an
"isolate / reverse the bundle" next action.

## Audit C — Driver attribution independence

**Finding: REMEDIATION REQUIRED.** The previous-slice `driver_development_state.py` treats "persists
across ≥2 setups" (distinct changed-field signatures) as evidence of driver technique. Two setups that
differ only in a field **irrelevant to the observed handling mechanism** are not materially
independent, so this over-attributes to the driver.

**Remediation (Phase 39):** `strategy/setup_independence.py::assess_setup_independence` deterministically
evaluates whether two setups are materially independent **for a given behaviour's mechanism**
(which fields changed, magnitude, whether the changed fields *should* influence that behaviour, shared
parent/narrow family, persistence across *relevant* variation, repeated lap/session evidence,
driver-input evidence, track/car explanations). Attribution states: `SETUP_LIKELY`,
`DRIVER_TECHNIQUE_LIKELY`, `TRACK_OR_CAR_CHARACTERISTIC`, `COMBINED_DRIVER_SETUP`,
`INTERACTION_UNRESOLVED`, `INSUFFICIENT_EVIDENCE`. Persistence across setups that vary only in an
irrelevant field yields `INTERACTION_UNRESOLVED` / `INSUFFICIENT_EVIDENCE`, never
`DRIVER_TECHNIQUE_LIKELY`.

## Audit D — Qt test harness

**Finding: TEST-HARNESS DEFECT (RESOLVED — no product change).** The UI off-thread tests drove the ONE
shared `QApplication` with `app.exec()` + `QTimer.singleShot(..., app.quit)`. Running many such tests
in one process corrupted the shared loop (a prior test's queued `quit` made a later `app.exec()` return
before the worker ran), producing 10 intermittent `test_worker_runs_build_off_ui_thread` failures in
combined runs that passed in isolation.

**Resolution:** `tests/_qt_worker_wait.py::drive_worker` replaces the nested/repeated application
`exec()` with deterministic waiting — it starts the `QThread`, joins it with `QThread.wait` (no event
loop), then drains the queued cross-thread signal to the main thread via `QApplication.processEvents`.
All 23 UI off-thread tests (Phases 13–38) were migrated to it. **The production worker, its signals,
the off-thread guarantee and the stale-worker guard are unchanged** — this is strictly a test-harness
fix. Combined run: previously `10 failed / 707 passed` → now `717 passed / 0 failed`; the full
UI+runtime combined run is `203 passed / 0 failed`.

## Summary

| Audit | Class | Status | Remediation |
| --- | --- | --- | --- |
| A | Product architecture | Remediated in Phase 39 | `ContextScopedKnowledgeChain` (classify-before-aggregate) |
| B | Product model | Remediated in Phase 39 | `RegressionAttribution` (bundle vs field) |
| C | Product model | Remediated in Phase 39 | `SetupIndependenceAssessment` |
| D | Test harness | Resolved | `drive_worker` deterministic wait (test-only) |
