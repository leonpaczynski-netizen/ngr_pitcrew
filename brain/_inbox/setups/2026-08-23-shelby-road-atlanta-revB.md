═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  MICHELIN RACEWAY ROAD ATLANTA (FULL)
  **ROUND 4 SUPERCARS — REV B**, after practice 1
  Session 71 · 23 Aug 09:51–10:08 · 11 laps · v1.71 · RS · 2× / 2×
  Issued 23 Aug 2026 · supersedes v1 on strategy, the differential and the beep
═══════════════════════════════════════════════════════════════════

# 0. What practice changed

**Every estimate in v1 was scaled off Yas Marina and every one of them was
wrong. The measured numbers are worse in the two places that matter.**

| | v1 estimate | **Measured, session 71** | |
|---|---:|---:|---|
| Lap time | 1:27 | **1:21.6** | I was 5.4 s/lap slow |
| Race distance | 20 laps | **22 laps** | |
| Fuel | 5.34 L/lap | **6.275 L/lap** | +18% |
| Fuel needed | 106.8 L | **138 L** | tank is 100 |
| Tyre wear, worst corner | 2.3 %/lap | **4.0 %/lap (FL)** | +74% |

**The headline reverses this morning's call. You cannot run this race without
stopping, and it is not close: one tank is 15.9 laps and the race is 22.**

**Tyres now agree.** At 4.0%/lap the stint limit is `0.85 / 0.040` = **21.3
laps** — also short of 22, and 22 laps on one set finishes at **88% worn**
against a cliff at ~90%. This morning both constraints were comfortable. Both
now bind, and fuel binds first by six laps.

> **The app's one-stop plan was right, for a reason it could not see.** I told
> you this morning to ignore it because its cap was evidence-shaped rather than
> tyre-shaped. That was true of the *reason* and wrong about the *answer*.

---

# 1. The race plan — one stop, fuel-bound

`recommend()` on the measured inputs:

```
  Stint 1   laps 1–14    RS    94.1 L
  Stint 2   laps 15–22   RS    56.5 L      binding constraint: FUEL
  22 laps · one stop · tyres finish stint 1 at 56% worn
```

**The stop is expensive and its cost is almost all fuel:**

```
  pit loss            20.0 s
  dead time            5.3 s
  refuel ~44 L @ 1.00 L/s   44.0 s   ← measured rate, twice
  ─────────────────────────────────
                     ~69 s
```

**Every litre is a second.** That is the whole optimisation, and it is where
short-shifting now pays — **not to delete the stop, but to shrink it:**

| Discipline | Burn | Race total | Refuel | Stationary | Lap-time cost | **Net** |
|---|---:|---:|---:|---:|---:|---:|
| As practised | 6.275 | 138 L | 44 L | 44 s | — | — |
| −17% | 5.20 | 114 L | 21 L | 21 s | ~9 s | **−14 s** |
| Full short-shift −21.6% | 4.92 | 108 L | 15 L | 15 s | ~11 s | **−18 s** |

**Short-shift the two straights and you take roughly 29 fewer litres aboard —
29 fewer seconds standing still — for about 11 seconds of lap time.**

## 1.1 The margin, and why you are keeping it this time

**`lap_count_firm` is false.** At 81.8 s/lap, 22 laps is **1,799.6 seconds** into
a 1,800-second race. It could not be closer, and the 22nd lap is inside your own
lap-to-lap noise. **This is precisely the case your rule carves out** — a timed
race keeps the spare lap *only* while the count is unresolved, and it is
unresolved by four tenths.

**It costs 6.3 L, which is 6.3 seconds stationary.** Priced, and said out loud.

## 1.2 Stop window

**Lap 13–15.** Fuel wants it late (carry less), tyres want it at half distance
(even wear across two stints). The model lands on 14. **Anywhere in 13–15 is
within a second of optimal — take the one where you have clear track.**

---

# 2. The differential — it did not work, and I own part of that

**You needed `bb −2` where Yas needed `−1`. The rear is worse, not better.**

Two changes went in together and **I should not have shipped them together** —
that is exactly the confounding I refused to accept for the ballast, and I did
it on the diff in the same sheet.

**`lsd_i` 5 → 0 is the prime suspect, and it is mine.** Preload is a baseline
locking force applied at all torque levels. Under braking and on the overrun it
is part of what keeps the two rear wheels turning together — **so taking it to 0
removed rear-axle coupling at exactly the phase where you are losing the car.**
I flagged 0 preload as a turn-in risk and did not think about what it does under
braking. That was the wrong risk to name.

**`lsd_b` 26 may also be less lock than the 22 you had**, which is the rescaled-
axis question from v1 §2.1 that is still unanswered. On the old 5–60 scale 22 was
**30.9%** of range. On the new 0–100 scale 26 is **26%**. If GT7 rescaled your
saved value through the patch, I reduced your braking lock while trying to raise
it.

**Both suspects point the same way, so the fix does not depend on knowing which:**

```
  lsd_i    0  →  5      revert. Restores the Yas baseline coupling.
  lsd_b   26  →  34     34% of the new range, above the old 22's 30.9%,
                        and +12 absolute — inside A4's +5 to +15 band.
```

**34 clears the old value on both readings of the scale.** That is deliberate:
22-equivalent was not enough at Yas either — you ran −1 there.

> **Stop the moment turn-in dulls.** That is the trail-braker's failure on the
> other side and it arrives before any telemetry sees it. If the car will not
> come round on the brakes, come down in 2s: 32, then 30. **Below 30 you are
> back in territory that has already failed twice.**
>
> ⚠️ **Still do the ten-second check.** Open the differential page and read the
> three numbers. If it shows **0 / 17 / 26**, the absolutes persisted and the
> numbers above are right. Anything else and the axis rescaled — tell me what it
> says.

## 2.1 Hand the bias back as the diff takes over — it is front-left tyre life

**`bb −2` is not free any more.** Forward bias puts more of the stop through the
front axle, and **the front-left is your wear limiter at 4.0%/lap.** The circuit
reference calls Road Atlanta front-biased with a slight front-left lean, and your
own gauge agrees — FL 0.316 → 0.389 → 0.400 across laps 8–10, worst corner on
every reading.

**So every click of bias you can give back is FL life, and FL life is now a
strategy input.** Start the race at **−1**, not −2 or 0:

- **−1** is where Yas ran and it is your fine adjustment around neutral.
- **If the rear is settled by lap 3, try 0** — that is the diff working, and it
  is worth reporting.
- **If you need −2 again, take it** and tell me. That is the finding: `lsd_b`
  needs to go past 34, and the ballast becomes the next lever.

**Never positive here.** T10a with a rearward bias is a spin.

---

# 3. Shift points — you are right, and the beep never fired

## 3.1 GT7's 8805 is the limiter, not the shift point

**Your instinct is correct and it is measured twice on this car.** The upshift
point is where the *next* gear's acceleration, at the rpm it lands on, beats this
gear's. Measured from your own throttle-open frames:

| Upshift | 36 laps, v1.70 | Session 71, v1.71 | **Use** |
|---|---:|---:|---:|
| 1 → 2 | 8500 | limiter-won* | **8500** |
| 2 → 3 | 8250 | 8500 | **8250** |
| 3 → 4 | 8250 | 6750† | **8250** |
| 4 → 5 | 8000 | **8000** ✅ | **8000** |
| 5 → 6 | 8250 | **8250** ✅ | **8250** |

\* first gear had 272 frames — not enough to compare.
† one bin compared. Discard it; the 36-lap figure stands.

**Two of the five agree exactly across a physics update, two circuits and a
gearbox change.** Holding to 8805 costs you in every gear — **555 rpm too late in
4th, 305 in 3rd and 5th.**

**For fuel, short-shift the straights another ~500 rpm below these** — the pit
straight and the back straight only, leaving the esses and T10b at full revs.
That is where fuel-per-second is highest and the lap-time price is lowest.

## 3.2 ⚠️ Why you did not hear it — and it is a two-minute fix

From your own log, timestamped at the start of the session:

```
09:51:25  pitcrew.beep  car 3391 has no measured shift points on the fitted
                        sheet, so the beep is silent.
```

**The beep does not use the 7,500 rpm in your settings. It reads a per-gear table
off the fitted setup sheet, and the fitted sheet is `Yas Marina race Rev C`,
whose `shift_rpm_json` is empty.** So it was silent for all eleven laps — and
**my v1 §4.2 was wrong to tell you that following the beep was already saving you
fuel. There was no beep.** Correcting that: the saving in §1 has to be driven by
hand tonight, or by putting the table on the sheet.

**The fix:** put the shift table on the Road Atlanta sheet — the paste block in §5
now carries it.

> **A second failure mode exists and it will bite even with the table in place.**
> Your log has seven of these on 22 August:
>
> ```
> beep failed: TimeoutError: the card was still busy 0.4s after the beep
>              asked for it - dropped rather than played at the wrong rpm
> ```
>
> That is the beep losing the audio card to the voice engineer or the haptics.
> **Dropping is correct behaviour** — a beep at the wrong rpm is worse than
> none — but seven drops in one evening is a contention problem, not an
> occasional collision. **Do not rely on the beep for the fuel saving tonight.**
> I can look at it properly after the race.

---

# 4. What is not changing

| Held | Why |
|---|---|
| `de_r` 32 | Shipped this morning, never separately read. One family is already moving. |
| `de_f` 40 | Held for the same reason as v1 §2.6 — firm front rebound works against the rear over the T10a crest. |
| Ride height 89 / 107 | No bottoming or platform complaint in eleven laps. |
| Downforce 150 / 260 | Front is at the ceiling of the new range. Traction is good; do not touch the rear. |
| `lsd_a` 17 | **Answered by your report** — *"drive traction feels really good."* The Rev B fork is closed: leave it. |
| TCS 1 | Traction is good; no reason to change it in the race. |
| Gearbox | Nothing in the session says otherwise, and §3.1 says the gears are fine — it is the shift *points* that were wrong. |
| Ballast 109 @ 0 | Still test #1, still not a race-day change. §6 |

---

# 5. Pit Crew paste block — race

**Note the new `shiftRpm` block. That is what makes the beep work.**

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Michelin Raceway Road Atlanta - Full Course",
    "sessionType": "race",
    "date": "2026-08-23",
    "gameVersion": "1.71",
    "compound": { "front": "RS", "rear": "RS" },
    "assists": { "abs": "Off", "tcs": 1, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Road Atlanta race Rev B",
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
      "bb": -1,
      "top": 300, "fg": 3.600
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "shiftRpm": { "1": 8500, "2": 8250, "3": 8250, "4": 8000, "5": 8250 },
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

**Three values move from what you just drove:** `lsd_i` 0 → 5, `lsd_b` 26 → 34,
`bb` −2 → −1. Plus the shift table, which is new.

> ⚠️ **The session recorded `setup_sheet_id 18` — "Yas Marina race Rev C".** The
> app still thinks your car is on the Yas sheet, which is why the beep was silent
> and why nothing in session 71's record reflects what you actually drove. **Paste
> this block and check the Event screen shows the Road Atlanta sheet fitted before
> you go out.** Fifth consecutive session with a wrong setup record.

---

# 6. After the race — in order

1. **The ballast sweep.** Now more valuable than this morning: the front-left is
   the wear limiter and rearward ballast is the only lever that moves load off
   it. Garage first, 30 seconds — read the distribution at +50, −50 and 0.
2. **A shift-point A/B for the fuel coefficient.** Two sessions, **1,500 rpm
   separation**, same fuel map, same tyres. That is the half of the short-shift
   trade nobody has measured, and it moves the optimum between 400 and 2,800 rpm
   below the crossover. `tools/shift_target.py --from-sessions FAST SLOW`.
3. **The beep contention bug.** Seven drops in one evening is worth a proper look.

---

# 7. Confidence flags

| Claim | Status |
|---|---|
| Pace 1:21.6, burn 6.275 L/lap, wear 4.0%/lap FL | **[MEASURED]** — session 71, v1.71, this car, this circuit |
| Wear 4.0%/lap | ⚠️ Measured across **three gauge readings** on laps 8–10, at `bb −2`, with off-track on 5 of 11 laps. **RR reads *backwards* across the three** (0.333 → 0.211 → 0.200), so the sampler is noisier than its 0.5% claim. FL is the consistent one. Treat 4.0% as the working figure and re-read at lap 10 tonight. |
| Burn 6.275 L/lap | Practice pace. The Yas precedent is that race burn comes in ~11% under practice — if that holds you gain about 15 L, which is 15 s of refuelling. **Plan on 6.275, expect better.** |
| One stop, fuel-bound | **[MODEL]** — `recommend()` on measured inputs, and both constraints agree |
| Shift points | **[MEASURED ×2]** — 36 laps v1.70 and 11 laps v1.71 agree exactly on 4→5 and 5→6 |
| Beep silent, cause | **[MEASURED]** — the log line names it at 09:51:25 |
| `lsd_b` 34 and `lsd_i` 5 | **[REASONED]** — two suspects, one fix that covers both. The scale question is still open |
| Whether 26 means what 22 meant | **[UNRESOLVED]** — ten seconds on the diff page, §2 |

---

# 8. RACE CARD — confirmed after practice 2 (session 72)

**The setup is finished. Nothing on the sheet moves.** Sheet 31 is fitted and all
22 values landed correctly — first time in five sessions.

```
  ┌─────────────────────────────────────────────────────────────┐
  │  22 LAPS · ONE STOP · BINDING CONSTRAINT: FUEL              │
  │                                                             │
  │  Stint 1   laps 1–14     RS      box window 13–15           │
  │  Stint 2   laps 15–22    RS                                 │
  │                                                             │
  │  Pace      1:20.7 – 1:21.0                                  │
  │  Burn      6.29 L/lap   (n=12, sd 0.14, full revs)          │
  │  Refuel    ~38 L  =  ~19 s stationary at 2.00 L/s           │
  │  Stop      ~20 s pit loss + 5.3 s dead + 19 s  =  ~44 s     │
  │                                                             │
  │  BRAKE BALANCE  −1        confirmed good, practice 2        │
  │  UPSHIFT        8500 / 8250 / 8250 / 8000 / 8250            │
  │  SHORT-SHIFT    ✗  DO NOT.  At 2 L/s it does not pay — §8.3 │
  │  GAUGE          read it at lap 10 and lap 20                │
  └─────────────────────────────────────────────────────────────┘
```

## 8.3 ⚠️ Short-shifting is OFF — the refuel rate reverses it

**Refuel is a per-series league setting and tonight it is 2.00 L/s** (driver,
23 Aug). Every refuel measurement in the database — four stops, 1.000 to 1.001
L/s — comes from **3× fuel events**, and no stop has ever been recorded at 2×.
The league setting outranks the inference.

**And it inverts the fuel trade, because at 2 L/s a litre is half a second
instead of a whole one, while the lap-time cost of short-shifting is unchanged.**
Asked of `recommend()` with each option carrying its own lap time:

| Discipline | Burn | Lap | Refuel | **Race total** |
|---|---:|---:|---:|---:|
| **Full revs** | 6.29 | 80.90 | 38.3 L = 19.2 s | **1835.6 s** ← |
| Light save −11% | 5.60 | 81.15 | 23.2 L = 11.6 s | 1835.6 s (**±0.0**) |
| Full short-shift −21.6% | 4.92 | 81.40 | 8.2 L = 4.1 s | 1838.4 s (**+2.8**) |

**Full revs and a light save are dead level. Full short-shifting loses.**
At 1.00 L/s the same table has saving ahead by 5 s — which is the advice I gave
in §1 and it was wrong for this event.

> **Drive it flat out.** It is never worse than tied, it is the simplest thing to
> do under a helmet, and it removes a thing to think about on a circuit you have
> sixteen laps of experience on.

**The trade rests on two borrowed numbers** — the −21.6% saving and the +0.5 s/lap
cost are both the RSR's, measured at Monza. The Shelby's own figures have never
been taken. That does not change tonight's call, because full revs is at worst
tied, but it is why this table cannot be reused at a 1 L/s series without
measuring the car first.

**The margin is decided at the stop, not now.** At practice scatter the lap count
is firm and the margin is **1.8 L**; if the race is scrappier and the count is
still open at lap 14, it is **6.3 L**. That is a 4.5-second difference and by lap
14 you will have fourteen laps of real scatter to decide it on.

## 8.1 What practice 2 confirmed and what it did not

| | |
|---|---|
| ✅ **Braking** | `lsd_i` 5 + `lsd_b` 34 worked. **`bb −1`, driver-confirmed better.** The rear-locking item open since 10 Aug is closed pending the race |
| ✅ **Pace** | best 1:21.591 → **1:20.726**, −0.87 s/lap. Confounded with track learning; the direction is not in doubt |
| ❌ **Fuel saving** | **not demonstrated** — 6.29 L/lap pooled across both sessions, no short-shifted laps exist. There was no beep to shift to |
| ❌ **Wear at `bb −1`** | **no gauge readings in session 72.** The 4.0%/lap figure is still from practice 1 at `bb −2`, which loaded the fronts harder than you are running now |

**Neither gap changes the plan.** Fuel forces the stop at any plausible burn, and
with a stop the tyres are comfortable at any plausible wear rate — 56% and 32%
across the two stints.

## 8.2 The short practice — two things, and neither is a test

**The fuel measurement is off the list.** It was going to be the headline job, but
§8.3 makes tonight's answer *flat out* whichever way it lands, so spending your
last laps on it buys nothing you can use today.

1. **Laps at race pace, full revs.** You have sixteen laps here. Use them to make
   T10a and the esses ordinary rather than to prove anything.
2. **Read the tyre gauge at the end of the run and enter it.** This is the one
   plan input still unmeasured at `bb −1` — practice 1's 4.0%/lap came from
   `bb −2`, which loaded the fronts harder than you are running now.

**✅ The shift table is now on the sheet and the beep is live** — you do not need
to type it. `Road Atlanta race Rev B` carries **8500 / 8250 / 8250 / 8000 / 8250**,
and replayed against your own practice laps it fires 3–7 times a lap, at 8261 in
third against a 8250 threshold and 8001 in fourth against 8000. **GT7's own 8805
is the limiter, not the crossover.** Two defects behind the silence are also
fixed — the sheet lookup had no circuit in its key, and the voice was blocking
the card for a whole sentence when the beep would only wait 0.4 s.

**And check the Event screen carries ballast 109 kg at position 0** — the paste
block does not import it and it has been recorded wrongly four times.

---

# 9. "More mid-corner hookup in the fronts, more drive in the rear"

## 9.1 Answered: **both phases** — so it is a real mid-corner push, not the diff trap

I asked because `02` §10.4 carries a double-warning: *if the push happens on
throttle, the mid-corner table is the wrong table* — every fix on it adds front
grip, which **masks a power-on diff problem while costing roll control or entry
stability.** It caught us at Laguna and was pre-registered and avoided at Monza.

**Your answer clears it.** A push that is there **off throttle as well** cannot
be a locking problem alone — an open-throttle-only push is the diff, a
both-phase push is mechanical balance. **So the front fix is legitimate**, and
there may be a *separate* on-throttle component sitting on top of it.

## 9.1a What the corners say

| You named | Reference calls it | Reads as |
|---|---|---|
| **T4–T7** — *"wind around left then down the hill and back up"* | the esses, blind and over crests, into the **heavy slow left at T7** | fast direction-changes plus one slow corner — **a push across both means balance, not aero** |
| **T7 exit** | traction-limited, feeds the run to T10 | drive |
| **T12** — *"last turn before s/f"* | **the highest-value exit on the lap** | a push here costs you the whole pit straight |

**Two of the three are the circuit's named traction-limited exits (T7 and T12).**
That is your "drive in the rear" complaint landing exactly where the reference
says it should.

> **⭐ And the push may be feeding the tyre problem.** `02` §10.11 lists, under
> front tyres wearing out: *"address any mid-corner understeer — a pushing car
> scrubs its fronts continuously."* **Your front-left is the wear limiter at
> 4.0%/lap and you are describing a car that pushes.** Those are probably one
> problem, which makes the front fix worth more than the lap time alone.

## 9.1b ✅ The diff fork is CLOSED — measured off the UDP, not observed at the wheel

**You asked whether the telemetry could tell. It can, and I should have looked
before asking you to watch the tyre indicators.** The frames carry per-wheel slip
ratio. Taking every corner-exit frame in both practice sessions — throttle >70%,
off the brakes, still cornering — and splitting the rear axle into **inside** and
**outside** (identified from suspension load: the compressed wheel is the outside
one):

**17,421 corner-exit frames, sessions 71 + 72.**

| Speed band | n | inside | outside | Δ | inside **ALONE** | **BOTH** |
|---|---:|---:|---:|---:|---:|---:|
| 0–90 km/h | 292 | 1.0561 | 1.0517 | +0.0044 | **0.0 %** | **100 %** |
| 90–130 km/h | 3,471 | 1.0534 | 1.0462 | +0.0072 | **0.1 %** | **99.7 %** |
| 130–180 km/h | 8,403 | 1.0354 | 1.0319 | +0.0035 | 1.3 % | 93.8 % |
| 180+ km/h | 5,255 | 1.0243 | 1.0218 | +0.0025 | 5.7 % | 53.7 % |
| **gear 2** | 3,808 | 1.0506 | 1.0448 | +0.0058 | **0.0 %** | **98.1 %** |

**It is "both rears together", and it is not close.** At the slow exits — the
T7 and T12 speeds you named — the inside wheel spins *alone* in 0.0% and 0.1% of
frames, and the two rear wheels track each other to within **0.4–0.7% of slip
ratio.** That is an axle moving in lockstep. An under-locked diff would show a
large inside/outside split; yours shows almost none.

> **The asymmetry is the load-bearing measurement and it is threshold-free.**
> The 1.02 wheelspin line was calibrated on the RSR, so the absolute slip levels
> carry a caveat. Inside-minus-outside does not — both wheels sit on the same
> axle with the same torque, so the split is self-referencing.

### ⚠️ So `lsd_a` goes DOWN, and my "take it to 22" was wrong

**Both external arguments pointed up and your own car's data beats both of them:**

| Argument | Said | Verdict |
|---|---|---|
| Road Atlanta reference: *"LSD acceleration 22–28"* | up | **overruled** — generic circuit guidance, pre-1.71 |
| `17` §9: slip down 40–60%, *"re-test upward from 14"* | up | **overruled** — written for the RSR, not measured on this car |
| **Your rear axle, 17,421 frames** | **down** | ✅ |

**`lsd_a` 17 → 14.** That is `02` §10.5 #1 — *"the single most validated entry in
this whole section"*, twice in-house (Huracán 18→14, RSR 16→14), and 14 is the
number both landed on.

**And it answers both of your requests with one change**, which is what §9.1b
below said the resolved fork would do:

- **Mid-corner front** — high accel-sens *"makes GT7 cars want to drive in a
  straight line and not continue turning."* **That is your push, described in the
  knowledge base's own words**, and it is present off throttle too because a
  locked axle resists yaw whenever it is transmitting anything at all.
- **Rear drive** — an axle dragged into slip together is wasting grip on both
  tyres. Unlocking it lets the loaded outside wheel do the work.

**Rear compression damping stays at 28.** It was queued for exit traction, and
`lsd_a` is the dominant lever for the same symptom — shipping both would make
neither readable. It is the next item if 14 is not enough.

## 9.2 Tonight — two changes, one per axle, one per request

**Normally one change per run. These two are on different axles in different
corner phases, so you can still tell them apart:**

| Change | | Why |
|---|---|---|
| **Front ARB 5 → 4** | mid-corner, turning | `02` §10.2 makes ARBs the *primary* mid-corner tool. Softer front bar puts more load on the inside front through the middle of the corner. **It is also #4 on the front-tyre-wear list**, and the front-left is your wear limiter at 4.0%/lap — so it pays twice. |
| **`lsd_a` 17 → 14** | exit, throttle open | Measured, §9.1b. The most validated entry in the section and the number both in-house tests landed on. Answers the front *and* the rear. |

**Front downforce cannot help** — 150 is the ceiling of the new 50–150 range.
That lever is gone, and it is why the bar is doing this job.

> **If it feels worse, put the ARB back first.** A softer front bar increases
> roll, and you are sensitive to a front axle that does not answer immediately —
> so the failure mode is *lazier*, not *pushier*. One click back and you are
> where you started.

**Not touching:** `lsd_b` 34, `lsd_i` 5, `bb` −1, ride height, camber, toe. The
braking took three attempts to get right and nothing on this list needs to
disturb it.

## 9.3 The proper answer is the ballast, and it is still the wrong night for it

**Rearward ballast is the one lever whose signature is exactly what you
described** — `02` §10.10 #6 *"very effective on RWD"* for rear drive, and it
adds mid-corner rotation at the same time, and it takes load off the front-left.
Your two requests are one ballast move.

**It still does not go in tonight:** 4 points of distribution changes what each
end's natural frequency should be, there is no practice to re-check the springs
in, and it costs entry stability — the thing that took three attempts. **Garage
sweep first (§6.1), then a proper run.** It is now clearly the number one item.

---

*Rev B issued 23 Aug 2026 · after practice 1, race card confirmed after practice 2 · GT7 v1.71*
*The strategy reversed: one stop, fuel-bound, and both constraints now agree.*
*`lsd_i` 0 was my error and it goes back to 5. `lsd_b` to 34 covers both suspects.*
*Every litre is a second — short-shift to shrink the stop, not to delete it.*
*The beep was silent all session: no shift table on the fitted sheet.*
