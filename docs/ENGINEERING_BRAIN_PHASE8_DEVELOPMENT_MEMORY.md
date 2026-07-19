# Engineering Brain — Phase 8: Cross-Session Engineering Development Memory & Driver Progress Intelligence

**Status:** implemented on branch `eng-brain-phase8-development-memory` (from `master` @ Phase 7 `dfc70a9`).
**Schema:** **additive migration to v24** — `DB_VERSION` 23 → **24**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the permanent engineering memory that sits ABOVE Phases 1–7. It answers
*"what have we learned over every previous session?"* — NOT *"what happened today?"*.
It makes NO engineering decision, authors no setup value, evaluates no lap, and mutates
no prior evidence. No AI, no network, no prediction, no text interpretation.

## 1. Problem solved

Phases 1–7 reason within a session / experiment. Nothing carried the crew's knowledge
across sessions: which issues recur, which fixes worked or failed, how each learned
working window evolved, which behaviours are protected, and the hard constraints that
must never be forgotten. Phase 8 records each completed engineering review immutably and
folds the accumulated history into permanent memory, long-term progress intelligence, an
engineering scorecard, session-to-session comparison and a long-term timeline.

## 2. Starting checkpoint

`eng-brain-phase8-development-memory` from `master` @ Phase 7 `dfc70a9` (Phases 2–7
stacked; master at Phase 1). Golden `config_id` vectors, frozen fan-out allowlist,
Apply-gate predicate and engine-wiring-status all unchanged.

## 3. Existing authorities reused (no duplication)

| Concern | Reused authority |
|---|---|
| One completed review (immutable record) | Phase 3 `setup_experiment_outcomes` (+children) — re-projected, never re-evaluated |
| Residual issue re-classification | Phase 6 `residual_issues_from_outcome` / `EngineeringIssueIdentity` (display-text-free) |
| Learned working windows | Phase 5 `list_working_windows` (`low_bound`/`high_bound`/confidence/counts) |
| Failed directions (constraints) | Phase 3 `setup_experiment_failed_directions` (via the outcome) |
| Engineering context | Phase 1 scope semantics (`_experiment_context_scope`) + a Phase-8 full memory key |

Phase 8 defines **no** second outcome/residual/recurrence/identity authority.

## 4. New modules (all pure: Qt-free, DB-free, UI-free, network-free, AI-free, never raise, no clock/random)

- **`strategy/development_history.py`** — the immutable record layer.
  - `MemoryContextKey` (driver/car/track/layout/discipline/gt7/compound). A known value and
    an unknown value are DIFFERENT scopes — incompatible contexts NEVER merge.
  - `DevelopmentRecord` — ONE completed review captured with its full context, changes,
    residual states, confirmed improvements, new regressions, protected behaviours, a
    working-window snapshot, and derived **protected knowledge** (constraints). The
    `record_key` is idempotent (context+experiment+outcome) and the `content_fingerprint`
    is time-independent (recorded_at is metadata, never part of content).
  - `build_development_record` (pure builder), `DevelopmentHistory` + `build_history`
    (chronological, dedup by record_key), `build_timeline` (session → experiment →
    improvement/regression/resolution/protected).
  - `ConstraintKind`: NEVER_MOVE_DIRECTION / NEVER_BELOW / NEVER_ABOVE / PREFERRED_RANGE /
    KNOWN_UNSTABLE / PROTECTED_BEHAVIOUR.
- **`strategy/engineering_memory.py`** — the permanent-memory fold.
  - `IssueMemory` (per-issue: recurrence, sessions/dates, times resolved/regressed, current
    resolution, successful/failed fix experiments), `WorkingWindowEvolution` (per-field
    snapshots + convergence), `ProtectedKnowledgeItem` (reinforced constraints),
    `EngineeringMemory` (+ time-independent fingerprint). `build_engineering_memory(history)`.
- **`strategy/progress_metrics.py`** — deterministic long-term intelligence.
  - `numeric_trend` (min-points + window + hysteresis → a single session can never flip a
    long-term trend), `ProgressMetrics` (experiment success rate, issue resolution rate,
    recurring-issues-reduced, working-window convergence, brake / corner-entry / exit-traction
    / driver-consistency / engineering-confidence trends, development velocity, experiment
    efficiency), `EngineeringScorecard` + `ScorecardBand`, `SessionComparison` +
    `compare_records` / `compare_latest_sessions`.

## 5. Persistence (DB v24 — additive, append-only, immutable)

`_migrate_v24` adds ONE standalone table `engineering_development_records` (CREATE IF NOT
EXISTS ⇒ idempotent; touches no existing table). It stores one immutable, append-only row
per completed review, keyed by the full memory context + a UNIQUE `record_key`.

**Why a migration here (unlike Phases 4/6/7, which were regenerable):** the memory context
key needs `driver / gt7_version / tyre_compound`, which are NOT reliably recoverable from the
persisted outcome rows — they are only fully known at review time. Capturing the record
immutably WITH its full context key is the honest implementation of permanent memory. Long-term
memory, history, metrics, scorecard and comparison are then deterministic FOLDS over the stored
`record_json` — regenerable, so a restart reproduces identical fingerprints.

Immutability is enforced: `_persist_development_record` uses `INSERT OR IGNORE`, never
UPDATE/DELETE; re-recording the same review is a no-op (verified). History is never rewritten.

## 6. Orchestrators (SessionDB, read-only)

- `record_engineering_development(experiment_id, …)` — build + persist the immutable record
  (idempotent). Wired best-effort into `review_and_learn`, so every completed review is captured
  automatically; a capture failure never breaks the review.
- `get_development_records(...)`, `build_development_history(...)`,
  `build_cross_session_memory(...)` (memory + metrics + scorecard + comparison + timeline).
  All read-only; the observer writes nothing beyond its own append-only log (verified).

## 7. UI — the Development History page

- `ui/development_history_vm.py` — pure Qt-free view-model (scorecard banner, metrics grid,
  timeline, resolved/remaining issues, protected behaviours + protected knowledge, experiment
  history, working-window evolution, session comparison).
- `ui/development_history_page.py` — `DevelopmentHistoryPage`, a self-contained read-only page.
  There are **no Apply / Save / Revert controls** (asserted by test).
- Wired as a real tab: `dashboard.py` adds a **"Development History"** tab (index 12);
  `ui/tab_registry.py` (`TAB_DEVELOPMENT_HISTORY` + `DEFAULT_TAB_ORDER` + `TAB_BASE_TITLES`) and
  `ui/product_flow.py` (`ROLE_WORKFLOW`) are updated together. The page refreshes read-only when
  shown, resolving the current car/track/layout/discipline from the event context.

## 8. Determinism & purity verification

- All four Phase-8 modules are pure (no random / wall-clock / sqlite / Qt / network imports — asserted).
- Record `content_fingerprint` + `record_key` are time-independent (different clock times → same key).
- History / memory / metrics folds are order-independent and restart-deterministic (rebuild from stored
  JSON is byte-identical — `test_restart_determinism`, `test_restart_determinism_production`).
- `numeric_trend` never flips on a single session (`test_trend_single_point_never_flips`).

## 9. Schema / contract changes

`_migrate_v24` + `_DDL_V24` (one additive table). `DB_VERSION` 23 → 24. `RULE_ENGINE_VERSION`
`46.0` unchanged. Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status untouched. Version-guard tests advanced (group55–61 → guard v25;
`test_session_db`/`test_phase5_persistence`/`test_phase6_golden_uat` now track `DB_VERSION`;
tab registry/count guards → 13 tabs).

## 10. Tests

`tests/test_phase8_{development_history,engineering_memory,progress_metrics,persistence,golden_uat,view_model}.py`
(50 non-UI) + `tests/test_phase8_ui_construction.py` (3 UI — run individually). Golden UAT runs the real
`review_and_learn` production loop across multiple Porsche-RSR-at-Fuji sessions and asserts the
permanent-memory conclusions.

## 11. Known limitations / deferred

- `driver` / `gt7_version` are honest inputs (default unknown when the app can't resolve them);
  `compound` is resolved from the test session's laps. Richer driver/gt7-version resolution is deferred.
- The Development History page refreshes on show; a live "recompute on new review" push into the page is
  deferred (the data is captured immediately regardless).
- Trends use fixed thresholds (`MIN_TREND_POINTS`, `TREND_DELTA`); per-discipline tuning is deferred.

## 12. Recommended Phase 9

**Cross-context transfer & regression-risk foresight**: deterministically surface, at the moment a new
experiment is proposed, the relevant permanent-memory constraints (failed directions, learned minimums,
known-unstable combinations) and prior cross-session outcomes for the same issue/field — still a pure
observer subordinate to the Phase-3/5 decision authority, still no auto-apply.
