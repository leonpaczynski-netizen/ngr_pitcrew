# Driver — Leon Paczynski

**Started 21 Aug 2026.** The knowledge base has `01-driver-profile-leon.md`, which
covers technique, symptom vocabulary and change hierarchy. **This file is for the
things that were true and written down nowhere** — established in conversation or
by measurement, and until now surviving only in a session's memory.

**Every line carries its source.** Nothing here is inferred from how he drives; it
is either something he said, something measured off his own data, or something a
document already records. Where two records disagree, both are stated.

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

**Never move brake balance forward.**
*Source: session memory, standing.*

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

**Rear-left is his worst-wearing corner** — nine gauge readings, never once a
front. *Eight prior, plus the live OBS sampler on 21 Aug 2026.*

**Short-shifting pays, and the figure is measured in-house.**
−21.6% fuel on v1.71 (`17` §4), −24.9% in an earlier controlled A/B, for about
+0.5 s/lap. **It can remove a pit stop**, which is worth more than the lap time
it costs. Optimum shift point ≈1200 rpm below the limiter; **his own habitual
849 rpm was well judged.**
> The seconds coefficient is the unresolved half and it moves the optimum
> between 400 and 2800 rpm. Measure it with a 1500 rpm separation.

---

## Where the records disagree

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

1. **Job 7a from the 1.71 protocol, and it is now urgent.** 1.71 adjusted
   force feedback, understeer vibration **and Fanatec Auto Setup parameters**.
   `08` and `07` both warn that **on an 18 Nm base an FFB change reads exactly
   like a grip change** — and the first 1.71 session came in 2.5 s off the
   pre-patch median. **Confirm the wheel settings are where you left them
   before diagnosing anything about grip.** Five minutes, and it separates "the
   wheel feels different" from "the car has less grip".
2. Does the fuel-map rule survive 1.71? It was established pre-patch, and 1.71
   changed the torque map. The *rule* is his call either way; the *evidence*
   behind it is now pre-patch like everything else.
