# Lamborghini Huracán GT3 '15 · Watkins Glen International — Long Course
### 20 laps · 2× tyre · 3× fuel · 1 mandatory stop · standing start · changeable · afternoon

**Rev B — 14 Aug 2026 · GT7 v1.70 · no BoP, open tuning**
**Supersedes Rev A (13 Aug 2026). First revision of this combination with a session on file.**
Driver profile: front-end-led precision attacker · ABS Weak · TCS 0 · Fanatec DD Extreme 18 Nm, ClubSport V3 load cell
Revision priority as set by the driver: **fuel and stint length.**

**Session behind this sheet:** practice / shakedown, 30 laps run, 23 counted, RS runs 1–4 and one 13-lap RM run.
**Build confirmed by the driver:** Rev A race spec exactly — NA (turbo removed), restrictor 99, ECU 94, ballast **55 kg @ −25**.
**Driver answers to the four questions:** right foot — *grip faded late in the stint*, i.e. it **develops, not lap 1**. Fuel map run — **FM1**. Compound call for the race — **split RS / RM**.

---

## 0. READ THIS FIRST — the sheet was built on two premises and the session falsified both

### 0.1 The wear-limiting tyre is the REAR-LEFT, not the front-left

Rev A built four separate decisions around the circuit reference's claim that the Glen *"wears front-left"* — ballast at −25, brake balance held at 0, rear ARB raised to 4 (*"rear grip is not the scarce resource here — the front-left is"*), and front camber raised to 1.4.

**Every gauge reading from lap 12 onward says rear-left.**

| Reading | FL | FR | **RL** | RR | Worst |
|---|---|---|---|---|---|
| lap 7 (RS, 4 laps in) | 10 % | 5 % | 8 % | 6 % | FL |
| lap 12 (RS, 5 laps in) | 34 % | 23 % | **35 %** | 31 % | **RL** |
| lap 17 (RS, 5 laps in) | 23 % | 19 % | **39 %** | 27 % | **RL** |
| lap 30 (RM, 13 laps in) | 18 % | 13 % | **24 %** | 16 % | **RL** |

`frontMinusRear −0.045`, `leftMinusRight +0.065`. The reference's *left-side* bias is confirmed; its *front/rear* call is inverted.

**The temperature channel agrees independently.** Rear runs **4.9 °C hotter than front** across the session, and the rear-left is the hottest corner on 29 of 30 laps. Over the settled laps 23–30 the pattern is metronomic: FL ≈ 84 °C, FR ≈ 77 °C, RL ≈ 89 °C, RR ≈ 85 °C. Two independent channels, same answer.

> **Backlog item G4 — "which corner/tyre goes first on the Huracán" — closes for this circuit, with the opposite of the predicted answer.** That is the second time in five days that a generic track-reference figure has pointed the wrong way on this car.

### 0.2 The fuel constraint that paid for the rear aero trim does not exist

Rev A trimmed rear downforce to **620** — 75 points below the 695 you ran at Laguna — explicitly to buy drag and fuel, on a modelled **8.7 L/lap** and a **~74-second** refuel that was called *"the strategic event this round."*

**Measured at FM1: 7.285 L/lap. The model was 19 % pessimistic. The refuel is 46 seconds, not 74.**

That makes three consecutive pessimistic fuel/tyre estimates from the same method (Laguna tyres 1.8×, Laguna fuel 20–25 %, Glen fuel 19 %). More to the point:

> **The rear downforce was sold to buy fuel headroom, and the rear tyre is the thing that gave up. You paid for a constraint that was never binding, and the currency was the one resource this car is actually short of.**
>
> This is the C3.1 corollary running in reverse. C3.1 says *durability you don't consume is pace you paid for and threw away.* Here it is: **a durability sacrifice made to buy headroom that was already there.**

**That single correction is the whole of this revision.** Rear downforce 620 → 660, front 415 → 435 to hold the aero balance. Everything else on this sheet is either a consequence of that change, or a free gain from a number that is now measured instead of assumed.

### 0.3 What is NOT changing, and why that matters more than what is

**The differential is untouched. So is the brake balance, the whole suspension platform, both ARBs, all four camber and toe values, and gears 1 through 5.**

You reported no power-on push, no entry instability and no lazy turn-in across 30 laps. Rev A flagged accel 18 as *"the one number on this sheet I am least confident about"* and made it test #1. **The test came back clean.** Moving it now to chase a tyre-wear symptom would destroy a measurement that is one stint from closing — see §6.1. Rev A's Laguna restraint is the pattern here, and it is the pattern that has paid twice.

---

## 1. THE SHEET

```
═══════════════════════════════════════════════════════════════════════════════
  LAMBORGHINI HURACÁN GT3 '15  ·  WATKINS GLEN INTERNATIONAL — LONG COURSE
  Rev B · 14 Aug 2026 · GT7 v1.70            ▲ = changed from Rev A
═══════════════════════════════════════════════════════════════════════════════
                                     RACE                  QUALIFYING
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound                     Racing Soft → Medium  Racing Soft
  Rear compound                      Racing Soft → Medium  Racing Soft
                                     (split at the stop — §5.3)

SUSPENSION
  Body height        Front         ▲ 65 mm               ▲ 63 mm
                                     40 % · +10 clicks     32 % · +8 clicks
                     Rear            72 mm                 70 mm
                                     40 % · +12 clicks     33 % · +10 clicks
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
                                     50.0 % · +100 clicks  50.0 % · +100 clicks
                     Rear            +0.08 °               +0.06 °
                                     54.0 % · +108 clicks  53.0 % · +106 clicks

DIFFERENTIAL
  Initial torque                     6                     6
  Acceleration sensitivity           18   ← HOLD, §6.1     20
  Braking sensitivity                28                    26

AERODYNAMICS
  Downforce          Front         ▲ 435                   435
                                     85 % of range         85 % of range
                     Rear          ▲ 660                   660
                                     80 % of range         80 % of range
                     (front share)   39.7 %                39.7 %
                     (total)         1095                  1095

TRANSMISSION  (speed at limiter, K measured 1077.9 — no longer assumed)
  Max speed setting                  300 km/h              300 km/h
                                     ⚠ DO NOT TOUCH — generator, wipes all ratios
  1st                                113 km/h              113 km/h
  2nd                                155 km/h              155 km/h
  3rd                                190 km/h              190 km/h
  4th                                221 km/h              221 km/h
  5th                                264 km/h              264 km/h
  6th                              ▲ 286 km/h            ▲ 275 km/h
  Final gear                         3.550                 3.550

  Ratios 1st→6th                     2.677 1.963 1.600     2.677 1.963 1.600
                                     1.376 1.150 ▲1.060    1.376 1.150 ▲1.104

BRAKES
  Brake balance                      0                     0
                                     (− = FRONT bias · + = REAR bias)
                                     ⚠ in-stint migration REVERSED — §5.5

PERFORMANCE ADJUSTMENT
  Turbocharger                       NONE (NA)             NONE (NA)
  Power restrictor                   99 %                  99 %
  ECU output                         94 %                  94 %
  Ballast                            55 kg                 55 kg
  Ballast position                   −25                   −50
                                     ⚠ re-check PP after the aero change — §7

FUEL
  Map                              ▲ 2                     1
  Refuel at stop                   ▲ ~38 L (≈38 s)         n/a
                                     (Rev A planned ~74 s)

ASSISTS
  ABS                                Weak                  Weak
  TCS                                1 for launch lap → 0  0
  Countersteering assist             Off                   Off
═══════════════════════════════════════════════════════════════════════════════
```

**Four values changed on the race sheet. Two of them are one coupled pair.**

---

## 2. DIAGNOSIS — symptoms ranked by what they cost

### The one-line version

> **There is one problem and it has three faces: the rear axle was deliberately under-supported to buy a fuel constraint that measurement has now shown does not exist.** The rear-left wear, the late-stint grip fade, and the sheer volume of rear traction events in the telemetry are the same fault seen from three angles.

### Ranked

| # | Symptom | Corner phase | Cause | Cost | Confidence |
|---|---|---|---|---|---|
| **1** | **Rear-left is the wear limiter — 39 % in 5 laps on RS** | Mid-corner, sustained lateral load | **Rear downforce trimmed 75 points below Laguna for a fuel constraint that isn't binding.** At a Med-Low downforce circuit with sustained 160–190 km/h loaded corners, rear lateral slip is the dominant wear source (C3). Trimming rear aero at exactly the circuit archetype that punishes it. | **Sets the stint.** Forces RS off the cliff by ~lap 7 and drives the whole strategy. | **Measured** — 4 gauge readings + independent temperature asymmetry |
| **2** | **"Grip faded late in the stint"** | Develops; all phases | **The same fault.** Not a separate complaint. The rear-left crosses the ~50 % fall-off point mid-stint on RS and the car goes with it. Note the RM stint's lap times *improved* (−0.18 s/lap raw) and its wear was 24 % at 13 laps — **the fade you felt was the RS runs, not the RM run.** | Same as #1 — this is #1 wearing its second face. | **Measured**, cross-checked against both compounds |
| **3** | **Rear traction events, every corner, every lap** | Early throttle → full exit | **The same fault again, third face** — a rear axle with less downforce over it on a TCS-0, 540 bhp MR car. ⚠️ **But see §3.1: I do not trust the magnitude of this channel.** | Contributes to #1; not independently actionable | **Direction real, count unusable** |
| **4** | **Front-axle float and countersteer at PC-T2 — 14 of 23 laps, plus 22 kerb strikes and 4 bottoming laps** | Turn-in / mid, high speed | **Front ride height.** PC-T2 and PC-T3 hold the lowest suspension heights on the entire lap (front 228–229 mm, the session's bottoming reference). Rev A predicted this exact failure — *"the compression at the top of the esses will bottom a very low car"* — and set 63 mm to avoid it. It happened anyway. Post-1.49 this is a ride-height problem, not a damper problem (A7). | **Second-largest.** 14 laps of countersteer at 165–192 km/h is a consistency and confidence tax on a driver with low tolerance for float. **You did not report this.** | **Telemetry only** — sub-threshold (4/23 bottoming vs a 6-lap threshold), so flagged, and half-addressed |
| **5** | **6th gear 23 km/h too long** | Straights | K was **assumed** at 1045; measured 1077.9. The whole box came out ~3 % longer than Rev A specified. 6th tops at 297.1 km/h; you reached 273.8 and never touched the limiter. | ~0.1–0.2 s/lap of unused acceleration on two long full-throttle sections. Free to fix, zero PP. | **Measured**, 23 laps |
| **6** | **PC-T5: 1.57 s lost vs best, 1.69 s consistency, 7.2 % of the corner on gravel** | Mid / exit, slow corner | Worst single corner on the lap by both measures, and you are running wide onto the outside on most laps. Could be line, could be an on-throttle push. **Not enough information to tune on.** | Largest single-corner loss on the lap | **Unresolved — needs your read.** See §7 |
| **7** | Mid-corner understeer flagged at 7 of 9 corners | Mid | ⚠️ **You did not report this.** See §3.2 — I am not treating it as real. | Not actioned | **Rejected as primary** |

### Which symptoms are one problem wearing two faces

- **#1, #2 and #3 are one problem.** Rear-left wear, late-stint fade, and rear traction events are a single under-supported rear axle. **One change addresses all three.** Do not expect three separate improvements from it — expect one, felt three ways.
- **#4 and #5 are genuinely independent** of #1–#3 and of each other. #4 is geometry, #5 is arithmetic.
- **#4 is coupled to the fix for #1** in the wrong direction — adding 60 points of downforce pushes the car down harder at the exact corner that already bottoms. That coupling is why the ride height moves on this sheet and it is named rather than shipped silently. See §4.

---

## 3. WHERE THE PIT CREW DATA AND YOUR REPORT DISAGREE

You asked me to say so explicitly, say which I am trusting, and why. Six disagreements. I am not averaging any of them.

### 3.1 The traction-event channel says every corner, every lap. I am trusting your report over it.

The detector flags a rear traction event in **all 9 corners on all 23 counted laps** — including **PC-T8, where throttle is 0.3 % and brake is 2.4 %.** You cannot spin the wheels at 0.3 % throttle. A flag that fires on 100 % of laps in 100 % of corners, including a corner where the car is coasting, has **zero discriminating power** — it cannot tell you where the problem is, which is the only thing a corner flag is for.

**There is a plausible mechanism for the bias, and it is in the packet's own notes.** `gearing.finalGearVsSheetPct` reads **+3.24 %**, and the packet explains why: *"GT7 broadcasts the unloaded radius, so this reads a few percent high."* If the slip detector derives driven-wheel ground speed from that same unloaded radius, **every sample carries a ~3.2 % standing positive slip bias — 40 % of the 8 % threshold — before the car does anything at all.** That is enough to convert genuine 5 % slip into a flagged 8 %.

> **Verdict: the direction is real** — a 540 bhp NA MR car on TCS 0 with a trimmed rear wing does spin its rears, and your rear-left wear is consistent with it. **The count is not usable as a magnitude and I have not tuned off it.** The gauge and temperature channels carry this diagnosis instead. **Recommend Pit Crew recompute slip against a loaded radius, or state the threshold in loaded-radius terms.**

### 3.2 The telemetry says mid-corner understeer at 7 of 9 corners. You said nothing. I am trusting you.

`understeer-mid` clears its 6-lap threshold at PC-T1 (8), T2 (15), T4 (7), T5 (8), T6 (7), T8 (11) and T9 (8). Only T3 and T7 are clean.

**Your report does not mention understeer at all**, and the brief instructs me to read it literally rather than smoothing it into generic symptoms. It is also the case that a symptom present at 7 of 9 corners **fails the localisation test that has diagnosed this car twice** — at Laguna it was T11's *silence* that identified the fault in one step. A flag with almost no silent corners is much more likely a threshold artefact than a car problem.

> **Verdict: not actioned. The differential does not move on this sheet.** But this is precisely why §7 asks you about PC-T5 specifically — if that one corner *is* an on-throttle push, it is the Laguna signature and the answer is accel 18 → 16, which is queued as next test #2.

### 3.3 The circuit reference says front-left. The car says rear-left. The car wins.

Covered in §0.1. Four gauge readings and an independent 4.9 °C thermal asymmetry against one generic reference line written for no particular car. **Trusting the measurement.** The reference entry should be amended.

### 3.4 The report header and the telemetry disagree on excluded laps

The header says **24 counted**, 6 laps *"struck by hand"* (4, 5, 8, 18, 22, 28). The telemetry says **23 counted**, 7 excluded, and carries a reason and source per lap: laps **4, 8, 13, 18** are `out-lap / auto`, only **5, 22, 28** are `manual / driver`. So lap 13 is missing from the header entirely, and 4 of the 6 "struck by hand" laps were not struck by hand at all.

> **Trusting the telemetry** — it carries provenance, the header does not. **Nothing in this diagnosis moves**, but the header's exclusion summary is being generated wrong and will eventually mislead. Worth a Pit Crew fix.

### 3.5 The packet's performance block is stale, and it nearly changed the diagnosis

The packet records **ballast 70 kg @ −50** with no restrictor, ECU or turbo fields at all. You have confirmed the car ran **Rev A race spec exactly: 55 kg @ −25, NA, restrictor 99, ECU 94.** 70 kg is Laguna's value and −50 is Rev A's *qualifying* position — the block is carrying two stale numbers from two different sheets.

**Trusting you.** But flag it hard: 15 kg of extra mass at the fully-forward position on an MR car would have been a live suspect for exactly the rear-traction symptom you reported, and I would have chased it. **Two Pit Crew items:** (a) the performance block is not being refreshed per session; (b) the `gt7-pitcrew/1.4` `performance` object has **no fields for restrictor, ECU or turbo**, although the sheet format's paste block carries them — so the single most consequential build variable on this car cannot round-trip. That is a format gap, not a user error.

### 3.6 Two derived fields in the packet contradict the packet's own warnings

- **`wear.modelledStintLaps: 46`** is computed from the **RM** rate. Read without its compound it says this setup does 46-lap stints; the RS runs measured **11**. Trusting the per-compound figures; **the headline field should not be shown without its compound.**
- **`wear.byLapTime.degradationMsPerLap: −177.2`** — the packet's own note says the fuel signal over that window is larger than the tyre signal and is not netted off. It is right: 87.6 L burned at ~0.003 s/L/lap ≈ 0.26 s/lap of fuel effect, which more than accounts for the −0.18 s/lap observed. **The lap-time channel says nothing about degradation here and I have not used it.** Its own `confidence: low` is correct.

---

## 4. DELTA TABLE — race sheet

| Parameter | As run | Revised | Why |
|---|---|---|---|
| **Downforce — rear** | 620 (60 %) | **660 (80 %)** | **The fix.** Rear-left is the wear limiter (§0.1) and lateral slip is the dominant wear source at a sustained-load circuit. 620 was trimmed 75 points below Laguna to buy fuel headroom that measurement says was never needed (§0.2). Still below Laguna's 695 — this is a correction, not an overshoot. |
| **Downforce — front** | 415 (65 %) | **435 (85 %)** | ⚠️ **COUPLED to the line above — these two move together or not at all.** Rear alone would drop front share from 40.1 % to 38.6 % and hand you understeer at a circuit where the nose has to respond at 190 km/h. +20 front holds the share at **39.7 %**, so the balance you drove for 30 laps without complaint is preserved and only the total changes. |
| **Body height — front** | 63 mm | **65 mm** | **Consequence of the two above, not an independent change.** PC-T2/T3 already hold the session's bottoming reference (228 mm front) with 4 bottoming laps and 14 countersteer laps; +60 points of downforce pushes the car down harder there. A7's post-1.49 fix order is ride height first, and nothing else works for arch contact. **+2 mm not +3–5 mm** — the bottoming was sub-threshold and I am protecting rake. Rake goes +9 → +7 mm. **If it still bangs, 67 mm is next test #1.** |
| **6th gear ratio** | 1.022 | **1.060** | **Free, and now measured rather than assumed.** K = 1077.9 (Rev A assumed 1045). 6th topped at 297.1 km/h; you reached **273.8** and never touched the limiter across 23 laps. 1.060 puts the limiter at **286 km/h** — reachable with the tow Rev A geared for, and with the extra drag from the aero change. Recovers acceleration on both full-throttle sections. **⚠️ Edit the 6th ratio directly. Do NOT touch Max Speed — it regenerates the whole box.** |
| **Fuel map** | 1 | **2** | Strategy, not setup. At 1 L/s, 1 litre saved = 1 second stationary, exactly. FM2 saves ~12 L ≈ **12 s** in the box against ~0.2–0.3 s/lap ≈ **5 s** on track. **Net ≈ +7 s.** There is no range constraint to satisfy (14.5 laps available, 10 needed) — this is purely buying pit time, and it reduces rear torque as a free side effect. |
| **Race compound** | RS throughout | **RS → RM at the stop** | Your call, and the data supports it. §5.3. |
| — | — | — | — |
| Everything else | | **unchanged** | §6. |

---

## 5. STRATEGY — the revision priority

### 5.1 Fuel, measured

```
Measured, FM1, Rev A aero, 3×          7.285 L/lap   (Rev A modelled 8.7 — 19 % pessimistic)
+3 % allowance for Rev B aero drag     7.50 L/lap    ⚠ estimate, flagged
FM2 at −8 %                            6.90 L/lap    ⚠ estimate, flagged

Race, 20 laps at FM2                 = 138.1 L
Tank                                   100 L
Refuel required                      =  38.1 L  ≈  38 seconds stationary
Range on a full tank at FM2          =  14.5 laps
```

**Rev A planned a 74-second refuel. This is 38. Thirty-six seconds recovered, from a measurement that took ten minutes.**

### 5.2 The stop window — fuel no longer constrains it at all

Refuel is **invariant at 38 L for every legal stop lap**, because total race consumption is fixed and you start full. Only tank capacity bounds the window:

| Stop at end of lap | Fuel left at stop | Needed after | Tank after refuel | |
|---|---|---|---|---|
| 5 | 65.5 L | 103.6 L | — | ✗ exceeds tank |
| **6** | 58.6 L | 96.7 L | 96.7 L | ✅ earliest legal |
| **10** | 31.0 L | 69.0 L | 69.0 L | ✅ **planned** |
| **14** | 3.4 L | 41.4 L | 41.4 L | ✅ latest legal |
| 15 | −3.6 L | — | — | ✗ runs dry |

> **Fuel window: laps 6–14. That is nine laps wide. The tyre decides the stop now, not the fuel** — which is the exact inversion of Rev A's premise and the direct answer to your revision priority.

### 5.3 The RS / RM split — and RS goes first

**Run RS for stint 1, RM for stint 2.**

The RS data contradicts itself — 2.0 %/lap on run 2 against 7.0 % and 7.8 % on runs 3 and 4, same compound, same sheet. Run 2 contained a 161-second lap (a big off), so it saw far less energy; **I am weighting runs 3 and 4 and treating RS as ~7.5 %/lap, with the caveat that a 4× gap to RM is not physically plausible and one of these numbers is wrong.**

**RS first, because it is the order that gives you an escape hatch:**

| | RS first | RM first |
|---|---|---|
| If RS is really 7.8 %/lap | **Stop early at lap 8. RM covers 12 laps easily** — measured 24 % at 13. Recoverable. | You discover it in the closing laps with no move left. |
| If RS is really 2.0 %/lap | Run to lap 11–12 and bank the fast laps. | You wasted the fast tyre on the stint you couldn't extend. |
| Heaviest fuel load | RS carries 100 L — the cost | RM carries 100 L — the benefit |

The fuel-load argument favours RM first; **the optionality argument favours RS first and it is worth more**, because it is the one that protects you against the reading that is actually in dispute. It also puts RM — the compound with enormous margin — on the second half of a **changeable** afternoon.

**The decision rule. Read the rear-left gauge at the end of lap 6:**

| RL at end of lap 6 | What it means | Do |
|---|---|---|
| **≥ 45 %** | The 7.8 %/lap reading is real | **Stop end of lap 8.** RM covers 12 laps. Refuel 38 L. |
| **25–45 %** | As modelled | **Stop end of lap 10.** Planned. Refuel 38 L. |
| **< 25 %** | Run 2 was right and RS is far better than feared | **Stop end of lap 11 or 12.** Take the fast laps. Refuel 38 L. |

Every branch refuels 38 L. Every branch is fuel-legal (§5.2). **One gauge reading at lap 6 decides the whole race, and it costs you nothing to take.**

### 5.4 Fuel map in the race

**FM2 from the green.** If at 5 laps to go you are showing more than 5 laps of range and you are in a fight, **go FM1 and spend it** — fuel you cross the line with is fuel you carried for nothing.

### 5.5 Brake balance — the migration direction is reversed

**Start at 0. It stays at 0 on the sheet.**

Rev A instructed *"move one click rearward (+1) as the front-left degrades."* **That instruction was built on the falsified front-left premise and is now backwards.** The front axle has measured headroom — 18 % FL against 24 % RL at lap 30. If the rear-left is what fades in the last three laps of a stint, the correct trim is **−1**, taking braking work off the axle that is actually short.

Two honest caveats: the effect is **modest**, because rear-left wear here is lateral- and traction-dominated rather than braking-dominated; and this is a late-stint trim, not a setting. It goes back to 0 at the stop. Your standing rule — forward bias is never a permanent answer — is intact.

### 5.6 What did not need saying again

Pit loss (~21 s), racecraft, the wide T1, the weak undercut — Rev A §6.5–6.8 stands unchanged and is not repeated here.

---

## 6. WHAT I DELIBERATELY LEFT ALONE

### 6.1 The differential — 6 / 18 / 28. This is the most important thing on this page.

Rev A called accel **18** *"the one number on this sheet I am least confident about"* and made it **test #1**. It was set to test a live hypothesis (D3.1: does an ECU-heavy build want more lock than a restrictor-heavy one at the same power?) after Laguna's measured **14** was invalidated by removing the restrictor.

**Across 30 laps you reported no power-on push.** That is the result. It is the first genuine evidence for D3.1 and it says **yes — removing the restrictor does push the correct accel value up, and 18 holds where 14 was needed at Laguna.**

> **Moving the diff now to chase a tyre-wear symptom would confound a measurement that is one clean stint from closing.** The Laguna double-win (*"the rotation fix and the stint-length fix pointed the same way"*) does tempt me here — less lock would mean less rear scrub. But the aero change addresses the same tyre with a bigger, cleaner mechanism, and **you cannot attribute a result to two changes at once.** 18 → 16 is queued as next test #2, behind the corner question that would justify it.

**LSD braking 28** — thirty laps, ABS Weak, high yaw inertia, the hardest stop on the lap, **brake balance never left 0**, and not one entry complaint. That is the A4 rear-stability stack validated on a second circuit without touching brake bias. **Do not walk it while it is working.**

### 6.2 Gears 1 through 5 — the error helped

The box came out ~3 % longer than Rev A specified, because K was assumed at 1045 and measures 1077.9. Second tops at **155** where the spec said 150; third at **190** against 184.

**Longer lower gears are GT7's #1-ranked fix for exit traction limitation, ahead of every LSD and suspension change (A6).** On a TCS-0 MR car with a rear-traction problem, an accidental 3 % lengthening of 2nd and 3rd is help, not error. **Keeping it. Only 6th moves**, and only because it is never reaching its limiter.

### 6.3 Everything else, and the reason each one earned its place

| Left alone | Why |
|---|---|
| **Front toe 0.00** | Still the top backlog item, still the wrong circuit for it — oscillation risk above ±0.05° at 190–250 km/h, and your profile calls for less front toe-out at high-speed circuits. Run the A/B somewhere slow. |
| **Rear toe +0.08** | It is the biggest alignment contributor to tyre wear, so it is a genuine suspect for #1 — but it is also what is keeping the rear honest at 190 km/h, LSD braking is already at 28 with nowhere to take the stability from, and no entry complaint was reported. Fallback only. |
| **Camber 1.4 / 1.2** | Front camber was raised from Laguna's 1.0 on the A1 argument, and **no braking degradation was reported** — Rev A's explicit revert trigger did not fire. Front is not the limiter. Rear camber is genuinely two-sided (more spreads outside-rear lateral load; more also taxes longitudinal grip and worsens traction) and I will not move a two-sided lever on a hunch. |
| **ARB 6 / 4** | Rear ARB 4 → 3 would add rear mid-corner grip — the same effect as the aero change, by a different route. **Shipping both loses attribution entirely.** Queued as next test #3. |
| **Natural frequency 3.55 / 3.70** | No bounce, no repeated-oscillation complaint. The one platform defect found (PC-T2 bottoming) is answered by ride height first per A7's fix order, which explicitly puts springs behind it. |
| **Damping 26/24 · 42/36** | Rear compression 24 was set low for kerb compliance, and PC-T2 took **22 kerb strikes across 23 laps and produced only 4 bottoming laps.** The compliance is doing its job. Front compression 26 is low for turn-in and no lazy-turn-in complaint was reported. |
| **Ballast 55 kg @ −25** | The rationale (protect the front-left) is falsified, so this value is now correct by accident rather than by argument. But the evidence for moving it is **two-sided**: further forward unloads the wear-limited rear axle, and further forward also removes rear traction on a TCS-0 MR car and feeds the same problem. Coupled, high-impact, ambiguous. **Not moving it. Noted as an open question rather than quietly left.** |
| **Brake balance 0** | Sheet value unchanged; only the in-stint migration direction is corrected (§5.5). |

---

## 7. WHAT EACH CHANGE SHOULD FEEL LIKE — one run tells you

Three clean laps each, and note the **corner**, not just the feeling.

| Change | What you should feel if it worked | What you should feel if it went wrong |
|---|---|---|
| **Rear DF 620 → 660** | The rear stays with you through the **long loaded corners** — PC-T2, T3, T8, the 160–190 km/h ones. It should feel like it takes a set and holds it rather than gradually giving ground. **The real test is not lap 1 — it is lap 8.** The stint should stop falling away where it did before. | The car feels safe but slower and duller, and top speed at the braking board drops more than ~5 km/h. That would mean the drag cost exceeded the grip gain. |
| **Front DF 415 → 435** *(coupled)* | **Nothing.** That is the point — it exists to keep the balance you already had. If the car feels the same in balance but more planted overall, the pair worked. | If the nose feels sharper or the car feels nervous at 190 km/h, the front went too far and you can take it back to 425 alone. |
| **Front height 63 → 65 mm** | **PC-T2 stops needing hands.** You were countersteering there on 14 laps out of 23; you should be able to hold one input through it. Fewer bangs over the crest. | The car feels lazier turning in and rolls more at the slow corners. That is the 2 mm of rake you gave up. If it is worse than the float was, go back to 63 and take the bottoming another way. |
| **6th 1.022 → 1.060** | You **reach the limiter in 6th with a tow** at the end of the long full-throttle section, and the pull from 250 km/h up is stronger. | You are bouncing off the limiter well before the braking board in clean air — go back toward 1.040. |
| **FM2** | Barely perceptible on a 70 %-full-throttle circuit — a slightly softer top end. If it feels like a real handicap out of the slow corners, that is worth more than 12 s and you go back to FM1. | |

---

## 8. THREE THINGS TO TRY NEXT, IN ORDER

**Only if the first revision is still not right. One change per run.**

### 1. Front ride height 65 → 67 mm — if PC-T2 still bangs or still needs hands

The highest-confidence unfixed defect on the car, and I under-treated it deliberately. A7's post-1.49 rule is **raise 3–5 mm** and I took 2 to protect rake. If the countersteer and kerb-strike behaviour at the fast crest is unchanged, finish the job. **Ride height is the only thing that fixes arch contact — nothing else works, so do not reach for dampers or springs here.**

### 2. LSD acceleration 18 → 16 — but only if PC-T5 is an **on-throttle** push

PC-T5 is the single worst corner on the lap: **1.57 s lost against your best, 1.69 s of consistency spread, and 7.2 % of the corner spent on gravel.** Entry 134 → apex 112 → exit 134 km/h in 2nd, 22 % brake. You are running wide there on most laps and it is costing more than any other corner.

**Before touching anything, answer the fork:** at PC-T5, are you **on the throttle** when it washes wide? If yes, that is the Laguna signature exactly — power-on push at a slow corner picked up with steering wound on — and **18 → 16 is the answer**, in a single 2-point step. If you are coasting or trailing brake there, the diff is not engaged and the answer is front grip, not the differential.

This also closes D3.1 either way, which is why it ranks above a change I would otherwise rate higher.

### 3. Rear ARB 4 → 3 — if the rear-left is still the wear limiter after the aero change

The second route to rear mid-corner grip, held back only so the aero change can be attributed. Costs roll control in the fast direction changes, which is why it is third and not first. **Take the gauge reading at lap 6 again and compare like for like.**

*(Held in reserve behind these three: rear camber 1.2 → 1.4 as a lateral-scrub lever — explicitly two-sided, and it will cost you traction on a car that is already spinning its rears. Rear toe +0.08 → +0.06. Ballast −25 → −50. None of these should be reached for before the three above.)*

---

## 9. RANGE CHECK

Every value on both sheets, against the ranges read off this car's own settings screen on 13 Aug 2026.

| Parameter | Min | Max | Race | Quali | Status |
|---|---|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | **65** | **63** | ✅ 40.0 % / 32.0 % |
| Ride height — rear | 60 mm | 90 mm | 72 | 70 | ✅ 40.0 % / 33.3 % |
| Natural frequency — front | 3 Hz | 5 Hz | 3.55 | 3.70 | ✅ |
| Natural frequency — rear | 3 Hz | 5 Hz | 3.70 | 3.85 | ✅ |
| Anti-roll bar — front | 1 | 10 | 6 | 7 | ✅ |
| Anti-roll bar — rear | 1 | 10 | 4 | 5 | ✅ |
| Damper compression — front | 20 % | 40 % | 26 | 25 | ✅ |
| Damper compression — rear | 20 % | 40 % | 24 | 26 | ✅ |
| Damper expansion — front | 30 % | 50 % | 42 | 43 | ✅ |
| Damper expansion — rear | 30 % | 50 % | 36 | 37 | ✅ |
| Camber — front | 0 ° | 6 ° | 1.4 | 1.5 | ✅ |
| Camber — rear | 0 ° | 6 ° | 1.2 | 1.3 | ✅ |
| Toe — front | −1 ° | 1 ° | 0.00 | 0.00 | ✅ |
| Toe — rear | −1 ° | 1 ° | +0.08 | +0.06 | ✅ |
| LSD initial torque | 5 | 60 | 6 | 6 | ✅ 1 above min **by design** |
| LSD acceleration | 5 | 60 | 18 | 20 | ✅ |
| LSD braking | 5 | 60 | 28 | 26 | ✅ |
| Downforce — front | 350 | 450 | **435** | 435 | ✅ 85 % — 15 points below max |
| Downforce — rear | 500 | 700 | **660** | 660 | ✅ 80 % — 40 points below max |
| Brake balance | −5 | 5 | 0 | 0 | ✅ |
| Maximum speed | 200 km/h | 800 km/h | 300 | 300 | ✅ generator — do not touch |
| Final gear | 2 | 5 | 3.550 | 3.550 | ✅ |

### Nothing is clamped. No value sits at a hard limit on either sheet.

> ### ⚠️ PP — check this before you commit
> **Downforce costs PP and does so non-monotonically** — reducing rear downforce has been reported to *raise* PP by ~10 on some cars, so raising it may move PP in either direction. You were at **PP 738.66**. **Press Triangle after entering the new aero values and re-read it.** If you are over your cap, take it from the **restrictor**, not the ECU (D3) — walk 99 → 98 → 97. Do not solve it by putting the wing back.

---

## 10. QUALIFYING SHEET — reissued, but not for the reason you'd expect

**The balance diagnosis does not move the qualifying sheet.** Rear-left tyre life over a stint is not a qualifying problem — there is no stint. Every balance and platform value in the quali column is unchanged from Rev A.

**Two measured facts move it anyway, and both are corrections of assumptions rather than of judgement:**

| Parameter | Rev A | Rev B | Why |
|---|---|---|---|
| **Body height — front** | 61 mm | **63 mm** | The quali car is 2 mm **lower** than the race car and runs the same aero. The race car bottomed at PC-T2 on 4 laps and countersteered on 14. The quali car would do it worse. Same reasoning as the race sheet, same +2 mm. |
| **6th gear ratio** | 1.075 | **1.104** | K measured at 1077.9, not the assumed 1045. Rev A specified quali 6th at 274 km/h; at the real K, 1.075 delivers **282.5** — ~12 km/h too long, and worse with quali aero drag. 1.104 lands it at **275**, as specified. |

**One thing that changed by itself, and it is worth naming.** Rev A ran quali aero at 435/660 against race 415/620, on the logic that the race car was trimmed for drag and fuel. **The race car is no longer trimmed for drag and fuel, so the two aero packages have converged.** That is not laziness — it is the falsified fuel premise showing up in a second place. The quali car is still a genuinely different car: stiffer platform, more roll stiffness, more camber, less rear toe, ballast at −50, a shorter 6th and no fuel load.

*Optional, if you have spare practice time: quali-only **445 / 690** is available and untested. It is one lap with nothing to protect, and the fast corners are the lap. I am not putting it on the sheet because it is unevidenced and it increases the bottoming risk you already have — but it is a legitimate A/B.*

---

## 11. PIT CREW PASTE BLOCKS

**Two blocks. Paste them one at a time into the paste box on Pit Crew's Event screen — race first, then qualifying.** Never both at once: the parser reads a single `setup` object per paste and a second sheet in the same payload is ignored **without a warning**.

**Acceptance test:** each paste should read **"22 of 23 settings, 6 gears"** with nothing unrecognised. `awd` is omitted deliberately — two-wheel-drive car, and `"awd": null` would be dropped silently and read as a clean 23.

### 11.1 RACE

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Lamborghini Huracán GT3 '15",
    "circuit": "Watkins Glen International — Long Course",
    "sessionType": "race",
    "date": "2026-08-14",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "Watkins Glen Long race v2",
    "values": {
      "rh_f": 65, "rh_r": 72,
      "nf_f": 3.55, "nf_r": 3.70,
      "arb_f": 6, "arb_r": 4,
      "dc_f": 26, "dc_r": 24,
      "de_f": 42, "de_r": 36,
      "cam_f": 1.4, "cam_r": 1.2,
      "toe_f": 0.00, "toe_r": 0.08,
      "lsd_i": 6, "lsd_a": 18, "lsd_b": 28,
      "df_f": 435, "df_r": 660,
      "bb": 0,
      "top": 300, "fg": 3.550
    },
    "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.060],
    "performance": { "powerRestrictor": 99, "ecuOutput": 94, "ballastKg": 55, "ballastPosition": -25 }
  }
}
```

### 11.2 QUALIFYING

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Lamborghini Huracán GT3 '15",
    "circuit": "Watkins Glen International — Long Course",
    "sessionType": "qualifying",
    "date": "2026-08-14",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "Watkins Glen Long quali v2",
    "values": {
      "rh_f": 63, "rh_r": 70,
      "nf_f": 3.70, "nf_r": 3.85,
      "arb_f": 7, "arb_r": 5,
      "dc_f": 25, "dc_r": 26,
      "de_f": 43, "de_r": 37,
      "cam_f": 1.5, "cam_r": 1.3,
      "toe_f": 0.00, "toe_r": 0.06,
      "lsd_i": 6, "lsd_a": 20, "lsd_b": 26,
      "df_f": 435, "df_r": 660,
      "bb": 0,
      "top": 300, "fg": 3.550
    },
    "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.104],
    "performance": { "powerRestrictor": 99, "ecuOutput": 94, "ballastKg": 55, "ballastPosition": -50 }
  }
}
```

### 11.3 What these blocks do **not** carry — enter by hand on the Event screen

The parser reads `sheetName`, `values` and `gears`. **That is all.**

- **Compounds** — RS for qualifying; race runs **RS stint 1 → RM stint 2** (§5.3), which the block cannot express
- **Assists** — ABS Weak, TCS 0 (race: TCS 1 for the launch lap only), countersteer off
- **Multipliers** — tyre 2×, fuel 3×
- **Performance adjustment** — turbo **removed**, restrictor 99, ECU 94, ballast 55 kg, position −25 race / −50 quali
- **Fuel map** — race **FM2**, quali FM1
- **Event** — 20 laps, 1 mandatory stop, standing start, changeable, afternoon
- **Refuel 1 L/s** *(declared)*, **pit loss ~21 s** *(still unmeasured)*, planned refuel **38 L**

---

## 12. WHAT TO BRING BACK

**The four that change the next sheet:**

1. **PC-T5 — where is your right foot?** On throttle, coasting, or trailing brake when it runs wide? This is the single highest-value answer available and it decides next test #2. *(Worst corner on the lap: 1.57 s lost, 1.69 s spread, 7.2 % on gravel.)*
2. **Rear-left gauge at end of lap 6 on RS**, at race pace. Resolves the 2.0 vs 7.8 %/lap contradiction and sets the stop.
3. **Did PC-T2 stop needing hands** at 65 mm? Fourteen countersteer laps out of 23 was the baseline.
4. **Did the rear stay with you at lap 8** of the RS stint, where it previously faded?

**And the housekeeping that keeps this loop honest:**

5. **The corner-ID mapping.** Pit Crew's auto-segmenter found **9 corners on an 11-turn circuit** and named them T1–T9 generically, so PC-T2 is *not* necessarily Turn 2. I have referred to them as PC-T*n* throughout and described each by its speed, gear and brake signature rather than guessing at circuit names. **One pass telling me which named corner each PC-ID is** makes every future sheet for this circuit sharper, and it is free.
6. **Fix the Pit Crew performance block** — it exported Laguna's ballast mass and Rev A's *qualifying* ballast position (§3.5). And the `1.4` format has **no fields at all** for restrictor, ECU or turbo, so the most consequential build variable on this car cannot round-trip.
7. **Actual top speed in 6th**, clean air and with a tow, after the aero change.
8. **Measured pit loss** including the refuel actually taken. Still the app default and still never measured here.
9. **PP after the aero change** (§9).

---

*Rev B · 14 Aug 2026 · GT7 v1.70 baseline · no BoP, open tuning · pitcrew-prompts/1.0*
*Supersedes `setups/2026-08-13-huracan-watkins-glen-long.md` (Rev A).*
