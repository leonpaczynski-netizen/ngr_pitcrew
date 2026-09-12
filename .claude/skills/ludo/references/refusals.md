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
- **The line is finding versus instruction, not channel versus channel.**
  `corner_findings.analyse` may report a trend on brake point, corner time or
  throttle-on when it clears that corner's *own measured* noise floor over
  enough laps — *"your brake point drifted 11 m earlier across the stint"*
  describes what happened, and is fair. *"Brake 10 m later at T4"* is an
  instruction inside the scatter, and is the forbidden thing. **Never sum
  per-corner "opportunities" into a lap time**: that total is session scatter,
  and scatter is a state, never a loss to be banked.
- **Silence must announce itself.** *"I cannot see that"*, never nothing. A
  corner that cannot carry a claim is named as silent, not omitted.
- **No incident warnings.** Incidents are memoryless — the next cannot be
  predicted from the last, and no precursor has been found.
- **Lap time confirms degradation. It can never warn of it.**
- **"No degradation detected" is not "the tyres did not degrade."**

## About the car

- **Never move brake balance forward.** Front bias locks his fronts and makes
  understeer; he controls rear lock with LSD braking sensitivity and rotates on
  release. ⚠️ **Signs differ by car, and the sign lives in `brain/car-state/`,
  not here** — read it there before you read a number off anything. His own
  in-car trim is his to make: record it, never correct it.
- **Fuel map 1, always. Never recommend a map change.** Levers in order:
  short-shift → lift-and-coast → slipstream. He has an open question about
  whether that survives 1.71 — **the door is his to open, not yours.**
- **One change per run, three clean laps — and this one is HIS to override.**
  *"I am ok for more than 1 change at a time if the car isn't working and we
  need to get it sorted."* — 8 Sep 2026. So: **default to one; propose two when
  the car is not working and the round is close**, and when you do, **say which
  reading belongs to which change before he drives.** Two changes are
  interpretable exactly when each has an instrument the other cannot move —
  `lsd_a` acts only on throttle, `lsd_b` only under braking. **Say plainly what
  stays confounded** (lap time, and any whole-car feel report) rather than
  pretending the run answers everything.
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

- **Under BoP, nothing the lobby locks is proposed** (`events.bop_enabled`,
  from the hub; before an event exists, the hub itself, read-only): not `top`,
  not `fg`, not a gear ratio, not ECU output, the restrictor or ballast - in
  any mode, `what to try` included. The gearbox lock is the driver's own
  report (Spa, 22 Aug); the rest is GT7's BoP as understood, erring safe.

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
