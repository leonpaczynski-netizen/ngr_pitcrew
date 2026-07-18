# Engineering Brain — Phase 5: Working-Window Learning, Successful-Direction Reinforcement & Minimum-Effective Experiment Selection

**Status:** implemented on branch `eng-brain-phase5-working-window-learning` (from `master` @ Phase 4 `52628af`).
**Schema:** SQLite `user_version` **22 → 23** (`DB_VERSION = 23`). `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** learning + selection over the canonical Phase 1–4 spine — NO generative AI,
no opaque scoring, no vehicle-dynamics physics, no auto-apply/revert, no multi-field
shotgun experiments.

## 1. Problem being solved

Phases 1–4 gave the app identity → experiments → outcomes → canonical evidence.
Phase 5 makes the Engineering Brain LEARN from completed, canonically-evaluated
experiments: it maintains evidence-backed parameter working windows, reinforces
setup-change directions that repeatedly improve a behaviour, blocks directions that
repeatedly worsen it, avoids dead-end retests, and selects the SMALLEST justified
next experiment — while protecting confirmed-good behaviour and staying honest when
evidence is weak, contradictory or unavailable.

## 2. Starting checkpoint

`eng-brain-phase5-working-window-learning` from `master` @ Phase 4 `52628af`
(Phases 2–4 stacked; master at Phase 1). `DB_VERSION 22`, `RULE_ENGINE_VERSION 46.0`.

## 3. Existing authorities reused (not duplicated)

| Concern | Reused |
|---|---|
| Canonical outcome (improved/worsened/…) | Phase 3 `SetupExperimentOutcome` / `OutcomeStatus` — consumed verbatim, never reinterpreted |
| Failed-direction learning | Phase 3 `setup_experiment_failed_directions` + `list_failed_directions_by_scope`; `setup_lineage` `DirectionKey`/`apply_direction_lockout` |
| Canonical evidence | Phase 4 `engineering_lap_validity`, `corner_evidence`, `setup_evidence_assembly` |
| Decision authority | Phase 4 `resolve_setup_decision` (selection is subordinate to it) |
| Field bounds / step | `setup_ranges.resolve_ranges` + `setup_synthesis._round` |
| Interaction / coupling | `setup_synthesis.PARAMETER_INTERACTIONS` + `HANDLING_AXES` |
| Recurrence | `practice_pattern_analysis.RecurrenceThresholds` |
| Per-analysis window | `setup_engineering_context.WorkingWindow` (Phase 5 is the durable layer beneath it) |

## 4. Working-window domain — `strategy/working_window.py` (pure)

A LEARNED working window is a **deterministic function of an append-only evidence
ledger** (one contribution per experiment-outcome), so replay is idempotent and
order-independent.

- `WindowContextKey` — driver + car + track + layout + discipline + field (stable
  hashed key).
- `WindowEvidence` — one experiment's contribution; idempotency key
  `(context_key, experiment_id, outcome_id)`.
- `WindowContribution` — SUCCESSFUL / UNSUCCESSFUL / INEFFECTIVE / NONE, mapped from
  `OutcomeStatus` (confirmed→successful, partial→successful+low-attribution,
  regression→unsuccessful, no_meaningful_change→ineffective,
  confounded/insufficient→none).
- `LearnedWorkingWindow` — successful/unsuccessful/ineffective values, evidence-backed
  low/high bounds + preferred centre, counts, `WindowConfidence`
  (none/provisional/low/medium/high), per-direction `DirectionalEvidence` (with
  lockout), contradiction flag, direct-vs-inherited flag, full provenance.
- `recompute_working_window(evidence, context, legal_low, legal_high)` — the pure
  recompute (de-dupes by identity as a safety net; a regression NARROWS the window
  around the proven centre; a strong single-field regression LOCKS that direction).

**Confidence never over-claims:** one experiment → PROVISIONAL; two → LOW; a
contradiction caps at LOW; HIGH needs ≥5 valid experiments with ≥3 improvements.

## 5. Evidence compatibility hierarchy

Direct context evidence (same driver/car/track/layout/discipline) outranks an
inherited cross-context prior (`is_direct=False` → lower confidence + a warning).
Cross-track/car evidence can seed a hypothesis but is never called direct proof.

## 6. Outcome-to-learning rules

Only a canonically-evaluated outcome teaches values. Confirmed improvement adds a
successful value + reinforces the direction (confidence rises only with quantity +
quality). Confirmed regression records the value/direction as unsuccessful, narrows
the window, locks the direction, preserves the parent rollback target — never
averaged away. No-meaningful-change marks the increment ineffective (reduces
retest priority), not an improvement. Confounded/insufficient/invalid update
metadata only.

## 7–8. Directional reinforcement & failed-direction lockouts

Per (field, direction) tallies of improved/worsened/no-effect. A direction locks
when it repeatedly worsened the target with **no compatible improvement** (one
strong single-field regression, or two weaker). A later confirmed improvement in the
same direction lifts the lockout (audited via the evidence ledger). Compound
(multi-field) experiments carry low attribution confidence → no hard field-level
lockout; an isolation follow-up is preferred.

## 9. Dead-end experiment prevention

`strategy/experiment_selection.py` HARD-blocks a candidate (visible reason, never an
invisible penalty) when it: repeats a failed direction, repeats an ineffective
direction, proposes an illegal/at-current/no-measurable-delta value, lands on a
disproved value, sits outside the evidence window without justification, is
non-reversible, or touches a protected-behaviour field.

## 10. Candidate generation — `strategy/experiment_selection.py`

`generate_candidates(SelectionContext)` maps the dominant symptom → a target
handling axis (`_SYMPTOM_AXIS`), finds the fields that move that axis in the desired
direction (from `PARAMETER_INTERACTIONS`), and proposes ONE legal step of ONE field
in the improving direction — a physics-informed HYPOTHESIS to test, never a generic
symptom→value lookup, never a universal "best" value. Each `CandidateExperiment`
carries hypothesis, expected positive/negative effects (coupled axes), protected
behaviours at risk, evidence grade, window/prior/directional relationships,
eligibility + hard blockers, and reversibility.

## 11–12. Deterministic selection & test protocol

`select_experiment(...)` runs 5 stages: (0) subordinate to the decision authority;
(1) hard eligibility; (2) evidence sufficiency (defers below the recurrence / valid-
lap thresholds); (3–4) experiment quality with a **stable documented tie-break**
(single-field isolation → least protected-risk → fewest coupled negatives → strongest
evidence → field-name order — no DB/dict/clock/random dependence); (5) honest
`NoSelectionReason` when nothing is justified. `build_test_protocol(...)` emits a
deterministic plan (value change, rollback target, min valid laps, target corners,
lap-invalidation conditions, success/regression/rollback criteria, driver questions,
required evidence) — inventing no GT7 environmental data.

## 13. Per-corner producer unification — `strategy/corner_evidence.py`

`from_corner_slip_aggregate(...)` adapts run-keyed `corner_slip_telemetry`
(`CornerTelemetryAggregate`) into canonical `CornerObservationRecord`s at LOWER
confidence — `lap_number=None`, `occurred_on_lap=False`, so slip evidence can NEVER
inflate distinct-affected-valid-lap recurrence. `unify_corner_observations(occ, slip)`
merges both producers, de-duplicating a physical event only on an explicit stable
identity match — same (segment, phase, issue, axle) AND the same session or applied
checkpoint (never a mere shared label). >1 distinct session → AMBIGUOUS (kept,
flagged); an unlinked slip (no session/checkpoint) is kept but ineligible for
outcome comparison — linkage is never fabricated from timing. The `UnificationAudit`
reports included / duplicates_removed / ambiguous / unlinked / source counts /
distinct affected valid laps.

## 14. Canonical lap-validity caller migration

`strategy/practice_capture.resolve_clean_lap` is now a **compatibility adapter** that
delegates to `strategy/engineering_lap_validity` (`LapPurpose.PRACTICE_PATTERN` with
the caller's pace ratio) — so the Practice and Perfect-Lap live paths route through
the ONE canonical authority. Behaviour is preserved (valid + positive time + within
the pace-outlier ratio); the engineering plausibility floor is relaxed for this
pace-focused purpose so no documented behaviour changed. Purpose policies
(SETUP_ENGINEERING / OUTCOME_COMPARISON strict, PRACTICE_PATTERN, PERFECT_LAP_REFERENCE,
RACE_STRATEGY fuel-focused) and every rejection reason are intact.

## 15. Persistence — DB schema v23 (additive, two tables)

`_migrate_v23` (`CREATE IF NOT EXISTS` ⇒ idempotent):
- **`setup_working_window_evidence`** — the APPEND-ONLY source-of-truth ledger.
  `UNIQUE(context_key, experiment_id, outcome_id)` ⇒ replaying the same outcome
  contributes exactly once (idempotent). Indexed by context, (scope, field),
  experiment.
- **`setup_working_windows`** — the MATERIALISED cache (`UNIQUE(context_key)`),
  recomputed from the ledger on each learn (deterministic; never a source of truth).

Every learned update traces to experiment + outcome + applied checkpoint + scope
fingerprint + delta. No new telemetry table (the corner producers are read, not
duplicated).

### Orchestrators (SessionDB)

- `learn_from_experiment_outcome(experiment_id)` — outcome → per-field evidence →
  persist (idempotent) → recompute windows. Only a completed canonical outcome teaches.
- `select_next_experiment(experiment_id, ...)` — build `SelectionContext` from
  learned windows + failed-direction learning + current setup → generate → select.
- `review_and_learn(experiment_id, ...)` — the full runtime step: review (Phase 4
  assembly + Phase 3 evaluate) → learn → select. Read-only w.r.t. the setup.
- `get_working_window`, `list_working_windows`.

## 16. UI integration

The off-thread "Review Test Outcome" worker now calls `review_and_learn` (was
`review_experiment_outcome`). `_display_outcome_result` additionally renders: learned
working-window updates, the selected minimum-effective next experiment (field, exact
value change, rationale), a blocked alternative with its reason, or an honest
no-selection state (retain / gather more evidence). Structured label text; no
whole-dashboard redesign; no new decision surface; no Apply/Revert from review.

## 17. Safety guarantees

Fully local / offline / deterministic; no generative AI / network / API key; no
auto-apply / auto-revert / pit call; the frozen Apply-gate predicate, fan-out
allowlist, golden `config_id`, engine-wiring-status and `RULE_ENGINE_VERSION 46.0`
are unchanged; the dormant `arbitrate_setup_decision` stays dormant; `resolve_setup_
decision` remains the runtime decision authority; pure modules import no Qt/DB/UI/AI
and write no files; no random or wall-clock ordering.

## 18. Tests added (by file)

- `tests/test_phase5_working_window.py` (21) — domain + update-engine + property.
- `tests/test_phase5_experiment_selection.py` (18) — candidate gen + selector + property.
- `tests/test_phase5_corner_unification.py` (10) — producer unification / dedup.
- `tests/test_phase5_lap_validity_migration.py` (15) — caller migration + purpose policies.
- `tests/test_phase5_persistence.py` (10) — v23 migration, idempotent learning, restart.
- `tests/test_phase5_golden_uat.py` (11) — Scenarios A–J + frozen contracts.
- `tests/test_phase5_wiring.py` (11) — UI/threading + architecture safety.

## 19. Known limitations

- Selection targets a single dominant symptom per call; multi-symptom prioritisation
  is left to the caller/UI.
- The `SelectionContext` corner/recurrence inputs to `review_and_learn` are derived
  from the reviewed experiment's diagnosis; a richer live per-corner residual-issue
  detector is a Phase 6 refinement.
- Cross-context (inherited-prior) seeding is represented (`is_direct`) but the
  automatic promotion of a like-car/other-track window into a starting prior is not
  yet wired into candidate generation.

## 20. Deferred work

Multi-symptom experiment queuing; automatic inherited-prior seeding of candidates;
merging the two live per-corner producers at write-time (Phase 5 unifies at read
time); a dedicated learned-window UI panel (the current surface is the outcome
summary).

## 21. Manual UAT procedure

See §16 of the task brief. Deterministic offline harness: create an RSR/Fuji
experiment, apply a single-field change, provide baseline + checkpoint-tagged test
evidence, `review_and_learn`, confirm a confirmed improvement reinforces the
direction (window PROVISIONAL, value recorded), a regression locks the direction and
blocks its re-selection, an unchanged result marks the increment ineffective,
restart reproduces the same next experiment, and no evidence is double-counted.

## 22. Recommended Phase 6

Phase 6 — Live Residual-Issue Detection & Multi-Symptom Experiment Planning: derive
the dominant residual issue + recurrence live from the unified per-corner evidence
(rather than the prior diagnosis), queue minimum-effective experiments across several
symptoms with protected-behaviour arbitration, and auto-seed inherited-prior windows
into candidate generation — all on the Phase 5 learning + Phase 1–4 evidence spine.
