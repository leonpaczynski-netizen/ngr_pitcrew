# AI Engineering Validation Report
**GT7 VR Dashboard — Read-only Audit**
**Date:** 2026-06-23
**Auditor:** AI Engineering Audit (Claude Sonnet 4.6)
**Scope:** strategy/ai_planner.py, strategy/driving_advisor.py, strategy/_ai_client.py, voice/query_listener.py, ui/dashboard.py (AI trigger methods), data/session_db.py (AI interaction tables)

---

## 1. Executive Summary

Seven AI call pathways were audited. **Two critical bugs** will silently produce wrong AI output on every run. **Eight medium-severity gaps** mean the AI lacks context it needs to give accurate advice. Three lower-priority gaps reduce output quality but do not cause incorrect recommendations.

| Severity | Count | Impact |
|----------|-------|--------|
| P1 — Wrong or illegal AI output | 2 | Every strategy/practice analysis call |
| P2 — Missing important context | 7 | Coaching, practice, strategy, build-setup calls |
| P3 — Useful but incomplete | 4 | All calls |
| P4 — Future enhancements | 3 | Coaching, strategy |

The app uses the Anthropic Messages API directly via raw HTTP (`requests.post`). Model defaults to `claude-opus-4-8`. Per-call token costs are tracked and logged. The `ai_interactions` table persists every call with full prompt, response, tokens, and cost.

---

## 2. AI Call Inventory

| # | Feature Name | Entry Function | Trigger | Max Tokens | Model |
|---|-------------|---------------|---------|-----------|-------|
| 1 | Strategy Analysis | `ai_planner.analyse_strategy()` | Strategy Builder → Analyse button | 6,000 | Configurable (default `claude-opus-4-8`) |
| 2 | Practice Analysis | `ai_planner.analyse_practice_session()` | Practice Review → Analyse button | 8,000 | Configurable |
| 3 | Build Car Setup | `ai_planner.build_car_setup()` | Setup Builder → Build button | 4,096 | Configurable |
| 4 | Tyre Degradation | `ai_planner.analyse_tyre_degradation()` | Internal, called from strategy flow | ~2,000 | Configurable |
| 5 | Driver Coaching | `driving_advisor.build_coaching_response()` | PTT "coaching" intent | 600 | Configurable |
| 6 | Setup Advice | `driving_advisor.build_setup_advice_response()` | PTT "setup" intent | 1,000 | Configurable |
| 7 | Combined Setup | `driving_advisor.build_combined_setup_response()` | Setup Builder → Analyse Setup button | 1,200 | Configurable |
| 8 | Handling Analysis | `driving_advisor.build_driver_feeling_response()` | Setup Builder → Feeling button | 1,000 | Configurable |

**Logging:** Every call fires `_fire_log_hook(AILogEntry)` → `dashboard._on_ai_log_entry()` → `session_db.log_ai_interaction()`. The `ai_interactions` table stores: timestamp, feature, model, full prompt, structured_payload, response, success, duration_ms, prompt_tokens, response_tokens, estimated_cost, error_msg, car_id, track.

**Cost tracking:** `_COST_INPUT_PER_TOKEN = $5.00/1M`, `_COST_OUTPUT_PER_TOKEN = $25.00/1M` (Opus 4.8 pricing, hardcoded in `_ai_client.py:24`).

---

## 3. Prompt Input Matrix

Legend: ✅ Present | ⚠ Partial | ❌ Missing

| Input | Strategy | Practice | Build Setup | Coaching | Setup Advice | Combined Setup | Handling |
|-------|----------|----------|-------------|---------|-------------|----------------|---------|
| GT7 Knowledge Base | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Driver Profile (driver_stats.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Track name/context | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Car name + specs | ✅ | ✅ | ✅ | ❌ PTT | ❌ PTT | ✅ | ✅ |
| Tyre wear multiplier | ✅ | ✅ | ❌ | N/A | N/A | N/A | N/A |
| Fuel burn per lap | ✅ | ✅ | ❌ | N/A | N/A | N/A | N/A |
| Race type (lap/timed) | ❌ **BUG** | ✅ | ⚠ partial | ✅ via event_ctx | ✅ via event_ctx | ✅ via event_ctx | N/A |
| Race duration (mins) | ❌ **BUG** | ✅ | ❌ | ✅ via event_ctx | ✅ via event_ctx | ✅ via event_ctx | N/A |
| Tuning constraints | ❌ **BUG** | ✅ | ✅ | ✅ | ✅ | ✅ | N/A |
| BoP status explicit | ❌ | ❌ | ✅ weight/power | ✅ via event_ctx | ✅ via event_ctx | ✅ via event_ctx | N/A |
| Mandatory compounds | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | N/A |
| Available tyres | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | N/A |
| Current tyre compound | N/A | N/A | N/A | ✅ (if passed) | ✅ (if passed) | ✅ (if passed) | N/A |
| Setup (current) | ⚠ history | ✅ filtered | N/A | ❌ coaching | ✅ | ✅ | ✅ |
| Setup (PTT source) | N/A | N/A | N/A | N/A | ❌ **stale config** | N/A | N/A |
| Historical session summary | ✅ setup history | ❌ **BUG car_id=0** | N/A | ✅ via DB | ✅ via DB | ✅ via DB | ✅ via DB |
| Driver feedback (DB) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | N/A |
| Previous AI recommendations | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | N/A |
| Lap times by compound (stats) | ✅ avg/best/std | ✅ avg/best/std | N/A | N/A | N/A | N/A | N/A |
| Per-lap telemetry (throttle, brake, G) | ❌ | ❌ | N/A | ✅ per-lap | ✅ avg | ✅ avg | ✅ avg |
| Advanced telemetry (B1–B6) | ❌ | ❌ | N/A | ✅ | ✅ | ✅ | ✅ |
| Data quality annotations | ❌ | ❌ | N/A | ✅ | ✅ | ✅ | ✅ |
| Gearbox analysis | N/A | N/A | ✅ | N/A | N/A | ✅ gear_note | N/A |
| Degradation data | ✅ | N/A | N/A | N/A | N/A | N/A | N/A |
| Setup comparison (history) | ✅ | ✅ | N/A | N/A | N/A | N/A | N/A |

---

## 4. Missing Data — Detailed Findings

### 4.1 Critical Missing Data

**BUG-1 — Strategy Analysis: race_type, duration_mins, tuning_locked, allowed_tuning are always default**
File: `ui/dashboard.py:3158–3171`
The `race_params` dict built for strategy analysis omits `race_type`, `duration_mins`, `tuning_locked`, and `allowed_tuning`. `RaceParams(**race_params)` uses their dataclass defaults (`race_type="lap"`, `duration_mins=0`, `tuning_locked=False`, `allowed_tuning=[]`). These are never corrected before the prompt is built.
Consequence: For a timed race, the AI is told "Race length: 35 laps" with no mention that it's a timed event — it cannot advise differently on pit timing, fuel top-up strategy, or remaining-time lap count. For a BoP event with tuning locked, the AI may recommend setup changes that are illegal under the event rules.

**BUG-2 — Practice Analysis: history always fetched with car_id=0**
File: `ui/dashboard.py:3316`
```python
car_id = 0   # ← hardcoded
track  = race_params.get("track", "")
hist = _db.get_car_track_summary(car_id, track)
```
`get_car_track_summary(0, track)` queries `WHERE car_id=0 AND track=?`. No session is ever stored with `car_id=0` (valid IDs start at 1). The `hist` dict is always empty. The practice analysis prompt always says "No historical data for this car and track combination." regardless of how many prior sessions exist for that car.
Consequence: The "historical context" block (best lap, avg lap, avg fuel, avg lockups, avg wheelspin from prior sessions) is permanently absent. The AI cannot say "you're 1.2s off your best from last week" or "your lock-up rate has worsened compared to your last session here."

### 4.2 High-Priority Missing Data

**MISS-3 — PTT coaching: no car_name, car_specs, or compound**
File: `voice/query_listener.py:474–475`
```python
response = da.build_coaching_response(
    allowed_tuning=_allowed, tuning_locked=_locked)
```
`car_name`, `car_specs`, and `compound` are all omitted. `_car_track_header()` returns only the track line with no car info. Coaching advice cannot reference drivetrain type, PP rating, aspiration, or which compound the driver is on.

**MISS-4 — PTT setup advice: setup sourced from config JSON, not current editor state**
File: `voice/query_listener.py:480–486`
```python
setup = self._config.get("car_setup", {}).get("setups", [{}])
response = da.build_setup_advice_response(
    setup[0] if setup else {}, ...)
```
The setup passed to AI is `config["car_setup"]["setups"][0]` — the first saved setup from the config file, which may be empty `{}` if no setup was saved, or may be a stale setup that doesn't match what the driver is currently running. The active setup fields being edited in the Setup Builder tab are not read.

**MISS-5 — Practice analysis: opens a new DB connection, misses current session's data**
File: `ui/dashboard.py:3312–3321`
```python
_db = _DB("data/gt7_sessions.db")
hist = _db.get_car_track_summary(car_id, track)
_db.close()
```
A new `SessionDB` connection is opened instead of using `self._db`. In SQLite WAL mode, a new connection will see all committed data but will not see any uncommitted data from the current session write-through. This is a minor freshness issue (only affects the current in-progress session's uncommitted tail), compounded by BUG-2 (which means even committed historical data is never found).

**MISS-6 — BoP status not explicitly stated in strategy or practice prompts**
Files: `ai_planner._build_race_prompt`, `ai_planner._build_practice_prompt`
Neither strategy nor practice prompts include a "BoP: ON/OFF" line. The Build Car Setup prompt includes BoP weight/power values when `bop_data` is provided, and the driving_advisor prompts include BoP status via `_get_event_context_block()`. But the two most-used AI features (Strategy and Practice Analysis) are silent on BoP.

**MISS-7 — Available tyres not listed in any prompt**
No prompt lists which tyre compounds are available for selection in the event. Mandatory compounds (required by race rules) are included in Strategy and Practice prompts. But if the event restricts to e.g. "Racing Hard only", the AI doesn't know Hard is the only valid choice — it may suggest "switch to Softs for the final stint" which is illegal.

**MISS-8 — Driver feedback table not used in strategy or practice analysis**
File: `ai_planner.py`
`driver_feedback` rows (corner_entry, mid_corner, exit_stability, rear_braking, tyre_condition, fuel_use, notes) are queried only by `driving_advisor._get_driver_feedback_context()`. They are never consulted for Strategy Analysis or Practice Analysis. The practice AI doesn't know the driver reported "too much oversteer on exit" or "rear unstable under braking."

**MISS-9 — Previous AI recommendations not in strategy or practice analysis**
File: `ai_planner.py`
`ai_interactions.response` is queried only by `driving_advisor._get_previous_ai_context()`. Strategy and Practice Analysis calls start fresh every time, with no memory of prior recommendations for that car/track. The AI may contradict its own previous advice.

---

## 5. Stale Data Risks

| Risk | Severity | Detail |
|------|----------|--------|
| Practice history always empty (BUG-2) | **CRITICAL** | `car_id=0` means `hist` is always `{}` |
| PTT setup is `config["car_setup"]["setups"][0]` | HIGH | May be `{}` or a stale saved setup |
| `_car_id_ref` in DrivingAdvisor may be 0 | MEDIUM | If `car_id_ref` never populated, coaching history and feedback also fail |
| Strategy Analysis for timed race uses estimated laps | MEDIUM | Total laps computed from avg pace, but prompt says it's a lap race |
| `get_recent_ai_recommendations()` depends on `car_id` + `track` in `ai_interactions` | MEDIUM | The log hook populates these — if they're 0/"" (e.g. car not yet registered in DB), recommendations are never retrieved |
| `load_gt7_reference()` caches static KB in `_GT7_REF_CACHE` | LOW | Static KB never refreshes mid-session; `driver_stats.md` is read fresh each call |
| Degradation data passed to strategy is from `_tyre_degradation_cache` | LOW | Cache populated by prior tyre degradation call; may be from a different track session |

---

## 6. BoP and Tuning Compliance Assessment

### 6.1 Strategy Analysis — Non-Compliant
The strategy prompt does not include tuning constraints (`tuning_locked=False` always). The AI may suggest "soften suspension" or "change aero" in its setup_history context even when tuning is locked. Post-hoc violation detection (`validate_ai_setup_response()`) is applied on the Practice Analysis result display but **not** on Strategy Analysis output.

### 6.2 Practice Analysis — Compliant (if data correct)
`tuning_locked` and `allowed_tuning` are correctly passed from Event Planner config. The practice prompt includes a tuning constraint block. Post-hoc validation (`validate_ai_setup_response()`) is applied on the display side. Setup changes are filtered by `_TUNING_CATEGORY_KEYS` before being sent. **HOWEVER:** this only works correctly if the `tuning` field in `config["strategy"]` is properly synced from the active event — a one-field bool that is easy to get wrong.

### 6.3 Build Car Setup — Compliant
`allowed_tuning` and `tuning_locked` are passed through. The prompt builder includes a tuning constraint block. BoP weight/power constraints are included when `bop_data` is available.

### 6.4 Driving Advisor (Coaching, Setup Advice, Combined) — Compliant
All three prompt builders include tuning constraints via `_tuning_constraint_block()`. Event context (BoP, tyre wear, fuel multiplier, required compounds) is injected via `_get_event_context_block()` when `set_event_context()` has been called.

### 6.5 Gap: `validate_ai_setup_response()` applied inconsistently
Applied: Practice Analysis display, Setup Advice display (dashboard.py ~line 5391).
**Not applied:** Strategy Analysis output, Build Car Setup output.

---

## 7. Telemetry Usage Assessment

### 7.1 What telemetry is captured per lap (LapStats)
From `telemetry/recorder.py` / `telemetry/state.py`:
- **Measured:** fuel_used, fuel_start, fuel_end, lap_time_ms, max_speed_kmh, avg_throttle_pct, avg_brake_pct, kerb_count, bottoming_count
- **Calculated:** lock_up_count, wheelspin_count, oversteer_count, oversteer_throttle_on_count, snap_throttle_count, brake_consistency_m (std-dev of brake points), rev_limiter_count, rev_limiter_by_gear
- **Estimated:** max_lat_g (angvel_z × speed / 9.81), tyre_radius trend (wear proxy), off_track_count (road normal), car_max_speed_theoretical_kmh
- **Positional:** lock_up_positions, wheelspin_positions, oversteer_positions, snap_throttle_positions, over_braking_positions

### 7.2 What reaches AI prompts

**Driving Advisor (Coaching, Setup Advice, Combined):** Full per-lap breakdown for 3–5 recent laps — all measured, calculated, and estimated metrics. Advanced telemetry (B1–B6): rev limiter by gear, location clusters, over-braking, theoretical max speed, tyre radius trend, off-track events. Data quality annotations (measured/calculated/estimated labels). **This is the best-instrumented prompt in the system.**

**Strategy Analysis:** Only `dict[str, list[float]]` — raw lap times by compound from the UI table. No telemetry fields at all. Average, best, and std-dev computed by `_compound_stats_lines()`.

**Practice Analysis:** Same compound stats as strategy. Plus setup (filtered by tuning permissions). Plus historical aggregates (but always empty due to BUG-2). No individual-lap telemetry metrics, no throttle/brake data, no position lists.

**Build Car Setup:** Only gearbox analysis (rev limiter by gear, corner exits, top speed). No general lap telemetry.

### 7.3 Telemetry lost before reaching AI

- Individual lap telemetry frames (~600/lap at 10 Hz) are discarded after `finalize_lap()` — `LapTelemetryRecorder` stores only aggregated `LapStats`. Frames are not persisted to `lap_telemetry` table (P1-F/P3-B from architecture plan — not yet implemented).
- Per-lap throttle/brake/G data reaches only DrivingAdvisor calls. Practice Analysis and Strategy Analysis are fully blind to these metrics.
- Outlap and pit-lap flags exist in `LapRecord` (`is_out_lap`, `is_pit_lap`) but are not surfaced in any AI prompt — the AI cannot filter or account for out-lap pace distortion.

---

## 8. Practice Session Data Usage Assessment

Practice data flows to AI through two paths:

**Path A — Lap times table (Practice Review tab):** User-tagged lap times by compound are read from `self._lap_table` via `_compound_at_row()`. These are `dict[str, list[float]]` → `_compound_stats_lines()`. This path works correctly. User must manually tag each lap with a compound name.

**Path B — Historical session DB:** `_db.get_car_track_summary(car_id, track)` returns total_laps, best_lap_ms, avg_lap_ms, avg_fuel, avg_lockups, avg_wheelspin from historical sessions. **This is always empty due to BUG-2 (`car_id=0`).**

**What the practice AI prompt actually receives:**
- ✅ Compound lap time stats (avg, best, std-dev per compound)
- ✅ Current setup (full or filtered by tuning)
- ✅ Race params: track, total_laps, fuel_burn, pit_loss, tyre_wear, tuning constraints
- ✅ Timed race branch (if `race_type == "timed"` — correctly handled in `_build_practice_prompt()`)
- ✅ Setup comparison text
- ❌ Historical best lap, avg lap, avg fuel, avg lockups (always empty — BUG-2)
- ❌ Driver feedback from DB
- ❌ Previous practice AI recommendations
- ❌ Per-lap telemetry (throttle, brake, G, lock-up counts per lap)
- ❌ Available tyres

---

## 9. Race Strategy Calculation Assessment

**Fuel calculation in strategy prompt:** Fuel burn comes from `_computed_fuel_burn_lpl()` in dashboard.py, which reads `self._tracker.avg_fuel_per_lap` (rolling average from live telemetry). This is the correct single-source value. The strategy prompt correctly uses this.

**Pit stop time formula in prompt:**
```
Pit stop time = ceil(fuel_for_next_stint / refuel_speed) + pit_loss_secs
```
This is correct per spec §18.

**Fuel margin:** The prompt instructions say to use race compound stats for stint lengths and cap by tyre life, but do not specify per-strategy fuel margins (Safe 8%, Balanced 5%, Aggressive 2% as per spec §18.1). The AI is not given explicit margin targets per strategy rank. The prompt names Safe/Balanced/Aggressive but leaves the margin interpretation to the model.

**Timed race handling:** In `_run_ai_analysis()`, `total_laps` is computed from `duration_secs / avg_lap_secs` before building `RaceParams`. This is a reasonable estimate. However, the prompt says "Race length: N laps" with no indication it's a timed race. The AI cannot account for the "last lap starts even if there are <30s left" rule that applies to timed GT7 races.

**Mandatory compounds enforcement:** Strategy prompt includes mandatory compound instructions. Post-check: the `_parse_strategies()` function does not validate whether each returned strategy includes the mandatory compound — it trusts the AI. No post-hoc compliance check for strategy output.

**Degradation data:** Correctly passed when `_tyre_degradation_cache` is populated. When absent, the prompt uses GT7 generic estimates (RS ~10–16 laps, RM ~18–25, RH ~28–40). These are stated as approximate; the prompt instructs the AI to prefer practice-derived data when available.

---

## 10. Recommended Fixes

### P1 — AI recommendations could be wrong or illegal

**FIX-P1-001: Add race_type, duration_mins, tuning_locked, allowed_tuning to strategy RaceParams**
File: `ui/dashboard.py` `_run_ai_analysis()` (~line 3158)
```python
race_params = {
    ...existing fields...,
    "race_type":            _sc.get("race_type", "lap"),
    "duration_mins":        int(_sc.get("race_duration_minutes", 0)),
    "tuning_locked":        not bool(_sc.get("tuning", True)),
    "allowed_tuning":       _sc.get("allowed_tuning_categories") or [],
}
```
And add a tuning constraint block to `_build_race_prompt()` in `ai_planner.py`.

**FIX-P1-002: Fix car_id in practice history lookup**
File: `ui/dashboard.py` `_run_practice_analysis()` (~line 3316)
```python
# Replace:
car_id = 0
# With:
car_id = self._db.get_car_id(car_name) if self._db is not None else 0
```
Where `car_name` comes from `self._config.get("strategy", {}).get("car", "")`. Alternatively use `self._db` directly instead of opening a new connection (which also fixes MISS-5).

### P2 — AI missing important context

**FIX-P2-001: Pass car_name, car_specs, and compound to PTT coaching**
File: `voice/query_listener.py` `_handle_trigger_inner()` (~line 474)
```python
_car_name = self._config.get("strategy", {}).get("car", "")
_car_specs_dict = {}  # load from car_specs.json for _car_name
_compound = self._config.get("strategy", {}).get("mandatory_compounds", "")
response = da.build_coaching_response(
    car_name=_car_name, car_specs=_car_specs_dict,
    allowed_tuning=_allowed, tuning_locked=_locked,
    compound=_compound)
```

**FIX-P2-002: PTT setup advice should use the active editor setup, not config JSON**
File: `voice/query_listener.py` (~line 480)
The `QueryListener` has no reference to the dashboard's `_current_setup_dict()`. Options:
a) Add a `get_setup_callback: Callable[[], dict]` parameter to `QueryListener.__init__()`, set from dashboard.
b) Or pass the current setup dict into the driving advisor via a shared mutable reference.

**FIX-P2-003: Replace new DB connection with self._db in practice analysis worker**
File: `ui/dashboard.py` `_run_practice_analysis()` (~line 3307)
Capture `_db = self._db` before spawning the thread and pass it to the worker instead of opening a new connection. Also apply FIX-P1-002 for correct `car_id`.

**FIX-P2-004: Add BoP explicit status to strategy and practice prompts**
File: `ai_planner._build_race_prompt()` and `_build_practice_prompt()`
Accept a `bop_active: bool = False` parameter and inject:
```
BoP: {"ON — weight and power are fixed by regulation" if bop_active else "OFF — free tuning"}
```
Pass from dashboard `_run_ai_analysis()` and `_run_practice_analysis()` via `_sc.get("bop", False)`.

**FIX-P2-005: Add available tyres to strategy and practice prompts**
File: `ai_planner._build_race_prompt()` and `_build_practice_prompt()`
Accept `avail_tyres: list[str] = []` and inject:
```
Available compounds: {', '.join(avail_tyres) or 'all compounds'}
```
Pass from `_sc.get("avail_tyres", [])` or `_sc.get("required_tyres", [])`.

**FIX-P2-006: Add driver feedback to practice analysis**
File: `ai_planner.analyse_practice_session()` and `_build_practice_prompt()`
Accept `driver_feedback_str: str = ""` and inject as a `## Recent Driver Feedback` block.
In `dashboard._run_practice_analysis()`, query `self._db.get_recent_feedback(car_id, track, limit=5)` and format it before calling `analyse_practice_session`.

**FIX-P2-007: Add previous AI recommendations to practice analysis**
File: `ai_planner.analyse_practice_session()` and `_build_practice_prompt()`
Accept `prev_ai_str: str = ""` and inject as a `## Previous AI Recommendations` block.
In `dashboard._run_practice_analysis()`, query `self._db.get_recent_ai_recommendations("Practice Analysis", car_id, track, limit=2)`.

### P3 — AI useful but incomplete

**FIX-P3-001: Add timed race indication to strategy prompt**
File: `ai_planner._build_race_prompt()`
When `params.race_type == "timed"`:
```
Race: {params.duration_mins}-minute timed race (estimated {params.total_laps} laps based on practice pace)
Note: In GT7 timed races, a new lap begins even if <30s remain at the lap-count-down boundary.
```

**FIX-P3-002: Add tyre wear multiplier, fuel multiplier, race type to Build Car Setup prompt**
File: `ai_planner.build_car_setup()` and `_build_setup_from_scratch_prompt()`
Accept additional parameters or accept a `race_context: dict` and inject:
```
Race type: {race_type} | Tyre wear: {tyre_wear}x | Fuel multiplier: {fuel_mult}x
Available tyres: {avail_tyres}
Required compounds: {req_tyres}
```

**FIX-P3-003: Apply data quality annotations to strategy and practice prompts**
File: `ai_planner._build_race_prompt()`, `_build_practice_prompt()`
Copy the `_DATA_QUALITY_NOTE` block from `driving_advisor.py` and inject it into both builders. This is especially important for the practice prompt which includes avg_lockups and avg_wheelspin from history (estimated data).

**FIX-P3-004: Apply validate_ai_setup_response() to Strategy Analysis output**
File: `ui/dashboard.py` `_display_strategy_results()` or similar
When displaying strategy options, call `validate_ai_setup_response()` on the setup/strategy text and display a warning banner if violations are detected.

### P4 — Future Enhancements

**ENH-P4-001: Per-lap fuel trend in prompts**
Include `[lap1_fuel, lap2_fuel, ...]` to enable AI to detect fuel burn variability (e.g. safety car laps, kerb cuts affecting fuel model).

**ENH-P4-002: Individual lap telemetry in practice prompt**
Include per-lap lock-up counts, wheelspin counts, max_lat_g in the practice prompt to let the AI correlate handling issues with specific laps.

**ENH-P4-003: Mandatory compound validation on strategy output**
`_parse_strategies()` should verify each returned strategy uses every required compound at least once. Raise a warning if not, rather than silently returning a non-compliant strategy.

---

## 11. Recommended Tests

```python
# test_ai_engineering_validation.py

# T-001: Strategy RaceParams includes race_type
def test_strategy_race_params_includes_race_type():
    """_run_ai_analysis race_params dict must contain race_type."""
    body = _dashboard_method_body("_run_ai_analysis")
    assert '"race_type"' in body

# T-002: Strategy RaceParams includes tuning_locked
def test_strategy_race_params_includes_tuning_locked():
    body = _dashboard_method_body("_run_ai_analysis")
    assert '"tuning_locked"' in body

# T-003: Practice analysis car_id not hardcoded to 0
def test_practice_analysis_car_id_not_zero():
    body = _dashboard_method_body("_run_practice_analysis")
    # Should not contain 'car_id = 0' literal
    assert "car_id = 0" not in body

# T-004: Practice prompt includes timed race branch
def test_practice_prompt_timed_race_branch():
    body = _planner_method_body("_build_practice_prompt")
    assert 'race_type' in body and 'timed' in body

# T-005: Race prompt does not silently ignore race_type
def test_race_prompt_accepts_race_type():
    body = _planner_method_body("_build_race_prompt")
    # Check params.race_type is referenced
    assert "race_type" in body or "timed" in body

# T-006: Build car setup receives tyre_wear_multiplier
def test_build_setup_receives_tyre_wear():
    body = _dashboard_method_body("_run_build_setup")
    assert "tyre_wear" in body or "tyre_wear_multiplier" in body

# T-007: PTT coaching passes car_name
def test_ptt_coaching_passes_car_name():
    body = _listener_method_body("_handle_trigger_inner")
    coaching_call_start = body.find("build_coaching_response")
    assert "car_name" in body[coaching_call_start:coaching_call_start + 200]

# T-008: Practice analysis passes driver_feedback to prompt
def test_practice_prompt_includes_driver_feedback_param():
    sig = _planner_function_sig("_build_practice_prompt")
    assert "driver_feedback" in sig or "feedback" in sig

# T-009: Race prompt builder accepts bop_active param
def test_race_prompt_has_bop_param():
    sig = _planner_function_sig("_build_race_prompt")
    assert "bop" in sig

# T-010: validate_ai_setup_response called on strategy output
def test_strategy_display_validates_tuning():
    body = _dashboard_method_body("_display_strategy_results")
    assert "validate_ai_setup_response" in body
```

---

## 12. Runtime Validation Checklist

Run these checks with a live GT7 telemetry session to confirm AI context is correct at runtime.

| # | Check | How to verify |
|---|-------|--------------|
| RV-01 | Strategy prompt race_type is correct for a timed event | Set event to 60-min timed, enable `GT7_AI_DEBUG=1`, run strategy — prompt must say "timed race" |
| RV-02 | Strategy prompt includes tuning constraint for locked events | BoP+lock event, run strategy — prompt must contain "TUNING LOCKED" |
| RV-03 | Practice history block has actual car data | After 10+ sessions, run practice analysis — prompt must NOT say "No historical data" |
| RV-04 | PTT coaching response references car name and compound | With car selected and compound set, trigger PTT coaching — response must name the car |
| RV-05 | PTT setup advice uses current editor setup | Edit ARB to extreme value, trigger PTT — response must reference the extreme ARB |
| RV-06 | Available tyres correctly limit AI recommendations | Set event to Hard-only, run strategy — no Soft compound should appear in strategy |
| RV-07 | BoP weight/power appears in build-setup prompt | Enable BoP, click Build Setup — prompt must contain "BOP minimum weight" |
| RV-08 | Driver feedback appears in coaching prompt | Submit oversteer feedback, trigger PTT coaching — response should address oversteer |
| RV-09 | Previous recommendations appear in 2nd coaching call | Run coaching twice same car/track — 2nd prompt must contain "Previous AI Recommendations" |
| RV-10 | validate_ai_setup_response warns on locked categories | BoP+locked suspension, run practice analysis — if AI recommends ARB, banner must show |

---

## Implementation Plan

### P1 — AI recommendations could be wrong or illegal
*Fix these before any live race use.*

| ID | Fix | File | Effort |
|----|-----|------|--------|
| FIX-P1-001 | Add race_type, tuning_locked, allowed_tuning to strategy RaceParams; add tuning block to race prompt | `ui/dashboard.py:3158`, `ai_planner._build_race_prompt()` | 2h |
| FIX-P1-002 | Fix `car_id=0` in practice history lookup; replace new DB conn with self._db | `ui/dashboard.py:3312–3321` | 1h |

### P2 — AI missing important context
*Fix these for meaningful AI output on real events.*

| ID | Fix | File | Effort |
|----|-----|------|--------|
| FIX-P2-001 | Pass car_name, car_specs, compound to PTT coaching | `voice/query_listener.py:474` | 1h |
| FIX-P2-002 | PTT setup advice: use active editor setup via callback | `voice/query_listener.py:480` | 2h |
| FIX-P2-003 | Use self._db in practice worker (handled by FIX-P1-002) | Covered above | 0h |
| FIX-P2-004 | BoP status to strategy + practice prompts | `ai_planner.py:444,_build_practice_prompt` | 1h |
| FIX-P2-005 | Available tyres to strategy + practice prompts | `ai_planner.py` | 1h |
| FIX-P2-006 | Driver feedback to practice analysis | `ai_planner.py`, `dashboard.py:3307` | 2h |
| FIX-P2-007 | Previous AI recommendations to practice analysis | `ai_planner.py`, `dashboard.py:3307` | 1h |

### P3 — AI useful but incomplete
*Fix these for improved output quality.*

| ID | Fix | File | Effort |
|----|-----|------|--------|
| FIX-P3-001 | Timed race indication in strategy prompt | `ai_planner._build_race_prompt()` | 30m |
| FIX-P3-002 | Tyre wear, fuel mult, race type in Build Car Setup | `ai_planner.build_car_setup()` | 1h |
| FIX-P3-003 | Data quality annotations in strategy + practice prompts | `ai_planner.py` | 1h |
| FIX-P3-004 | validate_ai_setup_response on strategy output | `ui/dashboard.py` display method | 30m |

### P4 — Future Enhancements

| ID | Enhancement | Effort |
|----|------------|--------|
| ENH-P4-001 | Per-lap fuel trend in practice prompt | 2h |
| ENH-P4-002 | Per-lap telemetry metrics in practice prompt | 3h |
| ENH-P4-003 | Mandatory compound validation in strategy parser | 1h |

---

*Do not implement code until this plan is approved.*
