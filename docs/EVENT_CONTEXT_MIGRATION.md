# EventContext Migration — `config["strategy"]` dependency register

> Sprint: **State Consolidation 1 — EventContext** · 2026-07-03
> Companion: `data/event_context.py`, `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§5, §7)
> Status: EventContext read model landed; `config["strategy"]` **retained** as
> legacy compatibility. This document lists every remaining dependency and the
> migration plan.

---

## 1. Purpose

`config["strategy"]` is a "god dict": `_on_event_set_active()`
(`ui/dashboard.py:7050`) fans the active event into it, and ~35 call sites read
event/race truth back out of it. This sprint introduced `EventContext`
(`data/event_context.py`) as the canonical, normalised read model. **No behaviour
changed**; `config["strategy"]` still exists and is still written. This register
enumerates the dependencies so later sprints can migrate them safely.

## 2. Two schemas EventContext reconciles

| Concept | DB event record (`SessionDB.get_event`) | `config["strategy"]` | EventContext field |
|---------|------------------------------------------|----------------------|--------------------|
| race duration (min) | `duration_mins` | `race_duration_minutes` | `race_duration_minutes` |
| tyre wear multiplier | `tyre_wear` | `tyre_wear_multiplier` | `tyre_wear_multiplier` |
| fuel multiplier | `fuel_mult` | `fuel_mult` | `fuel_multiplier` |
| refuel rate | `refuel_rate_lps` | `refuel_speed_lps` | `refuel_rate_lps` |
| required tyres | `req_tyres` | `required_tyres` | `required_tyres` |
| available tyres | `avail_tyres` | `avail_tyres` | `available_tyres` |
| allowed tuning | `allowed_tuning_categories` (JSON) | `allowed_tuning_categories` | `allowed_tuning_categories` |
| BoP / tuning | `bop`,`tuning` (0/1) | `bop`,`tuning` (bool) | `bop_enabled`,`tuning_allowed` |
| laps | `laps` | `laps` / `total_laps` | `laps` |
| car | *(not stored)* | `car` | `car` |
| track ids | *(not stored)* | `track_location_id`,`layout_id` | `track_location_id`,`layout_id` |
| event id | `id` | `event_id` | `event_id` |

Resolution rule: **prefer the durable DB event record** for race-rule fields
(so an edited-and-saved event never returns a stale value), overlay `car` /
track ids from the strategy snapshot (the events table doesn't store them), fall
back to the strategy dict entirely when no DB record is available.

## 3. The single writer (fan-out source)

| Site | What it does |
|------|--------------|
| `ui/dashboard.py:7050` `_on_event_set_active()` | Saves the event to the DB **and** writes ~20 fields into `config["strategy"]`; also pushes the DB event dict to `driving_advisor.set_event_context()`. **This is the fan-out to remove in a later sprint** (replace strategy writes with an EventContext the consumers read). |

## 4. Read-site register (`config["strategy"]`)

### 4a. EVENT-CONFIG reads — belong to EventContext (migration candidates)

| Site (`ui/dashboard.py`) | Method | Field(s) read | Risk |
|--------------------------|--------|---------------|------|
| 978 | `_on_live_mode_changed` | track, car, config_id, event_id | Med (opens DB session) |
| 1423 | telemetry/debug refresh | car | Low |
| 2114 | `_update_telemetry_labels` | car | Low |
| 2457 | `_resolve_setup_id_for_lap` | car | Low |
| 2583 | `_compute_race_config_id` | track, car, laps, race_type | Med (feeds config_id hash) |
| 2620 | `_update_race_config` | race_type, laps, duration | Med (pushes to tracker/engine) |
| 2653 | `_get_mandatory_compounds` | mandatory_compounds / required_tyres | Low |
| 3016 | `_save_session_to_db` | track, car | Low |
| 3094 | `_save_setup_from_lapdata` | track | Low |
| 3569 | `_run_practice_analysis` | full race_params (race_type, laps, duration, tyre_wear, fuel_mult, bop, tuning, allowed_tuning, avail_tyres, car, track) | **High** (AI prompt input — migrate late, snapshot-frozen) |
| 3713 | `_display_practice_results` | car/track context | Med |
| 3827 | `_display_strategy_results` | car/track context | Med |
| 4199 | `_build_ai_analysis_group` | fuel_mult | Low (label) |
| 4682 | `_sb_save_race_plan` | car | Low |
| 4784 | `_sb_refresh_saved_plans_combo` | car | Low |
| 4822 | `_live_init_from_plan` | car | Low |
| 5187 | `_refresh_bop_label` | car | Low |
| 5257, 5271 | BoP label/toggle | bop | Low |
| 5273 | BoP label | car | Low |
| 5382 | tyre-degradation setup | tyre_wear_multiplier | Med (strategy engine) |
| 5970 | `_sync_strategy_from_event` | track, car, race_type, duration, laps, tyre_wear, fuel_mult, refuel | Med (builds the on-screen event summary — a near-duplicate of `EventContext.summary_line()`) |
| 6017 | `_sync_practice_from_event` | car | Low |
| 6038 | `_refresh_telemetry_context` | event, car, track | **MIGRATED this sprint → reads `_build_event_context()`** |

External:

| Site | Method | Field | Note |
|------|--------|-------|------|
| `strategy/driving_advisor.py:1279` | `_get_event_context_block` | track (fallback) | Already uses its own `_event_ctx` DB dict; the `config["strategy"]` read is only a track fallback. Leave until the strategy prompt is migrated. |

### 4b. NON-EVENT reads — **do NOT move to EventContext**

These live in `config["strategy"]` but are not event/race configuration; they
belong to **StrategyContext** (now landed — State Consolidation 2,
`data/strategy_context.py`; see `docs/STRATEGY_CONTEXT_MIGRATION.md`) / telemetry
/ app-settings owners.

| Site | Method | Field | Correct future owner |
|------|--------|-------|----------------------|
| 498 | `__init__` | `stops[]` (saved stint plan) | StrategyContext |
| 2601 | `_computed_fuel_burn_lpl` | `fuel_burn_per_lap` | StrategyContext (telemetry-derived) |
| 2740 | `_refresh_lap_bank` | `config_id` | StrategyContext (derived match key) — **MIGRATED (State Consolidation 2) → reads `_build_strategy_context().config_id`** |
| 3238, 3250 | `_assemble_strategy_inputs` | `fuel_burn_per_lap`, plan fields | StrategyContext |
| 3344 | `_launch_replan_worker` | plan/strategy fields | StrategyContext |
| 3414, 3454 | `_run_ai_analysis` | strategy inputs, `config_id` | StrategyContext |
| 4193 | `_build_ai_analysis_group` | `fuel_burn_per_lap` | StrategyContext |
| 5383 | tyre-degradation | `degradation_consecutive_laps` | App setting |

> Note: several event-config and strategy reads are interleaved in the same
> method (e.g. `_run_practice_analysis`, `_assemble_strategy_inputs`). Those
> methods migrate when **both** EventContext and StrategyContext exist, taking
> event fields from EventContext and plan/telemetry fields from StrategyContext.

## 5. What was migrated this sprint

- **`ui/dashboard.py` `_build_event_context()` (NEW)** — builds the canonical
  `EventContext` from `_active_event()` (DB) + `config["strategy"]` +
  `active_event_id`. Defensive; never raises.
- **`_refresh_telemetry_context()`** — event/car/track now read from
  `EventContext` instead of `config["strategy"]`. The DEF-P1-011 fuel-burn
  behaviour is unchanged.

Everything else still reads `config["strategy"]` (compatibility preserved).

## 6. Migration plan (later sprints)

1. **Low-risk read-only consumers first** — migrate the "Low" rows in §4a to
   `self._build_event_context()` (labels, car/track displays, BoP label,
   mandatory compounds, `_sync_practice_from_event`). Each is a display read with
   no behaviour change.
2. **Event summary** — replace `_sync_strategy_from_event`'s hand-built summary
   string with `EventContext.summary_line()` + validation warnings (keep
   `_update_race_config()`).
3. **StrategyContext (LANDED — State Consolidation 2)** — `data/strategy_context.py`
   owns `stops`, `fuel_burn_per_lap`, `config_id`, ref-lap/pace fields,
   degradation assumptions + tolerances, and provides a frozen
   `StrategyPromptSnapshot` (EventContext race config + StrategyContext plan). Still
   **deferred**: migrating `_assemble_strategy_inputs`, `_run_ai_analysis`,
   `_run_practice_analysis` to read event fields from EventContext and plan fields
   from StrategyContext, freezing the snapshot per AI call (fixes SSOT-7). See
   `docs/STRATEGY_CONTEXT_MIGRATION.md`.
4. **SetupContext** — cache setup diagnosis per car/track keyed on
   `EventContext.change_hash`; the hash lets consumers cheaply detect a changed
   event and invalidate derived snapshots.
5. **Remove the fan-out** — once consumers read EventContext,
   `_on_event_set_active()` stops writing race-rule fields into
   `config["strategy"]`; the dict keeps only genuinely non-event keys
   (`stops`, `fuel_burn_per_lap`, `config_id`, …) or is retired in favour of
   StrategyContext.

## 7. Next-step plan for StrategyContext & SetupContext

- **StrategyContext**: owns stint plan, tyre refs, feasibility inputs, and the
  frozen strategy prompt snapshot. Reads event fields **from EventContext**, never
  from `config["strategy"]`. Depends on this sprint (EventContext) being in place.
- **SetupContext**: owns the current setup + cached setup diagnosis, keyed on
  `EventContext.change_hash` so diagnosis is recomputed only when the event
  actually changes. Reads legality (`bop_enabled`, `tuning_allowed`,
  `allowed_tuning_categories`) from EventContext.

Both are documented in `docs/PRODUCT_CONSOLIDATION_AUDIT.md §7`. EventContext is
their prerequisite and is now available.
