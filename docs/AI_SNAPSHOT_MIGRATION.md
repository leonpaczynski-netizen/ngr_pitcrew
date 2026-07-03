# AI Snapshot Migration — frozen context inputs register

> **Legacy Fan-Out Removal Phase 1 update (2026-07-03):** no AI-input read was
> changed. The `legacy_strategy=self._config.get("strategy", {})` arguments to
> `_build_strategy_ai_snapshot` / `_build_practice_ai_snapshot` /
> `_build_setup_ai_snapshot` are the snapshots' documented legacy input source
> (LEGACY_REQUIRED), not consumer leaks, so they stay. See
> `docs/LEGACY_FANOUT_PHASE_1.md` §3c.

> Sprint: **AI Snapshot Migration — Frozen Context Inputs** · 2026-07-03
> Branch: `ai-snapshot-migration-context-freeze`
> Companion: `data/ai_context_snapshot.py`, `tests/test_ai_context_snapshot.py`,
> the four context migration registers (`docs/EVENT_CONTEXT_MIGRATION.md`,
> `docs/STRATEGY_CONTEXT_MIGRATION.md`, `docs/SETUP_CONTEXT_MIGRATION.md`,
> `docs/TRACK_CONTEXT_MIGRATION.md`)
> Status: AI-input assembly paths migrated to frozen snapshots. **No prompt
> wording changed, no intelligence changed, no legacy store removed.**

---

## 1. Purpose

Every AI-input path assembled its inputs **live** from `config["strategy"]` at
call time (SSOT-7 / SSOT-12 in the audit): a prompt could mix a stale strategy
snapshot with fresh UI state, or read event fields that no longer match the
edited DB event, and worker threads re-read config mid-flight. This sprint
threads **frozen, owner-documented snapshots** of the four canonical read
models into the AI-input preparation paths, byte-identical to the legacy
expressions wherever the stores are in sync.

## 2. Every AI prompt/input path found

| # | Path | Entry point | Inputs (pre-sprint source) | Status |
|---|------|-------------|----------------------------|--------|
| 1 | Race strategy analysis | `dashboard._run_ai_analysis` → `run_strategy_analysis` → `_build_race_prompt` | race_params from `_sc.get(...)` inline; fuel burn from `_computed_fuel_burn_lpl()`; config_id from config | **MIGRATED** — `_build_strategy_ai_snapshot(fuel_burn_override=…)`; `config_id` from the snapshot (StrategyContext) |
| 2 | Strategy input assembly (pre-race + mid-race re-plan) | `dashboard._assemble_strategy_inputs` (used by `_launch_replan_worker`) | race_params from `_sc.get(...)` inline; fuel burn raw config read | **MIGRATED** — `_build_strategy_ai_snapshot()` (fuel burn via StrategyContext w/ legacy 2.0 default) |
| 3 | Practice analysis | `dashboard._run_practice_analysis` → `analyse_practice_session` → `_build_practice_prompt` | race_params from `_psc.get(...)` incl. DEF-P1-005 tuning default; fuel burn telemetry | **MIGRATED** — `_build_practice_ai_snapshot(fuel_burn_override=…)`; DEF-P1-005 semantics preserved in the builder |
| 4 | Build Setup with AI | `setup_builder._run_build_setup` → `ai_planner.build_car_setup` → `_build_setup_from_scratch_prompt` | 16 event/track fields from `config["strategy"]` inline; rec-metadata re-read config **inside the worker thread** | **MIGRATED** — `_build_setup_ai_snapshot()`; worker uses the frozen `track`/`layout_id` (mid-flight re-read removed) |
| 5 | Analyse Setup / combined setup | `setup_builder._setup_analyse_ai` → `driving_advisor.build_combined_setup_response` | allowed/locked/mandatory-compounds from `_sc.get(...)` | **MIGRATED** — `_build_setup_ai_snapshot()` |
| 6 | Setup-advice internals | `driving_advisor._build_setup_prompt` / `_build_combined_prompt` / `_race_engineer_directives` | current setup dict + diagnosis + history (params passed in) | **DEFERRED** — receives already-migrated args from #5; internal prompt builders untouched by design |
| 7 | Mid-race re-plan race situation | `dashboard._launch_replan_worker` race_situation block | `_sc.get("total_laps")` + engine/tracker live state | **DEFERRED** — live-race telemetry state; only its `_assemble_strategy_inputs` call is migrated (#2) |
| 8 | PTT coaching prompts | `driving_advisor` coaching paths | live telemetry + own `_event_ctx` | **OUT OF SCOPE** (no PTT/voice change allowed) |
| 9 | Degradation analysis | `dashboard` degradation worker | `tyre_wear_multiplier` + `degradation_consecutive_laps` from config | **DEFERRED** — documented in STRATEGY/EVENT registers |
| 10 | Track context prompt injection | `strategy/track_context_prompt.get_track_context_for_ai(params.track_location_id, params.layout_id)` | ids from RaceParams | **MIGRATED INDIRECTLY** — the ids inside RaceParams now come from TrackContext identity via the snapshot |
| 11 | AI log / recommendation metadata | `_parse_recs(..., track, layout_id)` in `_run_build_setup` worker | re-read `config["strategy"]` mid-flight | **MIGRATED** — frozen snapshot values captured before the thread starts |

## 3. The snapshot layer (`data/ai_context_snapshot.py`)

* **`AIContextSnapshot`** (frozen core) — `snapshot_id` (stable hash over the
  payload + component markers), the four component keys (`event_change_hash`,
  `strategy_change_hash`, `setup_snapshot_id`, `track_change_hash`), `source`
  (CONTEXTS / LEGACY_ONLY / EMPTY), build `warnings` and `stale_warnings`.
* **`StrategyAISnapshot`** / **`PracticeAnalysisSnapshot`** — frozen
  `race_params` (feeds `RaceParams(**…)`) + `config_id` (strategy). Two types
  because the legacy paths differ in exactly one semantic: the practice path's
  DEF-P1-005 safe default (unknown tuning flag → **locked**) vs the strategy
  paths' unlocked default — both preserved exactly.
* **`SetupAISnapshot`** — the 17 event/track fields the setup AI paths need,
  with the build-setup legacy defaults (refuel/pit-loss **0.0**, unlike the
  strategy paths' 10.0/23.0) preserved exactly.
* **`validate_ai_context_snapshot()`** — ok only when built from contexts with
  no staleness.
* Staleness detected at build time: strategy plan built against an older
  event (`StrategyContext.event_change_hash` vs current), setup generated for
  a previous event (`SetupPromptSnapshot.event_change_hash`), Track Modelling
  selection not matching the active event (`TrackContext.mismatches_event`).
* Builders never raise; `LEGACY_ONLY` fallback evaluates the **exact legacy
  expressions** and records a warning — never a silent fallback when a clean
  context exists.

### Ownership per input (documented in the module)
| Input | Owner |
|-------|-------|
| track, laps, duration, race type, tyre-wear/fuel multipliers, refuel rate, BoP/tuning legality, avail/required tyres, mandatory compounds | **EventContext** |
| fuel_burn_per_lap (when not telemetry-overridden), pit_loss_secs, config_id | **StrategyContext** |
| track_location_id / layout_id | **TrackContext** (its own combos→event→legacy resolution) |
| setup snapshot identity | **SetupContext** (`SetupPromptSnapshot`) |
| telemetry fuel burn (`_computed_fuel_burn_lpl()`) | caller-supplied `fuel_burn_override` — **telemetry-owned**, deferred to a TelemetryContext sprint |

## 4. Byte-identical prompt proof

`tests/test_ai_context_snapshot.py` captures the legacy expressions **verbatim**
(as they existed pre-migration) and proves:

* race_params dicts identical for: full synced state, fuel-burn override,
  lap race, BoP+locked, no-DB-event (legacy-strategy-only context), absent
  optional keys (defaults 25 / 10.0 / 23.0 / 2.0 preserved), present-zero
  values (0 stays 0 — never replaced by defaults), practice tuning-absent →
  locked, strategy tuning-absent → unlocked, setup-path defaults (0.0/0.0,
  "Unknown" car, empty compounds string).
* **`test_prompt_text_byte_identical`** — the actual `_build_race_prompt`
  output is byte-identical for legacy-built vs snapshot-built `RaceParams`.
* legacy-only fallback equals the legacy expressions exactly.

## 5. Intentional differences (each with a focused test)

1. **Fresh DB event supersedes a stale config copy.** When the durable DB
   event record was edited after "Set as Active", EventContext returns the
   fresh values where legacy read the stale fan-out copies
   (`test_edited_db_event_supersedes_stale_config`). This is the purpose of
   the migration — safer normalisation, not a prompt redesign.
2. **Practice tuning flag: DB truth over blind default.** When the config
   `tuning` key is missing but a DB event exists, legacy defaulted to LOCKED;
   the snapshot uses the DB truth
   (`test_practice_tuning_absent_but_db_event_present_uses_db_truth`). The
   pure absent-everywhere case still defaults to LOCKED (DEF-P1-005 preserved).
3. **`GT7_AI_DEBUG` stdout line changed** (debug print only, never prompt
   text): now shows race_params-sourced values + `snapshot_id`/`source` +
   snapshot warnings. Stale indicators surface here — no UI/label change.
4. **`race_laps` in Build Setup is now always `int`** (legacy passed the raw
   config value uncast). Same value for every real config (spinbox ints).

## 6. Legacy tests updated (contracts moved, intent preserved)

20 pre-existing source-scan tests asserted the *inline expressions* that moved
into the snapshot layer. Each was updated to guard the **same invariant** at
its new home (behavioural check through the production builder + a
routes-through-snapshot scan): `test_group7` (BoP context), `test_group10`
(tuning_locked derivation), `test_group12a` (DEF-P1-005 default),
`test_group15` (DEF-P1-013/P2-038/P2-039 race-param fields), `test_group2`
(tyre-wear source), `test_group36` AC8 runtime stubs (now route through the
real snapshot builder; the session-id invariants still exercise the real
`_assemble_strategy_inputs`).

## 7. Remaining legacy AI-input dependencies (documented, deferred)

| Dependency | Where | Why deferred |
|------------|-------|--------------|
| `_computed_fuel_burn_lpl()` | dashboard (loaded session → tracker → config 2.0) | telemetry-owned — TelemetryContext sprint |
| `_launch_replan_worker` race_situation (`total_laps`, engine/tracker state) | dashboard | live-race telemetry state; algorithm untouched by scope |
| `_display_setup_result` DEF-P2-007 validation reads (`tuning`, categories) | setup_builder | display-side response validation, not prompt input |
| `_current_setup_dict()` car/track/weather reads | setup_builder | setup-dict construction (SetupContext baseline), not AI assembly |
| `driving_advisor._get_event_context_block` / `_event_ctx` | driving_advisor | prompt-internal; PTT-adjacent — out of scope |
| degradation worker (`tyre_wear_multiplier`, `degradation_consecutive_laps`) | dashboard | separate small path; migrate with EventContext low-risk batch |
| `_get_mandatory_compounds()` helper | dashboard | now unused by the migrated paths but still referenced elsewhere; retire later |
| AILogEntry car_id/track threading (Group 15A) | `_ai_client` callers | unchanged; build-setup rec metadata now frozen (the worst offender) |

`config["strategy"]`, legacy setup stores, track state, and AI log tables are
all **unchanged**.

## 8. Remaining stale-state risks

* Staleness is now **detected and reported** (snapshot `stale_warnings`,
  `GT7_AI_DEBUG` output) but not yet shown in UI labels — surfacing them on
  the Strategy/Setup panels is deliberately deferred to the Home Dashboard
  sprint (display-only work).
* The deferred paths in §7 can still read mixed state; each is small and
  enumerated.
* The Track Modelling combo → `config["strategy"]` id fan-out still exists
  (TrackContext register §6); the snapshot reads ids through TrackContext, so
  removing the fan-out later will not disturb the AI paths.

## 9. Recommended next sprint

**Home Dashboard Build** — render the missing home/overview panel from
`build_flow_state_summary(**{**event_flags, **track_flags, …})` and surface
the now-available staleness indicators (`AIContextSnapshot.stale_warnings`,
`_last_setup_context`, `_last_track_context`) as display-only status rows.
All four contexts + the snapshot layer now provide real, tested inputs; the
panel is a rendering job. Follow-up options afterwards: TelemetryContext (owns
fuel-burn/lap-stats reads), then removal of the `_on_event_set_active` and
combo fan-outs once every consumer reads a context.
