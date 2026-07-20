# Engineering Brain — Phase 10: Engineering Experiment Pre-Flight Review

**Status:** implemented on branch `eng-brain-phase10-preflight-review` (from `master` @ Phase 9 `b979be0`).
**Schema:** **NO migration** — `DB_VERSION` stays **24**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** a READ-ONLY OBSERVER above Phases 1–9. Before the selected experiment is
presented to the driver it performs a deterministic engineering pre-flight review of the
EXACT Phase-5 selection. It NEVER creates experiments, changes priorities/ranking, changes
setup values, blocks recommendations, changes working windows, or mutates
evidence/memory/outcomes. No AI, no prediction, no statistical inference.

## 1. Problem solved

Phase 9 surfaces relevant past lessons for a context. Phase 10 answers, for the specific
experiment Phase 5 already selected, *"what engineering consequences should the driver know
before trying this?"* — assembling fixed review sections, the deterministic change
consequences, and an engineering checklist + descriptive risk level, all from
already-canonical outputs.

## 2. Starting checkpoint

`eng-brain-phase10-preflight-review` from `master` @ Phase 9 `b979be0` (Phases 2–9 stacked;
master at Phase 1). Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status all unchanged.

## 3. Existing authorities reused (no duplication)

| Concern | Reused authority |
|---|---|
| The selected experiment (verbatim) | Phase 5 `CandidateExperiment` (field/direction/value/effects/window/evidence) |
| Transfers / constraints / regression risks | Phase 9 `build_engineering_context` (for the proposed change) |
| Outstanding issues / familiarity / state | Phase 8 `build_cross_session_memory` |
| Coupled fields + interaction effects | canonical `setup_synthesis.PARAMETER_INTERACTIONS` |

Phase 10 re-derives **no** physics: the candidate's own `expected_positive_effect` /
`expected_negative_effects` (already from the interaction graph) are consumed verbatim.

## 4. New modules (all pure: Qt-free, DB-free, UI-free, network-free, AI-free, never raise, no clock/random)

- **`strategy/change_consequences.py`** — `derive_consequences(candidate, context)` →
  `ChangeConsequence`s: PRIMARY_EFFECT (candidate's own positive effect), SIDE_EFFECT (its
  coupled negatives), HISTORICAL (Phase-9 successful/failed transfers for the field),
  WORKING_WINDOW (whether the value stays inside the learned window), INTERACTION (coupled
  fields via the graph). `coupled_fields(field)` derives coupling from shared handling axes.
- **`strategy/engineering_checklist.py`** — `build_checklist(candidate, context, memory)` →
  (`ChecklistItem`s ✓/⚠/?, `RiskLevel` LOW/MODERATE/HIGH/UNKNOWN). Items: inside learned
  window, protected-behaviour conflict, similar experiment succeeded/failed, only one
  supporting session, regression risks (Phase 9), coupled interaction, outstanding residuals.
  Every item explains why + supporting sessions + confidence + context. Descriptive only —
  never changes the recommendation.
- **`strategy/preflight_review.py`** — `build_preflight_review(candidate, context, memory,
  interactions)` → `PreFlightReview`: the echoed experiment (verbatim), fixed review sections,
  the consequences, the checklist, the risk level, a summary, and a time-independent
  `content_fingerprint`.

## 5. Pre-flight review model (sections)

Evidence quality · Working-window confidence · Protected behaviour impact · Historical
success · Historical failure · Regression risk · Known constraints · Interaction risks ·
Coupled fields · Driver familiarity · Outstanding residual issues · Current engineering
state. (A section is emitted only when it has content — e.g. Regression risk appears only
when Phase 9 flagged risks.)

## 6. Consequence model

Each proposed change lists deterministic expected effects, every one referencing engineering
evidence: the primary effect (interaction graph), coupled side effects, what prior sessions
showed (Phase-9 transfers, with sessions + confirmed/provisional), whether the working window
remains valid, and the coupled fields it interacts with.

## 7. Engineering checklist + risk

`✓`/`⚠`/`?` items with why + supporting sessions + confidence + context. Risk level is a
deterministic descriptive aggregate: **HIGH** on any confirmed high-severity Phase-9 risk
(known failed direction / repeated regression / protected conflict); **MODERATE** on medium
risks, window edges or multiple cautions; **LOW** when inside window with confirmed successful
history and no risks; **UNKNOWN** with no comparable history. It is descriptive only and
never blocking.

## 8. Orchestrator (SessionDB, read-only, no migration)

`build_experiment_preflight(selection, car, track, layout_id, discipline, driver,
gt7_version, compound)` — echoes the exact Phase-5 selection, builds the Phase-9 context for
its proposed change + the Phase-8 memory, and assembles the review with the canonical
interaction graph. Read-only; regenerable; writes nothing; never blocks.

## 9. UI — the Pre-Flight Engineering Review panel

- `ui/preflight_review_vm.py` — pure Qt-free view-model (experiment, rationale, consequences,
  checklist, per-section rows, compact summary).
- `ui/preflight_review_panel.py` — `PreFlightReviewPanel`, a self-contained read-only panel
  with **no Apply and no approval controls** (asserted): risk banner, proposed experiment,
  engineering rationale, checklist, expected consequences, known risks, historical outcomes,
  protected behaviours, constraint summary.
- Surfaced beside the proposed experiment: the Setup Builder's outcome-review display appends
  a compact pre-flight summary (risk + top cautions/clears) next to the selected next
  experiment, computed read-only via `build_experiment_preflight` (guarded, best-effort).

## 10. Determinism & purity verification

- All 3 core modules verified free of random/wall-clock/sqlite/Qt/network.
- The review is order-independent and restart-deterministic (`content_fingerprint` identical
  on rebuild — `test_restart_determinism`).
- Inputs are never mutated (`test_metamorphic_inputs_not_mutated`,
  `test_checklist_never_changes_inputs`).

## 11. Schema / contract changes

**None.** No migration (`DB_VERSION` 24, `RULE_ENGINE_VERSION` 46.0). No new table, no new
tab. Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status untouched.

## 12. Tests

`tests/test_phase10_{change_consequences,engineering_checklist,preflight_review,orchestrator,view_model}.py`
(40 non-UI) + `tests/test_phase10_ui_construction.py` (3 UI — run individually). Golden UAT
drives the real `review_and_learn` loop (Porsche RSR @ Fuji), then pre-flights a follow-up
experiment and asserts the historical-success section + consequences appear.

## 13. Known limitations / deferred

- The compact pre-flight text is surfaced in the Setup Builder outcome flow; docking the full
  `PreFlightReviewPanel` widget into the Setup Builder layout beside the candidate is deferred
  (the panel + orchestrator are complete and tested).
- "Current engineering state" uses the Phase-8 cross-session summary (band + issue counts); a
  live Phase-7 in-session state feed is deferred.
- Risk thresholds are fixed deterministic rules; per-discipline tuning is deferred.

## 14. Recommended Phase 11

**Post-flight reconciliation:** after the experiment is tested, deterministically compare the
pre-flight prediction against the Phase-3 actual outcome (which cautions materialised, which
consequences held) and fold that into the Phase-8 memory as pre-flight calibration — still a
pure observer, still no auto-apply.
