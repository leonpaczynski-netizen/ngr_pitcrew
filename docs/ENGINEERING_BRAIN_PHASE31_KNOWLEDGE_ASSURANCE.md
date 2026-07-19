# Engineering Brain — Program 2, Phase 31: Knowledge Assurance & Audit Report (FINAL)

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase31-knowledge-assurance`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

The **final** layer of Program 2. A **read-only, advisory** AUDIT that examines the whole knowledge
programme — re-validation (26), coverage (27), readiness (28), contradiction (29) and assumptions
(30) — for **assurance findings**, and grades whether the engineering knowledge can be **ASSURED**.
It reports findings **only**; it authors no setup, schedules no test, and changes nothing.

## Core doctrine (test-guarded)

- **A single BLOCKING finding prevents ASSURED** (and prevents ASSURED_WITH_LIMITATIONS) — the grade
  drops to NOT_ASSURED.
- **Defects the audit catches:** hidden assumptions, unresolved contradictions, unresolved
  regressions, missing transfer boundaries, single-context / dependent reliance, critical blind
  spots, stale/version-unaddressed knowledge, unknown-attribute / unverified-proxy reliance,
  readiness-vs-coverage and readiness-vs-assumption inconsistency, **non-determinism** (a knowledge
  product lacking a stable content fingerprint) and **data mutation** (a read-only build that wrote).
- **The grade is rule-based over visible severity counts, not an opaque score** — the report always
  exposes the counts + the fired rule. Too little established knowledge → `INSUFFICIENT_EVIDENCE`.
- **Deterministic**: restart, shuffled input rows and different legal row order → byte-identical; the
  content fingerprint carries no timestamp. (The audit's own structural self-check flags any sub-
  report that would break this.)

## Vocabulary

**AssuranceFindingType (22):** `OPEN_CONTRADICTION`, `UNRESOLVED_REGRESSION`,
`BLOCKING_ASSUMPTION_PRESENT`, `ASSUMPTION_CAPS_READINESS_MISMATCH`, `HIDDEN_ASSUMPTION`,
`STALE_KNOWLEDGE`, `VERSION_SENSITIVITY_UNADDRESSED`, `SINGLE_CONTEXT_RELIANCE`,
`DEPENDENT_EVIDENCE_RELIANCE`, `CRITICAL_BLIND_SPOT`, `MISSING_TRANSFER_BOUNDARY`,
`CONFIRMED_GOOD_UNVERIFIED`, `CONFLICTING_MATURITY_SIGNALS`, `SUPERSEDED_STILL_REFERENCED`,
`READINESS_WITHOUT_COVERAGE`, `UNKNOWN_ATTRIBUTE_RELIANCE`, `UNVERIFIED_PROXY_RELIANCE`,
`INSUFFICIENT_EVIDENCE_FOR_GRADE`, `NO_KNOWN_KNOWLEDGE`, `NON_DETERMINISTIC_OUTPUT`,
`DATA_MUTATION_DETECTED`, `CLEAN`.
**AssuranceSeverity (5):** `BLOCKING`, `MAJOR`, `MODERATE`, `MINOR`, `INFORMATIONAL`.
**ProgrammeAssuranceGrade (5):** `ASSURED`, `ASSURED_WITH_LIMITATIONS`, `PARTIALLY_ASSURED`,
`NOT_ASSURED`, `INSUFFICIENT_EVIDENCE`.

### Grade rules (visible)

no known knowledge → `INSUFFICIENT_EVIDENCE`; any `BLOCKING` → `NOT_ASSURED`; else any `MAJOR` →
`PARTIALLY_ASSURED`; else any `MODERATE`/`MINOR` → `ASSURED_WITH_LIMITATIONS`; else → `ASSURED`.

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/assurance_finding.py` | `AssuranceFindingType` (22) + `AssuranceSeverity` (5) + default severity + finding text |
| `strategy/assurance_grade.py` | `ProgrammeAssuranceGrade` (5) + `grade_assurance(findings, has_known_knowledge)` → rule-based grade + counts + fired rule |
| `strategy/knowledge_assurance.py` | `audit(readiness, contradiction, assumptions, coverage, revalidation)` → (findings, has_known); dedups by (type, domain) keeping the most severe; structural self-check for missing fingerprints; CLEAN when nothing above informational |
| `strategy/programme_assurance_report.py` | `build_programme_assurance_report(readiness, contradiction, assumptions, coverage, revalidation)` → `ProgrammeAssuranceReport`; blocking/major/moderate-minor/informational buckets + audit summary + grade detail |
| `strategy/programme_assurance_report_render.py` | `render_assurance_sections` / `render_assurance_text` — strings only, zero DB |

## SessionDB entry (read-only) — the full chain

`SessionDB.build_programme_assurance_report(...)` returns `{"ok", "assurance": <report dict|None>,
"grade", "finding_count", "content_fingerprint"}`.

It uses the shared **`_build_knowledge_chain`** (Phase-22 built **once**; Phase-23/24/25 derived
purely; records returned by the chain), then computes the Phase-26 re-validation, Phase-27 coverage,
Phase-28 readiness, Phase-29 contradiction and Phase-30 assumptions **purely in memory**, and audits
them. It **never** calls the Phase-23/24/25/26/27/28/29/30 SessionDB entry points. No N+1; renderer
zero DB; no writes; DB byte-identical; `user_version` stays 26.

## UI

`ui/engineering_assurance_vm.py` (pure vm) + `ui/engineering_assurance_panel.py`
(`EngineeringAssurancePanel`, read-only) placed near the **top** of the Development History page
beneath the Phase-28 readiness executive summary (the assurance verdict pairs with it). States use
**text tags** (`[VERDICT]`, `[REVIEW]`) not colour alone. No Apply / edit / schedule control exists.
The heavy build runs **off the Qt thread** via the reused `MechanismAnnotationWorker`; a stale worker
result cannot replace a newer one (`_assurance_worker` guard).

## Tests (61 assertions across 5 files + regression)

- `test_phase31_domain.py` (16) — the 22/5/5 vocabulary; each audit derivation (open contradiction
  blocking, regression blocking, assumption reliance, caps-readiness mismatch, non-determinism,
  no-known, clean, dedup) + the full grade ladder.
- `test_phase31_golden.py` (10) — the mandated behaviours 1–10.
- `test_phase31_integration.py` (8) — Phase-22 built once; Phase-23/24/25/26/27/28/29/30 DB entries
  never called; query count constant (no N+1); renderer no DB; no writes / DB hash + counts +
  user_version unchanged; empty cheap; result shape; the real pipeline raises no non-determinism /
  mutation finding.
- `test_phase31_safety.py` (13) — no forbidden imports / wall-clock / setup-gen / scheduling; no
  duplicate authority; blocking prevents ASSURED; grade rule-based (no weight/score); defect finding
  types recognised; no setup-value leak; `_setup_constants.py` unchanged; no-AI scan.
- `test_phase31_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.
- Regression: Phase 26/27/28/29/30 integration green.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.

## Programme note

Phase 31 closes Program 2's engineering-knowledge assurance stack. **Phase 32 is NOT started.**
