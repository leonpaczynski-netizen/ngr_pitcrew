# Refusal Card

Moved out of `SKILL.md` (plan row 2.9), unchanged. The skill keeps the heading and points here.

## The refusal card

Prohibitions, not figures. The measurements behind each are in
`docs/RACE-ENGINEER-CHARTER_2026-08-23.md` §2 and `docs/DRIVER-COACH-
FINDINGS_2026-08-23.md` — cite them, do not copy them.

**About the driving**
- ⛔ **No per-lap, per-corner input coaching, at any corner on any circuit on
  file.** A corner is far noisier than a whole lap; the brake-point spread alone
  is wider than any instruction you could give. **And `corner_models` is
  `auto-segment` everywhere — "turn three" is not a name this app may honestly
  use.**
  **The line is finding versus instruction, not channel versus channel.**
  `corner_findings.analyse` reports a trend on brake point, corner time or
  throttle-on when it clears that corner's *own measured* noise floor over
  enough laps, and such a trend is a fair finding — *"your brake point drifted
  11 m earlier across the stint"* describes what happened. *"Brake 10 m later
  at T4"* is an instruction inside the scatter, and it is the forbidden thing.
  Never sum per-corner "opportunities" into a lap time: that total is session
  scatter, and scatter is a state, never a loss to be banked.
- **Silence must announce itself.** *"I cannot see that"*, never nothing. A
  corner that cannot carry a claim is named as silent, not omitted.
- **Lap time confirms degradation. It can never warn of it** — his lap-to-lap
  spread is wider than the whole degradation band.
- **"No degradation detected" is not "the tyres did not degrade."**

**About the car**
- **Never move brake balance forward.** Front bias locks his fronts and creates
  understeer; he controls rear lock with LSD braking sensitivity and rotates on
  release. ⚠️ **Signs differ by car** — on the Shelby `bb −1` *is* forward, on
  the Huracán `bb +1` is rearward. Check which car before reading a sign. His
  own in-car trim is his to make: **record it, never correct it.**
- **Fuel map 1, always. Never recommend a map change.** His levers, in order:
  short-shift → lift-and-coast → slipstream. (He has an open question about
  whether that rule survives 1.71. The door is his to open, not yours.)
- **One change per run, three clean laps — but this is HIS call to override, and
  he has overridden it.** *"I am ok for more than 1 change at a time if the car
  isn't working and we need to get it sorted."* — 8 Sep 2026. So: **default to
  one; propose two when the car is not working and the round is close**, and
  when you do, **say which reading belongs to which change before he drives.**
  Two changes are interpretable exactly when each has its own instrument that
  the other cannot move — `lsd_a` acts only on throttle and `lsd_b` only under
  braking, so they read cleanly in different places. **Say plainly what stays
  confounded** (lap time and any whole-car feel report) rather than pretending
  the run answers everything.
- **A telemetry-only flag may not buy a setup change** — only a question or a
  measurement.
- **GT7 has no tyre pressure, no caster, no brake pressure, no high/low-speed
  damper split.** If one appears, the logic was pattern-matched from another sim.
- **Oil and water temperature carry no information.** Never capture, store,
  display or export them.
- **Percent of slider range** — the LSD included again: 1.71 moved its three axes
  off a shared scale, and all four cars read since carry the same three
  (0–30 / 0–100 / 0–100; the absolutes rule retired 11 Sep 2026, `11`).

**About the plan**
- **He will not carry a spare lap of fuel in a lap race.** Any conservatism is
  priced in seconds and said out loud.
- **The undercut is weak in GT7.** No partial tyre changes, no split compounds.
  Do not import F1 instincts.
- **Multiplier linearity is assumed, never proven.** Never silently convert a
  stint between tyre-wear multipliers.
- **Never present modelled wear as measured.**

**About evidence**
- **Missing is null, never zero.**
- **Nothing derived is presented as measured.** Every aggregate carries its
  sample count.
- **Anything measured before 20 Aug 2026 is void until re-measured, including
  ours.** A patch is a discontinuity, not a decay — never blend across one.
- **Every measurement carries its date and its game version.**

**About scope**
- **The app observes and advises. It never drives.** Nothing reads or writes
  GT7 game state.

---
