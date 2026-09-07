# George and Ludo — assessment against the job, and the plan to get there

**Written 6 Sep 2026, the night of Deep Forest Round 6. Revision 3, after two
critic passes.** Read-only investigation of the live engineer (George:
`pitcrew/race/*`, `pitcrew/controller.py`), the garage engineer (Ludo:
`.claude/skills/ludo/`, `brain/`), the seam between them, tonight's race log and
database, the league hub, and external practice. Every code claim carries
`file:line`; the load-bearing ones were re-verified by hand and again by the critic.
Corrections from the critic are folded in and marked ⟂.

Companion to `RACE-ENGINEER-CHARTER_2026-08-23.md` (the standard),
`ENGINEER-TARGET-STATE_2026-08-29.md` (the architecture),
`LUDO-AUDIT_2026-09-04.md` (the last audit) and
`research/race-engineering-practice_2026-09-06.md` (how real teams do it).
Nothing here overrides `CLAUDE.md` or `EXPORT-CONTRACT.md`.

---

## 0. The answer in nine lines

1. ⟂ **The next race is tomorrow, not next Sunday.** GR3 Season 1 Round 6, Daytona,
   7 Sep 10:30 UTC, sign-in CONFIRMED on the hub. Event 10 in the app: 20 laps,
   one mandatory stop, fuel ×3, tyre ×2, refuel 1.0 L/s *declared*, pit loss 20 s
   *declared*, strategy 17 approved **with no playbook**, no knowledge row for
   Daytona, no shift table for the Huracán at Daytona in `shift_points`. Then four
   series and five more races in the following 19 days. §6 opens with what has to
   happen tonight.
2. **Tonight's P2 was lost in code, not in the car.** The fill is recomputed with
   the hose in, but the recompute can only *raise* the plan's stint length, never
   lower it (`race/calls.py:1467-1474`). 76 L called, 55–63 needed, 19.7 L crossed
   the line = 9.9 s standing against an 8 s gap. **The same defect bites tomorrow
   if the stop lands late**: a 20-lap race with an 11+9 plan, stopped on lap 13,
   is filled for 9 laps when 7 remain.
3. **"No tyres" was never said.** Ludo wrote it into `race_knowledge.notes`; George
   reads four of that record's fields and `notes` is not one of them. The box call
   always names the plan's compound (`race/calls.py:1378`), and the tyre-change
   detector then recorded the fresh set as *not changed*
   (`telemetry/session_state.py:718`, `bool(None)`).
4. **George races the fuel tank, not the race.** No gap to the car ahead was spoken
   in the whole 7-lap chase for P2 while the pit wall read 154 gap frames; no
   undercut/overcut arithmetic exists on a live path; every rival stop ever
   watched died on a missing column.
5. **The plan channel is an unvalidated third door.** Strategy 27 (and 17,
   tomorrow's) went in through `write_strategy`, which stores the handover half
   unchecked and auto-approves if it certifies: no `Handover.validate()`, so a plan with no
   playbook arms on defaults and ⟂ a plan with a mistyped or forbidden action
   would arm too. The only two plans that ever carried a validated playbook came
   through the CLI.
6. **Ludo's method is discipline, not procedure.** The last two car-state files do
   instrument-floor-falsifier by hand; the skill's `refine` step does not require
   it, no ledger is opened first, the corner substrate has been dark since session
   88, and the two channels that cost the place tonight (lift-and-coast, hand
   short-shift) still have no reader.
7. **The record is in five stores; four are uncommitted**, and the memory index
   that carries lessons forward was over its load limit and only partly loaded
   this session. ⟂ Trimmed under the limit tonight (24,439 bytes against 25,000).
8. **The league already knows the rivals.** The hub holds every rival's qualifying
   and best race lap for all five Supercars rounds and every GR3 round. The app
   reads finishing position, quali position and the pole/fastest-lap flags — never
   the lap times. ⟂ Only three entrants (one of them the driver himself) carry a
   driving profile, so that field is not a dossier.
9. **What works, keep:** the refusal card, predictions with falsifiers, the settings
   screenshot as rank zero, K-based gearbox cutting, the strategy optimiser and
   certifier, the pit wall's *reading* (968 frames, 7 stops recognised), the
   trimmed-difference gap estimator, the hub calendar adoption, and George's
   fuel-to-stop arithmetic when the stop lands on plan.

---

## 1. The standard — what the two roles actually do

From practitioner sources; full brief with citations in
`research/race-engineering-practice_2026-09-06.md`. Only what transfers to one
driver, one sim, one league is kept.

### 1.1 The garage / performance engineer (Ludo)

| Practice | Form |
|---|---|
| **Run plan before every session** | per run: purpose, fuel, tyre, the one setup delta, lap type (install / push / long) |
| **Baseline → one change → A-B-A** | the return-to-A leg separates the change from track evolution and the driver learning; runs of 5–7 laps give 3–5 usable |
| **Changes big enough to feel, both directions** | a change inside the driver's resolution "can take you the wrong way" |
| **Driver debriefed first, immediately, per run** | on a track map, four phases per corner, 1–5 scale; data shown *after* |
| **Single version of events per session** | run-by-run, written the same day, into the database |
| **Parameter-effect database** | what each slider did, in percent of range, with the instrument that saw it |
| **Track book per circuit** | pit loss, refuel dead time, wear rate and knee, burn, rival habits, overtaking zones |
| **Race plan = stints + standing orders** | what the live engineer may decide alone, what needs the driver, what is forbidden |
| **Predicted vs actual scored after every race** | burn, wear, pit loss, stint length, each with who was right |
| **Recommends, never decides live** | the live role has authority; the garage role hands over and stands down |

### 1.2 The race engineer / strategist (George)

| Practice | Form |
|---|---|
| **Recompute every lap and every position change** | fuel to end, laps in hand to flag *and* to stop (named separately), deg vs expected, pit loss under current conditions |
| **Deviation is the product** | "degradation is higher than we expected" is the call, not the number |
| **Gap ahead/behind projected to pit exit** | who you rejoin behind; undercut value vs pit loss; overcut when the car staying out holds pace |
| **Rivals get equal effort** | stint length so far, stop lap, pace vs tyre age, can they make the end |
| **The stop is re-sized at the stop** | laps remaining × burn − aboard, read back; a moved stop lap means a moved fill |
| **Pre-programmed branches** | incident, missed stop, fuel short/long — decided before the race, executed instantly |
| **One voice, on straights, instruction then short reason** | "box this lap", "li-co", suffix marks *suggestion* vs *instruction*; confirmation word |
| **Driver override accepted without argument, re-plan from it** | the driver is the early-warning instrument |
| **Every call logged with inputs and confidence** | for the audit |

### 1.3 What does not transfer, on evidence already on file

- Per-corner input coaching (refuted, charter §2).
- F1 undercut instincts (`CLAUDE.md` §5.4). ⟂ The "undercut is strong here" lines
  are in **our own** `brain/_inbox/05-track-reference.md` (Monza, Suzuka, RBR,
  Deep Forest entries), pre-1.49 and never re-flagged — that is a doctrine
  defect (L15), not a hub one.
- Fuel-map strategy (driver's standing refusal; the public map numbers are GT Sport
  era and void).
- Safety-car modelling: ⟂ confirmed no SC key anywhere in the hub's lobby settings,
  and GT7 broadcasts none.
- Lap time as a degradation warning (floor 1.74 s/lap above the whole band).

### 1.4 Where the pit wall stands against `CLAUDE.md` §8

§8 forbids building live leaderboards. The pit wall *reads GT7's own leaderboard
off the screen*, as the wear gauge reads GT7's own gauge; it composes nothing and
touches no game state. That is observation, which §8 permits. It is stated here so
the tension is on the record rather than discovered later. Two measured limits
travel with every rival-stop claim: only the top 8 are on screen, and a pitting car
drops below the cut, so the screen hides stops non-randomly.

---

## 2. George in isolation

### 2.1 Job

Brief the driver from the instruments actually armed; execute the plan; watch burn,
wear and pace for deviation; size the stop at the stop; decide tyres; know the
rivals' stops and the gaps; adapt to a missed stop, an incident, a rival's move; say
one thing at a time as an instruction with its reason; log every call for audit.

### 2.2 What it does — the score

Measured against tonight (session 138, 20 laps, one stop) and the code. Severity:
**CRIT** produced a wrong instruction in a real race or will again; **HIGH** wrong or
missing answer to a question an engineer must answer; **MED** built and unwired, or
right answer wrong label.

| # | Capability | State | Evidence | Sev |
|---|---|---|---|---|
| G1 | Fill sized at the stop from laps actually left | ✗ `after_stop = next_stint_laps`, raised to `remaining` only when larger — never lowered | `race/calls.py:1467-1474`; 76 L vs 55–63 | CRIT |
| G2 | Tyres yes/no as a decision and a word | ✗ no representation of "fuel only" in a plan stint or `strategy/handover.py:48-60`; call names plan compound; `notes` unread | `race/calls.py:1378`, knowledge id 8 | CRIT |
| G3 | Tyre change detected at the stop | ✗ needs a ≥5 °C four-corner drop in one frame; PIT_EXIT carries `bool(None)` → "not changed"; the gauge's own "fresh set" is not wired to the coordinator | `telemetry/session_state.py:612-622, 718`; ⟂ lap 13 `NULL`, lap 14 `0` | CRIT |
| G4 | Rival stops persisted and profiled | ✗ 0 rows ever; column in DDL, not in the live table, not in `ADDED_COLUMNS` | `store/schema.py:905-927`; 7 × OperationalError in the log | HIGH |
| G5 | Gap ahead / closing / target in a chase | ✗ read by the wall, never spoken in stint 2; `closing_call` fired once all day, wrongly (sim) | trace laps 14–20 | HIGH |
| G6 | Undercut / overcut / rejoin arithmetic | ✗ `race/ledger.py` undercut/overcut/cover_deadline exist; imported only by `rival_answers.py`, `rival_pace.py`, which nothing outside tests imports; `teammate.py` likewise | grep | HIGH |
| G7 | Rival stops move *our* stop | ✗ reach calls and the (broken) book, never the plan or the fill | `race/coordinator.py:742-802` | HIGH |
| G8 | Brief describes the armed instruments | ✗ reads `self._hud`, which is never assigned → "No tyre gauge" always; "can't see other cars" hard-coded | `controller.py:2263`, `race/brief.py:107,124` | MED |
| G9 | PTT "gap" | ✗ refuses while gaps are populated | `engineer/intents.py:497-505` vs `controller.py:2798-2808` | HIGH |
| G10 | Burn reflects the current stint | ✗ whole-race median; "6% under plan" spoken while stint 2 ran over | `race/expectations.py:226-272`, log 20:36:49 | HIGH |
| G11 | Sees his own fuel saving | ✗ only the app's beep flag; lift-and-coast and hand short-shift invisible; `short_shift_rpm` holds 717 zeros, 155 NULL, **0 measurements ever** | `controller.py:672-676` | HIGH |
| G12 | Timed-race lap count | ✗ 21 announced from `ceil(minutes / lap)` with no stop time; certifier marked it unchecked and armed; stint 1 of 11 drives 12 by construction (`stint_ends_on_lap = start+laps−1`, box fires at 11 *completed*) | `strategy/evidence.py:686-692`, `race/coordinator.py:422` | HIGH |
| G13 | One "laps remaining" expression | ✗ three (`race/calls.py:1432`, `race/replan.py:906`, `race/rival_calls.py:609`) | rule 12 | MED |
| G14 | One pit-loss policy | ✗ fill discount uses the declared 20 s; `_stop_costs_laps` (`race/coordinator.py:1218`) and the board refuse an unmeasured one; `events.pit_loss_source='measured'` has no writer | grep | MED |
| G15 | The D3 rail | ✗ gates nothing: `structural_action` is never set; the three shape-changing calls bypass it | `race/coordinator.py:1655-1684` | HIGH |
| G16 | Playbook adaptations | ✗ ran with `{}` tonight and will tomorrow | strategies 27, 17 | HIGH |
| G17 | Incident, damage, rain | ~ incident lap leaves the record, plan not re-costed. ⟂ **Damage and rain are on the HUD panel the gauge already captures** (car icon goes red; hygrometer left of the bars) and nothing reads them. Supercars, GR3 and Porsche run `damage: HEAVY`; Porsche, GR3 and Enduro run random weather | `race/coordinator.py:847-868`; memory `reference_gt7_wear_panel_geometry` | HIGH |
| G18 | Noise discipline | ✗ 9 position flaps, championship ×6 in 30 s mid-fight, duplicated fuel lines, haptics fault spoken on the out-lap, "Box now…" phrasing 3 laps early, "short-shift and lift" ×3 when a stop was unavoidable | trace | HIGH |
| G19 | Rule 13 | ✗ "Box this lap" from three kinds; "to the flag" two meanings | `race/calls.py:1368, 2020`, `engineer/intents.py:565` | MED |
| G20 | Gauge guard | ~ ⟂ the rule-10 reseed exists and fired 9× in the race; the defect is the **asymmetry** — a drop to zero on all corners is accepted instantly, a rise is refused 12 times, so ~25 s of series is discarded each cycle | `telemetry/hud.py:1778-1815` | MED |
| G21 | Gap trend | ✓ fixed in tree (trimmed adjacent-difference median); uncommitted | `race/gaps.py` | — |
| G22 | Driver board | ✓ instantiated and pushed at 4 Hz (memory said test-only: wrong); deque race fixed in tree, uncommitted | `controller.py:4823-4862` | — |
| G23 | OBS pre-flight | ~ fired falsely 5×; fix in tree, unverified live | `telemetry/hud_session.py` | MED |
| G24 | Position, field size, league projection | ✓ | `race/coordinator.py:933-955` | — |
| G25 | Fuel-to-stop arithmetic when the stop lands on plan | ✓ correct all race | trace laps 2–11 | — |
| G26 | ⟂ Lap-one and start type | ~ lap-one exclusion assumes a standing start; Porsche Cup and Enduro are rolling; `events.start_type` exists and is not consulted | `race/expectations.py:226` | MED |
| G27 | ⟂ Penalties / track limits | ✗ six laps served penalties unflagged at Daytona (memory); Supercars run `shortcutPenalty STRONG`; no detector | — | MED |

**The shape of the failure.** Most rows are *built and not wired* or *wired to the
wrong input*. George has most of the instruments a strategist needs and reads a
third of them.

---

## 3. Ludo in isolation

### 3.1 Job

Read every piece of data and the driver's report; develop the setup toward winning
and qualifying first, trading speed against tyre and fuel; author the run plan, the
race plan with its standing orders, the engineering sheet; debrief and score; carry
what was learned to the next round.

### 3.2 What it does — the score

| # | Capability | State | Evidence | Sev |
|---|---|---|---|---|
| L1 | Reads his own fuel behaviour (coast, hand short-shift) | ✗ no reader exists; done by hand once, after the race, after he said so | grep `pitcrew/analysis` "coast": 0 | CRIT |
| L2 | Race plan carries a playbook | ✗ strategies 27 and 17 have none; skill names no tool that writes one; `references/race-planner.md` shows no write call | `plan_json` keys | CRIT |
| L3 | "Single source" for wear | ✗ ⟂ `tyre_models`: 48 rows v1.70, **36 rows v1.71**, 82 of 84 unspeakable, read by nothing in `race/`; the multiplier lives in provenance JSON, not a column, so nothing can filter ×2 from ×8 | `SKILL.md:519-521` | HIGH as an instruction |
| L4 | Corner substrate | ✗ `grip_observations` last derived at session 88; no `corner_models` for Sardegna, Deep Forest or Suzuka; rung 3 of the ladder dark for 50 sessions | DB | HIGH |
| L5 | `refine` opens the ledger first | ✗ no such step; open items sit unsurfaced (Daytona `dc 20/20`, Shelby `lsd_a 17→24` since 26 Aug, QUALI's five predictions, `df_r 300`) | `SKILL.md:144-158` | HIGH |
| L6 | Instrument + floor + control required before a change | ✗ required only in `what to try` gate 1; `refine` step 4 says "with the prediction written down"; 5 Sep two "confirmations" died against a no-change control | `SKILL.md:153, 601-606` | HIGH |
| L7 | One clean-lap definition | ✗ `where_the_change_landed` refuses DF 133→134 (0 and 1 clean) while the car-state file says 4 and 5 and declares Rev B verified | `shelby-deep-forest.md:1606,1653` | HIGH |
| L8 | One change, three clean laps | ✗ ⟂ s107–110 and s112: 7 real changes each; s117: 3; s102 was one change plus a 16-key baseline declaration; n=2, 0, 1 clean at the last two events | `setup_changes` | HIGH |
| L9 | Platform vs trim | ✗ not in the skill (4 Sep rec. 4) | grep | MED |
| L10 | Per-car×circuit history with outcomes | ✗ history tables have no outcome column; outcomes in `RECONCILIATION` by letter and in 245 memory files | `shelby-deep-forest.md:1573-1581` | HIGH |
| L11 | George's calls audited in debrief | ✗ no step; `race_revisions` 336 rows, `accepted` on 1; `race/call_outcome.py` unnamed | `SKILL.md:193-205` | HIGH |
| L12 | Pit loss and refuel dead time measured per circuit | ✗ never, anywhere; 20.0 declared on every event; `race/refuel.py` measures and writes nothing | knowledge id 8 notes | HIGH |
| L13 | Quali as a discipline | ~ first well-formed quali doc at DF; nothing fed back; `write_qualifying_plan` never called; the hub holds rivals' quali laps (§5) and the memory holds a measured lever (best on flying lap 4, worth 1.2–1.6 s) | `practice_intent` unknown to skill | HIGH for "qualify first" |
| L14 | Speed vs wear vs fuel trade | ✗ no tool exposes wear- or fuel-vs-setting; only measured instances are prose | car-state files | MED |
| L15 | Doctrine tagged | ✗ `02` §10 5 tags on 123 rows; `05` zero 1.71 mentions, its DF entry wrong on 4 counts and its undercut lines pre-1.49; Shelby profile in `07` is stock spec, engineered prose is the Mustang; `11` contradicts `range_records` on 4 cells; `09` template 1.70 | files | HIGH |
| L16 | Stale instructions | ✗ `log_setup_change.py`, `check_setup_sheets.py` cited and deleted; `mechanic.md` paste-block/validate flow describes what §1a forbids; `write_shift_points` snippet not runnable as Python; eval 3 expects the deleted question gate | agent audit | MED |
| L17 | Tools that exist and the skill never names | ✗ `brake_bias.py`, `shortshift_trade.py`, `debrief.py`, `where_the_time_went.py`, `wear_rates.py`, `call_outcome.py`, `temps.py`, `tyre_split.py`, `refuel.py`, `pit_wall.py` — re-derived by hand | grep | MED |
| L18 | Record committed and under limit | ✗ two car-state files and three setup docs untracked; `RECONCILIATION` +70, `SKILL.md` +110 uncommitted; `MEMORY.md` was 42 KB against a 24 KB limit and partially loaded this session — ⟂ trimmed to 24,439 bytes tonight | git status | HIGH |
| L19 | Skill is a procedure | ~ 727 lines, ~40% incident narrative | count | MED |
| L20 | Evals | ✗ 11 in `evals/evals.json`, unchanged since 26 Aug; none for the nine documented failures | — | HIGH |
| L21 | ⟂ Multiplier discipline | ✗ Sardegna 16 Sep runs tyre ×8 and fuel ×3 and is tyre-bound; nothing in the skill or the tools filters evidence by multiplier or prompts the §5.2 calibration at the target multiplier | `CLAUDE.md` §5.2 | HIGH |
| L22 | ⟂ Multi-class and BoP | ✗ Enduro Fuji 26 Sep: 120 min, Gr.1/3/4, manufacturer roster, BoP (gearbox and power not settable); `initial` mode asks "is tuning open" and nothing else | memory Round 3 | MED |
| L23 | ⟂ Run plan per session | ✗ no artefact; runs are named after the fact in car-state files | — | MED |
| L24 | Predictions with falsifiers, scored | ✓ RSR Rev A–E, Shelby Rev B, DF Round-5 closure | files | — |
| L25 | Rank zero via screenshot; K-based gearbox; within-car instruments | ✓ | `shelby-deep-forest.md` 23/23 | — |

**The shape of the failure.** Ludo's best work is in the last two car-state files
and none of it is encoded: no ledger it must open, no step that demands the
instrument, no eval that reproduces a past failure.

---

## 4. The seam

| # | Channel | State | Defect |
|---|---|---|---|
| S1 | Plan → running app | ✗ Race screen refreshed only at event load and the two in-app approves; strategy 21 approved 14:29, sim armed 14:32 with `strategy_id NULL` | `controller.py:1389-1406, 3855` |
| S2 | Plan → playbook | ✗ ⟂ `write_strategy` stamps `expects`/`context` and stores the handover half unchecked — it never calls `Handover.validate()`; `playbook_of` (`strategy/handover.py:200-208`) reads whatever JSON is there, so a missing playbook arms on defaults and a bad one arms unchecked; the Strategy screen hides plans without one | `mcp/server.py:331-380`, `store/db.py:2138`, `controller.py:3676` |
| S3 | Rival book | ✗ 0 rows, schema drift; `briefing()` has no caller | `store/db.py:1442-1472` |
| S4 | Knowledge record | ~ George reads `pit_loss_s`, `refuel_l_per_s`, `wear_rates`, `calls_off` (never populated); `notes`, `rivals`, `undercut_s`, `overcut_s`, `tow_s_per_lap`, `expected_constraint`, `constraint_watch` read by nothing; briefing not in the export | `race/knowledge.py` consumers |
| S5 | Wear carry-forward | ✗ `analysis/wear_rates.carry_into_knowledge` has no caller; DF rate re-typed by hand | `wear_rates.py:153` |
| S6 | Compound on race laps | ✗ NULL without a plan (sessions 44, 118, 135); no gauge reads our own compound | `controller.py:3387-3426` |
| S7 | Pit loss / refuel measured → stored | ✗ `race/refuel.py` measures and writes nothing; `pit_loss_source='measured'` has no writer, so `_stop_costs_laps` never sees a measured value in production | grep |
| S8 | Live state → Ludo | ✗ gaps, rival pace, rival positions, pit-wall sightings, per-lap plan-vs-actual: not persisted | — |
| S9 | Journal | ~ `propose_strategy` journals nothing; MCP is used as Python imports, not registered (`mcpServers: {}`); `MCP-SEAM.md` documents the pre-29-Aug doctrine | `mcp/server.py:224-260` |
| S10 | Who was right | ✗ nowhere structured; `accepted` true on 1 of 336; `_disposition` computed at export and discarded | — |
| S11 | Second copies | ✗ `app_state.setting:beep_shift_points` holds 4 legacy per-car tables, `beep_rpm_source=manual` | §1a |
| S12 | Strategy screen | the only place the driver sees the playbook, unhandled triggers and certificate; the only source of `quali_minutes` | `ui/strategy_screen.py:245-400, 547-600` |
| S13 | Hub → rivals | ✗ `hub.results()` selects position, status, pole, fastest-lap flag, quali position and penalties; `RoundResult.bestLapMs/qualifyingLapMs` (202 rows), `EventQualifying` (111), `TrackProfile.raceIntelligence` (123) are never read | `hub/read.py:515-548` |
| S14 | ⟂ Hub freshness | ~ `Hub.stale` exists (3 days); no consumer refuses a rival claim on it | `hub/read.py:166` |

**One sentence.** Everything Ludo authors reaches George through a door that drops
half of it, and everything George measures leaves through no door at all.

---

## 5. Knowing our rivals — what is already available

Read-only query of the hub tonight, Supercars Series 1, all eight gaps ⟂ verified
to the millisecond:

| Round | Pole | Beeni Q gap | Fastest race lap | Beeni race-lap gap |
|---|---|---|---|---|
| Sainte-Croix B | Magical daddy | not recorded | Boxhead | not recorded |
| Watkins Short | Boxhead 68.254 | +0.472 (Q4) | Boxhead 68.421 | +0.353 |
| Yas Marina | Magical daddy 114.340 | +3.462 (Q5) | Magical daddy 114.259 | +3.059 |
| Road Atlanta | Boxhead 78.466 | +1.780 (Q4) | Magical daddy 79.134 | +0.630 |
| RBR Short | Boxhead 48.819 | +0.481 (Q3) | Magical daddy 49.091 | +1.069 (DNF, wheelbase) |

Three drivers have taken every pole and every win in this series. Beeni's
qualifying gap runs 0.5–3.5 s and his race-lap gap is smaller than his qualifying
gap at three of four rounds. That is a qualifying problem before it is a setup
problem, and it has been on the hub since July.

⟂ **The dossier is per series.** In GR3 Season 1 he qualified 4, 4, 5, 7, 7 and won
Round 3; the Supercars story does not transfer. Tomorrow's race is GR3.

The hub also holds Deep Forest's overtaking and traction zones as doctrine-class
notes. Nothing in `pitcrew/` or the skill reads any of it.

---

## 6. The plan

Ordered by seconds returned per hour, then by dependency, against the real calendar:

| Date | Race | Series | Format | Notes on file |
|---|---|---|---|---|
| **7 Sep** | **Daytona Road Course** | **GR3 S1 Rd6** | 20 laps, 1 stop, fuel ×3, tyre ×2, standing, weather random | event 10; plan 17 no playbook; no knowledge row; no Huracán shift table at Daytona |
| 13 Sep | Suzuka | Supercars Rd7 | 30 min timed | no event yet |
| 14 Sep | Mount Panorama | GR3 Rd7 | | |
| 16 Sep | Sardegna Road Track | Porsche Cup Rd9 | 50 min, tyre ×8, fuel ×3, rolling, weather random, Q 5 min at 20 L | tyre-bound; only wear number is pre-1.71 Monza |
| 20 Sep | Mount Panorama | Supercars Rd8 | 60 min override | |
| 21 Sep | Monza | GR3 Rd8 | | |
| 26 Sep | Fuji | Enduro Rd4 | 120 min, multi-class Gr.1/3/4, roster car, rolling, BoP | |

Each item names the failure it answers, where the change lands, and what "done"
means — a test on the *live* seam or the checked-in race fixture, never on a fresh
database alone.

### Phase −1 — tonight, for Daytona tomorrow. No code change he cannot verify before 20:00 ACST.

Event 10's state, checked: 20 laps, one mandatory stop, fuel ×3, tyre ×2; plan 17
= 11 + 9 on RS, `expects.expected_wear_per_lap` None; **no `tyre_models` row for
Daytona** and session 118's laps carry `compound NULL`, so the only wear number
George can use is one Ludo writes into the knowledge row. ⟂ At the measured
0.0570/lap (right rear, linear fit over the 3 Sep stint at ×2; through-origin
0.0636; front-left 0.0275) the race needs 1.14 sets, and a set reaches only lap
14.9 at the 0.85 ceiling of §5.2 (14.2 on the intercept fit in the same memory) —
so **tyres are yes**, and
because the box call always names the plan compound, George will say "RS" and be
right tomorrow. ⟂ The event row says `rain_possible = 0` with RH/RM/RS only while
the hub says weather RANDOM with inters and wets allowed.

| # | Work | Answers | Done when |
|---|---|---|---|
| −1.1 | **Commit the tree** as it stands — gap estimator, deque lock, pre-flight timeout, three test files, `SKILL.md`, `RECONCILIATION.md`, both car-state files, the three setup docs, ⟂ `firmware/wind/wind.ino`, this document and its research companion — one commit per concern, **after the full suite** (`python -m pytest pitcrew/tests`, rule 4) | G21–G23, L18 | `git status` clean; suite exit 0 |
| −1.2 | **The one-line `_hud` fix** at `controller.py:2263`: ⟂ read whether a sampler is *armed* (`self.hud._sampler is not None`, or a small `armed()` probe) rather than call `sampler()`, which is lazy on purpose — building it at brief time opens a socket for a practice brief that may never cross a line (`hud_session.py:540-542`). The hard-coded "I can't see other cars" (`race/brief.py:124`) stays until 0.6 | G8 | **George's spoken brief** (`race/brief.py`) says the gauge is armed at practice tomorrow |
| −1.3 | **A standing spoken rule for the stop**, in the pre-race brief and the plan's context: ⟂ *"George's fill is right if the stop lands on lap 11 or earlier. If you stop late, take laps left × this stint's burn plus the margin and ignore his number."* (raise-only means he is wrong only at a late last stop; ⟂ say "if you box when George calls it, or earlier" — the HUD reads lap 12 while he is in the box on a lap-11 call) | G1 | in **Ludo's written brief** to the driver |
| −1.4 | ⟂ **Ludo issues tomorrow's plan through the door that validates**: `strategy/handover.py accept()` via the CLI, copying strategy 15's playbook as the template. Entries carry `when` and `until`; actions from `ACTIONS` only — `fuel_short → short_shift`, `stop_missed → recost_to_flag`, `incident → recost_to_flag`, `rain → report_only`, `fuel_long → report_only`. `accept()` stores a *candidate*; **it arms only once approved on the Strategy screen.** A `race_knowledge` row for Daytona carrying the *measured* refuel 1.003 L/s and dead time 7.0 s (4 Sep) and the RS wear rate 0.0570/lap (3 Sep, source stated) — the two fields George reads and the one wear number he has. Rivals and tyre notes go **in Ludo's written brief to the driver**, not in `notes`, which nothing reads; ⟂ `wear_rates_json` holds one figure per compound, so "RR, linear, ×2, s118 laps 2–9" goes in its `source` (only s118 carries wear readings) | L2, G16, S4, G2 | strategy for event 10 shows **approved** with `handover`; knowledge row exists; **Ludo's brief** says "tyres: yes, RS" (George's spoken brief has no tyre line until 0.2) |
| −1.5 | ⟂ **Shift table for the Huracán at Daytona, or silence declared.** The legacy `app_state` table has a Huracán row (flat 7800 rpm) that **no code reads**; only `shift_points` beeps. Either Ludo cuts a table from the 4 Sep race frames via `tools/shift_points.py` and issues it with `write_shift_points`, or **Ludo's written brief** says "beep silent at Daytona" — and notes that the playbook's `short_shift` action has no beep drop behind it without a table | S11 | a Huracán/Daytona row in `shift_points`, or the sentence in Ludo's brief |
| −1.6 | **GR3 rival dossier** from the hub (⟂ verified: quali gaps to pole 1.60 / 1.60 / 1.13 / 2.35 / 3.53 s across Rounds 1–5; grid 4, 4, 5, 7, 7; won Round 3), one paragraph in **Ludo's written brief** with the hub's age (1 day) | S13, S14, §5 | that brief names the two to cover and the quali gap to pole |
| −1.7 | **Trim `MEMORY.md` under its limit** | L18 | ⟂ done tonight, 24,439 bytes |
| −1.8 | ⟂ **Pit loss measured in practice tomorrow** with (in-lap + out-lap) − 2 × clean lap, **put in Ludo's written brief and written to the knowledge row as `pit_loss_s` with its source** — the event row keeps `pit_loss_source='declared'` until 0.13's writer exists, because a hand-written "measured" off lap rows at the straddle circuit is worse than a declared 20 s, and tomorrow is a lap race so the stop-costs-a-lap logic is inert anyway | L12, G14 | knowledge row carries the number and its recipe |
| −1.9 | ⟂ **Fix event 10 on the Event screen**: `rain_possible` on, inters and wets in the compound list, to match the hub; **Ludo's brief** says "rain: George cannot see it — tell me" | G17 | event row matches the hub's lobby settings |

### Phase 0 — the week of 8–13 Sep (before Suzuka and Bathurst). The code that cost P2.

| # | Work | Answers | Lands in | Done when |
|---|---|---|---|---|
| 0.0 | ⟂ **The acceptance harness.** Extend `tools/replay_race_calls.py` to feed `lap_frames` and the pit wall's per-lap gaps and to run the controller's assess path, so anything George says can be replayed against session 138 and tomorrow's race | §6.2 | `tools/replay_race_calls.py` | replay of 138 reproduces tonight's call log verbatim before any fix |
| 0.1 | ⟂ **Fill sizing, correctly.** Last stop: `laps_after_this_stop × burn` + `fuel_margin_l` (which already prices the timed / lap-count-not-firm cases and the driver's no-spare-lap rule); intermediate stop: the plan's stint. Both discounted by *this* stop's own duration (dead time + litres / rate). The sentence names which bound and which burn | G1, G12 | `race/calls.py:fuel_target_l`, `_laps_after_this_stop` | tests: late last stop (lap 13 of a 20-lap race, 11+9 plan → 7-lap fill); **early last stop** (lap 9 → 11-lap fill, not 9); plan longer than race; replay of 138 says 63 not 76 |
| 0.2 | **Tyres is a decision.** Plan stint gains `tyres: bool`; `Handover.ACTIONS` gains `take_tyres` / `fuel_only`; box call says "No tyres" or "RS on"; knowledge `notes` retired for a `tyres_at_stop` field George reads; board shows it | G2, S4 | `strategy/model.py`, `strategy/handover.py`, `race/calls.py:1378`, `ui/driver_view.py:700` | replay of 138 says "Box this lap. No tyres. Fuel to 63." |
| 0.3 | **Tyre change = gauge fresh-set OR temp step OR driver word**, tri-state on PIT_EXIT, disagreement logged; `clear_stint` takes the tri-state; ⟂ **damage-red and hygrometer read off the same panel** with a "cannot see" state | G3, G17 | `telemetry/session_state.py:612-622, 718`, `telemetry/hud.py`, `race/coordinator.py:499` | ⟂ lap **14** of 138 records `tyres_changed=1`; a damaged frame from the sim capture reads damage |
| 0.4 | **`rival_stops.compound_reads` into `ADDED_COLUMNS`**, plus a test that diffs every DDL against `pragma table_info` on a copy of the live DB | G4, S3 | `store/schema.py`, `tests/test_schema_drift.py` | live DB has 14 columns; next race files stops |
| 0.5 | ⟂ **The handover recipe published first, then enforced.** `references/race-planner.md` gets the write call with a worked `handover` block; `write_strategy` runs every stored plan through `Handover.from_dict → validate` (it currently stores the handover half unchecked); **refuses** a plan without a playbook only from the first plan written after the recipe lands — as a separate check in `write_strategy`, because `Handover.validate()` deliberately accepts an empty playbook (`strategy/handover.py:144-170`); `playbook` absent and `playbook: []` are different answers. Until it lands, all plans go through the CLI. Screens show MCP-written plans; running app re-reads approved plans on Race-screen focus and on a `strategies` change | L2, G16, S1, S2 | `mcp/server.py:331`, `controller.py:1389, 3676` | approve from outside while the app runs → picker enables without restart; a plan without playbook is refused with the recipe named |
| 0.6 | **PTT "gap" answers** from `state.gap_ahead/behind`; ⟂ **call register markers**: a line is an instruction by default and carries no suffix; only a *suggestion* or an *unconfirmed* call is marked, in one word, and the box call takes a one-word driver confirmation (§5.5: one thing at a time) | G9, research §10.17–18 | `engineer/intents.py:497`, `race/calls.py` | PTT "gap" speaks a number when the wall has one; manifest carries the suffixes |
| 0.7 | **Noise cuts**: position hold ≥ one lap unless the place is *kept*; championship line once per change; a fuel-in-hand line suppressed within 60 s of a status carrying the same number; rig faults never spoken during a race; `rejoin_call` never opens with "Box now" when no stop is due; "short-shift and lift" suppressed when a stop is unavoidable | G18 | `race/calls.py`, `race/rival_calls.py:502`, `controller.py:5619` | replay of 138: no duplicated line, no position flap inside a lap, no rig line |
| 0.8 | ⟂ **Timed race distance computed with stop time** in `strategy/evidence.py`; the certifier runs that check and refuses only when the plan's lap count exceeds it; George says "about N on the clock" at the green and firms it | G12 | `strategy/evidence.py:686`, `strategy/certify.py`, `race/coordinator.py:339` | plan 27 re-certified says 20 and arms |
| 0.9 | **Stint-scoped burn** for the fill and the "vs plan" sentence; whole-race median kept for the flag projection only | G10 | `race/expectations.py:226-272` | replay says stint 2 over plan |
| 0.10 | ⟂ **Multiplier as a column and a gate.** `tyre_wear_mult` / `fuel_mult` promoted from provenance JSON to columns on `tyre_models` and `grip_observations`; every reader filters on the event's multiplier; a plan at a multiplier with no measured wear says `[ASSUMED]` and names the calibration run (`CLAUDE.md` §5.2) | L3, L21 | `analysis/wear_rates.py`, `strategy/evidence.py` | Sardegna ×8 plan refuses to quote a ×2 rate |
| 0.11 | ⟂ **Quali document for Suzuka**: gap-to-pole target from the hub, out-lap script, flying-lap-4 lever, fuel for the session's rule; written through `write_qualifying_plan`; predictions closed at the debrief | L13 | `brain/_inbox/setups/`, MCP | on file before Saturday |
| 0.12 | ⟂ **Run plan per session** as a template Ludo fills before every practice: runs, purpose, fuel, tyre, the one delta, lap type, clean-lap definition (the tool's) | L23, L7 | `references/mechanic.md` | Suzuka practice has one |
| 0.14 | ⟂ **Hub car regulations read into the event and the car-state file**: `carRegulations.powerLimitBhp` / `weightLimitKg` (Porsche Cup 509 BHP / 1,243 kg; Supercars 1,335 kg) and `drivetrainLimit`; `initial`/`refine` refuse a sheet outside them by name | L22, Sardegna 16 Sep | `hub/calendar.py`, `references/mechanic.md` | event 11's row and `rsr-sardegna-road-track-a.md` carry the limits |
| 0.13 | ⟂ **Pit loss and cold out-lap measured** at Daytona, Suzuka, Bathurst in practice and written with `source='measured'`; the writer for `events.pit_loss_source` added | L12, G14, S7 | `race/refuel.py`, `store/db.py` | three events carry measured values |

### Phase 1 — George becomes a strategist (14–26 Sep, across Bathurst, Sardegna, Monza, Fuji)

| # | Work | Answers | Done when |
|---|---|---|---|
| 1.1 | **Frame-level lift-and-coast and shift-rpm detectors**, live per lap and offline per stint; `short_shift_rpm` writes NULL when unmeasured; burn attributed to behaviour | G11, L1 | offline tool reproduces the 8.3/6.1/6.0 % coast and 8298/8694 shift table from session 138; harness fires the live call on the lap-17 step |
| 1.2 | **The chase call**: every lap with a car ahead inside N s: gap, closing rate (trimmed estimator), laps left, required delta **with its noise stated** (σ 0.918 s/lap; a 1.1 s/lap requirement is ~1.2σ and is said as such); silence announced when the wall cannot read it | G5 | replay of 138 laps 14–20 speaks the gap to the car ahead each lap |
| 1.3 | ⟂ **Undercut / overcut / rejoin wired — after 0.13 has measured the inputs**: `race/ledger.py` and `rival_pace.py` take the wall's gaps, the measured pit loss and cold out-lap, and the rival book; a rival's stop re-costs *our* stop lap and the fill; the top-8 truncation is stated as a limit on every projection | G6, G7 | replay: lap 10 says "three ahead are boxing, you inherit P2, stop on plan, they come out behind" |
| 1.4 | **One remaining-laps expression, one pit-loss policy** across `calls`, `replan`, `rival_calls`, the board | G13, G14 | one function, three callers |
| 1.5 | **The rail**: `structural_action` set on `stops-off`, the wear "Box this lap", and the stay-out fold; or delete `_within_the_playbook`. Decide. ⟂ And retire `safety_car` from `TRIGGERS` (`strategy/handover.py:43`) — no channel, no lobby setting — so it stops appearing under *unhandled* | G15, §6.1 | one of the two; test proves it; `safety_car` gone from `TRIGGERS` |
| 1.6 | **Persist what the wall and the trend see**: per-lap gaps, rival positions, sightings, plan-vs-actual snapshot; **a verdict per call** (`race/call_outcome` persisted, driver override recorded) | S8, S10, L11 | tables have rows after a race; export carries them |
| 1.7 | ⟂ **Race page absorbs the LoadedCard** (playbook, unhandled triggers, certificate); Strategy leaves the *Race day* rail group. **The Strategy page is KEPT and `quali_minutes` did NOT move** — the driver's call, 7 Sep: the page is where a plan is built, approved and qualifying is planned, all with the headset off, so only the contract needed to reach the grid | S12 | driver sees the standing orders before the green on the page he uses |
| 1.8 | ⟂ **The driver board, lap by lap**: box countdown; fuel in hand *to the stop* and *to the flag* as two numbers; gap ahead and behind with trend; tyre split (rear–front and RR–RL gaps, the signal measured at r=+0.82 to wear), never raw temps as colour; position; the tyres-at-stop decision; last call and its register | brief "dashboard or voice" | board spec in `ui/driver_view.py` docstring; screenshot from the harness |
| 1.9 | **Gauge guard symmetric**: a drop to zero on all corners holds for 3 reads like a rise | G20 | no series reset on replay |
| 1.10 | **Rule 13 pass** on the call inventory | G19 | manifest diff |
| 1.11 | ⟂ **Start type and penalties**: lap-one exclusion keyed on `events.start_type`; track-limit penalty detection from the lap-time step plus the HUD penalty indicator, flagged on the lap row | G26, G27 | Daytona's six penalty laps flag on replay |
| 1.12 | **Wiring audit tool**: tables with 0 rows in the live DB and modules with no non-test importer; run in CI | the pattern behind S3, S5, S7, G6 | first run lists ≤ the known set |

### Phase 2 — Ludo becomes a performance engineer with a method (parallel with 1)

| # | Work | Answers | Done when |
|---|---|---|---|
| 2.1 | ⟂⟂ **The experiment ledger lives in `brain/`, not the app.** One machine-readable table per car×circuit (`brain/ledger/<car>-<circuit>.md`, a fenced CSV block a tool can parse) beside the car-state file: date, session ids, key, direction, delta in percent of range, instrument, measured floor, control, prediction, falsifier, outcome, source, car-state revision. **The app writes nothing about it** — a change ledger in the database is what §1a removed, whatever its columns. `setup_changes` (`store/schema.py:233`, 206 rows to session 119, no writer since 5 Sep) stays as a writer-less archive beside `setup_sheets`, and §1a gains that line. `references/learning-loop.md:20`'s routing row "a setup change → `setup_changes`, filed automatically" is retired to point here. Opened first in `refine`, `race plan`, `debrief` | L5, L10, §1a | every open item above has a row; `refine` eval opens it; **no writer** for a change ledger anywhere in `pitcrew/` |
| 2.2 | **`refine` spine rewritten**: baseline (sessions, clean-lap count by the tool's definition) → hypothesis → one change (or a named coupled set under 2.3) → instrument with floor and a no-change control → prediction with complementary falsifier → verdict on the same instrument → ledger row. A-B-A return leg where a run is cheap | L6, L7, L8 | eval reproduces the 5 Sep control failure and the DF clean-lap contradiction |
| 2.3 | **Platform mode**: coupled sets judged on clearance instruments for cost and the driver for merit; trim = one slider on its named channel | L9 | eval |
| 2.4 | **Re-light the substrate**: `derive_grip_observations` 89–138, `corner_models` for Sardegna, Deep Forest, Suzuka; `tyre_models` refit per multiplier on 1.71 laps or the "single source" sentence deleted | L3, L4 | `data_health` reports observations for DF |
| 2.5 | **Debrief protocol**: driver first, per corner four phases 1–5, before data; then `where_the_change_landed`, coast/shift readers, George's calls vs outcome, radio; close every open prediction; score burn/wear/pit-loss/stint against plan; commit `brain/` | L11, L24, S10 | `tools/debrief.py` runs the whole list; a commit per debrief |
| 2.6 | **Race-plan deliverable = plan + playbook + engineering sheet** (all knowledge fields filled or "why not", tyres-at-stop stated) | L2, S4 | every strategy from Suzuka on has `handover` and a tyres decision |
| 2.7 | ⟂ **Multi-class and BoP for Fuji**: `initial` mode reads the roster car, BoP and the car regulations (0.14) from the hub; a BoP round refuses gearbox and power changes by name; the board truncation limit stated for a 3-class field | L22 | Fuji plan on file with those refusals |
| 2.8 | **Doctrine hygiene**: tag `02` §10 rows; 1.71 pass on `05` (DF entry rewritten, every "undercut is strong" line re-flagged); Shelby profile from the 156-lap archive; `11` JSON retired for `range_records`; `09` version; LSD-absolutes rule retired; `mechanic.md` paste-block removed; stale tool citations fixed | L15, L16 | `test_brain_reconciliation` extended and green |
| 2.9 | **Skill hygiene**: incidents out of `SKILL.md` into `RECONCILIATION`/memory with one line and a link; evals for the nine documented failures; `practice_intent` known | L19, L20 | `SKILL.md` < 450 lines; 20 evals |
| 2.10 | **Name every tool the skill may use**, one line each | L17 | `mechanic.md` instrument list complete |
| 2.11 | ⟂⟂ **The driver as a variable, within the refusal card**: incident rate, lap-one cost and consistency reported per session as *trends* **in the debrief only** — never in the brief, never priced into a plan, never a live warning (incidents are memoryless, `references/refusals.md`), never per corner | race-planner.md §incident ledger | debrief prints the three numbers with n; no plan carries an incident allowance |
| 2.12 | ⟂ **Register MCP** (`mcpServers` in `~/.claude.json`) and journal `propose_strategy`; rewrite `MCP-SEAM.md` to the doctrine the code follows | S9 | `engineer_writes` has a row per candidate |

### Phase 3 — Knowing our rivals (from Bathurst on)

| # | Work | Answers | Done when |
|---|---|---|---|
| 3.1 | **Hub rival dossier, per series**: quali and race-lap gap to us per round, finishing trend; spoken once in the pre-race brief; written to `race_knowledge.rivals` structured; refused when the hub is stale | S13, S14 | every brief from Suzuka on names the two to cover and the quali gap to pole |
| 3.2 | **Name the drivers**: `tools/name_drivers.py` run with hub identities; roster bitmaps ↔ hub names | S3 | `drivers` has real names |
| 3.3 | **Rival stop tendencies** per circuit from the book → George's undercut/overcut window and "he cannot make the end" calls | G7 | after two races the book projects a rival's stop lap |
| 3.4 | **Hub track intelligence** as `[DOCTRINE]` notes in the brief | §5 | brief line |

### Phase 4 — The learning loop that carries (ongoing)

| # | Work | Answers |
|---|---|---|
| 4.1 | **Predictions table** (who, what, when, falsifier, outcome, verdict) fed by Ludo's sheet predictions, the plan's `expects`, George's calls; scored automatically for burn, wear, pit loss, stint length | S10, L24 |
| 4.2 | **Parameter-effect database** from ledger rows that cleared their floor, in percent of range, keyed car × circuit × multiplier | L14 |
| 4.3 | **Track book generated from the DB** (pit loss, dead time, wear rate and knee per multiplier, burn, rival habits) — the knowledge record reads from it, never re-typed | S5, S7, L12 |
| 4.4 | **Wear-vs-temperature knee** tested on our own archive (public Feb-2025 figure is pre-1.71 and suspect) | research §9 |

### 6.1 What is refused, and why

- **Per-corner input coaching** stays refused (charter §2). 2.11 is trends only.
- **A setup record in the app** stays out (`CLAUDE.md` §1a). The ledger in 2.1 holds
  the experiment, not the value.
- **Fuel-map calls** stay out (driver's standing refusal).
- **Live rival vision as a fast signal** stays refused on the VR measurement; the
  driver has left VR, so it should be re-measured once, and the refusal kept until
  it is.
- **Safety-car branches**: no channel, no lobby setting on file. `TRIGGERS` still
  lists `safety_car`, so every handover shows it under *unhandled* on the Strategy
  screen — deliberately, until 1.5 retires the trigger.
- **A hard-coded spare lap**: `fuel_margin_l` prices the margin in litres from
  measured scatter and says it aloud; no item adds a lap.

### 6.2 Verification standard for every item

1. A test on the live seam or the checked-in race fixture, not a fresh database.
2. ⟂ Replay of session 138 (and tomorrow's Daytona race once captured) through the
   extended harness (0.0) as the acceptance run for anything George says; until 0.0
   lands, a named unit test on the seam plus the fixture.
3. Every table touched has a production writer *and* reader named in the commit.
4. `python -m pytest pitcrew/tests` green, exit 0.
5. Commit per fix; nothing left in the working tree overnight.

---

## 7. Corrections to the record made tonight

- **"He took tyres against the call" is wrong.** No call ever said "no tyres". The
  note was in the knowledge record and nothing reads it. Memory
  `project_deepforest_race_debrief_2026_09_06` needs amending.
- **"Never recomputed at the actual stop" is half wrong.** It was recomputed with the
  hose in (`race/refuel.py:176-178`); the recompute cannot go below the plan's
  stint — and ⟂ a `min()` would be wrong the other way, under-fuelling an early
  last stop. The rule is: last stop → laps to the flag; intermediate stop → plan.
- **"`DriverView` is built only from its test file" is stale.** Instantiated at
  `controller.py:4845`, pushed at 4 Hz. Memory `reference_tyre_temps_on_a_dashboard`
  needs amending.
- **"No qualifying session has ever been recorded"** (`SKILL.md:162`) is wrong by the
  column the skill does not know: `practice_intent='qualifying'` marks 12 sessions.
- ⟂ **"Damage: no channel"** was wrong in revision 1 of this document. The car icon
  on the wear panel goes red and the panel is already captured.
- ⟂ **The "undercut is strong here" lines are ours**, in `05-track-reference.md`, not
  the hub's.

---

## 8. What does not change

`EXPORT-CONTRACT.md`; `CLAUDE.md` §3 (no wear channel, no track ID); §1a (no setup
record in the app); the driver's report as primary evidence; fuel map 1; the
refusal card; one change per run, three clean laps — now with one definition of
clean.

---

## 9a. Execution record — 7 Sep 2026

**Phase −1: complete, critic agreed after two corrections.** Seven commits on
the night's tree (suite exit 0 first); `HudSession.armed()` replaces the
brief's non-existent attribute; strategy **29** approved for event 10 with a
five-entry playbook through `accept()`; knowledge row for Daytona (refuel
1.003 L/s, RS 0.0570/lap s118, rivals); Huracán shift table at Daytona for
gears 1–3 off s127 (4–6 silent); GR3 dossier and the spoken stop rule in
`brain/_inbox/setups/2026-09-07-huracan-daytona-BRIEF.md`; event 10 matched to
the hub on rain and compounds; `MEMORY.md` under limit. The critic corrected
three rival counts and two playbook notes, and found the pit-loss recipe and
`lost_the_gauge()` dead code — both taken into Phase 0.

**Phase 0: all fourteen rows landed**, one commit per row, each with tests on
the seam it fixes, suite exit 0 at every checkpoint:

| row | commit | note |
|---|---|---|
| 0.4 | `1f84ec1` | live file migrated by opening it; `tools/schema_audit.py` |
| 0.1 | `bd074e8` → `d40a5b4` → `8fd9af9` | the critic's blocker: at Daytona and Spa the line is crossed in the lane BEFORE the fill, so "in_pit → one lap off" under-fuelled tonight's plan by a lap; `crossed_in_box` fixes it and the box call and hose-in figure now count the same laps ("after the box" / "to the flag") |
| 0.2 | `7ae1bb2` | `Handover.ACTIONS` deliberately NOT extended (an action no trigger fires is dead vocabulary); the decision lives on the stint, not in a knowledge field |
| 0.3 | `ee0c917` | tri-state resolved by the gauge; **damage and hygrometer readers deferred** — no captured frame of a damaged or wet state to calibrate against |
| 0.5 | `0f8ba61` | recipe in `race-planner.md`; an empty playbook is accepted, an absent one refused |
| 0.6 | `420fa48` | the box-call "Copy?" deferred: "copy that" already accepts a re-plan |
| 0.7 | `420fa48` | position hold 8 s; league line once; fuel-long not after the heartbeat; "Fuel needs a stop"; rejoin conditional; rig faults held to the flag |
| 0.8 | `cb4d271` | stops off the clock; certifier refuses a plan that outruns it |
| 0.9 | `cb4d271` | the stint's burn once it has three clean laps |
| 0.10 | `08d9df5` | multiplier stamped on wear rates and checked; `tyre_models` columns deferred (read by nothing in `race/`) |
| 0.13 | `ad616eb` | measured at the flag from lap rows, `source='measured'` |
| 0.14 | `c5516dd` | `power_limit_bhp` / `weight_limit_kg` from the hub |
| 0.0 | `8fd9af9` | the harness replays the box off the pit lane's frames; gaps still cannot be replayed (S8) |
| 0.11, 0.12 | `34fcec9` | Suzuka quali plan; run-plan template |

**Corrected in this phase:** the plan's Phase −1 said the fill logic was "not
in the car tomorrow"; it is (0.1 and its two corrections landed before the
race). The memory `reference-crossing-in-the-box` records the lesson.

**Second critic pass on Phase 0 (0.3, 0.5–0.9) — one blocker, four majors,
all answered:**
- a red test from 0.7's conditional rejoin call, fixed to the new wording;
- 0.3: the wear projection is now silent through an unconfirmed stop (it could
  have said "Box this lap. FR at 42 percent, measured." off the old set on the
  out-lap); the resolver judges every reading against the pre-stop baseline it
  now holds, parks unresolved readings instead of appending them, needs **two**
  consecutive readings for a fresh set (an all-zero locator misread is on file)
  and uses the gauge's own `FRESH_SET_MAX`; the driver's word ("new tyres" /
  "no tyres") is a report intent that settles it outright and overrules a gauge
  verdict aloud; the resolution is written back onto the pit lap's row;
- 0.7: the fuel-repeat guard was dead (the crossing's lap number advances
  before `next_call`) and aimed at the wrong pair — removed; the straight-line
  colour call now drops the fuel figure when the heartbeat took this crossing,
  which is the pair that repeated; rig notices are released on `stop_race`;
- 0.8: the brief says the same "About N laps on the clock" the green will, and
  the line is built from fragments in the pack; 0.9: the stint's own scatter
  sizes the fill and the re-planner reads the same burn as the fill; 0.5:
  refusals are journalled.

**Third critic pass — two blockers, four majors, all answered, and one lesson
about me:** the rig-notice release had landed at the top of the per-event
close-out (my script anchored on the wrong docstring) and would have flushed
"check the amp" at the next crossing — moved into `stop_race`; the resolver
declined nothing when the sampler re-offered the same lap, so one all-zero
misread counted twice — a re-offered lap is now one reading; "same set" needs
two readings like "fresh set"; the driver's word overrules the session's swap
detector aloud, is held while he is still in the lane, names the stop it
belongs to and is written back; `SAVING_CHANGE` is argued into the facts
register in the test that exists to force that argument; the coast step is
sized on the stint's own scatter. **And the suite had been red for three
commits while I reported it green**: my background runs ended in an `echo`,
so the harness reported the echo's exit code. The output file said `EXIT 1`
the whole time. Memory `feedback-background-exit-code-is-the-echos`.

**Struck from the rows, with the reason:** 0.3's damage-red and hygrometer
readers — there is no captured frame of a damaged or wet state to calibrate
against, and a reader with no calibration frame is the fabricated-zero defect
in a new shape; they return as a Phase 1 item once one race has been driven
wet or damaged with the recording on. 0.6's box-call "Copy?" — "copy that"
already accepts a re-plan, and a confirmation word that can be misheard as one
is worse than none until the PTT round trip is proven live (A5). 0.7's "one
lap" position hold is eight seconds: a battle that has not settled in a
straight is one he is in, not one he needs told about. 0.9's "whole-race
median kept for the flag projection only" was not implemented: the stint's
burn is the best predictor of the laps ahead, flag included, and the race
median survives in the export and the audit line.

**Fourth critic pass (a34be79) — AGREED on Phase 0 and 1.1 at 418deb4,** all
ten items verified against HEAD, one residual: when "no tyres" overruled the
session's swap detector the record was corrected but the live projection still
counted the set as fresh, because `clear_stint(True)` had zeroed the count and
emptied the history. Fixed: the pre-stop count and readings are held in
`stint_before_stop` and put back under the projection on the overrule.

### Phase 1 — first batch, 7 Sep 2026

**The acceptance test, in the driver's words (7 Sep):** *"having that Deep
Forest Supercars race over again George would notice I was losing time to a
car in front that I was faster than through sector 1 and 2 but that he was
faster in sector 3, and pit me as soon as I could take enough fuel on board to
finish the race and perform an undercut."* That is now
`tests/test_undercut_deep_forest.py`, and it holds. The race is session 138 as
recorded — every lap time, fuel figure, position and the lap-13 stop — against
strategy 27. **The gaps are reconstructed**, because the wall read them on 154
frames that night and kept none (S8): built to his account, a second behind P2
at the line, two tenths gained through each of sectors 1 and 2 and four given
back in 3. The engineer now says *"Faster than Boxhead through 1 and 2. He has
you in 3."* on lap 5 (four laps of gaps, each sector outside twice its own
standard error) and *"Box this lap. Fuel to the flag. Undercut on Boxhead:
you're held up, and faster through 1 and 2. The fill costs the same now as on
lap 11."* on lap 7 — the first crossing at which 12 laps after the box at
7.4 L (96 L) fits the tank, and not on lap 6 (13 laps, 103 L). The fill it
then sizes is *"12 laps after the box"* off the same expression the box uses.
The next race replays its own reads: `gap_reads` (v16) files every gap the
wall reads with its road position, and `tools/replay_race_calls.py --gaps`
feeds them back.

**What the undercut IS here, and is not.** Not the tyre undercut — §5.4 calls
it weak in GT7 and it is not claimed. It is the *traffic* undercut: the fill
is the flag's laps times the burn less what is aboard, and both fall by one
lap's burn per lap, so the litres and the seconds standing are the same on
every lap from the first the tank can hold the flag on to the planned box.
Waiting buys nothing and keeps him in the traffic. Every term is read, not
assumed: held up is the gap inside 1.5 s for three consecutive laps; faster is
a sector where the gap shrinks outside its own noise; he has not stopped; the
stop is still owed and is the last one, so the fill is to the flag; the tank
holds it (`fuel_to_flag_l` is None while it does not); the tyres reach the flag
on the briefed rate, or the call says *"Tyre life to the flag unchecked"* and
goes out LOW with *"Unconfirmed."* A rival who has stopped, a sector map with
no measured gain, a set that will not reach the flag: silence, and the plan's
stop on the plan's lap.

**Rows landed:** 1.2 the chase (`CHASE`, a fact: gap, laps left, the required
delta against his own measured lap-to-lap spread from `expectations.sigma_ms`,
every other lap inside 20 s and 10 laps — not every lap, the closing call has
the other laps, and not the 0.918 s σ in the row, which is Monza's); 1.3 the
undercut, above, with `SECTOR_SPLIT` and `sectors.SectorMap` wired
(`note_circuit` / `note_gaps(ahead_samples=…)`), the map's bins rolled up onto
the circuit's own sector lines, and a straddling delta shared between bins by
distance — credited whole to its first bin, a 200 m read interval put a tenth
of one sector into its neighbour; 1.4 one remaining-laps expression
(`rival_calls` and the re-planner's `laps_done` both carry `laps_missed()`);
1.5 the rail — decided *set*, not delete: `STOPS_OFF` rides `drop_stop` under
`fuel_long`, the wear cliff's *"Box this lap"* rides `add_stop` under the new
`tyre_short` trigger when no stop was planned (a planned one brought forward is
timing, and free), the stay-out fold rides nothing because it recognises a stop
the driver already declined; the gate uses the call's own trigger (it looked
the KIND up as a trigger, and no kind is one, so every structural action would
have been refused whatever the desk granted); withheld, a call falls to its
`report_form` — *"You're fuelled to the flag."* and the litres — which is the
Daytona handover's `fuel_long: report_only` executed; `safety_car` retired from
`TRIGGERS` and the loaded card recomputes *unhandled* against today's triggers;
1.9 the gauge guard — a fresh-set reading is held until a second agrees (two,
not the row's three: a rise is refused up to twelve times, but the fresh-set
shape is an all-four-corners drop the locator is documented to produce, and
one confirming read separates the two), a held read is not a blind sample, and
in per-lap sampling it costs that lap its point; 1.12 the wiring audit
(`tools/wiring_audit.py`, importer regex fixed — its first run reported half
the package unimported): `rival_stops` empty, and `analysis.rivals`,
`analysis.wear_rates`, `race.rival_answers`, `race.teammate` imported by
nothing — `race.sectors` was on that list and is not now.

**Fifth critic pass (aac66fc) — NOT AGREED on 78a728a, and right.** The
call it built that I would not want under a helmet: a fuel-only plan, a
briefed 5 %/lap set, held up on lap 7 — *"Box this lap. Fuel to the flag."*
with no tyre word, onto a set at 95 % at the flag. Fixed: the undercut's tyre
check counts the laps already on the rubber when the stop takes none, and
the call carries the same tyre word every box call does. Also from the pass:
the rail had changed the sentence and not the behaviour — `stop_still_needed`
was decided by fuel alone, so a withheld `drop_stop` still dropped the stop
(now `drop_stop_granted` keeps it and the box call says why); the sector map
binned from the lap's first read while the sectors were cut from the line;
`gap_reads.lap` is laps *completed* and the replay fed the wrong lap and the
first read where the wall keeps the last; the reads are filed under the
driver's name; `CHASE` was spoken once a stint through `next_call` (its kind
was in `said`) while the builder marked laps it never spoke — tagged per lap
now, `chase_said_lap` set in `record()`, the trend read off a copy. **And the
acceptance test's pinned lap was the reconstruction's:** a constant burn
never measures a scatter, so the fill carried the model's whole-lap fallback
margin and lap 7 was that margin's lap. Driven on the session's real per-lap
burn the scatter measures (~0.15 L), the margin is two litres, and it is
**lap 6** — the test now holds both, says which premise each rests on, and
names the two that remain the reconstruction's (a lap race for a timed one;
one car ahead all race where he was P2 himself on laps 5 and 12).

**The driver's second half, same day (7 Sep):** *"I was saving fuel sitting
behind Boxhead but I was also losing lap time to first — was the fuel saving
worth the lost lap time? That's what George needs to calculate in real
time."* `race/tow.py`: a litre not burned before the stop is worth its
standing time at the pump and nothing else; against it, the lap time given
away in his wake. Held-up laps are the wall's; the clear-air reference is
this race's own laps with nothing within 3 s, else the plan's burn and lap
time, and the sentence says which. Deep Forest at the hub's 2 L/s: *"The tow
saves you 0.6 litres a lap — 0.3 seconds at the stop. You're losing 1.4
seconds a lap to Boxhead. Not worth it."* (`TOW_TRADE`, a fact; litres and
seconds both named — rule 13). A tow that pays means no undercut is called;
one that does not puts its two figures in the undercut's reason.

**1.11 landed:** `analysis/penalties.py` reads a served penalty off the frames
— a hard brake at speed, going straight, outside every corner's 250 m
approach in the circuit's corner model — and `tools/find_penalties.py`
reproduces the six laps the driver named from the 4 Sep Daytona runs at
5,194–5,218 m with no false positive at the Bus Stop or in the race (the
memory's count, exactly). The lap row carries `penalties_served` and the
derived `penalty_lost_s`; the lap leaves the pace and burn populations; he
hears *"Penalty served. About 1.5 seconds."* The HUD's penalty indicator is
NOT read — no calibration frame exists. And lap one is keyed on
`events.start_type`: evidence after a rolling start, out after a standing
one.

**Struck or deferred, with the reason:** the chase's *"silence announced when
the wall cannot read it"* is the brief's *"I can't see other cars"* line and
was not duplicated per lap. 1.6 is half done — the reads persist; verdicts per
call and the plan-vs-actual snapshot are not yet — and 1.7, 1.8, 1.10 are
open. Critic 5's open questions, carried: one misidentified board row resets
the held-up window and the sector map (the trend wipes on any subject
change); two consecutive locator misreads would still cut the gauge series;
the sector map's offset path (gap ≥ 2 s) has no test.

### Where we stopped — 7 Sep 2026, evening

**Done and committed (master, suite green on each by pytest's own exit line):**
Phase −1; Phase 0 rows 0.0–0.14; Phase 1 rows 1.1, 1.2, 1.3, 1.4, 1.5, 1.9,
1.11, 1.12, and half of 1.6 (gap reads and board positions persist). Last
commits: `78a728a` (the undercut and the chase), `d26e23e` (critic 5's fixes,
the tow trade, penalties). **The driver's acceptance test is in and holds:**
`pitcrew/tests/test_undercut_deep_forest.py` — sector split on lap 5, the
undercut on lap 6 on the real burn scatter, the tow priced and found not
worth it. Its remaining premises are written in its docstring (a lap race for
a timed one; one car ahead all race).

**Critic pass 6 (af83b53) on `d26e23e` — NOT AGREED, reported as we stopped.
The six pass-5 fixes are confirmed real (each driven, not just tested).
FIRST JOB ON RESUME — three defects, two of them calls wrong under a helmet:**

1. **`TOW_TRADE` speaks after the last stop** (`rival_calls.tow_trade_call`):
   no guard on a stop remaining, and `clear_stint` clears `said` at PIT_EXIT,
   so a new car ahead after the lap-13 stop gets *"Worth it — stay in it"*
   about a saving tow.py itself says is worth nothing once the fill is in.
   Fix: return None when no stop remains; gate the undercut on `worth_it`
   only while one does.
2. **The tow pairing is off by one live** (`coordinator._weigh_the_tow`):
   the trend's keys are laps COMPLETED (`lap_now()`), so the gap read
   during lap N pairs with lap N−1's burn and time; the acceptance test's
   `_drive` keys the trend on the lap itself with the FIRST read, which is
   neither the live nor the replay convention, so it cannot see it. Fix:
   shift keys by one in `_weigh_the_tow`, and make `_drive` note `lap−1`
   with the last read like the replay. (Also: the replay's `lap_num−1`
   ignores `laps_missed()`, so keys drift after a lost pit-lane lap.)
3. **The penalty detector's false positives become a spoken fact**
   (`analysis/penalties.py`, controller `_corner_windows`): a 0.6 s
   avoidance stab on a straight, a wet brake 300 m before a corner, or an
   auto-segment corner model missing a corner (the Bus Stop flagged every
   lap) each produce *"Penalty served. About 0.3 seconds."* Fix: refuse on
   auto-segment models (`CornerModel.source`) and wet sessions; speak it
   LOW with "Unconfirmed." since the HUD indicator is not read.

Minor: `_box_soon` lacks the "dropping the stop was not granted" clause
`_box_now` carries. Questions carried: the plan-burn reference for the tow is
inside the practice-over-race band (3–9 %), so "Worth it" can come from bias
alone — say it LOW on that reference; the rail without a `fuel_long:
drop_stop` entry re-enacts Fuji-lite (three box calls for a stop the fuel
does not need, then the fold) — the driver should be shown that choice;
`_offset_bins` is dead live and would clamp rather than wrap if wired; CHASE
plus CLOSING can speak about the same car four laps in five.

**1.6's other half — APPLIED 8 Sep 2026, `59a3144` and its critic fixes.**
It was parked in `docs/pending/` and both files there are now gone: the edit
script is spent and the test is in the suite. See "Critic pass 8" below for
what it took.

### Critic pass 8 — 8 Sep 2026, on 1.6's other half

**NOT AGREED on `59a3144`, two blockers, and the provenance was the story.**
Most of that commit came from a one-shot edit script written on 7 Sep and
**never run**. Its `controller.py` anchor did not match the file at all — it
was written from a condensed reading and omitted a comment block — so the
script applied four files and stopped. Every other anchor in it was equally
unchecked, and the critic was told to assume so. It found:

1. **The export field could not reach a file.** `_calls_made` carried
   `verdict`; the section builder projects `callsMade[]` through a fixed key
   list that did not include it, and nothing noticed because `kind` is
   dropped the same way. Worse, widening that list alone would have made
   `_validate_known_keys` **refuse the whole payload** — the field was
   undeclared in `payload.KNOWN_KEYS` and in the contract — so a half-done
   job costs the driver the export, not the field. Three places, and the
   format is now `gt7-pitcrew/1.9` with a §16 entry.
2. **`_filed_calls` outlived the race.** `stop_race` never cleared it and
   `_judge_filed_calls` runs at every crossing of every session kind, so a
   race whose flag was never detected — the Fuji failure, on file — left box
   calls held, and the first PRACTICE crossing afterwards judged them against
   practice laps and wrote *"not-acted"* onto a race call. CLAUDE.md rule 11,
   and the named remedy (a reset with a caller) existed only on the arming
   side. `_filed_session` is the guard, `__init__` builds both, and Stop
   settles what is open with `final=True` before the session id goes.

**Majors, each a real defect:** the verdict was popped from the dict BEFORE
the write, so a locked database — this app writes from the wear sampler, the
pit wall and the video path — lost that call's verdict for good and aborted
the rest of the loop into a log line naming none of them. The judging ran
before the fragment check, so the phantom row (*"two laps driven, three
recorded"*, observed twice) filled a box call's window one crossing early and
wrote *"no stop on laps 12-14"* about a lap 14 he had not driven. The
position-call path filed nothing, so `verdict = NULL` meant three unrelated
things. And `verdict` and `disposition` answered the same question two ways
in one object — `disposition` pools pit laps over every race session of the
event including rehearsals — so it is derived from the verdict now (rule 13),
falling back to its own derivation only on `cannot-tell`.

**Minors:** a board row filed under lap 0 where the crossing had no lap
number (rule 3); the short-shift window counted the call's own lap, so a
driver already short-shifting read as having obeyed; the v17 note in
`schema.py` had swallowed a v15 paragraph; and the controller half — the
hand-placed half — had no test at all, which is now five.

### Row 1.10 — the rule-13 pass, and the manifest diff

**The sweep.** 28 call kinds (`REGISTER`, `calls.py:283`), 25 of them ranked in
`URGENCY`; **51 `Call(...)` sites** — 33 in `calls.py`, 16 in `rival_calls.py`,
2 in `coordinator.py` — plus 14 further `voice.say` sites in the controller
feeding `brief`, `colour`, `replan`, `refuel`, `quali_fuel`, `qualifying`,
`intents` (~40 PTT answers), `gate`, `knowledge` and `debrief`. About **239
distinct sentence templates**.

**Two would have cost him a race.**

1. **"N laps of fuel" was an absolute when he asked and a margin when the
   engineer volunteered it.** The PTT answered `lapsOfFuel` — tank over burn —
   as *"8.2 laps of fuel."*, in the noun phrase `FUEL_LONG`, the colour line
   and the heartbeat all use for `_fuel_gap`, a margin, with the reference on
   it. **This is the original rule-13 defect reinstated on the push-to-talk
   path**, and the failure direction is the one that kills a race: 8.2 heard
   as a margin with ten to run is believing in slack that is really −1.8. The
   answer now comes from `fuel_in_hand`, the one expression that produces the
   figure and its reference together, and says the same words the engineer
   says. Where nothing frames it, it says *"8.2 laps of fuel in the tank."*
2. **The chatty tier kept counting down to a stop that had just been
   cancelled.** `_stops_off` says *"You're fuelled to the flag. No more stops
   on fuel."* and does not clear `stint_ends_on_lap`; `_box_now` and
   `_box_soon` go quiet because they gate on `stop_still_needed`, and
   `colour` speaks on exactly the crossings where they are silent — from the
   raw field. So the next lap said *"Stop next lap."* in the box vocabulary
   about a stop that had been called off, and on the same lap he could hear
   *"Fuel good to the flag."* The controller passes `None` once the stop is
   retired: the figure now comes from the expression that decided there is a
   stop (rule 12).

**The manifest diff.** Every wording that moved, and why:

| Site | Was | Is |
|---|---|---|
| `intents` FUEL | "8.2 laps of fuel." | "1.9 laps of fuel in hand to the stop." / "8.2 laps of fuel in the tank." |
| `colour._countdown` | "3 to the stop." / "Stop next lap." | "3 laps to the stop." / "One lap to the stop." |
| `colour` straight | "3 to the box." | "3 laps to the stop." |
| `colour` wear | "LR 72." | "LR 72 percent." |
| `calls._box_soon` | "Box in 2." | "Box in 2 laps." |
| `calls._box_now` | "…Fuel to 68 litres - 9 laps after the box." | "Fuel is the constraint. Fuel to 68 litres…" |
| `calls._chase` | "You need 0.7 a lap." | "You need 0.7 seconds a lap." |
| `calls.stay_out` fold | "Short-shift 450, you're 0.6 short." | "Short-shift 450 rpm, you're 0.6 laps short to the flag." |
| `calls._incident` | "That cost you 11 seconds." | "That cost you 11 seconds against your pace." |
| `coordinator` composure | "That moment cost you about 4 seconds." | "About 4 seconds off the road." |
| `calls._conserve` | "about 0.1 a lap per degree" | "about 0.1 seconds a lap per degree" |
| `calls._tyre_temp` | "Rears 6 over the fronts." | "Rears 6 degrees over the fronts." |
| `rival_calls.stay_out` | "Stay out." | "Don't box yet." |
| `rival_calls.sector_split` | "0.4 a lap through 1 and 2" | "0.4 seconds a lap through 1 and 2" |
| `rival_calls.rejoin_call` | "Box now and Rocky comes out in front." | "Rocky comes out in front if you box now." |
| `rival_calls.undercut` | "The tow's 0.3 seconds a lap at the stop against 1.4 seconds a lap lost." | "The tow saves 0.3 seconds of stop time a lap and costs 1.4 seconds of lap time." |
| `refuel` | "92 to the flag if you stay out." | "92 litres to the flag if you stay out." |
| `replan` | "Recommend 2 stops." | "Recommend 2 stops from here." |
| `brief` | "I can't see other cars - position only." always | only where the wall will not watch |
| `intents` GAP / PACE / `_on_plan` | "closing 0.3 a lap", "0.8 down on the plan", "Pace 0.8 a lap down" | all say "seconds a lap" |

**Why each moved, in one line each:** "a lap" carried seconds in five places
and litres in two while `tow.py`'s own docstring forbade exactly that; "N
stops" meant the race's total, this stop's ordinal and the stops remaining;
"cost you N seconds" was lap time in one place and time-off-road in another,
and one spin trips both; "N to the flag" was litres in exactly one place and
laps everywhere else; "Stay out." and "Staying out?" are one syllable apart
and mean opposite things; and `REJOIN` opened with the box instruction while
meaning the opposite, which §5.5 calls a hedge behind a flat assertion.

**The pack follows the sentences, and that is what "manifest diff" buys.**
`phrase_manifest._FUEL_LINE` parsed a fixed tail; it now takes the reference
from the line, so the PTT answer decomposes into `STOP_FUEL_TAIL` and
`COLOUR_FUEL_TAIL` — clips the pack **already held** for the volunteered call.
One sentence, one clip: rule 13 pays the voice pack as well as the driver.
`test_voice_pack` and `test_phrase_manifest` are the gate, and a sentence that
moves without reaching the pack is a pause at the moment a call arrives.

**Struck from the audit, with the reason.** `colour._milestone`'s *"5 to go."*
against the heartbeat's *"5 laps to go."* was reported as a collision and is
not one: rule 13 forbids one phrase meaning two things, not two phrasings of
one unambiguous thing — and `test_race_wiring` uses the difference as the
marker that tells a colour line from an instrument reading. Left alone.

**Carried:** the `UNDERCUT` reason can still stack the fill clause, the tow
clause and the tyre clause, which is long for §5.5. The driver asked for the
tow figures in that call by name (7 Sep), so they stay until he says
otherwise; what changed is that the two seconds figures no longer share a
phrase. Also carried from the audit: `intents` GAP answers as a two-row table
(§5.5), and `expectations`' *"3.12 against 3.20"* is two bare litres-per-lap.

**Row 1.10 closed — AGREED at `0015e74`, after four critic passes.** The
sweep found the two blockers above and fourteen more collisions; the four
passes then found six more, and **four of those were in my own fixes**, which
is the part worth keeping:

1. *"Fuel is the constraint."* was reported from `plan_binding_constraint`,
   which only one of `_stop_needed_on_fuel`'s three branches reads — so with
   a mandatory stop owed and fuel good to the flag it named fuel. Rule 12, in
   the commit that cited rule 12. `_why_the_stop_stands` returns the decision
   and its reason from one expression now.
2. The prefix was glued in front of `_fuel_instruction`, which can say *"Fuel
   is fine — the tank covers the next stint."* My fix SUPPRESSED the reason to
   hide the contradiction, which threw away the branch that kept the stop.
   **They were never contradictory** — one is against the flag, the other
   against the next stint, and neither named its reference. Rule 13 again.
3. `fuel_reaches_flag(state) is not True` folded *"cannot be known"* into
   *"will not reach"* — a claim about arithmetic nobody had done (rules 3
   and 5), two lines below the same function refusing to speak an unknown
   `mandatory_stops_left` as a regulation.
4. The retirement fix guarded two call sites and left **four** surfaces
   counting down to a cancelled stop; moving it into `laps_to_stop()` closed
   those, and the `lapsPastBox` key added in the next commit became a
   **fifth**. Its own docstring says why: a guard at each consumer is one
   chance to miss per consumer.

**And twice the test written for a blocker did not reach it** — one asserted
the absence of a string that no longer existed, one fed `lapsToStop: -2`,
which the coordinator cannot produce. Both are the impossible-fixture class
this project keeps finding. Every blocker now has a behavioural test driven
through a real coordinator or a real screen.

**Carried out of row 1.10, each named rather than quietly dropped:**

- The retirement of a cancelled stop has **no latch**, so a burn median that
  moves back across the margin makes the countdown vanish and return —
  rule 10's shape. Bounded today because `drop_stop_granted` is False without
  an explicit `fuel_long: drop_stop` entry.
- The `UNDERCUT` reason can still stack the fill clause, the tow clause and
  the tyre clause, which is long for §5.5. The driver asked for the tow
  figures in that call by name (7 Sep), so they stay until he says otherwise.
- `intents` answers GAP as a two-row table (§5.5), and `expectations` says
  *"3.12 against 3.20"* — two bare litres-per-lap.
- **Two families live-synthesise today and deserve their own pass**: the
  whole overdue family (*"N laps overdue."*, and FUEL_SHORT's *"…laps short
  of the flag on current burn — short-shift and lift if you stay out."*), and
  the push-to-talk's *"No gap read yet — the wall has nothing this lap."*
  Each is a pause at the moment a call arrives.
- For the driver-board session: `ui/driver_view.py:791` captions the
  countdown *"laps to box"* where everything else now says *to the stop*, and
  its `None` branch reads *"no plan"*, which is false both on the last stint
  of a real plan and now on a dropped stop — `DriverState.has_plan` sits
  right there unread.

### Row 1.7 — the standing orders, and critic pass 1

**AGREED pending: `3558801` + the critic-pass commit.** The playbook, the
certificate and what George cannot see lived on the Strategy page's
`LoadedCard` — and `refresh_plan`, which rebuilds that card, is wired to the
RACE screen's `shown` signal, so arriving on the race page refreshed a
contract rendered a screen away. The words are in
`strategy.handover.standing_orders` now and the ink in
`ui.widgets.render_standing_orders`; both screens render through them.

**The driver's scope call, 7 Sep:** *"drop it from race-day nav, keep the
page."* The row sent `quali_minutes` to the Race page because the page was
going to be deleted. It is kept, under a **Plan** group of its own, which is
where a qualifying session read with the headset off belongs — so
`quali_minutes` stays put and the row's "then the Strategy page goes" is
withdrawn rather than silently unmet. The rail group was **split** rather
than the name moved: `SCREENS` is `NAV_GROUPS` flattened and the rail indexes
straight into the stack, so relocating would have renumbered the stack build
order, `LATE_SCREENS` and the shortcuts.

**Three defects found by rendering the real stored plans through it** — not
by reading the diff — all in one direction, the driver told a rule is armed
when it cannot fire: a blind trigger was named only when there was *no* rule
for it (the RBR Short plan has a `rain` entry, so "he cannot see rain" was
suppressed and the rule listed as a standing order); `safety_car`, retired
from `TRIGGERS` on 7 Sep, rendered as an ordinary order on a plan that
predates the retirement, because `PlaybookEntry.validate` runs when a
handover is *authored* and nothing revalidates a stored one; and
`standing_orders({})` built the whole contract for a driver with **no plan**.
The six assumptions stored against the Daytona plan are rendered for the
first time.

**Critic pass 1 — two blockers, three majors, six minors, all fixed:**

1. **`clear_log()` deleted the block at the arm.** It predates the row, takes
   every widget out of `log_layout` and `deleteLater`s anything that is not
   `log_empty` — and the orders live in that layout. `start_race` calls it.
   Between the arm and the deferred delete the block was out of the layout
   but still a child of the log holding its last geometry, drawing under the
   incoming calls; once the delete ran, **every later `set_plan` raised
   `RuntimeError: wrapped C/C++ object of type QVBoxLayout has been
   deleted`** — reachable by returning to the Race page after the race, by
   `_poll_plan`, and by approving a plan mid-race, and PyQt aborts the
   process after `sys.excepthook`. It is the failure CLAUDE.md §7 records as
   having cost the suite a quarter of its files for months. `processEvents`
   does not run a DeferredDelete, which is why the suite was green.
2. **"George falls back to his own" was false for exactly the two triggers
   the structural rail gates.** `_may` returns True unconditionally for a
   free action and refuses a structural one with no entry. Two pairs reach
   it: `tyre_short → add_stop` and `fuel_long → drop_stop`. `tyre_short`
   joined `TRIGGERS` on 7 Sep so **no plan on file grants it**, and the
   approved plan told the driver George would use his judgement on the one
   decision he is barred from. **This is the identical inversion the commit
   claimed to be fixing** — the words changed, the failure to separate a free
   action from a gated one did not. The predicate is `handover.grants` now
   and `_may` delegates to it, so the sentence comes from the expression that
   decides the call (rule 12).
3. `"Standing orders - THE DESK"` was stamped over a block whose whole
   content is that no desk wrote anything — the row's own third fix,
   reintroduced by the heading it added.
4. Three phrasings for one fact (rule 13): the screen, the CLI's *"George
   will report it and decide nothing"*, and the stored `unhandled` list. The
   CLI prints the shared sentences now; the stored field is documented as an
   authoring-time record that nothing reads back.
5. *"which he cannot see at all — it will never fire"* asserted a cause the
   code had not determined: `dead` is anything not in `TRIGGERS`, which is a
   retirement for any reason. Two sentences now.
6. **The rail has never fitted the smallest display and nothing measured
   it** — 384 px bare and 510 px with all seven state notes against 501, and
   this row's new heading took it to 425/551. Nothing clipped because the
   layout spent the 20 px bottom margin first. It scrolls now, and there is a
   test.
7. Minor, each fixed: a blank stored trigger rendered *"The desk left a rule
   for , which …"*; the height test was a tautology inside a scroller (it
   asserts the block is in the scroll area too now); `render_standing_orders`
   returned a count one short of the widgets it added; and the
   `show_standing_orders` docstring named the wrong condition for an empty
   block. **One claimed minor was not a defect**: pass 1 said `dead`
   compared frozen dataclasses by value so a duplicated entry reported a live
   rule as never firing. It did not — liveness is a function of `trigger`
   alone, so two equal entries are both live or both dead. The comparison is
   by identity because that is what the question means, and the commit
   message for `3cf458c` overstates it.

### Row 1.7, critic pass 2 — three majors, all of them in pass 1's own fixes

1. **The `tyre_short` sentence was false for every stint but the last, on
   every approved plan on file.** `GATED` stated the gate flat; `calls.py`
   sets `add_stop` only when `stint_ends_on_lap is None`, which is the last
   stint — with a stop ahead the same reading brings it forward, which is
   timing, and timing is free. So on lap 8 of stint 1 at Daytona the driver
   hears *"Box this lap."*, the instruction the contract had just told him he
   would not get. And it was **worse than the sentence it replaced**, because
   `falls_back` now excludes gated triggers, so he got the wrong line instead
   of the incomplete one. Rule 12 half-applied: the sentence moved onto
   `grants()` and left the other half of the gate behind. The sentence now
   carries the condition and quotes the call's own `report_form`.
2. **`grants` answered the screen and the race differently for one stored
   plan.** The list branch took the FIRST entry for a trigger; the
   coordinator's dict comprehension keeps the LAST. On a playbook holding
   `fuel_long: drop_stop` then `fuel_long: report_only` the screen said
   George may drop the stop and the race refused it — the exact inversion the
   single-expression fix existed to remove, reintroduced by it. Reachable:
   `mcp.propose_strategy` stores a payload without `Handover.validate`, and
   `certify` never reads the playbook.
3. **The new rail scroller focused and selected items it did not scroll into
   view.** `QScrollArea` follows `focusNextPrevChild`, not a direct
   `setFocus`, so End / Down / Ctrl+7 put the crayon focus bar 71 px below
   the fold with nothing on screen to say where he was. `ensureWidgetVisible`
   in both, and the test asserts it rather than a height that can no longer
   fail.

And the rail's `NOTE_CHARS = 15` **never fitted**: 140 px between the column
margins, 162 px wanted at the widest character, so `3 x RM, 2 stops` was
clipped by the widget on the surface used every visit — the failure the
constant exists to prevent, in the constant itself. Measured to 12. The
scrollbar is 6 px and themed; the default took 14 px off a rail with
horizontal scrolling forced off, so those pixels were unreachable rather than
scrollable. The CLI re-rendered the handover it was sent rather than the row
it stored, which dropped every *"Not checked:"* line at the one moment the
author could still act on it.

**Left in Phase 1:** 1.8 (driver board spec and screenshot), 1.10 (rule-13 pass on the call
inventory — the "to the stop / to the flag" pair and "Box this lap" from three
kinds are the known ones; `UNDERCUT` now carries the tyre word), plus critic
5's carried questions (a misidentified board row resets the held-up window;
two locator misreads still cut the gauge series; the sector map's offset path
is untested). **Then Phases 2–4.**

### Critic pass 7 — 8 Sep 2026, five rounds on critic 6's three defects

**Commits `abcfe1a` → `f8230ca` → `c534de9` → `580addb` → `6d89827` →
`d573228`. AGREED at the fifth round.** All three of critic 6's defects and
the `_box_soon` minor are closed, verified against HEAD rather than against
the commit messages:

1. **`TOW_TRADE` after the last stop.** `_a_fill_is_still_to_come` gates the
   verdict on the flag, on `stint_ends_on_lap` and on `stop_still_needed` —
   the one expression this codebase uses for "is the stop still a stop"
   (rule 12). What replaced the silence is `_tow_is_spent`: said once, only
   to a driver who was told in those words to stay in it, and only about the
   car he was told about. Critic 7 checked and was right that `CHASE` and
   `CLOSING` do NOT cover the lap time he is giving away — `_chase` needs
   `laps_left <= CHASE_LAPS` and speaks a different quantity, and
   `closing_call` needs a rate outside `TREND_WORTH_SAYING_S`, which a
   driver at a steady gap in a wake is inside by construction.
2. **The tow pairing off by one.** `_lap_of_read_key[lap_now()] =
   lap.lap_num`, written at the top of `_on_lap` before `state.lap` moves,
   so it is the counter's real value rather than an assumed offset — a fixed
   `−1` drifts after a crossing lost in the pit lane, because `lap_now()`
   carries `laps_missed()`. A read whose lap never completed drops out
   (rule 3). `_drive` and `replay_race_calls.py` use the same convention.
3. **Penalty false positives spoken as fact.** "Possible penalty served" in
   the first two words, LOW so `spoken()` ends it "Unconfirmed.", and the
   seconds come from the readings that are sayable.

**The penalty detector was rebuilt three times, and every threshold in it now
comes off the archive rather than off an argument.** The record of the dead
ends matters more than the answer:

- *"Refuse auto-segment models"* (critic 6's suggestion) refuses all nine
  models on file and deletes the feature.
- *"Two consecutive laps at one place is the road"* deletes a real pair —
  Daytona session 114, laps 5 and 6.
- *"Four consecutive laps"* rested on a sweep that silently began at session
  82. **Yas Marina's 3,470 m is flagged on 10 of 15 laps of the session 44
  RACE with a run of NINE and is unambiguously a corner** — 13 of the 14
  looked-at laps brake there, 250 km/h down to 105, in a 1.6 km gap between
  T4 and T5. No run threshold can work.
- **What does work: a corner is braked on nearly every lap and a penalty is
  not.** `braked_at` reads every hard brake with no speed, lateral-g or
  corner-window filter; `RoadNotPenalty` judges the share of looked-at laps
  that brake at a place. On file the penalties top out at 56% (Daytona s118,
  5 of 9) and the corners start at 93% (Yas s44, 13 of 14).
- **And the biggest false-positive class was in neither critic's list:** of
  270 flags on file, **141 are lap one of a practice session** — four on one
  Monza lap, five on one Spa lap. Pit laps, out laps and lap one are not
  read at all.

**Two bars, because one is not enough.** Leave-one-out over every modelled
corner says ~28% of them would sit under `BRAKED_SHARE` if they went missing
— Watkins T2 at 13 of 18 in a race, Spa T1 at 13 of 17. So `BRAKED_SHARE`
(0.8) withdraws and the new `BRAKED_DOUBT_SHARE` (0.7) only silences: the lap
still leaves the pace and burn populations, which is safe whatever caused the
brake, and no sentence is spoken, which is not. On the archive the lower bar
changes nothing (0.65–0.80 all speak the same 49 readings at penalty places
and 34 at corners; 0.60 speaks 48). It is set from the RUNNING share, not the
settled one — Daytona s118 peaks at 3 of 5 on its way to 5 of 9.

**Struck from the previous commit messages, because they were wrong and are
now cited nowhere else:**

- `580addb` said "no place on file is flagged on every lap" and "the longest
  run is two". Both false — see Yas s44 above.
- `6d89827` justified the sayable-cost fix with session 65 laps 2/3/4 and the
  figures 13.1 s against 2.1 s. **Neither occurs.** Those laps are before
  `BRAKED_LAPS_NEEDED`, so nothing is in doubt and `speak == kept`; and
  **there is not one lap on file where `speak` is a proper subset of
  `kept`** — at 0.70 the doubt band silences nothing in the archive. The fix
  is right on rule 12 and stays; the evidence beside it was invented.
- The same commit said a missing corner costs 6–11 s against a real
  penalty's 1.4–3.5. The corner readings are 6.4–11.6 s (n=33), but the
  penalty readings run **0.8–10.7 s, median 1.9** (n=47) — 1.4–3.5 is the
  Daytona banking alone, and RBR s101's three confirmed race penalties are
  4.1, 4.2 and 5.1. **The derived cost does NOT separate the two
  populations**, so it is not available as corroboration.

**Also fixed across the five rounds:** a withdrawal recounts the lap rather
than zeroing it (session 65's laps carry a penalty at one place and a corner
at another); the withdrawal reaches the stored row through the new
`Store.set_lap_penalties`, not only the in-memory pace population; "the
fill's in" is only said where `last_stop_lap` records a stop (it was being
said to a driver whose stop had been dropped on fuel); `TowTrade.worth_it`
lost both its special cases — `max(x, 0.0)` was rule 9 and each replacement
was wrong once; the tow's sentence no longer borrows `closing_call`'s "losing
N seconds a lap to X", which means the gap growing and not a lap time
(rule 13); `penalty_note` is cleared at a stop like `incident_lap` beside it;
and `_box_soon` carries `_box_now`'s "dropping the stop was not granted".

**Carried, with the reason:** `tow_trade_call` is once a RACE per car, not
once a stint — `clear_stint` does not empty `said_tags`, so a verdict given
in stint one about a car he is still behind in stint two is not revised. A
lap is a lap however short it is in the brake share (8 of 654 looked-at laps
carry under 70% of a circuit's frames). A withdrawal already written is not
re-instated. `SAME_PLACE_M` at 150 m is wider than the closest corner pair in
five of nine models, so a penalty within 150 m of a habitual corner brake
inherits its share and is silenced — no instance on file.

**A process note worth keeping.** Three of the five rounds turned on an
archive count I had asserted from a sweep narrower than the archive. The
memory's own lesson — *"replay every circuit shape on file, and let the
critic build the counter-example"* — was written for exactly this and I broke
it three times. The rule that came out of it: **quote a count only from a
sweep whose bounds are in the script, and re-derive it after the code
changes** — the running share is not the settled share, and 49/34 differed
from the final-share figures I had first published.

**How to resume:** read §9a from "Fourth critic pass" down, run
`python -m pytest pitcrew/tests -p no:cacheprovider` and read pytest's own
summary line — **do not add a second `-q`**, `pytest.ini` already sets one
and `-qq` suppresses the summary, leaving only an exit code. Run
`python tools/wiring_audit.py`, then apply the parked verdict change and put
it to a critic before anything new. Every batch: build, test, critic, fix,
commit — in that order.

## 9. Critic record

**Pass 1 (6 Sep, late).** Twenty-six claims spot-checked: 21 confirmed, 2 wrong
(`tyre_models` "all v1.70"; "driver profile for each entrant"), 3 overstated
(s102's 17 keys; `results()` "nothing else"; a symbol name). Thirteen objections,
three blockers:

1. **The calendar** — Daytona is tomorrow; four series in 20 days. → Phase −1
   added; Phase 0 re-cut against the real dates; multiplier, rolling start,
   random weather, multi-class and BoP items added (0.10, 1.11, 2.7).
2. **0.1's `min()` under-fuels an early last stop.** → Rule replaced: last stop
   → laps to flag + `fuel_margin_l`; intermediate → plan stint; early-stop test
   added; hard-coded "+1 lap" removed (driver.md:108).
3. **2.1's from/to ledger is a second setup record.** → Ledger holds direction
   and percent-of-range delta with a link to the car-state file; no absolute
   value column.

Majors folded in: 0.5 and 0.8 no longer un-arm every plan; damage and rain
readers added to 0.3 (the panel is already captured); 1.3 now follows the pit-loss
measurement (0.13); quali moved to Phase 0 (0.11); run plan (0.12), board content
(1.8), PTT register markers (0.6), driver-as-variable trends (2.11), hub freshness
(S14, 3.1), MCP registration (2.12), the acceptance harness (0.0) and the §8
position on the pit wall (§1.4) added; `MEMORY.md` and the rival dossier moved to
tonight. Factual corrections applied throughout and marked ⟂.

**Pass 2 (6 Sep, later).** All thirteen pass-1 objections checked: eleven
resolved, two partly (the ledger's home; random weather tomorrow). Nine
revision-2 claims verified, one wrong: −1.4 named a playbook action
(`recost_stints`) that `ACTIONS` does not contain, so `validate()` would have
refused tonight's handover and the CLI exited 1 — **blocker, fixed** (actions
from `ACTIONS` only, `when`/`until` on every entry, "done" = approved on the
Strategy screen). Majors folded in: the ledger moved out of the app into
`brain/ledger/` (§1a is about *any* change ledger in the database); 2.11 is
debrief-only (the refusal card forbids incident prediction); S2/0.5
re-diagnosed — `write_strategy` is an *unvalidated* door, not one that drops
the playbook, so a bad playbook would arm too; event 10's rain flag and
compounds mismatch the hub (−1.9); −1.8 no longer hand-writes `measured` off
lap rows at the straddle circuit; hub car regulations read (0.14); the legacy
Huracán beep table is confirmed read by nothing (−1.5); 0.6 marks only
suggestions and unconfirmed calls. Minors applied (`wind.ino`, full suite,
`MEMORY.md` done, −1.2 caveats).

**Pass 3 (6 Sep, late).** Confined to the diff. All thirteen pass-2 items
resolved on evidence (every action and trigger in −1.4 exists in
`strategy/handover.py`; strategy 15 is a valid template; the five GR3 quali gaps
exact; the 3 Sep wear stint ran at the race multiplier). Two required changes,
both applied: the Phase −1 arithmetic had inverted "1.14 sets" into "covers
1.14 races" (a set reaches lap 14.9 at the 0.85 ceiling; tyres are yes, and more
so); and 2.1 must name `setup_changes` as a writer-less archive and retire
`learning-loop.md:20`'s routing row. Six minors applied: `validate()` accepts an
empty playbook so 0.5 needs its own check; `safety_car` stays an unhandled
trigger until 1.5; which *brief* each Phase −1 row means; this document in the
commit list; −1.2 probes rather than builds the lazy sampler; `wear_rates_json`
provenance goes in `source`.

**Pass 4 (confirmation).** Eight of nine items confirmed on evidence; three
residuals applied: the wear provenance string names `s118` (the only session
with wear readings), 1.5 now retires `safety_car` from `TRIGGERS` so §6.1 points
at a real item, and −1.5/−1.8 name Ludo's written brief.

**Pass 5 (confirmation).** All three residuals confirmed on evidence. Critic
verdict: *AGREED — all bases covered.* This is the plan of record until the
Daytona debrief on 7 Sep amends it.
