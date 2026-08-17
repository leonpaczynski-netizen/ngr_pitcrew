# Wheel and pedal settings — what is measured, what is reasoned, what is guessed

Written 16 Aug 2026, after the ButtKicker and wind sim were tuned against
recorded laps. Companion to `HAPTICS_2026-08-16.md`.

Rig: Fanatec DD Extreme (18 Nm, per `CLAUDE.md` §2), Porsche-branded CSL rim,
ClubSport V3 pedals with load-cell brake, PS5, sometimes PSVR2.

**Read the first section before the recommendations.** The recommendations are
weaker evidence than everything else in this repo and the document says so
rather than hiding it.

---

## 1. The honest boundary: GT7 broadcasts no force-feedback channel

Not in any of the four packet formats. `CLAUDE.md` §3.2 lists what the feed
carries and force feedback is not on it — there is no wheel torque, no rack
force, no clipping indicator, no FFB signal of any kind.

**So nothing in Pit Crew can measure, validate or optimise a force-feedback
setting.** Every FFB number below is a starting point to be tested in the
seat, not a measurement, and it is labelled as such. This is the same rule the
haptics work runs under, applied honestly to a place where it bites: the rig
was tunable because the transducer's input is generated here and its output
was measurable at the amp. The wheel's input is generated inside the PS5 and
nothing observable comes back.

What the feed **does** carry that bears on the wheel and pedals is the
driver's own inputs: steering angle, throttle and brake. Those are measured
below.

---

## 2. What was measured, from his own laps

### 2.1 Steering (129 laps, 893,870 frames, 248 minutes)

| statistic | value |
|---|---|
| median \|steering\| | 0.020 of channel full scale |
| p75 | 0.137 |
| p90 | 0.310 |
| p95 | 0.403 |
| p99 | 0.751 |
| frames beyond 50% | 2.98% |
| frames beyond 70% | 1.31% |
| frames beyond 90% | 0.39% |

Steering **rate**, in fractions of full scale per second: median 0.030,
p90 0.306, p99 1.15, p99.9 2.70. He is smooth — which is what his own driving
profile claims ("deliberate and relatively smooth, dislikes sawing at the
wheel") and this is the first time it has been measured rather than asserted.

**⚠️ The scale is not the rim.** `steering_norm` is normalised by π, not by
the wheel's physical rotation — measured and recorded in
`reference_gt7_extended_packet_offsets`. So "0.403 at p95" is 40% of the
packet's ±π range and **not** 40% of his rim's travel. Until that mapping is
established this measurement **cannot** justify a rotation (SEN) change, and
no recommendation below rests on it. What it does support is the shape of his
input: mostly small, rarely large, never frantic.

### 2.2 Brake pedal (recent sessions 35–41, 12 laps, 95,343 frames)

- Brake applied on **16.4%** of frames.
- While braking: p50 **49%**, p75 **91%**, p90 and above **100%**.
- **20.1% of all braking frames sit at 100% pedal** — the load cell is at full
  scale for a fifth of his braking.
- Throttle is at 100% on 60.3% of all frames.

---

## 3. The division of labour, now that the seat and the fans carry information

This is the part worth thinking about, and it is reasoning from measured rig
facts rather than a measurement itself.

Before the rig work, the wheel was the only channel carrying information about
what the car was doing. It no longer is. Measured and pinned in `synth.PROFILE`,
the transducer now carries:

| band | what it says |
|---|---|
| 28–34 Hz | engine, revs |
| 34–41 Hz | road texture and surface |
| 40–50 Hz | brake regulation past the optimum, and a lock (7–16 Hz pulse) |
| 50 Hz | gearshift, rev limiter |
| 52–60 Hz | kerb strike, sausage double-tap, landing, impact |
| 56–66 Hz | chassis load, in g |
| 86–104 Hz | rear traction: working, sliding, gone |

and the wind sim carries road speed.

**That is most of the high-frequency information load the wheel used to be
asked to carry through vibration.** What is left for the wheel is the thing
only the wheel can do: **self-aligning torque** — where the front axle is on
its grip curve, felt as weight in his hands. For a driver whose whole
technique is trail-braking on the front axle, that is the signal worth
protecting.

Three consequences follow, in descending order of confidence:

1. **Rim shaker/vibration motors are now pure duplication.** If the rim has
   them, the ButtKicker does the same job with 150 W and a measured band, and
   the two disagree in timing. Turn them off (`SHO` 0 on Fanatec firmware).
   This is the one change here that is a straight deduction rather than a
   preference — two devices reporting the same event is the fault the whole
   one-piston mixing discipline exists to prevent.
2. **High-frequency FFB detail is now partly redundant and costs the torque
   signal.** Every kerb jolt through the rack is both a second report of what
   the seat just said (kerb strike, double-tap) and a masker of the
   self-aligning torque underneath it. Moderate rather than maximum effect
   sharpness (`FEI`).
3. **Damping, friction and inertia mask exactly what the wheel is now
   specialised for.** `NDP`/`NFR`/`NIN` low, so the low-frequency torque
   information stays legible. His profile wants front bite and feel.

---

## 4. Starting points — NOT measurements

Verify the menu names against the firmware actually on the base; Fanatec has
renamed and re-scoped these across revisions. **Change one at a time.**

### In GT7 (PS5), Options → Controllers
GT7 exposes two force-feedback numbers only: **Max Torque** and
**Sensitivity**. On an 18 Nm base the base's own gain is usually the better
place to set level, because GT7's Max Torque interacts with per-car scaling.

### On the base (tuning menu)
| setting | starting point | why |
|---|---|---|
| `SEN` | AUTO | lets GT7 set rotation per car — a Gr.3 and a road car do not share a lock |
| `FFB`/`FF` | well under 100 | 18 Nm is far more than GT7's signal needs; headroom prevents clipping, and clipping is the one FFB fault that destroys information rather than changing taste |
| `NDP` | low | damping masks the torque signal the wheel is now specialised for |
| `NFR` | 0 to low | friction dulls exactly the front-axle feel he tunes cars around |
| `NIN` | low | inertia slows the return the trail-braker reads on release |
| `INT` | low | smoothing costs detail the seat can no longer compensate for |
| `FEI` | moderate, not maximum | see §3.2 — the seat now owns the sharp transients |
| `SHO` | **0** | §3.1, straight duplication of the ButtKicker |
| `BRF` | see §5 | measured argument below |

---

## 5. The one pedal setting with measured evidence behind it

**20.1% of his braking frames are at 100% pedal.** Above full scale there is
no modulation left — and the top of the brake range is precisely where
trail-braking happens for this driver.

The corroboration is in the same database: replayed through the real model,
session 41 (Shelby, Yas) produced **525 front-lock and 390 rear-lock frames**
against 23 and 8 for the Porsche at Monza. He is reaching and passing the slip
peak often. `vehicle.BRAKE_OPTIMUM` is 0.105 slip, measured, and past it GT7
gives up 12.4% of braking force.

**Hypothesis worth testing: raise `BRF` so 100% needs more force**, which
spreads the deep-braking region across more pedal travel and buys resolution
where he is currently pinned. This is an inference from two measurements, not
a measured result — the measurements say he saturates and he over-slips, not
that the pedal is why.

---

## 6. How to make any of this measured rather than felt

The rig was tuned by replaying recorded laps and reading numbers, never by
feel (`project_rig_response_and_replay_tuning_2026_08_16`). The wheel cannot
be tuned that way — no FFB channel — **but its effect on his driving can be**,
because the app already measures the outputs that a good setting should move:

- **lock frames per lap**, front and rear, from `VehicleModel` — fewer, for the
  same lap time, is a better brake setting
- **frames past `BRAKE_OPTIMUM`** — the 12.4% braking force he is giving away
- **steering rate p99 and reversal count** — a wheel he is fighting shows up as
  more correction, and his baseline is now recorded (§2.1)
- **lap-time consistency** — the spread, not the best lap

Protocol, borrowed from the bench sessions where the method lessons were
learned the hard way:

1. Change **one** setting.
2. Run a fixed number of laps at the same circuit, same car, same fuel.
3. Re-run the previous setting as a **control** before concluding anything —
   a known-good stimulus re-tested is what caught a dead audio path being
   mistaken for a frequency cutoff.
4. Compare the four measurements above, not the memory of how it felt.

---

## 7. What remains unknowable

- Force feedback strength, clipping, latency or quality — no channel, ever.
- Whether a given `FEI`/`NDP`/`NIN` value is "right" — taste, measurable only
  through its effect on his driving (§6).
- The mapping from `steering_norm` to physical rim degrees (§2.1) — knowable,
  not yet known; a bench test with the rim at known positions would settle it
  and would unlock rotation advice.
- Pedal force in newtons. The feed gives 0–255 of travel-or-force as GT7
  interprets it, not what his leg is doing.

---

## 8. Exact values — added 17 Aug 2026 from a photograph of the tuning menu

The base self-identifies as **CLUBSPORT DD+ WHEEL BASE**, not "DD Extreme" as
`CLAUDE.md` §2 records. Worth reconciling; the headroom argument in §4 is
unchanged either way, but the DD+ has **FullForce** (`FUL`), which §3–§4 did not
account for and which changes one recommendation materially.

**`SHO` is absent from the tuning page.** On Fanatec firmware that slider is
shown only when the attached rim exposes shaker motors. Its absence is evidence
the Porsche rim has none — which closes the open question at the end of §3.1
and makes that recommendation moot. The logic does not disappear, it **moves to
`FUL`** (§8.2).

### 8.1 As found (profile slot SETUP 5, ACTIVE PROFILE: none)

| | SEN | FFB | FUL | NDP | NFR | NIN | INT | FEI | FOR | SPR | DPR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| found | AUTO | 100% | 100% | 16% | 2% | OFF | 1 | 100 | 100% | 100% | 100% |
| set to | AUTO | 100% | **0%** | **5%** | **0%** | OFF | 1 | **80** | 100% | **0%** | **0%** |

Dynamic FFB tab: Speed Sensitive **Disabled**, Driving Reverse **Disabled** —
both stay disabled (§8.3).

**Nothing was saved to a profile.** ACTIVE PROFILE reads NO PROFILE LOADED, so
these values are live-but-unpersisted. Save to a named slot.

### 8.2 Reasoning, by class of claim

**Deduction from measured rig facts**

- `FUL` **0** — FullForce reproduces high-frequency tactile content (road,
  ABS, engine) through the base motor. That is the ButtKicker's measured job:
  28–34 Hz engine, 34–41 Hz road texture, 40–50 Hz brake regulation and lock,
  52–60 Hz kerb strike, 86–104 Hz rear traction, all pinned in `synth.PROFILE`.
  Two devices reporting one event, out of sync, is the exact fault the one-piston
  mixing discipline exists to prevent — and here the duplicate also sits on top
  of the self-aligning torque the wheel is now specialised for. This is §3.1's
  argument, transplanted from the shaker motors the rim turns out not to have.

**Measured-backed inference**

- `NFR` **0** — natural friction is a velocity-independent force floor. His
  measured median steering input is **0.020 of channel full scale** (129 laps,
  893,870 frames): he lives in tiny movements, which is precisely where a static
  friction floor does proportionally the most damage to the torque signal.
- `NIN` **OFF**, unchanged — inertia slows the wheel's return, which is what a
  trail-braker reads on brake release. His steering-rate p99.9 is 2.70
  lock-fractions/s; he is not sawing and needs no simulated mass to calm him.

**Preference, testable via §6**

- `NDP` **5%** (from 16%) — some damping suppresses on-centre oscillation of a
  high-torque motor; 16% is more than a driver this smooth needs, and damping
  masks the release rate. 0 is acceptable if no oscillation appears.
- `FEI` **80** (from 100) — §3.2. One step, not a leap; 60 if the transient
  duplication is still audible through the rack after a controlled comparison.

**Free diagnostics — strictly dominant given the stated priority**

- `SPR` **0** and `DPR` **0** — these scale the spring and damper *effect types*.
  If GT7 does not send them, zeroing changes nothing. If it does, they were
  masking the torque channel and zeroing removes them. Either way the result is
  information: **if the feel changes at all, GT7 sends those effects** — a fact
  nothing else in this repo can establish.

**Unchanged, with reason**

- `SEN` **AUTO** — GT7 sets rotation per car. Independently, §2.1's π-normalisation
  caveat means no measurement here can justify a manual number.
- `FFB` **100%** and `FOR` **100%** — `FOR` scales the constant-force effect,
  which *is* GT7's main channel, so lowering it is just a second master gain in
  series. Keep one gain. Set absolute level in GT7's own Max Torque, and if the
  wheel goes flat-topped in the heaviest corners, come down on `FFB` in steps
  of 5. There is no clipping indicator — GT7 broadcasts none (§1) — so the only
  symptom is the top of the load range going dead.
- `INT` **1** — minimal interpolation. Higher smooths at the cost of latency,
  and latency is paid exactly when catching a slide.

**In GT7 (Options → Controllers):** Max Torque **5**, Sensitivity **1**. Max
Torque is the stage that saturates first on a per-car basis; Sensitivity boosts
small-force detail, which is now the seat's job, not the wheel's. Sensitivity is
the single best GT7-side variable to A/B under §6.

### 8.3 Dynamic FFB — leave both Disabled

Whether the damping overlay receives a speed signal from GT7 on PS5 is
**unverified**. A telemetry path to the base plainly exists (GT7 drives Fanatec
rim displays), but whether this firmware module consumes it on console is not
established here.

It does not matter, because the recommendation is Disabled either way:

1. Speed-sensitive damping makes wheel weight a function of **speed**, which is
   not grip. That injects a confound into the one channel being protected.
2. **The wind sim already carries road speed**, measured and tuned. A wheel that
   also encodes speed is the same two-devices-one-event fault as `FUL` and `SHO`.

Driving Reverse damping is inert while racing; harmless, leave Disabled.

**To settle the unverified part in two minutes:** enable Speed Sensitive with
Threshold 100 kph, Max 300 kph, Damper Effect Strength 100, and drive up a
straight. If the wheel stiffens past 100 kph, GT7 feeds the module. If nothing
changes, it does not. Then disable it again regardless.
