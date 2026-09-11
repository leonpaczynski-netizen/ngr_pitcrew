# Lamborghini Huracán GT3 '15 · WeatherTech Raceway Laguna Seca
### 20 laps · 2× tyre · 3× fuel · no mandatory stop · standing start · dry

**Generated 10 Aug 2026 · GT7 v1.70 · no BoP, open tuning · 525 bhp / 1300 kg**
**Rev E — fuel measured. Tyres are the binding constraint, not fuel. Fuel map 1 all race.**
Driver profile: front-end-led precision attacker · ABS Weak · TCS 0

**Car ranges used:** Body height F 55–80 / R 60–90 mm · Natural frequency 3.00–5.00 Hz · Downforce F 350–450 / R 500–700

> **Revision history**
> **Rev A** — first draft, relative values.
> **Rev B** — absolute values, car ranges supplied by driver.
> **Rev C** — LSD acceleration **18 → 14** after driver test resolved power-on mid-corner understeer.
> **Rev D** — Race compound **Racing Hard → Racing Soft** after RS measured at 11–12 laps at 2×. Strategy rebuilt around **fuel** as the binding constraint.
> **Rev E (10 Aug 2026)** — **Fuel measured: 19.5 laps at FM1, 3×.** That is far better than modelled and it **reverses Rev D's central conclusion.** Fuel does not bind; **tyres do.** Race now runs **fuel map 1 throughout** with a splash at the tyre stop. All fuel-saving technique is withdrawn — it was going to cost ~0.5 s/lap for nothing.

---

## 0. READ THIS BEFORE THE SETUP

### 0.1 Both constraints are now measured. Here is where they actually sit.

| | Modelled (Rev A–C) | Measured | Verdict |
|---|---|---|---|
| **Tyres** — Racing Soft @ 2×, race pace, full fuel | ~6–7 laps | **11–12 laps** | Model 1.8× pessimistic |
| **Fuel** — FM1 @ 3×, full tank | 17–19 laps *(in map 2)* | **19.5 laps** *(in map 1)* | Model materially pessimistic again |

**Read the fuel row carefully: 19.5 laps is the figure in the *richest* map.** The modelled 17–19 was for map 2, which is ~8% leaner. Like-for-like the model was out by roughly 20–25%.

**Two things follow immediately.**

**1. A stop is still certain, and it is now certain twice over.**

- Tyres: 11–12 laps against a 20-lap race. Cannot be done on one set.
- Fuel: 19.5 laps against 20 in FM1. Half a lap short.

There is no no-stop strategy. Good — that removes the decision entirely and lets everything else be optimised around a single planned stop.

**2. But the stop is a TYRE stop now, not a fuel stop — and that changes how you drive every lap.**

Rev D had you short-shifting and lift-and-coasting from lap 1 to stretch fuel. **All of that is withdrawn.** Short-shifting costs ~0.5 s/lap; over 20 laps that is roughly **10 seconds thrown away to solve a problem you do not have.** Run map 1 and take the fuel you need in the box, where it costs a fraction of a second.

### 0.2 The fuel arithmetic, in full

At 19.5 laps per 100 L tank in FM1 at 3×:

```
Consumption          100 L ÷ 19.5 laps        = 5.13 L/lap  (FM1, 3×)
Whole race           20 laps × 5.13 L         = 102.6 L
Tank                                            100 L
Shortfall                                     = 2.6 L  ≈ half a lap
```

**At the stop (end of lap 10):**

```
Used in stint 1      10 laps × 5.13 L         = 51.3 L
Remaining                                     = 48.7 L  ≈ 9.5 laps
Needed for stint 2   10 laps                  = 51.3 L
Minimum splash                                = 2.6 L   (~3% of tank)
RECOMMENDED splash                            = ~10 L   (~10% of tank)
```

**Take ~10 L, not the bare 2.6 L.** At roughly 0.5–1.0 s per 10% of tank that is half a second to a second in the box, and it buys you an extra lap and a half of cover for a safety car, an extra formation lap, or a stint you have to stretch. The bare minimum leaves you finishing on fumes with zero margin for anything going wrong — a bad trade for half a second.

**Use the in-game diamond marker as the check.** It is accurate, and it will tell you exactly what you need at the moment you are sitting in the box. The arithmetic above is what to *expect*; the diamond is what to *do*.

### 0.3 One caveat on the 19.5 figure

It came from the **in-game fuel calculator**, which is accurate but projects your *current* pace forward. Race pace is not practice pace:

- Defending, following in dirty air and running off-line all raise consumption.
- The opening two laps of a standing-start race are the thirstiest of the event.
- Conversely, a lap spent in a tow is cheaper than a clean lap.

**Half a lap of margin on a 20-lap race is thin enough that this matters.** Watch the counter over the first three green laps. If it is tracking worse than 5.13 L/lap, the response is **not** to switch to map 2 for the whole race — it is to take a bigger splash at the stop, which costs a tenth or two instead of half a second a lap.

### 0.4 One number still needs re-reading

**PP 738.66 is the stock figure.** With the restrictor at 70 and 70 kg aboard, the real number reads far lower. If your league runs a PP cap, read it in-game before committing. **Note the Rev D compound change moved PP** — Racing Soft costs more than Racing Hard — and **re-check after setting downforce**, because aero moves PP non-monotonically. Suspension, gearing and LSD values remain free.

### 0.5 One place I am overruling the generic track advice

Standard Laguna guidance is **brake bias two clicks forward** — T11 is downhill, heavy, and you are already turning. I am **not** doing that:

- Your profile rejects front-biased brake balance as a permanent solution and requires the rear be stabilised mechanically.
- **Forward bias loads the front-right harder, and the front-right is this circuit's limiting tyre.** With tyres now the binding constraint on the race, that argument is stronger than it was, not weaker.

Stability comes from **LSD braking sensitivity** instead. Brake balance stays at 0.

---

## 1. THE SHEET — absolute values

```
═══════════════════════════════════════════════════════════════════════════
  LAMBORGHINI HURACÁN GT3 '15  ·  WEATHERTECH RACEWAY LAGUNA SECA
  Rev E
═══════════════════════════════════════════════════════════════════════════
                                    RACE                  QUALIFYING
───────────────────────────────────────────────────────────────────────────
TYRES
  Front compound                    Racing Soft           Racing Soft
  Rear compound                     Racing Soft           Racing Soft

SUSPENSION
  Body height        Front          64 mm                 61 mm
                     Rear           72 mm                 69 mm
                     (rake)         +8 mm                 +8 mm
  Anti-roll bar      Front          5                     6
                     Rear           3                     4
  Damping compr.     Front          27                    28
                     Rear           27                    28
  Damping expansion  Front          44                    44
                     Rear           36                    37
  Natural frequency  Front          3.30 Hz               3.45 Hz
                     Rear           3.45 Hz               3.60 Hz
  Camber angle       Front          1.0°                  1.3°
                     Rear           1.0°                  1.2°
                     (see §7.4 — 1.2/1.1 now worth testing)
  Toe angle          Front          0.00°                 0.00°
                     Rear           +0.06°                +0.05°

DIFFERENTIAL
  Initial torque                    6                     6
  Acceleration sensitivity          14  ← VALIDATED       14  ← see §9
  Braking sensitivity               26                    24

AERODYNAMICS
  Downforce          Front          425                   450
                     Rear           695                   675
                     (front share)  38%                   40%

TRANSMISSION  (speed at limiter in each gear)
  Max speed setting                 set LOW first, then final drive
  1st                               96 km/h               92 km/h
  2nd                               136 km/h              130 km/h
  3rd                               172 km/h              166 km/h
  4th                               205 km/h              200 km/h
  5th                               234 km/h              230 km/h
  6th                               258 km/h              254 km/h
  Final gear                        trim last to land the above
                                    (6th is now free — see §3)

BRAKES
  Brake balance                     0                     0
                                    (− = front, + = rear)

PERFORMANCE ADJUSTMENT
  Power restrictor                  70                    70
  ECU output                        97                    97
  Ballast                           70 kg                 70 kg
  Ballast position                  −25                   −15

FUEL
  Map                               1 (all race)  ← Rev E 1
  Splash at stop                    ~10 L                 n/a

ASSISTS
  ABS                               Weak                  Weak
  TCS                               0                     0
  Countersteering assist            Off                   Off
═══════════════════════════════════════════════════════════════════════════
```

**Nothing mechanical changed in Rev E.** The fuel measurement changed how the car is *driven* and *raced*, not how it is built. The one knock-on to the sheet is gearing — see §3.

**Ride height sanity check.** Front 64 sits 9 mm above your 55 mm floor (36% of the window); rear 72 sits 12 mm above the 60 mm floor (40%). Both deliberately mid-low rather than minimum — post-1.49, running the floor is actively slow and risks arch contact, which physically prevents the car steering. The 8 mm positive rake is modest on purpose: rake promotes entry rotation, and this car already has more yaw commitment than you want at the Corkscrew.

**Natural frequency sanity check.** 3.30/3.45 sits in the bottom quarter of your 3.00–5.00 window. Your Fuji RSR **race** setup ran **3.35/3.45**, quali 3.50/3.60. This is marginally softer, and Laguna has 55 m of elevation where Fuji is flat.

---

## 2. WHY — every deviation from baseline

| Parameter | Value | Why |
|---|---|---|
| **Racing Soft (race)** | **RS** | ✅ **Measured: 11–12 laps at 2× at race pace.** Two 10-lap stints fit with 1–2 laps of margin. The Hard's durability buys nothing and costs ~1.4 s/lap. |
| **Fuel map 1** | **FM1 — Rev E** | ✅ **Measured: 19.5 laps at 3×.** Fuel does not bind the race; the stop is forced by tyres regardless. Running lean would surrender ~0.5 s/lap to solve a problem that does not exist. |
| **Body height 64 / 72** | above floor | Laguna is an **elevation track first**, medium-high downforce second. The Corkscrew crest-then-plunge is the constraint: you land on a descent with the car light. |
| **Natural frequency 3.30 / 3.45** | bottom of window | Same reason — *do not run your stiffest springs here despite the downforce.* Your Sainte-Croix Shelby lesson applies directly. |
| **Front ARB 5** | softer | Your proven front-bite move, validated on the RSR at Fuji. More front mid-corner grip without touching the rear. |
| **Rear ARB 3** | soft end | Rear grip is this car's scarce resource. Softer bar = more rear mechanical grip = less scrub = more stint. |
| **Rear compression 27** | softer | The Corkscrew landing. A stiff rear bump makes the car skip on touchdown and refuse to turn at 8A. |
| **Front expansion 44** | **firmer** | The one deliberately firm damper. The front must extend over the T8 crest and find the road at 8A. |
| **Rear expansion 36** | softer | Your lift-off stability lever. Laguna's second half is all descending, lightly-loaded direction changes. |
| **Camber 1.0 / 1.0** | low — **now conservative** | Set low partly against a front-right wear limit that proved softer than modelled. Probably leaving mid-corner grip on the table. Test 1.2/1.1 — §7.4. |
| **Rear toe +0.06** | minimal | Toe is the largest alignment contributor to wear and the rear is the weak axle. Stability bought from LSD braking sensitivity instead. |
| **LSD acceleration 14** | ✅ **VALIDATED** | Was 18/22 on the theory that Laguna's T11 exit wants 20–28. Wrong for this car: 18 produced power-on mid-corner understeer through T2–T5 from lap 1. **14 fixed it completely.** Confirm on Softs — §7.5. |
| **LSD braking 26** | **up from 20** | The primary lever, doing the work brake bias would otherwise do. T11 is a heavy downhill stop **while turning in**, on ABS Weak, in a high-yaw-inertia car. Walk it — §7.3. |
| **Rear downforce 695** | near max | The cheapest rear grip in the game — no wear penalty. **Stronger justification in Rev E:** tyres now bind the race and drag costs you nothing you need, because fuel has margin. |
| **Front 425 race / 450 quali** | rear-biased in race | Race at 38% front share runs a little more stability into T1, T6 entry and T9. Quali maxes the front for turn-in. |
| **Brake balance 0** | neutral | Overruling the generic "two clicks forward." See §0.5. |

---

## 3. GEARING — and 6th is now free

**Do not touch the Max Speed slider after setting individual ratios.** It regenerates the box and wipes them. Order: Max Speed hard left → final drive → individual gears → final drive to trim.

- **You will use 5th at most, and 6th barely.** No straight of consequence — the pit straight is short and the rest of the lap is 2nd to 4th.
- **2nd is the money gear.** It covers **T2 (Andretti)** and **T11** — the two slowest corners, and T11 exit feeds the only real straight and the only overtaking approach. Get 2nd right and the rest is detail.
- **3rd** covers T5 and T10. **4th** covers T6 (uphill) and T9 (Rainey).
- Final-drive optimisation is worth **less** than getting 2nd right.

> **⚠️ Rev E changes the 6th-gear brief.** Rev A–D said *"6th exists for fuel, not speed"* — the idea being that a tall 6th drops revs on the pit straight and saves consumption. **With 19.5 laps of fuel against a race that stops at 10, that rationale is gone.** Gear 6th for whatever is fastest, or ignore it entirely. If you are not reaching it, shorten the final drive a click and take the extra acceleration everywhere else — there is no longer a fuel reason to protect a tall top gear.

**Three things pushing the lower gears longer than instinct suggests:**

1. **Standing start, 525 bhp, MR, TCS 0**, and Laguna races *"are usually decided in the first two corners."*
2. 2nd is the traction-control gear, and lengthening it is GT7's single most effective wheelspin fix. Your Fuji telemetry logged 22 wheelspin events in a lap; do not import that here.
3. **The restrictor at 70 makes this worse, not better** — see §5. You have proportionally more corner-exit torque than the peak power figure suggests.

**Racing Softs partially offset all three.** More rear grip means less wheelspin for a given gear. If 2nd feels lazy out of T2 on Softs, shortening it one click is now a legitimate option rather than a trap.

**Validate against actual pull.** Note the speed you genuinely reach before the T2 braking marker with a tow, and which gear you are in at T2, T5, T6, T9, T10 and T11. Your Fuji lesson — 271 km/h actual against a 300 km/h nominal target — is why this step is not optional.

---

## 4. BALLAST — −25, and it held up

70 kg at **−25** (moved from −50 in Rev B). Laguna's limiter is the **front-right**, and it is predominantly left-handed (T2, T5, T8, T9, T11), so the outside-front carries the sustained load. Full-forward ballast on a front-limited circuit buys rear life with the axle that was going to fail first anyway.

**Status:** ran without any looseness complaint, and the mid-corner push that did appear turned out to be diff-driven. **Provisionally validated — but never A/B'd against −50.** That comparison is still open and is now clean, since the diff confound is gone.

**Revert to −50 at rear-limited, traction-dominated circuits** — Monza, Red Bull Ring, Gilles-Villeneuve.

**If you go back to −50:** add **+0.10 Hz front natural frequency** (3.40 race / 3.55 quali) and **+1 mm front ride height** (65 / 62) to support the extra front load.

---

## 5. RESTRICTOR AND ECU

**Restrictor 70 / ECU 97 is the correct combination for this circuit.**

| | Power Restrictor | ECU Output |
|---|---|---|
| Mechanism | Restricts airflow | Electronic limit across the rev range |
| Curve effect | **Cuts top-end, largely preserves low-end torque** | Scales the **entire** curve proportionally |
| Right for | Twisty, traction-limited track | Fast tracks where predictability matters more |

Laguna has no straight of consequence and lives in 2nd, 3rd and 4th. **You are paying for the restriction in top speed you barely use and keeping the corner-exit torque that sets your lap time.** ECU at 97 is doing almost nothing (a 3% proportional trim) and should stay there.

**The consequence — and it is why 18 was too much diff lock.** A heavily restricted engine has **proportionally more low-end torque relative to its peak power** than an unrestricted one. On an MR car, with TCS 0, out of a sequence of slow corners, that is more wheelspin and more power-on push than the 525 bhp headline implies. **The restrictor setting and the LSD acceleration value are coupled: if you ever move the restrictor, re-test accel sensitivity.**

> **A note on the restrictor and fuel.** The restrictor should be buying economy as well as PP — a restricted engine burns materially less than an unrestricted one. The measured 5.13 L/lap at FM1/3× works out to about **1.71 L/lap at 1×**, or roughly **47.5 L/100 km** over the 3.6 km lap. For reference, the best Gr.3 cars measure around 41.4 L/100 km. So this build is around 15% thirstier than a class-leading Gr.3 despite the restriction — unsurprising for a 5.2 V10, and useful to know: **do not assume the restrictor will bail you out on fuel at a circuit with a real straight.** Laguna is forgiving because there is nowhere to use the top end.

---

## 6. STRATEGY — rebuilt on two measured numbers

### 6.1 The plan

**Two stints of 10 laps on Racing Soft. Fuel map 1 throughout. One stop, end of lap 10, for tyres — with a ~10 L splash while you are stationary.**

| | |
|---|---|
| RS life at 2×, race pace, full fuel | **11–12 laps (measured)** |
| Fuel range, FM1, 3×, full tank | **19.5 laps (measured)** |
| Stint length required | 10 laps |
| **Tyre margin per stint** | **1–2 laps** |
| **Fuel margin** | **Ample — with a splash at the stop** |
| **What forces the stop** | **Tyres** |
| Pit loss | ~18–20 s (~23% of a lap), plus ~0.5–1.0 s for the splash |

### 6.2 What changed, and what it is worth

Rev D had you saving fuel from lap 1. **Withdraw all of it:**

| Technique | Rev D | Rev E | Worth |
|---|---|---|---|
| Fuel map | Start map 2, ready for 3 | **Map 1, all race** | ~4% power, every lap |
| Short-shifting | Primary tool, from lap 1 | **Off** as a fuel tool | **~0.5 s/lap ≈ 10 s over the race** |
| Lift and coast into T2/T11 | Standard | **Off** | Braking-point consistency back |

**That is the single largest gain in this revision and it comes from deleting instructions, not adding them.** You were about to pay a lap-time tax every lap of the race to solve a constraint that does not exist.

**Keep one of them in reserve.** Short-shifting also **reduces rear tyre wear** by keeping the V10 out of peak torque on exit. Tyres are now what binds you, and the margin is only 1–2 laps. So: **race in map 1 and shift normally, but if a stint gets scrappy or you are held up and forced to defend, short-shifting on exit for the last two or three laps is the correct tool** — used as a tyre-management measure, not a fuel one.

### 6.3 The stop

**End of lap 10. Racing Softs. ~10 L of fuel.**

The diamond marker on the fuel gauge will tell you the exact requirement. Take it plus a lap of margin. Do not take the bare minimum — see §0.2.

**The undercut is strong and track position is expensive.** ⚠️ *[Re-flagged 11 Sep 2026, history: the undercut is weak in GT7 - a cold out-lap of 0.5–1.5 s plus a long pit delta (`CLAUDE.md` §5.4), and a fresh-tyre out-lap measured 1.41 s slower at Deep Forest. See `05`'s banner.]* Overtaking is realistically T2 only, plus the occasional Corkscrew move that ends in tears. **Within about a second of the car ahead at lap 9 — pit first ⚠️ *[re-flagged 11 Sep 2026: history - the undercut is weak in GT7]*.** Fresh Softs plus full power on the out-lap into T2 is the strongest weapon you have all race.

**Watch for the field stopping late.** Anyone who modelled their fuel the way I did will believe they are fuel-limited and plan around a fuel window. If the pack stops on a different lap to you, that is why — and it is an opportunity, not a signal that you have got it wrong.

### 6.4 The thin margin is now on tyres alone

**1–2 laps of headroom per stint is workable but it is not slack.**

- **A 10/10 split is the only sensible one.** An 11/9 split puts the first stint at the measured fall-off point. Available as a reaction to a rival, not as a plan.
- **You have no cover for a late safety car.** If the race is neutralised near your window, pit immediately rather than gambling.
- **Sloppy laps are expensive.** Lateral slip is the dominant wear source post-1.49, and the Soft is more sensitive to it than the Hard. **If you can hear the tyres, you are eating the margin.** Squeal is free telemetry — treat a noisy lap as a warning, not a fast lap.

### 6.5 Brake balance migration

Start at 0. As the front-right goes off, **move one click rearward (+1)** to shift work onto the fresher rears and extend front life. That is the correct direction and it is the opposite of the reflex. If T11 becomes frightening, −1 is available — but treat that as a symptom that LSD braking sensitivity needs to come up, not as the fix.

### 6.6 TCS and the start

TCS 0 for the race. On Softs over a 10-lap stint the case for adding it late is weak — reassess only if T11 exit gets loose in the closing laps of a run.

**The start is the exception.** Standing, 525 bhp, MR, TCS 0, restrictor-fattened low-end torque, **now in map 1**, and a race decided in the first two corners. Softs help. **Consider TCS 1 for the launch lap only** — the downside is close to zero and the downside of a bogged or spinning start is the race.

---

## 7. THINGS TO TEST — updated for Rev E

One change per run, three clean laps. If you can't feel it and the Data Logger can't see it, put it back.

**1. Front toe — A/B it. Still not done, and it is now the top item on the list.**
Run **−0.05 / 0.00 / +0.05**, three clean laps each. GT7's front toe behaviour is genuinely disputed and may be inverted relative to real-world expectation, and it sits directly on your number-one priority. This car has never had it tested. **Never front toe-in.** Both strategy unknowns are now closed — this is where the remaining lap time is.

**2. The Corkscrew landing — ride height and front expansion.**
Does the car **skip and refuse to turn at 8A** (too stiff, or arch contact — raise front ride height to 67 mm and re-test before anything else), or does it **bottom on the landing** (too soft — front expansion up before spring rate)? This corner decides whether you like the car.

**3. LSD braking sensitivity — walk it.**
26 is an estimate, not a measurement. Move in **+2 steps** and watch both failure modes:
- Rear still loose into T11 → keep going up.
- **Car stops wanting to turn in at T10 and the Corkscrew** → too far; back off 2 and take the rest from rear expansion damping.

**4. Camber up to 1.2 / 1.1.**
Camber was set to 1.0/1.0 partly to protect a front-right wear limit that turned out softer than modelled. With a 10-lap stint on Softs there is probably room to buy mid-corner grip back. Watch the braking zones — GT7 taxes camber against longitudinal grip, and braking is your weapon. If stopping distance or stability degrades at all, revert. **Do not go past 1.5.**

**5. Confirm accel 14 still reads right on Softs.**
14 was validated against the Rev C build. Racing Softs add grip at both axles, so the balance should carry — but if the car now feels like it is **failing to convert throttle into drive out of T11** (as opposed to pushing wide mid-corner), 16 is available. **The failure modes are different and must not be confused:** pushing wide mid-corner on throttle = too much lock, go down; inside rear spinning up on exit = too little lock, go up. Watch the tyre indicators.

**6. Ballast −25 vs −50**, now that the diff confound is gone. Three clean laps each. Watch mid-corner push at T5 and T9, and front-right wear across a full 10-lap stint.

**7. NEW — verify fuel consumption under race conditions, not practice conditions.**
The 19.5 came off the in-game calculator projecting practice pace. Run three laps in traffic or while defending and see whether 5.13 L/lap holds. **This is a 10-minute check on a number with only half a lap of margin.**

---

## 8. WHAT TO BRING BACK

- **Confirm the RS number over a full race stint** — 11–12 came from one run. Does it repeat with traffic, tow and defending?
- **Which corner/tyre went first on the Softs** — the model assumed front-right, the car's reputation says rear. **Nobody has checked. Top remaining measurement.**
- **Real-race fuel consumption** vs the 5.13 L/lap practice figure (§7.7).
- **Whether front toe-out helped or hurt** — settles a contested GT7 parameter for this car permanently.
- **Whether camber 1.2/1.1 costs braking** (§7.4).
- **Whether −25 ballast is actually better than −50** (§7.6).
- **The car's remaining slider ranges** (ARB, damper, LSD, toe, camber, gearing) so future sheets can be absolute from the first draft.

---

## 9. TEST LOG

### Test 1 — LSD acceleration sensitivity · 10 Aug 2026 · ✅ VALIDATED

| | |
|---|---|
| **Symptom (driver)** | *"Car is understeering and not rotating mid corner."* |
| **Phase** | **On throttle / power-on.** Neutral until throttle was picked up, then ran wide. |
| **Corners** | **T2, T3, T4, T5** — the first-sector sequence. Notably **not** T11. |
| **Onset** | **From lap 1, cold or hot.** Not degradation-related. |
| **Build state** | Sheet as written (Rev B), including ballast −25, front toe 0.00. |
| **Diagnosis** | Excessive acceleration lock. A mid-corner push that is *coasting* is a front-grip problem; a mid-corner push that is *power-on* is an accel-LSD problem. The symptom split cleanly on the second branch. |
| **Change** | **LSD acceleration 18 → 14.** Single change, isolated. |
| **Result** | **Fixed completely.** Driver: *"lsd change sorted it perfect."* |

**Why 18 was wrong:** I set it by splitting the difference between the MR baseline (15) and generic Laguna guidance (20–28 for T11 exit). The generic guidance is written for an unrestricted car; a restrictor-70 engine has proportionally more early-exit torque, and T2–T5 are picked up on throttle with steering still wound on. The track norm was solving a T11 problem this car didn't have, at the cost of every corner that mattered.

**The absence of T11 from the symptom list was the diagnostic tell** — it was the corner the value had been aimed at, which meant the value was right where it was pointed and wrong everywhere else.

**Changes NOT made:** front ARB 5→4 and front downforce 425→450 were queued as fallbacks. Neither was needed. Both would have masked a power-on problem by adding front grip.

**Generalisation:** treat **14 as the Huracán's accel-sensitivity starting point on any traction-limited, slow-corner circuit with a restrictor fitted** — below the MR baseline of 15, not above it.

⚠️ Provenance gap: run against a Hards-spec sheet; a confirmation pass on Softs is queued (§7.5).

---

### Test 2 — Racing Soft tyre life at 2× · 10 Aug 2026 · ✅ MEASURED

| | |
|---|---|
| Compound / multiplier | Racing Soft, 2× |
| Conditions | **Race pace, full-fuel start** |
| **Result** | **~11–12 laps before fall-off** (22–24 laps of 1× wear) |
| Model said | ~6–7 real laps |
| **Model error** | **~1.8× pessimistic. Measured Soft ≈ modelled Hard.** |

**Decision:** race compound changed **Racing Hard → Racing Soft**. The measured RS→RH delta at Laguna is **1.412 s/lap** — roughly **28 seconds over 20 laps, more than a full pit stop.** The Hard's durability advantage buys nothing once two 10-lap stints fit inside the Soft's life.

**What went wrong in the model:**

1. **The elevation penalty was invented.** I added wear because Laguna has 55 m of climb. Plausible physics, no data. **Withdrawn** — do not carry it to Bathurst or Sainte-Croix.
2. **Compound-ratio assumptions untested.** The model used RH ≈ 1.4× RM. Only RS has been measured, so the ladder is still uncalibrated. One RM run here would fix that cheaply.
3. **A reputation used as a number.** The Huracán's "2nd worst in the MR field" ranking is a 2019 GT Sport test at 10× on Hards — relative, stale, different settings. It was being treated as an absolute stint length.

---

### Test 3 — Fuel range at 3× · 10 Aug 2026 · ✅ MEASURED

| | |
|---|---|
| Fuel map | **1** (richest) |
| Multiplier | **3×**, race settings |
| Method | **In-game fuel calculator**, projecting practice pace |
| **Result** | **19.5 laps on a 100 L tank** |
| Derived consumption | **5.13 L/lap** at FM1/3× · ~1.71 L/lap at 1× · ~47.5 L/100 km |
| Model said | 17–19 laps **in map 2** — i.e. ~20–25% pessimistic like-for-like |

**This reversed Rev D's central conclusion.** Rev D had declared fuel the binding constraint and built the whole race around saving it. It is not binding. **Tyres are**, and they were the binding constraint all along — Rev D just had the wrong number for fuel.

**Decisions taken:**

- **Fuel map 1 for the entire race.** No map stepping.
- **Short-shifting and lift-and-coast withdrawn as fuel techniques** — worth ~0.5 s/lap, or about **10 seconds across the race**, surrendered for nothing.
- **Short-shifting retained as a *tyre* tool** for the closing laps of a stint if the margin gets thin.
- **~10 L splash at the tyre stop**, not the bare 2.6 L minimum — half a second in the box for a lap and a half of cover.
- **6th gear freed** from its fuel-saving brief (§3).

**The pattern across all three tests, and it is the finding worth keeping:**

> **Every modelled constraint on this sheet was pessimistic, and every one of them was pessimistic in a way that would have made the car slower.** Tyre life by 1.8×. Fuel range by ~20–25%. Both errors pushed toward a harder compound, a leaner map, more saving, more conservatism — a car and a race plan built to survive limits that were not there.
>
> **Two practice runs, maybe thirty minutes total, were worth roughly 38 seconds of race time** (28 s of compound delta plus ~10 s of unnecessary fuel saving). Nothing else in this document has that return.
>
> **Standing rule: measure both constraints before building the strategy, every event.** Not after. The setup follows from the constraints, and getting them wrong distorts everything downstream — compound, camber, aero, gearing, and how you drive every lap.

**Caveat carried forward:** the 19.5 is a calculator projection off practice pace, and race pace is thirstier. With only half a lap of margin over the full distance, verify it in traffic (§7.7). The response to a worse number is a bigger splash at the stop, **not** a leaner map for the whole race.
