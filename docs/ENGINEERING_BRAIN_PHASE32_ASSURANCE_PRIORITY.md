# Engineering Brain — Program 2, Phase 32: Assurance-Driven Engineering Priority

**Status:** DONE (committed locally, NOT pushed, no PR, not merged) ·
**Branch:** `eng-brain-phase32-assurance-priority` (from Phase-31 tip `4b485be`) ·
**DB:** v26 (no migration, no new persistence) · **RULE_ENGINE_VERSION:** 46.0 (unchanged) ·
`strategy/_setup_constants.py` byte-identical.

## What it is

A deterministic, offline, **read-only, advisory-only** system that converts the Phase-31 assurance
audit findings into a **prioritised list of evidence investigations** that would most efficiently
improve programme assurance. It answers: *"given the current assurance verdict, what evidence should
the engineering programme collect next, and why?"*

It is **evidence-priority planning only**. It produces a priority ORDER, never a schedule: it names
no dates, sessions, drivers, cars, tracks or resources; it creates no experiment, campaign or setup;
it exposes no Apply control; it invokes no AI/optimiser/scheduler; and it never claims a proposed
investigation guarantees an assurance-grade increase (impact is always *potential*).

It **consumes** the existing authorities (Phase 17 information-gain doctrine, Phase 22 shared chain,
Phase 25–31 products) and does **not** replace or mutate any of them.

## Core domain model (`strategy/assurance_engineering_priority.py`)

**`InvestigationPriorityBand`** (6): `BLOCKING`, `HIGH`, `MEDIUM`, `LOW`, `DEFER`, `NO_ACTION`.

**`InvestigationType`** (10): `revalidation`, `contradiction_discrimination`,
`independence_improvement`, `context_expansion`, `repeated_confirmation`, `assumption_establishment`,
`missing_domain_coverage`, `version_sensitive_confirmation`, `convergence_confirmation`,
`provenance_improvement`.

**`InvestigationCandidate`** visibly exposes: stable `candidate_id`, `domains`, `linked_finding_ids`
(stable `af_…` ids derived from the Phase-31 findings), `finding_types`, `max_severity`,
`investigation_type`, `evidence_requested`, `why_needed`, `current_evidence_state`,
`discriminating_requirement`, `expected_assurance_impact`, `impact_limitations`, the full
`dimensions` breakdown, `priority_score`, `priority_band`, `dependencies`, `defer_conditions`,
`rationale`, and an explicit `advisory_statement`.

## Candidate-generation rules

Findings are mapped to investigation types (grounded in the Phase-31 taxonomy) and **grouped by
(domain, investigation_type)** — so multiple findings for one domain **merge into one candidate**
(deduplication + cross-finding leverage). Mapping (examples):

| Phase-31 finding | Investigation |
| --- | --- |
| `open_contradiction` | contradiction_discrimination |
| `unresolved_regression` / `dependent_evidence_reliance` / `confirmed_good_unverified` | independence_improvement |
| `stale_knowledge` | revalidation |
| `version_sensitivity_unaddressed` | version_sensitive_confirmation |
| `single_context_reliance` | context_expansion |
| `critical_blind_spot` | missing_domain_coverage (labelled *untested, not disproven*) |
| `unknown_attribute` / `unverified_proxy` / `blocking_assumption` / `caps_readiness_mismatch` | assumption_establishment |
| `conflicting_maturity_signals` / `insufficient_evidence_for_grade` | convergence_confirmation |
| `readiness_without_coverage` | repeated_confirmation |
| `superseded` / `missing_transfer_boundary` / `non_deterministic_output` / `data_mutation_detected` | provenance_improvement |
| `no_known_knowledge` / `clean` | **no candidate** (truthful no-action) |

A fully-assured or empty programme returns a truthful empty / no-action result.

## Transparent scoring dimensions and weights

Every dimension exposes **raw · weight · contribution · rationale**; the priority score is a visible
signed sum (never one opaque number). Information-gain is weighted highest, mirroring the Phase-17
`DIMENSION_WEIGHTS["information_gain"] = 3.0` doctrine.

Value dimensions: `information_gain` 3.0, `blocker_clearance` 2.5, `cross_finding_leverage` 2.0,
`contradiction_discrimination` 2.0, `independence_gain` 1.75, `assumption_reduction` 1.5,
`freshness_value` 1.5, `context_relevance` 1.25, `evidence_availability` 1.0 (feasibility).
Penalty dimensions (negative contribution): `duplication_penalty` 1.5, `dependency_penalty` 1.5,
`collection_cost` 1.0.

`priority_score = Σ contributions` (value +, penalty −).

## Priority doctrine (encoded)

1. Blockers matter, but **severity is not the sole rule** — a blocking finding is downgraded to
   `DEFER` if it is infeasible or has an unresolved prerequisite, and a multi-finding
   (cross-leverage) candidate can outrank a single-blocker one within a band.
2. Prefer evidence that **changes what can be relied upon** (clear a blocker, resolve a contradiction,
   establish an assumption, restore version validity, improve independence, close a blind spot,
   reach convergence) — expressed as *potential*, never guaranteed.
3. **Independent evidence outranks dependent repetition.**
4. **Contradictions require discriminating evidence** — each contradiction candidate states what must
   differ; a generic "collect more laps" is explicitly insufficient. Never resolved by
   majority/recency/count/convenience.
5. Assumptions **stay assumptions** until established.
6. **Missing evidence is not negative evidence** (blind-spot candidates say *untested, not disproven*).
7. **Confirmed-good knowledge is protected** — no candidates for strongly-assured/current/converged
   domains.
8. **Duplicates merge** deterministically; one investigation may link many findings/domains.
9. **Hard prerequisites respected** — deterministic `_PREREQUISITE_PAIRS` (e.g. independence before
   contradiction discrimination; version confirmation before context expansion; context before
   convergence). A dependent candidate carries a `dependency_penalty`, is downgraded to `DEFER`, and
   **ranks after its prerequisite**.
10. **No scheduling** — a priority order, never a calendar.

## Deterministic ranking & tie-break

`priority_band` → `priority_score` desc → `blocker_clearance` contribution desc →
`cross_finding_leverage` desc → `information_gain` desc → `collection_cost` (cheaper first) →
canonical `KnowledgeDomain` order → `InvestigationType` order → stable `candidate_id`. No timestamp
affects ranking or the fingerprint.

## Relationship to Phase 17

Reuses the Phase-17 information-gain **doctrine** (transparent visible weighted valuation,
information-gain weighted highest) with an **assurance-specific data model**. It does **not** import
Phase-17 setup-experiment candidates (`ExperimentValuation` / `build_experiment_portfolio`), does not
schedule a Phase-17 experiment, and does not mutate a portfolio — asserted by a safety test. The
`assurance_engineering_priority` dimensions align conceptually with Phase-17's (information_gain,
dependency, effort/collection_cost, protection-of-confirmed-good) but operate on assurance findings,
not setup experiments.

## Read-only SessionDB orchestration

`SessionDB.build_assurance_engineering_priority_report(...)` returns `{"ok", "priority": <report
dict|None>, "grade", "candidate_count", "content_fingerprint"}`. It uses the shared
`_build_knowledge_chain` **once** (Phase-22 built once; Phase-23/24/25 derived purely), computes
Phase-26/27/28/29/30/31 **purely in memory**, then builds the priority report. It **never** calls the
lower public SessionDB report builders. The Phase-29 chain gate is unchanged, so negative-only
programmes remain analysable; truly empty programmes return the truthful empty result.

**Query-shape proof (tested):** Phase-22 built exactly once (monkeypatch); the nine lower SessionDB
builders (Phase 23–31) are never called; the development-records reads are bounded full-table scans
whose count is **constant** between small and large histories (no N+1) — Phase 32 itself adds zero
reads; the renderer touches no DB; the DB file is byte-identical and `user_version` stays 26.

## UI

`ui/assurance_engineering_priority_vm.py` (pure vm) + `ui/assurance_engineering_priority_panel.py`
(`AssuranceEngineeringPriorityPanel`, read-only) in the Development History page beneath the Phase-31
assurance verdict. No Apply / Run / Create / Schedule button, no editable priority input, no
setup-value control — asserted. `[COLLECT]` / `[DEFER]` text tags (not colour alone). Build runs
**off the Qt thread** via the reused `MechanismAnnotationWorker` with a stale-worker guard
(`_priority_worker`). Standalone construction preserved; truthful empty and no-action states.

## Fingerprint guarantees

`content_fingerprint = "assurance_engineering_priority_v1:" + sha256(payload)[:24]`, payload =
source identity + grade + finding counts + every candidate's (id, type, band, score, linked finding
ids, per-dimension raw/weight/contribution, dependency ids). No timestamp, object identity, address,
unordered dict, or DB row order. Verified identical across repeated builds, restart, shuffled input
rows and shuffled legal DB row order; changes when any material input (grade, finding, dimension,
weight, dependency, evidence request, deferral, order, membership) changes.

## Test totals (by suite)

| Suite | Count |
| --- | --- |
| `tests/test_phase32_domain.py` | 20 |
| `tests/test_phase32_scoring.py` | 13 |
| `tests/test_phase32_golden.py` | 9 (8 mandated scenarios + shuffle-stability) |
| `tests/test_phase32_integration.py` | 8 |
| `tests/test_phase32_safety.py` | 14 |
| `tests/test_phase32_ui_construction.py` | 11 |
| **Total** | **75** |

## Runtime verification

DB byte-identical before/after; `user_version` 26; repeated-build fingerprints identical;
restart-identical; shuffled legal row order → identical rendering **and** fingerprint; query count
constant (7 vs 7) between small and large history; no setup value / no date in report or UI;
ASCII-clean; negative-only programme remains visible; empty programme truthful; fully-assured
programme returns no unnecessary investigation work.

## Known caveats

- The Phase-32 UI off-thread test uses the repository's shared-`QApplication`.`exec()` pattern. It
  passes standalone and in combined runs; the previously-documented intermittent multi-file
  `app.exec()` timing artifact did not reproduce here (full 26–32 combined UI run: 71 passed).
- `evidence_availability` is a conservative feasibility proxy (a domain with no recorded evidence, or
  an unmet prerequisite, is deferred). It is not a resource model — no resources are ever allocated.

## Boundaries confirmed

No schema migration; no new persistent tables/fields; no DB write; no setup values; no experiment /
campaign / schedule / resource allocation; no Apply path; no AI/optimiser/scheduler; Phase-17
portfolio not imported or mutated; `_setup_constants.py` byte-identical; DB v26 / rule-engine 46.0.

**Phase 33 not started.**
