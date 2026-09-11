═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  MICHELIN RACEWAY ROAD ATLANTA (FULL)
  **ROUND 4 SUPERCARS** — race sheet v1
  30 min · timed · 2× tyre / 2× fuel · 0 mandatory stops · standing start · dry, afternoon
  606 bhp cap · 1335 kg minimum · 2.20 kg/hp · no BoP · no PP cap
  109 kg ballast @ 0 · **54 : 46 front/rear** · ABS **Off** (regulation) · TCS **1 (race)**
  **No practice in this car at this circuit. First run on v1.71.**
  Issued 23 Aug 2026 · GT7 **v1.71** · ranges re-read on this car **23 Aug 2026 ✅**
═══════════════════════════════════════════════════════════════════

# 0. Three things you told me today, and what each one moved

| You said | What it changed |
|---|---|
| **"locks rears on braking, I've had to move BB forward"** | The whole sheet. §0.1 |
| **`bb −1`, ABS Off is regulation** | Bias goes back to 0 **by hand**, and `lsd_b` is now your only structural rear tool. §2.3, §6.2 |
| **Ranges re-read; ballast 109 @ 0, 54:46** | `lsd_i` **5 → 0**, quali front wing off a clamp, and every percentage on this sheet. §2.4, §6.1 |

## 0.1 The contradiction that resolved

Rev C recorded **front** lockup at Yas on 9 of 14 laps and concluded `lsd_b` 22
had cured the rear so thoroughly that *"the front is now the limiting axle."*
You say the rear locks. Both are true, and they are one chain:

```
  rear locks under braking  →  you take bias to −1 in the car
                            →  the fronts lock
                            →  Rev C reads front lockup and credits lsd_b 22
                            →  the rear is never actually fixed
```

**One click is not "relying on forward bias"** — it is the fine adjustment around
neutral that `01` §16 explicitly allows, so you have not been breaking your own
rule. But **10% of the bias range with no ABS is not a small lever**, and the app
has never known: every sheet on file says `bb 0`. Fourth consecutive session in
which a value the export presented as fact was silently wrong.

**So `lsd_b` 22 is not a validated setting. It is an unread one** — +4 against a
playbook band of +5 to +15, on a rear-locking item open since 10 August across
two circuits.

---

# 1. The sheet

```
                                    RACE              QUALIFYING
───────────────────────────────────────────────────────────────────
TYRES
  Front compound                    Racing Soft       Racing Soft
  Rear compound                     Racing Soft       Racing Soft

SUSPENSION
  Body height          Front        89 mm · 16% · +14   86 mm · 13% · +11
                       Rear         107 mm · 14% · +12  105 mm · 12% · +10
  Anti-roll bar        Front        5   (44%)         5
                       Rear         4   (33%)         4
  Damping compression  Front        24  (20%)         24
                       Rear         28  (40%)         28
  Damping expansion    Front        40  (33%)         40
                       Rear         32  (7%)   <- CHANGE   32
  Natural frequency    Front        3.05 Hz · 52%     3.05 Hz
                       Rear         3.20 Hz · 60%     3.20 Hz
  Camber angle         Front        1.4°  (23%)       1.4°
                       Rear         1.0°  (17%)       1.0°
  Toe angle            Front        −0.05°            −0.05°
                       Rear         +0.10°            +0.10°

DIFFERENTIAL                        (absolutes — the three axes no longer
                                     share a scale. §6.1)
                                     (absolutes-only rule retired 11 Sep 2026 - `11`)
  Initial torque                    0   <- CHANGE       0      (0–30, at MIN)
  Acceleration sensitivity          17  (17%)         19      (0–100)
  Braking sensitivity               26  <- CHANGE       24      (0–100)

AERODYNAMICS
  Downforce            Front        150  (AT MAX)     150  (AT MAX)
                       Rear         260  (73%)        260

TRANSMISSION
  Max speed setting                 300 km/h          300 km/h
  Final gear                        3.600             3.700
  1st                               2.614             2.614
  2nd                               1.948             1.948
  3rd                               1.560             1.560
  4th                               1.318             1.318
  5th                               1.145             1.145
  6th                               1.019             1.019

BRAKES
  Brake balance                     0  <- CHANGE from the −1 in your car
                                       (− front / + rear)
                                    ↳ trim back to −1 mid-race if the rear still
                                      goes. Never positive here — §2.3.

PERFORMANCE ADJUSTMENT
  Power restrictor                  100%              100%
  ECU output                        100%              100%
  Ballast / position                109 kg / 0        109 kg / 0
                                    ↳ held, not settled — §2.5

ASSISTS
  ABS                               Off  (regulation)  Off
  TCS                               1                 0
```

**Percentages are on the register you read this morning.** Six parameters moved
and they are listed in §6.1.

---

# 2. Deviation notes

## 2.1 ◀ LSD braking sensitivity 22 → 26 — the main event

**GT7 has no engine-braking map, no brake pressure and no diff preload in Nm.
LSD braking sensitivity is your entire off-throttle and on-brake rear-stability
toolkit** — and with ABS Off mandated, it is the *only* structural tool that
reaches the rear axle under braking. The playbook names your Watkins Glen
session — *rear locking with no ABS, brake bias forward rejected as a solution* —
as precisely the problem this parameter exists to solve, and ranks it **#1**.

| Car | `lsd_b` | Bias | ABS | Result |
|---|---:|---:|---|---|
| Huracán, Laguna Seca | **26** | **0** | Weak | heavy downhill stop taken on turn-in — no entry complaint across the programme |
| RSR, Monza | **24** | **0** | Weak | the three heaviest stops in Gr.3 — no complaint |
| **Shelby, everywhere** | **22** | **−1** | **Off** | rear locking, open since 10 Aug |

**The Shelby is the only one of the three that never got the treatment**, and it
is the heaviest, has the least downforce, and is the only one on ABS Off.

**The failure mode on the other side is real:** braking sensitivity too high and
the car refuses to turn in on the brakes — the deep trail-braker's failure. That,
plus the fact that **`lsd_b` is not adjustable mid-race**, is why this is +4 and
not +10.

> ⚠️ **Two caveats, and the second one needs ten seconds in the garage.**
>
> **1. Both validations were run on ABS Weak. Neither on Off.** So 26 is
> doctrine-backed and cross-car validated but extrapolated across the assist
> setting — the one that governs whether a locked wheel stays locked. ABS Off
> argues for *more* braking sensitivity, so the extrapolation points the safe
> way. It is still an extrapolation.
>
> **2. The axis was rescaled and I cannot tell from here whether your saved
> value came with it.** `lsd_b` ran **5–60** and now runs **0–100**. On the old
> scale 22 was 38% of range; 26 on the new scale is 26%. **So in absolute terms
> this is an increase and in proportional terms it is a decrease** — and which
> one is physically true depends on whether GT7 preserved the number or
> rescaled it through the patch.
>
> **Open the differential page and read the three numbers.**
> - **Reads 5 / 17 / 22** → GT7 preserved the absolutes. Type **0 / 17 / 26** and
>   race. This is the expected case; it is what the RSR did.
> - **Reads anything else** → it rescaled, my numbers are wrong, **stop and tell
>   me what it says.** Two minutes and I redo the diff.

## 2.2 ◀ Rear expansion damping 34 → 32 — #2 in the same stack

*A rear that extends too fast on lift unloads abruptly.* **Lower is correct and
counter-intuitive** — it is #2 precisely because it works the same axle as #1
without touching the front. The playbook's standing prescription for this exact
item: *"LSD braking sensitivity up in +2 steps, rear expansion damping down, rear
ride height up from the floor. Brake bias stays at neutral."*

**Rear ride height is already up** — 107 mm against a 95 mm floor. So the sheet
now runs three of that prescription's four parts.

**30 is still the floor** on the new register, so 32 keeps two clicks in hand.
The ceiling moved 50 → 60, which matters only for the front — §2.6.

## 2.3 ⚠️ Brake balance −1 → 0 — a change you have to make by hand

**Your car has `−1` in it. The sheet says `0`. Those have never matched, so you
will not catch it by reading down the column.**

Why: **`lsd_b` 26 is doing the job −1 has been doing, and running both is how you
lock the fronts at T10a.** The Yas race had `lsd_b` 22 *and* bias −1 and produced
front lockup on 9 of 14 laps at T10, costing 369 ms/lap. Raising `lsd_b` moves
the limit further onto the front axle. Stack −1 on top and the front goes first.

**The asymmetry decides it, and it is T10a.** Both errors are recoverable — bias
is one of only two things adjustable mid-race — so the only question is which way
round to be wrong:

| Start at | If wrong | Where it bites |
|---|---|---|
| **0** | rear steps, you take −1 on the MFD | anywhere; a moment you can see coming |
| −1 | fronts lock, you take 0 on the MFD | **T10a — braking on a blind crest, no steering** |

**Front lock at T10a is both the expensive failure and the known one.**

- **If the rear lets go, take −1 back and race.** Legitimate, it is your fine
  adjustment, and **it does not become the sheet** — it becomes a report that
  `lsd_b` needs to go past 26.
- **Never positive here.** A rearward bias over the T10a crest is a spin. Rev C's
  standing offer of +1 for front lockup is **withdrawn for Road Atlanta.**

**The discriminator, one corner:**

| When the rear goes | Cause | Lever |
|---|---|---|
| **On the downshift**, as you release the brake | overrun torque through the diff | **`lsd_b`** — bias cannot reach this and costs you the front |
| **Brake hard on, straight line** | brake distribution | **bias −1** |

## 2.4 ◀ LSD initial torque 5 → 0 — free, and three revisions overdue

**The floor moved from 5 to 0. This sheet has carried initial torque "at minimum,
deliberately" for three revisions — the minimum just moved, so the setting
follows it.** This is not a new experiment; it is the same intent, now reachable.

Preload is the one diff parameter that cannot be aimed at a corner phase — it
opposes turn-in everywhere at once. And the car profile is explicit that the FR
Shelby is the one of your three that benefits most: *"it will not rotate for
free — you have to manufacture rotation with brake bias, front geometry and a
looser entry diff,"* with the note that **if the floor really dropped to 0, "a
looser entry diff" now has somewhere further to go.** It does.

**It also pays for §2.1.** Raising `lsd_b` to 26 costs turn-in; taking preload to
0 gives some back. The two changes push opposite ways on the one axis you are
most sensitive to, which is deliberate.

> ⚠️ **Nobody has run 0 preload on any car.** The floor was 5 until this week. If
> the car feels nervous or darty on the way *into* slow corners — not on the
> brakes, on the initial steer — that is this, and 2 or 3 puts it back.

## 2.5 Ballast 109 kg @ 0 — held tonight, and Rev C was wrong to call it settled

**You are right that this is a lever, and it is a big one.** Rev C dismissed it
as *"correct as built — the regs cap bhp and minimum weight, so there is no trade
to make."* **That reasoning covered the mass and never touched the position.**
With **no PP cap** in this series, most of the knowledge base's ballast material —
which is about buying PP back — does not apply to you at all. **Position here is
purely a handling tool, and it is free.**

**What the slider is worth on your car**, from 1,335 kg at 54:46 with 109 kg
fitted:

```
  109 kg is 8.2% of the car's mass.
  Moving it from the centre to over the rear axle shifts the CG back by
  about 4.4% of the wheelbase:

      position   0  →  54 : 46     (where you are — and it is roughly factory)
      position +50  →  ~50 : 50    estimated
      position −50  →  ~58 : 42    estimated
```

**That is real authority — about ±4 points of distribution.** And the direction
that helps tonight's symptom is rearward: from a 54:46 static split the rear is
already the light end, and braking makes it lighter still, which is a structural
reason the rear locks that **no diff setting can fully cure.**

**Four reasons it does not move tonight:**

1. **Hierarchy.** Ballast is #9 of 10 in your own change order, explicitly *after*
   LSD and suspension — *"always try suspension, LSD and aero first."* Tonight is
   the first ever test of the LSD step.
2. **It would cost me the answer.** If the rear is fixed and I moved two big
   levers, I learn nothing about either — and **the `lsd_b` answer transfers to
   every car and circuit you own, while a ballast position transfers to
   nothing.** That item has been open since 10 August. Tonight is its race.
3. **Springs.** Moving 4 points of distribution changes what each end's natural
   frequency should be (`Kw = 4π²F²M`). Shipping the move without re-checking
   3.05 / 3.20 means shipping mismatched springs, and there is no practice to
   check them in.
4. **⭐ The range re-read removed the compensating lever.** Rearward ballast costs
   front bite, and the standard compensation is more front wing. **Front
   downforce used to be 60–160 with the sheet at 150 — ten points in hand. It now
   reads 50–150 and the sheet is at the ceiling.** There is nothing left to pay
   with. That was true this morning and is not true any more.

**It is test #1, and §5 has the protocol.** The range re-read you did today was
the thing blocking it — the doctrine says *do the ballast sweep after the range
re-read, not before*, and that gate is now open.

## 2.6 Front expansion damping stays at 40 — and I took a change back out

The track reference calls for firm front expansion for the T10a crest, and I had
`de_f` at 43 for it earlier today. **It came out when you reported the rear.**
Firm front rebound with soft rear rebound pitches the car nose-down over a crest
and takes load off the rear — at the one corner it was meant to help, on the axle
you have told me is the problem. **Your report outranks a pre-1.71 track
reference.**

40 is now **33% of range**, not the midpoint it was this morning — the ceiling
moved 50 → 60. So there are 20 points of front expansion headroom above, where
there used to be 10. Noted for when the rear is settled and T10a is the
remaining problem, not before.

## 2.7 Ride height 89 / 107 held — on Road Atlanta's merits, not Rev C's

Rev C's reason was withdrawn: the `bottoming` flag that bought the raise fires on
the most *extended* wheel. **The height survives on two independent grounds** —
Road Atlanta has ~30 m of sharply profiled elevation with blind crests and
compressions and the reference asks for 2–3 clicks up, and rear ride height up is
part three of the rear-lock prescription in §2.2. Rake held at +18 mm. Ranges
unchanged in the re-read.

## 2.8 Downforce 150 / 260 held — and the front is now against the stop

Road Atlanta is **medium** downforce against Yas's medium-high, and two long
straights in a fuel-critical race argue for a trim. **Overruled** — T10a is a
rear-stability event, tonight's sheet is about the rear, and your failure mode is
spins (32.6 s direct plus ~21 s of step-down at Yas). Fifteen points of rear wing
does not buy that back. **The fuel lever on this car is the right foot, not the
drag** — §4.

**The front is at maximum on the new register.** The only aero balance lever left
is the rear, and that is the constraint behind §2.5 #4.

## 2.9 Everything else

Natural frequency, ARB, compression damping, camber, toe, LSD acceleration and
the gearbox are **unchanged from Rev C**. LSD acceleration is still undiagnosed
and still blocked on one observation — §5.

---

# 3. Gearing — held, and with no practice that is a decision

**The risk is asymmetric.** 6th has headroom to **277 km/h**, so if Road Atlanta
tops out lower you are merely under-revved and lose a little. Shorten the final
drive blind and you can arrive at the end of the back straight on the limiter
with a tow, which costs more and cannot be fixed from the seat.

**The constant:** `K = 1096 ± 1%`, twice measured.

```
  v (km/h) = rpm ÷ (final gear × ratio × 8.115)

  check:  8152 ÷ (3.600 × 1.019 × 8.115) = 273.9 km/h   ← measured 273.8 ✅
```

**At the measured upshift points, on fg 3.600:**

| Gear | Upshift rpm (measured) | Tops out at |
|---:|---:|---:|
| 1st | 8500 | 111 km/h |
| 2nd | 8250 | 145 km/h |
| 3rd | 8250 | 181 km/h |
| 4th | 8000 | 208 km/h |
| 5th | 8250 | 247 km/h |
| 6th | — | 277 km/h at 8250 |

- **The esses (T3–T5) should sit on 4th** — 4th runs 145–208 km/h and the
  reference asks that 4th carry them without a shift. It does, **provided you
  arrive below ~208.**
- **T10b onto the back straight is 4th.** No shift on the crest.
- **T7 and T12 exits are 2nd**, into 3rd at 145.

### Read these three things during the race — no practice needed

1. **Speed at the end of the back straight**, and whether 6th ever hits the
   limiter.
2. **Whether you had to upshift inside the esses.**
3. **Gear at the T10b exit.**

**Decision rule:** below **262 km/h** on the back straight, take final gear
**3.700** next time. Above, leave it. If you upshifted in the esses, 4th gets
longer instead.

> ⚠️ **1.71 footnote.** The RSR lost 3.9 km/h of top speed — outside its whole
> 20-session pre-patch spread — and its rpm-per-km/h fell in every gear as
> driven-wheel slip dropped. If the Shelby did the same, `K` reads ~1.5% high in
> 6th. Both push toward 3.700. **Both unmeasured on this car.**

---

# 4. Strategy — the binding constraint is **fuel**

## 4.1 The numbers, and where each came from

| | Value | Source |
|---|---|---|
| Race pace | ~**1:27** (±3 s) | Yas race median 1:59.62 scaled on the Gr.3 reference bands — **estimate** |
| Race distance | **20 laps** | 30 min at that pace — `recommend()` |
| Burn, full revs | ~**5.34 L/lap** | Yas 6.762 L/lap (n=7, unsaved race laps, sd 0.135) scaled per second of racing and by full-throttle share 58% → 63% — **estimate** |
| Fuel needed | **106.8 L** | 20 × 5.34 |
| Tank | **100 L** | |
| Wear | ~**2.3%/lap** | Yas gauge 2.6%/lap at 2×, scaled on relative tyre load — **estimate** |

**You are about 6.8 litres short — roughly 6.4%.**

## 4.2 The call: **no stop. Save the fuel.**

```
  A stop:   20 s pit loss  +  5.3 s dead  +  ~27 L at 1.00 L/s   ≈ 52 s  (0.6 of a lap)
  Saving:   ~10% of the burn, at roughly +0.25 s/lap × 20 laps    ≈  5 s
  ─────────────────────────────────────────────────────────────────────────
  No-stop wins by roughly 45 seconds.
```

**Same shape as Yas**, where the model planned two stops, you declined thirteen
calls, and all thirteen declines were correct. In a timed race with no mandatory
stop, **a pit stop is not a fuel solution — it is time stationary while the clock
runs, paid for in laps.**

You need **~10%** (6.4% plus margin). Measured short-shifting is **−21.6%** for
about +0.5 s/lap, so **roughly half a short-shift discipline** — the pit straight
and the back straight, leaving the esses and T10b alone. Those are the two zones
where fuel per second is highest and the lap-time price is lowest.

> **Your beep is already at 7500 rpm.** Against measured upshift points of
> 8500 / 8250 / 8250 / 8000 / 8250, following the beep *is* a 750–1000 rpm
> short-shift. On the straights you are most of the way there already.

**[ASSUMED]** the −21.6% figure is the RSR's, at Monza on 1.71. Never measured on
the Shelby.

## 4.3 ⚠️ The app will tell you to stop. Do not obey it.

I ran your own strategy model on these inputs. **Its best plan is one stop, and
the reason is neither the tyre nor the tank:**

> *"Stint 1 is 16 laps but only 15 are runnable on RS (evidence-limited)."*

**That is an evidence cap, not a limit.** Fifteen laps is the longest RS stint you
have ever run and the model refuses to plan past its evidence — correct behaviour,
wrong answer tonight. At 20 laps the tyre is at **~45% worn**, inside the flat
phase, against a cliff at ~90%.

**Ignore any box call not backed by a gauge reading.** And **finish 20 laps on one
set and the cap lifts itself** for every future race on this car.

## 4.4 Margin

Lap count is firm on these estimates, so **do not carry a spare lap** — 5 L you
would pay for at 1 L/s. Plan to cross the line with **~2 L**. The model sized
**1.6 L on the long stint**, on a systematic lift rather than a flat lap. Keep it.

## 4.5 Tyres

RS, no stop, no compound decision. Road Atlanta's wear is **front-biased with a
slight front-left lean** — the opposite of your usual rear-left, and consistent
with a 54:46 car. **Read the gauge at lap 10.** Fronts past 30% there and the
estimate is wrong; I want to know before the second half.

No published optimal temperature window exists for GT7. The only credible figure
is **wear onset at 88 °C on RS** — an upper bound, not a window. Watch the fronts
against 88.

## 4.6 With no practice, the first three laps are worth more than the last ten

Your own data, twice: at Yas you did 1:57.318 on lap 3, spun on laps 4 and 5,
**and never went within two seconds of that lap again for the remaining ten.**
The 13 August session has the same signature. **The car does not degrade — the
step-down is you, it starts at the first spin, and it does not come back inside
a race.**

Cost at Yas: 32.6 s of spins plus ~21 s of step-down. **More than this entire
strategy section is arguing about.** Standing start, cold tyres, ABS Off, a
circuit you have never driven this car on, and four changed values you have never
felt. **Bank clean laps first.**

---

# 5. Three things to test first, ranked

**One change per run, three clean laps.**

### ⭐ 1. The ballast sweep — and it needs no track time to start
**Unblocked as of this morning**, because the doctrine says do it *after* the
range re-read and you have now done that.

**In the garage, 30 seconds, no driving:** move the position slider to **+50**,
**−50** and back to **0**, and write down the front/rear percentage GT7 displays
at each. That tells us exactly what the lever is worth on this car instead of my
estimate. **Use the readout — do not guess**, and my ~50:50 figure in §2.5 is
arithmetic, not a measurement.

**Then, on track:** rearward in steps, **+15 at a time**, three clean laps each,
watching for the trade — rear settles under braking, front bite goes away. **Stop
the moment turn-in dulls.** And re-check ride height afterwards: ballast
compresses the car statically.

> **Why this is #1 now rather than #9:** it is the only lever left that adds load
> to the rear axle rather than redistributing what little is there, and **front
> downforce — the usual way to buy the front bite back — is against its stop.**

### 2. `lsd_b` past 26 — in +2 steps, on the driver report only
If the rear still goes on downshifts: **28, then 30.** **Stop the moment turn-in
starts to dull** — the trail-braker's failure mode arrives before any telemetry
sees it. And re-read §2.1's scale caveat first.

### 3. Rear toe-in +0.10 → +0.15
**#3 in the A4 stack**, after §2.1 and §2.2. Cheap and effective; costs a little
top speed and tyre life, which is why it is a trim and not a foundation.

**Natural frequency drops off the list, and the re-read is why.** It was queued on
the observation that 3.05 / 3.20 is *"64% / 63% of range — stiff for a 1,335 kg
road car, with everything below never tried."* **On the new register it is 52% and
60% — mid-window, not stiff**, and the floor rose from 1.88 to 2.00 so there is
less unexplored softness below than there appeared to be. The Sainte-Croix report
that stiffening this car costs grip still stands on its own, but the number that
made this urgent has evaporated.

**And the observation, which is not a change:** on any exit that steps out, watch
the tyre indicators. **One rear wheel alone and the car bogs → `lsd_a` 17 → 19.
Both rears together as a snap → 17 → 15.** T7 and T12 exits. Blocking the
differential since Rev B; one corner answers it.

---

# 6. Before you drive

## 6.1 ✅ The register — done, and six parameters moved

Read on this car **23 Aug 2026, v1.71, verified.**

| Parameter | v1.70 | **v1.71** | What it did |
|---|---|---|---|
| **LSD initial torque** | 5 – 60 | **0 – 30** | ⭐ **floor to 0 → `lsd_i` goes to 0** (§2.4); ceiling halved |
| **LSD acceleration** | 5 – 60 | **0 – 100** | 17 was 22% of range, now 17% |
| **LSD braking** | 5 – 60 | **0 – 100** | ⭐ **26 is +4 absolute but −12 points proportional** — §2.1 |
| **Downforce front** | 60 – 160 | **50 – 150** | ⭐ **150 is now the ceiling.** Quali's 160 was out of range; both columns now read 150 |
| **Damper expansion F/R** | 30 – 50 | **30 – 60** | floor intact, so `de_r` 32 is unaffected; front gains 20 points of headroom |
| **Natural frequency F** | 1.88 – 3.70 | **2.00 – 4.00** | 3.05 falls 64% → **52%**. Killed test #3 — §5 |
| **Natural frequency R** | 2.00 – 3.90 | **2.00 – 4.00** | 3.20 falls 63% → **60%** |

Unchanged: ride height, ARB, compression damping, camber, toe, rear downforce,
brake balance, max speed, final gear.

**Two consequences you would not have guessed:** the quali sheet was carrying a
front wing setting the game can no longer accept, and the single most interesting
untried direction on this car turned out to be an artefact of a stale range.

## 6.2 ABS Off is regulation — closed, and it raises the stakes

**Confirmed 23 Aug.** Weak is off the table, so the largest single rear-lock fix
in the playbook is unavailable in this series. Three consequences this sheet is
built on:

1. **`lsd_b` is not merely your best rear tool, it is your only structural one.**
   No ABS, no engine-braking map — nothing else reaches the rear axle under
   braking except rear damping, rear toe and ballast.
2. **1.71's ABS change does not reach you** (§7). Insulated from the assist
   rework, exposed to the raw tyre model instead.
3. **The 26 figure is extrapolated across the assist setting** — §2.1.

## 6.3 Two fields in the event record are wrong

| Field | Holds | Should be |
|---|---|---|
| `game_version` | **NULL** | **1.71** |
| `refuel_rate_lps` | 2.0, declared | **1.00** — measured twice, at Watkins and Monza |

The refuel rate decides whether a stop is worth taking, and 2.0 makes one look
twice as cheap as it is.

**Regs confirmed** — 606 bhp / 1335 kg minimum / no BoP / **no PP cap**. The build
carries over untouched, and with no cap the gearbox, brake balance, the whole
suspension sheet **and ballast position** are free performance.

## 6.4 Confirm the wheel settings are where you left them

1.71 adjusted force feedback, understeer vibration **and Fanatec Auto Setup
parameters**. On an 18 Nm base an FFB change reads exactly like a grip change,
and this is the Shelby's first run on the new physics. **Five minutes, and it
separates "the wheel feels different" from "the car has less grip."**

---

# 7. What 1.71 does and does not tell us about your braking

You asked, and the honest answer is short: **braking grip is the single
least-measured thing on v1.71.**

- **Measured:** driven-wheel slip under power fell **40–60%** on the RSR, top
  speed fell 3.9 km/h, the limiter did not move, short-shifting still saves
  ~21.6%. **All longitudinal, all under power.**
- **Explicitly not established:** *"cornering grip, braking grip and the limit of
  adhesion are separate questions and none of them were measured."*
- **1.71 adjusted ABS slip-ratio control and cornering brake behaviour** — the
  exact phase your problem lives in. **With ABS Off that does not reach you**,
  which cuts both ways: insulated from the assist change, running on the raw tyre
  model, which is the part that was reworked.

**So tonight is the measurement.** If the rear behaves differently from Yas, the
sheet changed *and* the physics changed, and I will not separate them from one
race — which is why §5 is sequenced one change at a time afterwards.

---

# 8. Confidence flags

| Claim | Status |
|---|---|
| Rear locking under braking | **[DRIVER REPORT — primary evidence]**, 23 Aug |
| Bias **−1** in the car; ABS Off is **regulation**; ballast 109 @ 0, **54:46** | **[DRIVER REPORT]**, 23 Aug. Every sheet on file says `bb 0` |
| Slider ranges | **[MEASURED — IN HOUSE]** 23 Aug, v1.71, verified ✅ |
| `lsd_b` 26 and `de_r` 32 | **[DOCTRINE]** — A4 stack #1 and #2, validated on two other cars at bias 0, **both v1.70 and both ABS Weak** |
| `lsd_i` 0 | **[INTENT CARRIED]** — the sheet has wanted minimum for three revisions; the minimum moved. **Nobody has run 0 on any car** |
| Whether 26 means what 22 meant | **[UNRESOLVED]** — the axis was rescaled. Ten seconds on the diff screen settles it, §2.1 |
| Ballast authority ~50:50 at +50 | **[ARITHMETIC]** — not measured. Read it off the screen, §5 |
| Ride height, ARB, camber, toe, NF, gearbox | **Carried from Rev C — never driven** |
| Lap time ~1:27, burn ~5.34 L/lap, wear ~2.3%/lap | **[ESTIMATE]** — scaled from Yas, no Road Atlanta data exists |
| Short-shift saving −21.6% | **[ASSUMED]** — RSR at Monza, not this car |
| `K = 1096` | **[MEASURED ×2]** on v1.70, may read ~1.5% high on 1.71 |
| Upshift points 8500/8250/8250/8000/8250 | **[MEASURED]** — 36 laps, v1.70, Rev A ratios |
| Braking grip on v1.71 | **[UNMEASURED]** — by anyone, on any car. §7 |

---

# 9. Pit Crew paste blocks

**Race first. One at a time, into the paste box on the Event screen.**

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
    "sheetName": "Road Atlanta race v1",
    "values": {
      "rh_f": 89, "rh_r": 107,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 4,
      "dc_f": 24, "dc_r": 28,
      "de_f": 40, "de_r": 32,
      "cam_f": 1.4, "cam_r": 1.0,
      "toe_f": -0.05, "toe_r": 0.10,
      "lsd_i": 0, "lsd_a": 17, "lsd_b": 26,
      "df_f": 150, "df_r": 260,
      "bb": 0,
      "top": 300, "fg": 3.600
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "Ford Shelby GT350R '16",
    "circuit": "Michelin Raceway Road Atlanta - Full Course",
    "sessionType": "qualifying",
    "date": "2026-08-23",
    "gameVersion": "1.71",
    "compound": { "front": "RS", "rear": "RS" },
    "assists": { "abs": "Off", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "2x", "fuel": "2x" }
  },
  "setup": {
    "sheetName": "Road Atlanta quali v1",
    "values": {
      "rh_f": 86, "rh_r": 105,
      "nf_f": 3.05, "nf_r": 3.20,
      "arb_f": 5, "arb_r": 4,
      "dc_f": 24, "dc_r": 28,
      "de_f": 40, "de_r": 32,
      "cam_f": 1.4, "cam_r": 1.0,
      "toe_f": -0.05, "toe_r": 0.10,
      "lsd_i": 0, "lsd_a": 19, "lsd_b": 24,
      "df_f": 150, "df_r": 260,
      "bb": 0,
      "top": 300, "fg": 3.700
    },
    "gears": [2.614, 1.948, 1.560, 1.318, 1.145, 1.019],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 109, "ballastPosition": 0 }
  }
}
```

**A clean paste reads "22 of 23 settings, 6 gears" with nothing unrecognised.**
`awd` is omitted deliberately — the car is FR.

**These blocks do not carry:** compounds · assists · multipliers · ballast,
restrictor and ECU · event format, length and weather · the slider ranges. All
still typed by hand on the Event screen.

> **The event row records a standing start and no qualifying session** — you left
> that line blank, so that is the assumption. **The quali column is not needed
> tonight.** It exists so the two sheets do not drift, and for a future time trial.

---

*Issued 23 Aug 2026 · GT7 v1.71 · no BoP · no PP cap · Round 4 Supercars*
*Four values change: `lsd_b` 26, `lsd_i` 0, `de_r` 32, and `bb` back to 0.*
*Three of them are one family — the rear axle under braking.*
*`de_f` 43 was on this sheet this morning; your report took it back off.*
*Read the diff page before you type — the LSD axis was rescaled. §2.1.*
*Ballast is a real lever, Rev C was wrong to close it, and it is test #1 — §2.5.*
*Fuel binds by ~6%. The answer is the right foot, not the pit lane.*
