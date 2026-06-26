# Group 15 — AI Engineering Context Remediation Plan

> **Status:** COMPLETE — Awaiting Runtime Retest (2026-06-23)
> **Source audit:** `/docs/AI_ENGINEERING_VALIDATION_REPORT.md` (2026-06-23)
> **Build baseline:** 426/431 pass. Last defect IDs: DEF-P1-012, DEF-P2-035. Last AWR: AWR-057.
> **Post-implementation:** 513/518 pass. 87 tests added. AWR-058–069 all created.
> **Read before editing:** `PROJECT_STATE.md`, then `MASTER_TESTING_REGISTER.md`.

---

## New Defects Assigned (Group 15)

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| DEF-P1-013 | P1 | Strategy Analysis RaceParams missing race_type, tuning_locked, BoP, allowed_tuning | **AWR-058** |
| DEF-P1-014 | P1 | Practice Analysis history always empty — car_id hardcoded to 0 | **AWR-059** |
| DEF-P2-036 | P2 | PTT coaching omits car_name, car_specs, current compound | **AWR-064** |
| DEF-P2-037 | P2 | PTT setup advice reads stale saved setup instead of active editor setup | **AWR-065** |
| DEF-P2-038 | P2 | BoP status absent from strategy and practice prompts | **AWR-060** |
| DEF-P2-039 | P2 | Available tyres not listed in strategy, practice, or build-setup prompts | **AWR-061** |
| DEF-P2-040 | P2 | Driver feedback table not queried in strategy or practice analysis | **AWR-062** |
| DEF-P2-041 | P2 | Previous AI recommendations not fed into strategy or practice prompts | **AWR-063** |
| DEF-P3-009 | P3 | Race strategy prompt does not identify timed races | **AWR-066** |
| DEF-P3-010 | P3 | Build Car Setup prompt missing race context (tyre wear, fuel mult, avail/req tyres) | **AWR-067** |
| DEF-P3-011 | P3 | Data quality annotations absent from strategy and practice prompts | **AWR-068** |
| DEF-P3-012 | P3 | validate_ai_setup_response() not applied to Strategy Analysis output | **AWR-069** |

AWRs assigned: **AWR-058 through AWR-069** (one per defect, runtime verification required after fix).

---

## Recommended Fix Order

```
1. DEF-P1-013 — Strategy RaceParams fields (prerequisite for DEF-P2-038, DEF-P3-009)
2. DEF-P1-014 — Practice history car_id (prerequisite for DEF-P2-040, DEF-P2-041)
3. DEF-P2-038 — BoP status in strategy/practice prompts (depends on DEF-P1-013 data path)
4. DEF-P2-039 — Available tyres in all prompts
5. DEF-P2-040 — Driver feedback in practice analysis (depends on DEF-P1-014 car_id fix)
6. DEF-P2-041 — Previous AI recommendations in practice analysis (same dependency)
7. DEF-P2-036 — PTT coaching car context
8. DEF-P2-037 — PTT setup advice active setup
9. DEF-P3-009 — Timed race indication in strategy prompt (depends on DEF-P1-013)
10. DEF-P3-010 — Build Car Setup race context
11. DEF-P3-011 — Data quality annotations
12. DEF-P3-012 — validate_ai_setup_response on strategy output
```

---

---

## DEF-P1-013 — Strategy Analysis RaceParams missing race_type, tuning_locked, BoP, allowed_tuning

### Root Cause

`_run_ai_analysis()` in `ui/dashboard.py` builds `race_params` at lines 3158–3167:

```python
race_params = {
    "track":                _sc.get("track", ""),
    "total_laps":           total_laps,
    "tyre_wear_multiplier": float(_sc.get("tyre_wear_multiplier", 1.0)),
    "fuel_burn_per_lap":    self._computed_fuel_burn_lpl(),
    "refuel_speed_lps":     float(_sc.get("refuel_speed_lps", 10.0)),
    "pit_loss_secs":        float(_sc.get("pit_loss_secs", 23.0)),
    "min_mandatory_stops":  _mandatory_stops,
    "mandatory_compounds":  _mandatory_cpds,
}
```

Four fields present in `RaceParams` (added in Group 4 for practice analysis) are never populated for the strategy path: `race_type`, `duration_mins`, `tuning_locked`, `allowed_tuning`. `RaceParams(**race_params)` at line 3171 uses defaults `race_type="lap"`, `duration_mins=0`, `tuning_locked=False`, `allowed_tuning=[]`.

`_build_race_prompt()` in `ai_planner.py` does not inject a tuning constraint block and has no timed-race identification.

### Runtime Data Path

```
_on_event_set_active()
  → strat["race_type"]                = _evt_race_type.currentText() (e.g. "timed")
  → strat["race_duration_minutes"]    = _evt_duration.value()
  → strat["tuning"]                   = _evt_tuning.isChecked()
  → strat["allowed_tuning_categories"] = [code for checked cats]
  → strat["bop"]                      = _evt_bop.isChecked()
  → self._config["strategy"] = strat

_run_ai_analysis()
  _sc = self._config.get("strategy", {})
  race_params = { ... }  ← currently missing the 5 fields above
  params = RaceParams(**race_params)  ← defaults used for missing fields
  _build_race_prompt(params, ...)     ← no tuning or race_type awareness
```

All five values ARE in `_sc` at call time. The fix is purely additive to the `race_params` dict.

### Proposed Fix

**File: `ui/dashboard.py` — `_run_ai_analysis()` (~line 3158)**

Add to `race_params`:
```python
"race_type":     _sc.get("race_type", "lap"),
"duration_mins": int(_sc.get("race_duration_minutes", 0)),
"tuning_locked": not bool(_sc.get("tuning", False)),
"allowed_tuning": _sc.get("allowed_tuning_categories") or [],
"bop":           bool(_sc.get("bop", False)),
```

Note: `not bool(_sc.get("tuning", False))` matches the existing practice analysis pattern from Group 12a: absent `"tuning"` key → defaults to `False` → `tuning_locked = True` (safe default = locked).

**File: `strategy/ai_planner.py` — `_build_race_prompt()` (~line 444)**

Add `tuning_block` injection using the same inline pattern as `_build_practice_prompt()`. After `rules_block = _race_rules_block(params)`:

```python
tuning_block = ""
if params.tuning_locked:
    tuning_block = (
        "\n## EVENT RULES — TUNING LOCKED\n"
        "Do NOT recommend any setup changes. "
        "Focus on pit timing, compound choice, and fuel targets only.\n"
    )
elif params.allowed_tuning:
    _locked = [c for c in _ALL_TUNING_CATS if c not in params.allowed_tuning]
    tuning_block = (
        f"\n## EVENT TUNING RESTRICTIONS\n"
        f"Allowed to modify: {', '.join(params.allowed_tuning)}\n"
        f"LOCKED (do not recommend changes): {', '.join(_locked)}\n"
        f"Only advise on ALLOWED areas.\n"
    )
bop_line = ""
if getattr(params, "bop", False):
    bop_line = "- BoP: ON — weight and power are fixed by regulation\n"
```

Inject `tuning_block` and `bop_line` into the return string.

Also add `bop: bool = False` to the `RaceParams` dataclass (line ~69 in `ai_planner.py`).

### Files to Change
- `ui/dashboard.py` — `_run_ai_analysis()`: add 5 fields to `race_params`
- `strategy/ai_planner.py` — `RaceParams` dataclass: add `bop: bool = False`
- `strategy/ai_planner.py` — `_build_race_prompt()`: add tuning block + bop line injection

### Acceptance Criteria (AWR-058)
1. Set event: Timed Race, 60 min, BoP ON, tuning locked. Set active. Run Strategy Analysis (`GT7_AI_DEBUG=1`).
2. Prompt contains "TUNING LOCKED" block.
3. Set event: Lap Race, BoP ON, suspension only. Prompt contains "EVENT TUNING RESTRICTIONS" with locked categories listed.
4. Set event: Lap Race, no BoP, free tuning. No TUNING block appears.
5. `bop: bool` in `RaceParams` does not break existing `RaceParams(**race_params)` call in practice path (practice path doesn't pass `bop` → defaults to `False`).

---

## DEF-P1-014 — Practice Analysis history always empty — car_id hardcoded to 0

### Root Cause

`_run_practice_analysis()` `_worker()` closure in `ui/dashboard.py` at line 3316:

```python
def _worker():
    hist: dict = {}
    try:
        from data.session_db import SessionDB as _DB
        import os
        if os.path.exists("data/gt7_sessions.db"):
            _db = _DB("data/gt7_sessions.db")   # new connection, not self._db
            car_id = 0                           # ← ALWAYS WRONG
            track  = race_params.get("track", "")
            hist = _db.get_car_track_summary(car_id, track)
            _db.close()
    except Exception:
        hist = {}
```

`get_car_track_summary(0, track)` queries `WHERE sessions.car_id = 0 AND sessions.track = ?`. No session is stored with `car_id = 0`. The result is always empty. Additionally, a new `SessionDB` connection is opened instead of reusing `self._db`.

### Runtime Data Path

```
_on_event_set_active()
  → strat["car"] = self._current_car_name   (e.g. "Honda NSX '17")

_load_car_specs_for_current()             → returns (_car_name, _car_specs)
  reads: self._config.get("strategy", {}).get("car", "")

session_db.get_car_id(car_name)           → looks up cars.id WHERE cars.name = ?
  ← returns correct car_id (e.g. 7) if car registered in DB

_run_practice_analysis() _worker()
  car_id = 0    ← wrong; should be session_db.get_car_id(_car_name)
```

The correct `car_id` can be retrieved from `self._db.get_car_id(car_name)`. This method exists in `session_db.py`. Capturing `self._db` and `_car_name` in the closure before the thread starts (main-thread read, thread-safe since both are set before the thread spawns) avoids any cross-thread DB access issues.

### Proposed Fix

**File: `ui/dashboard.py` — `_run_practice_analysis()` (~line 3297–3334)**

Before `_threading.Thread(target=_worker, daemon=True).start()`, capture:
```python
_hist_db   = self._db          # reuse existing connection; None if DB not open
_hist_car  = _car_name         # already captured above this point
_hist_track = race_params.get("track", "")
```

Replace the `_worker()` history block:
```python
hist: dict = {}
if _hist_db is not None:
    try:
        _car_id_hist = _hist_db.get_car_id(_hist_car) if _hist_car else 0
        hist = _hist_db.get_car_track_summary(_car_id_hist, _hist_track)
    except Exception:
        hist = {}
```

This eliminates the new DB connection, eliminates `car_id = 0`, and uses the correct car ID.

**Fallback behaviour:** If `get_car_id()` returns 0 (car not yet in DB), `get_car_track_summary(0, track)` returns empty — same result as before, but no longer structurally wrong. The car will be in the DB after its first session is opened via `_on_live_mode_changed()`.

### Files to Change
- `ui/dashboard.py` — `_run_practice_analysis()`: capture `_hist_db`, `_hist_car`, `_hist_track` before thread; replace worker's history block

### Acceptance Criteria (AWR-059)
1. After 3+ sessions on the same car+track combination, run Practice Analysis (`GT7_AI_DEBUG=1`).
2. Prompt must contain actual values in the historical context block (e.g. `Best lap: 1:42.345` not `No historical data`).
3. `_hist_db.get_car_id("Honda NSX '17")` returns the car's DB id (not 0).
4. No new `SessionDB` connection opened in the worker thread.

---

## DEF-P2-036 — PTT coaching omits car_name, car_specs, current compound

### Root Cause

`_handle_trigger_inner()` in `voice/query_listener.py` at lines 471–475:

```python
_sc = self._config.get("strategy", {})
_allowed = _sc.get("allowed_tuning_categories", []) or None
_locked  = not bool(_sc.get("tuning", True))
response = da.build_coaching_response(
    allowed_tuning=_allowed, tuning_locked=_locked)
```

`car_name`, `car_specs`, and `compound` are all left at their default empty values. `_car_track_header()` inside the coaching prompt returns only the track line. The coaching AI cannot reference the car's drivetrain, PP rating, aspiration, or current tyre compound.

### Runtime Data Path

```
config["strategy"]["car"]                 → car name string (e.g. "Honda NSX '17")
config["strategy"]["mandatory_compounds"] → compound string (e.g. "Racing Medium")

DrivingAdvisor._car_track_header(car_name, car_specs)
  → "Car: Honda NSX '17 | FR | NA | 530 hp | 1370 kg" if car_name and car_specs set
  → "" if car_name=""  (current PTT behaviour)
```

`QueryListener` already has `self._config`. It needs `car_specs` — a `dict` loaded from `car_specs.json`. The `DrivingAdvisor` itself has no car-specs-loading capability.

### Proposed Fix

**File: `voice/query_listener.py` — `__init__()`**

Add:
```python
self._car_specs_ref: dict = {}   # populated via update_car_specs()
```

Add a new method:
```python
def update_car_specs(self, car_specs: dict) -> None:
    """Called from dashboard whenever the active car changes."""
    self._car_specs_ref = car_specs or {}
```

**File: `voice/query_listener.py` — `_handle_trigger_inner()` (~line 471)**

```python
_sc       = self._config.get("strategy", {})
_allowed  = _sc.get("allowed_tuning_categories", []) or None
_locked   = not bool(_sc.get("tuning", True))
_car_name = _sc.get("car", "")
_compound = _sc.get("mandatory_compounds", "")
_car_specs = getattr(self, "_car_specs_ref", {})
response = da.build_coaching_response(
    car_name=_car_name, car_specs=_car_specs,
    allowed_tuning=_allowed, tuning_locked=_locked,
    compound=_compound)
```

Apply the same addition to the `setup_advice` branch:
```python
response = da.build_setup_advice_response(
    setup,
    car_name=_car_name, car_specs=_car_specs,
    allowed_tuning=_allowed, tuning_locked=_locked,
    compound=_compound)
```

**File: `ui/dashboard.py` — wherever `_query_listener` is wired up**

After `self._query_listener = QueryListener(...)`, and whenever the active car changes (in `_on_event_set_active()` or wherever `_car_specs` is set), call:
```python
if hasattr(self, "_query_listener"):
    _, _ql_specs = self._load_car_specs_for_current()
    self._query_listener.update_car_specs(_ql_specs)
```

### Files to Change
- `voice/query_listener.py` — `__init__()`: add `_car_specs_ref`; `update_car_specs()`: new method; `_handle_trigger_inner()`: pass car_name, car_specs, compound
- `ui/dashboard.py` — wherever active car changes: call `_query_listener.update_car_specs()`

### Acceptance Criteria (AWR-060)
1. Select a car. Trigger PTT coaching. Response references car name (e.g. "NSX").
2. Set compound to Racing Medium. Trigger PTT coaching. Response mentions compound.
3. `_handle_trigger_inner` source contains `"car_name"` in `build_coaching_response` call.
4. `_handle_trigger_inner` source contains `"car_name"` in `build_setup_advice_response` call.

---

## DEF-P2-037 — PTT setup advice reads stale saved setup instead of active editor setup

### Root Cause

`_handle_trigger_inner()` at lines 480–486:

```python
setup = self._config.get("car_setup", {}).get("setups", [{}])
response = da.build_setup_advice_response(
    setup[0] if setup else {}, ...)
```

`config["car_setup"]["setups"]` is the list of SAVED setups from `config.json`. When no setup has been saved, this is `[{}]`. When a setup was saved previously, it may be stale (different track, different car, user has changed values in the editor since saving). The active Setup Builder editor state (`_current_setup_dict()` in dashboard.py) is not accessible here.

### Proposed Fix

**File: `voice/query_listener.py` — `__init__()`**

Add:
```python
self._active_setup_getter = None   # Callable[[], dict] | None
```

Add a new method:
```python
def set_active_setup_getter(self, getter) -> None:
    """Register a callable that returns the current editor setup dict."""
    self._active_setup_getter = getter
```

**File: `voice/query_listener.py` — `_handle_trigger_inner()` setup_advice branch (~line 480)**

```python
if self._active_setup_getter is not None:
    setup = self._active_setup_getter()
else:
    _saved = self._config.get("car_setup", {}).get("setups", [{}])
    setup = _saved[0] if _saved else {}
response = da.build_setup_advice_response(setup, ...)
```

**File: `ui/dashboard.py` — `_query_listener` wiring**

```python
if hasattr(self, "_query_listener") and hasattr(self, "_current_setup_dict"):
    self._query_listener.set_active_setup_getter(self._current_setup_dict)
```

### Files to Change
- `voice/query_listener.py` — `__init__()`, new `set_active_setup_getter()`, `_handle_trigger_inner()`
- `ui/dashboard.py` — wire getter after listener created

### Acceptance Criteria (AWR-061)
1. Open Setup Builder, set ARB Front to maximum. Trigger PTT "setup advice". Response references the ARB value.
2. Source scan: `_handle_trigger_inner` uses `_active_setup_getter()` when not None.
3. Source scan: `_active_setup_getter` initialized to `None` in `__init__`.

---

## DEF-P2-038 — BoP status absent from strategy and practice prompts

### Root Cause

Neither `_build_race_prompt()` nor `_build_practice_prompt()` in `ai_planner.py` include a BoP status line. The strategy prompt has no mention of BoP at all. The practice prompt has tuning restrictions but no explicit "BoP: ON" flag — the AI must infer BoP from the tuning lock, and cannot account for weight/power constraints without being told.

The fix for DEF-P1-013 adds `bop: bool = False` to `RaceParams` for the strategy path. Practice analysis already has the BoP value available via `_psc.get("bop", False)` but does not pass it to `RaceParams`.

### Runtime Data Path

```
_on_event_set_active()
  → strat["bop"] = self._evt_bop.isChecked()
  → self._config["strategy"]["bop"] = True/False

_run_practice_analysis()
  _psc = self._config.get("strategy", {})
  race_params = { ... }   ← currently no "bop" key
  params = RaceParams(**race_params)  ← bop defaults to False

_run_ai_analysis()
  _sc = self._config.get("strategy", {})
  race_params = { ... }   ← DEF-P1-013 fix adds "bop" key

_build_race_prompt(params, ...)    ← DEF-P1-013 fix injects bop_line
_build_practice_prompt(params, ...)  ← needs same injection
```

### Proposed Fix

**File: `ui/dashboard.py` — `_run_practice_analysis()` (~line 3222)**

Add to `race_params`:
```python
"bop": bool(_psc.get("bop", False)),
```

**File: `strategy/ai_planner.py` — `_build_practice_prompt()` (~line 600)**

After the car/track header block, inject:
```python
bop_line = ""
if getattr(params, "bop", False):
    bop_line = "\n- BoP: ON — car weight and power are regulation-fixed\n"
```

Inject `bop_line` into the `## Race / Event parameters` section.

The `_build_race_prompt()` bop_line is handled by DEF-P1-013 fix.

### Files to Change
- `ui/dashboard.py` — `_run_practice_analysis()`: add `"bop"` to `race_params`
- `strategy/ai_planner.py` — `_build_practice_prompt()`: inject bop_line

### Acceptance Criteria (AWR-062)
1. Enable BoP on event. Run Practice Analysis (`GT7_AI_DEBUG=1`). Prompt contains "BoP: ON".
2. Disable BoP. Re-run. Prompt does not contain "BoP:".
3. Enable BoP. Run Strategy Analysis. Prompt contains "BoP: ON" (from DEF-P1-013 fix).
4. Source scan: `_build_practice_prompt` references `params.bop` or `getattr(params, "bop"`.

---

## DEF-P2-039 — Available tyres not listed in strategy, practice, or build-setup prompts

### Root Cause

No prompt currently lists the event's available tyre compounds. The AI can see which compounds have lap time data (from the compound stats block), and mandatory compounds from race rules, but it does not know which compounds are permitted by event rules. It may recommend switching to a compound that is not available in the event.

`avail_tyres` is stored in the event DB row and propagated to `strat["avail_tyres"]` via `_on_event_set_active()`. However, `RaceParams` has no `avail_tyres` field and it is never passed to any prompt builder.

### Runtime Data Path

```
Event DB: events.avail_tyres = '["Racing Medium", "Racing Hard"]' (JSON)
_on_event_set_active()
  → strat["avail_tyres"] = [code for code, cb in _avail_tyre_checks.items() if cb.isChecked()]
  → strat["mandatory_compounds"] = comma-separated req compound names
  → self._config["strategy"]["avail_tyres"] = ["RM", "RH"]  (compound codes)

_run_practice_analysis() / _run_ai_analysis()
  → race_params has no "avail_tyres" key
  → RaceParams has no avail_tyres field
  → prompts have no available tyres line
```

Note: `strat["avail_tyres"]` stores compound codes (e.g. `["RM", "RH"]`), not display names. The `data.tyres.get_by_code()` function converts codes to names.

### Proposed Fix

**File: `strategy/ai_planner.py` — `RaceParams` dataclass (~line 69)**

Add:
```python
avail_tyres: list = field(default_factory=list)
```

**File: `ui/dashboard.py` — `_run_practice_analysis()` and `_run_ai_analysis()`**

Add to `race_params` in both methods:
```python
"avail_tyres": _psc.get("avail_tyres", []) or [],   # compound codes
```

**File: `strategy/ai_planner.py` — `_build_practice_prompt()` and `_build_race_prompt()`**

Add after the mandatory compounds section:
```python
avail_line = ""
if params.avail_tyres:
    from data.tyres import get_by_code as _gbc
    names = [_gbc(c).name for c in params.avail_tyres if _gbc(c)]
    if names:
        avail_line = f"- Available compounds: {', '.join(names)}\n"
```

Inject `avail_line` into the race/event parameters block.

**File: `strategy/ai_planner.py` — `_build_setup_from_scratch_prompt()` and `build_car_setup()`**

Accept `avail_tyres: list = []` and `req_tyres: list = []`. Inject:
```python
if avail_tyres or req_tyres:
    avail_str = ", ".join(avail_tyres) if avail_tyres else "all compounds"
    req_str   = ", ".join(req_tyres) if req_tyres else "none"
    tyre_rules_line = f"\nAvailable tyres: {avail_str}\nRequired compounds: {req_str}\n"
```

**File: `ui/dashboard.py` — `_run_build_setup()`**

Pass:
```python
avail_tyres=_sc_build.get("avail_tyres", []) or [],
req_tyres=_sc_build.get("required_tyres", []) or [],
```

### Files to Change
- `strategy/ai_planner.py` — `RaceParams`: add `avail_tyres` field; `_build_practice_prompt()` and `_build_race_prompt()`: inject avail line; `build_car_setup()` and `_build_setup_from_scratch_prompt()`: add avail/req tyre params
- `ui/dashboard.py` — `_run_practice_analysis()`, `_run_ai_analysis()`, `_run_build_setup()`: pass avail_tyres/req_tyres

### Acceptance Criteria (AWR-063)
1. Set event with Racing Medium + Racing Hard available. Run Practice Analysis. Prompt contains "Available compounds: Racing Medium, Racing Hard".
2. Run Strategy Analysis. Same line appears.
3. Run Build Car Setup. Prompt contains available and required tyres.
4. With no avail_tyres set: prompt does not contain "Available compounds:" line.

---

## DEF-P2-040 — Driver feedback table not queried in strategy or practice analysis

### Root Cause

`session_db.get_recent_feedback(car_id, track, limit)` and the formatting logic in `driving_advisor._get_driver_feedback_context()` exist and work. However, `analyse_practice_session()` and `analyse_strategy()` in `ai_planner.py` do not accept driver feedback as input. The `_run_practice_analysis()` worker does not query the feedback table.

This fix depends on DEF-P1-014 (correct `car_id`) to be meaningful.

### Runtime Data Path

```
driver_feedback table:
  session_id → sessions.car_id, sessions.track (via JOIN)
  corner_entry, mid_corner, exit_stability, rear_braking, tyre_condition, fuel_use, notes

session_db.get_recent_feedback(car_id=7, track="Suzuka", limit=5)
  → SELECT df.* FROM driver_feedback df
    JOIN sessions s ON s.id = df.session_id
    WHERE s.car_id=7 AND s.track='Suzuka'
    ORDER BY df.submitted_at DESC LIMIT 5

driving_advisor._get_driver_feedback_context()  ← formats the rows
  ← Already works; just not called from practice/strategy path

analyse_practice_session(params, lap_data, setup, history, ...)
  ← currently has no driver_feedback parameter
```

### Proposed Fix

**File: `strategy/ai_planner.py` — `analyse_practice_session()`**

Add parameter: `driver_feedback_str: str = ""`

Pass to `_build_practice_prompt(params, ..., driver_feedback_str=driver_feedback_str)`.

**File: `strategy/ai_planner.py` — `_build_practice_prompt()`**

Add parameter: `driver_feedback_str: str = ""`

Inject into the prompt after the history block:
```python
feedback_section = (
    f"\n## Recent Driver Feedback\n{driver_feedback_str}\n"
    if driver_feedback_str.strip() else ""
)
```

**File: `ui/dashboard.py` — `_run_practice_analysis()` `_worker()`**

After the history fix (DEF-P1-014), query feedback:
```python
_feedback_str = ""
if _hist_db is not None and _car_id_hist:
    try:
        _rows = _hist_db.get_recent_feedback(_car_id_hist, _hist_track, limit=5)
        if _rows:
            _parts: list[str] = []
            for _row in _rows:
                _row_parts: list[str] = []
                for _fld in ("corner_entry", "mid_corner", "exit_stability",
                             "rear_braking", "tyre_condition", "fuel_use"):
                    _val = _row.get(_fld, "")
                    if _val and _val != "neutral":
                        _row_parts.append(f"{_fld.replace('_', ' ')}: {_val}")
                _free = (_row.get("notes") or _row.get("free_text") or "").strip()
                if _free:
                    _row_parts.append(f'"{_free}"')
                if _row_parts:
                    _parts.append("- " + ", ".join(_row_parts))
            _feedback_str = "\n".join(_parts)
    except Exception:
        _feedback_str = ""
```

Pass `driver_feedback_str=_feedback_str` to `analyse_practice_session(...)`.

Note: The `driver_feedback` table uses `notes` (not `free_text`) per the schema at line 105 of `session_db.py`. Confirm field name before implementation.

### Files to Change
- `strategy/ai_planner.py` — `analyse_practice_session()` and `_build_practice_prompt()`: add `driver_feedback_str` parameter
- `ui/dashboard.py` — `_run_practice_analysis()` `_worker()`: query feedback table, pass to `analyse_practice_session`

### Acceptance Criteria (AWR-064)
1. Submit driver feedback "too much oversteer on exit" for a session on the active car+track.
2. Run Practice Analysis. Prompt (`GT7_AI_DEBUG=1`) contains `## Recent Driver Feedback` block.
3. AI response should address the oversteer issue.
4. With no feedback submitted: prompt does not contain the feedback section.

---

## DEF-P2-041 — Previous AI recommendations not fed into strategy or practice prompts

### Root Cause

`session_db.get_recent_ai_recommendations(feature, car_id, track, limit)` exists and returns recent successful responses from `ai_interactions` filtered by feature+car_id+track. `driving_advisor._get_previous_ai_context()` already calls it for coaching/setup features. Practice Analysis and Strategy Analysis do not use it.

The `ai_interactions.car_id` and `ai_interactions.track` columns were added in schema V1. They are populated in `log_ai_interaction()`. The log hook fires from `_ai_client.call_api()` but the `AILogEntry` dataclass does not include `car_id` or `track` — these are written to `ai_interactions` only if the caller (dashboard log hook) appends them.

**Prerequisite check needed:** Verify in `main.py` or `dashboard._on_ai_log_entry()` that `car_id` and `track` are populated in the `log_ai_interaction()` call. If they default to 0/"", `get_recent_ai_recommendations()` will always return empty regardless of this fix. Flag this as a sub-investigation before implementing.

### Proposed Fix

**File: `strategy/ai_planner.py` — `analyse_practice_session()`**

Add parameter: `prev_ai_str: str = ""`

Pass to `_build_practice_prompt(params, ..., prev_ai_str=prev_ai_str)`.

**File: `strategy/ai_planner.py` — `_build_practice_prompt()`**

Add parameter: `prev_ai_str: str = ""`

Inject:
```python
prev_ai_section = (
    f"\n## Previous AI Recommendations (Practice Analysis)\n{prev_ai_str}\n"
    if prev_ai_str.strip() else ""
)
```

**File: `ui/dashboard.py` — `_run_practice_analysis()` `_worker()`**

After feedback query:
```python
_prev_ai_str = ""
if _hist_db is not None and _car_id_hist:
    try:
        _recs = _hist_db.get_recent_ai_recommendations(
            "Practice Analysis", _car_id_hist, _hist_track, limit=2)
        if _recs:
            _prev_ai_str = "\n".join(
                f"- {r[:300]}{'…' if len(r) > 300 else ''}" for r in _recs
            )
    except Exception:
        _prev_ai_str = ""
```

Pass `prev_ai_str=_prev_ai_str` to `analyse_practice_session(...)`.

Note: `get_recent_ai_recommendations()` signature: `(feature, car_id, track, limit)`. Feature string for practice must match what `call_api()` is called with — verify it is `"Practice Analysis"` (it is, per `ai_planner.py:222`).

### Files to Change
- `strategy/ai_planner.py` — `analyse_practice_session()` and `_build_practice_prompt()`: add `prev_ai_str` parameter
- `ui/dashboard.py` — `_run_practice_analysis()` `_worker()`: query AI recommendations, pass to function

### Sub-investigation required before implementation
Confirm that `ai_interactions.car_id` and `ai_interactions.track` are non-zero/non-empty for "Practice Analysis" feature rows. Check `main.py` `_ai_log_callback` or `dashboard._on_ai_log_entry()` to see where `log_ai_interaction()` is called and whether `car_id` and `track` are populated at that point.

### Acceptance Criteria (AWR-065)
1. Run Practice Analysis twice for same car+track.
2. Second run's prompt (`GT7_AI_DEBUG=1`) contains `## Previous AI Recommendations` block with a truncated version of the first run's response.
3. Sub-investigation: `SELECT car_id, track, feature FROM ai_interactions WHERE feature='Practice Analysis' LIMIT 5` shows non-zero car_id and non-empty track.

---

## DEF-P3-009 — Race strategy prompt does not identify timed races

### Root Cause

`_build_race_prompt()` produces "Race length: N laps" for all events regardless of `params.race_type`. For timed races, `N` is computed from `duration_secs / avg_lap_secs` in `_run_ai_analysis()` — a reasonable estimate — but the prompt gives no indication that:
1. The event is timed.
2. The lap count is an estimate.
3. GT7 timed races allow a new lap to start even with <30s remaining.

This fix depends on DEF-P1-013 having added `race_type` and `duration_mins` to the strategy `race_params`.

### Proposed Fix

**File: `strategy/ai_planner.py` — `_build_race_prompt()` (~line 513)**

Replace the static `"Race length: {params.total_laps} laps"` line with:

```python
if getattr(params, "race_type", "lap") == "timed":
    race_len_line = (
        f"Race: {params.duration_mins}-minute timed race "
        f"(estimated {params.total_laps} laps based on practice pace)\n"
        "Note: GT7 timed races allow a new lap to start even with <30s remaining — "
        "plan for 1 extra lap of fuel safety margin."
    )
else:
    race_len_line = f"Race length: {params.total_laps} laps"
```

### Files to Change
- `strategy/ai_planner.py` — `_build_race_prompt()`: replace lap-count line with conditional

### Acceptance Criteria (AWR-066)
1. Set event: Timed Race, 60 min. Run Strategy Analysis (`GT7_AI_DEBUG=1`).
2. Prompt contains "60-minute timed race" and "estimated X laps".
3. Prompt contains the GT7 timed race note.
4. Set event: Lap Race, 25 laps. Prompt contains "Race length: 25 laps" (no timed reference).

---

## DEF-P3-010 — Build Car Setup prompt missing race context params

### Root Cause

`build_car_setup()` and `_build_setup_from_scratch_prompt()` in `ai_planner.py` accept car/track/session_type/race_laps/min_weight/max_power/bop_data/car_specs/tuning constraints, but not:
- `tyre_wear_multiplier` — affects spring and ARB setup for degradation
- `fuel_multiplier` — affects fuel load and ballast placement strategy
- `avail_tyres` — tyres the driver can choose from
- `req_tyres` — compounds that must be used
- `race_type` — timed vs lap

`_run_build_setup()` in dashboard.py reads `_sc_build = self._config.get("strategy", {})` and has access to all these values but does not pass them.

### Proposed Fix

**File: `strategy/ai_planner.py` — `build_car_setup()` signature (~line 336)**

Add parameters:
```python
tyre_wear_multiplier: float = 1.0,
fuel_multiplier: float = 1.0,
avail_tyres: list | None = None,
req_tyres: list | None = None,
race_type: str = "lap",
```

Pass them through to `_build_setup_from_scratch_prompt()`.

**File: `strategy/ai_planner.py` — `_build_setup_from_scratch_prompt()` (~line 791)**

Add the same parameters. Inject into the prompt's race context block:
```python
race_context_lines: list[str] = []
if tyre_wear_multiplier != 1.0:
    race_context_lines.append(f"Tyre wear rate: {tyre_wear_multiplier}x")
if fuel_multiplier != 1.0:
    race_context_lines.append(f"Fuel consumption rate: {fuel_multiplier}x")
if avail_tyres:
    race_context_lines.append(f"Available tyres: {', '.join(avail_tyres)}")
if req_tyres:
    race_context_lines.append(f"Required compounds: {', '.join(req_tyres)}")
if race_type == "timed":
    race_context_lines.append("Race type: Timed Race")
race_context_block = (
    "\n## Race Context\n" + "\n".join(f"- {l}" for l in race_context_lines)
    if race_context_lines else ""
)
```

**File: `ui/dashboard.py` — `_run_build_setup()` (~line 5554)**

Pass additional parameters:
```python
rec = build_car_setup(
    ...,
    tyre_wear_multiplier = float(_sc_build.get("tyre_wear_multiplier", 1.0)),
    fuel_multiplier      = float(_sc_build.get("fuel_multiplier", 1.0)),
    avail_tyres          = _sc_build.get("avail_tyres", []) or [],
    req_tyres            = _sc_build.get("required_tyres", []) or [],
    race_type            = _sc_build.get("race_type", "lap"),
)
```

### Files to Change
- `strategy/ai_planner.py` — `build_car_setup()` and `_build_setup_from_scratch_prompt()`: add 5 parameters
- `ui/dashboard.py` — `_run_build_setup()`: pass values from `_sc_build`

### Acceptance Criteria (AWR-067)
1. Set event with tyre_wear=3x, fuel_mult=2x, available tyres=RM+RH. Run Build Car Setup (`GT7_AI_DEBUG=1`).
2. Prompt contains "Tyre wear rate: 3.0x", "Fuel consumption rate: 2.0x", "Available tyres: Racing Medium, Racing Hard".
3. With defaults (1x wear, 1x fuel, no avail_tyres): no race context block added.

---

## DEF-P3-011 — Data quality annotations absent from strategy and practice prompts

### Root Cause

`driving_advisor.py` has a `_DATA_QUALITY_NOTE` class attribute that distinguishes measured, calculated, and estimated data. This block is injected into all coaching, setup, and combined-setup prompts. It is absent from `_build_race_prompt()` and `_build_practice_prompt()` in `ai_planner.py`.

The practice prompt includes `avg_lockups` and `avg_wheelspin` from the history block — these are calculated metrics. The race prompt includes `tyre_wear_multiplier` — measured. Without the quality note, the AI may state calculated/estimated values as facts.

### Proposed Fix

**File: `strategy/ai_planner.py` — module level (near top)**

Add the same constant used in `driving_advisor.py`:
```python
_DATA_QUALITY_NOTE = (
    "## Data Quality Note\n"
    "Measured = direct GT7 packet values (fuel, speed, position).\n"
    "Calculated = derived via physics formulas (lock-up/wheelspin = wheel slip; "
    "braking consistency = std-dev of brake points).\n"
    "Estimated = inferred proxies with uncertainty (lateral G = angvel_z × speed / 9.81; "
    "tyre wear = radius trend; off-track = road normal Y < threshold).\n"
    "Do not state estimated values as fact. Qualify with 'may indicate' or 'suggests'."
)
```

Inject into `_build_race_prompt()` and `_build_practice_prompt()` return strings (at the end, before the output instructions block).

### Files to Change
- `strategy/ai_planner.py` — add `_DATA_QUALITY_NOTE` constant; inject in `_build_race_prompt()` and `_build_practice_prompt()`

### Acceptance Criteria (AWR-068)
1. Run Strategy Analysis (`GT7_AI_DEBUG=1`). Prompt contains "Data Quality Note".
2. Run Practice Analysis. Prompt contains "Data Quality Note".
3. AI response for high estimated lateral G includes hedged language ("suggests" / "may indicate") not absolute statements.

---

## DEF-P3-012 — validate_ai_setup_response() not applied to Strategy Analysis output

### Root Cause

`validate_ai_setup_response()` in `ai_planner.py` checks if a text response mentions tuning categories that are locked. It is applied in:
- Practice Analysis result display (`dashboard.py` ~line 3363)
- Setup Advice result display (`dashboard.py` ~line 5391)

It is NOT applied to Strategy Analysis output. Strategy AI occasionally adds "also consider softening suspension" or similar notes in `strategy.reasoning`. For BoP-locked events, these are illegal suggestions that the user may follow.

### Proposed Fix

**File: `ui/dashboard.py` — strategy result display handler**

Locate where strategy options are rendered (search for `_strategy_result_queue` or `_display_strategy_results`). After parsing the response and iterating strategies, for each option:

```python
_sc_v = self._config.get("strategy", {})
_tuning_locked_v = not bool(_sc_v.get("tuning", True))
_allowed_v = _sc_v.get("allowed_tuning_categories", []) or None
for _opt in options:
    _check_text = (getattr(_opt, "reasoning", "") or "") + " " + (getattr(_opt, "name", "") or "")
    _viol_cats = validate_ai_setup_response(_check_text, _tuning_locked_v, _allowed_v)
    if _viol_cats:
        # Show a warning banner above the strategy results:
        # "⚠ Strategy AI mentioned locked tuning category: {', '.join(_viol_cats)}"
        break
```

Import `validate_ai_setup_response` at the top of the method (already imported for practice path).

### Files to Change
- `ui/dashboard.py` — strategy result display: apply `validate_ai_setup_response()` and show warning banner

### Acceptance Criteria (AWR-069)
1. Enable BoP+lock event. Run Strategy Analysis with a mock response that mentions "soften suspension".
2. Warning banner appears: "⚠ Strategy AI suggested locked tuning changes".
3. With no tuning lock: no warning banner for normal strategy text.

---

## Test Plan for Group 15

### File: `tests/test_group15_ai_context_fixes.py`

Target: **≥50 new tests** across source-scan and DB-integration classes.

```
TestStrategyRaceParamsComplete (6 tests)
  - test_strategy_race_params_includes_race_type
  - test_strategy_race_params_includes_duration_mins
  - test_strategy_race_params_includes_tuning_locked
  - test_strategy_race_params_includes_allowed_tuning
  - test_strategy_race_params_includes_bop
  - test_strategy_race_params_tuning_default_false_safe_default

TestRacePromptTuningBlock (5 tests)
  - test_race_prompt_has_tuning_locked_block_when_locked
  - test_race_prompt_has_tuning_restrictions_when_partial
  - test_race_prompt_no_tuning_block_when_unlocked
  - test_race_prompt_has_bop_line_when_bop_on
  - test_race_prompt_no_bop_line_when_bop_off

TestRacePromptTimedRace (4 tests)
  - test_race_prompt_timed_race_mentions_minutes
  - test_race_prompt_timed_race_includes_note
  - test_race_prompt_lap_race_says_laps
  - test_race_prompt_timed_race_shows_estimated_laps

TestPracticeHistoryCarId (4 tests)
  - test_practice_worker_does_not_hardcode_car_id_zero
  - test_practice_worker_uses_self_db_not_new_connection
  - test_practice_worker_calls_get_car_id
  - test_practice_worker_passes_car_id_to_get_car_track_summary

TestPracticePromptBoP (3 tests)
  - test_practice_race_params_includes_bop
  - test_practice_prompt_has_bop_line_when_bop_on
  - test_practice_prompt_no_bop_line_when_bop_off

TestAvailTyresInPrompts (6 tests)
  - test_race_params_has_avail_tyres_field
  - test_strategy_race_params_includes_avail_tyres
  - test_practice_race_params_includes_avail_tyres
  - test_race_prompt_includes_avail_tyres_when_set
  - test_practice_prompt_includes_avail_tyres_when_set
  - test_build_setup_call_passes_avail_tyres

TestPracticeDriverFeedback (4 tests)
  - test_analyse_practice_session_has_driver_feedback_param
  - test_build_practice_prompt_has_driver_feedback_param
  - test_practice_worker_queries_get_recent_feedback
  - test_practice_prompt_includes_feedback_section_when_present

TestPracticePrevAiRecs (4 tests)
  - test_analyse_practice_session_has_prev_ai_param
  - test_build_practice_prompt_has_prev_ai_param
  - test_practice_worker_queries_get_recent_ai_recommendations
  - test_practice_prompt_includes_prev_ai_section_when_present

TestPttCoachingCarContext (5 tests)
  - test_ptt_coaching_passes_car_name
  - test_ptt_coaching_passes_compound
  - test_ptt_coaching_passes_car_specs
  - test_ptt_setup_advice_passes_car_name
  - test_query_listener_has_update_car_specs_method

TestPttActiveSetup (4 tests)
  - test_query_listener_has_active_setup_getter
  - test_ptt_setup_advice_uses_active_setup_getter_when_set
  - test_ptt_setup_advice_falls_back_to_config_when_getter_none
  - test_query_listener_set_active_setup_getter_method_exists

TestDataQualityAnnotations (3 tests)
  - test_race_prompt_includes_data_quality_note
  - test_practice_prompt_includes_data_quality_note
  - test_data_quality_note_constant_in_ai_planner

TestBuildSetupRaceContext (4 tests)
  - test_build_car_setup_accepts_tyre_wear_param
  - test_build_car_setup_accepts_fuel_multiplier_param
  - test_build_car_setup_accepts_avail_tyres_param
  - test_build_car_setup_accepts_race_type_param

TestStrategyValidation (3 tests)
  - test_strategy_display_calls_validate_ai_setup_response
  - test_strategy_display_shows_violation_banner_on_locked_event
  - test_strategy_display_no_banner_when_tuning_unlocked
```

**Total: ~55 tests.** All use source-code scanning (`_method_body()` pattern) or in-memory `SessionDB(":memory:")`. No Qt widgets.

---

## AWR Summary

| AWR | Defect | Description | Verification Method |
|-----|--------|-------------|---------------------|
| AWR-058 | DEF-P1-013 | Strategy prompt has tuning block and BoP line | `GT7_AI_DEBUG=1` + locked event |
| AWR-059 | DEF-P1-014 | Practice history uses correct car_id | `GT7_AI_DEBUG=1` + sessions in DB |
| AWR-060 | DEF-P2-036 | PTT coaching mentions car and compound | PTT trigger + coaching intent |
| AWR-061 | DEF-P2-037 | PTT setup uses active editor setup | Edit ARB → PTT setup advice |
| AWR-062 | DEF-P2-038 | BoP line in strategy and practice prompts | `GT7_AI_DEBUG=1` + BoP event |
| AWR-063 | DEF-P2-039 | Available tyres in strategy/practice/build prompts | `GT7_AI_DEBUG=1` + avail tyres set |
| AWR-064 | DEF-P2-040 | Driver feedback in practice prompt | Submit feedback → practice analysis |
| AWR-065 | DEF-P2-041 | Previous AI recs in practice prompt | Two consecutive practice analyses |
| AWR-066 | DEF-P3-009 | Timed race identified in strategy prompt | `GT7_AI_DEBUG=1` + timed event |
| AWR-067 | DEF-P3-010 | Race context in build-setup prompt | `GT7_AI_DEBUG=1` + non-default wear/fuel |
| AWR-068 | DEF-P3-011 | Data quality note in strategy/practice prompts | `GT7_AI_DEBUG=1` any event |
| AWR-069 | DEF-P3-012 | validate_ai_setup_response on strategy output | BoP+locked event + strategy run |

---

## Key Constraints

- **Do not change AI output JSON schema.** All prompt additions must be injected before or around the existing output format instructions, not inside them. Strategy, Practice, and Build Setup all have strict `Reply ONLY with valid JSON` blocks — do not alter those.
- **Prompt additions must be additive.** Do not remove existing sections from any prompt. Only inject new blocks.
- **No Qt in tests.** All tests use `_method_body()` source scanning or in-memory `SessionDB(":memory:")`.
- **`RaceParams` changes must be backward compatible.** All new fields must have default values so existing call sites that do not pass them continue to work.
- **Sub-investigation on DEF-P2-041** (check `ai_interactions.car_id`/`track` population) must be completed before implementing that fix.
- **Data quality distinction is critical.** Any metric presented to the AI that is calculated or estimated (not a direct GT7 packet read) must be annotated with its derivation method. This is a firm requirement, not a style preference.
