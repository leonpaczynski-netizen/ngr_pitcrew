# Strategy Builder — User Acceptance Test
**Group 18F | Product: Next Gear Racing Pit Crew**
**Version:** 1.0 | **Date:** 2026-06-26 | **Tester:** _______________

## Purpose
Verify that the Strategy Builder tab correctly auto-imports lap data from
recorded telemetry, produces valid AI strategy recommendations, and displays
all three ranked strategy options with their stint plans.

---

## Preconditions

| # | Requirement | Pass | Fail |
|---|---|---|---|
| P1 | App is launched and the main window is visible | | |
| P2 | Anthropic API key is set in Settings → AI Settings | | |
| P3 | An event is configured in Event Planner: Track, Car, Race Type (Lap Race or Timed Race), Fuel Multiplier, Tyre Wear, Available Tyres, Required Tyres | | |
| P4 | The event is set active | | |
| P5 | At least 3 practice laps have been recorded for the active car+track combination with valid fuel data (fuel_used > 0) | | |
| P6 | GT7_AI_DEBUG is NOT set | | |

---

## 1. Initial State — Strategy Builder Tab

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 1.1 | Click the **Strategy Builder** tab | Tab becomes active; no crash | | | |
| 1.2 | Inspect the Fuel Burn field | Auto-populated with calculated average fuel per lap from recorded telemetry; non-zero | | | |
| 1.3 | Inspect the Fuel Multiplier display | Matches the value set in Event Planner | | | |
| 1.4 | Inspect the Strategy Analysis area | Empty or shows cached result from last run | | | |
| 1.5 | Inspect the Stint Plan table | Empty or shows cached stint plan from last run | | | |
| 1.6 | Confirm the three strategy radio buttons / cards | Present; may be greyed out if no analysis has run yet | | | |

---

## 2. Lap Data Auto-Import (Group 18C)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 2.1 | Confirm that lap times have been recorded in the DB for the active car+track | At least 3 laps with valid compound tags | | | |
| 2.2 | Click **Strategy Builder** tab (or refresh if already there) | Fuel burn value is populated automatically; no manual entry required | | | |
| 2.3 | Click **"Run Analysis"** and observe the prompt in AI Log | AI Log entry shows prompt section containing per-compound lap time data auto-imported from DB | | | |

### DB verification
```sql
SELECT compound, COUNT(*) as laps, AVG(lap_time_ms)/1000.0 as avg_sec, AVG(fuel_used) as avg_fuel
FROM lap_records
WHERE car_id = (SELECT id FROM cars WHERE is_active = 1)
GROUP BY compound;
```
Expected: at least one compound with laps ≥ 3.

---

## 3. Run Analysis — Happy Path (Lap Race)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 3.1 | Ensure Race Type is Lap Race with ≥ 5 laps configured | Event Planner shows Lap Race, laps > 5 | | | |
| 3.2 | Click **"Run Analysis"** | Button disables or shows spinner; status updates | | | |
| 3.3 | Wait for AI call to complete (up to 90 s) | Three strategy cards or panels appear | | | |
| 3.4 | Inspect **Strategy 1 (Safe / Rank 1)** | Shows: Name, Estimated Race Time, Pit Stop count, Risk rating, Summary | | | |
| 3.5 | Inspect **Strategy 2 (Balanced / Rank 2)** | Shows same fields with different values | | | |
| 3.6 | Inspect **Strategy 3 (Aggressive / Rank 3)** | Shows same fields with different values | | | |
| 3.7 | Confirm each card shows Pros, Cons or Positives, Negatives, Risks | At least one of each present | | | |
| 3.8 | Estimated Race Time format | Displayed as h:mm:ss or mm:ss; non-zero | | | |

---

## 4. Stint Plan Display

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 4.1 | Click or select **Strategy 1** | Stint plan table populates | | | |
| 4.2 | Inspect Stint Plan table columns | Contains: Stint #, Compound, Laps, Fuel/Lap or similar; all rows non-empty | | | |
| 4.3 | Confirm the total laps across all stints | Sum of stint laps equals the race lap count from Event Planner | | | |
| 4.4 | Confirm compound names match Available Tyres from Event Planner | No unknown compound names appear | | | |
| 4.5 | Click **Strategy 2** | Stint plan updates to reflect Strategy 2 | | | |
| 4.6 | Click **Strategy 3** | Stint plan updates to reflect Strategy 3 | | | |

---

## 5. Run Analysis — Happy Path (Timed Race)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 5.1 | Update Event Planner: change Race Type to Timed Race (e.g., 30 minutes); set active | Timed Race configured | | | |
| 5.2 | Return to Strategy Builder; click **"Run Analysis"** | AI call completes; three strategies appear | | | |
| 5.3 | Inspect Stint Plan | Lap estimates are shown (estimated from best lap and time remaining) | | | |
| 5.4 | Confirm estimated laps are plausible | Laps = floor(race_duration / avg_lap_time) ± 1 | | | |

---

## 6. AI Log Persistence

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 6.1 | Click the **AI Log** tab | Tab becomes active | | | |
| 6.2 | Locate the most recent entry | Feature = "Strategy Analysis" or similar; success = true | | | |
| 6.3 | Inspect prompt | Contains race lap count or duration, per-compound lap data, fuel multiplier, tyre wear, available compounds | | | |
| 6.4 | Inspect response | JSON or structured text with 3 strategy options | | | |
| 6.5 | Confirm token counts and cost are non-zero | prompt_tokens > 0, estimated_cost > 0 | | | |

---

## 7. Save Strategy

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 7.1 | With a strategy selected, click **"Save Strategy"** (if present) | Strategy saved; confirmation message shown | | | |
| 7.2 | Navigate away and return to Strategy Builder | Selected strategy is retained or reloadable | | | |

---

## 8. No Lap Data — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 8.1 | Use a car+track combination with no recorded laps in the DB | Fuel burn field shows 0 or "No data" | | | |
| 8.2 | Click **"Run Analysis"** | Button is disabled OR a validation warning appears: "No lap data recorded" or "Insufficient fuel data"; no crash; no API call made | | | |

---

## 9. No Event Duration — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 9.1 | Create or modify an event with Race Type = Lap Race and Laps = 0 | Event saved with 0 laps | | | |
| 9.2 | Set active; go to Strategy Builder; click **"Run Analysis"** | Validation warning shown: "Race length must be greater than 0" or similar; no API call made | | | |

---

## 10. Mandatory Compound / Stop Requirements

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 10.1 | In Event Planner, set Required Tyres to a specific compound (e.g., Racing Hard) | Required tyre is shown in Setup Builder and Strategy Builder context | | | |
| 10.2 | Run analysis | At least one strategy includes the required compound in its stint plan | | | |
| 10.3 | Confirm no strategy recommends a compound not in Available Tyres | All compounds in stint plans are in the Available Tyres list | | | |

---

## 11. No API Key — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 11.1 | Clear the API key in Settings | Key cleared | | | |
| 11.2 | Click **"Run Analysis"** | Error message shown: "No Anthropic API key configured"; no crash | | | |
| 11.3 | Restore API key | Confirmed | | | |

---

## 12. Multi-Compound Lap Data

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 12.1 | Ensure the DB has laps recorded on at least two different tyre compounds | Two compound rows in lap_records | | | |
| 12.2 | Run analysis | AI prompt references both compounds with separate lap statistics | | | |
| 12.3 | Confirm per-compound stats in the prompt | Each compound's avg lap time and fuel/lap appear separately in the AI Log prompt | | | |

---

## 13. Deterministic Outcome Comparison (Strategy Outcome integration)

Covers the on-device total-race-time comparison added in the Strategy Outcome
integration. Requires a completed analysis (Section 3) with ≥ 2 strategy cards.

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 13.1 | After an analysis returns ≥ 2 strategies, inspect each card's time line | Each card shows an app-computed total race time (labelled distinctly from the AI's estimate) | | | |
| 13.2 | Inspect the head-to-head delta | The fastest strategy shows "fastest"; the others show **"+X.Xs vs fastest"** | | | |
| 13.3 | Inspect the rank badge | Each card shows a **"#N by time"** badge (fastest = #1); card order itself is unchanged (Load Strategy N still maps correctly) | | | |
| 13.4 | Inspect the pit/refuel figures | The label reads **"pit time"** (not "pit loss"); the value reflects pit loss + refuel time computed from the **actual refuel rate** (`pit loss + fuel / refuel speed`) | | | |
| 13.5 | Inspect the confidence badge | Each card shows an outcome-confidence indicator; with thin/absent tyre-degradation data the confidence is **low/medium** and visually distinct | | | |
| 13.6 | Inspect the risk chips | tyre / fuel / undercut risk and the AI confidence % are displayed when present (previously parsed but hidden); absent chips simply don't render | | | |
| 13.7 | Change the event refuel rate in Event Planner, re-run analysis | Pit/refuel time and the total-time comparison change accordingly (rate is actually used, not a flat guess) | | | |

## 14. Protected Behaviour — Mid-Race Replan & PTT (must still work)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 14.1 | Load a strategy, start a Race session, and let tyre-deg / fuel drift trigger a re-plan | Mid-race AI re-plan fires and updates the plan as before — unchanged by this integration | | | |
| 14.2 | Use PTT to ask for strategy / pace / fuel, and report rain / damage | PTT intents respond correctly (Practice/Qualifying/Race); voice prompts unchanged | | | |

---

## Summary

| Section | Description | Pass | Fail | Defects |
|---|---|---|---|---|
| 1 | Initial state | | | |
| 2 | Lap data auto-import | | | |
| 3 | Lap race happy path | | | |
| 4 | Stint plan display | | | |
| 5 | Timed race happy path | | | |
| 6 | AI log persistence | | | |
| 7 | Save strategy | | | |
| 8 | No lap data | | | |
| 9 | No event duration | | | |
| 10 | Mandatory compound | | | |
| 11 | No API key | | | |
| 12 | Multi-compound data | | | |
| 13 | Deterministic outcome comparison | | | |
| 14 | Protected — replan & PTT | | | |

**Overall result:** PASS / FAIL

---

## Defect Register

| ID | Section | Step | Description | Severity | Status | Root Cause | Fix |
|---|---|---|---|---|---|---|---|
| STA-001 | | | | | | | |

---

## Tester Notes

_Free-form observations, environment details, GT7 version, car used, track used, number of laps in DB:_
