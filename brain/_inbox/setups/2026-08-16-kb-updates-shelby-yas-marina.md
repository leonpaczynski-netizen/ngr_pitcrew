# Knowledge-base updates — Shelby GT350R '16 @ Yas Marina, race, 16 Aug 2026

**Filed separately from the setup sheet, per `00-INDEX.md` standing rule 6.**
GT7 v1.70 · every item carries a confidence flag.

**Confidence vocabulary used here:**

| Flag | Meaning |
|---|---|
| ✅ **MEASURED** | Read from the game or from a telemetry channel. Act on it. |
| ✅✅ **MEASURED ×2** | Independently confirmed in a second session. Treat as settled. |
| ⚠️ **INFERRED** | Argued from evidence but not directly measured. **Needs a second event to confirm.** |
| ❌ **CONTRADICTED** | An existing knowledge-base claim this event disagrees with. |

---

## A. What to record about **this car** — Ford Shelby GT350R '16

### A1. ✅ MEASURED — slider ranges, and they are **not** the Gr.3 constant

**Add to `11-car-slider-ranges.md` as the third car and the first road car.** Read off
this car's own settings screen 13 Aug 2026, verified, and used on three sheets since.

**The finding the register was built to catch, and it sharpens the Gr.3 claim rather
than killing it.** Of 22 parameters, **13 match the Gr.3 cars exactly and 9 do not:**

| Truly universal — confirmed across Gr.3 **and** Gr.N | Chassis-derived — differs by car |
|---|---|
| ARB 1–10 · dampers 20–40 / 30–50 · camber 0–6 ° · toe ±1.00 ° · LSD 5–60 ×3 · brake balance ±5 · max speed 200–800 · final gear 2.000–5.000 | **ride height 75–160 / 95–180 mm** (Gr.3: 55–80 / 60–90) · **natural frequency 1.88–3.70 / 2.00–3.90 Hz** (Gr.3: 3.00–5.00) · **downforce 60–160 / 150–300** (Gr.3: 350–450 / 500–700) |

**Consequences:**

1. **The register's "Gr.3 class constant" hypothesis survives, in a better form.** The
   13 universal endpoints are now confirmed across two classes and three cars. Promote
   them from "confirmed ×2, both MR Gr.3" to **"class-independent."**
2. **The 9 chassis-derived ones are per-car and the spans differ enormously** —
   ride height span 85 mm here against 25 mm on a Gr.3 car, a **3.4× difference.** That
   difference is the cause of finding **D1** below.
3. **The natural-frequency floor is 1.88 Hz**, against the RSR's 3.00. This car can go
   softer than any Gr.3 machine and never has — it has run 3.05 / 3.20 Hz on all three
   sheets, which is 64% / 63% of its own range.
4. **+20 mm of rake is built into the minimums** (75 front / 95 rear), against +5 mm on
   the Gr.3 cars. Rake on this car must be quoted as rear-minus-front in mm.

### A2. ✅✅ MEASURED ×2 — gearing constant **K = 1,096 ± 1%**

```
  13 Aug   K = 1,101   from a limiter strike (8,856 rpm, gear 1, fg 3.600)
  16 Aug   K = 1,091   from 273.8 km/h at 8,152 rpm, 6th (1.019), fg 3.600
  Agreement 0.9%.
```

The second reading is from a **non**-limiter point — the harder case — and still agrees
inside 1%. **Promote from "measured, ±2%, one point" to "measured, ±1%, two independent
sessions."** Every Shelby gearbox from here is a calculation, not an iteration.
Rev A's original estimate of 1,035 was **5.6% low**.

### A3. ✅ MEASURED — the Rev B gearbox design was correct to within 1%

Predicted *"~8,200 rpm at 278 km/h in clean air, limiter only in a tow."* Delivered
**8,152 rpm at 273.8 km/h in 6th, limiter never fired.** 6th went from a ratio never
touched in seven laps to the gear that sets top speed. **First fully validated gearbox
design in this knowledge base.**

### A4. ✅ MEASURED — fuel, and the number to plan with

```
  Race mean, tank to flag   (100 − 1.79) ÷ 15  =  6.548 L/lap   ← plan with this
  Median lap                                   =  6.751 L/lap
  Unsaved race laps (2–12)                     ≈  6.80  L/lap   ← worst case
  Deliberate save, lap 14                      =  4.44  L/lap   ← 34% in one lap, measured
  Tank                                         =  100 L
```

**Against 7.563 L/lap planned — the model was 12% high** because it carried forward a
practice-pace figure with no saving in it. **Record a range, not a point.**

### A5. ✅✅ MEASURED ×2 — Racing Soft is the settled race compound

15 race laps, degradation **flat** (laps 11–12 as quick as laps 7–8), ~47% consumed at
the flag against a ~50% cliff. Second confirmation. **Close the compound question on
this car at this circuit — the harder-compound comparison is not worth practice time**
(the Laguna-measured RS→RH delta of 1.412 s/lap would cost 21 s over 15 laps to solve a
problem that does not exist).

### A6. ⚠️ INFERRED — the ride height on the sheet has never been tested and is probably wrong

80 / 98 mm is **6% and 4%** of this car's own ranges. See **D1** for the mechanism.
At the worst corner the rear-right uses **26.7 mm more suspension travel than it does in
a straight line**, with `kerb-strike` on 14 of 14 laps. **Needs one run at 89 / 107 to
confirm. This is the highest-value untested thing on the car.**

### A7. ⚠️ INFERRED — the front axle runs cold and the rear runs hot

Front means **70.4–75.0 °C** across fifteen race laps, against GT7's **70 °C fitting
temperature**. Rears **77.6–85.0 °C**. Front-to-rear asymmetry **−8.3 °C**. Front
locking on a tyre three degrees off cold is consistent. **No GT7 tyre working range has
ever been measured**, so this cannot yet be judged against anything — the export's
`windowC: [85, 110]` is real-world slick data and says so itself. **Needs the working
range measured before it means anything.**

### A8. ⚠️ INFERRED — the differential is still undiagnosed, and the evidence points **against** the change already made

Rev B took `lsd_a` 20 → 17 on the driver's verbatim *"both rears went together — a
snap"* (A5 failure mode 2 → lower). **The tyre-temperature data has never agreed, in
either session:**

```
  Lap  4   RR 141.4 °C  ·  RL  82.1 °C    ← 59 °C split, ONE wheel
  Lap 13   RL 132.4 °C  ·  RR  82.9 °C    ← 50 °C split, ONE wheel
  Lap 15   RL 151.2 °C  ·  RR  89.3 °C    ← 62 °C split, ONE wheel
```

**Three of the four spin laps show one rear wheel 50–62 °C above its pair** — A5's
*first* failure mode (inside rear alone → accel too LOW → **raise** it). The 13 August
temperatures had the same single-wheel character and were logged as generic slide
events without anyone noticing.

**Unresolved. `lsd_a` does not move until one observation settles it** (§E2). Note this
is now the *only* parameter on the car whose direction is actively contested.

### A9. ✅ MEASURED — build data for the profile

**606 bhp / 1335 kg, PP 575.47, ballast 109 kg at position 0, restrictor and ECU 100%.**
`07-car-profiles.md` and `08` E3 both record the car at **stock 525 bhp / 1,658 kg**.
Both figures are correct; the profile should carry them **labelled as stock vs as-raced**,
because every LSD and gearing inference in the knowledge base is against the 606/1335
build, not the showroom car.

---

## B. What to record about **this circuit** — Yas Marina Circuit (Full Course)

### B1. ✅✅ MEASURED ×2 — pit loss is **22.3 s**, not 20 s

19% of a measured 1:57.3 lap. The 20 s on the event page is the app default and has
been wrong on both briefs. **Fix the field.** Closes `08` G10 for this circuit.

### B2. ✅ MEASURED — first Gr.N lap-time reference here

**Best 1:57.318 · median 1:59.676 · spread 2,256 ms over 10 counted laps**, at
606 bhp / 1335 kg on Racing Soft, at night, in race conditions with fuel saving.
`05-track-reference.md` §1.25 gives Gr.3 at 1:52–1:56. **A road car of this build is
roughly 1.5–5 s off Gr.3 pace here.**

### B3. ⚠️ INFERRED, and now genuinely uncertain — which axle wears

- `05` §1.25 classifies Yas Marina as wearing **"Rear (traction)."**
- 13 Aug measured **front-limited** (18% F vs 13% R) and the knowledge base recorded
  that as a contradiction.
- **This session took no gauge reading at all**, so it neither confirms nor refutes.
- **But the thermal data says the rear is the harder-worked axle by 8.3 °C.**

**The wear axle and the thermal axle now disagree on this car.** Downgrade the 13 August
"Yas Marina wears the front on this car" finding from a measurement to **one
unconfirmed measurement**, and re-measure. It matters because it inverts the standard
in-race brake-balance migration.

### B4. ✅ MEASURED — the "5/5 braking severity" classification does not describe this car here

Only **2 of 10 corners** carry a meaningful brake application; **five are essentially
brake-free**. On a 606 bhp road car this circuit reads as a **traction** circuit, not a
braking one. ⚠️ **Caveat that matters:** see **D8** — brake pressure levels are not
comparable across app versions, so this is a *within-session ranking* of corners, not an
absolute statement about pedal pressure.

### B5. ⚠️ INFERRED — revised top three levers, for a **road car** at this circuit

`05` §1.25's current levers are written for Gr.3. For a Gr.N car:

1. **Platform compliance over kerbs** — `kerb-strike` at 8 of 10 corners, 14/14 laps at
   the hairpin.
2. **Slow-corner exit traction** — the hairpin is the single largest clean time loss on
   the circuit (447 ms/lap).
3. **Fuel** — binding in both sessions, and the only thing that has ever forced a
   strategy decision here.

### B6. ✅ MEASURED — the game clock runs at ×1 from 17:58

Measured over 19 laps. Race window `finishAtS` 1874.5 s, `maxDurationS` 1918.9 s.
**15 laps at 1:59.7; 16 laps at anything under 1:57.1.**

---

## C. What to record about **this combination** specifically

### C1. ✅✅ MEASURED ×2 — the defining fact, and it is a driver signature, not a car one

> **The fastest laps are the first clean ones. An incident then produces a permanent
> ~2 s/lap step-down that does not recover inside the session.**

```
  13 Aug (practice, Rev A):  1:54.823 on lap 1  →  never within 4 s again over 6 more laps
  16 Aug (race, Rev B):      1:57.318 on lap 3  →  spun L4 and L5
                             → laps 6–12 run 1:59.2–2:00.1, FLAT, for seven laps
                             → laps 11 and 12 as quick as laps 7 and 8
```

**Two sessions, two sheets, three days apart, identical shape.** There is no
degradation in either — laps 11 and 12 sit on tyres seven laps older than laps 7 and 8
and are the same speed. **The car does not fall off. The driver's confidence does, and
it does not come back.**

**This should be the first thing read before any future sheet for this combination.**
It reframes what a setup here is for: **the objective is not a faster lap, it is a car
that does not produce the incident that costs the next ten.**

### C2. ✅ MEASURED — Rev B halved the spread and cost 2.5 s of peak pace

| | 13 Aug, Rev A | 16 Aug, Rev B | Change |
|---|---|---|---|
| Best lap | 1:54.823 | 1:57.318 | **+2.5 s** |
| Spread | 5,081 ms | 2,256 ms | **−56%** |
| Off-track excursions | 6 in 7 laps | 4 in 15 laps | −69% per lap |
| Spins | 1 in 7 | 4 in 15 | roughly unchanged |

Roughly **0.3 s** of the 2.5 s is the fuel saving (10.7% under plan, at C3's ~0.5 s/lap
per 20%); the rest is race conditions plus, possibly, a duller car. **Consistency was
bought and something was paid for it.** `01` §4 forbids exactly that trade — *"a
'planted but slow' car that achieves stability by dulling the front axle"* — but the
race outcome (P5, finished, no stop, and a strategy that beat the model by ~52 s) is the
better result. **Record the tension; do not resolve it in either direction yet.**

### C3. ✅ MEASURED — no-stop is correct here, and the model is wrong about it

15 laps, **0 stops**, **13 declined calls, 13 correct declines**, finished with 1.8 L.
Two stops would have cost ~56 s against ~4 s of saving. **See D5.**

### C4. ✅ MEASURED — first fully validated gearbox and the first free driving change

The hairpin keeps its 1st-gear apex (62.7 km/h — 2nd would be 3,536 rpm) and gains a
2nd-gear exit, which was the design intent. **T4 can be taken entirely in 2nd on the
current box** (87.9 → 97.5 km/h = 4,957 → 5,499 rpm), removing a mandatory mid-corner
upshift from one of the two 14/14-wheelspin corners. **Costs nothing.**

### C5. ⚠️ INFERRED — TCS 1 has still never been run on this car

Specified by Rev B for the race, and TCS 0 went in the car. **The cheapest untested
change on the combination, aimed directly at the driver's stated biggest limitation.**

---

## D. Claims in the knowledge base this event **contradicts**

**This is the section the post-mortem exists for. Twelve items.**

### ❌ D1. `08` B1's ride-height rule — *"F: 3–5 clicks above car minimum, R: 5–8 clicks above minimum"*

**The single most valuable finding in this report.**

The rule is stated in **absolute clicks** and was written against Gr.3 cars, whose ride
height sliders span **25 mm front and 30 mm rear**. On those cars, 5 clicks is **20% of
the range**. On this road car, whose sliders span **85 mm at each end**, the identical
instruction produces **6%.**

> **The rule silently changed meaning by more than 3× when it crossed from Gr.3 to
> Gr.N, and it produced a car parked 5 mm off its front floor and 3 mm off its rear
> floor on 85 mm of adjustment.**

**And it is the exact mirror image of the error `11-car-slider-ranges.md` already
caught on natural frequency**, where a *percent-of-range* heuristic (70–80%) produced
absurd absolute values on a car with a high floor. **So the register's lesson must not
be over-generalised:**

| Parameter | Express as | Why |
|---|---|---|
| **Natural frequency** | **absolute Hz** | The floor varies hugely; percent-of-range gives nonsense |
| **Ride height** | **percent of range**, or mm scaled to span | The span varies hugely; absolute clicks give nonsense |
| Toe, camber | **absolute degrees** | Range is universal; percent hides the scalpel |

**Action: rewrite B1's ride-height line as percent of range, and add a standing note
that every heuristic in B1 must declare whether it is absolute or proportional.**
⚠️ **INFERRED** — the failure mode is argued from range arithmetic, not yet measured.
**One run at 89 / 107 confirms or kills it.**

### ❌ D2. Rev B §7's ride-height decision — contradicted by its own metric

Rev B declined to move ride height because *"minimum suspension heights at the worst
corner sit **13–16 mm above** the session's own bottoming reference."* The equivalent
figures this session are **11–27 mm below it**, on the same car at the same circuit
three days later with the ride-height sliders untouched.

**Either the reference method changed between app versions (likely — corner model
v1→v2, `detectorVersion` 3) or the 13 August conclusion was wrong.** ✅ **MEASURED**
that the two disagree; ⚠️ **INFERRED** which is right. **The 13 August ride-height
clearance finding cannot be relied on and should be struck.**

### ❌ D3. `05` §1.25 — *"Brake bias: one click forward"*

Contradicted for this car. Brake balance has sat at **0** for three sheets with no
forward move ever needed, and the **new** symptom is **front** locking (9 of 14 laps at
the heavy stop), which points the opposite way — toward **+1, rearward.** **Tag the
"one click forward" recommendation as a Gr.3 assumption.** ✅ **MEASURED.**

### ❌ D4. `05` §1.25 — *"LSD acceleration sensitivity: medium-high, 25–32"*

The car raced **17** and nothing in the data suggests 25–32 would be better. **This is
the second independent case for `08` A5.1's rule** — *never import a track's generic
diff guidance without checking the build it assumes* — and it arrives on the **opposite
build** to the first (unrestricted FR here, restricted MR at Laguna). **Promote A5.1
from "validated once" to "validated twice, across opposite layouts and opposite
builds."** ✅ **MEASURED.**

### ❌ D5. The strategy model's response to a fuel constraint

The model identified the binding constraint **correctly** (fuel) and then **planned two
stops**. In a **timed** race with **zero mandatory stops**, a stop is time stationary
while the clock runs, paid for in laps.

```
  Two stops           2 × (22 s pit loss + ~6 s refuel)   ≈ 56 s
  Saving 11% instead  ~0.27 s/lap × 15 laps               ≈  4 s
  No-stop wins by roughly 52 seconds.
```

**The model has no fuel-saving lever, so it reached for the only tool it has.** Two
further defects: the stint shape **7 / 3 / 5** is incoherent (a three-lap middle stint
in a fifteen-lap race serves nothing), and the lap-4 **"You can push"** was actively
wrong on a fuel-critical no-stop plan. **Also: "Green, green, green" at lap 0 should not
count as a declined call.** ✅ **MEASURED — 13 declines, 13 correct.**

### ❌ D6. `degradationMsPerLap` — an artefact for the second consecutive session

880.7 ms/lap on 13 Aug, **447.8 ms/lap** now. Both raw straight-line fits with fuel not
netted, both tagged `confidence: low`, both wrong. The lap times settle it: **laps 11
and 12 are as quick as laps 7 and 8**, on tyres seven laps older. What exists is a
**2.1 s step between lap 3 and lap 6** — exactly where the two spins are — then a flat
line.

> **A straight-line fit across a race containing incidents and a deliberate fuel save
> is not a degradation measurement and should not be emitted as one.** Fit only over a
> contiguous run of clean, non-saving laps, or emit nothing. ✅ **MEASURED.**

### ❌ D7. `fuelWeightSPerLPerLap: 0.003` — 0 for 2

The fastest lap came on lap 3 with 86 L aboard; on 13 August it came on lap 1 with a
full 100 L. **Twice now this car has been quickest on the heaviest tank.**
⚠️ **INFERRED** — confounded with fresh rubber and I cannot separate them from this
data. **But the coefficient is `derived-not-measured` and has never been checked.** §E6
settles it in twenty minutes.

### ❌ D8. `brakePeakPct` is not comparable across app versions

70.7% at the heavy stop on 13 Aug against a **38.0% maximum anywhere on the circuit**
on 16 Aug, with the same corner reading **7.8%** — and the driver confirming the pedal
was unchanged. Corner model v1→v2 (8 corners → 10) re-segmented braking events out of
their corner windows; `brakePointM` at the hairpin is **208.6 m** before the apex, far
outside any plausible window.

> **Consequence: Rev B's headline diagnosis leaned on 70.7% as proof the driver was
> holding a third of the pedal back. That corroboration is withdrawn.** The diagnosis
> survives on the driver's verbatim report, which was always the primary evidence.
> **`brakePeakPct` is a within-session ranking, never a level.** ✅ **MEASURED**, driver-confirmed.

### ❌ D9. The `bottoming` flag carries no information as emitted

It fired on **10–14 of 14 laps at 10 of 10 corners.** Its reference is the straight-line
minimum height with a **3 mm** band, and every loaded corner compresses past that by
construction. **The flag reports "this is a corner," not "this is bottoming."**

**Fix:** widen the band substantially, or express it as travel *used* against a per-car
travel figure rather than against a straight-line height. **A flag that fires everywhere
crowds out the ones that don't.** ✅ **MEASURED.** *(Note: the ride-height case in D1 is
built on the raw `suspHeightMinMm` magnitudes, not on this flag.)*

### ❌ D10. `wheelspin` over-reads on a rear-driven car

`wheelspin` fires on **14 of 14 laps at T9 — the best corner on the circuit** (57 ms
loss, 45 ms consistency, no braking). T9 also has `kerb-strike` on 9 of 14 laps, and the
detector's own threshold note warns: *"a front wheel light over a kerb under throttle
reads as wheelspin on a rear-driven car."* **The flag is measuring kerbs.** Until GT7
exposes a drivetrain channel, `wheelspinWheels` should be declarable per car on the
Event screen. ✅ **MEASURED.**

### ❌ D11. `compoundProfiles.RS.wearPerLap` — provenance is broken

The payload says both of these, and they cannot both be true:

```
  compoundProfiles[0]:  wearPerLap 0.03161, source "measured", 13 laps, 2 stints
  wear.byRun[0]:        wearPerLapUnavailable — "no gauge reading was taken on this run"
  wear.modelBasis:      "no stint length: no run carried a usable gauge reading"
```

`runs` contains **exactly one run of 15 laps**, not two stints of 13. And 0.03161 does
not equal 13 August's measured **0.02571** either. **Either the figure is carried
forward from a prior session — in which case its provenance must say so, and it
disagrees with what that session measured — or it is modelled and mis-tagged as
measured.** ✅ **MEASURED — internal contradiction.**

Two smaller ones in the same payload: **lap 1's `fuelStartL` 49.99 rising to `fuelEndL`
92.84 is physically impossible** (a garage-state artefact — the race started on 100 L),
and **`runs[0].compound` is `null`** on a session whose compound is known.

### ❌ D12. The export's `setup.values` block — third consecutive silent-wrong-value finding

| Session | Wrong | Caught by |
|---|---|---|
| 13 Aug | `ballastPosition` 20 against 0 | asking the driver |
| 13 Aug | compound RM recorded, RS run | driver mentioned it |
| **16 Aug** | **v1 sheet reported against a Rev B car — `lsd_a`, `lsd_b`, `top` and all 6 ratios** | `gearing.fittedRatios` disagreed |

**`gearing.matchesSheet` was emitted as `null`. It should have been `false`.** Doc 13's
acceptance-test question 1 — *"is the gearbox in the car the gearbox on the sheet?"* —
was fully answerable from this payload and the payload declined to answer it.

> **The structural cause: `setup.values` is a *sheet record* — what was typed into the
> app — presented in the same payload, with the same authority and no provenance tag, as
> `gearing.fittedRatios`, which is *read from the game*.** Everything else in this
> export carries provenance; this block claims none and has now been wrong three times.

**Two small fixes:** emit `matchesSheet: false` when it is false, and tag
`setup.values` with `source: "sheet-record"`. ✅ **MEASURED, driver-confirmed.**
**This is now the highest-value fix in the app.**

---

## E. What to measure next session

Ranked by value. Items 1–3 are ten minutes together and unblock everything else.

| # | Test | Closes | Confidence today | Time |
|---|---|---|---|---|
| **1** ⭐ | **The platform run.** 89 / 107 against 80 / 98, three clean laps each, same fuel. **Success criterion: five laps without a spin**, not a lap time. | **A6, D1, D2** — the largest untested assumption on the car, and `08` F1's own step 1, never run in three sheets | ⚠️ INFERRED | 10 min |
| **2** ⭐ | **The diff observation Rev B asked for and never got.** On any exit that steps out, watch the on-screen tyre indicators. **One rear alone → `lsd_a` 17→19. Both together → 17→15.** | **A8** — the only parameter on the car whose direction is actively contested, and the temperature data disagrees with the change already made | ⚠️ CONTESTED | 1 corner |
| **3** | **TCS 1 vs 0**, one run each. | **C5** — free, already on the sheet, aimed at the stated biggest limitation | ⚠️ untested | 5 min |
| **4** | **A tyre gauge reading at the flag.** Every wear number in the last two sessions is carried forward or modelled; this session took none. | **A5, B3, D11** — and it is the only wear input the app has | ✅ trivial | 30 s |
| **5** | **Front toe A/B: −0.05 / 0.00 / +0.05**, three clean laps each, Data Logger on. | **`08` G item 1** — top of the backlog since 10 Aug, never run on any car, and the front axle is now the one with the new symptom | ❌ open | 20 min |
| **6** | **Heavy vs light fuel.** Two three-lap runs on the same tyre age, one at ~90 L and one at ~25 L. | **D7** — settles the 0.003 s/L/lap coefficient and the "fastest on the fullest tank" pattern in one go | ⚠️ 0 for 2 | 20 min |
| **7** | **GT7's actual tyre working range.** Log surface temperature against lap time across a stint. | **A7** — the `windowC: [85, 110]` in every export is real-world slick data and describes no part of this game | ❌ never measured | free |
| **8** | **Slider step sizes on this car**, while a settings screen is open. | `11-car-slider-ranges.md`'s standing gap — still the only thing making click counts estimates rather than instructions | ✅ trivial | 5 min |

---

*Filed 16 Aug 2026 · GT7 v1.70 · from the Shelby GT350R '16 / Yas Marina race post-mortem (Rev C)*
*12 contradictions · 5 new measurements · 2 promoted to ×2-confirmed · 1 knowledge-base rule requires rewriting (D1)*
