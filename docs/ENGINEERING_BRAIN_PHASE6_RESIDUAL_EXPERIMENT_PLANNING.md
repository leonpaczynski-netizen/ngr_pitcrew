# Engineering Brain — Phase 6: Live Residual-Issue Detection & Multi-Symptom Experiment Planning

**Status:** implemented on branch `eng-brain-phase6-residual-experiment-planning` (from `master` @ Phase 5 `535aed9`).
**Schema:** **NO migration** — `DB_VERSION` stays **23**, `RULE_ENGINE_VERSION` stays `46.0`.
**Nature:** residual detection + development-programme planning over the Phase 1–5 spine —
NO generative AI, no auto-apply/revert, no live-coaching, no whole-app redesign.

## 1. Problem solved

Fixing one setup problem can leave another unchanged, solve several related ones, or
create a new regression. Phase 5 selected the next experiment mainly from the reviewed
experiment's diagnosis. Phase 6 determines the COMPLETE current engineering state after
each experiment — what was resolved / improved-but-present / unchanged / worsened / new /
confirmed-good / damaged-good — and produces a deterministic development plan with AT MOST
ONE immediate setup experiment plus queued hypotheses, dependencies, conflicts and honest
no-selection.

## 2. Starting checkpoint

`eng-brain-phase6-residual-experiment-planning` from `master` @ Phase 5 `535aed9`
(Phases 2–5 stacked; master at Phase 1). `DB_VERSION 23`, `RULE_ENGINE_VERSION 46.0`.

## 3. Existing authorities reused

| Concern | Reused |
|---|---|
| Per-corner comparison + protected verdicts | Phase 3 `SetupExperimentOutcome` (`corners`, `protected` child rows) — re-classified, never re-evaluated |
| Overall experiment outcome | Phase 3 `OutcomeStatus` — Phase 6 never decides success/failure |
| Evidence assembly + recurrence + lap validity | Phase 4 `assemble_setup_experiment_evidence`, `CornerObservationRecord`, `evaluate_engineering_lap` |
| Setup-decision authority | Phase 4 `resolve_setup_decision` (planning is subordinate) |
| Working windows + candidates | Phase 5 `LearnedWorkingWindow`, `generate_candidates`, `select_next_experiment` (one selector) |
| Interaction / coupling | `setup_synthesis.PARAMETER_INTERACTIONS` |

## 4. Canonical issue identity — `strategy/engineering_issue.py`

`EngineeringIssueIdentity` (frozen): `issue_family` (braking/rotation/traction/platform/
gearing/drive_out/tyre/fuel/consistency/aero), issue_type, axle, phase, segment_id,
corner_name, discipline, scope_fingerprint, source_type. `key()` is a stable hash that
**excludes display text** (corner_name), so "Turn 1" and "T1" are the same identity, while
different issue/corner/phase/axle stay distinct.

## 5. Residual-state model

`ResidualState`: RESOLVED / IMPROVED_BUT_PRESENT / UNCHANGED / WORSENED / NEW /
CONFIRMED_GOOD / GOOD_BEHAVIOUR_DAMAGED / INSUFFICIENT_EVIDENCE / INVALID_COMPARISON /
AMBIGUOUS / NOT_OBSERVED / OUT_OF_SCOPE. `classify_corner_residual` /
`classify_protected_residual` map ONE Phase-3 outcome row → a `ResidualIssue` (identity,
baseline/test recurrence classes + affected laps, recurrence change, confidence, comparison
status, protected-good flag, setup relevance, is_new/is_regression, warnings, reasoning).
`residual_issues_from_outcome` derives the full set, de-duplicating by identity and keeping
the most-severe state.

## 6–10. Comparison, resolution, improvement, worsening, new-issue, confirmed-good rules

Phase 6 consumes the authoritative Phase-4 baseline/test comparison (checkpoint-tagged) that
Phase 3 already evaluated — it never picks the newest session or compares an experiment
against itself. **RESOLVED requires the verdict IMPROVED, the test recurrence below the
authorable threshold, ≥3 comparable samples, and non-low confidence** — a missing/unmeasurable
window is never resolution. IMPROVED_BUT_PRESENT preserves mixed evidence (recurrence down but
still present, or too few laps to prove resolution). WORSENED needs higher recurrence/severity.
A NEW issue requires a weak/absent baseline AND an authorable test recurrence — not merely
absence from a weak baseline. GOOD_BEHAVIOUR_DAMAGED comes from a protected-behaviour material/
minor regression. Association not resolved → INVALID_COMPARISON (blocks planning).

## 4′. Engineering-state snapshot — `strategy/engineering_state.py`

`build_engineering_state(outcome, ..., generated_at)` → `EngineeringStateSnapshot` (frozen):
scope + checkpoint, valid-lap summary, all residual issues grouped (resolved / improved /
unchanged / worsened / new / confirmed_good / damaged_good / insufficient), evidence gaps,
contradictions, the canonical decision state, working-window field references, and a
deterministic `content_fingerprint` (time-independent). The pure builder never reads the clock.

## 11–13. Live residual detection, clustering, priority

`cluster_issues` groups setup-relevant issues by (issue_family, axle, phase) — rule-based,
transparent, never by wording; a cluster always requires an isolated first test
(`coupled_response_permitted=False`). `prioritise_issues` runs hard exclusion first
(resolved/confirmed-good/not-observed/insufficient/invalid/ambiguous/out-of-scope; and the
decision authority) then a documented precedence: new regression → damaged-good →
high-recurrence control → persistent dominant → drive-out/gearing → tyre/fuel → consistency →
weak/isolated → evidence-gathering, with a stable tie-break `(tier, −severity, −test_affected,
issue_key)`. Non-setup issues (gearing / drive-out / tyre-fuel / driver-technique) are routed
to their own review/evidence task — never silently a suspension/LSD experiment.

## 9′. Conflict detection

`detect_conflicts(candidates)` surfaces: SAME_FIELD_OPPOSITE (two issues want opposite
directions of one field), STRONG_INTERACTION (different fields sharing a handling axis via the
interaction graph), and PROTECTED_GOOD (a candidate risks a confirmed-good behaviour). The
planner never resolves a same-field conflict arbitrarily.

## 16–17. Development plan — `strategy/experiment_planning.py`

`build_development_plan(snapshot, prioritised, immediate_selection, queued_candidates, ...)`
→ `DevelopmentPlan` (frozen): plan_id, scope + checkpoint, snapshot fingerprint, status
(READY / RETAIN_SETUP / EVIDENCE_REQUIRED / BLOCKED / NO_ACTION), **at most ONE immediate
experiment** (the Phase-5 selection — a full CandidateExperiment + test protocol),
`QueuedHypothesis`es (each with `queue_state` WAITING_FOR_CURRENT_EXPERIMENT / READY / BLOCKED /
…, depends-on-immediate, promotion + cancellation conditions, conflicts-with-immediate),
deferred (non-setup) and blocked issues, resolved issues, protected-good, conflicts, clusters,
reassessment + invalidation triggers (checkpoint/scope/discipline/driver change, new outcome,
resolved queued issue, new regression, working-window change, decision change, stale telemetry),
required evidence, rollback target, and a deterministic content fingerprint (time-independent).
The queue is a living plan of hypotheses — never a list of changes to apply.

## Runtime orchestration — `SessionDB.build_engineering_plan`

The DB orchestrator gathers the persisted Phase-3 outcome + Phase-4 validity/whole-lap +
Phase-5 working windows, builds the snapshot, prioritises, and — for the top setup-actionable
issue — calls the Phase-5 `select_next_experiment` for the IMMEDIATE experiment; the next
setup issues yield queued candidates. `review_and_learn` now returns
`review["engineering_plan"] = {snapshot, plan}`. Everything runs on the off-thread review
worker; the UI render only reads the pre-computed dict.

## Persistence decision — NO migration (proof)

The plan is a DETERMINISTIC function of already-persisted state: the immutable Phase-3
`setup_experiment_outcomes` (+ corner/protected children), the applied checkpoint scope, the
Phase-5 `setup_working_windows`, and `setup_ranges`/interaction constants. `build_engineering_plan`
regenerates a byte-identical snapshot + plan fingerprint across restart (golden UAT scenario L).
No evidence or audit is lost (the outcome + working-window ledgers already persist it), and no
temporary/UI ordering is stored. Therefore `DB_VERSION` stays **23** and no telemetry table is
added.

## Gear / drive-out & discipline

Gearing (`wrong_gear`, `gearing_too_long`) and drive-out issues are classified with their own
`IssueFamily` + `IssueRelevance`, so they are routed to a GEARING_REVIEW / DRIVE_OUT_REVIEW task
rather than becoming a suspension/LSD experiment (golden UAT scenario D pattern). No RPM/shift/
tyre channels are invented. Discipline is part of every issue identity and the working-window
context key, so Race vs Qualifying plans key on distinct scopes and cannot cross-contaminate
direct evidence.

## Driver-feedback reconciliation

The current review's `DriverReviewInput` drives the current outcome (Phase 3); Phase 6 reads
the resulting outcome, so stale prior feedback never keeps an issue "active". "Worse than
previous" remains authoritative regression evidence via the Phase-3 outcome. No natural-language
AI parsing — only the existing deterministic structured fields.

## UI surface

The Setup Builder outcome summary now renders, after review, a compact **Engineering state**
line (resolved/improved/unchanged/worsened/new/damaged-good counts) and a **Development plan**
line (one immediate experiment + queued count, or the no-immediate status + review/evidence
tasks), plus a candidate-conflict note and an explicit "plan is advisory — setup values are not
applied automatically" statement. No new decision surface; no Apply/Revert; the frozen Apply
gate is untouched.

## Safety guarantees

Fully local/offline/deterministic; no AI/network/API-key; no auto-apply/revert; the pure
modules import no Qt/DB/UI/AI, write no files, use no random or wall-clock; the frozen Apply-gate
predicate, fan-out allowlist, golden `config_id`, engine-wiring-status and `RULE_ENGINE_VERSION
46.0` are unchanged; `arbitrate_setup_decision` stays dormant; planning is subordinate to
`resolve_setup_decision` and reuses the one Phase-5 candidate authority (it defines no selector
of its own).

## Tests added

- `tests/test_phase6_residual_detection.py` (27) — residual states + issue identity + property.
- `tests/test_phase6_priority_planning.py` (21) — priority + conflict + clustering + plan + property.
- `tests/test_phase6_golden_uat.py` (10) — Scenarios A/B/F/G/J/L through the production loop + frozen contracts.
- `tests/test_phase6_wiring.py` (12) — runtime wiring + threading + architecture safety.

## Known limitations

- Live (non-experiment) practice residual detection reuses the same snapshot builder over the
  Phase-4 assembly but is surfaced only via the experiment-review path; a standalone live
  Practice snapshot button is deferred.
- Clustering is by (family, axle, phase); a physics-informed shared-cause solver (e.g. front
  ARB vs aero balance) is deferred to a later phase.
- Queued candidates are generated for up to 3 next issues; deeper queue planning is bounded.

## Deferred work

Standalone live-Practice engineering-state panel; richer cluster cause inference; multi-lap
live residual streaming; a dedicated development-plan UI panel (current surface is the outcome
summary).

## Manual UAT

Porsche 911 RSR '17 @ Fuji Full Course: apply a single-field Race experiment, drive/ persist
baseline + checkpoint-tagged test evidence across two symptoms, `review_and_learn`, and confirm
the snapshot distinguishes resolved / improved / unchanged / worsened / new / confirmed-good;
one immediate experiment is actionable (the rest queued with dependencies/blockers); failed
directions stay blocked; a queued experiment cancels if its target resolves; no setup changes
automatically; restart reproduces the same snapshot + plan fingerprint; protected runtime files
untouched.

## Recommended Phase 7

Phase 7 — Standalone Live Engineering-State Monitoring & Session Development Ledger: surface the
Phase-6 snapshot live during practice (off-thread, event-driven), persist a plan-history audit
trail (superseded/invalidated), and add a physics-informed shared-cause cluster solver — all on
the Phase 1–6 evidence + planning spine.
