# Race planner — the plan George runs

**Ludo plans. George executes.** Ludo works before the green and after the flag;
George is the app's voice in the car and adapts live on telemetry and
push-to-talk. Ludo never tries to be the live voice — Leon races in VR and
Claude Code is not reachable from inside a headset.

---

## Never hand-roll the race model

The optimiser already exists, it enumerates every legal plan across stop counts
*and* compounds, and it filters infeasible plans **before** ranking — because a
version that ranked first and filtered second once made the most impossible plan
look cheapest.

```python
from pitcrew.store.db import Store
from pitcrew.strategy.evidence import build_inputs
from pitcrew.strategy.model import StrategyImpossible, recommend

store = Store()
inputs, evidence = build_inputs(store, event_id)
print(inputs.missing())                  # [] means every input was measured
for e in evidence:
    print(e.label, e.value, e.source)    # measured | declared | assumed | missing

try:
    plans = recommend(inputs)            # recommend(inputs, *, max_stops=4)
except StrategyImpossible as exc:
    ...                                  # SHOW THE REFUSAL. Never invent a plan.
```

`recommend()` takes two arguments; everything else lives on `RaceInputs`.
**`build_inputs` writes to the database** — it saves a track clock when the laps
carry one — so it is not read-only.

Two other gates worth knowing: `certify_for_event(store, event_id, plan)` checks
a plan somebody *else* wrote and returns refusals, warnings and — importantly —
**`unchecked`, the checks that could not run.** Silence is never a pass.
`build_plan(inputs, stops)` never raises for infeasibility; it returns
`feasible=False` with notes saying what ran out.

---

## Preflight — check these before proposing anything

1. **Which sheet is in the car**, and does the session point at *this* circuit.
2. **`race_type` before `race_laps`.** `race_laps` holds **minutes** when the
   race is timed, and `race_minutes` is never written. Reading one without the
   other briefed a 120-minute race as 120 laps.
3. **The binding constraint, and where it came from.** A plan capped by *"nobody
   has run a stint this long"* used to report itself as fuel-limited. Those
   demand opposite driving: fuel-limited means staying out is not available;
   evidence-limited means nobody has tried yet. Any pre-1.6 export reading
   `tyre` or `fuel` may mean neither.
4. **Was the wear rate measured at the multiplier being raced?** Multiplier
   linearity is assumed, never proven. Never silently convert.
5. **What compound the evidence came from**, and whether a qualifying session
   was pooled into a race fuel model. One was, and the plan came out rich.
   **The app records which is which:** `sessions.practice_intent` is `race`
   (the default) or `qualifying`, set on the Practice screen and exported as
   `meta.practiceIntent`. A `qualifying` session feeds no burn, wear or stint
   figure, and a `race` session sets no quali target; a practice session
   with no value predates the field (the last is 14 Aug) - ask him, do not
   assume `race`. Race sessions never carry one; their kind says it.
6. **Burn rises across a stint as the car lightens.** Never size a fill off an
   early-stint figure.
7. **Refuel rate: measured, not declared.** A declared rate has inverted a call
   before now.
8. **Optimise litres, not laps.** Fuel in the pit lane costs far more per unit
   than the lap-time it buys — the ratio is measured and it is not close.
9. **Stint length is the safety factor over the wear rate**, and say the margin
   lap is deliberate. The question is *how long can I run without falling off
   the cliff*, not integrating pace. Do not fit a linear model.
10. **A timed race's distance is an output of the plan.** A stop is paid in
    laps. Rank on distance, then time.
11. **Which class, which car, and whether it runs BoP** (plan row 2.7). In a
    manufacturer series the car is the roster's car for the class he is
    assigned *that round*, and the class moves. `bop_enabled` locks the
    gearbox and the power adjustments (`mechanic.md`). **And the board
    shows eight rows, overall**: in a multi-class field some cars are always
    off it, a car in the pit lane drops toward the cut, and nothing on file
    shows GT7's race board marking class - so no plan line and no call
    claims a class position or a class gap off the board, and a slower
    class being lapped is traffic, not a rival.

---

## The three failure modes, all on the record

**The evidence cap.** Stint length is the lowest of three ceilings — tyre, tank,
and the longest stint anyone has actually run. When the third binds, the plan is
shaped by inexperience and **the action that removes it is a practice run, not a
code change.** Say so, and say what the run would be worth in stops.

**The fuel margin.** He will not carry a spare lap in a lap race. The margin is
sized on measured burn scatter, and **any conservatism is priced in seconds and
said out loud**. Fuel carried across the line is time spent standing still.

**The pit-loss decomposition.** The total may be right while both its parts are
wrong — dead time and transit have each been out by more than a stop is worth,
in opposite directions, cancelling. They will not cancel on a splash-and-dash.
And a dead time that included a tyre change is not the same constant as one that
did not.

---

## What Ludo hands George

Two artefacts. The plan is what to do; the **playbook** is what to do when the
race stops matching it — and without it George is silently re-planning against
your intent.

**The plan** — stints, compounds, fuel per stint, pit laps, the binding
constraint *named honestly*, and the assumptions with their source classes.
Certify it before handing it over.

**The playbook** — the bounded adaptations George may make alone. Each entry is
a trigger, an action, and a limit:

> **IF** fuel falls more than *n* laps short of the flag **THEN** call
> short-shift first, lift-and-coast second **UNTIL** the deficit clears.
> **NEVER** a fuel-map change.
>
> **IF** the stop is missed by more than *n* laps **THEN** re-cost to the flag
> and offer stay-out **IF** the tank covers it.
>
> **IF** an incident costs more than *n* seconds **THEN** re-cost the remaining
> stints; do not re-plan the whole race.

### The write call — both doors validate, and a plan with no playbook is refused

**Since 7 Sep 2026 `write_strategy` refuses a plan that carries no `playbook`
list.** An empty list is accepted and means "no adaptations"; absent is
refused, because absent is the driver assuming a playbook exists. Every entry
is validated — trigger in `TRIGGERS`, action in `ACTIONS`, a non-empty `when` —
and the stored row carries the certificate's `warnings` and `unchecked`.

```python
from pitcrew.mcp import server          # the tools are plain functions too
import json

payload = {
  "author": "ludo",
  "stops": 1, "pit_laps": [11], "laps": 20,
  "stints": [
    {"laps": 11, "compound": "RS", "fuel_l": 85.4, "start_lap": 1,  "tyres": True},
    {"laps": 9,  "compound": "RS", "fuel_l": 69.4, "start_lap": 12, "tyres": True},
  ],
  "binding_constraint": "fuel",
  "notes": ["one line per assumption, with its source class"],
  "playbook": [
    {"trigger": "fuel_short",  "action": "short_shift",
     "when": "the tank misses the stop or the flag by more than 0.5 lap",
     "until": "the projection reaches the target with 1 L in hand"},
    {"trigger": "stop_missed", "action": "recost_to_flag",
     "when": "lap 12 has been completed without a stop",
     "until": "the stop is taken"},
    {"trigger": "incident",    "action": "report_only",
     "when": "more than 8 seconds lost", "until": "the lap is complete"},
    {"trigger": "rain",        "action": "report_only",
     "when": "the surface reads wet", "until": "the driver acknowledges"},
  ],
  "assumptions": ["burn 7.7 L/lap [MEASURED s127]", "refuel 1.003 L/s [MEASURED 4 Sep]"],
}
print(server.write_strategy(event_id, json.dumps(payload), label="ludo plan"))
```

The reply says `approved` (it certified and is armed for the next launch or
the next time the Race screen is shown), or `written: false` with `problems`.
`unhandled` lists the triggers with no entry — George reports those and
decides nothing, and the driver should hear that list in his brief.

The CLI is the same door with a file:

```bash
python -m pitcrew.strategy.handover --event 10 --file plan.json
```

It stores a **candidate** and the driver approves it on the Strategy screen
(or `store.approve_strategy(id)` from a script, journalled with
`note_engineer_write`). Either way a running app picks the approval up within
15 s or when the Race screen is next shown.

**Every stint after the first carries `tyres: true|false`, or the plan is
refused** - by every door: `write_strategy`, `propose_strategy` and the CLI
(since 11 Sep 2026, plan row 2.6). The app's own optimiser writes `true`,
because it prices every stop as a fresh set. A fuel-only stop may not change
compound, and `certify` counts the laps on one set across it. That is the decision
the box call speaks — "No tyres." or "RS on." — and the board shows. Omitted,
George names the compound as he always did, which under a helmet reads as
"fit RS"; only 4 of 64 stored stints ever carried it. Stint 1 is exempt: the
car starts on what it is on.

### Fuel-save stints, the beep George runs, and the race's lap ceiling (15 Sep 2026)

Three plan fields, refused by name at every door when malformed
(`handover.fuel_plan_problems`, read by `validate` and `certify` alike):

- **`max_race_laps`** - the most laps the race can run. George caps his
  laps-left count at it, treats the count as firm there (no spare lap in the
  fill), and calls the flag on it. Set it only from a measured crossing - at
  Sardegna lap 28 ended with 3.1 s on the clock. A plan covering exactly the
  ceiling while the clock model allows one fewer certifies **with a warning**,
  not a refusal.
- **`fuel_burns: {"save": L/lap, "full": L/lap}`** - MEASURED, save below full.
  Required when any stint is fuel-save. The gate reaches a fuel-save stint on
  `save`; George prices a switch to full revs with `full`, and replaces both
  with this race's own burn after two clean laps on a column (the other column
  scaled by the plan's ratio).
- **`fuel_save: true|false` on a stint** - the beep plays the issued table's
  fuel-saving points from the start of that stint. **Any stint naming the key
  hands the beep to George** (`calls.fuel_mode_wanted`): to a stop on a
  fuel-save stint it holds saving; on the run to the flag it goes to full revs
  once the tank reaches at the full burn with the fill's margin and 1 L in
  hand, and back to saving when it stops reaching. Saving beyond the saving
  beep is the fuel call's job ("Save N litres a lap", lift). A plan that never
  names the key leaves the beep exactly as before.

**The deliverable is three things, from Suzuka on:** the plan (with its tyres
decisions), the playbook, and the engineering sheet - every `race_knowledge`
field filled, or a line saying why it cannot be.

Anything outside the playbook is George reporting, not deciding. **He may always
say "the plan no longer fits and I cannot fix it from here"** — that is a useful
call and it is honest.

---

## Qualifying

Different problem: one lap, unconstrained by survivability, where the race is a
control problem over many. A race sheet leaves adjustment headroom on the MFD; a
qualifying setup can and should spend all of its range on the one lap.

Use `pitcrew.race.qualifying_plan.build(...)` and
`pitcrew.race.quali_fuel.qualifying_fuel(...)` — both exist and both populate
refusals rather than raising.

A quali plan may honestly contain: tyre-prep from the event's own measured
temperature window, fuel for the flying laps at map 1, how many runs fit, and
whether to go again. **It may not contain sector targets** — the smallest
honestly speakable sector delta is wider than the calls anyone would make from
it, and sector times do not correlate across sessions. Gap creation has no
substrate in the app at all.

⚠️ The out-lap doctrine is **contested**: the claim that GT7 has no meaningful
warm-up phase contradicts the tyre model, and 1.71 adjusted tyre heating. **Plan
out-laps as if warm-up matters** until that is tested.

---

## The incident ledger — the driver-facing half

Incidents are seconds in a race, which is why they sit here rather than in a
role of their own. What survives measurement, and it is worth knowing which:

- **Incidents are the largest coachable loss** and account for essentially all
  of the gap between his worst race and his best. The two clean races are the
  two he won.
- **Lap one costs time in every race without exception.** It belongs in a
  pre-race brief, never in a live call. *(Open for the driver: plan row 2.11
  says debrief only, never in a brief. The two agree it is never a live call;
  which governs the brief is his to settle - surfaced, not averaged.)*
- **Warm-up laps two to four cost a little, and it is gone by lap five.**
- **Session scatter is reported as a state, never banked** as a loss.

What is refuted, and must never be said: race-day nerves (they cost nothing —
his race pace is *faster* than practice); *"today is a scrappy day, dial it
back"* (not knowable early); a post-incident step-down (not established); small
off-tracks costing time (they cost nothing). **Incidents are memoryless** — you
cannot predict the next from the last, so there is no such thing as a warning.

`pitcrew.analysis.incidents.find_incidents(laps, evidence_for)` needs a real
time loss **and** a corroborating channel — never one signal alone. An incident
lap leaves the counted set (pace, fuel, strategy) and stays in the diagnostic
set (corner aggregates).

---

## After the flag

`pitcrew.race.outcome.race_outcome(...)` states facts without judgement, and
`pitcrew.race.expectations.ExpectationTracker` compares plan against reality —
**fuel is actionable; lap time only ever confirms.**

Then record it (SKILL.md, *The record*) and route the findings
(`references/learning-loop.md`). A debrief that is not written back is a race
driven twice.
