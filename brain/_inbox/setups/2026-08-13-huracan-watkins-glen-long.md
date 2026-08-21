# Lamborghini Huracán GT3 '15 · Watkins Glen International — Long Course
### 20 laps · 2× tyre · 3× fuel · 1 mandatory stop · standing start · dry (sun/cloud only)

**Generated 13 Aug 2026 · GT7 v1.70 · no BoP, open tuning · target 540 bhp / 1285 kg**
**Rev A — first run of this combination. No session, lap or stint on file for this car at this circuit.**
Driver profile: front-end-led precision attacker · ABS Weak · TCS 0 · Fanatec DD Extreme 18 Nm, ClubSport V3 load cell
Priority this round: **Balanced — quali grid and race pace.** Per `08-playbook-leon.md` C2 this is the *"sprint, 1 mandatory stop, 20–40 min"* row → **race car set for mid-stint, quali sheet genuinely separate.**

**Car ranges used:** verified, read off this car's own settings screen 13 Aug 2026. Full register entry written to `11-car-slider-ranges.md`.

---

## 0. READ THIS FIRST — three things that decide the round

### 0.1 The build is the biggest single change on this sheet, and it invalidates the one measured LSD number you own

You are currently running **medium turbo + restrictor 70 + ECU 99 = 536 bhp.** I am recommending you throw that away.

**Recommended package: no turbo (NA), power restrictor 99 %, ECU output 94 %, ballast 55 kg.**

Three reasons, in order of size:

1. **Watkins Glen is a 70 %-full-throttle circuit and a restrictor cuts exactly the part of the curve you use here.** `08-playbook-leon.md` D3 is explicit: restrictor for twisty/traction-limited tracks, ECU for fast ones. Laguna was the former. The Glen is the latter — two very long full-throttle sections, 5th-gear esses, only three slow-to-medium corners on a 5.4 km lap. Restrictor 70 is taking a 30 % bite out of the top end on the one circuit where the top end sets the lap.
2. **The turbo is distorting the torque curve in the direction that fights your driving style.** A medium turbo fattened, then clipped back by a heavy restrictor, gives you a hump-shaped delivery: strong mid, flat top. Your profile's non-negotiable #4 is *progressive* exit traction with early partial throttle (5–20 %). A boosted-then-restricted curve is the opposite of progressive, and per **D3.1** it is the exact mechanism that made accel LSD 18 too much lock at Laguna.
3. **NA + a light ECU trim is the closest available thing to the factory GT3 curve** — 576 bhp scaled proportionally to ~540. Predictable, linear, information-rich. That is what the profile asks for and it is what a fast circuit wants.

> ### ⚠️ The consequence you must not miss
> **D3.1 rule 1: re-test LSD acceleration sensitivity after every restrictor change, and re-gear. Treat them as one job.**
> The validated **accel 14** from Laguna was validated *on a restrictor-70 build*. Removing the restrictor removes the low-end torque bias that made 14 correct. **14 does not carry over.** This sheet starts at **18** and §5 gives you the walk. Do not assume either number.

### 0.2 Stop chasing 540 bhp — it is worth about 0.05 s/lap and you are paying attention tax for it

576 bhp base. ECU steps in 1 % increments, so 94 % lands ≈ 541 and 93 % lands ≈ 536. Neither is exactly 540, which is why you have been stuck.

**Use ECU as the coarse tool and the restrictor as the vernier.** ECU 94, then walk the restrictor down 1 % at a time until the garage reads 540 or just under — expect **restrictor 99**. A 1 % restrictor trim removes 1 % of a top end you have plenty of; it does not reintroduce the curve distortion that restrictor 70 was causing.

The difference between 536 and 540 bhp is **0.7 %**. On a 1:45 lap that is roughly **0.05 s**. The turbo decision above is worth an order of magnitude more. Land under the limit, confirm it is legal, and move on.

### 0.3 Refuelling — not tyres, not pit loss — is the strategic event this round

At 1 L/s, **every litre you save is one second in the pit lane.** That exchange rate is exact and it is the whole strategy.

Estimated consumption at the Glen (derivation in §6.2) is **~8.7 L/lap at FM1 / 3×**, against a 100 L tank. That is **~11.5 laps of range** on a 20-lap race, and it means you must take on roughly **74 L — about 74 seconds stationary.** The declared 20 s pit loss is real but it is a rounding error next to that.

**So the fuel measurement is the highest-value 20 minutes of your practice, ahead of the tyre run.** At Laguna the fuel model was 20–25 % pessimistic and the tyre model 1.8 × pessimistic; both errors made the car slower. Measure both (§7), and note that unlike Laguna, **fuel-saving technique probably pays here** — the arithmetic is in §6.4.

---

## 1. THE SHEET

```
═══════════════════════════════════════════════════════════════════════════════
  LAMBORGHINI HURACÁN GT3 '15  ·  WATKINS GLEN INTERNATIONAL — LONG COURSE
  Rev A · 13 Aug 2026 · GT7 v1.70
═══════════════════════════════════════════════════════════════════════════════
                                     RACE                  QUALIFYING
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound                     Racing Soft *         Racing Soft
  Rear compound                      Racing Soft *         Racing Soft
                                     * pending §7.1 — do not lock this in

SUSPENSION
  Body height        Front           63 mm                 61 mm
                                     32 % · +8 clicks      24 % · +6 clicks
                     Rear            72 mm                 70 mm
                                     40 % · +12 clicks     33 % · +10 clicks
                     (rake)          +9 mm                 +9 mm
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
  Acceleration sensitivity           18   ← NOT validated  20
  Braking sensitivity                28                    26

AERODYNAMICS
  Downforce          Front           415                   435
                                     65 % of range         85 % of range
                     Rear            620                   660
                                     60 % of range         80 % of range
                     (front share)   40.1 %                39.7 %
                     (total)         1035                  1095

TRANSMISSION  (speed at limiter in each gear)
  Max speed setting                  300 km/h              300 km/h
                                     (generator — set FIRST, never touch again)
  1st                                110 km/h              110 km/h
  2nd                                150 km/h              150 km/h
  3rd                                184 km/h              184 km/h
  4th                                214 km/h              214 km/h
  5th                                256 km/h              256 km/h   ← fixed by the esses
  6th                                288 km/h              274 km/h   ← only quali change
  Final gear                         3.550                 3.550

BRAKES
  Brake balance                      0                     0
                                     (− = FRONT bias · + = REAR bias)

PERFORMANCE ADJUSTMENT
  Turbocharger                       NONE (run NA)         NONE (run NA)
  Power restrictor                   99 %                  99 %
  ECU output                         94 %                  94 %
  Ballast                            55 kg                 55 kg
  Ballast position                   −25                   −50

FUEL
  Map                                see §6.4 decision     1
  Refuel at stop                     ~74 L (≈74 s)         n/a

ASSISTS
  ABS                                Weak                  Weak
  TCS                                1 for launch lap → 0  0
  Countersteering assist             Off                   Off
═══════════════════════════════════════════════════════════════════════════════
```

**Ride-height sanity check.** Front 63 mm sits 8 mm above the 55 mm floor, rear 72 mm sits 12 mm above the 60 mm floor. Neither is near minimum, deliberately: the track reference is explicit that *"the compression at the top of the esses will bottom a very low car at 250 km/h, which post-1.49 is genuinely destabilising."* The car also has +5 mm of rake built into its own minimums, so the quoted **+9 mm rake** is only +4 mm of *added* rake — modest on purpose, because this is a high-speed direction-change circuit and your profile says the car cannot be knife-edge here.

**Natural-frequency sanity check.** 3.55 / 3.70 Hz is 27.5 / 35.0 % of the 3.00–5.00 Hz window. That reads soft as a percentage and it is not — the RSR register entry showed this window's *floor* is already race-stiff, so **anchor in absolute Hz, not percent of range.** For calibration: Laguna race ran 3.30 / 3.45 (deliberately soft for the Corkscrew), Fuji RSR race ran 3.35 / 3.45. This sheet is **0.25 Hz stiffer than Laguna at both ends** — the esses need a platform Laguna did not.

---

## 2. WHY — every deviation from the baseline sheet

Values at baseline (`08-playbook-leon.md` B1) are not explained. Values that differ are.

| Parameter | Value | Why |
|---|---|---|
| **Turbo removed, restrictor 99 / ECU 94** | NA | §0.1. A 70 %-full-throttle circuit is the wrong place to run a 30 % restrictor. ECU scales the whole curve; restrictor guillotines the part the Glen actually uses. This also removes the low-end torque bias that made accel 14 correct at Laguna. |
| **Ballast 55 kg** | not 70 | 1230 kg stock + 55 = 1285 kg exactly. The 70 kg in the brief header is stale from the Laguna sheet and would put you 15 kg over minimum for nothing. Your own note is the correct one. |
| **Ballast −25 race / −50 quali** | split | The Glen's limiter is the **front-left** (predominantly right-handed at speed). Same logic that moved Laguna from −50 to −25: do not load the axle that fails first. Quali has no stint to protect, so −50 buys front bite and calms the high-speed platform — **and gives you the −25 vs −50 A/B for free** (backlog G7). If you would rather have identical balance in both sessions, run −25 in both and lose the comparison. |
| **Body height 63 / 72** | above floor | Esses compression at 250 km/h + severe Bus Stop kerbs. Post-1.49 arch contact physically prevents steering; running the floor here is actively slow. 2 mm higher than quali because 100 L of fuel sits the car down. |
| **Natural frequency 3.55 / 3.70** | +0.25 Hz vs Laguna | *"Medium-stiff springs for the esses platform."* High-speed flowing archetype wants a firm controlled platform. Still nowhere near the top of the window — the Bus Stop kerbs are unavoidable and a launched exit is a lap-ender. |
| **Front ARB 6** | baseline, **not** your usual 5 | Your proven front-bite move is front ARB 5. **I am not using it here.** Mechanical grip is poorly rewarded at the Glen — you use it three times a lap — and softening the front bar at a 250 km/h direction-change circuit costs roll control where the lap actually is. **Front bite comes from aero (40 % front share) and low front compression damping instead**, which are the correct high-speed tools per A2. |
| **Rear ARB 4** | +1 vs Laguna | The Glen needs more total roll stiffness than Laguna for rapid direction changes, while keeping the same 2-point front-biased split for high-speed stability. Rear grip is not the scarce resource here — the front-left is. |
| **Front compression 26** | low end | A2 #1: lower front compression is the most underrated turn-in tool in GT7 and it costs nothing elsewhere. This is where the front response comes from on this sheet. |
| **Rear compression 24** | very soft | **Track-reference lever #3 at this circuit: rear compression damping for the Bus Stop kerbs.** *"A launched Bus Stop exit is a common lap-ender."* 24 is the bottom fifth of the window and it is deliberate. |
| **Front expansion 42** | firm-ish | The esses climb has compressions at the top where the car goes light at high speed. The front must extend and find the road on the far side. Same reasoning that put Laguna at 44; slightly less because the Glen's crest is gentler than the Corkscrew. |
| **Rear expansion 36** | low | A4 #2. A rear that extends too fast on lift unloads abruptly — and the Glen's whole boot section is lightly-loaded direction change. |
| **Camber 1.4 / 1.2** | **up from Laguna's 1.0 / 1.0** | A1's second failure mode: camber gets set low defensively against a wear budget that turns out bigger than modelled, and that is unpaid-for lap time. The Glen is the most sustained-lateral-load circuit this car will see — 5th-gear sweepers are exactly where camber earns. **Flagged: watch braking.** GT7 taxes camber against longitudinal grip and you have three heavy stops here. If T1 or the Bus Stop stopping distance degrades at all, come back to 1.2 / 1.1. **Do not go past 1.5.** |
| **Front toe 0.00** | unchanged, deliberately | A3's A/B (−0.05 / 0.00 / +0.05) is the top item on the backlog and it is still open on this car. **The Glen is the wrong place to run it** — front toe beyond ±0.05° introduces steering oscillation at speed, and this circuit is 250 km/h direction changes. Your own profile also calls for *"less aggressive front toe-out than on slower circuits."* Run the A/B at a slow circuit; run 0.00 here. |
| **Rear toe +0.08** | +0.02 vs Laguna | Mild rear toe-in is the standing high-speed-circuit rule for this driver. Slightly more than Laguna because the esses and the Bus Stop entry need rear security at speed and it is cheap. Quali +0.06 — no stint to protect and it costs straight-line speed. |
| **LSD acceleration 18** | ⚠️ **not validated** | Laguna's **14** was measured on a restrictor-70 build and does not carry over (§0.1). Generic Glen guidance says 22–28 — three traction-limited exits all feeding long full-throttle sections. But that guidance assumes an unrestricted max-PP car *and* it is the exact class of advice that caught us out at Laguna. **18 is deliberately between the two**, above Laguna's 14 because the low-end fattening is gone, below the track norm because the esses and the Chute are picked up on throttle with steering still wound on. **This is test #1.** |
| **LSD braking 28** | +2 vs Laguna's validated 26 | A4: this is your entire on-brake rear-stability toolkit and it is doing the job brake bias would otherwise do. The Bus Stop is *"from very high speed, slightly downhill, with severe kerbs — the hardest stop on the lap"*, on ABS Weak, in a high-yaw-inertia car. 26 held at Laguna with no entry complaint; the Glen asks for more. |
| **Downforce 415 / 620** | rear trimmed hard | Med-Low requirement, ~70 % full throttle, two long straights, a big tow, and a fuel bill that is the strategic event this round. Rear at 60 % of range is a real trim off the near-max 695 you ran at Laguna. **Front share 40.1 %** — one notch more front than Laguna's 38 % because the esses need the nose to respond at 5th-gear speed. **Not maxed**: 450/500 would be a 47 % front share and would make this circuit nervous. |
| **Downforce 435 / 660 (quali)** | more total | Opposite logic to Laguna's quali. There, race needed rear grip for tyre life so quali trimmed it. Here, race is trimmed for drag and fuel, so **quali adds it back** — one lap, no fuel bill, and the esses are the lap. |
| **Brake balance 0** | overruling the track guide | Generic Glen advice is *"one to two clicks forward"* for the Bus Stop's downhill approach. **Not doing it.** Your profile rejects front-biased balance as a permanent answer, and forward bias loads the front-left harder — which is this circuit's limiting tyre. Stability comes from LSD braking 28. **Escape hatch in §6.6.** |
| **TCS 1 for the launch lap** | not 0 | Standing start, ~540 bhp, MR, TCS 0, and a wide T1 where the race is decided. Downside of TCS 1 for one lap is close to zero; downside of a spun start is the race. Drop to 0 once clear. |

---

## 3. GEARING — built from the esses and the Bus Stop, not from a top-speed number

**Order of operations. This is GT7's #1 gearbox error and it will cost you the session if you get it wrong.**
`Max Speed slider FIRST (it is a generator — touching it wipes every individual ratio) → final drive to scale → individual ratios → final drive to trim. Never touch Max Speed again.`

### 3.1 The constraint that outranks everything else: **5th must span the entire esses**

The track reference is unambiguous — *"5th must carry the esses without a shift; if you find yourself shifting in the middle of the esses, your ratios are wrong and you will lose the car. This is the most important gearing note at the Glen."*

The esses (T2–T4) are 5th-gear commitment corners over a climb with a compression at the top. A mid-esses upshift or downshift at 230 km/h with the car going light is how you end a lap.

**So the box is built outward from 5th:**

- **5th tops at 256 km/h** — above the fastest point in the esses with the tow and the quali aero on.
- **4th tops at 214 km/h** — deliberately *below* the slowest point in the esses, so there is never a reason to be in 4th up there. That places the 4→5 crossover safely under the esses' speed floor.
- **This intentionally breaks the diminishing-increment rule.** The 4→5 gap is 42 km/h against 30 km/h for 3→4. The cost is a slightly lazy pull out of the Boot in 4th. The benefit is that you never shift in a 250 km/h commitment corner. **Take the trade.**

### 3.2 The slowest corner sets 2nd, not 1st

The slowest point on the Long Course is the **Bus Stop chicane / Toe of the Boot complex** — a genuine 2nd-gear stop. **2nd tops at 150 km/h**, which is long by instinct and correct by evidence:

- Lengthening 1st/2nd/3rd is GT7's #1-ranked fix for exit traction limitation, ahead of every LSD and suspension change (A6).
- Your Fuji telemetry logged **22 wheelspin events in a single lap**. Do not import that here.
- The Bus Stop exit feeds the run to the final turn and then the pit straight. It is one of three exits that sets a lap.

**1st tops at 110 km/h and exists only for the standing start.** No corner uses it. A long 1st is the cheapest launch insurance you have with TCS 0.

### 3.3 The longest straight sets 6th — and it is the only quali/race difference

The back straight with a tow is where 6th lives. *"6th tops out with a tow at the Bus Stop board."*

- **Race 6th: 288 km/h.** Geared for the tow, because there will be one — the Glen has a big slipstream and a wide T1, and track position is moderately cheap here.
- **Quali 6th: 274 km/h.** You are alone. Shortening 6th by 14 km/h recovers acceleration on the run to T1 and to the Bus Stop board that a tow-geared 6th throws away.

**Everything else is identical between the two sheets**, because the esses constraint fixes 5th, 5th fixes the final drive, and the final drive fixes the rest. That is not laziness — it is the constraint doing its job.

### 3.4 Starting ratios and the health warning

The speeds at the limiter above are **the specification**. The ratios below are a starting box computed from an assumed gearing constant (limiter ≈ 8,500 rpm, rolling circumference ≈ 2.05 m → K ≈ 1045). **⚠️ K is assumed, not measured for this car.**

| Gear | Race ratio | Quali ratio |
|---|---|---|
| 1st | 2.677 | 2.677 |
| 2nd | 1.963 | 1.963 |
| 3rd | 1.600 | 1.600 |
| 4th | 1.376 | 1.376 |
| 5th | 1.150 | 1.150 |
| 6th | 1.022 | **1.075** |
| Final | 3.550 | 3.550 |

**Dial the final drive until the on-screen speeds match the table in §1, then re-check 5th against the esses.** If the ratios land the speeds wrong, the speeds win — the ratios are the estimate.

### 3.5 Validation, in the car — do this on your first three laps

1. **Which gear are you in through the esses?** It must be 5th, the whole way, with no shift. This is the only gearing question that matters.
2. **Actual speed at the Bus Stop board**, clean air and with a tow. Note both. Your Fuji lesson — 271 km/h actual against a 300 km/h nominal target — is why a target number is not a specification.
3. **Which gear at each of the three real exits:** T1 exit onto the esses, Bus Stop exit, final turn onto the pit straight. Bus Stop should be 2nd.
4. **Is 6th reached at all?** If you never touch it in the race, shorten the final drive a click and take the acceleration everywhere else.

*Backlog: doc 13's `gearingConstantK` field would make every future gearbox on this car exact instead of iterated. One reading in top gear at the limiter.*

---

## 4. THE BUILD — what to actually do in the garage

| Step | Action |
|---|---|
| 1 | **Remove the turbocharger.** Run NA. |
| 2 | **Power restrictor → 100 %, ECU output → 94 %.** Read the bhp figure. |
| 3 | If it reads over 540, **walk the restrictor down 1 % at a time** (expect 99 %). Do not touch ECU again. |
| 4 | **Ballast 55 kg.** Confirm the weight reads 1285 kg. If it reads over, you have weight-reduction stages fitted that the 1230 kg stock figure does not account for — recompute. |
| 5 | **Ballast position −25** (race) / **−50** (quali). |
| 6 | **Re-gear** (§3). Mandatory after a power-curve change of this size. |
| 7 | **Re-test LSD acceleration** (§5, §7.3). Mandatory, same reason. |

### 4.1 The alternatives, since you said you are open to any package

| Package | Verdict |
|---|---|
| **NA + ECU 94 / restrictor 99** | ✅ **Recommended.** Closest to the factory GT3 curve. Predictable, linear, full top end, no low-end distortion. Right answer at a 70 %-full-throttle circuit. |
| **High RPM turbo + heavier trim to 540** | 🔬 **Worth one A/B if you have spare practice time.** Pushes peak power up the rev range and weakens the bottom — theoretically good for TCS-0 traction out of the three slow exits and for the top of 5th and 6th. **Cost: lag and a peaky delivery that directly fights "early partial throttle, 5–20 % opening."** Your Shelby experience with a peaky flat-plane V8 is the cautionary precedent. Not the sheet's recommendation, but a legitimate test. |
| **Medium turbo + restrictor 70 (current)** | ❌ Wrong circuit for it. This is a Laguna package. |
| **Low RPM turbo** | ❌ Actively wrong here. Fattens the low end you can barely use and makes the wheelspin and power-on-push problem worse. |

---

## 5. THE DIFFERENTIAL — the one number on this sheet I am least confident about

**Initial 6 / Acceleration 18 / Braking 28** (race). Quali **6 / 20 / 26**.

**Acceleration 18 is an engineering judgement, not a measurement**, and it is the parameter most likely to be wrong on this sheet. Here is the reasoning laid out so you can correct it fast:

| Input | Says |
|---|---|
| MR layout baseline | 15 |
| **Measured on this car at Laguna, restrictor-70 build** | **14** ✅ |
| Generic Watkins Glen track guidance | 22–28 |
| D3.1: removing the restrictor removes the low-end fattening | **push 14 upward** |
| D3.1 hypothesis: an ECU-heavy build may want *more* lock than a restrictor-heavy one at the same power | **push upward** (untested) |
| Laguna lesson: track guidance is written for unrestricted max-PP builds and over-specified lock by 4–14 points | **discount 22–28** |
| This driver's demonstrated sensitivity to power-on push | **start low, prove upward** |

**18 splits it, biased toward your side of the argument.** The direction rules, which you must not confuse:

- **Car pushes wide mid-corner *while you are on throttle*** → too much lock → **come down in 2-point steps.** This is the Laguna signature. Watch for it at the Chute, the Outer Loop and the Toe of the Boot — the corners you pick up on throttle with steering still wound on.
- **Inside rear lights up alone on exit** → too little lock → **go up in 2-point steps.** Watch the on-screen tyre indicators; do not guess between these two.
- **Both rears let go together, feels like a snap** → too much lock → come down.

**And ask yourself the four questions before changing anything** (`F2`): where is your right foot, which corners *and which corners are fine*, from lap 1 or does it develop, and is the car built as written. The silent corner localises the fault in one step — that is what T11 did at Laguna.

---

## 6. STRATEGY

### 6.1 The plan

**Two stints of 10 laps on Racing Soft. One stop at the end of lap 10 — tyres plus a ~74 L refuel. Fuel map per §6.4.**

| | |
|---|---|
| Race distance | 20 laps ≈ 35 min at ~1:45 |
| RS life at 2×, race pace, full fuel | **~10–12 laps** ⚠️ **ESTIMATED — measure it (§7.1)** |
| Fuel range, FM1, 3×, 100 L tank | **~11.5 laps** ⚠️ **ESTIMATED — measure it (§7.2)** |
| Stint length required | 10 laps |
| **Stop window (fuel-capacity bounded)** | **end of lap 9 to end of lap 11** |
| Refuel required, whole race | **~74 L ≈ 74 s stationary** |
| Pit loss | **20 s declared — see §6.5** |
| **What forces the stop** | **The regulation.** One mandatory stop. Both constraints then land close together. |

### 6.2 Where the fuel number comes from, and why it is the number to measure

There is no Glen data on file, so this is transferred from the one fuel measurement you own:

```
Laguna, measured 10 Aug 2026   5.13 L/lap @ FM1, 3×, on a 3.602 km lap
                             = 1.71 L/lap @ 1×
                             = 47.5 L/100 km   (on a restrictor-70, 525 bhp build)

Watkins Glen Long              5.4 km lap, ~70% full throttle vs Laguna's 2nd–4th gear character
                               and now ~540 bhp unrestricted — both push consumption up
Estimate                       52–56 L/100 km  →  2.8–3.0 L/lap @ 1×
                                               →  8.4–9.1 L/lap @ 3×
Central estimate               8.7 L/lap  →  100 L ÷ 8.7 = 11.5 laps of range
```

**The arithmetic that matters, and note the result is independent of when you stop:**

```
Whole race        20 laps × 8.7 L        = 174 L
Tank                                       100 L
Must be refuelled                        =  74 L
At 1 L/s                                 ≈  74 seconds stationary
```

Stop-lap bounds: you need ≤ 11.5 laps of fuel after the stop → **stop no earlier than end of lap 9**. You need ≤ 11.5 laps before it → **stop no later than end of lap 11.**

> ⚠️ **The knowledge base's track record on this exact calculation is bad.** The Laguna fuel model was 20–25 % pessimistic and the tyre model 1.8 × pessimistic, and both errors pointed toward a slower car. **Assume this estimate is wrong until you have measured it.** The measurement takes ten minutes and the whole race plan hangs off it.

### 6.3 The tyre estimate, and the decision rule

Track reference: *"Moderate-high, left-side biased… the front-left is the limiter. Expect 15–18 laps at 1×."* Those figures are conservative — the same class of figure at Laguna understated measured RS life by roughly 1.8×.

Applying that correction gives **~10–13 laps on RS at 2×**. That covers a 10-lap stint, but the margin is thin enough that it must be measured, not assumed.

**Decision rule after the stint run in §7.1:**

| Measured RS life at 2× | Do this |
|---|---|
| **≥ 11 laps** | **RS both stints.** 10/10 split. Confirmed plan. |
| **9–10 laps** | RS with a strict 10/10 split and disciplined driving — squeal is free telemetry and you have no slack. Or take RM if you expect to be racing in traffic. |
| **< 9 laps** | **RM both stints.** Accept the lap-time delta; a third stop is not available under a 1-stop regulation without wrecking the race. |

**Standing rule, from `08-playbook-leon.md` C3.1: no modelled wear figure may be used to select a race compound.** One run, at the multiplier you will actually race. That rule exists because ignoring it cost 28 seconds at Laguna.

### 6.4 Fuel map — and why the answer is probably the opposite of Laguna

At Laguna, Rev E **withdrew** all fuel saving: it cost ~0.5 s/lap to solve a constraint that did not exist. **Do not import that conclusion here.** The Glen inverts it, and the reason is one number:

> ### **At 1 L/s refuelling, 1 litre saved = 1 second of pit lane. Exactly.**

That is the exchange rate. Any technique that saves more litres than it costs seconds over 20 laps is a win. Work it out after you measure:

| Technique | Saves | Costs | Net (on the 8.7 L/lap estimate) |
|---|---|---|---|
| **Fuel map 2** (≈ −8 % consumption, ≈ −2 % power) | ~14 L ≈ **14 s** in the box | ~0.2–0.3 s/lap ≈ **4–6 s** | **+8 to +10 s** ✅ |
| **Fuel map 3** (leaner still) | ~25 L ≈ **25 s** | more power, harder to defend with | marginal — test before committing |
| **Short-shifting the three slow exits** | ~5–8 L ≈ **5–8 s** | ~0.2–0.4 s/lap ≈ **4–8 s** | **≈ break-even** ⚠️ |

**Note the short-shifting row carefully — it does *not* transfer from the generic 20 % figure.** That figure assumes a stop-start circuit. At the Glen you spend ~70 % of the lap at full throttle in a high gear, where short-shifting has nothing to work on. **Fuel map is the primary saving tool here precisely because it works everywhere, including at full throttle.**

**Recommendation pending measurement: start the race in FM2.** If your measured consumption comes in materially better than 8.7 L/lap, re-run the table — under about 7.0 L/lap the refuel drops toward 40 s and FM1 becomes defensible again.

**Keep short-shifting in reserve as a *tyre* tool**, not a fuel one — it keeps the V10 out of peak torque on exit and buys rear life in the closing laps of a stint if the margin gets thin.

### 6.5 Pit loss — confirming the 20 s, as asked

**It is plausible but it is the app default, and it has never been measured here.** The track reference puts the Glen at **20–22 s, confidence medium.** For planning, **use 21 s.**

**Then stop worrying about it.** Against a ~74 s refuel, a 1–2 s error in pit loss changes nothing you would decide differently. **The numbers that decide this race are consumption per lap and the 1 L/s refuel rate** — get those right and the pit-loss figure is noise.

Measure it anyway on a practice run (five minutes, backlog item 10): note the lap time of a normal lap and the lap time of the in-lap plus out-lap minus stationary time. Send it back and it goes into the register permanently.

### 6.6 Brake balance migration

**Start at 0.** As the front-left degrades through the second half of each stint, **move one click rearward (+1)** to shift work onto the fresher rear axle and extend front life. That is the correct direction and it is the opposite of the reflex.

**The Bus Stop escape hatch.** If the rear is genuinely unstable on the downhill entry and it is costing you the corner, **−1 is available in-session**. But treat it as a *symptom that LSD braking sensitivity needs to come up*, not as the fix — and take it back out once you have walked the diff. Going forward of neutral is not acceptable as a permanent answer on this car.

### 6.7 TCS and the start

**Quali: TCS 0.** No argument.

**Race: TCS 1 for the launch lap, then 0.** Standing start, ~540 bhp, MR, TCS 0, a wide T1 that is the best overtaking spot on the lap, and 19 more laps riding on not spinning it. TCS 1 costs near-nothing and catches the worst of it. Drop it once you are through T1 and settled.

**If T1 exit or the final turn gets loose in the closing laps of a stint**, TCS 1 is a legitimate reaction — but per B1, *if you need TCS 3 or more, the diff or the gearing is wrong.*

### 6.8 Racecraft notes

- **Track position is moderately cheap here.** Big slipstream on the back straight, wide T1. Overtaking is realistic. That argues against burning the race on a defensive strategy.
- **The undercut is weaker than at Laguna** because the stop is dominated by a 74-second refuel, not by pit loss. You cannot undercut someone by 74 seconds. **Strategy this round is about not running out, not about timing.**
- **Watch for rivals stopping outside laps 9–11.** Anyone who does either has a materially different consumption figure or has made an error. Either way it is information.
- **The Bus Stop is the lap-ender.** Severe kerbs, downhill entry from very high speed. More races are lost there than won at T1.

---

## 7. THREE THINGS TO TEST FIRST — ranked

One change per run. Three clean laps minimum. Record the change and the result. If you cannot feel it and the Data Logger cannot see it, put it back.

### **1. LSD acceleration sensitivity — 18 is unvalidated and the build change is why**

This is the highest-risk number on the sheet. Removing the restrictor changed the torque curve materially, and the one measured value you own (14) was measured under the old curve.

Run **18**, then move in **2-point steps** based on the failure mode, not on feel-in-general:

- **Pushing wide mid-corner while on throttle** (the Chute, the Outer Loop, the Toe of the Boot) → **down to 16, then 14.**
- **Inside rear spinning up alone on exit** (T1, Bus Stop, final turn) → **up to 20, then 22.**
- Watch the on-screen tyre indicators. These two are opposite fixes and confusing them costs a session.

**And note which corners are *fine*.** That is what solved Laguna in one step.

### **2. Fuel consumption at FM1 / 3× — ten minutes, and it decides the whole race plan**

Three laps at race pace, full fuel, FM1, 3× multiplier. Read the in-game calculator, then read it again after three green laps.

- If it confirms ~8.7 L/lap → **run FM2** and plan a ~74 L stop (≈60 L in FM2).
- If it comes in under ~7.0 L/lap → the refuel drops toward 40 s and **FM1 for the whole race becomes defensible.** Re-run the §6.4 table.
- **Caveat that bit us at Laguna:** the calculator projects your *current* pace. Race pace is thirstier — defending, dirty air, off-line, and the opening two laps of a standing start are the thirstiest of the event. **Check it again in traffic before you trust it.**

### **3. 5th gear through the esses, and the Bus Stop kerb strike**

Two checks, one run, because they are the two places this circuit ends laps.

- **Esses:** are you in 5th the whole way, with no shift? If you upshift or downshift mid-esses, lengthen 5th and shorten 4th until you are not. Nothing else on the gearbox matters until this is true.
- **Bus Stop:** does the car **launch on the kerb at the exit**? If yes, the rear is too stiff over the strike — rear compression is already at 24, so go to **rear ride height +2 mm (74 mm)** before touching springs, per A7's post-1.49 fix order. Does it **bang and then refuse to steer**? That is arch contact, and ride height is the only thing that fixes it.

### Queued behind those three

4. **LSD braking sensitivity — walk 28.** Up in +2 steps while the rear is loose into the Bus Stop; back off 2 the moment the car stops wanting to turn in there, and take the rest from rear expansion damping.
5. **Camber 1.4 / 1.2 — check it against the brakes.** If T1 or Bus Stop stopping distance or stability degrades at all versus 1.2 / 1.1, revert. GT7 taxes camber against exactly the thing you are best at.
6. **Ballast −25 vs −50** — you will have run both across quali and the race. Note mid-corner push at the Outer Loop and front-left wear across a full stint. That closes backlog item G7.
7. **Front toe A/B — not here.** Still the top backlog item, still open on this car, and the Glen is the wrong circuit for it (oscillation risk above ±0.05° at 250 km/h). Run it at a slow circuit.

---

## 8. RANGE CHECK

Every value on both sheets, against the ranges read off this car's settings screen on 13 Aug 2026.

| Parameter | Min | Max | Race | Quali | Status |
|---|---|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | 63 | 61 | ✅ in range |
| Ride height — rear | 60 mm | 90 mm | 72 | 70 | ✅ |
| Natural frequency — front | 3 Hz | 5 Hz | 3.55 | 3.70 | ✅ |
| Natural frequency — rear | 3 Hz | 5 Hz | 3.70 | 3.85 | ✅ |
| Anti-roll bar — front | 1 | 10 | 6 | 7 | ✅ |
| Anti-roll bar — rear | 1 | 10 | 4 | 5 | ✅ |
| Damper compression — front | 20 % | 40 % | 26 | 25 | ✅ |
| Damper compression — rear | 20 % | 40 % | 24 | 26 | ✅ (race is 20 % of window — deliberate, §2) |
| Damper expansion — front | 30 % | 50 % | 42 | 43 | ✅ |
| Damper expansion — rear | 30 % | 50 % | 36 | 37 | ✅ |
| Camber — front | 0 ° | 6 ° | 1.4 | 1.5 | ✅ |
| Camber — rear | 0 ° | 6 ° | 1.2 | 1.3 | ✅ |
| Toe — front | −1 ° | 1 ° | 0.00 | 0.00 | ✅ |
| Toe — rear | −1 ° | 1 ° | +0.08 | +0.06 | ✅ |
| LSD initial torque | 5 | 60 | 6 | 6 | ✅ — sits 1 above minimum **by design**, not clamped. High preload is a silent cause of the mid-corner push this driver rejects. |
| LSD acceleration | 5 | 60 | 18 | 20 | ✅ |
| LSD braking | 5 | 60 | 28 | 26 | ✅ |
| Downforce — front | 350 | 450 | 415 | 435 | ✅ |
| Downforce — rear | 500 | 700 | 620 | 660 | ✅ |
| Brake balance | −5 | 5 | 0 | 0 | ✅ |
| Maximum speed | 200 km/h | 800 km/h | 300 | 300 | ✅ (generator) |
| Final gear | 2 | 5 | 3.550 | 3.550 | ✅ |

### **Nothing was clamped. No value sits at a hard limit on either sheet.**

**Two notes on the click counts.** Step sizes have never been recorded for this car. The click figures in §1 assume GT7's usual increments — 1 mm ride height, 0.01 Hz natural frequency, 0.1° camber, 0.01° toe, 5-point downforce. **If a click count disagrees with what you see on screen, the percentage is the value that is always right.** Note the real step sizes next time the settings screen is open and they go into the register.

**Downforce values are all multiples of 5**, so they land correctly whether the slider steps in 1s or 5s.

---

## 9. PIT CREW PASTE BLOCKS

**Two blocks. Paste them one at a time into the paste box on Pit Crew's Event screen — race first, then qualifying.** Never both at once: the parser reads a single `setup` object per paste and a second sheet in the same payload is ignored **without a warning.**

**Acceptance test:** each paste should read **"22 of 23 settings, 6 gears"** with nothing unrecognised. `awd` is omitted deliberately — this is a two-wheel-drive car, and writing `"awd": null` would be dropped silently and read as a clean 23.

### 9.1 RACE

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Lamborghini Huracán GT3 '15",
    "circuit": "Watkins Glen International — Long Course",
    "sessionType": "race",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "Watkins Glen Long race v1",
    "values": {
      "rh_f": 63, "rh_r": 72,
      "nf_f": 3.55, "nf_r": 3.70,
      "arb_f": 6, "arb_r": 4,
      "dc_f": 26, "dc_r": 24,
      "de_f": 42, "de_r": 36,
      "cam_f": 1.4, "cam_r": 1.2,
      "toe_f": 0.00, "toe_r": 0.08,
      "lsd_i": 6, "lsd_a": 18, "lsd_b": 28,
      "df_f": 415, "df_r": 620,
      "bb": 0,
      "top": 300, "fg": 3.550
    },
    "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.022],
    "performance": { "powerRestrictor": 99, "ecuOutput": 94, "ballastKg": 55, "ballastPosition": -25 }
  }
}
```

### 9.2 QUALIFYING

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Lamborghini Huracán GT3 '15",
    "circuit": "Watkins Glen International — Long Course",
    "sessionType": "qualifying",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "Watkins Glen Long quali v1",
    "values": {
      "rh_f": 61, "rh_r": 70,
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
    "gears": [2.677, 1.963, 1.600, 1.376, 1.150, 1.075],
    "performance": { "powerRestrictor": 99, "ecuOutput": 94, "ballastKg": 55, "ballastPosition": -50 }
  }
}
```

### 9.3 What these blocks do **not** carry — enter these by hand on the Event screen

The parser reads `sheetName`, `values` and `gears`. **That is all.** Everything else above is there for you to read while pasting:

- **Compounds** — Racing Soft front and rear, *pending the §7.1 stint measurement*
- **Assists** — ABS Weak, TCS 0 (race: TCS 1 for the launch lap), countersteer off
- **Multipliers** — tyre 2×, fuel 3×
- **Performance adjustment** — restrictor 99, ECU 94, ballast 55 kg, position −25 race / −50 quali, **and the fact that the turbo has been removed**
- **Event** — 20 laps, 1 mandatory stop, standing start, changeable (dry), afternoon
- **Refuel rate 1 L/s** *(declared)* and **pit loss 21 s** *(estimated — 20 s declared is the app default; see §6.5)*
- **The car's slider ranges** — now in the register, but confirm the tool has loaded them

---

## 10. WHAT TO BRING BACK

This is the first run of this combination, so everything is a first data point.

1. **Measured RS life at 2×** at the Glen — and **which corner and which tyre goes first.** The model says front-left. Nobody has checked on this car.
2. **Measured fuel consumption at FM1 / 3×** — practice figure *and* an in-traffic figure. The gap between those two is itself a finding.
3. **Measured pit loss** including the refuel time actually taken.
4. **Where accel LSD landed**, and by which failure mode you got there. This is the second data point on the D3.1 hypothesis that an ECU-heavy build wants more lock than a restrictor-heavy one at the same power — the first genuine test of it.
5. **Whether the NA/ECU package felt more progressive than the turbo/restrictor package**, in your own words. This decision was made on reasoning, not measurement.
6. **Whether 5th covered the esses** on the box as issued, and the actual speed at the Bus Stop board clean and with a tow.
7. **Whether camber 1.4 cost anything under braking.**
8. **−25 vs −50 ballast**, since you will have run both.
9. **The car's step sizes** for each slider, next time the settings screen is open.

---

*Generated 13 Aug 2026 · GT7 v1.70 baseline · no BoP, open tuning · pitcrew-prompts/1.0*
