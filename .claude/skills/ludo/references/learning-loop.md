# The learning loop — which store, and what makes it learning

*"Everything I do with Ludo needs to be recorded properly and used for learning
for future."*

There are five stores and, before this file, no rule for which one a finding
belongs in. The consequence is on the record: one statistic carries three
different values across two documents and the database, because each was written
once and nobody re-queried; and a session's measured findings sat in `docs/` and
in memory for a day with the write-back gated on the driver saying "go", which
never came.

---

## Route every finding to exactly one store

| The finding is… | It goes to | Because |
|---|---|---|
| A **measurement** — a rate, a spread, a per-corner metric | `data/pitcrew.db`, via the derivation tools | It must be re-derivable. A number typed into prose cannot be re-checked |
| A **setup change** | `setup_changes` — filed automatically when the next session opens against the new sheet | It is an experiment, and it must be tied to the run that tested it |
| The **reasoning** behind a sheet | `brain/_inbox/setups/YYYY-MM-DD-<car>-<circuit>[-revX].md` | The database has nowhere to store *why*, and why is what a later revision needs |
| A **doctrine change** — something believed and now disproved | `brain/RECONCILIATION.md`, with the supersession recorded | A rule that was believed and refuted is evidence about the fault *and* about how it survived scrutiny |
| A **durable fact about him, the rig, or the project** | Claude's memory directory | It is loaded automatically next session. This is the only store that reaches the next conversation unprompted |
| A **one-off analysis** | `docs/` | And then extract whatever is durable into one of the above — `docs/` is read by nothing |

**A finding written in two stores becomes two answers.** Pick one, and reference
it from anywhere else that needs it.

---

## What he asked on the radio is evidence, and it is the only kind he generates

Every other store here records what the app measured or what a sheet said. The
`radio` table records **what he chose to ask**, which is the one signal that
comes from him unprompted — and the questions the engineer could not take are
the most useful rows in the whole database, because each one is a hole in the
vocabulary in his own words.

Run it in every debrief:

```bash
python tools/radio_review.py --event <id> --misses
```

Refusals first, repeats counted. Each candidate needs a decision, and there are
only three:

1. **It belongs to an existing intent** — add the phrasing to that intent's
   tuple in `pitcrew/engineer/intents.py`, then **re-run
   `python tools/gate_bands.py`**. `gate.py` carries the standing instruction to
   re-measure when the phrase list changes, and adding phrases is not free:
   measured 26 Aug, nine of twenty-nine held-out questions were being answered
   as the *wrong* question, and a widened `gap` intent pulled a fuel question
   into itself. **An addition that raises "reached" while raising "wrong" has
   made the engineer more confident and less correct.**
2. **It needs a new intent** — only if the snapshot can actually answer it.
   Check `controller._ptt_snapshot` for the keys before promising anything.
3. **The feed cannot answer it, ever** — then it gets an intent whose job is to
   refuse *by name*, like `gap` does for anything about other cars. A named
   refusal is worth an intent: he learns once and stops asking. "Say again"
   teaches him the app is broken.

**Never add a phrase to `PHRASES` and to `gate_bands.py`'s probe set.** A probe
in the phrase list scores ~0 against itself and grades its own answer key; the
tool now refuses to run when that happens.

---

## What makes a record learning rather than logging

The project records values, calls and changes. It records **no predictions** —
and without a prediction, an outcome teaches nothing. So every Ludo decision
carries four parts, and the fourth is the one usually missing:

1. **What was decided.**
2. **The evidence**, each item with its source class.
3. **What this predicts** — what should be true if it is right, stated so a
   later session can check it without re-reading the argument.
4. **What would falsify it**, and the run that would settle it.

**A prediction with no falsifier is an opinion.** If you cannot say what result
would prove it wrong, say that instead — it is a more honest output than a
confident number.

---

## Open a session by closing the last one

Before any new work: **check open predictions against what actually happened.**
That is the loop closing. Three outcomes, and all three are worth recording:

- **Confirmed** — say so, and say by how much. Raise the confidence.
- **Refuted** — say so plainly, amend `brain/RECONCILIATION.md`, and keep the
  superseded claim with its supersession recorded.
- **Still open** — say what is still missing and what would settle it. Very
  often the answer is a specific run, and naming it is the most useful thing in
  the session.

**Refutations are the most valuable thing you can write down.** They are what
stop the same wrong answer being re-derived in a month.

---

## The obligations that are never skipped

- **After any look at session data, write to memory before the turn ends.** Not
  just conclusions — the figures, the sample counts, and what was refuted. A
  session read and not written down is a session driven twice.
- **When a verdict reverses, amend `brain/RECONCILIATION.md`.** It exists
  because the three stores drift, and it is the only place that records that
  they did.
- **Never delete a superseded claim.** Record what replaced it and why.

---

## Before you rely on a table, check it has a writer

This codebase has built both ends of a mechanism and skipped the caller **five
times** — the setup-change ledger (fixed 25 Aug), the radio log, the wear
prediction table, the question gate, and the MCP seam. Each looks complete from
either end.

So: a table with rows is evidence; a table without rows may be a gap, a fossil,
or a design that was never built. `tools/data_health.py` distinguishes them for
the ones that matter. **`wear_predictions` in particular is a fossil** — one
hand-seeded row, referenced by no code, absent from the schema. Do not build on
it, and do not cite it as a precedent.

---

## What already works, and is worth protecting

- **`pitcrew/tests/test_brain_reconciliation.py`** — the only automated check
  that the knowledge base and the code still agree. It asserts in **both**
  directions, including that known defects still exist, so fixing one fails the
  test and the news is good. A failure there means a document needs amending,
  not that something broke.
- **The supersession rule** in `brain/README.md`.
- **Version as a precedence tier** — current-version laps used alone where
  enough exist, older held back rather than blended, and the plan says out loud
  when it rests on pre-patch evidence.
- **Model refitting with scope enforcement** — `derive_grip_observations` then
  `fit_tyre_models`, both idempotent, both versioned, and the fit writes
  `speakable` at fit time so the voice layer reads a boolean it does not get to
  argue with.
