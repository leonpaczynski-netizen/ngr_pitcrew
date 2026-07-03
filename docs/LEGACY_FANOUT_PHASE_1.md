# Legacy Fan-Out Removal Phase 1 — Read-Only Consumer Migration

> Author: Legacy Fan-Out Removal Phase 1 sprint · Date: 2026-07-03
> Branch: `legacy-fanout-removal-phase-1` (from `config-safety-guardrails` @ `d206be2`)
>
> Companion docs: `docs/EVENT_CONTEXT_MIGRATION.md`,
> `docs/STRATEGY_CONTEXT_MIGRATION.md`, `docs/SETUP_CONTEXT_MIGRATION.md`,
> `docs/TRACK_CONTEXT_MIGRATION.md`, `docs/AI_SNAPSHOT_MIGRATION.md`,
> `docs/PRODUCT_CONSOLIDATION_AUDIT.md`.

---

## 1. Goal and scope

Reduce dependence on the legacy `config["strategy"]` fan-out cache by migrating a
focused set of **low-risk, read-only** consumers to the canonical read models
(`EventContext`, `StrategyContext`, `TrackContext`, `SetupContext`,
`AIContextSnapshot`). Each migration is **byte-identical** to the expression it
replaces and is backed by a test.

**This sprint does NOT** remove `config["strategy"]`, remove either fan-out
writer, or change any product behaviour. The two fan-out writers stay
(compatibility) and are pinned by tests:

* **Event Planner "Set as Active"** — `_on_event_set_active` fans event/race
  fields into `config["strategy"]`.
* **Track Modelling combo** — writes `track_location_id` / `layout_id` into
  `config["strategy"]`.

## 2. Why some reads are safe to migrate and others are not

The canonical builders resolve fields with a **specific precedence** that is only
byte-identical to a raw `config["strategy"]` read for *some* fields:

| Field | Resolution in the context | Byte-identical to raw `config["strategy"]` read? |
|---|---|---|
| `config_id` | `StrategyContext` = `str(strategy["config_id"])` | **Yes** — strategy-owned, always a string/absent |
| `car` | `EventContext` = `str(strategy["car"])` first, DB event fallback (events never store a car) | **Yes** in practice |
| `track_location_id` / `layout_id` | `EventContext` = strategy-first | Yes, but the Track Modelling combo *writes* these — leave with the writer this sprint |
| `track` (display name) | `EventContext` = **DB-event-first**, strategy fallback | **No** — differs when a DB edit post-dates "Set as Active" (that's the point of EventContext, but it changes displayed text) |
| `tyre_wear_multiplier`, `fuel_mult`, `tuning`, `bop`, race length | `EventContext` = **DB-event-first** | **No** — same precedence caveat |
| `fuel_burn_per_lap` | telemetry-derived (`_computed_fuel_burn_lpl`) | **No** — owned by the telemetry layer, deferred by AI Snapshot Migration |

So this phase migrates **`config_id`** (StrategyContext) and **`car`**
(EventContext) read-only consumers only. Event-rule reads that would flip
strategy-first → DB-first precedence are **deferred** to a later phase that can
prove/accept that change.

## 3. Classification of remaining `config["strategy"]` accesses

Categories: **EVENT_CONFIG** (→ EventContext), **STRATEGY_PLAN** (→
StrategyContext), **TRACK_IDENTITY** (→ TrackContext), **SETUP_STATE** (→
SetupContext), **AI_INPUT** (→ AIContextSnapshot), **LEGACY_REQUIRED** (the
canonical builders legitimately read the legacy dict as their *input source*, or
the value feeds a hash/algorithm that must stay byte-stable), **WRITER** (out of
scope).

### 3a. Migrated this sprint

| Site | Field | Class | Action |
|---|---|---|---|
| `dashboard._active_config_id()` (NEW helper) | `config_id` | STRATEGY_PLAN | reads `StrategyContext.config_id` |
| `setup_builder._refresh_setup_history_combo` | `config_id` | STRATEGY_PLAN | read-only history lookup → `_active_config_id()` |
| `setup_builder._on_setup_history_selected` | `config_id` | STRATEGY_PLAN | read-only history lookup → `_active_config_id()` |
| `setup_builder._display_setup_result` (history key) | `config_id` | STRATEGY_PLAN | history-save key → `_active_config_id()` |
| `setup_builder._run_build_setup` (history key) | `config_id` | STRATEGY_PLAN | history-save key → `_active_config_id()` |
| `dashboard._sync_practice_from_event` | `car` | EVENT_CONFIG | practice-bank combo sync → `EventContext.car` |

(`dashboard._refresh_lap_bank` already read `config_id` from `StrategyContext` —
established precedent from State Consolidation 2.)

### 3b. Deferred — WRITER (out of scope)

| Site | Reason |
|---|---|
| `dashboard._on_event_set_active` (`strat["track"]`, `["bop"]`, `["tuning"]`, `["event_id"]`, …) | the Set-as-Active fan-out writer — must remain |
| `dashboard._update_race_config` / `_save_race_params` (`config_id`, `race_configs` snapshot, tolerances) | writers/restore path |
| `dashboard._restore_*` (`["track"]`, `["car"]`, `["total_laps"]`) | race-config restore writers |
| `track_modelling_ui` (`["track_location_id"]`, `["layout_id"]`) | the Track Modelling combo writer — must remain |

### 3c. Deferred — LEGACY_REQUIRED (compatibility bridge / byte-stable algorithm)

| Site | Reason |
|---|---|
| `dashboard._build_event_context` / `_build_strategy_context` / `_build_track_context` (`strategy=self._config.get("strategy", {})`) | the canonical builders **read** the legacy dict as their input source — this is the bridge, not a leak |
| `dashboard._build_strategy_ai_snapshot` / `_build_practice_ai_snapshot` and `setup_builder._build_setup_ai_snapshot` (`legacy_strategy=…`) | AI snapshots already consume the legacy dict as a documented fallback (`docs/AI_SNAPSHOT_MIGRATION.md`) |
| `dashboard._compute_race_config_id` (`track`/`car`/`race_type`/length) | feeds the `config_id` **hash** — changing the source risks changing the hash; must stay byte-identical |
| `dashboard._computed_fuel_burn_lpl` (`fuel_burn_per_lap`) | telemetry-owned; deferred by AI Snapshot Migration — **migrated in the SessionContext sprint (2026-07-03): now reads `SessionContext.fuel_burn_per_lap`, config fuel read moved into the context builder. See `docs/SESSION_CONTEXT_MIGRATION.md`.** |

### 3d. Deferred — EVENT_CONFIG / STRATEGY_PLAN with a precedence caveat (future phase)

These are legitimate context candidates but reading them from the DB-first
`EventContext` would (correctly) change displayed/validated values when a DB
event edit post-dates "Set as Active" — **not** byte-identical, so they need a
phase that accepts/proves that change:

| Site | Field(s) |
|---|---|
| `dashboard._sync_strategy_from_event` (strategy status label) | `track`, `car`, race length, `tyre_wear_multiplier`, `fuel_mult`, `refuel_speed_lps` |
| `setup_builder._sync_setup_builder_from_event` (setup status labels) | race-rule fields |
| `dashboard` AI-setup-response validation (`tuning`, `allowed_tuning_categories`) | tuning legality |
| `dashboard` BoP / degradation reads (`bop`, `tyre_wear_multiplier`, `degradation_consecutive_laps`) | feed algorithms — need behaviour proof |
| assorted `car` / `track` reads that feed DB lookups (`get_car_id`, session open) | mixed; migrate car with a proof, track only after the precedence decision |

## 4. What changed

* **`ui/dashboard.py`** — new `_active_config_id()` accessor
  (`StrategyContext.config_id`); `_sync_practice_from_event` reads the car from
  `EventContext.car`.
* **`ui/setup_builder_ui.py`** — the four `config_id` reads now call
  `self._active_config_id()` (two read-only history lookups, two history-save
  keys). Zero raw `config_id` reads remain in the file.
* **Tests** — `tests/test_legacy_fanout_phase_1.py` (byte-identity + source-scans
  + writer preservation + no-new-fan-out + invariants).

## 5. What was intentionally NOT changed

* `config["strategy"]` still exists; both fan-out writers remain (pinned).
* No event-rule read was flipped to DB-first precedence (deferred, §3d).
* No AI-input read changed (they already use snapshots); no prompt wording,
  setup logic, strategy calculation, track mapping, telemetry, PTT, voice, tab
  order, or Home Dashboard behaviour changed.
* Config-safety guardrails unchanged; all new tests are pure-Python and touch no
  real config.

## 6. Risks

* `_active_config_id()` builds a `StrategyContext` (which builds an
  `EventContext`) per call — heavier than a dict read, but these are UI event
  handlers, not hot loops, and the value is byte-identical.
* The §3d reads remain the bulk of the fan-out dependence; Phase 2 must decide
  whether display/validation should adopt EventContext's DB-first truth (a
  deliberate, tested behaviour change) or keep strategy-first.
  **Update (2026-07-03, Phase 2):** the §3d *display labels*
  (`_sync_strategy_from_event`, `_sync_setup_builder_from_event`) were migrated
  to DB-first EventContext (byte-identical in sync). See
  `docs/LEGACY_FANOUT_PHASE_2.md`.
  **Update (2026-07-03, Phase 3):** with product sign-off, the *functional*
  gating (setup permissions/BoP) and the DEF-P3-012 tuning validation were also
  migrated to DB-first EventContext — reader consistency complete. Remaining on
  the fan-out: the writers, minor label fallbacks (refuel/req/avail), the car
  rebind, `_get_mandatory_compounds`, and the context-builders' bridge inputs.
  See `docs/LEGACY_FANOUT_PHASE_3.md`.

## 7. Next sprint recommendation

Two viable tracks:

1. **SessionContext / TelemetryContext** — give the telemetry/session layer a
   canonical read model so `_computed_fuel_burn_lpl`, `has_valid_laps`,
   `live_active`, and live-session identity stop reading `config["strategy"]` /
   volatile attributes. Unblocks Home Dashboard's two documented approximations.
2. **Legacy Fan-Out Removal Phase 2** — migrate the §3d event-rule display/
   validation consumers to EventContext, explicitly accepting and testing the
   DB-first precedence (the point of EventContext), then start retiring the
   Set-as-Active fan-out once every reader is migrated.

Recommended: **SessionContext / TelemetryContext** first (it is additive and
low-risk like the other context sprints), then Phase 2.
