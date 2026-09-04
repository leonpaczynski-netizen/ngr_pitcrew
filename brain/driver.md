# Driver — Leon Paczynski

**Started 21 Aug 2026.** The knowledge base has `01-driver-profile-leon.md`, which
covers technique, symptom vocabulary and change hierarchy. **This file is for the
things that were true and written down nowhere** — established in conversation or
by measurement, and until now surviving only in a session's memory.

**Every line carries its source.** Nothing here is inferred from how he drives; it
is either something he said, something measured off his own data, or something a
document already records. Where two records disagree, both are stated rather
than reconciled by preference.

> ⚠️ **Needs his review.** Assembled from session memory and measurement, not
> dictated. Anything wrong here is wrong in the app's advice too.

---

## Non-negotiables

**Fuel map 1, always. Never recommend a map change.**
*Source: driver, 21 Aug 2026 — "I only ever run fm1". Previously established as
tested: other maps lose more lap time than they save.*
This is not a preference to be re-litigated each race. GT7's map 6 anomaly
(≈50% consumption for ≈80% power) makes a map recommendation superficially
attractive, and `02` §9.6 calls fuel map "the primary endurance-strategy lever" —
**for this driver it is not a lever at all.** His fuel levers, in order:
**short-shift → lift-and-coast → slipstream.**
*All three events on file now declare map 1, and all 333 recorded laps carry it.*

**Raising ride height is a LAST resort, never a first.**
*Source: driver, 31 Aug 2026 - "don't ever recommend high ride height again in
GR3 it must be solved differently with suspension" - and 1 Sep 2026,
"increasing ride height should be a last option not a first."*
If the platform sinks into the ground under load the order is **spring rate,
then compression damping, then ride height.** On the Huracan at Spa I raised
the car 68/77 -> 73/82 to stop Raidillon bottoming and **never once touched
`nf_f`/`nf_r` in the whole programme**; a reference car in the same race ran
**55/62 on springs of 3.90/4.10 against our 3.55/3.70.** Being soft is why ours
had to be high, and being high is what cost every sustained high-speed corner.
**Dampers control how fast the platform moves; springs control how far it
sinks. They are not substitutes.**
⚠️ **This does not suspend the bottoming check** - it changes the response to
it. Guard at Spa: minimum body height at 1,000-1,150 m and full throttle
through 1,000-1,250 m.

**And he does not want anyone's sheet copied wholesale.**
*Source: driver, 1 Sep 2026 - "I don't want to ditch our setup completely I
want you to learn from what he did and apply it to my driving style."*
A reference car is evidence about **principles and directions**, not a sheet to
paste. Take the platform logic; keep what his own style needs.

**Never move brake balance forward.**
*Source: session memory, standing.*
Front bias is wrong for his style specifically — **it locks the fronts and
creates understeer**. He controls rear lock with **LSD braking sensitivity**
and rotates on brake release. `08` A4 is the stack; `01` §16 states the
resolution as *"mechanical rear stability first, then brake balance around
neutral as a fine adjustment."*

> ⚠️ **23 Aug 2026 — he has been running `bb −1` in the car, and nothing on
> file records it.** His words: *"car has a tendency to lock rears on braking
> and I have had to move BB forward"*, magnitude confirmed as **one click**.
>
> **One click is not a violation of the rule above** — `01` §16 permits exactly
> this: *"mechanical rear stability first, then brake balance around neutral as
> a fine adjustment."* Record it as the fine adjustment, not as a lapse. But
> 10% of the bias range **with ABS Off** is not a small lever, and it has two
> consequences that were not being drawn:
>
> 1. **It explains the Yas front-locking finding.** Rev C recorded front lockup
>    on 9 of 14 laps at T10 and credited `lsd_b` 22 with curing the rear so
>    that *"the front is now the limiting axle."* Forward bias he had dialled
>    in himself is the simpler explanation, and it is the exact failure this
>    file names. **The rear was probably never cured.**
> 2. **The app's brake balance is wrong, for the fourth consecutive session** —
>    after `ballastPosition`, the compound, and the whole `setup.values` block.
>    Every sheet on file says `bb 0`.
>
> **Ask what bias is actually in the car before reading any braking telemetry
> off this driver.** `lsd_b` has never been taken past 22 against an A4 band of
> +5 to +15.

> ⚠️ **24 Aug 2026 — the Huracán is running `bb +1`, one click REARWARD, and no
> sheet records that either.** Rev D (sheet 19) says `bb 0`. Two cars, two
> different trims, both undocumented, opposite directions: the Shelby at −1 for
> rear lock, the Huracán at +1.
>
> **This makes the Watkins front-lock finding stronger, not weaker.** Over 8,906
> braking frames in the 17 Aug race the fronts fell below 0.90 slip on **20.2 %**
> and the rears on **0.5 %** — and that was measured with the balance *already*
> one click rearward. At `0` it would be worse. **Fuji's "brake bias one click
> forward" doctrine (`05` §1.12) must not be applied to this car**, and if T1
> locks the fronts the room is at `+2`, not the other way.


**ABS Off is a Supercars regulation, not a preference.**
*Source: driver, 23 Aug 2026.*
Both Supercars rounds on file declare Off; every other series he runs declares
Weak. **So `08` B3's "ABS Weak is the competitive meta" is unavailable in this
series, and A4's rear-stability stack is the only structural route to a stable
rear** — there is no engine-braking map, no brake pressure, and now no assist.
**Both of A4's validations (Huracán 26, RSR 24, each at bias 0) were run on ABS
Weak.** Nothing in the knowledge base has ever tested that stack on Off, which
is the setting that governs whether a locked wheel stays locked. `01` §47 —
*"when ABS is off, rear stability becomes even more important"* — is now a
standing condition of this series rather than an occasional one.

**He will not carry a spare lap of fuel in a lap race.**
*Source: driver feedback, recorded. 6.31 L left at the flag is 6.3 s stationary at
1 L/s — and a battle instead of a 6 s gap.*
Margin in a lap race is sized on measured burn scatter. In a timed race the
spare lap is kept **only** while the lap count is not firm. **Any conservatism
must be priced in his units — seconds — and said out loud.**

**Trail-brakes deep, by design. Low or no assists.**
*Source: `CLAUDE.md` §2. In practice ABS Weak, TCS 0–1 on the Gr.3 cars.*
Deep trail-braking is a technique, not a symptom. Do not diagnose it as one.

---

## What his data can and cannot show

**Lap-to-lap noise is σ ≈ 0.918 s, so the degradation detection floor is
≈1.74 s/lap** — *above the entire 0.5–1.5 s/lap degradation band*.
*Source: measured across 154 laps.*
**Consequence: lap time can confirm degradation but can never warn of it.** It
fired zero times in 154 laps. When the app is silent on wear it must say
*"silence means I can't see them"* rather than let silence read as "nothing
happening". **Never route a lap-time trigger through `recommend()`.**

*Circuit-dependent: σ is 2.04 s at Yas Marina and ~0.7 s at Monza, so the floor
moves with the track. At Watkins Glen (σ 0.68 s) lap time genuinely can carry
degradation.*

**Rear-left is his worst-wearing corner once wear has developed** — but the
flat "never once a front" this file carried on 21 Aug was **wrong, and the
database refutes it.** Of 45 four-corner readings on file, **5 have a front
worst**: FL/FR 0.18 vs RL/RR 0.13, 0.15 vs 0.10, and three more.

*Every one of them is early-stint and low: the largest is 18% worn.* So the
honest statement is that the rears take over as the stint develops, and a
front-worst reading in the first laps of a set is normal rather than a
contradiction. It matters because an axle-asymmetry conclusion drawn from lap 2
of a stint would be drawn from the part of the stint where it does not hold.

*Source: 45 readings across driver reports and the OBS sampler. The earlier
claim came from counting only the readings somebody had written down.*

**Short-shifting pays, and the figure is measured in-house.**
−21.6% fuel on v1.71 (`17` §4), −24.9% in an earlier controlled A/B, for about
+0.5 s/lap. **It can remove a pit stop**, which is worth more than the lap time
it costs. Optimum shift point ≈1200 rpm below the limiter; **his own habitual
849 rpm was well judged.**
> The seconds coefficient is the unresolved half and it moves the optimum
> between 400 and 2800 rpm. Measure it with a 1500 rpm separation.

---

## Hardware facts that were unclear and now are not

**The wheel base — settled 21 Aug 2026, and it was never a hardware
disagreement.** He runs a **Fanatec DD Extreme (18 Nm) with ClubSport V3
pedals** — his own words, and what `CLAUDE.md` §2 and `00-INDEX.md` say.
`docs/WHEEL-AND-PEDALS_2026-08-16.md` §8 records that the base's own tuning
menu, photographed on 17 Aug, reads **`CLUBSPORT DD+ WHEEL BASE`**.

**Both are right. It is one 18 Nm direct-drive base under two names**, and the
functional readings taken off that menu stand: **FullForce (`FUL`) is present**
— which is what he feels dirty air through, and which the feed can never render
because it carries no proximity or aero channel — and **`SHO` is absent, so the
rim has no shaker motors.** Nothing about what the rig can render changes.

*Recorded rather than deleted because the earlier note had it as a
contradiction and concluded the documents were wrong. They were not, and a
naming difference is not grounds to discard a photograph.*

**FullForce stays on.** He feels dirty air through it, and the telemetry feed has
no proximity or aero channel — so the ButtKicker can never render that cue. **GT7
Sensitivity 9 is load-bearing for it: never lower it. Max Torque yields instead.**
*Source: session memory, driver-confirmed.*

---

## Hardware, as it bears on advice

- PS5, **sometimes PSVR2**. In VR GT7 draws its HUD **on the car's dashboard in
  3D**, so it moves with head position — measured 21 Aug 2026. Anything that
  reads the screen must locate the gauge per frame, not by fixed geometry.
- ClubSport V3 pedals, **load-cell brake**, hydraulic throttle damper.
- ButtKicker on a WASAPI **shared** stream; exclusive mode renders nothing.

---

## Open questions for him

1. ~~**Job 7a from the 1.71 protocol.**~~ **✅ ANSWERED 1 Sep 2026, after eleven
   days open. Driver: "Fanatec auto setup is not on in GT7, I am running FFB 5
   and sensitivity 10."** Auto Setup being OFF is the decisive half: 1.71's
   *"Fanatec Auto Setup parameters optimised"* pushes values to the base only
   when it is enabled, so **it cannot have changed his wheel without him.** The
   two in-game sliders are user settings and are now recorded, so the next
   patch is diagnosable. ⚠️ **What this does NOT close: 1.71 also adjusted
   "understeer vibration", which is game behaviour rather than a user setting
   and cannot be ruled out from the settings screen.** But it was already
   demoted by the team mate running the same car flat through Blanchimont -
   a wheel setting cannot make a rival's car faster. **The car is genuinely
   going wide; that is measured. Treat FFB as closed unless new evidence
   reopens it.**

   *Superseded text, kept per the reconciliation rule:*
   **Job 7a from the 1.71 protocol, and it was urgent.** 1.71 adjusted
   force feedback, understeer vibration **and Fanatec Auto Setup parameters**.
   `08` and `07` both warn that **on an 18 Nm base an FFB change reads exactly
   like a grip change** — and the first 1.71 session came in 2.5 s off the
   pre-patch median. **Confirm the wheel settings are where you left them
   before diagnosing anything about grip.** Five minutes, and it separates "the
   wheel feels different" from "the car has less grip".
2. Does the fuel-map rule survive 1.71? It was established pre-patch, and 1.71
   changed the torque map. The *rule* is his call either way; the *evidence*
   behind it is now pre-patch like everything else.
