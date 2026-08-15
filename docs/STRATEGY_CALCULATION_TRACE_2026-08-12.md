# Strategy calculation trace — 12 Aug 2026

Audit of the race strategy path in NGR Pit Crew. No source was changed. Every
claim carries `file:line`. Runtime checks were run against a **copy** of
`data/pitcrew.db` (the live DB is at `user_version` 2 and opening it with
`Store` would migrate it to 3 — see §0.3).

---

## 0. Scope correction — read this first

The commissioning prompt was written against the **previous** codebase. Three of
its premises do not hold here, and the audit was re-scoped accordingly.

### 0.1 The referenced artefacts no longer exist

Commit `6a9117b` ("refactor: delete the old app, and add strategy.outcome",
11 Aug 2026) deleted **1586 files** — the whole of `docs/`, `main.py`, `ui/`,
`strategy/`, `services/` and `tests/`. Verified:

```
git show --diff-filter=D --name-only --pretty=format: 6a9117b | grep -c .   → 1586
```

| Prompt reference | Status |
|---|---|
| `docs/UAT_2026-08-07_DEFECT_REGISTER.md` | Deleted in `6a9117b`; readable only at `6a9117b^` |
| `docs/RACE_STRATEGY_TARGET_DESIGN_2026-08-12.md` | **Never existed in any commit or on disk.** The prompt's preamble asked for it to be saved before pasting; it was not |
| `strategy/tyre_curves.py` | Deleted |
| `ui/dashboard.py`, `ui/live_shell_bridge.py` | Deleted |
| `data/track_convergence.py:148` (defect D1) | Deleted |
| "hundreds of pre-existing modifications" | Working tree has **one** untracked path, `_to_delete/` |
| "11,000 passing tests" | Current suite is **710** tests in 30 files under `pitcrew/tests/` |

A copy of the old tree survives in the git worktree
`.claude/worktrees/pensive-banach-78f43f/`. It is not the audit target and is
excluded from every search below.

**Consequence.** Part 1 (this document) is answerable from the code and is
delivered in full. Part 2 (gap register *against the target design*) and Part 3
(a plan sequenced by that design's §11) cannot be produced without the design
document. They are not attempted here. See the chat report.

### 0.2 The "1 L/s" refuel rate is not a hardcoded constant

It is **driver-entered event data**, and the value in the live database really is
`1.0`:

```
sqlite> select refuel_rate_lps, pit_loss_secs from events;
1.0 | 19.0
```

The *code* default is `2.5`, in three places
(`pitcrew/strategy/model.py:136`, `pitcrew/store/schema.py:71`,
`pitcrew/prompts/context.py:32`). Full provenance in §6.

### 0.3 Live database state

`data/pitcrew.db` is at `user_version` 2 against `SCHEMA_VERSION = 3`
(`pitcrew/store/schema.py:42`) — the per-corner wear migration has not been run
on it yet. It holds one event, four practice sessions and **six laps**, none
flagged in-lap or out-lap, all compound-tagged. All runtime probes below used a
copy so the live file was not migrated.

---

## 1.1 The path

There is one shell. There is no classic/new split — `ui/dashboard.py` is gone.

### Pre-race — building a plan

```
Strategy screen "Build" button
  └─ StrategyScreen.build_requested                      pitcrew/ui/strategy_screen.py
     └─ Controller.build_strategy()                      pitcrew/controller.py:906
        │   wired at                                     pitcrew/controller.py:215
        ├─ Controller.active_event()                     pitcrew/controller.py:910
        ├─ build_inputs(store, event_id)                 pitcrew/strategy/evidence.py:189
        │  ├─ store.get_event                            pitcrew/strategy/evidence.py:191
        │  ├─ _lap_inputs → store.list_event_laps         pitcrew/strategy/evidence.py:54,62
        │  │  └─ _laps_to_hydrate (last 6 laps/compound)  pitcrew/strategy/evidence.py:92
        │  ├─ counted_laps                               pitcrew/analysis/session.py:153
        │  ├─ median fuel burn                           pitcrew/strategy/evidence.py:198
        │  ├─ green_lap_reference_ms                     pitcrew/analysis/session.py:157
        │  ├─ wear_per_lap  (driver gauge)               pitcrew/analysis/wear.py:152
        │  ├─ _fuel_capacity (from session row)          pitcrew/strategy/evidence.py:85
        │  ├─ reference_compound                         pitcrew/strategy/evidence.py:110
        │  ├─ compound_profiles                          pitcrew/strategy/evidence.py:135
        │  │  ├─ wear_rate_by_compound                   pitcrew/analysis/wear.py:108
        │  │  ├─ window_by_compound                      pitcrew/analysis/tyre_window.py
        │  │  └─ qualification                           pitcrew/analysis/tyre_window.py:142
        │  ├─ laps_from_minutes  (timed races only)      pitcrew/strategy/model.py:738
        │  └─ → (RaceInputs, list[Evidence])             pitcrew/strategy/evidence.py:214,229
        ├─ recommend(inputs)                             pitcrew/strategy/model.py:564
        │  ├─ for stops in 0..4:
        │  │  ├─ _candidate_sequences                    pitcrew/strategy/model.py:542
        │  │  └─ build_plan                              pitcrew/strategy/model.py:446
        │  │     ├─ stint_limit per stint                pitcrew/strategy/model.py:432
        │  │     ├─ allocate_laps                        pitcrew/strategy/model.py:350
        │  │     ├─ stint_time_s per stint               pitcrew/strategy/model.py:398
        │  │     ├─ refuel_time_s per stop               pitcrew/strategy/model.py:426
        │  │     └─ legal(plan, inputs)                  pitcrew/strategy/model.py:531
        │  ├─ _fits filter                               pitcrew/strategy/model.py:600,713
        │  ├─ sort by (total_time_s, stops)              pitcrew/strategy/model.py:601
        │  └─ crossover(ordered, inputs)                 pitcrew/strategy/model.py:610
        ├─ store.get_approved_strategy                   pitcrew/controller.py:929
        └─ StrategyScreen.show_plans(plans, evidence)    pitcrew/ui/strategy_screen.py:311
           ├─ PlanCard per plan                          pitcrew/ui/strategy_screen.py:157
           ├─ subtitle ← f"{n} legal plans. {best.notes[0]}"
           │                                             pitcrew/ui/strategy_screen.py:341
           └─ crossover_band.show_crossover              pitcrew/ui/strategy_screen.py:344
```

`StrategyImpossible` is caught at `pitcrew/controller.py:921` and shown as a
status rather than a plan — refusal over invention, correctly.

### Live — during the race

Two independent producers run off the same lap event, and they do **not** share
state:

```
UDPListener → bridge.on_packet → SessionState → EventKind.LAP_COMPLETED
  └─ Controller._on_race_event(event)                    pitcrew/controller.py:1064
     ├─ RaceCoordinator.handle(event)                    pitcrew/race/coordinator.py:110
     │  └─ _on_lap → _emit → next_call(state)            pitcrew/race/coordinator.py:144,177
     │     └─ _candidates → one Call                     pitcrew/race/calls.py:127,144
     ├─ Controller._check_replan(lap)                    pitcrew/controller.py:1070,1128
     │  └─ replan.assess(...)                            pitcrew/race/replan.py:90
     │     └─ recommend(_remaining_race(...), max_stops=3)
     │                                                   pitcrew/race/replan.py:146,167
     ├─ RaceScreen.show_snapshot / show_call / show_offer pitcrew/controller.py:1072,1079,1159
     ├─ voice.say(call.spoken())                         pitcrew/controller.py:1076
     └─ store.append_revision(...)                       pitcrew/controller.py:1084
```

Arming: `RaceScreen.start_requested` → `Controller.start_race()`
(`pitcrew/controller.py:993`, wired at `:218`), which refuses a plan built for a
different car/track/layout/lap-count via `PlanContext.matches`
(`pitcrew/race/coordinator.py:36`).

---

## 1.2 The objective function, literally

The score is `Plan.total_time_s`, accumulated in `build_plan`:

```python
# pitcrew/strategy/model.py:470-490
    stints: list[Stint] = []
    total = 0.0
    start_lap = 1
    for index, laps in enumerate(stint_lengths):
        fuel_needed = None
        if inputs.fuel_per_lap_l:
            # To the diamond, plus one lap of margin.
            fuel_needed = (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l
            if inputs.fuel_capacity_l:
                fuel_needed = min(fuel_needed, inputs.fuel_capacity_l)

        stints.append(Stint(laps=laps, compound=sequence[index],
                            fuel_l=fuel_needed, start_lap=start_lap))
        total += stint_time_s(laps, inputs, fuel_at_start_l=fuel_needed,
                              profile=profiles[index])
        start_lap += laps

        if index < len(stint_lengths) - 1:
            total += inputs.pit_loss_s + inputs.pit_dead_time_s
            if fuel_needed:
                total += refuel_time_s(fuel_needed, inputs)
```

and the per-stint term:

```python
# pitcrew/strategy/model.py:410-423
    base_s = inputs.lap_time_ms / 1000.0 + profile.pace_delta_s
    wear = profile.wear_per_lap
    total = 0.0
    for lap_index in range(laps):
        lap_time = base_s
        if wear:
            consumed = (lap_index + 1) * wear
            lap_time += pace_loss_s(consumed)
        if fuel_at_start_l is not None and inputs.fuel_per_lap_l:
            onboard = max(0.0, fuel_at_start_l
                          - lap_index * inputs.fuel_per_lap_l)
            lap_time += onboard * inputs.fuel_weight_s_per_l_per_lap
        total += lap_time
    return total
```

Selection is `min` over `(total_time_s, stops)` at
`pitcrew/strategy/model.py:601-602`.

**What is minimised.** Total race time. The summation genuinely includes:

- stint pace (`base_s`, `model.py:410`);
- compound pace offset (`profile.pace_delta_s`, same line);
- tyre degradation (`pace_loss_s`, `model.py:417`);
- fuel-mass effect (`model.py:421`);
- pit loss + dead time per stop (`model.py:488`);
- refuel time per stop (`model.py:490`).

**What is missing.** There is **no out-lap or in-lap penalty term anywhere.**
Grep for it returns nothing outside comments. CLAUDE.md §5.4 states a cold
out-lap costs 0.5–1.5 s and is the reason the undercut is weak in GT7. The
model therefore systematically **under-costs stops by ~0.5–1.5 s each** and
biases toward more stops. Nothing in the code or the notes records this
omission.

**Fuel mass.** Yes — `model.py:421`. Coefficient
`FUEL_WEIGHT_S_PER_L_PER_LAP = 0.003` s/L/lap, declared at `model.py:41` as
"Derived, not measured", sourced from CLAUDE.md §5.3. Overridable per-plan via
the `RaceInputs.fuel_weight_s_per_l_per_lap` field (`model.py:144`), but
**nothing in the UI or `build_inputs` ever sets it** — `evidence.py:214-227`
does not pass it, so the default always applies. The comment at `model.py:40`
and the evidence row at `evidence.py:265-267` both say the driver can overwrite
it. He cannot.

**Degradation: assumed shape, measured scale.** It is neither fitted nor
tabulated. The *shape* is a hardcoded piecewise function:

```python
# pitcrew/strategy/model.py:285-300
def pace_loss_s(wear_fraction: float) -> float:
    if wear_fraction <= PHASE_FLAT_UNTIL:          # 0.50
        return 0.0
    if wear_fraction >= PHASE_CLIFF_FROM:          # 0.90
        over = (wear_fraction - PHASE_CLIFF_FROM) / (1.0 - PHASE_CLIFF_FROM)
        return DEG_AT_CLIFF_S + over * DEG_AT_CLIFF_S * 8.0
    span = PHASE_CLIFF_FROM - PHASE_FLAT_UNTIL
    return DEG_AT_CLIFF_S * (wear_fraction - PHASE_FLAT_UNTIL) / span
```

The *scale* — how fast `wear_fraction` advances — is `wear_per_lap`, which comes
from the **driver's in-game gauge reading**, not from lap times
(`pitcrew/analysis/wear.py:152-170`).

**Is degradation confounded with fuel burn?**

**No, not in the strategy calculation.** This is the single most important
answer in the audit and it is a genuine strength. Because `wear_per_lap` is a
gauge reading divided by the laps that *set* ran
(`pitcrew/analysis/wear.py:65-69`), there is no regression against tyre age, no
free stint intercept, and therefore nothing for fuel burn to contaminate. The
`d − k_f·b` identification problem does not arise.

**But the confound does exist in the exported payload.**
`degradation_ms_per_lap` (`pitcrew/analysis/wear.py:215-232`) is a raw
difference-of-halves fit on lap times with **no fuel correction**:

```python
    drift = mean([lap.lap_time_ms for lap in second_half]) - \
        mean([lap.lap_time_ms for lap in first_half])
    return round(drift / gap_laps, 1)
```

It reaches the export as `wear.byLapTime.degradationMsPerLap`
(`pitcrew/analysis/wear.py:299-309`) via `wear_export` at
`pitcrew/export/build.py:236`, and from there into the external race-engineering
tool. On the live event (fuel 6.224 L/lap × 0.003 s/L/lap) the car sheds
**≈18.7 ms/lap** of lap time to fuel burn alone, so this figure understates true
degradation by about that much. It is labelled `"confidence": "low"` and
`"source": "lap-time-model"` (`wear.py:307-308`), which is honest, but it is not
labelled *fuel-uncorrected*, and it does not feed the strategy model. See the
gap register when the design doc lands.

**Cliff.** Yes — `pace_loss_s` models it explicitly, and it is deliberately
punitive (9× the linear-phase gradient past 90%). Stint length is capped short
of it at `0.85 / w` (`model.py:311-315`), and every plan says so in its notes
(`model.py:511-514`).

---

## 1.3 The candidate generator

**Exhaustive over (stop count × ordered compound assignment), with a cap.**

```python
# pitcrew/strategy/model.py:586-593
    for stops in range(0, max_stops + 1):
        stints = stops + 1
        if stints > inputs.race_laps:
            break
        for sequence in _candidate_sequences(inputs, stints):
            plan = build_plan(inputs, stops, sequence)
            if legal(plan, inputs):
                plans.append(plan)
```

`max_stops` defaults to 4 (`model.py:564`), 3 in the live re-plan
(`pitcrew/race/replan.py:146`). `_candidate_sequences` (`model.py:542-561`)
takes the Cartesian product of available compounds over stints, ordered — so
compound *sequence* is searched, not just the multiset. Above
`MAX_CANDIDATES = 4096` (`model.py:71`) it degrades to single-compound
assignments only (`model.py:559`).

**Search space:**

| Dimension | Searched? |
|---|---|
| Number of stops | Yes, 0–4 |
| Compound per stint (ordered) | Yes, full product up to the cap |
| **Stop laps** | **No** — derived, not searched (see below) |
| **Fuel quantity per stop** | **No** — see below |

**Stop laps are not a decision variable.** They are computed by `allocate_laps`
(`model.py:350-395`), which distributes the race in proportion to each stint's
own limit and then fixes up the remainder. Its own docstring is candid: *"This
is a heuristic, not a proven optimum"* (`model.py:364`). So the optimiser never
evaluates, say, a short-fill first stint to gain track position, or an
asymmetric split on equal compounds.

**Fuel quantity is not a decision variable either.** It is fixed policy — to the
diamond plus one lap, clamped to the tank:

```python
# pitcrew/strategy/model.py:476-479
            fuel_needed = (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l
            if inputs.fuel_capacity_l:
                fuel_needed = min(fuel_needed, inputs.fuel_capacity_l)
```

This is defensible under CLAUDE.md §5.4 ("Take fuel only to the in-game diamond
marker plus one lap of margin"), but it means the "fastest lap ≠ fastest race"
trade the project cares about — carrying less fuel and running leaner — is
**outside the search space entirely**. There is no fuel-map dimension in the
optimiser at all: `FUEL_MAP_CONSUMPTION` and `FUEL_MAP_POWER` are defined at
`model.py:52-53` and **read by nothing** (verified: no other reference in
non-test code).

**The `min(...)` clamp on line 479 is load-bearing in a bad way** — see §1.4.

---

## 1.4 The legality model

| Rule | Where | Kind |
|---|---|---|
| Mandatory stops | `model.py:533` | Hard filter, pre-scoring |
| Required compounds | `model.py:535-538` | Hard filter, pre-scoring |
| Minimum stint length | — | **Absent** |
| Tank capacity | `model.py:479` (clamp), `model.py:318-323` (limit) | **Soft** — post-hoc, and defeasible |
| Fuel reserve | `FUEL_MARGIN_LAPS = 1.0`, `model.py:49,477` | Policy inside the fuel figure |
| Tyre life | `model.py:311-315` → notes → `_fits` | **Soft** — post-hoc, and defeasible |

`legal()` (`model.py:531-539`) is applied **before** the plan is admitted
(`model.py:592`) and covers regulations only. Feasibility — can the car actually
run these stints — is handled quite differently, and this is where it breaks.

`build_plan` does not reject an over-long stint. It writes a **note** about it
(`model.py:464-468`), and `_fits` later detects feasibility by **string-matching
that note**:

```python
# pitcrew/strategy/model.py:713-716
def _fits(plan: Plan) -> bool:
    """Whether every stint is inside what its own compound can run."""
    return not any(note.startswith("Stint ") and "runnable on" in note
                   for note in plan.notes)
```

Then:

```python
# pitcrew/strategy/model.py:600-602
    runnable = [plan for plan in plans if _fits(plan)]
    ordered = sorted(runnable or plans,
                     key=lambda p: (p.total_time_s, p.stops))
```

**`runnable or plans` is the defect.** When *no* candidate is feasible the
infeasible set is scored and ranked as if it were fine.

### Can a scored plan run the tank dry? Yes — proved by construction.

100-lap race, 10 L/lap, 100 L tank (10 laps of fuel), no tyre data,
`max_stops=4`:

```
--- E: fuel-only limit, nothing runnable ---
  stops 0 laps [100] fuel_l [100.0] fits False
  fuel actually needed per stint: [1010.0]
  binding: fuel
  notes[0]: Stint 1 is 100 laps but only 10 are runnable on this compound (fuel-limited).
```

The **zero-stop plan wins**, and it wins *because* it is infeasible: the clamp at
`model.py:479` caps `fuel_l` at 100 L, so `stint_time_s` charges fuel weight for
only 100 L instead of 1010 L, and the plan pays no pit stops at all. The more
impossible the plan, the cheaper it scores. Ranking is monotonically wrong in the
infeasible region.

### The live database reproduces this today

Running the real path against a copy of `data/pitcrew.db`:

```
RaceInputs from the real event:
   race_laps = 29            lap_time_ms = 106828
   fuel_per_lap_l = 6.224    fuel_capacity_l = 100.0
   refuel_rate_lps = 1.0     pit_loss_s = 19.0
   wear_per_lap = 0.1666...  evidence_compound = 'RS'
   missing() = []

   stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False
   stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False
   stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False
   stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False
   stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False
   notes[0]: Stint 5 is 9 laps but only 5 are runnable on RH (tyre-limited).
```

Every plan the screen would show right now is infeasible. The final stint is 9
laps against a 5-lap tyre limit — the padding branch at `model.py:386`
(`laps[-1] += total - sum(laps)`). The tyre would be at 150% of modelled life,
deep past the cliff.

**And the screen does not say so on the card.** `PlanCard`
(`pitcrew/ui/strategy_screen.py:157-194`) renders the label, `"Fastest"`, the
race time, a stint bar and *"Limited by tyre"*. It never reads `plan.notes`. The
only surfacing is the subtitle, which shows `notes[0]` **of the top plan only**:

```python
# pitcrew/ui/strategy_screen.py:341-343
            self.subtitle.setText(
                f"{len(plans)} legal plans. "
                f"{best.notes[0] if best.notes else ''}")
```

So the driver reads **"5 legal plans"**, sees a card marked **"Fastest"**, and
the Approve button is enabled (`strategy_screen.py:331`) on a plan that cannot
be run. `missing()` returns `[]`, so `build_strategy` prints **"Every input
measured."** (`controller.py:961`).

### Also absent

- **No minimum stint length**, so a 1-lap stint is admissible.
- **`available_compounds` is not filtered by conditions.** The live event lists
  `('RH','RM','RS','IM','HW')`; the search enumerates intermediates and heavy
  wets as candidates for a dry race (5⁵ = 3125 < `MAX_CANDIDATES`).
- **`legal()` cannot express "the required compound must be *run*, not merely
  fitted"** — it tests set membership of `stint.compound` only
  (`model.py:536-538`), so a 1-lap stint satisfies a compound requirement.

---

## 1.5 Input provenance table

M = measured off telemetry · D = driver-declared · A = app assumption ·
H = hardcoded literal.

| Input | Consumed at | Produced at | Class | Scope | When missing |
|---|---|---|---|---|---|
| Base lap time | `model.py:410` | `session.py:157` `green_lap_reference_ms` — min of first 3 counted laps | **M** | per event | `recommend` raises `StrategyImpossible` (`model.py:581`); `evidence.py:216` coerces to `0` first |
| Compound pace offsets | `model.py:410` | `evidence.py:167` median-vs-reference | **M** (D if no wear rate) | per compound per event | `0.0` — compounds priced identically |
| Degradation *shape* | `model.py:285-300` | literals `model.py:32,33,37` | **H** | global | n/a |
| Degradation *scale* (`wear_per_lap`) | `model.py:311,435` | `wear.py:152` driver gauge ÷ laps on that set | **D** | per compound per event | `None` → tyre limit `None` → fuel-limited only, with a note (`model.py:521-523`) |
| Fuel burn per lap | `model.py:418-421,477` | `evidence.py:198-200` median of `fuel_start-fuel_end` | **M** | per event | `None` → no fuel limit, no fuel weight, `fuel_l` `None`; listed by `missing()` |
| Fuel tank capacity | `model.py:320,478` | `evidence.py:85` first practice session's `fuel_capacity_l` | **M** | per event | `None` → no fuel limit and **no clamp**; listed by `missing()` |
| Fuel-weight coefficient | `model.py:421` | literal `model.py:41` = 0.003 | **A** | global | never missing; **never overridable in practice** (§1.2) |
| Pit-lane delta | `model.py:488` | `events.pit_loss_secs`, UI `event_screen.py:270-273` | **D** | per event | schema default `20.0` (`schema.py:72`) |
| Tyre-change time | — | — | **absent** | — | not modelled at all (§1.6) |
| Refuel rate | `model.py:429` | `events.refuel_rate_lps`, UI `event_screen.py:265-268` | **D** | per event | schema default `2.5` (`schema.py:71`) |
| Pit dead time | `model.py:488` | literal `model.py:45` = 7.5 | **A** | global | never missing, never overridable |
| In-lap / out-lap penalty | — | — | **absent** | — | not modelled (§1.2) |
| Race length | `model.py:579,586` | `events.race_laps`; if `race_type='time'`, `laps_from_minutes` (`model.py:738`) | **D** (A when converted) | per event | `or 0` (`evidence.py:210`) → `StrategyImpossible` |
| Fuel multiplier | — | — | **absent** | — | not represented anywhere |
| Tyre multiplier | `model.py:515` (flag only) | `RaceInputs.wear_measured_at_race_multiplier` (`model.py:140`) | **A** | — | defaults `True`; **`build_inputs` never sets it** (`evidence.py:214-227`), so the `[ASSUMED]` warning at `model.py:516-519` is unreachable from the app |
| Required compounds | `model.py:535` | `events.required_compounds` | **D** | per event | `()` → no constraint |
| Mandatory stops | `model.py:533` | `events.mandatory_stops` | **D** | per event | `or 0` (`evidence.py:222`) |
| Available compounds | `model.py:549` | `events.available_compounds` | **D** | per event | `()` → falls back to `_compound_sequence` (`model.py:553,719`) |
| Fuel-map setting | — | `LapInput.fuel_map` (`session.py:36`) exists and is stored | **captured, unused** | — | `FUEL_MAP_*` tables (`model.py:52-53`) are read by nothing |
| Weather state | — | — | **absent** | — | not represented |
| Damage state | — | — | **absent** | — | not represented |
| Tyre window | `evidence.py:184` → note only | `tyre_window.py:142` `qualification` | **M** | per compound | `None` → no qualification; `_window_note` says so (`evidence.py:331`) |

---

## 1.6 Constants register

Every numeric literal on the strategy path.

### `pitcrew/strategy/model.py`

| Line | Name | Value | Overridable by measurement? |
|---|---|---|---|
| 29 | `STINT_SAFETY_FACTOR` | 0.85 | No. From CLAUDE.md §5.2; stated in notes |
| 32 | `PHASE_FLAT_UNTIL` | 0.50 | No |
| 33 | `PHASE_CLIFF_FROM` | 0.90 | No |
| 37 | `DEG_AT_CLIFF_S` | 1.0 | No. Comment concedes it is the midpoint of a 0.5–1.5 range and "an assumption, not a measurement" |
| 41 | `FUEL_WEIGHT_S_PER_L_PER_LAP` | 0.003 | **In theory yes** (field at :144); **in practice no** — never set by `build_inputs` |
| 45 | `PIT_DEAD_TIME_S` | 7.5 | No. Field at :138 exists but `build_inputs` never sets it |
| 49 | `FUEL_MARGIN_LAPS` | 1.0 | No |
| 52 | `FUEL_MAP_CONSUMPTION` | {1:1.0 … 6:0.50} | **Dead — read by nothing** |
| 53 | `FUEL_MAP_POWER` | {1:1.0 … 6:0.80} | **Dead — read by nothing** |
| 71 | `MAX_CANDIDATES` | 4096 | No |
| 136 | `refuel_rate_lps` default | **2.5** | Yes — event field |
| 137 | `pit_loss_s` default | 20.0 | Yes — event field |
| 298 | cliff gradient multiplier | `* 8.0` | No. Undocumented magic number |
| 564 | `max_stops` default | 4 | Call-site only |

### `pitcrew/race/calls.py`

| Line | Name | Value | Note |
|---|---|---|---|
| 40 | `STATUS_EVERY_LAPS` | 5 | |
| 43 | `FUEL_SHORT_LAPS` | 0.5 | |
| 45 | `FUEL_LONG_LAPS` | 1.5 | |
| 206 | `(after_stop + 1)` | 1 lap margin | Duplicates `FUEL_MARGIN_LAPS`, not shared |
| 215 | lap threshold for MEDIUM confidence | 3 | |
| 253 | tyre-warning threshold | **0.85** | Duplicates `STINT_SAFETY_FACTOR`, not shared |

### `pitcrew/race/replan.py`

| Line | Name | Value | Note |
|---|---|---|---|
| 28 | `FUEL_DRIFT` | 0.05 | |
| 29 | `PACE_DRIFT` | 0.02 | |
| 32 | `WORTH_CHANGING_S` | 8.0 | The only hysteresis-ish quantity in the codebase (§1.9) |
| 128 | fuel-short margin | 0.5 laps | |
| 142 | `BURN_LAPS_NEEDED` (coordinator) | 3 | `coordinator.py:142` |
| 146 | `max_stops` | 3 | Differs from pre-race 4 — a re-plan cannot recommend a 4-stop |

### `pitcrew/analysis/wear.py` / `session.py` / `evidence.py`

| Line | Name | Value |
|---|---|---|
| `wear.py:35` | `STINT_SAFETY_FACTOR` | 0.85 — **third copy** of the same constant |
| `wear.py:44,46` | phase boundaries | 0.5 / 0.9 — **second copy** |
| `session.py:25` | `GREEN_LAP_WINDOW` | 3 |
| `evidence.py:51` | `WINDOW_SAMPLE_LAPS` | 6 |

### The three specifically called out

**1. Refuel rate.** Not 1 L/s in code. Three defaults of **2.5**
(`model.py:136`, `schema.py:71`, `prompts/context.py:32`), one UI spinbox default
of 2.5 (`event_screen.py:268`, range 0.1–20.0). The live event holds **1.0**,
driver-entered. Read at `model.py:429` and `evidence.py:219,264`, and required
by the export validator (`export/payload.py:236-238`).

**Nothing measures it.** `pitcrew/telemetry/session_state.py:240-256` detects a
pit stop by observing that fuel is *rising* at low speed — it therefore has both
of the quantities needed (Δfuel and Δtime across the refuel window) and computes
neither. The comment at `prompts/build.py:527` shows the discrepancy is known:
*"At the current event refuel is 1 L/s against a 2.5 default, and it decides the
whole race."* It decides the whole race, it is entered by hand, and the app that
watches the refuel happen does not check it.

Sensitivity, at the live event's numbers (29 laps, 6.224 L/lap, 4 stops): a
one-stop fill of ~37 L costs **37 s at 1 L/s and 7.4 s at 5 L/s**. Across four
stops that is ~120 s — larger than the entire spread between the strategy
options. The stop count is effectively decided by this one unverified number.

**2. Tyre change vs refuel — neither summed nor maxed.** Tyre change time is
**not modelled at all**. The stop cost is
`pit_loss_s + pit_dead_time_s + refuel_time_s` (`model.py:488-490`) — three
terms, none of them a tyre change. So the code implicitly assumes tyre change is
either free or already folded into the driver's `pit_loss_secs` figure. Which of
those it assumes is **recorded nowhere** — not in a comment, not in the notes,
not in `as_export`'s `assumptions` block (`model.py:255-265`). A driver who
measures `pit_loss_secs` as a full stationary stop will double-count the dead
time; one who measures it as drive-through-only will under-count the tyre change.
The export declares `"pitLossSource": "measured-this-track"` unconditionally
(`model.py:257`) regardless of how it was actually obtained.

**3. Fuel weight, compound delta, degradation defaults.** Fuel weight 0.003 (§1.2
— nominally overridable, actually not). Compound delta defaults to `0.0`
(`model.py:88`), which is the honest choice — an unmeasured compound is priced as
identical to the reference and labelled `assumed` (`model.py:165-172`), and the
plan carries a note saying so (`model.py:498-504`). Degradation defaults are the
piecewise constants above; there is no per-car or per-track degradation store.

---

## 1.7 SessionDB derivation

There is no `SessionDB` class; the store is `pitcrew/store/db.py` (`Store`), and
derivation lives in `pitcrew/strategy/evidence.py` and `pitcrew/analysis/`.

| Quantity | Query | Transform |
|---|---|---|
| Clean race pace | `store.list_event_laps(event_id, "practice")` (`evidence.py:62`) | `green_lap_reference_ms` = `min` of first 3 counted laps (`session.py:157-163`) |
| Fuel consumption | same rows | `median(fuel_start - fuel_end)` over counted laps where the difference is positive (`evidence.py:198-200`) |
| Compound pace | same rows, grouped by `compound` | `median(lap_time_ms)` per compound minus reference median, ÷1000 (`evidence.py:157-168`) |
| Consistency | same rows | `pstdev(times)` → `session.lapTimeStdDevMs` (`session.py:186`) — **export only, not a strategy input** |
| Pit information | `is_pit_lap` column | used for stint grouping (`wear.py:83-90`) and outcome text (`race/outcome.py:19-20`). `pit_loss_secs` is **not derived** — it is typed in |
| Tyre-degradation proxy | same rows | `wear_rate_by_compound` (`wear.py:108-126`): per set, `worst_gauge_reading / laps_on_that_set`, averaged across sets of that compound |

### What defines a "clean lap"?

One property, on the lap row:

```python
# pitcrew/analysis/session.py:51-54
    @property
    def counted(self) -> bool:
        """Out-laps, in-laps and anything the driver excluded do not count."""
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)
```

| Excluded? | |
|---|---|
| In-laps (`is_pit_lap`) | Yes |
| Out-laps (`is_out_lap`) | Yes |
| Driver-excluded (`excluded`) | Yes |
| **First lap of stint (non-out-lap)** | **No** |
| **Caution / safety-car laps** | **No** — no such concept exists in the schema |
| **Off-track laps** | **No** |

The last one is the notable gap. `_off_track_count` already computes excursions
per lap from the surface channel (`session.py:115-134`) and exports them, but
**nothing gates a lap on it**. A lap with four wheels on the grass is a counted
lap and moves the median. Since the medians here run over ~6 laps, one such lap
is a sixth of the evidence. The gate is a raw boolean triple, with no statistical
outlier rejection of any kind.

### Is the degradation proxy fuel-corrected?

The proxy that **feeds strategy** (`wear_rate_by_compound`) is a gauge reading —
fuel correction is not applicable, and this is the right design. The proxy that
**feeds the export** (`degradation_ms_per_lap`, `wear.py:215-232`) is a lap-time
fit and is **not** fuel-corrected — §1.2.

### How many laps before a number is produced, and with what uncertainty?

| Quantity | Minimum | Uncertainty attached |
|---|---|---|
| `green_lap_reference_ms` | **1** counted lap (`session.py:160-163`) | none |
| Fuel per lap | **1** positive burn (`evidence.py:200`) | `len(burns)` in the evidence note only (`evidence.py:241`) |
| `wear_per_lap` | **1** gauge reading, on **1** stint (`wear.py:169-170`) | none on the value |
| Compound pace delta | **1** lap per compound (`evidence.py:167`) | `laps_measured` count carried (`evidence.py:179`) |
| `wear_rate_by_compound` | **1** stint | `stints` count carried (`wear.py:123`) |
| `degradation_ms_per_lap` | 3 counted laps (`wear.py:222`) | `"confidence": "low"` (`wear.py:308`) |
| Tyre window | ≤6 laps sampled (`evidence.py:51`) | `lapsSampled` carried |

Counts travel alongside every aggregate — CLAUDE.md §4.4 is honoured. But a
**count is not an interval**: nothing anywhere attaches a standard error or a
confidence bound to a value, and no minimum-sample gate blocks a number from
being produced. A one-lap fuel figure and an eleven-lap one enter `RaceInputs`
identically and rank plans identically.

### Is the degradation proxy derived from `tyre_radius`?

**No.** `tyre_radius` is parsed (`telemetry/packet.py:475`) but appears nowhere
in `pitcrew/analysis/wear.py` or `pitcrew/strategy/`. Verified by grep. Not
applicable to this codebase.

---

## 1.8 Uncertainty

**No part of the strategy path represents uncertainty numerically.** There are no
intervals, no distributions, no scenario sampling, no sensitivity analysis. Every
input is a point estimate and `total_time_s` is a point estimate.

What exists instead is **provenance labelling**, which is thorough and does
influence behaviour — but never the number.

| Mechanism | Where | Affects the number? |
|---|---|---|
| `SOURCE_MEASURED` / `_DECLARED` / `_ASSUMED` | `model.py:63-65` | No — label only |
| `CompoundProfile.is_measured` | `model.py:99-101` | No |
| `Plan.rests_on_assumption` | `model.py:217-220` | **Yes, indirectly** — gates the crossover verdict wording at `model.py:677` |
| `evidence_is_clean` (window) | `model.py:103-113` | **No — and this is a live defect.** Its docstring says the two "must not rank against each other silently", but the property has **no caller in non-test code** (verified by grep). Ranking is `total_time_s` alone (`model.py:601`), so window-qualified and clean evidence *do* rank against each other silently — exactly what the docstring forbids |
| `Call.confidence` HIGH/MEDIUM/LOW | `calls.py:21-23` | No — appends "Unconfirmed." to speech (`calls.py:62-63`) |
| `Replan.confidence` | `replan.py:47` | **No** — set to `"low"` at `replan.py:141,149` but never read by any decision; `_check_replan` gates on `verdict.offered` only (`controller.py:1148`) |
| `Evidence.source` (screen registers) | `evidence.py:28-31` | No — display only |

The strongest example of confidence-as-caption: on the live event, five plans
tie at exactly 3478 s because they are all planned on the same borrowed rate. The
crossover verdict says so in words — *"they are being planned on the same number.
This is not a comparison yet"* (`model.py:678-681`) — while the sort still emits
one of them as **"Fastest"** with a hard number beside it. The words are right
and the ranking is arbitrary.

---

## 1.9 The live path

### Trigger and cadence

**Lap boundary only.** `Controller._on_race_event` (`controller.py:1064`) runs on
every telemetry event, but:

- calls are produced by `RaceCoordinator.handle` → `_on_lap` → `_emit`
  (`coordinator.py:116,144,177`), i.e. on `LAP_COMPLETED`;
- re-planning runs from `_check_replan`, guarded to `LAP_COMPLETED`
  (`controller.py:1069-1070`).

No timer, no telemetry-tick recompute. `PIT_ENTRY` / `PIT_EXIT` mutate state but
return no call (`coordinator.py:118-125`). At ~107 s/lap this is roughly one
recompute every two minutes.

### Committed plan / live projection / candidate set

**Partially separated, but the committed plan is mutable.**

| Concept | Representation |
|---|---|
| Committed plan | `RaceCoordinator._stints` (`coordinator.py:63`), copied from the approved DB row |
| Live projection | `RaceState` (`calls.py:75-107`) — a mutable dataclass |
| Candidate set | Rebuilt from scratch inside `replan.assess` (`replan.py:146`) and **discarded**; only `best.stops` and `best.stint_laps` survive into `Replan` (`replan.py:161-162`) |

Good: the committed plan is not silently overwritten. `_pending_replan`
(`controller.py:1152`) holds the offer, and it is only applied when the driver
says so through PTT (`controller.py:1110-1124` → `coordinator.adopt`). Every
offer is persisted accepted-or-not (`controller.py:1084-1087`,
`controller.py:1120-1122`).

Bad: `adopt` **rewrites the committed plan in place** (`coordinator.py:187-204`),
dropping compounds and fuel figures to `None`
(`coordinator.py:200-201`). After one accepted re-plan the plan no longer knows
which tyre goes on, so `_box_now`'s compound clause (`calls.py:178`) goes silent
and `_ptt_snapshot`'s `stopFuelL` (`controller.py:1101`) becomes `None`. The
driver loses the two facts he most needs at the stop, as a side effect of
accepting advice.

### What can change a recommendation, and is there hysteresis?

Two thresholds and one dwell-like rule:

```python
# pitcrew/race/replan.py:27-32
FUEL_DRIFT = 0.05      # 5% off the planned burn rate
PACE_DRIFT = 0.02      # 2% off the reference lap
WORTH_CHANGING_S = 8.0
```

- **Trigger** (`replan.py:114-121`): burn >5% off plan, or pace >2% off.
- **Materiality** (`replan.py:155-156`): the new plan must beat the current one
  by more than 8 s or nothing is offered.
- **Urgent override** (`replan.py:125-133`): fuel short of the flag by >0.5 laps
  bypasses both.

`WORTH_CHANGING_S` is a genuine switching threshold and is the best-designed part
of the live path. But:

- **There is no dwell and no persistence requirement.** A single slow lap can
  trip `PACE_DRIFT`; the code does not require N consecutive laps.
- **There is no hysteresis band** — the same 8 s threshold governs switching in
  both directions, so a plan hovering at 8 s can flip repeatedly.
- **The pace input is a single lap**, `lap.lap_time_ms` (`controller.py:1142`),
  not a filtered or median value. The fuel input *is* median-filtered
  (`coordinator.py:158-160`), which shows the authors knew the pattern and
  applied it to only one of the two.
- **No clean-lap gate at all on the live path.** An in-lap, an out-lap or a lap
  spent in the gravel goes straight into `pace_drift`. 2% of a 107 s lap is
  2.1 s — comfortably inside the noise of a single traffic lap, let alone an
  off.

**How often would it fire?** `_pending_replan is not None` blocks a second offer
until the driver answers (`controller.py:1148`), so the practical rate is bounded
by his responses, not by the model. Absent an answer, the trigger is evaluated
every lap, and on a 29-lap race with a 2.1 s pace band and no clean-lap gate, a
safety car, a pit cycle or two traffic laps would each be sufficient to re-arm
it. `WORTH_CHANGING_S` is what actually suppresses most of these, not the drift
thresholds.

### Commitment point

**There is none.** `_box_now` fires when `laps_to_stop() <= 0`
(`calls.py:174-175`) — at the moment the lap that *should have ended* in the pits
completes, i.e. one lap late by construction, with no earlier deadline and no
expiry. `_box_soon` fires at 1–2 laps out (`calls.py:190`) and is suppressed once
said (`calls.py:138-140`). Nothing models the point past which "box this lap" can
no longer be executed, and nothing withdraws a call that has become stale.

**The D1 analogue.** The old defect was a prompt whose assumed action nothing
detected. The equivalent here is narrower but real: `_box_now` and `_box_soon`
tell the driver to box, and the app **cannot confirm he did**. Pit detection runs
entirely off `SessionState`'s fuel-rising-at-low-speed heuristic
(`session_state.py:240-256`). If a stop is taken without refuelling — a
tyres-only stop, which GT7 permits — `PIT_EXIT` never fires, `clear_stint` never
runs (`coordinator.py:123`), `stint_index` never advances, and `laps_to_stop()`
stays ≤ 0. `_box_now` is suppressed by `state.said` (`calls.py:138-140`) so it
does not repeat, but the coordinator now believes the car is on a stint that
ended. Every downstream number — `lapsToStop`, `nextCompound`, `stopFuelL` — is
wrong for the rest of the race, silently.

Worse, `pitcrew/telemetry/pit_state.py` exists precisely to grade this detection
(`MEDIUM` for refuel-based, `LOW` for speed-only, per its lines 41 and 189) and
**has no non-test importer anywhere in the codebase** — §1.11.

### What reaches the driver, and what gates emission

| Surface | Where | Gate |
|---|---|---|
| Voice | `controller.py:1076`, `1155` | one call per lap (`calls.py:127-141`); kind suppressed once said (`calls.py:138`), reset at each stop (`calls.py:274-277`) |
| Race screen call log | `controller.py:1079` | same |
| Race screen snapshot | `controller.py:1072` | every event |
| Re-plan offer | `controller.py:1159` | `verdict.offered` and no offer pending (`controller.py:1148`) |
| PTT answers | `engineer/intents.py` off `_ptt_snapshot` (`controller.py:1091`) | driver-initiated |
| DB revision log | `controller.py:1084`, `1120` | every call and every resolution |

The one-call-per-lap discipline (`calls.py:127-141`) and the urgency ordering
(`calls.py:35-36`) implement CLAUDE.md §5.5 well.

**But one spoken number is unexecutable.** `_fuel_instruction` has **no tank
clamp**:

```python
# pitcrew/race/calls.py:199-207
def _fuel_instruction(state: RaceState) -> str:
    """How much to take, in litres, to the diamond plus a lap."""
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return ""
    after_stop = state.laps_remaining()
    if state.stint_ends_on_lap is not None:
        after_stop = (state.laps_total or 0) - state.stint_ends_on_lap
    litres = (after_stop + 1) * state.fuel_per_lap_l
    return f"Fuel to {litres:.0f} litres."
```

`RaceState` carries no capacity field at all (`calls.py:75-91`), so the clamp
that `build_plan` applies at `model.py:479` has no counterpart here. Proved:

```
--- F: LIVE fuel instruction, no tank clamp ---
  _fuel_instruction -> 'Fuel to 510 litres.'
  (laps after stop = 60-10 = 50; 51*10 = 510 L into a 100 L tank)
```

Spoken at HIGH confidence, inside a `BOX_NOW` call (`calls.py:177,182`), under a
helmet.

---

## 1.10 Degradation on missing evidence

**No bare `except` exists anywhere on the strategy path.** Verified across
`pitcrew/strategy/`, `pitcrew/race/`, `pitcrew/analysis/wear.py`,
`pitcrew/analysis/session.py`, `pitcrew/analysis/tyre_window.py` and
`controller.py:900-1200`. The only handlers are three narrow ones:

- `except StrategyImpossible` — `controller.py:921`, `replan.py:147`
- `except ValueError` — `controller.py:1007` (falls back to `inputs = None`,
  which then propagates as `None` rather than a zero)

This is a real and substantial improvement over the old codebase's nine silent
swallows. Likewise **null-not-zero is honoured almost everywhere**:
`wear_per_lap` returns `None` (`wear.py:170`), `axle_bias` returns `None` per
axis rather than 0 (`wear.py:200-203`), `_off_track_count` returns `None` when
the channel is absent (`session.py:122-123`), `fuel_limited_laps` guards the
zero-capacity divide (`model.py:320-323`).

Verified for the electric-car case (capacity 0.0):

```
--- H: zero fuel capacity (electric) ---
  ok: 1 [10, 10] tyre fuel_l [None, None]
```

### Where it still degrades badly

| Condition | Behaviour | Where |
|---|---|---|
| Thin practice coverage | **Silent.** No minimum-lap gate. One lap produces a full plan | §1.7 |
| Compound never run | Handled well — no profile invented, reference rate borrowed and labelled `assumed`, note added | `model.py:165-172`, `evidence.py:145-147`, `model.py:496-504` |
| SessionDB returns nothing | `recommend` raises `StrategyImpossible`, caught and shown | `model.py:581`, `controller.py:921` |
| **Telemetry drops mid-race** | **Nothing.** No staleness concept in `RaceState`. `fuel_l` holds the last value seen forever, `laps_of_fuel()` keeps returning a number computed from it (`calls.py:98-102`), and `_fuel` keeps making HIGH-confidence calls off it (`calls.py:215-230`). The 1 Hz health timer *is* started for a race (`controller.py:1034`), and `_report_health` (`controller.py:873-902`) distinguishes bind failure, source-filter rejection, no-stream and decode failure carefully — but it writes every one of them to **`self.practice.set_status`**, the Practice screen. During a race that surface is not on screen, the message is never spoken, and nothing gates a call on it |
| **No plan is runnable** | **`runnable or plans`** — the infeasible set is ranked and presented (§1.4) |
| Missing wear rate | Note added (`model.py:521-523`), fuel-limited planning proceeds — correct |
| `race_laps` missing | `or 0` (`evidence.py:210`) → `StrategyImpossible` — acceptable, but the coercion pattern is the one CLAUDE.md §4.3 warns against |
| `reference_ms` missing | `or 0` (`evidence.py:216`) → `StrategyImpossible` at `model.py:581` — same |

The two `or 0` coercions at `evidence.py:210,216` are benign only because
`recommend` happens to reject 0 explicitly. Nothing enforces that coupling.

---

## 1.11 Wiring check

Computed by AST import-graph closure from `pitcrew.app` (the entry point;
there is no `main.py`), then hand-verified for `from pkg import module` forms
that the closure under-reports.

| Module | Reachable? | Entry point | Notes |
|---|---|---|---|
| `strategy/model.py` | **Yes** | `app` → `controller:906` → `recommend` | |
| `strategy/evidence.py` | **Yes** | `app` → `controller:918` → `build_inputs` | |
| `race/calls.py` | **Yes** | `controller:1068` → `coordinator:178` | |
| `race/coordinator.py` | **Yes** | `controller:1010`, `:1068` | |
| `race/replan.py` | **Yes** | `controller:1136` | |
| `race/outcome.py` | **Yes** | via `export/build.py` | |
| `analysis/wear.py` | **Yes** | `evidence:15-16`, `export/build:236` | |
| `analysis/session.py` | **Yes** | `evidence:14` | |
| `analysis/tyre_window.py` | **Yes** | `evidence:17` | |
| `analysis/thresholds.py` | **Yes** | `from pitcrew.analysis import thresholds` × 4 | |
| `store/catalogs.py` | **Yes** | `controller:39` + 6 others | |
| `engineer/gate.py` | **Yes** | `engineer/ptt.py:28` | |
| `ui/strategy_screen.py` | **Yes** | `controller:215` | |
| `ui/race_screen.py` | **Yes** | `controller:218` | |
| **`telemetry/pit_state.py`** | **NO** | — | **Zero importers, test or otherwise.** `grep -rn "pit_state"` across the repo returns only the file itself. 200 lines implementing graded pit detection (`MEDIUM` refuel-based / `LOW` speed-only, lines 41, 189) that the live path badly needs — §1.9 |
| `ui/preview.py` | **NO** | — | Developer screenshot tool, `python -m pitcrew.ui.preview` (its lines 3–4). Intentional; not a defect |

`strategy/tyre_curves.py` does not exist in this codebase — it was deleted with
the old tree (§0.1). Its structural successor is `telemetry/pit_state.py`: the
same failure mode, one module, currently live.

**Dead code inside reachable modules** (the more common shape here):

| Symbol | Where | Status |
|---|---|---|
| `FUEL_MAP_CONSUMPTION`, `FUEL_MAP_POWER` | `model.py:52-53` | Never read. The entire fuel-map model is inert |
| `CompoundProfile.evidence_is_clean` | `model.py:103-113` | No non-test caller, despite a docstring asserting a ranking rule (§1.8) |
| `RaceInputs.wear_measured_at_race_multiplier` | `model.py:140` | Never set by `build_inputs`; the `[ASSUMED]` multiplier warning at `model.py:516-519` is unreachable from the app |
| `RaceInputs.fuel_weight_s_per_l_per_lap` | `model.py:144` | Never set by `build_inputs`; the default always applies |
| `RaceInputs.pit_dead_time_s` | `model.py:138` | Never set by `build_inputs` |
| `RaceInputs.starting_fuel_l` | `model.py:145` | Never set and never read |
| `Plan.window_notes` | `model.py:222-227` | Read only by `crossover` (`model.py:639`) |
| `max_stint_laps` | `model.py:326-339` | Called once (`model.py:458`) for `binding_constraint` only; per-stint logic uses `stint_limit` instead |

---

## 1.12 Test-versus-executed path

30 test files, **710 test functions**, all under `pitcrew/tests/`.

**Strategy-path test files and what they import:**

| File | Imports the wired path? |
|---|---|
| `test_strategy_model.py` | Unit only — `strategy.model` |
| `test_strategy_wiring.py` | **Yes** — `controller`, `store.db`, `strategy.evidence`, `ui.strategy_screen`, `ui.event_screen`, `ui.practice_screen` |
| `test_compound_crossover.py` | `analysis.session`, `strategy.evidence`, `strategy.model` |
| `test_tyre_window.py` | `analysis.tyre_window`, `strategy.evidence`, `strategy.model` |
| `test_race.py` | Unit only — `race.calls`, `race.coordinator` |
| `test_race_wiring.py` | **Yes** — `controller`, `race.calls`, `store.db`, `ui.race_screen`, `ui.strategy_screen` |
| `test_ptt_and_replan.py` | **Yes** — `controller`, `race.replan`, `race.outcome`, `strategy.model`, `ui.*` |

**Ratio.** Of the 16 strategy-path modules in §1.11, **15 are reachable and 15
are under test**; the one unreachable module (`pit_state.py`) has **no tests
either**. So:

> **Tests exercising unreachable modules: 0 of 710.**
> **Strategy-path modules reachable and tested: 15/15 (100%).**
> **Strategy-path modules unreachable: 1 (`telemetry/pit_state.py`), untested.**

This is the opposite of the 6 August pattern. The suite is not testing a
parallel universe. Three dedicated `*_wiring.py` files exist specifically to
assert that screens are connected to the controller, which is a direct
structural response to the old failure mode.

> **Correction, 12 Aug, added while implementing the Commit 1 fixes.** I called
> this "the strongest single result in the audit". That was too strong, and the
> qualification matters. **Those three `*_wiring.py` files cannot run on this
> machine** — every test that constructs a `Controller` hangs indefinitely on a
> `win32com.client.Dispatch("SAPI.SpSharedRecognizer")` call reached through
> `controller.py:185` → `ptt.py:517` → `ptt.py:207`. Four files hang from their
> first test, three hang partway; the remaining 21 files (604 tests) pass. See
> gap-register **E6** for the faulthandler dump and the minimal fix.
>
> What survives: the reachability result above, which is static import-graph
> analysis and does not depend on running anything. What does not: the implied
> claim that the wiring is *verified*. It is asserted in tests that never
> execute — which is a different failure from the 6 August one, and closer to it
> than I first credited.

> **Resolved, same day.** The hang is fixed (register **E7**) and the whole
> suite now runs: **774 passed in 38.7 s across 30 files, zero failures, zero
> hangs.** All seven previously-blocked files pass in full. So the question the
> correction left open — *do the wiring tests verify what §1.12 said they
> verify?* — now has an answer, and it is three-part:
>
> **Yes, for controller-to-screen wiring, and more thoroughly than I assumed.**
> `test_strategy_wiring.py` (19 tests) builds a real `PitCrewController` with a
> real `StrategyScreen`, `EventScreen` and `PracticeScreen`, calls
> `build_strategy()`, and asserts on `strategy.subtitle.text()`,
> `approve_button.isEnabled()` and what `store` actually persisted on approve.
> `test_race_wiring.py` (18) arms a race, feeds telemetry events, and asserts
> the calls are spoken, recorded with their reason, reach the export, and move
> the pit wall. These are not import smoke tests; they drive the wired path
> through real widgets and a real store.
>
> **No, for the telemetry ingest path.** Both inject `Lap` objects directly
> rather than driving packets through `UDPListener → TelemetryBridge →
> SessionState`. The wiring verified is controller ↔ screen ↔ store, not
> socket ↔ plan.
>
> **And they caught neither P1.** A1's infeasible-plan ranking and D1's
> 510-litre call both sat inside this fully wired, fully asserted code. That is
> the §1.12 caveat holding exactly as written: a green suite here means the
> wires are connected, not that the number is right.
>
> The sharpest lesson is about the hang itself. These tests were **correct** and
> would have reported the startup defect the moment anyone ran them — the app
> could not start, and the suite said so by refusing to finish. The failure was
> not in the tests and not in the wiring; it was that nobody had run the suite
> to completion. That is a *third* variant of the 6 August failure mode, and the
> cheapest one to guard against: assert that the suite terminates.

**The caveat that matters.** The suite tests *connectivity*, not *correctness of
the number under adverse inputs*. Every defect in §1.4 and §1.9 — the infeasible
plan ranked "Fastest", the 510-litre fuel call, the missing out-lap penalty, the
stale-telemetry blindness — sits in fully wired, fully tested code. A green suite
here means the wires are connected. It does not mean the plan is runnable.

---

## Appendix A — Findings belonging to other phases

| # | Finding | Owner |
|---|---|---|
| A1 | `events.race_laps` holds **minutes** when `race_type = 'time'` (`evidence.py:210-212`). The live event stores `50` meaning 50 minutes. A column named `race_laps` holding minutes will be misread | Schema / Phase 1 |
| A2 | Live DB is at `user_version` 2 against `SCHEMA_VERSION = 3`; the per-corner wear migration runs on next open. Any tool reading `data/pitcrew.db` directly sees `wear_front`/`wear_rear`, not the four corners | Store |
| A3 | `packet.py:449-459` documents `current_position` as live race position at offset 0x84 with a byte-level layout, but `packet.py:173` calls the *other* candidate field "possibly race position". One of these is unverified. Out-of-range values return `0`, and `0` is falsy at `coordinator.py:149`, so a `-1`/`0xFF` grid field degrades to "no position" rather than a wrong one — safe, but by accident rather than by check | Telemetry |
| A4 | `_off_track_count` (`session.py:115-134`) is computed and exported but gates nothing | Analysis |
| A5 | `LapInput.fuel_map` (`session.py:36`) is captured and stored but read by no consumer | Analysis |
| A6 | `.claude/worktrees/pensive-banach-78f43f/` contains a full copy of the deleted ~200k-line app, including `strategy/tyre_curves.py` and `ui/live_shell_bridge.py`. It pollutes every repo-wide grep | Housekeeping |

## Appendix B — Reproducing the runtime checks

All probes were run from `C:\Projects\VR_Dashboard` with
`PYTHONPATH=C:\Projects\VR_Dashboard`, against a **copy** of `data/pitcrew.db`
placed in the session scratchpad. Scratch files were not committed and are not in
the repo. The four probes were:

- **A/E** — `recommend` on a fuel-starved race; shows the infeasible plan winning.
- **C** — `recommend` on a tyre-starved race; shows `_fits` false on the winner.
- **F** — `_fuel_instruction` with `laps_total=60`, `stint_ends_on_lap=10`,
  `fuel_per_lap_l=10.0`; returns `'Fuel to 510 litres.'`
- **G** — two identical `recommend` calls over 360 candidates; byte-identical
  results, confirming determinism (no wall clock, no RNG — verified by grep
  across `pitcrew/strategy/` and `pitcrew/race/`).
- **Live** — `build_inputs(store, 1)` + `recommend` against the real event.
