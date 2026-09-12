# Dispatch

Moved out of `SKILL.md` (plan row 2.9), unchanged. The skill keeps the heading and points here.

## Dispatching the crew

Three specialists, and they are **dispatch shapes, not authorities**:

- **Mechanic** — sliders, sheets, ranges, symptom→cause, what is in the car.
- **Driver model** — his style, his refusals, his symptom vocabulary, and what
  he needs *from* the car. Hands the Mechanic a brief, never a slider value.
- **Race planner** — stints, fuel, pit, quali, the plan George runs. Also owns
  the incident ledger, because incidents are seconds in a race.

Two rules when you dispatch:

1. **The refusal card travels in the prompt, verbatim.** A subagent inherits
   none of your context. One sent to read 17,000 frames without it will return a
   confident per-corner finding, and it will come back looking authoritative.
2. **A subagent returns a proposal, never a conclusion.** You check it before it
   reaches him.

Tyre wear sits between Mechanic and Race planner: **`tyre_models` is the single
source.** Both read it; neither computes its own. The Mechanic may say a change
*should* move wear; only a `speakable=1` model says by how much.

---

## Proposing something new

Ideas are an output *mode*, not a specialist. A proposal is a labelled block:

> **[HYPOTHESIS]** what you think is true · **[BASIS]** what suggests it, with
> source class · **[TEST]** the run that settles it · **[COST]** what it
> displaces · **[FALSIFIED BY]** what result would kill it.

Four gates, and the first does the work:

1. **The test must clear the measured noise floor of the instrument it uses,
   and you state that floor numerically.** This is what stops "brake 10 m later
   at T4, let's try it over five laps" — which is labelled, testable, and
   forbidden.
2. **Pre-20-Aug-2026 evidence is a hypothesis source, never a justification.**
3. **Price it in laps.** Three clean laps minimum per change — so an
   idea costs at least three laps and must say what it displaces.
4. **Never propose:** per-corner input coaching · a fuel-map change or A/B ·
   brake bias forward · a spare fuel lap in a lap race · any write to any store
   · anything touching GT7 game state.

---

## Things that look authoritative and are not

Check `tools/data_health.py` rather than trusting these:

- `race_revisions` is the **radio-call ledger**, not setup revisions.
- `tyre_models.confidence = 'high'` on a **baseline** is a grip level, not
  permission. Only `speakable = 1` may be spoken — and some `speakable = 0`
  verdicts are unimplemented stubs rather than evidence.
- `wear_predictions` is a **fossil** — one hand-seeded row, referenced by no
  code, not in the schema. Do not build on it.
- `radio` now has a writer (26 Aug 2026) and holds **his** side of the
  conversation, including the presses the engineer refused. **Every row
  predating that date is missing its verdict**, and a null `action` means
  not recorded, never acted. The engineer's own calls still live in
  `race_revisions.reason`.
- **This codebase has built both ends and skipped the caller five times.**
  Before relying on a table, check it has a writer.

---
