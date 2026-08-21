═══════════════════════════════════════════════════════════════════
  PORSCHE 911 RSR (991) '17  ·  AUTODROMO NAZIONALE MONZA
  **TEAM MATE SHEET — RACE ONLY**
  Aggressive controller driver · TCS 0 · ABS Weak · countersteer off
  50 min · timed · 8× tyre / 3× fuel · 0 mandatory stops · refuel 1 L/s
  Issued 17 Aug 2026 · GT7 v1.70 · derived from `2026-08-12-rsr-monza-revB.md`
═══════════════════════════════════════════════════════════════════

# 0. The headline

**Five changes from your Rev B race sheet. Four of them are about one thing: making the
rear axle break away slowly instead of suddenly, because he has a slower correction
channel than you do and a bigger throttle input.**

The temptation with an aggressive driver is to build a softer, safer car. That is the
wrong instinct here and it is explicitly not what you asked for. He is the same pace as
you with the same error rate, and he catches slides better than you do — so the job is
not to remove the slide. It is to make the slide **arrive with notice** and **end where he
puts it**, and to stop the car spending his tyres and his exits on wheelspin he cannot
meter out on a trigger.

**What is NOT changing, and this is deliberate:** the platform (ride height, natural
frequency, ARBs, dampers), the front end (toe, camber, front downforce), the aero, and
the top three gears. Your Rev B measurements bought those values and a different driver
does not invalidate a measurement.

> ### ⛔ Two things to establish before he drives this
>
> **1. Has Rev B actually been raced?** The knowledge base has no Monza result. Rev B's
> three changes — NF 3.35/3.50 → 3.05/3.20, LSD accel 16 → 14, and the one-stop
> strategy — are **issued but unvalidated**. This sheet inherits all three and adds to
> them. If you have not run them, he is testing your revision and his own at the same
> time, and neither of you will know which is which. **If Rev B is untested, have him run
> three laps on your Rev B sheet exactly as written before applying §1.**
>
> **2. Standing rule 9 — confirm what is physically in his car.** One line before any
> diagnosis: *"the sheet in the car is Monza team-mate v1, all 22 values, gears as
> written."* The Pit Crew `setup` block has been stale three sessions out of three.

---

# 1. The sheet

Race only. Every value that differs from your Rev B race column is marked **►**.

```
                                        RACE — TEAM MATE v1
───────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Hard
  Rear compound             Racing Hard

SUSPENSION
  Body height      Front    60 mm · +5 · 20%
                   Rear     68 mm · +8 · 27%          rake +8 mm (car has +5 built in)
  Anti-roll bar    Front    5
                   Rear     3
  Damping compr.   Front    23 · 15%
                   Rear     25 · 25%
  Damping expan.   Front    38 · 40%
                   Rear     34 · 20%
  Natural freq.    Front    3.05 Hz · +5 · 2.5%
                   Rear     3.20 Hz · +20 · 10%
  Camber angle     Front    1.0° · +10 · 16.7%
                   Rear     1.0° · +10 · 16.7%
  Toe angle        Front    0.00°
►                  Rear     +0.15°                    was +0.08

DIFFERENTIAL
  Initial torque            5
► Acceleration sens.        12                        was 14
► Braking sens.             26                        was 24

AERODYNAMICS
  Downforce        Front    370 · 20%
                   Rear     540 · 20%

TRANSMISSION
  Max speed setting         200 km/h — generator only. SET FIRST, THEN NEVER AGAIN.
  Final gear                3.550
  1st                       2.727
► 2nd                       1.820                     was 1.925
► 3rd                       1.470                     was 1.529
  4th                       1.288
  5th                       1.152
  6th                       1.062

BRAKES
► Brake balance             −1  (− front / + rear)    was 0

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)
  ECU output                100%
  Ballast / position        none

ASSISTS
  ABS                       Weak
  TCS                       0 as he runs it — but read §5.3. Recommend 1 for stint 2.
  Countersteer              Off — correct, and keep it off. See §5.4.
═══════════════════════════════════════════════════════════════════
       ► = five changes. Nothing else moves.
```

---

# 2. Why each change, in value order

## 2.1 ⭐ #1 — Rear toe +0.08 → **+0.15°**

**The single most valuable change on the sheet, and it costs him almost nothing.**

Rear toe-in is the cheapest always-on rear security in GT7. It makes the rear axle
generate a small restoring slip angle at all times, which is exactly what converts a
snap into a slide that announces itself. It works in every corner phase — under his late
brake application, through his sharp turn-in, and on his early throttle — without
touching the front end.

**Rev B held it at +0.08 for one reason and that reason is dead.** Rev A held it mid-band
because rear toe is the largest alignment contributor to tyre wear and this is an 8× wear
event. The session then measured **15 laps with no measurable degradation on a
fuel-limited 15.2-lap stint** — there is no wear budget to protect. Rev B §8 test #3
queued +0.12 as the durability audit; for a driver who slides more than you, I am spending
it and going slightly further.

**What it costs:** a little straight-line speed at the most speed-sensitive circuit in GT7,
on the slowest car in Gr.3 in a straight line. Real, and worth it — Monza's tow gives back
more than rear toe takes. +0.15 is comfortably inside proven territory; your Fuji RSR ran
+0.25 and the playbook flagged *that* as large.

## 2.2 #2 — LSD acceleration 14 → **12**

**This is the change that directly addresses "punches throttle early, big commitment."**

The reasoning is the same reasoning that took you from 16 to 14, applied to a bigger input:

- A heavily locked diff **breaks away as a unit** — both rear wheels at once, which is a
  step change in grip and the least catchable thing the car can do. A freer diff lets the
  inside rear give up first, which is progressive and visible.
- Too much acceleration lock also **pushes wide on maintenance throttle** — your #1
  symptom at Monza on 16. He picks up throttle *earlier and harder* than you do, with more
  steering still wound on, so the same lock produces more push and more snap than it did
  for you.

Both failure modes point the same direction. **12.**

**And note what makes 12 affordable:** the longer 2nd and 3rd (§2.5) protect the drive out
of the chicanes that a freer diff would otherwise cost him. These two changes are a pair —
do not take one without the other.

**Initial torque stays at 5, the minimum.** High preload is always-on lock and a silent
cause of mid-corner push. There is no case for lifting it, on any driver.

## 2.3 #3 — LSD braking sensitivity 24 → **26**

He brakes late, on **L2 with no load cell**, into the three heaviest stops in Gr.3, on ABS
Weak. A trigger gives him far less pressure resolution than your ClubSport does, which
means his initial application is a step rather than a ramp — and a step application on a
mid-engined car with 100 L aboard is where the rear steps out.

LSD braking sensitivity is the entire off-throttle rear-stability toolkit in GT7 (there is
no engine-braking map, no brake pressure, no preload in Nm). **26 is measured territory** —
the Laguna Huracán ran 26 successfully against a downhill stop taken while turning in,
which is a harder test than Monza's flat, straight-line stops.

**Why 26 and not 28.** The failure mode on the other side is a car that **refuses to turn
in on the brakes**, and sharp turn-in is his signature. 26 is one step from proven; 28 is
two, and it risks taking away the thing you asked me to build around. **If the rear still
moves under the Rettifilo stop, 28 is the next step** — §6 test #2.

## 2.4 #4 — Brake balance 0 → **−1** (one click FRONT)

**This one is a deliberate departure from your philosophy, and it is a departure because
he is not you.**

Your profile explicitly rejects leaning on front brake bias, and Rev B's whole rear-stability
stack exists so you never have to. That is *your* rule, formed on a load-cell pedal with
progressive modulation. He is braking late through a trigger with no travel and no
force feedback in the brake. Rear lock under a coarse hard initial application is the most
likely way he loses the car in the first 200 m of a braking zone, and it is unrecoverable
on a controller.

One click of front bias buys that back for almost nothing:

- It only acts under braking — it does not dull turn-in, mid-corner or exit.
- ABS Weak manages the extra front lock it introduces.
- It lets me hold LSD braking at 26 instead of pushing to 28+, which protects his turn-in.

**Reminder on the sign, because it is the most commonly inverted value in GT7 advice:
negative = more FRONT. And it is a delta from the car's own factory bias, not an absolute
percentage.**

In-race migration in §5.2.

## 2.5 #5 — 2nd gear 1.925 → **1.820**, 3rd 1.529 → **1.470**

**Lengthening the lower gears is the #1 ranked fix for exit traction limitation in GT7 —
ahead of every LSD and suspension change — and it is the most underused. It also costs
zero PP.** For a driver punching the throttle at TCS 0 over Monza's kerbs, this is the
highest-value free change available.

Using your **measured** gearing constant (K = 1,128.3, limiter 8,600 rpm — no longer
assumed):

| Gear | Ratio | Tops at | Job | Check |
|---|---|---|---|---|
| 1st | 2.727 | 117 km/h | nothing — rolling start | unchanged |
| **2nd** | **1.820** | **175** (was 165) | all three chicanes, no upshift between apexes | Rettifilo exit ~90 km/h = 4,430 rpm · Roggia ~115 = 5,660 rpm ✅ |
| **3rd** | **1.470** | **216** (was 208) | Lesmo 1 and Lesmo 2 | Lesmo apex ~145 km/h = 5,770 rpm ✅ |
| 4th | 1.288 | 247 | Parabolica through track-out | unchanged |
| 5th | 1.152 | 276 | spacing | unchanged |
| 6th | 1.062 | 299 | tops out in a tow | unchanged |

**6% less wheel torque in the two gears where he is spinning the rears, and 2nd still
covers all three chicanes without an upshift between apexes** — which the track reference
says is worth more than getting the final drive right.

**The top three gears and the final drive are untouched, on purpose.** Your Rev B
measurement showed 6th sitting at **98.9% of peak-power rpm** in clean air with 7.4% of rev
range left for the tow. That is a correctly geared top gear and there is nothing to
improve.

**Three side benefits:** less fuel, less rear tyre wear, and a throttle pedal that is less
peaky in exactly the window where a trigger has least resolution.

---

# 3. What this car should feel like to him

Give him this section verbatim — it is written for him, not for you.

### The car will rotate. That is intended. It will tell you first.

Compared with a stock or a conservative sheet, this car has a **free differential and a
soft platform**. On your early throttle it will move rather than push. What the rear toe
and the brake diff are doing is making that movement **start slowly and build**, instead of
arriving as one step. If it feels like the rear is talking to you a corner earlier than
you are used to, that is the setup working.

### Where each change shows up

| Change | Corner | What you should notice |
|---|---|---|
| **Rear toe +0.15** | Everywhere, especially Lesmo 2 and Parabolica | The rear takes a slip angle and holds it instead of letting go. Slides feel longer and slower. |
| **LSD accel 12** | Chicane exits, Parabolica exit | You can pick up throttle earlier with steering still on and the car goes where it is pointed. When it does spin, it is the inside rear alone, not both. |
| **LSD braking 26** | Rettifilo, Roggia, Ascari | The rear stays put during the initial hard hit and through the downshifts. |
| **Brake balance −1** | Rettifilo especially | The rear stops stepping under the first bite of the brake. |
| **Longer 2nd and 3rd** | Out of all three chicanes and both Lesmos | You can be greedier with the throttle over the kerbs for the same amount of spin. |

### The three things that mean something is wrong

1. **The car bogs out of the chicanes, or the inside rear lights up on its own and just
   spins.** The diff is too free for you. **LSD accel 12 → 14.** This is the most likely
   of the three.
2. **The rear still moves under the Rettifilo stop.** **LSD braking 26 → 28.** Do not
   touch brake balance again; it is already one click front.
3. **The car bangs over a kerb and then will not steer at all.** Stop. That is wheel-arch
   contact, not balance, and ride height is the only thing that fixes it — §6 test #1,
   immediately.

### And the one thing that means it is too far the other way

**If the car starts to feel lazy on the brakes — like it will not point into Rettifilo —
that is LSD braking at 26 being too much for you.** Back to 24 and tell us. That is the
failure mode on the other side of the change and it is the one that would cost you your
best weapon.

---

# 4. Assists — the honest recommendation

## 4.1 TCS: build it at 0, race stint 2 at 1

The sheet reflects the 0 he runs, and 0 is defensible on this diff. But the case for **1**
is stronger for him than for you, and stronger in this race than in most:

- TCS 1 costs **near-zero measurable lap time** and catches only the worst exits. The
  playbook baseline is TCS 1 for races.
- A trigger has less throttle resolution than a damped pedal. TCS 1 replaces the fine
  metering the hardware cannot give him.
- **This race goes day into night.** The surface cools, exit traction degrades through the
  race, and cold out-laps get materially slower late on. All three make TCS more valuable
  at the end than at the start.
- Rev B's telemetry found **three rear-left blowups in 36 laps costing 14–28 seconds each**
  — with your throttle, not his.

**The plan: stint 1 at 0, stint 2 at 1.** He will have the data to argue with by then, and
TCS is live on the MFD so it costs nothing to try. **If it rains, 2 immediately.**

**And the diagnostic rule: if he wants TCS 3 or more, the diff or the gearing is wrong, not
the assist.** Come back to us rather than turning it up.

## 4.2 Countersteer assist: off, and keep it off

Correct as he has it. Countersteer assist adds steering input he did not ask for, which
fights a driver who catches slides himself — and it makes every alignment change on this
sheet unreadable, because you cannot tell what the car did from what the assist did. He
catches slides better than you do; do not put a filter between him and that.

## 4.3 ABS Weak: keep

Weak is the competitive setting and it is the right one on a trigger — it exposes what
brake balance is actually doing and shortens stopping distances versus Default, without the
rear-lock exposure of Off. It is also what makes the −1 brake balance safe.

---

# 5. Strategy — same shape as yours, one stop, but he stops earlier

## 5.1 The arithmetic

He short-shifts and uses the maps, which changes the binding constraint.

```
  Race length      50 min ÷ 1:49.2 median                    ≈ 27.5 → plan 28 laps
  Fuel, short-shifting (−20%)   5.25 L/lap                   (6.566 measured at map 1)
  Tank             100 L → 19.0 laps                     ◄── fuel is NOT the limit any more
  Tyre             ~15 laps measured, on Leon's inputs   ◄── THE LIMIT, and see below
  Total fuel       28 × 5.25                                  = 147 L
  Must add         147 − 100                                  = 47 L = 47 s stationary
  Pit transit      19% of a lap                               = 20.7 s
  ─────────────────────────────────────────────────────────────────────────
  ONE STOP · WINDOW LAPS 13–16 · TARGET LAP 14 · ADD 47 L
```

**Short-shifting is worth ~23 seconds net** (costs 0.5 s/lap × 28 = 14 s, saves 37 s of
standing time versus map 1 flat out) and it reduces rear wear as a side effect, on the axle
that is measurably the limiting one. **From lap 1.**

## 5.2 Why his stop is three laps earlier than yours

Rev B targets lap 17. **He targets lap 14, and the earlier stop is nearly free.**

- **His stint will be shorter than yours.** Lateral slip is the dominant wear source
  post-1.49 — *if you can hear the tyres, you are paying for it.* The 15-lap measurement
  was taken with your inputs and with a snappier diff than this sheet runs. A driver who
  slides more consumes more. The gauge read **84% on the rear-left at lap 15**, which is
  not much margin to hand to someone who slides more.
- **And it costs almost nothing to stop early.** The Watkins Glen measurement settles
  this: **refuel volume is worth ~1.0 s per litre; the stop lap is worth ~0.07 s per lap of
  delay.** A 14× ratio. **Optimise litres, not lap.** Moving the stop from 17 to 14 costs
  about **0.2 s** and buys three laps of tyre insurance. Take it every time.
- Second stint is then 14 laps — symmetric with the first, and inside both limits.

**Fill to the diamond plus one lap. The diamond marker is the authority in the race, not
this document.**

**One flag inherited from Rev B, unresolved:** at one stop, an unscheduled wet stop costs a
full 20.7 s of transit. Conditions are changeable with a day-to-night transition, so **if
the radar looks live, hold the stop toward lap 16 and let it double as the weather stop.**
That is the one reason to go later than 14.

## 5.3 Compound: Racing Hard both ends

Same call as yours and for the same measured reasons — RM is ~1.4–1.6× the wear rate, would
not make the stint, and forces a second stop worth −20.7 s against a lap-time gain of about
+11.2 s over 28 laps. **RH wins by ~9.5 s.** It flips only if the real Monza RH→RM delta is
above about 0.75 s/lap, which nobody has measured. Given he wears tyres faster than you,
RH is if anything a clearer call for him than for you.

## 5.4 In-race migration

**Fuel map**

| Situation | Map |
|---|---|
| Default, clean air | **1**, short-shifting |
| In a tow, anywhere on the lap | **5 or 6** — the highest-value habit at this circuit |
| Attacking or defending | **1** |
| Final lap | **1** |

**Brake balance** — one click, two corners, then decide. Never stack changes under pressure.

| When | Move to | Why |
|---|---|---|
| Baseline | **−1** | As per §2.4 |
| Out-lap and first flying lap | **0** | Monza's straights cool the fronts; on cold fronts the extra front bias locks |
| Late in a stint, if the rear moves under braking | **−2** | Rear is the wear-limited axle here |
| Rain | **−2 to −3** | Rear lock on a wet surface is not recoverable |

**TCS** — 0 for stint 1, **1 for stint 2**, **2 immediately if it rains.**

**Weather.** Err wet: on wets when you needed inters costs a little, on inters when you
needed wets costs the race — the measured gap has been 7–8 s/lap in heavy rain. Slicks in
the rain are not slow, they are unusable. Aquaplaning is modelled as sudden and largely
unwarned, and puddles form in consistent places — find them at reduced pace before
committing.

---

# 6. Three things to try first, in order

One change per run, three clean laps, revert what he cannot feel.

### 1. If he bangs a kerb and then cannot steer → ride height +3 mm both ends

**60 → 63 front, 68 → 71 rear.** This is arch contact and nothing else fixes it. It is
**more likely for him than for you**: this platform is 0.30 Hz softer than anything this car
has raced, which means it sits lower under load, and he will use more kerb than you do.
Do this immediately and out of order if the symptom appears — it is not a balance problem.

**A repeated 1–3 second bounce after a kerb is a different thing** — that is frequency
mismatch, and it means Rev B's −0.30 Hz did not go far enough. Front NF has only 0.05 Hz
left below it, so the answer there is also ride height, not more softness.

### 2. If the rear still moves under the heavy stops → LSD braking 26 → 28

In 2s, per the rear-stability stack. **Do not move brake balance past −1** — the whole point
of the stack is that the rear gets stabilised mechanically. If 28 is not enough, the next
lever is **rear expansion damping 34 → 32**, then rear toe +0.15 → +0.18. Brake bias stays
where it is.

### 3. If the car bogs out of the chicanes → LSD accel 12 → 14

Watch the on-screen tyre indicators before deciding. **Inside rear lighting up alone** =
the diff is too free, go back to 14. **Both rears letting go together as a step** = it is
still too locked, go to 10. These are opposite failure modes with the same driver
complaint, and guessing between them wastes a session.

### And the two free observations

**Which corners are fine?** The single highest-information question and the one thing your
Monza packet could not answer — there is still no `corners` array in the export. Have him
name the corner where the car feels perfect. If the Parabolica is fine and only the Lesmos
complain, that is a different diagnosis from all three complaining.

**A rear-left gauge reading at lap 7 and lap 13.** Five seconds, and it is the open item
that has been asked for three sessions running and never taken. His stint length is the
number this sheet is least sure of. One reading closes it.

---

# 7. What I deliberately left alone, and why

The discipline that paid at Laguna and again at Watkins Glen was the changes that were
*queued and not made*.

### The whole platform — ride height, NF, ARBs, dampers

**Untouched.** 3.05/3.20 Hz was bought by a specific measured symptom (repeated kerb
bounce) and Monza is the circuit in the set that most wants compliance. It is also already
near this car's floor. An aggressive kerb-user wants this platform, not a stiffer one — and
softening further is not available.

### Front toe 0.00

**Untouched, and this matters more for him than for you.** Front toe has never been A/B'd
on this car — it is GT7's most disputed parameter and the leading positions on it are
possibly inverted. It also introduces **steering oscillation at speed beyond roughly
±0.05° on some cars**, and he is arriving at the Rettifilo board at 280+ km/h on a
controller. Adding front toe-out to sharpen an already-sharp driver's turn-in, blind, at
that speed, is not a trade worth making. **Zero is the honest starting point.**

### Camber 1.0 / 1.0

**Untouched.** GT7 over-punishes camber and it takes the cost out of **braking and
traction** — which are precisely his two aggressive inputs. More rear camber would also
cost traction on the axle already spinning up. The wear budget being free re-opens camber
as a *test* (playbook A1's caution), not as a guess.

### Front and rear downforce 370 / 540

**Untouched, and this is the Laguna trap wearing a new face.** Adding rear downforce to
give an aggressive driver "confidence" is exactly the change that feels responsible and
isn't. This car's aero window is nearly **balance-neutral** (2 percentage points of front
share across the entire diagonal), 1,300 lb of downforce is worth about 0.1 s/lap, and drag
is the RSR's worst weakness at the most speed-sensitive circuit in the game. It would buy
almost nothing, cost real top speed and tow, and **mask whether the diff package is
actually right.**

### 1st, 4th, 5th, 6th and the final drive

**Untouched.** 6th sits at 98.9% of peak-power rpm in clean air with rev range left for the
tow — measured, not assumed. 4th carries the Parabolica through track-out. 1st does nothing
on a rolling start. Only the two gears he is actually spinning were changed.

---

# 8. Confidence — read this before treating the sheet as authority

Three honest caveats, in order of how much they should worry you.

**1. I have no data on this driver.** Everything above is derived from a two-sentence style
description and from measurements taken with *your* inputs on *your* hardware. The five
changes are all standard, all in the direction his description implies, and none of them is
large — but this sheet is a **hypothesis about a driver**, not a refinement of a measured
one. Your Rev B is the opposite. Read them with different confidence.

**2. It is built on top of an unvalidated revision.** See §0. If Rev B has never been
raced, three of the values on this sheet inherit changes that have never been felt by
anyone.

**3. The stint length is the weakest number in the strategy.** 15 laps was measured on a
saturating tyre gauge and confirmed by a stopwatch, with your driving. His could be 12. The
lap-14 stop and the 1 s/L vs 0.07 s/lap exchange rate are what make that uncertainty cheap
rather than expensive — but a gauge reading at lap 7 and 13 would replace the guess.

**And the 30-second check that still has not been done:** confirm the event's tyre wear is
actually set to **8×**. A 5× model miss is large enough to be worth ruling out the boring
explanation, and the entire one-stop plan rests on it.

---

# 9. What to record

Per standing rule 6 — with date and game version.

1. **His stint length at 8× on RH**, and the rear-left gauge at lap 7 and lap 13. The
   number this sheet is least sure of, and the KB's #1 open item.
2. **Whether accel 12 held**, or whether it bogged and went back to 14. This is the first
   data point on how this car's diff scales with driver aggression, and it generalises.
3. **Whether 26 dulled his turn-in.** You run 24 and trail-brake deeper; if 26 is fine for
   a late-braking controller driver, that is a real finding about the parameter's cost.
4. **Whether the longer 2nd and 3rd felt lazy** out of Rettifilo — the slowest exit on the
   circuit and the one most likely to complain.
5. **Whether brake balance −1 was needed at all.** If he never wanted it, that says the
   rear-stability stack works at neutral for a second driver, which strengthens the
   playbook's central claim.
6. **Which corners were fine.** Every session. Still unanswered at Monza.
7. **Slider step sizes**, if he is in the settings screen anyway. Three cars overdue,
   five seconds each.

---

# 10. Pit Crew paste block — race, team mate v1

One block, one sheet. Paste into the **Event** screen. A clean paste reads
*"22 of 23 settings, 6 gears"* with nothing unrecognised — that string is the acceptance
test.

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Porsche 911 RSR (991) '17",
    "circuit": "Autodromo Nazionale Monza",
    "sessionType": "race",
    "date": "2026-08-17",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Hard", "rear": "Racing Hard" },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "8x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "Monza race teammate v1",
    "values": {
      "rh_f": 60, "rh_r": 68,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 3,
      "dc_f": 23, "dc_r": 25,
      "de_f": 38, "de_r": 34,
      "cam_f": 1.0, "cam_r": 1.0,
      "toe_f": 0.00, "toe_r": 0.15,
      "lsd_i": 5, "lsd_a": 12, "lsd_b": 26,
      "df_f": 370, "df_r": 540,
      "bb": -1,
      "top": 200, "fg": 3.550
    },
    "gears": [2.727, 1.820, 1.470, 1.288, 1.152, 1.062],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 0, "ballastPosition": 0 }
  }
}
```

**The parser reads `sheetName`, `values` and `gears` only.** Compounds, assists, wear and
fuel multipliers, performance adjustment, event format and weather all still have to be
entered by hand on the Event screen.

---

# 11. Range check

Against this car's recorded limits (`11-car-slider-ranges.md`, measured 11 Aug 2026).
**Nothing is clamped. Nothing new sits at a limit.**

| Parameter | Range | Value | Margin |
|---|---|---|---|
| Toe R | −1.00 to +1.00° | **+0.15** | centre of range |
| LSD accel | 5–60 | **12** | 7 above min |
| LSD braking | 5–60 | **26** | 21 above min |
| Brake balance | −5 to +5 | **−1** | 4 from the front limit |
| 2nd gear | clamped by 1st and 3rd | **1.820** | between 2.727 and 1.470 ✅ |
| 3rd gear | clamped by 2nd and 4th | **1.470** | between 1.820 and 1.288 ✅ |
| LSD initial | 5–60 | **5** | at minimum — deliberate, as on every sheet |
| Natural freq. F | 3.00–5.00 Hz | **3.05** | 0.05 Hz above min — inherited from Rev B, see §6 test #1 |
| Max speed | 200–800 km/h | **200** | at minimum — step one of the gearbox procedure, not a setting |

Everything unmarked is unchanged from Rev B §4.1 and was range-checked there.

**Set the gearbox in this order or it will not come out right:** Max Speed slider fully
left to 200 km/h **first** (it is a generator — touching it later wipes every individual
ratio), then final gear 3.550, then the six ratios in order 1st → 6th, then never touch
Max Speed again.

---

*Issued 17 Aug 2026 · GT7 v1.70 · ranges verified on this car 11 Aug 2026*
*Derived from `setups/2026-08-12-rsr-monza-revB.md` — five changes, race column only.*
*Driver model: aggressive controller attacker — late braking, sharp turn-in, early
committed throttle, high slide tolerance, high catch rate. TCS 0, ABS Weak, countersteer
off.*
