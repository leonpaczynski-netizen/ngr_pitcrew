# TrackContext Migration — track/layout/map state register

> Sprint: **State Consolidation 4 — TrackContext** · 2026-07-03
> Branch: `state-consolidation-4-track-context`
> Companion: `data/track_context.py`, `tests/test_track_context.py`,
> `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/STRATEGY_CONTEXT_MIGRATION.md`,
> `docs/SETUP_CONTEXT_MIGRATION.md`, `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§5 SSOT-2/§7)
> Status: TrackContext read model landed; **all legacy track files, loaders,
> resolver logic, calibration code and UI widgets retained unchanged.** This
> document registers every track state store and the migration plan.

---

## 1. Purpose

Track identity and track-model state are the most scattered state in the app
(SSOT-2 in the audit): the display name, the canonical ids, the model artefacts
and the live in-memory state live in four different kinds of store with no
single answer to *"what track is selected, what model data exists for it, and is
any of it stale?"*. This sprint introduced `TrackContext`
(`data/track_context.py`) as the canonical read model for **identity +
availability + status**, keyed to `EventContext.change_hash`. **No behaviour
changed**; every legacy store is still written and read exactly as before.

**No geometry truth is invented.** Every availability flag echoes what the
existing audits/validators said; Daytona remains seed-geometry-blocked and is
represented as such (`seed_geometry_available=False`, truth gates echoed False).

## 2. Ownership boundary

| TrackContext OWNS | TrackContext must NOT own (owner) |
|-------------------|-----------------------------------|
| track_location_id / layout_id / display names / combined id / identity source | event/race rules, race type, duration/laps, multipliers, BoP/tuning legality (**EventContext**) |
| seed metadata / lap-length / corner-window / sector / complex / coordinate-geometry availability + seed source | strategy plan, stint plan, fuel burn (**StrategyContext**) |
| reference path / calibration laps / station map / reviewed model / accepted model / lap-offset availability | setup recommendation state (**SetupContext**) |
| modelling status, resolver outcome (resolution_status / source_type / ai_ready) | raw telemetry packets, lap validity (**future Telemetry/SessionContext**) |
| alignment status (match status, accepted, delta, blocker/warning counts) | AI logs (**DiagnosticsContext**), driver learning history (**future LearningContext**) |
| lap-offset status + confidence | — |
| track-truth gates **as echoed** from `TrackTruthValidationResult` (tri-state) | — |
| `change_hash` (identity + availability + status) and `event_change_hash` key | — |

## 3. SSOT audit — the 16 state items (sprint §7)

| # | State item | Current owner | Files / keys | Duplicated? | Future owner |
|---|-----------|---------------|--------------|-------------|--------------|
| 1 | Selected track (display name) | none clear | `_evt_track` combo (dashboard.py:6666), event dict `track`, `config["strategy"]["track"]` (written dashboard.py:7106) | **YES — 3 stores** (combo, event record, strategy dict) | **TrackContext** identity (name), EventContext keeps its own event.track field |
| 2 | Selected layout (canonical ids) | none clear | `config["strategy"]["track_location_id"]`/`["layout_id"]` — **written by the Track Modelling combos** (track_modelling_ui.py:928-929), read by AI paths (`_run_practice_analysis`, `_assemble_strategy_inputs`, `strategy/track_context_prompt.py`) | **YES** — volatile combo state + persisted config keys, no round-trip verification | **TrackContext** |
| 3 | Track Modelling tab selection | `_tm_location_combo`/`_tm_layout_combo` (track_modelling_ui.py:177/183) | set: 893/910/1068-1075 (restore); read: ~25 call sites via `currentData()` | **YES** — combos are simultaneously UI state *and* the writer of item 2 | **TrackContext** (combos become a writer *into* it) |
| 4 | Display track/layout names | seed YAML | `TrackLocationSeed.display_name` / `TrackLayoutSeed.display_name` via `build_location_display_items`/`build_layout_display_items` (vm:170/186) | No (single source, but only reachable via seed load) | **TrackContext** identity |
| 5 | Seed metadata | `data/track_intelligence.py` | `docs/track_modelling_seed/track_modelling_seed.yaml`, module `_CACHE` (line 248), `load_track_seed()` | No (cached single loader) | stays; TrackContext **represents availability** |
| 6 | Seed corner windows / sectors / complexes | `TrackLayoutSeed` fields (track_intelligence.py:204-206) | readers: track_truth.py:494-541, track_model_alignment.py, vm:274 | No | stays; TrackContext represents availability + counts |
| 7 | Seed coordinate map | `data/track_library.py resolve_seed_coordinate_map()` (364-390, library-first → legacy fallback) | `data/track_library/tracks/.../geometry.seed_map.json` OR `data/track_seed_maps/<loc>__<lay>.seed_map.json` | No (single resolve point; fallback is degradation, not duplication) | stays; TrackContext represents `seed_geometry_available` + `seed_source` |
| 8 | Reference path | `data/track_calibration.py` (filename 1041, export 962, import 1006) + `track_calibration_runtime.save_reference_path` | `data/track_models/<loc>__<lay>.reference_path.json` | No file duplication; discovery is repeated ad hoc | stays; TrackContext represents availability + point count |
| 9 | Station map | `data/track_station_map.py` (export 744, import 786, find 845) **+ volatile** `self._tm_station_map` (track_modelling_ui.py:850, read at ~12 sites) | `data/track_models/<loc>__<lay>.station_map.json` | **Partial** — file + volatile attribute, never synced to config | **TrackContext** availability; attribute stays the live cache |
| 10 | Reviewed segment model | `data/track_segment_review.py` (export 437, import 516) | `data/track_models/<loc>__<lay>.reviewed_model.json`, `modelling_status` persisted in JSON | No | stays; TrackContext represents availability + modelling status |
| 11 | Accepted track model | `data/track_model_alignment.py` (export 354, find 394, import 406) + resolver chain (`track_model_resolver.py:271` — engineer_validated > ai_ready > reviewed > seed) | `data/track_models/<loc>__<lay>.accepted_model.json` + volatile `_tm_alignment_result` | **Partial** — file + volatile attribute | **TrackContext** availability/alignment status |
| 12 | Lap offset calibration | `data/lap_distance_mapper.py` (load 429) + volatile `_tm_offset_calibration` (track_modelling_ui.py:848) | `data/track_models/<loc>__<lay>__lap_offset.json` | **Partial** — file + volatile attribute | **TrackContext** status/confidence |
| 13 | Alignment result | volatile `self._tm_alignment_result` (set track_modelling_ui.py:1789, loaded-from-disk 2214, cleared 2015) | in-memory + item-11 file | **Partial** (same object serves live + persisted roles) | **TrackContext** alignment status |
| 14 | Live map-matching identity | Track Modelling combos (via `_tm_update_live_map_dot`, track_modelling_ui.py:1169) | `resolve_live_segment(track_location_id, layout_id, …)`; no config fallback | No duplication, but identity comes from a *diagnostic tab's* volatile combos | **TrackContext** (deferred — behaviour-bearing) |
| 15 | Track Truth model | computed on demand (`track_truth.resolve_track_truth_model`, 457) from library manifest + semantic model | no state duplication | No | stays; TrackContext echoes the validation gates tri-state |
| 16 | Modelling status | hybrid: seed YAML default → reviewed JSON `modelling_status` → resolver `_classify_review` promotion (track_model_resolver.py:135) | `TrackModellingStatus` (track_intelligence.py:31, 9 values) | **Partial** — three writers at different maturities; resolver is the arbiter | stays (resolver arbitrates); **TrackContext represents** the resolved value |

### File formats involved
`track_modelling_seed.yaml` (seed), `track_library_index_v1` + per-layout
`manifest.json`/`semantic_model.json`/`validation_rules.json`/`source_manifest.json`/
`geometry.seed_map.json` (library), `seed_coordinate_map_v1` (legacy seed maps),
`<loc>__<lay>.reference_path.json`, `.calibration_laps.json`, `.station_map.json`,
`.reviewed_model.json`, `.accepted_model.json`, `__lap_offset.json`
(all under `data/track_models/`), `track_truth_model_v1` (runtime-built, no file).
**None of these formats changed this sprint.**

## 4. The read model (`data/track_context.py`)

* **`TrackIdentity`** (frozen) — ids + display names + `combined_id`
  (`<loc>__<lay>`, matching every per-layout file convention) + `is_complete`.
* **`TrackMapAvailability`** (frozen) — seed metadata/lap-length/corner-window/
  sector/complex/coordinate-geometry availability + `seed_source`; reference
  path / calibration laps / station map / reviewed / accepted / lap-offset
  availability with counts.
* **`TrackGeometryStatus`** (frozen) — `modelling_status` (resolver value wins,
  seed value fallback), `ai_ready`, resolver `resolution_status` +
  `model_source_type`, corners_expected, seed/model lap lengths, and the three
  track-truth gates **echoed tri-state** (None = no validation supplied).
* **`TrackAlignmentStatus`** (frozen) — `available` (requires an
  alignment-shaped object), match status, accepted (+at), lap delta, blocker /
  warning counts, corner position match.
* **`TrackContext`** (frozen) — identity + source + the three status blocks +
  lap-offset status/confidence + `change_hash` + `event_change_hash`; helpers
  `matches_event` (tri-state: None when uncomparable), `mismatches_event`
  (True only on a possible-and-failing comparison), `is_stale_for_event`,
  `can_attempt_live_mapping`, `live_mapping_blockers()`, `summary_line`,
  `to_summary_lines`, `to_dict`.
* **`TrackContextSource`** — EMPTY / TRACK_MODELLING_UI / EVENT_CONTEXT /
  LEGACY_STRATEGY / SEED_LIBRARY. Identity priority: UI combos → EventContext →
  `config["strategy"]` ids → seed objects.
* **`TrackContextValidationResult`** — keeps `identity_warnings`/`identity_missing`
  **separate** from `availability_warnings` (what's absent) and
  `staleness_warnings` (event mismatch / drift). `.warnings` concatenates.
* **`build_track_context(...)`** — takes **duck-typed results the existing
  loaders already produce** (`SeedAuditResult`, `TrackModelFileAudit`,
  `TrackModelResolverResult`, `TrackModelAlignmentResult`,
  `LapStartOffsetCalibration`, `TrackTruthValidationResult`, seed objects,
  station map). **No file I/O, no invented geometry truth.** Never raises;
  EMPTY on garbage.
* **`compute_change_hash()`** — 12-char marker over identity + availability +
  status **only** (event drift tracked via `event_change_hash`).
* **`flow_flags(ctx)`** — splat-safe `ui.product_flow` bridge (`has_track`
  only), merge-composable with `event_context.flow_flags`.

Purity: no PyQt6, no UI, no DB, no network/AI, no file I/O.

## 5. What was migrated this sprint

- **`ui/track_modelling_ui.py` `_build_track_context()` (NEW)** — assembles the
  TrackContext from state the tab already holds (combo ids, loaded seed layout,
  `audit_layout_seed` + `audit_track_model_files` — the same audits the tab
  already runs on layout change — plus `_tm_station_map` /
  `_tm_alignment_result` / `_tm_offset_calibration`) keyed to
  `_build_event_context()`. Defensive; never raises; writes nothing.
- **`_tm_refresh_track_truth_panel()`** — track/layout identity now read through
  the canonical TrackContext instead of raw combo reads, and the context is
  captured into `self._last_track_context` for later staleness surfacing.
  **Strictly behaviour-preserving:** only a combo-sourced identity
  (`TrackContextSource.TRACK_MODELLING_UI`) drives the panel — an empty combo
  selection keeps showing the empty state exactly as before (TrackContext's
  event/config fallback is deliberately not used here).

Everything else still reads the legacy stores (compatibility preserved).

## 6. Consumers intentionally deferred (and why)

| Consumer | Reads | Why deferred |
|----------|-------|--------------|
| `_tm_update_live_map_dot` + `resolve_live_segment` inputs | combo ids | **Live map matching behaviour** — identity timing matters mid-session; migrate with tests + runtime UAT. |
| `strategy/track_context_prompt.get_track_context_for_ai` + `_run_practice_analysis`/`_assemble_strategy_inputs` id reads | `config["strategy"]` ids | **AI prompt paths** — migrate in the AI Snapshot sprint together with the frozen Event/Strategy/Setup snapshots. |
| `_tm_on_layout_changed` config fan-out (track_modelling_ui.py:928-929) | writer | The Group 17H **writer** — removed only when all id readers consume TrackContext (source-scanned as intentionally unchanged in `tests/test_track_context.py`). |
| Event Planner `_evt_track` ↔ strategy `track` name writes | writer | Event-side writer; belongs to the fan-out removal sprint. |
| `_tm_refresh_alignment_panel` / `_tm_refresh_details` / `_tm_audit_and_show_saved_files` label pipelines | raw result objects | Display-heavy panels driven by existing vm formatters that take the raw objects; rerouting through TrackContext is safe-but-wide — defer to a dedicated pass. |
| Calibration / detection / review / accept workflows | volatile attributes | Behaviour-bearing writers; out of scope by sprint constraint. |

## 7. Risks

- **Stale track model risk.** Artefact files persist per `<loc>__<lay>` and are
  auto-loaded on layout selection; nothing invalidates them if the seed or
  library data changes afterwards. TrackContext's `change_hash` now makes this
  *detectable* (hash changes when availability/status changes) but nothing yet
  *surfaces* it. `_last_track_context` is captured but not displayed.
- **Station-map-vs-reference-path staleness** is only partially detectable
  today: `TrackModelFileAudit` records the reference-path mtime but no station
  map mtime. Deferred honestly rather than half-implemented — extend the file
  audit first, then add the comparison helper.
- **Map-alignment risk.** Alignment lives twice (volatile `_tm_alignment_result`
  + accepted-model file); an accepted file loaded from disk has empty
  `corner_alignments` (import limitation). TrackContext only *represents* the
  counts, so it is not affected, but any future deeper consumer must load the
  full object.
- **Track library risk.** Library-first with legacy fallback means the same
  layout can resolve differently as files appear; `seed_source` is carried on
  the context so consumers can see which path fed it.
- **Identity fallback risk.** TrackContext falls back to `config["strategy"]`
  ids, which the Track Modelling combos wrote — the fallback is only as fresh as
  the last combo selection. This is exactly the SSOT-2 problem; it is
  documented, not solved, this sprint.
- **No Daytona accuracy claims.** Daytona still has no seed coordinate geometry;
  contexts built for it report `seed_geometry_available=False` and echoed-False
  truth gates, and validation keeps warning about missing geometry even when
  everything else is present (test-enforced).

## 8. Recommended next sprint

**AI Snapshot Migration** — the four read models now exist (Event, Strategy,
Setup, Track); the remaining highest-value risk is the AI-input paths assembling
state live from `config["strategy"]` + scattered ids. Thread frozen
`EventContext` + `StrategyPromptSnapshot` + `SetupPromptSnapshot` + a
`TrackContext` snapshot into `_run_practice_analysis` /
`_assemble_strategy_inputs` / `_run_ai_analysis` /
`build_setup_advice_response` / `get_track_context_for_ai`, proving prompts are
byte-identical before/after, then surface the stale indicators
(`_last_setup_context`, `_last_track_context`) in the UI.

Alternative: **Home Dashboard Build** — render the missing home/overview panel
from `build_flow_state_summary(**{**event_flags, **track_flags, …})`, which now
has real inputs from all four contexts. Lower risk, visible payoff; reasonable
to do first if a breather from state work is preferred.
