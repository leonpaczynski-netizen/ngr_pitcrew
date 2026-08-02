# Live Activation 2 — On-Hardware UAT (GT7 + PSVR2)

Branch `live/program3-activation2-qualifying-2026-08-01`. The second production telemetry seam
through the canonical event spine, applying the SAME authoritative-context activation pattern as
[Live Activation 1](LIVE_ACTIVATION_1_UAT.md) to a live **Qualifying** session: **live GT7
Qualifying recording against an explicitly active planned qualifying activity, persisted under one
canonical `session_run`, with a phase-driven Qualifying Engineer using that same authoritative
context.**

A qualifying engineer talks by **phase**, not lap count, and cares about ONE thing — the best
flying lap. The coordinator reuses the generic LA1 recording lifecycle (activation gate, run FSM,
reconnect, lap guard, persistence port) composed with the existing qualifying **phase machine**
(`strategy/qualifying_state_machine.py`): preparation → out-lap → flying lap → lap-complete →
cooldown. The phase is driven from telemetry: the **on-track flag's** False→True edge is the
pit-exit (out-lap), True→False is the box; completed laps advance out-lap → flying → complete.

Scope is Qualifying only. Broader PTT, per-lap Race-Strategy snapshots and damage/rain/fuel/tyre
replanning are **out of scope** and must stay inert.

**Every item below is `NOT TESTED` until the driver completes it on real hardware.** Claude cannot
mark any of these PASS; live certification remains explicitly `NOT TESTED`.

**Assumption to validate on hardware:** the coordinator models each attempt as *pit-exit → out-lap
→ flying lap → report*, i.e. a fresh attempt is bracketed by leaving/returning to the pits (the
standard league qualifying-simulation flow). Consecutive flying laps taken without boxing between
them are recorded, but only the first flying lap of each pit-exit-initiated attempt is scored as a
personal-best candidate by the phase machine. Confirm whether your qualifying flow needs
consecutive-hot-lap scoring (a follow-up if so). GT7 track-limits deletions are not captured
per-lap yet, so a deleted flying lap is not sourced from telemetry (the domain machine already
handles it once that capture exists).

---

## 0. Preparation

| # | Step | Expected | Result |
|---|------|----------|--------|
| 0.1 | Create or select ONE controlled event | Event visible + active | ☐ NOT TESTED |
| 0.2 | Select ONE car | Car shown in context header | ☐ NOT TESTED |
| 0.3 | Start the planned **Qualifying simulation** activity from the programme | Objective shown; session type = Qualifying | ☐ NOT TESTED |
| 0.4 | Press **Begin Qualifying** | App switches to the qualifying setup + qualifying shift RPM; qualifying compound (softest dry, or rain tyre when wet) on the qualifying sheet | ☐ NOT TESTED |
| 0.5 | Verify the diagnostics header reads **LIVE QUALIFYING DIAGNOSTICS** | Event ID, Session Plan ID, Session Type=Qualifying, Recording State=not_started, Car, Setup Snapshot, Context Revision shown (full ids behind the expander) | ☐ NOT TESTED |
| 0.6 | Verify no active run exists | Recording State = not_started; no Session Run ID | ☐ NOT TESTED |
| 0.7 | Start GT7 telemetry (PS5 → app) | Telemetry = connected | ☐ NOT TESTED |

**Context-incomplete check:** if any required identity (event programme, event, session plan, car,
car-spec revision, driver-profile version, context revision) is unresolved, recording must be
**blocked** with the exact missing requirement named — the app must NOT fall back to another event
or infer Qualifying from telemetry.

## 1. Live qualifying run

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1.1 | With telemetry live + the qualifying activity open, stay in the garage | One canonical Session Run ID appears; Recording State = recording; phase = preparation; engineer: "Focus — this is one lap…" | ☐ NOT TESTED |
| 1.2 | Leave the pits (go on track) | Phase → out-lap; attempt = 1; engineer prompts to build heat into the tyres toward the optimal window | ☐ NOT TESTED |
| 1.2a | Work the tyres up during the out-lap | Ongoing tyre-temp updates as the temps rise (cold → coming up → **up to temp**); spoken only on a status change, ending with "tyres are up to temp — this is your lap"; a warning if you overheat them | ☐ NOT TESTED |
| 1.3 | Complete the out-lap (cross the line) | Phase → flying lap; engineer terse: "This is your lap — commit." | ☐ NOT TESTED |
| 1.4 | Complete the flying lap | Phase → lap-complete; header shows **Best <time>**; if it's your fastest, engineer: "Personal best, <time>…" | ☐ NOT TESTED |
| 1.5 | Cool down, then box | Phase → preparation | ☐ NOT TESTED |
| 1.6 | Leave the pits again for a second attempt | Phase → out-lap; attempt = 2 | ☐ NOT TESTED |
| 1.7 | Set a FASTER flying lap | Best updates to the new time; engineer reports the new personal best | ☐ NOT TESTED |
| 1.8 | Set a SLOWER flying lap on a later attempt | Best does NOT change; engineer reports the gap ("… off your best") | ☐ NOT TESTED |
| 1.9 | Disconnect or interrupt telemetry once | Recording State = disconnected; no phantom lap finalised; best unchanged | ☐ NOT TESTED |
| 1.10 | Reconnect telemetry (same session) | Same Session Run ID resumes; Recording State = recording | ☐ NOT TESTED |
| 1.11 | Verify the engineer never chatters | One line per phase edge only; silent within a phase | ☐ NOT TESTED |

## 2. Context protection

| # | Step | Expected | Result |
|---|------|----------|--------|
| 2.1 | Navigate between UI pages during the run | Every page shows the SAME event + run; qualifying phase unchanged | ☐ NOT TESTED |
| 2.2 | Attempt to switch event WHILE recording | Blocked with a driver-facing message; must complete/abandon first — no silent switch | ☐ NOT TESTED |
| 2.3 | End the run (End run & record) | Recording State = completed; run is history | ☐ NOT TESTED |
| 2.4 | Restart the app | Correct event/session restored; the completed run does NOT reopen as active | ☐ NOT TESTED |
| 2.5 | Confirm a Practice activity does NOT drive qualifying | Running a Practice activity uses the Practice diagnostics/engineer, never the qualifying phase machine | ☐ NOT TESTED |

## 3. Database verification

Use the diagnostics header + a safe read-only query to confirm, for the run above:

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 3.1 | One intended session run | exactly 1 `session_runs` row for the qualifying plan | ☐ NOT TESTED |
| 3.2 | Correct stints | opening stint present, bound to the run | ☐ NOT TESTED |
| 3.3 | Laps persisted | timed `lap_records` for the flying laps driven, session_type = Qualifying | ☐ NOT TESTED |
| 3.4 | No duplicate lap numbers | no repeated `lap_num` for the run | ☐ NOT TESTED |
| 3.5 | Correct event relationship | run + laps carry the right `event_id` | ☐ NOT TESTED |
| 3.6 | Correct car + setup relationship | run traces to the car-spec + the qualifying setup snapshot in the header | ☐ NOT TESTED |
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

- Did the phase cues match what you were doing (prep / out-lap / flying / report)? ______
- Was the personal-best tracking accurate? ______
- Were the messages timely and terse on the flying lap (not distracting)? ______
- Did the pit-exit / box detection track leaving and returning to the pits correctly? ______
- Did the Qualifying Engineer ever appear to use the WRONG session or talk over another engineer? ______
- Was the reconnect behaviour understandable? ______
- Did the UI always show the correct event and the qualifying diagnostics? ______

---

## What this branch guarantees offline (already proven; see the tests)

- Recording blocks without full canonical context or on a non-Qualifying plan (never inferred from
  telemetry) — `test_live_qualifying_runtime.py`, `test_live_qualifying_driving.py`.
- One canonical session run owns the recording; laps persist bound to that run + stint (real-DB
  driving test), stamped session_type = Qualifying.
- The qualifying phase machine is driven from telemetry: on-track edges → pit-exit/box; completed
  laps → out-lap → flying → complete; personal best tracked across attempts.
- A Practice activity does NOT activate qualifying (the two coordinators are mutually exclusive on
  the open run's activity type).
- Reconnect resumes the same run only for the same event+plan; event switching is blocked while a
  run is active.
- The Qualifying Engineer speaks once per phase edge (anti-chatter) and does not talk over the
  session engineer.
- No setup value / strategy revision / pit instruction / PTT transcript is authored; DB v40 +
  Rule-Engine 46.0 unchanged.

## Sign-off

Live Activation 2 live certification: **NOT TESTED** — pending the driver completing every item
above on GT7 + PSVR2. Do not merge on offline evidence alone.
