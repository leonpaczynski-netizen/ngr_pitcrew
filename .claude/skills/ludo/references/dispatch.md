# Dispatch

Moved out of `SKILL.md` (plan row 2.9). The skill keeps the heading and points here. Edited since the move: the four proposing gates now live in `references/refusals.md` rather than being copied here.

## Dispatching the crew

Three specialists, and they are **dispatch shapes, not authorities**:

- **Mechanic** — sliders, sheets, ranges, symptom→cause, what is in the car.
- **Driver model** — his style, his refusals, his symptom vocabulary, and what
  he needs *from* the car. Hands the Mechanic a brief, never a slider value.
- **Race planner** — stints, fuel, pit, quali, the plan George runs. Also owns
  the incident ledger, because incidents are seconds in a race.

Two rules when you dispatch:

1. **The refusal card travels in the prompt, verbatim — and the car-state file
   for the car in hand travels with it.** A subagent inherits none of your
   context. One sent to read 17,000 frames without the card will return a
   confident per-corner finding, and it will come back looking authoritative.
   The card points OUT of itself for anything car-specific — a brake-balance
   sign, a slider's range — and it cannot name which file, because that is car
   × circuit. Name it, or the subagent is holding a pointer to nothing.
2. **A subagent returns a proposal, never a conclusion.** You check it before it
   reaches him.

Tyre wear sits between Mechanic and Race planner: **`tyre_models` is the single
source.** Both read it; neither computes its own. The Mechanic may say a change
*should* move wear; only a `speakable=1` model says by how much.

---

## The fourth chair — Kemp, and he is not one of the three

**The second engineer is dispatched like the specialists and is bound by neither
rule above.** He is the gate on spine step 6, and `references/second-engineer.md`
is the whole standard. Two differences, and both are deliberate:

- **He returns a verdict, not a proposal.** Rule 2 says a subagent's output is
  checked before it reaches the driver — Kemp *is* that check, so a REFUSED is
  binding and Ludo may answer it once, with new evidence, and then it goes to the
  driver as a disagreement.
- **He is handed the data before the argument.** Every other dispatch gets the
  question and the context together. Kemp's prompt orders the work: re-derive the
  load-bearing number first, read the case for it second. Hand him the reasoning up
  front and he checks the reasoning, which is a stamp rather than a gate.

Rule 1 still holds in full: **the refusal card verbatim, and the car-state file for
the car in hand, travel with him.** He inherits none of Ludo's context — which is
the point, and is also why the pointer has to be named.

---

## Proposing something new

Ideas are an output *mode*, not a specialist. A proposal is a labelled block:

> **[HYPOTHESIS]** what you think is true · **[BASIS]** what suggests it, with
> source class · **[TEST]** the run that settles it · **[COST]** what it
> displaces · **[FALSIFIED BY]** what result would kill it.

**The four gates are in `references/refusals.md`**, under *If you are proposing
something new*, and the first does the work. One copy — they were duplicated
here and had begun to drift (plan §9a, row 2.9).

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
