# Home Dashboard Build — Race Engineer Command Centre

> Author: Home Dashboard Build sprint · Date: 2026-07-03
> Branch: `home-dashboard-command-centre` (from `ai-snapshot-migration-context-freeze` @ `f8e9a9d`)
>
> Companion docs: `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§1.1 — the missing home
> surface), `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/STRATEGY_CONTEXT_MIGRATION.md`,
> `docs/SETUP_CONTEXT_MIGRATION.md`, `docs/TRACK_CONTEXT_MIGRATION.md`,
> `docs/AI_SNAPSHOT_MIGRATION.md` (§9 — this sprint's mandate).

---

## 1. Purpose

`REQUIREMENTS.md §12.2` specified a Dashboard/home tab showing the active
event, car, setup, strategy and a **suggested next action**. The Product
Consolidation Audit (§1.1) found it was never built — the app opens on the
Live tab with no overview of "where am I in the workflow / what should I do
next". The five consolidation sprints since then built everything the surface
needs: four canonical read models (EventContext, StrategyContext,
SetupContext, TrackContext), the frozen AI-input snapshot layer, and
`ui/product_flow.py`'s `build_flow_state_summary()` next-action resolver.

This sprint renders that surface: a **Home** tab (the Race Engineer Command
Centre) that answers, in plain English:

* What event is active, and is its configuration valid?
* What car / track / layout is selected?
* Is a strategy plan available, and is it still fresh for this event?
* Is a setup recommendation available, and is it still fresh for this event
  and strategy?
* What track model data exists, and can live corner mapping run?
* Would AI calls use clean frozen context snapshots right now?
* What is stale or missing?
* What is the single best next action?

**Display-only.** The Home Dashboard owns no state and mutates nothing — no
`config["strategy"]` writes, no setup/strategy stores, no track model files,
no event records, no AI logs, no telemetry/session data. No race, setup,
strategy, track-mapping, calibration, AI-prompt, PTT or voice logic changed.

## 2. What was built

### `ui/home_dashboard_vm.py` (NEW, pure Python)

No PyQt6, no AI, no DB, no network, no file I/O (source-scanned by test).
Converts duck-typed context objects into display-ready structures:

| Structure | Role |
|---|---|
| `HomeDashboardState` | The full dashboard: five cards + next action + all warnings |
| `HomeDashboardCard` | One section: key, title, status, headline, lines, warnings |
| `HomeDashboardStatus` | Traffic light: `READY` / `ATTENTION` / `MISSING` / `BLOCKED` |
| `HomeDashboardWarning` | Plain-English warning with a kind (`warning`/`stale`/`blocker`) |
| `HomeDashboardNextAction` | The suggested next step + tab + journey progress counts |
| `HomeDashboardAction` | A recommended action (action + tab) |

Entry points:

* `build_home_dashboard_state(...)` — **never raises**; every section builder
  is defensive, and malformed inputs degrade to a "Status unavailable" card.
* `build_flow_flags(...)` — derives the `build_flow_state_summary()` booleans
  from the contexts (event/car/track/tuning/setup/strategy) plus
  caller-supplied telemetry flags.
* `format_card_html(card)` / `format_next_action_html(next_action)` — pure
  HTML-string renderers (with escaping) consumed by the Qt labels, testable
  without Qt.

### Dashboard sections (cards)

| Card | Context source | Shows |
|---|---|---|
| **A. Race Setup** | EventContext (+ `validate_event_context`) | event name, car, track (+ layout name from TrackContext), race format, wear/fuel multipliers, BoP/tuning legality, refuel speed, mandatory stops, tyre lists, event validation warnings |
| **B. Track Intelligence** | TrackContext | track/layout identity, model maturity, seed metadata/geometry, reference path, corner position map (station map), reviewed/accepted model, live-mapping readiness + blockers, track-vs-event mismatch |
| **C. Setup Brain** | SetupContext (the `_last_setup_context` captured by State Consolidation 3) | label, purpose, source in plain English, car/track, adjustment count, primary issue, confidence, applied state, matches-current-event line, stale-vs-event and stale-vs-strategy warnings, validation warnings |
| **D. Strategy Brain** | StrategyContext | stints/stops, compound sequence, pit laps, fuel burn per lap, starting fuel, pit time, plan match key, stale-vs-event warning, uncalibrated-fuel warning |
| **E. AI Input Safety** | AI snapshot core (`AIContextSnapshot`) | whether AI prompts would use frozen context snapshots (`CONTEXTS`), legacy fallback (`LEGACY_ONLY`) or nothing (`EMPTY`), plus the snapshot's cross-context stale warnings |
| **F. Next Best Action** | `ui.product_flow.build_flow_state_summary()` | the single first-unmet-gate action, the tab to do it on, and "N of 8 steps done" progress |

Stale indicators use the exact plain-English forms the sprint brief asked for,
e.g. *"Setup was generated for an older event version."*, *"Strategy plan was
built before the current event settings changed."*, *"AI used legacy fallback
inputs for this path."*, *"Track or layout identity is missing."* Nothing is
reported as ready unless the corresponding context flag says so — availability
flags echo the existing audits and never claim accuracy.

### `ui/dashboard.py` — Home tab (additive)

* The **Home tab was APPENDED at index 13** (after Track Modelling) in this
  sprint. Tab indices 0–12 were hard-coded in `_on_tab_changed`, so appending
  was the only zero-risk placement — **no tab was reordered, renamed or
  removed**. *(Superseded: the **Home Dashboard Promotion** sprint (2026-07-03)
  later moved Home to index 0 as the default landing tab, once the Tab
  Navigation Refactor removed the index coupling — see
  `docs/HOME_DASHBOARD_PROMOTION.md`.)*
* `_build_home_tab()` — header + Refresh button, next-action banner label,
  and a 2-column grid of five rich-text card labels in a scroll area, using
  the existing dark-card style.
* `_build_home_dashboard_state()` — assembles the VM inputs from the existing
  context builders: `_build_event_context()`, `_build_strategy_context()`,
  `_build_track_context()` (TrackModellingMixin), the captured
  `_last_setup_context`, and `_build_strategy_ai_snapshot()` (a **pure
  computation** of what the AI inputs would be right now — no AI call).
* `_home_has_practice_laps(event_ctx)` — read-only DB query: do saved
  sessions with laps exist for the active car/track? Defensive, returns
  False on any failure.
* `_home_refresh()` — rebuild + render; never raises.
* `_home_refresh_if_visible()` — the cheap hook workflow actions call; no-op
  unless the Home tab is the current tab.
* `ui/product_flow.py` — "Home" registered as a `ROLE_WORKFLOW` tab (so the
  ⚙ diagnostic marker logic never decorates it). The diagnostic tab set is
  unchanged.

### Refresh triggers (no polling, no new workers, no new signals)

| Trigger | Where |
|---|---|
| Home tab shown | `_on_tab_changed` → `_home_refresh()` (same pattern as every other tab) |
| Manual | "Refresh" button on the Home tab |
| Active event changed | end of `_on_event_set_active` → `_home_refresh_if_visible()` |
| Strategy inputs recomputed | end of `_update_race_config` → `_home_refresh_if_visible()` |
| Setup result displayed | end of `_display_setup_result` (setup_builder_ui) — `hasattr`-guarded |
| Track truth panel refreshed | end of `_tm_refresh_track_truth_panel` (track_modelling_ui) — `hasattr`-guarded |

The `_if_visible` guard means background workflow actions never pay the
refresh cost (the track card re-runs the same file audits Track Modelling
runs on layout change) unless the user is actually looking at Home.

## 3. What is display-only / not owned

The Home Dashboard **reads** and never writes. Source-scan tests prove the
five `_home_*` / `_build_home_*` methods contain no `config["strategy"]`
writes, no `setdefault("strategy")`, no `_persist_config`, no DB
upserts/saves, no QTimer/QThread/worker creation. The VM module has no
Qt/DB/network/AI imports and no file I/O.

Approximations (documented, honest):

* `has_valid_laps` is currently supplied as `has_practice_laps` (recorded
  laps are treated as reviewable laps). Proper lap-validity truth belongs to
  a future SessionContext/TelemetryContext.
* `live_active` = telemetry tracker connected. "Racing right now" truth also
  belongs to a future SessionContext.
* The Setup Brain card shows the **last displayed** setup recommendation
  (`_last_setup_context`); a setup applied in an earlier app run is not
  reconstructed from the DB (deferred — see §5).

## 4. Tests

`tests/test_home_dashboard_vm.py` (NEW, 52 tests), following the no-Qt
convention (pure VM tests drive it with REAL contexts built by the
`data/*_context` builders; UI wiring is source-scanned):

* empty state; event-only; incomplete event warnings
* fresh strategy; stale strategy vs event; plan-less strategy; uncalibrated fuel
* fresh setup (matches current event); stale setup vs event; stale setup vs
  strategy snapshot; missing setup identity
* full track data ready; missing track identity; seed metadata present but
  geometry missing; station map unavailable → live mapping blocked;
  track-vs-event mismatch
* AI snapshot clean / legacy fallback / stale state surfaced / bare-core
  accepted / missing
* next-best-action ordering across the whole journey (event → practice →
  setup → strategy → race → complete), progress partition, strategy gate
  requires a plan not just a config
* display labels contain no developer jargon (`config_id`, `change_hash`,
  `snapshot_id`, `resolver`, enum values, context class names… forbidden)
* builder never raises on garbage in every slot, mixed garbage, and
  attribute-raising objects; formatters escape HTML
* source-scans: Home appended after tab 12, original addTab lines unchanged,
  diagnostic tabs still present, `_on_tab_changed` dispatches unchanged +
  Home added, Home reads from canonical contexts, Home methods write nothing,
  refresh hooks guarded, no polling/workers, VM module purity

Full suite after this sprint: see `MASTER_TESTING_REGISTER.md` (Home
Dashboard Build).

## 5. Intentionally deferred

* **Setup Brain persistence across restarts** — reconstructing the last
  setup recommendation from the DB (`setups` / `setup_recommendations`)
  so the card survives an app restart. Needs a "which setup is active"
  concept the stores don't record yet.
* ~~**Click-to-navigate** — making the next-action banner/tab names clickable
  (jump to the named tab). Low risk but touches tab-index coupling; do it
  together with the index-by-lookup refactor the audit recommends.~~
  **DONE (2026-07-03, Home Dashboard Promotion)** — each card and the
  next-action banner now carry an "Open <Tab>" button that navigates via
  `select_tab` using stable keys (`CARD_TAB_KEYS` / `key_for_title`). See
  `docs/HOME_DASHBOARD_PROMOTION.md`.
* **Per-panel stale badges** on the Strategy/Setup tabs themselves (the AI
  snapshot migration doc's §8 note) — Home surfaces them centrally first.
* **Telemetry-derived flags** (`has_valid_laps`, `live_active`) owned by a
  proper SessionContext/TelemetryContext instead of the current
  approximations.
* **AI-call capture** — showing "the LAST AI call used snapshot X" requires
  capturing the snapshot at call time in the AI paths; Home currently shows
  what a call made *now* would use, which never touches the migrated
  AI methods.

## 6. Remaining UI cleanup risks

* ~~Tab indices remain hard-coded in `_on_tab_changed` (now including the
  appended Home via `self._home_tab_index`).~~ **RESOLVED (2026-07-03, Tab
  Navigation Refactor)** — dispatch and navigation now go through the named
  tab registry (`ui/tab_registry.py`); `_home_tab_index` was retired in
  favour of `TAB_HOME`. See `docs/TAB_NAVIGATION_REFACTOR.md`.
* ~~The Home tab sits at the END of the tab bar; with the registry in place, a
  future sprint can move it to position 0 (where a home tab belongs) in one
  reviewed change.~~ **RESOLVED (2026-07-03, Home Dashboard Promotion)** — Home
  is now the first tab (index 0) and the default landing page. See
  `docs/HOME_DASHBOARD_PROMOTION.md`.
* The 7 hidden legacy per-segment buttons (`track_modelling_ui.py`) and the
  Strategy Builder duplicate API-key field are still present (audit §9).
* `_build_track_context()` re-runs seed/file audits (small file I/O) per
  refresh; acceptable for a tab-shown refresh, but a cached TrackContext
  (invalidated by its `change_hash`) would be cleaner.

## 7. Next sprint recommendation

> **Executed (2026-07-03):** the Diagnostic Tab Cleanup sprint ran next — see
> `docs/DIAGNOSTIC_TAB_CLEANUP.md`. The Guide now also explains the ⚙ tool
> tabs and its Step 8 describes this Home tab (replacing a stale description
> of a "Dashboard" tab that never existed). The recommendation after it is
> **Tab Navigation Refactor — Named Tab Lookup**, then moving Home to index 0.

**Diagnostic Tab Cleanup** (audit §9 items 1–4): delete the 7 hidden legacy
per-segment buttons + their `getattr` handlers, make Strategy Builder's API
key defer to Settings, hide/rename the "Race Config ID" hash, move the
Guide's telemetry byte-format reference to Diagnostics, and the
Diagnostics-tab wording pass. All display-only, all enumerated, and none of
it blocks the alternative — **Legacy Fan-Out Removal Phase 1** (start
retiring the `_on_event_set_active` → `config["strategy"]` fan-out behind
the now-complete context layer), which is the higher-value but higher-risk
follow-up.
