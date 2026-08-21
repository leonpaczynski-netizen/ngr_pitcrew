═══════════════════════════════════════════════════════════════════
  PORSCHE 911 RSR (991) '17  ·  AUTODROMO NAZIONALE MONZA
  **REV B** — reissued from the 11 Aug practice session (36 laps, 28 counted)
  50 min · timed · 8× tyre / 3× fuel · 0 mandatory stops · refuel 1 L/s
  Issued 12 Aug 2026 · GT7 v1.70 · no BoP, open tuning · ranges verified 11 Aug
═══════════════════════════════════════════════════════════════════

---

# 🔵 PRE-1.71 — AND THIS SHEET IS NOW THE MOST VALUABLE CONTROL GROUP IN THE PROGRAMME

**Stamped 21 August 2026.** Built and run on **GT7 v1.70**. Update **1.71 (20 Aug 2026)** changed the physics — see `../16-update-1.71-physics-change.md` and `00-PRE-1.71-NOTICE.md`.

**Do not type this sheet into a v1.71 car as a setup.** But do not treat it as merely historical either: **this is the reference measurement for `../16` §12 Job 2A**, the RSR-at-Monza control run, and it is the best-instrumented pre-patch baseline the knowledge base has.

## Why this sheet specifically

`../16` §10 makes the point that a 10-lap post-patch run at Monza can be tested against a **distribution** rather than a single prior lap — which is a class of evidence nothing else here can offer. **The numbers that distribution is built from are in this document**, and several of them are unusually clean:

| Baseline (v1.70, 11 Aug 2026) | Value | Why it is the right probe |
|---|---|---|
| **Clean-air Vmax in 6th** | **278.7 km/h @ 8,009 rpm** (§3) | ⭐ **The rolling-resistance probe.** 1.71: *"Road surface resistance (rolling resistance) has been optimised."* Terminal speed on a drag-limited circuit is where that shows up loudest, and this is a clean-air, no-tow observation. |
| **Observed limiter** | **8,600 rpm** (§3) | Measured, not assumed. Should be unchanged — the RSR is not on 1.71's max-RPM list. **If it reads differently, something bigger happened.** |
| **Gearing constant K** | **1,128.3** (§3, §9.1) | Derived from the two above. **Rolling resistance moving invalidates it**, so this is a direct re-measurement. |
| **Fuel at 3×, map 1, no short-shift** | **6.566 L/lap**, independently confirmed at 6.571 on run 5 (§1.6, §9.3) | ⭐ **The fuel probe.** Rolling resistance is a fuel term. Two independent confirmations make this one of the most solid numbers in the knowledge base. ⚠️ *Note the no-short-shift condition — see the run-mode decision below.* |
| **RH at 8×** | **15 laps, no measurable degradation** (§5.1) | Gauge and stopwatch agreed. **10 laps on RH will not stress this** — which is the point: it isolates grip and resistance from wear. |
| **Degradation over 15 laps** | **−17.8 ms/lap raw; ~9 ms/lap true after fuel burn-off** (§1.5) | Effectively zero. A post-patch run that shows real degradation over 10 laps would be a large finding. |
| **Best clean valid lap** | **1:46.828** (lap 6, fresh tyres, 6.19 L) | ⚠️ Note §1.2 — the recorded 1:44.912 is a **timing artefact and is discarded.** Do not compare against it. |
| **Green reference lap** | **1:47.982** (lap 4) | The degradation datum. Sound. |
| **Median, 28 counted laps** | **1:49.180** | ⭐ **The pace probe** — and the median plus the spread is what makes this a distribution rather than a datapoint. |
| Front/rear and left/right wear split | FL 0.79 / FR 0.63 · RL 0.84 / RR 0.74 (§2.5) | Establishes **front-left and rear-left** as the limiting corners here. A change in which corner goes first is a steering-geometry signal. |
| Tyre temps, lap 36 | FL 74.5 · FR 68.3 · RL 85.7 · RR 82.6 (§2.1) | ⭐ **The heat probe.** 1.71 *"adjusted tyre heating values."* This is a full four-corner reading at a known point in a known stint — rare, and directly comparable. |

## ⭐ Run mode — short-shift, with a full-RPM tail

**Driver's call, 21 Aug 2026, and it is the right one.**

This session's documented numbers were recorded at **map 1 with no short-shifting**. But across the ~200-lap Monza history, **few laps were run at full RPM** — most were short-shifted, as at Watkins Glen. **The whole value of this run is the size of the comparison set, so match the dominant baseline, not the session that happens to be written up here.** Running full-RPM would compare against a thin slice and throw away the run's only real advantage.

Three things make that hold up:

- **Use the app's shift beep.** Short-shifting is a *driver input* — if the shift points wander, that is variance stacked on top of the physics delta you are trying to measure. The beep makes it repeatable, and **repeatability is what a controlled comparison needs, not optimality.**
- **⚠️ The beep's RPM points were derived against the old torque map, and 1.71 replaced it.** They may no longer be the *best* points. **That does not hurt this comparison** — as long as the beep fires where it fired before, the comparison is clean. It does make *"should I still be short-shifting there?"* a separate and genuinely interesting question, and it is logged as `../16` §11 item 17.
- **The Vmax reading is unaffected by the choice.** You reach terminal speed at full throttle in 6th at the end of the main straight regardless of how you got up through the gears. **The single most diagnostic number in the run does not care about run mode at all.**

**Then add 2–3 full-RPM laps at the end.** Five minutes, and it touches the documented **6.566 L/lap** and **1:49.180** references directly. **One run, both comparisons.**

> **This is Standing Rule 12's second clause arriving before the rule was ratified: *match the run to the dominant condition in the history, not to whichever session happens to be written up.*** The instruction that previously stood here — "drive it without short-shifting" — was written from this sheet's own conditions without checking what the wider baseline actually contained. **Superseded.**

## How to run the comparison so it is worth something

**Match the conditions, or the baseline stops being a baseline:**

- **Same multipliers — 8× tyre, 3× fuel.** The fuel and wear numbers above are meaningless against different ones. *(And per §5.1, confirm the tyre multiplier actually reads 8× — that check was never done.)*
- **Same sheet, confirmed on the car.** Job 0 for this car: read the settings screen against §4 **before touching anything.** If any value was clamped or reset by the patch, you are comparing two different cars. **Check front natural frequency first — it sits at 3.05 Hz on a 3.00 floor, five clicks, which makes it the cheapest clamp detector on the car (§4.1).**
- **Same compound: Racing Hard**, and the same assists — **ABS Weak, TCS 0**.
- **Same run mode as the bulk of the history — short-shift on the beep**, plus a short full-RPM tail. See above.
- **Confirm the wheel first.** 1.71 adjusted FFB, understeer vibration and Fanatec Auto Setup parameters. On an 18 Nm DD that reads exactly like a grip change and would be baked silently into the comparison.
- **Clean air for the Vmax reading.** 278.7 was a no-tow observation; a tow invalidates the comparison.

**Record, in this order:** driver report verbatim *before* looking at any number (Standing Rule 7) → Vmax in 6th and the rpm at it → median and spread over the 10 laps → sector times → L/lap, short-shift and full-RPM separately → four-corner tyre temps at a fixed lap → which corner's gauge is worst, and on which side.

> **The two most diagnostic single numbers are Vmax and the median lap.** If Vmax moved and the median did not, it is rolling resistance. If the median moved and Vmax did not, it is grip or geometry. If both moved, the sector times separate them — straights versus corners.

**Two things worth reporting the moment you feel them, before any number:** whether the **grip-to-slip transition** still feels as abrupt as `04` §1.2a describes (1.71's slipping-regime rework targets it directly), and whether the **kerb behaviour at the chicanes** changed (the damper attenuation change — §2.2, and it would be the first hard evidence anyone has on what 1.71 did to the bottoming floor).

## What on this sheet is at risk, and what is not

**At risk:** every slider value (§4) sits on ranges 1.71 revised — the **§4.1 range check is void**, and note it already flags front NF at 3.05 as *"five clicks off the floor"*, which is exactly the kind of value a moved range would clamp. The **LSD 5–60 scale** may now floor at 0. **Camber 1.0/1.0** is exposed to the steering-geometry rework. **Every strategy number in §5** rests on the 15-lap RH stint and the 6.566 L/lap figure, both of which this run re-measures.

**Not at risk, and this is most of the document's value:**

- **§1 in its entirety** — the data-integrity findings. `wear.byCompound` fabricating compound labels, `bestLapMs` accepting a 0.16 L lap, the `fittedFinalGear` contradiction, the pinned gauge series. **These are app defects, not physics**, and they will still be there in the next packet. **Read §1 before ingesting any post-1.71 Pit Crew export.**
- **§2.5's correction to `05-track-reference.md`** — Monza's front wear side is left, not right, because its three sustained corners are rights. That is circuit geometry and it does not patch. *(The correction still needs making in `05`.)*
- **§2.4's "two problems, three faces"** and the whole diagnostic structure.
- **§7 — what was deliberately left alone, and why.** The reasoning about not adding rear downforce to mask a diff problem is the Laguna trap stated in general form, and it is exactly the discipline the rebuild needs.
- **§5.2's pit arithmetic** — refuel time is linear at 1 L/s, so extra stops are pure added transit. Pit mechanics were untouched by 1.71.

> **⚠️ And the finding this sheet is proudest of is also its biggest warning.** §5.1 records that the knowledge-base wear model was **~5× too pessimistic** here, against 1.8× at Laguna — *"the same failure mode: a model built from generic per-circuit base rates, applied to a specific car, and never checked."*
>
> **The 15-lap measurement that corrected it is now itself a v1.70 number.** That is not a criticism of the measurement; it is the reason Standing Rule 10 exists. **A stale measurement treated as current is the same error as a generic model treated as specific — with better provenance and therefore more dangerous.**

---

# 0. The headline

**The setup is 95% right. The strategy was wrong by a factor of five, and that is the bigger finding.**

Three changes to the sheet — two sliders for the kerb bounce, one for the mid-corner
symptom. Everything else stands, and now it stands on measurement rather than on
estimate.

But the race this sheet was built for does not exist. Rev A was written around a
**four-to-eight-stop tyre race**. The session says:

> **The tyre does 15 laps at 8× on Racing Hards with no measurable lap-time loss.
> The tank does 15.2. Both stints fit inside one stop. `bindingConstraint = fuel`.**

That is a one-stop race, and it changes the compound call, the stop count, the fuel
plan and the wet-weather plan. §5 is rewritten from the ground up.

---

# 1. Data integrity — read this before the diagnosis

**⭐ 21 Aug: this section is unaffected by 1.71 and should be re-read before ingesting any post-patch packet. All four defects are app defects.**

You asked me to say where Pit Crew and your report disagree rather than average them.
There is more disagreement in this packet than usual, and one item is not a
disagreement but a **fabrication**. Taking them in order of how much they would have
cost if I had believed them.

## 1.1 ⛔ `wear.byCompound` is three RH runs mislabelled as three compounds

The packet reports wear rates for RS, RM and RH, each `"stints": 1`, each tagged
`"source": "driver-gauge"`. **The session ran Racing Hard throughout** — `meta.compound`
says so, your report says so.

I reconstructed the session's run structure from the fuel channel. The tank refills at
laps 5, 7, 11 and 22, which gives five separate runs. Computing worst-corner wear rate
for three of those windows:

| Window | Laps | RL gauge | Rate/lap | App calls it |
|---|---|---|---|---|
| Laps 1–10 | 10 | 0 → 0.69 | **0.0690** | `RS: 0.069` |
| Run 4 (11–21) | 11 | 0 → 0.84 | **0.0764** | `RM: 0.07636` |
| Run 5 (22–36) | 15 | 0 → 0.84 | **0.0560** | `RH: 0.056` |

Three exact matches to five significant figures. **The app took three Racing Hard runs,
computed a wear rate for each, and assigned compound labels to them.** Nothing about
RS or RM was measured in this session. Both rows are deleted from the record.

This is the one that mattered: a fabricated RM rate of 0.076/lap would have made RM
look like a 13-lap tyre and pulled the compound call the wrong way.

## 1.2 ⛔ The recorded best lap is not a lap

`bestLapMs: 104912` — 1:44.912, quoted in your report as the session best. That lap
consumed **0.16 L of fuel**. Every other lap in the session consumed 6.19–6.78 L.

A Monza lap that burns 2.4% of the normal fuel is not a Monza lap. It is a timing
artefact — most likely a lap boundary landing inside a pit or garage transition.
**1:44.912 is discarded.**

Your real reference pace, from laps that burned a full lap's fuel:

| | Time | Note |
|---|---|---|
| Best clean valid lap | **1:46.828** (lap 6) | 6.19 L, fresh tyres |
| Green reference | **1:47.982** (lap 4) | the degradation datum — this one is sound |
| Median, 28 counted | **1:49.180** | |

So the car is **~2 s slower** than the header claimed. Nothing else in the analysis
depended on it, but it would have flattered every subsequent comparison.

> **⭐ 21 Aug — and it would flatter the 1.71 comparison too, badly.** Comparing a post-patch
> median against a phantom 1:44.912 would manufacture a two-second "physics regression"
> out of nothing. **Compare against 1:49.180 median and 1:46.828 best. Not 1:44.912.**

## 1.3 ⚠️ `gearing.fittedFinalGear: 3.665` contradicts `matchesSheet: true`

The packet reports a fitted final drive of 3.665 against a sheet value of 3.550, and
simultaneously asserts the gearbox matches the sheet. Both cannot be true.

`fittedRatios` match the sheet to six decimals, so the individual gears were definitely
as written. `finalGearSource` is *"derived: rpm against wheel speed and tyre radius"* —
and tyre radius is assumed, not measured. A 3% radius error produces exactly this.

Worse, **3.665 points the wrong way.** Rev A §3.5 says a car going *faster* than the
table wants a *higher* final drive. This car went **slower** than the table. The
correction, if you wanted one, would be *downward*.

**I am trusting `setup.fg = 3.550`, and ignoring 3.665 entirely** — because there is a
better datum in the same packet. See §3.

## 1.4 ⚠️ The tyre gauge series is pinned and cannot be read as a wear curve

| Lap | FL | FR | RL | RR |
|---|---|---|---|---|
| 4 | 0.00 | 0.00 | 0.00 | 0.00 |
| 6 | 0.00 | 0.00 | 0.00 | 0.00 |
| 10 | 0.53 | 0.42 | **0.69** | 0.50 |
| 21 | 0.79 | 0.58 | **0.84** | 0.66 |
| 36 | 0.79 | 0.63 | **0.84** | 0.74 |

FL and RL read **identical at lap 21 and lap 36** — fifteen laps apart. A tyre that
consumed 84% in eleven laps does not consume 0% in the next fifteen. The gauge is
saturating, or the readings span tyre resets the packet does not record.

The series also straddles at least four run boundaries with no record of whether tyres
reset at each. I cannot tell whether laps 22–36 were a fresh set or laps 11–36 were one
26-lap set. Both readings survive the temperature evidence.

**Consequence:** I am not using the gauge as a wear rate. I am using it only for the one
thing it says unambiguously — *which corner goes first* (§2.3) — and I am taking stint
length from the stopwatch instead.

> **⭐ 21 Aug — the same discipline applies to the comparison run.** Take the stint length
> from the stopwatch, and use the gauge only for which corner goes first. **And note the
> upside: over 10 laps the gauge will not saturate, so a post-patch run may give a cleaner
> wear-rate reading than this baseline did.**

## 1.5 ⛔ `byLapTime.degradationMsPerLap: 72.1` has the wrong sign

The app reports 72.1 ms/lap of degradation, `phase: linear`. Run 5 is the cleanest test
available: fifteen laps, one continuous tank, one tyre set, laps 27 and 33 struck.

```
First half  (23,24,25,28,29)        109.544 s
Second half (30,31,32,34,35,36)     109.373 s
Least-squares slope over 11 laps     −17.8 ms/lap
```

**The car got faster as the stint went on.** Fuel burn-off (98.6 L, ~70 kg) is worth
roughly +0.3 s/lap from full to empty; netting that off leaves true tyre degradation of
about **9 ms/lap, i.e. 0.13 s across a 15-lap stint.** Call it zero.

72.1 ms/lap is not supported. The app tagged it `confidence: low` itself, correctly, but
`wear.modelConfidence: "measured"` sits above it and overstates the whole section.

> **⭐ This is a directly comparable baseline number and one of the best in the knowledge
> base: ~9 ms/lap true degradation on RH at 8× at Monza.** If the post-patch run shows
> materially more than that over 10 laps, **that is the wear change, measured, with a
> control** — and it would be the first quantified read on 1.71's tyre wear that anyone has.

## 1.6 ✅ What the packet got right

Credit where due — these were checked and they hold:

- `fuelUsedPerLapL: 6.566` — run 5 gives 6.571 independently. **Solid.**
- `modelledStintLaps: 15` — agrees with my read of run 5. **Right answer.**
- `byCorner.frontMinusRear −0.08`, `leftMinusRight +0.13` — both recompute exactly.
- `limiterRpm 8600`, `maxSpeedKph 278.7`, `maxSpeedRpm 8009` — the most valuable numbers
  in the file. See §3. **⭐ And now the most valuable numbers in the knowledge base for
  measuring what 1.71 did to rolling resistance.**
- `gearboxChangedMidSession: false`, `fittedRatios` — the box was as written.

## 1.7 What is missing, and it is the important section

**There is no `corners` array.** The ingestion spec calls it *"the section that actually
changes setups — if only one telemetry section gets built, build this one."* Without it
there is no `countersteer`, no `understeer-mid`, no `wheelspin`, no `kerb-strike`, no
`bottoming`, no per-corner `consistencyMs`, no `suspHeightMinMm`.

Concretely: **your kerb-bounce symptom has zero telemetry corroboration.** There is no
suspension-height channel in this packet. I am acting on your word alone for that one,
which is correct under standing rule 7, but you should know the confidence is
driver-only. The same goes for *which corners* the mid-corner symptom appears at — the
single highest-information thing I do not have.

Also absent: `meta.gameVersion`, `meta.cornerModel`, `derived.bottomingRefMm`, and every
`fuelMap` is `null`. And `format` declares `gt7-pitcrew/1.3` against a spec at 1.1 — I do
not have a 1.2 or 1.3 changelog, so I read the unfamiliar fields conservatively.

> **⭐⭐ `meta.gameVersion` missing is no longer a minor gap — it is now Standing Rule 10's
> single most important field.** Every packet from here must carry the game version, or a
> future session cannot tell a 1.70 packet from a 1.71 one. **Raise it with the app as a
> priority-one fix**, alongside the three export bugs in §9.

---

# 2. Diagnosis

Ranked by what it is costing.

## 2.1 ⭐ #1 — "Will not hold line on maintenance throttle"

**Corner phase: mid-corner, on throttle.** Cost: the largest single item — it is putting
you off the road several times a lap.

**Cause: LSD acceleration sensitivity too high. Playbook A5, third failure mode.**

The four diagnostic questions, answered from what I have:

**Where is your right foot?** On throttle. "Maintenance throttle" is unambiguous, and it
forks the diagnosis immediately. This is **not** the front-grip branch — front ARB,
front downforce and front toe are all the wrong answer here, and reaching for them is
exactly the Laguna trap that Rev A §7 pre-registered a warning about.

**What the temperatures say.** This is the strongest objective evidence in the packet,
and it is unambiguous.

| | Lap 23 | Lap 36 | Change |
|---|---|---|---|
| Front axle mean | 68.2 °C | 71.4 °C | +3.2 |
| Rear axle mean | 76.3 °C | 84.2 °C | +7.9 |
| **Rear minus front** | **+8.1** | **+12.8** | **+4.7** |

Within a single 15-lap stint the rear axle pulls **4.7 °C further ahead of the front**.
The rear is progressively taking over the cornering work — a rear axle slipping more and
more to generate the same force.

And the corner-by-corner picture at lap 36 is the giveaway:

```
  FL 74.5   FR 68.3      <- inside front (FR) is the COLDEST tyre on the car
  RL 85.7   RR 82.6      <- outside rear (RL) is the HOTTEST, by 11 °C over FL
```

Monza's three sustained corners — Lesmo 1, Lesmo 2, Parabolica — are all **rights**,
which load the **left** tyres. So RL is the outside rear and FR is the inside front.
**The outside rear is being scrubbed at 86 °C while the inside front sits cold and does
nothing.** That is a car being dragged around on its rear axle instead of steered on its
front, which is precisely what a diff with too much acceleration lock does under steady
throttle.

> **⭐ 21 Aug — this table is also the knowledge base's only four-corner temperature
> baseline, and 1.71 "adjusted tyre heating values."** `03` §3 and `04` §6.1 openly
> disagree about whether GT7's temperature model matters at all. **Repeating this reading
> at a fixed lap in the comparison run is close to a free answer to a question that has
> been open since both documents were written** — and it is `../16` §12 Job 6 arriving
> early and for nothing.

**Rev A already wrote down the answer.** §7's trap note:

> *If the car pushes wide at Lesmo or on the Parabolica exit, ask where your right foot
> is before touching anything. On throttle → **LSD acceleration sensitivity down,
> 16 → 14.** Not front ARB, not front downforce.*

The symptom matched the pre-registered branch. **Taking the pre-registered value: 16 → 14.**

> **One honest caveat.** "Will not hold line" does not literally say *pushes wide*. It
> could describe a rear that steps. The temperature signature argues hard for the push
> reading — an inside front that cold is not a car whose rear is loose. But if 14 makes
> it *worse*, that is the other failure mode and the answer inverts. §7 has the one-lap
> test that separates them, and it costs you nothing to run.
>
> **⚠️ 21 Aug — and 1.71 introduced a new engine torque control map plus a revised diff
> range. The value 14 is a v1.70 answer to a v1.70 torque curve.** The diagnostic logic
> is intact and is the part to carry; the number is not. Note this car runs **restrictor
> 100 / ECU 100** — unrestricted — so `08` D3.1's restricted-build correction does not
> apply here, which is itself a useful contrast with the Huracán.

## 2.2 #2 — "Bounces repeatedly after a kerb"

**Corner phase: kerb strike, chicane entry and exit.** Cost: second, and it is the one
generating your off-track count — laps 13, 14, 29 and 30 each show 4–6 off-track events
on *valid* laps.

**Cause: natural-frequency mismatch. Playbook A7, and you used its exact words.**

A7's diagnostic table has three rows, and your report picks one of them cleanly:

| Symptom | Cause | Fix |
|---|---|---|
| Hops once and settles | Too stiff | Springs and ARBs |
| **Bounces repeatedly for 1–3 s** | **Frequency mismatch** | **Large NF change (±0.3 Hz), not small damper tweaks** |
| Bangs, then won't steer | Arch contact | Ride height only |

You said *bounces repeatedly*. Not "hops once", not "bangs then won't steer."

**This overrides Rev A §7.3, which had ride height queued as the first response to a
kerb problem.** That instruction was written before the symptom was known and it is now
the wrong branch — you have not reported the arch-contact signature. Ride height stays
where it is. Being wrong about this in Rev A is worth noting: it is why the playbook
carries a three-row table instead of a single "kerbs → raise the car" rule.

**Direction: softer.** Lowering spring rate at a fixed damper setting *raises* the
damping ratio (ζ = c/2√km), which is what kills a repeated oscillation. A7's own fix
list agrees. And Monza's sausage kerbs want compliance.

**NF 3.35/3.50 → 3.05/3.20, both ends −0.30 Hz.** Equal at both ends deliberately — see
§4 on why.

> **⚠️⚠️ 21 Aug — this is the most 1.71-exposed diagnosis on the sheet.** The update
> *"changed damper attenuation characteristics to make stance changes and road surface
> tracking feel more natural"* — **road surface tracking is kerb behaviour by another
> name.** And whether the underlying 1.49 arch-rub problem still exists is now [UNKNOWN]
> (`../16` §4), which puts A7's third row back in play as well. **Re-establish the kerb
> behaviour on the comparison run before trusting either the diagnosis or the 3.05/3.20
> values — and note that a moved suspension range may have clamped 3.05 anyway (§4.1).**

## 2.3 #3 — Rear-left wheelspin on kerb exits (telemetry only — you did not report this)

Not in your report. I am raising it because it is visible and it is coupled to #1.

The three excluded big-time laps have a common signature in `tyreTempMaxC`:

| Lap | Time | RL max °C | Off-track |
|---|---|---|---|
| 15 | 2:04.015 | **148.6** | 2 |
| 27 | 2:03.332 | **105.1** | 3 |
| 33 | 2:17.868 | **144.2** | 7 |

RL peaking at 148 °C against a mean of 82 °C is a large rear-left wheelspin event.
Three of them in 36 laps, each costing 14–28 seconds. Rev A §2 predicted the mechanism
in advance: *"every one of these exits is over an aggressive kerb, and a locked diff on a
kerb strike produces snap oversteer."*

**This is the same problem as #1 wearing a second face.** Diff lock on an overworked
rear axle: steady state it pushes, transient over a kerb it spins the outside rear.
16 → 14 addresses both. No separate change.

## 2.4 So which symptoms are one problem?

**Two problems, three faces.**

- **The diff** (#1 and #2.3) — mid-corner push on maintenance throttle *and* rear-left
  breakaway over kerb exits. One cause, one change.
- **The platform frequency** (#2) — the kerb bounce. Genuinely separate; a differential
  cannot make a car oscillate.

They are cleanly separable by feel in a single run: one is a mid-corner steady-state
sensation, the other happens the instant you leave a kerb.

## 2.5 A correction to the knowledge base

The circuit reference says Monza *"wears Rear + front-right."* Measured:

```
  FL 0.79 vs FR 0.63    (front-left worse by 0.16)
  RL 0.84 vs RR 0.74    (rear-left worse by 0.10)
```

**The rear half is confirmed. The front half is inverted.** Lesmo 1, Lesmo 2 and the
Parabolica are right-handers, which load the left-hand tyres — so front-*left* is the
front corner that goes first here. `05-track-reference.md` has the side backwards.
Per standing rule 6 the measurement wins; the doc needs correcting.

> **⭐ 21 Aug — this correction is geometry, not physics, and survives 1.71 intact. It is
> also still outstanding in `05-track-reference.md`.** And it gives the comparison run a
> second diagnostic: **if the limiting corner changes side after the patch, that is a
> steering-geometry signal**, since 1.71 reworked geometry per car.

---

# 3. Gearing — measured, and it is right. Do not touch it.

> **⚠️⚠️ 21 Aug — "do not touch it" was correct on v1.70 and is now the *first* thing to
> re-measure.** *"Road surface resistance (rolling resistance) has been optimised"* moves
> terminal speed directly, and every number in this section is derived from a terminal
> speed. **This section is the single best-instrumented rolling-resistance baseline in the
> knowledge base — which is exactly why the comparison run should reproduce it first.**

Rev A §3.5 asked for one number. The packet delivered it, and the answer is better than
expected.

```
  Observed:  278.7 km/h in 6th at 8,009 rpm, clean air, no tow
  Limiter:   8,600 rpm  (observed at the limiter — NOT the 8,800 assumed)

  6th at limiter = 278.7 × 8600/8009            = 299.3 km/h
  K = 299.3 × 1.062 × 3.550                     = 1,128.3

  ┌────────────────────────────────────────────────────────┐
  │  MEASURED K = 1,128.3   ·   LIMITER = 8,600 rpm        │
  │  Rev A assumed K = 1,161.6 — 2.9% optimistic           │
  └────────────────────────────────────────────────────────┘
```

The error was almost entirely the limiter (8,600 vs 8,800 = 2.3%); the 2.20 m rolling
circumference guess was good to about 0.6%.

**Corrected speed table:**

| Gear | Rev A said | Actually | Job it has to do | Verdict |
|---|---|---|---|---|
| 1st | 120 | **117** | nothing — rolling start | fine |
| 2nd | 170 | **165** | all three chicanes, no upshift between apexes | fine |
| 3rd | 214 | **208** | Lesmo 1 and Lesmo 2 | fine |
| 4th | 254 | **247** | Parabolica through track-out | fine |
| 5th | 284 | **276** | spacing | fine |
| 6th | 308 | **299** | top out in a tow | **see below** |

**Every gear is 2.9% short of the table, and every gear still does its job.**

And the top gear is better than Rev A dared hope. The RSR makes peak power at
**8,100 rpm**. In clean air it sat at **8,009 rpm** at maximum speed — **98.9% of
peak-power rpm.** The gearbox is delivering peak power exactly at Vmax, with 7.4% of rev
range still in hand for the tow. That is what a correctly geared top gear looks like, and
it happened despite the assumed limiter being wrong.

> **Leave the gearbox exactly as it is.** Do not apply the §3.5 correction. Do not apply
> the app's 3.665. The number was wrong and the outcome was right, which is worth
> knowing but is not worth acting on.
>
> **⚠️ 21 Aug — the *ratios* still stand (they are a choice, not a measurement), but the
> 98.9%-of-peak-power result does not.** If rolling resistance dropped, Vmax rises and 6th
> now over-runs peak power; if it rose, Vmax falls and 6th is too long. **One clean-air
> reading resettles it — and it is the same reading that re-measures K.**

**For the register: 911 RSR '17 — K = 1,128, limiter 8,600 rpm.** Every future gearbox
on this car is now exact instead of iterated. Backlog item §9.4, closed. **⚠️ Reopened by
1.71 — K is derived from Vmax. The limiter should be unchanged (the RSR is not on 1.71's
max-RPM list), which makes it a useful internal consistency check: if the limiter reads
8,600 and Vmax has moved, the move is real.**

---

# 4. The revised race sheet

**⚠️ v1.70 values on v1.70 ranges. Read against the car (Job 0), do not type in.**

```
                                        RACE (Rev B)            QUALIFYING (Rev B)
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Hard             Racing Soft
  Rear compound             Racing Hard             Racing Soft
                            ↑ now MEASURED, see §5

SUSPENSION
  Body height      Front    60 mm · +5 · 20%        58 mm · +3 · 12%
                   Rear     68 mm · +8 · 27%        65 mm · +5 · 17%
  Anti-roll bar    Front    5                       6
                   Rear     3                       4
  Damping compr.   Front    23 · 15%                25 · 25%
                   Rear     25 · 25%                27 · 35%
  Damping expan.   Front    38 · 40%                39 · 45%
                   Rear     34 · 20%                36 · 30%
► Natural freq.    Front    3.05 Hz · +5 · 2.5%     3.20 Hz · +20 · 10%
►                  Rear     3.20 Hz · +20 · 10%     3.35 Hz · +35 · 17.5%
  Camber angle     Front    1.0° · +10 · 16.7%      1.2° · +12 · 20%
                   Rear     1.0° · +10 · 16.7%      1.2° · +12 · 20%
  Toe angle        Front    0.00°                   −0.05°
                   Rear     +0.08°                  +0.05°

DIFFERENTIAL
  Initial torque            5                       5
► Acceleration sens.        14                      16
  Braking sens.             24                      22

AERODYNAMICS
  Downforce        Front    370 · 20%               360 · 10%
                   Rear     540 · 20%               515 · 7.5%

TRANSMISSION
  Max speed setting         200 km/h — generator only. SET FIRST, THEN NEVER AGAIN.
  Final gear                3.550                   3.750
  1st                       2.727                   2.950
  2nd                       1.925                   1.998
  3rd                       1.529                   1.557
  4th                       1.288                   1.307
  5th                       1.152                   1.156
  6th                       1.062                   1.065
                            UNCHANGED — validated by measurement, see §3.
                            Real limiter is 8,600 rpm and K = 1,128. Race 6th
                            sits at 98.9% of peak-power rpm in clean air.

BRAKES
  Brake balance             0  (− front / + rear)   0

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)             100%
  ECU output                100%                    100%
  Ballast / position        none                    none

ASSISTS
  ABS                       Weak                    Weak
  TCS                       0 — but read §6.4       0
═══════════════════════════════════════════════════════════════════
       ► = changed from Rev A.  Three values. Nothing else moves.
```

**The NF step on this car is 0.01 Hz.** Your feedback table gave 3.35 Hz as +35 clicks,
which settles the question Rev A §1.1 flagged as unrecorded. Click counts above are now
exact rather than a convenience. Worth writing into the register. **⚠️ And re-confirming —
step sizes are a property of the slider, and the sliders were revised.**

## 4.1 Range check on the changed values

> **🔴 VOID ON v1.71.** 1.71 revised adjustment ranges for suspension, differential and
> aerodynamics **in the official notes**. Re-read `../11-car-slider-ranges.md` first.

| Parameter | Range (v1.70) | Rev B race | Margin |
|---|---|---|---|
| Natural freq. F | 3.00–5.00 Hz | **3.05** | ⚠️ 0.05 Hz above min — deliberate, see below |
| Natural freq. R | 3.00–5.00 Hz | **3.20** | 0.20 Hz above min |
| LSD accel | 5–60 | **14** | 9 above min — ⚠️ *floor may now be 0* |

Everything else is unmoved from Rev A §8 and nothing else sits at a limit.

> **⚠️ Front NF at 3.05 is five clicks off the floor, and that is on purpose.** A7 says a
> repeated bounce needs a **large** change (±0.3 Hz) and explicitly warns that small
> tweaks will not do it. This car has never run below 3.35, so 3.05 is unexplored
> territory — but its floor is already 3.00 Hz, which is race-stiff in absolute terms
> before you touch anything, and Monza is the circuit in the set that most wants
> compliance.
>
> **Having almost no room left below is informative rather than dangerous.** If −0.30 Hz
> does not kill the bounce, A7's frequency diagnosis was wrong and the answer is ride
> height instead — which is exactly test #1 in §7.
>
> **⭐⭐ 21 Aug — and this makes front NF the single best clamp detector on the car.** It
> sits 5 clicks off a 3.00 Hz floor. **If 1.71 raised that floor at all, 3.05 was clamped
> and the settings screen will show it.** Check this value first during Job 0 — it is the
> cheapest possible test of whether the patch touched this car's ranges.

## 4.2 Why both ends move by the same amount

Front −0.30 and rear −0.30, preserving the 0.15 Hz gap and the rear-above-front
relationship (rotation on a stable platform, per B1).

**This is deliberate and it is a coupling decision.** I am already changing the diff,
which moves the balance. If the NF change moved the balance too, you could not attribute
whatever you feel to either one. Equal changes at both ends make the NF change
balance-neutral and leave the diff as the only balance input in the package.

**⭐ The same reasoning is why the comparison run changes nothing at all: with the setup
held fixed, any delta is attributable to the patch.**

---

# 5. ⛔ Strategy — this is the part that changed, and it changed completely

> **⚠️ 21 Aug — every number in §5 rests on two measurements the comparison run re-takes:
> the 15-lap RH stint and 6.566 L/lap. Both are exposed to 1.71** (wear values adjusted;
> rolling resistance is a fuel term). **The arithmetic is sound; re-run it on new inputs.**

## 5.1 What the session settled

Rev A §5 laid out three defensible models giving three different races. Here is what
they predicted against what happened:

| Source | Predicted stint at 8× | Stops in ~28 laps |
|---|---|---|
| Knowledge-base model | 2.5–3.1 laps | 8–10 |
| Model ÷ 1.8 Laguna correction | 4.5–5.6 laps | 4–5 |
| Polyphony design pattern | 7–8 laps | 3 |
| **MEASURED, this session** | **15+ laps, no measurable degradation** | **1** |

**The knowledge-base model was ~5× too pessimistic.** Laguna's miss was 1.8×. This one
is worse, and it is the same failure mode: a model built from generic per-circuit base
rates, applied to a specific car, and never checked.

Two independent lines agree on 15 laps:
- **Gauge:** 84% consumed on the worst corner (RL) over run 5's 15 laps.
- **Stopwatch:** −17.8 ms/lap over the same 15 laps. Netting off fuel burn-off, true
  degradation is about 9 ms/lap. **The tyre is not costing you lap time.**

Where those disagree, the stopwatch wins — a gauge reading only matters insofar as it
predicts pace, and here it does not.

> **⚠️ One 30-second check before you race.** A 5× model miss is large enough to be worth
> ruling out the boring explanation. **Open the event settings and confirm tyre wear is
> actually set to 8×.** If it reads 8× the measurement stands. The fuel multiplier is
> definitely applied (6.57 L/lap against a 6.0–7.0 estimate at 3×), which argues the
> tyre one is too — but the consequence of being wrong is the whole race plan.
>
> **⭐ 21 Aug — this check was never done, and it is now a prerequisite for the comparison
> run rather than a nicety.** If the baseline was actually recorded at a different
> multiplier than believed, the comparison compares nothing. **Thirty seconds. Do it.**

## 5.2 The race, computed

```
  Race length      50 min ÷ 1:49.2 median                    ≈ 27.5 → plan 28 laps
  Fuel             6.566 L/lap MEASURED (run 5 confirms 6.571)
  Tank             100 L → 15.2 laps                    ◄── FUEL LIMIT
  Tyre             15+ laps, no degradation              ◄── TYRE LIMIT
  Total fuel       28 × 6.566                                = 183.8 L
  Must add         183.8 − 100                               = 83.8 L
  At 1 L/s                                                   = 84 s stationary
  Pit transit      19% of a lap                              = 20.7 s per stop
```

**The fuel limit and the tyre limit are the same number.** That almost never happens and
it makes the call trivial.

| Stops | Transit | Refuel | **Total** |
|---|---|---|---|
| **1** | 20.7 | 83.8 | **104.6 s** |
| 2 | 41.5 | 83.8 | 125.3 s |
| 3 | 62.2 | 83.8 | 146.1 s |

Refuel time is linear at 1 L/s, so total standing time is identical whatever you do —
every extra stop is pure added transit loss. **One stop, by 20.7 seconds.**

Rev A §5.3 recommended splitting fuel across stops to keep the car light. That was
correct advice for a four-stop race. Here the average-fuel-load difference between one
and two stops is about 3.6 L, worth roughly **0.3 s across the whole race** against
20.7 s of extra pit loss. **Withdrawn.**

> **⚠️ 21 Aug — "the fuel limit and the tyre limit are the same number" is a coincidence
> of two independent measurements, and 1.71 moved both.** They may no longer coincide,
> and if they diverge the stop count changes. **The pit arithmetic itself is untouched**
> (`../03` §6) — only the two inputs need re-measuring.

## 5.3 Compound: stay on Racing Hard

Rev A §5.2 said RM goes live if the stint reaches 8 laps. It reached 15, so the question
is properly open — but the arithmetic closes it:

- RM is roughly one grade softer, so ~1.4–1.6× the wear rate → **RM does not make 15
  laps.** It forces a second stop.
- Extra stop: **−20.7 s.**
- RM lap-time gain at Monza (Rev A: RM→RH delta can be under 0.4 s/lap): **+11.2 s** over 28 laps.

**RH wins by ~9.5 seconds.** Closer than Rev A assumed, and it flips if the real Monza
RH→RM delta is above about 0.75 s/lap. That is a five-lap measurement if you have the
practice time — §7 lists it.

RS is not live for either stint: 13–15 laps is far outside its range at 8×.

**Qualifying stays on Racing Soft** — no stint to protect, the delta is pure lap time.

> **⚠️ 21 Aug — this call rests on the assumed RH:RM ratio (1.4–1.6×), which `../03` §1.3
> has always flagged as never measured, and on the 15-lap RH stint, which is now v1.70.
> A 9.5 s margin is thin enough to flip on either.** Re-derive after the comparison run.

## 5.4 The plan

**Short-shift from lap 1.** Now the highest-value habit in the race, and now on measured
fuel numbers rather than estimated ones:

| | Fuel/lap | Tank lasts | Fuel to add | Standing |
|---|---|---|---|---|
| Map 1, no short-shift | 6.57 L | 15.2 laps | 83.8 L | **84 s** |
| Short-shifting (−20%) | 5.25 L | 19.0 laps | 47.1 L | **47 s** |

Costs ~0.5 s/lap × 28 = **14 s**. Saves **37 s** of standing time. **Net gain ≈ 23 s** —
and it reduces rear tyre wear as a side effect, on the axle that is measurably the
limiting one.

**One stop. Window laps 15–18. Target lap 17.** Fill to the diamond plus one lap.

Late is better here, for a reason Rev A got backwards:

> **⛔ Rev A §6.5 said "a weather stop at this event is nearly free."** That was true at
> four to eight stops. **At one stop it is false** — an unscheduled wet stop now costs a
> full 20.7 s of transit that you were not going to spend. Conditions are changeable with
> a day-to-night transition, so **hold the stop as late as the fuel allows and keep it
> available to double as the weather stop.** That is the single biggest strategic
> difference between Rev A and Rev B.

**Fuel map:** map 1 default with short-shifting; **5 or 6 whenever you are in a tow** —
Monza's slipstream is the strongest in GT7 and this is close to free. Map 1 when
attacking, defending, or on the last lap. The diamond marker is the authority in the
race, not this document.

> **⚠️ 21 Aug — the −20% short-shift saving is a GT Sport-era figure (`../03` §5.6), and
> 1.71 introduced a new engine torque control map.** The *technique* is sound and it won
> the 17 Aug Watkins Glen race; the 20% needs re-checking.
>
> **⭐ And the comparison run is where that re-check happens for free.** Per the run-mode
> decision in the banner, **Job 2A is driven short-shifted on the beep** — matching the
> bulk of the Monza history — **with 2–3 full-RPM laps on the end.** That gives an L/lap
> figure in each mode from one session: the short-shift number for the dominant baseline,
> and the full-RPM number against this sheet's documented 6.566. **The difference between
> them is the −20% claim, re-measured on the new torque map.**

---

# 6. What each change should feel like

One run each. If you cannot feel it, revert it.

### LSD acceleration 16 → 14

**Where:** Lesmo 1, Lesmo 2 and the Parabolica, from the moment you pick up maintenance
throttle to track-out.

**Should feel like:** the car holds the arc you set instead of washing toward the outside
kerb. You should be able to hold steady throttle through the Parabolica without adding
lock. Secondary tell: the rear-left should stop lighting up on chicane exits over the
kerbs.

**Working:** off-track count drops. This is the cheapest objective check you have — you
were logging 4–6 per lap on valid laps.

**Too far (unlikely at 14, but watch for it):** the inside rear starts spinning up *alone*
on exit, and the car feels like it bogs out of the chicanes. That is A5's first failure
mode and it means go back up, to 15.

**⚠️ The inverted result:** if the car gets *looser* mid-corner rather than more
willing — if it starts wanting to rotate past the apex — then "will not hold line" meant
the rear stepping, not the front pushing, and my §2.1 reading was wrong. Go straight to
§7 test #2, and tell me: it also means the temperature signature is misleading me and
I want to know that.

### Natural frequency 3.35/3.50 → 3.05/3.20

**Where:** Rettifilo and Roggia kerbs first, Ascari second.

**Should feel like:** the car absorbs the kerb and settles in one movement instead of
oscillating. The repeated bounce should be gone, not reduced — a −0.30 Hz change is
large and a frequency mismatch resolves cleanly when you cross it.

**Working:** you can use more kerb at the chicanes than you dared before, and the car is
still pointing straight on exit.

**Cost you should expect and accept:** more body roll through the Lesmos and more pitch
under the Rettifilo stop with 100 L aboard. A slightly softer, lazier-feeling platform is
the price. If it feels merely *soft* but the bounce is gone, that is a win — leave it.

**⚠️ The one thing to watch:** a softer platform sits lower under load. If the car starts
**banging and then refusing to steer**, that is arch contact, not balance — A7's third
row. Ride height is the only thing that fixes it and it becomes test #1 immediately.

**⚠️⚠️ 21 Aug — and that watch item is now a live question rather than a precaution.**
Whether the 1.49 arch-rub problem survived 1.71 is [UNKNOWN] (`../16` §4), and 1.71
changed damper attenuation. **If the car bangs and refuses to steer on the comparison
run, that is a finding worth reporting immediately** — it would be the first hard
evidence anyone has on what 1.71 did to the bottoming floor.

---

# 7. What I deliberately left alone

**⭐ 21 Aug — this section is the most durable in the document. Every entry is a reasoning
chain about why *not* to change something, and that discipline is exactly what the 1.71
rebuild needs. Read it before touching any slider on this car.**

The discipline that paid at Laguna was the changes that were *queued and not made*.
Six here, each with the measured reason it survived.

### The gearbox — untouched, and now on measurement instead of assumption

Rev A's assumed limiter was wrong by 200 rpm and every speed in its table was 2.9%
optimistic. **The gearbox is still correct.** 8,009 rpm at Vmax against a peak-power
point of 8,100 is 98.9% — you cannot do better in clean air, and there is 7.4% of rev
range left for the tow. Every corner gear still covers its job (§3). Applying either the
§3.5 correction or the app's 3.665 would have broken a gearbox that measurement says is
right. **⚠️ Re-measure Vmax first — see §3.**

### Ride height 60/68 — untouched, and this is a reversal

Rev A §7.3 queued **ride height first** for any kerb problem. Your report says *bounces
repeatedly*, which is A7's frequency row, not its arch-contact row. **Rev A had the wrong
branch queued** and I am not taking it. It stays as the fallback in §8.

### Camber 1.0/1.0 — untouched, but the reason has narrowed

A1's caution says to re-open camber after any wear measurement that beats the model, and
this one beat it by 5×. But Rev A's camber argument was never a wear argument — it was
that Monza is the lowest-lateral-load circuit in the set and has the heaviest braking in
Gr.3, so camber's benefit is smallest and its longitudinal cost highest exactly here.
**That argument is untouched by the wear result.** It stays, and the sweep is queued
(§8) rather than guessed at now. Adding rear camber to help the overworked RL would also
cost traction on the corner that is already spinning up.

> **⚠️⚠️ 21 Aug — the camber argument IS touched by 1.71, and this is the exception to
> "§7 is durable."** The claim rests on GT7 taxing camber against *longitudinal* grip,
> which is a steering-geometry behaviour — and 1.71 reworked steering geometry per car. If
> the tax softened, Monza's heavy-braking argument weakens with it. **`../16` §12 Job 5.**

### Downforce 370/540 — untouched, and this is the Laguna trap

Adding rear downforce would add grip to the axle that is measurably overloaded, with no
wear cost to worry about any more. **It is still wrong.** Rev A measured this car's aero
window as nearly balance-neutral and noted 1,300 lb of downforce is worth about 0.1 s/lap
— so 40 units of rear DF buys almost nothing and costs real drag at the most
speed-sensitive circuit in the game, on the slowest car in Gr.3 in a straight line.

More importantly: it would **mask the diff problem while giving up top speed**. That is
precisely the Laguna case — front ARB and front downforce both queued as fallbacks, both
would have "fixed" a power-on symptom by adding grip elsewhere, and neither was needed
once the diff was right.

**⭐ This reasoning survives 1.71 completely, and it is the general form of the trap the
whole rebuild has to avoid: do not fix a symptom by adding grip somewhere else while the
cause goes unexamined.**

### LSD braking 24, brake balance 0 — untouched

No braking or entry-stability symptom reported, on a circuit with the three heaviest
stops in Gr.3, ABS Weak, neutral bias and a driver who trail-brakes deep. **The
rear-stability stack is working exactly as designed** — that is a real result and it
deserves recording, not adjusting. A4's whole claim is that the rear can be stabilised
mechanically without moving bias forward, and Monza is a harder test of it than Laguna
was. **⚠️ 1.71 adjusted ABS slip-ratio control and cornering brake behaviour — this is a
result worth re-confirming on the comparison run, because it is one of the playbook's
central claims.**

### Rear toe +0.08 — untouched, but now for a different reason

Rev A held it mid-band because rear toe is the largest alignment contributor to tyre wear
and this was an 8× wear event. **That reason is gone** — there is no wear budget to
protect. It is still the right value, but now on the other half of the argument: it costs
straight-line speed at the most speed-sensitive circuit in GT7, on a car that is already
drag-limited. It is queued as test #3 rather than shipped, because shipping it alongside
the diff change would confound both.

---

# 8. Three things to try next, in order

> **⭐ 21 Aug — superseded by `../16-update-1.71-physics-change.md` §12. The comparison run
> (Job 2A) comes first and changes nothing at all, by design. Everything below waits for
> its result.**

One change per run, three clean laps, revert what you cannot feel.

### 1. If it still bounces on the kerbs → ride height, +3 mm both ends

**60 → 63 front, 68 → 71 rear.** If a −0.30 Hz change did not resolve a repeated bounce,
A7's frequency diagnosis was wrong and this is the remaining candidate. Do **not** chase
it further with NF — you have 0.05 Hz of front travel left and going there would put the
car on its floor for no reason.

Related and separate: if the car ever **bangs and then refuses to steer**, stop
everything and do this immediately regardless of what else is queued. That is arch
contact and nothing else fixes it.

### 2. If the car got *looser* mid-corner rather than more willing → the diagnosis inverted

My §2.1 reading was wrong and "will not hold line" meant the rear stepping. Then:

1. **LSD accel back to 16.**
2. **LSD braking 24 → 26**, in 2s, per the A4 stack. Rev A already sanctioned this and
   the Laguna Huracán ran 26 successfully against a harder entry.
3. **Rear expansion damping 34 → 32** if 26 is not enough.
4. **Do not move brake balance.** That is the whole point of the stack.

### 3. If the car is right and you want the lap time back → the durability audit

C3.1's corollary: *durability you don't consume is pace you paid for and threw away.*
The wear budget turned out to be five times larger than the sheet was built for, so
several settings are now protecting against nothing. In value order:

- **Rear toe +0.08 → +0.12.** The wear objection is dead. Costs a little top speed, buys
  mid-corner rear security on the limiting axle. Cheapest of the three.
- **Camber sweep, 1.0 / 1.2 / 1.5**, Data Logger on, one axle at a time. Backlog item 11.
  Monza's braking argument still stands, but it has never been tested on this car.
  **⭐ 21 Aug — widen this to 0.5 / 1.5 / 2.5 and run it as `../16` §12 Job 5. The
  geometry rework may have changed the sign of the answer, not just its size.**
- **Five laps on RM at 8×** to measure the real Monza RH→RM delta. §5.3 shows RH wins by
  ~9.5 s — but it flips if RM is worth more than ~0.75 s/lap here, and nobody has
  measured that number.

### And the two free observations

**Which corners are fine?** The single highest-information thing I do not have. F2's
second question resolved the Laguna case in one step, and this packet has no `corners`
section to answer it with. Next session: name the corner where the car holds line
perfectly. If the Parabolica is fine and only the Lesmos complain, that is a different
diagnosis from all three complaining.

**TCS.** Rev A §6.4 flagged TCS 1 as a stronger case than usual in a changeable
day-to-night event, and the three rear-left blowups (§2.3) support it. But **TCS 1 and
the diff change are aimed at the same events** — make the diff change first and judge TCS
after, or you will not know which one helped. It stays adjustable live on the MFD.
**⚠️ And 1.71 "optimised" TCS intervention behaviour, so the price of TCS 1 is unknown.**

---

# 9. What to record

Per standing rule 6, with date and version. Four items close, three open, one correction.

**✅ CLOSED on v1.70 — ⚠️ items 1, 3 and 4 are reopened by 1.71**

1. **Gearing constant K = 1,128 · limiter 8,600 rpm** (911 RSR '17, v1.70, 11 Aug 2026).
   Backlog §9.4. Every future gearbox on this car is now exact. **⚠️ Reopened — K derives
   from Vmax and rolling resistance changed. The limiter should hold.**
2. **NF slider step on this car = 0.01 Hz.** Rev A §1.1 flagged it as unrecorded; your
   feedback table settles it. **⚠️ Re-confirm — the slider was revised.**
3. **Fuel at 3×, Monza, map 1, no short-shift = 6.566 L/lap.** Measured across 28 laps and
   independently confirmed on run 5 at 6.571. Rev A estimated 6.0–7.0 — **the fuel
   estimate was right.** Worth saying, given the wear estimate was not. **⚠️ Reopened —
   rolling resistance is a fuel term. Two independent confirmations make this the cleanest
   baseline available for measuring that change.** *(The full-RPM tail laps of Job 2A hit
   this figure directly; the short-shift laps give the number that matches the wider
   history.)*
4. **Tyre stint, RH at 8× at Monza = 15 laps with no measurable degradation.** The
   knowledge-base model was ~5× pessimistic. Backlog item 2, partly closed. Subject to the
   §5.1 multiplier sanity check. **⚠️ Reopened — tyre heating and wear values adjusted.**

**📝 CORRECTION — still outstanding, and unaffected by 1.71**

5. **`05-track-reference.md` has Monza's front wear side backwards.** It says front-right;
   measured FL 0.79 vs FR 0.63. Monza's three sustained corners are rights, which load the
   left. The rear half of the claim is confirmed. **Still not corrected in `05`.**

**❌ STILL OPEN**

6. **Front toe A/B on the RSR** (−0.05 / 0.00 / +0.05). Never run on this car. GT7's most
   disputed parameter, sitting on your stated #1 priority. Still 15 minutes. **⭐ And 1.71
   reworked the steering geometry that toe sensitivity depends on, so the dispute has just
   been re-rolled — `../16` §12 Job 5.**
7. **Multiplier linearity.** A 5× miss makes this more urgent, not less. Backlog item 5.
8. **Fuel weight penalty in s/L/lap.** Backlog item 9. Run 5 came close to giving it —
   98.6 L burned across 15 laps with tyre degradation near zero is almost a clean
   measurement of it, and one more stint at constant fuel load would isolate it.
9. **⭐ NEW — are the short-shift points still right?** The Pit Crew beep encodes RPM
   points derived against the old torque map, and 1.71 replaced it. **Repeatability is
   unaffected, so the comparison run is safe; optimality is a separate question.**
   `../16` §11 item 17.

**📤 FOR PIT CREW — three export bugs, plus one that is now priority-one**

- **⭐ `meta.gameVersion` is missing.** Standing Rule 10 now requires it on every packet.
  Without it a future session cannot tell a 1.70 export from a 1.71 one, and every
  measurement in the archive becomes ambiguous. **Fix this first.**
- `wear.byCompound` invents compound labels for same-compound runs. **Do not emit a
  compound key unless the compound was actually run.**
- `bestLapMs` accepts a lap that consumed 0.16 L. **Validate lap fuel delta before
  admitting a lap time.**
- `gearing` emits `matchesSheet: true` alongside a `fittedFinalGear` that differs from the
  sheet, and the derivation points the wrong way. **Either reconcile them or drop the
  derived final gear** — the observed speed/rpm/limiter triple is more useful and is
  already there.
- And the big one: **build the `corners` section.** The spec calls it the section that
  actually changes setups, and this diagnosis ran without it.

---

*Rev B issued 12 Aug 2026 · GT7 v1.70 · ranges verified on this car 11 Aug 2026*
*Three sliders changed. Strategy rewritten from a 4–8 stop race to a 1-stop race.*
*Driver profile: front-end-led precision attacker, neutral brake bias, low tolerance for rear snap*
***Stamped pre-1.71 on 21 Aug 2026. This is the reference baseline for `../16` §12 Job 2A — the RSR-at-Monza control run. Run mode: short-shift on the beep, plus a full-RPM tail. See `00-PRE-1.71-NOTICE.md`.***
