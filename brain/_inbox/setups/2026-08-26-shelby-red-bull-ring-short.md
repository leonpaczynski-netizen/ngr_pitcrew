═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  RED BULL RING — SHORT TRACK (2.336 km)
  **ROUND 5 SUPERCARS — v1, COLD START**
  Event 8 · 30 min + 180 s · standing · dry · RS/RM/RH · 2× wear / 2× fuel
  ABS Off · TCS 0 · countersteer off
  Issued 26 Aug 2026 · v1.71
═══════════════════════════════════════════════════════════════════

# 0. What this sheet is, and what it is not

**No lap, session or telemetry frame exists for this car at this circuit, and
none exists for this circuit at all.** `tools/data_health.py` returns three
lines and all three are refusals:

```
  corners        no corner observations - nothing to claim
  corner model   none stored - corners cannot be named
  gearbox        every session ran the sheet it is tagged with
```

So there is no symptom, and therefore no diagnosis. **Every value below is
either carried unchanged from a sheet that has been raced, or reasoned from
circuit doctrine.** Three values move. Everything else is held, deliberately,
because a change with no evidence behind it costs a run to unwind.

The knowledge base's Red Bull Ring entry (`05-track-reference.md` §1.10) is
written for the **Full course — 4.318 km, 10 corners.** This event is the
**Short Track — 2.336 km, 6 corners**, and the reference says nothing about it
beyond that one line. Where I have used the Full-course character I say so, and
where the premise does not survive the shorter lap I have held rather than
guessed.

---

# 1. Rank zero — what is actually in the car

**One value disagrees with itself, and it is the front anti-roll bar.**

| | |
|---|---|
| App sheet 31 `Road Atlanta race Rev B` holds | `arb_f` **4** |
| Every issued document says | `arb_f` **5** |

Rev B's paste block (§5), Road Atlanta v1 (its settings table, *"Front 5
(44%)"*) and Yas Marina Rev C all read **5**. Only the app's stored sheet reads
4, and `tools/check_setup_sheets.py` (since removed) flagged it. **I have written 5 into this
sheet** — three documents against one database row — but that is an assumption,
not a reading.

> ⚠️ **Ten seconds on the suspension page before you go out.** Read the front
> anti-roll bar. If it says 4, tell me — it means Road Atlanta was raced one
> click softer at the front than the sheet I wrote, and the Rev B braking
> verdict was taken on a car I was not describing.

**Also missing from the record:** sheet 31 carries an **empty** performance
block. Rev B specifies **ballast 109 kg at position 0**, and that document
already warns it *"has been recorded wrongly four times."* It is in the paste
block below. Check the Event screen shows it.

**Still open, and it invalidates every grip reading if it is wrong:** 1.71
changed force feedback, understeer vibration and the Fanatec Auto Setup
parameters. On an 18 Nm base an FFB change reads exactly like a grip change.
**Confirm your wheel settings survived the patch.** This has been open since
23 Aug and nothing in the telemetry can close it.

---

# 2. What the circuit asks for

`05-track-reference.md` §1.10, Full course. Compiled Aug 2026 on a post-1.49
baseline — **[DOCTRINE], and the tuning prescriptions in it are pre-1.71.**

| | |
|---|---|
| **Character** | Three heavy braking zones, **all uphill or on a crest**. Three traction-limited exits, **all uphill, all onto straights.** 65 m of elevation on the full lap. |
| **Grip priority** | **Mechanical grip and traction, clearly.** One of the few low-downforce circuits where aero is *not* the primary lever, because no corner is fast enough to make it pay. |
| **Brake bias** | *"Uphill braking loads the front naturally, so you need less forward bias here than on almost any other circuit — and a slightly rearward setting helps rotate the tight T3."* |
| **Top lever** | **LSD acceleration sensitivity.** The reference calls it *"the highest-value single setting at this circuit."* |
| **Second lever** | **2nd gear ratio** for the three slow uphill exits. |
| **Wear** | Moderate, **rear-biased**, front-right over front-left (T1, T3, T4, T6 are all rights). |

**What does not transfer to the short lap.** The reference argues LOW downforce
from *68% full-throttle share across two long straights on a 4.3 km lap*. Cut
the lap to 2.336 km and that premise is the part I cannot carry over — I do not
know which section survives. **Aero is held. See §3.4.**

---

# 3. The three changes

## 3.1 `bb` −1 → **0**

**[DOCTRINE] + [DRIVER STANDING RULE]**

Road Atlanta wanted −1 because T10a brakes downhill and the front-left was the
wear limiter at 4.0%/lap. **Neither applies here.** Every heavy stop at Red Bull
Ring is uphill, which loads the front for free, and the doctrine explicitly says
this circuit needs *less* forward bias than almost any other.

On this car **−1 is forward.** Going to 0 is handing a click back, which is the
direction your standing rule points anyway.

> **This is yours to trim in the car and I will not correct it.** If the rear
> steps out under the brakes on the climb, take −1 back and tell me — that is a
> finding about the diff, not about the bias.

## 3.2 `top` 300 → **265** — and the gearbox model is now measured, not assumed

**[MEASURED] the model. [ASSUMED] the target.**

Thirteen clean race laps at Road Atlanta, session 77, v1.71:

```
  Vmax           275.7 km/h mean · 278.8 max
  rpm at Vmax    8,092 mean · 8,152 max      (limiter ~8,805)
  6th gear       7.0% of the lap
```

**275.7 / 300 = 0.919. 8,092 / 8,805 = 0.919.** Those match to three figures, so
on this car **`top` is the road speed at which 6th reaches the limiter** — and
that gives a correction rule instead of a guess:

```
      corrected top  =  current top  ×  (rpm at Vmax) ÷ 8,805
```

At Road Atlanta that returns **276** against the 300 he raced: **~700 rpm of
6th never used, on a 4.088 km lap with a long back straight.** On a 2.336 km lap
it will be worse, and this is a circuit where the reference names 2nd gear as
lever #2 for three slow uphill exits. Shortening `top` shortens every ratio and
puts the acceleration where the lap is actually won.

**265 is a deliberate under-set, and it is the value on this sheet most likely
to be wrong.** Run 1 fixes it — §5.

> ⚠️ **The correction rule breaks if you are bouncing off the limiter.** If rpm
> at the braking board reads 8,805 the formula returns "no change" and it is
> lying. In that case go **up** 10 and read it again.

**Re-read the gearbox after you change `top`.** GT7 re-spaces the ratios and
they will not be `2.614 / 1.948 / 1.560 / 1.318 / 1.145 / 1.019` any more. The
gearbox is **the only one of the 23 setup values telemetry can verify** —
`pitcrew.analysis.gearing.matches_sheet` reads it straight out of the feed — so
it is the one place the record can be made honest for free. Read the six numbers
off Manual Adjustment and give them to me.

**The shift table carries over, to first order.** A uniform ratio change does
not move the crossover between two gears; it moves the road speed at which the
crossover happens, and therefore the drag at that moment, which is second-order.
**8500 / 8250 / 8250 / 8000 / 8250** stands. 4→5 and 5→6 are the two that agreed
exactly across 36 laps on v1.70 and 11 laps on v1.71.

## 3.3 `arb_f` 4 → **5** — a record repair, not a change

See §1. This is what every issued document says is in the car. If the car
disagrees, the sheet is wrong and not the car.

## 3.4 And the change I am **not** making: `lsd_a` stays at 17

**This is the highest-value setting at this circuit and I am holding it, on
purpose.**

The reference says FR cars want **28–35** here. You are at **17**. That is the
single biggest gap between this sheet and the doctrine — and there are two
reasons it is not moving today:

1. **[DRIVER REPORT] closed this fork nine laps ago.** Road Atlanta Rev B §4:
   *"drive traction feels really good."* That is primary evidence and it beats a
   pre-1.71 table.
2. **The axis is unresolved.** 28–35 on the old 5–60 scale is 42–55% of range;
   on the 0–100 scale this car now reports it is 28–35%. The register has not
   been re-read since 1.71 and I will not quote a number whose scale I cannot
   name.

**Tripling the lock on an FR car with 606 bhp, on a slow uphill exit, on a
circuit you have never driven, is how a trail-braker ends up in the wall.**
It gets its own run, with its own falsifier — §5, run 2.

---

# 4. The sheet

| | Value | % of range | |
|---|---:|---:|---|
| Ride height F / R | 89 / 107 mm | 16.5 / 14.1 | held |
| Natural frequency F / R | 3.05 / 3.20 Hz | 52.5 / 60.0 | held |
| Anti-roll bar F / R | **5** / 4 | 44.4 / 33.3 | **record repair** |
| Damper compression F / R | 24 / 28 | 20.0 / 40.0 | held |
| Damper expansion F / R | 40 / 32 | 33.3 / 6.7 | held |
| Camber F / R | 1.4 / 1.0° | 23.3 / 16.7 | held |
| Toe F / R | −0.05 / 0.10° | 47.5 / 55.0 | held |
| LSD initial / accel / braking | 5 / 17 / 34 | *absolutes* | held — §3.4 |
| Downforce F / R | 150 / 260 | 100.0 / 73.3 | held — §2 |
| Brake balance | **0** | 50.0 | **−1 → 0** |
| Top speed | **265** | 10.8 | **300 → 265** |
| Final gear | 3.600 | 53.3 | held |
| Ballast | 109 kg @ 0 | | **must be entered** |

**LSD in absolutes, not percentages** — 1.71 moved its three axes off a shared
scale and the register has not been re-read. *(Rule retired 11 Sep 2026: all four cars carry 0–30 / 0–100 / 0–100 on v1.71 - `11`.)*

**Held, and why.** Ride height: doctrine says mid-range for 65 m of gradient,
but that is the full lap, and **the last time this project raised ride height on
a bottoming argument the rationale was withdrawn** — the detector fires on the
most *extended* wheel. Rear compression damping: doctrine names the T6/T7 and
T9–T10 kerbs, and I do not know that the Short Track has them. Downforce: §2.
Dampers and geometry: one family is already moving.

---

# 5. The runs — three of them, priced

**One change per run, three clean laps minimum.**

### Run 1 — learn the circuit and fix the gearbox · 6–8 laps

**No setup change. This run exists to make the sheet honest.**

| Read | Why |
|---|---|
| **rpm at Vmax on the main straight**, in clean air | Feeds the §3.2 correction. This is the deliverable. |
| **The six ratios off Manual Adjustment**, after the `top` change | The only setup value the feed can verify |
| **Lap time** | Nothing about this race can be planned without it — §6 |
| **The tyre gauge at the end of the run** | The only wear instrument that exists |

**Then set `top` from the formula and read the ratios again.**

> Do not chase a time. Six laps of an unknown circuit are worth more than three
> fast ones, and the corner-identity archive is empty either way — the app cannot
> name a corner here and will not pretend to.

### Run 2 — the differential · 3+ clean laps

> **[HYPOTHESIS]** Red Bull Ring's three slow uphill exits reward more
> acceleration lock than Road Atlanta's did, and `lsd_a` 17 is leaving exit
> traction on the table.
>
> **[BASIS]** `05-track-reference.md` §1.10 — *"Red Bull Ring rewards diff lock
> more than almost any other circuit on this list, because all three critical
> exits are slow, uphill and feed straights."* **[DOCTRINE], pre-1.71, and the
> axis question in §3.4 is unresolved.** Against it: your own report at Road
> Atlanta, which is primary evidence.
>
> **[TEST]** `lsd_a` **17 → 24**. One bracket step, not the jump to 28–35 that
> the pre-1.71 table asks for.
>
> **[COST]** 3 clean laps, and it must come after run 1 or the gearbox change
> confounds it.
>
> **[FALSIFIED BY]** wheelspin *earlier* on the exits, the car running wide on
> power out of the slow rights, or turn-in going dull. **Any of those and it
> comes back to 17 and the doctrine is wrong for this car.** If it hooks up
> better, 28 is the next bracket.

**The instrument is your report, not the telemetry.** A per-corner exit-speed
comparison over three laps sits inside the scatter — a corner is 3–4× noisier in
relative terms than a whole lap on this driver's own data, and this circuit has
no corner model at all. I will read the rear-slip frames for a wheelspin pattern,
but the verdict is yours.

### Run 3 — a stint at race pace, full tank · 8+ laps

The wear rate and the burn rate at the multipliers actually being raced. Read
the gauge at the start and the end. **This is what turns §6 from arithmetic into
a plan.**

---

# 6. Strategy — one thing is already certain, and it is not close

**[DERIVED]** from Road Atlanta race burn, session 77: **6.256 L/lap, n = 19,
sd 0.225**, measured at the same 2× fuel multiplier on the same car under 1.71.

Two ways to carry that across, and **they agree on the only thing that matters:**

| Lap time | Laps in 30 min | Burn, scaled per km | Race total | Burn, scaled per second | Race total |
|---:|---:|---:|---:|---:|---:|
| 45 s | 40.0 | 3.57 L | 143 L | 3.40 L | 136 L |
| 50 s | 36.0 | 3.57 L | 129 L | 3.77 L | 136 L |
| 55 s | 32.7 | 3.57 L | 117 L | 4.15 L | 136 L |
| 60 s | 30.0 | 3.57 L | 107 L | 4.53 L | 136 L |

**The tank is 100 litres. Every cell in that table is over it.**

> **You are stopping. It is fuel, and it is decided before you drive a lap.**

**Tyres will not bind.** Road Atlanta's front-left limiter was 4.0%/lap on a
4.088 km lap — **0.98%/km**. At 2.336 km that is ~2.3%/lap, so `0.85 / 0.023`
is a **37-lap** stint against a 30–40 lap race. Even allowing that Red Bull Ring
is rear-biased and harder on traction than Road Atlanta was, the margin is
large. **[DERIVED, per-km scaling of three HUD readings, and never presented as
measured** — GT7 broadcasts no wear channel.**]**

**What I am not doing yet.** I am not calling a stop lap, a fuel load or a
window. That needs `build_inputs` and `recommend()` on a measured lap time and a
measured burn, and both come out of run 1 and run 3. **Ask me for the race plan
after run 3 and it will name which limit bound it, from the expression that
decided it.**

Two event-record items that will move that answer and are both **declared, not
measured**: `refuel_rate_lps` **2.0** and `pit_loss_secs` **20.0**. The 2 L/s
figure came from you on 23 Aug and it is what killed short-shifting at Road
Atlanta — at 2 L/s a litre is half a second and the trade inverts. If Round 5
runs a different rate, say so, because it changes the discipline.

---

# 7. Paste block

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Red Bull Ring - Short Track",
    "sessionType": "race",
    "date": "2026-08-26",
    "gameVersion": "1.71",
    "compound": { "front": "RS", "rear": "RS" },
    "assists": { "abs": "Off", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Red Bull Ring Short race v1",
    "values": {
      "rh_f": 89, "rh_r": 107,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 4,
      "dc_f": 24, "dc_r": 28,
      "de_f": 40, "de_r": 32,
      "cam_f": 1.4, "cam_r": 1.0,
      "toe_f": -0.05, "toe_r": 0.10,
      "lsd_i": 5, "lsd_a": 17, "lsd_b": 34,
      "df_f": 150, "df_r": 260,
      "bb": 0,
      "top": 265, "fg": 3.600
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "shiftRpm": { "1": 8500, "2": 8250, "3": 8250, "4": 8000, "5": 8250 },
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

> ⚠️ **`gears` above is the Road Atlanta box at `top` 300 and it will be wrong
> the moment you set 265.** It is in the block so the record is not empty. Read
> the six real numbers off Manual Adjustment after the change and replace them —
> §3.2.

> ⚠️ **Check the Event screen shows this sheet fitted before you go out.** The
> shift beep reads its table off the *fitted* sheet, and at Road Atlanta it was
> silent for eleven laps because the app still had the Yas Marina sheet on the
> car. Sheet 31 landed correctly — first time in five sessions. Make it two.

---

# 8. Confidence

| Claim | Status |
|---|---|
| Range record: verified, v1.71, 23 Aug 2026 | **[MEASURED]** — post-patch, valid |
| `top` is the speed at which 6th hits the limiter | **[MEASURED]** — 275.7/300 = 8092/8805 to three figures, 13 race laps, session 77 |
| ~700 rpm of 6th unused at Road Atlanta | **[MEASURED]** — session 77, v1.71 |
| Road Atlanta burn 6.256 L/lap, sd 0.225, n=19 | **[MEASURED]** — race, 2× fuel, v1.71 |
| Race total 107–143 L ⇒ one stop, fuel-bound | **[DERIVED]** — two scalings, both over the tank on every lap time |
| Wear will not bind | **[DERIVED]** — per-km scaling of three HUD readings. Never measured. |
| `top` 265 | **[ASSUMED]** — an under-set. Run 1 corrects it. |
| `bb` 0 | **[DOCTRINE]** — §1.10, pre-1.71. Driver's to trim. |
| `lsd_a` 17 held | **[DRIVER REPORT]** beats **[DOCTRINE]** — the fork is closed until run 2 |
| `arb_f` 5 | **[ASSUMED]** — three documents against one database row. §1 |
| Every corner claim | **[UNMEASURED]** — no corner model exists for this circuit. **I cannot see a corner here and I will not pretend to.** |
| Short Track layout | **[UNMEASURED]** — the reference covers the Full course. 6 corners, 2.336 km, and nothing else is on file. |

---

# 9. Predictions on the record

| Prediction | Falsified by |
|---|---|
| `top` 265 will still leave rpm unused at Vmax — the correction will come **down**, not up | rpm at the braking board reading ≥ 8,700 |
| One stop, and the binding constraint will be **fuel**, not tyres and not evidence | a burn under ~3.0 L/lap, or a stint capped by wear |
| `bb` 0 will be comfortable on the uphill stops and he will not ask for −1 back | he asks for −1 inside the first three laps |
| `lsd_a` 17 → 24 improves exit traction without dulling turn-in | wheelspin earlier, running wide on power, or turn-in going dull |

**Four sessions running, the driver's report has beaten the derived metric.**
If any of the above disagrees with what you feel, you are the one who is right
and I want to hear it before the telemetry does.
