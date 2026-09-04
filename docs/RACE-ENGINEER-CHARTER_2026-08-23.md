# The Race Engineer — charter, gap analysis and build order

**Written 23 Aug 2026** from the driver's specification of the same date.
Companion to `CLAUDE.md` (the app contract) and `.claude/skills/gt7-brain/SKILL.md`
(the engineering doctrine). **This document is the standard for the engineer
role; it does not change the export contract or the capture rules.**

---

## 0. The standard

> *"The engineer should increasingly identify what you are going to need before
> you can clearly describe it yourself. It should still ask you questions, but
> only where your perception provides information telemetry cannot reliably
> answer."*

**The one-line test for any engineer output:** *could this have been said without
looking at the data?* If yes, it is not engineering.

**The loop the spec asks for**, and it is the right one:

```
  Predict  →  Verify  →  Refine          not          Guess → test → fix
```

---

## 1. Verdict on all twenty sections

**Scored against what is actually in `data/pitcrew.db` and the codebase today**,
not against intent. Row counts are real.

| § | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Driver Engineering Model | 🟡 **PROSE ONLY** | `01-driver-profile-leon.md`, `driver.md`, `08-playbook-leon.md`. Rich, sourced, actively maintained — but not structured, not queryable, not per car×track |
| 2 | Driver × Car × Track × Conditions × Discipline | 🟢 **LARGELY BUILT** | `grip_observations` 2,201 rows keyed on `car_key`+`circuit_key`+`compound`+`stint_key`+`lap_in_stint`; `tyre_models` 48 fitted models on the same keys. **The car×track half exists in data. The driver-preference half is prose.** |
| 3 | Telemetry: braking / entry / mid / exit | 🟡 **DATA YES, ANALYSIS PARTIAL** | 41 channels at 60 Hz in `lap_frames`. `analysis/corners.py` extracts per-corner metrics. **But see §2 below — the per-corner comparison the spec assumes is bounded by measured noise.** |
| 4 | Video as a second telemetry system | 🔴 **BARELY STARTED** | `sessions.video_path` / `video_started_at` exist; `tools/read_hud_wear.py` reads the HUD wear gauge to 0.5%; one manual study (`docs/VIDEO_VS_DATA_2026-08-17_WATKINS.md`). **No automated visual analysis, and the NPU cannot host one** (Core Ultra 5 125U, ~11 TOPS) |
| 5 | Symptom vs cause | 🟢 **DOCTRINE EXISTS** | `02` §10.3–10.11 are cause-ranked tables, not slider lookups. Used correctly today: the mid-corner push was traced to `lsd_a` from 17,421 frames rather than to the front ARB |
| 6 | Targeted questions, not "how does it feel" | 🟡 **DOCTRINE YES, INTERFACE NO** | Added to `SKILL.md` 23 Aug. **But the app still presents a 13-field blank form and three of those fields are now resolvable from data** — designed out in `docs/INTERACTION-DESIGN_2026-08-23.md` |
| 7 | Driver feedback is evidence, not instruction | 🟢 **SHARPENS AN EXISTING RULE** | `CLAUDE.md` rule 1 says the report is primary evidence. The spec adds: *a hypothesis about a cause is not a work order.* No conflict — adopt |
| 8 | Every change is an experiment | 🔴 **TABLE EXISTS, ZERO ROWS** | **`setup_changes` has 0 rows.** Schema is `session_id, from_lap, key, from_value, to_value`. **This is the single biggest gap in the system** |
| 9 | Recognise a regression | 🟡 **PARTIAL** | `race_revisions` 74 rows with `reason`/`accepted` — closed-loop for *strategy*. Nothing equivalent for *setup*, because §8 is empty. Doctrine "MISSING ≠ REGRESSION" already stands |
| 10 | Setup history as accumulated knowledge | 🔴 **BLOCKED BY §8** | 13 sheets stored with values and gears. **No link from a sheet to what it changed, why, or whether it worked** |
| 11 | Qualifying is its own discipline | 🟡 **PARTIAL** | Sheets carry `purpose: qualifying`; `race/qualifying.py` exists. **No qualifying execution plan** (out-lap, tyre prep, gap creation, sector targets) |
| 12 | Race setup ≠ slower quali setup | 🟢 **DOCTRINE EXISTS** | `04-race-vs-qualifying.md`. Applied today: rear wing held against a fuel argument because spins cost more than drag |
| 13 | Strategy from *your* pace | 🟢 **BUILT** | `strategy/model.py` + `CompoundProfile` carries `pace_delta_s`, `wear_per_lap`, `source`, `laps_measured`, `longest_stint_laps`. Refuses to plan past its evidence |
| 14 | Car limitation vs driver opportunity vs interaction | 🟡 **DONE BY HAND** | The Yas post-mortem separated 32.6 s of spins from setup and called the step-down a driver effect. **Not automated** |
| 15 | Corner-specific coaching | ⛔ **REFUTED AS WRITTEN** | See §2 below. The specific examples in the spec are the ones his own data says cannot be said |
| 16 | Anticipate problems | 🟡 **THE RIGHT FORM, PARTLY REACHABLE** | The spec's own examples are *trends over laps*, which is exactly the form that survives §2. `grip_observations` + `tyre_models` are the substrate |
| 17 | Confidence always visible | 🟢 **BUILT AND ENFORCED** | `tyre_models.confidence` / `.speakable` / `.unknowns_json`; every setup sheet carries a confidence table; `CLAUDE.md` rule 5 |
| 18 | Ask the driver to test something | 🟢 **DOCTRINE EXISTS** | "One change per run, three clean laps." Used today |
| 19 | Decision hierarchy | 🟡 **ADOPT WITH ONE CORRECTION** | See §3 below — the spec ranks telemetry above driver feedback; `CLAUDE.md` rule 1 ranks it the other way |
| 20 | Career-long memory | 🟡 **SPLIT ACROSS THREE STORES** | `brain/` (prose), `data/pitcrew.db` (measurements), and Claude's memory directory. **No single index, and they drift** — `brain/RECONCILIATION.md` exists because of it |

**Score: 7 built, 9 partial, 3 missing, 1 refuted.** The spec is closer to
reality than it probably feels — but the three missing pieces are load-bearing.

---

## 2. ⛔ §15 is refuted by the driver's own data, and it must be rewritten

**This is the most important finding in this analysis.** The spec asks for:

> *"T1: Brake timing is good. Release 5-10% earlier…"*
> *"T6: Throttle reaches 60% too quickly… Hold 45-50% approximately 0.15 s longer."*

**Measured 22 Aug 2026 against all 307 clean laps on disk** (Monza 201, Watkins
72, Yas 34), noise taken from consecutive-lap differences within a run so a
stint's own drift is not counted as noise:

| Channel | 2σ noise floor | Verdict |
|---|---|---|
| Lap time | **1.66 %** of a lap | the quietest instrument available |
| Corner time | **4–6 %** of a corner | **3–4× noisier than the whole lap, in relative terms** |
| `brake_point_m` | **14–37 m** median, worst corner **142 m** | *"move your marker back 10 m"* cannot be said at any corner on any circuit on file |
| `throttle_on_pct` | **11–51 percentage points** | hopeless |
| `min_kph` | 9–11 km/h median (best corners 4–6) | **the only survivor — and only as a multi-lap trend** |

Two artefacts were ruled out before concluding: a lap-length sanity gate
(removed 8–12% of laps, improved Monza min-speed 2σ from 24.8 to 14.8 — nowhere
near enough) and distance-axis normalisation (barely moved it). **The residual
is real.**

**More measurements per lap does not beat a longer measurement.** Roughly a
third of corners carry any usable signal at all.

### What survives, and it is not nothing

**§15 rewritten to what the data supports:**

- ✅ **Multi-lap trends in `min_kph`** at the third of corners that carry signal.
- ✅ **Whole-lap and sector comparisons**, which sit below the noise floor.
- ✅ **§16's anticipation, unchanged** — *"your correction rate has increased over
  the last four laps"* is a trend, which is exactly the surviving form. **The
  spec's §16 examples are sound; its §15 examples are not.**
- ✅ **Car-limitation findings**, which pool across laps rather than comparing
  them: *"the front saturates on every lap where entry speed and line are
  correct"* is a distribution claim and is safe.
- ⛔ **Per-lap, per-corner input coaching in any channel.**

> **And when the engineer is silent about a corner it must say so.** The
> standing rule from the lap-time degradation work applies here too: *silence
> means I cannot see it*, not *nothing is happening*.

---

## 3. §19's decision hierarchy — adopt, with one correction

The spec ranks **telemetry (4) above video (5) above driver feedback (7)**.
`CLAUDE.md` standing rule 1 ranks the driver's report as *primary evidence* with
telemetry as corroboration, and the same rule is why `brain/RECONCILIATION.md`
records that the one time telemetry overrode the driver it cost 5 mm of ride
height and 2 mm of rake for nothing.

**These are reconcilable and the spec's own §7 does it:**

- **On what the car did** — telemetry leads. It is the better instrument and the
  driver should not be asked to report what a channel already measures.
- **On what the driver experienced** — the driver leads, absolutely. No channel
  carries confidence, hesitation, workload or feel.
- **Where they disagree, the disagreement is the finding** and is never averaged.

**A worked example from today**, which is why this matters: the Yas post-mortem
read a front-locking finding off telemetry and built a diagnosis on it, not
knowing the driver had dialled in `bb −1` himself. **The telemetry was correct
and the conclusion was wrong, because the car was not the car on the sheet.**

**Corrected hierarchy — one insertion:**

```
  0.  What is ACTUALLY IN THE CAR        ← new, and it is rank zero
  1.  Safety / major instability
  2.  Driver confidence
  3.  Vehicle behaviour
  4.  Telemetry evidence          ← leads on what happened
  5.  Video evidence
  6.  Historical Driver x Car x Track knowledge
  7.  Driver feedback             ← leads on what was experienced
  8.  Setup hypothesis
  9.  Controlled change
 10.  Outcome measurement
 11.  Learning
```

---

## 4. Three preconditions that block everything above

**None of §8, §9, §10 or §20 can work until these are fixed. They are not
features; they are the floor.**

### 4.1 🔴 The setup record is wrong, and it has been for five consecutive sessions

| Session | What was wrong | How it was caught |
|---|---|---|
| 13 Aug | `ballastPosition` 20 against an actual 0 | driver asked |
| 13 Aug | compound recorded RM, RS actually run | driver mentioned in passing |
| 16 Aug | `setup.values` reported the v1 sheet against a Rev B car — 5 values and 6 ratios | the gearbox channel contradicted it |
| 17 Aug | sheet "race v1" against Rev C values | driver asked directly |
| **23 Aug** | **session 71 tagged `setup_sheet_id 18` — the *Yas Marina* sheet, at Road Atlanta.** Brake balance `−1` in the car against `0` on every sheet on file | driver mentioned it in passing |

**An experiment log whose "before" is wrong is worse than no log**, because it
converts a wrong premise into permanent learning. **Fix this first.**

Two known mechanisms: the paste block cannot carry `performance` or `shiftRpm`
(by design — the parser reads `sheetName`, `values`, `gears` and nothing else),
and nothing reconciles the fitted sheet against the car actually on track.
`gearing.matchesSheet` is the one available ground truth and it is emitted as
`null` when it should be `false`.

### 4.2 🔴 `lap_distance_m` is unreliable on 8–12% of laps

It does not exist in the packet — `telemetry/recorder.py` integrates it from
speed. Measured at Monza against a true 5,793 m: **median 5,747 m, but the range
is 203 m to 11,187 m**, sd within a run **620 m — over 10% of a lap.** Laps that
swallow a missed crossing integrate to roughly two laps; fragments to a few
hundred metres.

**Everything corner-indexed inherits this**, including the corner aggregates in
the export. It is also half of why §2's noise floor is where it is.

### 4.3 🟡 `setup_changes` is empty

The table is already the right shape. **Nothing writes to it.** Until it does,
§8, §9 and §10 are aspirations and every revision re-derives what the last one
learned.

---

## 5. Build order

**Ranked by what unblocks the most, not by what is most interesting.**

| # | Work | Unblocks | Size |
|---|---|---|---|
| 1 | **Setup-record integrity** — emit `matchesSheet: false`, tag `setup.values` as `sheet-record` not `measured`, reconcile fitted sheet against the car, and capture brake balance and ballast where the driver actually has them | §8 §9 §10 §20 — **everything** | S |
| 2 | **Write `setup_changes`** — every value delta with its session, lap, hypothesis and expected result | §8 §9 §10 | S |
| 3 | **Outcome binding** — join a change to the laps that followed it and to the driver's verdict; `wear_predictions` already models predicted-vs-answered and is the pattern to copy | §9 regression detection | M |
| 4 | **Repair `lap_distance_m`** — anchor on crossings rather than integrating blind, and null the laps that cannot be trusted rather than exporting them | §3 corner analysis, export correctness | M |
| 5 | **Structure the driver model** — promote the prose in `01`/`driver.md` into records keyed Driver × Car × Track × Discipline, seeded from `grip_observations` | §1 §2 §20 | M |
| 6 | **Trend detection over `grip_observations`** — the §16 anticipation layer, built only on channels that clear §2's floor | §16 | M |
| 7 | **One index over three stores** — `brain/` prose, `pitcrew.db` measurement, Claude memory. `RECONCILIATION.md` exists because they drift | §20 | M |
| 8 | **Qualifying execution plan** | §11 | S |
| 9 | **Video analysis** | §4 | L — and it needs hardware that does not exist here |

**Items 1 and 2 are small, and they are worth more than everything below them.**

> **The implementation plan is `docs/ENGINEER-BRAIN-IMPLEMENTATION_2026-08-23.md`** —
> root causes, file-level changes and a definition of done for each. It carries
> one finding that belongs here too: **the five-session setup-record failure has a
> single root cause.** `controller.py:1822` calls `sheet_for(car_name, intent)`,
> which **has no circuit key** — so a session at Road Atlanta bound itself to a
> Yas Marina sheet because that was the only race sheet on file for the car. The
> same null table silenced the shift beep. It is one key.

---

## 6. What does not change

- `EXPORT-CONTRACT.md` and the export vocabulary.
- `CLAUDE.md` §3 — the four facts about the feed. **There is still no tyre wear
  channel and no track ID**, so §13's degradation curves stay gauge-corroborated
  and modelled, never presented as measured.
- **Lap time confirms degradation and can never warn of it** — σ 0.918 s puts the
  floor at 1.74 s/lap, above the entire 0.5–1.5 s/lap band. Any "expected
  degradation curve" in §13 is a wear model, not a lap-time observation.
- **Fuel map 1, always.** §12's list includes "fuel-map behaviour"; for this
  driver it is not a lever. His levers are short-shift → lift-and-coast →
  slipstream, and even that reverses when refuelling is fast — measured tonight.
- **One change per run, three clean laps**, and every measurement carries its
  date and game version.

---

*Written 23 Aug 2026 · GT7 v1.71 · from the driver's specification of the same date*
*Seven of twenty sections are built, nine partial, three missing, one refuted.*
*The refuted one is §15, and it is refuted by 307 of his own laps.*
*The three preconditions in §4 are worth more than any feature above them.*
