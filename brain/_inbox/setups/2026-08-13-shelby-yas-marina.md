═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  YAS MARINA CIRCUIT
  **REV A** — first run of this combination. No prior sheet, session or lap.
  30 min · timed · 2× tyre / 2× fuel · 0 mandatory stops · refuel 2 L/s
  606 bhp · 1335 kg · 2.20 kg/hp · ABS **Off** · TCS 0
  Issued 13 Aug 2026 · GT7 v1.70 · no BoP · min weight 1335 kg, max 606 bhp
  Slider ranges read off this car's own settings screen 13 Aug 2026 — **verified**
═══════════════════════════════════════════════════════════════════

# 0. The headline

**Your two complaints are one problem wearing two faces, and it is not the same
problem on each face.**

> *"Front grip turn in"* and *"rear stability out of corner"* on a 1,335 kg FR car
> with 606 bhp, no ABS and TCS 0 is the exact signature `08-playbook-leon.md` §E3
> describes: **the Shelby will not rotate for free, and it will not put 606 bhp down
> for free either.** If any one of *front sharp / rear supported / platform
> compliant* is missing, this car magnifies it.

So this sheet does three things in a deliberate order, and it does **not** try to buy
front response with camber or by adding front downforce over the top of a diff problem
(the Laguna trap, `08` A5.1):

1. **Rear stability under brake, mechanically, at brake balance 0.** LSD braking
   sensitivity **18** against an FR baseline of 10 — the largest single deviation on
   this sheet. With ABS **Off** at a **5/5 braking-severity** circuit, this is the
   whole ballgame, and A4 says it is the tool that exists for it.
2. **Front response from the four things that actually own turn-in in GT7** — front
   compression damping low (24), front ARB −1, mild front toe-out, front downforce
   high. **Not camber.**
3. **Exit traction from the gearbox first, the diff second.** A6: lengthening 2nd/3rd
   is the #1-ranked fix for exit traction in GT7 and it is massively underused. On a
   606 bhp FR car with TCS 0 it is worth more than any diff number.

**Three things on this sheet are estimates, and I have marked every one of them.**
This is the first run of the combination, so there is no measured wear, no measured
fuel, no gearing constant and no measured lap time for this car anywhere in the
knowledge base. §3.6, §5.1 and §5.2 say exactly what to measure and it costs you
about twelve minutes of the practice session.

---

# 1. What I changed about the build, and why

## 1.1 Ballast: 109 kg from **+20 → 0**, not to −20

You said move it forward. I moved it **20 points forward, to centre, and stopped
there** — and you should know why I did not go further, because the argument cuts
both ways and I do not want you to think it was a clean call.

**The case for moving it forward** (`02-gt7-setup-parameters.md` §8.1): rearward
ballast *"causes over-rotation off-throttle and on corner entry — the car pivots.
Also worsens braking stability."* That is a literal transcription of your complaint
about the rear stepping out under trail braking, and 109 kg at +20 is a meaningful
lump of mass sitting behind you doing it.

**The case against going to −20 or −50**, which is the part worth reading: the
GT350R is **already nose-heavy** — a front-engined Mustang sits around 53:47 front
before you add anything. Rearward ballast on a nose-heavy FR car is *helping* the
axle that has your other problem. Push it forward hard and you get:

- less rear static load → **worse** exit traction, on a 606 bhp car with TCS 0 at a
  circuit whose tyre wear is explicitly **rear (traction)**;
- more front load → more front tyre work mid-corner, which on a heavy car is how
  "no front grip" turns from an entry complaint into a mid-corner one;
- and per `06-car-building-and-pp.md` §5.4, a large distribution change wants the
  springs re-tuned around it — a big bet on an unrun combination.

**Centre is the position that takes the entry-pivot and braking-yaw penalty off the
car without paying for it on the axle that is already your limiting one.** There is
no PP cap this round (min weight + max bhp only), so position is regulatorily free
and you can sweep it — that is test #4 in §7.

> **If exit traction is worse than you expected on the first run, put it back to
> +10 and take the turn-in from front toe and front compression damping instead.**
> Those are the tools that own turn-in in GT7 anyway (A2). Ballast is a
> weight-distribution tool, not a turn-in tool, and I have used it as the former.

## 1.2 Power: stay at 606 bhp. There is no trade to make.

The regs cap **bhp and minimum weight**, not PP. That is unusual and it simplifies
things enormously: weight is pinned at 1335 kg whatever you do, so there is no
"spend PP on power vs weight" decision. Restrictor and ECU both stay at **100%**.

It also means **D3.1 does not apply to you here.** The restricted-build rule — start
accel LSD *below* the layout baseline because a restrictor preserves low-end torque —
was written for the Huracán at Laguna. You are unrestricted, with a flat-plane V8
that makes its power at the top. Your accel-LSD number is set from **power and layout**
(§2.4), not from a restrictor correction.

## 1.3 ABS Off — what that actually costs you on this sheet

You've fixed it, so I've built for it. Two consequences you should be aware of:

- **`08` B3 says ABS Weak is the competitive meta on a wheel** and shortens stopping
  distances vs Default without Off's rear-lock exposure. You are giving up something
  real. I am not arguing — your load-cell brake and sensitivity-10 FFB exist precisely
  to give you the lock information ABS would otherwise mask, and Yas Marina's three
  big stops are all **flat, smooth and wide**, which is the friendliest possible place
  to run Off.
- **It makes LSD braking sensitivity the single most load-bearing number on the
  sheet.** §2.4 explains why 18, and §7 test #2 is how you walk it.

---

# 2. The race sheet — and why every deviation exists

## 2.1 The sheet

```
                                        RACE                    QUALIFYING
─────────────────────────────────────────────────────────────────────────────────
TYRES
  Front compound            Racing Medium ⚠️        Racing Soft
  Rear compound             Racing Medium ⚠️        Racing Soft
                            ⚠️ HEDGE ONLY — do not commit until §5.2 is run

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
  Acceleration sens.        20     · +15 · 27.3%   22     · +17 · 30.9%
  Braking sens.             18     · +13 · 23.6%   16     · +11 · 20.0%
  [AWD]                     n/a — FR                n/a — FR

AERODYNAMICS
  Downforce        Front    150    · +90 · 90.0%   160    · +100 · 100.0%
                   Rear     260    · +110 · 73.3%  275    · +125 · 83.3%
                            total 410 · 36.6% F     total 435 · 36.8% F

TRANSMISSION
  Max speed setting         330 km/h — GENERATOR ONLY. Set first, then never again.
  Final gear                3.600  · 53.3%          3.700  · 56.7%
  1st                       2.614                   2.614
  2nd                       1.797                   1.797
  3rd                       1.400                   1.400
  4th                       1.155                   1.155
  5th                       1.010                   1.010
  6th                       0.921                   0.921
                            Ratios identical both columns; only final gear moves.

BRAKES
  Brake balance             0  (− front / + rear)   0

PERFORMANCE ADJUSTMENT
  Power restrictor          100% (none)             100%
  ECU output                100%                    100%
  Ballast / position        109 kg / 0 ◄ moved      109 kg / 0

ASSISTS (not on the GT7 sheet — set in the menu)
  ABS                       Off                     Off
  TCS                       0 — see §5.5            0
  Countersteer assist       Off                     Off
═══════════════════════════════════════════════════════════════════
```

**Step sizes assumed:** ride height 1 mm, natural frequency 0.01 Hz, camber 0.1°,
toe 0.01°, downforce 1 point (every downforce value above is a multiple of 5, so it
survives a 5-point step), final gear 0.001. **If any click count disagrees with what
you see on screen, the percentage is the authority** — that is the whole reason the
sheet carries three forms of each number.

## 2.2 Suspension — the deviations

**Ride height 80 / 98 (baseline says F +3–5, R +5–8 above minimum).**
Front is at baseline. **Rear is deliberately 2–5 clicks lower than baseline**, and
this is the one place I have gone against B1 on purpose.

This car's floors are **75 mm front / 95 mm rear** — it has **+20 mm of positive rake
built into its own minimums** before you touch anything. Baseline clicks on top of
that would give roughly +22 mm rake. Positive rake promotes entry rotation, which you
want — but A4 #5 lists *reducing* rake as a rear-stability lever, and rear stability
under brake is your stated problem. Running the rear near its floor puts effective
rake at **+18 mm**, i.e. slightly *less* than the car's own built-in minimum, without
giving up the rotation the rake is already providing for free.

This also matches the Watkins Glen finding in `01` §11: *"Rear ride height constraint:
minimum 95 mm rear on that setup. Stability must be found within the available
geometry."* It can be — but only by keeping the rear low, not by chasing rake.

Yas Marina permits it: **minimal elevation, moderate flat modern kerbs, "forgiving
suspension circuit — run low and medium-stiff"** (`05-track-reference.md` §1.25).
This is not Sainte-Croix and it is not Bathurst.

**Natural frequency 3.05 / 3.20 Hz.**
Two independent checks agree, which is reassuring given the RSR lesson that
percent-of-range and absolute Hz can point in completely different directions:

- **Percent of range:** 64.3% / 63.2%, just below B1's 70–80% racing-tyre band.
- **Absolute:** 3.0–3.2 Hz on a 1,335 kg car on racing slicks is squarely in the
  Gr.3 window.

Unlike the RSR — whose 3.00 Hz *floor* was already race-stiff and broke the
percent-of-range heuristic — this car's floor is **1.88 Hz**, genuinely road-soft.
So percent-of-range is meaningful here. I have sat just under the band because this
is a heavy road-car platform and `01` §11 records repeatedly that **stiffening the
Shelby has cost grip over surface changes and worsened throttle exit.** Rear is
**+0.15 Hz above front** — rotation on a stable platform, per B1 — and not more,
because a stiffer rear is exactly what you do *not* want on the axle that already has
your traction problem.

Headroom either way: **0.65 Hz above / 1.17 Hz below at the front.** Plenty of room
in both directions, which is what you want on an unrun combination.

**ARB 5 / 4 (FR baseline 6 / 4).**
Front −1 from baseline. This is your proven move — Fuji RSR, `08` B2 — and it is the
correct mid-corner front-grip lever. Rear stays at baseline: it protects rear grip on
a car whose exits feed two long straights.

Note what this does **not** claim: A2 is explicit that front ARB acts **mid-corner,
not at the instant of turn-in.** If your turn-in complaint is genuinely at the moment
you first load the wheel, the ARB is not the thing that will fix it — front
compression damping and toe are, which is why both moved too.

**Damping 24 / 28 compression, 40 / 34 expansion (baseline 28/30, 40/38).**

- **Front compression 24, four clicks off its floor.** A2 ranks *front compression
  damping lower* as the **#1 front-response tool in GT7 and the most underrated** —
  it lets load transfer forward faster, giving front bite at exactly the moment of
  turn-in, and it costs nothing elsewhere. Your complaint names that moment, so this
  goes further below baseline than usual.
- **Rear expansion 34, four clicks off its floor.** A4 #2: a rear that extends too
  fast on lift unloads abruptly. This is #2 in the rear-stability stack and it is
  free — it costs nothing on any other axis.
- **Rear compression 28** (−2): a touch more compliance on the axle that has to
  absorb 606 bhp off three slow exits.
- **Front expansion 40** stays at baseline.

> **A4 #4 is the tension you should know about.** Front compression damping is
> simultaneously your best turn-in tool (lower) and a rear-stability tool (higher).
> I have resolved it the way A4 says to: **take rear stability from #1–#3 of the
> stack — LSD braking, rear expansion, rear toe — which do not touch the front, and
> keep front compression low for bite.** If the rear is still stepping after test
> #2 in §7, front compression going *up* is the last resort, and it will cost you
> turn-in when it happens.

**Camber 1.4° front / 1.0° rear (baseline 1.2 / 1.2).**

Front **up** 0.2°, rear **down** 0.2°, and both directions are deliberate.

- **Front 1.4:** this is a heavy car on a softish platform, so it rolls more and loses
  more camber in roll than a Gr.3 car does — a real mid-corner front-grip argument.
  But A1 is unambiguous that GT7 over-punishes camber on **longitudinal** grip, and
  you are running **5/5 braking severity with ABS Off**. Every 0.1° here is a direct
  tax on the one thing you cannot afford to compromise. 1.4 is as far as that argument
  goes. **Camber is not a turn-in tool in GT7** (A1) — it is not addressing your entry
  complaint and I am not pretending it is.
- **Rear 1.0:** below baseline, protecting exit traction and rear tyre life on a
  circuit that explicitly **wears rear (traction)**. Rear camber costs the axle that
  is already your limiting one, twice over.

**Toe −0.05° front / +0.10° rear.**

- **Front −0.05 (toe-out).** A3: *never front toe-**in***, that is firm. Beyond that
  the direction is **genuinely disputed in GT7 and has never been A/B'd on this car**.
  I have gone one click out because your Shelby history in `01` §11 is a repeated
  request for more initial bite, and −0.05 sits inside the band where A3 warns
  **steering oscillation at speed** starts. Yas Marina has two long straights, so
  going further out is a real risk, not a theoretical one.
  **This is confidence-flagged. It is test #3 in §7 and it is 20 minutes.**
- **Front toe is identical in both columns**, deliberately. Normally quali gets more
  bite — but adding toe-out for one lap on a circuit with a 1.1 km straight risks
  losing the lap to a wandering car at 290 km/h. The gain is not worth the variance
  until the A/B says which direction this car even wants.
- **Rear +0.10.** Top of B1's recommended band (+0.05 to +0.10), not above it. With
  ABS Off and three traction-limited exits it earns its place, and B2 warns
  explicitly that **0.25 is too much** and that rear toe is the biggest alignment
  contributor to tyre wear. Quali takes **+0.08** — slightly less drag on the one lap,
  and no stint to protect.

## 2.3 Differential — the most important section on this sheet

**Initial torque 5 — at the hard minimum, and here is the justification the format
rule requires.**

Preload locks the diff in *every* phase of *every* corner at once. B1 calls high
preload *"a silent cause of the persistent mid-corner push you hate."* Your #1 stated
complaint is front grip at entry. Preload is the diff parameter that most directly
opposes it, and unlike the other two it cannot be aimed at a phase. Rear stability is
bought from **braking sensitivity**, which *is* direction-specific. So preload goes to
the floor and stays there.

**If the car feels vague or floppy on turn-in transition** — not pushing, just
disconnected — 5 → 8 is the one legitimate reason to move it, and it is a small,
cheap test.

**Acceleration sensitivity 20 (FR baseline 25).**

Down 5 from baseline, matching your validated Fuji RSR move (25 → 20, `08` B2).
Reasoning:

- **A5's rule is run low and prove you need more.** Two of A5's three failure modes —
  *both rears let go together as a snap*, and *pushes wide while on throttle* — are
  fixed by going **down**. Your complaint of "rear stability out of corner" is
  consistent with the first.
- **`05` §1.25 says accel 25–32 for Yas Marina.** I am not taking it. A5.1 rule 3 is
  explicit: **never import a track's generic diff guidance without checking the build
  it assumes.** That number is written for a Gr.3 car with ~550 bhp, far more
  downforce, and about 300 kg more aero-generated load through the fast sections. You
  have 606 bhp, road-car aero, TCS 0 and no ABS.
- **But it is not lower than 20**, because FR genuinely needs more lock than MR to put
  power down, and the other side of A5's fork — *inside rear lights up alone, car bogs
  out of the slow exits* — is a real risk on a 2.20 kg/hp car out of a 2nd-gear
  hairpin complex.

> ⚠️ **I do not know which of A5's failure modes you actually have, and I am not
> going to guess.** *"Rear stability out of corner"* is ambiguous between wheelspin
> (inside wheel — needs **more** lock) and snap (both wheels — needs **less**), and
> those point in opposite directions. **§7 test #1 separates them in one run using
> the on-screen tyre indicators, and it costs you nothing.** 20 is the value that is
> least wrong if you never run the test; it is not the value that is right.

**Braking sensitivity 18 (FR baseline 10) — the largest deviation on this sheet.**

A4 is the most important translation in the playbook and it applies to you almost
word for word:

> *GT7 has no engine-braking map, no brake pressure, no brake ducts, no preload in Nm.
> **LSD braking sensitivity IS your entire off-throttle and on-brake rear-stability
> toolkit**, alongside rear toe and rear damping. Your Watkins Glen Shelby session —
> rear locking with no ABS, brake bias forward rejected as a solution — is precisely
> the problem it exists to solve.*

That is this session, at a circuit with **5/5 braking severity** and three heavy
back-to-back stops. A4 puts the effective range at **+5 to +15** over baseline. I have
taken **+8**, not +10 or +15, because:

- The failure mode on the other side is **the car refusing to turn in on the brakes**,
  which for a deep trail-braker is the worse of the two, and you have never run this
  car near this number;
- The Laguna Huracán ran **26 against an MR baseline of 20** (+6) successfully, at
  brake balance 0, against a harder entry than any at Yas Marina — so a similar-sized
  step is proven, and a much larger one is not.

**Walk it, do not jump it.** §7 test #2 takes it up in 2s to 20 and 22 if the rear
still steps. Stop the instant turn-in dulls on the brakes.

**Quali runs 16, not 18.** One lap on fresh Softs, no worn rears, no fuel-load
transition — the entry-stability tax is smaller and the turn-in is worth more.

## 2.4 Aerodynamics

Yas Marina is **Med-High downforce, "at or slightly above midpoint"**, with a ~58%
full-throttle share — the two long straights are balanced against T2/T3 and the whole
final sector being genuine aero corners.

**Race 150 / 260 → total 410, 36.6% front.**
The front slider spans only 100 points on this car (60–160) against 150 at the rear,
so B1's *"max the front, then trim the rear to balance"* costs almost nothing in drag.
I have left **10 points of front headroom** on the race sheet on purpose, so there is
somewhere to go if you report mid-corner push in the fast sections **and test #1 has
already ruled out the diff**.

> ⚠️ **Read that condition literally.** Adding front downforce to a push you have not
> diagnosed is the exact move `08` A5.1 records as the trap that was avoided at
> Laguna — front ARB 5→4 and front DF 425→450 were both queued, neither was needed,
> and both would have masked a diff problem while giving up something real. **Diagnose
> the throttle state first. Every time.**

**Quali 160 / 275 → total 435, 36.8% front. Front is at its hard maximum.**
Justified per the format rule: the front span is only 100 points total, front bite is
your #1 stated complaint, and on a single lap there is no stint to protect and no fuel
to save. The drag cost of the last 10 front points is negligible against the benefit
through T2/T3 and the final sequence. Balance is held essentially constant between
columns (36.6% → 36.8%) so the quali car is a *sharper* version of the race car, not a
different one.

**Never trim rear downforce first for top speed** (`01` §8). If the car is slow down
the back straight, that is a gearing conversation (§3), not an aero one.

## 2.5 Brakes

**Brake balance 0, both columns. Held there on purpose.**

`05` §1.25 recommends *"one click forward"* for Yas Marina. **I am not taking it**,
because your profile is explicit — §16: *"the current explicit preference is not to
rely on forward brake bias. Resolution: mechanical rear stability first, then brake
balance around neutral as a fine adjustment."*

And re-reading your note: *"I prefer rear brake bias, not locking rears and stepping
out under trail braking."* You want to be at **+1**, and the rears won't let you.
**That is the whole point of the A4 stack.** LSD braking 18, rear expansion 34, rear
toe +0.10 and rear camber 1.0 exist to make **+1 available to you by the end of the
stint.** §5.5 treats that as the prize, not −1 as the fallback.

**−1 stays available as the emergency**, and it is the correct in-race response to a
genuine lock, but it is not a setup solution and it is not where this sheet starts.

---

# 3. Gearing — built from the circuit

## 3.1 The two constraints

Not a target top speed. From `05-track-reference.md` §1.25, the layout gives exactly
two hard constraints, and everything else is spacing:

| | Constraint | Sets |
|---|---|---|
| **Slowest** | *"The T5–T8 hairpin complex and the T11–T14 section are 2nd/3rd gear"* and *"**2nd for the hairpin complex**"* | **2nd gear** |
| **Longest** | *"The two longest straights end in slow corners"* — the T7→T8 back straight is the longer. *"**Gear for slipstream on the two long straights**"* | **6th gear** |

**2nd must cover the whole hairpin complex without an upshift between apexes.** That
constraint outranks the final drive — it is the same one that caught Monza out
(`13-pitcrew-v1.2` §Why, item 2) and that nothing in the export currently verifies.

## 3.2 The gearing constant

`setups/2026-08-12-rsr-monza-revB.md` §3 established the method: one reading of speed,
rpm and limiter in top gear gives **K = speed × ratio × final gear**, and every future
gearbox on that car is exact instead of iterated.

**This car has no measured K.** I have estimated it, and I want the estimate visible
rather than buried:

```
  K = limiter_rpm × rolling_circumference × 0.06

  Limiter               8,250 rpm    [ASSUMED — real GT350R redline; GT7 unverified]
  Rolling circumference 2.091 m      [ASSUMED — 305/30 R19 rear geometry]
  ────────────────────────────────────────────────────────────────
  K ≈ 1,035                          ⚠️ ESTIMATE. Compare RSR measured K = 1,128.
```

**The Monza precedent is the reason to distrust this.** Rev A there assumed an 8,800
rpm limiter; the real number was **8,600**, and every speed in the table was **2.9%
optimistic** — almost entirely from the limiter, not the tyre radius. Expect a similar
error here, in an unknown direction.

## 3.3 The ratios and what each gear is for

Race, final gear **3.600**:

| Gear | Ratio | Tops out at | The job it has to do |
|---|---|---|---|
| 1st | 2.614 | 110 km/h | Grid start only. Nothing else. |
| **2nd** | **1.797** | **160 km/h** | **The T5–T8 hairpin complex, apex to exit, no upshift.** The binding constraint. |
| 3rd | 1.400 | 205 km/h | T11–T14; the T9 exit before it straightens |
| 4th | 1.155 | 249 km/h | T2/T3 fast left-right; final-sector entry |
| 5th | 1.010 | 285 km/h | Spacing into top gear |
| **6th** | **0.921** | **312 km/h** | **Back straight, topping out in a tow, not in clean air.** |

Speed gaps: **+50, +45, +44, +36, +27 km/h** — diminishing increments, per A6 step 5.

**The top gear is set for a tow, not for clean air, and that is deliberate.** Yas
Marina has two long straights and `05` says explicitly *"gear for slipstream."* In a
30-minute timed race off a grid start you will spend real time in traffic. If 6th
tops out in clean air you have thrown away the only free lap time on the circuit.

Expected clean-air behaviour at K = 1,035: peak power somewhere around 7,700–7,900 rpm
on this build, which puts you at roughly **293–300 km/h in clean air with 6th still
pulling**, and the limiter reachable only with a tow. That is what a correctly geared
top gear looks like (RSR Monza sat at 98.9% of peak-power rpm at Vmax in clean air).

**Quali, final gear 3.700 — identical ratios, shorter final drive.** Clean air, no
tow, so 6th tops at **304 km/h** and every gear tightens ~2.7%. 2nd drops to
**156 km/h**, which still covers the hairpin complex.

## 3.4 The order you set it in — this is the #1 GT7 gearbox error

1. **Maximum Speed → 330 km/h. FIRST.** It is a *generator*, not a trim. Touching it
   afterwards wipes every individual ratio you have set.
2. **Final gear → 3.600** (race) / **3.700** (quali).
3. **Individual ratios**, 1st through 6th, as tabled.
4. **Never touch Maximum Speed again.**

## 3.5 ⏱️ Measure K — two minutes, and it makes every future Shelby gearbox exact

Down the back straight in clean air, no tow, note three numbers:

```
  ① Speed at the braking point for T8, in km/h  ______
  ② Rpm at that moment                          ______
  ③ Limiter rpm — ONLY if the rev limiter actually fires. Not the
     highest rpm you happen to see.             ______

  Then:  K = ① × (③ ÷ ②) × 0.921 × 3.600
```

Send me those three numbers and every gearbox this car ever gets stops being iterated.
`00-INDEX.md` standing rule 6 — it goes into the knowledge base with a date and a
version.

**Also tell me which gear you are in at:** the T5 apex, the T8 apex, the T11 apex, and
the final corner exit. That is the only way to verify constraint #1 actually held.

---

# 4. Strategy

## 4.1 What the race actually is

```
  Length        30 min, timed, grid start, 0 mandatory stops
  Laps          1800 s ÷ ~1:58 estimated  ≈ 15.3  →  plan 16 laps ⚠️ ESTIMATE
  Tyre          2× · Fuel 2×
  Refuel        2 L/s [declared]
  Pit loss      20 s [declared] ⚠️ but see §4.2 — the two figures disagree
```

**Lap time ⚠️ ESTIMATE.** Gr.3 reference here is 1:52–1:56. You have more power
(606 vs ~550), less downforce and 35 kg more than a Gr.3 car, on the same racing
compounds. **1:56–2:00 is my window, 1:58 central**, and the first flying lap of
practice replaces it. Every lap-count number below moves with it.

## 4.2 ⚠️ Pit loss — the two figures on the brief cannot both be true

```
  Declared           20 s   (still the app default — the brief asks you to confirm it)
  05-track-reference 19% of one lap
  19% of 1:58                                       = 22.4 s
  20 s would imply a lap time of                    = 1:45.3
```

**1:45 is faster than the Gr.3 record here.** So either the 20 s is a leftover default
or the track reference's 19% is wrong. I have run §4.4 at both and — usefully — **it
does not change the call**, because the call is *don't stop at all*. But it would
matter enormously if the tyre forces a stop.

**Measure it once:** on an out-lap in practice, note the clock crossing the pit-entry
line and crossing the pit-exit line, then subtract the time it would have taken to
drive that same stretch on track. Five minutes, and `08` G10 lists it as *"the number
that most changes strategy."*

## 4.3 ⚠️ Fuel — estimated, and this is where I am least confident

There is **no measured fuel figure for this car anywhere in the knowledge base.** The
best anchor available is the RSR at Monza — **6.566 L/lap at 3×**, measured across 28
laps, i.e. **0.378 L/km at 1×** for a 509 bhp Gr.3 car.

```
  Scaled for power     × 606/509                    = 1.19
  Scaled for throttle  Yas ~58% FT vs Monza ~78%    ≈ 0.85
  ────────────────────────────────────────────────────────
  ≈ 0.382 L/km at 1×  ×  5.3 km  ×  2 (multiplier)  ≈ 4.05 L/lap
```

**Call it 4.0–5.0 L/lap at 2×, central 4.5.** Confidence: low. The Monza fuel estimate
was the one thing the model got *right* (`revB` §9.3), so the method has one success
behind it — but on a different class of car.

**And I do not know your tank capacity.** GT7 uses realistic capacities for road cars;
the real GT350R is 60.6 L. I have used **60 L [ASSUMED]**. **Read it off the fuel
readout on your first lap of practice** — it is a two-second check and it is the
single number this whole section pivots on.

## 4.4 The call: **go for no stop**

```
  Fuel needed, 16 laps @ 4.5 L        = 72.0 L
  Tank                                = 60.0 L  ⚠️ assumed
  Shortfall                           = 12.0 L   → 17% saving required

  Short-shifting alone (−20%, C3)     = 3.60 L/lap → 57.6 L over 16 laps ✅ FITS
```

| | Cost | Note |
|---|---|---|
| **No stop, short-shift from lap 1** | ~0.5 s/lap × 16 = **8 s** | C3: short-shift ≈ −0.5 s/lap, −20% fuel, **and less rear tyre wear** |
| One splash, ~14 L | 22 s transit + 7 s standing = **29 s** | And it is 22 s even if you only need 3 L |

**No stop wins by roughly 21 seconds.** Over a 16-lap race that is ~1.3 s/lap, which
no compound delta at this circuit gets close to.

And short-shifting is a **triple win here**, not a compromise: it saves the fuel, it
reduces **rear** tyre wear, and this circuit's wear is explicitly **rear (traction)**.
Every argument points the same way, which per the Laguna note is rare and worth
trusting when it happens.

> **The whole plan therefore hangs on one question: does the compound survive 16 laps
> at 2×?** That is what §5.2 measures, and it is why the race compound on the sheet is
> flagged as a hedge rather than a decision.

**Fallback if the tank is smaller than 60 L or fuel/lap is above ~4.7:** one
splash-and-dash, **window laps 11–13**, take only what you need. At 2 L/s the standing
time is trivial; the transit is the whole cost, so take it as late as the fuel allows
and keep it available to double as a weather stop. (Conditions are declared **Dry,
afternoon** — but `revB` §5.4 records getting exactly this backwards at Monza.)

**Fuel map plan:**

- **Short-shift from lap 1.** Not a late-race rescue — the habit for the whole race.
- **Map 1 default.** Map 5–6 whenever you are in a tow on either long straight;
  it is close to free.
- **Map 1 when attacking, defending, or on the last lap.**
- **The arithmetic to run in-car on lap 3:** litres used ÷ 3 × laps remaining, against
  litres in the tank. If it does not fit, take one more map step. **The fuel diamond
  is the authority in the race, not this document.**

## 4.5 In-race brake-balance and TCS migration

Three phases. Both are live on the MFD and neither needs a pit stop.

| Laps | Brake balance | TCS | Why |
|---|---|---|---|
| **1–5** (full tank) | **0** | **0** | Full fuel sits the car down; the rear is at its most stable it will be all race. Start from the sheet and learn it. |
| **6–11** | **0**, or **−1** if you get a genuine rear lock into T5 or T8 | **0**, or **1** if the rear spins on the T7/T9 exits | Fuel is coming off the back of the car — entry rotation increases. `02` §7.4: move **toward the front** progressively as the tank empties to keep entry consistent. |
| **12–16** (light, worn rears) | **−1** if the rear is locking; **+1 if it is not** | **1** if the rears have gone off | Rears are the limiting axle here. `02` §7.4: as rears go off, move **forward** to shift work onto the fresher fronts. |

> **The +1 in the last phase is the point of this entire sheet.** If the A4 stack has
> done its job, you should be able to take the rear bias you actually prefer in the
> closing laps, on worn tyres, with no ABS. If you get there, tell me — that is a
> result worth recording, and it is a harder test of A4 than either Laguna or Monza
> was.

**TCS stays at 0 for the first runs**, against B1's *"TCS 1 for race"* default, for
the Monza reason: **TCS 1 and the accel-LSD number are aimed at the same events.**
Turn TCS on before you have run §7 test #1 and you will not know which one helped.
Run the diff test first. After that, TCS 1 late in a stint is cheap and sensible.

---

# 5. What to measure in the practice session — twelve minutes, in this order

You said you have 15–20 minutes. Here is how to spend it. **This is F1 step 5 and
`08` C3.1's standing rule:** *no modelled wear figure may be used to select a race
compound.*

## 5.1 First — read two numbers off the screen (30 seconds)

1. **Tank capacity in litres.** §4.3 pivots on it entirely.
2. **Confirm tyre wear is actually set to 2× and fuel to 2×** in the event settings.
   `revB` §5.1 flagged this as the boring explanation worth ruling out before you
   trust a surprising measurement, and it costs nothing.

## 5.2 ⭐ Then — one six-lap stint on **Racing Medium**, race pace, from full fuel

The highest-value twelve minutes available to you. Record:

| Lap | Time | Fuel used | Tyre gauge — worst corner |
|---|---|---|---|
| 1 | | | |
| … | | | |
| 6 | | | |

Then apply this decision rule:

| What you see over 6 laps | Race compound | Race plan |
|---|---|---|
| RM barely moves — <0.15 s/lap fall-off, gauge under ~35% | **Racing Soft.** Run one confirming RS stint if time allows. | No stop |
| RM steady — gauge projects past 16 laps | **Racing Medium.** As written. | No stop |
| RM projects to fall off around lap 12–14 | **Racing Hard** | No stop |
| Even RH cannot make 16 laps without >1.3 s/lap average loss | RM | One stop, lap 11–13 |

**That last row is the only thing that justifies a stop**, because 1.3 s/lap × 16 laps
is what the 21-second pit-loss saving is worth.

> **Why the sheet says Medium.** It is the hedge, not a decision. There is no measured
> wear for this car on any compound on any circuit, and the two times this knowledge
> base has modelled wear it was **1.8× wrong at Laguna and ~5× wrong at Monza** — both
> times *pessimistic*, both times costing real lap time to a compound that was harder
> than necessary. There is also a counterweight specific to you: `08` C4 notes **road
> cars are disproportionately punished post-1.49**, so 2× on this car may behave more
> like 4× on a Gr.3. Those two errors point in opposite directions, which is precisely
> why this gets measured rather than argued.

**Also note, for free, while you are out there:** **which corner and which tyre goes
first.** The circuit reference says rear (traction). The Monza session proved that
reference wrong on the front axle's side (`revB` §2.5), so it is worth an actual look.

## 5.3 Then — the K measurement (§3.5), if you have two minutes left

---

# 6. What each change should feel like

One change per run, three clean laps, revert what you cannot feel.

### LSD braking 10 → 18

**Where:** the T5 and T8 stops, from initial application through the trail phase to
the apex.
**Should feel like:** the rear stays *behind you* as you bleed the brake into steering.
The step-out under trail braking should be gone, not reduced.
**Working:** you can carry the brake deeper into T5 and T8 without a correction, and
you are not thinking about brake balance.
**Too far — and this is the failure mode that matters for you:** the car **refuses to
turn in on the brakes.** It feels safe and lazy and the nose will not come round while
you are still on the pedal. That is A4's other side and it is the worse of the two for
a deep trail-braker. **Back to 16, then 14.**

### Front compression 28 → 24

**Where:** the instant you first load the wheel — T5, T8, T11.
**Should feel like:** the nose takes a set faster. Less waiting for the car.
**Cost you should accept:** slightly more pitch under the big stops with a full tank.
**Watch for:** if the front feels *sharp but unsupported* — bites then washes — that is
too little compression, not too much toe. Go back to 26 before touching anything else.

### Natural frequency, and ballast to 0

**Should feel like:** a calmer, more compliant car than the Shelby usually is, with
less of the "grip loss over surface changes" `01` §11 keeps recording, and less pivot
when you release the brake.
**Cost you should expect and accept:** more body roll through T2/T3 and the final
sequence. **If the bounce/roll is present but the car repeats itself lap after lap,
leave it.** `01` §11 on this car: *"the correct end state is not a faster single lap;
it is a car that repeats the same balance lap after lap."*

---

# 7. Three things to test first — in priority order

## ⭐ 1. Diagnose the exit problem before touching the diff. One run. Free.

**I do not know which failure mode you have and neither do you yet.** A5's three modes
point in two opposite directions, and getting this wrong means a whole session spent
making it worse.

Out of the **T7 exit** and the **T9 exit** — the two that feed straights — watch the
**on-screen tyre indicators** and answer one question:

| What you see / feel | Diagnosis | Change |
|---|---|---|
| **Inside rear lights up alone**, car bogs out of the slow exits | Accel too **LOW** | **20 → 23** |
| **Both rears go together**, feels like a snap | Accel too **HIGH** | **20 → 17** |
| **Pushes wide while you are on throttle** | Accel too **HIGH** — A5's third mode, the one that caught us out at Laguna | **20 → 17** |

**Do not guess between them.** F2 question 1 — *where is your right foot* — forks this
entire diagnosis, and A5.1 records that it resolved a whole case in one step. And ask
F2 question 2 while you are at it: **which exits are fine?** If T7 is clean and only
T9 complains, that is a different answer from both complaining.

## 2. If the rear still steps under trail braking → walk LSD braking up, not brake balance forward

In **2-point steps**: **18 → 20 → 22.** Three clean laps at each. **Stop the moment
turn-in starts to dull on the brakes** — that is the boundary and it is the whole
tuning axis.

If 22 is not enough before turn-in goes, the stack continues in A4 order and **brake
balance is still not on the list**:

1. **Rear expansion damping 34 → 32.** (You have only 4 clicks of floor left here.)
2. **Rear toe +0.10 → +0.12.** Costs top speed on two long straights and rear tyre
   life on a rear-wear circuit — which is why it is third, not first.
3. **Rear ride height 98 → 101.** Reduces rake further. `01` §11's Watkins Glen note
   says the geometry is the constraint; this spends some of it.
4. **Front compression 24 → 26.** Last, because it is the one that takes your turn-in
   back (A4 #4).

**Brake balance forward is not a solution and is not on this list.** −1 is an in-race
trim for a single lock, not a fix.

## 3. Front toe A/B — the 20 minutes with the highest information content on this car

**−0.05 / 0.00 / +0.05**, three clean laps each, Data Logger on.

A3: GT7's front toe behaviour is **genuinely disputed and possibly inverted**, the two
best sources say opposite things, and **it has never been A/B'd on this car**. It sits
directly on your stated #1 priority. It has been the top open item in `08` Part G for
the Huracán since 10 August for exactly this reason, and it is the same 20 minutes here.

**Report which gave the initial bite.** Do this on a run where nothing else has
changed, or the result is worthless.

## And the fourth, if the first three land

**Ballast sweep: 0 vs +20 vs −20.** Two-minute change, no PP consequence under these
regs, and §1.1 explains why I stopped at centre rather than committing. If exit
traction is the surviving complaint after test #1, go back to **+10**. If entry pivot
is, go to **−20** and re-check the rear NF.

---

# 8. Range check

Every value on both sheets, against the ranges you read off this car on 13 Aug 2026.

| Parameter | Range | Race | Quali | Margin |
|---|---|---|---|---|
| Ride height F | 75 – 160 mm | 80 | 78 | ✅ 3 mm above min |
| Ride height R | 95 – 180 mm | 98 | 97 | ✅ 2 mm above min |
| Natural freq. F | 1.88 – 3.70 Hz | 3.05 | 3.20 | ✅ 0.50 Hz below max |
| Natural freq. R | 2.00 – 3.90 Hz | 3.20 | 3.35 | ✅ 0.55 Hz below max |
| ARB F | 1 – 10 | 5 | 6 | ✅ |
| ARB R | 1 – 10 | 4 | 5 | ✅ |
| Damper compr. F | 20 – 40 % | 24 | 25 | ✅ 4 above min |
| Damper compr. R | 20 – 40 % | 28 | 30 | ✅ |
| Damper expan. F | 30 – 50 % | 40 | 41 | ✅ |
| Damper expan. R | 30 – 50 % | 34 | 36 | ✅ 4 above min |
| Camber F | 0 – 6 ° | 1.4 | 1.6 | ✅ |
| Camber R | 0 – 6 ° | 1.0 | 1.2 | ✅ |
| Toe F | −1 – +1 ° | −0.05 | −0.05 | ✅ |
| Toe R | −1 – +1 ° | +0.10 | +0.08 | ✅ |
| **LSD initial** | **5 – 60** | **5** | **5** | ⚠️ **AT MINIMUM — deliberate, §2.3** |
| LSD accel | 5 – 60 | 20 | 22 | ✅ 15 above min |
| LSD braking | 5 – 60 | 18 | 16 | ✅ 13 above min |
| **Downforce F** | **60 – 160** | 150 | **160** | ⚠️ **QUALI AT MAXIMUM — deliberate, §2.4** |
| Downforce R | 150 – 300 | 260 | 275 | ✅ 25 below max |
| Brake balance | −5 – +5 | 0 | 0 | ✅ centred |
| Max speed | 200 – 800 km/h | 330 | 330 | ✅ generator only |
| Final gear | 2.000 – 5.000 | 3.600 | 3.700 | ✅ |

**Nothing was clamped.** No value had to be pulled back from a range boundary — every
number above is where the engineering put it.

**Two values sit at a hard limit, both on purpose, both justified in full above:**

1. **LSD initial torque = 5, at minimum, both columns.** Preload is the only diff
   parameter that cannot be aimed at a corner phase; it opposes turn-in in every
   corner at once, and turn-in is the stated #1 complaint. Rear stability comes from
   braking sensitivity instead, which *is* phase-specific. §2.3.
2. **Front downforce = 160, at maximum, qualifying only.** The front slider spans only
   100 points against the rear's 150, so the drag cost of the last 10 points is
   negligible, and on a single lap there is no stint or fuel to protect. The race
   column deliberately holds 10 points of headroom. §2.4.

**One convention note:** the toe percentages above are *percent of the full −1…+1
span*, so 47.5% reads as "just below centre" — that is correct and it is why
`09-setup-sheet-format.md` and the RSR register both insist **toe is issued in absolute
degrees, never as a percentage.** Use the degrees.

---

# 9. Pit Crew paste blocks

**One block per sheet. Paste them one at a time into the Event screen. Race first.**
A clean paste reads **"22 of 23 settings, 6 gears"** with nothing unrecognised —
22 because `awd` is correctly omitted on a two-wheel-drive car.

## 9.1 RACE

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Yas Marina Circuit",
    "sessionType": "race",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Medium", "rear": "Racing Medium" },
    "assists": { "abs": "Off", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Yas Marina race v1",
    "values": {
      "rh_f": 80, "rh_r": 98,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 4,
      "dc_f": 24, "dc_r": 28,
      "de_f": 40, "de_r": 34,
      "cam_f": 1.4, "cam_r": 1.0,
      "toe_f": -0.05, "toe_r": 0.10,
      "lsd_i": 5, "lsd_a": 20, "lsd_b": 18,
      "df_f": 150, "df_r": 260,
      "bb": 0,
      "top": 330, "fg": 3.600
    },
    "gears": [2.614, 1.797, 1.400, 1.155, 1.010, 0.921],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

## 9.2 QUALIFYING

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Yas Marina Circuit",
    "sessionType": "qualifying",
    "date": "2026-08-13",
    "gameVersion": "1.70",
    "compound": { "front": "Racing Soft", "rear": "Racing Soft" },
    "assists": { "abs": "Off", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Yas Marina quali v1",
    "values": {
      "rh_f": 78, "rh_r": 97,
      "nf_f": 3.20, "nf_r": 3.35,
      "arb_f": 6, "arb_r": 5,
      "dc_f": 25, "dc_r": 30,
      "de_f": 41, "de_r": 36,
      "cam_f": 1.6, "cam_r": 1.2,
      "toe_f": -0.05, "toe_r": 0.08,
      "lsd_i": 5, "lsd_a": 22, "lsd_b": 16,
      "df_f": 160, "df_r": 275,
      "bb": 0,
      "top": 330, "fg": 3.700
    },
    "gears": [2.614, 1.797, 1.400, 1.155, 1.010, 0.921],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

## 9.3 ⚠️ What the paste block does NOT carry — enter these by hand on the Event screen

The parser reads **`sheetName`, `values` and `gears`. That is all.** Everything else in
the blocks above is there for you to read while pasting. Enter by hand:

- **Compounds** — RM race (hedge), RS quali
- **Assists** — ABS **Off**, TCS **0**, countersteer Off
- **Multipliers** — 2× tyre, 2× fuel
- **Performance adjustment** — restrictor 100%, ECU 100%, **ballast 109 kg at position 0**
- **Event** — 30 min timed, grid start, dry, afternoon, 0 mandatory stops
- **Refuel rate 2 L/s** and **pit loss** — and per §4.2, do not leave pit loss at the
  20 s default. Measure it or set it to 22 s.
- **The slider ranges for this car** — from the brief, marked verified, read
  13 Aug 2026. Once they are in the app's car screen they never need entering again.

---

# 10. Copy this back to me after the session

Paste this into a session in this project once you have run practice. Fill in what you
have; **leave blank what you did not measure — a blank is information, a guessed zero
is a fabrication that gets diagnosed as a real value.**

```
## GT7 SETUP REFINEMENT — Shelby GT350R '16 · Yas Marina · Rev A → Rev B

### Session
Type: [practice / quali / TT / race]   Laps run: ___   Compound: ___
Conditions: dry, afternoon             Setup as run: Rev A race sheet [yes / deviations: ___]

### The numbers I asked for
Tank capacity                      ___ L
Wear + fuel multipliers confirmed  [2x / 2x?  yes / no — actual: ___]
Fuel used per lap                  ___ L
Best clean lap                     ___        Median lap: ___
Pit loss, measured                 ___ s      [or: not measured]

Gearing constant K
  Speed at T8 braking point (clean air, no tow)  ___ km/h
  Rpm at that moment                             ___
  Limiter rpm (only if it actually fired)        ___
  Gear at T5 apex ___  T8 apex ___  T11 apex ___  final corner exit ___
  Any corner where you had to upshift mid-corner: ___

Six-lap RM stint (§5.2)
  L1 ___  L2 ___  L3 ___  L4 ___  L5 ___  L6 ___
  Tyre gauge, worst corner, end of stint: ___%   Which corner/tyre went first: ___

### Test #1 — the exit diagnosis (§7.1) — THIS IS THE ONE I MOST NEED
Out of T7 and T9, which did you see?
  [ ] Inside rear lit up alone, car bogged        → accel 20 → 23
  [ ] Both rears went together, felt like a snap  → accel 20 → 17
  [ ] Pushed wide WHILE ON THROTTLE               → accel 20 → 17
  [ ] Neither — exits were clean
Which exits were FINE? ___

### Symptoms by corner phase — and for each: which corners, and which corners were fine
Braking / trail:   ___
Initial turn-in:   ___
Mid-corner:        ___   (where was your right foot? ___)
Early throttle:    ___
Full-throttle exit:___
Kerbs / bumps:     ___   (hops once / bounces repeatedly / bangs then won't steer?)

Did the rear step out under trail braking?  [yes / no]  Where: ___
Did you have to move brake balance off 0?   [no / −1 at lap ___ / +1 worked!]
Did it develop over the stint, or was it there from lap 1?  ___

### Changes I made and what happened
LSD braking 18 → ___     Result: ___
Accel 20 → ___           Result: ___
Front toe A/B (−0.05 / 0.00 / +0.05) — which gave the bite? ___
Ballast 0 → ___          Result: ___
Anything else: ___

### Priority for Rev B
[ ] Front turn-in   [ ] Rear stability under brake   [ ] Exit traction
[ ] Gearing         [ ] Race strategy / compound     [ ] Kerb compliance
Notes, verbatim: ___
```

---

# 11. What to record in the knowledge base after this session

Per `00-INDEX.md` standing rule 6 — with a date and a game version.

**These are new entries, not corrections. Nothing about this car or this circuit has
ever been measured.**

1. **`11-car-slider-ranges.md` — add the Shelby GT350R '16.** The ranges on this brief
   are read off the car's own screen and verified, which makes it the **second car in
   the register** and the **first road car**. Notable already: NF floor **1.88 Hz**
   against the RSR's 3.00, and ride height floors of **75/95 mm** with **+20 mm of
   rake built into the minimums** — which is a materially different animal and worth
   the register entry on its own.
2. **Gearing constant K and limiter rpm for this car** (§3.5). Closes the same item the
   RSR closed at Monza.
3. **Tyre wear, RM at 2× at Yas Marina, road car.** `08` G2 — and it is the first
   road-car wear datum in the entire knowledge base, which makes it a direct test of
   C4's claim that **road cars are disproportionately punished post-1.49**.
4. **Fuel per lap at 2×, and the tank capacity.** `08` G9-adjacent.
5. **Pit loss at Yas Marina** (§4.2). `08` G10.
6. **Front toe direction on the Shelby** (§7.3). A3's open question, second car.
7. **Whether the A4 stack bought you rear brake bias with no ABS** (§4.5). If you
   finish the race at **+1** on worn rears, that is the strongest evidence A4 has ever
   had, and it comes from the hardest case — no ABS, 5/5 braking severity, a
   1,335 kg car.

---

*Rev A issued 13 Aug 2026 · GT7 v1.70 · no BoP · ranges verified on this car 13 Aug 2026*
*First run of this combination. Race compound is a hedge, not a decision — §5.2 decides it.*
*Three values are estimates and every one is flagged: lap time, fuel per lap, gearing constant K.*
*Driver profile: front-end-led precision attacker · neutral brake bias · low tolerance for rear snap · ABS Off*
