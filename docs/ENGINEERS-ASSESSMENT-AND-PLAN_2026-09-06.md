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
| 1.7 | **Race page absorbs the LoadedCard** (playbook, unhandled triggers, certificate) and `quali_minutes`; then the Strategy page goes | S12 | driver sees the standing orders before the green on the page he uses |
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
