# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop

> The schema's enum (`web` / `ios` / `android` / `adaptive`) has no value for a
> Qt desktop application, so this records the truth instead of the nearest
> wrong option. The iOS and Android references do not apply; neither does the
> web design detector.

## Stack

Python 3.14 + PyQt6, single local desktop app. Existing codebase — not a
greenfield stack decision. SQLite for storage, no server, no network calls.

## Users

One driver: Leon. Sim racing Gran Turismo 7 on a PS5 with a Fanatec DD Extreme
(18 Nm) wheel, ClubSport V3 load-cell pedals, **in PSVR2**. He races a custom
league with no BoP and open garage tuning, mixed sprint and multi-stop formats.
He trail-brakes deep by design and runs low or no assists.

## Product Purpose

A local race-engineering companion for GT7. Four jobs, in order of maturity:

1. **Capture** GT7's 60 Hz UDP telemetry.
2. **Record practice sessions** — laps, corners, and the setup that was in the
   car at the time.
3. **Export** a `gt7-pitcrew/1.1` JSON payload that Leon pastes into an external
   Claude project, which returns a revised setup sheet.
4. **Race strategy** — a stint and fuel plan, then talk him through it live and
   adapt as the race unfolds.

Success is a faster car by the end of the loop, and a race run to a plan he did
not have to read.

## Positioning

The app deliberately does **not** author setups. That moved to an external
knowledge base which produces better tunes than the app's own rule engine did.
What remains is what only a local app can do: read the telemetry stream, and be
a voice in the driver's ear.

## Operating Context

- **Two monitors at the rig.** The app sits on the upper monitor, above the one
  the PS5 feeds.
- **He is in a VR headset while driving, so he cannot see the app at all during
  a session.** Every screen is used *between* sessions, headset off, from the
  driving position. Nothing needs to be glanceable at speed.
- **The only live channel during a race is audio.** That is why the race
  engineer speaks; it is not a stylistic choice.
- SimHub relays GT7's raw encrypted packets to `127.0.0.1:33741`, already in the
  368-byte `C` format.
- Setup sheets arrive as text from the Claude project and are pasted in.
  Slider ranges are read off the car's own settings screen, once per car.

## Capabilities and Constraints

Governing contracts, both at the repo root and both authoritative over any
plan: **`CLAUDE.md`** (build brief) and **`EXPORT-CONTRACT.md`**
(`gt7-pitcrew/1.1`).

Hard facts that bound what is buildable:

- **GT7 exposes no tyre wear channel, in any packet format.** Wear is modelled
  from the driver's gauge reading, lap-time degradation and temperature trend,
  and is never presented as measured.
- **GT7 sends no track ID.** Corner identity comes from the app's own model and
  must be declared in the export.
- Suspension is **absolute height in metres**, not travel remaining.
- Oil (~110 °C) and water (~85 °C) are pinned constants carrying no
  information; they are not captured at all.
- GT7 has **no tyre pressure, no caster, no brake pressure, and no
  high/low-speed damper split.** Any of these appearing in the UI means the
  logic was pattern-matched from another sim.
- Tyre wear degradation is **piecewise** (flat → linear → cliff), never linear.

Terminology is the export contract's shared vocabulary: 23 setup keys
(`rh_f`, `nf_f`, `arb_f`, `dc_f`, `de_f`, `cam_f`, `toe_f`, `lsd_i/a/b`, `awd`,
`df_f/r`, `bb`, `top`, `fg`), compound codes (`RH`/`RM`/`RS`/`IM`/`HW`), and
corner ids (`T1`…`Tn`).

## Brand Commitments

Product name: **Next Gear Racing Pit Crew**.

## Evidence on Hand

- Real GT7 telemetry: packet offsets measured against a live v1.70 stream,
  not taken from a community table.
- A track station map for Monza only; every other circuit uses auto-segmented
  corners.
- **No recorded real session is checked in yet.** `CLAUDE.md` §7 requires one as
  the aggregation test fixture. Until it exists, all analysis tests run on
  synthetic laps — future work must not present synthetic results as validation
  against real driving.

## Product Principles

1. **The driver's report is primary evidence; telemetry only corroborates.**
   Where the two disagree, that disagreement is the finding — surface it, never
   average it.
2. **Missing is null, never zero.** A zero that means "not measured" gets
   diagnosed as a real value, and that error survives all the way into a setup
   recommendation.
3. **Nothing derived is presented as measured.** Every computed figure carries
   its threshold, model or source.
4. **Every aggregate carries its sample count.** A corner from two laps and one
   from eleven are not the same claim.
5. **Refuse rather than emit something wrong.** The export's consumer is a
   reader, not a parser — malformed output does not throw, it gets misread.

## Accessibility & Inclusion

Used with a VR headset just removed, from the driving position on an upper
monitor — so text runs larger than desk-app default and contrast stays high.
No other product-specific requirement established.
