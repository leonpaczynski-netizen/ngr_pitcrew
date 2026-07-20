# Engineering Brain — Program 2, Phase 36: Canonical Context & Context-Safe Knowledge Activation

Read-only, offline, deterministic, advisory-only. Part of the combined **Phases 36-38 Race-Engineer
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose

Layer 1 + Layer 2 of the activation. Name *exactly* which programme is being evaluated, then classify
the recorded evidence relative to that context so **no current-context conclusion is ever driven by
incompatible evidence** (the Phase 36 invariant).

## Authority ownership

| Module | Owns |
| --- | --- |
| `strategy/engineering_context_scope.py` | The canonical `EngineeringContextScope`, its fingerprint, completeness grading, and `relate_context`. |
| `strategy/contextual_knowledge_activation.py` | Per-record classification into the five evidence classes, the contamination guard. |
| `strategy/contextual_knowledge_activation_render.py` | Deterministic renderer (scope + classified evidence + guard). |

It **reuses** the Phase-23 `evaluate_transfer` authority for every transfer decision and **creates no
new** transfer/diagnosis/setup engine.

## Canonical context fields (Layer 1)

Identity (fingerprint-material): `driver, car, car_variant, track, layout_id, event_id, discipline
(base/qualifying/race/unknown), compound, compound_policy`. Regulation: `bop_state,
tuning_permitted (yes/no/unknown tri-state), power_restriction, weight_restriction`. Versions:
`gt7_version, rule_engine_version, data_schema_version`. Objective: `race_objective, tyre_multiplier,
fuel_multiplier`.

Missing context is **explicit**: a genuinely-unknown component is held distinct from any known value
by an internal `_UNKNOWN` sentinel in the identity line, so a known value and an unknown value are
different scopes and never merge. `completeness()` grades `complete / sufficient / partial /
insufficient` from the known core (`driver, car, track, layout_id, discipline, gt7_version`).

## Compatibility rules (`relate_context`)

`EXACT` requires the **full** identity (car+track+layout+driver+discipline+version+compound). Same car
**or** same driver alone is never EXACT. Other results: `same_programme_other_discipline`,
`same_car_other_track`, `same_driver_other_car`, `different_version`, `unrelated`, `unverifiable`.

## Transfer boundaries (Layer 2)

Each record is classified against the current scope:

- `EXACT_CONTEXT` — exact identity; priority evidence.
- `EXPLICITLY_TRANSFERABLE` — a different-but-compatible context that the Phase-23 authority licenses
  at level ≥ medium for the record's implicated engineering domains; carries lower confidence and the
  transfer authority's visible limitations.
- `REFERENCE_ONLY` — related but transfer is weak (very_low/low); informational, does not drive.
- `EXCLUDED` — unrelated, or a non-transferable domain (gearbox/track are `car_track_specific` /
  `context_bound` and never transfer across tracks); must not drive any recommendation.
- `UNVERIFIABLE` — not enough identity to classify.

So other-track **handling / vehicle-dynamics** evidence transfers (with limitations) while other-track
**gearbox / track-specific** evidence is excluded — a Daytona result cannot silently shape a Fuji
working window. Every included and excluded item carries a reason; the contamination guard lists all
excluded/reference items.

## Fingerprint & determinism

`context_fingerprint` = SHA-256 over the canonical identity line (semantic identity only). Runtime /
object / machine identity and accidental source-row order are excluded; a different driver, car, track,
layout or discipline can never collide. The activation fingerprint is over the scope fingerprint +
sorted `(record_key, classification, transfer_level)` + class counts — canonical class order, not row
order; shuffling the input rows yields an identical fingerprint.

## Query shape

Phase 36 performs **no** DB access itself — it consumes the records the shared `_build_knowledge_chain`
already read once. See the Phase 38 doc for the SessionDB entry.

## Safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; authors no setup value; decides nothing;
creates no experiment. **Invariant:** no current-context engineering conclusion may be driven by
incompatible evidence without an explicit transfer decision and a visible limitation.

## Known evidence limitations

The current session's track/layout must be supplied (via `session_identity`) for exact-context
classification; the Phase-22 programme knowledge rolls up across tracks, so track/layout/compound
identity is only present on the individual records.
