# GT7 VR Dashboard — User Acceptance Test Plan

> **Version:** 2.0  
> **Created:** 2026-06-22 (updated 2026-06-22 for Group 6)  
> **Scope:** All defects marked "Fixed — Awaiting Retest" across Groups 1–6 (2026-06-21/22 remediation sessions)  
> **Tester:** Leon Paczynski  
> **Environment:** GT7 running on PS5, dashboard on PC via UDP, GT7_AI_DEBUG=1 set in shell  
> **Prerequisites:** PS5 and PC on same network, GT7 Custom race lobbies enabled, Anthropic API key set  

---

## How to Enable AI Debug Logging

Before testing anything AI-related, launch the app with debug enabled:

```
set GT7_AI_DEBUG=1
python main.py
```

Every AI prompt and response will print to the console and appear in the Debug tab.

---

## Test Sessions Overview

| Session | Tests | Time Estimate | Purpose |
|---------|-------|---------------|---------|
| Smoke Test | SMK-001 – SMK-006 | 15 minutes | Confirms app starts and basic navigation works |
| Full Workflow | WF-001 – WF-023 | 60–90 minutes | End-to-end test of Event → Practice → History → Review |
| AI Prompt Accuracy | AI-001 – AI-011 | 30–45 minutes | Validates every AI input defect is resolved |
| Session Persistence | SP-001 – SP-010 | 20–30 minutes | DB write/read integrity across sessions |
| Live Race Engineer | LRE-001 – LRE-010 | 30–45 minutes | PTT, voice guards, compound display on Live tab |
| Regression Checklist | REG-001 – REG-010 | 15 minutes | Catches unexpected regressions from the remediation work |

**Recommended order:** Smoke → Persistence → Workflow → AI → Live → Regression

---

---

## Section 1 — 15-Minute Smoke Test

*Run first. If any smoke test fails, stop and fix before proceeding.*

---

### SMK-001 — App Launches, Live Tab Is First, No Strategy Loaded

- **Related defects:** PROJECT_STATE.md Live Race Engineer Rules
- **Feature area:** App startup / Live Race Engineer
- **Preconditions:** App not running. Config file exists from a previous session.
- **Steps:**
  1. Launch `python main.py`
  2. Observe which tab is active on startup
  3. Check the strategy / pit window area — no race strategy should be pre-loaded
- **Expected result:** App opens on the Live Race Engineer tab. No race strategy is loaded. No pit window or stint plan visible. Mode selector shows saved mode (Practice or Race).
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of initial state
- **Priority:** P0 — blocker

---

### SMK-002 — PTT Status Label Visible on Live Tab

- **Related defects:** DEF-P4-001
- **Feature area:** Live Race Engineer / PTT
- **Preconditions:** App running, on Live tab
- **Steps:**
  1. Look at the Live tab info row (top row with Gear, Position, Remaining, Session, Mode)
  2. Locate the PTT status label
  3. Confirm it shows "RADIO READY" in green
- **Expected result:** A label showing "RADIO READY" in green is visible in the Live tab top row, to the right of the Mode selector. Label is clearly readable without scrolling or switching tabs.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of Live tab header
- **Priority:** P1

---

### SMK-003 — Active Tyre Compound Label Visible Above Tyre Temps

- **Related defects:** DEF-P3-002
- **Feature area:** Live Race Engineer / Tyre display
- **Preconditions:** App running, on Live tab. An event with a required tyre set and active.
- **Steps:**
  1. In Event Planner, create or select an event with Required Tyre = Racing Medium
  2. Click "Set Active"
  3. Switch to Live tab
  4. Look above the four tyre temperature circles
- **Expected result:** A label shows "Tyre: Racing Medium" above the tyre temp grid. If no event is active or no required tyre is set, label shows "Tyre: —"
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of tyre section on Live tab
- **Priority:** P1

---

### SMK-004 — Session Opens on Mode Selection, Not on First Lap

- **Related defects:** DEF-P1-001
- **Feature area:** Session management / Live tab
- **Preconditions:** PS5 connected, GT7 running in a custom race lobby. App running.
- **Steps:**
  1. Select "Practice" from the Live tab Mode selector
  2. **Before completing any lap**, open DB Browser for SQLite (or run `sqlite3 data/gt7_sessions.db`)
  3. Run: `SELECT id, session_type FROM sessions ORDER BY id DESC LIMIT 1`
- **Expected result:** A session row exists immediately with `session_type = 'practice'` — before any lap has been completed. The session was created when you selected the mode, not when the first lap finished.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result screenshot
- **Priority:** P0 — blocker

---

### SMK-005 — Save Session Does Not Crash

- **Related defects:** DEF-P1-003
- **Feature area:** Practice Review
- **Preconditions:** At least one live lap recorded in Practice mode
- **Steps:**
  1. Complete at least one lap in Practice mode
  2. Switch to Practice Review tab
  3. Confirm at least one lap row is visible in the lap table
  4. Click the "Save Session" button
- **Expected result:** Session saves successfully. No crash. No `AttributeError` in the console. App remains responsive.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Console output (no traceback), app still running
- **Priority:** P0 — blocker

---

### SMK-006 — History Tab Lists Sessions

- **Related defects:** General regression
- **Feature area:** History
- **Preconditions:** At least one saved session in DB
- **Steps:**
  1. Switch to History tab
  2. Confirm sessions are listed
  3. Select one session
  4. Confirm lap count and track/car are shown
- **Expected result:** Sessions appear in the History tab. Selecting a session shows its details. No errors.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of History tab with sessions listed
- **Priority:** P1

---

---

## Section 2 — Full Workflow Test

*Requires GT7 running and an active track session. Run in order.*

---

### WF-001 — Event Planner: Create Timed Race Event

- **Related defects:** DEF-P1-004, DEF-P3-004
- **Feature area:** Event Planner
- **Preconditions:** Event Planner tab accessible
- **Steps:**
  1. Open Event Planner tab
  2. Click "New" to create a new event
  3. Set Name: "UAT Timed Race Test"
  4. Set Track: Suzuka Circuit
  5. Set Race Type: **Timed Race**
  6. Set Duration: 40 minutes
  7. **Observe:** Does the Laps field become greyed out / disabled?
  8. Set Tyre Wear: 1.5x
  9. Set Fuel Multiplier: 2.0x
  10. Set Available Tyres: Racing Medium, Racing Hard
  11. Set Required Tyre: Racing Medium
  12. Click "Save"
- **Expected result:** Event saves. If DEF-P3-004 is fixed: the Laps field is disabled when Timed Race is selected. If not fixed, note this as a known open defect but continue.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (note if Laps field was enabled or disabled):** _______________
- **Evidence:** Screenshot of Event Planner with fields populated
- **Priority:** P1

---

### WF-002 — Event Planner: Create Lap Race Event

- **Related defects:** DEF-P1-004
- **Feature area:** Event Planner
- **Preconditions:** Event Planner accessible
- **Steps:**
  1. Click "New"
  2. Set Name: "UAT Lap Race Test"
  3. Set Race Type: **Lap Race**
  4. Set Laps: 25
  5. **Observe:** Duration field should be disabled (if DEF-P3-004 fixed)
  6. Set Tyre Wear: 1.0x
  7. Set Fuel Multiplier: 1.0x
  8. Click "Save"
- **Expected result:** Event saves correctly. Tyre Wear 1.0x and Fuel Multiplier 1.0x are preserved.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P2

---

### WF-003 — Event Planner: BoP With Tuning Locked

- **Related defects:** DEF-P2-004, DEF-P2-005, DEF-P2-006
- **Feature area:** Event Planner / Setup Builder
- **Preconditions:** "UAT Timed Race Test" event exists
- **Steps:**
  1. Open "UAT Timed Race Test" event in Event Planner
  2. Check the **BoP** checkbox: On
  3. Check **Tuning Allowed**: Off (unchecked)
  4. **Observe:** Does the Tuning Permissions group appear or hide?
  5. Save the event
  6. Click "Set Active"
  7. Switch to Setup Builder tab
  8. **Observe:** Is there a locked banner visible?
  9. **Observe:** Are setup spinboxes (ride height, springs, aero) disabled?
  10. **Observe:** Are the front and rear tyre compound dropdowns still ENABLED?
  11. Check the Race Conditions group: what do BoP and Tuning Allowed labels show?
- **Expected result:**
  - Tuning Permissions group is HIDDEN when Tuning = Off (nothing to configure)
  - Setup Builder shows a locked banner mentioning BoP
  - All setup spinboxes are disabled
  - Tyre compound dropdowns remain enabled (tyres are always free under BoP)
  - Race Conditions shows: BoP = "Yes", Tuning Allowed = "Not Allowed"
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of Setup Builder locked state. Screenshot of Race Conditions group.
- **Priority:** P1

---

### WF-004 — Event Planner: Tuning Permissions Visible Without BoP

- **Related defects:** DEF-P2-005
- **Feature area:** Event Planner
- **Preconditions:** Any event in Event Planner
- **Steps:**
  1. Open any event
  2. Set BoP: **Off**
  3. Set Tuning Allowed: **On**
  4. **Observe:** Does the Tuning Permissions group appear?
  5. Check "Suspension" and "Brake Balance" in the permissions group
  6. Uncheck Tuning Allowed
  7. **Observe:** Does the Tuning Permissions group hide?
  8. Now check BoP: On, Tuning: On
  9. **Observe:** Group should still appear
- **Expected result:**
  - Tuning Permissions group appears when Tuning=On, regardless of BoP state
  - Tuning Permissions group hides when Tuning=Off
  - BoP alone (without Tuning=On) does NOT show the group
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot showing group visible with BoP=Off, Tuning=On
- **Priority:** P1

---

### WF-005 — Garage: Select Active Car

- **Related defects:** General architecture rule
- **Feature area:** Garage
- **Preconditions:** Car list populated
- **Steps:**
  1. Open Garage tab
  2. Select a car (e.g., a GR3 or GR4 car)
  3. Click "Load to Event" or equivalent button to set the car as active
  4. Switch to Setup Builder
  5. Confirm the car name appears in the Race Conditions / header area
- **Expected result:** Car selection persists and appears in Setup Builder context.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P2

---

### WF-006 — Setup Builder: Race Conditions Read From Event

- **Related defects:** DEF-P2-004, DEF-P2-006
- **Feature area:** Setup Builder
- **Preconditions:** "UAT Lap Race Test" event set active with BoP=Off, Tuning=On
- **Steps:**
  1. Activate "UAT Lap Race Test" with BoP=Off, Tuning=Yes
  2. Switch to Setup Builder
  3. Inspect the Race Conditions group
  4. Confirm there is NO independent BoP checkbox in the Setup Builder form (it should only be in Race Conditions as a read-only label)
- **Expected result:** Race Conditions shows correct data from Event Planner. No standalone BoP checkbox exists in the main Setup Builder form.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of Setup Builder Race Conditions group
- **Priority:** P1

---

### WF-007 — Setup Builder: Partial Tuning Lock (Suspension + Brake Balance Only)

- **Related defects:** DEF-P2-006, DEF-P2-007
- **Feature area:** Setup Builder
- **Preconditions:** Event with BoP=On, Tuning=Yes, Allowed: Suspension + Brake Balance
- **Steps:**
  1. Set event: BoP=On, Tuning=On, Allowed Tuning = Suspension + Brake Balance
  2. Set Active
  3. Switch to Setup Builder
  4. **Observe:** Ride height, springs, dampers, ARB, camber, toe, brake balance — should be ENABLED
  5. **Observe:** Aero (front/rear downforce), LSD, gear ratios, ECU — should be DISABLED
  6. **Observe:** Tyre compound dropdowns — should be ENABLED
  7. Try clicking a disabled field — it should not respond
- **Expected result:** Only suspension and brake balance fields are interactive. All other mechanical fields are disabled. Tyre dropdowns remain active.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot showing mixed enabled/disabled state
- **Priority:** P1

---

### WF-008 — Setup Builder: Brake Balance Step = 1

- **Related defects:** DEF-P3-001
- **Feature area:** Setup Builder
- **Preconditions:** Setup Builder open, brake balance spinbox visible
- **Steps:**
  1. Locate the Brake Bias / Brake Balance spinbox
  2. Note the current value (e.g., 0)
  3. Click the up arrow once
  4. Note the new value
  5. Click the down arrow once
  6. Note the value again
- **Expected result:** Each click changes the value by exactly 1. Up: 0 → 1. Down: 1 → 0.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (actual step size observed):** _______________
- **Evidence:** None required
- **Priority:** P2

---

### WF-009 — Setup Builder: Tyre Dropdowns Always Enabled Under BoP

- **Related defects:** DEF-P2-006, SUP-008
- **Feature area:** Setup Builder
- **Preconditions:** Event with BoP=On, Tuning=Off (fully locked)
- **Steps:**
  1. Set an event: BoP=On, Tuning=No, set active
  2. Switch to Setup Builder
  3. Confirm the locked banner is visible
  4. Confirm suspension/aero spinboxes are disabled
  5. Locate the front and rear tyre compound dropdowns
  6. Try opening the front tyre dropdown
- **Expected result:** Tyre compound dropdowns are enabled and interactive even when all other tuning is locked. The locked banner does not reference tyres.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P1

---

### WF-010 — Practice Session: Session Opens on Mode Selection

- **Related defects:** DEF-P1-001
- **Feature area:** Session management
- **Preconditions:** PS5 connected, GT7 in a practice lobby. App open.
- **Steps:**
  1. Switch Live tab to **Practice** mode
  2. **Immediately** (without driving), open a terminal and run:
     `sqlite3 data/gt7_sessions.db "SELECT id, session_type, created_at FROM sessions ORDER BY id DESC LIMIT 1"`
  3. Note the result
- **Expected result:** A session row exists with `session_type = 'practice'` even though no lap has been completed. The `created_at` timestamp matches the time you changed the mode.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result
- **Priority:** P0

---

### WF-011 — Practice Session: Outlap Recorded and Labelled

- **Related defects:** DEF-P1-002
- **Feature area:** Practice session recording
- **Preconditions:** In a practice session in Practice mode. Complete a pit stop to generate an outlap.
- **Steps:**
  1. Drive into the pit lane during a practice session
  2. Serve the pit stop
  3. Exit the pits and complete the outlap (drive to the start/finish line)
  4. Switch to Practice Review tab
  5. Find the outlap row in the lap table
  6. Run DB query: `SELECT lap_num, is_out_lap, lap_time_ms FROM lap_records ORDER BY id DESC LIMIT 5`
- **Expected result:**
  - Outlap row is visible in Practice Review with a distinct visual style (dark green background or "OL" label)
  - DB shows `is_out_lap = 1` for the outlap row
  - Outlap is NOT silently discarded
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of Practice Review lap table showing outlap row. DB query result.
- **Priority:** P1

---

### WF-012 — Practice Review: Outlap Excluded From Summary

- **Related defects:** DEF-P2-011
- **Feature area:** Practice Review / Session Summary
- **Preconditions:** At least one outlap and 3+ normal laps recorded in Practice Review
- **Steps:**
  1. Note the outlap time (e.g., 1:55.2 — slower than race pace)
  2. Note the lap times for all non-outlap laps
  3. Manually calculate: best lap from non-outlap laps, average of non-outlap laps
  4. Compare with the Session Summary displayed above or beside the lap table
- **Expected result:**
  - Session Summary best lap = fastest non-outlap lap time
  - Session Summary average = average of non-outlap laps only
  - Total laps count includes the outlap
  - Outlap time does not appear in best or average fields
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (manual calc vs displayed):** _______________
- **Evidence:** Screenshot of Session Summary alongside lap table
- **Priority:** P1

---

### WF-013 — Practice Review: Tyre Compound Inherits From Previous Lap

- **Related defects:** DEF-P3-003
- **Feature area:** Practice Review
- **Preconditions:** 6+ laps in Practice Review. Compound set on one lap.
- **Steps:**
  1. In the Practice Review lap table, find lap 4
  2. Change its compound to "Racing Hard" using the compound dropdown
  3. Complete lap 5 during a live session (or load a new lap from History)
  4. Observe the compound shown for lap 5
- **Expected result:** Lap 5's compound initialises to "Racing Hard" (inherited from lap 4), not the default compound.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of laps 4 and 5 showing compound columns
- **Priority:** P2

---

### WF-014 — Practice Mode: Pit and Fuel Alerts Suppressed

- **Related defects:** DEF-P2-002
- **Feature area:** Voice / Live mode guard
- **Preconditions:** Live mode = Practice. Voice/TTS enabled.
- **Steps:**
  1. Confirm Live tab shows "Practice" mode
  2. Drive until fuel drops below the low-fuel threshold (typically < 3–4 laps remaining)
  3. Listen for a fuel-low voice alert
  4. Drive into the pit lane entry zone
  5. Listen for any pit advice voice alert
- **Expected result:** No fuel-low announcement. No pit box advice announcement. Voice system is otherwise active (lap time announcements should still occur if configured).
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (any unexpected alerts heard):** _______________
- **Evidence:** Audio recording or console log showing no _on_fuel_low or _on_pit events fired
- **Priority:** P1

---

### WF-015 — Practice Mode: No Race-Finished Announcement

- **Related defects:** DEF-P1-008, DEF-P2-QRF
- **Feature area:** Voice / Session mode guard
- **Preconditions:** Timed event active (e.g., 40-minute race). Live mode = Practice.
- **Steps:**
  1. Activate "UAT Timed Race Test" (40 minutes, Timed Race)
  2. Set Live tab to **Practice**
  3. Drive for 40+ minutes (or set a very short timed event, e.g., 1 minute, for faster testing)
  4. When the event timer would expire, listen for a "Race finished" voice announcement
  5. Observe the Debug tab for RACE_FINISHED events
- **Expected result:** No "Race finished" announcement. No RACE_FINISHED event in the Debug log during Practice mode. App continues in practice normally after the timed duration passes.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Debug tab screenshot showing no RACE_FINISHED during practice
- **Priority:** P1

---

### WF-016 — History Tab: Session Visible After Practice

- **Related defects:** DEF-P1-001 (session must exist for History to show it)
- **Feature area:** History
- **Preconditions:** Completed at least one lap in Practice mode, saved the session
- **Steps:**
  1. Switch to History tab
  2. Look for the most recent session (should be "Practice" type)
  3. Confirm it shows the correct track, car, session type, and lap count
- **Expected result:** The practice session appears in History with session_type = Practice. Lap count matches the number of laps completed.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of History tab entry
- **Priority:** P1

---

### WF-017 — History Reload: All Fields Preserved

- **Related defects:** DEF-P2-013 (pit flag), DEF-P2-014 (fuel start/end), DEF-P1-006 (compound)
- **Feature area:** History → Practice Review
- **Preconditions:** A session exists in History with at least one pit lap and known fuel values
- **Steps:**
  1. In History tab, select a session that contains a pit stop
  2. Click "Load to Practice Review" (or equivalent)
  3. Switch to Practice Review
  4. For the pit stop lap, confirm:
     a. The Pit column shows "Yes" with amber background
     b. Fuel Start shows a non-zero value
     c. Fuel End shows a non-zero value
     d. Compound column shows the correct compound
  5. For a normal lap, confirm:
     a. Pit column is blank
     b. Fuel Start and Fuel End are populated
- **Expected result:** All fields are fully populated after reload. No "—" placeholders for fuel, compound, or pit status where real data exists.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (list any blank fields that should have data):** _______________
- **Evidence:** Screenshot of Practice Review after reload, showing pit lap row
- **Priority:** P1

---

### WF-018 — Practice Review: Session Summary Recalculates After Reload

- **Related defects:** DEF-P3-006
- **Feature area:** Practice Review / Session Summary
- **Preconditions:** A session with 10+ laps loaded from History
- **Steps:**
  1. Load a 10-lap session from History into Practice Review
  2. Observe the Session Summary group (Best Lap, Avg Lap, Avg Fuel/Lap, Laps)
  3. Manually calculate: best lap, average of all non-outlap laps, average fuel
  4. Compare manual values to the displayed summary
- **Expected result:** Session Summary updates immediately after load. Values match manual calculation within rounding. Summary does not show stale values from a previous live session or remain blank.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (manual best vs displayed best):** _______________
- **Evidence:** Screenshot of Session Summary after load
- **Priority:** P1

---

### WF-019 — Practice Review: Outlap Not Counted as Best Lap After Reload

- **Related defects:** DEF-P2-011
- **Feature area:** Practice Review / Session Summary
- **Preconditions:** A session with an outlap loaded from History
- **Steps:**
  1. Load a session that contains an outlap (labelled "OL" or dark green row)
  2. Identify the outlap's lap time
  3. Identify the fastest normal lap
  4. Read the Session Summary Best Lap field
- **Expected result:** Best Lap field shows the fastest non-outlap lap time. Outlap (which is typically slower) is excluded from the calculation.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot
- **Priority:** P1

---

### WF-020 — Practice Review: Save Session Doesn't Crash

- **Related defects:** DEF-P1-003
- **Feature area:** Practice Review
- **Preconditions:** Laps visible in Practice Review table (either live or loaded from History)
- **Steps:**
  1. With at least one lap in the Practice Review table, click "Save Session"
  2. Monitor the console for any AttributeError or traceback
  3. Verify the app remains responsive
- **Expected result:** Session saves silently. No `AttributeError: 'MainWindow' object has no attribute '_lbl_bank_status'`. No other crash. App responsive.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Console output (clean)
- **Priority:** P0

---

### WF-021 — Strategy Builder: Removed Spinboxes Absent

- **Related defects:** SUP-006, SUP-007
- **Feature area:** Strategy Builder
- **Preconditions:** Strategy Builder tab accessible
- **Steps:**
  1. Open Strategy Builder tab
  2. Inspect the AI Analysis group
  3. Confirm there is NO pit loss spinbox
  4. Confirm there is NO lap tolerance spinbox
  5. Confirm there is NO fuel tolerance spinbox
  6. Confirm there is NO manual fuel burn input spinbox
- **Expected result:** None of these spinboxes exist. Strategy Builder uses event config values silently.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P2

---

### WF-022 — Practice Review: Driver Feedback Form Visible at Bottom (DEF-P2-010)

- **Related defects:** DEF-P2-010
- **Feature area:** Practice Review / Driver Feedback
- **Preconditions:** App running. Practice Review tab accessible.
- **Steps:**
  1. Switch to the **Practice Review** tab
  2. Scroll to the bottom of the tab
  3. Look for a group box titled "Driver Feedback — After Stint" (or similar)
  4. Confirm the group contains combo-box rows (e.g., Corner Entry, Mid-Corner, Exit Stability, Rear Braking, Tyre Condition, Fuel Use)
  5. Confirm there is a Submit button
  6. Now switch to the **Setup Builder** tab
  7. Scroll through the entire Setup Builder — look for any "Driver Feedback" group
- **Expected result:**
  - Practice Review contains the "Driver Feedback — After Stint" group with all combo selectors and a Submit button
  - Setup Builder does NOT contain any "Driver Feedback" group
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (which combos are visible in Practice Review):** _______________
- **Evidence:** Screenshot of Practice Review bottom showing feedback form. Screenshot of Setup Builder confirming no feedback form.
- **Priority:** P1

---

### WF-023 — Event Planner: Race Type Mutual Exclusivity (DEF-P3-004)

- **Related defects:** DEF-P3-004
- **Feature area:** Event Planner
- **Preconditions:** Event Planner open with a new or existing event
- **Steps:**
  1. Open Event Planner, create or open any event
  2. Select **Timed Race** from the Race Type dropdown
  3. **Observe:** Is the Laps field greyed out / disabled?
  4. Select **Lap Race** from the Race Type dropdown
  5. **Observe:** Is the Duration field greyed out / disabled?
  6. Set Duration to 40 minutes when Timed Race is selected
  7. Set Laps to 25 when Lap Race is selected
  8. Save the event
- **Expected result:**
  - Timed Race selected → Laps field is disabled (greyed out)
  - Lap Race selected → Duration field is disabled (greyed out)
  - Switching race type also enables the previously disabled field
  - Saved event stores the correct type-specific value (duration or laps) without confusion
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (field states observed):** _______________
- **Evidence:** Screenshot of Event Planner with Timed Race selected (Laps greyed) and again with Lap Race selected (Duration greyed)
- **Priority:** P2

---

---

## Section 3 — AI Prompt Accuracy Test

*Requires GT7_AI_DEBUG=1 set. Each test requires checking console or Debug tab output.*

---

### AI-001 — Timed Race Type in AI Prompt

- **Related defects:** DEF-P1-004
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** "UAT Timed Race Test" event active (40-minute timed race). 5+ laps in Practice Review with fuel data.
- **Steps:**
  1. Activate "UAT Timed Race Test" (40-minute, Timed Race)
  2. Load or complete 5+ practice laps with valid compound and fuel data
  3. Run Practice Analysis
  4. In the Debug tab or console, find the prompt section
  5. Search for "Race length" or "Race duration" in the prompt
- **Expected result:** Prompt contains **"Race duration: 40 minutes"** and **"Timed Race"**. Prompt does NOT contain "Race length: 1 laps" or any other lap count for a timed race.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (exact text found in prompt):** _______________
- **Evidence:** Console/Debug tab showing the prompt section
- **Priority:** P0

---

### AI-002 — Lap Race Type in AI Prompt

- **Related defects:** DEF-P1-004
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** "UAT Lap Race Test" active (25 laps). 5+ practice laps with fuel data.
- **Steps:**
  1. Activate "UAT Lap Race Test" (25 laps, Lap Race)
  2. Complete or load 5+ practice laps
  3. Run Practice Analysis
  4. Search for race type in prompt
- **Expected result:** Prompt contains **"Race length: 25 laps"** (not "1 laps"). No "Timed Race" mention.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (exact text):** _______________
- **Evidence:** Console prompt output
- **Priority:** P1

---

### AI-003 — Tyre Wear Multiplier in AI Prompt

- **Related defects:** DEF-P2-012
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** "UAT Timed Race Test" active with Tyre Wear = 1.5x
- **Steps:**
  1. Confirm the active event has Tyre Wear = 1.5x
  2. Run Practice Analysis
  3. Search for "tyre wear" in the prompt output
- **Expected result:** Prompt contains "1.5× faster" or "tyre wear multiplier: 1.5" — not "2.0×" or "1.0×". If Tyre Wear = 1.0x, prompt must say "Tyre wear rate is the same as in practice."
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (exact value in prompt):** _______________
- **Evidence:** Console prompt output
- **Priority:** P1

---

### AI-004 — Compound Lap Counts Match Practice Review Table

- **Related defects:** DEF-P1-006
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** 15 laps tagged as Racing Medium, 7 laps as Racing Soft in Practice Review
- **Steps:**
  1. In Practice Review, set compound for 15 laps to "Racing Medium" and 7 laps to "Racing Soft"
  2. Verify the compound dropdowns visually
  3. Run Practice Analysis
  4. Find `lap_data_by_compound` in the prompt or search for "Racing Medium" in the compound section
- **Expected result:** Prompt shows **RM: 15 laps, RS: 7 laps** (or equivalent labels). Numbers must match exactly what is visible in the Practice Review table, not the inverse.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (values found in prompt):** _______________
- **Evidence:** Screenshot of Practice Review compound columns + console prompt showing compound counts
- **Priority:** P0

---

### AI-005 — Fuel Burn Source Consistency

- **Related defects:** DEF-P1-007, DEF-P2-009
- **Feature area:** Fuel burn / Strategy Builder
- **Preconditions:** 10 historical laps loaded from History, averaging ~4.2 L/lap (visible in the fuel column)
- **Steps:**
  1. Load a session with 10 laps where Fuel Used column averages ~4.2 L/lap
  2. Manually calculate: `sum of fuel used / number of non-pit laps`
  3. Observe Strategy Builder Fuel Burn Auto display
  4. Run Practice Analysis; find `fuel_burn` in prompt
- **Expected result:**
  - Strategy Builder shows ~4.2 L/lap (matching historical laps)
  - Practice Analysis prompt contains `fuel_burn = ~4.2`
  - All three values (manual calc, Strategy Builder, prompt) agree within 0.1 L/lap
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (three values observed):** _______________
- **Evidence:** Screenshot of Strategy Builder fuel display + prompt showing fuel_burn
- **Priority:** P0

---

### AI-006 — BoP Tuning Lock in AI Prompt

- **Related defects:** DEF-P1-005
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** Event with BoP=On, Tuning=No set active. Laps available.
- **Steps:**
  1. Set event: BoP=On, Tuning=No. Set Active.
  2. Run Practice Analysis
  3. Search prompt for "TUNING LOCKED" or equivalent
  4. Confirm setup fields (ride height, spring rate, aero, LSD, gear ratios) are NOT listed as editable values in the setup section
- **Expected result:** Prompt contains a **"## EVENT RULES — TUNING LOCKED"** block. The setup payload does not include suspension, aero, differential, or transmission as editable change targets. AI response should contain no setup change recommendations.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (exact constraint block text found):** _______________
- **Evidence:** Console prompt showing the tuning locked block
- **Priority:** P1

---

### AI-007 — Partial Tuning Restrictions in AI Prompt

- **Related defects:** DEF-P1-005, DEF-P2-007
- **Feature area:** Practice Analysis AI prompt
- **Preconditions:** Event with Tuning=Yes, Allowed = Suspension + Brake Balance
- **Steps:**
  1. Set event: BoP=On, Tuning=Yes, Allowed = Suspension + Brake Balance. Set Active.
  2. Run Practice Analysis
  3. Search prompt for "EVENT TUNING RESTRICTIONS"
  4. Confirm "Allowed: suspension, brake_balance" appears
  5. Confirm "LOCKED: aero, differential, transmission, power..." appears
  6. Confirm AI response recommends suspension/brake changes but NOT aero/LSD/gear changes
- **Expected result:** Prompt contains **"## EVENT TUNING RESTRICTIONS"** block listing Allowed and Locked categories. AI response limits recommendations to allowed categories only.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Console prompt showing restriction block
- **Priority:** P1

---

### AI-008 — AI Output Validation Banner for Locked Field Violations

- **Related defects:** DEF-P2-007
- **Feature area:** Setup Builder AI / Practice Review AI
- **Preconditions:** Event with BoP=On, Tuning=No. Run an AI Setup Analysis that would normally suggest aero/suspension changes.
- **Steps:**
  1. Set event: BoP=On, Tuning=No. Set Active.
  2. In Setup Builder, run AI Setup Analysis
  3. Observe the displayed AI result
  4. If the AI response (despite the constraint block in the prompt) recommends changing downforce or spring rates, check for the amber warning banner
- **Expected result:** If the AI response contains recommendations for locked areas (e.g., "increase rear downforce"), an amber warning banner appears at the top of the AI result with text like "Event Restriction Warning — AI response may recommend changes to locked areas: aero. Review before applying."
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of AI result with or without banner
- **Priority:** P2

---

### AI-009 — Validation Gate Blocks Analysis With No Fuel Data

- **Related defects:** DEF-P2-016
- **Feature area:** Practice Analysis validation
- **Preconditions:** No laps in Practice Review, or all laps have 0 fuel data
- **Steps:**
  1. Clear Practice Review (or start fresh)
  2. Do not load any laps with valid fuel data
  3. Ensure fuel burn shows 0 or is unavailable
  4. Click the Practice Analysis button
  5. Observe result
- **Expected result:** A warning dialog appears listing validation failures (e.g., "No fuel burn data available"). The AI call is NOT made. No prompt appears in the Debug tab for this attempt.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (validation messages shown):** _______________
- **Evidence:** Screenshot of validation warning dialog
- **Priority:** P1

---

### AI-010 — AI Model Is claude-opus-4-8

- **Related defects:** DEF-P4-002
- **Feature area:** AI settings / AI log
- **Preconditions:** AI Log tab accessible. At least one AI call completed.
- **Steps:**
  1. Complete any AI call (Practice Analysis, Setup Analysis, or PTT coaching query)
  2. Switch to the AI Log tab
  3. Find the most recent entry
  4. Read the "Model" field in the log entry
- **Expected result:** Model field shows `"claude-opus-4-8"`. Field must NOT show `"claude-sonnet-4-6"` or any other model unless explicitly overridden in Settings.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (model value seen):** _______________
- **Evidence:** Screenshot of AI Log entry showing model field
- **Priority:** P2

---

### AI-011 — Top Speed Shows "—" or Valid Value, Not 11 km/h (DEF-P2-015)

- **Related defects:** DEF-P2-015
- **Feature area:** Setup Builder Transmission / AI prompt
- **Preconditions:** PS5 connected. Drive at least one full lap in Practice mode with telemetry active.
- **Steps:**
  1. Connect telemetry. Switch to Practice mode on the Live tab.
  2. Drive one complete lap.
  3. Switch to **Setup Builder → Transmission** group.
  4. Locate the **Top Speed** field (a spinbox).
  5. Note the value — it should either show "—" (dash) or a realistic value ≥ 120 km/h.
  6. With GT7_AI_DEBUG=1, run **Practice Analysis** (or Setup Analysis).
  7. In the Debug tab or console, search the prompt for "top_speed", "transmission_max_speed_kmh", or "11 km/h".
- **Expected result:**
  - The Top Speed spinbox shows either "—" (no valid capture yet) or a value ≥ 120 km/h
  - The spinbox does NOT show "11 km/h" or any value < 50 km/h
  - The AI prompt does NOT contain "11 km/h" for the top speed field
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (value shown in Top Speed spinbox, value in AI prompt if present):** _______________
- **Evidence:** Screenshot of Setup Builder Top Speed field. Console prompt output if running AI.
- **Priority:** P1

---

---

## Section 4 — Session Persistence Test

*DB-level verification. Run queries directly against `data/gt7_sessions.db`.*

---

### SP-001 — Practice Laps Written With session_type = 'practice'

- **Related defects:** DEF-P2-001
- **Feature area:** Session management / lap recording
- **Preconditions:** 3 laps completed with Live mode = Practice
- **Steps:**
  1. Complete 3 laps in Practice mode
  2. Run: `SELECT session_type FROM lap_records ORDER BY id DESC LIMIT 3`
- **Expected result:** All 3 rows return `session_type = 'practice'`. No row shows `'race'`.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result
- **Priority:** P0

---

### SP-002 — Session Row Created Before First Lap

- **Related defects:** DEF-P1-001
- **Feature area:** Session management
- **Preconditions:** Mode set to Practice, no laps completed yet
- **Steps:**
  1. Set Live tab to Practice
  2. Immediately run: `SELECT id, session_type, created_at FROM sessions ORDER BY id DESC LIMIT 1`
- **Expected result:** A session exists immediately. `session_type = 'practice'`. Timestamp is within a few seconds of when you changed mode.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result
- **Priority:** P0

---

### SP-003 — Outlap Written With is_out_lap = 1

- **Related defects:** DEF-P1-002
- **Feature area:** Lap recording
- **Preconditions:** A pit stop completed in Practice mode, outlap driven
- **Steps:**
  1. Complete a pit stop and outlap in Practice mode
  2. Run: `SELECT lap_num, is_out_lap, lap_time_ms FROM lap_records ORDER BY id DESC LIMIT 5`
- **Expected result:** The outlap row has `is_out_lap = 1`. Its `lap_time_ms` is non-zero. The outlap was not discarded.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result
- **Priority:** P1

---

### SP-004 — Fuel Start and End Persisted to DB

- **Related defects:** DEF-P2-014
- **Feature area:** Lap persistence
- **Preconditions:** 3+ laps completed in Practice mode
- **Steps:**
  1. Complete 3 laps
  2. Run: `SELECT lap_num, fuel_start, fuel_end, fuel_used FROM lap_records ORDER BY id DESC LIMIT 3`
- **Expected result:** `fuel_start` and `fuel_end` are non-zero for all three rows. `fuel_used = fuel_start - fuel_end` (approximately). No zero or NULL values.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (any zeroes found):** _______________
- **Evidence:** DB query result
- **Priority:** P1

---

### SP-005 — Pit Stop Flag Preserved After Reload

- **Related defects:** DEF-P2-013
- **Feature area:** Session reload
- **Preconditions:** A session with a pit lap exists and was loaded from History
- **Steps:**
  1. Load a session from History that contains a pit stop
  2. In Practice Review, find the pit lap row
  3. Confirm the Pit column shows "Yes" with amber background
  4. Run: `SELECT lap_num, is_pit_lap FROM lap_records WHERE session_id = [your session id]`
- **Expected result:** Practice Review shows "Yes" for the pit lap. DB has `is_pit_lap = 1` for that lap.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshot of Practice Review + DB query
- **Priority:** P1

---

### SP-006 — Compound Persisted and Restored After Reload

- **Related defects:** DEF-P1-006 (reload path)
- **Feature area:** Session reload
- **Preconditions:** Laps with known compounds saved and reloaded from History
- **Steps:**
  1. Complete 3 laps on "Racing Medium" in Practice mode
  2. Save session
  3. Reload from History
  4. Confirm compound dropdowns in Practice Review show "Racing Medium"
  5. Run: `SELECT lap_num, compound FROM lap_records ORDER BY id DESC LIMIT 3`
- **Expected result:** All 3 rows show `compound = 'RM'` (or equivalent code). Practice Review dropdowns show the correct compound after reload.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result
- **Priority:** P1

---

### SP-007 — Fuel Burn Consistency Across Sources

- **Related defects:** DEF-P2-009
- **Feature area:** Fuel burn / single source of truth
- **Preconditions:** 5 live laps completed in Practice mode
- **Steps:**
  1. After 5 live laps, note the fuel used per lap shown in the Practice Review table (col 8)
  2. Calculate the manual average: sum of fuel used / 5
  3. Open Strategy Builder and read the Fuel Burn Auto display
  4. Compare
- **Expected result:** Strategy Builder Fuel Burn Auto matches the manual average from Practice Review within ±0.1 L/lap. There is no separate manual override spinbox (removed).
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (manual avg, Strategy Builder value):** _______________
- **Evidence:** None required
- **Priority:** P1

---

### SP-008 — Fuel Formula Uses Percentage Multiplier

- **Related defects:** DEF-P4-003
- **Feature area:** Strategy Engine fuel calculation
- **Preconditions:** Fuel burn established (~3.0 L/lap from live laps). 10 laps remaining in race.
- **Steps:**
  1. With avg fuel = 3.0 L/lap and 10 laps remaining, observe the fuel target in the Strategy Builder or voice response
  2. If using the PTT "fuel check" intent, speak "fuel check" and listen to the response
  3. Expected Balanced target: 3.0 × 10 × 1.05 = **31.5 L**
  4. Compare with actual displayed/spoken value
- **Expected result:** Fuel target = 31.5 L (for Balanced strategy). If Safe: 32.4 L. If Aggressive: 30.6 L. Target is NOT `3.0 × (10 + 2) = 36 L` (the old additive formula).
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (actual value, formula used):** _______________
- **Evidence:** Voice response or Strategy Builder fuel target display
- **Priority:** P2

---

### SP-009 — Switching Modes Opens a New Session

- **Related defects:** DEF-P1-001
- **Feature area:** Session management
- **Preconditions:** In Practice mode with an open session
- **Steps:**
  1. Note the current session ID from DB
  2. Switch Live tab from Practice to **Race**
  3. Run: `SELECT id, session_type FROM sessions ORDER BY id DESC LIMIT 2`
- **Expected result:** A NEW session row appears with `session_type = 'race'`. The previous practice session ID is still there. Two separate rows exist.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** DB query result showing two separate session rows
- **Priority:** P1

---

### SP-010 — Driver Feedback Written to DB With Correct Session ID (DEF-P2-010)

- **Related defects:** DEF-P2-010
- **Feature area:** Driver feedback persistence
- **Preconditions:** A live session is open (select Practice mode and complete at least one lap so `_session_id > 0`).
- **Steps:**
  1. Select **Practice** mode on the Live tab. Note the session ID: `SELECT id FROM sessions ORDER BY id DESC LIMIT 1`
  2. Complete at least one lap so the session is active
  3. Switch to **Practice Review** tab
  4. In the "Driver Feedback — After Stint" form, set:
     - Corner Entry: Too much oversteer (or any non-default option)
     - At least one other combo to a non-default value
  5. Click **Submit Feedback**
  6. Run: `SELECT id, session_id, submitted_at FROM driver_feedback ORDER BY id DESC LIMIT 1`
- **Expected result:**
  - A row is inserted into `driver_feedback`
  - `session_id` matches the active session ID noted in step 1 (NOT 0)
  - `submitted_at` timestamp is recent (within the last few minutes)
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (active session_id, session_id in driver_feedback):** _______________
- **Evidence:** DB query result showing `session_id > 0` matching the active session
- **Priority:** P1

---

---

## Section 5 — Live Race Engineer Test

*Requires PS5 connected and GT7 running. Some tests require actual driving.*

---

### LRE-001 — PTT Status Visible on Live Tab

- **Related defects:** DEF-P4-001
- **Feature area:** Live tab / PTT
- **Preconditions:** App running on Live tab
- **Steps:**
  1. Look at the Live tab info row
  2. Confirm "RADIO READY" label is visible (green, in the header row)
  3. Press the PTT key
  4. Observe the label change
  5. After recording, observe label cycle through TRANSMITTING → PROCESSING → (ENGINEER RESPONDING) → RADIO READY
- **Expected result:** All four PTT status states are visible on the Live tab WITHOUT switching to the Settings tab. Label colour changes: green (RADIO READY), amber (TRANSMITTING), yellow (PROCESSING), blue (ENGINEER RESPONDING).
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes (which states were observed):** _______________
- **Evidence:** Screenshots of at least two different PTT states on Live tab
- **Priority:** P1

---

### LRE-002 — PTT Works in Practice Mode

- **Related defects:** DEF-P2-008
- **Feature area:** PTT / voice
- **Preconditions:** Live tab = Practice. Voice backend configured. Microphone working.
- **Steps:**
  1. Switch to **Practice** mode
  2. Press the PTT key
  3. Speak a coaching question (e.g., "how am I doing?" or "what should I work on?")
  4. Wait for response
  5. Check Debug tab for PTT status transitions
- **Expected result:** PTT triggers correctly in Practice mode. Status goes TRANSMITTING → PROCESSING → ENGINEER RESPONDING (if AI returns response) → RADIO READY. An AI response is spoken. No error or silent failure.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Debug tab showing PTT status transitions
- **Priority:** P1

---

### LRE-003 — PTT Works in Qualifying Mode

- **Related defects:** DEF-P2-008
- **Feature area:** PTT / voice
- **Preconditions:** Live tab = Qualifying. Voice configured.
- **Steps:**
  1. Switch to **Qualifying** mode
  2. Press PTT
  3. Speak a strategy question (e.g., "what's my pace?")
  4. Observe response
- **Expected result:** PTT works identically in Qualifying as in Practice and Race.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P2

---

### LRE-004 — PTT Works in Race Mode

- **Related defects:** DEF-P2-008
- **Feature area:** PTT / voice
- **Preconditions:** Live tab = Race. Voice configured. In an active race session.
- **Steps:**
  1. Switch to **Race** mode
  2. Press PTT during a race lap
  3. Ask a strategy question (e.g., "when should I pit?")
  4. Observe response
- **Expected result:** PTT triggers and returns a strategy response. Status transitions visible on Live tab.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P1

---

### LRE-005 — No Race-Finished Announcement in Practice Mode

- **Related defects:** DEF-P1-008
- **Feature area:** Voice / mode guard
- **Preconditions:** A timed event active. Live mode = Practice. Drive for the full event duration.
- **Steps:**
  1. Set event = 1-minute timed race (for fast testing). Set Active.
  2. Switch to **Practice**
  3. Drive for 90+ seconds (past the 1-minute mark)
  4. Listen for a "Race finished" announcement
  5. Check Debug tab for RACE_FINISHED events
- **Expected result:** No "Race finished" spoken. No RACE_FINISHED in Debug log during Practice.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Debug tab screenshot showing absence of RACE_FINISHED
- **Priority:** P0

---

### LRE-006 — No Race-Finished Announcement in Qualifying Mode

- **Related defects:** DEF-P2-QRF (DEF-P2-017 fixed)
- **Feature area:** Voice / mode guard
- **Preconditions:** Timed event active. Live mode = Qualifying. Drive for full duration.
- **Steps:**
  1. Set 1-minute timed race event active
  2. Switch to **Qualifying**
  3. Drive for 90+ seconds
  4. Listen for a "Race finished" announcement
  5. Check Debug tab
- **Expected result:** No "Race finished" spoken. No RACE_FINISHED in Debug log during Qualifying.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Debug tab screenshot
- **Priority:** P1

---

### LRE-007 — Pit and Fuel Alerts Suppressed in Practice

- **Related defects:** DEF-P2-002
- **Feature area:** Voice / mode guard
- **Preconditions:** Live mode = Practice. Low fuel scenario.
- **Steps:**
  1. Drive until fuel drops very low (< 3 L if possible)
  2. Enter the pit lane
  3. Listen for pit box advice and fuel-low alerts
- **Expected result:** No pit advice spoken. No fuel-low alert spoken.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Console log showing _on_pit / _on_fuel_low did not fire
- **Priority:** P1

---

### LRE-008 — Pit and Fuel Alerts Suppressed in Qualifying

- **Related defects:** DEF-P2-002
- **Feature area:** Voice / mode guard
- **Preconditions:** Live mode = Qualifying. Low fuel.
- **Steps:**
  1. Switch to **Qualifying**
  2. Drive with low fuel / enter pit lane
  3. Listen
- **Expected result:** No pit advice or fuel-low alert in Qualifying mode.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** None required
- **Priority:** P1

---

### LRE-009 — Pit and Fuel Alerts Active in Race Mode

- **Related defects:** DEF-P2-002 (regression — alerts must still work in Race)
- **Feature area:** Voice / mode guard
- **Preconditions:** Live mode = Race. Low fuel and entering pit lane.
- **Steps:**
  1. Switch to **Race** mode
  2. Drive with fuel low
  3. Enter pit lane
  4. Listen for alerts
- **Expected result:** Fuel-low alert IS spoken when fuel drops below threshold in Race mode. Pit box advice IS spoken when entering pits in Race mode. These alerts must not have been accidentally suppressed by the Practice/Qualifying guard fix.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Console log showing _on_pit and _on_fuel_low firing in Race mode
- **Priority:** P1

---

### LRE-010 — Active Tyre Compound Updates on Live Tab

- **Related defects:** DEF-P3-002
- **Feature area:** Live tab / tyre display
- **Preconditions:** Two events with different required tyres
- **Steps:**
  1. Set event A active with Required Tyre = Racing Hard
  2. Switch to Live tab
  3. Observe compound label above tyre temps
  4. Go back to Event Planner
  5. Activate event B with Required Tyre = Racing Medium
  6. Switch to Live tab again
  7. Observe compound label
  8. Switch Live mode from Race to Practice and back
  9. Observe whether label still shows correctly
- **Expected result:**
  - After activating event A: "Tyre: Racing Hard"
  - After activating event B: "Tyre: Racing Medium" (updates without restart)
  - After mode switch: label still correct
  - No event: "Tyre: —"
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________
- **Evidence:** Screenshots of each state
- **Priority:** P1

---

---

## Section 6 — Regression Test Checklist

*Quick checks to catch unexpected regressions from the remediation work. Note Pass/Fail only.*

---

### REG-001 — App Launches Without Errors

- **Related defects:** General
- **Check:** `python main.py` — no ImportError, no AttributeError on startup, no crash within first 30 seconds
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-002 — Telemetry Connection Status

- **Related defects:** General
- **Check:** With GT7 running and Custom Race Lobby active, the telemetry connection indicator shows connected (or similar status). Live data updates (gear, speed, position) are visible on the Live tab.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-003 — Live Lap Counter Increments

- **Related defects:** General
- **Check:** Complete 3 laps in Practice mode. Lap counter on Live tab increments from 1 to 3. Practice Review table adds a row after each lap.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-004 — Tyre Temperatures Update Live

- **Related defects:** General
- **Check:** While driving, the four tyre temperature circles on the Live tab update with changing values. They do not stay at zero or the same value throughout a lap.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-005 — Fuel Bar Updates Live

- **Related defects:** General
- **Check:** While driving, the fuel display on the Live tab decreases over the course of a lap. After a pit stop with fuel added, it increases.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-006 — Event Planner CRUD Works

- **Related defects:** General
- **Check:** Create a new event, save it, reload it, edit one field, save again. Delete it. No crashes or data loss.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-007 — AI Log Tab Shows Entries

- **Related defects:** General / DEF-P4-002
- **Check:** After completing any AI call (Practice Analysis or Setup Analysis), the AI Log tab shows an entry with timestamp, feature name, model, token count, and truncated response. Model field shows `claude-opus-4-8`.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-008 — Debug Tab Shows PTT Events

- **Related defects:** DEF-P2-008
- **Check:** Press PTT key. The Debug tab shows TRANSMITTING, PROCESSING, and RADIO READY status events in sequence. If a transcription error occurs, ERROR is shown with a reason.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-009 — Settings Tab Retains PTT Status Label

- **Related defects:** DEF-P4-001 regression — Settings tab should still work
- **Check:** Switch to Settings tab. PTT status label is still visible there (the Live tab addition should not have removed it from Settings). Press PTT — both Settings and Live tab labels update.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

### REG-010 — History Tab Loads a Session Into Practice Review

- **Related defects:** General / DEF-P3-006
- **Check:** Select a session in History tab. Click "Load to Practice Review" (or equivalent). Switch to Practice Review — laps appear, Session Summary is populated with correct values.
- **Pass:** ☐ &nbsp;&nbsp; **Fail:** ☐
- **Notes:** _______________

---

---

## Defect Sign-Off Matrix

| Defect ID | Description | Test Case IDs | Result | User Sign-Off | Notes |
|-----------|-------------|---------------|--------|---------------|-------|
| DEF-P1-001 | Session opens on mode selection | SMK-004, WF-010, SP-002, SP-009 | ☐ Pass ☐ Fail | | |
| DEF-P1-002 | Outlaps recorded, not discarded | WF-011, SP-003 | ☐ Pass ☐ Fail | | |
| DEF-P1-003 | Save Session no AttributeError crash | SMK-005, WF-020 | ☐ Pass ☐ Fail | | |
| DEF-P1-004 | Timed race type in AI prompt | AI-001, AI-002 | ☐ Pass ☐ Fail | | |
| DEF-P1-005 | BoP tuning lock in AI prompt | AI-006 | ☐ Pass ☐ Fail | | |
| DEF-P1-006 | Compound lap counts match table | AI-004, SP-006 | ☐ Pass ☐ Fail | | |
| DEF-P1-007 | Fuel burn single source of truth | AI-005, SP-007 | ☐ Pass ☐ Fail | | |
| DEF-P1-008 | Practice mode no RACE_FINISHED | WF-015, LRE-005 | ☐ Pass ☐ Fail | | |
| DEF-P2-001 | Practice laps written as 'practice' | SP-001 | ☐ Pass ☐ Fail | | |
| DEF-P2-002 | Pit/fuel alerts silent in Practice + Qualifying | WF-014, LRE-007, LRE-008, LRE-009 | ☐ Pass ☐ Fail | | |
| DEF-P2-003 | Required Tyres is a checkbox grid (register correction) | WF-001 steps 10–11 | ☐ Pass ☐ Fail | | |
| DEF-P2-004 | No independent BoP in Setup Builder | WF-003, WF-006 | ☐ Pass ☐ Fail | | |
| DEF-P2-005 | Tuning permissions visible without BoP | WF-004 | ☐ Pass ☐ Fail | | |
| DEF-P2-006 | Setup Builder field locking under BoP | WF-003, WF-007, WF-009 | ☐ Pass ☐ Fail | | |
| DEF-P2-007 | AI output validation banner | AI-007, AI-008 | ☐ Pass ☐ Fail | | |
| DEF-P2-008 | PTT works in Practice mode | LRE-002 | ☐ Pass ☐ Fail | | |
| DEF-P2-009 | Fuel burn one source | SP-007 | ☐ Pass ☐ Fail | | |
| DEF-P2-010 | Driver feedback form in Practice Review | WF-022, SP-010 | ☐ Pass ☐ Fail | | |
| DEF-P2-011 | Outlap excluded from session summary | WF-012, WF-019 | ☐ Pass ☐ Fail | | |
| DEF-P2-012 | Tyre wear multiplier correct in prompt | AI-003 | ☐ Pass ☐ Fail | | |
| DEF-P2-013 | Pit flag preserved after reload | WF-017, SP-005 | ☐ Pass ☐ Fail | | |
| DEF-P2-014 | Fuel start/end persisted to DB | WF-017, SP-004 | ☐ Pass ☐ Fail | | |
| DEF-P2-015 | Top speed shows "—" or ≥ 120 km/h, not 11 km/h | AI-011 | ☐ Pass ☐ Fail | | |
| DEF-P2-016 | Validation gate blocks bad AI call | AI-009 | ☐ Pass ☐ Fail | | |
| DEF-P2-017 | No RACE_FINISHED in Qualifying (register correction) | LRE-006 | ☐ Pass ☐ Fail | | |
| DEF-P2-QRF | No RACE_FINISHED in Qualifying (voice path) | WF-015, LRE-006 | ☐ Pass ☐ Fail | | |
| DEF-P3-001 | Brake balance step = 1 | WF-008 | ☐ Pass ☐ Fail | | |
| DEF-P3-002 | Active tyre compound on Live tab | SMK-003, LRE-010 | ☐ Pass ☐ Fail | | |
| DEF-P3-003 | Compound inherits from previous lap | WF-013 | ☐ Pass ☐ Fail | | |
| DEF-P3-004 | Race type mutual exclusivity in Event Planner (register correction) | WF-023 | ☐ Pass ☐ Fail | | |
| DEF-P3-006 | Summary recalculates after History load | WF-018, REG-010 | ☐ Pass ☐ Fail | | |
| DEF-P4-001 | PTT status on Live tab | SMK-002, LRE-001, REG-009 | ☐ Pass ☐ Fail | | |
| DEF-P4-002 | AI model = claude-opus-4-8 | AI-010, REG-007 | ☐ Pass ☐ Fail | | |
| DEF-P4-003 | Fuel formula = percentage multiplier | SP-008 | ☐ Pass ☐ Fail | | |

---

## Defects Not Covered by This UAT Plan

The following defects remain **Open** and are intentionally excluded from sign-off because no code fix has been implemented:

| Defect ID | Description | Why Excluded |
|-----------|-------------|--------------|
| DEF-P3-005 | Pit window static, not dynamically recalculated | Still Open — complex engine change, deferred |
| ENH-001–008 | Enhancements (dashboard tab, PTT intents, etc.) | Not in scope for this round |

*Note: DEF-P2-003, DEF-P2-010, DEF-P2-015, DEF-P2-017, and DEF-P3-004 were listed here in v1.0 as Open. All five are now fixed (Group 6, 2026-06-22) and included in the sign-off matrix above.*

---

## Recommended Testing Order

Work through sessions in this order to maximise defect detection before moving deeper:

1. **Smoke Test first (15 min)** — SMK-001 through SMK-006. If SMK-001 (app launch), SMK-004 (session opens), or SMK-005 (no crash) fail, stop and investigate before anything else.

2. **Session Persistence (20–30 min)** — SP-001 through SP-010. Run with GT7 active. These are DB-level checks that don't require extensive driving. If SP-001 or SP-002 fail, the entire lap-recording path is broken and further testing is unreliable. SP-010 (driver feedback DB) requires completing at least one lap first.

3. **Full Workflow (60–90 min)** — WF-001 through WF-023 in sequence. Plan at least one race distance of practice laps to have enough data for reload and summary tests. Create both a Timed and Lap Race event before starting. WF-022 (feedback form location) and WF-023 (race type mutual exclusivity) are quick UI checks — no driving required.

4. **AI Prompt Accuracy (30–45 min)** — AI-001 through AI-011. Requires GT7_AI_DEBUG=1. Have an activated event with known settings. AI-011 (top speed guard) requires one lap of telemetry first — run it immediately after your first practice lap.

5. **Live Race Engineer (30 min)** — LRE-001 through LRE-010. PTT tests require microphone and working voice backend. LRE-009 is a regression test — make sure race-mode alerts still work.

6. **Regression Checklist (15 min)** — REG-001 through REG-010. Quick final sweep.

**Total estimated time: 2.5–3.5 hours with driving.**

---

## Quick DB Reference

All queries assume SQLite. Run with:
```
sqlite3 data/gt7_sessions.db "your query here"
```

Useful queries:
```sql
-- Last 5 sessions
SELECT id, session_type, track, created_at FROM sessions ORDER BY id DESC LIMIT 5;

-- Last 5 laps with key fields
SELECT lap_num, session_type, is_out_lap, is_pit_lap, fuel_start, fuel_end, compound
FROM lap_records ORDER BY id DESC LIMIT 5;

-- Check session type for a specific session
SELECT lap_num, session_type FROM lap_records WHERE session_id = ?;

-- Verify compound counts
SELECT compound, COUNT(*) FROM lap_records WHERE session_id = ? GROUP BY compound;

-- Check driver feedback session linkage (SP-010)
SELECT id, session_id, submitted_at FROM driver_feedback ORDER BY id DESC LIMIT 3;

-- Check schema version
PRAGMA user_version;
```
