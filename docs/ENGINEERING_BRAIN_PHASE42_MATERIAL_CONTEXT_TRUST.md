# Engineering Brain — Program 2, Phase 42: Material Context Trust & Legacy Evidence

Read-only, offline, deterministic, advisory-only. Part of the **Phases 42–44 Assisted Runtime
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Context-source audit (canonical ownership of context fields)

| Field | Canonical source | Historical availability |
| --- | --- | --- |
| driver | user_profile / applied setup / dev-record context | KNOWN (in record context) |
| car (+ variant) | `cars` table / garage / applied setup | KNOWN (car); variant often unknown |
| track / layout | `events.track` / track authority / record context | KNOWN (track); layout in record context |
| event identity | `events.name` / id | KNOWN for current; historical records have none |
| setup discipline | applied-setup purpose / record context | KNOWN (record context) |
| tyre compound | applied setup / record context | KNOWN (record context) |
| compound policy | `events.avail_tyres` / `events.req_tyres` | current only |
| BoP | `events.bop` | **current only** — not on dev records |
| tuning-permitted | `events.tuning` / `events.allowed_tuning` | **current only** |
| power / weight restriction | `cars.power_hp` / `cars.weight_kg` / event | **current only** |
| tyre multiplier | `events.tyre_wear` | **current only** |
| fuel multiplier | `events.fuel_mult` | **current only** |
| refuel rate | `events.refuel_rate_lps` | **current only** |
| race duration / laps | `events.laps` / `events.duration_mins` / `events.race_type` | **current only** |
| weather / grip | `events.weather` / `events.damage` | **current only** |
| GT7 version | applied setup / record context | KNOWN (record context) |
| rule-engine version | `strategy/_setup_constants.RULE_ENGINE_VERSION` | KNOWN (constant) |
| applied setup identity | canonical applied-setup state | KNOWN for current |
| setup snapshot fingerprint | applied-setup `setup_hash` | KNOWN for current |
| session purpose | applied setup / session | KNOWN for current |
| telemetry / data schema version | `DB_VERSION` / packet version | KNOWN (constant) |

**Finding.** The **current** event's material context is fully available canonically (the `events`
table + `cars` + applied-setup). The **historical** `engineering_development_records` carry only the
Phase-8 `MemoryContextKey` (driver/car/track/layout/discipline/gt7/compound) — the event-condition
material fields (BoP, tuning, multipliers, restrictions, refuel, duration, weather) were **never**
persisted with a record. Per the doctrine, those legacy fields must remain **unknown**, not fabricated.

## Persistence decision — no migration in this slice

Preference order was: (1) reference existing canonical event/car/track/applied-setup records; (2) an
immutable semantic context snapshot/fingerprint associated with the session/experiment; (3) no
duplicated mutable truth. The **current** material context is already reachable canonically (option 1),
and a deterministic **semantic context snapshot fingerprint** is computed purely from those referenced
values (option 2) without persisting a copy. Historical records legitimately lack material fields, and
the doctrine requires leaving them unknown. Therefore **no additive schema migration is justified in
this slice** — `DB_VERSION` stays **26**. Persisting the material-context snapshot on *new* sessions
(so future records are exact-eligible for multiplier/BoP-dependent conclusions) is a documented,
deferred candidate for a future additive migration; it is not needed to make the loop trustworthy now.

## Context evidence states (per field)

`KNOWN_MATCH`, `KNOWN_DIFFERENT`, `UNKNOWN_CURRENT`, `UNKNOWN_HISTORICAL`, `UNKNOWN_BOTH`,
`NOT_APPLICABLE`, `INFERRED_WITH_LIMITATIONS`. Doctrine: **unknown never proves a difference, and
unknown never proves exact equivalence.** A field is `KNOWN_MATCH` only when both sides are known and
equal.

## Overall context trust classification

`EXACT_VERIFIED`, `EQUIVALENT_VERIFIED`, `PARTIAL_CONTEXT`, `TRANSFER_ONLY`, `REFERENCE_ONLY`,
`INCOMPATIBLE`, `UNVERIFIABLE`. Evidence enters exact-context maturity / convergence / working windows /
promotion / confirmed direction / best-known selection **only** when all fields required by that
conclusion's domain are `KNOWN_MATCH`. Any required field unknown → capped to `PARTIAL_CONTEXT`
(never exact). A different event id **alone** with all material conditions matching → `EQUIVALENT_VERIFIED`.

## Domain → required-context map (visible)

- **setup_working_windows** — driver, car(+variant), track/layout, discipline, tuning state, material
  restrictions, gt7_version, applied-setup identity.
- **tyre_degradation** — car, track/layout, compound, tyre_multiplier, stint conditions, discipline.
- **fuel_use** — car, track/layout, fuel_multiplier, (fuel map), race conditions.
- **gearing / aero** — car, track/layout, BoP, power/weight restriction, discipline.
- **driver_technique** — driver, car, track, corner (transfer permitted across some event conditions,
  but retains track/corner/car limits).
- **vehicle_dynamics** — transferable via the Phase-23 authority; never exact merely because the
  mechanism is general.

Every trust decision lists **which missing fields** limited confidence.

## Legacy evidence handling

Legacy records stay **visible** and may be exact (when enough is genuinely known), transferable,
reference-only, partial or unverifiable. They are never discarded for missing new fields and never
upgraded by assumption.

## Outputs & fingerprint

`strategy/material_context.py`: `build_material_context_trust(current, evidence, domain)` →
per-field trust, overall trust, domain eligibility, limitation explanation, semantic context snapshot +
`context_trust_fingerprint` (over required fields, per-field trust, overall trust, snapshot identity —
excludes object/machine identity, paths, wall-clock, row order). `strategy/material_context_render.py`
renders it for UI. Deterministic; restart/shuffle-stable; unknown cannot become known by reordering.
