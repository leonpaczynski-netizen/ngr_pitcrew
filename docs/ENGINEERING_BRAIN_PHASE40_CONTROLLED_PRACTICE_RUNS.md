# Engineering Brain — Program 2, Phase 40: Controlled Practice Runs & Execution Plan

Read-only, offline, deterministic, advisory-only. Part of the **Phases 39–41 Closed-Loop Development**
slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose & authorities

`strategy/engineering_run_plan.py` builds a deterministic advisory `EngineeringRunPlan` for testing ONE
existing candidate. `strategy/run_candidate_selection.py` selects/links the highest-value **existing**
Phase-17 portfolio candidate. Neither creates, persists, schedules or applies anything.

## Phase-17 candidate linkage

`select_run_candidate(valuations, ...)` drops retired/superseded candidates and any that risk a
confirmed-good protection, ranks by engineering value then single-field-first, and returns an
`ExperimentCandidateLink` (`is_existing`, `preflight_required`). The candidate is **referenced**, never
created; any real experiment/outcome/setup change stays in the existing explicit workflow, preflight and
the frozen Apply gate.

## Controlled changes & held-constant

`ControlledChangeSet`: exact fields, current value, proposed direction, why, expected mechanism,
interactions, rollback value. **Minimum effective intervention** — one field → `SINGLE_MECHANISM`; a
coupled bundle → `COUPLED_BUNDLE` (reduced causal confidence; individual field conclusions not
promoted, with a stated coupling reason). `HeldConstantSet`: every other applied field + technique
variables, compound, fuel-load window, tyre-age window, weather/track-state, assists, brake-balance/fuel
map. Any unlisted setup field that moves invalidates the run.

## Run structure, expected result, validity gate & stop conditions

`EvidenceCollectionPlan`: warm-up / measurement / minimum-clean / maximum laps, target corners, target
metrics (race adds tyre-degradation/fuel/stint; qualifying adds peak-grip/out-lap prep), required
driver feedback, comparison baseline. Expected result: primary outcome, protected behaviours, tolerated
trade-offs, unacceptable regressions, success/failure/inconclusive thresholds, falsifying observation.
`RunValidityGate`: the planned compound was used; only the controlled field(s) changed; the minimum
clean-lap count was met; fuel/tyre within windows; weather stable; no undisclosed technique change;
complete, uninterrupted telemetry; the discipline matches (a qualifying run does not validate a race
setup). Stop conditions: immediate stop (protected regression / instability / condition change), review
(confounded / unplanned change / incomplete telemetry), disposition (abandon/reverse/repeat/refine).

## Held-constant & discipline doctrine

Base / Qualifying / Race objectives are distinct (`_OBJECTIVE`). Qualifying optimises one-lap pace, tyre
prep, peak grip, braking/rotation confidence, acceleration onto straights and one-lap gearing. Race
optimises total race time, repeatability, tyre life, traction, fuel, stint stability, traffic, pit
implications and race gearing. A qualifying experiment is never auto-transferred to the race setup.

## Event-near deadline posture

With little practice time before a near event (and only high-interaction candidates), the selector
declines to a `PROTECT` posture and the plan sets a deadline posture: protect the current best-known
setup and collect low-risk evidence rather than start a high-interaction experiment.

## SessionDB entry & query shape

`build_engineering_run_plan_report`: resolves context once, builds the context-scoped exact chain +
Phase-37 products in memory, composes the Phase-17 portfolio **once**, selects the candidate and builds
the plan. Constant query shape; writes nothing.

## Safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; no setup values; creates/persists/applies/
schedules nothing; references only. With no candidate it yields a truthful collection run.
