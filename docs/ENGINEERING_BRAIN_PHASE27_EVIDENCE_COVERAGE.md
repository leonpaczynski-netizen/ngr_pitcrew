# Engineering Brain — Program 2, Phase 27: Evidence Coverage & Blind-Spot Mapping

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase27-evidence-coverage`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

A **read-only, advisory** layer that maps, per knowledge domain, **where the evidence is well
supported and where more evidence would strengthen confidence** (a *blind spot*). It assesses each
grounded domain across 18 visible **coverage dimensions**, ranks the resulting blind spots by
severity, and reports coverage **status only** — it recommends no setup, schedules no test, creates
no experiment/campaign, and never treats the absence of evidence as a negative result.

It sits **above** the Phase-25 convergence/timeline authority and reuses it (plus Phase-23 transfer
and Phase-26 re-validation) verbatim. It invents **no domains** and re-implements **no** record→
domain mapping — it reuses the canonical Phase-25 mapping.

## Core doctrine (test-guarded)

- **MISSING ≠ negative.** The absence of evidence (`MISSING`) is a distinct status from a recorded
  negative result (`REGRESSION_ONLY`); the two are never conflated. Missing coverage means
  *untested, never wrong*.
- **A blind spot ≠ a problem.** It is a place where more evidence would help. Early-stage domains
  with gaps are flagged `INFORMATIONAL`, explicitly "not a concern".
- **A large dependent-evidence count is never strong coverage** — only genuinely independent lines
  count (`DEPENDENT_EVIDENCE_ONLY` regardless of dependent magnitude).
- **One distinct track / car / driver / compound / discipline / version is `SINGLE_CONTEXT_ONLY`**,
  never multi-context coverage.
- **Severity reflects reliance vs evidence.** A strong claim (confirmed-good / mature / high
  confidence) resting on thin, single-context or dependent-only evidence is the important
  (`CRITICAL` / `MATERIAL`) blind spot; an unresolved conflict in a relied-upon domain is `CRITICAL`.
- Reuses Phase-23 transfer, Phase-25 convergence and Phase-26 re-validation. **Deterministic**:
  restart, shuffled input rows and different legal row order produce byte-identical output; the
  content fingerprint carries no timestamp.

## The 18 coverage dimensions

Context-breadth (counted from record contexts): `track_variety`, `layout_variety`, `car_variety`,
`driver_variety`, `discipline_variety`, `gt7_version_variety`, `tyre_compound_variety`,
`corner_phase_coverage`, `corner_type_coverage`.
Evidence-quality (from convergence / independence / re-validation): `independent_replication`,
`repeated_confirmation`, `high_confidence_evidence`, `regression_check`,
`confirmed_good_verification`, `conflict_resolution`, `convergence_achieved`, `transfer_validation`,
`revalidation_currency`.

**CoverageStatus (9):** `WELL_COVERED`, `ADEQUATELY_COVERED`, `PARTIALLY_COVERED`,
`DEPENDENT_EVIDENCE_ONLY`, `SINGLE_CONTEXT_ONLY`, `CONFLICTED_COVERAGE`, `REGRESSION_ONLY`,
`MISSING`, `UNKNOWN`.
**BlindSpotSeverity (5):** `CRITICAL`, `MATERIAL`, `MODERATE`, `INFORMATIONAL`, `UNKNOWN`.

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/coverage_dimension.py` | `CoverageDimension` (18) + `CoverageStatus` (9) + `BlindSpotSeverity` (5) + visible threshold constants (`BREADTH_WELL_COVERED`=3, `BREADTH_ADEQUATE`=2, `MIN_INDEPENDENT_FOR_ROBUST`=2, …) + `GAP_STATUSES` + priority maps |
| `strategy/evidence_coverage.py` | `coverage_signals(records)` (distinct-context counts, phase/corner counts, confirmations/regressions) + `assess_domain_coverage(domain, records, convergence, revalidation_item)` → `DomainCoverage` (per-dimension status + detail) |
| `strategy/knowledge_blind_spot.py` | `classify_blind_spot(coverage)` → `KnowledgeBlindSpot`; severity = gap between reliance (maturity/confidence/confirmed-good) and evidence robustness (independent lines/contexts/convergence); every blind spot carries "not a fault … untested, never wrong" |
| `strategy/programme_coverage_report.py` | `build_programme_evidence_coverage_report(timeline, programme, revalidation, records)` → `ProgrammeCoverageReport`; buckets records per domain via the reused canonical `_record_domains`, assesses each convergence domain, ranks blind spots (raised / early-stage / unassessable), totals + fingerprint |
| `strategy/programme_coverage_report_render.py` | `render_coverage_sections` / `render_coverage_text` — strings only, zero DB, no setup values / scheduling / dates-as-action |

## SessionDB entry (read-only)

`SessionDB.build_programme_evidence_coverage_report(...)` returns `{"ok", "coverage": <report
dict|None>, "domain_count", "blind_spot_count", "content_fingerprint"}`.

It uses the shared **`_build_knowledge_chain`** helper (Phase-22 built **once**; Phase-23/24/25
derived purely; one bounded `_timeline_evidence_records` bulk read). The chain now **additively
returns the evidence records** it read, so Phase 27 derives per-domain context breadth **without a
second DB query**. Phase 26 re-validation is computed **purely in memory** from the same chain. It
**never** calls the Phase-23/24/25/26 SessionDB entry points. No N+1 (query count constant vs event
count); renderer performs zero DB access; no writes; DB byte-identical; `user_version` stays 26.

## UI

`ui/engineering_coverage_vm.py` (pure vm) + `ui/engineering_coverage_panel.py`
(`EngineeringCoveragePanel`, read-only) embedded in the **Development History** page beneath the
Phase-26 re-validation panel. States use **text tags** (`[REVIEW]`, `[COVERED]`) not colour alone.
No Apply / Freeze / Complete / Execute / edit / schedule control exists. The heavy build runs **off
the Qt thread** via the reused `MechanismAnnotationWorker`; a stale worker result cannot replace a
newer one (`_coverage_worker` guard).

## Tests (69 assertions across 5 files)

- `test_phase27_domain.py` (17) — the 18 enums/orderings; MISSING≠REGRESSION distinctness; signal
  counting; each per-dimension rule; blind-spot severity (confirmed-good-thin→critical,
  emerging→informational, conflict-relied-upon→critical); blind spots never framed as faults.
- `test_phase27_golden.py` (10) — the mandated behaviours 1–10.
- `test_phase27_integration.py` (7) — Phase-22 built once; Phase-23/24/25/26 DB entries never
  called; query count constant vs event count (no N+1); renderer no DB; no writes / DB hash + counts
  + user_version unchanged; empty cheap; result shape; no setup-value leak through the records.
- `test_phase27_safety.py` (13) — no forbidden imports / wall-clock / setup-gen / scheduling; no
  duplicate authority or redefined canonical enums; reuses `_record_domains`; MISSING distinct from
  REGRESSION; no setup-value leak; safe blind-spot framing; `_setup_constants.py` unchanged; no-AI
  scan.
- `test_phase27_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.
