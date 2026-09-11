═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  DEEP FOREST RACEWAY — FULL COURSE (4.253 km)
  **ROUND 6 SUPERCARS — v1, COLD START**
  NGR Supercars Series 1 Rd6 · 6 Sep 2026 10:30 UTC · 30 min + 180 s
  standing · FIXED/CLEAR · RS/RM/RH · 2× wear / 2× fuel · refuel 2.0 L/s
  ABS **prohibited** · TCS **prohibited** · countersteer **prohibited**
  BoP **off**, tuning **allowed** — read from the hub, not assumed
  Issued 6 Sep 2026 · v1.71 · **SCREEN-CONFIRMED, rank zero clean**
═══════════════════════════════════════════════════════════════════

# 0. What this sheet is

**No lap, session or telemetry frame exists for this car at this circuit, and
none exists for this circuit at all.** `tools/data_health.py` returns three
lines and all three are refusals:

```
  corners        no corner observations - nothing to claim
  corner model   none stored - corners cannot be named
  gearbox        no sessions on file here - nothing to compare
```

So there is no symptom and therefore no diagnosis. **Every mechanical value on
this sheet is held unchanged from sheet 50, the setup you raced at Red Bull
Ring.** That is deliberate and it is the finding, not an absence of one — §3
prices each hold.

**The three things this sheet actually delivers** are the ones that are new:

1. **The shift beep, which has never existed for this car.** §4.
2. **The gearing constant, re-derived and corrected.** §5.
3. **The one question that decides whether this is a one-stop or a two-stop.**
   §7. It is a wear question, it is genuinely open, and an eight-lap practice
   stint settles it.

---

# 1. Rank zero — **CLOSED, and it is clean**

Settings screenshot read **6 Sep 2026**. This car had never had one.

✅ **22 of 23 visible values match sheet 50 exactly** — tyres, all six
suspension pairs, camber, toe, all three differential axes, both downforce
values, ECU, restrictor, ballast and ballast position.

✅ **`arb_f` is 5.** Eleven-day dispute closed. **App sheet 31 is the wrong
record** — and that is not cosmetic: the Road Atlanta race was run on `arb_f` 5,
not the 4 its own stored sheet says, so any reading taken against sheet 31
describes a car that was never on track. Filed as `RECONCILIATION` AS1.

✅ **Ballast 109 kg at position 0 is in the car.** And the screen settles what
it is: total weight reads **1,335 kg = exactly the series weight limit**, so the
**mass is a regulation, not a lever**. Only the position is tunable.

✅ **The wheel.** Driver, 6 Sep: *"DD+ wheel settings are perfect, in game FFB 6
SEN 10."* Open since 23 Aug, closed. **Grip readings from here are valid.**

## 🔴 Brake balance is **−2**, and no sheet has ever said so

Every sheet on file says `0`; Road Atlanta Rev B says `−1`; on 23 Aug you said
one click forward. **The car reads −2 — two clicks FORWARD on this car.**

Your trim is yours to make and I am recording it, not correcting it. But it is
information I did not have, it moves one direction across the season
(0 → −1 → −2), and with **ABS prohibited** in this series that is **20% of the
bias range**. Filed as `RECONCILIATION` AS2. §3.4 says what it means here.

## ✅ The gearbox: read off Manual Adjustment, 6 Sep — **exactly as recorded**

`3.400 / 2.410 / 1.760 / 1.500 / 1.320 / 1.165`, final `3.600`. **Rank zero is
now 23 of 23 and nothing on this sheet is `ISSUED`.** That is the first complete
record in the programme — the RSR got 14 of 14 *visible*, but its gearbox and
brake balance were both still unread. **This car's box is confirmed twice over,
SCREEN and FEED, in agreement.**

So: **§5, §4's shift table and the whole gearbox plan stand as written.** The
beep is issued for the box you are actually running.

### And `Top Speed` 270 is settled — the readout moves the wrong way

265 was carried over from sheet 45 and never re-read after you hand-cut the box.
With the real ratios in hand the two RBR boxes compare directly:

| box | Top Speed readout | 6th ratio | 6th ACTUALLY tops at |
|---|---:|---:|---:|
| sheet 45, auto-generated | **265** | 1.050 | **290 km/h** |
| sheet 50, hand-cut *(current)* | **270** | 1.165 | **261 km/h** |

**The readout rose 5 while the real top speed fell 29.** `Top Speed
(Automatically Adjusted)` is not a top speed, is not the generator input once
hand-cut, and is not any gear's limiter speed. **Never read a road speed off it.
[MEASURED], 6 Sep 2026.**


---

# 2. Closing Round 5 — three predictions, and one number that has to be retracted

### 🔧 First: Round 5 was ended by hardware, and none of it is about the car
Driver, 6 Sep: **the Fanatec wheelbase locked up from a GT7 error introduced by
the 1.71 update**, since resolved by a Fanatec firmware update.

That is the whole story of session 101's tail — a 1.08 s spin on lap 8, then
**20.2 s and 10.4 s off-track** on laps 14 and 15, P6 → P9, and the capture
stopping at 15:04 with 904 s to run. **Nothing after lap 13 of that race
describes the car, the setup or you.** Filed as `RECONCILIATION` AS3.

The good news for the numbers below: laps 1–13 are clean and already the only
ones used, because 8, 14 and 15 were flagged `excluded` at capture. **The race
burn figure stands.** What it can see:

### ✅ *"One stop, and the binding constraint will be fuel."* — HELD
Race burn measured **3.813 L/lap, sd 0.082, n = 12** over 2.336 km. A 30-minute
race at ~51 s is ~35 laps ⇒ ~134 L against a 100 L tank. Fuel bound it.

### ❌ The stop was planned **five laps too early**, and the reason generalises
Strategy 15 priced stint one at **21 laps** on an expected **4.47 L/lap**, taken
from *practice*. The race actually burned **3.813**. At the real rate the tank
covers **26 laps**.

**Practice burn overstates race burn on this car, on every circuit, in the same
direction:**

| circuit | practice | race | |
|---|---:|---:|---:|
| Yas Marina *(v1.70, void as evidence)* | 7.644 | 6.504 | −14.9% |
| Road Atlanta | 6.482 | 6.256 | −3.5% |
| RBR Short | 4.199 | 3.813 | −9.2% |

**[MEASURED], n = 2 post-patch circuits.** So when run 3 gives me a practice
burn today, I will discount it **3–9%** for the race and say which end I used.

### ⚠️ *"`top` 265 will still leave rpm unused"* — the question was voided
You hand-cut the box instead, which is the better answer. §5 replaces the rule
it was testing.

### ⏸️ *"`lsd_a` 17 → 24 improves exit traction"* — **NEVER RUN.** Sheet 50 still
reads 17. It is offered again below, and this is the second time. If it is not
worth three laps to you, say so and I will stop proposing it.

### 🔴 **Retracted: "Road Atlanta's front-left wear limiter was 4.0%/lap."**
That number is in the Round 5 sheet and it carried the whole wear argument. It
does not survive being looked at. Session 77's gauge series is **non-monotone
and straddles a tyre change**: FL reads 33.3 → 33.3 → 44.4 → 42.9, RR reads
25.0 → 44.4 → **20.0** — wear running *backwards* — and the readings at laps 20
and 21 are eight laps after a fresh set fitted on lap 12. **Road Atlanta has no
usable wear measurement.** The RBR series, by contrast, is clean and monotone in
all four sessions, and it is the only wear evidence this car has.

---

# 3. Every mechanical value is held, and here is the price of each hold

The circuit reference (`05-track-reference.md` §2.4, **[DOCTRINE], compiled
Aug 2026 on a pre-1.71 baseline**) names three levers. I am moving none of them,
and each refusal has a different reason.

## 3.1 Aero — doctrine says "run high", and I am holding at 73.3% rear anyway

Deep Forest is **MEDIUM-HIGH downforce, ~55% full throttle, almost every corner
a 3rd/4th-gear sweeper**. The obvious move is `df_r` 260 → 300.

**It is the wrong move and the range record is why.** `df_f` is already at
**150, which is 100.0% of this car's front range** — it cannot go up. So raising
the rear only moves the aero balance **rearward**, on a circuit whose own
reference names **front tyre life as lever #1** and whose wear it calls "high
and front-biased". Adding rear downforce here loads the front harder in exactly
the linked sweepers that do the damage.

The only way to move balance forward is to *lower* the rear.

**The screenshot has now promoted that from a maybe to run 2.** GT7's own
readout says this car is **high-speed understeering, −0.50**, and high speed is
what Deep Forest is made of — *"almost every corner a 3rd/4th-gear sweeper."*
That is the third independent indicator pointing at the front axle, alongside
the measured front-left wear limiter and two clicks of forward bias with no ABS.

**Held for run 1. It is run 2, and it goes DOWN. See §8.**

## 3.2 Ride height and springs — already where doctrine asks, and the instrument is broken

Doctrine: *"medium-stiff springs; you can run relatively low"*, and *"check ride
height at the banked final corner specifically."* You are at **89/107 mm
(16.5% / 14.1% of range — low)** on **3.05/3.20 Hz (52.5% / 60.0% —
medium-stiff)**. That is the prescription already.

**And I could not check the banked corner if I wanted to.** The app's
`bottoming` detector fires on the most *extended* wheel — GT7's suspension
channel is larger-is-more-compressed and the reference takes `min`. It has been
wrong since 17 Aug. **[UNMEASURED], and it will stay that way.**

## 3.3 `lsd_a` 17 — doctrine wants 20–26, and the gap is smaller than it looks

At Red Bull Ring the doctrine wanted **28–35** and you were at 17; that was a
large gap and it still went untested. Here the band is **20–26**, and the same
reference adds *"the linked sweeper sections punish high lock"* — so Deep
Forest's own doctrine is the most cautious of the two.

Against moving it: **[DRIVER REPORT]**, Road Atlanta — *"drive traction feels
really good."* That is primary evidence and it beats a pre-1.71 table. **Held.**
Run 2 below if you want it settled.

## 3.4 Brake balance −2 — recorded, not corrected, and here is what it costs here

Deep Forest doctrine says **one to two clicks forward**. On this car that is
`bb` −1 to −2. **You are at −2 — the far end of the doctrine's own band, and
doctrine agrees with you exactly.**

**I am not asking you to change it.** It is your trim, my refusal is about
*recommending* forward bias rather than about you running it, and you have been
right against the derived metric four sessions running.

**What I owe you is the consequence, stated once.** At this circuit, and only at
this circuit, it compounds:

- Deep Forest's own reference names **front tyre life as lever #1** — *"the
  stint is the race"* — and grades its wear **severity 5**, the harshest on your
  calendar.
- Your measured wear limiter on this car is the **front-left**, at ~1.6× the
  front-right.
- **ABS is prohibited**, so bias is doing all the lock management, and −2 is 20%
  of the range forward.
- GT7's own readout: **high-speed understeer −0.50**.

All four point the same way. **The lever I can move to help is aero balance, not
your bias** — §3.1, and it is run 2.

One thing worth knowing: `lsd_b` is at **34**, which is high, and the driver
model says you control rear lock with braking sensitivity and rotate on release.
If the fronts are what run out today, `lsd_b` is the knob that could let you
carry *less* forward bias for the same rear stability. **I am not proposing it
this weekend** — it is uninstrumented and one change per run — but it is the
honest alternative to living with the front wear.

## 3.5 The one change I nearly made and did not: front camber

`cam_f` 1.4° is 23.3% of range, and continuous medium-speed lateral load is the
textbook argument for more. Two reasons not to: **camber has no telemetry ground
truth at all**, and on the Huracán *reducing* camber improved braking and
turn-in — backwards from textbook. 1.71 also reworked the exact model that made
heavy camber expensive. **A coin flip with no instrument is not a change.**

---

# 4. The shift table — **issued, and this car had none**

`shift_points` held **one row, for the RSR**. The Shelby has never had a table
in the store, and the beep reads that store — so **it has been silent in this
car**. Written today as id 2:

```
  performance   1: 8500   2: 8250   3: 8250
  fuel saving   1: 8000   2: 7750   3: 7750
  gears 4, 5 and 6: SILENT, on purpose
```

**[MEASURED]** by `tools/shift_points.py` over the 156-lap Shelby archive:
1→2 **8500** (206 frames at the shift point), 2→3 **8250** (2,384), 3→4 **8250**
(6,932). Those three are solid.

**Why 4, 5 and 6 do not beep.** The same tool returns **8750** for 4→5 and 5→6
— off **76** and **14** frames. That disagrees with the 8000/8250 carried on
sheet 31 and there is not enough evidence to settle it either way. A number
nobody designed sounds at the wheel exactly like one that was, so it stays
silent. You will hear a beep in 1st, 2nd and 3rd, and nothing above.

**Fuel table** is the −500 rpm short-shift. Measured cost at the moment of the
shift: **+1.48 / +1.12 / +0.67 m/s²** in gears 1/2/3 — cheapest in 3rd, which is
where you will spend most of this lap.

> ⚠️ **Confound, stated:** the archive pools three different gearboxes into one
> accel-vs-rpm curve. A ratio change moves the road speed of the crossover, so
> this is second-order mixed rather than clean. **[MEASURED, with that caveat.]**

> ⚠️ **If you re-cut the box after run 1, tell me and I re-issue this.** A shift
> table belongs to a gearbox.

---

# 5. The gearing constant — re-derived, and it replaces the Round 5 rule

**[MEASURED], 6 Sep 2026, 156 laps, three gearboxes.** Within any session,
`ratio × (km/h per rpm)` is constant across gears at **0.0345**, and the limiter
sits at **~8,800 rpm**. Therefore:

```
      K  =  ratio  ×  (speed at which that gear reaches the limiter)  =  304 km/h
```

Road Atlanta and RBR agree to **0.3%**, which independently confirms both ran
final gear 3.600 on the same rolling radius.

**This supersedes the Round 5 sheet's rule** that `top` is the road speed at
which 6th reaches the limiter. That was falsified when `top` 265 produced a 6th
topping at **291** km/h. **`top` is a spacing slider. K is the invariant.**

Your current box, and what it tops out at:

| gear | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| ratio | 3.400 | 2.410 | 1.760 | 1.500 | 1.320 | 1.165 |
| km/h at limiter | 89 | 126 | **173** | **203** | 230 | **261** |

**Why I am carrying it rather than cutting a Deep Forest box today.** Doctrine
asks for *"2nd for the hairpins, 4th carrying the linked sweeper sections, and
gear for the pit straight"* — and I have **no corner-speed data for this
circuit at all**, so every one of those three targets would be a guess on a
guess. The RBR box happens to be a reasonable prior: it was cut for a circuit
with a slow hairpin and medium exits, and its 6th tops at 261, which is
plausible for this lap.

**But the 3→4 crossover at 173 km/h is the number I most expect to be wrong.**
If the linked sweepers sit around 150–190 km/h you will be shifting in the
middle of them, and this circuit specifically rewards holding one gear through a
sequence. **Run 1 measures it and I re-cut the same evening.**

> Hand-cutting the box at Red Bull Ring moved the clean median from **51.325**
> (n=8) to **50.616** (n=11) — **0.709 s/lap**. Honestly: that is **~2.1σ**, and
> it is confounded with learning, because session 93 was your first ever laps
> there and 94 followed immediately at ~0.3 s/run of improvement. **The real
> gearbox effect is somewhere between 0.4 and 0.7 s/lap** — still the largest
> single effect this project has measured on this car.

---

# 6. The sheet

| | Value | % of range | |
|---|---:|---:|---|
| Ride height F / R | 89 / 107 mm | 16.5 / 14.1 | held — §3.2 |
| Natural frequency F / R | 3.05 / 3.20 Hz | 52.5 / 60.0 | held — §3.2 |
| Anti-roll bar F / R | **5** / 4 | 44.4 / 33.3 | SCREEN — dispute closed, §1 |
| Damper compression F / R | 24 / 28 | 20.0 / 40.0 | held |
| Damper expansion F / R | 40 / 38 | 33.3 / 26.7 | held |
| Camber F / R | 1.4 / 1.0° | 23.3 / 16.7 | held — §3.5 |
| Toe F / R | −0.05 / 0.10° | 47.5 / 55.0 | held |
| LSD initial / accel / braking | 5 / 17 / 34 | *absolutes* | held — §3.3 |
| Downforce F / R | 150 / 260 | **100.0** / 73.3 | held — §3.1 |
| Brake balance | **−2** *(as it sits in the car)* | 30.0 | SCREEN — yours, recorded not corrected, §3.4 |
| Gear ratios | 3.400 / 2.410 / 1.760 / 1.500 / 1.320 / 1.165 | | **SCREEN + FEED**, confirmed twice — §1 |
| Final gear | 3.600 | 53.3 | **SCREEN**, confirmed |
| Top Speed readout | **270** | | SCREEN — a readout only, never a road speed, §1 |
| Ballast | 109 kg @ 0 | | SCREEN — in the car; the mass is a regulation |

**LSD in absolutes** — 1.71 moved its three axes off a shared scale and the
register has not been re-read. *(Rule retired 11 Sep 2026: all four cars carry 0–30 / 0–100 / 0–100 on v1.71 - `11`.)*

---

# 7. Strategy — one stop is certain. **Two is the open question, and it is a wear question.**

## 7.1 What is already decided

**Lap time [ASSUMED].** No data. Gr.3 runs 1:26–1:29 here; at Road Atlanta this
car laps within 0.1% of that circuit's Gr.3 reference. Deep Forest is
corner-denser and higher-downforce, which suits Gr.3 relatively better, so
expect the Shelby a little worse than parity: **≈ 88–95 s**, call it 91.

**Race distance.** 1800 s ÷ ~91 s ≈ **19–20 laps**, plus the finish-delay lap.

**Fuel [MEASURED, scaled].** Two independent scalings of the two post-patch race
measurements, and they agree:

| method | basis | Deep Forest |
|---|---|---:|
| per second | 0.0743–0.0768 L/s (RA + RBR races) | 6.76–6.99 L/lap |
| per km | 1.530–1.632 L/km (RA + RBR races) | 6.51–6.94 L/lap |

**≈ 6.5–7.0 L/lap. A 100 L tank covers 14.3–15.4 laps against a ~20-lap race.**

> **You are stopping. It is fuel, and it is decided before you drive a lap.**

## 7.2 The open question: is it a **two**-stop?

Three ceilings, and they do not agree:

| ceiling | value | source |
|---|---:|---|
| **Fuel** | **14.3–15.4 laps** | **[MEASURED]**, two post-patch races, both scalings |
| **Tyre**, from your own gauge | **14.8–22.2 laps** | **[DERIVED]** — RBR front-left 0.90–1.35 %/km × 4.253 km, then `0.85 / w` |
| **Tyre**, from circuit doctrine | **6.5–8 laps** | **[DOCTRINE]** — reference says 13–16 laps at 1×, halved for 2× |
| **Evidence** | **16 laps** | longest continuous run on file for this car (session 101) |

**The two tyre numbers are a factor of three apart and they demand opposite
races.** If your measured rate carries, fuel binds at ~15 and it is a
comfortable one-stop. If the doctrine is right, the tyre binds at ~7 and it is a
**two-stop, and the fuel plan is irrelevant.**

I am not going to average them. Two things pull each way, honestly:

- **Toward the doctrine being right:** Deep Forest's wear severity is graded
  **5** against Red Bull Ring's **3** — the harshest circuit on your calendar —
  and it is continuous lateral load with almost no recovery.
- **Toward your measurement being right:** RBR's front-left rate is a
  *worst-wheel-on-an-asymmetric-circuit* number. RBR Short's heavy corners are
  all rights, so the front-left is the loaded outside wheel every time and it
  ran ~1.6× the front-right. Deep Forest is direction-balanced, so the same
  total front load spreads across both fronts and the *peak* wheel rate should
  come down.

**Eight laps of practice with the gauge settles it.** That is run 3, and it is
worth more than any setup change on this sheet.

## 7.3 The stop itself

**Refuel is 2.0 L/s** — from the hub's own series settings, not assumed. Total
race fuel ≈ 20 × 6.75 ≈ **135 L**; you start with 100; so **~35–40 L goes in at
the stop = 17.5–20 s standing**, plus 5–10 s dead time, plus ~19–20 s of pit
transit. **The fuelling is longer than the pit lane.** Standing time decides a
GT7 stop and it is all fuel.

That also means the second stop of a two-stop costs much less than the first
looks: the total fuel is fixed, so the extra cost is one more transit and one
more dead time — **≈ 25–30 s, not 40.**

## 7.4 Two things about this circuit that invert the standing rules

- ⚠️ **"The undercut is weak in GT7" does not survive here.** The reference
  calls Deep Forest **narrow, with genuinely hard overtaking**, and says the
  undercut is *unusually strong* because track position is expensive. Both are
  true at once: the undercut is still mechanically weak (cold out-lap, long pit
  delta) but what you buy with it is worth more here than anywhere else you
  race. **[DOCTRINE] — I have no measurement of either.**
- **The grid is set by fastest lap, not by a qualifying session.** Your practice
  pace *is* your grid slot.

## 7.5 What I am not doing yet

No stop lap, no fuel load, no window. That needs `build_inputs` and
`recommend()` on a **measured** lap time and a **measured** burn, and both come
out of runs 1 and 3. **Ask me for the plan after run 3 and it will name which
limit bound it, from the expression that decided it.**

---

# 8. The runs — three, priced, in this order

**One change per run, three clean laps minimum.** Note that Round 5's Rev B
changed the gearbox *and* `de_r` in the same run, which is why neither has a
clean verdict.

### Run 1 — learn the circuit and cut the gearbox · 6–8 laps
**No setup change.** This run exists to make the sheet honest.

| Read | Why |
|---|---|
| **Vmax and the rpm at it**, clean air, main straight | Sets 6th. Currently tops at 261 km/h. |
| **The gear you are in through the linked sweepers**, and roughly how fast | The 3→4 crossover at 173 km/h is the value I most expect to be wrong |
| **The gear at each hairpin exit** | Doctrine wants 2nd; 2nd currently runs to 126 km/h |
| **Lap time** | Nothing about this race can be planned without it |
| **The tyre gauge at the end** | The only wear instrument that exists |

Then I re-cut the box from K = 304 and re-issue the shift table with it.

> Do not chase a time. Six laps of an unknown circuit are worth more than three
> fast ones — and the app cannot name a corner here and will not pretend to.

### Run 2 — **aero balance** · 3+ clean laps *(this replaces the diff test)*

> **[HYPOTHESIS]** This car is front-limited at Deep Forest, and moving aero
> balance forward buys both lap time in the sweepers and front tyre life.
>
> **[BASIS]** Four indicators, all pointing the same way, and only one of them
> is doctrine:
> - **[MEASURED]** front-left is the wear limiter in all four RBR sessions, at
>   ~1.6× the front-right.
> - **[DERIVED, by GT7]** its own stability readout: high speed **−0.50
>   (Under)**, low speed −0.29 (Neutral). Deep Forest is a high-speed lap.
> - **[SCREEN]** two clicks of forward brake bias with **ABS prohibited**.
> - **[DOCTRINE]** the circuit reference names front tyre life lever #1 and aero
>   level lever #2, *"set in the linked sweepers"*, and grades wear severity 5.
>
> **[TEST]** `df_r` **260 → 235**. Front cannot move — it is already 100.0% of
> range — so the whole adjustment is on the rear. 25 units is 16.7% of the rear
> range; **[ASSUMED]** sizing, because I have no measurement of this car's aero
> magnitude and the one figure on file is from a different car.
>
> **[COST]** 3 clean laps, after run 1 or the gearbox confounds it.
>
> **[FALSIFIED BY]** the rear stepping out in the linked sweepers, instability
> under trail-braking into the medium descending stops, or anything unsettled
> through the **banked final corner** — that corner loads the rear vertically
> and it is the one place this change could bite. Any of those and it goes
> straight back to 260 and the front stays where it is.
>
> ⚠️ **Deep Forest is narrow with hard overtaking.** If run 1 leaves you at all
> uneasy with the car, skip this and race sheet 50 as it stands. A loose rear
> here is expensive in a way it was not at Red Bull Ring.

### Run 4 (only if runs 1–3 leave time) — the differential

`lsd_a` **17 → 22**. Doctrine wants 20–26; against it, your own Road Atlanta
report — *"drive traction feels really good"* — and this circuit's own warning
that the linked sweepers *punish* high lock. **Falsified by** running wide on
power out of either hairpin, earlier wheelspin, or turn-in going dull.

**This is the third time I have written this test and it has never run.** It is
now behind the aero test because the evidence for that one is four-sided and
this one is doctrine against your own report. **Say the word and I will stop
proposing it.**

### Run 3 — a stint at race pace, full tank · **8+ laps, and this is the important one**

**Read the gauge at the start and at the end.** This is the run that decides
one stop or two, and §7.2 is undecidable without it. Eight laps is enough to
separate a 4%/lap rate from a 12%/lap one — they differ by 64 percentage points
over that run, which is far outside the gauge's coarseness.

Also gives me the practice burn, which I will discount **3–9%** for the race
per §2.

---

# 9. Confidence

| Claim | Status |
|---|---|
| Range record: verified, v1.71, 23 Aug 2026 | **[MEASURED]** — post-patch, valid |
| Race format: 30 min, 2×/2×, 2.0 L/s, ABS+TCS prohibited, no overrides | **[MEASURED]** — read from the hub's own round and series records |
| K = 304 km/h; limiter ~8,800 rpm | **[MEASURED]** — 156 laps, 3 boxes, two circuits agree to 0.3% |
| Shift points 8500 / 8250 / 8250 in gears 1–3 | **[MEASURED]** — 206 / 2,384 / 6,932 frames |
| Shift points in gears 4–6 | **[UNMEASURED]** — 76 and 14 frames. **Silent on purpose.** |
| Race burn 6.5–7.0 L/lap ⇒ one stop, fuel-bound | **[DERIVED]** — two scalings of two post-patch races, in agreement |
| Practice burn overstates race burn 3–9% | **[MEASURED]** — 2 post-patch circuits, same sign |
| Lap time 88–95 s | **[ASSUMED]** — Gr.3 reference and one parity observation |
| Tyre ceiling 14.8–22.2 laps | **[DERIVED]** — per-km scaling of RBR gauge readings. Never measured here. |
| Tyre ceiling 6.5–8 laps | **[DOCTRINE]** — pre-1.71 circuit reference, halved for 2× |
| Road Atlanta wear 4.0%/lap | 🔴 **RETRACTED** — non-monotone series straddling a tyre change |
| Every mechanical value | **held** — §3 gives the price of each |
| Every corner claim | **[UNMEASURED]** — no corner model exists here. **I cannot see a corner at this circuit and I will not pretend to.** |
| `arb_f` 5, ballast 109 @ 0, bb −2 | **[SCREEN]** — settings screenshot, 6 Sep 2026 |
| Wheel settings valid post-1.71 | **[DRIVER REPORT]** — FFB 6, SEN 10, and the Fanatec firmware fault is fixed |
| Round 5's result is a hardware failure, not the car | **[DRIVER REPORT]** — corroborated by 20.2 s and 10.4 s off-track on laps 14–15 |
| Gearbox 3.400/2.410/1.760/1.500/1.320/1.165, fg 3.600 | **[SCREEN + FEED]** — confirmed twice, 6 Sep 2026 |
| The Top Speed readout is not a road speed | **[MEASURED]** — readout +5 while real 6th top −29 km/h |
| High-speed understeer −0.50 | **[DERIVED by GT7]** — its own static readout, not a track measurement |

---

# 10. Predictions on the record

| Prediction | Falsified by |
|---|---|
| Fuel binds before the tyre; one stop, not two | a measured wear rate above **5.7 %/lap** on run 3, which puts the tyre ceiling under 15 laps |
| Race burn lands **6.5–7.0 L/lap**; practice reads 3–9% higher | a race burn outside that band |
| 6th at 261 km/h is **too short** — Vmax will reach or pass it and the box wants lengthening at the top | rpm at Vmax reading well under 8,800, i.e. 6th never near the limiter |
| The 3→4 crossover at 173 km/h falls **inside** the linked sweepers and you will be shifting mid-sequence | you report holding one gear cleanly through them |
| Lap time **88–95 s** | anything outside that |
| `df_r` 260 → 235 does **not** make the rear loose in the sweepers or the banked corner | you report any of the three symptoms in run 2's falsifier |
| ~~The six ratios are unchanged~~ | ✅ **CONFIRMED 6 Sep — exact match. Closed.** |

**Four sessions running, your report has beaten the derived metric. If any of
the above disagrees with what you feel, you are the one who is right and I want
to hear it before the telemetry does.**
