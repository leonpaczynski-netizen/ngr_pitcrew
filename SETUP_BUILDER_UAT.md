# Setup Builder — User Acceptance Test
**Group 18F | Product: Next Gear Racing Pit Crew**
**Version:** 1.0 | **Date:** 2026-06-26 | **Tester:** _______________

## Purpose
Verify that the Setup Builder tab produces valid, context-aware AI car setup
recommendations and correctly persists each iteration into the learning loop.

---

## Preconditions

| # | Requirement | Pass | Fail |
|---|---|---|---|
| P1 | App is launched and the main window is visible | | |
| P2 | Anthropic API key is set in Settings → AI Settings | | |
| P3 | At least one event has been created in Event Planner with Track, Car, Race Type, Fuel Multiplier, Tyre Wear, Available Tyres, and Required Tyres populated | | |
| P4 | The event is set active (Event Planner → "Set Active") | | |
| P5 | GT7_AI_DEBUG is NOT set (live API calls are expected) | | |

---

## 1. Initial State — Setup Builder Tab

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 1.1 | Click the **Setup Builder** tab | Tab becomes active; no crash | | | |
| 1.2 | Inspect the Race Conditions group | Track, Car, Race Type, BoP Status, Fuel Multiplier, Tyre Wear, Available Tyres, Required Tyres are all populated from the active event | | | |
| 1.3 | Inspect the Car Setup group | All spinboxes and inputs are present; fields are editable according to event tuning permissions | | | |
| 1.4 | Inspect the Setup History combo | Present; shows "No history" or any prior saved setups for this car+track | | | |
| 1.5 | Confirm no setup values are pre-filled from a previous session | All spinboxes at default / last-saved values | | | |

---

## 2. Build Setup with AI — Happy Path

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 2.1 | Select **Setup Type**: Race Setup | Selector shows "Race Setup" | | | |
| 2.2 | Click **"Build Setup with AI"** button | Button becomes disabled or shows spinner; status changes to "Building…" or similar | | | |
| 2.3 | Wait for the AI call to complete (up to 60 s) | Spinboxes auto-populate with numeric values across all setup categories | | | |
| 2.4 | Inspect **Ride Height F/R** | Two numeric values (mm); both > 0 | | | |
| 2.5 | Inspect **Springs F/R** | Two numeric values (N/mm); both > 0 | | | |
| 2.6 | Inspect **Dampers Comp F/R** | Two numeric values; both within GT7 range | | | |
| 2.7 | Inspect **Dampers Ext F/R** | Two numeric values; both within GT7 range | | | |
| 2.8 | Inspect **ARB F/R** | Two numeric values; both within GT7 range | | | |
| 2.9 | Inspect **Camber F/R** | Two numeric values (degrees) | | | |
| 2.10 | Inspect **Toe F/R** | Two numeric values (degrees) | | | |
| 2.11 | Inspect **Aero F/R** | Two numeric values (downforce kg) | | | |
| 2.12 | Inspect **LSD Initial / Accel / Decel** | Three numeric values | | | |
| 2.13 | Inspect **Brake Bias** | Single integer; GT7 scale −5 to +5 | | | |
| 2.14 | Inspect **Ballast kg** and **Ballast Position** | Two values; position within −50 to +50 | | | |
| 2.15 | Inspect **Final Drive** | Numeric ratio or "not set" | | | |
| 2.16 | Inspect **AI Setup Reasoning** text area | Non-empty paragraph explaining the setup choices | | | |
| 2.17 | Confirm "Build Setup with AI" button is re-enabled after completion | Button is clickable again | | | |

---

## 3. AI Log Persistence

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 3.1 | Click the **AI Log** tab | Tab becomes active | | | |
| 3.2 | Locate the most recent entry | Entry exists; Feature = "Car Setup"; success = true | | | |
| 3.3 | Expand or view the entry | Prompt text, response text, token counts, estimated cost, and duration are all non-empty | | | |
| 3.4 | Confirm `session_id` is logged | session_id column shows a non-zero value if a live session is active, or 0 in idle state | | | |

### DB verification (optional)
```sql
SELECT feature, success, prompt_tokens, response_tokens, session_id
FROM ai_interactions ORDER BY id DESC LIMIT 3;
```
Expected: top row has feature = 'Car Setup', success = 1.

---

## 4. Recommendation Persistence (Learning Loop)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 4.1 | After step 2.17, open an SQLite browser or run the query below | `setup_recommendations` table has at least one new row with status = 'proposed' | | | |
| 4.2 | Confirm `car_id` matches the active car | car_id is non-zero and matches the car in Event Planner | | | |
| 4.3 | Confirm `track` matches the active track | track string matches event track name | | | |
| 4.4 | Confirm `recommendation_text` is non-empty | At least one recommendation row has text | | | |
| 4.5 | Confirm `session_id` is populated | session_id is non-zero if a live session was active; 0 otherwise | | | |

### DB verification
```sql
SELECT id, car_id, track, status, outcome, LENGTH(recommendation_text) AS text_len
FROM setup_recommendations ORDER BY id DESC LIMIT 5;
```
Expected: newest rows have status = 'proposed', outcome = 'not_verified', text_len > 0.

---

## 5. Setup History Context Injection (Second Build)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 5.1 | Without changing the event or car, click **"Build Setup with AI"** a second time | AI call completes; new setup values appear | | | |
| 5.2 | Navigate to AI Log tab and open the newest Car Setup entry | Prompt text contains the section header "## Previous Setup Recommendations for This Car and Track" | | | |
| 5.3 | Confirm the prompt also contains "## Setup Performance Comparison (Lap Data)" if laps are recorded | Section is present when lap history exists; absent (no header) if no laps | | | |
| 5.4 | Confirm the AI Reasoning text references prior setup context | Text mentions something like "previous recommendation", "last setup", "prior iteration", or similar phrasing | | | |

---

## 6. BoP Tuning Locked — AI Must Not Recommend Locked Changes

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 6.1 | In Event Planner, set BoP = On and Tuning Allowed = Off; set active | Race Conditions shows Tuning: Locked | | | |
| 6.2 | Return to Setup Builder and click **"Build Setup with AI"** | AI call completes | | | |
| 6.3 | Inspect AI Setup Reasoning | Reasoning explicitly states that tuning-locked parameters are not changed, or notes constraints | | | |
| 6.4 | Inspect spinbox values for locked parameters | Locked parameters should not be changed from GT7 defaults (or a note is shown) | | | |

---

## 7. Qualifying Setup Type

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 7.1 | Change Setup Type to **Qualifying Setup** | Selector shows "Qualifying Setup" | | | |
| 7.2 | Click **"Build Setup with AI"** | AI call completes; new values appear | | | |
| 7.3 | Inspect AI Setup Reasoning | Reasoning mentions qualifying, single lap, low fuel, or similar qualifier-specific context | | | |

---

## 8. No API Key — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 8.1 | Navigate to Settings → AI Settings; clear the API key field; save | API key field is blank | | | |
| 8.2 | Return to Setup Builder; click **"Build Setup with AI"** | An error message appears: "No Anthropic API key configured" or similar; no crash | | | |
| 8.3 | Restore the API key in Settings | API key restored | | | |

---

## 9. No Active Event — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 9.1 | In Event Planner, deactivate the current event (if a "Clear Active" option exists) or ensure no event is active | Race Conditions in Setup Builder shows dashes (—) for all fields | | | |
| 9.2 | Click **"Build Setup with AI"** | Button is disabled, or a validation message appears: "No active event" or similar; no crash | | | |
| 9.3 | Restore the active event | Fields populate correctly | | | |

---

## 10. Apply Recommendation to Session (Outcome Tracking)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 10.1 | With a 'proposed' recommendation in the DB, save a setup using the generated values | Setup saved to Garage/history | | | |
| 10.2 | With a live telemetry session active, trigger `_apply_and_save_ai_setup()` (save button) | No crash; confirmation shown | | | |
| 10.3 | Check DB: most recent 'proposed' row for this car+track | status = 'applied'; outcome_session_id > 0; before_metrics JSON contains best_lap_ms, avg_fuel_per_lap, lap_count | | | |

### DB verification
```sql
SELECT id, status, outcome, outcome_session_id, before_metrics
FROM setup_recommendations ORDER BY id DESC LIMIT 3;
```
Expected: newest row has status = 'applied', before_metrics != '{}'.

---

## Summary

| Section | Description | Pass | Fail | Defects |
|---|---|---|---|---|
| 1 | Initial state | | | |
| 2 | Happy path — AI build | | | |
| 3 | AI log persistence | | | |
| 4 | Recommendation persistence | | | |
| 5 | History context injection | | | |
| 6 | BoP tuning lock | | | |
| 7 | Qualifying setup type | | | |
| 8 | No API key | | | |
| 9 | No active event | | | |
| 10 | Outcome tracking | | | |

**Overall result:** PASS / FAIL

---

## Defect Register

| ID | Section | Step | Description | Severity | Status | Root Cause | Fix |
|---|---|---|---|---|---|---|---|
| SB-001 | | | | | | | |

---

## Tester Notes

_Free-form observations, environment details, GT7 version, car used, track used:_

