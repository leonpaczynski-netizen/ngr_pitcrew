# Pit Crew Detector Audit — what the flags actually measure

**Opened 17 Aug 2026** after the Watkins Glen Long race (Huracán GT3 '15, P1 from P5).
**Why this file exists:** two detector flags have now driven real setup changes on this car, and the arithmetic in this file says both flags measure something other than what they are named. A flag that fires on physics rather than on a fault is worse than no flag, because it survives every revision and keeps buying changes.

**Scope:** `gt7-pitcrew` packet formats 1.4 / 1.5, detector `derived.thresholds.detectorVersion: 3`.

---

## 1. `bottoming` — it fires on body roll, and the reference guarantees it

### The rule as shipped (v3)

> `bottomingRefRule`: *"lowest suspension height on straight-line frames — outside every corner window and under 5% of lock"*
> `bottomingBandMm: 3.0` · `bottomingMinMs: 50` · flag if a wheel sits ≥3 mm below that reference for ≥50 ms.

### The defect

**The reference is taken at the fastest point of the lap, which is also the point of maximum aero load.** Every corner on the circuit is slower, therefore less loaded, therefore the car sits *higher* in a corner than it does on the reference frames. A per-wheel test against that reference then flags the loaded wheel of any car that rolls — while the car as a whole is above its own reference.

### The arithmetic that shows it

Watkins Glen Long, 17 Aug 2026, 17 counted laps, Huracán GT3 at 68 / 75 mm. Mean of the four corner minima against the four reference heights (positive = lower than reference):

| Corner | FL | FR | RL | RR | **mean heave** | flag |
|---|---|---|---|---|---|---|
| T1 | −13.10 | +0.92 | −4.75 | +3.41 | **−3.4 mm (higher)** | 4/17 |
| **T2** | +18.46 | +13.00 | +23.86 | +9.47 | **+16.2 mm (lower)** | **17/17** |
| T3 | −22.42 | −5.19 | −14.93 | +1.23 | −10.3 mm (higher) | 0 |
| **T4** | +5.56 | −28.60 | +7.71 | −17.63 | **−8.2 mm (higher)** | **17/17** |
| T5 | −12.20 | −6.38 | −6.66 | −3.29 | −7.1 mm (higher) | 0 |
| T6 | −18.71 | +1.88 | −6.60 | +4.87 | −4.6 mm (higher) | 3/17 |
| **T7** | +6.56 | −18.71 | +5.29 | −13.27 | **−5.0 mm (higher)** | **17/17** |
| **T8** | +2.74 | −18.81 | +5.65 | −16.38 | **−6.7 mm (higher)** | **17/17** |
| T9 | −17.83 | −7.63 | −4.60 | +1.06 | −7.3 mm (higher) | 0 |

**T4, T7 and T8 flag `bottoming` on every single lap while the car is sitting 5 to 8 mm HIGHER than its own straight-line reference.** One side is down 5–8 mm and the other is up 13–29 mm. That is not floor contact. That is a car rolling in a right-hand corner. All three are right-handers (`steerPeakDeg` positive).

**T2 is the only corner on the circuit with genuine four-corner heave** (+16.2 mm), and T2 is the corner the driver deliberately rides the kerb at — 13.7 % of the corner on kerb, `kerb-strike` 17/17, 64.3 % peak brake, zero trail brake. A car going over a kerb under heavy braking compresses. That is the kerb, chosen on purpose, not a ride-height fault.

### What it already cost

`setups/2026-08-17-huracan-watkins-glen-long-revC.md` §0.2 called this *"unambiguous… a height in millimetres against a properly-defined reference, not a heuristic"* and **overrode the driver's silence on it** (§3.4) to raise the car +5 mm front, +3 mm rear. That is the only place in the project where telemetry has been trusted over an explicit driver report, and the flag it rested on cannot distinguish roll from contact.

**Consequence of the raise:** rake went from the +9 mm the car had raced at Rev A to +7 mm. It won anyway, so it is not being put back — but the reason for it is withdrawn.

### The falsification test that already ran

Raising the car 5 mm and adding 60 points of downforce should reduce arch contact and increase measured compression. Measured T2 depth **doubled**:

| | Rev A/B blend, 63–65 / 72 mm | Rev C, 68 / 75 mm |
|---|---|---|
| FL | 9.13 mm | **18.46 mm** |
| FR | 6.48 mm | **13.00 mm** |
| RL | 9.04 mm | **23.86 mm** |
| RR | 5.46 mm | **9.47 mm** |

**The flag got worse when the car was raised.** A contact detector cannot do that. A compression detector must.

### The fix Pit Crew needs

1. Take the reference **per speed band**, or normalise it for dynamic aero load, so a corner is compared against what the car would sit at *at that speed*.
2. Report **mean heave across the four wheels** alongside the per-wheel minima. Roll cancels in the mean; contact does not.
3. Exclude frames flagged `kerb-strike` from the bottoming test, or report the two separately. A kerb is a road input, not a setup fault.
4. State that `bottoming` is inferred. The packet already says GT7 reports absolute height and not travel remaining — that disclosure should sit on the flag, not only in the thresholds block.

**Confidence: measured.** The table above is arithmetic on the packet's own numbers, no modelling.

---

## 2. `understeer-mid` — it orders almost perfectly by entry speed

### The rule as shipped (v3)

> Flag when steering rises ≥ 20 °/s while yaw rate < 0.6 × (0.116 × speed × steer° / 180 / wheelbase), held ≥ 100 ms.

### The structural bias

Expected yaw in that rule is **proportional to speed**. Achieved yaw for a car at its grip limit is `v/R`, and with `v²/R = μg` that is `μg/v` — **inversely** proportional to speed. So the achieved/expected ratio falls as `1/v²` for any car driven at the limit, whatever its balance. Unless downforce raises μ as fast as v², **a perfectly neutral car will flag understeer more at high speed by construction.**

The gain (0.116) was calibrated as a *median* over 154,714 frames across all speeds — so it is right at the median speed and wrong at both ends, in opposite directions.

### The evidence

Watkins Glen Long, 17 counted laps, sorted by entry speed:

| Corner | entry km/h | understeer laps | trail brake |
|---|---|---|---|
| T2 | 204.4 | **15 / 17** | 0 ms |
| T8 | 194.1 | **15 / 17** | 0 ms |
| T3 | 184.9 | 6 / 17 | 0 ms |
| T9 | 170.0 | **12 / 17** | 121 ms |
| T4 | 153.3 | 7 / 17 | 267 ms |
| T1 | 143.7 | 7 / 17 | 207 ms |
| T6 | 134.1 | **0 / 17** | 394 ms |
| T5 | 132.7 | **0 / 17** | 85 ms |
| T7 | 119.6 | **0 / 17** | 106 ms |

Near-monotone in speed, with **T3 the single outlier** — and T3 is the one fast corner taken with no brake and the least steering, i.e. barely a corner. A genuine front-grip fault would track *load*, not raw speed, and would not switch off completely below 135 km/h.

### The compounding errors already on file

- `understeerWheelbaseM: 2.516`, sourced *"assumed — the recorder does not store the packet's wheelbase"*. The Huracán's is ≈2.62 m. Expected yaw goes as 1/wheelbase, so the expectation is ~4 % high and the bias points **toward** reporting understeer. Flagged in Rev C §3.3, still unfixed.
- The driver has reported no understeer across **four** sessions on this car while the flag has fired at 6–7 of 9 corners in every one of them.

### The fix Pit Crew needs

1. Store and use the **packet's real wheelbase**. This is a one-field change and it has now been outstanding for two revisions.
2. Normalise the yaw deficit for speed, or calibrate the gain **per speed band** rather than as one median.
3. Report the deficit as a continuous magnitude, not a boolean. "How far short of expected rotation, in what units" is tunable; a lap count at 6 of 9 corners is not.

**Confidence: inferred, strong.** The `1/v²` argument is analytic; the ordering is measured; the wheelbase error is disclosed by the packet itself. What would confirm it: one session where a corner's flag count changes without its entry speed changing.

---

## 3. `wheelspin` — direction real, count still unusable (unchanged)

The packet now discloses it: `wheelspinWheels: "all four — GT7 broadcasts no drivetrain channel and none was declared… A front wheel light over a kerb under throttle reads as wheelspin on a rear-driven car."`

**The fix is one declared field: tell Pit Crew this car is MR / rear-wheel drive.** Outstanding since Rev B (14 Aug). Until then, wheelspin counts at kerb-heavy corners (Watkins Glen T2: 15/17 wheelspin, 17/17 kerb strike) are largely lifted front wheels.

Where the channel *is* usable: T5 (12/17 wheelspin, 0.4 % kerb) and T7 (9/17, 1.0 % kerb) — slow second-gear exits with essentially no kerb contact. Those are real.

**Confidence: measured (the limitation is stated by the packet).**

---

## 4. The `setup` / `performance` / PP block is stale — three sessions running

| Session | Packet reported | Actually run | Caught by |
|---|---|---|---|
| 14 Aug | ballast 70 kg @ −50 | 55 kg @ −25 | driver confirmation (Rev B §3.5) |
| 17 Aug (practice) | sheet "…race v1", Rev A values | two sheets, Rev A + Rev B | `gearboxChangedMidSession` contradiction (Rev C §3.5) |
| **17 Aug (race)** | **sheet "…race v1", Rev A values, ballast 70 @ −50, PP 738.66** | **Rev C: 68/75, 435/660** | **driver asked directly** |

**This is the highest-severity defect in the whole loop.** In the race post-mortem it would have produced a fully coherent, fully wrong diagnosis: it reports the low car with the trimmed rear wing, which is exactly the setup Rev C was written to replace. Every delta, every "as run" column and every ranked cost would have been computed against a car that was not on the circuit.

**Two consequences adopted as standing practice:**

1. **Never omit a key from a `gt7-pitcrew-reply` block for this app while this defect is live.** The contract says an omission is safe because *"Pit Crew already holds the sheet as run"* — it does not. **Re-assert every value on every sheet.** An omission reverts to v1.
2. **Confirm the sheet actually in the car before diagnosing**, in one line, every time. It is the cheapest question in the process and it has now been wrong three times out of three.

**Confidence: measured** (driver-confirmed, three occurrences).

---

## 5. Smaller packet defects logged this session

| # | Defect | Evidence | Severity |
|---|---|---|---|
| 5.1 | `gearingConstantK` computed with the **derived** final gear, not the sheet's | 291.7 × 1.055 × **3.66** = 1126.4 (reported) vs × **3.55** = **1092.5** (correct). The packet's own note says the derived final gear reads high through the unloaded tyre radius — and then uses it anyway. Same class of error as Rev C §3.2. | high — it drives gearbox changes |
| 5.2 | `callsMade[].accepted` is **false on all 14 calls**, including "Green, green, green.", "P3. 15 to go." and "Chequered flag." — and the driver *did* box one lap after the box call | The field defaults false and has no third state for informational calls. **The calls ledger is currently worthless as evidence about the model.** Needs `informational` / `offered` / `taken` / `declined`. | high — it is the only feedback channel on the strategy engine |
| 5.3 | Lap 1 fuel runs **upward**: `fuelStartL 49.94 → fuelEndL 93.56` | Recorder started in the pits. Total race consumption must be computed from lap 2 onward; the lap-1 figures are unusable. | medium |
| 5.4 | `fuelMap` is **null on all 20 laps** | The single cheapest field on the sheet, and the whole fuel model is expressed per map. Had to be recovered by asking the driver. | medium |
| 5.5 | `runs[].compound` **null on both runs** while `strategy.plan.compounds` says RS/RS | Wear rates cannot be attributed to a compound from the packet alone. | medium |
| 5.6 | "Burning 8 % under plan" (lap 7 call) is not reproducible | Laps 2–7 burned 6.115 L/lap against a plan of 6.214 — **1.6 % under**, not 8 %. | medium |
| 5.7 | `corners[].samples` = 17 for all nine corners, matching `lapsCounted` | The off-by-one seen last session is fixed. ✅ | resolved |

---

## 6. What this file changes in the knowledge base

- **`08-playbook-leon.md` A7** ("post-1.49 bottoming — raise 3–5 mm, ride height first") is **not** withdrawn. The 1.49 arch-contact problem is real and independently sourced. What is withdrawn is **using the v3 `bottoming` flag as the trigger for it.** A7 needs a driver symptom — *"bangs, then won't steer"* — or a mean-heave figure, not a per-wheel flag count.
- **`02-gt7-setup-parameters.md` symptom tables**: any entry keyed on "telemetry says understeer at N corners" should be keyed on the driver report plus a speed-normalised deficit instead.
- **Standing rule 7** (*"the driver report is primary evidence… where telemetry and the driver disagree, that disagreement is the finding"*) is **vindicated**. The one time it was overridden — Rev C §3.4 — the telemetry was wrong. Strengthen it: **a telemetry-only flag may not buy a setup change on its own; it may only buy a question or a measurement.**

---

*Opened 17 Aug 2026 · GT7 v1.70 · packet formats gt7-pitcrew/1.4 and /1.5 · detector v3*
