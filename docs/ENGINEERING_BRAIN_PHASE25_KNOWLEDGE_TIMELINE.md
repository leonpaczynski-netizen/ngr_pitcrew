# Engineering Brain — Program 2, Phase 25: Stable Knowledge Timeline & Convergence

**Status:** implemented on branch `eng-brain-phase25-knowledge-timeline` (from the Phase-24 tip `8fae013`). Committed locally; **not pushed; no PR; not merged; not live. `master` does not contain Phase 25.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). The timeline is rebuilt deterministically from immutable records.
**Nature:** a deterministic, offline, read-only **temporal** knowledge layer that explains how engineering understanding evolved across compatible events, where evidence has genuinely converged through **independent** repeated evidence, where it remains unresolved, and where apparent repetition is only duplicated or dependent evidence.

It generates no setup values, recommends no setup changes, schedules no tests, creates no experiments/campaigns, optimises nothing, applies nothing, and mutates no engineering data. Dates are evidence data only — **recency never automatically means correctness**.

## 1. Authority chain
```
Phase 17-21 engineering intelligence -> Phase 22 knowledge graph -> Phase 23 transfer report
  -> Phase 24 cross-programme playbook -> Phase 25 stable knowledge timeline & convergence
```
`SessionDB.build_programme_knowledge_timeline` composes the **Phase-22** programme knowledge report **exactly once** (the only heavy DB reconstruction), derives the **Phase-23** transfer report and the **Phase-24** playbook **purely** from that same in-memory programme (it never calls the Phase-23 or Phase-24 SessionDB entry points), performs **one bounded bulk read** of the immutable development records for the compatibility group, then runs the pure Phase-25 assembler. Proven by monkeypatch test: Phase-22 built once; Phase-23 DB entry 0 calls; Phase-24 DB entry 0 calls; query count constant vs event/campaign count; renderer touches 0 rows; no N+1.

## 2. Domain model (pure)
- **`strategy/evidence_independence.py` — `EvidenceIndependence`** (INDEPENDENT, PARTIALLY_INDEPENDENT, SAME_SESSION, SAME_CAMPAIGN, SAME_SOURCE_RECORD, DERIVED_FROM_EXISTING_CONCLUSION, UNKNOWN) + `assess_independence` / `independence_summary`. Visible deterministic rules; repeated evidence from one source chain never counts as multiple independent confirmations; Phase-22/23/24 re-statements are one lineage (DERIVED_FROM_EXISTING_CONCLUSION).
- **`strategy/knowledge_transition.py` — `KnowledgeTransitionType`** (18 states: INITIAL_OBSERVATION, REPEATED_SUPPORT, INDEPENDENT_CONFIRMATION, CONFIDENCE_INCREASED/REDUCED, MATURITY_ADVANCED/REDUCED, CONFIRMED_GOOD_ESTABLISHED/PRESERVED, CONFLICT_INTRODUCED/RESOLVED, REGRESSION_OBSERVED, DIRECTION_RETIRED, SUPERSEDED, CONTEXT_NARROWED, TRANSFER_LIMITED, NO_MATERIAL_CHANGE, INSUFFICIENT_EVIDENCE) + `classify_transition`. Conflict, regression, supersession and uncertainty are never collapsed into one generic state. A newer weaker contradiction yields `NO_MATERIAL_CHANGE` (older stronger finding preserved); a stronger later independent positive can reopen a retired direction.
- **`strategy/knowledge_timeline.py` — `TimelinePoint`** + `build_timeline`. One point per material evidence transition, with prior/resulting local-narrative state, evidence references, independence, confidence/maturity before/after, confirmed-good before/after, negative-learning flag, context/transfer limitations, rationale and explicit `unknown_fields`. Evidence is sorted internally (date/seq/ref) so the timeline is **insertion-order independent**.
- **`strategy/knowledge_convergence.py` — `ConvergenceStatus`** (STRONGLY_CONVERGED, CONVERGING, STABLE_BUT_CONTEXT_BOUND, STABLE_CONFIRMED_GOOD, MIXED, CONFLICTING, REGRESSED, SUPERSEDED, INSUFFICIENT_EVIDENCE, UNKNOWN) + `KnowledgeConvergence` + `assess_convergence`. Per domain: independent/dependent support counts, regression/conflict/confirmation counts, compatible/context-limited contexts, current maturity/confidence (reused from Phase 22), confirmed-good, retired directions, unresolved boundaries, transfer limitations, evidence-lineage summary, `suitable_only_as_investigation_aid`, rationale.
- **`strategy/programme_timeline_report.py` — `ProgrammeKnowledgeTimeline`** + `build_programme_timeline` (pure orchestration; joins Phase-22 graph + Phase-24 playbook + evidence records; maps records to domains with the **visible Phase-22 keyword maps**, no new mapping logic) + **`strategy/programme_timeline_report_render.py`** (deterministic renderer, zero DB).

## 3. Deterministic ordering & fingerprint
- **Timeline order:** `(evidence date [unknown -> "9999-99-99"], stable session sequence key, domain enum index, transition enum index, stable source record id, stable point id)`.
- **Convergence order:** `(convergence-status priority, confirmed-good priority, -independent support, -maturity rank, -confidence rank, domain enum index, domain id)`.
No dependence on dict order, DB row order, timestamps-as-sole-tie-break, hash randomisation, current time, UUIDs or randomness. The content fingerprint excludes generated timestamps and is identical across restart and shuffled-row input (asserted).

## 4. Dates-as-data rules
A newer observation never automatically overrides an older confirmed finding; recency identifies sequence, not truth; an older conclusion remains authoritative when later evidence is weaker/dependent/incompatible/invalid; unknown dates stay unknown (never fabricated from insertion order); **the event date is `session_date`, never `recorded_at` (creation time)** — asserted; missing dates never become the current date; no wall-clock call; supersession requires explicit stronger contradictory evidence, not merely a later date; conflict resolution requires explicit evidence and preserves the historical conflict. Golden tests cover out-of-order insertion, unknown/equal dates and a newer-but-weaker contradiction.

## 5. Evidence independence rules
Group by scope (investigation) first, then session: same `record_key` → SAME_SOURCE_RECORD (never double-counted); same `test_session_id` → SAME_SESSION (dependent); same `scope_fingerprint`, different session → SAME_CAMPAIGN (partially independent); different scope + session → INDEPENDENT; no session and no scope → UNKNOWN. `independent_support_count` = distinct scopes with support. Five records from one session yield **one** independent line, not five.

## 6. Convergence rules
Strong convergence requires **≥2 genuinely independent supporting lines** (`STRONG_MIN_INDEPENDENT_GROUPS`, visible), an established Phase-22 maturity, no unresolved regression and no unresolved conflict. A conclusion re-stated through Phases 22/23/24 is one lineage, not three confirmations; repeated same-session/same-record evidence never strongly converges. Confirmed-good is distinct (`STABLE_CONFIRMED_GOOD`). Conflicting evidence → `CONFLICTING` (certainty reduced, never averaged). Regressions with no offsetting confirmation → `REGRESSED`. Context-bound domains (gearbox/track/driver) surface as `STABLE_BUT_CONTEXT_BOUND` — stable here, not universal, never labelled strongly converged. Incompatible-context / cross-car evidence is a separate programme (excluded by the compatibility-scoped bulk read) and never counted as direct confirmation.

## 7. Confirmed-good preservation
Reuses the Phase-24 confirmed-good semantics (no second definition). The timeline shows when confirmed-good was established, what established it, whether later evidence preserved it (`CONFIRMED_GOOD_PRESERVED`), and marks a masking conflict when a harmful direction appears in a confirmed-good domain. A harmful setup direction retires only the tested direction; it does not erase the whole domain-level proxy unless evidence proves the whole conclusion invalid. No setup-field values are exposed.

## 8. Negative learning & supersession
Failed historical outcome, regression, conflict, invalid/insufficient evidence, retired direction, superseded conclusion, narrowed context and transfer rejection are distinguished. A retired direction never reappears as a positive converged recommendation without new explicit stronger evidence that reopens it. Supersession retains the historical conclusion and explains why it was replaced. History is never deleted, flattened or silently overwritten. **Retired/contradicted domains remain visible** — they are not filtered out; the SessionDB derives confirmation/regression counts directly from the raw records so negative learning is grounded even when Phase-22 retired the direction.

## 9. Knowledge boundaries & transfer limits
Reuses the Phase-24 `KnowledgeBoundary` and the Phase-23 `TransferLevel` verbatim (no re-creation). Limitations are kept adjacent to any claimed stable knowledge: gearbox car/track-specific, fuel/tyre event-context-bound, driver-technique same-driver, GT7-version caps, cross-manufacturer suspension as an unverified proxy, unknown attributes left unknown, `SUPPORTED` transfer = hypothesis/investigation aid only, no setup/LSD/suspension/gearbox values copied.

## 10. SessionDB integration & query shape
`SessionDB._timeline_evidence_records` is **one** `SELECT` over the compatibility columns (car+discipline+gt7-version+driver, all tracks/layouts/compounds) — its result grows with records but its query **count** does not. `build_programme_knowledge_timeline` performs no writes, no migration, no persistence, and leaves the database file byte-identical, all table counts unchanged and `PRAGMA user_version` = 26 (verified by SHA-256 + counts).

## 11. UI behaviour
`EngineeringTimelinePanel` (+ pure `ui/engineering_timeline_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-24 playbook panel. Structured sections: historical sequence, convergence by domain (independent vs dependent), confirmed-good preservation (tagged `[PROTECT]`, success colour), unresolved conflicts + regressions/retired (tagged `[REVIEW]`, warn colour), superseded conclusions, context/transfer limitations, unknowns and independence lineage. Distinct states use **text tags, not colour alone**. Read-only: no Apply / Create-Experiment / Schedule / Optimise / setup-editor / edit control, no setup values. Built OFF the Qt thread via the reused `MechanismAnnotationWorker`; a **stale worker result cannot replace a newer one** (handler guards on the current worker — asserted). All Phase 12/19/20/21/22/23/24 panels coexist (asserted).

## 12. Safety boundaries (proven)
No AI/network/random/wall-clock; no setup generation/values/writes/snapshots; no experiment/campaign creation; no scheduler/optimiser; no Apply/approval/pit/driver command; no migration/DB mutation/persistence; no duplicate knowledge graph or transfer logic; the Phase-23 `TransferLevel` is imported and never redefined; the event date is `session_date` (never `recorded_at`); no setup-field values in data or rendering (regex-asserted); `strategy/_setup_constants.py` git-verified byte-identical; the frozen Apply gate, config identity, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 unchanged; no-AI architecture guard green.

## 13. Test evidence (exact totals)
| Command | Result |
|---|---|
| `test_phase25_independence.py` | 13 passed |
| `test_phase25_convergence.py` | 36 passed |
| `test_phase25_timeline.py` | 14 passed |
| `test_phase25_integration.py` | 5 passed |
| `test_phase25_golden.py` | 11 passed |
| `test_phase25_safety.py` | 10 passed |
| `test_phase25_ui_construction.py` | 10 passed (offscreen) |
| **Full Phase-25 suite (7 files)** | **93 passed** |
| Phase 17–24 non-UI regression (9 files) | 84 passed |
| `test_session_db.py` + `test_no_ai_architecture.py` | 34 passed |
| Phase 22/23/24 UI construction (per-file) | 7 / 7 / 9 passed |
| Apply-gate + config safety (`test_group41` + `test_setup_apply_checkpoint_ui` + `test_phase3_coherence_gate` + `test_config_safety_guardrails`) | 125 passed, 1 skipped, 1 warning |

## 14. Runtime verification results
Disposable DB with a multi-track Porsche programme (3 independent lines + an unknown-date record), a dependent-repeat domain, a regression, a conflict and a cross-car Toyota: differential & weight_transfer → `stable_confirmed_good` (independent support counted correctly; the unknown-date record counted, the Toyota excluded as a separate programme); brake_balance → `conflicting`, present in both unresolved-conflicts and regressions/retired (negative learning visible); 2 unknown-date points preserved. **All table counts unchanged, DB-file SHA-256 unchanged, `PRAGMA user_version` = 26, restart-identical content fingerprint, no setup-field-value assignments.**

## 15. Known limitations
- The timeline covers the current (primary) compatibility group; cross-car programmes are separate (never merged into this group's convergence).
- Per-point maturity/confidence are a local evidence narrative; the authoritative current maturity/confidence come from the Phase-22 graph.
- Confirmed-good is a domain-level proxy (Phase-24), not a per-corner driver-confirmed behaviour.
- A heavily-contradicted single-domain programme can collapse to an honest empty timeline (the retired direction removes the only domain).

## 16. Deferred work / recommended Phase 26
**Phase 26 — Knowledge Decay & Re-validation Prompts (advisory):** identify where established knowledge is ageing (no recent independent confirmation across a run of events) or where a GT7 version change has invalidated prior evidence, and surface a read-only "re-validate" flag — still read-only, reusing Phases 17–25, dates as data, no scheduling / optimiser / setup generation. Not started.
