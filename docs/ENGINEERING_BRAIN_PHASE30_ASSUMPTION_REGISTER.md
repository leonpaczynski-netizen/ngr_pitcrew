# Engineering Brain — Program 2, Phase 30: Engineering Assumption Register

**Status:** DONE (committed, not pushed) · **Branch:** `eng-brain-phase30-assumption-register`
· **DB:** v26 (no migration) · **RULE_ENGINE_VERSION:** 46.0 (unchanged)

## What it is

A **read-only, advisory** layer that makes explicit the **assumptions** the programme's engineering
knowledge relies on but has **not established** — things a conclusion depends on that are not
themselves directly evidenced (transfer assumed, single-context result assumed to generalise,
dependent evidence relied on as if independent, knowledge assumed still current, confirmed-good
assumed to persist, version stability assumed, one side of an open contradiction assumed, unknown
vehicle attributes, unverified proxies). It classifies each, states its impact, and records that an
assumption can only **CAP** how ready knowledge may be, **never create** readiness.

It reuses the Phase-24 playbook boundaries + the Phase-25/26/27/29 authorities verbatim; it lists
only assumptions, **never facts**.

## Core doctrine (test-guarded)

- **Facts ≠ assumptions.** A directly-evidenced conclusion (strong convergence, current, no coverage
  gaps, no open contradiction) is a FACT and produces **no** assumption. `is_factual(...)` gates it.
- **Assumptions cannot create readiness — only cap it.** `AssumptionImpact` has no positive member;
  `IMPACT_READINESS_CAP` maps every impact to a ceiling in
  `{not_ready, context_bound_only, ready_with_limitations, ready}` — never above.
- **Conservative bounds are labelled** (`is_conservative_bound=True`,
  `status=EXPLICIT_AND_LABELLED`) — a deliberate caution, not a defect.
- **Deterministic**: restart, shuffled input rows and different legal row order → byte-identical; the
  content fingerprint carries no timestamp.

## AssumptionType (16)

`TRANSFER_ASSUMED`, `GENERALISATION_FROM_SINGLE_CONTEXT`, `INDEPENDENCE_ASSUMED`, `CURRENCY_ASSUMED`,
`CONTEXT_COMPARABILITY_ASSUMED`, `UNKNOWN_VEHICLE_ATTRIBUTE_ASSUMED`, `UNVERIFIED_PROXY_ASSUMED`,
`CONFIRMED_GOOD_PERSISTS_ASSUMED`, `VERSION_STABILITY_ASSUMED`, `DRIVER_CONSISTENCY_ASSUMED`,
`COMPOUND_EQUIVALENCE_ASSUMED`, `BASELINE_EQUIVALENCE_ASSUMED`, `NO_INTERACTION_ASSUMED`,
`MONOTONIC_RESPONSE_ASSUMED`, `CONTRADICTION_SIDE_ASSUMED`, `MEASUREMENT_RELIABILITY_ASSUMED`.

**AssumptionStatus (8):** `EXPLICIT_AND_LABELLED`, `EVIDENCE_BACKED_PARTIALLY`, `UNVERIFIED`,
`AT_RISK`, `CONTRADICTED`, `CONSERVATIVE_BOUND`, `RESOLVED`, `UNKNOWN`.
**AssumptionImpact (6):** `BLOCKS_RELIANCE`, `CAPS_READINESS`, `NARROWS_SCOPE`,
`WEAKENS_CONFIDENCE`, `INFORMATIONAL`, `UNKNOWN` — all non-positive.

## Modules (pure — Qt-free, DB-free, no wall-clock, never raise)

| Module | Responsibility |
| --- | --- |
| `strategy/assumption_classification.py` | `AssumptionType` (16) + `AssumptionStatus` (8) + priority + type text |
| `strategy/assumption_impact.py` | `AssumptionImpact` (6) + `IMPACT_READINESS_CAP` (an assumption never lifts readiness) + impact text |
| `strategy/engineering_assumption.py` | `is_factual(...)` + `derive_domain_assumptions(domain, convergence, revalidation_item, coverage_item, contradiction_item)` → assumptions (empty when factual) |
| `strategy/programme_assumption_register.py` | `build_programme_assumption_register(timeline, revalidation, coverage, contradiction, playbook)` → `ProgrammeAssumptionRegister`; per-domain assumptions + programme-level from Phase-24 boundaries; blocking/capping/narrowing/informational/conservative buckets |
| `strategy/programme_assumption_register_render.py` | `render_assumption_sections` / `render_assumption_text` — strings only, zero DB |

## SessionDB entry (read-only)

`SessionDB.build_programme_assumption_register(...)` returns `{"ok", "assumptions": <report
dict|None>, "assumption_count", "content_fingerprint"}`.

It reuses the shared **`_build_knowledge_chain`** (Phase-22 built **once**; Phase-23/24/25 derived
purely; records returned by the chain), then computes the Phase-26 re-validation, Phase-27 coverage
and Phase-29 contradiction **purely in memory**. It **never** calls the
Phase-23/24/25/26/27/29 SessionDB entry points. No N+1; renderer zero DB; no writes; DB
byte-identical; `user_version` stays 26.

## UI

`ui/engineering_assumption_vm.py` (pure vm) + `ui/engineering_assumption_panel.py`
(`EngineeringAssumptionPanel`, read-only) embedded in the **Development History** page beneath the
Phase-29 contradiction panel. States use **text tags** (`[REVIEW]`, `[BOUND]`) not colour alone. No
Apply / edit / schedule control exists. The heavy build runs **off the Qt thread** via the reused
`MechanismAnnotationWorker`; a stale worker result cannot replace a newer one (`_assumption_worker`
guard).

## Tests (58 assertions across 5 files + regression)

- `test_phase30_domain.py` (13) — the 16/8/6 enums; `is_factual`; each derivation rule; contradiction-
  side only when open-with-standing; every assumption caps.
- `test_phase30_golden.py` (10) — the mandated behaviours 1–10.
- `test_phase30_integration.py` (7) — Phase-22 built once; Phase-23/24/25/26/27/29 DB entries never
  called; query count constant (no N+1); renderer no DB; no writes / DB hash + counts + user_version
  unchanged; empty cheap; result shape.
- `test_phase30_safety.py` (13) — no forbidden imports / wall-clock / setup-gen / scheduling; no
  duplicate authority; facts ≠ assumptions; assumptions only cap; conservative bound labelled; no
  setup-value leak; `_setup_constants.py` unchanged; no-AI scan.
- `test_phase30_ui_construction.py` (12) — panel construct/empty/none/error-safe; no mutation
  controls; text-tag state distinction; no setup values; page embed + forwarder; prior panels
  coexist; stale-worker ignored; build runs off the UI thread.
- Regression: Phase 28/29 integration green.

## Runtime verification

DB byte-identical after repeated runs; content fingerprint identical across restart; `user_version`
26; no setup-value leak; output ASCII-clean.
