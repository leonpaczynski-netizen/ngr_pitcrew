# UAT Phase 2 — Smoke Test

> **Target:** 15 minutes  
> **Scope:** Groups 7–10 only (Root Causes A, B, C, D)  
> **Goal:** Confirm the four major root causes are resolved before running the full UAT checklist.  
> **Run order matters** — steps chain together to minimise tab switching.

---

## Launch

```powershell
$env:GT7_AI_DEBUG = "1"
python main.py
```

`GT7_AI_DEBUG=1` lets you inspect AI prompts without a real API key. Required for Tests 3 and 4.

---

## Test 1 — Root Cause A: Event Persistence (Group 7) `~3 min`

**Defect:** DEF-P1-009 | **AWR:** AWR-031

### Steps

1. Open the **Event Planner** tab.
2. Click **New Event**. Fill in these specific non-default values:

   | Field | Value |
   |-------|-------|
   | Track | Suzuka Circuit |
   | Race Type | Lap Race |
   | Laps | 20 |
   | Tyre Wear | 2× |
   | Fuel Multiplier | 3× |
   | Available Tyres | Racing Medium ✓, Racing Hard ✓ |
   | Required Tyres | Racing Hard ✓ |
   | BoP | On ✓ |
   | Tuning | Off (unchecked) |

3. Click **Save**.
4. Click a different event in the list (or click **New Event** then immediately click back on your saved event).
5. Click the saved event again to reload it.

### Expected

- [ ] Tyre Wear shows **2×** (not the default 1×)
- [ ] Fuel Multiplier shows **3×** (not the default 1×)
- [ ] Racing Medium and Racing Hard are **both checked** under Available Tyres
- [ ] Racing Hard is **checked** under Required Tyres
- [ ] BoP checkbox is **ticked**
- [ ] Tuning checkbox is **unticked**

6. Click **Set Active**.

### Expected

- [ ] Strategy Builder Fuel Multiplier updates to **×3**
- [ ] Tyre wear multiplier is **×2** (visible in any AI prompt fuel/tyre context)

**RESULT: PASS / FAIL**

---

## Test 2 — Root Cause D: Validation Gate (Group 10) `~1 min`

**Defect:** DEF-P2-016 | **AWR:** AWR-039

Keep the BoP=On, Tuning=Off event active from Test 1.

### Steps

1. Navigate to the **Practice Review** tab.
2. If any laps are visible in the table, click **Clear** (or load a fresh state with 0 laps).
3. Click **Run Analysis** with an empty lap table.

### Expected

- [ ] A **warning dialog** appears listing the validation failure(s) — e.g. "No lap data", "Fuel burn not available"
- [ ] **No entry is added** to the AI Log tab (verify before proceeding)

**RESULT: PASS / FAIL**

---

## Test 3 — Root Cause C: AI Log Visibility (Group 9) `~2 min`

**Defect:** DEF-P1-010 | **AWR:** AWR-036

### Steps

1. Still in **Practice Review**. Load at least 2 laps:
   - Load from History (History tab → select a session → Load), **or**
   - Complete 2 quick laps on track if connected.
2. Verify at least 2 laps are visible in the Practice Review table.
3. Click **Run Analysis**.
4. Navigate to the **AI Log** tab.

### Expected

- [ ] At least **one entry** is visible in the AI Log list
- [ ] The entry shows **✗** (failed / dry-run) in the status column
- [ ] The entry shows a **feature name** (e.g. "Practice Analysis") and timestamp
- [ ] Clicking the entry and opening the **Prompt** sub-tab shows the full prompt text

**RESULT: PASS / FAIL**

---

## Test 4 — Root Cause D: BoP Prompt Content (Group 10) `~2 min`

**Defect:** DEF-P1-005 | **AWR:** AWR-037

This test uses the console output from Test 3 (same Run Analysis call). No additional steps needed.

### Steps

1. Check the **terminal / console** output from the Test 3 Run Analysis call.
   - Look for the block surrounded by `====` separators.

### Expected

- [ ] Prompt contains **`## EVENT RULES — TUNING LOCKED`**
- [ ] Setup section shows **`[TUNING LOCKED — setup changes not permitted for this Event]`** — not actual numeric ride height, spring rate, or aero values
- [ ] Prompt does **not** contain your actual ride height, spring rate, aero, or LSD values as editable recommendations

> **Optional — partial tuning check (AWR-038):** Edit the event to Tuning=On, Allowed=[Brake Balance only]. Set Active. Run Analysis again. Prompt must contain `## EVENT TUNING RESTRICTIONS` and show `Ride Height F/R: ?/? mm` while showing an actual `Brake bias:` value.

**RESULT: PASS / FAIL**

---

## Test 5 — Root Cause B: Session Reload Mapping (Group 8) `~4 min`

**Defects:** DEF-P2-009, DEF-P2-013, DEF-P2-014 | **AWR:** AWR-033, AWR-034, AWR-035

### Step A — Fuel Burn Display (AWR-034) — required

1. Navigate to the **History** tab.
2. Select any session that has at least 3 non-pit laps.
3. Click **Load** (or equivalent action to send laps to Practice Review).
4. Navigate to the **Strategy Builder** tab.

### Expected

- [ ] **Fuel Burn Auto** label shows a value ending with **"(loaded session)"**
- [ ] The displayed value is non-zero and plausible (not 0.00 or the app startup default)

### Step B — Pit Flag Persistence (AWR-033) — requires a session driven after the Group 8 fix

> Skip this step if you have no sessions containing a pit stop lap recorded after 2026-06-22.

1. From History, load a session that contains at least one pit stop lap.
2. Navigate to **Practice Review**.

### Expected

- [ ] Pit stop lap row has an **amber background**
- [ ] Pit column shows **Yes** for that row

### Step C — DB Verification (AWR-035) — optional, ~30 seconds

Open a SQLite client against `data/gt7_sessions.db`:

```sql
SELECT lap_num, session_type, fuel_start, fuel_end, is_pit_lap, is_out_lap
FROM lap_records
ORDER BY id DESC
LIMIT 5;
```

### Expected

- [ ] `session_type` is `'practice'` or `'race'` (not empty string `''`)
- [ ] `fuel_start` and `fuel_end` are non-zero for laps recorded after the Group 8 fix
- [ ] At least one row has `is_pit_lap = 1` if you have driven a pit lap

**RESULT: PASS / FAIL**

---

## Scorecard

| Test | Root Cause | Group | AWR | Result |
|------|-----------|-------|-----|--------|
| 1 — Event Persistence | A | 7 | AWR-031 | PASS / FAIL |
| 2 — Validation Gate | D | 10 | AWR-039 | PASS / FAIL |
| 3 — AI Log Visibility | C | 9 | AWR-036 | PASS / FAIL |
| 4 — BoP Prompt Content | D | 10 | AWR-037 | PASS / FAIL |
| 5A — Fuel Burn Display | B | 8 | AWR-034 | PASS / FAIL |
| 5B — Pit Flag Persistence | B | 8 | AWR-033 | PASS / FAIL / N/A |
| 5C — DB Field Verification | B | 8 | AWR-035 | PASS / FAIL / SKIP |

### Gate

- **All PASS (or N/A):** Proceed to the full UAT checklist.
- **Any FAIL:** Stop. File the failure with the exact step, observed value, and expected value. Do not run full UAT until resolved.

---

## Failures — Record Here

| Step | Observed | Expected | Notes |
|------|----------|----------|-------|
| | | | |
