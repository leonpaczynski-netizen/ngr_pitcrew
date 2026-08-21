# Lamborghini Huracán GT3 '15 · Watkins Glen International (Long Course)
### 20 laps · 2× tyre · 3× fuel · 1 mandatory stop · standing start · changeable · from 18:05 at ×2 clock

**Rev D — 17 Aug 2026 · GT7 v1.70 · no BoP, open tuning**
**Supersedes Rev C (17 Aug 2026). First revision issued after a WIN.**

> ## RESULT: **P1, from P5 on the grid.** Best 1:43.601 · median 1:44.457 · 20 laps · one stop, lap 13.
> **Rev C was the sheet in the car** — 68/75 mm, 435/660, 6th 1.055, FM1, Racing Soft both stints — *driver-confirmed, because the packet said otherwise (§3.1).*
> Median lap improved ~1.5 s against the previous session on this car. Driver report: *"This setup and the short shifting worked so well finished in 1st place!! From qualifying in 5th."*

---

# 🔴 PRE-1.71 — DO NOT TYPE THIS SHEET INTO A v1.71 CAR

**Stamped 21 August 2026.** This sheet was built and won on **GT7 v1.70**. Update **1.71 (20 Aug 2026)** changed the tyre model, per-car steering geometry, damper attenuation, the defaults **and adjustment ranges** of suspension, differential and aerodynamics, PP fleet-wide, both assists, and the damage model. See `../16-update-1.71-physics-change.md` and `00-PRE-1.71-NOTICE.md`.

**This is now the control group and the starting point — the best one this programme has, because it is the sheet that won.** It is not a setup.

**Specifically at risk on this sheet:**

| On this sheet | 1.71 exposure |
|---|---|
| **§8 RANGE CHECK — the whole table** | ⚠️ **Void.** Every min/max is a v1.70 reading. 1.71 revised adjustment ranges for suspension, diff and aero **in the official notes.** The percentages in that table (52.0 %, 85 %, 80 %…) are the *output* of those ranges — **if a range moved, every percentage on this sheet silently changed meaning.** Re-read `../11-car-slider-ranges.md` first. |
| **LSD 6 / 18 / 28** | ⚠️ Diff range revised, and **[COMMUNITY — single source]** the floor may now be **0** rather than 5. Also: 1.71 introduced a **new engine torque control map**, and §7's whole argument for 18 (vs Laguna's 14) is a torque-shape argument. |
| **Downforce 435 / 660**, front share 39.7 % | ⚠️ Aero defaults **and ranges** revised on race cars. 435 was 85 % of a 350–450 range; if the range moved, it is not 85 % any more. |
| **Ride height 68 / 75, rake +7 mm** | ⚠️ Suspension ranges revised **and** damper attenuation changed. §2.2's withdrawn bottoming diagnosis is unaffected (it was a detector artefact), but whether the underlying 1.49 arch-rub problem still exists is now **[UNKNOWN]** — `../16` §4. |
| **Damping 26/24, 42/36** | ⚠️ *"Damper attenuation characteristics have been changed."* Both the values and the 20–40 / 30–50 windows are unverified. |
| **Camber 1.4 / 1.2** | ⚠️⚠️ 1.71 reworked **per-car steering geometry** — the model that makes camber expensive in GT7. **Do not issue a camber value until the Job 5 A/B is run.** |
| **Gearing: K = 1092.5, 6th at 291.7 km/h, observed top 273.5** | ⚠️ *"Rolling resistance has been optimised."* **Terminal speed moved.** §2.3's "18 km/h of unused 6th" is computed from a v1.70 observed top speed. The K measurement in §6.0 is now **more** valuable, not less — it has to be taken fresh anyway. |
| **Fuel 6.117 L/lap, and all of §4** | ⚠️ Rolling resistance is a fuel term. **L/lap may have moved with no driver input**, which moves the stop window, the refuel volume and §4.2's whole arithmetic. |
| **Compound: RS both stints, 12 laps with no fall-off** | ⚠️ **The single most exposed conclusion on this sheet.** Tyre heating and wear values were adjusted. §4.4 killed Rev C's RM argument on the strength of a 12-lap RS stint — **that evidence is v1.70.** `../16` §12 Job 2 re-takes it on this exact car and circuit. |
| **TCS 1 launch lap → 0** | ⚠️ TCS intervention behaviour "optimised." The v1.70 price was up to two tenths per corner; unknown now. |
| **ABS Weak, brake balance 0** | ⚠️ ABS **slip-ratio control and cornering brake behaviour** adjusted — the trail-braking phase by name. The *principle* (find entry stability mechanically, not with bias) stands; the reference does not. |
| **Restrictor 99 / ECU 94 / ballast 55 @ −25 / PP** | ⚠️ **PP recalculated fleet-wide.** Read the current number before racing — the league is PP-capped and no-BoP. `../16` §12 Job 4. |

**What on this sheet is NOT at risk, and it is the majority of the document:**

- **§2.2 the withdrawn bottoming diagnosis** and **§3.1 the stale-packet finding** — both are about the Pit Crew app's detectors and data contract, not about GT7 physics. `../15-pitcrew-detector-audit.md` stands unchanged, and Standing Rules 8 and 9 with it.
- **§4.2's 14× ratio finding** — *a litre of refuel is worth ~1.0 s, a lap of stop delay ~0.073 s.* The **ratio** is a property of pit-lane mechanics and fuel weight, neither of which 1.71 touched. The **L/lap input** did move. **Optimise litres, not lap** survives.
- **§3.2's traffic-vs-degradation separation** and **§3.3's calls-ledger defect** — both are analysis method and app defects.
- **§6's test ordering and §7's "what did not move, and why"** — the discipline of not changing a thing without a reason is exactly what the rebuild needs.
- **§2.1's corner table as a record of what the driver actually did.** The lap times are not comparable to v1.71 times; the *shape* of the loss (T9 entry consistency, T2/T8 entered with zero brake) is a driving observation.

> ## The one instruction that matters before this sheet is opened again
>
> **Job 0, two minutes:** open the car and read its **current** settings screen against §1 below, **before changing anything.**
>
> - **Values match §1** → tunes survived; go to the range re-read.
> - **Values reset to defaults** → the garage is gone; **this sheet is how you rebuild the car.**
> - **Some match, some don't** → the ones that changed were **clamped by a moved range** — and they map out exactly where the new endpoints are. Record every one.
>
> Write down which happened. It is the first post-1.71 measurement this programme takes.

---

## 0. THE HEADLINE — nothing on the race sheet moves, and here is why that is the strong answer

**Zero setup changes. Every value re-asserted, none omitted.**

Three separate lines of evidence had to be tested before "leave it alone" became a decision rather than laziness:

1. **The bottoming diagnosis that drove Rev C is withdrawn.** It was a detector artefact — see `../15-pitcrew-detector-audit.md` §1. The car flags `bottoming` 17/17 at T4, T7 and T8 **while sitting 5–8 mm higher than its own straight-line reference.** That is body roll. The only corner with real four-corner compression is T2, and the driver rides that kerb on purpose.
2. **The understeer diagnosis is withdrawn as a primary.** The flag orders almost perfectly by entry speed, which is what the detector's own `1/v²` construction bias predicts and what a real front-grip fault would not. Audit §2.
3. **Every remaining candidate change is confounded** by racing in traffic (P5→P1), by the compound (RS both stints vs mostly RM last time), and by the short-shifting. None of them clears the bar for a one-change-per-run test on a car that just won.

**The recoverable time in this race was not in the setup. It was ~3–5 s sitting in the pit box over-fuelling (§4.2), and ~18 km/h of unused 6th gear that was a deliberate tow gamble (§2.3).**

---

## 1. THE SHEET

**⚠️ v1.70 values. Read this against the car (Job 0), do not type it into the car.**

```
═══════════════════════════════════════════════════════════════════════════════
  LAMBORGHINI HURACÁN GT3 '15  ·  WATKINS GLEN INTERNATIONAL (LONG COURSE)
  Rev D · 17 Aug 2026 · GT7 v1.70        ● = Rev C value, RE-ASSERTED (§3.1)
  ═══ RACE SHEET: NO CHANGES ═══         ▲ = changed (qualifying only)
  ═══ PRE-1.71 — CONTROL GROUP, NOT A SETUP ═══
═══════════════════════════════════════════════════════════════════════════════
                                     RACE                  QUALIFYING
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front / rear compound              Racing Soft           Racing Soft
                                   ● RS BOTH STINTS — §4.4

SUSPENSION
  Body height        Front         ● 68 mm                 66 mm
                                     52 % · +13 clicks     44 % · +11 clicks
                     Rear          ● 75 mm                 73 mm
                                     50 % · +15 clicks     43 % · +13 clicks
                     (rake)          +7 mm                 +7 mm
  Anti-roll bar      Front           6                     7
                     Rear            4                     5
  Damping compr.     Front           26                    25
                     Rear            24                    26
  Damping expansion  Front           42                    43
                     Rear            36                    37
  Natural frequency  Front           3.55 Hz               3.70 Hz
                     Rear            3.70 Hz               3.85 Hz
  Camber angle       Front           1.4 °                 1.5 °
                     Rear            1.2 °                 1.3 °
  Toe angle          Front           0.00 °                0.00 °
                     Rear            +0.08 °               +0.06 °

DIFFERENTIAL
  Initial torque                     6                     6
  Acceleration sensitivity           18   ← D3.1 CLOSED    20
  Braking sensitivity                28                    26

AERODYNAMICS
  Downforce          Front         ● 435                 ▲ 445
                     Rear          ● 660                 ▲ 675
                     (front share)   39.7 %                39.7 % — held
                     (total)         1095                  1120

TRANSMISSION   (K = 1092.5 with the sheet's own final drive — §2.3)
  Max speed setting                  300 km/h              300 km/h
                                     ⚠ DO NOT TOUCH — generator, wipes all ratios
  Final gear                         3.550                 3.550
  Ratios 1st→6th                   ● 2.677 1.963 1.600     2.677 1.963 1.600
                                   ● 1.376 1.150 1.055     1.376 1.150 1.104
  6th at limiter                     291.7 km/h            278.7 km/h
  (observed clean-air top speed)     273.5 km/h

BRAKES
  Brake balance                      0                     0

PERFORMANCE ADJUSTMENT   (not carried by the reply contract — enter by hand)
  Turbocharger                       NONE (NA)             NONE (NA)
  Power restrictor                   99 %                  99 %
  ECU output                         94 %                  94 %
  Ballast                            55 kg                 55 kg
  Ballast position                   −25                   −50
                                     ⚠ packet reports 70 @ −50 — stale, §3.1

FUEL
  Map                                1  (as raced, won)    1
  Refuel at stop                   ▲ 26 L, not 30 — §4.2   n/a

ASSISTS
  ABS                                Weak                  Weak
  TCS                                1 launch lap → 0      0
  Countersteering assist             Off                   Off
═══════════════════════════════════════════════════════════════════════════════
```

---

## 2. POST-MORTEM — what the setup cost, ranked

| # | Cost | Corner phase | Size | Confidence |
|---|---|---|---|---|
| **1** | **6th gear geared for a tow that never arrived.** Clean-air top speed 273.5 km/h; 6th reaches the limiter at 291.7. 18.2 km/h of unused gear, and the previous session on the same gearbox also topped at 273.8 — two sessions, no tow. | Full-throttle straights | ~0.1 s/lap, ≈2 s over the race | **Measured** speed; **inferred** cost. ⚠️ *v1.70 — rolling resistance changed* |
| **2** | **Rake fell from +9 mm to +7 mm** when Rev C raised the front 5 mm and the rear 3 mm. Understeer flags spread from 2 corners to 5 (T1, T4, T9 went from silent to flagging). | Mid, 150–200 km/h | Unquantifiable | **Contested** — confounded by traffic, compound and a biased detector |
| **3** | **T5 / T7 exit traction**, 12/17 and 9/17 wheelspin on corners with ~1 % kerb — the two places the wheelspin channel is actually clean. | Exit, 2nd gear | Already largely bought back by short-shifting | **Measured** direction, unusable magnitude |
| **4** | Everything else the telemetry flagged | — | **Zero** | Withdrawn — audit §1, §2 |

### 2.1 The corner table, and what it actually says

**⚠️ Lap times and losses are v1.70 and are not comparable to v1.71 times. The *shape* of the loss is a driving observation and carries.**

| | loss vs own best | spread | trail brake | understeer /17 | peak brake | entry km/h |
|---|---|---|---|---|---|---|
| T6 | 78 ms | 63 | 394 ms | 0 | 40.0 % | 134 |
| T4 | 87 | 41 | 267 | 7 | 40.9 % | 153 |
| T1 | 89 | 69 | 207 | 7 | 24.5 % | 144 |
| **T9** | **128** | **178** | 121 | 12 | 40.9 % | 170 |
| T7 | 86 | 47 | 106 | 0 | 9.9 % | 120 |
| T5 | 101 | 125 | 85 | 0 | 10.8 % | 133 |
| **T2** | **150** | 114 | **0** | 15 | 64.3 % | 204 |
| T3 | 79 | 67 | 0 | 6 | 0 % | 185 |
| T8 | 77 | 73 | **0** | 15 | 0 % | 194 |

**Total median corner loss vs the driver's own best through each corner: 875 ms.**

- **T9 is the worst corner on the lap and it is new** — 178 ms of spread, the largest on the circuit, and 12/17 understeer where the previous session had 8/23. It is also the shortest braking zone on the lap (109 m) with only 121 ms of trail brake against 267 at T4 and 394 at T6. **This is an entry-phase consistency problem, not a balance problem.**
- **T2 and T8 are the only two corners entered with literally zero brake pressure**, and both flag understeer on 88 % of laps. Even after discounting the detector's speed bias, this is worth a driving test before it is worth a setup change (§6).
- **T5 collapsed from 1.57 s lost (previous session) to 101 ms**, with no diff change. That is the short-shifting.

> **⚠️ Still outstanding, and now blocking Job 2: the Watkins Glen corner-ID mapping.** Pit Crew's auto-segmenter finds 9 corners on an 11-turn circuit and names them T1–T9. **Which named corner is which has been asked for twice and never answered** — and `../16` §12 Job 2 runs at this circuit, so it is needed now.

### 2.2 The bottoming diagnosis is withdrawn

Full arithmetic in `../15-pitcrew-detector-audit.md` §1. Summary: T4, T7 and T8 flag `bottoming` on 17 of 17 laps while the car's **mean** height across all four wheels is 5–8 mm *above* its straight-line reference — one side down 5–8 mm, the other up 13–29 mm. That is roll in a right-hand corner. T2 is the only corner with genuine four-corner heave (+16.2 mm) and it is a deliberate kerb.

**The falsification is already on file: raising the car 5 mm and adding 60 points of downforce made the measured T2 depth roughly double.** A contact detector cannot do that.

> **Rev C §3.4 overrode the driver's silence to make this change. That override was wrong.** It is the only time in this project telemetry has been trusted over an explicit driver report, and it did not survive contact with the next packet. The ride height is not being put back — the car won on it — but the argument for it is withdrawn, and the A/B is queued as test #2.
>
> **⭐ 21 Aug — this finding is entirely about the Pit Crew detector and is unaffected by 1.71.** Standing Rule 8 stands: a telemetry-only flag may buy a question or a measurement, never a setup change. **And it matters more during the rebuild, not less** — with every physics baseline unverified, a detector artefact is even easier to mistake for a real change.

### 2.3 Gearing — K recomputed, and the packet is wrong again

```
maxSpeedKph 273.5 @ 7868 rpm in 6th, limiter 8392
  -> speed at limiter in 6th = 273.5 x 8392/7868 = 291.7 km/h
K = 291.7 x 1.055 x 3.550 = 1092.5     <- correct, using the SHEET's final drive
K = 291.7 x 1.055 x 3.660 = 1126.4     <- what the packet reports, using the DERIVED one
```

The packet computes `gearingConstantK` through the derived final gear, which its own note says reads high because GT7 broadcasts the unloaded tyre radius. Same class of error Rev C caught last session.

**But K is still not measured, and the two extrapolations disagree by 1.8 %** — 1112.6 last session, 1092.5 this one, on the same gearbox. Both extrapolate from a non-limiter observation, and the observed limiter itself differs (8264 vs 8392) because it was caught in a different gear each time.

> **Stop extrapolating. 5th gear reaches its limiter at 267.6 km/h and the car does 273.5 — so on the long straight you already pass through it.** Hold 5th to the limiter once and read the speed off the HUD. That closes K exactly, in one lap, for every gearbox this car ever gets. It is the single cheapest open item on this car.
>
> **⭐ 21 Aug — and 1.71 makes it unavoidable rather than merely cheap.** *"Road surface resistance (rolling resistance) has been optimised"* moves terminal speed. **Both extrapolations above are now v1.70 numbers, and so is the 273.5 observed top speed the "18 km/h of unused 6th" finding rests on.** The measurement has to be retaken regardless — so take the *exact* one this time.

Speed at the limiter in every gear, at K = 1092.5 / fg 3.550:

| Gear | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| ratio | 2.677 | 1.963 | 1.600 | 1.376 | 1.150 | 1.055 |
| km/h at limiter | 115.0 | 156.8 | 192.3 | 223.7 | 267.6 | 291.7 |

### 2.4 Short-shifting — what the app's beep is actually doing

Four upshift observations: **7035, 7051, 7238, 7647 rpm** against a limiter of 8392. That is 745–1357 rpm early — genuine short-shifting, and on a 540 bhp NA MR car with **TCS 0** it is a traction tool, not a power loss.

Where it clearly paid: the second-gear exits. **T5 dropped from the worst corner on the lap (1.57 s lost) to 101 ms with no differential change.** T6 and T7 both went silent on understeer and T5/T6/T7 are where the clean wheelspin signal lives.

Where it may be costing: T8 (upshift at 7647 with the throttle at 5.8 % — the car is coasting, there is nothing to protect) and the straights.

> **Recommended map: short-shift the second- and third-gear exits — T5, T6, T7, and T1 — and take everything else to the limiter.** Sample count is 4, so this is a hypothesis with a cheap test, not a finding.
>
> **⚠️ 21 Aug — 1.71 introduced a new engine torque control map** (citing improved partial-throttle speed control). **Short-shifting is a torque-delivery technique, and this is the technique that won the race.** Re-check the shift points early; it is both the highest-value driving lever on this car and the one most directly exposed.

---

## 3. WHERE THE DATA AND THE DRIVER DISAGREE

### 3.1 The `setup` block is stale for the third consecutive session — and this time it would have inverted the whole post-mortem

The packet reports sheet **"Watkins Glen Long race v1"**: `rh_f 63`, `rh_r 72`, `df_f 415`, `df_r 620`, 6th `1.022`, ballast `70 @ −50`, `PP 738.66`. **The driver confirms Rev C was in the car: 68/75, 435/660.**

The fitted ratios corroborate him — 6th fits at **1.055**, and he confirms 1.055 is what he set. The stale block reports 1.022.

The ballast is stale by the same mechanism Rev B §3.5 documented (70 kg is Laguna's figure, −50 is Rev A's *qualifying* position), and **PP 738.66 is byte-identical to the pre-aero-change figure**, which is only possible if the whole performance block is a copy. Treating the build as **55 kg @ −25, restrictor 99, ECU 94, NA** — driver-confirmed spec, **inferred** for this session.

> **Trusting the driver, completely.** Had the packet been believed, this post-mortem would have diagnosed the low car with the trimmed rear wing — the exact setup Rev C was written to replace — and every ranked cost would have been computed against a car that was not on the circuit.
>
> **Standing consequence: while this defect is live, no key may be omitted from a reply block for this app.** The contract's "an omission is safe, Pit Crew holds the sheet as run" is false here. **Rev D re-asserts every race value.**
>
> **⭐ 21 Aug — this is Standing Rule 9, and 1.71 gives it a second failure mode.** The rule exists because the *app* held a stale sheet. Now the *car* may hold a different sheet than the one written down, if the patch reset or clamped saved values. **Job 0 is Rule 9 asked once, globally, before the session starts.** Note that PP 738.66 in the packet is also now doubly stale — PP was recalculated fleet-wide.

### 3.2 The tyre-degradation channel says two opposite things, and neither is a tyre

| | raw slope | fuel effect | fuel-netted |
|---|---|---|---|
| Run 1 (laps 2–12) | +140 ms/lap | −20 ms/lap | **+160 ms/lap** |
| Run 2 (laps 15–20) | −185 ms/lap | −22 ms/lap | **−162 ms/lap** |

Equal and opposite on the same compound. Run 1 is the P5→P3 fight in traffic; run 2 is a clear-air charge to the lead on a cooling track (game clock ×2, 18:05 → ~19:15). **These are traffic signals, not degradation.**

What *is* usable: **lap 17 (103.825) on seven-lap-old tyres is within 224 ms of the outright best lap on five-lap-old tyres.** Racing Soft is not measurably falling away inside a 12-lap stint at 2× on this circuit.

> **⚠️ 21 Aug — that last paragraph is the most load-bearing tyre conclusion on the sheet and it is a v1.70 result.** It is what killed Rev C's RM-first plan (§4.4). **1.71 adjusted tyre heating and wear values, and reworked the slipping regime.** `../16` §12 Job 2 re-runs exactly this — same car, same circuit, same compound, same multiplier — with this result as the control. **The separation method (net out fuel, then read traffic vs degradation) is sound and carries; the number does not.**

### 3.3 The calls ledger reports 14 of 14 declined, including "Chequered flag."

`accepted: false` on every call, including ones that cannot be accepted or declined — "Green, green, green.", "P3. 15 to go.", "Tyres cold." — **and the driver did box, one lap after the box call.** The field defaults false and has no third state.

> **The calls ledger is currently worthless as evidence about the strategy model, which is the one thing it exists for.** Needs `informational` / `offered` / `taken` / `declined`. *(An app defect — unaffected by 1.71.)*

### 3.4 "Burning 8 % under plan" is not reproducible

Laps 2–7 burned **6.115 L/lap** against a plan of 6.214 — **1.6 % under**, not 8 %. Either the call uses a different baseline or the comparison is wrong. **Flagged, not trusted.**

---

## 4. STRATEGY REVIEW

> **⚠️ Every litre-per-lap figure below is a v1.70 measurement, and 1.71 optimised rolling resistance — a fuel term.** The **arithmetic and the ratios are sound and survive**; the **inputs need re-measuring**. §4.2's 14× finding is the part to carry forward.

### 4.1 Was "fuel" the right binding constraint? **Yes — but only just, and it binds the wrong thing**

```
measured 6.117 L/lap (median) -> 20 laps = 122.3 L, tank 100 L
  fuel range on a full tank  = 16.35 laps
  RS tyre range at 0.05193/lap (2x) = 19.3 laps
  16.35 < 19.3  ->  fuel binds stint length. CORRECT.
```

**But the number of stops was never in question — the regulations mandate one.** What fuel actually binds is the *stop window* and the *refuel volume*, and the model spent its attention on the wrong one of those two.

> **⚠️ Both inputs to that comparison moved in 1.71** — the fuel rate via rolling resistance, the tyre rate via the wear model. **The comparison could invert.** Re-derive it after Job 2; it is two numbers.

### 4.2 The stop window is nine laps wide and almost free. The refuel volume is where the seconds are.

Legal window at 6.117 L/lap: **laps 4 to 16.** He stopped on 13; the plan said 12.

| Stop lap | 10 | 12 | **13** | 14 | 15 | 16 |
|---|---|---|---|---|---|---|
| Cost vs lap 13 (fuel weight) | +0.22 s | +0.07 s | **0** | −0.07 s | −0.15 s | −0.22 s |

**A lap of delay is worth 0.073 s. A litre of refuel is worth ~1.0 s.** That is a **14×** ratio, and the model has been optimising the cheaper variable for three revisions.

**He crossed the line with 6.31 L — 1.03 laps of fuel still in the tank.**

| Reserve you want | Litres over | Seconds given away |
|---|---|---|
| 3.0 L (half a lap, prudent in changeable conditions) | 3.3 | **3.3 s** |
| 1.5 L | 4.8 | **4.8 s** |
| 1.0 L | 5.3 | **5.3 s** |

> **This is the largest uncontested loss of the race, and it is bigger than anything the setup cost.** Next time: **take 26 L, not 30.** Formula: `refuel = (20 − stopLap) × 6.13 − fuelAtStop + 3`.
>
> **⭐ 21 Aug — the 14× ratio is one of the most durable findings in the knowledge base and it survives 1.71.** Pit-lane mechanics and fuel mass are not things the patch touched. **"Optimise litres, not lap" stands.** What changes is the `6.13` in the formula — re-measure L/lap, then the formula works unchanged. `../00-INDEX.md` Settled Facts carries this with the same caveat.

### 4.3 Pit loss — measured for the first time

Lap 13 took **155.712 s** against a green median of 104.457 → **51.3 s** total stop cost. Estimated refuel ≈ 26.2 L. At the declared 1 L/s that leaves **~25 s of pit-lane transit loss**, against the 20 s declared on the event page and the ~21 s the circuit reference carries.

**One stop cannot separate the fixed loss from the refuel rate.** Both are in the 51.3 s. What it does establish, and this is the number that matters: **the stop cost 51.3 s and took on 26 L — so a litre of fuel really is worth about a second, and possibly more.**

> **⭐ Pit travel time is a track constant and refuel rate is an event property. 1.71 touched neither** (`../03` §6). **This is one of the few measurements on this sheet that is still current** — and one of the few worth taking now, because it will not go stale.

### 4.4 Compounds — Rev C said RM first, he ran RS both stints, and RS was right

Rev C built a three-argument case for RM→RS resting on RS being possibly 7.8 %/lap. **A 12-lap RS stint with no measurable fall-off kills that reading.** At 0.05193/lap a 12-lap stint is 62 % used; at 7.8 %/lap it would have been 94 % gone and the last three laps would have collapsed. They did not.

> **RS both stints, confirmed by a win.** Rev C's compound argument is withdrawn. The cooling-track argument for putting softs late was sound in isolation and simply irrelevant once RS clears 12 laps comfortably.
>
> **⚠️⚠️ 21 Aug — this is the conclusion on this sheet most likely to have been overturned by 1.71, and it is the one a race would be planned around.** It rests entirely on a v1.70 wear rate. **Do not carry "RS both stints" into a v1.71 race on this evidence.** `../03` §1.3.1's standing rule, extended: *no modelled wear figure may pick a compound — and that now includes every measured figure taken on a previous game version.* **Job 2 settles it in 30 minutes on this exact combination.**

### 4.5 Which calls were right

| Call | Verdict |
|---|---|
| Lap 7 "burning 8 % under plan" | **Wrong number** (1.6 %), right direction |
| Laps 10–12 "box in 2 / next lap / this lap" | **3–4 laps early.** The window ran to lap 16 and later is (marginally) better. Taking it on 13 was correct. |
| Lap 12 "Box this lap. RS." | **Compound call correct.** RS was right and Rev C's RM plan was wrong. ⚠️ *on v1.70* |
| **The refuel-volume call that was never made** | **The most expensive omission of the race — 3–5 s.** The engineer must call litres, not just "box". |
| Everything else | Informational, mislogged as declined (§3.3) |

### 4.6 What changes in the strategy model

1. **Optimise refuel volume first, stop lap second.** 1.0 s/L vs 0.073 s/lap. **⭐ Survives 1.71.**
2. **Emit an explicit refuel-litres call** at the box call: `(remainingLaps × L/lap) − fuelAtStop + reserve`. **⭐ Survives — re-measure the L/lap input.**
3. **Reserve is a declared policy, not a safety margin the model picks.** 3 L in changeable conditions, 1.5 L in settled. **⭐ Survives.**
4. **Stop treating the stop lap as the decision.** Within the legal window it is worth less than a tenth of a second per lap. **⭐ Survives.**
5. **Do not plan a compound change on an unmeasured wear rate when the reference compound has already cleared the stint length.** **⚠️ Survives as a rule — but on v1.71 *nothing* has cleared a stint length yet, so the rule currently says: measure first.**

---

## 5. DELTA TABLE

### Race sheet

| Parameter | As run (Rev C) | Revised | Why |
|---|---|---|---|
| **Every setup value** | — | **UNCHANGED** | Won from P5. Both telemetry-driven candidates (bottoming, understeer) are detector artefacts (audit §1, §2). Every remaining candidate is confounded by traffic, compound and short-shifting. |
| *(all re-asserted, not omitted)* | | | **The packet says Pit Crew is holding sheet v1 with Rev A values. An omission would revert 5 mm of ride height and 60 points of wing.** §3.1 |
| Refuel at the stop | ~30 L | **26 L** | Strategy. Crossed the line with 6.31 L = 1.03 laps. §4.2 |
| Stop lap | 13 | **13–15** | Window is laps 4–16 and later is marginally better. Not worth risk. §4.2 |
| Compound | RS / RS | **RS / RS** | Confirmed. §4.4 ⚠️ *on v1.70* |
| Fuel map | 1 | **1** | Won on FM1 at 6.117 L/lap and the refuel is only 26 L. FM2's whole case was buying pit time that no longer exists. |

### Qualifying sheet

| Parameter | Rev C | Rev D | Why |
|---|---|---|---|
| **Downforce — front** | 435 | **445** | Rev C held this back for one reason only: *"it increases the bottoming risk you already have."* **That risk is now withdrawn** (audit §1). One lap, no stint to protect, and the Glen's lap is its fast corners. P5 on the grid is where the weakness is. |
| **Downforce — rear** | 660 | **675** | ⚠️ **COUPLED — these move together or not at all.** 445 alone would push front share to 40.9 % and hand you a nervous car at 190 km/h. 445/675 holds front share at **39.7 %**, identical to the race car. Only the total moves: 1095 → 1120. |
| Everything else | | **unchanged** | The race diagnosis produced no balance change, so there is nothing to carry across. |

**Revert trigger:** if the quali car feels nervous or vague at T2/T8 entry, go back to 435/660 in one step. Both values, together.

> **⚠️ 21 Aug — the quali change was never run.** 445/675 was issued on 17 Aug and 1.71 landed on the 20th. **It is an untested v1.70 recommendation on aero ranges that have since been revised.** The *reasoning* (couple the two, hold front share at 39.7 %) is sound and carries; the numbers wait for the range re-read.

---

## 6. WHAT TO TRY NEXT, IN ORDER

> **⭐ 21 Aug — superseded at the top by `../16-update-1.71-physics-change.md` §12 Jobs 0, 1 and 2.** Nothing below is interpretable until the ranges are known and one stint is measured. **But note how well §6.0 has aged: both "free measurements" below are now mandatory rather than merely cheap, and both are folded into the 1.71 protocol.**

### 0. *(Before any of them)* — the two free measurements

Neither is a change. Both close questions that have been open for three revisions.

1. **Read the rear-left tyre gauge at lap 6 and lap 12 of an RS stint.** Third session asked, third session not taken. It is the only thing standing between the RS wear rate being measured and being modelled, and every strategy decision rests on it.
   > **⭐ Fourth session now, and it is inside `../16` §12 Job 2 — a run that is happening anyway. It is also the fastest read anyone will have on what 1.71 did to tyre wear. Five seconds of attention.**
2. **Hold 5th gear to the limiter on the long straight and read the speed.** 5th limits at ~267.6 km/h and the car reaches 273.5, so you already pass through it. One lap, and K stops being an extrapolation forever. §2.3
   > **⭐ And rolling resistance changed, so K has to be retaken regardless. Take the exact measurement rather than a third extrapolation.**

### 1. The T8 brake test — a driving change, not a setup change

**T2 and T8 are the only corners you enter with zero brake pressure, and they are the only two flagging understeer on 88 % of laps.** At T8 — the ~190 km/h kink you take with no brake and no throttle — **brush the brake for a tenth on entry for three laps** and see whether the car takes more speed through it.

If it does, the answer was never front downforce. If nothing changes, then front downforce 435 → 445 becomes a legitimate race-sheet test, and the quali sheet is already carrying that experiment for you.

**⭐ This is a driving test with no setup dependency, which makes it one of the few things on this list that is still runnable as written after the patch — once the car has been re-baselined enough to be driven at pace.**

### 2. Ride height back to 63 / 72 — the honest A/B

Rev C raised the car on an argument that is now withdrawn, and it cost 2 mm of rake. The car won anyway, so this is a pace test, not a fix. **Run three clean laps at 63/72 (rake +9 mm) against three at 68/75.** Watch T1, T4 and T9 — the three corners that went from silent to flagging when the car came up.

**Only after the T8 test**, and only as a single change. **⚠️ And after the range re-read — 63 and 72 are positions on a v1.70 range.**

### 3. Short-shift map — limiter on the fast corners, short-shift the slow exits

Take T8, T9 and the straights to the limiter; keep short-shifting T1, T5, T6, T7. Four upshift samples is not a finding, and this is the cheapest way to turn it into one. **⚠️ New torque control map in 1.71 — re-establish the shift points before mapping them.**

*(Held further back, all still queued behind a measurement: LSD acceleration 18 → 16, rear ARB 4 → 3, front toe A/B at a slower circuit, ballast −25 → −50.)*

**⭐ Two of those move up the list post-1.71: the front toe A/B** (fourth session outstanding, and toe sensitivity is downstream of the reworked steering geometry — `../16` §12 Job 5 pairs it with the camber A/B in one session) **and the LSD accel value** (new torque map; 18 needs re-establishing before 16 can be tested against it).

---

## 7. WHAT DID NOT MOVE, AND WHY

**⚠️ Every "why" below is a v1.70 justification. The reasoning is sound; the evidence is a version behind.**

| Left alone | Why |
|---|---|
| **LSD 6 / 18 / 28** | **D3.1 closes.** Four sessions, no power-on push, and T5 — previously the worst corner on the lap — dropped to 101 ms with the diff untouched. Removing the restrictor does push the correct accel value up: **18 holds where Laguna needed 14.** ⚠️ *A torque-shape argument, and 1.71 changed the torque map. Also: the floor may now be 0, not 5.* |
| **Brake balance 0** | Proven at bias 0 with **no ABS at all** last session, and no entry complaint in a race won from P5. ⚠️ *ABS cornering brake behaviour adjusted.* |
| **Ride height 68 / 75** | The reason for it is withdrawn; the result is not. Queued as an A/B (§6.2), not reverted on a whim. ⚠️ *Suspension ranges revised; damper model changed.* |
| **Downforce 435 / 660 (race)** | Finally validated by a win, on the correct compound, with the correct assists. First time this aero package has had a clean run. ⚠️ *Aero defaults and ranges revised on race cars.* |
| **6th gear 1.055** | 18 km/h of unused top end is a deliberate tow gamble that has now failed to pay twice. It is the one free change available — and it is behind the K measurement, because shortening 6th against a K that is 1.8 % uncertain is how you chase a phantom. ⚠️ *And now behind a K that must be re-measured on new rolling resistance.* |
| **ARB, natural frequency, damping, camber, toe** | No driver complaint in four sessions and no surviving telemetry signal. ⚠️ **Camber is now the exception — 1.71 reworked the geometry model that prices it. It moves to the front of the queue, not the back.** |
| **Ballast 55 @ −25** | Still two-sided, still unmeasured, still not moving on a hunch. ⚠️ *And ballast position is the free-PP exploit, which matters more now PP moved — `../06` §5.5.* |

---

## 8. RANGE CHECK

> **🔴 THIS ENTIRE TABLE IS VOID ON v1.71.** Every min/max is a v1.70 reading and 1.71 revised adjustment ranges for suspension, differential and aerodynamics **in the official notes**. **Every percentage in the right-hand column is the output of a range that may have moved** — which is the precise failure mode `../11-car-slider-ranges.md` documents twice already. **Re-read the register (`../16` §12 Job 1, 15 minutes) before this table means anything.**

| Parameter | Min | Max | Race | Quali | Status (v1.70) |
|---|---|---|---|---|---|
| Ride height — front | 55 mm | 80 mm | 68 | 66 | ✅ 52.0 % / 44.0 % |
| Ride height — rear | 60 mm | 90 mm | 75 | 73 | ✅ 50.0 % / 43.3 % |
| Natural frequency — f/r | 3 Hz | 5 Hz | 3.55 / 3.70 | 3.70 / 3.85 | ✅ |
| Anti-roll bar — f/r | 1 | 10 | 6 / 4 | 7 / 5 | ✅ |
| Damper compression — f/r | 20 % | 40 % | 26 / 24 | 25 / 26 | ✅ |
| Damper expansion — f/r | 30 % | 50 % | 42 / 36 | 43 / 37 | ✅ |
| Camber — f/r | 0 ° | 6 ° | 1.4 / 1.2 | 1.5 / 1.3 | ✅ |
| Toe — f/r | −1 ° | 1 ° | 0.00 / +0.08 | 0.00 / +0.06 | ✅ |
| LSD i / a / b | 5 | 60 | 6 / 18 / 28 | 6 / 20 / 26 | ⚠️ **floor may now be 0** |
| Downforce — front | 350 | 450 | 435 | **445** | ✅ 85 % / **95 %** — 5 points of headroom |
| Downforce — rear | 500 | 700 | 660 | **675** | ✅ 80 % / **87.5 %** |
| Brake balance | −5 | 5 | 0 | 0 | ✅ *(unaffected — the range is class-independent and not in 1.71's list)* |
| Maximum speed | 200 | 800 | 300 | 300 | ✅ generator — do not touch |
| Final gear | 2 | 5 | 3.550 | 3.550 | ✅ |

**Nothing clamped, on v1.70.** Quali front downforce at 445 is the closest approach to a limit on either sheet, with 5 points in hand — deliberate, so there is somewhere to go.

> **⭐ And that headroom is now diagnostic.** Front downforce at 435 race / 445 quali sits at 85 % / 95 % of a 350–450 range. **If the aero range moved and the saved value was clamped, this is one of the first places it would show** — which makes it a useful thing to check first during Job 0.

---

*Rev D · 17 Aug 2026 · GT7 v1.70 · no BoP, open tuning · pitcrew-prompts/1.2*
*Supersedes `2026-08-17-huracan-watkins-glen-long-revC.md`.*
*Detector findings filed separately in `../15-pitcrew-detector-audit.md`.*
***Stamped pre-1.71 on 21 Aug 2026. Control group and starting point — not a setup. See `00-PRE-1.71-NOTICE.md` and `../16-update-1.71-physics-change.md`.***
