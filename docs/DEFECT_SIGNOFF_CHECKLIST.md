# GT7 VR Dashboard — Defect Sign-Off Checklist

> **Tester:** Leon Paczynski  
> **Date:** _______________  
> **Build:** Groups 1–6 complete — 204 automated tests passing  
> **Environment:** GT7 on PS5, dashboard on PC, GT7_AI_DEBUG=1  
>
> **How to use:** Tick ✅ when you have confirmed the behaviour in the running app. Tick ❌ if it fails — note the failure in the Notes column and raise a new defect. Reference the UAT plan (`docs/UAT_TEST_PLAN.md`) for exact steps if needed.

---

## Group 1 — Crash Fixes

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 1 | DEF-P1-003 | Click "Save Session" with laps in Practice Review — no crash, no `AttributeError` in console | SMK-005, WF-020 | ☐ | ☐ | |
| 2 | DEF-P1-004 | Activate a 40-min timed race event, run Practice Analysis — prompt says "Race duration: 40 minutes", NOT "Race length: 1 laps" | AI-001 | ☐ | ☐ | |
| 3 | DEF-P1-008 | In Practice mode, drive past a 1-min timed event timer — no "Race finished" voice announcement | LRE-005 | ☐ | ☐ | |

---

## Group 2 — AI Prompt Accuracy + Data Persistence

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 4 | DEF-P1-005 | Event with BoP=On, Tuning=No — AI prompt contains `## EVENT RULES — TUNING LOCKED` block | AI-006 | ☐ | ☐ | |
| 5 | DEF-P1-006 | Tag 15 laps RM, 7 laps RS in Practice Review, run Practice Analysis — prompt shows RM:15, RS:7 (not swapped) | AI-004 | ☐ | ☐ | |
| 6 | DEF-P1-007 | Load 10 historical laps avg ~4.2 L/lap — Strategy Builder Fuel Burn Auto shows ~4.2, prompt shows ~4.2 | AI-005 | ☐ | ☐ | |
| 7 | DEF-P2-012 | Event with Tyre Wear 1.5× — Practice Analysis prompt says "1.5× faster" not "2.0×" or "1.0×" | AI-003 | ☐ | ☐ | |
| 8 | DEF-P2-014 | Complete 3 laps, query: `SELECT fuel_start, fuel_end FROM lap_records ORDER BY id DESC LIMIT 3` — all non-zero | SP-004 | ☐ | ☐ | |
| 9 | DEF-P2-016 | With no fuel data in Practice Review, click Practice Analysis — warning dialog appears, no AI call is made | AI-009 | ☐ | ☐ | |
| 10 | DEF-P4-002 | After any AI call, check AI Log tab — Model field shows `claude-opus-4-8` | AI-010 | ☐ | ☐ | |

---

## Group 3 — Session Reload Accuracy

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 11 | DEF-P1-002 | Complete a pit stop and outlap — outlap appears in Practice Review (dark green row or "OL" label), `is_out_lap = 1` in DB | WF-011, SP-003 | ☐ | ☐ | |
| 12 | DEF-P2-011 | With an outlap and 3+ normal laps, Session Summary best lap is the fastest **non-outlap** lap | WF-012, WF-019 | ☐ | ☐ | |
| 13 | DEF-P2-013 | Load a session from History that has a pit lap — Pit column shows "Yes" with amber background, `is_pit_lap = 1` in DB | WF-017, SP-005 | ☐ | ☐ | |
| 14 | DEF-P3-006 | Load a 10-lap session from History into Practice Review — Session Summary updates immediately with correct best/avg/fuel | WF-018 | ☐ | ☐ | |

---

## Group 4 — BoP and Tuning Permissions

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 15 | DEF-P2-004 | Open Setup Builder — there is NO standalone BoP checkbox in the form (BoP is read-only in Race Conditions group) | WF-006 | ☐ | ☐ | |
| 16 | DEF-P2-005 | Event with BoP=Off, Tuning=On — Tuning Permissions group appears in Event Planner; uncheck Tuning → group hides | WF-004 | ☐ | ☐ | |
| 17 | DEF-P2-006 | Event with BoP=On, Tuning=Off — Setup Builder shows locked banner, suspension/aero/gear spinboxes disabled, tyre dropdowns still **enabled** | WF-003, WF-009 | ☐ | ☐ | |
| 18 | DEF-P2-007 | Event with Tuning=Yes, Allowed=Suspension+Brake Balance — AI prompt contains `## EVENT TUNING RESTRICTIONS` listing Allowed and LOCKED categories | AI-007 | ☐ | ☐ | |

---

## Group 5 — Live Mode + Voice Guards

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 19 | DEF-P1-001 | Select Practice mode on Live tab **before driving** — `SELECT id, session_type FROM sessions ORDER BY id DESC LIMIT 1` shows a row immediately | SMK-004, SP-002 | ☐ | ☐ | |
| 20 | DEF-P2-001 | Complete 3 laps in Practice mode — `SELECT session_type FROM lap_records ORDER BY id DESC LIMIT 3` — all rows show `'practice'` | SP-001 | ☐ | ☐ | |
| 21 | DEF-P2-002 | In Practice mode, run low on fuel and enter the pit lane — no fuel-low voice alert, no pit advice spoken | WF-014, LRE-007 | ☐ | ☐ | |
| 22 | DEF-P2-002 | In Qualifying mode, same scenario — no fuel-low or pit alerts spoken | LRE-008 | ☐ | ☐ | |
| 23 | DEF-P2-002 | In Race mode — fuel-low alert IS spoken, pit advice IS spoken (regression — alerts must not be over-suppressed) | LRE-009 | ☐ | ☐ | |
| 24 | DEF-P2-008 | In Practice mode, press PTT and ask a coaching question — response returned, Live tab status goes TRANSMITTING → RADIO READY | LRE-002 | ☐ | ☐ | |
| 25 | DEF-P2-QRF | In Qualifying mode, drive past a 1-min timed event timer — no "Race finished" voice announcement | LRE-006 | ☐ | ☐ | |
| 26 | DEF-P2-009 | After 5 live laps, manual average of fuel column ≈ Strategy Builder Fuel Burn Auto display (within ±0.1 L/lap) | SP-007 | ☐ | ☐ | |
| 27 | DEF-P3-001 | In Setup Builder, click Brake Balance spinbox up once — value changes by exactly 1 | WF-008 | ☐ | ☐ | |
| 28 | DEF-P3-002 | Activate event with Required Tyre = Racing Hard — Live tab above tyre temps shows "Tyre: Racing Hard" | SMK-003, LRE-010 | ☐ | ☐ | |
| 29 | DEF-P3-003 | In Practice Review, change lap 4 compound to Racing Hard — lap 5's compound initialises to Racing Hard, not the default | WF-013 | ☐ | ☐ | |
| 30 | DEF-P4-001 | On the Live tab, "RADIO READY" label is visible without switching to Settings; press PTT — label updates on Live tab | SMK-002, LRE-001 | ☐ | ☐ | |
| 31 | DEF-P4-003 | With avg fuel 3.0 L/lap and 10 laps remaining, Balanced fuel target ≈ 31.5 L (3.0 × 10 × 1.05), NOT 36 L (additive formula) | SP-008 | ☐ | ☐ | |

---

## Group 6 — UI Placement + Data Quality

| # | Defect | What to confirm | UAT Ref | ✅ Pass | ❌ Fail | Notes |
|---|--------|-----------------|---------|---------|---------|-------|
| 32 | DEF-P2-010 | Open Practice Review — "Driver Feedback — After Stint" group is visible at the bottom with combo selectors and Submit button | WF-022 | ☐ | ☐ | |
| 33 | DEF-P2-010 | Open Setup Builder — no "Driver Feedback" group anywhere on the tab | WF-022 | ☐ | ☐ | |
| 34 | DEF-P2-010 | Submit feedback from Practice Review with a live session — `SELECT session_id FROM driver_feedback ORDER BY id DESC LIMIT 1` returns a value > 0 matching the active session | SP-010 | ☐ | ☐ | |
| 35 | DEF-P2-015 | After one lap of telemetry, check Setup Builder → Transmission → Top Speed — shows "—" or a value ≥ 120 km/h, never "11 km/h" | AI-011 | ☐ | ☐ | |
| 36 | DEF-P2-015 | Run Practice Analysis with GT7_AI_DEBUG=1 — search prompt for "11 km/h" — it does NOT appear | AI-011 | ☐ | ☐ | |
| 37 | DEF-P2-003 | In Event Planner, set Available Tyres = Racing Medium + Racing Hard — Required Tyres shows checkboxes for those two compounds only (not a dropdown) | WF-001 | ☐ | ☐ | |
| 38 | DEF-P2-017 | In Qualifying mode (timed event) — no "Race finished" announcement when timer expires (timed-race code path) | LRE-006 | ☐ | ☐ | |
| 39 | DEF-P3-004 | In Event Planner, select Timed Race — Laps field is greyed out; select Lap Race — Duration field is greyed out | WF-023 | ☐ | ☐ | |

---

## Sign-Off Summary

| Group | Defects | All Pass? | Signed off by | Date |
|-------|---------|-----------|---------------|------|
| Group 1 — Crash Fixes | #1–3 | ☐ Yes ☐ No | | |
| Group 2 — AI Prompt + Data | #4–10 | ☐ Yes ☐ No | | |
| Group 3 — Session Reload | #11–14 | ☐ Yes ☐ No | | |
| Group 4 — BoP + Tuning | #15–18 | ☐ Yes ☐ No | | |
| Group 5 — Live Mode + Voice | #19–31 | ☐ Yes ☐ No | | |
| Group 6 — UI + Data Quality | #32–39 | ☐ Yes ☐ No | | |
| **All 39 items** | **#1–39** | **☐ Yes ☐ No** | | |

---

## Useful DB Queries

```sql
-- Session created on mode selection (items 19, 20)
SELECT id, session_type, created_at FROM sessions ORDER BY id DESC LIMIT 3;

-- Lap session type and fuel fields (items 20, 8)
SELECT lap_num, session_type, fuel_start, fuel_end, compound, is_out_lap, is_pit_lap
FROM lap_records ORDER BY id DESC LIMIT 5;

-- Driver feedback session linkage (item 34)
SELECT id, session_id, submitted_at FROM driver_feedback ORDER BY id DESC LIMIT 3;

-- Schema version
PRAGMA user_version;
```
