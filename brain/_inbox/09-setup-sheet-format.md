# Setup Sheet Output Format

**Purpose:** every setup I produce comes back in this exact layout, so it can be typed straight into GT7's settings screen without translation or re-ordering. **It is not typed into Pit Crew** (`CLAUDE.md` §1a): the one copy of what is in the car is `brain/car-state/<car>-<circuit>.md`. The order below follows GT7's in-game sheet top to bottom.

**Every sheet ships as the human sheet below**, and the car-state file is updated with it. The Pit Crew paste block it used to carry is retired (last section).

## Why values are given as percent-of-range

GT7's slider ranges are **per-car**, derived from internal chassis data (lever ratio ~0.5–1.5, corner mass, total suspension travel). Natural frequency, ride height, damper windows and camber limits all differ between cars — many road cars cannot reach 3.50 Hz at all, some race cars exceed 5.00. So absolute numbers copied between cars are meaningless.

Every per-car parameter is therefore given three ways:

`72% · +9 clicks from min · ≈3.42 Hz`

- **Percent of range** — always correct, use this if the other two disagree with what you see on screen
- **Clicks from minimum** — fastest to dial in; hold the slider at minimum, then count up
- **Absolute estimate** — a convenience figure, and explicitly *an estimate* unless that car's ranges have been recorded

Parameters on **universal scales** are given as plain numbers, because they are the same on every car: ARB (1–10), dampers (20–40 compression / 30–60 expansion on v1.71), LSD (0–30 initial / 0–100 acceleration / 0–100 braking on v1.71 - three scales, never one line), brake balance (−5 to +5), camber and toe in degrees.

---

## The sheet

```
═══════════════════════════════════════════════════════════════════
  <CAR>  ·  <CIRCUIT>  ·  <EVENT>
  Generated <date> · GT7 v<version> · no BoP, open tuning
═══════════════════════════════════════════════════════════════════

                                    RACE              QUALIFYING
───────────────────────────────────────────────────────────────────
TYRES
  Front compound                    ...               ...
  Rear compound                     ...               ...

SUSPENSION
  Body height          Front        ..% ·  +.. clicks ...
                       Rear         ...               ...
  Anti-roll bar        Front        ..                ..
                       Rear         ..                ..
  Damping compression  Front        ..                ..
                       Rear         ..                ..
  Damping expansion    Front        ..                ..
                       Rear         ..                ..
  Natural frequency    Front        ..% ·  +.. clicks ...
                       Rear         ...               ...
  Camber angle         Front        ...°              ...°
                       Rear         ...°              ...°
  Toe angle            Front        ±...°             ±...°
                       Rear         ±...°             ±...°

DIFFERENTIAL
  Initial torque                    ..                ..
  Acceleration sensitivity          ..                ..
  Braking sensitivity               ..                ..
  [AWD only] Front/rear torque      ../..             ../..

AERODYNAMICS
  Downforce            Front        ..% of range      ...
                       Rear         ..% of range      ...

TRANSMISSION
  Max speed setting                 ... km/h          ... km/h
  Final gear                        ....              ....
  1st … nth                         ....              ....

BRAKES
  Brake balance                     ..  (− front / + rear)

PERFORMANCE ADJUSTMENT
  Power restrictor                  ..%               ..%
  ECU output                        ..%               ..%
  Ballast / position                .. kg / ..        .. kg / ..

ASSISTS (not on the sheet, but part of the setup)
  ABS                               ...               ...
  TCS                               ..                ..
═══════════════════════════════════════════════════════════════════
```

## What always accompanies the sheet

1. **Deviation notes.** Every value that differs from the baseline starting sheet gets one line saying why. Values at baseline are not explained — that keeps the notes short enough to actually read.
2. **Gearing derivation.** Which corner set 1st, which straight set top gear, what speed is actually reached with tow, and which gear each significant exit lands in. Never a target-top-speed number on its own.
3. **Strategy note.** Expected stint length at the event's multipliers, the stop window, fuel map plan, and the in-race brake-balance and TCS migration through the stint.
4. **Three things to test first**, ranked, if the car is not right on the first run. One change per run, three clean laps.
5. **Confidence flags.** Anything derived from a contested or single-source claim is marked, so it gets tested rather than trusted.
6. ~~The Pit Crew paste blocks~~ — **retired 5 Sep 2026** with the app's setup record (`CLAUDE.md` §1a); `pitcrew/setup/parse.py` no longer exists. The car-state file update travels instead.

## Ordering rule for the two columns

The **race sheet is the primary column** and is built first. The qualifying sheet is expressed as a **delta from it**, because that is how the car is actually developed — you do not build two cars, you build one and sharpen it. For a pure time-trial event the columns collapse to one.

---

# Feeding Pit Crew — the paste block

> **⛔ RETIRED 5 Sep 2026 - history only.** The app no longer takes a setup (`CLAUDE.md` §1a) and the parser this section describes is deleted, so a block pasted anywhere in the app goes nowhere. **Do not produce these blocks.**

**Status: verified against the app's own parser (`pitcrew/setup/parse.py`) on 11 Aug 2026.** This is not a proposed contract; it is what the code actually reads.

## The rule

**Every sheet is followed by one fenced JSON block per column** — race first, then qualifying. Leon pastes them one at a time into the paste box on Pit Crew's **Event** screen.

**One block per sheet, never one block for both.** The parser reads a single `setup` object per paste (`payload["setup"]`, or a bare object with a `values` key). A second sheet nested anywhere else in the same payload is ignored **without a warning** — which is the one failure mode that matters here, because the driver would believe both loaded.

## The shape

```json
{
  "format": "gt7-pitcrew/1.1",
  "meta": {
    "car": "...", "circuit": "...", "sessionType": "race",
    "date": "YYYY-MM-DD", "gameVersion": "1.70",
    "compound": { "front": "...", "rear": "..." },
    "assists": { "abs": "Weak", "tcs": 0, "countersteer": false },
    "multipliers": { "tyreWear": "8x", "fuel": "3x" }
  },
  "setup": {
    "sheetName": "<circuit> <race|quali> v<n>",
    "values": { "rh_f": 60, "...": 0 },
    "gears": [2.727, 1.925, 1.529, 1.288, 1.152, 1.062],
    "performance": { "powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 0, "ballastPosition": 0 }
  }
}
```

## Keys — all 23, and no others

`rh_f` `rh_r` · `nf_f` `nf_r` · `arb_f` `arb_r` · `dc_f` `dc_r` · `de_f` `de_r` · `cam_f` `cam_r` · `toe_f` `toe_r` · `lsd_i` `lsd_a` `lsd_b` · `awd` · `df_f` `df_r` · `bb` · `top` `fg`

Identical to the export vocabulary in `10-pit-crew-data-format.md` §3, because it is the same module (`pitcrew/setup/vocabulary.py`). A range record round-trips out and a sheet round-trips in with no translation.

## Five rules the parser makes non-optional

1. **Numbers only inside `values`.** A string, or a value with a unit attached, is dropped.
2. **Omit `awd` entirely on two-wheel-drive cars.** Do **not** write `"awd": null` — a null on a known key is dropped *silently*, with no unmatched warning. An omitted key reads honestly as 22 of 23.
3. **`gears` is 1st…nth in order, positive floats.** Wrong order imports wrong; the app does not sort them.
4. **Signs explicit.** Toe `+` in, `−` out. Brake balance `−` front, `+` rear, as a delta from factory bias.
5. **Any key outside the 23 lands in `unmatched`** and shows on screen as "n lines not recognised". A clean paste reads *"22 of 23 settings, 6 gears"* with nothing unrecognised — that string is the acceptance test.

## What the paste block does **not** carry

The parser reads `sheetName`, `values` and `gears`. **That is all.** Everything else in the block is there for the driver to read while pasting, and still has to be entered by hand on the Event screen:

- compounds · assists (ABS/TCS) · wear and fuel multipliers · performance adjustment (restrictor, ECU, ballast) · event format, length and weather · the car's slider ranges

Say so under every pair of blocks. A field that looks like it imported and did not is worse than one that was never offered.

## The human sheet stays as it is

The layout above is still optimised for reading down a column while typing into GT7 itself — the paste block feeds the app, not the game. Two conventions therefore still hold:

- **One value per line, never a range.** If I am uncertain, I give a value plus a separate test instruction — not "38–42".
- **Signs are explicit.** Toe is written `+0.10` or `−0.10`, never bare. Brake balance carries its direction reminder on every sheet, because the sign convention is the single most commonly inverted parameter in GT7 advice.
