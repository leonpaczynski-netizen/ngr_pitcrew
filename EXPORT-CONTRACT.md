# Pit Crew export contract — `gt7-pitcrew/1.1`

**What this is.** The exact payload Pit Crew emits after a session. The driver copies
it and pastes it into the **Pit Crew data** box on the Driver Feedback tab of the GT7
Race Engineering HTML tool. That tool does **not parse it** — it wraps the blob
verbatim in a fenced code block inside a prompt, together with the driver's own
report, and sends it to the race-engineering knowledge base for diagnosis.

Two consequences, and they drive every decision below:

1. **The consumer is a reader, not a parser.** Malformed JSON will not throw. It will
   be misread. Self-validate before export.
2. **It shares a context window with the driver's report.** Every field costs
   attention that would otherwise go to what the driver felt. Export what changes a
   setup decision and nothing else.

Supersedes `gt7-pitcrew/1.0`. Changes and their justification are in §14.

---

## 1. Envelope

One JSON object. Every top-level section is optional except `meta` — emit what Pit
Crew actually has and omit the rest. An omitted section reads as "not built yet"; a
section full of nulls reads as "built but nothing measured." Both are honest. A
section full of zeros is not.

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta":        { },
  "setup":       { },
  "rangeRecord": { },
  "session":     { },
  "laps":        [ ],
  "corners":     [ ],
  "wear":        { },
  "strategy":    { },
  "derived":     { },
  "notes":       ""
}
```

---

## 2. `meta` — required

```json
"meta": {
  "car": "Porsche 911 RSR (991) '17",
  "carCategory": "Gr.3",
  "circuit": "Fuji Speedway (Full)",
  "gameVersion": "1.70",
  "date": "2026-08-11",
  "sessionType": "practice",
  "compound": { "front": "Racing Medium", "rear": "Racing Medium" },
  "assists": { "abs": "Weak", "tcs": 1, "countersteer": false },
  "multipliers": { "tyreWear": "4x", "fuel": "2x" },
  "packet": "C",
  "cornerModel": { "source": "track-map", "id": "fuji-full", "version": 3 },
  "appVersion": "pitcrew 2.0.1"
}
```

| Field | Type | Notes |
|---|---|---|
| `car` | string | Full GT7 name including year, exactly as the game writes it |
| `carCategory` | string | `Gr.1`…`Gr.4`, `Gr.B`, `N100`…`N1000`, or `null` |
| `circuit` | string | Full GT7 name including layout variant |
| `gameVersion` | string | e.g. `"1.70"` |
| `date` | string | `YYYY-MM-DD` |
| `sessionType` | enum | `practice` \| `quali` \| `tt` \| `race` — must match the Driver Feedback tab so the two halves line up |
| `compound.front/.rear` | string | Full compound name. GT7 cannot run split compounds, so these are normally equal; keep both fields so a mismatch is visible as an input error |
| `assists.abs` | enum | `Off` \| `Weak` \| `Default` |
| `assists.tcs` | int 0–5 | |
| `assists.countersteer` | bool | |
| `multipliers.tyreWear/.fuel` | string | `"Off"` or `"Nx"`. String, not number, so `Off` is representable |
| **`packet`** | enum | `A` \| `B` \| `~` \| `C`. **Required.** Declares which channels were physically available. Without it a null is ambiguous between "not captured" and "not offered by this packet format" |
| **`cornerModel`** | object | `source` ∈ `track-map` \| `auto-segment`. `id` and `version` identify the definition used, so corner IDs are comparable across sessions. Required if `corners` is present |
| `appVersion` | string | So a change in the detector does not read as a change in the car |

---

## 3. `setup` — the sheet as run

**The highest-value section, and the cheapest: it is pure app state, no telemetry.**
It removes all ambiguity about which version of a sheet produced these symptoms.
Keys are the **shared vocabulary** (§4) — the same keys the consuming tool uses for
its per-car range library, so ranges round-trip with no translation.

```json
"setup": {
  "sheetName": "Fuji race v2",
  "values": {
    "rh_f": 62,   "rh_r": 70,
    "nf_f": 3.42, "nf_r": 3.68,
    "arb_f": 6,   "arb_r": 4,
    "dc_f": 28,   "dc_r": 30,
    "de_f": 40,   "de_r": 38,
    "cam_f": 1.2, "cam_r": 1.2,
    "toe_f": 0.00, "toe_r": 0.08,
    "lsd_i": 5, "lsd_a": 15, "lsd_b": 25,
    "awd": null,
    "df_f": 320, "df_r": 640,
    "bb": -1,
    "top": 300, "fg": 3.720
  },
  "gears": [3.10, 2.28, 1.79, 1.46, 1.22, 1.04],
  "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 0, "ballastPosition": 0 },
  "build": { "bhp": 525, "weightKg": 1300, "pp": 730.12 },
  "driverChanges": [
    { "fromLap": 5, "key": "arb_r", "from": 4, "to": 3 },
    { "fromLap": 6, "key": "bb", "from": -1, "to": -2 }
  ]
}
```

- **`values`** — absolute values as entered in GT7. Signs explicit: toe `+` is in,
  `−` is out; brake balance `−` is front bias, `+` is rear, expressed as a **delta
  from the car's factory bias**, not an absolute percentage.
- **`gears`** — 1st…nth, in order. Separate from `values` because it is an array.
- **`driverChanges`** — structured, not free text. Mid-session changes are exactly
  the thing that invalidates a corner aggregate, so they need to be machine-legible.
  Anything not expressible as a key change goes in `notes`.

## 4. `rangeRecord` — the car's slider limits

Read off the car's own settings screen, once per car, never re-entered. This is worth
more than the setup values themselves, because it makes every returned recommendation
enterable without clamping.

```json
"rangeRecord": {
  "car": "Porsche 911 RSR (991) '17",
  "measuredDate": "2026-08-11",
  "gameVersion": "1.70",
  "verified": true,
  "r": {
    "rh_f": [55, 80],  "rh_r": [60, 90],
    "nf_f": [3, 5],    "nf_r": [3, 5],
    "arb_f": [1, 10],  "arb_r": [1, 10],
    "dc_f": [20, 40],  "dc_r": [20, 40],
    "de_f": [30, 50],  "de_r": [30, 50],
    "cam_f": [0, 6],   "cam_r": [0, 6],
    "toe_f": [-1, 1],  "toe_r": [-1, 1],
    "lsd_i": [5, 60],  "lsd_a": [5, 60], "lsd_b": [5, 60],
    "df_f": [350, 450], "df_r": [500, 700],
    "bb": [-5, 5],     "top": [200, 800], "fg": [2, 5]
  }
}
```

`verified: true` means read off the screen. `false` or absent means estimated —
say so, because the difference determines whether the returned sheet is enterable.
Emit `rangeRecord` on **every** export for a car whose ranges are known; it is a few
lines and it keeps the register in sync automatically.

---

## 5. `session` — run-level totals

```json
"session": {
  "lapsRun": 12,
  "lapsCounted": 9,
  "lapsExcluded": [1, 2, 11],
  "fuelUsedPerLapL": 3.42,
  "fuelCapacityL": 100,
  "bestLapMs": 93912,
  "medianLapMs": 94480,
  "lapTimeStdDevMs": 610,
  "greenLapRefMs": 93912
}
```

- `lapsCounted` excludes out-laps, in-laps, laps with an off, and traffic-compromised
  laps. `lapsExcluded` lists which, and `notes` says why.
- **Median, not mean.** One bad lap should not move the number.
- `greenLapRefMs` — the fresh-tyre reference lap the degradation model is measured
  against. Needed to interpret `wear.byLapTime`.
- `fuelCapacityL` is 100 for almost every car, 5 for karts, **0 for electric**. Zero
  is a real value.
- Track temperature is **not exposed by GT7**. There is no field for it. Do not
  invent a proxy.

## 6. `laps` — one object per counted lap

```json
"laps": [
  {
    "lap": 3,
    "timeMs": 93912,
    "valid": true,
    "fuelStartL": 92.1,
    "fuelEndL": 88.7,
    "fuelMap": 1,
    "tyreTempMeanC": { "fl": 84, "fr": 79, "rl": 81, "rr": 82 },
    "tyreTempMaxC":  { "fl": 97, "fr": 88, "rl": 86, "rr": 89 },
    "offTrackCount": 0
  }
]
```

Export tyre temperature **mean and max** per corner per lap. The mean gives the
working range; the max shows what is being abused. Tyre temperature is the one
channel GT7 gives that maps directly onto load distribution, and it is the strongest
available evidence for a front-left overload pattern.

---

## 7. `corners` — the section that actually changes setups

Aggregated across counted laps, one object per corner. **If only one telemetry
section gets built, build this one.**

```json
"corners": [
  {
    "id": "T1",
    "name": "Turn 1",
    "samples": 9,
    "entrySpeedKph": 268,
    "minSpeedKph": 96,
    "exitSpeedKph": 142,
    "brakePeakPct": 97,
    "brakePointM": 118,
    "trailBrakeMs": 940,
    "steerPeakDeg": 128,
    "steerPeakNorm": 0.34,
    "throttleOnPct": 34,
    "timeLossVsBestMs": 210,
    "consistencyMs": 180,
    "suspHeightMinMm": { "fl": 34, "fr": 36, "rl": 41, "rr": 42 },
    "surfaceMix": { "T": 0.94, "C": 0.06 },
    "flags": ["countersteer", "trail-brake-instability"]
  }
]
```

| Field | Definition |
|---|---|
| `id` / `name` | From `meta.cornerModel`. Stable across sessions if `source` is `track-map` |
| `samples` | Counted laps contributing. **Required on every corner object** |
| `brakePointM` | Metres before the **apex**, where apex is the minimum-speed point inside the corner window. Requires cumulative lap distance — state the definition in `derived.thresholds.apexDefinition` |
| `trailBrakeMs` | Time with brake > 5% while steering exceeds 15% of lock. This driver trail-brakes deep by design; if it collapses at one corner that is a rear-stability finding, not a driving one |
| `steerPeakDeg` | Degrees. The feed gives radians — converted in the app. Say which channel in `derived.steerSource` |
| `steerPeakNorm` | Peak steering as a fraction of full lock, −1…1. **Portable across rotation settings; prefer this when comparing sessions** |
| `throttleOnPct` | Percentage through the corner where throttle first exceeds 10% |
| `consistencyMs` | Spread of this corner's time across counted laps. **High spread with a normal average is the signature of a car the driver cannot trust, and it never shows up in a lap time** |
| `suspHeightMinMm` | Minimum **absolute** suspension height reached, per wheel. **Not travel remaining** — see §14. Interpret against `derived.bottomingRefMm` |
| `surfaceMix` | Fraction of samples per surface character: `T` tarmac, `C` kerb, `D` dirt, `G` grass, `S` sand, `s` snow. Packet `~`/`C` only |

### 7.1 `flags` — controlled vocabulary

| Flag | Detection |
|---|---|
| `bottoming` | suspension height within the bottoming reference band for > 50 ms |
| `countersteer` | steering sign reversal > 10° within 300 ms |
| `wheelspin` | driven-wheel surface speed exceeds vehicle speed by > 8% under throttle |
| `lockup` | wheel surface speed below vehicle speed by > 15% under brake |
| `trail-brake-instability` | countersteer inside the trail-brake window |
| `understeer-mid` | steering angle rising while yaw rate flat or falling |
| `off-track` | any wheel on a surface other than `T` or `C` |
| `kerb-strike` | suspension height step change > 20 mm in < 100 ms |

**Thresholds are the app's, not the game's.** Restate them in `derived.thresholds` on
every export, so that retuning a detector does not read as a change in the car.

---

## 8. `wear` — modelled, never measured

**GT7 exposes no tyre wear channel in any packet format.** This section exists to
make that explicit rather than to hide it. Every entry carries its source.

```json
"wear": {
  "channelAvailable": false,
  "byDriverGauge": [
    { "lap": 6,  "front": 0.55, "rear": 0.42, "source": "driver-gauge" },
    { "lap": 11, "front": 0.88, "rear": 0.71, "source": "driver-gauge" }
  ],
  "byLapTime": {
    "refLapMs": 93912,
    "degradationMsPerLap": 118,
    "phase": "linear",
    "estimatedFractionAtEnd": 0.74,
    "source": "lap-time-model",
    "confidence": "low"
  },
  "byTemp": {
    "frontRearAsymmetryC": 5.5,
    "trendCPerLap": 1.2,
    "source": "tyre-temp-trend",
    "confidence": "low"
  },
  "modelledStintLaps": 11,
  "modelBasis": "0.85 / w, w measured in-house at this multiplier",
  "modelConfidence": "measured"
}
```

- `byDriverGauge` is the most reliable input and the only one anchored to the game's
  own number. Fraction **consumed**, 0–1.
- `phase` ∈ `flat` (0–50%) \| `linear` (50–90%) \| `cliff` (>90%) — GT7 degradation is
  piecewise. Do not report a linear rate without saying which phase it was fitted in.
- `modelConfidence` ∈ `measured` \| `assumed` \| `converted`. **`converted` means the
  stint was calibrated at a different multiplier and scaled** — multiplier linearity
  is assumed, never demonstrated, so this value must never be presented as measured.

## 9. `strategy` — the plan and its assumptions

Present only for `sessionType: "race"`, or for a practice session run explicitly to
calibrate strategy. Its purpose is to make the app's own reasoning auditable.

```json
"strategy": {
  "plan": { "stops": 1, "stintLaps": [11, 9], "compounds": ["RS", "RM"], "pitLap": 11 },
  "bindingConstraint": "fuel",
  "assumptions": {
    "pitLossS": 19.5,
    "pitLossSource": "measured-this-track",
    "fuelPerLapL": 3.42,
    "fuelWeightSPerLPerLap": 0.003,
    "fuelWeightSource": "derived-not-measured",
    "compoundDeltaSPerLap": null
  },
  "callsMade": [
    { "lap": 4,  "call": "Map 3 down the back straight",     "reason": "1.2 laps short on fuel", "confidence": "high" },
    { "lap": 9,  "call": "Brake balance one click rearward", "reason": "front temps +6C over rear", "confidence": "medium" }
  ],
  "outcome": "Stopped lap 11. Fuel to the diamond +1 lap. Tyres had 2 laps left — stint was fuel-limited, not tyre-limited."
}
```

`bindingConstraint` ∈ `tyre` \| `fuel` \| `regulation` \| `unknown`. Knowing which
one bound the stint is the single most useful strategy output, because it decides
whether the next setup should chase durability or pace.

`callsMade` exists so live advice can be checked against what actually happened.
An app that gives calls and never records them cannot be improved.

## 10. `derived` and `notes`

```json
"derived": {
  "thresholds": {
    "wheelspinPct": 8,
    "lockupPct": 15,
    "countersteerDeg": 10,
    "trailBrakeSteerPct": 15,
    "kerbStrikeMm": 20,
    "apexDefinition": "minimum speed point within the corner window"
  },
  "steerSource": "wheelRotation",
  "steerRotationDeg": 1080,
  "bottomingRefMm": { "fl": 31, "fr": 31, "rl": 38, "rr": 38 },
  "bottomingRefSource": "steady-state minimum observed, laps 3-9",
  "understeerIndexByCorner": { "T1": 0.12, "T3": 0.31 },
  "balanceDriftPerLap": "+0.4 understeer index over 9 laps"
},
"notes": "Laps 1, 2 and 11 excluded - out-lap, traffic, in-lap. Rear ARB changed lap 5, so corner aggregates span two configurations; T1 and T3 recomputed on laps 5-10 only."
```

`notes` is free text and is read literally. Use it for anything that qualifies the
numbers above — it is cheaper to explain an exclusion than to have a setup built on a
misread aggregate.

---

## 11. Units — fixed, no inference from magnitude

| Quantity | Unit | Note |
|---|---|---|
| Speed | km/h | Feed is m/s — convert once, in the app |
| Lap and sector time | milliseconds, integer | Never a formatted string in a numeric field |
| Distance | metres | |
| Suspension and body height | millimetres, **absolute height** | Feed is metres. Not travel remaining |
| Temperature | °C | |
| Fuel | litres | |
| Throttle / brake | percent, 0–100 | Feed is 0–255 — convert in the app |
| Steering | degrees, and normalised −1…1 | Feed is radians. State rotation setting |
| Angles (camber, toe) | degrees, signed | Toe `+` in, `−` out |
| Brake balance | integer −5…+5 | `−` front, `+` rear; a delta from factory bias |
| Wear fractions | 0–1, consumed | Not "remaining" |

---

## 12. What NOT to export

Raw 60 Hz traces · GPS position arrays · engine RPM series · **oil and water
temperature** (pinned at ~110 °C and ~85 °C — they carry no information) · boost ·
replay-derived data · anything about tyre pressure, caster, brake pressure, or
high/low-speed damper splits (**none of these exist in GT7**).

None of it changes a setup decision, and all of it displaces the driver's report.

---

## 13. Markdown fallback

If JSON is impractical, the same content as markdown parses less cleanly but is
acceptable. Keep the headings identical to the JSON keys — `## meta`, `## setup`,
`## rangeRecord`, `## session`, `## laps`, `## corners`, `## wear`, `## strategy`,
`## derived`, `## notes` — one table per section. Do not invent a different layout;
the value is in the consistency, not the syntax.

---

## 14. Changes from `gt7-pitcrew/1.0`, and why

Every change below exists because the v1.0 field could not be produced honestly from
what GT7 actually emits, or because the app's scope grew to cover strategy.

| # | Change | Reason |
|---|---|---|
| 1 | `suspMinTravelMm` → **`suspHeightMinMm`** + `derived.bottomingRefMm` | The feed gives **absolute suspension height in metres**, not travel remaining. "Zero means bottomed" was not measurable. Bottoming is now explicitly inferred against a stated reference |
| 2 | Added **`meta.packet`** | Four packet formats (A/B/~/C) expose different channels. Without knowing which was captured, a null is ambiguous between "not measured" and "not available" — which violates the missing-is-null rule at its root |
| 3 | Added **`meta.cornerModel`** | GT7 emits **no track ID**. Corner identity comes from the app, so it must be declared, versioned, and comparable across sessions. v1.0 assumed corner IDs were self-evident |
| 4 | `steerPeakDeg` gains **`steerPeakNorm`**, `derived.steerSource`, `steerRotationDeg` | The feed gives **radians**, and two different channels (`wheelRotation` = the wheel, `wheelSteeringAngle` = the road wheels). Degrees alone are not portable across rotation settings |
| 5 | `brakePointM` gains **`derived.thresholds.apexDefinition`** | "Metres before the apex" needs an apex definition and a lap-distance model, neither of which the game supplies |
| 6 | `offTrack` → **`surfaceMix`** | Surface type is a character per wheel (`T`/`C`/`D`/`G`/`S`/`s`), not a boolean. Kerb contact and a grass excursion are different findings |
| 7 | **New `wear` section** | v1.0 had none, and **GT7 exposes no tyre wear channel at all**. Since the app now computes strategy, wear must be carried explicitly with its source and confidence, or it will be read as measured |
| 8 | **New `strategy` section** | The rebuild adds race strategy and live calls. Recording the plan, its assumptions and the calls made is what makes the advice auditable |
| 9 | **New `rangeRecord` section** | The app stores slider ranges. Exporting them in the consuming tool's own key vocabulary means measured ranges reach the register with no re-entry |
| 10 | `setup` re-keyed to the **shared vocabulary** (`rh_f`, `nf_f`, `arb_f`, …) | The consuming tool's per-car range library already uses these keys. Matching them removes a translation step and a class of silent mismatches |
| 11 | `setup.driverChanges` free text → **structured array** | Mid-session changes invalidate corner aggregates. That has to be machine-legible, not prose |
| 12 | `session.trackTempProxy` **removed** | GT7 does not expose track temperature and no honest proxy exists. A null field invites someone to fill it |
| 13 | `session` gains `lapsExcluded`, `greenLapRefMs` | Exclusions were prose-only in v1.0. The green reference lap is required to interpret any degradation figure |

### 14.1 Kept unchanged, deliberately

- **The driver report is primary; this is corroboration.** Nothing in the schema
  implies otherwise, and nothing should.
- **Aggregates, not raw samples.** Still the right call at 60 Hz.
- **Missing is `null`, never `0`.** Strengthened, via `meta.packet`.
- **Every aggregate carries its sample count.**
- **Nothing derived is presented as measured.** Extended to wear and bottoming.
