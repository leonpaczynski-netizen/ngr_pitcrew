═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  YAS MARINA CIRCUIT (FULL COURSE)
  **REV B** — after 7-lap practice / shakedown on Rev A, RS, 13 Aug 2026
  30 min · timed · 2× tyre / 2× fuel · 0 mandatory stops · grid start · dry, night
  606 bhp · 1335 kg · 2.20 kg/hp · ABS **Off** · TCS 0 → **1 for the race**
  Issued 13 Aug 2026 · GT7 v1.70 · no BoP · ranges verified on this car 13 Aug 2026
  Revision priority as stated: **drivability — "I need to be able to lean on it"**
═══════════════════════════════════════════════════════════════════

# 0. The headline

**The car is not slow. You did a 1:54.823 on lap 1, on a full 100 L tank, and then
never went within four seconds of it again.**

That single fact reframes the whole session. Lap 1 is normally the *slowest* lap of a
stint — heaviest fuel, and you have the least information. Here it is the fastest by
**4.4 seconds over the median**, the tyres barely moved (18% at lap 7), and the
degradation trend is flat. Nothing about the car got worse. **You stopped trusting it,
and stopped using it.**

The proof is in the brake trace. At **T6 — the only genuine heavy stop in the corner
model — your peak brake pressure is 70.7%.** With ABS **Off**, a load-cell pedal and
FFB sensitivity at 10, that is not a driver at the limit. That is a driver holding
back roughly a third of the pedal because he does not believe the rear will stay
behind him. Your own words: *"[don't] trust brakes or throttle, car is too sketchy for
me to be confident to drive it fast."* **I am reading that literally and I am treating
it as the primary finding.**

So Rev B is not a pace revision. It is a **confidence revision**, and it makes exactly
three changes, each mapped to one named symptom:

| # | Symptom you named | Change | Family |
|---|---|---|---|
| 1 | Rear excited / sketchy under braking · heavy braking zones cost most | **LSD braking 18 → 22** | A4 rear-stability stack |
| 2 | Loose on throttle exit — **"both rears went together, a snap"** | **LSD acceleration 20 → 17** | A5, diagnosed |
| 3 | Gearbox too long | **Ratios re-spaced; final drive unchanged** | A6 |

Plus one assist change (**TCS 0 → 1 for the race only**) and one strategy decision
(**race on Racing Soft — measured, not hedged**).

**Nothing else on the sheet moves.** §7 lists what I left alone and why.

---

# 1. Two things in the data are wrong, and you should know before you read further

## 1.1 ✅ The car WAS built as written — the export is what's wrong

The Pit Crew export records `performance.ballastPosition: 20`. The Rev A sheet
specified **109 kg at position 0**. You have confirmed the car is at **0 in game**.

**That matters twice over.**

- **It kills what would otherwise have been my headline diagnosis.** Rearward ballast
  is `02-gt7-setup-parameters.md` §8.1's textbook cause of *"over-rotation
  off-throttle and on corner entry… also worsens braking stability"* — a word-for-word
  match to your complaint. If I had not asked, I would have shipped you a sheet whose
  main change was moving a ballast slider that was already where I wanted it, and
  spent nothing on the actual problem. **F2 question 4 — "is the car built as
  written?" — earned its place again.**
- **It means the export's `performance` block is not reading the game.** Every other
  value in `setup.values` matches the Rev A race sheet exactly, all 22, plus the six
  gear ratios. The one block that is wrong is the one the app asks you to type by
  hand. Fix that field in Pit Crew before the next session, or it will mislead a
  future diagnosis in the same way — **and the failure is silent, because a wrong
  number looks exactly like a right one.**

So: **rear stability under braking has to be bought entirely from the A4 stack.**
There is no free build correction available. That is why §2 spends more on it than it
otherwise would.

## 1.2 You ran Racing Soft, not the Racing Medium on the sheet — and that was the better call

The sheet's race compound was flagged as *"a hedge, not a decision"* and §5.2 asked for
a six-lap **RM** stint. You ran **seven laps on RS**. I am not treating that as a
deviation to correct: it measured the compound you actually want to race, which is
strictly more useful than measuring the fallback. §5 turns it into the decision.

Log it, though: "Driver changes away from it: none recorded" is not quite true, and
next time a one-line note saves me guessing whether the tyre or the ballast is the
odd one out.

---

# 2. Diagnosis — each symptom, its cause, its corner phase, ranked by cost

## 2.1 The ranking

| Rank | Symptom | Corner phase | Cause | Est. cost |
|---|---|---|---|---|
| **1** | **Rear excited/sketchy under braking**; "heavy braking zones cost me most"; won't trust the brakes | **Braking + trail-brake** | Rear axle has insufficient decel-side authority with ABS Off. **LSD braking sensitivity is the entire toolkit** (A4) and 18 is not enough on this car. | **~3–4 s/lap of median**, and all of the 5.1 s spread |
| **2** | Loose on throttle exit — **both rears together, a snap** | **Early throttle + full exit** | **LSD acceleration too high** — A5's second failure mode, now diagnosed rather than guessed. Wheelspin flagged on **7 of 7 laps at 7 of 8 corners**. | ~0.5–1.0 s/lap, multiplied because it sits on the exits feeding two long straights |
| **3** | Gearbox too long | **Full exit + straight**, and inverted at the T6 apex | **6th gear is never used** (max speed 272.9 km/h in **5th**, limiter never reached in top). And the ratio spread forces **1st gear at T6** — apex *and* exit. | ~0.3–0.6 s/lap directly, plus it makes #2 materially worse |
| **4** | Mid-corner push at T6 (understeer-mid, 4 of 7 laps) | **Mid-corner, on throttle** | **Not a separate problem** — see §2.4 | folded into #2/#3 |

## 2.2 Rank 1 — where the telemetry and your report disagree, and which I trust

**They disagree, and it is worth being explicit.**

- **You say:** the rear is excited and sketchy under braking, and heavy braking zones
  are what costs you most.
- **The telemetry says:** `trail-brake-instability` fired on **1 lap of 7** at T6 and
  nowhere else — *below* the detector's own 2-lap threshold, so it isn't even raised as
  a flag. `countersteer` fired once at T6 and once at T7. On the face of it, the car
  is not measurably unstable under brake.

**I am trusting you, and here is the mechanism that reconciles them rather than
averaging them.**

The instability isn't showing up **because you are not going near it.** Peak brake at
T6 is **70.7%**. A no-ABS load-cell driver attacking a 5/5-severity braking circuit
lives at 90–100% with the front locking under him as the information channel. At 71%
you are braking early, braking soft, and leaving the rear alone — which is exactly
what a driver does when the rear has bitten him once. The detector cannot log an event
you are successfully avoiding. **A quiet telemetry channel and a frightened driver are
the same reading.**

Three things corroborate it rather than the flags:

1. **`brakePointM` at T6 is 111.3 m** — you are getting on the brakes early for an
   87 km/h apex from 142 km/h entry.
2. **`trailBrakeMs` at T6 is 823.8 ms** — you *are* trail braking, at length. So the
   technique is intact; it is the pressure that is missing. That is a confidence
   signature, not a technique one.
3. **Rear tyre temperature maxima spike to 157–169 °C** (RL lap 1 157.0, RL lap 6
   168.9, RR lap 7 161.7) against rear means of 83–88 °C. Those are lock/slide events
   on the rear axle. Mean rear temps also run **7.8 °C hotter than the fronts** and
   climb 0.82 °C/lap. The rear axle is doing more work than it should and occasionally
   letting go.

**The fix is A4, worked properly.** `08-playbook-leon.md` A4 is unambiguous: GT7 has no
engine-braking map, no brake pressure, no ducts, no preload in Nm — **LSD braking
sensitivity *is* your off-throttle and on-brake rear-stability toolkit.** The window
over an FR baseline of 10 is **+5 to +15**. Rev A took +8 (=18). That was the
conservative end of a proven window, chosen because you had never run this car near
that number and because the failure mode on the other side — *the car refuses to turn
in on the brakes* — is the worse one for a deep trail-braker.

**You did not report that failure mode.** Turn-in is not on your symptom list at all
this session, and `understeer-mid` fired only at T6 (4 laps) and T8 (2 laps), both of
which §2.4 attributes elsewhere. **That silence is what buys the room to go further.**

→ **LSD braking 18 → 22** (+12 over baseline, still inside A4's window).

## 2.3 Rank 2 — the exit snap, now diagnosed rather than guessed

You answered Rev A test #1: **"both rears went together — a snap."**

That is A5's second failure mode, verbatim, and it has exactly one direction:
**acceleration sensitivity is too high — lower it.** A heavily locked diff approaches a
spool and a spool axle breaks away as a unit. That is ordinary diff physics, not a GT7
anomaly, and it happens to sit directly on your non-negotiable #4 (progressive exit
traction).

This is the answer Rev A explicitly refused to guess at, and the reason it refused is
worth restating: the other side of A5's fork — *inside rear lights up alone, car bogs*
— points the opposite way, and a session spent moving the wrong direction is a session
spent making it worse. **One line of driver observation resolved it. §7's standing
exception applies: the symptom is diagnosed to a specific control, so the change
hierarchy no longer gets a vote — I do not go looking for a higher-ranked lever.**

Corroboration: `wheelspin` is flagged on **7 of 7 laps at T1, T2, T3, T4, T6, T7 and
T8** — every corner except T5. That is not a corner-specific traction problem, it is a
whole-car one, on a 606 bhp FR road car with TCS 0. And `throttleOnPct` sits at
**7–14% at six of the eight corners**, against 41–42% at T5 and T8. You are barely
opening the throttle anywhere. Same story as the brake pedal: the car is not being
used.

→ **LSD acceleration 20 → 17** (−3, one step past the 2-point minimum because the
diagnosis is now unambiguous and you have a practice session to walk it back in).

## 2.4 Rank 4 — the T6 push and the T6 snap are one problem wearing two faces

**T6, every lap: `gearMin 1`, `gearAtApex 1`, `gearAtExit 1`.** You are taking the
hairpin in **first gear**, at a 75.1 km/h apex and an 87.6 km/h exit.

At 87.6 km/h in 1st, on the current box, you are at roughly **5,700 rpm with a
9.41:1 overall reduction** — the largest torque multiplication the car owns, applied at
a rev point where the flat-plane V8 is making real power, through a diff locked at 20,
with TCS 0, on a rear axle that is already the hottest thing on the car.

That single fact produces **both** T6 flags:

- **`wheelspin` 7/7 laps** — the exit snap. Face one.
- **`understeer-mid` 4/7 laps** — the mid-corner push. Face two. It is *on throttle*
  (F2 question 1), and a locked diff being fed a 1st-gear torque spike while the wheel
  is still wound on is the Laguna signature exactly: **power-on push.** `08` A5.1.

It also produces **`kerb-strike` on 5 of 7 laps** — a car that spins up and pushes wide
at a hairpin ends up on the exit kerb — and the **1 shift per lap inside the corner**
that `shiftsInCorner: 1` records, which is a mid-corner destabilisation you do not need.

**So T6 is not four problems. It is one gear.** The gearbox change in §4 makes T6 a
**2nd-gear corner** — 25% less torque multiplication and ~750 rpm lower in the range —
and the accel-LSD change removes the lock that turns the remaining spike into a snap.
**Those two changes are coupled and I am saying so rather than shipping them silently:
if T6 is transformed after Rev B, I will not be able to tell you which one did it
unless you stage them.** §6 tells you how to stage them in ten minutes.

## 2.5 What is NOT one problem

**Braking instability and exit snap are on the same axle but they are not the same
problem, and they must not be treated as one.** GT7 splits them across two independent
sliders — `lsd_b` for the decel side, `lsd_a` for the drive side — and they move in
opposite directions here (braking **up**, acceleration **down**). A single "make the
rear more secure" instinct would have raised both and made the exit worse. This is the
one place where the rear-stability stack and the traction diagnosis genuinely diverge.

## 2.6 What the lap times actually say

Excluding lap 6 (2:12.408 — an obvious moment), your laps run:

```
  L1 1:54.823   ← fastest, on a FULL tank
  L2 1:58.940
  L3 1:59.246   ← 4 off-tracks
  L4 1:59.002   ← 1 off-track
  L5 1:59.883
  L7 2:00.107   ← 1 off-track
```

**Laps 2–7 are flat within 1.2 seconds.** The headline `degradationMsPerLap: 880.7` is
an artefact — it is a straight-line fit dominated by lap 1 at one end and the 2:12 at
the other, on raw times with fuel not netted off, and the export's own
`byLapTime.confidence` is **low** and its `phase` reads **flat**. Netting the ~52 L of
fuel burned (worth roughly 0.02 s/lap of *gain*) leaves genuine tyre degradation at
**under 0.1 s/lap.** Do not let the 880 ms number reach a strategy decision — it would
have told you to pit, and it is wrong.

**The real signal: 6 off-track excursions in 7 laps, and a 5,081 ms spread.** That is
not a car falling off. That is a driver who has no idea what the rear is going to do
next.

---

# 3. The revised race sheet

```
                                        RACE                    QUALIFYING
─────────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Soft ✅ MEASURED  Racing Soft
  Rear compound             Racing Soft ✅ MEASURED  Racing Soft
                            No longer a hedge — §5.1 decides it on measured wear

SUSPENSION
  Body height      Front    80 mm  · +5  ·  5.9%   78 mm  · +3  ·  3.5%
                   Rear     98 mm  · +3  ·  3.5%   97 mm  · +2  ·  2.4%
  Anti-roll bar    Front    5                      6
                   Rear     4                      5
  Damping compr.   Front    24     · +4  · 20.0%   25     · +5  · 25.0%
                   Rear     28     · +8  · 40.0%   30     · +10 · 50.0%
  Damping expan.   Front    40     · +10 · 50.0%   41     · +11 · 55.0%
                   Rear     34     · +4  · 20.0%   36     · +6  · 30.0%
  Natural freq.    Front    3.05 Hz · +117 · 64.3% 3.20 Hz · +132 · 72.5%
                   Rear     3.20 Hz · +120 · 63.2% 3.35 Hz · +135 · 71.1%
  Camber angle     Front    1.4°   · +14 · 23.3%   1.6°   · +16 · 26.7%
                   Rear     1.0°   · +10 · 16.7%   1.2°   · +12 · 20.0%
  Toe angle        Front    −0.05° · +95 · 47.5%   −0.05° · +95 · 47.5%
                   Rear     +0.10° · +110 · 55.0%  +0.08° · +108 · 54.0%

DIFFERENTIAL
  Initial torque            5      · +0  ·  0.0%   5      · +0  ·  0.0%
  Acceleration sens.        17 ◄── · +12 · 21.8%   19 ◄── · +14 · 25.5%
  Braking sens.             22 ◄── · +17 · 30.9%   20 ◄── · +15 · 27.3%
  [AWD]                     n/a — FR                n/a — FR

AERODYNAMICS
  Downforce        Front    150    · +90 · 90.0%   160    · +100 · 100.0%
                   Rear     260    · +110 · 73.3%  275    · +125 · 83.3%
                            total 410 · 36.6% F     total 435 · 36.8% F

TRANSMISSION
  Max speed setting         300 km/h ◄── GENERATOR ONLY. Set FIRST, then never again.
  Final gear                3.600  · 53.3%          3.700  · 56.7%
  1st                       2.614                   2.614   (unchanged)
  2nd                       1.948 ◄──               1.948 ◄──
  3rd                       1.560 ◄──               1.560 ◄──
  4th                       1.318 ◄──               1.318 ◄──
  5th                       1.145 ◄──               1.145 ◄──
  6th                       1.019 ◄──               1.019 ◄──

BRAKES
  Brake balance             0  (− front / + rear)   0

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)             100%
  ECU output                100%                    100%
  Ballast / position        109 kg / 0              109 kg / 0
                            ⚠️ Confirm on screen. The export says +20; the car says 0.

ASSISTS (not on the GT7 sheet — set in the menu)
  ABS                       Off                     Off
  TCS                       1 ◄── race only          0
  Countersteer assist       Off                     Off
═══════════════════════════════════════════════════════════════════
```

**Step sizes assumed:** ride height 1 mm, natural frequency 0.01 Hz, camber 0.1°, toe
0.01°, downforce 1 point, LSD 1, final gear 0.001, individual ratios 0.001.
**If any click count disagrees with what you see on screen, the percentage is the
authority.**

---

# 4. Gearing — rebuilt on a measured constant, not an estimate

## 4.1 ✅ K is now measured. Rev A's estimate was 6.4% low.

Rev A guessed the gearing constant from a real-world redline and a tyre size, flagged
it, and warned it would probably be wrong in an unknown direction. It was.

```
  From the export, one clean data point:
    maxSpeedKph 272.9  ·  maxSpeedGear 5 (ratio 1.010)  ·  maxSpeedRpm 7,978
    final gear as run 3.600  ·  limiterRpm 8,856 (observed at the limiter, gear 1)

  Effective rolling circumference
    = 272.9 × 1.010 × 3.600 ÷ (7,978 × 0.06)          = 2.073 m

  K  = limiter_rpm × circumference × 0.06
     = 8,856 × 2.073 × 0.06                            = 1,101      ✅ MEASURED
                                                          (Rev A assumed 1,035)

  v_at_limiter (km/h) = 1,101 ÷ (ratio × final gear)
```

Confidence: **measured, ±2%.** It rests on one telemetry point rather than a
hand-noted trio, and `limiterRpm` is tagged `observed-at-rev-limiter` so it is a real
limiter strike, not a highest-rpm-seen. The design below is deliberately insensitive to
a 2% error in either direction — check §4.4.

**This goes in the knowledge base.** It closes the same item the RSR closed at Monza,
and every Shelby gearbox from here is exact rather than iterated.

## 4.2 What the old box was actually doing

| Gear | Ratio | Tops out at | What actually happened |
|---|---|---|---|
| 1st | 2.614 | 117 km/h | **Used at T6 apex AND exit, every lap.** §2.4 |
| 2nd | 1.797 | 170 km/h | T7 only |
| 3rd | 1.400 | 218 km/h | T1, T5, T8 |
| 4th | 1.155 | 265 km/h | T2 |
| 5th | 1.010 | 303 km/h | T3, T4 — **and the end of the back straight, at 272.9 km/h** |
| 6th | 0.921 | **332 km/h** | ⚠️ **Never used. Not once, in seven laps.** |

`topGearReachedLimiter: false`, `maxSpeedGear: 5`. **Your complaint is literally
correct and the telemetry states it flatly: you are racing a five-speed with a dead
ratio bolted on the end.** Rev A geared 6th for a tow to ~312 km/h on a K that was 6.4%
low; on the real K it tops at 332, and you reach 273.

**And the cost is not just the wasted ratio.** Six gears spread to 332 km/h on a car
that reaches 273 means every step below is stretched too — which is why 2nd is too
long to be usable at a 75 km/h hairpin and you drop to 1st, and 1st is far too short
for the job. **That is the whole of §2.4.**

## 4.3 The new box

Same final drive (3.600). Same 1st gear. **The five gears above it are re-spaced so the
box spans what the car actually does.**

| Gear | Ratio | Tops at (limiter) | At peak power ≈7,900 rpm | The job it does |
|---|---|---|---|---|
| 1st | 2.614 | 117 km/h | 104 | Grid start only — unchanged |
| **2nd** | **1.948** | **157 km/h** | 140 | **T6 apex and exit (4,230 → 4,940 rpm), and T7 to its exit.** The corner this box was rebuilt for. |
| 3rd | 1.560 | 196 km/h | 175 | T5, T8, T1 entry |
| 4th | 1.318 | 232 km/h | 207 | T2, T1 exit |
| 5th | 1.145 | 267 km/h | 238 | T3, T4 |
| **6th** | **1.019** | **300 km/h** | 268 | **The back straight. ~8,200 rpm at 278 km/h in clean air, limiter only in a tow.** |

Speed steps: **+40, +39, +36, +35, +33 km/h** — diminishing increments, per A6 step 5.

**Corner-by-corner check against the actual telemetry speeds:**

| Corner | Min → exit (km/h) | Old gear | New gear | New rpm at apex |
|---|---|---|---|---|
| T1 | 174.5 → 182.5 | 3 | 3, upshift 4 on exit | 7,880 |
| T2 | 196.1 → 205.9 | 4 | 4 | 7,480 |
| T3 | 238.4 → 242.5 | 5 | 5 | 7,910 |
| T4 | 225.9 → 229.5 | 5 | 5 | 7,490 |
| T5 | 163.7 → 165.9 | 3 | 3 | 7,400 |
| **T6** | **75.1 → 87.6** | **1** | **2** ✅ | **4,230 → 4,940** |
| T7 | 113.4 → 161.0 | 2→3 | 2→3 | 6,370 |
| T8 | 140.9 → 147.0 | 3 | 3 | 6,370 |

**T6 is the point of the exercise.** Overall reduction at the exit drops from **9.41:1
to 7.01:1 — 25% less torque at the contact patch — and ~750 rpm lower in the range.**
On a 606 bhp car with TCS 0 that is worth more than any diff number, which is precisely
A6's claim: *lengthening the effective gear you use out of a slow corner is the
#1-ranked fix for exit traction in GT7, ahead of every LSD and suspension change.*

**The honest cost:** T7's apex moves from ~5,880 to ~6,370 rpm and T8's from ~5,710 to
~6,370, i.e. roughly 8–11% more wheel torque at those two exits. Both already show
wheelspin on 7/7 laps. **The accel-LSD drop to 17 and TCS 1 are what pay for that**,
and it is a good trade because T6 is far the worse offender and it is the corner that
sets up the shorter of the two straights.

## 4.4 Robustness to a wrong K

If K is really 1,075 (−2.4%), 6th tops at 293 and you sit at ~8,400 rpm at 278 km/h.
If it is 1,130 (+2.6%), 6th tops at 308 and you sit at ~7,990 rpm. **Both are usable
top gears, and neither hits the limiter in clean air.** The design does not depend on
K being exactly right — that is deliberate.

## 4.5 The order you set it in

1. **Maximum Speed → 300 km/h. FIRST.** It is a *generator*, not a trim. Touching it
   afterwards wipes every ratio. I have dropped it from 330 to 300 so the generated set
   starts near the target and the individual sliders have room to reach these numbers.
2. **Final gear → 3.600** (race) / **3.700** (quali).
3. **Individual ratios**, 1st → 6th, as tabled.
4. **Never touch Maximum Speed again.**

> ⚠️ **If a ratio slider will not reach its target**, drop Maximum Speed another
> 10 km/h and re-enter **all six**. Do not part-set them — a half-generated box is
> worse than either.

## 4.6 What to report back

**Which gear you are in at the T6 apex.** If it is still 1st, tell me and I will
shorten 2nd again. That one answer verifies the entire section.

---

# 5. Strategy — now on measured numbers

## 5.1 ✅ Race on Racing Soft. This is decided, not hedged.

```
  Measured: 18% front / 13% rear consumed at lap 7, RS, at the 2× race multiplier
  Wear per lap                                        2.571%   ✅ MEASURED
  Race distance ≈ 16 laps  →  16 × 2.571%           = 41.1% at the flag
  Fall-off cliff (C3)                                 ~50%
  Laps to the cliff                                   ~19.5
  Degradation actually observed, laps 2–7             < 0.1 s/lap  (flat)
```

**RS covers the race with about 3.5 laps of margin and essentially no fall-off.** Rev A
put RM on the sheet as an explicit hedge and said §5.2 would decide it. §5.2 has
decided it: **the hedge costs you time you do not need to spend.** This is the third
consecutive time this knowledge base has modelled wear pessimistically and been
corrected by one measurement (Laguna 1.8×, Monza ~5×, now Yas Marina) — `08` C3.1's
standing rule keeps paying for itself.

**Two findings to log:**

1. **The front axle is the limiting one here — 18% vs 13% — not the rear.**
   `05-track-reference.md` classifies Yas Marina as wearing **"Rear (traction)."** On
   this car it does not. That has a direct consequence in §5.4.
2. **`08` C4 warns road cars are disproportionately punished post-1.49.** At
   2.571%/lap at 2× on the *softest* compound, this car is not. **First road-car wear
   datum in the knowledge base, and it does not support the warning.**

## 5.2 ⚠️ Fuel is the binding constraint, and it is tight

```
  Measured fuel                                      7.563 L/lap at 2×   ✅ MEASURED
  Measured tank                                      100 L               ✅ MEASURED
                                                     (Rev A assumed 60 L — 40% wrong)
  Race length          1800 s ÷ ~1:57                ≈ 15.4  →  16 laps completed

  Raw requirement      16 × 7.563                    = 121.0 L
  Shorter gearbox, +2–4% at partial throttle         ≈ 124  L   [ESTIMATE]
  Tank                                               = 100  L
  ──────────────────────────────────────────────────────────────
  Saving required                                    ≈ 19–20%
  Short-shifting alone (C3: −20%, ~−0.5 s/lap)       ≈ 99 L   — fits by ~1 L
```

**That is too tight to leave to chance, so treat the saving as mandatory from lap 1,
not as a late-race rescue.**

Note what does *not* break it: the gearbox change costs 2–4%, but you were 17% short
**before** it. At the end of the straight you go from 7,978 rpm in 5th to ~8,200 in
6th — a 2.9% rpm rise at wide-open throttle, where nearly all the fuel goes. **The
gearing is not the reason the fuel doesn't fit. 7.563 L/lap into a 100 L tank is.**

**The plan:**

- **Short-shift from lap 1.** Not a compromise here — it is a **quadruple** win: it
  saves the fuel, it cuts rear tyre wear, it reduces the torque spike that produces
  your exit snap, and the new shorter box makes short-shifting land you in a gear that
  still pulls. Every argument points the same way.
- **Fuel map 1 by default. Map 4–6 whenever you are in a tow** on either straight —
  close to free.
- **Map 1 when attacking, defending, or on the last lap.**
- **The lap-5 gate, run it in the car:** if you have used **more than 31 L after 5
  laps**, you will not make 16 on this tank. Take one more map step immediately, or
  commit to the splash.

**Splash fallback:** window **laps 11–13**, take only what you need.

```
  Pit loss  19% of a lap × ~117 s          ≈ 22.4 s
  Refuel ~22 L at 2 L/s                    ≈ 11.0 s
  ─────────────────────────────────────────────────
  Total                                    ≈ 33 s
  vs short-shifting 0.5 s/lap × 16         ≈  8 s
```

**No-stop wins by roughly 25 seconds** — the same call as Rev A, now on measured
numbers instead of estimates. There are 0 mandatory stops, so nothing forces your hand.

## 5.3 The pit-loss discrepancy is resolved

Rev A flagged that the declared 20 s and the reference's 19%-of-a-lap could not both be
true. On a measured ~1:57–1:59 lap, **19% = 22.2–22.6 s**, and 20 s would imply a
1:45 lap that is faster than the Gr.3 record here. **Use 22 s.** The 20 s was the app
default. Still worth measuring properly on an out-lap when you have a spare one.

## 5.4 In-race brake balance and TCS

`02` §7.4's standard migration says move brake balance **forward** as the rears go
off — **but on this car at this circuit the fronts go off first (18% vs 13%), so that
rule is inverted here.** Which is convenient, because rear bias is what you actually
want.

| Laps | Brake balance | TCS | Why |
|---|---|---|---|
| **1–5** (full tank) | **0** | **1** | Full fuel sits the car down; the rear is as planted as it will be. Learn the new brake feel before touching anything. |
| **6–11** | **0** | **1** | Fuel coming off the back increases entry rotation. If LSD braking 22 has done its job you should not need to move. |
| **12–16** (light, worn fronts) | **+1 — take it if it's there** | **1**, or **0** if TCS is audibly cutting you on exit | Fronts are the limiting axle, so shifting work rearward is now supported by the wear data as well as your preference. |

> **The +1 in the last phase is the prize.** If you finish this race at **+1 on worn
> tyres with ABS Off at a 5/5-braking circuit in a 1,335 kg car**, that is the
> strongest evidence the A4 stack has ever had — harder than Laguna, harder than Monza.
> Tell me if you get there.

**−1 remains the emergency response to a single genuine lock. It is not a setup
solution and it is not where this sheet starts.**

## 5.5 Why TCS 1 for the race

`08` B1's default is **TCS 0 for quali, 1 for race**, and Rev A deliberately overrode it
to keep the diff diagnosis clean. **That diagnosis is now made** — you answered test #1 —
so the reason for the override is gone.

TCS 1 costs near-nothing, catches the worst exits, and your stated revision priority is
**drivability**. It is insurance for cold tyres on lap 1, for traffic, and for the two
exits (T7, T8) where §4.3 admits the new gearbox asks slightly more of the rear.

**But run practice at TCS 0**, so §6's staging tells you what the diff and gearbox
actually did. If you need TCS 3+ at any point, the diff or the gearing is wrong and I
want to hear about it.

---

# 6. What each change should feel like — one run each

**Ten minutes of practice, staged in this order.** This ordering exists so that if
something goes backwards you know which change did it.

### Run 1 — the gearbox alone (TCS 0, diff untouched at 20/18)

**Where:** the T6 hairpin, apex to exit. And the end of the back straight.
**Should feel like:** T6 becomes a **2nd-gear corner you can feed throttle into**
rather than a 1st-gear corner you have to feather. Less snap, less push, no mid-corner
downshift. On the straight, you should now **upshift into 6th at ~267 km/h and keep
pulling** instead of running out of road in 5th.
**Working:** you can get on the power earlier at T6 without a correction, and you are
not clipping the exit kerb every lap.
**Not working:** if 2nd feels lazy or bogged at the T6 apex, tell me — I shorten 2nd a
click. If you still instinctively drop to 1st, that is the same answer.
**Report:** the gear you are in at the T6 apex.

### Run 2 — LSD acceleration 20 → 17

**Where:** T6 exit, T7 exit, T8.
**Should feel like:** the rear **goes progressively** instead of both wheels letting go
together. If it steps, it should step in a way you can catch and drive through, not one
that arrives all at once. This is your non-negotiable #4 — progressive exit traction —
and it is what 17 buys.
**Cost you should accept:** slightly more rotation on power. That is not a fault.
**Too far — the other side of A5's fork:** the **inside rear lights up alone** and the
car **bogs** out of T6 while the inner wheel spins. That means 17 is too low: go to 19.
Watch the on-screen tyre indicators; do not guess.

### Run 3 — LSD braking 18 → 22 ⭐ the one that matters

**Where:** the T6 stop, from initial application through the trail phase to the apex.
**Should feel like:** the rear **stays behind you** as you bleed the brake into
steering. The single thing I want you to test is whether you can push the pedal
*harder* — you are at 70.7% peak and there is a third of a pedal on the table.
**Working:** you brake later, harder, and stop thinking about the rear. The lap-time
signature is the **median coming toward the 1:54.8, not the 1:54.8 getting faster.**
**Too far — and this is the failure mode that matters for a trail-braker:** the car
**refuses to turn in on the brakes.** It feels safe and lazy, the nose will not come
round while you are still on the pedal. **Back to 20, then 18.** Stop the instant
turn-in dulls.

> **If you only have time for one run, make it this one**, at 22, and put the gearbox
> and the diff in together and unpicked. Rank 1 is the one costing you seconds.

### The compound and TCS (no run needed)

RS is decided on measured wear. TCS 1 goes on for the race, not for practice.

---

# 7. What I deliberately left alone, and why

**Ten parameters moved on Rev A. Three move on Rev B. Here is why the rest didn't.**

| Left alone | At | Why |
|---|---|---|
| **Ride height** | 80 / 98 mm | No bump, kerb or "won't steer" complaint from you, and the data agrees: minimum suspension heights at the worst corner sit **13–16 mm above** the session's own bottoming reference. A7 says raise ride height first for kerb problems — **you do not have one.** ⚠️ *Correction to Rev A §7.2 item 3, which said raising the rear to 101 mm "reduces rake further." It does the opposite — rake is rear minus front, so raising the rear increases it. If rake ever needs to come out, it comes out at the front.* |
| **Natural frequency** | 3.05 / 3.20 Hz | No bounce, no repeated oscillation, no grip loss over surfaces reported. `01` §11 records repeatedly that **stiffening this car costs grip and worsens throttle exit** — and softening it is not indicated by anything in this session. |
| **ARB** | 5 / 4 | The only mid-corner push in the data is T6, and §2.4 attributes it to a gear and a diff. **Softening the front ARB to "fix" a power-on push is the exact trap `08` A5.1 records as avoided at Laguna** — it masks the cause while giving up roll control. |
| **Damper compression** | 24 / 28 | Front 24 is your turn-in tool and **turn-in is not a complaint this session.** A4 #4's tension says front compression *up* is a rear-stability lever — it is last in the stack precisely because it takes your bite back. Not while there is room in `lsd_b`. |
| **Damper expansion** | 40 / 34 | Rear 34 is **A4 #2 and the first thing I reach for if 22 is not enough** — held as test #1 in §8, not shipped, so it stays a clean single change. |
| **Camber** | 1.4 / 1.0 | A1: GT7 over-taxes camber against **longitudinal** grip — braking and traction — which are your two complaints. There is now measured wear headroom that would normally re-open camber upward (A1's caution), **but not on a session where braking confidence is the problem.** Deferred, not forgotten. |
| **Toe** | −0.05 / +0.10 | Front toe direction on this car has still never been A/B'd, and A3 says GT7's behaviour here is **genuinely disputed and possibly inverted**. Moving it blind on a race sheet would poison every reading. Rear toe +0.10 is A4 #3 and available as a fallback, but it costs top speed on two long straights in a fuel-critical race. |
| **Downforce** | 150 / 260 | No high-speed instability reported and none in the data — T2/T3/T4 are clean but for wheelspin. Rear downforce would add braking stability, but it costs drag in a race you may not have the fuel for. **10 points of front headroom deliberately retained**, as Rev A left it. |
| **Brake balance** | 0 | The entire point of the A4 stack. `01` §16: *mechanical rear stability first, then brake balance around neutral as a fine adjustment.* If Rev B works you should end the race at **+1**, not −1. |
| **LSD initial torque** | 5 | At minimum, deliberately. Preload is the only diff parameter that cannot be aimed at a corner phase — it opposes turn-in everywhere at once. Rear stability comes from **braking sensitivity**, which is phase-specific. Raise it to 8 only if the car feels *vague* on turn-in transition, which you have not reported. |
| **Ballast** | 109 kg @ 0 | Correct as built. §1.1. Sweeping it is queued behind three diagnosed changes. |
| **Power / restrictor / ECU** | 606 bhp, 100 / 100 | The regs cap bhp and minimum weight, not PP. There is no trade to make and `08` D3.1's restricted-build rules do not apply to you here. |

---

# 8. Three things to try next, in order, if Rev B is still not right

## ⭐ 1. Rear expansion damping 34 → 32 — if the rear is still loose under brake

**A4 #2, and the next rung of the stack.** A rear that extends too fast on lift unloads
abruptly; slowing that rebound keeps load on the rear tyres through the trail phase. It
is **free** — it costs nothing on any other axis and does not touch the front.

You have four clicks of floor left (30 is the minimum). Take **32** first, and **30**
only if 32 clearly helped and you want more.

**Do this before you consider going past LSD braking 22.** If 22 has already started to
dull turn-in, this is the lever that adds rear support without taking any more front.

## 2. Walk LSD braking to 24, in one 2-point step

Only if **both** 22 and rear expansion 32 are in and the rear is still stepping under
trail braking. 24 is **+14 over the FR baseline of 10 — near the top of A4's +5 to +15
window**, so this is the end of the road on that axis, not a waypoint.

**Stop the instant turn-in dulls on the brakes.** That boundary is the whole tuning
axis, and past it you have traded your best weapon for stability you can get elsewhere.

If 24 is not enough before turn-in goes, the stack continues in A4 order:

1. **Rear toe +0.10 → +0.12** — costs top speed on two long straights and rear tyre
   life. Third, not first.
2. **Rear expansion 32 → 30** — the floor.
3. **Front compression 24 → 26** — **last**, because it is the one that takes your
   turn-in back (A4 #4).

**Brake balance forward is still not on this list.**

## 3. Re-check the exit at T7 and T8 specifically, at TCS 0

§4.3 is honest that the new box asks **8–11% more wheel torque** at the T7 and T8
apexes than the old one did, in exchange for fixing T6 properly. Both already showed
wheelspin on 7/7 laps.

**Ask F2 question 2 — which exits are FINE?** If T6 is transformed and T7/T8 have got
worse, that is a *localised* answer, not a global one, and it points to:

- **LSD acceleration 17 → 15** if it is still snapping at those two only, **or**
- **3rd gear lengthened** (1.560 → 1.510) so T8 sits ~200 rpm lower, leaving 2nd and
  T6 alone.

**Do not reach for front grip or front aero for a push at these corners.** That is the
Laguna trap and it is recorded in `08` A5.1 as the mistake that was avoided by asking
where the right foot was.

## And the fourth, if the first three land

**Front toe A/B: −0.05 / 0.00 / +0.05**, three clean laps each, Data Logger on. It has
been the top open item in `08` Part G since 10 August, it sits directly on your #1
long-term priority, and it is 20 minutes. **It is now cleaner to run than it has ever
been on this car** — the diff confound is diagnosed and the gearbox is measured.

---

# 9. Delta table

| Parameter | As run | Revised | Why |
|---|---|---|---|
| **LSD braking sensitivity** | 18 | **22** | Rank-1 symptom. A4: braking sensitivity **is** the entire on-brake rear-stability toolkit in GT7. 18 = +8 over the FR baseline of 10; 22 = +12, still inside A4's proven +5 to +15 window. **Turn-in is not a complaint this session, which is what buys the room.** §2.2 |
| **LSD acceleration sensitivity** | 20 | **17** | Rank-2 symptom, now **diagnosed**: you saw *both rears go together — a snap*, which is A5's second failure mode and has exactly one direction. A heavily locked diff breaks away as a unit. §2.3 |
| **Gear ratio 2nd** | 1.797 | **1.948** | Makes T6 a 2nd-gear corner. Overall reduction at the exit falls from 9.41:1 to 7.01:1 — **25% less torque at the contact patch, ~750 rpm lower.** A6: the #1-ranked exit-traction fix in GT7. §2.4, §4.3 |
| **Gear ratio 3rd** | 1.400 | **1.560** | Spacing consequence of 2nd and 6th. Keeps T5/T8/T1 in 3rd at peak power. |
| **Gear ratio 4th** | 1.155 | **1.318** | Spacing. Keeps T2 in 4th at ~7,480 rpm. |
| **Gear ratio 5th** | 1.010 | **1.145** | Spacing. Tops at 267 km/h so you now **upshift into 6th before the end of the straight.** |
| **Gear ratio 6th** | 0.921 | **1.019** | **6th was never used in seven laps** — max speed 272.9 km/h was set in **5th**. Now tops at 300 km/h: ~8,200 rpm at 278 in clean air, limiter only in a tow. §4.2 |
| **Maximum speed setting** | 330 km/h | **300 km/h** | Generator only. Lowered so the individual ratio sliders can reach the values above. **Set first, then never again.** §4.5 |
| **Front compound (race)** | RM (hedge) | **Racing Soft** | ✅ Measured: 2.571%/lap at 2× → 41% consumed at the flag, degradation flat at <0.1 s/lap. The hedge is unnecessary and costs real time. §5.1 |
| **Rear compound (race)** | RM (hedge) | **Racing Soft** | As above. |
| **TCS** | 0 | **1 — race only** | `08` B1's race default. Rev A overrode it to keep the diff diagnosis clean; that diagnosis is now made, and drivability is the stated priority. **Practice still runs at 0.** §5.5 |
| Ballast position | 0 (export said +20) | **0** | ⚠️ No change — the sheet was always 0 and the car is at 0. **The export is wrong.** §1.1 |
| Final gear | 3.600 | 3.600 | Unchanged. The re-spacing is done in the ratios so the whole box shifts without moving the drive. |
| 1st gear | 2.614 | 2.614 | Unchanged. A start gear, and nothing in the data uses it anywhere else once T6 moves to 2nd. |
| *Everything else* | — | *unchanged* | §7 |

---

# 10. Qualifying sheet — reissued, and here is why

**Yes, the diagnosis moves it.** Three of the four Rev B changes are car-level, not
race-specific:

- **Gear ratios** — identical set, final gear stays **3.700**. Limiter speeds become
  114 / 153 / 191 / 226 / 260 / 292 km/h. 2nd still covers T6 and T7; 6th still tops
  out above a clean-air lap, at ~8,430 rpm at 278 km/h with no tow to lean on. The old
  quali box had the same dead top gear as the race box.
- **LSD acceleration 22 → 19.** The snap diagnosis is a property of the car, not the
  session. Quali stays 2 above race, as before — one lap, fresh Softs, no stint to
  protect, and a shade more lock is affordable on green rubber.
- **LSD braking 16 → 20.** Same reasoning as the race sheet, held 2 below it: one lap,
  no worn rears, no fuel transition, so the entry-stability tax is smaller and the
  turn-in is worth more.
- **TCS stays 0** for qualifying, per B1.

**Everything else in the quali column is unchanged from Rev A** — it was a sharper
version of the same car and the diagnosis does not disturb that relationship.

> ⚠️ **But note: this event is a grid start with no qualifying session.** The quali
> column is here for time trial, for a future round at this circuit, and so the two
> sheets do not drift apart. **It is not something you need to enter today.**

---

# 11. Range check

Every changed value against the ranges read off this car on 13 Aug 2026.

| Parameter | Range | Race | Quali | Margin |
|---|---|---|---|---|
| LSD acceleration | 5 – 60 | **17** | **19** | ✅ 12 above min |
| LSD braking | 5 – 60 | **22** | **20** | ✅ 17 above min, 38 below max |
| Max speed | 200 – 800 km/h | **300** | **300** | ✅ generator only |
| Final gear | 2.000 – 5.000 | 3.600 | 3.700 | ✅ |
| LSD initial | 5 – 60 | 5 | 5 | ⚠️ **AT MINIMUM — deliberate, §7** |
| Downforce F | 60 – 160 | 150 | **160** | ⚠️ **QUALI AT MAXIMUM — deliberate, unchanged from Rev A** |

All unchanged parameters were range-checked on Rev A and none has moved.
**Nothing was clamped.** The two values at a hard limit are both carried over
deliberately and both are justified in §7.

**Individual gear ratios are the one thing I cannot range-check**, because GT7's
per-gear slider limits are not in the register and they shift with the Maximum Speed
setting. That is why §4.5 sets Maximum Speed to 300 first, and why it tells you what to
do if a slider will not reach.

---

# 12. Pit Crew paste blocks

**One block per sheet. Paste them one at a time into the Event screen. Race first.**
A clean paste reads **"22 of 23 settings, 6 gears"** with nothing unrecognised — 22
because `awd` is correctly omitted on a two-wheel-drive car.

## 12.1 RACE

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Yas Marina Circuit (Full Course)",
    "sessionType": "race",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Off", "tcs": 1, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Yas Marina race v2",
    "values": {
      "rh_f": 80, "rh_r": 98,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 4,
      "dc_f": 24, "dc_r": 28,
      "de_f": 40, "de_r": 34,
      "cam_f": 1.4, "cam_r": 1.0,
      "toe_f": -0.05, "toe_r": 0.10,
      "lsd_i": 5, "lsd_a": 17, "lsd_b": 22,
      "df_f": 150, "df_r": 260,
      "bb": 0,
      "top": 300, "fg": 3.600
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

## 12.2 QUALIFYING

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Yas Marina Circuit (Full Course)",
    "sessionType": "qualifying",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Off", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Yas Marina quali v2",
    "values": {
      "rh_f": 78, "rh_r": 97,
      "nf_f": 3.20, "nf_r": 3.35,
      "arb_f": 6, "arb_r": 5,
      "dc_f": 25, "dc_r": 30,
      "de_f": 41, "de_r": 36,
      "cam_f": 1.6, "cam_r": 1.2,
      "toe_f": -0.05, "toe_r": 0.08,
      "lsd_i": 5, "lsd_a": 19, "lsd_b": 20,
      "df_f": 160, "df_r": 275,
      "bb": 0,
      "top": 300, "fg": 3.700
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

## 12.3 ⚠️ What the paste block does NOT carry — enter these by hand

The parser reads **`sheetName`, `values` and `gears`. That is all.** Enter by hand on
the Event screen:

- **Compounds** — **Racing Soft** both sheets now
- **Assists** — ABS **Off**, TCS **1 for the race / 0 for practice and quali**,
  countersteer Off
- **Multipliers** — 2× tyre, 2× fuel
- **Performance adjustment** — restrictor 100%, ECU 100%, **ballast 109 kg at
  position 0**. ⚠️ **This is the field the export got wrong. Check it on screen and fix
  it in the app.**
- **Event** — 30 min timed, grid start, dry, **night**, 0 mandatory stops
- **Pit loss — set it to 22 s**, not the 20 s default (§5.3)

---

# 13. What to record in the knowledge base

Per `00-INDEX.md` standing rule 6, with a date and a game version. **This session
produced five measured values and one methodology failure, which is a good return on
seven laps.**

1. ✅ **Gearing constant K = 1,101 for the Shelby GT350R '16**, GT7 v1.70, derived from
   telemetry (272.9 km/h / 7,978 rpm / 5th / fg 3.600) with `limiterRpm` 8,856 observed
   at the limiter. Rolling circumference 2.073 m. **Rev A's estimate of 1,035 was 6.4%
   low** — the second time an assumed limiter has produced a systematically optimistic
   gearbox (Monza was 2.9% the other way). `08` G-adjacent.
2. ✅ **Tyre wear: Racing Soft, 2×, Yas Marina, road car = 2.571%/lap**, 18% F / 13% R
   at lap 7, degradation flat at <0.1 s/lap over laps 2–7. **First road-car wear datum
   in the knowledge base.** It does **not** support `08` C4's warning that road cars are
   disproportionately punished post-1.49. `08` G2.
3. ✅ **Yas Marina wears the FRONT on this car**, 18% vs 13% — contradicting
   `05-track-reference.md` §1.25's "Rear (traction)" classification. `08` G4-equivalent,
   and it inverts the standard in-race brake-balance migration (§5.4).
4. ✅ **Fuel: 7.563 L/lap at 2×, tank 100 L.** Rev A assumed 60 L and ~4.5 L/lap — the
   tank was **40% wrong** and the consumption **68% low**. The power-and-throttle-share
   scaling method that worked at Monza did **not** transfer to a road car. `08` G3, G9.
5. ✅ **Pit loss ≈ 22 s** at Yas Marina, from 19% of a measured lap. The 20 s on the
   brief was the app default. `08` G10.
6. ✅ **A5 failure mode on this car: both rears together, a snap** — accel 20 was too
   high on an *unrestricted* 606 bhp FR build. Note this is the **opposite build** to
   the Laguna case (restricted MR) and arrives at the same direction: **start accel low
   and prove you need more.** Two independent cases now.
7. ⚠️ **Methodology finding: the Pit Crew export's `performance` block does not read
   the game.** It reported ballast position +20 against an actual 0 and would have
   produced a wrong headline diagnosis. **Silent, and it looks exactly like a correct
   value.** Worth a fix in the app before the next session.
8. ⚠️ **Correction to Rev A §7.2 item 3:** raising rear ride height *increases* rake, it
   does not reduce it. If rake needs to come out of this car, it comes out at the front.

---

*Rev B issued 13 Aug 2026 · GT7 v1.70 · no BoP · ranges verified on this car 13 Aug 2026*
*Three changes, each mapped to one named symptom. Everything else held — §7.*
*Race compound is now decided on measured wear, not hedged. Gearing is now built on a measured K.*
*Driver profile: front-end-led precision attacker · neutral brake bias · low tolerance for rear snap · ABS Off*
