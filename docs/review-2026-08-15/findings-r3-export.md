# Round 3, F3 — export payload enumerated field by field against contract 1.4

Method: contract read in full; five real files in `exports/` plus three payloads regenerated
from a read-only copy of `data\pitcrew.db` (events 1-3, all validating clean).

## THE VALIDATOR DOES BLOCK — verified
`to_json` (payload.py:443-450) calls `validate()` and raises `ExportRefused` before
`json.dumps`. Both callers gate on it: `controller._on_export` (1719-1731) returns before
`_write_export`; `prompts/context.py:324-334` sets `payload = None` on refusal.
**There is no path that writes an unvalidated payload.** This is the one place the export layer
is unambiguously right.

## NEW P1s

- **fuelCapacityL 0.0 wins over 100.0 and SILENTLY DISABLES the fuel-plausibility gate.**
  `_merged_session` (build.py:270) picks the first non-None, so a stored `0.0` beats a later
  `100.0`. Contract §5 makes 0 a REAL value meaning electric, so the payload asserts an electric
  car whose own `laps[]` burn 7.28 L a lap.
  Real DB event 3: session 13 has `fuel_capacity_l = 0.0` (first packet arrived before the car
  loaded); sessions 14-17 all have 100.0. Shipped artifact `pitcrew-20260813-222406.json` carries
  `"fuelCapacityL": 0.0` beside `laps[0].fuelStartL: 100.0` and `"fuelUsedPerLapL": 7.281`.
  **Knock-on chain:** `classify_exclusions(laps, 0.0)` → `fuel_implausible_laps`, whose
  `if fuel_capacity_l <= 0: return set()` guard **turns the whole 1.4 lap-validity check off for
  the event**, with nothing in the payload saying so. Same first-non-None rule in
  `prompts/context.py:348-351` and `strategy/evidence.py:92-96` ⇒ `RaceInputs.fuel_capacity_l =
  0.0`; `missing()` only reports the gap when None; `fuel_limited_laps` returns None on a falsy
  capacity ⇒ **a race plan is built with no fuel constraint at all, `bindingConstraint` can never
  be `fuel`**, and the Strategy screen shows "Fuel capacity 0 L" labelled MEASURED.

- **`wear.modelledStintLaps` is the LAST run's rate, unlabelled — export impact quantified.**
  Confirms A4 and puts a number on it. Regenerated Monza export (91 laps, 8 runs, 3 compounds):
  `byCompound.RS 0.1725` (→4 laps), `RM 0.07636` (→11), `RH 0.05118` (→16), last run 0.03154
  (→26). Payload emits **`"modelledStintLaps": 26`** with `"modelBasis": "0.85 / w, w from the
  driver's gauge at this multiplier"` — **no compound named.** A driver planning on 26 laps who
  fits Racing Softs runs **6.5x past the cliff.** Shipped export shows the same shape:
  `modelledStintLaps: 46` from the RM rate while RS reads 0.05767 (→14 laps).

- **A temperature-inferred fresh set promotes a one-reading rate to `confidence: "measured"`.**
  `RunWear.confidence` returns `measured` when `_has_delta or tyres_fresh is True`, and
  `tyres_fresh` falls back to `fresh_by_temperature()` — an app-side heuristic against
  `FRESH_TYRE_TEMP_C`. So a rate resting entirely on a temperature band the app chose is tagged
  `measured`, and `as_export` withholds `assumesFreshAtLap` because
  `method != METHOD_FRESH_AT_RUN_START`.
  Regenerated Monza: runs 3, 4, 5, 6 all carry `"confidence": "measured"` on
  `"method": "one gauge reading, over a set whose opening temperatures are those of a set as
  fitted"`, with no `assumesFreshAtLap`. Those four dominate `_model_confidence`, producing
  **`"modelConfidence": "measured"`** for a payload where four of six runs are anchored to a
  60-70 °C band, not to the driver. Contract §6.1/§8 make `measured` conditional on two readings
  or the driver's own declaration; nothing else.
  (Corroborates the standing note that `FRESH_TYRE_TEMP_C = 70.0` is fabricated.)

- **2π slip — found INDEPENDENTLY for the third time**, by a different route (median slip
  fl 6.2839, fr 6.2822, rl 6.5149, rr 6.5203 on 5,505 throttle frames above 50 km/h; 100.0% of
  frames exceed the 1.08 threshold on all four wheels).

## NEW P2s
- **`derived.steerRotationDeg` is a hard-coded 1080.0 contradicting `steerPeakDeg` by 3x.**
  Never assigned from anything — grep returns only the definition and the default.
  `steerPeakDeg` is degrees on a channel saturating at ±π, so full lock is **180°**. A reader
  given `steerPeakDeg: -67.47` with `steerRotationDeg: 1080` computes 12.5% of lock;
  `steerPeakNorm: -0.375` says 37.5%. The contract pairs the two fields precisely so degrees can
  be scaled, and this is the wrong scale.
- **`corners[].brakePointM` reports the PREVIOUS corner's braking for a corner never braked for.**
  `_brake_point_m` searches 500 m back and returns None only if NO frame in the window braked.
  Shipped export: T3 `brakePeakPct 2.8` (no braking in the corner) with `brakePointM 560.4`;
  T8 `2.4` with `445.9`. The distance can exceed the 500 m lookback because it is measured from
  the apex. Reads as "he starts braking 560 m before T3" at a corner he takes flat.
- **`wear.byTemp.trendCPerLap` is understated ~2x and fitted across every run, compound and
  tyre set, with no sample count.** Half-mean estimator divides by the FULL span while the two
  half-centroids are only half a span apart. Arithmetic check: 10 laps rising exactly 1.0 °C/lap
  → reports 0.56. Regenerated Monza fits one figure over 74 laps spanning 8 runs, 3 compounds,
  8 tyre sets. Contract §6.1: "Nothing may be fitted across a refuel."
- **`wear.byLapTime.estimatedFractionAtEnd`/`.phase` are the driver's last gauge reading from
  ANYWHERE in the session, published under `source: "lap-time-model"`.** Reachable whenever the
  longest run is not the last run with a reading. Both shipped exports happen to coincide, which
  is why it is invisible in the artifacts.
- **Per-corner means are taken over however many laps carried the channel, but published under
  ONE `samples` count of all laps.** `upshiftRpm` is clearest: `_first_upshift_rpm` returns None
  on laps with no upshift, so the mean is over only those that did. Shipped export T1:
  `"samples": 23`, `"shiftsInCorner": 0.09` (≈2 shifts across 23 laps), `"upshiftRpm": 7787.0` —
  **a two-lap figure the payload calls a 23-lap one**, and the contract asks the reader to
  compare it against `gearing.limiterRpm` to judge short-shifting.

## P3s
- `meta.carCategory` emits GT7's raw token (`GR3`, `GRN`) not the contract's `Gr.3` vocabulary.
  Real DB holds `GR3` on 15 sessions and `GRN` on 2. Not validated.
- Seven flag thresholds missing from `derived.thresholds` (matches G-series).
- `derived.bottomingRefSource` says "counted laps" but the reference is built from the
  DIAGNOSTIC set — counted PLUS incident laps. An off or a spin compresses the suspension below
  anything on a clean lap, **so an incident sets the floor every `bottoming` flag is judged
  against.** Regenerated Monza: incident laps 26, 74, 79 feed `bottomingRefMm`.
- **15 keys emitted that the contract does not define**, and `validate()` has no unknown-key
  check: `meta.practiceIntent/practiceMode/rehearsal`, `setup.purpose`,
  `runs[].tyresChangedAtStop`, `wear.byRun[].wearPerLapUnavailable`,
  `wear.byCompound[].wearPerLapUnavailable`, `wear.byLapTime.fuelNettedNote`,
  `wear.byLapTime.degradationUnavailable`, `derived.incidents`, `derived.thresholds.incident*`,
  `strategy.assumptions.mandatoryStops`, `strategy.raceLength.startHour`/`timeMultiplier`,
  `strategy.compoundProfiles[].paceBasis`. Several are useful and should be SPECIFIED rather than
  removed — the defect is that they ship undeclared.

## Sections audited CLEAN
- **§9 `gearing` — the cleanest section in the payload.** Every field present, correctly typed,
  correctly labelled, matching the contract field for field. No defects. **But the validator
  checks NONE of it.**
- §3 `setup`: only keys actually present are emitted; unentered omitted, never 0. `awd` correctly
  absent rather than null.
- §6 `laps[]`: integer ms, `fuelMap` null when unset never 0, `tyreTemp*` null when no frames.
- §6.1 `runs[]`: tri-state `tyresFresh` preserved, never inferred from the refuel; bare `false`
  refused without a source. Driver input verified genuine in the DB.
- `wear.byDriverGauge[]`, `byCorner`, `byRun[].degradation*`, `byLapTime` slope machinery,
  `byCompound` structure — all correct.
- `meta.compoundsRun` order preserved, never a vote. `meta.cornerModel` correctly declared.

## Contract fields the app NEVER emits
`derived.understeerIndexByCorner`, `derived.balanceDriftPerLap` (**no producer exists anywhere
in `pitcrew/`**), `setup.build.pp`, `session.lapsExcludedDetail[].note`,
`wear.byRun[].assumesFreshAtLap` on the observed-fresh path (suppressed by the P1),
`corners[].flags: "lockup"` (unreachable via the 2π P1).

## 37 CONTRACT CONSTRAINTS THE VALIDATOR DOES NOT ENFORCE — the highlights
The full list is in the agent output; the ones that matter:
- **`session` — NOTHING AT ALL.** No required keys, no `lapsCounted` cross-check against
  `laps[].valid`, no `bestLapMs ∈ {counted lap times}`. This is why SM3's rack/export divergence
  and the `fuelCapacityL: 0.0` P1 both sail through.
- **The ENTIRE `gearing` section** — no field, type, enum or consistency check.
  `matchesSheet: true` beside a contradictory `fittedFinalGear` was defect 1.4/10 and the
  validator still cannot see it.
- **§13's prohibitions: only `"tow"` is walked.** Nothing refuses an rpm SERIES, a GPS array,
  `oilTemp`, `waterTemp`, `boost`, `tyrePressure`, `caster`, `brakePressure`, or a high/low-speed
  damper split — the eight things CLAUDE.md §8 and §4.8 name as proof the logic was
  pattern-matched from another sim.
- `strategy.raceLength`: `finishAtS <= maxDurationS` — **the one invariant §10.0 exists to
  state** — is not checked. Nor is `stintLaps` summing to `plan.laps`.
- `wear.byRun[].method`/`.confidence` enums; `assumesFreshAtLap` required when the rate rests on
  an assumed fresh set; `runId` pointing at a run that exists; `stintsMeasured <= stints`;
  `byLapTime.samples >= 5`.
- `meta.carCategory` vocabulary; `multipliers` format; `lapsExcludedDetail[].reason`/`.source`
  enums; `runs[]` contiguity (only overlap is refused — a lap belonging to no run passes).
- `setup` and `rangeRecord` are validated at BUILD time in their own classes but **never
  re-checked on the payload**, so a section assembled by any other route ships unchecked.
- No unknown-key detection at any level.

## Context notes
- `session.greenLapRefMs` is `min` of the first 3 counted laps of the MERGED event, so with 8
  runs merged it is the first run's best, not a green reference for the run `byLapTime` is fitted
  on. Same root as G12. Low severity, filed as context.
- `wear.wearMeasuredAtRaceMultiplier` is **hard-coded `true`** — defaults True and neither real
  caller ever passes anything else; only tests do. Same shape as `pitLossSource`.
- `meta.compound.front`/`.rear` are both set from one value, so the contract's stated purpose
  ("keep both so a mismatch is visible as an input error") can never fire. Harmless; decorative.
- `session.lapsExcludedDetail[].reason: "in-lap"` is unreachable — `is_pit_lap` is 0 on all 132
  laps in the real DB, so a pitted lap can only surface as `incident`.
- `meta.gameVersion` emits `"1.7"` on event 3 where the row holds a truncated string; the app
  default is `"1.70"`. Two exports now disagree about the same update.
