# Engineering Brain — Program 2, Phase 28: Engineering Knowledge Readiness Report

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase28-knowledge-readiness`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

The **executive-summary capstone** of Program 2. A **read-only, advisory** layer that states, per
known engineering domain, **whether the evidence supports relying on the knowledge for a decision**
(ready / ready within limits / provisional / not yet ready — and why), and grades the whole
programme with a **transparent, rule-based grade**. It reports readiness **status only** — "ready"
means "the evidence supports relying on it", **never** "apply this setup"; it recommends no setup,
schedules no test, creates no experiment/campaign, and never marks unvalidated knowledge ready.

It synthesises the Phase-25 convergence, Phase-26 re-validation and Phase-27 coverage/blind-spot
authorities **verbatim** — it re-derives none of them and invents no domains.

## Core doctrine (test-guarded)

- **"Ready" ≠ "apply this setup".** Readiness is about whether the evidence supports *relying on the
  knowledge*, not about setting a value. The phrase "apply this setup" appears only inside denial
  text.
- **Unvalidated knowledge is never READY.** A merely-converging / mixed / insufficient / unknown
  domain never comes out READY.
- **A recorded conflict or regression blocks readiness** (`CONFLICTED` / `REGRESSED`) **and prevents
  a HIGH grade**, regardless of how many other domains are ready.
- **The grade is rule-based, not an opaque score.** `ProgrammeReadinessGrade` (HIGH / MEDIUM / LOW /
  INSUFFICIENT_EVIDENCE) is decided by a small set of visible rules over counts, and the report
  always exposes the counts + the rule that fired. Too few assessable domains →
  `INSUFFICIENT_EVIDENCE` rather than a falsely low/high grade.
- **Deterministic**: restart, shuffled input rows and different legal row order produce byte-
  identical output; the content fingerprint carries no timestamp.

## KnowledgeReadinessStatus (11) — the per-domain ladder (top wins)

`SUPERSEDED` → `CONFLICTED` → `REGRESSED` → `NEEDS_REVALIDATION` (version/context change) →
`INSUFFICIENT_EVIDENCE` → `NEEDS_MORE_EVIDENCE` (critical blind spot) → `READY` /
`READY_WITH_LIMITATIONS` (strong + current + covered) → `CONTEXT_BOUND_ONLY` →
`READY_WITH_LIMITATIONS` (confirmed-good on material blind spot) → `PROVISIONAL` (converging/mixed) →
`NEEDS_MORE_EVIDENCE` (remaining gaps) → `UNKNOWN`.

`RELYABLE_STATUSES = {ready, ready_with_limitations, context_bound_only}`;
`BLOCKING_STATUSES = {conflicted, regressed}`.

## Programme grade rules (visible thresholds)

`MIN_ASSESSABLE_FOR_GRADE = 2`, `HIGH_RELYABLE_FRACTION = 0.75`, `MEDIUM_RELYABLE_FRACTION = 0.40`.
`assessable` excludes insufficient/unknown domains; `relyable / assessable` decides HIGH/MEDIUM/LOW;
any blocker caps the grade below HIGH.

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/knowledge_readiness.py` | `KnowledgeReadinessStatus` (11) + `READINESS_PRIORITY` + `RELYABLE_STATUSES`/`BLOCKING_STATUSES` + `classify_readiness(convergence, revalidation_item, coverage_item)` → `KnowledgeReadinessItem` (status, limiting factors, `usable_as`, what would raise readiness) |
| `strategy/readiness_grade.py` | `ProgrammeReadinessGrade` (4) + `grade_programme(items)` → rule-based grade + visible counts + fired rule + reasons |
| `strategy/programme_readiness_report.py` | `build_programme_knowledge_readiness_report(timeline, programme, revalidation, coverage)` → `ProgrammeKnowledgeReadinessReport` (per-domain items, ready/ready-with-limits/blocked/not-yet buckets, executive summary, grade detail, fingerprint) |
| `strategy/programme_readiness_report_render.py` | `render_readiness_sections` / `render_readiness_text` — strings only, zero DB, no setup values / scheduling / dates-as-action |

## SessionDB entry (read-only)

`SessionDB.build_programme_knowledge_readiness_report(...)` returns `{"ok", "readiness": <report
dict|None>, "grade", "domain_count", "content_fingerprint"}`.

It uses the shared **`_build_knowledge_chain`** (Phase-22 built **once**; Phase-23/24/25 derived
purely; one bounded bulk read whose records the chain returns), then computes the Phase-26
re-validation and Phase-27 coverage **purely in memory**. It **never** calls the Phase-23/24/25/26/27
SessionDB entry points. No N+1 (query count constant vs event count); renderer performs zero DB
access; no writes; DB byte-identical; `user_version` stays 26.

## UI

`ui/engineering_readiness_vm.py` (pure vm) + `ui/engineering_readiness_panel.py`
(`EngineeringReadinessPanel`, read-only) placed at the **top** of the Development History page (it is
the executive summary). States use **text tags** (`[READY]`, `[REVIEW]`) not colour alone. No Apply /
edit / schedule control exists. The heavy build runs **off the Qt thread** via the reused
`MechanismAnnotationWorker`; a stale worker result cannot replace a newer one (`_readiness_worker`
guard).

## Tests (83 assertions across 5 files + regression)

- `test_phase28_domain.py` (20) — the 11-status ladder + rule-based grade (HIGH needs no blocker;
  single blocker prevents HIGH; insufficient-when-too-few; counts/rule exposed; low/empty).
- `test_phase28_golden.py` (10) — the mandated behaviours 1–10.
- `test_phase28_integration.py` (7) — Phase-22 built once; Phase-23/24/25/26/27 DB entries never
  called; query count constant vs event count (no N+1); renderer no DB; no writes / DB hash + counts
  + user_version unchanged; empty cheap; result shape.
- `test_phase28_safety.py` (13) — no forbidden imports / wall-clock / setup-gen / scheduling; no
  duplicate authority or redefined canonical enums; grade rule-based (no opaque score/weight);
  unvalidated never ready; "ready" never means "apply this setup"; no setup-value leak;
  `_setup_constants.py` unchanged; no-AI scan.
- `test_phase28_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.
- Regression: Phase 26/27 integration green after reusing the shared chain.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.
