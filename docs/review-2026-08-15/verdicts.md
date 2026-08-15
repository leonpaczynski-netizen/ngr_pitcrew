# Adjudicated verdicts

## Verifier 1 — analysis (A) + export/prompts (X)

CONFIRMED: A1 P1, A2 P1, A3 P2, A4 P2, A5 P2, A6 P3, X1 P1, X4 P2, X5 P2
REJECTED:  X2, X3, X6

### Rejections and the guard that killed them
- **X2, X3 — REJECTED.** `grep -rn "add_setup_change"` returns the DAO definition and
  four TEST call sites, nothing else. No screen, controller or tool writes a
  `setup_changes` row. `list_setup_changes` returns `[]` for every real session,
  `driver_changes` is None, `payload.py:151` omits the key, `prompts/build.py:277` skips
  the block. The earliest-vs-latest split cannot occur with real data. The reviewer's
  `from_lap` shift caveat is unverifiable — with no writer there is no convention for
  what `from_lap` counts.
- **X6 — REJECTED.** `event_screen._on_save` (1145-1165) blocks `saved.emit` unless name,
  track AND car are all non-empty, and is the only emitter. `data/pitcrew.db` holds
  3 events, 0 with null/empty `car_name` or `track`. The `or "unknown"` fallbacks are dead
  defensive code. The two-paths-disagree observation is true but unreachable.

### Confirmations, with what the verifier ran
- **A1 P1 CONFIRMED — the wear delta.** Ran the real functions: lap 8 full read
  (`fl 0.30`), lap 18 rears-only (`rr 0.45`) → rate 0.015, method "two gauge readings
  inside one run", confidence **measured**, `modelled_stint_laps` **56**. Exactly as claimed.
  Partial reads are a DESIGNED input — `TyreGauge.clear()` (widgets.py:895) makes "unread"
  first-class and the contract says an unread corner stays null.
  Second half also reproduces: lap 8 `fl 0.55`, lap 18 `rr 0.42` → `rate` None and
  `unavailable_reason` says "the readings do not span any laps" (they span ten), discarding
  a usable single reading.
  **Verifier's additions:** (a) even with four corners read at BOTH ends,
  `max₁₈ − max₈ ≤ true worst corner's delta` — the arithmetic is biased toward
  UNDERSTATING w whenever the limiting corner changes identity, i.e. always toward the
  longer stint, which §5.1 calls the expensive direction; (b) w also sets
  `Plan.binding_constraint` via `max_stint_laps` (model.py:648,753) — the contract's
  "single most useful strategy output" — and gates the live `_tyre` call
  (race/calls.py:266-268), which at w=0.015 never fires in any realistic race.
  **Mitigation found:** `stint_limit` (model.py:614-616) caps per-compound stints at
  `longest_stint_laps`, so `build_plan` will NOT schedule 56 laps. But
  `wear.modelledStintLaps`, `binding_constraint` and the live call have no such cap.
- **A2 P1 CONFIRMED — race_span.** `read_clock` returns multiplier 0.0 (gameclock.py:120)
  and `race_span` gates on `is not None`. Frozen 15:00 practice, race declared 18:00 ×6 for
  50 min → `race_span (15.0, 15.0)`, `raceSpanHours 0.0`, `covered True`, note "Practice has
  run in every game hour the race passes through (15:00 to 15:00)."
  Mild case confirmed: practice ×1 vs declared ×6 → 0.83 h instead of 5 h, and
  `practice_clock_warning` returns None because evidence.py:494-497 hands it
  `reading.multiplier`, comparing practice against itself.
  **Nuance the verifier adds:** the FROZEN case does still trip the warning; only the
  ×1-vs-×6 case is fully silent. `start_hour` is overridden the same way — not called out
  by the original reviewer.
- **A3 P2 CONFIRMED.** `covered_hours` on laps carrying `tod_start_ms`/`tod_end_ms` but no
  frames returns `[]`; with one frame returns `[15.0]`. One-line fix.
- **A4 P2 CONFIRMED.** Three 10-lap RM runs + one 4-lap RS run → headline `wear_per_lap`
  0.1 (the RS rate), `modelled_stint_laps` 8, while `byCompound` correctly shows RM 0.03
  (3 stints) and `reference_compound` is RM. evidence.py:557-565 then prints
  "Tyre wear 10.0 % per lap" beside "Evidence compound RM — wear and fuel describe this
  compound only", which is false.
- **A5 P2 CONFIRMED, and worse than reported.** Reproduced `{5}`. The test
  (test_out_laps.py:71-77) DOES encode the bug, but its stated purpose survives any
  non-empty assertion so it is cheap to correct. **Verifier's addition:**
  `controller._rows_for_event` (1357-1359) re-asserts `row.is_out_lap = True` from
  `auto_out_laps` on EVERY rebuild, so the driver cannot restore the lap — the "a struck
  lap can be restored" mitigation does not apply.
  **Verifier corrects the proposed fix:** NOT "apply to all runs" (a mid-session refuel
  genuinely opens a real out-lap) — discard the first lap of any run that is also the
  first lap of a TIME_TRIAL session.
- **A6 P3 CONFIRMED, impact smaller than written.** The survivor is reduced by a median,
  so one extra short value shifts the answer ~one rank. Module explicitly unwired
  (m0.py:36). P3 is the ceiling; P4 defensible.
- **X1 P1 CONFIRMED.** The majority-vote fix WAS applied to the export path only
  (build.py:298-320); `_dominant_compound` still votes and `_session_line`
  (prompts/build.py:612-613) prints it beside a payload that omits `meta.compound`.
- **X4 P2 CONFIRMED.** `_clicks_and_percent('cam_f', -3.2, race_preset)` → `('-32','-32%')`
  against a preset minimum of 0.0. No range check anywhere — `SetupSheet.validate()` checks
  vocabulary, numeric type and gear order only.
  **Verifier corrects the write-up:** the `-2.4` in `returnRules*` is a number-FORMATTING
  example, legitimate for `toe_*` or `bb`; only `returnShape`'s `cam_f: -3.2` is a camber
  claim. The test fixtures adopt the wrong convention but their assertions test parse
  fidelity — correcting them is bookkeeping, not a behaviour change.
- **X5 P2 CONFIRMED** — genuine independent corroboration of S8. Merge, keep this
  write-up's extra evidence (EVENT_DEFAULTS already knows 20.0 is untouched;
  prompts/build.py:1002-1012 renders `[measured-this-track]`).

### NEW defects found during verification
- **N1 · P2 · prompts/context.py:373 — `_dominant_compound` is NON-DETERMINISTIC on a tie.**
  `max(set(tags), key=tags.count)` iterates a SET OF STRINGS, so PYTHONHASHSEED decides the
  winner. Six fresh processes over five RM and five RS laps returned `RM RS RM RS RS RS`.
  This is the identical bug `strategy/evidence.reference_compound`'s docstring (118-142)
  says was found and fixed there — **the fix was never carried across.** Two equal stints on
  two compounds is the normal shape of a comparison test, so the tie is the COMMON case.
- **N2 · P2 · feature gap — `setup.driverChanges` is unreachable end to end.**
  Schema (`setup_changes`, schema.py:132), DAO, model, export (build.py:353) and prompt
  (build.py:277-281) all exist; EXPORT-CONTRACT.md §3 calls mid-session changes "exactly
  the thing that invalidates a corner aggregate". **Nothing in the UI can create one.**
  This is the real finding behind the rejected X2/X3, and it is bigger than either: a
  corner aggregate spanning a mid-session ARB change is exported with no marker at all.
- **N3 · coverage — the strongest-confidence wear path has ZERO tests.**
  `grep -rn "start_reading\|gauge_readings" pitcrew/tests/` returns nothing; no test
  mentions `_has_delta` or `METHOD_GAUGE_DELTA`. The only branch that emits
  `confidence: "measured"` for a wear rate — the one A1 shows is wrong — is untested.
  Any fix for A1 needs tests built from scratch.

---

## Verifier 2 — store / controller (C)

CONFIRMED: C1 P1, C3 P2, C4 P2, C5 P2, C6 P2, C7 P3
DOWNGRADED: C2 P1 -> **P3**

- **C1 P1 CONFIRMED, both halves reproduced** against the real Store and the real
  `_save_sheet`. Saved a race and a qualifying sheet in the same second on a temp DB:
  `list_setup_sheets(car)[0]` returned the QUALIFYING sheet (ties on second-resolution
  `updated_at`, broken by `id DESC`; `_save_sheet` writes the form's sheet first and the
  pasted other half second). Ran the real `_save_sheet` twice with the form state
  `load_active_event` -> `event_screen.load` -> `_reset()` actually produces. Result:
  both rows `purpose=race`; `sheet_for(car,'race')` returns the QUALIFYING values;
  `sheet_for(car,'qualifying')` returns None.
  No test covers it: `test_sheet_pair.py` only ever calls `sheet_for`, never the
  `list_setup_sheets[0]` path `load_active_event` uses.
  **Fix correction: `sheet_for(car,"race")` is necessary but NOT sufficient** — the purpose
  flip survives via the `list_setup_sheets[0]` fallback for a car that has only a
  qualifying sheet. `event_screen.load` must ALSO set `sheet_purpose` from `sheet.purpose`.

- **C2 DOWNGRADED P1 -> P3. The crash is real code but NOT reachable with real data.**
  (a) TRUE: `LapRow` has no `frames`; reproduced the exact AttributeError at incidents.py:234.
  (b) TRUE: gate is `lost_s >= 3.0` inside a run with >=3 clean laps, and `stored_or_read`
      dereferences `lap.frames` before the `if`, so the ternary is no protection.
  (c) **FALSE in practice.** Copied the owner's real `data/pitcrew.db` (user_version 3,
      132 laps, 132 `lap_frames` rows), ran the real Store open which performed
      `_migrate_v5_incident_evidence`, then queried: `crawl_s IS NULL` -> **0 rows**.
      Ran the real `_rows_for_event` + `find_incidents` over all three events
      (91, 30, 11 laps): no crash.
  Going forward NULL is also unreachable on the live path: `record_frame` drops exactly the
  packets `SessionState.update`/`_check_lap` also refuse, and runs BEFORE `state.update` on
  the same packet (controller.py:181-187), so `rows` is always >=1 at LAP_COMPLETED and
  `add_lap` never writes NULL evidence. No tool inserts laps.
  Latent trap for a legacy/undecodable-blob DB only. Worth the one-line
  `getattr(lap, "frames", None)` fix, but **not a launch blocker.**

- **C3 P2 CONFIRMED.** `clock_source` written to 'measured' in exactly one place, never
  reset anywhere. Ran the sequence on a temp DB: measure 15.933 -> driver types 18.0 and
  saves -> `record_measured_clock` returns True and puts 15.933 back.
  Test claim correct: test_gameclock.py:255 starts from a never-set `clock_source`.
  **Fix nuance:** clear `clock_source` only when the value actually CHANGED, or a no-op
  re-save of a measured event needlessly freezes the measurement.

- **C4 P2 CONFIRMED, exact traceback reproduced:**
  `AttributeError: 'NoneType' object has no attribute 'adopt'` at controller.py:1670.
  `set_armed(False)` only relabels the Start button, so `offer_row` stays visible with
  Accept/Keep still connected. First dereference guarded, second not.
  **Fix must do both halves** — guard `self.race.adopt` AND have `stop_race` clear
  `_pending_replan`, `ptt.pending_replan`, `race_run_id` and call `hide_offer()`.
  Guarding alone leaves a dead Accept button that writes a revision against a finished run.

- **C5 P2 CONFIRMED, and worse than described.** Bound two UDP sockets to the same port
  with SO_REUSEADDR — **succeeded**, both in one process and across two processes. So
  `bind_error` stays None and `_report_health` never says a word.
  Delivery tested: on this box the **first-bound** socket keeps receiving and the new one
  gets nothing. So starting practice during a race leaves the NEW listener silent (health
  says "No telemetry") while the ORPHANED listener keeps feeding the shared bridge, whose
  `session_id` now points at the new session.

- **C6 P2 CONFIRMED.** `self.session_id = None` appears at only two sites (stop_practice
  1138, shutdown 1761). Chain verified real. **Blast radius narrower than written**: bites
  only when the rehearsal is the first run in the evidence ordering, because
  `auto_out_laps` only applies the TT exception to `runs[0]` — which is finding A5's bug.

- **C7 P3 CONFIRMED.** Not purely cosmetic: `_on_lap_changed` -> `carry_compound` runs over
  the mixed rack and writes `set_lap_compound` against real RACE `lap_id`s.

### NEW defect
- **N4 · P2 · telemetry/listener.py:202 — the "another copy of Pit Crew is already running"
  diagnostic can NEVER fire.** The bind-failure branch (205-210) logs exactly that message,
  but `setsockopt(SO_REUSEADDR, 1)` on the line above makes a second bind to the same UDP
  port succeed on Windows — verified across two separate processes. A second instance binds
  cleanly, receives nothing, and reports "No telemetry on 33741. Is GT7 running and SimHub
  relaying?" The app misdiagnoses a port conflict as a dead console — precisely what
  CLAUDE.md §7 exists to prevent. UDP has no TIME_WAIT so SO_REUSEADDR buys nothing here.

---

## Round 2, gap sweep A — validator / schema / settings (previously ZERO findings)

- **G1 · P2 · settings.py:119 — `speech_backend` and `speech_sensitivity` have NO control
  anywhere, and every Save silently rewrites them to their defaults.**
  `Settings` declares both, `validate()` enforces their enums, and the controller reads both
  when building the recogniser. But `SettingsScreen.values()` (settings_screen.py:432)
  constructs a fresh `Settings(...)` from the widgets and passes NEITHER, so both take the
  dataclass default. `settings.save()` (settings.py:212-218) then iterates `fields(Settings)`
  and writes EVERY field — so pressing Save persists `sapi`/`medium` over whatever was stored.
  **This compounds E2 directly:** E2 says the SAPI default ships with no UI to change it;
  G1 says even a stored non-default would be wiped by the next Save.
  Fix note: if the UI is deliberately not wanted, `values()` must carry current values
  through (`dataclasses.replace(self._loaded, ...)`) so Save cannot clobber a field the
  screen does not own.

- **G2 · P2 · export/build.py:305 — `meta.packet` falls back to the literal "A", asserting a
  packet format that was never received, and defeating the validator's required-field check.**
  `packet=session["packet_format"] or "A"`. `validate()` tests `if not meta.get(key)` then
  membership in `PACKET_FORMATS` — `"A"` satisfies both, so the refusal gate cannot see it.
  **Worse in kind than the rejected X6:** `"unknown"` is visibly not a car name, whereas
  `"A"` is a positive, well-formed claim that the 296-byte base format was captured. Per
  EXPORT-CONTRACT §2 the entire purpose of `packet` is to disambiguate a null channel
  between "not captured" and "not offered by this packet format" — so declaring `A` makes
  every absent extended channel (steering, surface type, current-lap ms) read as physically
  unavailable rather than unmeasured.
  Trigger: press Record while GT7 is not streaming, then Stop. `on_packet` never fires,
  `note_stream_facts` never runs, `sessions.packet_format` stays NULL. Export then succeeds
  (it requires a session row, not laps — build.py:243-245), `validate()` returns `[]`, and
  the file is written and copied with "0 laps copied to the clipboard".
  Confirmed the write path DOES block on `ExportRefused`, so the only way a bad payload
  ships is one that passes `validate()` — which this does.

- **G3 · P3 · export/payload.py:351 — the `refuelRateLps` refusal can NEVER fire.**
  `_validate_strategy` refuses when the key is `None` or `""`, but the only producer assigns
  `event["refuel_rate_lps"]`, a column declared `REAL NOT NULL DEFAULT 2.5`. Always a float,
  so the guard is unreachable from any app-built payload.
  The failure mode it was added for is not "the key is absent" but "the app default is
  standing in for a measurement", and that case ships silently. The prompts path already has
  the machinery (`EVENT_DEFAULTS`, context.py:37, 393-395 tags a default-equal value
  "still the app default — confirm it"); the export does not use it.
  Contract §16.2 calls this "the number that decides the race": on the measured Monza figure
  of ~1 L/s against the 2.5 default that is a 2.5x error in the stop count.

---

## Round 2, gap sweep B — large UI screens (previously ZERO findings)

- **G4 · P1 · controller.py:1463 — switching events leaves the PREVIOUS event's plans on the
  Strategy screen and in `self._plans`, so Approve files event A's plan against event B.**
  NEW — nobody was looking here. `self._plans`/`self._inputs` are assigned only inside
  `build_strategy` (writes at 1416, 1421, 1426), and `StrategyScreen.show_plans` is called
  only from there. Neither `switch_event` (382-425) nor `load_active_event` (351-381) clears
  them or the screen — both touch `event_screen`, `practice`, `car_screen`, `engineer` and
  never `self.strategy`.
  `approve_strategy` then reads `plan = self._plans[index]` (1469) but takes the event id
  and guard context from `self.active_event()` — now event B. So it writes A's stints, pit
  laps and export payload as B's approved strategy, stamped with B's car/track/layout/
  race_laps. **`payload['context']` therefore agrees with itself and the race-day guard
  passes.** Approve is still enabled because `show_plans` is what disables it and it never ran.
  The driver races to a plan computed from a different event's evidence.

- **G5 · P1 · ui/event_screen.py:1027 — `load()` never sets the `For` picker from the sheet
  it loaded.** **INDEPENDENT CORROBORATION OF C1, from the UI side.** `_reset()` puts
  `sheet_purpose` at index 0 (FOR_RACE) and `load()`'s `if sheet is not None:` block sets
  name, 23 editors, gears and build block but never reads `sheet.purpose`. `values()` then
  returns `'race'` whatever was loaded, and the upsert sets `purpose=excluded.purpose`.
  Verified against a real Store: after the save, `sheet_for(car,'qualifying')` returns None
  and both rows read `purpose='race'`.
  Note `sheet.py:41-50`'s docstring: purpose is None rather than defaulting to race, because
  "a sheet stored before the question existed has not answered it" — so the fix must fall
  back to index 0 ONLY when `sheet.purpose` is None.
  **Two reviewers reached this independently from opposite ends. Treat as high-confidence.**

- **G6 · P2 · ui/event_screen.py:187 — changing the track keeps the OLD track's layout and
  INJECTS it into the new track's layout list.** `_on_track_changed` calls
  `layout_edit.set_items(layouts)`, but `Picker.set_groups` snapshots `currentText()` before
  clearing and restores it with `setCurrentText(current)` — and `Picker.setCurrentText`
  ADDS the item when `findData` misses (widgets.py:740-744). The `elif len(layouts) == 1`
  branch only rescues single-layout circuits.
  Verified live: Le Mans / Full Course → change track to Alsace → Layout still reads
  "Full Course" and Alsace's dropdown now offers
  `['Village','Village (Reverse)','Test Course','Test Course (Reverse)','Full Course']`.
  `values()` returns `track='Alsace', layout='Full Course'`, written straight into the event.
  **31 of the catalogue's circuits have more than one layout.** Layout is what the station
  map, the track model and the rain list key on.
  Note the `Picker` docstring (widgets.py:637) claims "There is no way to add to it from
  here" and "the list is authoritative" — the code contradicts its own docstring.

- **G7 · P2 · ui/event_screen.py:567 — `Refuel rate` and `Pit loss` have NO empty sentinel,
  so fabricated defaults render in CRAYON and the evidence column swears he entered them.**
  Every other optional spin box on the screen (`pp_cap`, `extra_time`, `start_hour`,
  `time_multiplier`, all 23 setup editors) uses the `EMPTY` sentinel with
  `setSpecialValueText('—')` and `struck_when_empty`. These two are constructed with
  `setValue(2.5)` / `setValue(20.0)` on ranges with no sentinel.
  Verified live on a brand-new event: both painted `#A3E635` (CRAYON) while `pp_cap` beside
  them is `#807870` (STRUCK). They reach `evidence.py:571` which emits
  `Evidence("Pit loss", "20.0 s", DECLARED, "a track constant")` unconditionally.
  **So the Strategy evidence column — the one surface whose whole job is saying which inputs
  are measured and which are guesses — paints a number nobody entered in crayon and captions
  it "entered".** Pit loss sets the cost of a stop and therefore the stop count.
  The app already knows better elsewhere: `EVENT_DEFAULTS` (context.py:37, 393-395) tags a
  default-equal value "still the app default — confirm it". The two paths disagree.
  **This is the root cause behind S8/X5** — those found the export lying about provenance;
  this finds the UI lying about it too, from the same absent sentinel.

- **G8 · P2 · ui/strategy_screen.py:371 — a REFUSED rebuild leaves the previous plan's race
  time and stop count on the spec line, in 23px derived purple above "No plans yet".**
  `spec.clear()` and every `spec.add(...)` sit inside `if plans:`; the `else:` at 402 only
  hides the crossover band. `controller.build_strategy` catches `StrategyImpossible`, calls
  `show_plans([], ...)` and `set_status(warn=True)`, and returns before reaching `.note(...)`.
  Verified live: plate reads "No plans yet", subtitle reads the refusal, Approve disabled —
  and the spec line still reads `Plan 2-stop RM/RM · Race time 48:12 · Limited by tyres` at
  DATA_LARGE_PX bold, footer still "Every input measured."
  **The two largest pieces of text on the screen describe a plan the app has just refused to make.**

- **G9 · P2 · ui/event_screen.py:329 — the dirty-form switch guard compares event ids with
  `is not`, so above id 256 the event can NEVER be switched to.**
  `target = itemData(index)` round-trips through a C++ QVariant and returns a FRESH Python
  int each call; identity holds only because CPython caches small ints.
  Verified live: with ids 1 and 2, `itemData(idx) is itemData(idx)` is True and the
  arm/release sequence works. With ids 900 and 901 it is False and the first, second and
  third clicks all re-arm — `switched` never fires, the picker snaps back every time.
  With unsaved edits the event becomes unreachable; only Save or Discard exits.
  Event ids are sqlite rowids and are never reused, so this arrives after 256 events have
  been created over the app's life, not at 256 concurrent events.
  Fix must keep the `_UNSET` sentinel (it exists so None can be a real target) but compare
  by value.

- **G10 · P3 · ui/event_screen.py:1161 — `_on_save`'s "and go there" focus call is a no-op
  for Track and Car.** Those are `Picker`s — plain QWidgets wrapping the combo, default
  `NoFocus` — so `setFocus` does nothing. Verified: `track_edit.focusPolicy()` is 0, and
  after `_on_save` neither the picker nor its combo has focus. Only `ensureWidgetVisible`
  does its half. The comment at 1155-1159 says this path exists because "the message named
  the problem and left him to hunt for it". Fix: `setFocusProxy(self.combo)` in `Picker.__init__`.

- **G11 · P3 · ui/car_screen.py:374 — `read_ranges` accepts an INVERTED min/max pair and
  saves it as a hard slider limit.** Checks both bounds are present but never that
  `low < high`. Verified live: Min 200, Max 50 for `rh_f` → `saved` fires with
  `{'rh_f': [200.0, 50.0]}`, no warning. `percent_of_range` (sheet.py:173-176) and
  `prompts/build.py:113` both divide by `high - low` and both guard only `high == low`, so
  every percentage quoted against that key comes out negative.
  Rule: CLAUDE.md §4.6. Reaching it needs a transposition while copying 22 pairs of numbers
  by hand off the car's settings screen — which is exactly what this screen is for.
