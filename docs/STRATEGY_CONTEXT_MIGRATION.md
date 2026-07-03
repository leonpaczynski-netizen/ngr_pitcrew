# StrategyContext Migration — strategy-plan state register

> Sprint: **State Consolidation 2 — StrategyContext** · 2026-07-03
> Companion: `data/strategy_context.py`, `tests/test_strategy_context.py`,
> `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§5/§7)
> Status: StrategyContext read model landed; `config["strategy"]` **retained** as
> legacy compatibility. This document lists every strategy-specific dependency
> and the migration plan.

---

## 1. Purpose

`config["strategy"]` is a "god dict" mixing two different kinds of truth:

* **event / race configuration** — now owned by `EventContext`
  (State Consolidation 1; see `docs/EVENT_CONTEXT_MIGRATION.md`).
* **strategy-plan state** — the selected/generated stint plan, planned stops,
  fuel burn per lap, the derived `config_id` match key, degradation assumptions
  and the analysis tolerances.

This sprint introduced `StrategyContext` (`data/strategy_context.py`) as the
canonical read model for the **second** kind. It **reads event/race rules from
an `EventContext`** rather than duplicating them, so the two can never drift.
**No behaviour changed**; `config["strategy"]` still exists and is still written.

## 2. Ownership boundary

| StrategyContext OWNS (strategy-plan) | StrategyContext must NOT own (read from EventContext) |
|--------------------------------------|-------------------------------------------------------|
| `config_id` (active strategy/config match key) | selected event, car, track/layout |
| `stint_plan` (typed `StintPlanEntry` tuple) | race type, race duration / lap count |
| `planned_stops`, `pit_laps` (derived from the plan) | tyre wear multiplier, fuel multiplier |
| `fuel_burn_per_lap` (telemetry-derived) | refuel **rate** (`refuel_rate_lps`) |
| `starting_fuel`, `fuel_margin`, `refuel_required` (optional) | BoP / tuning legality, allowed setup changes |
| `pit_loss_secs` | required / available tyres |
| `degradation_consecutive_laps`, `tyre_degradation_available` | telemetry packets, lap validity |
| `lap_time_tolerance_ms`, `fuel_tolerance_liters` | setup diagnosis, track-map geometry |
| `source`, `change_hash` (strategy change marker) | AI logs, driver learning history |
| `event_change_hash` (which event it was built against) | — |

> Note the **rate vs number** split: the *minimum required* stops
> (`mandatory_stops`) and the *refuel rate* (`refuel_rate_lps`) are **event
> rules** (EventContext). The *planned* number of stops and the pit laps are
> **strategy state**, derived from the stint plan (`planned_stops =
> max(0, len(stints) - 1)`; `pit_laps` = cumulative stint lengths excluding the
> last).

## 3. Strategy-specific fields in `config["strategy"]`

| Field | Meaning | Written by | Read by (current) | Owner |
|-------|---------|-----------|-------------------|-------|
| `stops` | saved stint plan (`[{laps, compound, ref_lap_ms, pace_threshold_ms}]`) | `_strategy_apply_plan` (dashboard.py:4633) | `__init__` restore (498); engine `Stint.from_dict` | **StrategyContext** |
| `config_id` | 10-char race-config match key (track+car+length) | `_update_race_config` (2635) | `_on_live_mode_changed` (981), `_save_session_to_db` (3019), `_refresh_lap_bank` (2740 — **migrated**), `_run_ai_analysis` (3454) | **StrategyContext** |
| `fuel_burn_per_lap` | telemetry-derived burn | `_save_race_params` (2606), `_strategy_apply_plan` (4635) | `_computed_fuel_burn_lpl` (2601), `_assemble_strategy_inputs` (3250), `_build_ai_analysis_group` (4193) | **StrategyContext** |
| `pit_loss_secs` | pit lane time loss (analysis input) | `_save_race_params` (2608) | `_assemble_strategy_inputs` (3252), `_run_ai_analysis` (3431) | **StrategyContext** |
| `lap_time_tolerance_ms` | strategy analysis tolerance | `_save_race_params` (2610) | strategy analysis | **StrategyContext** |
| `fuel_tolerance_liters` | strategy analysis tolerance | `_save_race_params` (2612) | strategy analysis | **StrategyContext** |
| `degradation_consecutive_laps` | tyre-degradation assumption | (config default) | degradation worker (5383) | **StrategyContext** |

Fields *not currently present* but modelled as optional so a future
AI-generated plan can populate them without a schema change: `starting_fuel`,
`fuel_margin`, `refuel_required`. The `tyre_degradation` cache
(`self._tyre_degradation_cache`) is passed to the builder opaquely — the context
records only `tyre_degradation_available`, never its internals.

## 4. The read model (`data/strategy_context.py`)

* **`StrategyContext`** (frozen dataclass) — the fields in §2, plus convenience
  (`has_active_strategy`, `total_planned_laps`, `has_fuel_burn`,
  `compound_sequence()`, `summary_line()`, `to_summary_lines()`, `to_dict()`).
* **`StintPlanEntry`** (frozen) — one stint; `to_dict()` round-trips back to the
  legacy stops shape so existing engine code (`Stint.from_dict`) still works.
* **`StrategyContextSource`** — `EMPTY` / `LEGACY_STRATEGY` / `GENERATED`.
* **`StrategyContextValidationResult`** — keeps `strategy_warnings` /
  `strategy_missing` **separate** from `event_warnings` / `event_missing`, so a
  caller can tell the user whether it is the *strategy* or the *event* that is
  under-specified. A `.warnings` property concatenates both for a single banner.
* **`StrategyPromptSnapshot`** + `build_strategy_prompt_snapshot()` — an
  immutable, **value-copied** freeze of a consistent EventContext (race config) +
  StrategyContext (plan). Stays stable even if `config["strategy"]` mutates
  afterwards. `snapshot_id` is a stable hash of `(event_change_hash,
  strategy_change_hash)`.
* **`build_strategy_context(strategy=…, event_context=…, tyre_degradation=…,
  source=…)`** — never raises; returns an `EMPTY` context on missing/garbage
  input. Event fields in the strategy dict are **ignored**.
* **`compute_change_hash()`** — stable 12-char strategy change marker over the
  strategy fields **only** (event fields excluded — those are tracked via
  `event_change_hash`).

Purity: no PyQt6, no DB, no I/O.

## 5. What was migrated this sprint

- **`ui/dashboard.py` `_build_strategy_context()` (NEW)** — builds the canonical
  `StrategyContext` from `config["strategy"]` + `_build_event_context()` +
  `self._tyre_degradation_cache`. Defensive; never raises.
- **`_refresh_lap_bank()`** — the practice-lap-bank ★ marker now reads the active
  `config_id` from `StrategyContext.config_id` instead of
  `config["strategy"]["config_id"]`. A pure read-only display consumer; no
  behaviour change (the ★ still marks sessions recorded under the current
  config).

Everything else still reads `config["strategy"]` (compatibility preserved).

## 6. Consumers intentionally deferred (and why)

| Consumer | Field(s) | Why deferred |
|----------|----------|--------------|
| `_assemble_strategy_inputs` (3213) | `fuel_burn_per_lap`, plan, tolerances **+ event fields** | **MIGRATED (AI Snapshot Migration)** — reads via `StrategyAISnapshot` (event from EventContext, fuel burn/pit loss/config_id from StrategyContext with legacy defaults preserved). See `docs/AI_SNAPSHOT_MIGRATION.md`. |
| `_run_ai_analysis` (3401) | `config_id`, `fuel_burn_per_lap`, plan | **MIGRATED (AI Snapshot Migration)** — same snapshot; fuel burn stays the telemetry-derived `_computed_fuel_burn_lpl()` override. |
| `_launch_replan_worker` (3317) | plan / `total_laps` | Still deferred: the race_situation block reads live engine/tracker state + `total_laps` from config; only its `_assemble_strategy_inputs` call is migrated. |
| `__init__` stint restore (498) | `stops` | A writer-adjacent restore into the stint table; low-risk but touches UI construction — defer to the batch that also migrates `_strategy_apply_plan`. |
| `_build_ai_analysis_group` label (4193) | `fuel_burn_per_lap` | UI-construction-time label; migrate with the other Strategy Builder display reads. |
| degradation worker (5383) | `degradation_consecutive_laps`, `tyre_wear_multiplier` | `tyre_wear_multiplier` is an **event** field — migrate this read to EventContext, and the consecutive-laps read to StrategyContext, in one pass. |

## 7. Remaining legacy dependencies

`config["strategy"]` is still the **writer-side** store for all strategy fields
(`_strategy_apply_plan`, `_save_race_params`, `_update_race_config`). This sprint
did **not** change any writer. StrategyContext is a **read model** layered on top
— consumers migrate to it one at a time; the dict is retired only once every
consumer reads a context (a later sprint, jointly with the EventContext
fan-out removal in `docs/EVENT_CONTEXT_MIGRATION.md §6`).

## 8. Risks

- **AI-input path is the payoff and the risk.** `_assemble_strategy_inputs` /
  `_run_ai_analysis` interleave event and strategy reads; they must migrate as a
  unit and freeze a `StrategyPromptSnapshot`, with a full strategy-prompt UAT.
- **`config_id` derivation unchanged.** StrategyContext *reads* `config_id`; it
  does not recompute it. `_compute_race_config_id` remains the single writer.
- **Optional fuel fields are forward-looking.** `starting_fuel` / `fuel_margin`
  / `refuel_required` are not yet written anywhere; they exist so a generated
  plan can populate them without a schema change. Validation treats them as
  optional (absent → `None`, no warning).

## 9. Recommended next sprint

**SetupContext — LANDED (State Consolidation 3, `data/setup_context.py`; see
`docs/SETUP_CONTEXT_MIGRATION.md`).** Keyed on `EventContext.change_hash` **and**
`StrategyPromptSnapshot.snapshot_id`; owns setup-recommendation state (purpose,
adjustments, baseline/target setup, confidence, validation); reads event/strategy
state only as those keys; detects stale setups via `is_stale_for_event` /
`is_stale_for_strategy`. `build_strategy_prompt_snapshot()` is consumed by
SetupContext's builder to key setups to the strategy assumptions.

Still **deferred**: migrate the deferred AI-input consumers (§6) to the frozen
`StrategyPromptSnapshot` (jointly with the SetupContext AI-prompt migration), and
finally remove the `config["strategy"]` fan-out (EventContext migration §6) once
every consumer reads a context. Next likely sprint: **TrackContext** (SSOT-2).
