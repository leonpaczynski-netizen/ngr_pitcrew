# GT7 VR Dashboard — Master Testing Register

> Last updated: 2026-06-26 (Group 17U — Track Library Schema and Seed Data Registry — 2329 pass / 5 skip / 0 fail — 83 tests in test_group17u_track_library_schema.py)
> Read PROJECT_STATE.md first, then this file, before touching any code.

---

## Open Defects

### P1 Critical

---

**ID:** DEF-P1-001
**Title:** Session opens on first lap completion, not on mode selection
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_on_live_mode_changed()` in `ui/dashboard.py` now calls `_db.open_session()` immediately and pushes the session id to the dispatcher via `set_session_id()`. Auto-open logic removed from `EventDispatcher._dispatch()`. `EventDispatcher` gains a `tracker` parameter (fixes latent `AttributeError`). RACE_STARTED retains a fallback open only when `_session_id == 0`.
**Description:** `open_session()` was triggered by the EventDispatcher on the first LAP_COMPLETED event, not when the user selects a Live mode. `_autosave_db` was never set to `True` so the entire DB write path was dead code.
**Expected Behaviour:** When the user changes the Live tab mode selector (Practice / Qualifying / Race), the dashboard immediately calls `_db.open_session()` and stores the resulting `session_id`. All subsequent lap saves use that session. No lap is ever written with `session_id = 0`.
**Acceptance Criteria:**
- Select Practice mode on the Live tab before any lap has completed.
- Query `SELECT id, session_type FROM sessions ORDER BY id DESC LIMIT 1` — a row exists immediately (before any lap).
- Outlap is saved with the correct `session_id` and `session_type = 'practice'`.
- Switching from Practice to Race opens a new session row with `session_type = 'race'`.

---

**ID:** DEF-P1-002
**Title:** Outlaps silently discarded after pit exit
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** DEF-P1-001 fix (session opened on mode change) ensures `session_id > 0` when the outlap fires. The stale print statement in `_exit_pit()` corrected to read "will be recorded as out-lap". State.py already records outlaps with `is_out_lap=True`; the only barrier was `session_id == 0` causing `write_lap()` to be skipped — now resolved.
**Description:** `telemetry/state.py` detects an outlap after a pit exit and silently drops the lap record with a print statement. The lap time is non-zero and valid for tyre warm-up analysis. The spec requires outlaps to be recorded and labelled, not dropped.
**Expected Behaviour:** Outlaps are recorded with `is_out_lap = True` and written to `lap_records`. They are displayed in Practice Review with a visual indicator (e.g., "(out)" suffix or distinct row colour). The lap time is preserved for AI and tyre temperature analysis.
**Acceptance Criteria:**
- Complete an outlap after a pit stop in Practice mode.
- `SELECT lap_num, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` — the outlap row exists with `is_out_lap = 1`.
- Practice Review displays the outlap row with a distinct style or label.
- AI coaching does not use the outlap for pace benchmarking (excluded from best-lap calculations).

---

---

**ID:** DEF-P1-003
**Title:** Practice Review "Save Session" crashes with AttributeError on _lbl_bank_status
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_set_bank_status(self, msg: str)` helper with `hasattr` guard to `ui/dashboard.py`. Replaced all 20 bare `self._lbl_bank_status.setText(` calls throughout the file with `self._set_bank_status(` using replace_all. Method returns silently when `_lbl_bank_status` is absent. `_refresh_lap_bank()` already had its own guard and was unaffected.
**Reported:** 2026-06-21
**Root Cause:** SUP-002 (P6-A) removed `_build_practice_lap_bank_group()`, which created `self._lbl_bank_status` at line 3680. The "Save Session" button at line 6298 still calls `_save_session_to_db()`, which references `self._lbl_bank_status` at lines 2841, 2856, and 2865 without a `hasattr` guard. Only the early-exit path at lines 2817/2822 has the guard. The first unguarded reference at line 2841 raises `AttributeError: 'MainWindow' object has no attribute '_lbl_bank_status'`.
**Description:** Clicking "Save Session" in Practice Review crashes the application. The status label widget was removed as part of the P6-A session-loader removal but the save method was not updated to match.
**Expected Behaviour:** Saving a session succeeds silently or displays a status message in an appropriate location. Application does not crash.
**Acceptance Criteria:**
- Click "Save Session" in Practice Review with at least one live lap in the table. Session is saved to DB. No crash.
- If save fails, an error is shown (QMessageBox or equivalent) rather than raising an unhandled exception.
- `SELECT * FROM sessions ORDER BY id DESC LIMIT 1` reflects the newly saved session.

---

**ID:** DEF-P1-004
**Title:** Practice Analysis AI prompt uses wrong race type — timed race shown as 1-lap race
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `race_type: str = "lap"` and `duration_mins: int = 0` optional fields to `RaceParams` dataclass in `strategy/ai_planner.py`. In `_run_practice_analysis()` (`ui/dashboard.py`), added `"race_type": _psc.get("race_type", "lap")` and `"duration_mins": int(_psc.get("race_duration_minutes", 0))` to the `race_params` dict. In `_build_practice_prompt()`, added `race_len_line` local variable that branches on `params.race_type`: timed → `"Race duration: {duration_mins} minutes (Timed Race)"`, lap → `"Race length: {total_laps} laps"`. Template uses `- {race_len_line}` instead of the hardcoded string.
**Reported:** 2026-06-21
**Related:** DEF-P3-004, Addendum A1
**Root Cause:** `RaceParams` dataclass (`ai_planner.py` line 69) has `total_laps: int` but no `race_type` or `duration_mins` field. `_run_practice_analysis()` (`dashboard.py` line 3096) always passes `total_laps = int(_psc.get("total_laps", 25))` regardless of race type. When the active event is a timed race, `total_laps` may be 1 (the laps spinbox default if the user never set it) or any incorrect value, because the laps field is not disabled for timed races (DEF-P3-004 unfixed). `_build_practice_session_prompt()` in `ai_planner.py` uses `params.total_laps` with no timed-race branch, producing "Race length: 1 laps" in the AI prompt.
**Description:** Event Planner is configured as Timed Race. Full Practice Analysis prompt tells the AI "Race length: 1 laps." All strategy recommendations are based on a 1-lap race rather than the correct duration. Confirmed by AI prompt evidence: "Race length: 1 laps."
**Expected Behaviour:** Practice Analysis prompt must respect the active event's race type. For timed races, prompt contains "Race duration: X minutes, Timed Race" and no lap count. For lap races, prompt contains "Race length: N laps."
**Acceptance Criteria:**
- Set Event Planner to Timed Race, 40 minutes. Set event active. Run Practice Analysis.
- AI prompt (via `GT7_AI_DEBUG=1`) contains "Timed Race" and "40 minutes" — not "1 laps."
- Set Event Planner to Lap Race, 25 laps. Set event active. Re-run. Prompt contains "25 laps."

---

**ID:** DEF-P1-005
**Title:** Practice Analysis AI prompt sends full setup including BoP-locked fields
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12a) — Root cause confirmed: `_psc.get("tuning", True)` default in `_run_practice_analysis()` caused tuning_locked=False when "tuning" key absent from config (old config, or silent exception). Changed to `False` default (absent key = locked = safe). Also fixed `except Exception: pass` → traceback logging. Debug print added (GT7_AI_DEBUG).
**Fix:** Added `tuning_locked: bool = False` and `allowed_tuning: list = field(default_factory=list)` to `RaceParams` dataclass. Added `_TUNING_CATEGORY_KEYS` and `_ALL_TUNING_CATS` constants to `ai_planner.py`. `_build_practice_prompt()` now: when `tuning_locked`, appends `## EVENT RULES — TUNING LOCKED` block and replaces setup block with locked notice; when `allowed_tuning` is set, appends `## EVENT TUNING RESTRICTIONS` block and filters setup dict to only pass allowed keys to `format_setup_for_prompt()`. `_run_practice_analysis()` in `dashboard.py` now populates `tuning_locked` and `allowed_tuning` from `_psc` (strategy config). See tests `TestBoPPromptRestrictions` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P2-007, Addendum A2
**Root Cause:** `_run_practice_analysis()` (`dashboard.py` line 3126) calls `self._current_setup_dict()` which returns ALL setup fields unconditionally. It does not pass `tuning_locked` or `allowed_tuning` to `analyse_practice_session()`. The `ai_planner.analyse_practice_session()` function has no parameters for BoP or tuning restrictions and builds its prompt without any constraint block. Contrast with `build_combined_setup_response()` in `driving_advisor.py` which does accept `allowed_tuning` and `tuning_locked`. The practice analysis is on a completely separate prompt-building path that has never had constraint injection implemented.
**Description:** Event is configured as BoP with tuning not allowed. The Practice Analysis AI prompt includes full setup fields: ride height, springs, dampers, ARB, camber, toe, aero, LSD, ballast, power restrictor, gear ratios. AI produces setup change recommendations for fields that are locked by BoP. Confirmed by AI prompt evidence showing full setup payload.
**Expected Behaviour:** When `_config["strategy"]["bop"] = True` and `tuning = False`, the practice analysis prompt excludes editable setup fields and contains a `## EVENT RULES — TUNING LOCKED` block instructing the AI to give driving advice only. When categories are partially restricted, only allowed fields are included.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Run Practice Analysis.
- Prompt debug output does not contain ride height, spring rate, aero, LSD, or gear ratio values as editable recommendations.
- Prompt contains "TUNING LOCKED" or equivalent instruction.
- AI response contains no suspension/aero/differential change recommendations.

---

**ID:** DEF-P1-006
**Title:** Tyre compound lap counts in AI prompt do not match Practice Review lap log
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Three-part fix: (1) `_add_bank_lap_row()` in `dashboard.py` now prefers the DB-supplied `compound` value over any existing `_lap_compound_tags` entry for the same lap number. (2) `_import_bank_session()` clears stale `_lap_compound_tags` entries for laps being loaded before populating them. (3) `get_session_laps()` in `session_db.py` already returns `compound`; `_add_bank_lap_row()` now correctly uses it. See `TestCompoundTagPreference` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P3-003, Addendum A4
**Root Cause:** `_run_practice_analysis()` (`dashboard.py` line 3107) reads compounds from `_compound_at_row(row)`, which reads the QComboBox widget at col 13. For laps loaded from History, `_add_bank_lap_row()` populates the compound from `lap.get("compound") or ""`. FIX-012 (AWR-005) added compound write to `write_lap()`, but AWR-005 has not been runtime-verified — compounds may not have been persisted to DB for the tested session. When loaded from history, laps with empty compound fall through to the `_lap_compound_tags` inheritance chain or `_default_lap_compound`, which may assign all laps the same default. Additionally, `_lap_compound_tags` persists across session loads and can carry stale data from a previous session, overriding the correct DB values for reloaded laps.
**Description:** Practice session contained significantly more laps on Racing Medium than Racing Soft. AI prompt reported RM: 7 laps, RS: 17 laps — approximately the reverse of actual. AI strategy was based on entirely wrong compound distribution. Confirmed by AI prompt evidence.
**Expected Behaviour:** `lap_data_by_compound` passed to AI must exactly match the compound assignment visible in the Practice Review lap table at the time the analysis is run.
**Acceptance Criteria:**
- Load a session with 15 RM laps and 7 RS laps into Practice Review. Verify visually in the table.
- Run Practice Analysis. Prompt (via debug) shows `"RM": 15, "RS": 7` (or equivalent names).
- Reloading the session does not change compound assignments.

---

**ID:** DEF-P1-007
**Title:** Strategy Builder fuel burn (3.0 L/lap) disagrees with Practice Review lap log (>4.0 L/lap)
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_loaded_session_avg_fuel: float = 0.0` attribute to `MainWindow`. `_import_bank_session()` computes the average fuel used across non-pit laps from the loaded session and stores it in `_loaded_session_avg_fuel`. `_computed_fuel_burn_lpl()` now uses a three-level priority: (1) `_loaded_session_avg_fuel` if > 0, (2) `self._tracker.avg_fuel_per_lap` if > 0, (3) config fallback. `_add_lap_row()` resets `_loaded_session_avg_fuel = 0.0` when a live lap arrives so the live tracker takes over. See `TestFuelBurnSource` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P2-009
**Root Cause:** DEF-P2-009 unified the fuel average display by pointing both sources to `tracker.avg_fuel_per_lap`. However, `tracker.avg_fuel_per_lap` only reflects laps from the **current live session** (accumulated since the last tracker reset). If the user loaded laps from History into Practice Review (FIX-013), those historical laps are in the table but are NOT fed into the tracker's rolling average. The tracker saw zero or few live laps (3.0 L/lap average from live), while the historical laps in the table show 4.0+ L/lap per row. The two values are from different data sources: tracker average = live session only; lap table col 8 = all rows including loaded historical laps.
**Description:** Strategy Builder Fuel Burn Auto shows 3.0 L/lap. Every lap row in Practice Review shows >4.0 L/lap fuel used. Single source of truth requirement is violated. AI prompt fuel burn and strategy recommendations are based on wrong data.
**Expected Behaviour:** The fuel burn shown in Strategy Builder must agree with the average fuel per lap derived from the laps currently visible in Practice Review. If historical laps are loaded, the fuel average must update to reflect them.
**Acceptance Criteria:**
- Load 10 historical laps averaging 4.2 L/lap into Practice Review.
- Strategy Builder Fuel Burn Auto updates to ~4.2 L/lap.
- Practice Analysis prompt receives ~4.2 L/lap as `fuel_burn`.
- Manually verify: `sum(col 8 values) / row_count` matches displayed average.

---

**ID:** DEF-P1-008
**Title:** Practice mode triggers RACE_FINISHED announcement after timed event duration elapses
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `and self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition at `telemetry/state.py` line 292. The condition now only fires when the session override is not PRACTICE. Race mode (`SessionType.RACE`) and unset override (None) still fire correctly.
**Reported:** 2026-06-21
**Root Cause:** `_on_event_set_active()` at `dashboard.py` line 7350 calls `tracker.set_race_config(RaceType.TIMED, duration_minutes=40)`, setting `_manual_race_type = RaceType.TIMED` and `_timed_race_duration_ms = 2,400,000 ms`. In practice mode, `_phase_transitions()` still transitions `PRE_RACE → RACING` when speed > 80 km/h and `_race_start_time = time.monotonic()` is set (line 512 in state.py) regardless of `_session_type_override`. After 40 minutes of practice, `computed_remaining_ms()` returns 0, satisfying the `RACE_FINISHED` conditions at state.py lines 289-302. The RACE_FINISHED event fires and the announcer says "Race ended at 40 minutes" during a Practice session.
**Description:** While running Practice Mode on the Live tab, the voice engineer announced "Race ended at 40 minutes." The active event was configured as a 40-minute timed race. The race timer fires correctly for an actual timed race, but it incorrectly fires during a Practice session when the same event is active.
**Expected Behaviour:** RACE_FINISHED logic must be suppressed entirely when `_session_type_override == SessionType.PRACTICE`. The race completion announcements, phase transition to FINISHED, and any post-race UI changes must not occur during practice regardless of the event's race type.
**Acceptance Criteria:**
- Set a 40-minute timed race event active. Switch Live tab to Practice mode. Run practice for 40+ minutes.
- No "Race finished" announcement. No `RACE_FINISHED` event in debug log.
- Switch to Race mode and start a timed session. After 40 minutes the announcement fires correctly.

---

**ID:** DEF-P1-009
**Title:** Event load does not restore saved Event variables (tyre_wear, fuel_mult, avail_tyres, req_tyres)
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix:** `_on_event_selected()` in `ui/dashboard.py`. Root cause: `_evt_tyre_wear`, `_evt_fuel_mult`, and `_evt_refuel_rate` are `QSpinBox` (integer-only) widgets, but the DB schema stores `tyre_wear`, `fuel_mult`, and `refuel_rate_lps` as `REAL` columns. SQLite returns `REAL` as Python `float`; PyQt6's `QSpinBox.setValue()` raises `TypeError` on a float argument. The broad `except Exception: pass` silently swallowed this error, leaving those spinboxes at their default value of 1 and preventing all subsequent field population (fuel_mult, avail_tyres, req_tyres, tuning categories, notes) from executing. Fix: wrapped all three REAL→QSpinBox assignments in `int(round(...))`. Secondary fix: changed `except Exception: pass` to `except Exception: import traceback; traceback.print_exc()` so future exceptions are visible. Tertiary fix: tuning permissions group visibility in `_on_event_selected` changed from `_bop_on and _tun_on` to `bool(_tun_on)` to match `_update_tuning_perms_visibility()`.
**Reported:** 2026-06-22 (UAT Group 2–4)
**Root Cause A:** Event persistence/reload broken
**Description:** When a previously saved event is selected in Event Planner, all form fields reset to their defaults instead of restoring the saved values. Affected fields: tyre wear multiplier, fuel multiplier, available tyres, required/mandatory tyres, tuning categories. Track, name, race type, laps, and duration loaded correctly (those spinboxes have INTEGER DB columns and Qt accepts int).
**Expected Behaviour:** Selecting a saved event from the Event Planner list restores all 17 fields to their saved values without requiring a "Set Active" click.
**Acceptance Criteria:**
- Save an event with Tyre Wear = 2, Fuel Mult = 3, Available = Racing Hard + Medium, Required = Racing Hard, BoP=On, Tuning=Off.
- Click the event in the list. Confirm all five fields restore to saved values (not defaults).
- Click "Set Active". Confirm Strategy Builder fuel multiplier shows ×3, tyre wear ×2.
- Verify `_config["strategy"]["tyre_wear_multiplier"] == 2` and `_config["strategy"]["fuel_mult"] == 3` in debug or by running Practice Analysis and checking the prompt.

---

**ID:** DEF-P1-010
**Title:** AI Debug / AI Log tab not visible after AI calls
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Reported:** 2026-06-22 (UAT Group 2)
**Root Cause C:** `call_api()` raised `RuntimeError` before reaching `_fire_log_hook()` when `GT7_AI_DEBUG=1` was set
**True Root Cause:** In `strategy/_ai_client.py`, the `if _AI_DEBUG:` block printed the prompt to stdout then raised `RuntimeError`. The `_fire_log_hook()` call is inside the `try/except` block that follows — unreachable when the RuntimeError is raised. Result: DB never written, bridge signal never emitted, AI Log tab empty for every intercepted call.
**Fix:** Added `_fire_log_hook(AILogEntry(..., success=False, error_msg="AI_DEBUG mode active..."))` immediately before the `raise RuntimeError` in the debug branch. Dry-run entries now appear in the AI Log tab with the full prompt captured.
**Description:** AI API calls succeed (strategy generates, driver feedback appears in AI prompt, PTT coaching returns responses), but nothing appears in the AI Log tab after any call. `GT7_AI_DEBUG=1` environment variable produces console output but not an AI Log entry. The log hook was never reached in debug mode.
**Expected Behaviour:** After any AI call (Practice Analysis, coaching, setup), the AI Log tab shows an entry with: model used, token count, prompt preview, response preview, and timestamp. With `GT7_AI_DEBUG=1` set, the AI Log tab shows a dry-run entry (success=False, error_msg="AI_DEBUG mode active...") with the full prompt captured.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1` (PowerShell). Run Practice Analysis or PTT coaching.
- Console output contains the full prompt text.
- Switch to AI Log tab. At least one entry exists with model, feature name, and success=✗.
- Click the entry — Prompt tab shows the full prompt text.
- `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.
- Without `GT7_AI_DEBUG`, make a real API call. AI Log shows a success entry with token count and cost.
**Blocked by:** None (independent of DEF-P1-009). Unblocks verification of DEF-P2-007, DEF-P2-016, DEF-P4-002.

---

**ID:** DEF-P1-011
**Title:** Strategy Builder Fuel Burn Auto shows stale "last session" value after switching events
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Reported:** 2026-06-22 (Phase 2 Smoke Test — user observed 3 L/lap matching event fuel_mult=3×)
**Root Cause:** `_on_event_set_active()` calls `_sync_setup_builder_from_event()` which only updates `_lbl_fuel_burn_display` when `tracker.avg_fuel_per_lap > 0`. When no live telemetry is active the label is left showing the persisted `config["strategy"]["fuel_burn_per_lap"]` value (e.g. 3.0 from a previous session) with the text "(last session)". The number coincidentally matched the fuel multiplier (both 3), causing user confusion.
**Fix:** Added reset block at the end of `_on_event_set_active()` (after `_sync_setup_builder_from_event()`). When both `tracker.avg_fuel_per_lap <= 0` AND `_loaded_session_avg_fuel <= 0`, `_lbl_fuel_burn_display` is reset to "— (complete practice laps to calibrate)". Live-data and loaded-session cases are preserved.
**Expected Behaviour:** After clicking Set Active on a new event with no live telemetry and no historical session loaded, the Fuel Burn Auto label shows "— (complete practice laps to calibrate)", not a stale numeric value from a previous session.
**Acceptance Criteria:**
- Ensure no live GT7 connection and no session loaded in Practice Review.
- Create a new event with Fuel Multiplier = 3×. Click Set Active.
- Navigate to Strategy Builder. Fuel Burn Auto shows "— (complete practice laps to calibrate)", not "3.00 L/lap (last session)".
- Load a historical session from History tab. Fuel Burn Auto updates to "X.XX L/lap (loaded session)".
**AWR:** AWR-040
**Group:** 11

---

### P2 High

---

**ID:** DEF-P2-001
**Title:** Practice mode laps recorded with session_type = 'race'
**Status:** Verified Fixed — 2026-06-21 (developer confirmed practice sessions appear as Practice in Practice Review)
**Fix:** `_on_live_mode_changed()` now calls `tracker.set_session_type_override()` (already did this) AND opens the session with the correct type string ("practice"/"qualifying"/"race"). The session type passed to `open_session()` now comes from the mode selector, not from a hardcoded string inside the dispatcher. At startup `_on_live_mode_changed()` is already called with the saved mode (line 499 in dashboard.py).
**Description:** `LapRecord.session_type` was derived from `_race_is_active` in `telemetry/state.py`. If a race session completed and the user switched to Practice, `_race_is_active` remained True. Practice laps were written with `session_type = 'race'`.
**Expected Behaviour:** The session type written to `lap_records.session_type` always matches the Live tab mode selector at the time the lap is completed.
**Acceptance Criteria:**
- Set Live tab to Practice. Complete two laps. `SELECT session_type FROM lap_records ORDER BY id DESC LIMIT 2` — both rows return `'practice'`.
- Switch to Race mode. Complete one lap. That row returns `'race'`.
- No lap written with `session_type = 'race'` when the mode selector shows Practice.

---

**ID:** DEF-P2-002
**Title:** Fuel-low and pit voice alerts fire during Practice sessions
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_on_pit()` and `_on_fuel_low()` in `voice/announcer.py` now guard `in ("practice", "qualifying")` instead of `== "practice"`. Both alerts are suppressed in Practice and Qualifying modes; Race mode still fires them. Qualifying was also unguarded — fixed in the same change.
**Description:** `VoiceAnnouncer._on_pit()` and `_on_fuel_low()` have no session-mode guard. Both alerts fire regardless of whether the current Live mode is Practice, Qualifying, or Race. In Practice these alerts are distracting and irrelevant.
**Expected Behaviour:** Fuel-low and pit advice alerts are suppressed when `_session_mode == 'practice'`. All other voice features (coaching, PTT responses, lap time announcements) remain active in Practice mode.
**Acceptance Criteria:**
- Set Live tab to Practice. Drop fuel to below the low-fuel threshold mid-lap. No fuel-low alert is spoken.
- Cross the pit entry line in Practice. No pit box advice is spoken.
- Switch to Race. Same fuel level — fuel-low alert fires as expected.
See `TestPitFuelAlertSuppression` in `test_group5_fixes.py`.

---

**ID:** DEF-P2-003
**Title:** Required Tyres field is a single dropdown, not a checkbox subset of Available Tyres
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. `_req_tyre_checks` checkbox grid was already implemented in `_build_event_planner_tab()`. `_avail_toggled()` callback enforces the subset rule. `_on_event_save()` writes a JSON list to `req_tyres`. `_on_event_selected()` restores checkboxes from the list with backward-compat string fallback. `_on_event_set_active()` writes `required_tyres` list and `mandatory_compounds` string to strategy config. See `TestRegisterCorrections` in `test_group6_fixes.py`.
**Description:** The Event Planner "Required Tyre" field is a single `QComboBox`. The spec requires a checkbox grid matching the Available Tyres selection. Required tyres must always be a subset of available tyres — enabling a compound as Required that is not Available must be prevented at the UI level.
**Expected Behaviour:** Required Tyres is a checkbox grid. Each compound is enabled only when that compound is also checked in Available Tyres. Unchecking an Available Tyre automatically unchecks the same compound in Required Tyres. Multiple required tyres can be selected simultaneously.
**Acceptance Criteria:**
- Enable Racing Hard and Racing Medium in Available Tyres. Both Required Tyres checkboxes become enabled.
- Uncheck Racing Hard in Available. Racing Hard Required checkbox is automatically unchecked and disabled.
- Save the event. `SELECT req_tyres FROM events WHERE name = ?` returns a JSON array of the checked codes.
- Load the event. Required Tyre checkboxes restore to the saved state.

---

**ID:** DEF-P2-004
**Title:** Setup Builder contains a BoP checkbox duplicating Event Planner
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_chk_bop` was removed from Setup Builder (no longer in source). `_current_setup_dict()` reads `bop_race` from `_config["strategy"]["bop"]`. `_get_bop_data_for_car()` reads from the same source. Race Conditions group has `_lbl_rc_bop` and `_lbl_rc_tuning` read-only labels populated by `_sync_setup_builder_from_event()`. `_on_event_set_active()` writes `strat["bop"]` from `_evt_bop`. See `TestBoPSourceOfTruth` in `test_group4_fixes.py`.
**Description (original):** `_chk_bop` in the Setup Builder allowed the user to manually toggle BoP independently of the active Event. This created a split source of truth.

---

**ID:** DEF-P2-005
**Title:** Tuning Permissions group only appears when BoP is ALSO enabled — not when Tuning is checked alone
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_update_tuning_perms_visibility()` in `dashboard.py` changed from `show = self._evt_bop.isChecked() and self._evt_tuning.isChecked()` to `show = self._evt_tuning.isChecked()`. The Tuning Permissions group now appears whenever "Tuning allowed" is checked, regardless of BoP state. See `TestTuningPermissionsVisibility` in `test_group4_fixes.py`.
**Root Cause:** The visibility condition incorrectly required both checkboxes. Tuning restrictions can apply without BoP (e.g., series-mandated category restrictions in non-BoP classes).

---

**ID:** DEF-P2-006
**Title:** Setup Builder does not enforce tuning permissions — all fields editable under BoP lock
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** After `_sync_setup_builder_from_event()` in `_on_event_set_active()`, an explicit unconditional call to `_apply_setup_permissions(strat.get("bop", False), strat.get("tuning", True), strat.get("allowed_tuning_categories", []))` was added. Belt-and-suspenders call fires regardless of DB lookup result.
**Description:** When an Event has BoP enabled with tuning not permitted, Setup Builder displays all fields as editable. There is no locked banner, no per-category disabling, and no warning that setup changes are not allowed for this event.
**Expected Behaviour:** `_apply_setup_permissions(bop, tuning_allowed, allowed_cats)` is called whenever the active event changes. When `tuning_allowed = False`, all setup fields except tyre dropdowns and metadata are disabled and a banner is shown. When categories are restricted, only those fields are enabled. Tyre dropdowns are always enabled regardless of BoP status.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Set it active. Setup Builder shows the locked banner. All spinboxes and dropdowns (except tyre compound) are disabled.
- Set Event with BoP=On, Tuning=Yes, Allowed=Suspension+BrakeBalance. Only suspension and brake balance fields are editable. Tyre dropdowns remain enabled.
- Set Event with BoP=Off. All fields are editable.

---

**ID:** DEF-P2-007
**Title:** AI coaching and setup advice does not respect tuning lock
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix (three parts):**
1. **Prompt constraint injection**: `_tuning_constraint_block()` in `driving_advisor.py` injects either `## EVENT RULES — TUNING LOCKED` (full lock) or `## EVENT TUNING RESTRICTIONS` (partial) into all prompt builders. All three advisor methods (`build_coaching_response`, `build_setup_advice_response`, `build_combined_setup_response`) accept and pass `tuning_locked` and `allowed_tuning`.
2. **Caller propagation**: `_setup_analyse_ai()` reads `_config["strategy"]["allowed_tuning_categories"]` and `tuning` flag and passes them. `_run_practice_analysis()` includes them in `RaceParams`. `query_listener.py` coaching and setup_advice paths read and pass both params.
3. **AI output validation**: `validate_ai_setup_response(response, tuning_locked, allowed_tuning)` added to `ai_planner.py`. Detects violations (locked-category keyword + action verb within 200 chars) and returns a list of violated category codes. `_display_setup_result()` and `_display_practice_results()` in `dashboard.py` both call the validator and prepend an amber warning banner if violations are detected.
See `TestAITuningConstraintPropagation` and `TestAIOutputValidation` in `test_group4_fixes.py`.

---

**ID:** DEF-P2-008
**Title:** PTT speech-to-text does not function reliably in Practice mode
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Source scan confirmed: (1) `main.py` starts `QueryListener` unconditionally at line 566 — no mode gate; (2) `_handle_trigger()` already has `try/except Exception` with `traceback.print_exc()` and `_emit_ptt_status(f"PTT ERROR: {_e}")`; (3) `_handle_trigger_inner()` has no session_mode guard — PTT responds in all modes. No code change required; defect was a documentation gap.
**Description:** PTT trigger fires (keyboard listener active) but `_handle_trigger()` may fail silently in Practice mode. No debug output confirms whether the failure is in transcription, intent routing, or AI call. The QueryListener may not be started for all Live modes.
**Expected Behaviour:** PTT works identically in Practice, Qualifying, and Race modes. Debug tab shows PTT status transitions: TRANSMITTING → PROCESSING → RADIO READY (or ERROR with traceback). `QueryListener` is started unconditionally at app startup regardless of initial Live mode.
**Acceptance Criteria:**
- Switch Live tab to Practice. Press PTT key. Debug tab shows "TRANSMITTING".
- Speak a coaching query. Debug tab shows "PROCESSING" then "RADIO READY".
- AI response is spoken and logged to AI log.
- If transcription fails, Debug tab shows "ERROR: <reason>" with traceback.
See `TestPTTPracticeMode` in `test_group5_fixes.py`.

---

**ID:** DEF-P2-009
**Title:** Fuel Burn Auto shows stale value after session reload from History
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix (Group 8):** Both `_on_history_load_session()` and `_import_bank_session()` in `dashboard.py` now update `_lbl_fuel_burn_display` immediately after computing `_loaded_session_avg_fuel`. Previously the label was only set at widget creation time (startup) and was never refreshed after a History reload. Fix: `if hasattr(self, "_lbl_fuel_burn_display") and self._loaded_session_avg_fuel > 0: self._lbl_fuel_burn_display.setText(f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")`. Fuel average correctly excludes pit laps and out-laps (now that their DB flags are correctly written by the DEF-P2-013 fix). See `TestHistoryLoadSessionMapping` in `test_group8_session_reload.py`.
**Fix (Group 2 — earlier partial fix):** `dashboard.py` Practice Review lap table replaced `self._logger.avg_fuel_per_lap()` with `getattr(self._tracker, "avg_fuel_per_lap", 0.0)`. `strategy/engine.py` already used `self._tracker.avg_fuel_per_lap` directly.
**Description:** After loading a historical session from History into Practice Review, the Strategy Builder Fuel Burn Auto label still shows the value from app startup (either "—" or the previous live session average). `_loaded_session_avg_fuel` was being set correctly, but the UI label was never refreshed.
**Expected Behaviour:** After loading a session from History, the Strategy Builder Fuel Burn label shows the average fuel per lap from the loaded session (excluding pit laps and out-laps). `_computed_fuel_burn_lpl()` returns the loaded session average and the display reflects it immediately.
**Acceptance Criteria:**
- Load a 10-lap session from History where the average fuel is ~3.0 L/lap. Strategy Builder Fuel Burn label updates to "3.00 L/lap (loaded session)" immediately.
- Run Practice Analysis — `fuel_burn_per_lap` in the prompt matches the loaded session average.
- Pit laps and out-laps are excluded from the average (their fuel values are not representative).

---

**ID:** DEF-P2-010
**Title:** Driver feedback form embedded in Setup Builder instead of Practice Review
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix (three parts):**
1. Removed `layout.addWidget(self._build_driver_feedback_form())` from `_build_setup_builder_tab()`.
2. Added `layout.addWidget(self._build_driver_feedback_form())` to `_build_practice_review_tab()` after the Practice AI Analysis group.
3. Updated `_on_driver_feedback_submit()`: `_setup_feeling_input` access guarded with `hasattr`; `session_id=0` replaced with `getattr(self, "_session_id", 0)` so feedback links to the active session; `_setup_analyse_ai()` call removed (it belongs to Setup Builder, not Practice Review).
See `TestDriverFeedbackLocation` in `test_group6_fixes.py`.
**Description:** The driver feedback form (corner entry, mid-corner, exit stability, etc.) is placed inside the Setup Builder tab. Per spec §4.3, post-session feedback is a Practice Review prompt. Drivers finishing a stint must not navigate to Setup Builder to submit handling notes.
**Expected Behaviour:** Driver feedback form is accessible from Practice Review via a "Submit Feedback" button or collapsible section. Submitting from Practice Review writes to `driver_feedback` linked to the current session. That feedback then appears in subsequent AI coaching prompts.
**Acceptance Criteria:**
- Practice Review tab contains a "Submit Feedback" button or collapsible feedback form.
- Submitting feedback from Practice Review writes a row to `driver_feedback` linked to the current session.
- That row appears in the next AI coaching prompt under "## Recent Driver Feedback".

---

---

**ID:** DEF-P2-011
**Title:** Practice Review session summary includes outlaps and invalid laps in best/average calculations
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Three-part fix: (1) `get_session_laps()` in `session_db.py` now SELECTs `is_out_lap` in addition to `is_pit_lap`. (2) `_add_bank_lap_row()` and `_add_lap_row()` in `dashboard.py` now store `{"is_out_lap": ..., "is_pit_lap": ...}` in the col 0 item's `Qt.ItemDataRole.UserRole` data. Outlap rows display "Practice (OL)" in col 1 and use a dark green `#003A1A` background. (3) `_refresh_practice_summary()` now reads the UserRole flag per row and skips any row with `is_out_lap=True` from best lap, average lap, and average fuel calculations. Total row count still includes outlaps. See `TestOutlapSummaryLogic` and `TestOutlapDB` in `test_group3_fixes.py`.
**Reported:** 2026-06-21
**Root Cause:** `_refresh_practice_summary()` (`dashboard.py` line 6782) iterates all rows, reads col 3 (lap time ms), and includes every row where `ms > 0`. There is no mechanism to identify outlap rows: `_add_lap_row()` does not store `is_out_lap` in any table column or item data, and `_add_bank_lap_row()` has no `is_out_lap` parameter. The `get_session_laps()` query does not return `is_out_lap` even though it is stored in `lap_records`. Outlap times (typically 10–40% slower than a flying lap) inflate the average and may affect best-lap identification if displayed alongside regular laps.
**Description:** Practice Review Session Summary best lap and average lap calculations include outlaps and should not. DEF-P1-002 fix ensured outlaps are recorded with `is_out_lap=True`, but the summary calculation does not filter them out.
**Expected Behaviour:** Outlaps are excluded from best lap, average lap, and average fuel calculations. Outlaps are still displayed in the lap table with a visual indicator (e.g., "OL" label or distinct background colour) but are not used in summary statistics.
**Acceptance Criteria:**
- Complete an outlap (4s slower than lap pace). Session Summary best lap is not the outlap.
- Load a session containing an outlap from History. Outlap row visible in table. Summary best and average exclude it.
- Outlap row has a distinct visual style (colour or label).

---

**ID:** DEF-P2-012
**Title:** Practice Analysis prompt sends wrong tyre wear multiplier (2.0× instead of actual event value)
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_run_practice_analysis()` in `dashboard.py` now reads `tyre_wear_multiplier` from `_psc` (strategy config) immediately before building `race_params`, ensuring no stale cached value is used. Added a debug log: `print(f"[PracticeAnalysis] tyre_wear_multiplier={_tyre_wear:.2f} (from Event config)")`. See `TestTyreWearSource` source scan test in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P1-004, Addendum A3
**Root Cause:** `_run_practice_analysis()` reads `tyre_wear_multiplier` from `_psc.get("tyre_wear_multiplier", 1.0)` where `_psc = self._config.get("strategy", {})`. This value is set by `_on_event_set_active()` from `self._evt_tyre_wear.value()`. If the active event was last saved with tyre wear = 2.0 and the user hasn't re-activated the event after changing the wear multiplier, the stale 2.0 value is sent to the AI. The `_wear_note()` function in `ai_planner.py` (line 432) converts `tyre_wear_multiplier != 1.0` into "Race tyre wear is X× faster than practice." When `tyre_wear_multiplier == 1.0`, it correctly outputs "Tyre wear rate is the same as in practice."
**Description:** Event Planner had tyre wear configured equal to practice. Practice Analysis prompt stated "Race tyre wear is 2.0× faster than practice." This is factually incorrect. Confirmed by AI prompt evidence.
**Expected Behaviour:** `tyre_wear_multiplier` in the practice analysis prompt must exactly match the currently active event's tyre wear multiplier. If the event has 1.0x wear, prompt must say "Tyre wear rate is the same as in practice."
**Acceptance Criteria:**
- Set Event tyre wear to 1.0x. Set event active. Run Practice Analysis.
- Prompt contains "Tyre wear rate is the same as in practice."
- Set tyre wear to 1.5x. Re-activate event. Re-run. Prompt contains "1.5× faster."

---

**ID:** DEF-P2-013
**Title:** Pit stop indicator lost after session reload from History
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12b investigation) — Code investigation confirmed both load paths (`_on_history_load_session` and `_import_bank_session`) correctly pass `is_pit_lap` via `get_session_laps()`. Zero values in retesting were from pre-Group-8 session data (wrote `is_pit_lap=0` by default). New sessions recorded after Group 8 have correct values. DEF-P2-022 root cause hypothesis was incorrect.
**Fix (Group 8 — complete fix):** `main.py` EventDispatcher `write_lap()` call now passes `is_pit_lap=bool(getattr(record, "is_pit_lap", False))` and `is_out_lap=bool(getattr(record, "is_out_lap", False))`. Also passes `delta_ms` and `session_type`. These four fields were silently defaulting to 0/False/"" because they were not forwarded from the `LapRecord`. The UI-side fixes (Groups 2+3) were correct but had no effect because the DB column was always 0. See `TestMainWriteLapPassesPitFlag` in `test_group8_session_reload.py`.
**Fix (Groups 2+3 — partial):** `get_session_laps()` extended to SELECT `is_pit_lap`; `_add_bank_lap_row()` extended to accept and apply `is_pit_lap` (amber background `#4A4000`, "Yes" in col 11); both `_on_history_load_session()` and `_import_bank_session()` updated to pass `is_pit_lap=bool(lap.get("is_pit_lap", 0))`.
**Reported:** 2026-06-21
**Root Cause:** `main.py` EventDispatcher called `write_lap()` without forwarding `is_pit_lap`, `is_out_lap`, `delta_ms`, or `session_type` from the `LapRecord`. These all defaulted to 0/False/"". The DB column `is_pit_lap` was therefore always 0. Live display reads from the `LapRecord` in memory and showed correctly; the reload path reads from DB and always found 0.
**Root Cause (original — already fixed Groups 2+3):** `get_session_laps()` only selected `lap_num, lap_time_ms, compound, fuel_used`. `is_pit_lap` was stored in DB but not retrieved. `_add_bank_lap_row()` always wrote `""` for col 11.
**Description:** After reloading a session from History into Practice Review, pit stop laps that were correctly marked with a pit indicator when originally recorded show as blank in the Pit column. The data is in the DB but not retrieved or displayed.
**Expected Behaviour:** Pit stop indicator (col 11, "Yes") is preserved after session reload. Rows that were pit laps retain the amber background and "Yes" marker.
**Acceptance Criteria:**
- Complete a pit stop lap in Practice. Save session. Reload from History. The pit lap row shows "Yes" in the Pit column with amber background.
- Non-pit laps show blank in the Pit column.
- `get_session_laps()` returns `is_pit_lap` field in its result dict.

---

**ID:** DEF-P2-014
**Title:** Fuel Start and Fuel End not persisted to DB and missing after session reload
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12b investigation) — Same finding as DEF-P2-013: code is correct for new sessions. History detail shows `fuel_used` (always persisted); `fuel_start`/`fuel_end` are persisted by Group 8 fix for sessions recorded after that fix. Pre-Group-8 sessions have 0.0 defaults. AWR-043 must use a session recorded after Group 8 to pass.
**Fix (Group 8 — additional fix):** The secondary effect of DEF-P2-013 (is_out_lap always 0 in DB) meant outlap fuel values were included in the loaded session average, skewing the Fuel Burn Auto display. With Group 8's fix to write `is_out_lap` correctly, the fuel average now correctly excludes outlaps. `_lbl_fuel_burn_display` is also now refreshed after session load (see DEF-P2-009 fix). See `TestGetSessionLapsColumns` in `test_group8_session_reload.py`.
**Fix (Group 2 — schema + write path):** Added `fuel_start REAL NOT NULL DEFAULT 0.0` and `fuel_end REAL NOT NULL DEFAULT 0.0` columns to `_DDL_BASE` `lap_records` table in `session_db.py`. Added `_V2_ALTER_COLUMNS` list and `_migrate_v2()` method (idempotent ALTER TABLE with duplicate-column guard). `_migrate()` dispatcher now runs v2. `write_lap()` signature extended with `fuel_start: float = 0.0` and `fuel_end: float = 0.0`; both columns added to the INSERT (now 33 `?` placeholders). `get_session_laps()` SELECT extended to return `is_pit_lap, fuel_start, fuel_end`. `_add_bank_lap_row()` extended to accept and display these values. `main.py` EventDispatcher passes `fuel_start=getattr(record, "fuel_start", 0.0)` and `fuel_end=getattr(record, "fuel_end", 0.0)` to `write_lap()`. See `TestFuelStartEndDB` in `test_group2_fixes.py`.
**Reported:** 2026-06-21
**Root Cause:** `write_lap()` (`session_db.py` line 817) does not write `fuel_start` or `fuel_end` columns — neither exists in the `lap_records` INSERT statement. `LapRecord` carries both fields but they are never passed to `write_lap()`. The EventDispatcher at `main.py` calls `write_lap(..., fuel_used=...)` without fuel_start or fuel_end. `get_session_laps()` does not return them. `_add_bank_lap_row()` always writes `"—"` for col 6 (fuel_start) and col 7 (fuel_end) at lines 2694-2695.
**Description:** After reloading a practice session from History, the Fuel Start and Fuel End columns are blank ("—") for all laps. These values are available at lap-record time but are never written to the database.
**Expected Behaviour:** Fuel Start and Fuel End per lap are stored in `lap_records` and restored when loading from History. Reloaded rows show numeric fuel start/end values.
**Acceptance Criteria:**
- Complete 3 laps in Practice. Each lap's Fuel Start and Fuel End are populated in the table.
- Reload the same session from History. Fuel Start and Fuel End columns show the same values.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 3` returns non-zero values.

---

**ID:** DEF-P2-015
**Title:** Top speed target in AI prompt shows invalid value (~11 km/h) instead of actual target speed
**Status:** Fixed — Awaiting Retest (2026-06-22)
**Fix:** Changed `if ms > 0:` to `if ms >= 50:` in `_refresh_gear_ratios()` at `ui/dashboard.py`. Values below 50 km/h are now treated as raw-field artefacts and not written to `_spin_top_speed`. The spinbox stays at 0 (shows "—"), and `_current_setup_dict()` sends `transmission_max_speed_kmh: 0` which the AI ignores. See `TestTopSpeedGuard` in `test_group6_fixes.py`.
**Reported:** 2026-06-21
**Related:** Addendum A5
**Root Cause:** `transmission_max_speed_kmh` property in `packet.py` (line 312) computes `self.transmission_max_speed * 3.6`. The raw `transmission_max_speed` field in the GT7 UDP packet is not a speed in m/s — reverse-engineering of the GT7 packet format shows this field may encode the transmission type index, a gear ratio scaling factor, or an unused value that happens to be ~3.0. Multiplying a ratio/index value (~3.0) by 3.6 gives ~11 km/h. `_capture_gear_ratios()` at `dashboard.py` line 5639 writes this invalid value directly to `_spin_top_speed`. `_current_setup_dict()` at line 4691 sends `"transmission_max_speed_kmh": int(self._spin_top_speed.value())`, passing 11 km/h to `analyse_practice_session()`.
**Description:** AI prompt reports "Top speed target: 11 km/h." No GT7 car has a top speed target near 11 km/h. This nonsense value pollutes the AI setup recommendation.
**Expected Behaviour:** If the captured top speed value is below 50 km/h, treat it as not captured and send 0 or omit the field. The prompt should not contain an invalid top speed target. Minimum valid GT7 top speed target is approximately 120 km/h.
**Acceptance Criteria:**
- Run a practice lap. `_spin_top_speed` shows either 0 ("—") or a realistic value ≥ 120 km/h.
- AI prompt does not contain "11 km/h" or any value < 50 km/h for top speed target.
- If `transmission_max_speed_kmh` < 50, it is excluded from the setup dict payload.

---

**ID:** DEF-P2-016
**Title:** Practice Analysis requests race strategy from AI without validating input data integrity
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added a validation gate in `_run_practice_analysis()` before the AI call. Builds `_validation_warnings: list[str]` checking: (1) timed race with `duration_mins < 5`, (2) lap race with `total_laps < 2`, (3) `fuel_burn_per_lap <= 0`, (4) no compound with ≥ 2 laps. If any warning present, shows an HTML warning dialog with the list, logs `"[PracticeAnalysis] Validation blocked"`, and returns without calling AI. See `TestValidationGateLogic` in `test_group2_fixes.py` and source-scan test `test_source_contains_validation_gate`.

---

**ID:** DEF-P2-017
**Title:** Qualifying mode may trigger RACE_FINISHED logic on timed events
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. DEF-P2-QRF (Group 5, 2026-06-21) implemented a two-layer fix: (1) `telemetry/state.py` timed-race RACE_FINISHED condition excludes both `SessionType.PRACTICE` and `SessionType.QUALIFYING`; (2) `voice/announcer.py` `_on_race_finish()` guards `_session_mode != "race"` as a belt-and-suspenders fallback. See `TestQualifyingRaceFinished` in `test_group5_fixes.py`.
**Reported:** 2026-06-21
**Related:** DEF-P1-008
**Root Cause:** The DEF-P1-008 fix at `telemetry/state.py` adds `self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition. This suppresses the event during practice but not during qualifying. A qualifying session with a timed event active (e.g., a 15-minute qualifying session configured in Event Planner) will still have `_race_start_time` set when the car exceeds 80 km/h, and `computed_remaining_ms()` will reach 0 after the configured timed duration. If the user pauses the game (`packet.loading = True`) at that point, RACE_FINISHED fires and the voice engineer announces race completion during qualifying.
**Description:** RACE_FINISHED logic should only run in Race mode. Practice and Qualifying must never trigger race-finished events, race-completion announcements, or the FINISHED phase transition. DEF-P1-008 fixed the Practice case but left Qualifying unguarded.
**Expected Behaviour:** The RACE_FINISHED condition is only evaluated when `_session_type_override == SessionType.RACE` or `_session_type_override is None` (auto-detect, assumed race context). Practice and Qualifying overrides suppress the event entirely.
**Acceptance Criteria:**
- Set a timed event active. Switch Live tab to Qualifying mode. Drive for the full timed duration. No "Race finished" announcement.
- `RACE_FINISHED` does not appear in the Debug tab event log during qualifying.
- Practice mode: same — no RACE_FINISHED (existing AWR-011 covers this).
- Race mode: RACE_FINISHED still fires correctly after the configured duration.
**Reported:** 2026-06-21
**Related:** DEF-P1-004, DEF-P1-005, DEF-P1-006, Addendum A6
**Root Cause:** `_run_practice_analysis()` calls `analyse_practice_session()` unconditionally once `lap_data_by_compound` is non-empty. There is no pre-flight validation of: race type correctness, compound distribution accuracy, fuel burn source consistency, BoP/tuning permissions loading, or tyre wear multiplier accuracy. The AI receives a strategy request built from potentially incorrect race length (1 lap), wrong compound counts, wrong fuel burn source, full setup with locked fields, and wrong tyre wear — producing a response that is internally consistent but based on bad data. Detected when actual testing showed all five prompt inputs were wrong simultaneously.
**Description:** Practice Analysis sends a three-strategy race recommendation request to AI even when the prompt's race type, compound history, fuel burn, BoP restrictions, and tyre wear are all incorrect. The AI response appears plausible but is based on wrong data throughout.
**Expected Behaviour:** Before calling the AI, `_run_practice_analysis()` validates: race type is correctly resolved, compound data matches the visible lap table, fuel burn is from a live or loaded source (not a stale tracker value), BoP/tuning restrictions are loaded, and no obviously invalid values (top speed < 50 km/h, race laps < 2 for a lap race) are present. If validation fails, the Analysis button is disabled or a warning panel is shown listing the data quality issues.
**Acceptance Criteria:**
- With a timed race event active and 0 live laps (tracker has no fuel data), Practice Analysis button shows a data quality warning rather than sending the AI call.
- After loading historical laps with correct compound tags and an activated event, the button becomes available and the prompt passes validation.
- Debug tab logs each validation check and its result before the AI call.

---

**ID:** DEF-P2-018
**Title:** Outlap row has no visual identification in Practice Review
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 3 partial)
**Related:** DEF-P1-002 (outlap recording fix — was Partially Fixed)
**Description:** Outlaps are now saved to the DB with `is_out_lap=1` (DEF-P1-002 fix) but the Practice Review lap table displays them with the same style as normal laps. No "OL" label, no dark green row background, and no "(out)" suffix on the lap time. Drivers cannot distinguish outlap from push lap at a glance.
**Expected Behaviour:** Outlap rows in Practice Review display with a distinct visual style: dark green (`#003A1A`) row background OR an "OL" label in column 1 next to the lap number. The lap time column shows "(out)" suffix or is otherwise flagged. The outlap is excluded from best-lap calculations in the Session Summary.
**Acceptance Criteria:**
- Complete a pit stop and outlap in Practice mode.
- Practice Review: the outlap row has visually distinct styling (dark green or "OL" label).
- `is_out_lap = 1` in the DB for that row.
- Session Summary best lap excludes the outlap.

---

**ID:** DEF-P2-019
**Title:** Tyre compound change on existing lap does not propagate to subsequent laps
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Superseded by DEF-P2-026 (same defect, clearer spec)
**Reported:** 2026-06-22 (UAT Group 5 partial)
**Related:** DEF-P3-003 (new lap compound inheritance — was Partially Fixed); DEF-P2-026 (same defect re-reported with clearer spec)
**Fix:** `_on_compound_selected()` in `ui/dashboard.py` previously stopped propagation at the first row with any different compound string. Since every row is pre-tagged with `_default_lap_compound`, this stopped at row `start_row + 1` every time. Fix: removed the `existing and existing != norm` break condition and replaced it with a check for `is_pit_lap` in the row's UserRole data. Propagation now continues through all laps until the next pit lap boundary.
**AWR:** AWR-048
**Group:** 13

---

**ID:** DEF-P2-020
**Title:** Live tab tyre label shows available/required tyres from Event, not current fitted compound
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Superseded by DEF-P2-027 (same defect, full priority spec)
**Reported:** 2026-06-22 (UAT Group 5 partial)
**Related:** DEF-P3-002 (live tyre label — was Partially Fixed); DEF-P2-027 (same defect re-reported with full priority hierarchy spec)
**Fix:** See DEF-P2-027. `_get_current_tyre_compound()` and `_refresh_live_tyre_label()` implement Priority 1 (active race plan current stint) → Priority 2 (Setup Builder front tyre) → Priority 3 ("Not Set"). `mandatory_compounds` no longer used as tyre source. Label prefix changed to "Current Tyre:". Wired to `_on_tyre_preset_changed()`, `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, and `_setup_tyre_f.currentTextChanged`.
**AWR:** AWR-049
**Group:** 13

---

**ID:** DEF-P2-023
**Title:** Pit Lap Not Captured During Live Session (no-refuel stops)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Pit lap detection is entirely fuel-based — `_fuel_gained >= _pit_threshold (0.5L)` must be exceeded before `_enter_pit()` is called and `_pit_lap = True` is set. When the driver pits without refueling (e.g., tyre change only), `_fuel_gained` stays at 0 and the pit stop is never detected. The lap during which the car was in the pit box is written to DB with `is_pit_lap = 0`.
**Root cause:** `telemetry/state.py` `_phase_transitions()` only triggers `_enter_pit()` via the fuel accumulation path. No fallback for speed=0 service stops.
**Fix:** Added `_low_speed_start: float = 0.0` tracker variable. In `_phase_transitions()`, when `self._phase == RacePhase.RACING` and `p.speed_kmh < 10`: if timer not running, start it; if timer running for ≥ 3.0 seconds, call `_enter_pit()`. Reset timer when speed rises back above 10 km/h or when `_enter_pit()` fires. Timer also reset in `_enter_pit()` itself to prevent double-firing if fuel detection fires at the same time.
**Expected Behaviour:** When the driver comes to a full stop in the pit box for ≥ 3 seconds (with or without refueling), `is_pit_lap = 1` is written to `lap_records`. Practice Review shows amber background on the pit stop lap.
**Acceptance Criteria:**
- Run Practice session. Pit and take 0 fuel (tyre change only). Continue.
- `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` — the pit lap row has `is_pit_lap = 1`.
- Practice Review shows amber background for that lap.
- Outlap after the no-fuel pit stop shows `is_out_lap = 1`.
**AWR:** AWR-045
**Group:** 13

---

**ID:** DEF-P2-024
**Title:** Outlap Metadata Lost After History Reload (Save Session button path)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Outlap is visible in Practice Review during a live session (correct `is_out_lap = True` from `LapRecord`). After the user clicks Save Session, clears the session, and reloads from History, the outlap flag is gone — the row shows as a normal lap. The save path via `_save_session_to_db()` was calling `write_lap()` with only 6 positional arguments, omitting `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`, `delta_ms`, and `session_type`. All omitted fields default to 0/False/"" in the DB.
**Root cause:** `ui/dashboard.py` `_save_session_to_db()` line 2935: `self._db.write_lap(sid, lap.lap_num, lap.lap_time_ms, lap.fuel_used, stats, compound)` — no keyword arguments for the lap metadata fields.
**Fix:** Extended the `write_lap()` call with `fuel_start=getattr(lap, "fuel_start", 0.0)`, `fuel_end=getattr(lap, "fuel_end", 0.0)`, `is_pit_lap=bool(getattr(lap, "is_pit_lap", False))`, `is_out_lap=bool(getattr(lap, "is_out_lap", False))`, `delta_ms=int(getattr(lap, "delta_ms", 0))`, `session_type=(lap.session_type.value if hasattr...)`.
**Acceptance Criteria:**
- Run Practice session with outlap. Save Session → Clear → Load from History.
- Outlap row in Practice Review shows dark green background and "Practice (OL)" label.
- `SELECT is_out_lap FROM lap_records ORDER BY id DESC LIMIT 10` — outlap row has `is_out_lap = 1`.
**AWR:** AWR-046
**Group:** 13

---

**ID:** DEF-P2-025
**Title:** Fuel Data Lost After History Reload (Save Session button path)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT)
**Description:** Same root cause as DEF-P2-024. `_save_session_to_db()` omitted `fuel_start` and `fuel_end` from the `write_lap()` call. After Save Session + History reload, Fuel Start and Fuel End columns in Practice Review show "—" (0.0 in DB) even though the live session showed non-zero values.
**Root cause:** Same as DEF-P2-024 — missing keyword args in `_save_session_to_db()`.
**Fix:** Same as DEF-P2-024 — `fuel_start=getattr(lap, "fuel_start", 0.0)` and `fuel_end=getattr(lap, "fuel_end", 0.0)` now passed.
**Acceptance Criteria:**
- Run Practice session with ≥ 3 laps. Fuel Start and Fuel End are non-zero live. Save Session → Clear → Load from History.
- Practice Review Fuel Start and Fuel End columns show non-zero numeric values matching the live session.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 5` — non-zero values.
**AWR:** AWR-047
**Group:** 13

---

**ID:** DEF-P2-026
**Title:** Tyre Compound Propagation Only Updates Selected Lap (duplicate of DEF-P2-019)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13) — Same defect as DEF-P2-019, more specific reproduction steps
**Reported:** 2026-06-22 (UAT)
**Related:** DEF-P2-019 (same root cause, same fix)
**Fix:** See DEF-P2-019.
**AWR:** AWR-048
**Group:** 13

---

**ID:** DEF-P2-027
**Title:** Live Tab Displays Event Required Tyre Instead of Current Fitted Compound
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 13)
**Reported:** 2026-06-22 (UAT — extended spec provided)
**Related:** DEF-P2-020 (same root cause, full priority hierarchy spec added)
**Description:** The Live tab `_lbl_live_tyre_compound` label was set from `strategy["mandatory_compounds"]` (the event's Required Tyre field). Required tyres are race rules (what must be used at some point), not the current fitted compound. The user received a detailed spec requiring a priority hierarchy.
**Fix:** Added `_get_current_tyre_compound()` that checks (1) active race plan current incomplete stint `.compound`, (2) Setup Builder front tyre `_setup_tyre_f.currentText()`, (3) returns "Not Set". Added `_refresh_live_tyre_label()` that sets label to `"Current Tyre: {compound}"`. Wired to: `_on_tyre_preset_changed()` (fires on stint change), `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, and `_setup_tyre_f.currentTextChanged`. `mandatory_compounds` removed entirely from the live tyre label logic.
**Acceptance Criteria:**
- Load a race plan with Stint 1 = Racing Medium, Stint 2 = Racing Soft. Live tab shows "Current Tyre: Racing Medium". After pit stop completes Stint 1, shows "Current Tyre: Racing Soft".
- No race plan loaded, Setup Builder front tyre = Racing Hard → Live tab shows "Current Tyre: Racing Hard".
- No race plan, no setup tyre → Live tab shows "Current Tyre: Not Set".
- Required tyres from Event are NOT shown in the current tyre label.
**AWR:** AWR-049
**Group:** 13

---

**ID:** DEF-P2-021
**Title:** AI Log list does not auto-select new entries; timestamp and status format incomplete
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 12c) — Three fixes: (1) Timestamp: `[:19].replace("T"," ")` → YYYY-MM-DD HH:MM:SS. (2) Status: "✓ OK"/"✗ FAIL"/"⊘ DRY-RUN" (dry-run detected via duration_ms==0 and "AI_DEBUG" in error_msg). (3) Auto-select: `_ai_log_pending_select` flag set in `_on_ai_log_entry()`; flushed by `_flush_ai_log_pending_select()` when AI Log tab (index 11) becomes active via `_on_tab_changed()`.
**Reported:** 2026-06-22 (Phase 2 Smoke Test — user reported "no visible AI log entry" after Practice Analysis with GT7_AI_DEBUG=1)
**Note:** Originally misreported as DEF-P2-019 (that ID is already taken by "Compound change not propagating forward").
**Root Cause:** `_add_ai_log_list_item()` called `scrollToBottom()` after appending the new item, but if the AI Log tab was not the currently visible tab when the `bridge.ai_log_entry` signal fired (QueuedConnection → delayed), `scrollToBottom()` had no visual effect. When the user later navigated to the AI Log tab, they saw the top of the list (DB-loaded history) and missed the new entry sitting at the bottom without selection. DB-loaded startup entries appeared populated; the user clicked one and saw the Prompt tab — but could not find the new live entry.
**Fix:** `_add_ai_log_list_item()` now accepts `auto_select: bool = False`. When `True`, calls `setCurrentRow(count - 1)` after `addItem()`, selecting the newly added item. `_on_ai_log_entry()` (the live signal handler) passes `auto_select=True`; `_on_ai_log_entry_dict()` (DB startup load) keeps the default `False` to avoid disrupting startup ordering.
**Expected Behaviour:** When a new AI call completes (or fails in debug mode), the entry is added to the AI Log list AND automatically selected. When the user navigates to the AI Log tab the new entry is highlighted, and the detail pane (Details, Prompt, Payload, Response tabs) immediately shows that entry's data.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Run Practice Analysis (with ≥ 2 laps and valid fuel data).
- Navigate to AI Log tab. The most recent entry is highlighted (selected) automatically.
- Entry shows ✗, feature="Practice Analysis", timestamp from the run.
- Prompt sub-tab shows the intercepted prompt (requires Developer Mode enabled in Settings).
**AWR:** AWR-041
**Group:** 11

---

**ID:** DEF-P2-022
**Title:** History session detail and Practice Review load path use different data sources — pit flag and fuel data missing in Practice Review
**Status:** CLOSED — Root cause hypothesis incorrect (2026-06-22 Group 12b investigation)
**Reported:** 2026-06-22 (discovered during AWR-040 runtime retest)
**Investigation conclusion:** Both load paths (`_on_history_load_session()` and `_import_bank_session()`) use the SAME `get_session_laps()` SELECT which correctly returns `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`. Both methods correctly pass all fields to `_add_bank_lap_row()`. `write_lap()` in `main.py` correctly receives `fuel_start`, `fuel_end`, `is_pit_lap` from `LapRecord`. The History detail panel shows only `fuel_used` (not `fuel_start`/`fuel_end`); the user's comparison was between different columns. Zero values observed in AWR-040 retest were caused by testing with pre-Group-8 session data that had `DEFAULT 0.0` for newly-added columns. No code change required. Tests in `test_group12b_history_practice_mapping.py` verify correctness.
**Related:** DEF-P2-013, DEF-P2-014
**Group:** 12

---

---

**ID:** DEF-P1-012
**Title:** Practice Analysis prompt provides setup changes even when tuning is locked (BoP event)
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_build_practice_prompt()` in `strategy/ai_planner.py` had both a `constraint_block` saying "DO NOT recommend setup changes" AND a fixed `## Instructions` line asking for "3–5 Setup changes". The AI followed the explicit instruction over the constraint.
**Fix:** The `setup_changes` instruction at line 685 is now a Python conditional. When `params.tuning_locked=True`: "No setup changes…Tuning is locked…do NOT recommend any setup changes." When `not params.tuning_locked`: original "3–5 changes following the endurance priority order…" text.
**Acceptance Criteria:**
- BoP event, Tuning Off → run Practice Analysis → AI response contains "tuning not permitted" or "setup changes not recommended"; no specific setup change values.
- Non-BoP event → AI response still provides 3–5 setup changes.
**AWR:** AWR-050
**Group:** 14

---

**ID:** DEF-P2-029
**Title:** Outlap metadata row silently skipped when write_lap receives stats=None
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `write_lap()` in `data/session_db.py` had `if stats is None: return 0` as first statement in the method body. Outlap after manual "Save Session" following a clear had no recorder stats → row was never written.
**Fix:** Removed the `if stats is None: return 0` guard. All stat field accesses made None-safe (`stats.field if stats else 0`). `positions_blob` JSON uses conditional list expressions. Metadata-only rows (zeros for telemetry) are now written and return a valid row id. Updated docstring explains the behaviour.
**Acceptance Criteria:**
- Practice session with outlap. Click "Save Session". Click "Clear". Click "Save Session" again. Query `SELECT is_out_lap FROM lap_records WHERE is_out_lap=1` — row exists.
- The outlap appears in History with `is_out_lap=1` and `fuel_start`/`fuel_end` non-zero.
**AWR:** AWR-051
**Group:** 14

---

**ID:** DEF-P2-030
**Title:** Save Session button creates a duplicate session when live session already open
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_save_session_to_db()` called `_db.open_session()` unconditionally. `_on_live_mode_changed()` also called `_db.open_session()` at mode-change time. Clicking Save Session during a live session created a second session row with `total_laps = 0` plus re-inserted all laps.
**Fix:** `_save_session_to_db()` now reads `self._dispatcher._session_id`. If > 0, it reuses that session and only calls `update_lap_compound()` + `update_lap_setup_id()` per lap (laps already written by EventDispatcher). Falls back to full `open_session()` path only when no live session exists.
**Acceptance Criteria:**
- Start Practice mode (session auto-opened). Complete 3 laps. Click "Save Session". Query `SELECT COUNT(*) FROM sessions` — exactly 1 session row, not 2. Compound tags applied to existing session rows.
**AWR:** AWR-052
**Group:** 14

---

**ID:** DEF-P2-031
**Title:** Qualifying outlap calming phrase never fires when using Qualifying override in Live tab
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_exit_pit()` in `telemetry/state.py` emitted `PIT_EXIT` with `session_type=self._session_type.value` (packet-detected). In a custom race, this is often `unknown` or `practice`. `voice/announcer.py` checks `event.data.get("session_type") == "qualifying"` to fire the outlap calming phrase — which therefore never matched.
**Fix:** `_exit_pit()` now uses `_session_type_override.value` when `_session_type_override is not None`, falling back to `self._session_type.value` otherwise. Same pattern already used for `LapRecord.session_type` on lines 708–711.
**Acceptance Criteria:**
- Set Live tab mode to Qualifying. Do a flying lap and come into the pits. Exit the pit. The qualifying outlap calming phrase is heard from the announcer.
**AWR:** AWR-053
**Group:** 14

---

**ID:** DEF-P2-032
**Title:** Pit fuel commentary spoken in Qualifying mode (pit/fuel alerts not suppressed)
**Status:** Already Fixed (Group 5) — Regression Guard Added (Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** Investigation showed both `_on_pit()` and `_on_fuel_low()` in `announcer.py` already guard against `"qualifying"` in `in ("practice", "qualifying")` check. No production code change needed.
**Fix:** Source-scan regression guards added to `tests/test_group14_uat_remediation.py` `TestQualifyingAlertSuppression` class.
**Acceptance Criteria:**
- Qualifying mode → fill fuel in pit → NO pit commentary spoken.
- Qualifying mode → low fuel → NO fuel-low alert spoken.
**AWR:** AWR-054
**Group:** 14

---

**ID:** DEF-P2-033
**Title:** AI Log auto-select fires on hidden widget — new entry not visible when navigating to AI Log tab
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_on_ai_log_entry()` called `_add_ai_log_list_item(auto_select=True)` which called `setCurrentRow()` immediately. If the AI Log tab (index 11) was not the active tab, `setCurrentRow()` had no visible effect. When the user later navigated to the tab the new entry was unselected.
**Fix:** Removed `auto_select=True`. Added `QTimer.singleShot(0, self._flush_ai_log_pending_select)` for deferred execution. `_flush_ai_log_pending_select()` now checks `self._tabs.currentIndex() != 11`; if the tab is not active, returns without clearing the flag. `_on_tab_changed(11)` calls `_flush_ai_log_pending_select()` so the selection fires as soon as the user navigates to the tab.
**Acceptance Criteria:**
- Run Practice Analysis with AI Log tab NOT visible. Navigate to AI Log tab. The new entry is automatically selected.
- Run Practice Analysis with AI Log tab visible. New entry is selected immediately on completion.
**AWR:** AWR-055
**Group:** 14

---

**ID:** DEF-P2-034
**Title:** AI Log entry timestamps show UTC time instead of local time
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `strategy/_ai_client.py` used `_dt.datetime.utcnow().isoformat()` for all 3 `AILogEntry` `timestamp` fields (debug dry-run, success, and error paths). `utcnow()` returns UTC time with no timezone info; for users in non-UTC timezones the timestamp is wrong.
**Fix:** All 3 occurrences changed to `_dt.datetime.now().isoformat()` which returns local wall-clock time.
**Acceptance Criteria:**
- Run a Practice Analysis. Navigate to AI Log tab. The timestamp on the new entry matches the current local time (not UTC).
**AWR:** AWR-056
**Group:** 14

---

**ID:** DEF-P2-035
**Title:** Garage tab does not show DB-saved setups; setup query exceptions silently swallowed
**Status:** Fixed — Awaiting Retest (2026-06-22 Group 14)
**Reported:** 2026-06-22 (UAT Group 14)
**Root Cause:** `_on_garage_car_selected()` in `ui/dashboard.py` had two bare `except Exception: pass` blocks around the sessions query and setup query. Exceptions were invisible. The `get_setups_for_car()` method existed in `SessionDB` but was never called from the Garage tab — only `get_all_sessions()` was called, and setups came from `config.json` only.
**Fix:** Both `except Exception: pass` blocks replaced with `import traceback; traceback.print_exc()`. Added a DB setups block: resolves `car_id` from recent sessions for the displayed car name; calls `self._db.get_setups_for_car(car_id)`; populates `_garage_setups_table` rows with name, notes excerpt, and creation date.
**Acceptance Criteria:**
- Run Practice Analysis that produces AI setup recommendations. Navigate to Garage. Select the car. The saved setup appears in the Setups table.
- Introduce a deliberate exception (disconnect DB). Check console — traceback is printed, app does not crash.
**AWR:** AWR-057
**Group:** 14

---

**ID:** DEF-P1-013
**Title:** Strategy Analysis race_params missing race_type, duration_mins, tuning_locked, allowed_tuning, bop, avail_tyres
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_ai_analysis()` race_params dict extended with `race_type`, `duration_mins`, `tuning_locked`, `allowed_tuning`, `bop`, `avail_tyres`. `RaceParams` dataclass extended with `bop: bool = False` and `avail_tyres: list = field(default_factory=list)`. `_build_race_prompt()` injects `tuning_block`, `bop_line`, and `avail_line`.
**AWR:** AWR-058
**Group:** 15

---

**ID:** DEF-P1-014
**Title:** Practice Analysis worker uses car_id=0 and opens new DB connection
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_practice_analysis()` now captures `_hist_db = self._db`, `_hist_track`, `_hist_car_name` before spawning `_worker()`. Worker calls `_hist_db.get_car_id(_hist_car_name)` to resolve car_id. No new DB connection opened.
**AWR:** AWR-059
**Group:** 15

---

**ID:** DEF-P2-036
**Title:** PTT coaching and setup_advice missing car_name, car_specs, compound
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `QueryListener.__init__()` gains `_car_specs_ref: dict` and `update_car_specs()` method. `_handle_trigger_inner()` coaching and setup_advice branches now pass `car_name`, `car_specs`, `compound`. Dashboard calls `update_car_specs()` in `_on_event_set_active()`.
**AWR:** AWR-064
**Group:** 15

---

**ID:** DEF-P2-037
**Title:** PTT setup_advice reads stale config["car_setup"] instead of live setup
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `QueryListener.__init__()` gains `_active_setup_getter` and `set_active_setup_getter()`. setup_advice branch uses getter if set, falls back to config. Dashboard wires `set_active_setup_getter(self._current_setup_dict)` at startup.
**AWR:** AWR-065
**Group:** 15

---

**ID:** DEF-P2-038
**Title:** Practice Analysis race_params missing bop field
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_run_practice_analysis()` race_params extended with `"bop": bool(_psc.get("bop", False))`. `_build_practice_prompt()` injects `bop_line` when `params.bop` is True.
**AWR:** AWR-060
**Group:** 15

---

**ID:** DEF-P2-039
**Title:** avail_tyres missing from RaceParams, both race_params dicts, and prompts
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `avail_tyres` added to `RaceParams`, both race_params dicts, `build_car_setup()`, `_build_setup_from_scratch_prompt()`. `_build_race_prompt()` and `_build_practice_prompt()` inject `avail_line`. `_run_build_setup()` passes `avail_tyres` and `req_tyres`.
**AWR:** AWR-061
**Group:** 15

---

**ID:** DEF-P2-040
**Title:** Driver feedback not passed to Practice Analysis AI
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `analyse_practice_session()` and `_build_practice_prompt()` gain `driver_feedback_str: str = ""`. Worker queries `get_recent_feedback(car_id, track, limit=5)`, formats rows, passes `driver_feedback_str`. Prompt injects `feedback_section` when non-empty.
**AWR:** AWR-062
**Group:** 15

---

**ID:** DEF-P2-041
**Title:** Previous AI recommendations not included in Practice Analysis prompt
**Status:** Fixed — Partially Effective (2026-06-23 runtime validation — see DEF-P3-013)
**Fix:** `analyse_practice_session()` and `_build_practice_prompt()` gain `prev_ai_str: str = ""`. Worker queries `get_recent_ai_recommendations("Practice Analysis", car_id, track, limit=2)`, truncates to 300 chars each, passes `prev_ai_str`. Prompt injects `prev_ai_section` when non-empty.
**AWR:** AWR-063
**Group:** 15

---

**ID:** DEF-P3-009
**Title:** Race prompt hardcodes "N laps" even for timed races
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_build_race_prompt()` computes `race_len_line` conditionally: `"Race duration: N minutes (Timed Race)"` when `params.race_type == "timed"`, else `"Race length: N laps"`. Prompt uses `{race_len_line}`.
**AWR:** AWR-066
**Group:** 15

---

**ID:** DEF-P3-010
**Title:** build_car_setup missing race context (tyre wear, fuel mult, avail_tyres, req_tyres, race_type)
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `build_car_setup()` and `_build_setup_from_scratch_prompt()` gain `tyre_wear_multiplier`, `fuel_multiplier`, `avail_tyres`, `req_tyres`, `race_type`. Prompt injects `_race_ctx_block`. `_run_build_setup()` reads all values from `_sc_build` and passes them.
**AWR:** AWR-067
**Group:** 15

---

**ID:** DEF-P3-011
**Title:** _DATA_QUALITY_NOTE absent from ai_planner.py prompts
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_DATA_QUALITY_NOTE` constant added to `ai_planner.py` (mirrors `driving_advisor.py`). Injected into both `_build_race_prompt()` and `_build_practice_prompt()`.
**AWR:** AWR-068
**Group:** 15

---

**ID:** DEF-P3-012
**Title:** _display_strategy_results does not validate AI output for tuning violations
**Status:** Fixed — Awaiting Retest (2026-06-23 Group 15)
**Fix:** `_display_strategy_results()` calls `validate_ai_setup_response()` on each strategy option's setup_changes text. If violations found, an orange warning banner is prepended to the strategy HTML. Banner shows F5A623 styling consistent with event lock banners.
**AWR:** AWR-069
**Group:** 15

---

**ID:** DEF-P3-013
**Title:** AILogEntry missing car_id and track — get_recent_ai_recommendations() always returns empty
**Status:** Fixed (2026-06-23 Group 15A)
**Root cause:** `AILogEntry` dataclass (`strategy/_ai_client.py:32`) had no `car_id` or `track` fields. `call_api()` constructed `AILogEntry` without them; `_asdict(entry)` passed to `log_ai_interaction()` wrote `car_id=0, track=""` for every `ai_interactions` row. `get_recent_ai_recommendations(feature, car_id, track)` filters on real car_id, so always returned `[]`.
**Fix (Group 15A):**
1. `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields (with defaults so existing code is not broken)
2. `call_api()` gains `car_id: int = 0` and `track: str = ""` kwargs; all three `AILogEntry` construction sites thread them through
3. `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` in `ai_planner.py` gain `car_id: int = 0`; pass `car_id=car_id, track=params.track` / `track=track` to `call_api()`
4. All four `call_api()` sites in `DrivingAdvisor` pass `car_id=self._car_id_ref[0], track=self._config.get("strategy", {}).get("track", "")`
5. `_run_ai_analysis()` resolves `_car_id_strat` before worker; passes `car_id=_car_id_strat` to `analyse_strategy()`
6. `_run_practice_analysis()` passes `car_id=_car_id_hist` to `analyse_practice_session()`
7. `_run_build_setup()` resolves `_car_id_build` before worker; passes `car_id=_car_id_build` to `build_car_setup()`
8. `_on_ai_log_entry_dict()` in dashboard reconstructs AILogEntry from DB rows with `car_id` and `track` populated
**AWR:** AWR-063 (now CLOSED)
**Group:** 15A
**Tests:** `tests/test_group15a_ai_log_car_track.py` (56 tests — all pass)

---

### P3 Medium

---

**ID:** DEF-P3-001
**Title:** Brake balance spinbox step increment unverified
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Source scan confirmed `_setup_bb.setSingleStep(1)` at `ui/dashboard.py:3984`. Called immediately after widget creation in `_build_car_setup_group()`. No code change required — already correct.
**Description:** `_setup_bb` is created by a helper function that may not call `setSingleStep(1)`. In GT7 the brake balance adjustment is 1 unit per click. If the step defaults to a non-1 value the control does not match in-game behaviour.
**Expected Behaviour:** Each click of the brake balance spinbox changes the value by exactly 1.
**Acceptance Criteria:**
- Click the up arrow on the brake balance spinbox once. Value increments by exactly 1.
- Click the down arrow once. Value decrements by exactly 1.
- Range is confirmed against GT7 in-game brake balance scale.
See `TestBrakeBalanceStep` in `test_group5_fixes.py`.

---

**ID:** DEF-P3-002
**Title:** Active tyre compound not displayed on Live Race Engineer tab
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_lbl_live_tyre_compound` already existed in Live tab (created at `ui/dashboard.py:606`). Added update call in `_on_live_mode_changed()` so the label refreshes from `_config["strategy"]["mandatory_compounds"]` whenever mode changes. `_sync_setup_builder_from_event()` also updates it when an event is set active (existing behaviour confirmed).
**Description:** The Live tab tyre widget shows four temperature circles but no label indicating the current compound (e.g., "Racing Medium"). The compound is available in `_config["strategy"]["mandatory_compounds"]`.
**Expected Behaviour:** A compound label (`_lbl_live_tyre_compound`) appears above the tyre temperature grid on the Live tab. It updates when the event is set active and when the mode changes.
**Acceptance Criteria:**
- Set an event with Required Tyre = Racing Hard and set it active. Live tab shows "Tyre: Racing Hard" above the temperature circles.
- Change to Racing Medium and set active. Label updates without restart.
- No event set — label shows "Tyre: —".
See `TestLiveTyreCompoundDisplay` in `test_group5_fixes.py`.

---

**ID:** DEF-P3-003
**Title:** Newly arriving laps in Practice Review do not inherit tyre compound from previous lap
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** In `_add_bank_lap_row()`, before the `existing_tag` assignment, added compound inheritance logic: if `compound` is empty and `lap_num` not yet in `_lap_compound_tags`, resolves compound from the highest-numbered prior key in `_lap_compound_tags` or falls back to `_default_lap_compound`.
**Description:** When a new lap row is appended to the Practice Review table, it always initialises the compound selector to `_default_lap_compound` regardless of what the previous lap's compound was.
**Expected Behaviour:** When a new lap row is added, it checks the compound on the previous lap (`_lap_compound_tags.get(lap_num - 1, _default_lap_compound)`) and initialises the selector to that value.
**Acceptance Criteria:**
- Set lap 5 compound to "Racing Medium" in Practice Review.
- Complete lap 6. The newly added row shows "Racing Medium" as the default compound.
- Change lap 6 to "Racing Hard". Complete lap 7. Lap 7 shows "Racing Hard".
- Laps before lap 5 are unchanged.

---

**ID:** DEF-P3-004
**Title:** Race type mutual exclusivity not enforced in Event Planner
**Status:** Fixed — Awaiting Retest (register correction 2026-06-22)
**Fix:** Register was stale. `_on_race_type_changed()` was already implemented in `_build_event_planner_tab()`: disables `_evt_laps` when "timed" selected, disables `_evt_duration` otherwise, and is called once at build time for immediate enforcement. `_on_event_set_active()` correctly uses `"timed" if "timed" in rt_str.lower() else "lap"`. DEF-P1-004 fix ensures AI prompt uses `race_type` and `duration_mins` fields. See `TestRegisterCorrections` in `test_group6_fixes.py`.
**Description:** When "Timed Race" is selected in the race type dropdown, the Laps field remains editable. The AI prompt may receive `total_laps = 1` for a timed race, producing an incorrect strategy recommendation.
**Expected Behaviour:** Selecting "Timed Race" disables and dims the Laps spinbox. Selecting "Lap Race" disables and dims the Duration spinbox. The AI prompt builder uses a "timed race" description and `race_laps = 0` for timed races.
**Acceptance Criteria:**
- Select "Timed Race" in Event Planner. Laps field is greyed out and non-interactive.
- Select "Lap Race". Duration field is greyed out.
- Save a timed race event and set it active. AI setup prompt contains "timed race" not "1-lap race".

---

**ID:** DEF-P3-005
**Title:** Pit window is static and not recalculated on fuel or pace deviation
**Status:** Open
**Description:** Pit window is fixed at `stint.end_lap - 2` (warning) / `stint.end_lap` (box call). It is not updated when actual fuel consumption or lap pace deviates from the strategy plan.
**Expected Behaviour:** After each lap, the strategy engine checks actual fuel remaining and current pace against the planned stint. If deviation exceeds tolerance, the pit window recalculates and a revised box call is issued. `_replan_after_overdue()` considers fuel state, not only lap count.
**Acceptance Criteria:**
- Use 30% more fuel than the plan over 5 laps. Pit window moves earlier by at least 1 lap. Voice alert indicates the revised window.
- Save 20% fuel. Pit window extends by at least 1 lap.
- Pit window recalculation is logged in the Debug tab.

---

**ID:** DEF-P3-006
**Title:** Practice Review session summary not recalculated after loading from History
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_refresh_practice_summary()` method that iterates `_lap_table`, reads lap time ms (col 3) and fuel used (col 8), and updates `_lbl_pr_best`, `_lbl_pr_avg`, `_lbl_pr_fuel`, `_lbl_pr_laps`. Called at end of `_on_history_load_session()` and also at end of `_add_lap_row()` (live laps) to keep summary consistent during live sessions.
**Description:** When a historical session is loaded from the History tab into Practice Review, the Session Summary group (Best Lap, Avg Lap, Avg Fuel/Lap, Laps) is not recalculated from the newly loaded rows.
**Expected Behaviour:** After `_on_history_load_session()` populates the lap table, the session summary labels are immediately recalculated: best time, average time, average fuel per lap, and total lap count.
**Acceptance Criteria:**
- Load a historical session with 10 laps from History.
- Practice Review Session Summary shows the correct best lap, average lap, average fuel, and lap count.
- These values match a manual calculation from the same session in History.

---

---

**ID:** DEF-P3-007
**Title:** Disabled race type alternate field not visually dimmed when race type changes
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 6 partial)
**Related:** DEF-P3-004 (race type mutual exclusivity — was Partially Fixed)
**Description:** When "Timed Race" is selected in Event Planner, the Laps spinbox is correctly disabled (setEnabled(False)) but its text colour does not change. It appears the same as enabled fields. The user cannot visually distinguish which field is active without clicking it. Same issue in reverse when switching to Lap Race (Duration spinbox disabled but not greyed).
**Expected Behaviour:** The disabled spinbox should have visibly muted text colour (e.g., `#555` on the dark background). The enabled spinbox should have normal white text.
**Acceptance Criteria:**
- Select Timed Race in Event Planner. Laps spinbox text appears greyed/muted.
- Select Lap Race. Duration spinbox text appears greyed/muted; Laps spinbox returns to normal white.

---

**ID:** DEF-P3-008
**Title:** Top speed target never populated from valid practice telemetry
**Status:** Open
**Reported:** 2026-06-22 (UAT Group 6 partial)
**Related:** DEF-P2-015 (top speed artefact guard — was Partially Fixed)
**Description:** The 11 km/h invalid artefact is correctly rejected by the `ms >= 50` guard (DEF-P2-015 fix). However, no valid top speed reading ever populates `_spin_top_speed` during a real practice session — the field always shows "—". The telemetry field used may not actually capture the session maximum speed, or the `>= 50` threshold may be too high and reject real low-speed readings early in the session.
**Expected Behaviour:** After driving at least one full lap that includes a straight, `_spin_top_speed` should show the highest speed recorded during that lap or session (typically 120–350 km/h for GT7 cars on normal circuits).
**Acceptance Criteria:**
- Drive at least one lap in Practice mode on any circuit with a straight.
- Setup Builder → Transmission → Top Speed shows a value ≥ 120 km/h (or "—" only if the telemetry data genuinely never exceeded 50 km/h on that lap).
- `SELECT MAX(max_speed_kmh) FROM lap_records WHERE session_id = <active_session>` returns a plausible value (> 0).

---

### P4 Low

---

**ID:** DEF-P4-001
**Title:** PTT button and voice status indicator are in Settings tab only
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** Added `_live_ptt_status_lbl` QLabel to the Live tab info row (after the Mode combo, before the stretch). `_on_ptt_status()` now updates both `_ptt_status_lbl` (Settings tab) and `_live_ptt_status_lbl` (Live tab). Status transitions (RADIO READY / TRANSMITTING / PROCESSING / ENGINEER RESPONDING) visible on the Live tab during a race without switching tabs.
**Description:** The PTT button and voice/microphone status indicator are located in the Settings tab. During an active race the driver cannot leave the Live tab to check PTT status or trigger a query. Spec §12.8 requires both controls on the Live Race Engineer tab.
**Expected Behaviour:** PTT button and voice status indicator appear on the Live Race Engineer tab, accessible without tab switching during a race. Settings tab may retain configuration-level controls.
**Acceptance Criteria:**
- Live Race Engineer tab contains a visible PTT button and voice status indicator.
- Pressing PTT from the Live tab triggers the full recording and response cycle.
- Voice status transitions (IDLE / TRANSMITTING / PROCESSING / RADIO READY) are visible on the Live tab.
See `TestPTTOnLiveTab` in `test_group5_fixes.py`.

---

**ID:** DEF-P4-002
**Title:** AI model hardcoded to claude-sonnet-4-6 instead of claude-opus-4-8
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_MODEL` constant removed from `strategy/_ai_client.py`; replaced with `_DEFAULT_MODEL = "claude-opus-4-8"`. `call_api()` gains `model: str | None = None` parameter; resolves `effective_model` with whitespace guard before falling back to `_DEFAULT_MODEL`. All `AILogEntry(model=...)` fields updated. `model` parameter added to `analyse_strategy`, `analyse_practice_session`, `build_car_setup`, `analyse_tyre_degradation` in `ai_planner.py` and `propose_profile_update` in `profile_updater.py`. All 4 `call_api` callers in `driving_advisor.py` and all 5 dashboard call sites pass `model=self._config.get("anthropic", {}).get("model") or None`.
**Description:** `strategy/_ai_client.py` has the model string hardcoded to `claude-sonnet-4-6`. The project default is `claude-opus-4-8`. No model selection UI exists.
**Expected Behaviour:** Default model is `claude-opus-4-8`. A model selector in Settings allows the user to choose between available Claude models. Selected model is persisted to config and used for all AI calls.
**Acceptance Criteria:**
- AI interaction log shows `"model": "claude-opus-4-8"` for all calls where no override is set.
- Settings tab contains a model selector.
- Changing the model in Settings causes the next AI call to use the newly selected model.

---

**ID:** DEF-P4-003
**Title:** Fuel formula uses additive lap safety instead of percentage multiplier
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix:** `_fuel_target_for_next()` and `build_fuel_check_response()` in `strategy/engine.py` now use `avg × laps × multiplier`. Module-level `_FUEL_MULTIPLIERS = {"safe": 1.08, "balanced": 1.05, "aggressive": 1.02}` added. Strategy mode read from `config["fuel"]["strategy"]` (defaults to "balanced"). `safety_margin_laps` additive pattern removed. 9 new unit tests added covering all three multipliers and edge cases. All 48 tests pass.
**Description:** `strategy/engine.py` `_fuel_target_for_next()` computed fuel as `avg × (laps + safety_margin_laps)`. Spec §18.1 requires `safe_fuel = avg × laps_remaining × multiplier` with per-strategy margins: Safe 8%, Balanced 5%, Aggressive 2%.
**Expected Behaviour:** Fuel target uses a percentage multiplier over laps remaining. Safe = 1.08, Balanced = 1.05, Aggressive = 1.02.
**Acceptance Criteria:**
- With `avg_fuel_per_lap = 3.0L` and 10 laps remaining, Balanced strategy targets 31.5L. ✓ (test passes)
- Safe strategy targets 32.4L. ✓ Aggressive targets 30.6L. ✓
- Unit test covers all three multipliers. ✓

---

**ID:** DEF-P2-QRF
**Title:** Race-finished announcement fires in Qualifying mode
**Status:** Fixed — Awaiting Retest (2026-06-21)
**Fix (two-part):**
1. `voice/announcer.py` `_on_race_finish()`: added mode guard at top — `if _session_mode != "race": return`. Announcement now only fires when announcer is in Race mode.
2. `telemetry/state.py` timed race RACE_FINISHED path: changed `!= SessionType.PRACTICE` to `not in (SessionType.PRACTICE, SessionType.QUALIFYING)`. Prevents the RACE_FINISHED event from being emitted at all when session type is Practice or Qualifying.
**Description:** When the qualifying timer expired or lap count matched the race lap count while in Qualifying mode, `EventType.RACE_FINISHED` was emitted and `_on_race_finish()` announced "Race finished" to the driver. The timed race path in `state.py` guarded against Practice but not Qualifying.
**Expected Behaviour:** "Race finished" is only spoken when the Live mode is Race. Practice and Qualifying timers do not trigger the race-finished announcement.
**Acceptance Criteria:**
- Set Live mode to Qualifying. Let a timed session end. No "Race finished" announcement.
- Set Live mode to Race. Complete the race. Announcement fires correctly.
- Practice laps never trigger race-finished regardless of lap count.
See `TestQualifyingRaceFinished` in `test_group5_fixes.py`.

---

## Open Enhancements

---

**ID:** ENH-001
**Title:** Dashboard tab redesign
**Status:** Deferred — pending design decision
**Description:** The Dashboard tab was specified as the primary landing screen providing at-a-glance overview of active event, car, setup, strategy, and session state. It was suppressed in Architecture Stabilisation. See SUP-001.
**Expected Behaviour:** A Dashboard tab provides a single-screen summary with quick-links to other tabs. All summary fields populate from the active event and session state.
**Acceptance Criteria:** Dashboard tab renders without error. Active event, car, setup, and session state are displayed correctly.

---

**ID:** ENH-002
**Title:** PTT intents — should_push, save_fuel, where_losing_time not implemented
**Status:** Open
**Description:** Three intents from spec §19 are absent from `voice/query_listener.py` `_INTENT_KEYWORDS`. All other 13 intents are implemented.
**Expected Behaviour:** Saying "should I push?", "how much fuel can I save?", or "where am I losing time?" triggers the corresponding intent and returns an AI-generated response using current session context.
**Acceptance Criteria:** All three intents resolve from natural speech input. Responses reference current session data.

---

**ID:** ENH-003
**Title:** Strategy-becoming-impossible scenario not detected or announced
**Status:** Open
**Description:** When fuel remaining drops below a viable 1-stop strategy and tyre life is insufficient to extend the stint, no warning is issued. The driver may continue unaware the strategy is no longer achievable.
**Expected Behaviour:** `strategy/engine.py` detects when no valid stint plan can reach the end of the race. A voice alert fires once. A recalculation attempt is made and logged in Debug.
**Acceptance Criteria:** Simulated fuel-critical scenario triggers the voice alert and a Debug log entry. Alert fires once, not on every lap.

---

**ID:** ENH-004
**Title:** Live Race Engineer tab missing fuel target, estimated laps remaining, and pit window display
**Status:** Open
**Description:** The Live tab shows a fuel bar but not numeric fuel target, estimated laps remaining on current fuel, or pit window. Spec §9.3 and §12.8 require all three.
**Expected Behaviour:** Live tab displays current fuel (L), fuel target for next stint (L), estimated laps remaining on current fuel, and pit window (earliest — latest lap to box). All values update after each lap.
**Acceptance Criteria:** After lap 5 of a 25-lap race, all four values are visible and correct.

---

**ID:** ENH-005
**Title:** Practice Review missing per-lap tyre temperature trends
**Status:** Open
**Description:** Practice Review lap table has a Compound column but no tyre temperature data. Spec §12.6 requires tyre temperature trends per lap. `LapRecord` and `lap_records` do not store `tyre_temp_average`.
**Expected Behaviour:** Practice Review lap table includes average tyre temperature per lap sourced from `lap_records.tyre_temp_avg`.
**Acceptance Criteria:** After 5 laps, each row shows an average tyre temperature matching the DB value.

---

**ID:** ENH-006
**Title:** Setup Builder missing structured test plan output
**Status:** Open
**Description:** AI responses contain test plan suggestions in free text but no structured test plan widget exists. Spec §12.5 requires a dedicated test plan display.
**Expected Behaviour:** After an AI setup recommendation, a "Test Plan" section displays as a structured list: outlap checks, key corners to evaluate, conditions to watch for.
**Acceptance Criteria:** After AI Setup Analysis, a structured Test Plan section appears with at least 3 specific items.

---

**ID:** ENH-007
**Title:** AI driver feedback interpretation function not implemented
**Status:** Open
**Description:** Spec §14.1 requires a discrete `driver_feedback_interpretation` AI function that takes raw driver ratings and returns a structured handling diagnosis. Feedback is stored but never interpreted as a standalone AI call.
**Expected Behaviour:** Submitting driver feedback triggers an AI interpretation call returning: primary handling diagnosis, likely setup cause, suggested investigation area. Result stored in `ai_interactions` with `feature = 'feedback_interpretation'`.
**Acceptance Criteria:** Submitting feedback with corner entry understeer and exit oversteer triggers the interpretation call. Response contains a handling diagnosis. One `ai_interactions` row added with `feature = 'feedback_interpretation'`.

---

**ID:** ENH-008
**Title:** AI model selector not available in Settings
**Status:** Open
**Description:** No Settings UI exists to change the AI model. Related to DEF-P4-002.
**Expected Behaviour:** Settings tab contains a model selector dropdown. Selection is saved to `config["anthropic"]["model"]` and used for all subsequent AI calls.
**Acceptance Criteria:** Changing the model and rerunning an AI call shows the new model ID in the AI interaction log.

---

## Superseded Requirements

---

**ID:** SUP-001
**Title:** Dashboard tab
**Status:** Superseded — deferred to future redesign
**Description:** Specified as the primary landing screen. Not built and officially suppressed during Architecture Stabilisation. Tracked as ENH-001 for future redesign.
**Expected Behaviour:** N/A — requirement removed from current scope.
**Acceptance Criteria:** N/A.

---

**ID:** SUP-002
**Title:** Session Loader in Practice Review
**Status:** Superseded — removed in P6-A (2026-06-21)
**Description:** Session Loader widget (track/car dropdowns, session combo, Load and Delete buttons) embedded in Practice Review tab. Historical session loading now belongs exclusively to the History tab. `_build_practice_lap_bank_group()` call removed from `_build_practice_review_tab()`.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Practice Review contains no Session Loader widget. History tab provides session loading.

---

**ID:** SUP-003
**Title:** Car selector in Event Planner
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only car label (`_lbl_evt_active_car`) displayed in Event Planner. Car selection is owned by the Garage tab. Label removed as it added no functional value.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Event Planner contains no car label row.

---

**ID:** SUP-004
**Title:** Car selector in Setup Builder
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only car label (`_lbl_setup_car`) in Setup Builder form. Removed. Car is read from `_config["strategy"]["car"]` at call time.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Setup Builder contains no "Car:" read-only label row.

---

**ID:** SUP-005
**Title:** Track selector in Setup Builder
**Status:** Superseded — removed in P6-B (2026-06-21)
**Description:** Read-only track label (`_lbl_setup_track`) in Setup Builder form. Removed. Track is read from `_config["strategy"]["track"]` wherever needed.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Setup Builder contains no "Track:" read-only label row.

---

**ID:** SUP-006
**Title:** Pit loss and lap/fuel tolerance spinboxes in Strategy Builder
**Status:** Superseded — removed in P6-C (2026-06-21)
**Description:** Three `QDoubleSpinBox` widgets (`_ai_pit_loss`, `_ai_lap_tolerance`, `_ai_fuel_tolerance`) allowed manual entry of race detail parameters in Strategy Builder. Values now come from active event config defaults. Widgets removed; callers updated to use `_config["strategy"].get("pit_loss_secs", 23.0)`.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Strategy Builder AI Analysis group contains no pit loss, lap tolerance, or fuel tolerance spinboxes.

---

**ID:** SUP-007
**Title:** Manual fuel burn input in Strategy Builder
**Status:** Superseded — removed in P6-C (2026-06-21)
**Description:** Manual fuel burn spinbox existed in Strategy Builder. Fuel burn is now authoritative from `RaceStateTracker.avg_fuel_per_lap`. Manual override removed.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Strategy Builder contains no manual fuel burn input spinbox.

---

**ID:** SUP-008
**Title:** Tyres in BoP tuning permissions
**Status:** Superseded — removed in P6-D (2026-06-21)
**Description:** "Tyre compound selection" was listed as a tuning category in `_TUNING_CATEGORIES`. In GT7 tyres are always freely changeable regardless of BoP. The entry was removed. Tyre widgets are always enabled in `_apply_setup_permissions()` unconditionally.
**Expected Behaviour:** N/A — requirement removed.
**Acceptance Criteria:** Tuning permissions list does not include a "Tyres" entry. Tyre dropdowns are always enabled in Setup Builder.

---

## Fixed Issues

---

**ID:** FIX-001
**Title:** Schema migration infrastructure missing — no PRAGMA user_version guard
**Status:** Fixed — 2026-06-20
**Description:** No schema version tracking. DDL ran on every startup. Fixed by adding `_migrate()` dispatcher, `PRAGMA user_version` read/write, idempotent `ALTER TABLE` via try/except per column, and `PRAGMA foreign_keys = ON` on every connection.

---

**ID:** FIX-002
**Title:** Missing DB tables — events, cars, user_profile, setups, lap_telemetry
**Status:** Fixed — 2026-06-20
**Description:** Five tables required by the spec did not exist. Created in schema v1 migration: `events`, `cars` (seeded from car_specs.json), `user_profile`, `setups`, `lap_telemetry` (compressed frame blob per lap). FK columns added to `sessions` and `lap_records`.

---

**ID:** FIX-003
**Title:** Events stored only in config.json with no DB backup or FK integrity
**Status:** Fixed — 2026-06-20
**Description:** All Event Planner CRUD redirected to `_db.upsert_event()`. Startup migration seeds DB from config on first run. `config["events"]` is no longer the authoritative store.

---

**ID:** FIX-004
**Title:** Setups stored only in config.json — diverged from setup_snapshots table
**Status:** Fixed — 2026-06-21
**Description:** Setup CRUD redirected to `setups` table via `_db.save_setup()` and `_db.update_setup()`. `get_all_setups_legacy()` added for backward-compatible loading. `_migrate_setups_to_db()` seeds DB from config on first run. `_setup_save()` writes to DB on every save.

---

**ID:** FIX-005
**Title:** Per-frame telemetry discarded after each lap — no TelemetrySample table
**Status:** Fixed — 2026-06-21
**Description:** `last_lap_frames()` added to `LapTelemetryRecorder`. EventDispatcher calls `recorder.last_lap_frames()` after each lap and passes the frame list to `write_lap(frames=...)`. Frames are zlib-compressed and stored in `lap_telemetry`.

---

**ID:** FIX-006
**Title:** Extended LapStats fields not persisted to lap_records
**Status:** Fixed — 2026-06-21
**Description:** `oversteer_count`, `oversteer_throttle`, `kerb_count`, `bottoming_count`, `snap_throttle_count`, `max_lat_g`, `off_track_count`, `tyre_temp_avg`, `is_out_lap`, `is_pit_lap`, `delta_ms`, `position`, `session_type`, `event_positions_json` columns added via migration and populated in `write_lap()`.

---

**ID:** FIX-007
**Title:** Driver feedback never injected into AI prompts
**Status:** Fixed — 2026-06-21
**Description:** `get_recent_feedback(car_id, track, limit=5)` added to `SessionDB`. `_get_driver_feedback_context()` added to `DrivingAdvisor`. All three prompt builders include a "## Recent Driver Feedback" section when feedback records exist for the current car and track.

---

**ID:** FIX-008
**Title:** Previous AI recommendations never fed back into prompts — AI amnesia
**Status:** Fixed — 2026-06-21
**Description:** `get_recent_ai_recommendations(feature, car_id, track, limit=2)` added to `SessionDB`. `_get_previous_ai_context(feature)` added to `DrivingAdvisor`. All prompt builders include a "## Previous AI Recommendations" section (truncated to 300 chars each) when prior calls exist for the same feature, car, and track.

---

**ID:** FIX-009
**Title:** Event profile not included in AI prompts
**Status:** Fixed — 2026-06-21
**Description:** `set_event_context(event_dict)` and `_get_event_context_block()` added to `DrivingAdvisor`. All prompts include a "## Event Rules" section covering track, race type, tyre wear, fuel multiplier, BoP, weather, damage, and required tyres. `_on_event_set_active()` calls `set_event_context()`.

---

**ID:** FIX-010
**Title:** Tyre compound not passed to AI calls
**Status:** Fixed — 2026-06-21
**Description:** `compound: str = ""` parameter added to all three `build_*_response()` and `_build_*_prompt()` methods in `DrivingAdvisor`. Compound injected as "Current tyre compound: X" in the header block. `_setup_analyse_ai()` passes compound from `_config["strategy"]["mandatory_compounds"]`.

---

**ID:** FIX-011
**Title:** AI prompts did not distinguish measured, calculated, and estimated data
**Status:** Fixed — 2026-06-21
**Description:** `_DATA_QUALITY_NOTE` class constant added to `DrivingAdvisor`. All prompts include a "## Data Quality Note" section with source annotations. Inline metric tags added throughout prompt builders.

---

**ID:** FIX-012
**Title:** Active tyre compound not written to lap_records
**Status:** Fixed — 2026-06-21
**Description:** `set_compound(compound: str)` added to `RaceStateTracker`. `_on_compound_selected()` in dashboard calls `self._tracker.set_compound(norm)`. EventDispatcher reads `self._tracker._current_compound` at lap save time and passes it to `write_lap(compound=...)`.

---

**ID:** FIX-013
**Title:** History tab Load button had no implementation
**Status:** Fixed — 2026-06-21
**Description:** `_on_history_load_session()` was a stub delegating to the removed session loader. Replaced with a direct implementation reading `_hist_selected_session_id`, calling `_db.get_session_laps(sid)`, and populating Practice Review via `_add_bank_lap_row()`.

---

**ID:** FIX-014
**Title:** Session mode not pushed to tracker and announcer at startup
**Status:** Fixed — 2026-06-21
**Description:** `set_session_mode()` and `set_session_type_override()` were only called from `_on_live_mode_changed()`. If the user never changed mode, tracker and announcer stayed at construction defaults. Fixed by calling `_on_live_mode_changed(config["live"]["mode"])` in the startup sequence.

---

## Awaiting Retest

Items here are code-complete and pass all 45 unit tests. Runtime verification against the running application and live GT7 telemetry is required before promotion to Fixed Issues.

---

**ID:** AWR-001
**Title:** Per-lap frame telemetry — verify frame_count populated after real lap
**Status:** Awaiting runtime verification
**Description:** FIX-005 is implemented. Requires a real lap to confirm `lap_telemetry` rows are written with non-zero frame counts.
**Expected Behaviour:** After completing one lap, `lap_telemetry` contains a row with `frame_count > 0`.
**Acceptance Criteria:** `SELECT frame_count FROM lap_telemetry ORDER BY id DESC LIMIT 1` returns a value > 0 immediately after the first lap.

---

**ID:** AWR-002
**Title:** Events persist from DB after config.json events section removed
**Status:** Awaiting runtime verification
**Description:** FIX-003 is implemented. Requires a restart test with `config["events"]` absent to confirm DB is authoritative.
**Expected Behaviour:** App loads event list from DB on startup with no errors and no dependency on `config["events"]`.
**Acceptance Criteria:** Delete `events` key from config.json. Restart app. Event Planner populates correctly from DB.

---

**ID:** AWR-003
**Title:** Setups persist from DB across restarts
**Status:** Awaiting runtime verification
**Description:** FIX-004 is implemented. Requires restart test to confirm `get_all_setups_legacy()` returns correct setups from DB.
**Expected Behaviour:** Saved setups appear in the setup list after restart without relying on config.json.
**Acceptance Criteria:** Save a new setup. Restart app. Setup appears in the list without config.json entry.

---

**ID:** AWR-004
**Title:** AI prompts contain driver feedback, event profile, and previous recommendations sections
**Status:** Awaiting runtime verification
**Description:** FIX-007 through FIX-009 implemented. Requires an AI call with `GT7_AI_DEBUG=1` to verify prompt structure.
**Expected Behaviour:** Debug log for an AI coaching call shows all three injected sections where data exists.
**Acceptance Criteria:** Prompt debug output contains "## Recent Driver Feedback", "## Event Rules", and "## Previous AI Recommendations" (where data exists for that car/track).

---

**ID:** AWR-005
**Title:** Active compound written to lap_records after each lap
**Status:** Awaiting runtime verification
**Description:** FIX-012 implemented. Requires setting a compound in Practice Review and completing a lap.
**Expected Behaviour:** The compound selected in Practice Review is present in `lap_records.compound` for each lap completed after the selection.
**Acceptance Criteria:** Set compound to "Racing Medium". Complete a lap. `SELECT compound FROM lap_records ORDER BY id DESC LIMIT 1` returns `'Racing Medium'`.

---

**ID:** AWR-006
**Title:** History tab Load populates Practice Review lap table
**Status:** Awaiting runtime verification
**Description:** FIX-013 implemented. Requires runtime test to confirm rows load from History into Practice Review. Note: session summary recalculation after load is tracked separately as DEF-P3-006.
**Expected Behaviour:** Selecting a session in History and clicking Load populates the Practice Review lap table with all laps from that session.
**Acceptance Criteria:** Select a session with at least 5 laps from History. Lap table in Practice Review shows all 5 rows. (Session summary recalculation tracked under DEF-P3-006.)

---

**ID:** AWR-007
**Title:** Strategy Builder AI analysis runs without error after spinbox removal
**Status:** Awaiting runtime verification
**Description:** P6-C removed `_ai_pit_loss`. `_run_ai_analysis()` now reads from `_config["strategy"].get("pit_loss_secs", 23.0)`. Requires a Strategy Builder AI run to confirm no AttributeError.
**Expected Behaviour:** Strategy Builder AI analysis completes. No AttributeError referencing `_ai_pit_loss`, `_ai_lap_tolerance`, or `_ai_fuel_tolerance`.
**Acceptance Criteria:** Run AI analysis in Strategy Builder. No errors in console. AI payload includes `"pit_loss_secs"` sourced from config.

---

**ID:** AWR-008
**Title:** Setup Builder and Event Planner show no removed car/track labels
**Status:** Awaiting runtime verification
**Description:** P6-B removed `_lbl_setup_car`, `_lbl_setup_track`, and `_lbl_evt_active_car`. Requires visual and error-free confirmation.
**Expected Behaviour:** Setup Builder has no "Car:" or "Track:" read-only label rows. Event Planner has no "Car:" read-only label row. No AttributeError in `_sync_setup_builder_from_event()`.
**Acceptance Criteria:** Open both tabs. Labels are absent. Set an event active. No errors in console.

---

**ID:** AWR-009
**Title:** Save Session does not crash after _lbl_bank_status removal (DEF-P1-003)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-003 added `_set_bank_status()` helper and replaced all 20 bare `.setText()` call sites. Requires a runtime click of "Save Session" in Practice Review to confirm no AttributeError.
**Expected Behaviour:** Clicking "Save Session" with at least one live lap in the table saves the session to the DB without crashing. Status feedback (if any) is silent when `_lbl_bank_status` is absent.
**Acceptance Criteria:**
- Click "Save Session" in Practice Review with ≥ 1 live lap. No AttributeError. No crash.
- `SELECT id, total_laps FROM sessions ORDER BY id DESC LIMIT 1` reflects the saved session.
- If the DB write fails, the error is caught and no unhandled exception propagates to the user.

---

**ID:** AWR-010
**Title:** Practice Analysis prompt shows correct race type for timed and lap events (DEF-P1-004)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-004 added `race_type` and `duration_mins` to `RaceParams` and branches the prompt on race type. Unit tests pass. Requires a live Practice Analysis run with `GT7_AI_DEBUG=1` to confirm the prompt content.
**Expected Behaviour:** Prompt for a timed race event contains "Race duration: X minutes (Timed Race)" and not "Race length: N laps". Prompt for a lap race contains "Race length: N laps".
**Acceptance Criteria:**
- Set Event Planner to Timed Race, 40 minutes. Set event active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Debug log contains "Race duration: 40 minutes (Timed Race)". Does not contain "Race length: 1 laps" or "Race length:" at all.
- Set Event Planner to Lap Race, 25 laps. Set event active. Re-run.
- Debug log contains "Race length: 25 laps".

---

**ID:** AWR-011
**Title:** Practice mode does not trigger RACE_FINISHED after timed event duration (DEF-P1-008)
**Status:** Awaiting runtime verification
**Test run:** 65/70 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-008 added `_session_type_override != SessionType.PRACTICE` guard to the RACE_FINISHED condition in `telemetry/state.py`. Unit tests pass for both suppression (practice) and correct firing (race). Requires a 40-minute live practice session to confirm silence.
**Expected Behaviour:** With a 40-minute timed race event active and Live tab in Practice mode, no "Race ended" voice announcement and no RACE_FINISHED event after 40 minutes.
**Acceptance Criteria:**
- Set 40-minute timed race event active. Switch to Practice mode. Drive for 40+ minutes. No "Race ended" announcement.
- `RACE_FINISHED` does not appear in the Debug tab event log.
- Switch to Race mode with the same event. After 40 minutes, the announcement fires correctly.

---

**ID:** AWR-012
**Title:** Practice Analysis prompt respects BoP tuning lock (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-005 added constraint block injection to `_build_practice_prompt()`. Unit tests pass. Requires a live Practice Analysis run with BoP enabled.
**Expected Behaviour:** With BoP=On, Tuning=Off: prompt contains "TUNING LOCKED" and no setup field values. With partial restrictions: prompt contains "EVENT TUNING RESTRICTIONS" listing locked categories.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Activate event. Run Practice Analysis with `GT7_AI_DEBUG=1`. Prompt contains "TUNING LOCKED". No ride height, spring, aero, or LSD numeric values in setup section.
- Set Event with BoP=On, Tuning=Yes, Allowed=[suspension]. Prompt contains "EVENT TUNING RESTRICTIONS" listing aero and differential as locked. Suspension values appear; aero values do not.

---

**ID:** AWR-013
**Title:** Tyre compound counts in Practice Analysis prompt match lap table (DEF-P1-006)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-006 corrects compound resolution in `_add_bank_lap_row()` and clears stale `_lap_compound_tags` on session load. Requires loading a session with a known compound mix.
**Expected Behaviour:** After loading a session with 15 RM laps and 7 RS laps, the Practice Analysis prompt compound counts match the visible table counts exactly.
**Acceptance Criteria:**
- Load session with 15 RM + 7 RS laps. Verify table shows correct compounds. Run Practice Analysis with `GT7_AI_DEBUG=1`. Prompt shows RM: 15, RS: 7 (or equivalent) — not the reverse.
- Reload the session a second time. Counts unchanged.

---

**ID:** AWR-014
**Title:** Fuel burn in Strategy Builder matches average from loaded historical session (DEF-P1-007)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P1-007 adds `_loaded_session_avg_fuel` which takes priority over the live tracker. Requires loading a historical session and checking the Strategy Builder fuel display.
**Expected Behaviour:** After loading 10 historical laps averaging 4.2 L/lap, Strategy Builder Fuel Burn shows ~4.2 L/lap. After a live lap completes, reverts to live tracker.
**Acceptance Criteria:**
- Load a session with laps averaging 4.2 L/lap from History. Strategy Builder Fuel Burn Auto updates to ~4.2. Practice Analysis prompt receives 4.2 as `fuel_burn`.
- Complete one live lap (any value). Strategy Builder Fuel Burn updates to the live tracker value.

---

**ID:** AWR-015
**Title:** Fuel start and fuel end appear after session reload (DEF-P2-014)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-014 adds `fuel_start`/`fuel_end` columns to DB (v2 migration) and wires them through `write_lap()`, `get_session_laps()`, and `_add_bank_lap_row()`. Requires completing laps and reloading.
**Expected Behaviour:** After completing laps and reloading from History, Fuel Start and Fuel End columns show the correct per-lap values.
**Acceptance Criteria:**
- Complete 3 laps in Practice. Each row shows numeric Fuel Start and Fuel End.
- Reload the session from History. Same columns show the same values.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 3` returns non-zero values.

---

**ID:** AWR-016
**Title:** Tyre wear multiplier in Practice Analysis prompt matches current event setting (DEF-P2-012)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-012 ensures `tyre_wear_multiplier` is read freshly from `_psc` each call. Debug log added. Requires activating an event with a specific wear value and running Practice Analysis.
**Expected Behaviour:** Prompt tyre wear matches the active event exactly. Debug log shows `[PracticeAnalysis] tyre_wear_multiplier=X.XX (from Event config)`.
**Acceptance Criteria:**
- Set event tyre wear to 1.0x. Activate. Run Practice Analysis. Prompt: "Tyre wear rate is the same as in practice." Console: `tyre_wear_multiplier=1.00`.
- Set to 1.5x. Re-activate. Re-run. Prompt: "1.5× faster." Console: `tyre_wear_multiplier=1.50`.

---

**ID:** AWR-017
**Title:** Practice Analysis validation gate blocks AI call on bad data (DEF-P2-016)
**Status:** Awaiting runtime verification
**Test run:** 98/103 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-016 adds a validation gate before the AI call. Requires testing with an empty session and with a valid session.
**Expected Behaviour:** With no fuel data and fewer than 2 laps, Practice Analysis shows a warning dialog. With valid data (≥ 2 laps, fuel > 0, correct race config), the AI call proceeds normally.
**Acceptance Criteria:**
- With 0 live laps and a timed race event with duration < 5 min active: clicking Run Analysis shows a warning dialog listing the issues. No AI API call made.
- After loading a valid session with ≥ 2 laps on one compound and fuel data: clicking Run Analysis proceeds to the AI call.

---

**ID:** AWR-018
**Title:** Outlap rows excluded from best/avg summary in Practice Review (DEF-P2-011)
**Status:** Awaiting runtime verification
**Test run:** 117/122 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-011 adds `is_out_lap` to `get_session_laps()`, stores the flag in row UserRole data, and filters it in `_refresh_practice_summary()`. Requires a live outlap to confirm the visual indicator and summary exclusion.
**Expected Behaviour:** After recording an outlap, the lap row shows dark green background and "Practice (OL)" label. Session summary best lap and average exclude the outlap time and fuel.
**Acceptance Criteria:**
- Complete an outlap (first lap after leaving pits). Practice Review shows the row with dark green background and "Practice (OL)" in the session column.
- Session Summary best lap is NOT the outlap time even if it's faster than all other laps.
- Load a session containing an outlap from History. Same visual and exclusion behaviour.

---

**ID:** AWR-019
**Title:** Pit stop indicator and outlap flag persist after History reload (DEF-P2-013)
**Status:** Awaiting runtime verification
**Test run:** 117/122 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** FIX for DEF-P2-013 is complete (Group 2 + Group 3 side effects). Requires runtime confirmation after a pit lap is saved and reloaded.
**Expected Behaviour:** Pit lap rows show amber background and "Yes" in the Pit column after reload. Outlap rows show dark green and "Practice (OL)" after reload.
**Acceptance Criteria:**
- Complete a pit stop lap. Save session. Reload from History. Pit lap row shows amber background and "Yes" in Pit column.
- Complete an outlap. Reload. Outlap row shows dark green and "Practice (OL)".
- `SELECT is_pit_lap, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` reflects correct values.

---

**ID:** AWR-020
**Title:** Tuning Permissions group visible without BoP (DEF-P2-005)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** `_update_tuning_perms_visibility()` now uses `self._evt_tuning.isChecked()` only (removed BoP gate). Requires confirming the group appears correctly in the UI.
**Expected Behaviour:** Check "Tuning allowed" in Event Planner without enabling BoP → Tuning Permissions group is visible and all category checkboxes are shown. Uncheck Tuning → group hides.
**Acceptance Criteria:**
- Check "Tuning allowed" only. The Tuning Permissions group appears listing all categories.
- Uncheck Tuning. Group hides.
- Check both BoP and Tuning. Group remains visible.
- Check Suspension + Brake Balance. Save event. Active event has `allowed_tuning_categories = ["suspension", "brake_balance"]` in `_config["strategy"]`.

---

**ID:** AWR-021
**Title:** BoP status flows from Event Planner to Setup Builder Race Conditions (DEF-P2-004)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** No `_chk_bop` in Setup Builder. Race Conditions group shows `_lbl_rc_bop` / `_lbl_rc_tuning` from event. Requires confirming the flow in the UI.
**Expected Behaviour:** Set event BoP=Yes, Tuning=No → activate it → Setup Builder Race Conditions shows "BoP: Yes" and "Tuning Allowed: Not Allowed". Change event to BoP=No → activate → shows "BoP: No".
**Acceptance Criteria:**
- Setup Builder has no BoP checkbox anywhere.
- Activating BoP=Yes event → Race Conditions "BoP: Yes", all setup fields except tyres disabled, locked banner shown.
- Activating BoP=No event → Race Conditions "BoP: No", all setup fields enabled.

---

**ID:** AWR-022
**Title:** AI output validation flags locked tuning recommendations (DEF-P2-007)
**Status:** Awaiting runtime verification
**Test run:** 156/161 pass, 5 skipped (Qt display), 0 failed — 2026-06-21
**Description:** `validate_ai_setup_response()` added to `ai_planner.py`. Display handlers call it. Requires runtime test with a locked event.
**Expected Behaviour:** With tuning locked, if AI response recommends "increase rear downforce", an amber "Event Restriction Warning" banner appears at the top of the Setup Builder result and/or Practice Analysis result.
**Acceptance Criteria:**
- Set event BoP=On, Tuning=No. Run Setup Analyse. If AI mentions any locked field with an action verb, an amber warning banner appears before the AI response text.
- If AI complies with the tuning constraint (no locked field recommendations), no banner appears.
- Prompt debug log (GT7_AI_DEBUG=1) shows the `## EVENT RULES — TUNING LOCKED` block.

---

**ID:** AWR-029
**Title:** Top speed shows "—" for invalid capture, not ~11 km/h (DEF-P2-015)
**Status:** Awaiting runtime verification
**Test run:** 204/209 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_refresh_gear_ratios()` now only writes `_spin_top_speed` when `ms >= 50`. Requires driving a car with telemetry to confirm the spinbox shows "—" or a realistic value.
**Expected Behaviour:** After a lap with telemetry active, `_spin_top_speed` shows either "—" (no valid capture) or a realistic value ≥ 120 km/h. AI prompt does not contain "11 km/h" or any top speed < 50 km/h.
**Acceptance Criteria:**
- Connect PS5 telemetry. Drive one lap. Check Setup Builder Transmission → Top Speed field. Shows "—" or ≥ 120 km/h.
- Run Setup Analyse or Practice Analysis. Prompt does NOT contain "11 km/h".

---

**ID:** AWR-030
**Title:** Driver feedback form appears in Practice Review, not Setup Builder (DEF-P2-010)
**Status:** Awaiting runtime verification
**Test run:** 204/209 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Form relocated from Setup Builder to Practice Review. `_on_driver_feedback_submit()` now writes `session_id` from `_session_id`. Requires runtime confirmation of placement and DB write.
**Expected Behaviour:** Practice Review tab shows "Driver Feedback — After Stint" group below the Practice AI Analysis group. Setup Builder does not show this form. Submitting feedback writes a DB row linked to the active session.
**Acceptance Criteria:**
- Open Practice Review tab. "Driver Feedback — After Stint" group is visible with all combo selectors.
- Open Setup Builder tab. No "Driver Feedback" section present.
- Select a live mode (e.g., Practice). Complete one lap. Open Practice Review. Submit feedback with "Corner Entry: Too much oversteer". `SELECT * FROM driver_feedback ORDER BY id DESC LIMIT 1` shows a row with `session_id > 0`.
- Run AI coaching. Prompt debug log (GT7_AI_DEBUG=1) contains "## Recent Driver Feedback" with the submitted entry.

---

---

**ID:** AWR-031
**Title:** Event load restores all saved variables after Group 7 fix (DEF-P1-009)
**Status:** Awaiting runtime verification
**Test run:** 237/242 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_on_event_selected()` now casts REAL DB values to `int(round(...))` before passing to QSpinBox. The silent exception suppressor is removed.
**Expected Behaviour:** Selecting a saved event in Event Planner restores all fields: Tyre Wear ×, Fuel Mult ×, Available Tyres (checkboxes), Required Tyres (checkboxes), BoP, Tuning, Tuning Categories, Track, Race Type, Laps/Duration, Notes.
**Acceptance Criteria:**
- Save event: Tyre Wear=2, Fuel Mult=3, Available=RM+RH, Required=RH, BoP=On, Tuning=Off.
- Click event in list (do NOT click Set Active yet). Verify all five fields match saved values.
- Click Set Active. Confirm Strategy Builder shows ×2 wear, ×3 fuel.
- Run Practice Analysis. Prompt (GT7_AI_DEBUG=1) must contain `## EVENT RULES — TUNING LOCKED`.

---

**ID:** AWR-032
**Title:** AI Practice Analysis prompt contains BoP/tuning restrictions after Group 7 fix (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 237/242 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_run_practice_analysis()` already builds `tuning_locked` and `allowed_tuning` from `_config["strategy"]`. After Group 7, these values are now correct because the event load works. Needs runtime verification that the AI prompt actually receives the restriction block.
**Expected Behaviour:** Event with BoP=On, Tuning=Off activated → Practice Analysis prompt contains `## EVENT RULES — TUNING LOCKED`. AI response does not recommend suspension, aero, or gearbox changes.

---

**ID:** AWR-033
**Title:** Pit flag persists after History reload (DEF-P2-013 Group 8 fix)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `main.py` now passes `is_pit_lap` and `is_out_lap` from `LapRecord` to `write_lap()`. Previously these defaulted to 0. New sessions will correctly record these flags in the DB.
**Expected Behaviour:** Complete a pit stop lap. Reload from History. The pit lap row shows amber background and "Yes" in the Pit column. Non-pit laps show blank.
**Acceptance Criteria:**
- Complete a pit stop lap. Save session. Reload from History.
- Pit lap row shows amber background (#4A4000) and "Yes" in Pit column.
- `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` — at least one row shows is_pit_lap = 1.

---

**ID:** AWR-034
**Title:** Fuel Burn Auto updates on History reload (DEF-P2-009 Group 8 fix)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `_on_history_load_session()` and `_import_bank_session()` now update `_lbl_fuel_burn_display` after setting `_loaded_session_avg_fuel`. Previously the label was only set at startup and never refreshed.
**Expected Behaviour:** Load a historical session. Strategy Builder Fuel Burn label immediately updates to the loaded session average. The value excludes pit laps and out-laps.
**Acceptance Criteria:**
- Load a session with known average fuel (e.g., ~3.5 L/lap). Strategy Builder Fuel Burn label shows approximately 3.50 L/lap immediately after load.
- Label text ends with "(loaded session)".

---

**ID:** AWR-035
**Title:** Fuel start/end and session_type correctly written to DB for new sessions (DEF-P2-014 / DEF-P2-013 support)
**Status:** Awaiting runtime verification
**Test run:** 274/279 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `main.py` now also passes `delta_ms` and `session_type` to `write_lap()`. These previously defaulted to 0/"". Fuel start/end have been passed since Group 2. This AWR confirms all fields are now correctly written in new sessions.
**Expected Behaviour:** After driving laps, `SELECT lap_num, session_type, fuel_start, fuel_end, is_pit_lap, is_out_lap FROM lap_records ORDER BY id DESC LIMIT 5` shows non-empty session_type, non-zero fuel_start/end, and correct pit/out flags.
**Acceptance Criteria:**
- Drive 3 laps in Practice mode.
- `SELECT session_type, fuel_start, fuel_end, is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 3` — session_type = 'practice', fuel_start > 0, fuel_end > 0.
**Acceptance Criteria:**
- Activate a BoP=On, Tuning=Off event. Run Practice Analysis with tagged laps.
- Console (GT7_AI_DEBUG=1) shows `## EVENT RULES — TUNING LOCKED` in prompt.
- AI response makes no suspension/aero/transmission change recommendations.
- Activate a BoP=Off, Tuning=On, Allowed=Suspension+Brake event. Prompt shows `## EVENT TUNING RESTRICTIONS` with locked category list.

---

**ID:** AWR-036
**Title:** AI Log tab shows dry-run entry after GT7_AI_DEBUG call (DEF-P1-010 Group 9 fix)
**Status:** Awaiting runtime verification
**Test run:** 292/297 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** `call_api()` now fires `_fire_log_hook()` with a `success=False` dry-run entry before raising `RuntimeError` in the `_AI_DEBUG` branch. AI Log tab must show intercepted calls.
**Expected Behaviour:** After any AI call made with `GT7_AI_DEBUG=1` set: AI Log tab shows an entry with feature name, model, `success=✗`, and the full prompt accessible in the Prompt sub-tab. DB records the entry with `success=0`.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1; python main.py` (PowerShell).
- Run Practice Analysis with at least two tagged laps.
- Console shows the full prompt text surrounded by `=` separators.
- Switch to AI Log tab. At least one entry visible with `✗` status indicator.
- Click the entry. Prompt sub-tab shows the full prompt text.
- `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.
- Without `GT7_AI_DEBUG`, real API call appears in AI Log with `✓` status and token count.

---

**ID:** AWR-037
**Title:** BoP On + Tuning Off → prompt contains "## EVENT RULES — TUNING LOCKED" (DEF-P1-005/DEF-P2-007)
**Status:** FAILED (2026-06-22) — Prompt still passes full tuning block with BoP=On, Tuning=Off active; "## EVENT RULES — TUNING LOCKED" not present; prompt not contain correct BoP/tuning context; AI response recommends locked setup changes; DEF-P1-005 reopened
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 tests prove `_build_practice_prompt()` inserts the tuning locked constraint block when `tuning_locked=True`. `RaceParams` correctly derives this from `not bool(_psc.get("tuning"))` in `_run_practice_analysis()`. Requires a live run to confirm the end-to-end path.
**Expected Behaviour:** With BoP=On, Tuning=Off active: Practice Analysis prompt contains `## EVENT RULES — TUNING LOCKED` and no editable setup field values. AI response contains no suspension/aero/differential change recommendations.
**Acceptance Criteria:**
- Set Event: BoP=On, Tuning=No. Set Active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Prompt contains `## EVENT RULES — TUNING LOCKED`.
- Setup section shows "[TUNING LOCKED — setup changes not permitted for this Event]" not numeric values.
- AI response section contains no ride height, spring rate, or aero recommendation.

---

**ID:** AWR-038
**Title:** Partial tuning allowed → locked setup fields replaced with ? in prompt (DEF-P1-005)
**Status:** Awaiting runtime verification
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 tests prove `_build_practice_prompt()` filters the setup dict to only pass allowed category keys to `format_setup_for_prompt()`. Locked keys show as `?` in the prompt. Requires a live run with partial tuning permissions.
**Expected Behaviour:** With BoP=On, Tuning=Yes, Allowed=[brake_balance]: prompt contains `## EVENT TUNING RESTRICTIONS`, brake_bias value appears, ride height shows as `?/?`.
**Acceptance Criteria:**
- Set Event: BoP=On, Tuning=Yes, Allowed=[Brake Balance]. Set Active. Run Practice Analysis with `GT7_AI_DEBUG=1`.
- Prompt contains `## EVENT TUNING RESTRICTIONS`.
- Prompt shows `Brake bias: <actual value>` — not `?`.
- Prompt shows `Ride Height F/R: ?/? mm` — not actual ride height value.

---

**ID:** AWR-039
**Title:** Practice Analysis blocks AI call on insufficient input data (DEF-P2-016)
**Status:** Awaiting runtime verification
**Test run:** 305/310 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 10 source-scan tests prove the validation gate checks `total_laps < 2`, `fuel_burn_per_lap <= 0`, `duration_mins < 5`, and `>= 2 laps per compound` — and that the `return` statement precedes `def _worker()`. Requires a live test with bad input to confirm the warning dialog fires before any API call.
**Expected Behaviour:** With 0 or 1 tagged laps, or with fuel_burn_per_lap = 0: clicking Run Practice Analysis shows a warning dialog listing the validation failures. No API call is made. No entry appears in AI Log.
**Acceptance Criteria:**
- Clear Practice Review (0 laps). Click Run Analysis. Warning dialog appears listing validation failure. No AI Log entry added.
- Set a Timed Race event with duration < 5 minutes active. Click Run Analysis. Warning dialog appears.
- Load a valid session (≥ 2 laps, fuel data present). Click Run Analysis. AI call proceeds normally.

---

**ID:** AWR-040
**Title:** Fuel Burn Auto resets to uncalibrated after Set Active with no live/loaded data (DEF-P1-011)
**Status:** PARTIAL PASS (2026-06-22) — PASSED: uncalibrated display after Set Active with no data; live telemetry path; loaded session average (fuel burn label). FAILED: Practice Review rows missing pit flag and fuel_start/fuel_end after History load — DEF-P2-013 and DEF-P2-014 reopened; root cause is data mapping divergence (DEF-P2-022)
**Test run:** 317/322 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 11 source-scan tests confirm `_on_event_set_active()` resets `_lbl_fuel_burn_display` when `avg_fuel_per_lap <= 0 AND _loaded_session_avg_fuel <= 0`. Requires live test with no telemetry and no loaded session.
**Expected Behaviour:** After clicking Set Active on any event with no live telemetry and no historical session loaded, Strategy Builder shows "— (complete practice laps to calibrate)" for Fuel Burn Auto.
**Acceptance Criteria:**
- Ensure no GT7 connection. Do not load a session.
- Create an event with Fuel Multiplier = 3×. Click Set Active.
- Navigate to Strategy Builder. Fuel Burn Auto shows "— (complete practice laps to calibrate)", not "3.00 L/lap (last session)".
- Load a session from History. Fuel Burn Auto updates to "X.XX L/lap (loaded session)".

---

**ID:** AWR-041
**Title:** AI Log list auto-selects new entry from live AI call (DEF-P2-021)
**Status:** FAILED (2026-06-22) — PASSED: entry visible; feature=Practice Analysis; Prompt sub-tab shows prompt. FAILED: entry NOT auto-selected on tab navigation; timestamp shows only HH:MM:SS, not date+time; status text does not distinguish dry-run from failure; DEF-P2-021 reopened with expanded scope
**Test run:** 317/322 pass, 5 skipped (Qt display), 0 failed — 2026-06-22
**Description:** Group 11 source-scan tests confirm `_on_ai_log_entry()` passes `auto_select=True` so new live entries are auto-selected in the AI Log list via `setCurrentRow()`. Requires GT7_AI_DEBUG=1 run.
**Expected Behaviour:** After Practice Analysis with GT7_AI_DEBUG=1, navigating to AI Log tab shows the dry-run entry highlighted (selected) without requiring manual scroll.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Load ≥ 2 laps (valid fuel data). Run Practice Analysis.
- Switch to AI Log tab. Most recent entry is auto-selected (highlighted).
- Detail pane shows feature="Practice Analysis", success=✗, timestamp from this run.

---

**ID:** AWR-042
**Title:** BoP=On + Tuning=Off → runtime prompt contains TUNING LOCKED (DEF-P1-005)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12a confirms `_run_practice_analysis()` uses `get("tuning", False)` so absent or False "tuning" key → tuning_locked=True. Requires runtime test with a real event configured BoP=On, Tuning=Off.
**Acceptance Criteria:**
- Set Event with BoP=On, Tuning=No. Set it active. Run with `$env:GT7_AI_DEBUG=1`.
- Console output shows `tuning=False tuning_locked=True`.
- AI prompt (Prompt sub-tab) contains "TUNING LOCKED" or "## EVENT RULES — TUNING LOCKED".
- No ride height, spring rate, aero, or gear ratio recommendations in AI response.

---

**ID:** AWR-043
**Title:** History load shows pit flag and fuel_start/end for post-Group-8 sessions (DEF-P2-013/014)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12b investigation confirmed code is correct. AWR-043 must use a session recorded AFTER Group 8 was applied (not legacy data). Pit laps and fuel_start/fuel_end should appear correctly.
**Acceptance Criteria:**
- Record a new Practice session with ≥ 1 pit stop after Group 8 fix is applied.
- Go to History tab. Select the new session. Load to Practice Review.
- Pit stop lap row shows "Yes" in Pit column (amber background).
- Fuel Start and Fuel End columns show non-zero numeric values.
- `SELECT fuel_start, fuel_end, is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` confirms non-zero values.

---

**ID:** AWR-044
**Title:** AI Log entry auto-selected with full date+time and "⊘ DRY-RUN" status (DEF-P2-021)
**Status:** Pending runtime
**Test run:** 363/368 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 12)
**Description:** Group 12c implemented three fixes: timestamp format, status labels, and pending-select flush on tab activation. Requires GT7_AI_DEBUG=1 run.
**Acceptance Criteria:**
- Launch with `$env:GT7_AI_DEBUG=1`. Load ≥ 2 laps with valid fuel data. Run Practice Analysis.
- Navigate to AI Log tab. Most recent entry is auto-selected (highlighted), no manual scroll needed.
- Entry text shows: `[YYYY-MM-DD HH:MM:SS] Practice Analysis — ⊘ DRY-RUN — 0ms`.
- Prompt sub-tab shows the intercepted prompt (Developer Mode enabled).

---

**ID:** AWR-045
**Title:** No-refuel pit stop detected with `is_pit_lap = 1` (DEF-P2-023)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** Speed-based pit detection added. Requires a real Practice session with a no-refuel stop to confirm the 3-second stationary timer fires correctly.
**Acceptance Criteria:**
- Practice session with at least one pit stop where no fuel is taken.
- After the pit stop lap completes, `SELECT is_pit_lap FROM lap_records ORDER BY id DESC LIMIT 5` shows `is_pit_lap = 1` for that lap.
- Practice Review shows amber background on the pit stop lap row.
- Outlap following the no-fuel stop shows `is_out_lap = 1`.

---

**ID:** AWR-046
**Title:** Outlap persists after Save Session + History reload (DEF-P2-024)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_save_session_to_db()` now passes `is_out_lap` to `write_lap()`. Requires confirming the full save→clear→reload round-trip.
**Acceptance Criteria:**
- Run Practice session with outlap. Save Session button → Clear session → go to History tab → load session into Practice Review.
- Outlap row shows dark green background and "Practice (OL)" label (not plain "Practice").
- `SELECT is_out_lap FROM lap_records ORDER BY id DESC LIMIT 10` — outlap row has `is_out_lap = 1`.

---

**ID:** AWR-047
**Title:** Fuel Start/End columns populated after Save Session + History reload (DEF-P2-025)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_save_session_to_db()` now passes `fuel_start`/`fuel_end` to `write_lap()`. Requires confirming round-trip.
**Acceptance Criteria:**
- Run Practice session (≥ 3 laps). Note Fuel Start and Fuel End values in Practice Review. Save Session → Clear → History load.
- Practice Review Fuel Start and Fuel End columns show the same non-zero values as the live session.
- `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 5` — non-zero values.

---

**ID:** AWR-048
**Title:** Compound change propagates to all laps until next pit stop (DEF-P2-019/026)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_on_compound_selected()` now stops propagation at `is_pit_lap` boundary instead of at any different compound. Requires a session with ≥ 10 laps to verify forward fill.
**Acceptance Criteria:**
- Practice session with 10+ laps. Change lap 4 compound to Racing Soft.
- Laps 5 through the session end all update to Racing Soft automatically.
- Laps 1–3 are unchanged.
- If a pit lap exists at lap 7, propagation stops at lap 7 (lap 8+ unchanged).

---

**ID:** AWR-049
**Title:** Live tab "Current Tyre" shows race plan stint compound (DEF-P2-020/027)
**Status:** Pending runtime
**Test run:** 389/394 pass, 5 skipped (Qt display), 0 failed — 2026-06-22 (Group 13)
**Description:** `_get_current_tyre_compound()` implements three-priority hierarchy. Requires runtime verification of all three fallback levels.
**Acceptance Criteria:**
- Load a race plan (2 stints: S1=Racing Medium, S2=Racing Soft). Live tab shows "Current Tyre: Racing Medium". After pit stop, shows "Current Tyre: Racing Soft".
- Clear the race plan. Setup Builder front tyre = Racing Hard. Live tab shows "Current Tyre: Racing Hard".
- Set Setup Builder front tyre to blank/none. Live tab shows "Current Tyre: Not Set".
- Required tyres from Event never appear in the "Current Tyre:" label.

---

## Remediation Plan — 2026-06-21 Testing Session

> Priority order: Fix crashes first, then AI prompt accuracy, then data loss, then UI cosmetics.
> Do not implement fixes without updating this file and running `pytest` after each group.

---

### Group 8 — Session Reload Mapping (COMPLETED 2026-06-22)

**Defects:** DEF-P2-013, DEF-P2-014, DEF-P2-009
**Test result:** 274 passed / 279 collected / 5 skipped (Qt display) / 0 failed

**Root cause (DEF-P2-013 and DEF-P2-009):** `main.py` EventDispatcher called `write_lap()` without forwarding `is_pit_lap`, `is_out_lap`, `delta_ms`, or `session_type` from the `LapRecord`. All four parameters defaulted to 0/False/"". The DB therefore always stored `is_pit_lap = 0` and `is_out_lap = 0`. The live display read directly from the `LapRecord` object in memory (showing correct values); the reload path read from the DB (always 0 → pit flag missing, outlaps included in fuel average).

**Root cause (DEF-P2-009):** After `_on_history_load_session()` set `_loaded_session_avg_fuel`, the `_lbl_fuel_burn_display` widget in Strategy Builder was never refreshed. It was only populated at widget creation time (app startup) and never again.

**Fix 1 — `main.py` write_lap() extended (DEF-P2-013, DEF-P2-014 support, DEF-P2-009 support):**
Added `is_pit_lap=bool(getattr(record, "is_pit_lap", False))`, `is_out_lap=bool(getattr(record, "is_out_lap", False))`, `delta_ms=int(getattr(record, "delta_ms", 0))`, `session_type=(record.session_type.value if hasattr(record.session_type, "value") else str(...))` to the `write_lap()` call in `EventDispatcher._dispatch()`.

**Fix 2 — `ui/dashboard.py` fuel burn display refreshed (DEF-P2-009):**
Both `_on_history_load_session()` and `_import_bank_session()` now update `_lbl_fuel_burn_display` immediately after setting `_loaded_session_avg_fuel`: `self._lbl_fuel_burn_display.setText(f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")`.

**AWR-033:** Pit flag and out-lap flag persist in DB for new sessions → reload shows pit flag with amber background.
**AWR-034:** Fuel Burn Auto label updates to loaded session average immediately on History reload.
**AWR-035:** session_type, fuel_start, fuel_end, delta_ms all correctly written to DB for new sessions.

---

### Group 10 — AI Prompt BoP Context (COMPLETED 2026-06-22)

**Defects:** DEF-P1-005, DEF-P2-007, DEF-P2-016
**Test result:** 305 passed / 310 collected / 5 skipped (Qt display) / 0 failed
**Scope:** Test coverage only. No production code was changed.

**Investigation conclusion:** All three defects were correctly implemented in Groups 2–4. The root cause of UAT failures was Root Cause A (event persistence broken — Group 7), not missing production code. After Group 7, BoP/tuning values correctly reach `_config["strategy"]` and propagate to `_build_practice_prompt()` via `RaceParams`.

**Tests added — `tests/test_group10_ai_prompt_bop.py`** (13 tests in 3 classes):

- `TestPracticePromptSetupFiltering` (5 tests): Directly calls `_build_practice_prompt()` with known setup dict values and `RaceParams` combinations. Confirms: (1) `tuning_locked=True` replaces setup block with TUNING LOCKED text and adds `## EVENT RULES — TUNING LOCKED`; (2) `allowed_tuning=["brake_balance"]` includes `brake_bias` value but filters `ride_height_front` to `?`; (3) partial restriction adds `## EVENT TUNING RESTRICTIONS`; (4) no restriction passes all setup field values through.
- `TestPracticeValidationGate` (5 tests): Source-scan of `_run_practice_analysis()`. Confirms: validation gate checks `total_laps < 2`, `fuel_burn_per_lap <= 0`, `duration_mins < 5`, and `>= 2 laps per compound`. Confirms `return` statement precedes `def _worker()` — proving the gate exits before any API call.
- `TestRaceParamsBoPFields` (3 tests): Confirms `RaceParams` dataclass has `tuning_locked: bool = False` and `allowed_tuning` fields. Confirms `_run_practice_analysis()` derives `tuning_locked` as `not bool(_psc.get("tuning"))` and reads `allowed_tuning_categories` from strategy config.

**AWR-037:** BoP On + Tuning Off → live prompt contains `## EVENT RULES — TUNING LOCKED` (end-to-end runtime check)
**AWR-038:** Partial tuning allowed → locked fields show as `?` in live prompt (end-to-end runtime check)
**AWR-039:** Practice Analysis validation dialog fires before AI call when input data is invalid (runtime check)

---

### Group 13 — Live Session Defects: Pit Detection, Save Session, Compound Propagation, Live Tyre (COMPLETED 2026-06-22)

**Defects:** DEF-P2-023, DEF-P2-024, DEF-P2-025, DEF-P2-019/026, DEF-P2-020/027
**Test result:** 389 passed / 394 collected / 5 skipped (Qt display) / 0 failed

**13a — DEF-P2-023: Speed-based pit detection fallback:**
Fuel-only pit detection missed no-refuel stops entirely. Added `_low_speed_start: float = 0.0` to `_reset()`. In `_phase_transitions()`, under `RacePhase.RACING` guard: if `p.speed_kmh < 10`, start timing; if stationary for ≥ 3.0s, call `_enter_pit()`. Timer reset on speed recovery or when `_enter_pit()` fires. `_enter_pit()` also resets `_low_speed_start = 0.0` to prevent double-trigger.

**13b — DEF-P2-024 + DEF-P2-025: Save Session passes all LapRecord fields:**
`_save_session_to_db()` called `write_lap()` with only 6 positional args — omitted `fuel_start`, `fuel_end`, `is_pit_lap`, `is_out_lap`, `delta_ms`, `session_type`. All defaulted to 0/False/"" in DB. The automatic EventDispatcher write (in `main.py`) was already correct; only the manual Save Session button path was broken. Fixed by adding all 6 keyword args with `getattr(lap, ...)` safe reads.

**13c — DEF-P2-019/026: Compound propagation stops at pit lap boundary:**
`_on_compound_selected()` broke propagation at the first row with any different compound string. Since every new lap row is pre-tagged with `_default_lap_compound`, the fill stopped at `start_row + 1`. Removed `if existing and existing != norm: break`. Added check: read `is_pit_lap` from col-0 UserRole data; if true, break. Fill now continues through all laps of the current stint.

**13d — DEF-P2-020/027: Live tyre label shows actual compound via priority hierarchy:**
Label previously read `mandatory_compounds` (race rules, not fitted compound). Replaced with:
- `_get_current_tyre_compound()`: Priority 1 = active race plan first-incomplete-stint `.compound`; Priority 2 = `_setup_tyre_f.currentText()`; Priority 3 = "Not Set".
- `_refresh_live_tyre_label()`: updates label with `"Current Tyre: {compound}"`.
- Wired to: `_on_tyre_preset_changed()` (stint change), `_on_live_mode_changed()`, `_sync_setup_builder_from_event()`, `_setup_tyre_f.currentTextChanged`.
- Label initial text changed to "Current Tyre: Not Set".
- Group 5 tests updated to assert new "Current Tyre:" prefix and `_refresh_live_tyre_label()` call pattern.

**Tests added — `tests/test_group13_live_session_defects.py`** (26 tests in 4 classes):
- `TestSpeedBasedPitDetection` (6): `_low_speed_start` initialized; speed < 10 threshold; 3.0s timeout; RACING phase guard; reset in `_enter_pit`.
- `TestSaveSessionPassesAllFields` (7): `fuel_start=`, `fuel_end=`, `is_pit_lap=`, `is_out_lap=`, `delta_ms=`, `session_type=`, `getattr(lap,` in `_save_session_to_db`.
- `TestCompoundPropagationStopsAtPitLap` (3): stops at `is_pit_lap`; reads UserRole; no `existing != norm` break.
- `TestLiveTyreLabelPriorityHierarchy` (10): `_get_current_tyre_compound` exists; P1 reads strategy_engine; P1 checks completed; P2 reads `_setup_tyre_f`; P3 returns "Not Set"; `_refresh_live_tyre_label` exists and calls helper; "Current Tyre:" prefix; `_on_tyre_preset_changed` calls refresh; `mandatory_compounds` not in helper.

**AWR-045:** No-refuel pit stop → `is_pit_lap=1`, `is_out_lap=1` in DB (DEF-P2-023)
**AWR-046:** Save Session + History reload → outlap shows dark green "Practice (OL)" label (DEF-P2-024)
**AWR-047:** Save Session + History reload → Fuel Start/End columns non-zero (DEF-P2-025)
**AWR-048:** Compound change on lap 4 → laps 5–end all update; stops at pit lap if present (DEF-P2-019/026)
**AWR-049:** Race plan loaded → "Current Tyre: Racing Medium"; after pit → "Current Tyre: Racing Soft"; no plan → setup tyre; nothing → "Not Set" (DEF-P2-020/027)

---

### Group 14 — UAT No-Go Remediation (COMPLETED 2026-06-22)

**Defects:** DEF-P1-012, DEF-P2-029, DEF-P2-030, DEF-P2-031, DEF-P2-032, DEF-P2-033, DEF-P2-034, DEF-P2-035
**Test result:** 426 passed / 431 collected / 5 skipped (Qt display) / 0 failed

**14a — DEF-P1-012: Practice prompt instructs AI to provide setup changes even when tuning is locked:**
`_build_practice_prompt()` in `strategy/ai_planner.py` line 685 had a fixed `## Instructions` line always asking for "3–5 Setup changes". The `constraint_block` said DO NOT recommend setup changes, but the explicit instruction overrode it. Fix: the `setup_changes` instruction is now a Python conditional — `"3–5 changes…"` when `not params.tuning_locked`; `"No setup changes…Tuning is locked…do NOT recommend any setup changes"` when `tuning_locked=True`.

**14b — DEF-P2-029: Outlap silently skipped when write_lap receives stats=None:**
`write_lap()` had `if stats is None: return 0` before entering the DB write block, silently dropping outlap metadata rows. Removed the guard. All stat field accesses made None-safe (`stats.field if stats else 0`). `positions_blob` JSON uses list comprehension with `if stats else []`. Metadata-only rows (zeros for telemetry) are now written and return a valid lap_record id.

**14c — DEF-P2-030: Save Session button creates a duplicate session:**
`_save_session_to_db()` called `open_session()` unconditionally, duplicating the session already opened by `_on_live_mode_changed()`. Fix: reads `self._dispatcher._session_id`; if > 0, skips `open_session()` and only calls `update_lap_compound()` + `update_lap_setup_id()` per lap. The fallback (no live session) retains the full `open_session()` path for manual saves.

**14d — DEF-P2-031: Qualifying outlap calming phrase never fires:**
`_exit_pit()` in `telemetry/state.py` emitted `PIT_EXIT` with `session_type=self._session_type.value` (packet-detected — often `unknown` in custom races). `voice/announcer.py` checks `event.data.get("session_type") == "qualifying"`. Fix: `_exit_pit()` now uses `_session_type_override.value` when set, falling back to `_session_type` otherwise — same pattern already used for `LapRecord.session_type`.

**14e — DEF-P2-032: Qualifying suppression for pit/fuel alerts (already fixed in Group 5):**
Investigation confirmed both `_on_pit()` and `_on_fuel_low()` in `announcer.py` already check `in ("practice", "qualifying")`. No production code change needed. Regression guard added to test file.

**14f — DEF-P2-033: AI Log auto-select fires on hidden widget:**
`_on_ai_log_entry()` called `_add_ai_log_list_item(auto_select=True)` which triggered `setCurrentRow()` even when the AI Log tab was not visible — the call had no effect. Fix: removed `auto_select=True`; added `QTimer.singleShot(0, self._flush_ai_log_pending_select)` instead. `_flush_ai_log_pending_select()` now checks `self._tabs.currentIndex() != 11` and returns early (leaving `_ai_log_pending_select = True`) if the tab is not active. `_on_tab_changed(11)` re-calls the flush when the user navigates there.

**14g — DEF-P2-034: AI Log timestamps stored in UTC, displayed as local time:**
All 3 occurrences of `_dt.datetime.utcnow().isoformat()` in `strategy/_ai_client.py` changed to `_dt.datetime.now().isoformat()`. This applies to the debug dry-run path, the success path, and the except/error path.

**14h — DEF-P2-035: Garage tab shows no DB setups; exceptions silently swallowed:**
`_on_garage_car_selected()` had bare `except Exception: pass` around both the sessions query and the setup query. Replaced with `traceback.print_exc()`. Added a DB setups block: looks up `car_id` from recent sessions for the displayed car name, calls `get_setups_for_car(car_id)`, and populates `_garage_setups_table` rows from the results.

**Tests added — `tests/test_group14_uat_remediation.py`** (37 tests in 7 classes):
- `TestBoPPromptSetupChangesConditional` (4): setup_changes instruction references tuning_locked; locked branch present; 3–5 changes in unlocked branch; DO NOT directive in locked branch.
- `TestBoPPromptRoundTrip` (4): Live calls to `_build_practice_prompt()`. Locked prompt contains TUNING LOCKED; no ride_height value; no "3–5 changes". Unlocked prompt has "3–5 changes".
- `TestWriteLapNoneStats` (5): write_lap returns nonzero id; preserves is_out_lap; preserves fuel_start/end; zeros telemetry; increments total_laps.
- `TestSaveSessionNoduplication` (4): reads `_dispatcher._session_id`; calls `update_lap_compound`; returns early before `open_session`; existing_sid guard precedes open_session.
- `TestPitExitSessionTypeOverride` (4): `_exit_pit` uses override; fallback to detected; checks `is not None`; logic correctness.
- `TestQualifyingAlertSuppression` (3): regression guards for `_on_pit`, `_on_fuel_low`, `_on_race_finish`.
- `TestAiLogAutoSelectQTimer` (5): QTimer used; pending_select flag set; flush checks currentIndex; flag left set when tab not visible; no auto_select=True.
- `TestAiLogLocalTimestamp` (3): no utcnow(); datetime.now() present; replace("T"," ") display format retained.
- `TestGarageDbIntegration` (5): get_all_sessions called; get_setups_for_car called; traceback.print_exc used; method exists; zero-lap sessions filtered out.

**AWR-050:** Practice Analysis with BoP+Tuning Off → AI response says "tuning not permitted" and provides no setup changes (DEF-P1-012)
**AWR-051:** Pit outlap recorded in DB with is_out_lap=1 when manual Save Session clicked after clear (DEF-P2-029)
**AWR-052:** Save Session with live session active → no duplicate session in History; compound tags applied to existing session (DEF-P2-030)
**AWR-053:** Qualifying mode → pit exit → outlap calming phrase heard from announcer (DEF-P2-031)
**AWR-054:** Practice mode → fuel low → NO voice alert (DEF-P2-032 regression guard)
**AWR-055:** AI call completes → AI Log tab auto-scrolls to new entry when tab is visible; flag deferred when tab hidden (DEF-P2-033)
**AWR-056:** AI Log entry timestamps match local clock time, not UTC (DEF-P2-034)
**AWR-057:** Garage tab → car with DB-saved setups → setup rows appear in setups table (DEF-P2-035)

**AWR-058:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_run_ai_analysis()` race_params dict includes all 6 new fields (race_type, duration_mins, tuning_locked, allowed_tuning, bop, avail_tyres). `_build_race_prompt()` injects tuning_block, bop_line, avail_line. (DEF-P1-013)
**AWR-059:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_worker()` captures `_hist_db`, `_hist_track`, `_hist_car_name` before thread start; calls `_hist_db.get_car_id(_hist_car_name)` not hardcoded 0. (DEF-P1-014)
**AWR-060:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_run_practice_analysis()` race_params includes `"bop": bool(_psc.get("bop", False))`; `_build_practice_prompt()` injects bop_line. (DEF-P2-038)
**AWR-061:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `avail_tyres` in both race_params dicts, RaceParams dataclass, `build_car_setup()`, `_build_setup_from_scratch_prompt()`, and both prompt builders. (DEF-P2-039)
**AWR-062:** CLOSED (2026-06-23 runtime validation) — Source confirmed: worker queries `get_recent_feedback(car_id, track, limit=5)`, formats rows into `_driver_feedback_str`, passes to `analyse_practice_session()`. Produces output when feedback exists for this car+track. (DEF-P2-040)
**AWR-063:** CLOSED (2026-06-23 Group 15A) — DEF-P3-013 fixed. `AILogEntry` now has `car_id`/`track` fields. All `call_api()` sites, `ai_planner.py` functions, `DrivingAdvisor` methods, and dashboard callers thread real car_id and track to every `ai_interactions` row. `get_recent_ai_recommendations()` now returns results when matching data exists. (DEF-P2-041 / DEF-P3-013)
**AWR-064:** CLOSED (2026-06-23 runtime validation) — Source confirmed: coaching branch reads `_car_name_ql`, `_car_specs_ql = self._car_specs_ref`, `_compound_ql` and passes all three to `build_coaching_response()`. Dashboard calls `update_car_specs()` in `_on_event_set_active()`. (DEF-P2-036)
**AWR-065:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_active_setup_getter` checked first; dashboard wires `set_active_setup_getter(self._current_setup_dict)` at startup. Falls back to config only if getter not set. (DEF-P2-037)
**AWR-066:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `race_len_line` computed conditionally on `params.race_type == "timed"`; prompt uses `{race_len_line}`. Hardcoded "N laps" string removed. (DEF-P3-009)
**AWR-067:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `build_car_setup()` and `_build_setup_from_scratch_prompt()` accept all 5 new params; `_race_ctx_block` constructed and injected; `_run_build_setup()` reads and passes all from `_sc_build`. (DEF-P3-010)
**AWR-068:** CLOSED (2026-06-23 runtime validation) — `_DATA_QUALITY_NOTE` constant confirmed in `ai_planner.py` and injected into both prompts. AWR-063 blocker now resolved via DEF-P3-013 fix (Group 15A). (DEF-P3-011)
**AWR-069:** CLOSED (2026-06-23 runtime validation) — Source confirmed: `_display_strategy_results()` imports `validate_ai_setup_response`, iterates options, checks setup_changes text, prepends orange `F5A623` banner when violations found. (DEF-P3-012)

---

### Group 16 — Phase 2: Per-Lap Telemetry in Practice and Strategy Prompts (COMPLETED 2026-06-23)

**Roadmap:** Phase 2 (2-A / 2-B / 2-C / 2-D from SMART_RACE_ENGINEER_ROADMAP.md)  
**Test result:** 643 passed / 648 collected / 5 skipped (Qt display) / 0 failed  
**New tests:** `tests/test_group16_per_lap_telemetry.py` — 74 tests

**Files changed:**
- `telemetry/recorder.py` — `TelemetryFrame` gains `tyre_temp_fl/fr/rl/rr: float = 0.0`; `LapStats` gains `tyre_temp_fl/fr/rl/rr_avg: float = 0.0`; `_compute_stats()` computes per-corner averages (frames with temp > 0 only, rounded to 1 dp); `record_frame()` feeds tyre temps from packet
- `data/session_db.py` — `lap_records` DDL adds 4 tyre_temp avg columns; `_V3_ALTER_COLUMNS` + `_migrate_v3()` + PRAGMA user_version=3 guard added; `write_lap()` persists tyre temp avgs; `get_session_laps()` gains `exclude_pit`, `exclude_out`, `limit` params + expanded SELECT (telemetry fields); `get_recent_fuel_sequence()` returns chronological per-lap fuel (L/lap) excluding pit/out/zero-fuel laps; `get_compound_lap_sequences()` returns per-compound lap-time sequences with session filter and limit-per-compound cap
- `strategy/ai_planner.py` — `_build_per_lap_telemetry_block()` formats per-lap table (lock_up, spin, oversteer+T, kerb, lat-g, optional tyre temps); `_build_fuel_trend_block()` formats avg/std-dev/95th-pct fuel trend (Phase 2-B); `_build_compound_sequence_block()` formats per-compound sequences with linear-regression deg rate (Phase 2-C); `analyse_practice_session()` + `_build_practice_prompt()` gain `per_lap_telemetry: list | None = None`; `analyse_strategy()` + `_build_race_prompt()` gain `fuel_sequence: list | None = None` and `compound_sequences: dict | None = None`
- `ui/dashboard.py` — `_run_practice_analysis()` captures `_hist_session_id` before thread, queries `get_session_laps()` with exclude_pit/exclude_out/limit=5, passes `per_lap_telemetry` to `analyse_practice_session()`; `_run_ai_analysis()` queries `get_recent_fuel_sequence()` + `get_compound_lap_sequences()` before thread, passes both to `analyse_strategy()`

---

### Group 15A — AILogEntry car_id/track Fix (COMPLETED 2026-06-23)

**Defect:** DEF-P3-013  
**Test result:** 569 passed / 574 collected / 5 skipped (Qt display) / 0 failed  
**New tests:** `tests/test_group15a_ai_log_car_track.py` — 56 tests

**Files changed:**
- `strategy/_ai_client.py` — `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields; `call_api()` gains matching kwargs; all three `AILogEntry` construction sites (debug, success, exception) pass them through
- `strategy/ai_planner.py` — `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` gain `car_id: int = 0`; thread to `call_api()` with `track=params.track` / `track=track`
- `strategy/driving_advisor.py` — all four `call_api()` sites pass `car_id=self._car_id_ref[0], track=self._config.get("strategy", {}).get("track", "")`
- `ui/dashboard.py` — `_run_ai_analysis()` resolves `_car_id_strat` before worker; `_run_practice_analysis()` passes `car_id=_car_id_hist`; `_run_build_setup()` resolves `_car_id_build` before worker; `_on_ai_log_entry_dict()` passes `car_id`/`track` when reconstructing AILogEntry from DB rows

**AWR-063:** CLOSED — previous AI recommendations in Practice Analysis will now be found when a prior run for the same car+track exists in `ai_interactions`.

---

### Group 12 — BoP/Tuning Runtime Fix + History Mapping Investigation + AI Log Display (COMPLETED 2026-06-22)

**Defects:** DEF-P1-005 (12a), DEF-P2-013/014/022 (12b), DEF-P2-021 (12c)
**Test result:** 363 passed / 368 collected / 5 skipped (Qt display) / 0 failed

**12a — DEF-P1-005 root cause confirmed and fixed:**
Bug: `_psc.get("tuning", True)` in `_run_practice_analysis()` (line 3183). With default `True`, absent "tuning" key → `not bool(True)` = `tuning_locked=False` — practice analysis sends full setup even when event was configured with Tuning=Off. Old configs (pre-Group-7) or configs where `_on_event_set_active()` silently failed (due to `except Exception: pass`) lacked the "tuning" key entirely.
- Fix 1: `_psc.get("tuning", False)` → absent key = locked (safe default).
- Fix 2: `except Exception: pass` → `import traceback; traceback.print_exc()` in `_on_event_set_active()` so future failures are visible.
- Fix 3: `GT7_AI_DEBUG` context print block added after `race_params` dict built — shows bop, tuning, tuning_locked, allowed_tuning, race_type, fuel_mult, tyre_wear to stdout.

**12b — DEF-P2-022/013/014 investigation: code correct, hypothesis incorrect:**
Both load paths (`_on_history_load_session()` and `_import_bank_session()`) use same `get_session_laps()` SELECT returning all required columns. Both pass all fields to `_add_bank_lap_row()`. `write_lap()` in `main.py` correctly passes `fuel_start`, `fuel_end`, `is_pit_lap` from `LapRecord`. Zero values in AWR-040 retest were pre-Group-8 session data with DEFAULT 0. DEF-P2-022 closed. DEF-P2-013/014 status updated. No production code change required.

**12c — DEF-P2-021 three remaining issues fixed:**
- Timestamp: `entry.timestamp[:19].replace("T", " ")` → YYYY-MM-DD HH:MM:SS (shows date, not just HH:MM:SS).
- Status: "✓ OK" / "✗ FAIL" / "⊘ DRY-RUN" (dry-run when duration_ms==0 and "AI_DEBUG" in error_msg).
- Auto-select: `_ai_log_pending_select = True` set in `_on_ai_log_entry()`; `_flush_ai_log_pending_select()` new helper; `_on_tab_changed()` calls flush for index 11 (AI Log tab). `setCurrentRow(count-1)` re-applied when tab becomes visible.

**Tests added — `tests/test_group12a_bop_tuning_propagation.py`** (12 tests in 4 classes):
- `TestTuningLockedDefault` (4): Confirms get("tuning", False) not True; key in race_params; allowed_tuning in race_params.
- `TestOnEventSetActiveExceptionLogging` (2): No bare except:pass; traceback present.
- `TestStratIsReference` (3): setdefault used; strat["tuning"] written; strat["bop"] written.
- `TestDebugContextPrint` (3): GT7_AI_DEBUG gate; tuning_locked in debug; bop in debug.

**Tests added — `tests/test_group12b_history_practice_mapping.py`** (20 tests in 5 classes):
- `TestGetSessionLapsSelect` (4): fuel_start/end, is_pit_lap, is_out_lap in SELECT.
- `TestHistoryLoadSessionMapping` (4): _on_history_load_session passes all 4 fields.
- `TestImportBankSessionMapping` (4): _import_bank_session passes all 4 fields.
- `TestAddBankLapRowDisplay` (4): _add_bank_lap_row uses is_out_lap, is_pit_lap, fuel_start, fuel_end.
- `TestWriteLapStoresAllFields` (4): write_lap INSERT includes all 4 fields.

**Tests added — `tests/test_group12c_ai_log_display.py`** (12 tests in 3 classes):
- `TestAiLogTimestampFormat` (3): [:19] replace T; not [11:19].
- `TestAiLogStatusText` (5): OK/FAIL/DRY-RUN labels; AI_DEBUG detection; duration_ms==0.
- `TestAiLogPendingSelect` (6): pending flag set; flush method exists; flush reads flag; flush calls setCurrentRow; tab_changed handles index 11; flush clears flag.

**AWR-042:** BoP=On, Tuning=Off → runtime prompt contains TUNING LOCKED; `GT7_AI_DEBUG=1` stdout shows `tuning=False tuning_locked=True` (DEF-P1-005)
**AWR-043:** Load session (recorded AFTER Group 8 fix) from History into Practice Review → pit flag "Yes" in pit column; fuel_start/fuel_end show numeric values (DEF-P2-013/014)
**AWR-044:** After Practice Analysis with GT7_AI_DEBUG=1, navigate to AI Log tab → new entry auto-selected; timestamp shows YYYY-MM-DD HH:MM:SS; status shows "⊘ DRY-RUN" (DEF-P2-021)

---

### Group 11 — UI Display Fixes (COMPLETED 2026-06-22)

**Defects:** DEF-P1-011, DEF-P2-021
**Test result:** 313 passed / 318 collected / 5 skipped (Qt display) / 0 failed

**Root cause (DEF-P1-011):** `_on_event_set_active()` calls `_sync_setup_builder_from_event()` which only updates `_lbl_fuel_burn_display` when `tracker.avg_fuel_per_lap > 0`. When no live telemetry is present, the label retains the initialisation value from `config["strategy"]["fuel_burn_per_lap"]` (e.g. `3.0` from a prior session). This stale value was displayed as "3.00 L/lap (last session)". In the smoke test the number coincidentally equalled the event fuel multiplier (both 3×), causing confusion.

**Fix (DEF-P1-011) — `ui/dashboard.py` `_on_event_set_active()`:**
Added reset block after `_sync_setup_builder_from_event()` call. When `tracker.avg_fuel_per_lap <= 0 AND _loaded_session_avg_fuel <= 0`, resets `_lbl_fuel_burn_display` to `"— (complete practice laps to calibrate)"`. Live telemetry and loaded-session paths are unchanged.

**Root cause (DEF-P2-021):** `_add_ai_log_list_item()` appended the new item and called `scrollToBottom()`. However `bridge.ai_log_entry` uses `QueuedConnection` (cross-thread delivery) so the slot fires after the current timer tick. If the AI Log tab is not visible at that moment, `scrollToBottom()` has no visual effect. When the user navigated to the tab they saw the DB-loaded startup history at the top and missed the new entry at the bottom. The user clicked an old entry and saw the Prompt sub-tab (from that historical entry) — this explained "Prompt tab populated. Prompt text visible."

**Fix (DEF-P2-021) — `ui/dashboard.py` `_add_ai_log_list_item()` and `_on_ai_log_entry()`:**
Added `auto_select: bool = False` parameter to `_add_ai_log_list_item()`. When `True`, calls `setCurrentRow(count - 1)` after `addItem()`, selecting and highlighting the new entry. `_on_ai_log_entry()` (live signal) passes `auto_select=True`. `_on_ai_log_entry_dict()` (DB startup load) keeps `auto_select=False` to avoid disrupting history load order.

**Tests added — `tests/test_group11_ui_display_fixes.py`** (12 tests in 3 classes):
- `TestFuelBurnLabelResetOnEventSwitch` (4 tests): Source-scan of `_on_event_set_active()`. Confirms: checks `avg_fuel_per_lap`, checks `_loaded_session_avg_fuel`, resets `_lbl_fuel_burn_display` to uncalibrated text, reset is conditional on `<= 0`.
- `TestAiLogAutoSelect` (4 tests): Source-scan of `_add_ai_log_list_item()` and related methods. Confirms: `auto_select` parameter present, `setCurrentRow` called when flag is set, `_on_ai_log_entry` passes `auto_select=True`, `_on_ai_log_entry_dict` does NOT pass `auto_select=True`.
- `TestFuelBurnLiveTelemetryUpdate` (4 tests): Source-scan of `_refresh_telemetry_context()`. Confirms: reads `avg_fuel_per_lap` from tracker, updates `_lbl_fuel_burn_display`, uses "from telemetry" label suffix to distinguish from loaded-session values, guards update with `avg > 0` check. (Note: History-load path covered in Group 8 — `TestHistoryLoadSessionMapping.test_updates_fuel_burn_display_after_load` and `TestImportBankSessionMapping.test_updates_fuel_burn_display_after_load`.)

**AWR-040:** Fuel Burn Auto resets to uncalibrated after Set Active with no live/loaded data (DEF-P1-011)
**AWR-041:** AI Log list auto-selects new live entry after Practice Analysis (DEF-P2-021)

---

### Group 9 — AI Debug / Log Visibility (COMPLETED 2026-06-22)

**Defects:** DEF-P1-010
**Test result:** 292 passed / 297 collected / 5 skipped (Qt display) / 0 failed

**Root cause:** `call_api()` in `strategy/_ai_client.py` raised `RuntimeError` in the `_AI_DEBUG` branch before reaching the `try/except` block that contains both `_fire_log_hook()` calls. When `GT7_AI_DEBUG=1` was set:
- Prompt was printed to stdout (visible in Debug tab terminal output)
- `RuntimeError` was raised immediately
- `_fire_log_hook()` was never called
- `db.log_ai_interaction()` was never called
- `bridge.ai_log_entry` signal was never emitted
- AI Log tab received no entry

The same issue existed for the missing API key path (`ValueError` before hook), but the primary test scenario used `GT7_AI_DEBUG=1`.

**Fix — `strategy/_ai_client.py`:**
Added `_fire_log_hook(AILogEntry(...))` immediately before `raise RuntimeError` in the `_AI_DEBUG` block. Dry-run entries use:
- `success=False`
- `response="[AI_DEBUG dry-run — no API call made]"`
- `error_msg="AI_DEBUG mode active — prompt intercepted, no API call made"`
- `duration_ms=0`, `prompt_tokens=0`, `response_tokens=0`, `estimated_cost=0.0`
- `feature`, `model`, `prompt` from the actual call arguments

No changes to `dashboard.py`, `session_db.py`, or `main.py` — the signal chain was already fully wired and correct.

**AWR-036:** Launch with `$env:GT7_AI_DEBUG=1`. Run Practice Analysis. AI Log tab shows dry-run entry with feature name and full prompt text. `SELECT COUNT(*) FROM ai_interactions WHERE success=0` returns > 0.

---

### Group 7 — Event Persistence (COMPLETED 2026-06-22)

**Defects:** DEF-P1-009
**Unblocks:** DEF-P1-005 (AI prompt BoP context — was blocked by wrong tyre_wear/tuning values in strategy config)
**Test result:** 237 passed / 242 collected / 5 skipped (Qt display) / 0 failed

**Root cause identified:** `_evt_tyre_wear`, `_evt_fuel_mult`, and `_evt_refuel_rate` are `QSpinBox` (integer-only) widgets, but their corresponding DB columns (`tyre_wear`, `fuel_mult`, `refuel_rate_lps`) are `REAL` in the SQLite schema. `get_all_events()` returns Python `float` values; PyQt6's `QSpinBox.setValue()` raises `TypeError` on a float argument. The `except Exception: pass` in `_on_event_selected()` silently swallowed this TypeError, leaving the spinboxes at 1 (minimum/default) and skipping all remaining field population in the function (lines 7322–7357 never executed).

**Fix 1 — int cast for REAL→QSpinBox in `_on_event_selected()`:**
Changed three bare `setValue(evt.get(...))` calls to `setValue(int(round(evt.get(...) or default)))` for `tyre_wear`, `fuel_mult`, and `refuel_rate_lps`. All other fields (laps, duration, mandatory_stops) are INTEGER columns and return Python int — no cast needed.

**Fix 2 — Exception handler now prints traceback:**
Changed `except Exception: pass` to `except Exception: import traceback; traceback.print_exc()`. Silent exception suppression was the reason the root cause was invisible for so long.

**Fix 3 — Tuning perms group visibility consistency:**
`_on_event_selected()` was using `_bop_on and _tun_on` for the tuning permissions group visibility while `_update_tuning_perms_visibility()` correctly used `_tun_on` only. Fixed to `bool(_tun_on)` to match the design intent (tuning perms visible whenever Tuning is enabled, regardless of BoP).

**AWR-031:** Event load restores tyre_wear, fuel_mult, avail_tyres, req_tyres, tuning cats from saved values (not defaults). Set Active pushes correct multipliers to Strategy Builder and AI prompt.

**AWR-032:** DEF-P1-005 BoP prompt restrictions — after Group 7 fix, BoP/tuning values correctly reach `_config["strategy"]` and are forwarded to `_run_practice_analysis()` as `tuning_locked` / `allowed_tuning`. Requires runtime verification that AI prompt shows `## EVENT RULES — TUNING LOCKED` for a BoP=On event.

---

### Group 1 — Crash Fixes (COMPLETED 2026-06-21)

**Defects:** DEF-P1-003, DEF-P1-004, DEF-P1-008
**Test result:** 65 passed / 70 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-009, AWR-010, AWR-011)

**DEF-P1-003: _lbl_bank_status AttributeError — DONE**
- Added `_set_bank_status(self, msg: str)` helper with `hasattr` guard to `ui/dashboard.py`.
- Replaced all 20 bare `self._lbl_bank_status.setText(` calls via replace_all.
- `_refresh_lap_bank()` was already safe (has its own guard); no change needed there.

**DEF-P1-004: Timed race shown as 1-lap race in Practice Analysis prompt — DONE**
- Added `race_type: str = "lap"` and `duration_mins: int = 0` to `RaceParams` dataclass.
- Read `strat["race_type"]` and `strat["race_duration_minutes"]` in `_run_practice_analysis()`.
- `_build_practice_prompt()` now branches: timed → "Race duration: X minutes (Timed Race)", lap → "Race length: N laps".

**DEF-P1-008: Practice mode triggers RACE_FINISHED — DONE**
- Added `and self._session_type_override != SessionType.PRACTICE` to the RACE_FINISHED condition at `telemetry/state.py` line 292.
- Race mode and None override still fire. Qualifying is unguarded → tracked as DEF-P2-017.

---

### Group 2 — AI Prompt Accuracy + Data Persistence (COMPLETED 2026-06-21)

**Defects:** DEF-P1-005, DEF-P1-006, DEF-P1-007, DEF-P2-012, DEF-P2-014, DEF-P2-016
**Test result:** 98 passed / 103 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-012 through AWR-017)

**DEF-P1-005: Full setup payload ignores BoP restrictions — DONE**
- Added `tuning_locked` / `allowed_tuning` to `RaceParams`. `_build_practice_prompt()` in `ai_planner.py` injects constraint block. `_TUNING_CATEGORY_KEYS` maps category codes to setup dict keys for filtering.

**DEF-P1-006: Compound counts wrong in AI prompt — DONE**
- DB compound preferred over stale `_lap_compound_tags` in `_add_bank_lap_row()`. Stale tags cleared before session load in `_import_bank_session()`.

**DEF-P1-007: Fuel burn disagrees between Strategy Builder and lap log — DONE**
- `_loaded_session_avg_fuel` attribute set on historical load, cleared on live lap, checked first in `_computed_fuel_burn_lpl()`.

**DEF-P2-012: Wrong tyre wear multiplier — DONE**
- `_run_practice_analysis()` reads `tyre_wear_multiplier` fresh from `_psc` each call. Debug log added.

**DEF-P2-014: fuel_start / fuel_end not persisted to DB — DONE**
- Schema v2 migration adds `fuel_start`/`fuel_end` columns. `write_lap()` extended. `get_session_laps()` returns them. `main.py` dispatcher passes them.

**DEF-P2-016: No validation gate before AI call — DONE**
- Validation gate checks: timed race duration ≥ 5 min, lap race ≥ 2 laps, fuel burn > 0, ≥ 2 laps on one compound. Shows warning dialog and aborts if any fail.

---

### Group 3 — Session Reload Accuracy (COMPLETED 2026-06-21)

**Defects:** DEF-P2-011, DEF-P2-013
**Test result:** 117 passed / 122 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-018, AWR-019)

**DEF-P2-011: Outlaps included in summary — DONE**
- `get_session_laps()` now SELECTs `is_out_lap`. `_add_bank_lap_row()` accepts and stores `is_out_lap` in UserRole; displays "Practice (OL)" + dark green `#003A1A`. `_add_lap_row()` stores UserRole flags and uses `#003A1A` for outlap rows. `_refresh_practice_summary()` reads UserRole per row and skips outlap rows from best/avg/fuel.

**DEF-P2-013: Pit indicator lost after reload — DONE (fixed by Group 2)**
- `get_session_laps()` returns `is_pit_lap`. `_add_bank_lap_row()` uses it. Callers pass it. Group 3 additionally stores it in UserRole data. Side-effects of DEF-P2-014 fix covered this defect.

**Also fixed (side effects):**
- `_on_history_load_session()` now clears stale `_lap_compound_tags` before loading (was missing, `_import_bank_session()` had it). Also computes `_loaded_session_avg_fuel` (was missing from History tab path — only `_import_bank_session()` had it). Fuel average now excludes both pit laps and outlaps.

---

### Group 4 — BoP and Tuning Permissions (COMPLETED 2026-06-21)

**Defects:** DEF-P2-004, DEF-P2-005, DEF-P2-007 (DEF-P2-006 already fixed in Group 2)
**Test result:** 156 passed / 161 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-020, AWR-021, AWR-022)

**DEF-P2-004: BoP independent source removed — DONE**
- `_chk_bop` removed; `_current_setup_dict()` reads from `_config["strategy"]["bop"]`; Race Conditions group has read-only `_lbl_rc_bop` and `_lbl_rc_tuning` labels populated by `_sync_setup_builder_from_event()`.

**DEF-P2-005: Tuning permissions visibility fixed — DONE**
- `_update_tuning_perms_visibility()` changed from `bop.isChecked() and tuning.isChecked()` to `tuning.isChecked()` only. Group now shows whenever Tuning is enabled, regardless of BoP.

**DEF-P2-006: Setup Builder field locking — DONE (Group 2)**
- `_apply_setup_permissions()` fully implemented; tyre widgets always re-enabled; locked banner shown when tuning disabled.

**DEF-P2-007: AI output validation added — DONE**
- Prompt constraint blocks already injected by `_tuning_constraint_block()`. New: `validate_ai_setup_response()` in `ai_planner.py` post-processes AI output for locked-field violations. `_display_setup_result()` and `_display_practice_results()` in `dashboard.py` call it and prepend an amber warning banner if violations are detected.

---

### Group 5 — Live Mode + Voice Guards (COMPLETED 2026-06-21)

**Defects:** DEF-P2-002, DEF-P2-008, DEF-P2-QRF (new), DEF-P3-001, DEF-P3-002, DEF-P4-001
**Test result:** 187 passed / 192 collected / 5 skipped (Qt display) / 0 failed
**Status:** All awaiting runtime retest (AWR-023 through AWR-028)

**DEF-P2-002: Pit/fuel alerts now suppressed in Qualifying — DONE**
- `announcer.py` `_on_pit()` and `_on_fuel_low()` guard changed from `== "practice"` to `in ("practice", "qualifying")`.

**DEF-P2-008: PTT in Practice — CONFIRMED ALREADY WORKING**
- Source scan: `QueryListener` started unconditionally in `main.py:566`. `_handle_trigger()` has `try/except` + `traceback.print_exc()` + `_emit_ptt_status("PTT ERROR: ...")`. No mode guard in `_handle_trigger_inner()`. No code change needed.

**DEF-P2-QRF: Qualifying race-finished defect — DONE**
- `announcer.py` `_on_race_finish()`: added `if _session_mode != "race": return` guard as first line.
- `state.py` timed-race RACE_FINISHED path: changed `!= SessionType.PRACTICE` to `not in (SessionType.PRACTICE, SessionType.QUALIFYING)`.

**DEF-P3-001: Brake balance step — CONFIRMED ALREADY CORRECT**
- `_setup_bb.setSingleStep(1)` at `dashboard.py:3984`. No code change needed.

**DEF-P3-002: Live tyre compound label — DONE**
- Added `_lbl_live_tyre_compound` update in `_on_live_mode_changed()` — reads `mandatory_compounds` from strategy config and refreshes the label.

**DEF-P4-001: PTT status on Live tab — DONE**
- Added `_live_ptt_status_lbl` QLabel to Live tab info row (after Mode combo).
- `_on_ptt_status()` now updates both `_ptt_status_lbl` (Settings) and `_live_ptt_status_lbl` (Live).

---

**AWR-023:** Qualifying session — pit/fuel alerts silent
**AWR-024:** Qualifying timer end — no "Race finished" announcement
**AWR-025:** Practice timer end — no "Race finished" announcement
**AWR-026:** Practice PTT press — TRANSMITTING → PROCESSING → RADIO READY visible on Live tab
**AWR-027:** Event set active with compound — Live tab shows "Tyre: Racing Hard" (etc.)
**AWR-028:** Brake balance spinbox — each click changes value by exactly 1

---

### Group 6 — UI Placement + Data Quality (COMPLETED 2026-06-22)

**Defects:** DEF-P2-010, DEF-P2-015
**Register corrections:** DEF-P2-003, DEF-P2-017, DEF-P3-004 (all implemented; register was stale)
**Test result:** 204 passed / 209 collected / 5 skipped (Qt display) / 0 failed

**DEF-P2-015: Top speed ~11 km/h artefact — DONE**
- `_refresh_gear_ratios()` in `dashboard.py`: changed `if ms > 0:` to `if ms >= 50:`.
- Raw-field artefact (~3.0 raw × 3.6 = ~11 km/h) no longer written to `_spin_top_speed`.
- Spinbox shows "—" (special value text for 0). AI prompt receives `transmission_max_speed_kmh: 0`, which is excluded from setup recommendations.

**DEF-P2-010: Driver feedback form relocated to Practice Review — DONE**
- Removed `_build_driver_feedback_form()` call from `_build_setup_builder_tab()`.
- Added `_build_driver_feedback_form()` call to `_build_practice_review_tab()` (after Practice AI Analysis group).
- `_on_driver_feedback_submit()` updated: `_setup_feeling_input` guarded with `hasattr`; `session_id` uses `getattr(self, "_session_id", 0)`; `_setup_analyse_ai()` call removed (wrong tab context).

**Register corrections (code already correct, register was stale):**
- **DEF-P2-003** (Required Tyres checkbox grid): `_req_tyre_checks` already implemented; marked Fixed.
- **DEF-P2-017** (Qualifying RACE_FINISHED): Fixed via DEF-P2-QRF in Group 5; marked Fixed.
- **DEF-P3-004** (Race type mutual exclusivity): `_on_race_type_changed()` already implemented; marked Fixed.

**AWR-029:** Top Speed field shows "—" or ≥ 120 km/h (not ~11 km/h) after telemetry
**AWR-030:** Driver Feedback form visible in Practice Review; absent from Setup Builder

---

### (Original) Group 4 — Session Data Persistence (SUPERSEDED — completed in Groups 2 + 3)

**Defects:** DEF-P2-013 (completed in Group 3), DEF-P2-014 (completed in Group 2)

**DEF-P2-013: Pit stop indicator lost after reload — DONE (see Group 3 above)**

**DEF-P2-014: fuel_start/fuel_end not persisted — DONE (see Group 2)**

**Original plan for reference:**
- Step 1 (now done): Add `is_pit_lap` to the SELECT in `get_session_laps()`.
- Step 2: Add `is_pit_lap: bool = False` parameter to `_add_bank_lap_row()`.
- Step 3: When `is_pit_lap`, set col 11 to "Yes" and apply amber background (same logic as `_add_lap_row()`).
- Test: Save a pit lap. Reload from History. Col 11 shows "Yes" with amber background.

**DEF-P2-014: Fuel start/end not persisted**
- File: `data/session_db.py`, `telemetry/state.py` or `main.py`
- Step 1: Add `fuel_start REAL NOT NULL DEFAULT 0.0` and `fuel_end REAL NOT NULL DEFAULT 0.0` columns to `lap_records` via schema migration (version bump in `_migrate()`).
- Step 2: Pass `fuel_start` and `fuel_end` from `LapRecord` into `write_lap()`.
- Step 3: Add `fuel_start`, `fuel_end` to `get_session_laps()` SELECT.
- Step 4: Pass values through `_add_bank_lap_row()` and populate cols 6 and 7.
- Test: Complete a lap. Reload from History. Cols 6 (Fuel Start) and 7 (Fuel End) show non-zero values matching the live session.

---

### Group 5 — Session/Mode Logic

**Defects:** DEF-P1-007, DEF-P2-011, DEF-P2-017
**DEF-P1-008 was in this group — now DONE (Group 1).**

**DEF-P1-007: Fuel burn source mismatch**
- File: `ui/dashboard.py` — `_refresh_practice_summary()` and Strategy Builder fuel auto
- Fix: When historical laps are loaded into Practice Review via `_on_history_load_session()`, compute a session-scoped fuel average from the loaded rows and push it to a local `_loaded_session_avg_fuel` attribute. The Strategy Builder Fuel Burn Auto field reads from `self._loaded_session_avg_fuel` if set, falling back to `self._tracker.avg_fuel_per_lap` for live sessions only.
- Test: Load 10 historical laps averaging 4.2 L/lap. Strategy Builder shows ~4.2. Live session with 3.0 L/lap avg shows 3.0 when no historical session is loaded.

**DEF-P2-017: Qualifying mode may trigger RACE_FINISHED on timed events**
- File: `telemetry/state.py` — RACE_FINISHED condition (same block as DEF-P1-008 fix, line 292)
- Fix: Extend the existing Practice guard to also exclude Qualifying. Change:
  `and self._session_type_override != SessionType.PRACTICE`
  to:
  `and self._session_type_override not in (SessionType.PRACTICE, SessionType.QUALIFYING)`
- Tests required:
  - Qualifying mode does not fire RACE_FINISHED (new test in `TestRaceFinishedPracticeGuard`)
  - Practice mode still suppressed (existing AWR-011 + test)
  - Race mode still fires (existing test)
  - None override still fires (existing test)
- Test: Set timed event active. Switch Live tab to Qualifying mode. Drive for full duration. No "Race finished" announcement.
- Note: One-line change. Low risk. Can be batched with Group 1 if approved before Group 5.

**DEF-P2-011: Best lap includes outlaps**
- File: `ui/dashboard.py` — `_refresh_practice_summary()` (line 6782), `_add_lap_row()` (line 2156)
- Step 1: In `_add_lap_row()`, store `is_out_lap` as `Qt.ItemDataRole.UserRole` data on the lap time cell (col 3). Pass `is_out_lap` as a parameter (default `False`).
- Step 2: In `_refresh_practice_summary()`, skip rows where col 3 item's `UserRole` data is `True`.
- Step 3: For `_add_bank_lap_row()`, pass `is_out_lap` from the DB row and store it similarly.
- Test: Record an outlap (~30 s slower than pace). Session Summary best lap is not the outlap. Average fuel excludes the outlap.

---

### Group 6 — UI Behaviour

**Defects:** DEF-P2-005

**DEF-P2-005: Tuning Permissions group requires BoP to appear**
- File: `ui/dashboard.py` — `_update_tuning_perms_visibility()` (line 6996)
- Fix: Change condition from `self._evt_bop.isChecked() and self._evt_tuning.isChecked()` to `self._evt_tuning.isChecked()`.
- Test: Check Tuning without BoP — group appears. Uncheck Tuning — group hides. Check both — group still appears.

---

### Implementation Constraints

- Fix each group atomically. Run `python -m pytest tests/ -v` after each group. Do not proceed to the next group if tests fail.
- Each fix must include a regression test in `tests/` that would have caught the defect.
- Do not implement fixes until this analysis is confirmed complete by user.
- **Group 1 COMPLETE (2026-06-21).** 65/70 tests pass. AWR-009/010/011 awaiting runtime.
- Group 2 partial compound dependency: DEF-P2-012 (tyre wear) needs Group 3 for accuracy verification; DEF-P1-005, DEF-P2-015, DEF-P2-016 have no compound dependency.
- DEF-P2-017 (qualifying guard) is a one-line extension of the Group 1 state.py fix — can be batched with Group 2 or treated as Group 5.
- Groups 4, 5, 6 are independent of each other and can be done in parallel if needed.

---

### Group 17 (user Group 16) — Corner-Level Telemetry Learning (2026-06-23)

**New tests:** `tests/test_group17_corner_learning.py` — 64 tests, all pass

**Coverage:**
- CornerIssue dataclass and ISSUE_TYPES constant
- `_corner_id_from_xyz()` — XZ world bucket snapping (100 m grid)
- PATH A (`detect_issues_from_lap_records`) — brake_lock, wheelspin, oversteer from event_positions_json
- Repeated-issue thresholds: ≥3 laps OR ≥30% of valid laps
- One-off events below both thresholds not flagged
- Multiple distinct corners produce separate issues
- Malformed JSON in event_positions_json skipped safely
- PATH B (`detect_corner_events_from_frames`) — frame-by-frame brake lock + exit wheelspin detection
- `detect_issues_from_frame_data` — aggregate per-lap events with thresholds
- `strong_drive_confirmed` excluded from repeated-issue list
- `merge_issues()` — PATH B overwrites PATH A for same (corner_id, issue_type)
- Fix verification: fixed, improved, unchanged, worse, not_enough_data
- `build_corner_summary_for_prompt()` — header, corner IDs, issue types, %, setup focus, fix status, max_issues cap
- `get_setup_advice()` — all major issue types return non-empty lists
- SessionDB schema v4: `corner_issues` table created, `PRAGMA user_version = 4`
- `save_corner_issues()` — accepts CornerIssue objects and plain dicts
- `get_corner_issues()` — filtered by car_id and track
- `get_previous_corner_issues()` — excludes current session_id, different car returns empty
- Safe degradation: missing JSON field, missing pos/wheel fields in frames, verify_fix with sparse dicts

**Files changed:**
- NEW: `data/corner_learning.py`
- `data/session_db.py` — _DDL_V4, _migrate_v4(), save_corner_issues(), get_corner_issues(), get_previous_corner_issues(), get_session_laps() adds event_positions_json to SELECT
- `strategy/ai_planner.py` — corner_issues_summary param in _build_practice_prompt(), analyse_practice_session(), _build_race_prompt(), analyse_strategy()
- `strategy/driving_advisor.py` — corner_issues_summary param in build_coaching_response(), _build_coaching_prompt(), build_setup_advice_response(), _build_setup_prompt(), _build_combined_prompt()
- `ui/dashboard.py` — corner learning wired in _run_practice_analysis() (PATH A detection, save, verify, prompt); _run_ai_analysis() reads saved issues for strategy prompt
- `tests/test_group16_per_lap_telemetry.py` — test_user_version_is_3 updated to >= 3

**Tests Run:** 707 pass / 5 skip / 0 fail (712 collected)

---

### Group 18 — DEF-P3-014 Startup Residual Strategy/Race Config Activation (2026-06-23)

**Defect:** Running `python main.py` with a previously saved event/plan printed:
```
[Strategy] plan set: 2 stints
[StateTracker] race config: timed, duration=40.0 min
[StateTracker] race config: timed, duration=40.0 min
```
No strategy plan should be active and no race config should be pushed to StateTracker until the user explicitly activates one.

**Root Causes:**

1. `main.py` lines 361–365 (removed): called `strategy_engine.set_plan()` at startup with `config["strategy"]["stops"]` — immediately activated the Live Race Engineer.

2. `main.py` lines 509–527 (removed): applied `tracker.set_race_config()` from persisted `config["race"]` / `config["strategy"]["race_type"]` on startup before window opened — first StateTracker print.

3. `ui/dashboard.py` `_update_race_config()` (removed block): called `tracker.set_race_config()` during `_build_strategy_builder_tab()` construction on every startup — second StateTracker print.

4. `ui/dashboard.py` `_on_event_set_active()` line 7801 (fixed): imported `from telemetry.tracker import RaceType` — module does not exist. Import was silently caught by `except Exception`, so `set_race_config()` never fired from the explicit user activation path. Fixed to `from telemetry.state import RaceType`.

**Fixes Applied:**

- `main.py`: Removed `set_plan()` call with saved stops (stops remain available in config for Strategy Builder UI population in `dashboard.__init__`)
- `main.py`: Removed entire `set_race_config()` startup block (both `config["race"]` path and strategy fallback)
- `ui/dashboard.py` `_update_race_config()`: Removed the `if race_type in ("timed", "lap"):` tracker-push block (11 lines). Config persistence and label update remain.
- `ui/dashboard.py` `_on_event_set_active()`: Fixed import `telemetry.tracker` → `telemetry.state`

**New tests:** `tests/test_group18_startup_no_plan.py` — 21 tests, all pass

**Coverage:**
- StateTracker starts with UNKNOWN race type and zero duration
- RaceStrategyEngine starts with empty stints and inactive
- `main.py` source: no `set_plan()` call in `main()` function
- `main.py` source: no `set_race_config()` call in `main()` function
- `_update_race_config()` source: no `set_race_config()` call
- `_update_race_config()` still calls `_persist_config()`
- `_on_event_set_active()` source: no `telemetry.tracker` import
- `telemetry.tracker` module confirmed non-existent
- `set_plan([])` leaves engine inactive
- `set_plan([Stint(...)])` populates stints but `_active` remains False
- Empty-stint engine ignores events (no-op)
- `set_race_config()` changes `_manual_race_type` and `_timed_race_duration_ms`
- `computed_remaining_ms()` returns -1 when no config set (correct idle state)
- Config with saved stops does not auto-activate engine after fix
- Config with race_type does not auto-push to tracker after fix
- Zero `set_race_config()` calls during simulated startup

**Architecture boundary preserved:** `_on_event_set_active()` (explicit user action) remains the ONLY path that calls `tracker.set_race_config()`.

**Tests Run:** 728 pass / 5 skip / 0 fail (733 collected)

---

### Group 17A — Track Intelligence Seed Loader and Track Modelling Foundation (2026-06-24)

**New module:** `data/track_intelligence.py` — typed seed loader for `docs/track_modelling_seed/track_modelling_seed.yaml`.

**Dataclasses added:**
- `TrackSeedMetadata` — schema name, version, purpose, track/layout counts
- `CalibrationCarProfile` — primary calibration car facts (Porsche 911 RSR '17)
- `TrackLayoutSeed` — layout facts: length, corners, elevation, pit delta, flags, modelling status
- `TrackLocationSeed` — location grouping layouts, aliases, region/country/surface flags
- `TrackSeedLoadResult` — load result with errors, warnings, duplicate detection, unknown status tracking

**Enum added:**
- `TrackModellingStatus` — 9 values: `not_modelled`, `seed_only`, `telemetry_sampled`, `reference_path_built`, `segment_detected`, `user_reviewed`, `practice_refined`, `race_validated`, `engineer_grade`
- Helper methods: `is_ready_for_calibration()`, `is_ready_for_ai()`, `missing_calibration_requirements()`

**Functions added:**
- `load_track_seed(yaml_path, force_reload)` — loads + validates YAML, caches on success
- `get_track_locations()` — returns all 41 track locations
- `get_track_layouts()` — returns flat list of all 121 layouts
- `resolve_track_layout(track_location_id, layout_id)` — exact lookup by IDs
- `search_track_layouts(query)` — case-insensitive substring search across names and aliases
- `build_seed_track_context_for_prompt(track_location_id, layout_id)` — AI prompt context block with caveat for unmodelled layouts

**Validation checks:**
- File exists check
- Required metadata fields (`schema_name`, `schema_version`, `generated_utc`)
- At least one calibration car profile
- Non-empty tracks list
- Unknown modelling_status values preserved and reported
- Duplicate layout IDs detected and reported
- Layout ID prefix match (warning if mismatch)
- Alias clash with other location IDs (warning if found)

**Caching:** Results cached after first successful load from default path. Custom path never pollutes cache.

**Documentation:** `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` created.

**Coverage:**
- All 9 enum values exist and are correct strings
- `is_ready_for_calibration()`: False below `telemetry_sampled`, True at and above
- `is_ready_for_ai()`: False below `segment_detected`, True at and above
- `missing_calibration_requirements()`: non-empty for unmodelled, empty for engineer_grade
- Seed file exists and loads without errors
- Metadata fields populated: schema_name, schema_version
- 41 track locations loaded
- 121 layouts loaded (flat list)
- Calibration car: Porsche 911 RSR, 509 BHP, 1243 kg, RH tyres, Gr.3 MR
- No duplicate layout IDs in real seed
- Fuji Full Course: 4563m, 16 corners, 17s pit delta, rain=True
- Daytona Road Course: 5729m
- Deep Forest Reverse: notes populated
- All layouts have valid `TrackModellingStatus` enum values
- Missing file → failure result
- Invalid YAML → failure result
- Missing schema_name → error reported
- Missing calibration cars → error reported
- Empty tracks → error reported
- Unknown modelling_status → preserved in `unknown_modelling_statuses`
- Duplicate layout_id → detected in `duplicate_layout_ids`
- Root not a dict → failure result
- Valid custom seed → success
- 41 locations returned, all have IDs and display names
- All locations have at least one layout
- Flat layout list is 121 items, all `TrackLayoutSeed`
- All layouts have `track_location_id` populated
- Resolve known layout returns correct object
- Resolve unknown location → None
- Resolve unknown layout → None
- Search by display name (Fuji → 2 layouts)
- Search case-insensitive
- Search by location ID substring
- Empty query → empty list
- No-match query → empty list
- Search by alias (custom seed)
- Search "Reverse" returns only reverse layouts
- `build_seed_track_context_for_prompt` returns non-empty string
- Context contains track name and layout name
- Context contains seed data caveat for unmodelled layouts
- Context contains calibration car boundary note
- Unknown location → error string
- Unknown layout → error string
- Fuji Full Course context includes "4563"
- Context includes modelling_status
- Second `load_track_seed()` call returns same cached object
- `force_reload=True` returns different object with same metadata
- Custom path does not write to global cache
- Cache reset to None behaves correctly

**Tests Run:** 791 pass / 5 skip / 0 fail (796 collected)

---

### Group 17B — Track Modelling UI Foundation (2026-06-24)

**New module:** `ui/track_modelling_vm.py` — pure-Python view model, no PyQt6 dependency.

**Modified:** `ui/dashboard.py` — tab 12 "Track Modelling" added; `_build_track_modelling_tab()`, `_tm_on_tab_shown()`, all `_tm_*` slots and widgets.

**View model functions tested:**
- `format_layout_facts(layout, loc)` — 27-row list; None → UNKNOWN_VALUE; bools → Yes/No/Unknown; units appended (m, s, %)
- `format_readiness(layout)` — seed_only flag, calibration readiness, AI readiness, missing steps count + drill-down rows
- `format_calibration_car(car)` — 509 BHP, 1243 kg, RH, Gr.3, MR; PP (stock) present only when set
- `get_seed_warning_text(layout)` — SEED DATA ONLY for not_modelled/seed_only; PARTIAL TELEMETRY for sampled/path_built; empty for segment_detected+; "No layout selected" for None
- `is_seed_only(layout)` — True for not_modelled, seed_only; False for sampled+; True for None
- `build_location_display_items(seed_result)` — 41 items, sorted alphabetically, correct IDs
- `build_layout_display_items(seed_result, loc_id)` — Fuji=2, Spa=2+, empty for unknown; failed seed → []
- `get_selected_location(seed_result, loc_id)` — resolves known; None for unknown/empty
- `get_selected_layout(seed_result, loc_id, lay_id)` — resolves Fuji full (4563m); None for unknown
- `build_prompt_preview(seed_result, loc_id, lay_id)` — placeholder for empty ids; Fuji content >100 chars; includes caveat; error text for failed seed
- `describe_seed_load_status(seed_result)` — version, 41 locations, 121 layouts; FAILED for errors; warning count
- `CALIBRATION_CAR_BOUNDARY_NOTE` — non-empty, mentions Porsche, mentions independence
- `SEED_WARNING_TEXT` — non-empty, mentions SEED, mentions calibration

**Tests Run:** 892 pass / 5 skip / 0 fail (897 collected)

---

### Group 17C — Calibration Lap Capture and Reference Path Builder (2026-06-24)

**New module:** `data/track_calibration.py` — pure Python, no PyQt6 dependency.

**Data models:**
- `TelemetrySample` — one GT7 telemetry snapshot with `from_frame()` duck-typed factory; `steering=None` (not in GT7); `is_off_track` from `road_plane_y < 0.5 AND speed > 20 kph`; `is_in_pit_lane=None`
- `LapQualityResult`, `CalibrationLap`, `CalibrationSession`, `ReferencePathPoint`, `ReferencePath`, `CalibrationBuildResult`
- `CalibrationLapQuality` enum: `USABLE`, `LOW_CONFIDENCE`, `REJECTED`
- `CalibrationSource` enum: `GT7_TELEMETRY_LIVE`, `IMPORTED_JSON`, `SYNTHETIC_TEST`

**Quality rejection rules:** too few samples (<50), all-zero xyz, coordinate jump >100 m, pit lane >10%, off-track >30%, duration outlier (>2×/<0.5× session median), path length outlier

**Distance/progress helpers:** `point_distance_3d`, `estimate_path_length`, `detect_coordinate_jumps`, `cumulative_distances`, `normalize_to_lap_progress`, `resample_to_buckets`

**Reference path:** `build_reference_path(session)` — 200 buckets, averaged x/y/z/speed, cumulative distance, confidence from fill rate × lap count; requires ≥ 2 usable laps

**File I/O:** `export_reference_path_json`, `import_reference_path_json` (temp dir safe)

**UI:** Disabled placeholder buttons added to Track Modelling tab right panel (Start/Stop Calibration Session, Build Reference Path, status label). No live wiring.

**Test coverage:**
- `TelemetrySample` supports optional/missing channels
- `from_frame()` factory duck-typed; `steering` always None; `is_off_track` from road_plane_y heuristic
- `CalibrationSession` defaults: `porsche_911_rsr_991_2017`, empty laps, GT7_TELEMETRY_LIVE source
- Lap quality: rejects too few samples, all-zero xyz, coordinate jumps, excessive pit/off-track, duration/path outliers
- `point_distance_3d`, `estimate_path_length`, circle circumference accuracy
- Teleport/jump detection: threshold exclusive, multiple jumps
- `cumulative_distances` monotonically increasing, length = sample count
- `normalize_to_lap_progress` 0.0→1.0, monotonic, degenerates to zeros
- `resample_to_buckets` n_buckets count, all samples assigned, ordered progress
- `build_reference_path`: fails with no/1 lap, succeeds ≥2, correct IDs, confidence 0–1, distance monotonic, rejected laps excluded
- Export/import roundtrip preserves all fields; missing file raises; creates nested output dir
- `assess_session_laps` session-median outlier detection
- Regression: Group 17A/17B imports still clean; seed loads; constants valid

**Tests Run:** 994 pass / 5 skip / 0 fail (999 collected)

---

### Group 17D — Live Telemetry Calibration Session Wiring (2026-06-24)

**New module:** `data/track_calibration_runtime.py` — pure Python, no PyQt6 dependency.

**Adapter helpers (pure functions):**
- `can_capture_calibration_sample(packet)` — guards intake; returns False for paused/loading/off-track or exception
- `infer_lap_number(packet, fallback)` — `laps_completed + 1` when ≥ 0; fallback when -1 (practice mode)
- `packet_to_calibration_sample(packet, lap_number)` — duck-typed GT7Packet → `TelemetrySample`; `steering=None` (not in GT7 protocol); `is_in_pit_lane=None`; `is_off_track` from `road_plane_y < 0.5 AND speed > 20 kph`; returns None on invalid/exception

**State machine:** `CalibrationCaptureState` enum: `INACTIVE`, `RECORDING`, `STOPPED`, `BUILT`, `ERROR`

**Controller:** `TrackCalibrationCaptureController`
- `start_session(track_location_id, layout_id, calibration_car_id=PRIMARY)` — fails with ERROR state if IDs blank
- `add_sample_from_packet(packet)` — RECORDING only; infers lap number; closes current lap on boundary; groups into `CalibrationLap` objects
- `stop_session()` — flushes in-progress lap; transitions to STOPPED
- `evaluate_laps()` — delegates to `assess_session_laps()`
- `build_reference_path()` — delegates to `build_reference_path()`; transitions to BUILT on success
- `save_reference_path(output_dir)` — delegates to `export_reference_path_json()`
- `get_status_summary()` — dict with 15 fields for UI status labels
- Properties: `can_start`, `can_stop`, `can_build`, `can_save`, `is_recording`

**`ui/dashboard.py` changes:**
- `SignalBridge.calibration_packet = pyqtSignal(object)` — cross-thread ~10 Hz packet delivery
- Import `TrackCalibrationCaptureController`
- Calibration group rebuilt with 4 active buttons (Start/Stop/Build/Save) and 5 status labels
- `self._tm_controller = TrackCalibrationCaptureController()` stored on window
- `_tm_on_layout_changed()` and `_tm_clear_detail_panels()` call `_tm_update_cal_buttons()`
- New slots: `_tm_on_calibration_packet`, `_tm_start_session`, `_tm_stop_session`, `_tm_build_path`, `_tm_save_path`, `_tm_update_cal_buttons`, `_tm_update_cal_status`
- `_connect_signals()` wires all 5 new connections

**`main.py` changes:**
- `_cal_pkt_counter = [0]` closure variable
- Every 6th packet in `on_packet()`: `bridge.calibration_packet.emit(packet)` — ~10 Hz subsampling

**Test coverage (81 tests, 10 test classes):**
- `TestCanCaptureSample` — valid, not-on-track, paused, loading, missing/exception attrs
- `TestInferLapNumber` — 0/1/5/negative/missing/exception cases; fallback propagation
- `TestPacketToCalibrationSample` — field mapping, steering=None, pit=None, off-track heuristic, threshold boundary, paused/invalid/malformed → None
- `TestCalibrationCaptureState` — all 5 enum values
- `TestControllerStart` — inactive state, blank IDs fail, valid IDs succeed, Porsche default, custom car, reset on restart
- `TestControllerSampling` — captures while recording; ignores when inactive/stopped/paused/off-track
- `TestControllerLapGrouping` — samples grouped by lap number, boundary detection, multi-lap, flush on stop, lap time from timestamps, practice mode fallback
- `TestControllerStop` — state transition, double-stop fails, can_build guard
- `TestControllerBuild` — fails while recording/no session/no laps/1 lap; succeeds with 2 good laps; state=BUILT; can_save; rebuild ok
- `TestControllerSave` — None before build, temp dir roundtrip, saved path in summary
- `TestControllerStatusSummary` — 15 required keys; state values at each lifecycle stage
- `TestButtonStateProperties` — all can_start/can_stop/can_build/can_save transitions
- `TestControllerEvaluateLaps` — empty without session; returns per-lap results
- `TestRegressionImports` — Groups 17A/17B/17C/17D all importable

**Tests Run:** 1075 pass / 5 skip / 0 fail (1080 collected)

---

### Group 17E — Automatic Track Segment Detection (2026-06-24)

**New module:** `data/track_segment_detection.py` — pure Python, no PyQt6 dependency.

**Enums:**
- `TrackSegmentType` (12 values): `start_finish`, `straight`, `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone`, `gear_zone`, `limiter_zone`, `fuel_saving_candidate`, `kerb_or_bump_candidate`, `unknown`
- `TrackSegmentDirection`: `left`, `right`, `unknown`
- `TrackSegmentDetectionConfidence`: `high`, `medium`, `low`, `insufficient`

**Dataclasses:**
- `SegmentDetectionConfig` — 13 configurable thresholds (brake/throttle/curvature/RPM/kerb/fuel-save/straight)
- `DetectedTrackSegment` — per-segment output with `segment_id`, `segment_type`, `display_name`, progress bounds, `confidence`, `evidence`, `warnings`, `source_lap_count`, `turn_number`, optional `calibration_car_id` (set for car-specific segments)
- `SegmentDetectionResult` — full detection output with corner count, expected count, confidence, errors, warnings

**Private helpers (7):**
- `_smooth(values, window)` — centred rolling average
- `_compute_headings_xz(samples)` — heading from consecutive X/Z positions; zeros when no position variation
- `_angular_diff(a, b)` — normalised angular difference (-π, π]
- `_compute_curvature(headings, cum_dists)` — heading change rate per metre (rad/m); smoothed
- `_find_local_minima(values, min_drop)` — local minima where drop ≥ min_drop from preceding max
- `_find_local_maxima(values)` — local maxima
- `_has_position_variation(samples)` — True when total XZ movement > 1 m

**Per-lap detection:** `detect_segments_from_lap(lap, config, track_location_id, layout_id) → list[DetectedTrackSegment]`
- Computes lap_progress, smoothed speed, XZ headings, curvature
- Finds speed minima as apex candidates; walks back/forward for braking onset and exit
- Emits per-corner: `braking_zone` (0–80% of entry-to-apex), `corner_entry` (80–100%), `apex_zone` (±3% around apex), `corner_exit` (apex to 60% of exit), `traction_zone` (60–100% of exit)
- Fills inter-corner gaps with `straight` or `fuel_saving_candidate` (span ≥ 8% + avg throttle > 70%)
- All braking/traction zones tagged with `calibration_car_id = PRIMARY_CALIBRATION_CAR_ID`
- Single-lap confidence: LOW (speed-only) or MEDIUM (curvature evidence)

**Multi-lap detection:** `detect_track_segments(session, reference_path, layout_seed, config) → SegmentDetectionResult`
- Extracts USABLE laps only (REJECTED ignored)
- Per-lap corner detection, then `_cluster_apex_progress` groups by proximity (2.5% merge radius)
- Clusters in ≥ 2 laps → confirmed corners; < 2 laps → warning + excluded
- Confidence: HIGH (≥ 3 laps + curvature), MEDIUM (≥ 2 laps), LOW (1 lap), INSUFFICIENT (0)
- `layout_seed.corners_expected` used for count mismatch warning ONLY — no corners invented
- Auxiliary: gear zones (modal gear at apex ±3 samples), limiter zones (RPM ≥ 92% observed max), kerb candidates (Z-spike consistent across ≥ 2 laps), fuel-save candidates (inter-corner gaps ≥ 8%)

**Corner numbering:** `assign_corner_numbers(segments, expected_corner_count) → list[DetectedTrackSegment]`
- Sorts apex zones by `lap_progress_mid`, assigns T1/T2/T3…
- Mismatch warning on all apex segments when |detected − expected| > 2
- Never invents or removes corners to match expected count

**JSON I/O:**
- `export_segment_detection_json(result, output_dir, session_id) → Path` — schema `segment_detection_result_v1`
- `import_segment_detection_json(json_path) → SegmentDetectionResult` — raises `FileNotFoundError`, `ValueError`
- Filename: `<track_loc>__<layout>__segments__<session_id>.json`

**`ui/dashboard.py` changes:**
- Import: `from data.track_segment_detection import detect_track_segments as _detect_track_segments`
- "Detect Segments" button (5th button in Calibration group; enabled when `ctrl.can_save`)
- 3 status labels: `_tm_lbl_seg_summary`, `_tm_lbl_seg_expected`, `_tm_lbl_seg_status`
- `_tm_detect_segments()` method: fetches session from `ctrl._session`, fetches layout seed from UI state, calls `_detect_track_segments`, updates all labels; shows `QMessageBox.warning` on failure
- `_connect_signals()` wires `_tm_btn_detect_segs.clicked → _tm_detect_segments`
- `_tm_update_cal_buttons()` sets `_tm_btn_detect_segs.setEnabled(ctrl.can_save)`

**Car-specific vs track-geometry boundary:**
- `calibration_car_id` set on: `braking_zone`, `corner_entry`, `traction_zone`, `limiter_zone`, `fuel_saving_candidate`, `gear_zone`
- NOT set on: `apex_zone`, `straight`, `corner_exit`, `kerb_or_bump_candidate` (geometry candidates)
- All car-specific segments carry warning: "Car-specific — Porsche RSR, not universal"

**GT7 limitations documented:**
- `steering=None` in all GT7 packets → corner direction from XZ heading only
- No per-sample `is_in_pit_lane` → pit laps excluded by session-level quality assessment only
- `yaw_rate` (angvel_z) available as secondary curvature evidence (not primary)

**Test coverage (99 tests, 22 test classes):**
- `TestEnums` — 5 tests: all 12 segment types, direction, confidence, str-comparability
- `TestDataclasses` — 4 tests: config defaults/custom, DetectedTrackSegment, SegmentDetectionResult
- `TestSmooth` — 5 tests: empty, single, constant, length, spike reduction
- `TestHeadings` — 4 tests: straight X, constant position, single sample, empty
- `TestCurvature` — 2 tests: straight → zero, empty
- `TestLocalMinima` — 5 tests: finds minimum, too-small drop, empty, two-long, multiple minima
- `TestStraightDetection` — 4 tests: straight produces straight/fuel-save, no apex, no braking, spans most of lap
- `TestBrakingZoneDetection` — 4 tests: detected, car_id set, car warning, comes before apex
- `TestApexZoneDetection` — 4 tests: detected, speed evidence, middle range, mid equals midpoint
- `TestCornerExitDetection` — 3 tests: detected, after apex, has evidence
- `TestTractionZoneDetection` — 3 tests: detected, car_id set, after apex
- `TestGearZoneDetection` — 2 tests: detected in corner, has car_id
- `TestLimiterZoneDetection` — 4 tests: detected when high RPM, car_id, RPM evidence, covers only high-RPM samples
- `TestFuelSavingCandidateDetection` — 4 tests: long straight is candidate, low throttle not candidate, car_id, car warning
- `TestKerbCandidateDetection` — 3 tests: detected across 2 laps, single lap not reported, Z-spike evidence
- `TestCornerNumbering` — 4 tests: T1/T2/T3 assigned, progress order, display name, non-apex unchanged
- `TestCornerCountMismatch` — 3 tests: mismatch produces warning, warning on apex segments, small mismatch no warning
- `TestNoInventedCorners` — 2 tests: count not inflated to match expected, apex count equals detected_corner_count
- `TestMissingPositionData` — 3 tests: zero-position adds warning, does not crash, direction warning on segments
- `TestRejectedLapsIgnored` — 3 tests: all rejected fails, rejected not in source count, mixed session still detects
- `TestEmptyMalformedSessions` — 4 tests: empty fails safely, no-samples graceful, single-sample graceful, too-few returns empty list
- `TestJsonRoundtrip` — 9 tests: creates file, filename contains IDs, preserves success/segments/corner-count/types/turn-numbers, missing file raises, wrong schema raises
- `TestMultiLapConfidence` — 5 tests: 2-lap ≥ medium, confirmed corners source_count ≥ 2, success=True, has segments, track location propagated
- `TestDetectFromLap` — 4 tests: returns list, valid progress range, sorted by progress, single-lap ≤ MEDIUM
- `TestRegressionImports` — 6 tests: 17A–17E all importable, all segment types have string values

**Tests Run:** 1174 pass / 5 skip / 0 fail (1179 collected)

---

### Group 17F — Segment Review and Track Model Approval (2026-06-24)

**New module:** `data/track_segment_review.py` (pure Python, no PyQt6)

**Enums:**
- `SegmentReviewStatus` (8 values): `unreviewed`, `confirmed`, `renamed`, `split_required`, `merge_required`, `rejected`, `needs_more_laps`, `engineer_validated`
- `SegmentReviewAction` (7 values): `confirm`, `rename`, `reject`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `promote_engineer_validated`

**Dataclasses:**
- `ReviewedTrackSegment` — original detection fields preserved + review state (`review_status`, `reviewed_display_name`, `review_notes`, `reviewed_at`, `last_action`); `display_name` property returns override or original; `is_reviewed` property
- `TrackModelReviewResult` — detection metadata + `list[ReviewedTrackSegment]`; `detection_warnings` always preserved; `last_reviewed_at` updated on every action

**Action functions (7 — all mutate in place, return review):**
- `confirm_segment(review, segment_id, notes="")` → CONFIRMED + reviewed_at + last_action
- `rename_segment(review, segment_id, new_name, notes="")` → RENAMED + reviewed_display_name; blank name ignored
- `reject_segment(review, segment_id, notes="")` → REJECTED
- `mark_needs_more_laps(review, segment_id, notes="")` → NEEDS_MORE_LAPS
- `mark_split_required(review, segment_id, notes="")` → SPLIT_REQUIRED
- `mark_merge_required(review, segment_id, notes="")` → MERGE_REQUIRED
- `promote_engineer_validated(review, segment_id, notes="")` → ENGINEER_VALIDATED (CONFIRMED only; UNREVIEWED ignored)

**Aggregate helpers:**
- `review_completion_pct(review) → float` — 0–100%; empty = 100%
- `is_ai_ready(review) → (bool, list[str])` — 5-blocker rule set:
  1. Segments must exist
  2. All apex_zone segments reviewed (not UNREVIEWED)
  3. No NEEDS_MORE_LAPS segments
  4. No SPLIT_REQUIRED / MERGE_REQUIRED segments
  5. Required types detected: straight, braking_zone, apex_zone, corner_exit

**JSON I/O:**
- `export_review_json(review, output_dir, session_id) → Path` — schema `track_model_review_result_v1`
- `import_review_json(json_path) → TrackModelReviewResult` — raises `FileNotFoundError`, `ValueError`
- Filename: `<loc>__<layout>__reviewed_segments__<session_id>.json`

**`ui/track_modelling_vm.py` additions:**
- `format_segment_row(seg) → dict` — display values for table row (8 keys)
- `format_review_summary(review) → dict` — approval panel display (8 keys)
- `get_review_button_states(review, selected_segment_id) → dict` — 7 button enabled states

**`ui/dashboard.py` changes:**
- Import block: `track_segment_review` action functions + vm helpers
- `_tm_detection_result`, `_tm_review_result`, `_tm_selected_segment_id` instance variables
- `_tm_detect_segments()` auto-creates `TrackModelReviewResult` and populates table on success
- "Segment Review" QGroupBox: 8-col read-only QTableWidget, 6 action buttons (colour-coded), "Save Reviewed Model" button + save-path label
- "Review Approval" QGroupBox: 7 stat labels (detected/reviewed/confirmed/rejected/needs-laps/completion%/ai-ready/blockers)
- 11 new methods: `_tm_refresh_seg_table`, `_tm_on_seg_selected`, `_tm_refresh_review_buttons`, `_tm_refresh_approval_panel`, `_tm_review_confirm/rename/reject/needs_laps/split/merge/save`
- `_connect_signals()`: 8 new connections

**Deferred:**
- Graphical split/merge segment editing (currently review flags only)
- Integration into Setup Builder / Strategy Builder / Practice Analysis / Live prompts (Group 17G+)
- `modelling_status` promotion after review save

**Test coverage (122 tests, 14 test classes):**
- `TestSegmentReviewStatus` — 5 tests: 8 values, str comparability, isinstance str
- `TestSegmentReviewAction` — 4 tests: 7 values, str comparability, all actions
- `TestReviewedTrackSegment` — 7 tests: defaults, is_reviewed, display_name property
- `TestTrackModelReviewResult` — 4 tests: construction, defaults, created_at
- `TestCreateReviewFromDetection` — 9 tests: all-unreviewed, counts, field preservation, direction
- `TestConfirmSegment` — 7 tests: status, reviewed_at, unknown id, last_action, notes, return
- `TestRenameSegment` — 7 tests: status, name change, display_name, unknown id, blank name, reviewed_at
- `TestRejectSegment` — 4 tests: status, reviewed_at, unknown id, last_action
- `TestMarkNeedsMoreLaps` — 4 tests: status, reviewed_at, unknown id, last_action
- `TestMarkSplitRequired` — 3 tests: status, unknown id, last_action
- `TestMarkMergeRequired` — 3 tests: status, unknown id, last_action
- `TestPromoteEngineerValidated` — 4 tests: CONFIRMED→VALIDATED, UNREVIEWED blocked, unknown id, last_action
- `TestReviewCompletionPct` — 5 tests: 0%, partial%, 100%, empty=100%, mixed statuses
- `TestIsAIReady` — 10 tests: all blocker branches, true when all confirmed, ready with rejected apexes
- `TestAIReadyMissingTypes` — 4 tests: missing straight/braking/exit blocks, all types present no blocker
- `TestExportImportJSON` — 10 tests: file created, filename, schema, roundtrip fields, missing file raises, wrong schema raises
- `TestViewModelSegmentRow` — 7 tests: keys, status labels, turn number, progress, warnings
- `TestViewModelReviewSummary` — 7 tests: None dashes, counts, completion%, ai_ready, blockers
- `TestReviewButtonStates` — 7 tests: None all-false, no-selection, with-selection, save enabled/disabled
- `TestDetectionWarningsPreserved` — 3 tests: detection warnings visible, car warnings on segments, confirmation doesn't clear
- `TestRegressionImports` — 8 tests: 17A–17F importable, status/action values are strings

**Tests Run:** 1296 pass / 5 skip / 0 fail (1301 collected)

---

### Group 17G — Approved Track Model Resolver and Modelling Status Promotion (2026-06-24)

**New module:** `data/track_model_resolver.py` (pure Python, no PyQt6)

**Enums:**
- `TrackModelSourceType` (6 values): `seed_only`, `detected_unreviewed`, `reviewed_model`, `ai_ready_reviewed_model`, `engineer_validated_model`, `missing`
- `TrackModelResolutionStatus` (6 values): `found`, `found_with_warnings`, `seed_only_fallback`, `not_ai_ready`, `missing`, `error`

**Dataclasses:**
- `ResolvedTrackModel`: track_location_id, layout_id, source_type, modelling_status, ai_ready, review_completion_pct, segment/confirmed/rejected/needs_more_laps/warning counts, blockers, warnings, source_path, reviewed_model, seed_layout
- `TrackModelResolverResult`: resolution_status, resolved_model, all_candidate_paths, errors, warnings

**Discovery functions:**
- `list_reviewed_track_models(base_dir)` → all `*__reviewed_segments__*.json`, newest first
- `find_reviewed_models_for_layout(loc, layout, base_dir)` → filtered by prefix, newest first
- `load_reviewed_track_model(path)` → delegates to `import_review_json`
- `resolve_best_track_model(loc, layout, base_dir)` → best model with maturity priority

**Resolution priority logic:**
1. engineer_validated_model (any ENGINEER_VALIDATED segment) → rank 5
2. ai_ready_reviewed_model (is_ai_ready = True) → rank 4
3. reviewed_model (file exists, not AI-ready) → rank 3
4. seed_only (no reviewed file; seed entry found) → rank 1
5. missing (no seed entry either) → rank 0

When maturity equal: prefer newest by created_at, filename as tie-breaker.
Malformed files silently skipped; errors recorded in `TrackModelResolverResult.errors`.

**Schema extension (`data/track_segment_review.py`):**
- `TrackModelReviewResult.modelling_status: Optional[str] = None` (new optional field)
- `export_review_json()` computes and writes `modelling_status` (engineer_grade / user_reviewed / segment_detected)
- `import_review_json()` reads `modelling_status`; old files get `None` (backward-compatible)

**Prompt context builder (not wired to AI yet):**
- `build_resolved_track_context_for_prompt(loc, layout, base_dir) → str`
  - Missing → "MISSING" message
  - Seed-only → seed context + "No reviewed track model" warning
  - Reviewed → source, modelling status, AI-ready, segment summary, confirmed list, boundary note, blockers
  - Always includes Porsche RSR boundary note

**`ui/track_modelling_vm.py` addition:**
- `format_resolver_summary(resolver_result) → dict` — 8 keys: source_type (human label), modelling_status, ai_ready, blockers, model_path, warnings, resolution_status, candidate_count

**`ui/dashboard.py` changes:**
- Import: `resolve_best_track_model as _resolve_track_model`, `format_resolver_summary as _format_resolver_summary`
- `_tm_resolver_result` instance variable
- "Resolver Status" QGroupBox: 5 labels (source, status, AI-ready, candidates, file) + blockers + warnings
- `_tm_review_save()` calls `_tm_refresh_resolver()` after successful save
- `_tm_on_layout_changed()` calls `_tm_refresh_resolver()` to show pre-existing models
- `_tm_refresh_resolver()` — resolves model, formats summary, updates labels (AI-ready colour-coded)

**Deferred:**
- Integration into Setup Builder, Strategy Builder, Practice Analysis, Live Race Engineer (Group 17H+)
- Graphical split/merge editing
- Auto-detection of track/layout from telemetry

**Test coverage (68 tests, 13 test classes):**
- `TestListReviewedTrackModels` — 5 tests: empty dir, infix filter, non-json, sorted newest-first, multiple tracks
- `TestFindReviewedModelsForLayout` — 4 tests: matching layout, missing track, multiple versions, empty dir
- `TestLoadReviewedTrackModel` — 3 tests: valid file, missing file raises, bad schema raises
- `TestResolverSeedOnlyFallback` — 4 tests: seed fallback, ai_ready false, has warning, missing for unknown track
- `TestResolverNotAIReady` — 4 tests: resolution status, source type, blockers preserved, ai_ready false
- `TestResolverAIReady` — 5 tests: resolution status, source type, ai_ready flag, no blockers, modelling_status
- `TestResolverPriority` — 3 tests: ai_ready > not-ai-ready, engineer_validated > ai_ready, newest when equal
- `TestResolverMalformedFiles` — 3 tests: skip malformed + continue, all malformed falls to seed, wrong schema error
- `TestCandidatePathsTracked` — 1 test: all candidate paths in result
- `TestModellingStatusInJSON` — 5 tests: ai-ready=user_reviewed, not-ready=segment_detected, validated=engineer_grade, import reads it, old file returns None
- `TestBuildResolvedTrackContextForPrompt` — 8 tests: all branches (seed/missing/ai-ready/not-ready/engineer-validated)
- `TestViewModelResolverSummary` — 7 tests: None dashes, keys, ai_ready yes/no, source label, blockers, path, count
- `TestEngineerValidatedModel` — 3 tests: source type, modelling_status, resolution FOUND
- `TestWarningsPreserved` — 3 tests: detection warnings in resolved, segment warnings, warning_count
- `TestRegressionImports` — 9 tests: 17A–17G importable, enum string values

**Tests Run:** 1364 pass / 5 skip / 0 fail (1369 collected)

---

### Group 17I — Telemetry Issue to Segment Enrichment (2026-06-24)

**New module:** `data/track_issue_enrichment.py`

**Test file:** `tests/test_group17i_track_issue_enrichment.py` — 76 tests, 15 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 6 | Enum values, field defaults |
| TestExactSegmentIdMatch | 2 | Exact segment_id match; fallthrough when ID not in model |
| TestLapProgressMatch | 3 | Range match; outside-range nearest fallback; boundary values |
| TestDistanceAlongLapMatch | 1 | distance_along_lap_m → reference path → segment |
| TestXYZNearestMatch | 2 | XYZ nearest via reference path; no reference path → UNRESOLVED |
| TestUnresolvedFallback | 3 | Warning content; unresolved_count tracked; no evidence → UNRESOLVED |
| TestSeedOnlyConfidence | 2 | Seed-only → LOW/UNRESOLVED; missing → UNRESOLVED |
| TestRejectedSegmentHandling | 3 | REJECTED → UNRESOLVED; NEEDS_MORE_LAPS → LOW; UNREVIEWED capped |
| TestImplicationMappings | 11 | brake_lock, wheelspin, limiter, poor_exit, wrong_gear, oversteer, understeer |
| TestPromptSummary | 7 | Segment name/type/count; no invented names for unresolved; grouping |
| TestIssuesFromLapStats | 9 | All five position list types; XYZ populated; lap_num; empty |
| TestIssuesFromCornerIssues | 8 | Type mapping; corner_id decode; phase map; empty |
| TestDrivingAdvisorEnrichment | 6 | Returns string; empty without IDs; no raise; coaching/setup prompts |
| TestFullPipeline | 3 | End-to-end XYZ→segment→prompt; resolver exception; multi-lap |
| TestRegressionImports | 10 | All 17A–17H modules importable; decode_corner_id edge cases |

**Full suite result: 1574 pass / 5 skip / 0 fail (after 17J added)**

---

### Group 17J — Live Current Segment Resolver (2026-06-24)

**New module:** `data/live_segment_resolver.py`

**Test file:** `tests/test_group17j_live_segment_resolver.py` — 78 tests, 17 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 7 | Enum values, field defaults, dataclass construction |
| TestExactSegmentIdMatch | 3 | Exact match; HIGH confidence for ai_ready; unknown ID falls through |
| TestLapProgressMatch | 5 | Range match; start/end boundary; outside bounds → nearest; nearest → lower confidence |
| TestDistanceAlongLapMatch | 1 | distance_along_lap_m → reference path → lap_progress → segment |
| TestXYZNearestMatch | 2 | XYZ via reference path; no reference path → no_position_data |
| TestNoReviewedModel | 3 | seed_only → no_reviewed_model; missing → no_reviewed_model; warning present |
| TestNoPositionData | 2 | None position; empty position (all None fields) |
| TestNotAiReadyModel | 2 | Reviewed-not-AI-ready allows match with warning; confidence ≤ MEDIUM |
| TestPreviousNextSegment | 5 | Next present; previous present; start/finish wraparound; three-segment; single segment |
| TestRejectedSegmentExclusion | 2 | Rejected excluded from match; all rejected → no_segment_bounds |
| TestSegmentConfidenceDegradation | 3 | needs_more_laps → degraded + warning; unreviewed excluded by default; unreviewed included when config set |
| TestFormatLiveSegmentForEngineer | 8 | Name/confidence/next in text; nearest fallback note; no_reviewed_model/no_position_data/error safe text; no invented names |
| TestPacketToLivePosition | 9 | Valid packet; paused/loading/off-track/zero-xyz → None; lap_progress not set; distance not set; missing attrs; exception |
| TestGetLiveSegmentContextForPrompt | 4 | No model → ""; matched → prompt block; prompt includes segment type; no position → no invented names; never raises |
| TestDrivingAdvisorLiveSegment | 7 | No position → ""; no IDs → ""; returns string; does not raise; coaching/setup prompts include live segment |
| TestResolverErrorHandling | 3 | Exception → error status; malformed segments safe; all rejected → no_segment_bounds |
| TestRegressionImports | 11 | All 17A–17I importable; DrivingAdvisor has method; XZ-only distance verified; speed_kph populated; text length reasonable |

**Full suite result: 1574 pass / 5 skip / 0 fail**

---

### Group 17K — Segment-Aware Live Coaching Rules (2026-06-24)

**New module:** `data/live_segment_coaching.py`

**Test file:** `tests/test_group17k_live_segment_coaching.py` — 78 tests, 19 test classes

| Class | Tests | Coverage |
|-------|-------|----------|
| TestDataclassConstruction | 6 | Enum values (all 13 cue types, 4 priorities, 12 suppression reasons), dataclass defaults, config defaults |
| TestNoSegmentSuppression | 7 | no_reviewed_model/no_position_data/error → NO_SEGMENT; seed_only → SEED_ONLY; no issues → NO_MATCHING_RULE; cue=None when suppressed; garbage input never raises |
| TestLowConfidenceSuppression | 3 | unknown → LOW_CONFIDENCE; low by default → LOW_CONFIDENCE; low allowed when config disabled |
| TestBrakeLockRules | 6 | brake_lock+braking_zone → BRAKING_STABILITY HIGH; corner_entry → MEDIUM; cue text includes segment name; basis_issue_type set; repetition count |
| TestWheelspinRules | 2 | wheelspin+corner_exit → THROTTLE_PICKUP; wheelspin+apex_zone → THROTTLE_PICKUP |
| TestRotationRules | 2 | oversteer+apex → ROTATION; understeer+corner_entry → ROTATION |
| TestExitDriveRules | 2 | poor_exit_drive+corner_exit → EXIT_DRIVE; poor_exit_drive+traction_zone → EXIT_DRIVE |
| TestGearChoiceRules | 2 | wrong_gear+apex_zone → GEAR_CHOICE; wrong_gear+corner_exit → GEAR_CHOICE |
| TestLimiterRules | 2 | limiter_hit+straight → SHORT_SHIFT; limiter_hit+other → LIMITER_WARNING |
| TestConfigGatedRules | 3 | fuel_save suppressed by default; fires when enable_fuel_save_cues=True; tyre_management suppressed by default |
| TestSegmentQualitySuppression | 3 | rejected warning → REJECTED_SEGMENT; needs_more_laps warning → NEEDS_MORE_LAPS; allowed when config disabled |
| TestNoInventedNames | 4 | No {segment} literal in output; no invented corner names when display_name empty; suppressed format → ""; format with unresolved → "" |
| TestPriorityBehaviour | 3 | High repetition maintains base priority; medium confidence base priority; multi-issue → highest priority wins |
| TestCooldownBehaviour | 4 | Same cue+segment within 3 laps → COOLDOWN; same cue after N laps → fires; max_cues_per_lap → MAX_CUES_REACHED; empty previous_cues does not suppress |
| TestMinRepetitionsGate | 3 | Single lap suppressed (default min=2); 2 laps fires; config min=1 allows single |
| TestFormatForPrompt | 5 | Cue text in block; header present; basis line present; suppressed → ""; never raises |
| TestDebugMetadata | 3 | Suppressed → cue_included=False + reason; cue fired → cue_included=True + type/priority/segment; never raises |
| TestDrivingAdvisorIntegration | 6 | No position → ""; no IDs → ""; returns string; never raises; coaching prompt includes coaching block; coaching prompt omits block when no_call |
| TestRegressionImports | 12 | All modules importable; DrivingAdvisor has method; format_cue_text insert/remove; downgrade_priority low→low/high→medium; all covered issue types have fallback rule; garbage input safe; 17A+17G importable |

**Full suite result: 1652 pass / 5 skip / 0 fail**

---

### Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping (2026-06-24)

**New module:** `data/lap_distance_mapper.py` (pure Python, no PyQt6)

**Enums:** `LapDistanceMappingStatus` (mapped / mapped_with_wrap / no_distance_data / no_track_length / invalid_offset / error), `LapDistanceMappingConfidence` (high / medium / low / unknown)

**Dataclasses:** `LapStartOffsetCalibration` (track_location_id, layout_id, calibration_source, track_length_m, gt7_start_distance_m, model_start_distance_m, offset_m, confidence, sample_count, source_session_id, created_at, warnings), `LapDistanceMappingResult` (status, distance_along_lap_m, lap_progress, wrapped, confidence, warnings, offset_m, track_length_m), `LapDistanceMapperConfig` (min_track_length_m, clamp_progress)

**Core functions:**
- `normalise_distance(distance_m, track_length_m) -> float` — modulo wrap to [0, track_length); handles negatives; raises on ≤ 0 length
- `calculate_lap_start_offset(gt7_start, model_start, track_length) -> float` — normalised offset
- `map_road_distance_to_lap_distance(road_distance_m, offset_m, track_length_m, config) -> LapDistanceMappingResult` — full error-status returns
- `map_road_distance_to_lap_progress(road_distance_m, offset_m, track_length_m, config) -> LapDistanceMappingResult` — 0.0–1.0 clamped

**Calibration helpers:** `create_offset_zero()`, `create_offset_from_reference_path()`, `load_offset_calibration_for_track()`

**JSON persistence:** `export_offset_calibration_json(calibration, output_dir)` → `<loc>__<lay>__lap_offset.json`; `import_offset_calibration_json(path)`

**`data/live_segment_resolver.py` updates (Group 17L):**
- `LivePosition` gains `road_distance_m: Optional[float] = None` (raw GT7 field)
- `packet_to_live_position()` now populates `road_distance_m` from packet
- `enrich_position_with_road_distance(position, offset_calibration) -> LivePosition` added
- `resolve_live_segment()` gains optional `offset_calibration` parameter; Priority 3 now maps road_distance via offset before caller-supplied distance
- Matching priority updated to: segment_id → lap_progress → road_distance+offset → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved

**69 tests** in `tests/test_group17l_lap_distance_mapper.py`

| Test group | Count | What it covers |
|---|---|---|
| normalise_distance | 8 | normal, over-length, exact wrap, negative, zero, zero track raises, negative track raises |
| calculate_lap_start_offset | 5 | zero/nonzero gt7/model starts, equal → 0, raises on zero |
| map_road_distance_to_lap_distance | 10 | success, wrap, no_distance_data, no_track_length, below_min, invalid_offset, wrap warning text |
| map_road_distance_to_lap_progress | 8 | basic, start, near-end clamping, wrap, always [0,1], no data, no track length, result fields |
| Calibration helpers | 8 | create_offset_zero, from_reference_path (basic/nonzero gt7/none/empty/zero-length/session_id), confidence |
| JSON persistence | 4 | export creates file, import reads, round-trip all fields, missing file raises |
| packet_to_live_position | 4 | road_distance_m populated, None when missing, distance_along_lap_m still None, paused=None |
| enrich_position_with_road_distance | 5 | enriches, no-op (already set), no-op (no cal), no-op (no road_dist), returns new instance |
| resolve_live_segment integration | 4 | uses road_distance, prefers lap_progress, safe without calibration, wrap warnings propagated |
| load_offset_calibration_for_track | 2 | returns None when not found, loads when found |
| result field checks | 3 | stores offset/track_length, status is str-enum, no_distance_data str value |
| calibration fields | 1 | all fields preserved |
| config + edge cases | 4 | default config, clamp disabled, multiple wraps, session_id |
| regression | 3 | 17A–17K imports, road_distance_m field exists, optional field |

**Full suite result after Group 17L: 1721 pass / 5 skip / 0 fail**

---

### Group 17M — Runtime UAT and Calibration Workflow Hardening (2026-06-24)

**New module:** `data/track_modelling_runtime_check.py`

**New file:** `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist

**`ui/track_modelling_vm.py` additions:**
- `_WORKFLOW_ERROR_MESSAGES` — 11-key dict mapping error keys to human-readable strings
- `get_workflow_error_message(error_key)` — safe lookup with unknown-key fallback
- `get_calibration_button_states(ctrl_state, has_track, has_completed_laps, has_ref_path, has_review_model, selected_segment_id=None, has_track_length=False)` — returns 15-key bool dict for all workflow buttons
- `format_calibration_status_extended(status_summary, last_packet_age_s=None)` — returns dict with: state_text, recording_indicator, packet_age, sample_count, lap_count, path_info, saved_path
- `format_lap_offset_status(offset_calibration=None, track_length_m=None)` — returns dict with: status, offset_m, confidence, track_length, source, warnings, provisional_note
- `format_live_resolver_status_summary(loc_id, lay_id, resolver_result=None, offset_calibration=None, live_position=None, live_segment_result=None)` — returns newline-separated status string

**`data/track_modelling_runtime_check.py` (new):**
- `RuntimeCheckResult` dataclass — 14 fields covering track/resolver/offset/live status; `summary_text()` method
- `run_track_modelling_runtime_check()` — never raises; duck-typed arguments; aggregates full pipeline status

**`data/lap_distance_mapper.py` change:**
- `create_offset_zero()` — default source changed from `"manual"` to `"zero_offset"`; added `ValueError` on non-positive track_length_m

**`ui/dashboard.py` additions:**
- `_tm_lbl_packet_age` — packet age label in calibration group (green/amber/red based on age)
- `_tm_last_packet_time` and `_tm_offset_calibration` instance variables
- Lap Offset Calibration QGroupBox — Create Zero Offset / Load Offset / Save Offset buttons; status/detail/warning labels; provisional note
- `_tm_update_packet_age_label()` — refreshes packet age label from wall-clock timestamp
- `_tm_get_track_length_m()` — derives track length from reference path or seed
- `_tm_update_offset_status()` — refreshes all offset calibration labels
- `_tm_create_zero_offset()` — creates provisional zero calibration; shows dialog on missing track length
- `_tm_load_offset()` — loads calibration from JSON; shows informational dialog when not found
- `_tm_save_offset()` — saves calibration to JSON; updates status label
- Signal connections for the three new offset buttons

**94 tests** in `tests/test_group17m_runtime_hardening.py`

| Test group | Count | What it covers |
|---|---|---|
| TestWorkflowErrorMessages | 4 | all 11 keys non-empty, unknown key safe, track mention, GT7 mention |
| TestCalibrationButtonStatesInactive | 5 | start with/without track, stop/build/review all disabled |
| TestCalibrationButtonStatesRecording | 3 | stop enabled, start/build disabled while recording |
| TestCalibrationButtonStatesStopped | 4 | build with/without laps, start enabled, stop disabled |
| TestCalibrationButtonStatesBuilt | 4 | save_path, detect_segments enabled/disabled |
| TestCalibrationButtonStatesReview | 4 | confirm with/without selection, save_review with/without model |
| TestCalibrationButtonStatesOffsetActions | 5 | create_zero with/without track/length, load_offset with/without track |
| TestFormatCalibrationStatusExtended | 11 | inactive/recording/stopped/built text, packet age ms/warn, sample count, recording indicator, saved path |
| TestFormatLapOffsetStatus | 10 | no-cal, offset display, provisional/validated, warnings, track_length |
| TestFormatLiveResolverStatusSummary | 12 | no track, track shown, resolver/offset/position/segment display |
| TestRuntimeCheckResult | 5 | summary_text no track, with track, warnings, errors, offset_m |
| TestRunTrackModellingRuntimeCheck | 17 | no track, with track, resolver source extraction, offset provisional/validated, live position, live segment, never-raises, bad object |
| TestZeroOffsetCalibrationCreation | 5 | valid, track_ids, confidence LOW, zero length raises, negative length raises |
| TestRegressionImports | 6 | all 17A–17M imports, existing vm functions unchanged |

**Full suite result after Group 17M: 1815 pass / 5 skip / 0 fail**

---

### Group 17M UAT Defect Remediation (2026-06-25)

**Defects addressed:**
- DEF-17M-UAT-001 — Lap count mismatch display (8 shown / 5 valid confusion)
- DEF-17M-UAT-002 — Detect Segments crash (`seed_result.layouts` AttributeError)
- DEF-17M-UAT-003 — Saved reference path not discoverable after restart

**New functions:**
- `ui/track_modelling_vm.py` — `format_lap_count_info(status_summary) -> dict[str, str]` (3 keys: captured_text, quality_text, explanation)
- `ui/track_modelling_vm.py` — `format_file_audit_status(audit) -> dict[str, str]` (4 keys: saved_text, detail_text, load_status, extras_text)
- `data/track_calibration.py` — `reference_path_filename(loc_id, lay_id) -> str`
- `data/track_calibration.py` — `TrackModelFileAudit` dataclass (13 fields, `summary_line()`, `ref_path_status_text()`)
- `data/track_calibration.py` — `audit_track_model_files(loc_id, lay_id, search_dir=None) -> TrackModelFileAudit` (never raises)

**Dashboard changes:**
- `_tm_update_cal_status()` — uses `format_lap_count_info()` for clear lap count display; tooltip shows partial segment explanation
- `_tm_detect_segments()` — split into outer error catcher + `_tm_detect_segments_safe()` inner; crash wrapped in try/except with QMessageBox
- `_tm_detect_segments_safe()` — fixed `seed_result.layouts` → `get_selected_layout()`; disk fallback when no active session
- `_tm_on_layout_changed()` — calls `_tm_audit_and_show_saved_files()` to populate UI from disk on restart
- `_tm_audit_and_show_saved_files()` — new method; reads audit, updates save-path label, build-info label, offset label, Detect Segments button enabled state

**New test file:** `tests/test_group17m_uat_defects.py` (49 tests)

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestFormatLapCountInfo | 11 | no laps, recording, stopped, built, gap explanation, singular, edge cases |
| TestSeedResultLayoutsAccess | 5 | layouts attr absence, get_selected_layout correct use, wrong loc/lay |
| TestDetectSegmentsNoCrash | 3 | empty session, None seed, real layout seed |
| TestReferencePathFilename | 2 | filename format, ID-based naming |
| TestAuditTrackModelFilesNotFound | 5 | all false, loc/lay stored, expected path, never raises |
| TestAuditTrackModelFilesFound | 8 | exists, load_ok, point count, confidence, laps, modified, wrong track, Daytona integration |
| TestAuditTrackModelFilesCorrupt | 2 | corrupt JSON, empty JSON |
| TestFormatFileAuditStatus | 6 | no file, load ok, load failed, reviewed extras, offset extras, no extras |
| TestTrackModelFileAuditSummaryLine | 5 | no loc/lay, not found, found+load ok, status text no file, with file |
| TestRoundTripSaveAndAudit | 2 | save→audit→load round trip, crash-restart simulation |

**Full suite result after Group 17M UAT Remediation: 1864 pass / 5 skip / 0 fail**

---

### Group 17N UAT Defect Remediation (2026-06-25)

**Defect fixed:** DEF-17N-UAT-004 — Detect Segments requires a live calibration session despite a saved reference path existing.

**Root cause:** `detect_track_segments()` requires raw `CalibrationLap` objects with per-sample `TelemetrySample` data. `save_reference_path()` only persisted the 200-point aggregated `ReferencePath` JSON; raw lap samples were discarded on every app restart.

**Files modified:**
- `data/track_calibration.py` — Added `calibration_laps_filename()`, `export_calibration_laps_json()`, `import_calibration_laps_json()`. Updated `TrackModelFileAudit` with `calibration_laps_exists`, `calibration_laps_usable_count`, `can_detect_segments` (property), `is_legacy_ref_path_only` (property). `audit_track_model_files()` now audits the laps file. `summary_line()` includes lap count.
- `data/track_calibration_runtime.py` — `save_reference_path()` now writes both the reference path JSON and the calibration laps JSON in one call.
- `ui/dashboard.py` — `_tm_detect_segments_safe()` rewritten with three-path logic: active session / load from disk / legacy format dialog. `_tm_audit_and_show_saved_files()` updated with `can_detect_segments`/`is_legacy_ref_path_only` button logic.
- `ui/track_modelling_vm.py` — `format_file_audit_status()` now includes laps count in `detail_text` and distinguishes "Detect Segments ready" vs legacy format message in `load_status`.

**New test file:** `tests/test_group17n_uat_defects.py` — 41 tests

| Test class | Count | What it proves |
|---|---|---|
| `TestCalibrationLapsFilename` | 2 | Filename format, distinct from ref path |
| `TestExportCalibrationLapsJson` | 8 | File creation, USABLE-only filtering, field preservation, metadata, empty list, multiple laps, dir creation |
| `TestImportCalibrationLapsJson` | 10 | Returns CalibrationSession, track/car IDs preserved, lap count, sample round-trip, quality, error raising, session_id, yaw_rate |
| `TestSaveReferencePathAlsoSavesLaps` | 3 | Controller.save_reference_path() writes both files; lap count matches |
| `TestAuditIncludesCalibrationLaps` | 8 | Laps file detected, usable count, no-file state, can_detect_segments, is_legacy_ref_path_only |
| `TestDetectSegmentsFromLoadedLaps` | 4 | Loaded session has USABLE laps; detect_track_segments does not raise; returns SegmentDetectionResult; empty session returns failure |
| `TestFormatFileAuditStatusWithLaps` | 3 | Laps present in detail_text, legacy message, no ref path |
| `TestDaytonaBehaviourWithExistingFile` | 1 | Pre-17N Daytona file detected as legacy (skipped if file absent) |
| `TestRoundTripSaveReloadDetect` | 2 | Full pipeline: save → restart → detect without live session; controller save_reference_path produces both files |

**Also fixed:** `tests/test_group17m_uat_defects.py::TestFormatFileAuditStatus::test_file_found_load_ok_saved_text` — updated to match 17N-aware `format_file_audit_status()` behaviour (ref path only → legacy; both files → ready). Added `test_file_found_legacy_no_laps_shows_preformat_message` for the legacy case.

**Full suite result after Group 17N UAT Remediation: 1906 pass / 5 skip / 0 fail**

---

### Group 17N UAT-005 Defect Remediation (2026-06-25)

**Defect fixed:** DEF-17N-UAT-005 — "No Usable Calibration Laps" message lacks actionable rejection diagnostics.

**Root causes:**
1. `CalibrationLap.quality` defaults to `REJECTED` and was never updated after `build_reference_path()` assessed the laps as USABLE. `detect_track_segments()` filters by `quality == USABLE` → finds none → generic "No USABLE calibration laps" error even after successful Build.
2. `_tm_build_path()` only showed `result.errors`, discarding per-lap rejection reasons in `result.warnings`.

**Files modified:**
- `data/track_calibration.py` — `build_reference_path()` now mutates `CalibrationLap.quality` and `quality_reasons` after assessment (runs on both success and failure paths). Added `diagnose_calibration_session(session) -> dict` (structured diagnostic snapshot, never raises).
- `data/track_segment_detection.py` — Added `assess_session_laps` to imports. Added `_build_no_usable_laps_errors(session) -> list[str]` helper that re-assesses quality and builds per-lap diagnostic error lines. `detect_track_segments()` calls this instead of the hardcoded generic message.
- `ui/track_modelling_vm.py` — Added `format_build_failure_diagnostics(result, session=None) -> str` (multi-line dialog text: primary error, lap counts, per-lap rejection reasons, car ID, context-specific recommended action). Added `_min_samples()` helper.
- `ui/dashboard.py` — Added `format_build_failure_diagnostics as _format_build_diag` to track_modelling_vm import. `_tm_build_path()` now calls `_format_build_diag(result, session)` instead of `"\n".join(result.errors)`.
- `tests/test_group17n_uat_defects.py` — Updated `TestDaytonaBehaviourWithExistingFile::test_daytona_ref_path_is_legacy_until_resaved` to handle the three-way state (no laps file / laps file with 0 usable / laps file with >0 usable).

**New test file:** `tests/test_group17n_uat005_defects.py` — 32 tests

| Test class | Count | What it proves |
|---|---|---|
| `TestDiagnoseCalibrationSession` | 9 | Empty, all-usable, all-rejected, mixed, off-track, per-lap detail, car id, sample count, never-raises |
| `TestBuildReferencePathMutatesLapQuality` | 4 | Usable laps marked USABLE, rejected marked REJECTED, quality_reasons populated, failed build still mutates |
| `TestDetectSegmentsNoUsableLapsDiagnostics` | 7 | Empty session, rejected with reasons, count in error, car id, off-track advice, UDP advice, successful-session-works |
| `TestFormatBuildFailureDiagnostics` | 10 | String returned, counts, primary error, warnings, car id, no-laps message, UDP/off-track/one-usable advice, never-raises |
| `TestIntegrationBuildFailThenBuildSucceed` | 2 | Add laps → build succeeds → detect works; warnings surface in dialog text |

**Full suite result after Group 17N UAT-005 Remediation: 1938 pass / 5 skip / 0 fail**

---

### Group 17O — Seeded 1m Track Map, Width Corridor, Map Matching, Visual Verification (2026-06-25)

**New test file:** `tests/test_group17o_track_station_map.py` — 76 tests

| Class | Count | Coverage |
|-------|-------|----------|
| `TestBuildTrackStationMap` | 9 | station count, IDs, confidence, corners_expected, empty raises, headings, curvature, spacing |
| `TestResamplePath` | 5 | straight path, spacing accuracy, single point, empty list, 3D y preservation |
| `TestFindNearestStation` | 4 | exact match, between stations, empty raises, off-track |
| `TestStationMAndProgress` | 3 | start, midpoint, progress bounded 0-100 |
| `TestLateralOffset` | 4 | centreline zero, left positive, right negative, magnitude |
| `TestEdgeDistances` | 3 | equal edges on centreline, left reduces near-left, non-negative |
| `TestMissingWidth` | 2 | zero width falls back to default, empty map returns UNKNOWN |
| `TestPitAndOutlapDetection` | 5 | low speed, far from track, on track, outlap before crossing, not outlap after |
| `TestDaytonaSeedednCorners` | 7 | count=12, T1-T12 IDs, ascending stations, placeholder confidence, corners_expected, no corners map, placeholders fill to expected |
| `TestTelemetryOverlaySeparation` | 4 | no braking event fields, geometry-only fields, corner phase enum, segment types excluded |
| `TestDrawingPrimitives` | 10 | draw data returned, centreline, edges match length, corner labels count, no dot without match, has_map, empty map, no PyQt import, valid bounds, status text |
| `TestCarDotPrimitive` | 5 | dot created, position near station, confidence reflects match, no dot for pit, screen projection |
| `TestLowConfidenceState` | 5 | far=UNKNOWN, medium distance=MEDIUM, centreline=HIGH, warnings non-empty, confidence color green |
| `TestLegacyRefPathHandling` | 5 | 200-pt produces valid map, 200-pt corners, 200-pt matchable, curvature non-flat, JSON roundtrip |
| `TestWidthModel` (bonus) | 4 | unused pct at centreline, near-left detected, near-right detected, centreline not near-edge |
| `test_no_pyqt_in_data_modules` | 1 | none of the 3 data modules import PyQt6 |

**Full suite result after Group 17O: 2014 pass / 5 skip / 0 fail**

---

### Group 17O UAT Remediation — DEF-17O-UAT-001/002/003 (2026-06-25)

**New test file:** `tests/test_group17o_uat_defects.py` — 23 tests

| Class | Count | Coverage |
|-------|-------|----------|
| `TestDef17OUAT001RefPathAttribute` | 6 | Controller has no `_ref_path`; correct attribute is `_last_build_result.reference_path`; station map builds from ref path; `has_map=True`; None/empty → no map |
| `TestDef17OUAT002OverlayFiltering` | 9 | `_TELEMETRY_OVERLAY_SEG_TYPES` defined; GEAR_ZONE, LIMITER_ZONE, FUEL_SAVING_CANDIDATE, KERB_OR_BUMP_CANDIDATE in set; geometry types NOT in set; filtering removes overlays; review result filtering; count calculation |
| `TestDef17OUAT003DaytonaCornerCount` | 8 | seed=12 → 12 seeded corners; station map authoritative over detection count; placeholders fill gap; 12 corner labels in draw data; status text includes count; detection result count can differ from station map |

**Defects fixed in `ui/dashboard.py`:**
- DEF-17O-UAT-001: `_tm_try_build_station_map()` now accepts optional `ref_path` param; when None, reads `ctrl._last_build_result.reference_path` (not the non-existent `ctrl._ref_path`)
- DEF-17O-UAT-001 (disk path): `_tm_detect_segments_safe()` disk-load branch now also loads saved reference path and builds station map if not already built
- DEF-17O-UAT-002: Added `_TELEMETRY_OVERLAY_SEG_TYPES` frozenset; after `_create_seg_review()`, filters `review.segments` to geometry types only; segment count label shows geometry-only count
- DEF-17O-UAT-003: Summary labels now prefer station map corner counts when `_tm_station_map` is available; shows `"{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated"`

**New imports added to `ui/dashboard.py`:**
- `import_reference_path_json as _import_ref_path` from `data.track_calibration`
- `TrackSegmentType as _TrackSegmentType` from `data.track_segment_detection`

**Full suite result after Group 17O UAT Remediation Round 1: 2037 pass / 5 skip / 0 fail**

---

### Group 17O UAT Remediation Round 2 — DEF-17O-UAT-004/005/006/007/008 (2026-06-25)

**Updated test file:** `tests/test_group17o_uat_defects.py` — 40 tests (+17 new)

| Class | Count | Coverage |
|-------|-------|----------|
| `TestDef17OUAT002OverlayFiltering` | 10 (+1) | Added `test_braking_and_traction_zones_are_overlay`; reclassified BRAKING_ZONE/TRACTION_ZONE as car-specific overlays (Porsche RSR warnings); updated `test_geometry_types_not_in_overlay_set` and `test_review_segment_filtering_preserves_geometry` |
| `TestDef17OUAT004StationMapCountDisplay` | 3 | Station count non-zero; count formatted in label with "Map:" prefix; station count != reference path point count (different metrics) |
| `TestDef17OUAT005SeedLookupFix` | 5 | `TrackSeedLoadResult` has no `.layouts`; has `.track_locations`; `get_selected_layout()` navigates nested structure; returns None on wrong IDs; full pipeline test (get_selected_layout → SimpleNamespace → build_track_station_map with 12 corners) |
| `TestDef17OUAT007MapDisplayFix` | 2 | Seed lookup succeeds → draw data `has_map=True`, 12 corner labels; no seed → draw data still `has_map=True` |
| `TestDef17OUAT008StationMapPersistence` | 6 | export creates .json file; import roundtrip preserves station count; import roundtrip preserves 12 corners; find_station_map_path returns path after export; returns None when not exported; imported map produces valid draw data with 12 corner labels |

**Defects fixed in `ui/dashboard.py`:**
- DEF-17O-UAT-005/007 (CRITICAL seed bug): `_tm_try_build_station_map()` — replaced `for layout in self._tm_seed_result.layouts:` (AttributeError: `TrackSeedLoadResult` has `.track_locations` not `.layouts`) with `get_selected_layout(self._tm_seed_result, loc_id, lay_id)`; also reads `loc_id` from location combo (was missing)
- DEF-17O-UAT-006: Added `_TrackSegmentType.BRAKING_ZONE` and `_TrackSegmentType.TRACTION_ZONE` to `_TELEMETRY_OVERLAY_SEG_TYPES` — both carry "Car-specific — Porsche RSR" warnings and are NOT universal track geometry
- DEF-17O-UAT-004: After successful station map build in `_tm_try_build_station_map()`, updates `_tm_lbl_build_info` to show `"Path: N pts | Conf: X | Map: N stations / N corners"` instead of path-only
- DEF-17O-UAT-008 (persistence): `_tm_try_build_station_map()` now calls `_export_station_map()` after each build (best-effort, silent on failure); added `_tm_try_load_station_map_from_disk(loc_id, lay_id)` called from `_tm_on_layout_changed()` — auto-loads saved station map from `data/track_models/` when layout is selected
- Turn column: `_tm_refresh_seg_table()` now matches each segment to the nearest `SeededCorner` by `lap_progress_mid` (< 15% threshold) when `turn_number` is None — populates Turn column for non-apex segments (braking, entry, exit, corner_exit) from station map corner IDs

**New imports added to `ui/dashboard.py`:**
- `export_station_map_json as _export_station_map`, `import_station_map_json as _import_station_map`, `find_station_map_path as _find_station_map_path` from `data.track_station_map`

**Full suite result after Group 17O UAT Remediation Round 2: 2054 pass / 5 skip / 0 fail**

---

### Group 17H — Track Intelligence AI Prompt Integration (2026-06-24)

**New module:** `strategy/track_context_prompt.py`

**Public function:**
- `get_track_context_for_ai(track_location_id, layout_id) -> str`
  - Missing/empty IDs: returns `"Track Intelligence unavailable: no selected track/layout was provided."`
  - Present: delegates to `build_resolved_track_context_for_prompt()` from `data.track_model_resolver`
  - Resolver exception: returns safe error note with exception class and message; never raises

**`strategy/ai_planner.py` changes:**
- `RaceParams.track_location_id: str = ""` and `RaceParams.layout_id: str = ""` new optional fields
- `_build_race_prompt(track_context="")` — injects section before `## Practice lap times`
- `_build_practice_prompt(track_context="")` — injects section before `## Practice lap times`
- `_build_setup_from_scratch_prompt(track_context="")` — injects section after race conditions block
- `build_car_setup(track_location_id="", layout_id="")` — calls `get_track_context_for_ai()`, passes context to prompt builder; adds `track_context_included`, `track_location_id`, `layout_id` to `structured_payload`
- `analyse_strategy()` — resolves context from `params.track_location_id/layout_id`; adds debug metadata to `structured_payload`; adds "Track Intelligence unavailable" to `_warnings` when IDs missing
- `analyse_practice_session()` — same

**`strategy/driving_advisor.py` changes:**
- `DrivingAdvisor._get_track_intelligence_context()` — reads from `config["strategy"]["track_location_id"/"layout_id"]`; calls `get_track_context_for_ai()`; never raises
- `_build_coaching_prompt()` — `track_intel_block` prepended in `extra_sections`
- `_build_setup_prompt()` — same
- `_build_combined_prompt()` — same

**`ui/dashboard.py` changes:**
- `_tm_on_layout_changed()` — stores `loc_id`/`lay_id` to `config["strategy"]["track_location_id"/"layout_id"]`
- `_run_ai_analysis()` — passes `track_location_id`/`layout_id` from config into `RaceParams`
- `_run_practice_analysis()` — same; debug print updated with track context presence info
- `_run_build_setup()` — reads `_track_loc_id`/`_layout_id_build` from config; passes to `build_car_setup()`

**Context injection summary:**
- Missing IDs → "Track Intelligence unavailable" note in every AI prompt
- Seed-only → seed context + "seed data only — NOT validated" warning
- Not AI-ready → reviewed segments + blockers + explicit "NOT AI-READY" caveat
- AI-ready → full segment summary + confirmed list + Porsche boundary note
- Engineer-validated → same as AI-ready but with "Engineer-validated" source label

**Deferred:**
- Live current-segment lookup
- Telemetry-to-segment issue enrichment
- Wiring `layout_id` from Event Planner (currently only from Track Modelling tab selection)
- `_build_feeling_prompt` track context injection
- Track auto-detection from telemetry

**Test coverage (56 tests, 16 test classes):**
- `TestGetTrackContextMissingIds` — 6 tests: None loc, None layout, empty loc, empty layout, both None, returns string
- `TestGetTrackContextCallsResolver` — 3 tests: resolver called when IDs present, receives exact IDs, real seed returns section
- `TestGetTrackContextErrorSafety` — 4 tests: RuntimeError, ImportError, error returns string, does not raise
- `TestRaceParamsFields` — 5 tests: default empty, default empty, set loc, set layout, both coexist
- `TestBuildRacePromptTrackContext` — 3 tests: injected when provided, no crash when empty, before practice lap times
- `TestBuildPracticePromptTrackContext` — 3 tests: injected, no crash, before practice lap times
- `TestBuildSetupFromScratchTrackContext` — 3 tests: injected, no crash, forwarded via build_car_setup
- `TestAnalyseStrategyTrackContext` — 2 tests: payload true when IDs set, payload false when missing
- `TestAnalysePracticeSessionTrackContext` — 2 tests: payload flag true, flag false when missing
- `TestDrivingAdvisorTrackIntelligence` — 4 tests: warning when no IDs, calls resolver, returns string on error, does not raise
- `TestCoachingPromptTrackIntelligence` — 3 tests: included when IDs set, warning when missing, in extra_sections
- `TestSetupPromptTrackIntelligence` — 3 tests: included when IDs set, warning when missing, combined prompt included
- `TestSeedOnlyContextWarning` — 2 tests: seed includes not-validated warning, missing track returns non-empty string
- `TestMissingLayoutIdSafety` — 2 tests: analyse_strategy no crash, build_car_setup no crash
- `TestBuildCarSetupPayloadDebug` — 2 tests: payload true when IDs set, payload false when missing
- `TestRegressionImports` — 9 tests: 17A–17H importable, RaceParams has new fields, DrivingAdvisor has method, get_track_context returns string

**Tests Run:** 1420 pass / 5 skip / 0 fail (1425 collected)
