═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  YAS MARINA CIRCUIT (FULL COURSE)
  **REV C** — post-mortem on the completed race, 16 Aug 2026
  30 min · timed · 2× tyre / 2× fuel · 0 mandatory stops · grid start · dry, night
  606 bhp · 1335 kg · 2.20 kg/hp · ABS **Off** · TCS **0 as raced** (sheet said 1)
  Raced: **full Rev B**, driver-confirmed · Result **P5**, 15 laps, 0 stops
  Issued 16 Aug 2026 · GT7 v1.70 · no BoP · ranges verified on this car 13 Aug 2026
═══════════════════════════════════════════════════════════════════

# 0. The headline

**You did 1:57.318 on lap 3. You spun on lap 4 and again on lap 5. You never went
within two seconds of that lap again for the remaining ten.**

That is the same shape as the 13 August practice session, where you did 1:54.823 on
lap 1 and never went within four seconds of it again. **Two sessions, same signature,
three days apart, on two different sheets.** The car does not degrade. Laps 11 and 12
(1:59.624, 1:59.729) are as quick as laps 7 and 8 (1:59.170, 1:59.557) on tyres seven
laps older and a tank 60 L lighter. There is no fall-off in the data at all.

**What steps down is you, and it steps down at the exact lap you first spin, and it
does not come back inside a race.**

You told me the four stops on laps 4, 5, 13 and 15 were **your own spins, not
contact**. That answer is the most important line in this report, because it converts
32.6 seconds of lost time from *racing* into *evidence*, and it makes the ranking below
almost mechanical.

So Rev C is a **platform revision**. It makes two changes, in one family, and they are
the one thing Rev A and Rev B both declined to touch:

| # | Change | Why |
|---|---|---|
| 1 | **Ride height front 80 → 89 mm** | §2.2 |
| 2 | **Ride height rear 98 → 107 mm** | §2.2 — coupled to #1; rake held at +18 mm |

Plus one assist correction (**run the TCS 1 the sheet already specified**) and one
free driving change (**take T4 in 2nd, not 1st** — §4.3).

**Nothing else on the sheet moves**, and §7 says why. Five values in the app's record
of the car are wrong and are being resent as corrections rather than changes — §1.

---

# 1. Before anything else: the app's record of the car is wrong on 5 values and all 6 gears

## 1.1 What you actually raced

I asked, and you answered: **full Rev B was in the car — LSD 5 / 17 / 22, max speed
300, Rev B gear ratios.** The export's `setup.values` block reported the **v1 sheet**:
LSD 5 / 20 / 18, max speed 330, Rev A ratios, plus the already-known `ballastPosition`
20 against an actual 0.

I could prove the gearbox before you answered, and it is worth showing how, because it
is the only part of that block that has a ground truth:

```
  gearing.fittedRatios   2.614  1.948  1.560  1.318  1.145  1.019   ← Rev B, exactly
  setup.gears            2.614  1.797  1.400  1.155  1.010  0.921   ← Rev A

  Cross-check on K, from maxSpeed 273.8 km/h at 8,152 rpm, fg 3.600:
    if 6th = 1.019 (Rev B)  →  K = 1,091      ← agrees with 13 Aug's 1,101 to 0.9%
    if 6th = 0.921 (Rev A)  →  K =   986      ← 10% out. Impossible.
```

**`gearing.matchesSheet` was emitted as `null`.** It should have been `false`. Doc 13's
acceptance test question 1 — *"is the gearbox in the car the gearbox on the sheet?"* —
was fully answerable from this payload, and the payload declined to answer it.

## 1.2 Why this is now the highest-value fix in the app

This is the **third consecutive session** in which a value the export presented as fact
was silently wrong:

| Session | What was wrong | How it was caught |
|---|---|---|
| 13 Aug | `ballastPosition` 20 against an actual 0 | I asked. It would otherwise have been the headline diagnosis. |
| 13 Aug | Compound recorded as RM; RS was actually run | Driver mentioned it in passing |
| **16 Aug** | **`setup.values` reported the v1 sheet against a Rev B car — 5 values and 6 ratios** | The one channel that reads the game contradicted it |

**The pattern is now clear and it is structural, not incidental.** `setup.values` is a
*sheet record* — what was typed into the app — and it is being presented in the same
payload, with the same authority, as `gearing.fittedRatios`, which is *read from the
game*. Those are different kinds of claim and the export does not distinguish them.

**Two fixes, both small:**

1. **Emit `matchesSheet: false` when it is false.** The comparison is already
   specified, the data is already there, and it is one boolean that would have saved
   this entire section.
2. **Tag `setup.values` with a provenance field** — `sheet-record`, not `measured`.
   Everything else in this export carries provenance. This block is the only one that
   claims none and it is the one that has been wrong three times.

Until that lands: **the only setup fact this export can establish is the gearbox.**
Everything else has to be confirmed with you, and I will keep asking.

## 1.3 What I am resending as a record correction

Pit Crew holds the sheet as run, so an omitted key means *leave it alone* — which
would leave five wrong values in place. **These are in the JSON block not because they
are changing, but because the app's copy is wrong:**

`lsd_a` 17 · `lsd_b` 22 · `top` 300 · `fg` 3.600 · and the full six-ratio `gears` array.

Also fix by hand on the Event screen, again: **ballast 109 kg at position 0.**

---

# 2. Diagnosis — ranked by what it cost, mapped to corner phase

## 2.1 The ranking

| Rank | Symptom | Corner phase | Cause | Cost |
|---|---|---|---|---|
| **1** | **Four self-inflicted spins**, and the permanent step-down that followed the first two | **Entry and exit both** — the transitions, not the steady state | **Platform.** The car sits 5 mm off its front floor and 3 mm off its rear floor on sliders with **85 mm of adjustment each**. Kerb strikes at **8 of 10 corners**. At the worst corner the rear-right uses **27 mm more travel than it does in a straight line.** | **32.6 s direct**, plus **~21 s** of step-down over laps 6–15 |
| **2** | **Loose on throttle exit** — your stated biggest limitation | **Early throttle → full exit** | **You raced TCS 0 against a sheet specifying TCS 1.** Plus the platform at the hairpin. The diff is *not* diagnosed and I am not moving it — §2.5. | T5 **447 ms**, T1 262 ms, T4 204 ms of in-corner loss per lap |
| **3** | **Front locking** — a new symptom | **Braking + trail** | **lsd_b 22 working as designed.** The rear no longer reaches its limit first, so the front does. Compounded by fronts running at **70–75 °C**, five degrees off GT7's 70 °C fitting temperature. | T10 **369 ms**/lap, lockup on **9 of 14 laps** |
| **4** | **Rear steps out on entry** | **Trail-brake** | Weak in telemetry — countersteer fired on 2 of 14 laps at three corners, **below the detector's own 4-lap threshold**. Folded into rank 1. | not separately costed |

## 2.2 Rank 1 — the platform, and why I am overriding two previous decisions to get at it

**The number that starts this.** Your ride-height sliders on this car run
**75–160 mm front and 95–180 mm rear.** You are at **80 and 98** — **6% and 4% of
range.** On a road car with 85 mm of travel adjustment at each end, that is as close to
the floor as makes no difference.

**Where that number came from, and why it is wrong.** `08` B1 says *"ride height F: 3–5
clicks above car minimum, R: 5–8 clicks above minimum."* That rule was written against
Gr.3 cars, whose sliders span **25 mm front and 30 mm rear** — where 5 clicks is **20%
of the range**. Transported to this car, the identical click count is **6%**.

> **The rule silently changed meaning by a factor of more than three when it crossed
> from Gr.3 to Gr.N, and nobody noticed.** This is the same class of error
> `11-car-slider-ranges.md` caught on natural frequency — and it is the exact mirror
> image of it. **Natural frequency wants absolute Hz. Ride height wants percent of
> range.** Neither generalises to the other and B1 currently states both as clicks.

**The evidence from the session, and I am going to be careful about what it does and
does not prove:**

| Wheel | Straight-line reference | Lowest reached (all four at T5) | Extra travel used |
|---|---|---|---|
| Front left | 226.71 mm | 212.27 mm | **−14.4 mm** |
| Front right | 226.01 mm | 214.73 mm | **−11.3 mm** |
| Rear left | 215.30 mm | 196.08 mm | **−19.2 mm** |
| **Rear right** | **213.49 mm** | **186.82 mm** | **−26.7 mm** |

**What this does not prove.** The export says it outright and it is right to:
*"Bottoming is inferred, never measured: GT7 reports absolute height, not travel
remaining."* I cannot show the car ran out of travel. **And I am explicitly discounting
the `bottoming` flag itself** — it fired on 10–14 of 14 laps at **10 of 10 corners**,
which means it is reporting *"this is a corner"*, not *"this is bottoming"* (§5.4.9).

**What it does prove.** Twenty-seven millimetres of additional compression at the
rear-right, at a corner where **`kerb-strike` fires on 14 laps out of 14**, on a car
parked 3 mm above its rear floor. That is a measurement, not an inference, and it sits
at the corner that costs you the most clean lap time on the circuit.

**And here is what makes it rank 1 rather than a hunch.** A platform that runs out of
compliance explains **all three** of your symptoms at once, which nothing else on this
sheet does:

- **Rear steps out on entry** — a rear corner that hits its travel limit under
  braking pitch, or over a kerb, unloads abruptly and without warning.
- **Loose on throttle exit** — same thing at the exit of a slow corner: the tyre
  skips, vertical load spikes and drops, and traction goes.
- **Front locking** — a front axle that cannot build load progressively cannot
  generate temperature. **Your fronts averaged 70–75 °C across fifteen laps against a
  70 °C fitting temperature.** A cold front tyre locks. Your rears sat 8.3 °C hotter.

And it explains the four spins specifically, because it is the **only** cause on the
list that produces grip loss with *no warning* — which is a direct hit on your
non-negotiable #5, information-rich controls, and it is exactly what a driver cannot
drive around.

**Two decisions I am overriding, and I want them on the record:**

1. **`08` F1 step 1 — *"Rule out arch rub / bottoming. Post-1.49, before diagnosing any
   balance problem: raise ride height 3–5 mm and re-test."*** This is step **one** of
   the session protocol, it has an "always first now" attached to it in A7, and it has
   **never been run on this car.** Three sheets in, we have gone straight to the diff
   every time.
2. **Rev B §7's ride-height decision, which is contradicted by its own metric.** Rev B
   declined to move ride height because *"minimum suspension heights at the worst
   corner sit 13–16 mm **above** the session's own bottoming reference."* The equivalent
   figures this session are **11–27 mm below it.** Same car, same circuit, three days
   apart, and the ride-height sliders did not move. **Either the reference method
   changed between app versions (likely — corner model v1→v2, detector v3) or the 13
   August conclusion was wrong. Either way it cannot be relied on**, and it was the
   whole basis for leaving the platform alone.

**The change: front 80 → 89 mm, rear 98 → 107 mm.** Both ends up 9 mm, so **rake is
held at +18 mm** — I am not using this to make a balance change through the back door.
Front goes 6% → 16% of range, rear 4% → 14%. Both are still in the bottom fifth of
their own sliders. **Ride height is free in PP** (`08` D2), so there is nothing to
re-check.

> **This is the largest single change any sheet has made to this car, and it is one
> family, deliberately.** It is also why nothing else moves — §7. If it works you will
> know within three laps, and §6 tells you exactly what to feel for.

## 2.3 Rank 2 — the exit, and the cheapest fix on the page

You named **loose on throttle exit** as your biggest single limitation. **I am ranking
it second, and I should say plainly that I am disagreeing with you on the ordering.**
The reason is arithmetic: four spins and the step-down behind them cost roughly 54
seconds of a race you finished P5 in, and the exit losses total about 0.9 s/lap of
in-corner inconsistency. Both are real. One is an order of magnitude larger.

**But the cheapest fix on this entire sheet belongs to your symptom, and it is not a
slider.**

> **You raced TCS 0. Rev B specified TCS 1 for the race.**

`08` B1's default is TCS 0 for qualifying, 1 for the race. Rev A overrode it to keep
the diff diagnosis clean; Rev B put it back and said *"practice still runs at 0."* It
did not go in the car. On a **606 bhp FR road car with an open-ish diff at night**,
running the session whose named limitation is exit traction with the traction control
you were given switched off is the single largest free change available. **Run it.**

**Where the exit actually costs you** — and note which corners are silent, because that
is `08` F2 question 2 and it localises this cleanly:

| Corner | Time loss / lap | Consistency | Brake peak | Wheelspin | What it says |
|---|---|---|---|---|---|
| **T5** (the hairpin) | **447 ms** | 168 ms | 7.8% | **14/14** | Worst clean corner. Also lowest ride heights on the car and kerb-strike 14/14. |
| **T10** | **369 ms** | **236 ms** | 38.0% | 14/14 | Heaviest brake + longest trail (504 ms) + lockup 9/14. This is the rank-3 corner. |
| T1 | 262 ms | 115 ms | 32.3% | 13/14 | Second brake zone. |
| T8 | 219 ms | 231 ms | 2.3% | 2/14 | Inconsistent without an obvious flag. |
| **T9** | **57 ms** | **45 ms** | 0.0% | **14/14** | **The silent corner.** Best on the lap — and the wheelspin flag fires on every lap. |

**T9 is the diagnostic.** It has `wheelspin` on 14 of 14 laps and it is simultaneously
the **most consistent and lowest-loss corner on the circuit**. Wheelspin that costs
57 ms is not wheelspin. What T9 also has is `kerb-strike` on 9 of 14 laps — and the
detector's own threshold note warns: *"a front wheel light over a kerb under throttle
reads as wheelspin on a rear-driven car."*

> **So the `wheelspin` flag is over-reading, badly, and the corners that actually cost
> you are the ones with a brake application in them.** T2, T6, T9 — no meaningful
> braking — are all fine. T5, T10, T1 — the three with real pedal — are the three that
> hurt. **That points at entry and the brake-to-throttle transition, not at steady-state
> traction, and it is a second independent argument for the platform.**

## 2.4 Rank 3 — front locking is Rev B's stack working, not failing

**This symptom is new.** On 13 August your complaint was *the rear* under braking.
This session it is *the front*, and `lockup` fires on 9 of 14 laps at T10 and 4 of 14
at T7 — both above the detector's threshold, where `countersteer` never gets there.

The mechanism is straightforward and it is the intended outcome: **lsd_b 18 → 22 gave
the rear axle enough decel-side authority that it no longer reaches its limit first.
So the front does.** That is what an A4 stack looks like when it lands. `01` §16
records the resolution you asked for: *mechanical rear stability first, then brake
balance around neutral as a fine adjustment* — and front locking with a settled rear
is exactly the condition where **brake balance +1 (rearward) becomes correct**, which
is the prize Rev B §5.4 flagged.

**I am not putting +1 on the sheet, for two reasons.** You also report the rear
stepping out on entry, and +1 makes that worse — shipping both would be shipping a
coupled pair silently. And brake balance is #7 in your change hierarchy and *last* in
F1's sequence, applied after the mechanical platform is right; the platform is what
this rev is changing. **Take +1 in the car if the front still locks once the ride
height is up** — §6, and it is test #4 in §8.

**One more thing about the front, and it is worth measuring rather than guessing.**
Your front tyres averaged **70.4–75.0 °C** over fifteen laps. GT7 fits a set at 70 °C.
**The front axle barely got above the temperature it arrived at.** Rears ran
77.6–85.0 °C. That is a −8.3 °C front-to-rear asymmetry and it is consistent with a
front axle that is never properly loaded. **No GT7 tyre working range has ever been
measured**, so I cannot tell you whether 73 °C is cold in absolute terms — the
`windowC: [85, 110]` in the export is real-world slick data and the export says so
itself. **But 3 °C above fitting temperature after fifteen race laps is a fact, and it
belongs in the backlog.**

## 2.5 Where the telemetry and your report disagree — four places, and what I am trusting

**This is the section that matters most, per standing rule 7.**

**1. Brake pressure. The channel says 38%; you say the pedal was the same as practice.
I am trusting you, and I am withdrawing a number from Rev B.**

13 Aug recorded **70.7%** peak at the heavy stop. This session's maximum *anywhere on
the circuit* is **38.0%**, and the corner that was the 70.7% stop reads **7.8%**. You
told me the pedal was unchanged. Nine-to-one is not a driver.

What changed is the app: **corner model v1 → v2 (8 corners → 10), `detectorVersion` 3,
appVersion 2.2.0.** The re-segmentation has moved braking events out of the corner
windows they used to sit in — you can see it directly in `brakePointM` at T5, which is
**208.6 m** before the apex, far outside any plausible corner window.

> **Consequence, and it is uncomfortable: Rev B's headline diagnosis leaned on the
> 70.7% figure as proof you were holding a third of the pedal back. That corroboration
> is withdrawn.** The diagnosis still stands, because it stood on your own verbatim
> report — *"[don't] trust brakes or throttle, car is too sketchy"* — which is primary
> evidence and the telemetry never was. **But `brakePeakPct` must never again be
> compared across app versions.** It is a within-session ranking, not a level.

**2. Rear instability on entry. You report it; `countersteer` fires on 2 of 14 laps at
three corners, below the detector's own 4-lap threshold. I am trusting you, and I am
not spending a slider on it.** Same reasoning as 13 August — a detector cannot log an
event you are avoiding — but with a difference: this time I think the cause is the
platform, so it is being addressed by rank 1 rather than by another 2 points of
`lsd_b`. If the platform lands and the entry is still loose, **rear expansion damping
34 → 32** is queued and free (§8).

**3. The exit ranking. You say exit traction is the biggest limitation; I have ranked
the platform above it.** Stated openly in §2.3. I am not smoothing this — if you think
I have it wrong after the platform run, say so and I will move the diff.

**4. Which way the diff is wrong — and this one is unresolved, so I am not touching
it.** On 13 August you said *"both rears went together — a snap"*, which is A5's second
failure mode and produced **accel 20 → 17**. But the temperature data, both then and
now, says something else:

```
  Lap  4   RR max 141.4 °C   ·  RL 82.1 °C     ← 59 °C split, one wheel
  Lap 13   RL max 132.4 °C   ·  RR 82.9 °C     ← 50 °C split, one wheel
  Lap 15   RL max 151.2 °C   ·  RR 89.3 °C     ← 62 °C split, one wheel
  Lap  5   RL 190.3 / RR 142.2                 ← both — but this is a full spin
  Lap 10   RL 112.9 / RR 113.3                 ← both, +30 °C, on a valid lap
```

**Three of the four spin laps show ONE rear wheel 50–62 °C above its pair.** That is
A5's *first* failure mode — inside rear lighting up alone — which points at accel
sensitivity being too **LOW**, the opposite direction to the change Rev B made. The 13
August temperatures had the same single-wheel character and Rev B read them as
generic "lock/slide events" without noticing.

> **I will not move `lsd_a` on this.** Two of the readings point one way, two point the
> other, and the whole reason Rev A refused to guess at this fork is that a session
> spent moving the wrong direction makes it worse. **Rev B §6 Run 2 asked you to watch
> the on-screen tyre indicators and that observation never came back. It is the single
> unanswered question blocking the differential, and it takes one corner exit to
> answer.** §6 and §9 both ask for it again.

---

# 3. The revised sheets

```
                                        RACE                    QUALIFYING
─────────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Soft ✅ MEASURED×2 Racing Soft
  Rear compound             Racing Soft ✅ MEASURED×2 Racing Soft
                            Settled. Covered 15 race laps with flat degradation. §5.1

SUSPENSION
  Body height      Front    89 mm ◄── · +14 · 16.5%  86 mm ◄── · +11 · 12.9%
                   Rear    107 mm ◄── · +12 · 14.1%  105 mm ◄── · +10 · 11.8%
                            rake held at +18 mm race / +19 mm quali
  Anti-roll bar    Front    5                       6
                   Rear     4                       5
  Damping compr.   Front    24     · +4  · 20.0%    25     · +5  · 25.0%
                   Rear     28     · +8  · 40.0%    30     · +10 · 50.0%
  Damping expan.   Front    40     · +10 · 50.0%    41     · +11 · 55.0%
                   Rear     34     · +4  · 20.0%    36     · +6  · 30.0%
  Natural freq.    Front    3.05 Hz · +117 · 64.3%  3.20 Hz · +132 · 72.5%
                   Rear     3.20 Hz · +120 · 63.2%  3.35 Hz · +135 · 71.1%
  Camber angle     Front    1.4°   · +14 · 23.3%    1.6°   · +16 · 26.7%
                   Rear     1.0°   · +10 · 16.7%    1.2°   · +12 · 20.0%
  Toe angle        Front    −0.05° · +95 · 47.5%    −0.05° · +95 · 47.5%
                   Rear     +0.10° · +110 · 55.0%   +0.08° · +108 · 54.0%

DIFFERENTIAL
  Initial torque            5      · +0  ·  0.0%    5      · +0  ·  0.0%
  Acceleration sens.        17 ⚠️  · +12 · 21.8%    19 ⚠️  · +14 · 25.5%
  Braking sens.             22 ⚠️  · +17 · 30.9%    20 ⚠️  · +15 · 27.3%
                            ⚠️ = unchanged, but the APP HAS THESE WRONG. §1.3
  [AWD]                     n/a — FR                 n/a — FR

AERODYNAMICS
  Downforce        Front    150    · +90 · 90.0%    160    · +100 · 100.0%
                   Rear     260    · +110 · 73.3%   275    · +125 · 83.3%
                            total 410 · 36.6% F      total 435 · 36.8% F

TRANSMISSION
  Max speed setting         300 km/h ⚠️  GENERATOR ONLY. Set FIRST, then never again.
  Final gear                3.600  · 53.3%           3.700  · 56.7%
  1st                       2.614                    2.614
  2nd                       1.948                    1.948
  3rd                       1.560                    1.560
  4th                       1.318                    1.318
  5th                       1.145                    1.145
  6th                       1.019                    1.019
                            ⚠️ Gearbox is CORRECT in the car and WRONG in the app. §1

BRAKES
  Brake balance             0  (− front / + rear)    0
                            Take +1 in the car if the front still locks. §2.4, §6

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)              100%
  ECU output                100%                     100%
  Ballast / position        109 kg / 0               109 kg / 0
                            ⚠️ App still says +20. Third session running. Fix by hand.

ASSISTS (not on the GT7 sheet — set in the menu)
  ABS                       Off                      Off
  TCS                       1 ◄── RACE. You ran 0.    0
  Countersteer assist       Off                      Off
═══════════════════════════════════════════════════════════════════
```

**Step sizes assumed:** ride height 1 mm, natural frequency 0.01 Hz, camber 0.1°, toe
0.01°, downforce 1 point, LSD 1, final gear 0.001, individual ratios 0.001.
**Where a click count and a percentage disagree, the percentage is the authority.**

**Nothing was clamped.** Two values sit at a hard limit and both are carried over
deliberately: `lsd_i` 5 at minimum (§7) and quali `df_f` 160 at maximum (§7).

---

# 4. Gearing — validated, and one free driving change

## 4.1 ✅ The Rev B gearbox worked, and the design was right to within 1%

Rev B predicted 6th would run *"~8,200 rpm at 278 km/h in clean air, limiter only in a
tow."* Measured: **8,152 rpm at 273.8 km/h, in 6th, and the limiter never fired.**

| | 13 Aug (Rev A box) | 16 Aug (Rev B box) |
|---|---|---|
| Max speed | 272.9 km/h | 273.8 km/h |
| Gear it was set in | **5th** | **6th** ✅ |
| Rpm there | 7,978 | 8,152 |
| Top gear reached limiter | — | **no** ✅ |

**6th went from a dead ratio you never once touched in seven laps to the gear that
sets your top speed.** That is the complaint fixed, and it is measured rather than
asserted.

## 4.2 ✅ K confirmed a second time, from a harder measurement

```
  13 Aug:  K = 1,101   from a limiter strike (8,856 rpm, gear 1)
  16 Aug:  K = 1,091   from 273.8 km/h at 8,152 rpm, 6th (1.019), fg 3.600
  ────────────────────────────────────────────────────────────────────
  Agreement: 0.9%.     K = 1,096 ± 1%     ✅ MEASURED ×2
```

The second reading is the harder case — it comes from a *non*-limiter point, where the
first came from a clean limiter strike — and it still agrees inside 1%. **Promote K
from "measured, ±2%, one telemetry point" to "measured, ±1%, two independent
sessions."** Every Shelby gearbox from here is a calculation.

## 4.3 The hairpin is still a 1st-gear apex — and Rev B's offer to fix that is withdrawn

Rev B §4.6 said: *"which gear you are in at the T6 apex. If it is still 1st, tell me
and I will shorten 2nd again."* The answer is **1st** — and **I am not shortening 2nd**,
because the question was framed on a number that has since moved.

**Careful: the corner model changed.** `cornerModel.version` went from 1 to 2 and the
auto-segmenter now finds **10 corners where it found 8**. The hairpin is **T5** in the
new numbering, not T6, and its recorded minimum speed dropped from **75.1 to 62.7 km/h**
while its exit speed stayed identical (87.6 → 87.3 km/h). **That is a re-segmentation,
not you going 12 km/h slower.** Comparisons across corner-model versions are unsafe and
I will stop making them.

At a genuine 62.7 km/h apex, 2nd gear sits at **3,536 rpm** on a flat-plane V8 that
makes its power at 7,500. **1st is correct there.** And the thing Rev B was actually
after did land: `gearAtExit` at T5 is **2**, which is where the torque multiplication
matters.

**But there is a free change at T4**, and it costs nothing:

| | T4 | T5 (hairpin) |
|---|---|---|
| Entry → min → exit | 87.9 → **81.5** → 97.5 km/h | 68.3 → **62.7** → 87.3 km/h |
| Gear now | **1** at apex, 2 at exit | 1 at apex, 2 at exit |
| `shiftsInCorner` | **1.00** | **1.00** |
| 2nd gear rpm across the corner | **4,957 → 5,499** ✅ | 3,536 ✗ too low |

> **Take T4 in 2nd, entry to exit. The current gearbox already covers it** — 2nd tops
> at 157 km/h and T4's entry is 87.9. That removes a mandatory mid-corner upshift from
> one of the two corners where `wheelspin` fires on 14 laps out of 14, and it costs
> nothing on the sheet. T5 keeps its 1st-gear apex and its upshift; there is no way
> round that one.

---

# 5. Strategy review

## 5.1 Was the binding constraint correctly identified? Yes in kind. No in consequence.

**Fuel did bind.** You finished with **1.8 litres** — about 0.3 of a lap — having
saved roughly 11% against the planned consumption. Tyres never came close: RS ran flat
for 15 laps at ~47% consumed against a ~50% cliff. **The model got the constraint
right.**

**And then it did the wrong thing about it.** It planned **two stops.**

> **In a timed race with zero mandatory stops, a pit stop is not a fuel solution. It is
> time stationary while the clock runs, paid for in laps.** The correct response to a
> fuel shortfall is to burn less. The model has no fuel-saving lever at all, so it
> reached for the only tool it has.

The arithmetic it should have run:

```
  Two stops           2 × (22 s pit loss + ~6 s refuel)        ≈ 56 s
  Saving 11% instead  ~0.27 s/lap × 15 laps  (C3: −20% ≈ −0.5 s/lap)  ≈ 4 s
  ─────────────────────────────────────────────────────────────────────
  No-stop wins by roughly 52 seconds.
```

**You declined thirteen calls and all thirteen declines were correct.** The lap-4
*"You can push"* was actively wrong on a fuel-critical no-stop plan. The stint shape —
**7 / 3 / 5** — is incoherent on its face: a three-lap middle stint in a fifteen-lap
race serves no purpose at all. And the lap-0 *"Green, green, green"* should not be in
the declined column; it is not a call.

## 5.2 Was the stint model right? No, in three specific ways.

**1. `fuelPerLapL: 7.563` was carried over from 13 August and was 12% high.** That
figure was measured at *practice pace with no saving*. It is not a race number.

```
  Measured this race:
    Race mean, tank to flag    (100 − 1.79) ÷ 15   =  6.548 L/lap  ← plan with this
    Median lap                                     =  6.751 L/lap
    Unsaved race laps (2–12)                       ≈  6.80  L/lap  ← worst case
    Deliberate save, laps 13–15                    =  4.44–5.95    ← the lever, measured
```

**The model needs a saveable range, not a point estimate.** You demonstrated a **34%**
single-lap saving on lap 14 (4.44 L). Even a modest constant 8% save changes the whole
plan, and the model cannot currently represent it.

**2. `degradationMsPerLap: 447.8` is an artefact, for the second consecutive session.**
13 August emitted 880.7 ms/lap and it was wrong. This time it is 447.8 and it is wrong
in the same way — a raw straight-line fit across a race containing four incidents and
a deliberate three-lap fuel save, with fuel not netted, tagged `confidence: low` by the
export's own accounting.

**The lap times settle it:**

```
  L2  1:57.724      L7  1:59.170      L11 1:59.624
  L3  1:57.318 ★    L8  1:59.557      L12 1:59.729
                    L6  2:00.073
```

**Laps 11 and 12 are as quick as laps 7 and 8**, on tyres seven laps older. There is no
slope. There is a **step of 2.1 seconds between lap 3 and lap 6** — which is precisely
where you spun twice — and then a flat line for seven laps.

> **That is not degradation. It is the two spins, and it never recovers.**
> A straight-line fit over a race with incidents in it is not a degradation
> measurement and should not be emitted as one.

**3. `fuelWeightSPerLPerLap: 0.003`, tagged `derived-not-measured`, is contradicted for
the second time.** Your fastest lap came on lap 3 with 86 L aboard; on 13 August it
came on lap 1 with a full 100 L. **Twice now, this car has been quickest on the
heaviest tank.** I will not claim the coefficient is wrong — it is confounded with
fresh rubber, and I cannot separate them from this data. **But it is 0 for 2, and one
twenty-minute test settles it** (§9.6).

## 5.3 Is the missing compound comparison worth the practice time? No.

You asked directly. **No — spend that time on the platform run instead.**

RS has now covered the race distance twice with flat degradation and roughly 47%
consumed at the flag against a ~50% cliff. The alternative compounds would be planned
on RS's own number, which is the honest gap the export flags — **but the decision is not
close enough for the measurement to change it.** The Laguna-measured RS→RH delta is
**1.412 s/lap**; over 15 laps that is 21 seconds spent to solve a problem you do not
have. **The compound is settled. Close the question.**

## 5.4 The plan for the next running

**No stop. Save from lap 1. Do not let the model talk you into the pit lane.**

```
  Expected pace with the platform up          ~1:58    (assume no gain, plan for 16 laps)
  Race window (finishAtS)                      1874.5 s  →  16 laps
  Unsaved requirement    16 × 6.80           = 108.8 L
  Tank                                       = 100.0 L
  ──────────────────────────────────────────────────────
  Saving required                            ≈ 8%      ← you demonstrated 34% on one lap
  Target                                      6.25 L/lap
```

- **Fuel map 2 from lap 1**, or short-shift the two long straights only. 8% is a much
  gentler ask than last time's 20% and it should cost well under 0.3 s/lap.
- **Map 4–6 whenever you are in a tow.** Close to free.
- **Map 1 when attacking, defending, or on the last lap.**
- **The lap-5 gate: if you have used more than 32 L after five laps, you will not make
  16.** Take one more map step immediately.
- **Splash fallback: laps 12–14, take only what you need.** ~22 s pit loss + ~5 s
  refuel = 27 s, against ~4 s of saving. It loses. It is there in case the gate fails.
- **Pit loss is 22 s, not the 20 s on the event page.** 19% of a measured 1:57.3 lap.
  Second confirmation. Fix the field.

---

# 6. What each change should feel like

**Ten minutes. Run them in this order.** The platform first, alone, because it is the
change and everything else is queued behind reading it.

### Run 1 — the platform, alone ⭐ (TCS 0, diff untouched at 17/22, bb 0)

**Where:** the hairpin (**T5**) first, then the heavy stop at **T10**, then anywhere you
put a wheel on a kerb — which this session was **eight corners out of ten**.

**Should feel like:** the car **absorbs** the kerb instead of skipping off it. At T5 you
should be able to run the same line without the rear going light on the exit kerb. At
T10 the front should build load progressively under the pedal rather than going from
grip to lock.

**Working:** you stop having moments you did not see coming. Concretely — **you complete
five laps without a spin.** That is the whole test, and it is a bigger prize than any
lap time on this sheet.

**Not working, and this is the failure mode on the other side:** the car feels **taller
and lazier** — more roll, slower to take a set, less immediate on turn-in. If that is
what you get, come back to **85 / 102** and tell me; there is a middle ground and I
would rather find it than lose your front end.

**Report:** how many laps you can run clean, and whether the front still locks at T10.

### Run 2 — TCS 1

Free, it is what the sheet already said, and it is aimed straight at your stated
biggest limitation. Practice at 0 so runs 1 and 3 stay clean; race at 1.

### Run 3 — the diff diagnosis Rev B asked for and never got ⭐

**This is not a change. It is one observation, and it is blocking the differential.**

On any exit that steps out, **watch the on-screen tyre indicators**:

| What you see | What it means | Where 17 goes |
|---|---|---|
| **One rear wheel alone** lights up, car bogs | accel sensitivity too **LOW** | **17 → 19** |
| **Both rears together**, arrives as a snap | accel sensitivity too **HIGH** | **17 → 15** |

The temperature data says the first (§2.5.4). Your 13 August report said the second.
**Until one of them wins, `lsd_a` does not move.** One corner exit answers it.

### Run 4 — brake balance +1, in the car, if the front still locks

Only after the platform is up. If the front is still locking at T10 with the ride
height raised, take **+1** and see whether the entry stays with you. **If it does, that
is the strongest evidence the A4 stack has ever had** — no ABS, a 5/5-severity braking
circuit, a 1,335 kg car, and rear brake bias. It is the prize Rev B flagged and it is
still on the table. **−1 remains the emergency response to a single genuine lock, not a
setup solution.**

---

# 7. What I deliberately left alone, and why

**Two parameters move on Rev C. Here is why the other twenty didn't.**

| Left alone | At | Why |
|---|---|---|
| **LSD acceleration** | 17 | **Undiagnosed, and the two evidence sources point opposite ways.** §2.5.4. Rev A refused to guess at this fork for good reason; Rev B resolved it on one line of driver report and the temperature data has never agreed. One observation (§6 Run 3) settles it. Moving it blind now would also confound the platform test. |
| **LSD braking** | 22 | **It worked.** The rear is no longer the axle that reaches its limit first — that is what the new front-locking symptom means. Going further risks the failure mode that matters for a trail-braker: the nose refusing to come round on the brakes. Held. |
| **Natural frequency** | 3.05 / 3.20 Hz | Tempting — 64% / 63% of range is stiff for a 1,335 kg road car, and `01` §11 records that stiffening this car costs grip and worsens throttle exit at Sainte-Croix. **But springs and ride height interact, and shipping both makes the platform test unreadable.** A7's order puts ride height at step 1 and frequency at step 5. Queued as §8 item 2. |
| **ARB** | 5 / 4 | `understeer-mid` fires above threshold only at T2 (7/14) and T3 (9/14), both fast corners with no braking, both cheap (150 ms, and T3 is incident-contaminated). Softening a bar to chase that would give up roll control on a car I have just raised. |
| **Damper compression** | 24 / 28 | Front 24 is your turn-in tool and the front is the axle now under scrutiny. A4 #4's tension applies: compression up is a rear-stability lever that takes your bite back, and it is last in the stack. |
| **Damper expansion** | 34 rear | **A4 #2, and the first thing I reach for if the entry is still loose after the platform.** Held as §8 item 1 rather than shipped, so the ride height stays a clean single change. Four clicks of floor left. |
| **Camber** | 1.4 / 1.0 | A1 points **down** for both your longitudinal complaints — front locking and exit traction are both longitudinal-grip failures and GT7 over-taxes camber against exactly those. **But A1 also says re-open camber upward after a wear measurement that beats the model, and RS has now beaten it twice.** The two arguments point opposite ways and neither is urgent. Deferred, and it is now genuinely ambiguous rather than merely unqueued. |
| **Toe** | −0.05 / +0.10 | Front toe on this car has **still** never been A/B'd, and A3 says GT7's behaviour here is disputed and possibly inverted. It is the top item in `08` Part G and it has been open since 10 August. It is a 20-minute test, not a race-sheet change. §9.5. |
| **Downforce** | 150 / 260 | No high-speed instability reported and none in the data. Rear downforce would add braking stability — **but it adds drag in a race you finished with 1.8 litres in the tank.** The fuel constraint vetoes it. 10 points of front headroom retained. |
| **Brake balance** | 0 | Front locking says +1 is now indicated, and entry looseness says it is not. **Coupled — so it goes in the car as a trim (§6 Run 4), not on the sheet.** `01` §16 and F1 step 13 both put it last. |
| **LSD initial torque** | 5 | At minimum, deliberately, third sheet running. Preload is the only diff parameter that cannot be aimed at a corner phase — it opposes turn-in everywhere at once. |
| **Gearbox** | Rev B set | **Validated to within 1% (§4.1).** The one thing on this car that is measured, correct, and finished. It is in the JSON only because the app's copy is wrong. |
| **Compound** | Racing Soft | Settled on two measurements. §5.3 |
| **Ballast / power / ECU** | 109 @ 0, 100/100 | Correct as built. The regs cap bhp and minimum weight, not PP; there is no trade to make. |

---

# 8. Three things to try next, in order, if Rev C is still not right

## ⭐ 1. Rear expansion damping 34 → 32 — if the entry is still loose

**A4 #2, and it has been queued since Rev B §8.1.** A rear that extends too fast on lift
unloads abruptly; slowing that rebound keeps load on the rear tyres through the trail
phase. **It is free** — it costs nothing on any other axis and does not touch the front.
Four clicks of floor left; take **32** first and **30** only if 32 clearly helped.

**Do this before you consider going past LSD braking 22.** With the front now locking,
`lsd_b` has nothing left to give without taking your turn-in.

## 2. Natural frequency down — if the platform helped but the car still skips over kerbs

**3.05 / 3.20 Hz is 64% / 63% of this car's own range**, on a floor of 1.88 / 2.00 Hz —
this car can go far softer than any Gr.3 machine and never has. `01` §11 records
Sainte-Croix directly: *"changes that stiffened the car or removed rear security created
grip loss over bumps and worsened throttle exit."*

**Take a full 0.20 Hz off both ends — 2.85 / 3.00 — not a click.** A7's diagnostic is
explicit that frequency problems need large changes and that small damper tweaks doing
nothing is normal post-1.49. **But only after the ride height is settled**, or you
cannot read either.

## 3. LSD acceleration, once §6 Run 3 has answered which way

**19 if one rear lights alone. 15 if both go together.** Not before.

## And the fourth, which has been open since 10 August

**Front toe A/B: −0.05 / 0.00 / +0.05**, three clean laps each, Data Logger on. It is
the #1 item in `08` Part G, it has never been run on any car, and it is now more
relevant than it has ever been because **the front axle is the one with the new
symptom.** Twenty minutes.

---

# 9. Delta table

| Parameter | As run | Revised | Why |
|---|---|---|---|
| **Ride height — front** | 80 mm | **89 mm** | Rank 1. 80 mm is **6% of a 75–160 mm range**; `08` B1's "3–5 clicks above minimum" was written for Gr.3 cars with a 25 mm span, where the same clicks are 20%. F1 step 1 — *raise ride height and re-test before diagnosing any balance problem* — has never been run on this car. Front reaches 212–215 mm against a 226 mm straight-line reference. §2.2 |
| **Ride height — rear** | 98 mm | **107 mm** | Same change, same family, **coupled** — both ends up 9 mm so rake is **held at +18 mm** and this is not a balance change in disguise. The rear-right uses **26.7 mm more travel than in a straight line**, at a corner with `kerb-strike` on 14 of 14 laps. Rear is 3 mm off its floor on 85 mm of adjustment. §2.2 |
| **TCS** | 0 *(as raced)* | **1 — race only** | **Not a change — the sheet already said this and it did not go in the car.** `08` B1's race default, aimed directly at your stated biggest limitation, on a 606 bhp FR road car at night. Practice still runs at 0. §2.3 |
| LSD acceleration | **17** | 17 | ⚠️ **Unchanged — but the app holds 20.** Resent as a record correction. Undiagnosed; see §2.5.4 and §6 Run 3. |
| LSD braking | **22** | 22 | ⚠️ **Unchanged — but the app holds 18.** Resent. It worked; the front is now the limiting axle. §2.4 |
| Max speed setting | **300** | 300 | ⚠️ **Unchanged — but the app holds 330.** Resent. Generator only; set first, never again. |
| Final gear + all 6 ratios | **Rev B set** | unchanged | ⚠️ **Unchanged — but the app holds the Rev A box.** Resent in full. Validated to 1% (§4.1). |
| Brake balance | 0 | 0 | Front locking indicates +1; entry looseness indicates not. Coupled, so it goes in the car as a trim, not on the sheet. §2.4, §6 Run 4 |
| Compound | Racing Soft | Racing Soft | Settled on two measurements. §5.3 |
| Ballast position | 0 *(app says +20)* | **0** | ⚠️ No change. Third session the export has got this wrong. Fix by hand. §1.2 |
| *Everything else* | — | *unchanged* | §7 |

---

# 10. Qualifying sheet

**Yes, the diagnosis moves it, and by the same amount.**

- **Ride height 78 / 97 → 86 / 105.** Eight millimetres at each end, rake held at
  +19 mm. Slightly less than the race lift because quali carries no fuel load and no
  stint to survive — **but the platform argument applies more to qualifying, not less**,
  because a one-lap run attacks kerbs harder than a race stint does.
- **Everything else in the quali column is unchanged from Rev B.** The diff is
  undiagnosed on both sheets and moves on neither.
- **The same five record corrections apply** — `lsd_a` 19, `lsd_b` 20, `top` 300,
  `fg` 3.700 and the full gear set. I do not know which quali sheet the app is
  holding, and this set converges to the right answer whether it holds Rev A's or
  Rev B's.
- **TCS stays 0** for qualifying, per B1.

> ⚠️ **This event is a grid start with no qualifying session.** The quali column exists
> for time trial, for a future round here, and so the two sheets do not drift apart.
> **You do not need to enter it today.**

---

# 11. Range check

Every changed value against the ranges read off this car on 13 Aug 2026.

| Parameter | Range | Race | Quali | Margin |
|---|---|---|---|---|
| Ride height — front | 75 – 160 mm | **89** | **86** | ✅ 14 above min, 71 below max |
| Ride height — rear | 95 – 180 mm | **107** | **105** | ✅ 12 above min, 73 below max |
| LSD acceleration | 5 – 60 | 17 | 19 | ✅ |
| LSD braking | 5 – 60 | 22 | 20 | ✅ |
| Max speed | 200 – 800 km/h | 300 | 300 | ✅ generator only |
| Final gear | 2.000 – 5.000 | 3.600 | 3.700 | ✅ |
| LSD initial | 5 – 60 | 5 | 5 | ⚠️ **AT MINIMUM — deliberate, §7** |
| Downforce F | 60 – 160 | 150 | **160** | ⚠️ **QUALI AT MAXIMUM — deliberate, §7** |

**Nothing was clamped.** The two values at a hard limit are both carried over
deliberately and justified in §7.

**Individual gear ratios remain the one thing I cannot range-check** — GT7's per-gear
limits are clamped by neighbouring gears and shift with Maximum Speed. The box is
already in the car and correct, so this only matters if you have to re-enter it.

---

*Rev C issued 16 Aug 2026 · GT7 v1.70 · no BoP · ranges verified on this car 13 Aug 2026*
*Two changes, one family: the platform. Everything else held — §7.*
*Five values and six ratios resent as record corrections, not changes — §1.3.*
*The gearbox is validated to 1%. The differential is undiagnosed and does not move.*
*Driver profile: front-end-led precision attacker · neutral brake bias · low tolerance for rear snap · ABS Off*
