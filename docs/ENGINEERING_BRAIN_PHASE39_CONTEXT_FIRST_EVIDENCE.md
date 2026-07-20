# Engineering Brain — Program 2, Phase 39: Context-First Evidence Pipeline & Validation

Read-only, offline, deterministic, advisory-only. Part of the **Phases 39–41 Closed-Loop Development**
slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose & where context filtering occurs

The Phase-22 chain aggregates a compatibility group of `(car, discipline, gt7_version, driver)` that
**excludes track/layout/compound** (see the pre-phase audit). Phase 39 introduces a **classify-before-
aggregate** pipeline so exact-context conclusions are never contaminated by incompatible evidence.

`strategy/context_scoped_chain.py::build_context_scoped_chain(scope, raw_records)`:

1. classifies **every** raw record against the current `EngineeringContextScope` via the Phase-36
   activation **before** any aggregate;
2. buckets into exact / transferable / reference-only / excluded / unverifiable;
3. builds the exact-context summary (per-domain evidence count, independent sessions, improvements,
   regressions, convergence) from **exact records only**;
4. keeps a labelled transferable overlay (never counted as independent exact evidence);
5. retains full provenance (every inclusion/exclusion reason);
6. exposes `exact_record_keys` for the downstream Phase 40/41 authorities.

**Proof it occurs before aggregation:** the exact-context summary and `exact_content_fingerprint` are
pure functions of the exact record set + scope identity. `exact_content_fingerprint` is computed with
**zero** reference to transferable/excluded records or their counts. Metamorphic test: adding 100
incompatible Daytona records leaves `exact_content_fingerprint` byte-identical (only the full
fingerprint / history counts change). A confounded/insufficient run is visible but does **not**
strengthen convergence or independence (an invalid run cannot move a proven window).

## Exact vs transferable boundary

Transferable evidence enters ONLY via the Phase-23 `evaluate_transfer` authority (from the Phase-36
activation). Other-track handling/vehicle-dynamics evidence transfers (lower confidence + visible
limitations) into the overlay; other-track gearbox/track-specific evidence is excluded. The overlay is
never merged into exact independence or convergence.

## Event-condition equivalence

`strategy/context_equivalence.py::assess_context_equivalence(a, b)` compares two contexts along visible,
fingerprinted dimensions: identity-critical (driver/car/variant/discipline/gt7 → `INCOMPATIBLE` if
different), track-critical (track/layout/direction → `TRANSFER_ONLY`), event-condition
(compound/BoP/tuning/power/weight/tyre+fuel multipliers/objective/weather/grip → `MATERIALLY_DIFFERENT`
if a *known* value differs), and administrative `event_id`. A different event ID **alone** →
`EQUIVALENT_CONDITIONS` (a different instance, engineering-equivalent — evidence eligible), never
incompatible. "Both known differ" semantics: an unknown value never counts as a difference.

## Bundle vs field attribution (Audit B)

`strategy/regression_attribution.py`: a multi-field worsened delta → `BUNDLE_REGRESSION_CONFIRMED`
(blocked) with each field only `FIELD_DIRECTION_SUSPECT`. A field is `FIELD_DIRECTION_CONFIRMED` only
via a single-field controlled test, independent repeated bundles sharing that field, or valid reversal
evidence. A coupled bundle repeating across independent sessions → `INTERACTION_SUSPECTED`. Correlation
is never silently promoted to field-level causation.

## Setup-independence rules (Audit C)

`strategy/setup_independence.py`: `assess_setup_independence(a, b, behaviour)` maps fields → mechanism
domains → the behaviour's relevant domains. Setups differing only in an irrelevant field are
`IRRELEVANT_VARIATION` (not independent). `attribute_issue` yields `SETUP_LIKELY` /
`DRIVER_TECHNIQUE_LIKELY` / `TRACK_OR_CAR_CHARACTERISTIC` / `COMBINED_DRIVER_SETUP` /
`INTERACTION_UNRESOLVED` / `INSUFFICIENT_EVIDENCE`. Persistence across non-independent setups never
yields driver-technique.

## Production-history validation

`strategy/production_history_validation.py::validate_production_history(scope, records)` is read-only
(`performed_repair: False`, no migration). It reports raw/exact/transferable/reference/excluded/
unverifiable counts, missing context fields, orphan setup references, broken lineage, missing applied/
experiment/outcome links, contradictory outcomes, ambiguous multi-field regressions, thin fields,
coaching dimensions lacking telemetry, and unsafe attribution.

## Read-only SessionDB entries

`build_context_scoped_evidence_report`, `build_production_history_validation_report` — each resolves the
context once, reuses the shared chain's single bounded evidence read, writes nothing.

## Safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; no setup values; no repair. **Invariant:** no
current-context conclusion is driven by incompatible evidence; incompatible evidence cannot alter the
exact-context fingerprint.
