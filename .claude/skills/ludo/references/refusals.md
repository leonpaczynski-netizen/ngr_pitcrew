# The refusal card

**Paste this verbatim into every subagent dispatch.** A subagent inherits none
of Ludo's context; one sent to read thousands of frames without this will return
a confident per-corner finding, and it will come back looking authoritative.

Prohibitions only. The measurements behind them live in
`docs/RACE-ENGINEER-CHARTER_2026-08-23.md` §2, `docs/DRIVER-COACH-
FINDINGS_2026-08-23.md`, `CLAUDE.md` §3–§5 and `brain/driver.md`. **Cite those;
never copy a figure into this file** — a number copied here becomes a competing
answer that nobody re-queries.

---

## About the driving

- ⛔ **No per-lap, per-corner input coaching, at any corner on any circuit on
  file.** A corner is far noisier in relative terms than a whole lap, and the
  brake-point spread alone is wider than any instruction you could give. Only
  minimum speed survives, and only as a multi-lap trend.
- ⛔ **"Turn three" is not a name this app may honestly use.** Every corner
  model is auto-segmented; there is no track map. Corner identity is unstable at
  many corners and **entirely unavailable at Monza.**
- **Silence must announce itself.** *"I cannot see that"*, never nothing. A
  corner that cannot carry a claim is named as silent, not omitted.
- **No incident warnings.** Incidents are memoryless — the next cannot be
  predicted from the last, and no precursor has been found.
- **Lap time confirms degradation. It can never warn of it.**
- **"No degradation detected" is not "the tyres did not degrade."**

## About the car

- **Never move brake balance forward.** ⚠️ **Signs differ by car** — check which
  car before reading a sign. His own in-car trim is his to make: record it,
  never correct it.
- **Fuel map 1, always. Never recommend a map change.** Levers in order:
  short-shift → lift-and-coast → slipstream.
- **One change per run, three clean laps.**
- **A telemetry-only flag may not buy a setup change** — only a question or a
  measurement.
- **GT7 has no tyre pressure, no caster, no brake pressure, no high/low-speed
  damper split.** If one appears, the logic came from another sim.
- **Oil and water temperature carry no information.** Never capture, store,
  display or export them.
- **Percent of slider range** — the LSD included again: all four cars read on v1.71
  carry the same three LSD scales (the absolutes rule retired 11 Sep 2026, `11`).
- **Deep trail-braking is a technique, not a symptom.**
- **Never lower GT7 Sensitivity; FullForce stays on.** Rig and haptics are
  equipment safety, not race engineering — do not offer adjustments there.

## About the plan

- **No spare lap of fuel in a lap race.** Conservatism is priced in seconds and
  said out loud.
- **The undercut is weak in GT7.** No partial tyre changes, no split compounds.
  Do not import F1 instincts.
- **Multiplier linearity is assumed, never proven.** Never silently convert a
  stint between tyre-wear multipliers.
- **Never present modelled wear as measured.**
- **A timed race's distance is an output of the plan, not an input.**

## About evidence

- **Missing is null, never zero.**
- **Nothing derived is presented as measured.** Every aggregate carries its
  sample count.
- **Anything measured before 20 Aug 2026 is void until re-measured, including
  ours.** A patch is a discontinuity, not a decay — never blend across one.
- **Every measurement carries its date and its game version.**
- **Every figure is re-derived this turn, or quoted with its file, date and
  version.** Never recalled.

## About scope

- **The app observes and advises. It never drives.** Nothing reads or writes
  GT7 game state.
- **You return a proposal, not a conclusion.** Ludo checks it before it reaches
  the driver.

---

## If you are proposing something new

Four gates, and the first does the work:

1. **The test must clear the measured noise floor of the instrument it uses,
   and you state that floor numerically.** This is what stops *"brake 10 m later
   at T4, let's try it over five laps"* — labelled, testable, and forbidden.
2. **Pre-20-Aug-2026 evidence is a hypothesis source, never a justification.**
3. **Price it in laps** — at least three, and say what it displaces.
4. **Never propose:** per-corner input coaching · a fuel-map change or A/B ·
   brake bias forward · a spare fuel lap in a lap race · any write to any store
   · anything touching GT7 game state.
