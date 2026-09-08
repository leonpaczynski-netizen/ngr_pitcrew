# What every axis does on the Huracán GT3 '15 — the car, not the circuit

**⛔ NO SETUP VALUE MAY BE WRITTEN IN THIS FILE.** Values live in
`brain/car-state/<car>-<circuit>.md` and nowhere else (`CLAUDE.md` §1a). This file holds
**verdicts about direction** — what moving an axis does to this car — which is a different
thing and which is the half that travels between circuits.

**Why it exists.** On 8 Sep 2026 a full day of setup work produced eleven findings about this
car, and every one of them was written into `huracan-daytona.md` — a file that stops being
read the moment the series leaves Daytona. Round 7 is Mount Panorama on 14 Sep and Round 8 is
Monza on 21 Sep. **The circuit half expires; this half does not.**

All measurements v1.71. Anything dated before 20 Aug 2026 is void.

---

## The standing facts about this car

| | measured |
|---|---|
| ⭐ **Mid-corner is FRONT-limited** | Off both pedals, the front tyres slip **about twice** what the rears do — front +0.021 to +0.029, rear +0.010 to +0.018 — **at every corner, in every one of six setups tested.** This is the car's defining weakness and it did not move all day. |
| **Exits are traction-limited, not lock-limited** | Both rear wheels spin **together** on exit; the wheel-speed split is a median of 0.0000. The rear axle is at its limit, not misdistributing. 1 Sep, 2,727 + 2,869 frames. |
| **Rear-right is the tyre that ends the stint** | 1.75× the front-left. Consistent across every Daytona session. |
| ⚠️ **Positive yaw and positive steering are a LEFT turn** | Calibrated on load, not on prose — see `reference_gt7_yaw_and_map_orientation` in memory. |

---

## The axis register — direction, verdict, evidence

| axis | direction | verdict | what actually happened |
|---|---|---|---|
| **`rh` rake** | less positive (rear down) | ✅ **CONFIRMED** 8 Sep | 12 mm → 6 mm. Driver: *"so much better."* Two of the three fastest laps on file followed. ⛔ **Its entry-stability rationale was REFUTED** — Turn 1 catches went 8-in-31 → 5-in-15, no change. It won on pace and feel, not on the argument I sold it with. **The reading that found it was percent of range** (12 % front against 33 % rear), not millimetres. |
| **`arb_r`** | stiffer | ✅ **CONFIRMED** 8 Sep — the best change of the day | 4 → 6. **Sector 2 median 36.233 → 35.784 with sectors 1 and 3 unmoved**, and the two fastest S2s in the archive. Driver: *"the best it has."* ⭐ **Apex speeds did NOT change** — the gain is in the drive out. It did **not** worsen the kerbs (grass 3-in-9 against 9-in-17). |
| **`arb_f`** | softer | ⛔ **CLOSED. Refuted twice.** Spa 31 Aug, Daytona 8 Sep | 5 → 3. Driver: *"less pointed, more slidy, not as responsive."* It **added 1.5–3.6 mm of roll at BOTH ends and barely moved the front/rear ratio** — it did not shift the balance, it just let the car fall over. ⇒ **this car wants LESS roll, not more.** Do not propose it again. |
| **`lsd_a`** | **down** | ⛔ **REFUTED — backwards to the textbook** 8 Sep | 14 → 8 gave **less** rotation on power, not more. On-power index at his T5 0.00724 → 0.00554 against a 0.00104 floor; driver said it first. |
| **`lsd_a`** | up | ~ direction real, magnitude not | 8 → 20 is monotonic and clears the floor, but **14 → 20 is inside it.** All the gain lives between 8 and 14. Driver prefers the higher end; the instrument cannot separate them. |
| **`lsd_b`** | up | ⛔ **REFUSED — the price is far too high** | 35 → 40 **halved entry rotation at Turn 1** (0.01197 → 0.00485) and cost mid-corner rotation at all three corners by 2–3.6× their floors. It **does** kill the rear brake lock (0-in-5 against 2-in-15). Not worth it. Driver called it before the numbers did. |
| **`de_r`** | up | ⛔ **REFUTED** 8 Sep, n=2 | 44 → 52. *"Lost rotation on throttle, no change in T1."* He did two laps and came in. The rear brake lock came **back**. |
| **`dc`** | softer | ⛔ **FALSIFIED at the Bus Stop** 4 Sep | 28/26 → 20/20 made the body swing **worse** (32.3 mm against 30.5). ⭐ **The driver says it is fixed and the disagreement stands unaveraged.** |
| **camber, front** | either way | ⛔ **Nothing measurable on the front** 4 Sep | 1.0 ↔ 4.0 moved front surface temperature by 0.4 °C. ⚠️ **Camber is a RIDE-HEIGHT lever here — 2.8 mm per degree** — so every camber change is a platform change and will disturb a settled rake. |
| **camber, rear** | up | ⚠️ costs exit traction | 4.0 raised rear slip >1.05 on exit at all four zones. `[DERIVED]`, one run. |
| **`df` front/rear** | either way | ⛔ **Invisible** 4 Sep | ±25–50 clicks is **3–6 % of the total aero load**. Nothing moved except GT7's own static readout. |
| **`toe_f`** | toe-out | ⚠️ held, not refused | −0.08 → 0.00 on 3 Sep removed a front left/right braking asymmetry (0.0428 → inside the floor) and **that fix is holding.** Going back risks re-introducing it. The last unspent front-grip lever. |
| **`bb` forward** | — | ⛔ **REFUSED, and now with a number** | His fronts already lock past the ABS point under braking — Turn 1 front slip minimum a **median 0.878** against an RS working point of 0.92–0.935. Forward makes that worse. **His trim to make; mine to record, never to correct.** |
| **short-shifting** | — | ⛔ **Not worth it unless it deletes a pit stop** | Fuel +3.458 L per 1000 rpm; lap −6.767 s per 1000 rpm. Break-even needs `litres per 1000 ÷ refuel rate > seconds per 1000`. See `reference_shortshift_daytona_vs_monza`. |

---

## The instruments, and what each one can and cannot see

**Build these before arguing about a change. Every floor is measured by splitting one session's
own clean laps odd/even — same car, same day, same tyres.**

| instrument | what it answers | floor |
|---|---|---|
| **on-power rotation index** — median \|yaw\| per degree of lock, throttle >60 % | does it rotate on the throttle | T3 exit **0.00058** · T5 exit **0.00104** |
| **mid-corner rotation index** — same, off both pedals | does the nose bite in the middle | T1 **0.00086** · hairpin **0.00027** · T5 **0.00026** |
| **entry rotation index** — same, brake ≥20 % | does it turn in on the brake | **0.0033** (4 Sep) |
| **roll** — front and rear left/right suspension split through a corner | is the car falling over | — |
| **Turn-1 counters** — opposite-lock frames, and frames with rear slip below 0.90 | is the back end going, and is it the brakes | — |
| **road position** — kerb and grass rate per corner exit | is he running out of road | — |
| ⛔ **rear wheel-speed split** | **NOTHING about the differential.** It sat at 0.0000 through a six-click change while the rotation index moved twice its floor. It refuted `lsd_a` for a week and should not have. | — |

⚠️ **And a null on a derived index does not outvote the driver plus an outcome measure.** The
`arb_r` change was invisible to every rotation index I had and showed up as half a second of
sector time and *"the best it has."* Both witnesses were right and the instrument was blind.

---

## What to do first at a NEW circuit with this car

1. **Range record, and read the sheet in percent of range** — front against rear, looking for
   an asymmetry. That is what found the rake.
2. **Draw the map** — `tools/draw_track_map.py`, corners named from the league hub.
3. **Mid-corner will be front-limited.** Start from that; it has been true in every setup.
4. **The pre-race pass on that weekend's own practice laps, before the green.** See
   `feedback_debrief_the_practice_before_the_green`.
5. ⚠️ **Mount Panorama, 14 Sep:** the track reference says *"avoid aggressive rake; pitch
   sensitivity over Skyline is dangerous"* — **the same direction we reached from lap times,
   by a different argument.** But Bathurst is bumpy with big crests and will want more
   clearance, which pulls the other way on ride height. **Settle that tension first.**
