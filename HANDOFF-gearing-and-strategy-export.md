# Pit Crew `gt7-pitcrew/1.2` — gearing, RPM and strategy

**Status, 11 Aug 2026: requested, not built.**

This is a **change request against `EXPORT-CONTRACT.md`**, kept separate on purpose:
that document describes what the app actually emits today (`1.1`), and folding an
unbuilt schema into it would make a request read as a fact. **When the work lands and
a real 1.2 payload arrives, these sections move into the contract and this file is
deleted.**

Additive only. Nothing in 1.1 changes meaning.

---

## Why

Three questions the tune builder asks the driver to answer by hand, all of which are
already in the packets Pit Crew records and none of which reach the export:

1. **Is the gearbox in the car the gearbox on the sheet?**
2. **Does 2nd cover all three chicanes without an upshift?** — the constraint that
   outranks the final drive, and nothing verifies it.
3. **What is this car's real gearing constant K?** — one reading makes every future
   gearbox on the car exact instead of iterated.

Plus: the strategy model computes a plan, makes live calls and stores an immutable
revision chain, and **the export builder has never once passed `strategy=`**. So a
returned setup has no idea what the strategy was or whether it held.

## What was already there — recorded 11 Aug 2026

Checked against the working tree:

- **`gear`, `rpm` and `rev_limiter` are already captured per frame** in
  `pitcrew/telemetry/recorder.py`. The `rpm` field carries the comment *"captured for
  short-shift analysis; never exported."* No new capture is needed for any of this.
- **Gear ratios already round-trip both ways** — paste → Event screen →
  `SetupSheet.gears` → `setup.gears` in the export.
- **`GT7Packet.gear_ratios`** (eight floats, the ratios actually fitted) is decoded and
  read by nothing. This is the only new capture in the request.
- `strategies`, `race_runs` and `race_revisions` tables all exist and populate.
- `events.refuel_rate_lps`, `pit_loss_secs` and `mandatory_stops` are stored and
  exported nowhere.

---

## New: per-corner gear fields

Added to each object in `corners`:

| Field | Definition |
|---|---|
| `gearMin` | Lowest gear held in the corner window. **Modal across counted laps, not mean** — a mean gear of 2.6 is not a gear |
| `gearAtApex` | Gear at the minimum-speed point, same apex definition as `brakePointM` |
| `gearAtExit` | Gear at the window's end |
| `shiftsInCorner` | Mean gear changes inside the window. A fraction is meaningful here: 0.4 means he shifted on four laps in ten |
| `upshiftRpm` | Mean rpm at the first upshift after the apex. Null if none. **This is how short-shifting becomes visible** |

`shiftsInCorner` is the highest-value field in the request — it answers the two
gearbox constraints that currently go unverified at every circuit.

## New: `gearing` section

```json
"gearing": {
  "fittedRatios": [2.727, 1.925, 1.529, 1.288, 1.152, 1.062],
  "fittedFinalGear": 3.550,
  "ratioSource": "telemetry",
  "matchesSheet": true,
  "limiterRpm": 8800,
  "limiterRpmSource": "observed-at-rev-limiter",
  "maxSpeedKph": 312.4, "maxSpeedGear": 6, "maxSpeedRpm": 8790,
  "topGearReachedLimiter": true,
  "samples": 9,
  "gearingConstantK": 1178.2,
  "gearingConstantSource": "computed: observed speed x ratio x final gear, top gear, laps 3-9"
}
```

- **`matchesSheet`** catches "the sheet says one gearbox, the car has another" —
  otherwise invisible until a whole test session has been run on the wrong box.
- **`gearingConstantK`** = observed speed × that gear's ratio × final gear, in top gear
  at the limiter, with its sample count.
- **`limiterRpm` is null unless the `rev_limiter` flag actually fired.** Not the
  highest rpm observed.

### The tow constraint — permanent, not a v1.2 detail

**GT7's feed has no proximity, closing speed or opponent positions. A tow cannot be
detected.** The tune builder wants "top speed in clean air vs in a tow" and will not
get it. The export carries the observed maximum with its sample count; whether there
was a tow comes from the driver in `notes`.

Any future field named `towSpeedKph` is a fabrication by definition. The build
includes a test asserting no key matching `tow` exists in the payload.

## New: `strategy` wired up

Shape is unchanged from the contract's §9, plus mandatory provenance on every
assumption using `pitcrew/strategy/evidence.py`'s existing vocabulary —
`measured` / `declared` / `assumed` / `missing`.

Three additions that matter:

- **`assumptions.refuelRateLps` is required.** At the current event it is 1 L/s against
  a 2.5 default, and it is the number that decides the whole race. A plan exported
  without it is unreadable.
- **`callsMade` includes declined calls**, from `race_revisions.accepted`. A plan
  offered and refused is evidence about the model; dropping it makes the model look
  better than it is.
- **`wearMeasuredAtRaceMultiplier: false` must survive to the export.** Multiplier
  linearity remains assumed and never demonstrated.

Absent strategy → the section is **omitted**, not emitted as a skeleton of nulls.

## Unchanged, deliberately

- Fuel evidence as it stands is correct: `session.fuelUsedPerLapL` (median),
  per-lap `fuelStartL` / `fuelEndL` / `fuelMap`, `fuelCapacityL`. **`fuelMap` stays
  null unless the driver declares it** — GT7 does not broadcast it and inferring it
  would be a fabrication.
- The 23-key setup vocabulary. Individual ratios stay a separate `gears` array;
  `top` and `fg` stay in `values`.
- The import side does not check `format`, so paste blocks keep working across
  versions.

---

## The acceptance test

A recorded race session exports a payload from which these five are answerable without
asking the driver anything. **None of them are answerable from a 1.1 payload.**

1. Is the gearbox in the car the gearbox on the sheet?
2. Did 2nd cover all three chicanes without an upshift?
3. What is this car's real gearing constant?
4. What bound the stint — fuel or tyres?
5. What did the strategy engine say during the race, and was it right?
