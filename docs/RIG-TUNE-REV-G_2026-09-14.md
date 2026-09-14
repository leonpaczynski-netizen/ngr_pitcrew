# Rev G — the rig's tune, locked in 14 Sep 2026

**Driver, after laps on it (session 171): "perfect lock it in".**
It is now what runs with nothing selected. **Amp 35 is part of the tune.**

Start of the thread: `docs/RIG-SWEEP_2026-09-12.md` (the remount sweep),
`docs/RIG-CHECK-PLAN_2026-09-13.md`, `docs/RIG-REV-A-TEST_2026-09-13.md`.

## Running it

| want | how |
|---|---|
| the tune (default) | launch normally — the log says `haptics profile: REV G (duck 0.92 / critical 0.88)` |
| amp | **35** — every level below was set and knock-checked there; at 29 the beds go under the floor |
| the pre-tune original, to compare | `$env:PITCREW_RIG_REV = "ORIGINAL"; python -m pitcrew.app` |
| an earlier revision | `$env:PITCREW_RIG_REV = "C"` (any letter A-G) |

**Check the log line before trusting any feel report.** Twice this weekend a
test would have run a different mix from the one reported: a half-applied Rev A
(profile bound at import) and haptics switched off in settings.

## What changed from the original profile, and the reason for each

| voice | original | Rev G | why |
|---|---|---|---|
| chassis_load | on, 56-66 Hz | **off** (trim 0.01) | continuous in every corner on the most sensitive band; buried traction 42% of its live time even in the original, 91% of that under chassis_load |
| rear_traction | trim 1.00 | 1.259 (+6 dB over B) | "especially rear traction loss"; knock-clean at full on the bench |
| impact / kerbs | trim 3.80, fixed 0.70 floor | trim 1.906, **graded**: worst wheel's peak compression over 50 ms, log scale, 0.362-0.685 | "a small kerb and big kerb hit the same" — the old grading put p10 and p90 kerbs ~1 dB apart; set -3 dB on the bench: "perfect" |
| suspension bumps | median bump under the 25% gate, never felt | **one thud per compression event** (rising edge, 50 ms rise, 90 ms decay), 0.35-0.60 | "road bumps ... missing"; 41% of compression events recur at the same lap position (real); a swell felt "like a rumble" |
| driveline | 0.95 | 0.95 | +7 "too big and blunt", +3 lost to it |
| brake_limit | 0.85 | 0.849 | +5 knocked slightly at 50 Hz; +3 clean |
| engine | 28-34 Hz, gain 9.52 | **53-131.5 Hz (66->100 on a pull), gain 9.43** | "I don't think engine rumble should be that deep?" — it swept 28->31.8 Hz across every rev; then "could climb more" |
| road | 0.80 | 1.596 | "texture still seems to lack a bit" |
| duck (event / limit) | 0.70 / 0.82 | **0.92 / 0.88** | a deeper dip under the shift beat a louder thud when the engine came up |

## Two design rules the tune breaks, on record

Both are strict `xfail` tests, so they flag the moment either is fixed. Neither
was averaged away: the driver drove it and called it right.

1. **A limit cue should duck the background harder than an event.** Rev G's
   event duck (0.92) is deeper than its limit duck (0.88). The brake cue is the
   most-buried voice in the replay, and this is the first thing to try if
   "brake over the limit" ever gets hard to feel: raise `DUCK_CRITICAL` above
   0.92.
2. **No continuous voice may share the traction band.** The engine now climbs
   into 86-104 Hz at high revs. Traction is 4% buried in the replay and "great"
   in the seat.

Also past a convention, named in its test: `rear_traction`'s scale (0.63) is
over the 0.5 calibration reference; knock-checked clean, renders at ~0.50.

## How it was tuned — the parts worth reusing

- **Masking check before laps** (`tools/rig_levels.py --profile X`): every
  critical and transient cue's margin over the strongest other voice at every
  instant it is live, on one scale (dB above the driver's floor). Validated by
  reproducing the Rev A rejection from telemetry before grading anything new.
  It over-reads short thuds (gear change 33% "buried" was "great" on track).
- **Knock-check every raised voice at full intensity, seated, before a lap.**
  The microphone knock curve is ~6 dB more cautious than the ear; neither alone.
- **Bench demos built from the app's own curves** — a two-gear pull on
  `RPM_CURVE` and the shift pulse, a cruise with texture and bumps, measured
  kerb and slip sizes — and A/B, never a single held level: one held level is
  what produced "traction just goes full vibration" when the real curve was fine.
- **Check a detector against the laps before building a cue on it**: tarmac
  velocity bumps recurred 0% (noise, not built); compression events 41% (real, built).
