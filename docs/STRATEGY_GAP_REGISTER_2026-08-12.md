# Strategy gap register — 12 Aug 2026

Measured against **"Race strategy — how it should be calculated"** (NGR Pit Crew
target design, 12 Aug 2026), supplied by the owner mid-audit. Companion to
[STRATEGY_CALCULATION_TRACE_2026-08-12.md](STRATEGY_CALCULATION_TRACE_2026-08-12.md),
which carries the full call chain, provenance table and constants register that
these findings cite.

> **The target design is not in the repo.** It was pasted into the session, not
> saved. Section references below (`§3.2`, `§8.4`…) resolve against the owner's
> copy. Save it as `docs/RACE_STRATEGY_TARGET_DESIGN_2026-08-12.md` from the
> authoritative text — transcribing it from a chat transcript risks silent drift
> in a document that is meant to be a contract.

**Severity**
**P1** — the calculation is wrong, a wrong number can reach the driver, or a
plan can be recommended that is illegal or runs the car dry.
**P2** — defensible arithmetic, but uncertainty, provenance or gating is missing,
so a measured answer cannot be told from a guessed one.
**P3** — architecture and maintainability.

No source was changed. Nothing staged, nothing committed.

---

## Summary

| | P1 | P2 | P3 | Total |
|---|---|---|---|---|
| A. The objective function | 3 | 3 | — | 6 |
| B. Gates and legality | 2 | 2 | 1 | 5 |
| C. Evidence and uncertainty | — | 5 | — | 5 |
| D. Live operation | 3 | 4 | — | 7 |
| E. Architecture | 1 | 2 | 3 | 6 |
| **Total** | **9** | **16** | **4** | **29** |

**The headline.** The strategy path does **not** have the setup path's
wired/unwired split — 15 of 16 modules are reachable, and 0 of 710 tests
exercise dead code. **Qualified by E6:** the three `*_wiring.py` files that
would *prove* that wiring cannot execute on this machine at all, so the
reachability result is static analysis, not a passing test. The defects are of a different kind: they sit in fully
wired, fully tested code, and they are dominated by *missing terms* and
*defeasible gates* rather than by disconnection. Two of them are live right now
against the stored event.

---

## A. The objective function

### A1 · P1 · A plan that cannot be run is scored, ranked and labelled "Fastest"

Target design §4: legality and survivability gates are "filters applied to the
candidate set *before* anything is ranked… A candidate that fails any gate is not
scored, not shown, and not held in reserve."

The code scores first and filters after — and the filter is defeasible:

```python
# pitcrew/strategy/model.py:600-602
    runnable = [plan for plan in plans if _fits(plan)]
    ordered = sorted(runnable or plans,
                     key=lambda p: (p.total_time_s, p.stops))
```

`runnable or plans` means that when *no* candidate is feasible, the infeasible
set is ranked as though it were fine. Worse, ranking is **monotonically wrong**
in that region, because the tank clamp at `model.py:479` caps `fuel_l` at
capacity, so an impossible plan is charged fuel weight for a tank it never
carries and pays no pit stops:

```
--- constructed: 100 laps, 10 L/lap, 100 L tank, max_stops=4 ---
  stops 0 laps [100] fuel_l [100.0] fits False
  fuel actually needed per stint: [1010.0]
```

The zero-stop plan **wins a race it cannot finish**, and it wins *because* it is
impossible.

**Live today.** Against a copy of `data/pitcrew.db`:

```
  stops=4 laps=[5, 5, 5, 5, 9] t=3478s constraint=tyre fits=False   (×5, all tied)
  notes[0]: Stint 5 is 9 laps but only 5 are runnable on RH (tyre-limited).
```

Every plan the Strategy screen would show right now is infeasible. The last stint
runs 9 laps on a 5-lap tyre — 150% of modelled life, well past the cliff.

**And the card does not say so.** `PlanCard`
(`pitcrew/ui/strategy_screen.py:157-194`) renders label, `"Fastest"`, race time,
stint bar and *"Limited by tyre"*. It never reads `plan.notes`. The only
surfacing is `notes[0]` **of the top plan**, in the subtitle
(`strategy_screen.py:341-343`), next to the words *"5 legal plans"*. The Approve
button is enabled (`strategy_screen.py:331`), and `missing()` returns `[]`, so
the controller prints **"Every input measured."** (`controller.py:961`).

**Evidence:** `pitcrew/strategy/model.py:600-602`, `:479`, `:713-716`, `:386` ·
`pitcrew/ui/strategy_screen.py:157-194`, `:331`, `:341-343` ·
`pitcrew/controller.py:961`

---

### A2 · P1 · No in-lap or out-lap penalty term exists anywhere

Target design §3.1 includes `π(l)` in the lap-time model; §3.4 decomposes pit
loss as `Δ_lane + t_tyres + V/ṙ + Δ_in + Δ_out + p_penalty`. CLAUDE.md §5.4 says
the cold out-lap costs 0.5–1.5 s and is *the reason the undercut is weak in GT7*.

The stop cost in the code is three terms:

```python
# pitcrew/strategy/model.py:488-490
            total += inputs.pit_loss_s + inputs.pit_dead_time_s
            if fuel_needed:
                total += refuel_time_s(fuel_needed, inputs)
```

`Δ_in`, `Δ_out` and `p_penalty` are absent. Grep across `pitcrew/strategy/` and
`pitcrew/race/` returns no in-lap or out-lap cost outside docstrings. Every stop
is therefore **under-costed by ~0.5–1.5 s**, biasing systematically toward more
stops — the exact direction §6.2 says is expensive. Nothing in the code, the
notes or `as_export`'s `assumptions` block records the omission.

**Evidence:** `pitcrew/strategy/model.py:488-490`, `:255-265`

---

### A3 · P1 · The refuel rate decides the race, is typed by hand, and nothing measures it

Target design §0.4 and §11 item 1: *"the highest-value single measurement in the
whole project."* §8.7 makes the reason explicit — the fuel-saving break-even is
`c < Δ / ṙ`, so the entire doctrine scales inversely with `ṙ`.

`refuel_rate_lps` is driver-entered event data. Three code defaults of **2.5**
(`model.py:136`, `store/schema.py:71`, `prompts/context.py:32`), a UI spinbox
defaulting to 2.5 over a 0.1–20.0 range (`ui/event_screen.py:265-268`). The live
event holds **1.0**:

```
sqlite> select refuel_rate_lps, pit_loss_secs from events;
1.0 | 19.0
```

**Nothing measures it.** `pitcrew/telemetry/session_state.py:240-256` detects a
pit stop *by observing that fuel is rising at low speed* — it has both quantities
needed for `Δfuel / Δt` and computes neither.

Sensitivity at the live event (29 laps, 6.224 L/lap, 4 stops): a ~37 L fill costs
**37 s at 1 L/s and 7.4 s at 5 L/s**. Across four stops that is ~120 s — larger
than the entire spread between the strategy options being ranked. The stop count
is decided by this number alone.

The discrepancy is already known and written down:
*"At the current event refuel is 1 L/s against a 2.5 default, and it decides the
whole race"* (`pitcrew/prompts/build.py:527`).

**Evidence:** `pitcrew/strategy/model.py:136`, `:429` ·
`pitcrew/store/schema.py:71` · `pitcrew/prompts/context.py:32` ·
`pitcrew/prompts/build.py:527` · `pitcrew/telemetry/session_state.py:240-256` ·
`data/pitcrew.db` events row

---

### A4 · P2 · Tyre change is not modelled at all — serial vs parallel is unrecorded

Target design §3.4: *"Modelling a max as a sum (or vice versa) is a material
error. Measure it, then encode which one is true, with provenance."* §11 item 2
ranks it second-highest value.

The code models **neither**. There is no `t_tyres` term (`model.py:488-490`). It
implicitly assumes tyre change is free, or already inside the driver's
`pit_loss_secs`. Which of those it assumes is recorded nowhere — not in a
comment, not in the plan notes, not in the exported `assumptions` block. A driver
who measures `pit_loss_secs` as a full stationary stop double-counts
`PIT_DEAD_TIME_S`; one who measures it drive-through-only under-counts the tyre
change entirely.

The export compounds this by declaring the provenance unconditionally:

```python
# pitcrew/strategy/model.py:256-257
                "pitLossS": inputs.pit_loss_s,
                "pitLossSource": "measured-this-track",
```

`"measured-this-track"` is emitted regardless of how the number was obtained.

**Evidence:** `pitcrew/strategy/model.py:488-490`, `:256-257`

---

### A5 · P2 · Fuel quantity is not a decision variable

Target design §2 ("Partial fill supported… fuel quantity is therefore a
**decision variable, not a constant**") and §3.4 ("`V_added` is a decision
variable. Filling to full by default leaves seconds on the table at every stop").

Fixed policy, not searched:

```python
# pitcrew/strategy/model.py:476-479
            fuel_needed = (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l
            if inputs.fuel_capacity_l:
                fuel_needed = min(fuel_needed, inputs.fuel_capacity_l)
```

Defensible under CLAUDE.md §5.4 (diamond plus one lap) and *better* than
fill-to-full, but it is not a search. Stop laps are not searched either — they
come from `allocate_laps` (`model.py:350-395`), whose own docstring says *"This
is a heuristic, not a proven optimum"* (`model.py:364`).

**Evidence:** `pitcrew/strategy/model.py:476-479`, `:350-395`, `:364`

---

### A6 · P2 · The entire fuel-map model is inert

Target design §2 and §11 item 6 (lap-time cost per fuel-map step is one of the
six quantities to measure); §8.7 makes lift-and-coast and map changes the primary
live fuel lever.

```python
# pitcrew/strategy/model.py:52-53
FUEL_MAP_CONSUMPTION = {1: 1.00, 2: 0.92, 3: 0.85, 4: 0.78, 5: 0.72, 6: 0.50}
FUEL_MAP_POWER = {1: 1.00, 2: 0.96, 3: 0.92, 4: 0.88, 5: 0.85, 6: 0.80}
```

**Read by nothing** — verified, one reference each, the definition. There is no
fuel-map dimension in the optimiser, and `LapInput.fuel_map`
(`pitcrew/analysis/session.py:36`) is captured and stored but consumed by no one.

Meanwhile the live engineer *does* issue a map instruction —
`"Map 3 down the straights."` (`pitcrew/race/calls.py:219`) — as a **hardcoded
string**. Map 3 is not chosen; it is spelled.

**Evidence:** `pitcrew/strategy/model.py:52-53` · `pitcrew/analysis/session.py:36`
· `pitcrew/race/calls.py:219`

---

## B. Gates and legality

### B1 · P1 · The fuel floor is a soft, post-hoc, string-matched check

Target design §4: the fuel floor must hold *"for **every** lap under the
*pessimistic* burn percentile, not the mean"*, as a pre-scoring filter.

The code has no percentile — burn is a single median (`evidence.py:198-200`) —
and feasibility is detected by **string-matching a note the plan wrote about
itself**:

```python
# pitcrew/strategy/model.py:713-716
def _fits(plan: Plan) -> bool:
    """Whether every stint is inside what its own compound can run."""
    return not any(note.startswith("Stint ") and "runnable on" in note
                   for note in plan.notes)
```

A reworded note silently disables the only feasibility check in the system. Then
A1's `runnable or plans` discards it entirely when it matters most.

**Evidence:** `pitcrew/strategy/model.py:713-716`, `:464-468`, `:600` ·
`pitcrew/strategy/evidence.py:198-200`

---

### B2 · P1 · No reserve, no minimum stint, and required compounds can be satisfied by a one-lap stint

Target design §4 gate table.

| Gate | Status |
|---|---|
| Mandatory stops | Present, hard, pre-scoring — `model.py:533` |
| Required compounds | Present but weak — see below |
| Minimum stint length | **Absent.** A 1-lap stint is admissible |
| Fuel floor | Soft — B1 |
| Tank ceiling | Clamp, not a gate — `model.py:479` |
| Executability | **Absent** — D3 |
| Compound availability | **Not condition-filtered** — B3 |
| Reserve | **Absent.** §4: *"Reserve sizing is a real decision, not a constant"*; the code has `FUEL_MARGIN_LAPS = 1.0`, a constant |

Required compounds is set membership only:

```python
# pitcrew/strategy/model.py:535-538
    if inputs.required_compounds:
        used = {stint.compound for stint in plan.stints if stint.compound}
        if not set(inputs.required_compounds) <= used:
            return False
```

Combined with the absent minimum stint length, a **1-lap stint satisfies a
compound requirement**. §2 notes GT7 punishes non-compliance with a post-race
2-minute penalty, and §6.2 puts missing a mandatory compound in the
never-a-scored-term row.

**Evidence:** `pitcrew/strategy/model.py:531-539`, `:479`, `:49`

---

### B3 · P2 · Wet compounds are enumerated as candidates for a dry race

`available_compounds` is not filtered by conditions. The live event lists
`('RH','RM','RS','IM','HW')` and `_candidate_sequences` takes the full ordered
product (5⁵ = 3125, under `MAX_CANDIDATES`), so intermediates and heavy wets are
costed as dry-race options using the reference compound's borrowed wear rate.

Target design §7 treats compound-vs-wetness as an optimal-stopping problem over a
wetness trajectory; the code has no wetness state at all.

**Evidence:** `pitcrew/strategy/model.py:542-561`, `:549` · `data/pitcrew.db`
events row

---

### B4 · P2 · No weather and no damage state

Target design scope table names both as in scope; §7 and §8.6 specify the
handling. Neither concept exists anywhere in `pitcrew/strategy/` or
`pitcrew/race/`. There is no driver-declared wetness input, no wet compound pace
model, no damage flag, and no contingency branch for either (see D6).

**Evidence:** absence across `pitcrew/strategy/`, `pitcrew/race/`

---

### B5 · P3 · The candidate search narrows silently, and a comment claims otherwise

Target design §10: *"No silent caps — if a workflow bounds coverage, log what was
dropped."*

```python
# pitcrew/strategy/model.py:555-559
    if len(available) ** stints > MAX_CANDIDATES:
        # Too wide to enumerate honestly. Fall back to the assignments worth
        # most: every stint on one compound, for each compound. The narrowing
        # is reported in the plan's notes rather than passed off as a search.
        return [[code] * stints for code in available]
```

**No such note is ever added.** `build_plan` appends notes at `model.py:466`,
`:494`, `:499`, `:511`, `:516`, `:521` — over-limit stints, tyre window, guessed
compounds, wear phase, multiplier. None mentions narrowing, and `build_plan` has
no way to know it happened. Verified by probe: 11 compounds over 5 stints returns
**22 candidates, silently**, where the driver would reasonably read the result as
a search.

**Evidence:** `pitcrew/strategy/model.py:555-559`, `:466-521`

---

## C. Evidence and uncertainty

### C1 · P2 · Degradation is not confounded with fuel burn in the strategy path — but it is in the export

Target design §3.2, the highest-priority question in the commissioning prompt.

**Verdict: NOT PRESENT in the strategy calculation.** This is a genuine strength
and it should be protected. `wear_per_lap` is a driver gauge reading divided by
the laps *that set* ran:

```python
# pitcrew/analysis/wear.py:65-69
    @property
    def rate(self) -> float | None:
        """Fraction consumed per lap on this set."""
        if not self.worst or self.worst <= 0 or self.lap_count < 1:
            return None
        return self.worst / self.lap_count
```

No regression against tyre age, no free stint intercept, so nothing for fuel burn
to contaminate. The `d − k_f·b` identification problem does not arise. The stint
grouping at `wear.py:83-90` also correctly avoids dividing by lap *number*, which
would understate every stint after the first.

**Verdict: CONFIRMED in the export path.** `degradation_ms_per_lap` is an
uncorrected difference-of-halves fit:

```python
# pitcrew/analysis/wear.py:230-232
    drift = mean([lap.lap_time_ms for lap in second_half]) - \
        mean([lap.lap_time_ms for lap in first_half])
    return round(drift / gap_laps, 1)
```

It ships to the external race-engineering tool as `wear.byLapTime.degradationMsPerLap`
(`wear.py:299-309` → `pitcrew/export/build.py:236`). At the live event's numbers
(6.224 L/lap × 0.003 s/L/lap) the car sheds **≈18.7 ms/lap** to fuel burn alone,
so the figure understates true degradation by about that much. It is labelled
`"confidence": "low"` and `"source": "lap-time-model"`, which is honest, but not
`fuel-uncorrected`.

It is also not a robust slope — a difference of half-means, not Theil–Sen or
Huber as §9 `estimate/robust.py` specifies, so one fat-tailed lap moves it.

**Evidence:** `pitcrew/analysis/wear.py:65-69`, `:83-90`, `:152-170`, `:215-232`,
`:299-309` · `pitcrew/export/build.py:236`

---

### C2 · P2 · No interval, no minimum sample, on any quantity

Target design §3.3 gives the precision limit
`σ_d̂ = σ_ε·√(12/(n(n²−1)))` and states that *"any tool reporting a degradation
figure after 5 laps without an interval is lying"*, and that before ~lap 10 the
estimate is mostly prior.

Nothing in the codebase attaches a standard error, an interval or a posterior to
any value. Minimum samples:

| Quantity | Minimum before a number is produced |
|---|---|
| Reference lap time | **1** counted lap (`session.py:160-163`) |
| Fuel per lap | **1** positive burn (`evidence.py:200`) |
| `wear_per_lap` | **1** gauge reading on **1** stint (`wear.py:169-170`) |
| Compound pace delta | **1** lap per compound (`evidence.py:167`) |
| `degradation_ms_per_lap` | 3 counted laps (`wear.py:222`) |

Sample **counts** do travel alongside aggregates — `laps_measured`,
`stints_measured` (`evidence.py:179-180`), `lapsSampled` — which honours
CLAUDE.md §4.4. But a count is not an interval, and no count gates anything. A
one-lap fuel figure and an eleven-lap one enter `RaceInputs` identically and rank
plans identically.

There is no shrinkage toward a practice prior (§3.3), no profile likelihood for
the cliff onset (§3.3), and the cliff breakpoint is a hardcoded constant
(`PHASE_CLIFF_FROM = 0.90`, `model.py:33`) rather than a fitted, interval-bearing
quantity.

**Evidence:** `pitcrew/analysis/session.py:160-163` ·
`pitcrew/strategy/evidence.py:167`, `:179-180`, `:200` ·
`pitcrew/analysis/wear.py:169-170`, `:222` · `pitcrew/strategy/model.py:32-33`

---

### C3 · P2 · The clean-lap gate excludes three things and misses four

Target design §8.3 rule 1: *"Clean-lap gate first — it matters more than the
statistics."*

```python
# pitcrew/analysis/session.py:51-54
    @property
    def counted(self) -> bool:
        """Out-laps, in-laps and anything the driver excluded do not count."""
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)
```

| §8.3 requires excluding | Status |
|---|---|
| In-laps | Excluded |
| Out-laps | Excluded |
| Driver-excluded | Excluded |
| **First lap of a stint** | **Not excluded** |
| **Laps under caution** | **Not excluded** — no caution concept in the schema |
| **Off-track / contact laps** | **Not excluded** |
| **Laps where the app itself commanded a lift** | **Not excluded** |

The off-track omission is the sharpest, because the data already exists:
`_off_track_count` computes excursions per lap from the surface channel
(`session.py:115-134`) and exports them, and **gates nothing**. With medians
running over ~6 laps, one four-wheels-on-the-grass lap is a sixth of the
evidence.

The last row is §8.3's subtle trap — *"once the engine issues pace or fuel
targets, its own instructions confound its own degradation estimate"*. The app
issues `"Map 3 down the straights."` and `"You can push."` (`calls.py:219,228`)
and does not record the commanded target against the lap.

**Evidence:** `pitcrew/analysis/session.py:51-54`, `:115-134` ·
`pitcrew/race/calls.py:219`, `:228`

---

### C4 · P2 · Three provenance fields exist, are documented as load-bearing, and are unreachable

Target design §11: every measured constant should be *"provenance-tagged,
per-event… with an explicit fallback and a visible marker when the fallback is in
use"*.

| Field | Where | Status |
|---|---|---|
| `fuel_weight_s_per_l_per_lap` | `model.py:144` | **Never set by `build_inputs`** (`evidence.py:214-227`). The comment at `model.py:40` and the evidence row at `evidence.py:265-267` both tell the driver he can overwrite it. He cannot |
| `pit_dead_time_s` | `model.py:138` | Never set; the 7.5 s constant always applies |
| `wear_measured_at_race_multiplier` | `model.py:140` | Never set, so the `[ASSUMED]` multiplier warning at `model.py:516-519` — required by CLAUDE.md §5.2 — is **unreachable from the app** |
| `starting_fuel_l` | `model.py:145` | Never set and never read |

`CompoundProfile.evidence_is_clean` (`model.py:103-113`) is the sharpest case.
Its docstring states a ranking rule — *"a plan resting on it is not the same
claim as one resting on a compound that ran in its window, and the two must not
rank against each other silently"* — and the property **has no non-test caller**.
Ranking is `total_time_s` alone (`model.py:601`). They do rank silently.

**Evidence:** `pitcrew/strategy/model.py:103-113`, `:138-145`, `:516-519`,
`:601` · `pitcrew/strategy/evidence.py:214-227`, `:265-267`

---

### C5 · P2 · Confidence is a caption, never an input to a decision

Target design §6, §8.4 gate 4 (*"evidence grade of the driving input ≥ the grade
required for that trigger"*).

| Mechanism | Affects any number or decision? |
|---|---|
| `SOURCE_MEASURED / _DECLARED / _ASSUMED` (`model.py:63-65`) | No |
| `Call.confidence` HIGH/MEDIUM/LOW (`calls.py:21-23`) | No — appends `"Unconfirmed."` to speech (`calls.py:62-63`) |
| `Replan.confidence` (`replan.py:47`) | **No** — set to `"low"` at `replan.py:141,149`, read by nothing. `_check_replan` gates on `verdict.offered` alone (`controller.py:1148`) |
| `Evidence.source` registers (`evidence.py:28-31`) | No — display only |
| `Plan.rests_on_assumption` (`model.py:217-220`) | Only the crossover verdict *wording* (`model.py:677`) |

The clearest illustration is live: five plans tie at exactly 3478 s because all
are planned on the same borrowed rate. The crossover verdict says so in words —
*"they are being planned on the same number. This is not a comparison yet"*
(`model.py:678-681`) — while the sort still emits one as **"Fastest"** with a
hard number beside it. The prose is right; the ranking is arbitrary.

**Evidence:** `pitcrew/strategy/model.py:63-65`, `:217-220`, `:677-681` ·
`pitcrew/race/calls.py:21-23`, `:62-63` · `pitcrew/race/replan.py:47`, `:141`,
`:149` · `pitcrew/controller.py:1148`

---

## D. Live operation

### D1 · P1 · The engineer will tell the driver to put 510 litres in a 100-litre tank

Target design §8.7 (fuel advice must be executable) and §10 row 7 (*"claim-check
every number against state before speaking"*).

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
`build_plan` applies at `model.py:479` has no counterpart on the live path.
Verified:

```
--- laps_total=60, stint_ends_on_lap=10, fuel_per_lap_l=10.0 ---
  _fuel_instruction -> 'Fuel to 510 litres.'
```

Spoken at HIGH confidence, inside a `BOX_NOW` call (`calls.py:177,182`), under a
helmet, at racing speed.

Separately, §8.7 asks for `margin_laps` and a **corner count** — *"Lift three
corners: one, six, eleven"* — not litres. The app emits litres and a hardcoded
map number.

**Evidence:** `pitcrew/race/calls.py:75-91`, `:177-182`, `:199-207` ·
`pitcrew/strategy/model.py:479`

---

### D2 · P1 · Telemetry loss produces confident calls off frozen data, and the warning goes to a screen nobody is looking at

Target design §8.6 (`TELEMETRY_LOST` card: *"freeze the committed plan, suppress
new recommendations, **tell the driver**"*), §8.3 rule 6, §10 row 8.

`RaceState` has no staleness concept (`calls.py:75-91`). On a dropout `fuel_l`
holds its last value forever, `laps_of_fuel()` keeps returning a number computed
from it (`calls.py:98-102`), and `_fuel` keeps issuing HIGH-confidence calls off
it once past lap 3 (`calls.py:215-230`).

The health monitor **is** started for a race (`controller.py:1034`) and
`_report_health` (`controller.py:873-902`) distinguishes bind failure,
source-filter rejection, no-stream and decode failure carefully. It writes every
one of them to:

```python
# pitcrew/controller.py:884, :890, :896, :900
            self.practice.set_status(...)
```

the **Practice** screen. During a race that surface is not on screen, the message
is never spoken, and nothing gates a call on it. There is no return-to-last-known
phase, no per-channel freshness budget, and no `UNKNOWN` propagation.

**Evidence:** `pitcrew/race/calls.py:75-91`, `:98-102`, `:215-230` ·
`pitcrew/controller.py:873-902`, `:1034`

---

### D3 · P1 · No commitment point, and a tyres-only stop makes the coordinator silently wrong for the rest of the race

Target design §8.5, described there as *"the most under-implemented concept in
amateur strategy tools"*.

`_box_now` fires when the stop lap has already passed:

```python
# pitcrew/race/calls.py:170-183
def _box_now(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if to_stop > 0:
        return None
```

`laps_to_stop() <= 0` means the lap that *should have ended* in the pits has
completed — one lap late by construction. There is no `commit_deadline`, no
expiry, no cancel, and no pre-filtering of the candidate set by feasibility.
`_box_soon` at 1–2 laps out (`calls.py:190`) is suppressed once said
(`calls.py:138-140`), so the lead-time ladder of §8.8 is two rungs, not five, and
neither rung is deadline-aware.

**The execution-detection hole.** Pit detection is entirely
fuel-rising-at-low-speed (`pitcrew/telemetry/session_state.py:240-256`). GT7
permits a tyres-only stop. On one of those, `PIT_EXIT` never fires,
`clear_stint` never runs (`coordinator.py:123`), `stint_index` never advances,
and `laps_to_stop()` stays ≤ 0 forever. `_box_now` is suppressed by
`state.said` so it does not repeat — the failure is *silent*. Every downstream
number — `lapsToStop`, `nextCompound`, `stopFuelL` (`controller.py:1101`) — is
wrong for the remainder of the race.

This is the D1-shaped defect the commissioning prompt asked about: the app issues
an instruction whose execution nothing reliably detects.

**And the module that would fix it is dead.** `pitcrew/telemetry/pit_state.py`
grades exactly this (`MEDIUM` refuel-based, `LOW` speed-only —
`pit_state.py:41`, `:189`) and has **no importer anywhere in the repo, test or
otherwise**.

**Evidence:** `pitcrew/race/calls.py:170-183`, `:138-140`, `:190` ·
`pitcrew/race/coordinator.py:118-125` ·
`pitcrew/telemetry/session_state.py:240-256` ·
`pitcrew/telemetry/pit_state.py:41`, `:189` · `pitcrew/controller.py:1101`

---

### D4 · P2 · Divergence detection is two raw thresholds on unfiltered single laps

Target design §8.3: clean-lap gate → EWMA for reporting → CUSUM (k = 0.5, h = 5)
for acting → directional asymmetry → reset on signal.

```python
# pitcrew/race/replan.py:27-32
FUEL_DRIFT = 0.05      # 5% off the planned burn rate
PACE_DRIFT = 0.02      # 2% off the reference lap
WORTH_CHANGING_S = 8.0
```

| §8.3 requirement | Status |
|---|---|
| Clean-lap gate | **Absent on the live path entirely.** An in-lap, out-lap or off feeds `pace_drift` directly |
| EWMA | Absent |
| CUSUM | Absent |
| Directional asymmetry | Absent — `abs(drift)` both sides (`replan.py:114,118`) |
| Reset on signal / at stops | Absent |
| `UNKNOWN` propagation | Partial — `drift()` returns `None` (`replan.py:83-87`), which suppresses that channel silently rather than downgrading confidence |

The pace input is a **single raw lap**, `lap.lap_time_ms` (`controller.py:1142`).
The fuel input **is** median-filtered over ≥3 laps (`coordinator.py:158-160`) —
so the pattern was known and applied to one of the two channels. 2% of a 107 s
lap is 2.1 s, comfortably inside one traffic lap.

**Evidence:** `pitcrew/race/replan.py:27-32`, `:83-87`, `:108-121` ·
`pitcrew/race/coordinator.py:158-160` · `pitcrew/controller.py:1142`

---

### D5 · P2 · One of the five switching gates exists

Target design §8.4 requires GAIN ∧ PERSISTENCE ∧ DWELL ∧ CONFIDENCE ∧ FEASIBLE.

| Gate | Status |
|---|---|
| **GAIN** | **Present** — `WORTH_CHANGING_S = 8.0` (`replan.py:32`, `:155-156`). The best-designed thing on the live path |
| PERSISTENCE (m-of-n) | Absent |
| DWELL (D laps since last change) | Absent |
| CONFIDENCE grade | Absent — C5 |
| FEASIBLE (≤ commitment point) | Absent — D3 |

Also absent: `z·σ_diff` in θ (no paired uncertainty exists — D7), `C_switch`,
and the two-sided `θ_in / θ_out` hysteresis §8.4 requires to stop oscillation at
the boundary. `WORTH_CHANGING_S` is symmetric, and §6.2's 21:1 asymmetry between
shortening and extending a stint is not encoded anywhere.

§8.4's *"recommend a window, commit a lap"* is absent: `Replan` carries a single
`stops` and `stint_laps` tuple (`replan.py:44-45`), never `[earliest, optimal,
latest]` with a cost curve.

Partial mitigation: `_pending_replan is not None` blocks a second offer until the
driver answers (`controller.py:1148`), which bounds the practical thrash rate by
his responses rather than by the model.

**Evidence:** `pitcrew/race/replan.py:32`, `:44-45`, `:155-156` ·
`pitcrew/controller.py:1148`

---

### D6 · P2 · No contingency cards

Target design §8.6. None of the eight triggers exists — `CAUTION`, `RAIN_ONSET`,
`DAMAGE`, `FORCED_STOP`, `TYRE_CLIFF`, `FUEL_HIGH`, `PACE_OFF_PLAN`,
`TELEMETRY_LOST`. There is no `ContingencyCard`, no `PlanDelta`, no
`TriggerKey`, no background refresh, no freshness or feasibility validation at
trigger time.

The live path does the opposite of §8.6's rule: on divergence it runs a **fresh
optimisation under time pressure** — `recommend(rest, max_stops=3)` inside
`assess` (`replan.py:146`) — which §8.6 explicitly names as the thing
pre-computation exists to avoid. Measured at **~20 ms** for the live event's
5-compound shape, so it is not a performance problem; it is a
*recognition-vs-comparison* problem at the moment of highest driver load.

The highest-value card per §8.6 — caution, because it collapses the pit-loss term
— cannot be built at all: there is no caution signal in GT7 telemetry and no
driver-declared substitute.

**Evidence:** `pitcrew/race/replan.py:146` · absence across `pitcrew/race/`

---

### D7 · P2 · No scenario sampling, therefore no CRN, no CVaR, no regret

Target design §5, §6.

Every input is a point estimate; `total_time_s` is a point estimate; selection is
`min` over `(total_time_s, stops)` (`model.py:601-602`). There is no scenario
table, no seeded stream, no paired difference, no `σ_diff`, no CVaR, no minimax
regret, no feasibility probability, and no risk-posture switch.

`Plan.delta_s` (`model.py:604-605`) is a point-estimate gap between candidates —
the raw material for §3.5's cost curve, but with no uncertainty attached it
cannot answer the separability question. The crossover band does better,
reporting `breakEvenSPerLap` and a margin test at 0.15 s/lap (`model.py:693`) —
that is the closest thing in the codebase to §3.5's *"are the top plans separable
at all"*, and it is genuinely good work. It applies to compound choice only, not
to stop count.

**Assessment.** This is the largest single gap against the design, and it is also
the one I would build **last** — see the plan, item P3-6. With sample sizes of
one-to-six laps and six unmeasured constants (§11), scenario sampling would put a
confidence interval around a guess. §5's variance reduction is real, but it
reduces *Monte Carlo* variance, not *parameter* uncertainty, and parameter
uncertainty is what dominates here.

**Evidence:** `pitcrew/strategy/model.py:601-605`, `:693`

---

## E. Architecture

### E1 · P2 · Committed plan and live projection are separated; the candidate set is discarded and the commit is destructively mutated

Target design §8.1.

| Object | Status |
|---|---|
| **Committed plan** | `RaceCoordinator._stints` (`coordinator.py:63`), from the approved DB row. **Not** immutable, **not** versioned, **not** content-hashed |
| **Live projection** | `RaceState` (`calls.py:75-107`) — mutable dataclass, recomputed per lap. Broadly correct |
| **Candidate set** | Rebuilt inside `assess` and **discarded**; only `best.stops` and `best.stint_laps` survive (`replan.py:161-162`) |

Genuinely right: the plan is never silently switched. `_pending_replan` holds the
offer (`controller.py:1152`) and it is applied only on an explicit driver ACCEPT
through PTT (`controller.py:1110-1124`). Every offer is persisted accepted-or-not
(`controller.py:1084-1087`, `:1120-1122`) — which is most of §9's
`DecisionRecord` intent, for the *changes*.

Two defects:

**`adopt` destroys the plan's content.** (`coordinator.py:187-204`)

```python
# pitcrew/race/coordinator.py:199-201
        for laps in stint_laps:
            fresh.append({"laps": laps, "compound": None, "fuel_l": None,
                          "start_lap": start})
```

After one accepted re-plan, the plan no longer knows which tyre to fit or how
much fuel to take. `_box_now`'s compound clause (`calls.py:178`) goes silent and
`stopFuelL` (`controller.py:1101`) becomes `None`. The driver loses the two facts
he most needs at the stop, **as a side effect of accepting advice**.

**Non-changes are not logged.** §9: *"'We considered stopping on lap 17 and
rejected it because dwell had not elapsed' is the single most valuable record for
debugging thrash."* `append_revision` fires only when a call is emitted or an
offer resolved. The `Replan(NONE, "…but the plan still wins")` path
(`replan.py:156`) computes exactly the §9 `DecisionRecord` payload —
`gain_s`, `threshold_s`, `blocked_by` — and discards it.

**Evidence:** `pitcrew/race/coordinator.py:63`, `:187-204` ·
`pitcrew/race/replan.py:156`, `:161-162` · `pitcrew/race/calls.py:178` ·
`pitcrew/controller.py:1084-1087`, `:1101`, `:1110-1124`, `:1152`

---

### E2 · P3 · Determinism and replayability: a clean pass

Target design §9. This is the strongest result in the audit and it should be
locked down with a test before anything else changes.

| §9 invariant | Status |
|---|---|
| No wall-clock inside logic | **Confirmed** — grep across `pitcrew/strategy/` and `pitcrew/race/` finds no `time.`, `datetime`, `now()` |
| No global RNG | **Confirmed** — no `random` |
| Replay determinism | **Confirmed by probe** — two `recommend` calls over 360 candidates returned byte-identical results. `build_inputs(store, event_id)` is a pure function of the DB |
| Off the telemetry thread | **Confirmed** — `on_packet` runs on the UDP thread (`controller.py:100-101`) and hands off via `pyqtSignal` (`controller.py:66-69`), so strategy runs on the Qt thread. Measured 106 ms pre-race / 20 ms per live lap — acceptable |
| Idempotence | Untested |
| Content-hash plan comparison | **Absent** — plans are matched on `(stops, compounds)` (`controller.py:938-44`), and rounding happens inside `as_export` (`model.py:264`) rather than at a single presentation boundary |
| Golden-race replay test | **Absent** — §10 test 1, and CLAUDE.md §7 asks for a checked-in session fixture |

Notable good history: `reference_compound` (`evidence.py:110-132`) documents a
fixed bug where iterating a `set` made the reference compound depend on string
hash randomisation — *"a different reference compound per process, and with it a
different sign on every pace delta"*. Exactly §9's failure mode, already found
and fixed.

**Evidence:** `pitcrew/strategy/evidence.py:110-132` ·
`pitcrew/controller.py:66-69`, `:100-101`, `:938-944` ·
`pitcrew/strategy/model.py:264`

---

### E3 · P3 · No race-phase state machine

Target design §9 requires
`PRE_SESSION → GRID → FORMATION → GREEN ⇄ CAUTION ⇄ {PIT_APPROACH → PIT_LANE →
OUT_LAP} → FINAL_LAP → FINISHED ⊥ TELEMETRY_LOST`, with each phase declaring
which estimators update and which recommendations may issue — and warns it *"must
actually gate emission or it will be decorative in exactly the way
`RaceWeekendPhase` currently is"*.

`RacePhase` (`coordinator.py:21-26`) has four states: `IDLE`, `ARMED`,
`RUNNING`, `FINISHED`. It **does** gate — `handle` returns `None` unless
`RUNNING` (`coordinator.py:114-115`) and `_on_green` refuses a race that started
unarmed (`coordinator.py:131-134`). So it is not decorative, which is the right
lesson learned.

Missing: `CAUTION` (no signal available), `PIT_LANE` / `OUT_LAP` as
estimator-freezing phases, `FINAL_LAP`, and `TELEMETRY_LOST` (D2). `in_pit` is a
bool on `RaceState` (`calls.py:83`) that suppresses calls but freezes no
estimator — the burn median at `coordinator.py:156-160` keeps accumulating
across a stop.

**Evidence:** `pitcrew/race/coordinator.py:21-26`, `:114-115`, `:131-134`,
`:156-160` · `pitcrew/race/calls.py:83`

---

### E4 · P3 · Constants are duplicated across three modules

`STINT_SAFETY_FACTOR = 0.85` is defined at `pitcrew/strategy/model.py:29` and
again at `pitcrew/analysis/wear.py:35`, and hardcoded a third time as the tyre
warning threshold at `pitcrew/race/calls.py:253`. Phase boundaries 0.5 / 0.9
appear at `model.py:32-33` and `wear.py:44-46`. The one-lap fuel margin is
`FUEL_MARGIN_LAPS` at `model.py:49` and a bare `+ 1` at `calls.py:206`.

Changing the safety factor in one place silently desynchronises the plan from the
live warning.

**Evidence:** `pitcrew/strategy/model.py:29`, `:32-33`, `:49` ·
`pitcrew/analysis/wear.py:35`, `:44-46` · `pitcrew/race/calls.py:206`, `:253`

---

### E6 · P1 · Every `Controller`-constructing test hangs on a SAPI COM call — added 12 Aug, during Commit 1

**Found while establishing a baseline for the Commit 1 fixes. It is pre-existing
— the working tree was unmodified — and it materially corrects this audit's own
§1.12 conclusion.**

`Controller.__init__` calls `best_recogniser_for` (`controller.py:185`), which
constructs `SapiGrammarRecogniser` (`ptt.py:517`), which does:

```python
# pitcrew/engineer/ptt.py:206-207
        pythoncom.CoInitialize()
        self._engine = win32com.client.Dispatch("SAPI.SpSharedRecognizer")
```

That `Dispatch` **blocks indefinitely** under pytest. Confirmed with
`faulthandler`, which dumps the hung frame:

```
Timeout (0:00:40)!
Thread 0x000080b8 (most recent call first):
  File "...win32com\client\dynamic.py", line 83 in _GetGoodDispatch
  File "...win32com\client\__init__.py", line 116 in Dispatch
  File "C:\Projects\VR_Dashboard\pitcrew\engineer\ptt.py", line 207 in __init__
  File "C:\Projects\VR_Dashboard\pitcrew\engineer\ptt.py", line 517 in best_recogniser_for
  File "C:\Projects\VR_Dashboard\pitcrew\controller.py", line 185 in __init__
```

**The `try/except Exception` at `ptt.py:519` cannot help** — a hang is not an
exception. The fallback chain is written to survive a missing recogniser and
does survive one; it has no defence against one that never returns.

Measured status per file:

| File | Result |
|---|---|
| `test_controller.py` | **Hangs from the first test** |
| `test_strategy_wiring.py` | **Hangs from the first test** |
| `test_race_wiring.py` | **Hangs from the first test** |
| `test_engineer_wiring.py` | **Hangs from the first test** |
| `test_ptt_and_replan.py` | 53 of 60 pass, then hangs |
| `test_event_inputs.py` | 17 pass, then hangs |
| `test_settings_and_diagnostics.py` | 13 pass, then hangs |
| All 21 other files | Pass — 604 tests |

CPU delta over 20 s on the hung process was 0.1 s against a flat working set,
which is how a hang is told from slowness here.

**Why this matters more than a flaky test.** §1.12 of the trace concluded that
this codebase avoids the 6 August wired/unwired failure because three dedicated
`*_wiring.py` files assert the screens are connected to the controller. Those
three files are `test_strategy_wiring.py`, `test_race_wiring.py` and
`test_engineer_wiring.py` — **all three are in the hang list, and none of them
can execute on this machine.** The import-graph reachability result stands
(15/16 modules reachable, verified statically). The claim that wiring is
*verified by a green suite* does not: the suite cannot reach those assertions.

**Minimal fix**, and it is small: give the recogniser factory the same
`PYTEST_CURRENT_TEST` seam the project already uses for the config-clobber
guardrail — skip SAPI construction under pytest, or make the recogniser
injectable so `Controller` can be built with a null one. Either way the
constructor stops depending on a COM object that may never answer. **Not done in
Commit 1**: it is in the PTT path, outside this task's stated scope, and it wants
its own review.

**Evidence:** `pitcrew/engineer/ptt.py:202-215`, `:511-522` ·
`pitcrew/controller.py:185` · faulthandler dump above

---

### E5 · P2 · `pitcrew/telemetry/pit_state.py` is unreachable

Zero importers in the repo — test or otherwise. 200 lines implementing graded pit
detection that D3 shows the live path needs. This is the one module matching the
old `strategy/tyre_curves.py` pattern.

**Evidence:** `pitcrew/telemetry/pit_state.py` · `grep -rn "pit_state"` returns
only the file itself

---

## Verdicts on the commissioned questions

| # | Design | Verdict | Where |
|---|---|---|---|
| **G1** | §3.2 identification | **NOT PRESENT** in the strategy path (gauge-based, no regression, no free intercept). **CONFIRMED** in the exported `wear.byLapTime` | C1 |
| **G2** | §0.4, §1.6 refuel rate | **CONFIRMED** — assumed, never measured, decides the stop count | A3 |
| **G3** | §3.4 serial vs parallel | **NOT APPLICABLE as posed** — the code models *neither*; there is no tyre-change term. The assumption is unrecorded | A4 |
| **G4** | §3.5 flatness | **PARTIAL** — `delta_s` gives a cost curve without uncertainty; the compound crossover band does report break-even and a separability margin, but only for compound choice, not stop count | D7 |
| **G5** | §4 hard gates before scoring | **NOT PRESENT** for fuel floor and tyre life — post-hoc, string-matched, and discarded by `runnable or plans`. Regulations *are* hard and pre-scoring | A1, B1, B2 |
| **G6** | §5 scenario sampling + CRN | **NOT PRESENT** | D7 |
| **G7** | §6 tail risk vs point estimate | **NOT PRESENT** — argmin of a point estimate | D7 |
| **G8** | §8.1 three objects | **PARTIAL** — committed/projection separated and never silently switched; candidate set discarded; commit destructively mutated by `adopt` | E1 |
| **G9** | §8.3 statistically gated divergence | **NOT PRESENT** — raw thresholds, no clean-lap gate, no CUSUM/EWMA, no reset | D4 |
| **G10** | §8.4 switching threshold / dwell | **PARTIAL** — GAIN present (`WORTH_CHANGING_S`); persistence, dwell, confidence, feasibility and two-sided hysteresis all absent | D5 |
| **G11** | §8.5 expiry / commitment | **NOT PRESENT** — and `_box_now` fires one lap late by construction | D3 |
| **G12** | §8.6 contingency branches | **NOT PRESENT** — none of the eight | D6 |
| **G13** | §8.7 executable fuel advice | **NOT PRESENT** — litres, unclamped, plus a hardcoded map number | D1, A6 |
| **G14** | §8.8 traceable spoken numbers | **CONFIRMED favourably** — all calls are deterministic f-strings over `RaceState`; there is no generative layer, so the 81.9% faithfulness risk does not apply. But there is no claim-check, and D1 proves an unphysical number can be spoken | D1 |
| **G15** | §9 deterministic and replayable | **CONFIRMED** — no wall-clock, no RNG, byte-identical across runs, pure function of the DB. Missing: content hashing, idempotence tests, golden-race replay | E2 |
| **G16** | §10 eight failure modes | See table below | — |
| **G17** | §12 opponent data | **PARTIAL** — the code makes exactly the mislabel §1.2 warns about, but the consequence is contained | below |

### G16 — which of §10's failure modes does the code permit?

| §10 failure mode | Permitted? |
|---|---|
| Stale offline lookup feeding a live gate | **No.** No precomputed lookup tables exist; the live path calls the same `recommend` as pre-race (`replan.py:146`) — one code path, not two. §10's *"tested path is not the executed path"* warning is specifically **not** present here: 0 of 710 tests exercise unreachable code |
| Stale state at the decision moment | **Yes** — D2. No freshness stamp, no staleness budget |
| Degradation extrapolated past validity | **Yes** — A1. `allocate_laps` pads the final stint past its cap (`model.py:386`), and no horizon cap or interval widening exists |
| Over-reacting to one lap | **Yes** — D4. Single raw lap into `pace_drift`, no clean-lap gate, no CUSUM. Partly mitigated by `WORTH_CHANGING_S` |
| Point estimates without uncertainty | **Yes** — C2, D7 |
| Confounded parameter estimation | **No** in the strategy path (C1) — the single best design decision in the codebase. **Yes** in the exported `wear.byLapTime` |
| Speech layer stating what the model does not contain | **No** generative layer. But **yes** in effect — D1's 510 L is spoken and unverified |
| Silent degradation | **Mostly no.** Zero bare `except` on the strategy path (a real improvement over the old code's nine), null-not-zero honoured widely — `wear.py:170`, `:200-203`, `session.py:122-123`, `model.py:320-323`. **But yes** at D2 (telemetry loss) and B5 (silent candidate narrowing) |

### G17 — opponent data

`pitcrew/telemetry/packet.py:449-459` asserts:

```python
    @property
    def current_position(self) -> int:
        """Live race position (1-based).

        GT7 encodes four bytes at offset 0x84:
          byte 0 (bits[7:0])   = current race position (updates live)
```

and `packet.py:159` documents `0x84` as `byte0=live_pos`. **This is exactly the
mislabel design §1.2 warns about** — *"The i16 at 0x84 is the pre-race grid slot
and goes to −1 at lights-out. At least one public library labels it
`race_position`. It is not."*

The consequence is contained, by accident rather than by check:

```python
# pitcrew/telemetry/packet.py:458-459
        pos = self.start_pos_and_cars & 0xFF
        return pos if 1 <= pos <= 100 else 0
```

`−1`/`0xFF` falls outside 1–100 → returns `0` → falsy at
`coordinator.py:149`, `calls.py:166` and `calls.py:269`, so it reads as *"no
position"* rather than a wrong one. Position is spoken only in `_status` and
`_chequer` and is not an input to any calculation.

**Graded P2, with a P1 escalation condition:** if GT7 *retains* the grid slot
during the race rather than zeroing it, the app will say **"P5. 20 to go."** for
an entire race regardless of actual position — a wrong number, spoken with
confidence. That is a one-run experiment (§ plan item M0). Elsewhere the codebase
is scrupulous about this: `pitcrew/analysis/gearing.py:14` and
`pitcrew/export/payload.py:207` both state plainly that GT7 carries no proximity,
closing speed or opponent positions.

Related and clean: the `−1` lap-time trap of §1.1 **is** guarded —
`session_state.py:272` requires `p.last_lap_ms > 0`.

**Evidence:** `pitcrew/telemetry/packet.py:159`, `:449-459` ·
`pitcrew/race/coordinator.py:149` · `pitcrew/race/calls.py:166`, `:269` ·
`pitcrew/telemetry/session_state.py:272`

---

## Where I think the target design is wrong or not applicable

Offered as pushback, per the commissioning prompt. The design was written without
access to this repository and is right about most of what it could not see.

**1. §3.2's identification result does not apply here, and §3.3's estimator would
be a regression.** The design assumes degradation is *fitted from lap times* —
reasonably, since that is what every other tool does. This app doesn't: it reads
the driver's in-game gauge, which is anchored to GT7's own wear model. That is
strictly better evidence than any lap-time fit, it sidesteps `d − k_f·b`
entirely, and it is already implemented and correct. **Do not replace the gauge
path with §3.3's profile-likelihood fit.** The right move is to keep the gauge as
primary and add the fuel-corrected lap-time fit as the *corroborating* second
source CLAUDE.md §3.3 asks for — which also fixes C1's export defect. This
changes the priority of §11 item 3 (`k_f`): it is still needed, but for
corroboration and for the fuel-weight term in the objective, not as the
foundation everything else is fitted on.

**2. §3.6's DP is over-engineered for this problem, and the state space is
wrong-shaped.** The proposed state is `(compound, tyre age, compounds-used
bitmask, fuel level)` over `l = 1..L`. For the live event that is 29 laps × 5
compounds × ~29 ages × 32 masks × 50 fuel bins ≈ 6.7M states — versus the current
exhaustive enumeration at **3905 candidates and 106 ms**. The DP's advantages
(cliffs natively, exact, value function for replanning) are real, but the current
enumeration already handles the cliff exactly, and at this problem size the
argument for DP is not speed. The genuine case for it is §3.6's *stochastic*
extension. I would not build the DP until D7 is wanted, and I would then build it
for that reason, stated.

**3. §5's Common Random Numbers is right in principle and premature in practice.**
CRN reduces *Monte Carlo* variance in the paired comparison. It does nothing
about *parameter* uncertainty, which here is total: `wear_per_lap` rests on one
gauge reading from one stint, and the refuel rate is typed by hand. Sampling
scenarios around those would produce a confident-looking interval around a guess
— and the design's own §11 says the same thing about optimisers ("A better
optimiser fed guessed constants is worth nothing"). §5 should be gated behind
§11, and I have sequenced it that way.

**4. §6.1's `P(win) ∝ P(finish legally) × P(T ≤ target) × P(no forced stop)` is
not a probability and should not be written as one.** The three factors are
strongly dependent — a forced stop is a common cause of both missing the target
time and failing legality — so the product understates the joint. It is a fine
*ranking* heuristic and the lexicographic ordering that follows (feasibility →
CVaR → regret → mean) is sound and implementable. I would ship the ordering and
drop the product notation, which invites exactly the fabricated-field-model
criticism §6.1 is trying to avoid.

**5. §1.4's "one consumer per console" is already violated in this deployment, and
the design's framing may be the wrong way round.** The design warns that the
packet format is latched by the first heartbeat and that a competing SimHub
instance means one of you reads garbage. In this app **SimHub is the relay** —
`pitcrew/telemetry/listener.py` binds and receives; the app never heartbeats the
PS5 (`controller.py:1031-1033`, `udp_source_ip` is an accept-filter). So the
mitigation is already in place by architecture, and the risk is inverted: the
app's exposure is SimHub stopping, not contending. `_report_health` already
distinguishes those cases well (`controller.py:883-902`) — it just tells the
wrong screen (D2).

**6. §8.6's caution card cannot be built.** It is named the highest-value card,
because caution collapses the pit-loss term. GT7 exposes no caution signal, and
in a private league there is no marshalling system to declare one. Unless the
driver is willing to press something mid-corner, this card has no trigger. I
would drop it rather than leave a card that never fires, and say why.

---

# Part 3 — Remediation plan

## The sequencing principle

Design §11 names six unmeasured quantities. The order below is set by **which
constants a change would be built on**, not by ambition. A better optimiser fed
guessed constants is worth nothing — and, as A3 shows, one of these constants is
currently deciding the stop count on its own.

Two changes are exceptions and go first, because they are wrong *regardless of
any constant*: A1 (an impossible plan ranked "Fastest") and D1 (510 litres).
Neither depends on a measurement.

**Phase 1 (base setup correctness) remains the agreed priority.** Everything in
Stage M below is measurement and documentation — it needs the driver in the car,
not the codebase, and runs in parallel with Phase 1 at zero merge risk. Stage 0
is small, self-contained and touches no file Phase 1 touches. Stage 1 onward
should wait.

---

## Stage 0 — Remove the P1s that need no measurement

**Runs in parallel with Phase 1.** ~1 day total. Blast radius given per item.

### 0-A · A1 · Stop ranking plans that cannot be run

Smallest fix, three parts:

1. Replace `runnable or plans` (`model.py:601`) with: if nothing is runnable,
   return the infeasible set **flagged**, and have the caller refuse rather than
   rank. `Plan` gains a `feasible: bool` field set in `build_plan` — replacing
   `_fits`'s string-matching (B1) at the same time.
2. `PlanCard` shows infeasibility on the card, not only in the subtitle
   (`strategy_screen.py:157-194`).
3. `build_strategy` disables Approve and does not print "Every input measured."
   when the top plan is infeasible (`controller.py:955-961`,
   `strategy_screen.py:331`).

**Blast radius:** `strategy/model.py`, `ui/strategy_screen.py`,
`controller.py:906-961`. `test_strategy_model.py` and `test_strategy_wiring.py`
will need new cases; existing assertions on `_fits` change shape.
**Verification:** a test that the live DB's event produces **zero approvable
plans**, and the constructed 100-lap/10 L case never returns a 0-stop winner.

### 0-B · D1 · Clamp the live fuel instruction

Add `fuel_capacity_l` to `RaceState` (`calls.py:75-91`), set it from
`inputs.fuel_capacity_l` in `start_race` (`controller.py:1010-1013`), and clamp
in `_fuel_instruction`. When the clamp binds, the plan is short — say so:
*"Fuel to full. Still two laps short."*

**Blast radius:** `race/calls.py`, `race/coordinator.py:53-64`,
`controller.py:1010-1013`. Small and well covered by `test_race.py`.
**Verification:** property test — no emitted fuel figure exceeds capacity, over
random `RaceState`s.

### 0-C · D2 · Route health warnings to the race surface and freeze on loss

Two changes: `_report_health` writes to the active screen, not always
`self.practice` (`controller.py:873-902`); and a stale-stream flag on `RaceState`
suppresses `_fuel`/`_tyre` calls and speaks *"Lost telemetry. Plan is frozen."*
once.

**Blast radius:** `controller.py:873-902`, `race/calls.py`. Needs a way for the
controller to know which screen is live — check whether `app.py`'s stack index is
already available before estimating further.
**Verification:** a test that drops the stream mid-race and asserts no
HIGH-confidence fuel call is emitted afterwards.

### 0-D · E2 · Lock determinism down before anything else moves

Check in a recorded session as CLAUDE.md §7 requires, and assert
`build_inputs → recommend` produces identical plan content across runs. This is
cheap now and it is the safety net for every later stage.

**Blast radius:** test-only, plus a fixture file.

### 0-E · B5, C4 · Truth-up the docstrings that describe behaviour that does not exist

Either implement or delete: the narrowing note (`model.py:557`), the
"driver can overwrite it" fuel-weight claim (`model.py:40`,
`evidence.py:265-267`), and `evidence_is_clean`'s ranking rule
(`model.py:103-113`). A comment asserting a guarantee the code does not provide
is worse than no comment — it is what made A1 survive review.

**Blast radius:** comments and one property. Zero runtime risk if deleted.

---

## Stage M — The measurement programme

**Runs in parallel with Phase 1.** This is driver time, not engineering time.
Ordered by what unblocks the most.

### M0 · One run, four answers · ~30 minutes in the car

A single race-length run with a scripted stop sequence settles four of the six:

| Measure | How | Unblocks |
|---|---|---|
| **Refuel rate ṙ** (§11-1) | Log `Δfuel/Δt` while stationary. Already in the stream | A3, and the entire §8.7 doctrine |
| **Serial vs parallel** (§11-2) | Three stops: tyres only, fuel only, both. Compare stationary times | A4, every double-stint calculation |
| **Pit-lane delta** (§11-4) | Entry line → exit line vs equivalent track time | Validates the typed `pit_loss_secs`, and separates `Δ_lane` from `t_tyres` so A4 can be encoded without double-counting |
| **Position field** (G17) | Read `start_pos_and_cars & 0xFF` from lap 1 to the flag, starting from a non-pole grid slot | Settles whether G17 is P2 or P1 |

The first three are all recoverable from **one recorded telemetry file**, which
means this is a capture-and-analyse task, not four experiments.

### M1 · Fuel weight `k_f` (§11-3) · ~20 minutes

Identical fresh tyres, tyre wear off, full tank vs ~10 L, same track, same map.
Fuel is telemetered directly, so this is the cleanest measurement available.

Unblocks: the fuel-weight term in the objective (currently a hardcoded 0.003 that
C4 shows is not overridable), and the fuel correction that C1's export fix needs.

### M2 · Compound deltas and degradation slopes (§11-5) · several sessions

≥12 clean laps per compound, gauge read at the end of every stint. §3.3 says
fewer than ~10 laps is prior-dominated, so this is a real programme, not a run.

This is what the practice loop already exists to do. Note the current state: the
live DB holds **six laps on one compound**, which is why every plan ties at
3478 s (A1). The app's compound comparison is correct and honest about this
already (`evidence.py:281-303`, `model.py:677-681`) — it is waiting for data, not
broken.

### M3 · Fuel-map lap-time cost (§11-6) · ~20 minutes

Paired laps at FM *n* and *n*+1. Deferred deliberately: A6 shows there is no
consumer for it yet, so measuring it early would be evidence with nowhere to go.

---

## Stage 1 — Encode what was measured *(blocked on M0, M1; after Phase 1)*

Nothing here is worth building before Stage M returns.

- **A3 →** measure the refuel rate from the first stop of each event, store it
  per event with provenance, and mark the plan when the typed value and the
  measured value disagree. This is where `pitcrew/telemetry/pit_state.py` (E5)
  gets wired instead of deleted — it already grades stop detection, which is
  exactly what a per-stop measurement needs to trust its own sample.
- **A4 →** add `t_tyres` and encode serial-or-parallel as a stored, provenance-
  tagged event property. Fix `"pitLossSource": "measured-this-track"`
  (`model.py:257`) to report the real provenance.
- **A2 →** add `Δ_in`/`Δ_out` to the stop cost. Cheap once M0 has separated pit
  transit from stationary time; wrong to guess before that.
- **C4 →** make `fuel_weight_s_per_l_per_lap`, `pit_dead_time_s` and
  `wear_measured_at_race_multiplier` settable from the event, so M1's number and
  the CLAUDE.md §5.2 multiplier warning can actually reach the model.
- **B2 →** minimum stint length, a sized reserve, and require required-compound
  stints to be non-trivial.

**Verification:** re-run the golden fixture from 0-D and diff the plan. Every
number that moves should be attributable to a measurement, and that attribution
should be in the export's `assumptions` block.

---

## Stage 2 — Live correctness *(after Stage 1)*

- **D3 →** commitment points. The app already models track progress and pit-lane
  geometry, so `commit_deadline` is a lookup. Pre-filter the candidate set by
  feasibility; expire recommendations; issue an explicit cancel. Wire
  `pit_state.py` so a tyres-only stop advances `stint_index`.
- **D4 →** clean-lap gate on the live path first (it is the highest-value single
  line — §8.3 says so and C3 shows the off-track data is already computed), then
  EWMA for reporting, then CUSUM for acting, with reset-on-signal and at stops.
- **D5 →** persistence, dwell, and two-sided `θ_in`/`θ_out`. Encode §6.2's 21:1
  asymmetry: far more evidence to *extend* a stint than to shorten one.
- **E1 →** stop `adopt` destroying compounds and fuel; log non-changes as
  `DecisionRecord`s. The `Replan(NONE, …)` path already computes the payload.
- **E3 →** freeze estimators in `PIT_LANE`/`OUT_LAP`; add `TELEMETRY_LOST`
  properly (0-C is the stopgap).
- **C3 →** off-track laps out of the practice clean-lap gate too.

**Verification:** §10's thrash regression test —
`plan_changes_per_race ≤ N` and `min_laps_between_changes ≥ D` on a golden race.
The design is right that nobody writes this test and it is the one that keeps
§8.4 honest.

---

## Stage 3 — Judgement calls, in this order *(after Stage 2)*

1. **C1's export fix** — subtract `k_f·Δm_fuel` before the lap-time degradation
   fit, and label it. Small, and it improves what the external tool receives
   immediately. Blocked only on M1.
2. **A6 / M3** — put the fuel map in the objective and replace the hardcoded
   `"Map 3"` string. Then §8.7's corner-count advice becomes buildable.
3. **A5** — make fill quantity a decision variable.
4. **D6** — contingency cards, minus the caution card (pushback 6). `FORCED_STOP`
   and `TELEMETRY_LOST` are the two with real triggers today.
5. **B3/B4** — driver-declared wetness, then §7's optimal-stopping crossover.
6. **D7** — scenario sampling, CRN, CVaR. **Last, and only after M2 has returned
   real degradation slopes with real sample sizes.** Before that it is an
   interval around a guess (pushback 3).

---

## Effort and verification

| Stage | Rough effort | Verification that proves it done |
|---|---|---|
| 0 | 1 day | No approvable infeasible plan on the live DB; property test on fuel figures; determinism fixture green |
| M | ~1 hr driving + 1 day analysis (M0, M1); M2 is a practice programme | Measured constants stored per event with provenance; `[ASSUMED]` markers visible where a fallback is in use |
| 1 | 2–3 days | Golden-fixture diff, every moved number attributable to a measurement |
| 2 | ~1 week | Thrash regression; feasibility invariant (no recommendation with `deadline < issue_time`); freshness invariant |
| 3 | Several weeks, each item independently shippable | Per item; D7 needs §10's analytic oracles — DP vs `n* = √(2T_p/d)`, and Monte Carlo collapsing onto the deterministic result at σ_ε = 0 |

## Wire, delete, or leave

| Module / symbol | Recommendation |
|---|---|
| `pitcrew/telemetry/pit_state.py` | **Wire**, at Stage 1 — A3's per-stop refuel measurement needs graded stop detection, and D3's tyres-only-stop hole needs it too. It was written for this |
| `FUEL_MAP_CONSUMPTION` / `FUEL_MAP_POWER` | **Leave, at Stage 3-2.** Delete only if M3 is abandoned |
| `CompoundProfile.evidence_is_clean` | **Wire or delete now** (0-E). Its docstring asserts a ranking rule the code does not implement |
| `RaceInputs.starting_fuel_l` | **Delete.** Never set, never read, no planned consumer |
| `RaceInputs.fuel_weight_s_per_l_per_lap`, `pit_dead_time_s`, `wear_measured_at_race_multiplier` | **Wire** at Stage 1 |
| `pitcrew/ui/preview.py` | **Leave.** Developer screenshot tool, run as `python -m`, correctly unimported |
| `.claude/worktrees/pensive-banach-78f43f/` | **Delete the worktree.** A full copy of the deleted 200k-line app, pollutes every repo-wide grep |

## The single most valuable next action

**M0** — one recorded race-length run with three scripted stops. It settles the
refuel rate (which currently decides the stop count on its own), serial-vs-
parallel, the pit-lane delta, and the G17 position question, from **one telemetry
file**. Every code change in Stage 1 is blocked on it, and it costs half an hour
in the car.
