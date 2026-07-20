# Engineering Brain — Phase 4: Canonical Evidence Authorities, Unified Clean-Lap Semantics & Live Per-Corner Outcome Assembly

**Status:** implemented on branch `eng-brain-phase4-canonical-evidence` (from `master` @ Phase 3 `6314c05`).
**Schema:** **NO migration** — `DB_VERSION` stays **22**, `RULE_ENGINE_VERSION` stays `46.0`.
**Nature:** evidence authorities + live wiring only — NO new physics, NO new setup
rules, NO new outcome evaluator, NO auto-apply/rollback, NO UI redesign.

## Why

Phases 1–3 built identity → experiments → outcomes, but the live outcome review
could not assemble per-corner baseline/test evidence from runtime telemetry (it
passed *nothing* for corner evidence, so every per-corner criterion fell to
UNMEASURABLE). Phase 4 makes all Engineering-Brain decisions use the SAME answers
to: is this lap valid for setup engineering? why accepted/rejected? which setup /
experiment / corner / phase does the evidence belong to? is an issue isolated /
emerging / recurring / strongly-recurring? what baseline/test should Phase 3
compare? what decision state should be shown?

## Deliverables (four composed authorities)

### 1. Canonical engineering lap-validity authority — `strategy/engineering_lap_validity.py`

`evaluate_engineering_lap(lap_row, *, purpose, ...) -> EngineeringLapValidity` +
`evaluate_session_laps(...) -> (verdicts, LapValiditySummary)`.

- **States:** VALID / VALID_WITH_LIMITATIONS / INVALID / UNRESOLVED.
- **Purpose-specific policy (one authority, per-purpose knobs)** `LapPurpose`:
  SETUP_ENGINEERING & OUTCOME_COMPARISON (strictest: reject pit/out/in/off-track/
  incident/implausible-time/pace-outlier), PRACTICE_PATTERN (allows 1 off-track,
  no pace gate), PERFECT_LAP_REFERENCE (tighter pace ratio 1.05), RACE_STRATEGY
  (fuel-focused: tolerates pace outlier + off-track). A lap valid for fuel evidence
  is not necessarily valid for setup engineering — the purpose is explicit.
- **Unifies** the previously-scattered rules: `recommendation_scoring.aggregate_
  lap_window` (pit/out flags), `practice_capture.resolve_clean_lap` (pace-outlier
  gate), `cross_lap_persistence.LapMeta.representative` (rejection-reason vocabulary).
- Every rejection reason is retained; a single `primary_rejection_reason` is chosen
  by a fixed priority. Identity gates (setup / track-layout mismatch) are strongest.
  Unknown signals stay unknown and never fabricate a rejection.

### 2. Canonical per-corner evidence authority — `strategy/corner_evidence.py`

`CornerObservationRecord` (canonical per-corner observation) + adapter
`from_issue_occurrence_row` (from the live-populated `corner_issue_occurrences`
store) + the recurrence classifier.

- **Recurrence** REUSES `practice_pattern_analysis.RecurrenceThresholds` /
  `RecurrenceClass` (isolated / emerging / recurring / strongly_recurring — not a
  new scale). `classify_recurrence` counts DISTINCT affected **valid** laps against
  total valid laps, never raw event count; excluded (kerb/airborne/noise) events
  never count; returns classification + affected/total valid laps + ratio +
  threshold + confidence + source laps + exclusions + rationale code.
- `aggregate_corner_evidence` groups strictly by (segment, phase, issue, axle) —
  different corners/phases/axles never aggregate. `to_phase3_observations` converts
  to the exact Phase-3 `CornerObservation` shape, filtered to valid laps.
- No invented GT7 channels (steering angle, true slip, tyre wear %, brake temp,
  tyre load are refused); only real available metrics are carried.

### 3. Canonical evidence assembly — `strategy/setup_evidence_assembly.py` (pure) + SessionDB orchestrator

Pure selectors `select_test_session` / `select_baseline_session` return
RESOLVED / PARTIAL / AMBIGUOUS / MISSING / INCOMPATIBLE — **never silently pick the
newest session**. Test evidence must be tagged with the experiment's applied
checkpoint and share the scope; baseline must be the authoritative parent (not the
most recent previous session) and must NOT carry the experiment's own checkpoint.
`summarise_valid_laps` gives a median-based whole-lap summary over valid laps only.

`SessionDB.assemble_setup_experiment_evidence(experiment_id, ...)` resolves the
applied-checkpoint scope, evaluates every candidate session's lap validity, selects
baseline/test, and builds per-corner baseline/test `CornerObservation` tuples from
`corner_issue_occurrences` — returning evidence in the EXACT Phase-3 form. It never
decides the outcome and records missing/ambiguous/incompatible evidence.

`SessionDB.review_experiment_outcome(experiment_id, ...)` = assemble → call the
Phase-3 `evaluate_setup_experiment` with the assembled evidence. This is the
production review path — **no test-only manual `CornerObservation` objects required**.

### 4. Canonical setup-decision status authority — `strategy/setup_decision_status.py`

`resolve_setup_decision(*, recommendation_status, experiment_status, apply_state,
applied_match_state, outcome_status, ...) -> SetupDecisionResult`. States:
NO_RECOMMENDATION / EVIDENCE_REQUIRED / RECOMMENDATION_READY / READY_FOR_APPLY /
APPLIED / TEST_REQUIRED / READY_FOR_REVIEW / CONFIRMED / PARTIAL / REJECTED /
INCONCLUSIVE / REVERTED / INVALID. Precedence: a persisted Phase-3 outcome wins,
else the Phase-2 lifecycle, else the recommendation status. Contradictions
(e.g. COMPLETED with no outcome; APPLIED with nothing saved) become INVALID with
explicit `inconsistencies`. Returns deterministic allowed/blocked driver actions.
It does NOT replace the Phase-2 lifecycle or Phase-3 outcome; the UI renders it
instead of re-deriving status strings. The frozen Apply-gate predicate is unchanged.

## No migration required (proof)

`corner_issue_occurrences` already carries `session_id` + `setup_checkpoint_id` +
`lap_number` + `segment_id` + `corner_phase` + `issue_type` + `issue_subtype` +
`axle` + `severity` + `confidence` + `exclusion_reason` + `provenance`, and is
LIVE-populated by the Practice capture path (`dashboard._extract` →
`save_issue_occurrences`). This provides durable per-corner evidence keyed to a
session AND the applied checkpoint. `sessions.date_utc` + `applied_setup_checkpoints
.confirmed_at/created_at` give before/after timing; the applied-checkpoint tag on
each occurrence gives the authoritative setup association. Phase 4 therefore adds
NO table (no duplicate telemetry storage) and reads existing stores. `DB_VERSION`
stays 22.

## Duplicate clean-lap inventory & disposition

| Rule | Module | Purpose | Disposition |
|---|---|---|---|
| `aggregate_lap_window` | `data/recommendation_scoring.py` | OFR-1 / Phase-3 whole-lap windows | **Compatibility adapter** — still used for whole-lap windows; superseded for per-lap validity by the authority |
| `resolve_clean_lap` | `strategy/practice_capture.py` | live practice / perfect-lap pace-outlier | **Specialised-purpose policy** — its pace-outlier rule is now `LapPurpose.PRACTICE_PATTERN`/`PERFECT_LAP_REFERENCE` in the authority; live callers unchanged this group |
| `LapMeta.representative` | `strategy/cross_lap_persistence.py` | richest reason vocabulary | **Deprecated (dormant)** — vocabulary folded into the authority's rejection reasons |
| `evaluate_lap_validity` | `strategy/setup_experiment_outcome.py` | Phase-3 gate | **Canonical caller** — Phase-4 assembly feeds it via the authority-derived validity |
| `get_laps_for_scoring` SQL | `data/session_db.py` | row fetch | unchanged (fetch only; validity now via the authority) |

The new Phase-4 assembly + review path is the canonical caller of the lap-validity
authority. Live practice / perfect-lap callers are documented as specialised-purpose
policies and are NOT rewritten this group (owner: Phase 5 unification pass) to avoid
a dangerous repository-wide change.

## Dormant arbiter disposition

`strategy/setup_decision.py::arbitrate_setup_decision` and
`strategy/cross_lap_persistence.py::analyse_cross_lap` were already dormant (unwired,
guarded by `tests/test_engine_wiring_status.py`). Phase 4 **formally deprecated**
`arbitrate_setup_decision` (docstring note pointing to the Phase 1–4 spine +
`resolve_setup_decision`), kept the required EXPERIMENTAL banner + its render
dataclasses (`DecisionStatus`/`SetupDecision`/`FieldDecision`, still used by the UI),
and added `tests/test_phase4_setup_decision.py::test_dormant_arbiter_deprecated_and_
unwired`. `resolve_setup_decision` is the single driver-facing decision authority.

## Runtime production integration

The off-thread Setup Builder "Review Test Outcome" worker now calls
`db.review_experiment_outcome(...)` (was: `evaluate_setup_experiment` with no corner
evidence). Path: record practice laps → persist valid corner evidence
(`corner_issue_occurrences`) → associate by applied checkpoint → assemble
baseline/test observations (canonical authorities) → Phase-3 evaluator → meaningful
outcome. The summary renders the canonical `resolve_setup_decision` state, evidence
readiness (valid/rejected laps, test/baseline corner counts, missing evidence), and
distinguishes an infrastructure failure from honest engineering insufficiency (a
DB/parse error is never presented as a verdict). No work on the UDP/Qt threads; no
auto-apply/revert; the experiment recommendation is never mutated.

## Ambiguity & error handling

Ordinary missing evidence never raises — the assembler returns explicit
RESOLVED/PARTIAL/AMBIGUOUS/MISSING/INCOMPATIBLE selections and a `missing_evidence`
list; the review distinguishes an assembly/infrastructure failure (`phase` field)
from engineering insufficiency. Multiple plausible baselines/tests → AMBIGUOUS (never
auto-picked). A DB/parse error is never converted into `NO_MEANINGFUL_CHANGE`.

## Golden UAT (production assembly path — Porsche 911 RSR '17 @ Fuji Full Course)

`tests/test_phase4_golden_uat.py` (evidence persisted + assembled, no manual objects):
1. **Improvement** — baseline recurring T1 front-lock; test T1 isolated, protected
   corners clean → CONFIRMED_IMPROVEMENT → COMPLETED, decision CONFIRMED, no lockout.
2. **Regression** — T1 improves but rear-exit wheelspin recurring at a protected
   corner across several valid laps → REGRESSION → REJECTED, scoped LOCKOUT, parent
   remains rollback target, no auto-rollback, decision REJECTED.
3. **Insufficient** — 2 valid laps with a high raw event count on ONE lap; the
   authority excludes it → INSUFFICIENT_EVIDENCE, no lockout, experiment stays
   reviewable, `missing_evidence` populated so the UI can explain what's missing.

## Known limitations

- Live `corner_slip_telemetry` (Setup-Builder analyse path, run-keyed) is not yet
  merged with `corner_issue_occurrences` (Practice path, session-keyed) — the
  assembler reads the session/checkpoint-keyed occurrences store (the one with the
  linkage Phase 3 needs). Unifying the two live per-corner producers into one keyed
  store is a Phase 5 follow-up.
- Practice / perfect-lap live callers still use `resolve_clean_lap` directly; they
  are documented specialised-purpose policies to migrate onto the authority in a
  later pass (no behavioural drift — the authority encodes the same rules per purpose).

## Phase 5 — DELIVERED

Phase 5 (Working-Window Learning, Successful-Direction Reinforcement & Experiment
Selection) is now implemented — see `docs/ENGINEERING_BRAIN_PHASE5_WORKING_WINDOW_LEARNING.md`.
It added DB v23 (`setup_working_window_evidence` + `setup_working_windows`),
`strategy/working_window.py` + `strategy/experiment_selection.py`, the
`from_corner_slip_aggregate`/`unify_corner_observations` producer unification, and
migrated `resolve_clean_lap` onto this authority. The original prerequisite notes
below are retained for history.

Phase 5 (Working-Window Learning, Successful-Direction Reinforcement, Experiment
Selection) will consume the now-canonical evidence + Phase-3 outcomes to update
driver/car/track working windows, reinforce confirmed directions, and select
minimum-effective next experiments. The canonical lap-validity, per-corner evidence,
recurrence and decision authorities plus the production assembly path already exist.
