# Engineering Brain — Program 2, Phase 29: Knowledge Contradiction Resolution

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase29-contradiction-resolution`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

A **read-only, advisory** layer that finds, per known engineering domain, where the evidence
**contradicts itself** (a confirming *and* a regressing conclusion for the same domain) and
characterises each disagreement: its visible **causes** and whether it is resolved by context,
resolved by stronger independent evidence, superseded, or **genuinely open**. It reports resolution
**status only** — it authors no setup, schedules no test, and is willing to say *the evidence does
not tell us which conclusion is right*.

It reuses the canonical Phase-25 record→domain mapping verbatim (invents no domains), and grounds
every contradiction in **real records** (never in a flag alone).

## Core doctrine (test-guarded)

- **Never resolved by majority or averaging.** Counting how many records fall on each side decides
  nothing — a larger count of dependent observations never wins.
- **Dependent evidence can never defeat independent evidence.** Independence (distinct sessions +
  high confidence), not count, is what stands.
- **Newer evidence does not automatically win.** Supersession requires the later side to be **also
  stronger**, not merely later — checked before the concurrent independence case so recency alone
  never decides.
- **A version / context mismatch is always surfaced** as a visible cause, never silently ignored;
  a context difference lets both conclusions hold within their own contexts.
- **A contradiction may stay UNRESOLVED** — a genuine same-context disagreement between comparably
  supported sides is reported as open.
- **Deterministic**: restart, shuffled input rows and different legal row order → byte-identical; the
  content fingerprint carries no timestamp.

## ContradictionCause (19)

Context (9): `DIFFERENT_CAR`, `DIFFERENT_TRACK`, `DIFFERENT_LAYOUT`, `DIFFERENT_DRIVER`,
`DIFFERENT_COMPOUND`, `DIFFERENT_GT7_VERSION`, `DIFFERENT_DISCIPLINE`, `DIFFERENT_FUEL_OR_TYRE_RULE`,
`DIFFERENT_BASELINE_SETUP`. Evidence-quality (5): `DEPENDENT_EVIDENCE_ON_ONE_SIDE`,
`LOW_CONFIDENCE_EVIDENCE`, `SINGLE_OBSERVATION`, `WITHIN_MEASUREMENT_NOISE`,
`SUPERSEDED_BY_LATER_EVIDENCE`. Directional (2): `REGRESSION_VS_CONFIRMATION`,
`NON_MONOTONIC_RESPONSE`. Residual (3): `UNKNOWN_CONTEXT_DIFFERENCE`,
`INSUFFICIENT_EVIDENCE_TO_EXPLAIN`, `GENUINE_UNEXPLAINED_CONTRADICTION`.

## ContradictionStatus (9)

`NOT_A_CONTRADICTION`, `RESOLVED_BY_CONTEXT`, `RESOLVED_BY_INDEPENDENCE`, `RESOLVED_BY_SUPERSESSION`,
`RESOLVED_WITHIN_NOISE`, `PARTIALLY_RESOLVED`, `UNRESOLVED`, `UNRESOLVED_INSUFFICIENT_EVIDENCE`,
`UNKNOWN`.

### Resolution ladder (top wins)

context difference → **supersession** (later AND stronger) → **independence** (independent outweighs
dependent) → both-weak → insufficient → **UNRESOLVED** (genuine open contradiction).

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/contradiction_cause.py` | `ContradictionCause` (19) + `context_difference_causes(pos, neg)` (disjoint context-value detection) + `CONTEXT_RESOLVING_CAUSES` + cause text |
| `strategy/contradiction_resolution_status.py` | `ContradictionStatus` (9) + `resolve(signals)` deterministic ladder; never by majority/recency; `RESOLVED_STATUSES` |
| `strategy/knowledge_contradiction.py` | `detect_contradiction(domain, positive_records, negative_records)` → `KnowledgeContradiction`; computes per-side signals (context spread, distinct sessions, confidence, dates — independence, not count) |
| `strategy/programme_contradiction_report.py` | `build_programme_contradiction_report(timeline, programme, records)` → `ProgrammeContradictionReport`; buckets records positive/negative per domain via the reused canonical mapping; a contradiction exists only where a domain has BOTH sides |
| `strategy/programme_contradiction_report_render.py` | `render_contradiction_sections` / `render_contradiction_text` — strings only, zero DB |

## SessionDB entry (read-only) + shared-chain change

`SessionDB.build_programme_contradiction_report(...)` returns `{"ok", "contradiction": <report
dict|None>, "contradiction_count", "open_count", "content_fingerprint"}`.

It reuses the shared **`_build_knowledge_chain`** and the records it returns. **The shared chain gate
was relaxed** from "known_domains non-empty" to "known_domains non-empty **OR** any recorded
evidence": regressions retire domains out of `known_domains`, so the previous gate hid exactly the
contradiction evidence this phase exists to analyse. The Phase-25 timeline already keeps negative
learning visible regardless, so this is a strict, consistent improvement — Phase 26/27/28 remain
green (their confirmation-based tests are unaffected; a fully-retired programme now correctly shows
its regressed domains instead of nothing). Empty programmes (no known domains **and** no evidence)
still yield no chain. No N+1; renderer zero DB; no writes; DB byte-identical; `user_version` stays 26.

## UI

`ui/engineering_contradiction_vm.py` (pure vm) + `ui/engineering_contradiction_panel.py`
(`EngineeringContradictionPanel`, read-only) embedded in the **Development History** page beneath the
Phase-27 coverage panel. States use **text tags** (`[OPEN]`, `[RESOLVED]`) not colour alone. No
Apply / edit / schedule control exists. The heavy build runs **off the Qt thread** via the reused
`MechanismAnnotationWorker`; a stale worker result cannot replace a newer one (`_contradiction_worker`
guard).

## Tests (68 assertions across 5 files + regression)

- `test_phase29_domain.py` (15) — 19 causes / 9 statuses; context-difference detection; the full
  resolution ladder (context / independence-not-count / newer-not-auto-win / later-and-stronger /
  genuine-unresolved / both-weak); end-to-end `detect_contradiction`.
- `test_phase29_golden.py` (10) — the mandated behaviours 1–10.
- `test_phase29_integration.py` (6) — Phase-22 built once; Phase-23/24/25 DB entries never called;
  query count constant vs event count (no N+1); renderer no DB; no writes / DB hash + counts +
  user_version unchanged; empty cheap; result shape + detects a contradiction.
- `test_phase29_safety.py` (13) — no forbidden imports / wall-clock / setup-gen / scheduling; no
  duplicate authority; reuses `_record_domains`; never resolves by majority or recency; contradiction
  may stay open; version mismatch visible; no setup-value leak; `_setup_constants.py` unchanged;
  no-AI scan.
- `test_phase29_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.
- Regression: Phase 25/26/27/28 (107) green after the shared-chain gate relaxation.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.
