# Lamborghini Huracán GT3 '15 · Watkins Glen International (Long Course)
### 20 laps · 2× tyre · 3× fuel · 1 mandatory stop · standing start · changeable · from 18:05 at ×2 clock

**Rev C — 17 Aug 2026 · GT7 v1.70 · no BoP, open tuning**
**Supersedes Rev B (14 Aug 2026), which supersedes Rev A (13 Aug 2026).**
Driver profile: front-end-led precision attacker · ABS Weak · TCS 0 · Fanatec DD Extreme 18 Nm, ClubSport V3 load cell

**Session:** 38 laps, 28 counted, **two setup sheets**. Laps 1–30 = Rev A (runs 1–5). Laps 31–38 = **Rev B, 8 laps, RM, and ABS OFF by error** (run 6).

---

## 0. READ THIS FIRST

### 0.1 Rev B has not been tested. It has not been falsified either.

The 8-lap run was invalid as a test of Rev B on three counts, and they compound:

1. **ABS was off.** That is a control-system fault, and it sits at the very top of your change hierarchy — *"Hardware / calibration: bad data makes a good chassis look wrong."* Your own operating procedure opens with *"Validate controls first. Do not tune around faulty hardware,"* and the profile already carries the precedent: at Watkins Glen with the Shelby, recalibrating the throttle **invalidated part of the previous exit diagnosis.** Same circuit, same lesson.
2. **Wrong compound.** Rev B's one change of substance was made to fix **rear-left wear on Racing Softs**. The run was on **Racing Mediums**, which wear at 1.9 %/lap and were never the problem. Measuring an RS fix with an RM stint is measuring with the wrong instrument.
3. **Wrong length.** 8 laps, of which 7 counted, of which the first two were the driver adapting to no ABS.

> **So: almost nothing on this sheet moves, because almost nothing was tested.** Changing more would be tuning on invalid data, which is the thing this knowledge base was built to stop.

### 0.2 One defect is now unambiguous, and the old detector was hiding it

**The car bottoms out at PC-T2 on 29 of 29 counted laps.** Not 4 of 23 — *every lap*.

That is not new car behaviour. It is a **new detector.** Pit Crew moved from v1 to v3 and rewrote the bottoming reference:

| | Old rule (v1) | New rule (v3) |
|---|---|---|
| Reference | *"lowest suspension height observed across the counted laps"* | *"lowest height over the **straight-line frames** — outside every corner window and under 5 % of lock"* |
| Front-left ref | 228.32 mm | **238.14 mm** |
| Consequence | The reference was set **by the cornering minima**, so a corner could barely register as below it | The reference is the car's actual static-ish ride height, so a corner *can* register |

Against the honest reference the car is **5.5 to 9.1 mm below its own straight-line height at PC-T2, on all four corners**, held long enough to clear a 50 ms / 3 mm band, every lap:

| | ref | observed min | below |
|---|---|---|---|
| FL | 238.14 | 229.01 | **9.13 mm** |
| FR | 235.29 | 228.81 | **6.48 mm** |
| RL | 254.62 | 245.58 | **9.04 mm** |
| RR | 253.01 | 247.55 | **5.46 mm** |

**Rev B raised the front 2 mm and it was not enough — I said at the time it might not be.** A7's rule is 3–5 mm and I took 2 to protect rake. The evidence has gone from suggestive to overwhelming, and it says do the job properly. **It is also both axles, not just the front**, which the Rev B sheet did not anticipate.

### 0.3 PC-T2's understeer and PC-T2's bottoming are one problem

PC-T2 also carries `understeer-mid` on **23 of 29 laps** — and this is now the best-localised symptom the project has produced since Laguna, because of what is *silent*:

| Corner | Speed | Understeer laps | |
|---|---|---|---|
| PC-T2 | 198 → 170 km/h | **23 / 29** | flags |
| PC-T8 | 192 → 180 km/h | **23 / 29** | flags |
| PC-T3 | 181 → 162 km/h | 7 / 29 | at threshold |
| PC-T1 | 143 → 129 | 1 | silent |
| **PC-T4, T5, T6** | **150 → 108 km/h** | **0, 0, 0** | **all silent** |
| PC-T7, T9 | 123, 167 | 1, 5 | silent |

**Every slow corner is silent. Only the 160–200 km/h corners complain.** That is your own §8 rule — *"ask which corners are not complaining"* — returning a clean answer: **mechanical front grip is fine.** This is not an ARB, toe or camber problem.

And for PC-T2 specifically it is not an aero problem either, because **a car sitting on its bump stops cannot generate front grip.** The bottoming is sufficient to explain the understeer at that corner. **One cause, two faces, one fix.**

PC-T8 is the corner that survives that explanation — 2 bottoming laps, no brake, no throttle, coasting at 180 km/h, 11 kerb strikes and 7 off-tracks. That one is a genuine open item and it is next test #1, not a change.

### 0.4 What the ABS error accidentally bought you

**Eight laps with no ABS at all, brake balance at 0, and you reported nothing.** No instability, no incidents on laps 31–38, and lap times that improved through the run.

Your profile says: *"Sometimes runs no ABS. When ABS is off, rear stability becomes even more important. A tune that only works with brake bias pushed heavily forward is not a finished solution."*

> **This sheet passed that test.** LSD braking 28, rear toe +0.08, rear expansion 36, brake balance **0** — no ABS, no rear complaint, no incident. That is a standing question in the profile answered by accident, and it is worth more than the run cost you. **It is logged, and it is a reason not to touch the rear-stability stack.**

---

## 1. THE SHEET

```
═══════════════════════════════════════════════════════════════════════════════
  LAMBORGHINI HURACÁN GT3 '15  ·  WATKINS GLEN INTERNATIONAL (LONG COURSE)
  Rev C · 17 Aug 2026 · GT7 v1.70          ▲ = changed from Rev B
                                           ● = Rev B value, RE-ASSERT (see §8)
═══════════════════════════════════════════════════════════════════════════════
                                     RACE                  QUALIFYING
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound                     Racing Medium →       Racing Soft
  Rear compound                      Racing Soft           Racing Soft
                                   ▲ RM first, RS to the flag — §5.3

SUSPENSION
  Body height        Front         ▲ 68 mm               ▲ 66 mm
                                     52 % · +13 clicks     44 % · +11 clicks
                     Rear          ▲ 75 mm               ▲ 73 mm
                                     50 % · +15 clicks     43 % · +13 clicks
                     (rake)          +7 mm                 +7 mm
  Anti-roll bar      Front           6                     7
                     Rear            4                     5
  Damping compr.     Front           26                    25
                     Rear            24                    26
  Damping expansion  Front           42                    43
                     Rear            36                    37
  Natural frequency  Front           3.55 Hz               3.70 Hz
                                     27.5 % · +55 clicks   35.0 % · +70 clicks
                     Rear            3.70 Hz               3.85 Hz
                                     35.0 % · +70 clicks   42.5 % · +85 clicks
  Camber angle       Front           1.4 °                 1.5 °
                                     23.3 % · +14 clicks   25.0 % · +15 clicks
                     Rear            1.2 °                 1.3 °
                                     20.0 % · +12 clicks   21.7 % · +13 clicks
  Toe angle          Front           0.00 °                0.00 °
                     Rear            +0.08 °               +0.06 °

DIFFERENTIAL
  Initial torque                     6                     6
  Acceleration sensitivity           18   ← STILL HOLD     20
  Braking sensitivity                28   ← proven no-ABS  26

AERODYNAMICS
  Downforce          Front         ● 435                   435
                                     85 % of range · +17 clicks
                     Rear          ● 660                   660
                                     80 % of range · +32 clicks
                     (front share)   39.7 %                39.7 %

TRANSMISSION  (speed at limiter — K = 1077.9, NOT the 1112.6 in the packet, §3.2)
  Max speed setting                  300 km/h              300 km/h
                                     ⚠ DO NOT TOUCH — generator, wipes all ratios
  1st                                113 km/h              113 km/h
  2nd                                155 km/h              155 km/h
  3rd                                190 km/h              190 km/h
  4th                                221 km/h              221 km/h
  5th                                264 km/h              264 km/h
  6th                              ● 286 km/h              275 km/h
  Final gear                         3.550                 3.550

  Ratios 1st→6th                     2.677 1.963 1.600     2.677 1.963 1.600
                                     1.376 1.150 ●1.060    1.376 1.150  1.104

BRAKES
  Brake balance                      0                     0
                                     (− = FRONT bias · + = REAR bias)
                                     ⚠ do NOT move it forward for the lockups — §3.1

PERFORMANCE ADJUSTMENT
  Turbocharger                       NONE (NA)             NONE (NA)
  Power restrictor                   99 %                  99 %
  ECU output                         94 %                  94 %
  Ballast                            55 kg                 55 kg
  Ballast position                   −25                   −50

FUEL
  Map                                2                     1
  Refuel at stop                   ▲ ~33 L (≈33 s)         n/a

ASSISTS
  ABS                              ⚠ WEAK — CHECK IT       Weak
  TCS                                1 for launch lap → 0  0
  Countersteering assist             Off                   Off
═══════════════════════════════════════════════════════════════════════════════
```

**Two values changed. Both are the same change, made at both ends of the car.**

---

## 2. DIAGNOSIS — ranked by cost

| # | Symptom | Corner phase | Cause | Cost | Confidence |
|---|---|---|---|---|---|
| **1** | **Bottoming at PC-T2, 29 of 29 laps, all four corners, 5.5–9.1 mm below the straight-line reference** | Braking → turn-in → kerb, 198→170 km/h | **Ride height, both axles.** PC-T2 is a hard-braked, kerb-riding chicane — 70.6 % brake with **zero trail braking**, 12.9 % of the corner on kerb, kerb-strike 29/29. The platform runs out of travel over the kerb every single lap. Rev B's +2 mm front was under-treatment and did not touch the rear at all. | **Largest.** It is chronic, it is every lap, and it causes #2. | **Measured** — a height in millimetres against a properly-defined reference, not a heuristic |
| **2** | **Mid-corner understeer at PC-T2, 23 of 29 laps** | Mid, high speed | **The same problem.** A bottomed car has no front grip. | Included in #1 | Same |
| **3** | **Mid-corner understeer at PC-T8, 23 of 29 laps** — plus 11 kerb strikes and 7 off-tracks | Mid, coasting at 180 km/h | **Genuinely open.** Only 2 bottoming laps, so #1 does not explain it. Every *slow* corner is silent, which rules out mechanical front grip and points at front aero at speed. ⚠️ But you reported nothing, and the detector is brand new (§3.3). | Second-largest **if real** | **Contested** — telemetry only, on a v3 detector with an assumed wheelbase 4 % short |
| **4** | **Lockups: 39 corner-laps, against 1 in the previous packet** | Braking | **The ABS error. Nothing else.** Only 7 new laps were added and they carry essentially all 39. | Zero — **discarded** | **Attributed, not diagnosed** |
| **5** | Rear-left is still the wear limiter — 5th consecutive gauge reading | Mid / exit | Unchanged from Rev B. `frontMinusRear −0.015`, `leftMinusRight +0.035`. **The circuit reference's "wears front-left" is wrong for this car and this is the fifth time it has been wrong.** | Sets the compound plan | **Measured**, 5 readings |
| **6** | Wheelspin flags still noisy — PC-T2 27/29 | Exit | **The detector now admits it**: `wheelspinWheels: "all four … a front wheel light over a kerb under throttle reads as wheelspin on a rear-driven car"`. PC-T2 has 29/29 kerb strikes. Its wheelspin count is mostly lifted front wheels. | Not actionable | **Vindicates my Rev B §3.1 call.** Fixable — §3.6 |

### Which symptoms are one problem wearing two faces

- **#1 and #2 are one problem.** Bottoming and the understeer that follows it. **One fix.**
- **#4 is not a symptom of the car at all.** It is the assist error wearing a car's face, and the single most likely way this session could have made the setup worse — see §3.1.
- **#3 is genuinely separate** and is the reason there is a next test rather than a change.

---

## 3. WHERE THE DATA AND YOUR REPORT DISAGREE

Nine of them. None averaged.

### 3.1 The lockups. Discarded — and the trap they set.

The previous packet, over 23 counted laps, recorded **one** lockup lap in total. This packet, over 29 counted laps, records **39**: PC-T2 ×10, PC-T6 ×10, PC-T4 ×7, PC-T7 ×5, PC-T1 ×3, PC-T9 ×3. The `lockupPct: 15` threshold did **not** change between detector versions. Only seven counted laps were added, and every one of them ran **with no ABS**.

> **Trusting the attribution, not the flag.** These are the ABS error. **Brake balance does not move, and neither does LSD braking.** Moving bias forward to cure lockups caused by a missing assist would be the exact failure your profile forbids twice — *"Don't depend on front-heavy brake bias, it masks rear problems"* — and it would arrive on a sheet that has now been proven stable **with no ABS at all** at bias 0.
>
> **This is the single most dangerous piece of data in the session and the correct response to it is to delete it.**

### 3.2 The gearing constant. The packet's number is wrong; I am using arithmetic.

The packet reports `gearingConstantK: 1112.6`. **It is wrong, and the packet contains the proof.**

```
maxSpeedKph 273.8 @ maxSpeedRpm 7617, limiter 8264
  -> speed at limiter in that gear = 273.8 x 8264/7617 = 297.1 km/h
K = 297.1 x ratio x 3.55
  with the OLD 6th (1.022): K = 1077.8   <- the gearbox that was in the car
  with the NEW 6th (1.055): K = 1112.6   <- what the packet reports
```

`gearboxChangedMidSession: true`, and `maxSpeedKph` / `maxSpeedRpm` are **byte-identical to the 30-lap packet**, which covered only Rev A laps. So the observation was made on the 1.022 gearbox and the packet has multiplied it by the 1.055 ratio.

> **Trusting K = 1077.9.** Had I taken 1112.6 at face value I would have computed 6th as still ~10 km/h too long and shortened it again — chasing a phantom. **Pit Crew must compute `gearingConstantK` per gearbox, not once per session.**
>
> **And 1.060 is right.** At K = 1077.9 it puts the limiter at **286.4 km/h**; clean-air terminal velocity is ~274, which with a ~12 km/h tow reaches **8,245 of 8,264 rpm.** `topGearReachedLimiter: false` in practice is the *expected* result for a gear deliberately set for a tow you do not get when running alone. **No change. Confirm it with a tow.**

### 3.3 PC-T8's understeer. Trusting you, but not dismissing it.

You reported **"nothing flagged from the symptom list."** The v3 detector flags understeer on 23 of 29 laps at PC-T8.

The detector is much better than v1 — a proper yaw-gain model calibrated on 154,714 frames — and its localisation (every slow corner silent) is exactly the diagnostic pattern that solved Laguna. But it also discloses this:

> `understeerWheelbaseM: 2.516` · `understeerWheelbaseSource: "assumed — the recorder does not store the packet's wheelbase"`

**The Huracán's wheelbase is about 2.62 m.** Expected yaw rate goes as 1/wheelbase, so a wheelbase 4 % short makes the expectation ~4 % high and **biases the detector toward reporting understeer.** Small, but it is in the direction of the disagreement.

> **Trusting your report — no change made.** But PC-T8 also carries 11 kerb strikes and 7 off-tracks, which is independent evidence of running wide, so I am not dismissing it either. **It is next test #1 and it is a question, not a change.** *(Fixable: store the packet's wheelbase.)*

### 3.4 Your silence at PC-T2. Here I am overriding you, and saying so.

You reported nothing. The car is on its bump stops at PC-T2 on **every lap**.

> **Trusting the telemetry over the silence — the only place in this revision I do that, and here is why it is legitimate.** Bottoming is the one defect that characteristically does *not* announce itself as a symptom: A7 describes the signature as *"bangs, then won't steer"*, which a driver reads as the car simply not turning, and it is listed precisely because it masquerades as a balance problem. This is also not a heuristic — it is a height in millimetres against a defined reference, on all four corners, on 29 of 29 laps.
>
> If you look at PC-T2 next run and it feels fine, **tell me and I will put the ride height back.** But I am not leaving a measured platform failure unfixed on the basis that it did not make the complaint list.

### 3.5 The packet's `setup` block cannot represent a two-sheet session — and this could cost you the race

`setup.sheetName` still reads **"Watkins Glen Long race v1"** with the Rev A values: `rh_f 63`, `df_f 415`, `df_r 620`, 6th `1.022`.

Meanwhile the same packet says `gearboxChangedMidSession: true`, `fittedRatios` 6th = **1.055**, `matchesSheet: false`, and `bottomingRefSource` refers to *"the setup sheet each lap ran (**2 sheets**)"*.

> **Trusting the fitted ratios and your own statement that you ran the new settings.** Two consequences, and the second is serious:
>
> 1. **Every per-corner flag count is an unsplittable blend of two setups.** When PC-T2 shows understeer on 23 of 29 laps, I cannot tell whether that is 22 Rev A laps + 1 Rev B, or 16 + 7 — i.e. whether Rev B fixed it or not. **`flagLaps` must be split by sheet when a session runs two.** This is now the biggest single limitation on diagnosing your car.
> 2. **If Pit Crew is holding v1, then omitting a key from my reply reverts it to Rev A.** The reply contract says an omission is safe because *"Pit Crew already holds the sheet as run"* — but the packet says the sheet it holds is **v1**. So in §11 I have **re-asserted** `df_f`, `df_r`, `rh_*` and `gears` rather than omitting them, even though only ride height is genuinely new. **Marked ● on the sheet.** Losing 40 points of rear wing to a silent omission is exactly the transcription failure the JSON block exists to prevent.

### 3.6 The wheelspin detector now states its own limitation

`wheelspinWheels: "all four — GT7 broadcasts no drivetrain channel and none was declared, so the contract's driven-wheel test could not be applied. A front wheel light over a kerb under throttle reads as wheelspin on a rear-driven car."`

That is precisely the objection I raised in Rev B §3.1, and the improved detector confirms it: PC-T8's wheelspin fell from **23/23 to 4/29** once the rules tightened. PC-T2 remains at 27/29 — with 29/29 kerb strikes, on a chicane. **Its wheelspin count is largely lifted front wheels.**

> **Direction still real, count still unusable.** **Concrete fix: declare the drivetrain to Pit Crew as MR / rear-wheel-drive.** That one field turns a contaminated channel into a working one.

### 3.7 The packet contradicts itself on whether anything was measured

`wear.modelConfidence: "assumed"`, with `modelConfidenceBasis: "no gauge reading, so nothing is measured"` — sitting directly above `byDriverGauge` containing **five** gauge readings, and five `byRun` entries each stamped `confidence: "measured"`.

> **Trusting `byCompound`, which is right.** The headline confidence field is generating the wrong string. `modelledStintLaps: null` with the explanation *"RM and RS each produced a rate and they are not one set of tyres"* is a genuine improvement on the previous packet's misleading 46 — **that fix landed, this one did not.**

### 3.8 `byLapTime` — the packet tells you not to use it, and it is right

`runsDisagree: "The fitted run trends +23 ms/lap but run 6 at −294 ms/lap trends the other way."`

Neither is a tyre signal. Run 5 burned 80 L and run 6 burned ~50 L; at ~0.003 s/L/lap that is 0.24 and 0.15 s/lap of pure fuel effect, both larger than any degradation over those windows. Run 6 additionally has a driver getting comfortable with no ABS across seven laps. **Not used.**

### 3.9 Lap counts now agree — one off-by-one left

Header and telemetry both say **28 counted / 10 excluded**, and the exclusion reasons match. **Fixed since the last packet.** But `corners[].samples` reports **29** for all nine corners. Off-by-one somewhere between the lap filter and the corner sampler. It does not move anything here; it will eventually.

---

## 4. DELTA TABLE — race sheet

| Parameter | As run (Rev B) | Revised | Why |
|---|---|---|---|
| **Body height — front** | 65 mm | **68 mm** | Bottoming at PC-T2 on **29 of 29 laps**, 9.1 mm below the straight-line reference at the front-left. Rev B's +2 mm was under-treatment against a 4/23 signal; the honest v3 reference shows it is every lap. A7: *raise 3–5 mm at the affected end, always first.* This is +3, the bottom of that range. |
| **Body height — rear** | 72 mm | **75 mm** | ⚠️ **COUPLED — these two move together.** The rear is bottoming just as hard as the front (RL 9.0 mm below reference vs FL 9.1 mm); Rev B raised only the front because the v1 detector could not see the rear. Moving the front alone would cut rake to +4 mm and hand you a balance change you did not ask for. **+3/+3 keeps rake at +7 mm and changes only clearance.** |
| — | — | — | — |
| **Fuel map** | 2 | **2** (unchanged) | Refuel is now ~33 s. FM2 still saves ~12 L ≈ 12 s in the box against ~5 s on track. It now also lands on the **RS** stint, where less torque means less rear scrub. |
| **Compound order** | RS → RM | **RM → RS** | ▲ Strategy, not a sheet value. §5.3. |
| **Stop lap** | 10 | **12–13** | ▲ §5.2. |
| Everything else | | **unchanged** | §6. Values marked ● in §1 are Rev B values re-asserted because the packet says Pit Crew is still holding v1 — see §3.5. |

---

## 5. STRATEGY

### 5.1 Fuel — measured on both sheets

| | L/lap at FM1 |
|---|---|
| Rev A, RM, 11 laps (20–30), ABS Weak | **7.27** |
| Rev B, RM, 7 laps (32–38), ABS off | **7.04** |
| Session median, mixed | 7.25 |

Rev B measured *more economical* despite more downforce and a shorter 6th — which is backwards, and is almost certainly the ABS-off driving (braking earlier and more gently) rather than the car. **Planning on 7.25 L/lap at FM1**, the higher of the two, because it is the one not contaminated by the assist error.

```
FM1  7.25 L/lap  ->  20 laps = 145.0 L  ->  refuel 45.0 L ≈ 45 s  ->  range 13.8 laps
FM2  6.67 L/lap  ->  20 laps = 133.4 L  ->  refuel 33.4 L ≈ 33 s  ->  range 15.0 laps
```

*(For the record: Rev A modelled 74 s, Rev B measured its way to 46 s, and the plan is now 33 s. That is the fourth consecutive time the modelled figure has been pessimistic.)*

### 5.2 Stop window — laps 6 to 14, and later is better

Refuel is **invariant at 33.4 L** at every legal stop lap, because total race consumption is fixed and you start full. Only tank capacity bounds it: **legal laps 6–14.**

**Stop at the end of lap 12 or 13.** Two independent reasons:

- **It minimises average fuel weight.** You burn down to 13–20 L before taking on 33.
- **It shortens the RS stint**, which is the whole hedge — see below.

### 5.3 Compound — RM first, RS to the flag. This is a reversal of Rev B.

Rev B put RS first, on the argument that it gave you an early-stop escape hatch. **Three new pieces of evidence overturn that.**

**(a) RM is now the most solid number in the knowledge base.** Two independent stints, 13 laps and 8 laps, two different sheets: **1.846 %/lap and 1.875 %/lap.** A 1.6 % spread. RM cannot fail at any stint length this race can produce, so putting it first costs you nothing in flexibility.

**(b) RS is still unmeasured** — no RS run happened on Rev B. Still 2.0 / 7.0 / 7.8 %/lap from three short runs, still contradictory.

**(c) A late stop makes the RS uncertainty irrelevant.** This is the part Rev B got wrong:

| Stop at end of lap | RS covers | RS consumed at the flag, **pessimistic 7.8 %/lap** |
|---|---|---|
| 10 | 10 laps | 78.0 % — marginal |
| 11 | 9 laps | 70.2 % |
| **12** | **8 laps** | **62.4 %** ✅ |
| **13** | **7 laps** | **54.6 %** ✅ |
| 14 | 6 laps | 46.8 % |

> **RM first with a lap 12–13 stop puts RS inside its budget on every reading of the data, including the worst one.** RS-first for 10 laps was 78 % on the pessimistic reading with no way back. This is a strictly better hedge and it took the second RM measurement to see it.

**And the new time-of-day information points the same way.** 20 laps at ~1:46 plus a ~54 s stop is **36 minutes real = 72 minutes of game time at ×2, so 18:05 → roughly 19:17.** The track cools right through the race. A cooling track means **less wear and relatively better softs late** — so the soft compound belongs in the second stint, not the first. Three arguments, one answer.

**Bonus: it is the rain-robust order.** Conditions are changeable and you hold your one mandatory stop until lap 12–13, so a shower in the first half finds you with the stop still in hand.

### 5.4 Fuel map

**FM2 from the green.** If at 5 laps to go you are showing more than 5 laps of range and you are in a fight, **switch to FM1 and spend it.**

### 5.5 Brake balance

**0. It does not move, and specifically it does not move forward.** See §3.1 — the lockups are the ABS error. Late in the RS stint, if the rear-left is what fades, **−1 is available as a trim** and goes back to 0 at nothing (there is no second stop). The front axle has measured headroom to absorb it.

---

## 6. WHAT I DELIBERATELY LEFT ALONE

| Left alone | Why |
|---|---|
| **LSD acceleration 18** | Third session, still no power-on push reported, and the slow corners are now measured **silent** on understeer (PC-T4/T5/T6 all 0/29). That is the D3.1 hypothesis all but closed: **removing the restrictor does push the correct accel value up, and 18 holds where Laguna needed 14.** One valid RS stint finishes it. |
| **LSD braking 28 · rear toe +0.08 · rear expansion 36 · brake balance 0** | **Proven with no ABS at all** across 8 laps, no rear complaint, no incidents (§0.4). This is the strongest single endorsement the rear-stability stack has had. Touching it now would be vandalism. |
| **Downforce 435 / 660** | The Rev B change and it was **never tested** — wrong compound, ABS off. It is not validated, but nothing falsifies it either, and PC-T2's understeer has a better explanation (§0.3). Re-asserted, not re-decided. **Moving it again before one valid run would leave two revisions of untested aero stacked on each other.** |
| **6th gear 1.060** | Correct at the real K (§3.2). The fit reads 1.055 — within the ±0.005 tolerance, so either is fine; check the screen. |
| **Gears 1–5, final drive 3.550** | The ~3 % accidental lengthening still helps traction (A6) and nothing complained. |
| **ARB 6/4 · NF 3.55/3.70 · damping** | The one platform defect found is answered by ride height, which A7 puts **ahead of** dampers, bars and springs in the post-1.49 fix order. Rear compression 24 is already in the bottom fifth for kerb absorption. |
| **Camber 1.4 / 1.2** | No braking degradation reported across three sessions; Rev A's revert trigger has never fired. |
| **Front toe 0.00** | Still the top backlog item, still the wrong circuit for it. |
| **Ballast 55 kg @ −25** | Evidence still two-sided, as in Rev B. Not moving a coupled parameter on a hunch. |
| **Front downforce, for PC-T8** | It is the obvious reach and it is next test #1 — **as a question first.** You reported nothing, the detector is new, and its wheelbase is assumed 4 % short (§3.3). |

---

## 7. WHAT EACH CHANGE SHOULD FEEL LIKE

| Change | Worked | Went wrong |
|---|---|---|
| **Front + rear height +3 mm** | **PC-T2 — the fast braked chicane with the big kerbs — stops banging and starts turning.** The specific thing to feel for is the car *taking the kerb and still steering*, rather than going light-then-numb across it. If PC-T2's mid-corner push disappears with the bang, §0.3 was right and one change fixed two symptoms. | The car rolls more and feels lazier through the fast direction changes, and the slow corners feel vaguer. That is CoG. If it is worse than the bottoming was, go back to 66/73 and take the difference from front compression instead. |
| **Ride height, as a pair** | **Nothing should change in balance.** Rake is held at +7 mm deliberately. If the balance moved, something else moved with it. | |
| **RM first, stop lap 12–13** | You arrive at the stop with RM barely used, and the RS stint is short enough that the last three laps still have grip on a cooling track. | If RS is gone by lap 17, the pessimistic wear reading is real *and* worse than measured — take RM both stints next time. |
| **The one thing to verify before anything else** | **ABS reads Weak on the assists screen.** | |

---

## 8. THREE THINGS TO TRY NEXT, IN ORDER

### 0. *(Before any of them)* — one valid run. ABS Weak, Racing Soft, 10 laps.

Not a change; the missing measurement. It closes four open items at once: whether the aero fixed RS rear-left wear, which RS wear rate is real, whether accel 18 survives a full RS stint, and whether PC-T2 is fixed. **Read the rear-left gauge at lap 6 and again at lap 10.**

### 1. Front downforce 435 → 445 — but only if PC-T8 is really running wide

**Ask yourself first, at PC-T8** — the fast kink you take at ~180 km/h with no brake and no throttle: **are you running out of front there, or are you just taking too much speed in?** The telemetry says understeer on 23 of 29 laps with 7 off-tracks; you reported nothing. If it *is* the front, aero is the right tool because every slow corner is silent — front share goes 39.7 % → 40.3 %, with 5 points still in hand to 450. If it is entry speed, changing the car makes it worse.

### 2. Front ride height 68 → 71 — if PC-T2 still bottoms

Third attempt, and the car is 9 mm below reference so there is room for it to still be short. **Ride height is the only thing that fixes arch contact — do not reach for dampers or springs.**

### 3. LSD acceleration 18 → 16 — only after a valid RS stint

Still queued, still behind a measurement. If the valid RS run shows rear-left wear that the aero change did **not** cure, less lock is the remaining rear-scrub lever and the Laguna double-win applies.

*(Held further back: rear ARB 4 → 3, rear camber 1.2 → 1.4, ballast −25 → −50.)*

---

## 9. RANGE CHECK

| Parameter | Min | Max | Race | Quali | Status |
|---|---|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | **68** | **66** | ✅ 52.0 % / 44.0 % |
| Ride height — rear | 60 mm | 90 mm | **75** | **73** | ✅ 50.0 % / 43.3 % |
| Natural frequency — front / rear | 3 Hz | 5 Hz | 3.55 / 3.70 | 3.70 / 3.85 | ✅ |
| Anti-roll bar — front / rear | 1 | 10 | 6 / 4 | 7 / 5 | ✅ |
| Damper compression — front / rear | 20 % | 40 % | 26 / 24 | 25 / 26 | ✅ |
| Damper expansion — front / rear | 30 % | 50 % | 42 / 36 | 43 / 37 | ✅ |
| Camber — front / rear | 0 ° | 6 ° | 1.4 / 1.2 | 1.5 / 1.3 | ✅ |
| Toe — front / rear | −1 ° | 1 ° | 0.00 / +0.08 | 0.00 / +0.06 | ✅ |
| LSD initial / accel / braking | 5 | 60 | 6 / 18 / 28 | 6 / 20 / 26 | ✅ |
| Downforce — front | 350 | 450 | 435 | 435 | ✅ 85 % |
| Downforce — rear | 500 | 700 | 660 | 660 | ✅ 80 % |
| Brake balance | −5 | 5 | 0 | 0 | ✅ |
| Maximum speed | 200 | 800 | 300 | 300 | ✅ generator — do not touch |
| Final gear | 2 | 5 | 3.550 | 3.550 | ✅ |

### Nothing clamped. No value at a hard limit on either sheet.

---

## 10. QUALIFYING SHEET — reissued, same two values, same reason

**The diagnosis moves it, and only in one place.** Every balance, aero, diff and gearing value is unchanged from Rev B — the bottoming fix is the only thing carried across, because the quali car sits **2 mm lower than the race car and runs identical aero**, so it bottoms harder at PC-T2 than the car that bottomed on 29 of 29 laps.

| Parameter | Rev B | Rev C | Why |
|---|---|---|---|
| Body height — front | 63 mm | **66 mm** | Same defect, same +3 mm, same A7 rule. |
| Body height — rear | 70 mm | **73 mm** | Coupled — holds the quali rake at +7 mm. |

The −2 mm race-to-quali offset is preserved. **6th stays at 1.104** — at the real K = 1077.9 that puts the limiter at **275.0 km/h** against a clean-air terminal velocity of ~274, which is exactly right for a car running alone.

**Sent complete rather than as a delta.** The qualifying sheet has never actually been run, so there is no "sheet as run" for Pit Crew to hold — every key is being specified, not left alone.

---

## 11. NOTE ON THE JSON BLOCK BELOW

Three things worth reading before you paste it:

1. **The race sheet re-asserts more than it changes.** Only `rh_f` and `rh_r` are new. `df_f`, `df_r`, `gears` and `fg` are Rev B values repeated, because the packet's `setup` block says Pit Crew is holding **v1** (§3.5). Under the contract a repeated key means *"I have checked this and it stays"* — which is exactly the instruction intended. Omitting them would have risked reverting 40 points of rear wing.
2. **`awd` is `null`**, per this reply contract's rule for a setting the car does not have. Note this differs from the *paste-block* contract in `09-setup-sheet-format.md`, which asks for `awd` to be omitted entirely. Two different contracts, two different rules — worth reconciling.
3. **Nothing was clamped.**

---

```json
{
  "contract": "gt7-pitcrew-reply/1.0",
  "car": "Lamborghini Huracán GT3 '15",
  "circuit": "Watkins Glen International (Long Course)",
  "sheets": [
    {
      "purpose": "race",
      "sheetName": "Watkins Glen Long race v3",
      "values": {
        "rh_f": 68,
        "rh_r": 75,
        "df_f": 435,
        "df_r": 660,
        "fg": 3.55,
        "awd": null
      },
      "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.060],
      "why": {
        "rh_f": "Bottoming at PC-T2 on 29 of 29 laps, 9.1 mm below the v3 straight-line reference at FL. Rev B's +2 mm was under-treatment against a v1 signal of 4/23. A7 calls for 3-5 mm; this is +3.",
        "rh_r": "COUPLED to rh_f. RL bottoms 9.0 mm below reference, as hard as the front; Rev B raised only the front because the v1 detector could not see the rear. +3/+3 holds rake at +7 mm so only clearance changes.",
        "df_f": "UNCHANGED from Rev B - re-asserted because your setup block still reports sheet v1 at 415. Never validly tested (ABS off, RM only), and PC-T2's understeer is better explained by the bottoming, so not re-decided.",
        "df_r": "UNCHANGED from Rev B - re-asserted because your setup block still reports sheet v1 at 620. Rear-left is the wear limiter for the fifth consecutive gauge reading; this is the change made for it and it still has not had a valid run.",
        "fg": "Unchanged at 3.550. Checked against the real gearing constant K=1077.9, not the packet's 1112.6.",
        "awd": "Two-wheel-drive car - this setting does not exist on it.",
        "gears": "6th 1.060 re-asserted; your setup block still reports 1.022 and the fit reads 1.055 (inside tolerance, check the screen). At K=1077.9 that is 286.4 km/h at the limiter, which a ~12 km/h tow reaches at 8245 of 8264 rpm. Gears 1-5 unchanged: the ~3% accidental lengthening helps exit traction."
      }
    },
    {
      "purpose": "qualifying",
      "sheetName": "Watkins Glen Long quali v3",
      "values": {
        "rh_f": 66,
        "rh_r": 73,
        "nf_f": 3.70,
        "nf_r": 3.85,
        "arb_f": 7,
        "arb_r": 5,
        "dc_f": 25,
        "dc_r": 26,
        "de_f": 43,
        "de_r": 37,
        "cam_f": 1.5,
        "cam_r": 1.3,
        "toe_f": 0.00,
        "toe_r": 0.06,
        "lsd_i": 6,
        "lsd_a": 20,
        "lsd_b": 26,
        "awd": null,
        "df_f": 435,
        "df_r": 660,
        "bb": 0,
        "top": 300,
        "fg": 3.55
      },
      "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.104],
      "why": {
        "rh_f": "CHANGED +3 mm. Same bottoming defect as the race car, and the quali car sits lower on identical aero so it bottoms harder. Holds the -2 mm race-to-quali offset.",
        "rh_r": "CHANGED +3 mm. Coupled to rh_f - holds quali rake at +7 mm.",
        "nf_f": "Unchanged. Quali platform 0.15 Hz stiffer than race, per the C1 quali/race scalar.",
        "nf_r": "Unchanged. Rear stiffer than front for a stable platform under rotation.",
        "arb_f": "Unchanged. One step stiffer than race - no stint to protect, and the lap is the fast direction changes.",
        "arb_r": "Unchanged. Holds the same 2-point front-biased split as the race car.",
        "dc_f": "Unchanged. Low for turn-in bite per A2 #1.",
        "dc_r": "Unchanged. Slightly firmer than race - no kerb-compliance budget to protect over a stint.",
        "de_f": "Unchanged. Front must extend and find the road over the fast crest.",
        "de_r": "Unchanged. Low rear rebound for lift-off stability per A4 #2.",
        "cam_f": "Unchanged. One notch above race; no braking degradation has ever been reported at 1.4.",
        "cam_r": "Unchanged. Low - GT7 taxes camber against braking and traction.",
        "toe_f": "Unchanged at zero. The A3 front-toe A/B is still open and the Glen is the wrong circuit for it - oscillation risk above +-0.05 deg at 190-250 km/h.",
        "toe_r": "Unchanged. Less than race: mild rear toe-in for high-speed security, trimmed because it costs straight-line speed and there is no stint to protect.",
        "lsd_i": "Unchanged. Low preload - high preload is a silent cause of mid-corner push.",
        "lsd_a": "Unchanged at 20. Two above race: one lap, no rear tyre to protect.",
        "lsd_b": "Unchanged at 26. Two below race for turn-in on the brakes; the race value of 28 has now been proven with no ABS at all.",
        "awd": "Two-wheel-drive car - this setting does not exist on it.",
        "df_f": "Unchanged. Race and quali aero converged at Rev B once the fuel constraint that justified trimming the race car proved not to exist.",
        "df_r": "Unchanged. 40 points below max - deliberate headroom, not a limit.",
        "bb": "Unchanged at neutral. Do NOT move it forward for the 39 lockup corner-laps in this session: those are the ABS-off error, not the car.",
        "top": "Unchanged at 300. Generator only - set it first and never touch it again, it wipes every individual ratio.",
        "fg": "Unchanged at 3.550. Same final drive as the race sheet; only 6th differs between the two."
      }
    }
  ],
  "clamped": [],
  "testFirst": [
    "Before any change: one valid run. ABS Weak, Racing Soft, 10 laps, race pace, full fuel. Read the rear-left gauge at lap 6 and lap 10. Nothing in this session tested Rev B - wrong compound, wrong assists - and this one run closes four open items at once.",
    "Front downforce 435 -> 445, but ONLY if PC-T8 (the ~180 km/h kink taken with no brake and no throttle) is genuinely running out of front rather than carrying too much entry speed. Telemetry says understeer on 23 of 29 laps with 7 off-tracks; you reported nothing; the detector's wheelbase is assumed 4% short. Answer the question before changing the car.",
    "Front ride height 68 -> 71 if PC-T2 still bottoms. Ride height is the only fix for arch contact - do not reach for dampers, bars or springs.",
    "LSD acceleration 18 -> 16, but only after a valid RS stint, and only if rear-left wear survives the aero change."
  ]
}
```
