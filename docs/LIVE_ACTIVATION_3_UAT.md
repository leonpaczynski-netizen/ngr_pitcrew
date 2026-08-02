# Live Activation 3 — On-Hardware UAT (GT7 + PSVR2)

Branch `live-activation-3-race-certification`. The third production telemetry seam through the
canonical event spine, applying the SAME authoritative-context activation pattern as
[Live Activation 1](LIVE_ACTIVATION_1_UAT.md) (Practice) and
[Live Activation 2](LIVE_ACTIVATION_2_UAT.md) (Qualifying) to a live **Race**: **live GT7 Race
recording against an explicitly active planned race activity, persisted under one canonical
`session_run`, with a phase-driven Race Engineer, deterministic advisory strategy, bounded PTT,
post-session integrity audit, and a guided race-day certification workflow.**

A race engineer talks by **phase** and **strategy-relevant event** — grid, lights-out, settled
racing, the pit sequence, the finish — not by a fixed lap cadence. The coordinator reuses the
generic LA1/LA2 recording lifecycle (activation gate, run FSM, reconnect, lap guard, persistence
port) composed with a new race engineer phase machine driven from the EXISTING canonical race-state
vocabulary (`telemetry.state.RacePhase` + `canonical_live_race_state.PitPhase`). Strategy advice
comes from the existing deterministic replan pipeline and stays advisory-only — no pit is ever
called, no setup ever applied.

**Every item below is `NOT TESTED` until the driver completes it on real hardware.** Automated and
simulated evidence can NEVER promote a physical checkpoint to PASS; only a result you record in the
certification panel can. Live certification remains explicitly `NOT TESTED`.

**Assumption to validate on hardware:** the race activation is driven by the PLANNED "race" activity
(the event's climax race), never inferred from GT7 telemetry (which auto-classifies any multi-car
lobby as a race). The race plan must belong to THIS event/car/track/layout (config_id coherence) or
activation is blocked with a distinct reason. Practice-development race runs (`long_race_run`,
`strategy_validation_run`) are recorded as PRACTICE, not as the event race.

---

## 0. Preparation

| # | Step | Expected | Result |
|---|------|----------|--------|
| 0.1 | Create or select ONE controlled event | Event visible + active | ☐ NOT TESTED |
| 0.2 | Select ONE car | Car shown in the context header | ☐ NOT TESTED |
| 0.3 | Build + confirm the **race setup**; approve a **race plan** for this event | Race sheet authored; approved strategy present | ☐ NOT TESTED |
| 0.4 | Start the planned **Race** activity from the programme | Objective shown; session type = Race | ☐ NOT TESTED |
| 0.5 | Press **Start Race** | App switches to the race setup + race shift RPM; the approved plan shows on the pit wall | ☐ NOT TESTED |
| 0.6 | Verify the diagnostics header reads **LIVE RACE DIAGNOSTICS** | Event ID, Session Plan ID, Session Type=Race, Recording State=not_started, Car, Setup Snapshot, Context Revision, Race Plan ID shown (full ids behind the expander) | ☐ NOT TESTED |
| 0.7 | Verify no active run exists | Recording State = not_started; no Session Run ID | ☐ NOT TESTED |
| 0.8 | Start GT7 telemetry (PS5 → app) | Telemetry = connected | ☐ NOT TESTED |

**Context-incomplete / plan-mismatch check:** if any required identity (event programme, event,
session plan, car, car-spec revision, driver-profile version, context revision) is unresolved, OR
the approved race plan was built for a different car/track (config_id mismatch), recording must be
**blocked** with the exact reason named — the app must NOT fall back to another event, infer Race
from telemetry, or drive a mis-scoped plan.

## 1. Live race run

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1.1 | With telemetry live + the race activity open, sit on the grid | One canonical Session Run ID appears; Recording State = recording; phase = waiting; engineer: "On the grid…" | ☐ NOT TESTED |
| 1.2 | Lights out — start racing | Phase → race-start; engineer: "Lights out. Clean getaway…" | ☐ NOT TESTED |
| 1.3 | Complete lap 1 | Phase → racing; header shows Lap 1; best lap set | ☐ NOT TESTED |
| 1.4 | Run several clean laps | Lap total climbs; best lap updates; fuel/pace KPIs track live | ☐ NOT TESTED |
| 1.5 | At the end of a lap where fuel/pace diverge | The engineer relays a deterministic strategy advisory (remain / save fuel / revise window) with a confidence + missing-evidence note; NO pit is called | ☐ NOT TESTED |
| 1.6 | Enter the pit lane | Phase → pit-entry; engineer HIGH-priority "Pit entry — limiter on." | ☐ NOT TESTED |
| 1.7 | Complete the stop and rejoin | Phase → pit-exit → racing; pit-stop count increments by one | ☐ NOT TESTED |
| 1.8 | Disconnect or interrupt telemetry once mid-race | Recording State = disconnected; no phantom lap; no false pit stop; lap total unchanged | ☐ NOT TESTED |
| 1.9 | Reconnect telemetry (same session) | Same Session Run ID resumes; Recording State = recording; NO duplicate laps | ☐ NOT TESTED |
| 1.10 | Take the chequered flag | Phase → finished; engineer: "Chequered flag…"; the voice queue clears (no lingering chatter) | ☐ NOT TESTED |
| 1.11 | Verify the engineer never chatters | One line per phase edge only; strategy advisory only on a real change | ☐ NOT TESTED |

## 2. PTT (bounded vocabulary)

Ask each while racing; the answer must come from the **live canonical race state**, never stale UI
text, and be honest when the data is unavailable.

| # | Ask | Expected | Result |
|---|-----|----------|--------|
| 2.1 | "Fuel?" | Current fuel in litres (or honest "no reading yet") | ☐ NOT TESTED |
| 2.2 | "Will I make it on fuel?" | Predicted finish fuel spare/short (or "can't predict yet") | ☐ NOT TESTED |
| 2.3 | "Laps remaining?" / "Time remaining?" | Laps to go / mm:ss (lap vs timed race) | ☐ NOT TESTED |
| 2.4 | "Position?" | P-number (or honest "GT7 isn't giving me one") | ☐ NOT TESTED |
| 2.5 | "How's my pace?" / "Delta?" | Up/down vs the plan | ☐ NOT TESTED |
| 2.6 | "Pit window?" / "Strategy?" | Stops remaining / plan summary (or honest "not settled yet") | ☐ NOT TESTED |
| 2.7 | "Tyres?" | Compound + age, or honest "GT7 doesn't always give me that" | ☐ NOT TESTED |
| 2.8 | "Push" / "Save fuel" / "Repeat" / "Quiet" | Acknowledged; repeat echoes the last answer | ☐ NOT TESTED |
| 2.9 | An out-of-vocabulary question | Honest refusal — no free-form dialogue, no fabricated answer | ☐ NOT TESTED |

## 3. Voice (PSVR2 audio)

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 3.1 | Race start / pit / finish cues are audible through the PSVR2 | Piper TTS (or SAPI fallback) speaks each phase-edge cue | ☐ NOT TESTED |
| 3.2 | Critical advice is not buried | Fuel/pit/finish cues are HIGH priority; low-value chatter never masks them | ☐ NOT TESTED |
| 3.3 | Two engineers never talk over each other | Only the race engineer speaks while the race run owns the voice | ☐ NOT TESTED |

## 4. Context protection

| # | Step | Expected | Result |
|---|------|----------|--------|
| 4.1 | Navigate between UI pages during the race | Every page shows the SAME event + run; race phase unchanged | ☐ NOT TESTED |
| 4.2 | Attempt to switch event WHILE recording | Blocked with a driver-facing message; complete/abandon first | ☐ NOT TESTED |
| 4.3 | End the run (End run & record) | If coherent: Recording State = completed and the run is history. If the post-session audit finds a problem: the run is **held for review** (not promoted), with the reason shown | ☐ NOT TESTED |
| 4.4 | Restart the app | Correct event/session restored; the completed run does NOT reopen as active | ☐ NOT TESTED |
| 4.5 | Confirm a Practice / Qualifying activity does NOT drive Race | Those activities use their own diagnostics/engineer, never the race phase machine | ☐ NOT TESTED |

## 5. Database + persistence verification

Read-only helper query (safe):

```sql
SELECT r.run_id, r.session_plan_id, r.event_id, r.session_type, r.status,
       COUNT(l.id) AS timed_laps
FROM session_runs r
LEFT JOIN lap_records l ON l.session_run_id = r.run_id AND l.lap_time_ms > 0
GROUP BY r.run_id ORDER BY r.created_at DESC LIMIT 5;
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 5.1 | One intended session run | exactly 1 `session_runs` row for the race plan, `session_type = Race` | ☐ NOT TESTED |
| 5.2 | Laps persisted once | timed `lap_records` for the laps driven; no duplicate `lap_num` | ☐ NOT TESTED |
| 5.3 | Correct relationships | run + laps carry the right `event_id`; run traces to the car-spec + race setup snapshot | ☐ NOT TESTED |
| 5.4 | No cross-event / cross-session rows | no lap of this run attached to another event or a Practice/Qualifying session | ☐ NOT TESTED |
| 5.5 | Reload after restart | the completed race reloads with correct event/car/track/layout identity | ☐ NOT TESTED |
| 5.6 | Invalid session is not promoted | if the audit flagged the session, no trusted track/setup/driver learning was promoted from it | ☐ NOT TESTED |

## 6. Guided race-day certification workflow

Open the **Race-Day Certification** panel on the Live Pit Wall (press **Rebuild from app state**).

| # | Step | Expected | Result |
|---|------|----------|--------|
| 6.1 | Rebuild the report | Environment/build + Identity + Integrity-audit stages auto-fill; every physical stage shows NOT_TESTED | ☐ NOT TESTED |
| 6.2 | Record each physical stage result (telemetry, practice, qualifying, race, voice, PTT, restart) | Only a manually recorded result changes the stage; a simulated pass is NOT credited | ☐ NOT TESTED |
| 6.3 | Verdict while any physical gate is NOT_TESTED | Never "Certified" — IN_PROGRESS at best | ☐ NOT TESTED |
| 6.4 | Record a FAIL/BLOCKED on any core stage | Verdict = FAILED | ☐ NOT TESTED |
| 6.5 | Export JSON + Markdown | Both reports written to `<config-dir>/race_certifications/`; automated/simulated/manual evidence clearly distinguished | ☐ NOT TESTED |
| 6.6 | Final verdict | Only **Certified** when every mandatory physical gate is manually PASS; **Conditionally certified** with documented non-core limitations; else FAILED / IN_PROGRESS | ☐ NOT TESTED |

## 7. Driver assessment (capture free-text)

- Did the race phases match what you were doing (grid / start / racing / pit / finish)? ______
- Was the strategy advisory timely, honest about missing evidence, and never a pit *command*? ______
- Did PTT answer from the live state (fuel, laps, position, pit window) and stay honest when unknown? ______
- Was the voice audible and calm under pressure through the PSVR2? ______
- Did reconnect behave (no duplicate laps, no false pit stop)? ______
- Did the completed race persist and reload correctly? ______
- Did the certification workflow read clearly and refuse to certify until you recorded the hardware results? ______

---

## What this branch guarantees offline (already proven; see the tests)

- Race recording blocks without full canonical context, on a non-Race plan (never inferred from
  telemetry), or when the race plan was built for a different car/track (config_id mismatch) —
  `test_live_race_activation.py`, `test_live_race_runtime.py`, `test_live_race_driving.py`.
- One canonical session run owns the recording; laps persist bound to that run + stint, stamped
  `session_type = Race`; the race phase machine + pit-stop count are driven from the canonical
  race-state signals; reconnect resumes the same run (no duplicate laps); event switching is blocked
  while recording.
- Strategy advice comes from the existing deterministic replan pipeline and stays advisory-only;
  unknown evidence is never treated as safe.
- The post-session integrity audit blocks promotion of an invalid session (invalid/placeholder
  identity, wrong session type, duplicate/orphan laps, contradictory car/track) — never deleting data
  (`test_live_race_integrity.py`).
- Bounded PTT answers come from the canonical race state, are honest when unknown, and refuse
  out-of-vocabulary questions (`test_race_ptt_answers.py`).
- The certification workflow cannot mark a physical gate PASS from automated/simulated evidence, and a
  Certified verdict is impossible while a mandatory physical gate is NOT_TESTED
  (`test_race_certification.py`, `test_race_certification_ui.py`).
- No setup value / pit instruction is ever authored or executed; DB v40 + Rule-Engine 46.0 unchanged;
  no migration; user runtime data untouched.

## Sign-off

Live Activation 3 live certification: **NOT TESTED** — pending the driver completing every physical
item above on GT7 + PSVR2 and recording it in the certification panel. Do not merge on offline
evidence alone; do not label the system race-day certified while any mandatory hardware gate is
NOT_TESTED.
