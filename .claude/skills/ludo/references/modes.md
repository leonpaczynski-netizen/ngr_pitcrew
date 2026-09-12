# Modes

Moved out of `SKILL.md` (plan row 2.9). The skill keeps the heading and points here. Edited since the move: two cross-references that pointed "above" and "below" now name the file they mean.

## refine — a sheet ran and he has a report

1. **Rank zero, both halves** (spine step 1). The record has been wrong in five
   consecutive sessions; this is the mode where that costs the most, because a
   correct reading against a wrong record produces a confident wrong answer.
2. **The ledger, before any hypothesis.** `brain/ledger/<car>-<circuit>.md`:
   what has been tried on this car here, in which direction, by how much of
   the slider's range, on which instrument, and what came of it. A change
   already refuted in one direction is not a new idea in that direction, and
   **`unresolvable` is not `refuted`** — a refutation carries a direction.
   Every change this session makes is a new row there (plan row 2.1); the
   value itself stays in the car-state file and nowhere else (§1a).
3. **What else changed.** Compound, fuel load, session type, game version. The
   reference lap has no compound filter, so "faster on the new sheet" can be a
   softer tyre wearing a setup's clothes. Name the confound or rule it out.
4. **His report is the brief**, in his words, with throttle state resolved —
   `references/driver-model.md` has the four fields, and the third decides which
   symptom table applies at all.
5. **A baseline, counted by the tool's definition** (plan row 2.2). Which
   sessions, and how many clean laps as `tools/where_the_change_landed.py`
   counts them (`off_track_s == 0`). Where another count disagrees - the
   car-state file said 4 and 5 at Deep Forest 133→134 where the tool found 0
   and 1 - **the disagreement is the finding**: surface it, say which
   definition the comparison uses, never average them (eval 13).
6. **One change, three clean laps at least, written as an experiment
   before the run** - in its ledger row: the key, the direction and the delta in percent of slider range; the
   instrument and its *measured* floor; **a no-change control**; the
   prediction and a complementary falsifier. A coupled set only as a named
   set (row 2.3). **The control is the drift between sessions, not the
   scatter inside one**: at Sardegna on 5 Sep, +0.633 g cleared its
   within-session floor of 0.532 g and died, because a no-change pair moved
   +0.411 g on its own - learning is one-directional and flattering, so be
   most suspicious of a result that agrees with you (eval 12).
7. **The verdict on the same instrument, against the control's drift** -
   confirmed, refuted (with its direction), or unresolvable, and the ledger
   row closed with it. Read where it landed, not whether the lap moved: the
   lap time cannot answer this (see `references/where-the-change-landed.md`) -
   sectors first, distance bins where the sectors are silent. **An A-B-A
   return leg where a run is cheap** - it is the one control learning
   cannot fake. Where there is no valid control, say "I cannot see that" and
   let his report carry the finding.
8. **If a ratio moved, the shift table moved with it.** Re-issue it in the
   same message — the recipe and the `write_shift_points` call are in
   `SKILL.md`, under *Every sheet carries its shift table*, which is the one
   step of these modes you cannot execute from this file alone.

**Platform or trim — decide which before step 6** (plan row 2.3). A setup has
two layers and they need opposite methods
([[reference-setup-platform-before-sliders]] in memory):

- **The platform** is ride height, natural frequency, compression damping and
  downforce — **one decision, not four**, because each works only at the
  value the others allow. It changes as **one named coupled set** (one ledger
  row, keys joined with `;`), judged for its **cost on clearance
  instruments** — the body-height channel's share of frames below the car's
  reference, the per-wheel suspension minimum against a steady-state
  reference (CLAUDE.md §3.3.3: bottoming is inferred, never read) — and for
  its **merit by the driver**. A coupled set cannot be attributed key by key
  on telemetry, so do not try.
- **The trim** is one balance slider — ARB, diff, camber, toe, rebound, brake
  bias — on the channel the axis register names for it, by step 6's method.
- **One-change-at-a-time cannot find a platform, and it rejects the right
  direction**: a change that only works as part of a set tests as a failure
  on its own (Spa, 31 Aug: `arb_f` softer on a soft, high car only added
  roll). **Raise ride height last** — spring rate, then compression damping,
  then ride height (*"a last option not a first"*, the driver, 1 Sep). And
  **never copy a reference platform in pieces**: its ride height without its
  springs is the one way to be worse than either.
- The worked example: Sardegna, 9 Sep — a front spring was a platform move,
  so no single-slider change was issued, and the fuel/wear stint became the
  platform sweep for free.

## quali — one lap

**No qualifying session has ever been recorded.** The reference is the best
counted *practice* lap (`race.qualifying.reference_lap`), and saying so is part
of the answer: quali advice here rests on practice evidence, which is a
different thing from qualifying evidence. **The nearest evidence is marked:**
a practice session run as a quali simulation carries
`sessions.practice_intent = 'qualifying'` (13 on file, 17 Aug - 7 Sep; set on
the Practice screen, exported as `meta.practiceIntent`). Read those for the
lap and the out-lap, and never feed them to a race burn, wear or stint figure
(`references/race-planner.md` preflight 5).

1. **The out-lap owns the result.** Warm-up is the whole game, and **no optimal
   tyre window has ever been published for GT7, by anyone**. So: a warm-up
   *plateau* call, never "in the window" or "push to get temperature into it".
   Fresh sets arrive at 45 °C or at exactly 70 and nobody knows why — treat a
   fresh set's opening temperature as unexplained, never as a target.
2. **A quali setup may spend its whole range on one lap.** Tyre life, fuel
   saving and consistency-over-a-stint are race concerns and do not apply.
   Importing them is this mode's failure.
3. **Minimum fuel** — `race.quali_fuel.qualifying_fuel(...)` exists and
   populates the plan; `race.qualifying_plan.build(...)` for the rest.
4. Deliver: prep laps, the flyer, and what he should feel on the out-lap.

## debrief — after the flag

**`tools/debrief.py <event>` runs the whole list, in this order** (plan row
2.5), and every section says what it could not see:

1. **His account, free and unprompted, before he is shown any data** — whatever
   he says, in his words (`--report FILE` prints it at the top). Numbers shown
   first lead him; his account is primary evidence and everything after it
   corroborates. **It asks him nothing, so spine steps 3 and 4 still hold:**
   the telemetry is read before any question, and then at most four, one at a
   time, each buying what the feed cannot carry. *(Open for the driver: plan
   row 2.5 asks for a per-corner grid, each phase scored 1-5, before the data
   - on a twelve-corner circuit that is some forty prompted answers, which
   step 4 does not allow. Until he settles it, the grid is taken only if he
   volunteers it, or inside step 4's four questions. The row says four
   phases; `driver-model.md` names three - entry, mid, exit - and which the
   grid uses is part of the same open question.)*
2. **The open predictions** for this car at this circuit, off `brain/ledger/`.
   That is the loop closing; a debrief that does not is a log. What was
   predicted, what happened, and which of the two was right — including when it
   was him, which it has been four sessions running.
3. **Where a change landed** is a sector-and-bin question, not a lap-time one:
   `--before`/`--after` runs `tools/where_the_change_landed.py`'s table.
4. **How it was driven** — coast share and upshift rpm, per session.
5. **The driver as a variable** (row 2.11) — incident rate, lap-one cost and
   consistency per session, each with its n. **Debrief only**: never in a brief,
   never priced into a plan, never a warning, never per corner. *(Open for the
   driver: `race-planner.md` puts lap one's cost in the pre-race brief. The two
   agree it is never a live call; which of them governs the brief is his to
   settle - surfaced, not averaged.)*
6. **George's calls against what followed** — the verdict filed on each.
7. **Plan versus actual, from the data and never from the plan** — burn, lap
   time and wear against `expects`, stints planned against run, each stop's
   measured pit loss against the event's own figure, named by its source. The app once lost a whole lap in
   a pit stop by preferring the lap-time sum over the wall clock, and reported
   the plan's own number as the outcome. **Incidents are seconds**: they belong
   in the ledger and in the total.
8. **The radio review** — `learning-loop.md`. His own questions are the only
   evidence in the archive that he generates unprompted.

Then close each open prediction in its ledger row and commit `brain/` — one
commit per debrief.
