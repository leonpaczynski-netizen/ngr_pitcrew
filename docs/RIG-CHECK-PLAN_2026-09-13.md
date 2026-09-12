# The rig check plan — after the race

Written 12 Sep 2026, for the driver to run when he has the rig back. Built on
`docs/RIG-SWEEP_2026-09-12.md` (what was measured) and
`docs/RESEARCH-VEHICLE-FREQUENCIES_2026-09-12.md` (what the literature says).

**Race setting until then: amp 29.** Verified in the seat at full kerb
intensity and full traction severity, both clean.

---

## Why there is a plan rather than a rebuild

Three things came out of 12 Sep that each invalidate a different assumption the
spectral plan rests on, and none of them can be settled from the desk:

1. **60 Hz is probably not the transducer's resonance.** If it is a mode of the
   seat and mount instead, it can be MOVED - which is far cheaper than designing
   a permanent 52-70 Hz no-go band into the profile.
2. **The beds may be sitting below the driver's detection threshold**, while the
   events run 20+ dB above it and into the stops.
3. **Frequency separation does not separate these cues** (§3 below), so the
   whole idea of re-placing seven effects by frequency may be the wrong lever.

Each step below is ordered by *decisiveness per minute*. Step 1 settles the
biggest open question in five minutes with a pair of calipers.

---

## Step 1 — the caliper test. Five minutes, no acoustics, decisive.

**Question:** is 60 Hz the shaker's own resonance, or a mode of the seat and
mount?

Static sag of a suspended mass is `d = g / (2*pi*f0)^2`. That is the whole
test, because sag is measurable with a ruler and `f0` is not.

    f0 =  5 Hz  ->  9.9 mm
    f0 = 10 Hz  ->  2.5 mm
    f0 = 15 Hz  ->  1.1 mm
    f0 = 60 Hz  ->  0.069 mm

**Do this:** unbolt the unit, rest it on foam, and measure the piston's rest
position with calipers **lying on its side**, then **standing on end**. The
difference IS the sag.

| you measure | it means |
|---|---|
| ~10 mm | Fs ≈ 5 Hz. Gravity sag explains the whole headroom loss. |
| ~2.5 mm | Fs ≈ 10 Hz. Same conclusion, smaller margin. |
| unmeasurable | Fs ≥ 40 Hz, and the mechanism is something else entirely. |

**Guitammer's own patent gives the number: "about 8 Hz or 9 Hz"**
(US5973422A, Clamme, assignee The Guitammer Company - the foundational
ButtKicker patent, stating the preferred embodiment's mechanical resonance).
That predicts **3.1-3.9 mm of sag**, and the mass cancels out of equation (8),
so it applies to the 1 lb Gamer Pro piston exactly as to the 3.25 lb LFE one.

**But there is a twist that may invert the whole expectation, and it is why
this measurement is worth doing rather than assuming.** The same patent says
the magnet and coil positions "**may be offset to accommodate the bias force of
gravity**" - the sag is designed out at manufacture, for one assumed
orientation. And Guitammer's manuals say which orientation that is:

> "designed for optimal performance when mounted vertically (either 'up' or
> 'down'), but will function at any angle... **a vertical installation is
> strongly recommended for the best effect**"
> — ButtKicker Advance (BK4-4) Owner's Manual, p.06

**So vertical is the manufacturer's recommended orientation, and plausibly the
one the unit is trimmed for.** If that holds, the remount moved the piston
TOWARD its designed rest position, not away - and the headroom we lost cannot
be gravity sag at all. It would then be entirely the structural mode (step 2).

The caliper test separates these cleanly:

| you measure | it means |
|---|---|
| **~3-4 mm** | Untrimmed, Fs ≈ 8-9 Hz as the patent says. Sag is real and vertical costs travel. |
| **~0 mm, either orientation** | The unit is gravity-trimmed. **Sag explains nothing** and the whole headroom loss is the 60 Hz structural mode. |
| **~3-4 mm HORIZONTAL but ~0 vertical** | Trimmed for vertical. The remount *helped*, and the loss is the mode. |

## Step 2 — the driver-mass sweep. The discriminator is the FREQUENCY, not the level.

**Question:** does the 60 Hz feature belong to the seat, or to the unit?

    python tools/rig_knock_curve.py --amp 35 --quick     # with driver seated
    python tools/rig_knock_curve.py --amp 35 --quick     # empty seat

Run both, same mic position, same amp, same session.

- **If the 60 Hz knock minimum MOVES DOWN and BROADENS with the driver in the
  seat** -> it is a structural mode of seat+mount. 96 kg of lossy load damps it
  and shifts it. **It can be moved on purpose.**
- **If it stays at 60 Hz and only changes level** -> it belongs to the unit and
  the no-go band is permanent.

**Do not read the level difference as the answer.** The obvious reading of
"less knocking when I sit in it" is added mass, and that is wrong: the piston is
1 lb (0.454 kg, manufacturer spec), so 96 kg changes the `(1 + m/M)` term by
**0.16 dB** - far too little to notice. The mechanism that fits is damping: at a
structural resonance the housing recoils in antiphase with the piston, so the
relative displacement is the SUM of the two, and a seated human is a lossy load
that shrinks the recoil.

## Step 3 — if 60 Hz is structural, move it before designing around it

Cheapest levers, in order. Each is a step-1-style measurement afterwards - the
sweep tells you where the mode went.

1. **Add mass at the transducer.** A few kilos bolted to the RHS near the unit.
   This is the only fix found so far that costs nothing in the cues.
2. **Add damping to the seat shell** - the shell became the dominant shaping
   element once the drive moved onto the brackets' stiff axis.
3. **Change the mounting point** along the RHS.

**Note what stiffening does, because it is the opposite of the intuition and it
is what happened here:** stiffening does not remove a resonance, it moves it UP.
The remount pushed the bracket mode from 40-55 Hz into 60 - out of a region
where it was doing useful work and into the middle of where six of the seven
effects live. The remount changed two variables in one action: gravity sag
(broadband headroom) and mode relocation (where the knock is centred).

## Step 4 — re-test the beds against masking, NOT against a silent room

**Question:** are `road`, `engine` and `chassis_load` actually below threshold
in the car, or only below a threshold measured in silence?

Replayed over twelve real laps they fire at -29.1 to -25.8 dBFS against a 40 Hz
floor of -25.0. That says the beds are inaudible - but the floors came from
2-second pure tones in a quiet room with nothing else playing, and a bed is
band-limited noise heard while a wheel is moving in the driver's hands.

**Re-run `tools/rig_perception.py` with the road bed playing underneath**, at
the level the replay says it actually reaches. The difference between that
threshold and the silent one IS the masking, and it is the number that decides
whether the beds need raising or the whole allocation is wrong.

Until that is measured, **do not raise the beds.** The finding is real but the
measurement behind it does not yet apply to the car.

## Step 5 — separate the cues on RHYTHM, not frequency

This is the finding that most changes the plan, and it means the re-placement
may be a smaller job than expected.

- **Frequency JND for touch runs 3-50%**, and masking in touch is channel-bound
  rather than narrowband. On that axis `driveline` (50 Hz), `impact` (52-60) and
  `chassis_load` (56-66) are within 20% of each other: **they are one cue.** No
  amount of re-placing inside 25-160 Hz separates them.
- **Rhythm identification runs above 90%.** Separation has to be carried on the
  ENVELOPE - onset, gap, repetition - not the carrier.

The app already has one worked example of this and it was arrived at by
accident: the sausage-kerb strike was 100% masked by the ripple strip's edge
thump until it was made a RHYTHM - tap, hard gap, second tap - and the gap
punched through the barrage is what made it legible. That is the mechanism the
literature says to use, and it should now be the default tool rather than the
exception.

**So the re-placement brief changes:** stop trying to give seven effects seven
frequency bands. Give them distinguishable envelopes, and use frequency only
for the coarse "low is the car, high is the contact patch" distinction the
driver has already learned.

## Step 6 — reconsider where the beds sit, on evidence

Le et al. (2023) found the tactile system **does** resolve spectral content, and
that salience is set by the ratio to the **lowest** component present: removing
the lowest tone from a complex was detected 87.8% of the time, the highest only
55.9% against 33% chance.

`engine` (28-34) and `road` (34-41) are the **lowest** bands in the profile and
they are **always on**. That is the worst position an always-on bed can occupy -
it anchors the perception of everything above it.

Encouragingly the same work found **no effect of complexity**: a seventh
simultaneous component is not categorically worse than a second. The problem is
where the bed sits, not how many things are playing.

**This is a design change, not a fix, and it needs the driver in the seat** -
his learned map says low means the car, and moving the beds up cuts against it.

---

## What NOT to do

- **Do not enable the knock ceiling** (`PITCREW_KNOCK_CEILING`) until it caps
  the emitted peak rather than the gain coefficient. As built it is ~6 dB too
  aggressive, and even corrected it made the kerb strike unrecognisable.
- **Do not move an effect to where the rig has room without testing what it
  MEANS.** 120-140 Hz has the most usable range on the rig and the kerb strike
  placed there read as "ABS or traction control".
- **Do not treat the 9-12 dB headroom loss as exact.** It compares August's
  reference at amp 50 against 12 Sep at amp 35; it is an upper bound.
- **Do not measure anything on this rig with an empty seat** unless the empty
  seat is the variable, and say which it was.

## Two things the sources could not answer

- **Guitammer publish no mounting-orientation guidance at all** - so the
  question "is vertical supported" has no manufacturer answer, and the caliper
  test in step 1 is the only way to know what it costs.
- The research document lists **14 explicit gaps** in §7 rather than filling
  them. Read those before treating any figure in it as settled.
