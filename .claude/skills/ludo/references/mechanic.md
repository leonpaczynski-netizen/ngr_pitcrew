# Mechanic — the setup pass

Procedure only. Slider semantics, symptom tables and per-car values live in the
knowledge base — reach them through the `gt7-brain` skill, which routes to the
right file. Nothing here restates a measurement.

---

## Before a slider moves

**The league's limits first.** `events.power_limit_bhp` and
`events.weight_limit_kg` carry the hub's `carRegulations` (Porsche Cup 509 BHP
/ 1,243 kg; Supercars 1,335 kg). A sheet whose ECU, restrictor or ballast puts
the car outside them is not a sheet - the lobby refuses it - so read them off
the event row and say them on the sheet before anything else is priced. Where
the row is NULL the league did not limit it; that is not zero.

**Rank zero first, both halves** (SKILL.md step 1). A correct telemetry reading
against a wrong setup record produces a confident wrong answer, and that has
happened in five consecutive sessions.

Then **diagnose by phase and throttle state.** The knowledge base's symptom
tables are cause-ranked and need no baseline — but they fork on one question
that decides which table you are even in: *does the symptom happen on throttle
or off it?* Reading the wrong side of that fork produces a confident answer from
the wrong table.

The four questions worth his attention, when the data cannot settle them:

1. **Where is your right foot when it happens?** (the fork above)
2. **Which corners are fine?** — a symptom everywhere is the platform; a symptom
   in one phase is that phase's lever.
3. **From lap one, or does it develop?** — separates setup from tyre state.
4. **Is it built as written?** — rank zero, asked plainly.

---

## Choosing the lever

The knowledge base carries a ranked change hierarchy — hardware, then brake
stability, front grip, differential, ride height, aero, brake bias. Use it to
choose **among controls that already fit the diagnosis.** It is not a licence to
reach for a higher-ranked control once the symptom has been traced to a specific
one.

**One change per run, three clean laps.** Not suspended for the 1.71 rebuild —
with every baseline unverified, a two-change run is uninterpretable.

**A telemetry-only flag may not buy a change.** It buys a question or a
measurement. This was overridden once and bought nothing for ride height and
rake.

---

## What the app can verify, and what it cannot

- `pitcrew.analysis.gearing.matches_sheet(laps, sheet_gears)` — **the only setup
  value telemetry can verify.** Element-wise, final drive deliberately excluded.
- `pitcrew.analysis.corners.aggregate_corners(...)` — per-corner metrics, each
  mean carrying its own sample count, with flags that fire only when a quarter
  of laps show them. Understeer is deliberately **not** a flag any more; the old
  detector's shape made a neutral car flag more at speed by construction.
- `pitcrew.analysis.corner_findings.analyse(model, laps) -> Report` — the
  post-session debrief that replaced live corner coaching. **`Report.silent`
  names the corners that cannot carry a claim.** Report those as silent; do not
  omit them.
- `tools/where_the_change_landed.py --before <sessions> --after <sessions>`
  — **where on the lap a change landed.** Sector medians with their own spread
  (a delta inside it prints as *inside the scatter*, which is a refusal), and
  with `--bins` a 100 m attribution that sums back to the delta as an
  identity. Bins are labelled from the BEFORE run only, so the classification
  cannot be moved by the change being measured. It refuses when the two runs
  were cut on different sector models and warns when the compound differs.
  **This is the answer to "the lap time cannot show a tune working"** — the
  lap cannot, the parts can.
- `RangeRecord.fraction_of_range(key, value)` — advisory only. Nothing refuses
  on it, so a value outside range still needs your eyes.

Everything else on a sheet — twenty-one of twenty-three values — has **no ground
truth in the feed.** For those, the record is what he tells you, and the only
defence is provenance and confirmation.

---

## Validation, before anything is filed

`SetupSheet.validate()` refuses: a key outside the shared vocabulary; a
non-numeric value; **a negative on an unsigned key** (only toe front, toe rear
and brake balance take a sign); a shift-rpm entry outside its gear or rpm
bounds; more than nine gears; a non-positive ratio; **gears not strictly
descending**. It does *not* check slider ranges.

---

## The deliverable

Two artefacts, always both.

**1. The human sheet.** GT7's in-game order exactly, race primary and qualifying
as a delta. Every per-car value given three ways — the absolute, the position in
its range, and the physical meaning — because one alone is unenterable, one
alone is meaningless across cars, and one alone is unverifiable. The format is
specified in the knowledge base; follow it rather than inventing a layout.

Six things travel with it, and a sheet without them is not finished: deviation
notes one per moved value, the gearing derivation, the strategy note, three
things to test first in priority order, confidence flags, and the paste block.

**2. The paste block.** The parser reads `sheetName`, `values` and `gears` and
nothing else. Numbers only inside `values`; signs explicit; gears in order.
**Omit a key entirely when it does not apply — never send it as null**, because
a null on a known key is dropped silently and you will not be told.

---

## Then record it

Every change is an experiment (SKILL.md, *The record*). The setup delta is now
filed automatically when the next session opens against the new sheet — but the
**prediction is yours**, and it is the part that makes the ledger learning
rather than logging. Say what the change should do, and what result would prove
it wrong.
