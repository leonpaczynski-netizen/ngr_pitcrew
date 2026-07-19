# Engineering Brain — Program 2, Phase 26: Knowledge Decay & Re-validation Status

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase26-knowledge-revalidation`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

A **read-only, advisory** layer that reports, per knowledge domain, whether established engineering
knowledge remains **current / protected** or may need **re-validation** — because the context or
GT7 version changed, or because the evidence weakened (conflict / regression / dependence / unknown
date or context). It reports **status only**. It schedules nothing, creates no reminders or future
dates, generates no test plan, authors no setup, and never touches the Apply gate.

It sits **above** the Phase-25 convergence/timeline authority and reuses it verbatim; it re-derives
no diagnosis, transfer, timeline or convergence logic.

## Core doctrine (enforced by tests)

- **Age alone never decays knowledge.** There is no fixed expiry, no "older than N days" rule, and
  no date arithmetic anywhere in the pure layer (`timedelta`, `days_since`, `fromisoformat`, etc.
  are all absent and guarded). Old but independently-confirmed compatible knowledge stays CURRENT.
- **Dates are evidence data, never authority.** A newer record is never automatically more correct.
- **A version change re-validates only version-sensitive knowledge** (domains whose Phase-25
  transfer limitations mention the GT7 version). Version-insensitive knowledge is *not* invalidated
  by a version change.
- **Confirmed-good behaviour stays protected** unless evidence explicitly invalidates it — an
  unrelated direction regressing does not un-protect it.
- **Conflict weakens certainty without deleting history**; **regression** marks the tested direction
  weakened or **retired**; **superseded** knowledge stays visible but inactive; **retired** stays
  retired.
- **Unknown date → INSUFFICIENT_DATE_EVIDENCE**, unknown context → INSUFFICIENT_CONTEXT_EVIDENCE —
  never automatic invalidation. Unknown stays explicitly unknown.
- **Deterministic**: no wall-clock, random, row/dict/insertion order reliance. Restart, shuffled
  input rows and different legal row order produce byte-identical output. Content fingerprint carries
  no timestamp.

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/revalidation_reason.py` | `RevalidationReason` (20 visible reasons) + `context_change_reason(field)` + `reasons_from_signals(signals)` — a reason is emitted only when its explicit signal is present |
| `strategy/knowledge_decay.py` | `programme_context_changes(compatibility)` (version/context change from Phase-22 `excluded_reasons.differing_fields`, verbatim) + `decay_signals(convergence, timeline_points, programme_changes)` — the visible signals that decide status. `MIN_INDEPENDENT_FOR_ROBUST = 2` |
| `strategy/revalidation_status.py` | `KnowledgeFreshnessStatus` (12) + `FRESHNESS_PRIORITY` (visible ordering) + `classify_revalidation(signals, source_programme)` — the deterministic ladder |
| `strategy/programme_revalidation_report.py` | `build_revalidation_report(timeline, programme_knowledge)` → `ProgrammeRevalidationReport` (buckets, totals, safety statement, content fingerprint) |
| `strategy/programme_revalidation_report_render.py` | `render_revalidation_sections` / `render_revalidation_text` — strings only, zero DB, no setup values / scheduling / dates-as-action |

### Freshness ladder (top wins)

`SUPERSEDED` → `RETIRED` (only when not confirmed-good and convergence is regressed/conflicting/
mixed/unknown) → `WEAKENED_BY_CONFLICT` → `WEAKENED_BY_REGRESSION` (unless confirmed-good) →
`INVALIDATED_BY_VERSION_CHANGE` (version-sensitive + version changed) → `INSUFFICIENT_DATE_EVIDENCE`
→ `INSUFFICIENT_CONTEXT_EVIDENCE` → confirmed-good ⇒ `CURRENT` / `CURRENT_BUT_CONTEXT_BOUND` →
`strongly_converged` ⇒ `CURRENT` → context-bound ⇒ `CURRENT_BUT_CONTEXT_BOUND` → dependent-heavy or
converging/mixed ⇒ `REVALIDATION_ADVISED` → `insufficient_evidence` ⇒
`INSUFFICIENT_CONTEXT_EVIDENCE` → else `UNKNOWN`.

## SessionDB entry (read-only)

`SessionDB.build_programme_revalidation_report(memory_context_key="", *, applied_setup, …, **ctx)`
returns `{"ok", "revalidation": <report dict|None>, "domain_count", "content_fingerprint"}`.

It uses the shared **`_build_knowledge_chain`** helper, which builds the Phase-22 knowledge report
**once**, then derives Phase-23 transfer + Phase-24 playbook + Phase-25 timeline **purely** in
memory (one bounded `_timeline_evidence_records` bulk read). It **never** calls the Phase-23/24/25
SessionDB entry points. No N+1 (query count constant vs event count); renderer performs zero DB
access; no writes; DB stays byte-identical; `user_version` stays 26.

## UI

`ui/engineering_revalidation_vm.py` (pure vm) + `ui/engineering_revalidation_panel.py`
(`EngineeringRevalidationPanel`, read-only) embedded in the **Development History** page beneath the
Phase-25 timeline panel. States use **text tags** (`[PROTECT]`, `[REVIEW]`) not colour alone. No
Apply / Freeze / Complete / Execute / edit / schedule control exists. The heavy build runs **off the
Qt thread** via the reused `MechanismAnnotationWorker`; a stale worker result cannot replace a newer
one (handler guards on the current worker reference).

## Tests (70 assertions across 5 files)

- `test_phase26_domain.py` (20) — context-change detection, decay signals, reason gating, the full
  classification ladder, report assembly + fingerprint stability.
- `test_phase26_golden.py` (10) — the mandated behaviours 1–10 (age stays current; unknown date;
  version-sensitive re-validation; version-insensitive protected; context narrows to aid; conflict
  weakens without deleting; regression weakens/retires; confirmed-good protected; superseded
  visible-but-inactive; restart + shuffle identical).
- `test_phase26_integration.py` (7) — Phase-22 built once; Phase-23/24/25 DB entries never called;
  query count constant vs event count (no N+1); renderer no DB; no writes / DB hash + counts +
  user_version unchanged; empty is cheap; result shape.
- `test_phase26_safety.py` (13) — no forbidden imports / wall-clock / setup generation / scheduling;
  no duplicate authority or redefined canonical enums; no date arithmetic (age can't decay); no
  setup-value leak; safety-denial language present; `_setup_constants.py` unchanged; no-AI scan.
- `test_phase26_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.
