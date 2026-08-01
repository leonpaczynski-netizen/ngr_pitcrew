# Live Activation 1 — On-Hardware UAT (GT7 + PSVR2)

Branch `live/program3-activation1-practice-recording-2026-08-01`. This is the first production
telemetry seam through the canonical event spine: **live GT7 Practice recording against an
explicitly active planned session, persisted under one canonical `session_run`, with the Practice
Engineer using that same authoritative context.**

Scope is Practice only. Qualifying, broader PTT, per-lap Race-Strategy snapshots and damage/rain/
fuel/tyre replanning are **out of scope** and must stay inert.

**Every item below is `NOT TESTED` until the driver completes it on real hardware.** Claude cannot
mark any of these PASS; live certification remains explicitly `NOT TESTED`.

---

## 0. Preparation

| # | Step | Expected | Result |
|---|------|----------|--------|
| 0.1 | Create or select ONE controlled event | Event visible + active | ☐ NOT TESTED |
| 0.2 | Select ONE car | Car shown in context header | ☐ NOT TESTED |
| 0.3 | Select ONE Practice session with a clear objective (e.g. baseline validation) | Objective shown; session type = Practice | ☐ NOT TESTED |
| 0.4 | Verify the context/diagnostics header | Event ID, Session Plan ID, Session Type=Practice, Engineer Mode, Recording State=not_started, Car, Setup Snapshot, Context Revision all shown (full ids behind the diagnostics expander) | ☐ NOT TESTED |
| 0.5 | Verify no active run exists | Recording State = not_started; no Session Run ID | ☐ NOT TESTED |
| 0.6 | Start GT7 telemetry (PS5 → app) | Telemetry = connected | ☐ NOT TESTED |

**Context-incomplete check:** if any required identity (event programme, event, session plan, car,
car-spec revision, driver-profile version, context revision) is unresolved, recording must be
**blocked** with the exact missing requirement named — the app must NOT fall back to another event.

## 1. Live run

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1.1 | Start the Practice run | One canonical Session Run ID appears; Recording State = recording | ☐ NOT TESTED |
| 1.2 | Confirm the Practice Engineer brief | Brief matches the CHOSEN objective (not a different one) | ☐ NOT TESTED |
| 1.3 | Confirmation when recording begins | Engineer confirms recording started | ☐ NOT TESTED |
| 1.4 | Drive several valid laps | Valid-lap count increments; "N laps so far" on the run card | ☐ NOT TESTED |
| 1.5 | Intentionally create ONE invalid/incomplete lap where safe (e.g. cut / pit) | Lap recorded but flagged invalid; count does NOT increment; engineer explains why | ☐ NOT TESTED |
| 1.6 | Disconnect or interrupt telemetry once | Recording State = disconnected; no phantom lap is finalised | ☐ NOT TESTED |
| 1.7 | Reconnect telemetry | Same Session Run ID resumes (same event+plan); Recording State = recording | ☐ NOT TESTED |
| 1.8 | Complete the target number of laps | Engineer notes sufficient evidence collected | ☐ NOT TESTED |
| 1.9 | Verify completion message | Concise session conclusion; Recording State = completing → completed | ☐ NOT TESTED |

## 2. Context protection

| # | Step | Expected | Result |
|---|------|----------|--------|
| 2.1 | Navigate between UI pages during the run | Every page shows the SAME event + run; objective unchanged | ☐ NOT TESTED |
| 2.2 | Attempt to switch event WHILE recording | Blocked with a driver-facing message; must complete/abandon first — no silent switch | ☐ NOT TESTED |
| 2.3 | End the run | Recording State = completed; run is history | ☐ NOT TESTED |
| 2.4 | Restart the app | Correct event/session restored; the completed run does NOT reopen as active; honest no-active-run state | ☐ NOT TESTED |
| 2.5 | Start a DIFFERENT event, run Practice | A new distinct Session Run; Engineer Mode re-resolved; no lap/objective leakage from the first event | ☐ NOT TESTED |

## 3. Database verification

Use the diagnostics header + a safe read-only query/report to confirm, for the run above:

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 3.1 | One intended session run | exactly 1 `session_runs` row for the plan | ☐ NOT TESTED |
| 3.2 | Correct stints | opening stint present, bound to the run | ☐ NOT TESTED |
| 3.3 | Correct lap count | timed `lap_records` == valid laps driven | ☐ NOT TESTED |
| 3.4 | No duplicate lap numbers | no repeated `lap_num` for the run | ☐ NOT TESTED |
| 3.5 | Correct event relationship | run + laps carry the right `event_id` | ☐ NOT TESTED |
| 3.6 | Correct car + setup relationship | run traces to the car-spec + setup snapshot in the header | ☐ NOT TESTED |
| 3.7 | No cross-event rows | no lap of this run attached to another event | ☐ NOT TESTED |

Read-only helper query (safe):

```sql
SELECT r.run_id, r.session_plan_id, r.event_id, r.session_type, r.status,
       COUNT(l.id) AS timed_laps
FROM session_runs r
LEFT JOIN lap_records l ON l.session_run_id = r.run_id AND l.lap_time_ms > 0
GROUP BY r.run_id ORDER BY r.created_at DESC LIMIT 5;
```

## 4. Driver assessment (capture free-text)

- Did the brief match the chosen objective? ______
- Were messages timely (not chatty)? ______
- Was any message distracting? ______
- Were valid vs invalid laps identified accurately? ______
- Did the Engineer ever appear to use the WRONG session? ______
- Was the reconnect behaviour understandable? ______
- Did the UI always show the correct event? ______

---

## What this branch guarantees offline (already proven; see the completion report)

- Recording blocks without full canonical context or a non-Practice plan (never inferred).
- One canonical session run owns the recording; laps persist bound to that run + stint (real-DB test).
- Reconnect resumes the same run only for the same event+plan; otherwise an explicit new run.
- Stale-run / other-event / duplicate / reset / zero-length laps are rejected.
- Event switching is blocked while a run is active.
- No setup value / strategy revision / pit instruction / PTT transcript is authored; DB v40 +
  Rule-Engine 46.0 unchanged.

## Sign-off

Live Activation 1 live certification: **NOT TESTED** — pending the driver completing every item above
on GT7 + PSVR2. Do not merge on offline evidence alone.
