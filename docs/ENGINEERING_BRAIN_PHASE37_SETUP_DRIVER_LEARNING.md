# Engineering Brain — Program 2, Phase 37: Setup-Outcome, Working-Window & Driver Learning

Read-only, offline, deterministic, advisory-only. Part of the combined **Phases 36-38 Race-Engineer
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose

Layers 3-6. Turn the EXACT-context development history into evidence-backed learning: setup lineage &
outcomes, per-field working windows, driver-development state, and coaching priorities.

## Authority ownership

| Module | Layer | Owns |
| --- | --- | --- |
| `strategy/setup_outcome_learning.py` | 3 | Lineage interpretation, directional guidance, no-repeat guard, rollback, protected behaviour. |
| `strategy/setup_working_window.py` | 4 | Per-field working windows. |
| `strategy/driver_development_state.py` | 5 | Driver dimensions, trend, cause attribution. |
| `strategy/coaching_priority.py` | 6 | Falsifiable coaching priorities + gearing/drive-out. |

All four consume the **EXACT-context** `DevelopmentRecord` dicts (from the Phase-36 activation). They
create no new setup/diagnosis/experiment/driver-profile engine.

## Setup-lineage behaviour (Layer 3)

Ordered applied setups (by `recorded_at`, `outcome_id`, `record_key`). Per record: the applied delta
(`changes`), the outcome verdict (`improved / worsened / unchanged / inconclusive`), and — when
worsened — the rollback target (the last non-worsening applied state, else `baseline`). "Worse than the
previous setup" is authoritative regression evidence against the immediately preceding delta.

### Failed-direction no-repeat guard (invariant)

A worsened `(field, direction)` becomes `BLOCKED`. It **unblocks only** when a later exact-context
record repeats the same field+direction and improves with **equal or stronger** confidence. Canonical
Phase-3 `NEVER_MOVE_DIRECTION` / `KNOWN_UNSTABLE` protected-knowledge is folded into the blocked set.
**A failed setup experiment therefore alters future advice; the same failed direction is never
re-recommended without stronger new evidence.**

## Working-window behaviour (Layer 4)

Per supported field: `current_value`, `proven_good_values` (a **union**, never an average),
`proven_context`, `regression_values` (to avoid), `window_min/max`, `confidence`, `evidence_count`,
`independent_count`, evidence-observed `interactions` (fields co-changed in the same record),
`transfer_limitation`, and a status: `PROTECT` (converged proven window from ≥2 independent records at
≥medium confidence), `EXPLORE` (proven but unconverged), `AVOID` (a value/direction associated with a
regression or a blocked direction), or `INSUFFICIENT`. Windows are exact-context + single-discipline,
so **Qualifying and Race windows stay separate**. A mature converged window is not overturned by one
noisy record.

## Driver-development model (Layer 5)

Repeated per-corner residuals map to canonical driving dimensions (threshold braking, trail-brake
release, turn-in/front-load, minimum-corner speed, rear stability, exit wheelspin, drive-out, gear
selection, apex connection, throttle timing/progression, steering correction, use of track width).
Each dimension is graded `strength / development_area / emerging / insufficient` by aggregate score +
**trend** — the latest session is never assumed better and a single good session does not promote a
development area to a strength. Cause **attribution**: persists across ≥2 materially different setups
=> `likely_technique` (or `track_interaction` when bound to one corner); appeared under one setup and
not improving => `likely_setup`; improving under a constant setup => `likely_technique`. A strong setup
is not blamed for driver inconsistency without evidence, and a repeated car behaviour is not dismissed
as driver error.

## Corner, gearing & drive-out coaching (Layer 6)

A small set of falsifiable coaching priorities is chosen from the **driver-attributable / interaction**
dimensions only (setup-only problems are setup fixes, not coaching). Each carries: affected
corner/phase, current vs desired behaviour, why it matters, evidence confidence, ONE technique focus, a
measurable success criterion, the confirming telemetry, a falsifier, and whether the setup must be held
constant during the test. Exit / traction / gear priorities include a gearing & drive-out assessment
(rotation, throttle control, wheelspin management, acceleration, speed onto the next straight, fuel).
A persistent per-corner issue remains a priority across sessions until the evidence shows it resolved.

## Fingerprints & determinism

Every product carries a semantic `content_fingerprint` over its material fields, in canonical order,
excluding runtime/object identity and accidental row order. Inputs are re-sorted internally, so
shuffling the raw records yields identical output. One-off noisy evidence cannot override a mature
proven window without a recorded regression.

## Safety invariants

Pure (no Qt/DB/network/AI/clock/random); never raises; authors no setup value; applies nothing; creates
no experiment. **Invariant:** a failed setup experiment must alter future engineering advice.
