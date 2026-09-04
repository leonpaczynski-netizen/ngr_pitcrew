# Engineering brain — implementation plan

**Written 23 Aug 2026.** Turns the ranked build order in
`RACE-ENGINEER-CHARTER_2026-08-23.md` into work with root causes, file-level
changes and a definition of done that is a *measurement* rather than an opinion.

**Nothing here is a new subsystem.** Every item below is a defect, a missing
writer, or a key that is wrong — the read paths mostly already exist.

---

# Phase 0 — Integrity. Nothing above this is worth building until it is done.

## 0.1 🔴 ROOT CAUSE FOUND: the sheet lookup ignores the circuit

**This is why the setup record has been wrong in five consecutive sessions, and
it is one line.**

`pitcrew/controller.py:1822`:

```python
sheet = self.store.sheet_for(event["car_name"] or "", intent)
```

**`sheet_for` keys on car name and intent. It does not know what circuit you are
at.** The Shelby has four sheets on file, all of them Yas Marina. Opening a
practice session at **Road Atlanta** therefore bound session 71 to sheet 18,
*"Yas Marina race Rev C"* — a different circuit's gearbox, ride height and diff —
and the app then reported that as the setup as run.

The surrounding comment is careful and correct about the *intent* half of the
problem, and explicitly says *"missing is null, never a substitute: a
`setup_sheet_id` that names a sheet he was not running is worse than one that
names none."* **The circuit half was simply never in the key.**

**It also silenced the shift beep**, because the beep reads its per-gear table
off the fitted sheet and sheet 18's `shift_rpm_json` is `{}` — logged verbatim at
`09:51:25` and again at `10:22:06`.

**Change:**

- Add `circuit_key` to `setup_sheets` and to `sheet_for(car, circuit, intent)`.
  A sheet is a property of the car **and the circuit** — the gearbox alone proves
  it, and `tools/migrate_shift_points.py` already states the principle:
  *"a shift point is a property of the gearbox, not of the car."*
- **The one-sheet fallback must not cross circuits.** Falling back to a single
  sheet for the car is right within a circuit and wrong across one.
- Backfill `circuit_key` on the 13 existing sheets from their names and the
  sessions that used them. Sheets whose circuit cannot be established get null
  and are excluded from auto-binding rather than guessed.

**Done when:** opening a session at a circuit with no sheet for that car records
`setup_sheet_id = NULL` and shows the status line — verified by opening a session
at a fourth circuit and asserting the null. **And session 71's binding is
repaired via `identity_repairs`, not by rewriting the row silently.**

## 0.2 🔴 The feed can verify exactly one setup value, so stop trying to measure the rest

`analysis/gearing.py:78` `matches_sheet()` compares fitted ratios against the
sheet, and `MATCHES_SHEET_COVERS` already declares its scope. **That scope is the
gearbox and nothing else** — GT7 broadcasts no ride height setting, no diff, no
brake balance, no ballast. Twenty-one of the twenty-three values have **no ground
truth in the feed at all.**

**Consequence, and it is a design decision rather than a defect:** setup-record
integrity cannot be solved with more telemetry. It has to be solved with
**provenance and confirmation**.

**Change:**

1. **Tag `setup.values` with `provenance: "sheet-record"`**, distinct from
   `gearing.fittedRatios` which is `measured`. Raised in the Rev C post-mortem on
   16 Aug and still open. One field, and it stops the export presenting a typed
   record and a read channel with identical authority.
2. **Emit `matchesSheet: false` when it is false.** It returned `null` at Yas
   when the gearbox was provably Rev B — investigate whether `fitted_ratios()`
   returned empty for that session and fix the null-vs-false path.
3. **Capture the trims the driver actually makes.** Brake balance and TCS are
   MFD-adjustable mid-race and are the two values most likely to differ from the
   sheet — `bb −1` and then `−2` tonight, against `0` on every sheet on file.
   They are not in the feed, so they must be *asked*: a one-line confirmation at
   session start and a PTT intent (`"brake balance minus two"`) during the run,
   written to `setup_changes`.

**Done when:** an export for a session where the car differs from the sheet says
so in the payload, and a race where brake balance was trimmed has those trims in
`setup_changes` with their lap numbers.

## 0.3 🔴 Nothing writes `setup_changes` — and both ends are already built

```
  pitcrew/store/db.py:538   add_setup_change(session_id, change)      EXISTS
  pitcrew/store/db.py:548   list_setup_changes(session_id)            EXISTS
  pitcrew/export/build.py:595                    consumes it          EXISTS
  pitcrew/prompts/context.py:346  -> driver_changes                   EXISTS
  callers of add_setup_change in production:                          NONE
```

**Every caller is a test.** The table has 0 rows after 72 sessions.

**Change — three writers, all small:**

| Writer | Trigger | Source of the delta |
|---|---|---|
| **Sheet diff** | a sheet is pasted or edited | diff `values_json` against the previous sheet for that car+circuit |
| **In-car trim** | PTT intent, or the session-start confirmation | driver report, `from_lap` = current lap |
| **Between-run** | a new sheet is fitted mid-session | same diff, `from_lap` = the lap it took effect |

**Done when:** tonight's race, replayed through the loop, yields
`lsd_i 5→0`, `lsd_b 22→26→34`, `de_r 34→32`, `arb_f 5→4`, `lsd_a 17→14` and
`bb 0→−1→−2` as rows with lap numbers.

## 0.4 🟡 `lap_distance_m` is integrated blind

Not in the packet — `telemetry/recorder.py` integrates it from speed. At Monza
(true 5,793 m) the range is **203 m to 11,187 m**, sd within a run **620 m**.
Laps that swallow a missed crossing integrate to roughly two laps.

**Change:** anchor on lap crossings — scale each lap's integrated distance to the
circuit's known length, and where the integration disagrees with the crossing by
more than a threshold, **null the channel for that lap rather than exporting it.**
Missing is null, never a plausible-looking number.

**Done when:** the Monza distribution's sd within a run falls below 2% of lap
length, and the laps that cannot be rescued export `lap_distance_m: null` — with
the count of nulled laps reported rather than silently absorbed.

---

# Phase 1 — The experiment loop

**Only reachable once Phase 0 is done, because an experiment log with a wrong
"before" converts a wrong premise into permanent learning.**

## 1.1 Extend `setup_changes` into an experiment record

Current columns are `session_id, from_lap, key, from_value, to_value, created_at`
— a *delta*, not an experiment. Charter §8 needs the reasoning and the result.

**Add:** `experiment_id` (groups values changed together as one change), plus an
`experiments` table carrying `problem`, `hypothesis`, `expected_result`,
`verdict` (`improved` | `neutral` | `worse` | `unread`), `evidence_json`,
`driver_verdict`, `closed_at`.

**One change per run is a doctrine, not a schema constraint** — the schema must
represent tonight honestly, where five values moved as three separate arguments.

## 1.2 Outcome binding

`wear_predictions` already models exactly this shape — `predicted_*` beside
`answer_*`, with `rate_source`, `rate_confidence`, `rate_samples`. **Copy that
pattern rather than inventing one.**

Bind an experiment to the laps after `from_lap`, pull the same measures from
`grip_observations`, and record the verdict **with the driver's own words
alongside it**. Where they disagree, store both — the disagreement is the finding
and must never be averaged.

## 1.3 Regression detection

With 1.1 and 1.2, `worse` becomes queryable. The rule already exists as doctrine
(*"MISSING ≠ REGRESSION"*) and now gets a mechanism: **a direction that produced
`worse` for this driver, car and circuit is never re-proposed without saying that
it failed before, and when.**

**Done when:** the engineer can answer *"has this been tried, and what happened?"*
for any parameter, from the database, in one query.

---

# Phase 2 — Structure the driver model

The prose in `01-driver-profile-leon.md`, `driver.md` and `08-playbook-leon.md` is
rich and sourced. It is not queryable and it is not per car × track.

**The car × track half already exists in data** — `grip_observations` has 2,201
rows keyed on `car_key`, `circuit_key`, `compound`, `stint_key`, `lap_in_stint`;
`tyre_models` has 48 fitted models on the same keys with `confidence`,
`speakable`, `unknowns_json` and `game_version`.

**Change:** a `driver_preferences` table on the same key vocabulary, each row
carrying its evidence, its source (`driver-stated` | `derived` | `inferred`), its
date and its game version. Seeded from the prose, then updated only by Phase 1
outcomes.

## 2.1 ⭐ The first metric: car affinity — *which cars does he go well in?*

**Asked for by the driver, 23 Aug 2026:** *"It's about knowing which cars I like
and which I don't and struggle with."* **It is measurable today from data
already on disk, and the answer is not what a pooled driver profile would say.**

Four components, all per **car × circuit × race**, all normalised so circuits
compare:

| Component | Definition | Why |
|---|---|---|
| **Relative consistency** | σ of clean race laps ÷ median lap, as % | absolute σ is meaningless across a 81 s and a 145 s lap |
| **Recovery** | after the first incident, does any later clean lap come within 1.0 s of the pre-incident best? Plus the median step in seconds | **the most diagnostic single number** — see below |
| **Trajectory** | does the best clean lap fall in the first or last third of the race? | late = confidence building through the stint; early = falling away from it |
| **Incident rate** | incidents ÷ racing laps, weighting spins above off-tracks | off-track severity varies by circuit; a spin does not |

**Measured, all races on file with five or more clean laps:**

| Session | Car | Circuit | clean | σ | **σ%** | best@ | **step** | recovers |
|---|---|---|---:|---:|---:|---|---:|---|
| 49 | Huracán GT3 | Watkins Glen | 7 | 0.76 | **0.73 %** | early | n/a | n/a |
| 52 | 911 RSR | Monza | 5 | 0.93 | **0.85 %** | early | n/a | n/a |
| **58** | **911 RSR** | **Monza** | **18** | **1.06** | **0.96 %** | **late** | **−0.07 s** | **YES** |
| 53 | 911 RSR | Monza | 8 | 1.70 | 1.56 % | late | −3.08 s | YES |
| 44 | Shelby GT350R | Yas Marina | 10 | 4.58 | **3.82 %** | early | **+3.43 s** | **NO** |

**Session 58 is the reference case for what "a car he goes well in" looks like:**
18 clean laps at 0.96%, the lowest incident rate on file, **his fastest lap of
the race on lap 20 on twenty-lap-old tyres**, and after a minor off at lap 3 the
step was −0.07 s with **16 of the next 17 laps inside a second of his
pre-incident best.**

**Session 44 is the opposite and it is the only one on file:** four times worse
relatively, best lap on lap 3, +3.43 s step, and **not one lap afterwards came
within a second of it.**

> ⚠️ **The confound, and it must be stated on the record.** The Shelby has been
> raced only at Yas Marina, so car and circuit cannot be separated from race data
> alone. **Road Atlanta is the first separation** and it points at the circuit or
> the setup rather than the car: four clean practice laps at **1.42%**, and the
> two best 0.079 s apart. **This is exactly why the model must be keyed
> car × circuit and never car alone.**

**Done when:** the engineer can answer *"how do I go in this car, here?"* with
these four numbers before a session opens, and flags a car × circuit whose
recovery figure is `NO` as needing a different plan — more margin early, and a
reset protocol rather than a push.

**The point is per-context learning**, exactly as the charter asks: *"Leon
historically likes rotation, but in this Porsche at Watkins Glen his fastest laps
come with slightly more rear stability"* is a far more useful record than *"Leon
likes oversteer."*

**Done when:** the sheet generator reads the working window from the database
instead of from a document, and a preference that was never true for a given
car × circuit cannot be applied to it.

---

# Phase 3 — Anticipation

Charter §16. **Built only on channels that clear the measured noise floor** —
whole-lap and sector measures, pooled distributions, and multi-lap `min_kph`
trends at the third of corners that carry signal. `grip_observations` is the
substrate and `tyre_models.speakable` is the precedent for the gate.

**And it must say when it is silent.** *"Silence means I cannot see it"*, never
silence that reads as *"nothing is happening."*

---

# Phase 4 — One index over three stores

`brain/` (prose), `data/pitcrew.db` (measurement) and Claude's memory directory
hold overlapping claims and drift apart — `brain/RECONCILIATION.md` exists
because of it. One index, with each claim's home and its date, so a stale figure
is visible rather than merely wrong.

---

# Sequencing

```
  0.1  sheet binding keyed on circuit          S   <- unblocks everything, one key
  0.3  three writers for setup_changes         S   <- both ends already exist
  0.2  provenance, matchesSheet, trim capture  S
  1.1  experiment schema                       S
  1.2  outcome binding                         M
  0.4  lap_distance_m repair                   M   <- can run in parallel
  1.3  regression detection                    S
  2    structured driver model                 M
  3    anticipation                            M
  4    one index                               M
```

**The first four are all small and they are the whole foundation.** Everything
the charter asks for above them is unreachable until a change, its reason and its
outcome can be written down against a setup record that is actually right.

---

*Written 23 Aug 2026 · GT7 v1.71*
*Root cause of the five-session setup-record failure: `sheet_for(car, intent)` has no circuit key.*
*`add_setup_change` has existed since the rebuild and has never once been called outside a test.*
*The feed can verify the gearbox and nothing else — the other 21 values need provenance, not telemetry.*
