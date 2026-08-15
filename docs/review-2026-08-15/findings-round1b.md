# Round 1 findings, part 2 — analysis, export/prompts, store/controller

Same rules as part 1: claims and pointers only. Verify each from source yourself.

---

## AREA: analysis (pitcrew/analysis/*)

**A1 · P1 · analysis/wear.py:115 — the two-reading wear delta subtracts two DIFFERENT corners' fractions.**
`RunWear.rate` takes `_has_delta` whenever a run has two gauge readings and computes
`(self.reading - self.start_reading) / gap`. Both operands are `LapInput.worst_wear` =
`max()` over only the corners the driver actually read on that lap (session.py:135-143),
so the two ends of the subtraction need not be the same corner. Result is labelled
`method: 'two gauge readings inside one run'`, `confidence: 'measured'` — the strongest
pair the module emits — and feeds `modelled_stint_laps` directly.
Claimed repro: lap 8 reads all four (worst fl 0.30), lap 18 reads only rears (worst rr 0.45)
→ rate 0.015, `modelled_stint_laps` = **56 laps**, while the front-left is actually done
by ~lap 22. That is a plan running the limiting corner to ~210% consumed.
Second bug, same line: if the later reading's worst corner is LESS worn than the earlier
one's, `rate > 0` fails → returns None *without* falling through to the single-reading
path, and `unavailable_reason` (wear.py:155) then says "the readings do not span any laps"
which is false — they span ten.
Downstream: `wear.modelledStintLaps` in the export; `wear_per_lap` → evidence.py:453 →
`RaceInputs.wear_per_lap` → `tyre_limited_laps` (`0.85/w`) and race/calls.py:268.
**This is the app's central claim (CLAUDE.md §3.3 fact 1 — there is NO wear channel).
Verify it with the most care of anything in this review.**

**A2 · P1 · analysis/gameclock.py:246 — `race_span` uses the PRACTICE multiplier as the race's.**
`race_span` overwrites the driver-declared `declared_multiplier` with `reading.multiplier`,
measured off practice laps. The module's own docstring says practice frequently is NOT run
at the race's clock, and `practice_clock_warning` exists in the same file to report that
mismatch. A frozen practice session measures 0.0 — not None — so it wins, and
`end = start + (minutes * 0.0)/60` collapses the race span to a single instant.
Claimed repro: declared 18:00 ×6 for 50 min, practice frozen at 15:00 →
`race_span` returns (15.0, 15.0); `coverage` returns `covered: True`, `raceSpanHours: 0.0`,
note "Practice has run in every game hour the race passes through (15:00 to 15:00)".
The race actually runs 18:00→23:00 and none of it has been driven. Milder common case:
practice at ×1 vs declared ×6 → 0.82 h span instead of 5 h.
Safety net also disabled: evidence.py:494-497 passes `reading.multiplier` as
`practice_clock_warning`'s `race_multiplier`, so the warning compares practice against
itself and returns None.
**Cross-check against the memory note that the cached Monza `track_clock` row was poisoned.**

**A3 · P2 · analysis/daylight.py:50 — `lap_hour` reads only decoded frames, so `practiceHours` is empty on the strategy path.**
`lap_hour` looks for `time_of_day_ms` inside `lap.frames` only. Every lap also stores
`tod_start_ms`/`tod_end_ms` on the row precisely so it can be read without decoding —
`gameclock._stamps` (78-89) was changed to prefer that pair for exactly this reason.
But `strategy/evidence.py:_laps_to_hydrate` (105-110) only hydrates rows where
`row['compound']` is truthy, capped at 6 per compound. So with untagged compounds no lap
gets frames, `covered_hours` returns `[]`, and the app tells the driver "No lap on record
carries a time of day … run a practice session to put evidence on the map" — right after
he ran one, on laps that all carry `tod_start_ms`. Partial hydration is quieter and worse:
`uncoveredHours` lists hours he has already driven.

**A4 · P2 · analysis/wear.py:342 — `wear_per_lap` returns `rates[-1]`, i.e. whichever run was last, ignoring compound.**
No docstring or comment says it does this, in a module that justifies every other choice
at length. Not filtered by compound, so the headline wear rate can be measured on a
compound the plan is not built on. The same module aggregates the same quantity a second,
different way in `wear_rate_by_compound` (mean of that compound's runs, wear.py:246), so
two figures for one tyre disagree inside one payload.
Claimed repro: three long RM runs then a short RS run → `reference_compound` picks RM so
the screen prints "Evidence compound: RM — wear and fuel describe this compound only",
while the Tyre wear row beside it prints the **RS** rate, `max_stint_laps` caps with
`0.85/w_RS`, and `RaceCoordinator` is armed with it (controller.py:1526).
Rule: §4.4 (no sample count, hides how many runs were discarded), §4.5.

**A5 · P2 · analysis/runs.py:469 — the time-trial out-lap exception is applied only to `runs[0]`.**
`auto_out_laps` strikes the first lap of every run then discards that strike only for
`runs[0]`. `practice_mode` is per-session and joined onto every lap; an event export
concatenates all practice sessions, each opening a new run via `starts_run`'s
`session_changed` branch. So session 2+ of a declared time trial has its opening lap —
which GT7 times from the line, and which the module's own docstring says is the fastest
lap of the session in six of eight recorded time trials — struck as an out-lap.
Claimed repro: two TT sessions, laps 1-4 and 5-8 → `auto_out_laps == {5}`. Lap 5 leaves
`counted` so it cannot be `session.bestLapMs`, cannot enter `green_lap_reference_ms`, and
is missing from the pace and fuel medians.
Note the reviewer's own caveat: `test_going_back_to_the_garage_opens_a_run` asserts `{4}`
for this shape and would need updating — decide whether the test encodes the bug.

**A6 · P3 · analysis/m0.py:303 — `_green_lap_s` trims the shortest and longest DURATIONS while its comment claims it drops the capture's first and last LAPS.**
`clean` is a list of durations sorted ascending, not laps in capture order, so `clean[1:-1]`
removes the quickest and slowest lap of the session. Both partial end-laps are short, so at
most one is removed and the genuinely slowest clean lap is discarded in its place. The
surviving partial biases the green reference low, inflating the `pitLaneDeltaS` written
into the provenance-tagged constants file the driver reads to set the event's pit loss.
Contained: the module states it is not wired into the strategy path.

---

## AREA: export / prompts / setup (pitcrew/export/*, prompts/*, setup/*)

**X1 · P1 · prompts/context.py:373 — the prompt's Session line declares ONE compound by majority vote, contradicting the payload beneath it.**
`_dominant_compound` returns `max(set(tags), key=tags.count)` and `_session_line` prints it
as `compound **RM**`. This is exactly the vote contract 1.4 removed from `meta.compound`;
the payload in the same document correctly omits `meta.compound` and lists
`meta.compoundsRun: ["Racing Medium","Racing Soft"]`. Prose and JSON in one document state
mutually exclusive things about which rubber ran, and the prose is what gets read.
Contrast export/build.py:298-320 which deliberately refuses the vote, with a comment
saying voting made a three-compound session read as a Racing Hard one.
**This matches the memory note that `meta.compound`'s majority vote was the fabrication —
check whether the fix was applied to the export path only and the prompt path missed.**

**X2 · P2 · export/build.py:353 — `setup.driverChanges` only ever carries the EARLIEST session's changes.**
`build_event_export` aggregates laps from every practice session but takes its `session`
from `_merged_session(sessions)` = `dict(ordered[0])`; only `packet_format`,
`car_category`, `fuel_capacity_l`, `setup_sheet_id`, `practice_intent`, `practice_mode`
are merged — `id` is not. `list_setup_changes(session["id"])` (db.py:240,
`WHERE session_id = ?`) therefore reads one session. A change made in run 2 or 3 is
dropped while `corners`, `laps` and `session` in the same payload span all runs.
Claimed repro: `arb_r 4→3` in run 1, `arb_f 6→5` in run 2 → only the `arb_r` change exports.
Note the reviewer's fix caveat: because `event_lap_inputs` renumbers laps continuously,
each change's `from_lap` must be shifted by the laps in preceding runs or `fromLap` will
index a different numbering than `laps[].lap`. **Check that shift is actually needed.**

**X3 · P2 · prompts/context.py:321 — the prompt's driver-changes PROSE and the JSON inside the same prompt name DIFFERENT changes.**
`gather` picks the *latest* practice session (`sorted(...)[-1]`) for
`context.driver_changes`; the payload a few lines down is built by `build_event_export`
which reads the *earliest*. Claimed repro: prose "from lap 2: `arb_f` 6 → 5" against
payload `[{'fromLap': 3, 'key': 'arb_r', ...}]`. Two irreconcilable configurations in one
document. Same root as X2.

**X4 · P2 · prompts/templates.json:33 — the return-shape template asks for NEGATIVE camber, which the app's own vocabulary and the contract define as 0-and-up.**
`shared.returnShape` shows `"cam_f": -3.2`; `returnRules*` give `-2.4` as the model number.
`setup/parse.py:265-269` stores whatever came back verbatim — `SetupSheet.validate()`
(sheet.py:55-81) checks vocabulary, type and gear order only, never the range record.
GT7 enters camber as a positive magnitude: the app's own preset is `cam_f: [0.0, 10.0]`,
the contract's examples are `[0, 6]` and `cam_f: 1.2`, and both real payloads in `exports/`
carry `cam_f: 1.0`.
Claimed repro: `_clicks_and_percent('cam_f', -3.2, race_preset)` → `('-32', '-32%')` — the
driver is shown front camber at −32 clicks / −32% of a slider whose minimum is 0.0, and the
export emits a value he cannot enter in GT7.
`test_reply_contract.py:41` asserts `cam_f == -3.2` — **the test encodes the bug.**

**X5 · P2 · strategy/model.py:357 — `pitLossSource` hard-coded "measured-this-track".**
DUPLICATE of S8 from the strategy reviewer, found independently. Merge them. This one adds:
`prompts/context.py:37 EVENT_DEFAULTS` knows 20.0 is the untouched default, and
`prompts/build.py:1007-1012` renders it as `` `pitLossS`: **20** [measured-this-track] ``.
Two independent reviewers reaching the same finding is corroboration — say so.

**X6 · P3 · export/build.py:302 — `meta.car`/`meta.circuit` fall back to the literal "unknown", defeating the validator's own refusal.**
`car=event["car_name"] or "unknown"`, `_circuit_name` → `track or "unknown"`.
`payload.py:190-192` only checks the keys are non-empty, so "unknown" passes and the export
is written with a car name that is not a GT7 car. `controller._on_save_event`
(458-484) applies no car-name requirement. The prompt path already refuses this case
(`PromptRefused`, prompts/build.py:1194-1197) — **the two paths disagree about whether a
car-less event is exportable.** Rule: CLAUDE.md §7 "refuse to export rather than export
something wrong."

---

## AREA: store / controller / app (pitcrew/store/*, controller.py, app.py, settings.py)

**C1 · P1 · controller.py:371 — the Event screen loads whichever sheet was saved LAST, not the race sheet, and re-saving rewrites the qualifying sheet as the race sheet.**
`load_active_event` takes `list_setup_sheets(car)[0]` and passes it to `event_screen.load`
without looking at `sheet.purpose`, though `Store.sheet_for(car, purpose)` exists for
exactly this and IS used by `open_practice_session` (controller.py:1059).
`list_setup_sheets` orders `updated_at DESC, id DESC` (db.py:216-228) and `_save_sheet`
writes both halves of a pasted pair inside the same second, so the second-written sheet
(normally qualifying) sorts first. `event_screen.load` calls `_reset()` which sets the
"For" combo back to Race (event_screen.py:961), then fills the editors from the qualifying
sheet. The next Save round-trips those values with `purpose='race'`, and
`save_setup_sheet`'s `ON CONFLICT(car_name, sheet_name) DO UPDATE` (db.py:184-189) flips
the stored qualifying row's purpose to race.
Claimed repro: after a second save the DB holds both sheets as `purpose=race`;
`sheet_for(car,'race')` returns the QUALIFYING setup and `sheet_for(car,'qualifying')`
returns None. `open_practice_session` files `setup_sheet_id` against it, so the export's
"setup as run" for a race session is the qualifying tune.
Rule: CLAUDE.md §6 — the setup as run is the highest-value section of the export precisely
because it removes ambiguity about which sheet produced these symptoms.

**C2 · P1 · controller.py:1364 — `_rows_for_event` raises AttributeError on any lap with null incident evidence, so the app dies on launch.**
`find_incidents(rows, stored_or_read)` is called with `LapRow`. When stored
`crawl_s`/`off_track_s`/`spin_s` are all NULL, `incidents.evidence_of` returns None and
`stored_or_read` (incidents.py:225-234) falls through to
`read_evidence(lap.frames) if lap.frames else Evidence()`. `LapRow`
(practice_screen.py:95-146) declares the three evidence fields but **has no `frames`
attribute** → AttributeError. The export path survives only because it passes `LapInput`,
which does have `.frames` (build.py:139).
Null evidence is not an accident: `_migrate_v5_incident_evidence` (schema.py:535-572)
deliberately leaves those columns NULL for any lap with no `lap_frames` row and any lap
whose blob will not decode (`except Exception: continue`).
Reached only for laps past the 3.0 s TIME_LOSS_S threshold, which is why fixtures miss it.
Fires inside `_rows_for_event` → `load_active_event` → `PitCrewController.__init__`, so
**the window never opens and the driver sees the app die on launch.**
**This is the highest-consequence finding in the review if it holds. Verify hard —
especially whether a real DB can actually contain such a lap.**

**C3 · P2 · store/db.py:148 — `update_event` never resets `clock_source`, so a hand-corrected start hour is silently overwritten by the next session.**
`record_measured_clock` (db.py:385-395) protects a typed value by refusing to write when
`clock_source != 'measured'`, but nothing ever moves `clock_source` back off `'measured'`.
`_on_event_saved` (controller.py:473-481) writes `start_hour`/`time_multiplier` through
`update_event`, which touches only the columns given plus `updated_at`.
Claimed repro: measured 15.933 → driver types 18.0 → saved, but `clock_source` still
'measured' → next `_learn_clock` (controller.py:1186) puts 15.933 back.
Existing test (test_gameclock.py:255) only covers the never-set case, so it passes.
Rule: CLAUDE.md §4.1, and schema.py:352-356's own comment about not overwriting his
declaration.

**C4 · P2 · controller.py:1670 — accepting a re-plan after End race dereferences `self.race`, which `stop_race` set to None.**
`stop_race` sets `self.race = None` but leaves `_pending_replan` set, leaves `race_run_id`
set, and never calls `race_screen.hide_offer()` — so Accept / Keep stay visible and live.
`_resolve_replan` passes its `race_run_id is None` guard, guards the FIRST dereference
(`self.race.state.lap if self.race else 0`) and leaves the SECOND unguarded
(`self.race.adopt(...)`). The `if self.race else 0` on the line above proves None is
expected there. Propagates out of a Qt slot through `diagnostics._excepthook` and PyQt
aborts the process — **the app dies immediately after a race, before the outcome is exported.**

**C5 · P2 · controller.py:1541 — starting a race or practice while another is open orphans the first session and leaks its listener.**
Neither `start_practice` nor `start_race` checks for an open session; both assign over
`self.session_id` and `self.listener`. Previous session never gets `ended_at`; previous
`UDPListener` never `stop()`ped — and `SO_REUSEADDR` (listener.py:202) lets the duplicate
UDP bind succeed on Windows rather than failing loudly. Worse in the practice-during-race
direction: `self.race` stays non-None so `_on_race_event` keeps feeding practice laps to
the `RaceCoordinator`, which speaks calls and writes them into the still-open race run.
Nothing disables either button while the other runs. Consequence surfaces later as
`_close_orphaned_sessions` (controller.py:859-882) reporting "the app did not shut down
cleanly" when it did.

**C6 · P2 · controller.py:1586 — `stop_race` leaves `self.session_id` pointing at the closed race session.**
`stop_practice` clears it (controller.py:1135-1138); `stop_race` does not. Every handler
that writes "to the open session" then writes to the race row. `_on_practice_mode`
(1265-1266) and `_on_practice_intent` (1281-1282) do exactly that with no kind check, and
both picker signals fire on `currentIndexChanged` (practice_screen.py:618, 637).
`list_evidence_laps` (db.py:530-541) selects `sessions.practice_mode` for rehearsal race
sessions and `auto_out_laps` consumes it, so a rehearsal's opening lap can stop being
treated as an out-lap in the evidence the strategy is built from.
`shutdown()` also re-stamps `ended_at` on the already-closed session.

**C7 · P3 · controller.py:1241 — race laps are appended to the Practice screen's rack and numbered as a continuation of practice.**
`_on_lap_completed` is connected for every session kind (controller.py:255) and
unconditionally calls `practice.add_lap(... lap_num=len(self.practice.rows()) + 1 ...)`.
`_rows_for_event` filters on `kind='practice'` so the rows vanish on the next rebuild —
the two paths disagree about what the rack contains. `stop_practice` counts
`practice.rows()` and reports "N laps recorded"; `_on_lap_changed` runs `carry_compound`
over a rack mixing practice and race laps.
