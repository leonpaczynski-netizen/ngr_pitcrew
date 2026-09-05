# Pit Crew export contract — `gt7-pitcrew/1.8`

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

Supersedes `gt7-pitcrew/1.0`. Changes and their justification are in §15 (through
1.1) and §16 (1.2 through 1.8). **Every version bump lands with its change table in
the same commit** — without one the consumer cannot tell an added field from a
renamed one, and has to read every unfamiliar field conservatively.

---

## 1. Envelope

One JSON object. Every top-level section is optional except `meta` — emit what Pit
Crew actually has and omit the rest. An omitted section reads as "not built yet"; a
section full of nulls reads as "built but nothing measured." Both are honest. A
section full of zeros is not.

```json
{
  "format": "gt7-pitcrew/1.8",
  "meta":        { },
  "rangeRecord": { },
  "session":     { },
  "laps":        [ ],
  "corners":     [ ],
  "wear":        { },
  "gearing":     { },
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
| `carCategory` | string | `Gr.1`…`Gr.4`, `Gr.B`, `Gr.X`, `Gr.N`, `N100`…`N1000`, or `null`. **The contract's spelling, not GT7's token** — the stream says `GR3` and it is mapped at the export boundary. Validated since 1.5 |
| `circuit` | string | Full GT7 name including layout variant |
| `date` | string | `YYYY-MM-DD` |
| `sessionType` | enum | `practice` \| `quali` \| `tt` \| `race` — must match the Driver Feedback tab so the two halves line up |
| `gameVersion` | string | **Required since 1.4.** Export refuses without it |
| `compound.front/.rear` | string | Full compound name. GT7 cannot run split compounds, so these are normally equal; keep both fields so a mismatch is visible as an input error. **Emitted only when exactly one compound was run** — a session that ran three has no compound, and voting on the most common lap tag made two thirds of it disappear |
| `compoundsRun` | array of string | Every compound the session ran, in order, full names. Present whether one was run or five. `wear.byCompound` may name no compound absent from this list, and export refuses if it does |
| `assists.abs` | enum | `Off` \| `Weak` \| `Default` |
| `assists.tcs` | int 0–5 | |
| `assists.countersteer` | bool | |
| `multipliers.tyreWear/.fuel` | string | `"Off"` or `"Nx"`. String, not number, so `Off` is representable |
| **`packet`** | enum | `A` \| `B` \| `~` \| `C`. **Required.** Declares which channels were physically available. Without it a null is ambiguous between "not captured" and "not offered by this packet format" |
| **`cornerModel`** | object | `source` ∈ `track-map` \| `auto-segment`. `id` and `version` identify the definition used, so corner IDs are comparable across sessions. Required if `corners` is present |
| `appVersion` | string | So a change in the detector does not read as a change in the car |

---

## 3. `setup` — the sheet as run · **RETIRED in 1.8, read-only**

> ⚠ **Pit Crew no longer emits this section, as of 5 Sep 2026.** The app does not
> record what is in the car. The tune builder holds the setup and the gearbox,
> issues changes directly, and the driver confirms them against GT7's own settings
> screen — so the reader of this payload already has the sheet, from the side that
> wrote it. A second copy travelling from here is the defect the removal was for:
> a value kept in two places becomes two values, and it had already happened
> twice on one car.
>
> **The shape below is still declared, and a reader must still accept it**, because
> the archive holds exports going back to 1.0 that carry it. Nothing new will.
> `rangeRecord` (§4) did *not* go with it — a range record is the car's own slider
> limits, not a claim about what is bolted to it, and it is what makes reasoning in
> percent of range possible at all.

**Was:** the highest-value section, and the cheapest — pure app state, no telemetry.
It removed all ambiguity about which version of a sheet produced these symptoms.
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
  "build": { "bhp": 525, "weightKg": 1300, "pp": 730.12, "drivetrain": "MR",
             "weightBalance": "43:57", "torqueKgfm": 56.0, "displacementCc": 5204 },
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
- **`build`** — what the car *is*, as opposed to what was set on it. `bhp`,
  `weightKg` and `pp` are the figures GT7 shows on the tuning screen; **`drivetrain`
  (`FF` \| `FR` \| `MR` \| `RR` \| `4WD`), `weightBalance` (front:rear, as GT7
  writes it), `torqueKgfm` and `displacementCc` joined in 1.7.** Every one of them
  changes what a recommendation should say and none is derivable from the values:
  a rear-biased MR car and a nose-heavy FR car do not want the same answer to the
  same complaint, and the app had no drivetrain field anywhere until the sheet
  started carrying one. Null wherever the sheet does not record it.

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
  "lapsExcludedDetail": [
    { "lap": 1,  "reason": "out-lap",          "source": "auto" },
    { "lap": 2,  "reason": "manual",           "source": "driver",
      "note": "spun at T4" },
    { "lap": 11, "reason": "fuel-implausible", "source": "auto" }
  ],
  "fuelUsedPerLapL": 3.42,
  "fuelCapacityL": 100,
  "bestLapMs": 93912,
  "medianLapMs": 94480,
  "lapTimeStdDevMs": 610,
  "greenLapRefMs": 93912
}
```

- `lapsCounted` excludes out-laps, in-laps, laps with an off, traffic-compromised
  laps, and laps whose fuel burn says they never went round. `lapsExcluded` lists
  which; **`lapsExcludedDetail` says why and who worked it out.**
- `lapsExcludedDetail[].reason` ∈ `out-lap` | `in-lap` | `incident` | `traffic` |
  `fuel-implausible` | `manual`; `.source` ∈ `auto` | `driver`. `note` appears only
  where the driver's own words say more than the vocabulary does — "spun at T4"
  survives, "struck by hand" does not, because it repeats `source`.
- **Fuel plausibility is part of validity.** A lap burning less than half the
  session's median burn is a lap boundary that landed inside a pit or garage
  transition: it is `valid: false`, absent from `lapsCounted`, and never eligible
  for `bestLapMs`. Skipped entirely when `fuelCapacityL` is 0 — an electric car
  burns nothing and every lap would fail.
- **Median, not mean.** One bad lap should not move the number.
- `greenLapRefMs` — the fresh-tyre reference lap the degradation model is measured
  against. Needed to interpret `wear.byLapTime`.
- `fuelCapacityL` is 100 for almost every car, 5 for karts, **0 for electric**. Zero
  is a real value — but it is never *inferred*. GT7 reports 0 both for a car with
  no tank and for a packet that arrived before the car loaded, so the event takes
  the first **plausible** capacity across its runs, and where every run read 0 the
  field is `null` and `notes` says so. A zero that is really the second case
  switches the plausibility gate below off for the whole event.
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

### 6.1 `runs` — which tank, and which set of tyres

**Nothing may be fitted across a refuel**, and until 1.4 nothing in the payload said
where one run ended and the next began. A wear rate spanning three tanks, and a
lap-time trend spanning five, were both computed and both reported as facts about the
tyre.

```json
"runs": [
  { "id": 1, "firstLap": 1, "lastLap": 4, "laps": 4, "lapsCounted": 3,
    "fuelStartL": 100.0, "fuelEndL": 74.82, "fuelDeltaL": 25.18,
    "refuelledBefore": false, "compound": "RS",
    "tyresFresh": null,
    "tyresFreshSource": "not declared - the feed carries no tyre-change event" },
  { "id": 2, "firstLap": 5, "lastLap": 6, "laps": 2, "lapsCounted": 1,
    "fuelStartL": 99.97, "fuelEndL": 87.58, "fuelDeltaL": 12.4,
    "refuelledBefore": true, "compound": "RS",
    "tyresFresh": true,
    "tyresFreshSource": "derived: all four corners at GT7's fitting temperature (70 C) with the car stationary",
    "tyresFreshDeclared": null,
    "tyresFreshObserved": true }
]
```

**A tank and a set of tyres are different objects, and this section keeps them apart.**

| Field | Definition |
|---|---|
| `id` | 1-based, in the order the runs happened. `wear.byDriverGauge[].runId`, `wear.byRun[].runId` and `wear.byCompound[].runIds` all point here |
| `firstLap` / `lastLap` | Inclusive, in the payload's own lap numbering. Runs never overlap and export refuses if they do |
| `refuelledBefore` | **Measured.** The tank rose by more than 0.5 L between the end of the previous lap and the start of this one. A run also starts wherever the driver came in, and wherever the recording session changed — a stop and restart means he went back to the garage |
| `fuelStartL` / `fuelEndL` / `fuelDeltaL` | **Measured.** What the tank did across the run. `fuelDeltaL` is what `wear.byLapTime.fuelDeltaL` is netted against, if the reader chooses to net it |
| `compound` | The compound tagged on this run's laps, or `null` where they disagree. **Never a vote** — a run tagged two ways is a data-entry question, and answering it silently is how three compounds became one |
| `tyresFresh` | `true`, `false` or **`null`**. The resolved answer: the driver's declaration where he made one, otherwise what the temperatures show. **Never inferred from the refuel** — taking fuel without taking tyres is a normal stop, and inferring `true` from one would halve every wear rate spanning it. `null` means neither source can say. **`false` is a positive claim that the set carried over** and needs its source; export refuses a bare `false` |
| `tyresFreshDeclared` | What the driver said on the rack, or `null`. **Primary evidence, and it wins** |
| `tyresFreshObserved` | What the opening tyre temperatures say, or `null`. Corroboration, never more |
| `tyresFreshSource` | Which of the two produced `tyresFresh`, and how. Required alongside a `false` |
| `tyresFreshDisagreement` | Present **only** when the driver and the temperatures say different things. The declaration stands and the disagreement is reported, never averaged away: it is worth more than either statement alone |

**Reading a set off the stream.** GT7 fits every set at one temperature, on all
four corners. That figure is **measured, not looked up** — three runs across
Racing Soft, Racing Medium and Racing Hard in the 11 Aug Monza captures each open
at exactly 70.0 °C on all four corners with the car stationary; nothing published
documents it, and the public accounts describe only the behaviour, that a fresh
set is cold and takes a couple of corners to come in. It is restated every export
in `derived.thresholds.freshTyreTempC` with the runs it came from, so re-measuring
it after a game update reads as a change in the app rather than in the car.

From there a stationary set only cools, so a fresh one reads at or under that
figure with the four corners **even**. The evenness is what does the work, not the
absolute value: a set that has turned a wheel picks up corner-to-corner asymmetry
inside a lap and keeps it, so a spread alone says the set is not new.

It returns `null` rather than guessing in the two cases it cannot separate:

* the car was already rolling when the recording picked it up — a set already
  working reads like a used one whether it is or not;
* the reading is even but has cooled past the allowance, which a fresh set left
  waiting and a used set left longer both eventually do.

**Why `tyresFresh` is worth a field at all.** Every wear rate in `wear.byRun` that
comes from a single gauge reading needs a starting point. Where the set is known to
have gone on at the run's first lap there is one, and the rate is `measured` —
`wear.byRun[].method` states which source established it. Where nothing can say, the
rate assumes the set went on there anyway, which is usually true and occasionally
very wrong, so it carries `assumesFreshAtLap` and drops to `assumed`. The arithmetic
is identical; what differs is whether the export says so.

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
    "gearMin": 2,
    "gearAtApex": 2,
    "gearAtExit": 3,
    "shiftsInCorner": 1.22,
    "upshiftRpm": 8410,
    "yawDeficitPct": 12.4,
    "yawDeficitSamples": 17,
    "yawDeficitFrames": 214,
    "meanHeaveMm": -6.7,
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
| `gearMin` | Lowest gear held anywhere in the corner window, **modal across the counted laps** — the gear he most often got down to, not the average of the gears he got down to |
| `gearAtApex` | Gear at the minimum-speed point, modal across laps. Same apex as `brakePointM` |
| `gearAtExit` | Gear at the last frame of the corner window, modal across laps |
| `shiftsInCorner` | Gear changes inside the window, **mean across laps, so a fraction is meaningful** — `0.4` means he shifted on four laps in ten, which is the inconsistency worth seeing. This is what answers "does 2nd cover all three chicanes without an upshift" |
| `upshiftRpm` | Engine speed at the **first upshift after the apex**, mean across the laps that had one, rounded to whole rpm. `null` if he never upshifted in the window. Compare against `gearing.limiterRpm`: an upshift well below the limiter is a deliberate short-shift, and it costs pace to save fuel and rear tyre |
| `yawDeficitPct` | **How far short of the rotation the steering implied the car actually turned**, median across the frames where lock was being added, mean across laps. Positive is short; negative means it rotated more than the lock implied. **Read it beside `entrySpeedKph` and nowhere else.** Expected yaw is proportional to speed while a car at its grip limit yaws as `1/v`, so this quantity carries a `1/v²` structure that is a property of the expression and not of the car — a neutral car reads worse at speed. It is a magnitude for a human to weigh against the driver's own account, and **it gates nothing**. `null` where no frame could be judged, which is not zero deficit |
| `yawDeficitSamples` / `yawDeficitFrames` | Laps that produced a figure, and total qualifying frames behind it |
| `meanHeaveMm` | **The four-wheel mean of peak compression against `derived.bottomingRefMm`.** Positive is closer to the floor than the car gets in a straight line; negative is further from it. **Read this before `flags: bottoming`** — roll cancels in a four-wheel mean and floor contact does not, so a corner flagging on one wheel with a negative mean heave is a car leaning, not a car grounding. `null` without a reference, which is not zero |
| `suspHeightMinMm` | Minimum of the per-wheel suspension channel. **That channel is COMPRESSION, not height** — measured 17 Aug 2026, `body_height_mm` falls 61→50 mm from 120 to 260 km/h while every `susp_mm` rises — so this is the most **extended** the wheel got, i.e. the lightest, and the bottoming end is the maximum. The name predates the measurement and is kept for compatibility; `derived.bottomingRefMm` is now peak compression on straight-line frames and is the figure to interpret against. **Not travel remaining** — see §15 |
| `surfaceMix` | Fraction of samples per surface character: `T` tarmac, `C` kerb, `D` dirt, `G` grass, `S` sand, `s` snow. Packet `~`/`C` only |

**Gears are modal, never mean.** A mean gear of 2.6 is not a gear, and a reader
given one reasons about a gearbox that does not exist. `shiftsInCorner` and
`upshiftRpm` are a count and an engine speed rather than a gear, so those two
average legitimately.

### 7.1 `flags` — controlled vocabulary

| Flag | Detection |
|---|---|
| `bottoming` | per-wheel suspension **compression** within the reference band of the straight-line peak for > 50 ms, **excluding frames where that wheel reads surface `C`** — a kerb compresses the suspension by design and is reported separately as `kerb-strike`. Inferred, never measured: GT7 reports no travel-remaining channel. Weigh it against `meanHeaveMm` |
| `countersteer` | steering sign reversal > 10° within 300 ms |
| `wheelspin` | driven-wheel surface speed exceeds vehicle speed by > 8% under throttle |
| `lockup` | wheel surface speed below vehicle speed by > 15% under brake |
| `trail-brake-instability` | countersteer inside the trail-brake window |
| `off-track` | any wheel on a surface other than `T` or `C` |
| `kerb-strike` | suspension height step change > 20 mm in < 100 ms |

**A flag carries its lap count.** `flags` lists only those that fired on at least
`derived.thresholds.flagMinShareOfLaps` of the counted laps - a quarter. `flagLaps`
gives every flag seen with the number of laps it fired on, and `flagThresholdLaps` the
count that had to be met. A set union across laps made every corner carry every flag
once enough laps were run: seven findings, which is none. Standing rule 4 applies to
flags exactly as it does to numbers.

**Thresholds are the app's, not the game's.** Restate them in `derived.thresholds` on
every export, so that retuning a detector does not read as a change in the car.

---

## 8. `wear` — modelled, never measured

**GT7 exposes no tyre wear channel in any packet format.** This section exists to
make that explicit rather than to hide it. Every entry carries its source.

**Readings are per corner, not per axle.** The four wheels wear at different rates,
GT7's own gauge shows them separately, and a stint ends when the **worst single
corner** is done — not when an axle pair averages done. An axle figure cannot express
a car eating its front-left, which is the pattern open tuning without BoP tends to
produce and the one brake balance and setup actually act on. `worst` is that limiting
corner's fraction and is what `modelledStintLaps` is computed from.

`worstCorner` is `null` when more than one corner shares the highest reading.
Nominating one of a tied pair would assert an asymmetry the driver never reported.
A corner he did not read is `null` and stays `null` — never `0`, which would read as
a fresh tyre and be believed.

```json
"wear": {
  "channelAvailable": false,
  "byDriverGauge": [
    { "lap": 6,  "fl": 0.58, "fr": 0.52, "rl": 0.43, "rr": 0.41,
      "worst": 0.58, "worstCorner": "fl", "source": "driver-gauge" },
    { "lap": 11, "fl": 0.94, "fr": 0.83, "rl": 0.72, "rr": 0.70,
      "worst": 0.94, "worstCorner": "fl", "source": "driver-gauge" }
  ],
  "byCorner": {
    "atLap": 11,
    "worstCorner": "fl",
    "worst": 0.94,
    "frontMinusRear": 0.175,
    "leftMinusRight": 0.048,
    "source": "driver-gauge"
  },
  "byRun": [
    { "runId": 3, "compound": "RS", "firstLap": 7, "lastLap": 10,
      "readingLap": 10, "reading": 0.69, "readingCorner": "rl",
      "wearPerLap": 0.1725,
      "method": "one gauge reading, assumed fresh at the run's first lap",
      "confidence": "assumed", "source": "driver-gauge",
      "assumesFreshAtLap": 7,
      "degradationMsPerLap": null, "degradationSamples": 2 }
  ],
  "byCompound": {
    "RS": { "compound": "Racing Soft", "wearPerLap": 0.1725,
            "stints": 3, "stintsMeasured": 1, "runIds": [1, 2, 3],
            "source": "driver-gauge", "confidence": "assumed" }
  },
  "byLapTime": {
    "refLapMs": 93912,
    "degradationMsPerLap": -38.2,
    "fittedRunId": 5,
    "fittedOverLaps": [22, 36],
    "samples": 12,
    "fuelDeltaL": 98.57,
    "fuelNetted": false,
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
  "wearMeasuredAtRaceMultiplier": true,
  "wearMultiplier": "8x",
  "modelBasis": "0.85 / w, w from the driver's gauge at this multiplier",
  "modelConfidence": "assumed",
  "modelConfidenceBasis": "weakest of byCompound.RS (assumed), byRun[3] (assumed); byLapTime and byTemp corroborate rather than feed this and carry their own confidence"
}
```

**Every rate is computed inside one run** (section 6.1) and never across a refuel. The
previous rule - one reading divided by the laps of every run sharing a compound tag -
read a Racing Soft set consuming 17% a lap as 6.9%: an understatement of two and a
half times, in the direction section 5.1 of `CLAUDE.md` says costs most.

- `byRun` is one record per run: what the gauge said, the rate it gives, **the method
  that produced it**, and what that method had to assume. `method` is either
  `"two gauge readings inside one run"`, which assumes nothing, or `"one gauge
  reading, assumed fresh at the run's first lap"`, which carries `assumesFreshAtLap`
  and is `assumed` unless the driver declared the set fresh. Where no rate could be
  taken, `wearPerLap` is `null` and `wearPerLapUnavailable` says why in a sentence.
- `byRun[].degradationMsPerLap` is the lap-time trend **inside that run only**. Two
  runs on one compound can trend opposite ways; a single headline figure hides that,
  and the disagreement is worth more than the headline.
- `byCompound[].compound` is the full name, so the section can be checked against
  `meta.compoundsRun` - **export refuses a compound the session never ran.**
  `stints` is how many runs were on that compound; `stintsMeasured` how many produced
  a rate. Run three times and read once is a thinner claim than run once and read
  once, and only the pair of counts says so.
- `byLapTime` is fitted **within one run**, by **Theil-Sen** (the median of pairwise
  slopes), and names the run in `fittedRunId` / `fittedOverLaps` / `samples`. Fitted
  across tanks, the sawtooth of a car getting heavier and then abruptly light reads as
  degradation: +72 ms/lap was once exported for a car that was getting faster. Least
  squares was abandoned because one un-struck incident lap moved the slope by 90
  ms/lap and took the sign with it. `null`, with a stated reason, when no run is long
  enough - five counted laps.
- **Fuel is not netted off.** `fuelNetted` is `false` and `fuelDeltaL` gives the burn
  over the fit window, so the reader nets it with a coefficient they can state. A full
  tank is worth roughly 0.003 s/L/lap, which over a long stint exceeds the tyre signal
  it would be netted against - and that coefficient is itself derived, not measured.
- `wearMeasuredAtRaceMultiplier` and `wearMultiplier` travel with every rate.
  Multiplier linearity is assumed and has never been demonstrated.
- `gaugePinned` appears when the worst corner read the same twice. Either the gauge
  has saturated or the two readings are of different sets; no rate is taken through it.
- `modelConfidence` is **computed, not declared** - the weakest of the fields the
  model is built from - and `modelConfidenceBasis` shows the working. It deliberately
  does **not** roll in `byLapTime` and `byTemp`: both are `low` by nature, and
  including them would peg the field to `assumed` on every export ever made, which
  says nothing about whether `w` itself was measured. The basis names them as
  corroborating, so the roll-up cannot be read as covering them.

- `byDriverGauge` is the most reliable input and the only one anchored to the game's
  own number. Fraction **consumed**, 0–1, one entry per corner: `fl`, `fr`, `rl`,
  `rr`. Same corner vocabulary as `laps[].tyreTempMeanC`, so a wear figure and the
  temperature that explains it are named the same thing. An entry that names no
  corner at all is refused at export rather than emitted.
- `byCorner` is the axle and side asymmetry at the last lap read. It is reported, not
  optimised against: **GT7 allows no partial tyre change and no split compounds
  front-to-rear**, so asymmetric wear is a brake-balance and setup finding, never a
  strategy one. `frontMinusRear` and `leftMinusRight` are `null` — not `0` — when only
  one end or one side was read.
- `phase` ∈ `flat` (0–50%) \| `linear` (50–90%) \| `cliff` (>90%) — GT7 degradation is
  piecewise. Do not report a linear rate without saying which phase it was fitted in.
- `modelConfidence` ∈ `measured` \| `assumed` \| `converted`. **`converted` means the
  stint was calibrated at a different multiplier and scaled** — multiplier linearity
  is assumed, never demonstrated, so this value must never be presented as measured.

## 9. `gearing` — the box as fitted, with the final drive derived

**GT7 broadcasts the eight gear-ratio slots but not the final drive.** Everything
in this section that comes off the stream says so, and the one figure that does
not — `fittedFinalGear` — is computed from engine speed against wheel speed and
tyre radius and is labelled `derived`, per standing rule 5 in `CLAUDE.md`. It must
never be read as the number on the sheet.

The section answers three questions the driver otherwise answers by hand:

- **Is the gearbox in the car the gearbox on the sheet?** Otherwise invisible
  until a whole test session has been run on the wrong box.
- **Where is the limiter, really?** Only when the rev-limiter flag actually fired.
- **What is this car's gearing constant?** One clean reading makes every future
  gearbox on that car exact instead of iterated.

**There is no tow detection and there never will be.** GT7's feed carries no
proximity, no closing speed and no opponent positions, so "top speed in clean air
versus in a tow" is not answerable. This section reports the observed maximum with
its sample count; whether there was a tow is the driver's to say in `notes`. Export
validation walks the payload and **refuses any key containing "tow" at any depth**,
because such a field could only be a fabrication.

```json
"gearing": {
  "fittedRatios": [3.10, 2.28, 1.79, 1.46, 1.22, 1.04],
  "fittedFinalGear": 3.72,
  "ratioSource": "telemetry",
  "finalGearSource": "derived: rpm against wheel speed and tyre radius",
  "matchesSheet": true,
  "gearboxChangedMidSession": false,
  "limiterRpm": 8612.0,
  "limiterRpmSource": "observed-at-rev-limiter",
  "samples": 9,
  "maxSpeedKph": 278.7,
  "maxSpeedGear": 6,
  "maxSpeedRpm": 8600.0,
  "topGearReachedLimiter": true,
  "gearingConstantK": 1078.2,
  "gearingConstantSource": "computed: observed speed x ratio x final gear, gear 6, 9 laps"
}
```

| Field | Type / unit | Provenance |
|---|---|---|
| `fittedRatios` | array of float, or `null` | **Measured.** The ratios the car actually had, taken from the **most recent counted lap that carried them** — not merged across laps. 1st…nth in order, dimensionless. GT7 sends eight slots and zeroes the ones a car does not have; the unused slots are dropped at capture, so the array length **is** the number of forward gears. `null` when no counted lap carried ratios |
| `fittedFinalGear` | float, 3 dp, or `null` | **Derived, never measured** — GT7 does not broadcast it. `final = (rpm / 60) × 2π × r / (v × ratio[gear])`, evaluated per frame and reduced by **median**. Frames qualify only above 100 km/h and only in a gear the ratio array covers. `null` whenever `fittedRatios` is null or no frame qualified |
| `ratioSource` | string, or `null` | `"telemetry"` when ratios were read off the stream, `null` when there are none. There is no other value: the app never reads ratios off the sheet into this field |
| `finalGearSource` | string, or `null` | Literally `"derived: rpm against wheel speed and tyre radius"`, or `null` when `fittedFinalGear` is null. **Its whole job is to stop a derived number reading as a measured one** |
| `matchesSheet` | bool, or `null` | **Derived comparison.** `fittedRatios`, truncated to the sheet's gear count, against `setup.gears`, each ratio within **±0.005 absolute**. `null` when either side is unknown — which is not "they differ", and is the reason it is a tri-state rather than a bool. **It does not cover the final drive**, and `matchesSheetCovers` says so in the payload rather than leaving a reader to infer it from a boolean sitting beside a contradictory number |
| `matchesSheetCovers` | string | What the boolean above is, and is not, a claim about. Present whenever `gearing` is |
| `finalGearSheet` | float, or `null` | **The driver's own figure**, off `setup.values.fg`. Exact, unlike the derived one |
| `finalGearVsSheetPct` | float, or `null` | The gap between derived and sheet, as a percentage of the sheet. Expect a few percent high: GT7 broadcasts the **unloaded** tyre radius, and a loaded racing tyre stands shorter |
| `rollingRadiusImpliedM` | float, 4 dp, or `null` | The tyre radius the sheet's final drive implies. On the 911 RSR the packet broadcasts a constant 0.355 m and this comes out at 0.3438 m — a 3.2% deflection, which accounts for the whole of `finalGearVsSheetPct`. It turns a misleading gearbox number into a measured tyre one |
| `limiterGear` | int, or `null` | **Measured.** The gear the limiter fired in, modal across the frames. Without it, `limiterRpmSource: observed-at-rev-limiter` beside `topGearReachedLimiter: false` reads as a contradiction. It is not one, and this is the field that says so |
| `gearboxChangedMidSession` | bool, never `null` | **Measured.** `true` when not every ratio-carrying lap ran the same box. A mid-session gearbox change invalidates any aggregate spanning it, exactly as a setup change does. `false` when fewer than two laps carried ratios — absence of evidence, reported as no change |
| `limiterRpm` | float, whole rpm, or `null` | **Measured, and only at the limiter.** Median engine speed across frames where GT7's own rev-limiter flag was set. `null` when the limiter never fired. **Deliberately not "the highest rpm seen"** — a session that never hit the limiter has no limiter reading, and the peak in its place means something else entirely |
| `limiterRpmSource` | string, always present | `"observed-at-rev-limiter"`, or `"limiter never fired in this session"` when `limiterRpm` is null. The null carries its own explanation rather than leaving the reader to guess between "not captured" and "never happened" |
| `samples` | int | Counted laps that carried **frames**. Note this is the frame-bearing lap count, not the count of laps that carried ratios — `fittedRatios` is a single-lap reading and has no sample count of its own |
| `maxSpeedKph` | float, 1 dp | **Measured.** Highest speed in any frame of any counted lap. Absent — the key is omitted, not null — when no frame carried a speed. `maxSpeedGear`, `maxSpeedRpm` and `topGearReachedLimiter` are omitted with it |
| `maxSpeedGear` | int, or `null` | **Measured.** Gear held at that fastest frame |
| `maxSpeedRpm` | float, whole rpm, or `null` | **Measured.** Engine speed at that fastest frame |
| `topGearReachedLimiter` | bool | **Derived.** `true` only when the fastest frame was in the **top** gear the ratio array holds *and* within 100 rpm of `limiterRpm`. This is the qualifier for `gearingConstantK`, and on its own it answers whether the car is over- or under-geared for the circuit |
| `gearingConstantK` | float, 1 dp | **Computed or extrapolated, and only in top gear.** `K = speed in top gear at the limiter × ratio[topGear] × final drive`. Where the limiter fired in top, the observed speed is used. Where it did not — most sessions at most circuits — the observed top-gear speed is scaled to the limiter by `limiterRpm / maxSpeedRpm`, and the source says `extrapolated:` rather than `computed:`. **Omitted entirely** — key absent, not null — anywhere but top gear: there the car simply was not going as fast as the gearing allows, and no scaling recovers it |
| `gearingConstantSource` | string | `computed: …` or `extrapolated: top gear observed at N rpm, scaled to limiter M, K laps`. The two are never worded alike |
| `gearingConstantFinalGear` / `…FinalGearSource` | float / string | **Which final drive K was built on.** The sheet's wherever there is one: it is exact, and the derived figure carries the unloaded-radius bias, so a K built on that would put every future gearbox out by the same few percent |
| `gearingConstantSamples` | int | Frame-bearing counted laps behind it, so a K from one lap is not mistaken for a K from nine |
| `topGearSpeedAtLimiterKph` | float, 1 dp | The speed the extrapolation used, so the arithmetic can be checked |

**`fittedRatios` is not rounded.** It is the raw 32-bit float as broadcast, so
expect `3.0999999046325684` where the game's screen shows `3.100`. That noise is
exactly why `matchesSheet` and `gearboxChangedMidSession` compare within ±0.005
rather than for equality, and it is why the ratios should be read to three decimals
and no further.

**Tyre radius is the rear-left wheel's.** The derivation needs a driven-wheel
radius and the recorder stores one channel, `tyre_radius_m`, taken from the rear
left. On a front-drive car with a different front radius the derived final drive
inherits that error. Laps recorded before this channel existed decode fine and
simply yield `fittedFinalGear: null`.

**The whole section is omitted** when no counted lap carried ratios *and* no frame
carried a speed — there is nothing to say about the box. It is emitted with nulls
when something was captured but not enough to conclude, which is the honest middle
case §1 describes.

## 10. `strategy` — the plan and its assumptions

Present only for `sessionType: "race"`, or for a practice session run explicitly to
calibrate strategy. Its purpose is to make the app's own reasoning auditable.

```json
"strategy": {
  "plan": { "stops": 1, "laps": 27, "stintLaps": [13, 14],
            "compounds": ["RH", "RH"], "pitLap": 13 },
  "raceLength": {
    "type": "time",
    "minutes": 50,
    "extraTimeS": 180,
    "lapsAtThisPace": 27,
    "maxDurationS": 3108.0,
    "finishAtS": 3043.1,
    "note": "The flag falls at the first line crossing after the clock. Distance is an output of the plan, not an input - every stop is time stationary while the clock runs and is paid for in laps. maxDurationS is the longest this race can possibly last; a plan past it is impossible, not slow."
  },
  "bindingConstraint": "fuel",
  "compoundProfiles": [
    { "compound": "RS", "paceDeltaSPerLap": 0.0,  "wearPerLap": 0.055,
      "source": "measured", "lapsMeasured": 12, "stintsMeasured": 1,
      "longestStintLaps": 12,
      "wearConfidence": "measured", "deepestObservedFrac": 0.56,
      "tyreWindow": {
        "meanC": 103.4,
        "perCornerC": { "fl": 108.1, "fr": 101.7, "rl": 102.0, "rr": 101.8 },
        "band": "optimal",
        "lapsSampled": 6, "lapsInWindow": 6, "inWindow": true,
        "windowC": [85, 110],
        "hottestCorner": "fl",
        "source": "tyre-surface-temp"
      },
      "windowQualification": null },
    { "compound": "RM", "paceDeltaSPerLap": 0.34, "wearPerLap": 0.038,
      "source": "measured", "lapsMeasured": 11, "stintsMeasured": 1,
      "longestStintLaps": 11,
      "wearConfidence": "assumed", "deepestObservedFrac": 0.24,
      "tyreWindow": {
        "meanC": 71.2,
        "perCornerC": { "fl": 74.0, "fr": 70.1, "rl": 70.4, "rr": 70.3 },
        "band": "warming",
        "lapsSampled": 6, "lapsInWindow": 0, "inWindow": false,
        "windowC": [80, 105],
        "hottestCorner": "fl",
        "source": "tyre-surface-temp"
      },
      "windowQualification": "RM never got into its window (71.2 °C mean against a 80–105 °C window, 6 of 6 laps outside it). A cold tyre is slower than the compound is and wears less than it will, so its pace deficit is overstated and its stint length is flattered. Neither figure describes a race run at temperature." }
  ],
  "compoundCrossover": {
    "winner":      { "label": "1 stop",  "compounds": ["RS", "RM"] },
    "alternative": { "label": "2 stops", "compounds": ["RS", "RS", "RS"],
                     "lostBySeconds": 8.4 },
    "stopsSaved": 1,
    "alternativePaceDeltaSPerLap": 0.0,
    "breakEvenSPerLap": -0.42,
    "restsOnAssumption": false,
    "outsideTyreWindow": ["RM never got into its window (…)"],
    "verdict": "RS/RM beats RS/RS/RS by 8.4 s over the race, saving 1 stop. RS/RS/RS would need to be 0.42 s/lap quicker than it is to change the call. RM never got into its window (…)",
    "source": "derived-from-total-race-time"
  },
  "assumptions": {
    "pitLossS": 19.5,
    "pitLossSource": "measured-this-track",
    "refuelRateLps": 1.0,
    "refuelRateSource": "as the plan was costed",
    "fuelPerLapL": 3.42,
    "fuelWeightSPerLPerLap": 0.003,
    "fuelWeightSource": "derived-not-measured",
    "compoundDeltaSPerLap": 0.153
  },
  "callsMade": [
    { "lap": 4,  "call": "Map 3 down the back straight",     "reason": "1.2 laps short on fuel", "accepted": false, "disposition": "declined", "confidence": "high" },
    { "lap": 12, "call": "Box this lap. RS.",                "reason": "fuel is the constraint", "accepted": null, "disposition": "taken", "confidence": "high" },
    { "lap": 20, "call": "Chequered flag. P1.",              "reason": "race complete", "accepted": null, "disposition": "informational", "confidence": "high" }
  ],
  "outcome": "Stopped lap 11. Fuel to the diamond +1 lap. Tyres had 2 laps left — stint was fuel-limited, not tyre-limited."
}
```

`bindingConstraint` ∈ `tyre` \| `fuel` \| `regulation` \| `evidence` \| `unknown`.
Knowing which one bound the stint is the single most useful strategy output, because
it decides whether the next setup should chase durability or pace.

**`evidence` means none of the others bound it — the cap is the longest stint anyone
has actually run on the compound, and it is an admission rather than a measurement.**
Read it as *"do not conclude anything about durability from this plan's stint
length"*: the tyre and the tank both allowed more, and the only reason the plan is
shaped this way is that nobody has been out that far yet. The action it implies is a
long run in practice, not a setup change. Added in 1.6 — see §16.

`callsMade` exists so live advice can be checked against what actually happened.
An app that gives calls and never records them cannot be improved.

**`accepted` is null for every call that was never a question, and
`disposition` is the field to read.** Most calls are statements — "Green,
green, green.", "P2. 5 to go.", "Chequered flag." — and a boolean cannot hold
what became of a statement. Recording those as `accepted: false` is not a
missing value, it is the claim that the driver refused them; on the Watkins
race of 17 Aug 2026 it made **all fourteen calls read as declined**, which left
the only feedback channel on the strategy engine saying nothing at all.

| `disposition` | Meaning |
|---|---|
| `informational` | Said, never asked. `accepted` is null and means nothing here |
| `taken` / `not-taken` | An instruction, and whether a pit lap followed it within two laps. **Derived from the laps, not from an answer** — an instruction is never offered and never answered |
| `accepted` / `kept` / `expired` / `superseded` | A re-plan offer and how it left the desk. `accepted` is a real boolean for these |
| `declined` | A record from before the marker existed, where the stored boolean was all there was |

#### 10.0 A timed race is not a lap race

**For a race run to the clock, the distance is an output of the plan.** The flag
falls at the first line crossing after the time expires, so every pit stop is
time spent stationary while the clock runs and is paid for **in laps, not in
seconds**. Two stops on a 108-second circuit cost about a lap of race distance,
and that trade is the whole question.

A model handed a fixed lap count cannot see it at all: it reports the stops as
free and the race as getting longer. That is how a 50-minute race came back as
a **52-minute plan** — not a slow plan, an impossible one.

| Field | Definition |
|---|---|
| `raceLength.type` | `time` or `laps`. Everything below applies to `time` |
| `.minutes` | The clock, as declared |
| `.extraTimeS` | What GT7 allows for finishing the lap the clock ran out on, or `null` for one full lap |
| `.lapsAtThisPace` | What **this plan** covers. A different stop count gives a different number, which is the point |
| `.maxDurationS` | **The longest this race can possibly last**: the limit plus one lap, or plus `extraTimeS`, whichever is shorter. Any plan whose finish exceeds it is describing a race that cannot happen |
| `.finishAtS` | When the flag falls under this plan, always at or under `maxDurationS` |

Two consequences for reading the plans:

- **They are ranked on distance, then on time.** Every plan ends when the clock
  does, so ranking on elapsed time ranks them on where the last lap happened to
  fall. `delta_s` is seconds behind at the flag, a lap down counting as a lap's
  worth of time — which is what the results screen shows.
- **No plan stops after the flag.** A stop scheduled past the limit is marked
  not runnable: nobody turns into the pit lane on the last lap of a timed race.

## 10.1 `compoundProfiles` and `compoundCrossover`

**What each compound costs, and why the plan picked the one it did.** The model
searches stop counts *and* compound assignments, costing every candidate over the
full race distance — so a tyre that is slower per lap but lasts long enough to
delete a stop can win, which is the whole question the driver asks before a race.

| Field | Type / unit | Provenance |
|---|---|---|
| `compoundProfiles[].paceDeltaSPerLap` | float, seconds | **Measured** where practice ran that compound: median counted lap on it against the median on the reference. The reference compound is always `0.0` |
| `compoundProfiles[].wearPerLap` | float 0–1, or `null` | **Measured** over the laps the set actually ran, not over the lap number — a reading of 60% at lap 20 is a different rate depending on when the tyres went on. `null` where the compound was run but no gauge reading was taken |
| `compoundProfiles[].source` | enum | `measured` \| `declared` \| `assumed`. `declared` means the pace is known but the wear rate — which is what sets the stint — is not. `assumed` means the compound inherited the reference's rate and was never run |
| `compoundProfiles[].lapsMeasured` / `.stintsMeasured` | int | The sample count behind the pair. A rate from one stint and one from three are not the same claim |
| `compoundCrossover.stopsSaved` | int | Stops the winner saves against the alternative. Negative when the winner takes *more* stops and still wins |
| `compoundCrossover.breakEvenSPerLap` | float, seconds | The pace delta at which the alternative would draw level. Compare against its actual `alternativePaceDeltaSPerLap`: a small margin means a tenth either way decides the race |
| `compoundProfiles[].tyreWindow` | object, or `null` | **Measured**, from per-wheel tyre *surface* temperature against that compound's own window in `store/tyres.py`. `meanC` and `perCornerC` are averaged over whole laps — surface temperature responds far faster than the carcass, so a single frame is not a working range. `lapsSampled` is capped (see below) and always travels with the conclusion. `null` when no frames carried a temperature, which is **not** the same as the tyre having been fine |
| `compoundProfiles[].windowQualification` | string, or `null` | What the window does to the two figures above, in one sentence. `null` when the tyre was working and the evidence needs no qualification |
| `compoundCrossover.outsideTyreWindow` | array of string | Every qualification bearing on this comparison, from **both** sides — a call is only as good as the weaker of the two measurements it rests on. Empty when both compounds were in window |
| `compoundCrossover.restsOnAssumption` | bool | True when either side is planned on a rate never measured on it |
| `compoundCrossover.verdict` | string | The comparison in one sentence, written once in the model so the screen, this payload and the engineer's prompt all say the same thing about the same plan |

**A gap of zero between two compounds is not a dead heat.** When only one compound
has a measured wear rate, every alternative is that same rate wearing a different
name, so the plans cost identically. `restsOnAssumption` is `true` in that case and
`verdict` says the comparison has not been earned yet rather than reporting a tie.
`compoundCrossover` is absent entirely when there was no alternative on different
rubber to compare against.

### 10.2 The tyre window qualifies the evidence; it never corrects it

**A compound below its window is slower than it is, and wears less than it will.**
Harder compounds need more energy to light up, so a Racing Hard measured on a cool
track looks like a bad tyre that lasts forever — and *both* halves of that are the
temperature rather than the compound. Above the window the opposite: an overheating
stint measures a wear rate a cooler race will not reproduce.

Nothing in this section scales a measured figure to what it "would have been".
GT7 publishes no recovery curve, and inventing one would put a fabricated number
where a measured one belongs, in the section a race plan is built from. The pace
and wear stay exactly as measured; `windowQualification` says how far they carry.

This is the quieter of the two failures the crossover can suffer. `restsOnAssumption`
is loud — a number is simply missing. A window failure looks complete: the
arithmetic is finished and the inputs are genuinely measured, and only the
temperature says the answer will not reproduce on race day.

**Sampling.** Decoding a lap's frames costs roughly 65 ms against a ~1.6 MiB blob,
so the window reads the **most recent 6 counted laps per compound** rather than the
whole event — the latest setup, on the most rubbered-in track. A lap's mean surface
temperature barely moves lap to lap, so this is a real sample rather than a
compromise, and `lapsSampled` carries it so the cap is never silent.

## 11. `derived` and `notes`

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
  "steerRotationDeg": 180,
  "steerRotationSource": "full lock of the exported channel, from centre - wheelRotation saturates at +-pi whatever rotation the rim is set to, so steerPeakDeg divided by this is steerPeakNorm. Not the driver's physical wheel rotation setting.",
  "bottomingRefMm": { "fl": 31, "fr": 31, "rl": 38, "rr": 38 },
  "bottomingRefSource": "steady-state minimum observed, laps 3-9",
  "observedMinHeightMm": { "fl": 28, "fr": 29, "rl": 35, "rr": 36 },
  "understeerIndexByCorner": { "T1": 0.12, "T3": 0.31 },
  "balanceDriftPerLap": "+0.4 understeer index over 9 laps"
},
"notes": "Laps 1, 2 and 11 excluded - out-lap, traffic, in-lap. Rear ARB changed lap 5, so corner aggregates span two configurations; T1 and T3 recomputed on laps 5-10 only."
```

`notes` is free text and is read literally. Use it for anything that qualifies the
numbers above — it is cheaper to explain an exclusion than to have a setup built on a
misread aggregate.

---

## 12. Units — fixed, no inference from magnitude

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
| Gear ratios and final drive | dimensionless | 1st…nth in order; final drive separate. Read to three decimals — `fittedRatios` carries float noise below that |
| Engine speed | rpm | Scalars only, each named and sourced. Never a series — see §13 |
| Gear | integer, 1-based | Modal across laps, never averaged |

---

## 13. What NOT to export

Raw 60 Hz traces · GPS position arrays · engine RPM **series** · **oil and water
temperature** (pinned at ~110 °C and ~85 °C — they carry no information) · boost ·
replay-derived data · anything about tyre pressure, caster, brake pressure, or
high/low-speed damper splits (**none of these exist in GT7**).

None of it changes a setup decision, and all of it displaces the driver's report.

The RPM prohibition is on the **series**, not on engine speed as such. Three named
rpm scalars are exported, each answering one question and each stated with its
provenance: `gearing.limiterRpm`, `gearing.maxSpeedRpm` and `corners[].upshiftRpm`.
A 60 Hz rpm trace is still refused.

---

## 14. Markdown fallback

If JSON is impractical, the same content as markdown parses less cleanly but is
acceptable. Keep the headings identical to the JSON keys — `## meta`, `## setup`,
`## rangeRecord`, `## session`, `## laps`, `## corners`, `## wear`, `## gearing`,
`## strategy`, `## derived`, `## notes` — one table per section. Do not invent a different layout;
the value is in the consistency, not the syntax.

---

## 15. Changes from `gt7-pitcrew/1.0`, and why

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

### 15.1 Kept unchanged, deliberately

- **The driver report is primary; this is corroboration.** Nothing in the schema
  implies otherwise, and nothing should.
- **Aggregates, not raw samples.** Still the right call at 60 Hz.
- **Missing is `null`, never `0`.** Strengthened, via `meta.packet`.
- **Every aggregate carries its sample count.**
- **Nothing derived is presented as measured.** Extended to wear and bottoming.

---

## 16. Changes since `gt7-pitcrew/1.1`

### 16.1 → `1.2`

| # | Change | Reason |
|---|---|---|
| 1 | **New `gearing` section** (§9) | GT7 broadcasts the eight fitted ratios but not the final drive. The section carries the ratios as fitted, whether they match the stored sheet, whether the box was changed mid-session, and the observed limiter — with the final drive marked **derived** (from rpm against wheel speed and tyre radius) rather than passing as measured |
| 2 | `corners` gains **`gearMin`, `gearAtApex`, `gearAtExit`, `shiftsInCorner`, `upshiftRpm`** | Gear selection at a corner is a setup question the corner aggregates could not previously answer. `shiftsInCorner` is what answers "does 2nd cover all three chicanes without an upshift"; `upshiftRpm` against `gearing.limiterRpm` is what makes a deliberate short-shift visible. The three gear fields are **modal** across laps — a mean gear is not a gear |
| 3 | `strategy` is finally passed to the payload | It never had been, so every export before 1.2 was silent about the plan. `strategy.assumptions.refuelRateLps` became **required** at the same time and export refuses without it: at 1 L/s against a 2.5 default it is the number that decides the race |
| 4 | Export refuses any key containing **"tow"**, at any depth | GT7 carries no proximity, closing speed or opponent positions, so a tow field could only be a fabrication. Enforced by the validator rather than left to discipline |

**1.2 shipped without a contract revision** — the four rows above were written
after the fact, and the `gearing` spec in §9 was reconstructed from
`analysis/gearing.py` rather than from a sample payload. A sample would have got it
wrong: the one to hand has `fittedRatios: null` and carries neither
`gearingConstantK` nor `gearingConstantSource`, so the shape it shows is a subset
of the shape the code emits.

### 16.2 → `1.3`

| # | Change | Reason |
|---|---|---|
| 1 | `wear.byDriverGauge[].front/.rear` → **`.fl/.fr/.rl/.rr`**, plus `worst` and `worstCorner` | **Breaking.** The four corners wear at different rates and GT7's own gauge shows them separately. A stint ends when the worst *single corner* is done; an axle pair averages that away, and a plan built on the average overshoots the cliff — which §5.1 of `CLAUDE.md` says costs far more than undershooting. `worst` is what `modelledStintLaps` divides |
| 2 | **New `wear.byCorner`** | Which corner is going, and the front/rear and left/right asymmetry behind it. Reported rather than optimised against: GT7 permits no partial tyre change and no split compounds, so this is a brake-balance and setup finding |
| 3 | `worstCorner` is `null` on a tie | Naming one of two corners tied at the same reading asserts an asymmetry the driver never reported, and an invented asymmetry is what a setup then gets built on |
| 4 | A gauge entry naming **no** corner is refused at export | A row of nulls dressed as evidence is worse than no row. Consistent with refusing rather than emitting something that will be misread |
| 5 | **New `wear.byCompound`** | A wear rate measured on one compound describes that compound and no other, so rates are keyed by compound and never pooled. Measured over the laps each set ran — the old figure divided by the lap number, which assumed the tyres went on at lap 1 and understated every stint after the first by the length of the ones before it |
| 6 | **New `strategy.compoundProfiles` and `strategy.compoundCrossover`** (§10.1) | The model could not tell compounds apart at all: one `wear_per_lap`, one `lap_time_ms`, and a search over stop counts only. A harder tyre was costed as identical to the soft it replaced, so it could never win — which made "is it worth running the hard longer to skip a stop" unanswerable |
| 7 | `assumptions.compoundDeltaSPerLap` is a real figure | It had been hard-coded `null` since the field was introduced. It is now the plan's compounds against the reference, weighted over the race distance |
| 8 | **New `compoundProfiles[].tyreWindow` / `.windowQualification` and `compoundCrossover.outsideTyreWindow`** (§10.2) | `store/tyres.py` had carried a per-compound temperature window since the rebuild and **nothing read it**, so compounds were compared on pace and wear without asking whether either was gathered on a tyre that was working. A compound below its window is slower than it is *and* wears less than it will, so a cold Racing Hard reads as a bad tyre that lasts forever — and a stint planned on that fails in the direction §5.1 says costs most |

**Migrating stored 1.1 data.** The app's schema v3 migration spreads each axle
reading across both of that axle's corners, which is what the single figure meant
when it was entered. It does overstate precision on the healthier corner of a pair
and no later reading can correct that, so pre-1.3 readings should be read as axle
figures wearing corner names.

### 16.3 → `1.4`

Every row here comes from a defect the knowledge base found while diagnosing a real
setup off the 11 Aug Monza export. Three of them would have changed the setup or the
race strategy if they had been believed.

| # | Change | Reason |
|---|---|---|
| 1 | **New top-level `runs`** (§6.1), and `wear.byDriverGauge[].runId` | Nothing may be fitted across a refuel, and nothing could say where one run ended. A gauge reading at lap 21 and the same reading at lap 36 could not be told from one set read twice, so "was the last stint a fresh set or the tail of a 26-lap one" — two different findings — had the same representation. Runs come from the fuel channel and are therefore certain; `tyresFresh` is the driver's declaration and is `null` until he makes it, **never `false`**, which would claim the set carried over |
| 2 | `meta.compound` is emitted **only when one compound was run**; **new `meta.compoundsRun`** | It was the most common lap tag. A session that ran three compounds across five runs declared one, and two thirds of it lost a vote silently. The consumer reads a single compound as a single-compound session and picks the race tyre off it |
| 3 | `wear.byCompound[].compound`, `.stintsMeasured`, `.runIds`, `.confidence`; **export refuses a compound the session never ran** | A rate keyed by code could not be checked against a `meta` that speaks in full names, so three compounds' worth of rates sat beside a contradictory `meta.compound` and nothing caught it. `stints` is now how many runs were on that compound and `stintsMeasured` how many produced a rate: run three times and read once is a thinner claim than run once and read once |
| 4 | **Wear rates are computed inside one run**, and `wear.byRun` carries each with its method and what it assumed | The old rate divided one gauge reading by the laps of every run sharing a compound tag. On the Monza session that read a Racing Soft set consuming 17% a lap as 6.9% — an understatement of two and a half times, in the direction §5.1 of `CLAUDE.md` says costs most. Where the driver has not declared the set fresh, the rate still needs a starting point: `assumesFreshAtLap` says so and the confidence drops to `assumed` |
| 5 | **New `session.lapsExcludedDetail`** — `{lap, reason, source}`, `reason` ∈ `out-lap` \| `in-lap` \| `incident` \| `traffic` \| `fuel-implausible` \| `manual`, `source` ∈ `auto` \| `driver` | `notes` read "lap 2 struck by hand, lap 5 struck by hand…" eight times, which qualified nothing — and four of the eight were the out-laps after a refuel, which the fuel channel names for free. The flat `lapsExcluded` array is unchanged. `notes` now carries only what the structure cannot, such as the driver's own "spun at T4" |
| 6 | **Fuel plausibility gates lap validity** (§5) | A lap burning under half the session's median is a lap boundary inside a pit or garage transition, not a lap of the circuit. One such lap burned 0.16 L against a 6.57 L median, was counted, and became `bestLapMs` — 1.9 s clear of the fastest real lap, in the driver's own report. Skipped entirely when `fuelCapacityL` is 0: electric cars burn nothing and zero is a real value |
| 7 | `wear.byLapTime` gains `fittedRunId`, `fittedOverLaps`, `samples`, `fuelDeltaL`, `fuelNetted`, `runsDisagree`; **fitted inside one run, by Theil–Sen** | Fitted across five tanks, the sawtooth of a car getting heavier and then abruptly light again reads as a rising trend: +72 ms/lap was exported for a car that was getting faster. Fuel is **not** netted off — a full tank is worth more than the tyre signal and the coefficient that would net it is itself derived — so the raw slope goes out with the fuel burned over the same window. The estimator is the median of pairwise slopes, because least squares gave one un-struck incident lap enough weight to flip the sign |
| 8 | `wear.modelConfidence` is **computed**, not declared; **new `modelConfidenceBasis`** | It read `measured` while sitting above a fabricated `byCompound`, a wrong-signed `byLapTime` marked `low`, and a pinned gauge series. A section-level flag that overrides the per-field tags beneath it defeats the point of having them. It is now the weakest of the fields the model is **built from**, and the basis names them — and names `byLapTime`/`byTemp` as corroborating rather than feeding it, since those are `low` by nature and rolling them in would peg the field to `assumed` on every export ever made |
| 9 | **New `wear.wearMeasuredAtRaceMultiplier` and `wear.wearMultiplier`**; **new `wear.gaugePinned`** | Multiplier linearity is assumed and has never been demonstrated, so the multiplier a rate was taken at travels with the rate. A gauge that has not moved between two readings is either saturated or reading a set that was changed in between; either way no rate is taken through it, and now it says so |
| 10 | `gearing.matchesSheetCovers`, `finalGearSheet`, `finalGearVsSheetPct`, `rollingRadiusImpliedM`, `limiterGear` | `matchesSheet: true` sat beside a `fittedFinalGear` of 3.665 against a sheet of 3.550 and asserted incompatible things. The derivation is **not** inverted: GT7 broadcasts the **unloaded** tyre radius (a constant 0.355 m on this car), and the rolling radius implied by the sheet's final drive is 0.3438 m — a 3.2% loaded deflection that accounts for the whole gap. That bias is larger than one final-drive step, so the final drive cannot be range-checked this way; the two figures and the gap between them are given instead, and `matchesSheetCovers` states plainly what the boolean does and does not cover. `limiterGear` stops `observed-at-rev-limiter` beside `topGearReachedLimiter: false` reading as a contradiction |
| 11 | **`gearing.gearingConstantK` is now extrapolated to the limiter**, with `gearingConstantFinalGear`, `gearingConstantFinalGearSource`, `gearingConstantSamples`, `topGearSpeedAtLimiterKph` | K was omitted whenever the limiter did not fire in top gear, which on a circuit like Monza is most sessions — so the field the tune builder most wants was never exported. Scaling the observed top-gear speed to the limiter is sound; the source string distinguishes `extrapolated:` from `computed:` so the two are never confused. **K uses the sheet's final drive, not the derived one** — the derived figure carries the unloaded-radius bias and a K built on it would put every future gearbox out by the same few percent |
| 12 | **`meta.gameVersion` is required.** Export refuses without it | GT7 rewrote its physics, tyre model and geometry in 1.49 and again in 1.55. A measurement that does not say which update it was taken under cannot be filed and cannot safely be compared with the next one. It costs one field on the event page, which now exists |
| 13 | **`corners` is emitted for the first time** (§7), and `corners[].flagLaps` / `.flagThresholdLaps` are new | The section the contract calls the one to build if only one gets built had never once been exported, and the reason was upstream: what the recorder stored as lap distance was the **road plane's fourth coefficient** — about −80 to −250 m, covering 125 m over a whole lap of Monza — so corner detection could never segment a lap. GT7 broadcasts no lap-distance channel at all; it is now integrated from speed against the packet clock. `flags` was a set union across laps, so with enough laps every corner carried every flag; a flag now has to fire on a quarter of them, and `flagLaps` keeps the one-offs visible as one-offs |
| 15 | **Fresh sets are read off the stream**: `runs[].tyresFreshDeclared` / `.tyresFreshObserved` / `.tyresFreshDisagreement`, `wear.byRun[].method` names which source established the set, and `derived.thresholds.freshTyreTempC` restates the constant | GT7 broadcasts no tyre-change event, so the app could only ask. It turns out it does not have to: **GT7 fits every set at one temperature on all four corners**, measured at 70.0 °C across three compounds in the 11 Aug captures, and a stationary set only cools from there. The evenness is the discriminator - a set that has turned a wheel carries asymmetry within a lap. The driver's own declaration still outranks it, and where the two disagree the disagreement is reported rather than resolved |
| 16 | `wear.gaugePinned` fires **within one run only** | Two equal readings on two different sets are two sets that came off equally worn, which is a coincidence and not a finding. Before `runs` existed the two cases were indistinguishable, and the 11 Aug session's 84% at lap 21 and 84% at lap 36 - the very reading P6 raised - was reported as a gauge that had stopped moving. It was a new set |
| 17 | **New `strategy.raceLength`**, and `strategy.plan.laps` | A timed race and a lap race are different objects, and the payload said the same thing for both. For a race run to the clock the distance is an **output of the plan**: every stop is time spent stationary while the clock runs, so it is paid for in laps rather than seconds. Modelled as a fixed lap count, a 50-minute race came back as a **52-minute plan** - which is not a slow plan but an impossible one, since the flag falls at the first line crossing after the clock and the race can last at most the limit plus one lap. `maxDurationS` states that ceiling so a reader can check any plan against it |
| 18 | **Wet compounds are never planned on**, and `compoundProfiles[].longestStintLaps` is new | GT7's weather cannot be known before the race and no wet running has ever been done, so a stint on Intermediates rests on nothing - and it *won*, because a compound with no profile inherits the reference's rate and is costed as though it were the measured one. They stay declared as available to the driver, who can still call for them; they are not a strategy. `longestStintLaps` is the third ceiling on a stint alongside the tyre and the tank: `0.85 / w` will extrapolate a stint nobody has ever completed, and when the rate behind it was understated that is exactly what it did |
| 19 | **`compoundProfiles[].wearConfidence` and `.deepestObservedFrac` are new, and together they can lift the evidence cap** | `source` reads `measured` for any rate that exists at all, so a rate from two gauge readings inside one run and a rate from one reading over a set merely *assumed* fresh arrived indistinguishable - and the second is the one that proposed a twelve-lap stint on a set that never went past four. `wearConfidence` separates them. `deepestObservedFrac` is the load-bearing half: CLAUDE.md §5.1 makes wear piecewise, near-flat to about half worn and progressive after, so a rate fitted entirely inside the flat opening and run out to 85% crosses a boundary nobody has watched. Where the rate is `measured` **and** the gauge saw the set past 50%, `0.85 / w` is continuing an observed curve rather than projecting an unobserved one, and the longest-stint-ever-run ceiling no longer applies. Fuji is both cases in one weekend: two six-lap practice runs read once each to 24% held the cap at six laps and were right to; nineteen readings across two sets watched to 56% lift it, and a 20-lap race becomes the one stop the tank forces rather than the three the longest previous run implied |
| 14 | `derived.thresholds.flagMinShareOfLaps` | Same rule as every other threshold: it is the app's choice, not the game's, so retuning it must read as a change in the detector rather than a change in the car |

**The frame clock was GT7's in-game clock.** Not a payload field, but it reached every
millisecond in `corners`: `t_ms` came from `time_of_day_ms`, which is frozen in a
fixed-time event and runs at many times real speed in a day-to-night one. Laps came
out spanning 0 s or 970 s where the lap took 110. Trail-brake duration, time loss and
consistency were all scaled by whatever multiplier the event happened to use. The
clock is now the packet counter at a known 60 Hz.

**Laps recorded before 1.4 are repaired on read**, not re-recorded: lap distance is
integrated from the stored speed channel and the clock rebuilt from the frame index,
so a session captured last week yields corners without being run again. The integrated
distance lands within about a percent of the circuit's published length and does so
consistently lap to lap, which is what corner windows need.

### 16.4 → `1.5`

**This is the version where the validator caught up with the contract.** The
audit that produced it found 37 constraints this document states and the
validator did not check, and 15 keys the app was shipping that the document did
not define. A constraint nobody enforces is a comment, and an undeclared key
has to be read conservatively by a consumer who cannot tell an addition from a
rename — which is what §1 says this format exists to prevent.

| # | Change | Reason |
|---|---|---|
| 1 | **No field may fall back to a placeholder.** `meta.packet` no longer defaults to `"A"`, and `meta.car` / `meta.circuit` no longer to `"unknown"`. Where the app has no value the field is `null` and the export refuses | `"A"` is a positive, well-formed claim that the 296-byte base set was captured, and it satisfied the validator's own enum check — so every absent extended channel read as *physically unavailable* rather than *not measured*, which is the exact ambiguity §2 exists to remove. Press Record with GT7 not streaming and that was the payload. `"unknown"` is at least visibly not a car name; both defeated the refusal gate they were sitting behind |
| 2 | **`session.fuelCapacityL` is the first *plausible* capacity across the event's runs, never the first present one.** A `0` is emitted only where a car genuinely has no tank; where every run read 0 it is `null` and `notes` says why | GT7 reports 0 both for an electric car and for a packet that arrived before the car had loaded. A session that opened on the second stored 0.0 and beat the 100.0 four later runs measured, so the payload asserted an electric car whose own `laps[]` burned 7.28 L each — **and silently switched the 1.4 lap-validity gate off for the whole event**, since fuel plausibility is skipped on a capacity of 0. It also removed the fuel constraint from every race plan, so `bindingConstraint` could never be `fuel`. Zero stays a real value; what changed is that it is no longer *inferred* from a zero |
| 3 | `meta.carCategory` is the contract's vocabulary (`Gr.3`), mapped from GT7's raw token (`GR3`) at the export boundary, and the validator checks it. `Gr.X` and `Gr.N` join the enum | The consuming tool's per-car library is keyed on `Gr.3`. `GR3` is not a car class it knows, and nothing checked. The stream reports the N-class as a group rather than as a number, so `Gr.N` cannot become `N500` here — the PP that would decide it is not in the packet |
| 4 | **`derived.steerRotationDeg` is the full lock of the exported channel — 180° — not the driver's 1080° rim setting**, and new `derived.steerRotationSource` says so | `wheelRotation` is GT7's in-game wheel and saturates at ±π whatever the rim is set to. A reader given `steerPeakDeg: -67.47` against 1080 computes 12.5% of lock; `steerPeakNorm: -0.375` says 37.5%. §7 pairs the two fields precisely so degrees can be scaled, and this was the wrong scale by a factor of three. Nothing ever assigned it |
| 5 | **New `derived.observedMinHeightMm`**, beside `bottomingRefMm`, and `bottomingRefSource` now names the set the reference came from | `CLAUDE.md` 3.3 fact 3 asks for two quantities — a steady-state reference *and* excursions toward the observed minimum — and the app published one. The source string also said "counted laps" while the reference was built from the diagnostic set, counted **plus incidents**: an off compresses the suspension below anything a clean lap reaches, so one incident lap set the floor every `bottoming` flag was judged against. It is now the counted laps only, keyed per setup sheet, with the incident laps held out |
| 6 | **`strategy.assumptions.refuelRateLps` is what the plan was costed with**, and new **`refuelRateSource`** says whether it was measured, declared, or still the app default. A race export is refused on an unconfirmed default | The event column was written over the top of the plan's own figure, so a plan whose every stop was costed at a measured 3.0 L/s exported the driver's typed 1.0 beside it, and a reader re-derived a 100 s stop for a plan that assumed 33 s. The 1.2 refusal for a missing rate could never fire — the column is `NOT NULL DEFAULT 2.5` — so the case it was written for, the app's own default standing in for a measurement, shipped in silence. At ~1 L/s measured against 2.5 that is a 2.5x error in the stop count |
| 7 | **New `wear.modelledStintCompound`**, required whenever `byCompound` names more than one | `modelledStintLaps` was whichever run happened to be last, with no compound attached: **26 laps** off a Racing Hard rate on a session whose Racing Soft rate gives 4. A driver planning 26 laps who fits softs runs six times past the cliff, which §5.1 of `CLAUDE.md` calls the expensive direction |
| 8 | **`wear.byRun[].confidence: "measured"` is refused where `method` names the temperature-observed fresh set** | §6.1 makes `measured` conditional on two gauge readings inside one run, or on the driver's own declaration, and on nothing else. A set called fresh because its opening temperatures fell in a band the app chose is an app-side heuristic: four of six runs on the 11 Aug Monza data carried `measured` on exactly that, which promoted the whole payload to `modelConfidence: "measured"` |
| 9 | **New `wear.byTemp.samples`** | Standing rule 4. The trend shipped with no sample count at all |
| 10 | **New `wear.byLapTime.estimatedFractionSource`**, required beside `estimatedFractionAtEnd` | `phase` and `estimatedFractionAtEnd` are the driver's last gauge reading from anywhere in the session, published under `source: "lap-time-model"` — where they read as an output of the fit |
| 11 | **New per-metric sample counts on `corners[]`**: `brakePointSamples`, `trailBrakeSamples`, `steerPeakSamples`, `throttleOnSamples`, `upshiftRpmSamples` | `samples` counts the laps that reached the corner; a mean is only over the laps that carried the channel. The shipped export carried `upshiftRpm: 7787` under `samples: 23` beside `shiftsInCorner: 0.09` — two laps' evidence presented as twenty-three, and §7 asks the reader to compare that figure against `gearing.limiterRpm` to judge short-shifting |
| 12 | **The keys the app was already shipping are specified rather than dropped**: `meta.practiceIntent` / `.practiceMode` / `.rehearsal`, `setup.purpose`, `runs[].tyresChangedAtStop`, `wear.byRun[].wearPerLapUnavailable`, `wear.byCompound[].wearPerLapUnavailable`, `wear.byLapTime.fuelNettedNote` / `.degradationUnavailable` / `.runsDisagree`, `derived.incidents` and `derived.thresholds.incident*`, `strategy.assumptions.mandatoryStops`, `strategy.raceLength.startHour` / `.timeMultiplier`, `strategy.compoundProfiles[].paceBasis` | Several are genuinely useful; the defect was that they shipped undeclared. `wearPerLapUnavailable` in particular is the sentence §8 requires beside a null rate |
| 13 | **The validator refuses an undefined key at any depth** | The fifteen above arrived one at a time and none announced itself. This is what stops the sixteenth |
| 14 | **§13's prohibitions are all walked, not just `"tow"`**: `oilTemp`, `waterTemp`, `boost`, `tyrePressure`, `caster`, `brakePressure`, a high/low-speed damper split, GPS, and any key naming an rpm or trace **series** | The middle four are what `CLAUDE.md` §4.8 names as proof a heuristic was pattern-matched from a simulator that is not GT7, so they are the ones most worth refusing automatically. The rpm prohibition is on the shape, not the word: the three named rpm scalars are still exported |
| 15 | **The `session` section is validated for the first time.** Required keys; `lapsRun` and `lapsCounted` cross-checked against `laps[]`; `lapsExcluded` against the laps marked invalid; `bestLapMs` must be the time of a counted lap; `lapsExcludedDetail[].reason` / `.source` enums | Nothing here was checked at all, which is how a lap boundary inside a pit transition became `bestLapMs` 1.9 s clear of the fastest real lap, and how a `fuelCapacityL` of 0 sailed through above laps burning 7.28 L each. The two sections are built by different code and agree only by accident unless something says they must |
| 16 | **The `gearing` section is validated for the first time**: every source string must agree with the field it describes, `matchesSheetCovers` is required beside `matchesSheet`, `limiterRpmSource` must match the presence of `limiterRpm`, `gearingConstantSource` must begin `computed:` or `extrapolated:` | The section audited clean field by field and was checked by nothing. `matchesSheet: true` beside a contradictory `fittedFinalGear` was defect 1.4/10 and the validator could not see it |
| 17 | `strategy.raceLength.finishAtS <= maxDurationS` is enforced; `plan.stintLaps` must sum to `plan.laps`, and the stint count must match the stop count | **The one invariant §10.0 exists to state**, and it was not checked. A plan past `maxDurationS` is not a slow plan, it is an impossible one |
| 18 | `runs[]` must be contiguous, not merely non-overlapping | Only the overlap was refused, so a lap belonging to no run passed — and every rate in `wear.byRun` is computed inside a run, so those are laps nothing can be measured over |
| 19 | Further enforced: `wear.byRun[].method` / `.confidence` enums, `assumesFreshAtLap` where the rate rests on an assumed fresh set, a null `wearPerLap` needing its reason, `runId`s pointing at runs that exist, `stintsMeasured <= stints`, `byLapTime.samples >= 5` with a named `fittedRunId`, `byLapTime.phase` enum, `compoundProfiles[].source` enum | Each is a sentence this document already contained and nothing tested |

**Setup values are refused where GT7 could not accept them.** Not a payload
change — a change in what reaches the payload. Camber, ride height, natural
frequency, ARB, dampers, LSD, downforce, top speed and final gear are entered
in GT7 as magnitudes; only `toe_f`, `toe_r` and `bb` take a sign. The prompt's
own return-shape example asked for `cam_f: -3.2` for two versions, which is
−32 clicks on a slider whose minimum is 0.0 — a position the driver cannot
enter, arriving in the one section of the payload that has no telemetry behind
it to contradict it. `SetupSheet.validate()` now refuses it and the prompt no
longer asks for it.

### `gt7-pitcrew/1.6`

**One value, and it exists because the app told the driver the wrong reason for a
three-stop race.** `stint_limit()` weighs three ceilings — the tyre, the tank, and
the longest stint on record — and the plan is laid out against the lowest. The
constraint it *reported* came from a different function that weighs only the first
two, so a plan capped by inexperience could only ever describe itself as tyre- or
fuel-limited.

| # | Change | Reason |
|---|---|---|
| 1 | **`strategy.bindingConstraint` gains `evidence`** | Fuji, 24 Aug 2026: RS wear of 0.04115/lap gives a tyre ceiling of 20.7 laps and the tank gives 15.4 — both longer than the 20-lap race — while the longest RS stint on record was 6. Evidence bound every stint, the optimiser produced four of them, and the approved plan exported `bindingConstraint: "fuel"`, which its own numbers refute: 20 laps at 6.507 L/lap into a 100 L tank needs one stop, not three. The app then priced that plan 50 s slower than the one-stop candidate it replaced and briefed it anyway. The two readings demand opposite driving — *fuel-limited* means staying out is not available, *evidence-limited* means nobody has tried yet — and the driver, told the first, correctly acted on the second: he ignored two box calls, ran to the flag, finished P5. A consumer that reads `fuel` here concludes the car is fuel-constrained and starts trimming for economy, when the finding is that the practice programme never ran a long stint |

### `gt7-pitcrew/1.7`

**Four fields the app was already emitting and the contract then refused.** The
Fuji sheet of 24 Aug 2026 is the first setup record in this project's history read
off the car's own settings screen rather than transcribed from a plan, and it
carries the whole build block that screen shows. The export refused it on four
undeclared keys — so the one verified sheet could not be exported at all, which is
the refusal gate working correctly against a contract that had fallen behind.

| # | Change | Reason |
|---|---|---|
| 1 | **`setup.build` gains `drivetrain`, `weightBalance`, `torqueKgfm` and `displacementCc`** | None is derivable from `values`, and each changes what a recommendation should say: an MR car at 43:57 and an FR car at 57:43 do not want the same answer to the same mid-corner complaint. `drivetrain` matters most — the app had no drivetrain field anywhere on file, so every diagnosis that depends on which axle drives was being made without it. All four are null wherever the sheet does not record them, which is the ordinary case for a sheet typed from a plan rather than read off the screen |

### `gt7-pitcrew/1.8`

**The app stopped claiming to know what is in the car.** The setup record was
wrong in five consecutive sessions and every one of them was caught by the driver
mentioning it in passing, never by the app. The answer is not a better check: it
is that two copies of a setup existed at all. The tune builder holds the car and
the gearbox now, issues changes directly, and the driver confirms them against
GT7's own settings screen — one place a setup value lives, and it is not here.

| # | Change | Reason |
|---|---|---|
| 1 | **`setup` is retired (§3).** Never emitted; still declared, and readers must still accept it | The archive holds exports back to 1.0 that carry it, and a reader that rejects them loses the history. What changes is that nothing new will carry one — so a consumer must not read an absent `setup` as "the app failed to record it". It is not recorded anywhere in this app by design |
| 2 | **`setup.driverChanges` goes with it** | The mid-session change ledger was a second record of the same thing, keyed to sheets that no longer exist. A change to the car is now recorded where the car is recorded |
| 3 | **The export no longer refuses on an untrustworthy setup record** | The rank-zero gate existed because an export is where a wrong premise becomes a knowledge base's permanent learning. There is no longer a setup record to distrust, so the gate has nothing to weigh — and `acknowledge_setup_doubt` is gone with it. **The question has not gone away**; it has moved to the side that can actually answer it, which is the one holding the sheet and the screenshot |
| 4 | **`gearing` keeps every field and several are now always `null`** | `matchesSheet`, `finalGearSheet`, `finalGearVsSheetPct` and `rollingRadiusImpliedM` all compare the fitted box against a stated one, and there is no stated one. They report `null` — *not measured*, which is what the tri-state was built for — rather than being dropped. `fittedRatios`, `limiterRpm` and `gearboxChangedMidSession` are read from the packet and are unaffected. `gearingConstantK` now always falls back to the derived final drive, which reads a few percent high through GT7's unloaded tyre radius; `gearingConstantFinalGearSource` says so, and it always said so |
| 5 | **`rangeRecord` is untouched, and that is the distinction worth stating** | It looks like a setup section and is not. A range record is the car's own slider limits, read off its settings screen once and never re-entered — it is what makes reasoning in percent of range possible at all, and it outlives every sheet ever run on the car |
