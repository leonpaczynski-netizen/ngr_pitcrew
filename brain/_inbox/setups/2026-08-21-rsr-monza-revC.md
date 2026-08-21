═══════════════════════════════════════════════════════════════════
  PORSCHE 911 RSR (991) '17  ·  AUTODROMO NAZIONALE MONZA
  **REV C** — the first post-1.71 sheet, from the 21 Aug control run (12 laps)
  50 min · timed · 8× tyre / 3× fuel · 0 mandatory stops · refuel 1 L/s
  Issued 21 Aug 2026 · **GT7 v1.71** · no BoP, open tuning
  **Ranges re-read on this car 21 Aug 2026 — five endpoints moved**
═══════════════════════════════════════════════════════════════════

---

# 0. The headline

**No slider changes. The strategy inputs moved, and the plan you were actually going to run barely moved at all.**

Rev B remains the control group and is not superseded as a *record* — read it for the diagnosis, the data-integrity findings (§1) and the reasoning about what was deliberately left alone (§7), all of which stand. **This sheet replaces only its §3 gearing numbers and its §5 strategy.**

Three things to know before anything else:

1. **The car is unchanged and confirmed unchanged.** Job 0 read every value against Rev B §4 and nothing moved; the telemetry confirms it independently — gear ratios byte-identical across the patch.
2. **⭐ The short-shift fuel plan survives almost exactly.** Rev B estimated 5.25 L/lap short-shifted from a −20 % rule of thumb. Measured on v1.71: **5.282 L/lap.** The tank still covers 18.9 laps against Rev B's 19.0. **The plan you were going to run is intact.**
3. **⚠️ Tyre life is completely unmeasured on v1.71, and it is now the only unknown that can change the stop count.** The control run used Racing Hards over 10 laps deliberately so wear would not confound the grip measurement. It worked, and it means this sheet cannot tell you what the tyre does.

**Why there are no slider changes.** The one value with a strong case for moving is **LSD acceleration sensitivity**, and it has too strong a case to guess at — the wheelspin it manages fell 40–60 %, its range doubled to 0–100, and the torque map it was tuned against was replaced. **That is `../16` §12 Job 2B, a full-span sweep, not a slider nudge on this sheet.**

---

# 1. What the run measured

**Session 60, 21 Aug 2026, 12 laps — 10 short-shifted on the beep, 2 at full RPM.** Full workings and confound analysis: **`../17-v1.71-measured-results.md`**.

| | v1.70 baseline | **v1.71 measured** | Δ | Confidence |
|---|---|---|---|---|
| **Rear slip at full throttle, 6th** | 1.0278 | **1.0109** | **−61 %** | ✅ **[MEASURED]** |
| **Rear slip at full throttle, 1st** | 1.1004 | **1.0479** | **−52 %** | ✅ **[MEASURED]** |
| **Clean Vmax in 6th** | 278.7 km/h @ 8,009 rpm | **274.9 km/h @ 7,826 rpm** | **−3.9 km/h** | ✅ **[MEASURED]** |
| **Observed limiter** | 8,600 rpm | **~8,600 rpm** | unchanged | ✅ **[MEASURED]** |
| **Fuel — short-shift on the beep** | 5.25 L/lap *(estimated)* | **5.282 L/lap** | +0.6 % | ✅ **[MEASURED]**, 10 laps |
| **Fuel — map 1, full RPM** | 6.566 L/lap | **6.736 L/lap** | +2.6 % | ⚠️ **[PROVISIONAL]**, 2 laps |
| **Short-shift saving** | −20 % *(inherited, GT Sport era)* | **−21.6 %** | confirmed | ✅ **[MEASURED]** |
| **Median lap** | 1:49.180 (28 laps) | 1:52.525 (12 laps) | — | ❌ **not comparable — see §4** |
| **Tyre wear, RH @ 8×** | 15 laps, ~9 ms/lap | **not measured** | — | ❌ |
| **Four-corner temps** | lap 36 | lap 12 | — | ❌ **wrong lap to compare** |

**The Vmax result is the one to trust most on the physics side**, because 274.9 falls **below the floor of twenty pre-patch practice sessions** (275.6–282.1). It is not a datapoint against a datapoint — it is outside a distribution.

---

# 2. Gearing — the numbers moved, but do NOT re-gear yet

Rev B §3 said *"leave the gearbox exactly as it is,"* on the strength of 6th sitting at **98.9 % of peak-power rpm** at clean-air Vmax. That number has moved.

```
  v1.70:  278.7 km/h @ 8,009 rpm   →  98.9 % of peak power (8,100 rpm)
                                      7.4 % rev headroom to the limiter

  v1.71:  274.9 km/h @ 7,826 rpm   →  96.6 % of peak power
                                      9.0 % rev headroom to the limiter
```

**6th is now slightly too long.** The car reaches terminal speed **274 rpm below peak power** and 774 rpm below the limiter, where it used to arrive within 91 rpm of peak power. On paper, shortening the gearbox ~2.4 % puts Vmax back on the power peak.

### The derived gearing constant

```
  6th at limiter = 274.9 × 8600/7826         = 302.1 km/h
  K = 302.1 × 1.062 × 3.550                  = 1,139

  ┌──────────────────────────────────────────────────────────┐
  │  K = 1,139  (was 1,128.3)   ·   LIMITER = 8,600 rpm      │
  │  +1.0 %, and the ratios are byte-identical.             │
  └──────────────────────────────────────────────────────────┘
```

**Nothing mechanical changed.** Gear ratios read `2.727 / 1.925 / 1.529 / 1.288 / 1.152 / 1.062` before and after; tyre radius reads 0.355 m before and after. **The entire +1.0 % is the slip reduction showing up in the speed-per-rev relationship** — with the wheels turning 1.7 % less fast than the road in 6th, the engine now does fewer revs for the same road speed.

**Use 1,139 for gearbox arithmetic** — it is the relationship the car actually exhibits, and that is what K is for. **Do not conclude the gearbox changed.**

### ⛔ But do not act on any of this yet

**The terminal-speed drop has two explanations that call for opposite responses** (`../16` §3.3):

| Reading | Mechanism | Response |
|---|---|---|
| **Rolling resistance rose** | The car really is slower. Supported by the fuel figure. | Re-gear. |
| **The old speed was slip-flattered** | Wheels were turning 2.8 % faster than the road in 6th. Less slip shows as less speed with no resistance change. | **Do nothing.** |

**Neither can be ruled out from this run, and the two were not separated because sector times were not recorded.** Re-gearing on the wrong reading corrects for something that did not happen.

> **The test is cheap: sector times on the two straights, or a coast-down from 250 km/h in neutral.** Fifteen minutes. `../08` Part G item 17. **Until then the gearbox stays exactly as written in Rev B §4.**

---

# 3. ⭐ Strategy, re-derived

## 3.1 The race

```
  Race length      50 min
  Lap time         see §4 — plan on 1:50–1:52, not 1:49.2
  Laps             50 min ÷ 1:51                            ≈ 27 laps  (was 28)
  Pit transit      19 % of a lap                            ≈ 21 s per stop
```

**Plan 27 laps, and treat 28 as the optimistic case.** The lap-time uncertainty is genuine (§4) and it changes the fuel total by one lap's worth either way.

## 3.2 Fuel — the short-shift plan is essentially unchanged

**This is the good news and it is worth stating plainly. Rev B's short-shift figure was an estimate derived from a GT Sport-era −20 % rule. It has now been measured on v1.71 and it was right.**

| | Rev B (v1.70) | **Rev C (v1.71 measured)** | Change |
|---|---|---|---|
| Map 1, **no** short-shift | 6.566 L/lap | **6.736 L/lap** ⚠️ *provisional* | +2.6 % |
| **Short-shifting on the beep** | 5.25 L/lap *(estimated)* | **5.282 L/lap** ✅ *measured, 10 laps* | **+0.6 %** |
| Tank range, short-shifting | 19.0 laps | **18.9 laps** | −0.1 lap |
| Tank range, full RPM | 15.2 laps | **14.8 laps** | −0.4 lap |

**Note which number is better evidenced.** The short-shift figure comes from ten laps; the full-RPM figure from two. **The plan runs on the well-measured one.**

### The one-stop arithmetic, short-shifting from lap 1

```
  27 laps × 5.282 L                                    = 142.6 L
  Tank                                                 = 100 L
  Must add                                             =  42.6 L  →  43 s stationary
  Plus transit                                         =  21 s
  ─────────────────────────────────────────────────────────────────
  ONE STOP, TOTAL COST                                 ≈  64 s
```

| Stops | Transit | Refuel | **Total** |
|---|---|---|---|
| **1** | 21 | 43 | **64 s** |
| 2 | 42 | 43 | 85 s |
| 3 | 63 | 43 | 106 s |

**Refuel time is linear at 1 L/s, so total standing time is identical whatever you do — every extra stop is pure added transit.** One stop, by 21 seconds. **Unchanged from Rev B, and by a wider margin than before** because the smaller fuel total means less standing time to amortise.

### The window

**Fuel allows a maximum stint of 18.9 laps.** Over 27 laps that puts the stop anywhere from **lap 9 to lap 18**, with the constraint that neither stint exceeds 18.9.

**Target lap 16–17.** Late for the same reason Rev B gives, and it is now a stronger argument:

> **⛔ Rev A said "a weather stop at this event is nearly free." At one stop that is false** — an unscheduled wet stop costs a full 21 s of transit you were not going to spend. Conditions are changeable with a day-to-night transition. **Hold the stop as late as the fuel allows and keep it available to double as the weather stop.**

**Fuel map:** map 1 with short-shifting; **5 or 6 whenever you are in a tow** — Monza's slipstream is the strongest in GT7 and this is close to free. Map 1 when attacking, defending, or on the last lap. **The diamond marker is the authority in the race, not this document.**

## 3.3 ⚠️ Compound — the call cannot be made from this run

Rev B chose **Racing Hard** on a **9.5-second margin** over Racing Medium, resting on two numbers:

- the **15-lap RH stint at 8×** — a v1.70 measurement, **not re-taken**;
- the **assumed RH:RM wear ratio of 1.4–1.6×** — which `../03` §1.3 has always flagged as never measured on any version.

**Neither has been measured on v1.71, and a 9.5-second margin is thin enough to flip on either.**

> ### The thing that would change the stop count
>
> **Fuel now allows 18.9 laps. Tyre life is unknown.** On v1.70 the tyre gave "15+ laps with no measurable degradation" — a floor, not a limit, because the run ended rather than the tyre.
>
> **If 1.71 made wear meaningfully faster and RH now falls off inside ~14 laps, the tyre becomes the binding constraint and a 27-lap race needs two stops.** That is a 21-second swing and it is the only thing on this sheet that can still move the race plan.
>
> **Ten laps on RH at 8× with the gauge read at laps 5 and 10 settles it.** Do it before the race, not during it.

**Qualifying stays on Racing Soft** — no stint to protect, the delta is pure lap time.

---

# 4. ⚠️ Why there is no pace figure on this sheet

**The 12-lap median of 1:52.525 is not a valid comparison against Rev B's 1:49.180, and it should not be used to conclude anything about grip.** Three reasons, any one of which is disqualifying:

1. **First session on materially changed physics.**
2. **Off-track time on 8 of the 12 laps** (0.93–3.70 s), including both full-RPM laps.
3. **Run order confounds mode with familiarity.** The short-shifted laps came first, while adapting; the full-RPM laps came last, when dialled in. The apparent 2.6 s/lap short-shift cost is therefore **not** a measurement of short-shifting — the documented figure is ~0.5 s/lap, and the best short-shifted lap here (1:51.267) is 1.26 s off the best full-RPM lap (1:50.012).

**For planning purposes: assume 1:50–1:52 and re-measure once the physics stop feeling new.** The fuel and stop arithmetic in §3 is not sensitive to a second either way — it changes the lap count by one.

> **⚠️ And do not compare against 1:44.912.** Rev B §1.2 established it as a timing artefact — the lap burned 0.16 L. **Comparing a post-patch median against it would manufacture a phantom seven-second regression.**

---

# 5. The sheet — UNCHANGED from Rev B

**Every value below is identical to Rev B and was confirmed present on the car on 21 August. Nothing was clamped or reset by the patch.**

```
                                        RACE (Rev C)            QUALIFYING (Rev C)
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Hard ⚠️ §3.3      Racing Soft
  Rear compound             Racing Hard ⚠️ §3.3      Racing Soft

SUSPENSION
  Body height      Front    60 mm · +5 · 20%        58 mm · +3 · 12%
                   Rear     68 mm · +8 · 27%        65 mm · +5 · 17%
  Anti-roll bar    Front    5                       6
                   Rear     3                       4
  Damping compr.   Front    23 · 15%                25 · 25%
                   Rear     25 · 25%                27 · 35%
  Damping expan.   Front    38 · 27%◄               39 · 30%◄
                   Rear     34 · 13%◄               36 · 20%◄
  Natural freq.    Front    3.05 Hz · +5 · 2.5%     3.20 Hz · +20 · 10%
                   Rear     3.20 Hz · +20 · 10%     3.35 Hz · +35 · 17.5%
  Camber angle     Front    1.0° · 16.7%            1.2° · 20%
                   Rear     1.0° · 16.7%            1.2° · 20%
  Toe angle        Front    0.00°                   −0.05°
                   Rear     +0.08°                  +0.05%

DIFFERENTIAL  ◄ percentages restated on the NEW ranges
  Initial torque            5 · 16.7%◄              5 · 16.7%◄
  Acceleration sens.        14 · 14.0%◄ ⚠️          16 · 16.0%◄
  Braking sens.             24 · 24.2%◄             22 · 22.2%◄

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
                            UNCHANGED. K is now 1,139 and 6th sits at 96.6% of
                            peak-power rpm — but see §2 before touching anything.

BRAKES
  Brake balance             0  (− front / + rear)   0

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)             100%
  ECU output                100%                    100%
  Ballast / position        none                    none

ASSISTS
  ABS                       Weak                    Weak
  TCS                       0 — and see §6          0
═══════════════════════════════════════════════════════════════════
   ◄ = percentage restated on a moved range. NO ABSOLUTE VALUE CHANGED.
```

## 5.1 ⭐ Range check — re-read on v1.71, and read this carefully

**Five endpoints moved on this car. No value was clamped, but four percentages changed meaning.**

| Parameter | v1.70 range | **v1.71 range** | Value | Was | **Now** |
|---|---|---|---|---|---|
| **LSD initial torque** | 5–60 | **0–30** | 5 | 0 % | **16.7 %** |
| **LSD acceleration** | 5–60 | **0–100** | 14 | 16.4 % | **14.0 %** |
| **LSD braking** | 5–60 | **0–99** | 24 | 34.5 % | **24.2 %** |
| **Damper expansion F** | 30–50 | **30–60** | 38 | 40 % | **26.7 %** |
| **Damper expansion R** | 30–50 | **30–60** | 34 | 20 % | **13.3 %** |
| Natural frequency F | 3.00–5.00 | **unchanged** | 3.05 | 2.5 % | 2.5 % ✅ |
| Everything else | — | **unchanged** | — | — | ✅ |

**Three consequences:**

1. **⭐ The cheapest clamp detector on the car read clean.** Front NF still sits at 3.05 Hz on a 3.00 floor — five clicks. Rev B §4.1 nominated it as the value a moved suspension range would clamp first. **It did not move, and that is the independent confirmation that Job 0's "nothing changed" is real.**
2. **⭐ Initial torque at 5 is no longer on the floor.** It was 0 % of range; it is now 16.7 %. **The setting `../08` B1 calls "low, because high preload is a silent cause of the mid-corner push you hate" is a sixth of the way up a range that now goes below it.** There is territory under this value that has never existed before.
3. **⭐ The rear damper is proportionally much softer in rebound than it reads.** 34 was 20 % of range and is now 13.3 %. **`../08` A4 #2 wants rear expansion low for lift-off stability, so this is the direction you want** — but it means the sheet is further toward that end than intended, and the new headroom (50 → 60) is at the end this car has least use for.

---

# 6. What to test next, in order

**One change per run, three clean laps, revert what you cannot feel.** Standing Rule 5 matters more during a rebuild, not less — and Job 2A is the proof: it produced three confirmed findings precisely because nothing on the car was touched.

### ⭐ 1. LSD acceleration sensitivity — full span, 0 / 25 / 50 / 100

**The highest-value chassis test on this car, and the reason Rev C ships no diff change.** Three independent things moved at once:

- the wheelspin it manages is **down 40–60 %**;
- the range went from **5–60 to 0–100**;
- the value 14 was set against a **torque map that no longer exists**.

**Do not walk up from 14.** That assumes the old optimum is still nearby, and nothing supports that any more. **Sweep the span** — `../16` §12 Job 2B has the full protocol.

**Record per setting:** driver report verbatim first (`../08` A5's three failure modes are the vocabulary) · median of three clean laps · **rear slip ratio at full throttle in 2nd and 3rd** · off-track count · Parabolica exit speed.

**Expect 100 to be undriveable.** That is the point — a span needs a bracket at both ends. **And watch for a flat response between 25 and 50: that would mean the parameter has become insensitive, which is a bigger finding than any particular value.**

### 2. Ten laps on RH at 8×, gauge read at laps 5 and 10

**The only remaining unknown that can change the stop count** (§3.3). Also the cheapest read on whether *lateral* slip moved the way longitudinal slip did — which is `../03`'s central wear assumption and currently the biggest open question in the knowledge base.

**⚠️ And do the thirty-second check Rev B §5.1 flagged and nobody has done: confirm the event's tyre wear actually reads 8×.** The whole baseline rests on it.

### 3. Sector times on the straights, or a coast-down

Fifteen minutes, and it decides whether to re-gear at all (§2). **Until it is done the gearbox does not move.**

### 4. If the car now understeers less on maintenance throttle — expect it, and say so

Rev B §2.1's whole diagnosis was a car being dragged round on its rear axle under steady throttle. **The measured slip reduction says exactly that problem should be smaller now.** If the Lesmos and the Parabolica have gone quiet with no setup change, **that is a confirmation of the slip finding from the driver's seat and it is worth reporting** — it would be the first subjective corroboration of a number that currently rests entirely on telemetry.

**⚠️ And the inverted result matters just as much:** if the car is now *looser* mid-corner, the accel value may already be too low for the new physics, and the sweep in test 1 should start from the top rather than the bottom.

### 5. Kerb behaviour at the chicanes

Rev B §2.2's −0.30 Hz fix was aimed at a repeated bounce, and **1.71 changed damper attenuation — "road surface tracking" is kerb behaviour by another name.** Whether the fix is still needed, still sufficient, or now overdone is unknown. **And if the car ever bangs and then refuses to steer, stop everything and raise the ride height** — that is arch contact, and whether the 1.49 bottoming problem survived is still [UNKNOWN].

---

# 7. What carries over from Rev B unchanged

**Read Rev B for these. They are not reproduced here and they have not been superseded.**

- **§1 — the four data-integrity findings.** `wear.byCompound` fabricating compound labels from same-compound runs · `bestLapMs` accepting a 0.16 L lap · the `fittedFinalGear` contradiction · the pinned gauge series. **These are app defects, not physics.** Read them before ingesting any post-1.71 export.
- **§2.4 — "two problems, three faces."** The diff and the platform frequency, cleanly separable by feel.
- **§2.5 — the correction to `../05-track-reference.md`.** Monza's front wear side is **left**, not right, because its three sustained corners are rights. Circuit geometry; does not patch. **Still not corrected in `05`.**
- **§7 — what was deliberately left alone, and why.** The most durable section in the archive. In particular: **do not add rear downforce to mask a diff problem.** That is the Laguna trap stated in general form, and it is exactly the discipline this rebuild needs. **The one exception is §7's camber argument**, which rests on GT7 taxing camber against longitudinal grip — a steering-geometry behaviour that 1.71 reworked.

---

# 8. What to record

**✅ CLOSED ON v1.71**

1. **Slider ranges, all 22 parameters** — read 21 Aug. Five moved. Filed in `../11`.
2. **Short-shift fuel saving = 21.6 %** (5.282 vs 6.736 L/lap). **The inherited −20 % figure is confirmed on the new torque map, and this is the first in-house measurement of it on any version.**
3. **Rev limiter unchanged at ~8,600 rpm.** Confirmed against three pre-patch sessions using the identical query.
4. **Gear ratios unchanged**, byte-identical — an independent confirmation of Job 0.
5. **Driven-wheel slip under power, down 40–60 %.** `../17` §1.

**⚠️ PROVISIONAL**

6. **Fuel at map 1, full RPM = 6.736 L/lap.** Two laps. **Five clean full-RPM laps would settle it.**
7. **K = 1,139**, up 1.0 %, **entirely attributable to the slip change rather than to any mechanical difference.** Use it for gearbox arithmetic; do not read it as a gearbox change.

**❌ STILL OPEN ON THIS CAR**

8. **Tyre wear on v1.71.** Completely unmeasured. **The only unknown that can still move the race plan.**
9. **Slider step sizes.** Missed again on 21 August with the screens open. **Five sessions overdue.**
10. **Front toe A/B** (−0.05 / 0.00 / +0.05). Never run on this car, and the geometry it depends on was just reworked.
11. **Camber sweep**, 0.5 / 1.5 / 2.5. Same reason.
12. **Confirm the tyre multiplier reads 8×.** Thirty seconds, never done, and the entire baseline rests on it.
13. **Is the terminal-speed drop resistance or a slip artefact?** §2.
14. **Are the short-shift beep points still optimal?** The saving is confirmed; the points were derived on the old torque map.

**📤 FOR PIT CREW**

- **⭐ `meta.gameVersion` is still missing, and it is now demonstrably biting.** `game_version` reads NULL on all three range records in the database **including the v1.71 one taken on 21 August** — the date is the only thing distinguishing it from a v1.70 reading. **Priority one.**
- **Record the run mode per lap.** `short_shift_rpm` was 0.0 on all 12 laps of a session that was explicitly ten short-shifted laps plus two at full RPM. **The single most useful classifier in the session was not stored.**
- **Record the tyre gauge.** `wear_fl/fr/rl/rr` were null on all 12 laps.
- The three Rev B §9 export bugs are still open, and **the `corners` section still does not exist.**

---

*Rev C issued 21 Aug 2026 · **GT7 v1.71** · ranges re-read on this car 21 Aug 2026*
*No slider changed. Strategy re-derived on measured fuel. Gearbox held pending one 15-minute test.*
*Baseline and control group: `2026-08-12-rsr-monza-revB.md` — **not superseded, and not to be overwritten.***
*Measurements: `../17-v1.71-measured-results.md` · Work order: `../16-update-1.71-physics-change.md`*
