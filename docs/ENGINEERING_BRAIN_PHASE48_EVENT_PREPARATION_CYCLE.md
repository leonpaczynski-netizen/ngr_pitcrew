# Engineering Brain — Phase 48: Canonical Event Preparation Cycle

Program 2, Phase 48. Branch `eng-brain-phase48-50-event-preparation-cycle`. Read-only, deterministic,
offline, no AI. Introduces **Layer B** (the preparation programme) additively over Layers A/C/D — see
`NGR_EVENT_PREPARATION_ARCHITECTURE.md`.

## Doctrine

An NGR race event is not a self-contained weekend. Between rounds a driver runs a *preparation cycle*
that may span an evening or several weeks. **Every valid Practice session bound to one upcoming round
feeds the same cumulative engineering programme** — sessions are never treated as disconnected
mini-events, and a new session never resets prior evidence.

Flexible duration: one evening (span 0), several days, a week, three weeks, a month, or any gap — all
valid. A long quiet gap is not an error and never auto-abandons or auto-completes a cycle.

## Modules

- `strategy/event_preparation_cycle.py` — identity + timeline + activity model. `EventPreparationCycle`,
  `EventPreparationCycleIdentity`, `PreparationCycleState` (5), `PreparationPhase` (17), `PHASE_ORDER`,
  `PreparationActivityType` (22), `PreparationActivityState` (10), `PreparationTransitionDecision` (17),
  `OfficialSession`/`OfficialSessionType`, `PreparationDeadline`, `EventMilestone`, `EventFormatProfile`,
  `PreparationActivity`, `PreparationObjective`, `PreparationReadiness`/`ReadinessLevel`,
  `PreparationProgress`, `PreparationTimeline`. Built-in NGR-neutral profiles: `multiweek`,
  `single_evening`, `multi_race`, `endurance` (skipped phases are always explicit). `build_preparation_timeline`
  (date-ordered, shuffle-stable, no forced "Week 1/2/3"), `build_event_preparation_cycle`.
- `strategy/preparation_transitions.py` — deterministic `evaluate_activity_transition(s)` and pure
  scheduling transforms (`reschedule/cancel/skip/mark_optional/bind_session`) that return NEW values and
  never persist.
- `strategy/preparation_evidence.py` — cumulative Practice evidence (§8). `PracticeEvidenceSample`,
  `EvidenceCompatibility` (exact/partial/incompatible/unknown), `EvidenceDomain` (10), `_TYPE_DOMAINS`
  (the session-purpose map), `ConfidenceLevel`, `DomainEvidence`, `CumulativePreparationEvidence`,
  `build_cumulative_evidence`, projections `to_readiness/to_progress/to_objective`.

## Cumulative evidence invariants (§8)

- **Session purpose** is structural: `_TYPE_DOMAINS` maps each activity type to the only domains it can
  feed. A coaching-only run feeds `driver_coaching` only (never setup/working-window); a fuel test feeds
  `fuel_model` only (never promotes a setup); a qualifying simulation feeds the qualifying setup (never
  the race setup). Base / Qualifying / Race setups stay separate.
- **Context safety**: `EXACT` strengthens the exact conclusion; `PARTIAL` is counted, labelled and caps
  the domain; `INCOMPATIBLE` contributes nothing (never strengthens exact); `UNKNOWN` (e.g. unknown fuel
  multiplier) counts as partial and caps. Per-domain overrides let one long run be exact for pace yet
  unknown for fuel.
- **Monotonic membership**: adding a valid session only adds sessions; an invalid session adds nothing
  and can never raise confidence. A single quick sample never yields STRONG.

## Determinism

Semantic fingerprints (sorted-key ASCII JSON, `allow_nan=False`, version-prefixed sha256[:24]) cover
identity / profile / official sessions / ordered activity membership + status / timeline / readiness /
span. They **exclude** the display countdown (`days_until_race`, from an injected `now_date`), widget/
page/machine identity, paths, wall-clock and random ids. Proven stable across shuffled input and
different injected `now_date`. Viewing/refresh recomputes a pure view and never advances cycle state.

## Persistence (v28)

Three additive tables (`event_preparation_cycles`, `event_preparation_activities`,
`event_preparation_activity_sessions`) referencing `events.id`. Sole writers:
`SessionDB.upsert_preparation_cycle` / `upsert_preparation_activity` / `bind_session_to_activity`
(sessions are **never** auto-bound). `get_practice_sessions_for_cycle` is the event-scoped Practice
query the flat `sessions.event_id` column never provided. `build_event_preparation_report` resolves
cycle/activities/bound-sessions once (constant query count, no N+1) and writes nothing.

## Tests

`test_phase48_cycle_identity.py` (15), `test_phase48_transitions.py` (11), `test_phase48_evidence.py`
(18); plus the shared persistence/golden/safety suites. See `MASTER_TESTING_REGISTER.md`.
