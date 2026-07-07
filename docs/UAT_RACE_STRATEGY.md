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

## Group 53 additions (Phase 7 — live current-state replan input)

Group 52's replan foundation is now wired to the app's **existing read-only live
race-state source**. It reads live state, compares it to the pre-race plan, and shows
an **advisory-only** snapshot. It makes no pit call, sends no driver command, changes
no setup, needs no API key, and invents nothing.

### Which live fields exist (discovery)

From `telemetry.state.RaceStateTracker` + the last `GT7Packet`:

| Field | Source | Available? |
| --- | --- | --- |
| current lap | `tracker.laps_recorded` | ✅ live |
| remaining time (timed) | `tracker.computed_remaining_ms()` | ✅ live |
| remaining laps (lap race) | `tracker.laps_remaining` | ✅ live |
| fuel remaining % | `packet.fuel_level / packet.fuel_capacity` | ✅ live |
| live fuel burn / lap | `tracker.avg_fuel_per_lap` | ✅ live (feeds the snapshot) |
| current compound | `tracker._current_compound` | ⚠️ strategy/UI tag (GT7 doesn't broadcast it) |
| tyre age (laps) | — | ❌ **not tracked → missing** |
| pit stops completed | — | ❌ **not tracked → missing** |
| required compounds used | — | ❌ **not tracked → missing** |
| weather / damage / safety-car | — | ❌ not structured → missing |

**Consequence:** because tyre age and pit-stop count are not tracked live, a live
snapshot in this app is typically **LOW_CONFIDENCE** (tyre unknown) or
**INSUFFICIENT_EVIDENCE** (fuel/compound/distance unknown) — and it says so honestly.

### Modules

- `strategy/race_strategy_live_state.py` — read-only adapter. `build_replan_state_from_tracker`,
  `build_replan_state_from_live_packet`, `build_replan_state_from_dashboard_context`,
  `extract_live_replan_state`, `summarise_live_state_sources`. Populates only real
  fields; drops impossible values (fuel > capacity, negative laps); records the rest as
  missing. Never raises, never writes, no AI, no setup imports.
- `strategy/race_strategy_live_replan.py` — `build_live_replan_snapshot(*, pre_race_result,
  live_source=…, event_settings=…, generated_at=…)` → read-only `LiveReplanResult`
  (state, state_sources, readiness, snapshot, driver_message, missing_state, warnings,
  safety_notes, generated_at). Plus deterministic Fuji fixtures and `render_live_replan_text`.

### UI

The Group 52 placeholder is now a small read-only **Live Replan Readiness** group with a
**Refresh Live Replan Snapshot** button. It reads the live tracker/packet (read-only),
compares against the last-built Race Plan, and shows the status (still viable / needs
review / insufficient evidence), confidence, reason, and missing live state. No
auto-refresh loop, no voice, no pit call, no Apply — refresh is a manual click.

### Manual UAT (live path)

1–4. As above (confirm event, load session, open Strategy Builder, **Build Race Strategy**).
5. Start / connect live telemetry if available.
6. Under **Live Replan Readiness**, click **Refresh Live Replan Snapshot**.
7. Confirm current lap / fuel / remaining distance show only when genuinely available; tyre
   age and pit-stop count show as **missing** (the app does not track them live).
8. Confirm the snapshot says *still viable* / *needs review* / *insufficient evidence*.
9. Confirm the safety note *"Advisory only — no pit call, setup change, or driver command is
   applied"* is shown, and **no** pit call / setup recommendation / Apply control appears.

### Offline UAT helper

```python
from ui.race_strategy_uat import run_fuji_live_replan
r = run_fuji_live_replan("healthy")     # one-stop still viable, MEDIUM confidence
r = run_fuji_live_replan("fuel_short")  # plan needs review (fuel below expected)
r = run_fuji_live_replan("missing")     # INSUFFICIENT_EVIDENCE, missing state listed
```

---

## Known caveats

- SessionDB has no explicit tyre-wear or pit-loss column, so **tyre degradation is
  a disclosed lap-drift proxy** and **pit loss is manual / event-supplied**.
- The session selector lists recent sessions for the current **car + track**
  (layout is not stored per session, so layout match is informational).
- On Windows / Python 3.14, run UI test files individually (a known PyQt cross-file
  segfault); the Group 51 readiness/UAT suites are Qt-free and run together cleanly.
