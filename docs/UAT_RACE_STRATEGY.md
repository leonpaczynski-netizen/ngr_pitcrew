# Race Strategy Brain — Manual UAT Guide

> Covers the driver-facing Race Plan surface in the Strategy Builder tab
> (Groups 48 → 51). This is a **read-only, evidence-based** strategy tool: it
> never changes or applies a car setup, never needs an API key, and is honest
> about what evidence it has and what is missing.

---

## What the Race Plan surface does

```
Event settings + SessionDB practice laps
   → strategy evidence (measured / event / derived / missing)
   → legal candidates
   → total-race-time scoring
   → recommended plan + confidence + explanation
```

It answers, at a glance:

- **Which session is the strategy using?** (session selector + status line)
- **Is the session for the right car / track / layout?** (match status)
- **What evidence did it find? What is missing?** (readiness "Found" / "Missing")
- **Can I trust this recommendation?** (readiness level + confidence)
- **What should I record next?** (next-best-action)

---

## Group 51 additions (Phase 5 — UAT hardening & session polish)

- **Readiness / evidence checklist** (`ui/race_strategy_readiness_vm.py`,
  `build_race_plan_readiness`): grades `READY / PARTIAL / LOW_CONFIDENCE /
  INSUFFICIENT_EVIDENCE` from the session samples + event settings, with per-field
  statuses, a `Found` / `Missing` list, and a specific `next_best_action`.
- **Session selection polish** (`build_session_diagnostics`,
  `list_recent_matching_sessions`): a small read-only session dropdown (recent
  sessions for this car+track) + Refresh, a session-status line showing car /
  track / match / clean-lap count / fuel + tyre availability. Selecting
  "Active session (auto)" uses the currently resolved session.
- **Event settings validation** (`validate_event_settings`): honest warnings for
  missing race duration, refuel rate, pit loss, car, track — never blocks unless
  the pipeline truly cannot run (no race length at all).
- **Better empty / missing states** (`empty_state_messages`): short, actionable
  lines for every case (no session, not found, no laps, no clean laps, car/track
  mismatch, fuel/tyre/compound missing, race length / refuel / pit loss missing).
  No vague "strategy failed" wording.

### Readiness levels

| Level | Meaning |
| --- | --- |
| `READY` | Clean laps, fuel, tyre proxy, compound pace, pit loss, refuel, race length all present. |
| `PARTIAL` | Core + pit maths present, but tyre degradation or compound pace missing. |
| `LOW_CONFIDENCE` | Laps + fuel + race length present, but pit loss or refuel rate missing. |
| `INSUFFICIENT_EVIDENCE` | No clean laps (< 3), or no fuel, or no race length — no recommendation. |

---

## Recommended manual UAT scenario

```
Car:        Porsche 911 RSR '17
Track:      Fuji Full Course
Race:       50 minutes
Tyre wear:  8×
Fuel:       3×
Refuel rate: 1 L/sec
```

### Steps

1. Open **Event Planner** and confirm Porsche RSR / Fuji / race settings (50 min,
   tyre 8×, fuel 3×, refuel 1 L/s). Set as active.
2. Record or load a **practice session** with clean laps (ideally 8+ laps on one
   compound so tyre drop-off can be derived).
3. Open **Strategy Builder** → the **Race Plan** group.
4. Confirm the **Session** selector shows recent sessions and the status line
   reports the selected session's car / track / clean-lap count.
5. Confirm the **match status** ("Session matches the current event.") is visible.
6. Confirm the **readiness level** and any **missing evidence** are shown, with a
   **next-best-action** line.
7. Click **Build Race Strategy**.
8. Confirm the **one-stop vs two-stop total race time** comparison appears in the
   candidate table (one-stop should win here — the 1 L/s refuel makes the extra
   stop expensive).
9. Confirm the recommended plan, confidence, stint plan, evidence sources, risk
   flags, and next-best-action guidance are all visible.
10. Confirm **no setup recommendations** are created.
11. Confirm **no setup Apply / approve controls** appear anywhere in the surface.

### Expected result

- Readiness `READY` (with a full session) or `LOW_CONFIDENCE` (if refuel/pit loss
  are unset).
- One-stop `~51:52`, two-stop `~52:28` (`+36.0s`).
- The **push** two-stop plan is flagged *"rear traction fragile — push strategy
  not recommended"* and is **not** recommended.
- Evidence sources show race pace + fuel as **SessionDB measured**, tyre
  degradation as **derived (lap-drift proxy)**, refuel/pit loss as **event / manual**.

---

## Offline UAT helper (no game, no API key)

`ui/race_strategy_uat.py` reproduces the scenario deterministically in-memory:

```python
from ui.race_strategy_uat import build_fuji_uat_context, run_fuji_uat

ctx = build_fuji_uat_context()          # readiness + diagnostics from seeded SessionDB
print(ctx.readiness.overall_readiness)  # READY
print(ctx.diagnostics.message)          # "Using session 1: 12 clean lap(s), fuel yes, tyre proxy yes."

result = run_fuji_uat()                 # full session-backed recommendation
# result.recommendation.recommended.candidate_id == "1stop"
```

`build_fuji_uat_context(n_laps=4, fuel=0.0)` simulates an incomplete session so you
can see the readiness drop and the missing-evidence guidance appear.

---

## Group 52 additions (Phase 6 — UAT harness & read-only replan foundation)

### Structured UAT verification harness

`ui/race_strategy_uat.py::run_fuji_race_plan_uat_check()` runs the whole Race Plan
surface offline and returns a **structured, testable** `FujiUatCheckResult` (not just
printed text): event/session validation, readiness level, clean-lap count, fuel + tyre
evidence flags, candidate count, recommended plan, one-stop vs two-stop total times,
whether the push plan was rejected, missing evidence, warnings, a `safety_checks` dict,
and `passed` / `failure_reasons`.

```python
from ui.race_strategy_uat import run_fuji_race_plan_uat_check
c = run_fuji_race_plan_uat_check()
assert c.passed and c.readiness_level == "READY"
assert c.one_stop_total_time == "51:52.0" and c.two_stop_total_time == "52:28.0"
assert c.push_plan_rejected_or_not_recommended
```

**UAT outcome (Group 52): no defects found.** The full and incomplete Porsche/Fuji
scenarios both behave correctly — the surface never crashes, keeps missing evidence
visible, keeps legal candidates only, does not recommend the rear-fragile push plan,
and emits no false-certainty wording. The behaviours are pinned by
`tests/test_group52_race_plan_uat_remediation.py` as regression guards.

### Read-only live-replan readiness foundation (NOT live yet)

`strategy/race_strategy_replan.py` is a **pure, advisory-only** foundation for a future
live/mid-race replan. It does **not** connect live telemetry, make pit calls, send driver
commands, change setup, or write anything.

- `RaceReplanState` — reported current race state (current lap, fuel remaining %, current
  compound, tyre age, remaining laps/time, pit stops completed, …). Every field defaults
  to **unknown** (`None`); nothing is fabricated, and **unknown tyre state is never treated
  as safe**.
- `validate_replan_state(state)` — honest per-field validation (missing fuel / compound /
  remaining distance / tyre age flagged, never crashes).
- `assess_replan_readiness(state)` — `READY / PARTIAL / LOW_CONFIDENCE /
  INSUFFICIENT_EVIDENCE` (no fuel/compound/distance → INSUFFICIENT; tyre unknown →
  LOW_CONFIDENCE).
- `build_replan_snapshot(*, pre_race_result, state, …)` — read-only `RaceReplanSnapshot`:
  is the pre-race plan still viable? It compares reported fuel remaining to the pre-race
  burn rate over the laps to the next planned stop; advisory options are the pre-race
  Group 48 scored candidates (labelled *pre-race estimates* — no invented live numbers);
  confidence is capped at MEDIUM (LOW when tyre is unknown); `INSUFFICIENT_EVIDENCE` when
  critical state or a pre-race plan is missing. Every snapshot carries the standing note:
  *"Advisory only — no pit call, setup change, or driver command is applied."*

```python
from strategy.race_strategy_replan import RaceReplanState, build_replan_snapshot
from ui.race_strategy_uat import run_fuji_uat
snap = build_replan_snapshot(
    pre_race_result=run_fuji_uat(),
    state=RaceReplanState(current_lap=10, fuel_remaining_pct=8.0, current_compound="RM",
                          tyre_age_laps=10, remaining_laps=20, pit_stops_completed=0))
# snap.current_plan_still_viable == False  (fuel below expected)  → advisory options shown
```

The Strategy Builder shows a **read-only "Live Replan Readiness" placeholder** that says
live telemetry is *not connected yet* and lists the state a future replan will need. It is
a labelled wiring point only — no button, no loop, no action.

---

## Safety guarantees (unchanged since Group 43)

- No API key required to build a Race Plan.
- No setup Apply / approve controls in the strategy surface.
- No setup recommendations created; no writes to `data/setup_history.json`.
- SessionDB strategy access is **read-only**.
- Missing evidence stays visible; nothing is fabricated.
- The Setup Apply-gate predicate and the disabled AI-Build path are untouched.

---

## Known caveats

- SessionDB has no explicit tyre-wear or pit-loss column, so **tyre degradation is
  a disclosed lap-drift proxy** and **pit loss is manual / event-supplied**.
- The session selector lists recent sessions for the current **car + track**
  (layout is not stored per session, so layout match is informational).
- On Windows / Python 3.14, run UI test files individually (a known PyQt cross-file
  segfault); the Group 51 readiness/UAT suites are Qt-free and run together cleanly.
