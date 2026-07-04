# GT7 Pit Crew — Smart Race Engineer Roadmap

> **Vision:** GT7 Pit Crew learns your driving style, your car preferences, your track-specific weaknesses, and your setup response history — getting smarter with every session, until its advice is indistinguishable from a real race engineer who has been watching you drive for years.
>
> **Date:** 2026-06-29 (updated)
> **Prerequisite:** Group 15 remediation plan approved (`/docs/GROUP15_AI_CONTEXT_REMEDIATION_PLAN.md`).
> **Status:** Phase 1 and setup-prompt engineering delivered (Groups 26–31). Phase 2 onwards is roadmap.

---

## Outstanding Feature Requests — Setup-Advice Review (2026-06-27)

> Logged from the setup-advice review that delivered car-specific tuning ranges and
> the race-engineer prompt upgrade (items 1–7). The two items below were explicitly
> **deferred** from that work to be scoped and built as their own efforts. Both are
> larger than a prompt edit and overlap the learning/telemetry phases below.
> **Status: OFR-1 DELIVERED (2026-07-04)** — Loop 1 setup self-scoring built via
> feature-factory on branch `ofr1-between-race-learning`; see
> `docs/OFR1_BETWEEN_RACE_LEARNING.md`. **OFR-2 DELIVERED (2026-07-04)** — Core
> split (discipline-aware telemetry in setup-build + practice-analysis prompts)
> on branch `ofr2-quali-race-disciplines`; see `docs/OFR2_SEPARATE_DISCIPLINES.md`.
> Strategy-prompt telemetry (Phase 2-B/2-C) remains deferred.

### OFR-1 — Between-Race Learning Loop (self-scoring recommendations)

After each race, the AI should evaluate whether its own setup recommendations actually
worked, and adjust its confidence accordingly — so that over many races the engineer
becomes *Leon's* engineer rather than a generic model.

For every recommendation it made, score it against the measured outcome, e.g.:

```
Rear toe — Expected: better traction.
Actual: tyre wear improved 9%, exit speed +2 km/h.  → Confidence increased.

LSD Accel — Expected: reduce wheelspin.
Actual: no measurable improvement.                  → Confidence reduced.
```

Requires: capturing each recommendation's expected effects (the seven labelled
sub-points now emitted by the setup prompt — see §6.4 and the Group 26 work),
correlating them with post-change telemetry, and persisting a per-recommendation
confidence/score that feeds back into future prompts.

**Heavily overlaps:** §5 (Data Model for Learning Over Time — `ai_interactions.outcome_rating`/
`was_followed`, `setup_deltas`, `prediction_log`), §6.4 (Learning Feedback Layer), and
Phase 3-B/3-C. Scope should reconcile OFR-1 with those rather than duplicate them.

### OFR-2 — Separate Race vs Qualifying Telemetry Disciplines

Qualifying and race are different engineering problems and should optimise against
different telemetry targets:

- **Qualifying:** peak grip, peak braking, peak rotation, one-lap pace.
- **Race:** fuel per lap, tyre wear per corner, brake-lock frequency, wheelspin
  frequency, steering corrections, throttle smoothness, average exit speed,
  consistency, traffic performance, dirty-air performance.

The setup prompt already branches quali vs race for the *objective text* (Group 26),
but telemetry inputs and the optimisation discipline are not yet differentiated.

**Heavily overlaps:** §2 (Setup Engineering telemetry), §3 (Race Strategy telemetry),
and Phase 2 (per-lap telemetry in practice/strategy prompts). Scope should build on
Phase 2 rather than start fresh.

---

## Contents

1. [Current Telemetry Usage Gap Analysis](#1-current-telemetry-usage-gap-analysis)
2. [Required Telemetry Signals — Setup Engineering](#2-required-telemetry-signals--setup-engineering)
3. [Required Telemetry Signals — Race Strategy](#3-required-telemetry-signals--race-strategy)
4. [Required Telemetry Signals — PTT / Live Race Decisions](#4-required-telemetry-signals--ptt--live-race-decisions)
5. [Data Model for Learning Over Time](#5-data-model-for-learning-over-time)
6. [AI Prompt Architecture Changes](#6-ai-prompt-architecture-changes)
7. [Phased Implementation Plan](#7-phased-implementation-plan)
8. [Appendix: Telemetry Signal Catalogue](#appendix-telemetry-signal-catalogue)

---

## 1. Current Telemetry Usage Gap Analysis

### 1.1 What the GT7 Packet Provides

Every UDP packet at ~60 Hz carries 24 raw fields. After processing they produce:

**Directly measured (raw packet values):**
- `fuel_level`, `fuel_capacity` → instantaneous fuel in litres
- `car_speed_ms` → speed in m/s (converted to km/h)
- `lap_count`, `laps_in_race` → position tracking
- `position_x/y/z`, `velocity_x/y/z` → world-space position and velocity
- `angular_velocity_x/y/z` → body rotation rates
- `body_height_m` → ride height (suspension travel proxy)
- `road_normal_x/y/z` → road surface normal (off-track detection)
- `tyre_surface_temp_fl/fr/rl/rr` → four corner tyre surface temps
- `suspension_height_fl/fr/rl/rr` → per-corner suspension displacement
- `current_gear`, `suggested_gear` → transmission
- `engine_rpm`, `max_rpm` → engine state
- `throttle_raw`, `brake_raw` → driver inputs (0–255)
- `tyre_radius_fl/fr/rl/rr` → rolling radius

**Derived (calculated from packet fields):**
- `tyre_wear_proxy` = change in tyre_radius over time (radius shrinks as rubber wears)
- `lateral_g` = angular_velocity_z × car_speed_ms / 9.81 (**estimated — not direct measurement**)
- `longitudinal_g` = Δvelocity / Δtime (**calculated**)
- `lock_up` = wheel slip detected from angular velocity vs ground speed (**calculated**)
- `wheelspin` = wheel spin detected from angular velocity vs ground speed (**calculated**)
- `off_track` = road_normal_y below threshold (**estimated — threshold tuned empirically**)
- `fuel_used` = fuel_level[lap_start] − fuel_level[lap_end] (**measured**)

### 1.2 What Each AI Call Currently Receives

The five call surfaces have dramatically different telemetry richness:

| Signal Type | Strategy Analysis | Practice Analysis | Build Car Setup | PTT Coaching | PTT Setup |
|------------|:-----------------:|:-----------------:|:---------------:|:------------:|:---------:|
| Lap times by compound (avg/best/std) | ✅ | ✅ | — | — | — |
| Fuel burn per lap | ✅ | ✅ | — | — | — |
| Tyre wear multiplier | ✅ | ✅ | ❌ | — | — |
| Race type / duration | ❌ BUG-1 | ✅ | ❌ | ✅ via ctx | ✅ via ctx |
| Tuning constraints | ❌ BUG-1 | ✅ | ✅ | ✅ | ✅ |
| BoP status (explicit) | ❌ | ❌ | ✅ | ✅ | ✅ |
| Available tyres | ❌ | ❌ | ❌ | ❌ | ❌ |
| Car name + specs | ✅ | ✅ | ✅ | ❌ MISS-3 | ❌ MISS-3 |
| Current compound | — | — | — | ✅ (if passed) | ✅ (if passed) |
| Historical session summary | ✅ (setup history) | ❌ BUG-2 | — | ✅ | ✅ |
| Driver feedback (DB) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Previous AI recommendations | ❌ | ❌ | ❌ | ✅ | ✅ |
| Per-lap throttle/brake avg | ❌ | ❌ | — | ✅ | ✅ |
| Per-lap lock-up / wheelspin | ❌ | ❌ | — | ✅ | ✅ |
| Per-lap oversteer count | ❌ | ❌ | — | ✅ | ✅ |
| Per-lap lateral G (estimated) | ❌ | ❌ | — | ✅ | ✅ |
| Rev limiter by gear (B1) | ❌ | ❌ | ✅ | ✅ | ✅ |
| Location clusters (B2) | ❌ | ❌ | — | ✅ | ✅ |
| Over-braking zones (B3) | ❌ | ❌ | — | ✅ | ✅ |
| Theoretical max speed (B4) | ❌ | ❌ | — | ✅ | ✅ |
| Tyre radius trend (B5) | ❌ | ❌ | — | ✅ | ✅ |
| Off-track events (B6) | ❌ | ❌ | — | ✅ | ✅ |
| Data quality annotations | ❌ | ❌ | — | ✅ | ✅ |
| Gearbox analysis | — | — | ✅ | — | — |
| Compound degradation data | ✅ | — | — | — | — |

**The inversion problem:** PTT coaching (a 600-token voice query) has richer telemetry context than Strategy Analysis (a 6,000-token planning call). This is backwards. Race strategy decisions depend on understanding how the car performs; PTT quick-queries can work with summaries.

### 1.3 Structural Gaps by Category

**Broken paths (produce wrong output today):**
- BUG-1: Strategy Analysis never receives race_type, duration_mins, tuning_locked, or allowed_tuning
- BUG-2: Practice Analysis history always empty (car_id=0)
- MISS-4: PTT setup advice reads `config["car_setup"]["setups"][0]` — may be empty or stale

**Missing context (produce incomplete output today):**
- No AI call receives available tyres list
- No AI call receives per-lap telemetry beyond DrivingAdvisor
- Strategy Analysis has no per-lap throttle/brake/G data
- Practice Analysis has no per-lap telemetry metrics at all
- Driver feedback not used in Strategy or Practice Analysis
- Previous AI recommendations not used in Strategy or Practice Analysis

**Missing learning infrastructure (system cannot improve over time):**
- No mechanism to track whether an AI recommendation was followed
- No mechanism to record whether setup changes improved or worsened handling
- No compound-specific degradation model (uses GT7 generic estimates: RS 10–16 laps, RM 18–25, RH 28–40)
- Tyre radius trend used as wear proxy — **not validated against actual tyre life**
- No cross-session compound performance learning

---

## 2. Required Telemetry Signals — Setup Engineering

Setup engineering requires correlating driver inputs, car behaviour, and lap outcome. The following signals, per lap and per corner position, are needed to diagnose setup problems and recommend changes.

### 2.1 Corner Classification Signals

A real race engineer diagnoses by corner phase: entry, apex, exit. Each phase implicates different setup parameters.

| Phase | What to measure | Setup parameters implicated |
|-------|----------------|----------------------------|
| **Braking zone** | Lock-up positions, lock-up frequency, brake consistency (std-dev of brake points) | Brake balance, ABS, spring rates |
| **Corner entry** | Entry oversteer/understeer onset distance from apex | Rear camber, ARB balance, slow damper bump |
| **Mid-corner** | Peak lateral G, throttle application rate, wheelspin onset distance | LSD (initial), differential, front ARB |
| **Exit** | Wheelspin frequency, throttle smoothness, exit oversteer | LSD (acceleration), rear spring, toe-out |
| **Straight** | Rev limiter hits by gear, top speed vs target | Gear ratios, final drive, power restrictor |
| **Kerb use** | Kerb strike count, suspension displacement peaks | Ride height, bump dampers, spring rates |
| **Bottoming** | Bottoming count (body_height_m at minimum) | Ride height, spring rates |

**Currently captured per lap:** lock_up_count, wheelspin_count, oversteer_count, kerb_count, bottoming_count, brake_consistency_m, rev_limiter_by_gear. ✅

**Currently missing:**
- Per-corner-position aggregates (lock-up at T1 vs T5 is very different setups)
- Oversteer at throttle vs oversteer at braking (already split into `oversteer_throttle_on_count` — not yet sent to Practice/Strategy AI)
- Suspension displacement variance (body_height_m spread across the lap)
- Tyre temperature by corner (FL/FR/RL/RR avg across each lap)

### 2.2 Signals Required for Setup Prompt

For an AI to give calibrated setup advice, the practice prompt needs:

```
## Per-Lap Telemetry (last 5 clean laps)
Lap | Time    | Fuel | Lock-up | Wheelspin | Oversteer | Kerb | Bottom | Lat-G* | Brake-Cons
 14 | 1:42.1  | 3.2L |    4    |     2     |     1     |   6  |    0   |  2.8*  |    4.2m
 15 | 1:41.8  | 3.1L |    2    |     1     |     0     |   4  |    0   |  2.9*  |    3.8m
...

* Lateral G is estimated from angular_velocity_z × speed / 9.81. Not a direct measurement.
  Values >3.0 may indicate sensor saturation, not actual G-load. Do not state as fact.

## Oversteer Breakdown (latest clean lap)
- Throttle-on oversteer: 0 events (good)
- Braking oversteer: 1 event (rear balance issue under braking)

## Rev Limiter by Gear (latest clean lap)
Gear 1: 0 | Gear 2: 0 | Gear 3: 2 | Gear 4: 1 | Gear 5: 0 | Gear 6: 0

## Tyre Temperature by Corner (latest clean lap, all 4 tyres)
FL: 78°C | FR: 91°C | RL: 82°C | RR: 88°C
Front imbalance: +13°C outside → suggests too much camber or pressure
Rear temperature: within 6°C — acceptable

## Suspension Displacement (latest clean lap)
Body height range: 42–178mm. 0 bottoming events. Clearance adequate.
```

**Tyre temperature caveat:** The GT7 packet provides `tyre_surface_temp_fl/fr/rl/rr`. These are already captured by `recorder.py` per-frame but not stored per-lap or sent to any AI. Tyre temps are **measured directly** — they should be labelled as such, unlike tyre radius trend which is estimated.

### 2.3 Tyre Radius as Wear Proxy — Validation Requirement

`tyre_radius_fl/fr/rl/rr` shrinks as the tyre wears. The current B5 metric uses this as a wear proxy. **This must not be treated as direct tyre wear** because:

1. Tyre radius also varies with tyre temperature (thermal expansion) — same lap, different corner, different radius
2. Radius trend is noisy — single-frame outliers can look like sudden wear events
3. The relationship between radius delta (mm) and actual compound life remaining is not validated
4. GT7 may report inflated radius on fresh tyres due to loading artefacts

**Required before using radius in setup advice:**
- Collect radius samples across 5+ full stints
- Correlate end-of-stint radius with reported lap time degradation
- Validate that radius trend produces a monotone wear curve (if it's noisy, it's not reliable)
- Until validated: label all radius-based conclusions as **estimated/unvalidated** in prompts
- Consider using lap time delta per lap (Δlap_time) as the primary wear indicator instead

The roadmap includes a validation task (Phase 3) before radius-based wear enters strategy calculations.

---

## 3. Required Telemetry Signals — Race Strategy

Race strategy requires predicting the future from the past. The signals needed are different from setup engineering — less about corner-by-corner behaviour, more about stint-level trends.

### 3.1 Fuel Model Signals

**Currently used:** `avg_fuel_per_lap` (rolling average from live session or loaded session)
**Currently missing:**

| Signal | Why needed | Source |
|--------|-----------|--------|
| Per-lap fuel burn sequence `[3.1, 3.2, 3.0, 3.4, ...]` | Detect fuel mode changes, safety car savings, drafting | `lap_records.fuel_used` per lap |
| Fuel burn variance (std-dev across laps) | Estimate buffer needed for fuel uncertainty | Computed from per-lap sequence |
| Fuel burn under SC conditions | Safety car lap burns less fuel — strategy must account for it | Not currently detectable |
| Fuel mode indicator | Power setting (ECU output from packet) — high ECU = more fuel | `engine_rpm` / throttle ratio proxy |

**AI fuel prompt should contain:**
```
## Fuel Trend (last 15 laps)
Per-lap burn: 3.1, 3.2, 3.0, 3.4, 3.1, 3.0, 3.2, 3.1, 3.3, 3.0, 3.2, 3.1, 3.4, 3.0, 3.2
Average: 3.15 L/lap [measured]
Std-dev: 0.12 L/lap [calculated]
Worst-case (95th percentile): 3.4 L/lap
Safe fuel target: avg × laps × 1.05 = [calculated]
```

### 3.2 Tyre Degradation Signals

**Currently used:** Lap time data by compound (avg/best/std-dev from Practice Review table)
**Currently missing:**

| Signal | Why needed | Source |
|--------|-----------|--------|
| Lap time sequence per compound `[1:42.1, 1:42.4, 1:42.8, ...]` | Detect degradation trend (not just average) | Per-lap times tagged by compound |
| Degradation rate (seconds per lap) | Linear or exponential model for stint projection | Regression on per-lap sequence |
| Cliff lap estimate (when lap time jumps >1.5s) | GT7 compounds often have a hard cliff — strategy must avoid it | Identified from sequence |
| Cross-session compound profiles | How does this compound degrade on this track in this car? | Historical `lap_records` JOIN `compound` |

**Strategy prompt should contain:**
```
## Compound Lap Time Trend (this session)
Racing Medium (15 laps):
  Lap-by-lap: 1:42.1 → 1:42.4 → 1:42.6 → 1:42.9 → 1:43.4 → 1:44.1...
  Degradation rate: +0.18s/lap [calculated — linear regression]
  Estimated cliff: lap 22 (pace loss accelerates above 1:44.5) [estimated]
  Best pace: 1:42.1 (lap 3 of stint)

Racing Hard (7 laps):
  Lap-by-lap: 1:43.8 → 1:43.9 → 1:44.0 → 1:44.0 → 1:44.1...
  Degradation rate: +0.04s/lap [calculated]
  No cliff detected in observed range [estimated]

Note: Degradation rates are calculated from this session only.
Historical cross-session data: 3 prior sessions on this car/track — 
  RM typically degrades 0.15–0.22s/lap on this circuit [cross-session average]
```

### 3.3 Pit Strategy Signals

**Currently used:** Static pit stop time estimate (`fuel_load / refuel_rate + pit_loss`)
**Currently missing:**

| Signal | Why needed | Source |
|--------|-----------|--------|
| Actual pit time from session | Validate static estimate; GT7 pit time varies by track/car | `lap_records` where `is_pit_lap=True`: `lap_time_ms` |
| Measured pit time vs estimated | If actual > estimated, strategy is wrong | `pit_loss_actual = pit_lap_time - avg_clean_lap` |
| Live laps remaining when in pit window | Strategy should recalculate when actual pace deviates | Real-time from tracker |
| Mandatory compound compliance status | Has the mandatory compound been used yet? | Track across stint history |

### 3.4 Race Position Signals

The GT7 packet provides `laps_in_race` but not competitor positions. Without live position data, the strategy cannot advise on undercuts, overcuts, or gap management. This is a hard limitation of the GT7 UDP telemetry — competitor gaps are not transmitted.

**Workaround for strategy:** The driver can report their position and gap via PTT ("I'm P3, 4 seconds ahead of P4"). The strategy AI can then factor this into undercut/overcut decisions. This requires a PTT intent: `gap_report`.

---

## 4. Required Telemetry Signals — PTT / Live Race Decisions

The PTT coaching path (DrivingAdvisor) is already the best-instrumented call in the system. Its telemetry gaps are narrower but still meaningful for live race engineering.

### 4.1 What PTT Currently Has (DrivingAdvisor)

Per-lap for 3–5 recent laps:
- Lap time, fuel used, max speed
- Lock-up count, wheelspin count, oversteer count, kerb count, bottoming count
- Avg throttle %, avg brake %, brake consistency (std-dev)
- Max lateral G (estimated), snap throttle count
- Rev limiter by gear, location clusters, over-braking zones
- Tyre radius trend, off-track events
- Data quality annotations (measured/calculated/estimated)
- Car name + specs, track, tuning constraints, event context (BoP, wear mult, compounds)
- Driver feedback (last 5 entries), previous coaching recommendations

### 4.2 What PTT Is Missing for Live Race Engineering

| Signal | Live Race Use | Priority |
|--------|--------------|----------|
| **Live fuel level** (current packet value) | "How many laps can I do?" | **HIGH** |
| **Current lap partial time** | "Am I on a hot lap?" | HIGH |
| **Current tyre temp** (all four, from latest frame) | "Are tyres ready for push lap?" | HIGH |
| **Current lap vs personal best** | "Am I on a good lap?" | HIGH |
| **Race position** (self-reported via PTT) | Gap-based undercut/overcut advice | HIGH |
| **Laps remaining** | Strategy horizon | MEDIUM |
| **Pit window open?** (fuel/tyre intersection) | "Box now?" | MEDIUM |
| **Current stint length** | How many laps on current tyre | MEDIUM |
| **Mandatory compound status** | Has mandatory tyre been used? | MEDIUM |
| **Competitor gap** (self-reported) | Undercut/overcut advice | LOW (requires PTT intent) |
| **Weather change** | Wet → dry or dry → wet | LOW (GT7 packet has weather flags) |

### 4.3 PTT Architecture for Live Race

The PTT system should have access to a **live state snapshot** — assembled in real time from the tracker and updated every lap. This is distinct from the practice-session telemetry summary.

```
## Live Race State (at time of PTT query)
Lap: 18 of 25 (7 to go)
Current fuel: 14.2L [measured — current packet]
Fuel needed: 7 × 3.15 L/lap = 22.1L — CRITICAL: 8L short
Fuel per lap budget: 2.0L/lap to stretch to finish (save mode required)
Current tyres: Racing Medium, lap 18 of current stint
Estimated tyre life: 22–25 laps on RM [historical range]
Pit window: open (fuel forces box within 5 laps)
Mandatory compound: Racing Hard — NOT YET USED ← compliance risk
Position: not available — report via voice ("I'm P2")

Current pace (last 3 laps): 1:42.4 → 1:42.9 → 1:43.1 (degrading)
Personal best on RM: 1:41.8 (lap 12)

## Situation
AI has enough data to advise on: fuel strategy, pit window, tyre life.
AI does NOT have: gap data, competitor pace, safety car history.
```

The key design principle: **the AI should explicitly state what it knows and what it doesn't know** before giving advice. This prevents confident-sounding advice based on incomplete data.

---

## 5. Data Model for Learning Over Time

For GT7 Pit Crew to learn and improve, it needs to accumulate structured knowledge across sessions. The current data model captures session/lap data but does not connect outcomes to decisions.

### 5.1 What Learning Requires

**Three learning loops:**

**Loop 1 — Setup learning:** What setup changes improved pace or handling?
- Record: what the setup was before an AI recommendation
- Record: what the driver actually changed (or didn't)
- Record: how the next session's pace/handling changed
- Connect: setup delta → outcome delta

**Loop 2 — Strategy learning:** Which strategies performed closest to prediction?
- Record: what the AI predicted (fuel, pit window, compound choice)
- Record: what actually happened (actual fuel burn, actual tyre life, actual pit lap)
- Compute: prediction error = actual − predicted
- Use prediction error to calibrate future estimates

**Loop 3 — Driver style learning:** Is the driver improving on specific weaknesses?
- Record: lock-up rate per session, per track, per corner
- Record: brake consistency trend over time
- Record: driver feedback recurring themes
- Detect: systematic weaknesses (e.g. always overbrakes T1)

### 5.2 Required DB Tables / Columns

**Existing tables that need extension:**

`ai_interactions` (already exists):
- `car_id` ✅ (added, may need population fix — DEF-P2-041 prerequisite check)
- `track` ✅ (same)
- `feature` ✅
- `response` ✅
- Need to add: `outcome_rating INT DEFAULT NULL` — driver rates the recommendation after following it (1–5 or NULL if not rated)
- Need to add: `was_followed INT DEFAULT NULL` — 1 if driver says they followed it, 0 if not, NULL if unknown

`driver_feedback` (already exists):
- Used to collect per-session feeling
- Need to add: `session_lap INT DEFAULT NULL` — which lap in the session this feedback refers to
- Need to add: trend analysis: compare last 5 sessions for recurring themes (done in query layer, no schema change needed)

**New tables needed:**

**`setup_deltas`** — records what changed between sessions:
```sql
CREATE TABLE IF NOT EXISTS setup_deltas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    track           TEXT    NOT NULL,
    session_from_id INTEGER REFERENCES sessions(id),
    session_to_id   INTEGER REFERENCES sessions(id),
    field           TEXT    NOT NULL,   -- e.g. "arb_front"
    value_before    REAL    NOT NULL,
    value_after     REAL    NOT NULL,
    ai_recommended  INT     NOT NULL DEFAULT 0,  -- was this AI's suggestion?
    outcome_note    TEXT    NOT NULL DEFAULT '', -- driver's verdict
    lap_delta_ms    INT     NOT NULL DEFAULT 0,  -- avg lap time change
    changed_at      TEXT    NOT NULL
);
```

**`compound_profiles`** — cross-session compound degradation per car/track:
```sql
CREATE TABLE IF NOT EXISTS compound_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    track           TEXT    NOT NULL,
    compound        TEXT    NOT NULL,
    sample_count    INT     NOT NULL DEFAULT 0,  -- number of sessions contributing
    avg_first_lap_s REAL    NOT NULL DEFAULT 0.0, -- fresh-tyre pace (lap 1–3 of stint)
    deg_rate_s_per_lap REAL NOT NULL DEFAULT 0.0, -- seconds added per lap [calculated]
    cliff_lap_est   INT     NOT NULL DEFAULT 0,  -- estimated lap where cliff begins
    observed_max_laps INT   NOT NULL DEFAULT 0,  -- max laps before driver pitted
    updated_at      TEXT    NOT NULL
);
```

**`prediction_log`** — AI strategy predictions vs actual:
```sql
CREATE TABLE IF NOT EXISTS prediction_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    feature         TEXT    NOT NULL,   -- "Strategy Analysis", "Practice Analysis"
    predicted_fuel_lpl REAL DEFAULT NULL,
    actual_fuel_lpl    REAL DEFAULT NULL,
    predicted_tyre_life_laps INT DEFAULT NULL,
    actual_tyre_life_laps    INT DEFAULT NULL,
    predicted_best_lap_ms    INT DEFAULT NULL,
    actual_best_lap_ms       INT DEFAULT NULL,
    recorded_at     TEXT    NOT NULL
);
```

**`driver_weaknesses`** — computed summary table (updated after each session):
```sql
CREATE TABLE IF NOT EXISTS driver_weaknesses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    track           TEXT    NOT NULL,
    weakness_type   TEXT    NOT NULL,  -- "lockups", "oversteer_exit", "wheelspin", "brake_consistency"
    severity        REAL    NOT NULL,  -- normalized 0–1 (1 = most severe)
    session_count   INT     NOT NULL,  -- how many sessions contributed
    trend           TEXT    NOT NULL DEFAULT 'stable', -- "improving", "worsening", "stable"
    last_value      REAL    NOT NULL,  -- most recent session value
    avg_value       REAL    NOT NULL,  -- rolling average
    updated_at      TEXT    NOT NULL
);
```

### 5.3 Cross-Session Learning Query Examples

These queries power the AI prompt's historical context block:

```sql
-- Compound degradation profile for RM on NSX at Suzuka
SELECT avg_first_lap_s, deg_rate_s_per_lap, cliff_lap_est, sample_count
FROM compound_profiles
WHERE car_id = ? AND track = 'Suzuka' AND compound = 'RM';

-- Driver's worst weakness on this track (for coaching focus)
SELECT weakness_type, severity, trend
FROM driver_weaknesses
WHERE car_id = ? AND track = ?
ORDER BY severity DESC LIMIT 3;

-- What setup changes have improved this car at this track
SELECT field, value_before, value_after, lap_delta_ms, outcome_note
FROM setup_deltas
WHERE car_id = ? AND track = ?
  AND lap_delta_ms < 0        -- negative = faster
ORDER BY lap_delta_ms ASC LIMIT 5;

-- Did the AI's last fuel prediction match reality?
SELECT predicted_fuel_lpl, actual_fuel_lpl,
       (actual_fuel_lpl - predicted_fuel_lpl) AS prediction_error
FROM prediction_log
WHERE feature = 'Strategy Analysis' AND session_id IN (
  SELECT id FROM sessions WHERE car_id = ? ORDER BY id DESC LIMIT 10
);
```

---

## 6. AI Prompt Architecture Changes

### 6.1 Current Architecture (ad hoc)

Each of the 7 AI calls builds its own prompt in isolation. Context is assembled differently in each location:

```
_build_race_prompt()        ← ai_planner.py (strategy)
_build_practice_prompt()    ← ai_planner.py (practice)
_build_setup_from_scratch() ← ai_planner.py (build setup)
_build_coaching_prompt()    ← driving_advisor.py
_build_setup_prompt()       ← driving_advisor.py
_build_combined_prompt()    ← driving_advisor.py
_build_feeling_prompt()     ← driving_advisor.py
```

Helper methods exist in DrivingAdvisor (`_get_driver_feedback_context()`, `_get_previous_ai_context()`, `_get_event_context_block()`, `_get_history_context()`, `_car_track_header()`) but are NOT used by `ai_planner.py`. The two prompt builders do not share infrastructure.

### 6.2 Target Architecture (shared context builder)

The target is a **ContextBuilder** class shared by all AI calls, assembled in layers:

```
Layer 1: Static context (never changes)
  ├── GT7 Knowledge Base (cached, from load_gt7_reference())
  └── Driver Profile (driver_stats.md, read fresh)

Layer 2: Session context (set when event is activated)
  ├── Car: name, specs, PP, drivetrain, weight, power
  ├── Event: track, race_type, duration/laps, tyre_wear_mult, fuel_mult
  ├── Rules: BoP, tuning_locked, allowed_tuning, avail_tyres, req_tyres
  └── Setup: current setup (filtered by tuning permissions)

Layer 3: Historical context (queried from DB at call time)
  ├── Session history: best_lap, avg_lap, avg_fuel (last N sessions)
  ├── Driver weaknesses: top 3 by severity and trend
  ├── Compound profiles: deg_rate, cliff_lap, max_laps (cross-session)
  ├── Driver feedback: last 5 entries for this car+track
  ├── Previous AI recommendations: last 2 for this feature+car+track
  └── Setup deltas: what changed and what improved

Layer 4: Telemetry context (assembled at call time)
  ├── Per-lap table: time, fuel, lock-ups, wheelspin, oversteer, kerb,
  │                  lateral-G*, brake_cons (last 5 clean laps)
  ├── Compound sequences: per-lap times by compound (degradation trend)
  ├── Fuel sequence: per-lap burn (last 15 laps)
  ├── Tyre temps: per-corner averages (latest lap)
  ├── Advanced metrics (B1–B6): rev limiter, clusters, over-braking, etc.
  └── Data quality note: measured / calculated / estimated / assumed

Layer 5: Call-specific context (unique to each call type)
  ├── Strategy: degradation data, pit loss, race options
  ├── Practice: setup comparison, outlap exclusion note
  ├── Build Setup: gearbox analysis, session_type
  └── PTT: live race state snapshot (fuel, position, tyre age, pit window)
```

The ContextBuilder doesn't need to be a single class. It can be a set of shared free functions:

```python
# strategy/context_builder.py
def build_static_context(ai_client) -> str: ...
def build_session_context(car_name, car_specs, event_dict, setup_dict) -> str: ...
def build_historical_context(db, car_id, track, feature) -> str: ...
def build_telemetry_context(lap_data, tyre_temps, compound_sequences) -> str: ...
def build_data_quality_note() -> str: ...  # _DATA_QUALITY_NOTE constant
```

Each prompt builder calls the relevant context builders and assembles them. This eliminates the current inconsistency where DrivingAdvisor has rich context helpers that ai_planner doesn't use.

### 6.3 Data Quality Layer — Non-Negotiable

Every prompt must include a data quality declaration block. This is not optional:

```
## Data Quality Declarations
This prompt contains data from three quality tiers:

MEASURED — direct GT7 packet values. Treat as authoritative.
  Examples: fuel used per lap, tyre surface temperature, speed, throttle input

CALCULATED — derived from measured values via physics formulas.
  Examples: lock-up count (wheel slip threshold), brake consistency (std-dev),
            oversteer count (yaw rate × speed), longitudinal G (Δvelocity/Δtime)
  These are accurate but depend on threshold tuning. Report counts, not physics.

ESTIMATED — inferred proxies with meaningful uncertainty.
  Examples: lateral G (angvel_z × speed / 9.81 — not measured, sensor noise amplifies),
            tyre wear (radius shrinkage — also responds to temperature, not just wear),
            off-track (road normal threshold — false positives on banked corners)
  Never state these as fact. Use "may indicate", "suggests", "approximately".

HISTORICAL — averages from prior sessions. Accuracy depends on sample size (N= reported).
  Session count < 3: treat as anecdotal, not statistical.
  Session count ≥ 10: treat as reliable baseline.

ASSUMED — GT7 generic estimates when no measured data exists.
  Examples: RM tyre life 18–25 laps (GT7 general range, not measured for this car/track).
  Label clearly. Always prefer measured data over GT7 generic estimates.
```

### 6.4 Learning Feedback Layer

To close the learning loop, the AI should receive feedback on its past recommendations:

```
## Performance of Previous Recommendations (this car + track)
Strategy recommendation (2 sessions ago):
  AI suggested: 2-stop RH-RM-RM, pit lap 12 and 22
  Actual execution: pitted lap 11 (fuel low), pit lap 24 (tyre cliff)
  Fuel prediction error: +0.4 L/lap (AI under-predicted fuel burn)
  Tyre life prediction: RM lasted 13 laps vs predicted 12 → accurate within range

Setup change (last session):
  Changed: ARB front 4 → 3 (AI recommended to reduce understeer)
  Outcome: driver reported "better rotation, exit more stable" — improvement confirmed
  Lap delta: -0.4s on clean laps
```

This gives the AI the calibration data it needs to sharpen future estimates. It also surfaces when its predictions are systematically wrong (e.g. consistently underestimating fuel burn — the driver may be pushing harder than the AI models).

---

## 7. Phased Implementation Plan

### Phase 1 — Fix Broken Context Paths (Group 15 — Planned)

**Goal:** Every current AI call receives correct, complete context. No broken data paths.

**Scope:** Fully defined in `/docs/GROUP15_AI_CONTEXT_REMEDIATION_PLAN.md`.

| Fix | Impact | AWR |
|-----|--------|-----|
| DEF-P1-013: Strategy RaceParams race_type + tuning + BoP | Correct race type + legal setup advice | AWR-058 |
| DEF-P1-014: Practice history car_id=0 | Historical context now flows | AWR-059 |
| DEF-P2-036: PTT coaching car_name + compound | Coaching references the car | AWR-060 |
| DEF-P2-037: PTT setup advice active setup | Setup advice uses current setup | AWR-061 |
| DEF-P2-038: BoP status in strategy/practice prompts | BoP declared explicitly | AWR-062 |
| DEF-P2-039: Available tyres in all prompts | No illegal compound suggestions | AWR-063 |
| DEF-P2-040: Driver feedback in practice analysis | Practice AI hears driver complaints | AWR-064 |
| DEF-P2-041: Previous AI recs in practice analysis | Practice AI recalls prior advice | AWR-065 |
| DEF-P3-009: Timed race identification in strategy prompt | Correct timed race strategy | AWR-066 |
| DEF-P3-010: Race context in Build Car Setup | Setup built for correct event | AWR-067 |
| DEF-P3-011: Data quality annotations in strategy/practice | AI hedges uncertain claims | AWR-068 |
| DEF-P3-012: validate_ai_setup_response on strategy output | Illegal advice flagged | AWR-069 |

**Tests:** ~55 new tests in `tests/test_group15_ai_context_fixes.py`

**Estimated effort:** 2–3 days implementation, 1 day testing.

---

### Phase 2 — Per-Lap Telemetry in Practice and Strategy

**Goal:** Practice Analysis and Strategy Analysis receive the same per-lap telemetry richness that PTT coaching currently has. Close the inversion gap.

**New defect IDs:** DEF-P2-042 through DEF-P2-048 (to be assigned after Group 15 complete)

#### Phase 2-A: Per-Lap Telemetry Table in Practice Prompt

**What to add to `_build_practice_prompt()`:**

```
## Per-Lap Telemetry (last 5 clean laps)
Lap | Time    | Fuel | Lock-up | Wheelspin | Oversteer | Kerb | Lat-G*
 12 | 1:42.1  | 3.2L |    4    |     2     |     0(T)  |   6  |  2.8*
 13 | 1:41.8  | 3.1L |    2    |     1     |     1(T)  |   4  |  2.9*
...

(T) = throttle-on oversteer   * = estimated (angvel_z × speed / 9.81)
Outlap excluded from analysis.
```

**Source:** `lap_records` table — `lock_up_count`, `wheelspin_count`, `oversteer_count`, `oversteer_throttle_on_count`, `kerb_count`, `max_lat_g` are already written by `main.py EventDispatcher` (via Group 14).

**Implementation:** Add `per_lap_telemetry: list[dict] = []` parameter to `analyse_practice_session()` and `_build_practice_prompt()`. In `_run_practice_analysis()` worker, query:
```python
recent_laps = _hist_db.get_session_laps(session_id, exclude_pit=True, exclude_out=True, limit=5)
```

#### Phase 2-B: Per-Lap Fuel Sequence in Strategy Prompt

**What to add to `_build_race_prompt()`:**
```
## Fuel Trend (last 15 laps)
Per-lap: 3.1, 3.2, 3.0, 3.4, 3.1, 3.0, 3.2, 3.1, 3.3, 3.0, 3.2, 3.1, 3.4, 3.0, 3.2
Average: 3.15 L/lap [measured], Std-dev: 0.12 L/lap [calculated]
Worst case (95th pct): 3.4 L/lap
```

**Source:** Last 15 non-pit laps from `lap_records.fuel_used` for current car+track.

#### Phase 2-C: Compound Degradation Sequence in Strategy Prompt

**What to add:** Per-lap lap times grouped by compound (a sequence, not just avg/best/std):
```
Racing Medium (15 laps this session):
  1:42.1 → 1:42.4 → 1:42.6 → 1:42.9 → 1:43.4 → 1:44.1 (+ trending)
  Degradation rate: +0.18s/lap [calculated — linear regression on last 10 laps]
```

**Source:** `lap_records` WHERE `compound = 'RM'` AND `session_id = current_session` ORDER BY `lap_num`.

#### Phase 2-D: Tyre Temperature per Lap in Practice Prompt

**Prerequisite:** Tyre temps are captured per-frame by `recorder.py` but NOT stored as per-lap averages in `lap_records`. Need to add:
- `tyre_temp_fl_avg`, `tyre_temp_fr_avg`, `tyre_temp_rl_avg`, `tyre_temp_rr_avg` columns to `lap_records`
- Compute in `LapTelemetryRecorder._compute_stats()` from per-frame temps
- Write in `main.py EventDispatcher`

This is a schema migration (adds 4 columns — idempotent, backward compatible).

**What to add to practice prompt:**
```
## Tyre Temperature (latest clean lap) [measured]
FL: 78°C | FR: 91°C | RL: 82°C | RR: 88°C
Front outside/inside delta: +13°C → review camber or tyre pressure
Rear balance: within 6°C — acceptable
```

**Estimated effort:** Phase 2-A + 2-B: 1 day. Phase 2-C: 1 day. Phase 2-D: 2 days (schema + data path).

---

### Phase 3 — Historical Learning Data Model

**Goal:** Build the data model that enables cross-session learning. No AI prompt changes yet — this phase is purely about accumulating the right data.

#### Phase 3-A: Compound Profile Learning

After each session, update `compound_profiles`:
- Compute fresh-tyre pace (avg of laps 2–5 of each stint)
- Compute degradation rate (linear regression on laps 5+ of each stint)
- Estimate cliff lap (where degradation accelerates past threshold)
- Increment `sample_count`; roll into rolling average

**Trigger:** On session close (`_on_live_mode_changed` → Practice → other mode) or manual "Save Session".

#### Phase 3-B: Setup Delta Recording

When the Setup Builder saves a new setup that differs from the previous session's setup on the same car:
- Record each changed field in `setup_deltas`
- `ai_recommended` flag based on whether the change matches a recent AI recommendation
- `lap_delta_ms` populated after the next session's AI analysis compares current vs previous best

#### Phase 3-C: Prediction Log

After each Strategy Analysis run, record the predictions in `prediction_log`:
- `predicted_fuel_lpl` = the fuel burn used in the strategy
- `predicted_tyre_life_laps` = the compound life used
- `predicted_best_lap_ms` = the lap time target

After the race session completes, populate `actual_*` fields from the session DB.

#### Phase 3-D: Driver Weakness Tracker

After each session, update `driver_weaknesses`:
- Compute lock-up rate = `lock_up_count / clean_laps` for the session
- Compare to rolling average; update `severity` and `trend`
- Same for wheelspin, oversteer, brake consistency

**AI prompt change:** When `driver_weaknesses.severity > 0.6` and `trend = "worsening"`, inject into practice/coaching prompt:
```
## Recurring Weaknesses (based on last 8 sessions)
⚠ Lock-up rate: HIGH (4.2/lap avg, worsening over last 3 sessions)
   Recent feedback: "braking too late for T1" — connected to this pattern
```

**Estimated effort:** Phase 3-A through 3-D: 5–7 days (new DB tables, migration, computation logic, session-close hooks).

---

### Phase 4 — Tyre Radius Validation

**Goal:** Determine whether `tyre_radius` is a reliable wear indicator before using it in strategy calculations.

**Current status:** B5 metric in DrivingAdvisor uses radius trend. It is labelled as estimated. It is NOT used in strategy calculations.

**Validation method:**
1. For 5+ complete stints on the same compound (RM preferred — most data):
   - Record radius at start of stint (first frame after entering track) and end of stint (last frame before pitting)
   - Record stint length in laps
   - Record whether the driver reported tyre degradation in driver feedback
2. Plot: radius_delta vs stint_laps. If monotone and consistent across sessions → reliable proxy.
3. Plot: radius_delta vs driver-reported handling degradation. Correlation > 0.7 → use for AI.
4. If not validated: remove B5 from all prompts except with explicit "NOT VALIDATED — do not use for strategy" warning.

**Tool required:** A simple session analysis view that plots radius start/end vs lap count across sessions. Can be a Python matplotlib script that reads from the DB — not a UI feature.

**Decision gate:** Do not use radius data in any strategy or compound-life calculation until this validation is complete. Phase 3-A compound profiles use lap time degradation instead, which is directly measured.

---

### Phase 5 — Live Race Intelligence

**Goal:** The PTT race engineer becomes genuinely useful during a race, not just a post-lap review tool.

#### Phase 5-A: Live State Snapshot

Build a `LiveRaceSnapshot` dataclass populated every lap from tracker state:
```python
@dataclass
class LiveRaceSnapshot:
    lap_current: int
    laps_total: int          # 0 if timed race
    laps_remaining: int
    fuel_current_l: float    # from latest packet
    fuel_per_lap_avg: float  # from tracker
    fuel_needed_l: float     # laps_remaining × fuel_per_lap_avg
    fuel_margin_l: float     # fuel_current - fuel_needed (negative = deficit)
    tyre_age_laps: int       # laps since last pit
    compound_current: str
    mandatory_compound_used: bool
    last_lap_ms: int
    personal_best_ms: int
    pace_delta_ms: int       # last_lap vs personal_best
```

Expose as `tracker.live_snapshot` property. Pass to DrivingAdvisor for every PTT call.

#### Phase 5-B: Pit Window Calculation

Replace the static `stint.end_lap - 2` (warning) / `stint.end_lap` (box) with a real-time calculation:

```python
def compute_pit_window(snapshot: LiveRaceSnapshot, strategy: StrategyOption) -> tuple[int, int]:
    """Returns (warn_lap, box_lap) based on current fuel and tyre state."""
    fuel_limited_pit = snapshot.lap_current + int(snapshot.fuel_margin_l / snapshot.fuel_per_lap_avg)
    tyre_limited_pit = compute_tyre_cliff_lap(snapshot.compound_current, snapshot.tyre_age_laps)
    warn_lap = min(fuel_limited_pit, tyre_limited_pit) - 1
    box_lap = min(fuel_limited_pit, tyre_limited_pit)
    return warn_lap, box_lap
```

Announce when the pit window opens. Recalculate after every lap. Alert when the driver is past the window.

#### Phase 5-C: Dynamic Strategy Deviation Alert

When actual pace or fuel deviates significantly from the AI's strategy prediction:
- `|actual_fuel - predicted_fuel| > 0.3 L/lap for 3+ consecutive laps` → announce "fuel usage higher than planned, consider strategy change"
- `|actual_lap - predicted_lap| > 1.5s for 3+ consecutive laps` → announce "pace below target — review with AI?"

This requires the strategy AI's output to be stored (it is, in `ai_interactions.structured_payload`) and compared to live telemetry in the `EventDispatcher`.

---

### Phase 6 — Compound Intelligence Database

**Goal:** GT7 Pit Crew has its own per-car, per-track, per-compound performance database that replaces GT7 generic tyre estimates.

After Phase 3-A has accumulated enough compound profile data (≥5 sessions per compound per track):

- Replace "RM typically 18–25 laps" (assumed) with "RM on NSX at Suzuka: 21.4 laps avg (±2.1, N=7)" (measured/calculated)
- Strategy AI can use compound_profiles for stint length instead of generic estimates
- Degradation rate from profiles feeds into pit window calculation
- Cliff lap estimates replace the static GT7 range

The AI prompt section changes from:
```
## Estimated Tyre Life (GT7 generic)
Racing Soft: 10–16 laps | Racing Medium: 18–25 | Racing Hard: 28–40 [assumed]
```

To:
```
## Compound Profiles (this car + track, measured/calculated)
Racing Soft: avg 12.3 laps [calculated from 5 sessions, N=12 stints, degradation +0.31s/lap]
Racing Medium: avg 21.4 laps [calculated from 7 sessions, N=18 stints, degradation +0.18s/lap]
Racing Hard: avg 33.1 laps [calculated from 4 sessions, N=9 stints, degradation +0.07s/lap]
```

---

### Phase 7 — Track Intelligence and Setup Outcome Learning

**Goal:** GT7 Pit Crew understands where problems happen on track, remembers what setup changes were made, knows whether those changes worked, and learns how Leon responds to different setup directions — getting progressively more accurate with each session.

**Prerequisites:**
- Group 15 (Phase 1) complete and AWRs 058–069 verified — correct data flowing to all AI calls
- Phase 2 complete — per-lap telemetry in practice/strategy prompts
- Phase 3 complete — learning data model tables in DB (`setup_deltas`, `compound_profiles`, `prediction_log`, `driver_weaknesses`)

This phase adds the spatial and outcome intelligence layers on top of the foundation built by Phases 2 and 3. It does not modify Group 15 scope.

---

#### Phase 7-A: Corner Intelligence — Telemetry Event Location Mapping

**Problem:** Every lap, events (lock-ups, wheelspin, oversteer, snap throttle, kerb strikes, bottoming) are detected and counted. Their world-space positions (`position_x/y/z`) are available at detection time and stored temporarily in per-frame position lists (`lock_up_positions`, `wheelspin_positions`, etc. in `LapStats`). These lists are held in memory and **never persisted to the DB**. At session end, all spatial information is lost.

**What this unlocks:** "You lock up at the same two places every lap" is far more actionable than "you locked up 4 times." A race engineer tells you *where* the problem is. This phase does the same.

**New table: `telemetry_event_locations`**

```sql
CREATE TABLE IF NOT EXISTS telemetry_event_locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_record_id   INTEGER NOT NULL REFERENCES lap_records(id),
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    track           TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    -- Valid types: "lockup", "wheelspin", "oversteer", "oversteer_throttle",
    --              "snap_throttle", "kerb", "bottoming", "rev_limiter", "over_braking"
    pos_x           REAL    NOT NULL,
    pos_y           REAL    NOT NULL,
    pos_z           REAL    NOT NULL,
    speed_kmh       REAL    NOT NULL DEFAULT 0.0,
    gear            INT     NOT NULL DEFAULT 0,
    lap_num         INT     NOT NULL,
    recorded_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tel_evt_loc_car_track
    ON telemetry_event_locations(car_id, track, event_type);
```

**Data source:** `LapStats.lock_up_positions` / `wheelspin_positions` / `oversteer_positions` / `snap_throttle_positions` / `over_braking_positions` — already populated by `LapTelemetryRecorder._compute_stats()`. These are `list[tuple[float, float, float]]` (x, y, z coordinates from the GT7 packet at the moment of the event).

**Population trigger:** In `main.py EventDispatcher._dispatch()`, after `write_lap()` returns the `lap_record_id`, iterate the position lists and batch-insert rows into `telemetry_event_locations`.

**Implementation note:** Use a single `executemany()` call per event type per lap to keep the write fast. A lap with 4 lock-ups, 2 wheelspin events, and 1 oversteer event generates 7 rows — negligible overhead.

**Query for AI context:**
```python
# Get top event zones for this car+track (last 10 sessions)
SELECT event_type,
       ROUND(AVG(pos_x), 1) AS zone_x,
       ROUND(AVG(pos_y), 1) AS zone_y,
       ROUND(AVG(pos_z), 1) AS zone_z,
       COUNT(*) AS occurrence_count
FROM telemetry_event_locations
WHERE car_id = ? AND track = ?
  AND session_id IN (
      SELECT id FROM sessions WHERE car_id = ? AND track = ?
      ORDER BY id DESC LIMIT 10
  )
GROUP BY event_type, ROUND(pos_x / 50.0) * 50, ROUND(pos_z / 50.0) * 50
ORDER BY occurrence_count DESC
LIMIT 20;
```

This clusters events into 50m grid squares and returns the most frequent issue zones across the last 10 sessions.

---

#### Phase 7-B: Track Fingerprinting

**Problem:** The system has no persistent model of each track's structure. It knows Leon had 4 lock-ups this session but cannot connect this to "this is the turn where Leon always locks up on this car" without storing the spatial history.

**What this unlocks:** After 5+ sessions, the system builds a fingerprint of recurring trouble zones per car+track combination. This fingerprint is injected into coaching and setup prompts as `## Corner Intelligence`.

**New table: `track_corner_profiles`**

```sql
CREATE TABLE IF NOT EXISTS track_corner_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    track           TEXT    NOT NULL,
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    zone_label      TEXT    NOT NULL DEFAULT '',
    -- Auto-generated label (e.g. "Zone_A", "Zone_B") until user renames via UI
    -- User can rename: "T1 Braking", "Dunlop Hairpin", "Spoon Exit"
    center_x        REAL    NOT NULL,
    center_y        REAL    NOT NULL,
    center_z        REAL    NOT NULL,
    radius_m        REAL    NOT NULL DEFAULT 40.0,
    corner_type     TEXT    NOT NULL DEFAULT '',
    -- Inferred type: "braking_zone", "traction_zone", "high_speed", "kerb_sensitive"
    dominant_event  TEXT    NOT NULL DEFAULT '',
    -- Most frequent event type in this zone
    occurrence_count INT    NOT NULL DEFAULT 0,
    sessions_observed INT   NOT NULL DEFAULT 0,
    severity        REAL    NOT NULL DEFAULT 0.0,  -- normalized 0–1
    notes           TEXT    NOT NULL DEFAULT '',
    updated_at      TEXT    NOT NULL,
    UNIQUE(track, car_id, zone_label)
);
```

**Zone generation:** After each session, run the cluster query from Phase 7-A. For each cluster with `occurrence_count >= 3`, upsert a `track_corner_profiles` row:
- If an existing zone center is within `radius_m` of the new cluster: update `occurrence_count` and `sessions_observed`
- If no nearby zone exists: insert a new zone with an auto-label (Zone_A, Zone_B, etc.)
- Recompute `severity = occurrence_count / max_occurrence_in_session / sessions_observed`

**Inferred corner type:** Based on the cluster's dominant event:
- `lockup` → `braking_zone`
- `wheelspin` or `snap_throttle` → `traction_zone`
- `oversteer_throttle` → `traction_zone`
- `kerb` → `kerb_sensitive`
- `bottoming` → `bumpy_section`
- `rev_limiter` → `straight` (gear ratio target zone)

**AI prompt injection (example):**
```
## Corner Intelligence (Suzuka — Honda NSX '17 — 6 sessions observed)
Recurring issue zones [calculated — position clustering across sessions]:

Zone_A ("T1 Braking" — user-renamed):
  Dominant issue: Lock-up (14 events across 6 sessions, avg 2.3/lap)
  Secondary: Over-braking (9 events)
  Corner type: braking_zone | Severity: HIGH [calculated]
  Insight: braking point inconsistent across laps — brake consistency std-dev 6.1m

Zone_B ("Spoon Exit"):
  Dominant issue: Wheelspin (11 events across 5 sessions)
  Secondary: Snap throttle (6 events)
  Corner type: traction_zone | Severity: MEDIUM [calculated]
  Insight: throttle applied before full rotation complete

Zone_C ("Casio Triangle"):
  Dominant issue: Oversteer throttle-on (7 events across 4 sessions)
  Corner type: traction_zone | Severity: MEDIUM
```

This replaces the current B2 location clusters in DrivingAdvisor (which only covers the current session and is discarded) with a persistent multi-session view.

---

#### Phase 7-C: Setup Outcome Learning

**Extends:** Phase 3-B `setup_deltas` table. Phase 3-B records what changed; Phase 7-C adds the full outcome pipeline including telemetry comparison, driver feedback, and confidence scoring.

**The problem with Phase 3-B alone:** `setup_deltas` records that ARB front changed from 5 to 4 and the lap time improved by 0.3s. But it doesn't record: which events improved (lock-ups reduced?), what the driver felt, whether the AI recommended it, or how confident we should be that the change caused the improvement vs natural variation.

**New table: `setup_change_outcomes`**

```sql
CREATE TABLE IF NOT EXISTS setup_change_outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id              INTEGER NOT NULL REFERENCES cars(id),
    track               TEXT    NOT NULL,
    compound            TEXT    NOT NULL DEFAULT '',
    field               TEXT    NOT NULL,  -- e.g. "arb_front"
    value_before        REAL    NOT NULL,
    value_after         REAL    NOT NULL,
    ai_recommended      INT     NOT NULL DEFAULT 0,
    ai_interaction_id   INTEGER REFERENCES ai_interactions(id),
    session_before_id   INTEGER REFERENCES sessions(id),
    session_after_id    INTEGER REFERENCES sessions(id),
    -- Outcome metrics (populated after session_after completes)
    lap_delta_ms        INT     NOT NULL DEFAULT 0,      -- negative = faster
    lockup_rate_before  REAL    NOT NULL DEFAULT 0.0,    -- events/clean_lap
    lockup_rate_after   REAL    NOT NULL DEFAULT 0.0,
    wheelspin_rate_before REAL  NOT NULL DEFAULT 0.0,
    wheelspin_rate_after  REAL  NOT NULL DEFAULT 0.0,
    oversteer_rate_before REAL  NOT NULL DEFAULT 0.0,
    oversteer_rate_after  REAL  NOT NULL DEFAULT 0.0,
    fuel_delta_lpl      REAL    NOT NULL DEFAULT 0.0,    -- fuel burn change
    driver_feedback     TEXT    NOT NULL DEFAULT '',     -- free text verdict
    outcome             TEXT    NOT NULL DEFAULT 'unknown',
    -- Values: "improved", "worsened", "neutral", "insufficient_data", "unknown"
    confidence          REAL    NOT NULL DEFAULT 0.0,   -- 0.0–1.0
    -- Confidence sources: AI recommendation + multiple sessions + clear delta
    recorded_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sco_car_track_field
    ON setup_change_outcomes(car_id, track, field);
```

**Confidence scoring formula:**
```
confidence = 0.0
if ai_recommended:              confidence += 0.2
if |lap_delta_ms| > 200:        confidence += 0.3   # clear lap time signal
if session_after_has_5+_laps:   confidence += 0.2
if driver_feedback != "":       confidence += 0.2
if cross_validated_3+_sessions: confidence += 0.1
# cap at 1.0
```

**Population trigger:** On session close, for each setup field that changed since the previous session on the same car+track:
1. Look up `session_before_id` from `sessions` (previous session, same car+track)
2. Compute `lap_delta_ms` = `current_session.avg_lap_ms - previous_session.avg_lap_ms`
3. Compute event rate deltas from `lap_records` aggregates
4. Check `driver_feedback` for the latest entry in `driver_feedback` table
5. Assign `outcome` based on `lap_delta_ms` and driver_feedback
6. Compute and store confidence

**AI prompt injection for setup advice:**
```
## Setup Change History (Porsche 911 RSR at Fuji — last 5 relevant changes)
Successful changes (confidence ≥ 0.6):
  ARB front: 5 → 4 [AI recommended]
    Result: +0.32s faster avg, lock-ups −0.8/lap, driver: "better entry rotation"
    Confidence: 0.85 [high — multiple sessions confirm]

  Rear toe: 0.05° → 0.08°
    Result: +0.18s faster avg, oversteer −0.4/lap
    Confidence: 0.70

Failed/worsened changes (confidence ≥ 0.5):
  Spring front: 3 → 2
    Result: −0.15s slower avg, driver: "lazy front, can't trail brake"
    Confidence: 0.65 — AVOID: front spring reduction causes understeer tendency

Insufficient data:
  Differential LSD accel: 30 → 25 (changed last session — insufficient comparison data)
```

---

#### Phase 7-D: Driver-Specific Setup Memory

**Problem:** `driver_stats.md` is a static file written once. It captures Leon's style as it was when the file was written. It does not update as Leon's data accumulates in the DB. The AI cannot say "over the last 15 sessions, Leon's rear instability under braking has increased" — it only knows what was written in the file.

**What this unlocks:** A dynamic driver profile that grows from actual telemetry and feedback history, expressed as named preferences with evidence counts. This replaces/augments the static `driver_stats.md` file as the primary driver context source for setup AI calls.

**New table: `driver_preference_profile`**

```sql
CREATE TABLE IF NOT EXISTS driver_preference_profile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_key  TEXT    NOT NULL UNIQUE,
    -- Defined vocabulary (matches user specification):
    -- "trail_braking", "front_end_bite", "smooth_throttle",
    -- "stable_rear_platform", "rotation_on_entry", "lazy_front_aversion",
    -- "rear_instability_sensitivity", "kerb_tolerance",
    -- "snap_throttle_tendency", "oversteer_recovery_skill"
    preference_type TEXT    NOT NULL DEFAULT 'style',
    -- Values: "style" (what Leon does), "sensitivity" (what bothers Leon),
    --         "aversion" (what Leon explicitly dislikes)
    strength        REAL    NOT NULL DEFAULT 0.5,   -- 0.0 (absent) to 1.0 (dominant)
    evidence_source TEXT    NOT NULL DEFAULT '',    -- "telemetry", "feedback", "both"
    evidence_count  INT     NOT NULL DEFAULT 0,     -- sessions/feedback items contributing
    description     TEXT    NOT NULL DEFAULT '',    -- human-readable summary
    last_updated    TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
```

**Preference computation:**

| Key | Calculation | Update trigger |
|-----|-------------|---------------|
| `trail_braking` | Brake input still > 20% at apex position — frequency across sessions | Per session close |
| `front_end_bite` | Mentions in driver_feedback "lazy front", "needs more front" → negative correlation; mentions "good rotation" → positive | Per driver feedback submit |
| `smooth_throttle` | snap_throttle_count / clean_laps — high = low smooth_throttle strength | Per session close |
| `stable_rear_platform` | oversteer_rate (especially braking oversteer) — high = high sensitivity | Per session close |
| `rotation_on_entry` | From driver_feedback positive mentions + setup changes that reduced entry understeer with positive outcome | Per session close |
| `lazy_front_aversion` | driver_feedback mentions "lazy front" + successful spring front increases with positive outcome | Per setup_change_outcomes |
| `rear_instability_sensitivity` | `driver_feedback.rear_braking` rated severe + oversteer_rate trend | Per session close |
| `snap_throttle_tendency` | snap_throttle_count / clean_laps rolling average | Per session close |

**AI prompt injection:**
```
## Driver Preference Profile (Leon — based on 23 sessions, 6 tracks)
[dynamically generated from driver_preference_profile table]

Driving style [evidence: telemetry]:
  Trail braking: Strong (0.82/1.0) — applies brake past apex on 74% of corners
  Smooth throttle: Moderate weakness (0.35/1.0) — snap throttle rate 1.8/lap avg
  Oversteer recovery: Good (0.71/1.0) — recovers oversteer events without spin

Sensitivities [evidence: feedback + telemetry]:
  Rear instability: HIGH sensitivity (0.88/1.0) — frequently rates rear_braking severe
  Lazy front: Aversion confirmed (0.79/1.0) — 4/5 feedback entries mention front
  Kerb tolerance: Moderate (0.55/1.0) — kerb count high but lap time not affected

Setup response history [evidence: setup_change_outcomes]:
  Responds well to: ARB front softening (4/4 instances improved), rear toe increase (3/3)
  Responds poorly to: front spring reduction (3/4 instances worsened — lazy front complaint)

IMPORTANT: Prioritise rear stability and front bite in all setup recommendations.
           Avoid front spring reduction on this car. Leon will not tolerate lazy front end.
```

This section is generated at call time from DB queries, not from a static file — ensuring it stays current.

---

#### Phase 7-E: Recommendation Confidence Scoring

**Problem:** All current AI recommendations are stated without qualification. The AI may say "soften front springs" with identical confidence whether it has 10 sessions of evidence or this is the first session on this car+track combination.

**What this unlocks:** Every AI setup or strategy recommendation includes a confidence level. The output instructions are updated to require confidence reporting in the JSON response.

**New table: `recommendation_outcomes`**

```sql
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ai_interaction_id   INTEGER NOT NULL REFERENCES ai_interactions(id),
    car_id              INTEGER NOT NULL REFERENCES cars(id),
    track               TEXT    NOT NULL,
    feature             TEXT    NOT NULL,
    -- Context at time of recommendation
    sessions_on_car_track INT   NOT NULL DEFAULT 0,
    setup_change_history_count INT NOT NULL DEFAULT 0,
    driver_feedback_count INT   NOT NULL DEFAULT 0,
    -- Outcome (filled in after driver acts)
    was_followed        INT     DEFAULT NULL,  -- 1=yes, 0=no, NULL=unknown
    driver_rating       INT     DEFAULT NULL,  -- 1–5 or NULL
    outcome_note        TEXT    NOT NULL DEFAULT '',
    session_after_id    INTEGER REFERENCES sessions(id),
    setup_change_outcome_id INTEGER REFERENCES setup_change_outcomes(id),
    recorded_at         TEXT    NOT NULL
);
```

**Confidence tiers:**

| Tier | Conditions | Label in prompt |
|------|-----------|-----------------|
| **HIGH** | ≥5 sessions on car+track AND ≥3 prior successful changes in same area | `HIGH — supported by prior successful changes on this car+track` |
| **MEDIUM** | 2–4 sessions on car+track OR telemetry supports but limited history | `MEDIUM — telemetry suggests but limited historical confirmation` |
| **LOW** | <2 sessions on car+track OR new car+track combination | `LOW — first session on this car+track; recommendation based on GT7 general knowledge` |
| **ASSUMED** | No telemetry, GT7 generic knowledge only | `ASSUMED — no measured data available; general GT7 setup principle` |

**Output instruction change (to be added to setup AI prompts):**
```
For each setup recommendation, include a "confidence" field in the JSON response:
  "confidence": "HIGH | MEDIUM | LOW | ASSUMED"
  "confidence_reason": "3 prior sessions confirm ARB reduction improves entry rotation on this car"

Do NOT state ASSUMED recommendations as fact. Use "typically", "in general", "may help".
HIGH confidence recommendations may be stated directly.
```

---

#### Phase 7-F: Learning Loop Lifecycle

This ties together all Phase 7 components into a closed loop. Every AI recommendation passes through the full cycle.

**Lifecycle:**

```
Step 1 — AI recommends
  AI Setup Advice / Practice Analysis / Build Car Setup
  → AI response includes setup changes + confidence tier
  → Stored in: ai_interactions (full response), recommendation_outcomes (context snapshot)

Step 2 — User acts or rejects
  User applies changes to Setup Builder and saves
  → setup_change_outcomes row created: field, value_before, value_after, ai_recommended=1
  → OR: user rejects → recommendation_outcomes.was_followed = 0

Step 3 — User completes practice laps
  EventDispatcher writes laps to lap_records
  Telemetry events written to telemetry_event_locations
  Compound stats accumulate

Step 4 — Session closes (mode switch or Save Session)
  System computes session metrics (avg_lap, lock-up rate, wheelspin rate, etc.)
  setup_change_outcomes.session_after_id set
  lap_delta_ms, event rate deltas, confidence computed and stored
  driver_preference_profile updated from session telemetry
  track_corner_profiles updated from telemetry_event_locations clusters
  compound_profiles updated with stint data

Step 5 — Driver submits feedback (optional)
  driver_feedback row inserted
  driver_preference_profile updated with feedback-derived preferences
  recommendation_outcomes.driver_rating set
  setup_change_outcomes.driver_feedback, outcome updated

Step 6 — Next AI call (any feature)
  Historical context block now includes:
  - Corner intelligence from track_corner_profiles (7-B)
  - Successful and failed setup changes from setup_change_outcomes (7-C)
  - Driver preferences from driver_preference_profile (7-D)
  - Confidence tier computed from recommendation_outcomes history (7-E)
  AI response is calibrated by actual outcome history
```

**Implementation note:** Steps 1–2 require no new infrastructure beyond Phase 7-E's `recommendation_outcomes` table. Steps 3–4 are the session-close hook (a new `_on_session_close()` method in dashboard.py that fires all the DB population routines). Step 5 already has driver_feedback — just needs to wire to `recommendation_outcomes`. Step 6 is a query-time operation — no new infrastructure, just new queries to the Phase 7 tables.

---

#### Phase 7: Required DB Additions Summary

| Table | Purpose | Depends On |
|-------|---------|-----------|
| `telemetry_event_locations` | Persist spatial coordinates of telemetry events per lap | `lap_records` FK; Phase 2 telemetry flow |
| `track_corner_profiles` | Persistent clustered track zones by event type | `telemetry_event_locations` data accumulation |
| `setup_change_outcomes` | Full setup change before/after with telemetry delta and outcome | `sessions`, `ai_interactions`, Phase 3-B `setup_deltas` |
| `recommendation_outcomes` | Track whether AI recommendations were followed and whether they worked | `ai_interactions` FK |
| `driver_preference_profile` | Dynamic driver style profile from telemetry + feedback | `driver_feedback`, `lap_records` aggregates |
| `car_track_setup_baselines` | Best-performing setup per car+track+compound combination | `sessions`, `setups`, `lap_records` |

**`car_track_setup_baselines` schema:**

```sql
CREATE TABLE IF NOT EXISTS car_track_setup_baselines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id          INTEGER NOT NULL REFERENCES cars(id),
    track           TEXT    NOT NULL,
    compound        TEXT    NOT NULL DEFAULT '',
    setup_json      TEXT    NOT NULL DEFAULT '{}',
    best_lap_ms     INT     NOT NULL DEFAULT 0,
    avg_lap_ms      INT     NOT NULL DEFAULT 0,
    avg_fuel_lpl    REAL    NOT NULL DEFAULT 0.0,
    session_count   INT     NOT NULL DEFAULT 0,
    last_session_id INTEGER REFERENCES sessions(id),
    updated_at      TEXT    NOT NULL,
    UNIQUE(car_id, track, compound)
);
```

---

#### Phase 7: Future AI Prompt Changes

When Phase 7 data is available (≥3 sessions contributing to each table), the practice, setup, and strategy prompts will include:

```
## Corner Intelligence  ← from track_corner_profiles
[Zone list with dominant event, severity, session count]

## Setup History — What Worked  ← from setup_change_outcomes (outcome="improved")
[field, value_before → value_after, lap_delta_ms, driver verdict, confidence]

## Setup History — What Failed  ← from setup_change_outcomes (outcome="worsened")
[field, value_before → value_after, lap_delta_ms, driver complaint, confidence]
IMPORTANT: Do not recommend these changes again.

## Driver Preference Profile  ← from driver_preference_profile
[Driving style, sensitivities, setup response patterns]
IMPORTANT: Prioritise {top_preferences} in all recommendations.

## Baseline Setup  ← from car_track_setup_baselines
[Best performing setup over N sessions — filtered by tuning permissions]

## Recommendation Confidence
Available evidence: {session_count} sessions on this car+track.
Confidence tier: HIGH | MEDIUM | LOW | ASSUMED
[reason]
```

All data retains the `[measured]`, `[calculated]`, `[estimated]`, `[historical]`, or `[assumed]` labels from the data quality layer defined in Phase 1 (Group 15 DEF-P3-011).

---

#### Phase 7: Recommended Implementation Group

**Group 31** = Race-engineer prompt directives (AC1–AC14) + bottoming classifier + server-side validation + `prior_outcomes` structured block + C-series defect fixes (C1 setup_fields rebuild, C2 max_tokens=1500, C3 locked-field strip + validation banner, I1 ride-height-at-max directive, I5 _derive_locked_fields comments). Delivered 2026-06-29.

**Group 16** = Phase 2 (per-lap telemetry in practice/strategy prompts) — immediate next group after Group 15
**Group 17** = Phase 3 (learning data model — `setup_deltas`, `compound_profiles`, `prediction_log`, `driver_weaknesses`)
**Group 18** = Phase 7-A + 7-B (corner intelligence — `telemetry_event_locations` + `track_corner_profiles`)
**Group 19** = Phase 7-C + 7-D (setup outcome learning + driver preference profile)
**Group 20** = Phase 7-E + 7-F (confidence scoring + full learning loop lifecycle)
**Group 21** = Phase 5 (live race intelligence — `LiveRaceSnapshot`, dynamic pit window, deviation alerts)
**Group 22** = Phase 6 + 7 integration (compound intelligence database feeds into setup outcome confidence)

Phase 4 (tyre radius validation) runs as a background research task throughout Groups 16–20, not as a standalone group. The validation check gates whether radius data is promoted to the Phase 5 pit window calculation.

---

## Implementation Priority Summary

| Phase | Group | Focus | Effort | Unlocks |
|-------|-------|-------|--------|---------|
| **Phase 1 (Group 15)** | 15 | Fix broken context — right data to right calls | 2–3 days | Correct AI output today |
| **Phase 2** | 16 | Per-lap telemetry in practice/strategy prompts | 3–4 days | Strategy AI has real telemetry |
| **Phase 3** | 17 | Learning data model (DB tables + population) | 5–7 days | Cross-session learning infrastructure |
| **Phase 4** | background | Tyre radius validation (research task) | 1 day + data accumulation | Safe to use wear proxy |
| **Phase 5** | 21 | Live race intelligence (snapshot + pit window) | 3–4 days | Real-time race engineer |
| **Phase 6** | 22 | Compound intelligence database | 2 days + data accumulation | Own tyre life models |
| **Phase 7-A/B** | 18 | Corner intelligence — event location mapping + track zones | 3–4 days | "Where" problems happen on track |
| **Phase 7-C/D** | 19 | Setup outcome learning + driver preference profile | 4–5 days | What works for this driver on this car |
| **Phase 7-E/F** | 20 | Confidence scoring + full learning loop lifecycle | 2–3 days | AI knows how reliable its own advice is |

**Sequencing rules:**
- Do not start Phase 2 (Group 16) until Group 15 is complete and AWRs 058–069 verified.
- Do not start Phase 7-A (Group 18) until Phase 2 is complete — event locations depend on per-lap telemetry data flowing correctly.
- Phase 3 (Group 17) can run in parallel with Phase 2 — DB tables are additive and population hooks are independent of prompt changes.
- Phase 7-C/D (Group 19) depends on Phase 3 — `setup_deltas` and `driver_weaknesses` tables must exist.
- Phase 5 (Group 21) depends on Phase 7-E (Group 20) for the compound cliff lap estimates used in pit window calculation.
- Phase 4 is a research task, not a development group. Accumulate data from Group 16 onwards; validate when ≥5 complete stints per compound are in the DB. Decision gate before Phase 6.

**What the learning system looks like after Phase 7 is complete:**

```
Session 1: AI gives generic GT7 advice. Confidence: ASSUMED.
Session 5: AI knows Leon's top weakness zones at this track. Confidence: LOW→MEDIUM.
Session 10: AI knows which setup changes worked. Confidence: MEDIUM.
Session 15: AI has a driver preference profile from telemetry + feedback. Confidence: HIGH.
Session 20+: AI recommendation carries evidence: "ARB softening at front improved T1
             entry in 4 of 5 prior attempts on this car. High confidence."
```

---

## Appendix: Telemetry Signal Catalogue

### A.1 Measured Signals (direct GT7 packet)

| Signal | Variable | Accuracy | Use |
|--------|----------|----------|-----|
| Fuel level | `fuel_level` | ±0.1L | Fuel per lap, fuel remaining |
| Speed | `car_speed_ms` | ±1 km/h | Top speed, speed profiles |
| Throttle input | `throttle_raw` | 0–255 | Throttle application analysis |
| Brake input | `brake_raw` | 0–255 | Brake point detection |
| Engine RPM | `engine_rpm` | ±10 RPM | Rev limiter detection |
| Tyre surface temp (4 corners) | `tyre_surface_temp_*` | ±2°C | Tyre balance diagnosis |
| Suspension displacement (4 corners) | `suspension_height_*` | ±1mm | Bottoming, ride height |
| Tyre rolling radius (4 corners) | `tyre_radius_*` | ±0.1mm | Wear proxy (not validated) |
| Road normal | `road_normal_x/y/z` | directional | Off-track detection |
| Body height | `body_height_m` | ±5mm | Bottoming detection |
| Position | `position_x/y/z` | ±1m | Location clustering |
| Velocity | `velocity_x/y/z` | ±0.1 m/s | Speed, longitudinal G (derived) |
| Angular velocity | `angular_velocity_x/y/z` | ±0.01 rad/s | Lateral G (derived), oversteer |

### A.2 Calculated Signals (derived, formula-based)

| Signal | Formula | Accuracy | Use |
|--------|---------|----------|-----|
| Fuel used | `fuel_start − fuel_end` | High (±0.1L) | Strategy fuel model |
| Lock-up | Wheel slip from angular velocity vs ground speed | Medium | Brake diagnosis |
| Wheelspin | Wheel spin from angular velocity vs ground speed | Medium | Traction/exit diagnosis |
| Oversteer | Yaw rate × speed exceeds threshold | Medium | Balance diagnosis |
| Brake consistency | Std-dev of brake initiation positions | High | Driver consistency |
| Longitudinal G | Δvelocity / Δtime | Medium | Braking/acceleration analysis |
| Degradation rate | Linear regression on lap time sequence | Medium (N≥5) | Stint length estimation |

### A.3 Estimated Signals (inferred, uncertain)

| Signal | Proxy | Uncertainty | Current Use |
|--------|-------|-------------|-------------|
| Lateral G | `angvel_z × speed / 9.81` | ±30% (sensor noise) | DrivingAdvisor coaching |
| Tyre wear | `tyre_radius` trend | Unvalidated | DrivingAdvisor B5 metric (labelled) |
| Off-track | `road_normal_y < threshold` | False positives on banking | DrivingAdvisor B6 metric |
| Over-braking zone | Position clustering near lock-up events | Corner-dependent | DrivingAdvisor B3 metric |
| Car max speed theoretical | Extrapolation from `rev_limiter_by_gear` and tyre radius | Medium | DrivingAdvisor B4 metric |

### A.4 Assumed Values (GT7 generic, not measured)

| Value | Source | Condition for promotion to measured |
|-------|--------|-------------------------------------|
| RM tyre life 18–25 laps | GT7 generic knowledge | 5+ sessions with compound profiling |
| RH tyre life 28–40 laps | GT7 generic knowledge | 5+ sessions with compound profiling |
| RS tyre life 10–16 laps | GT7 generic knowledge | 5+ sessions with compound profiling |
| Refuel speed default 10 L/s | User-configurable default | Measured from actual pit lap time |
| Pit loss default 23s | User-configurable default | Measured from actual pit lap time |

---

*This roadmap covers the engineering path from "AI prompt tool" to "learning race engineer." Group 15 (immediate) fixes the broken foundation. Phases 2–6 build the intelligence stack on top of it. Do not implement Phase 2+ until Group 15 AWRs are verified.*
