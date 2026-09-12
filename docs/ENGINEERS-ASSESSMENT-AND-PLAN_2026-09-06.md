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
| 3.5 | **Their lap time, derived and labelled so**: a rival's lap is ours plus the change in the gap, read at the same road position each lap off `gap_reads` (v16). Carries its sample count (rule 4) and goes under `derived` with the model stated (rule 5) — never spoken as a measured time | driver, 12 Sep | George states a named rival's pace with its n, or says he cannot |
| 3.6 | **Read the stop off the standing time**: a gap jump of about the circuit's stored pit loss marks it; litres = (standing − dead time − tyre time) × the measured refuel rate. **Tyres-or-fuel is not separable from standing time alone**, so the fill is a range with its assumption named, and `None` when the stop was not seen (rule 3) | G7, driver 12 Sep | `rival_stops` carries a row per stop with its source and its range |
| 3.7 | **Must they stop again, and are we ahead**: their derived burn against the laps to the flag; our remaining stops × pit loss plus our pace against theirs; and the lap time needed to get or stay in front, against his own measured lap-to-lap spread (`expectations.sigma_ms`, not Monza's σ). Reports the constraint that bound it (rule 12) | driver, 12 Sep | one call per race naming the rival, the number and what bound it |
| 3.8 | **The profile that carries between races**: per driver name per series — habitual stop count, stop lap as a fraction of the race, compound choice, whether they defend or yield. Written to the book, refused on fewer than two races | S13, driver 12 Sep | the brief names a rival's habitual strategy with the race count behind it |

**What binds Phase 3, and it is not the arithmetic.** Every row above keys off
seeing a rival stop. The GT7 board shows **only the top 8**
(`reference-gt7-board-truncation`) and a car that pits drops below the cut —
so the name and the gap both go dark at precisely the moment the derivation
needs them. `rival_stops` is still empty, which is the keystone defect on the
Deep Forest register. Until a stop can be timed from the board, 3.6 returns
`None` rather than a number and 3.7 and 3.8 have nothing to stand on, so
**3.2 — naming the drivers — is the row that unblocks the rest**, and 3.5 is
the only one of the four that can land before it.

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
- ~~**"No qualifying session has ever been recorded"** is wrong by the column
  the skill does not know: `practice_intent='qualifying'` marks 12 sessions.~~
  **STRUCK 12 Sep - this correction was wrong twice, and the skill was right.**
  `sessions.kind` holds only `practice` (140) and `race` (19): no qualifying
  session has ever been recorded, literally. And the marked count is **13**,
  not 12 - all `kind='practice'`, 17 Aug to 7 Sep. The skill now says both,
  correctly (`references/modes.md`, `quali`), which is row 2.9's
  "`practice_intent` known".
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
was not duplicated per lap. 1.6's verdict per call landed at
`59a3144`; 1.7 and 1.10 are closed; **1.8 is what is left**, with the
plan-vs-actual snapshot still outstanding. Critic 5's open questions, carried: one misidentified board row resets
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

The CLI re-rendered the handover it was sent rather than the row it stored,
which dropped every *"Not checked:"* line at the one moment the author could
still act on it.

**Two claims in this pass were measured on an uncalibrated instrument and are
retracted below** — the rail's note width and the scrollbar. See pass 3.

### Row 1.7, critic pass 3 — I measured Qt text on a platform with no fonts

**Offscreen Qt has no font database.** `QFontInfo(stencil_font(10)).family()`
is `''` and `pixelSize` is `-1`, so every glyph gets the same fallback advance
and `"W" * 12` measures exactly what `"i" * 12` does. Every width in pass 2
came from that, and two app changes were made on the strength of them:

- **`NOTE_CHARS` 15 → 12 was a regression.** On the machine the app runs on,
  `Bahnschrift Condensed` resolves and fifteen W's want **102 px** of the 140
  available; every note on file wants 62–76. Nothing had ever clipped. The
  shorter count truncated `Ludo 1-stop, RBR Short, 30 Aug` and three sibling
  plans to the identical string `Ludo 1-stop…` — on the note whose whole job
  is to say *which plan is armed*. It is a pixel elision now
  (`QFontMetrics.elidedText` against `NOTE_PX = 134`), because a character
  count cannot be right in a proportional font.
- **The 6 px scrollbar rule bought nothing and cost contrast.** `theme.apply`
  already paints the trough `RUBBER_DEEP`, the handle `TREAD` and a
  `TREAD_LIGHT` hover, at 12 px. The "14 px unstyled #9f9f9f stripe" was the
  platform default measured *without the theme loaded*. The local rule halved
  it, dropped the hover state, and set the handle at **1.57:1** — worse than
  the 2.04:1 that `app.py` rejects for this same rail twenty lines below.
  Deleted.

This is `feedback_calibrate_instruments_before_use` on a project that has
already discarded six derived indices for it, and it is the third pass running
in which the worst finding was inside the previous pass's own fix.

**Two more, both real:**

3. **The `tyre_short` sentence was wrong a third time.** Pass 2 moved the
   condition into the words but left it as prose in a constant, and
   `standing_orders` never evaluated it — so a plan with **no stop in it**
   (`_recommend` iterates `range(0, max_stops + 1)`) read *"he may bring a
   planned stop forward"* about a stop that does not exist, and *"on the last
   stint"* about a gate that bites from the green. `_withheld_sentence(trigger,
   plan)` reads `stops` now, and the `fuel_long` line is withheld entirely on a
   no-stop plan because `_stops_off` needs a planned stop to fire at all.
4. **The AST guard could not see the construction `calls.py` uses.** It walked
   `keywords` on any node and found the wear-cliff site only because that site
   spells its rail as `dict(...)`; a dict *literal* splatted as `**rail` — one
   refactor away — would have left `found` equal to `GATED` and the test green
   about a call site it never read. It reads both shapes now and asserts that
   the number of containers it saw equals the number of textual mentions, so
   it cannot go blind quietly.

Minor: the screen asked `grants` a filtered playbook while the race asks an
unfiltered one (equal today only because both gated triggers are live —
retiring one, as happened to `safety_car` on 7 Sep, would have reopened the
split); the AST test read a CWD-relative path; only one of the two
`report_form`s was pinned against `calls.py`; and
`test_the_screen_and_the_race_ask_the_same_gate` hand-wrote the coordinator's
own dict comprehension instead of building a real coordinator.

**Carried, not fixed:** the briefed wear cliff's reason restates its call
(*"Tyres past the stint limit. Tyres are past the stint limit on the measured
rate for this compound…"*) against §5.5's *reason second and short*.
Pre-existing since `78a728a`, and the contract now quotes that call, so the
two move together.

### Row 1.7, critic pass 4 — the arithmetic behind pass 3, and three guards that could pass while blind

**Pass 3's change was right and its numbers were wrong.** *"Fifteen W's want
102 px"* was measured **through `set_note` while `NOTE_CHARS` was still 12**,
so it truncated first and I measured twelve. With the theme loaded the family
resolves to Bahnschrift — the app-wide sheet beats `stencil_font`'s Condensed,
and `note.font()` reports it, so the elision metrics were at least the ones
the label paints with — and fifteen want **129 px**. The real strategy labels,
which `nav_state` passes through verbatim, want **169–306 px against a 178 px
rail**, so long ones elide whatever the constant is. Measured against every
label on file, the pixel elision is better than or equal to the old character
count on all of them — `1 stop - box lap 5` survives whole at 94 px where 15
characters cut it — so the change stands and only the arithmetic is retracted.
**That the rail cannot show a full strategy label is the rail's width, and is
carried rather than fixed here.**

1. **`NOTE_PX = 134` was a constant where the widget knows its own width.**
   The scrollbar takes 12 px when it shows and nothing when it does not, so a
   constant for the narrow case cut every note 12 px short in the wide one —
   which is the normal one at his 1600×1000 window. The room is asked of the
   viewport now.
2. **The rail test asserted the elider against its own argument.**
   `set_note` elides *to* `NOTE_PX`, so `sizeHint().width() <= NOTE_PX` is
   green at 134, at 300 and at 1000. It compares against the viewport less the
   column margins now — the only number that is not the elider's own input.
3. **`_stops_planned` read two fields that may both be absent and ignored the
   one `Handover.validate` requires.** A plan carrying only `stints`
   certifies and stores, and returned `None` — which the caller rendered as
   *"he may bring a planned stop forward"* about a plan with no stop in it,
   the fourth wrong version of that sentence. It reads `len(stints) - 1` now:
   `Plan.stops`' own definition, present on all 28 stored plans, agreeing with
   the stored `stops` on every one, and the expression the coordinator arms
   from. **It also caught the test fixture**, which claimed one stop while
   holding one stint.
4. **The AST guard counted containers it could not read.** `containers`
   incremented before the literal check, so a site naming its action through a
   module constant, or setting its trigger elsewhere, kept the tally balanced
   and dropped the pair in silence; and `mentions` was a raw substring count,
   so a comment failed the test for nothing. Tokenised now, with an explicit
   `unread` list. Break-tested against five shapes: dict literal splatted as
   `**rail`, action via a constant, a missing trigger key, plain keywords, and
   a mention in a comment — the first four go red, the last stays green.

Also: the two withheld sentences had drifted apart (rule 13) — the tyre line
had dropped *"without a rule from the desk"* while the fuel line kept it — and
a **granted** `fuel_long: drop_stop` on a plan with no stop is a rule that can
never fire, which is the same failure as a rule for a trigger he cannot see
and now says so.

### Row 1.7, critic pass 5 — a confident zero, and three guards with no teeth

1. **`_stops_planned` returned a confident `0` for a plan whose other fields
   said `1`.** `certify` refuses `stops != len(stints) - 1` but **never checks
   `pit_laps` against either**, and `validate` requires only `stints` — so a
   plan listing one box lap and one stint validates, certifies, stores, and
   printed *"box lap 10"* two inches above *"No stop is planned"* on the grid
   card. Pass 4 caused it by reading `stints` first and returning it. Three
   disagreeing fields is a don't-know, and the function's own headline says
   never 0 for a don't-know. It reports a number only when the readings agree
   now, and **says the disagreement aloud** (rule 1): *"The plan lists 1
   stint, names 1 box lap — they disagree, so how many stops it holds is not
   known."* The `tyre_short` sentence has a third form for the unknown case —
   the half that is true whatever the count.
2. **My own MAJOR-5 fix said the same thing three times.** Dropping an
   unfireable rule out of `live` put it in `dead` (*"George no longer acts on
   it"* — false, it is a live trigger) and left its trigger uncovered
   (*"No rule from the desk on fuel long"* — also false, there is one). An
   entry is in exactly one of three states now: readable and able to fire,
   readable and unable, unreadable.
3. **The rail assertion was `_note_room`'s own expression, bit for bit.** The
   suite was green with `NOTE_MARGINS = 0` while notes ran 41 px past the
   viewport with horizontal scrolling off. And the first two replacements
   were the **instrument error a third time**: the label grows with its own
   content so its width says nothing, and the absolute rail width is a text
   measurement — offscreen, *"Reference"* alone wants 154 px of the rail's
   178 (96 on the real font). What no font can change is that eliding a long
   note must not make the rail want more room than a short one, and that is
   what it asserts.
4. **`_note_room()` was 608 at the moment the app calls `set_note`.**
   `_update_rail` runs from `PitCrewWindow.__init__`, before `show()`, when
   the scroll area is unlaid and its viewport reports the default 640 — so
   nothing elided and the first painted frame carried a 307 px note hard-cut
   inside a 178 px rail. Bounded by the rail's own fixed width now.
5. **Notes were never re-elided**, so one set while the scrollbar was hidden
   kept its text and had the last 12 px clipped — reachable by dragging the
   window toward its own 560 px minimum. The raw text is kept and
   `resizeEvent` redoes it.
6. **The AST guard's `containers == uses - 1`** hard-coded "exactly one
   benign mention" and failed on `return bool(call.structural_action)`, a
   keyword-only parameter, a second annotated dataclass, and
   `replace(call, structural_action=None)` — ordinary code, two of which
   `coordinator.py` already contains. Every occurrence is classified into a
   named box now, and anything that fits no box is what *gone blind* means.
   Break-tested both ways in the suite: six innocent shapes stay green, five
   blind ones go red (dict literal, action via a constant, missing trigger,
   plain keywords, subscript assignment). The one shape it still cannot see —
   a positional `Call(...)` — is stated in the docstring rather than claimed
   away.

Minor: the rule-13 assertion was a bare `count(...) == 2`, which stays green
if one sentence is emitted twice and the other dropped; it checks each
sentence now. And `max(60, ...)` in `_note_room` — a floor invented for a
viewport the widget could not read — is gone with the ceiling that replaced
the need for it.

### Row 1.7, critic pass 6 — the re-elision missed the path the app uses

1. **`resizeEvent` never fires when the scrollbar appears.** The rail is
   `setFixedWidth(178)` and its height belongs to the window, so the widget
   is not resized by the thing that narrows the viewport by 12 px — and that
   happens part-way through `_update_rail`'s own loop over the screens.
   Measured on the real platform with the theme at **1600×501, his smallest
   display**: two notes clipped, `ludo plan - Daytona GR3` with the ellipsis
   itself half cut — the exact state pass 5's comment claimed to have fixed.
   An event filter on the viewport now, and the test brings the bar in the
   way the app does (seven notes at a height where the empty rail fits and
   the filled one does not) rather than by resizing the rail.
2. **"The plan lists 3 stintss."** The plural was added twice for `stints`,
   and both fire for every plan with two or more stints — which is every real
   one. Pass 5's test used a single-stint plan, the one case where it cannot
   show.
3. **`live` was built per-entry while `grants` is last-wins.** A playbook
   holding `fuel_long: drop_stop` then `fuel_long: report_only` printed both
   under *George may* while the race honoured only the second: the driver
   believing a lever is armed when it is not, in the block pass 5 rewrote
   under the heading *"an entry is in exactly one state"*.
4. **The AST guard had a false PASS in the idiom `calls.py` itself uses.**
   `constant()` unwrapped an `IfExp` to its `body` and discarded the `else`,
   so `structural_action="add_stop" if unplanned else "abandon_plan"` read as
   one gate and dropped the other in silence — the whole thing the guard
   exists to prevent. Both branches now, and the break-test covers it.
5. **The rail assertion was a fallback-font artefact for the third time.**
   *"Eliding must not make the rail want more room than a short note does"*
   is **false on the real font** — it held offscreen only because the
   fallback inflates the nav labels to 178 px and swamps the note. It
   compares the elided text's own advance against the room the LAYOUT gives
   it (margins read off the layout, not from `NOTE_MARGINS`), which is true
   under any font and is not `_note_room`'s expression.
6. **The action was never checked**, only the trigger — so `fuel long - fuel
   map`, a standing refusal of the driver's, printed as something George may
   do alone, and `incident - teleport to pits` **filled the coverage gap** so
   he was never told he was on his own for an incident. And six ordinary
   shapes (`getattr`, a comparison, `global`, an import, a `def` of that
   name, a comprehension key) were falsely accused of blinding the walker.

**And a failure that was not row 1.7's**, found by this pass: eleven tests in
`test_hub_events.py` went red overnight on `SOON = "2026-09-07T10:30:00"` —
a hard-coded future date that became the past, so *"the round that is
coming"* linked nothing. It is `test_hub_calendar.py`'s constant too. Both
derive from the day the test runs now; bumping them would only reset the
fuse. CLAUDE.md §7's *"reproduce it with your change reverted"* is exactly
what this was.

### Row 1.7, critic pass 7 — two sentences that argue with themselves

1. **"The plan lists 1 stint, says 1 stop, names 1 box lap — they disagree."**
   The readings are compared in STOPS and were printed in each field's own
   unit, so the numbers on screen were not the numbers compared. Three equal
   figures and a claim that they conflict reads as the app being broken
   rather than the plan. Every figure is in stops now — *"its stints imply 0
   stops, it says 1 stop, its box laps name 1 stop"* — and the test walks all
   100 combinations asserting no sentence ever prints equal figures.
2. **The `unrunnable` bucket added in pass 6 was left out of `covered`**, so
   one block said *"The desk's rule for incident asks for teleport to pits …
   it will never fire"* and, four lines below, *"No rule from the desk on …
   incident"*. One trigger, two opposite claims — which the block's own
   comment already forbids for `stillborn`, and which pass 6's new test
   **encoded as the desired result** by asserting the two halves separately
   and never reading them side by side.
3. **The Race page's headroom is two pixels, not eight.** 493 was measured
   offscreen; with the real font and the app's own stylesheet the page wants
   **499** against the 501 cap. The instrument error a third time, in the
   number this row has quoted in three commits. The orders still cost zero —
   499 bare and 499 with the longest plan on file — which was the design
   claim and it holds. **The 8 px of slack in the test assertion does not
   exist**, and it is recorded there rather than papered over: the equality
   is the part with teeth and it holds in both.

Minor: *"asks for nothing, which George cannot execute"* for a blank action —
doing nothing is the one thing that is always executable, and it is also how
a driver reads `report_only`; it is named as unreadable now, the way a blank
trigger is. A superseded duplicate vanished silently and is named. *"you have
refused outright"* put the driver in two roles in one paragraph, where every
other line is third person. And the pass-6 write-up called the `IfExp` false
pass *"the idiom `calls.py` itself uses"* — `calls.py`'s conditional is
`… else None`, for which the old code was already right, so it was hardening
against a shape one edit away, not a live defect. Corrected in both places.

**Carried, and worth a decision rather than an accident:** strategy 15 renders
**3,432 characters** of standing orders with one 432-character line, #29
1,801. It scrolls away once calls arrive and §5.5 binds live calls rather than
pre-green reading — but there is no cap, and on the 501-px display the block
is below the fold from the first frame.

### Row 1.7, critic pass 8 — I removed a contradiction by deleting the true half

1. **Pass 7 restored the defect pass 6 had found.** Pass 6: *"`incident -
   teleport to pits` filled the coverage gap so he was never told he was on
   his own for an incident."* Pass 7 saw the opposite complaint — one trigger
   described twice — and fixed it by putting `unrunnable` back into
   `covered`, which is exactly what pass 6 removed. The driver then read that
   the desk's rule will never fire, did not find `incident` among the things
   George decides himself, and would conclude George does nothing on an off —
   while `_incident` carries no `structural_action` and fires with no
   playbook at all. **The fix is the merge, not the deletion:** one sentence
   carries both facts. Trading a visible contradiction for a false silence is
   the worse of the two errors.
2. **"Treat it as absent" told the driver to do what the function does not.**
   A blank action is still cover, so the trigger is struck from the fall-back
   line — the sentence now says the fall-back itself, like the one above it.
3. **"Only the last is used"** sat directly above *"…it will never fire"* in
   five states out of six. *Read*, not *used* — true in all of them.
4. **The corrected instrument story was wrong in both places.** 493 vs 499 is
   not the font and not `offscreen`: offscreen **with the stylesheet** reads
   the same 499 the real platform does, and the 6 px is the app-wide
   `font-size: 15px` box metric — which `race_screen.py` already documents
   forty lines above. And the slack was removable: `setStyleSheet(
   theme.STYLESHEET)` on the screen reproduces the real figure with no
   process-wide effect. **`test_every_screen_fits_the_smallest_display_he_owns`
   now measures with the sheet too** — it had 6–8 px of slack on every screen,
   on the one display that cannot afford any. All seven still fit: the Race
   page at 499, the rest between 259 and 324.
5. A test whose docstring required the state its own assertions now forbid,
   and a figure guard that could not see a sign — `str.isdigit()` is False
   for `-1`, and a negative `stops` printed *"it says -1 stops"*. A negative
   is not a count (rule 3): the reading is dropped rather than rendered.

Minor: the middle clause of the disagreement said a bare *"it says"* where
the other two name their field. And pass 7's write-up claimed the test
*"walks all 100 combinations asserting no sentence ever prints equal
figures"* — the assertion is that they are not ALL equal, and 36 of the 84
sentences legitimately repeat a figure. The claim was wrong, not the test.

### Row 1.7, critic pass 9 — the oscillation, caught

1. **Pass 8's fall-back clause re-said what pass 1 blocked.** Pass 1's second
   blocker was, in its own words, *"it said George falls back to his own on
   the two decisions he is barred from"* — and the reasoning is still in the
   file: *"the gated pairs … drop out here, because saying both about one
   trigger is saying two things."* Appending the clause unconditionally put
   it back for `fuel_long` and `tyre_short`, sharpest on a no-stop plan where
   George's own judgement on tyre-short is nothing at all. It is true for
   `fuel_short`, `stop_missed` and `incident`, whose calls carry no
   `structural_action`, and is emitted only there. **This is the ninth pass
   and the first to catch the fix oscillating rather than merely being
   wrong.**
2. **Dropping a negative `stops` deleted the finding.** `{stints: 3,
   stops: -2}` went back to reporting a confident **2** and *"he may bring a
   planned stop forward"*, with nothing saying the stored plan carries an
   impossible figure — pass 5's *"a confident zero"*, back. The wording was
   the wrong half; *"how many it holds is not known"* was the true half. The
   reading is kept and rendered as *"its stop count says -2, which is not a
   count"*.
3. **The 6 px cause was written down a second time without being measured.**
   `font-size: 15px` contributes **zero** on both platforms; the figure is
   set by `QScrollBar::handle:vertical { min-height: 40px }` — drop that one
   rule and the page wants 459. And bare is 493 offscreen but **497 native**,
   so four of those pixels really are the font database. What is true and
   now stated in all three places: **499 with the sheet, offscreen and
   native alike, against the 501 cap.**
4. The test written to close the contradiction asserted only `incident` and
   said nothing about `fuel long`, which appeared twice — the gated trigger
   was the one left unchecked, which is the same omission it was written to
   fix.

Minor: a cross-reference to a comment in `race_screen.py` that lives in
`ui/widgets.py`, and a low-end screen height (259) quoted from offscreen.

### Row 1.7, critic pass 10 — one finding refused, and the asymmetry under it

**The pass's headline is refused, and pass 5 established why.** It reported
*"No rule from the desk on … fuel long — George falls back to his own"* on a
0-stop plan as false. It is true: `_past_half_stint` falls back to
`lap >= laps_total / 2` when there is no stop, so the FUEL_LONG call fires —
measured, *"You can push."* with `structural_action=None`, so the playbook is
never consulted. Changing it would be the oscillation this pass was asked to
look for, with me causing it. **Recorded rather than acted on.**

**The real defect was the asymmetry underneath it**, which the same pass
reported as a minor: on a 0-stop plan, a plan with NO `fuel_long` rule was
told George falls back to his own, and one with a GARBAGE rule was told only
that it will never fire — so adding an unrunnable rule *removed* a true
statement. The suppression was keyed on *"is this trigger gated"* when it
means *"will a withheld sentence follow"*, and on a 0-stop plan none does.

**Three tests were blind to that shape.** The file does carry 0-stop
fixtures — that is how `stillborn` is reached at all — but not in the three
tests that could have seen this, including the one written in pass 9 to close
this very contradiction. `test_a_plan_with_no_handover_still_says_george_has_no_rules`
was green *because* of the leak: it asserted each trigger's words appear
somewhere, which cannot tell a true sentence from a false one. Both plan
shapes now, and it asserts the gated pair is never both fallen back on and
withheld.

Minor: *"one reading cannot disagree with itself"* — a lone corrupt `stops`
said *"The plan disagrees with itself"*; and the *"which is not a count"*
clause dangled into the next reading when the negative was not last. Corrupt
readings are ordered last and the head sentence matches the case.

**And a fourth copy of the disproven `font-size` cause**, in
`test_impeccable_findings.py`, with figures from the wrong platform. Measured
natively, bare → styled: Car 247→**265**, Settings 243→265, Event 249→267,
Strategy 257→279, Reference 267→285, Practice 305→324, **Race 497→499**
against the 501 cap — so the six that are not the Race page sit between 265
and 324 styled. Deleting `font-size: 15px` changes nothing on either
platform. (Car's styled figure was written as its bare one, and the correct
265–324 spread was deleted for disagreeing with it — pass 11.)

### Row 1.7, critic pass 11 — the asymmetry was half-closed

1. **(A)** Pass 10 gave the `unrunnable` loop a fall-back clause keyed on
   whether a withheld sentence follows; the **`stillborn` loop beside it
   never had one**. So on a 0-stop plan whose desk granted
   `fuel_long: drop_stop` — the grant `GATED` exists to accept, on a shape
   `_recommend` produces — the driver was told George uses his own judgement
   with a *garbage* rule and with *no* rule, and told nothing with the real
   one. Pass 8's first finding, left standing in the sibling loop. All three
   states say it now.
2. **The new block-level assertion could not fail.** The two facts are always
   on different lines, so a per-line check never fires — measured against a
   mutant restoring pass 1's original blocker, which left the test green. It
   checks across the block now: for each gated trigger, named in the
   fall-back list *or* carrying a withheld sentence, never both.
3. **Both new sentence branches shipped untested** — the corrupt-reading
   ordering and the single-reading head. The 100-combination sweep seeds
   `stints` every iteration, so it can never build a one-reading plan.
4. **The single-reading branch sliced the sentence it had just built**
   (`split(" says ")`), a phrase only one of the three readings contains — an
   `IndexError` on the grid for any rewording. Built from the reading now.
   And the `" - which is not a count"` separator collided with the head's own
   dash; `(not a count)` instead.
5. *"Twenty of the twenty-eight plans on file"* matches neither sweep:
   **24 of 28 rows** carry no handover, and **7 of the 10 approved** — which
   is the figure that matters, since only an approved plan reaches the grid,
   and it is the one the line originally had.

### Row 1.7, critic pass 12 — a stop count of `5.0` was dropped

**(A), and pre-existing.** `_stop_readings` and `certify` both gated on
`isinstance(stops, int)`, so a float or a string vanished from the
comparison: `_stops_planned` answered a confident **0** off the stints alone,
`_stop_disagreement` said nothing, and the grid printed *"No stop is planned,
so he cannot bring one forward…"* over a plan whose own field said five.
`certify` could not refuse it because **it shares the guard**.

**JSON has no integer type** and `mcp.propose_strategy` stores arbitrary JSON
from the desk, so `5.0` is what a round-trip produces rather than a hostile
input. This is pass 5's *"confident zero"* in the one shape eleven sweeps
never parameterised — every one of them seeded `stops` as a Python `int`.
`_as_count` reads an integral float as a count now; a field that is there and
cannot be read at all is named and quoted rather than dropped, and `certify`
refuses it.

Minor: `_FIELD_NAMES` was a second vocabulary for the three fields, two of
its three entries unreachable by construction — the lone-reading sentence is
promoted off the same `_STOP_SAID` map now. The `stillborn` loop's fall-back
guard had one reachable branch, which is a fact about `_cannot_fire` rather
than a shortcut, and both now say so where they are. And a **second copy** of
the stale row list — *"1.7, 1.8, 1.10 are open"* — 758 lines above the one
pass 11 trimmed, which is §1a's own shape.

### Row 1.7, critic pass 13 — `"stops": null` became a corrupt field

1. **(A), and an oscillation I caused.** Pass 12 keyed the new branch on the
   KEY (`"stops" in plan`) where both its siblings read the VALUE, and where
   `certify` — added in the same diff — guards `is not None`. So
   `"stops": null`, the ordinary JSON for *not stated*, counted as corrupt:
   `_stops_planned` returned `None` instead of `0`, `_cannot_fire` went
   False, and a granted `fuel_long: drop_stop` rendered under *George may, on
   his own* on a plan where `_stops_off` can never fire — **the state pass 11
   was written to close.** One token.
2. **`len(parts) > 1` is not "the readings disagree".** An unreadable clause
   counted as evidence of a conflict, so two fields that agree plus one that
   cannot be read printed *"The plan disagrees with itself"* over two
   identical figures. And checking the conflict first then gave a **lone**
   negative reading the same head. The head is chosen in order now: one
   clause is never a disagreement; a conflict between readings is; anything
   else is a field that cannot be read.
3. **`as_stop_count` was a guard at two consumers.** Four more sites read
   `plan["stops"]` raw, so a float certified clean by pass 12's new gate then
   printed **"1.0 stop"** on the Race page, slipped past the export's own
   stints-vs-stops cross-check (`isinstance(stops, int)`), went into
   `strategy.plan.stops` as `1.0` against a contract whose example is `1`,
   and matched an approved plan in the controller only by `==` luck. One
   expression, read by all six — `feedback_a_guard_at_each_consumer`.

Minor: `1e300` passed `is_integer()` and became a 301-digit number printed
into a wrapped label on the grid (bounded now); an unreadable field was
`repr`'d without truncation, so a `stints` given as a dict rendered its whole
structure into a standing order; and the lone-clause sentence was still
string surgery on the built clause — it is formatted from the template, with
an assertion so a reworded template fails loudly instead of silently losing
its capital.

### Row 1.7, critic pass 14 — the bound guarded the exotic shape and missed the common one

1. **(A)** `isinstance(value, int)` returned *before* `_STOP_CEILING` was
   consulted, so the bound sat on the float branch alone — and `json.loads`
   gives a Python `int` for a digit string with no decimal point, which is
   the likelier shape. **`1001.0` was refused as unreadable and `1001` was
   read as a count**: two opposite verdicts on the same JSON number, inside
   the expression this row created so every consumer would agree. Measured, a
   400-digit int rendered a **2,822 px** order line against a ~733 px plate —
   more than double the 1,352 px `strategy_screen.py` already records as a
   defect worth fixing.
2. **(A)** `any(number < 0)` in the head test was decisive **only** where
   there was one reading beside an unreadable field — only `stops` can read
   negative, so with two readings the set-size test has already decided. So
   the one case it changed was the one the ordering exists to prevent: *"The
   plan disagrees with itself about stops"* with a single figure in the
   sentence. Removed; the set size is the whole test.
3. `certify`'s refusal quoted the same field with a bare `repr` and reaches a
   driver-facing status label — `_short` is `short_value`, public, and both
   read it. And `export/payload` treated a value it could not read as a
   reason to **skip** the stints-vs-stops cross-check rather than as a
   problem, so `stops: true` — which `isinstance(True, int)` used to
   catch — silently stopped being checked.

Minor: the comment added in pass 13 said *"a float is what
`_section_from_plan` emits"*, which the same diff had made false; and one
last raw read of `plan["stops"]` in `race_outcome`'s caller.

### Row 1.7, critic pass 15 — nothing in (A) survives

The pass's own verdict: *"AGREED on the substance — nothing in (A) survives."*
It measured the export byte-identical for all ten events with an approved
plan, every one of the 28 plans' sentences identical, the bucket partition
unchanged, and all three of pass 14's tests failing against the parent and
pinned by targeted mutation. What it did find is all (B), and all of it is
closed here:

1. **The same `isinstance`-on-a-JSON-number gate, one line above the one
   three passes hardened.** `_validate_plan`'s stops check sat inside
   `all(isinstance(n, int) for n in stintLaps)`, so **one float in that list
   silently disabled it** — and the stintLaps-vs-laps check with it. The
   enclosing gate reads the same way now, and a list that is not lap counts
   is its own problem rather than a reason to skip everything below it.
2. **A stop ceiling is not a lap ceiling.** Fixing (1) by reusing
   `as_stop_count` bounded a lap count at 1,000 — and a 24-hour race at
   90-second laps is **960**. `as_whole_number(value, ceiling)` takes the
   bound from the caller; `as_stop_count` is the stop-shaped wrapper.
3. `build.py`'s comment claimed the value was *"normalised upstream on both
   branches"*. It is not — `_strategy_section` prefers the stored
   `plan["export"]` block and normalises nothing on that branch, so the call
   is load-bearing exactly where it matters, and the comment invited the next
   reader to delete it.

**Carried:** `_section_from_plan` maps every unreadable `stops` to `null`, so
the payload cannot tell *"the desk stated no stop count"* from *"it stated one
that is not a count"* — §7 asks that every null be genuinely unmeasured.
Bounded rather than fixed: `certify` refuses such a plan and both approval
routes are certify-gated, so it cannot become the approved plan the export
reads.

### Row 1.7, critic pass 16 — an empty `stintLaps` skipped every check

1. **(A), introduced by pass 15.** `if raw_stints and all(…)` / `elif
   raw_stints:` left an **empty list in neither branch**, so the sum, the
   stops and the compounds checks all vanished with no problem raised — where
   the version before it reached them, because `all(…)` over an empty list is
   True. Demonstrated end to end through the MCP door on a DB copy: a 20-lap,
   one-stop, two-compound section **with no stints at all** exported clean,
   and §7's *"refuse to export rather than export something wrong"* did not
   fire. An empty list is a readable list of no laps; the checks below say
   what is wrong with it.
2. **The other half of pass 15's claim was not delivered.** The stops
   readability problem was still nested under the stints, so a `stintLaps`
   that could not be read took it down too. Both it and an unreadable `laps`
   are their own problems now, outside that block.
3. **The same `isinstance`-on-a-JSON-number gate in `certify`**, on stint
   laps: `{"laps": 10.0}` was refused as *"not a positive whole number"*
   while `{"stops": 1.0}` on the same plan certified. It failed safe — a
   refusal, not an accept — but told the driver a plan lacked whole lap
   counts when it had them.
4. `abs(value) <= ceiling` made a negative a whole number, so `[-5, 25]`
   summed to 20 and passed under a message reading *"not a list of lap
   counts"*. `as_whole_number` takes a `minimum`: `None` for stops, where a
   negative is deliberately kept and **named** as unusable, and 0 for laps,
   where it is simply not a lap count.
5. `pitLap` was the unnormalised sibling of `stops`, two lines under the
   comment saying why `stops` is normalised — desk JSON put `11.0` into the
   contract, `_validate_plan` never looks at that key, and `race_outcome`
   rendered *"lap 11.0"* to the driver. And `if plan.get("pitLap")` folded a
   box lap of 0 to None.

Minor: pass 15 added a test whose docstring narrated a defect **no commit ever
contained** — reusing `as_stop_count` for `stintLaps` was the first draft of
that pass's fix and never shipped. It pins the constant, and now says so.

### Row 1.7, critic pass 17 — the shape, not another site

**The pass's own diagnosis, and it is the right one:** *"each pass normalises
at ONE site, and the next pass finds the site it did not cover."* Passes 12–16
taught six readers that `11.0` is eleven; pass 17 found `certify` widened to
accept `{"laps": 11.0}`, normalising into a **local list** and handing the
plan on untouched — so `stint_ends_on_lap` became `11.0` and George said
**"the next 9.0-lap stint"** with the hose in, on the driver view and in the
rival calls too. `feedback_a_guard_at_each_consumer`, in the gate this time.

So the answer is not a seventh reader:

1. **The plan is read as whole numbers ONCE, at the door.** `from_dict` is
   where desk JSON becomes a plan and every route to storage goes through it;
   after that no consumer can see a float and the six readers are
   belt-and-braces. It **normalises and does not judge** — a value that
   cannot be read is left exactly as written, because `certify` and
   `_validate_plan` are the two that refuse and they need what the desk
   actually sent.
2. **`export` joins `RESERVED_KEYS`.** It was not on the list, so
   `_strategy_section` preferred a desk-supplied block **verbatim** over the
   section the app builds — shipping `1.0`, `[11.0, 9.0]` and `pitLap: 11.0`
   into the contract on the one branch where every reader this row added is
   bypassed. Two copies of one set of figures is §1a, and the app's copy is
   the one with the arithmetic behind it.
3. **`propose_strategy` was not a door.** `write_race_plan` goes through
   `from_dict`; this one stored whatever JSON arrived, so both of the above
   had a way round them on the tool whose docstring says it takes *"the JSON
   of a plan"*.
4. A box lap is 1-based — `Plan.pit_laps` is a stint's `end_lap` and
   `certify` refuses a 0-lap stint — so `minimum=1`, and `race_outcome` can
   no longer assert *"against a planned lap 0"* from a figure the app cannot
   produce.

### Row 1.7, critic pass 18 — `start_lap` was the field one to the left

**(A).** `stint_ends_on_lap` is `start_lap + laps - 1`, and `whole_numbers`
normalised `laps` and left `start_lap` as written — so the sentence that
motivated the door, *"George said 'the next 9.0-lap stint' with the hose in"*,
was **still true after the fix**, through the documented desk door on an
auto-approved plan: *"10.0 laps after the planned box"*, spoken. Enumerating
one more field would be the same shape a fourth time, so the count-shaped keys
are **declared** (`PLAN_COUNTS`, `STINT_COUNTS`) and held against what
`Plan.as_dict` actually emits — a field added to the plan cannot quietly skip
the door.

**And four of pass 17's six changes were unpinned**, found by mutation over
600 tests: `minimum=1` on both `pitLap` sites, the `isinstance(pit_laps,
list)` guard, and both `propose_strategy` guards all survived. The
`isinstance` one is the costly gap — `certify` never checks that type, so an
approved plan with `pit_laps: 11` raised `TypeError` and a dict raised
`KeyError`, taking **the whole export** down rather than one key. All four are
tested now, the MCP pair against the real stdio door.

### Row 1.7, critic pass 19 — the door was hardened and nobody asked what it stores

1. **(A), pre-existing.** `propose_strategy` **never stamped**.
   `write_strategy` does; `approve_stored_strategy` only certifies; and
   `start_race` arms straight off the row. So a proposed plan approved in the
   app had **no `start_lap`** — every stint then ends at `laps`, because
   `_apply_stint` reads `start_lap or 1`, so two stints of a three-stint plan
   share a box lap and `_box_now` fires **every lap to the flag**. That is the
   nine-box-calls defect `_with_start_laps` exists to prevent. No `context`
   either, so `arm` skips `planned.matches(actual)` and a plan for one circuit
   arms at another — §1a's named failure — and no `expects`, so every per-lap
   comparison reports nothing.
2. **(A)** A `start_lap` of `1.5` passed both doors *and the gate*: the door
   reads what it can and passes the rest through by design, and `certify`
   checked stint `laps` and **never looked at the start**. George said *"Box
   in 8.5 laps."* `certify` refuses it now, which is where a value the door
   could not read belongs.
3. Pass 18's *"all four are tested now"* was true of one site and one guard:
   the second `pitLap` reading and the `isinstance(payload, dict)` guard both
   survived mutation. Both pinned — the outcome's reading at the source, said
   plainly, because `_outcome` takes a store and a behavioural test there
   would be a fixture pretending to be a database.
4. The MCP advice was one answer for a set holding **three** ownerships:
   `write_strategy` refuses `export` too, so routing it there was wrong, and
   `unhandled`/`certificate` are recomputed wherever they arrive. Per key now.
   `validate`'s own message still said *"the handover's own — rename it"*
   about `export`, which is the app's.
5. `end_lap` was declared in `STINT_COUNTS` and is a `Stint` **property** —
   never stored, never read off a stored stint, so it was a key that could not
   be exercised.

Minor, each a claim wider than its code: *"every route to storage goes through
it"* is false — the app's own optimiser writes `Plan.as_dict` (ints by
construction) and `save_qualifying_plan` is a different surface, so what is
true is *"every plan a desk can write"*. *"Rename it"* was lifted from a set
with one ownership and is wrong for the five keys the handover consumes —
renaming a `playbook` strips George's bounds; the answer for those is
`write_strategy`. `export` was **dropped in silence** on the flat shape the
desk actually writes, so the desk's own arithmetic disappeared with no
message; it is kept on the plan and refused by name. And the null-is-bounded
argument quoted for `stops` does not transfer to `pitLap`, because `certify`
never reads `pit_laps` — carried, and said where it is.

### Row 1.7, critic pass 20 — the deliverable, and where the row actually went

**The last defect in the row's own deliverable, and it is the row's own named
failure.** `set_plan` is the only caller of `show_standing_orders` and is
driven by `_refresh_race_options` and `_poll_plan`, neither of which reads
`use_plan()`. So picking **No plan** left *"Standing orders — LUDO"* over
*"George may, on his own"* on the grid — while `start_race` passes
`approved = None`, the coordinator builds its playbook from `{}`, and `_may`
refuses every structural action. The driver told a rule is armed when it
cannot fire, one combo box away. Fixed, and the store cannot put it back:
`_poll_plan` re-runs `set_plan` every tick and the driver's choice wins.

**Where the row went, counted.** Of the findings in passes 12–20, about **8
are in the deliverable** — all of them in passes 12, 13 and 14 — and about
**26 are in the strategy-storage and normalisation layer**, which this row
reached only through the `stops: 5.0` chain that opened in pass 12.
**Passes 15–19 produced seventeen numbered findings and not one is in the
deliverable.** That layer is real work and the defects are real — an unstamped
`propose_strategy` arms a plan with no start laps, and ten stored plans carry
no `context` — but it is not row 1.7, and it is not converging.

**So the row closes here on its deliverable** — the standing orders, their
rendering, the Race page block and the nav change, all measured clean against
every plan on file — **and the storage layer is carried as its own item.**

### Carried out of row 1.7, for a row of its own

- **`approve_stored_strategy` does not stamp.** Fixed at both doors; the
  consumer that turns a candidate into the armed plan still does not, and
  `start_race` arms straight off the row. On the live DB **10 stored plans
  lack `context` and 13 lack `expects`**, and strategy 9 (Spa, approved)
  certifies clean with neither — so `arm(None, actual)` returns True at any
  circuit. `feedback_a_guard_at_each_consumer`, one consumer further on.
- **`stamp`'s `_with_start_laps` silently drops a non-dict stint**, and
  derives the remaining start laps over the survivors — the opposite of
  `whole_numbers`' stated rule that what cannot be read is passed through for
  `certify` to refuse. Now reachable from `propose_strategy` too.
- **`except ValueError` around `stamp`** returns `int()`'s own message
  (*"invalid literal for int() with base 10: 'ten'"*) and stores no candidate,
  where the parent stored one and let `certify` say *"every stint needs a
  positive whole number of laps"*.
- **`certify`'s start-lap refusal reports one constraint for three** (rule
  12): not whole, negative, and past `LAP_CEILING` all say *"needs a whole
  one"*. Its `minimum=1` is nearly dead, because `_with_start_laps` rewrites a
  falsy start to the running lap before it is reached.
- Three guards in that layer survive full-suite mutation, and
  `Handover.validate`'s new `export` branch is untested.

**Left in Phase 1:** 1.8 (driver board spec and screenshot), plus critic
5's carried questions (a misidentified board row resets the held-up window;
two locator misreads still cut the gauge series; the sector map's offset path
is untested). **Then Phases 2–4.**

### Row 1.8 — merged, and the caption that was left (11 Sep 2026)

**It was already in the tree.** `master` had been fast-forwarded to the
driver-board merge (`a9c348d`), so there was nothing to merge; the live tree
sits on `feat/measurement-store`, which is `master` plus fifteen car-state
commits. The board session's own critic round six (`f0af704`) had already
replaced the countdown's *"no plan"* with `NO_STOP_TO_COME` wherever
`has_plan` is set — the last stint of a real plan and a dropped stop both.
What was left of the note at line ~897 was the caption: every other surface
says *to the stop* and the countdown said *"laps to box"*. Renamed on the
block, the spec and the settings tooltip (`612217f`), and the `has_plan`
branch, which carried a fix and no test, is pinned. Suite before the batch:
4425 passed, 5 skipped.

**Critic pass 1 on row 1.8 — NOT AGREED, five majors, all one shape: the
fix reached the block it was aimed at and not the one beside it.** Driven
through real `RaceState`s into a real `DriverView`:

1. A **dropped stop** read `LAPS TO THE STOP -- / no stop still to come`
   beside `IN HAND TO THE STOP -- / the stop is late`, after *"No more stops
   on fuel"* — `laps_to_stop()` retires the stop, `past_box_lap` does not,
   and `fuel_in_hand_to_stop` asked the second. "Late" is the word that sends
   him in for fuel he does not need (Fuji). Now late only while
   `stop_still_needed`.
2. **On the box lap itself** the fuel block said "late" beside "box this
   lap" — the due-vs-late defect `laps_past_box`'s own comment records,
   one block along. New reason `STOP_IS_DUE`, *"the stop is this lap"*.
3. With **No plan** chosen the fuel block said *"no stop still to come"*
   beside a red −5.0 flag figure — a plan's answer, given where nobody
   planned. `_board_fuel` now says `NO_PLAN`, the box block's own word, now a
   shared constant.
4. **On the grid** the board is opened at arming and the state was a bare
   `DriverState()` until the green, so it said "no plan" under *"Armed:
   running to the approved plan"* — the carried §9a defect on a path the fix
   never reached. The armed board now builds the countdown off the same two
   expressions the running board uses (the stint is applied at construction)
   and says *"from the green"* for the fuel figures.
5. **`has_plan = False` survived every board file.** Pinned both ways off a
   real `_stints` list — and the default stub, which had a countdown and no
   plan, now carries the two-stint plan its own state describes.

And a minor that was not minor: `test_the_box_caption_names_the_set_going_on_
not_the_one_coming_off` built a `DriverView` with **no QApplication** and
aborted the process with 0xC0000409 when run alone — reproduced under
PowerShell, not only Git Bash. It passed in the suite only because an earlier
file had made an app. §7's own sentence: passes in a group, fails alone, is
shared state. Minor 6 (the in-box panel's "past the plan" against the running
board's "no stop still to come" after an unplanned stop) is left: they
describe the stop in progress and the stop still to come, which are different
facts.

### The strategy-storage row — build (11 Sep 2026)

The census first, read-only off the live DB: **10 plans lack `context` and 13
lack `expects`** (the carried figures hold); of those only **strategy 3**
(Yas Marina, no `expects`) and **strategy 9** (Spa, neither) are approved. No
stored plan lacks start laps, and every stored plan's start laps chain.

1. **Approval stamps.** `approve_stored_strategy` runs the row through
   `stamp` (context = the event *as it stands at approval*, which is the
   driver saying which race), refuses a context that names another race by
   `PlanContext.matches`' own words, certifies the stamped plan, and writes it
   back (`Store.update_strategy_plan`, one caller) before approving — so the
   row that reaches the grid is the row that was certified.
2. **The grid refuses a row without its contract** and does not stamp it
   there: a context taken off the event at the grid is the event checked
   against itself. `execution.contract_gaps` names every gap (rule 12) and the
   status says *"Approve a plan on the Strategy page"* — not *"approve it
   again"*, because the loaded cards list only rows carrying a handover, so an
   optimiser plan approved before stamping has no card to press. **This
   refuses strategies 3 and 9 on the grid** — both are past rounds.
3. **`_with_start_laps` keeps every stint where it was, as it was.** A
   non-dict stint stays in place; derivation stops at the first stint whose
   start or length cannot be read; a start of `0` is left for `certify`; no
   `int()` on anything. So `propose_strategy` now stores `"laps": "ten"` and
   `certify` refuses it by name — the `except ValueError` now carries only
   `stamp`'s own messages (a context or `expects` of the wrong shape).
4. **`certify`** refuses a non-dict stint *by position* (it used to certify
   over the survivors — the same drop, in the gate), a non-dict plan, and
   names each start-lap constraint on its own: not a lap number, not a whole
   lap, before lap 1, past any race. **And the starts must chain**: an
   overlap shares a box lap (the nine-box-calls shape), a gap leaves laps
   that belong to no stint.
5. **`Handover.validate` answers a reserved key by its owner**, the split
   `propose_strategy` already made: `export` the app builds, `unhandled` and
   `certificate` the app works out, and the handover's own three go *beside*
   the plan — not "rename it". The `export` branch is tested on both shapes.

**Mutation sweep, in a throwaway worktree at `827712b`:** 31 mutants across
`_with_start_laps`, `contract_gaps`, `stamp`, `certify`, `whole_numbers`,
`Handover.validate`, approval, the grid and the MCP door — **all 31 killed.**
The carried "three guards survive full-suite mutation" is closed.

**Critic pass 2 on the storage row — NOT AGREED, two majors.**

1. **The context check went into one approving door.** `write_strategy`
   approved on `certified` alone, so last round's file written against this
   event was approved, the good plan demoted to a candidate, and the grid
   then refused the foreign one with nothing to fall back on — exactly what
   the commit's own comment said the check was for.
   `execution.built_for_another_race` is now the one expression both doors
   ask; `write_strategy` stores a foreign plan as a candidate and says so.
2. **The chaining refusal missed the laps before stint 1.** A first stint
   on lap 5 certified; the page said *"box lap 10"* and George boxed on 14
   on a load sized for 10. Refused now — `adopt`'s mid-race tail is the only
   stint list that starts later, and it never passes the gate — and
   `pit_laps` must be the laps the stints box on (every stored plan agrees).

Minors, all fixed: an unrecorded layout read *"built for the None layout"*;
the start-lap early return is pinned directly; an unreadable approved plan
was told *"approval fills those in"*; the Race page showed strategies 3 and 9
as approved all week with no sign they will not arm (it says so now, in the
grid's own sentence); and the approval write-back left `certified: false` in
the row's evidence — it records its own certificate and what it stamped.

**And a defect the new tests found, not the critic:** `RaceScreen.set_plan`
called `.get` on every stint, so an approved row holding an unreadable one
raised on the Race page from `_poll_plan` every tick. It says the plan will
not arm instead, and draws none of the stints rather than the survivors.

**Critic pass 2 on row 1.8 — NOT AGREED, one major, and it predates the
row.** At the flag `phase` is FINISHED — neither running nor armed — so the
gate this row rewrote returned a bare state and the board went blank and
said *"no plan"*; the finished branch that keeps position and tyres was
reachable only from a stub that was running AND finished, which production
never is. Let through now, and tested in production's shape. Minors: the
grid's last call is pinned; `_board_fuel`'s `has_plan` is required; the grid
countdown carries no "from the green" caveat through a late green detection
(Monza detected at lap 2) — left, recorded here.

**Critic pass 3 on row 1.8 — AGREED at `e662626`.** Driven through a real
`RaceCoordinator` on all three finish paths (last crossing, `RACE_FINISHED`,
a timed race's clock): each board reads `FLAG / race over` with position,
compound and last call; the next race's grid shows none of the last one's
result (rule 11); all three mutations of the new gate caught. Minors: both
fuel blocks read "not measured" at the flag, which is false (fixed — "race
over"); a re-arm refused before `self.race` is replaced left the previous
race's result on the new grid (fixed — the board closes on entry to
`start_race` when the race it shows is over); and a set fitted on a stop
whose pit exit arrives after the flag leaves the finished board naming the
set that came off — post-race only, left.

### The carried live-call items — build (11 Sep 2026)

**The biggest was not on the list.** Scoping "two sentence families
live-synthesise", a read-only probe of 36 box-call shapes found **15 missing
the voice pack: every box call carrying a tyre DECISION** ("RS on.", "No
tyres.", "Tyres on.") **and every overdue one.** `_tyre_word` has said those
words since the Phase 0.2 decision landed, and the manifest's states were
never extended to them, so every stop with a `tyres` field has been a
synthesis pause on the call he acts on. Worse, the overdue call with a tyre
word was not even counted as a miss: the peel stopped at "Box this lap.",
the rest landed as one clause holding two numbers, and `uncovered_reason`
filed it as a *declared* gap — a decision nobody made. The tyre words are
now their own family taken from `_tyre_word` itself (codes only — the plan
stores the code), peelable on their own; every overdue shape is declared,
with both of its tails; and the GAP refusals ("No gap read yet", and the new
"Nothing read ahead/behind yet") are fixed lines. Pack: 658 → 678 clips,
under the 700 budget. **The rendered pack on disk holds 580 — it was 78
behind before this — so it needs `tools/render_voice_pack.py`.**

**GAP answers one car, in the board's words.** It was a two-row table, and
worse than the note said: the voice said "closing" above **0.1 s a lap with
no lap count**, while the board says "steady" below `TREND_WORTH_SAYING_S`
(0.8, set from the gap's own random walk) or under five laps — so the ear
could say "closing 0.3 seconds a lap" about a car the eye called steady.
`gaps.trend_words` is now the one expression both read, per side ("you're
catching him" / "he's catching you"), and the snapshot carries the lap count
it used to drop. The question is read for its side (`intents.GAP_SIDES`,
held against every GAP phrase — "how far ahead am I" is the car BEHIND); a
question naming neither gets the nearer car, and a side asked for but not
read is refused rather than answered with the other car. **"Steady" for too
few laps is the board's decision, not reversed**:
`test_too_few_consecutive_laps_is_steady_rather_than_a_slope` pins it, and
the voice took the same meaning rather than a second one.

**Standing orders: the desk's prose is capped, the contract is not.** Every
line over 200 characters on strategy 15 is a *Resting on* assumption (2,262
of 3,432). `Order.resting` marks them; the one renderer both screens use cuts
them at a word inside 160 characters with the whole line on the tooltip — so
the Strategy card and the Race page still say the same words — and never
touches a rule, because a rule cut short is one he cannot read in full.

**Two carried items are not changed, and why.** The `UNDERCUT` reason's
three clauses stay: the driver asked for the tow figures in that call by
name (7 Sep), and §9a already says they stay until he says otherwise. The
cancelled-stop latch is its own batch: every plan on file grants `fuel_long`
recost or report, never `drop_stop`, so `stop_still_needed` is always True
and the latch cannot fire on any plan on file today — below a gap that fires
on every stop.

**Critic pass 3 on the storage row — NOT AGREED, a BLOCKER in pass 2's own
fix.** The context check pass 2 added put an app crash on the Approve
button: `stamp` checked the context's keys and not its values, so a desk
typo - `"race_laps": "twenty"`, `"race_minutes": "50"` - stored clean and
`int()` raised inside `built_for_another_race`, uncaught (PyQt aborts after
the excepthook); `write_strategy` returned `int()`'s own message, the exact
thing item 3 of this row removed. `execution._context_problem` now reads the
values once, in the one shape check every door and the grid ask, and refuses
by field name; a null distance is refused rather than read as "0 laps"
(rule 3). **MAJOR:** the in-week warning was set when true and never taken
down, so after he re-approved the plan the Race page still said it would not
arm - it is taken down now, and only that warning. Minors fixed: the week's
warning names a plan for another race too (the grid's own `matches` words)
and says nothing when he has chosen not to use the plan; `write_strategy`
reports a foreign plan under `builtForAnotherRace`, so `certified: True`
and the certificate's empty refusals no longer sit beside a refusal in one
reply; the `pit_laps` no-start-laps guard is pinned.

**Critic pass 4 on the storage row — NOT AGREED, one major: the stale
message came back the likelier way.** Pass 3's take-down matched only the
week's own prefix, so after a failed Start the page carried the grid's
*"Plan refused: It was approved without…"*, and re-approving - exactly what
it told him to do - left it up. The grid now remembers the refusal it wrote,
word for word, and the refresh takes down that and the week's warning and
nothing else: a refusal by `certify` is still true after a refresh, and a
test now pins that another status is left alone (that mutant had survived).
Minors fixed: `stamp` checks the context it builds from the event, so an
event with no distance is refused at approval rather than stamped and then
refused by its own next approval; choosing "No plan" re-asks, so the warning
does not stand over a plan he has set aside; `_context_problem` refuses an
empty car or track, and a duration that is true, infinite or zero. Replayed
by the critic read-only: no stored or approved row on the live DB is newly
refused, and no context it could build still reaches a raise.

**Critic pass 1 on the voice batch — NOT AGREED, and the probe that scoped
it had the same blind spot as its test.** Every box state in the sweep
carried no fuel data, and no race with a measured burn makes that call: with
a burn it says *"Box this lap. RS on. The regulations need a stop. Fuel to
24 litres - 7 laps after the box."*, the reason sentences were clips but not
peelable, the fuel sentence carries two numbers, and the whole call was
filed as a declared gap - 588 box lines declared and 306 missing in the
critic's sweep, on the call he acts on at every stop. And the declared-gap
test accepted any "numbers left" line whatever kind of call it was. Now:
`reason_lines` (the calls' own reason sentences) are peelable;
`fuel_sentence_fragments`, taken from `_fuel_instruction` over every basis,
let `_split_on_numbers` play a sentence of several numbers when every word
between them is declared; the sweep carries fuel-bearing box states; and a
box call may never be declared (the undercut is the named exception - its
reason carries the rival's name, and the engine plays a line from the pack
only whole). **Two defects found under the fix:** `number_word(100)` indexed
past `TENS_WORDS`, so "Fuel to 100 litres" - a full tank - could never play;
and a last-lap stop said *"1 laps after the box."* Minors fixed: "steady" is
no longer said from no trend at all (a slope through too few laps still is
- the board's pinned word); a side named in other words ("what's the gap
behind") is read; a gap of zero or less is not a reading, and one under a
twentieth is said "within a tenth". Left and recorded: full compound names
in the "X on." form (the plan stores codes), answered GAP lines are live
(they carry a name), and a cut assumption can lose a trailing qualifier
behind its "…" (the whole line is on the tooltip on the Strategy page).

**Critic pass 2 on the voice batch — NOT AGREED, one major, and it was my
own fix's.** The box call a real race makes plays now (the critic's sweep
fell from 306 misses and 588 declared to none outside full compound names).
But the singular this batch gave the fill sentence - *"1 lap after the box."*,
*"1 lap to the flag."* - was never in the pack, because no fuel-bearing state
left a single lap; so a one-lap fill, a late splash, filed its whole box call
as a declared gap. One-lap bases are swept now. Minors fixed: the side-word
fallback read "what's the gap **back** to the car in **front**" as the car
behind, because "behind"/"back" were checked first - both sides named is no
side now, and "back" is not a side; and `_split_on_numbers` accepted a
sentence of numbers alone. **Left, on the budget, and said so:** a full
compound name in "X on." (about 11 clips) and the unnamed GAP answer (about
5) cannot both fit under 700; the plan stores codes, and `certify` refuses a
name wherever the event declares its compounds, so the names are the one
left. The undercut's instruction half stays live - the voice engine plays a
line from the pack only whole, and its reason carries a rival's name.

### The cancelled-stop latch — build (11 Sep 2026)

Rule 10's two guards, both. **The retirement latches when he is told** —
`record` on a `STOPS_OFF` that really retired the stop; with the drop not
granted he hears the report form, the stop stands, and nothing latches — and
`laps_to_stop()` returns None while latched, so one lap's burn moving back
across the margin no longer makes the countdown vanish and return. **Only a
sustained reversal retires the latch**: `STOP_BACK_LAPS` (2) consecutive laps
on which the fuel does not reach, counted once a lap in `_on_lap` after that
lap's burn is installed. Then it is **said** — the new DECISION `STOP_BACK`,
*"The stop is back on."* with the stop's own reason from
`_why_the_stop_stands` (rule 12) and no countdown in it, ranked beside the
call it reverses — because a countdown reappearing in silence after "No more
stops on fuel" is the contradiction `STOPS_OFF` was written to prevent. Both
the retirement and the reinstatement are logged (the accepts, not only the
refusals). The latch belongs to the stop it retired: `_apply_stint` clears it
across a stop taken, a re-plan adopted and construction.

**Critic pass 1 on the latch — NOT AGREED, a BLOCKER: it moved the flicker
rather than closing it.** Driven through real races with `drop_stop`
granted: taking the stop off needed one lap and putting it back needed two,
so a burn going short, short, long cycled *"The stop is back on"* / *"No more
stops on fuel"* **eight times in ten laps**, and push-to-talk flipped between
"Box in 5 laps" and "No stop planned" with them — the row 1.10 flicker,
spoken. Three majors under it: a stop coming back on its box lap was called
a lap late (`STOP_BACK` outranked `BOX_NOW`) and then *"1 lap overdue"*
counted from the plan; **four surfaces bypassed the latch** because they read
`stop_still_needed` directly — the colour tier said "3 laps to the stop"
with the countdown blank (rule 13); and `_apply_stint` cleared the latch but
left `stops_off_said`, so after a re-plan the new stop flickered in silence.
And the tests only ever called `note_stop_need()` by hand.

**Redesigned, not patched.** The fuel's answer about the stop is now HELD in
`_stop_needed_on_fuel` — the one predicate every consumer asks — and moves
only in `note_stop_need`, once a lap, after `STOP_FLIP_LAPS` (2) consecutive
laps of contrary arithmetic **in either direction**; the raw arithmetic lives
in one private function only the lap hook reads. Holding the fuel answer
rather than the grant keeps the report form working where the drop is not
granted. A stop needed again on or after its box lap becomes the lap in
progress, so `STOP_BACK` says *"The stop is back on. Box this lap."* with the
tyre word, and "overdue" counts from then. `_apply_stint` resets all of it —
the hold, the count, `stops_off_said`, both calls' `said` entries — and logs
it. `record` no longer latches, so a briefing that silences `STOPS_OFF`
cannot leave the stop unheld (minor 8). The race-driven tests go through
`RaceCoordinator.handle`. Left and recorded: a timed race's soft distance can
still move the arithmetic on its own; the hysteresis damps it, and "Fuel
won't reach the flag." is unhedged there as it was before (minor 7).

**Critic pass 3 on the voice batch — AGREED at `0cedbfe`.** Every box line
in code form plays, the one-lap fills in both frames, a fill to a hundred
litres, and every `STOP_BACK` shape batch 4b made; the only misses are the
full-name "X on." family left on the budget, and the critic confirmed the
budget is a constraint, not a choice (both leftovers take it to about 703).
Minors, all labelled rather than silent: "am I" overrides a side word he
named - kept, because "am I far behind" names the car ahead through the
word "behind", which is the inversion the rule exists for; the phrase table
wins over the both-sides guard in compound questions; "the leader ahead" is
answered with the car directly ahead, which the answer names. **The pack is
rendered**, read off the tool's own summary: `en_GB-alan-medium`, 112 clips
rendered and 575 unchanged, 687 on disk against 687 declared. Twelve older
wavs are no longer in the manifest; the tool names them and deletes nothing,
and they are left - removing files is the driver's call.

### Phase 2 — rows 2.1 and 2.2, first batch (11 Sep 2026)

**2.1 — the experiment ledger lives in `brain/`, and the app writes nothing
about it.** `brain/ledger/<car>-<circuit>.md` for the four circuits on file,
plus a README: **115 rows** at seeding, **118 after two critic passes** (Daytona 37,
Mount Panorama 11, Sardegna 60, Deep Forest 10), every one a key, a direction and a delta in percentage points of
slider range, every block parsing to its 13 columns. Seeded by a read-only
extraction from the car-state files, which I read in full before a line of
it went in, and built by slicing that extract rather than retyping it - a
line-count guard in the build stopped one replacement that would have
shifted every later slice by a line. **§1a turned out to cover more than the
plan's wording:** the extraction kept no `from`/`to` in any row, but its
prose quoted positions as percentages (*"50 → 70 → 90 %"*, *"dc 20/20"*,
*"a slider value at 73.3 %"*), and a position in percent is a setting read
back through the range record - ten were stripped, each asserted. Items with
no slider range (gear ratios, shift points, ECU, ballast) are cited by
location and restated nowhere. **Forty contradictions are surfaced in the
files, not averaged**; two matter beyond housekeeping and are for Ludo and
the driver: Bathurst's `lsd_a` is justified by a doctrine band its value is
outside, on a pre-1.71 scale; and a Daytona `lsd_b` "it worked" rests on 5
laps against the same file's own 22-lap requirement. **A third, as first
written here, was wrong** (critic 5): "the Shelby's car-state percentages
fit neither record". They fit the v1.71 record in `pitcrew.db`, verified
23 Aug, on every ranged key checked - it is the register that is stale, and
its LSD spans answer the register's own class-independence question.

`setup_changes` is **read and written by nothing** (206 rows to session 119,
last written 4 Sep, carrying `from_value`/`to_value`) - `CLAUDE.md` §1a now
says so and names the ledger as its replacement, and `learning-loop.md`'s
routing row, which still sent a setup change there "automatically", points
at the ledger. `SKILL.md` opens the ledger first in `refine`, `race plan`
and `debrief`.

**2.2 — `refine` runs the method.** After rank zero and the ledger: a
baseline counted by the tool's own clean-lap definition (a disagreeing count
is the finding); one change written as an experiment *before the run* - key,
direction, pp, instrument and its measured floor, **a no-change control
measuring the drift between sessions**, prediction and complementary
falsifier; the verdict on the same instrument against that drift; and an
A-B-A return leg where a run is cheap. Two evals (12 and 13) hold it to the
two failures the row names - Sardegna's +0.633 g against a no-change +0.411,
and Deep Forest's 0-and-1 against 4-and-5 clean laps - **written, not yet
run through an eval harness.**

**Critic 5 on 2.1-2.2: NOT AGREED at `f354419`, fixed in the next commit.**
Three blockers, all §1a leaks the first strip missed: a Daytona source cell
quoting the untried `de` setting; Sardegna's "aero to the midpoint" beside
the front share before and after, which together rebuild every aero
setting; and the Shelby's `bb` trim written as a value. Majors: "back to
zero" on toe (with the steps it rebuilds the setting); "no travel left
upward" on the Shelby (the ceiling, reworded); four rows refuted beside
directions their files do not refute (Daytona `lsd_a` +12; the `arb_r`
Bus Stop risk that did not happen; both Daytona `df` steps; Sardegna `arb_r`
+22.2, whose size is refuted and whose direction is confirmed one row on);
D5 scored confirmed on 0 of 5 laps against its own file's ~22 (open now);
D9 carrying one row where rule 1 needs two (his report is its own row); and
S1. **S1 was mine and wrong both ways** - left "not resolvable from files"
in the ledger and called "fits neither" above. Read read-only,
`range_records` holds the Shelby at v1.71, verified 23 Aug, and every
car-state percentage checked reproduces from it; the register is the stale
file. Its LSD spans (0-30 / 0-100 / 0-100) are the answer the register's
own class-independence test was waiting for - flagged for Ludo, not edited,
because the register is not this row's. Minors: `refine` step 6 had lost
the three-clean-laps minimum (restored); eval 12 denied a change the file
confirms on his report (it now keeps the change on the report, refuses only
the number, and the prompt carries a report); eval 13 tested a `refine`
step with a `debrief` prompt (now a refine prompt, with "no complaints" in
it); §1a said three things stayed above four bullets; the Daytona `bb` trim
had no row. **117 rows**, every one 13 columns; a leak scan over the diff
finds measurements and deltas only.

**2.3 - platform or trim, decided before step 6.** `SKILL.md` `refine`
now says which a complaint is before a change is written: platform is ride
height, natural frequency, compression damping and downforce as one coupled
set, moved together and with ride height last; trim is one balance slider.
Eval 14 holds it.

**Critic 5, pass 2 (on `8937de0`): NOT AGREED, four majors, fixed.**
(1) The new debrief order - "his report first, before any data" - flatly
contradicted the spine's step 3, "Read the telemetry. All of it. Before
asking him anything", and every mode runs the spine in order. **The answer
was the merge, not either side:** the driver's own role instruction (23 Aug)
says the engineer reads the telemetry before *asking him to observe
anything* and that a question should *buy something the data cannot*; plan
row 2.5 wants his report *before data*. Those are two acts. His unprompted
account is taken before he is shown any numbers, because numbers shown first
lead him; that asks him nothing, so every question still follows the
telemetry. Step 1 says so, and says the spine holds. (2) `SKILL.md` described
a `tools/debrief.py` that did not exist at that commit - true; it lands with
2.5 below. (3) "§9a not touched" - true of `8937de0`; the S1 correction and
this record went in `85522eb`. (4) **A Daytona row scored a falsified
threshold as confirmed.** Pass 1 had asked for the `lsd_a` +12 row to carry
the file's axis verdict; written into the one row, it now claimed the index
rose above 0.0089 when it read 0.00748. Split the D6 way: the threshold
refuted (its direction cell says only the threshold is), the axis confirmed.
Minors fixed: `wear_rates.carry_into_knowledge` writes, so it is listed with
the writers; "write nothing else" is "write no database row" (`analyse_m0`
and `draw_track_map` write files); eval 13's Rev B is FEED-confirmed, not
screen-confirmed; R12's session cell and its uncertainty, which is the
0.0528 reference's own (±0.0056 over 5-lap runs), not s153's (±0.0006); and
**the lap-one conflict is now written into both files** - `race-planner.md`
puts lap one's cost in the pre-race brief, row 2.11 says never; both say
never live; which governs the brief is the driver's to settle. 118 rows;
the leak scan over the new diff finds nothing.

**2.5 and 2.11 - `tools/debrief.py` runs the whole list.** In the protocol's
order: his report (`--report`); the open rows of this car × circuit's
ledger, matched word-for-word through `slugify` because the ledger's names
are not the event's ("Huracán GT3 '15" inside "Lamborghini Huracán GT3
'15"); the practice session; where a named change landed (`--before` /
`--after`, `where_the_change_landed`'s own functions and its compound
confound, now one expression); coast share and upshift per session; **the
driver as a variable** (`analysis/driver_trends.py`: incidents over the laps
`find_incidents` could judge - a session it could not judge has no count,
not zero; lap one against lap five on, races only; the counted set's spread;
each with its n, in the debrief and nowhere else); George's calls against
the verdict filed on each (a missing verdict counted, never read as acted);
the race against the plan it ran, through the export's own
`audit_line_from_laps` and `pit_loss.measure`; the radio. `mark_incidents`
takes the accessor through, so the trends mark laps through the export's own
expression. `--db` points it at a copy. **Run on a backup of the archive,
never the live file, and three lines were wrong on real data before any
critic saw them:** a measured pit loss called "declared" (Daytona's 72.28 s
is a measurement); a stop with no fill printed as an "ex-fuel" figure when
nothing was taken off - a ceiling, by `pit_loss.best`'s own account; and a
clean-lap count with no definition beside it, where a count that differs
from another file's is the finding. All three are pinned.

**2.10** is in `8937de0` above; critic 5 checked all 51 tools and found no
reader that writes.

**Critic 5, pass 4 (on `91ee5b6`): AGREED - the Phase 2 docs are done.** Its
one minor - the plan row asks for four phases per corner, `driver-model.md`
names three, and `SKILL.md` had quietly used the three - is written into the
open note: which the grid uses is part of the question the driver settles.

**Critic 6 on 2.5 and 2.11 (`5137ea5`): NOT AGREED, two blockers - and the
second is a production defect the debrief exposed, not one it caused.**

1. **Races with incidents printed "incidents 0".** Laps the app had already
   stored as incidents arrive struck, and `find_incidents` skips struck laps,
   so none of the 20 stored race-incident laps on file was counted - the
   Sardegna grass spin among them. `driver_trends` now counts every lap
   stored as `incident` inside the runs `find_incidents` judges, and names
   one outside such a run. **One lap is not tagged `incident` and is not
   counted:** Deep Forest s135's lap 2 is struck in his own words ("crash ...
   the driver reported damage"), which the export files as manual. Counting
   it would make "incidents" mean two things; printing a bare 0 beside it
   would hide his report. It is quoted on the line instead - the
   disagreement shown, not averaged.
2. **`pit_loss.measure` read a 0.0 as "no fill".** It took the fill from the
   in-lap and fell back to the out-lap only on a None; Daytona's in-lap
   stores 0.0 and its out-lap the 49 L, so the fuel term was dropped. The
   same function runs at every flag (`_record_pit_loss`), so **Daytona's
   stored "measured" pit loss, 72.28 s, and Bathurst's, 87.8 s, each have
   49-65 s of refuelling inside them** - the real ex-fuel figures are about
   23.2 and 23.1 s. Both rows are summed now, and `PitLoss.fill_seen_l`
   keeps "no fill on file", "a fill with no rate to take it off" and "under
   2 L" apart. **The two stored figures are wrong in the live database and
   correcting them is a write to it - it waits for the driver's yes.**
   Bathurst races on 14 Sep; a plan built on 88 s a stop avoids stopping.

Majors, all fixed: a stop filed on two pit rows (Fuji) is one stop;
`--sessions` filters the radio; lap one names its start type, is refused
where lap one was a pit lap, and a rehearsal says it is one; and the audit's
fixed sentence about three old gauge readings - printed word for word at
every event as that race's finding - is dropped from the debrief, with the
export side filed as its own task. Minors: no spread over fewer than three
laps or over laps nobody screened; "declared" is said to be possibly the
app's 20 s default; a stop compared with its own stored figure says so; the
laps on file are set against the race's length. Four surviving mutants are
pinned (exactly three clean laps; an incident lap inside the lap-one
reference; the trend line's None branch; a ledger header with an empty
side). Re-run on the backup copy: Daytona s143 reads "2 in 17 judged laps"
and its stop "23.2 s ex-fuel against the event's 72.28 s (measured - from
this very stop, so this compares it with itself)".

**2.8, part 1 - the checkable half of doctrine hygiene.** `11` states what
`range_records` holds, read read-only: all four cars on v1.71, verified; the
LSD at 0-30 / 0-100 / 0-100 on every one, the Shelby included - the
register's own "outcome 1", so **the rule to issue LSD in absolutes is
retired**, where it is written (`11`, `17`, `refusals.md`, `SKILL.md`,
`00-INDEX.md`); the Shelby's natural frequency and front downforce moved on
v1.71; the JSON blocks marked as history nothing reads; the Car screen named
as how a car is added. `09`'s paste block and `mechanic.md`'s paste block and
`SetupSheet.validate()` - an input and a class §1a removed - are retired. The
three deleted tools are marked as removed where they are cited. The shift-
table example in `SKILL.md` named a car not on file and a circuit key the
app never builds, so a table issued from it beeped nowhere; it now uses the
store's own spellings. Eval 3 no longer expects the deleted question gate.
`test_brain_reconciliation` section E pins all of it - and on its first run
caught one more citation whose "since removed" note had wrapped onto the
next line. **Part 2 is content, and needs Ludo's care:** `02` §10's tags,
the 1.71 pass on `05`, the Shelby profile in `07`, and setup values still
restated outside `brain/car-state/` in `11`.

**Critic 5 on 2.8 part 1 (`acd9da7`): NOT AGREED, two majors, fixed.** (1)
**The retired rule was still in force where sheets are issued**: both
current car-state sheets headed their differential block "ABSOLUTES, not
percentages ... the register has not been re-read", both ledgers quoted it,
and `test_e2` passed because it matched only the two phrasings I had
rewritten - **a test checking fewer phrasings than the rule was written in
passes without checking the places that matter.** Both headers are retired
where they stand; the test now matches every phrasing the rule was written
in, and on its first run found two more (the archived Red Bull Ring and Deep
Forest sheets - the Deep Forest car-state sends its reader to the second, so
both are annotated, not exempted). (2) **The register's "CURRENT" RSR block
contradicted the database**: dated 21 Aug with `lsd_b` 0-99, where the
record, updated 5 Sep, reads 0-100; the file still said three cars were
read, twice told the reader to re-read the RSR's ceiling, and defined
outcome 1 with the old 99. The block is marked superseded by the 5 Sep
record and the four lines are closed. Minors fixed: the ledger README and the
Sardegna ledger's R17 carried the 99 (R17 resolved); my own edit had put a
v1.71 floor beside a v1.70 percentage (now labelled v1.70); `08`'s and `04`'s
"until `11` is re-read" gates are marked met; `13` called `SetupSheet.gears`
"verified end to end", and `test_e1` now catches a live `SetupSheet` as well
as a dead tool - on its first run, also my own "`SetupSheet` ... went with"
in `mechanic.md`, which did not say removed. 118 ledger rows, all 13
columns.

**Critic 5, pass 2 on 2.8 part 1 (`afc0d5d`): NOT AGREED - and the lesson
is in how the fixes were being made.** The retired LSD rule was still
binding in the `gt7-brain` skill ("Express LSD in absolutes until then"),
which loads on every setup question and which the test did not scan; and
`00-INDEX.md` still named the retired artifact's range library, with `11`
as its persistence layer. **Two passes running, each fix had covered only
the phrasings its critic named.** So this pass began with a sweep of every
skill and every brain file for any line pairing LSD with "absolute", any
"ABSOLUTES", and any "until ... re-read" gate, sorted into live and history,
and fixed the live ones at once: the `gt7-brain` rule, `00-INDEX`'s gate
and range-library paragraphs, `02`'s gate, `11`'s two present-tense 0-99
lines, RECONCILIATION D3, and two more archived differential headers.
`test_e2` now scans every skill, reads paragraphs rather than lines (a rule
and the note retiring it are often a wrapped line apart), and carries every
phrasing the sweep found - **and it was shown to fail on the unpatched
files, flagging all six live places, before it was trusted to pass.**

**Critic 5, pass 3 on 2.8 part 1 (`79c964d`): AGREED - 2.8 part 1 is
done.** Its own sweep, wider than the test and including folders the test
does not scan, found no live copy of the retired rule; it agreed with every
line I had judged history, and named `16`'s "the app's range library
inherits `11`'s numbers" as the one borderline case - a dated impact table,
so history. Its three minors were each a way `test_e2` could still pass a
live rule, and all three are closed: the retirement words are word-bounded
("unresolved" is not "resolved"), "met" counts only as "gate met" ("not met"
is not a retirement), and a table row or list item is its own block, so one
retired row no longer clears a whole table. **The stricter test at once
found a live one the looser had hidden**: the Red Bull Ring sheet's "the
register has not been re-read since 1.71", passed because the same item said
"the axis is unresolved". Annotated there - the scale reason retired, the
driver-report reason beside it standing. The test was also shown on
synthetic files to flag all three of the minors' cases and to pass a
properly retired rule.

**Critic 6, pass 2 on 2.5/2.11 (`0958a02`): NOT AGREED, two majors, fixed.**
(1) **My Fuji fix went the wrong way**: "[6, 14]" put the out-lap in stint 1
and had him box a lap late; he boxed on lap 5. A stop now closes on its
first pit row and the out-lap opens the next stint - Fuji "[5, 15]",
Daytona still "[12, 8]". (2) **"Measured - compares it with itself" told
him nothing**: Daytona's stored 72.28 s is the s143 stop's *total*, fill
inside, stored as the ex-fuel figure. The event's figure is now matched
against every race session's stops, and a total with a fill in it is
called that - "about 49 s high; the correction waits for the driver's
yes" - and the earlier Daytona race is told which session it came from.
Minors: a hand strike is quoted by the export's own rule (`_driver_note`),
not the app's placeholder, and on its session's row; a stored incident on
a pit lap is named; "the app's 20 s default" only for a figure of 20; a
lap one stored as an incident says its cost includes it. **Its mutation
sweep left eight untested branches; each has a test now** - the two
consistency guards separately, the radio filter through a fake store, the
stored pit lap, and the rehearsal label, wear strip and race length as pure
helpers.

**Critic 6, pass 3 on 2.5/2.11 (`79c964d`): NOT AGREED, one major, fixed.**
Every fix held on every event in the full debrief - Fuji "[5, 15]" agreeing
with its own "stop on lap 5", Daytona and Bathurst each naming the stop
their stored figure came from - but `--sessions` brought the pass-2 defect
back: the stops the figure is matched against were built from the filtered
runs, so `debrief.py 10 --sessions 127` called a figure with 49 L of fill
inside it "measured". They come from every race run on the event now, and
the filter chooses only what is printed; a fake-store test filters to the
earlier race and still has it name the session 143 stop. Its five surviving
mutants are pinned: a figure that is this stop's own ex-fuel (the path every
corrected figure will take); "compares it with itself" never attached to
another session's stop; lap one stored as an incident; his words under his
own row (`split_notes`, a pure helper now); and the full-run stop list.

**2.6 - every stop carries its tyres decision.** `Handover.validate` refuses
a plan whose stints after the first carry no `tyres` (absent or null): the
box call otherwise names the compound as a bare "RS." - "fit RS" under a
helmet - and only 4 of 64 stored stints ever carried the decision. Stint 1
is exempt; a one-stint race has no stop. `validate` has two callers,
`write_strategy` and the CLI - not the in-app approve, not the arm - so a plan
already stored arms exactly as before. `race-planner.md` says so, and names
the deliverable as three things from Suzuka on: the plan with its tyres
decisions, the playbook, and the engineering sheet (every `race_knowledge`
field, or a line saying why not). The rule failed 21 tests, built by five fixture
factories that made a stop with no decision; each factory was given one,
and none was loosened.

**The critic on 2.6 (`aad9ae3`): NOT AGREED - the guard was right and the
row's promise was not.** Its blocker was on the radio: the box call said
"Box this lap. No tyres." and "what tyres?" answered "RS." - under a
helmet, "fit RS" (rule 13). The snapshot had no `nextTyres`; it has now,
and BOX_WHAT answers in the box call's three forms ("No tyres.", "RM on.",
"RM.") while the plan summary says "no tyres" rather than "onto RM", both
declared to the pack. Its majors: `propose_strategy` was a third door with
no check - one `stint_tyre_problems` now answers for all three, and adds
that a fuel-only stop may not change compound; `certify` priced a
`tyres: false` stop as a fresh set, so a stated fuel-only 10 + 10 certified
past a 17-lap cliff - laps on one set are summed across it now, read
through the coordinator's own `_tri`; a mid-race re-plan (`adopt`) dropped
the decision, so "No tyres." became "RS." after he accepted - it is carried,
and a changed compound becomes a set going on; and **the app's own optimiser
never wrote the decision** - it prices every stop as a fresh set and now
says so. **Bathurst's approved plan (strategy 30, event 14) came from the
optimiser before this and carries no decision: its box call will say "RS."
until it is rebuilt and re-approved** - a driver's act on the Strategy
page. Minors: the refusal reads "plan refused", not "playbook refused"; the
old "true, false or absent" message no longer says absent is allowed; the
fixture count above says what was counted.

**Critic 6, pass 4 on 2.5/2.11 (`90a720e`): AGREED - the debrief rows are
done.** `--sessions 127` names the session 143 stop word for word as the
unfiltered run does; every event 1-14 runs without a crash or a write after
`Store()`. Its minor: the one line in `main` that feeds the pass-3 fix was
run by nothing, so two mutants on it survived - `main` is driven with
`--sessions` now, and must score the filtered run against every run.

**The voice pack lost nine lines to the latch, with nothing red (`f446334`).**
After `85522eb` an unjudged stop is the plan's and stands, so the manifest's
bare states for `_stops_off` and the ungranted drop never reached either
branch: "You're fuelled to the flag.", its litres, and the seven "not
granted" lines fell out (687 -> 678 clips). The coverage test checks the
manifest's own examples, so the generator and the check went blind
together. The states now say the fuel has retired the stop; the nine are
pinned by name, and a race judged for `STOP_FLIP_LAPS` laps is driven
through `next_call`, granted and not, and must play from the pack.

**The critic on 2.6, pass 2 (`90a720e`): NOT AGREED - one blocker, one
major, fixed.** Blocker: `tyres: true` with no compound - the box call said
"Tyres on." and "what tyres?" answered "No tyre change planned.", the
opposite instruction on the same stop. It answers "Tyres on." and the plan
summary says "tyres on". Major: `adopt` carried decisions by position, so a
re-plan that added a stop moved a lap-14 "No tyres." onto a new lap-8 stop
and left the added stop undecided. The re-planner's offer carries its own
decisions now (`stint_tyres`: every stop it priced is a fresh set) and they
win; the positional carry is left only for callers that priced nothing.
Minors, all fixed: the Race page line reads "RS → RS (no tyres)" and both
stint bars label a fuel-only stint NO TYRES; the grid brief says "No tyres
at the stop - fuel only." (three fixed sentences, rendered); and **Bathurst's
strategy 30 is flagged by the app now** - `stint_tyre_problems` is asked at
approval and by `_why_it_will_not_arm`, so the Race page says in the week
that it will not arm, and it cannot be re-approved without a decision.
Its note that each new branch was killed by one test only is answered with
a second test on the radio, `adopt` and the gate.

**2.8, part 2 - the content half of doctrine hygiene.** Every claim is taken
from a ledger row, a car-state file or a read-only count, and says which.
- **`05`, the 1.71 pass.** A banner names three kinds of line that no longer
  hold. First, the ~40 per-circuit LSD bands are on the v1.70 5-60 scale: a
  direction only, issued in percent of range. Second, "the undercut is
  strong" was said at ten circuits; every one is re-flagged (`CLAUDE.md`
  §5.4, plus the one in-house measurement: a 1.41 s fresh-tyre out-lap).
  Third, the wear figures and severity grades are refuted where tested. The
  Deep Forest entry is rewritten from what was measured: the front-right at
  0.66 %/km, a 30-lap stint at 2x (about four times the reference, AS4),
  gentler per km than RBR's grade 3, and the tyre did not bind in the race.
  Its pit loss is **not** measured (the event carries 20 s with no source);
  what was measured is standing time (9.9 s of surplus fuel against an 8 s
  gap) and the 1.41 s out-lap. Two archived sheets that said the same about
  the undercut are annotated as history.
- **`02` §10, tagged.** Rows are [COMMUNITY] unless tagged. Tags from the
  ledgers: [IN-HOUSE ✅] on rearward brake balance (RSR, Sardegna), a stiffer
  rear bar (Huracán, Daytona and RSR, Sardegna), front wing (RSR) and LSD
  braking up for entry stability (Huracán). [CONTESTED] on §10.5's #1:
  lowering LSD acceleration was refuted on the v1.71 Huracán and raising it
  confirmed, so the section's "most validated entry" now has an in-house
  result against it. Also [CONTESTED] on reduced rake, softer compression at
  the kerb (the driver and the instrument disagree, both kept) and "fronts
  wear first" (the RSR's worst wheel is the rear-right). [IN-HOUSE ❌] on
  front wing as a wear lever. The "brake balance stays at 0" preference is
  marked as no longer true on either car. The table orderings are still the
  community's, and the key says so.
- **`07`, the Shelby profile** from the archive, read-only: **213 laps in 24
  sessions, 177 on v1.71** - the plan's "156" was the count before Deep
  Forest. The profile covers:
  - the front axle as the limit, on three indicators;
  - the rear-lock complaint that was real and a fix that overshot (suggestive
    across circuits, not measured);
  - rake refuted as the lever;
  - K = 304 km/h;
  - the top-speed readout that moves the wrong way;
  - practice burn overstating race burn.
  Yas Marina's 36 laps are void.
- **`11`** keeps the percent of range and drops every absolute setup value
  it quoted from a sheet - the diff, the rebound, the ride heights, the
  spring rates and the rake (§1a).
- **`test_brain_reconciliation`** gains e6 (every live claim that the undercut
  pays is re-flagged) and e7 (`11` restates no setup value; `07` and `02`
  carry their new sections). **Both were shown to fail on the files at HEAD
  before they were trusted** - e6 flagged all 12 places, e7 all 8 quotations.

**Critic on 2.8 part 2 (`e0bcf93`): NOT AGREED - three blockers, eight
majors, seven minors, all fixed.** Three of them would have given a wrong
instruction.

- **B1: the Deep Forest rewrite planned on practice wear.** The race's own
  rate is 3.47-3.57 %/lap, a quarter higher, which gives about 24 laps, not
  30. The rule "take tyres only if the gauge asks" would have left a
  42 %-at-lap-12 set to run past the cliff in a longer race. The entry now
  quotes both rates and plans on the race's. It calls the tyre gain
  unresolvable, not zero: stint 2 was quicker, but he changed his driving at
  the same time. The rule is now gauge % plus laps left times the race rate,
  against 85 %.
- **B2: Suzuka, the next race, still said "an aggressive early stop to get
  clean air is usually correct".** That is the undercut without the word, so
  e6 could not see it.
- **B3: `07` wrote "discount practice burn 3-9 % for the race" as a rule.**
  At Deep Forest the last stint burned *more* than practice (7.92 against
  7.84 L/lap) because his driving changed. The discount would have left him
  about 5 L dry. It is now an observation, and the fill is sized from the
  live burn at the hose.

Majors:
- **M1:** every one of the 38 LSD bands in `05` is flagged where it stands,
  and the §0 table now names the v1.71 ranges. A new test, e8, checks this.
- **M2:** `11` and `07` kept positions as percentages. On a 0-100 axis a
  percent *is* the value, so they are gone: `11` keeps the conversion
  arithmetic, and `07` points to the car-state files.
- **M3-M6, the `02` tags, corrected against the ledger rows:**
  - `arb_f` softer was refuted;
  - lowering `lsd_b` is untested, and the step down on file is open;
  - the rotation index is derived, the net step was unresolvable, and it
    cost 2 spins;
  - front wing was tested upward for rear wear, so the direction is not
    refuted.
- **M7:** 9.9 s is derived, 3 s is his figure, and 1.41 s is one lap.
- **M8:** `03`'s "except where overtaking is impossible" is re-flagged, as
  are Laguna's "pit first" and Fuji's "aggressive strategy pays". e6 now
  catches every wording the critic listed, and a re-flag counts only in the
  sentence that makes the claim.

Minors:
- GT7 labels the Shelby's −0.29 stability reading Neutral.
- Its PP is 723.61 on v1.71; the old 575.47 is void.
- Brake balance is worded as issued on the RSR and as his own trim on the
  Shelby, and the Shelby's 47-of-47 front lock is shown to support the old
  preference.
- Reduced rake is [IN-HOUSE ❌] for entry instability, and the Shelby's rake
  claim is marked as having no ledger row.
- The 1x→2x conversion is marked [ASSUMED].
- The median is now the median of per-lap minimum slip.

**Critic on 2.8 part 2, pass 2 (`b00be9f`): NOT AGREED - one blocker, one
major, four minors, all fixed.**

- **B3 was fixed in `07` and still live in two other files.** The Fuji plan
  for 26 Sep said "discount practice burn 3-9 % for the race, as every
  circuit on file has shown". On a 120-minute race at 1 L/s, where fuel is
  the whole stop, that can plan one stop short. The Deep Forest sheet states
  the rule four times, and that race is its own counter-example.
  - The Fuji plan now measures the burn and sizes the fill from the hose.
  - All four Deep Forest lines are re-flagged, the prediction row as
    falsified: the race burned 7.55 L/lap overall.
  - **e9 checks for the rule in every live doctrine file, not just `07`.**
- **Major: one LSD band escaped** - Nürburgring GP's "LSD compromise ...
  18-25". e8 now matches any band on a line about the diff, and exempts only
  a line that flags the scale or states the v1.71 reading itself.
- **Minors:**
  - Two sentences are flagged in their own words: Laguna's "strongest weapon"
    and the Deep Forest sheet's "worth more here".
  - e6 sees the critic's second list too, and "not re-flagged" is not a flag.
  - "With his agreement" is dropped, because nothing on file sources it.
  - `11`'s floor position in words is now a change in points. The critic's
    suggested "0 % to a sixth" was itself a position as a percentage, so
    that is the merge with pass 1's M2.
  - "Still open" now says where each row stands.
- **Proof at the parent:** e9 flags 4 lines, the widened e8 line 151, and e6
  the Deep Forest sentence.

**Row 2.4 re-lit, 12 Sep, with the driver's authorisation.** The substrate was
frozen exactly where the row said: **3961 grip observations, none past session
88**, nothing at all for Daytona, Sardegna, Mount Panorama, Spa's full course
or the Red Bull Ring, and **Deep Forest at zero**.
- **6395 observations now** from 1094 laps, 715 counting toward a fit, and
  **140 tyre models replacing 84**. Deep Forest reports `n=43` on RS with one
  speakable scope where it had nothing.
- **Corner models built for two of the three.** Sardegna and Deep Forest
  segmented from their fastest counted lap carrying frames - the same
  reference `export/build.py` and the controller choose, because that lap
  defines the corner identities and two choices give two models. Six corners
  each, `source='auto-segment'`, which is the honest declaration and leaves
  `refusals.md` true. **Suzuka has no counted lap carrying frames at all**, so
  it has no model and gets none: an invented one is worse than none.
- **Order matters and I had it wrong first.** The derivation ran before the
  corner models existed, so it wrote lap observations and no CORNER
  observations - `data_health` then read "corner model stored; no observations
  derived yet". Re-derived after, which is the only order that works.

**The corner-source defect fixed, 12 Sep - and the gate retired itself as
designed.** `build_track_map.py` updated `corners_json` and never `source`, so
a world-anchored model still exported as `auto-segment`, which is the one
declaration `CLAUDE.md` §3.2 requires it to make and the whole basis on which
`refusals.md` says corner names may not be used. **It writes `track-map` only
when EVERY corner in the model is anchored** - the export declares one source
for the model, and a half-anchored one is not a track map.
- **The assertion written three passes earlier failed on the day the defect
  was fixed**, with the message it was given: *the corner refusal's gate has
  opened, and the block must be rewritten*. It was, in the same commit, and
  the assertion turned over to hold the tool to the declaration instead. **A
  check that knew when it was finished** - which is what pinning the property
  rather than the prose buys.

**Row 2.10 DONE: critic AGREED on pass 7** - every mutant from seven passes
dead, including every one it wrote. Its own summary of why: every tool and
every MCP call has its own line in both directions; which side of the writers'
rule a call belongs on is read from the server's body rather than its name,
which is how `propose_strategy` was caught writing despite it; a tool that
writes cannot be filed as not-an-instrument through any binding shape, any
receiver, raw DML, a derived module-level writer, a `try`-nested def or a
class method; the claims about `--apply` and about the corner refusal are
asserted against the code; and **the corner gate retires itself** the day
`build_track_map` writes `source`. It also found a live product defect on its
first real run - `build_inputs` writing through two read-only doors.

**Its three residual minors closed in the same batch rather than banked**, one
of them because it was wrong in both directions at once:
- `owners` was a dict keyed on the bare METHOD name, so of two classes in a
  module defining the same method only the last walked was recorded - **hiding
  a writer and accusing a reader with one line.** Resolved per node now, by
  walking to the enclosing class.
- `_terminates` accepted any callee whose last name segment was `exit`, so a
  local `def exit(message): print(message)` read as a terminator. The dotted
  form only.
- And it rejected a guard ending `try: return 0 finally: ...` - correct code,
  reported as a fault, with the message saying something untrue about the
  tool. It recurses into `Try`, `With` and `If` now; loops stay out, because a
  `for` over a possibly empty iterable cannot be shown to terminate.
- Four mutants: X2 and X3 fail, **X1a and X4 pass** - the two that were
  correct code being punished.

**Row 2.10 pass 6 (`d5884ae`): NOT AGREED - one major, one minor, fixed.**
Reachability was the right shape and the call graph works; the major was one
predicate inside it.
- **Major: the early-return rule tested for a terminator SOMEWHERE under the
  `If`,** because it walked the whole statement - nested branches, the
  `orelse`, `try` bodies, nested `def`s. Four shapes passed while leaving the
  tool writing without the flag, and the fourth is the one that would arrive
  by accident: **`if not args.apply: print(...) else: return 0`** returns when
  the flag IS set and falls through to the write when it is not. **An inverted
  guard reading as a guard**, on the check whose entire purpose is that a tool
  cannot write without `--apply`. The guard's body must now END in a
  terminator - verified against all eight, seven of which end in `return`,
  while the eighth never relied on the rule.
- **Minor:** only the DERIVATION of the module writers had been fixed, not the
  lookup - a writer imported through the class that owns it
  (`from X import Filer`, then `Filer.file_it(...)`) was still invisible. The
  owning class is recorded and resolved now.
- **Two questions answered against my own suspicion, by the critic:**
  recursion cannot be marked guarded (the fixpoint only ever moves upward from
  a genuinely guarded site), and the bare-name scope key errs towards flagging.
- Five mutants: E1-E4 and M2 all fail; G2 still passes.

**Row 2.9's evals, 12 Sep: 14 -> 21, and the "nine documented failures" was an
artefact.** No such list exists anywhere - the number appears only in the row -
so on the driver's instruction the count was dropped and the evals written for
what the record actually supports. Each names an incident in this document, in
`CLAUDE.md` or in a memory file, **and each would have been answered wrongly
by this skill before that incident was understood**: lowering the accel diff
for a push (refuted at s145); naming a corner "turn 3" when every model on
file is auto-segmented; running a writer as a step in a diagnosis; planning a
30-lap stint on practice wear when the race ran 25% higher; reading a `0.0` as
"did not happen"; quoting the derived shift table as the issued one; and
planning on a pit loss with the refuelling still inside it.

**And the guard I wrote for that was rule 10 again, with the working example
three lines above it.** I told the critic the eval check was *"keyed on the
same `UPDATE corner_models SET` parse"*. **It never read the parse at all** - an
unconditional deny-list on two literals, sitting under an eager `assert
"source" in columns`. So in the one direction it existed for - the code losing
the declaration again - the assert fired first and the eval's staleness was
never reached. **And my mutation had tested only the arm that works**, which is
the same failure this whole chain has been correcting. Collected into one
assertion now, so neither short-circuits the other, and checked in all four
states rather than one.
- **Where I did not take the critic's shape, and why.** It wanted the state
  "tool stops declaring, an eval says so" to go GREEN. It should not: losing
  the declaration is a §3.2 fault in its own right, and the symmetric arm -
  *"the tool stopped declaring and no eval says so"* - would make a broken tool
  green the moment an eval described it, and would oblige the evals to carry a
  defect's obituary. The rule is: **the evals may not contradict a tool that is
  behaving; a tool that is not behaving is reported whatever they say.**

**Row 3.2, 12 Sep: the board reader handed the operator the one picture that
cannot be read, and I nearly labelled a roster off it.** `read_replay_board`
clusters name strips by Hamming distance and leaves the naming to a person -
*"the operator labels each cluster once by looking at it"*. What it wrote to
disk for them to look at was `group["bits"]`: the 64x16 normalisation, which
exists so a crop a pixel wider does not read as a different driver. **The name
column is 142x24 on the canvas.** Squashed to 16 px tall the strokes that
separate `Seeni` from `Beeni` are gone before the PNG is ever written.
- **What I was about to do with it.** Session 159 came back as 8 clusters. I
  upscaled the exemplars 3x, then 8x, then inverted them, and read off
  provisional names - "Graebs", "Jonas" - against the 50-name hub list, with
  two clusters still unresolved and four that are plainly noise. That is
  reading tea leaves and calling it a measurement, against a list short enough
  that anything vaguely letter-shaped finds a match. The tool refuses to guess
  at a name at every other step - `UNREADABLE` exists precisely so an
  illegible cluster does not get one - and I was about to supply the guess by
  hand at the only step it delegates.
- **The fix is that the crop was always there and was thrown away.** The native
  ink crop is computed on the way to the normalisation and discarded one line
  later. It is now carried beside the bits, and each cluster writes
  `name-<session>-<n>-raw.png`: its three clearest sightings - ordered by
  distance from the cluster's own exemplar - stacked, dark-on-light, 6x
  nearest-neighbour. Three rather than one because a single crop can have a
  marshal's post through the middle of it and the next two will not have it in
  the same place. No interpolation, so no stroke appears that GT7 did not draw.
- **"Pinned, both halves" was written before it was true, and the critic broke
  seven of the pins.** The first round of tests exercised the new functions as
  pure functions and never as WIRED: reverting the one line in the reading
  loop that prunes the rows passed the entire suite. `test_the_roster_points_
  at_the_readable_png` was a prose pin over `main`'s source text and passed
  with `_legible` never called at all. And my own first banner test put him at
  the TOP of the board, where the banner is never adjacent - it proved nothing
  and passed with the fix ripped out.
  - The reading loop is now `read_frame()`, extracted from `main` **so that it
    can be driven by a test**, and the tests build a canvas the real
    `flag_rows` finds rows in. Seven mutations, each the defect named: the
    pruning disconnected, one sample instead of three, the render left
    light-on-dark, the fill ceiling back at 0.60, the step back at 120, the
    brightness margin removed, the merge pass removed. **All seven now fail a
    test; all seven passed before.**
**And the readable crop immediately showed the defect it was hiding: the tool
named a car that was never in the race, with his own name.** Sardegna session
159 is a THREE-car rehearsal - `Beeni` P1, `J.Jonas` P2, `K.Graebs` P3 - and the
reader came back with eight clusters. Cluster 2, 27 sightings, reads `...eeni`.
- **`flag_rows` cannot tell a flag from a place in the running order.** The
  fastest-lap banner at the foot of the board carries a country flag and a
  driver's name in the same font and the same column, so it enters the row
  grid as a driver row. At 360 s and 400 s he was P3 - last - and the row
  "behind" him was the banner. **The banner names whoever holds the fastest
  lap, which was him.** With `--apply` that writes `Beeni` onto 27 of his own
  traffic contacts as the rival behind him.
- **This is the failure the tool was written to prevent, arriving through the
  one door it left open.** `UNREADABLE` exists so an illegible cluster never
  gets a name; the name join is bounded by the sampling interval so a name is
  never carried across a pass. Both assume the row was a car. Nothing
  downstream can tell that this one was not - it is a real driver's name, in
  the right font, at the right place, on a car that does not exist.
- **Two rules, both measured over 240 frames of that race, neither reading a
  digit:**

  | | measured |
  |---|---|
  | step between rows on the board | 37-72 px (n=122) |
  | step to the banner, **three-car board** | 259-291 px (n=54) |
  | step to the banner, **full board** (s142) | **60 px** |
  | ink fill of a rival's name | 0.126-0.422 (n=122) |
  | ink fill of his own white row read as a rival | 0.906-0.918 (n=61) |

  **That third row arrived last and demolished the fix.** I measured the
  banner's separation on a THREE-CAR board, where it sits 259-291 px below the
  last row because there is nothing between them, and built the guard out of
  that number. On a full board it sits **sixty** pixels below the last driver -
  inside the 66-67 px a gap readout already occupies - so no step threshold
  separates them at any value, and `MAX_ROW_STEP` would have let the banner
  through on every league race there is. The measurement was real and the
  generalisation from it was not: one race, and the one race whose shape made
  the answer look easy.
  - **What holds in both layouts is position, not spacing.** The fastest-lap
    banner is the last thing on the board wearing a flag, and nothing with a
    flag is drawn below it, so the bottom-most flag is never read as the car
    behind him. That costs the genuinely last car on the early laps before a
    fastest lap exists and the banner is absent - a contact dropped, never one
    invented, which is the only direction this may be wrong in. The step rule
    stays for the far-separated case and for scenery.

  `board_rows` keeps the run of flags around his own row and drops panels
  beyond `MAX_ROW_STEP`. And a name is strokes, not a filled rectangle:
  `NAME_FILL` rejects a crop outside 0.05-0.50, which is what was arriving as
  the four one- and two-sighting clusters - his white-backed row read with the
  RIVAL polarity, so the background became the ink.
  - **Both constants were first set wrong, in the same direction, by the same
    withdrawn reasoning** - *"err wide, a split is invisible"*. `MAX_ROW_STEP`
    at 120 sits UNDER the 136 px a doubled gap readout makes when his own flag
    is missed, so it would split the board through his own row; it is 150.
    `NAME_FILL`'s ceiling at 0.60 sits ABOVE the 0.595 scenery floor measured
    in the same sweep - five thousandths from admitting the exact thing the
    constant exists to reject; it is 0.50, the middle of the 0.422-0.595 gap.
    Neither error was visible while the justification for them was a sentence
    the same file withdraws forty lines later.
  - **The refusals are counted and printed now**, by reason. CLAUDE.md 4.10 is
    the tyre-gauge ratchet: a band a few thousandths wrong refuses everything
    for a whole session and is invisible while it does, because only the
    accepts were ever reported.
- **Ink fill does NOT separate the banner, and must not be used to try.** The
  banner filled 0.162-0.267 against a rival's 0.126-0.422 - overlapping,
  necessarily, because the banner *is* a name in the same font. Only the
  geometry separates it.
- **The live pit wall does not have this defect**, and the contrast is the
  finding. `telemetry/board._ladder` takes *"the longest run of rows at one
  pitch, allowing two equal wider steps"* and caps a wide step at 2.2x the
  pitch - about 88 px - so a 288 px jump breaks the run and the banner is
  never a rung. Verified independently by the critic, running `_ladder`
  directly on 8 rungs plus a 288 px banner step. **With one thing to say
  alongside it:** `MIN_LADDER_ROWS = 5`, so on a three-car board the live wall
  produces nothing at all. It is SILENT on the Sardegna case, not correct on
  it - a distinction worth keeping, because "the live path is fine" would
  otherwise be read as cover it has not earned.
- The careful implementation was built for the thing that talks during a race;
  the offline tool kept the naive one, and **the offline tool is what feeds the
  briefing**: `traffic.rival` -> `analysis/rivals.py tendencies()` ->
  `carry_into_knowledge()` -> `race_knowledge.rivals_json` -> the event
  briefing the engineer reads before the green. So the concrete wrong output,
  had `--apply` run on 159, is a line in his own round briefing reading
  **"Beeni raced him for 27 laps, mostly behind"**. Nothing reads
  `traffic.rival` on the live path, so no wrong call in his ear - the damage
  is to the document the calls are planned from.
- **The stored archive is CLEAR, and it was checked rather than assumed.**
  Sessions 88 and 112 were named by the unfixed tool, and session 88 has no
  `video_path` so it can never be re-read. It did not need to be. The banner
  is only ever adjacent when he is the BOTTOM row of the board, and it is
  always read as `behind`, because it sits below the last row - so a
  contaminated row has a fingerprint that needs no video:

  **it carries the name of the race's fastest-lap holder, on the `behind`
  side, on a lap he spent on the bottom row.** The hub records who set the
  fastest lap.

  - **Session 112:** 889 traffic rows, **499 named**. He ran P4-P6 throughout,
    in a field of at least nine. Never the bottom row, so never exposed.
  - **Session 88:** 626 rows, **334 named**. One lap of twenty at the bottom
    row (lap 12, P8), and three `behind` contacts on it, all named `Chook`.
    The hub's Rd4 classification for his race - the one holding all nine names
    the reader found, him P5 - gives the fastest lap to **`CruisingChaos`**,
    who appears in that session only as `ahead`, four times, and so cannot be
    a banner read at all. `Chook` finished **P8** in that same race and was
    genuinely the car behind him.
  - **I first wrote 379 and 479 here. Both were wrong** - read off a
    `GROUP BY` by eye instead of counted, which is the habit
    `quote-a-count-from-its-own-sweep` already names. The figures above are
    `COUNT(*)`.

  So the defect reached exactly one session - 159, which was never applied -
  and was caught before a row was written. That is the outcome the roster step
  exists for, and it only worked because the crop had been made readable
  first: on the old exemplar this cluster was the unreadable `...eeni` I was
  about to label from a 50-name list.
- **Sessions 88 and 112 are the only two ever labelled this way** - `traffic`
  has rows for those and no others. I wrote "the four sessions (112, 127)",
  which is wrong three ways: it says four and lists two, **session 127 has no
  traffic rows at all**, and session 88 - the subject of the bullet above it -
  is the one actually in the category and was left out. The module docstring's
  "for four sessions" carried the same uncounted number and is corrected.
  Nothing says those names are wrong; it says the evidence they were labelled
  from was thinner than the tool had.

**OPEN, and bigger than the banner if it holds: 91 of session 88's 334 names
were written on laps he may not have been on the board for.** The critic
found them and I confirmed the count twice:

    SELECT COUNT(*) FROM traffic t JOIN laps l ON l.id = t.lap_id
     WHERE t.rival IS NOT NULL AND l.position > 8;        -- 91

They sit on laps where `laps.position` is 10 or 11, split 52 `ahead` and 39
`behind`. If GT7 draws only the top eight, his white-backed row was not on
screen, `own_row` picked a row that was not his, and the names beside it are
not the cars beside him - 27% of that session, on the one capture that no
longer exists to re-read.

- **The premise is `reference-gt7-board-truncation`, my own memory file:**
  *"eight rows, positions 1-8... a driver outside the top eight is not on
  screen at all,"* measured on the Spa race and confirmed by the driver.
- **RESOLVED, and the premise is wrong.** The driver handed over a third
  capture while this was open - Daytona session 143's race, and with it
  session 142 from the same lobby twenty minutes earlier, where he ran **P10
  with a video**. That frame reads:

      1 TommyTbone   2 Rocky   3 K.Graebs   8 PUNISHED
      9 Greenmachine 070   **10 Beeni**   11 Corn_flake   12 Magical daddy

  He is TENTH, on screen, with two cars drawn below him, in a full league
  lobby. The board keeps the top three and then a window around his own row.
  So "positions 1-8" was an over-reading of "about eight rows"; **all 91
  contacts stand, and nothing is retracted.** The memory file is corrected.
- **A note on the suite, because it failed twice and neither was mine.**
  `test_e12_every_tool_is_named_or_excluded_by_the_mechanic` failed in two
  consecutive full runs at the "tools with no line and no exclusion" assert,
  and passed alone and in its own file both times. **Another Claude session is
  working in this tree** - `tools/rig_knock_curve.py`,
  `tools/haptics_bench.py`, `pitcrew/tests/test_haptics_bench_mode.py` and
  `docs/RIG-SWEEP_2026-09-12.md` all appeared during this batch and none is
  mine. e12 globs `tools/*.py` against `mechanic.md`, so it reads a tree that
  is moving: the other session added the tool and its `mechanic.md` line a
  little apart, and both sweeps went past in between. All 54 tools are
  accounted for now. CLAUDE.md 7 already says a test that fails in a group and
  passes alone is about shared state; **a concurrent editor belongs on that
  list**, and it is why this commit stages its files by name rather than
  `git add -A`.
- **And the near miss is the point.** Session 88's capture is deleted. Had I
  taken the review's conclusion on my own wrong memory and quarantined those
  rows, 27% of the only Round 4 record would have gone, with nothing left to
  restore it from. The rule that saved it is the ordinary one: the premise was
  a claim in a file, not a measurement in front of me, and one frame settled
  it.

**Row 3.2, 12 Sep, later: I made the SAME over-generalisation twice in one
batch, and the second one shipped.** The paragraph above records measuring the
banner's spacing on a three-car board and building a guard from it, then having
that falsified by a full board. In the same commit I added a merge pass to
`cluster()` - justified on the same three-car race - and it collapsed a
twelve-car grid.
- **What it did.** Daytona session 143, the Round 6 league race, came back with
  **856 of 1,078 sightings in ONE cluster**. The reader itself was faultless:
  probed at nine points it tracked his row correctly the whole way from P2 to
  P7, reading `CruisingChaos` ahead early, then `Magical daddy` /
  `ZenPhilosopher`, then `PUNISHED` / `K.Graebs`. The clustering then threw
  those distinctions away.
- **Why.** Every distance in this file's history was measured on a race with
  two or three rivals. On eleven, five names read off the crops by eye measure:

      Magical daddy / Magical daddy   0.017   SAME driver, twelve laps apart
      Magical daddy / ZenPhilosopher  0.229   different drivers
      CruisingChaos / Magical daddy   0.250   different drivers
      K.Graebs / ZenPhilosopher       0.253   different drivers

  **Three of fifteen different-driver pairs fall under 0.25**, and a transitive
  closure over those merges the grid: A joins B, B joins C, and nothing ever
  compares A with C. The streaming pass is spared only because "which existing
  group is nearest" is asked one bitmap at a time and cannot chain.
- **Both changes are reverted, and the threshold moves with them.** No merge
  pass, and `SAME_NAME_MAX_DIFF` 0.25 -> **0.15**. The populations genuinely
  overlap - a same-driver pair at 0.017 and a different-driver pair at 0.229,
  which is *below* the 0.244 two crops of one driver reached on Sardegna - so
  **no threshold is correct** and the only choice is the direction of the
  error. A split is two readable crops carrying one name and costs a line in
  the roster; a merge puts one driver's name on another's car, is invisible
  from then on, and arrives in the briefing as fact.
- **The cost, measured, and it is the right cost.** 143 now returns 21 clusters
  for 7 drivers - `PUNISHED` alone splits eight ways. Every one is legible and
  labelled, and the seven are exactly the cars that finished P1-P6 and P8
  around his P7, confirmed against the hub's own classification. That is the
  doctrine working: the split is visible and cheap precisely because the crop
  is readable, which is what the first half of this row bought.
- **And the reason it was caught at all is that the driver handed over a
  twelve-car race.** Both errors survived every test, both critics and my own
  mutation sweep, because every artefact I had to measure against was a small
  field. A guard measured on one race is a guard measured on one race.

**Row 3.2, 12 Sep, third pass: the geometry is now the SHAPE GT7 draws, not a
threshold, and the third attempt is the one that holds.** Two absolute rules
were tried and both were wrong for the same reason - the fastest-lap banner's
distance from the board is not a constant. 259-291 px on a three-car board;
**60 px** on a full one, closer than the gap readout above his own row.
- **And the bottom-most flag is not the banner either.** GT7 draws a purple
  fastest-lap TIME bar about 22 px below the banner - measured RGB
  (100, 78, 153) on a session 143 frame - and it passes the flag test, with
  track paint below that. So `bottom = flags[-1]` looked straight past the
  banner on the very frames it existed for. Session 143 has the banner inside
  the board run on **162 of 181** readable frames.
- **What holds is the pattern.** Rows at one pitch, with a gap readout - the
  pitch plus a constant - above his row and below it and nowhere else. So a
  board admits ONE wider step each way. `_rungs` walks outward from his own
  row on that rule and it settles every case measured: the banner at 60 px
  (the wide allowance is spent on the readouts), the banner at 288 px, the
  time bar at 22 px, the track below it, and scenery 34 px above the top row
  that was being returned as *"the car ahead"* of the race leader.
  **This is `telemetry/board._ladder`'s rule**, measured over 73 frames for
  the live pit wall, and I should have reused it two attempts earlier instead
  of inventing geometry twice. The one thing added is the anchor: his row is
  known here, so a tie between equally long runs breaks toward the larger
  pitch - a stray nearer than the true pitch manufactures a smaller candidate.
- **The one case geometry cannot settle** is him LAST on the board, where the
  step down to the banner is the step down to a car below a gap readout.
  Measured cost of refusing it: 9 real contacts across 270 full-board frames,
  all on an opening lap before a fastest lap existed. Cost of keeping it: a
  real driver's name on a car that was never there. Refused.
- **An unreadable cluster was being answered.** `UNREADABLE` dropped its
  sightings from the join, so a contact then matched the NEXT readable reading
  within the interval and inherited a neighbour's name - the one case the
  operator marked unknowable was the one that got an answer. They stay in the
  map as `None` now and block the match, and the count is printed.
- Ten mutations, all caught - including one that exposed a hole in my own
  harness, which was running one of the two test files and so reported the
  `UNREADABLE` fix as pinned when nothing pinned it.

**Row 3.2 is BLOCKED on the traffic reader, and the block is measured.**
Session 143's names are read, verified against the hub and written to the
roster - 22 clusters, 8 drivers, sightings summing to 1,096 - and they cannot
be applied, because `read_replay_traffic` returned **0 contacts from 595
samples** with the radar unreadable on nearly every one.
- **The radar is somewhere else on this capture.** The tool reads
  `(1620, 830)-(1900, 1000)`; on session 143 that is bare tarmac and the radar
  is centre-bottom between the dials. `OWN_XY = (1750, 907)` was measured to
  +/- 0.23 px across 36 frames and **its y is exactly right here** - same
  widget, same scale, moved horizontally. A HUD-layout difference, not a bad
  measurement.
- **Not bodged.** Auto-detection is not a constant change: the own marker is
  ~37 red pixels and the rev counter and gear indicator are far larger red
  elements in the same band, so a naive red search finds those. Picking a
  number and hoping is the failure this row has already corrected twice.
  Needs its own measurement across captures, and until then no session whose
  capture uses this layout can be named.

**Row 3.2, 12 Sep, fourth pass: the radar is FOUND now, and finding it proved
the radar is the wrong instrument for this row.**
- **The fix.** `read_replay_traffic` read a fixed box and returned 0 contacts
  from 595 samples on the Daytona league race, because that box is bare
  tarmac on a capture whose radar sits centre-bottom. The marker is located
  from the capture now, and the route matters: **not by colour.** The HUD is
  translucent, so over dark tarmac the red arrow separates and over Daytona's
  concrete it washes out - found on 2 frames of 16. What does not vary is that
  the widget is STATIC and the track is not, so a per-pixel median over a
  dozen frames keeps the HUD and averages the scenery flat, and on that image
  the radar's crosshair is a 248 px bright run through the marker. Located on
  s143 (959, 908), s160 (959, 908), s159 (964, 909); **refused** on the s142
  practice capture, which is the point - the legacy box would have put the
  search on tarmac and reported an empty race, silently, as it already had.
- **A measurement of mine that was fake, and I published it.** I reported the
  red-marker detector hitting "17 of 21 frames". It was one frame read
  twenty-one times: `Image.open` held the file, ffmpeg could not overwrite it,
  and every later grab failed without saying so. Sixteen readings identical to
  the pixel, which I read as consistency. The real rate is about 2 in 16.
- **And a second artefact of my own sampling.** Daytona laps run ~103 s and I
  sampled every 132.9 s, so successive samples drift only ~30 s round the lap
  and sit in the same bright banking sector where the marker washes out. That
  is why 2/16 and 50/70 disagreed on the same capture.
- **What it yields on s143: 2 contacts, both unplaced - and that is the race,
  not the reader.** Three measured reasons. The MFD cycles pages, so the radar
  is up on ~71% of sampled frames against Fuel Map ~17%, the pit menu and a
  telemetry overlay. GT7's radar range is short: at 700 s he is P2 with
  **+1.712 ahead and -1.264 behind** and the radar shows nothing but his own
  marker. And he spent most of that race alone - +1:18 and -25.8 by lap 19.

**Row 3.2's carrier is wrong, and this is the recommendation.** The board
reader takes **1,096 sightings** of who was either side of him across that
race - eight drivers, continuous, every 4 s, cross-checked against the hub -
and then **throws all of it away except the names it can pin onto radar
contacts**, of which there are two. The richest source in the pipeline is
being filtered through the poorest.
- Everything row 3.2 exists to answer - gap to the leader, who is ahead and
  behind, when they pit, what fuel they took, whether they must stop again -
  is board and packet data. None of it needs the radar, which answers only
  *"is somebody alongside me right now"*.
- **Proposed:** persist the board readings in their own right -
  `(video_s, lap, side, driver)` - and build the rival derivation on those,
  leaving `traffic` to the close-quarters question it is actually good at.
  A schema change, so it is put here rather than taken.

**Row 3.2 DONE, 13 Sep: the board's reading is stored as the reading it is,
and session 143 is named.** `board_sightings` (schema v19, additive) holds
`(video_s, lap, side, driver)` per sighting. `side` is never null - the board
always says which side, where the radar often cannot - and `driver` is null
where the operator marked the cluster unreadable, which is the honest answer.
`tendencies()` reads the board and falls back to `traffic` where no board pass
was run, so sessions 88 and 112 keep answering; both paths are pinned.
- **Session 143: 1,094 sightings, 8 drivers**, and the distribution checks out
  against the hub's own classification of that race - `CruisingChaos` ahead
  231 (he ran P2 behind him for seven laps), `K.Graebs` behind 223 (P8 to his
  P7), `PUNISHED` ahead 218. This is what row 3.2 was for.
- **And the first apply put one row in wrong.** The roster was keyed by
  cluster INDEX. This run refused two strips as the fastest-lap banner - the
  guard working - which removed `Greenmachine 070`'s single sighting, took the
  list from 22 clusters to 21, and shifted every index past it up one. The
  label written against index 20 was applied to `ZenPhilosopher`. One row of
  1,094, and the tool's own output read `20 -> Greenmachine 070` beside a
  bitmap that plainly says otherwise.
  - Found by checking the stored rows against the images rather than trusting
    the print-out, and fixed at the root: each cluster now carries a
    `fingerprint` of its exemplar and the roster is matched on that, index
    only as a fallback for rosters written before. **A label belongs to the
    bitmap someone looked at, not to the position it held in a sorted list.**
  - Verified 15-19 as well rather than assuming only one had moved.
- **Third time tonight for one shape of error**: something measured or indexed
  under one set of conditions, generalised, and wrong when the conditions
  moved. Banner spacing, the cluster merge threshold, and now list position.
  The correction each time is the same - key on what the thing IS, not where
  it happened to sit.

**Row 2.9, final pass: an eval outlived the defect it described, and my own
commit is what orphaned it.** Eval 17 told Ludo that `build_track_map` *"cannot
honestly be run at all"* because it updates `corners_json` and never `source`.
True when it was written; **false two commits later**, when the source fix
landed and rewrote `mechanic.md` in the same breath. So a Ludo answering
CORRECTLY failed its own eval, and the eval pushed it to tell the driver
something false about his own tooling - `mechanic.md` and `evals.json` saying
opposite things about one file. **That is this row's whole subject, one
artefact further along**: the fix reached the code and the prose and left the
copy in the test behind.
- **The evals were the one artefact in the skill with nothing holding them to
  the tree.** e12 now asserts that no eval still claims the defect, ~~keyed on
  the same `UPDATE corner_models SET` parse that retires the corner refusal -
  so the day the code changes, the eval that describes it fails too. Pinned and
  mutation-checked.~~ **STRUCK — it was keyed on nothing, and "mutation-checked"
  covered one arm of two.** The correction is the entry above, dated the same
  day; what is in the tree now is a collected `problems` list asserted once.
- **And the habit the critic named, which is the same one three times.** I put
  incident history into `SKILL.md`'s refusal pointer (60 words), into
  `dispatch.md` (5 lines) and into `refusals.md` (2.5 lines) - the last while
  removing a duplication from that very file, and `refusals.md` is what travels
  verbatim into every subagent prompt. A subagent needs to know where the sign
  is, not why the card no longer holds it. All three are out; §9a holds them.
  **This is also where the line count went**: 455 by the cut, 466 now.
- Two reference headers claimed "unchanged" after being edited; both now say
  what changed. `dispatch.md` rule 1 says the car-state file travels with the
  card - the card points out of itself for anything car-specific and cannot
  name which file, that being car x circuit.

**Row 2.9, 12 Sep: `SKILL.md` 975 -> 463 lines. THE PREMISE WAS RIGHT AND I
MEASURED IT WRONG - corrected below, and this paragraph is the correction.**
The scoping said to delete "two blocks duplicating `refusals.md`". I compared
sections to reference files line for line, found a highest overlap of 2 lines
of 16, wrote "nothing duplicates" into this document, and moved the refusal
card to a file of its own instead of deleting it.
- **An exact-line diff over rewrapped prose measures line breaks, not
  content** - and this repo already knew that: `test_brain_reconciliation.py`
  has `_live_paragraphs()` for exactly this reason, *"a rule and the note that
  retires it are often a wrapped line apart"*. Re-measured on stripped lines,
  **23 of the refusal card's 72 lines are verbatim in `refusals.md`**, 8 of 22
  bullets are byte-identical once unwrapped, and 6 sentences match at ratio
  1.00. The second block the row named - the four proposing gates - is
  `refusals.md`:88-99 word for word.
- **And the two copies had already diverged, against the driver.** Three
  copies of the one-change rule existed; `refusals.md` and `mechanic.md` both
  said one change per run, while the third carried his own override of it -
  *"I am ok for more than 1 change at a time if the car isn't working"*, 8 Sep
  - and `mechanic.md` said flatly that the rule was *"not suspended"*. **Ludo
  was told a rule the driver had personally lifted, for four days.** That is
  `CLAUDE.md` §1a in prose: two copies, so two rules.
- **Fixed as the row asked in the first place.** The unique half of the card
  is merged into `refusals.md` - which is the copy that travels verbatim in
  every dispatch - the duplicate file is deleted, and `mechanic.md` now defers
  to it and records that it was wrong. One card.
- **The lesson is about the instrument, not the file.** I priced a trade for
  the driver - thirteen lines against a behaviour risk - on a measurement that
  was an artefact of my own tooling, and wrote the artefact into this document
  as settled. **Measure the way the thing is written, not the way it is
  stored.**
- **Every heading stays.** `debrief`, `The spine` step 1 and `The record` are
  named anchors other things resolve against, so the heading stays and the
  body moves, with a pointer that says what is over there.
- **Four things did not move, because something parses them out of this file:**
  the `write_shift_points` block (e4 splits `SKILL.md` on it), `The spine` (the
  17,421-frame figure eval 3 anchors on), the frontmatter, and the six-mode
  table the frontmatter restates.
- **Five new references** (`wc -l`, after the correction below):
  `where-the-change-landed.md` 153, `modes.md` 142, `voice.md` 77,
  `dispatch.md` 66, `closing-sheet.md` 57. A sixth, `refusal-card.md`, was
  created and then **deleted** - it duplicated `refusals.md` and is the
  blocker recorded above.
- **The restructure would have forbidden itself.** "If you have opened more
  than two references, you have read too much" was written when the modes were
  in this file; with the bodies moved, every mode must open `modes.md` and that
  rule eats one of its two. **Two wordings were wrong before the third stuck.**
  "Counts references of JUDGEMENT" exempted `modes.md` by name and left
  `where-the-change-landed.md` to be counted - which the same commit had just
  made mandatory for `refine`, so the rule forbade the table printed directly
  above it. It counts what is opened BEYOND the table now, **and says that this
  is a change of scope rather than a restatement**: every reference file is
  named in that table, so the clause that still binds is "two beyond the row,
  and if you want a third, say what question it is for".
- **466 lines, against the row's under-450.** 455 by the cut; the routing table,
  the corrections above and this record's own honesty cost the rest. **Deleting
  the duplication does not buy any of it** - that lived in the reference layer,
  and the commit that removed 81 duplicated lines took `SKILL.md` from 463 to
  464. Going under 450 means moving a rule Ludo applies every time, which is a
  behaviour risk for a line count; the driver was shown that trade and took the
  restructure without it.

**Row 2.10 pass 5 (`7b47de9`): NOT AGREED - one major, two minors, fixed.**
All four pass-4 fixes landed and hold, and the derived-writers change found a
live defect on its first run (`build_inputs`, above). The major was inside the
one thing that pass added.
- **Major: `guarded()` asked the wrong question, and was wrong in BOTH
  directions.** It climbed to the enclosing function and asked whether that
  scope contained any branch mentioning the flag - which is not the same as
  the write being REACHED under it. So `if args.apply: print("applying")`
  blessed every write after it (these tools already print under the flag, so
  it is the more natural shape, and it needs no boolean literal); and moving a
  write into a helper called only from under the guard - behaviour identical -
  **turned the suite red while naming a tool that was behaving correctly.**
  That is the misdirection class again, one layer along.
- **Reachability, with the two shapes the eleven actually split into.** Eight
  bail early (`if not args.apply: return`), where the write is a SIBLING after
  a terminating guard and ancestry cannot see it; three write inside
  `if args.apply:`, where ancestry is exactly right. **A helper is guarded
  when every one of its call sites is** - the call graph, to a fixpoint, not
  the tree. A behaviour-preserving refactor now passes, which is the test that
  matters.
- **My own false positive on the way:** counting a call to a local function as
  a write made every tool's `main()` a write at module level, under the
  `if __name__` line where no flag can reach. The function's own writes are
  recorded in its own scope; the call graph carries them.
- **Minors:** `remember=False` silenced the check on spelling alone, so a
  callee with no such parameter could be exempted - it is honoured now only
  when the callee declares it. And `_module_writers` read `tree.body`, so a
  writer defined inside a `try:` or as a class method was invisible; it walks
  the tree.
- **Six mutants**: G1, R1, R2 and M2 fail as they should, and **G2 passes** -
  the refactor that used to be punished.

**Row 2.12 DONE, 12 Sep, with the driver's authorisation.** The server is
registered in `~/.claude.json` under both spellings of this project's path -
project-scoped, not global, because it opens one app's database - with the
interpreter named absolutely, since an MCP client is not launched from a shell.
- **`propose_strategy` was not journalled, and its name is why nobody
  noticed.** It reads like a proposal and saves a strategy row, so a plan
  written over this seam was indistinguishable from one the driver built in
  the app, which is the one thing the journal exists to tell apart. A refusal
  on the way in already left a trace; the write did not. Pinned, and the pin
  mutation-checked.
- **`MCP-SEAM.md` was not stale but wrong.** It said *"Writes propose. They
  never apply"* when seven of the eighteen tools write directly; it led with
  `propose_setup_sheet`, which does not exist and cannot - §1a removed the
  app's setup record altogether; and it gave the cwd as `C:\Projects\Pit_Crew`,
  which is not where this project is, so anyone following it registered a
  server that could not start. Rewritten to the seven writers and the eleven
  readers, with `strategy_evidence`'s own former write named.

**Row 2.10 pass 4 (`0ecddce`): NOT AGREED - two majors, four minors, fixed.**
Every mutant from three reviews was dead and keying on the method was
confirmed sound (134 `Store` methods swept; no read-ish name among the 66 that
write, and no library collision). What did not hold were the two pins added
that pass.
- **Major: a docstring in an unrelated file broke the check and blamed the
  wrong files.** `_store_write_methods` read the unparsed body including
  prose, so one sentence in `Store.get_lap_frames`' docstring naming
  `self.save_race_knowledge(` put that reader into the write set - and the
  any-receiver rule then flagged the fourteen tools that call it, with a
  message pointing at `mechanic.md`, which had not changed. **A rot-guard
  failing loudly at the wrong file is how this programme spent months calling
  a product defect an environment fault.** Docstrings are stripped there now.
- **Major: the `--apply` pin was two substring tests, and was gated on the
  prose it replaced.** `if False and not args.apply:` satisfied both while
  writing unconditionally; and the loop read ` --apply` out of the document it
  polices, so editing the line skipped the check and the tool could then drop
  the flag. It is driven from the tools now, and asserts the GUARD: every
  write site must sit in a scope that branches on the flag, and **a test
  carrying a boolean literal is not a branch.**
- **Minor: `_MODULE_WRITERS` named one of at least five.** Derived now, and
  resolved through each file's imports so a tool's own local `record()` is not
  mistaken for `rival_book.record`. **It found a real defect on its first
  run:** `evidence.build_inputs` saves the measured track clock, so the MCP
  `strategy_evidence` call and `tools/shift_target.py` - both documented as
  read-only - wrote to the database every time they were asked a question.
  Fixed at the root with `remember=False` on those two doors rather than by
  relabelling them, because reading the evidence should not mutate the store.
- **Minor: the self-retiring gate used `search`**, so a SECOND
  `UPDATE corner_models SET source` would have been invisible - which is
  exactly how the authorised fix might land. `finditer`, columns unioned.
- **Stated limit, not closed:** a refusal rewritten to its opposite while
  avoiding the deny-list still passes. The real pin on that block is the
  `source` property, which holds until the gate is fixed.

**Row 2.10 pass 3 (`245f6c7`): NOT AGREED - three majors, fixed. Every mutant
from the two earlier reviews was dead; all three attacks I had asked for
landed.** The review's own diagnosis is the thing worth keeping: **`_WRITERS_
RULE`, `_APPLY_RULE` and `_CORNER_REFUSAL` each assert that a word sequence is
PRESENT, and a word sequence cannot be true or false.** That is why both a
contradiction placed beside a rule and a rewrite around it got through.
- **Major: seven false negatives in the AST write-detection, one a
  regression.** Binding only bare `Name` targets lost `self.store = Store()`,
  which the regex it replaced had caught - and with it `with Store() as db`,
  the walrus, a tuple target and a local factory. Worse, **`carry_into_
  knowledge`** - the module-level writer `mechanic.md` documents itself - was
  invisible, so a tool calling it could be filed under "not instruments" with
  the suite green.
- **The move that closed the class: key on the METHOD, not the receiver.** A
  `Store` handed in as `handle` binds to nothing a single file can see, and no
  widening of the binding rules reaches it. `Store`'s own write methods are
  read off `store/db.py` (`self._write(`, raw DML, or calling another such
  method, to a fixpoint) and a call to any of them counts wherever it appears.
  They are distinctive: nothing else has a `save_strategy`.
- **Major: the MCP side-detection knew three write verbs where the tool check
  knew nine**, so a call whose only write was `store.set_teammate(...)` read
  as a reader; and splitting the server on `@mcp.tool()` threw away the module
  head, where helpers live - a tool whose body was `_persist(plan)` read as a
  reader, and a helper BETWEEN two tools made the check fail **naming the
  innocent tool before it**, which is worse than a miss because the obvious
  fix is to move the innocent one. One verb set now, and helpers resolved to a
  fixpoint over the whole module.
- **Major: the corner refusal could be rewritten to mean its opposite** - the
  critic supplied a block containing every anchor phrase, in order, telling
  Ludo that corner names are reliable and running the writer first is routine.
  **Answered by pinning the property instead of the prose:** each `--apply`
  tool must declare `--apply` and branch on it, and `build_track_map`'s
  `UPDATE corner_models SET` must not include `source` - which holds today and
  **fails the day the gate is fixed, which is exactly when the refusal has to
  be rewritten.** The block retires itself. A short deny-list of absolution
  phrases backs it up, kept because that edit has now been observed twice and
  not because a deny-list is a principle.
- **Minor:** the raw-DML pre-check read docstrings, so a reader quoting SQL in
  prose became a writer - safe direction, wrong reason. Docstrings are
  stripped first.
- **Ten mutants, all killed**: A1-A7, B1, B3 and C. Two took a second go - the
  tuple target, because `db, _ = Store(), None` has a TUPLE on the right and
  the binding test wanted a call; and the handed-in Store, which is what
  method-keying was built for.

**Row 2.10 pass 2 (`0fd4518`): NOT AGREED - three majors, fixed. All three
were the row's own thesis turned back on me.**
- **Major: I fixed the `tools/` half and left the MCP half on a NAME.** The
  new check asked only that each `@mcp.tool()` appeared somewhere in the
  section - the roster check I had just replaced, left standing on the
  higher-stakes half. **All seven writers could be relabelled read-only with
  the suite green**, including the write that beeps in his ear at 60 Hz, the
  approved race plan, and the measurement store. Each MCP call now needs its
  own line, and the check asserts **which side of the writers' rule it is on**,
  read from the server's own body.
- **Major: the corner refusal was deletable, falsifiable and detachable.**
  Deleting the whole block, changing "nine of nine" to "three of nine", and
  moving `build_track_map` out of the writers all passed. Worse, the count was
  a **copied figure inside a refusal**, which `refusals.md`'s own header
  forbids - *"a number copied here becomes a competing answer that nobody
  re-queries"* - and the critic found **four circuits with no corner model at
  all**, two of them current programme circuits, which the number hid. The
  count is gone, replaced by the query; the block is pinned by what it must
  keep saying; and the tool's own line points back at it (a guard at each
  consumer). **The gate it named could never open**, since `build_track_map`
  writes `corners_json` and never `source` - so it now says the tool cannot
  honestly be run at all until that is fixed.
- **Major: `shift_points` meant two things in one section** - the tool that
  DERIVES a table from his laps, and the MCP call that returns the one ISSUED
  and in the car. Rule 13 on the two halves of rank zero, with a line on only
  one of them. Both lines now name the other and say they can differ.
- **Minors:** the store-write guard forced 8 of 14 writers into place and a
  writer using raw SQL walked into the exclusion list; it is decided by the
  AST now - names bound to `Store(...)`, plus raw DML - which catches the
  three that call no store method at all. A bullet inside a fence, inside an
  HTML comment, or indented as a sub-bullet counted as a tool's line. The
  `--apply` sentence was pinned by a substring. A code span wrapped across a
  line, rendering `references/ refusals.md`. And `_mechanic()`'s heading
  failures were messageless `ValueError`s.
- **Ten mutants, all killed**, including all seven the pass-2 review left
  alive. **And it confirmed by AST what I had found by body: seven MCP
  writers, not six** - `propose_strategy` saves the strategy it proposes.

**Row 2.10: NOT AGREED on `5b351c1`, fixed - three majors.** e12 made the row
**checkable, not met**, and the two things that actually endanger the driver
sat in its blind spot.
- **Major: the MCP surface was missing entirely.** `pitcrew/mcp/server.py` has
  eighteen tools and `SKILL.md`:621 sends the skill to four by name; the word
  MCP did not appear in `mechanic.md`. So the writers' standing rule - *only
  with the driver's yes, never as a step of a diagnosis* - reached fourteen
  scripts and **none of the MCP calls that write**. Checked by body rather
  than by name, there are **seven**, not the six the critic listed:
  `propose_strategy` saves the strategy it proposes despite its name, and
  `write_measurement`/`write_verdict` write through `record_measurement` /
  `record_verdict` plus a journal entry. And `write_shift_points` appeared
  once, framed as a validator - it is the authoritative write of the one setup
  artefact that reaches him at 60 Hz.
- **Major: e12 pinned the roster, not the line.** Seven of the critic's
  mutants lived: any backticked identifier satisfied it (a `tools/fit.py` or
  `tools/judge.py` would pass on the strength of callables named elsewhere),
  the reverse direction covered 32 of 51, an instrument could be reclassified
  as *not* an instrument invisibly, and the writers' rule could be deleted or
  inverted to "harmless, run them freely" with everything green. It now reads
  the two lists as separate sections and requires a LINE; both directions for
  both lists; every MCP tool named; a tool that writes the store listed under
  the writers; and **a tool the skill sends itself to may not be excluded**.
- **Major: the list offered three earth-anchored-corner tools while
  `refusals.md` says there is no track map.** All nine `corner_models` rows
  are `source='auto-segment'` (read-only check), so the refusal is true today
  and `build_track_map.py --apply` is the thing that would make it false -
  silently, mid-diagnosis, after which "T4 entry" reads as a name the app may
  use. Now carried as a refusal in `mechanic.md` itself.
- **Minors, each a claim that was not true:** `read_replay_board` writes its
  roster JSON and PNGs on the *dry* run, so "writes nothing without `--apply`"
  was false (the DATABASE is what it leaves alone); "write" meant two things
  three lines apart; `brake_bias`'s one line invited rule 5 on a value GT7
  does not send; the exclusion reason did not cover two of its own entries;
  and `draw_bathurst_map` opens `Store()` at module scope, so *importing* it
  writes the live database. Counts corrected to 51 tools, 32 instruments, 19
  excluded. Eight mutants, all killed.
- **Out of scope, wants its own row:** `tools/build_track_map.py` UPDATEs
  `corner_models.corners_json` and never touches `source`, so a world-anchored
  model would still export as `auto-segment` - the declaration CLAUDE.md §3.2
  requires.

**Critic on 2.8 part 2, pass 11 (`e6fe7ca`): AGREED - row 2.8 is done.** It
ran the perturbation proof itself and confirmed both majors closed: under the
house style pass 10 loses `07`:609 and pass 11 loses nothing; with the front
axis bolded pass 10 flags one line more, the FWD line it should exclude. It
called perturbing the input *"better than the standard I set"*. Seven minors
carried to a follow-up, and the first is the one that matters: **`named.add(
sentence)` can become `named.add(line)` and no test fails**, which would make
the back-reference rule line-scoped - the fail-open class this row has fought
since pass 7. Also: `_SENTENCE_END` knows `)` and `"` but not `]`, which is
how every stamp in this corpus closes (measured at 0.12% of sentence ends, so
a minor and not a repeat of the major); e11's call site can revert to `_CURE`
untested; e11's fixed-width lookbehinds miss `front  accel` where e10's
`[\s-]*` does not; and **narrowing e11's vocabulary cost his own word** -
"the car will not turn in" is no longer seen, when the looseness was distance,
not vocabulary.

**Row 2.8's seven residual minors, closed.** `_SENTENCE_END` takes `]` and
`}`; `_plain` evens the spacing, which fixes e11's double-space gap for every
pattern instead of teaching four lookbehinds to count spaces; the backtick
came out of `_MARKUP`, the critic having shown it earned nothing; e11's corpus
check and its probes go through one expression, so the call site is pinned and
not only the patterns it is built from; `_axis_name`'s note says it flattens
underscores where `_plain` does not; and **his own word for the symptom is
back** - "the car will not turn in" is seen again, while "out of every turn"
and "Turn 4" are not, the distinction being the phrase rather than the
distance.
- **The one that mattered took two goes.** `named.add(sentence)` →
  `named.add(line)` survived even the two probes written for it, and working
  out why corrected the finding: the mutant stores the LINE and looks up the
  SENTENCE, so the two never match and the rule goes **inert** rather than
  line-scoped - identical on a single-sentence line, and on a multi-sentence
  one it simply stops suppressing. Every probe in the file is one sentence or
  expects a flag, so none could see it. The shape that separates them is two
  sentences with both claims in the second. **A mutant that survives is worth
  more read than re-killed:** its survival said the finding's stated
  consequence was wrong.

**Critic on 2.8 part 2, pass 10 (`202b26a`): NOT AGREED - two majors, five
minors, fixed.** It granted the substance of all three pass-9 majors: the
sentence is the right unit and not a third wrong one, the proof script is
sound, `08` A5 is properly resolved, and it checked each of the three new
stamps on its merits and agreed with all three (and that `05`'s traction
levers are rightly left alone). **The defects were in the execution.**
- **Major: the right unit, the wrong splitter.** `_sentence` broke on `". "`,
  and **29.6% of the sentence ends in e10's own scope are `.**`, `.)` or
  `."`** - the house style, 173 times in `07-car-profiles.md` alone. Where one
  is missed the function degrades silently back to the line, which is the
  defect it was written to fix. The critic proved it by rewriting a single
  full stop on the real `07`:609 and watching e10 go blind on the exact line
  the pass was about.
- **Major: the FWD exclusion wanted the literal string `front `**, so
  `**front** accel` - which is how `02` §10.5's own AWD and FWD lines are
  written - turned off the guard added in the same commit to provide it.
- **One fix for both: take the emphasis out before matching anything.** A
  guard resting on a formatting choice nobody knows is load-bearing is not a
  guard, and six patterns each guessing at the house style is six chances to
  guess wrong.
- **The back-reference rule, which closed three findings at once.** `diff` and
  `lock` name no particular slider, so once a sentence has named one and had
  it rejected, the bare word is that same slider described again. It settles
  the FWD line carrying a second lowering verb, "Braking sensitivity down
  unlocks the diff", and §4.1's Initial Torque bullet - which pass 7 had to
  hand-stamp precisely because no pattern could separate them. The stamp stays
  and still documents it; the check no longer rests on it.
- **Minors.** e11's symptom set was `_CURE` with no proximity bound at all, so
  "out of every turn" and "Turn 4 is the reference corner" counted as
  evidence - the traction levers were out of reach by an accident of wording
  rather than by the distinction the check claims to draw. Narrowed to the
  rotation family. e11's scope was 18 files narrower than e10's with no reason
  given, including the ledger this very commit had argued into e10; they share
  one constant now. `low` came out of the lowering words. `05`:730's stamp
  called a wear claim a traction one. And a comment claimed `\block\b` fixed a
  line it does not fix.
- **Minor, and the lesson: my mutants were chosen against my probe list, not
  against my diff**, so five of the critic's nine survived - two of them
  changes this commit's own message announced. Twelve against the diff this
  time: **nine killed**, one anchor gone with the dead code it named, and
  **two survive and are written down as surviving** - `low`'s removal, now
  redundant beside the back-reference rule, and e11's normalisation, which is
  precautionary.
- **A robustness change cannot be proved by a corpus diff**, and pass 11
  returns exactly the same ten lines. `scratchpad/prove_pass11.py` perturbs
  the corpus into the house style the critic measured instead: under it
  **pass 10 loses `07`:609 and pass 11 loses nothing**, and with the front
  axis bolded pass 10 flags eleven lines to pass 11's ten - the extra being
  the FWD line it is supposed to exclude.

**Row 2.7's pins confirmed (`d40c4c8`), and row 2.10 pinned.** The critic
re-ran its four pass-6 mutants against the new tests: **all four killed, each
by the test written for it** rather than by incidental collateral. It then
named the seam those tests do not cover - a mutant inking `CHALK`
unconditionally, so that the widget stops honouring `warn`, survives every one
of them, because they pin what the controller ASKS for and not what is
painted. Pinned on the other side too, the way `test_banner.py` already does
it; and both warn assertions now select their note by what it says instead of
by being last, which would otherwise follow a later note in silence.

**Row 2.10 was built and was kept true by nothing.** `mechanic.md` already
names every instrument and, separately, every tool that is deliberately not
one - the app's own health, voice, rig and build. Nothing stopped that going
stale, and a tool added without a line reads exactly like a tool that was
never written, which is the finding the row came from: ten tools existed and
were re-derived by hand because nothing named them. **e12 checks both
directions**, the second being row 2.8's stale-citation defect from the other
end - a line for a tool that no longer exists sends the skill to run something
that is not there. Three mutants, all killed: a tool losing its line, a
citation to a tool that does not exist, and the footer ignoring its warning.

**Critic on 2.8 part 2, pass 9 (`9128418`): NOT AGREED - three majors, three
minors, fixed.**
- **Major: judging the refutation on the LINE put pass 7's major straight
  back.** e10 iterates lines and a markdown row is one line of many cells, so
  a refutation quoted inside a stamp cleared the live claim standing beside
  it. Not hypothetical: it failed open on `07-car-profiles.md`:609 - the line
  pass 6 named as one of the two most canonical places - and stripping that
  line's stamps left e10 seeing nothing at all. **Both wording exemptions are
  judged on the sentence now** (`_sentence`, bounded by `|` and `. `, the
  boundaries the claim pattern itself refuses to cross); `_OVERRUN` moved to
  the same unit, having had no reason to differ.
- **Major: the proof proved nothing about the pass.** The old script reported
  the same 9 lines for pass 8's code and pass 9's on every tree in the
  history - evidence about the corpus, not the change - and hardcoded the
  live tree's path, so its answer depended on what happened to be checked
  out. `scratchpad/compare_e10.py` takes the repo and both commits as
  arguments and runs the two versions over one corpus: **pass 10 gains
  `07`:609 and loses `04-race-vs-qualifying.md`:258**, the Initial-Torque line
  the axis rule now correctly rejects. One variable, two intended changes.
- **Major: what Ludo would actually say, which is the only test that
  matters.** `08-playbook-leon.md`'s A5 - the section opened for a push on
  throttle - carried an unstamped **heading** and an unstamped standing rule,
  both saying *run acceleration sensitivity LOW*, and `08`:144 and `08`:152
  asserted opposite things about whether that direction survived 1.71. Rule
  13 inside one document, with the unstamped half being the line a reader
  scans. The call it produced, *"accel sensitivity down two clicks"*, is the
  step the axis register records as REFUTED. Heading and rule stamped, and the
  contradiction resolved by separating A5's two claims: the **mechanism** (a
  near-spool axle breaks away as a unit) survived 1.71; the **cure** did not.
- **e11 added, because e10 is not shaped to catch it.** e10 asks whether
  lowering the axis is offered as the CURE for a push; a standing rule names
  no symptom, so no cure-shaped check can see one. e11 flags a "run the
  acceleration axis low" instruction on a line that names a rotation symptom,
  which caught `01`:247 and `05`:408 and `05`:730 - all three stating that a
  locked diff pushes you wide. Stamped. **`05`'s traction levers are
  deliberately out of reach**: "more lock produces more wheelspin, not more
  drive" is a different claim and was not refuted, and stamping it CONTESTED
  would be the false record this file exists to prevent.
- **Minors: 4 of 15 mutants were alive**, including this pass's own stated
  change. The 200-character window is pinned by a rationale that genuinely
  needs it; `_ON_POWER` loses "push" and "understeer", which are the two
  commonest symptoms there are and whose presence killed the overrun
  exemption for every ordinary wording of it; `\block\b` so the "lock" inside
  "unlocks" is not read as the axis being lowered; `brain/ledger/` into e10's
  scope, **and said plainly that it flags nothing today and that a mutant
  removing it survives** - a door closed on the way in, not a defect caught.
- **Found by my own mutation run, and the same fault the critic keeps
  finding:** the axis rule - the whole of what passes 8, 9 and 10 have argued
  about - was pinned by no probe at all, because every exclusion in the probe
  list is decided by the refutation or the overrun rule. Three probes added.
- **Proof:** 7 of 8 mutants killed, the eighth being the ledger scope.

**Critic on 2.7, pass 6 (`1a1bdcd`): AGREED - row 2.7 is done.** Every one of
pass 5's findings was attacked at runtime and none reproduced: the switch now
carries the link, the BoP change and the limit alongside the boxed
comparison; a second switch repeats none of it, the round being spent; and
`_switch_to_round` appends rather than overwrites. Four minors remain, all
test gaps rather than wrong behaviour, and all four are pinned in the same
batch as row 2.8's pass 10:
- **The unconditional `_calendar_news` assignment is load-bearing and was
  unpinned.** Moving it inside `if said:` passed every test - and that one
  line is the whole of what stops one event's news being prefixed to the next
  event's footer, which is CLAUDE.md rule 11 exactly.
- **Neither warn flag was pinned**, on the switch footer or on the
  adopted-link footer - the second being the precise mistake my own first
  attempt made, so a demoted warning could return unnoticed.
- **The states-none early return's discard was unpinned**, which would have
  brought pass 5's staleness back for the rounds the plain league series
  produces, which is most of them.

**Critic on 2.7, pass 5 (`4cf5dbc`): NOT AGREED - one major, three minors,
fixed.** The carry itself was verified sound - the critic's corrected mutants
killed it in both directions - but everything it produces was being destroyed
on the ordinary route between two events.
- **Major: `switch_event` threw the hub's news away, and nothing could ever
  say it again.** It rebuilt the footer out of its own regulation comparison
  and wrote it over the one `load_active_event` had just composed. The
  comparison survived, because the switch repeated it; every "From the hub:"
  clause did not - the BoP and the limits, which appear on no other screen.
  And they cannot be repeated: by then the round is spent and the stored value
  agrees with the hub, so no later load has anything to say. The stored value
  was right and Ludo's instruction was right; the driver was simply never
  told. **One note builder now**: `_say_calendar_news` keeps what it composed
  in `_calendar_news`, and the switch prefixes its own line to those parts
  instead of replacing them. The two paths cannot say different things because
  there is only one thing.
- **Minor: the round was spent above the write it justifies.** An
  `update_event` that raised left the row unwritten, the footer silent and the
  link unsayable ever after - the one fact that knew the match was inferred
  having already been discarded. Moved below the write. Same spend-before-act
  shape as pass 3's minor 2.
- **Minor: a load with nothing to fill left the round remembered for good.**
  The early return sat above the discard, so an event whose values already
  agreed was never told it had been matched - and the next genuine change,
  whole loads later, was announced as "linked to ... by circuit and car",
  crediting a fresh match for something unrelated to it. **The link is news on
  its own now**, said and spent whether or not a fill follows.
- **Minor: the discard was pinned by nothing** - three mutants lived. Four
  tests added, asserting on the remembered set itself.
- **Found while fixing it, same class one layer out:** `_switch_to_round`
  calls `switch_event` and then overwrote *its* footer for an adopted round -
  which is the one path that infers a link, so the note being replaced was the
  one carrying it. It appends now, and carries the warning with it.
- **Proof:** five mutants, all killed - the switch rebuilding its own footer,
  the discard back above the write, the no-fill return dropping the link,
  `inferred.clear()` for `discard`, and the discard removed entirely. Suite:
  4750 passed, 5 skipped.

**Critic on 2.8 part 2, pass 8 (`5a01a32`): NOT AGREED - one major, two
minors, fixed.**
- **Major: the span rule fixed the examples, not the class.** Pass 7's
  check scanned the matched span for a disqualifying token, so a claim that
  named a second slider *while making the claim* cleared itself - "lower
  the accel **and the initial torque**, and the push goes away". Seven of
  the critic's eight probes passed through. **The axis is decided from the
  match now** (`_ACCEL` captures it), and three things are ruled out on
  their own terms: the matched axis being braking, initial torque or the
  FWD front diff; the refutation's own sentence ("gives LESS rotation on
  power", both car-state wordings); and an OVERRUN claim that offers a
  rotation source rather than a power-on cure. All sixteen probes are
  pinned.
- **Minor: "turn" and "point" are the same symptom in his words**, and the
  windows were too short for a rationale with a clause in the middle. Both
  widened.
- **Minor: the commit carried no §9a entry.** This is that entry, with pass
  7's.

**Critic on 2.7, pass 4 (`858f281`): NOT AGREED - one major, one minor,
fixed.**
- **Major: my adopted-link fix was dead code.** `_apply_hub_regulations`
  only runs for an event that already carries `hub_round_id`, and
  `_link_round` writes that id *before* the load. `upcoming()` then resolves
  the event through `known_rounds` rather than inferring it again, so the
  proposal reaching the apply step never says `adopted`. An inferred link
  went on stamping regulations onto his own event in silence. The critic
  proved it three ways, the decisive one being a mutant that forces
  `adopted` true for every event and changes no test outcome.
  - The fact is carried from where the inference happens now: `_link_round`
    remembers the round, and the next apply spends it once.
- **Minor: that commit changed no test file, and all seven of its mutants
  survived** - including the ordering fix I had called the important one.
  Four tests now pin it: the inferred link says what it brings and is not
  news twice; a first fill on a link he made is not news; a round stating
  none of the four writes nothing while the boxed comparison still runs;
  and a write that fails says nothing it did not do.
- **The inferred-link test was itself mutation-checked**: with the carry
  removed it fails. That is the check the previous fix never had.

**Critic on 2.8 part 2, pass 7 (`b95c137`): NOT AGREED - one major, one
minor, fixed.**
- **Major: the exclusion was tested against the whole line, so a sentence
  naming a second axis cleared the live claim beside it.** "With initial
  torque already low, drop the acceleration sensitivity to cure the push"
  is ordinary writing, and it passed. Nothing in the corpus was wrongly
  cleared - the critic checked all seven - but the guard failed open for
  the next thing written, on a claim that has come back four passes
  running. It is judged on the **matched span** now
  (`claims_lower_accel`), and the critic's six two-axis sentences are
  pinned.
- **Minor: I reported `02` §4's zero-floor hedge as updated and it was
  not** - only its sibling in `08` was. It said "may no longer be 5" and
  "confirm it before it changes a single setup" while `range_records` had
  already answered. Fixed.
- **What the span-level check then exposed, and the decision it forced.**
  `_CURE` stopped at "rotat", so the refutation's own "gives LESS rotation"
  fell outside the span and the check flagged the evidence that refutes the
  claim. The symptom word is matched whole now. And **"freer differential"
  had to come out of the exclusion list**: §4.1's Initial Torque bullet and
  the live claim say it in the same words, so no pattern can separate them.
  The check flags the wording, and the bullet carries a hand stamp - a test
  reads the file to hold it there.
- **The proof script was reading `HEAD`, which already carried this pass's
  stamps**, so it reported zero and I nearly believed it. Against the
  correct parent (`e4f2767`) e10 flags 9 lines and e8b's slider-name form 9.

**Critic on 2.7, pass 3 (`5b656db`): AGREED - row 2.7 is done.** All five of
its break attempts behaved: a hub that goes silent leaves the stored value
standing (silence is not a change); a Save between a hub change and the next
load cannot strand a stale value, because `_on_event_saved` ends in
`load_active_event`; no hub means no crash and no claim; the create path
carries the regulations; and re-linking works. Seven of nine mutants killed,
the two survivors being test adequacy rather than behaviour.

Its four minors, fixed:
- **The notes were worded after the write and inside its `try`.** A raise
  there would have left the row updated, the form stale and the change
  unsaid. They are built before the write now, and `_said_change` says "not
  stated before" instead of formatting a None.
- **An inferred adoption** - a link matched by circuit and car - stamps the
  round's regulations onto his own event, and said nothing, because a first
  fill is deliberately not news. It now says "linked to <round> by circuit
  and car" with the values.
- The `SPOKEN` comment says why re-adding an entry there would be dead
  rather than wrong: by the time it runs the stored value is the hub's.
- A linked round that states none of the four is logged, so "stated today"
  and "stated once, then silence" are distinguishable in the log.

**Critic on 2.8 part 2, pass 6 (`af58e50`): NOT AGREED - two majors, two
minors, fixed.** Both majors were the same shape: a line-level check misses
the claim when it is written another way.

- **M1: the claim survived in the two most canonical places**, stated as a
  mechanism rather than an instruction.
  - `02` §4.1's own definition of the parameter: "Decrease → more rotation
    on throttle", with "Increase → ... power understeer" saying it from the
    other side.
  - `07` §6.2 on the Huracán: "less acceleration lock means less rear
    scrub", where **that car's own file says the opposite** - "on this car
    LESS acceleration lock gives LESS rotation on power". Both now carry the
    pointer, and `07`'s cites the car-state line that refutes it.
  - e10 gains the mechanism wordings: decrease, freer, open the diff, less
    lock, soften, back off, out of the diff.
- **M2: e8b could not see a band unless the line said "LSD"**, and §4.1
  names each slider in its own heading. So "Initial Torque (5-60)" and
  "Braking Sensitivity (5-60)" kept the v1.70 range while the acceleration
  sibling had been stamped - the section contradicted itself. It now matches
  a slider's own name, and `04`'s quali bands are stamped: taking "initial
  torque 5-10" on v1.71's 0-30 slider is a third of the way up, not the
  floor.
- **Minors:** `02` §4's and `08`'s hedged zero floor now cite
  `range_records`, and the critic's probe list is pinned.
- **Widening it found five false positives, each a different claim:** the
  overrun/braking axis (`02`:422, `08`:118, `11`:256), Initial Torque's own
  bullet (`02`:434), a FWD front diff being *raised* (`02`:915), and **the
  refutation itself** (`car-state/huracan-daytona.md`:342). Stamping any of
  them would have been a false record, so `NOT_THIS_CLAIM` keeps them out
  and a test pins that.
- **Two blind spots, stated and hand-stamped instead:** a bullet that takes
  its axis from the heading above it (`02`:440 and its Initial Torque
  sibling), and the arrow forms ("18 → 14", "25→20"), which carry no
  lowering word at all.

**Critic on 2.7, pass 2 (`db55a11`): NOT AGREED - one blocker, four minors,
fixed.**
- **The blocker: the hub's first word was kept for good as if it were his.**
  Pass 1's fix filled a NULL and then reported, never overwrote, a value on
  file. But no screen writes `bop_enabled`, `tuning_allowed` or the power
  and weight limits: the hub is their only author. In the critic's repro
  the league turned BoP on and moved the limit after he saved, and the app
  went on handing Ludo "BoP off" at 509 BHP. A sheet with gear ratios would
  have gone to a round that locks them. The power change was not said at
  all.
  - For these four hub-only columns, the hub's current value now wins on
    every load of a linked upcoming round, and each change is said in his
    words: "BoP is now on for this round", "power limit now 520 BHP (was
    509)". "Report, never overwrite" stays for the columns that have a box.
  - The hub's word is applied **before** the form loads, so a later Save
    carries it, not the stale copy.
- **Minors:**
  - The blocker's regression test now takes the round off the hub before
    saving, so it pins the save path on its own. It had passed without the
    fix, because the next load filled the values back.
  - The weight limit is tested.
  - The change notes are in the driver's words, not "BoP 0 here, 1 on the
    hub".
  - The hub is read once per load, and the proposal is passed on to the
    comparison.
  - A fill is logged with the round that caused it.

**Critic on 2.8 part 2, pass 5 (`e4f2767`): NOT AGREED - one major, two
minors, fixed, and the class now has its own check.** Passes 4 and 5 each
found four more places offering "lower the accel" as the cure for a power-on
push, unpointed, after the v1.71 Huracán test refuted that step (s145).
Chasing lines critic by critic was not converging, so the claim itself is
now checked.

- **e10** covers every line in the skills, the knowledge base (`00`-`17`)
  and the car-state files that ties lowering the accel to a push,
  understeer or rotation. Each must carry "CONTESTED", the `02` §10.5
  pointer or its v1.70 stamp.
  - The snap, tyre-wear and wet-weather "lower accel" lines are a different
    claim and stay clear of it, and a test pins that.
  - **Its limit, stated:** a line that never names the accel ("come DOWN
    from 25") and the arrow forms ("18 → 14", "25→20") are beyond a worded
    pattern. `08`:530, `01` §11, `01`:163 and `08`:274 carry their pointers
    by hand.
  - `01` §11 is stamped v1.70, with a note that its values are history.
- **e8b now also sees** a band written before "accel", a triple after the
  diff, and "initial torque N, acceleration N". A triple in a car-state file
  is that car's setting, so it is exempt. Newly flagged: `02`:510, `06`:529
  and :535, `07`:220 and :543.
- **Two more stale "floor may be 0" lines** (`04`:258, `07`:392) now say
  `range_records` confirmed it. `07`:40's "20-28" is labelled v1.70, the
  case the critic raised: an exemption clearing a line whose band was still
  the old scale.
- **Proof at the parent:** e10 flags 6 lines and e8b's new forms 5.
- **Tests:** `test_brain_reconciliation` 21 passed.

**Critic on 2.7 (`c48e018`): NOT AGREED - one blocker, three majors, five
minors, fixed.**
- **B1: the BoP flag never reached the Fuji event.** Every Enduro round
  arrives incomplete, because the hub gives no legal compounds. So it goes
  pick -> fill the compounds -> Save. The save copies a fixed list of
  fields, and the flag, `tuning_allowed` and 0.14's power and weight limits
  were not on it. The Event screen now carries all four, the save writes
  them, and the critic's repro is kept as a regression test.
- **M1: nothing wrote the hub's word onto an event already stored.** A NULL
  is not his answer, so on every load of a linked event the hub now fills
  it. A value he holds is compared against the hub, and a change is reported
  ("BoP 0 here, 1 on the hub"), never written over. **Event 4 (Spa Enduro,
  "RUNS BoP" in its notes) is a past round and will not fill that way.
  Backfilling it is a write to the live DB, and waits for his yes.**
- **M2: Ludo had no route to the flag before an event row exists.**
  `initial` step 2 now names the hub itself, read-only, for that case.
- **M3: `what to try` could propose a locked key.** `refusals.md` carries
  the BoP refusal for every mode. The Fuji runs must be run in a BoP lobby
  on the Enduro settings, because burn, pace and shift points taken in a
  time trial are a different car's.
- **Minors:**
  - A mixed True/False test case, so swapping the two columns fails.
  - `list_events` must carry the new keys.
  - Eval 10's expected output no longer says "the app has no BoP field".
  - The practice-intent gap is about practice sessions; race sessions never
    carry the field.
  - The Fuji plan labels the open-tuning list and the ECU, restrictor and
    ballast lock [ASSUMED], with their source, and adds slipstream-disabled
    qualifying.
  - **Out of this row, for a follow-up:** `CLAUDE.md` §2 still says the league
    has no BoP.

**Critic on 2.8 part 2, pass 4 (`68eb4d1`): NOT AGREED - two majors, two
minors, fixed.**
- **Major: "lower the LSD acceleration" still read as validated** in `01`,
  `03`, `07` and `08`. The worst was `01`: "This is the whole answer more
  often than not". Each place now points to `02` §10.5: on v1.71 the Huracán
  refuted lowering it, and raising it cost 2 spins in 10 laps.
- **Major: `02` §11 gave "accel 15-25, brake 10-20" unflagged.** e8b extends
  the band check to the skills, the knowledge base (`00`-`10`) and the
  car-state files. It found **two live car-state lines** reading the
  Huracán's v1.71 `lsd_a` against a v1.70 band, which is exactly the error
  the flags exist for:
  - Mount Panorama: "18 is already inside the reference's 20–28", and 18 is
    outside it anyway.
  - Daytona: the knowledge base's "22-28 ask was pointing the right way".
  It also found fourteen knowledge-base lines. Four of them still said the
  floor "may be 0"; `range_records` has answered that.
  **The first narrowed version missed both car-state lines.** `\bLSD\b`
  cannot match `lsd_a`, because the underscore is a word character, and an
  80-character window was too short. It now matches the slider keys over
  120 characters. **At the parent it flags 19 lines**, both car-state lines
  and the two the critic named among them.
- **Minors:**
  - `03` §8.5's note is current, and its step sizes are flagged.
  - The absolute v1.70 values in `07` are declared, once in its banner,
    history of a void version and never a setting. I chose that over
    converting two of the seven places they appear.

**Critic on 2.8 part 2, pass 3 (`24a332e`): NOT AGREED - one major, two
minors, fixed.**
- **Major:** the Deep Forest Rev B sheet still planned on the discount - "race
  burn at the measured 3-9% practice discount is 7.46-7.95 L/lap" - with the
  number before the word, where e9 could not see it. That sentence is now
  re-flagged with 7.55 overall and 7.92 in the last stint. e9 now matches
  every form the rule took: the number first, "take/knock X % off
  practice", "runs X % under practice", and the number-less "overstates race
  burn ... on every circuit". The critic's probes are pinned, and the
  observation in `07` ("ran above race burn at ...") is held clear of it.
- **Minor:** the Deep Forest sheet's "overstates race burn on this car, on
  every circuit" is flagged where it stands.
- **Minor:** I had asked whether a delta in points still leaks a position,
  and it does. "Rose by about a sixth" solves, with both formulas printed
  beside it, to exactly 5. It now says only that initial torque moved
  further than any other axis.
- **Proof at the parent:** e9 flags both sentences.
- **Tests:** `test_brain_reconciliation` 18 passed.

**The critic on 2.6, pass 5 (`ee4e4d4`): AGREED - row 2.6 is done.** N1, N5
and N6 are killed by the new tests. The test pinning N1 now runs with the
compound unnamed and with it named. The one pinning N5 and N6 goes through the
real `_driver_board_state` with the race running. N3 and N4 are recorded as
equivalent. On the grid no lap has been judged, so `laps_to_stop()` is None
only on a plan's last stint, where `next_tyres` and `next_compound` are
already None, and neither guard can change what the board shows. Across
passes 4 and 5 every other mutant on a new branch is caught by a test. Its
suite on this machine: 5 failed, 4729 passed, 8 skipped. The five are the
same data-dependent tests that fail at the parent.

**The critic on 2.6, pass 4 (`234b0af`): NOT AGREED - on tests, not code.**
It could not build a wrong call or screen against the code. A fuzz of
112,944 plans found `tyres_refusal` and `stint_tyre_problems` refusing the
same ones. Of 27 mutants on the new branches, 21 were killed through their
real callers. Last pass's eight survivors are all among them.

- **The major:** three of the retired-stop guards had no test.
  - **N1:** the retired-stop test's plan named no compound, so the snapshot's
    guard changed nothing it could see.
  - **N5 and N6:** the running board's guards were never exercised after a
    stop was retired.
  - All three are pinned in `ee4e4d4`. The test now runs with a compound and
    without. A board test drives the real `_driver_board_state` through a
    retirement.
- **Two harmless survivors:** N3 and N4, the same guards on the grid board.
  Before the green no lap is judged, so `to_stop` cannot be None while a
  stop is planned.
- **Minor:** the "same stop count, the desk's decision stands" branch of
  `adopt` cannot be reached from an accepted offer. `assess` only offers a
  count that differs from his plan. The branch is correct and pinned, and
  stays as the answer if `assess` ever offers a same-count shape.

**The critic on 2.6, pass 3 (`f511c9e` + `f446334`): NOT AGREED - three
majors, all fixed.**
1. **A retired stop kept its tyres answer.** After "You're fuelled to the
   flag. No more stops on fuel.", "what tyres?" said "Tyres on." (or "RS
   on.") and the board read "fit a set". The snapshot and both driver-board
   states now drop the next stop's compound and decision while
   `laps_to_stop()` is None, the expression BOX_WHEN answers "No stop
   planned" from.
2. **A JSON `0` was fuel only to the voice and a second set to every
   screen.** One public `handover.tyres_decision` now answers for
   `coordinator._tri`, the brief count, the Race page, the spine and the
   stint bar.
3. **Eight surviving mutants**, among them the pass-2 MAJOR fix itself: M4
   (`assess`'s `stint_tyres`), M5 (the controller's hand-off), M8, M9-M11
   (the three NO TYRES labels, whose choice moves into `Spine.band_label`
   and `stint_label` so it can be tested without painting), M13 and M14 (the
   brief lines leaving the pack unseen - pinned from `brief()` itself). Each
   has a pin through its real caller.

Minors:
- The refusals speak to the driver, with the remedy for that problem and "on
  the Strategy page" (`tyres_refusal`, held to refusing exactly what
  `stint_tyre_problems` refuses).
- A compound-less fuel-only stop shows on the Race page and the spine.
- A zero-lap first stint no longer takes the NO TYRES label.
- The judged-race voice test names its call and no longer accepts a declared
  gap.

**Its re-plan minor reversed pass 2 on the same line, and the answer is the
merge.** Pass 2: "No tyres." carried by position across a changed stop count
lands on a stop it was never made for. Pass 3: replacing it everywhere turns
a fuel-only plan into "RS on." on an offer that never mentioned tyres. **Same
stop count: the desk's decision stands. Changed count: the re-planner's
priced decision, the only one there is for stops the desk never saw.**

**Carried, with the reason:** an accepted re-plan that changes the count
still does not say "tyres on" in the offer's words. The box call says it at
each stop. The Race page plan line is not repainted after `adopt`, which
predates this row. The pack is at 690 of the test's 700 cap.

**2.7 - multi-class and BoP for Fuji.** The hub already said it and the app
dropped it: the Enduro's `carRegulations` carries **`bopEnabled: true`** and
`tuningAllowed: true`, and `regulations()` read only the power and weight
limits. Now:

- **Two nullable event columns**, `bop_enabled` and `tuning_allowed`, are
  added through the existing additive migration (1/0 from a real boolean, NULL
  where the hub is silent, never "no"). `list_events` hands them to Ludo with
  the limits and the series.
- **`initial` reads the hub's answer instead of asking.** It asks only where
  the hub is silent. **A BoP round refuses, by name, `top`, `fg`, the ratios,
  ECU output, the restrictor and ballast** (`SKILL.md`, `mechanic.md`, eval 10).
- **The car comes from the class he is assigned that round.**
  `race-planner.md` preflight 11 says so, and states the board: eight rows,
  overall. In a multi-class field some cars are always off it, and nothing on
  file shows GT7 marking class, so **no call or plan line claims a class
  position**.

**The Fuji plan on file:**
`brain/_inbox/setups/2026-09-26-porsche-963-fuji-enduro-initial.md`, an
`initial` document.

- **From the hub, read-only:** Gr.1 for this round, so the roster's **Porsche
  963 '24**. The field is **ten cars: 4 Gr.1, 3 Gr.3, 3 Gr.4**. No per-car
  override is set. The format is 120 minutes timed at 3x/2x, 1 L/s.
- **It carries the refusals.**
- **Its first deliverable is the settings screen to read**, because the 963
  has no range record.
- **It lists the runs** that turn it into evidence.
- **Not written to the database.** The event row is his act on the Calendar
  screen, and that is where the BoP flag enters.

**Still open in Phase 2 (updated 12 Sep):** 2.4, which waits for his yes;
2.6, 2.7 and 2.8, each closing on its critic's AGREED; 2.9, where `SKILL.md`
is at 968 lines against 450 and there are 14 evals against 20, and the "nine
documented failures" the evals are for are named nowhere - they wait for him;
and **2.12 - the MCP server is registered nowhere** (no `pitcrew` entry in `~/.claude.json`, no
project `.mcp.json`), which is a change to the user's configuration and
waits for his yes.

**The batch's own test found the defect under it, not the reading.**
`_worth_saying_again` silences a kind already in `said` for the whole stint,
so a stop that came back and then retired again would never have been
announced a second time — "told it was back on, he must be told again when it
is off" failed. Each reversal now clears the other's entry, so each can be
said once and neither twice in a row.

**Critic 4 on the redesign (`243b9c6`): NOT AGREED, two majors, fixed.**
(1) The hold started empty, so the first judged lap set it outright and a
retirement cost ONE lap - at the green, after a stop, after a re-plan -
where a reinstatement cost two: the asymmetry the redesign existed to
remove, reachable at every stint boundary. An unjudged stop is now the
plan's answer: `note_stop_need` starts from True and `_stop_needed_on_fuel`
reads True for a stop not yet judged, so taking any stop off needs the full
`STOP_FLIP_LAPS`. (2) Rule 12 across the hold: the box calls decided on the
held answer and took their reason from the arithmetic, so on a box lap the
hold still kept he heard "Box this lap." for the reason "Fuel is fine - the
tank covers the next stint." `_why_the_stop_is_held` gives `_box_now`,
`_box_soon` and `_stop_back` the reason of the answer that decided - "On
the plan." where the tank no longer keeps the stop. Minors: the four guards
that survived its mutation sweep (the reinstatement's `stops_off_said` and
`said` clears, the retirement's `STOP_BACK` and `stop_back_due` clears) are
pinned by an off-on-off-on sequence and a retire-before-told test;
`_a_stop_is_in_question` reads `stop_still_needed` rather than the raw box
lap. Five older tests built a "retired" stop as a bare state that was never
judged; they now retire it the way a race does. **Carried, with reasons:** a
stop moved late leaves the following stint fuelled for its full plan length
(over, never under); three reversals in six laps is the fastest the hold
allows, and whether that is too many is the driver's question.

**Critic 4 on `85522eb`: AGREED.** Nineteen scenarios driven through
`RaceCoordinator.handle` with `drop_stop` granted, every surface compared
lap by lap - voice, `laps_to_stop`, the snapshot, the PTT answer, the colour
tier, `_pending_stops`, the board's fuel block and `_a_stop_is_in_question` -
and not one disagreement. Retiring takes two judged laps everywhere: at the
green, after a stop, after a re-plan, in a timed race. Eleven of fourteen
mutants killed; the three that survive are equivalent (the reason calls only
fire while the hold keeps the stop). **Carried, as design questions for the
driver:** a box call inside the first two judged laps is followed by its
cancellation when the tank already reaches ("Box next lap." on lap 1, "No
more stops on fuel." on lap 2) - the hysteresis doing its job, and rare,
because a plan seldom puts a fuel stop that close; "Fuel is fine - the tank
covers the next stint." reads as reassurance where "No fuel - ..." would read
as the fill instruction it is (one clip, inside the pack's budget); and a
timed race's retirement is spoken unhedged before `laps_estimate_firm`.
**The clip is declined, and the earlier pass is why.** `_fuel_instruction`
chose "Fuel is fine" over "No fuel -" deliberately, and
`test_a_fill_below_what_is_aboard_is_not_an_instruction` pins it: under a
helmet a sentence that opens "No fuel" is an emergency until its second
half lands. Re-read before editing, as the standing order says - the two
critics were weighing different risks, and the one already paid for (a
driver hearing "no fuel") outranks a sentence that reads as reassurance.

**Storage pass 6 (critic 2 on `e640384`), one major, fixed.** An armed race
kept its status line but not its plan line: the desk approving plan B after
the arm repainted B's box laps under "running to the approved plan" while
the coordinator held A (rule 13). The armed/running return now sits above
`set_plan`. Its mutation sweep did not finish - the session limit stopped
it - and it is re-sent.

**Storage pass 7 (critic 2 on `85522eb`): NOT AGREED, one major, fixed.**
The guard held the plan line, and the poll went on marking the new plan
*seen* behind it - so after Stop nothing repainted, and the next Start armed
plan B under plan A's box laps: the pass-6 wrong line, carried past the
Stop and into a race that runs it. Three parts: `refresh_plan` records
nothing as seen while a race is armed or running; `stop_race` refreshes
once the race is gone (logged, never raised - `shutdown` comes through
there); and `start_race` paints the plan it arms, because a plan approved
moments before Start is inside the 15 s poll. The picker is disabled while
armed (its minor: it could read "No plan" over a race holding plan A). All
six of its mutants were killed on the earlier guards.

**Storage pass 8 (critic 2 on `e4d2486`): AGREED - the storage row is
done.** A plan approved while armed or running shows after Stop, a refused
Start paints and locks nothing, and all five mutants on the four new guards
are killed. Its three minors had one cause - three guards each deciding for
themselves whether a race owned the page - and are closed by one
expression, `_race_holds_the_page` (armed, running, or finished and not yet
stopped), read by the poll, the refresh and the seen-id: the flag no longer
lets the next poll paint plan B over the race that ran A; Start paints the
approved row before any refusal, so a refusal about B sits under B's line;
and the poll no longer rebuilds the Strategy page's cards every 15 s while
armed.

**Critic 5, pass 3 (on `e4d2486`): NOT AGREED, one major, fixed.** The
merge said step 1 "asks him nothing" and then asked for every phase of every
corner scored 1-5 - some forty prompted answers on a twelve-corner circuit,
before the telemetry, where spine step 4 allows four, after it. Step 1 is his
free, unprompted account now, which does ask nothing; the plan row's grid is
written into `SKILL.md` as open for the driver (grid before the data against
four questions after it), taken meanwhile only if he volunteers it or
inside step 4's four; and the phases are `driver-model.md`'s - entry, mid,
exit - where I had written an unnamed "four". Its minor: the tool's line
"never ... a line in a brief" settled for all three numbers what both skill
files leave open for lap one; it now says incidents and scatter never go in
a brief and lap one's place there is open.

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
