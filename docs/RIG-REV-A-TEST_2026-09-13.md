# Rev A — the tune to drive

First profile built from measurement rather than from feel. Opt-in, nothing is
the default until it has run laps.

**Amp 35. Not 29.** That is part of the change, not a leftover.

---

## What was wrong, in one table

Every effect's real in-car level (replayed over twelve of your own laps),
against the two curves measured on 12 Sep — the knock ceiling and your own
perception floor:

| effect | level | vs FLOOR | vs KNOCK | |
|---|---|---|---|---|
| engine | −28.4 | **−3.4** | −24.5 | **inaudible** |
| road | −25.8 | **−0.8** | −15.6 | **inaudible** |
| chassis_load | −26.1 | +8.7 | −9.0 | |
| brake_limit | −10.4 | +17.1 | −1.4 | no margin |
| driveline | −11.4 | +18.6 | −5.4 | |
| impact | −6.2 | +26.8 | **+7.0** | **knocks** |
| rear_traction | −6.0 | +22.4 | **0.0** | on the limit |

**The beds are not quiet, they are absent** — below the level at which you can
detect them at all — while two events run past the point where the transducer
runs out of travel. The rig's whole range is spent at one end.

At amp 29 it is worse: engine −9.4 and road −6.8 under the floor. That is why
the race setting feels sparse, and it is not a fault in the mix.

## What Rev A does

Brings the offenders down, the beds up, and keeps amp 35 — the only position
where the beds get near audible at all.

| effect | change | vs FLOOR | vs KNOCK |
|---|---|---|---|
| engine | **+4.1 dB** | +0.7 | −20.4 |
| road | **+7.0 dB** | +6.2 | −8.6 |
| chassis_load | **+3.0 dB** | +11.7 | −6.0 |
| brake_limit | **−3.0 dB** | +14.1 | −4.4 |
| driveline | **−2.0 dB** | +16.6 | −7.4 |
| impact | **−9.0 dB** | +17.8 | −3.1 |
| rear_traction | **−4.0 dB** | +18.4 | −4.0 |

**Every effect is now above your floor and below the stops. That has not been
true before.**

The duck deepens with them — 0.70 → 0.80, and the critical duck 0.82 → 0.88.
Raising a bed raises what every event has to beat, and that is exactly how the
kerb thump came to fire 11.3 dB *below* the road bed once already.

## What it does NOT do, and why

- **`impact` stays at 52–60 Hz.** 60 Hz is the most sensitive frequency on the
  rig. Moving it down to 30–42 costs about 10 dB that no trim can buy back
  inside the ceiling; moving it to 120–140 you tried in the seat and called
  "more like ABS or traction control". It stays and comes down in level.
- **No band moves at all.** Gains, thresholds, gammas, priorities: untouched.
  One variable, so the laps mean something.
- **The per-band knock ceiling stays off.** It caps a gain coefficient rather
  than the emitted amplitude and is about 6 dB too aggressive as built.

## Before the laps — two minutes

1. **Amp to 35.**
2. Kerb strike at full, with the new trim. It should be clean:
   ```bash
   python tools/haptics_bench.py cue impact --level 0.9 --seconds 5
   ```
   **If it knocks, stop** — that is the `PEAK_BELOW_SCALE_DB` assumption
   failing, and I want to know before you drive it.
3. Traction at full severity:
   ```bash
   python tools/haptics_bench.py cue rear_traction --level 0.95 --seconds 5
   ```

Run the app with `PITCREW_RIG_REV_A=1` set.

## What to report after the laps

Four questions, in order of what they decide:

1. **Can you feel the road bed now?** This is the whole point. It should be
   present but quiet — a floor under everything, not an effect. If it is still
   absent, `road` needs GAIN rather than trim, which is your number to change.
2. **Is the kerb strike still a kerb strike?** It has come down 9 dB. It should
   still read as an impact; it will be less violent. If it has stopped reading
   as a kerb, that is the finding and `impact` has nowhere good left to go.
3. **Can you still tell `brake_limit` from `rear_traction`?** They are the two
   CRITICAL cues, both now above 40 Hz — the same Pacinian critical band — so
   frequency does not separate them. They are relying on their AM rates, which
   overlap (7–16 vs 5–14 Hz). If they blur, that is the next thing to fix and
   it will be an AM change, not a frequency one.
4. **Does anything knock?** Especially on kerbs and over the Bathurst kerbs.

And one open question the research raised that only you can answer: **does a
FASTER pulse read as more urgent to you, or less?** The measured answer for
touch is that perceived roughness *falls* as modulation rate rises from 20 to
50 Hz — the opposite of audio, which is where the app's severity mapping came
from. `AM_RANGE_HZ` is 5–16 Hz and peak modulation sensitivity is at 40 Hz, so
there may be a whole axis being used backwards and underpowered. Worth noticing
what your gut says while you drive.

## Reverting

Unset `PITCREW_RIG_REV_A`. Nothing else changes; the default profile and the
default duck are untouched.
