# SetupContext Migration — setup-recommendation state register

> Sprint: **State Consolidation 3 — SetupContext** · 2026-07-03
> Branch: `state-consolidation-3-setup-context`
> Companion: `data/setup_context.py`, `tests/test_setup_context.py`,
> `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/STRATEGY_CONTEXT_MIGRATION.md`,
> `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§5/§7)
> Status: SetupContext read model landed; legacy setup config/DB storage
> **retained** as compatibility. This document registers every setup-specific
> dependency and the migration plan.

---

## 1. Purpose

Setup state is scattered across four stores that mix different kinds of truth and,
critically, **none records which event and strategy assumptions a setup
recommendation was generated against**, so a setup can silently go stale when the
event or strategy changes underneath it. This sprint introduced `SetupContext`
(`data/setup_context.py`) as the canonical read model for setup-recommendation
truth, **keyed** to `EventContext.change_hash` and
`StrategyPromptSnapshot.snapshot_id`. **No behaviour changed**; the legacy stores
still exist and are still written. This register enumerates the dependencies so
later sprints can migrate them safely.

It follows `EventContext` (State Consolidation 1) and `StrategyContext`
(State Consolidation 2) and depends on both.

## 2. Ownership boundary

| SetupContext OWNS (setup-recommendation) | SetupContext must NOT own (read from elsewhere) |
|------------------------------------------|-------------------------------------------------|
| `setup_id`, `config_id`, `setup_label` | selected event, race type, race duration/lap count (EventContext) |
| `purpose` (qualifying/race/practice/test/unknown) | tyre/fuel multipliers, refuel rate (EventContext) |
| `source` (ai/generated/manual/saved_db/legacy_config) | BoP/tuning legality, allowed setup **categories** (EventContext) |
| `adjustments` (`SetupChangeEntry` tuple), `changed_fields` | active strategy plan, stint plan, fuel burn per lap (StrategyContext) |
| `baseline_setup`, `target_setup` (frozen copies) | raw telemetry packets, lap validity (Telemetry/Session context) |
| `reason_summary`, `primary_issue`, `confidence` | track/corner map geometry (a later TrackContext) |
| `validation_warnings`, `applied` | AI logs; driver learning history (a later LearningContext) |
| `change_hash` (setup change marker) | — |
| `event_change_hash`, `strategy_snapshot_id`, `telemetry_diagnosis_hash` (keys it was built against) | — |

> The setup's **car/track identity** (`car`, `track`, `track_location_id`,
> `layout_id`) IS carried by SetupContext because a setup is *for* a car+track —
> but it is read from the setup dict, falling back to EventContext, and is never
> treated as the owner of the event's selection.

## 3. Setup-specific stores discovered

### 3a. Config-based

| Store | Shape | Writer | Readers |
|-------|-------|--------|---------|
| `config["car_setup"]["setups"]` | list of setup dicts | `_setup_save` (setup_builder_ui.py:975), `_save_setup_from_lapdata` | `__init__` (dashboard.py:478-484 → `self._saved_setups`), Garage (dashboard.py:7339), `_resolve_setup_id_for_lap` (2460) |
| the current form setup | `_current_setup_dict()` (setup_builder_ui.py:720) — ~40 fields | the setup form widgets | `build_setup_advice_response`, `_setup_save`, `_display_setup_result` |

### 3b. DB-based (`data/session_db.py`)

| Table | Columns (setup-relevant) | Writers | Readers |
|-------|--------------------------|---------|---------|
| `setups` | id, car_id, event_id, name, setup_json, ai_notes, created_at, updated_at | `save_setup` (856), `update_setup` (939) | `get_setup` (885), `get_setups_for_car` (875), `get_all_setups_legacy` (905), `delete_setup` (900) |
| `setup_recommendations` | id, ai_interaction_id, session_id, car_id, track, layout_id, feature, recommendation_text, status, outcome, outcome_session_id, before_metrics, after_metrics, corner_issue_ids | `insert_setup_recommendations` (1014), `update_recommendation_outcome` (1061), `apply_recommendation_for_car_track` (1120) | `get_recommendations_for_context` (1028), `get_setup_history_for_car_track` (1164) |
| `setup_snapshots` (legacy) | session_id, car_id, track, setup_dict | `write_setup` (1439) | (legacy) |
| `lap_records.setup_id` | FK linking a lap to a setup | `update_lap_setup_id` (1471) | `_build_setup_comparison_text` |

### 3c. AI response payload (`strategy/driving_advisor.py`)

`build_setup_advice_response` (837) / `build_combined_setup_response` (1015) return a
JSON dict:

| Key | Meaning | SetupContext field |
|-----|---------|--------------------|
| `analysis` | free-text analysis | `reason_summary` |
| `changes` | `[{setting, field, from, to, why, to_clamped}]` | `adjustments` (`SetupChangeEntry`) |
| `setup_fields` | target setup `{field: value}` | `target_setup` |
| `validation_errors` | server-side validation strings | `validation_warnings` |
| `primary_issue` | dominant problem | `primary_issue` |
| `confidence` | AI confidence | `confidence` |
| `engineering_validation_failed` / `_errors` | engineering-rule failures | (folded into display; not owned) |

From-scratch build: `ai_planner.build_car_setup` → `CarSetupRecommendation`
dataclass (28 setup fields + reasoning + shift RPMs).

### 3d. Diagnosis + history

| Source | Shape | Note |
|--------|-------|------|
| `strategy/setup_diagnosis.build_setup_diagnosis` (475) | dict — `dominant_problem`, bands, `location_confidence`, `recommended_tuning_priority`, … | hashed into `telemetry_diagnosis_hash`; mined for optional `reason_summary`/`primary_issue`/`confidence` |
| `data/setup_history.save_entry` (43) | `{type: build_qual/build_race/analyse_setup/feeling_fix, changes, analysis, labels, …}` keyed by `config_id` | purpose maps: build_qual→QUALIFYING, build_race→RACE |
| `_build_setup_comparison_text` (dashboard.py:2540) | markdown, setup performance across compounds | DB-derived |

## 4. The read model (`data/setup_context.py`)

* **`SetupContext`** (frozen dataclass) — the fields in §2, plus convenience
  (`has_active_setup`, `is_ai_generated`, `baseline_setup_dict()`,
  `target_setup_dict()`, `summary_line()`, `to_summary_lines()`, `to_dict()`) and
  keying helpers (`matches_event`, `is_stale_for_event`, `is_stale_for_strategy`,
  `is_missing_identity`, `matches_purpose`).
* **`SetupChangeEntry`** (frozen) — one adjustment; `to_dict()` round-trips to the
  AI `changes` shape (`{field, from, to, why}`).
* **`SetupContextSource`** — EMPTY / AI / GENERATED / MANUAL / SAVED_DB / LEGACY_CONFIG.
* **`SetupPurpose`** — QUALIFYING / RACE / PRACTICE / TEST / UNKNOWN; `normalise_purpose()`
  maps the UI's "Qualifying Setup"/"Race Setup", history `build_qual`/`build_race`,
  or free text.
* **`SetupContextValidationResult`** — keeps `setup_warnings`/`setup_missing`
  **separate** from `staleness_warnings` (event/strategy drift, purpose mismatch).
  `.warnings` concatenates both.
* **`SetupPromptSnapshot`** + `build_setup_prompt_snapshot()` — an immutable,
  value-copied freeze of the setup recommendation with the event + strategy keys
  it was built against. Stays stable even if the source setup dict / config
  mutates later. `snapshot_id` = stable hash of the event + strategy + setup +
  diagnosis change markers. **Exists for a future AI-setup-prompt migration; the
  high-risk prompt paths are NOT migrated this sprint.**
* **`build_setup_context(setup, recommendation, event_context, strategy_snapshot,
  diagnosis, purpose, source, applied)`** — never raises; EMPTY on
  missing/garbage input. Event/strategy fields are read only as `change_hash` /
  `snapshot_id` keys, never copied as owned state.
* **`compute_change_hash()`** — stable 12-char setup change marker over the setup
  fields **only** (event/strategy tracked via their own hashes).

Purity: no PyQt6, no DB, no I/O, no network/AI.

## 5. What was migrated this sprint

- **`ui/setup_builder_ui.py` `_build_setup_context()` (NEW)** — builds the
  canonical `SetupContext` from `_current_setup_dict()` + `_build_event_context()`
  + a `StrategyPromptSnapshot` (from `_build_strategy_context()`). Defensive;
  never raises.
- **`_setup_type_prefix()`** — the Q/R setup-name prefix now derives the purpose
  via `normalise_purpose()` / `SetupPurpose.QUALIFYING` (setup purpose is
  SetupContext-owned) instead of an ad-hoc substring test. Behaviour-preserving.
- **`_display_setup_result()`** — after parsing the AI response it captures the
  canonical `SetupContext` into `self._last_setup_context` (keyed to the event +
  strategy it was built against). **Read-only and additive** — it does not alter
  the displayed HTML, the history save, or the apply button; it exists so a later
  sprint can surface a "setup is stale" indicator.

Everything else still reads the legacy stores (compatibility preserved).

## 6. Consumers intentionally deferred (and why)

| Consumer | Store | Why deferred |
|----------|-------|--------------|
| `build_setup_advice_response` / `build_combined_setup_response` prompt construction (driving_advisor.py:837/1015) | current setup + diagnosis + history | **Partially migrated (AI Snapshot Migration):** the *event-input assembly* feeding these calls (`_setup_analyse_ai` allowed/locked/compounds) now comes from a frozen `SetupAISnapshot`; the prompt builders' internals remain untouched by design. |
| `build_car_setup` from-scratch (ai_planner.py:544) | event + car | **Input assembly migrated (AI Snapshot Migration):** `_run_build_setup`'s 16 event/track reads now come from one frozen `SetupAISnapshot` (worker-thread rec metadata frozen too); the prompt builder itself is untouched. |
| `_apply_and_save_ai_setup` / `_apply_build_setup_result` | form + DB | Mutating apply paths — behaviour-critical; migrate after the read-only surface is proven. |
| `_resolve_setup_id_for_lap` (dashboard.py:2453) | `_saved_setups` | Behaviour-bearing lap tagging (matches by `captured_at`); not a clean single-context read. |
| `_setup_save` / DB `save_setup` writers | config + DB | Writers unchanged this sprint by design. |
| `get_setup_history_for_car_track`, `setup_history.format_for_prompt` | DB + json | Feed AI prompts; migrate with the prompt paths. |

## 7. Remaining legacy dependencies

Legacy setup storage is still the **writer-side** truth: `config["car_setup"]["setups"]`,
the `setups` / `setup_recommendations` / `setup_snapshots` DB tables, and
`setup_history.json`. This sprint changed **no writer**. SetupContext is a read
model layered on top — consumers migrate to it one at a time; the legacy stores
are retired only once every consumer reads a context (a later sprint).

## 8. Risks

- **Stale setup risk (the reason this exists).** A setup built for one event/strategy
  can be applied under a changed one. SetupContext now *detects* this
  (`is_stale_for_event` / `is_stale_for_strategy`) but nothing yet *surfaces* it
  to the user — that is the next visible payoff. `_last_setup_context` is captured
  but not yet displayed.
- **Prompt-snapshot risk.** `SetupPromptSnapshot` exists but the AI setup-prompt
  paths are **not** migrated. Doing so must freeze a consistent EventContext +
  StrategyPromptSnapshot + SetupContext and prove byte-identical prompts before/after.
- **Validation risk.** `validate_setup_context` reports staleness/identity/purpose
  warnings but is advisory — it does not block any existing flow, and the existing
  `_validate_setup_response` / `validate_setup_engineering` logic is untouched.
- **Identity fallback.** `car`/`track` fall back to EventContext when the setup
  dict omits them; a setup built with no event active will carry empty identity
  and warn, not crash.

## 9. Recommended next sprint

Either:

1. **TrackContext** — unify track/layout selection (SSOT-2: name vs seed IDs vs
   Track Modelling combos), owning reference path / station map / corner-segment
   model / seed geometry / track-truth; SetupContext and StrategyContext read
   corner context from it. **Or**
2. **Migrate the deferred AI-input consumers** to frozen snapshots — thread
   `EventContext` + `StrategyPromptSnapshot` + `SetupPromptSnapshot` into
   `build_setup_advice_response` / `build_combined_setup_response` /
   `_assemble_strategy_inputs` / `_run_ai_analysis`, proving prompts are unchanged,
   then surface the stale-setup indicator from `_last_setup_context`.

Recommended: **TrackContext first** (clean, additive, unblocks corner-aware setup
and strategy context), then the AI-input snapshot migration.

> **Update (State Consolidation 4):** TrackContext **landed** —
> `data/track_context.py` + `docs/TRACK_CONTEXT_MIGRATION.md`. Next sprint is
> the AI Snapshot Migration (or the Home Dashboard build) per that doc's §8.
