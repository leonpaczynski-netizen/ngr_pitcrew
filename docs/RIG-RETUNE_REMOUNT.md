# Retuning the rig after the ButtKicker remount

Horizontal to vertical (inverted). Written 12 Sep 2026, before the new mount was
measured. Supersedes nothing: it says which of the existing measurements the
remount invalidates, which it does not, and the order to re-take them in.

Sources: `pitcrew/rig/transducer.py`, `pitcrew/rig/synth.py`,
`docs/HAPTICS_2026-08-16.md`, bench sessions 15-16 Aug 2026.

---

## 0. What the remount actually invalidates

One measurement, and it is the one everything else was sized against.

`transducer.FELT_RESPONSE` is **not a property of the transducer**. The source
comment says so: *"It is the seat, the mounts and the chassis as much as the
transducer."* Nine tones at -18 dBFS, endpoint metered at exactly 0.125 for
every one, rated 0-3 in the seat:

    30 Hz 2 - 40 Hz 3 - 50 Hz 3 - 60 Hz 2 - 70 Hz 1 (null)
    85 Hz 2 - 100 Hz 2 - 120 Hz 1 - 140 Hz 0.5

Two usable regions - **40-55** and **85-105** - a dead spot at 70, nothing
above 120. A resonance structure, not a rolloff.

Changing the mount axis and the mounting point changes the mass, the stiffness
and the boundary condition on both sides of that structure. **Assume the peaks
and the null have moved until measured.** They may have moved a little; the
null may have split; there may now be two.

### The mount as built (12 Sep 2026, from the driver)

- **25 x 25 x 2.5 RHS**, welded into a C, carrying the transducer.
- Welded to the **75 x 6 mm flat bar** seat bracket mounts.
- The ButtKicker's **factory bracket** bolted to the RHS. There is no other
  mounting interface on this unit - do not propose one.

This is a stiff closed section, not a compliant strap, and it is welded rather
than clamped: no joint compliance, no fretting, and torsionally stiff enough
that the seat pan should translate rather than rock.

**So the expectation is a FLATTER, better-coupled response than the old mount,
not a peakier one.** 25 x 25 x 2.5 is about 1.9e4 mm^4; with the transducer's
mass at midspan of a short run fixed both ends, first bending lands above
150 Hz - past the amp's 160 high-cut and clear of every effect band. The frame
stops being a filter and the seat shell becomes the shaping element.

**The one structural unknown that would change this: whether the RHS leg
carrying the unit is welded at both ends or has a free end.** The same section
cantilevered rather than spanning drops that mode by roughly 4x - to around
40 Hz, directly on the old low peak. Spanning, the frame is out of the band;
cantilevered, it is the dominant feature of the new response.

With everything else welded steel, **the factory bracket is now the softest
thing in the load path**, so any surprise below 40 Hz in the sweep is coming
from there. Characterise it; do not hunt it.

### What rests on it, and therefore is now unverified

- **The spectral plan** - every effect's band was placed into the two peak
  regions on purpose (`synth.py`):

  | effect | band | gain | felt_trim | priority |
  |---|---|---|---|---|
  | engine | 28-34 | 9.52 | 2.50 | BED |
  | road | 34-41 | 37.62 | 0.80 | BED |
  | brake_limit | 40-50 | 70.00 | 0.85 | CRITICAL |
  | driveline | 50 | 39.87 | 0.95 | TRANSIENT |
  | impact | 52-60 | 18.00 | 3.80 | TRANSIENT |
  | chassis_load | 56-66 | 35.19 | 0.85 | STATE |
  | rear_traction | 86-104 | 70.00 | 1.00 | CRITICAL |

  If the 70 Hz null moved to 60, `impact` and `chassis_load` are now in it and
  no trim fixes that - they have to be re-placed.

- **Every `felt_trim`.** A trim is a correction for where the effect sits in
  the response. The response is the thing that changed.

- **His SimHub gains**, which are a compensation curve for the *old* response
  (highest on wheel-spin at 82-108, a weak region; lowest on RPM at 34-42, a
  peak). They were arrived at by feel over eight days against a rig that no
  longer exists in that configuration.

- **The felt half of the amp reference.** `CALIBRATION_FREQ_HZ 40` /
  `CALIBRATION_DBFS -6` at **amp 35** was "very strong, no knock." The digital
  reference has not moved; whether 40 Hz is still a peak, and whether 35 still
  reads "very strong," both have.

### What the remount does NOT touch

Do not re-measure these; they are electrical and software, not mechanical.

- WASAPI **shared** only - exclusive opens, reports 21.3 ms, renders nothing.
- 2 ch @ 48 kHz; both channels reach the piston and **sum** (0.5 each).
- Amp band: fixed 25 Hz low-cut, high-cut switch **set to 160**.
- Bass Management and Loudness Equalization must stay **off** on that endpoint.
- The GIL / `SWITCH_INTERVAL_S = 0.0005` fix and the clock story.
- The named-mutex single-instance guard, USB selective suspend, CH340.

### One new thing to watch for, specific to going vertical

`AM_RANGE_HZ = (5.0, 16.0)` - severity is carried by amplitude modulation, and
5-16 Hz sits right on the vertical-axis whole-body resonance (~4-8 Hz peak).
Modulation rate is not gated by the amp's 25 Hz low-cut; it rides the carrier.
**The AM may read noticeably stronger on a vertical mount than it did
horizontally**, which would show up as severity feeling exaggerated rather than
as any one effect being too loud. `AM_MAX_DEPTH = 0.60` is the knob if so.

---

## 1. Pre-flight - before rating a single tone

A starved or degraded endpoint reads as a bad mount. Do not skip this, or the
remount will be blamed for the audio bug.

```bash
python tools/haptics_bench.py devices
```

Then confirm the endpoint is running at rate, not at the degraded ~30.5k f/s
that survives across processes and **only clears on a reboot**. If in any
doubt: reboot first, and re-run `tools/rig_usb_power.ps1` if Windows has
updated since August.

Also confirm the amp knob's actual position and write it down. The settled
operating point was **35 of 50** with master 1. Master 2 tripped DC-protect and
needed a full PC restart.

---

## 2. The response sweep - the one that must be re-run

```bash
python tools/haptics_bench.py band --freq 30
```

Then repeat, one invocation each, for 40, 50, 60, 70, 85, 100, 120, 140.

Defaults are -18 dBFS, 3 s, faded in and out. Rate each **0-3** in the seat.

**Method rules, each of which cost real time the first time round:**

1. **ONE tone per invocation.** A sweep sends its labels to the operator only
   after it finishes, so the man in the seat cannot say which buzz was which.
2. **Re-run a known-good tone as a control before theorising.** A 40 Hz tone
   rated "strong" read as nothing minutes later and sent the last session
   hunting a mystery cutoff. There wasn't one - the path had died.
3. **Disambiguate one-word answers.** "1 yes" and "only 1 burst" each had two
   readings with opposite implications, and guessing once put a fabricated
   measurement into a source comment.
4. The endpoint meter should read **0.125 for every tone**. If it does not, the
   difference is not the rig and the run is void.

**New for the vertical mount:** listen for *mechanical knock* separate from the
felt effect, especially at 30 and 40 Hz. Gravity now parks the piston off-centre
and it will reach one end stop sooner than the other. Knock at -18 dBFS would be
a real problem; knock only at the calibration level is a gain question.

Then re-take the reference:

```bash
python tools/haptics_bench.py calibrate
```

40 Hz at -6 dBFS, 10 s. Find the amp position that is "very strong, no knock"
and record it. **If the amp needs to come down from 35, that is good news** -
a stiff welded path delivers more of the same excursion into the seat, so
"very strong" arrives at less drive. It also makes the end-stop question less
live rather than more, because knock is set by excursion and excursion is set
by drive.

---

## 3. Re-place the bands, only if the peaks moved

If the peaks have moved, this is placement work, not trimming. The organising
idea holds regardless: **low is the car, high is the contact patch**, and the
two CRITICAL cues (`brake_limit`, `rear_traction`) get the two best regions
because they are the ones that cost lap time when masked.

Update `FELT_RESPONSE`, `FELT_PEAK_LOW`, `FELT_PEAK_HIGH` and `FELT_NULL_HZ` in
`transducer.py` from the measured table - the tests in `test_transducer.py` pin
these, so they will tell you what else assumed the old numbers.

---

## 4. Replay before touching a single gain

```bash
python tools/rig_levels.py --laps 12
```

Drives the **real** derivers and the real gain chain frame by frame over stored
laps, and prints median / p99 / peak / %live per effect. It turned six vague
complaints into six numbers in one pass.

- It must read laps through `Store.get_lap_frames`, **not** off the blob.
- This measures the *signal*, which the remount did not change. Its value here
  is as the control: the levels the mix is producing are identical to August,
  so any difference in feel is the mount, and only the mount.

`--sessions` and `--game-version` exist for controlled comparisons.

---

## 5. Re-learn the vocabulary in the new position

```bash
python tools/haptics_bench.py pair rear_traction road
```

`cue <effect>` plays one effect through the real `HapticMix`; `pair <effect>
<background>` is the question that actually matters on one piston: **not "can I
feel it" but "can I still tell it apart."**

Check specifically, because these were hard-won and a response change can undo
any of them:

- **brake_limit**: silent at/below the optimum, one ramp 0 to 0.50 up to the
  lock threshold. The boundary is the *onset of feedback*. Third shape agreed;
  do not redesign it, just confirm the onset is still perceptible.
- **impact vs road**: the sausage-kerb strike is a **rhythm** - tap, hard gap,
  second tap. The gap punched through the strip's barrage is the signature. If
  the new mount blurs the gap, that is a decay problem, not a gain problem.
- **The duck.** Sustained effects duck 20 ms out / 180 ms back under a
  transient, gated at shaped 0.15. Contrast, not frequency, is what makes an
  event legible here.

---

## 6. The standing rule for the trims

**Sum stacked trims against the felt table before shipping.** Three brake cuts -
trim, min_force, floor - were each right alone and summed to -13 dB, which
inverted the balance and put the road bed at twice the brake cue.

And: a trim is a correction, not a change of purpose. `impact` at 3.80 is the
one gain in the table that is no longer the driver's.

---

## Order, short form

1. Reboot / verify endpoint at rate. Record the amp knob position.
2. Nine tones, one per invocation, rated 0-3. Listen for knock.
3. `calibrate` for the new amp position at "very strong, no knock."
4. Update `FELT_RESPONSE` and friends; run `test_transducer.py`.
5. Re-place bands **only** if the peaks moved.
6. `rig_levels.py` as the control - the signal did not change.
7. `cue` / `pair` for separability.
8. Trims last, summed against the felt table.
